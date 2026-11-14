# ---------------------------------------------------------------- shared helpers (library helper block, as in the prop guns)
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_<name>.py -- <out dir>
# 1 unit = 1 m, front toward -Y, up +Z. Everything is built into ONE bmesh with per-face material indices,
# so there is no join and no slot shuffle.
import bpy, bmesh, sys, math, os, subprocess
from mathutils import Vector, Matrix

OUT = sys.argv[sys.argv.index('--') + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# shared palette: same name = same colour in every library model of this batch
# (name: rgb, roughness, metallic, emission, alpha)
PALETTE = {
    'Steel':      ((0.30, 0.31, 0.32), 0.45, 0.6, 0, 1),
    'Black':      ((0.025, 0.025, 0.027), 0.6, 0.0, 0, 1),
    'Wood':       ((0.45, 0.20, 0.075), 0.7, 0.0, 0, 1),
    'WoodDark':   ((0.36, 0.155, 0.055), 0.75, 0.0, 0, 1),
    'Glass':      ((0.012, 0.014, 0.018), 0.08, 0.0, 0, 1),          # lenses (dark, opaque)
    'GlassClear': ((0.22, 0.32, 0.36), 0.05, 0.0, 0, 0.35),           # vehicle glazing, same values as the vehicle anchors' Glass
    'Plastic':    ((0.035, 0.036, 0.04), 0.5, 0.0, 0, 1),
    'PlasticGrey': ((0.20, 0.205, 0.21), 0.5, 0.0, 0, 1),
    'Graphite':   ((0.075, 0.078, 0.085), 0.45, 0.3, 0, 1),
    'GripRubber': ((0.045, 0.046, 0.05), 0.85, 0.0, 0, 1),
    'PaintWhite': ((0.80, 0.80, 0.78), 0.5, 0.0, 0, 1),
    'PaintBlue':  ((0.025, 0.11, 0.42), 0.45, 0.0, 0, 1),
    'Olive':      ((0.10, 0.11, 0.06), 0.7, 0.0, 0, 1),
    'LensRed':    ((0.90, 0.06, 0.03), 0.25, 0.0, 2.5, 1),
    'LensGreen':  ((0.05, 0.75, 0.20), 0.25, 0.0, 0.8, 1),
}
ORDER = []
def use(*names):
    for n in names:
        rgb, rough, metal, emit, alpha = PALETTE[n]
        m = bpy.data.materials.new('Glass' if n == 'GlassClear' else n); m.use_nodes = True
        b = m.node_tree.nodes['Principled BSDF']
        b.inputs['Base Color'].default_value = (*rgb, 1); b.inputs['Roughness'].default_value = rough
        b.inputs['Metallic'].default_value = metal; m.diffuse_color = (*rgb, alpha)
        if emit:
            b.inputs['Emission Color'].default_value = (*rgb, 1); b.inputs['Emission Strength'].default_value = emit
        if alpha < 1:
            b.inputs['Alpha'].default_value = alpha
            try: m.surface_render_method = 'BLENDED'
            except Exception: pass
        ORDER.append(m)
    return range(len(names))

BM = bmesh.new()
def add(tbm, M=None, mi=None):
    """Copy a temporary bmesh into the model, optionally transformed and recoloured."""
    if M is not None: tbm.transform(M)
    vmap = {v: BM.verts.new(v.co) for v in tbm.verts}
    for f in tbm.faces:
        try:
            nf = BM.faces.new([vmap[v] for v in f.verts]); nf.material_index = f.material_index if mi is None else mi
        except ValueError: pass
    tbm.free()

def _bevel(bm, bev, segs):
    if bev: bmesh.ops.bevel(bm, geom=bm.edges[:] + bm.verts[:], offset=bev, segments=segs, affect='EDGES', profile=0.5, clamp_overlap=True)

def box(lo, hi, mi, bev=0.01, segs=2, M=None, ret=False):
    c = [(lo[i] + hi[i]) / 2 for i in range(3)]; s = [hi[i] - lo[i] for i in range(3)]
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((*s, 1)))
    _bevel(bm, bev, segs)
    if ret:
        for f in bm.faces: f.material_index = mi
        return bm
    add(bm, M, mi)

def hexa(corners, mi, bev=0.01, segs=2, M=None):
    """Box with free corners: corners[(sx, sy, sz)] = (x, y, z) for sx, sy, sz in -1/1."""
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=2.0)
    for v in bm.verts: v.co = Vector(corners[(round(v.co.x), round(v.co.y), round(v.co.z))])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces); _bevel(bm, bev, segs); add(bm, M, mi)

def lathe(prof, n, mi, M=None, rfun=None, cap_top=True, cap_bot=True):
    """prof: list of (r, z) or (r, z, mi_segment). rfun(angle, r, z) -> (r, mi or None) bends the ring per angle."""
    bm = bmesh.new(); rings = []
    for p in prof:
        r, z = p[0], p[1]; ring = []
        for k in range(n):
            a = 2 * math.pi * k / n; rr = r
            if rfun: rr = rfun(a, r, z)[0]
            ring.append(bm.verts.new((rr * math.cos(a), rr * math.sin(a), z)))
        rings.append(ring)
    def segmi(i, k):
        m = prof[i][2] if len(prof[i]) > 2 else mi
        if rfun:
            a = 2 * math.pi * (k + 0.5) / n; o = rfun(a, prof[i][0], (prof[i][1] + prof[i + 1][1]) / 2)[1]
            if o is not None: m = o
        return m
    for i in range(len(prof) - 1):
        for k in range(n):
            f = bm.faces.new([rings[i][k], rings[i][(k + 1) % n], rings[i + 1][(k + 1) % n], rings[i + 1][k]]); f.material_index = segmi(i, k)
    if cap_bot and prof[0][0] > 1e-6: f = bm.faces.new(rings[0][::-1]); f.material_index = prof[0][2] if len(prof[0]) > 2 else mi
    if cap_top and prof[-1][0] > 1e-6: f = bm.faces.new(rings[-1]); f.material_index = prof[-2][2] if len(prof[-2]) > 2 else mi
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces); add(bm, M)

def cyl(r, z0, z1, mi, n=24, M=None, bev=0.0):
    if bev: prof = [(r - bev, z0), (r, z0 + bev), (r, z1 - bev), (r - bev, z1)]
    else: prof = [(r, z0), (r, z1)]
    lathe(prof, n, mi, M)

def prism(poly, d0, d1, mi, axis='Z', bev=0.0, segs=2, M=None, ret=False):
    """Extrude a 2D polygon. axis 'Z': poly in XY, depth Z. 'X': poly in (Y, Z), depth X. 'Y': poly in (X, Z), depth Y."""
    bm = bmesh.new()
    def P(u, v, d):
        return {'Z': (u, v, d), 'X': (d, u, v), 'Y': (u, d, v)}[axis]
    a = [bm.verts.new(P(u, v, d0)) for u, v in poly]; b = [bm.verts.new(P(u, v, d1)) for u, v in poly]
    n = len(poly); bm.faces.new(a[::-1]); bm.faces.new(b)
    for i in range(n): bm.faces.new([a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces); _bevel(bm, bev, segs)
    if ret:
        for f in bm.faces: f.material_index = mi
        return bm
    add(bm, M, mi)

def stroke(pts, w, d0, d1, mi, axis='X', bev=0.0, segs=2, M=None):
    """Thick 2D polyline (mitred), extruded like prism(): frames, brackets, curved magazines."""
    P = [Vector((p[0], p[1])) for p in pts]; L, R = [], []
    for i, p in enumerate(P):
        t0 = (P[i] - P[i - 1]).normalized() if i > 0 else (P[1] - P[0]).normalized()
        t1 = (P[i + 1] - P[i]).normalized() if i < len(P) - 1 else t0
        t = (t0 + t1).normalized(); nrm = Vector((-t.y, t.x)); s = w / 2 / max(0.3, nrm.dot(Vector((-t0.y, t0.x))))
        L.append(p + nrm * s); R.append(p - nrm * s)
    prism([tuple(v) for v in L + R[::-1]], d0, d1, mi, axis, bev, segs, M)

def tube(pts, r, mi, n=12, fillet=0.08, steps=6):
    Pt = [Vector(p) for p in pts]; path = [Pt[0]]
    for i in range(1, len(Pt) - 1):
        a, b, c = Pt[i - 1], Pt[i], Pt[i + 1]; f = min(fillet, (a - b).length / 2, (c - b).length / 2)
        s, e = b + (a - b).normalized() * f, b + (c - b).normalized() * f
        for k in range(steps + 1): t = k / steps; path.append((1 - t) ** 2 * s + 2 * (1 - t) * t * b + t ** 2 * e)
    path.append(Pt[-1]); bm = bmesh.new(); rings = []
    for i, p in enumerate(path):
        t = (path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]).normalized()
        u = t.cross(Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))).normalized(); v = t.cross(u)
        rings.append([bm.verts.new(p + r * (math.cos(2 * math.pi * k / n) * u + math.sin(2 * math.pi * k / n) * v)) for k in range(n)])
    for i in range(len(rings) - 1):
        for k in range(n): bm.faces.new([rings[i][k], rings[i][(k + 1) % n], rings[i + 1][(k + 1) % n], rings[i + 1][k]])
    bm.faces.new(rings[0][::-1]); bm.faces.new(rings[-1]); bmesh.ops.recalc_face_normals(bm, faces=bm.faces); add(bm, None, mi)

def rotx(a): return Matrix.Rotation(math.radians(a), 4, 'X')
def roty(a): return Matrix.Rotation(math.radians(a), 4, 'Y')
def rotz(a): return Matrix.Rotation(math.radians(a), 4, 'Z')
def at(x, y, z): return Matrix.Translation((x, y, z))
ALONG = rotx(-90)                               # lathe axis Z -> +Y
BACK = rotx(90)                                 # lathe axis Z -> -Y (toward the muzzle / nose)

def shift(dx, dy, dz):
    bmesh.ops.translate(BM, verts=BM.verts, vec=(dx, dy, dz))

def finish(NAME, seat=None, smooth_angle=35):
    """Weld, smooth, export FBX exactly like the anchors, print stats."""
    bmesh.ops.remove_doubles(BM, verts=BM.verts, dist=0.0002)
    me = bpy.data.meshes.new(NAME + '_Mesh'); BM.to_mesh(me)
    for m in ORDER: me.materials.append(m)
    me.shade_smooth(); me.set_sharp_from_angle(angle=math.radians(smooth_angle))
    obj = bpy.data.objects.new(NAME + '_Mesh', me); scene.collection.objects.link(obj)
    root = bpy.data.objects.new(NAME, None); scene.collection.objects.link(root); obj.parent = root
    if seat:
        s = bpy.data.objects.new('Seat', None); scene.collection.objects.link(s); s.parent = root; s.location = seat
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    xs = [v.co for v in me.vertices]; lo = [min(v[a] for v in xs) for a in range(3)]; hi = [max(v[a] for v in xs) for a in range(3)]
    used = sorted({p.material_index for p in me.polygons})
    print(f'[{NAME}] triangles {tris}, materials {len(used)} {[ORDER[i].name for i in used]}, '
          f'size {hi[0]-lo[0]:.3f} x {hi[1]-lo[1]:.3f} x {hi[2]-lo[2]:.3f} m, '
          f'x {lo[0]:.3f}..{hi[0]:.3f} y {lo[1]:.3f}..{hi[1]:.3f} z {lo[2]:.3f}..{hi[2]:.3f}')
    for o in scene.objects: o.select_set(True)
    bpy.ops.export_scene.fbx(filepath=f'{OUT}/{NAME}.fbx', use_selection=True, apply_unit_scale=True,
                             apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)
    return lo, hi

def stage(lo):
    """Plain light grey backdrop with a soft shadow, sun, Eevee at 1672x941; returns the camera."""
    world = bpy.data.worlds.new('W'); scene.world = world; world.use_nodes = True
    wn = world.node_tree.nodes; wl = world.node_tree.links
    wn['Background'].inputs['Color'].default_value = (0.62, 0.62, 0.63, 1)        # what lights the model
    wn['Background'].inputs['Strength'].default_value = 0.6
    bgc = wn.new('ShaderNodeBackground'); bgc.inputs['Color'].default_value = (0.78, 0.78, 0.78, 1)   # what the camera sees
    lp = wn.new('ShaderNodeLightPath'); mix = wn.new('ShaderNodeMixShader')
    wl.new(lp.outputs['Is Camera Ray'], mix.inputs['Fac']); wl.new(wn['Background'].outputs[0], mix.inputs[1])
    wl.new(bgc.outputs[0], mix.inputs[2]); wl.new(mix.outputs[0], wn['World Output'].inputs['Surface'])
    gm = bpy.data.materials.new('GroundM'); gm.use_nodes = True; gb = gm.node_tree.nodes['Principled BSDF']
    gb.inputs['Base Color'].default_value = (0.10, 0.10, 0.10, 1); gb.inputs['Roughness'].default_value = 0.95
    gb.inputs['Emission Color'].default_value = (0.78, 0.78, 0.78, 1); gb.inputs['Emission Strength'].default_value = 0.86
    gme = bpy.data.meshes.new('Ground'); g = bmesh.new(); bmesh.ops.create_grid(g, x_segments=1, y_segments=1, size=200); g.to_mesh(gme); g.free()
    gme.materials.append(gm); ground = bpy.data.objects.new('Ground', gme); scene.collection.objects.link(ground); ground.location.z = lo[2]
    sd = bpy.data.lights.new('Sun', 'SUN'); sd.energy = 2.6; sd.angle = math.radians(12)
    sun = bpy.data.objects.new('Sun', sd); scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(40), 0, math.radians(-30))
    scene.render.engine = 'BLENDER_EEVEE'; scene.view_settings.view_transform = 'Standard'
    scene.render.resolution_x, scene.render.resolution_y = 1672, 941
    cd = bpy.data.cameras.new('Cam'); cam = bpy.data.objects.new('Cam', cd); scene.collection.objects.link(cam); scene.camera = cam
    return cam, sun

def render(lo, hi, az=-35, el=18, lens=50, fill=0.98, side=None, sun=None, fit=None):
    """Three-quarter preview with the camera fitted to the bbox; side='+X' adds an orthographic side view."""
    from bpy_extras.object_utils import world_to_camera_view
    cam, sunobj = stage(lo); cd = cam.data; cd.lens = lens
    if sun: sunobj.rotation_euler = (math.radians(sun[0]), 0, math.radians(az + sun[1]))     # light from the camera side
    c = Vector([(lo[i] + hi[i]) / 2 for i in range(3)])
    corners = fit or [Vector(v.co) for o in scene.objects if o.type == 'MESH' and o.name.endswith('_Mesh') for v in o.data.vertices][::3]
    d = Vector((math.sin(math.radians(az)) * math.cos(math.radians(el)), -math.cos(math.radians(az)) * math.cos(math.radians(el)), math.sin(math.radians(el))))
    def place(dist):
        cam.location = c + d * dist; cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler(); bpy.context.view_layer.update()
        p = [world_to_camera_view(scene, cam, v) for v in corners]
        return max(max(abs(q.x - 0.5), abs(q.y - 0.5)) * 2 for q in p)
    a, b = 0.3, 200.0
    for _ in range(40):
        m = (a + b) / 2
        if place(m) > fill: a = m
        else: b = m
    place(b)
    scene.render.filepath = f'{OUT}/render-34.png'; bpy.ops.render.render(write_still=True)
    if side:
        cd.type = 'ORTHO'; L = hi[1] - lo[1]; cd.ortho_scale = L / 0.92
        cam.location = (40, c[1], c[2]); cam.rotation_euler = (math.pi / 2, 0, math.pi / 2)
        sunobj.rotation_euler = (math.radians(50), 0, math.radians(75))
        scene.render.filepath = f'{OUT}/render-side.png'; bpy.ops.render.render(write_still=True)

def compare():
    ref = f'{OUT}/ref-34.png'; ren = f'{OUT}/render-34.png'; out = f'{OUT}/compare.jpg'
    if os.path.exists(f'{OUT}/ref-side.png') and os.path.exists(f'{OUT}/render-side.png'):
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', ref, '-i', ren, '-i', f'{OUT}/ref-side.png', '-i', f'{OUT}/render-side.png',
                        '-filter_complex', '[0]scale=836:470[a];[1]scale=836:470[b];[2]scale=836:470[c];[3]scale=836:470[d];'
                        '[a][b]hstack[t];[c][d]hstack[u];[t][u]vstack', '-q:v', '3', out])
    elif os.path.exists(ref):
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', ref, '-i', ren, '-filter_complex',
                        '[0]scale=-2:941[a];[a][1]hstack', '-q:v', '3', out])
    else: subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', ren, '-q:v', '3', out])
# ---------------------------------------------------------------- model
# Generic light utility helicopter (own design, civilian, no markings). About 12 m nose to tail, main rotor 10.5 m,
# 3.2 m tall. Built with y = metres back from the nose, then centred on the footprint. Left side is +X (tail rotor side).
# Fuselage and cowling are lofted superellipse sections; colours, glazing, frames and door seams are face bands of the loft.
NAME = 'Helicopter'
WH, BLU, GL, BL, GR, IN, LR, LG = use('PaintWhite', 'PaintBlue', 'GlassClear', 'Black', 'Graphite', 'PlasticGrey', 'LensRed', 'LensGreen')

def catmull(keys, d, idx):
    ds = [k[0] for k in keys]
    if d <= ds[0]: return keys[0][idx]
    if d >= ds[-1]: return keys[-1][idx]
    i = max(j for j in range(len(ds) - 1) if ds[j] <= d)
    t = (d - ds[i]) / (ds[i + 1] - ds[i])
    p0 = keys[max(i - 1, 0)][idx]; p1 = keys[i][idx]; p2 = keys[i + 1][idx]; p3 = keys[min(i + 2, len(keys) - 1)][idx]
    v = 0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)
    return v

def section(keys, d):
    return [catmull(keys, d, i) for i in range(1, 5)]          # hw, zb, zt, n

def loft(keys, dlist, Ffun, matfn, cap0=True, cap1=True):
    """keys: (d, half width, z bottom, z top, superellipse n). Ffun(d) -> sorted z-fractions -1..1 for the half ring.
    matfn(d, f, x) -> material index for the face centred there."""
    bm = bmesh.new(); rings = []; meta = []
    for d in dlist:
        hw, zb, zt, n = section(keys, d); zc, hh = (zb + zt) / 2, (zt - zb) / 2
        F = Ffun(d)
        half = [(hw * max(0.0, 1 - abs(f) ** n) ** (1 / n), zc + hh * f, f) for f in F]
        ring = half + [(-x, z, f) for x, z, f in half[-2:0:-1]]
        rings.append([bm.verts.new((x, d, z)) for x, z, f in ring]); meta.append([f for x, z, f in ring])
    m = len(rings[0])
    for i in range(len(rings) - 1):
        for k in range(m):
            k2 = (k + 1) % m
            vs = [rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]]
            c = sum((v.co for v in vs), Vector()) / 4
            fc = (meta[i][k] + meta[i][k2] + meta[i + 1][k] + meta[i + 1][k2]) / 4
            try:
                f = bm.faces.new(vs); f.material_index = matfn(c.y, fc, c.x)
            except ValueError: pass
    if cap0: f = bm.faces.new(rings[0][::-1]); f.material_index = matfn(dlist[0], 0.0, 0.0)
    if cap1: f = bm.faces.new(rings[-1]); f.material_index = matfn(dlist[-1], 0.0, 0.0)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    add(bm)

def dsamples(d0, d1, step, keys=()):
    ks = [k for k in keys if d0 <= k <= d1]
    base = [round(d0 + i * step, 4) for i in range(int((d1 - d0) / step) + 1)] + [d0, d1]
    base = [b for b in base if all(abs(b - k) > 0.012 for k in ks) or b in (d0, d1)]
    return sorted(set(base + ks))

def fill_fracs(nfill, keys):
    base = [math.sin(math.radians(-90 + 180 * i / nfill)) for i in range(nfill + 1)]
    base = [math.copysign(abs(b) ** 0.8, b) for b in base]
    base = [round(b, 4) for b in base if all(abs(b - k) > 0.025 for k in keys)]
    return sorted(set(base + list(keys) + [-1.0, 1.0]))

# ---------------------------------------------------------------- fuselage (cabin + tail boom in one loft)
FUS = [(0.00, 0.12, 1.00, 1.30, 2.2), (0.12, 0.52, 0.76, 1.70, 2.3), (0.40, 0.76, 0.62, 2.06, 2.5), (0.85, 0.90, 0.57, 2.34, 2.7),
       (1.40, 0.95, 0.56, 2.48, 2.9), (2.20, 0.96, 0.56, 2.52, 3.0), (3.00, 0.95, 0.58, 2.52, 3.0), (3.60, 0.90, 0.64, 2.48, 2.9),
       (4.20, 0.74, 0.80, 2.36, 2.6), (4.80, 0.56, 1.02, 2.20, 2.3), (5.40, 0.42, 1.22, 2.08, 2.1), (6.20, 0.33, 1.38, 2.00, 2.0),
       (8.50, 0.24, 1.50, 1.94, 2.0), (10.60, 0.17, 1.58, 1.90, 2.0), (11.10, 0.13, 1.62, 1.88, 2.0), (11.25, 0.06, 1.68, 1.82, 2.0)]
WS1 = 1.30                                  # windshield ends (front door pillar starts)
DOOR_F = (1.38, 2.46); DOOR_R = (2.50, 3.52)
WIN_F = (1.48, 2.36); WIN_R = (2.60, 3.42)
KD = [0.12, 0.85, WS1 - 0.06, WS1, DOOR_F[0], DOOR_F[0] + 0.025, WIN_F[0] - 0.05, WIN_F[0], WIN_F[1], WIN_F[1] + 0.05,
      DOOR_F[1], DOOR_R[0], WIN_R[0] - 0.05, WIN_R[0], WIN_R[1], WIN_R[1] + 0.05, DOOR_R[1] - 0.025, DOOR_R[1], 9.25, 9.7]
FW = (-0.24, 0.66); FWF = (-0.30, 0.72)      # side window glass and frame (z fractions)
CHIN = (-0.80, -0.52); WSB = (-0.44, -0.38)   # chin window, windshield bottom frame
SEAMTOP = (0.80, 0.83)
KF = [-1.0, CHIN[0], CHIN[1], WSB[0], WSB[1], FWF[0], FW[0], FW[1], FWF[1], SEAMTOP[0], SEAMTOP[1], 1.0]
FIX = fill_fracs(14, KF)

def swoop(d):
    """z fraction of the blue/white line: low along the cabin, sweeping up into the boom centre line."""
    if d <= 0.5: return -0.42
    if d <= 3.2: return -0.42 + (d - 0.5) / 2.7 * 0.08
    if d <= 5.6:
        t = (d - 3.2) / 2.4; t = t * t * (3 - 2 * t); return -0.34 + t * 0.59
    return 0.25

def fus_fracs(d):
    s = swoop(d)
    for f in FIX:
        if abs(f - s) < 0.012: s = f + 0.012
    return sorted(FIX + [s])

def fus_mat(d, f, x):
    ax = abs(x)
    if CHIN[0] < f < CHIN[1] and 0.12 < d < 0.85 and ax > 0.10: return GL
    if f < swoop(d) - 1e-4: return BLU
    if d < 0.02: return WH
    # windshield + nose bubble
    if d < WS1:
        if CHIN[0] < f < CHIN[1] and 0.12 < d < 0.85 and ax > 0.10: return GL
        if d > WS1 - 0.06 and f > WSB[0]: return BL
        if WSB[0] < f < WSB[1]: return BL
        if f > WSB[1]:
            if ax < 0.05: return BL                     # centre post
            if d > 0.85 and f > 0.93: return WH         # roof
            return GL
        return WH
    if ax > 0.35:
        for (w0, w1) in (WIN_F, WIN_R):
            if w0 < d < w1 and FW[0] < f < FW[1]: return GL
            if w0 - 0.05 < d < w1 + 0.05 and FWF[0] < f < FWF[1]: return BL
        for (a, b) in ((DOOR_F[0], DOOR_F[0] + 0.025), (DOOR_F[1], DOOR_R[0]), (DOOR_R[1] - 0.025, DOOR_R[1])):
            if a < d < b and f < SEAMTOP[1]: return BL
        if DOOR_F[0] < d < DOOR_R[1] and SEAMTOP[0] < f < SEAMTOP[1]: return BL
    return WH

DL = dsamples(0.0, 1.4, 0.06, KD) + [d for d in dsamples(1.4, 6.2, 0.10, KD) if d > 1.4] + \
     [d for d in dsamples(6.2, 11.25, 0.35, KD) if d > 6.2]
loft(FUS, sorted(set(DL)), fus_fracs, fus_mat)

# ---------------------------------------------------------------- engine cowling with louvres, mast fairing, exhaust
COWL = [(2.95, 0.12, 2.36, 2.52, 2.4), (3.15, 0.54, 2.32, 2.74, 2.8), (3.60, 0.62, 2.30, 2.82, 3.0), (4.70, 0.60, 2.15, 2.78, 3.0),
        (5.30, 0.44, 1.95, 2.54, 2.6), (5.75, 0.20, 1.80, 2.20, 2.2)]
def cowl_mat(d, f, x):
    if abs(x) > 0.3 and -0.05 < f < 0.55:
        for k in range(4):
            a = 4.00 + k * 0.13
            if a < d < a + 0.07: return BL
    return WH
CKD = [4.00 + k * 0.13 for k in range(4)] + [4.07 + k * 0.13 for k in range(4)]
loft(COWL, dsamples(2.95, 5.75, 0.12, CKD), lambda d: fill_fracs(10, [-0.05, 0.55]), cowl_mat)
# cowling side seam (access panel line)
for s in (-1, 1):
    box((s * 0.615 - 0.006, 3.55, 2.38), (s * 0.615 + 0.006, 3.57, 2.76), BL, 0.0, 1)
lathe([(0.30, 2.76), (0.30, 2.80), (0.22, 2.85), (0.13, 2.88), (0.0, 2.88)], 24, WH, at(0, 3.35, 0))     # mast fairing
cyl(0.075, 2.84, 3.00, GR, 16, at(0, 3.35, 0))                                                            # mast
cyl(0.15, 2.87, 2.91, GR, 20, at(0, 3.35, 0), 0.01)                                                       # swashplate
lathe([(0.0, 2.94), (0.24, 2.94), (0.26, 2.97), (0.26, 3.02), (0.20, 3.06), (0.10, 3.09), (0.0, 3.10)], 24, GR, at(0, 3.35, 0))  # hub
for k in range(4):
    a = 45 + 90 * k; R = at(0, 3.35, 0) @ rotz(a)
    box((0.20, -0.05, 2.945), (0.60, 0.05, 3.025), GR, 0.012, 2, R)                                     # blade grip
    box((0.55, -0.15, 2.965), (4.95, 0.13, 3.005), GR, 0.012, 2, R)                                     # blade
    box((4.95, -0.15, 2.965), (5.25, 0.13, 3.005), BLU, 0.012, 2, R)                                    # painted tip
    cyl(0.012, 2.90, 2.96, BL, 8, R @ at(0.22, 0.09, 0))                                                 # pitch link
lathe([(0.0, -0.05), (0.13, -0.05), (0.12, 0.10), (0.10, 0.34), (0.08, 0.36), (0.0, 0.36)], 16, GR,
      at(0, 5.55, 2.30) @ rotx(-70))                                                                     # exhaust stack
cyl(0.075, 0.36, 0.37, BL, 16, at(0, 5.55, 2.30) @ rotx(-70))
lathe([(0.0, 0.0), (0.05, 0.0), (0.05, 0.03), (0.035, 0.06), (0.0, 0.07)], 12, LR, at(0, 4.75, 2.77))     # anti-collision beacon
box((-0.01, 2.0, 2.48), (0.01, 2.06, 2.70), BL, 0.004, 1)               # roof antenna

# ---------------------------------------------------------------- tail: fins, stabiliser, tail rotor
TFX = 0.045
prism([(10.20, 1.80), (10.95, 2.66), (11.15, 2.90), (11.62, 2.90), (11.72, 2.78), (11.45, 1.76)], -TFX, TFX, BLU, 'X', 0.02, 2)
prism([(10.76, 2.22), (11.00, 2.50), (11.64, 2.50), (11.58, 2.22)], -TFX - 0.004, TFX + 0.004, WH, 'X', 0.006, 1)  # white band
prism([(11.00, 1.66), (11.28, 1.20), (11.55, 1.17), (11.62, 1.24), (11.42, 1.70)], -TFX, TFX, BLU, 'X', 0.02, 2)    # ventral fin
prism([(11.28, 1.20), (11.70, 1.14), (11.72, 1.18), (11.55, 1.22)], -0.02, 0.02, GR, 'X', 0.008, 1)                  # tail skid
# horizontal stabiliser with end plates and position lights
prism([(9.25, 1.70), (9.33, 1.73), (9.68, 1.72), (9.70, 1.69), (9.30, 1.67)], -1.0, 1.0, WH, 'X', 0.01, 2)
for s in (-1, 1):
    x0, x1 = (0.98, 1.03) if s > 0 else (-1.03, -0.98)
    prism([(9.22, 1.55), (9.35, 1.95), (9.62, 1.95), (9.70, 1.55)], x0, x1, BLU, 'X', 0.01, 2)
    xl = 1.035 if s > 0 else -1.035
    box((xl - 0.012, 9.40, 1.70), (xl + 0.012, 9.50, 1.76), LR if s > 0 else LG, 0.006, 1)
# tail rotor on the left (+X) side: gearbox, hub, two blades
cyl(0.09, 0.0, 0.20, GR, 16, at(0.04, 11.30, 2.02) @ roty(90), 0.01)
cyl(0.06, 0.20, 0.30, GR, 16, at(0.04, 11.30, 2.02) @ roty(90), 0.01)
for k in (0, 1):
    R = at(0.30, 11.30, 2.02) @ rotx(25 + 180 * k)
    box((-0.012, -0.065, 0.05), (0.012, 0.065, 0.82), GR, 0.008, 1, R)
    box((-0.013, -0.066, 0.70), (0.013, 0.066, 0.82), BLU, 0.006, 1, R)
lathe([(0.0, 0.29), (0.07, 0.29), (0.07, 0.33), (0.04, 0.37), (0.0, 0.38)], 12, GR, at(0.04, 11.30, 2.02) @ roty(90))
# drive shaft cover on top of the boom
box((-0.06, 5.90, 1.92), (0.06, 10.20, 1.97), WH, 0.02, 2)

# ---------------------------------------------------------------- cabin interior: floor, console, seats, cyclic
box((-0.60, 1.00, 0.72), (0.60, 3.50, 0.76), IN, 0.0, 1)
box((-0.56, 0.66, 0.80), (0.56, 0.98, 1.22), IN, 0.03, 2)                       # instrument console
box((-0.62, 0.74, 1.22), (0.62, 1.02, 1.28), BL, 0.02, 2)                       # glare shield
def seat(x, d, w=0.44):
    box((x - w / 2, d - 0.24, 0.76), (x + w / 2, d + 0.24, 0.96), IN, 0.04, 2)
    hexa({(sx, sy, sz): (x + sx * w / 2, d + 0.22 + 0.05 * sy + (0.10 if sz > 0 else 0), 0.98 if sz < 0 else 1.66)
          for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)}, IN, 0.035, 2)
for x in (-0.40, 0.40): seat(x, 1.80, 0.46)
for x in (-0.33, 0.33): seat(x, 3.05, 0.50)
for x in (-0.40, 0.40):
    tube([(x, 1.35, 0.76), (x, 1.32, 1.02)], 0.014, BL, 8)                    # cyclic
    box((x - 0.02, 1.29, 1.02), (x + 0.02, 1.35, 1.10), BL, 0.008, 1)

for s in (-1, 1):                                                               # door handles
    for d in (2.26, 3.36):
        box((s * 0.945 - 0.02, d - 0.07, 1.18), (s * 0.945 + 0.02, d + 0.07, 1.22), BL, 0.008, 1)
DZ = 0.10                                                                       # airframe sits on taller gear
bmesh.ops.translate(BM, verts=BM.verts[:], vec=(0, 0, DZ))

# ---------------------------------------------------------------- landing gear: skids, cross tubes, steps
SX = 1.25
for s in (-1, 1):
    x = s * SX
    tube([(x, 0.50, 0.46), (x, 0.95, 0.045), (x, 4.70, 0.045), (x, 4.95, 0.14)], 0.045, GR, 12, 0.30, 6)
    for d in (1.70, 3.60):
        box((x - 0.06, d - 0.10, 0.06), (x + 0.06, d + 0.10, 0.11), GR, 0.02, 1)       # saddle clamp
    box((s * 0.95 - 0.10, 2.05, 0.44), (s * 0.95 + 0.10, 2.95, 0.48), BL, 0.015, 1)  # step plate
    for d in (2.15, 2.85):
        box((s * 0.82 - 0.07, d - 0.025, 0.46), (s * 0.82 + 0.07, d + 0.025, 0.92), GR, 0.01, 1)   # step bracket
for d, zt in ((1.70, 0.72), (3.60, 0.80)):
    tube([(SX, d, 0.05), (SX - 0.10, d, zt - 0.18), (0.45, d, zt), (-0.45, d, zt), (-SX + 0.10, d, zt - 0.18), (-SX, d, 0.05)],
         0.05, GR, 12, 0.22, 5)

# ---------------------------------------------------------------- centre on the footprint, export, render
xs = [v.co for v in BM.verts]
cy = (min(v.y for v in xs) + max(v.y for v in xs)) / 2
shift(0, -cy, 0)
lo, hi = finish(NAME, seat=(-0.40, 1.80 - cy, 0.96 + DZ))
FIT = [Vector(v.co) for v in bpy.data.objects[NAME + '_Mesh'].data.vertices if v.co.z < 2.95][::3]
render(lo, hi, az=50, el=12, lens=40, fill=0.96, side='+X', sun=(55, 20), fit=FIT)
compare()

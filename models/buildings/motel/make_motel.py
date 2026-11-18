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
# ---------------------------------------------------------------- extra helpers for this batch (vehicles and buildings)
PALETTE.update({
    'Red':        ((0.50, 0.025, 0.02), 0.45, 0.0, 0, 1),
    'Aluminium':  ((0.50, 0.51, 0.52), 0.35, 0.7, 0, 1),
    'LensWhite':  ((0.85, 0.85, 0.80), 0.25, 0.0, 0.6, 1),
    'LensAmber':  ((0.95, 0.50, 0.02), 0.25, 0.0, 0.8, 1),
    'Concrete':   ((0.30, 0.30, 0.29), 0.9, 0.0, 0, 1),
    'ConcreteStain': ((0.20, 0.195, 0.19), 0.95, 0.0, 0, 1),
    'White':      ((0.80, 0.80, 0.78), 0.55, 0.0, 0, 1),
    'Yellow':     ((0.80, 0.55, 0.03), 0.5, 0.0, 0, 1),
    'Teal':       ((0.03, 0.20, 0.24), 0.45, 0.0, 0, 1),
    'Interior':   ((0.035, 0.037, 0.042), 0.9, 0.0, 0, 1),
    'Fabric':     ((0.80, 0.74, 0.62), 0.95, 0.0, 0, 1),
    'Slate':      ((0.055, 0.055, 0.060), 0.85, 0.0, 0, 1),
    'Stucco':     ((0.62, 0.58, 0.50), 0.9, 0.0, 0, 1),
    'Trim':       ((0.74, 0.67, 0.51), 0.8, 0.0, 0, 1),
    'GlassBldg':  ((0.018, 0.022, 0.028), 0.25, 0.0, 0, 1),
})

def side_poly(top, zb, arches, n=14):
    """Side outline in (y, z): top runs from (y0, zb) over the body to (y1, zb); the bottom line at zb runs back
    to the front with a wheel arch (yc, zc, r) cut up into it for each axle."""
    poly = list(top)
    for yc, zc, r in sorted(arches, key=lambda a: -a[0]):
        h = zb - zc; a0 = math.asin(max(-1, min(1, h / r)))
        for k in range(n + 1):
            a = a0 + (math.pi - 2 * a0) * k / n
            poly.append((yc + r * math.cos(a), zc + r * math.sin(a)))
    return poly

def arch_flare(yc, zc, r, w, x0, x1, mi, zb, n=14):
    """Dark arch trim following the wheel arch, extruded from x0 to x1."""
    h = zb - zc; a0 = math.asin(max(-1, min(1, h / (r + w / 2))))
    pts = [(yc + (r + w / 2) * math.cos(a0 + (math.pi - 2 * a0) * k / n), zc + (r + w / 2) * math.sin(a0 + (math.pi - 2 * a0) * k / n)) for k in range(n + 1)]
    stroke(pts, w, x0, x1, mi, 'X', 0.008, 1)

def wheel(x, y, R, w, s, T, RIM, rimr=None, n=28, zc=None, hub=None, lugs=8):
    """Tyre plus dished rim; s = +1 outer face toward +X, -1 toward -X."""
    rimr = rimr or R * 0.60; zc = R if zc is None else zc; hub = RIM if hub is None else hub
    h = w / 2
    prof = [(0.0, -h + 0.03, T), (rimr * 0.9, -h + 0.03, T), (R - 0.06, -h, T), (R - 0.01, -h + 0.04, T), (R, -h + 0.08, T),
            (R, h - 0.08, T), (R - 0.01, h - 0.04, T), (R - 0.06, h, T), (rimr + 0.02, h - 0.005, T),
            (rimr, h - 0.02, RIM), (rimr * 0.93, h - 0.05, RIM), (rimr * 0.40, h - 0.07, RIM), (rimr * 0.32, h - 0.04, hub), (0.0, h - 0.035)]
    M = at(x, y, zc) @ roty(90 * s)
    lathe(prof, n, T, M)
    for k in range(lugs):
        a = 2 * math.pi * k / lugs; rr = rimr * 0.55
        cyl(0.018, h - 0.07, h - 0.045, hub, 8, M @ at(rr * math.cos(a), rr * math.sin(a), 0))

def disc(x, y, z, r, t, mi, s, n=20, rim=None, rw=0.01):
    """Round lens, gauge or cap on a side face: axis along X, outward toward s."""
    M = at(x, y, z) @ roty(90 * s)
    if rim is not None: lathe([(0.0, 0.0), (r + rw, 0.0), (r + rw, t), (r, t), (r, t * 0.6), (0.0, t * 0.6)], n, rim, M)
    else: lathe([(0.0, 0.0), (r, 0.0), (r, t * 0.7), (r * 0.85, t), (0.0, t)], n, mi, M)
    if rim is not None: cyl(r, 0.0, t * 0.62, mi, n, M)

def centre_xy():
    xs = [v.co for v in BM.verts]
    cx = (min(v.x for v in xs) + max(v.x for v in xs)) / 2; cy = (min(v.y for v in xs) + max(v.y for v in xs)) / 2
    shift(-cx, -cy, -min(v.z for v in xs)); return cx, cy
# ---------------------------------------------------------------- model

def recolour_arch(yc, zc, r, zb, mi, xmax):
    """Paint the inside of a wheel arch tunnel (faces facing the axle) with mi."""
    for f in BM.faces:
        c = f.calc_center_median(); n = f.normal
        if abs(n.x) > 0.3 or abs(c.x) > xmax or c.z < zb - 0.02: continue
        d = math.hypot(c.y - yc, c.z - zc)
        if r - 0.03 < d < r + 0.01: f.material_index = mi
PALETTE['PaintDark'] = ((0.075, 0.078, 0.085), 0.55, 0.1, 0, 1)

def addf(bm, fn, mi=None):
    """Bend a temporary bmesh vertex by vertex (fn(Vector) -> Vector), then copy it into the model."""
    for v in bm.verts: v.co = fn(v.co.copy())
    bm.normal_update(); add(bm, None, mi)
PALETTE['PaintCream'] = ((0.72, 0.67, 0.57), 0.55, 0.0, 0, 1)
PALETTE['BoatBlue'] = ((0.06, 0.17, 0.32), 0.5, 0.0, 0, 1)

def render_front(lo, hi):
    """Orthographic straight-on front view (from -Y) saved as render-side.png, for references drawn from the front."""
    cam = scene.camera; cd = cam.data; cd.type = 'ORTHO'
    W, H = hi[0] - lo[0], hi[2] - lo[2]
    cd.ortho_scale = max(W / 0.92, H / 0.92 * 1672 / 941)
    cam.location = ((lo[0] + hi[0]) / 2, lo[1] - 60, (lo[2] + hi[2]) / 2); cam.rotation_euler = (math.pi / 2, 0, 0)
    cd.clip_end = 300
    sun = bpy.data.objects.get('Sun')
    if sun: sun.rotation_euler = (math.radians(50), 0, math.radians(-25))
    scene.render.filepath = f'{OUT}/render-side.png'; bpy.ops.render.render(write_still=True)

def rrect(x0, y0, x1, y1, r, n=6):
    """Rounded rectangle outline in XY."""
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n); pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts
PALETTE['Stucco'] = ((0.62, 0.48, 0.30), 0.9, 0.0, 0, 1)
PALETTE['Sandstone'] = ((0.36, 0.28, 0.19), 0.85, 0.0, 0, 1)
PALETTE['RoofTile'] = ((0.30, 0.075, 0.045), 0.8, 0.0, 0, 1)

def render_side(lo, hi):
    """Orthographic side view from +X that fits both length and height, saved as render-side.png."""
    cam = scene.camera; cd = cam.data; cd.type = 'ORTHO'
    L, H = hi[1] - lo[1], hi[2] - lo[2]
    cd.ortho_scale = max(L / 0.92, H / 0.92 * 1672 / 941); cd.clip_end = 300
    cam.location = (hi[0] + 60, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2); cam.rotation_euler = (math.pi / 2, 0, math.pi / 2)
    sun = bpy.data.objects.get('Sun')
    if sun: sun.rotation_euler = (math.radians(50), 0, math.radians(75))
    scene.render.filepath = f'{OUT}/render-side.png'; bpy.ops.render.render(write_still=True)
# Single-storey roadside motel block (own design, blank sign, no text). About 24 m x 7 m, 3.5 m to the ridge.
# Six rooms along X with the office at the +X end; the covered walkway faces -Y. Built centred on the footprint.
NAME = 'Motel'
PALETTE['Cream'] = ((0.66, 0.53, 0.34), 0.9, 0.0, 0, 1)
PALETTE['DoorRed'] = ((0.36, 0.075, 0.05), 0.7, 0.0, 0, 1)
PALETTE['TrimGreen'] = ((0.15, 0.21, 0.13), 0.75, 0.0, 0, 1)
CR, DR, TG, SL, GB, GL, CO, TR = use('Cream', 'DoorRed', 'TrimGreen', 'Slate', 'GlassBldg', 'GlassClear', 'Concrete', 'Trim')
XL, XR, XO = -12.0, 12.0, 7.8           # ends of the block, start of the office
YF, YB, YW = -1.5, 3.5, -3.40           # room front wall, back wall, walkway post line / office front
ZF = 0.15                               # floor level on the slab
RW = (XO - XL) / 6                      # room width (3.3 m)
def u(y): return 3.40 - 0.16 * abs(y)   # underside of the roof

# ---------------------------------------------------------------- slab, walkway joints
box((XL - 0.25, YW - 0.35, 0.0), (XR + 0.25, YB + 0.15, ZF), CO, 0.02, 1)
for k in range(1, 7):
    x = XL + k * RW if k < 6 else XO
    box((x - 0.012, YW - 0.35, ZF - 0.005), (x + 0.012, YF, ZF + 0.004), SL, 0.0, 1)

# ---------------------------------------------------------------- walls with gable ends
prism([(YF, ZF), (YB, ZF), (YB, u(YB)), (0.0, u(0.0)), (YF, u(YF))], XL, XR, CR, 'X', 0.02, 1)
box((XL - 0.02, YF - 0.02, ZF), (XO, YF + 0.02, 0.55), DR, 0.0, 1)                      # low wainscot band
box((XL - 0.02, YF - 0.025, 0.55), (XO, YF + 0.02, 0.60), TR, 0.0, 1)

# ---------------------------------------------------------------- rooms: door, window, wall lamp, party-wall pilasters
for i in range(6):
    xc = XL + (i + 0.5) * RW
    xd, xw = xc - 0.75, xc + 0.65
    box((xd - 0.52, YF - 0.06, ZF), (xd + 0.52, YF + 0.01, 2.30), TR, 0.01, 1)          # door casing
    box((xd - 0.45, YF - 0.08, ZF + 0.02), (xd + 0.45, YF - 0.03, 2.22), DR, 0.01, 1)   # door leaf
    lathe([(0.0, 0.0), (0.04, 0.0), (0.045, 0.03), (0.0, 0.05)], 12, SL, at(xd + 0.33, YF - 0.08, 1.05) @ BACK)   # knob
    box((xd - 0.06, YF - 0.09, 1.60), (xd + 0.06, YF - 0.07, 1.64), SL, 0.0, 1)        # number plate (blank)
    box((xw - 0.70, YF - 0.06, 1.00), (xw + 0.70, YF + 0.01, 2.10), TR, 0.01, 1)          # window frame
    box((xw - 0.62, YF - 0.08, 1.08), (xw + 0.62, YF - 0.04, 2.02), GB, 0.0, 1)          # glass
    box((xw - 0.03, YF - 0.10, 1.08), (xw + 0.03, YF - 0.05, 2.02), TR, 0.0, 1)          # mullion
    box((xw - 0.62, YF - 0.10, 1.53), (xw + 0.62, YF - 0.05, 1.57), TR, 0.0, 1)          # transom
    box((xw - 0.80, YF - 0.16, 0.94), (xw + 0.80, YF + 0.01, 1.00), TR, 0.01, 1)          # sill
    box((xd - 0.15, YF - 0.12, 2.48), (xd + 0.15, YF, 2.62), TR, 0.02, 2)                 # wall lamp
    box((xd - 0.12, YF - 0.13, 2.50), (xd + 0.12, YF - 0.11, 2.60), CR, 0.0, 1)
    if i > 0:
        box((XL + i * RW - 0.08, YF - 0.06, ZF), (XL + i * RW + 0.08, YF + 0.01, u(YF)), TR, 0.01, 1)   # pilaster
# back wall: small bathroom windows
for i in range(6):
    xc = XL + (i + 0.5) * RW
    box((xc - 0.40, YB - 0.01, 1.70), (xc + 0.40, YB + 0.05, 2.25), TR, 0.01, 1)
    box((xc - 0.33, YB + 0.03, 1.76), (xc + 0.33, YB + 0.07, 2.19), GB, 0.0, 1)

# ---------------------------------------------------------------- office: projecting glazed front, interior
box((XO, YW, ZF), (XO + 0.15, YF, u(YW)), CR, 0.02, 1)                                   # side wall toward the rooms
box((XR - 0.15, YW, ZF), (XR, YF, 0.90), DR, 0.01, 1)                                     # end wall: wainscot
box((XR - 0.15, YW, 2.45), (XR, YF, u(YW) + 0.02), CR, 0.01, 1)                           # end wall: header
box((XR - 0.12, YW + 0.1, 0.90), (XR - 0.03, YF - 0.1, 2.45), GL, 0.0, 1)                # end wall glazing
box((XO + 0.15, YW, ZF), (XR - 0.15, YW + 0.15, 0.90), DR, 0.01, 1)                       # front wainscot
box((XO + 0.15, YW, 2.45), (XR - 0.15, YW + 0.15, u(YW) + 0.02), CR, 0.01, 1)             # front header
box((XO + 0.15, YW + 0.05, 0.90), (10.55, YW + 0.10, 2.45), GL, 0.0, 1)                  # shop window
box((10.75, YW + 0.03, ZF + 0.02), (11.65, YW + 0.08, 2.40), GL, 0.0, 1)                 # glass door
box((10.55, YW + 0.02, 0.90), (10.75, YW + 0.15, 2.45), TG, 0.0, 1)
for (a, b, p, q) in ((XO + 0.15, 10.55, 0.86, 0.94), (XO + 0.15, 10.55, 2.41, 2.49), (10.55, 11.85, 2.40, 2.49)):
    box((a, YW - 0.02, p), (b, YW + 0.12, q), TG, 0.0, 1)                                # frame rails
for x in (XO + 0.20, 9.20, 10.55, 10.70, 11.70, 11.85):
    box((x - 0.05, YW - 0.02, 0.86 if x < 10.6 else ZF), (x + 0.05, YW + 0.12, 2.49), TG, 0.0, 1)    # frame stiles
box((10.75, YW - 0.02, ZF), (11.65, YW + 0.10, ZF + 0.12), TG, 0.0, 1)
box((11.50, YW - 0.06, 0.95), (11.53, YW + 0.02, 1.40), TR, 0.0, 1)                     # door pull
for y in (YW + 0.1, YF - 0.1):
    box((XR - 0.15, y - 0.05, 0.86), (XR + 0.02, y + 0.05, 2.49), TG, 0.0, 1)
box((XR - 0.15, YW, 0.86), (XR + 0.02, YF, 0.94), TG, 0.0, 1); box((XR - 0.15, YW, 2.41), (XR + 0.02, YF, 2.49), TG, 0.0, 1)
box((XO + 0.15, YW + 0.15, ZF), (XR - 0.15, YF, ZF + 0.02), CO, 0.0, 1)                  # office floor
box((XO + 0.15, YW + 0.15, 2.55), (XR - 0.15, YF, 2.60), TR, 0.0, 1)                     # ceiling
box((8.5, -2.4, ZF), (10.2, -1.9, 1.05), TR, 0.02, 1)                                     # reception desk
box((8.45, -2.45, 1.05), (10.25, -1.85, 1.10), DR, 0.01, 1)
lathe([(0.0, 1.10), (0.08, 1.10), (0.03, 1.14), (0.02, 1.38), (0.14, 1.38), (0.10, 1.58), (0.0, 1.58)], 16, TR, at(9.9, -2.1, 0))   # desk lamp
box((8.9, -1.75, ZF), (9.4, -1.55, 0.95), SL, 0.02, 1)                                    # chair back

# ---------------------------------------------------------------- walkway posts, braces, beam
posts = [XL + 0.12] + [XL + k * RW for k in range(1, 6)] + [XO - 0.10]
for x in posts:
    box((x - 0.20, YW - 0.08, ZF), (x + 0.20, YW + 0.32, ZF + 0.20), CO, 0.02, 1)         # footing
    box((x - 0.08, YW + 0.04, ZF + 0.20), (x + 0.08, YW + 0.20, 2.68), TG, 0.01, 1)
    for s in (-1, 1):
        if (x < XL + 0.5 and s < 0) or (x > XO - 0.5 and s > 0): continue
        stroke([(x, 2.25), (x + s * 0.45, 2.68)], 0.07, YW + 0.06, YW + 0.18, TG, 'Y', 0.005, 1)   # brace
box((XL - 0.05, YW + 0.02, 2.66), (XO, YW + 0.22, u(YW + 0.12)), TG, 0.01, 1)            # beam
for x in posts[:-1]:
    box((x - 0.05, YW + 0.2, 2.70), (x + 0.05, YF, 2.80), TG, 0.0, 1)                     # rafter ties

# ---------------------------------------------------------------- roof: low-pitch gable over the walkway, fascia, barge boards
RY, RT = 3.80, 0.14
prism([(-RY, u(RY)), (0.0, u(0.0)), (RY, u(RY)), (RY, u(RY) + RT), (0.0, u(0.0) + RT), (-RY, u(RY) + RT)], XL - 0.25, XR + 0.25, SL, 'X', 0.02, 1)
for k in range(1, 24):
    x = XL - 0.25 + k * (XR - XL + 0.5) / 24
    for s in (-1, 1):
        stroke([(0.0, u(0.0) + RT), (s * RY, u(RY) + RT)], 0.03, x - 0.02, x + 0.02, SL, 'X', 0.0, 1)   # standing seams
for s in (-1, 1):
    box((XL - 0.28, s * RY - 0.04 if s > 0 else -RY - 0.06, u(RY) - 0.12), (XR + 0.28, s * RY + 0.06 if s > 0 else -RY + 0.04, u(RY) + RT + 0.02), TG, 0.01, 1)   # fascia
for xe in (XL - 0.26, XR + 0.26):
    stroke([(-RY - 0.05, u(RY) + RT + 0.01), (0.0, u(0.0) + RT + 0.01), (RY + 0.05, u(RY) + RT + 0.01)], 0.18, xe - 0.03, xe + 0.03, TG, 'X', 0.005, 1)   # barge boards

# ---------------------------------------------------------------- blank sign on the roof above the office
for x in (8.7, 11.1):
    box((x - 0.08, -0.08, u(0.0) - 0.1), (x + 0.08, 0.08, 3.95), TG, 0.01, 1)
prism(rrect(7.9, 3.85, 11.9, 4.65, 0.20), -0.12, 0.12, DR, 'Y', 0.02, 1)
prism(rrect(8.04, 3.97, 11.76, 4.53, 0.12), -0.15, 0.15, TR, 'Y', 0.01, 1)

# ---------------------------------------------------------------- export, render
lo, hi = finish(NAME)
render(lo, hi, az=-28, el=7, lens=50, fill=0.97, sun=(50, -25))
render_front(lo, hi)
compare()

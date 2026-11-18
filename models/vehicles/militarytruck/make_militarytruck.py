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
# Generic six-wheel army cargo truck (own design, plain olive, no markings). About 7.5 m long, 2.5 m wide, 3.0 m tall.
# Built with y = metres back from the front bumper, then centred on the footprint. Left side is +X (driver side).
NAME = 'MilitaryTruck'
PALETTE['Canvas'] = ((0.19, 0.18, 0.10), 0.95, 0.0, 0, 1)
OL, CV, BL, ST, GL, PL, LW, LR = use('Olive', 'Canvas', 'Black', 'Steel', 'GlassClear', 'Interior', 'LensWhite', 'LensRed')
R = 0.53                                    # tyre carcass radius (knobs add 0.035)
ZC = R + 0.035                              # axle height
YF, Y2, Y3 = 1.25, 5.45, 6.75               # axles
XW = 1.04                                   # wheel centre offset

def tyre(M, T, RIM, hub, w=0.42, n=28, knobs=20):
    """Off-road tyre with staggered tread blocks and a painted rim; local +Z is the outer face."""
    rimr = R * 0.58; h = w / 2
    prof = [(0.0, -h + 0.03, T), (rimr * 0.9, -h + 0.03, T), (R - 0.06, -h, T), (R - 0.01, -h + 0.04, T), (R, -h + 0.08, T),
            (R, h - 0.08, T), (R - 0.01, h - 0.04, T), (R - 0.06, h, T), (rimr + 0.02, h - 0.005, T),
            (rimr, h - 0.02, RIM), (rimr * 0.93, h - 0.06, RIM), (rimr * 0.42, h - 0.08, RIM), (rimr * 0.34, h - 0.03, hub), (0.0, h - 0.02)]
    lathe(prof, n, T, M)
    for k in range(8):
        a = 2 * math.pi * k / 8; rr = rimr * 0.62
        cyl(0.022, h - 0.085, h - 0.05, hub, 8, M @ at(rr * math.cos(a), rr * math.sin(a), 0))
    for k in range(knobs):
        a = 360 * k / knobs
        box((R - 0.02, -0.05, 0.015), (R + 0.035, 0.05, h - 0.03), T, 0.0, 1, M=M @ rotz(a))
        box((R - 0.02, -0.05, -h + 0.03), (R + 0.035, 0.05, -0.015), T, 0.0, 1, M=M @ rotz(a + 180 / knobs))

def side(s, xo, lo, hi, mi, bev=0.01, d=0.03):
    """Box standing proud of the side face at x = s * xo; lo/hi are (y, z)."""
    x0, x1 = (xo - 0.005, xo + d) if s > 0 else (-xo - d, -xo + 0.005)
    box((x0, lo[0], lo[1]), (x1, hi[0], hi[1]), mi, bev, 1)

# ---------------------------------------------------------------- chassis, axles, wheels
for s in (-1, 1):
    box((s * 0.45 - 0.05, 0.30, 0.78), (s * 0.45 + 0.05, 7.45, 1.02), BL, 0.01, 1)          # frame rails
for y in (0.5, 2.0, 3.5, 5.0, 6.1, 7.3):
    box((-0.42, y - 0.05, 0.82), (0.42, y + 0.05, 0.98), BL, 0.0, 1)                       # cross members
for y in (YF, Y2, Y3):
    cyl(0.07, -0.85, 0.85, BL, 12, at(0, y, ZC) @ roty(90))                                # axle
    lathe([(0.0, -0.22), (0.14, -0.22), (0.20, -0.08), (0.20, 0.08), (0.14, 0.22), (0.0, 0.22)], 14, BL, at(0, y, ZC) @ roty(90))   # diff
    for s in (-1, 1):
        tyre(at(s * XW, y, ZC) @ roty(90 * s), BL, OL, ST)
cyl(0.05, 0.0, 1.3, BL, 10, at(0, 5.45, ZC + 0.12) @ ALONG)                               # walking beam between the rear axles
for s in (-1, 1):
    box((s * 0.75 - 0.08, Y2 + 0.1, ZC + 0.05), (s * 0.75 + 0.08, Y3 - 0.1, ZC + 0.20), BL, 0.02, 1)   # leaf spring bogie
    box((s * 0.75 - 0.06, YF - 0.6, ZC + 0.08), (s * 0.75 + 0.06, YF + 0.6, ZC + 0.18), BL, 0.02, 1)   # front spring

# ---------------------------------------------------------------- bumper, tow hooks, hood, grille, lamps, fenders
box((-1.20, 0.0, 0.62), (1.20, 0.24, 0.90), OL, 0.04, 2)                                    # front bumper
for s in (-1, 1):
    box((s * 0.45 - 0.07, 0.20, 0.66), (s * 0.45 + 0.07, 0.45, 0.86), BL, 0.0, 1)         # bumper brackets
    tube([(s * 0.62 - 0.09, 0.02, 0.84), (s * 0.62 - 0.09, -0.14, 0.84), (s * 0.62 - 0.09, -0.14, 0.62), (s * 0.62 - 0.09, 0.02, 0.62)], 0.026, ST, 10, 0.06, 4)
    tube([(s * 0.62 + 0.09, 0.02, 0.84), (s * 0.62 + 0.09, -0.14, 0.84), (s * 0.62 + 0.09, -0.14, 0.62), (s * 0.62 + 0.09, 0.02, 0.62)], 0.026, ST, 10, 0.06, 4)
    box((s * 0.62 - 0.11, -0.16, 0.70), (s * 0.62 + 0.11, -0.12, 0.76), ST, 0.01, 1)     # hook pin
    box((s * 1.05 - 0.07, -0.02, 0.70), (s * 1.05 + 0.07, 0.02, 0.80), BL, 0.0, 1)       # bumper bolt plates
# hood
box((-0.80, 0.24, 0.98), (0.80, 1.98, 1.88), OL, 0.06, 2)
box((-0.012, 0.30, 1.80), (0.012, 1.96, 1.91), BL, 0.0, 1)                                  # hood centre seam
for s in (-1, 1):
    for k in range(5):
        y = 0.95 + k * 0.16; side(s, 0.80, (y, 1.48), (y + 0.10, 1.74), BL, 0.0, 0.012)      # side louvres
    for y in (0.55, 1.65): side(s, 0.80, (y, 1.80), (y + 0.10, 1.84), ST, 0.008, 0.03)       # hood latches
box((-0.62, 0.20, 1.06), (0.62, 0.27, 1.72), BL, 0.0, 1)                                   # grille backing
for k in range(11):
    x = -0.56 + k * 0.112; box((x - 0.025, 0.17, 1.08), (x + 0.025, 0.24, 1.70), OL, 0.008, 1)    # grille bars
box((-0.66, 0.17, 1.70), (0.66, 0.26, 1.78), OL, 0.015, 1); box((-0.66, 0.17, 1.00), (0.66, 0.26, 1.08), OL, 0.015, 1)
for s in (-1, 1):
    # enclosed fender: sloped nose, flat top, back to the cab
    prism(side_poly([(0.30, 0.92), (0.30, 1.24), (0.44, 1.37), (2.00, 1.37), (2.00, 0.92)], 0.92, [(YF, ZC, 0.68)]), s * 0.80, s * 1.24, OL, 'X', 0.03, 2)
    # round headlight in the fender nose
    lathe([(0.0, 0.0), (0.15, 0.0), (0.15, 0.06), (0.13, 0.08), (0.0, 0.08)], 24, BL, at(s * 1.02, 0.31, 1.10) @ BACK)
    lathe([(0.0, 0.0), (0.12, 0.0), (0.12, 0.09), (0.0, 0.10)], 24, LW, at(s * 1.02, 0.31, 1.10) @ BACK)
    box((s * 1.02 - 0.07, 0.40, 1.37), (s * 1.02 + 0.07, 0.48, 1.42), LR, 0.008, 1)      # small marker lamp on the fender
    # cab steps under the doors
    for z in (0.50, 0.74):
        box((min(s * 0.98, s * 1.22), 2.15, z), (max(s * 0.98, s * 1.22), 2.70, z + 0.05), ST, 0.01, 1)
    box((min(s * 1.18, s * 1.22), 2.13, 0.60), (max(s * 1.18, s * 1.22), 2.17, 0.96), BL, 0.0, 1)
    box((min(s * 1.18, s * 1.22), 2.68, 0.60), (max(s * 1.18, s * 1.22), 2.72, 0.96), BL, 0.0, 1)

recolour_arch(YF, ZC, 0.68, 0.92, BL, 1.25)

# ---------------------------------------------------------------- cab: lower shell, pillars, glass, roof, interior
CY0, CY1 = 1.96, 3.15
box((-1.15, CY0, 0.95), (1.15, CY1, 2.08), OL, 0.04, 2)
box((-1.17, CY0 - 0.02, 2.62), (1.17, CY1 + 0.02, 2.78), OL, 0.05, 2)                     # roof
box((-1.15, CY1 - 0.08, 2.05), (1.15, CY1, 2.64), OL, 0.01, 1)                            # back wall
for s in (-1, 1):
    box((min(s * 1.06, s * 1.15), CY0, 2.05), (max(s * 1.06, s * 1.15), CY0 + 0.09, 2.64), OL, 0.01, 1)     # A pillar
    box((min(s * 1.06, s * 1.15), CY1 - 0.16, 2.05), (max(s * 1.06, s * 1.15), CY1, 2.64), OL, 0.01, 1)     # C pillar
    box((s * 0.53 - 0.48, CY0 + 0.01, 2.10), (s * 0.53 + 0.48, CY0 + 0.04, 2.58), GL, 0.0, 1)                 # windshield pane
    for (a, b, u, v) in ((0.03, 1.07, 2.05, 2.10), (0.03, 1.07, 2.58, 2.64)):
        box((min(s * a, s * b), CY0 - 0.01, u), (max(s * a, s * b), CY0 + 0.05, v), OL, 0.008, 1)               # frame
    box((min(s * 1.12, s * 1.16), CY0 + 0.10, 2.10), (max(s * 1.12, s * 1.16), CY1 - 0.17, 2.58), GL, 0.0, 1)   # door glass
    for (p, q, u, v) in ((CY0 + 0.08, CY1 - 0.15, 2.05, 2.10), (CY0 + 0.08, CY1 - 0.15, 2.58, 2.64)):
        box((min(s * 1.11, s * 1.165), p, u), (max(s * 1.11, s * 1.165), q, v), OL, 0.008, 1)
    for y in (CY0 + 0.05, CY1 - 0.12):
        side(s, 1.15, (y - 0.012, 1.24), (y + 0.012, 2.08), BL, 0.0, 0.012)               # door seams
    side(s, 1.15, (CY0 + 0.05, 1.24), (CY1 - 0.12, 1.26), BL, 0.0, 0.012)
    side(s, 1.15, (CY1 - 0.38, 1.88), (CY1 - 0.22, 1.93), ST, 0.008, 0.04)                 # handle
    for y in (CY0 + 0.15, CY0 + 0.70):
        side(s, 1.15, (y, 1.40), (y + 0.06, 1.62), BL, 0.008, 0.03)                         # hinges
    # mirror on an arm
    tube([(s * 1.14, CY0 + 0.06, 2.45), (s * 1.38, CY0 + 0.06, 2.45), (s * 1.38, CY0 + 0.06, 2.00), (s * 1.14, CY0 + 0.06, 2.00)], 0.016, BL, 8, 0.05, 3)
    box((s * 1.38 - 0.05, CY0 - 0.02, 2.06), (s * 1.38 + 0.05, CY0 + 0.12, 2.40), BL, 0.03, 2)
    tube([(s * 0.12, CY0 - 0.02, 2.62), (s * 0.70, CY0 - 0.04, 2.58)], 0.012, BL, 6)        # wipers, parked high
for k in range(3):
    x = -0.30 + k * 0.30; box((x - 0.06, CY0 - 0.04, 2.70), (x + 0.06, CY0 + 0.02, 2.75), LR, 0.008, 1)   # roof marker lamps
box((-1.08, CY0 + 0.05, 1.50), (1.08, CY0 + 0.40, 2.08), PL, 0.04, 2)                         # dash
lathe([(0.20, 0.0), (0.20, 0.035), (0.17, 0.035), (0.17, 0.0)], 20, BL, at(0.55, CY0 + 0.52, 2.10) @ rotx(-55))
cyl(0.025, 0.0, 0.30, BL, 8, at(0.55, CY0 + 0.40, 1.90) @ rotx(-55))
for x in (0.55, -0.55):
    box((x - 0.26, 2.45, 1.40), (x + 0.26, 2.85, 1.55), PL, 0.05, 2)                         # seat cushions
    box((x - 0.26, 2.85, 1.55), (x + 0.26, 2.97, 2.25), PL, 0.05, 2)                         # backs

# ---------------------------------------------------------------- spare wheel, fuel tank, exhaust
tyre(at(0.62, 3.80, 1.78) @ roty(90), BL, OL, ST)                                          # spare, upright between cab and bed
box((0.18, 3.62, 1.00), (0.40, 3.98, 2.30), BL, 0.01, 1)                                    # spare carrier
box((0.18, 3.70, 1.70), (0.45, 3.90, 1.86), ST, 0.01, 1)
lathe([(0.0, 0.0), (0.24, 0.0), (0.28, 0.04), (0.28, 1.06), (0.24, 1.10), (0.0, 1.10)], 24, OL, at(-0.84, 3.60, 0.86) @ ALONG)
for y in (3.80, 4.50):
    lathe([(0.285, -0.025), (0.30, -0.015), (0.30, 0.015), (0.285, 0.025)], 24, BL, at(-0.84, y, 0.86) @ ALONG, cap_top=False, cap_bot=False)
cyl(0.06, 0.0, 0.06, ST, 16, at(-0.84, 4.15, 1.14))                                         # filler cap
box((-0.62, 3.70, 0.70), (-0.50, 4.60, 0.84), BL, 0.0, 1)                                   # tank bracket
tube([(-0.40, 1.20, 0.90), (-0.40, 3.30, 0.90), (-0.92, 3.33, 0.90), (-0.92, 3.33, 3.05)], 0.055, BL, 12, 0.18, 4)   # exhaust
lathe([(0.08, 1.75), (0.08, 2.75)], 16, ST, at(-0.92, 3.33, 0), cap_top=False, cap_bot=False)                         # heat shield
box((-0.70, 3.24, 2.20), (-0.86, 3.30, 2.30), BL, 0.0, 1)

# ---------------------------------------------------------------- cargo bed: floor, drop sides, tailgate, mudguards
BY0, BY1 = 4.42, 7.45
box((-1.24, BY0, 1.28), (1.24, BY1, 1.43), OL, 0.02, 1)                                     # floor
for s in (-1, 1):
    box((min(s * 1.17, s * 1.25), BY0, 1.43), (max(s * 1.17, s * 1.25), BY1, 1.98), OL, 0.02, 1)   # drop side
    for z in (1.56, 1.72, 1.88):
        side(s, 1.25, (BY0 + 0.05, z), (BY1 - 0.05, z + 0.03), OL, 0.008, 0.025)             # ribs
    for y in (4.48, 5.20, 5.95, 6.70, 7.38):
        side(s, 1.25, (y - 0.03, 1.30), (y + 0.03, 1.98), OL, 0.008, 0.035)                  # stakes
    for y in (4.84, 5.58, 6.33, 7.04):
        side(s, 1.25, (y - 0.04, 1.36), (y + 0.04, 1.40), ST, 0.006, 0.05)                   # rope hooks
    box((min(s * 0.80, s * 1.27), 4.85, 1.20), (max(s * 0.80, s * 1.27), 7.32, 1.26), BL, 0.01, 1)   # tandem mudguard
    box((min(s * 0.80, s * 1.26), 7.32, 0.42), (max(s * 0.80, s * 1.26), 7.36, 1.22), BL, 0.0, 1)    # mud flap
box((-1.24, BY0, 1.43), (1.24, BY0 + 0.08, 1.98), OL, 0.02, 1)                              # bed front wall
box((-1.17, BY1 - 0.08, 1.43), (1.17, BY1, 1.98), OL, 0.02, 1)                              # tailgate
for z in (1.56, 1.72, 1.88):
    box((-1.12, BY1, z), (1.12, BY1 + 0.025, z + 0.03), OL, 0.008, 1)
for x in (-0.80, 0.80):
    box((x - 0.06, BY1, 1.80), (x + 0.06, BY1 + 0.05, 1.86), ST, 0.008, 1)                 # tailgate latches

# ---------------------------------------------------------------- canvas cover on bows
CT, CR, CW = 3.00, 0.34, 1.20
def cover(w, top, r, z0=1.94, n=8):
    pts = [(-w, z0), (w, z0)]
    for cx, a0 in ((w - r, 0), (-w + r, 90)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n); pts.append((cx + r * math.cos(a), top - r + r * math.sin(a)))
    return pts
prism(cover(CW, CT, CR), BY0 + 0.04, BY1 - 0.02, CV, 'Y', 0.03, 2)
for y in (BY0 + 0.10, 5.17, 5.93, 6.69, BY1 - 0.08):
    prism(cover(CW + 0.022, CT + 0.022, CR + 0.022), y - 0.035, y + 0.035, CV, 'Y', 0.012, 1)          # bows under the canvas
for s in (-1, 1):
    for y in (4.84, 5.55, 6.31, 7.07):
        tube([(s * 1.205, y, 2.05), (s * 1.24, y, 1.98), (s * 1.27, y, 1.40)], 0.010, BL, 6, 0.04, 2)  # tie-down ropes
box((-1.21, BY1 - 0.04, 2.00), (1.21, BY1 + 0.01, 2.06), BL, 0.0, 1)                         # rear flap hem
box((-0.012, BY1 - 0.03, 2.06), (0.012, BY1 + 0.005, 2.95), BL, 0.0, 1)                       # rear flap split
lathe([(0.075, -1.0), (0.075, 1.0)], 16, CV, at(0, BY1 - 0.02, 2.80) @ roty(90))               # rolled flap

# ---------------------------------------------------------------- rear: bumper, lamps, pintle hook
box((-1.10, BY1 - 0.05, 0.78), (1.10, BY1 + 0.12, 0.95), OL, 0.03, 2)
for s in (-1, 1):
    box((s * 0.92 - 0.12, BY1 + 0.10, 0.80), (s * 0.92 + 0.12, BY1 + 0.14, 0.93), LR, 0.01, 1)
    box((s * 0.45 - 0.06, BY1 - 0.10, 0.95), (s * 0.45 + 0.06, BY1 + 0.06, 1.28), BL, 0.0, 1)
box((-0.14, BY1 + 0.10, 0.76), (0.14, BY1 + 0.16, 0.97), ST, 0.01, 1)
tube([(0.0, BY1 + 0.16, 0.86), (0.0, BY1 + 0.28, 0.86), (0.0, BY1 + 0.28, 0.76)], 0.03, ST, 10, 0.05, 3)

# ---------------------------------------------------------------- centre on the footprint, export, render
cx, cy = centre_xy()
lo, hi = finish(NAME, seat=(0.55 - cx, 2.65 - cy, 1.55))
render(lo, hi, az=40, el=12, lens=40, fill=0.95, side='+X', sun=(50, 25))
compare()

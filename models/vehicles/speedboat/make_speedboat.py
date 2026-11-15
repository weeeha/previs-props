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
# Generic open motorboat (own design, no markings). About 6 m long with the outboard, 2.2 m beam.
# Built with y = metres back from the bow, keel on the ground. Left side is +X; the helm is on the right (-X).
NAME = 'Speedboat'
CR, BU, BL, GR, GL, PG, ST = use('PaintCream', 'BoatBlue', 'Black', 'Graphite', 'GlassClear', 'PlasticGrey', 'Steel')
LH = 5.60                                   # hull length, bow to transom
ZF = 0.40                                   # cockpit floor
YC = 1.85                                   # foredeck ends, cockpit starts

def beam(y):
    if y < 2.6: t = y / 2.6; return 0.03 + 1.07 * (1 - (1 - t) ** 2) ** 0.85
    return 1.10 - 0.06 * (y - 2.6) / (LH - 2.6)
def keel(y): return 0.0 if y > 2.4 else 0.92 * ((2.4 - y) / 2.4) ** 1.6
def sheer(y): return 0.92 + 0.30 * max(0.0, (2.6 - y) / 2.6) ** 1.6

def half(y, deck):
    b, zk, zs = beam(y), keel(y), sheer(y)
    zc = zk + 0.26 * b / 1.1 + 0.02
    zb0 = zc + 0.08 + 0.12 * (zs - zc - 0.1) / 0.9                     # blue band from here
    H = [((0.0, zk), CR), ((0.45 * b, zk + 0.10 * b), CR), ((0.88 * b, zc), CR), ((0.91 * b, zc + 0.03), CR),
         ((0.95 * b, zb0), BU), ((0.99 * b, zs - 0.13), CR), ((b, zs), CR), ((max(0.0, b - 0.11), zs + 0.012), CR)]
    if deck:
        H += [((0.62 * b, zs + 0.05), CR), ((0.30 * b, zs + 0.085), CR), ((0.0, zs + 0.095), CR)]
    else:
        H += [((b - 0.13, ZF + 0.10), PG), ((b - 0.22, ZF), PG), ((0.0, ZF), PG)]
    return H

def hull(ys, deck, cap0, cap1):
    bm = bmesh.new(); rings = []; mats = None
    for y in ys:
        H = half(y, deck); pts = [p for p, m in H]; mats = [m for p, m in H]
        ring = pts + [(-x, z) for x, z in pts[-2:0:-1]]
        rings.append([bm.verts.new((x, y, z)) for x, z in ring])
    n = len(rings[0]); nh = len(mats)
    def segmat(k):
        i = k if k < nh - 1 else (n - 1 - k)                                   # mirror side
        return mats[i] if k < nh - 1 else mats[i - 1] if i - 1 >= 0 else mats[0]
    for i in range(len(rings) - 1):
        for k in range(n):
            k2 = (k + 1) % n
            try:
                f = bm.faces.new([rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]]); f.material_index = segmat(k)
            except ValueError: pass
    if cap0: f = bm.faces.new(rings[0][::-1]); f.material_index = CR
    if cap1: f = bm.faces.new(rings[-1]); f.material_index = CR
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5); bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    add(bm)

hull([0.0, 0.03, 0.08, 0.16, 0.28, 0.45, 0.65, 0.90, 1.15, 1.40, 1.65, YC], True, False, True)
hull([YC] + [round(YC + 0.25 * k, 3) for k in range(1, 15)] + [LH], False, True, True)

# rub rail along the sheer and around the stem
rail = [(beam(y) + 0.015, y, sheer(y) - 0.03) for y in [LH - 0.02, 5.0, 4.0, 3.0, 2.4, 1.8, 1.2, 0.8, 0.5, 0.25, 0.10]]
tube(rail + [(0.0, -0.03, sheer(0.0) - 0.03)] + [(-x, y, z) for x, y, z in rail[::-1]], 0.035, BL, 8, 0.15, 3)
# transom trim and swim platforms
box((-1.02, LH - 0.02, 0.62), (1.02, LH + 0.03, 0.68), BL, 0.01, 1)
for s in (-1, 1):
    box((s * 0.75 - 0.25, LH, 0.40), (s * 0.75 + 0.25, LH + 0.30, 0.46), PG, 0.02, 1)

# ---------------------------------------------------------------- foredeck fittings: cleats and bow light
for s in (-1, 1):
    y = 0.75; x = s * beam(y) * 0.70
    box((x - 0.012, y - 0.015, sheer(y) + 0.05), (x + 0.012, y + 0.015, sheer(y) + 0.10), ST, 0.004, 1)
    box((x - 0.016, y - 0.09, sheer(y) + 0.10), (x + 0.016, y + 0.09, sheer(y) + 0.125), ST, 0.008, 1)
cyl(0.025, sheer(0.1) + 0.06, sheer(0.1) + 0.20, ST, 10, at(0, 0.12, 0))
lathe([(0.0, 0.0), (0.04, 0.0), (0.04, 0.03), (0.0, 0.05)], 12, GL, at(0, 0.12, sheer(0.1) + 0.20))

# ---------------------------------------------------------------- wraparound windshield on a low dash
ZD = sheer(YC) + 0.08
box((-0.84, YC, ZF), (0.84, YC + 0.35, ZD - 0.02), CR, 0.03, 2)                     # dash / front wall
WB, WT = (YC + 0.05, ZD), (YC + 0.38, ZD + 0.45)
def slab(c, mi, t=0.012):
    """Thin panel between four corners (quad), extruded along its normal by t."""
    a, b, cc, d = [Vector(p) for p in c]; nrm = (b - a).cross(d - a).normalized() * t
    bm = bmesh.new(); vs = [bm.verts.new(p) for p in (a, b, cc, d)] + [bm.verts.new(p + nrm) for p in (a, b, cc, d)]
    for f in ((0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)): bm.faces.new([vs[i] for i in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces); add(bm, None, mi)
XC = 0.50
C0 = [(-XC, WB[0], WB[1]), (XC, WB[0], WB[1]), (XC * 0.92, WT[0], WT[1]), (-XC * 0.92, WT[0], WT[1])]
slab(C0, GL)
corners = {}
for s in (-1, 1):
    bx, by = beam(YC + 0.45) - 0.10, YC + 0.45
    S0 = [(s * XC, WB[0], WB[1]), (s * bx, by, ZD - 0.01), (s * (bx - 0.06), by + 0.20, ZD + 0.36), (s * XC * 0.92, WT[0], WT[1])]
    slab(S0 if s < 0 else S0[::-1], GL)
    corners[s] = S0
    tube([S0[0], S0[3]], 0.02, BL, 8)                                                       # corner posts
    tube([S0[3], S0[2], S0[1]], 0.02, BL, 8, 0.05, 2)                                       # side frame
tube([C0[3], C0[2]], 0.02, BL, 8)                                                           # top frame
tube([C0[0], C0[1]], 0.02, BL, 8)
for s in (-1, 1): tube([corners[s][0], corners[s][1]], 0.02, BL, 8)

# ---------------------------------------------------------------- helm console, wheel, throttle
box((-0.84, YC + 0.30, ZF), (-0.30, YC + 0.75, ZD + 0.08), CR, 0.04, 2)
prism([(YC + 0.30, ZD + 0.08), (YC + 0.62, ZD + 0.12), (YC + 0.62, ZD + 0.02)], -0.92, -0.33, PG, 'X', 0.01, 1)   # dash pod
lathe([(0.0, 0.0), (0.05, 0.0), (0.05, 0.06), (0.0, 0.06)], 12, BL, at(-0.62, YC + 0.70, ZD - 0.05) @ rotx(-60))
WC = at(-0.62, YC + 0.78, ZD + 0.05) @ rotx(-60)
lathe([(0.17, -0.02), (0.19, 0.0), (0.17, 0.02), (0.15, 0.0)], 24, BL, WC, cap_top=False, cap_bot=False)   # wheel rim
for k in range(3):
    box((-0.008, 0.0, -0.01), (0.008, 0.16, 0.01), BL, 0.0, 1, WC @ rotz(120 * k + 90))
cyl(0.03, -0.02, 0.03, BL, 12, WC)
box((-0.98, YC + 0.70, ZD - 0.05), (-0.94, YC + 0.78, ZD + 0.18), BL, 0.01, 1)                 # throttle lever
box((0.30, YC + 0.30, ZF), (0.84, YC + 0.75, ZD - 0.05), CR, 0.04, 2)                        # passenger console
box((0.35, YC + 0.70, ZD - 0.15), (0.90, YC + 0.76, ZD - 0.10), PG, 0.01, 1)                 # grab rail

# ---------------------------------------------------------------- seats: two buckets and a rear bench
def bucket(x, y):
    box((x - 0.06, y - 0.06, ZF), (x + 0.06, y + 0.06, ZF + 0.32), PG, 0.01, 1)                    # pedestal
    box((x - 0.26, y - 0.26, ZF + 0.32), (x + 0.26, y + 0.24, ZF + 0.46), CR, 0.05, 2)            # cushion
    box((x - 0.17, y - 0.24, ZF + 0.46), (x + 0.17, y + 0.12, ZF + 0.47), BU, 0.0, 1)
    hexa({(sx, sy, sz): (x + sx * (0.26 if sz < 0 else 0.23), y + 0.18 + 0.05 * sy + (0.10 if sz > 0 else 0), ZF + 0.42 if sz < 0 else ZF + 1.02)
          for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)}, CR, 0.05, 2)                     # backrest
    hexa({(sx, sy, sz): (x + sx * 0.15, y + 0.12 + 0.01 * sy + (0.09 if sz > 0 else 0), ZF + 0.52 if sz < 0 else ZF + 0.90)
          for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)}, BU, 0.02, 1)
bucket(-0.55, 3.05); bucket(0.55, 3.05)
box((-0.86, 4.65, ZF), (0.86, 5.30, ZF + 0.42), CR, 0.04, 2)                                    # bench base
for k in range(3):
    x = -0.61 + k * 0.61
    box((x - 0.30, 4.62, ZF + 0.42), (x + 0.30, 5.20, ZF + 0.56), BU if k == 1 else CR, 0.05, 2)
    box((x - 0.30, 5.18, ZF + 0.42), (x + 0.30, 5.40, ZF + 0.88), CR, 0.05, 2)
box((-0.90, 5.38, ZF), (0.90, LH - 0.02, sheer(LH) + 0.02), CR, 0.03, 2)                           # engine well wall

# ---------------------------------------------------------------- outboard motor on the transom
MY = LH + 0.03
box((-0.12, MY, 0.68), (0.12, MY + 0.12, 1.00), GR, 0.02, 1)                                 # clamp bracket
lathe([(0.0, 0.0), (0.26, 0.0), (0.30, 0.10), (0.30, 0.42), (0.24, 0.55), (0.0, 0.58)], 8, GR,
      at(0, MY + 0.32, 0.94) @ Matrix.Diagonal((0.85, 1.15, 1.0, 1.0)) @ rotz(22.5))               # cowling
box((-0.27, MY + 0.10, 1.08), (0.27, MY + 0.55, 1.11), BL, 0.0, 1)                           # cowling split line
box((-0.10, MY + 0.15, 0.30), (0.10, MY + 0.40, 0.96), GR, 0.04, 2)                           # mid section
box((-0.07, MY + 0.15, 0.12), (0.07, MY + 0.38, 0.32), GR, 0.03, 2)                           # lower unit
box((-0.20, MY + 0.08, 0.30), (0.20, MY + 0.48, 0.33), GR, 0.01, 1)                           # cavitation plate
box((-0.025, MY + 0.22, 0.02), (0.025, MY + 0.38, 0.12), GR, 0.01, 1)                         # skeg
lathe([(0.0, -0.10), (0.06, -0.08), (0.06, 0.10), (0.0, 0.14)], 12, GR, at(0, MY + 0.40, 0.20) @ rotx(-90))   # gear case
for k in range(3):
    box((-0.035, -0.012, 0.03), (0.035, 0.012, 0.16), ST, 0.008, 1, at(0, MY + 0.52, 0.20) @ roty(120 * k + 30))

# ---------------------------------------------------------------- centre on the footprint, export, render
cx, cy = centre_xy()
lo, hi = finish(NAME, seat=(-0.55 - cx, 3.05 - cy, ZF + 0.46))
render(lo, hi, az=40, el=16, lens=55, fill=0.95, side='+X', sun=(50, 25))
compare()

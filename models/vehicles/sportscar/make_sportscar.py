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
# Generic low two-door sports coupe (own design, not based on any real make). About 4.4 m long, 1.9 m wide, 1.25 m tall.
# Built with y = metres back from the nose, then centred on the footprint. Left side is +X (driver side).
# The body is a loft of cross-sections (raised fenders, lower hood centre, waist crease); the wheel arches are
# pressed into it afterwards and edged with a flared lip.
NAME = 'SportsCar'
RD, BL, GL, IN, GR, LW, LR = use('Red', 'Black', 'GlassClear', 'Interior', 'Graphite', 'LensWhite', 'LensRed')
R, TW = 0.35, 0.30                     # wheel radius, tyre width
YF, YR = 1.02, 3.58                    # axles
XT = 0.79                              # wheel centre track (half)
RA = 0.38                             # wheel arch radius
ZB = 0.20                              # body underside
LB = 4.40                              # body length

def lerp(pts, y):
    if y <= pts[0][0]: return pts[0][1]
    for (a, va), (b, vb) in zip(pts, pts[1:]):
        if a <= y <= b: t = (y - a) / (b - a); t = t * t * (3 - 2 * t); return va + (vb - va) * t
    return pts[-1][1]
def bump(y, c, s): return math.exp(-((y - c) / s) ** 2)
TOP = [(0.0, 0.57), (0.14, 0.64), (0.45, 0.70), (1.0, 0.745), (1.70, 0.795), (2.6, 0.815), (3.4, 0.85), (3.95, 0.88), (4.30, 0.87), (4.40, 0.80)]
WID = [(0.0, 0.84), (0.10, 0.88), (0.35, 0.91), (1.0, 0.925), (1.7, 0.905), (2.4, 0.895), (3.1, 0.915), (3.6, 0.93), (4.1, 0.915), (4.40, 0.86)]
def ztop(y): return lerp(TOP, y)
def wid(y): return lerp(WID, y) + 0.022 * bump(y, YF, 0.45) + 0.025 * bump(y, YR, 0.50)
def zfender(y): return ztop(y) + 0.06 * bump(y, YF, 0.50) + 0.035 * bump(y, YR, 0.55) + 0.012
def zhood(y): return ztop(y) - 0.035 * max(0.0, min(1.0, (1.80 - y) / 0.4))
FR = [0.12, 0.24, 0.33, 0.42, 0.53, 0.66, 0.74, 0.90]    # side points as fractions from underside to the shoulder
def section(y):
    w, zt, zf, zc = wid(y), ztop(y), zfender(y), zhood(y)
    zs = lambda f: ZB + (zf - ZB) * f
    return [(0.0, ZB), (w - 0.13, ZB), (w - 0.035, ZB + 0.055), (w - 0.012, zs(FR[0])), (w, zs(FR[1])), (w + 0.003, zs(FR[2])),
            (w + 0.006, zs(FR[3])), (w + 0.010, zs(FR[4])), (w + 0.014, zs(FR[5])), (w - 0.004, zs(FR[6])), (w - 0.045, zs(FR[7])), (w - 0.13, zf),
            (0.62 * w, zf - 0.006), (0.44 * w, (zf + zc) / 2), (0.24 * w, zc), (0.0, zc + 0.004)]
def side_x(y, z):
    """Outer surface x of the body side at height z (between the sill and the shoulder)."""
    P = section(y)[2:11]
    for (x0, z0), (x1, z1) in zip(P, P[1:]):
        if z0 <= z <= z1: return x0 + (x1 - x0) * (z - z0) / (z1 - z0)
    return P[-1][0]

# ---------------------------------------------------------------- body loft
# Everything on the flank is part of the loft itself: the wheel arches are cut into the sections (outer edge
# snapped onto the arch circle, a flared lip, a black well wall set in), the door seams are V grooves made of
# three close stations, and the side intake is an inset of the loft's own faces.
SEAMS = (1.70, 2.93)                    # door shut lines (vertical, constant y)
SG = 0.008                              # half width of a seam groove
VENT = (3.01, 3.14, 0.40, 0.55)         # side intake ahead of the rear wheel: y0, y1, z0, z1
SIDE = range(2, 11)                     # section indices on the flank (sill to shoulder)

def arch_h(y):
    """Arch opening top at y (None outside the opening): semicircle above the axle, straight down below it."""
    for yc in (YF, YR):
        dy = abs(y - yc)
        if dy < RA: return R + math.sqrt(RA * RA - dy * dy)
    return None
def surf_x(sec, z):
    P = sec[2:11]
    for (x0, z0), (x1, z1) in zip(P, P[1:]):
        if z0 <= z <= z1: return x0 + (x1 - x0) * (z - z0) / (z1 - z0)
    return P[0][0] if z < P[0][1] else P[-1][0]

ys = {0.0, 0.025, 0.06, 0.11, 0.18, 0.26}
y = 0.35
while y < 4.26:
    near = min(abs(y - YF), abs(y - YR)) < 0.50
    ys.add(round(y, 3)); y += 0.025 if near else 0.10
for yc in (YF, YR):
    for d in (-RA - 0.003, -RA + 0.003, RA - 0.003, RA + 0.003): ys.add(round(yc + d, 4))
for sy in SEAMS:
    ys -= {v for v in ys if abs(v - sy) < 0.03}
    ys |= {sy - 0.05, sy - SG, sy, sy + SG, sy + 0.05}
ys -= {v for v in ys if VENT[0] - 0.02 < v < VENT[1] + 0.02}
ys |= {VENT[0] - 0.012, VENT[0], VENT[0] + 0.033, VENT[0] + 0.065, VENT[0] + 0.098, VENT[1], VENT[1] + 0.012}
ys |= {4.30, 4.35, 4.38, LB}
ys = sorted(ys)

bm = bmesh.new(); rings = []; flags = []
for i, y in enumerate(ys):
    sec = section(y)
    k = 0.90 if i == 0 or y == LB else (0.97 if i == 1 or y == 4.38 else 1.0)       # rounded nose and tail edges
    dz = -0.035 if i == 0 or y == LB else (-0.012 if i == 1 or y == 4.38 else 0.0)
    pts = [[x * k, z + (dz if z > 0.45 else 0.0) + (0.012 if (i == 0 or y == LB) and z < 0.25 else 0.0)] for x, z in sec]
    fl = [''] * len(pts)
    h = arch_h(y)
    if h is not None:
        # fixed roles inside the opening: 1..5 well floor and wall (x = 0.60) up to the arch, 6 the outer edge on the
        # circle (flared), 7..10 the flank from the arch up to the shoulder; same indices at every arch station
        zt = pts[10][1]
        for j in range(1, 6):
            pts[j] = [0.60, ZB + (h - ZB) * (j - 1) / 4]; fl[j] = 'in'
        pts[6] = [surf_x(sec, h) + 0.020, h]; fl[6] = 'edge'
        for j in range(7, 10):
            z = h + (zt - h) * (j - 6) / 4
            pts[j] = [surf_x(sec, z) + 0.012 * max(0.0, 1 - (z - h) / 0.08), z]
    for sy in SEAMS:
        if abs(y - sy) < 1e-6:
            for j in SIDE: pts[j][0] -= 0.007; fl[j] = 'seam'
        elif abs(abs(y - sy) - SG) < 1e-6:
            for j in SIDE: fl[j] = 'seamside'
    ring = pts + [[-x, z] for x, z in pts[-2:0:-1]]
    rf = fl + fl[-2:0:-1]
    rings.append([bm.verts.new((x, y, z)) for x, z in ring]); flags.append(rf)
n = len(rings[0])
for i in range(len(rings) - 1):
    for j in range(n):
        j2 = (j + 1) % n
        f = bm.faces.new([rings[i][j], rings[i][j2], rings[i + 1][j2], rings[i + 1][j]])
        fs = {flags[i][j], flags[i][j2], flags[i + 1][j2], flags[i + 1][j]}
        if 'in' in fs: f.material_index = BL                                                # arch well wall, floor and rim
        elif 'seam' in fs and fs <= {'seam', 'seamside'}: f.material_index = BL           # seam groove
        else: f.material_index = RD
f = bm.faces.new(rings[0][::-1]); f.material_index = RD
f = bm.faces.new(rings[-1]); f.material_index = RD
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5); bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
# side intake: inset the loft's own faces inside the vent rectangle, push them in, colour them dark
vf = [f for f in bm.faces if abs(f.calc_center_median().x) > 0.7 and VENT[0] < f.calc_center_median().y < VENT[1]
      and VENT[2] < f.calc_center_median().z < VENT[3]]
for s in (-1, 1):
    side_faces = [f for f in vf if f.calc_center_median().x * s > 0]
    bmesh.ops.inset_region(bm, faces=side_faces, thickness=0.008, depth=-0.018, use_even_offset=True)
    for f in side_faces: f.material_index = BL
bm.normal_update()
add(bm)
for yc in (YF, YR):                                                      # wheel-well roof, inside the body only
    stroke([(yc + 0.32 * math.cos(math.pi * k / 14), R + 0.32 * math.sin(math.pi * k / 14)) for k in range(15)], 0.02, -0.60, 0.60, BL, 'X')

# ---------------------------------------------------------------- side details: slats in the intake, handle, skirts
def on_side(y0, y1, z0, z1, mi, proud=0.006, bev=0.005, depth=0.03):
    for s in (-1, 1):
        x = side_x((y0 + y1) / 2, (z0 + z1) / 2)
        a, b = x - depth, x + proud
        box((a if s > 0 else -b, y0, z0), (b if s > 0 else -a, y1, z1), mi, bev, 1)
for s in (-1, 1):
    for zc in (0.445, 0.505):
        x = side_x((VENT[0] + VENT[1]) / 2, zc)
        box(((x - 0.022) if s > 0 else (-x + 0.004), VENT[0] + 0.012, zc - 0.007), ((x - 0.004) if s > 0 else (-x + 0.022), VENT[1] - 0.012, zc + 0.007), GR, 0.003, 1)
on_side(2.50, 2.68, 0.655, 0.685, BL, 0.012, 0.008)                                         # door handle
for s in (-1, 1):
    xs = wid(2.3) - 0.03
    box((s * xs - 0.07, YF + RA + 0.06, 0.15), (s * xs + 0.07, YR - RA - 0.06, 0.24), BL, 0.02, 1)          # side skirt

# ---------------------------------------------------------------- front fascia: intake, splitter, lamp units in the corners
box((-0.50, -0.012, 0.24), (0.50, 0.06, 0.40), BL, 0.03, 2)                                  # lower intake
for z in (0.285, 0.335): box((-0.47, -0.02, z), (0.47, 0.0, z + 0.014), GR, 0.004, 1)
for s in (-1, 1):
    box((s * 0.66 - 0.11, -0.010, 0.25), (s * 0.66 + 0.11, 0.06, 0.37), BL, 0.02, 1)       # corner vents
box((-0.82, -0.05, 0.16), (0.82, 0.32, 0.215), BL, 0.02, 1)                                 # splitter
for s in (-1, 1):
    # dark surround and the lens, set into the corner and wrapping a little onto the side (no projector ring: it read as an eye)
    hexa({(sx, sy, sz): (s * (0.33 if sx < 0 else 0.76), -0.012 if sy < 0 else 0.09,
          (0.405 if sz < 0 else 0.505) + (0.035 if sx > 0 else 0.0)) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)}, BL, 0.012, 1)
    hexa({(sx, sy, sz): (s * (0.36 if sx < 0 else 0.73), -0.020 if sy < 0 else 0.0,
          (0.425 if sz < 0 else 0.49) + (0.032 if sx > 0 else 0.0)) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)}, LW, 0.006, 1)

# ---------------------------------------------------------------- rear: framed tail lamps, diffuser, exhausts
for s in (-1, 1):
    box((s * 0.57 - 0.22, LB - 0.05, 0.62), (s * 0.57 + 0.22, LB + 0.008, 0.74), BL, 0.015, 1)
    box((s * 0.57 - 0.19, LB - 0.02, 0.645), (s * 0.57 + 0.19, LB + 0.016, 0.715), LR, 0.008, 1)
box((-0.32, LB - 0.04, 0.665), (0.32, LB + 0.004, 0.695), BL, 0.006, 1)                      # light bar between the lamps
box((-0.20, LB - 0.03, 0.44), (0.20, LB + 0.006, 0.56), BL, 0.008, 1)                         # plate recess
box((-0.86, LB - 0.30, 0.15), (0.86, LB + 0.02, 0.32), BL, 0.03, 2)                           # diffuser / bumper
for k in range(5):
    x = -0.40 + k * 0.20; box((x - 0.012, LB - 0.20, 0.13), (x + 0.012, LB + 0.02, 0.30), BL, 0.0, 1)
for s in (-1, 1):
    lathe([(0.0, 0.0), (0.05, 0.0), (0.05, 0.16), (0.04, 0.16), (0.04, 0.10), (0.0, 0.10)], 16, GR, at(s * 0.62, LB - 0.10, 0.25) @ rotx(-90))

# ---------------------------------------------------------------- greenhouse: frame, glass, roof (normalised x, tumblehome)
ZW, ZT = 0.80, 1.25
def gh_fn(v):
    t = max(0.0, min(1.0, (v.z - ZW) / (ZT - ZW)))
    return Vector((v.x * (0.80 - 0.20 * t), v.y, v.z))
WSb, WSt, RFe, BKe = (1.74, ZW), (2.44, ZT - 0.04), (3.04, ZT - 0.03), (3.98, 0.87)
def gh(bm): addf(bm, gh_fn)
def gstroke(pts, w, u0, u1, mi, bev=0.01):
    P = [Vector(p) for p in pts]; L, Rr = [], []
    for i, p in enumerate(P):
        t0 = (P[i] - P[i - 1]).normalized() if i > 0 else (P[1] - P[0]).normalized()
        t1 = (P[i + 1] - P[i]).normalized() if i < len(P) - 1 else t0
        t = (t0 + t1).normalized(); nrm = Vector((-t.y, t.x)); L.append(p + nrm * w / 2); Rr.append(p - nrm * w / 2)
    gh(prism([tuple(v) for v in L + Rr[::-1]], u0, u1, mi, 'X', bev, 1, ret=True))
def toward(a, b, t): return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
gh(box((-0.98, 2.40, ZT - 0.07), (0.98, 3.08, ZT), RD, 0.04, 2, ret=True))                  # roof
gstroke([WSb, WSt], 0.016, -0.93, 0.93, GL, 0.0)                                            # windshield
gstroke([(WSb[0] - 0.02, WSb[1] + 0.02), (WSt[0] + 0.01, WSt[1] - 0.01)], 0.03, -0.96, -0.92, BL, 0.0)
gstroke([(WSb[0] - 0.02, WSb[1] + 0.02), (WSt[0] + 0.01, WSt[1] - 0.01)], 0.03, 0.92, 0.96, BL, 0.0)
gstroke([(WSb[0] - 0.05, WSb[1] + 0.012), (WSb[0] + 0.08, WSb[1] + 0.03)], 0.04, -0.97, 0.97, BL)   # cowl seal
gstroke([toward(RFe, BKe, 0.02), toward(RFe, BKe, 0.80)], 0.016, -0.88, 0.88, GL, 0.0)     # rear window
for u in (-0.90, 0.90):
    gstroke([toward(RFe, BKe, 0.02), toward(RFe, BKe, 0.80)], 0.03, u - 0.02, u + 0.02, BL, 0.0)
gstroke([toward(RFe, BKe, 0.80), BKe], 0.03, -1.0, 1.0, RD)                                  # rear deck lip
for s in (-1, 1):
    u0, u1 = (0.90, 1.0) if s > 0 else (-1.0, -0.90)
    gstroke([WSb, WSt, (2.52, ZT - 0.04)], 0.07, u0, u1, RD)                                 # A pillar into the roof rail
    gstroke([(2.50, ZT - 0.045), RFe], 0.06, u0, u1, RD)
    gh(prism([(2.92, ZW), RFe, toward(RFe, BKe, 0.72), BKe, (3.90, ZW)], u0, u1, RD, 'X', 0.012, 1, ret=True))  # C pillar
    g0, g1 = (0.955, 0.975) if s > 0 else (-0.975, -0.955)
    gh(prism([(1.90, ZW + 0.01), (2.46, ZT - 0.09), (2.86, ZT - 0.10), (2.94, ZW + 0.01)], g0, g1, GL, 'X', 0.0, 1, ret=True))  # door glass
    gh(prism([(3.02, 0.86), (3.07, 1.12), (3.44, 0.99), (3.38, 0.86)], 0.985 * s - 0.005, 0.985 * s + 0.005, IN, 'X', 0.0, 1, ret=True))
    gh(prism([(3.04, 0.875), (3.08, 1.10), (3.42, 0.985), (3.37, 0.875)], 0.997 * s - 0.004, 0.997 * s + 0.004, GL, 'X', 0.0, 1, ret=True))  # quarter glass
    f0, f1 = (0.95, 1.0) if s > 0 else (-1.0, -0.95)
    gh(prism([(2.86, ZT - 0.10), (2.94, ZW + 0.01), (2.99, ZW + 0.01), (2.91, ZT - 0.09)], f0, f1, BL, 'X', 0.0, 1, ret=True))  # B frame
    gstroke([(1.84, ZW + 0.012), (2.94, ZW + 0.012)], 0.025, f0, f1, BL, 0.0)               # window sill seal
    gstroke([(2.46, ZT - 0.085), (2.86, ZT - 0.095)], 0.02, f0, f1, BL, 0.0)                # window top seal
    # mirror housing on a stalk from the door
    xd = side_x(1.95, 0.76)
    box((min(s * (xd - 0.02), s * 0.97), 1.92, 0.80), (max(s * (xd - 0.02), s * 0.97), 1.97, 0.83), BL, 0.008, 1)
    box((s * 1.00 - 0.075, 1.86, 0.82), (s * 1.00 + 0.075, 2.00, 0.93), RD, 0.025, 2)
    box((s * 1.00 - 0.065, 2.00, 0.83), (s * 1.00 + 0.065, 2.01, 0.92), GR, 0.0, 1)

# rear spoiler on two struts
for s in (-1, 1):
    prism([(4.02, 0.86), (4.14, 0.86), (4.20, 1.01), (4.12, 1.01)], s * 0.52 - 0.02, s * 0.52 + 0.02, BL, 'X', 0.006, 1)
prism([(4.02, 1.01), (4.30, 1.04), (4.32, 1.07), (4.06, 1.055)], -0.80, 0.80, RD, 'X', 0.012, 2)
for s in (-1, 1):
    box((s * 0.80 - (0.012 if s < 0 else 0.0), 4.00, 0.96), (s * 0.80 + (0.012 if s > 0 else 0.0), 4.34, 1.10), BL, 0.006, 1)

# ---------------------------------------------------------------- interior: tub, dash, seats, wheel
box((-0.70, 1.74, 0.24), (0.70, 3.00, 0.34), IN, 0.0, 1)
box((-0.72, 1.80, 0.55), (0.72, 2.07, 0.80), IN, 0.04, 2)                                    # dash
box((-0.10, 2.07, 0.30), (0.10, 2.70, 0.55), IN, 0.03, 2)                                    # tunnel
lathe([(0.17, 0.0), (0.17, 0.03), (0.14, 0.03), (0.14, 0.0)], 24, BL, at(0.36, 2.18, 0.70) @ rotx(-65))
for k in range(3):
    box((-0.008, 0.0, 0.0), (0.008, 0.15, 0.02), BL, 0.0, 1, at(0.36, 2.18, 0.70) @ rotx(-65) @ rotz(120 * k - 90))
for x in (0.36, -0.36):
    box((x - 0.22, 2.32, 0.30), (x + 0.22, 2.77, 0.42), IN, 0.05, 2)
    hexa({(sx, sy, sz): (x + sx * 0.22, (2.72 if sy < 0 else 2.84) + (0.16 if sz > 0 else 0), 0.40 if sz < 0 else 1.00)
          for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)}, IN, 0.05, 2)
box((-0.70, 2.97, 0.30), (0.70, 3.40, 0.82), IN, 0.0, 1)                                     # rear bulkhead

# ---------------------------------------------------------------- wheels: wide tyres, five-spoke rims
for s in (-1, 1):
    for yc in (YF, YR):
        wheel(s * XT, yc, R, TW, s, BL, BL, rimr=0.225, n=32, hub=GR, lugs=5)
        M = at(s * XT, yc, R) @ roty(90 * s)
        lathe([(0.225, TW / 2 - 0.02), (0.235, TW / 2 - 0.02), (0.235, TW / 2 - 0.035), (0.215, TW / 2 - 0.05)], 32, GR, M, cap_top=False, cap_bot=False)
        for k in range(5):
            box((0.04, -0.024, TW / 2 - 0.075), (0.22, 0.024, TW / 2 - 0.035), GR, 0.008, 1, M @ rotz(72 * k + 18))
        cyl(0.05, TW / 2 - 0.08, TW / 2 - 0.03, GR, 12, M)
        lathe([(0.11, TW / 2 - 0.09), (0.15, TW / 2 - 0.09), (0.15, TW / 2 - 0.08), (0.11, TW / 2 - 0.08)], 16, RD, M, cap_top=False, cap_bot=False)  # brake caliper ring hint

# ---------------------------------------------------------------- check: no dark faces on the outer flank outside seams, intake and arches
def stray(c):
    if abs(c.x) < 0.5 or not (0.40 < c.y < 4.0) or not (ZB + 0.06 < c.z < zfender(c.y) - 0.02): return False
    if abs(abs(c.x) - side_x(c.y, c.z)) > 0.01: return False
    if any(abs(c.y - sy) < SG + 0.003 for sy in SEAMS): return False
    if VENT[0] - 0.01 < c.y < VENT[1] + 0.01 and VENT[2] - 0.03 < c.z < VENT[3] + 0.03: return False
    if 2.49 < c.y < 2.69 and 0.64 < c.z < 0.70: return False                     # door handle
    h = arch_h(c.y)
    if h is not None and c.z < h + 0.02: return False
    if any(abs(abs(c.y - yc) - RA) < 0.03 and c.z < R + 0.05 for yc in (YF, YR)): return False
    return True
STRAY = sum(1 for f in BM.faces if f.material_index == BL and stray(f.calc_center_median()))
PLANT = [stray(Vector((side_x(2.2, 0.50), 2.2, 0.50))), stray(Vector((side_x(1.3, 0.60), 1.3, 0.60)))]
print(f'[SportsCar] stray black faces on the flank: {STRAY} (planted test points flagged: {PLANT})')

# ---------------------------------------------------------------- centre on the footprint, export, render
cx, cy = centre_xy()
lo, hi = finish(NAME, seat=(0.36 - cx, 2.54 - cy, 0.42))
render(lo, hi, az=40, el=9, lens=70, fill=0.95, side='+X', sun=(50, 25))
compare()
# close crop of the left flank from the rear three-quarter, front arch to rear wheel
cam = scene.camera; cam.data.type = 'PERSP'; cam.data.lens = 50
tgt = Vector((0.85, (YF + YR) / 2 - cy, 0.48)); cam.location = Vector((3.4, YR - cy + 2.2, 1.05))
cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
sun = bpy.data.objects['Sun']; sun.rotation_euler = (math.radians(50), 0, math.radians(120))
scene.render.filepath = f'{OUT}/render-side-close.png'; bpy.ops.render.render(write_still=True)

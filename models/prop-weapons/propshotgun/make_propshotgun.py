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

def render(lo, hi, az=-35, el=18, lens=50, fill=0.98, side=None, sun=None):
    """Three-quarter preview with the camera fitted to the bbox; side='+X' adds an orthographic side view."""
    from bpy_extras.object_utils import world_to_camera_view
    cam, sunobj = stage(lo); cd = cam.data; cd.lens = lens
    if sun: sunobj.rotation_euler = (math.radians(sun[0]), 0, math.radians(az + sun[1]))     # light from the camera side
    c = Vector([(lo[i] + hi[i]) / 2 for i in range(3)])
    corners = [Vector(v.co) for o in scene.objects if o.type == 'MESH' and o.name.endswith('_Mesh') for v in o.data.vertices][::3]
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
# Generic pump-action shotgun prop (own design, silhouette only, no markings), 1.0 m long.
# Laid like the library prop guns: muzzle toward -Y, ejection side +X, up +Z, origin at the grip (wrist) centre.
# Receiver with ejection port, barrel with vent rib and bead, tube magazine with cap and barrel clamp,
# grooved wooden fore-end slide on action bars, trigger guard, fixed wooden stock with semi-pistol grip and pad.
NAME = 'PropShotgun'
WD, MT, BL = use('Wood', 'Graphite', 'Black')
BZ = 0.072
prism([(-0.120, 0.030), (-0.120, 0.088), (-0.110, 0.094), (0.050, 0.094), (0.065, 0.085), (0.070, 0.030)], -0.017, 0.017, MT, 'X', 0.003, 2)
box((0.017, -0.060, 0.062), (0.0185, -0.015, 0.080), BL, 0.0, 1)                                                 # ejection port (+X)
box((-0.0185, -0.090, 0.030), (0.0185, -0.020, 0.034), BL, 0.0, 1)                                               # loading port
lathe([(0.0, 0.0), (0.0115, 0.0), (0.0115, 0.540), (0.0105, 0.544), (0.0075, 0.544), (0.0075, 0.538), (0.0, 0.538)], 12, MT,
      at(0, -0.120, BZ) @ BACK)                                                                                   # barrel
box((-0.0032, -0.650, BZ + 0.0105), (0.0032, -0.120, BZ + 0.0150), MT, 0.001, 1)                                  # vent rib
lathe([(0.0, 0.0), (0.0028, 0.0), (0.0028, 0.004), (0.0, 0.006)], 8, BL, at(0, -0.645, BZ + 0.015))               # bead
MZ = 0.044
lathe([(0.0, 0.0), (0.0105, 0.0), (0.0105, 0.470), (0.0125, 0.470), (0.0125, 0.492), (0.0105, 0.496), (0.0, 0.496)], 12, MT,
      at(0, -0.120, MZ) @ BACK)                                                                                   # magazine tube + cap
hexa({(sx, sy, sz): (sx * 0.0135, -0.565 if sy < 0 else -0.550, (BZ + 0.010) if sz > 0 else (MZ - 0.012)) for sx in (-1, 1)
      for sy in (-1, 1) for sz in (-1, 1)}, MT, 0.002, 1)                                                         # barrel clamp
FE = [(0.0, 0.0), (0.019, 0.0), (0.023, 0.008)]
for k in range(6):
    z = 0.020 + k * 0.025
    FE += [(0.023, z), (0.0205, z + 0.003), (0.0205, z + 0.007), (0.023, z + 0.010)]
FE += [(0.023, 0.172), (0.019, 0.180), (0.0, 0.180)]
lathe(FE, 12, WD, at(0, -0.205, MZ + 0.002) @ BACK @ Matrix.Diagonal((1.0, 1.15, 1, 1)))                          # grooved fore-end
for s in (-1, 1): box((s * 0.0125 - 0.002, -0.210, MZ - 0.004), (s * 0.0125 + 0.002, -0.118, MZ + 0.004), MT, 0.0, 1)   # action bars
# trigger group
stroke([(-0.050, 0.030), (-0.052, 0.010), (-0.040, 0.002), (-0.006, 0.002), (0.008, 0.015), (0.010, 0.030)], 0.005, -0.004, 0.004, MT, 'X', 0.001, 1)
stroke([(-0.022, 0.030), (-0.027, 0.018), (-0.024, 0.008)], 0.0045, -0.0025, 0.0025, BL, 'X', 0.0008, 1)
cyl(0.004, 0.0, 0.004, BL, 8, at(0, 0.040, 0.094))                                                                # tang safety
# fixed wooden stock with semi-pistol grip
prism([(0.060, 0.088), (0.060, 0.030), (0.064, 0.000), (0.066, -0.032), (0.078, -0.046), (0.098, -0.044), (0.132, -0.020),
       (0.330, -0.088), (0.330, 0.058), (0.200, 0.066), (0.100, 0.078)], -0.021, 0.021, WD, 'X', 0.007, 2)
box((-0.022, 0.330, -0.092), (0.022, 0.345, 0.062), BL, 0.004, 1)                                                 # recoil pad
cyl(0.004, 0.0, 0.010, MT, 8, at(0, 0.290, -0.075) @ rotx(180 - 19))                                             # sling stud
shift(0, -0.074, 0.020)
lo, hi = finish(NAME)
render(lo, hi, az=78, el=16, lens=50, sun=(45, 25))
compare()

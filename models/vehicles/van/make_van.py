import bpy, sys, math, bmesh
from mathutils import Vector, Matrix, Euler
from bpy_extras.object_utils import world_to_camera_view

OUT = sys.argv[sys.argv.index('--') + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


# ------------------------------------------------------------------ materials (max 10)
MATS = {}
def mat(name, rgb, rough=0.75, metal=0.0, emit=0.0, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*rgb, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if emit:
        b.inputs['Emission Color'].default_value = (*rgb, 1)
        b.inputs['Emission Strength'].default_value = emit
    if alpha < 1:
        b.inputs['Alpha'].default_value = alpha
        try: m.surface_render_method = 'BLENDED'
        except Exception: pass
    m.diffuse_color = (*rgb, alpha)
    MATS[name] = m
    return name


# ------------------------------------------------------------------ helpers
parts = []          # (object, material name)
cutters = []
def keep(o, m):
    parts.append((o, m)); return o

def bevel(o, w, segs=2, angle=30):
    if w <= 0: return o
    b = o.modifiers.new('bevel', 'BEVEL'); b.width = w; b.segments = segs
    b.limit_method = 'ANGLE'; b.angle_limit = math.radians(angle)
    return o

def new_obj(name, bm):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); scene.collection.objects.link(o); return o

def box(name, c, size, m, bev=0.0, rot=(0, 0, 0), segs=2):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts: v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    o = new_obj(name, bm); o.location = c; o.rotation_euler = rot
    return keep(bevel(o, bev, segs), m)

def cyl(name, c, r, depth, axis, m, verts=32, bev=0.0, segs=2, rot=None, r2=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=verts, radius1=r,
                          radius2=r if r2 is None else r2, depth=depth)
    o = new_obj(name, bm); o.location = c
    o.rotation_euler = rot or {'X': (0, math.pi / 2, 0), 'Y': (math.pi / 2, 0, 0), 'Z': (0, 0, 0)}[axis]
    return keep(bevel(o, bev, segs), m)

def prism_x(name, pts, x0, x1, m, bev=0.0, taper=None, segs=2, keep_it=True):
    """Side profile pts [(d, z)] extruded across X from x0 to x1. taper(z) scales x (keep it linear: faces stay planar)."""
    bm = bmesh.new()
    vs = [bm.verts.new((x0, Y(d), z)) for d, z in pts]
    f = bm.faces.new(vs)
    r = bmesh.ops.extrude_face_region(bm, geom=[f])
    for v in [e for e in r['geom'] if isinstance(e, bmesh.types.BMVert)]: v.co.x = x1
    if taper:
        for v in bm.verts: v.co.x *= taper(v.co.z)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = new_obj(name, bm)
    bevel(o, bev, segs)
    return keep(o, m) if keep_it else o

def prism_y(name, pts, d0, d1, m, bev=0.0, segs=2, shear=None, keep_it=True):
    """Front cross-section pts [(x, z)] extruded along the length from d0 to d1. shear(d) adds a linear z offset."""
    bm = bmesh.new()
    vs = [bm.verts.new((x, Y(d0), z)) for x, z in pts]
    f = bm.faces.new(vs)
    r = bmesh.ops.extrude_face_region(bm, geom=[f])
    for v in [e for e in r['geom'] if isinstance(e, bmesh.types.BMVert)]: v.co.y = Y(d1)
    if shear:
        for v in bm.verts: v.co.z += shear(v.co.y + D0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = bevel(new_obj(name, bm), bev, segs)
    return keep(o, m) if keep_it else o

def cut(target, cutter, first=True):
    mod = target.modifiers.new('cut', 'BOOLEAN'); mod.operation = 'DIFFERENCE'; mod.object = cutter
    mod.solver = 'EXACT'
    if first: target.modifiers.move(len(target.modifiers) - 1, 0)
    cutter.hide_render = True; cutter.hide_viewport = True
    if cutter not in cutters: cutters.append(cutter)

def cutter_box(c, size, bev=0.0):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts: v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    o = new_obj('cutter', bm); o.location = c
    if bev: bevel(o, bev, 2)
    return o

def torus(name, c, R, r, m, rot=(0, 0, 0), maj=20, mnr=8):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=maj, minor_segments=mnr,
                                     location=c, rotation=rot)
    o = bpy.context.active_object; o.name = name
    return keep(o, m)


# ================================================================== VAN (round 2 rebuild, library)
# Generic full-size cargo van, own design. Measured from ../../van/ref-side.png at 3.28 mm/px;
# d = metres back from the front bumper tip, z = metres above the ground.
NAME = 'Van'
D0 = 2.65                        # centre of the length (bumper 0 .. rear bumper 5.30)
def Y(d): return d - D0          # front toward -Y
REF34 = OUT + '/../../van/ref-34.png'
REFSIDE = OUT + '/../../van/ref-side.png'
YAW, ELEV, SIDE34, SIDECAM = 38, 8, -1, 1
LENS = 75

PAINT = mat('Paint', (0.300, 0.045, 0.035), 0.55)
TRIM  = mat('Trim',  (0.150, 0.152, 0.158), 0.7)
BLACK = mat('Black', (0.012, 0.012, 0.013), 0.85)
GLASS = mat('Glass', (0.10, 0.13, 0.15), 0.05, alpha=0.55)
STEEL = mat('Steel', (0.50, 0.51, 0.53), 0.45, metal=0.3)
LAMP  = mat('Lamp',  (0.85, 0.85, 0.80), 0.2, emit=0.15)
AMBER = mat('Amber', (0.90, 0.33, 0.01), 0.35)
RED   = mat('Red',   (0.50, 0.01, 0.01), 0.35)

HW, TK, Z0 = 0.975, 0.04, 0.31  # half width at the sill, tumblehome per metre, sill height
def taper(z): return 1 - TK * (z - Z0)
def side_x(z): return HW * taper(z)
TH = math.atan(HW * TK)          # side lean angle
WR, WT, WX = 0.415, 0.235, 0.82  # tyre radius, width, wheel centre x
WD = [0.93, 4.25]

# ------------------------------------------------------------------ body shell: rounded hood and roof via a big bevel
PROFILE = [(0.11, Z0), (0.11, 1.17), (0.20, 1.26), (0.34, 1.31), (0.79, 1.41), (1.36, 2.03), (1.47, 2.12),
           (4.88, 2.12), (5.03, 2.03), (5.21, 1.27), (5.21, Z0)]
body = prism_x('Body', PROFILE, -HW, HW, PAINT, bev=0.09, segs=3, taper=taper)
# cab: hollow, windshield and side windows (cuts after the big bevel so the openings stay crisp)
cut(body, cutter_box((0, Y(1.62), 1.47), (1.72, 1.24, 1.03)), first=False)
cut(body, prism_x('wscut', [(0.83, 1.45), (1.31, 1.98), (1.70, 1.98), (1.70, 1.45)], -0.80, 0.80, PAINT, keep_it=False), first=False)
WIN = [(1.30, 1.32), (1.30, 1.52), (1.50, 1.96), (2.04, 1.96), (2.04, 1.32)]
for s in (-1, 1):
    cut(body, prism_x('wincut', WIN, s * 0.6, s * 1.3, PAINT, bev=0.025, keep_it=False), first=False)
# wheel arches
def arch_out(dc, bot): return [(dc - 0.45, bot), (dc - 0.44, 0.66), (dc - 0.37, 0.85), (dc - 0.20, 0.98),
                               (dc + 0.19, 0.98), (dc + 0.37, 0.88), (dc + 0.47, 0.70), (dc + 0.50, bot)]
def arch_in(dc, bot): return [(dc - 0.37, bot), (dc - 0.36, 0.62), (dc - 0.30, 0.78), (dc - 0.16, 0.90),
                              (dc + 0.15, 0.90), (dc + 0.30, 0.81), (dc + 0.39, 0.66), (dc + 0.42, bot)]
for dc in WD:
    for s in (-1, 1):
        cut(body, prism_x('archcut', arch_in(dc, 0.1), s * 0.55, s * 1.3, PAINT, keep_it=False), first=False)
        prism_x('Liner', arch_in(dc, 0.45), s * 0.55, s * 0.58, BLACK)
        # raised arch lip in body colour, standing proud of the side
        a, b = sorted((s * 0.925, s * 1.0))
        prism_x('ArchLip', arch_out(dc, Z0 + 0.02) + arch_in(dc, Z0 + 0.02)[::-1], a, b, PAINT, bev=0.018, segs=2)
# inset cargo panel on the left side (+X), sliding door on the right (-X)
PANEL = [(2.27, 1.36), (2.27, 1.98), (4.95, 1.98), (4.95, 1.36)]
cut(body, prism_x('panelcut', PANEL, HW - 0.03, 1.4, PAINT, bev=0.035, segs=2, taper=taper, keep_it=False), first=False)
bevel(body, 0.01, 1, 40)

def on_side(s, d, z, size, m, out=0.001, bev=0.0):
    """A thin part lying on the leaning body side."""
    return box('Side', (s * (side_x(z) + out + size[0] / 2 - 0.004), Y(d), z), size, m, bev=bev, rot=(0, -s * TH, 0))

for s in (-1, 1):
    # cab door shut lines (front edge, rear edge, bottom, top) and handle
    on_side(s, 1.03, 1.21, (0.008, 0.008, 0.42), BLACK)
    on_side(s, 2.15, 1.22, (0.008, 0.008, 1.52), BLACK)
    on_side(s, 1.80, 0.46, (0.008, 0.70, 0.008), BLACK)
    on_side(s, 1.97, 1.23, (0.03, 0.17, 0.055), BLACK, out=0.004, bev=0.01)
    # belt crease (full length) and lower crease between the arches
    on_side(s, 2.66, 1.16, (0.012, 4.98, 0.03), PAINT, bev=0.004)
    on_side(s, 2.60, 0.68, (0.012, 2.13, 0.03), PAINT, bev=0.004)
    for d0, d1 in ((0.15, 0.46), (4.77, 5.02)):
        on_side(s, (d0 + d1) / 2, 0.68, (0.012, d1 - d0, 0.03), PAINT, bev=0.004)
    # mirror on an arm
    box('MirrorArm', (s * 1.0, Y(1.16), 1.36), (0.12, 0.05, 0.05), BLACK, bev=0.01)
    box('Mirror', (s * 1.07, Y(1.21), 1.46), (0.07, 0.18, 0.33), BLACK, bev=0.025, segs=2)
    box('MirrorGlass', (s * 1.07, Y(1.30), 1.46), (0.05, 0.006, 0.27), GLASS)
    # side marker under the headlamp
    box('SideMarker', (s * (side_x(0.82) - 0.002), Y(0.20), 0.82), (0.02, 0.14, 0.10), AMBER, bev=0.006)
# sliding door on the right
for d, z, h in ((2.24, 1.22, 1.52), (3.58, 1.22, 1.52)):
    on_side(-1, d, z, (0.008, 0.008, h), BLACK)
on_side(-1, 2.91, 0.46, (0.008, 1.34, 0.008), BLACK)
on_side(-1, 4.22, 1.33, (0.01, 1.30, 0.02), BLACK)      # slide track
on_side(-1, 2.40, 1.23, (0.03, 0.17, 0.055), BLACK, out=0.004, bev=0.01)

# ------------------------------------------------------------------ front: grille panel, round lamps, bumper
box('GrillePanel', (0, Y(0.085), 0.99), (1.62, 0.06, 0.38), TRIM, bev=0.03, segs=2)
box('GrilleBack', (0, Y(0.054), 0.99), (0.86, 0.01, 0.26), BLACK)
for z in (0.93, 0.99, 1.05):
    box('GrilleBar', (0, Y(0.050), z), (0.86, 0.02, 0.025), TRIM, bev=0.006)
for s in (-1, 1):
    cyl('LampBezel', (s * 0.62, Y(0.052), 0.99), 0.115, 0.02, 'Y', BLACK, 24)
    cyl('Headlight', (s * 0.62, Y(0.040), 0.99), 0.095, 0.03, 'Y', LAMP, 24, 0.02, 2)
    box('Indicator', (s * 0.76, Y(-0.003), 0.58), (0.13, 0.02, 0.06), AMBER, bev=0.006)
box('BumperF', (0, Y(0.24), 0.515), (2.0, 0.48, 0.34), TRIM, bev=0.05, segs=3)
box('BumperSlot', (0, Y(-0.002), 0.42), (1.0, 0.02, 0.04), BLACK)
box('Plate', (0, Y(-0.005), 0.56), (0.44, 0.012, 0.13), LAMP, bev=0.008)
box('Wiper', (0.20, Y(0.90), 1.535), (0.62, 0.02, 0.02), BLACK, rot=(math.atan2(0.53, 0.48), 0, math.radians(4)))
box('Wiper', (-0.42, Y(0.90), 1.535), (0.62, 0.02, 0.02), BLACK, rot=(math.atan2(0.53, 0.48), 0, math.radians(4)))

# ------------------------------------------------------------------ rear: doors, lamps, bumper
box('BumperR', (0, Y(5.135), 0.505), (2.0, 0.33, 0.31), TRIM, bev=0.05, segs=3)
box('RearSeam', (0, Y(5.212), 0.82), (0.008, 0.006, 0.88), BLACK)
RL = math.atan2(0.18, 0.74)
box('RearSeamUp', (0, Y(5.125), 1.64), (0.008, 0.006, 0.70), BLACK, rot=(RL, 0, 0))
for s in (-1, 1):
    box('RearHandle', (s * 0.10, Y(5.22), 1.02), (0.05, 0.03, 0.14), BLACK, bev=0.008)
    box('TailRed', (s * 0.86, Y(5.18), 1.13), (0.17, 0.08, 0.25), RED, bev=0.02)
    box('TailWhite', (s * 0.86, Y(5.18), 0.92), (0.17, 0.08, 0.15), LAMP, bev=0.02)
box('RearGlassL', (0.45, Y(5.122), 1.66), (0.66, 0.006, 0.42), BLACK, rot=(RL, 0, 0))
box('RearGlassR', (-0.45, Y(5.122), 1.66), (0.66, 0.006, 0.42), BLACK, rot=(RL, 0, 0))

# ------------------------------------------------------------------ glass (inset in frames) and cab interior
WSA = math.atan2(0.53, 0.48)
box('Windshield', (0, Y(1.07 + 0.017), 1.71 - 0.016), (1.66, 0.76, 0.008), GLASS, rot=(WSA, 0, 0))
for s in (-1, 1):
    xg = side_x(1.6) - 0.03
    prism_x('SideGlass', WIN, s * xg, s * (xg + 0.008), GLASS)
box('CabFloor', (0, Y(1.62), 0.96), (1.72, 1.24, 0.02), BLACK)
box('Dash', (0, Y(1.10), 1.28), (1.70, 0.30, 0.26), BLACK, bev=0.04)
box('Bulkhead', (0, Y(2.22), 1.47), (1.72, 0.02, 1.03), BLACK)
for sx in (-0.42, 0.42):
    box('SeatBase', (sx, Y(1.76), 1.03), (0.50, 0.50, 0.15), BLACK, bev=0.04)
    box('SeatBack', (sx, Y(2.03), 1.38), (0.50, 0.12, 0.60), BLACK, bev=0.04, rot=(math.radians(-10), 0, 0))
    box('Headrest', (sx, Y(2.09), 1.76), (0.26, 0.09, 0.16), BLACK, bev=0.03, rot=(math.radians(-10), 0, 0))
SWC = (0.42, Y(1.38), 1.44)
torus('SteeringWheel', SWC, 0.19, 0.018, BLACK, rot=(math.radians(-60), 0, 0), maj=24, mnr=6)
box('Spoke', SWC, (0.34, 0.025, 0.03), BLACK, rot=(math.radians(-60), 0, 0))
SEAT = (0.42, Y(1.76), 1.11)

# ------------------------------------------------------------------ chassis and wheels (steel wheels with hubcaps)
for dc in WD:
    cyl('Axle', (0, Y(dc), WR), 0.05, 2 * WX - 0.2, 'X', BLACK, 12)
def wheel(c, s):
    o = s * WT / 2
    cyl('Tyre', c, WR, WT, 'X', BLACK, 32, 0.06, 2)
    cyl('Sidewall', c + Vector((o, 0, 0)), 0.33, 0.012, 'X', BLACK, 32)
    cyl('Hubcap', c + Vector((o - s * 0.005, 0, 0)), 0.245, 0.03, 'X', STEEL, 32, 0.012, 2)
    for k in range(8):
        a = k * math.pi / 4 + math.pi / 8
        box('Slot', c + Vector((o + s * 0.011, 0.165 * math.cos(a), 0.165 * math.sin(a))),
            (0.006, 0.045, 0.06), BLACK, rot=(a, 0, 0))
    cyl('HubBoss', c + Vector((o + s * 0.018, 0, 0)), 0.095, 0.03, 'X', STEEL, 24, 0.012, 2)
for dc in WD:
    for s in (-1, 1):
        wheel(Vector((s * WX, Y(dc), WR)), s)

# ------------------------------------------------------------------ merge into one mesh with fixed material slots
# A part's material may be a function f(centre, normal) -> material name; then CUTS_Z planes split it first.
MAT_ORDER = list(MATS.keys())
dg = bpy.context.evaluated_depsgraph_get()
bm = bmesh.new()
for o, m in parts:
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
    me.transform(o.matrix_world)
    if callable(m):
        b2 = bmesh.new(); b2.from_mesh(me)
        for zc in getattr(m, 'cuts', []):
            g = b2.verts[:] + b2.edges[:] + b2.faces[:]
            bmesh.ops.bisect_plane(b2, geom=g, plane_co=(0, 0, zc), plane_no=(0, 0, 1))
        for f in b2.faces: f.material_index = MAT_ORDER.index(m(f.calc_center_median(), f.normal))
        b2.to_mesh(me); b2.free()
    else:
        idx = MAT_ORDER.index(m)
        for p in me.polygons: p.material_index = idx
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)
for f in bm.faces: f.smooth = True
for e in bm.edges:
    e.smooth = e.is_manifold and e.calc_face_angle(math.pi) < math.radians(40)
used = sorted({f.material_index for f in bm.faces})
remap = {old: new for new, old in enumerate(used)}
for f in bm.faces: f.material_index = remap[f.material_index]
bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
me = bpy.data.meshes.new(NAME + '_Mesh'); bm.to_mesh(me); bm.free()
for i in used: me.materials.append(MATS[MAT_ORDER[i]])
for o, _ in parts: bpy.data.objects.remove(o)
for o in cutters: bpy.data.objects.remove(o)
body = bpy.data.objects.new(NAME + '_Mesh', me); scene.collection.objects.link(body)
# guard against the join slot shuffle: every slot must carry the material its faces were given
assert [m.name for m in me.materials] == [MAT_ORDER[i] for i in used]

tris = len(me.polygons)
xs = [v.co.x for v in me.vertices]; ys = [v.co.y for v in me.vertices]; zs = [v.co.z for v in me.vertices]
print(f'[{NAME}] triangles {tris}, materials {len(me.materials)} {[m.name for m in me.materials]}')
print(f'[{NAME}] size x {max(xs)-min(xs):.2f} y {max(ys)-min(ys):.2f} z {max(zs)-min(zs):.2f}  '
      f'y {min(ys):.2f}..{max(ys):.2f} x {min(xs):.2f}..{max(xs):.2f} z {min(zs):.2f}..{max(zs):.2f}')

root = bpy.data.objects.new(NAME, None); scene.collection.objects.link(root); body.parent = root
seat = bpy.data.objects.new('Seat', None); seat.location = SEAT
scene.collection.objects.link(seat); seat.parent = root
for o in scene.objects: o.select_set(o in (root, body, seat))
bpy.ops.export_scene.fbx(filepath=f'{OUT}/{NAME}.fbx', use_selection=True, apply_unit_scale=True,
                         apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)

# ------------------------------------------------------------------ previews (match the reference framing)
world = bpy.data.worlds.new('W'); scene.world = world; world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.70, 0.70, 0.71, 1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.0
bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 0, 0)); ground = bpy.context.active_object
gm = bpy.data.materials.new('Ground'); gm.use_nodes = True
gm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.40, 0.40, 0.405, 1)
gm.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 1.0
ground.data.materials.append(gm)
bpy.ops.object.light_add(type='SUN', location=(0, 0, 10)); sun = bpy.context.active_object
sun.data.energy = 2.2; sun.data.angle = math.radians(25)
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x, scene.render.resolution_y = 1672, 941
scene.view_settings.view_transform = 'Standard'
cam_data = bpy.data.cameras.new('Cam'); cam = bpy.data.objects.new('Cam', cam_data)
scene.collection.objects.link(cam); scene.camera = cam
PTS = [body.matrix_world @ v.co for v in list(me.vertices)[::7]]

def ref_bbox(path, thr=0.12):
    """Pixel bbox (x0, x1, y0, y1, top-down) of the object in a reference on a plain backdrop."""
    import numpy as np
    im = bpy.data.images.load(path); w, h = im.size
    a = np.array(im.pixels[:]).reshape(h, w, 4)[::-1, :, :3]
    bg = np.median(np.concatenate([a[:6].reshape(-1, 3), a[:, :6].reshape(-1, 3), a[:, -6:].reshape(-1, 3)]), axis=0)
    m = np.abs(a - bg).max(axis=2) > thr
    rows = np.where(m.sum(1) > 4)[0]; cols = np.where(m.sum(0) > 4)[0]
    return (cols[0] * 1672 / w, cols[-1] * 1672 / w, rows[0] * 941 / h, rows[-1] * 941 / h)

def frame_bounds():
    bpy.context.view_layer.update()
    cs = [world_to_camera_view(scene, cam, p) for p in PTS]
    return min(c.x for c in cs), max(c.x for c in cs), min(c.y for c in cs), max(c.y for c in cs)

def shoot34(yaw_deg, elev_deg, lens, box_px, side):
    """yaw from the nose toward the given side (-1: vehicle right / -X, +1: left / +X); box_px = ref bbox."""
    cam_data.type = 'PERSP'; cam_data.lens = lens
    yaw, el = math.radians(yaw_deg), math.radians(elev_deg)
    dirv = Vector((side * math.sin(yaw) * math.cos(el), -math.cos(yaw) * math.cos(el), math.sin(el)))
    tgt = Vector((0, 0, (max(zs) + min(zs)) / 2)); dist = 3 * (max(ys) - min(ys))
    W, H = 1672.0, 941.0
    want = ((box_px[0] + box_px[1]) / 2 / W, 1 - (box_px[2] + box_px[3]) / 2 / H,
            (box_px[1] - box_px[0]) / W, (box_px[3] - box_px[2]) / H)
    for _ in range(14):
        cam.location = tgt + dirv * dist
        cam.rotation_euler = (-dirv).to_track_quat('-Z', 'Y').to_euler()
        x0, x1, y0, y1 = frame_bounds()
        k = max((x1 - x0) / want[2], (y1 - y0) / want[3])
        dist *= k ** 0.9
        right = cam.matrix_world.to_3x3() @ Vector((1, 0, 0)); up = cam.matrix_world.to_3x3() @ Vector((0, 1, 0))
        vw = dist * 36.0 / lens
        tgt += right * ((x0 + x1) / 2 - want[0]) * vw + up * ((y0 + y1) / 2 - want[1]) * vw * H / W
    scene.render.filepath = f'{OUT}/render-34.png'; bpy.ops.render.render(write_still=True)

def shoot_side(box_px, cam_side):
    """cam_side +1: camera on +X (front on the left of the frame); -1: camera on -X (front on the right)."""
    W, H = 1672.0, 941.0
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = (max(ys) - min(ys)) / ((box_px[1] - box_px[0]) / W)
    cx_frac = (box_px[0] + box_px[1]) / 2 / W
    ground_frac = 1 - box_px[3] / H
    yc = (min(ys) + max(ys)) / 2 - cam_side * (cx_frac - 0.5) * cam_data.ortho_scale
    zc = (0.5 - ground_frac) * cam_data.ortho_scale * H / W
    cam.location = (cam_side * 30, yc, zc); cam.rotation_euler = (math.pi / 2, 0, cam_side * math.pi / 2)
    scene.render.filepath = f'{OUT}/render-side.png'; bpy.ops.render.render(write_still=True)

sun.rotation_euler = (math.radians(35), 0, math.radians(150 if SIDE34 > 0 else -150))
shoot34(YAW, ELEV, globals().get('LENS', 50), ref_bbox(REF34), SIDE34)
sun.rotation_euler = (math.radians(30), 0, math.radians(60 if SIDECAM > 0 else -60))
shoot_side(ref_bbox(REFSIDE), SIDECAM)

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


# ================================================================== CITY BUS (library)
# Generic single-deck low-floor city bus, own design. Lengths from ref-side.png at 7.52 mm/px, heights rescaled
# to a 2.88 m roof (the reference is stubbier than a real bus); d = metres back from the front bumper tip.
NAME = 'CityBus'
D0 = 6.0                         # centre of the length (bumper 0 .. rear bumper 12.0)
def Y(d): return d - D0          # front toward -Y
REF34 = OUT + '/ref-34.png'
REFSIDE = OUT + '/ref-side.png'
YAW, ELEV, SIDE34, SIDECAM = 44, 5, -1, -1
LENS = 45

PAINT = mat('Paint', (0.020, 0.105, 0.420), 0.5)
WHITE = mat('White', (0.78, 0.79, 0.80), 0.6)
BLACK = mat('Black', (0.012, 0.012, 0.013), 0.85)
GLASS = mat('Glass', (0.20, 0.25, 0.28), 0.05, alpha=0.30)
STEEL = mat('Steel', (0.50, 0.51, 0.53), 0.45, metal=0.3)
LAMP  = mat('Lamp',  (0.85, 0.85, 0.80), 0.2, emit=0.15)
AMBER = mat('Amber', (0.90, 0.33, 0.01), 0.35)
RED   = mat('Red',   (0.50, 0.01, 0.01), 0.35)

HW = 1.275
WR, WT, WX = 0.50, 0.30, 1.10
WD = [3.37, 10.20]
WZ0, WZ1 = 1.41, 2.35            # window glass bottom, top
DOORS = [(1.34, 2.50), (8.14, 9.40)]                     # on the kerb side (-X)
WIN_COMMON = [(0.50, 1.18), (2.73, 4.29), (4.46, 6.11), (6.30, 7.99), (9.57, 10.70), (10.85, 11.45)]
WIN_LEFT = WIN_COMMON + [(1.40, 2.45), (8.15, 9.40)]     # +X side has windows where the doors are

def livery(c, n):
    """Blue skirt and roof, white middle; the nose stays white down to the bumper."""
    outside = abs(c.x) > HW - 0.05 or c.z > 2.72 or c.z < 0.33 or c.y < Y(0.45) or c.y > Y(11.9)
    if outside and c.z > 2.64: return PAINT
    if outside and c.z < 0.83 and c.y > Y(0.45): return PAINT
    return WHITE
livery.cuts = [0.83, 2.64]

# ------------------------------------------------------------------ body shell
PROFILE = [(0.08, 0.32), (0.08, 1.15), (0.10, 1.22), (0.32, 2.62), (0.45, 2.82), (0.65, 2.88),
           (11.70, 2.88), (11.90, 2.80), (11.97, 2.62), (11.97, 0.32)]
body = prism_x('Body', PROFILE, -HW, HW, livery, bev=0.14, segs=3)
cut(body, cutter_box((0, Y(6.05), 1.575), (2.40, 11.6, 2.25)), first=False)            # hollow saloon
cut(body, prism_x('wscut', [(-0.2, 1.25), (-0.2, 2.60), (0.7, 2.60), (0.7, 1.25)], -1.17, 1.17, PAINT, keep_it=False), first=False)
band = {}
for s in (-1, 1):
    band[s] = box('WindowBand', (s * (HW + 0.004), Y(6.0), 1.895), (0.012, 11.16, 1.19), BLACK)
def rect(d0, d1, z0, z1): return [(d0, z0), (d0, z1), (d1, z1), (d1, z0)]
for s, wins in ((-1, WIN_COMMON), (1, WIN_LEFT)):
    for d0, d1 in wins:
        c = prism_x('wincut', rect(d0, d1, WZ0, WZ1), s * 1.0, s * 1.6, PAINT, bev=0.03, keep_it=False)
        cut(body, c, first=False); cut(band[s], c, first=False)
for d0, d1 in DOORS:
    c = prism_x('doorcut', rect(d0, d1, 0.25, 2.40), -1.6, -1.0, PAINT, bev=0.02, keep_it=False)
    cut(body, c, first=False); cut(band[-1], c, first=False)
def arc(dc, R, Rz, b, n=14):
    return [(dc + R, b)] + [(dc + R * math.cos(math.pi * k / n), 0.50 + Rz * math.sin(math.pi * k / n)) for k in range(n + 1)] + [(dc - R, b)]
for dc in WD:
    for s in (-1, 1):
        cut(body, prism_x('archcut', arc(dc, 0.64, 0.58, 0.1), s * 0.95, s * 1.6, PAINT, keep_it=False), first=False)
        a, b = sorted((s * 1.255, s * 1.30))
        prism_x('ArchLip', arc(dc, 0.78, 0.70, 0.33) + arc(dc, 0.64, 0.58, 0.33)[::-1], a, b, PAINT, bev=0.018, segs=2)
    box('WheelHouse', (0, Y(dc), 0.83), (2.40, 1.50, 0.76), BLACK, bev=0.06)
bevel(body, 0.012, 1, 40)

# ------------------------------------------------------------------ glass in frames, doors
for s, wins in ((-1, WIN_COMMON), (1, WIN_LEFT)):
    for d0, d1 in wins:
        box('SideGlass', (s * (HW - 0.045), Y((d0 + d1) / 2), (WZ0 + WZ1) / 2), (0.008, d1 - d0 + 0.04, WZ1 - WZ0 + 0.04), GLASS)
        if d0 > 1.3:
            box('Transom', (s * (HW - 0.03), Y((d0 + d1) / 2), 2.17), (0.03, d1 - d0, 0.04), BLACK)
for d0, d1 in DOORS:
    for p in (d0 - 0.03, d1 + 0.03):
        box('DoorPost', (-(HW + 0.004), Y(p), 1.37), (0.014, 0.07, 2.06), BLACK)
    box('DoorStep', (-(HW - 0.10), Y((d0 + d1) / 2), 0.345), (0.20, d1 - d0, 0.02), AMBER)
    wl = (d1 - d0) / 2
    for a in (d0, d0 + wl):                              # two leaves, each a black frame round a tall pane
        b = a + wl; x = -(HW - 0.035)
        for p in (a + 0.03, b - 0.03):
            box('LeafPost', (x, Y(p), 1.375), (0.04, 0.06, 2.03), BLACK)
        for z, h in ((2.355, 0.07), (0.42, 0.14), (0.80, 0.04)):
            box('LeafRail', (x, Y((a + b) / 2), z), (0.04, wl - 0.02, h), BLACK)
        box('LeafGlass', (x, Y((a + b) / 2), 1.40), (0.01, wl - 0.10, 1.90), GLASS)
        cyl('LeafRail', (x + 0.06, Y((a + b) / 2), 1.20), 0.018, 1.10, 'Z', AMBER, 8)

# ------------------------------------------------------------------ front: windshield, display, lamps, bumper
WSL = math.atan2(0.22, 1.40)
box('Windshield', (0, Y(0.245), 1.925), (2.36, 0.008, 1.42), GLASS, rot=(-WSL, 0, 0))
box('Destination', (0, Y(0.36), 2.44), (2.30, 0.04, 0.30), BLACK, rot=(-WSL, 0, 0))
box('ScreenBase', (0, Y(0.085), 1.20), (2.42, 0.04, 0.07), BLACK)
for s in (-1, 1):
    box('Wiper', (s * 0.50 - 0.10, Y(0.085), 1.33), (0.85, 0.02, 0.025), BLACK, rot=(-WSL, -math.radians(14), 0))
    box('LampBezel', (s * 0.83, Y(0.072), 0.90), (0.48, 0.02, 0.21), BLACK, bev=0.02)
    box('Headlight', (s * 0.83, Y(0.062), 0.90), (0.40, 0.02, 0.14), LAMP, bev=0.015)
    box('Indicator', (s * 1.13, Y(0.068), 0.90), (0.16, 0.025, 0.13), AMBER, bev=0.012)
    box('Vent', (s * 0.75, Y(-0.002), 0.50), (0.42, 0.01, 0.10), BLACK)
    # mirrors on swan-neck arms from the roof corners
    dx = 0.30; dy = -0.40
    box('MirrorArm', (s * 1.36, Y(0.30), 2.68), (0.50, 0.05, 0.05), BLACK, rot=(0, 0, math.atan2(dy, s * dx)))
    box('MirrorDrop', (s * 1.51, Y(0.10), 2.53), (0.05, 0.05, 0.30), BLACK)
    box('Mirror', (s * 1.51, Y(0.10), 2.17), (0.09, 0.15, 0.48), BLACK, bev=0.03, segs=2)
box('BumperF', (0, Y(0.20), 0.51), (2.55, 0.40, 0.42), PAINT, bev=0.06, segs=3)
box('BumperR', (0, Y(11.85), 0.51), (2.55, 0.30, 0.42), PAINT, bev=0.06, segs=3)

# ------------------------------------------------------------------ rear and sides
box('RearWindow', (0, Y(11.973), 1.95), (1.90, 0.01, 0.90), BLACK, bev=0.004)
for z in (0.92, 1.00, 1.08, 1.16, 1.24):
    box('RearGrille', (0, Y(11.973), z), (1.30, 0.012, 0.035), BLACK)
for s in (-1, 1):
    box('TailRed', (s * 1.10, Y(11.97), 1.03), (0.24, 0.03, 0.15), RED, bev=0.01)
    box('TailAmber', (s * 1.10, Y(11.97), 0.84), (0.24, 0.03, 0.15), AMBER, bev=0.01)
    for z in (0.98, 1.06, 1.14, 1.22, 1.30):
        box('Louvre', (s * (HW + 0.003), Y(11.55), z), (0.01, 0.45, 0.035), BLACK)
    for d in (4.46, 7.77, 11.2):
        box('Marker', (s * (HW + 0.008), Y(d), 0.56), (0.02, 0.12, 0.05), AMBER, bev=0.005)
# roof pod (air conditioning) with vents
box('RoofPod', (0, Y(4.65), 2.95), (1.80, 3.30, 0.30), WHITE, bev=0.10, segs=3)
for s in (-1, 1):
    for k in range(3):
        box('PodVent', (s * 0.45, Y(3.40 + 0.10 * k), 3.101), (0.55, 0.04, 0.006), BLACK)
        box('PodVent', (s * 0.45, Y(5.70 + 0.10 * k), 3.101), (0.55, 0.04, 0.006), BLACK)

# ------------------------------------------------------------------ saloon interior: floor, seat rows, poles, cab
box('Floor', (0, Y(6.05), 0.462), (2.38, 11.55, 0.02), BLACK)
box('Dash', (0, Y(0.56), 0.95), (2.30, 0.42, 0.40), BLACK, bev=0.05)
box('DriverBase', (0.75, Y(1.10), 0.95), (0.50, 0.50, 0.15), BLACK, bev=0.04)
box('DriverBack', (0.75, Y(1.37), 1.36), (0.50, 0.12, 0.72), BLACK, bev=0.04, rot=(math.radians(-8), 0, 0))
torus('SteeringWheel', (0.75, Y(0.80), 1.28), 0.23, 0.02, BLACK, rot=(math.radians(-25), 0, 0), maj=24, mnr=6)
box('CabScreen', (0.62, Y(1.55), 1.60), (0.02, 0.40, 1.0), GLASS)
SEAT = (0.75, Y(1.10), 1.03)

def seat(x, d, zb):
    box('SeatBase', (x, Y(d), zb), (0.42, 0.42, 0.08), PAINT, bev=0.015, segs=1)
    box('SeatBack', (x, Y(d + 0.21), zb + 0.30), (0.42, 0.06, 0.55), PAINT, bev=0.015, segs=1, rot=(math.radians(-8), 0, 0))
    box('SeatGrip', (x, Y(d + 0.25), zb + 0.60), (0.30, 0.03, 0.03), STEEL)
SX = (-1.00, -0.56, 0.56, 1.00)
for d in (4.5, 5.3, 6.1, 6.9, 7.7):
    for x in SX: seat(x, d, 0.92)
for d in (2.9, 3.7, 9.7, 10.5):
    for x in SX: seat(x, d, 1.30)
for d in (8.5, 9.25):
    for x in SX[2:]: seat(x, d, 0.92)
for x in (-1.0, -0.5, 0.0, 0.5, 1.0):
    seat(x, 11.30, 1.22)
for d0, d1 in DOORS:
    for p in (d0 + 0.15, d1 - 0.15):
        cyl('DoorPole', (-1.05, Y(p), 1.58), 0.02, 2.24, 'Z', AMBER, 8)
for d in (2.6, 4.9, 6.5, 8.1, 10.1):
    for s in (-1, 1):
        cyl('Pole', (s * 0.33, Y(d), 1.58), 0.02, 2.24, 'Z', AMBER, 8)
for s in (-1, 1):
    cyl('CeilingRail', (s * 0.40, Y(6.4), 2.50), 0.018, 9.8, 'Y', AMBER, 8)

# ------------------------------------------------------------------ chassis and wheels
def wheel(c, s):
    o = s * WT / 2
    cyl('Tyre', c, WR, WT, 'X', BLACK, 32, 0.07, 2)
    cyl('Rim', c + Vector((o - s * 0.006, 0, 0)), 0.30, 0.03, 'X', STEEL, 32, 0.012, 2)
    cyl('RimDish', c + Vector((o + s * 0.010, 0, 0)), 0.22, 0.006, 'X', STEEL, 32)
    cyl('Hub', c + Vector((o + s * 0.020, 0, 0)), 0.11, 0.03, 'X', STEEL, 24, 0.012, 2)
    cyl('HubCap', c + Vector((o + s * 0.038, 0, 0)), 0.05, 0.02, 'X', BLACK, 12, 0.006, 1)
    for k in range(10):
        a = k * math.pi / 5
        cyl('Lug', c + Vector((o + s * 0.016, 0.17 * math.cos(a), 0.17 * math.sin(a))), 0.022, 0.03, 'X', BLACK, 8)
for dc in WD:
    cyl('Axle', (0, Y(dc), WR), 0.06, 2 * WX - 0.2, 'X', BLACK, 12)
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

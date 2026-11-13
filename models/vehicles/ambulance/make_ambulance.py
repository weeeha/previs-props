# Box-body ambulance on a van cab (own design), library round.
# Blender 5.1 headless:  Blender -b --python make_ambulance.py -- <out dir>
# d = metres back from the front bumper tip. Front toward -Y, up +Z, origin on the ground at the footprint centre.
import bpy, sys, math, bmesh
from mathutils import Vector, Matrix

OUT = sys.argv[sys.argv.index('--') + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

NAME = 'Ambulance'
LEN = 6.00
D0 = LEN / 2
def Y(d): return d - D0

# ------------------------------------------------------------------ materials (max 8)
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

WHITE  = mat('PaintWhite', (0.80, 0.80, 0.78), 0.5)
RED    = mat('Red',        (0.55, 0.02, 0.02), 0.45)
ORANGE = mat('Orange',     (0.90, 0.30, 0.02), 0.45)
PLAST  = mat('Plastic',    (0.060, 0.062, 0.068), 0.75)
BLACK  = mat('Black',      (0.012, 0.012, 0.013), 0.85)
RIM    = mat('Steel',      (0.42, 0.43, 0.44), 0.45, metal=0.3)
GLASS  = mat('Glass',      (0.22, 0.32, 0.36), 0.05, alpha=0.35)
LAMP   = mat('Lamp',       (0.85, 0.85, 0.80), 0.2, emit=0.15)
# red/blue lenses reuse Red, Lamp; amber reuses Orange (8 materials)

# ------------------------------------------------------------------ helpers
parts = []
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

def boxd(name, x0, x1, d0, d1, z0, z1, m, bev=0.0, segs=2):
    """Box by extents: x, d (front distance), z."""
    x0, x1 = min(x0, x1), max(x0, x1)
    return box(name, ((x0 + x1) / 2, Y((d0 + d1) / 2), (z0 + z1) / 2), (x1 - x0, d1 - d0, z1 - z0), m, bev, segs=segs)

def cyl(name, c, r, depth, axis, m, verts=32, bev=0.0, segs=2, rot=None, r2=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=verts, radius1=r,
                          radius2=r if r2 is None else r2, depth=depth)
    o = new_obj(name, bm); o.location = c
    o.rotation_euler = rot or {'X': (0, math.pi / 2, 0), 'Y': (math.pi / 2, 0, 0), 'Z': (0, 0, 0)}[axis]
    return keep(bevel(o, bev, segs), m)

def prism_x(name, pts, x0, x1, m, bev=0.0, segs=2, keep_it=True):
    """Side profile pts [(d, z)] extruded across X from x0 to x1."""
    bm = bmesh.new()
    vs = [bm.verts.new((x0, Y(d), z)) for d, z in pts]
    f = bm.faces.new(vs)
    r = bmesh.ops.extrude_face_region(bm, geom=[f])
    for v in [e for e in r['geom'] if isinstance(e, bmesh.types.BMVert)]: v.co.x = x1
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = new_obj(name, bm)
    bevel(o, bev, segs)
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

# ------------------------------------------------------------------ dimensions
CHW = 0.99                       # cab half width
BHW = 1.10                       # box half width
WR, WZ, WT = 0.39, 0.39, 0.25
WD = [0.98, 4.62]                # wheel centres (d)
BOX0, BOX1 = 2.20, 5.86          # patient box front/back (d)
BZ0, BZ1 = 0.70, 2.56            # patient box bottom/top
BELT = 1.24

# ------------------------------------------------------------------ cab (van front)
cab = prism_x('Cab', [(0.08, 0.50), (0.05, 1.05), (0.10, 1.24), (0.50, 1.36), (1.25, 2.24), (1.36, 2.30),
                      (2.26, 2.30), (2.26, 0.50)], -CHW, CHW, WHITE, bev=0.04, segs=3)
cut(cab, cutter_box((0, Y(1.60), 1.60), (1.80, 1.16, 1.04)))           # hollow cab
# windshield opening, side windows
cut(cab, prism_x('wscut', [(0.30, 1.42), (1.05, 2.20), (1.90, 2.20), (1.90, 1.42)], -0.86, 0.86, WHITE, keep_it=False))
WIN = [(1.22, 1.48), (1.22, 2.02), (1.32, 2.14), (2.10, 2.14), (2.10, 1.48)]
for s in (-1, 1):
    cut(cab, prism_x('wincut', WIN, s * 0.6, s * 1.2, WHITE, bev=0.02, keep_it=False))
# wheel arch
def arch(dc, grow=0.0, bot=0.3):
    return [(dc - 0.46 - grow, bot), (dc - 0.42 - grow, 0.72 + grow), (dc - 0.30 - grow * 0.7, 0.85 + grow), (dc - 0.10, 0.89 + grow),
            (dc + 0.10, 0.89 + grow), (dc + 0.30 + grow * 0.7, 0.85 + grow), (dc + 0.42 + grow, 0.72 + grow), (dc + 0.46 + grow, bot)]
for s in (-1, 1):
    cut(cab, prism_x('archcut', arch(WD[0], 0.0, 0.2), s * 0.62, s * 1.2, WHITE, keep_it=False))
    prism_x('Liner', arch(WD[0], 0.0, 0.46), s * 0.60, s * 0.63, BLACK)
    a, b = (CHW - 0.02, CHW + 0.04) if s > 0 else (-(CHW + 0.04), -(CHW - 0.02))
    prism_x('Flare', arch(WD[0], 0.06, 0.55) + arch(WD[0], 0.0, 0.55)[::-1], a, b, PLAST, bev=0.015)
# cab side details
for s in (-1, 1):
    x = s * (CHW + 0.001)
    box('DoorLineF', (x, Y(1.16), 1.555), (0.006, 0.01, 1.17), BLACK)
    box('DoorLineR', (x, Y(2.16), 1.40), (0.006, 0.01, 1.70), BLACK)
    box('DoorLineB', (x, Y(1.80), 0.56), (0.006, 0.72, 0.01), BLACK)
    box('Handle', (s * (CHW + 0.014), Y(2.00), 1.40), (0.03, 0.16, 0.04), PLAST, bev=0.01)
    box('MirrorArm', (s * (CHW + 0.06), Y(1.10), 1.62), (0.12, 0.05, 0.04), PLAST, bev=0.01)
    box('Mirror', (s * (CHW + 0.13), Y(1.10), 1.72), (0.06, 0.12, 0.30), PLAST, bev=0.02, segs=3)
    box('MirrorGlass', (s * (CHW + 0.13), Y(1.037), 1.72), (0.045, 0.006, 0.25), GLASS)
    box('Step', (s * (CHW - 0.02), Y(1.66), 0.42), (0.16, 0.70, 0.06), PLAST, bev=0.015)
    # bands along the cab doors (orange over red)
    x = s * (CHW + 0.003)
    boxd('CabRed', x - 0.004, x + 0.004, 0.10, 2.26, 1.10, 1.28, RED)
    boxd('CabOrange', x - 0.004, x + 0.004, 0.10, 2.26, 0.94, 1.10, ORANGE)
# bands wrap the front corners
for s in (-1, 1):
    boxd('CabRedF', s * 0.93, s * (CHW + 0.007), 0.045, 0.10, 1.10, 1.28, RED)
    boxd('CabOrangeF', s * 0.93, s * (CHW + 0.007), 0.045, 0.10, 0.94, 1.10, ORANGE)
# glass
RAKE = math.atan2(1.58 - 1.05, 2.10 - 1.36)
wl = math.hypot(0.53, 0.74)
box('Windshield', (0, Y(0.925), 1.81), (1.74, 1.02, 0.008), GLASS, rot=(math.atan2(0.86, 0.75), 0, 0))
for s in (-1, 1):
    prism_x('SideGlass', WIN, s * (CHW - 0.045), s * (CHW - 0.037), GLASS)
# front: grille, lamps, bumper
F = 0.06
boxd('GrilleFrame', -0.52, 0.52, 0.04, 0.12, 0.64, 0.98, PLAST, bev=0.02)
for z in (0.72, 0.81, 0.90):
    boxd('GrilleBar', -0.46, 0.46, 0.02, 0.05, z - 0.02, z + 0.02, BLACK)
for s in (-1, 1):
    boxd('LampHouse', s * 0.56, s * 0.92, 0.05, 0.16, 0.80, 1.03, PLAST, bev=0.02)
    cyl('Headlight', (s * 0.70, Y(0.035), 0.915), 0.075, 0.03, 'Y', LAMP, 24, 0.012)
    boxd('Amber', s * 0.82, s * 0.90, 0.04, 0.10, 0.85, 0.98, ORANGE, bev=0.008)
    boxd('LampWrap', s * 0.90, s * (CHW + 0.008), 0.06, 0.20, 0.84, 0.94, ORANGE, bev=0.008)
    boxd('LampWrapW', s * 0.90, s * (CHW + 0.008), 0.06, 0.16, 0.94, 1.02, LAMP, bev=0.008)
    # red/blue-free: grille strobes (red), flat
    boxd('GrilleStrobe', s * 0.30 - 0.06, s * 0.30 + 0.06, 0.01, 0.03, 0.555, 0.595, RED)
boxd('BumperF', -1.0, 1.0, 0.00, 0.22, 0.42, 0.64, PLAST, bev=0.04, segs=3)
boxd('Intake', -0.40, 0.40, -0.005, 0.01, 0.47, 0.52, BLACK)
# interior hint
boxd('Dash', -0.90, 0.90, 0.70, 1.10, 1.10, 1.38, PLAST, bev=0.04)
boxd('CabBackWall', -0.90, 0.90, 2.12, 2.16, 0.53, 2.14, PLAST)
boxd('Headliner', -0.90, 0.90, 1.10, 2.16, 2.10, 2.13, PLAST)
for sx in (-0.48, 0.48):
    boxd('SeatBase', sx - 0.25, sx + 0.25, 1.60, 2.00, 0.78, 0.94, PLAST, bev=0.04)
    boxd('SeatBack', sx - 0.25, sx + 0.25, 1.92, 2.04, 0.94, 1.62, PLAST, bev=0.04)
SWC = (0.48, Y(1.30), 1.42)
torus('SteeringWheel', SWC, 0.19, 0.018, BLACK, rot=(math.radians(-55), 0, 0), maj=24, mnr=6)
boxd('CabFloor', -0.95, 0.95, 1.00, 2.14, 0.50, 0.53, PLAST)

# ------------------------------------------------------------------ patient box
body = boxd('Box', -BHW, BHW, BOX0, BOX1, BZ0, BZ1, WHITE, bev=0.06, segs=3)
boxd('BoxSkirt', -BHW + 0.02, BHW - 0.02, BOX0 + 0.02, BOX1 - 0.02, 0.52, BZ0 + 0.04, PLAST, bev=0.02)
for s in (-1, 1):
    cut(body, prism_x('archcut', arch(WD[1], 0.03, 0.2), s * 0.70, s * 1.3, WHITE, keep_it=False))
    prism_x('Liner', arch(WD[1], 0.03, 0.46), s * 0.70, s * 0.73, BLACK)
    a, b = (BHW - 0.01, BHW + 0.04) if s > 0 else (-(BHW + 0.04), -(BHW - 0.01))
    prism_x('Flare', arch(WD[1], 0.09, 0.62) + arch(WD[1], 0.03, 0.62)[::-1], a, b, PLAST, bev=0.015)
# box skirt cut too
for o, m in parts:
    if o.name.startswith('BoxSkirt'):
        for s in (-1, 1):
            cut(o, prism_x('archcut', arch(WD[1], 0.03, 0.2), s * 0.70, s * 1.3, WHITE, keep_it=False))
# bands: red with orange stripe above, wrapping the sides, rear and front face of the box
RZ0, RZ1, OZ0, OZ1 = 1.10, 1.28, 0.94, 1.10
for s in (-1, 1):
    x = s * (BHW + 0.004)
    boxd('BandRed', x - 0.004, x + 0.004, BOX0 + 0.05, BOX1 - 0.05, RZ0, RZ1, RED)
    boxd('BandOrange', x - 0.004, x + 0.004, BOX0 + 0.05, BOX1 - 0.05, OZ0, OZ1, ORANGE)
boxd('BandRedR', -BHW + 0.05, BHW - 0.05, BOX1 - 0.002, BOX1 + 0.006, RZ0, RZ1, RED)
boxd('BandOrangeR', -BHW + 0.05, BHW - 0.05, BOX1 - 0.002, BOX1 + 0.006, OZ0, OZ1, ORANGE)
# left (+X) side: two compartment doors front and rear of the wheel, handles
def panel(s, d0, d1, z0, z1):
    x = s * (BHW + 0.008)
    for (a, b, c, e) in ((d0, d1, z0, z0 + 0.012), (d0, d1, z1 - 0.012, z1)):
        boxd('Seam', x - 0.004, x + 0.004, a, b, c, e, BLACK)
    for dd in (d0, d1 - 0.012):
        boxd('Seam', x - 0.004, x + 0.004, dd, dd + 0.012, z0, z1, BLACK)
def handle(s, d, z):
    x = s * (BHW + 0.012)
    boxd('Handle', x - 0.012, x + 0.012, d - 0.08, d + 0.08, z - 0.02, z + 0.02, PLAST, bev=0.008)
panel(-1, 2.40, 3.25, 0.78, 2.10); handle(-1, 3.10, 1.45)
panel(-1, 3.31, 3.95, 1.45, 2.10); handle(-1, 3.60, 1.60)
panel(-1, 5.18, 5.76, 0.78, 2.10); handle(-1, 5.30, 1.45)
# left (+X) side: entry door with window, big window over the rear wheel
panel(1, 2.95, 3.70, 0.76, 2.30); handle(1, 3.06, 1.48)
boxd('DoorWinF', BHW, BHW + 0.012, 3.13, 3.53, 1.72, 2.12, PLAST, bev=0.01)
boxd('DoorWin', BHW, BHW + 0.016, 3.16, 3.50, 1.75, 2.09, GLASS)
boxd('BigWinF', BHW, BHW + 0.012, 4.36, 5.36, 1.72, 2.14, PLAST, bev=0.01)
boxd('BigWin', BHW, BHW + 0.016, 4.39, 5.33, 1.75, 2.11, GLASS)
# rear: two doors with windows, step bumper, tail lights
boxd('RearSeam', -0.006, 0.006, BOX1, BOX1 + 0.006, 0.76, 2.36, BLACK)
boxd('RearDoorTop', -0.95, 0.95, BOX1, BOX1 + 0.006, 2.36, 2.372, BLACK)
for sx in (-1, 1):
    xc = sx * 0.50
    boxd('RearWinF', xc - 0.30, xc + 0.30, BOX1 - 0.001, BOX1 + 0.006, 1.66, 2.22, BLACK)
    boxd('RearWin', xc - 0.26, xc + 0.26, BOX1, BOX1 + 0.010, 1.70, 2.18, GLASS)
    boxd('RearHandle', sx * 0.10 - 0.02, sx * 0.10 + 0.02, BOX1 + 0.005, BOX1 + 0.03, 1.30, 1.50, PLAST)
    boxd('TailRed', sx * 1.02 - 0.06, sx * 1.02 + 0.06, BOX1 - 0.01, BOX1 + 0.02, 0.85, 1.05 - 0.10, RED, bev=0.01)
    boxd('TailAmber', sx * 1.02 - 0.06, sx * 1.02 + 0.06, BOX1 - 0.01, BOX1 + 0.02, 0.76, 0.84, ORANGE, bev=0.01)
    boxd('Reverse', sx * 1.02 - 0.06, sx * 1.02 + 0.06, BOX1 - 0.01, BOX1 + 0.02, 0.96, 1.04, LAMP, bev=0.01)
    # upper rear warning lights
    boxd('RearBeacon', sx * 0.92 - 0.11, sx * 0.92 + 0.11, BOX1 - 0.01, BOX1 + 0.03, 2.38, 2.50, RED, bev=0.015)
    boxd('RearAmber', sx * 0.66 - 0.08, sx * 0.66 + 0.08, BOX1 - 0.01, BOX1 + 0.03, 2.38, 2.50, ORANGE, bev=0.015)
boxd('RearStep', -0.95, 0.95, BOX1 - 0.10, BOX1 + 0.18, 0.50, 0.62, PLAST, bev=0.02)
boxd('RearStepPad', -0.90, 0.90, BOX1 - 0.05, BOX1 + 0.16, 0.62, 0.63, BLACK)
# front face of the box above the cab: warning lights
for sx in (-1, 1):
    boxd('FrontBeacon', sx * 0.92 - 0.11, sx * 0.92 + 0.11, BOX0 - 0.03, BOX0 + 0.01, 2.38, 2.50, RED, bev=0.015)
    boxd('FrontAmber', sx * 0.66 - 0.08, sx * 0.66 + 0.08, BOX0 - 0.03, BOX0 + 0.01, 2.38, 2.50, ORANGE, bev=0.015)
# side corner warning lights
for s in (-1, 1):
    x = s * (BHW + 0.01)
    for d, m in ((BOX0 + 0.18, RED), (BOX0 + 0.42, ORANGE), (BOX1 - 0.42, ORANGE), (BOX1 - 0.18, RED)):
        boxd('SideBeacon', x - 0.02, x + 0.02, d - 0.10, d + 0.10, 2.38, 2.50, m, bev=0.012)
    boxd('SideMarker', s * (BHW + 0.01) - 0.015, s * (BHW + 0.01) + 0.015, 4.95 - 0.04, 4.95 + 0.04, 0.68, 0.73, ORANGE)
# roof: AC unit and vent, cab-roof light bar
boxd('RoofAC', -0.40, 0.40, 3.6, 4.4, BZ1 - 0.02, BZ1 + 0.04, WHITE, bev=0.02)
boxd('RoofVent', -0.25, 0.25, 4.9, 5.3, BZ1 - 0.02, BZ1 + 0.035, PLAST, bev=0.015)
# light bar on the front edge of the box roof: red / white / red
B0, B1 = BOX0 + 0.08, BOX0 + 0.48
for sx in (-0.55, 0.55):
    boxd('BarFoot', sx - 0.05, sx + 0.05, B0 + 0.08, B1 - 0.08, BZ1 - 0.02, BZ1 + 0.04, BLACK)
boxd('BarBody', -0.88, 0.88, B0, B1, BZ1 + 0.04, BZ1 + 0.065, BLACK, bev=0.01)
for sx0, sx1, m in ((-0.88, -0.24, RED), (-0.22, 0.22, LAMP), (0.24, 0.88, RED)):
    boxd('BarLens', sx0, sx1, B0 + 0.01, B1 - 0.01, BZ1 + 0.06, BZ1 + 0.14, m, bev=0.025, segs=3)

# ------------------------------------------------------------------ chassis
for s in (-1, 1):
    boxd('Rail', s * 0.42 - 0.05, s * 0.42 + 0.05, 0.6, 5.6, 0.40, 0.55, BLACK)
for dc in WD:
    cyl('Axle', (0, Y(dc), WZ), 0.05, 1.5, 'X', BLACK, 12)
boxd('FuelTank', 0.45, 0.85, 2.6, 3.4, 0.33, 0.55, BLACK)
cyl('Exhaust', (-0.55, Y(4.0), 0.36), 0.035, 3.2, 'Y', BLACK, 12)

# ------------------------------------------------------------------ wheels (steel rims, dual rear)
def wheel(c, axis_dir, dish=0.0):
    ax = Vector(axis_dir)
    rot = ax.to_track_quat('Z', 'Y').to_euler()
    M = Matrix.Translation(c) @ rot.to_matrix().to_4x4()
    R = tuple(rot)
    def p(z, x=0.0, y=0.0): return (M @ Vector((x, y, z)))
    o = WT / 2
    cyl('Tyre', c, WR, WT, 'Z', BLACK, 32, 0.06, 2, rot=R)
    cyl('RimWell', p(o - 0.004), 0.25, 0.02, 'Z', PLAST, 32, rot=R)
    torus('RimLip', p(o + 0.002), 0.245, 0.014, RIM, rot=R, maj=32, mnr=6)
    cyl('RimFace', p(o - dish), 0.21, 0.02, 'Z', RIM, 32, 0.006, 1, rot=R)
    for k in range(8):
        a = k * math.pi / 4
        cyl('Vent', p(o - dish + 0.008, 0.15 * math.cos(a), 0.15 * math.sin(a)), 0.03, 0.01, 'Z', BLACK, 12, rot=R)
    cyl('Hub', p(o - dish + 0.02), 0.085, 0.04, 'Z', RIM, 24, 0.01, 1, rot=R)
    for k in range(8):
        a = k * math.pi / 4 + math.pi / 8
        cyl('Lug', p(o - dish + 0.04, 0.065 * math.cos(a), 0.065 * math.sin(a)), 0.011, 0.02, 'Z', BLACK, 6, rot=R)
for s in (-1, 1):
    wheel(Vector((s * 0.82, Y(WD[0]), WZ)), (s, 0, 0))
    wheel(Vector((s * 0.88, Y(WD[1]), WZ)), (s, 0, 0), dish=0.03)
    cyl('InnerTyre', (s * 0.62, Y(WD[1]), WZ), WR, WT, 'X', BLACK, 32, 0.06)

# ------------------------------------------------------------------ merge into one mesh with fixed material slots
MAT_ORDER = list(MATS.keys())
dg = bpy.context.evaluated_depsgraph_get()
TRI = {}
bm = bmesh.new()
for o, m in parts:
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
    me.transform(o.matrix_world)
    idx = MAT_ORDER.index(m)
    for p in me.polygons: p.material_index = idx
    TRI[o.name.split('.')[0]] = TRI.get(o.name.split('.')[0], 0) + sum(len(p.vertices) - 2 for p in me.polygons)
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)
print('[parts]', sorted(TRI.items(), key=lambda kv: -kv[1])[:20])
for f in bm.faces: f.smooth = True
for e in bm.edges:
    e.smooth = e.is_manifold and e.calc_face_angle(math.pi) < math.radians(40)
used = sorted({f.material_index for f in bm.faces})
remap = {old: new for new, old in enumerate(used)}
for f in bm.faces: f.material_index = remap[f.material_index]
bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
me = bpy.data.meshes.new(NAME + '_Mesh'); bm.to_mesh(me); bm.free()
for i in used: me.materials.append(MATS[MAT_ORDER[i]])
for o, _ in parts: bpy.data.objects.remove(o)
for o in cutters: bpy.data.objects.remove(o)
body = bpy.data.objects.new(NAME + '_Mesh', me); scene.collection.objects.link(body)

tris = sum(len(p.vertices) - 2 for p in me.polygons)
xs = [v.co.x for v in me.vertices]; ys = [v.co.y for v in me.vertices]; zs = [v.co.z for v in me.vertices]
print(f'[{NAME}] triangles {tris}, materials {len(me.materials)} {[m.name for m in me.materials]}')
print(f'[{NAME}] size x {max(xs)-min(xs):.2f} y {max(ys)-min(ys):.2f} z {max(zs)-min(zs):.2f}  '
      f'y {min(ys):.2f}..{max(ys):.2f} x {min(xs):.2f}..{max(xs):.2f} z {min(zs):.2f}..{max(zs):.2f}')

root = bpy.data.objects.new(NAME, None); scene.collection.objects.link(root); body.parent = root
seat = bpy.data.objects.new('Seat', None); seat.location = (0.48, Y(1.80), 0.96)   # driver seat (left-hand drive, +X)
scene.collection.objects.link(seat); seat.parent = root
for o in scene.objects: o.select_set(o in (root, body, seat))
bpy.ops.export_scene.fbx(filepath=f'{OUT}/{NAME}.fbx', use_selection=True, apply_unit_scale=True,
                         apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)

# ------------------------------------------------------------------ previews
world = bpy.data.worlds.new('W'); scene.world = world; world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.70, 0.70, 0.71, 1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.0
bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, 0)); ground = bpy.context.active_object
gm = bpy.data.materials.new('Ground'); gm.use_nodes = True
gb = gm.node_tree.nodes['Principled BSDF']
gb.inputs['Base Color'].default_value = (0.08, 0.08, 0.08, 1); gb.inputs['Roughness'].default_value = 1.0
gb.inputs['Emission Color'].default_value = (0.70, 0.70, 0.71, 1); gb.inputs['Emission Strength'].default_value = 0.72
ground.data.materials.append(gm)
bpy.ops.object.light_add(type='SUN', location=(0, 0, 10)); sun = bpy.context.active_object
sun.data.energy = 2.4; sun.data.angle = math.radians(25)
scene.render.engine = 'BLENDER_EEVEE'
scene.eevee.taa_render_samples = 48
scene.render.resolution_x, scene.render.resolution_y = 1672, 941
scene.view_settings.view_transform = 'Standard'
cam_data = bpy.data.cameras.new('Cam'); cam = bpy.data.objects.new('Cam', cam_data)
scene.collection.objects.link(cam); scene.camera = cam

def shoot(name, loc, target, lens=50, ortho=None):
    cam.location = loc
    d = Vector(target) - Vector(loc); cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    if ortho: cam_data.type = 'ORTHO'; cam_data.ortho_scale = ortho
    else: cam_data.type = 'PERSP'; cam_data.lens = lens
    scene.render.filepath = f'{OUT}/{name}.png'; bpy.ops.render.render(write_still=True)

CAM34 = (6.9, -7.6, 3.9)          # front-left (+X), ~40 deg off the nose
sun.rotation_euler = (math.radians(38), 0, math.radians(150))
shoot('render-34', CAM34, (0.0, 0.30, 1.20), 41)
sun.rotation_euler = (math.radians(30), 0, math.radians(60))
shoot('render-side', (20, 0.02, 1.58), (0, 0.02, 1.58), ortho=6.75)

# ------------------------------------------------------------------ compare.jpg (reference left, render right)
import numpy as np, os
W, H = 836, 470
def tile(path):
    im = bpy.data.images.load(path); im.scale(W, H)
    a = np.empty(W * H * 4, dtype=np.float32); im.pixels.foreach_get(a)
    return a.reshape(H, W, 4)
views = [v for v in ('34', 'side') if os.path.exists(f'{OUT}/ref-{v}.png')]
grid = np.ones((H * len(views), W * 2, 4), dtype=np.float32)
for row, view in enumerate(views):
    r = len(views) - 1 - row
    grid[r * H:(r + 1) * H, 0:W] = tile(f'{OUT}/ref-{view}.png')
    grid[r * H:(r + 1) * H, W:2 * W] = tile(f'{OUT}/render-{view}.png')
cmp = bpy.data.images.new('compare', W * 2, H * len(views))
cmp.pixels.foreach_set(grid.ravel())
cmp.filepath_raw = f'{OUT}/compare.jpg'; cmp.file_format = 'JPEG'
cmp.save()
print(f'[{NAME}] done')

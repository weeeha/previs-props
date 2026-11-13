# Medium delivery box truck: cab-over cab plus cargo box with a roll-up rear door (own design), library round.
# Blender 5.1 headless:  Blender -b --python make_boxtruck.py -- <out dir>
# d = metres back from the front bumper tip. Front toward -Y, up +Z, origin on the ground at the footprint centre.
import bpy, sys, math, bmesh
from mathutils import Vector, Matrix

OUT = sys.argv[sys.argv.index('--') + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

NAME = 'BoxTruck'
LEN = 7.50
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

BLUE   = mat('PaintBlue',  (0.020, 0.13, 0.55), 0.45)
WHITE  = mat('PaintWhite', (0.80, 0.80, 0.78), 0.5)
RED    = mat('Red',        (0.55, 0.02, 0.02), 0.45)
ORANGE = mat('Orange',     (0.90, 0.30, 0.02), 0.45)
PLAST  = mat('Plastic',    (0.060, 0.062, 0.068), 0.75)
BLACK  = mat('Black',      (0.012, 0.012, 0.013), 0.85)
STEEL  = mat('Steel',      (0.42, 0.43, 0.44), 0.45, metal=0.3)
GLASS  = mat('Glass',      (0.22, 0.32, 0.36), 0.05, alpha=0.35)
LAMP   = WHITE                                   # lamp lenses reuse PaintWhite to stay within 8 materials

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
CHW = 1.10                       # cab half width
BHW = 1.20                       # cargo box half width
WR, WZ, WT = 0.48, 0.48, 0.26
WD = [1.35, 5.75]                # wheel centres (d)
BOX0, BOX1 = 2.10, 7.40          # cargo box front/back (d)
BZ0, BZ1 = 1.08, 3.30            # cargo box bottom/top

# ------------------------------------------------------------------ cab-over cab
cab = prism_x('Cab', [(0.10, 0.62), (0.05, 1.58), (0.10, 1.72), (0.22, 2.64), (0.36, 2.80), (1.98, 2.80), (2.00, 0.62)],
              -CHW, CHW, BLUE, bev=0.05, segs=3)
cut(cab, cutter_box((0, Y(1.15), 2.00), (2.00, 1.66, 1.40)))                    # hollow: d 0.32..1.98, z 1.30..2.70
cut(cab, prism_x('wscut', [(-0.2, 1.76), (-0.2, 2.56), (0.6, 2.56), (0.6, 1.76)], -0.98, 0.98, BLUE, keep_it=False))
WIN = [(0.44, 1.78), (0.44, 2.58), (1.50, 2.58), (1.50, 1.98), (1.20, 1.78)]
for s in (-1, 1):
    cut(cab, prism_x('wincut', WIN, s * 0.6, s * 1.3, BLUE, bev=0.02, keep_it=False))
def arch(dc, grow=0.0, bot=0.3):
    return [(dc - 0.56 - grow, bot), (dc - 0.52 - grow, 0.90 + grow), (dc - 0.38 - grow * 0.7, 1.05 + grow), (dc - 0.12, 1.10 + grow),
            (dc + 0.12, 1.10 + grow), (dc + 0.38 + grow * 0.7, 1.05 + grow), (dc + 0.52 + grow, 0.90 + grow), (dc + 0.56 + grow, bot)]
for s in (-1, 1):
    cut(cab, prism_x('archcut', arch(WD[0], 0.0, 0.2), s * 0.70, s * 1.3, BLUE, keep_it=False))
    prism_x('Liner', arch(WD[0], 0.0, 0.62), s * 0.68, s * 0.71, BLACK)
    a, b = (CHW - 0.02, CHW + 0.05) if s > 0 else (-(CHW + 0.05), -(CHW - 0.02))
    prism_x('Flare', arch(WD[0], 0.07, 0.66) + arch(WD[0], 0.0, 0.66)[::-1], a, b, PLAST, bev=0.015)
# glass
TILT = math.atan2(0.12, 0.92)
box('Windshield', (0, Y(0.125), 2.16), (1.98, 0.008, 0.80), GLASS, rot=(-TILT, 0, 0))
for s in (-1, 1):
    prism_x('SideGlass', WIN, s * (CHW - 0.055), s * (CHW - 0.047), GLASS)
    x = s * (CHW + 0.001)
    box('DoorLineF', (x, Y(0.38), 1.70), (0.006, 0.01, 1.70), BLACK)
    boxd('DoorLineR', x - 0.003, x + 0.003, 1.56, 1.57, 1.12, 2.66, BLACK)
    boxd('DoorLineB', x - 0.003, x + 0.003, 1.10, 1.57, 1.12, 1.13, BLACK)
    boxd('Handle', s * CHW, s * (CHW + 0.03), 1.30, 1.46, 1.66, 1.70, PLAST, bev=0.008)
    # mirror on a tube arm
    boxd('MirrorArm', s * CHW, s * (CHW + 0.15), 0.30, 0.34, 2.40, 2.43, PLAST)
    boxd('MirrorArmL', s * CHW, s * (CHW + 0.15), 0.30, 0.34, 1.86, 1.89, PLAST)
    boxd('MirrorPost', s * (CHW + 0.13), s * (CHW + 0.16), 0.30, 0.34, 1.86, 2.43, PLAST)
    boxd('Mirror', s * (CHW + 0.11), s * (CHW + 0.19), 0.24, 0.40, 1.92, 2.38, PLAST, bev=0.025, segs=3)
    boxd('MirrorGlass', s * (CHW + 0.12), s * (CHW + 0.18), 0.40, 0.408, 1.95, 2.35, GLASS)
    # cab entry steps
    boxd('Step', s * (CHW - 0.20), s * (CHW + 0.01), 0.30, 0.80, 0.50, 0.55, PLAST)
    boxd('Step2', s * (CHW - 0.20), s * (CHW + 0.01), 0.30, 0.80, 0.82, 0.86, PLAST)
    boxd('StepSide', s * (CHW - 0.01), s * (CHW + 0.01), 0.30, 0.32, 0.50, 0.86, PLAST)
    boxd('StepSide', s * (CHW - 0.01), s * (CHW + 0.01), 0.78, 0.80, 0.50, 0.86, PLAST)
    boxd('CabMarker', s * (CHW - 0.15), s * (CHW - 0.05), 0.30, 0.40, 2.80, 2.83, ORANGE, bev=0.01)
# front face: grille, lamps, bumper, wipers
boxd('GrilleFrame', -0.62, 0.62, 0.02, 0.10, 0.96, 1.40, PLAST, bev=0.025)
for z in (1.05, 1.13, 1.21, 1.29):
    boxd('GrilleBar', -0.56, 0.56, 0.00, 0.04, z - 0.025, z + 0.025, BLACK)
for s in (-1, 1):
    boxd('LampHouse', s * 0.68, s * 1.06, 0.03, 0.12, 0.98, 1.24, PLAST, bev=0.02)
    boxd('Headlight', s * 0.72, s * 0.94, 0.02, 0.05, 1.01, 1.21, LAMP, bev=0.015)
    boxd('Amber', s * 0.95, s * 1.04, 0.02, 0.06, 1.01, 1.21, ORANGE, bev=0.012)
    boxd('AmberSide', s * (CHW - 0.02), s * (CHW + 0.006), 0.10, 0.24, 1.01, 1.21, ORANGE, bev=0.01)
    box('Wiper', (s * 0.42, Y(0.10), 1.80), (0.65, 0.025, 0.02), BLACK, rot=(0, -s * math.radians(12), 0))
boxd('BumperF', -1.12, 1.12, -0.02, 0.24, 0.56, 0.90, PLAST, bev=0.04, segs=3)
boxd('BumperSlot', -0.70, 0.70, -0.025, 0.0, 0.68, 0.74, BLACK)
for s in (-1, 1):
    boxd('Fog', s * 0.78, s * 0.98, -0.025, 0.0, 0.66, 0.76, LAMP, bev=0.01)
boxd('RoofMarkers', -0.30, 0.30, 0.32, 0.40, 2.80, 2.83, ORANGE, bev=0.01)
# interior
boxd('Dash', -1.00, 1.00, 0.30, 0.62, 1.30, 1.78, PLAST, bev=0.04)
boxd('CabBackWall', -1.0, 1.0, 1.92, 1.96, 1.30, 2.70, PLAST)
boxd('Headliner', -1.0, 1.0, 0.30, 1.96, 2.66, 2.70, PLAST)
for sx in (-0.55, 0.55):
    boxd('SeatBase', sx - 0.26, sx + 0.26, 1.10, 1.55, 1.58, 1.74, PLAST, bev=0.04)
    boxd('SeatBack', sx - 0.26, sx + 0.26, 1.50, 1.64, 1.74, 2.42, PLAST, bev=0.04)
    boxd('SeatRiser', sx - 0.22, sx + 0.22, 1.12, 1.50, 1.30, 1.58, PLAST)
SWC = (0.55, Y(0.80), 2.02)
torus('SteeringWheel', SWC, 0.22, 0.02, BLACK, rot=(math.radians(-30), 0, 0), maj=24, mnr=6)
cyl('Column', (0.55, Y(0.68), 1.86), 0.035, 0.40, 'Y', BLACK, 12, rot=(math.radians(60) + math.pi / 2, 0, 0))

# ------------------------------------------------------------------ cargo box
boxd('Box', -BHW, BHW, BOX0, BOX1, BZ0, BZ1, WHITE, bev=0.03, segs=2)
T = 0.07                                         # trim profile
for sx in (-1, 1):
    for d in (BOX0, BOX1):                       # vertical corner posts
        dd = (d - 0.02, d + T) if d == BOX0 else (d - T, d + 0.02)
        boxd('Post', sx * (BHW - T), sx * (BHW + 0.02), dd[0], dd[1], BZ0 - 0.02, BZ1 + 0.02, STEEL, bev=0.012)
    for z0, z1 in ((BZ1 - 0.08, BZ1 + 0.02), (BZ0 - 0.02, BZ0 + 0.12)):   # top and bottom rails
        boxd('Rail', sx * (BHW - 0.02), sx * (BHW + 0.025), BOX0, BOX1, z0, z1, STEEL, bev=0.012)
    # side panel seams (thin insets)
    for d in (3.42, 4.75, 6.08):
        boxd('Seam', sx * (BHW - 0.002), sx * (BHW + 0.004), d - 0.006, d + 0.006, BZ0 + 0.12, BZ1 - 0.08, STEEL)
    # amber side markers
    for d in (BOX0 + 0.15, (BOX0 + BOX1) / 2, BOX1 - 0.15):
        boxd('SideMarker', sx * (BHW + 0.02), sx * (BHW + 0.035), d - 0.05, d + 0.05, BZ0 + 0.04, BZ0 + 0.09, ORANGE, bev=0.008)
    for d in (BOX0 + 0.15, BOX1 - 0.15):
        boxd('TopMarker', sx * (BHW + 0.02), sx * (BHW + 0.035), d - 0.05, d + 0.05, BZ1 - 0.07, BZ1 - 0.02, ORANGE, bev=0.008)
for d in (BOX0, BOX1):                            # front/rear top and bottom rails
    dd = (d - 0.03, d + 0.02) if d == BOX1 else (d - 0.02, d + 0.03)
    boxd('RailX', -BHW, BHW, dd[0], dd[1], BZ1 - 0.08, BZ1 + 0.02, STEEL, bev=0.012)
    boxd('RailX', -BHW, BHW, dd[0], dd[1], BZ0 - 0.02, BZ0 + 0.12, STEEL, bev=0.012)
boxd('RoofSeam', -BHW + 0.05, BHW - 0.05, BOX0 + 0.05, BOX1 - 0.05, BZ1, BZ1 + 0.004, WHITE)
# rear roll-up door: frame, slats, handle
R = BOX1
boxd('DoorFrame', -BHW + 0.02, BHW - 0.02, R - 0.01, R + 0.04, BZ1 - 0.22, BZ1 - 0.06, STEEL, bev=0.012)
for sx in (-1, 1):
    boxd('DoorJamb', sx * (BHW - 0.14), sx * (BHW - 0.02), R - 0.01, R + 0.04, BZ0 + 0.10, BZ1 - 0.06, STEEL, bev=0.012)
boxd('DoorBack', -BHW + 0.14, BHW - 0.14, R - 0.01, R + 0.012, BZ0 + 0.10, BZ1 - 0.22, BLACK)
NS = 14
h = (BZ1 - 0.22 - (BZ0 + 0.12)) / NS
for k in range(NS):
    z0 = BZ0 + 0.12 + k * h
    boxd('Slat', -BHW + 0.15, BHW - 0.15, R, R + 0.03, z0 + 0.008, z0 + h - 0.008, STEEL, bev=0.008, segs=1)
boxd('DoorHandle', -0.18, 0.18, R + 0.03, R + 0.06, BZ0 + 0.20, BZ0 + 0.25, PLAST, bev=0.01)
boxd('DoorLatch', -0.04, 0.04, R + 0.03, R + 0.065, BZ0 + 0.12, BZ0 + 0.30, BLACK)
boxd('DoorStrap', 0.38, 0.42, R + 0.03, R + 0.045, BZ0 + 0.12, BZ0 + 0.70, BLACK)

# ------------------------------------------------------------------ chassis, rear end
for s in (-1, 1):
    boxd('FrameRail', s * 0.38, s * 0.48, 0.30, BOX1 - 0.05, 0.62, 0.86, BLACK)
for d in [BOX0 + 0.1 + 0.55 * k for k in range(10)]:
    boxd('CrossSill', -BHW + 0.04, BHW - 0.04, d - 0.05, d + 0.05, 0.86, BZ0, BLACK)
boxd('Subframe', -0.55, 0.55, BOX0, BOX1, 0.86, 0.98, BLACK)
for dc in WD:
    cyl('Axle', (0, Y(dc), WZ), 0.06, 1.70, 'X', BLACK, 12)
cyl('Diff', (0, Y(WD[1]), WZ), 0.17, 0.24, 'Y', BLACK, 12, 0.02, 1)
# fuel tank (+X) and battery box (-X)
cyl('FuelTank', (0.80, Y(2.75), 0.70), 0.24, 0.90, 'Y', BLACK, 24, 0.03)
boxd('TankStrap', 0.55, 1.05, 2.45, 2.49, 0.45, 0.95, PLAST)
boxd('TankStrap', 0.55, 1.05, 3.01, 3.05, 0.45, 0.95, PLAST)
boxd('BatteryBox', -1.02, -0.55, 2.30, 2.90, 0.50, 0.86, PLAST, bev=0.02)
# side guards between the axles
for s in (-1, 1):
    for z in (0.50, 0.72):
        boxd('Guard', s * (BHW - 0.10), s * (BHW - 0.04), 3.25, 5.10, z - 0.04, z + 0.04, STEEL, bev=0.01)
    for d in (3.40, 4.20, 5.00):
        boxd('GuardPost', s * (BHW - 0.12), s * (BHW - 0.06), d - 0.03, d + 0.03, 0.46, BZ0, BLACK)
    boxd('MudFlap', s * (BHW - 0.36), s * (BHW - 0.02), 6.32, 6.34, 0.20, 0.86, BLACK)
cyl('Exhaust', (-0.62, Y(2.6), 0.60), 0.05, 1.6, 'Y', BLACK, 12)
cyl('ExhaustTip', (-0.62, Y(3.42), 0.56), 0.06, 0.12, 'Y', STEEL, 16)
# rear underride bar and lights
boxd('Underride', -1.10, 1.10, BOX1 - 0.02, BOX1 + 0.08, 0.46, 0.62, PLAST, bev=0.02)
for s in (-1, 1):
    boxd('UnderPost', s * 0.48, s * 0.58, BOX1 - 0.40, BOX1 + 0.02, 0.56, 0.86, PLAST)
    boxd('TailHouse', s * 0.80, s * 1.14, BOX1 - 0.05, BOX1 + 0.06, 0.74, 0.96, BLACK, bev=0.015)
    boxd('TailRed', s * 0.86, s * 1.08, BOX1 + 0.05, BOX1 + 0.075, 0.86, 0.94, RED, bev=0.008)
    boxd('TailAmber', s * 0.86, s * 1.08, BOX1 + 0.05, BOX1 + 0.075, 0.76, 0.84, ORANGE, bev=0.008)
    boxd('RearCornerRed', s * (BHW - 0.05), s * (BHW + 0.01), R + 0.03, R + 0.06, BZ1 - 0.16, BZ1 - 0.10, RED, bev=0.008)
boxd('Plate', -0.16, 0.16, BOX1 + 0.05, BOX1 + 0.07, 0.66, 0.80, WHITE)

# ------------------------------------------------------------------ wheels (steel rims, dual rear)
def wheel(c, axis_dir, dish=0.0):
    ax = Vector(axis_dir)
    rot = ax.to_track_quat('Z', 'Y').to_euler()
    M = Matrix.Translation(c) @ rot.to_matrix().to_4x4()
    Rr = tuple(rot)
    def p(z, x=0.0, y=0.0): return (M @ Vector((x, y, z)))
    o = WT / 2
    cyl('Tyre', c, WR, WT, 'Z', BLACK, 32, 0.07, 2, rot=Rr)
    cyl('RimWell', p(o - 0.004), 0.31, 0.02, 'Z', PLAST, 32, rot=Rr)
    torus('RimLip', p(o + 0.002), 0.305, 0.016, STEEL, rot=Rr, maj=32, mnr=6)
    cyl('RimFace', p(o - dish), 0.27, 0.02, 'Z', STEEL, 32, 0.006, 1, rot=Rr)
    for k in range(6):
        a = k * math.pi / 3
        cyl('Vent', p(o - dish + 0.008, 0.19 * math.cos(a), 0.19 * math.sin(a)), 0.04, 0.01, 'Z', BLACK, 12, rot=Rr)
    cyl('Hub', p(o - dish + 0.03), 0.11, 0.06, 'Z', STEEL, 24, 0.015, 1, rot=Rr)
    for k in range(8):
        a = k * math.pi / 4 + math.pi / 8
        cyl('Lug', p(o - dish + 0.05, 0.085 * math.cos(a), 0.085 * math.sin(a)), 0.013, 0.025, 'Z', BLACK, 6, rot=Rr)
for s in (-1, 1):
    wheel(Vector((s * 0.92, Y(WD[0]), WZ)), (s, 0, 0))
    wheel(Vector((s * 0.95, Y(WD[1]), WZ)), (s, 0, 0), dish=0.03)
    cyl('InnerTyre', (s * 0.68, Y(WD[1]), WZ), WR, WT, 'X', BLACK, 32, 0.07)

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
seat = bpy.data.objects.new('Seat', None); seat.location = (0.55, Y(1.32), 1.74)   # driver seat (left-hand drive, +X)
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

CAM34 = (8.6, -9.5, 4.1)          # front-left (+X), ~40 deg off the nose
sun.rotation_euler = (math.radians(38), 0, math.radians(150))
shoot('render-34', CAM34, (0.0, 0.45, 1.55), 49)
sun.rotation_euler = (math.radians(30), 0, math.radians(60))
shoot('render-side', (20, 0.02, 1.96), (0, 0.02, 1.96), ortho=8.35)

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

# Semi truck: conventional tractor (sleeper, 3 axles) + box trailer (2 axles), previs library v3. Own design, no brands.
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_semitruck.py -- <out dir>
# 1 unit = 1 m, front toward -Y, up +Z, origin on the ground at the centre of the footprint.
# FBX holds two roots: `SemiTruck` (tractor + trailer, one mesh) and `SemiTruck_Tractor` (tractor alone, origin at the
# centre of the tractor footprint; the root sits at x = +4 m so the two do not overlap when the file is dropped whole).
import bpy, sys, math, bmesh, os
from mathutils import Vector

OUT = sys.argv[sys.argv.index('--') + 1]
NAME = 'SemiTruck'
L = 16.5
TR_LEN = 8.25          # tractor footprint (front bumper .. rear of frame / mudflaps)

def Y(d):  # distance from the front -> scene Y (front is -Y)
    return d - L / 2

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ---------------------------------------------------------------- materials (8)
MATS = []
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
    MATS.append(m)
    return m

RED = mat('Red', (0.50, 0.025, 0.02), 0.45)
WHITE = mat('PaintWhite', (0.80, 0.80, 0.78), 0.5)
STEEL = mat('Steel', (0.42, 0.43, 0.44), 0.45, metal=0.3)
BLACK = mat('Black', (0.012, 0.012, 0.013), 0.85)
GLASS = mat('Glass', (0.09, 0.13, 0.17), 0.08)
LAMP = mat('Lamp', (0.85, 0.85, 0.80), 0.2, emit=0.15)
AMBER = mat('Orange', (0.90, 0.30, 0.02), 0.45)
TAILL = mat('TailLamp', (0.55, 0.04, 0.02), 0.3, emit=0.3)

# ---------------------------------------------------------------- helpers
GROUP = {'tractor': [], 'trailer': []}
CUR = 'tractor'
def keep(o, m):
    o.data.materials.clear()
    o['mid'] = MATS.index(m)
    GROUP[CUR].append(o)
    return o

def bevel(o, w, segs=2, ang=30):
    b = o.modifiers.new('bevel', 'BEVEL'); b.width = w; b.segments = segs
    b.limit_method = 'ANGLE'; b.angle_limit = math.radians(ang)
    return o

def box(name, c, s, m, bv=0.0, rot=None, segs=2):
    bpy.ops.mesh.primitive_cube_add(size=1, location=c)
    o = bpy.context.active_object; o.name = name; o.scale = s
    if rot: o.rotation_euler = rot
    bpy.ops.object.transform_apply(location=False, scale=True, rotation=True)
    if bv: bevel(o, bv, 1 if bv <= 0.02 else segs)
    return keep(o, m)

def cyl(name, loc, r, depth, axis, m, verts=32, bv=0.0, segs=2, ang=30):
    rot = {'X': (0, math.pi / 2, 0), 'Y': (math.pi / 2, 0, 0), 'Z': (0, 0, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    o = bpy.context.active_object; o.name = name
    bpy.ops.object.transform_apply(location=False, rotation=True)
    if bv: bevel(o, bv, segs, ang)
    return keep(o, m)

def pipe(name, pts, r, m, res=2):
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '3D'
    cu.bevel_depth = r; cu.bevel_resolution = res; cu.use_fill_caps = True
    sp = cu.splines.new('POLY'); sp.points.add(len(pts) - 1)
    for p, q in zip(sp.points, pts): p.co = (*q, 1)
    co = bpy.data.objects.new(name, cu); scene.collection.objects.link(co)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(co.evaluated_get(dg))
    bpy.data.objects.remove(co); bpy.data.curves.remove(cu)
    o = bpy.data.objects.new(name, me); scene.collection.objects.link(o)
    return keep(o, m)

def slab(name, prof, hw, m, xc=0.0, chamfer=0.0, soft=0.0, ang=30):
    """side profile [(d, z)] extruded across X; hw(d, z) half width, xc centre"""
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    L_, R_ = [], []
    for d, z in prof:
        w = hw(d, z) if callable(hw) else hw
        c = xc(d, z) if callable(xc) else xc
        L_.append(bm.verts.new((c - w, Y(d), z))); R_.append(bm.verts.new((c + w, Y(d), z)))
    bm.faces.new(L_); bm.faces.new(list(reversed(R_)))
    n = len(prof)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new([L_[i], R_[i], R_[j], L_[j]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); scene.collection.objects.link(o)
    if chamfer: bevel(o, chamfer, 1, ang)
    if soft: bevel(o, soft, 2, ang)
    return keep(o, m)

def P(d, z, x=0.0):
    return (x, Y(d), z)

def arch(dc, zc, r, a0, a1, n=12):
    return [(dc + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)),
             zc + r * math.sin(math.radians(a0 + (a1 - a0) * k / n))) for k in range(n + 1)]

# ---------------------------------------------------------------- wheels
WR, WT = 0.52, 0.28
def wheel(d, x, full=True):
    s = 1 if x > 0 else -1
    y = Y(d)
    cyl('Tyre', (x, y, WR), WR, WT, 'X', BLACK, 32 if full else 24, 0.07 if full else 0.05, 1)
    if not full:
        return
    o = x + s * WT / 2
    cyl('RimWell', (o + s * 0.004, y, WR), 0.40, 0.016, 'X', BLACK, 32)
    cyl('RimFace', (o + s * 0.014, y, WR), 0.30, 0.016, 'X', STEEL, 32)
    cyl('Hub', (o + s * 0.04, y, WR), 0.14, 0.05, 'X', STEEL, 20, 0.012, 1)
    cyl('HubCap', (o + s * 0.075, y, WR), 0.07, 0.04, 'X', STEEL, 12)
    for k in range(8):
        a = 2 * math.pi * k / 8
        cyl('Lug', (o + s * 0.07, y + 0.105 * math.cos(a), WR + 0.105 * math.sin(a)), 0.014, 0.025, 'X', BLACK, 6)
    for k in range(6):
        a = 2 * math.pi * k / 6 + 0.3
        cyl('Hand', (o + s * 0.020, y + 0.225 * math.cos(a), WR + 0.225 * math.sin(a)), 0.035, 0.008, 'X', BLACK, 8)

def axle(d, dual):
    for s in (-1, 1):
        if dual:
            wheel(d, s * 1.08)
            wheel(d, s * 0.77, full=False)
        else:
            wheel(d, s * 1.06)
    pipe('Axle', [P(d, WR, -0.9), P(d, WR, 0.9)], 0.07, BLACK, res=1)
    if dual:
        box('Diff', P(d, WR), (0.38, 0.38, 0.36), BLACK, 0.06)

# ================================================================= TRACTOR (red)
FRONT_AX = 1.30
DRIVE = (6.25, 7.55)
for d in (FRONT_AX,):
    axle(d, False)
for d in DRIVE:
    axle(d, True)

# frame rails and fifth wheel
for s in (-1, 1):
    box('Rail', P(4.25, 0.92, s * 0.47), (0.10, 7.9, 0.30), BLACK, 0.01)
for d in (2.4, 4.5, 6.9, 8.1):
    box('CrossMember', P(d, 0.92), (0.94, 0.12, 0.22), BLACK)
box('FifthPlate', P(6.9, 1.17), (1.9, 1.40, 0.12), BLACK, 0.03)
box('FifthTop', P(6.9, 1.25), (1.55, 1.15, 0.05), STEEL, 0.02)
slab('FifthSlot', [(6.25, 1.27), (6.95, 1.27), (6.95, 1.29), (6.25, 1.29)], 0.07, BLACK)
for s in (-1, 1):   # quarter fenders over the drive axles and mud flaps
    box('QFender', P(6.9, 1.12, s * 0.93), (0.66, 2.55, 0.05), BLACK, 0.02)
    box('MudFlap', P(8.15, 0.58, s * 0.93), (0.62, 0.025, 0.72), BLACK, 0.01)
    box('FlapBar', P(8.15, 0.98, s * 0.93), (0.66, 0.06, 0.06), STEEL, 0.015)

# front bumper, grille, hood
box('Bumper', P(0.17, 0.66), (2.45, 0.30, 0.40), STEEL, 0.06)
box('BumperSlot', P(0.02, 0.64), (0.85, 0.02, 0.10), BLACK)
box('GrilleSurround', P(0.40, 1.42), (1.20, 0.14, 1.10), STEEL, 0.05)
box('GrilleBack', P(0.33, 1.42), (1.00, 0.04, 0.92), BLACK)
for k in range(8):
    box('GrilleBar', P(0.32, 1.02 + k * 0.115), (1.00, 0.05, 0.035), STEEL, 0.008, segs=1)
box('GrilleCap', P(0.42, 2.00), (1.24, 0.18, 0.08), STEEL, 0.03)
FIRST = slab('Hood', [(0.38, 0.86), (0.40, 1.96), (0.55, 2.06), (2.60, 2.22), (2.60, 0.95)],
             lambda d, z: 0.66 - max(0.0, z - 1.9) * 0.4, RED, chamfer=0.05, soft=0.02)
box('HoodSeam', P(1.5, 1.45, 0.0), (1.355, 0.012, 0.02), BLACK, rot=(0, 0, 0))
for s in (-1, 1):
    # fender sweeping over the steer wheel (arch cut-out)
    prof = [(0.36, 0.72), (0.38, 1.40), (0.70, 1.62), (1.90, 1.64), (2.40, 1.40), (2.60, 1.10), (2.60, 0.72)]
    prof += arch(FRONT_AX, WR, 0.66, 8, 172, 14)
    slab('Fender', prof, 0.28, RED, xc=s * 0.94, chamfer=0.05)
    box('Headlamp', P(0.42, 1.12, s * 0.92), (0.30, 0.04, 0.16), LAMP, 0.02)
    box('HeadlampBezel', P(0.45, 1.12, s * 0.92), (0.36, 0.05, 0.22), BLACK, 0.02)
    box('Indicator', P(0.44, 1.12, s * 1.15), (0.10, 0.05, 0.14), AMBER, 0.015)

# cab + sleeper (one shell) with a roof fairing
CAB0, CAB1, SLP1 = 2.60, 4.15, 5.65
shell = [(CAB0, 1.00), (CAB0, 2.20), (2.92, 2.98), (3.10, 3.07), (3.55, 3.10), (4.35, 3.58), (SLP1, 3.58),
         (SLP1, 1.05)]
slab('Cab', shell, lambda d, z: 1.20 - max(0.0, z - 2.9) * 0.18, RED, chamfer=0.06, soft=0.025)
slab('CabSkirt', [(CAB0, 0.95), (SLP1, 0.95), (SLP1, 1.12), (CAB0, 1.12)], 1.21, BLACK, soft=0.01)
# windscreen (two panes) and side glass
for s in (-1, 1):
    a = Vector(P(CAB0 + 0.02, 2.24, s * 0.06)); b = Vector(P(2.90, 2.95, s * 0.06))
    mid = (a + b) / 2; ang = math.atan2(b.z - a.z, b.y - a.y)
    box('Windscreen', (s * 0.53, mid.y - 0.02 * math.sin(ang), mid.z + 0.02 * math.cos(ang)), (0.94, 0.02, (b - a).length - 0.06), GLASS, 0.01,
        rot=(ang - math.pi / 2, 0, 0))
    box('SideGlass', P(3.42, 2.58, s * 1.205), (0.025, 0.95, 0.58), GLASS, 0.01)
    box('SideGlassFrame', P(3.42, 2.58, s * 1.198), (0.02, 1.03, 0.66), BLACK, 0.01)
    box('SleeperGlass', P(4.85, 2.80, s * 1.155), (0.025, 0.42, 0.24), GLASS, 0.01)
    box('SleeperGlassFrame', P(4.85, 2.80, s * 1.148), (0.02, 0.50, 0.32), BLACK, 0.01)
    # door seams and handle, sleeper door
    for d in (2.78, 4.10):
        box('DoorSeam', P(d, 1.75, s * 1.208), (0.012, 0.012, 1.40), BLACK)
    box('DoorSeamLow', P(3.44, 1.06, s * 1.205), (0.012, 1.32, 0.012), BLACK)
    box('Handle', P(3.95, 2.12, s * 1.215), (0.03, 0.20, 0.035), STEEL, 0.01)
    box('SleeperDoor', P(4.85, 1.70, s * 1.205), (0.012, 0.62, 0.95), BLACK)
    box('SleeperDoorIn', P(4.85, 1.70, s * 1.208), (0.012, 0.58, 0.91), RED)
    # mirrors on arms ahead of the doors
    pipe('MirrorArm', [P(2.85, 2.05, s * 1.18), P(2.80, 2.05, s * 1.27), P(2.80, 2.75, s * 1.27),
                       P(2.85, 2.75, s * 1.18)], 0.016, STEEL, res=1)
    box('Mirror', P(2.82, 2.42, s * 1.265), (0.07, 0.10, 0.40), BLACK, 0.025)
    # vertical exhaust stack behind the cab corner
    pipe('Stack', [P(4.25, 1.15, s * 1.12), P(4.25, 3.70, s * 1.12), P(4.15, 3.92, s * 1.12)], 0.085, STEEL)
    box('StackGuard', P(4.25, 2.55, s * 1.12), (0.22, 0.22, 0.85), STEEL, 0.03)
    for z in (1.6, 3.2):
        box('StackClamp', P(4.20, z, s * 1.08), (0.12, 0.12, 0.05), BLACK, 0.01)
    # fuel tank with straps and a step box ahead of it
    cyl('FuelTank', P(5.05, 0.78, s * 0.86), 0.33, 1.10, 'Y', STEEL, 32, 0.05)
    for d in (4.7, 5.4):
        cyl('TankStrap', P(d, 0.78, s * 0.86), 0.338, 0.05, 'Y', BLACK, 32)
    box('StepBox', P(3.40, 0.70, s * 1.00), (0.50, 1.20, 0.50), BLACK, 0.03)
    for z in (0.52, 0.86):
        box('Step', P(3.40, z, s * 1.13), (0.26, 1.05, 0.04), STEEL, 0.01)
    box('Grab', P(4.12, 1.7, s * 1.23), (0.035, 0.035, 0.9), STEEL, 0.012)
    box('BackOfCab', P(SLP1 + 0.02, 2.3, s * 0.0), (2.30, 0.04, 2.4), RED, 0.02) if s > 0 else None
# roof marker lights and a sun visor
for k in range(5):
    box('Marker', P(2.98, 3.09, -0.5 + k * 0.25), (0.11, 0.05, 0.05), AMBER, 0.012)
box('Visor', P(2.92, 3.02), (2.22, 0.20, 0.04), RED, 0.015, rot=(math.radians(-12), 0, 0))
# air hoses from the back of the cab to the trailer
for k, x in enumerate((-0.2, 0.2)):
    pts = [P(SLP1 + 0.04, 2.6, x)]
    for i in range(1, 9):
        t = i / 8
        pts.append(P(SLP1 + 0.04 + t * 0.30, 2.6 - t * 0.1 + 0.05 * math.sin(t * 12), x + 0.06 * math.cos(t * 12)))
    pipe('AirHose', pts, 0.018, AMBER if k else BLACK, res=1)

# ================================================================= TRAILER (white box)
CUR = 'trailer'
T0, T1 = 6.05, 16.5
TZ0, TZ1 = 1.38, 4.00
TW = 2.55
TRFIRST = box('Box', P((T0 + T1) / 2, (TZ0 + TZ1) / 2), (TW, T1 - T0, TZ1 - TZ0), WHITE, 0.05)
for d in (T0 + 0.04, T1 - 0.05):
    for s in (-1, 1):
        box('CornerPost', P(d, (TZ0 + TZ1) / 2, s * (TW / 2 - 0.03)), (0.08, 0.10, TZ1 - TZ0 + 0.01), STEEL, 0.015)
for s in (-1, 1):
    box('TopRail', P((T0 + T1) / 2, TZ1 - 0.05, s * (TW / 2 + 0.005)), (0.03, T1 - T0 - 0.1, 0.10), STEEL, 0.01)
    box('BottomRail', P((T0 + T1) / 2, TZ0 + 0.09, s * (TW / 2 + 0.008)), (0.04, T1 - T0 - 0.1, 0.18), STEEL, 0.01)
    n = 7
    for k in range(1, n):
        d = T0 + (T1 - T0) * k / n
        box('Seam', P(d, (TZ0 + TZ1) / 2 + 0.04, s * (TW / 2 + 0.002)), (0.008, 0.02, TZ1 - TZ0 - 0.28), STEEL)
    for k in range(5):
        box('SideMarker', P(T0 + 0.6 + k * 2.45, TZ0 + 0.09, s * (TW / 2 + 0.03)), (0.02, 0.10, 0.05), AMBER, 0.008)
box('FrontRoofRail', P(T0 + 0.02, TZ1 - 0.05), (TW - 0.04, 0.04, 0.10), STEEL, 0.01)
box('FrontBottomRail', P(T0 + 0.02, TZ0 + 0.09), (TW - 0.04, 0.04, 0.18), STEEL, 0.01)
# rear doors: frame, two leaves, lock bars, hinges
box('RearFrame', P(T1 - 0.01, (TZ0 + TZ1) / 2), (TW - 0.06, 0.04, TZ1 - TZ0 - 0.04), STEEL, 0.01)
for s in (-1, 1):
    box('DoorLeaf', P(T1 + 0.01, (TZ0 + TZ1) / 2 + 0.02, s * 0.61), (1.18, 0.03, TZ1 - TZ0 - 0.36), WHITE, 0.01)
    for x in (0.30, 0.90):
        box('LockBar', P(T1 + 0.04, (TZ0 + TZ1) / 2, s * x), (0.04, 0.04, TZ1 - TZ0 - 0.30), STEEL, 0.01)
        box('LockHandle', P(T1 + 0.07, TZ0 + 0.8, s * (x - 0.08)), (0.18, 0.04, 0.04), STEEL, 0.01)
    for z in (TZ0 + 0.45, (TZ0 + TZ1) / 2, TZ1 - 0.45):
        box('Hinge', P(T1 + 0.035, z, s * 1.18), (0.14, 0.04, 0.10), STEEL, 0.01)
    box('TailLight', P(T1 + 0.0, TZ0 - 0.08, s * 1.0), (0.30, 0.06, 0.10), TAILL, 0.02)
box('RearSill', P(T1 - 0.05, TZ0 - 0.08), (TW - 0.1, 0.12, 0.16), BLACK, 0.02)
# underride guard
box('Guard', P(T1 - 0.18, 0.58), (2.30, 0.12, 0.16), STEEL, 0.03)
for s in (-1, 1):
    box('GuardPost', P(T1 - 0.30, 0.95, s * 0.55), (0.10, 0.10, 0.70), STEEL, 0.015)
# chassis: main beams, cross members, landing gear, kingpin plate
for s in (-1, 1):
    box('Beam', P((T0 + T1) / 2, TZ0 - 0.16, s * 0.48), (0.10, T1 - T0 - 0.6, 0.32), BLACK, 0.01)
for k in range(10):
    box('Cross', P(T0 + 1.6 + k * 0.95, TZ0 - 0.06, 0.0), (2.40, 0.08, 0.10), BLACK)
box('KingPlate', P(T0 + 1.0, TZ0 - 0.04), (1.6, 1.6, 0.06), BLACK)
LG = 8.85
for s in (-1, 1):
    box('LegOuter', P(LG, 0.92, s * 0.80), (0.14, 0.14, 0.80), STEEL, 0.02)
    box('LegInner', P(LG, 0.40, s * 0.80), (0.10, 0.10, 0.40), STEEL, 0.015)
    box('Foot', P(LG, 0.05, s * 0.80), (0.28, 0.28, 0.08), STEEL, 0.02)
    box('LegBrace', P(LG - 0.55, 1.05, s * 0.80), (0.05, 1.2, 0.05), STEEL, 0.01, rot=(math.radians(-25), 0, 0))
box('LegCross', P(LG, 0.72), (1.60, 0.06, 0.06), STEEL, 0.01)
box('Crank', P(LG, 1.05, 0.95), (0.18, 0.04, 0.04), STEEL, 0.01)
# axles on a slider, mud flaps
TAX = (14.30, 15.55)
for d in TAX:
    axle(d, True)
for s in (-1, 1):
    box('Slider', P(14.95, TZ0 - 0.40, s * 0.48), (0.10, 2.6, 0.20), BLACK, 0.01)
    box('MudFlapT', P(16.20, 0.60, s * 0.93), (0.62, 0.025, 0.66), BLACK, 0.01)

# ================================================================= finish
def prep(objs):
    for o in objs:
        bpy.context.view_layer.objects.active = o
        for md in list(o.modifiers):
            bpy.ops.object.modifier_apply(modifier=md.name)
        me = o.data
        at = me.attributes.new('mid', 'INT', 'FACE')
        at.data.foreach_set('value', [o['mid']] * len(me.polygons))

def join(objs, first):
    for o in scene.objects: o.select_set(False)
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = first
    bpy.ops.object.join()
    first.data.transform(first.matrix_world); first.matrix_world.identity()
    return first

def materialize(o, name):
    me = o.data
    mids = [0] * len(me.polygons); me.attributes['mid'].data.foreach_get('value', mids)
    used = sorted(set(mids)); remap = {u: k for k, u in enumerate(used)}
    me.materials.clear()
    for u in used: me.materials.append(MATS[u])
    me.polygons.foreach_set('material_index', [remap[v] for v in mids])
    me.attributes.remove(me.attributes['mid'])
    me.polygons.foreach_set('use_smooth', [True] * len(me.polygons))
    me.set_sharp_from_angle(angle=math.radians(35))
    o.name = name + '_Mesh'; me.name = name
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    bb = [Vector(c) for c in o.bound_box]
    mn = Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb)))
    mx = Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb)))
    print(f'[{name}] triangles {tris}, materials {len(me.materials)} {[m.name for m in me.materials]}, '
          f'size {mx.x - mn.x:.2f} x {mx.y - mn.y:.2f} x {mx.z - mn.z:.2f} m, y {mn.y:.2f}..{mx.y:.2f}, z {mn.z:.2f}')
    return o

prep(GROUP['tractor'] + GROUP['trailer'])
from collections import Counter
cnt = Counter()
for o in GROUP['tractor'] + GROUP['trailer']: cnt[o.name.split('.')[0]] += sum(len(p.vertices) - 2 for p in o.data.polygons)
print('[tris]', cnt.most_common(22))
if os.environ.get('COUNT_ONLY'): raise SystemExit
tractor = join(GROUP['tractor'], FIRST)
trailer = join(GROUP['trailer'], TRFIRST)
solo = tractor.copy(); solo.data = tractor.data.copy(); scene.collection.objects.link(solo)
SHIFT = Vector((0.0, -(Y(0) + TR_LEN / 2), 0.0))          # centre of the tractor footprint -> origin
solo.data.transform(__import__('mathutils').Matrix.Translation(SHIFT))
full = join([tractor, trailer], tractor)
materialize(full, NAME)
materialize(solo, NAME + '_Tractor')

SEAT = Vector(P(3.45, 1.95, 0.55))   # driver on the left (+X), US layout
root = bpy.data.objects.new(NAME, None); scene.collection.objects.link(root); full.parent = root
s1 = bpy.data.objects.new('Seat', None); s1.location = SEAT; scene.collection.objects.link(s1); s1.parent = root
root2 = bpy.data.objects.new(NAME + '_Tractor', None); scene.collection.objects.link(root2)
root2.location = (4.0, 0, 0)
solo.parent = root2
s2 = bpy.data.objects.new('Seat', None); s2.location = SEAT + SHIFT; scene.collection.objects.link(s2); s2.parent = root2
for o in scene.objects: o.select_set(False)
# Two files, so each has a child named exactly Seat (Blender would rename a second one to Seat.001).
for o in (root, full, s1): o.select_set(True)
bpy.ops.export_scene.fbx(filepath=f'{OUT}/{NAME}.fbx', use_selection=True, apply_unit_scale=True,
                         apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)
for o in scene.objects: o.select_set(False)
s1.name = 'Seat_Full'; s2.name = 'Seat'
_keep = root2.location.copy(); root2.location = (0, 0, 0); bpy.context.view_layer.update()
for o in (root2, solo, s2): o.select_set(True)
bpy.ops.export_scene.fbx(filepath=f'{OUT}/{NAME}Tractor.fbx', use_selection=True, apply_unit_scale=True,
                         apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)
root2.location = _keep; s2.name = 'Seat_Tractor'; s1.name = 'Seat'
solo.hide_render = True

# ---------------------------------------------------------------- previews
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

# front-left (+X, driver side), front of the truck to the left of frame like the references
sun.rotation_euler = (math.radians(38), 0, math.radians(150))
shoot('render-34', (8.2, -13.0, 3.7), (0.4, -2.2, 1.9), 30)
sun.rotation_euler = (math.radians(30), 0, math.radians(60))
shoot('render-side', (30, 0.0, 3.3), (0, 0.0, 3.3), ortho=17.4)

# ---------------------------------------------------------------- compare.jpg (reference left, render right)
import numpy as np
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

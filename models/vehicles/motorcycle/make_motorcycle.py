# Motorcycle (naked road bike), previs library v3. Own design, no brands.
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_motorcycle.py -- <out dir>
# 1 unit = 1 m, front toward -Y, up +Z, origin on the ground at the centre. Rider's right = -X (exhaust side).
import bpy, sys, math, bmesh, os
from mathutils import Vector

OUT = sys.argv[sys.argv.index('--') + 1]
NAME = 'Motorcycle'
L = 2.1

def Y(d):  # distance from the front -> scene Y (front is -Y)
    return d - L / 2

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ---------------------------------------------------------------- materials (8)
MATS = []
def mat(name, rgb, rough=0.7, metal=0.0, emit=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*rgb, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if emit:
        b.inputs['Emission Color'].default_value = (*rgb, 1)
        b.inputs['Emission Strength'].default_value = emit
    m.diffuse_color = (*rgb, 1)
    MATS.append(m)
    return m

PAINT = mat('Red', (0.50, 0.025, 0.02), 0.45)            # tank, shrouds, fender, tail cowl
BLACK = mat('Black', (0.012, 0.012, 0.013), 0.85)        # tyres, frame, swingarm, rims
PLAST = mat('Plastic', (0.030, 0.031, 0.034), 0.75)      # seat, nacelle, covers, plate
METAL = mat('Metal', (0.022, 0.022, 0.024), 0.6, 0.0)      # engine
STEEL = mat('Steel', (0.20, 0.20, 0.21), 0.45, 0.15)      # fork tubes, exhaust, discs, levers
LAMP = mat('Lamp', (0.85, 0.85, 0.80), 0.2, 0.0, 0.15)
AMBER = mat('Orange', (0.90, 0.30, 0.02), 0.45)          # indicators, shock spring
TAILL = mat('TailLamp', (0.55, 0.04, 0.02), 0.3, 0.0, 0.3)

# ---------------------------------------------------------------- helpers
parts = []
def keep(o, m):
    o.data.materials.clear()
    o['mid'] = MATS.index(m)
    parts.append(o)
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
    if bv: bevel(o, bv, segs)
    return keep(o, m)

def cyl(name, loc, r, depth, axis, m, verts=32, bv=0.0, segs=2, ang=30, rot=None):
    if rot is None:
        rot = {'X': (0, math.pi / 2, 0), 'Y': (math.pi / 2, 0, 0), 'Z': (0, 0, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    o = bpy.context.active_object; o.name = name
    bpy.ops.object.transform_apply(location=False, rotation=True)
    if bv: bevel(o, bv, segs, ang)
    return keep(o, m)

def fillet(pts, r, closed=False, n=3):
    P_ = [Vector(p) for p in pts]
    out = []
    N = len(P_)
    for i in range(N):
        if not closed and (i == 0 or i == N - 1):
            out.append(P_[i]); continue
        a, p, b = P_[i - 1], P_[i], P_[(i + 1) % N]
        da, db = (a - p), (b - p)
        rr = min(r, da.length * 0.45, db.length * 0.45)
        s0 = p + da.normalized() * rr; s1 = p + db.normalized() * rr
        for k in range(n + 1):
            t = k / n
            out.append((1 - t) ** 2 * s0 + 2 * (1 - t) * t * p + t * t * s1)
    return out

def pipe(name, pts, r, m, closed=False, res=2, round_r=0.0):
    """tube along a polyline; res 0/1/2 = 4/8/12 sides"""
    if round_r: pts = fillet(pts, round_r, closed)
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '3D'
    cu.bevel_depth = r; cu.bevel_resolution = res; cu.use_fill_caps = True
    sp = cu.splines.new('POLY'); sp.points.add(len(pts) - 1)
    for p, q in zip(sp.points, pts): p.co = (*q, 1)
    sp.use_cyclic_u = closed
    co = bpy.data.objects.new(name, cu); scene.collection.objects.link(co)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(co.evaluated_get(dg))
    bpy.data.objects.remove(co); bpy.data.curves.remove(cu)
    o = bpy.data.objects.new(name, me); scene.collection.objects.link(o)
    return keep(o, m)

def slab(name, prof, hw, m, xc=0.0, chamfer=0.0, soft=0.008, ang=30):
    """side profile [(d, z)] extruded across X; hw(d, z) half width, xc(d, z) centre"""
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

def helix(name, a, b, rad, turns, wire, m):
    a, b = Vector(a), Vector(b); ax = (b - a)
    q = ax.to_track_quat('Z', 'X')
    pts = []
    n = int(turns * 8)
    for k in range(n + 1):
        t = k / n; ang = 2 * math.pi * turns * t
        pts.append(a + q @ Vector((rad * math.cos(ang), rad * math.sin(ang), ax.length * t)))
    return pipe(name, pts, wire, m, res=1)

def lathe(name, x, y, z, prof, m, n=32):
    """revolve a (radius, x-offset) profile around the X axis"""
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    rings = []
    for k in range(n):
        a = 2 * math.pi * k / n
        rings.append([bm.verts.new((x + px, y + r * math.cos(a), z + r * math.sin(a))) for r, px in prof])
    for k in range(n):
        A, B = rings[k], rings[(k + 1) % n]
        for i in range(len(prof) - 1):
            bm.faces.new([A[i], A[i + 1], B[i + 1], B[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); scene.collection.objects.link(o)
    return keep(o, m)

def P(d, z, x=0.0):
    return (x, Y(d), z)

# ---------------------------------------------------------------- wheels (cast, 5 split spokes, road tyres)
FD, FZ, FR = 0.31, 0.31, 0.31
RD, RZ, RR = 1.765, 0.315, 0.315

def wheel(d, zc, R, tw, front):
    y = Y(d); hw = tw / 2; rr = R - 0.098       # rim radius (17 in)
    lathe('Tyre', 0, y, zc, [(rr - 0.004, -hw * 0.62), (rr + 0.03, -hw * 0.95), (R - 0.045, -hw), (R - 0.016, -hw * 0.8),
                             (R - 0.002, -hw * 0.42), (R, 0), (R - 0.002, hw * 0.42), (R - 0.016, hw * 0.8),
                             (R - 0.045, hw), (rr + 0.03, hw * 0.95), (rr - 0.004, hw * 0.62)], BLACK)
    lathe('Rim', 0, y, zc, [(rr - 0.03, -hw * 0.55), (rr + 0.006, -hw * 0.66), (rr + 0.006, hw * 0.66), (rr - 0.03, hw * 0.55),
                            (rr - 0.03, -hw * 0.55)], BLACK)
    for s in (-1, 1):   # thin machined lip on both rim edges
        lathe('RimLip', 0, y, zc, [(rr - 0.012, s * hw * 0.67), (rr + 0.007, s * hw * 0.67)], STEEL)
    cyl('Hub', (0, y, zc), 0.06, 0.12, 'X', PLAST, 20, 0.01)
    for k in range(5):
        t0 = 2 * math.pi * k / 5 + 0.3
        for off in (-0.09, 0.09):
            t = t0 + off * 0.5
            rm = (0.055 + rr - 0.03) / 2
            ln = rr - 0.03 - 0.05
            box('Spoke', (0, y + rm * math.cos(t + off * 0.6), zc + rm * math.sin(t + off * 0.6)),
                (0.045, 0.034, ln), BLACK, 0.008, rot=(t + off * 0.6 - math.pi / 2, 0, 0), segs=1)
    if front:
        for s in (-1, 1):
            cyl('Disc', (s * 0.075, y, zc), 0.13, 0.006, 'X', STEEL, 32)
            cyl('DiscCarrier', (s * 0.08, y, zc), 0.085, 0.01, 'X', PLAST, 16)
    else:
        cyl('Disc', (-0.085, y, zc), 0.11, 0.006, 'X', STEEL, 32)
        cyl('Sprocket', (0.09, y, zc), 0.105, 0.008, 'X', METAL, 32, 0.003, 1)
        cyl('SprocketHub', (0.095, y, zc), 0.05, 0.012, 'X', STEEL, 16)

wheel(FD, FZ, FR, 0.13, True)
wheel(RD, RZ, RR, 0.19, False)

# ---------------------------------------------------------------- fork, yokes, bars, mirrors, headlight
top = Vector(P(0.645, 1.00)); axle = Vector(P(FD, FZ))
up = (top - axle).normalized()
for s in (-1, 1):
    o = Vector((s * 0.085, 0, 0))
    a = axle + o
    pipe('ForkLower', [a - up * 0.03, a + up * 0.30], 0.032, BLACK, res=2)
    pipe('ForkUpper', [a + up * 0.27, top + o], 0.024, STEEL, res=2)
    cyl('ForkFoot', tuple(a), 0.036, 0.05, 'X', BLACK, 12, 0.006)
    box('Caliper', tuple(a + o * 0.0 + Vector((s * 0.0, 0.10, 0.08))), (0.03, 0.06, 0.12), PLAST, 0.008,
        rot=(math.radians(-30), 0, 0))
cyl('AxleF', tuple(axle), 0.016, 0.22, 'X', STEEL, 10)
for f, h in ((0.80, 0.03), (1.0, 0.035)):
    c = axle + (top - axle) * f
    box('Yoke', tuple(c), (0.24, 0.08, h), BLACK, 0.01, rot=(math.radians(-24), 0, 0))
pipe('HeadTube', [tuple(axle + (top - axle) * 0.78), tuple(axle + (top - axle) * 1.01)], 0.035, BLACK, res=2)
box('BarClamp', P(0.665, 1.03), (0.12, 0.05, 0.04), BLACK, 0.008)
box('Clocks', P(0.60, 1.07), (0.15, 0.05, 0.09), PLAST, 0.015, rot=(math.radians(-30), 0, 0))
for s in (-1, 1):
    pipe('Bar', [P(0.67, 1.04, 0.0), P(0.69, 1.045, s * 0.12), P(0.74, 1.05, s * 0.26), P(0.76, 1.05, s * 0.30)],
         0.012, BLACK, round_r=0.05)
    pipe('Grip', [P(0.76, 1.05, s * 0.30), P(0.785, 1.05, s * 0.39)], 0.019, PLAST, res=2)
    cyl('BarEnd', P(0.787, 1.05, s * 0.395), 0.022, 0.014, 'X', STEEL, 12)
    box('SwitchBox', P(0.755, 1.05, s * 0.285), (0.04, 0.05, 0.045), PLAST, 0.008)
    pipe('Lever', [P(0.73, 1.05, s * 0.29), P(0.70, 1.05, s * 0.34), P(0.71, 1.045, s * 0.40)], 0.007, STEEL)
    pipe('MirrorStalk', [P(0.72, 1.05, s * 0.25), P(0.72, 1.07, s * 0.27), P(0.70, 1.09, s * 0.30)], 0.007, BLACK)
    box('Mirror', P(0.70, 1.10, s * 0.33), (0.13, 0.03, 0.065), PLAST, 0.012, rot=(0, 0, s * math.radians(-10)))
# headlight nacelle with a round lens
box('Nacelle', P(0.53, 0.93), (0.19, 0.15, 0.18), PLAST, 0.03, rot=(math.radians(-22), 0, 0))
cyl('LampRim', P(0.455, 0.925), 0.072, 0.04, 'Y', BLACK, 24, 0.008, rot=(math.radians(90 - 22), 0, 0))
cyl('Lens', P(0.44, 0.93), 0.06, 0.025, 'Y', LAMP, 24, 0.012, rot=(math.radians(90 - 22), 0, 0))
for s in (-1, 1):
    pipe('IndStalk', [P(0.53, 0.89, s * 0.09), P(0.53, 0.89, s * 0.16)], 0.008, BLACK)
    box('IndF', P(0.52, 0.89, s * 0.18), (0.05, 0.035, 0.03), AMBER, 0.008)
# front fender (hugger over the tyre, following the wheel arc)
fprof = []
for a in range(30, 151, 12):
    t = math.radians(a)
    fprof.append((FD + (FR + 0.035) * math.cos(t), FZ + (FR + 0.035) * math.sin(t)))
for a in range(150, 29, -12):
    t = math.radians(a)
    fprof.append((FD + (FR + 0.008) * math.cos(t), FZ + (FR + 0.008) * math.sin(t)))
slab('FenderF', fprof, 0.075, PAINT, chamfer=0.008, soft=0.004, ang=25)

# ---------------------------------------------------------------- tank, shrouds, seat, tail
FIRST = slab('Tank', [(0.68, 0.86), (0.71, 0.95), (0.80, 0.995), (0.98, 0.99), (1.10, 0.92), (1.12, 0.86),
                      (1.00, 0.80), (0.80, 0.79)],
             lambda d, z: 0.16 - max(0.0, z - 0.94) * 1.1 - max(0.0, d - 1.0) * 0.25, PAINT, chamfer=0.022, soft=0.008)
cyl('FuelCap', P(0.86, 1.0), 0.04, 0.02, 'Z', PLAST, 16, 0.004)
for s in (-1, 1):
    slab('Shroud', [(0.66, 0.92), (0.76, 0.93), (0.90, 0.84), (0.86, 0.72), (0.72, 0.70)], 0.022, PAINT,
         xc=lambda d, z, s=s: s * (0.165 + max(0.0, 0.80 - d) * 0.15), chamfer=0.01, soft=0.005)
    slab('ShroudVent', [(0.74, 0.84), (0.82, 0.82), (0.80, 0.75), (0.74, 0.76)], 0.006, PLAST,
         xc=lambda d, z, s=s: s * (0.187 + max(0.0, 0.80 - d) * 0.15), soft=0.002)
slab('Seat', [(1.06, 0.88), (1.12, 0.885), (1.40, 0.855), (1.52, 0.865), (1.56, 0.915), (1.80, 0.94), (1.83, 0.92),
              (1.62, 0.85), (1.42, 0.80), (1.12, 0.80)],
     lambda d, z: 0.135 - max(0.0, d - 1.40) * 0.18 - max(0.0, z - 0.88) * 0.6, PLAST, chamfer=0.015, soft=0.01)
slab('TailCowl', [(1.38, 0.80), (1.55, 0.86), (1.80, 0.915), (2.03, 0.985), (2.055, 0.965), (1.92, 0.88), (1.70, 0.79),
                  (1.50, 0.74)],
     lambda d, z: 0.115 - max(0.0, d - 1.5) * 0.11, PAINT, chamfer=0.012, soft=0.005)
box('TailLight', P(2.045, 0.955), (0.10, 0.03, 0.035), TAILL, 0.008, rot=(math.radians(-60), 0, 0))
slab('Undertray', [(1.70, 0.79), (1.95, 0.86), (1.98, 0.84), (1.75, 0.75)], 0.07, PLAST, soft=0.004)
pipe('PlateArm', [P(1.92, 0.84), P(2.00, 0.78), P(2.06, 0.70)], 0.012, BLACK, round_r=0.03)
box('Plate', P(2.065, 0.645), (0.17, 0.008, 0.11), PLAST, 0.004, rot=(math.radians(-12), 0, 0))
for s in (-1, 1):
    pipe('IndStalkR', [P(1.97, 0.80, s * 0.03), P(1.97, 0.80, s * 0.11)], 0.007, BLACK)
    box('IndR', P(1.975, 0.80, s * 0.125), (0.045, 0.035, 0.028), AMBER, 0.008)
# rear hugger
hprof = []
for a in range(60, 131, 10):
    t = math.radians(a); hprof.append((RD + (RR + 0.03) * math.cos(t), RZ + (RR + 0.03) * math.sin(t)))
for a in range(130, 59, -10):
    t = math.radians(a); hprof.append((RD + (RR + 0.01) * math.cos(t), RZ + (RR + 0.01) * math.sin(t)))
slab('Hugger', hprof, 0.07, BLACK, soft=0.004)

# ---------------------------------------------------------------- trellis frame, swingarm, shock
PIV = (1.24, 0.46)
for s in (-1, 1):
    x = s * 0.115
    pipe('FrameTop', [P(0.66, 0.97, x * 0.45), P(0.95, 0.90, x), P(1.17, 0.80, x), P(1.25, 0.62, x), P(*PIV, x)],
         0.019, BLACK, round_r=0.04)
    pipe('FrameDown', [P(0.68, 0.86, x * 0.45), P(0.86, 0.72, x), P(1.02, 0.60, x), P(1.25, 0.60, x)], 0.017, BLACK)
    pipe('FrameDiag', [P(0.95, 0.90, x), P(0.86, 0.72, x)], 0.014, BLACK)
    pipe('FrameDiag', [P(0.95, 0.90, x), P(1.02, 0.60, x)], 0.014, BLACK)
    pipe('FrameDiag', [P(1.17, 0.80, x), P(1.02, 0.60, x)], 0.014, BLACK)
    pipe('Subframe', [P(1.17, 0.80, x), P(1.85, 0.90, x * 0.65)], 0.013, BLACK)
    pipe('Subframe', [P(1.25, 0.62, x), P(1.70, 0.84, x * 0.7)], 0.011, BLACK)
    slab('Swingarm', [(1.21, 0.50), (1.28, 0.52), (RD, RZ + 0.04), (RD + 0.03, RZ), (RD, RZ - 0.035), (1.27, 0.40)],
         0.022, BLACK, xc=s * 0.105, chamfer=0.008, soft=0.004)
    box('Peg', P(1.18, 0.37, s * 0.19), (0.10, 0.035, 0.025), PLAST, 0.006)
    slab('HeelGuard', [(1.10, 0.37), (1.24, 0.37), (1.30, 0.50), (1.24, 0.53), (1.16, 0.45)], 0.004, STEEL,
         xc=s * 0.155, soft=0.002)
    box('PegR', P(1.47, 0.50, s * 0.19), (0.08, 0.03, 0.022), PLAST, 0.006)
    pipe('PegRArm', [P(1.47, 0.50, s * 0.12), P(1.55, 0.62, s * 0.115), P(1.62, 0.80, s * 0.10)], 0.012, BLACK)
cyl('Pivot', P(*PIV), 0.028, 0.26, 'X', STEEL, 12)
cyl('AxleR', P(RD, RZ), 0.016, 0.26, 'X', STEEL, 10)
pipe('Shock', [P(1.28, 0.48), P(1.36, 0.80)], 0.016, STEEL)
helix('ShockSpring', P(1.29, 0.53), P(1.345, 0.74), 0.036, 6, 0.008, AMBER)
pipe('Chain', [P(1.10, 0.43, 0.105), P(RD, RZ + 0.11, 0.105), P(RD + 0.08, RZ + 0.075, 0.105), P(RD + 0.11, RZ, 0.105),
               P(RD + 0.08, RZ - 0.075, 0.105), P(RD, RZ - 0.11, 0.105), P(1.10, 0.36, 0.105), P(1.07, 0.395, 0.105)],
     0.009, METAL, closed=True, res=1)
pipe('BrakePedal', [P(1.13, 0.36, -0.16), P(1.02, 0.33, -0.18), P(0.98, 0.34, -0.18)], 0.01, STEEL)
pipe('ShiftLever', [P(1.13, 0.40, 0.16), P(1.02, 0.36, 0.18), P(0.99, 0.37, 0.18)], 0.01, STEEL)

# ---------------------------------------------------------------- engine (inline four, cylinders tilted forward)
box('Crankcase', P(1.02, 0.38), (0.40, 0.42, 0.24), METAL, 0.035)
box('Sump', P(0.96, 0.24), (0.30, 0.26, 0.08), METAL, 0.02)
box('Gearbox', P(1.17, 0.44), (0.30, 0.18, 0.20), METAL, 0.03)
TILT = math.radians(-24)
box('Block', P(0.90, 0.60), (0.38, 0.17, 0.22), METAL, 0.02, rot=(TILT, 0, 0))
for k in range(5):
    box('Fin', P(0.885 - k * 0.012, 0.52 + k * 0.035), (0.40, 0.21, 0.012), METAL, 0.003, rot=(TILT, 0, 0), segs=1)
box('Head', P(0.855, 0.76), (0.40, 0.19, 0.09), METAL, 0.025, rot=(TILT, 0, 0))
box('HeadCover', P(0.865, 0.815), (0.34, 0.15, 0.04), PLAST, 0.015, rot=(TILT, 0, 0))
for s in (-1, 1):
    cyl('SideCover', P(1.04, 0.38, s * 0.215), 0.10, 0.04, 'X', METAL, 32, 0.012)
    cyl('CoverCap', P(1.04, 0.38, s * 0.237), 0.055, 0.01, 'X', STEEL, 20)
box('Airbox', P(1.10, 0.72), (0.24, 0.20, 0.14), PLAST, 0.02)
slab('SideFill', [(1.08, 0.80), (1.45, 0.80), (1.40, 0.66), (1.28, 0.58), (1.12, 0.62)], 0.09, PLAST, chamfer=0.01, soft=0.005)
box('Radiator', P(0.71, 0.66), (0.42, 0.05, 0.28), PLAST, 0.008, rot=(math.radians(-12), 0, 0))
for k in range(7):
    box('RadFin', P(0.692, 0.56 + k * 0.03 + 0.005), (0.38, 0.012, 0.008), BLACK, 0.0, rot=(math.radians(-12), 0, 0))
# exhaust: four headers -> collector -> short angular muffler on the right (-X)
for i, x in enumerate((-0.12, -0.04, 0.04, 0.12)):
    pipe('Header', [P(0.73, 0.72, x), P(0.66, 0.62, x), P(0.66, 0.36, x * 0.7), P(0.74, 0.22, x * 0.4),
                    P(0.88, 0.17, -0.02)], 0.019, STEEL, round_r=0.06, res=1)
pipe('Collector', [P(0.86, 0.17, -0.02), P(1.10, 0.17, -0.06), P(1.28, 0.30, -0.17), P(1.36, 0.38, -0.19)],
     0.028, STEEL, round_r=0.07, res=1)
pipe('Muffler', [P(1.34, 0.37, -0.195), P(1.66, 0.52, -0.195)], 0.07, STEEL, res=1)
pipe('MufflerEnd', [P(1.65, 0.515, -0.195), P(1.70, 0.54, -0.195)], 0.058, PLAST, res=1)
pipe('Tip', [P(1.69, 0.535, -0.195), P(1.72, 0.55, -0.195)], 0.03, BLACK, res=1)
pipe('MufflerStrap', [P(1.47, 0.46, -0.10), P(1.50, 0.62, -0.10)], 0.012, BLACK)

# ---------------------------------------------------------------- finish: apply, join, per-face materials
for o in list(parts):
    bpy.context.view_layer.objects.active = o
    for md in list(o.modifiers):
        bpy.ops.object.modifier_apply(modifier=md.name)
    me = o.data
    at = me.attributes.new('mid', 'INT', 'FACE')
    at.data.foreach_set('value', [o['mid']] * len(me.polygons))
from collections import Counter
cnt = Counter()
for o in parts: cnt[o.name.split('.')[0]] += sum(len(p.vertices) - 2 for p in o.data.polygons)
print('[tris]', cnt.most_common(14))
for o in scene.objects: o.select_set(False)
for o in parts: o.select_set(True)
bpy.context.view_layer.objects.active = FIRST
bpy.ops.object.join()
mdl = FIRST
mdl.data.transform(mdl.matrix_world); mdl.matrix_world.identity()
me = mdl.data
mids = [0] * len(me.polygons); me.attributes['mid'].data.foreach_get('value', mids)
used = sorted(set(mids)); remap = {u: k for k, u in enumerate(used)}
me.materials.clear()
for u in used: me.materials.append(MATS[u])
me.polygons.foreach_set('material_index', [remap[v] for v in mids])
me.attributes.remove(me.attributes['mid'])
me.polygons.foreach_set('use_smooth', [True] * len(me.polygons))
me.set_sharp_from_angle(angle=math.radians(35))
mdl.name = NAME + '_Mesh'; me.name = NAME
tris = sum(len(p.vertices) - 2 for p in me.polygons)
bb = [Vector(c) for c in mdl.bound_box]
mn = Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb)))
mx = Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb)))
print(f'[{NAME}] triangles {tris}, materials {len(me.materials)} {[m.name for m in me.materials]}, '
      f'size {mx.x - mn.x:.2f} x {mx.y - mn.y:.2f} x {mx.z - mn.z:.2f} m, y {mn.y:.2f}..{mx.y:.2f}, z {mn.z:.2f}')

root = bpy.data.objects.new(NAME, None); scene.collection.objects.link(root); mdl.parent = root
seatE = bpy.data.objects.new('Seat', None); seatE.location = P(1.28, 0.86); scene.collection.objects.link(seatE)
seatE.parent = root
for o in scene.objects: o.select_set(False)
root.select_set(True); mdl.select_set(True); seatE.select_set(True)
bpy.ops.export_scene.fbx(filepath=f'{OUT}/{NAME}.fbx', use_selection=True, apply_unit_scale=True,
                         apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)

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

# camera on the rider's right (-X, exhaust side), front of the bike to the right of frame, like the references
sun.rotation_euler = (math.radians(38), 0, math.radians(-120))
shoot('render-34', (-3.0, -2.75, 1.35), (0.0, -0.08, 0.58), 62)
sun.rotation_euler = (math.radians(30), 0, math.radians(-60))
shoot('render-side', (-12, 0.0, 0.60), (0, 0.0, 0.60), ortho=2.33)

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

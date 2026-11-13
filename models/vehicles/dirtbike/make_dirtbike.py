# Dirt bike (enduro), previs library, round 2 (opus). Own design, no brands.
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_dirtbike.py -- <out dir>
# 1 unit = 1 m, front toward -Y, up +Z, origin on the ground at the centre.
# Side reference: 2.1 m over 1550 px (1.355 mm/px), ground at y=915, front of the front tyre at x=55.
import bpy, sys, math, bmesh
from mathutils import Vector

OUT = sys.argv[sys.argv.index('--') + 1]
REF = './dirtbike'
NAME = 'DirtBike'
L = 2.1

def Y(d):  # distance from the front -> scene Y (front is -Y)
    return d - L / 2

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ---------------------------------------------------------------- materials
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

PAINT = mat('Paint', (0.52, 0.36, 0.19), 0.6)          # sand / tan plastics
MUD = mat('PaintWorn', (0.38, 0.27, 0.15), 0.8)        # weathering on low plastic faces
SEATM = mat('Seat', (0.028, 0.027, 0.028), 0.85)
FRAME = mat('Frame', (0.035, 0.035, 0.038), 0.55)      # frame, lower fork legs, bars, chain
METAL = mat('Metal', (0.17, 0.17, 0.17), 0.45, 0.3)    # engine, rims, hubs
SILVER = mat('Silver', (0.42, 0.42, 0.43), 0.35, 0.6)  # fork tubes, swingarm, skid plate, spokes
TYRE = mat('Tyre', (0.03, 0.03, 0.03), 0.9)
LAMP = mat('Lamp', (0.85, 0.85, 0.82), 0.2, 0.0, 0.6)
RED = mat('TailLamp', (0.55, 0.04, 0.02), 0.3, 0.0, 0.3)

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

def cyl(name, loc, r, depth, axis, m, verts=32, bv=0.0, segs=2, ang=30):
    rot = {'X': (0, math.pi / 2, 0), 'Y': (math.pi / 2, 0, 0), 'Z': (0, 0, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    o = bpy.context.active_object; o.name = name
    bpy.ops.object.transform_apply(location=False, rotation=True)
    if bv: bevel(o, bv, segs, ang)
    return keep(o, m)

def fillet(pts, r, closed=False, n=3):
    """round the corners of a polyline with small quadratic arcs"""
    P = [Vector(p) for p in pts]
    out = []
    N = len(P)
    for i in range(N):
        if not closed and (i == 0 or i == N - 1):
            out.append(P[i]); continue
        a, p, b = P[i - 1], P[i], P[(i + 1) % N]
        da, db = (a - p), (b - p)
        rr = min(r, da.length * 0.45, db.length * 0.45)
        s0 = p + da.normalized() * rr; s1 = p + db.normalized() * rr
        for k in range(n + 1):
            t = k / n
            out.append((1 - t) ** 2 * s0 + 2 * (1 - t) * t * p + t * t * s1)
    return out

def pipe(name, pts, r, m, closed=False, res=2, round_r=0.0):
    """tube along a polyline (curve bevel converted to mesh); res 2 = 8 sides"""
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
    """side profile [(d, z)] given width by hw(d, z) (half width) - tapering gives tumblehome"""
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

def arc(cd, cz, r, a0, a1, n=14):
    return [(cd + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)),
             cz + r * math.sin(math.radians(a0 + (a1 - a0) * k / n))) for k in range(n + 1)]

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
    """revolve a (radius, x-offset) profile around the X axis (closed ring, open centre)"""
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


# ---------------------------------------------------------------- wheels (spoked, knobby)
FD, FZ, FR = 0.332, 0.332, 0.332      # front wheel centre (d, z) and outer radius
RD, RZ, RR = 1.768, 0.315, 0.315      # rear
FORK = (Vector(P(FD, FZ)) - Vector(P(0.664, 1.077))).normalized()   # fork axis, ~24 deg rake

def wheel(d, zc, rout, tw, front):
    y = Y(d); core = rout - 0.024
    hw = tw / 2
    lathe('Tyre', 0, y, zc, [(core - 0.115, -hw * 0.75), (core - 0.07, -hw), (core - 0.02, -hw * 0.9), (core, -hw * 0.55),
                             (core, hw * 0.55), (core - 0.02, hw * 0.9), (core - 0.07, hw), (core - 0.115, hw * 0.75)], TYRE)
    n = 22
    for k in range(n):          # paired shoulder knobs with a centre knob between pairs
        for off, ln, ph, ht in ((-hw * 0.5, hw * 0.95, 0.0, 0.042), (hw * 0.5, hw * 0.95, 0.0, 0.042),
                                (0.0, hw * 0.8, 0.5, 0.026)):
            t = 2 * math.pi * (k + ph) / n
            rr = core + ht / 2 - 0.008
            box('Knob', (off, y + rr * math.cos(t), zc + rr * math.sin(t)), (ln, 0.046, ht), TYRE,
                0.006, rot=(t - math.pi / 2, 0, 0), segs=1)
    rim_r = core - 0.115
    lathe('Rim', 0, y, zc, [(rim_r - 0.022, -0.028), (rim_r + 0.004, -0.032), (rim_r + 0.004, 0.032), (rim_r - 0.022, 0.028)],
          METAL, n=32)
    cyl('Hub', (0, y, zc), 0.045, 0.11, 'X', METAL, 16, 0.008)
    for k in range(20):
        t = 2 * math.pi * k / 20
        side = 0.04 if k % 2 else -0.04
        t2 = t + (0.25 if k % 2 else -0.25)
        pipe('Spoke', [(side, y + 0.04 * math.cos(t2), zc + 0.04 * math.sin(t2)),
                       (side * 0.4, y + (rim_r - 0.02) * math.cos(t), zc + (rim_r - 0.02) * math.sin(t))], 0.0035, SILVER, res=0)
    if front:   # brake disc and caliper on the +x side
        cyl('Disc', (0.06, y, zc), 0.115, 0.006, 'X', SILVER, 24)
        for k in range(8):
            t = 2 * math.pi * k / 8
            cyl('DiscHole', (0.064, y + 0.085 * math.cos(t), zc + 0.085 * math.sin(t)), 0.009, 0.004, 'X', FRAME, 6)
        cyl('DiscCarrier', (0.065, y, zc), 0.06, 0.008, 'X', METAL, 12)
    else:       # rear sprocket
        cyl('Sprocket', (0.075, y, zc), 0.10, 0.008, 'X', METAL, 24, 0.004, 1)
        for k in range(5):
            t = 2 * math.pi * k / 5
            cyl('SprocketHole', (0.08, y + 0.06 * math.cos(t), zc + 0.06 * math.sin(t)), 0.018, 0.004, 'X', FRAME, 8)
        cyl('Disc', (-0.06, y, zc), 0.10, 0.006, 'X', SILVER, 24)

wheel(FD, FZ, FR, 0.095, True)
wheel(RD, RZ, RR, 0.125, False)

# ---------------------------------------------------------------- fork, clamps, bars
top = Vector(P(0.664, 1.077)); axle = Vector(P(FD, FZ))
for s in (-1, 1):
    o = Vector((s * 0.075, 0, 0))
    a = axle + o; m_ = axle + (top - axle) * 0.45 + o; t_ = top + o
    pipe('ForkLower', [a + FORK * -0.02, m_], 0.032, FRAME, res=3)
    pipe('ForkUpper', [m_ - (m_ - a).normalized() * 0.03, t_], 0.024, SILVER, res=3)
    cyl('ForkFoot', tuple(a), 0.034, 0.05, 'X', FRAME, 12, 0.006)
    pipe('Caliper', [a + (top - axle).normalized() * 0.10 + Vector((s * 0.0, 0, 0)) + Vector((0.0, 0.04, 0.0)),
                     a + (top - axle).normalized() * 0.18 + Vector((0.0, 0.05, 0.0))], 0.02, FRAME) if s > 0 else None
cyl('AxleF', tuple(axle), 0.014, 0.20, 'X', SILVER, 8)
for f, h in ((0.86, 0.03), (1.0, 0.035)):
    c = axle + (top - axle) * f
    box('Clamp', tuple(c), (0.22, 0.07, h), FRAME, 0.01, rot=(math.radians(-24), 0, 0))
pipe('HeadTube', [tuple(axle + (top - axle) * 0.80), tuple(axle + (top - axle) * 1.02)], 0.032, FRAME, res=3)
cB = axle + (top - axle) * 1.04
box('BarClamp', tuple(cB + Vector((0, 0.02, 0.01))), (0.10, 0.05, 0.04), FRAME, 0.008)
for s in (-1, 1):
    pipe('Bar', [P(0.69, 1.105, 0.0), P(0.70, 1.115, s * 0.12), P(0.78, 1.165, s * 0.25), P(0.83, 1.175, s * 0.31)],
         0.0125, FRAME, round_r=0.04)
    pipe('Grip', [P(0.83, 1.175, s * 0.31), P(0.88, 1.175, s * 0.405)], 0.02, FRAME, res=3)
    cyl('BarEnd', P(0.885, 1.175, s * 0.41), 0.022, 0.012, 'X', FRAME, 10)
    box('Perch', P(0.815, 1.168, s * 0.29), (0.04, 0.045, 0.045), FRAME, 0.006)
    pipe('Lever', [P(0.80, 1.16, s * 0.30), P(0.75, 1.145, s * 0.35), P(0.76, 1.135, s * 0.42)], 0.007, SILVER)
pipe('BarPad', [P(0.70, 1.13, -0.08), P(0.70, 1.13, 0.08)], 0.022, FRAME, res=3)
pipe('Cable', [P(0.80, 1.16, 0.28), P(0.62, 1.12, 0.12), P(0.66, 0.92, 0.10), P(0.80, 0.78, 0.10)], 0.005, FRAME, round_r=0.08)

# number-plate shroud with the headlight, leaning with the fork
slab('Shroud', [(0.555, 0.87), (0.515, 1.04), (0.565, 1.175), (0.63, 1.165), (0.615, 1.05), (0.65, 0.88)],
     lambda d, z: 0.135 - max(0.0, z - 1.08) * 0.6 - max(0.0, 0.95 - z) * 0.5, PAINT, chamfer=0.02, soft=0.006)
box('LampHouse', P(0.53, 1.01), (0.13, 0.03, 0.10), FRAME, 0.01, rot=(math.radians(-18), 0, 0))
box('Lamp', P(0.523, 1.015), (0.105, 0.02, 0.075), LAMP, 0.008, rot=(math.radians(-18), 0, 0))

# high front fender (long beak)
slab('FenderF', [(0.075, 0.735), (0.085, 0.77), (0.29, 0.905), (0.55, 0.93), (0.66, 0.905), (0.65, 0.86),
                 (0.55, 0.855), (0.30, 0.835), (0.12, 0.735)],
     lambda d, z: 0.065 + min(d, 0.5) * 0.06, PAINT, chamfer=0.012, soft=0.006, ang=25)

# ---------------------------------------------------------------- body: tank, radiator shrouds, seat, side panels
FIRST = slab('Tank', [(0.66, 0.90), (0.67, 0.965), (0.72, 0.995), (0.90, 0.995), (0.95, 0.96), (0.92, 0.88), (0.75, 0.84)],
             lambda d, z: 0.12 - max(0.0, z - 0.93) * 0.8, PAINT, chamfer=0.02, soft=0.008)
cyl('FuelCap', P(0.85, 1.005), 0.032, 0.03, 'Z', FRAME, 10, 0.004)
for s in (-1, 1):
    slab('RadShroud', [(0.664, 0.969), (0.955, 0.962), (0.806, 0.603), (0.732, 0.603)],
         lambda d, z: 0.03, PAINT, xc=lambda d, z, s=s: s * (0.15 + max(0.0, 0.88 - d) * 0.40),
         chamfer=0.012, soft=0.006)
    slab('Vent', [(0.79, 0.85), (0.87, 0.85), (0.83, 0.76), (0.78, 0.76)], 0.012, FRAME,
         xc=lambda d, z, s=s: s * (0.178 + max(0.0, 0.88 - d) * 0.40), soft=0.003)
box('Radiator', P(0.76, 0.76), (0.26, 0.10, 0.28), FRAME, 0.01)
box('Airbox', P(1.27, 0.74), (0.18, 0.26, 0.26), FRAME, 0.02)
slab('Seat', [(0.91, 0.985), (0.96, 1.005), (1.10, 0.988), (1.70, 0.985), (1.76, 0.968), (1.74, 0.925), (1.25, 0.885),
              (1.02, 0.855), (0.95, 0.90)],
     lambda d, z: 0.10 + min(max(d - 0.93, 0.0), 0.3) * 0.1 - max(0.0, z - 0.97) * 0.8, SEATM, chamfer=0.015, soft=0.01)
for s in (-1, 1):
    slab('SidePanel', [(1.213, 0.792), (1.294, 0.885), (1.70, 0.90), (1.68, 0.83), (1.524, 0.603), (1.281, 0.603)],
         lambda d, z: 0.025, PAINT, xc=s * 0.115, chamfer=0.012, soft=0.006)
slab('Tail', [(1.60, 0.90), (1.74, 0.955), (2.03, 0.975), (2.045, 0.955), (1.76, 0.90), (1.64, 0.86)],
     lambda d, z: 0.10 - max(0.0, d - 1.8) * 0.15, PAINT, chamfer=0.01, soft=0.005)
box('TailLight', P(2.03, 0.935), (0.07, 0.03, 0.03), RED, 0.006)
slab('Flap', [(1.92, 0.94), (2.03, 0.945), (2.08, 0.76), (2.055, 0.745), (1.97, 0.86)], 0.075, FRAME, soft=0.006)

# ---------------------------------------------------------------- frame, swingarm, shock
for s in (-1, 1):
    x = s * 0.085
    pipe('Spar', [P(0.70, 0.93, x * 0.4), P(1.05, 0.83, x), P(1.20, 0.72, x), P(1.23, 0.44, x), P(1.15, 0.27, x)],
         0.022, FRAME, round_r=0.06)
    pipe('Sub', [P(1.18, 0.78, x), P(1.80, 0.90, x * 0.8)], 0.014, FRAME)
    pipe('SubLow', [P(1.23, 0.55, x), P(1.78, 0.88, x * 0.8)], 0.012, FRAME)
    # swingarm (tapered, silver)
    slab('Swingarm', [(1.20, 0.485), (1.79, 0.35), (1.79, 0.272), (1.20, 0.38)], 0.018, SILVER, xc=s * 0.075,
         chamfer=0.006, soft=0.004)
    box('Peg', P(1.14, 0.33, s * 0.17), (0.11, 0.04, 0.025), FRAME, 0.005)
pipe('Down', [P(0.70, 0.90), P(0.80, 0.55), P(0.82, 0.30), P(0.92, 0.24), P(1.15, 0.27)], 0.024, FRAME, round_r=0.07)
cyl('Pivot', P(1.226, 0.43), 0.025, 0.21, 'X', SILVER, 12)
cyl('AxleR', P(RD, RZ), 0.014, 0.22, 'X', SILVER, 8)
pipe('ShockBody', [P(1.21, 0.43), P(1.29, 0.78)], 0.018, SILVER)
helix('ShockSpring', P(1.22, 0.47), P(1.28, 0.71), 0.04, 6, 0.008, METAL)
box('Reservoir', P(1.30, 0.70, 0.05), (0.04, 0.05, 0.12), FRAME, 0.01)
pipe('Chain', [P(1.15, 0.445, 0.10), P(RD, RZ + 0.105, 0.10), P(RD + 0.075, RZ + 0.075, 0.10), P(RD + 0.105, RZ, 0.10),
               P(RD + 0.075, RZ - 0.075, 0.10), P(RD, RZ - 0.105, 0.10), P(1.15, 0.365, 0.10), P(1.11, 0.405, 0.10)],
     0.009, FRAME, closed=True, res=1)
pipe('BrakePedal', [P(1.12, 0.36, -0.15), P(0.98, 0.33, -0.17), P(0.94, 0.35, -0.17)], 0.01, SILVER)

# ---------------------------------------------------------------- engine
box('Crankcase', P(1.00, 0.43), (0.24, 0.42, 0.30), METAL, 0.03)
box('Gearbox', P(1.12, 0.35), (0.20, 0.16, 0.16), METAL, 0.02)
box('Cylinder', P(0.91, 0.60), (0.17, 0.15, 0.17), METAL, 0.02, rot=(math.radians(-12), 0, 0))
for k in range(6):
    box('Fin', P(0.905 - k * 0.006, 0.535 + k * 0.03), (0.27, 0.22, 0.014), METAL, 0.004, rot=(math.radians(-12), 0, 0))
box('Head', P(0.93, 0.73), (0.19, 0.16, 0.07), METAL, 0.02, rot=(math.radians(-12), 0, 0))
cyl('ClutchCover', P(1.02, 0.42, 0.12), 0.085, 0.04, 'X', METAL, 24, 0.012)
cyl('ClutchCap', P(1.02, 0.42, 0.145), 0.045, 0.012, 'X', SILVER, 16)
cyl('IgnCover', P(0.98, 0.43, -0.12), 0.075, 0.04, 'X', METAL, 24, 0.012)
cyl('Carb', P(1.05, 0.66, 0.0), 0.04, 0.10, 'X', METAL, 12)
pipe('Header', [P(0.86, 0.66, 0.03), P(0.80, 0.60, 0.07), P(0.79, 0.46, 0.10), P(0.86, 0.38, 0.12), P(1.15, 0.50, 0.13),
                P(1.45, 0.70, 0.13), P(1.62, 0.80, 0.13)], 0.022, SILVER, round_r=0.07)
pipe('Muffler', [P(1.58, 0.795, 0.13), P(1.86, 0.865, 0.13)], 0.058, FRAME, res=3)
pipe('MufflerCap', [P(1.85, 0.862, 0.13), P(1.92, 0.88, 0.13)], 0.05, SILVER, res=3)
# skid plate
slab('Skid', [(0.76, 0.37), (0.80, 0.25), (1.13, 0.25), (1.14, 0.28), (0.83, 0.28), (0.79, 0.37)], 0.12, SILVER,
     chamfer=0.006, soft=0.004)
for k in range(3):
    box('SkidHole', P(0.88 + k * 0.08, 0.265, 0.121), (0.004, 0.04, 0.012), FRAME)

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
# weathering: low paint faces (mud splash on the fender skirts and side covers)
for i, p in enumerate(me.polygons):
    if mids[i] == MATS.index(PAINT) and p.center.z < 0.66:
        mids[i] = MATS.index(MUD)
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
seatE = bpy.data.objects.new('Seat', None); seatE.location = P(1.30, 0.99); scene.collection.objects.link(seatE)
seatE.parent = root
for o in scene.objects: o.select_set(False)
root.select_set(True); mdl.select_set(True); seatE.select_set(True)
bpy.ops.export_scene.fbx(filepath=f'{OUT}/{NAME}.fbx', use_selection=True, apply_unit_scale=True,
                         apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)

# ---------------------------------------------------------------- previews
world = bpy.data.worlds.new('W'); scene.world = world; world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.62, 0.62, 0.63, 1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.0
bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0)); ground = bpy.context.active_object
gm = bpy.data.materials.new('Ground'); gm.use_nodes = True
gm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.56, 0.56, 0.57, 1)
gm.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 1.0
ground.data.materials.append(gm)
bpy.ops.object.light_add(type='SUN', location=(0, 0, 10)); sun = bpy.context.active_object
sun.data.energy = 2.2; sun.rotation_euler = (math.radians(35), 0, math.radians(-150)); sun.data.angle = math.radians(25)
scene.render.engine = 'BLENDER_EEVEE'
scene.eevee.taa_render_samples = 48
try:
    scene.eevee.use_raytracing = True
except Exception:
    pass
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

# three-quarter: front to the right of frame, left side of the bike, ~60 deg off the nose
shoot('render-34', (-3.18, -2.67, 1.22), (0.0, -0.05, 0.60), 65)
# side: ortho, same scale and ground line as the reference (2.266 m across, centre 0.602 m up)
shoot('render-side', (12, 0.008, 0.602), (0, 0.008, 0.602), ortho=2.266)

# ---------------------------------------------------------------- compare.jpg (reference left, render right)
import numpy as np
W, H = 836, 470
def tile(path):
    im = bpy.data.images.load(path); im.scale(W, H)
    a = np.empty(W * H * 4, dtype=np.float32); im.pixels.foreach_get(a)
    return a.reshape(H, W, 4)
grid = np.ones((H * 2, W * 2, 4), dtype=np.float32)
for row, view in enumerate(('34', 'side')):  # pixel rows go bottom-up
    r = 1 - row
    grid[r * H:(r + 1) * H, 0:W] = tile(f'{REF}/ref-{view}.png')
    grid[r * H:(r + 1) * H, W:2 * W] = tile(f'{OUT}/render-{view}.png')
cmp = bpy.data.images.new('compare', W * 2, H * 2)
cmp.pixels.foreach_set(grid.ravel())
cmp.filepath_raw = f'{OUT}/compare.jpg'; cmp.file_format = 'JPEG'
scene.render.image_settings.quality = 90
cmp.save()
print(f'[{NAME}] done')

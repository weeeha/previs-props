# ATV (quad bike), previs library, round 2 (opus). Own design, no brands.
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_atv.py -- <out dir>
# 1 unit = 1 m, front toward -Y, up +Z, origin on the ground at the centre.
# Side reference: 2.0 m over 1465 px (1.365 mm/px), ground at y=905, front of bumper at x=120.
import bpy, sys, math, bmesh
from mathutils import Vector

OUT = sys.argv[sys.argv.index('--') + 1]
HERE = OUT
REF = './atv'
NAME = 'ATV'
L = 2.0

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

PAINT = mat('Paint', (0.135, 0.185, 0.075), 0.6)
MUD = mat('PaintWorn', (0.105, 0.115, 0.06), 0.8)     # weathering on low fender faces
RIM = mat('Rim', (0.12, 0.15, 0.065), 0.55)
SEATM = mat('Seat', (0.032, 0.030, 0.032), 0.85)
TRIM = mat('Trim', (0.055, 0.055, 0.058), 0.6)        # frame, racks, bumper, grille
METAL = mat('Metal', (0.16, 0.16, 0.16), 0.45, 0.3)   # engine, springs
TYRE = mat('Tyre', (0.03, 0.03, 0.03), 0.9)
LAMP = mat('Lamp', (0.85, 0.78, 0.62), 0.25, 0.0, 0.6)
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
        L_.append(bm.verts.new((xc - w, Y(d), z))); R_.append(bm.verts.new((xc + w, Y(d), z)))
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

# ---------------------------------------------------------------- wheels
WZ = 0.30                         # wheel centre height (tyre radius incl. lugs ~0.30)
TX = 0.485                        # track half width -> 1.2 m over tyres
DF, DR = 0.36, 1.63               # wheel centres from the front
TR = 0.255; TW = 0.21             # tyre core radius / width

def wheel(s, d):
    x = s * TX; y = Y(d)
    lathe('Tyre', x, y, WZ, [(0.168, -0.085), (0.20, -0.098), (0.232, -0.106), (0.252, -0.098), (TR, -0.075),
                             (TR, 0.075), (0.252, 0.098), (0.232, 0.106), (0.20, 0.098), (0.168, 0.085)], TYRE)
    n = 16
    for row, off in ((0, -0.047), (1, 0.047)):
        for k in range(n):
            t = 2 * math.pi * (k + 0.5 * row) / n
            rr = TR + 0.012
            box('Lug', (x + off, y + rr * math.cos(t), WZ + rr * math.sin(t)), (0.125, 0.088, 0.042), TYRE,
                0.008, rot=(t - math.pi / 2, 0, 0), segs=1)
    # rim: dished wheel with a lip, five vent holes and an octagonal hub (recessed inside the sidewall)
    cyl('Rim', (x, y, WZ), 0.172, 0.17, 'X', RIM, 32, 0.012)
    cyl('RimDish', (x + s * 0.083, y, WZ), 0.135, 0.012, 'X', RIM, 32)
    for k in range(5):
        t = 2 * math.pi * k / 5 + 0.3
        box('Vent', (x + s * 0.087, y + 0.092 * math.cos(t), WZ + 0.092 * math.sin(t)), (0.006, 0.052, 0.036),
            TRIM, rot=(t - math.pi / 2, 0, 0))
    cyl('Hub', (x + s * 0.093, y, WZ), 0.054, 0.022, 'X', RIM, 8, 0.006, 1, 50)
    cyl('HubNut', (x + s * 0.106, y, WZ), 0.027, 0.014, 'X', TRIM, 8)

for s in (-1, 1):
    for d in (DF, DR):
        wheel(s, d)

# ---------------------------------------------------------------- bodywork
def fender_hw(base, top_in):
    return lambda d, z: base - max(0.0, z - 0.66) * top_in

R_ARCH = 0.41
front = [(0.035, 0.575), (0.045, 0.76), (0.11, 0.815), (0.30, 0.83), (0.46, 0.83), (0.58, 0.79),
         (0.75, 0.52), (0.75, 0.49)] + arc(DF, WZ, R_ARCH, 27.6, 141)
FF = slab('FenderF', front, fender_hw(0.585, 0.55), PAINT, chamfer=0.06, soft=0.012)

rear = [(1.24, 0.49), (1.47, 0.79), (1.52, 0.825), (1.92, 0.83), (1.965, 0.79), (1.965, 0.62),
        (1.91, 0.60)] + arc(DR, WZ, R_ARCH, 47, 150)
RF = slab('FenderR', rear, fender_hw(0.585, 0.55), PAINT, chamfer=0.06, soft=0.012)
# raised hood between the front fenders, carries the front rack
slab('Hood', [(0.05, 0.78), (0.12, 0.865), (0.48, 0.875), (0.60, 0.84), (0.60, 0.78)],
     lambda d, z: 0.27 - max(0.0, z - 0.80) * 0.6, PAINT, chamfer=0.03, soft=0.01)
# dark inner wheel-well liners so the arches read solid
box('LinerF', P(0.38, 0.58), (0.40, 0.50, 0.26), TRIM, 0.02)
box('LinerR', P(1.62, 0.58), (0.40, 0.56, 0.24), TRIM, 0.02)

# central body: tank, side covers (narrower and tapering upward)
centre = [(0.56, 0.78), (0.60, 0.88), (0.66, 0.925), (0.80, 0.925), (0.86, 0.87), (0.98, 0.68), (1.28, 0.67),
          (1.38, 0.73), (1.52, 0.81), (1.40, 0.62), (1.30, 0.49), (1.10, 0.49), (1.02, 0.635), (0.72, 0.635),
          (0.62, 0.70)]
slab('Centre', centre, lambda d, z: 0.27 - max(0.0, z - 0.76) * 0.65, PAINT, chamfer=0.03, soft=0.01)
# seat: wider at the back, dipped in the middle
seat = [(0.84, 0.86), (0.87, 0.882), (0.95, 0.862), (1.07, 0.838), (1.30, 0.852), (1.46, 0.888), (1.53, 0.878),
        (1.53, 0.82), (1.36, 0.71), (1.28, 0.68), (0.98, 0.69), (0.90, 0.78)]
slab('Seat', seat, lambda d, z: 0.14 + (d - 0.84) * 0.10 - max(0.0, z - 0.80) * 0.4, SEATM, chamfer=0.02, soft=0.012)
cyl('FuelCap', P(0.73, 0.935), 0.045, 0.03, 'Z', TRIM, 8, 0.005)

# lower dark band under the rear of the side covers, and the nose block behind the grille
box('Band', P(1.14, 0.45), (0.46, 0.30, 0.10), TRIM, 0.015)
box('Nose', P(0.16, 0.48), (0.46, 0.24, 0.24), TRIM, 0.02)

# front face: grille with slats and two lamp housings
box('GrilleFrame', P(0.045, 0.565), (0.34, 0.03, 0.27), TRIM, 0.012)
for k in range(4):
    box('Slat', P(0.028, 0.46 + k * 0.06), (0.30, 0.02, 0.022), TRIM, 0.006)
for s in (-1, 1):
    box('LampHouse', P(0.045, 0.675, s * 0.33), (0.19, 0.035, 0.105), TRIM, 0.012, rot=(0, s * -0.12, 0))
    box('Lamp', P(0.032, 0.677, s * 0.335), (0.155, 0.02, 0.075), LAMP, 0.008, rot=(0, s * -0.12, 0))
    box('Tail', P(1.965, 0.73, s * 0.42), (0.10, 0.02, 0.055), RED, 0.006)

# engine (seen under the side cover)
box('Engine', P(0.92, 0.47), (0.36, 0.34, 0.30), METAL, 0.02)
for k in range(4):
    box('Fin', P(0.84, 0.50 + k * 0.035), (0.40, 0.12, 0.014), METAL, 0.004)
for s in (-1, 1):
    cyl('CrankCover', P(1.00, 0.42, s * 0.19), 0.085, 0.04, 'X', METAL, 24, 0.008)

# frame rails, footboards
for s in (-1, 1):
    pipe('Rail', [P(0.60, 0.42, s * 0.22), P(0.68, 0.25, s * 0.22), P(1.24, 0.25, s * 0.22), P(1.32, 0.44, s * 0.22)],
         0.028, TRIM, round_r=0.06)
    box('Footboard', P(0.97, 0.265, s * 0.37), (0.27, 0.52, 0.025), TRIM, 0.006)
    pipe('FootLip', [P(0.71, 0.27, s * 0.50), P(0.73, 0.30, s * 0.50), P(1.21, 0.30, s * 0.50), P(1.23, 0.27, s * 0.50)],
         0.012, TRIM)
    for k in range(4):
        box('Tread', P(0.80 + k * 0.11, 0.282, s * 0.37), (0.20, 0.03, 0.012), TRIM)

# ---------------------------------------------------------------- suspension
for s in (-1, 1):
    for d in (DF, DR):
        y = Y(d)
        pipe('ArmLo', [(s * 0.16, y - 0.12, 0.26), (s * 0.38, y, 0.28), (s * 0.16, y + 0.12, 0.26)], 0.016, TRIM)
        pipe('ArmHi', [(s * 0.18, y - 0.10, 0.40), (s * 0.36, y, 0.36), (s * 0.18, y + 0.10, 0.40)], 0.014, TRIM)
        cyl('Knuckle', (s * 0.38, y, WZ), 0.04, 0.06, 'X', TRIM, 12)
        a, b = (s * 0.30, y + 0.02, 0.33), (s * 0.24, y + 0.03, 0.70)
        pipe('Damper', [a, b], 0.016, METAL)
        helix('Spring', (s * 0.295, y + 0.022, 0.42), (s * 0.255, y + 0.028, 0.64), 0.034, 4.5, 0.008, METAL)
        cyl('SpringCap', ((a[0] * 0.3 + b[0] * 0.7), y + 0.028, 0.65), 0.04, 0.02, 'Z', TRIM, 12)

# ---------------------------------------------------------------- racks
def rack(d0, d1, hw, z, posts, zbase, raised=0.0):
    loop = [P(d0, z, -hw), P(d0, z, hw), P(d1, z, hw), P(d1, z, -hw)]
    pipe('RackLoop', loop, 0.018, TRIM, closed=True, round_r=0.06)
    zi = z - 0.03
    pipe('RackInner', [P(d0 + 0.04, zi, -hw + 0.04), P(d0 + 0.04, zi, hw - 0.04), P(d1 - 0.04, zi, hw - 0.04),
                       P(d1 - 0.04, zi, -hw + 0.04)], 0.012, TRIM, closed=True)
    for x in (-hw / 3, hw / 3):
        pipe('RackLong', [P(d0 + 0.04, zi, x), P(d1 - 0.04, zi, x)], 0.012, TRIM)
    for k in (1, 2):
        dd = d0 + (d1 - d0) * k / 3
        pipe('RackCross', [P(dd, zi, -hw + 0.04), P(dd, zi, hw - 0.04)], 0.012, TRIM)
        for s in (-1, 1):
            pipe('RackRung', [P(dd, z, s * hw), P(dd, zi, s * (hw - 0.04))], 0.011, TRIM)
    for s in (-1, 1):
        for dd in posts:
            pipe('RackPost', [P(dd, z, s * hw), P(dd, zbase, s * (hw - 0.02))], 0.014, TRIM)

rack(0.03, 0.50, 0.31, 0.96, (0.15, 0.40), 0.80)
rack(1.46, 1.99, 0.31, 0.98, (1.60, 1.88), 0.80)

# ---------------------------------------------------------------- bumper and skid plate
for s in (-1, 1):
    pipe('BumperSide', [P(0.12, 0.79, s * 0.27), P(0.01, 0.70, s * 0.27), P(0.01, 0.38, s * 0.27),
                        P(0.08, 0.27, s * 0.27), P(0.34, 0.27, s * 0.22)], 0.022, TRIM, round_r=0.05)
pipe('BumperTop', [P(0.01, 0.66, -0.27), P(0.01, 0.66, 0.27)], 0.02, TRIM)
pipe('BumperLow', [P(0.01, 0.40, -0.27), P(0.01, 0.40, 0.27)], 0.02, TRIM)
box('Skid', P(0.12, 0.30), (0.50, 0.14, 0.03), TRIM, 0.01, rot=(math.radians(-25), 0, 0))
for k in range(4):
    box('SkidSlot', P(0.065, 0.32, -0.15 + k * 0.1), (0.04, 0.012, 0.035), METAL, 0.003,
        rot=(math.radians(-25), 0, 0))
pipe('Exhaust', [P(1.30, 0.40, 0.16), P(1.70, 0.52, 0.20), P(1.90, 0.55, 0.20)], 0.035, METAL, round_r=0.08)

# ---------------------------------------------------------------- steering
pipe('Column', [P(0.66, 0.84), P(0.60, 1.06)], 0.026, TRIM)
box('Pod', P(0.585, 1.00), (0.21, 0.12, 0.12), TRIM, 0.025, rot=(math.radians(-15), 0, 0))
for s in (-1, 1):
    pipe('Bar', [P(0.60, 1.07, 0.0), P(0.61, 1.08, s * 0.10), P(0.65, 1.13, s * 0.18), P(0.71, 1.15, s * 0.255)],
         0.015, TRIM, round_r=0.03)
    pipe('Grip', [P(0.71, 1.15, s * 0.255), P(0.80, 1.15, s * 0.355)], 0.022, TRIM, res=3)
    for k in range(3):
        t = 0.3 + 0.25 * k
        pipe('GripRib', [P(0.71 + 0.09 * t - 0.004, 1.15, s * (0.255 + 0.1 * t - 0.004)),
                         P(0.71 + 0.09 * t + 0.004, 1.15, s * (0.255 + 0.1 * t + 0.004))], 0.026, TRIM)
    box('Perch', P(0.70, 1.145, s * 0.25), (0.05, 0.05, 0.05), TRIM, 0.008)
    pipe('Lever', [P(0.69, 1.14, s * 0.26), P(0.67, 1.12, s * 0.32), P(0.70, 1.10, s * 0.38)], 0.007, METAL)
    cyl('LeverEnd', P(0.70, 1.10, s * 0.385), 0.011, 0.02, 'X', METAL, 8)

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
bpy.context.view_layer.objects.active = FF
bpy.ops.object.join()
mdl = FF
mdl.data.transform(mdl.matrix_world); mdl.matrix_world.identity()
me = mdl.data
mids = [0] * len(me.polygons); me.attributes['mid'].data.foreach_get('value', mids)
# weathering: low paint faces (mud splash on the fender skirts and side covers)
for i, p in enumerate(me.polygons):
    if mids[i] == MATS.index(PAINT) and p.center.z < 0.56:
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
seatE = bpy.data.objects.new('Seat', None); seatE.location = P(1.15, 0.85); scene.collection.objects.link(seatE)
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

# three-quarter: front-left of frame, camera ~40 deg off the nose, ~15 deg down
shoot('render-34', (3.57, -2.89, 1.18), (0.0, -0.10, 0.50), 60)
# side: ortho, same scale and ground line as the reference (2.28 m across, centre 0.593 m up)
shoot('render-side', (12, -0.023, 0.593), (0, -0.023, 0.593), ortho=2.282)

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

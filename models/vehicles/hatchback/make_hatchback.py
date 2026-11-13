# Compact five-door hatchback (own design), library build (opus).
# Blender 5.1 headless:  Blender -b --python make_hatchback.py -- <out dir>
# d = metres back from the front bumper tip, front toward -Y. Proportions from ref-side.png, size real.
import bpy, sys, math, bmesh
from mathutils import Vector, Matrix
from bpy_extras.object_utils import world_to_camera_view

OUT = sys.argv[sys.argv.index('--') + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ------------------------------------------------------------------ model parameters
NAME = 'Hatchback'
SUV = False
L, BOT, FLOOR = 4.10, 0.22, 0.30
HW, CW, ROOF_HW = 0.88, 0.86, 0.70          # body, cabin base and roof half widths
WR, WT, WX, WD, RIM_R, ARCH = 0.32, 0.205, 0.765, [0.80, 3.46], 0.205, 0.06
WZ = WR
FRONT = [(0.07, 0.24), (0.0, 0.36), (0.0, 0.58), (0.05, 0.68), (0.16, 0.75)]
HOOD = [(0.16, 0.75), (0.50, 0.84), (0.80, 0.90), (1.08, 0.95)]
REAR = [(3.86, 1.00), (4.04, 1.00), (4.10, 0.86), (4.10, 0.36), (4.02, 0.24), (3.92, BOT)]
CP = [(1.08, 0.95), (1.84, 1.41), (2.08, 1.48), (3.24, 1.48), (3.62, 1.43), (4.04, 1.00)]
DB, DC, WIN_ZB, WIN_ZT = 2.38, 3.14, 1.02, 1.40
QW = (0.16, 0.34)                            # quarter window inset from the hatch line (top, bottom)
DOOR = [(1.22, 0.96), (1.20, 0.42), (1.28, 0.32), (2.98, 0.32), (3.04, 0.40), (3.04, 0.60), (3.24, 0.78), (3.24, 1.00)]
CHAMF_F, CHAMF_R = (0.24, 0.32), (0.14, 0.12)
SEAT = (0.36, 2.40, 0.54)                    # driver x, d, cushion top z
DASH = (1.45, 0.86)
PAINT_RGB = (0.30, 0.045, 0.040)
PLAST_RGB = (0.055, 0.056, 0.060)

# ------------------------------------------------------------------ derived
D0 = L / 2
def Y(d): return d - D0
LP = FRONT + HOOD[1:] + REAR + [(0.14, BOT)]
A, B, E, F = CP[0], CP[1], CP[-2], CP[-1]
ROOF = max(z for _, z in CP)
ZBELT = A[1]
KT = (1 - ROOF_HW / CW) / (ROOF - ZBELT)
GH = lambda z: 1.0 - KT * (z - ZBELT)       # greenhouse tumblehome (linear in z, faces stay planar)
def dA(z): return A[0] + (z - A[1]) * (B[0] - A[0]) / (B[1] - A[1])
def dH(z): return F[0] + (z - F[1]) * (E[0] - F[0]) / (E[1] - F[1])
def interp(pts, x):                          # pts sorted by first coordinate
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1: return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[0][1] if x < pts[0][0] else pts[-1][1]
def hood_z(d): return interp(HOOD, d)
def front_d(z): return interp(sorted([(zz, dd) for dd, zz in FRONT]), z)

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

PAINT = mat('Paint',    PAINT_RGB, 0.5)
PLAST = mat('Plastic',  PLAST_RGB, 0.8)
BLACK = mat('Black',    (0.012, 0.012, 0.013), 0.85)
GLASS = mat('Glass',    (0.22, 0.32, 0.36), 0.05, alpha=0.35)
LAMP  = mat('Lamp',     (0.85, 0.85, 0.80), 0.2, emit=0.15)
RED   = mat('Red',      (0.50, 0.01, 0.01), 0.35)
STEEL = mat('Steel',    (0.30, 0.31, 0.32), 0.45, metal=0.3)
SEATM = mat('Interior', (0.035, 0.037, 0.042), 0.9)

# ------------------------------------------------------------------ helpers (from the opus pickup)
parts, cutters = [], []
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
    """Side profile pts [(d, z)] extruded across X from x0 to x1. taper(z) scales x (linear: faces stay planar)."""
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

def cut(target, cutter, first=True):
    mod = target.modifiers.new('cut', 'BOOLEAN'); mod.operation = 'DIFFERENCE'; mod.object = cutter
    mod.solver = 'EXACT'
    if first: target.modifiers.move(len(target.modifiers) - 1, 0)
    cutter.hide_render = True; cutter.hide_viewport = True
    if cutter not in cutters: cutters.append(cutter)

def cutter_box(c, size, rot=(0, 0, 0)):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts: v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    o = new_obj('cutter', bm); o.location = c; o.rotation_euler = rot
    return o

def torus(name, c, R, r, m, rot=(0, 0, 0), maj=20, mnr=8):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=maj, minor_segments=mnr,
                                     location=c, rotation=rot)
    o = bpy.context.active_object; o.name = name
    return keep(o, m)

def seam(name, pts, x, m=BLACK, w=0.008, t=0.006):
    """Thin line on the body side through (d, z) points at x."""
    for (d0, z0), (d1, z1) in zip(pts, pts[1:]):
        ln = math.hypot(d1 - d0, z1 - z0)
        box(name, (x, Y((d0 + d1) / 2), (z0 + z1) / 2), (t, ln + w, w), m, rot=(math.atan2(z1 - z0, d1 - d0), 0, 0))

def grow(poly, w):
    """Convex (d, z) polygon -> (same polygon CCW, polygon offset outward by w)."""
    n = len(poly)
    if sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n)) < 0:
        poly = poly[::-1]
    lines = []
    for i in range(n):
        p, q = Vector(poly[i]), Vector(poly[(i + 1) % n]); t = (q - p).normalized()
        lines.append((p + Vector((t.y, -t.x)) * w, t))
    out = []
    for i in range(n):
        (p1, t1), (p2, t2) = lines[i - 1], lines[i]
        den = t1.x * t2.y - t1.y * t2.x
        a = ((p2.x - p1.x) * t2.y - (p2.y - p1.y) * t2.x) / den
        out.append(tuple(p1 + t1 * a))
    return poly, out

def along(fn, z0, z1, o0, o1):
    return [(fn(z0) + o0, z0), (fn(z1) + o0, z1), (fn(z1) + o1, z1), (fn(z0) + o1, z0)]

def arch(dc, R, bot, n=14):
    return [(dc + R, bot)] + [(dc + R * math.cos(math.pi * k / n), WZ + R * math.sin(math.pi * k / n)) for k in range(n + 1)] + [(dc - R, bot)]

def plan_chamfer(target, s, front, a, b):
    """Cut the plan-view corner off: a = inset across x, b = inset along the length."""
    if front:
        p1, p2 = Vector((s * (HW - a), Y(0))), Vector((s * HW, Y(b)))
        n = Vector((s * b, -a)).normalized()
    else:
        p1, p2 = Vector((s * (HW - a), Y(L))), Vector((s * HW, Y(L - b)))
        n = Vector((s * b, a)).normalized()
    u = p2 - p1; c = (p1 + p2) / 2 + n * 0.5
    cut(target, cutter_box((c.x, c.y, 0.8), (1.0, 1.0, 3.0), rot=(0, 0, math.atan2(u.y, u.x))))

# ------------------------------------------------------------------ body shell
lower = prism_x('Lower', LP, -HW, HW, PAINT, bev=0.035, segs=3)
cab = prism_x('Cab', CP, -CW, CW, PAINT, bev=0.03, segs=3, taper=GH)
for s in (-1, 1):
    plan_chamfer(lower, s, True, *CHAMF_F)
    plan_chamfer(lower, s, False, *CHAMF_R)
# hollow interior
cut(lower, cutter_box((0, Y((A[0] + 0.10 + L - 0.16) / 2), FLOOR + 0.5), (2 * HW - 0.12, L - 0.26 - A[0], 1.0)))
zb0, zr = ZBELT - 0.05, min(ROOF - 0.06, B[1] - 0.01)
cut(cab, prism_x('cabcut', [(dA(zb0) + 0.07, zb0), (dA(zr) + 0.07, zr), (dH(zr) - 0.07, zr), (dH(zb0) - 0.07, zb0)],
                 -(CW - 0.05), CW - 0.05, PAINT, taper=GH, keep_it=False))
# windshield and hatch openings, glass slightly inset
zbw, ztw = ZBELT + 0.05, B[1] - 0.02
cut(cab, prism_x('wscut', along(dA, zbw, ztw, -0.12, 0.30), -(CW - 0.11), CW - 0.11, PAINT, taper=GH, keep_it=False))
prism_x('Windshield', along(dA, zbw, ztw, 0.02, 0.032), -(CW - 0.09), CW - 0.09, GLASS, taper=GH)
zbh, zth = F[1] + 0.10, E[1] - 0.04
cut(cab, prism_x('hcut', along(dH, zbh, zth, -0.30, 0.12), -(CW - 0.13), CW - 0.13, PAINT, taper=GH, keep_it=False))
prism_x('RearGlass', along(dH, zbh, zth, -0.032, -0.02), -(CW - 0.11), CW - 0.11, GLASS, taper=GH)
# side windows: opening, black frame ring, glass
zb, zt = WIN_ZB, WIN_ZT
WINS = [[(dA(zb) + 0.15, zb), (dA(zt) + 0.15, zt), (DB - 0.05, zt), (DB - 0.05, zb)],
        [(DB + 0.05, zb), (DB + 0.05, zt), (DC - 0.04, zt), (DC - 0.04, zb)],
        [(DC + 0.04, zb), (DC + 0.04, zt), (dH(zt) - QW[0], zt), (dH(zb) - QW[1], zb)]]
for s in (-1, 1):
    for w in WINS:
        pw, gw = grow(w, 0.03)
        cut(cab, prism_x('wincut', gw, s * 0.5, s * 1.3, PAINT, taper=GH, keep_it=False))
        for i in range(len(pw)):
            prism_x('WinFrame', [pw[i], pw[(i + 1) % len(pw)], gw[(i + 1) % len(pw)], gw[i]],
                    s * (CW - 0.035), s * (CW - 0.004), BLACK, taper=GH)
        prism_x('SideGlass', pw, s * (CW - 0.03), s * (CW - 0.022), GLASS, taper=GH)
    for dp in (DB, DC):
        prism_x('Pillar', [(dp - 0.05, zb - 0.03), (dp - 0.05, zt + 0.03), (dp + 0.05, zt + 0.03), (dp + 0.05, zb - 0.03)],
                s * (CW - 0.01), s * (CW + 0.004), BLACK, taper=GH)

# wheel arches
for dc in WD:
    for s in (-1, 1):
        cut(lower, prism_x('archcut', arch(dc, WR + ARCH, BOT - 0.1), s * 0.55, s * 1.3, PAINT, keep_it=False))
        prism_x('Liner', arch(dc, WR + ARCH, WZ + 0.02), s * 0.53, s * 0.56, BLACK)
        if SUV:   # cladding flare band standing proud of the body
            ri, ro = WR + ARCH, WR + ARCH + 0.08
            n = 14
            ring_i = [(dc + ri * math.cos(math.pi * k / n), WZ + ri * math.sin(math.pi * k / n)) for k in range(n + 1)]
            ring_o = [(dc + ro * math.cos(math.pi * k / n), WZ + ro * math.sin(math.pi * k / n)) for k in range(n + 1)]
            ring_i = [(dc + ri, BOT + 0.02)] + ring_i + [(dc - ri, BOT + 0.02)]
            ring_o = [(dc + ro, BOT + 0.02)] + ring_o + [(dc - ro, BOT + 0.02)]
            for k in range(len(ring_i) - 1):
                prism_x('Flare', [ring_i[k], ring_o[k], ring_o[k + 1], ring_i[k + 1]],
                        s * (HW - 0.03), s * (HW + 0.02), PLAST, bev=0.008, segs=1)
    if dc == WD[1]:
        for s in (-1, 1):
            box('WheelTub', (s * (HW - 0.20), Y(dc), WZ + 0.25), (0.30, 2 * (WR + ARCH) + 0.05, 0.45), SEATM)

# ------------------------------------------------------------------ side details
for s in (-1, 1):
    x = s * (HW + 0.001)
    seam('DoorLine', DOOR, x)
    seam('DoorLineB', [(DB, 0.99), (DB, DOOR[2][1])], x)
    box('Crease', (s * (HW + 0.004), Y((HOOD[1][0] + REAR[0][0]) / 2), DOOR[2][1] + 0.50),
        (0.008, REAR[0][0] - HOOD[1][0], 0.035), PAINT, bev=0.003, segs=1)
    for d in ((DOOR[0][0] + DB) / 2 + 0.12, (DB + DC) / 2 + 0.12):
        box('Handle', (s * (HW + 0.014), Y(d), ZBELT - 0.09), (0.03, 0.17, 0.04), PLAST, bev=0.01)
    # sill cladding between the arches
    d0, d1 = WD[0] + WR + ARCH, WD[1] - WR - ARCH
    box('Sill', (s * (HW - 0.01), Y((d0 + d1) / 2), BOT + (0.07 if SUV else 0.04)),
        (0.06, d1 - d0, 0.14 if SUV else 0.08), PLAST, bev=0.015)
    # mirror: base on the door, arm, housing, glass
    md, mz = A[0] + 0.16, ZBELT + 0.06
    box('MirrorBase', (s * (CW * GH(mz) - 0.0), Y(md), mz), (0.05, 0.12, 0.08), BLACK, bev=0.01)
    box('MirrorArm', (s * (CW + 0.03), Y(md + 0.02), mz + 0.01), (0.08, 0.05, 0.04), BLACK, bev=0.01)
    box('Mirror', (s * (CW + 0.08), Y(md + 0.03), mz + 0.03), (0.13, 0.10, 0.11), PAINT, bev=0.03, segs=3)
    box('MirrorGlass', (s * (CW + 0.08), Y(md + 0.081), mz + 0.03), (0.10, 0.008, 0.08), GLASS)

# spoiler at the roof end
box('Spoiler', (0, Y(E[0] - 0.02), E[1] + 0.025), (2 * ROOF_HW * 0.98, 0.20, 0.045), PAINT, bev=0.02,
    rot=(math.radians(-6), 0, 0))
box('Brake', (0, Y(E[0] + 0.085), E[1] + 0.005), (0.30, 0.02, 0.02), RED)

# ------------------------------------------------------------------ front
TH = math.atan2(CHAMF_F[1], CHAMF_F[0])          # plan angle of the front corners
for s in (-1, 1):
    if SUV:
        hz = FRONT[-2][1] - 0.04
        box('Headlight', (s * (HW - 0.24), Y(front_d(hz) + 0.07), hz), (0.40, 0.16, 0.10), LAMP, bev=0.02,
            rot=(0, 0, s * math.radians(20)))
        box('LampHouse', (s * (HW - 0.24), Y(front_d(hz) + 0.09), hz), (0.44, 0.16, 0.14), BLACK, bev=0.02,
            rot=(0, 0, s * math.radians(20)))
        box('FogHouse', (s * (HW - 0.22), Y(0.035), 0.52), (0.20, 0.06, 0.10), BLACK, bev=0.015)
        box('Fog', (s * (HW - 0.22), Y(0.008), 0.52), (0.13, 0.02, 0.06), LAMP, bev=0.008)
    else:
        hz = 0.665
        fd = front_d(hz)
        box('Headlight', (s * (HW - CHAMF_F[0] - 0.11), Y(fd + 0.035), hz), (0.24, 0.08, 0.11), LAMP, bev=0.02,
            rot=(math.radians(-25), 0, 0))
        p1, p2 = Vector((s * (HW - CHAMF_F[0]), Y(0))), Vector((s * HW, Y(CHAMF_F[1])))
        u = p2 - p1; n = Vector((s * CHAMF_F[1], -CHAMF_F[0])).normalized()
        c = p1 + u * 0.36 - n * 0.04
        box('HeadlightC', (c.x, c.y, hz), (u.length * 0.62, 0.08, 0.11), LAMP, bev=0.02,
            rot=(0, 0, math.atan2(u.y, u.x)))
if SUV:
    gz = 0.78
    box('Grille', (0, Y(0.035), gz), (1.02, 0.06, 0.30), BLACK, bev=0.01)
    for dz in (-0.16, 0.16):
        box('GrilleFrame', (0, Y(0.02), gz + dz), (1.08, 0.05, 0.035), PLAST, bev=0.01)
    for s in (-1, 1):
        box('GrilleFrameS', (s * 0.53, Y(0.02), gz), (0.035, 0.05, 0.33), PLAST, bev=0.01)
    for dz in (-0.08, 0.0, 0.08):
        box('GrilleBar', (0, Y(0.012), gz + dz), (0.98, 0.04, 0.03), PLAST, bev=0.008)
    box('BumperF', (0, Y(0.10), 0.42), (2 * HW - 0.16, 0.24, 0.24), PLAST, bev=0.05, segs=3)
    box('Intake', (0, Y(-0.012), 0.44), (0.90, 0.02, 0.09), BLACK)
    box('Skid', (0, Y(0.02), 0.33), (1.00, 0.10, 0.06), STEEL, bev=0.02, rot=(math.radians(20), 0, 0))
else:
    box('GrilleBand', (0, Y(0.045), 0.635), (0.80, 0.06, 0.085), BLACK, bev=0.01)
    box('Intake', (0, Y(0.025), 0.42), (0.96, 0.06, 0.17), BLACK, bev=0.015)
    for dz in (-0.04, 0.03):
        box('IntakeSlat', (0, Y(0.004), 0.42 + dz), (0.90, 0.03, 0.022), PLAST)
    box('LipF', (0, Y(0.20), BOT + 0.01), (1.20, 0.20, 0.03), PLAST, bev=0.01)

# ------------------------------------------------------------------ rear
TR = math.atan2(CHAMF_R[1], CHAMF_R[0])
rz = REAR[1][1] - 0.10
for s in (-1, 1):
    box('TailLight', (s * (HW - 0.14), Y(L - 0.05), rz), (0.26 if SUV else 0.22, 0.12, 0.13 if SUV else 0.20), RED,
        bev=0.02, rot=(0, 0, -s * math.radians(25)))
    box('Reflector', (s * (HW - 0.18), Y(L + 0.002), BOT + 0.17), (0.12, 0.01, 0.03), RED)
    box('TailgateLine', (s * (HW - 0.24), Y(L + 0.002), (rz - 0.12 + REAR[0][1]) / 2), (0.008, 0.006, REAR[0][1] - rz + 0.12), BLACK)
box('TailgateLineH', (0, Y(L + 0.002), rz - 0.12), (2 * HW - 0.48, 0.006, 0.008), BLACK)
box('Plate', (0, Y(L - 0.002), rz - 0.27), (0.52, 0.012, 0.12), PLAST, bev=0.004)
box('HatchHandle', (0, Y(L + 0.004), rz - 0.17), (0.18, 0.02, 0.03), PLAST, bev=0.006)
box('BumperR', (0, Y(L - 0.08), BOT + 0.10), (2 * HW - 0.18, 0.18, 0.20 if SUV else 0.10), PLAST, bev=0.03)
if SUV:
    box('SkidR', (0, Y(L + 0.01), BOT + 0.06), (0.90, 0.04, 0.06), STEEL, bev=0.01)
cyl('ExhaustTip', (-0.55, Y(L - 0.05), BOT + 0.04), 0.035, 0.16, 'Y', STEEL, 12)

# ------------------------------------------------------------------ roof rails (SUV)
if SUV:
    for s in (-1, 1):
        xr = s * (ROOF_HW - 0.10)
        box('Rail', (xr, Y((CP[2][0] + CP[3][0]) / 2), ROOF + 0.065), (0.04, CP[3][0] - CP[2][0] - 0.15, 0.03), BLACK, bev=0.01)
        for d in (CP[2][0] + 0.12, CP[3][0] - 0.12):
            box('RailFoot', (xr, Y(d), ROOF + 0.03), (0.05, 0.10, 0.06), BLACK, bev=0.012)

# ------------------------------------------------------------------ interior
sx, sd, sz = SEAT
box('CabFloor', (0, Y((A[0] + L - 0.16) / 2), FLOOR + 0.01), (2 * HW - 0.14, L - 0.20 - A[0], 0.02), SEATM)
box('Dash', (0, Y(DASH[0]), DASH[1]), (2 * CW - 0.14, 0.40, 0.22), SEATM, bev=0.04)
box('DashTop', (0, Y(DASH[0] - 0.06), DASH[1] + 0.12), (2 * CW - 0.20, 0.26, 0.05), SEATM, bev=0.02)
for s in (-1, 1):
    box('DoorPanel', (s * (HW - 0.07), Y((A[0] + L - 0.2) / 2), (FLOOR + ZBELT) / 2 + 0.02), (0.02, L - 0.3 - A[0], ZBELT - FLOOR), SEATM)
box('Console', (0, Y(sd - 0.25), FLOOR + 0.16), (0.24, 0.80, 0.30), SEATM, bev=0.03)
for x in (-sx, sx):
    box('SeatBase', (x, Y(sd), sz - 0.07), (0.50, 0.50, 0.14), SEATM, bev=0.04)
    box('SeatBack', (x, Y(sd + 0.27), sz + 0.27), (0.50, 0.12, 0.60), SEATM, bev=0.04, rot=(math.radians(-12), 0, 0))
    box('Headrest', (x, Y(sd + 0.34), sz + 0.66), (0.26, 0.09, 0.16), SEATM, bev=0.03, rot=(math.radians(-12), 0, 0))
    box('SeatPost', (x, Y(sd), (FLOOR + sz - 0.14) / 2), (0.36, 0.36, sz - 0.14 - FLOOR), BLACK)
rb = sd + 0.82
box('RearBench', (0, Y(rb), sz - 0.07), (2 * CW - 0.30, 0.48, 0.14), SEATM, bev=0.04)
box('RearBack', (0, Y(rb + 0.26), sz + 0.24), (2 * CW - 0.30, 0.12, 0.56), SEATM, bev=0.04, rot=(math.radians(-10), 0, 0))
box('RearBase', (0, Y(rb), (FLOOR + sz - 0.14) / 2), (2 * CW - 0.34, 0.44, sz - 0.14 - FLOOR), BLACK)
SWC = (sx, Y(sd - 0.48), sz + 0.38)
torus('SteeringWheel', SWC, 0.18, 0.018, BLACK, rot=(math.radians(-60), 0, 0), maj=24, mnr=6)
box('Spoke', SWC, (0.32, 0.025, 0.03), BLACK, rot=(math.radians(-60), 0, 0))
cyl('Column', (sx, Y(sd - 0.62), sz + 0.32), 0.03, 0.30, 'Y', BLACK, 12, rot=(math.radians(30) + math.pi / 2, 0, 0))

# ------------------------------------------------------------------ chassis
for dc in WD:
    cyl('Axle', (0, Y(dc), WZ), 0.04, 2 * WX - 0.2, 'X', BLACK, 12)
box('Underbody', (0, Y(L / 2), BOT + 0.01), (2 * HW - 0.4, L - 0.6, 0.02), BLACK)

# ------------------------------------------------------------------ wheels (road tyres, five-spoke alloys)
def wheel(c, axis_dir):
    ax = Vector(axis_dir)
    rot = ax.to_track_quat('Z', 'Y').to_euler()
    M = Matrix.Translation(c) @ rot.to_matrix().to_4x4()
    R = tuple(rot)
    def p(z, x=0.0, y=0.0): return (M @ Vector((x, y, z)))
    o = WT / 2
    cyl('Tyre', c, WR, WT, 'Z', BLACK, 32, WR * 0.17, 2, rot=R)
    cyl('RimWell', p(o - 0.005), RIM_R + 0.008, 0.02, 'Z', BLACK, 32, rot=R)
    torus('RimLip', p(o + 0.003), RIM_R, 0.013, STEEL, rot=R, maj=32, mnr=6)
    for k in range(5):
        a = k * 2 * math.pi / 5 + math.pi / 2
        Mk = M @ Matrix.Rotation(a, 4, 'Z') @ Matrix.Translation((RIM_R * 0.55, 0, o + 0.008))
        loc, q, _ = Mk.decompose()
        box('Spoke', loc, (RIM_R * 0.85, RIM_R * 0.34, 0.022), STEEL, bev=0.008, rot=tuple(q.to_euler()))
    cyl('HubDisc', p(o + 0.008), RIM_R * 0.40, 0.024, 'Z', STEEL, 24, 0.008, 1, rot=R)
    cyl('HubCap', p(o + 0.025), RIM_R * 0.18, 0.02, 'Z', STEEL, 8, 0.006, 1, rot=R)
    for k in range(5):
        a = k * 2 * math.pi / 5
        cyl('Lug', p(o + 0.024, RIM_R * 0.28 * math.cos(a), RIM_R * 0.28 * math.sin(a)), 0.009, 0.02, 'Z', BLACK, 6, rot=R)
for dc in WD:
    for s in (-1, 1):
        wheel(Vector((s * WX, Y(dc), WZ)), (s, 0, 0))

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
seat = bpy.data.objects.new('Seat', None); seat.location = (sx, Y(sd), sz)
scene.collection.objects.link(seat); seat.parent = root
for o in scene.objects: o.select_set(o in (root, body, seat))
bpy.ops.export_scene.fbx(filepath=f'{OUT}/{NAME}.fbx', use_selection=True, apply_unit_scale=True,
                         apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)

# ------------------------------------------------------------------ previews (match the reference framing)
world = bpy.data.worlds.new('W'); scene.world = world; world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.70, 0.70, 0.71, 1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.0
bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0)); ground = bpy.context.active_object
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

def frame_bounds():
    bpy.context.view_layer.update()
    cs = [world_to_camera_view(scene, cam, p) for p in PTS]
    return min(c.x for c in cs), max(c.x for c in cs), min(c.y for c in cs), max(c.y for c in cs)

def shoot34(yaw_deg, elev_deg, lens, box_px, side):
    cam_data.type = 'PERSP'; cam_data.lens = lens
    yaw, el = math.radians(yaw_deg), math.radians(elev_deg)
    dirv = Vector((side * math.sin(yaw) * math.cos(el), -math.cos(yaw) * math.cos(el), math.sin(el)))
    tgt = Vector((0, 0, ROOF / 2)); dist = 9.0
    W, H = 1672.0, 941.0
    want = ((box_px[0] + box_px[1]) / 2 / W, 1 - (box_px[2] + box_px[3]) / 2 / H,
            (box_px[1] - box_px[0]) / W, (box_px[3] - box_px[2]) / H)
    for _ in range(12):
        cam.location = tgt + dirv * dist
        cam.rotation_euler = (-dirv).to_track_quat('-Z', 'Y').to_euler()
        x0, x1, y0, y1 = frame_bounds()
        k = max((x1 - x0) / want[2], (y1 - y0) / want[3])
        dist *= k ** 0.9
        right = cam.matrix_world.to_3x3() @ Vector((1, 0, 0)); up = cam.matrix_world.to_3x3() @ Vector((0, 1, 0))
        vw = dist * 36.0 / lens
        tgt += right * ((x0 + x1) / 2 - want[0]) * vw + up * ((y0 + y1) / 2 - want[1]) * vw * H / W
    scene.render.filepath = f'{OUT}/render-34.png'; bpy.ops.render.render(write_still=True)

def shoot_side(box_px):
    W, H = 1672.0, 941.0
    cam_data.type = 'ORTHO'
    Lb = max(ys) - min(ys)
    cam_data.ortho_scale = Lb / ((box_px[1] - box_px[0]) / W)
    cx_frac = (box_px[0] + box_px[1]) / 2 / W
    ground_frac = 1 - box_px[3] / H
    yc = (min(ys) + max(ys)) / 2 - (cx_frac - 0.5) * cam_data.ortho_scale
    zc = (0.5 - ground_frac) * cam_data.ortho_scale * H / W
    cam.location = (20, yc, zc); cam.rotation_euler = (math.pi / 2, 0, math.pi / 2)
    scene.render.filepath = f'{OUT}/render-side.png'; bpy.ops.render.render(write_still=True)

sun.rotation_euler = (math.radians(35), 0, math.radians(150))
shoot34(40, 9, 70, (115, 1575, 80, 885), side=1)
sun.rotation_euler = (math.radians(30), 0, math.radians(60))
shoot_side((50, 1618, 172, 850))

# ------------------------------------------------------------------ compare.jpg (reference left, render right)
import numpy as np
W2, H2 = 836, 470
def tile(path):
    im = bpy.data.images.load(path); im.scale(W2, H2)
    a = np.empty(W2 * H2 * 4, dtype=np.float32); im.pixels.foreach_get(a)
    return a.reshape(H2, W2, 4)
grid = np.ones((H2 * 2, W2 * 2, 4), dtype=np.float32)
for row, view in enumerate(('34', 'side')):
    r = 1 - row
    grid[r * H2:(r + 1) * H2, 0:W2] = tile(f'{OUT}/ref-{view}.png')
    grid[r * H2:(r + 1) * H2, W2:2 * W2] = tile(f'{OUT}/render-{view}.png')
cmp = bpy.data.images.new('compare', W2 * 2, H2 * 2)
cmp.pixels.foreach_set(grid.ravel())
cmp.filepath_raw = f'{OUT}/compare.jpg'; cmp.file_format = 'JPEG'
cmp.save()
print(f'[{NAME}] done')

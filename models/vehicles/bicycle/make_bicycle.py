# Builds a generic step-through city bicycle at previs-library detail (own design, no brands) and renders a preview.
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_bicycle.py -- <out dir> [diag]
# Convention: 1 unit = 1 m, front toward -Y, up +Z, origin on the ground at the centre. Bike plane is x = 0;
# the drivetrain and chain guard sit on the rider's right (-X), as on a real bike.
# Size target from the brief: about 1.8 x 0.6 x 1.05 m (28-inch wheels, 1.10 m wheelbase, 0.60 m bars).
import bpy, sys, math, bmesh
from mathutils import Vector

ARGS = sys.argv[sys.argv.index('--') + 1:]
OUT = ARGS[0]
DIAG = len(ARGS) > 1

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

MATS = {}
def mat(name, rgb, rough=0.6, metal=0.0, emit=0.0, alpha=1.0):
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
    return m

parts, cutters = [], []
def orient_out(bm):
    """Closed meshes: make normals point outward (signed volume > 0). Mirrored builds otherwise come out inside-out."""
    if not bm.faces or not all(e.is_manifold for e in bm.edges): return
    vol = 0.0
    for f in bm.faces:
        vs = [v.co for v in f.verts]
        for i in range(1, len(vs) - 1): vol += vs[0].dot(vs[i].cross(vs[i + 1]))
    if vol < 0: bmesh.ops.reverse_faces(bm, faces=bm.faces)

def link(name, bm, m, store=True):
    orient_out(bm)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); scene.collection.objects.link(o)
    me.materials.append(m)
    if store: parts.append(o)
    return o

def bevel(o, w, segs=2, angle=40):
    b = o.modifiers.new('bevel', 'BEVEL'); b.width = w; b.segments = segs
    b.limit_method = 'ANGLE'; b.angle_limit = math.radians(angle)
    return o

def loft(name, sections, m, closed=True, caps=True):
    bm = bmesh.new()
    rings = [[bm.verts.new(p) for p in s] for s in sections]
    n = len(sections[0])
    for a, b in zip(rings, rings[1:]):
        for i in range(n if closed else n - 1):
            j = (i + 1) % n
            bm.faces.new((a[i], a[j], b[j], b[i]))
    if caps and closed:
        bm.faces.new(rings[0]); bm.faces.new(rings[-1][::-1])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return link(name, bm, m)

def hull(name, pts, m, store=True):
    bm = bmesh.new()
    for p in pts: bm.verts.new(p)
    bmesh.ops.convex_hull(bm, input=bm.verts)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return link(name, bm, m, store)

def box(name, c, s, m, bev=0.0, rot=None):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    for v in bm.verts:
        v.co = Vector((v.co.x * s[0], v.co.y * s[1], v.co.z * s[2]))
        if rot: v.co.rotate(rot)
        v.co += Vector(c)
    o = link(name, bm, m)
    if bev: bevel(o, bev)
    return o

def prism(name, outline, z0, z1, m, bev=0.0):   # outline: [(x, y)] in any winding
    bm = bmesh.new()
    lo = [bm.verts.new((x, y, z0)) for x, y in outline]
    hi = [bm.verts.new((x, y, z1)) for x, y in outline]
    n = len(outline)
    bm.faces.new(lo); bm.faces.new(hi)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = link(name, bm, m)
    if bev: bevel(o, bev)
    return o

def lathe(name, prof, m, centre, side, segs=32, closed=False):
    """Revolve [(radius, axial)] around the X axis through centre; axial grows outward (side = +-1)."""
    cx, cy, cz = centre
    bm = bmesh.new(); rings = []
    for r, a in prof:
        x = cx + side * a
        if r < 1e-6:
            rings.append([bm.verts.new((x, cy, cz))])
        else:
            rings.append([bm.verts.new((x, cy + r * math.cos(2 * math.pi * k / segs), cz + r * math.sin(2 * math.pi * k / segs))) for k in range(segs)])
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if closed else [])
    for a, b in pairs:
        if len(a) == 1 and len(b) == 1: continue
        if len(a) == 1:
            for k in range(segs): bm.faces.new((a[0], b[k], b[(k + 1) % segs]))
        elif len(b) == 1:
            for k in range(segs): bm.faces.new((a[k], a[(k + 1) % segs], b[0]))
        else:
            for k in range(segs):
                k2 = (k + 1) % segs
                bm.faces.new((a[k], a[k2], b[k2], b[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return link(name, bm, m)


FRAME = mat('Frame', (0.085, 0.215, 0.180), 0.55)        # muted teal
BLACK = mat('Black', (0.014, 0.014, 0.015), 0.8)
STEEL = mat('Steel', (0.42, 0.43, 0.45), 0.45, 0.2)
LEATHER = mat('Leather', (0.155, 0.072, 0.040), 0.7)
LAMP = mat('LampClear', (0.62, 0.64, 0.64), 0.2)
ORDER = [FRAME, BLACK, STEEL, LEATHER, LAMP]

def V(y, z, x=0.0): return Vector((x, y, z))

def catmull(pts, n=6):
    """Smooth path through control points (Catmull-Rom), n samples per span."""
    P = [Vector(p) for p in pts]
    P = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(n):
            t = k / n
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    return out + [P[-2]]

def sweep(name, path, m, r=0.02, segs=12, r_end=None):
    """Round tube along a polyline with parallel-transport frames, capped."""
    path = [Vector(p) for p in path]
    bm = bmesh.new(); rings = []
    n = None
    for i, p in enumerate(path):
        t = (path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]).normalized()
        if n is None:
            ref = Vector((1, 0, 0)) if abs(t.x) < 0.9 else Vector((0, 0, 1))
            n = (ref - t * ref.dot(t)).normalized()
        else:
            n = (n - t * n.dot(t)).normalized()
        b = t.cross(n)
        rr = r if r_end is None else r + (r_end - r) * i / (len(path) - 1)
        rings.append([bm.verts.new(p + rr * (math.cos(2 * math.pi * k / segs) * n + math.sin(2 * math.pi * k / segs) * b)) for k in range(segs)])
    for a, b2 in zip(rings, rings[1:]):
        for k in range(segs):
            k2 = (k + 1) % segs
            bm.faces.new((a[k], a[k2], b2[k2], b2[k]))
    bm.faces.new(rings[0]); bm.faces.new(rings[-1][::-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return link(name, bm, m)

def tube(name, a, b, m, r=0.02, segs=12): return sweep(name, [a, b], m, r, segs)

# ------------------------------------------------------------------ key points (y forward is negative)
WR = 0.350                       # 28-inch wheel outer radius
FA, RA = V(-0.550, WR), V(0.550, WR)          # axles
BB = V(0.050, 0.280)                          # bottom bracket
AX = Vector((0, 0.375, 0.927))                # steering axis, pointing up (and back toward the rider)
H0 = V(-0.400, 0.660); H1 = H0 + AX * 0.170  # head tube bottom / top
SC = V(0.190, 0.780)                          # seat cluster
SEAT_TOP = V(0.225, 0.965)

# ------------------------------------------------------------------ wheels
TYRE = [(0.306, -0.012), (0.318, -0.021), (0.333, -0.022), (0.345, -0.015), (0.350, 0.0), (0.345, 0.015),
        (0.333, 0.022), (0.318, 0.021), (0.306, 0.012)]
RIM = [(0.290, -0.011), (0.309, -0.012), (0.309, 0.012), (0.290, 0.011), (0.282, 0.0)]
for c in (FA, RA):
    lathe('Tyre', TYRE, BLACK, tuple(c), 1, 32, closed=True)
    lathe('Rim', RIM, STEEL, tuple(c), 1, 32, closed=True)
    lathe('Hub', [(0.0, -0.060), (0.012, -0.060), (0.016, -0.045), (0.030, -0.040), (0.030, -0.030), (0.018, -0.026),
                  (0.018, 0.026), (0.030, 0.030), (0.030, 0.040), (0.016, 0.045), (0.012, 0.060), (0.0, 0.060)],
          STEEL, tuple(c), 1, 16)
    # 32 tangent-laced spokes, alternating flanges
    for k in range(32):
        side = 1 if k % 2 else -1
        a_hub = 2 * math.pi * k / 32
        a_rim = a_hub + side * 0.32 * (1 if (k // 2) % 2 else -1)
        hub = c + Vector((side * 0.035, 0.026 * math.cos(a_hub), 0.026 * math.sin(a_hub)))
        rim = c + Vector((0.0, 0.284 * math.cos(a_rim), 0.284 * math.sin(a_rim)))
        tube('Spoke', hub, rim, STEEL, 0.0022, 4)
    for s in (-1, 1):
        box('AxleNut', (s * 0.062, c.y, c.z), (0.012, 0.022, 0.022), STEEL, 0.004)

# ------------------------------------------------------------------ frame
TR = 0.019
sweep('LoopTube', catmull([H0 + AX * 0.125, V(-0.300, 0.640), V(-0.205, 0.470), V(-0.110, 0.405), V(0.035, 0.395),
                           V(0.118, 0.430)]), FRAME, TR)
sweep('DownTube', catmull([H0 + AX * 0.030, V(-0.320, 0.520), V(-0.215, 0.360), V(-0.080, 0.290), BB]), FRAME, TR)
sweep('SeatTube', [BB, SC + (SC - BB).normalized() * 0.02], FRAME, 0.017)
sweep('HeadTube', [H0 - AX * 0.01, H1], FRAME, 0.025, 16)
for p in (H0 - AX * 0.012, H1 + AX * 0.004):
    sweep('HeadSet', [p - AX * 0.012, p + AX * 0.012], BLACK, 0.029, 16)
lathe('BBShell', [(0.0, -0.040), (0.024, -0.040), (0.024, 0.040), (0.0, 0.040)], FRAME, tuple(BB), 1, 16)
for s in (-1, 1):
    drop = RA + Vector((s * 0.062, 0, 0))
    sweep('ChainStay', catmull([BB + Vector((s * 0.025, 0.02, 0)), BB + Vector((s * 0.058, 0.18, 0.02)), drop]), FRAME, 0.011, 8)
    sweep('SeatStay', catmull([SC + Vector((s * 0.018, 0.012, -0.03)), SC + Vector((s * 0.045, 0.16, -0.17)), drop]), FRAME, 0.010, 8)
    box('Dropout', tuple(drop), (0.010, 0.050, 0.040), FRAME, 0.005)
sweep('SeatClamp', [SC - (SC - BB).normalized() * 0.005, SC + (SC - BB).normalized() * 0.035], BLACK, 0.021, 12)
sweep('SeatPost', [SC, SEAT_TOP - Vector((0, 0.0, 0.035))], STEEL, 0.0135, 12)

# fork: crown under the head tube, two legs curving forward to the axle
crown = H0 - AX * 0.045
box('ForkCrown', tuple(crown), (0.14, 0.05, 0.035), FRAME, 0.012)
for s in (-1, 1):
    top, end = crown + Vector((s * 0.052, 0, -0.01)), FA + Vector((s * 0.060, 0, 0))
    leg = catmull([top, top.lerp(end, 0.5) + Vector((0, -0.010, 0)), end], 6)     # straight leg, slight forward bow
    sweep('ForkLeg', leg, FRAME, 0.0145, 10, r_end=0.010)
sweep('Steerer', [H1, H1 + AX * 0.14], STEEL, 0.017, 12)

# stem and swept-back city bar
stem_top = H1 + AX * 0.14
clamp = stem_top + Vector((0, -0.030, 0.012))
sweep('Stem', [H1 + AX * 0.06, stem_top, clamp], STEEL, 0.017, 12)
bar_r = [Vector(p) for p in ((0.0, clamp.y, clamp.z), (0.07, clamp.y - 0.005, clamp.z + 0.004), (0.15, clamp.y + 0.020, clamp.z + 0.030),
                              (0.22, clamp.y + 0.090, clamp.z + 0.055), (0.255, clamp.y + 0.160, clamp.z + 0.060),
                              (0.290, clamp.y + 0.205, clamp.z + 0.060))]
bar = catmull([Vector((-p.x, p.y, p.z)) for p in reversed(bar_r)] + bar_r[1:], 5)
sweep('Handlebar', bar, STEEL, 0.0115, 12)
lathe('BarClamp', [(0.0, -0.028), (0.020, -0.028), (0.020, 0.028), (0.0, 0.028)], STEEL, tuple(clamp), 1, 12)
for s in (-1, 1):
    a = Vector((s * 0.205, clamp.y + 0.115, clamp.z + 0.058)); b = Vector((s * 0.300, clamp.y + 0.215, clamp.z + 0.060))
    d = (b - a).normalized()
    sweep('Grip', [a + d * 0.0, b + d * 0.008], LEATHER, 0.0175, 12)
    # brake lever: clamp on the bar, blade reaching forward under the grip
    sweep('LeverClamp', [a - d * 0.025, a - d * 0.005], BLACK, 0.017, 10)
    blade = catmull([a - d * 0.015 + Vector((0, -0.02, -0.005)), a + d * 0.03 + Vector((0, -0.07, -0.02)),
                     a + d * 0.085 + Vector((0, -0.06, -0.03))], 4)
    sweep('Lever', blade, BLACK, 0.0055, 6)
# bell on the left of the bar: a small dome on a clamp
bx = 0.115; bp = Vector((bx, clamp.y + 0.002, clamp.z + 0.008))
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.026, radius2=0.012, depth=0.020)
for v in bm.verts: v.co += bp + Vector((0, 0, 0.030))
link('Bell', bm, STEEL); bevel(parts[-1], 0.004, 2, 40)
tube('BellPost', bp, bp + Vector((0, 0, 0.022)), BLACK, 0.006, 8)

# ------------------------------------------------------------------ saddle
def saddle_sec(y, w, top, th):
    return [(sx * w * f, y, top - th * g) for sx, (f, g) in
            [(1, (0.0, 0.0)), (1, (0.55, 0.06)), (1, (0.92, 0.30)), (1, (1.0, 0.65)), (1, (0.80, 1.0)), (1, (0.0, 1.0))]] + \
           [(-w * f, y, top - th * g) for f, g in [(0.80, 1.0), (1.0, 0.65), (0.92, 0.30), (0.55, 0.06)]]
SY, SZ = SEAT_TOP.y, SEAT_TOP.z
SAD = [(-0.135, 0.022, -0.006), (-0.110, 0.030, -0.002), (-0.060, 0.045, 0.0), (-0.010, 0.072, 0.0), (0.040, 0.098, 0.002),
       (0.085, 0.108, 0.004), (0.112, 0.100, 0.003), (0.128, 0.075, 0.0)]
secs = []
for dy, w, dz in SAD:
    sec = saddle_sec(SY + dy, w, SZ + dz, 0.055)
    secs.append([(x, y, z) for x, y, z in sec])
loft('Saddle', secs, LEATHER)
bevel(parts[-1], 0.006, 2, 40)
box('SaddleRails', (0, SY + 0.03, SZ - 0.062), (0.10, 0.15, 0.016), BLACK, 0.006)
for s in (-1, 1):
    sweep('Spring', [V(SY + 0.075, SZ - 0.050, s * 0.05), V(SY + 0.075, SZ - 0.105, s * 0.05)], BLACK, 0.013, 10)

# ------------------------------------------------------------------ mudguards
def guard(name, c, a0, a1, R=0.385, hw=0.030, n=30):
    secs = []
    prof = [(-hw, -0.014), (-0.8 * hw, 0.000), (0.0, 0.006), (0.8 * hw, 0.000), (hw, -0.014),
            (0.8 * hw, -0.004), (0.0, 0.002), (-0.8 * hw, -0.004)]
    for k in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * k / n)
        rad = Vector((0, math.cos(a), math.sin(a)))
        secs.append([tuple(c + rad * (R + dr) + Vector((x, 0, 0))) for x, dr in prof])
    o = loft(name, secs, FRAME); bevel(o, 0.002, 1, 50); return o
guard('FrontGuard', FA, 200, 20)          # angles from +Y (rearward) round over the top to the front
guard('RearGuard', RA, 170, -10)
for s in (-1, 1):
    tube('GuardStay', FA + Vector((s * 0.058, 0, 0)), FA + Vector((s * 0.034, -0.30, 0.205)), STEEL, 0.0035, 6)
    tube('GuardStay', RA + Vector((s * 0.058, 0, 0)), RA + Vector((s * 0.034, 0.33, 0.175)), STEEL, 0.0035, 6)

# ------------------------------------------------------------------ rear rack
RZ = 0.790
for x in (-0.065, 0.0, 0.065):
    tube('RackRail', V(0.330, RZ, x), V(0.800, RZ, x), FRAME, 0.0075, 8)
for y in (0.330, 0.48, 0.64, 0.800):
    tube('RackCross', V(y, RZ, -0.072), V(y, RZ, 0.072), FRAME, 0.0075, 8)
for s in (-1, 1):
    tube('RackStrut', V(0.800, RZ, s * 0.068), RA + Vector((s * 0.066, 0.01, 0.0)), FRAME, 0.0075, 8)
    tube('RackStrut', V(0.640, RZ, s * 0.068), RA + Vector((s * 0.066, -0.01, 0.0)), FRAME, 0.0075, 8)
    tube('RackStay', V(0.330, RZ, s * 0.068), SC + Vector((s * 0.022, 0.03, -0.05)), FRAME, 0.006, 8)

# ------------------------------------------------------------------ drivetrain (right side, -X) and pedals
CR = 0.100                                    # chainring radius
lathe('Chainring', [(0.0, 0.000), (CR, 0.000), (CR, 0.004), (0.0, 0.004)], BLACK, (-0.058, BB.y, BB.z), 1, 28)
# chain guard: one flat plate around the ring and along the top run, with a rolled rim
cg = []
for k in range(24):
    a = 2 * math.pi * k / 24
    cg.append((BB.y + 0.125 * math.cos(a), BB.z + 0.125 * math.sin(a)))
for k in range(16):
    a = 2 * math.pi * k / 16
    cg.append((RA.y - 0.02 + 0.060 * math.cos(a), RA.z + 0.060 * math.sin(a)))
hull('ChainGuard', [(x, y, z) for y, z in cg for x in (-0.080, -0.072)], FRAME); bevel(parts[-1], 0.004, 2, 30)
hull('ChainGuardInner', [(x, y, z) for y, z in cg for x in (-0.070, -0.066)], BLACK)
for s, ang in ((1, math.radians(-35)), (-1, math.radians(145))):
    end = BB + Vector((s * 0.098, 0.165 * math.cos(ang), 0.165 * math.sin(ang)))
    tube('Crank', BB + Vector((s * 0.098, 0, 0)), end, STEEL, 0.014, 10)
    lathe('CrankBolt', [(0.0, 0.0), (0.020, 0.0), (0.020, 0.012), (0.0, 0.012)], STEEL, (s * 0.090, BB.y, BB.z), s, 12)
    box('PedalAxle', (s * 0.120, end.y, end.z), (0.040, 0.012, 0.012), STEEL)
    box('Pedal', (s * 0.170, end.y, end.z), (0.085, 0.100, 0.022), BLACK, 0.006)
    for dy in (-0.040, 0.040):
        box('PedalReflector', (s * 0.170, end.y + dy, end.z), (0.060, 0.012, 0.024), LAMP, 0.003)

# kickstand on the left, folded back
tube('Kickstand', V(0.17, 0.30, 0.05), V(0.40, 0.08, 0.10), BLACK, 0.010, 8)
# front lamp on the fork crown, rear reflector on the guard
lathe('HeadLamp', [(0.0, 0.0), (0.030, 0.0), (0.036, 0.030), (0.036, 0.040), (0.0, 0.040)], BLACK, (0.0, 0.0, 0.0), 1, 16)
hl = parts[-1]
for v in hl.data.vertices:          # turn the lathe axis (X) to face forward (-Y) and place it on the crown
    x, y, z = v.co
    v.co = Vector((y, -x, z)) + crown + Vector((0, -0.055, 0.0))
lathe('HeadLens', [(0.0, 0.0), (0.030, 0.0), (0.030, 0.006), (0.0, 0.006)], LAMP, (0.0, 0.0, 0.0), 1, 16)
hl = parts[-1]
for v in hl.data.vertices:
    x, y, z = v.co
    v.co = Vector((y, -x - 0.040, z)) + crown + Vector((0, -0.055, 0.0))
box('Reflector', (0, RA.y + 0.355, RA.z + 0.16), (0.040, 0.012, 0.050), BLACK, 0.004)

# ------------------------------------------------------------------ bake, join, export
for o in parts:
    bpy.context.view_layer.objects.active = o
    for m in list(o.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)
for o in parts:
    me = o.data
    attr = me.attributes.new('mid', 'INT', 'FACE')
    ids = [ORDER.index(o.material_slots[p.material_index].material) if o.material_slots else 0 for p in me.polygons]
    attr.data.foreach_set('value', ids)
for o in scene.objects: o.select_set(False)
for o in parts: o.select_set(True)
bike = parts[0]
bpy.context.view_layer.objects.active = bike
bpy.ops.object.join()
bike.name = 'Bicycle_Mesh'; me = bike.data
me.materials.clear()
for m in ORDER: me.materials.append(m)
ids = [0] * len(me.polygons); me.attributes['mid'].data.foreach_get('value', ids)
for p, i in zip(me.polygons, ids): p.material_index = i
me.attributes.remove(me.attributes['mid'])
for p in me.polygons: p.use_smooth = True
try:
    me.set_sharp_from_angle(angle=math.radians(40))
except Exception:
    with bpy.context.temp_override(active_object=bike, object=bike, selected_objects=[bike], selected_editable_objects=[bike]):
        bpy.ops.object.shade_auto_smooth(angle=math.radians(40))
used = sorted(set(p.material_index for p in me.polygons))
tris = sum(len(p.vertices) - 2 for p in me.polygons)
bb = [bike.matrix_world @ Vector(v) for v in bike.bound_box]
size = [max(v[i] for v in bb) - min(v[i] for v in bb) for i in range(3)]
print(f'[Bicycle] triangles {tris}, materials {len(used)} {[ORDER[i].name for i in used]}, size {size[0]:.3f} x {size[1]:.3f} x {size[2]:.3f}, '
      f'y {min(v[1] for v in bb):.3f}..{max(v[1] for v in bb):.3f}, zmin {min(v[2] for v in bb):.3f}')

root = bpy.data.objects.new('Bicycle', None); scene.collection.objects.link(root); bike.parent = root
seat = bpy.data.objects.new('Seat', None); seat.location = (0.0, SEAT_TOP.y + 0.03, SEAT_TOP.z + 0.005)
scene.collection.objects.link(seat); seat.parent = root
for o in scene.objects: o.select_set(False)
root.select_set(True); bike.select_set(True); seat.select_set(True)
bpy.ops.export_scene.fbx(filepath=f'{OUT}/Bicycle.fbx', use_selection=True, apply_unit_scale=True,
                         apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)

# ------------------------------------------------------------------ previews (match the reference framing)
BG = 0.693   # linear value of the references' sRGB 217 grey
world = bpy.data.worlds.new('W'); scene.world = world; world.use_nodes = True
nt = world.node_tree; nodes = nt.nodes
bg_light = nodes['Background']; bg_light.inputs['Color'].default_value = (0.75, 0.77, 0.80, 1); bg_light.inputs['Strength'].default_value = 0.9
bg_cam = nodes.new('ShaderNodeBackground'); bg_cam.inputs['Color'].default_value = (BG, BG, BG, 1); bg_cam.inputs['Strength'].default_value = 1.0
lp = nodes.new('ShaderNodeLightPath'); mix = nodes.new('ShaderNodeMixShader')
nt.links.new(lp.outputs['Is Camera Ray'], mix.inputs[0])
nt.links.new(bg_light.outputs[0], mix.inputs[1]); nt.links.new(bg_cam.outputs[0], mix.inputs[2])
nt.links.new(mix.outputs[0], nodes['World Output'].inputs['Surface'])

# ground: shows only the shadow on the reference grey
gm = bpy.data.materials.new('Ground'); gm.use_nodes = True; gn = gm.node_tree.nodes; gl = gm.node_tree.links
for n in list(gn):
    if n.type != 'OUTPUT_MATERIAL': gn.remove(n)
dif = gn.new('ShaderNodeBsdfDiffuse'); dif.inputs['Color'].default_value = (1, 1, 1, 1)
s2r = gn.new('ShaderNodeShaderToRGB'); gl.new(dif.outputs[0], s2r.inputs[0])
mul = gn.new('ShaderNodeMath'); mul.operation = 'MULTIPLY'; mul.use_clamp = True; mul.inputs[1].default_value = 0.55
gl.new(s2r.outputs['Color'], mul.inputs[0])
lift = gn.new('ShaderNodeMapRange'); lift.inputs['To Min'].default_value = 0.55; lift.inputs['To Max'].default_value = 1.0
gl.new(mul.outputs[0], lift.inputs['Value'])
tint = gn.new('ShaderNodeMath'); tint.operation = 'MULTIPLY'; tint.inputs[1].default_value = BG
gl.new(lift.outputs['Result'], tint.inputs[0])
em = gn.new('ShaderNodeEmission'); gl.new(tint.outputs[0], em.inputs['Color'])
gl.new(em.outputs[0], gn['Material Output'].inputs['Surface'])
bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0)); ground = bpy.context.active_object; ground.data.materials.append(gm)

bpy.ops.object.light_add(type='SUN', location=(0, 0, 10)); sun = bpy.context.active_object
sun.data.energy = 3.2; sun.rotation_euler = (math.radians(35), 0, math.radians(-25)); sun.data.angle = math.radians(25)
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x, scene.render.resolution_y = 1672, 941
scene.view_settings.view_transform = 'Standard'
cam_data = bpy.data.cameras.new('Cam'); cam = bpy.data.objects.new('Cam', cam_data); scene.collection.objects.link(cam); scene.camera = cam

def shoot(name, loc, target, lens=50, ortho=None, ground_on=True):
    ground.hide_render = not ground_on
    cam.location = loc
    d = Vector(target) - Vector(loc); cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    if ortho: cam_data.type = 'ORTHO'; cam_data.ortho_scale = ortho
    else: cam_data.type = 'PERSP'; cam_data.lens = lens
    scene.render.filepath = f'{OUT}/{name}.png'; bpy.ops.render.render(write_still=True)

# camera on the bike's right (-X), front to the left of frame like the reference
shoot('render-34', (-1.72, -2.22, 1.02), (0.0, 0.02, 0.50), 42)
if DIAG:
    shoot('diag-side', (-6, 0, 0.55), (0, 0, 0.55), ortho=2.1)
    shoot('diag-left', (1.72, -2.22, 1.02), (0.0, 0.02, 0.50), 42)
    shoot('diag-top', (0, 0.01, 5), (0, 0, 0), ortho=2.1)

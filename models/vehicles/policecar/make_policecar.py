# Builds a generic four-door family sedan at previs-library detail (own design, no brands) and renders two previews.
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_sedan.py -- <out dir>
# Convention: 1 unit = 1 m, front toward -Y, up +Z, origin on the ground at the centre.
# Measured from ../../sedan/ref-side.png: lengths at 2.963 mm/px (1620 px = 4.8 m), heights squashed to
# 2.557 mm/px so the roof lands on 1.45 m. u below = metres back from the front bumper.
#
# Build: lower body is a loft of cross-sections along the length (plan-view rounding, crowned hood and deck,
# side bulge), wheel wells are boolean-cut with black liners. The greenhouse is a second loft with tumblehome,
# turned into a hollow shell; window openings are boolean-cut (cut walls become the black frames) and glass is
# a conforming copy of the shell surface sitting 12 mm inside the frame. Seats, dash and wheel sit inside.
import bpy, sys, math, bmesh
from mathutils import Vector

ARGS = sys.argv[sys.argv.index('--') + 1:]
OUT = ARGS[0]
DIAG = len(ARGS) > 1          # extra close-up shots for checking, written next to the render
VARIANT = 'police'              # 'taxi' or 'police': the only line that differs between the two scripts
NAME = {'taxi': 'Taxi', 'police': 'PoliceCar'}[VARIANT]
L = 4.80
def Y(u): return u - L / 2

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ------------------------------------------------------------------ materials (<= 10)
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

# 8 materials at most: trim, seams, interior and tyres share Black.
if VARIANT == 'taxi':
    PAINT = mat('Paint', (0.70, 0.46, 0.035), 0.5)               # muted cab yellow
else:
    PAINT = mat('Paint', (0.018, 0.019, 0.021), 0.35)            # gloss-ish black
BLACK = mat('Black', (0.014, 0.014, 0.015), 0.8)
SEAM = TRIM = INTER = BLACK
GLASS = mat('Glass', (0.020, 0.026, 0.034), 0.08, alpha=0.82)
HUB = mat('Steel', (0.42, 0.43, 0.45), 0.45, 0.2)
LAMP = mat('LampClear', (0.62, 0.64, 0.64), 0.2)
RED = mat('Red', (0.50, 0.025, 0.02), 0.3)
WHITE = mat('White', (0.78, 0.78, 0.76), 0.55)
if VARIANT == 'taxi':
    AMBER = mat('Amber', (0.85, 0.36, 0.03), 0.3)
    ORDER = [PAINT, BLACK, GLASS, HUB, LAMP, AMBER, RED, WHITE]
else:
    BLUE = mat('Blue', (0.02, 0.07, 0.55), 0.3)
    AMBER = LAMP                                                 # clear indicators keep the count at 8
    ORDER = [PAINT, BLACK, GLASS, HUB, LAMP, RED, BLUE, WHITE]

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

def ribbon(name, pts, normal_fn, width, depth, m):
    """Thin raised strip along a 3D polyline; normal_fn(p) gives the outward surface normal there."""
    bm = bmesh.new(); top, bot = [], []
    for i, p in enumerate(pts):
        p = Vector(p)
        d = (Vector(pts[min(i + 1, len(pts) - 1)]) - Vector(pts[max(i - 1, 0)])).normalized()
        n = Vector(normal_fn(p)).normalized()
        side = d.cross(n).normalized() * width / 2
        for lst, off in ((top, n * depth), (bot, -n * 0.004)):
            lst.append((bm.verts.new(p + off + side), bm.verts.new(p + off - side)))
    for i in range(len(pts) - 1):
        a, b = top[i], top[i + 1]; c, d = bot[i], bot[i + 1]
        bm.faces.new((a[0], b[0], b[1], a[1])); bm.faces.new((c[1], d[1], d[0], c[0]))
        bm.faces.new((a[1], b[1], d[1], c[1])); bm.faces.new((c[0], d[0], b[0], a[0]))
    bm.faces.new((top[0][0], top[0][1], bot[0][1], bot[0][0]))
    bm.faces.new((bot[-1][0], bot[-1][1], top[-1][1], top[-1][0]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return link(name, bm, m)

def lerp_table(table, u):
    if u <= table[0][0]: return table[0][1:]
    for a, b in zip(table, table[1:]):
        if a[0] <= u <= b[0]:
            t = (u - a[0]) / (b[0] - a[0])
            return tuple(x + (y - x) * t for x, y in zip(a[1:], b[1:]))
    return table[-1][1:]

# ------------------------------------------------------------------ lower body
# (u, z bottom, z top at centreline, half width, crown)
BODY = [
    (0.000, 0.300, 0.585, 0.800, 0.020),
    (0.030, 0.245, 0.620, 0.860, 0.022),
    (0.065, 0.215, 0.640, 0.882, 0.025),
    (0.120, 0.200, 0.770, 0.895, 0.030),
    (0.250, 0.200, 0.845, 0.910, 0.035),
    (0.520, 0.200, 0.905, 0.922, 0.035),
    (0.810, 0.200, 0.945, 0.925, 0.032),
    (1.100, 0.200, 0.970, 0.925, 0.028),
    (1.320, 0.200, 0.985, 0.925, 0.025),
    (1.500, 0.200, 0.975, 0.925, 0.018),
    (2.400, 0.200, 0.975, 0.925, 0.015),
    (3.400, 0.200, 0.985, 0.925, 0.015),
    (3.900, 0.205, 1.010, 0.925, 0.020),
    (4.150, 0.210, 1.035, 0.924, 0.028),
    (4.450, 0.215, 1.055, 0.922, 0.030),
    (4.610, 0.220, 1.055, 0.915, 0.030),
    (4.690, 0.225, 1.000, 0.902, 0.028),
    (4.740, 0.250, 0.955, 0.888, 0.024),
    (4.775, 0.285, 0.890, 0.868, 0.020),
    (4.800, 0.330, 0.640, 0.840, 0.018),
]
def body_half(u):
    """Right-half section from the bottom centre round to the top centre: [(x, z)]."""
    zb, zt, w, c = lerp_table(BODY, u)
    h = zt - c - zb
    hood = 1.0 if u < 1.3 else 0.0      # hood: flat centre bulge with two creases
    return [(0.0, zb), (0.93 * w, zb), (0.985 * w, zb + 0.10 * h), (w, zb + 0.42 * h), (0.997 * w, zb + 0.78 * h),
            (0.978 * w, zb + 0.94 * h), (0.935 * w, zt - c), (0.75 * w, zt - (0.55 - 0.15 * hood) * c),
            ((0.40 + 0.08 * hood) * w, zt - (0.12 - 0.10 * hood) * c), (0.0, zt)]

def body_ring(u):
    half = body_half(u)
    right = [(x, Y(u), z) for x, z in half]
    left = [(-x, Y(u), z) for x, z in reversed(half[1:-1])]
    return right + left

STATIONS = sorted(set([round(r[0], 3) for r in BODY] + [round(i * 0.1, 3) for i in range(2, 47)] + [1.45, 1.49, 3.41]))
STATIONS = [u for k, u in enumerate(STATIONS) if k == 0 or u - STATIONS[k - 1] > 0.015]
body = loft('Body', [body_ring(u) for u in STATIONS], PAINT)
bevel(body, 0.025, 2, 50)

def side_x(u, z):
    half = body_half(u)
    for (x0, z0), (x1, z1) in zip(half[1:7], half[2:7]):
        if z0 <= z <= z1:
            t = (z - z0) / (z1 - z0) if z1 > z0 else 0
            return x0 + (x1 - x0) * t
    return half[3][0]

def top_z(u, x):
    half = body_half(u)
    top = half[6:]
    for (x0, z0), (x1, z1) in zip(top, top[1:]):
        if x1 <= abs(x) <= x0:
            t = (x0 - abs(x)) / (x0 - x1)
            return z0 + (z1 - z0) * t
    return half[-1][1]

def side_n(p):  # outward normal of the body side near p
    s = 1 if p.x >= 0 else -1
    return (s, 0, 0)

WR, WZ = 0.340, 0.340        # wheel radius and centre height
WHEEL_U = [0.963, 3.830]
ARCH_R = 0.415
for i, u in enumerate(WHEEL_U):
    for s in (-1, 1):
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=40, radius1=ARCH_R, radius2=ARCH_R, depth=0.7)
        for v in bm.verts:
            v.co = Vector((v.co.z + s * 0.95, v.co.y + Y(u), v.co.x + WZ))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        cut = link(f'ArchCut{i}{s}', bm, TRIM, store=False); cutters.append(cut)
        mod = body.modifiers.new(f'arch{i}{s}', 'BOOLEAN'); mod.operation = 'DIFFERENCE'; mod.object = cut
        mod.material_mode = 'TRANSFER'

# Arch lips: a rounded flare swept round each opening.
for u in WHEEL_U:
    for s in (-1, 1):
        bm = bmesh.new(); rings = []
        a0, a1, n = math.radians(-14), math.radians(194), 30
        w = 0.925
        sec = [(ARCH_R - 0.005, w - 0.03), (ARCH_R + 0.030, w - 0.03), (ARCH_R + 0.045, w + 0.006),
               (ARCH_R + 0.022, w + 0.022), (ARCH_R - 0.005, w + 0.016)]
        for k in range(n + 1):
            a = a0 + (a1 - a0) * k / n
            rings.append([bm.verts.new((s * x, Y(u) - r * math.cos(a), WZ + r * math.sin(a))) for r, x in sec])
        for ra, rb in zip(rings, rings[1:]):
            for j in range(len(sec)):
                j2 = (j + 1) % len(sec)
                bm.faces.new((ra[j], ra[j2], rb[j2], rb[j]))
        bm.faces.new(rings[0]); bm.faces.new(rings[-1][::-1])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        link('ArchLip', bm, PAINT)

# ------------------------------------------------------------------ greenhouse (hollow shell)
# (u, roof height at centre); half widths come from height: tumblehome from 0.84 at the belt to 0.64 at the roof.
GH = [(1.290, 0.985), (1.420, 1.065), (1.560, 1.150), (1.700, 1.235), (1.840, 1.315), (1.960, 1.380),
      (2.060, 1.420), (2.180, 1.443), (2.400, 1.452), (2.900, 1.455), (3.300, 1.450), (3.420, 1.437),
      (3.520, 1.405), (3.640, 1.335), (3.780, 1.250), (3.920, 1.165), (4.050, 1.095), (4.190, 1.040)]
GH_BASE = 0.93
def gh_half(u, zt):
    f = max(0.0, min(1.0, (zt - 0.985) / (1.455 - 0.985)))
    wb = 0.845 - 0.03 * (1 - f) * (1 if u < 2 else 0.5)
    wt = wb + (0.645 - wb) * f
    belt = min(0.975, GH_BASE + 0.5 * (zt - GH_BASE))
    return [(wb, GH_BASE), (wb - 0.004, belt), (wt + 0.012, zt - 0.040), (wt - 0.02, zt - 0.014),
            (0.55 * wt, zt - 0.003), (0.0, zt)]

def gh_ring(u, zt):
    half = gh_half(u, zt)
    return [(x, Y(u), z) for x, z in half] + [(-x, Y(u), z) for x, z in reversed(half[:-1])]

gh_sections = [gh_ring(u, z) for u, z in GH]
def gh_surface(name, m):
    bm = bmesh.new()
    rings = [[bm.verts.new(p) for p in s] for s in gh_sections]
    n = len(gh_sections[0])
    for a, b in zip(rings, rings[1:]):
        for i in range(n - 1):
            bm.faces.new((a[i], a[i + 1], b[i + 1], b[i]))
    # end walls (windshield base and rear-glass base) as fans so the shell is closed except the floor
    for ring, rev in ((rings[0], False), (rings[-1], True)):
        c = bm.verts.new(sum((v.co for v in ring), Vector()) / len(ring))
        for i in range(n - 1):
            f = (ring[i], ring[i + 1], c)
            bm.faces.new(f[::-1] if rev else f)
    bm.normal_update()
    roof = max(bm.faces, key=lambda f: f.calc_center_median().z)
    if roof.normal.z < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    return link(name, bm, m)

shell = gh_surface('Greenhouse', PAINT)
shell.data.materials.append(INTER)
sol = shell.modifiers.new('shell', 'SOLIDIFY'); sol.thickness = 0.035; sol.offset = -1
sol.material_offset = 1; sol.material_offset_rim = 1; sol.use_rim = True

# Window cutters (black: their cut walls become the window frames)
win_coll = bpy.data.collections.new('WinCutters'); scene.collection.children.link(win_coll)
def win_cutter(name, pts):
    o = hull(name, pts, TRIM, store=False)
    for c in o.users_collection: c.objects.unlink(o)
    win_coll.objects.link(o); cutters.append(o)
    return o

def slope_cutter(name, a, b, s0, s1, half_w0, half_w1, thick=0.16):
    a, b = Vector(a), Vector(b)          # (u, z) ends of the glass line
    d = (b - a); n = Vector((-d.y, d.x)).normalized()
    pts = []
    for s, hw in ((s0, half_w0), (s1, half_w1)):
        p = a + d * s
        for k in (-1, 1):
            q = p + n * thick * k
            for sx in (-1, 1): pts.append((sx * hw, Y(q.x), q.y))
    return win_cutter(name, pts)

slope_cutter('CutWindshield', (1.30, 0.99), (2.07, 1.425), 0.08, 0.93, 0.70, 0.575)
slope_cutter('CutRearGlass', (4.18, 1.045), (3.48, 1.425), 0.10, 0.90, 0.68, 0.575)
SIDE_WINDOWS = [
    [(1.640, 0.990), (2.600, 0.990), (2.600, 1.375), (2.040, 1.375)],
    [(2.700, 0.990), (3.360, 0.990), (3.360, 1.375), (2.700, 1.375)],
    [(3.420, 0.995), (3.700, 0.995), (3.440, 1.360), (3.420, 1.360)],
]
for k, poly in enumerate(SIDE_WINDOWS):
    for s in (-1, 1):
        win_cutter(f'CutSide{k}{s}', [(s * x, Y(u), z) for u, z in poly for x in (0.50, 1.10)])

bo = shell.modifiers.new('windows', 'BOOLEAN'); bo.operation = 'DIFFERENCE'
bo.operand_type = 'COLLECTION'; bo.collection = win_coll; bo.material_mode = 'TRANSFER'

# Glass: the same surface pushed 12 mm inside, thickened, kept only inside the openings.
for cut in list(win_coll.objects):        # one glass pane per opening (a collection INTERSECT would be empty)
    glass = gh_surface('Glass', GLASS)
    bm = bmesh.new(); bm.from_mesh(glass.data); bm.normal_update()
    for v in bm.verts: v.co -= v.normal * 0.012
    bm.to_mesh(glass.data); bm.free()
    gs = glass.modifiers.new('thick', 'SOLIDIFY'); gs.thickness = 0.006; gs.offset = -1
    gb = glass.modifiers.new('keep', 'BOOLEAN'); gb.operation = 'INTERSECT'; gb.object = cut

# ------------------------------------------------------------------ interior (visible through the glass)
DRV_X = 0.37
for sx in (-1, 1):
    box('SeatBack', (sx * DRV_X, Y(2.62), 1.06), (0.48, 0.13, 0.36), INTER, 0.03)
    box('Headrest', (sx * DRV_X, Y(2.66), 1.31), (0.26, 0.10, 0.15), INTER, 0.03)
box('RearBench', (0, Y(3.55), 1.03), (1.36, 0.14, 0.30), INTER, 0.03)
for sx in (-1, 1):
    box('RearHeadrest', (sx * 0.40, Y(3.58), 1.24), (0.24, 0.09, 0.13), INTER, 0.03)
box('Dash', (0, Y(1.66), 1.00), (1.56, 0.36, 0.10), INTER, 0.03)
box('ParcelShelf', (0, Y(3.85), 1.05), (1.40, 0.40, 0.03), INTER)
# steering wheel: a ring tilted toward the driver, plus the column
bm = bmesh.new()
bmesh.ops.create_circle(bm, cap_ends=False, segments=24, radius=0.185)
ring_verts = list(bm.verts)
geom = bmesh.ops.extrude_edge_only(bm, edges=list(bm.edges))['geom']
for v in [g for g in geom if isinstance(g, bmesh.types.BMVert)]: v.co *= 0.84
rot = Vector((0, 0, 1)).rotation_difference(Vector((0, -0.55, 0.835)).normalized())
for v in bm.verts:
    v.co.rotate(rot); v.co += Vector((DRV_X, Y(2.12), 1.07))
link('SteeringWheel', bm, INTER)
sw = parts[-1]; sws = sw.modifiers.new('t', 'SOLIDIFY'); sws.thickness = 0.03; sws.offset = 0
box('Column', (DRV_X, Y(1.95), 1.00), (0.06, 0.30, 0.06), INTER, rot=Vector((0, 1, 0)).rotation_difference(Vector((0, 0.84, -0.55))))

# ------------------------------------------------------------------ front
# The lamp band is the steep face between stations u=0.065 (z 0.64) and u=0.12 (z 0.77).
def nose_u(z): return 0.065 + max(0.0, min(1.0, (z - 0.637) / 0.128)) * 0.055
def nose_slab(name, x0, x1, z0, z1, m, proud=0.004, depth=0.10, x_back=None):
    pts = []
    for z in (z0, z1):
        for x in (x0, x1):
            u = nose_u(z) - proud
            if x_back is not None and abs(x) == max(abs(x0), abs(x1)): u += x_back
            pts += [(x, Y(u), z), (x, Y(u + depth), z)]
    o = hull(name, pts, m); bevel(o, 0.006, 2, 30); return o
def nose_poly(name, outline, m, proud=0.004, depth=0.08, bev=0.006):
    """Slab whose front face follows the lamp band; outline [(x, z)] drawn on the nose."""
    pts = []
    for x, z in outline:
        u = nose_u(z) - proud
        pts += [(x, Y(u), z), (x, Y(u + depth), z)]
    o = hull(name, pts, m); bevel(o, bev, 2, 30); return o
# grille: a trapezoid frame, black back, four slats (wider at the top, as in the reference)
nose_poly('GrilleSurround', [(-0.47, 0.772), (0.47, 0.772), (0.43, 0.612), (-0.43, 0.612)], TRIM, 0.012, 0.10)
nose_poly('GrilleBack', [(-0.435, 0.752), (0.435, 0.752), (0.405, 0.628), (-0.405, 0.628)], BLACK, 0.016, 0.03)
for k in range(4):
    z = 0.648 + k * 0.032
    hw = 0.405 + (z - 0.628) / 0.124 * 0.03 - 0.008
    nose_poly(f'GrilleBar{k}', [(-hw, z + 0.008), (hw, z + 0.008), (hw, z - 0.008), (-hw, z - 0.008)], TRIM, 0.026, 0.03, 0.004)
# headlights: big lens from the grille to the corner, its bottom edge rising outward, an amber tip wrapping
# onto the fender, all in a black housing. Front points follow the nose; side points follow the fender.
def lamp(name, s, front, side, m, proud, back=0.07):
    pts = []
    for x, z in front:
        u = nose_u(z) - proud
        pts += [(s * x, Y(u), z), (s * x, Y(u + back), z)]
    for u, z in side:
        zz = min(z, lerp_table(BODY, u)[1] - lerp_table(BODY, u)[3] - 0.004)
        x = side_x(u, zz)
        pts += [(s * (x + proud), Y(u), zz), (s * (x - back), Y(u), zz)]
    o = hull(name, pts, m); bevel(o, 0.005, 2, 30); return o
for s in (-1, 1):
    lamp('LampHousing', s, [(0.468, 0.777), (0.468, 0.608), (0.865, 0.777), (0.865, 0.668)],
         [(0.140, 0.785), (0.140, 0.680)], TRIM, 0.007)
    lamp('HeadLens', s, [(0.485, 0.765), (0.485, 0.622), (0.70, 0.765), (0.70, 0.650), (0.79, 0.765), (0.79, 0.668)],
         [], LAMP, 0.013)
    lamp('Indicator', s, [(0.805, 0.765), (0.805, 0.672), (0.852, 0.765), (0.852, 0.680)],
         [(0.128, 0.775), (0.128, 0.690)], AMBER, 0.013)
    # inner reflector bowl: a dark ring look on the lens
    nose_poly('Reflector', [(s * 0.53, 0.745), (s * 0.66, 0.745), (s * 0.66, 0.66), (s * 0.53, 0.645)], LAMP, 0.017, 0.02, 0.012)
# bumper: crease along its top, a wide lower intake, angled fog-lamp pockets at the corners, a lip
box('BumperCrease', (0, Y(0.004), 0.582), (1.50, 0.02, 0.012), SEAM, 0.004)
prism('LowerIntake', [(-0.56, Y(-0.007)), (0.56, Y(-0.007)), (0.50, Y(0.05)), (-0.50, Y(0.05))], 0.300, 0.440, BLACK, 0.012)
for k in range(2):
    box('IntakeBar', (0, Y(-0.010), 0.348 + k * 0.05), (1.04, 0.02, 0.014), TRIM, 0.004)
for s in (-1, 1):
    hull('FogPocket', [(s * x, Y(u), z) for x, z in ((0.60, 0.465), (0.77, 0.475), (0.64, 0.330), (0.78, 0.345))
                       for u in (-0.006, 0.07)], BLACK); bevel(parts[-1], 0.01, 2, 30)
    hull('FogLens', [(s * x, Y(u), z) for x, z in ((0.645, 0.430), (0.735, 0.435), (0.665, 0.375), (0.745, 0.380))
                     for u in (-0.010, 0.02)], LAMP); bevel(parts[-1], 0.006, 2, 30)
box('BumperLip', (0, Y(0.04), 0.255), (1.30, 0.10, 0.03), TRIM, 0.01)
# cowl and wipers
box('Cowl', (0, Y(1.33), 0.990), (1.50, 0.08, 0.02), TRIM, 0.005)
for k in (-1, 1):
    box('Wiper', (k * 0.30 - 0.05, Y(1.36), 1.012), (0.58, 0.02, 0.012), BLACK, rot=Vector((1, 0, 0)).rotation_difference(Vector((1, 0.18 * k, 0))))

# ------------------------------------------------------------------ rear
def tail_u(z): return 4.800 - max(0.0, min(1.0, (z - 0.640) / 0.250)) * 0.025
def tail_slab(name, x0, x1, z0, z1, m, proud=0.005):
    pts = []
    for z in (z0, z1):
        for x in (x0, x1):
            u = tail_u(z) + proud - (0.04 if abs(x) > 0.8 else 0.0)
            pts += [(x, Y(u), z), (x, Y(u - 0.10), z)]
    o = hull(name, pts, m); bevel(o, 0.006, 2, 30); return o
# tail lamps: the rear face and the wing wrap are found by ray-casting the finished body, so every lens sits
# on the real (bevelled, crowned) surface instead of on a guessed one.
from mathutils.bvhtree import BVHTree
_bvh = BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get())
def on_body(origin, direction):
    hit = _bvh.ray_cast(Vector(origin), Vector(direction))
    return hit[0]
def tail_lamp(name, s, z0, z1, m, proud, depth=0.05):
    pts = []
    for z in (z0, z1):
        for x in (0.50, 0.58, 0.66, 0.74, 0.80, 0.84, 0.865):
            h = on_body((s * x, Y(6.0), z), (0, -1, 0))
            if h: pts += [h + Vector((0, proud, 0)), h - Vector((0, depth, 0))]
        for u in (4.76, 4.72, 4.67, 4.62, 4.57):
            h = on_body((s * 2.0, Y(u), z), (-s, 0, 0))
            if h: pts += [h + Vector((s * proud, 0, 0)), h - Vector((s * depth, 0, 0))]
    o = hull(name, pts, m); bevel(o, 0.004, 2, 30); return o
for s in (-1, 1):
    tail_lamp('TailHousing', s, 0.668, 0.900, TRIM, 0.004)
    tail_lamp('TailRed', s, 0.768, 0.888, RED, 0.009)
    tail_lamp('TailWhite', s, 0.680, 0.758, LAMP, 0.009)
box('RearDiffuser', (0, Y(4.765), 0.300), (1.30, 0.07, 0.07), TRIM, 0.01)
box('TrunkLock', (0, Y(tail_u(0.82) + 0.004), 0.82), (0.12, 0.02, 0.05), TRIM, 0.006)
for r, d, mm in ((0.032, 0.18, TRIM), (0.024, 0.19, BLACK)):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=r, radius2=r, depth=d)
    for v in bm.verts: v.co = Vector((v.co.x - 0.55, v.co.z + Y(4.74), v.co.y + 0.255))
    link('Exhaust', bm, mm)

# ------------------------------------------------------------------ side details
def surface_side(points_uz, s, lift=0.0):
    return [(s * (side_x(u, z) + lift), Y(u), z) for u, z in points_uz]

def seam(name, pts_uz, s, width=0.008):
    pts = surface_side(pts_uz, s, -0.002)
    return ribbon(name, pts, lambda p: (s, 0, 0), width, 0.0035, SEAM)

def densify(pts, step=0.04):
    out = []
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(math.dist(a, b) / step))
        out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n)]
    return out + [pts[-1]]

def arc_pts(u0, r, a0, a1, n=12):
    return [(u0 - r * math.cos(math.radians(a0 + (a1 - a0) * k / n)), WZ + r * math.sin(math.radians(a0 + (a1 - a0) * k / n))) for k in range(n + 1)]

for s in (-1, 1):
    seam('SeamDoorFront', densify([(1.485, 0.955), (1.470, 0.80), (1.430, 0.62), (1.420, 0.36), (1.46, 0.315)]), s)
    seam('SeamB', densify([(2.640, 0.955), (2.640, 0.315)]), s)
    seam('SeamDoorRear', densify([(3.735, 0.955), (3.70, 0.86)] + arc_pts(3.83, 0.50, 70, 18, 8) + [(3.36, 0.315)]), s)
    seam('SeamSill', densify([(1.46, 0.315), (3.37, 0.315)]), s)
    seam('SeamFender', densify([(1.485, 0.955), (1.40, 0.958)]), s)
    # body-side moulding on both doors
    for a, b in ((1.53, 2.59), (2.69, 3.47)):
        pts = surface_side(densify([(a, 0.555), (b, 0.555)], 0.08), s, 0.0)
        o = ribbon('Moulding', pts, lambda p: (s, 0, 0), 0.035, 0.012, PAINT); bevel(o, 0.004, 2, 30)
    # handles: a dark recess and a body-colour pull
    for u in (2.38, 3.22):
        x = side_x(u, 0.80)
        box('HandleRecess', (s * (x + 0.002), Y(u), 0.800), (0.006, 0.15, 0.040), TRIM, 0.002)
        box('Handle', (s * (x + 0.012), Y(u), 0.803), (0.020, 0.15, 0.030), TRIM, 0.007)
    # mirror: black sail on the door, body-colour shell, dark glass on the back
    x = side_x(1.72, 0.99)
    box('MirrorSail', (s * (x + 0.01), Y(1.72), 1.015), (0.03, 0.14, 0.09), TRIM, 0.008)
    box('MirrorArm', (s * (x + 0.03), Y(1.73), 1.035), (0.06, 0.05, 0.04), TRIM, 0.008)
    mirror = [(0, -0.07), (0.16, -0.045), (0.17, 0.05), (0, 0.06)]
    prism('MirrorShell', [(s * (x + 0.035 + a * 0.75), Y(1.74) + b) for a, b in mirror], 0.985, 1.115, PAINT, 0.02)
    box('MirrorGlass', (s * (x + 0.095), Y(1.79), 1.05), (0.11, 0.01, 0.10), TRIM, 0.004)
    # fuel flap on the right rear wing
    if s < 0:
        box('FuelFlap', (s * (side_x(4.25, 0.85) + 0.001), Y(4.25), 0.85), (0.006, 0.17, 0.13), PAINT, 0.003)

# hood and trunk shut lines on the top surface
def top_line(name, pts_ux):
    pts = [(x, Y(u), top_z(u, x)) for u, x in pts_ux]
    return ribbon(name, pts, lambda p: (0, 0, 1), 0.008, 0.003, SEAM)
for s in (-1, 1):
    top_line('TrunkSide', [(4.20 + k * 0.08, s * 0.83) for k in range(6)])
top_line('TrunkFront', [(4.20, -0.83 + k * 0.151) for k in range(12)])

# ------------------------------------------------------------------ variant kit
ROOF = 1.455
if VARIANT == 'taxi':
    # roof sign: a tapered box on two feet, blank (no text)
    SU = 2.72
    for sx in (-1, 1):
        box('SignFoot', (sx * 0.22, Y(SU), ROOF + 0.012), (0.10, 0.20, 0.03), BLACK, 0.008)
    box('SignBase', (0, Y(SU), ROOF + 0.035), (0.68, 0.30, 0.025), BLACK, 0.008)
    hull('Sign', [(sx * hw, Y(SU + sy * d), z) for sx in (-1, 1) for sy in (-1, 1)
                  for hw, d, z in ((0.32, 0.135, ROOF + 0.045), (0.29, 0.075, ROOF + 0.215))], WHITE)
    bevel(parts[-1], 0.018, 3, 30)
    hull('SignCap', [(sx * 0.27, Y(SU + sy * 0.06), z) for sx in (-1, 1) for sy in (-1, 1) for z in (ROOF + 0.205, ROOF + 0.228)], AMBER)
    bevel(parts[-1], 0.008, 2, 30)
    # checker band: two rows of flat black squares on the doors and wings
    SQ = 0.056
    for s in (-1, 1):
        n = int((3.38 - 1.56) / SQ)
        for row in range(2):
            z = 0.640 + row * SQ
            for k in range(n):
                if (k + row) % 2: continue
                u = 1.56 + (k + 0.5) * SQ
                box('Check', (s * (side_x(u, z) + 0.0015), Y(u), z), (0.004, SQ, SQ), BLACK)
        for z in (0.640 - SQ / 2 - 0.006, 0.640 + 1.5 * SQ + 0.006):     # thin black rules above and below
            pts = surface_side(densify([(1.56, z), (1.56 + n * SQ, z)], 0.1), s, 0.0)
            ribbon('CheckRule', pts, lambda p: (s, 0, 0), 0.008, 0.002, BLACK)
else:
    # roof light bar: black base on feet, red lens on the left, blue on the right, a clear centre module
    LU = 2.42
    for sx in (-1, 1):
        box('BarFoot', (sx * 0.50, Y(LU), ROOF + 0.015), (0.08, 0.22, 0.03), BLACK, 0.008)
    box('BarBase', (0, Y(LU), ROOF + 0.045), (1.26, 0.30, 0.04), BLACK, 0.012)
    for sx, m in ((1, RED), (-1, BLUE)):
        box('BarLens', (sx * 0.345, Y(LU), ROOF + 0.105), (0.53, 0.26, 0.085), m, 0.03)
    box('BarCentre', (0, Y(LU), ROOF + 0.100), (0.14, 0.24, 0.07), LAMP, 0.02)
    for sx in (-1, 1):
        box('BarEnd', (sx * 0.62, Y(LU), ROOF + 0.100), (0.03, 0.27, 0.09), BLACK, 0.01)
    # push bar in front of the bumper
    for sx in (-1, 1):
        box('PushPost', (sx * 0.30, Y(-0.13), 0.50), (0.06, 0.06, 0.56), BLACK, 0.012)
        for z in (0.33, 0.62):
            box('PushBracket', (sx * 0.30, Y(-0.06), z), (0.05, 0.14, 0.04), BLACK, 0.008)
        box('PushPad', (sx * 0.30, Y(-0.165), 0.50), (0.07, 0.02, 0.44), BLACK, 0.008)
    for z in (0.40, 0.66):
        box('PushRail', (0, Y(-0.13), z), (0.72, 0.05, 0.05), BLACK, 0.012)
    # A-pillar spotlight on the driver side
    x = side_x(1.60, 0.95)
    box('SpotPost', (x + 0.03, Y(1.60), 1.00), (0.03, 0.03, 0.12), BLACK, 0.006)
    box('SpotHousing', (x + 0.05, Y(1.58), 1.08), (0.10, 0.16, 0.10), HUB, 0.03)
    box('SpotLens', (x + 0.05, Y(1.495), 1.08), (0.08, 0.012, 0.08), LAMP, 0.004)

# ------------------------------------------------------------------ wheels
TYRE = [(0.215, -0.100), (0.290, -0.106), (0.322, -0.100), (0.337, -0.075), (0.340, 0.0), (0.337, 0.075),
        (0.322, 0.100), (0.290, 0.106), (0.215, 0.100)]
HUBCAP = [(0.0, 0.112), (0.05, 0.111), (0.15, 0.104), (0.205, 0.094), (0.216, 0.080), (0.216, 0.05), (0.0, 0.05)]
for u in WHEEL_U:
    for s in (-1, 1):
        cx = s * 0.795
        lathe('Tyre', TYRE, BLACK, (cx, Y(u), WZ), s, 32, closed=True)
        lathe('Hubcap', HUBCAP, HUB, (cx, Y(u), WZ), s, 32, closed=True)
        lathe('CentreCap', [(0.0, 0.118), (0.040, 0.116), (0.048, 0.110), (0.048, 0.10), (0.0, 0.10)], HUB, (cx, Y(u), WZ), s, 20, closed=True)
        bevel(parts[-1], 0.004, 2, 30)
        # seven trapezoid vents in the cap
        for k in range(7):
            a = 2 * math.pi * k / 7 + 0.3
            pts = []
            for r, half in ((0.095, 0.022), (0.180, 0.040)):
                for t in (-1, 1):
                    aa = a + t * half / r
                    ax = 0.111 - (r - 0.05) / 0.10 * 0.007
                    pts.append(Vector((cx + s * (ax + 0.001), Y(u) + r * math.cos(aa), WZ + r * math.sin(aa))))
            quad = [pts[0], pts[1], pts[3], pts[2]]
            bm = bmesh.new()
            top = [bm.verts.new(p) for p in quad]
            bot = [bm.verts.new(p - Vector((s * 0.006, 0, 0))) for p in quad]
            bm.faces.new(top); bm.faces.new(bot[::-1])
            for i in range(4):
                j = (i + 1) % 4
                bm.faces.new((top[i], bot[i], bot[j], top[j]))
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            link('Vent', bm, TRIM)

# ------------------------------------------------------------------ bake: apply modifiers, tag faces, join
for o in cutters:
    o.hide_render = True; o.hide_viewport = False
for o in parts:
    bpy.context.view_layer.objects.active = o
    for m in list(o.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)
for c in cutters: bpy.data.objects.remove(c)

for o in parts:
    me = o.data
    attr = me.attributes.new('mid', 'INT', 'FACE')
    ids = [ORDER.index(o.material_slots[p.material_index].material) if o.material_slots else 0 for p in me.polygons]
    attr.data.foreach_set('value', ids)

for o in scene.objects: o.select_set(False)
for o in parts: o.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.object.join()
car = body; car.name = NAME + '_Mesh'; me = car.data
me.materials.clear()
for m in ORDER: me.materials.append(m)
ids = [0] * len(me.polygons); me.attributes['mid'].data.foreach_get('value', ids)
for p, i in zip(me.polygons, ids): p.material_index = i

# interior floor (and the police two-tone) as face colour; no geometry, no textures
for p in me.polygons:
    c = p.center
    u = c.y + L / 2
    if p.material_index == 0:
        if p.normal.z > 0.6 and 1.40 < u < 4.10 and abs(c.x) < 0.80 and c.z < 1.0:
            p.material_index = ORDER.index(INTER)          # cabin floor seen through the glass
        elif VARIANT == 'police' and 1.45 < u < 3.41 and c.z < 0.965 and abs(p.normal.x) > 0.3:
            p.material_index = ORDER.index(WHITE)          # white doors
        elif VARIANT == 'police' and c.z > 1.40 and p.normal.z > 0.5:
            p.material_index = ORDER.index(WHITE)          # white roof
me.attributes.remove(me.attributes['mid'])

for p in me.polygons: p.use_smooth = True
try:
    me.set_sharp_from_angle(angle=math.radians(35))
except Exception:
    with bpy.context.temp_override(active_object=car, object=car, selected_objects=[car], selected_editable_objects=[car]):
        bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
used = sorted(set(p.material_index for p in me.polygons))
tris = sum(len(p.vertices) - 2 for p in me.polygons)
bb = [car.matrix_world @ Vector(v) for v in car.bound_box]
size = [max(v[i] for v in bb) - min(v[i] for v in bb) for i in range(3)]
print(f'[{NAME}] triangles {tris}, materials {len(used)} {[ORDER[i].name for i in used]}, size {size[0]:.3f} x {size[1]:.3f} x {size[2]:.3f}')

root = bpy.data.objects.new(NAME, None); scene.collection.objects.link(root); car.parent = root
seat = bpy.data.objects.new('Seat', None); seat.location = (DRV_X, Y(2.45), 0.50); scene.collection.objects.link(seat); seat.parent = root
for o in scene.objects: o.select_set(False)
root.select_set(True); car.select_set(True); seat.select_set(True)
bpy.ops.export_scene.fbx(filepath=f'{OUT}/{NAME}.fbx', use_selection=True, apply_unit_scale=True,
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

shoot('render-34', (2.95, -4.45, 1.50), (0.20, 0.05, 0.60), 30)
if DIAG:
    shoot('diag-front', (1.6, -5.2, 0.95), (0.0, -2.3, 0.62), 50)
    shoot('diag-side', (12, 0, 0.893), (0, 0, 0.893), ortho=4.954)
    shoot('diag-rear', (-2.95, 4.45, 1.70), (0.0, 0.0, 0.70), 30)

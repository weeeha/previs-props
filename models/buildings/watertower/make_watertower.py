# Steel water tower (own design, CC0), previs base library (Opus).
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_watertower.py -- <out dir>
# 1 unit = 1 m, front toward -Y, up +Z, origin on the ground at the centre of the footprint.
# Follows ref-34.png / ref-side.png: four splayed box-section legs on concrete footings, two braced panels per face
# (flat-bar X braces with octagonal gusset plates, horizontal struts), a balcony deck with a two-rail railing on
# knee brackets, a 4.0 m tank with hoop bands and a cone bottom, a cone roof with ribs and a finial. One ladder runs
# up the +X face through a hatch in the deck, the second climbs the tank and hooks over the eave with goosenecks.
# Weathered pale-green paint: tank and roof are cut into small cells; each picks paint / worn / rust from noise.
import bpy, bmesh, sys, math, os
from mathutils import Vector, Matrix, noise

OUT = os.path.abspath(sys.argv[sys.argv.index('--') + 1])
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ---------------------------------------------------------------- materials (fixed order = fixed slots)
ORDER = []
def mat(name, rgb, rough=0.85, metal=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*rgb, 1); b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal; m.diffuse_color = (*rgb, 1)
    ORDER.append(m); return len(ORDER) - 1

PAINT = mat('Paint', (0.200, 0.255, 0.165), 0.8)        # weathered pale green
PAINT_D = mat('PaintWorn', (0.160, 0.200, 0.130), 0.85)
RUST = mat('Rust', (0.200, 0.095, 0.050), 0.9)
CONC = mat('Concrete', (0.215, 0.188, 0.162))
STEEL = mat('Steel', (0.085, 0.090, 0.100), 0.6, 0.3)
BLACK = mat('Black', (0.012, 0.012, 0.012), 1.0)

parts = []
def new_obj(name, me):
    o = bpy.data.objects.new(name, me); scene.collection.objects.link(o)
    for m in ORDER: o.data.materials.append(m)
    parts.append(o); return o

def set_all(o, idx):
    for p in o.data.polygons: p.material_index = idx

def box(name, lo, hi, idx, bevel=0.0, segs=2):
    lo, hi = [min(a, b) for a, b in zip(lo, hi)], [max(a, b) for a, b in zip(lo, hi)]
    c = [(lo[i] + hi[i]) / 2 for i in range(3)]; s = [hi[i] - lo[i] for i in range(3)]
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((*s, 1)))
    if bevel:
        bmesh.ops.bevel(bm, geom=bm.edges[:] + bm.verts[:], offset=bevel, segments=segs, affect='EDGES', profile=0.5)
    bm.to_mesh(me); bm.free()
    o = new_obj(name, me); set_all(o, idx); return o

def frame_from(d, n):
    """Rotation matrix whose X is d, Y is n made orthogonal to d, Z = X x Y."""
    x = Vector(d).normalized(); y = (Vector(n) - x * x.dot(Vector(n))).normalized(); z = x.cross(y)
    m = Matrix((x, y, z)).transposed(); return m.to_4x4()

def beam(name, a, b, w, t, n, idx, bevel=0.0, ext=0.0):
    """Box from a to b, width w (in-plane), thickness t along n."""
    a, b = Vector(a), Vector(b); d = (b - a); L = d.length + 2 * ext
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Diagonal((L, t, w, 1)))
    if bevel: bmesh.ops.bevel(bm, geom=bm.edges[:] + bm.verts[:], offset=bevel, segments=1, affect='EDGES', profile=0.5)
    bm.transform(Matrix.Translation((a + b) / 2) @ frame_from(d, n))
    bm.to_mesh(me); bm.free()
    o = new_obj(name, me); set_all(o, idx); return o

def lathe(name, prof, n, loc=(0, 0, 0), cap_top=True, cap_bot=True, mat_fn=None, rot=0.0):
    """prof: list of (r, z, mat_idx); mat_fn(center, normal) may override per face."""
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    rings = [[bm.verts.new((loc[0] + r * math.cos(2 * math.pi * k / n + rot), loc[1] + r * math.sin(2 * math.pi * k / n + rot), loc[2] + z))
              for k in range(n)] for r, z, _ in prof]
    for i in range(len(prof) - 1):
        for k in range(n):
            f = bm.faces.new([rings[i][k], rings[i][(k + 1) % n], rings[i + 1][(k + 1) % n], rings[i + 1][k]])
            f.material_index = prof[i][2]
    if cap_bot: f = bm.faces.new(rings[0][::-1]); f.material_index = prof[0][2]
    if cap_top: f = bm.faces.new(rings[-1]); f.material_index = prof[-2][2]
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if mat_fn:
        for f in bm.faces:
            m = mat_fn(f.calc_center_median(), f.normal)
            if m is not None: f.material_index = m
    bm.to_mesh(me); bm.free()
    return new_obj(name, me)

def tube(name, pts, r, idx, n=8, fillet=0.0):
    P = [Vector(p) for p in pts]; path = [P[0]]
    for i in range(1, len(P) - 1):
        a, b, c = P[i - 1], P[i], P[i + 1]
        f = min(fillet, (a - b).length / 2, (c - b).length / 2)
        if f <= 0: path.append(b); continue
        s, e = b + (a - b).normalized() * f, b + (c - b).normalized() * f
        for k in range(6):
            t = k / 5; path.append((1 - t) ** 2 * s + 2 * (1 - t) * t * b + t ** 2 * e)
    path.append(P[-1])
    me = bpy.data.meshes.new(name); bm = bmesh.new(); rings = []
    for i, p in enumerate(path):
        t = (path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]).normalized()
        u = t.cross(Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))).normalized(); v = t.cross(u)
        rings.append([bm.verts.new(p + r * (math.cos(2 * math.pi * k / n) * u + math.sin(2 * math.pi * k / n) * v)) for k in range(n)])
    for i in range(len(rings) - 1):
        for k in range(n):
            bm.faces.new([rings[i][k], rings[i][(k + 1) % n], rings[i + 1][(k + 1) % n], rings[i + 1][k]])
    bm.faces.new(rings[0][::-1]); bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    o = new_obj(name, me); set_all(o, idx); return o

def ring(name, r, z, rr, idx, n=48, m=6, gap=None):
    """Torus-ish rail ring; gap=(angle, half_width) leaves an opening."""
    me = bpy.data.meshes.new(name); bm = bmesh.new(); rings = []
    angs = [2 * math.pi * k / n for k in range(n)]
    for a in angs:
        c = Vector((r * math.cos(a), r * math.sin(a), z)); out = Vector((math.cos(a), math.sin(a), 0))
        rings.append([bm.verts.new(c + rr * (math.cos(2 * math.pi * j / m) * out + math.sin(2 * math.pi * j / m) * Vector((0, 0, 1)))) for j in range(m)])
    for k in range(n):
        if gap and abs(math.remainder((angs[k] + angs[(k + 1) % n]) / 2 + (math.pi if k == n - 1 else 0) - gap[0], 2 * math.pi)) < gap[1]: continue
        for j in range(m):
            bm.faces.new([rings[k][j], rings[(k + 1) % n][j], rings[(k + 1) % n][(j + 1) % m], rings[k][(j + 1) % m]])
    bm.to_mesh(me); bm.free()
    o = new_obj(name, me); set_all(o, idx); return o

def disc(name, center, normal, r, t, n, idx, rot=0.0):
    o = lathe(name, [(0.0, 0, idx), (r, 0, idx), (r, t, idx), (0.0, t, idx)], n, rot=rot)
    z = Vector(normal).normalized(); x = z.cross(Vector((0, 0, 1)) if abs(z.z) < 0.9 else Vector((1, 0, 0))).normalized()
    y = z.cross(x)
    o.data.transform(Matrix.Translation(center) @ Matrix((x, y, z)).transposed().to_4x4())
    return o

def fbm(x, y, z, oct=3):
    v, a, f = 0.0, 1.0, 1.0
    for _ in range(oct):
        v += a * noise.noise(Vector((x * f, y * f, z * f))); a *= 0.5; f *= 2.1
    return v

# ---------------------------------------------------------------- dimensions
FOOT = 0.40                     # top of the concrete footings
DECK = 9.00                     # top of the balcony deck (legs end just under it)
B, T = 2.45, 1.70               # leg centreline half-spread at the ground and at the deck
def lr(z): return B - (B - T) * z / DECK
def leg_pt(sx, sy, z): return Vector((sx * lr(z), sy * lr(z), z))
TR = 2.00                       # tank radius
TZ0, TZ1 = DECK + 0.12, 13.60   # tank shell bottom and top
RR, RAPEX = 2.22, 15.50         # roof eave radius and apex height
DR = 2.65                       # deck outer radius
PANELS = [FOOT, 4.55, DECK - 0.35]

# ---------------------------------------------------------------- footings, base plates, legs
for sx in (-1, 1):
    for sy in (-1, 1):
        p = leg_pt(sx, sy, 0)
        f = lathe('Footing', [(0.62, 0.0, CONC), (0.62, 0.12, CONC), (0.44, FOOT, CONC), (0.0, FOOT, CONC)], 4, (p.x, p.y, 0), rot=math.pi / 4)
        bpy.context.view_layer.update()
        box('BasePlate', (p.x - 0.30, p.y - 0.30, FOOT), (p.x + 0.30, p.y + 0.30, FOOT + 0.04), STEEL, 0.008, 1)
        for bx in (-1, 1):
            for by in (-1, 1):
                lathe('Bolt', [(0.0, 0, STEEL), (0.035, 0, STEEL), (0.035, 0.07, STEEL), (0.0, 0.08, STEEL)], 6, (p.x + bx * 0.22, p.y + by * 0.22, FOOT + 0.04))
        a, b = leg_pt(sx, sy, FOOT + 0.04), leg_pt(sx, sy, DECK - 0.12)
        beam('Leg', a, b, 0.38, 0.38, (sx, -sy, 0), PAINT, 0.02)
        # leg shoe gussets
        for d in ((sx, 0, 0), (0, sy, 0)):
            beam('Shoe', a + Vector(d) * 0.21 + Vector((0, 0, 0.0)), a + Vector(d) * 0.21 + Vector((0, 0, 0.45)), 0.10, 0.03,
                 Vector((d[1], d[0], 0)) if True else d, PAINT_D, 0.0)

# ---------------------------------------------------------------- bracing on the four faces
def face_normal(axis, s):
    n = Vector((0, 0, (B - T) / DECK)); n[axis] = s; return n.normalized()
faces = [(0, 1), (0, -1), (1, 1), (1, -1)]       # (axis, sign): axis 0 -> faces at x = +-, axis 1 -> y = +-
for axis, s in faces:
    n = face_normal(axis, s)
    def corner(k, z):   # k = -1 / +1 along the face
        return leg_pt(s, k, z) if axis == 0 else leg_pt(k, s, z)
    for z in PANELS[1:]:
        beam('Strut', corner(-1, z), corner(1, z), 0.24, 0.12, n, PAINT, 0.012)
        for k in (-1, 1):   # joint plates where strut meets leg
            disc('JointPlate', corner(k, z) + n * 0.16, n, 0.24, 0.02, 4, PAINT_D, rot=math.pi / 4)
    for z0, z1 in zip(PANELS, PANELS[1:]):
        za, zb = z0 + 0.15, z1 - 0.12
        for k in (-1, 1):
            beam('Brace', corner(k, za) + n * 0.10, corner(-k, zb) + n * (0.10 + 0.03 * k), 0.20, 0.04, n, PAINT, 0.008)
        # octagonal gusset at the crossing (the two diagonals cross at the panel mid-line)
        cA0, cA1, cB0, cB1 = corner(-1, za), corner(1, zb), corner(1, za), corner(-1, zb)
        mid = (cA0 + cA1 + cB0 + cB1) / 4
        disc('Gusset', mid + n * 0.135, n, 0.26, 0.02, 8, PAINT_D, rot=math.pi / 8)
        for bxy in ((-0.11, 0), (0.11, 0), (0, -0.11), (0, 0.11)):
            t1 = (corner(1, 0) - corner(-1, 0)).normalized(); t2 = n.cross(t1)
            disc('Rivet', mid + n * 0.155 + t1 * bxy[0] + t2 * bxy[1], n, 0.03, 0.02, 6, PAINT_D)

# ---------------------------------------------------------------- deck: ring joists, knee brackets, deck plate with a hatch
HATCH_A = math.atan2(-0.95, T + 0.36)            # the lower ladder lands here
HATCH_W = math.radians(9.5)
for sx in (-1, 1):
    for sy in (-1, 1):
        top = leg_pt(sx, sy, DECK - 0.12)
        box('LegCap', (top.x - 0.22, top.y - 0.22, DECK - 0.20), (top.x + 0.22, top.y + 0.22, DECK - 0.12), PAINT, 0.01, 1)
for axis, s in faces:
    a = leg_pt(s, -1, DECK - 0.2) if axis == 0 else leg_pt(-1, s, DECK - 0.2)
    b = leg_pt(s, 1, DECK - 0.2) if axis == 0 else leg_pt(1, s, DECK - 0.2)
    beam('RingBeam', a, b, 0.18, 0.18, face_normal(axis, s), PAINT, 0.01)
for k in range(8):                                # radial joists + knee brackets down to the legs/ring
    ang = math.pi / 8 + k * math.pi / 4 if k % 2 else k * math.pi / 4
    ang = k * math.pi / 4 + math.pi / 8
    u = Vector((math.cos(ang), math.sin(ang), 0))
    beam('Joist', u * 1.55 + Vector((0, 0, DECK - 0.20)), u * (DR - 0.05) + Vector((0, 0, DECK - 0.20)), 0.14, 0.10, Vector((-u.y, u.x, 0)), PAINT, 0.01)
    beam('Knee', u * 1.80 + Vector((0, 0, DECK - 1.05)), u * (DR - 0.25) + Vector((0, 0, DECK - 0.24)), 0.10, 0.06, Vector((-u.y, u.x, 0)), PAINT, 0.008)
N_D = 48
me = bpy.data.meshes.new('Deck'); bm = bmesh.new()
for k in range(N_D):
    a0, a1 = 2 * math.pi * k / N_D, 2 * math.pi * (k + 1) / N_D
    if abs(math.remainder((a0 + a1) / 2 - HATCH_A, 2 * math.pi)) < HATCH_W: continue
    vs = []
    for z in (DECK - 0.10, DECK):
        for r in (1.92, DR):
            for a in (a0, a1): vs.append(bm.verts.new((r * math.cos(a), r * math.sin(a), z)))
    # index: z(0/1)*4 + r(0/1)*2 + a(0/1)
    q = lambda zi, ri, ai: vs[zi * 4 + ri * 2 + ai]
    for f in ((q(1, 0, 0), q(1, 1, 0), q(1, 1, 1), q(1, 0, 1)), (q(0, 0, 0), q(0, 0, 1), q(0, 1, 1), q(0, 1, 0)),
              (q(0, 1, 0), q(0, 1, 1), q(1, 1, 1), q(1, 1, 0)), (q(0, 0, 0), q(1, 0, 0), q(1, 0, 1), q(0, 0, 1)),
              (q(0, 0, 0), q(0, 1, 0), q(1, 1, 0), q(1, 0, 0)), (q(0, 0, 1), q(1, 0, 1), q(1, 1, 1), q(0, 1, 1))):
        bm.faces.new(f)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
for f in bm.faces:
    c = f.calc_center_median()
    f.material_index = PAINT_D if (f.normal.z > 0.7 and fbm(c.x * 1.3, c.y * 1.3, 4.0) > 0.25) else PAINT
bm.to_mesh(me); bm.free(); new_obj('Deck', me)
# deck edge band, railing (posts + two rails)
lathe('DeckEdge', [(DR, DECK - 0.16, PAINT), (DR + 0.03, DECK - 0.16, PAINT), (DR + 0.03, DECK + 0.05, PAINT), (DR, DECK + 0.05, PAINT)], 48, cap_top=False, cap_bot=False)
RAIL_R = DR - 0.06
for k in range(16):
    a = 2 * math.pi * k / 16 + math.pi / 16
    tube('Post', [(RAIL_R * math.cos(a), RAIL_R * math.sin(a), DECK), (RAIL_R * math.cos(a), RAIL_R * math.sin(a), DECK + 1.06)], 0.03, PAINT, 6)
ring('RailTop', RAIL_R, DECK + 1.06, 0.035, PAINT, 48, 6)
ring('RailMid', RAIL_R, DECK + 0.55, 0.028, PAINT, 48, 6)
ring('Toe', RAIL_R, DECK + 0.06, 0.03, PAINT_D, 48, 4)

# ---------------------------------------------------------------- tank (cells for weathering), hoops, seams, bottom cone, outlet
HOOPS = [10.60, 12.10]
def tank_mat(c, n):
    a = math.atan2(c.y, c.x); u = a * TR; z = c.z
    if n.z < -0.5: return None
    under = min([h - z for h in HOOPS + [TZ1] if h - z > 0] + [9.0])       # distance below a hoop / the eave
    streak = fbm(u * 2.2, z * 0.35, 1.3, 3)
    if under < 0.16 and streak > 0.0: return RUST
    if under < 0.75 and streak + (0.75 - under) * 0.45 > 0.74: return RUST
    if fbm(u * 0.9 + 9, z * 0.9, 2.2, 2) > 0.40: return PAINT_D
    return None
def ring_prof(r, z0, z1, step, idx):
    k = max(1, round((z1 - z0) / step)); return [(r, z0 + (z1 - z0) * i / k, idx) for i in range(k + 1)]
lathe('Tank', ring_prof(TR, TZ0, TZ1, 0.15, PAINT), 32, cap_top=False, cap_bot=False, mat_fn=tank_mat)
for z in HOOPS + [TZ0 + 0.10, TZ1 - 0.06]:
    lathe('Hoop', [(TR - 0.01, z - 0.05, PAINT), (TR + 0.035, z - 0.045, PAINT), (TR + 0.035, z + 0.045, PAINT), (TR - 0.01, z + 0.05, PAINT)],
          32, cap_top=False, cap_bot=False, mat_fn=lambda c, n: RUST if (n.z < -0.3 and fbm(c.x * 3, c.y * 3, c.z) > 0.3) else None)
for k in range(8):                                # vertical plate seams
    a = 2 * math.pi * k / 8 + 0.2
    u = Vector((math.cos(a), math.sin(a), 0))
    beam('Seam', u * (TR + 0.006) + Vector((0, 0, TZ0 + 0.15)), u * (TR + 0.006) + Vector((0, 0, TZ1 - 0.1)), 0.06, 0.02, u, PAINT, 0.0)
lathe('Bottom', [(0.30, 7.65, PAINT), (0.30, 7.95, PAINT), (0.55, 8.00, PAINT), (1.20, 8.50, PAINT), (1.70, 8.90, PAINT), (TR, TZ0, PAINT)],
      32, cap_top=False, cap_bot=False, mat_fn=lambda c, n: PAINT_D if fbm(c.x * 1.5, c.y * 1.5, c.z * 1.5) > 0.25 else None)
lathe('Outlet', [(0.0, 7.62, BLACK), (0.22, 7.62, PAINT), (0.33, 7.62, PAINT), (0.33, 7.70, PAINT)], 24, cap_top=False, cap_bot=False)
lathe('OutletIn', [(0.22, 7.62, BLACK), (0.22, 7.95, BLACK)], 24, cap_top=False, cap_bot=False)

# ---------------------------------------------------------------- roof: cone with eave lip, ribs, finial vent, hatch
def roof_z(r): return TZ1 + 0.02 + (RR - r) / RR * (RAPEX - TZ1 - 0.02)
def roof_mat(c, n):
    r = math.hypot(c.x, c.y); a = math.atan2(c.y, c.x)
    if n.z < -0.2: return PAINT_D
    e = fbm(a * 4.0, r * 1.6, 7.0, 3)
    if r > RR - 0.30 and e > 0.20: return RUST
    if e > 0.62: return RUST
    if fbm(a * 2.0 + 3, r * 1.0, 1.0) > 0.40: return PAINT_D
    return None
rp = [(RR - 0.03, TZ1 - 0.12, PAINT), (RR, TZ1 - 0.08, PAINT), (RR, TZ1 + 0.02, PAINT)]
for i in range(1, 12):
    r = RR * (1 - i / 12); rp.append((max(r, 0.16), roof_z(max(r, 0.16)), PAINT))
lathe('Roof', rp, 32, cap_top=True, cap_bot=False, mat_fn=roof_mat)
lathe('RoofUnder', [(TR, TZ1 - 0.02, PAINT_D), (RR - 0.03, TZ1 - 0.12, PAINT_D)], 32, cap_top=False, cap_bot=False)
for k in range(16):                               # standing-seam ribs
    a = 2 * math.pi * k / 16
    u = Vector((math.cos(a), math.sin(a), 0)); t = Vector((-u.y, u.x, 0))
    p0 = u * (RR - 0.02) + Vector((0, 0, roof_z(RR - 0.02) + 0.03)); p1 = u * 0.22 + Vector((0, 0, roof_z(0.22) + 0.03))
    beam('Rib', p0, p1, 0.05, 0.05, t, PAINT, 0.0)
lathe('Finial', [(0.0, RAPEX - 0.12, PAINT), (0.20, RAPEX - 0.12, PAINT), (0.20, RAPEX + 0.10, PAINT), (0.12, RAPEX + 0.12, BLACK),
                 (0.12, RAPEX + 0.20, BLACK), (0.30, RAPEX + 0.22, PAINT), (0.30, RAPEX + 0.27, PAINT), (0.14, RAPEX + 0.40, PAINT),
                 (0.0, RAPEX + 0.43, PAINT)], 16, cap_bot=False)

# ---------------------------------------------------------------- ladders
LW = 0.46                                         # rail spacing
def ladder(name, p0, p1, side, n_out, top_ext=None, rung_step=0.30):
    """Rails from p0 to p1 (centreline), side = unit vector across the ladder; optional top_ext(rail_offset) -> extra points."""
    p0, p1 = Vector(p0), Vector(p1)
    for s in (-1, 1):
        off = side * (s * LW / 2)
        pts = [p0 + off, p1 + off] + ([q + off for q in top_ext] if top_ext else [])
        tube(name + 'Rail', pts, 0.028, PAINT, 6, fillet=0.18)
    L = (p1 - p0).length; n = int(L / rung_step)
    for i in range(1, n + 1):
        c = p0 + (p1 - p0) * (i * rung_step / L)
        if c.z > p1.z - 0.05: break
        tube(name + 'Rung', [c - side * (LW / 2), c + side * (LW / 2)], 0.018, PAINT, 6)

# lower ladder: outside the +X face, following its slope, up through the deck hatch, rails continue as grab handles
OUT_OFF = 0.36
ly = -0.95
def lx(z): return lr(z) + OUT_OFF
side_l = Vector((0, 1, 0))
lp0 = Vector((lx(0.0), ly, 0.0)); lp1 = Vector((lx(DECK), ly, DECK))
ladder('Lower', lp0, lp1, side_l, None, top_ext=[lp1 + Vector((-0.0, 0, 1.05)), lp1 + Vector((-0.30, 0, 1.15))])
for z in (2.6, 4.55, 6.8):                       # stand-off brackets to the face
    for s in (-1, 1):
        a = Vector((lx(z), ly + s * LW / 2, z)); b = Vector((lr(z) + 0.05, ly + s * LW / 2, z))
        beam('LadBr', a, b, 0.05, 0.03, (0, 1, 0), PAINT_D, 0.0)
# hatch frame around the opening
for s in (-1, 1):
    a = HATCH_A + s * HATCH_W
    u = Vector((math.cos(a), math.sin(a), 0))
    beam('HatchFr', u * 1.92 + Vector((0, 0, DECK + 0.02)), u * DR + Vector((0, 0, DECK + 0.02)), 0.06, 0.06, Vector((-u.y, u.x, 0)), PAINT_D)
# upper ladder on the tank wall at the same azimuth, goosenecks over the eave onto the roof
ua = HATCH_A + math.radians(4)
u = Vector((math.cos(ua), math.sin(ua), 0)); t = Vector((-u.y, u.x, 0))
R_UP = TR + 0.24
up0 = u * R_UP + Vector((0, 0, DECK)); up1 = u * R_UP + Vector((0, 0, TZ1 - 0.15))
ladder('Upper', up0, up1, t, u, top_ext=[u * R_UP + Vector((0, 0, TZ1 + 0.55)), u * (RR - 0.05) + Vector((0, 0, TZ1 + 0.72)),
                                         u * (RR - 0.55) + Vector((0, 0, roof_z(RR - 0.55) + 0.05))])
for z in (DECK + 1.6, 11.4, 13.0):
    for s in (-1, 1):
        a = u * R_UP + t * (s * LW / 2) + Vector((0, 0, z)); b = u * (TR + 0.02) + t * (s * LW / 2) + Vector((0, 0, z))
        beam('UpBr', a, b, 0.05, 0.03, t, PAINT_D, 0.0)

# ---------------------------------------------------------------- join (all parts carry the same slot list)
for o in scene.objects: o.select_set(False)
for o in parts: o.select_set(True)
base = parts[0]
bpy.context.view_layer.objects.active = base
bpy.ops.object.join()
mesh = base; mesh.name = 'WaterTower_Mesh'
assert [m.name for m in mesh.data.materials] == [m.name for m in ORDER], 'material slots shuffled'
bm = bmesh.new(); bm.from_mesh(mesh.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0003)
bm.to_mesh(mesh.data); bm.free()
with bpy.context.temp_override(active_object=mesh, object=mesh, selected_objects=[mesh], selected_editable_objects=[mesh]):
    bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
tris = sum(len(p.vertices) - 2 for p in mesh.data.polygons)
used = sorted({p.material_index for p in mesh.data.polygons})
co = [v.co for v in mesh.data.vertices]
lo = [min(c[i] for c in co) for i in range(3)]; hi = [max(c[i] for c in co) for i in range(3)]
print(f'[watertower] triangles {tris}, materials {len(used)} {[ORDER[i].name for i in used]}, '
      f'size {hi[0]-lo[0]:.2f} x {hi[1]-lo[1]:.2f} x {hi[2]-lo[2]:.2f}, bounds {[round(v, 2) for v in lo]} {[round(v, 2) for v in hi]}')

root = bpy.data.objects.new('WaterTower', None); scene.collection.objects.link(root); mesh.parent = root
for o in scene.objects: o.select_set(False)
root.select_set(True); mesh.select_set(True)
bpy.ops.export_scene.fbx(filepath=f'{OUT}/WaterTower.fbx', use_selection=True, apply_unit_scale=True,
                         apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)

# ---------------------------------------------------------------- previews
world = bpy.data.worlds.new('W'); scene.world = world; world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.66, 0.66, 0.66, 1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.0
gm = bpy.data.materials.new('Ground'); gm.use_nodes = True
gb = gm.node_tree.nodes['Principled BSDF']
gb.inputs['Base Color'].default_value = (0.08, 0.08, 0.08, 1); gb.inputs['Roughness'].default_value = 0.95
gb.inputs['Emission Color'].default_value = (0.66, 0.66, 0.66, 1); gb.inputs['Emission Strength'].default_value = 0.80
gme = bpy.data.meshes.new('Ground'); gbm = bmesh.new()
bmesh.ops.create_grid(gbm, x_segments=1, y_segments=1, size=3000); gbm.to_mesh(gme); gbm.free()
ground = bpy.data.objects.new('Ground', gme); scene.collection.objects.link(ground); gme.materials.append(gm)
sun_d = bpy.data.lights.new('Sun', 'SUN'); sun_d.energy = 3.0; sun_d.angle = math.radians(10)
sun = bpy.data.objects.new('Sun', sun_d); scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(48), 0, math.radians(38))
scene.render.engine = 'BLENDER_EEVEE'
scene.view_settings.view_transform = 'Standard'
cam_d = bpy.data.cameras.new('Cam'); cam_d.clip_end = 8000
cam = bpy.data.objects.new('Cam', cam_d); scene.collection.objects.link(cam); scene.camera = cam
def shoot(name, loc, target, lens=50, ortho=None, res=(1672, 941)):
    scene.render.resolution_x, scene.render.resolution_y = res
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    if ortho: cam_d.type = 'ORTHO'; cam_d.ortho_scale = ortho
    else: cam_d.type = 'PERSP'; cam_d.lens = lens
    scene.render.filepath = f'{OUT}/{name}.png'; bpy.ops.render.render(write_still=True)

shoot('render-34', (22.0, -28.5, 10.0), (0.2, 0.0, 7.6), 38)
shoot('render-side', (0, -60, 8.1), (0, 0, 8.1), ortho=17.6, res=(941, 1672))

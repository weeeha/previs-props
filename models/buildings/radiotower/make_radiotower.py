# Original three-legged lattice radio tower (intact + broken) for the VR Director previs library. Round 2, Fable.
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_radiotower.py -- <out dir>
# 1 unit = 1 m, front toward -Y (the face between the two front legs), up +Z, origin on the ground at the centre.
# Measured from ref-side.png (90 px per metre): 18 m tall, front legs 5.6 m apart at the footings, flared
# (Eiffel-like) profile down to 0.52 m at the lattice top (16.2 m), bands red/white/red/white/red.
import bpy, sys, math, bmesh
from mathutils import Vector, Matrix

OUT = sys.argv[sys.argv.index('--') + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

MATS = []
def mat(name, rgb, rough=0.7, metal=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*rgb, 1); b.inputs['Roughness'].default_value = rough; b.inputs['Metallic'].default_value = metal
    m.diffuse_color = (*rgb, 1); MATS.append(m); return len(MATS) - 1
RED = mat('Tower_Red', (0.47, 0.075, 0.032))
WHITE = mat('Tower_White', (0.66, 0.62, 0.54))
STEEL = mat('Tower_Steel', (0.27, 0.28, 0.29), 0.55, 0.2)
CONC = mat('Tower_Concrete', (0.40, 0.39, 0.37), 0.95)
ANT = mat('Tower_Antenna', (0.70, 0.68, 0.63), 0.5)
DARK = mat('Tower_Dark', (0.035, 0.035, 0.04), 0.6)
RUST = mat('Tower_Rust', (0.16, 0.06, 0.025), 0.9)

# ------------------------------------------------------------------ geometry helpers
def frame(p, n):
    return Matrix.Translation(p) @ Vector(n).normalized().to_track_quat('Z', 'Y').to_matrix().to_4x4()

def merge(bm, t, mi, M=None):
    vm = {v: bm.verts.new(M @ v.co if M else v.co) for v in t.verts}
    for f in t.faces:
        bm.faces.new([vm[v] for v in f.verts]).material_index = f.material_index if mi is None else mi
    t.free()

def cbox(bm, size, M, mi, bevel=0.0, segs=1, taper=1.0):
    t = bmesh.new(); bmesh.ops.create_cube(t, size=1.0)
    for v in t.verts:
        k = taper if v.co.z > 0 else 1.0
        v.co = Vector((v.co.x * size[0] * k, v.co.y * size[1] * k, v.co.z * size[2]))
    if bevel: bmesh.ops.bevel(t, geom=t.edges[:], offset=bevel, segments=segs, profile=0.5, affect='EDGES')
    merge(bm, t, mi, M)

def beam(bm, p1, p2, w, mi, ref=None, h=None, cham=0.22):
    """Box beam from p1 to p2, w wide across `ref`, h deep along `ref`, with chamfered long edges."""
    p1, p2 = Vector(p1), Vector(p2); d = (p2 - p1).normalized()
    if ref is None: ref = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
    u = d.cross(Vector(ref)).normalized(); v = u.cross(d).normalized()
    a, b = w / 2, (h or w) / 2; c = cham * min(a, b)
    if c > 0: sec = [(a - c, b), (-a + c, b), (-a, b - c), (-a, -b + c), (-a + c, -b), (a - c, -b), (a, -b + c), (a, b - c)]
    else: sec = [(a, b), (-a, b), (-a, -b), (a, -b)]
    A = [bm.verts.new(p1 + u * x + v * y) for x, y in sec]; B = [bm.verts.new(p2 + u * x + v * y) for x, y in sec]
    n = len(sec)
    fs = [bm.faces.new(A[::-1]), bm.faces.new(B)] + [bm.faces.new((A[i], A[(i + 1) % n], B[(i + 1) % n], B[i])) for i in range(n)]
    for f in fs: f.material_index = mi

def lathe(bm, prof, segs, mi, M=Matrix.Identity(4)):
    """Revolve (radius, height) points around local Z. A radius of 0 closes the end with a fan."""
    rings = []
    for r, hgt in prof:
        if r < 1e-6: rings.append([bm.verts.new(M @ Vector((0, 0, hgt)))])
        else: rings.append([bm.verts.new(M @ Vector((r * math.cos(2 * math.pi * k / segs), r * math.sin(2 * math.pi * k / segs), hgt))) for k in range(segs)])
    for A, B in zip(rings, rings[1:]):
        if len(A) == 1 and len(B) == 1: continue
        for k in range(segs):
            k2 = (k + 1) % segs
            if len(A) == 1: f = bm.faces.new((A[0], B[k], B[k2]))
            elif len(B) == 1: f = bm.faces.new((A[k], A[k2], B[0]))
            else: f = bm.faces.new((A[k], A[k2], B[k2], B[k]))
            f.material_index = mi

def tube(bm, pts, r, segs, mi, closed=False):
    pts = [Vector(p) for p in pts]; n = len(pts); rings = []; nrm = None
    for i in range(n):
        if closed: t = (pts[(i + 1) % n] - pts[i - 1]).normalized()
        else: t = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized()
        if nrm is None:
            nrm = t.cross(Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))).normalized()
        nrm = (nrm - t * nrm.dot(t)).normalized(); b = t.cross(nrm)
        rings.append([bm.verts.new(pts[i] + (nrm * math.cos(2 * math.pi * k / segs) + b * math.sin(2 * math.pi * k / segs)) * r) for k in range(segs)])
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if closed else [])
    for A, B in pairs:
        for k in range(segs):
            bm.faces.new((A[k], A[(k + 1) % segs], B[(k + 1) % segs], B[k])).material_index = mi
    if not closed:
        bm.faces.new(rings[0][::-1]).material_index = mi; bm.faces.new(rings[-1]).material_index = mi

def bolt(bm, p, n, r, h, mi=STEEL):
    lathe(bm, [(r, 0), (r, h), (0, h)], 6, mi, frame(p, n))

# ------------------------------------------------------------------ tower dimensions
Z0, ZT, ZTOP = 0.45, 16.2, 18.0
HW = [(0.45, 2.80), (5.0, 1.60), (9.9, 0.82), (12.4, 0.50), (16.2, 0.26)]      # half width of a face, from the side view
RINGS = [0.45, 3.3, 5.0, 6.9, 8.4, 9.9, 11.2, 12.4, 13.3, 14.1, 14.9, 15.6, 16.2]
LEG_ANG = [math.radians(a) for a in (210, 330, 90)]                             # front-left, front-right, back
RAD = [Vector((math.cos(a), math.sin(a), 0)) for a in LEG_ANG]
def hw(z):
    z = max(HW[0][0], min(HW[-1][0], z))
    for (za, a), (zb, b) in zip(HW, HW[1:]):
        if z <= zb: return a + (b - a) * (z - za) / (zb - za)
def leg(i, z): return RAD[i] * (hw(z) / math.cos(math.radians(30))) + Vector((0, 0, z))
def face_n(i): return (RAD[i] + RAD[(i + 1) % 3]).normalized()
def band(z): return WHITE if (5.0 <= z < 6.9 or 9.9 <= z < 12.4) else RED
def s(z): return 1.0 - 0.5 * (z - Z0) / (ZT - Z0)                               # member size falls off with height
def legdir(i, z): return (leg(i, min(z + 0.3, ZT)) - leg(i, max(z - 0.3, Z0))).normalized()

def collar(bm, i, z, mi):
    p = leg(i, z); d = legdir(i, z); cw = 0.36 * s(z) * 1.32; hl = 0.24 * s(z) + 0.06
    beam(bm, p - d * hl, p + d * hl, cw, mi, RAD[i])
    u = d.cross(RAD[i]).normalized(); br = 0.026 * s(z) + 0.012
    for sg in (-1, 1):
        for off in ((-0.55, 0.55) if z < 13 else (0.0,)):
            bolt(bm, p + u * sg * cw / 2 + d * off * hl, u * sg, br, 0.03)

def lattice(bm, k0, k1, low_ring=True):
    for k in range(max(k0, 1), k1 + 1):
        if k == k0 and not low_ring: continue
        z = RINGS[k]; mi = band(z + 0.01)
        for i in range(3):
            beam(bm, leg(i, z), leg((i + 1) % 3, z), 0.18 * s(z), mi, h=0.13 * s(z))
            collar(bm, i, z, mi)
    for k in range(k0, k1):
        z0, z1 = RINGS[k], RINGS[k + 1]; zm = (z0 + z1) / 2; mi = band(zm)
        for i in range(3):
            j = (i + 1) % 3; n = face_n(i); dw = max(0.085, 0.16 * s(zm))
            beam(bm, leg(i, z0), leg(i, z1), 0.36 * s(zm), mi, RAD[i])
            if k == 0:                                           # bottom bay: inverted V up to the middle of the first ring
                mid = (leg(i, z1) + leg(j, z1)) / 2
                beam(bm, leg(i, 1.25), mid, dw, mi, n, dw * 0.6); beam(bm, leg(j, 1.25), mid, dw, mi, n, dw * 0.6)
                cbox(bm, (0.42, 0.34, dw * 0.6 + 0.05), frame(mid - Vector((0, 0, 0.06)), n), mi, 0.02)
                bolt(bm, mid + n * (dw * 0.3 + 0.025), n, 0.035, 0.03)
            else:                                                # X bracing with a bolted plate at the crossing
                beam(bm, leg(i, z0), leg(j, z1), dw, mi, n, dw * 0.6); beam(bm, leg(j, z0), leg(i, z1), dw, mi, n, dw * 0.6)
                t = hw(z0) / (hw(z0) + hw(z1)); x = leg(i, z0).lerp(leg(j, z1), t); ps = 0.34 * s(zm) + 0.04
                cbox(bm, (ps, ps, dw * 0.6 + 0.04), frame(x, n), mi, 0.015)
                bolt(bm, x + n * (dw * 0.3 + 0.02), n, 0.022 * s(zm) + 0.012, 0.03)

def footings(bm):
    for i in range(3):
        p = leg(i, Z0)
        cbox(bm, (1.55, 1.55, 0.14), Matrix.Translation((p.x, p.y, 0.07)), CONC, 0.025)
        cbox(bm, (1.25, 1.25, 0.28), Matrix.Translation((p.x, p.y, 0.26)), CONC, 0.04, 2, taper=0.74)
        cbox(bm, (0.62, 0.62, 0.05), Matrix.Translation((p.x, p.y, 0.42)), STEEL, 0.012)
        for sx in (-1, 1):
            for sy in (-1, 1):
                bolt(bm, Vector((p.x + sx * 0.23, p.y + sy * 0.23, 0.445)), (0, 0, 1), 0.045, 0.06)
        d = legdir(i, Z0)
        beam(bm, p - d * 0.02, p + d * 0.42, 0.42, RED, RAD[i])                 # leg shoe

LAD_R = 1.30                                                                     # ladder reaches the platform rim
def lad_p(z):
    zz = min(z, 12.4); off = 0.40 + (LAD_R - leg(0, 12.4).xy.length - 0.40) * (zz - 0.7) / (12.4 - 0.7)
    q = leg(0, zz) + RAD[0] * off; q.z = z; return q
def ladder(bm, z0, z1):
    tng = Vector((-RAD[0].y, RAD[0].x, 0))
    brk = sorted({z0, z1} | {z for z in (5.0, 9.9, 12.4) if z0 < z < z1})
    for sg in (-1, 1):
        for a, b in zip(brk, brk[1:]):
            beam(bm, lad_p(a) + tng * sg * 0.23, lad_p(b) + tng * sg * 0.23, 0.055, WHITE, RAD[0])
    z = z0 + 0.25
    while z < min(z1, 12.35):
        beam(bm, lad_p(z) - tng * 0.23, lad_p(z) + tng * 0.23, 0.035, WHITE, cham=0); z += 0.30
    for z in RINGS[1:7]:
        if z0 < z < z1:
            for sg in (-1, 1): beam(bm, leg(0, z), lad_p(z) + tng * sg * 0.23, 0.04, STEEL, cham=0)

def platform(bm):
    zp = 12.4; R = 1.22
    lathe(bm, [(0, -0.05), (R - 0.02, -0.05), (R, -0.03), (R, 0.03), (R - 0.02, 0.05), (0, 0.05)], 24, RED, Matrix.Translation((0, 0, zp)))
    lathe(bm, [(R - 0.04, 0.05), (R - 0.04, 0.16), (R - 0.01, 0.16), (R - 0.01, 0.05)], 24, RED, Matrix.Translation((0, 0, zp)))   # toe board
    for zr, rr in ((zp + 0.55, 0.022), (zp + 1.0, 0.032)):
        tube(bm, [(math.cos(2 * math.pi * k / 24) * (R - 0.04), math.sin(2 * math.pi * k / 24) * (R - 0.04), zr) for k in range(24)], rr, 6, RED, closed=True)
    for k in range(12):
        a = 2 * math.pi * (k + 0.5) / 12; c = Vector((math.cos(a), math.sin(a), 0)) * (R - 0.04)
        beam(bm, c + Vector((0, 0, zp)), c + Vector((0, 0, zp + 1.0)), 0.05, RED, cham=0)
    for i in range(3):
        beam(bm, leg(i, 11.45), RAD[i] * (R - 0.12) + Vector((0, 0, zp - 0.04)), 0.09, RED, RAD[i], 0.07)

def dish(bm, c, d, R):
    M = frame(c, d)
    lathe(bm, [(0, -0.30 * R), (0.30 * R, -0.30 * R), (0.96 * R, -0.05 * R), (R, 0.0), (R, 0.10 * R), (0.96 * R, 0.13 * R),
               (0.91 * R, 0.09 * R), (0.45 * R, 0.035 * R), (0, 0.02 * R)], 24, ANT, M)
    lathe(bm, [(0, -0.52 * R), (0.15 * R, -0.52 * R), (0.15 * R, -0.29 * R), (0, -0.29 * R)], 10, STEEL, M)
    lathe(bm, [(0, 0.02 * R), (0.055 * R, 0.02 * R), (0.045 * R, 0.16 * R), (0, 0.16 * R)], 8, DARK, M)

def mounted_dish(bm, i, z, d, R, reach=0.34):
    d = Vector(d).normalized(); C = leg(i, z) + d * reach; pl = R * 0.62
    tube(bm, [C - Vector((0, 0, pl)), C + Vector((0, 0, pl))], 0.05, 8, STEEL)
    for dz in (-pl * 0.7, pl * 0.7):
        beam(bm, leg(i, z + dz), C + Vector((0, 0, dz)), 0.08, STEEL, cham=0)
        cbox(bm, (0.16, 0.16, 0.10), Matrix.Translation(C + Vector((0, 0, dz))), STEEL, 0.015)
    dish(bm, C + d * 0.52 * R, d, R)

def panel(bm, i, z, d, hgt=1.7):
    d = Vector(d).normalized(); C = leg(i, z) + d * 0.36; P = C + d * 0.17
    tube(bm, [C - Vector((0, 0, hgt / 2 + 0.1)), C + Vector((0, 0, hgt / 2 + 0.1))], 0.04, 8, STEEL)
    for dz in (-hgt * 0.32, hgt * 0.32):
        beam(bm, leg(i, z + dz), C + Vector((0, 0, dz)), 0.07, STEEL, cham=0)
        cbox(bm, (0.14, 0.14, 0.09), Matrix.Translation(C + Vector((0, 0, dz))), STEEL, 0.012)
    M = Matrix.Translation(P) @ Matrix.Rotation(math.atan2(d.y, d.x) - math.pi / 2, 4, 'Z')
    cbox(bm, (0.32, 0.17, hgt), M, ANT, 0.045, 2)
    for sx in (-0.08, 0.08):                                                    # connectors and feeder cables
        q = M @ Vector((sx, 0, -hgt / 2))
        lathe(bm, [(0, -0.07), (0.025, -0.07), (0.025, 0.0), (0, 0.0)], 6, DARK, Matrix.Translation(q))
    q = M @ Vector((0, 0, -hgt / 2 - 0.06)); l = leg(i, z - hgt / 2 - 0.75)
    tube(bm, [q, q + Vector((0, 0, -0.22)), q.lerp(l, 0.55) + Vector((0, 0, -0.30)), l], 0.022, 6, DARK)

def mast(bm):
    lathe(bm, [(0, -0.06), (0.36, -0.06), (0.36, 0.02), (0.30, 0.06), (0, 0.06)], 12, RED, Matrix.Translation((0, 0, ZT)))
    r = 0.07
    lathe(bm, [(0, ZT), (0.13, ZT), (0.13, ZT + 0.16), (r, ZT + 0.2), (r, 16.95)], 12, RED)
    lathe(bm, [(r, 16.95), (r, 17.5)], 12, WHITE)
    lathe(bm, [(r, 17.5), (r, 17.8), (0.045, 17.82), (0.045, 17.86), (0.085, 17.9), (0.085, 17.96), (0.05, 18.0), (0, 18.0)], 12, RED)

def top_gear(bm, big=True):
    platform(bm); mast(bm)
    if big: mounted_dish(bm, 0, 14.75, (-1.0, -0.42, 0), 0.92)
    panel(bm, 1, 15.05, RAD[1])
    panel(bm, 2, 14.3, RAD[2], 1.4)
def low_gear(bm):
    mounted_dish(bm, 1, 10.55, (1.0, -0.45, 0), 0.52, 0.42)

def tris(bm): return sum(len(f.verts) - 2 for f in bm.faces)

# ------------------------------------------------------------------ intact
bmI = bmesh.new()
lattice(bmI, 0, len(RINGS) - 1); footings(bmI); ladder(bmI, 0.7, 13.45); top_gear(bmI); low_gear(bmI)

# ------------------------------------------------------------------ broken: stump, sheared top lying bent beside it
KC = 6; ZC = RINGS[KC]                                                          # cut above the 11.2 m ring
bmB = bmesh.new()
lattice(bmB, 0, KC); footings(bmB); ladder(bmB, 0.7, 10.9); low_gear(bmB)
for i, (hgt, out, side) in enumerate([(0.95, 0.42, 0.10), (0.40, 0.05, -0.12), (1.25, 0.30, 0.28)]):   # torn leg stubs
    p = leg(i, ZC); tng = Vector((-RAD[i].y, RAD[i].x, 0)); m = p + legdir(i, ZC) * hgt * 0.55
    q = m + Vector((0, 0, hgt * 0.45)) + RAD[i] * out + tng * side
    beam(bmB, p, m, 0.36 * s(ZC), band(ZC + 0.1), RAD[i]); beam(bmB, m, q, 0.28 * s(ZC), band(ZC + 0.1), RAD[i])
    beam(bmB, q, q + (q - m).normalized() * 0.10, 0.25 * s(ZC), RUST, RAD[i])
n0 = face_n(0); a = leg(0, ZC)                                                  # one brace left hanging on the front face
beam(bmB, a, a + Vector((0.55, 0, -1.25)) + n0 * 0.35, 0.085, WHITE, n0, 0.05)
a = leg(2, ZC); n2 = face_n(2)
beam(bmB, a, a + Vector((-0.2, -0.5, 0.75)) + n2 * 0.25, 0.085, WHITE, n2, 0.05)

top = bmesh.new()
lattice(top, KC, len(RINGS) - 1, low_ring=False); ladder(top, 11.75, 13.45); top_gear(top, big=False)
for i, (ln, out) in enumerate([(0.55, 0.22), (0.95, -0.15), (0.30, 0.10)]):    # ragged lower ends of the fallen part
    p = leg(i, ZC); q = leg(i, ZC - ln) + RAD[i] * out
    beam(top, p, q, 0.36 * s(ZC), band(ZC - 0.1), RAD[i]); beam(top, q, q + (q - p).normalized() * 0.10, 0.25 * s(ZC), RUST, RAD[i])

# bend the fallen part (in what becomes the ground plane), tip it over its front face, settle it on the ground
T0, T1, TH = 2.8, 4.2, math.radians(-40); RHO = (T1 - T0) / TH
def bend(co):
    x, t = co.x, co.z - ZC
    if t <= T0: sx, st, a = 0.0, t, 0.0
    else:
        a = TH * min(1.0, (t - T0) / (T1 - T0)); sx = RHO * (1 - math.cos(a)); st = T0 + RHO * math.sin(a)
        if t > T1: sx += (t - T1) * math.sin(TH); st += (t - T1) * math.cos(TH)
    return Vector((sx + x * math.cos(a), co.y, st - x * math.sin(a)))
bent = [(v, bend(v.co), v.co.z - ZC) for v in top.verts]
def settle(phi):
    Rm = Matrix.Rotation(math.radians(90) + phi, 4, 'X')
    pts = [(Rm @ b, t) for _, b, t in bent]; lo = min(p.z for p, _ in pts); far = min(p.z for p, t in pts if t > 4.5)
    return Rm, lo, far
phi = 0.0
while phi < math.radians(25):
    Rm, lo, far = settle(phi)
    if far - lo < 0.01: break
    phi += math.radians(0.25)
PLACE = Matrix.Translation((5.4, -3.0, 0)) @ Matrix.Rotation(math.radians(74), 4, 'Z') @ Matrix.Translation((0, 0, -lo)) @ Rm
for v, b, _ in bent: v.co = PLACE @ b
merge(bmB, top, None)

fd = bmesh.new(); dish(fd, (0, 0, 0), (0.28, -0.20, 1.0), 0.92)                  # the big dish, torn off, lying face up
tube(fd, [(-0.15, 0.1, -0.5), (0.25, -0.1, -0.42), (1.05, -0.35, -0.50)], 0.05, 8, STEEL)
lo = min(v.co.z for v in fd.verts)
merge(bmB, fd, None, Matrix.Translation((8.2, 2.6, -lo)) @ Matrix.Rotation(math.radians(40), 4, 'Z'))

# ------------------------------------------------------------------ objects, export
def finish(bm, name, root_name, loc):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    n = tris(bm); used = sorted({f.material_index for f in bm.faces}); remap = {u: k for k, u in enumerate(used)}
    for f in bm.faces: f.material_index = remap[f.material_index]
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for u in used: me.materials.append(MATS[u])
    o = bpy.data.objects.new(name, me); scene.collection.objects.link(o)
    with bpy.context.temp_override(active_object=o, object=o, selected_objects=[o], selected_editable_objects=[o]):
        bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
    root = bpy.data.objects.new(root_name, None); scene.collection.objects.link(root); root.location = loc; o.parent = root
    lo = [min(v.co[a] for v in me.vertices) for a in range(3)]; hi = [max(v.co[a] for v in me.vertices) for a in range(3)]
    print(f'[{root_name}] triangles {n}, materials {len(used)}, bbox {hi[0]-lo[0]:.2f} x {hi[1]-lo[1]:.2f} x {hi[2]-lo[2]:.2f} m, z {lo[2]:.3f}..{hi[2]:.3f}')
    return root, o
BX = 16.0
rootI, meshI = finish(bmI, 'RadioTower_Mesh', 'RadioTower', (0, 0, 0))
rootB, meshB = finish(bmB, 'RadioTower_Broken_Mesh', 'RadioTower_Broken', (BX, 0, 0))
for o in scene.objects: o.select_set(False)
for o in (rootI, meshI, rootB, meshB): o.select_set(True)
bpy.ops.export_scene.fbx(filepath=f'{OUT}/RadioTower.fbx', use_selection=True, apply_unit_scale=True,
                         apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)

# ------------------------------------------------------------------ previews (studio grey like the references)
world = bpy.data.worlds.new('W'); scene.world = world; world.use_nodes = True
nt = world.node_tree; bg = nt.nodes['Background']; bg.inputs['Color'].default_value = (0.72, 0.72, 0.72, 1); bg.inputs['Strength'].default_value = 0.6
bg2 = nt.nodes.new('ShaderNodeBackground'); bg2.inputs['Color'].default_value = (0.72, 0.72, 0.72, 1)      # what the camera sees
lp = nt.nodes.new('ShaderNodeLightPath'); mx = nt.nodes.new('ShaderNodeMixShader')
nt.links.new(lp.outputs['Is Camera Ray'], mx.inputs[0]); nt.links.new(bg.outputs[0], mx.inputs[1]); nt.links.new(bg2.outputs[0], mx.inputs[2])
nt.links.new(mx.outputs[0], nt.nodes['World Output'].inputs['Surface'])
bpy.ops.object.light_add(type='SUN', location=(0, 0, 30)); sun = bpy.context.active_object
sun.data.energy = 2.3; sun.rotation_euler = (math.radians(52), 0, math.radians(-28)); sun.data.angle = math.radians(12)
scene.render.engine = 'BLENDER_EEVEE'; scene.view_settings.view_transform = 'Standard'
cam_data = bpy.data.cameras.new('Cam'); cam = bpy.data.objects.new('Cam', cam_data); scene.collection.objects.link(cam); scene.camera = cam
cam_data.clip_end = 500
def shoot(name, loc, target, lens=50, ortho=None, res=(1672, 941), show=()):
    scene.render.resolution_x, scene.render.resolution_y = res
    for r in (rootI, rootB):
        for o in [r] + list(r.children): o.hide_render = r not in show
    cam.location = loc; d = Vector(target) - Vector(loc); cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    if ortho: cam_data.type = 'ORTHO'; cam_data.ortho_scale = ortho
    else: cam_data.type = 'PERSP'; cam_data.lens = lens
    scene.render.filepath = f'{OUT}/{name}.png'; bpy.ops.render.render(write_still=True)
shoot('render-34', (3.6, -33.5, 16.0), (0, 0, 8.7), 35, show=(rootI,))
shoot('render-side', (0, -80, 8.94), (0, 0, 8.94), ortho=18.6, res=(941, 1672), show=(rootI,))
shoot('render-broken', (BX + 17, -34, 11), (BX + 4.4, 0, 5.2), 40, show=(rootB,))

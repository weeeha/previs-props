# SedanBuck: picture-car buck of the library sedan (own design, no brand). Same exterior as
# models/vehicles/sedan/make_sedan.py, split into hideable parts with a real interior.
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_sedanbuck.py -- <out dir>
# Convention: 1 unit = 1 m, front toward -Y, up +Z, origin on the ground at the centre.
# Car-left is +X (facing -Y), so the driver sits at +X. (The library sedan's wheel is at -X, i.e. right-hand drive.)
# Parts (children of the root empty, each with its origin at the root origin): Body, Roof, Windshield, RearWindow,
# Door_FL, Door_FR, Door_RL, Door_RR, Interior. Seat empties: Seat_Driver, Seat_Passenger, Seat_RearLeft,
# Seat_RearRight, plus Seat (= Seat_Driver, read by the app today).
# How it is split: the body is the library loft; Body = loft - cabin cavity - door prisms, Door = loft & prism.
# The greenhouse is rebuilt as thick patches over the library's own (station, ring) grid, so pillars, roof,
# door frames and glass are rectangles in that grid and can belong to different parts.
import bpy, bmesh, sys, os, math, json
import numpy as np
from mathutils import Vector, Matrix

OUT = sys.argv[sys.argv.index('--') + 1]
NAME = 'SedanBuck'
L = 4.80
pi = math.pi

def Y(x):  # distance from the front bumper -> scene Y (front is -Y)
    return x - L / 2

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ---------------------------------------------------------------- materials (library names and colours + Headliner)
MATLIST = []
def mat(name, rgb, rough=0.75, metal=0.0, emit=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*rgb, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if emit:
        b.inputs['Emission Color'].default_value = (*rgb, 1)
        b.inputs['Emission Strength'].default_value = emit
    if name == 'Glass': b.inputs['Specular IOR Level'].default_value = 0.08
    m.diffuse_color = (*rgb, 1)
    MATLIST.append(m)
    return len(MATLIST) - 1

PAINT = mat('Paint', (0.115, 0.175, 0.24), 0.6)
SEAM = mat('Seam', (0.06, 0.095, 0.13), 0.8)
TRIM = mat('Trim', (0.10, 0.105, 0.11), 0.7)
BLACK = mat('Black', (0.018, 0.018, 0.02), 0.85)
GLASS = mat('Glass', (0.016, 0.02, 0.028), 0.45)
HUB = mat('Hub', (0.42, 0.43, 0.44), 0.45, 0.2)
LAMP = mat('Lamp', (0.56, 0.56, 0.52), 0.3)
AMBER = mat('Amber', (0.85, 0.33, 0.03), 0.3)
RED = mat('Red', (0.55, 0.03, 0.025), 0.3)
HEAD = mat('Headliner', (0.30, 0.30, 0.29), 0.9)

g = MATLIST[GLASS]
g.node_tree.nodes['Principled BSDF'].inputs['Alpha'].default_value = 0.25
g.diffuse_color = (0.016, 0.02, 0.028, 0.25)
for attr, val in (('surface_render_method', 'BLENDED'), ('blend_method', 'BLEND'), ('use_transparency_overlap', True),
                  ('use_transparent_shadow', True), ('use_backface_culling', False)):
    try: setattr(g, attr, val)
    except Exception: pass

PARTS = ['Body', 'Roof', 'Windshield', 'RearWindow', 'Door_FL', 'Door_FR', 'Door_RL', 'Door_RR', 'Interior']
GROUPS = {p: [] for p in PARTS}
CUR = ['Body']
TMP = []

def finish(o, mi=None):
    for m in MATLIST: o.data.materials.append(m)
    if mi is not None:
        for p in o.data.polygons: p.material_index = mi
    GROUPS[CUR[0]].append(o)
    return o

def obj_from_bm(name, bm):
    me = bpy.data.meshes.new('tmp_' + name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new('tmp_' + name, me); scene.collection.objects.link(o)
    TMP.append(o)
    return o

def add_bevel(o, bevel, seg=2):
    if bevel:
        b = o.modifiers.new('bevel', 'BEVEL'); b.width = bevel; b.segments = seg; b.limit_method = 'ANGLE'

def box(name, c, size, mi, bevel=0.0, rot=(0, 0, 0), seg=2):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1)
    for v in bm.verts: v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    o = obj_from_bm(name, bm); o.location = c; o.rotation_euler = rot
    add_bevel(o, bevel, seg)
    return finish(o, mi)

def cyl(name, c, r, depth, axis, mi, n=32, bevel=0.0, seg=2, rot=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=n, radius1=r, radius2=r, depth=depth)
    o = obj_from_bm(name, bm); o.location = c
    o.rotation_euler = rot or {'X': (0, pi / 2, 0), 'Y': (pi / 2, 0, 0), 'Z': (0, 0, 0)}[axis]
    add_bevel(o, bevel, seg)
    return finish(o, mi)

def mbox(name, M, lc, size, mi, bevel=0.0, seg=2):
    """Box in a local frame M (4x4), centred at local point lc."""
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1)
    for v in bm.verts: v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    bmesh.ops.transform(bm, matrix=M @ Matrix.Translation(lc), verts=bm.verts)
    o = obj_from_bm(name, bm); add_bevel(o, bevel, seg)
    return finish(o, mi)

def mcyl(name, M, lc, r, depth, mi, n=24, bevel=0.0):
    """Cylinder along local Z of frame M."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=n, radius1=r, radius2=r, depth=depth)
    bmesh.ops.transform(bm, matrix=M @ Matrix.Translation(lc), verts=bm.verts)
    o = obj_from_bm(name, bm); add_bevel(o, bevel)
    return finish(o, mi)

def sph(name, c, r, mi, seg=16):
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=r)
    o = obj_from_bm(name, bm); o.location = c
    return finish(o, mi)

def prism_bm(poly, w0, w1):
    """Closed prism: polygon in (x from front bumper, z), extruded laterally from w0 to w1."""
    bm = bmesh.new()
    a = [bm.verts.new((w0, Y(x), z)) for x, z in poly]
    b = [bm.verts.new((w1, Y(x), z)) for x, z in poly]
    n = len(poly)
    bm.faces.new(a); bm.faces.new(b[::-1])
    for i in range(n):
        bm.faces.new([a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm

SOUP = []
def face(verts, mi, hint):
    SOUP.append(([Vector(v) for v in verts], mi, Vector(hint), CUR[0]))

# ---------------------------------------------------------------- body sections (library sedan, unchanged)
def tab(t, x):
    if x <= t[0][0]: return t[0][1]
    for (x0, v0), (x1, v1) in zip(t, t[1:]):
        if x <= x1: return v0 + (v1 - v0) * (x - x0) / (x1 - x0)
    return t[-1][1]

TOP = [(0, .58), (.03, .62), (.06, .645), (.11, .80), (.50, .87), (1.00, .945), (1.33, 1.00), (2.0, 1.00),
       (3.6, 1.02), (4.19, 1.07), (4.45, 1.065), (4.62, 1.05), (4.70, 1.01), (4.74, .92), (4.755, .78),
       (4.765, .66), (4.80, .62)]
BOT = [(0, .25), (.03, .22), (.10, .22), (.50, .24), (1.0, .25), (4.3, .25), (4.6, .27), (4.74, .30), (4.80, .36)]
HW = [(0, .74), (.03, .83), (.08, .865), (.11, .875), (.30, .895), (.50, .90), (4.3, .90), (4.6, .885),
      (4.72, .85), (4.765, .80), (4.80, .72)]
CROWN = [(0, 0), (.06, 0), (.11, .03), (.50, .05), (1.33, .055), (1.40, 0), (4.10, 0), (4.19, .025),
         (4.62, .025), (4.70, .01), (4.74, 0)]
F4 = [(0, .68), (2.0, .68), (4.3, .60), (4.8, .60)]
SD = [(0, .012), (.06, .012), (.11, .14), (.50, .11), (1.0, .09)]

def section(x):
    t, b, h, c = tab(TOP, x), tab(BOT, x), tab(HW, x), tab(CROWN, x)
    H = t - b
    return [(0, b), (h - .14, b), (h - .03, b + min(.07, .2 * H)), (h, b + .42 * H),
            (h - .004, b + tab(F4, x) * H), (h - .02, t - min(tab(SD, x), .22 * H)), (h - .08, t - .012),
            (.62 * h, t + .15 * c), (.52 * h, t + c), (0, t + c)]

def side_w(x, z):
    p = section(x)[2:7]
    if z <= p[0][1]: return p[0][0]
    for (w0, z0), (w1, z1) in zip(p, p[1:]):
        if z <= z1: return w0 + (w1 - w0) * (z - z0) / max(z1 - z0, 1e-6)
    return p[-1][0]

WHEEL_X = (0.955, 3.83); WHEEL_Z = 0.335; WHEEL_R = 0.335; ARCH_R = 0.40
LAMP_F0, LAMP_F1, AMBER_F = .06, .50, .32
LAMP_R0 = 4.52

stations = sorted(set([x for x, _ in TOP + BOT + HW + CROWN] + [AMBER_F, LAMP_R0, 1.7, 2.4, 3.1]))
stations = [x for x in stations if 0 <= x <= L]

bm = bmesh.new()
rings = []
for x in stations:
    s = section(x)
    half = [bm.verts.new((w, Y(x), z)) for w, z in s]
    other = [bm.verts.new((-w, Y(x), z)) for w, z in s[8:0:-1]]
    rings.append(half + other)
MARK_GRILLE = HUB
for i in range(len(stations) - 1):
    x0, x1 = stations[i], stations[i + 1]
    xm = (x0 + x1) / 2
    for j in range(18):
        k = j if j < 9 else 17 - j
        f = bm.faces.new([rings[i][j], rings[i][(j + 1) % 18], rings[i + 1][(j + 1) % 18], rings[i + 1][j]])
        mi = PAINT
        if LAMP_F0 < xm < .11 and k in (5, 6, 7):   # v2: lamps on the front face only, no strip along the fender
            mi = LAMP
        elif LAMP_F0 < xm < .11 and k == 8:
            mi = MARK_GRILLE
        elif LAMP_R0 < xm < 4.72 and k == 4:
            mi = RED
        elif 4.70 < xm < 4.755 and k in (5, 6, 7):
            mi = RED
        elif 4.755 < xm < 4.765 and k in (5, 6, 7):
            mi = LAMP
        elif 1.40 < xm < 4.10 and k in (6, 7, 8):
            mi = BLACK
        f.material_index = mi
bm.faces.new(rings[0]); bm.faces.new(rings[-1])
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
loft = obj_from_bm('Loft', bm)
for m in MATLIST: loft.data.materials.append(m)
loft_mesh = loft.data

def cutter(name, bm, mats):
    """Cutter object; mats(face) -> material index (cut faces take the cutter's material)."""
    for f in bm.faces: f.material_index = mats(f)
    o = obj_from_bm(name, bm)
    for m in MATLIST: o.data.materials.append(m)
    o.hide_render = True
    return o

def evaluated_bm(o):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = o.evaluated_get(dg)
    bm = bmesh.new(); bm.from_mesh(ev.to_mesh()); ev.to_mesh_clear()
    return bm

# cabin cavity: floor at 0.30, inner side walls at |w| = 0.80, firewall at 1.40, behind the rear bench at 3.85,
# minus the rear wheelhouses (left in the body as humps). Floor = Black carpet, walls = Trim.
CAV_X0, CAV_X1, CAV_W, FLOOR = 1.40, 3.85, 0.80, 0.30
cav = cutter('Cavity', prism_bm([(CAV_X0, FLOOR), (CAV_X1, FLOOR), (CAV_X1, 2.2), (CAV_X0, 2.2)], -CAV_W, CAV_W),
             lambda f: BLACK if f.normal.z < -.9 else TRIM)
for s in (-1, 1):
    hb = bmesh.new()
    bmesh.ops.create_cone(hb, cap_ends=True, segments=40, radius1=.43, radius2=.43, depth=.78)
    hc = cutter('Hump', hb, lambda f: TRIM); hc.location = (s * .86, Y(WHEEL_X[1]), WHEEL_Z); hc.rotation_euler = (0, pi / 2, 0)
    mod = cav.modifiers.new('hump', 'BOOLEAN'); mod.operation = 'DIFFERENCE'; mod.object = hc
cav2 = cutter('Cavity2', evaluated_bm(cav), lambda f: f.material_index)

# door outlines (x, z), seams of the library sedan; B pillar strip 2.62..2.70 stays in the body
DOOR_F = [(1.47, .31), (2.62, .31), (2.62, 1.6), (1.47, 1.6)]
DOOR_R = [(2.70, .31), (3.34, .31), (3.36, .40), (3.41, .52), (3.49, .635), (3.63, .745), (3.72, .85), (3.73, 1.0),
          (3.73, 1.6), (2.70, 1.6)]
DOORS = [('Door_FL', 1, DOOR_F), ('Door_FR', -1, DOOR_F), ('Door_RL', 1, DOOR_R), ('Door_RR', -1, DOOR_R)]

def door_prism(name, s, poly, w_in):
    bm = prism_bm(poly, s * w_in, s * 1.3)
    return cutter(name, bm, lambda f: TRIM if f.normal.x * s < -.9 else SEAM)

# Body: loft - wells - cavity - door prisms
body0 = bpy.data.objects.new('tmp_Body0', loft_mesh.copy()); scene.collection.objects.link(body0); TMP.append(body0)
for wx in WHEEL_X:
    for s in (-1, 1):
        cb = bmesh.new()
        bmesh.ops.create_cone(cb, cap_ends=True, segments=40, radius1=ARCH_R, radius2=ARCH_R, depth=0.72)
        c = cutter('Well', cb, lambda f: BLACK); c.location = (s * 0.86, Y(wx), WHEEL_Z); c.rotation_euler = (0, pi / 2, 0)
        mod = body0.modifiers.new('well', 'BOOLEAN'); mod.operation = 'DIFFERENCE'; mod.object = c
mod = body0.modifiers.new('cabin', 'BOOLEAN'); mod.operation = 'DIFFERENCE'; mod.object = cav2
for name, s, poly in DOORS:
    mod = body0.modifiers.new('door', 'BOOLEAN'); mod.operation = 'DIFFERENCE'; mod.object = door_prism(name, s, poly, .79)
bm = evaluated_bm(body0)

def inset(bm, faces, thick, depth, rim_mi):
    if not faces: return
    r = bmesh.ops.inset_region(bm, faces=faces, thickness=thick, depth=depth, use_even_offset=True, use_boundary=True)
    for f in r['faces']: f.material_index = rim_mi

bm.faces.ensure_lookup_table()
front = lambda f: f.calc_center_median().y < 0
inset(bm, [f for f in bm.faces if f.material_index in (LAMP, AMBER) and front(f)], .014, -.004, TRIM)   # v2: shallow, no dark gap under the hood
grille = [f for f in bm.faces if f.material_index == MARK_GRILLE]
inset(bm, grille, .016, -.010, TRIM)
for f in grille: f.material_index = BLACK
inset(bm, [f for f in bm.faces if f.material_index in (RED, LAMP) and not front(f)], .010, -.008, TRIM)
CUR[0] = 'Body'; finish(obj_from_bm('Body', bm))

# Doors: loft & prism (inner face at |w| = 0.80 is the inner door panel, Trim)
for name, s, poly in DOORS:
    d = bpy.data.objects.new('tmp_' + name, loft_mesh.copy()); scene.collection.objects.link(d); TMP.append(d)
    mod = d.modifiers.new('door', 'BOOLEAN'); mod.operation = 'INTERSECT'; mod.object = door_prism(name, s, poly, .80)
    CUR[0] = name; finish(obj_from_bm(name, evaluated_bm(d)))

# ---------------------------------------------------------------- greenhouse as thick patches
BELT = 1.0; TUMBLE = 0.52
GH = [(1.30, 1.03), (1.50, 1.143), (2.05, 1.455), (2.63, 1.478), (2.69, 1.48), (3.42, 1.468), (3.47, 1.466),
      (3.52, 1.462), (3.80, 1.31), (4.19, 1.10)]
def gh_section(x, zt):
    wb = tab(HW, x) - .045
    zb = tab(TOP, x) - .03
    wat = lambda z: wb - TUMBLE * max(z - BELT, 0)
    return [(wb, zb), (wat(zt - .045), zt - .045), (wat(zt) - .05, zt - .005), (.33, zt + .014), (0, zt + .018)]

def half_pt(x, k):
    p = gh_section(x, tab(GH, x)); i = min(int(k), 3); f = k - i
    return Vector(p[i]).lerp(Vector(p[i + 1]), f)

def S(x, u, d=0.0):
    """Greenhouse surface. u in [0, 8]: 0 = +X belt, 1 = side top, 2 = roof edge, 4 = centre, 8 = -X belt.
    d = offset inward (toward the cabin) in metres."""
    s = 1 if u <= 4 else -1
    k = min(max(u if u <= 4 else 8 - u, 0), 4)
    p = half_pt(x, k)
    T = (half_pt(x, min(k + .02, 4)) - half_pt(x, max(k - .02, 0))).normalized()
    q = p + Vector((-T.y, T.x)) * d
    return Vector((s * q.x, Y(x), q.y))

GHB = {}
def patch(part, x0, x1, u0, u1, mo, mi_in, mw, off=0.0, t=0.035):
    if x1 - x0 < 1e-4 or u1 - u0 < 1e-4: return
    xs = sorted(set([x0, x1] + [x for x, _ in GH + HW + TOP if x0 + 1e-4 < x < x1 - 1e-4]))
    us = sorted(set([u0, u1] + [float(k) for k in range(9) if u0 + 1e-4 < k < u1 - 1e-4]))
    bm = GHB.setdefault(part, bmesh.new())
    O = [[bm.verts.new(S(x, u, off)) for u in us] for x in xs]
    I = [[bm.verts.new(S(x, u, off + t)) for u in us] for x in xs]
    fs = []
    nx, nu = len(xs), len(us)
    for i in range(nx - 1):
        for j in range(nu - 1):
            fs.append((bm.faces.new([O[i][j], O[i + 1][j], O[i + 1][j + 1], O[i][j + 1]]), mo))
            fs.append((bm.faces.new([I[i][j], I[i][j + 1], I[i + 1][j + 1], I[i + 1][j]]), mi_in))
    for i in range(nx - 1):
        for j in (0, nu - 1):
            fs.append((bm.faces.new([O[i][j], I[i][j], I[i + 1][j], O[i + 1][j]]), mw))
    for j in range(nu - 1):
        for i in (0, nx - 1):
            fs.append((bm.faces.new([O[i][j], O[i][j + 1], I[i][j + 1], I[i][j]]), mw))
    for f, m in fs: f.material_index = m
    bmesh.ops.recalc_face_normals(bm, faces=[f for f, _ in fs])

def ustep(xm, u, w, sgn):
    lo, hi = 0.0, 1.0
    for _ in range(30):
        mid = (lo + hi) / 2
        if (S(xm, u + sgn * mid) - S(xm, u)).length < w: lo = mid
        else: hi = mid
    return u + sgn * lo

def framed(fpart, gpart, x0, x1, u0, u1, bands, inner=TRIM, t=.035, splits=()):
    """Window: frame bands (each a ring of 4 thick strips) in fpart, glass panes in gpart."""
    xm = (x0 + x1) / 2
    for w, mi in bands:
        ua, ub = ustep(xm, u0, w, 1), ustep(xm, u1, w, -1)
        xa, xb = x0 + w, x1 - w
        patch(fpart, x0, x1, u0, ua, mi, inner, mi, 0, t)
        patch(fpart, x0, x1, ub, u1, mi, inner, mi, 0, t)
        patch(fpart, x0, xa, ua, ub, mi, inner, mi, 0, t)
        patch(fpart, xb, x1, ua, ub, mi, inner, mi, 0, t)
        x0, x1, u0, u1 = xa, xb, ua, ub
    edges = [x0]
    for sa, sb, mi in splits:
        patch(fpart, sa, sb, u0, u1, mi, inner, BLACK, 0, t)
        edges += [sa, sb]
    edges.append(x1)
    for ga, gb in zip(edges[::2], edges[1::2]):
        patch(gpart, ga, gb, u0, u1, GLASS, GLASS, GLASS, .012, .006)

WS_BANDS = [(.045, PAINT), (.018, BLACK)]
DOOR_BANDS = [(.020, PAINT), (.016, BLACK)]
framed('Body', 'Windshield', 1.30, 2.05, 2, 6, WS_BANDS)
framed('Body', 'RearWindow', 3.52, 4.19, 2, 6, WS_BANDS)
patch('Roof', 2.05, 3.52, 1, 7, PAINT, HEAD, PAINT, 0, .03)
for lo, hi in ((0, 1), (7, 8)):
    patch('Body', 1.30, 1.47, lo, hi, PAINT, TRIM, PAINT)      # A pillar foot
    patch('Body', 2.62, 2.70, lo, hi, TRIM, TRIM, TRIM)        # B pillar
    patch('Body', 3.73, 4.19, lo, hi, PAINT, TRIM, PAINT)      # C pillar
for lo, hi in ((1, 2), (6, 7)):
    patch('Body', 1.30, 2.05, lo, hi, PAINT, TRIM, PAINT)      # A pillar
    patch('Body', 3.52, 4.19, lo, hi, PAINT, TRIM, PAINT)      # C pillar top
for name, s, poly in DOORS:
    u0, u1 = (0, 1) if s > 0 else (7, 8)
    if name.startswith('Door_F'):
        framed(name, name, 1.47, 2.62, u0, u1, DOOR_BANDS, t=.04)
    else:
        framed(name, name, 2.70, 3.73, u0, u1, DOOR_BANDS, t=.04, splits=[(3.42, 3.47, TRIM)])

# ---------------------------------------------------------------- arch lips (Body)
CUR[0] = 'Body'
LIP0, LIP1 = ARCH_R - .008, ARCH_R + .055
for wx in WHEEL_X:
    for s in (-1, 1):
        n = 26; a0 = math.radians(-4); a1 = math.radians(184)
        def lip(a):
            ca, sa = math.cos(a), math.sin(a)
            xi, zi = wx + LIP0 * ca, WHEEL_Z + LIP0 * sa
            xo, zo = wx + LIP1 * ca, WHEEL_Z + LIP1 * sa
            wi = side_w(xi, zi)
            A = Vector((s * (wi + .022), Y(xi), zi))
            B = Vector((s * (side_w(xo, zo) - .002), Y(xo), zo))
            C = Vector((s * (wi - .05), Y(xi), zi))
            return A, B, C, Vector((0, -ca, -sa))
        for i in range(n):
            A0, B0, C0, h0 = lip(a0 + (a1 - a0) * i / n)
            A1, B1, C1, h1 = lip(a0 + (a1 - a0) * (i + 1) / n)
            face([A0, A1, B1, B0], PAINT, (s, 0, 0))
            face([C0, C1, A1, A0], PAINT, h0 + h1)

# ---------------------------------------------------------------- seams, mouldings, handles, mirrors
def side_strip(pts, width, mi, off=.004, sides=(1, -1)):
    for s in sides:
        for (x0, z0), (x1, z1) in zip(pts, pts[1:]):
            a, b = Vector((x0, z0)), Vector((x1, z1))
            d = (b - a); u = d.normalized(); nrm = Vector((-u.y, u.x)) * width / 2
            a = a - u * width / 2; b = b + u * width / 2; d = b - a
            k = max(1, int(d.length / .22))
            for i in range(k):
                p, q = a + d * i / k, a + d * (i + 1) / k
                quad = [p - nrm, q - nrm, q + nrm, p + nrm]
                face([(s * (side_w(v.x, v.y) + off), Y(v.x), v.y) for v in quad], mi, (s, 0, 0))

SW = .012
CUR[0] = 'Body'
side_strip([(.05, .585), (.56, .585)], SW, SEAM)
side_strip([(4.24, .62), (4.77, .62)], SW, SEAM)
side_strip([(4.02, .80), (4.16, .80), (4.16, .92), (4.02, .92), (4.02, .80)], .008, SEAM, sides=(1,))
for s in (-1, 1):
    tag = 'L' if s > 0 else 'R'
    CUR[0] = 'Door_F' + tag
    side_strip([(1.47, .31), (1.47, .985)], SW, SEAM, sides=(s,))
    side_strip([(2.62, .31), (2.62, .985)], SW, SEAM, sides=(s,))
    side_strip([(1.47, .31), (2.62, .31)], SW, SEAM, sides=(s,))
    box('Moulding', (s * .906, Y(2.06), .565), (.04, 1.06, .05), PAINT, .014)
    w = side_w(2.41, .86)
    box('HandleCup', (s * (w + .001), Y(2.41), .86), (.012, .24, .075), SEAM, 0)
    box('Handle', (s * (w + .012), Y(2.41), .865), (.03, .20, .04), TRIM, .012)
    box('MirrorSail', (s * .838, Y(1.66), 1.045), (.03, .20, .085), BLACK, .008)
    box('MirrorStalk', (s * .89, Y(1.70), 1.04), (.10, .06, .045), BLACK, .01)
    box('Mirror', (s * 1.005, Y(1.71), 1.075), (.20, .10, .135), PAINT, .03, rot=(0, 0, s * 0.18), seg=3)
    box('MirrorGlass', (s * 1.012, Y(1.71) + .05, 1.075), (.16, .012, .10), BLACK, 0, rot=(0, 0, s * 0.18))
    # inside: armrest, pull handle, sill cap
    box('Armrest', (s * .765, Y(2.02), .64), (.07, .55, .05), TRIM, .015)
    box('InnerHandle', (s * .79, Y(1.75), .82), (.02, .12, .03), HUB, .006)
    box('SillCap', (s * .79, Y(2.045), .975), (.04, 1.09, .03), BLACK, .008)
    CUR[0] = 'Door_R' + tag
    side_strip([(2.70, .31), (2.70, .985)], SW, SEAM, sides=(s,))
    side_strip([(3.73, 1.0), (3.72, .85), (3.63, .745), (3.49, .635), (3.41, .52), (3.36, .40), (3.34, .31)], SW, SEAM, sides=(s,))
    side_strip([(2.70, .31), (3.34, .31)], SW, SEAM, sides=(s,))
    box('Moulding', (s * .906, Y(3.055), .565), (.04, .63, .05), PAINT, .014)
    w = side_w(3.45, .86)
    box('HandleCup', (s * (w + .001), Y(3.45), .86), (.012, .24, .075), SEAM, 0)
    box('Handle', (s * (w + .012), Y(3.45), .865), (.03, .20, .04), TRIM, .012)
    box('Armrest', (s * .765, Y(3.05), .64), (.07, .45, .05), TRIM, .015)
    box('InnerHandle', (s * .79, Y(2.92), .82), (.02, .12, .03), HUB, .006)
    box('SillCap', (s * .79, Y(3.21), .975), (.04, .98, .03), BLACK, .008)

# ---------------------------------------------------------------- front and rear details (Body)
CUR[0] = 'Body'
def slant(x):
    return tab(TOP, x) + tab(CROWN, x)
for k in range(3):
    x = .070 + k * .0145
    ang = math.atan2(.80 + .03 - .645, .11 - .06)
    box('GrilleBar', (0, Y(x) - .004, slant(x) - .008), (.80, .014, .022), TRIM, .004, rot=(-(pi / 2 - ang), 0, 0))
box('Intake', (0, Y(0) + .012, .325), (.92, .05, .09), BLACK, .012)
box('IntakeBar', (0, Y(0) + .0, .325), (.90, .03, .014), TRIM, 0)
# v2: a real bumper bar that wraps the corners and runs back to the wheel arch, and amber side markers
BUMP_Z0, BUMP_Z1 = .405, .535
BUMP = [(.93, .50), (.925, .30), (.905, .11), (.895, .08), (.86, .03), (.80, -.012), (.72, -.035)]   # (half width, x), rear to front
outline = [(w, x) for w, x in BUMP] + [(-w, x) for w, x in BUMP[::-1]]
bb = bmesh.new()
ring = []
for w, x in outline:
    wi = w - math.copysign(.07, w)
    xi = x + .07 if x < .05 else x
    ring.append((bb.verts.new((w, Y(x), BUMP_Z0)), bb.verts.new((w, Y(x), BUMP_Z1)),
                 bb.verts.new((wi, Y(xi), BUMP_Z0)), bb.verts.new((wi, Y(xi), BUMP_Z1))))
for a, b in zip(ring, ring[1:]):
    bb.faces.new([a[0], b[0], b[1], a[1]])      # outer wall
    bb.faces.new([a[1], b[1], b[3], a[3]])      # top
    bb.faces.new([a[0], a[2], b[2], b[0]])      # bottom
for e in (ring[0], ring[-1]):
    bb.faces.new([e[0], e[1], e[3], e[2]])      # end caps at the wheel arches
bmesh.ops.recalc_face_normals(bb, faces=bb.faces)
o = obj_from_bm('BumperF', bb); add_bevel(o, .012, 2); finish(o, TRIM)
for s in (-1, 1):
    box('Fog', (s * .60, Y(0) + .02, .325), (.13, .06, .06), LAMP, .010)
    box('Marker', (s * (side_w(.24, .60) + .002), Y(.24), .60), (.014, .17, .05), AMBER, .004, rot=(0, 0, -s * .105))
box('PlateRear', (0, Y(4.80) + .004, .50), (.48, .012, .12), LAMP, .004)
box('TrunkHandle', (0, Y(4.765) + .012, .70), (.50, .02, .03), TRIM, .006)
box('TrunkSeam', (0, Y(4.44), 1.091), (.90, .012, .008), SEAM, 0)
cyl('Exhaust', (-.48, Y(4.74), .275), .032, .14, 'Y', HUB, 12)
cyl('ExhaustBore', (-.48, Y(4.812), .275), .024, .004, 'Y', BLACK, 12)

def hub(cx, cy, cz, s):
    def P(r, a, x): return Vector((cx + s * x, cy + s * r * math.cos(a), cz + r * math.sin(a)))
    AX = Vector((s, 0, 0))
    N = 24; ro, ri, xf, xr = .185, .108, .028, .004
    prof = [(.236, 0.0), (.218, .018), (.198, .026), (ro, xf)]
    for i in range(N):
        a0, a1 = 2 * pi * i / N, 2 * pi * (i + 1) / N
        for (ra, xa), (rb, xb) in zip(prof, prof[1:]):
            face([P(ra, a0, xa), P(ra, a1, xa), P(rb, a1, xb), P(rb, a0, xb)], HUB, AX)
        if i % 4 in (1, 2):
            mid = P((ro + ri) / 2, (a0 + a1) / 2, xr)
            def wall(vs):
                c = sum(vs, Vector()) / len(vs); face(vs, BLACK, mid - c)
            face([P(ro, a0, xr), P(ro, a1, xr), P(ri, a1, xr), P(ri, a0, xr)], BLACK, AX)
            wall([P(ro, a0, xr), P(ro, a1, xr), P(ro, a1, xf), P(ro, a0, xf)])
            wall([P(ri, a0, xr), P(ri, a1, xr), P(ri, a1, xf), P(ri, a0, xf)])
            ae = a0 if i % 4 == 1 else a1
            wall([P(ro, ae, xr), P(ri, ae, xr), P(ri, ae, xf), P(ro, ae, xf)])
        else:
            face([P(ro, a0, xf), P(ro, a1, xf), P(ri, a1, xf), P(ri, a0, xf)], HUB, AX)
        face([P(ri, a0, xf), P(ri, a1, xf), P(.072, a1, .032), P(.072, a0, .032)], HUB, AX)
        face([P(.072, a0, .032), P(.072, a1, .032), P(.056, a1, .048), P(.056, a0, .048)], HUB, AX)
        face([P(.056, a0, .048), P(.056, a1, .048), P(0, 0, .048)], HUB, AX)

for wx in WHEEL_X:
    for s in (-1, 1):
        cx = s * 0.765
        cyl('Tyre', (cx, Y(wx), WHEEL_Z), WHEEL_R, 0.215, 'X', BLACK, 32, 0.045, 3)
        hub(cx + s * 0.098, Y(wx), WHEEL_Z, s)
cyl('Axle', (0, Y(WHEEL_X[0]), WHEEL_Z), .05, 1.3, 'X', BLACK, 8)   # front only: the rear one would cross the cabin

# ---------------------------------------------------------------- interior
CUR[0] = 'Interior'
DRV = 1          # driver side sign (+X = car-left)
FZ, RZ = .48, .50            # cushion surface heights, front and rear
FX, RX = 2.20, 3.03          # cushion centres (distance from the front bumper)
SEATS = {'Seat_Driver': (DRV * .40, Y(FX), FZ), 'Seat_Passenger': (-DRV * .40, Y(FX), FZ),
         'Seat_RearLeft': (.36, Y(RX), RZ), 'Seat_RearRight': (-.36, Y(RX), RZ)}

# dashboard: profile across the full cabin width, padded top in Black
dash = prism_bm([(1.40, .62), (1.55, .60), (1.72, .68), (1.84, .80), (1.88, .92), (1.84, 1.00), (1.74, 1.045),
                 (1.55, 1.055), (1.40, 1.02)], -.785, .785)
o = obj_from_bm('Dash', dash); add_bevel(o, .02); finish(o, TRIM)
for p in o.data.polygons:
    if p.normal.z > .6: p.material_index = BLACK
box('Binnacle', (DRV * .40, Y(1.80), 1.065), (.38, .16, .10), BLACK, .025)
for dx in (-.085, .085):
    cyl('Gauge', (DRV * .40 + dx, Y(1.882), 1.055), .055, .008, 'Y', HUB, 24)
box('Stack', (0, Y(1.80), .78), (.30, .16, .42), TRIM, .02)
box('Screen', (0, Y(1.882), .90), (.22, .008, .13), BLACK, 0)
for dx in (-.07, .07):
    cyl('Knob', (dx, Y(1.89), .77), .022, .02, 'Y', HUB, 12)
for wx in (-.60, -.17, .17, .60):
    box('Vent', (wx, Y(1.862), .955), (.14, .02, .05), BLACK, .006)
box('Glovebox', (-DRV * .42, Y(1.855), .84), (.38, .02, .14), BLACK, .006)
# tunnel, console, gear lever
box('Tunnel', (0, Y(2.45), .36), (.30, 1.90, .12), BLACK, .03)
box('Console', (0, Y(2.32), .44), (.22, .70, .28), TRIM, .025)
box('ConsoleLid', (0, Y(2.53), .60), (.21, .30, .05), HEAD, .02)
box('Gate', (0, Y(2.08), .585), (.10, .16, .012), BLACK, .004)
cyl('GearStick', (0, Y(2.08), .65), .011, .13, 'Z', HUB, 8)
sph('GearKnob', (0, Y(2.08), .725), .03, BLACK, 12)
# steering wheel and column (wheel axis points back and up toward the driver)
A = Vector((0, math.cos(math.radians(25)), math.sin(math.radians(25))))
WC = Vector((DRV * .40, Y(2.00), .93))
MW = Matrix.Translation(WC) @ A.to_track_quat('Z', 'Y').to_matrix().to_4x4()
bm = bmesh.new(); N, n, R, r = 28, 8, .18, .017
rg = [[bm.verts.new(((R + r * math.cos(2 * pi * j / n)) * math.cos(2 * pi * i / N),
                     (R + r * math.cos(2 * pi * j / n)) * math.sin(2 * pi * i / N), r * math.sin(2 * pi * j / n)))
       for j in range(n)] for i in range(N)]
for i in range(N):
    for j in range(n):
        bm.faces.new([rg[i][j], rg[(i + 1) % N][j], rg[(i + 1) % N][(j + 1) % n], rg[i][(j + 1) % n]])
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
bmesh.ops.transform(bm, matrix=MW, verts=bm.verts)
finish(obj_from_bm('WheelRim', bm), BLACK)
mcyl('WheelHub', MW, (0, 0, 0), .065, .05, BLACK, 20, .01)
for ang in (0, pi, -pi / 2):
    Ms = MW @ Matrix.Rotation(ang, 4, 'Z')
    mbox('Spoke', Ms, (.11, 0, 0), (.13, .035, .015), BLACK, .005)
mcyl('Column', MW, (0, 0, -.19), .032, .30, BLACK, 12)
# pedals (accelerator to the driver's right, i.e. toward the centre)
for pw, ph in ((.30, .10), (.48, .07)):
    box('Pedal', (DRV * pw, Y(1.58), .42), (.075 if pw < .4 else .11, .025, ph), HUB, .006, rot=(.45, 0, 0))
    box('PedalArm', (DRV * pw, Y(1.55), .53), (.02, .02, .18), BLACK, 0, rot=(.45, 0, 0))
box('FootRest', (DRV * .66, Y(1.56), .38), (.08, .03, .14), BLACK, .006, rot=(.6, 0, 0))

def seat_back(M, places, width, h, mid=None):
    for px in places:
        mbox('BackPad', M, (px, .06, .06 + h / 2), (width, .12, h), HEAD, .035)
        mbox('Headrest', M, (px, .07, h + .17), (.26, .10, .17), HEAD, .035)
        for dx in (-.07, .07):
            mcyl('Post', M, (px + dx, .07, h + .06), .008, .10, HUB, 6)
    if mid: mbox('BackMid', M, (0, .07, .04 + mid / 2), (.22, .10, mid), TRIM, .02)

# front seats: insert + bolsters, tilted backrest with headrest
for s in (1, -1):
    cx = s * .40
    box('SeatBase', (cx, Y(FX), .35), (.40, .40, .10), BLACK, .015)
    box('Cushion', (cx, Y(FX), FZ - .05), (.36, .50, .10), HEAD, .03)
    for b in (-1, 1):
        box('Bolster', (cx + b * .22, Y(FX + .02), FZ - .03), (.10, .48, .12), TRIM, .035)
    M = Matrix.Translation((cx, Y(2.45), .44)) @ Matrix.Rotation(-.30, 4, 'X')
    seat_back(M, (0,), .36, .60)
    for b in (-1, 1):
        mbox('BackBolster', M, (b * .22, .04, .36), (.10, .16, .60), TRIM, .035)
# rear bench: two shaped places with a lower middle section
box('BenchBase', (0, Y(RX), .35), (1.30, .46, .10), BLACK, .015)
for s in (1, -1):
    box('BenchPlace', (s * .36, Y(RX), RZ - .055), (.52, .50, .11), HEAD, .035)
box('BenchMid', (0, Y(RX + .02), RZ - .07), (.22, .46, .08), TRIM, .02)
M = Matrix.Translation((0, Y(3.28), .44)) @ Matrix.Rotation(-.32, 4, 'X')
seat_back(M, (-.36, .36), .52, .60, mid=.56)
box('ParcelShelf', (0, Y(3.74), 1.03), (1.56, .40, .03), BLACK, .008)

# ---------------------------------------------------------------- merge each part into one mesh
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
built = {}
for pn in PARTS:
    bm = bmesh.new()
    for o in GROUPS[pn]:
        ev = o.evaluated_get(dg); me = ev.to_mesh()
        me.transform(o.matrix_world); bm.from_mesh(me); ev.to_mesh_clear()
    extra = []
    if pn in GHB: extra.append(GHB[pn])
    sb = bmesh.new()
    for vs, mi, hint, part in SOUP:
        if part != pn: continue
        f = sb.faces.new([sb.verts.new(v) for v in vs]); f.material_index = mi
        f.normal_update()
        if f.normal.dot(hint) < 0: f.normal_flip()
    bmesh.ops.remove_doubles(sb, verts=sb.verts, dist=1e-5)
    extra.append(sb)
    for e in extra:
        tmp = bpy.data.meshes.new('tmp_merge'); e.to_mesh(tmp); bm.from_mesh(tmp); bpy.data.meshes.remove(tmp)
    built[pn] = bm
for o in TMP:
    bpy.data.objects.remove(o)

root = bpy.data.objects.new(NAME, None); scene.collection.objects.link(root)
stats = {'parts': {}}
part_objs = []
for pn in PARTS:
    mesh = bpy.data.meshes.new(pn + '_Mesh'); built[pn].to_mesh(mesh); built[pn].free()
    used = sorted({p.material_index for p in mesh.polygons})
    for i in used: mesh.materials.append(MATLIST[i])
    remap = {old: new for new, old in enumerate(used)}
    for p in mesh.polygons: p.material_index = remap[p.material_index]
    mesh.polygons.foreach_set('use_smooth', [True] * len(mesh.polygons))
    mesh.set_sharp_from_angle(angle=math.radians(22))
    o = bpy.data.objects.new(pn, mesh); scene.collection.objects.link(o); o.parent = root
    part_objs.append(o)
    stats['parts'][pn] = {'tris': sum(len(p.vertices) - 2 for p in mesh.polygons),
                          'materials': [MATLIST[i].name for i in used]}
allv = [v.co for o in part_objs for v in o.data.vertices]
xs = [v.x for v in allv]; ys = [v.y for v in allv]; zs = [v.z for v in allv]
stats['size'] = [round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3), round(max(zs) - min(zs), 3)]
stats['min_z'] = round(min(zs), 3)
stats['tris'] = sum(p['tris'] for p in stats['parts'].values())
stats['materials'] = sorted({m for p in stats['parts'].values() for m in p['materials']})
print(f"[{NAME}] triangles {stats['tris']}, materials {len(stats['materials'])}, size {stats['size']} m")
for pn, p in stats['parts'].items(): print(f"  {pn}: {p['tris']} tris, {p['materials']}")

empties = []
for sn, pos in list(SEATS.items()) + [('Seat', SEATS['Seat_Driver'])]:
    e = bpy.data.objects.new(sn, None); e.location = pos; e.empty_display_size = .15
    scene.collection.objects.link(e); e.parent = root; empties.append(e)

# head room: roof inner surface above each seat point, straight up and at the head (0.29 m behind the point)
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
stats['seats'] = {}
for sn, pos in SEATS.items():
    r = {'pos': [round(c, 3) for c in pos]}
    for key, dy in (('roof_above', 0.0), ('roof_at_head', 0.29)):
        hit, loc, nrm, idx, ob, mw = scene.ray_cast(dg, Vector(pos) + Vector((0, dy, .01 if dy == 0 else .60)), Vector((0, 0, 1)))
        r[key] = round(loc.z, 3) if hit else None
        r[key + '_obj'] = ob.name if hit else None
    r['cushion_to_roof'] = round(min(v for v in (r['roof_above'], r['roof_at_head']) if v) - pos[2], 3)
    r['headroom_1p8m'] = round(r['cushion_to_roof'] - .90, 3)   # 1.8 m person: head top 0.90 above the cushion
    stats['seats'][sn] = r
print(json.dumps(stats['seats'], indent=1))
json.dump(stats, open(f'{OUT}/stats.json', 'w'), indent=1)

for o in scene.objects: o.select_set(False)
for o in [root] + part_objs + empties: o.select_set(True)
bpy.ops.export_scene.fbx(filepath=f'{OUT}/{NAME}.fbx', use_selection=True, apply_unit_scale=True,
                         apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)

if '--no-render' in sys.argv: sys.exit(0)

# ---------------------------------------------------------------- previews (render only, not exported)
world = bpy.data.worlds.new('W'); scene.world = world; world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.66, 0.66, 0.66, 1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.0
gm = bpy.data.materials.new('Ground'); gm.use_nodes = True
gm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.50, 0.50, 0.50, 1)
gm.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 1.0
bpy.ops.mesh.primitive_plane_add(size=600, location=(0, 0, 0)); bpy.context.active_object.data.materials.append(gm)
def sun(frm, energy):
    bpy.ops.object.light_add(type='SUN', location=frm); o = bpy.context.active_object
    o.data.energy = energy; o.data.angle = math.radians(12)
    o.rotation_euler = (-Vector(frm)).to_track_quat('-Z', 'Y').to_euler()
    return o
sun((-3, -5, 8), 2.0); sun((6, -2, 3), 0.7)
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x, scene.render.resolution_y = 1672, 941
scene.view_settings.view_transform = 'Standard'
try: scene.eevee.taa_render_samples = 32
except Exception: pass
cam_data = bpy.data.cameras.new('Cam'); cam = bpy.data.objects.new('Cam', cam_data)
scene.collection.objects.link(cam); scene.camera = cam

# 1.8 m seated stand-in: capsule torso, sphere head, capsule thighs and shins
fm = bpy.data.materials.new('Figure'); fm.use_nodes = True
fm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.55, 0.55, 0.55, 1)
def capsule(a, b, r):
    a, b = Vector(a), Vector(b); d = b - a
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, segments=16, radius1=r, radius2=r, depth=d.length)
    for c in (-d.length / 2, d.length / 2):
        sb = bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=r)
        bmesh.ops.translate(bm, vec=(0, 0, c), verts=sb['verts'])
    M = Matrix.Translation((a + b) / 2) @ d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=M, verts=bm.verts)
    me = bpy.data.meshes.new('fig'); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new('Figure', me); scene.collection.objects.link(o); o.data.materials.append(fm)
    o.data.polygons.foreach_set('use_smooth', [True] * len(o.data.polygons))
    return o
FIGS = []
def figure(sp, floor_z=FLOOR):
    x, y, z = sp
    hip = Vector((x, y + .12, z + .11))
    head = Vector((x, y + .29, z + .90 - .11))
    neck = head - Vector((0, .03, .17))
    FIGS.append(capsule(hip, neck, .15))
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=10, radius=.11)
    me = bpy.data.meshes.new('head'); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new('Figure', me); o.location = head; scene.collection.objects.link(o)
    o.data.materials.append(fm); o.data.polygons.foreach_set('use_smooth', [True] * len(o.data.polygons)); FIGS.append(o)
    for dx in (-.10, .10):
        knee = Vector((x + dx, y - .30, z + .14))
        foot = Vector((x + dx, y - .42, floor_z + .07))
        FIGS.append(capsule(hip + Vector((dx, -.02, -.02)), knee, .075))
        FIGS.append(capsule(knee, foot, .06))
    for o in FIGS: o.hide_render = True

def show(hidden=(), figs=False):
    for o in part_objs: o.hide_render = o.name in hidden
    for o in FIGS: o.hide_render = not figs

def shoot(name, loc, target, lens=50):
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    cam_data.type = 'PERSP'; cam_data.lens = lens
    scene.render.filepath = f'{OUT}/{name}.png'; bpy.ops.render.render(write_still=True)

figure(SEATS['Seat_Driver']); figure(SEATS['Seat_RearRight'])
show()
shoot('render-34', (3.95, -5.55, 1.75), (-0.05, -0.3, 0.66), 47)
show(hidden=('Roof',), figs=True)
shoot('render-noroof', (4.3, -3.2, 4.9), (0, .15, .55), 36)
show(hidden=('Door_FL', 'Door_RL'), figs=True)
shoot('render-nodoors', (7.2, .15, 1.0), (0, .15, .78), 40)
show()
bpy.ops.object.light_add(type='AREA', location=(0, Y(2.3), 1.30)); cl = bpy.context.active_object
cl.data.energy = 3; cl.data.size = 1.0; cl.rotation_euler = (0, 0, 0); cl.rotation_euler = (pi, 0, 0)
shoot('render-inside', (0.0, Y(3.25), 1.22), (0.05, Y(1.50), .90), 17)

# ---------------------------------------------------------------- compare.jpg: references on top, renders below
def px(path):
    if not os.path.exists(path): return np.full((941, 1672, 4), .5, np.float32)
    im = bpy.data.images.load(path)
    if tuple(im.size) != (1672, 941): im.scale(1672, 941)
    a = np.empty(1672 * 941 * 4, np.float32); im.pixels.foreach_get(a)
    return a.reshape(941, 1672, 4)
D = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else OUT
tiles = [[f'{OUT}/ref-noroof.png', f'{OUT}/ref-nodoors.png', f'{OUT}/render-34.png'],
         [f'{OUT}/render-noroof.png', f'{OUT}/render-nodoors.png', f'{OUT}/render-inside.png']]
rows = [np.hstack([px(p)[::2, ::2] for p in r]) for r in tiles]
grid = np.vstack(rows[::-1]); grid[..., 3] = 1     # Blender images are bottom-up
h, w = grid.shape[:2]
out = bpy.data.images.new('compare', w, h); out.pixels.foreach_set(grid.ravel())
out.filepath_raw = f'{OUT}/compare.jpg'; out.file_format = 'JPEG'; out.save()
print('[SedanBuck] done')

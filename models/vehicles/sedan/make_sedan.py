# Generic four-door sedan at previs-library detail (own design, no brand), round 2 "fable" build.
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_sedan.py -- <out dir>
# Convention: 1 unit = 1 m, front toward -Y, up +Z, origin on the ground at the centre.
# The body is a loft of cross-sections along the length (so hood, shoulder, tumblehome and nose taper are
# real shapes), wheel wells are booleans, lamps / grille / glass are inset regions of the loft.
# Side view measured from ../../sedan/ref-side.png: 337 px per metre along the length. The reference is
# stubbier than a real sedan (1.67 m tall at that scale), so heights use 380 px per metre to land on 1.48 m.
import bpy, bmesh, sys, os, math
import numpy as np
from mathutils import Vector, Matrix

OUT = sys.argv[sys.argv.index('--') + 1]
REF = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'sedan')
NAME = 'Sedan'
L = 4.80
pi = math.pi

def Y(x):  # distance from the front bumper -> scene Y (front is -Y)
    return x - L / 2

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ---------------------------------------------------------------- materials (same slot order on every part)
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

parts = []
def finish(o, mi=None):
    for m in MATLIST: o.data.materials.append(m)
    if mi is not None:
        for p in o.data.polygons: p.material_index = mi
    parts.append(o)
    return o

def obj_from_bm(name, bm):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); scene.collection.objects.link(o)
    return o

def box(name, c, size, mi, bevel=0.0, rot=(0, 0, 0), seg=2):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1)
    for v in bm.verts: v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    o = obj_from_bm(name, bm); o.location = c; o.rotation_euler = rot
    if bevel:
        b = o.modifiers.new('bevel', 'BEVEL'); b.width = bevel; b.segments = seg; b.limit_method = 'ANGLE'
    return finish(o, mi)

def cyl(name, c, r, depth, axis, mi, n=32, bevel=0.0, seg=2, rot=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=n, radius1=r, radius2=r, depth=depth)
    o = obj_from_bm(name, bm); o.location = c
    o.rotation_euler = rot or {'X': (0, pi / 2, 0), 'Y': (pi / 2, 0, 0), 'Z': (0, 0, 0)}[axis]
    if bevel:
        b = o.modifiers.new('bevel', 'BEVEL'); b.width = bevel; b.segments = seg; b.limit_method = 'ANGLE'
    return finish(o, mi)

# Loose faces with an outward hint, welded into one "Details" object at the end (winding fixed per face,
# because Unity culls back faces).
SOUP = []
def face(verts, mi, hint):
    SOUP.append(([Vector(v) for v in verts], mi, Vector(hint)))

# ---------------------------------------------------------------- body sections
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
SD = [(0, .012), (.06, .012), (.11, .14), (.50, .11), (1.0, .09)]   # shoulder drop below the hood line

def section(x):
    """Half cross-section (lateral, height) from the bottom centre round to the top centre."""
    t, b, h, c = tab(TOP, x), tab(BOT, x), tab(HW, x), tab(CROWN, x)
    H = t - b
    return [(0, b), (h - .14, b), (h - .03, b + min(.07, .2 * H)), (h, b + .42 * H),
            (h - .004, b + tab(F4, x) * H), (h - .02, t - min(tab(SD, x), .22 * H)), (h - .08, t - .012),
            (.62 * h, t + .15 * c), (.52 * h, t + c), (0, t + c)]

def side_w(x, z):
    """Lateral position of the body side at height z."""
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
MARK_GRILLE = HUB  # temporary marker, the body has no hub faces
for i in range(len(stations) - 1):
    x0, x1 = stations[i], stations[i + 1]
    xm = (x0 + x1) / 2
    for j in range(18):
        k = j if j < 9 else 17 - j
        f = bm.faces.new([rings[i][j], rings[i][(j + 1) % 18], rings[i + 1][(j + 1) % 18], rings[i + 1][j]])
        mi = PAINT
        if LAMP_F0 < xm < LAMP_F1 and (k == 5 or (k in (6, 7) and xm < .11)):
            mi = AMBER if xm > AMBER_F else LAMP
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
body0 = obj_from_bm('Body0', bm)
for m in MATLIST: body0.data.materials.append(m)

# wheel wells: closed pockets, their faces take the cutter's (black) material index
cutters = []
for wx in WHEEL_X:
    for s in (-1, 1):
        cb = bmesh.new()
        bmesh.ops.create_cone(cb, cap_ends=True, segments=40, radius1=ARCH_R, radius2=ARCH_R, depth=0.72)
        c = obj_from_bm('cut', cb); c.location = (s * 0.86, Y(wx), WHEEL_Z); c.rotation_euler = (0, pi / 2, 0)
        for m in MATLIST: c.data.materials.append(m)
        for p in c.data.polygons: p.material_index = BLACK
        mod = body0.modifiers.new('well', 'BOOLEAN'); mod.operation = 'DIFFERENCE'; mod.object = c
        cutters.append(c)
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
ev = body0.evaluated_get(dg)
bm = bmesh.new(); bm.from_mesh(ev.to_mesh()); ev.to_mesh_clear()
for o in cutters + [body0]: bpy.data.objects.remove(o)

def inset(bm, faces, thick, depth, rim_mi):
    if not faces: return
    r = bmesh.ops.inset_region(bm, faces=faces, thickness=thick, depth=depth, use_even_offset=True, use_boundary=True)
    for f in r['faces']: f.material_index = rim_mi

bm.faces.ensure_lookup_table()
front = lambda f: f.calc_center_median().y < 0
inset(bm, [f for f in bm.faces if f.material_index in (LAMP, AMBER) and front(f)], .014, -.012, TRIM)
grille = [f for f in bm.faces if f.material_index == MARK_GRILLE]
inset(bm, grille, .016, -.022, TRIM)
for f in grille: f.material_index = BLACK
inset(bm, [f for f in bm.faces if f.material_index in (RED, LAMP) and not front(f)], .010, -.008, TRIM)
finish(obj_from_bm('Body', bm))

# ---------------------------------------------------------------- greenhouse (roof, pillars, inset glass)
BELT = 1.0; TUMBLE = 0.52
GH = [(1.30, 1.03), (1.50, 1.143), (2.05, 1.455), (2.63, 1.478), (2.69, 1.48), (3.42, 1.468), (3.47, 1.466),
      (3.52, 1.462), (3.80, 1.31), (4.19, 1.10)]
def gh_section(x, zt):
    wb = tab(HW, x) - .045
    zb = tab(TOP, x) - .03
    wat = lambda z: wb - TUMBLE * max(z - BELT, 0)
    return [(wb, zb), (wat(zt - .045), zt - .045), (wat(zt) - .05, zt - .005), (.33, zt + .014), (0, zt + .018)]

bm = bmesh.new()
rings = []
for x, zt in GH:
    s = gh_section(x, zt)
    rings.append([bm.verts.new((w, Y(x), z)) for w, z in s] + [bm.verts.new((-w, Y(x), z)) for w, z in s[3::-1]])
regions = {}
for i in range(len(GH) - 1):
    xm = (GH[i][0] + GH[i + 1][0]) / 2
    for j in range(9):
        f = bm.faces.new([rings[i][j], rings[i][(j + 1) % 9], rings[i + 1][(j + 1) % 9], rings[i + 1][j]])
        f.material_index = PAINT
        side = 'L' if j == 0 else 'R' if j == 7 else None
        if j == 8: f.material_index = BLACK
        elif j in (2, 3, 4, 5) and xm < 2.05: regions.setdefault('WS', []).append(f)
        elif j in (2, 3, 4, 5) and xm > 3.52: regions.setdefault('RG', []).append(f)
        elif side and 1.50 < xm < 2.63: regions.setdefault('SW1' + side, []).append(f)
        elif side and 2.69 < xm < 3.42: regions.setdefault('SW2' + side, []).append(f)
        elif side and 3.47 < xm < 3.80: regions.setdefault('SW3' + side, []).append(f)
        elif side and (2.63 < xm < 2.69 or 3.42 < xm < 3.47): f.material_index = TRIM
bm.faces.new(rings[0]); bm.faces.new(rings[-1])
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
for key, fs in regions.items():
    wide = key in ('WS', 'RG')
    inset(bm, fs, .045 if wide else .020, 0, PAINT)       # body-colour pillar / header band
    inset(bm, fs, .018 if wide else .016, -.012, BLACK)   # black gasket, glass sits inset in it
    for f in fs: f.material_index = GLASS
finish(obj_from_bm('Greenhouse', bm))

# ---------------------------------------------------------------- arch lips
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
side_strip([(1.47, .31), (1.47, .985)], SW, SEAM)                       # front door, leading edge
side_strip([(2.655, .31), (2.655, .985)], SW, SEAM)                     # B pillar
side_strip([(3.73, 1.0), (3.72, .85), (3.63, .745), (3.49, .635), (3.41, .52), (3.36, .40), (3.34, .31)], SW, SEAM)
side_strip([(1.47, .31), (3.34, .31)], SW, SEAM)                        # door bottoms
side_strip([(.05, .585), (.56, .585)], SW, SEAM)                        # front bumper joint
side_strip([(4.24, .62), (4.77, .62)], SW, SEAM)                        # rear bumper joint
side_strip([(4.02, .80), (4.16, .80), (4.16, .92), (4.02, .92), (4.02, .80)], .008, SEAM, sides=(1,))  # fuel flap

for s in (-1, 1):
    zm = .565
    for xa, xb in ((1.53, 2.59), (2.72, 3.37)):
        box('Moulding', (s * (.90 + .006), Y((xa + xb) / 2), zm), (.04, xb - xa, .05), PAINT, .014)
    for xh in (2.41, 3.45):
        w = side_w(xh, .86)
        box('HandleCup', (s * (w + .001), Y(xh), .86), (.012, .24, .075), SEAM, 0)
        box('Handle', (s * (w + .012), Y(xh), .865), (.03, .20, .04), TRIM, .012)
    # mirror: black sail + stalk, body-colour shell, dark glass facing back
    box('MirrorSail', (s * .838, Y(1.66), 1.045), (.03, .20, .085), BLACK, .008)
    box('MirrorStalk', (s * .89, Y(1.70), 1.04), (.10, .06, .045), BLACK, .01)
    box('Mirror', (s * 1.005, Y(1.71), 1.075), (.20, .10, .135), PAINT, .03, rot=(0, 0, s * 0.18), seg=3)
    box('MirrorGlass', (s * 1.012, Y(1.71) + .05, 1.075), (.16, .012, .10), GLASS, 0, rot=(0, 0, s * 0.18))

# ---------------------------------------------------------------- front and rear details
def slant(x):  # point on the grille face (centre line) at distance x
    return tab(TOP, x) + tab(CROWN, x)
for k in range(3):
    x = .070 + k * .0145
    ang = math.atan2(.80 + .03 - .645, .11 - .06)
    box('GrilleBar', (0, Y(x) - .004, slant(x) - .008), (.80, .014, .022), TRIM, .004, rot=(-(pi / 2 - ang), 0, 0))
box('Intake', (0, Y(0) + .012, .36), (.92, .05, .11), BLACK, .012)
box('IntakeBar', (0, Y(0) + .0, .36), (.90, .03, .014), TRIM, 0)
for s in (-1, 1):
    box('Fog', (s * .66, Y(0) + .03, .43), (.15, .07, .08), BLACK, .012, rot=(0, 0, s * -0.25))
box('PlateRear', (0, Y(4.80) + .004, .50), (.48, .012, .12), LAMP, .004)
box('TrunkHandle', (0, Y(4.765) + .012, .70), (.50, .02, .03), TRIM, .006)
box('TrunkSeam', (0, Y(4.44), 1.091), (.90, .012, .008), SEAM, 0)
cyl('Exhaust', (-.48, Y(4.74), .275), .032, .14, 'Y', HUB, 12)
cyl('ExhaustBore', (-.48, Y(4.812), .275), .024, .004, 'Y', BLACK, 12)

# ---------------------------------------------------------------- interior (only seen if glass is made clear)
for s in (-1, 1):
    box('SeatBack', (s * .40, Y(2.42), 1.03), (.48, .13, .50), TRIM, .03, rot=(-.22, 0, 0))
    box('Headrest', (s * .40, Y(2.49), 1.33), (.26, .09, .15), TRIM, .03)
    box('RearHeadrest', (s * .42, Y(3.52), 1.30), (.24, .09, .13), TRIM, .03)
box('RearBench', (0, Y(3.45), 1.03), (1.36, .13, .46), TRIM, .03, rot=(-.25, 0, 0))
box('Dash', (0, Y(1.68), 1.03), (1.50, .34, .12), TRIM, .03)
cyl('SteeringWheel', (-.40, Y(1.93), 1.09), .18, .028, 'Y', BLACK, 20, rot=(pi / 2 - .45, 0, 0))
cyl('SteeringColumn', (-.40, Y(1.83), 1.05), .03, .22, 'Y', BLACK, 8, rot=(pi / 2 - .45, 0, 0))

# ---------------------------------------------------------------- wheels
def hub(cx, cy, cz, s):
    """Hubcap with six recessed slots and a centre cap, axis pointing outward (s = +1 / -1)."""
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
    cyl('Axle', (0, Y(wx), WHEEL_Z), .05, 1.3, 'X', BLACK, 8)

# ---------------------------------------------------------------- weld details, merge everything into one mesh
bm = bmesh.new()
for vs, mi, hint in SOUP:
    f = bm.faces.new([bm.verts.new(v) for v in vs]); f.material_index = mi
    f.normal_update()
    if f.normal.dot(hint) < 0: f.normal_flip()
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
finish(obj_from_bm('Details', bm))

bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
bm = bmesh.new()
for o in parts:
    ev = o.evaluated_get(dg); me = ev.to_mesh()
    me.transform(o.matrix_world)
    bm.from_mesh(me); ev.to_mesh_clear()
for o in parts: bpy.data.objects.remove(o)
mesh = bpy.data.meshes.new(NAME + '_Mesh'); bm.to_mesh(mesh); bm.free()
used = sorted({p.material_index for p in mesh.polygons})
for i in used: mesh.materials.append(MATLIST[i])
remap = {old: new for new, old in enumerate(used)}
for p in mesh.polygons: p.material_index = remap[p.material_index]
mesh.polygons.foreach_set('use_smooth', [True] * len(mesh.polygons))
mesh.set_sharp_from_angle(angle=math.radians(22))
car = bpy.data.objects.new(NAME + '_Mesh', mesh); scene.collection.objects.link(car)
tris = sum(len(p.vertices) - 2 for p in mesh.polygons)
xs = [v.co.x for v in mesh.vertices]; ys = [v.co.y for v in mesh.vertices]; zs = [v.co.z for v in mesh.vertices]
print(f'[{NAME}] triangles {tris}, materials {len(mesh.materials)}, size {max(xs)-min(xs):.2f} x {max(ys)-min(ys):.2f} x {max(zs)-min(zs):.2f} m, min z {min(zs):.3f}')

root = bpy.data.objects.new(NAME, None); scene.collection.objects.link(root); car.parent = root
seat = bpy.data.objects.new('Seat', None); seat.location = (-0.40, Y(2.25), 0.55)
scene.collection.objects.link(seat); seat.parent = root
for o in scene.objects: o.select_set(False)
for o in (root, car, seat): o.select_set(True)
bpy.ops.export_scene.fbx(filepath=f'{OUT}/{NAME}.fbx', use_selection=True, apply_unit_scale=True,
                         apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)

# ---------------------------------------------------------------- previews
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
sun((-3, -5, 8), 2.0); sun((6, -2, 3), 0.7)
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x, scene.render.resolution_y = 1672, 941
scene.view_settings.view_transform = 'Standard'
try: scene.eevee.taa_render_samples = 32
except Exception: pass
cam_data = bpy.data.cameras.new('Cam'); cam = bpy.data.objects.new('Cam', cam_data)
scene.collection.objects.link(cam); scene.camera = cam

def shoot(name, loc, target, lens=50, ortho=None):
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    if ortho: cam_data.type = 'ORTHO'; cam_data.ortho_scale = ortho
    else: cam_data.type = 'PERSP'; cam_data.lens = lens
    scene.render.filepath = f'{OUT}/{name}.png'; bpy.ops.render.render(write_still=True)

shoot('render-34', (3.95, -5.55, 1.75), (-0.05, -0.3, 0.66), 47)
shoot('render-side', (14, 0, 0.89), (0, 0, 0.89), ortho=1672 / 337)

# ---------------------------------------------------------------- compare.jpg (reference left, render right)
def px(path):
    im = bpy.data.images.load(path); w, h = im.size
    a = np.empty(w * h * 4, np.float32); im.pixels.foreach_get(a)
    return a.reshape(h, w, 4)[:941, :1672]
try:
    rows = [np.hstack([px(f'{REF}/ref-{v}.png'), px(f'{OUT}/render-{v}.png')]) for v in ('side', '34')]
    grid = np.vstack(rows); grid[..., 3] = 1
    h, w = grid.shape[:2]
    out = bpy.data.images.new('compare', w, h); out.pixels.foreach_set(grid.ravel())
    out.filepath_raw = f'{OUT}/compare.jpg'; out.file_format = 'JPEG'; out.save()
except Exception as e:
    print('[compare] failed:', e)

# Rowboat: wooden lapstrake rowing boat, two thwarts, oars shipped in their rowlocks. Previs library v3. Own design.
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_rowboat.py -- <out dir>
# 1 unit = 1 m, bow toward -Y, up +Z, origin at the keel centre (bottom of the keel, middle of the length).
import bpy, sys, math, bmesh, os
from mathutils import Vector

OUT = sys.argv[sys.argv.index('--') + 1]
NAME = 'Rowboat'
L = 3.6

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ---------------------------------------------------------------- materials (5)
MATS = []
def mat(name, rgb, rough=0.75, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*rgb, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    m.diffuse_color = (*rgb, 1)
    MATS.append(m)
    return m

WOOD = mat('Wood', (0.200, 0.068, 0.022))           # hull planking outside
WOOD_IN = mat('WoodInner', (0.165, 0.055, 0.018))   # inside of the planking, floorboards
WOOD_D = mat('WoodDark', (0.105, 0.034, 0.012))     # keel, frames, risers, seams
WOOD_L = mat('WoodLight', (0.520, 0.215, 0.070))    # gunwale cap, thwarts, transom cap, oars
STEEL = mat('Steel', (0.085, 0.090, 0.100), 0.6, 0.3)   # rowlocks and their plates (dark iron)

# ---------------------------------------------------------------- hull lines
def B(s):        # half beam at the sheer
    if s <= 0.55:
        return max(0.012, 0.62 * math.sin(math.pi / 2 * s / 0.55) ** 0.72)
    return 0.62 - 0.20 * ((s - 0.55) / 0.45) ** 2

def ZS(s):       # sheer height
    if s < 0.5:
        return 0.395 + 0.105 * ((0.5 - s) / 0.5) ** 2
    return 0.395 + 0.055 * ((s - 0.5) / 0.5) ** 2

def ZK(s):       # hull bottom at the centreline (keel strip below it)
    return 0.05 + 0.40 * max(0.0, (0.24 - s) / 0.24) ** 1.7 + 0.09 * max(0.0, (s - 0.70) / 0.30) ** 2

def PX(s):       # section fullness: round bilge amidships, V towards the bow
    return 0.62 + 0.38 * max(0.0, (0.35 - s) / 0.35)

def Ys(s):
    return -L / 2 + L * s

def sec(s, u):
    """point on the outer section at girth fraction u (0 keel, 1 sheer), right side (x >= 0)"""
    th = u * math.pi / 2
    x = B(s) * math.sin(th) ** PX(s)
    z = ZK(s) + (ZS(s) - ZK(s)) * (1 - math.cos(th)) ** 1.05
    return x, z

def inner_x(s, z, inset=0.025):
    """half width of the inside of the hull at height z (bisection along the girth)"""
    lo, hi = 0.0, 1.0
    for _ in range(30):
        m = (lo + hi) / 2
        if sec(s, m)[1] < z: lo = m
        else: hi = m
    return max(0.0, sec(s, lo)[0] - inset)

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

def cyl(name, loc, r, depth, axis, m, verts=16, bv=0.0, segs=1):
    rot = {'X': (0, math.pi / 2, 0), 'Y': (math.pi / 2, 0, 0), 'Z': (0, 0, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    o = bpy.context.active_object; o.name = name
    bpy.ops.object.transform_apply(location=False, rotation=True)
    if bv: bevel(o, bv, segs)
    return keep(o, m)

def pipe(name, pts, r, m, res=1):
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '3D'
    cu.bevel_depth = r; cu.bevel_resolution = res; cu.use_fill_caps = True
    sp = cu.splines.new('POLY'); sp.points.add(len(pts) - 1)
    for p, q in zip(sp.points, pts): p.co = (*q, 1)
    co = bpy.data.objects.new(name, cu); scene.collection.objects.link(co)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(co.evaluated_get(dg))
    bpy.data.objects.remove(co); bpy.data.curves.remove(cu)
    o = bpy.data.objects.new(name, me); scene.collection.objects.link(o)
    return keep(o, m)

def sweep(name, pts, axis, w, h, m, soft=0.0, off=(0.0, 0.0)):
    """rectangular bar along a polyline; the rectangle spans `axis` (w) and tangent x axis (h)"""
    pts = [Vector(p) for p in pts]; A = Vector(axis).normalized()
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    rings = []
    for i, p in enumerate(pts):
        t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        a = (A - t * A.dot(t)).normalized(); b = t.cross(a).normalized()
        c = p + a * off[0] + b * off[1]
        rings.append([bm.verts.new(c + a * (sa * w / 2) + b * (sb * h / 2))
                      for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    for i in range(len(rings) - 1):
        for k in range(4):
            bm.faces.new([rings[i][k], rings[i][(k + 1) % 4], rings[i + 1][(k + 1) % 4], rings[i + 1][k]])
    bm.faces.new(rings[0]); bm.faces.new(list(reversed(rings[-1])))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); scene.collection.objects.link(o)
    if soft: bevel(o, soft, 1, 40)
    return keep(o, m)

# ---------------------------------------------------------------- hull shell (lapstrake) with solidify
NS = 30                       # stations bow -> stern
STRAKES, PER = 5, 3           # planks per side, girth samples per plank
LAP = 0.018                   # how far each plank's lower edge stands proud of the one above it
S_LIST = [0.012 + (1.0 - 0.012) * (i / (NS - 1)) ** 1.0 for i in range(NS)]

def section_pts(s):
    """right half outer section with the lap steps, keel -> sheer: list of (x, z)"""
    out = []
    for k in range(STRAKES):
        for j in range(PER + 1):
            u = (k + j / PER) / STRAKES
            x, z = sec(s, u)
            x2, z2 = sec(s, min(1.0, u + 0.01)); x1, z1 = sec(s, max(0.0, u - 0.01))
            tx, tz = x2 - x1, z2 - z1; n = math.hypot(tx, tz) or 1
            nx, nz = tz / n, -tx / n                     # outward normal (right side)
            lap = LAP * (1 - j / PER) if k > 0 else 0.0  # each plank laps over the one below at its lower edge
            out.append((x + nx * lap, z + nz * lap))
    return out

me = bpy.data.meshes.new('Hull'); bm = bmesh.new()
rows = []
for s in S_LIST:
    half = section_pts(s)
    full = [(-x, z) for x, z in reversed(half)] + half[1:]
    rows.append([bm.verts.new((x, Ys(s), z)) for x, z in full])
for i in range(NS - 1):
    A, Bv = rows[i], rows[i + 1]
    for k in range(len(A) - 1):
        bm.faces.new([A[k], A[k + 1], Bv[k + 1], Bv[k]])
bm.faces.new(rows[-1])        # transom
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
bm.to_mesh(me); bm.free()
hull = bpy.data.objects.new('Hull', me); scene.collection.objects.link(hull)
hull.data.materials.append(WOOD); hull.data.materials.append(WOOD_IN)
sol = hull.modifiers.new('sol', 'SOLIDIFY'); sol.thickness = 0.022; sol.offset = -1
sol.material_offset = 1; sol.material_offset_rim = 1; sol.use_even_offset = True
bpy.context.view_layer.objects.active = hull
bpy.ops.object.modifier_apply(modifier='sol')
# make sure "outside" faces really face outward: flip the material on faces whose normal points to the centreline
hm = hull.data
idx = [0] * len(hm.polygons); hm.polygons.foreach_get('material_index', idx)
hmid = [MATS.index(WOOD) if i == 0 else MATS.index(WOOD_IN) for i in idx]
hull['mid'] = -1; hull['mids'] = hmid
parts.append(hull)
FIRST = hull

# the bow stem, keel strip, outer transom frame
stem_pts = [(0, Ys(0.0) - 0.012, ZS(0.0) + 0.07), (0, Ys(0.0) - 0.012, ZS(0.0) - 0.02)]
stem_pts += [(0, Ys(s) - 0.012, ZK(s) - 0.024) for s in [0.012 + 0.11 * k / 8 for k in range(9)]]
sweep('Stem', stem_pts, (1, 0, 0), 0.07, 0.07, WOOD_L, soft=0.01)
keel = [(0, Ys(s), ZK(s) - 0.026) for s in [0.10 + (0.995 - 0.10) * k / 22 for k in range(23)]]
sweep('Keel', keel, (1, 0, 0), 0.06, 0.052, WOOD_D, soft=0.008)

# gunwale cap (light) and rubbing strake (dark) along the sheer, both sides
GS = [0.006 + (0.995 - 0.006) * k / 26 for k in range(27)]
for sd in (-1, 1):
    cap = [(sd * (B(s) - 0.005), Ys(s), ZS(s) + 0.012) for s in GS]
    sweep('Gunwale', cap, (sd, 0, 0), 0.075, 0.035, WOOD_L, soft=0.008)
    rub = [(sd * (B(s) + 0.012), Ys(s), ZS(s) - 0.045) for s in GS[1:]]
    sweep('Rubbing', rub, (sd, 0, 0), 0.03, 0.035, WOOD_D, soft=0.006)
# transom: outer cap board and quarter knees
ST = S_LIST[-1]
box('TransomCap', (0, Ys(ST) - 0.01, ZS(ST) + 0.012), (2 * B(ST) + 0.04, 0.07, 0.035), WOOD_L, 0.008, segs=1)
for sd in (-1, 1):
    box('TransomPost', (sd * (B(ST) - 0.035), Ys(ST) - 0.005, ZS(ST) - 0.03),
        (0.06, 0.07, 0.22), WOOD_L, 0.01, segs=1)
box('TransomKnee', (0, Ys(ST) - 0.06, (ZS(ST) + ZK(ST)) / 2 - 0.03), (0.06, 0.10, 0.28), WOOD_D, 0.008, segs=1)
box('BowBreasthook', (0, Ys(0.04), ZS(0.04) - 0.02), (0.10, 0.18, 0.03), WOOD_L, 0.006, segs=1)

# dark seam lines along the plank laps, outside
for k in range(1, STRAKES):
    for sd in (-1, 1):
        pts = []
        for s in S_LIST[1:]:
            u = k / STRAKES
            x, z = sec(s, u)
            x2, z2 = sec(s, min(1, u + 0.01)); x1, z1 = sec(s, max(0, u - 0.01))
            tx, tz = x2 - x1, z2 - z1; n = math.hypot(tx, tz)
            nx, nz = tz / n, -tx / n
            pts.append((sd * (x + nx * (LAP + 0.001)), Ys(s), z + nz * (LAP + 0.001)))
        sweep('LapSeam', pts, (0, 0, 1), 0.010, 0.006, WOOD_D)

# frames (ribs) inside, risers, floorboards
for s in [0.16 + k * 0.095 for k in range(9)]:
    for sd in (-1, 1):
        pts = []
        for k in range(9):
            u = 0.08 + 0.84 * k / 8
            x, z = sec(s, u)
            x2, z2 = sec(s, min(1, u + 0.01)); x1, z1 = sec(s, max(0, u - 0.01))
            tx, tz = x2 - x1, z2 - z1; n = math.hypot(tx, tz)
            nx, nz = tz / n, -tx / n
            pts.append((sd * (x - nx * 0.034), Ys(s), z - nz * 0.034))
        sweep('Frame', pts, (0, 1, 0), 0.04, 0.022, WOOD_D)
Z_T = 0.30                           # thwart top
RS = [0.22 + (0.92 - 0.22) * k / 14 for k in range(15)]
for sd in (-1, 1):
    riser = [(sd * (inner_x(s, Z_T - 0.05, 0.035) - 0.005), Ys(s), Z_T - 0.055) for s in RS]
    sweep('Riser', riser, (0, 0, 1), 0.05, 0.03, WOOD_D)
ZF = 0.105
for k in range(5):
    x = -0.22 + k * 0.11
    span = [s for s in [0.12 + 0.01 * i for i in range(86)] if inner_x(s, ZF + 0.012, 0.03) > abs(x) + 0.055]
    if len(span) < 2: continue
    s0, s1 = span[0], span[-1]
    box('Floorboard', (x, (Ys(s0) + Ys(s1)) / 2, ZF), (0.10, Ys(s1) - Ys(s0), 0.018), WOOD_IN, 0.004, segs=1)
for s in (0.30, 0.55, 0.80):
    box('FloorBatten', (0, Ys(s), ZF - 0.016), (0.52, 0.04, 0.014), WOOD_D)

# thwarts with centre posts
THWARTS = (0.45, 0.76)
for s in THWARTS:
    w = 2 * inner_x(s, Z_T - 0.02, 0.012)
    box('Thwart', (0, Ys(s), Z_T - 0.0175), (w, 0.24, 0.035), WOOD_L, 0.008, segs=2)
    box('ThwartPost', (0, Ys(s), (ZF + Z_T) / 2 - 0.01), (0.05, 0.05, Z_T - ZF - 0.04), WOOD_D, 0.005, segs=1)
    for sd in (-1, 1):   # small knees between thwart and hull side
        xi = inner_x(s, Z_T + 0.05, 0.03)
        box('Knee', (sd * (xi - 0.03), Ys(s), Z_T + 0.035), (0.05, 0.05, 0.07), WOOD_D, 0.005, segs=1)

# rowlocks (aft of the middle thwart) and the shipped oars resting in them
S_RL = 0.555
for sd in (-1, 1):
    xr, zr = B(S_RL) - 0.005, ZS(S_RL) + 0.03
    yr = Ys(S_RL)
    box('LockPlate', (sd * xr, yr, zr), (0.09, 0.16, 0.012), STEEL, 0.004, segs=1)
    box('LockBlock', (sd * (xr + 0.035), yr, zr - 0.05), (0.025, 0.12, 0.10), STEEL, 0.004, segs=1)
    cyl('LockStem', (sd * xr, yr, zr + 0.025), 0.016, 0.05, 'Z', STEEL, 8)
    for e in (-1, 1):   # U-shaped horns
        box('LockHorn', (sd * (xr + e * 0.03), yr, zr + 0.085), (0.016, 0.03, 0.08), STEEL, 0.004, segs=1)
    box('LockBase', (sd * xr, yr, zr + 0.048), (0.08, 0.03, 0.02), STEEL, 0.004, segs=1)

def oar(sd):
    """oar shipped fore-and-aft: loom in the rowlock, blade resting on the stern quarter, grip forward"""
    xr, zr, yr = B(S_RL) - 0.005, ZS(S_RL) + 0.075, Ys(S_RL)
    a = Vector((sd * xr, yr, zr))                       # point on the loom inside the rowlock
    tip_s = 0.985
    tip = Vector((sd * (B(S_RL) - 0.085), Ys(tip_s), ZS(tip_s) + 0.06))
    d = (tip - a).normalized()
    grip = a - d * 0.72
    bstart = tip - d * 0.56
    side = Vector((0, 0, 1)).cross(d).normalized()
    pipe('OarGrip', [tuple(grip), tuple(grip + d * 0.13)], 0.019, WOOD_L, res=1)
    pipe('OarLoom', [tuple(grip + d * 0.12), tuple(a - d * 0.25)], 0.026, WOOD_L, res=1)
    pipe('OarShaft', [tuple(a - d * 0.26), tuple(bstart + d * 0.05)], 0.022, WOOD_L, res=1)
    pipe('OarCollar', [tuple(a - d * 0.13), tuple(a + d * 0.13)], 0.029, WOOD_D, res=1)
    # flat blade, widening from the shaft to a rounded tip
    outline = [(0.0, 0.022), (0.10, 0.03), (0.20, 0.07), (0.44, 0.078), (0.52, 0.07), (0.555, 0.045), (0.56, 0.0)]
    outline = outline + [(u, -v) for u, v in reversed(outline[:-1])]
    me = bpy.data.meshes.new('Blade'); bm = bmesh.new()
    top = [bm.verts.new(bstart + d * u + side * v + Vector((0, 0, 0.011))) for u, v in outline]
    bot = [bm.verts.new(bstart + d * u + side * v - Vector((0, 0, 0.011))) for u, v in outline]
    bm.faces.new(top); bm.faces.new(list(reversed(bot)))
    n = len(outline)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new([top[i], top[j], bot[j], bot[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new('Blade', me); scene.collection.objects.link(o)
    bevel(o, 0.005, 1, 40)
    keep(o, WOOD_L)
for sd in (-1, 1):
    oar(sd)

# ---------------------------------------------------------------- finish: apply, join, per-face materials
for o in list(parts):
    bpy.context.view_layer.objects.active = o
    for md in list(o.modifiers):
        bpy.ops.object.modifier_apply(modifier=md.name)
    me = o.data
    at = me.attributes.new('mid', 'INT', 'FACE')
    vals = list(o['mids']) if o['mid'] < 0 else [o['mid']] * len(me.polygons)
    at.data.foreach_set('value', vals)
from collections import Counter
cnt = Counter()
for o in parts: cnt[o.name.split('.')[0]] += sum(len(p.vertices) - 2 for p in o.data.polygons)
print('[tris]', cnt.most_common(12))
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
      f'size {mx.x - mn.x:.2f} x {mx.y - mn.y:.2f} x {mx.z - mn.z:.2f} m, y {mn.y:.2f}..{mx.y:.2f}, z {mn.z:.3f}')

root = bpy.data.objects.new(NAME, None); scene.collection.objects.link(root); mdl.parent = root
seatE = bpy.data.objects.new('Seat', None); seatE.location = (0, Ys(THWARTS[0]), Z_T)
scene.collection.objects.link(seatE); seatE.parent = root
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

# elevated stern quarter (transom near, bow away to the right), like the reference
sun.rotation_euler = (math.radians(35), 0, math.radians(-150))
shoot('render-34', (-2.9, 3.45, 2.75), (0.0, -0.1, 0.22), 45)
# side, slightly from above so the thwarts read, bow on the left
sun.rotation_euler = (math.radians(35), 0, math.radians(60))
el = math.radians(14)
shoot('render-side', (12 * math.cos(el), 0.0, 0.25 + 12 * math.sin(el)), (0, 0.0, 0.25), ortho=3.95)

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

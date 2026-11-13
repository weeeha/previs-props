# Single-car detached garage (own design, CC0), previs base library, buildings (Opus).
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_garage.py -- <out dir>
# 1 unit = 1 m, front (roll-up door, gable end) toward -Y, up +Z, origin on the ground at the centre of the footprint.
# Exterior only. Built to ref-34.png / ref-front.png: lap siding as tapered boards, cream trim, four-by-four panelled
# roll-up door, panelled side door on the right wall, pitched shingle roof with staggered courses.
import bpy, bmesh, sys, math
from mathutils import Vector, Matrix

OUT = sys.argv[sys.argv.index('--') + 1]
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

parts = []
def new_obj(name, me):
    o = bpy.data.objects.new(name, me); scene.collection.objects.link(o)
    for m in ORDER: o.data.materials.append(m)
    parts.append(o); return o

def set_all(o, idx):
    for p in o.data.polygons: p.material_index = idx

def box(name, lo, hi, idx, bevel=0.0, segs=2, M=None):
    c = [(lo[i] + hi[i]) / 2 for i in range(3)]; s = [hi[i] - lo[i] for i in range(3)]
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((*s, 1)))
    if bevel:
        bmesh.ops.bevel(bm, geom=bm.edges[:] + bm.verts[:], offset=min(bevel, min(s) * 0.45), segments=segs,
                        affect='EDGES', profile=0.5)
    if M is not None: bmesh.ops.transform(bm, matrix=M, verts=bm.verts)
    bm.to_mesh(me); bm.free()
    o = new_obj(name, me); set_all(o, idx); return o

def hull(name, pts, idx, M=None):
    """Convex solid from points (gables, sloped awnings, roof planes)."""
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    for p in pts: bm.verts.new(p)
    bmesh.ops.convex_hull(bm, input=bm.verts[:])
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(1), verts=bm.verts[:], edges=bm.edges[:])
    if M is not None: bmesh.ops.transform(bm, matrix=M, verts=bm.verts)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    o = new_obj(name, me); set_all(o, idx); return o

def cyl(name, r, z0, z1, loc, idx, n=16, M=None):
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=n, radius1=r, radius2=r, depth=z1 - z0,
                          matrix=Matrix.Translation((loc[0], loc[1], (z0 + z1) / 2)))
    if M is not None: bmesh.ops.transform(bm, matrix=M, verts=bm.verts)
    bm.to_mesh(me); bm.free()
    o = new_obj(name, me); set_all(o, idx); return o

def cut(target, cutters):
    """One EXACT boolean difference with all cutters joined into one object."""
    bm = bmesh.new()
    for c in cutters:
        bm.from_mesh(c.data); parts.remove(c); bpy.data.objects.remove(c)
    me = bpy.data.meshes.new('Cutter'); bm.to_mesh(me); bm.free()
    for m in ORDER: me.materials.append(m)   # same slots as the target, so the boolean adds none
    co = bpy.data.objects.new('Cutter', me); scene.collection.objects.link(co)
    m = target.modifiers.new('b', 'BOOLEAN'); m.operation = 'DIFFERENCE'; m.object = co; m.solver = 'EXACT'
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier='b')
    bpy.data.objects.remove(co)
    while len(target.data.materials) > len(ORDER): target.data.materials.pop()

# facade frames: local x along the wall (left to right seen from outside), local y into the wall, z up
def face_M(side, d):
    """side: 'F' front (-Y), 'B' back, 'L' left (-X), 'R' right (+X); d = distance of that wall plane from origin."""
    if side == 'F': return Matrix.Translation((0, -d, 0))
    if side == 'B': return Matrix.Translation((0, d, 0)) @ Matrix.Rotation(math.pi, 4, 'Z')
    if side == 'R': return Matrix.Translation((d, 0, 0)) @ Matrix.Rotation(math.pi / 2, 4, 'Z')
    if side == 'L': return Matrix.Translation((-d, 0, 0)) @ Matrix.Rotation(-math.pi / 2, 4, 'Z')

def finish(name, root_name, seat=None):
    for o in scene.objects: o.select_set(False)
    for o in parts: o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    mesh = parts[0]; mesh.name = f'{root_name}_Mesh'
    assert [m.name for m in mesh.data.materials] == [m.name for m in ORDER], 'material slots shuffled'
    bm = bmesh.new(); bm.from_mesh(mesh.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0003)
    bm.to_mesh(mesh.data); bm.free()
    with bpy.context.temp_override(active_object=mesh, object=mesh, selected_objects=[mesh], selected_editable_objects=[mesh]):
        bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
    tris = sum(len(p.vertices) - 2 for p in mesh.data.polygons)
    used = sorted({p.material_index for p in mesh.data.polygons})
    bpy.context.view_layer.update()
    ws = [mesh.matrix_world @ Vector(c) for c in mesh.bound_box]
    lo = [min(v[i] for v in ws) for i in range(3)]; hi = [max(v[i] for v in ws) for i in range(3)]
    print(f'[{name}] triangles {tris}, materials {len(used)} {[ORDER[i].name for i in used]}, '
          f'size {hi[0]-lo[0]:.2f} x {hi[1]-lo[1]:.2f} x {hi[2]-lo[2]:.2f}, bounds {[round(v,2) for v in lo]} {[round(v,2) for v in hi]}')
    root = bpy.data.objects.new(root_name, None); scene.collection.objects.link(root); mesh.parent = root
    for o in scene.objects: o.select_set(False)
    root.select_set(True); mesh.select_set(True)
    bpy.ops.export_scene.fbx(filepath=f'{OUT}/{root_name}.fbx', use_selection=True, apply_unit_scale=True,
                             apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)
    return mesh

def studio():
    world = bpy.data.worlds.new('W'); scene.world = world; world.use_nodes = True
    wn = world.node_tree.nodes; wl = world.node_tree.links
    wn['Background'].inputs['Color'].default_value = (0.62, 0.62, 0.64, 1)
    wn['Background'].inputs['Strength'].default_value = 0.55
    bg_cam = wn.new('ShaderNodeBackground'); bg_cam.inputs['Color'].default_value = (0.68, 0.68, 0.69, 1)
    lp = wn.new('ShaderNodeLightPath'); mix = wn.new('ShaderNodeMixShader')
    wl.new(lp.outputs['Is Camera Ray'], mix.inputs['Fac']); wl.new(wn['Background'].outputs[0], mix.inputs[1])
    wl.new(bg_cam.outputs[0], mix.inputs[2]); wl.new(mix.outputs[0], wn['World Output'].inputs['Surface'])
    gme = bpy.data.meshes.new('Ground'); gbm = bmesh.new()
    bmesh.ops.create_grid(gbm, x_segments=1, y_segments=1, size=80); gbm.to_mesh(gme); gbm.free()
    ground = bpy.data.objects.new('Ground', gme); scene.collection.objects.link(ground)
    gm = bpy.data.materials.new('GroundM'); gm.use_nodes = True
    gm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.42, 0.42, 0.43, 1)
    gm.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 1.0
    gme.materials.append(gm); ground.visible_camera = False
    sun_d = bpy.data.lights.new('Sun', 'SUN'); sun_d.energy = 3.4; sun_d.angle = math.radians(12)
    sun = bpy.data.objects.new('Sun', sun_d); scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(50), 0, math.radians(32))
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x, scene.render.resolution_y = 1672, 941
    scene.view_settings.view_transform = 'Standard'

def shoot(name, loc, target, lens=50, ortho=None):
    cam = scene.camera
    if cam is None:
        cam_d = bpy.data.cameras.new('Cam'); cam = bpy.data.objects.new('Cam', cam_d)
        scene.collection.objects.link(cam); scene.camera = cam
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    if ortho: cam.data.type = 'ORTHO'; cam.data.ortho_scale = ortho
    else: cam.data.type = 'PERSP'; cam.data.lens = lens
    cam.data.clip_end = 300
    scene.render.filepath = f'{OUT}/{name}.png'; bpy.ops.render.render(write_still=True)

def wallM(p, theta_deg):
    """Wall frame at point p: local x along the wall (left to right seen from outside), local y into the wall."""
    return Matrix.Translation(p) @ Matrix.Rotation(math.radians(theta_deg), 4, 'Z')

def window(M, x, z0, w, h, fidx, gidx, cidx, inset=0.14, ft=0.07, mt=0.045, cols=2, rows=2, depth=0.35):
    """Opening (returned cutter, in world space) plus frame members, mullions and dark glass at the reveal."""
    c = box('Cut', (x - w / 2, -0.4, z0), (x + w / 2, inset + depth, z0 + h), cidx, M=M)
    x0, x1, z1 = x - w / 2, x + w / 2, z0 + h
    yf0, yf1 = inset - 0.06, inset + 0.02
    box('FrB', (x0, yf0, z0), (x1, yf1, z0 + ft), fidx, 0.01, 1, M=M)
    box('FrT', (x0, yf0, z1 - ft), (x1, yf1, z1), fidx, 0.01, 1, M=M)
    box('FrL', (x0, yf0, z0), (x0 + ft, yf1, z1), fidx, 0.01, 1, M=M)
    box('FrR', (x1 - ft, yf0, z0), (x1, yf1, z1), fidx, 0.01, 1, M=M)
    for k in range(1, cols):
        xm = x0 + (w * k / cols)
        box('Mul', (xm - mt / 2, yf0 + 0.015, z0), (xm + mt / 2, yf1 - 0.005, z1), fidx, 0.008, 1, M=M)
    for k in range(1, rows):
        zm = z0 + (h * k / rows)
        box('Tra', (x0, yf0 + 0.015, zm - mt / 2), (x1, yf1 - 0.005, zm + mt / 2), fidx, 0.008, 1, M=M)
    box('Glass', (x0, inset, z0), (x1, inset + 0.02, z1), gidx, M=M)
    return c

# ---------------------------------------------------------------- garage
SIDING = mat('Siding', (0.125, 0.185, 0.255), 0.85)
TRIM = mat('Trim', (0.74, 0.67, 0.51), 0.8)
SHING = mat('Shingle', (0.050, 0.050, 0.055), 0.95)
SHING_D = mat('ShingleDark', (0.032, 0.032, 0.036), 0.95)
CONC = mat('Concrete', (0.43, 0.39, 0.32), 0.95)
GLASS = mat('Glass', (0.018, 0.022, 0.028), 0.25)
BLACK = mat('Black', (0.035, 0.035, 0.038), 0.7)

W, D = 4.0, 6.5                  # wall footprint
EAVE = 2.35                      # wall top
PITCH = 0.415                    # rise per metre (about 22.5 degrees)
OH_S, OH_G = 0.30, 0.25          # overhang at the eaves and at the gables
RT = 0.12                        # roof slab thickness (vertical)
APEX = EAVE + W / 2 * PITCH      # gable apex on the wall plane
FND = 0.18                       # foundation top
import random
rng = random.Random(11)

def gable_hw(z):
    return W / 2 if z <= EAVE else max(0.0, W / 2 - (z - EAVE) / PITCH)

body = hull('Body', [(x, y, z) for y in (-D / 2, D / 2) for x, z in ((-W / 2, FND - 0.02), (W / 2, FND - 0.02), (W / 2, EAVE), (0, APEX), (-W / 2, EAVE))],
            SIDING)
box('Foundation', (-W / 2 - 0.05, -D / 2 - 0.05, 0.0), (W / 2 + 0.05, D / 2 + 0.05, FND), CONC, 0.015, 1)

F, B = face_M('F', D / 2), face_M('B', D / 2)
R, L = face_M('R', W / 2), face_M('L', W / 2)
# openings (local x0, x1, z0, z1) per wall
GD = (-1.3, 1.3, 0.0, 2.12)          # roll-up door
SD = (0.6, 1.5, FND, 2.18)          # side door on the right wall (local x runs front to back there)
WL = (-0.5, 0.5, 1.15, 1.95)         # small window on the left wall
WB = (-0.45, 0.45, 1.2, 1.9)         # small window at the back
holes = {'F': [GD], 'R': [SD], 'L': [WL], 'B': [WB]}
frames = {'F': F, 'B': B, 'R': R, 'L': L}

cutters = [box('GDCut', (GD[0], -0.4, GD[2]), (GD[1], 0.35, GD[3]), SIDING, M=F),
           box('SDCut', (SD[0], -0.4, SD[2]), (SD[1], 0.3, SD[3]), SIDING, M=R)]
cutters.append(window(L, 0, WL[2], WL[1] - WL[0], WL[3] - WL[2], TRIM, GLASS, SIDING, inset=0.1, ft=0.06, cols=2, rows=1))
cutters.append(window(B, 0, WB[2], WB[1] - WB[0], WB[3] - WB[2], TRIM, GLASS, SIDING, inset=0.1, ft=0.06, cols=1, rows=2))
cut(body, cutters)

# lap siding: tapered boards, thick at the bottom edge, split around the openings and stopped under the gable trim
BH, BT = 0.2, 0.028
for side, M in frames.items():
    half = W / 2 if side in 'FB' else D / 2
    z = FND
    while True:
        z1 = z + BH
        hw = half if side in 'LR' else gable_hw(z1 + 0.05)
        if side in 'LR' and z1 > EAVE + 0.001: break
        if hw < 0.12: break
        segs = [(-hw + 0.02, hw - 0.02)]
        for h in holes[side]:
            if z1 > h[2] and z < h[3] + 0.16:
                out = []
                for a, b in segs:
                    if b <= h[0] - 0.14 or a >= h[1] + 0.14: out.append((a, b)); continue
                    if a < h[0] - 0.14: out.append((a, h[0] - 0.14))
                    if b > h[1] + 0.14: out.append((h[1] + 0.14, b))
                segs = out
        for a, b in segs:
            if b - a < 0.02: continue
            hull('Board', [(a, 0.0, z1), (b, 0.0, z1), (a, -BT, z + 0.004), (b, -BT, z + 0.004), (a, 0.0, z), (b, 0.0, z),
                           (a, -0.006, z1), (b, -0.006, z1)], SIDING, M=M)
        z = z1

# corner boards and opening trim
for sx in (-1, 1):
    for sy in (-1, 1):
        box('Corner', (sx * W / 2 - 0.07, sy * D / 2 - 0.07, FND), (sx * W / 2 + 0.07, sy * D / 2 + 0.07, EAVE), TRIM, 0.012, 1)
def trim_around(M, h, w=0.14, head=0.18, proud=0.05, sill=False):
    x0, x1, z0, z1 = h
    box('TrimL', (x0 - w, -proud, z0), (x0, 0.0, z1 + head), TRIM, 0.012, 1, M=M)
    box('TrimR', (x1, -proud, z0), (x1 + w, 0.0, z1 + head), TRIM, 0.012, 1, M=M)
    box('TrimH', (x0 - w - 0.03, -proud - 0.01, z1), (x1 + w + 0.03, 0.0, z1 + head), TRIM, 0.012, 1, M=M)
    if sill: box('TrimS', (x0 - w - 0.03, -proud - 0.04, z0 - 0.08), (x1 + w + 0.03, 0.0, z0), TRIM, 0.012, 1, M=M)
trim_around(F, GD, 0.16, 0.2)
trim_around(R, SD, 0.10, 0.12)
trim_around(L, WL, 0.09, 0.1, sill=True)
trim_around(B, WB, 0.09, 0.1, sill=True)

# roll-up door: four sections, four raised panels each, seams between sections
DX0, DX1, DZ1 = GD[0], GD[1], GD[3]
box('GDoor', (DX0, 0.22, 0.0), (DX1, 0.27, DZ1), TRIM, M=F)
NC, NR, G = 4, 4, 0.08
pw = (DX1 - DX0 - (NC + 1) * G) / NC; ph = (DZ1 - (NR + 1) * G) / NR
for r in range(NR):
    for c in range(NC):
        x = DX0 + G + c * (pw + G); z = G + r * (ph + G)
        box('GPanel', (x, 0.19, z), (x + pw, 0.22, z + ph), TRIM, 0.025, 2, M=F)
    if r: box('GSeam', (DX0, 0.214, r * (ph + G) + G / 2 - 0.008), (DX1, 0.222, r * (ph + G) + G / 2 + 0.008), SIDING, M=F)
box('GHandle', (-0.12, 0.16, 0.42), (0.12, 0.19, 0.47), BLACK, 0.008, 1, M=F)
box('Apron', (DX0 - 0.1, -0.6, 0.0), (DX1 + 0.1, 0.22, 0.04), CONC, 0.012, 1, M=F)

# side door: slab with four raised panels, knob, hinges
X0, X1, Z0, Z1 = SD
box('SDoor', (X0 + 0.01, 0.12, Z0), (X1 - 0.01, 0.17, Z1 - 0.01), TRIM, 0.01, 1, M=R)
for zc, hh in ((Z0 + 0.48, 0.62), (Z0 + 1.42, 0.78)):
    for xc in (X0 + 0.24, X1 - 0.24):
        box('SPanel', (xc - 0.16, 0.10, zc - hh / 2), (xc + 0.16, 0.12, zc + hh / 2), TRIM, 0.018, 2, M=R)
cyl('Knob', 0.035, 0.0, 0.07, (0, 0), BLACK, 12, M=R @ Matrix.Translation((X0 + 0.11, 0.10, Z0 + 0.95)) @ Matrix.Rotation(math.pi / 2, 4, 'X'))
for zz in (Z0 + 0.3, Z1 - 0.35):
    box('Hinge', (X1 - 0.04, 0.09, zz), (X1 + 0.01, 0.12, zz + 0.12), BLACK, M=R)
box('SStep', (X0 - 0.15, -0.4, 0.0), (X1 + 0.15, 0.05, FND - 0.02), CONC, 0.015, 1, M=R)

# roof: two slabs, shingle courses with staggered tabs, ridge cap, fascia and barge boards
XE = W / 2 + OH_S
def roof_z(x): return APEX + RT + 0.02 - abs(x) * PITCH      # top surface over the wall-plane apex
YF, YB = -D / 2 - OH_G, D / 2 + OH_G
for s in (-1, 1):
    hull('RoofSlab', [(s * xx, y, z) for y in (YF, YB) for xx, z in ((0, roof_z(0)), (XE, roof_z(XE)), (XE, roof_z(XE) - RT), (0, roof_z(0) - RT))],
         SHING)
    # courses from the eave up to the ridge
    NCOURSE = 9; span = XE - 0.05
    for k in range(NCOURSE):
        xa = XE + 0.02 - k * span / NCOURSE           # lower edge (outer)
        xb = xa - span / NCOURSE - 0.06                # upper edge, overlaps the next course
        xb = max(xb, 0.0)
        y = YF - 0.01; off = rng.uniform(0, 0.5)
        cuts = [YF - 0.01] + [YF + off + 0.62 * j for j in range(1, 20) if YF + off + 0.62 * j < YB - 0.2] + [YB + 0.01]
        for a, b in zip(cuts[:-1], cuts[1:]):
            idx = SHING_D if rng.random() < 0.28 else SHING
            za, zb = roof_z(xa), roof_z(xb)
            hull('Shingle', [(s * xa, a + 0.008, za + 0.002), (s * xa, b - 0.008, za + 0.002),
                             (s * xa, a + 0.008, za + 0.045), (s * xa, b - 0.008, za + 0.045),
                             (s * xb, a + 0.008, zb + 0.002), (s * xb, b - 0.008, zb + 0.002),
                             (s * xb, a + 0.008, zb + 0.012), (s * xb, b - 0.008, zb + 0.012)], idx)
    # fascia board under the eave edge
    box('Fascia', (min(s * XE, s * (XE - 0.04)), YF, roof_z(XE) - RT - 0.12), (max(s * XE, s * (XE - 0.04)), YB, roof_z(XE) - RT + 0.02), TRIM, 0.01, 1)
    # barge boards on both gables
    for yb, sgn in ((YF, -1), (YB, 1)):
        y0, y1 = sorted((yb, yb + sgn * 0.05))
        hull('Barge', [(s * xx, y, z) for y in (y0, y1) for xx, z in
                       ((0, roof_z(0) - RT + 0.02), (XE, roof_z(XE) - RT + 0.02), (XE, roof_z(XE) - RT - 0.20), (0, roof_z(0) - RT - 0.20))], TRIM)
hull('Ridge', [(x, y, z) for y in (YF - 0.02, YB + 0.02) for x, z in ((-0.17, roof_z(0.17) + 0.03), (0.17, roof_z(0.17) + 0.03), (0, roof_z(0) + 0.10),
                                                                  (-0.17, roof_z(0.17) + 0.07), (0.17, roof_z(0.17) + 0.07))], SHING_D)

mesh = finish('garage', 'Garage')
studio()
shoot('render-34', (6.2, -9.6, 3.0), (0.25, -0.7, 1.5), 40)
shoot('render-front', (0, -30, 1.70), (0, 0, 1.70), ortho=6.6)

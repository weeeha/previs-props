# Three-storey brick row house (own design, CC0), previs base library, buildings (Opus).
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_rowhouse.py -- <out dir>
# 1 unit = 1 m, front toward -Y, up +Z, origin on the ground at the centre of the brick box.
# Exterior only: a solid box with the openings cut as pockets; windows and doors are inset frames with dark glass.
# From ref-34.png / ref-front.png, with the brief's six windows (two per storey) instead of the refs' eight.
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

# ---------------------------------------------------------------- rowhouse
BRICK = mat('Brick', (0.40, 0.058, 0.034), 0.9)
BRICK_D = mat('BrickDark', (0.30, 0.042, 0.026), 0.9)
TRIM = mat('Trim', (0.74, 0.67, 0.51), 0.8)
CONC = mat('Concrete', (0.43, 0.39, 0.32), 0.95)
GLASS = mat('Glass', (0.018, 0.022, 0.028), 0.25)
WOOD = mat('Wood', (0.085, 0.040, 0.026), 0.7)
BLACK = mat('Black', (0.035, 0.035, 0.038), 0.7)

W, D = 6.0, 7.4                 # brick box (x, y)
FY = -D / 2                     # front face y
BASE = 1.30                     # stone base top = ground-floor level (stoop height)
TOPB = 10.0                     # top of brick
F = face_M('F', D / 2)

body = box('Body', (-W / 2, -D / 2, BASE - 0.05), (W / 2, D / 2, TOPB), BRICK, 0.02, 2)
box('Base', (-W / 2 - 0.06, -D / 2 - 0.06, 0.0), (W / 2 + 0.06, D / 2 + 0.06, BASE), CONC, 0.03, 2)
box('BaseCap', (-W / 2 - 0.09, -D / 2 - 0.09, BASE - 0.06), (W / 2 + 0.09, D / 2 + 0.09, BASE + 0.02), CONC, 0.02, 2)

cutters = []
# six windows: two per storey, with cream architraves, lintels and sills
WX, WW, WH = 1.75, 1.15, 1.75
for z0 in (1.95, 4.95, 7.85):
    for x in (-WX, WX):
        cutters.append(window(F, x, z0, WW, WH, TRIM, GLASS, BRICK, inset=0.16, ft=0.08))
        box('Arch', (x - WW / 2 - 0.1, -0.03, z0 - 0.02), (x - WW / 2, 0.02, z0 + WH), TRIM, 0.01, 1, M=F)
        box('Arch', (x + WW / 2, -0.03, z0 - 0.02), (x + WW / 2 + 0.1, 0.02, z0 + WH), TRIM, 0.01, 1, M=F)
        box('Lintel', (x - WW / 2 - 0.2, -0.07, z0 + WH), (x + WW / 2 + 0.2, 0.02, z0 + WH + 0.24), TRIM, 0.02, 2, M=F)
        box('LintelCap', (x - WW / 2 - 0.25, -0.11, z0 + WH + 0.24), (x + WW / 2 + 0.25, 0.02, z0 + WH + 0.30), TRIM, 0.015, 1, M=F)
        box('Sill', (x - WW / 2 - 0.16, -0.12, z0 - 0.12), (x + WW / 2 + 0.16, 0.02, z0 + 0.0), TRIM, 0.02, 2, M=F)

# front door: recessed, panelled, with pilasters and an entablature
DW, DH = 1.10, 2.45
cutters.append(box('DoorCut', (-DW / 2, -0.4, BASE), (DW / 2, 0.55, BASE + DH), BRICK, M=F))
box('Door', (-DW / 2 + 0.02, 0.24, BASE), (DW / 2 - 0.02, 0.30, BASE + DH - 0.02), WOOD, 0.01, 1, M=F)
for zc, ph in ((BASE + 0.55, 0.75), (BASE + 1.6, 0.65)):
    for xc in (-0.25, 0.25):
        box('DoorPanel', (xc - 0.17, 0.215, zc - ph / 2), (xc + 0.17, 0.24, zc + ph / 2), WOOD, 0.012, 2, M=F)
cyl('Knob', 0.035, 0.0, 0.08, (0, 0), BLACK, 12,
    M=F @ Matrix.Translation((0.38, 0.24, BASE + 1.05)) @ Matrix.Rotation(math.pi / 2, 4, 'X'))
box('DoorJambL', (-DW / 2, 0.0, BASE), (-DW / 2 + 0.06, 0.3, BASE + DH), TRIM, 0.01, 1, M=F)
box('DoorJambR', (DW / 2 - 0.06, 0.0, BASE), (DW / 2, 0.3, BASE + DH), TRIM, 0.01, 1, M=F)
box('DoorHead', (-DW / 2, 0.0, BASE + DH - 0.06), (DW / 2, 0.3, BASE + DH), TRIM, 0.01, 1, M=F)
for s in (-1, 1):
    xp = s * (DW / 2 + 0.12)
    box('Pilaster', (xp - 0.12, -0.08, BASE), (xp + 0.12, 0.02, BASE + DH + 0.05), TRIM, 0.015, 2, M=F)
    box('PilBase', (xp - 0.15, -0.11, BASE), (xp + 0.15, 0.02, BASE + 0.2), TRIM, 0.015, 1, M=F)
box('Frieze', (-DW / 2 - 0.3, -0.10, BASE + DH + 0.05), (DW / 2 + 0.3, 0.02, BASE + DH + 0.32), TRIM, 0.015, 2, M=F)
box('DoorCornice', (-DW / 2 - 0.4, -0.2, BASE + DH + 0.32), (DW / 2 + 0.4, 0.02, BASE + DH + 0.42), TRIM, 0.02, 2, M=F)

# quoins at the two front corners (front and side faces), alternating long/short blocks
z = BASE + 0.05; k = 0
while z + 0.36 < TOPB - 0.05:
    L = 0.55 if k % 2 == 0 else 0.35
    for s in (-1, 1):
        x_out = s * (W / 2 + 0.03)
        xa, xb = sorted((s * W / 2 - s * L, x_out))
        box('QuoinF', (xa, FY - 0.03, z), (xb, FY + 0.3, z + 0.34), BRICK_D, 0.012, 1)
        box('QuoinS', (min(s * W / 2, x_out) - (0.0 if s > 0 else 0.0), FY - 0.03, z),
            (max(s * W / 2, x_out), FY + (0.55 if k % 2 else 0.35), z + 0.34), BRICK_D, 0.012, 1)
    z += 0.40; k += 1
# string course between ground floor and first floor
box('Band', (-W / 2 - 0.04, FY - 0.05, 4.32), (W / 2 + 0.04, FY + 0.1, 4.44), TRIM, 0.015, 1)

# cornice: frieze band, modillion brackets, projecting slab, dark coping (front and both sides)
box('CorFrieze', (-W / 2 - 0.05, FY - 0.08, TOPB - 0.55), (W / 2 + 0.05, D / 2 - 0.4, TOPB), TRIM, 0.02, 2)
box('CorBed', (-W / 2 - 0.12, FY - 0.15, TOPB - 0.62), (W / 2 + 0.12, D / 2 - 0.4, TOPB - 0.52), TRIM, 0.015, 1)
for k in range(9):
    x = -W / 2 + 0.2 + k * (W - 0.4) / 8
    box('Modillion', (x - 0.09, FY - 0.36, TOPB - 0.25), (x + 0.09, FY, TOPB), TRIM, 0.02, 2)
for s in (-1, 1):
    for k in range(4):
        y = FY + 0.3 + k * 1.05
        box('ModS', (s * W / 2 - (0.0 if s > 0 else 0.36), y - 0.09, TOPB - 0.25),
            (s * W / 2 + (0.36 if s > 0 else 0.0), y + 0.09, TOPB), TRIM, 0.02, 2)
box('CorSlab', (-W / 2 - 0.40, FY - 0.40, TOPB), (W / 2 + 0.40, D / 2 - 0.4, TOPB + 0.22), TRIM, 0.03, 2)
box('Coping', (-W / 2 - 0.44, FY - 0.44, TOPB + 0.22), (W / 2 + 0.44, D / 2 - 0.35, TOPB + 0.34), BLACK, 0.03, 2)
box('RoofBack', (-W / 2, D / 2 - 0.45, TOPB), (W / 2, D / 2 + 0.03, TOPB + 0.30), BRICK, 0.02, 2)
box('RoofCap', (-W / 2 - 0.05, D / 2 - 0.45, TOPB + 0.30), (W / 2 + 0.05, D / 2 + 0.08, TOPB + 0.36), BLACK, 0.015, 1)
box('Hatch', (0.8, 1.5, TOPB + 0.34), (1.7, 2.4, TOPB + 0.62), BLACK, 0.03, 2)
box('Chimney', (-2.6, 2.3, TOPB + 0.34), (-1.7, 3.2, TOPB + 0.95), BRICK, 0.02, 2)
box('ChimneyCap', (-2.68, 2.22, TOPB + 0.95), (-1.62, 3.28, TOPB + 1.03), CONC, 0.015, 1)

# back: plain door and two windows per upper floor
B = face_M('B', D / 2)
cutters.append(box('BackDoorCut', (-1.8 - 0.5, -0.4, BASE), (-1.8 + 0.5, 0.4, BASE + 2.2), BRICK, M=B))
box('BackDoor', (-2.28, 0.18, BASE), (-1.32, 0.24, BASE + 2.18), WOOD, 0.01, 1, M=B)
box('BackStep', (-2.6, -0.9, 0), (-1.0, 0.05, BASE), CONC, 0.02, 2, M=B)
for z0 in (4.95, 7.85):
    for x in (-WX, WX):
        cutters.append(window(B, x, z0, 1.0, 1.55, TRIM, GLASS, BRICK, inset=0.12, ft=0.07))
        box('BSill', (x - 0.6, -0.08, z0 - 0.1), (x + 0.6, 0.02, z0), TRIM, 0.015, 1, M=B)
cut(body, cutters)

# a few proud bricks scattered over the brick faces (front and both sides), clear of the openings
import random
rng = random.Random(7)
holes = [(x - WW / 2 - 0.35, x + WW / 2 + 0.35, z0 - 0.3, z0 + WH + 0.45) for z0 in (1.95, 4.95, 7.85) for x in (-WX, WX)]
holes += [(-DW / 2 - 0.5, DW / 2 + 0.5, 0, BASE + DH + 0.6), (-9, 9, 4.2, 4.55), (-9, 9, TOPB - 0.75, 99)]
placed = 0
while placed < 70:
    side = rng.choice('FFLR'); L = D if side in 'LR' else W
    x = rng.uniform(-L / 2 + 0.75, L / 2 - 0.75); z = BASE + 0.25 + round(rng.uniform(0, TOPB - BASE - 1.2) / 0.1) * 0.1
    if side == 'F' and any(a < x < b and c < z < d for a, b, c, d in holes): continue
    if side in 'LR' and (z > TOPB - 0.75): continue
    w = 0.24 if rng.random() < 0.6 else 0.46
    box('Brick', (x - w / 2, -0.025, z), (x + w / 2, 0.0, z + 0.075), BRICK_D, M=face_M(side, D / 2 if side in 'FB' else W / 2))
    placed += 1

# stoop: stone steps between cheek walls, iron rails on top
STEPS = 7; RISE = BASE / STEPS; RUN = 0.29; LAND = 0.55; SW = 1.7
for i in range(STEPS):
    top = (i + 1) * RISE
    yf = FY - LAND - (STEPS - 1 - i) * RUN
    box('Step', (-SW / 2, yf, 0.0), (SW / 2, FY + 0.05, top), CONC, 0.012, 1)
    box('Nose', (-SW / 2, yf - 0.03, top - 0.05), (SW / 2, yf + 0.05, top), CONC, 0.012, 1)
Y0 = FY - LAND - (STEPS - 1) * RUN - 0.25   # foot of the stoop
for s in (-1, 1):
    xa, xb = s * SW / 2, s * (SW / 2 + 0.36)
    xa, xb = min(xa, xb), max(xa, xb)
    pts = []
    for x in (xa, xb):
        pts += [(x, FY + 0.05, 0), (x, Y0, 0), (x, Y0, 0.55), (x, FY - LAND, BASE + 0.62), (x, FY + 0.05, BASE + 0.62)]
    hull('Cheek', pts, CONC)
    box('CheekCap', (xa - 0.03, FY - LAND - 0.1, BASE + 0.62), (xb + 0.03, FY + 0.05, BASE + 0.70), CONC, 0.015, 1)
    box('Newel', (xa - 0.04, Y0 - 0.04, 0), (xb + 0.04, Y0 + 0.36, 0.78), CONC, 0.02, 2)
    box('NewelCap', (xa - 0.07, Y0 - 0.07, 0.78), (xb + 0.07, Y0 + 0.39, 0.86), CONC, 0.015, 1)
    # iron rail: sloped bar on posts
    xr = (xa + xb) / 2; r = 0.022
    ya, za = Y0 + 0.18, 0.86 + 0.80
    yb, zb = FY - LAND, BASE + 0.70 + 0.80
    rp = []
    for dx in (-r, r):
        for dz in (-r, r):
            rp += [(xr + dx, ya, za + dz), (xr + dx, yb, zb + dz), (xr + dx, FY + 0.02, zb + dz)]
    hull('Rail', rp[0::3] + rp[1::3], BLACK)
    hull('RailTop', rp[1::3] + rp[2::3], BLACK)
    for t in (0.0, 0.35, 0.7, 1.0):
        yy = ya + (yb - ya) * t; zt = za + (zb - za) * t
        zbase = 0.86 + (BASE + 0.70 - 0.86) * t if t < 1 else BASE + 0.70
        box('Baluster', (xr - 0.016, yy - 0.016, zbase - 0.02), (xr + 0.016, yy + 0.016, zt), BLACK)
    box('Baluster', (xr - 0.016, FY - 0.05, BASE + 0.68), (xr + 0.016, FY - 0.02, zb), BLACK)
    yv = Y0 + 0.18
    cyl('Volute', 0.05, 0.86, 0.86 + 0.1, (xr, yv), BLACK, 12)

mesh = finish('rowhouse', 'Rowhouse')
studio()
shoot('render-34', (9.5, -30.0, 9.0), (0.2, -1.3, 5.0), 40)
shoot('render-front', (0, -40, 5.6), (0, 0, 5.6), ortho=20.5)

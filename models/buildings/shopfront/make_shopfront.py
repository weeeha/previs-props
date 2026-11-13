# Single-storey corner shop (own design, CC0), previs base library, buildings (Opus).
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_shopfront.py -- <out dir>
# 1 unit = 1 m, front toward -Y, up +Z, origin on the ground at the centre of the footprint.
# Exterior only. Built to ref-34.png: chamfered front-right corner with a recessed glass door, display windows on the
# front and right faces, scalloped awning, blank sign band (no text), flat roof behind a capped parapet.
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

# ---------------------------------------------------------------- shopfront
BRICK = mat('Brick', (0.40, 0.058, 0.034), 0.9)
TRIM = mat('Trim', (0.74, 0.67, 0.51), 0.8)
GREEN = mat('GreenPaint', (0.040, 0.095, 0.055), 0.6)
CANVAS = mat('Canvas', (0.17, 0.30, 0.15), 0.95)
GLASS = mat('Glass', (0.018, 0.022, 0.028), 0.25)
SLATE = mat('Slate', (0.055, 0.055, 0.060), 0.85)
CONC = mat('Concrete', (0.43, 0.39, 0.32), 0.95)
STEEL = mat('Steel', (0.36, 0.37, 0.38), 0.45, 0.4)

W, D, C = 8.0, 7.0, 1.9          # footprint and the corner chamfer (front-right corner)
T22 = math.tan(math.radians(22.5))
def poly(o):
    """Footprint offset outward by o (chamfered rectangle)."""
    return [(-W / 2 - o, -D / 2 - o), (W / 2 - C + o * T22, -D / 2 - o), (W / 2 + o, -D / 2 + C - o * T22),
            (W / 2 + o, D / 2 + o), (-W / 2 - o, D / 2 + o)]
def prism(name, o, z0, z1, idx, pts=None):
    pts = pts or poly(o)
    return hull(name, [(x, y, z) for x, y in pts for z in (z0, z1)], idx)
def street(o):
    """Only the two street faces and the chamfer (the hull closes it through the inside of the building)."""
    p = poly(o); return [(-W / 2 - 0.02, p[0][1]), p[1], p[2], (p[3][0], D / 2 - 0.02)]

TOP, WIN0, WIN1 = 3.90, 0.55, 2.50
F = wallM((0, -D / 2, 0), 0)                                   # front: local x = world x, -4 .. 2.1
R = wallM((W / 2, 0, 0), 90)                                   # right: local x = world y, -1.6 .. 3.5
CH = wallM((W / 2 - C / 2, -D / 2 + C / 2, 0), 45)             # chamfer: local x -1.34 .. 1.34
CL = C * math.sqrt(2) / 2

body = prism('Body', 0, 0.0, TOP, BRICK)
cutters = []
# display windows: green frames, three lights each, green sill
for M, x0, x1 in ((F, -3.45, 1.62), (R, -1.12, 2.95)):
    cutters.append(window(M, (x0 + x1) / 2, WIN0, x1 - x0, WIN1 - WIN0, GREEN, GLASS, BRICK, inset=0.12, ft=0.11, mt=0.08,
                          cols=3, rows=1))
    box('Sill', (x0 - 0.05, -0.12, WIN0 - 0.08), (x1 + 0.05, 0.03, WIN0 + 0.02), GREEN, 0.015, 1, M=M)
    box('TransomBar', (x0, 0.04, WIN1 - 0.40), (x1, 0.11, WIN1 - 0.34), GREEN, 0.01, 1, M=M)
# recessed corner entrance
DW = 1.5
cutters.append(box('DoorCut', (-DW / 2, -0.4, 0.12), (DW / 2, 0.80, WIN1), BRICK, M=CH))
cut(body, cutters)
Y = 0.74                         # door-frame plane inside the recess
for lo, hi in (((-DW / 2, 0.12), (-DW / 2 + 0.09, WIN1)), ((DW / 2 - 0.09, 0.12), (DW / 2, WIN1)),
               ((-0.50, 0.12), (-0.43, 2.12)), ((0.43, 0.12), (0.50, 2.12)),
               ((-DW / 2, WIN1 - 0.09), (DW / 2, WIN1)), ((-DW / 2, 2.09), (DW / 2, 2.18)),
               ((-DW / 2, 0.12), (DW / 2, 0.42))):
    box('DoorFrame', (lo[0], Y - 0.07, lo[1]), (hi[0], Y + 0.01, hi[1]), GREEN, 0.01, 1, M=CH)
box('DoorGlass', (-DW / 2, Y + 0.01, 0.12), (DW / 2, Y + 0.03, WIN1), GLASS, M=CH)
for xs in (-0.43, 0.43):        # door leaf stiles sit proud of the frame
    box('Stile', (xs - (0 if xs < 0 else 0.1), Y - 0.11, 0.42), (xs + (0.1 if xs < 0 else 0), Y - 0.06, 2.09), GREEN, 0.01, 1, M=CH)
box('Handle', (0.25, Y - 0.17, 0.95), (0.28, Y - 0.14, 1.45), STEEL, 0.008, 1, M=CH)
for zz in (0.97, 1.43):
    box('HandleLeg', (0.25, Y - 0.15, zz - 0.015), (0.28, Y - 0.10, zz + 0.015), STEEL, M=CH)
box('RecessFloor', (-DW / 2, -0.05, 0.0), (DW / 2, 0.78, 0.12), CONC, M=CH)
hull('Step', [(x, y, z) for x, y in ((-CL - 0.25, 0.0), (CL + 0.25, 0.0), (CL - 0.1, -0.55), (-CL + 0.1, -0.55))
              for z in (0.0, 0.11)], CONC, M=CH)

# dark plinth all round, sign band with green borders on the street faces, parapet cap, roof
prism('Plinth', 0.05, 0.0, 0.45, SLATE)
prism('PlinthCap', 0.08, 0.40, 0.48, SLATE)
prism('Sign', 0.07, 2.98, 3.70, TRIM, street(0.07))
prism('SignTrimLo', 0.11, 2.90, 3.00, GREEN, street(0.11))
prism('SignTrimHi', 0.11, 3.68, 3.78, GREEN, street(0.11))
cap = prism('Cap', 0.13, TOP - 0.05, TOP + 0.28, SLATE)
cut(cap, [prism('CapIn', -0.22, TOP + 0.06, TOP + 1.0, SLATE)])
for x, y in ((-W / 2, -D / 2), (-W / 2, D / 2), (W / 2, D / 2), (W / 2 - C + 0.1, -D / 2), (W / 2, -D / 2 + C - 0.1)):
    box('CapPost', (x - 0.22, y - 0.22, TOP + 0.20), (x + 0.22, y + 0.22, TOP + 0.36), SLATE, 0.03, 2)

# end piers stand proud of the brick between the windows
for M, xs in ((F, (-W / 2 + 0.28, 1.86)), (R, (-1.36, D / 2 - 0.28))):
    for k, x in enumerate(xs):
        end = (M is F and k == 0) or (M is R and k == 1)      # far ends run up past the sign band
        box('Pier', (x - 0.27, -0.12 if end else -0.06, 0.45), (x + 0.27, 0.02, TOP - 0.06 if end else 2.90), BRICK, 0.02, 2, M=M)
for x in (-CL + 0.31, CL - 0.31):
    box('Pier', (x - 0.31, -0.06, 0.45), (x + 0.31, 0.02, 2.90), BRICK, 0.02, 2, M=CH)

# awning: three mitred canvas slopes with a scalloped valance and black brackets
AT, AB, AP = 2.95, 2.66, 1.00    # top at the wall, front edge height, projection
EXT = AP * T22
def awning(M, x0, x1, m0, m1):
    """m0/m1: mitre the left/right end for a 135-degree corner."""
    xo0, xo1 = x0 - (EXT if m0 else 0), x1 + (EXT if m1 else 0)
    hull('Awning', [(x0, 0.0, AT), (x1, 0.0, AT), (xo0, -AP, AB), (xo1, -AP, AB),
                    (x0, 0.0, AT - 0.05), (x1, 0.0, AT - 0.05), (xo0, -AP, AB - 0.05), (xo1, -AP, AB - 0.05)], CANVAS, M=M)
    hull('Valance', [(xo0, -AP, AB + 0.01), (xo1, -AP, AB + 0.01), (xo0 + 0.03 * (m0), -AP + 0.05, AB + 0.01), (xo1 - 0.03 * (m1), -AP + 0.05, AB + 0.01),
                     (xo0, -AP, AB - 0.24), (xo1, -AP, AB - 0.24), (xo0 + 0.03 * (m0), -AP + 0.05, AB - 0.24), (xo1 - 0.03 * (m1), -AP + 0.05, AB - 0.24)],
         CANVAS, M=M)
    n = max(2, round((xo1 - xo0) / 0.34)); step = (xo1 - xo0) / n
    for k in range(n):
        x = xo0 + step * (k + 0.5)
        cyl('Scallop', step * 0.5, -0.018, 0.018, (0, 0), CANVAS, 12,
            M=M @ Matrix.Translation((x, -AP + 0.025, AB - 0.24)) @ Matrix.Rotation(math.pi / 2, 4, 'X'))
awning(F, -W / 2 + 0.1, W / 2 - C, False, True)
awning(R, -D / 2 + C, D / 2 - 0.1, True, False)
awning(CH, -CL, CL, True, True)
for M, x in ((F, -W / 2 + 0.3), (F, 1.86), (R, -1.36), (R, D / 2 - 0.3)):
    hull('Bracket', [(x + dx, y, z) for dx in (-0.025, 0.025) for y, z in ((0.0, 2.32), (0.0, 2.40), (-0.75, AT - 0.75 * (AT - AB) / AP - 0.06),
                                                                            (-0.75, AT - 0.75 * (AT - AB) / AP - 0.12))], SLATE, M=M)
    box('BracketPlate', (x - 0.06, -0.03, 2.18), (x + 0.06, 0.0, 2.50), SLATE, 0.008, 1, M=M)

# back: steel service door and a small barred window; roof: AC unit and a hatch
B = face_M('B', D / 2)
bc = [box('BackDoorCut', (1.2, -0.4, 0.0), (2.2, 0.3, 2.15), BRICK, M=B),
      window(B, -1.8, 1.5, 1.0, 0.8, SLATE, GLASS, BRICK, inset=0.1, ft=0.06, cols=1, rows=1)]
cut(body, bc)
box('BackDoor', (1.22, 0.12, 0.0), (2.18, 0.17, 2.13), STEEL, 0.01, 1, M=B)
box('BackHandle', (1.33, 0.06, 1.0), (1.45, 0.12, 1.04), SLATE, 0.005, 1, M=B)
box('BackLintel', (1.1, -0.04, 2.15), (2.3, 0.02, 2.3), CONC, 0.01, 1, M=B)
for k in range(4):
    x = -2.15 + 0.7 / 3 * k + 0.0
    box('Bar', (x + 0.08, -0.03, 1.5), (x + 0.11, 0.0, 2.3), SLATE, M=B)
box('AC', (-2.6, 0.6, TOP + 0.06), (-1.4, 1.5, TOP + 0.55), STEEL, 0.04, 2)
cyl('Fan', 0.36, TOP + 0.55, TOP + 0.58, (-2.0, 1.05), SLATE, 20)
box('Hatch', (1.0, 1.4, TOP + 0.06), (1.9, 2.3, TOP + 0.36), SLATE, 0.03, 2)

mesh = finish('shopfront', 'Shopfront')
studio()
shoot('render-34', (12.6, -13.6, 3.8), (0.7, -0.6, 1.85), 45)
d = Vector((1, -1, 0)).normalized()
shoot('render-front', tuple(Vector((3.25, -2.75, 2.1)) + d * 30), (3.25, -2.75, 2.1), ortho=12.6)

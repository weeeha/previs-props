# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_tent.py -- <out dir>
# 1 unit = 1 m, front toward -Y, up +Z, origin on the ground at the centre of the footprint.
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
        bmesh.ops.bevel(bm, geom=bm.edges[:] + bm.verts[:], offset=bevel, segments=segs, affect='EDGES', profile=0.5)
    bm.to_mesh(me); bm.free()
    if M is not None: me.transform(M)
    o = new_obj(name, me); set_all(o, idx); return o

def prism(name, pts, a0, a1, idx, bevel=0.0, segs=2, axis='X', M=None):
    """Extrude a convex 2D polygon. axis 'X': pts are (y, z), extruded from x=a0 to a1. axis 'Y': pts are (x, z)."""
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    def P(p, a): return (a, p[0], p[1]) if axis == 'X' else (p[0], a, p[1])
    r0 = [bm.verts.new(P(p, a0)) for p in pts]; r1 = [bm.verts.new(P(p, a1)) for p in pts]
    n = len(pts)
    bm.faces.new(r0); bm.faces.new(r1[::-1])
    for i in range(n):
        bm.faces.new([r0[i], r0[(i + 1) % n], r1[(i + 1) % n], r1[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if bevel:
        bmesh.ops.bevel(bm, geom=bm.edges[:] + bm.verts[:], offset=bevel, segments=segs, affect='EDGES', profile=0.5)
    bm.to_mesh(me); bm.free()
    if M is not None: me.transform(M)
    o = new_obj(name, me); set_all(o, idx); return o

def lathe(name, prof, n, loc=(0, 0, 0), cap_top=True, cap_bot=True, M=None):
    """prof: list of (r, z, mat_idx); segment i (point i to i+1) takes prof[i][2]."""
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    rings = [[bm.verts.new((loc[0] + r * math.cos(2 * math.pi * k / n), loc[1] + r * math.sin(2 * math.pi * k / n), loc[2] + z))
              for k in range(n)] for r, z, _ in prof]
    for i in range(len(prof) - 1):
        for k in range(n):
            f = bm.faces.new([rings[i][k], rings[i][(k + 1) % n], rings[i + 1][(k + 1) % n], rings[i + 1][k]])
            f.material_index = prof[i][2]
    if cap_bot: f = bm.faces.new(rings[0][::-1]); f.material_index = prof[0][2]
    if cap_top: f = bm.faces.new(rings[-1]); f.material_index = prof[-2][2]
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    if M is not None: me.transform(M)
    return new_obj(name, me)

def tube(name, pts, r, idx, n=8):
    """Round rod along a polyline (no fillets)."""
    P = [Vector(p) for p in pts]
    me = bpy.data.meshes.new(name); bm = bmesh.new(); rings = []
    for i, p in enumerate(P):
        t = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized()
        u = t.cross(Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))).normalized(); v = t.cross(u)
        rings.append([bm.verts.new(p + r * (math.cos(2 * math.pi * k / n) * u + math.sin(2 * math.pi * k / n) * v)) for k in range(n)])
    for i in range(len(rings) - 1):
        for k in range(n):
            bm.faces.new([rings[i][k], rings[i][(k + 1) % n], rings[i + 1][(k + 1) % n], rings[i + 1][k]])
    bm.faces.new(rings[0][::-1]); bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    o = new_obj(name, me); set_all(o, idx); return o

def boolean(target, cutters, op='DIFFERENCE'):
    """Apply one boolean with all cutters joined into a single object."""
    if not cutters: return
    for o in scene.objects: o.select_set(False)
    for c in cutters: c.select_set(True)
    bpy.context.view_layer.objects.active = cutters[0]
    if len(cutters) > 1: bpy.ops.object.join()
    cut = cutters[0]
    for c in cutters: parts.remove(c)
    m = target.modifiers.new('b', 'BOOLEAN'); m.operation = op; m.object = cut; m.solver = 'EXACT'; m.use_self = True
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier='b')
    bpy.data.objects.remove(cut)

def wall_frame(side, half_x, half_y):
    """Local wall frame: local x = along the wall (left to right seen from outside), local -y = outward, z = up."""
    if side == 'front': return Matrix.Translation((0, -half_y, 0))
    if side == 'back': return Matrix.Translation((0, half_y, 0)) @ Matrix.Rotation(math.pi, 4, 'Z')
    if side == 'left': return Matrix.Translation((-half_x, 0, 0)) @ Matrix.Rotation(-math.pi / 2, 4, 'Z')
    if side == 'right': return Matrix.Translation((half_x, 0, 0)) @ Matrix.Rotation(math.pi / 2, 4, 'Z')

# ---------------------------------------------------------------- join (all parts carry the same slot list)
def finish(name, smooth_deg=35):
    for o in scene.objects: o.select_set(False)
    for o in parts: o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    mesh = bpy.context.view_layer.objects.active; mesh.name = f'{name}_Mesh'
    assert [m.name for m in mesh.data.materials] == [m.name for m in ORDER], 'material slots shuffled'
    bm = bmesh.new(); bm.from_mesh(mesh.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0003)
    bm.to_mesh(mesh.data); bm.free()
    with bpy.context.temp_override(active_object=mesh, object=mesh, selected_objects=[mesh], selected_editable_objects=[mesh]):
        bpy.ops.object.shade_auto_smooth(angle=math.radians(smooth_deg))
    tris = sum(len(p.vertices) - 2 for p in mesh.data.polygons)
    used = sorted({p.material_index for p in mesh.data.polygons})
    d = mesh.dimensions
    print(f'[{name}] triangles {tris}, materials {len(used)} {[ORDER[i].name for i in used]}, size {d.x:.2f} x {d.y:.2f} x {d.z:.2f}')
    root = bpy.data.objects.new(name, None); scene.collection.objects.link(root); mesh.parent = root
    for o in scene.objects: o.select_set(False)
    root.select_set(True); mesh.select_set(True)
    bpy.ops.export_scene.fbx(filepath=f'{OUT}/{name}.fbx', use_selection=True, apply_unit_scale=True,
                             apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)
    return mesh

def studio():
    world = bpy.data.worlds.new('W'); scene.world = world; world.use_nodes = True
    wn = world.node_tree.nodes; wl = world.node_tree.links
    wn['Background'].inputs['Color'].default_value = (0.62, 0.62, 0.64, 1)        # what lights the model
    wn['Background'].inputs['Strength'].default_value = 0.55
    bg_cam = wn.new('ShaderNodeBackground'); bg_cam.inputs['Color'].default_value = (0.68, 0.68, 0.69, 1)   # what the camera sees
    lp = wn.new('ShaderNodeLightPath'); mix = wn.new('ShaderNodeMixShader')
    wl.new(lp.outputs['Is Camera Ray'], mix.inputs['Fac']); wl.new(wn['Background'].outputs[0], mix.inputs[1])
    wl.new(bg_cam.outputs[0], mix.inputs[2]); wl.new(mix.outputs[0], wn['World Output'].inputs['Surface'])
    gme = bpy.data.meshes.new('Ground'); gbm = bmesh.new()
    bmesh.ops.create_grid(gbm, x_segments=1, y_segments=1, size=80); gbm.to_mesh(gme); gbm.free()
    ground = bpy.data.objects.new('Ground', gme); scene.collection.objects.link(ground)
    gm = bpy.data.materials.new('GroundM'); gm.use_nodes = True
    gm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.42, 0.42, 0.43, 1)
    gm.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 1.0
    gme.materials.append(gm)
    ground.visible_camera = False   # seamless studio backdrop, shadow only
    sun_d = bpy.data.lights.new('Sun', 'SUN'); sun_d.energy = 3.4; sun_d.angle = math.radians(12)
    sun = bpy.data.objects.new('Sun', sun_d); scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(50), 0, math.radians(32))
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x, scene.render.resolution_y = 1672, 941
    scene.view_settings.view_transform = 'Standard'
    try: scene.eevee.taa_render_samples = 48
    except Exception: pass

def shoot(name, loc, target, lens=50, ortho=None):
    cam = scene.camera
    if cam is None:
        cam_d = bpy.data.cameras.new('Cam'); cam = bpy.data.objects.new('Cam', cam_d)
        scene.collection.objects.link(cam); scene.camera = cam
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    if ortho: cam.data.type = 'ORTHO'; cam.data.ortho_scale = ortho
    else: cam.data.type = 'PERSP'; cam.data.lens = lens
    scene.render.filepath = f'{OUT}/{name}.png'; bpy.ops.render.render(write_still=True)

# ================================================================ TENT
# Canvas ridge tent (own design), previs library. After ref-34.png: short sidewalls under an A roof with a fly lip,
# green bottom band, two wooden poles (front and back), front flap half open and tied back, guy lines to wooden pegs.
# Body 2.4 m wide (x) x 3.0 m long (y), ridge 1.80 m, pole tops 2.02 m. Entrance on the front (-Y) gable.
CANVAS = mat('Canvas', (0.600, 0.455, 0.235))
CANVAS_IN = mat('CanvasShade', (0.200, 0.140, 0.065))
GREEN = mat('Groundsheet', (0.150, 0.170, 0.045))
WOOD = mat('Wood', (0.330, 0.105, 0.028))
ROPE = mat('Rope', (0.560, 0.390, 0.170))

HX, HY = 1.2, 1.5
EAVE, RIDGE = 0.70, 1.80
KS = (RIDGE - EAVE) / HX      # roof slope

# ---------------------------------------------------------------- body: hollow pentagon shell with the door cut out
body = prism('Body', [(-HX, 0.0), (HX, 0.0), (HX, EAVE), (0, RIDGE), (-HX, EAVE)], -HY, HY, CANVAS, 0.012, 1, axis='Y')
T = 0.03
inner = prism('Inner', [(-HX + T, 0.02), (HX - T, 0.02), (HX - T, EAVE - 0.01), (0, RIDGE - T * 1.4), (-HX + T, EAVE - 0.01)],
              -HY + T, HY - T, CANVAS_IN, axis='Y')
door = prism('DoorCut', [(0.05, -0.1), (0.72, -0.1), (0.72, 1.05), (0.05, 1.66)], -HY - 0.2, -HY + 0.2, CANVAS_IN, axis='Y')
boolean(body, [inner, door])
box('Floor', (-HX + T, -HY + T, 0.02), (HX - T, HY - T, 0.035), GREEN)

# fly: two thin roof slabs over the body with a lip past the walls
for sx in (-1, 1):
    xo = sx * (HX + 0.16)
    z0 = RIDGE + 0.004
    pts = [(0, z0), (0, z0 + 0.035), (xo, z0 + 0.035 - abs(xo) * KS), (xo, z0 - abs(xo) * KS)]
    prism('Fly', pts, -HY - 0.035, HY + 0.035, CANVAS, 0.012, 1, axis='Y')

# green bottom band (left of the door, right of the door, sides, back)
BH, BP = 0.20, 0.008
box('BandL', (-HX - BP, -HY - BP, 0.0), (0.05, -HY + 0.02, BH), GREEN)
box('BandR', (0.72, -HY - BP, 0.0), (HX + BP, -HY + 0.02, BH), GREEN)
box('BandB', (-HX - BP, HY - 0.02, 0.0), (HX + BP, HY + BP, BH), GREEN)
for sx in (-1, 1):
    box('BandS', (sx * HX - 0.02 if sx > 0 else -HX - BP, -HY - BP, 0.0), (HX + BP if sx > 0 else -HX + 0.02, HY + BP, BH), GREEN)

# ---------------------------------------------------------------- the open flap: diagonal edge + gathered bundle tied back
prism('FlapEdge', [(0.05, 1.70), (0.15, 1.66), (0.84, 0.58), (0.74, 0.55)], -HY - 0.03, -HY - 0.005, CANVAS, 0.006, 1, axis='Y')
FX, FY = 0.84, -HY - 0.07
lathe('Bundle', [(0.0, 0.000, CANVAS), (0.10, 0.000, CANVAS), (0.12, 0.117, CANVAS), (0.10, 0.328, CANVAS), (0.06, 0.468, CANVAS),
                 (0.045, 0.538, CANVAS), (0.06, 0.620, CANVAS), (0.085, 0.749, CANVAS), (0.07, 0.889, CANVAS), (0.03, 1.006, CANVAS),
                 (0.0, 1.018, CANVAS)], 14, (FX, FY, 0.0))
lathe('Tie', [(0.050, 0.474, ROPE), (0.068, 0.491, ROPE), (0.068, 0.585, ROPE), (0.050, 0.603, ROPE)], 14, (FX, FY, 0.0),
      cap_top=False, cap_bot=False)

# ---------------------------------------------------------------- poles with rope lashing
PT = 2.02
for sy in (-1, 1):
    py = sy * (HY + 0.075)
    box('Pole', (-0.045, py - 0.045, 0.0), (0.045, py + 0.045, PT), WOOD, 0.018, 2)
    lathe('Lash', [(0.058, 1.70, ROPE), (0.07, 1.715, ROPE), (0.07, 1.82, ROPE), (0.058, 1.835, ROPE)], 12, (0, py, 0),
          cap_top=False, cap_bot=False)

# ---------------------------------------------------------------- pegs and guy lines
def peg(px, py):
    u = Vector((px, py, 0)).normalized(); a = Vector((-u.y, u.x, 0))
    M = Matrix.Translation((px, py, 0)) @ Matrix.Rotation(math.radians(14), 4, a)
    box('Peg', (-0.028, -0.028, -0.15), (0.028, 0.028, 0.20), WOOD, 0.01, 1, M=M)
    lathe('Wrap', [(0.036, 0.10, ROPE), (0.046, 0.11, ROPE), (0.046, 0.15, ROPE), (0.036, 0.16, ROPE)], 10,
          M=M, cap_top=False, cap_bot=False)
    return M @ Vector((0, 0, 0.13))

for sy in (-1, 1):
    top = Vector((0, sy * (HY + 0.075), 1.77))
    for sx in (-1, 1):
        tube('Guy', [top, peg(sx * 0.95, sy * 2.75)], 0.011, ROPE, 6)
for sx in (-1, 1):
    for sy in (-1, 1):
        yy = sy * (HY - 0.35)
        ex = sx * (HX + 0.14); ez = RIDGE + 0.004 - abs(ex) * KS + 0.01
        box('Patch', (ex - 0.05 if sx > 0 else ex - 0.02, yy - 0.06, ez - 0.03), (ex + 0.02 if sx > 0 else ex + 0.05, yy + 0.06, ez + 0.06), GREEN, 0.008, 1)
        tube('Guy', [Vector((ex, yy, ez)), peg(sx * 2.15, sy * 1.55)], 0.011, ROPE, 6)

finish('Tent')
studio()
shoot('render-34', (4.4, -6.6, 2.7), (-0.1, 0, 0.85), 38)

# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_cabin.py -- <out dir>
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

# ================================================================ CABIN
# Small wooden cabin (own design), previs library. After ref-34.png / ref-front.png: gable front with a plank door
# and one cross-barred window, horizontal plank walls as shallow grooves, corner posts, sill beam on stone piers,
# shingle roof (ridge along Y) with barge boards and rafter tails, steel stove pipe with a conical cap.
WOOD = mat('Wood', (0.330, 0.105, 0.028))
WOOD_D = mat('WoodDark', (0.190, 0.060, 0.020))
ROOF = mat('RoofShingle', (0.085, 0.085, 0.090), 0.8)
CONC = mat('Concrete', (0.215, 0.215, 0.220))
GLASS = mat('Glass', (0.130, 0.190, 0.300), 0.25)
STEEL = mat('Steel', (0.060, 0.064, 0.070), 0.55, 0.3)

HX, HY = 2.1, 1.8           # half footprint of the walls (gable front 4.2 m, depth 3.6 m)
F = 0.50                    # floor / wall bottom
H = 2.50                    # eave line
K = 0.45; A = math.atan(K)
OVE, OVG = 0.38, 0.32       # eave / gable overhang
TS = 0.12
ZU0 = H + HX * K; ZT0 = ZU0 + TS
YR = HY + OVG

# ---------------------------------------------------------------- base
for sx in (-1, 0, 1):
    for sy in (-1, 1):
        x = sx * (HX - 0.12); y = sy * (HY - 0.12)
        box('Pier', (x - 0.17, y - 0.17, 0.0), (x + 0.17, y + 0.17, 0.32), CONC, 0.03, 2)
box('Sill', (-HX - 0.09, -HY - 0.09, 0.30), (HX + 0.09, HY + 0.09, F), WOOD_D, 0.025, 2)

# ---------------------------------------------------------------- plank walls and gables
walls = box('Walls', (-HX, -HY, F - 0.02), (HX, HY, H), WOOD)
gable = prism('Gable', [(-HX, H - 0.02), (HX, H - 0.02), (0, ZU0 + 0.02)], -HY, HY, WOOD, axis='Y')
PLANK, GD, GH = 0.24, 0.032, 0.042
def grooves(z0, z1):
    cut = []; z = z0
    while z < z1:
        cut += [box('G', (-HX - 0.2, -HY - 0.2, z), (HX + 0.2, -HY + GD, z + GH), WOOD),
                box('G', (-HX - 0.2, HY - GD, z), (HX + 0.2, HY + 0.2, z + GH), WOOD),
                box('G', (-HX - 0.2, -HY - 0.2, z), (-HX + GD, HY + 0.2, z + GH), WOOD),
                box('G', (HX - GD, -HY - 0.2, z), (HX + 0.2, HY + 0.2, z + GH), WOOD)]
        z += PLANK
    return cut
cutters = grooves(F + PLANK, H - 0.05)
boolean(gable, grooves(H + 0.14 + PLANK * 0.6, ZU0 - 0.12))

for sx in (-1, 1):            # corner posts
    for sy in (-1, 1):
        box('Post', (sx * HX - 0.10, sy * HY - 0.10, F - 0.02), (sx * HX + 0.10, sy * HY + 0.10, H + 0.02), WOOD_D, 0.02, 2)
for sy in (-1, 1):            # tie beam and king post on both gables
    box('Tie', (-HX - 0.12, sy * HY - 0.07, H - 0.02), (HX + 0.12, sy * HY + 0.07, H + 0.16), WOOD_D, 0.02, 2)
    box('King', (-0.08, sy * HY - 0.06, H + 0.16), (0.08, sy * HY + 0.06, ZU0 - 0.03), WOOD_D, 0.02, 2)
for sx in (-1, 1):            # wall plates along the eaves
    box('Plate', (sx * HX - 0.07, -HY - 0.1, H - 0.12), (sx * HX + 0.07, HY + 0.1, H + 0.04), WOOD_D, 0.02, 2)

# ---------------------------------------------------------------- door and window on the gable front
M = wall_frame('front', HX, HY)
DU, DW, DH = -0.85, 0.86, 1.92
cutters.append(box('DoorCut', (DU - DW / 2, -0.3, F), (DU + DW / 2, 0.13, F + DH), WOOD, M=M))
door = box('Door', (DU - DW / 2, 0.06, F), (DU + DW / 2, 0.13, F + DH), WOOD, M=M)
boolean(door, [box('DG', (DU - DW / 2 + k * DW / 4 - 0.012, 0.0, F - 0.1), (DU - DW / 2 + k * DW / 4 + 0.012, 0.075, F + DH + 0.1), WOOD, M=M)
               for k in (1, 2, 3)])
box('DoorCore', (DU - DW / 2, 0.074, F), (DU + DW / 2, 0.13, F + DH), WOOD, M=M)
for zz in (F + 0.28, F + DH - 0.42):
    box('Batten', (DU - DW / 2 + 0.04, 0.03, zz), (DU + DW / 2 - 0.04, 0.06, zz + 0.16), WOOD_D, 0.012, 1, M=M)
    for xx in (DU - DW / 2 + 0.12, DU + DW / 2 - 0.12):
        box('Bolt', (xx - 0.022, 0.018, zz + 0.058), (xx + 0.022, 0.03, zz + 0.102), STEEL, 0.006, 1, M=M)
    box('Hinge', (DU - DW / 2 - 0.10, 0.012, zz + 0.04), (DU - DW / 2 + 0.22, 0.03, zz + 0.12), STEEL, 0.006, 1, M=M)
lathe('Knob', [(0.0, 0, STEEL), (0.02, 0, STEEL), (0.02, 0.03, STEEL), (0.05, 0.045, STEEL), (0.05, 0.07, STEEL),
               (0.03, 0.085, STEEL), (0.0, 0.088, STEEL)], 16,
      M=M @ Matrix.Translation((DU + DW / 2 - 0.13, 0.06, F + 0.98)) @ Matrix.Rotation(math.pi / 2, 4, 'X'))
b = lambda lo, hi, idx=WOOD_D, bev=0.015: box('Frame', lo, hi, idx, bev, 1, M=M)
b((DU - DW / 2 - 0.13, -0.05, F), (DU - DW / 2, 0.0, F + DH))
b((DU + DW / 2, -0.05, F), (DU + DW / 2 + 0.13, 0.0, F + DH))
b((DU - DW / 2 - 0.19, -0.065, F + DH), (DU + DW / 2 + 0.19, 0.0, F + DH + 0.15))

WU, WZ, WW, WH = 0.95, 1.30, 0.92, 0.78
cutters.append(box('WinCut', (WU - WW / 2, -0.3, WZ), (WU + WW / 2, 0.13, WZ + WH), WOOD, M=M))
box('Glass', (WU - WW / 2, 0.09, WZ), (WU + WW / 2, 0.13, WZ + WH), GLASS, M=M)
b((WU - WW / 2 - 0.11, -0.05, WZ), (WU - WW / 2, 0.0, WZ + WH))
b((WU + WW / 2, -0.05, WZ), (WU + WW / 2 + 0.11, 0.0, WZ + WH))
b((WU - WW / 2 - 0.17, -0.065, WZ + WH), (WU + WW / 2 + 0.17, 0.0, WZ + WH + 0.12))
b((WU - WW / 2 - 0.19, -0.11, WZ - 0.11), (WU + WW / 2 + 0.19, 0.0, WZ))
b((WU - 0.03, 0.04, WZ), (WU + 0.03, 0.09, WZ + WH), WOOD, 0.008)
b((WU - WW / 2, 0.04, WZ + WH / 2 - 0.03), (WU + WW / 2, 0.09, WZ + WH / 2 + 0.03), WOOD, 0.008)
boolean(walls, cutters)

# ---------------------------------------------------------------- steps up to the door
for sx in (-1, 1):
    x0 = DU + sx * 0.47
    prism('Stringer', [(-HY - 0.74, 0.0), (-HY - 0.56, 0.0), (-HY + 0.02, 0.40), (-HY + 0.02, 0.52)], x0 - 0.035, x0 + 0.035, WOOD_D, 0.012, 1)
box('Tread', (DU - 0.52, -HY - 0.62, 0.15), (DU + 0.52, -HY - 0.30, 0.21), WOOD, 0.015, 2)
box('Tread', (DU - 0.52, -HY - 0.34, 0.33), (DU + 0.52, -HY - 0.02, 0.39), WOOD, 0.015, 2)

# ---------------------------------------------------------------- roof: slabs, shingle courses, barge boards, ridge
def roof_frame(sx):
    """x along the ridge, y down-slope toward side sx, z out of the roof; origin on the slab top at the ridge."""
    c, sn = math.cos(A), math.sin(A)
    return Matrix(((0, sx * c, sx * sn, 0), (-sx, 0, 0, 0), (0, -sn, c, ZT0), (0, 0, 0, 1)))
SL = (HX + OVE) / math.cos(A)
for sx in (-1, 1):
    xo = sx * (HX + OVE)
    prism('RoofSlab', [(0, ZU0), (0, ZT0), (xo, ZT0 - abs(xo) * K), (xo, ZU0 - abs(xo) * K)], -YR, YR, ROOF, 0.015, 1, axis='Y')
    R = roof_frame(sx)
    NC = 5; L = (SL + 0.02) / NC; tilt = math.atan(0.03 / L); TW = 0.75
    for i in range(NC):
        s0 = i * L - 0.035 if i else 0.0
        Mt = R @ Matrix.Translation((0, s0, 0)) @ Matrix.Rotation(tilt, 4, 'X')
        off = (i % 2) * TW / 2
        xs = [-YR] + [x for x in [-YR + off + k * TW for k in range(1, 12)] if -YR + 0.2 < x < YR - 0.2] + [YR]
        for a, bb in zip(xs[:-1], xs[1:]):
            box('Shingle', (a + 0.012, 0.0, -0.01), (bb - 0.012, L + 0.035, 0.045), ROOF, M=Mt)
    for e in (-1, 1):   # barge boards on the rakes
        box('Barge', (e * YR - 0.06, -0.02, -TS - 0.16), (e * YR + 0.06, SL + 0.02, 0.07), WOOD_D, 0.018, 2, M=R)
    for lx in (-1.35, -0.45, 0.45, 1.35):   # rafter tails under the eave
        box('Rafter', (lx - 0.06, SL - 0.62, -TS - 0.15), (lx + 0.06, SL - 0.04, -TS), WOOD_D, 0.015, 1, M=R)
box('RidgeCap', (-0.11, -YR - 0.08, -0.11), (0.11, YR + 0.08, 0.11), WOOD_D, 0.025, 2,
    M=Matrix.Translation((0, 0, ZT0 + 0.04)) @ Matrix.Rotation(math.pi / 4, 4, 'Y'))

# ---------------------------------------------------------------- stove pipe on the right slope
PX, PY = 1.05, 0.55
zr = ZT0 - PX * K
lathe('Pipe', [(0.0, zr - 0.3, STEEL), (0.10, zr - 0.3, STEEL), (0.10, zr + 0.40, STEEL), (0.125, zr + 0.41, STEEL),
               (0.125, zr + 0.47, STEEL), (0.085, zr + 0.48, STEEL), (0.085, zr + 0.66, STEEL), (0.035, zr + 0.66, STEEL),
               (0.035, zr + 0.70, STEEL), (0.24, zr + 0.70, STEEL), (0.24, zr + 0.73, STEEL), (0.02, zr + 0.84, STEEL),
               (0.0, zr + 0.84, STEEL)], 24, (PX, PY, 0))
R = roof_frame(1); s = PX / math.cos(A); lx = -PY
box('Flashing', (lx - 0.24, s - 0.26, 0.02), (lx + 0.24, s + 0.26, 0.07), STEEL, 0.012, 1, M=R)

finish('Cabin')
studio()
shoot('render-34', (-5.6, -9.4, 3.3), (0.1, 0, 1.75), 40)
shoot('render-front', (0, -30, 2.0), (0, 0, 2.0), ortho=7.3)

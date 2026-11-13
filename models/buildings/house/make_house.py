# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_house.py -- <out dir>
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

# ================================================================ HOUSE
# Single-storey suburban house (own design), previs library. Measured loosely from ref-34.png / ref-front.png:
# stucco walls on a concrete plinth, slate tile roof (ridge along X), red lap siding in the gables, a small
# gabled porch on two square columns over the front door, four front windows, brick chimney on the back slope.
STUCCO = mat('Stucco', (0.62, 0.48, 0.30))
TRIM = mat('Trim', (0.74, 0.64, 0.48))
ROOF = mat('Roof', (0.085, 0.095, 0.130), 0.8)
CONC = mat('Concrete', (0.215, 0.215, 0.220))
BRICK = mat('Brick', (0.330, 0.105, 0.065))
GLASS = mat('Glass', (0.130, 0.190, 0.300), 0.25)
DOOR = mat('Door', (0.300, 0.085, 0.050))
BLACK = mat('Black', (0.020, 0.020, 0.022), 0.5)

HX, HY = 5.0, 4.0           # half footprint of the walls
PL = 0.42                   # plinth top / floor
H = 2.80                    # wall top (eave line)
K = 0.50                    # roof pitch (rise per run)
OVE, OVG = 0.45, 0.35       # eave / gable overhang
TS = 0.16                   # roof slab thickness (vertical)
ZU0 = H + HY * K            # underside at the ridge
ZT0 = ZU0 + TS              # slab top at the ridge
A = math.atan(K)

# ---------------------------------------------------------------- shell
walls = box('Walls', (-HX, -HY, PL - 0.05), (HX, HY, H), STUCCO)
box('Plinth', (-HX - 0.07, -HY - 0.07, 0.0), (HX + 0.07, HY + 0.07, PL), CONC, 0.025, 2)
gable = prism('Gable', [(-HY, H - 0.02), (HY, H - 0.02), (0, ZU0 + 0.02)], -HX, HX, BRICK)
for sx in (-1, 1):   # cream belt board under each gable
    box('Belt', (sx * HX - 0.045, -HY - 0.045, H - 0.06), (sx * HX + 0.045, HY + 0.045, H + 0.10), TRIM, 0.015, 2)
for sx in (-1, 1):   # corner boards
    for sy in (-1, 1):
        box('Corner', (sx * HX - 0.08, sy * HY - 0.08, PL), (sx * HX + 0.08, sy * HY + 0.08, H - 0.02), STUCCO, 0.02, 2)

# lap siding grooves in the gables
cut = []
z = H + 0.28
while z < ZU0 - 0.1:
    for sx in (-1, 1):
        cut.append(box('Groove', (sx * HX - 0.025 if sx > 0 else -HX - 0.2, -HY, z), (HX + 0.2 if sx > 0 else -HX + 0.025, HY, z + 0.045), BRICK))
    z += 0.30
boolean(gable, cut)

# ---------------------------------------------------------------- windows and door (cut into the wall box)
def window(side, u, z0, w=1.0, h=1.05):
    M = wall_frame(side, HX, HY)
    cutters.append(box('WinCut', (u - w / 2, -0.3, z0), (u + w / 2, 0.14, z0 + h), STUCCO, M=M))
    b = lambda lo, hi, idx=TRIM, bev=0.012: box('Win', lo, hi, idx, bev, 1, M=M)
    b((u - w / 2 - 0.09, -0.045, z0), (u - w / 2, 0.0, z0 + h))
    b((u + w / 2, -0.045, z0), (u + w / 2 + 0.09, 0.0, z0 + h))
    b((u - w / 2 - 0.12, -0.06, z0 + h), (u + w / 2 + 0.12, 0.0, z0 + h + 0.11))
    b((u - w / 2 - 0.15, -0.11, z0 - 0.09), (u + w / 2 + 0.15, 0.0, z0))
    box('Glass', (u - w / 2, 0.10, z0), (u + w / 2, 0.14, z0 + h), GLASS, M=M)
    f = 0.055   # sash frame + cross muntins
    b((u - w / 2, 0.05, z0), (u - w / 2 + f, 0.10, z0 + h), TRIM, 0.006)
    b((u + w / 2 - f, 0.05, z0), (u + w / 2, 0.10, z0 + h), TRIM, 0.006)
    b((u - w / 2 + f, 0.05, z0), (u + w / 2 - f, 0.10, z0 + f), TRIM, 0.006)
    b((u - w / 2 + f, 0.05, z0 + h - f), (u + w / 2 - f, 0.10, z0 + h), TRIM, 0.006)
    b((u - 0.025, 0.055, z0 + f), (u + 0.025, 0.10, z0 + h - f), TRIM, 0.006)
    b((u - w / 2 + f, 0.055, z0 + h / 2 - 0.025), (u + w / 2 - f, 0.10, z0 + h / 2 + 0.025), TRIM, 0.006)

def door(side, u, z0, w=0.95, h=2.12):
    M = wall_frame(side, HX, HY)
    cutters.append(box('DoorCut', (u - w / 2, -0.3, z0), (u + w / 2, 0.16, z0 + h), STUCCO, M=M))
    b = lambda lo, hi, idx=TRIM, bev=0.012: box('Door', lo, hi, idx, bev, 1, M=M)
    b((u - w / 2 - 0.11, -0.05, z0), (u - w / 2, 0.0, z0 + h))
    b((u + w / 2, -0.05, z0), (u + w / 2 + 0.11, 0.0, z0 + h))
    b((u - w / 2 - 0.15, -0.06, z0 + h), (u + w / 2 + 0.15, 0.0, z0 + h + 0.13))
    b((u - w / 2, 0.08, z0), (u + w / 2, 0.16, z0 + h), DOOR, 0.0)
    for zz, hh in ((z0 + 0.18, 0.80), (z0 + 1.15, 0.78)):      # two raised panels
        b((u - w / 2 + 0.13, 0.06, zz), (u + w / 2 - 0.13, 0.08, zz + hh), DOOR, 0.012)
    lathe('Knob', [(0.0, 0, BLACK), (0.022, 0, BLACK), (0.022, 0.035, BLACK), (0.045, 0.05, BLACK), (0.048, 0.075, BLACK),
                   (0.03, 0.095, BLACK), (0.0, 0.098, BLACK)], 16,
          M=M @ Matrix.Translation((u + w / 2 - 0.13, 0.08, z0 + 1.02)) @ Matrix.Rotation(math.pi / 2, 4, 'X'))

cutters = []
WZ, WH = 1.15, 1.05
for u in (-3.75, -2.05, 2.05, 3.75): window('front', u, WZ)
for u in (-2.6, 1.2): window('back', u, WZ)
window('left', 0.0, WZ); window('right', -0.9, WZ)
door('front', 0.0, PL)
boolean(walls, cutters)

# ---------------------------------------------------------------- main roof: base slab + tile courses + ridge
def roof_frame(sy):
    """Roof-local frame for the slope on side sy (-1 front, +1 back): x along ridge, y down-slope, z out of the roof.
    Origin on the slab top at the ridge."""
    d = Vector((0, sy * math.cos(A), -math.sin(A))); n = Vector((0, sy * math.sin(A), math.cos(A)))
    R = Matrix(((sy * -1, 0, 0, 0), (0, d.y, n.y, 0), (0, d.z, n.z, ZT0), (0, 0, 0, 1)))
    return R

SL = (HY + OVE) / math.cos(A)      # slope length ridge -> eave edge
XR = HX + OVG
for sy in (-1, 1):
    yo = sy * (HY + OVE)
    pts = [(0, ZU0), (0, ZT0), (yo, ZT0 - (HY + OVE) * K), (yo, ZU0 - (HY + OVE) * K)]
    if sy < 0: pts = pts[::-1]
    prism('RoofSlab', pts, -XR, XR, ROOF, 0.02, 1)
    R = roof_frame(sy)
    NC = 8; L = (SL + 0.02) / NC; TW = 1.0; TT = 0.05
    tilt = math.atan(0.035 / L)
    for i in range(NC):
        s0 = i * L - 0.04 if i else 0.0
        off = (i % 2) * TW / 2
        xs = [-XR] + [x for x in [-XR + off + k * TW for k in range(1, 13)] if -XR + 0.25 < x < XR - 0.25] + [XR]
        Mt = R @ Matrix.Translation((0, s0, 0)) @ Matrix.Rotation(tilt, 4, 'X')
        for a, b in zip(xs[:-1], xs[1:]):
            box('Tile', (a + 0.014, 0.0, -0.01), (b - 0.014, L + 0.04, TT), ROOF, M=Mt)
# ridge cap: square bar turned 45 degrees
box('Ridge', (-XR - 0.02, -0.13, -0.13), (XR + 0.02, 0.13, 0.13), ROOF, 0.035, 2,
    M=Matrix.Translation((0, 0, ZT0 + 0.03)) @ Matrix.Rotation(math.pi / 4, 4, 'X'))
# cream rake boards under the gable edges
for sx in (-1, 1):
    for sy in (-1, 1):
        R = roof_frame(sy)
        box('Rake', (sx * HX - 0.06, 0.05, -TS - 0.16), (sx * HX + 0.06, SL - 0.08, -TS + 0.01), TRIM, 0.015, 1, M=R)

# ---------------------------------------------------------------- porch (gabled canopy on two columns, steps)
PW, PD = 1.45, 1.35          # half width, depth in front of the wall
PY0 = -HY - PD
PK = 0.80; PH = 2.72         # porch pitch, eave height
PZU = PH + PW * PK           # underside at porch ridge
PA = math.atan(PK)
box('Landing', (-PW + 0.05, PY0 + 0.05, 0.0), (PW - 0.05, -HY, PL), CONC, 0.025, 2)
box('Step', (-1.0, PY0 - 0.42, 0.0), (1.0, PY0 + 0.1, PL / 2), CONC, 0.025, 2)
for sx in (-1, 1):
    cx = sx * (PW - 0.27); cy = PY0 + 0.3
    box('ColBase', (cx - 0.17, cy - 0.17, PL), (cx + 0.17, cy + 0.17, PL + 0.28), TRIM, 0.02, 2)
    box('Col', (cx - 0.12, cy - 0.12, PL + 0.28), (cx + 0.12, cy + 0.12, PH - 0.30), TRIM, 0.02, 2)
    box('ColCap', (cx - 0.16, cy - 0.16, PH - 0.30), (cx + 0.16, cy + 0.16, PH - 0.20), TRIM, 0.02, 2)
    box('Pilaster', (sx * (PW - 0.27) - 0.1, -HY - 0.06, PL), (sx * (PW - 0.27) + 0.1, -HY, PH - 0.2), TRIM, 0.015, 1)
# beam ring and pediment
box('BeamF', (-PW + 0.05, PY0 + 0.12, PH - 0.22), (PW - 0.05, PY0 + 0.48, PH), TRIM, 0.02, 2)
for sx in (-1, 1):
    box('BeamS', (sx * (PW - 0.27) - 0.13, PY0 + 0.15, PH - 0.22), (sx * (PW - 0.27) + 0.13, -HY, PH), TRIM, 0.02, 2)
ped = prism('Pediment', [(-PW + 0.1, PH), (PW - 0.1, PH), (0, PZU - 0.04)], PY0 + 0.25, -HY + 0.2, TRIM, axis='Y')
cut = [box('PGroove', (-PW, PY0 + 0.15, z), (PW, PY0 + 0.262, z + 0.025), TRIM) for z in (PH + 0.32, PH + 0.62)]
boolean(ped, cut)
for sx in (-1, 1):   # porch roof slabs, run back into the main roof
    xo = sx * (PW + 0.18)
    pts = [(0, PZU), (0, PZU + 0.15), (xo, PZU + 0.15 - (PW + 0.18) * PK), (xo, PZU - (PW + 0.18) * PK)]
    if sx > 0: pts = pts[::-1]
    prism('PorchRoof', pts, PY0 - 0.12, -1.85, ROOF, 0.03, 2, axis='Y')
for sx in (-1, 1):   # tile courses on the porch slopes
    c, sn = math.cos(PA), math.sin(PA)
    R = Matrix(((0, sx * c, sx * sn, 0), (-sx, 0, 0, 0), (0, -sn, c, PZU + 0.15), (0, 0, 0, 1)))
    xa, xb = sorted((-sx * (PY0 - 0.12), -sx * -1.85))
    PSL = (PW + 0.18) / c; NC = 3; L = (PSL + 0.02) / NC; tilt = math.atan(0.03 / L)
    for i in range(NC):
        s0 = i * L - 0.03 if i else 0.0
        Mt = R @ Matrix.Translation((0, s0, 0)) @ Matrix.Rotation(tilt, 4, 'X')
        off = (i % 2) * 0.35
        xs = [xa] + [x for x in [xa + off + k * 0.7 for k in range(1, 8)] if xa + 0.2 < x < xb - 0.2] + [xb]
        for a, b in zip(xs[:-1], xs[1:]):
            box('PTile', (a + 0.012, 0.0, -0.01), (b - 0.012, L + 0.03, 0.045), ROOF, M=Mt)
box('PRidge', (-0.1, PY0 - 0.14, -0.1), (0.1, -1.85, 0.1), ROOF, 0.03, 2,
    M=Matrix.Translation((0, 0, PZU + 0.19)) @ Matrix.Rotation(math.pi / 4, 4, 'Y'))

# ---------------------------------------------------------------- chimney on the back slope, right end
CX, CY, CW, CDp = 3.45, 0.25, 0.95, 0.72
ch = box('Chimney', (CX - CW / 2, CY - CDp / 2, 3.4), (CX + CW / 2, CY + CDp / 2, 5.45), BRICK, 0.015, 1)
cut = []
z = 3.6
while z < 5.4:
    cut.append(box('Course', (CX - CW / 2 - 0.1, CY - CDp / 2 - 0.1, z), (CX + CW / 2 + 0.1, CY + CDp / 2 + 0.1, z + 0.022), BRICK))
    z += 0.16
boolean(ch, cut)
# inner core so the grooves read as mortar lines, not see-through slots
box('ChimCore', (CX - CW / 2 + 0.011, CY - CDp / 2 + 0.011, 3.4), (CX + CW / 2 - 0.011, CY + CDp / 2 - 0.011, 5.45), BRICK)
box('ChimCap', (CX - CW / 2 - 0.07, CY - CDp / 2 - 0.07, 5.45), (CX + CW / 2 + 0.07, CY + CDp / 2 + 0.07, 5.60), CONC, 0.025, 2)
box('ChimTop', (CX - CW / 2 + 0.03, CY - CDp / 2 + 0.03, 5.60), (CX + CW / 2 - 0.03, CY + CDp / 2 - 0.03, 5.66), CONC, 0.015, 1)

finish('House')
studio()
shoot('render-34', (-11.0, -19.5, 4.6), (0.3, 0, 2.5), 40)
shoot('render-front', (0, -40, 2.75), (0, 0, 2.75), ortho=12.4)

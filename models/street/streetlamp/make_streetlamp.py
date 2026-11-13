# Original 7 m street lamp for the VR Director previs library. Round 2, Fable.
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_streetlamp.py -- <out dir>
# 1 unit = 1 m, front toward -Y (the arm reaches over the road toward -Y), up +Z, origin on the ground at the pole centre.
# Measured from ref-side.png (130 px per metre at 7 m): flange, octagonal bell, octagonal tapered pole with a step at 3.75 m,
# collar at 5.6 m, arm bend radius 0.75 m, head ending 3.6 m out. Section thicknesses are about 88% of the stylised
# reference so the pole reads as a real street lamp at eye level in VR (see report).
import bpy, sys, math, bmesh
from mathutils import Vector, Matrix

OUT = sys.argv[sys.argv.index('--') + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

MATS = []
def mat(name, rgb, rough=0.6, metal=0.0, emit=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*rgb, 1); b.inputs['Roughness'].default_value = rough; b.inputs['Metallic'].default_value = metal
    if emit: b.inputs['Emission Color'].default_value = (*rgb, 1); b.inputs['Emission Strength'].default_value = emit
    m.diffuse_color = (*rgb, 1); MATS.append(m); return len(MATS) - 1
METAL = mat('Lamp_Metal', (0.20, 0.21, 0.225), 0.6, 0.15)
DARK = mat('Lamp_DarkMetal', (0.115, 0.12, 0.13), 0.55, 0.2)
LENS = mat('Lamp_Lens', (0.95, 0.80, 0.55), 0.3, 0.0, 0.85)
BOLT = mat('Lamp_Bolt', (0.30, 0.31, 0.32), 0.45, 0.4)

def frame(p, n): return Matrix.Translation(p) @ Vector(n).normalized().to_track_quat('Z', 'Y').to_matrix().to_4x4()
def merge(bm, t, mi, M=None):
    vm = {v: bm.verts.new(M @ v.co if M else v.co) for v in t.verts}
    for f in t.faces: bm.faces.new([vm[v] for v in f.verts]).material_index = f.material_index if mi is None else mi
    t.free()
def cbox(bm, size, M, mi, bevel=0.0, segs=1):
    t = bmesh.new(); bmesh.ops.create_cube(t, size=1.0)
    for v in t.verts: v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    if bevel: bmesh.ops.bevel(t, geom=t.edges[:], offset=bevel, segments=segs, profile=0.5, affect='EDGES')
    merge(bm, t, mi, M)
def lathe(bm, prof, segs, mi, M=Matrix.Identity(4)):
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
def tube(bm, pts, r, segs, mi):
    pts = [Vector(p) for p in pts]; n = len(pts); rings = []; nrm = Vector((1, 0, 0))
    for i in range(n):
        t = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized(); nrm = (nrm - t * nrm.dot(t)).normalized(); b = t.cross(nrm)
        rings.append([bm.verts.new(pts[i] + (nrm * math.cos(2 * math.pi * k / segs) + b * math.sin(2 * math.pi * k / segs)) * r) for k in range(segs)])
    for A, B in zip(rings, rings[1:]):
        for k in range(segs): bm.faces.new((A[k], A[(k + 1) % segs], B[(k + 1) % segs], B[k])).material_index = mi
    bm.faces.new(rings[0][::-1]).material_index = mi; bm.faces.new(rings[-1]).material_index = mi

bm = bmesh.new()
OCT = Matrix.Rotation(math.radians(22.5), 4, 'Z')                 # octagon with a flat facing -Y

# ---- base: stepped flange, anchor bolts with washers, octagonal bell
lathe(bm, [(0, 0), (0.64, 0), (0.66, 0.02), (0.66, 0.07), (0.64, 0.09), (0.50, 0.09), (0.48, 0.11), (0.48, 0.14), (0, 0.14)], 28, METAL)
for k in range(4):
    a = math.radians(45 + 90 * k); p = Vector((math.cos(a) * 0.57, math.sin(a) * 0.57, 0.09))
    lathe(bm, [(0.075, 0), (0.075, 0.012), (0, 0.012)], 12, BOLT, Matrix.Translation(p))
    lathe(bm, [(0.048, 0.012), (0.048, 0.05), (0.040, 0.06), (0, 0.06)], 6, BOLT, Matrix.Translation(p) @ Matrix.Rotation(a, 4, 'Z'))
    lathe(bm, [(0.022, 0.06), (0.022, 0.085), (0, 0.085)], 8, BOLT, Matrix.Translation(p))
lathe(bm, [(0.39, 0.14), (0.40, 0.17), (0.40, 0.52), (0.36, 0.58), (0.30, 0.60)], 8, METAL, OCT)

# ---- pole: octagonal lower shaft, step ring, slimmer upper shaft, round collar
def pole_r(z): return 0.295 - (0.295 - 0.185) * (z - 0.56) / (3.75 - 0.56)
lathe(bm, [(pole_r(0.56), 0.56), (pole_r(3.75), 3.75)], 8, METAL, OCT)
lathe(bm, [(0.185, 3.70), (0.205, 3.72), (0.205, 3.80), (0.18, 3.83), (0.158, 3.84)], 8, DARK, OCT)
lathe(bm, [(0.158, 3.84), (0.128, 5.56)], 8, METAL, OCT)
lathe(bm, [(0.128, 5.52), (0.175, 5.55), (0.18, 5.58), (0.18, 5.80), (0.175, 5.83), (0.10, 5.86)], 16, DARK)
# access door on the front flat, with two screws
ap = pole_r(1.15) * math.cos(math.radians(22.5))
cbox(bm, (0.17, 0.026, 0.44), Matrix.Translation((0, -ap, 1.15)), DARK, 0.008)
for dz in (-0.16, 0.16): lathe(bm, [(0.012, 0), (0.012, 0.008), (0, 0.008)], 6, BOLT, frame((0, -ap - 0.013, 1.15 + dz), (0, -1, 0)))

# ---- arm: round tube, 0.75 m bend, then straight out to the head
AR, BR, ZA = 0.095, 0.75, 6.80
pts = [(0, 0, 5.80), (0, 0, ZA - BR)]
for k in range(1, 13):
    a = math.radians(90) * k / 12; pts.append((0, -BR * (1 - math.cos(a)), ZA - BR + BR * math.sin(a)))
Y_HEAD = -2.0
pts.append((0, Y_HEAD - 0.1, ZA))
tube(bm, pts, AR, 14, METAL)

# ---- lamp head: socket collar, lofted housing (chamfered section, widening then tapering), top cover, recessed lens
lathe(bm, [(0.10, 0), (0.135, 0.015), (0.135, 0.22), (0.12, 0.24)], 14, DARK, frame((0, Y_HEAD + 0.12, ZA), (0, -1, 0)))
SEC = [(0.00, 0.15, 6.945, 6.675), (0.18, 0.32, 6.990, 6.660), (0.60, 0.375, 7.000, 6.660), (1.30, 0.375, 7.000, 6.660),
       (1.56, 0.325, 6.960, 6.690), (1.65, 0.27, 6.920, 6.730)]          # (distance along the head, half width, top z, bottom z)
c = 0.045; loops = []
for sd, hw_, zt, zb in SEC:
    y = Y_HEAD - sd
    loops.append([bm.verts.new((x, y, z)) for x, z in ((hw_ - c * 1.6, zt), (-hw_ + c * 1.6, zt), (-hw_, zt - c), (-hw_, zb + c * 0.6),
                                                       (-hw_ + c * 0.6, zb), (hw_ - c * 0.6, zb), (hw_, zb + c * 0.6), (hw_, zt - c))])
for A, B in zip(loops, loops[1:]):
    for k in range(8): bm.faces.new((A[k], A[(k + 1) % 8], B[(k + 1) % 8], B[k])).material_index = DARK
bm.faces.new(loops[0][::-1]).material_index = DARK; bm.faces.new(loops[-1]).material_index = DARK
cbox(bm, (0.44, 0.86, 0.03), Matrix.Translation((0, Y_HEAD - 0.90, 7.008)), METAL, 0.01)                 # top cover plate
lathe(bm, [(0.045, 0), (0.045, 0.05), (0.03, 0.065), (0, 0.065)], 10, BOLT, Matrix.Translation((0, Y_HEAD - 0.30, 6.99)))  # photocell
# lens tray under the housing: rim, recess walls, emissive lens face
y0, y1, hx, zt, zr, zl, ins = Y_HEAD - 0.26, Y_HEAD - 1.50, 0.32, 6.68, 6.635, 6.595, 0.04
def rect(hx_, ya, yb, z): return [bm.verts.new(p) for p in ((hx_, ya, z), (-hx_, ya, z), (-hx_, yb, z), (hx_, yb, z))]
T, O, I, L = rect(hx, y0, y1, zt), rect(hx, y0, y1, zr), rect(hx - ins, y0 - ins, y1 + ins, zr), rect(hx - ins - 0.05, y0 - ins - 0.07, y1 + ins + 0.07, zl)   # lens drops below the rim as a shallow prism
for A, B, mi in ((T, O, DARK), (O, I, DARK), (I, L, LENS)):
    for k in range(4): bm.faces.new((A[k], A[(k + 1) % 4], B[(k + 1) % 4], B[k])).material_index = mi
bm.faces.new(L).material_index = LENS
bm.faces.new(T[::-1]).material_index = DARK

bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
n = sum(len(f.verts) - 2 for f in bm.faces)
me = bpy.data.meshes.new('StreetLamp_Mesh'); bm.to_mesh(me); bm.free()
for m in MATS: me.materials.append(m)
lamp = bpy.data.objects.new('StreetLamp_Mesh', me); scene.collection.objects.link(lamp)
with bpy.context.temp_override(active_object=lamp, object=lamp, selected_objects=[lamp], selected_editable_objects=[lamp]):
    bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
root = bpy.data.objects.new('StreetLamp', None); scene.collection.objects.link(root); lamp.parent = root
lo = [min(v.co[a] for v in me.vertices) for a in range(3)]; hi = [max(v.co[a] for v in me.vertices) for a in range(3)]
print(f'[StreetLamp] triangles {n}, materials {len({p.material_index for p in me.polygons})}, bbox {hi[0]-lo[0]:.2f} x {hi[1]-lo[1]:.2f} x {hi[2]-lo[2]:.2f} m, z {lo[2]:.3f}..{hi[2]:.3f}')
for o in scene.objects: o.select_set(False)
root.select_set(True); lamp.select_set(True)
bpy.ops.export_scene.fbx(filepath=f'{OUT}/StreetLamp.fbx', use_selection=True, apply_unit_scale=True,
                         apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)

# ---- previews (studio grey like the references)
world = bpy.data.worlds.new('W'); scene.world = world; world.use_nodes = True
nt = world.node_tree; bg = nt.nodes['Background']; bg.inputs['Color'].default_value = (0.72, 0.72, 0.72, 1); bg.inputs['Strength'].default_value = 0.6
bg2 = nt.nodes.new('ShaderNodeBackground'); bg2.inputs['Color'].default_value = (0.72, 0.72, 0.72, 1)
lp = nt.nodes.new('ShaderNodeLightPath'); mx = nt.nodes.new('ShaderNodeMixShader')
nt.links.new(lp.outputs['Is Camera Ray'], mx.inputs[0]); nt.links.new(bg.outputs[0], mx.inputs[1]); nt.links.new(bg2.outputs[0], mx.inputs[2])
nt.links.new(mx.outputs[0], nt.nodes['World Output'].inputs['Surface'])
bpy.ops.object.light_add(type='SUN', location=(0, 0, 30)); sun = bpy.context.active_object
sun.data.energy = 2.3; sun.rotation_euler = (math.radians(55), 0, math.radians(-60)); sun.data.angle = math.radians(12)
scene.render.engine = 'BLENDER_EEVEE'; scene.render.resolution_x, scene.render.resolution_y = 1672, 941
scene.view_settings.view_transform = 'Standard'
cam_data = bpy.data.cameras.new('Cam'); cam = bpy.data.objects.new('Cam', cam_data); scene.collection.objects.link(cam); scene.camera = cam
def shoot(name, loc, target, lens=50, ortho=None):
    cam.location = loc; d = Vector(target) - Vector(loc); cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    if ortho: cam_data.type = 'ORTHO'; cam_data.ortho_scale = ortho
    else: cam_data.type = 'PERSP'; cam_data.lens = lens
    scene.render.filepath = f'{OUT}/{name}.png'; bpy.ops.render.render(write_still=True)
shoot('render-34', (-9.0, -6.3, 3.6), (0, -1.25, 3.55), 28)
shoot('render-side', (-40, -0.93, 3.51), (0, -0.93, 3.51), ortho=12.9)

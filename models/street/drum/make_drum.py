# 200-litre steel drum, own design, previs-library detail (round 2, fable). Second root Drum_Fallen lies on its side.
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_drum.py -- <out dir>
# 1 unit = 1 m, up +Z, origin on the ground at the centre. 0.58 m diameter, 0.88 m tall.
# One lathed bmesh with fixed material indices (no join step). Rust is flat colour: the shell is a grid of
# cells, a periodic noise picks paint or rust per cell, then coplanar cells of one material are dissolved.
import bpy, bmesh, sys, math, os, shutil, subprocess
from mathutils import Vector, Matrix

OUT = sys.argv[sys.argv.index('--') + 1]
HERE = os.path.dirname(os.path.abspath(__file__))
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

MATS = []
def mat(name, rgb, rough=0.8, metal=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*rgb, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    m.diffuse_color = (*rgb, 1)
    MATS.append(m); return len(MATS) - 1

PAINT = mat('Paint', (0.036, 0.095, 0.220), 0.7, 0.1)
RUST  = mat('Rust', (0.190, 0.064, 0.028), 0.9)
RUSTD = mat('RustDark', (0.115, 0.045, 0.025), 0.9)
ZINC  = mat('Bung', (0.300, 0.262, 0.205), 0.5, 0.5)

bm = bmesh.new()
def lathe(profile, segs, mi, M=None):
    """profile: (r, z) from the bottom centre, outside going up, to the top centre; mi is an index or f(i, k, angle, z)"""
    M = M if M is not None else Matrix.Identity(4)
    for k in range(len(profile) - 1):
        (r0, z0), (r1, z1) = profile[k], profile[k + 1]
        for i in range(segs):
            a0, a1 = 2 * math.pi * i / segs, 2 * math.pi * (i + 1) / segs
            am = (a0 + a1) / 2
            pts = []
            for r, z, a in ((r0, z0, a0), (r0, z0, a1), (r1, z1, a1), (r1, z1, a0)):
                p = M @ Vector((r * math.cos(a), r * math.sin(a), z))
                if not pts or (p - pts[-1]).length > 1e-6: pts.append(p)
            if len(pts) > 2 and (pts[0] - pts[-1]).length < 1e-6: pts.pop()
            if len(pts) < 3: continue
            n = Vector((math.cos(am) * (z1 - z0), math.sin(am) * (z1 - z0), -(r1 - r0)))
            f = bm.faces.new([bm.verts.new(p) for p in pts])
            f.material_index = mi(i, k, am, (z0 + z1) / 2) if callable(mi) else mi
            f.normal_update()
            if f.normal.dot(n) < 0: f.normal_flip()

def h3(i, j, k):
    n = (i * 374761393 + j * 668265263 + k * 1442695041) & 0xffffffff
    n = ((n ^ (n >> 13)) * 1274126177) & 0xffffffff
    return ((n ^ (n >> 16)) & 0xffff) / 65535.0
def vnoise(x, y, seed=0):
    xi, yi = math.floor(x), math.floor(y); fx, fy = x - xi, y - yi
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b, c, d = h3(xi, yi, seed), h3(xi + 1, yi, seed), h3(xi, yi + 1, seed), h3(xi + 1, yi + 1, seed)
    return (a + (b - a) * fx) * (1 - fy) + (c + (d - c) * fx) * fy
def ring(a, freq, seed):                     # noise that wraps cleanly around the drum
    return vnoise(8 + freq * math.cos(a), 8 + freq * math.sin(a), seed)

# ------------------------------------------------------------------ profile
N = 40
RB, RR, RC, HT = 0.272, 0.288, 0.290, 0.880      # body, rib crest, chime (rim) radius, height
LID = 0.858
BANDS = [(0.040, 0.275), (0.320, 0.565), (0.610, 0.840)]     # painted body panels between rims and ribs
def rows(z0, z1, n): return [(RB, z0 + (z1 - z0) * i / n) for i in range(n + 1)]
def rib(z): return [(0.283, z + 0.008), (RR, z + 0.0225), (0.283, z + 0.037)]
profile = ([(0.0, 0.010), (0.262, 0.010), (0.270, 0.0), (0.284, 0.0), (RC, 0.010), (RC, 0.024), (0.284, 0.034)]      # recessed base + bottom chime
           + rows(*BANDS[0], 7) + rib(0.275) + rows(*BANDS[1], 7) + rib(0.565) + rows(*BANDS[2], 7)
           + [(0.284, 0.846), (RC, 0.856), (RC, 0.870), (0.284, HT), (0.271, HT), (0.266, LID + 0.004),              # top chime, lip, inner wall
              (0.200, LID), (0.110, LID), (0.0, LID)])                                               # lid in three rings

def rustc(a, z):                               # two rust tones so big patches are not one flat blob
    return RUSTD if vnoise(8 + 2.6 * math.cos(a), 8 + 2.6 * math.sin(a) + z * 5.0, 9) > 0.62 else RUST

def shell_mat(i, k, a, z):
    (r0, z0), (r1, z1) = profile[k], profile[k + 1]
    if z1 <= 0.012 and r1 <= 0.27: return RUSTD                           # underside
    if z < 0.04 or (z > 0.84 and (r0 > 0.268 or r1 > 0.268)):   # chimes
        return PAINT if (0.012 < z < 0.87 and ring(a, 2.2, 1 if z < 0.4 else 2) > 0.64) else rustc(a, z)
    if z0 >= LID - 1e-6 and r0 <= 0.27:                                    # lid rings
        if r1 >= 0.2: return rustc(a, z) if ring(a, 1.6, 3) > 0.62 else PAINT
        if r1 >= 0.11: return rustc(a, z) if ring(a, 1.6, 3) > 0.78 else PAINT
        return PAINT
    for b, (b0, b1) in enumerate(BANDS):
        if b0 - 1e-6 <= z0 and z1 <= b1 + 1e-6:
            lo, hi = z - b0, b1 - z
            if lo < 0.30 * max(0.0, ring(a, 3.6, 10 + b) - 0.52) * (0.3 + 1.4 * ring(a, 7.0, 20 + b)): return rustc(a, z)
            if hi < 0.28 * max(0.0, ring(a, 3.6, 30 + b) - 0.54) * (0.3 + 1.4 * ring(a, 7.0, 40 + b)): return rustc(a, z)
            if vnoise(8 + 3.2 * math.cos(a), 8 + 3.2 * math.sin(a) + z * 9.0, 50) > 0.92: return rustc(a, z)
            return PAINT
    crest = max(r0, r1) > RR - 1e-6                    # ribs: worn crest, painted flanks
    thr = 0.50 if crest else 0.74
    return rustc(a, z) if ring(a, 3.0, 60 + (1 if z > 0.45 else 0)) > thr else PAINT

lathe(profile, N, shell_mat)

# ------------------------------------------------------------------ bung (2 inch, octagonal cap on a flange) and small vent plug
BX, BY = 0.150, 0.075
lathe([(0.054, 0.0), (0.054, 0.010), (0.038, 0.012)], 16, lambda i, k, a, z: RUST if (k == 0 and i % 5 == 0) else ZINC, Matrix.Translation((BX, BY, LID)))
lathe([(0.036, 0.010), (0.036, 0.034), (0.029, 0.041), (0.0, 0.041)], 8, ZINC, Matrix.Translation((BX, BY, LID)) @ Matrix.Rotation(math.pi / 8, 4, 'Z'))
lathe([(0.021, 0.0), (0.021, 0.012), (0.014, 0.016), (0.0, 0.016)], 6, RUSTD, Matrix.Translation((-0.13, -0.10, LID)))

# ------------------------------------------------------------------ finish
bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.0002)
bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(0.5), verts=bm.verts[:], edges=bm.edges[:], delimit={'MATERIAL'})
bmesh.ops.dissolve_degenerate(bm, dist=0.0001, edges=bm.edges[:])
bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
me = bpy.data.meshes.new('Drum_Mesh'); bm.to_mesh(me); bm.free()
for m in MATS: me.materials.append(m)
for p in me.polygons: p.use_smooth = True
me.set_sharp_from_angle(angle=math.radians(50))
me.validate(); me.update()
drum = bpy.data.objects.new('Drum_Mesh', me); scene.collection.objects.link(drum)
wn = drum.modifiers.new('WN', 'WEIGHTED_NORMAL'); wn.mode = 'FACE_AREA'; wn.weight = 60; wn.keep_sharp = True
with bpy.context.temp_override(object=drum, active_object=drum, selected_objects=[drum]):
    bpy.ops.object.modifier_apply(modifier='WN')
root = bpy.data.objects.new('Drum', None); scene.collection.objects.link(root); drum.parent = root

# Drum_Fallen: the same mesh data, lying along X, rolled so the bung sits low on the visible end
fallen = bpy.data.objects.new('Drum_Fallen_Mesh', me); scene.collection.objects.link(fallen)
rootF = bpy.data.objects.new('Drum_Fallen', None); scene.collection.objects.link(rootF); fallen.parent = rootF
fallen.matrix_local = Matrix.Translation((-HT / 2, 0, RC)) @ Matrix.Rotation(math.radians(90), 4, 'Y') @ Matrix.Rotation(math.radians(205), 4, 'Z')
rootF.location = (1.4, 0, 0)

tris = sum(len(p.vertices) - 2 for p in me.polygons)
cs = [v.co for v in me.vertices]
dims = [max(c[i] for c in cs) - min(c[i] for c in cs) for i in range(3)]
print(f'[Drum] triangles {tris} (Drum_Fallen instances the same mesh), materials {len(me.materials)} '
      f'(used {len({p.material_index for p in me.polygons})}), size {dims[0]:.3f} x {dims[1]:.3f} x {dims[2]:.3f} m, min z {min(c[2] for c in cs):.3f}')

for o in scene.objects: o.select_set(False)
for o in (root, drum, rootF, fallen): o.select_set(True)
bpy.ops.export_scene.fbx(filepath=f'{OUT}/Drum.fbx', use_selection=True, apply_unit_scale=True,
                         apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)

# ------------------------------------------------------------------ previews
world = bpy.data.worlds.new('W'); scene.world = world; world.use_nodes = True
nt = world.node_tree; nt.nodes.clear()
o = nt.nodes.new('ShaderNodeOutputWorld'); mx = nt.nodes.new('ShaderNodeMixShader'); lp = nt.nodes.new('ShaderNodeLightPath')
amb = nt.nodes.new('ShaderNodeBackground'); amb.inputs['Color'].default_value = (0.80, 0.82, 0.86, 1); amb.inputs['Strength'].default_value = 0.45
bg = nt.nodes.new('ShaderNodeBackground'); bg.inputs['Color'].default_value = (0.76, 0.76, 0.76, 1); bg.inputs['Strength'].default_value = 1.0
nt.links.new(lp.outputs['Is Camera Ray'], mx.inputs['Fac']); nt.links.new(amb.outputs[0], mx.inputs[1]); nt.links.new(bg.outputs[0], mx.inputs[2])
nt.links.new(mx.outputs[0], o.inputs['Surface'])
sun_d = bpy.data.lights.new('Sun', 'SUN'); sun_d.use_shadow = True; sun_d.energy = 3.4; sun_d.angle = math.radians(6)
sun = bpy.data.objects.new('Sun', sun_d); scene.collection.objects.link(sun)
sun.rotation_euler = Vector((-0.35, -0.65, 0.67)).to_track_quat('Z', 'Y').to_euler()
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x, scene.render.resolution_y = 1672, 941
scene.view_settings.view_transform = 'Standard'
for k, v in (('taa_render_samples', 48), ('use_raytracing', True), ('use_shadows', True)):
    try: setattr(scene.eevee, k, v)
    except Exception as e: print('eevee', k, e)
cam_data = bpy.data.cameras.new('Cam'); cam = bpy.data.objects.new('Cam', cam_data); scene.collection.objects.link(cam); scene.camera = cam
def shoot(name, loc, target, lens=50, ortho=None):
    cam.location = loc
    d = Vector(target) - Vector(loc); cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    if ortho: cam_data.type = 'ORTHO'; cam_data.ortho_scale = ortho
    else: cam_data.type = 'PERSP'; cam_data.lens = lens
    scene.render.filepath = f'{OUT}/{name}.png'; bpy.ops.render.render(write_still=True)
fallen.hide_render = True
shoot('render-34', (0.35, -3.05, 1.72), (0, 0, 0.43), 60)
shoot('render-side', (0, -12, 0.455), (0, 0, 0.455), ortho=1.75)
fallen.hide_render = False; drum.hide_render = True
shoot('render-fallen', (1.4 + 1.7, -2.6, 1.2), (1.4, 0, 0.29), 60)
drum.hide_render = False

ff = shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg'
ref = os.path.normpath(os.path.join(HERE, '..', '..', 'drum'))
if os.path.exists(ff) and os.path.exists(f'{ref}/ref-34.png'):
    subprocess.run([ff, '-y', '-loglevel', 'error', '-i', f'{ref}/ref-34.png', '-i', f'{OUT}/render-34.png', '-i', f'{ref}/ref-side.png',
                    '-i', f'{OUT}/render-side.png', '-filter_complex',
                    '[0]scale=1672:941[a];[1]scale=1672:941[b];[2]scale=1672:941[c];[3]scale=1672:941[d];[a][b]hstack[t];[c][d]hstack[u];[t][u]vstack,scale=2400:-2',
                    '-q:v', '3', f'{OUT}/compare.jpg'])

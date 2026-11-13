# Previs library model, round 2 (Fable build). Own design, no brands. Headless Blender 5.1:
#   /Applications/Blender.app/Contents/MacOS/Blender -b --python <this file> -- <out dir>
# Convention: 1 unit = 1 m, front toward -Y, up +Z, origin on the ground at the centre.
# d = distance in metres from the front-most point; Y(d) turns it into scene Y.
# ==== KIT ==== (shared helpers; the model starts at the MODEL marker)
import bpy, sys, math, bmesh
from math import radians, sin, cos, pi
from mathutils import Vector, Matrix, Euler

OUT = sys.argv[sys.argv.index('--') + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
L = 4.0
def Y(d): return d - L / 2

MATS = {}
def mat(name, rgb, rough=0.75, metal=0.0, emit=0.0, alpha=1.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*rgb, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if emit:
        b.inputs['Emission Color'].default_value = (*rgb, 1)
        b.inputs['Emission Strength'].default_value = emit
    if alpha < 1:
        b.inputs['Alpha'].default_value = alpha
        m.surface_render_method = 'BLENDED'
    m.diffuse_color = (*rgb, alpha)
    MATS[name] = m
    return m

parts = []                      # every object that ends up in the final mesh
XF = [Matrix.Identity(4)]       # transform stack (used for wheels)

def _mk(name, bm, m, mx=None, bevel=0.0, segs=2, angle=30):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    full = XF[-1] @ mx if mx is not None else XF[-1]
    me.transform(full)
    o = bpy.data.objects.new(name, me); scene.collection.objects.link(o)
    if m is not None:
        o['m'] = m.name; parts.append(o)
    if bevel: add_bevel(o, bevel, segs, angle)
    return o

def add_bevel(o, width, segs=2, angle=30):
    b = o.modifiers.new('bevel', 'BEVEL'); b.width = width; b.segments = segs
    b.limit_method = 'ANGLE'; b.angle_limit = radians(angle)

def cut(target, *cutters):
    for c in cutters:
        md = target.modifiers.new('cut', 'BOOLEAN'); md.operation = 'DIFFERENCE'; md.object = c; md.solver = 'EXACT'

def box(name, c, size, m, bevel=0.0, segs=2, rot=None):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1)
    for v in bm.verts: v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    mx = Matrix.Translation(c)
    if rot: mx = mx @ Euler(rot).to_matrix().to_4x4()
    return _mk(name, bm, m, mx, bevel, segs)

def dbox(name, d0, d1, x0, x1, z0, z1, m, bevel=0.0, segs=2):
    return box(name, ((x0 + x1) / 2, Y((d0 + d1) / 2), (z0 + z1) / 2), (abs(x1 - x0), abs(d1 - d0), abs(z1 - z0)), m, bevel, segs)

def cyl(name, c, r, depth, axis, m, verts=32, bevel=0.0, segs=2, r2=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=verts, radius1=r, radius2=r if r2 is None else r2, depth=depth)
    rot = {'X': (0, pi / 2, 0), 'Y': (-pi / 2, 0, 0), 'Z': (0, 0, 0)}[axis]
    return _mk(name, bm, m, Matrix.Translation(c) @ Euler(rot).to_matrix().to_4x4(), bevel, segs)

def loft(name, secs, m, **kw):
    # secs: [(d, ring)], ring = [(x, z) or (x, z, extra_d)], same point count in every ring
    bm = bmesh.new(); rings = []
    for d, ring in secs:
        rings.append([bm.verts.new((p[0], Y(d + (p[2] if len(p) > 2 else 0)), p[1])) for p in ring])
    n = len(rings[0])
    for a, b in zip(rings, rings[1:]):
        for i in range(n): bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
    bm.faces.new(rings[0]); bm.faces.new(list(reversed(rings[-1])))
    return _mk(name, bm, m, None, **kw)

def prism_x(name, pts, x0, x1, m, **kw):
    # polygon given as (d, z), extruded across X
    bm = bmesh.new()
    a = [bm.verts.new((x0, Y(d), z)) for d, z in pts]; b = [bm.verts.new((x1, Y(d), z)) for d, z in pts]
    n = len(pts)
    for i in range(n): bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
    bm.faces.new(a); bm.faces.new(list(reversed(b)))
    return _mk(name, bm, m, None, **kw)

def prism_y(name, pts, d0, d1, m, **kw):
    # polygon given as (x, z), extruded along the length
    bm = bmesh.new()
    a = [bm.verts.new((x, Y(d0), z)) for x, z in pts]; b = [bm.verts.new((x, Y(d1), z)) for x, z in pts]
    n = len(pts)
    for i in range(n): bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
    bm.faces.new(a); bm.faces.new(list(reversed(b)))
    return _mk(name, bm, m, None, **kw)

def strip_x(name, outer, inner, x0, x1, m, closed=False, **kw):
    # band between two (d, z) polylines with matching points, extruded across X (arch lips, window frames)
    bm = bmesh.new(); n = len(outer)
    V = lambda pts, x: [bm.verts.new((x, Y(d), z)) for d, z in pts]
    o0, i0, o1, i1 = V(outer, x0), V(inner, x0), V(outer, x1), V(inner, x1)
    for i in range(n if closed else n - 1):
        j = (i + 1) % n
        bm.faces.new((o0[i], o0[j], i0[j], i0[i])); bm.faces.new((o1[i], o1[j], i1[j], i1[i]))
        bm.faces.new((o0[i], o0[j], o1[j], o1[i])); bm.faces.new((i0[i], i0[j], i1[j], i1[i]))
    if not closed:
        for k in (0, n - 1): bm.faces.new((o0[k], i0[k], i1[k], o1[k]))
    return _mk(name, bm, m, None, **kw)

def pane(name, pts, m, thick=0.008, **kw):
    # thin two-sided slab from a planar 3D polygon (glass, seams on sloped surfaces)
    P = [Vector(p) for p in pts]
    nrm = (P[1] - P[0]).cross(P[2] - P[0]).normalized() * (thick / 2)
    bm = bmesh.new()
    a = [bm.verts.new(p + nrm) for p in P]; b = [bm.verts.new(p - nrm) for p in P]
    n = len(P)
    for i in range(n): bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
    bm.faces.new(a); bm.faces.new(list(reversed(b)))
    return _mk(name, bm, m, None, **kw)

def bar(name, p0, p1, w, h, m, bevel=0.0):
    p0, p1 = Vector(p0), Vector(p1); dv = p1 - p0
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1)
    for v in bm.verts: v.co = Vector((v.co.x * w, v.co.y * h, v.co.z * dv.length))
    mx = Matrix.Translation((p0 + p1) / 2) @ dv.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    return _mk(name, bm, m, mx, bevel, 1)

def lathe(name, prof, m, segs=32, mx=None, **kw):
    # closed profile [(radius, x)] revolved around the X axis
    bm = bmesh.new(); rings = []
    for k in range(segs):
        a = 2 * pi * k / segs
        rings.append([bm.verts.new((x, r * cos(a), r * sin(a))) for r, x in prof])
    n = len(prof)
    for k in range(segs):
        A, B = rings[k], rings[(k + 1) % segs]
        for i in range(n): bm.faces.new((A[i], A[(i + 1) % n], B[(i + 1) % n], B[i]))
    return _mk(name, bm, m, mx, **kw)

def torus(name, c, axis, R, r, m, seg=20, sub=6):
    prof = [(R + r * cos(2 * pi * k / sub), r * sin(2 * pi * k / sub)) for k in range(sub)]
    mx = Matrix.Translation(c) @ Vector(axis).to_track_quat('X', 'Z').to_matrix().to_4x4()
    return lathe(name, prof, m, seg, mx)

def finish(name, seat, recolor=None, cam34=None, target=(0, 0, 1), lens=60, side_scale=5.0, side_z=1.0, side_y=0.0):
    """Collapse every part into ONE mesh with bmesh (no object.join, so material slots cannot shuffle),
    assign the material per face, export the FBX and render the two previews."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new(); used = []
    for o in parts:
        eo = o.evaluated_get(dg)
        me = bpy.data.meshes.new_from_object(eo)
        n0 = len(bm.faces)
        bm.from_mesh(me); bpy.data.meshes.remove(me)
        bm.faces.ensure_lookup_table()
        mname = o['m']
        for i in range(n0, len(bm.faces)):
            f = bm.faces[i]; nm = mname
            if recolor:
                r = recolor(f.calc_center_median(), f.normal, mname, o.name)
                if r: nm = r
            if nm not in used: used.append(nm)
            f.material_index = used.index(nm); f.smooth = True
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.0002)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for nm in used: me.materials.append(MATS[nm])
    me.set_sharp_from_angle(angle=radians(38))
    for o in list(scene.objects): bpy.data.objects.remove(o)
    obj = bpy.data.objects.new(name + '_Mesh', me); scene.collection.objects.link(obj)
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    xs = [v.co.x for v in me.vertices]; ys = [v.co.y for v in me.vertices]; zs = [v.co.z for v in me.vertices]
    print(f'[{name}] triangles {tris}, materials {len(me.materials)} {used}')
    print(f'[{name}] size L {max(ys) - min(ys):.2f} W {max(xs) - min(xs):.2f} H {max(zs) - min(zs):.2f}, min z {min(zs):.3f}, y {min(ys):.2f}..{max(ys):.2f}')
    root = bpy.data.objects.new(name, None); scene.collection.objects.link(root); obj.parent = root
    st = bpy.data.objects.new('Seat', None); st.location = seat; scene.collection.objects.link(st); st.parent = root
    for o in (root, obj, st): o.select_set(True)
    bpy.ops.export_scene.fbx(filepath=f'{OUT}/{name}.fbx', use_selection=True, apply_unit_scale=True,
                             apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)
    # previews
    world = bpy.data.worlds.new('W'); scene.world = world; world.use_nodes = True
    bg = world.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (0.78, 0.78, 0.78, 1); bg.inputs['Strength'].default_value = 1.0
    gm = bpy.data.meshes.new('Ground'); gb = bmesh.new(); bmesh.ops.create_grid(gb, x_segments=1, y_segments=1, size=40); gb.to_mesh(gm); gb.free()
    ground = bpy.data.objects.new('Ground', gm); scene.collection.objects.link(ground)
    gmat = bpy.data.materials.new('Ground'); gmat.use_nodes = True
    gmat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.42, 0.42, 0.42, 1)
    gmat.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 1.0
    gm.materials.append(gmat)
    sd = bpy.data.lights.new('Sun', 'SUN'); sd.energy = 2.2; sd.angle = radians(12)
    sun = bpy.data.objects.new('Sun', sd); scene.collection.objects.link(sun)
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x, scene.render.resolution_y = 1672, 941
    scene.view_settings.view_transform = 'Standard'
    cd = bpy.data.cameras.new('Cam'); cam = bpy.data.objects.new('Cam', cd); scene.collection.objects.link(cam); scene.camera = cam
    def shoot(fname, loc, tgt, ortho=None, sunrot=(40, 0, -140)):
        cam.location = loc
        cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        if ortho: cd.type = 'ORTHO'; cd.ortho_scale = ortho
        else: cd.type = 'PERSP'; cd.lens = lens
        sun.rotation_euler = tuple(radians(a) for a in sunrot)
        scene.render.filepath = f'{OUT}/{fname}.png'; bpy.ops.render.render(write_still=True)
    sx = 1 if cam34[0] > 0 else -1
    shoot('render-34', cam34, target, sunrot=(48, 0, -25 * sx))
    shoot('render-side', (16, side_y, side_z), (0, side_y, side_z), ortho=side_scale, sunrot=(50, 0, 60))

# ==== MODEL ==== old boxy 4x4 field vehicle with a soft top. Measured from ref-side.png at 2.5 mm per pixel:
# length 4.0 m with the spare, wheelbase 2.26 m, wheel radius 0.41 m, roof at 2.0 m.
PAINT = mat('Paint', (0.105, 0.13, 0.048), 0.7)
SEAM = mat('PaintDark', (0.06, 0.075, 0.028), 0.8)
CANVAS = mat('Canvas', (0.20, 0.17, 0.08), 0.95)
TRIM = mat('Trim', (0.05, 0.05, 0.047), 0.7)
BLACK = mat('Rubber', (0.022, 0.022, 0.022), 0.9)
INTERIOR = mat('Interior', (0.085, 0.095, 0.055), 0.9)
GLASS = mat('Glass', (0.30, 0.36, 0.38), 0.1, alpha=0.42)
LAMP = mat('Lamp', (0.80, 0.78, 0.62), 0.25)
AMBER = mat('Amber', (0.9, 0.33, 0.02), 0.3)
RED = mat('Red', (0.55, 0.03, 0.02), 0.3)

W = 0.80                      # body half width
WZ, WR = 0.41, 0.41           # wheel centre height, radius
CF, CR = 0.785, 3.04          # wheel centres (d)
WX = 0.745                    # wheel track half width

# ---- Tub: lofted cross sections (hood with chamfered shoulders, flat belt, lower rear) ----
def ring(w, zb, zs, wc, zt): return [(-w, zb), (w, zb), (w, zs), (wc, zt), (-wc, zt), (-w, zs)]
tub = loft('Tub', [
    (0.30, ring(0.775, 0.72, 1.07, 0.63, 1.13)),
    (0.37, ring(W, 0.72, 1.115, 0.66, 1.195)),
    (0.45, ring(W, 0.72, 1.12, 0.66, 1.205)),
    (0.46, ring(W, 0.50, 1.12, 0.66, 1.205)),
    (1.45, ring(W, 0.50, 1.15, 0.66, 1.24)),
    (1.47, ring(W, 0.50, 1.17, 0.775, 1.195)),
    (2.39, ring(W, 0.50, 1.17, 0.775, 1.195)),
    (2.41, ring(W, 0.50, 1.105, 0.775, 1.13)),
    (3.64, ring(W, 0.56, 1.105, 0.775, 1.13)),
    (3.69, ring(0.775, 0.60, 1.09, 0.75, 1.115))], PAINT)
arch_f = [(CF - 0.62, 0.2), (CF - 0.36, 0.72), (CF - 0.22, 0.84), (CF + 0.27, 0.84), (CF + 0.47, 0.50), (CF + 0.50, 0.2)]
arch_r = [(CR - 0.52, 0.2), (CR - 0.47, 0.50), (CR - 0.26, 0.84), (CR + 0.26, 0.84), (CR + 0.42, 0.60), (CR + 0.50, 0.2)]
cutters = [dbox('cCockpit', 1.56, 2.50, -0.73, 0.73, 0.60, 1.6, None),
           dbox('cRear', 2.48, 3.60, -0.73, 0.73, 0.88, 1.6, None),
           dbox('cAisle', 2.48, 3.60, -0.42, 0.42, 0.60, 1.6, None)]
for s in (-1, 1):
    cutters.append(prism_x(f'cArchF{s}', arch_f, s * 0.50, s * 1.0, None))
    cutters.append(prism_x(f'cArchR{s}', arch_r, s * 0.50, s * 1.0, None))
cut(tub, *cutters)
add_bevel(tub, 0.016, 2)

# ---- Fender flares: angular arch lips standing proud of the body ----
fl_f_o = [(CF - 0.42, 0.72), (CF - 0.26, 0.925), (CF + 0.32, 0.925), (CF + 0.54, 0.50)]
fl_f_i = [(CF - 0.35, 0.72), (CF - 0.22, 0.845), (CF + 0.27, 0.845), (CF + 0.465, 0.50)]
fl_r_o = [(CR - 0.55, 0.50), (CR - 0.31, 0.925), (CR + 0.31, 0.925), (CR + 0.50, 0.60)]
fl_r_i = [(CR - 0.465, 0.50), (CR - 0.26, 0.845), (CR + 0.26, 0.845), (CR + 0.425, 0.60)]
for s in (-1, 1):
    strip_x(f'FlareF{s}', fl_f_o, fl_f_i, s * 0.76, s * 0.895, PAINT, bevel=0.014, segs=2)
    strip_x(f'FlareR{s}', fl_r_o, fl_r_i, s * 0.76, s * 0.895, PAINT, bevel=0.014, segs=2)
    dbox(f'Sill{s}', 1.27, 2.58, s * 0.72, s * 0.80, 0.43, 0.51, PAINT, 0.01, 1)

# ---- Front face: grille, lamps, bumper ----
FY = Y(0.30)
box('GrilleBack', (0, FY - 0.002, 0.925), (0.70, 0.02, 0.33), BLACK)
for k in range(4):
    box(f'GrilleBar{k}', (0, FY - 0.016, 0.79 + k * 0.09), (0.70, 0.03, 0.05), PAINT, 0.008, 1)
for s in (-1, 1):
    box(f'LampPanel{s}', (s * 0.57, FY - 0.004, 0.925), (0.37, 0.016, 0.385), PAINT, 0.008, 1)
    box(f'GrillePost{s}', (s * 0.365, FY - 0.016, 0.925), (0.045, 0.03, 0.37), PAINT, 0.008, 1)
    cyl(f'LampRing{s}', (s * 0.565, FY - 0.035, 0.95), 0.135, 0.09, 'Y', PAINT, 32, 0.015, 2)
    cyl(f'LampLens{s}', (s * 0.565, FY - 0.085, 0.95), 0.105, 0.02, 'Y', LAMP, 32, r2=0.085)
    cyl(f'Indicator{s}', (s * 0.61, FY - 0.02, 0.765), 0.042, 0.05, 'Y', AMBER, 16)
    box(f'BumperMount{s}', (s * 0.40, Y(0.24), 0.56), (0.07, 0.20, 0.07), BLACK)
    box(f'BumperStub{s}', (s * 0.33, Y(0.13), 0.625), (0.07, 0.12, 0.05), TRIM, 0.008, 1)
    torus(f'Shackle{s}', (s * 0.33, Y(0.0), 0.475), (0, 1, 0), 0.042, 0.012, TRIM, 12, 5)
    box(f'HoodLatch{s}', (s * 0.52, Y(0.41), 1.215), (0.03, 0.08, 0.03), TRIM)
    for k in range(6):
        box(f'Vent{s}{k}', (s * (W + 0.001), Y(0.86 + k * 0.05), 1.03), (0.012, 0.022, 0.085), SEAM)
    bar(f'CowlSeam{s}', (s * (W + 0.002), Y(1.41), 0.93), (s * (W + 0.002), Y(1.41), 1.14), 0.008, 0.012, SEAM)
    bar(f'HoodSeam{s}', (s * (W + 0.002), Y(0.40), 1.118), (s * (W + 0.002), Y(1.41), 1.148), 0.008, 0.010, SEAM)
box('Bumper', (0, Y(0.11), 0.535), (1.76, 0.22, 0.135), TRIM, 0.018, 2)
bar('HoodCentre', (0, Y(0.40), 1.207), (0, Y(1.44), 1.242), 0.03, 0.012, PAINT)

# ---- Windshield: raked frame, glass, wipers ----
rake = math.atan2(0.21, 0.60)
ws_o = [(-0.78, 0), (0.78, 0), (0.75, 0.64), (-0.75, 0.64)]
ws_i = [(-0.725, 0.05), (0.725, 0.05), (0.70, 0.595), (-0.70, 0.595)]
def wsp(u, v, off=0.0):   # point on the windshield plane: u across, v up the slope, off toward the front
    return Vector((u, Y(1.47) + v * sin(rake) - off * cos(rake), 1.19 + v * cos(rake) + off * sin(rake)))
bm = bmesh.new()
ring_pts = {}
for key, pts in (('o', ws_o), ('i', ws_i)):
    for off in (0.03, -0.03):
        ring_pts[(key, off)] = [bm.verts.new(wsp(u, v, off)) for u, v in pts]
for off in (0.03, -0.03):
    o_, i_ = ring_pts[('o', off)], ring_pts[('i', off)]
    for i in range(4): bm.faces.new((o_[i], o_[(i + 1) % 4], i_[(i + 1) % 4], i_[i]))
for key in ('o', 'i'):
    a, b = ring_pts[(key, 0.03)], ring_pts[(key, -0.03)]
    for i in range(4): bm.faces.new((a[i], a[(i + 1) % 4], b[(i + 1) % 4], b[i]))
_mk('WindshieldFrame', bm, PAINT, None, 0.008, 1)
pane('WindshieldGlass', [wsp(u, v) for u, v in ws_i], GLASS, 0.008)
for u0, u1 in ((-0.10, -0.52), (0.52, 0.10)):
    bar('Wiper', wsp(u0, 0.07, 0.035), wsp(u1, 0.30, 0.035), 0.014, 0.014, BLACK)
box('CabMirror', tuple(wsp(0, 0.53, -0.08)), (0.20, 0.02, 0.06), BLACK)

# ---- Doors: seams, hinges, handle, window frame with glass ----
df_o = [(1.50, 1.19), (2.40, 1.19), (2.40, 1.78), (1.706, 1.78)]
df_i = [(1.575, 1.235), (2.355, 1.235), (2.355, 1.735), (1.75, 1.735)]
for s in (-1, 1):
    x = s * (W + 0.002)
    for (d0, z0), (d1, z1) in (((1.49, 0.75), (1.49, 1.17)), ((2.39, 0.55), (2.39, 1.17)), ((1.61, 0.55), (2.39, 0.55)), ((1.49, 0.75), (1.61, 0.55))):
        bar(f'DoorSeam{s}', (x, Y(d0), z0), (x, Y(d1), z1), 0.008, 0.013, SEAM)
    for z in (0.66, 1.06):
        box(f'Hinge{s}', (s * (W + 0.012), Y(1.475), z), (0.026, 0.11, 0.065), PAINT, 0.006, 1)
    box(f'Handle{s}', (s * (W + 0.018), Y(2.25), 1.07), (0.03, 0.15, 0.035), BLACK, 0.006, 1)
    strip_x(f'DoorFrame{s}', df_o, df_i, s * 0.742, s * 0.778, PAINT, closed=True, bevel=0.006, segs=1)
    pane(f'DoorGlass{s}', [(s * 0.76, Y(d), z) for d, z in df_i], GLASS, 0.008)
    # mirror on a bent arm
    bar(f'MirrorArm{s}a', (s * 0.80, Y(1.53), 1.13), (s * 0.90, Y(1.50), 1.20), 0.022, 0.022, BLACK)
    bar(f'MirrorArm{s}b', (s * 0.90, Y(1.50), 1.19), (s * 0.90, Y(1.50), 1.32), 0.022, 0.022, BLACK)
    box(f'Mirror{s}', (s * 0.915, Y(1.50), 1.38), (0.07, 0.05, 0.19), BLACK, 0.012, 1)

# ---- Soft top: lofted canvas with sagging bows, hollowed, windows cut ----
def cring(wb, zb, wm, zm, wt, zt, crown, dm=0.0, dt=0.0):
    return [(-wb, zb), (wb, zb), (wm, zm, dm), (wt, zt, dt), (0, zt + crown, dt), (-wt, zt, dt), (-wm, zm, dm)]
top = loft('Canvas', [
    (1.64, cring(0.765, 1.785, 0.765, 1.80, 0.70, 1.84, 0.008)),
    (1.71, cring(0.785, 1.775, 0.785, 1.805, 0.715, 1.88, 0.012)),
    (2.37, cring(0.795, 1.775, 0.795, 1.82, 0.725, 1.985, 0.015)),
    (2.40, cring(0.83, 1.115, 0.805, 1.60, 0.725, 1.99, 0.015)),
    (2.72, cring(0.83, 1.115, 0.80, 1.60, 0.715, 1.95, 0.02)),
    (3.05, cring(0.83, 1.115, 0.805, 1.60, 0.725, 1.985, 0.012)),
    (3.36, cring(0.83, 1.115, 0.80, 1.60, 0.715, 1.955, 0.02)),
    (3.58, cring(0.83, 1.115, 0.795, 1.60, 0.70, 1.97, 0.012)),
    (3.73, cring(0.80, 1.10, 0.76, 1.60, 0.66, 1.90, 0.01, -0.05, -0.13))], CANVAS)
c_in = loft('cTopIn', [
    (2.47, cring(0.755, 1.0, 0.745, 1.60, 0.655, 1.885, 0.0)),
    (3.64, cring(0.755, 1.0, 0.745, 1.60, 0.655, 1.885, 0.0, -0.06, -0.14))], None)
c_roof = dbox('cRoof', 1.75, 2.52, -0.69, 0.69, 1.70, 1.845, None)
c_win = dbox('cWinSide', 2.76, 3.275, -1.0, 1.0, 1.36, 1.68, None); add_bevel(c_win, 0.045, 2, 30)
c_winr = dbox('cWinRear', 3.3, 3.9, -0.42, 0.42, 1.40, 1.70, None); add_bevel(c_winr, 0.045, 2, 30)
cut(top, c_in, c_roof, c_win, c_winr)
add_bevel(top, 0.02, 2)
for s in (-1, 1):
    pane(f'SoftWin{s}', [(s * 0.772, Y(d), z) for d, z in ((2.74, 1.34), (3.30, 1.34), (3.30, 1.70), (2.74, 1.70))], GLASS, 0.006)
    for d in (2.53, 2.86, 3.19, 3.52):
        box(f'Strap{s}', (s * 0.838, Y(d), 1.165), (0.016, 0.05, 0.13), PAINT, 0.004, 1)
        cyl(f'Stud{s}', (s * 0.848, Y(d), 1.125), 0.014, 0.012, 'X', TRIM, 8)
pane('SoftWinRear', [(x, Y(3.625), z) for x, z in ((-0.44, 1.38), (0.44, 1.38), (0.44, 1.72), (-0.44, 1.72))], GLASS, 0.006)

# ---- Rear: lamps, bumperettes, spare carrier ----
for s in (-1, 1):
    box(f'TailAmber{s}', (s * 0.735, Y(3.70), 0.875), (0.085, 0.05, 0.105), AMBER, 0.008, 1)
    box(f'TailRed{s}', (s * 0.735, Y(3.70), 0.765), (0.085, 0.05, 0.105), RED, 0.008, 1)
    box(f'RearBumper{s}', (s * 0.55, Y(3.745), 0.555), (0.46, 0.12, 0.11), TRIM, 0.014, 2)
    torus(f'RearRing{s}', (s * 0.55, Y(3.80), 0.47), (0, 1, 0), 0.04, 0.011, TRIM, 12, 5)
box('SpareMount', (-0.42, Y(3.70), 0.95), (0.22, 0.12, 0.22), BLACK)
bar('TailgateSeam', (-0.70, Y(3.692), 1.09), (0.70, Y(3.692), 1.09), 0.012, 0.008, SEAM)

# ---- Underside: frame rails, axles, differentials, transfer case, shafts, exhaust ----
for s in (-1, 1):
    dbox(f'Rail{s}', 0.20, 3.70, s * 0.34, s * 0.42, 0.42, 0.52, BLACK)
    bar(f'RadiusArm{s}', (s * 0.40, Y(1.50), 0.45), (s * 0.47, Y(CF + 0.05), 0.40), 0.035, 0.035, BLACK)
    bar(f'SpringR{s}', (s * 0.50, Y(CR - 0.50), 0.47), (s * 0.50, Y(CR + 0.50), 0.47), 0.06, 0.03, BLACK)
dbox('Floor', 0.45, 3.66, -0.50, 0.50, 0.50, 0.53, BLACK)
for c in (CF, CR):
    cyl('Axle', (0, Y(c), WZ), 0.045, 1.36, 'X', BLACK, 10)
    cyl('Diff', (0.14, Y(c), WZ), 0.115, 0.17, 'Y', BLACK, 14, 0.03, 1)
box('TransferCase', (0.05, Y(1.97), 0.385), (0.30, 0.36, 0.15), TRIM, 0.02, 1)
bar('ShaftF', (0.12, Y(1.82), 0.39), (0.14, Y(CF + 0.09), WZ), 0.04, 0.04, BLACK)
bar('ShaftR', (0.10, Y(2.14), 0.39), (0.14, Y(CR - 0.09), WZ), 0.04, 0.04, BLACK)
cyl('Exhaust', (-0.52, Y(3.05), 0.44), 0.028, 1.50, 'Y', TRIM, 8)
box('Muffler', (-0.52, Y(2.45), 0.44), (0.16, 0.40, 0.10), TRIM, 0.02, 1)

# ---- Interior: seats, dashboard, steering wheel, gear lever ----
for sx in (-0.38, 0.38):
    box('SeatPed', (sx, Y(2.03), 0.66), (0.36, 0.36, 0.12), BLACK)
    box('SeatBase', (sx, Y(2.02), 0.775), (0.46, 0.46, 0.13), INTERIOR, 0.03, 2)
    box('SeatBack', (sx, Y(2.29), 1.10), (0.46, 0.11, 0.60), INTERIOR, 0.03, 2, rot=(radians(-8), 0, 0))
dbox('Dash', 1.53, 1.66, -0.73, 0.73, 0.95, 1.185, INTERIOR, 0.02, 1)
dbox('Binnacle', 1.62, 1.70, 0.24, 0.52, 1.07, 1.17, BLACK, 0.015, 1)
SW = Vector((0.38, Y(1.84), 1.27)); col = Vector((0, -0.22, -0.17)).normalized()
bar('SteerColumn', SW, SW + col * 0.30, 0.035, 0.035, BLACK)
torus('SteerWheel', SW, -col, 0.18, 0.014, BLACK, 20, 5)
side = Vector((1, 0, 0)); upv = col.cross(side).normalized()
for v in (side, -side, upv):
    bar('Spoke', SW, SW + v * 0.175, 0.012, 0.03, BLACK)
bar('GearLever', (0.0, Y(1.90), 0.60), (0.0, Y(1.86), 0.95), 0.02, 0.02, BLACK)
cyl('GearKnob', (0.0, Y(1.86), 0.96), 0.03, 0.04, 'Z', BLACK, 8)

# ---- Wheels: lathed tyre with tread blocks, dished steel rim with holes, hub cap and nuts ----
TYRE = [(0.25, -0.115), (0.34, -0.13), (0.385, -0.125), (0.405, -0.10), (0.405, 0.10), (0.385, 0.125), (0.34, 0.13), (0.25, 0.115)]
RIM = [(0.26, -0.06), (0.26, 0.115), (0.24, 0.125), (0.205, 0.085), (0.205, -0.06)]
def wheel(c, yaw):
    XF.append(Matrix.Translation(c) @ Matrix.Rotation(yaw, 4, 'Z'))
    lathe('Tyre', TYRE, BLACK, 32)
    NB = 18
    for k in range(NB):
        for sd in (-1, 1):
            a = 2 * pi * (k + (0.5 if sd > 0 else 0)) / NB
            box('Tread', (sd * 0.068, 0.408 * cos(a), 0.408 * sin(a)), (0.118, 0.085, 0.03), BLACK, rot=(a - pi / 2, 0, 0))
            box('Lug', (sd * 0.128, 0.375 * cos(a), 0.375 * sin(a)), (0.022, 0.07, 0.07), BLACK, rot=(a - pi / 2, 0, 0))
    lathe('Rim', RIM, PAINT, 32)
    cyl('Disc', (0.07, 0, 0), 0.21, 0.04, 'X', PAINT, 32)
    cyl('HubCap', (0.105, 0, 0), 0.075, 0.07, 'X', TRIM, 16, 0.014, 1)
    for k in range(8):
        a = 2 * pi * k / 8
        cyl('Hole', (0.0905, 0.155 * cos(a), 0.155 * sin(a)), 0.021, 0.004, 'X', BLACK, 8)
    for k in range(6):
        a = 2 * pi * (k + 0.5) / 6
        cyl('Nut', (0.097, 0.108 * cos(a), 0.108 * sin(a)), 0.014, 0.02, 'X', TRIM, 6)
    XF.pop()
for c in (CF, CR):
    wheel((WX, Y(c), WZ), 0)
    wheel((-WX, Y(c), WZ), pi)
wheel((-0.42, Y(3.86), 0.95), pi / 2)

# ---- Per-face recolour (geometry-free): dark cabin inside the tub, black wheel wells and underside, worn sills ----
def recolor(c, n, m, oname):
    d = c.y + L / 2
    if oname == 'Tub':
        if abs(c.x) < 0.74 and 1.55 < d < 3.61 and c.z > 0.59: return 'Interior'
        if n.z < -0.5 and c.z < 0.9: return 'Rubber'
        if 0.49 < abs(c.x) < 0.79 and c.z < 0.86 and (abs(d - CF) < 0.6 or abs(d - CR) < 0.56) and abs(n.x) < 0.9: return 'Rubber'
        if abs(c.x) < 0.51 and c.z < 0.86 and abs(n.x) > 0.9 and (abs(d - CF) < 0.6 or abs(d - CR) < 0.56): return 'Rubber'
    if oname.startswith('Sill') and n.z < -0.5: return 'PaintDark'
    return None

finish('Offroad4x4', (0.38, Y(2.04), 0.86), recolor,
       cam34=(-7.7, -7.9, 2.3), target=(0.0, -0.05, 0.95), lens=88, side_scale=4.19, side_z=0.975, side_y=0.0)

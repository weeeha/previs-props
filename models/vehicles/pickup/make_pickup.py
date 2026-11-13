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

# ==== MODEL ==== crew-cab pickup with an open bed. Measured from ref-side.png at 3.3 mm per pixel:
# length 5.3 m, wheelbase 3.3 m, wheel radius 0.42 m, roof at 1.85 m, bed rail at 1.40 m.
L = 5.30
PAINT = mat('Paint', (0.010, 0.028, 0.115), 0.55)
SEAM = mat('PaintDark', (0.006, 0.013, 0.045), 0.7)
TRIM = mat('Trim', (0.042, 0.042, 0.046), 0.7)
BLACK = mat('Rubber', (0.02, 0.02, 0.022), 0.9)
INTERIOR = mat('Interior', (0.045, 0.05, 0.055), 0.9)
GLASS = mat('Glass', (0.22, 0.36, 0.44), 0.1, alpha=0.5)
LAMP = mat('Lamp', (0.60, 0.60, 0.56), 0.3)
AMBER = mat('Amber', (0.9, 0.33, 0.02), 0.3)
RED = mat('Red', (0.55, 0.03, 0.02), 0.3)
ALLOY = mat('Alloy', (0.27, 0.275, 0.29), 0.45, 0.1)

W = 0.94
WZ, WR = 0.42, 0.42
CF, CR = 0.94, 4.24
WX = 0.80

# ---- Lower body: lofted sections (hood with shoulders and a raised centre, tucked sills, bed) ----
def ring(w0, zb, w, zc, zs, wt, zt, wh, zh):
    return [(-w0, zb), (w0, zb), (w, zc), (w, zs), (wt, zt), (wh, zh), (-wh, zh), (-wt, zt), (-w, zs), (-w, zc)]
body = loft('Body', [
    (0.14, ring(0.84, 0.52, 0.88, 0.71, 1.10, 0.76, 1.19, 0.42, 1.215)),
    (0.26, ring(0.90, 0.50, W, 0.71, 1.17, 0.80, 1.265, 0.44, 1.295)),
    (0.50, ring(0.90, 0.50, W, 0.71, 1.21, 0.81, 1.30, 0.45, 1.335)),
    (1.29, ring(0.90, 0.50, W, 0.71, 1.27, 0.82, 1.37, 0.46, 1.40)),
    (1.31, ring(0.90, 0.50, W, 0.71, 1.27, 0.915, 1.30, 0.46, 1.30)),
    (3.455, ring(0.90, 0.50, W, 0.71, 1.27, 0.915, 1.30, 0.46, 1.30)),
    (3.475, ring(0.90, 0.50, W, 0.71, 1.36, 0.915, 1.40, 0.46, 1.40)),
    (5.14, ring(0.90, 0.50, W, 0.71, 1.36, 0.915, 1.40, 0.46, 1.40)),
    (5.22, ring(0.88, 0.54, 0.92, 0.72, 1.35, 0.895, 1.385, 0.46, 1.385))], PAINT)
def arch_in(c): return [(c - 0.44, 0.50), (c - 0.42, 0.76), (c - 0.35, 0.90), (c - 0.23, 0.975), (c + 0.23, 0.975), (c + 0.35, 0.90), (c + 0.42, 0.76), (c + 0.44, 0.50)]
def arch_out(c): return [(c - 0.52, 0.50), (c - 0.50, 0.80), (c - 0.42, 0.97), (c - 0.28, 1.065), (c + 0.28, 1.065), (c + 0.42, 0.97), (c + 0.50, 0.80), (c + 0.52, 0.50)]
cutters = [dbox('cCabin', 1.42, 3.40, -0.86, 0.86, 0.62, 1.7, None),
           dbox('cBedTop', 3.56, 5.13, -0.80, 0.80, 1.02, 1.7, None),
           dbox('cBedMid', 3.565, 5.125, -0.62, 0.62, 0.80, 1.7, None),
           dbox('cBedFront', 3.57, 3.74, -0.795, 0.795, 0.805, 1.7, None),
           dbox('cBedBack', 4.74, 5.12, -0.795, 0.795, 0.805, 1.7, None)]
for s in (-1, 1):
    for c in (CF, CR):
        pts = [(c - 0.46, 0.2)] + arch_in(c) + [(c + 0.46, 0.2)]
        cutters.append(prism_x(f'cArch{s}', pts, s * 0.64, s * 1.1, None))
cut(body, *cutters)
add_bevel(body, 0.02, 2)

# ---- Greenhouse: lofted cab with tumblehome, hollowed, window openings cut, glass set inside ----
def tw(z): return 0.925 - 0.34 * (z - 1.29)      # half width of the cab at height z
def gring(zt): return [(-0.925, 1.29), (0.925, 1.29), (tw(zt), zt), (-tw(zt), zt)]
def iring(zt): return [(-0.87, 1.0), (0.87, 1.0), (0.87, 1.29), (tw(zt) - 0.05, zt), (-(tw(zt) - 0.05), zt), (-0.87, 1.29)]
cab = loft('Cab', [(1.27, gring(1.385)), (1.86, gring(1.78)), (2.04, gring(1.85)), (3.30, gring(1.85)), (3.43, gring(1.76)), (3.47, gring(1.32))], PAINT)
c_in = loft('cCabIn', [(1.46, iring(1.44)), (1.93, iring(1.735)), (2.07, iring(1.80)), (3.28, iring(1.80)), (3.39, iring(1.715)), (3.41, iring(1.33))], None)
c_wf = prism_x('cWinF', [(1.60, 1.335), (2.44, 1.335), (2.44, 1.745), (1.97, 1.745)], -1.2, 1.2, None); add_bevel(c_wf, 0.03, 2)
c_wr = prism_x('cWinR', [(2.60, 1.335), (3.24, 1.335), (3.24, 1.745), (2.60, 1.745)], -1.2, 1.2, None); add_bevel(c_wr, 0.03, 2)
c_ws = prism_y('cWinShield', [(-0.80, 1.45), (0.80, 1.45), (0.69, 1.74), (-0.69, 1.74)], 1.0, 2.2, None)
c_wb = prism_y('cWinBack', [(-0.60, 1.42), (0.60, 1.42), (0.56, 1.70), (-0.56, 1.70)], 3.2, 3.6, None)
cut(cab, c_in, c_wf, c_wr, c_ws, c_wb)
add_bevel(cab, 0.025, 2)
def wsp(x, z):   # point just under the windshield surface
    return (x, Y(1.27 + (z - 1.385) / 0.669) + 0.0167, z - 0.025)
pane('WindshieldGlass', [wsp(-0.83, 1.43), wsp(0.83, 1.43), wsp(0.72, 1.76), wsp(-0.72, 1.76)], GLASS, 0.008)
for u0, u1 in ((-0.05, -0.55), (0.60, 0.10)):
    a = Vector(wsp(u0, 1.46)); b = Vector(wsp(u1, 1.60)); o = Vector((0, -0.016, 0.024))
    bar('Wiper', a + o, b + o, 0.014, 0.014, BLACK)
pane('BackGlass', [(x, Y(3.445 - (z - 1.32) * 0.09), z) for x, z in ((-0.63, 1.40), (0.63, 1.40), (0.59, 1.72), (-0.59, 1.72))], GLASS, 0.008)
for s in (-1, 1):
    for pts in ([(1.57, 1.31), (2.47, 1.31), (2.47, 1.77), (1.94, 1.77)], [(2.57, 1.31), (3.27, 1.31), (3.27, 1.77), (2.57, 1.77)]):
        pane(f'SideGlass{s}', [(s * (tw(z) - 0.025), Y(d), z) for d, z in pts], GLASS, 0.008)

# ---- Wheel arch flares ----
for s in (-1, 1):
    for c in (CF, CR):
        strip_x(f'Flare{s}', arch_out(c), arch_in(c), s * 0.90, s * 0.985, TRIM, bevel=0.014, segs=2)

# ---- Front: grille frame with bars, lamp housings, bumper with fog lamps ----
prism_y('GrilleFrame', [(-0.42, 0.70), (0.42, 0.70), (0.52, 0.80), (0.52, 1.08), (0.44, 1.17), (-0.44, 1.17), (-0.52, 1.08), (-0.52, 0.80)], 0.055, 0.16, TRIM, bevel=0.014, segs=2)
box('GrilleMesh', (0, Y(0.05), 0.935), (0.86, 0.02, 0.35), BLACK)
for z in (0.845, 0.935, 1.025):
    box('GrilleBar', (0, Y(0.04), z), (0.88, 0.03, 0.05), TRIM, 0.008, 1)
for s in (-1, 1):
    box(f'LampHousing{s}', (s * 0.685, Y(0.115), 0.955), (0.31, 0.09, 0.29), BLACK, 0.012, 1)
    cyl(f'LampRing{s}', (s * 0.665, Y(0.075), 0.955), 0.118, 0.03, 'Y', TRIM, 32)
    cyl(f'LampLens{s}', (s * 0.665, Y(0.06), 0.955), 0.095, 0.02, 'Y', LAMP, 32, r2=0.08)
    box(f'Marker{s}', (s * 0.90, Y(0.20), 0.955), (0.085, 0.25, 0.27), AMBER, 0.014, 1)
    box(f'Fog{s}', (s * 0.66, Y(0.0), 0.545), (0.17, 0.02, 0.075), LAMP, 0.006, 1)
    box(f'FogBezel{s}', (s * 0.66, Y(0.006), 0.545), (0.22, 0.02, 0.115), BLACK)
    box(f'BumperEnd{s}', (s * 0.90, Y(0.22), 0.60), (0.14, 0.36, 0.28), TRIM, 0.035, 2)
box('Bumper', (0, Y(0.125), 0.61), (1.90, 0.25, 0.31), TRIM, 0.04, 2)
box('Valance', (0, Y(0.17), 0.43), (1.60, 0.22, 0.10), TRIM, 0.02, 1)
box('Intake', (0, Y(0.0), 0.545), (0.86, 0.012, 0.09), BLACK)
for k in range(2):
    box('IntakeBar', (0, Y(-0.004), 0.525 + k * 0.04), (0.86, 0.012, 0.012), TRIM)
for s in (-1, 1):   # hood shut lines along the raised centre
    bar(f'HoodLine{s}', (s * 0.47, Y(0.30), 1.297), (s * 0.48, Y(1.27), 1.40), 0.012, 0.008, SEAM)

# ---- Sides: door and bed seams, handles, mirrors, running boards ----
def sidex(z): return 0.90 + 0.04 * (z - 0.50) / 0.21 if z < 0.71 else W
for s in (-1, 1):
    for d in (1.475, 2.51, 3.365):
        bar(f'DoorSeam{s}', (s * (W + 0.002), Y(d), 0.71), (s * (W + 0.002), Y(d), 1.275), 0.008, 0.013, SEAM)
        bar(f'DoorSeamLow{s}', (s * (sidex(0.54) + 0.002), Y(d), 0.54), (s * (W + 0.002), Y(d), 0.71), 0.008, 0.013, SEAM)
    bar(f'DoorSeamBottom{s}', (s * (sidex(0.54) + 0.002), Y(1.475), 0.54), (s * (sidex(0.54) + 0.002), Y(3.365), 0.54), 0.008, 0.013, SEAM)
    bar(f'BedGap{s}', (s * (W + 0.002), Y(3.465), 0.72), (s * (W + 0.002), Y(3.465), 1.34), 0.008, 0.024, SEAM)
    bar(f'Crease{s}', (s * (W + 0.001), Y(1.48), 0.712), (s * (W + 0.001), Y(3.70), 0.712), 0.008, 0.012, SEAM)
    for d in (2.33, 3.19):
        box(f'Handle{s}', (s * (W + 0.018), Y(d), 1.13), (0.035, 0.22, 0.05), TRIM, 0.01, 1)
    bar(f'MirrorArm{s}', (s * 0.90, Y(1.63), 1.34), (s * 1.00, Y(1.61), 1.35), 0.05, 0.07, BLACK)
    box(f'Mirror{s}', (s * 1.06, Y(1.57), 1.36), (0.20, 0.15, 0.22), BLACK, 0.03, 2)
    box(f'Step{s}', (s * 0.985, Y(2.42), 0.355), (0.20, 2.06, 0.075), TRIM, 0.015, 1)
    for d in (1.62, 3.22):
        box(f'StepBracket{s}', (s * 0.92, Y(d), 0.43), (0.10, 0.08, 0.10), BLACK)
    # bed rail caps
    dbox(f'RailCap{s}', 3.49, 5.21, s * 0.80, s * 0.925, 1.39, 1.418, BLACK, 0.006, 1)
    # tail lamps wrap the corner
    box(f'TailRed{s}', (s * 0.888, Y(5.19), 1.03), (0.115, 0.10, 0.40), RED, 0.014, 1)
    box(f'TailWhite{s}', (s * 0.892, Y(5.195), 0.93), (0.118, 0.10, 0.07), LAMP)
    bar(f'TailgateSeam{s}', (s * 0.79, Y(5.222), 0.60), (s * 0.79, Y(5.222), 1.37), 0.012, 0.008, SEAM)
dbox('RailCapFront', 3.485, 3.565, -0.80, 0.80, 1.39, 1.418, BLACK, 0.006, 1)
dbox('RailCapRear', 5.125, 5.215, -0.80, 0.80, 1.385, 1.413, BLACK, 0.006, 1)
box('TailgateHandle', (0, Y(5.225), 1.22), (0.26, 0.02, 0.07), TRIM, 0.006, 1)
box('TailgatePanel', (0, Y(5.222), 0.95), (1.30, 0.012, 0.34), PAINT, 0.004, 1)
box('RearBumper', (0, Y(5.20), 0.585), (1.92, 0.20, 0.23), TRIM, 0.03, 2)
box('RearStep', (0, Y(5.22), 0.705), (0.80, 0.14, 0.02), BLACK)
box('PlateRecess', (0, Y(5.302), 0.585), (0.36, 0.01, 0.13), BLACK)
for k in range(5):  # bed floor ribs
    dbox('BedRib', 3.60, 5.10, -0.50 + k * 0.25 - 0.04, -0.50 + k * 0.25 + 0.04, 0.80, 0.815, BLACK)

# ---- Underside ----
for s in (-1, 1):
    dbox(f'Rail{s}', 0.25, 5.15, s * 0.36, s * 0.44, 0.40, 0.50, BLACK)
    bar(f'Spring{s}', (s * 0.52, Y(CR - 0.6), 0.46), (s * 0.52, Y(CR + 0.6), 0.46), 0.06, 0.03, BLACK)
dbox('Floor', 0.30, 5.15, -0.62, 0.62, 0.49, 0.52, BLACK)
for c in (CF, CR):
    cyl('Axle', (0, Y(c), WZ), 0.045, 1.44, 'X', BLACK, 10)
cyl('Diff', (0.0, Y(CR), WZ), 0.13, 0.20, 'Y', BLACK, 14, 0.03, 1)
bar('Shaft', (0, Y(2.0), 0.44), (0, Y(CR - 0.1), WZ), 0.045, 0.045, BLACK)
cyl('Exhaust', (-0.60, Y(4.85), 0.42), 0.035, 0.9, 'Y', TRIM, 10)
box('Muffler', (-0.52, Y(3.4), 0.42), (0.20, 0.55, 0.12), TRIM, 0.02, 1)

# ---- Interior: dash, wheel, front seats, rear bench ----
dbox('Dash', 1.40, 1.74, -0.86, 0.86, 0.95, 1.31, INTERIOR, 0.03, 1)
box('Console', (0, Y(2.25), 0.78), (0.24, 0.80, 0.26), INTERIOR, 0.02, 1)
for sx in (-0.44, 0.44):
    box('SeatBase', (sx, Y(2.25), 0.80), (0.52, 0.50, 0.17), INTERIOR, 0.035, 2)
    box('SeatBack', (sx, Y(2.53), 1.17), (0.50, 0.12, 0.62), INTERIOR, 0.035, 2, rot=(radians(-10), 0, 0))
    box('Headrest', (sx, Y(2.60), 1.565), (0.27, 0.09, 0.17), INTERIOR, 0.025, 1)
    box('RearHeadrest', (sx, Y(3.33), 1.55), (0.27, 0.09, 0.16), INTERIOR, 0.025, 1)
box('BenchBase', (0, Y(3.03), 0.80), (1.56, 0.48, 0.17), INTERIOR, 0.035, 2)
box('BenchBack', (0, Y(3.28), 1.16), (1.56, 0.12, 0.60), INTERIOR, 0.035, 2, rot=(radians(-8), 0, 0))
SW = Vector((0.44, Y(1.93), 1.23)); col = Vector((0, -0.24, -0.13)).normalized()
bar('SteerColumn', SW, SW + col * 0.24, 0.05, 0.05, BLACK)
torus('SteerWheel', SW, -col, 0.185, 0.016, BLACK, 20, 5)
sidev = Vector((1, 0, 0)); upv = col.cross(sidev).normalized()
for v in (sidev, -sidev, upv):
    bar('Spoke', SW, SW + v * 0.18, 0.014, 0.035, BLACK)
box('CabMirror', (0, Y(1.90), 1.70), (0.22, 0.02, 0.07), BLACK)

# ---- Wheels: road tyre with two grooves, six-spoke alloy ----
TYRE = [(0.27, -0.12), (0.36, -0.135), (0.40, -0.125), (0.42, -0.095), (0.42, -0.045), (0.407, -0.04), (0.407, -0.022), (0.42, -0.017),
        (0.42, 0.017), (0.407, 0.022), (0.407, 0.04), (0.42, 0.045), (0.42, 0.095), (0.40, 0.125), (0.36, 0.135), (0.27, 0.12)]
RIM = [(0.28, -0.06), (0.28, 0.12), (0.26, 0.13), (0.235, 0.10), (0.235, -0.06)]
def wheel(c, yaw):
    XF.append(Matrix.Translation(c) @ Matrix.Rotation(yaw, 4, 'Z'))
    lathe('Tyre', TYRE, BLACK, 32)
    lathe('Rim', RIM, ALLOY, 32)
    cyl('Well', (0.03, 0, 0), 0.236, 0.02, 'X', BLACK, 32)
    for k in range(6):
        a = 2 * pi * k / 6
        box('Spoke', (0.095, 0.145 * cos(a), 0.145 * sin(a)), (0.03, 0.20, 0.085), ALLOY, 0.008, 1, rot=(a, 0, 0))
        b = a + pi / 6
        cyl('Nut', (0.128, 0.085 * cos(b), 0.085 * sin(b)), 0.013, 0.02, 'X', TRIM, 6)
    cyl('Hub', (0.105, 0, 0), 0.075, 0.05, 'X', ALLOY, 24, 0.01, 1)
    cyl('Cap', (0.137, 0, 0), 0.042, 0.02, 'X', TRIM, 6)
    XF.pop()
for c in (CF, CR):
    wheel((WX, Y(c), WZ), 0)
    wheel((-WX, Y(c), WZ), pi)

# ---- Per-face recolour: dark cabin and bed liner, black wells and underside ----
CABC = Vector((0, Y(2.4), 1.45))
def near_wheel(d): return abs(d - CF) < 0.5 or abs(d - CR) < 0.5
def recolor(c, n, m, oname):
    d = c.y + L / 2
    if oname == 'Body':
        if abs(c.x) < 0.87 and 1.41 < d < 3.41 and c.z > 0.61: return 'Interior'
        if abs(c.x) < 0.81 and 3.55 < d < 5.14 and 0.79 < c.z < 1.385: return 'Rubber'
        if n.z < -0.5 and c.z < 0.99: return 'Rubber'
        if 0.63 < abs(c.x) < 0.93 and c.z < 0.99 and near_wheel(d) and abs(n.x) < 0.9: return 'Rubber'
        if abs(c.x) < 0.65 and c.z < 0.99 and near_wheel(d) and abs(n.x) > 0.9: return 'Rubber'
    if oname == 'Cab':
        if n.dot(CABC - c) > 0.02 and abs(c.x) < tw(c.z) - 0.03 and 1.40 < d < 3.44 and c.z < 1.83: return 'Interior'
        if 2.45 < d < 2.59 and abs(n.x) > 0.5 and 1.30 < c.z < 1.79: return 'Rubber'
    return None

finish('Pickup', (0.44, Y(2.27), 0.90), recolor,
       cam34=(7.1, -11.6, 3.0), target=(0.0, -0.6, 0.85), lens=104, side_scale=5.546, side_z=1.09, side_y=0.0)

# ---------------------------------------------------------------- shared helpers (same block in every street-item script)
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_<name>.py -- <out dir>
# 1 unit = 1 m, front toward -Y, up +Z, origin on the ground at the centre of the footprint.
# Everything is built into ONE bmesh with per-face material indices, so there is no join and no slot shuffle.
import bpy, bmesh, sys, math
from mathutils import Vector, Matrix

OUT = sys.argv[sys.argv.index('--') + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# shared palette: same name = same colour in every library model of this batch
PALETTE = {
    'Steel':      ((0.30, 0.31, 0.32), 0.45, 0.6, 0),
    'Black':      ((0.025, 0.025, 0.027), 0.6, 0.0, 0),
    'Concrete':   ((0.30, 0.30, 0.29), 0.9, 0.0, 0),
    'ConcreteStain': ((0.20, 0.195, 0.19), 0.95, 0.0, 0),
    'Wood':       ((0.45, 0.20, 0.075), 0.7, 0.0, 0),
    'WoodDark':   ((0.36, 0.155, 0.055), 0.75, 0.0, 0),
    'CastIron':   ((0.055, 0.057, 0.06), 0.6, 0.3, 0),
    'White':      ((0.80, 0.80, 0.78), 0.55, 0.0, 0),
    'SignalPaint': ((0.06, 0.065, 0.07), 0.55, 0.2, 0),
    'LensRed':    ((0.90, 0.06, 0.03), 0.25, 0.0, 2.5),
    'LensAmber':  ((0.95, 0.50, 0.02), 0.25, 0.0, 0.8),
    'LensGreen':  ((0.05, 0.75, 0.20), 0.25, 0.0, 0.8),
    'LensWhite':  ((0.85, 0.85, 0.80), 0.25, 0.0, 0.6),
    'SignRed':    ((0.55, 0.03, 0.03), 0.5, 0.0, 0),
    'ConeOrange': ((0.95, 0.22, 0.03), 0.6, 0.0, 0),
    'StreetGreen': ((0.035, 0.11, 0.055), 0.55, 0.2, 0),
    'StreetGreenWorn': ((0.025, 0.055, 0.038), 0.7, 0.1, 0),
}
ORDER = []
def use(*names):
    for n in names:
        rgb, rough, metal, emit = PALETTE[n]
        m = bpy.data.materials.new(n); m.use_nodes = True
        b = m.node_tree.nodes['Principled BSDF']
        b.inputs['Base Color'].default_value = (*rgb, 1); b.inputs['Roughness'].default_value = rough
        b.inputs['Metallic'].default_value = metal; m.diffuse_color = (*rgb, 1)
        if emit:
            b.inputs['Emission Color'].default_value = (*rgb, 1); b.inputs['Emission Strength'].default_value = emit
        ORDER.append(m)
    return range(len(names))

BM = bmesh.new()
def add(tbm, M=None, mi=None):
    """Copy a temporary bmesh into the model, optionally transformed and recoloured."""
    if M is not None: tbm.transform(M)
    vmap = {v: BM.verts.new(v.co) for v in tbm.verts}
    for f in tbm.faces:
        try:
            nf = BM.faces.new([vmap[v] for v in f.verts]); nf.material_index = f.material_index if mi is None else mi
        except ValueError: pass
    tbm.free()

def _bevel(bm, bev, segs):
    if bev: bmesh.ops.bevel(bm, geom=bm.edges[:] + bm.verts[:], offset=bev, segments=segs, affect='EDGES', profile=0.5, clamp_overlap=True)

def box(lo, hi, mi, bev=0.01, segs=2, M=None, ret=False):
    c = [(lo[i] + hi[i]) / 2 for i in range(3)]; s = [hi[i] - lo[i] for i in range(3)]
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((*s, 1)))
    _bevel(bm, bev, segs)
    if ret:
        for f in bm.faces: f.material_index = mi
        return bm
    add(bm, M, mi)

def hexa(corners, mi, bev=0.01, segs=2, M=None):
    """Box with free corners: corners[(sx, sy, sz)] = (x, y, z) for sx, sy, sz in -1/1."""
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=2.0)
    for v in bm.verts: v.co = Vector(corners[(round(v.co.x), round(v.co.y), round(v.co.z))])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces); _bevel(bm, bev, segs); add(bm, M, mi)

def lathe(prof, n, mi, M=None, rfun=None, cap_top=True, cap_bot=True):
    """prof: list of (r, z) or (r, z, mi_segment). rfun(angle, r, z) -> (r, mi or None) bends the ring per angle."""
    bm = bmesh.new(); rings = []
    for p in prof:
        r, z = p[0], p[1]; ring = []
        for k in range(n):
            a = 2 * math.pi * k / n; rr = r
            if rfun: rr = rfun(a, r, z)[0]
            ring.append(bm.verts.new((rr * math.cos(a), rr * math.sin(a), z)))
        rings.append(ring)
    def segmi(i, k):
        m = prof[i][2] if len(prof[i]) > 2 else mi
        if rfun:
            a = 2 * math.pi * (k + 0.5) / n; o = rfun(a, prof[i][0], (prof[i][1] + prof[i + 1][1]) / 2)[1]
            if o is not None: m = o
        return m
    for i in range(len(prof) - 1):
        for k in range(n):
            f = bm.faces.new([rings[i][k], rings[i][(k + 1) % n], rings[i + 1][(k + 1) % n], rings[i + 1][k]]); f.material_index = segmi(i, k)
    if cap_bot and prof[0][0] > 1e-6: f = bm.faces.new(rings[0][::-1]); f.material_index = prof[0][2] if len(prof[0]) > 2 else mi
    if cap_top and prof[-1][0] > 1e-6: f = bm.faces.new(rings[-1]); f.material_index = prof[-2][2] if len(prof[-2]) > 2 else mi
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces); add(bm, M)

def cyl(r, z0, z1, mi, n=24, M=None, bev=0.0):
    if bev: prof = [(r - bev, z0), (r, z0 + bev), (r, z1 - bev), (r - bev, z1)]
    else: prof = [(r, z0), (r, z1)]
    lathe(prof, n, mi, M)

def prism(poly, d0, d1, mi, axis='Z', bev=0.0, segs=2, M=None, ret=False):
    """Extrude a 2D polygon. axis 'Z': poly in XY, depth Z. 'X': poly in (Y, Z), depth X. 'Y': poly in (X, Z), depth Y."""
    bm = bmesh.new()
    def P(u, v, d):
        return {'Z': (u, v, d), 'X': (d, u, v), 'Y': (u, d, v)}[axis]
    a = [bm.verts.new(P(u, v, d0)) for u, v in poly]; b = [bm.verts.new(P(u, v, d1)) for u, v in poly]
    n = len(poly); bm.faces.new(a[::-1]); bm.faces.new(b)
    for i in range(n): bm.faces.new([a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces); _bevel(bm, bev, segs)
    if ret:
        for f in bm.faces: f.material_index = mi
        return bm
    add(bm, M, mi)

def cut(target, cutters):
    """Exact boolean DIFFERENCE of temp bmeshes; returns a new bmesh."""
    def ob(bm, n):
        me = bpy.data.meshes.new(n); bm.to_mesh(me); bm.free(); o = bpy.data.objects.new(n, me); scene.collection.objects.link(o); return o
    t = ob(target, 'CutTarget')
    for i, c in enumerate(cutters):
        m = t.modifiers.new(f'b{i}', 'BOOLEAN'); m.operation = 'DIFFERENCE'; m.solver = 'EXACT'; m.object = ob(c, f'Cutter{i}')
    dg = bpy.context.evaluated_depsgraph_get(); bm = bmesh.new(); bm.from_object(t, dg)
    for o in [t] + [m.object for m in t.modifiers]: bpy.data.objects.remove(o)
    return bm

def stroke(pts, w, d0, d1, mi, axis='X', bev=0.0, segs=2, M=None):
    """Thick 2D polyline (mitred), extruded like prism(): cast frames, brackets."""
    P = [Vector((p[0], p[1])) for p in pts]; L, R = [], []
    for i, p in enumerate(P):
        t0 = (P[i] - P[i - 1]).normalized() if i > 0 else (P[1] - P[0]).normalized()
        t1 = (P[i + 1] - P[i]).normalized() if i < len(P) - 1 else t0
        t = (t0 + t1).normalized(); nrm = Vector((-t.y, t.x)); s = w / 2 / max(0.3, nrm.dot(Vector((-t0.y, t0.x))))
        L.append(p + nrm * s); R.append(p - nrm * s)
    prism([tuple(v) for v in L + R[::-1]], d0, d1, mi, axis, bev, segs, M)

def tube(pts, r, mi, n=12, fillet=0.08):
    Pt = [Vector(p) for p in pts]; path = [Pt[0]]
    for i in range(1, len(Pt) - 1):
        a, b, c = Pt[i - 1], Pt[i], Pt[i + 1]; f = min(fillet, (a - b).length / 2, (c - b).length / 2)
        s, e = b + (a - b).normalized() * f, b + (c - b).normalized() * f
        for k in range(7): t = k / 6; path.append((1 - t) ** 2 * s + 2 * (1 - t) * t * b + t ** 2 * e)
    path.append(Pt[-1]); bm = bmesh.new(); rings = []
    for i, p in enumerate(path):
        t = (path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]).normalized()
        u = t.cross(Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))).normalized(); v = t.cross(u)
        rings.append([bm.verts.new(p + r * (math.cos(2 * math.pi * k / n) * u + math.sin(2 * math.pi * k / n) * v)) for k in range(n)])
    for i in range(len(rings) - 1):
        for k in range(n): bm.faces.new([rings[i][k], rings[i][(k + 1) % n], rings[i + 1][(k + 1) % n], rings[i + 1][k]])
    bm.faces.new(rings[0][::-1]); bm.faces.new(rings[-1]); bmesh.ops.recalc_face_normals(bm, faces=bm.faces); add(bm, None, mi)

def visor(c, r, depth, t, mi, a0=-25, a1=205, n=12):
    """Signal visor: open-bottom half tube around +Y axis lens at c, sticking out toward -Y."""
    bm = bmesh.new(); rows = []
    for rr in (r, r + t):
        for y in (c[1], c[1] - depth):
            rows.append([bm.verts.new((c[0] + rr * math.cos(math.radians(a0 + (a1 - a0) * k / n)), y,
                                        c[2] + rr * math.sin(math.radians(a0 + (a1 - a0) * k / n)))) for k in range(n + 1)])
    ib, if_, ob, of = rows
    for k in range(n):
        for A, B in ((ib, if_), (if_, of), (of, ob), (ob, ib)): bm.faces.new([A[k], A[k + 1], B[k + 1], B[k]])
    for k in (0, n): bm.faces.new([ib[k], if_[k], of[k], ob[k]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces); add(bm, None, mi)

def rotx(a): return Matrix.Rotation(math.radians(a), 4, 'X')
def roty(a): return Matrix.Rotation(math.radians(a), 4, 'Y')
def rotz(a): return Matrix.Rotation(math.radians(a), 4, 'Z')
def at(x, y, z): return Matrix.Translation((x, y, z))

def finish(NAME, seat=None, smooth_angle=35):
    """Weld, smooth, export FBX exactly like the anchors, print stats."""
    bmesh.ops.remove_doubles(BM, verts=BM.verts, dist=0.0002)
    me = bpy.data.meshes.new(NAME + '_Mesh'); BM.to_mesh(me)
    for m in ORDER: me.materials.append(m)
    me.shade_smooth(); me.set_sharp_from_angle(angle=math.radians(smooth_angle))
    obj = bpy.data.objects.new(NAME + '_Mesh', me); scene.collection.objects.link(obj)
    root = bpy.data.objects.new(NAME, None); scene.collection.objects.link(root); obj.parent = root
    if seat:
        s = bpy.data.objects.new('Seat', None); scene.collection.objects.link(s); s.parent = root; s.location = seat
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    xs = [v.co for v in me.vertices]; lo = [min(v[a] for v in xs) for a in range(3)]; hi = [max(v[a] for v in xs) for a in range(3)]
    used = sorted({p.material_index for p in me.polygons})
    print(f'[{NAME}] triangles {tris}, materials {len(used)} {[ORDER[i].name for i in used]}, '
          f'size {hi[0]-lo[0]:.2f} x {hi[1]-lo[1]:.2f} x {hi[2]-lo[2]:.2f} m, zmin {lo[2]:.3f}')
    for o in scene.objects: o.select_set(False)
    for o in scene.objects: o.select_set(True)
    bpy.ops.export_scene.fbx(filepath=f'{OUT}/{NAME}.fbx', use_selection=True, apply_unit_scale=True,
                             apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)
    return lo, hi

def render(lo, hi, az=-35, el=18, lens=50, fill=0.92):
    """Three-quarter Eevee preview on a plain light grey backdrop with a soft shadow; camera fitted to the bbox."""
    from bpy_extras.object_utils import world_to_camera_view
    world = bpy.data.worlds.new('W'); scene.world = world; world.use_nodes = True
    wn = world.node_tree.nodes; wl = world.node_tree.links
    wn['Background'].inputs['Color'].default_value = (0.62, 0.62, 0.63, 1)        # what lights the model
    wn['Background'].inputs['Strength'].default_value = 0.6
    bgc = wn.new('ShaderNodeBackground'); bgc.inputs['Color'].default_value = (0.78, 0.78, 0.78, 1)   # what the camera sees
    lp = wn.new('ShaderNodeLightPath'); mix = wn.new('ShaderNodeMixShader')
    wl.new(lp.outputs['Is Camera Ray'], mix.inputs['Fac']); wl.new(wn['Background'].outputs[0], mix.inputs[1])
    wl.new(bgc.outputs[0], mix.inputs[2]); wl.new(mix.outputs[0], wn['World Output'].inputs['Surface'])
    gm = bpy.data.materials.new('GroundM'); gm.use_nodes = True; gb = gm.node_tree.nodes['Principled BSDF']
    gb.inputs['Base Color'].default_value = (0.10, 0.10, 0.10, 1); gb.inputs['Roughness'].default_value = 0.95
    gb.inputs['Emission Color'].default_value = (0.78, 0.78, 0.78, 1); gb.inputs['Emission Strength'].default_value = 0.86
    gme = bpy.data.meshes.new('Ground'); g = bmesh.new(); bmesh.ops.create_grid(g, x_segments=1, y_segments=1, size=200); g.to_mesh(gme); g.free()
    gme.materials.append(gm); ground = bpy.data.objects.new('Ground', gme); scene.collection.objects.link(ground)
    sd = bpy.data.lights.new('Sun', 'SUN'); sd.energy = 2.6; sd.angle = math.radians(12)
    sun = bpy.data.objects.new('Sun', sd); scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(40), 0, math.radians(-30))
    scene.render.engine = 'BLENDER_EEVEE'; scene.view_settings.view_transform = 'Standard'
    scene.render.resolution_x, scene.render.resolution_y = 1672, 941
    cd = bpy.data.cameras.new('Cam'); cam = bpy.data.objects.new('Cam', cd); scene.collection.objects.link(cam); scene.camera = cam
    cd.lens = lens
    c = Vector([(lo[i] + hi[i]) / 2 for i in range(3)])
    corners = [Vector((x, y, z)) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    d = Vector((math.sin(math.radians(az)) * math.cos(math.radians(el)), -math.cos(math.radians(az)) * math.cos(math.radians(el)), math.sin(math.radians(el))))
    def place(dist):
        cam.location = c + d * dist; cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler(); bpy.context.view_layer.update()
        p = [world_to_camera_view(scene, cam, v) for v in corners]
        return max(max(abs(q.x - 0.5), abs(q.y - 0.5)) * 2 for q in p)
    a, b = 0.3, 200.0
    for _ in range(40):
        m = (a + b) / 2
        if place(m) > fill: a = m
        else: b = m
    place(b)
    scene.render.filepath = f'{OUT}/render-34.png'; bpy.ops.render.render(write_still=True)
# ---------------------------------------------------------------- model
# Dumpster: dark green steel skip with a sloped front, top rim, ribs, side fork pockets, two black
# plastic lids hinged at the back, and four swivel casters. About 1.92 x 1.15 x 1.32 m. Front toward -Y.
NAME = 'Dumpster'
GREEN, WORN, BLACK, STEEL = use('StreetGreen', 'StreetGreenWorn', 'Black', 'Steel')
ZB, ZT = 0.20, 1.12
def yf(z): return -0.45 - (z - ZB) / (ZT - ZB) * 0.10      # sloped front face
def yb(z): return 0.48 + (z - ZB) / (ZT - ZB) * 0.04
def xs(z): return 0.85 + (z - ZB) / (ZT - ZB) * 0.08
hexa({(sx, sy, sz): (sx * xs(ZB if sz < 0 else ZT), (yf if sy < 0 else yb)(ZB if sz < 0 else ZT), ZB if sz < 0 else ZT)
      for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)}, GREEN, 0.025, 2)
box((-0.96, -0.585, 1.08), (0.96, 0.555, 1.16), GREEN, 0.015)                         # top rim
box((-0.84, -0.45, 0.16), (0.84, 0.47, 0.205), WORN, 0.01)                             # base channel
for z in (0.50, 0.82):                                                                 # ribs front and back
    box((-xs(z) + 0.03, yf(z) - 0.035, z - 0.03), (xs(z) - 0.03, yf(z) + 0.01, z + 0.03), GREEN, 0.012)
    box((-xs(z) + 0.03, yb(z) - 0.01, z - 0.03), (xs(z) - 0.03, yb(z) + 0.035, z + 0.03), GREEN, 0.012)
for s in (-1, 1):                                                                       # fork pockets / side ears
    x = s * xs(0.7)
    box((min(x, x + s * 0.08), -0.36, 0.62), (max(x, x + s * 0.08), 0.36, 0.80), GREEN, 0.015)
    for y in (-0.365, 0.365):
        box((min(x, x + s * 0.065), y - 0.006, 0.635), (max(x, x + s * 0.065), y + 0.006, 0.785), BLACK, 0.0)
    for z in (0.40, 0.98):
        box((min(x, x + s * 0.02) - 0.01 * s * 0, -0.40, z - 0.02), (max(x, x + s * 0.02), 0.40, z + 0.02), GREEN, 0.008)
# casters: plate, swivel fork, tyre, hub
for cx in (-0.70, 0.70):
    for cy in (-0.30, 0.32):
        box((cx - 0.07, cy - 0.07, 0.15), (cx + 0.07, cy + 0.07, 0.165), STEEL, 0.0)
        cyl(0.03, 0.135, 0.15, STEEL, 8, at(cx, cy, 0))
        for sx in (-1, 1): box((cx + sx * 0.035 - 0.006, cy - 0.03, 0.07), (cx + sx * 0.035 + 0.006, cy + 0.06, 0.14), STEEL, 0.003, 1)
        box((cx - 0.041, cy - 0.03, 0.128), (cx + 0.041, cy + 0.06, 0.14), STEEL, 0.003, 1)
        cyl(0.075, -0.025, 0.025, BLACK, 14, at(cx, cy + 0.03, 0.075) @ roty(90), bev=0.01)
        cyl(0.032, -0.03, 0.03, STEEL, 8, at(cx, cy + 0.03, 0.075) @ roty(90), bev=0.004)
# lids: two plastic lids hinged at the back, sloping 5 degrees down to the front
for s in (-1, 1):
    x0, x1 = sorted((s * 0.008, s * 0.955))
    M = at(0, -0.02, 1.215) @ rotx(5)
    box((x0, -0.575, 0.0), (x1, 0.575, 0.04), BLACK, 0.012, 2, M)
    box((x0, -0.585, -0.06), (x1, -0.555, 0.04), BLACK, 0.008, 2, M)               # front lip
    for k in range(4):
        xc = x0 + (x1 - x0) * (0.17 + 0.22 * k)
        box((xc - 0.025, -0.50, 0.04), (xc + 0.025, 0.46, 0.058), BLACK, 0.01, 1, M)  # ribs
    box((x0 + 0.04, 0.48, 0.04), (x1 - 0.04, 0.54, 0.058), BLACK, 0.01, 2, M)
    for hx in (x0 + 0.18, x1 - 0.18):
        cyl(0.025, -0.07, 0.07, STEEL, 12, at(hx, 0.565, 1.245) @ roty(90), bev=0.004)
lo, hi = finish(NAME)
render(lo, hi, az=-30, el=18, lens=50)

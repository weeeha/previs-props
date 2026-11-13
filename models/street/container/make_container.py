# Generic 20-foot shipping container at previs-library detail (own design, no markings), round 2 "fable" build.
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_container.py -- <out dir>
# Convention: 1 unit = 1 m, front toward -Y (doors on the +Y end), up +Z, origin on the ground at the centre.
# Real ISO size 6.06 x 2.44 x 2.59 m. ../../container/ref-side.png is 258 px per metre along the length (the
# reference is squatter than a real box, the real height wins).
import bpy, bmesh, sys, os, math
import numpy as np
from mathutils import Vector

OUT = sys.argv[sys.argv.index('--') + 1]
REF = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'container')
NAME = 'Container'
HL, HW, H = 3.03, 1.22, 2.59
pi = math.pi

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

MATLIST = []
def mat(name, rgb, rough=0.75, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*rgb, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    m.diffuse_color = (*rgb, 1)
    MATLIST.append(m)
    return len(MATLIST) - 1

PAINT = mat('Paint', (0.40, 0.046, 0.024), 0.7)
SHADE = mat('PaintShade', (0.225, 0.025, 0.013), 0.8)     # recessed corrugation faces
RUST = mat('Rust', (0.16, 0.035, 0.018), 0.9)            # weathering patches
GASKET = mat('Gasket', (0.11, 0.022, 0.014), 0.9)
STEEL = mat('Steel', (0.50, 0.51, 0.52), 0.45, 0.3)
BLACK = mat('Black', (0.03, 0.012, 0.01), 0.9)

parts = []
def finish(o, mi=None):
    for m in MATLIST: o.data.materials.append(m)
    if mi is not None:
        for p in o.data.polygons: p.material_index = mi
    parts.append(o)
    return o

def obj_from_bm(name, bm):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); scene.collection.objects.link(o)
    return o

def raw_box(name, c, size, bevel=0.0, seg=2):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1)
    for v in bm.verts: v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    o = obj_from_bm(name, bm); o.location = c
    for m in MATLIST: o.data.materials.append(m)
    if bevel:
        b = o.modifiers.new('bevel', 'BEVEL'); b.width = bevel; b.segments = seg; b.limit_method = 'ANGLE'
    return o

def box(name, c, size, mi, bevel=0.0, seg=2):
    o = raw_box(name, c, size, bevel, seg)
    for p in o.data.polygons: p.material_index = mi
    parts.append(o)
    return o

def cyl(name, c, r, depth, axis, mi, n=12):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=n, radius1=r, radius2=r, depth=depth)
    o = obj_from_bm(name, bm); o.location = c
    o.rotation_euler = {'X': (0, pi / 2, 0), 'Y': (pi / 2, 0, 0), 'Z': (0, 0, 0)}[axis]
    return finish(o, mi)

cutters = []
def cut(target, c, size, bevel=0.0):
    """Boolean a (dark) pocket out of target."""
    k = raw_box('cut', c, size, bevel)
    for p in k.data.polygons: p.material_index = BLACK
    m = target.modifiers.new('cut', 'BOOLEAN'); m.operation = 'DIFFERENCE'; m.object = k
    cutters.append(k)

SOUP = []
def face(verts, mi, hint):
    SOUP.append(([Vector(v) for v in verts], mi, Vector(hint)))

IN = 0.012                       # rails and posts sit this far inside the corner castings
CX, CY, CZ = 0.19, 0.22, 0.19    # corner casting size
RAIL_T = 0.09                    # rail / post thickness
BOT_H, TOP_H = 0.17, 0.12        # bottom and top side rail heights
POST = 0.13

# ---------------------------------------------------------------- corner castings with slotted holes
for sx in (-1, 1):
    for sy in (-1, 1):
        for sz in (0, 1):
            c = Vector((sx * (HW - CX / 2), sy * (HL - CY / 2), CZ / 2 if sz == 0 else H - CZ / 2))
            o = raw_box('Casting', c, (CX, CY, CZ), 0.016, 2)
            for p in o.data.polygons: p.material_index = PAINT
            cut(o, c + Vector((sx * CX / 2, 0, 0)), (0.10, 0.075, 0.115), 0.03)          # side slot
            cut(o, c + Vector((0, sy * CY / 2, 0)), (0.075, 0.10, 0.115), 0.03)          # end slot
            cut(o, c + Vector((0, 0, (CZ / 2) * (1 if sz else -1))), (0.07, 0.12, 0.10), 0.028)  # top / bottom slot
            parts.append(o)

# ---------------------------------------------------------------- frame: rails, posts, sills
XO = HW - IN                      # outer face of the side rails
YO = HL - IN                      # outer face of the end frames
rail_len = 2 * (HL - CY) + 0.02
for sx in (-1, 1):
    bot = box('BottomRail', (sx * (XO - RAIL_T / 2), 0, BOT_H / 2 + 0.005), (RAIL_T, rail_len, BOT_H - 0.01), PAINT, 0.012)
    for py in (-1.32, 1.32):      # forklift pockets
        cut(bot, (sx * XO, py, 0.085), (0.10, 0.39, 0.105))
    box('TopRail', (sx * (XO - RAIL_T / 2), 0, H - IN - TOP_H / 2), (RAIL_T, rail_len, TOP_H), PAINT, 0.012)
    for sy in (-1, 1):
        box('Post', (sx * (XO - POST / 2), sy * (YO - POST / 2), H / 2), (POST, POST, H - 2 * CZ + 0.02), PAINT, 0.012)
end_len = 2 * (HW - CX) + 0.02
box('FrontBottomRail', (0, -(YO - RAIL_T / 2), BOT_H / 2 + 0.005), (end_len, RAIL_T, BOT_H - 0.01), PAINT, 0.012)
box('FrontTopRail', (0, -(YO - RAIL_T / 2), H - IN - TOP_H / 2), (end_len, RAIL_T, TOP_H), PAINT, 0.012)
DOOR_SILL_Y = YO - 0.028          # header and sill face, set back so the lock gear stays inside 6.06 m
box('DoorSill', (0, DOOR_SILL_Y - 0.05, BOT_H / 2 + 0.005), (end_len, 0.10, BOT_H - 0.01), PAINT, 0.012)
box('DoorHeader', (0, DOOR_SILL_Y - 0.05, H - IN - TOP_H / 2), (end_len, 0.10, TOP_H), PAINT, 0.012)

# ---------------------------------------------------------------- corrugated panels
def corrugated(a0, a1, b0, b1, n, depth, place, hint, notch_top=True, notch_bot=False, rust=()):
    """Trapezoid corrugation running along b, repeated along a. place(a, b, d) -> xyz, d = 0 outer .. depth."""
    p = (a1 - a0) / (n + 0.40)
    cols = []                      # (a, d) polyline across the corrugation
    for i in range(n + 1):
        s = a0 + i * p
        cols += [(s, 0.0), (s + 0.40 * p, 0.0)]
        if i < n: cols += [(s + 0.52 * p, depth), (s + 0.88 * p, depth)]
    rows = [(b0, 1.0 if not notch_bot else 0.0), (b0 + (0.035 if notch_bot else 0.0), 1.0 if not notch_bot else 0.0), (b0 + 0.10, 1.0), (b0 + 0.36, 1.0), (b1 - 0.10, 1.0),
            (b1 - 0.035, 0.0 if notch_top else 1.0), (b1, 0.0 if notch_top else 1.0)]
    for r in range(len(rows) - 1):
        (ba, fa), (bb, fb) = rows[r], rows[r + 1]
        for ci in range(len(cols) - 1):
            (aa, da), (ab, db) = cols[ci], cols[ci + 1]
            quad = [place(aa, ba, da * fa), place(ab, ba, db * fa), place(ab, bb, db * fb), place(aa, bb, da * fb)]
            kind = ci % 4          # 0 outer flat, 1 slope in, 2 inner flat, 3 slope out
            mi = SHADE if kind in (2, 3) else PAINT
            if kind == 2 and r in (1, 2) and (ci // 4) in rust: mi = RUST   # grime collected low in a few recesses
            face(quad, mi, hint)

WALL_OUT = XO - 0.014
Z0, Z1 = BOT_H - 0.01, H - IN - TOP_H + 0.01
Y0, Y1 = -(YO - POST + 0.01), (YO - POST + 0.01)
corrugated(Y0, Y1, Z0, Z1, 19, 0.045, lambda a, b, d: (WALL_OUT - d, a, b), (1, 0, 0), rust=(2, 3, 11, 16))
corrugated(Y0, Y1, Z0, Z1, 19, 0.045, lambda a, b, d: (-(WALL_OUT - d), a, b), (-1, 0, 0), rust=(5, 6, 13))
X0, X1 = -(XO - POST + 0.01), (XO - POST + 0.01)
corrugated(X0, X1, Z0, Z1, 7, 0.045, lambda a, b, d: (a, -(YO - 0.014 - d), b), (0, -1, 0), rust=(1, 5))
# roof: ribs run across the width, both ends of every rib slope down before the rails
ROOF_Z = H - IN - 0.012
corrugated(-(YO - RAIL_T + 0.01), YO - RAIL_T + 0.01, -(XO - RAIL_T + 0.01), XO - RAIL_T + 0.01, 13, 0.028,
           lambda a, b, d: (b, a, ROOF_Z - 0.028 + d), (0, 0, 1), notch_top=True, notch_bot=True)
# underside
face([(-XO + .05, -YO + .05, .04), (XO - .05, -YO + .05, .04), (XO - .05, YO - .05, .04), (-XO + .05, YO - .05, .04)], BLACK, (0, 0, -1))

# ---------------------------------------------------------------- doors
DOOR_Y = YO - 0.062               # door outer face
DZ0, DZ1 = BOT_H + 0.005, H - IN - TOP_H - 0.005
DX = XO - POST                    # half width of the opening
box('DoorGasket', (0, DOOR_Y - 0.035, (DZ0 + DZ1) / 2), (2 * DX, 0.03, DZ1 - DZ0), GASKET)
GAP = 0.028
leaf_w = DX - 1.5 * GAP
for s in (-1, 1):
    cx = s * (GAP / 2 + leaf_w / 2)
    box('DoorLeaf', (cx, DOOR_Y - 0.02, (DZ0 + DZ1) / 2), (leaf_w, 0.04, DZ1 - DZ0 - 2 * GAP), PAINT, 0.008)
    # raised horizontal pressings on the leaf
    rw, rh, rd, ch = leaf_w - 0.20, 0.30, 0.026, 0.05
    for k in range(4):
        zc = DZ0 + 0.36 + k * 0.52
        x0, x1, z0, z1 = cx - rw / 2, cx + rw / 2, zc - rh / 2, zc + rh / 2
        y0, y1 = DOOR_Y - 0.002, DOOR_Y + rd
        o = [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)]
        i = [(x0 + ch, y1, z0 + ch), (x1 - ch, y1, z0 + ch), (x1 - ch, y1, z1 - ch), (x0 + ch, y1, z1 - ch)]
        face(i, PAINT, (0, 1, 0))
        for a in range(4):
            b = (a + 1) % 4
            mid = (Vector(o[a]) + Vector(o[b])) / 2 - Vector((cx, y0, zc))
            face([o[a], o[b], i[b], i[a]], SHADE if a == 2 else PAINT, (mid.x, 1, mid.z))
    # hinges on the corner post
    for zc in (DZ0 + 0.22, DZ0 + 0.84, DZ1 - 0.84, DZ1 - 0.22):
        box('Hinge', (s * (DX + 0.005), DOOR_Y + 0.012, zc), (0.12, 0.05, 0.15), PAINT, 0.012)
        cyl('HingePin', (s * (DX + 0.005), DOOR_Y + 0.04, zc), 0.016, 0.17, 'Z', PAINT, 8)
    # locking bar with guides, cams, keepers and a handle
    bx = s * 0.30
    by = DOOR_Y + 0.045
    cyl('LockBar', (bx, by, (DZ0 + DZ1) / 2), 0.019, DZ1 - DZ0 + 0.20, 'Z', STEEL, 10)
    for zc in (DZ0 + 0.20, DZ0 + 0.52, DZ0 + 1.40, DZ1 - 0.52, DZ1 - 0.20):
        box('BarGuide', (bx, by - 0.012, zc), (0.105, 0.05, 0.085), STEEL, 0.008)
        for bs in (-1, 1):
            cyl('GuideBolt', (bx + bs * 0.036, by + 0.016, zc), 0.011, 0.012, 'Y', STEEL, 6)
    for zc in (DZ0 - 0.07, DZ1 + 0.07):
        box('CamKeeper', (bx, DOOR_SILL_Y + 0.012, zc), (0.13, 0.03, 0.085), STEEL, 0.008)
        box('Cam', (bx, by, zc), (0.075, 0.045, 0.05), STEEL, 0.008)
    hz = DZ0 + 0.86
    box('HandleHub', (bx, by + 0.004, hz), (0.07, 0.05, 0.11), STEEL, 0.008)
    box('Handle', (bx + s * 0.20, by + 0.018, hz), (0.38, 0.018, 0.04), STEEL, 0.006)
    box('HandleCatch', (bx + s * 0.27, by - 0.006, hz), (0.06, 0.05, 0.13), STEEL, 0.008)
    box('HandleRetainer', (bx + s * 0.36, by - 0.006, hz - 0.02), (0.045, 0.045, 0.085), STEEL, 0.008)

# ---------------------------------------------------------------- weld loose faces, merge everything into one mesh
bm = bmesh.new()
for vs, mi, hint in SOUP:
    f = bm.faces.new([bm.verts.new(v) for v in vs]); f.material_index = mi
    f.normal_update()
    if f.normal.dot(hint) < 0: f.normal_flip()
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-5)
finish(obj_from_bm('Panels', bm))

bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
bm = bmesh.new()
for o in parts:
    ev = o.evaluated_get(dg); me = ev.to_mesh()
    me.transform(o.matrix_world)
    bm.from_mesh(me); ev.to_mesh_clear()
for o in parts + cutters: bpy.data.objects.remove(o)
mesh = bpy.data.meshes.new(NAME + '_Mesh'); bm.to_mesh(mesh); bm.free()
used = sorted({p.material_index for p in mesh.polygons})
for i in used: mesh.materials.append(MATLIST[i])
remap = {old: new for new, old in enumerate(used)}
for p in mesh.polygons: p.material_index = remap[p.material_index]
mesh.polygons.foreach_set('use_smooth', [True] * len(mesh.polygons))
mesh.set_sharp_from_angle(angle=math.radians(30))
box_obj = bpy.data.objects.new(NAME + '_Mesh', mesh); scene.collection.objects.link(box_obj)
tris = sum(len(p.vertices) - 2 for p in mesh.polygons)
xs = [v.co.x for v in mesh.vertices]; ys = [v.co.y for v in mesh.vertices]; zs = [v.co.z for v in mesh.vertices]
print(f'[{NAME}] triangles {tris}, materials {len(mesh.materials)}, size {max(xs)-min(xs):.2f} x {max(ys)-min(ys):.2f} x {max(zs)-min(zs):.2f} m, min z {min(zs):.3f}')

root = bpy.data.objects.new(NAME, None); scene.collection.objects.link(root); box_obj.parent = root
for o in scene.objects: o.select_set(False)
for o in (root, box_obj): o.select_set(True)
bpy.ops.export_scene.fbx(filepath=f'{OUT}/{NAME}.fbx', use_selection=True, apply_unit_scale=True,
                         apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)

# ---------------------------------------------------------------- previews
world = bpy.data.worlds.new('W'); scene.world = world; world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.66, 0.66, 0.66, 1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.75
gm = bpy.data.materials.new('Ground'); gm.use_nodes = True
gm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.56, 0.56, 0.56, 1)
gm.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 1.0
bpy.ops.mesh.primitive_plane_add(size=600, location=(0, 0, 0)); bpy.context.active_object.data.materials.append(gm)
def sun(frm, energy):
    bpy.ops.object.light_add(type='SUN', location=frm); o = bpy.context.active_object
    o.data.energy = energy; o.data.angle = math.radians(12)
    o.rotation_euler = (-Vector(frm)).to_track_quat('-Z', 'Y').to_euler()
sun((2, 6, 9), 1.9); sun((7, -5, 4), 0.9)
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x, scene.render.resolution_y = 1672, 941
scene.view_settings.view_transform = 'Standard'
try: scene.eevee.taa_render_samples = 32
except Exception: pass
cam_data = bpy.data.cameras.new('Cam'); cam = bpy.data.objects.new('Cam', cam_data)
scene.collection.objects.link(cam); scene.camera = cam

def shoot(name, loc, target, lens=50, ortho=None):
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    if ortho: cam_data.type = 'ORTHO'; cam_data.ortho_scale = ortho
    else: cam_data.type = 'PERSP'; cam_data.lens = lens
    scene.render.filepath = f'{OUT}/{name}.png'; bpy.ops.render.render(write_still=True)

shoot('render-34', (7.3, 11.3, 3.7), (0.45, -0.2, 1.2), 60)
shoot('render-side', (14, 0, 1.171), (0, 0, 1.171), ortho=1672 / 257.8)

# ---------------------------------------------------------------- compare.jpg (reference left, render right)
def px(path):
    im = bpy.data.images.load(path); w, h = im.size
    a = np.empty(w * h * 4, np.float32); im.pixels.foreach_get(a)
    return a.reshape(h, w, 4)[:941, :1672]
try:
    rows = [np.hstack([px(f'{REF}/ref-{v}.png'), px(f'{OUT}/render-{v}.png')]) for v in ('side', '34')]
    grid = np.vstack(rows); grid[..., 3] = 1
    h, w = grid.shape[:2]
    out = bpy.data.images.new('compare', w, h); out.pixels.foreach_set(grid.ravel())
    out.filepath_raw = f'{OUT}/compare.jpg'; out.file_format = 'JPEG'; out.save()
except Exception as e:
    print('[compare] failed:', e)

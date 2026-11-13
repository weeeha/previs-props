# Abandoned concrete monitoring-station entrance (own design, CC0), previs-library detail, round 2 (Opus).
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_bunker.py -- <out dir>
# 1 unit = 1 m, front toward -Y, up +Z, origin on the ground at the centre.
# Measured from ref-34.png / ref-side.png: roof slab 6.0 x 4.5 m, walls 5.7 x 4.2 m, top of slab 3.18 m,
# plinth 0.45 m, door opening 1.0 x 2.1 m in a 1.7 m recessed niche, barred window 1.0 x 0.95 m, vent ~0.65 m tall.
# The two references are mirror images of each other; this follows the three-quarter view (window left of door).
# Weathering is flat colour only: the concrete is cut into ~12 cm cells and each triangle picks a material from
# a noise mask (drips from the top, rising damp at the bottom, chipped corners). No image textures.
import bpy, bmesh, sys, math
from mathutils import Vector, Matrix, noise

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

CON = mat('Concrete', (0.215, 0.188, 0.162))
CON_D = mat('ConcreteStain', (0.132, 0.118, 0.104))
CON_L = mat('ConcreteChip', (0.300, 0.275, 0.245))
STEEL = mat('Steel', (0.085, 0.090, 0.100), 0.6, 0.3)
RUST = mat('Rust', (0.150, 0.060, 0.030), 0.85)
RUST_D = mat('RustDark', (0.085, 0.034, 0.018), 0.9)
PIPE = mat('Pipe', (0.200, 0.205, 0.210), 0.55, 0.3)
INTERIOR = mat('Interior', (0.012, 0.012, 0.012), 1.0)

parts = []
def new_obj(name, me):
    o = bpy.data.objects.new(name, me); scene.collection.objects.link(o)
    for m in ORDER: o.data.materials.append(m)
    parts.append(o); return o

def set_all(o, idx):
    for p in o.data.polygons: p.material_index = idx

def box(name, lo, hi, idx, bevel=0.0, segs=2):
    c = [(lo[i] + hi[i]) / 2 for i in range(3)]; s = [hi[i] - lo[i] for i in range(3)]
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((*s, 1)))
    if bevel:
        bmesh.ops.bevel(bm, geom=bm.edges[:] + bm.verts[:], offset=bevel, segments=segs, affect='EDGES', profile=0.5)
    bm.to_mesh(me); bm.free()
    o = new_obj(name, me); set_all(o, idx); return o

def lathe(name, prof, n, loc=(0, 0, 0), cap_top=True, cap_bot=True):
    """prof: list of (r, z, mat_idx); the material of segment i (between point i and i+1) is prof[i][2]."""
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
    return new_obj(name, me)

def tube(name, pts, r, idx, n=10, fillet=0.12):
    """Round pipe along a polyline with filleted corners."""
    P = [Vector(p) for p in pts]; path = [P[0]]
    for i in range(1, len(P) - 1):
        a, b, c = P[i - 1], P[i], P[i + 1]
        d1, d2 = (a - b).normalized(), (c - b).normalized()
        f = min(fillet, (a - b).length / 2, (c - b).length / 2)
        s, e = b + d1 * f, b + d2 * f
        for k in range(7):   # quadratic bezier through the corner
            t = k / 6; path.append((1 - t) ** 2 * s + 2 * (1 - t) * t * b + t ** 2 * e)
    path.append(P[-1])
    me = bpy.data.meshes.new(name); bm = bmesh.new(); rings = []
    for i, p in enumerate(path):
        t = (path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]).normalized()
        u = t.cross(Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))).normalized(); v = t.cross(u)
        rings.append([bm.verts.new(p + r * (math.cos(2 * math.pi * k / n) * u + math.sin(2 * math.pi * k / n) * v)) for k in range(n)])
    for i in range(len(rings) - 1):
        for k in range(n):
            bm.faces.new([rings[i][k], rings[i][(k + 1) % n], rings[i + 1][(k + 1) % n], rings[i + 1][k]])
    bm.faces.new(rings[0][::-1]); bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    o = new_obj(name, me); set_all(o, idx); return o

def fbm(x, y, z, oct=3):
    v, a, f = 0.0, 1.0, 1.0
    for _ in range(oct):
        v += a * noise.noise(Vector((x * f, y * f, z * f))); a *= 0.5; f *= 2.1
    return v

def cellify(bm, cell, keep_face, origin=(0.013, 0.017, 0.011)):
    """Slice the faces that pass keep_face() on a world-aligned grid so each cell can take its own colour."""
    lo = Vector((min(v.co[i] for v in bm.verts) for i in range(3)))
    hi = Vector((max(v.co[i] for v in bm.verts) for i in range(3)))
    for axis in range(3):
        no = Vector((0, 0, 0)); no[axis] = 1
        x = math.floor((lo[axis] - origin[axis]) / cell) * cell + origin[axis]
        while x < hi[axis]:
            faces = [f for f in bm.faces if keep_face(f)]
            edges = list({e for f in faces for e in f.edges}); verts = list({v for f in faces for v in f.verts})
            co = Vector((0, 0, 0)); co[axis] = x
            bmesh.ops.bisect_plane(bm, geom=verts + edges + faces, plane_co=co, plane_no=no)
            x += cell


# ---------------------------------------------------------------- dimensions
WX, WY = 5.70, 4.20          # walls
FY = -WY / 2                 # front wall face (y)
H = 2.90                     # wall top (under slab)
SLAB = (2.88, 3.18)
PL = 0.45                    # plinth height
FLOOR = 0.33                 # step / threshold / interior floor
DXC = 0.75                   # door centre x
DW, DH = 1.00, 2.10          # door opening
NW, NTOP, ND = 1.70, 2.66, 0.14   # niche width, top, depth
WINX, WIN_W, WIN_Z = -1.45, 1.00, (1.35, 2.30)

# ---------------------------------------------------------------- concrete shell (booleans, then one mesh)
def boolean(target, cutter, op):
    m = target.modifiers.new('b', 'BOOLEAN'); m.operation = op; m.object = cutter; m.solver = 'EXACT'
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier='b')
    parts.remove(cutter); bpy.data.objects.remove(cutter)

shell = box('Shell', (-WX / 2, -WY / 2, 0.10), (WX / 2, WY / 2, H), CON, 0.035, 2)
plinth = box('Plinth', (-WX / 2 - 0.10, -WY / 2 - 0.10, 0.0), (WX / 2 + 0.10, WY / 2 + 0.10, PL), CON, 0.03, 2)
boolean(shell, plinth, 'UNION')
boolean(shell, box('Room', (-WX / 2 + 0.25, -WY / 2 + 0.25, FLOOR), (WX / 2 - 0.25, WY / 2 - 0.25, H - 0.18), CON), 'DIFFERENCE')
boolean(shell, box('Niche', (DXC - NW / 2, FY - 0.5, FLOOR), (DXC + NW / 2, FY + ND, NTOP), CON), 'DIFFERENCE')
boolean(shell, box('DoorHole', (DXC - DW / 2, FY - 0.5, FLOOR), (DXC + DW / 2, FY + 0.6, FLOOR + DH), CON), 'DIFFERENCE')
boolean(shell, box('WinHole', (WINX - WIN_W / 2, FY - 0.5, WIN_Z[0]), (WINX + WIN_W / 2, FY + 0.6, WIN_Z[1]), CON), 'DIFFERENCE')

slab = box('Slab', (-3.0, -2.25, SLAB[0]), (3.0, 2.25, SLAB[1]), CON, 0.05, 3)
step = box('Step', (DXC - 1.25, FY - 0.90, 0.0), (DXC + 1.25, FY + ND, FLOOR), CON, 0.025, 2)
surround = [box('SurL', (DXC - NW / 2 - 0.12, FY - 0.035, PL - 0.02), (DXC - NW / 2, FY + 0.01, NTOP + 0.12), CON, 0.015, 2),
            box('SurR', (DXC + NW / 2, FY - 0.035, PL - 0.02), (DXC + NW / 2 + 0.12, FY + 0.01, NTOP + 0.12), CON, 0.015, 2),
            box('SurT', (DXC - NW / 2 - 0.12, FY - 0.035, NTOP), (DXC + NW / 2 + 0.12, FY + 0.01, NTOP + 0.12), CON, 0.015, 2)]
sill = box('Sill', (WINX - 0.66, FY - 0.13, WIN_Z[0] - 0.13), (WINX + 0.66, FY + 0.02, WIN_Z[0] - 0.01), CON, 0.02, 2)
for o in (shell, slab, step, sill, *surround): parts.remove(o)

# merge the concrete pieces in one bmesh, slice into cells, paint by mask
bm = bmesh.new()
for o in (shell, slab, step, sill, *surround):
    bm.from_mesh(o.data)
    bpy.data.objects.remove(o)

ROOM_LO = Vector((-WX / 2 + 0.25, -WY / 2 + 0.25, FLOOR)); ROOM_HI = Vector((WX / 2 - 0.25, WY / 2 - 0.25, H - 0.18))
def is_interior(f):
    c = f.calc_center_median()
    return all(ROOM_LO[i] - 0.005 <= c[i] <= ROOM_HI[i] + 0.005 for i in range(3)) and \
        (abs(c.x - ROOM_LO.x) < 0.006 or abs(c.x - ROOM_HI.x) < 0.006 or abs(c.y - ROOM_LO.y) < 0.006 or
         abs(c.y - ROOM_HI.y) < 0.006 or abs(c.z - ROOM_LO.z) < 0.006 or abs(c.z - ROOM_HI.z) < 0.006)
def cuttable(f):
    if f.normal.z < -0.7: return False            # undersides
    if is_interior(f): return False
    return True
cellify(bm, 0.15, cuttable)
print("[bunker] concrete tris", len(bm.faces))

def concrete_mat(c, n):
    # noise thresholds from the fbm distribution: 0.17 ~ top 30 %, 0.27 ~ top 20 %, 0.42 ~ top 10 %, 0.63 ~ top 2 %
    if abs(n.z) > 0.7:
        u, w, off = c.x, c.y, 0.0
    elif abs(n.y) >= abs(n.x):
        u, w, off = c.x, 0.0, 17.0 if n.y > 0 else 0.0
    else:
        u, w, off = c.y, 0.0, 31.0 if n.x > 0 else 47.0
    z = c.z
    corner = abs(abs(u) - (WX / 2 if abs(n.y) >= abs(n.x) else WY / 2)) if abs(n.z) < 0.7 else 9.0   # to the building's vertical corners
    chip = fbm(u * 3.0 + off, z * 3.0, w * 3.0 + 3.3, 2)
    if z > SLAB[0] - 0.01:                                       # roof slab: top and edges
        if n.z > 0.7:
            return CON_D if fbm(c.x * 0.7 + 5, c.y * 0.7, 1.7) > 0.22 else CON
        if chip > 0.62: return CON_L
        return CON_D if fbm(u * 1.0 + off, z * 1.5, 2.2) > 0.20 else CON
    if z < PL + 0.005 and n.z < 0.7:                             # plinth / step sides: damp and dirt
        if chip > 0.60: return CON_L
        return CON_D if fbm(u * 1.1 + off, z * 1.2, 7.1) + (PL - z) * 0.4 > 0.22 else CON
    if n.z > 0.7:                                                 # ledges (plinth top, step top, sill top)
        return CON_D if fbm(c.x * 1.3 + 9, c.y * 1.3, 3.3) > 0.30 else CON
    if corner < 0.14 and chip > 0.62: return CON_L                 # chipped corners
    top = max(0.0, (z - 1.9) / (H - 1.9))                          # drips hanging from under the slab
    top = top ** 0.7
    if top * 0.9 + fbm(u * 2.6 + off, z * 0.40, 1.1, 3) * 0.95 > 0.66: return CON_D
    bot = max(0.0, (0.95 - z) / (0.95 - PL))                       # rising damp
    if bot * 0.75 + fbm(u * 1.6 + off, z * 0.9, 4.4, 3) * 0.8 > 0.60: return CON_D
    under_sill = abs(u - WINX) < 0.7 and WIN_Z[0] - 0.9 < z < WIN_Z[0] - 0.12 and n.y < -0.7   # sill run-off
    if under_sill and fbm(u * 2.2 + 2, z * 0.6, 9.0) + (z - (WIN_Z[0] - 0.9)) * 0.4 > 0.40: return CON_D
    if fbm(u * 0.8 + off + 40, z * 0.8, 6.0, 2) > 0.56: return CON_D   # a few loose patches
    return CON

for f in bm.faces:
    f.material_index = INTERIOR if is_interior(f) else concrete_mat(f.calc_center_median(), f.normal)
bmesh.ops.triangulate(bm, faces=bm.faces[:])   # colours were picked per square cell, so patch edges step like the reference
me = bpy.data.meshes.new('Concrete'); bm.to_mesh(me); bm.free()
concrete = new_obj('Concrete', me)

# ---------------------------------------------------------------- door frame, door, hinges, handle
x0, x1 = DXC - DW / 2, DXC + DW / 2
yb = FY + ND                                     # niche back face
box('JambL', (x0 - 0.07, yb - 0.035, FLOOR), (x0 + 0.005, yb + 0.12, FLOOR + DH + 0.07), STEEL, 0.008)
box('JambR', (x1 - 0.005, yb - 0.035, FLOOR), (x1 + 0.07, yb + 0.12, FLOOR + DH + 0.07), STEEL, 0.008)
box('Head', (x0 - 0.07, yb - 0.035, FLOOR + DH - 0.005), (x1 + 0.07, yb + 0.12, FLOOR + DH + 0.07), STEEL, 0.008)
box('Threshold', (x0, yb - 0.04, FLOOR - 0.01), (x1, yb + 0.20, FLOOR + 0.015), STEEL, 0.005)

DOOR_W, DOOR_H, DOOR_T = 0.97, 2.07, 0.05
dme = bpy.data.meshes.new('Door'); bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((DOOR_W / 2, -DOOR_T / 2, DOOR_H / 2)) @ Matrix.Diagonal((DOOR_W, DOOR_T, DOOR_H, 1)))
bmesh.ops.bevel(bm, geom=bm.edges[:] + bm.verts[:], offset=0.008, segments=2, affect='EDGES', profile=0.5)
cellify(bm, 0.08, lambda f: abs(f.normal.y) > 0.7)
for f in bm.faces:
    c = f.calc_center_median(); e = min(c.x, DOOR_W - c.x, c.z, DOOR_H - c.z)
    side = 0.0 if f.normal.y < 0 else 13.0
    v = fbm(c.x * 3.2 + side, c.z * 1.4, 2.0, 3) + max(0.0, 0.16 - e) * 4.0 + max(0.0, 0.7 - c.z) * 0.5
    f.material_index = RUST_D if v > 0.75 else RUST if v > 0.42 else STEEL
bmesh.ops.triangulate(bm, faces=bm.faces[:])
# stiffener ribs on the inside face read through the gap
bm.to_mesh(dme); bm.free()
door = new_obj('Door', dme)
OPEN = math.radians(-88)
door_m = Matrix.Translation((x0 + 0.01, yb - 0.04, FLOOR + 0.015)) @ Matrix.Rotation(OPEN, 4, 'Z')
door.data.transform(door_m)
def on_door(lo, hi, idx, bevel=0.004):   # boxes in door-local coordinates
    o = box('DoorPart', lo, hi, idx, bevel, 1); o.data.transform(door_m); return o
on_door((DOOR_W - 0.13, -DOOR_T - 0.012, 0.98), (DOOR_W - 0.07, -DOOR_T, 1.22), PIPE)          # backplate
on_door((DOOR_W - 0.24, -DOOR_T - 0.06, 1.13), (DOOR_W - 0.08, -DOOR_T - 0.035, 1.155), PIPE)  # lever
on_door((DOOR_W - 0.11, -DOOR_T - 0.045, 1.12), (DOOR_W - 0.09, -DOOR_T - 0.01, 1.165), PIPE)  # lever boss
on_door((DOOR_W - 0.12, -DOOR_T - 0.008, 1.02), (DOOR_W - 0.08, -DOOR_T, 1.06), STEEL)         # key plate
for z in (0.22, 1.05, 1.86):                     # hinges: knuckle on the jamb + leaf on the door
    lathe('Hinge', [(0.0, 0, PIPE), (0.022, 0, PIPE), (0.022, 0.16, PIPE), (0.0, 0.16, PIPE)], 10,
          (x0 - 0.005, yb - 0.055, FLOOR + 0.015 + z))
    on_door((0.0, -DOOR_T - 0.008, z + 0.01), (0.14, -DOOR_T, z + 0.15), RUST)

# ---------------------------------------------------------------- barred window
for k in range(5):
    x = WINX - 0.36 + k * 0.18
    lathe('Bar', [(0.0, 0, RUST), (0.02, 0, RUST), (0.02, 1.02, RUST), (0.0, 1.02, RUST)], 10,
          (x, FY - 0.045, WIN_Z[0] - 0.04))
for z in (WIN_Z[0] + 0.12, WIN_Z[1] - 0.12):
    box('BarFlat', (WINX - 0.56, FY - 0.075, z - 0.025), (WINX + 0.56, FY - 0.055, z + 0.025), RUST, 0.004, 1)
    for sx in (-1, 1):
        box('Tab', (WINX + sx * 0.60 - 0.055, FY - 0.03, z - 0.055), (WINX + sx * 0.60 + 0.055, FY, z + 0.055), RUST_D, 0.006, 1)
        b = lathe('Bolt', [(0.0, 0, PIPE), (0.016, 0, PIPE), (0.016, 0.022, PIPE), (0.0, 0.022, PIPE)], 8)
        b.data.transform(Matrix.Translation((WINX + sx * 0.60, FY - 0.03, z)) @ Matrix.Rotation(math.pi / 2, 4, 'X'))
        box('TabLink', (WINX + sx * 0.56 - 0.01, FY - 0.06, z - 0.02), (WINX + sx * 0.56 + 0.04 * sx + 0.01, FY - 0.02, z + 0.02), RUST, 0.0)

# ---------------------------------------------------------------- roof vent (rusty stack with louvres and a cap)
VX, VY, Z0 = 1.15, -1.25, SLAB[1]
vp = [(0.00, 0.00, RUST_D), (0.36, 0.00, RUST_D), (0.36, 0.035, RUST_D), (0.27, 0.045, RUST)]
z = 0.045
vp.append((0.27, 0.16, RUST)); z = 0.16
for k in range(4):                               # louvre band: recessed dark slots between slats
    vp += [(0.27, z, RUST_D), (0.235, z + 0.005, RUST_D), (0.235, z + 0.04, RUST), (0.27, z + 0.045, RUST)]
    z += 0.065
vp += [(0.27, z + 0.04, RUST), (0.29, z + 0.05, RUST), (0.29, z + 0.07, RUST_D),   # top band
       (0.12, z + 0.07, RUST_D), (0.12, z + 0.10, RUST_D),                         # neck under the cap
       (0.42, z + 0.10, RUST), (0.43, z + 0.125, RUST), (0.22, z + 0.25, RUST), (0.05, z + 0.29, RUST), (0.0, z + 0.295, RUST)]
lathe('Vent', vp, 20, (VX, VY, Z0), cap_top=False, cap_bot=False)

# ---------------------------------------------------------------- conduit, clamps, junction box
CX = 2.15; PY = FY - 0.06
tube('Conduit', [(CX, PY, 1.70), (CX, PY, 2.66), (CX, -2.32, 2.80), (CX, -2.32, 3.24), (CX, -2.10, 3.25), (CX, -1.55, 3.25)], 0.034, PIPE, 10, 0.12)
box('JBox', (CX - 0.17, FY - 0.13, 1.18), (CX + 0.17, FY, 1.62), PIPE, 0.015, 2)
box('JBoxLid', (CX - 0.15, FY - 0.145, 1.20), (CX + 0.15, FY - 0.125, 1.60), STEEL, 0.006, 1)
lathe('Gland', [(0.0, 0, PIPE), (0.045, 0, PIPE), (0.045, 0.08, PIPE), (0.0, 0.08, PIPE)], 10, (CX, PY, 1.62))
for zc in (1.95, 2.45):
    box('Clamp', (CX - 0.09, FY - 0.035, zc - 0.03), (CX + 0.09, FY, zc + 0.03), PIPE, 0.006, 1)
    box('ClampBand', (CX - 0.05, PY - 0.045, zc - 0.022), (CX + 0.05, PY + 0.03, zc + 0.022), STEEL, 0.006, 1)
box('RoofClamp', (CX - 0.08, -1.80, SLAB[1]), (CX + 0.08, -1.70, SLAB[1] + 0.08), PIPE, 0.006, 1)

# ---------------------------------------------------------------- join (all parts carry the same slot list)
for o in scene.objects: o.select_set(False)
for o in parts: o.select_set(True)
bpy.context.view_layer.objects.active = concrete
bpy.ops.object.join()
mesh = concrete; mesh.name = 'Bunker_Mesh'
assert [m.name for m in mesh.data.materials] == [m.name for m in ORDER], 'material slots shuffled'
bm = bmesh.new(); bm.from_mesh(mesh.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0003)
bm.to_mesh(mesh.data); bm.free()
with bpy.context.temp_override(active_object=mesh, object=mesh, selected_objects=[mesh], selected_editable_objects=[mesh]):
    bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
tris = sum(len(p.vertices) - 2 for p in mesh.data.polygons)
used = sorted({p.material_index for p in mesh.data.polygons})
dims = mesh.dimensions
print(f'[bunker] triangles {tris}, materials {len(used)} {[ORDER[i].name for i in used]}, size {dims.x:.2f} x {dims.y:.2f} x {dims.z:.2f}')

root = bpy.data.objects.new('Bunker', None); scene.collection.objects.link(root); mesh.parent = root
for o in scene.objects: o.select_set(False)
root.select_set(True); mesh.select_set(True)
bpy.ops.export_scene.fbx(filepath=f'{OUT}/Bunker.fbx', use_selection=True, apply_unit_scale=True,
                         apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)

# ---------------------------------------------------------------- previews
world = bpy.data.worlds.new('W'); scene.world = world; world.use_nodes = True
wn = world.node_tree.nodes; wl = world.node_tree.links
wn['Background'].inputs['Color'].default_value = (0.62, 0.62, 0.64, 1)        # what lights the model
wn['Background'].inputs['Strength'].default_value = 0.55
bg_cam = wn.new('ShaderNodeBackground'); bg_cam.inputs['Color'].default_value = (0.68, 0.68, 0.69, 1)   # what the camera sees
lp = wn.new('ShaderNodeLightPath'); mix = wn.new('ShaderNodeMixShader')
wl.new(lp.outputs['Is Camera Ray'], mix.inputs['Fac']); wl.new(wn['Background'].outputs[0], mix.inputs[1])
wl.new(bg_cam.outputs[0], mix.inputs[2]); wl.new(mix.outputs[0], wn['World Output'].inputs['Surface'])
gme = bpy.data.meshes.new('Ground'); gbm = bmesh.new()
bmesh.ops.create_grid(gbm, x_segments=1, y_segments=1, size=60); gbm.to_mesh(gme); gbm.free()
ground = bpy.data.objects.new('Ground', gme); scene.collection.objects.link(ground)
gm = bpy.data.materials.new('GroundM'); gm.use_nodes = True
gm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.42, 0.42, 0.43, 1)
gm.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 1.0
gme.materials.append(gm)
ground.visible_camera = False   # seamless studio backdrop like the reference
sun_d = bpy.data.lights.new('Sun', 'SUN'); sun_d.energy = 3.4; sun_d.angle = math.radians(12)
sun = bpy.data.objects.new('Sun', sun_d); scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(50), 0, math.radians(32))
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x, scene.render.resolution_y = 1672, 941
scene.view_settings.view_transform = 'Standard'
cam_d = bpy.data.cameras.new('Cam'); cam = bpy.data.objects.new('Cam', cam_d); scene.collection.objects.link(cam); scene.camera = cam
def shoot(name, loc, target, lens=50, ortho=None):
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    if ortho: cam_d.type = 'ORTHO'; cam_d.ortho_scale = ortho
    else: cam_d.type = 'PERSP'; cam_d.lens = lens
    scene.render.filepath = f'{OUT}/{name}.png'; bpy.ops.render.render(write_still=True)

shoot('render-34', (-6.0, -12.1, 3.0), (0.25, 0, 1.55), 45)
shoot('render-side', (0, -16, 1.97), (0, 0, 1.97), ortho=7.5)

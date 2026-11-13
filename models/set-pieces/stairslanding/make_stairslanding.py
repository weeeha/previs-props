# Modular set pieces, wave 3 (floortile, doordouble, elevatordoors, stairslanding, curtains), Opus. Own designs, CC0.
# Helpers and the export/render tail are copied unchanged from library/wall3m/make_wall3m.py, so the parts match the
# wall kit: walls 0.15 m thick, 2.7 m tall, same skirting, lining and architrave, 1 m grid.
# One script builds all five; each folder holds a copy named make_<name>.py.
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_floortile.py -- <library dir> [names...]
import bpy, bmesh, sys, math, os, subprocess
from mathutils import Vector, Matrix

ARGS = sys.argv[sys.argv.index('--') + 1:]
LIB = ARGS[0]
ALL = ['wall1m', 'wall3m', 'walldoorway', 'wallwindow', 'doorinterior', 'doorsteel', 'windowframe',
       'stairs', 'railing', 'fencechainlink', 'fencewood', 'pillar']
NAMES = ARGS[1:] or ALL + ['kit']
PASCAL = {'wall1m': 'Wall1m', 'wall3m': 'Wall3m', 'walldoorway': 'WallDoorway', 'wallwindow': 'WallWindow',
          'doorinterior': 'DoorInterior', 'doorsteel': 'DoorSteel', 'windowframe': 'WindowFrame', 'stairs': 'Stairs',
          'railing': 'Railing', 'fencechainlink': 'FenceChainLink', 'fencewood': 'FenceWood', 'pillar': 'Pillar'}

# ---------------------------------------------------------------- materials (shared names across the library)
MATS = [  # name, linear rgb, roughness, metallic, alpha
    ('WallPaint', (0.40, 0.37, 0.33), 0.9, 0.0, 1.0),
    ('Skirting', (0.085, 0.080, 0.072), 0.7, 0.0, 1.0),
    ('Trim', (0.62, 0.60, 0.56), 0.6, 0.0, 1.0),
    ('Steel', (0.50, 0.51, 0.52), 0.45, 0.2, 1.0),
    ('Black', (0.012, 0.012, 0.013), 0.8, 0.0, 1.0),
    ('Glass', (0.30, 0.36, 0.38), 0.1, 0.0, 0.42),
    ('Wood', (0.32, 0.19, 0.09), 0.8, 0.0, 1.0),
    ('WoodDark', (0.16, 0.095, 0.048), 0.85, 0.0, 1.0),
    ('DoorPaint', (0.50, 0.46, 0.40), 0.6, 0.0, 1.0),
    ('SteelPaint', (0.11, 0.15, 0.17), 0.55, 0.2, 1.0),
    ('Concrete', (0.262, 0.232, 0.198), 0.95, 0.0, 1.0),
]
I = {m[0]: i for i, m in enumerate(MATS)}

def get_mat(i):
    name, rgb, rough, metal, alpha = MATS[i]
    m = bpy.data.materials.get(name)
    if m: return m
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*rgb, 1); b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if alpha < 1:
        b.inputs['Alpha'].default_value = alpha; m.surface_render_method = 'BLENDED'
    m.diffuse_color = (*rgb, alpha)
    return m

# ---------------------------------------------------------------- geometry helpers
class Builder:
    def __init__(s): s.bm = bmesh.new()
    def add(s, tbm, idx=None, M=None):
        if idx is not None:
            for f in tbm.faces: f.material_index = idx
        if M is not None: bmesh.ops.transform(tbm, matrix=M, verts=tbm.verts[:])
        me = bpy.data.meshes.new('tmp'); tbm.to_mesh(me); tbm.free()
        s.bm.from_mesh(me); bpy.data.meshes.remove(me)

def cube(lo, hi, bevel=0.0, segs=2):
    c = [(lo[i] + hi[i]) / 2 for i in range(3)]; sz = [hi[i] - lo[i] for i in range(3)]
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((*sz, 1)))
    if bevel:
        bmesh.ops.bevel(bm, geom=bm.edges[:] + bm.verts[:], offset=min(bevel, min(sz) * 0.45), segments=segs,
                        affect='EDGES', profile=0.5, clamp_overlap=True)
    return bm

def box(B, lo, hi, idx, bevel=0.0, segs=2, M=None):
    B.add(cube(lo, hi, bevel, segs), idx, M)

def lathe_bm(prof, n):
    """prof: [(r, z)] bottom to top; r == 0 makes a pole; open ends are capped with an n-gon."""
    bm = bmesh.new(); rings = []
    for r, z in prof:
        if r < 1e-6: rings.append([bm.verts.new((0, 0, z))])
        else: rings.append([bm.verts.new((r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n), z)) for k in range(n)])
    for a, b in zip(rings, rings[1:]):
        for k in range(n):
            if len(a) == 1 and len(b) == 1: continue
            if len(a) == 1: bm.faces.new([a[0], b[k], b[(k + 1) % n]])
            elif len(b) == 1: bm.faces.new([a[k], a[(k + 1) % n], b[0]])
            else: bm.faces.new([a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]])
    if len(rings[0]) > 1: bm.faces.new(rings[0][::-1])
    if len(rings[-1]) > 1: bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm

AXIS = {'Z': Matrix.Identity(4), 'X': Matrix.Rotation(math.pi / 2, 4, 'Y'), 'Y': Matrix.Rotation(-math.pi / 2, 4, 'X'),
        '-Y': Matrix.Rotation(math.pi / 2, 4, 'X')}

def lathe(B, prof, n, base, idx, axis='Z', M=None):
    m = Matrix.Translation(base) @ AXIS[axis]
    if M is not None: m = M @ m
    B.add(lathe_bm(prof, n), idx, m)

def cyl(B, base, length, r, idx, n=16, axis='Z', M=None):
    lathe(B, [(r, 0), (r, length)], n, base, idx, axis, M)

def prism(B, pts, d0, d1, idx, plane='XZ', M=None):
    """Extrude a 2D outline. plane 'XZ': (x, z) points, extruded along Y; 'YZ': (y, z) points, extruded along X."""
    bm = bmesh.new()
    def v(a, b, d): return bm.verts.new((a, d, b) if plane == 'XZ' else (d, a, b))
    lo = [v(a, b, d0) for a, b in pts]; hi = [v(a, b, d1) for a, b in pts]; n = len(pts)
    bm.faces.new(lo); bm.faces.new(hi[::-1])
    for k in range(n): bm.faces.new([lo[k], lo[(k + 1) % n], hi[(k + 1) % n], hi[k]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    B.add(bm, idx, M)

def strip(B, p0, p1, w, yc, t, idx, M=None):
    """Thin bar in the XZ plane from p0 to p1 (x, z), width w, thickness t along Y centred at yc."""
    p0, p1 = Vector(p0), Vector(p1); d = (p1 - p0).normalized(); nrm = Vector((-d.y, d.x)) * (w / 2)
    prism(B, [p0 - nrm, p1 - nrm, p1 + nrm, p0 + nrm], yc - t / 2, yc + t / 2, idx, 'XZ', M)

def carved(B, tbm, cutters, idx, M=None):
    """Exact-boolean DIFFERENCE of cutter boxes [(lo, hi)] from tbm, then merged into B."""
    for f in tbm.faces: f.material_index = idx
    me = bpy.data.meshes.new('carve'); tbm.to_mesh(me); tbm.free()
    o = bpy.data.objects.new('carve', me); bpy.context.scene.collection.objects.link(o)
    for lo, hi in cutters:
        cb = cube(lo, hi); cme = bpy.data.meshes.new('cut'); cb.to_mesh(cme); cb.free()
        c = bpy.data.objects.new('cut', cme); bpy.context.scene.collection.objects.link(c)
        mod = o.modifiers.new('b', 'BOOLEAN'); mod.operation = 'DIFFERENCE'; mod.object = c; mod.solver = 'EXACT'
        bpy.context.view_layer.objects.active = o
        with bpy.context.temp_override(active_object=o, object=o):
            bpy.ops.object.modifier_apply(modifier='b')
        bpy.data.objects.remove(c); bpy.data.meshes.remove(cme)
    bm = bmesh.new(); bm.from_mesh(o.data)
    bpy.data.objects.remove(o); bpy.data.meshes.remove(me)
    B.add(bm, idx, M)

# ---------------------------------------------------------------- shared wall parts
T, H = 0.15, 2.70
SK_H, SK_P = 0.10, 0.012          # skirting height and projection

def wall_body(B, w, holes=(), M=None):
    carved(B, cube((-w / 2, -T / 2, 0), (w / 2, T / 2, H), 0.006, 2),
           [((x0, -1, z0), (x1, 1, z1)) for x0, x1, z0, z1 in holes], I['WallPaint'], M)

def skirting(B, w, gaps=(), M=None):
    spans = [(-w / 2, w / 2)]
    for g0, g1 in gaps:
        spans = [s for a, b in spans for s in ((a, min(b, g0)), (max(a, g1), b)) if s[1] - s[0] > 0.01]
    for a, b in spans:
        for y0, y1 in ((-T / 2 - SK_P, -T / 2 + 0.002), (T / 2 - 0.002, T / 2 + SK_P)):
            box(B, (a, y0, 0), (b, y1, SK_H), I['Skirting'], 0.003, 1, M)

def build_wall1m(B, M=None):
    wall_body(B, 1.0, M=M); skirting(B, 1.0, M=M)

def build_wall3m(B, M=None):
    wall_body(B, 3.0, M=M); skirting(B, 3.0, M=M)

OW, OH = 0.904, 2.102     # doorway clear opening (door leaf 0.9 x 2.1 with a hair of gap)
LIN, ARC, ARP = 0.03, 0.07, 0.018   # lining thickness, architrave width and projection

def build_walldoorway(B, M=None):
    hw = OW / 2 + LIN
    wall_body(B, 3.0, [(-hw, hw, -1, OH + LIN)], M)
    tr = I['Trim']
    box(B, (-hw, -T / 2, 0), (-OW / 2, T / 2, OH + LIN), tr, 0.003, 1, M)        # lining
    box(B, (OW / 2, -T / 2, 0), (hw, T / 2, OH + LIN), tr, 0.003, 1, M)
    box(B, (-hw, -T / 2, OH), (hw, T / 2, OH + LIN), tr, 0.003, 1, M)
    ax0, ax1 = OW / 2 + 0.005, OW / 2 + 0.005 + ARC
    for y0, y1 in ((-T / 2 - ARP, -T / 2 + 0.002), (T / 2 - 0.002, T / 2 + ARP)):   # architraves, both faces
        box(B, (-ax1, y0, 0), (-ax0, y1, OH + 0.005 + ARC), tr, 0.005, 2, M)
        box(B, (ax0, y0, 0), (ax1, y1, OH + 0.005 + ARC), tr, 0.005, 2, M)
        box(B, (-ax1, y0, OH + 0.005), (ax1, y1, OH + 0.005 + ARC), tr, 0.005, 2, M)
    skirting(B, 3.0, [(-ax1, ax1)], M)

WIN_W, WIN_Z = 1.20, 0.90
# ---------------------------------------------------------------- doors (origin at the hinge edge, on the floor)
DW, DH = 0.90, 2.10

def lever(B, x, z, yf, face, M=None):
    """Rose + lever handle on one face of a leaf: yf = face plane y, face = -1 (front) or +1 (back)."""
    st = I['Steel']; ax = 'Y' if face > 0 else '-Y'
    lathe(B, [(0.028, 0), (0.028, 0.006), (0.022, 0.011), (0, 0.011)], 20, (x, yf, z), st, ax, M)
    cyl(B, (x, yf, z), 0.055, 0.009, st, 12, ax, M)
    yl = yf + face * 0.05
    box(B, (x - 0.125, yl - 0.009, z - 0.011), (x + 0.012, yl + 0.009, z + 0.011), st, 0.008, 2, M)

def build_doorinterior(B, M=None):
    t = 0.045; dp = I['DoorPaint']; z0 = 0.004
    box(B, (0.002, -0.012, z0), (DW - 0.002, 0.012, DH), dp, 0.0, 1, M)      # core (panel plane)
    S, TR, MR, BR = 0.11, 0.11, 0.17, 0.21
    zl = 0.92                                                                    # lock rail centre
    members = [(0, S, z0, DH), (DW - S, DW, z0, DH), (S, DW - S, DH - TR, DH), (S, DW - S, zl - MR / 2, zl + MR / 2),
               (S, DW - S, z0, z0 + BR), (DW / 2 - 0.045, DW / 2 + 0.045, z0 + BR, zl - MR / 2),
               (DW / 2 - 0.045, DW / 2 + 0.045, zl + MR / 2, DH - TR)]
    for x0, x1, a, b in members:
        box(B, (x0, -t / 2, a), (x1, t / 2, b), dp, 0.003, 1, M)
    for x0, x1 in ((S, DW / 2 - 0.045), (DW / 2 + 0.045, DW - S)):              # raised fields, both faces
        for a, b in ((z0 + BR, zl - MR / 2), (zl + MR / 2, DH - TR)):
            box(B, (x0 + 0.018, -0.017, a + 0.018), (x1 - 0.018, 0.017, b - 0.018), dp, 0.012, 2, M)
    for f in (-1, 1): lever(B, DW - 0.065, 1.0, f * t / 2, f, M)
    for zc in (0.22, 1.05, 1.88):                                                # hinge knuckles on the hinge edge
        cyl(B, (0.0, t / 2 + 0.002, zc - 0.05), 0.10, 0.008, I['Steel'], 12, 'Z', M)
        box(B, (0.0, t / 2 - 0.002, zc - 0.05), (0.03, t / 2 + 0.002, zc + 0.05), I['Steel'], 0.0, 1, M)


# ================================================================ set pieces wave 3 (floortile, doordouble,
# elevatordoors, stairslanding, curtains). Helpers above are the wall3m kit's, unchanged, so wall thickness,
# height, skirting, lining and architrave sizes match exactly.
ALL = ['floortile', 'doordouble', 'elevatordoors', 'stairslanding', 'curtains']
NAMES = ARGS[1:] or ALL
PASCAL = {'floortile': 'FloorTile', 'doordouble': 'DoorDouble', 'elevatordoors': 'ElevatorDoors',
          'stairslanding': 'StairsLanding', 'curtains': 'Curtains'}
MATS = MATS + [
    ('WoodLight', (0.56, 0.36, 0.18), 0.75, 0.0, 1.0),
    ('WoodLightAlt', (0.53, 0.335, 0.165), 0.75, 0.0, 1.0),
    ('Stainless', (0.64, 0.65, 0.66), 0.3, 0.55, 1.0),
    ('Amber', (0.95, 0.42, 0.04), 0.4, 0.0, 1.0),
    ('Fabric', (0.20, 0.29, 0.36), 0.95, 0.0, 1.0),
]
I = {m[0]: i for i, m in enumerate(MATS)}
ANGLE = {'curtains': 70}                       # auto-smooth angle per model (folds need a wider one)
VIEW = {'floortile': (-0.55, -1.0, 0.95)}      # camera direction per model (default three-quarter)
_get_mat = get_mat
def get_mat(i):
    m = _get_mat(i)
    if MATS[i][0] == 'Amber':                  # lit buttons and indicator glow a little
        b = m.node_tree.nodes['Principled BSDF']
        b.inputs['Emission Color'].default_value = (1.0, 0.45, 0.05, 1); b.inputs['Emission Strength'].default_value = 2.0
    return m

def tube(B, p0, p1, r, idx, n=12, M=None):
    p0, p1 = Vector(p0), Vector(p1); d = p1 - p0
    m = Matrix.Translation(p0) @ d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    B.add(lathe_bm([(0, 0), (r, 0), (r, d.length), (0, d.length)], n), idx, m if M is None else M @ m)

# ---------------------------------------------------------------- floortile: 3 x 3 m, top at z = 0
def build_floortile(B, M=None):
    S, TH, G, PW = 3.0, 0.10, 0.004, 0.15      # size, thickness, groove width/depth, plank width
    box(B, (-S / 2, -S / 2, -TH), (S / 2, S / 2, -G), I['WoodDark'], 0.004, 1, M)      # slab, groove colour on top
    offs = [0.0, 0.55, 1.05, 0.3, 0.8, 0.15, 0.95, 0.45]                               # staggered butt joints
    L = 1.2
    for r in range(int(S / PW)):
        y0 = -S / 2 + r * PW; y1 = y0 + PW
        cuts = [-S / 2] + [x for x in (-S / 2 + offs[r % 8] + k * L for k in range(-1, 4)) if -S / 2 + 0.2 < x < S / 2 - 0.2] + [S / 2]
        for j, (a, b) in enumerate(zip(cuts, cuts[1:])):
            mat = I['WoodLight'] if (r * 3 + j) % 3 else I['WoodLightAlt']
            box(B, (a + G / 2 if a > -S / 2 else a, y0 + G / 2 if r else y0, -G),
                (b - G / 2 if b < S / 2 else b, y1 - G / 2 if r < int(S / PW) - 1 else y1, 0.0), mat, 0.0, 1, M)

def leaf_light(B, M=None):
    """doorinterior's four-panel leaf at about a third of the triangles (unbevelled stiles, single-segment fields)."""
    t = 0.045; dp = I['DoorPaint']; st = I['Steel']; z0 = 0.004
    box(B, (0.002, -0.012, z0), (DW - 0.002, 0.012, DH), dp, 0.0, 1, M)
    S, TR, MR, BR = 0.11, 0.11, 0.17, 0.21; zl = 0.92
    for x0, x1, a, b in [(0, S, z0, DH), (DW - S, DW, z0, DH), (S, DW - S, DH - TR, DH), (S, DW - S, zl - MR / 2, zl + MR / 2),
                         (S, DW - S, z0, z0 + BR), (DW / 2 - 0.045, DW / 2 + 0.045, z0 + BR, zl - MR / 2),
                         (DW / 2 - 0.045, DW / 2 + 0.045, zl + MR / 2, DH - TR)]:
        box(B, (x0, -t / 2, a), (x1, t / 2, b), dp, 0.0, 1, M)
    for x0, x1 in ((S, DW / 2 - 0.045), (DW / 2 + 0.045, DW - S)):
        for a, b in ((z0 + BR, zl - MR / 2), (zl + MR / 2, DH - TR)):
            box(B, (x0 + 0.018, -0.017, a + 0.018), (x1 - 0.018, 0.017, b - 0.018), dp, 0.012, 1, M)
    x, z = DW - 0.065, 1.0
    for f in (-1, 1):
        ax = 'Y' if f > 0 else '-Y'; yf = f * t / 2
        lathe(B, [(0.028, 0), (0.028, 0.006), (0.02, 0.011), (0, 0.011)], 8, (x, yf, z), st, ax, M)
        cyl(B, (x, yf, z), 0.055, 0.009, st, 6, ax, M)
        yl = yf + f * 0.05
        box(B, (x - 0.125, yl - 0.009, z - 0.011), (x + 0.012, yl + 0.009, z + 0.011), st, 0.008, 1, M)
    for zc in (0.25, 1.85):
        cyl(B, (0.0, t / 2 + 0.002, zc - 0.05), 0.10, 0.008, st, 8, 'Z', M)

# ---------------------------------------------------------------- doordouble: two 0.9 x 2.1 leaves, origin bottom centre
def build_doordouble(B, M=None):
    W2 = 2 * DW + 0.004; hw = W2 / 2 + LIN; tr = I['Trim']
    box(B, (-hw, -T / 2, 0), (-W2 / 2, T / 2, OH + LIN), tr, 0.0, 1, M)              # lining (wall-thick frame)
    box(B, (W2 / 2, -T / 2, 0), (hw, T / 2, OH + LIN), tr, 0.0, 1, M)
    box(B, (-hw, -T / 2, OH), (hw, T / 2, OH + LIN), tr, 0.0, 1, M)
    box(B, (-W2 / 2, -0.035, OH - 0.012), (W2 / 2, -0.0235, OH), tr, 0.0, 1, M)         # door stop at the head
    ax0, ax1 = W2 / 2 + 0.005, W2 / 2 + 0.005 + ARC
    for y0, y1 in ((-T / 2 - ARP, -T / 2 + 0.002), (T / 2 - 0.002, T / 2 + ARP)):     # architraves, both faces
        box(B, (-ax1, y0, 0), (-ax0, y1, OH + 0.005 + ARC), tr, 0.005, 1, M)
        box(B, (ax0, y0, 0), (ax1, y1, OH + 0.005 + ARC), tr, 0.005, 1, M)
        box(B, (-ax1, y0, OH + 0.005), (ax1, y1, OH + 0.005 + ARC), tr, 0.005, 1, M)
    def mm(m): return m if M is None else M @ m
    leaf_light(B, mm(Matrix.Translation((-W2 / 2 + 0.001, 0, 0))))
    leaf_light(B, mm(Matrix.Translation((W2 / 2 - 0.001, 0, 0)) @ Matrix.Rotation(math.pi, 4, 'Z')))
    box(B, (-0.002, -0.0225 - 0.008, 0.004), (0.022, -0.0225, DH), I['DoorPaint'], 0.003, 1, M)   # astragal on the meeting edge

# ---------------------------------------------------------------- elevatordoors: 3 m wall, 1.1 x 2.1 lift entrance
def build_elevatordoors(B, M=None):
    EW, EH, LN = 1.10, 2.10, 0.02
    st, ss, bk, am = I['Steel'], I['Stainless'], I['Black'], I['Amber']
    wall_body(B, 3.0, [(-EW / 2 - LN, EW / 2 + LN, -1, EH + LN)], M)
    box(B, (-EW / 2 - LN, -T / 2, 0), (-EW / 2, T / 2, EH + LN), st, 0.0, 1, M)         # steel lining in the opening
    box(B, (EW / 2, -T / 2, 0), (EW / 2 + LN, T / 2, EH + LN), st, 0.0, 1, M)
    box(B, (-EW / 2 - LN, -T / 2, EH), (EW / 2 + LN, T / 2, EH + LN), st, 0.0, 1, M)
    yf = -T / 2; FW, FP = 0.09, 0.025                                                    # portal frame on the front face
    box(B, (-EW / 2 - LN - FW, yf - FP, 0), (-EW / 2 - LN + 0.004, yf + 0.002, EH + LN), st, 0.006, 1, M)
    box(B, (EW / 2 + LN - 0.004, yf - FP, 0), (EW / 2 + LN + FW, yf + 0.002, EH + LN), st, 0.006, 1, M)
    box(B, (-EW / 2 - LN - FW, yf - FP - 0.006, EH + LN - 0.004), (EW / 2 + LN + FW, yf + 0.002, EH + LN + 0.13), st, 0.008, 2, M)
    for s in (-1, 1):                                                                     # two sliding leaves, closed
        x0, x1 = sorted((s * 0.0015, s * (EW / 2 + LN / 2)))
        box(B, (x0, -0.03, 0.006), (x1, -0.006, EH + 0.005), ss, 0.003, 1, M)
        xe = s * (EW / 2 - 0.06)                                                          # vertical seam line on each leaf
        box(B, (xe - 0.002, -0.0315, 0.04), (xe + 0.002, -0.029, EH - 0.04), st, 0.0, 1, M)
    box(B, (-EW / 2 - LN - FW, yf - 0.10, 0), (EW / 2 + LN + FW, -0.006, 0.008), st, 0.002, 1, M)   # threshold plate
    box(B, (-EW / 2, -0.045, 0.006), (EW / 2, -0.037, 0.0095), bk, 0.0, 1, M)              # leaf track groove
    px, pz = EW / 2 + LN + FW + 0.16, 1.10                                                # call button panel
    box(B, (px - 0.06, yf - 0.012, pz - 0.16), (px + 0.06, yf + 0.002, pz + 0.16), ss, 0.006, 2, M)
    for zc in (pz + 0.055, pz - 0.055):
        lathe(B, [(0.026, 0), (0.026, 0.006), (0.021, 0.008), (0, 0.008)], 12, (px, yf - 0.012, zc), st, '-Y', M)
        lathe(B, [(0.016, 0), (0.016, 0.006), (0.012, 0.009), (0, 0.009)], 12, (px, yf - 0.018, zc), am, '-Y', M)
    iz = EH + LN + 0.13 + 0.08                                                            # floor indicator over the header
    box(B, (-0.21, yf - 0.03, iz), (0.21, yf + 0.002, iz + 0.13), ss, 0.006, 2, M)
    box(B, (-0.18, yf - 0.035, iz + 0.025), (0.18, yf - 0.028, iz + 0.105), bk, 0.0, 1, M)
    yd = yf - 0.037
    prism(B, [(-0.15, iz + 0.04), (-0.11, iz + 0.04), (-0.13, iz + 0.09)], yd, yd + 0.004, am, 'XZ', M)   # up arrow
    for k in range(6):                                                                    # position dots, one lit
        x = -0.07 + k * 0.045
        box(B, (x - 0.012, yd, iz + 0.055), (x + 0.012, yd + 0.004, iz + 0.075), am if k == 2 else st, 0.0, 1, M)
    skirting(B, 3.0, [(-EW / 2 - LN - FW, EW / 2 + LN + FW)], M)

# ---------------------------------------------------------------- stairslanding: 8 steps, 1 x 1 landing, 8 steps at 90 deg
def build_stairslanding(B, M=None):
    n, go, w = 17, 0.25, 1.0; r = H / n; cap = 0.03          # 17 risers of 0.159 m; footprint exactly 3 x 3 m
    co, wd, bk = I['Concrete'], I['Wood'], I['Black']
    def tread(lo, hi, z, nose):                                # Wood cap with a black anti-slip strip on the nosing
        box(B, (lo[0], lo[1], 0), (hi[0], hi[1], z - cap), co, 0.0, 1, M)
        l2, h2 = list(lo), list(hi)
        if nose == '-Y': l2[1] -= 0.025
        if nose == '+X': h2[0] += 0.025
        box(B, (l2[0], l2[1], z - cap), (h2[0], h2[1], z), wd, 0.006, 1, M)
        if nose == '-Y': box(B, (lo[0] + 0.03, l2[1] - 0.002, z - 0.004), (hi[0] - 0.03, l2[1] + 0.05, z + 0.002), bk, 0.0, 1, M)
        if nose == '+X': box(B, (h2[0] - 0.05, lo[1] + 0.03, z - 0.004), (h2[0] + 0.002, hi[1] - 0.03, z + 0.002), bk, 0.0, 1, M)
    for k in range(8):                                         # flight 1: runs toward +Y along x 0.5..1.5
        y0 = -1.5 + k * go; tread((0.5, y0), (1.5, y0 + go), (k + 1) * r, '-Y')
    tread((0.5, 0.5), (1.5, 1.5), 9 * r, '-Y')                 # landing
    for k in range(8):                                         # flight 2: turns left, runs toward -X along y 0.5..1.5
        x1 = 0.5 - k * go; tread((x1 - go, 0.5), (x1, 1.5), (10 + k) * r, '+X')
    st, hr = I['Steel'], 0.90                                  # handrail on the open inner edges
    xi, yi = 0.54, 0.54
    def nz1(y): return r * (1 + (y + 1.5) / go)                # flight 1 nosing line
    def nz2(x): return r * (10 + (0.5 - x) / go)               # flight 2 nosing line
    posts = [((xi, -1.44), r), ((xi, yi), 9 * r), ((-1.44, yi), 17 * r)]
    tops = [nz1(-1.44) + hr, 10 * r + hr + 0.04, 17 * r + hr]
    posts += [((xi, -0.5), nz1(-0.5) - r), ((-0.5, yi), nz2(-0.5) - r)]          # one mid post per flight
    tops += [nz1(-0.5) + hr, nz2(-0.5) + hr]
    for ((x, y), z0), zt in zip(posts, tops):
        cyl(B, (x, y, z0), zt + 0.03 - z0, 0.022, st, 8, 'Z', M)
    for zo in (hr, hr * 0.5):                                  # top rail and mid rail
        tube(B, (xi, -1.44, nz1(-1.44) + zo), (xi, yi, nz1(yi) + zo), 0.022 if zo == hr else 0.012, st, 10 if zo == hr else 8, M)
        tube(B, (xi, yi, nz2(xi) + zo), (-1.44, yi, nz2(-1.44) + zo), 0.022 if zo == hr else 0.012, st, 10 if zo == hr else 8, M)

# ---------------------------------------------------------------- curtains: tab-top pair on a rod over wallwindow
WIN_W, WIN_Z = 1.20, 0.90
def curtain_panel(B, xa, xb, flare, yc, ztop, folds, M=None, th=0.012):
    NC, zs = 30, (ztop, (ztop + 0.012) * 0.5, 0.012)
    amps, spread = (0.022, 0.034, 0.046), (0.0, 0.5, 1.0)
    bm = bmesh.new(); F, Bk = [], []
    for zi, z in enumerate(zs):
        a = xa - flare[0] * spread[zi]; b = xb + flare[1] * spread[zi]; fr, bkr = [], []
        for c in range(NC + 1):
            u = c / NC; x = a + (b - a) * u
            y = yc + amps[zi] * math.sin(2 * math.pi * folds * u + 0.4 * zi)
            fr.append(bm.verts.new((x, y - th / 2, z))); bkr.append(bm.verts.new((x, y + th / 2, z)))
        F.append(fr); Bk.append(bkr)
    for zi in range(len(zs) - 1):
        for c in range(NC):
            bm.faces.new([F[zi][c], F[zi + 1][c], F[zi + 1][c + 1], F[zi][c + 1]])
            bm.faces.new([Bk[zi][c], Bk[zi][c + 1], Bk[zi + 1][c + 1], Bk[zi + 1][c]])
        for c in (0, NC):
            bm.faces.new([F[zi][c], Bk[zi][c], Bk[zi + 1][c], F[zi + 1][c]])
    for zi in (0, len(zs) - 1):
        for c in range(NC):
            bm.faces.new([F[zi][c], F[zi][c + 1], Bk[zi][c + 1], Bk[zi][c]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    B.add(bm, I['Fabric'], M)

def build_curtains(B, M=None):
    st, fb = I['Steel'], I['Fabric']
    yr = T / 2 + 0.10; zr = WIN_Z + WIN_W + 0.065 + 0.11; RX = 0.96
    lathe(B, [(0.0, -RX), (0.014, -RX), (0.014, RX), (0.0, RX)], 16, (0, yr, zr), st, 'X', M)        # rod
    for s in (-1, 1):
        prof = [(0, 0)] + [(0.034 * math.sin(math.pi * k / 6), 0.034 * (1 - math.cos(math.pi * k / 6))) for k in range(1, 6)] + [(0, 0.068)]
        prof = [(0.016, -0.012)] + [(0.016, 0.0)] + prof[1:]
        lathe(B, [(0, -0.012)] + prof, 10, (RX, yr, zr), st, 'X', M if s > 0 else
              (Matrix.Rotation(math.pi, 4, 'Z') if M is None else M @ Matrix.Rotation(math.pi, 4, 'Z')) @ Matrix.Translation((0, -2 * yr, 0)))
        bx = s * 0.80                                                                                 # wall brackets
        lathe(B, [(0.03, 0), (0.03, 0.008), (0.012, 0.012), (0, 0.012)], 12, (bx, T / 2, zr), st, 'Y', M)
        box(B, (bx - 0.008, T / 2 + 0.01, zr - 0.012), (bx + 0.008, yr, zr + 0.006), st, 0.003, 1, M)
    ztop = zr - 0.03
    for s in (-1, 1):                                          # half drawn: each panel covers 0.62 m, 0.56 m gap
        xa, xb = sorted((s * 0.92, s * 0.28))
        fl = (0.03, 0.05) if s < 0 else (0.05, 0.03)
        curtain_panel(B, xa, xb, fl, yr, ztop, 4.5, M)
        for k in range(6):                                     # tab loops over the rod
            x = xa + 0.02 + k * (xb - xa - 0.04) / 5
            box(B, (x - 0.022, yr - 0.02, ztop - 0.01), (x + 0.022, yr + 0.02, zr + 0.022), fb, 0.0, 1, M)

BUILD = {n: globals()['build_' + n] for n in ALL}
# ---------------------------------------------------------------- mesh object, export, render
def to_object(B, name):
    me = bpy.data.meshes.new(name + '_Mesh'); B.bm.to_mesh(me); B.bm.free()
    used = sorted({p.material_index for p in me.polygons})
    remap = {old: new for new, old in enumerate(used)}
    before = {}
    for p in me.polygons: before[MATS[p.material_index][0]] = before.get(MATS[p.material_index][0], 0) + 1
    for p in me.polygons: p.material_index = remap[p.material_index]
    for old in used: me.materials.append(get_mat(old))
    after = {}
    for p in me.polygons:
        k = me.materials[p.material_index].name; after[k] = after.get(k, 0) + 1
    assert before == after, 'material remap broke'
    o = bpy.data.objects.new(name + '_Mesh', me); bpy.context.scene.collection.objects.link(o)
    with bpy.context.temp_override(active_object=o, object=o, selected_objects=[o], selected_editable_objects=[o]):
        bpy.ops.object.shade_auto_smooth(angle=math.radians(CUR_ANGLE))
    return o

def stats(o):
    me = o.data; tris = sum(len(p.vertices) - 2 for p in me.polygons)
    co = [o.matrix_world @ v.co for v in me.vertices]
    lo = Vector([min(c[i] for c in co) for i in range(3)]); hi = Vector([max(c[i] for c in co) for i in range(3)])
    return tris, [m.name for m in me.materials], lo, hi

def setup_render(scene):
    world = bpy.data.worlds.new('W'); scene.world = world; world.use_nodes = True
    wn = world.node_tree.nodes; wl = world.node_tree.links
    wn['Background'].inputs['Color'].default_value = (0.62, 0.62, 0.64, 1)
    wn['Background'].inputs['Strength'].default_value = 0.55
    bg_cam = wn.new('ShaderNodeBackground'); bg_cam.inputs['Color'].default_value = (0.68, 0.68, 0.69, 1)
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
    ground.visible_camera = False
    sun_d = bpy.data.lights.new('Sun', 'SUN'); sun_d.energy = 3.4; sun_d.angle = math.radians(12)
    sun = bpy.data.objects.new('Sun', sun_d); scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(50), 0, math.radians(32))
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x, scene.render.resolution_y = 1672, 941
    scene.view_settings.view_transform = 'Standard'
    cam_d = bpy.data.cameras.new('Cam'); cam = bpy.data.objects.new('Cam', cam_d); scene.collection.objects.link(cam)
    scene.camera = cam
    return cam

def shoot(scene, cam, path, loc, target, lens=45):
    cam.location = loc; cam.data.lens = lens
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = path; bpy.ops.render.render(write_still=True)

def frame_shot(scene, cam, path, lo, hi, direction=(-0.55, -1.0, 0.38), lens=45):
    c = (lo + hi) / 2; r = (hi - lo).length / 2
    fov_v = 2 * math.atan(18 / (1672 / 941) / lens)
    d = Vector(direction).normalized() * (r / math.sin(fov_v / 2) * 1.0)
    shoot(scene, cam, path, c + d, c, lens)

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene

report = []
for name in NAMES:
    if name == 'kit': continue
    scene = reset(); out = os.path.join(LIB, name); os.makedirs(out, exist_ok=True)
    CUR_ANGLE = ANGLE.get(name, 35); B = Builder(); BUILD[name](B)
    mesh = to_object(B, PASCAL[name])
    tris, mats, lo, hi = stats(mesh)
    root = bpy.data.objects.new(PASCAL[name], None); scene.collection.objects.link(root); mesh.parent = root
    for o in scene.objects: o.select_set(False)
    root.select_set(True); mesh.select_set(True)
    bpy.ops.export_scene.fbx(filepath=f'{out}/{PASCAL[name]}.fbx', use_selection=True, apply_unit_scale=True,
                             apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)
    cam = setup_render(scene)
    frame_shot(scene, cam, f'{out}/render-34.png', lo, hi, VIEW.get(name, (-0.55, -1.0, 0.38)))
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', f'{out}/render-34.png', '-q:v', '3', f'{out}/compare.jpg'])
    line = (f'[setpiece3] {name}: tris {tris}, mats {len(mats)} {mats}, size {hi.x - lo.x:.3f} x {hi.y - lo.y:.3f} x '
            f'{hi.z - lo.z:.3f} m, bbox lo {tuple(round(v, 3) for v in lo)} hi {tuple(round(v, 3) for v in hi)}')
    print(line); report.append(line)

print('\n'.join(report))

# Modular set pieces for the VR Director previs library (own designs, CC0), Opus.
# One script builds all twelve; each model folder holds a copy named make_<name>.py.
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_wall3m.py -- <library dir> [names... | kit]
# 1 unit = 1 m, front toward -Y, up +Z. Walls run along X, 0.15 m thick, 2.7 m tall, origin at the bottom centre
# of the footprint, so they snap on a 1 m grid. Doors: origin at the hinge edge (leaf runs toward +X).
# windowframe: origin at the bottom centre of the frame; it sits at z = 0.9 in wallwindow (opening 1.2 x 1.2).
# Everything is built straight into one bmesh with material indices from a fixed list, so no join() and no
# material-slot shuffle; unused slots are dropped at the end with an explicit remap.
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
def build_windowframe(B, M=None):
    tr, F, D = I['Trim'], 0.06, 0.07
    hw = WIN_W / 2
    box(B, (-hw, -D / 2, 0), (hw, D / 2, F), tr, 0.004, 1, M)                         # sill member
    box(B, (-hw, -D / 2, WIN_W - F), (hw, D / 2, WIN_W), tr, 0.004, 1, M)             # head
    box(B, (-hw, -D / 2, F - 0.002), (-hw + F, D / 2, WIN_W - F + 0.002), tr, 0.004, 1, M)
    box(B, (hw - F, -D / 2, F - 0.002), (hw, D / 2, WIN_W - F + 0.002), tr, 0.004, 1, M)
    box(B, (-0.025, -D / 2 + 0.006, F - 0.002), (0.025, D / 2 - 0.006, WIN_W - F + 0.002), tr, 0.004, 1, M)   # mullion
    for x0, x1 in ((-hw + F, -0.025), (0.025, hw - F)):                                # glazing beads + glass
        for z0, z1, xa, xb in ((F, F + 0.018, x0, x1), (WIN_W - F - 0.018, WIN_W - F, x0, x1)):
            for ys in ((-0.022, -0.008), (0.008, 0.022)):
                box(B, (xa, ys[0], z0), (xb, ys[1], z1), tr, 0.0, 1, M)
        for xa, xb in ((x0, x0 + 0.018), (x1 - 0.018, x1)):
            for ys in ((-0.022, -0.008), (0.008, 0.022)):
                box(B, (xa, ys[0], F), (xb, ys[1], WIN_W - F), tr, 0.0, 1, M)
        box(B, (x0, -0.004, F), (x1, 0.004, WIN_W - F), I['Glass'], 0.0, 1, M)
    box(B, (0.03, D / 2, 0.56), (0.05, D / 2 + 0.018, 0.64), I['Steel'], 0.004, 1, M)   # casement handle (inside face)
    box(B, (0.035, D / 2 + 0.008, 0.54), (0.045, D / 2 + 0.03, 0.62), I['Steel'], 0.003, 1, M)
    box(B, (-hw - 0.004, -D / 2 - 0.014, -0.004), (hw + 0.004, -D / 2 + 0.002, 0.012), tr, 0.003, 1, M)   # drip

def build_wallwindow(B, M=None):
    hw = WIN_W / 2
    wall_body(B, 3.0, [(-hw, hw, WIN_Z, WIN_Z + WIN_W)], M)
    fm = Matrix.Translation((0, 0, WIN_Z)); build_windowframe(B, fm if M is None else M @ fm)
    tr = I['Trim']
    box(B, (-0.68, -T / 2 - 0.055, WIN_Z - 0.045), (0.68, -0.033, WIN_Z + 0.004), I['Concrete'], 0.008, 1, M)   # outside sill
    box(B, (-0.70, 0.036, WIN_Z - 0.005), (0.70, T / 2 + 0.035, WIN_Z + 0.022), tr, 0.005, 1, M)   # inside stool
    box(B, (-0.64, T / 2 - 0.002, WIN_Z - 0.09), (0.64, T / 2 + 0.014, WIN_Z - 0.005), tr, 0.004, 1, M)  # apron
    a = 0.065
    for x0, x1, z0, z1 in ((-hw - a, -hw, WIN_Z + 0.022, WIN_Z + WIN_W + a), (hw, hw + a, WIN_Z + 0.022, WIN_Z + WIN_W + a),
                           (-hw - a, hw + a, WIN_Z + WIN_W, WIN_Z + WIN_W + a)):          # inside architrave
        box(B, (x0, T / 2 - 0.002, z0), (x1, T / 2 + ARP, z1), tr, 0.005, 1, M)
    skirting(B, 3.0, M=M)

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

def build_doorsteel(B, M=None):
    t = 0.05; sp = I['SteelPaint']; st = I['Steel']; z0 = 0.004
    VX0, VX1, VZ0, VZ1 = DW / 2 - 0.13, DW / 2 + 0.13, 1.40, 1.80           # vision panel opening
    carved(B, cube((0.0, -t / 2, z0), (DW, t / 2, DH), 0.006, 1), [((VX0, -1, VZ0), (VX1, 1, VZ1))], sp, M)
    for s in (-1, 1):                                                            # bead frame round the glass, both faces
        y0, y1 = sorted((s * t / 2 - s * 0.002, s * (t / 2 + 0.012)))
        for lo, hi in (((VX0 - 0.03, y0, VZ0 - 0.03), (VX1 + 0.03, y1, VZ0)), ((VX0 - 0.03, y0, VZ1), (VX1 + 0.03, y1, VZ1 + 0.03)),
                       ((VX0 - 0.03, y0, VZ0), (VX0, y1, VZ1)), ((VX1, y0, VZ0), (VX1 + 0.03, y1, VZ1))):
            box(B, lo, hi, sp, 0.004, 1, M)
        box(B, (0.05, y0, z0 + 0.02), (DW - 0.05, y1 - s * 0.009, z0 + 0.27), st, 0.003, 1, M)     # kick plate
    box(B, (VX0, -0.003, VZ0), (VX1, 0.003, VZ1), I['Glass'], 0.0, 1, M)
    g = 0.032                                                                    # wire grid inside the glass
    x = VX0 + g
    while x < VX1 - 0.005:
        box(B, (x - 0.0015, -0.0045, VZ0), (x + 0.0015, 0.0045, VZ1), I['Black'], 0.0, 1, M); x += g
    z = VZ0 + g
    while z < VZ1 - 0.005:
        box(B, (VX0, -0.0045, z - 0.0015), (VX1, 0.0045, z + 0.0015), I['Black'], 0.0, 1, M); z += g
    # push bar on the back face (+Y): two end housings and a round bar
    yb = t / 2
    box(B, (0.10, yb, 0.94), (0.17, yb + 0.075, 1.06), sp, 0.012, 1, M)
    box(B, (DW - 0.24, yb, 0.92), (DW - 0.05, yb + 0.085, 1.08), sp, 0.014, 1, M)
    cyl(B, (0.16, yb + 0.05, 1.0), DW - 0.40 - 0.16 + 0.01, 0.022, st, 16, 'X', M)
    box(B, (DW - 0.25, yb + 0.03, 0.975), (DW - 0.20, yb + 0.07, 1.025), st, 0.008, 2, M)
    # pull handle on the front face (-Y)
    for zc in (0.90, 1.20):
        cyl(B, (DW - 0.10, -yb, zc), 0.06, 0.012, st, 12, '-Y', M)
    cyl(B, (DW - 0.10, -yb - 0.06, 0.88), 0.34, 0.016, st, 16, 'Z', M)
    box(B, (DW - 0.13, -yb - 0.008, 1.32), (DW - 0.07, -yb + 0.002, 1.40), st, 0.004, 1, M)          # key escutcheon
    lathe(B, [(0.009, 0), (0.009, 0.004), (0, 0.004)], 10, (DW - 0.10, -yb - 0.008, 1.36), I['Black'], '-Y', M)
    for zc in (0.25, 1.05, 1.85):
        cyl(B, (0.0, -t / 2 - 0.004, zc - 0.065), 0.13, 0.011, st, 12, 'Z', M)
        lathe(B, [(0.011, 0), (0.008, 0.008), (0, 0.01)], 12, (0.0, -t / 2 - 0.004, zc + 0.065), st, 'Z', M)

# ---------------------------------------------------------------- stairs, railing, fences, pillar
def build_stairs(B, M=None):
    n, rise, go, w = 16, H / 16, 0.27, 1.0
    L = n * go; y0 = -L / 2; cap = 0.03
    pts = [(y0, 0.0)]
    for k in range(n):
        pts += [(y0 + k * go, (k + 1) * rise - cap), (y0 + (k + 1) * go, (k + 1) * rise - cap)]
    pts += [(L / 2, 0.0)]
    pts2 = [pts[0]] + [p for i, p in enumerate(pts[1:-1])] + [pts[-1]]
    prism(B, pts2, -w / 2, w / 2, I['Concrete'], 'YZ', M)
    for k in range(n):
        za = (k + 1) * rise
        box(B, (-w / 2 - 0.01, y0 + k * go - 0.025, za - cap), (w / 2 + 0.01, y0 + (k + 1) * go, za), I['Wood'], 0.006, 1, M)
        box(B, (-w / 2 + 0.03, y0 + k * go - 0.027, za - 0.004), (w / 2 - 0.03, y0 + k * go + 0.025, za + 0.002), I['Black'], 0.0, 1, M)
    for s in (-1, 1):                                                            # side stringers: a band under the nosing line
        xs = (s * w / 2, s * (w / 2 + 0.02))
        slope = H / (L - go); dz = 0.20
        prism(B, [(y0 - 0.02, 0.0), (y0 - 0.02, rise + 0.02), (L / 2 - go, H - rise + 0.02), (L / 2, H - 0.035),
                  (L / 2, H - 0.035 - dz * 1.4), (y0 + dz * 1.4 / slope + 0.1, 0.0)], min(xs), max(xs), I['Skirting'], 'YZ', M)

def build_railing(B, M=None):
    st, hgt = I['Steel'], 1.0
    for x in (-0.975, 0.0, 0.975):
        cyl(B, (x, 0, 0.012), hgt - 0.012 - 0.024, 0.024, st, 20, 'Z', M)
        box(B, (x - 0.06, -0.06, 0), (x + 0.06, 0.06, 0.012), st, 0.003, 1, M)
        for xb, yb in ((-0.04, -0.04), (0.04, -0.04), (-0.04, 0.04), (0.04, 0.04)):
            lathe(B, [(0.008, 0), (0.008, 0.008), (0, 0.011)], 6, (x + xb, yb, 0.012), I['Black'], 'Z', M)
    lathe(B, [(0.0, -1.0), (0.028, -1.0), (0.028, 1.0), (0.0, 1.0)], 24, (0, 0, hgt - 0.028), st, 'X', M)   # top rail
    cyl(B, (-1.0, 0, 0.11), 2.0, 0.014, st, 12, 'X', M)                                                     # bottom rail
    for a, b in ((-0.975, 0.0), (0.0, 0.975)):
        for k in range(1, 8):
            x = a + (b - a) * k / 8
            cyl(B, (x, 0, 0.11), hgt - 0.028 - 0.11, 0.008, st, 8, 'Z', M)

def build_fencechainlink(B, M=None):
    st, W, Hf = I['Steel'], 2.5, 1.8
    px = W / 2 - 0.03
    for x in (-px, px):
        lathe(B, [(0.03, 0), (0.03, Hf), (0.036, Hf), (0.036, Hf + 0.03), (0.025, Hf + 0.05), (0.0, Hf + 0.058)], 16, (x, 0, 0), st, 'Z', M)
        for zc in (0.25, 0.95, 1.55):                                            # tension bands
            box(B, (x - 0.04, -0.034, zc - 0.012), (x + 0.04, 0.034, zc + 0.012), st, 0.0, 1, M)
    lathe(B, [(0.0, -px), (0.021, -px), (0.021, px), (0.0, px)], 16, (0, -0.045, Hf - 0.06), st, 'X', M)    # top rail
    cyl(B, (-px, -0.045, 0.06), 2 * px, 0.004, st, 6, 'X', M)                                               # bottom wire
    for x in (-px, px):
        box(B, (x - 0.03, -0.065, Hf - 0.085), (x + 0.03, -0.025, Hf - 0.035), st, 0.01, 1, M)               # rail clamps
    x0, x1, z0, z1, sp = -px + 0.04, px - 0.04, 0.06, Hf - 0.06, 0.16
    yc = -0.045
    for sgn in (1, -1):                                                          # diamond mesh: two families of diagonals
        c = (x0 - z1) if sgn == 1 else (x0 + z0)
        cend = (x1 - z0) if sgn == 1 else (x1 + z1)
        c += sp / 2
        while c < cend:
            if sgn == 1: za, zb = max(z0, x0 - c), min(z1, x1 - c); pa, pb = (za + c, za), (zb + c, zb)
            else: za, zb = max(z0, c - x1), min(z1, c - x0); pa, pb = (c - za, za), (c - zb, zb)
            if zb - za > 0.02: strip(B, pa, pb, 0.007, yc + sgn * 0.002, 0.005, st, M)
            c += sp
    for x in (x0, x1):                                                           # tension bars
        box(B, (x - 0.006, yc - 0.006, z0), (x + 0.006, yc + 0.006, z1), st, 0.0, 1, M)

def build_fencewood(B, M=None):
    W, Hf = 2.0, 1.5
    wd, wdd = I['Wood'], I['WoodDark']
    pxc = W / 2 - 0.045
    for x in (-pxc, pxc):
        box(B, (x - 0.045, -0.02, 0), (x + 0.045, 0.07, Hf + 0.02), wdd, 0.006, 2, M)
        box(B, (x - 0.055, -0.03, Hf + 0.02), (x + 0.055, 0.08, Hf + 0.045), wdd, 0.008, 2, M)    # post cap
    for zc in (0.32, 1.15):
        box(B, (-pxc, 0.0, zc - 0.045), (pxc, 0.035, zc + 0.045), wdd, 0.005, 2, M)
    span = 2 * (pxc - 0.045); npk = 13; pw = 0.088
    gap = (span - npk * pw) / (npk + 1)
    for k in range(npk):
        xa = -pxc + 0.045 + gap + k * (pw + gap); xb = xa + pw
        top = Hf - 0.0 - (0.02 if k % 2 else 0.0)
        prism(B, [(xa, 0.05), (xb, 0.05), (xb, top - 0.055), ((xa + xb) / 2, top), (xa, top - 0.055)],
              -0.02, 0.0, wd, 'XZ', M)
        for zc in (0.32, 1.15):                                                  # nail heads
            for xn in (xa + 0.025, xb - 0.025):
                box(B, (xn - 0.006, -0.023, zc - 0.006), (xn + 0.006, -0.0195, zc + 0.006), I['Black'], 0.0, 1, M)

def build_pillar(B, M=None):
    wp, tr, sk = I['WallPaint'], I['Trim'], I['Skirting']
    box(B, (-0.2, -0.2, 0), (0.2, 0.2, 0.12), sk, 0.008, 2, M)
    box(B, (-0.18, -0.18, 0.12), (0.18, 0.18, 0.18), tr, 0.012, 2, M)
    box(B, (-0.16, -0.16, 0.17), (0.16, 0.16, 2.53), wp, 0.012, 2, M)
    box(B, (-0.18, -0.18, 2.52), (0.18, 0.18, 2.58), tr, 0.012, 2, M)
    box(B, (-0.2, -0.2, 2.58), (0.2, 0.2, 2.70), tr, 0.008, 2, M)
    for s in (-1, 1):                                                            # shallow vertical flutes
        for k in (-1, 0, 1):
            box(B, (k * 0.075 - 0.012, s * 0.16 - 0.004, 0.32), (k * 0.075 + 0.012, s * 0.16 + 0.004, 2.38), I['WallPaint'], 0.0, 1, M)
            box(B, (s * 0.16 - 0.004, k * 0.075 - 0.012, 0.32), (s * 0.16 + 0.004, k * 0.075 + 0.012, 2.38), I['WallPaint'], 0.0, 1, M)

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
        bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
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
    B = Builder(); BUILD[name](B)
    mesh = to_object(B, PASCAL[name])
    tris, mats, lo, hi = stats(mesh)
    root = bpy.data.objects.new(PASCAL[name], None); scene.collection.objects.link(root); mesh.parent = root
    for o in scene.objects: o.select_set(False)
    root.select_set(True); mesh.select_set(True)
    bpy.ops.export_scene.fbx(filepath=f'{out}/{PASCAL[name]}.fbx', use_selection=True, apply_unit_scale=True,
                             apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)
    cam = setup_render(scene)
    frame_shot(scene, cam, f'{out}/render-34.png', lo, hi)
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', f'{out}/render-34.png', '-q:v', '3', f'{out}/compare.jpg'])
    line = (f'[setpiece] {name}: tris {tris}, mats {len(mats)} {mats}, size {hi.x - lo.x:.3f} x {hi.y - lo.y:.3f} x '
            f'{hi.z - lo.z:.3f} m, bbox lo {tuple(round(v, 3) for v in lo)} hi {tuple(round(v, 3) for v in hi)}')
    print(line); report.append(line)

if 'kit' in NAMES:
    # small room corner: back wall along X at y = 3 (front faces into the room), side wall along Y at x = 0
    scene = reset(); out = os.path.join(LIB, 'wall3m'); os.makedirs(out, exist_ok=True)
    R90 = Matrix.Rotation(math.pi / 2, 4, 'Z'); RM90 = Matrix.Rotation(-math.pi / 2, 4, 'Z')
    T_ = Matrix.Translation
    layout = [('wallwindow', T_((1.5, 3.0, 0))), ('wall3m', T_((4.5, 3.0, 0))), ('wall1m', T_((6.5, 3.0, 0))),
              ('walldoorway', T_((0.0, 1.5, 0)) @ R90), ('wall3m', T_((0.0, -1.5, 0)) @ R90),
              ('doorinterior', T_((0.05, 1.5 - OW / 2 + 0.002, 0)) @ Matrix.Rotation(math.radians(35), 4, 'Z')),
              ('pillar', T_((0.0, 3.0, 0))), ('stairs', T_((7.0 - 2.16, 3.0 - T / 2 - 0.52, 0)) @ R90),
              ('railing', T_((2.6, -0.4, 0)) @ R90)]
    lo = Vector((1e9,) * 3); hi = Vector((-1e9,) * 3)
    for i, (n, Mx) in enumerate(layout):
        B = Builder(); BUILD[n](B); o = to_object(B, f'{PASCAL[n]}{i}'); o.matrix_world = Mx
        _, _, a, b = stats(o)
        lo = Vector([min(lo[k], a[k]) for k in range(3)]); hi = Vector([max(hi[k], b[k]) for k in range(3)])
    fl = cube((-0.5, -3.5, -0.02), (7.5, 3.0, 0.0)); fb = Builder(); fb.add(fl, I['Concrete'])
    to_object(fb, 'Floor')
    cam = setup_render(scene)
    shoot(scene, cam, f'{out}/kit.png', (7.6, -6.2, 3.6), (2.8, 1.4, 1.15), 32)
    print('[setpiece] kit rendered')

print('\n'.join(report))

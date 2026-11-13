# Corrugated steel industrial warehouse (own design, CC0), previs base library (Opus).
# Usage: /Applications/Blender.app/Contents/MacOS/Blender -b --python make_warehouse.py -- <out dir>
# 1 unit = 1 m, front toward -Y, up +Z, origin on the ground at the centre of the footprint.
# Follows ref-34.png: gable end to the front (12 m wide), 20 m deep in three bays, eaves 6.0 m, ridge 7.5 m.
# Front gable: big sliding door standing a third open onto a dark interior, personnel door, high strip window,
# top track with hangers. Sides: pilasters between bays, strip windows per bay. Three louvred cupola vents.
# Corrugation is real geometry: a trapezoid-profile sheet generator that leaves holes for openings.
import bpy, bmesh, sys, math, os
from mathutils import Vector, Matrix

OUT = os.path.abspath(sys.argv[sys.argv.index('--') + 1])
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

CLAD = mat('Cladding', (0.140, 0.205, 0.285), 0.75)        # muted steel blue wall sheet
CLAD_D = mat('CladdingWorn', (0.098, 0.135, 0.180), 0.85)
TRIM = mat('Trim', (0.400, 0.385, 0.355), 0.75)            # warm light grey flashings, frames, pilasters
ROOF = mat('Roof', (0.300, 0.300, 0.290), 0.7, 0.1)
STEEL = mat('Steel', (0.085, 0.090, 0.100), 0.6, 0.3)
CONC = mat('Concrete', (0.215, 0.188, 0.162))
GLASS = mat('Glass', (0.050, 0.060, 0.070), 0.15)
BLACK = mat('Black', (0.012, 0.012, 0.012), 1.0)

parts = []
def new_obj(name, me):
    o = bpy.data.objects.new(name, me); scene.collection.objects.link(o)
    for m in ORDER: o.data.materials.append(m)
    parts.append(o); return o

def set_all(o, idx):
    for p in o.data.polygons: p.material_index = idx

def box(name, lo, hi, idx, bevel=0.0, segs=2):
    lo, hi = [min(a, b) for a, b in zip(lo, hi)], [max(a, b) for a, b in zip(lo, hi)]
    c = [(lo[i] + hi[i]) / 2 for i in range(3)]; s = [hi[i] - lo[i] for i in range(3)]
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((*s, 1)))
    if bevel:
        bmesh.ops.bevel(bm, geom=bm.edges[:] + bm.verts[:], offset=bevel, segments=segs, affect='EDGES', profile=0.5)
    bm.to_mesh(me); bm.free()
    o = new_obj(name, me); set_all(o, idx); return o

def poly_prism(name, pts, y0, y1, idx, bevel=0.0):
    """Extrude an (x, z) polygon along y."""
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    a = [bm.verts.new((x, y0, z)) for x, z in pts]; b = [bm.verts.new((x, y1, z)) for x, z in pts]
    bm.faces.new(a); bm.faces.new(b[::-1])
    n = len(pts)
    for i in range(n): bm.faces.new([a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if bevel: bmesh.ops.bevel(bm, geom=bm.edges[:], offset=bevel, segments=1, affect='EDGES')
    bm.to_mesh(me); bm.free()
    o = new_obj(name, me); set_all(o, idx); return o

# ---------------------------------------------------------------- corrugated sheet generator
PERIOD, DEPTH = 0.36, 0.035
PROF = [(0.0, 0.0), (0.30, 0.0), (0.40, 1.0), (0.80, 1.0), (0.90, 0.0)]   # trapezoid rib, fraction of period
def depth_at(u, u0):
    t = ((u - u0) % PERIOD) / PERIOD
    pts = PROF + [(1.0, 0.0)]
    for (a, da), (b, db) in zip(pts, pts[1:]):
        if a <= t <= b: return DEPTH * (da + (db - da) * (t - a) / (b - a))
    return 0.0

def sheet(name, frame, u0, u1, z0, ztop, holes=(), idx=CLAD, worn=None, extra_u=()):
    """Corrugated sheet in a local (u, depth, z) frame mapped by frame(u, d, z) -> world Vector.
    ztop(u) gives the top edge; holes are (ua, ub, za, zb) rectangles left open; worn(u, z) -> bool picks CLAD_D.
    Rows are split only in the columns that cross a hole, so a big wall stays one quad tall elsewhere."""
    us = set(); u = u0
    while u < u1 - 1e-6:
        for f, _ in PROF: us.add(round(u + f * PERIOD, 5))
        u += PERIOD
    us |= {u0, u1, *extra_u}
    for (ua, ub, za, zb) in holes: us |= {ua, ub}
    us = sorted(x for x in us if u0 - 1e-6 <= x <= u1 + 1e-6)
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    def P(u, z): return frame(u, depth_at(u, u0), z)
    for i in range(len(us) - 1):
        ua, ub = us[i], us[i + 1]; um = (ua + ub) / 2
        hs = [h for h in holes if h[0] - 1e-6 <= um <= h[1] + 1e-6]
        zs = sorted({z0, *[h[2] for h in hs], *[h[3] for h in hs]})
        ta, tb = ztop(ua), ztop(ub)
        zs = [z for z in zs if z < min(ta, tb) - 1e-4]
        for j, za in enumerate(zs):
            last = j == len(zs) - 1
            zm = (za + (zs[j + 1] if not last else min(ta, tb))) / 2
            if any(h[2] - 1e-6 <= zm <= h[3] + 1e-6 for h in hs): continue
            za_ = za; zb_a = ta if last else zs[j + 1]; zb_b = tb if last else zs[j + 1]
            f = bm.faces.new([bm.verts.new(P(ua, za_)), bm.verts.new(P(ub, za_)), bm.verts.new(P(ub, zb_b)), bm.verts.new(P(ua, zb_a))])
            f.material_index = CLAD_D if (worn and worn(um, zm)) else idx
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bm.to_mesh(me); bm.free()
    return new_obj(name, me)

# ---------------------------------------------------------------- dimensions
LX, LY = 12.0, 20.0
HX, HY = LX / 2, LY / 2
SLAB = 0.15
EAVE, RIDGE = 6.00, 7.50
SLOPE = (RIDGE - EAVE) / HX
def roof_z(x): return EAVE + (HX - abs(x)) * SLOPE
PLINTH = 0.55                      # trim-coloured base band
BASE = PLINTH                      # cladding starts above it
FY = -HY
# big sliding door
SD_X0, SD_X1 = -1.2, 3.8           # 5.0 m opening
SD_TOP = 4.55
OPEN_FRAC = 1 / 3                  # leaf slid left, a third of the opening open
# personnel door
PD_X0, PD_X1, PD_TOP = -5.15, -4.15, 2.35
# strip windows
GW_X0, GW_X1, GW_Z0, GW_Z1 = -4.6, 4.6, 5.20, 5.85          # front gable
SW_Z0, SW_Z1 = 4.55, 5.20                                       # side bays
BAYS = [-HY, -HY / 3, HY / 3, HY]
PIL = 0.32                                                      # pilaster width

def worn_wall(u, z):   # dirt band just above the plinth, a few streaks
    h = math.sin(u * 1.7) * 0.5 + math.sin(u * 4.3 + 1.0) * 0.3
    return z < BASE + 0.35 + 0.18 * h

# ---------------------------------------------------------------- slab, plinth, interior
box('Slab', (-HX - 0.35, -HY - 0.35, 0), (HX + 0.35, HY + 0.35, SLAB), CONC, 0.03, 2)
box('Apron', (SD_X0 - 0.8, -HY - 2.6, 0), (SD_X1 + 0.8, -HY - 0.3, SLAB - 0.03), CONC, 0.03, 2)
box('PDStep', (PD_X0 - 0.35, FY - 0.9, 0), (PD_X1 + 0.35, FY - 0.3, SLAB + 0.12), CONC, 0.02, 2)
PT = 0.10
def plinth_run(lo, hi): box('Plinth', lo, hi, TRIM, 0.015, 2)
plinth_run((-HX - PT, -HY - PT, SLAB), (SD_X0 - 0.15, -HY + 0.2, PLINTH))     # front, left of the door
plinth_run((SD_X1 + 0.15, -HY - PT, SLAB), (HX + PT, -HY + 0.2, PLINTH))      # front, right of the door
plinth_run((-HX - PT, HY - 0.2, SLAB), (HX + PT, HY + PT, PLINTH))
plinth_run((-HX - PT, -HY - PT, SLAB), (-HX + 0.2, HY + PT, PLINTH))
plinth_run((HX - 0.2, -HY - PT, SLAB), (HX + PT, HY + PT, PLINTH))

I = 0.25
def inner_quad(name, pts):
    me = bpy.data.meshes.new(name); bm = bmesh.new(); bm.faces.new([bm.verts.new(p) for p in pts]); bm.to_mesh(me); bm.free()
    o = new_obj(name, me); set_all(o, BLACK); return o
ix0, ix1, iy0, iy1, iz0, iz1 = -HX + I, HX - I, -HY + I, HY - I, SLAB + 0.002, EAVE - 0.15
inner_quad('InFloor', [(ix0, iy0, iz0), (ix1, iy0, iz0), (ix1, iy1, iz0), (ix0, iy1, iz0)])
inner_quad('InBack', [(ix0, iy1, iz0), (ix1, iy1, iz0), (ix1, iy1, iz1), (ix0, iy1, iz1)])
inner_quad('InL', [(ix0, iy0, iz0), (ix0, iy1, iz0), (ix0, iy1, iz1), (ix0, iy0, iz1)])
inner_quad('InR', [(ix1, iy1, iz0), (ix1, iy0, iz0), (ix1, iy0, iz1), (ix1, iy1, iz1)])
inner_quad('InTop', [(ix0, iy0, iz1), (ix0, iy1, iz1), (ix1, iy1, iz1), (ix1, iy0, iz1)])
# a portal-frame column and a rack inside so the open door shows some depth
box('Col', (2.0, -HY / 3 - 0.15, SLAB), (2.3, -HY / 3 + 0.15, iz1), STEEL)
box('Rack', (0.5, -2.0, SLAB), (3.4, -1.1, 3.0), BLACK)

# ---------------------------------------------------------------- cladding
front = sheet('Front', lambda u, d, z: Vector((u, FY - d, z)), -HX, HX, BASE, roof_z,
              holes=[(SD_X0, SD_X1, BASE - 1, SD_TOP), (PD_X0, PD_X1, BASE - 1, PD_TOP), (GW_X0, GW_X1, GW_Z0, GW_Z1)],
              worn=worn_wall, extra_u=(0.0,))
back = sheet('Back', lambda u, d, z: Vector((-u, HY + d, z)), -HX, HX, BASE, roof_z,
             holes=[(-3.0, 3.0, GW_Z0, GW_Z1)], worn=worn_wall, extra_u=(0.0,))
side_holes = [(a + 0.8, b - 0.8, SW_Z0, SW_Z1) for a, b in zip(BAYS, BAYS[1:])]
left = sheet('Left', lambda u, d, z: Vector((-HX - d, -u, z)), -HY, HY, BASE, lambda u: EAVE,
             holes=[(-b, -a, za, zb) for a, b, za, zb in side_holes], worn=worn_wall)
right = sheet('Right', lambda u, d, z: Vector((HX + d, u, z)), -HY, HY, BASE, lambda u: EAVE,
              holes=side_holes, worn=worn_wall)
# the big-door opening: cladding stops at the slab there, so carry the plinth band only either side

# pilasters at the corners and between bays, eave fascia on the sides
for sx in (-1, 1):
    for y in BAYS:
        y0, y1 = max(y - PIL / 2, -HY - 0.12), min(y + PIL / 2, HY + 0.12)
        if y <= -HY: y1 = y0 + PIL
        if y >= HY: y0 = y1 - PIL
        box('Pilaster', (sx * HX - 0.02 * sx, y0, SLAB), (sx * (HX + 0.14), y1, EAVE + 0.05), TRIM, 0.015, 2)
for sy in (-1, 1):
    for sx in (-1, 1):
        box('CornerF', (sx * (HX - PIL + 0.10), sy * HY - 0.02 * sy, SLAB), (sx * (HX + 0.14), sy * (HY + 0.12), EAVE + 0.05 if True else 0), TRIM, 0.015, 2)

# ---------------------------------------------------------------- roof (ribs run down the slope, profile along y)
OH = 0.30
def roof_plane(name, sx):
    x_e, z_e = sx * (HX + OH), EAVE - OH * SLOPE + 0.06
    L = math.hypot(HX + OH, RIDGE + 0.06 - z_e)
    n = Vector((sx * (RIDGE + 0.06 - z_e), 0, HX + OH)).normalized()
    def fr(u, d, s):
        t = s / L
        return Vector((x_e * (1 - t), u, z_e + (RIDGE + 0.06 - z_e) * t)) + n * d
    return sheet(name, fr, -HY - OH, HY + OH, 0.0, lambda u: L, idx=ROOF)
roof_plane('RoofL', -1); roof_plane('RoofR', 1)
# underside of the roof, so a low view does not see through the sheet
for sx in (-1, 1):
    me = bpy.data.meshes.new('Soffit'); bm = bmesh.new()
    z_e = EAVE - OH * SLOPE + 0.03
    vs = [bm.verts.new(p) for p in ((sx * (HX + OH), -HY - OH, z_e), (0, -HY - OH, RIDGE + 0.03), (0, HY + OH, RIDGE + 0.03), (sx * (HX + OH), HY + OH, z_e))]
    bm.faces.new(vs if sx > 0 else vs[::-1]); bm.to_mesh(me); bm.free(); o = new_obj('Soffit', me); set_all(o, ROOF)
# fascia (eaves), barge boards (gable verges), ridge cap
FH = 0.26
for sx in (-1, 1):
    z_e = EAVE - OH * SLOPE
    box('Fascia', (sx * (HX + OH), -HY - OH - 0.06, z_e - FH + 0.10), (sx * (HX + OH + 0.08), HY + OH + 0.06, z_e + 0.16), TRIM, 0.015, 2)
for sy in (-1, 1):
    y0, y1 = sy * (HY + OH), sy * (HY + OH + 0.08)
    for sx in (-1, 1):
        x_e, z_e = sx * (HX + OH + 0.08), EAVE - (OH + 0.08) * SLOPE
        pts = [(x_e, z_e - FH + 0.14), (0, RIDGE - FH + 0.14), (0, RIDGE + 0.16), (x_e, z_e + 0.16)]
        poly_prism('Barge', pts if sx > 0 else pts[::-1], min(y0, y1), max(y0, y1), TRIM, 0.012)
    # gable-wall rake flashing where the cladding meets the roof
    for sx in (-1, 1):
        pts = [(sx * (HX + 0.10), EAVE - 0.18), (0, RIDGE - 0.18), (0, RIDGE + 0.02), (sx * (HX + 0.10), EAVE + 0.02)]
        poly_prism('Rake', pts if sx > 0 else pts[::-1], sy * HY - 0.02 * sy if sy > 0 else sy * (HY + 0.12), sy * (HY + 0.12) if sy > 0 else sy * HY - 0.02 * sy, TRIM, 0.01)
for sx in (-1, 1):
    pts = [(0, RIDGE + 0.06), (sx * 0.32, RIDGE + 0.06 - 0.32 * SLOPE), (sx * 0.32, RIDGE + 0.12 - 0.32 * SLOPE), (0, RIDGE + 0.14)]
    poly_prism('Ridge', pts if sx > 0 else pts[::-1], -HY - OH - 0.06, HY + OH + 0.06, TRIM, 0.01)

# ---------------------------------------------------------------- cupola vents on the ridge (square, louvred, hip cap)
for yv in (-6.2, 0.0, 6.2):
    zb = RIDGE + 0.05; W = 0.62; Hc = 0.62
    # base saddle that sits on both roof slopes
    pts = [(-0.78, RIDGE + 0.06 - 0.78 * SLOPE), (0.78, RIDGE + 0.06 - 0.78 * SLOPE), (0.78, zb + 0.18), (-0.78, zb + 0.18)]
    poly_prism('CupBase', pts, yv - 0.78, yv + 0.78, TRIM, 0.015)
    box('CupBody', (-W, yv - W, zb + 0.18), (W, yv + W, zb + 0.18 + Hc), ROOF, 0.02, 2)
    for side in range(4):     # louvre slats on each face, dark gaps behind
        rot = Matrix.Rotation(side * math.pi / 2, 4, 'Z')
        for k in range(5):
            z = zb + 0.28 + k * 0.095
            s = box('CupSlat', (-W + 0.08, -0.025, -0.022), (W - 0.08, 0.025, 0.022), ROOF)
            s.data.transform(Matrix.Translation((0, yv, 0)) @ rot @ Matrix.Translation((0, -W - 0.02, z)) @ Matrix.Rotation(math.radians(-40), 4, 'X'))
        g = box('CupGap', (-W + 0.08, -0.005, zb + 0.25), (W - 0.08, 0.005, zb + 0.18 + Hc - 0.07), BLACK)
        g.data.transform(Matrix.Translation((0, yv, 0)) @ rot @ Matrix.Translation((0, -W - 0.0, 0)))
    for cx in (-1, 1):
        for cy in (-1, 1):
            box('CupPost', (cx * W - 0.06 * (cx > 0) - 0.02 * (cx < 0), yv + cy * W - 0.06 * (cy > 0) - 0.02 * (cy < 0), zb + 0.18),
                (cx * W + 0.02 * (cx > 0) + 0.06 * (cx < 0), yv + cy * W + 0.02 * (cy > 0) + 0.06 * (cy < 0), zb + 0.18 + Hc), TRIM, 0.01, 1)
    # hip cap: a low pyramid with an eave lip
    ct = zb + 0.18 + Hc
    box('CupLip', (-W - 0.14, yv - W - 0.14, ct), (W + 0.14, yv + W + 0.14, ct + 0.07), TRIM, 0.015, 2)
    me = bpy.data.meshes.new('CupCap'); bm = bmesh.new()
    E = W + 0.12
    vs = [bm.verts.new((x, yv + y, ct + 0.07)) for x, y in ((-E, -E), (E, -E), (E, E), (-E, E))]
    tv = [bm.verts.new((x, yv + y, ct + 0.36)) for x, y in ((-0.12, -0.12), (0.12, -0.12), (0.12, 0.12), (-0.12, 0.12))]
    for i in range(4): bm.faces.new([vs[i], vs[(i + 1) % 4], tv[(i + 1) % 4], tv[i]])
    bm.faces.new(tv); bm.faces.new(vs[::-1]); bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free(); o = new_obj('CupCap', me); set_all(o, ROOF)

# ---------------------------------------------------------------- big sliding door, track, frame
DW = SD_X1 - SD_X0
fy = FY - DEPTH
box('SDJambL', (SD_X0 - 0.16, fy - 0.08, SLAB), (SD_X0 + 0.02, FY + 0.15, SD_TOP + 0.02), TRIM, 0.012, 2)
box('SDJambR', (SD_X1 - 0.02, fy - 0.08, SLAB), (SD_X1 + 0.16, FY + 0.15, SD_TOP + 0.02), TRIM, 0.012, 2)
box('SDHead', (SD_X0 - 0.16, fy - 0.08, SD_TOP - 0.02), (SD_X1 + 0.16, FY + 0.15, SD_TOP + 0.16), TRIM, 0.012, 2)
box('SDSill', (SD_X0, fy - 0.02, SLAB - 0.01), (SD_X1, FY + 0.15, SLAB + 0.025), STEEL, 0.006, 1)
# top track beam: runs over the opening and on to the left where the leaf parks
LW = DW + 0.24
lx0 = SD_X0 - 0.12 - DW * (1 - OPEN_FRAC) * 0 - DW * OPEN_FRAC * 0   # placeholder, set below
lx0 = SD_X1 + 0.12 - LW - DW * OPEN_FRAC                             # leaf left edge
TX0, TX1 = lx0 - 0.35, SD_X1 + 0.45
ty0, ty1 = fy - 0.36, fy - 0.10
TZ = SD_TOP + 0.30
box('Track', (TX0, ty0, TZ), (TX1, ty1, TZ + 0.22), TRIM, 0.02, 2)
for x in [TX0 + 0.25 + k * (TX1 - TX0 - 0.5) / 3 for k in range(4)]:
    box('TrackBr', (x - 0.07, ty1 - 0.02, TZ - 0.04), (x + 0.07, FY, TZ + 0.26), TRIM, 0.01, 1)
    box('TrackBolt', (x - 0.03, ty0 - 0.02, TZ + 0.08), (x + 0.03, ty0, TZ + 0.14), STEEL)
# the leaf: corrugated light-grey skin in a frame, hung from two trolleys
ly = (ty0 + ty1) / 2 + 0.02
lz0, lz1 = SLAB + 0.02, SD_TOP + 0.12
box('LeafCore', (lx0 + 0.05, ly - 0.03, lz0 + 0.05), (lx0 + LW - 0.05, ly + 0.04, lz1 - 0.05), TRIM)
LEAF_SKIN_FRAME = lambda u, d, z: Vector((u, ly - 0.03 - d, z))
_c = CLAD
sheet('LeafSkin', LEAF_SKIN_FRAME, lx0 + 0.07, lx0 + LW - 0.07, lz0 + 0.10, lambda u: lz1 - 0.10, idx=TRIM)
for (a, b) in ((lx0, lx0 + 0.09), (lx0 + LW - 0.09, lx0 + LW)):
    box('LeafStile', (a, ly - 0.08, lz0), (b, ly + 0.05, lz1), TRIM, 0.012, 2)
for (c, d) in ((lz0, lz0 + 0.12), (lz1 - 0.12, lz1)):
    box('LeafRail', (lx0, ly - 0.08, c), (lx0 + LW, ly + 0.05, d), TRIM, 0.012, 2)
for x in (lx0 + 0.45, lx0 + LW - 0.45):
    box('Hanger', (x - 0.07, ly - 0.06, lz1 - 0.06), (x + 0.07, ly - 0.03, TZ + 0.14), STEEL, 0.008, 1)
    box('Trolley', (x - 0.16, ty0 - 0.04, TZ + 0.04), (x + 0.16, ty0 + 0.02, TZ + 0.20), STEEL, 0.01, 1)
# recessed pull handles at both stiles (dark pocket in a frame)
for hx in (lx0 + 0.30, lx0 + LW - 0.30):
    box('PullFrame', (hx - 0.07, ly - 0.10, 1.25), (hx + 0.07, ly - 0.075, 1.65), STEEL, 0.008, 1)
    box('PullPocket', (hx - 0.04, ly - 0.105, 1.29), (hx + 0.04, ly - 0.10, 1.61), BLACK)
box('FloorGuide', (SD_X0 - 0.40, ly - 0.10, SLAB), (SD_X0 - 0.22, ly + 0.10, SLAB + 0.10), STEEL, 0.01, 1)
box('Stop', (TX0, ty0, TZ - 0.02), (TX0 + 0.10, ty1, TZ + 0.24), STEEL, 0.01, 1)

# ---------------------------------------------------------------- personnel door
box('PDJambL', (PD_X0 - 0.10, fy - 0.05, SLAB), (PD_X0 + 0.01, FY + 0.12, PD_TOP + 0.10), TRIM, 0.01, 1)
box('PDJambR', (PD_X1 - 0.01, fy - 0.05, SLAB), (PD_X1 + 0.10, FY + 0.12, PD_TOP + 0.10), TRIM, 0.01, 1)
box('PDHead', (PD_X0 - 0.10, fy - 0.05, PD_TOP - 0.01), (PD_X1 + 0.10, FY + 0.12, PD_TOP + 0.10), TRIM, 0.01, 1)
PDZ0 = SLAB + 0.12
box('PDoor', (PD_X0 + 0.01, FY + 0.00, PDZ0), (PD_X1 - 0.01, FY + 0.06, PD_TOP), TRIM, 0.01, 2)
for z in (PDZ0 + 0.25, PD_TOP - 0.30):
    box('PDHinge', (PD_X0 + 0.005, FY - 0.03, z), (PD_X0 + 0.04, FY + 0.01, z + 0.10), STEEL, 0.004, 1)
box('PDRose', (PD_X1 - 0.13, FY - 0.02, PDZ0 + 0.95), (PD_X1 - 0.08, FY, PDZ0 + 1.06), STEEL, 0.004, 1)
box('PDLever', (PD_X1 - 0.24, FY - 0.06, PDZ0 + 0.99), (PD_X1 - 0.09, FY - 0.035, PDZ0 + 1.02), STEEL, 0.006, 1)
box('PDLeverNeck', (PD_X1 - 0.12, FY - 0.05, PDZ0 + 0.985), (PD_X1 - 0.09, FY - 0.01, PDZ0 + 1.025), STEEL)

# ---------------------------------------------------------------- strip windows (glass in frames, mullions)
def strip(x0, x1, z0, z1, frame_fn, n):
    """frame_fn(lo, hi) builds a box in local (u, out, z) -> world; out < 0 is outward."""
    frame_fn('WinTop', (x0 - 0.10, -0.08, z1), (x1 + 0.10, 0.02, z1 + 0.09))
    frame_fn('WinBot', (x0 - 0.10, -0.08, z0 - 0.09), (x1 + 0.10, 0.02, z0))
    frame_fn('WinSill', (x0 - 0.14, -0.15, z0 - 0.13), (x1 + 0.14, -0.06, z0 - 0.06))
    for x in (x0 - 0.10, x1):
        frame_fn('WinSide', (x, -0.08, z0), (x + 0.10, 0.02, z1))
    frame_fn('Glass', (x0, -0.02, z0), (x1, -0.005, z1), GLASS)
    for k in range(1, n):
        x = x0 + (x1 - x0) * k / n
        frame_fn('Mullion', (x - 0.035, -0.07, z0), (x + 0.035, 0.0, z1))
def front_fn(name, lo, hi, idx=TRIM):
    box(name, (lo[0], FY - DEPTH + lo[1], lo[2]), (hi[0], FY - DEPTH + hi[1], hi[2]), idx, 0.008 if idx == TRIM else 0, 1)
def back_fn(name, lo, hi, idx=TRIM):
    box(name, (-hi[0], HY + DEPTH - lo[1], lo[2]), (-lo[0], HY + DEPTH - hi[1], hi[2]), idx, 0.008 if idx == TRIM else 0, 1)
def side_fn(sx):
    def f(name, lo, hi, idx=TRIM):
        if sx > 0: box(name, (HX + DEPTH - lo[1], lo[0], lo[2]), (HX + DEPTH - hi[1], hi[0], hi[2]), idx, 0.008 if idx == TRIM else 0, 1)
        else: box(name, (-HX - DEPTH + lo[1], -hi[0], lo[2]), (-HX - DEPTH + hi[1], -lo[0], hi[2]), idx, 0.008 if idx == TRIM else 0, 1)
    return f
strip(GW_X0, GW_X1, GW_Z0, GW_Z1, front_fn, 9)
strip(-3.0, 3.0, GW_Z0, GW_Z1, back_fn, 6)
for sx in (-1, 1):
    for a, b, za, zb in side_holes:
        strip(a, b, za, zb, side_fn(sx), 6)

# ---------------------------------------------------------------- join (all parts carry the same slot list)
for o in scene.objects: o.select_set(False)
for o in parts: o.select_set(True)
base = parts[0]
bpy.context.view_layer.objects.active = base
bpy.ops.object.join()
mesh = base; mesh.name = 'Warehouse_Mesh'
assert [m.name for m in mesh.data.materials] == [m.name for m in ORDER], 'material slots shuffled'
bm = bmesh.new(); bm.from_mesh(mesh.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0003)
bm.to_mesh(mesh.data); bm.free()
with bpy.context.temp_override(active_object=mesh, object=mesh, selected_objects=[mesh], selected_editable_objects=[mesh]):
    bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
tris = sum(len(p.vertices) - 2 for p in mesh.data.polygons)
used = sorted({p.material_index for p in mesh.data.polygons})
co = [v.co for v in mesh.data.vertices]
lo = [min(c[i] for c in co) for i in range(3)]; hi = [max(c[i] for c in co) for i in range(3)]
print(f'[warehouse] triangles {tris}, materials {len(used)} {[ORDER[i].name for i in used]}, '
      f'size {hi[0]-lo[0]:.2f} x {hi[1]-lo[1]:.2f} x {hi[2]-lo[2]:.2f}, bounds {[round(v, 2) for v in lo]} {[round(v, 2) for v in hi]}')

root = bpy.data.objects.new('Warehouse', None); scene.collection.objects.link(root); mesh.parent = root
for o in scene.objects: o.select_set(False)
root.select_set(True); mesh.select_set(True)
bpy.ops.export_scene.fbx(filepath=f'{OUT}/Warehouse.fbx', use_selection=True, apply_unit_scale=True,
                         apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', bake_space_transform=True)

# ---------------------------------------------------------------- previews
world = bpy.data.worlds.new('W'); scene.world = world; world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.66, 0.66, 0.66, 1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.0
gm = bpy.data.materials.new('Ground'); gm.use_nodes = True
gb = gm.node_tree.nodes['Principled BSDF']
gb.inputs['Base Color'].default_value = (0.08, 0.08, 0.08, 1); gb.inputs['Roughness'].default_value = 0.95
gb.inputs['Emission Color'].default_value = (0.66, 0.66, 0.66, 1); gb.inputs['Emission Strength'].default_value = 0.68
gme = bpy.data.meshes.new('Ground'); gbm = bmesh.new()
bmesh.ops.create_grid(gbm, x_segments=1, y_segments=1, size=3000); gbm.to_mesh(gme); gbm.free()
ground = bpy.data.objects.new('Ground', gme); scene.collection.objects.link(ground); gme.materials.append(gm)
sun_d = bpy.data.lights.new('Sun', 'SUN'); sun_d.energy = 3.0; sun_d.angle = math.radians(10)
sun = bpy.data.objects.new('Sun', sun_d); scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(48), 0, math.radians(38))
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x, scene.render.resolution_y = 1672, 941
scene.view_settings.view_transform = 'Standard'
cam_d = bpy.data.cameras.new('Cam'); cam_d.clip_end = 8000
cam = bpy.data.objects.new('Cam', cam_d); scene.collection.objects.link(cam); scene.camera = cam
def shoot(name, loc, target, lens=50, ortho=None):
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    if ortho: cam_d.type = 'ORTHO'; cam_d.ortho_scale = ortho
    else: cam_d.type = 'PERSP'; cam_d.lens = lens
    scene.render.filepath = f'{OUT}/{name}.png'; bpy.ops.render.render(write_still=True)

shoot('render-34', (25.0, -26.0, 11.0), (-1.0, 0.0, 2.6), 43)
shoot('render-side', (0, -60, 4.3), (0, 0, 4.3), ortho=16.6)

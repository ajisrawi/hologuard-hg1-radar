"""HoloGuard HG-1 enclosure -- parametric FreeCAD model.

Frame: X = width (azimuth), Y = height (elevation), Z = depth, +Z toward the
radome (boresight). Fin tips at Z = 0, radome face at Z = ENV_D = 57 mm.

Run headless:
  "C:/Program Files/FreeCAD 1.1/bin/freecadcmd.exe" mech/build_enclosure.py
Outputs (mech/out): HG1_enclosure.FCStd, HG1_enclosure.step, <part>.stl,
mass report (mass_report.json) and 3-view drawing data (views.json).
"""
import json
import math
import os
import sys

import FreeCAD as App
import Part
import Mesh
import MeshPart

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else \
    r"C:/Users/ahmad/Documents/3d holographic radar/mech"
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import hg1_params as P  # noqa: E402

OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
V = App.Vector

W, H, D = P.ENV_W, P.ENV_H, P.ENV_D
R = P.ENV_CORNER_R
Z_FIN0 = 0.0
Z_BACK0 = P.FIN_H                       # 11.0  back plate outer face
Z_BACK1 = Z_BACK0 + P.BACKWALL          # 13.5  back plate inner face
Z_LIP = D - 3.0                         # 54.0  housing / radome joint
Z_RAD_IN = D - P.RADOME_T               # 56.0  radome inner skin
Z_ANT_B = 45.9                          # ANT board back (component) side
Z_ANT_F = Z_ANT_B + P.ANT_PCB_T         # 48.0  antenna face
Z_DSP_F = 33.5                          # DSP rear-facing (F) side
Z_DSP_B = Z_DSP_F + P.DIG_PCB_T         # 35.1
Y_DSP = 20.0
Y_PWR_BOT = -97.6                       # PWR board underside (horizontal)
Z_PWR_C = 29.0                          # PWR board / M12 axis depth
Y_IN = -H / 2 + P.WALL                  # interior floor (-99.3)


def rrect_face(w, h, r, z=0.0):
    r = min(r, w / 2 - 0.01, h / 2 - 0.01)
    x0, x1, y0, y1 = -w / 2, w / 2, -h / 2, h / 2
    e = []
    e.append(Part.LineSegment(V(x0 + r, y0, z), V(x1 - r, y0, z)).toShape())
    e.append(Part.Arc(V(x1 - r, y0, z), V(x1 - r + r * math.sin(math.pi / 4), y0 + r - r * math.cos(math.pi / 4), z),
                      V(x1, y0 + r, z)).toShape())
    e.append(Part.LineSegment(V(x1, y0 + r, z), V(x1, y1 - r, z)).toShape())
    e.append(Part.Arc(V(x1, y1 - r, z), V(x1 - r + r * math.cos(math.pi / 4), y1 - r + r * math.sin(math.pi / 4), z),
                      V(x1 - r, y1, z)).toShape())
    e.append(Part.LineSegment(V(x1 - r, y1, z), V(x0 + r, y1, z)).toShape())
    e.append(Part.Arc(V(x0 + r, y1, z), V(x0 + r - r * math.sin(math.pi / 4), y1 - r + r * math.cos(math.pi / 4), z),
                      V(x0, y1 - r, z)).toShape())
    e.append(Part.LineSegment(V(x0, y1 - r, z), V(x0, y0 + r, z)).toShape())
    e.append(Part.Arc(V(x0, y0 + r, z), V(x0 + r - r * math.cos(math.pi / 4), y0 + r - r * math.sin(math.pi / 4), z),
                      V(x0 + r, y0, z)).toShape())
    return Part.Face(Part.Wire(e))


def rrect_solid(w, h, r, z0, z1):
    return rrect_face(w, h, r, z0).extrude(V(0, 0, z1 - z0))


def box(cx, cy, cz, sx, sy, sz):
    return Part.makeBox(sx, sy, sz, V(cx - sx / 2, cy - sy / 2, cz - sz / 2))


def cyl(r, h, base, axis=V(0, 0, 1)):
    return Part.makeCylinder(r, h, base, axis)


def try_fillet(shape, radius, pick):
    try:
        edges = [e for e in shape.Edges if pick(e)]
        return shape.makeFillet(radius, edges) if edges else shape
    except Exception as exc:  # keep the model building even if OCC refuses one fillet
        print("fillet skipped:", exc)
        return shape


# =========================================================================
# Housing (AlSi10Mg die-cast): walls, back plate, fins, bosses, ports
# =========================================================================
outer = rrect_solid(W, H, R, Z_BACK0, Z_LIP)
inner = rrect_solid(W - 2 * P.WALL, H - 2 * P.WALL, R - P.WALL, Z_BACK1, Z_LIP + 1)
housing = outer.cut(inner)

# gasket land / radome register step (0.8 mm) on the lip
step_cut = rrect_solid(W - 2 * P.WALL + 1.6, H - 2 * P.WALL + 1.6, R - P.WALL + 0.8, Z_LIP - 1.2, Z_LIP + 0.1)
housing = housing.cut(step_cut)

# vertical convection fins on the back, clipped to the rounded outline
fin_clip = rrect_solid(W - 6, H - 6, R - 3, Z_FIN0, Z_BACK0 + 0.01)
fins = []
n_fin = int((W - 14) // P.FIN_PITCH) + 1
x_start = -(n_fin - 1) * P.FIN_PITCH / 2
MOUNT_HALF = 31.0       # fin-free square for the 4 x M6 mount bosses (VESA-like 50 mm)
for k in range(n_fin):
    x = x_start + k * P.FIN_PITCH
    f = box(x, 0, (Z_FIN0 + Z_BACK0) / 2, P.FIN_T, H, Z_BACK0 - Z_FIN0)
    f = f.common(fin_clip)
    if abs(x) < MOUNT_HALF:
        f = f.cut(box(x, 0, Z_BACK0 / 2, P.FIN_T + 1, 2 * MOUNT_HALF, Z_BACK0 + 1))
    fins.append(f)
fin_solid = fins[0].multiFuse(fins[1:])
# chamfer-like top relief on fin tips for drip/handling
housing = housing.fuse(fin_solid)

# mount bosses (4 x M6, 50 mm square) and centre heat pedestal under Versal
for sx in (-25, 25):
    for sy in (-25, 25):
        housing = housing.fuse(cyl(7.0, Z_BACK0, V(sx, sy, 0)))
        housing = housing.cut(cyl(2.5, 18.0, V(sx, sy, -1)))      # M6 tap drill 5.0
# Versal / PoL pedestal (DSP F side at Z_DSP_F faces back; Versal 2.5 mm tall)
ped_h = Z_DSP_F - 2.5 - 0.5 - Z_BACK1 + 0.5
ped_c = (Z_BACK1 + Z_DSP_F - 2.5 - 0.5) / 2 + 0.25
ped = box(0, Y_DSP + 10, ped_c, 30, 30, ped_h).cut(box(0, Y_DSP + 10, ped_c - 1.5, 25, 25, ped_h))
ped = ped.fuse([box(0, Y_DSP + 10, ped_c, 1.8, 28, ped_h), box(0, Y_DSP + 10, ped_c, 28, 1.8, ped_h)])
housing = housing.fuse(ped)   # hollow, cross-ribbed pedestal

# PCB stand-offs (shared by ANT and DSP: radar y 90 / 22 / -40 at x = +-70)
for x in (-70, 70):
    for y in (90, 22, -40):
        housing = housing.fuse(cyl(3.2, Z_DSP_F - Z_BACK1, V(x, y, Z_BACK1)))
        housing = housing.cut(cyl(1.05, 30, V(x, y, Z_BACK1 + 2)))       # M2.5 tap
    housing = housing.fuse(cyl(3.2, Z_ANT_B - 2 - Z_BACK1, V(x, -90, Z_BACK1)))
    housing = housing.cut(cyl(1.05, 40, V(x, -90, Z_BACK1 + 2)))

# radome screw bosses (8 x M3) in the corners of the wall
radome_screws = []
for sx in (-1, 1):
    for sy in (-1, 1):
        cx, cy = sx * (W / 2 - 6.0), sy * (H / 2 - 6.0)
        housing = housing.fuse(cyl(4.2, Z_LIP - 1.2 - Z_BACK1, V(cx, cy, Z_BACK1)))
        housing = housing.cut(cyl(1.25, 12, V(cx, cy, Z_LIP - 11)))
        radome_screws.append((cx, cy))
    for y in (-35.0, 35.0):
        cx, cy = sx * (W / 2 - 4.6), y
        housing = housing.fuse(box(cx, cy, (Z_BACK1 + Z_LIP - 1.2) / 2, 5.0, 9.0, Z_LIP - 1.2 - Z_BACK1))
        housing = housing.cut(cyl(1.25, 12, V(cx, cy, Z_LIP - 11)))
        radome_screws.append((cx, cy))

# M12 ports through the floor (+ Gore vent between them)
for x in (-42, 42):
    housing = housing.cut(cyl(8.1, 10, V(x, -H / 2 - 2, Z_PWR_C), V(0, 1, 0)))     # M16 panel hole
housing = housing.cut(cyl(6.1, 10, V(0, -H / 2 - 2, Z_PWR_C), V(0, 1, 0)))       # M12x1 vent
# earthing stud: tapped M4 in the floor
housing = housing.cut(cyl(1.7, 6, V(-68, -H / 2 - 1, 20), V(0, 1, 0)))

housing = housing.removeSplitter()

# =========================================================================
# Radome (PC/ABS) with inner pocket -> 1.0 mm skin, crowned edge fillet
# =========================================================================
radome = rrect_solid(W, H, R, Z_LIP, D)
radome = try_fillet(radome, 2.4, lambda e: abs(e.BoundBox.ZMin - D) < 1e-6 and abs(e.BoundBox.ZMax - D) < 1e-6)
pocket = rrect_solid(W - 2 * P.WALL - 1.6 + 0.2, H - 2 * P.WALL - 1.6 + 0.2, R - P.WALL, Z_LIP - 0.1, Z_RAD_IN)
skirt_in = rrect_solid(W - 2 * P.WALL - 1.6 - 0.2, H - 2 * P.WALL - 1.6 - 0.2, R - P.WALL, Z_LIP - 1.2, Z_LIP + 0.05)
register = rrect_solid(W - 2 * P.WALL + 1.6 - 0.2, H - 2 * P.WALL + 1.6 - 0.2, R - P.WALL + 0.8, Z_LIP - 1.2, Z_LIP)
radome = radome.cut(pocket).fuse(register.cut(skirt_in))
for (cx, cy) in radome_screws:     # counter-bored M3 screw holes in the radome rim
    radome = radome.cut(cyl(1.7, 6, V(cx, cy, Z_LIP - 2)))
    radome = radome.cut(cyl(3.0, 1.8, V(cx, cy, D - 1.6)))
radome = radome.removeSplitter()

screws = []
for (cx, cy) in radome_screws:
    hd = cyl(2.7, 1.6, V(cx, cy, D - 1.6)).cut(cyl(1.1, 1.0, V(cx, cy, D - 0.9)))   # socket recess
    screws.append(hd.fuse(cyl(1.5, 8.0, V(cx, cy, D - 9.6))))
screw_solid = screws[0].multiFuse(screws[1:])

# raised logo text on the radome margin (separate body -> separate material)
logo_solids = []
FONT = r"C:/Windows/Fonts/arialbd.ttf"
if os.path.exists(FONT):
    for txt, size, ty in (("HOLOGUARD", 7.0, -94.0), ("HG-1  4D HOLOGRAPHIC RADAR", 3.0, -98.6)):
        wires = Part.makeWireString(txt, FONT, size, 0.6 if size > 5 else 0.2)
        faces = []
        for ch in wires:
            if not ch:
                continue
            try:
                f = Part.Face(Part.Wire(ch[0])) if len(ch) == 1 else Part.makeFace(ch, "Part::FaceMakerBullseye")
                faces.append(f)
            except Exception:
                pass
        if not faces:
            continue
        comp = Part.makeCompound(faces)
        bb = comp.BoundBox
        comp.translate(V(-bb.Center.x, ty - bb.YMin, D - 0.001))
        logo_solids.append(comp.extrude(V(0, 0, 0.35)))
logo = Part.makeCompound(logo_solids) if logo_solids else None

# =========================================================================
# Internal parts: PCBs (with antenna copper), shield frame, fence, pedestal
# =========================================================================
ant = rrect_solid(P.ANT_PCB_W, P.ANT_PCB_H, 4.0, Z_ANT_B, Z_ANT_F)
with open(os.path.join(ROOT, "antenna", "element_design.json")) as fh:
    EL = json.load(fh)
lp, wp = EL["parasitic_patch_LxW_mm"]
patches = [box(x, y, Z_ANT_F + 0.03, lp, wp, 0.06) for (x, y) in P.tx_positions() + P.rx_positions()]
patches.append(box(0, 42, Z_ANT_F + 0.03, 31.4, 31.4, 0.06))
patches.append(box(0, -4, Z_ANT_F + 0.03, 4.0, 4.0, 0.06))
copper = patches[0].multiFuse(patches[1:])
gnss = box(0, 80, Z_ANT_F + 2.0, 18, 18, 4.0)

fence = box(0, P.FENCE_Y, (Z_ANT_F + Z_RAD_IN - 0.4) / 2, P.ANT_PCB_W - 7, 2.0, Z_RAD_IN - 0.4 - Z_ANT_F)
fence = fence.cut(box(0, P.FENCE_Y, Z_RAD_IN - 1.0, P.ANT_PCB_W - 7, 0.8, 1.6))   # absorber slot
absorber = box(0, P.FENCE_Y, Z_RAD_IN - 1.0, P.ANT_PCB_W - 8, 0.8, 1.2)

# shield / heat-spreader frame between ANT and DSP (Z 37.0 .. 45.9):
# 1.0 mm spreader web + 1.2 mm cavity walls + thermal pedestals that touch
# the GaN PAs and RFICs through 0.5 mm gap pads. Walls carry the conductive
# EMI gasket to the ANT board's Dwgs.User wall lines.
FZ0, FZ1 = 37.0, Z_ANT_B - 0.05
WT, WEB = 1.2, 1.0
rfic_y = P.RX_Y0 - 1.5 * P.D
pair_cx = [P.RX_X0 + (2 * k + 0.5) * P.D for k in range(6)]


def wall_rect(cx, cy, w, h):
    o = box(cx, cy, (FZ0 + FZ1) / 2, w, h, FZ1 - FZ0)
    return o.cut(box(cx, cy, (FZ0 + FZ1) / 2, w - 2 * WT, h - 2 * WT, FZ1 - FZ0 + 1))


web = box(0, 3.0, FZ0 + WEB / 2, 146, 178, WEB)
for s_ in (-1, 1):
    web = web.cut(box(s_ * 34, -14, FZ0, 32, 9, 4))
web = web.cut(box(0, -12, FZ0, 18, 9, 4))
for x in (-70, 70):
    for y in (90, 22, -40, -90):
        web = web.cut(cyl(3.6, 4, V(x, y, FZ0 - 1)))
for sx in (-1, 1):                    # lightening windows away from hot spots
    for (cy, hh) in ((70.0, 26.0), (14.0, 30.0)):
        web = web.cut(box(sx * 58, cy, FZ0, 18, hh, 4))
walls = [wall_rect(0, 3.0, 146, 178), wall_rect(0, 50.0, 146, 88),
         wall_rect(0, -36.0, 146, 14)]
walls += [wall_rect(c, rfic_y, 17, 30) for c in pair_cx]
peds = [box(x - (11.0 if x > 0 else -11.0), y, (FZ0 + FZ1 - 2.0) / 2, 6, 6, FZ1 - 2.0 - FZ0)
        for (x, y) in P.tx_positions()]
peds += [box(c, rfic_y, (FZ0 + FZ1 - 1.6) / 2, 8, 8, FZ1 - 1.6 - FZ0) for c in pair_cx]
peds += [box(s_ * 30, 40.5, (FZ0 + FZ1 - 1.6) / 2, 6, 6, FZ1 - 1.6 - FZ0) for s_ in (-1, 1)]
frame = web.fuse(walls + peds).removeSplitter()

dsp = rrect_solid(P.DIG_PCB_W, P.DIG_PCB_H, 4.0, Z_DSP_F, Z_DSP_B)
dsp.translate(V(0, Y_DSP, 0))
versal = box(0, Y_DSP + 10, Z_DSP_F - 1.25, 23, 23, 2.5)
pwr = Part.makeBox(P.PWR_PCB_W, P.PWR_PCB_T, P.PWR_PCB_H,
                   V(-P.PWR_PCB_W / 2, Y_PWR_BOT, Z_PWR_C - P.PWR_PCB_H / 2))
tim = box(0, Y_DSP + 10, Z_DSP_F - 2.5 - 0.25, 30, 30, 0.5)

# =========================================================================
# External hardware: M12 receptacles + mated plugs, vent, mount bracket
# =========================================================================
hw = []
plugs = []
for x in (-42, 42):
    y0 = -H / 2 - 0.2
    nut = Part.makePolygon([V(x + 10.4 * math.cos(a), y0, Z_PWR_C + 10.4 * math.sin(a))
                            for a in [k * math.pi / 3 + math.pi / 6 for k in range(7)]])
    nut = Part.Face(nut).extrude(V(0, -3.0, 0)).cut(cyl(8.0, 5, V(x, y0 + 1, Z_PWR_C), V(0, -1, 0)))
    barrel = cyl(6.0, 12.0, V(x, y0, Z_PWR_C), V(0, -1, 0)).cut(cyl(4.6, 13, V(x, y0 + 0.5, Z_PWR_C), V(0, -1, 0)))
    hw += [nut, barrel]
    # mated cable plug: knurled coupling nut + overmould + strain relief + cable
    ring = cyl(7.6, 11.0, V(x, y0 - 6.0, Z_PWR_C), V(0, -1, 0))
    for k in range(24):
        a = 2 * math.pi * k / 24
        ring = ring.cut(box(x + 7.6 * math.cos(a), y0 - 11.5, Z_PWR_C + 7.6 * math.sin(a), 0.8, 9.0, 0.8))
    body = cyl(7.0, 22.0, V(x, y0 - 17.0, Z_PWR_C), V(0, -1, 0))
    relief = Part.makeCone(5.5, 3.6, 14.0, V(x, y0 - 39.0, Z_PWR_C), V(0, -1, 0))
    cable = cyl(3.3, 60.0, V(x, y0 - 53.0, Z_PWR_C), V(0, -1, 0))
    plugs.append(ring.fuse([body, relief]))
    hw.append(cable)
vent = cyl(6.0, 4.0, V(0, -H / 2 - 0.2, Z_PWR_C), V(0, -1, 0)).fuse(
    Part.Face(Part.makePolygon([V(9.0 * math.cos(a), -H / 2 - 4.2, Z_PWR_C + 9.0 * math.sin(a))
                                for a in [k * math.pi / 3 for k in range(7)]])).extrude(V(0, -3.5, 0)))
hw.append(vent)
ground_stud = cyl(1.5, 8, V(-68, -H / 2 - 4, 20), V(0, 1, 0))
hw.append(ground_stud)
connectors = hw[0].multiFuse(hw[1:])
plug_solid = plugs[0].fuse(plugs[1])

# tilt bracket (6061-T6 anodised): adapter plate, yoke, pivots, pole clamp, pole
plate = box(0, 0, -3.0, 70, 70, 6.0)
for sx in (-25, 25):
    for sy in (-25, 25):
        plate = plate.cut(cyl(3.3, 10, V(sx, sy, -8)))
plate = plate.fuse(box(0, 0, -11.0, 40, 30, 10.0))           # hub
yoke_l = box(-46, 0, -20.0, 6, 40, 34).fuse(box(-30, 0, -34.0, 38, 40, 6))
yoke_r = box(46, 0, -20.0, 6, 40, 34).fuse(box(30, 0, -34.0, 38, 40, 6))
ears = box(-39, 0, -13.0, 8, 26, 14).fuse(box(39, 0, -13.0, 8, 26, 14))
pivot = cyl(4.0, 104, V(-52, 0, -14), V(1, 0, 0))
knobs = cyl(9.0, 7, V(-56, 0, -14), V(1, 0, 0)).fuse(cyl(9.0, 7, V(49, 0, -14), V(1, 0, 0)))
clamp = box(0, -14.0, -46.0, 64, 44, 18).cut(cyl(24.6, 60, V(0, -40, -64), V(0, 1, 0)))
bracket = plate.fuse([yoke_l, yoke_r, ears, clamp]).removeSplitter()
pole = cyl(24.0, 360, V(0, -330, -64), V(0, 1, 0)).cut(cyl(21.0, 362, V(0, -331, -64), V(0, 1, 0)))
hardware_dark = pivot.fuse(knobs)

# =========================================================================
# Document, mass, export
# =========================================================================
doc = App.newDocument("HG1_enclosure")
parts = {
    "housing": (housing, 2.68),           # AlSi10Mg g/cc
    "radome": (radome, 1.12),             # PC/ABS
    "radome_screws": (screw_solid, 7.9),
    "logo": (logo, 1.12) if logo else None,
    "ant_pcb": (ant, 1.95),
    "ant_copper": (copper, 8.9),
    "gnss_patch": (gnss, 3.9),
    "iso_fence": (fence, 2.70),
    "absorber": (absorber, 1.6),
    "shield_frame": (frame, 2.68),
    "dsp_pcb": (dsp, 1.85),
    "versal": (versal, 2.2),
    "tim_pad": (tim, 3.0),
    "pwr_pcb": (pwr, 1.85),
    "connectors": (connectors, 7.9),
    "m12_plugs": (plug_solid, 1.4),
    "bracket": (bracket, 2.70),
    "bracket_hw": (hardware_dark, 7.9),
    "pole": (pole, 7.9),
}
mass = {}
for name, val in parts.items():
    if val is None:
        continue
    shp, rho = val
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = shp
    mass[name] = round(shp.Volume / 1000.0 * rho, 1)
    mesh = MeshPart.meshFromShape(Shape=shp, LinearDeflection=0.04, AngularDeflection=0.15, Relative=False)
    mesh.write(os.path.join(OUT, f"{name}.stl"))
doc.recompute()
doc.saveAs(os.path.join(OUT, "HG1_enclosure.FCStd"))
import Import  # noqa: E402
Import.export([o for o in doc.Objects if o.Name not in ("pole", "m12_plugs")],
              os.path.join(OUT, "HG1_enclosure.step"))

# radar unit mass (excl. bracket, pole, cables); boards replaced by measured
# PCB volume x density, components lumped in a 35 % adder on PCB mass
unit = ["housing", "radome", "radome_screws", "logo", "ant_pcb", "ant_copper", "gnss_patch",
        "iso_fence", "absorber", "shield_frame", "dsp_pcb", "versal", "tim_pad", "pwr_pcb", "connectors"]
pcb_adder = 0.35 * (mass["ant_pcb"] + mass["dsp_pcb"] + mass["pwr_pcb"])
total = sum(mass.get(k, 0) for k in unit) - mass["connectors"] + 46.0 + pcb_adder   # M12 x2 + vent: 46 g
bb = housing.BoundBox.united(radome.BoundBox)
report = {"mass_g": mass, "pcb_component_adder_g": round(pcb_adder, 1),
          "radar_unit_mass_g": round(total, 1),
          "envelope_mm": [round(bb.XLength, 2), round(bb.YLength, 2), round(bb.ZLength, 2)],
          "housing_wetted_area_m2": round(housing.Area / 1e6, 4),
          "interior_volume_cc": round(inner.Volume / 1000, 1)}
with open(os.path.join(OUT, "mass_report.json"), "w") as fh:
    json.dump(report, fh, indent=2)

# 2-D projections for the dimensioned drawing (TechDraw works headless)
try:
    import TechDraw
    unit_shape = Part.makeCompound([housing, radome, connectors])
    views = {}
    for vname, d in (("front", V(0, 0, 1)), ("side", V(1, 0, 0)), ("bottom", V(0, -1, 0)), ("back", V(0, 0, -1))):
        vis = TechDraw.projectEx(unit_shape, d)[0]
        segs = []
        for e in vis.Edges:
            pts = e.discretize(Deflection=0.2) if e.Length > 0.5 else [e.Vertexes[0].Point, e.Vertexes[-1].Point]
            segs.append([[round(p.x, 2), round(p.y, 2)] for p in pts])
        views[vname] = segs
    with open(os.path.join(OUT, "views.json"), "w") as fh:
        json.dump(views, fh)
except Exception as exc:
    print("projection skipped:", exc)

print(json.dumps(report, indent=1))

"""Generate the three HoloGuard HG-1 PCBs as KiCad 10 boards.

  HG1-ANT  150 x 190 mm, 10-layer hybrid (RO4003C/RO4450F + 370HR + RO4350B)
           L1-L4 antenna (parasitic, driven, slotted GND, stripline feed);
           bottom side: 6x HRX-8 RFIC, 6x AD9083, 6x GaN PA, 2x TX beamformer,
           dual chirp synthesizer, HMC7044 JESD clocking, LDOs.
  HG1-DSP  146 x 150 mm, 12-layer: Versal AI Edge, 2x LPDDR4, eMMC, QSPI,
           GbE PHY, MCU, GNSS, BLE/Wi-Fi Remote-ID, IMU, PoL regulators.
  HG1-PWR  146 x 34 mm, 6-layer 2 oz: M12 power/IO + M12 X-coded Ethernet,
           surge/reverse protection, 28 V GaN drain buck-boost, 5 V buck,
           -5 V GaN gate bias, magnetics, RS-485 / 1PPS.

This is a placement + RF-critical-copper layout (antenna, feeds, RF fan-out,
LO/IF trunks, planes, shield-frame outlines). Remaining digital/power
routing is to be completed interactively in KiCad after schematic capture.

Run with KiCad's interpreter:
  "C:/Program Files/KiCad/10.0/bin/python.exe" board/generate_boards.py
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import hg1_params as P  # noqa: E402
import pcbnew  # noqa: E402
from kicad_helpers import Board  # noqa: E402

OUT = os.path.join(HERE, "kicad")
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(ROOT, "antenna", "element_design.json")) as fh:
    EL = json.load(fh)

L_PAR, W_PAR = EL["parasitic_patch_LxW_mm"]
L_DRV, W_DRV = EL["driven_patch_LxW_mm"]
SLOT_L = EL["slot"]["length_mm"]
SLOT_W = EL["slot"]["width_mm"]
ARM_L = EL["slot"]["end_arms_mm"][0]
STUB = EL["stub_beyond_slot_mm"]
W_STRIP = EL["stripline_50ohm_width_mm"]
W_CPW = 0.30          # B.Cu grounded-CPW on 0.17 mm RO4350B (~50 ohm)


def h_slot(cx, cy):
    """Dog-bone (H) coupling slot polygon, long axis along y."""
    a, Lh, e, t = SLOT_W / 2, SLOT_L / 2, ARM_L / 2, SLOT_W / 2
    pts = [(-e, Lh + t), (e, Lh + t), (e, Lh - t), (a, Lh - t), (a, -Lh + t), (e, -Lh + t),
           (e, -Lh - t), (-e, -Lh - t), (-e, -Lh + t), (-a, -Lh + t), (-a, Lh - t), (-e, Lh - t)]
    return [(cx + x, cy + y) for x, y in pts]


def rect_pts(cx, cy, w, h):
    return [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2),
            (cx - w / 2, cy + h / 2)]


# =========================================================================
# HG1-ANT
# =========================================================================
def build_ant():
    B = Board(10, P.ANT_PCB_T)
    W, H = P.ANT_PCB_W, P.ANT_PCB_H
    outline = B.outline_rounded(W, H, 4.0)
    full = B.rounded_pts(W, H, 4.0, inset=0.5)

    rx = P.rx_positions()
    tx = P.tx_positions()
    slots = []

    # ---------------- radiating elements (L1 parasitic, L2 driven) -------
    for name, (x, y) in [(f"TX{i + 1}", p) for i, p in enumerate(tx)] + \
                        [(f"RX{i + 1:02d}", p) for i, p in enumerate(rx)]:
        B.rect("F.Cu", x, y, L_PAR, W_PAR)
        B.rect("In1.Cu", x, y, L_DRV, W_DRV)
        slots.append(h_slot(x, y))

    # Remote-ID / RF-detect 2.45 GHz patch (with 5.8 GHz U-slot) + GNSS patch + OTA cal probe
    B.rect("F.Cu", 0, 42, 31.4, 31.4)
    B.via(0, 42 - 6.5, "RID_RF", 0.3, 0.6)
    B.custom_fp("AE1", "GNSS L1/L5 ceramic patch 18x18 (Taoglas CGGP.18 class)", 0, 80,
                [dict(num=1, x=0, y=-1.8, w=1.2, h=1.2, net="GNSS_RF"),
                 dict(num=2, x=-6, y=6, w=3, h=3, net="GND"), dict(num=3, x=6, y=6, w=3, h=3, net="GND"),
                 dict(num=4, x=-6, y=-6, w=3, h=3, net="GND"), dict(num=5, x=6, y=-6, w=3, h=3, net="GND")],
                courtyard=(18.5, 18.5))
    for gx, gy in ((-6, 86), (6, 86), (-6, 74), (6, 74)):
        B.bvia(gx, gy, "GND", "F.Cu", "In4.Cu", 0.2, 0.45)
    B.rect("F.Cu", 0, -4, 4.0, 4.0)
    B.via(0, -4 - 1.2, "CAL_PROBE", 0.2, 0.45)

    # ---------------- top-side GND ring + TX/RX isolation fence ----------
    ring_in = B.rounded_pts(W, H, 4.0, inset=3.5)
    B.zone("F.Cu", "GND", full, holes=[ring_in], priority=1, name="TOP_GND_RING")
    B.rect("F.Cu", 0, P.FENCE_Y, W - 7, 3.0, net="GND")
    for k in range(int((W - 10) / 1.5)):
        x = -W / 2 + 5 + k * 1.5
        # blind L1->L5: ties the soldered fence to the L5 ground without
        # blocking bottom-side routing
        B.bvia(x, P.FENCE_Y - 0.75, "GND", "F.Cu", "In4.Cu", 0.2, 0.4)
        B.bvia(x + 0.75, P.FENCE_Y + 0.75, "GND", "F.Cu", "In4.Cu", 0.2, 0.4)

    # ---------------- L3 slotted ground, L5/L7/L9 solid grounds ---------
    B.zone("In2.Cu", "GND", full, holes=slots, priority=0, name="L3_SLOT_GND")
    for lay in ("In4.Cu", "In6.Cu", "In8.Cu"):
        B.zone(lay, "GND", full, priority=0)
    # L6 power islands
    B.zone("In5.Cu", "+28V_PA", [(-W / 2 + 1, -10), (W / 2 - 1, -10), (W / 2 - 1, H / 2 - 1),
                                 (-W / 2 + 1, H / 2 - 1)], priority=1)
    B.zone("In5.Cu", "+3V3_RF", [(-W / 2 + 1, -H / 2 + 1), (W / 2 - 1, -H / 2 + 1),
                                 (W / 2 - 1, -11), (-W / 2 + 1, -11)], priority=1)
    # bottom GND pour
    B.zone("B.Cu", "GND", full, priority=0, clearance=0.25)

    # ---------------- RX chain: feed -> via -> RFIC -> ADC ---------------
    pair_cx = [P.RX_X0 + (2 * k + 0.5) * P.D for k in range(6)]
    rfic_y = P.RX_Y0 - 1.5 * P.D
    adc_y = -36.0
    rfics, adcs = [], []
    for k, cx in enumerate(pair_cx):
        # EP thermal vias must be BLIND (L5-L10) under the antenna: use the
        # plain footprint here; blind-via farm is specified in the fab notes.
        rf = B.fp("Package_DFN_QFN", "QFN-64-1EP_9x9mm_P0.5mm_EP3.8x3.8mm",
                  f"U{10 + k}", "HRX-8  8-ch Ku SiGe RX RFIC (LNA+IQ mix+IF)", cx, rfic_y, bottom=True)
        ad = B.fp("Package_BGA", "BGA-121_9.0x9.0mm_Layout11x11_P0.8mm_Ball0.4mm_Pad0.35mm_NSMD",
                  f"U{20 + k}", "AD9083BBCZ 16-ch 125 MHz CTSD ADC", cx, adc_y, bottom=True)
        for p_ in rf.Pads():
            if p_.GetNumber() == "65":
                p_.SetNet(B.net("GND"))
        rfics.append(rf)
        adcs.append(ad)
        side = 1 if cx > 0 else -1
        B.fp("Package_DFN_QFN", "DFN-10-1EP_3x3mm_P0.5mm_EP1.65x2.38mm", f"U{30 + k}",
             "LT3045 ultra-low-noise LDO (RFIC)", cx, -89.0, bottom=True)
        B.fp("Package_DFN_QFN", "DFN-10-1EP_3x3mm_P0.5mm_EP1.65x2.38mm", f"U{40 + k}",
             "ADP7159 LDO (ADC)", cx + side * 5.5, -24.0, bottom=True)

    used = {id(f): set() for f in rfics}
    # Non-crossing fan-out (pair-relative, s = outward):
    #   rows 0/3 : via(8.5) -> (6.0, py+-2.75) -> (5.2, py) -> pad(4.4)
    #   rows 1/2 : via(8.5) -> (6.6, py) -> pad(4.4)
    # A single GND via per transition sits on the side away from the route.
    row_pad_dy = {0: 3.25, 1: 1.25, 2: -1.25, 3: -3.25}
    for i, (x, y) in enumerate(rx):
        col, row = i % P.RX_NX, i // P.RX_NX
        k = col // 2
        c = pair_cx[k]
        s = -1 if col % 2 == 0 else 1
        net = f"RX{i + 1:02d}"
        vx = x + s * 4.0
        B.track("In3.Cu", [(vx, y), (x - s * STUB, y)], W_STRIP, net)   # L4 stripline + stub
        B.via(vx, y, net, 0.2, 0.45)
        B.via(vx, y + (1.0 if row < 2 else -1.0), "GND", 0.2, 0.4)
        pad = B.nearest_pad(rfics[k], c + s * 4.4, rfic_y + row_pad_dy[row], used[id(rfics[k])],
                            side="left" if s < 0 else "right")
        px, py = B.pad_xy(pad)
        if row in (0, 3):
            sgn = 1 if row == 0 else -1
            pts = [(vx, y), (c + s * 6.0, py + sgn * 2.75), (c + s * 5.2, py)]
        else:
            pts = [(vx, y), (c + s * 6.6, py)]
        B.connect("B.Cu", rfics[k], pad, pts, W_CPW, net)

    # IF fan-out: 16 RFIC top-edge pins -> AD9083 balls, planar & non-crossing
    #   pins 0-2  -> left ball column (nested escape channels at c-5.6/-5.2/-4.8)
    #   pins 3-12 -> bottom ball row
    #   pins 13-15-> right ball column (mirror)
    for k, (rf, ad) in enumerate(zip(rfics, adcs)):
        c = pair_cx[k]
        top = sorted([p for p in rf.Pads() if p.GetNumber().isdigit() and int(p.GetNumber()) <= 64
                      and B.pad_xy(p)[1] > rfic_y + 4.0], key=lambda p: B.pad_xy(p)[0])
        balls = list(ad.Pads())
        bx = sorted({round(B.pad_xy(p)[0], 2) for p in balls})
        by = sorted({round(B.pad_xy(p)[1], 2) for p in balls})

        def ball(ix, iy):
            for p in balls:
                x_, y_ = B.pad_xy(p)
                if abs(x_ - bx[ix]) < 0.05 and abs(y_ - by[iy]) < 0.05:
                    return p
            raise RuntimeError("ball not found")

        plan = []
        for j, (chan, yh, iy) in enumerate(((-5.6, -56.5, 3), (-5.2, -55.5, 2), (-4.8, -54.5, 1))):
            plan.append((top[j], ball(0, iy), "L", c + chan, yh))
        for j in range(10):
            plan.append((top[3 + j], ball(j, 0), "B", None, None))
        for j, (chan, yh, iy) in enumerate(((4.8, -54.5, 1), (5.2, -55.5, 2), (5.6, -56.5, 3))):
            plan.append((top[13 + j], ball(10, iy), "R", c + chan, yh))
        for j, (p_rf, p_ad, kind, chan_x, yh) in enumerate(plan):
            net = f"IF{k + 1}_CH{j // 2 + 1}{'IQ'[j % 2]}"
            p_rf.SetNet(B.net(net))
            p_ad.SetNet(B.net(net))
            (x1, y1), (x2, y2) = B.pad_xy(p_rf), B.pad_xy(p_ad)
            if kind == "B":
                pts = [(x1, y1), (x1, -50.0), (x2, -44.0), (x2, y2)]
            else:
                pts = [(x1, y1), (x1, yh), (chan_x, yh), (chan_x, y2), (x2, y2)]
            B.track("B.Cu", pts, 0.1, net)

    # ---------------- clocking / chirp synthesis -------------------------
    syn = {
        "Y1": ("Oscillator", "Oscillator_SMD_Diodes_FN-4Pin_7.0x5.0mm", "100 MHz OCXO, -165 dBc/Hz floor", 0, 88),
        "U1": ("Package_DFN_QFN", "QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm", "ADF4159 FMCW PLL (TX chirp)", -16, 72),
        "U2": ("Package_DFN_QFN", "QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm", "HMC733 VCO 10-20 GHz (TX)", -7, 72),
        "U3": ("Package_DFN_QFN", "QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm", "ADF4159 FMCW PLL (RX LO chirp)", 7, 72),
        "U4": ("Package_DFN_QFN", "QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm", "HMC733 VCO 10-20 GHz (LO)", 16, 72),
        "U5": ("Package_DFN_QFN", "QFN-16-1EP_3x3mm_P0.5mm_EP1.7x1.7mm", "HMC903 LO amp (+14 dBm)", 16, 60),
        "U8": ("Package_DFN_QFN", "QFN-16-1EP_3x3mm_P0.5mm_EP1.7x1.7mm", "HMC903 TX drive amp", -16, 60),
        "U9": ("Package_DFN_QFN", "QFN-64-1EP_9x9mm_P0.5mm_EP3.8x3.8mm",
               "HMC7044 JESD204B clock + SYSREF (14 out)", 0, 6),
    }
    U = {}
    for ref, (lib, name, val, x, y) in syn.items():
        U[ref] = B.fp(lib, name, ref, val, x, y, bottom=True)
        for p_ in U[ref].Pads():
            if p_.GetNumber() in ("17", "25", "65") and ref != "Y1":
                p_.SetNet(B.net("GND"))
    us = {r: set() for r in U}

    def link(a, ax, ay, b, bx_, by_, net, via_y=None, width=W_CPW):
        """Route pad(a near ax,ay) -> pad(b near bx_,by_) with an orthogonal dog-leg."""
        pa_ = B.nearest_pad(U[a], ax, ay, us[a])
        pb_ = B.nearest_pad(U[b], bx_, by_, us[b])
        pa_.SetNet(B.net(net))
        (x1, y1), (x2, y2) = B.pad_xy(pa_), B.pad_xy(pb_)
        if via_y is None:
            pts = [(x1, y1), ((x1 + x2) / 2, y1), ((x1 + x2) / 2, y2)]
        else:
            pts = [(x1, y1), (x1, via_y), (x2, via_y)]
        B.connect("B.Cu", U[b], pb_, pts, width, net)
        return pa_

    link("U1", -13.5, 72, "U2", -9.5, 72, "TX_VCO_TUNE")
    link("U3", 9.5, 72, "U4", 13.5, 72, "LO_VCO_TUNE")
    link("U2", -7, 69.5, "U8", -16, 62, "TX_VCO_OUT", via_y=66.0)
    link("U4", 16, 69.5, "U5", 16, 62, "LO_VCO_OUT", via_y=66.0)
    p_ref = link("Y1", -2, 85.5, "U1", -16, 74.5, "REF_100M", via_y=80.0, width=0.2)
    pr = B.nearest_pad(U["U3"], 7, 74.5, us["U3"])
    rx_, ry_ = B.pad_xy(p_ref)
    B.connect("B.Cu", U["U3"], pr, [(rx_, 80.0), (B.pad_xy(pr)[0], 80.0)], 0.2, "REF_100M")

    # LO distribution: U5 -> blind via -> L8 (In7) stripline bus around the
    # RX block -> blind via -> each RFIC LO pin (bottom edge). 1:6 reactive
    # tee tree, +14 dBm in -> ~+3 dBm per RFIC (needs 0 dBm).
    p_lo = B.nearest_pad(U["U5"], 16, 57.5, us["U5"])
    p_lo.SetNet(B.net("LO_CHIRP"))
    lx, ly = B.pad_xy(p_lo)
    B.track("B.Cu", [(lx, ly), (16.0, 55.5)], W_CPW, "LO_CHIRP")
    B.bvia(16.0, 55.5, "LO_CHIRP", "In7.Cu", "B.Cu")
    LO_BUS_Y, LO_X = -82.0, 63.0
    B.track("In7.Cu", [(16.0, 55.5), (LO_X, 55.5), (LO_X, LO_BUS_Y), (pair_cx[0], LO_BUS_Y)], 0.2,
            "LO_CHIRP")
    for k, c in enumerate(pair_cx):
        B.bvia(c, LO_BUS_Y, "LO_CHIRP", "In7.Cu", "B.Cu")
        pad = B.nearest_pad(rfics[k], c, rfic_y - 4.6, used[id(rfics[k])], side="bottom")
        B.connect("B.Cu", rfics[k], pad, [(c, LO_BUS_Y), (B.pad_xy(pad)[0], LO_BUS_Y + 3.0)],
                  W_CPW, "LO_CHIRP")

    # ---------------- TX: drive amp -> beamformer -> GaN PA -> element ----
    bf = {}
    for s, ref in ((-1, "U50"), (1, "U51")):
        bf[s] = B.fp("Package_DFN_QFN", "QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm_ThermalVias", ref,
                     "ADAR1000 4-ch Ku beamformer (DDMA phase code / spotlight)", s * 30, 40.5,
                     bottom=True)
        for p_ in bf[s].Pads():
            if not p_.GetNumber().isdigit() or int(p_.GetNumber()) > 48:
                p_.SetNet(B.net("GND"))
    used_bf = {s: set() for s in (-1, 1)}
    p_tx = B.nearest_pad(U["U8"], -16, 57.5, us["U8"])
    p_tx.SetNet(B.net("TX_CHIRP"))
    tx0, ty0 = B.pad_xy(p_tx)
    B.track("B.Cu", [(tx0, ty0), (tx0, 52.0)], W_CPW, "TX_CHIRP")
    for s in (-1, 1):
        pb_ = B.nearest_pad(bf[s], s * 30, 44.5, used_bf[s], side="top")
        bx2, by2 = B.pad_xy(pb_)
        B.connect("B.Cu", bf[s], pb_, [(tx0, 52.0), (bx2, 52.0)], W_CPW, "TX_CHIRP")

    for i, (x, y) in enumerate(tx):
        s = 1 if x > 0 else -1
        pa_x = x - s * 11.0
        pa = B.fp("Package_DFN_QFN", "QFN-24-1EP_4x4mm_P0.5mm_EP2.65x2.65mm_ThermalVias",
                  f"U{60 + i}", "Ku GaN-on-SiC PA 1 W (QGaN15, 28 V)", pa_x, y, bottom=True)
        for p_ in pa.Pads():
            if not p_.GetNumber().isdigit() or int(p_.GetNumber()) > 24:
                p_.SetNet(B.net("GND"))
        for dy in (-5.8, 5.8):
            B.fp("Capacitor_SMD", "C_1210_3225Metric", B.ref("C"), "10u 50V X7R drain",
                 pa_x, y + dy, bottom=True)
        net = f"TX{i + 1}"
        vx = x - s * 4.0
        B.track("In3.Cu", [(vx, y), (x + s * STUB, y)], W_STRIP, net)
        B.via(vx, y, net, 0.25, 0.5)
        B.via(vx + s * 0.8, y + 0.8, "GND", 0.2, 0.4)
        B.via(vx + s * 0.8, y - 0.8, "GND", 0.2, 0.4)
        u_pa = set()
        p_out = B.nearest_pad(pa, pa_x + s * 2.0, y, u_pa, side="right" if s > 0 else "left")
        B.connect("B.Cu", pa, p_out, [(vx, y), (B.pad_xy(p_out)[0] + s * 1.0, B.pad_xy(p_out)[1])],
                  W_CPW, net)
        p_in = B.nearest_pad(pa, pa_x - s * 2.0, y, u_pa, side="left" if s > 0 else "right")
        if abs(y - 40.5) < 1:
            p_bf = B.nearest_pad(bf[s], s * 33.5, 40.5, used_bf[s], side="right" if s > 0 else "left")
        else:
            p_bf = B.nearest_pad(bf[s], s * 32.0, 44.5 if y > 40.5 else 36.5, used_bf[s],
                                 side="top" if y > 40.5 else "bottom")
        n2 = f"TXDRV{i + 1}"
        p_bf.SetNet(B.net(n2))
        (x1, y1), (x2, y2) = B.pad_xy(p_bf), B.pad_xy(p_in)
        if abs(y - 40.5) < 1:
            pts = [(x1, y1), ((x1 + x2) / 2, y1), ((x1 + x2) / 2, y2)]
        else:
            pts = [(x1, y1), (x1, y2)]
        B.connect("B.Cu", pa, p_in, pts, W_CPW, n2)
        # PA thermal slug: footprint via farm (blind L5-L10) -> shield-frame heat spreader

    # ---------------- interconnect to DSP / power -----------------------
    conn = {}
    for s in (-1, 1):
        conn[s] = B.fp("Connector_Samtec", "Samtec_LSHM-150-xx.x-x-DV-N_2x50_P0.50mm_Vertical",
                       f"J{2 if s < 0 else 3}", "Samtec LSHM-150 JESD204B x12 lanes (10 mm stack)",
                       s * 34, -14, bottom=True)
    B.fp("Connector_Samtec", "Samtec_LSHM-120-xx.x-x-DV-N_2x20_P0.50mm_Vertical", "J4",
         "Samtec LSHM-120 SPI/sync/GNSS/RID/CAL", 0, -12, bottom=True)
    B.fp("Connector_Molex", "Molex_Micro-Fit_3.0_43650-0400_1x04_P3.00mm_Horizontal", "J1",
         "Molex Micro-Fit 4p: +28V_PA, +5V, GND x2", -52, 88, rot=0, bottom=True)
    # JESD204B: 4 lanes per ADC to the bottom pad row of the nearer mezzanine.
    # Lane nearest the connector takes the lowest jog and the furthest pad,
    # which keeps the fan-out planar.
    for s in (-1, 1):
        jp = sorted([p for p in conn[s].Pads() if p.GetNumber().isdigit()
                     and B.pad_xy(p)[1] < -14.0], key=lambda p: B.pad_xy(p)[0])
        jused = set()
        for k, (c, ad) in enumerate(zip(pair_cx, adcs)):
            if (c > 0) != (s > 0):
                continue
            tops = sorted([p for p in ad.Pads() if B.pad_xy(p)[1] > adc_y + 3.9],
                          key=lambda p: B.pad_xy(p)[0])
            lanes = tops[3:7]
            jx_min, jx_max = B.pad_xy(jp[0])[0], B.pad_xy(jp[-1])[0]
            inside = jx_min + 0.5 < c < jx_max - 0.5
            if inside:
                order = lanes
                targets = []
                for p in lanes:
                    cand = min((q for q in jp if q.GetNumber() not in jused),
                               key=lambda q: abs(B.pad_xy(q)[0] - B.pad_xy(p)[0]))
                    jused.add(cand.GetNumber())
                    targets.append(cand)
            else:
                toward = -1 if c > jx_max else 1          # travel direction
                order = sorted(lanes, key=lambda p: -toward * B.pad_xy(p)[0])   # leading first
                free = [q for q in jp if q.GetNumber() not in jused]
                free = free[::-1] if toward < 0 else free
                edge = free[:len(order)]                    # pads nearest this ADC
                targets = edge[::-1]                        # leading lane -> furthest pad
                for q in targets:
                    jused.add(q.GetNumber())
            for lane, (p, q) in enumerate(zip(order, targets)):
                net = f"JESD{k + 1}_L{lane}"
                p.SetNet(B.net(net))
                (x1, y1), (x2, y2) = B.pad_xy(p), B.pad_xy(q)
                yh = -29.5 + lane * 0.5
                B.connect("B.Cu", conn[s], q, [(x1, y1), (x1, yh), (x2, yh)], 0.12, net)

    # ---------------- mounting, shield-frame outlines, labels ------------
    holes = [(-70, 90), (70, 90), (-70, -90), (70, -90), (-70, 22), (70, 22), (-70, -40),
             (70, -40), (-18, 0), (18, 0)]
    for k, (x, y) in enumerate(holes):
        B.fp("MountingHole", "MountingHole_2.7mm_M2.5_Pad_Via", f"H{k + 1}", "M2.5", x, y,
             pad_net="GND")
    walls = [rect_pts(0, 7.5 + 87 / 2 - 7.5, 146, 88)]           # TX/synth cavity
    walls += [rect_pts(cx, rfic_y, 17, 30) for cx in pair_cx]     # per-RFIC cavities
    walls += [rect_pts(0, adc_y, 146, 14)]                        # ADC row
    for w in walls:
        B.polyline("Dwgs.User", w, 0.3, closed=True)
    # Blind thermal vias (B.Cu -> L9 GND) in every grounded exposed pad
    for f in B.b.GetFootprints():
        for p_ in f.Pads():
            if p_.GetNetname() == "GND" and p_.GetAttribute() == pcbnew.PAD_ATTRIB_SMD                     and p_.IsOnLayer(B.L("B.Cu")) and pcbnew.ToMM(p_.GetSize().x) > 1.5:
                cx_, cy_ = B.pad_xy(p_)
                hw = pcbnew.ToMM(p_.GetSize().x) / 2 - 0.5
                for dx in (-hw, 0, hw):
                    for dy in (-hw, 0, hw):
                        B.bvia(cx_ + dx, cy_ + dy, "GND", "In8.Cu", "B.Cu", 0.15, 0.35)
    # GND stitching: every free 3 mm grid point (keeps clear of patches,
    # slots, feeds, pads and routing on all layers)
    patch_keep = [rect_pts(x, y, L_PAR + 3.0, W_PAR + 3.0) for (x, y) in list(tx) + list(rx)]
    patch_keep += [rect_pts(0, 42, 35, 35), rect_pts(0, -4, 7, 7)]
    nst = B.stitch("GND", 3.0, keep=slots + patch_keep, margin=0.5,
                   region=(-W / 2 + 4, -H / 2 + 4, W / 2 - 4, H / 2 - 4))
    nst += B.stitch("GND", 2.1, keep=slots + patch_keep, margin=0.35,
                    region=(-W / 2 + 4, -H / 2 + 4, W / 2 - 4, H / 2 - 4))
    print(f"   ANT: {nst} GND stitching vias")
    B.text("Dwgs.User", "Shield/heat-spreader frame walls (AlSi10Mg, 1.5 mm, conductive gasket)",
           0, -96.5, 1.6)
    B.text("B.SilkS", "HoloGuard HG-1  ANT/RF  rev A", 0, 10, 2.5, mirrored=True, thickness=0.35)
    B.text("B.SilkS", "10L hybrid RO4003C/RO4450F/370HR/RO4350B 2.1 mm", 0, 14, 1.4, mirrored=True)
    B.text("F.SilkS", "HG-1 ANT  TX: 6  RX: 48  pitch 9.0 mm  H-pol", 0, 92.2, 1.4)
    # Patches are mask-free (immersion silver / ENEPIG): soldermask over a
    # patch detunes it by ~1-2 %.
    for (x, y) in list(tx) + list(rx):
        B.rect("F.Mask", x, y, L_PAR + 0.4, W_PAR + 0.4)
    B.rect("F.Mask", 0, 42, 31.8, 31.8)
    B.rect("F.Mask", 0, -4, 4.4, 4.4)
    return B


# =========================================================================
# HG1-DSP (viewed from its F side, which faces the rear wall; x mirrored
# relative to the radar frame; mezzanines are symmetric)
# =========================================================================
def build_dsp():
    B = Board(12, P.DIG_PCB_T)
    W, H = P.DIG_PCB_W, P.DIG_PCB_H
    B.outline_rounded(W, H, 4.0)
    full = B.rounded_pts(W, H, 4.0, inset=0.5)
    for lay in ("In1.Cu", "In3.Cu", "In5.Cu", "In8.Cu", "In10.Cu"):
        B.zone(lay, "GND", full)
    B.zone("In6.Cu", "VCCINT_0V8", rect_pts(0, 10, 60, 60), priority=1)
    B.zone("In6.Cu", "+1V1_DDR", rect_pts(-40, 14, 30, 50), priority=1)
    B.zone("B.Cu", "GND", full)

    parts = [
        ("Package_BGA", "Microchip_FCVG784_BGA-784_23x23mm_Layout28x28_P0.8mm", "U1",
         "XCVE2302-1LSESFVA784 Versal AI Edge (AIE-ML 3D beamforming)", 0, 10, 0),
        ("Package_BGA", "BGA-200_10x14.5mm_Layout12x22_P0.8x0.65mm", "U2",
         "LPDDR4 32Gb x32 (MT53E1G32D2)", -27, 14, 0),
        ("Package_BGA", "BGA-200_10x14.5mm_Layout12x22_P0.8x0.65mm", "U3",
         "LPDDR4 32Gb x32 (MT53E1G32D2)", 27, 14, 0),
        ("Package_BGA", "LFBGA-153_11.5x13mm_Layout14x14_P0.5mm", "U4", "eMMC 64 GB pSLC", -27, -14, 0),
        ("Package_SON", "WSON-8-1EP_8x6mm_P1.27mm_EP3.4x4.3mm", "U5", "QSPI NOR 512 Mb (boot)", -27, 36, 0),
        ("Package_DFN_QFN", "QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm", "U6",
         "DP83867IR GbE PHY + IEEE1588 SFD", 40, -50, 0),
        ("Package_QFP", "LQFP-64_10x10mm_P0.5mm", "U7", "STM32G474 housekeeping / power-seq / BIT", -42, -50, 0),
        ("RF_GPS", "ublox_NEO", "U8", "u-blox NEO-F10T GNSS timing (L1/L5)", 42, 52, 0),
        ("RF_Module", "Raytac_MDBT50Q", "U9", "nRF52840 BT5 LR Remote-ID rx", -48, 54, 0),
        ("Package_DFN_QFN", "QFN-40-1EP_6x6mm_P0.5mm_EP4.6x4.6mm", "U10",
         "nRF7002 Wi-Fi 6 2.4/5 GHz companion: Wi-Fi Beacon/NAN Remote-ID rx (fed from ANT RID patch)", -46, 32, 0),
        ("Package_LGA", "Bosch_LGA-14_3x2.5mm_P0.5mm", "U11", "ISM330DHCX 6-axis IMU", 0, -40, 0),
        ("Package_LGA", "LGA-12_2x2mm_P0.5mm", "U12", "LIS2MDL magnetometer", 8, -40, 0),
        ("Package_DFN_QFN", "QFN-40-1EP_6x6mm_P0.5mm_EP4.6x4.6mm_ThermalVias", "U20",
         "TPS546D24A 40 A PoL VCCINT 0.8 V", 44, 12, 0),
        ("Package_DFN_QFN", "QFN-40-1EP_6x6mm_P0.5mm_EP4.6x4.6mm_ThermalVias", "U21",
         "TPS546D24A PoL VCC_AIE 0.8 V", 44, -6, 0),
        ("Package_DFN_QFN", "QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm", "U22", "LT8640S 1V1/1V8/3V3 bucks", 44, 30, 0),
        ("Inductor_SMD", "L_Coilcraft_XAL6030-XXX", "L1", "XAL6030 0.22 uH", 58, 12, 0),
        ("Inductor_SMD", "L_Coilcraft_XAL6030-XXX", "L2", "XAL6030 0.22 uH", 58, -6, 0),
        ("Inductor_SMD", "L_Coilcraft_XAL6030-XXX", "L3", "XAL6030 1.0 uH", 58, 30, 0),
        ("Connector_FFC-FPC", "Hirose_FH12-30S-0.5SH_1x30-1MP_P0.50mm_Horizontal", "J5",
         "FFC to PWR/IO: GbE MDI, RS-485, 1PPS, discretes", 18, -68, 0),
        ("Connector_Molex", "Molex_Micro-Fit_3.0_43650-0400_1x04_P3.00mm_Horizontal", "J6",
         "Micro-Fit 4p: +12V_DSP in", -22, -66, 0),
    ]
    for lib, name, ref, val, x, y, rot in parts:
        B.fp(lib, name, ref, val, x, y, rot=rot)
    # mezzanine plugs on B side (faces ANT board); ANT (x,y) -> DSP (-x, y-20)
    for s, ref in ((-1, "J2"), (1, "J3")):
        B.fp("Connector_Samtec", "Samtec_LSHM-150-xx.x-x-DV-N_2x50_P0.50mm_Vertical", ref,
             "Samtec LSHM-150 (mate ANT)", -s * 34, -14 - 20, bottom=True)
    B.fp("Connector_Samtec", "Samtec_LSHM-120-xx.x-x-DV-N_2x20_P0.50mm_Vertical", "J4",
         "Samtec LSHM-120 (mate ANT)", 0, -12 - 20, bottom=True)
    # shares the ANT stand-offs at radar y = 90 / 22 / -40  (DSP y = radar y - 20)
    for k, (x, y) in enumerate([(-70, 70), (70, 70), (-70, 2), (70, 2), (-70, -60), (70, -60)]):
        B.fp("MountingHole", "MountingHole_2.7mm_M2.5_Pad_Via", f"H{k + 1}", "M2.5", x, y, pad_net="GND")
    # Versal heat-spreader keep-out (TIM pad to rear wall pedestal)
    B.polyline("Dwgs.User", rect_pts(0, 10, 34, 34), 0.3, closed=True)
    B.text("Dwgs.User", "Rear-wall pedestal + 0.5 mm TIM (Versal, PoL)", 0, 30, 1.4)
    B.text("F.SilkS", "HoloGuard HG-1  DSP  rev A  12L 370HR/Megtron-6 HDI", 0, -60, 1.8, thickness=0.3)
    return B


# =========================================================================
# HG1-PWR  (horizontal at housing bottom; +y = toward rear; B side faces down)
# =========================================================================
def m12_pads(n_pins, net_prefix):
    pads = []
    if n_pins == 8:
        pin_r = 2.6
        for k in range(7):
            a = math.radians(90 + k * 360 / 7)
            pads.append(dict(num=k + 1, x=pin_r * math.cos(a), y=pin_r * math.sin(a), w=1.5, h=1.5,
                             shape="circle", drill=0.9, net=f"{net_prefix}{k + 1}"))
        pads.append(dict(num=8, x=0, y=0, w=1.5, h=1.5, shape="circle", drill=0.9, net=f"{net_prefix}8"))
    for k in range(4):
        a = math.radians(45 + 90 * k)
        pads.append(dict(num=f"S{k + 1}", x=7.0 * math.cos(a), y=7.0 * math.sin(a), w=2.4, h=2.4,
                         shape="circle", drill=1.5, net="CHASSIS"))
    return pads


def build_pwr():
    B = Board(6, P.PWR_PCB_T)
    W, H = P.PWR_PCB_W, P.PWR_PCB_H
    B.outline_rounded(W, H, 2.0)
    full = B.rounded_pts(W, H, 2.0, inset=0.4)
    B.zone("In1.Cu", "GND", full)
    B.zone("In4.Cu", "GND", full)
    B.zone("In2.Cu", "VIN_PROT", rect_pts(-36, 0, 70, 32), priority=1)
    B.zone("In3.Cu", "+28V_PA", rect_pts(20, 0, 50, 32), priority=1)
    for cx in (-42, 42):   # chassis ring bonding the M12 shells (B side)
        ring = [(cx + 9.5 * math.cos(math.radians(a)), 9.5 * math.sin(math.radians(a))) for a in range(0, 360, 15)]
        B.zone("B.Cu", "CHASSIS", ring, priority=2)
    B.track("B.Cu", [(-34.5, 0), (34.5, 0)], 1.0, "CHASSIS")

    B.custom_fp("J1", "M12 A-coded 8p PCB rear-mount: 12-36 VDC, RS-485, 1PPS, discretes",
                -42, 0, m12_pads(8, "PWRIO_"), courtyard=(17, 17), bottom=True)
    B.custom_fp("J2", "M12 X-coded 8p PCB rear-mount: 1000BASE-T / 2.5GBASE-T",
                42, 0, m12_pads(8, "MDI_"), courtyard=(17, 17), bottom=True)
    # F side keeps clear of the M12 THT pin circles (r 8.5 mm at x=+-42).
    parts = [
        ("Diode_SMD", "D_SMC", "D1", "SMCJ36CA TVS (MIL-STD-1275 / ISO 7637)", -60, 0, 90),
        ("Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm", "U6", "THVD1450 RS-485 (isolated option)", -58, -11, 0),
        ("Package_DFN_QFN", "DFN-10-1EP_3x3mm_P0.5mm_EP1.65x2.38mm", "U1",
         "LT4363 surge stopper + reverse-V protection", -29, 0, 0),
        ("Inductor_SMD", "L_12x12mm_H6mm", "L1", "CM choke + DM filter (EMI, MIL-STD-461 CE102)", -20, -7, 0),
        ("Capacitor_SMD", "CP_Elec_8x10", "C1", "100 uF 50 V polymer hold-up", -7.5, -9, 0),
        ("Package_DFN_QFN", "QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm", "U2", "LT8640S 12 V/6 A (DSP rail)", -8, 1.5, 0),
        ("Inductor_SMD", "L_Coilcraft_XAL6030-XXX", "L2", "XAL6030 4.7 uH", 2.2, -9, 0),
        ("Package_DFN_QFN", "QFN-28-1EP_4x5mm_P0.5mm_EP2.65x3.65mm", "U3",
         "LT8390 buck-boost 28 V / 1.2 A GaN drain", 3, 1.5, 0),
        ("Inductor_SMD", "L_12x12mm_H6mm", "L3", "10 uH 6 A shielded", 14, -7, 0),
        ("Package_TO_SOT_SMD", "TSOT-23-6", "U4", "LT3462 -5 V GaN gate bias (sequenced)", 14, 3, 0),
        ("Package_DFN_QFN", "QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm", "U5", "LT8640S 5 V/6 A (RF rail)", 24, 1.5, 0),
        ("Capacitor_SMD", "CP_Elec_8x10", "C2", "100 uF 50 V polymer", 26.5, -9, 0),
        ("Connector_Molex", "Molex_Micro-Fit_3.0_43650-0400_1x04_P3.00mm_Horizontal", "J4",
         "Micro-Fit 4p to DSP: +12V", -24, 11, 0),
        ("Connector_Molex", "Molex_Micro-Fit_3.0_43650-0400_1x04_P3.00mm_Horizontal", "J3",
         "Micro-Fit 4p to ANT: +28V_PA, +5V", -2, 11, 0),
        ("Connector_FFC-FPC", "Hirose_FH12-30S-0.5SH_1x30-1MP_P0.50mm_Horizontal", "J5",
         "FFC to DSP: MDI, RS-485, 1PPS", 22, 11, 0),
    ]
    for lib, name, ref, val, x, y, rot in parts:
        B.fp(lib, name, ref, val, x, y, rot=rot)
    B.custom_fp("T1", "1000BASE-T magnetics (HX1188NL class)", 60, -2,
                [dict(num=k + 1, x=-4.5 + (k % 6) * 1.8, y=-3.6 if k < 6 else 3.6, w=0.8, h=1.6)
                 for k in range(12)], courtyard=(12, 9))
    for k, (x, y) in enumerate([(-68, 10.5), (68, 10.5), (-68, -10.5), (68, -10.5)]):
        B.fp("MountingHole", "MountingHole_3.2mm_M3_Pad_Via", f"H{k + 1}", "M3", x, y, pad_net="GND")
    B.text("F.SilkS", "HG-1 PWR/IO rev A  12-36 VDC  6L 2oz", -40, -13.6, 1.1)
    return B


KICAD_CLI = os.environ.get("KICAD_CLI", r"C:/Program Files/KiCad/10.0/bin/kicad-cli.exe")


def refill_and_drc(path):
    import subprocess
    rpt = path.replace(".kicad_pcb", "_drc.json")
    subprocess.run([KICAD_CLI, "pcb", "drc", "--refill-zones", "--save-board", "--format", "json",
                    "--severity-error", "-o", rpt, path], check=False, capture_output=True)
    with open(rpt) as fh:
        d = json.load(fh)
    kinds = {}
    for v in d.get("violations", []):
        kinds[v["type"]] = kinds.get(v["type"], 0) + 1
    return len(d.get("violations", [])), len(d.get("unconnected_items", [])), kinds


if __name__ == "__main__":
    for name, fn in (("HG1-ANT", build_ant), ("HG1-DSP", build_dsp), ("HG1-PWR", build_pwr)):
        b = fn()
        path = os.path.join(OUT, f"{name}.kicad_pcb")
        b.save(path)
        nfp = len(list(b.b.GetFootprints()))
        ntr = len(list(b.b.GetTracks()))
        print(f"{name}: {nfp} footprints, {ntr} tracks/vias, {len(b.nets)} nets -> {path}", flush=True)
        nv, nu, kinds = refill_and_drc(path)
        print(f"   zones refilled; DRC errors {nv} {kinds}; unconnected {nu}",
              flush=True)

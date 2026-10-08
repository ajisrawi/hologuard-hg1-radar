"""HoloGuard HG-1 -- single source of truth for design parameters.

Every analysis, PCB, CAD and render script imports this file so that the
antenna layout, board outline and enclosure always agree.
Units: mm, GHz, W, dB unless noted.
"""

# --------------------------------------------------------------------------
# Envelope (identical to Echodyne EchoGuard: 16.3 x 20.3 x 5.7 cm)
# Portrait orientation: X = width (azimuth), Y = height (elevation), Z = depth
# --------------------------------------------------------------------------
ENV_W = 163.0
ENV_H = 203.0
ENV_D = 57.0
ENV_CORNER_R = 10.0          # plan-view corner radius

WALL = 1.8                   # housing side wall (A356-T6 / AlSi10Mg cast)
RADOME_T = 1.0               # radome skin (PC/ABS + glass-free, er~2.8, tan d 0.006)
RADOME_STANDOFF = 3.0        # radome dome height above housing lip
FIN_H = 11.0                 # rear fin height
FIN_T = 1.2                  # fin thickness
FIN_PITCH = 7.5              # fin pitch
BACKWALL = 2.0               # rear wall under fins

# --------------------------------------------------------------------------
# RF
# --------------------------------------------------------------------------
F_LO_GHZ = 15.5
F_HI_GHZ = 16.5
F0_GHZ = 16.0
C_MM_PER_NS = 299.792458
LAMBDA0_MM = C_MM_PER_NS / F0_GHZ           # 18.74 mm
D = 9.0                                      # element pitch (0.495 lambda @ 16.5 GHz)

# Receive sub-aperture: 12 (az) x 4 (el), filled lambda/2 grid
RX_NX = 12
RX_NY = 4
# Transmit: 2 (az) x 3 (el). Az offset = RX_NX*D, el offset = RX_NY*D
TX_X = (-54.0, 54.0)
TX_Y = (76.5, 40.5, 4.5)
RX_X0 = -49.5                                # first RX column centre
RX_Y0 = -49.5                                # top RX row centre (rows go down)
FENCE_Y = -22.5                              # TX/RX isolation fence centre line

# Waveform (surveillance mode)
BW_MHZ = 250.0               # 0.60 m range resolution
T_CHIRP_US = 75.0            # active ramp
T_PRI_US = 80.0              # incl. 5 us reset/settle -> PRF 12.5 kHz
CPI_CHIRPS = 625             # 50 ms CPI
N_CPI_WINDOW = 8             # 400 ms sliding integration window (staring)
IF_MAX_MHZ = 66.7            # max beat = slope * tau(3 km)
INSTR_RANGE_M = 3000.0

# Power
PT_TOTAL_W = 6.0             # 6 x 1.0 W GaN (30 dBm per TX)
NF_DB = 2.8                  # RFIC 2.5 dB + 0.3 dB feed/ESD
LOSS_DB = 4.5                # radome 0.4, taper 1.3, straddle 1.5, atm 0.3, misc 1.0
G_ELEM_DBI = 5.0             # embedded element realised gain (broadside)

# --------------------------------------------------------------------------
# Boards
# --------------------------------------------------------------------------
# Physical stack-ups: the single source for the fab notes, the KiCad board stack-up and the
# board thicknesses below. "cu" lists finished copper per layer, top (F.Cu) to bottom (B.Cu);
# "gaps" lists the dielectric between consecutive copper layers as (type, [(material, t_mm, er,
# tan_d), ...]) where a gap with several entries is a core plus bond-ply build.
_RO4003C, _RO4450F, _RO4350B = ("RO4003C", 3.55, 0.0027), ("RO4450F", 3.52, 0.004), ("RO4350B", 3.66, 0.0037)
_370HR, _MEG6 = ("370HR", 4.04, 0.021), ("Megtron-6 R-5775", 3.40, 0.004)


def _d(mat, t):
    return (mat[0], t, mat[1], mat[2])


MASK_T = 0.01
STACKS = {
    # 10L hybrid antenna/RF board. L1-L2 1.016 = EM-optimised parasitic spacer (docs/06);
    # L2-L3, L3-L4, L4-L5 as in the EM model; 370HR power/LO layers; RO4350B under the L10 GCPW.
    "ANT": {"finish": "ENEPIG",
            "cu": [0.035, 0.018, 0.018, 0.018, 0.018, 0.035, 0.035, 0.018, 0.018, 0.035],
            "gaps": [("core", [_d(_RO4003C, 0.813), _d(_RO4450F, 0.203)]),     # L1-L2 parasitic spacer
                     ("core", [_d(_RO4003C, 0.508)]),                          # L2-L3 driven patch
                     ("core", [_d(_RO4003C, 0.203)]),                          # L3-L4 stripline (top)
                     ("prepreg", [_d(_RO4450F, 0.102), _d(_RO4003C, 0.101)]),  # L4-L5 stripline (bottom)
                     ("prepreg", [_d(_370HR, 0.100)]),
                     ("core", [_d(_370HR, 0.100)]),
                     ("prepreg", [_d(_370HR, 0.075)]),                         # L7-L8 LO bus stripline
                     ("core", [_d(_370HR, 0.075)]),
                     ("core", [_d(_RO4350B, 0.168)])]},                        # L9-L10 GCPW
    # 12L HDI processing board (1+10+1 build-up, Megtron-6 for the JESD/DDR layers).
    "DSP": {"finish": "ENIG",
            "cu": [0.035] + [0.018] * 10 + [0.035],
            "gaps": [("prepreg", [_d(_MEG6, 0.075)])]
            + [("core", [_d(_MEG6, 0.130)]) if k % 2 == 0 else ("prepreg", [_d(_MEG6, 0.1325)]) for k in range(9)]
            + [("prepreg", [_d(_MEG6, 0.075)])]},
    # 6L 2 oz power / IO board.
    "PWR": {"finish": "ENIG",
            "cu": [0.070] * 6,
            "gaps": [("prepreg", [_d(_370HR, 0.20)]), ("core", [_d(_370HR, 0.30)]),
                     ("prepreg", [_d(_370HR, 0.16)]), ("core", [_d(_370HR, 0.30)]),
                     ("prepreg", [_d(_370HR, 0.20)])]},
}


def stack_thickness(name):
    s = STACKS[name]
    return round(sum(s["cu"]) + sum(t for _, subs in s["gaps"] for _, t, _, _ in subs) + 2 * MASK_T, 3)


ANT_PCB_W = 150.0
ANT_PCB_H = 190.0
ANT_PCB_T = stack_thickness("ANT")      # 2.716 mm
DIG_PCB_W = 150.0
DIG_PCB_H = 150.0
DIG_PCB_T = stack_thickness("DSP")      # 1.600 mm
PWR_PCB_W = 146.0
PWR_PCB_H = 30.0
PWR_PCB_T = stack_thickness("PWR")      # 1.600 mm


def rx_positions():
    """RX element centres (x, y) in mm, row-major, top row first."""
    return [(RX_X0 + i * D, RX_Y0 - j * D) for j in range(RX_NY) for i in range(RX_NX)]


def tx_positions():
    return [(x, y) for y in TX_Y for x in TX_X]


def virtual_positions():
    return [(tx + rx, ty + ry) for (tx, ty) in tx_positions() for (rx, ry) in rx_positions()]

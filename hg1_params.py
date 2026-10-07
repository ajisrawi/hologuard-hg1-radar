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
ANT_PCB_W = 150.0
ANT_PCB_H = 190.0
ANT_PCB_T = 2.1
DIG_PCB_W = 150.0
DIG_PCB_H = 150.0
DIG_PCB_T = 1.6
PWR_PCB_W = 146.0
PWR_PCB_H = 30.0
PWR_PCB_T = 1.6


def rx_positions():
    """RX element centres (x, y) in mm, row-major, top row first."""
    return [(RX_X0 + i * D, RX_Y0 - j * D) for j in range(RX_NY) for i in range(RX_NX)]


def tx_positions():
    return [(x, y) for y in TX_Y for x in TX_X]


def virtual_positions():
    return [(tx + rx, ty + ry) for (tx, ty) in tx_positions() for (rx, ry) in rx_positions()]

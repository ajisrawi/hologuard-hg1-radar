"""HG-1 system block diagram -> analysis/figures/block_diagram.png"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

HERE = os.path.dirname(os.path.abspath(__file__))
fig, ax = plt.subplots(figsize=(15, 8.6))
ax.set_xlim(0, 150)
ax.set_ylim(0, 86)
ax.axis("off")

C_RF, C_TX, C_MIX, C_DIG, C_PWR, C_MECH = "#fde6d8", "#f8d0c0", "#dbe8fb", "#d9f0e3", "#f3ead0", "#ececec"


def blk(x, y, w, h, title, body="", fc="#fff", ec="#333", fs=8.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.25,rounding_size=1.2", fc=fc, ec=ec, lw=1))
    ax.text(x + w / 2, y + h - 1.6, title, ha="center", va="top", fontsize=fs, weight="bold")
    if body:
        ax.text(x + w / 2, y + h - 4.6, body, ha="center", va="top", fontsize=6.9, linespacing=1.25)


def arrow(x0, y0, x1, y1, txt="", c="#333", ls="-"):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0), arrowprops=dict(arrowstyle="-|>", color=c, lw=1.1, ls=ls))
    if txt:
        ax.text((x0 + x1) / 2, (y0 + y1) / 2 + 0.9, txt, ha="center", fontsize=6.5, color=c)


ax.text(75, 84, "HoloGuard HG-1  -  4D holographic (staring) MIMO radar, Ku-band GaN, 163 x 203 x 57 mm",
        ha="center", fontsize=12, weight="bold")
# frames
ax.add_patch(FancyBboxPatch((1, 30), 74, 50, boxstyle="round,pad=0.3", fc="none", ec="#c87f33", ls="--"))
ax.text(3, 78.3, "HG1-ANT  antenna / RF board  (10L hybrid RO4003C + 370HR, 150 x 190 mm)", fontsize=8,
        color="#a35b17", weight="bold")
ax.add_patch(FancyBboxPatch((78, 30), 71, 50, boxstyle="round,pad=0.3", fc="none", ec="#1a9e77", ls="--"))
ax.text(80, 78.3, "HG1-DSP  processing board (12L HDI, 150 x 150 mm)", fontsize=8, color="#127a5b", weight="bold")
ax.add_patch(FancyBboxPatch((1, 2), 148, 24, boxstyle="round,pad=0.3", fc="none", ec="#8a7d55", ls="--"))
ax.text(3, 24.3, "HG1-PWR  power / IO board (6L 2 oz, 146 x 30 mm)  +  enclosure", fontsize=8, color="#6d6240",
        weight="bold")

# antenna
blk(3, 58, 18, 18, "TX aperture", "6 stacked patches\nH-pol, 2 x 3 grid\naz 108 mm / el 36 mm\nGaN spotlight +7.8 dB", C_RF)
blk(3, 34, 18, 21, "RX aperture", "48 stacked patches\n12 x 4, 9.0 mm pitch\naperture-coupled\n=> 24 x 12 virtual\n(288 ch, 216 x 108 mm)",
    C_RF)
ax.text(12, 56.2, "choke fence  >= 60 dB isolation", ha="center", fontsize=6.3, color="#555")
blk(24, 60, 16, 16, "GaN PA x6", "QGaN15, 1 W each\n30 % PAE, 28 V\nIdq trim by MCU", C_TX)
blk(43, 60, 14, 16, "ADAR1000 x2", "TX phase / gain\nDDMA codes\nspotlight weights", C_TX)
blk(60, 60, 13, 16, "Chirp synth", "2 x ADF4159\n2 x HMC733\n100 MHz OCXO\nTX + LO ramps", C_MIX)
blk(24, 34, 16, 21, "HRX-8 RFIC x6", "48 RX channels\nLNA NF 2.5 dB\nIQ dechirp mixer\nIF VGA + AAF\n75 mW / ch", C_MIX)
blk(43, 34, 14, 21, "AD9083 x6", "96 ADC ch\n125 MHz CTSD\nDDC / decim.\nJESD204B\n24 lanes", C_MIX)
blk(60, 34, 13, 21, "HMC7044", "device clock\n+ SYSREF\nmulti-chip\nphase sync", C_MIX)
arrow(24, 68, 21, 68)
arrow(43, 68, 40, 68, "drive")
arrow(60, 70, 57, 70, "TX chirp")
arrow(66, 60, 66, 56, "", "#555")
ax.text(67, 57.3, "LO chirp (L8 bus)", fontsize=6.3)
arrow(21, 45, 24, 45)
arrow(40, 45, 43, 45, "IQ IF")
arrow(60, 42, 57, 42, "clk")

# digital
blk(80, 40, 36, 36, "AMD Versal AI Edge  XCVE2302", "PL: JESD rx, range FFT, DMA\nAIE-ML: Doppler FFT, DDMA demux,\n"
    "holographic 2-D beamforming (0.6 TMAC/s)\nAPU (A72): CFAR, plots, EKF tracker,\nmicro-Doppler classifier, spotlight\n"
    "scheduler, API (UDP/PTP)\nRPU (R5F): radar timing, safety", C_DIG, fs=9)
arrow(57, 36, 80, 42, "", "#1a6b4f")
ax.text(76.5, 33.2, "JESD204B 24 x 6.7 Gb/s\n(Samtec LSHM mezzanine)", fontsize=6.3, color="#1a6b4f", ha="center")
blk(119, 64, 28, 12, "Memory", "2 x LPDDR4 32 Gb (cube ping-pong)\neMMC 64 GB, QSPI boot", C_DIG)
blk(119, 50, 28, 12, "Sensors / ID", "GNSS L1/L5 timing (1PPS)\nIMU + magnetometer\nRemote-ID BT5-LR + Wi-Fi", C_DIG)
blk(119, 34, 28, 14, "STM32G474 housekeeping", "GaN gate-before-drain sequencing\nIdq trim, thermal back-off\nCBIT, emission interlock",
    C_DIG)
arrow(116, 70, 119, 70)
arrow(116, 56, 119, 56)
arrow(119, 41, 116, 44, "UART")
arrow(119, 36, 40, 61, "", "#a35b17", "--")
ax.text(100, 31.2, "PA gate bias / TX mute (SPI)", fontsize=6.3, color="#a35b17", ha="center")
arrow(80, 72, 73, 72, "", "#555")
ax.text(76.5, 77.0, "SPI ramp /\nbeam-state", fontsize=6.0, color="#555", ha="center")

# power
blk(4, 5, 26, 16, "M12 A-coded", "12-36 VDC in\nRS-485, 1PPS, discretes\nMIL-STD-1275 / ISO 7637", C_PWR)
blk(34, 5, 30, 16, "Protection + conversion", "LT4363 surge / reverse\nCM/DM EMI filter\nLT8390 28 V GaN drain\nLT8640S 12 V & 5 V, LT3462 -5 V",
    C_PWR)
blk(68, 5, 26, 16, "M12 X-coded", "1000BASE-T / 2.5G\nPTP IEEE-1588\nUDP track / plot stream", C_PWR)
blk(98, 5, 49, 16, "Enclosure", "AlSi10Mg die-cast, vertical fins, IP67, Gore vent\nPC/ABS radome 1.0 mm, M3 x 12\n"
    "1.01 kg  -  46.8 W  -  -40 .. +75 degC (TX back-off > +60 degC PA)", C_MECH)
arrow(30, 13, 34, 13)
arrow(49, 21, 49, 34, "+28 V / +5 V", "#6d6240")
arrow(64, 18, 98, 42, "+12 V", "#6d6240")
arrow(94, 13, 98, 40, "", "#1a6b4f")
fig.savefig(os.path.join(HERE, "figures", "block_diagram.png"), dpi=140, bbox_inches="tight")
print("ok")

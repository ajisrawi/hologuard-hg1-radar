"""HoloGuard HG-1 project symbol library (HG1.kicad_sym).

Symbols for parts without an official KiCad symbol. Pin numbers of every pin
that is routed on the PCB are taken from the layout (board/generate_boards.py),
so "Update PCB from Schematic" keeps the routed nets. Pins marked PROVISIONAL
in the description sit on proxy footprints and must be re-checked against the
vendor pin-out before fabrication.

Pin tuple: (number | [numbers...], name, electrical_type, side)
  side: L / R / T / B. A list of numbers makes stacked pins (same name/place).
"""

PROXY = " PROVISIONAL pin-out on proxy footprint - verify against vendor data sheet."


def rng(prefix, n, start=0):
    return [f"{prefix}{i}" for i in range(start, start + n)]


SYMBOLS = {}


def sym(name, ref, footprint, desc, pins, value=None):
    SYMBOLS[name] = dict(ref=ref, footprint=footprint, desc=desc, pins=pins, value=value or name)


QFN64 = "Package_DFN_QFN:QFN-64-1EP_9x9mm_P0.5mm_EP3.8x3.8mm"
QFN48 = "Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm_ThermalVias"
QFN40 = "Package_DFN_QFN:QFN-40-1EP_6x6mm_P0.5mm_EP4.6x4.6mm_ThermalVias"
QFN24 = "Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm"
QFN24TV = "Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.65x2.65mm_ThermalVias"
QFN16 = "Package_DFN_QFN:QFN-16-1EP_3x3mm_P0.5mm_EP1.7x1.7mm"
DFN10 = "Package_DFN_QFN:DFN-10-1EP_3x3mm_P0.5mm_EP1.65x2.38mm"

# ---------------------------------------------------------------- ANT board
# HRX-8: pads of RF inputs / LO / IF are the routed pads (identical on U10..U15)
_rfin = {1: 47, 2: 2, 3: 43, 4: 6, 5: 38, 6: 11, 7: 34, 8: 15}
sym("HRX-8", "U", QFN64, "8-ch Ku-band SiGe receiver RFIC: LNA + IQ dechirp mixer + IF VGA/AAF (custom ASIC)."
    " RF/LO/IF pads = routed PCB pads.",
    [(_rfin[c], f"RFIN{c}", "passive", "L") for c in range(1, 9)]
    + [(24, "LO_IN", "input", "L")]
    + [(49 + 2 * (c - 1), f"IF{c}I", "output", "R") for c in range(1, 9)]
    + [(50 + 2 * (c - 1), f"IF{c}Q", "output", "R") for c in range(1, 9)]
    + [(17, "SCLK", "input", "L"), (18, "SDIO", "bidirectional", "L"), (19, "CSB", "input", "L"),
       (20, "RESETB", "input", "L"), (21, "PD", "input", "L"), (27, "VCM_IN", "input", "R"),
       (22, "TEMP", "output", "R")]
    + [([4, 45], "VCC_LNA", "power_in", "T"), ([8, 41], "VCC_MIX", "power_in", "T"),
       ([9, 40, 13, 36], "VCC_IF", "power_in", "T"), (26, "VCC_LO", "power_in", "T")]
    + [([65, 1, 3, 5, 7, 10, 12, 14, 16, 23, 25, 30, 31, 32, 33, 35, 37, 39, 42, 44, 46, 48],
        "GND", "power_in", "B")])

# AD9083 (BGA-121 proxy): VIN/SERDOUT balls = routed balls
_vin = ["H11", "J11", "K11", "L11", "L10", "L9", "L8", "L7", "L6", "L5", "L4", "L3", "L2", "K1", "J1", "H1"]
sym("AD9083", "U", "Package_BGA:BGA-121_9.0x9.0mm_Layout11x11_P0.8mm_Ball0.4mm_Pad0.35mm_NSMD",
    "16-ch 125 MHz CTSD ADC, JESD204B (Analog Devices). Inputs drawn single-ended (I/Q of 8 RX)."
    " VIN/SERDOUT = routed balls." + PROXY,
    [(_vin[i], f"VIN{i}", "input", "L") for i in range(16)]
    + [("A2", "CLK+", "input", "L"), ("A3", "CLK-", "input", "L"), ("A10", "SYSREF+", "input", "L"),
       ("A11", "SYSREF-", "input", "L"), ("C1", "SCLK", "input", "L"), ("C2", "SDIO", "bidirectional", "L"),
       ("C3", "CSB", "input", "L"), ("C4", "PWDN", "input", "L"), ("B1", "SYNCINB", "input", "L")]
    + [("A8", "SERDOUT0", "output", "R"), ("A7", "SERDOUT1", "output", "R"), ("A6", "SERDOUT2", "output", "R"),
       ("A5", "SERDOUT3", "output", "R"), ("D1", "VCM_OUT", "output", "R")]
    + [(["E5", "E6", "E7"], "VDD1", "power_in", "T"), (["F5", "F6", "F7"], "VDD1P8", "power_in", "T")]
    + [(["E1", "E2", "F2", "G5", "G6", "G7", "H5", "H6"], "GND", "power_in", "B")])

sym("GaN_PA_Ku", "U", QFN24TV, "Ku-band GaN-on-SiC MMIC PA, 1 W, 28 V (Qorvo QGaN15 class). RFIN/RFOUT = routed pads."
    + PROXY,
    [(15, "RFIN", "input", "L"), (18, "VG", "input", "L"), (3, "RFOUT", "output", "R"),
     ([21, 22], "VD", "power_in", "T"), ([25, 2, 4, 14, 16], "GND", "power_in", "B")])

sym("ADAR1000", "U", QFN48, "8-16 GHz 4-ch beamformer, TX mode: DDMA phase codes, spotlight weights, PA gate-bias"
    " DACs (Analog Devices; real part is LGA-88). RF_COM/RF1-3 = routed pads." + PROXY,
    [(31, "RF_COM", "input", "L"), (24, "SCLK", "input", "L"), (25, "SDIO", "bidirectional", "L"),
     (26, "SDO", "tri_state", "L"), (27, "CSB", "input", "L"), (28, "ADDR0", "input", "L"),
     (29, "ADDR1", "input", "L"), (33, "TR", "input", "L"), (34, "TX_LOAD", "input", "L"),
     (37, "PA_ON", "input", "L")]
    + [(46, "RF1", "output", "R"), (14, "RF2", "output", "R"), (6, "RF3", "output", "R"),
       (38, "RF4", "output", "R"), (40, "PA_BIAS1", "output", "R"), (20, "PA_BIAS2", "output", "R"),
       (2, "PA_BIAS3", "output", "R"), (36, "PA_BIAS4", "output", "R")]
    + [([10, 11, 21], "VDD", "power_in", "T"), (1, "VSS_NEG", "power_in", "T"),
       ([49, 45, 47, 13, 15, 5, 7, 30, 32], "GND", "power_in", "B")])

sym("ADF4159", "U", QFN24, "13 GHz fractional-N FMCW ramp PLL (Analog Devices). CP_OUT/REF_IN = routed pads." + PROXY,
    [(21, "REF_IN", "input", "L"), (9, "RFIN", "input", "L"), (13, "CLK", "input", "L"),
     (14, "DATA", "input", "L"), (15, "LE", "input", "L"), (16, "CE", "input", "L"),
     (12, "TXDATA", "input", "L"), (3, "CP_OUT", "output", "R"), (18, "MUXOUT", "output", "R"),
     (20, "RSET", "passive", "R"), ([5, 6, 7, 8], "VDD", "power_in", "T"), ([25, 17], "GND", "power_in", "B")])

sym("HMC733", "U", QFN24, "10-20 GHz wideband VCO, Fo and Fo/2 outputs (Analog Devices). VTUNE/RFOUT = routed pads."
    + PROXY,
    [(15, "VTUNE", "input", "L"), (9, "RFOUT", "output", "R"), (21, "RFOUT_DIV2", "output", "R"),
     ([3, 4], "VCC", "power_in", "T"), ([25, 17], "GND", "power_in", "B")])

sym("HMC903", "U", QFN16, "6-17 GHz amplifier, +14 dBm P1dB (Analog Devices). RFIN/RFOUT = routed pads." + PROXY,
    [(14, "RFIN", "input", "L"), (6, "RFOUT", "output", "R"), (3, "VDD", "power_in", "T"),
     ([17, 13, 15, 5, 7], "GND", "power_in", "B")])

sym("HMC7044", "U", "Package_DFN_QFN:QFN-64-1EP_9x9mm_P0.5mm_EP3.8x3.8mm",
    "JESD204B clock generator / jitter cleaner, 14 outputs (Analog Devices, real part LFCSP-68)." + PROXY,
    [(1, "CLKIN0", "input", "L"), (3, "SCLK", "input", "L"), (4, "SLEN", "input", "L"),
     (5, "SDATA", "bidirectional", "L"), (6, "RESET", "input", "L"), (7, "SYNC", "input", "L")]
    + [(30 + 2 * k, f"DCLK{k}", "output", "R") for k in range(7)]
    + [(31 + 2 * k, f"SYSREF{k}", "output", "R") for k in range(7)]
    + [([10, 11, 12, 13], "VCC", "power_in", "T"), ([65, 17, 25], "GND", "power_in", "B")])

sym("OCXO_4P", "Y", "Oscillator:Oscillator_SMD_Diodes_FN-4Pin_7.0x5.0mm",
    "100 MHz OCXO/TCXO, CMOS out, -165 dBc/Hz floor.",
    [(1, "EN", "input", "L"), (3, "OUT", "output", "R"), (4, "VCC", "power_in", "T"), (2, "GND", "power_in", "B")])

sym("ADP7159", "U", DFN10, "Ultra-low-noise 2 A LDO (Analog Devices)." + PROXY,
    [([1, 2], "VIN", "power_in", "L"), (3, "EN", "input", "L"), (8, "REF", "passive", "R"),
     ([9, 10], "VOUT", "power_out", "R"), ([5, 11], "GND", "power_in", "B")])

sym("TPS62913", "U", DFN10, "17 V 3 A low-noise buck (Texas Instruments)." + PROXY,
    [([1, 2], "VIN", "power_in", "L"), (3, "EN", "input", "L"), (4, "FB", "input", "L"),
     ([9, 10], "SW", "output", "R"), (8, "PG", "open_collector", "R"), ([5, 11], "GND", "power_in", "B")])

sym("ADS7138", "U", QFN16, "8-ch 12-bit I2C ADC with GPIO (Texas Instruments) - PA pedestal NTCs." + PROXY,
    [(1, "AIN0", "input", "L"), (2, "AIN1", "input", "L"), (3, "AIN2", "input", "L"), (4, "AIN3", "input", "L"),
     (5, "AIN4", "input", "L"), (6, "AIN5", "input", "L"), (9, "SCL", "input", "R"),
     (10, "SDA", "bidirectional", "R"), (11, "ADDR", "input", "R"), (14, "AVDD", "power_in", "T"),
     ([17, 15], "GND", "power_in", "B")])

sym("INA186", "U", "Package_TO_SOT_SMD:SOT-363_SC-70-6",
    "Current-sense amplifier 40 V, gain 100 V/V (A3) (Texas Instruments).",
    [(4, "IN+", "input", "L"), (5, "IN-", "input", "L"), (6, "OUT", "output", "R"), (3, "REF", "input", "L"),
     (1, "VS", "power_in", "T"), (2, "GND", "power_in", "B")])

sym("PMOS_SO8", "Q", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    "P-channel MOSFET -60 V 15 mOhm (drain switch, SQJ457EP class).",
    [([1, 2, 3], "S", "passive", "L"), (4, "G", "input", "L"), ([5, 6, 7, 8], "D", "passive", "R")])

sym("GNSS_PATCH", "AE", "HG1:GNSS_PATCH_18x18", "GNSS L1/L5 ceramic patch 18 x 18 (Taoglas CGGP.18 class).",
    [(1, "FEED", "passive", "R"), ([2, 3, 4, 5], "GND", "passive", "B")])

sym("Conn_02x50", "J", "Connector_Samtec:Samtec_LSHM-150-xx.x-x-DV-N_2x50_P0.50mm_Vertical",
    "Samtec LSHM-150 Razor Beam 2x50 0.5 mm, 10 mm stack.",
    [(2 * i + 1, f"{2 * i + 1}", "passive", "L") for i in range(50)]
    + [(2 * i + 2, f"{2 * i + 2}", "passive", "R") for i in range(50)])

sym("Conn_02x20_SM", "J", "Connector_Samtec:Samtec_LSHM-120-xx.x-x-DV-N_2x20_P0.50mm_Vertical",
    "Samtec LSHM-120 Razor Beam 2x20 0.5 mm.",
    [(2 * i + 1, f"{2 * i + 1}", "passive", "L") for i in range(20)]
    + [(2 * i + 2, f"{2 * i + 2}", "passive", "R") for i in range(20)])

# ---------------------------------------------------------------- DSP board
_ddr = (rng("CA", 6) + ["CS", "CKE", "CK_T", "CK_C", "RESET_N"] + rng("DQ", 32)
        + rng("DQS_T", 4) + rng("DQS_C", 4) + rng("DMI", 4))


def _versal_pins():
    pins = []
    n = [0]

    def add(name, t, side):
        n[0] += 1
        pins.append((f"P{n[0]}", name, t, side))

    for k in range(1, 7):
        for l in range(4):
            add(f"GTYP_RX_{k}_{l}", "input", "L")
    for nm in ("GTREFCLK", "SYSREF_IN"):
        add(nm, "input", "L")
    add("JESD_SYNC", "output", "L")
    for nm in ("SPI_SCLK", "SPI_MOSI"):
        add(nm, "output", "L")
    add("SPI_MISO", "input", "L")
    for nm in rng("CS_RFIC", 6) + rng("CS_ADC", 6) + ["CS_PLL_TX", "CS_PLL_LO", "CS_CLK", "CHIRP_TRIG", "TX_LOAD"]:
        add(nm, "output", "L")
    for nm in ("PLL_LD_TX", "PLL_LD_LO"):
        add(nm, "input", "L")
    for ch in "AB":
        for s in _ddr:
            t = "bidirectional" if s.startswith(("DQ", "DMI")) else "output"
            add(f"DDR{ch}_{s}", t, "R")
    for nm in ("EMMC_CLK",):
        add(nm, "output", "R")
    for nm in ["EMMC_CMD"] + rng("EMMC_D", 8):
        add(nm, "bidirectional", "R")
    add("EMMC_RST_N", "output", "R")
    add("QSPI_CLK", "output", "R")
    add("QSPI_CS_N", "output", "R")
    for nm in rng("QSPI_DQ", 4):
        add(nm, "bidirectional", "R")
    for nm in ["RGMII_TXC", "RGMII_TX_CTL"] + rng("RGMII_TXD", 4) + ["MDC", "PHY_RST_N"]:
        add(nm, "output", "L")
    for nm in ["RGMII_RXC", "RGMII_RX_CTL"] + rng("RGMII_RXD", 4) + ["PHY_INT_N"]:
        add(nm, "input", "L")
    add("MDIO", "bidirectional", "L")
    for nm, t in (("UART_MCU_TX", "output"), ("UART_MCU_RX", "input"), ("PMB_SCL", "input"),
                  ("PMB_SDA", "bidirectional"), ("GNSS_RX", "output"), ("GNSS_TX", "input"), ("PPS", "input"),
                  ("IMU_SCLK", "output"), ("IMU_MOSI", "output"), ("IMU_MISO", "input"), ("IMU_CS", "output"),
                  ("MAG_CS", "output"), ("IMU_INT", "input"), ("BLE_TX", "input"), ("BLE_RX", "output"),
                  ("WIFI_SCK", "output"), ("WIFI_MOSI", "output"), ("WIFI_MISO", "input"), ("WIFI_CS", "output"),
                  ("WIFI_IRQ", "input"), ("WIFI_EN", "output"), ("RS485_TX", "output"), ("RS485_RX", "input"),
                  ("RS485_DE", "output"), ("PPS_EXT", "input"), ("DISC_IN", "input"), ("RF_RESET_N", "output"),
                  ("TCK", "input"), ("TMS", "input"),
                  ("TDI", "input"), ("TDO", "output"), ("POR_B", "input"), ("PS_REFCLK", "input")):
        add(nm, t, "L")
    for nm in ("VCCINT", "VCC_AIE", "VCCAUX", "VCCO_DDR", "VCCO_1V8", "VCCO_3V3", "GTYP_AVCC", "GTYP_AVTT"):
        add(nm, "power_in", "T")
    add("GND", "power_in", "B")
    return pins


sym("XCVE2302", "U", "Package_BGA:Microchip_FCVG784_BGA-784_23x23mm_Layout28x28_P0.8mm",
    "AMD Versal AI Edge XCVE2302-1LSESFVA784: functional symbol (banks grouped). Pin numbers P1..Pn are"
    " PLACEHOLDERS - replace with the AMD SFVA784 package file (ball map) before layout.",
    _versal_pins())

sym("LPDDR4_x32", "U", "Package_BGA:BGA-200_10x14.5mm_Layout12x22_P0.8x0.65mm",
    "LPDDR4 32 Gb x32 (Micron MT53E1G32D2), single channel shown." + PROXY,
    [(f"P{i + 1}", s, "bidirectional" if s.startswith(("DQ", "DMI")) else "input", "L" if i < 11 else "R")
     for i, s in enumerate(_ddr)]
    + [(["P60", "P61"], "VDD1", "power_in", "T"), (["P62", "P63"], "VDD2", "power_in", "T"),
       (["P64", "P65"], "VDDQ", "power_in", "T"), (["P66", "P67", "P68"], "VSS", "power_in", "B")])

sym("eMMC_5.1", "U", "Package_BGA:LFBGA-153_11.5x13mm_Layout14x14_P0.5mm",
    "eMMC 5.1 64 GB pSLC, HS400." + PROXY,
    [("P1", "CLK", "input", "L"), ("P2", "CMD", "bidirectional", "L"), ("P11", "RST_N", "input", "L")]
    + [(f"P{3 + i}", f"DAT{i}", "bidirectional", "R") for i in range(8)]
    + [(["P12", "P13"], "VCC", "power_in", "T"), (["P14", "P15"], "VCCQ", "power_in", "T"),
       ("P16", "VDDI", "passive", "R"), (["P17", "P18"], "VSS", "power_in", "B")])

_rg = (["TX_CLK", "TX_CTRL"] + rng("TX_D", 4) + ["RX_CLK", "RX_CTRL"] + rng("RX_D", 4)
       + ["MDC", "MDIO", "RESET_N", "INT_N"])
sym("DP83867IR", "U", "Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm",
    "Gigabit Ethernet PHY, RGMII, IEEE 1588 SFD (Texas Instruments)." + PROXY,
    [(i + 1, s, ("input" if s.startswith("TX") or s in ("MDC", "RESET_N") else
                 "bidirectional" if s == "MDIO" else "output"), "L") for i, s in enumerate(_rg)]
    + [(17 + i, f"TD_{p}", "bidirectional", "R") for i, p in enumerate(
        ["A+", "A-", "B+", "B-", "C+", "C-", "D+", "D-"])]
    + [(26, "XI", "input", "R"), ([30, 31], "VDDA2P5", "power_in", "T"), ([32, 33], "VDD1P0", "power_in", "T"),
       ([34, 35], "VDDIO", "power_in", "T"), ([49, 36], "GND", "power_in", "B")])

sym("nRF7002", "U", QFN40, "Wi-Fi 6 2.4/5 GHz companion IC (Nordic) - Remote-ID beacon/NAN receiver." + PROXY,
    [(1, "SPI_SCK", "input", "L"), (2, "SPI_MOSI", "input", "L"), (3, "SPI_MISO", "output", "L"),
     (4, "SPI_CS", "input", "L"), (5, "HOST_IRQ", "output", "L"), (6, "BUCKEN", "input", "L"),
     (7, "IOVDD_EN", "input", "L"), (20, "RF", "bidirectional", "R"), ([10, 11], "VBAT", "power_in", "T"),
     (12, "VDDIO", "power_in", "T"), ([41, 21, 19], "GND", "power_in", "B")])

sym("TPS546D24A", "U", QFN40, "40 A PMBus synchronous buck, stackable (Texas Instruments)." + PROXY,
    [([1, 2, 3], "VIN", "power_in", "L"), (4, "EN", "input", "L"), (5, "PMB_CLK", "input", "L"),
     (6, "PMB_DATA", "bidirectional", "L"), (7, "VOSNS+", "input", "L"), (8, "VOSNS-", "input", "L"),
     ([20, 21, 22], "SW", "output", "R"), (23, "PGOOD", "open_collector", "R"), (24, "ADRSEL", "input", "R"),
     ([41, 30], "GND", "power_in", "B")])

sym("LT8640S", "U", QFN24, "42 V 6 A synchronous Silent Switcher 2 buck (Analog Devices)." + PROXY,
    [([1, 2], "VIN", "power_in", "L"), (3, "EN/UV", "input", "L"), (4, "FB", "input", "L"),
     (5, "RT", "passive", "L"), ([10, 11], "SW", "output", "R"), (12, "PG", "output", "R"),
     (13, "BST", "passive", "R"), (14, "INTVCC", "power_out", "R"), ([25, 17], "GND", "power_in", "B")])

sym("TPS3700", "U", "Package_TO_SOT_SMD:SOT-23-6", "Window comparator / voltage monitor (Texas Instruments).",
    [(3, "INA+", "input", "L"), (4, "INB-", "input", "L"), (1, "OUTA", "open_collector", "R"), (6, "OUTB", "open_collector", "R"),
     (5, "VDD", "power_in", "T"), (2, "GND", "power_in", "B")])

# ---------------------------------------------------------------- PWR board
sym("M12_8P", "J", "HG1:M12_8P_PCB", "M12 8-pin PCB rear-mount receptacle with 4 shell pads (A- or X-coded).",
    [(i, f"{i}", "passive", "L") for i in range(1, 9)]
    + [(["S1", "S2", "S3", "S4"], "SHELL", "passive", "B")])

sym("LT4363", "U", DFN10, "Surge stopper with reverse-input protection (Analog Devices, real part DFN-12/MSOP-12)."
    + PROXY,
    [(1, "VCC", "power_in", "L"), (2, "SNS", "input", "L"), (3, "UV", "input", "L"), (4, "OV", "input", "L"),
     (6, "GATE", "output", "R"), (7, "OUT", "input", "R"), (8, "FB", "input", "R"), (9, "TMR", "passive", "R"),
     (10, "FLT", "output", "R"), ([5, 11], "GND", "power_in", "B")])

sym("LT8390", "U", "Package_DFN_QFN:QFN-28-1EP_4x5mm_P0.5mm_EP2.65x3.65mm",
    "60 V 4-switch synchronous buck-boost controller (Analog Devices)." + PROXY,
    [([1, 2], "VIN", "power_in", "L"), (3, "EN/UVLO", "input", "L"), (4, "FB", "input", "L"),
     (5, "ISP", "input", "L"), (6, "ISN", "input", "L"), (20, "TG1", "output", "R"), (21, "BG1", "output", "R"),
     (22, "TG2", "output", "R"), (23, "BG2", "output", "R"), (24, "SW1", "passive", "R"), (25, "SW2", "passive", "R"),
     (26, "PG", "output", "R"), (27, "INTVCC", "power_out", "R"), ([29, 13], "GND", "power_in", "B")])

sym("LT3462", "U", "Package_TO_SOT_SMD:TSOT-23-6", "Inverting DC/DC, -5 V GaN gate bias (Analog Devices).",
    [(5, "VIN", "power_in", "L"), (4, "SHDN", "input", "L"), (3, "FB", "input", "L"), (1, "SW", "output", "R"),
     (6, "VOUT", "passive", "R"), (2, "GND", "power_in", "B")])

sym("THVD1450", "U", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", "3.3 V RS-485 transceiver, 50 Mbps (Texas Instruments).",
    [(1, "R", "output", "L"), (2, "~{RE}", "input", "L"), (3, "DE", "input", "L"), (4, "D", "input", "L"),
     (6, "A", "bidirectional", "R"), (7, "B", "bidirectional", "R"), (8, "VCC", "power_in", "T"),
     (5, "GND", "power_in", "B")])

sym("GBE_MAG", "T", "HG1:GBE_MAG_16P", "1000BASE-T magnetics, 4 pairs, PHY side / cable side (HX1188NL class).",
    [(i + 1, f"P{n}", "passive", "L") for i, n in enumerate(["A+", "A-", "B+", "B-", "C+", "C-", "D+", "D-"])]
    + [(i + 9, f"C{n}", "passive", "R") for i, n in enumerate(["A+", "A-", "B+", "B-", "C+", "C-", "D+", "D-"])])

sym("NMOS_SOT23", "Q", "Package_TO_SOT_SMD:SOT-23", "N-channel MOSFET 60 V (2N7002 class).",
    [(1, "G", "input", "L"), (3, "D", "passive", "R"), (2, "S", "passive", "B")])

sym("NMOS_PWR", "Q", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", "N-channel MOSFET 80 V 6 mOhm (surge-stopper pass FET).",
    [([5, 6, 7, 8], "D", "passive", "L"), (4, "G", "input", "B"), ([1, 2, 3], "S", "passive", "R")])


# ------------------------------------------------- map placeholder pins to pads
import os as _os
import re as _re

FPLIB = _os.environ.get("KICAD_FPLIB", r"C:/Program Files/KiCad/10.0/share/kicad/footprints")


def _footprint_pads(fp):
    lib, name = fp.split(":")
    txt = open(_os.path.join(FPLIB, lib + ".pretty", name + ".kicad_mod"), encoding="utf-8").read()
    seen, pads = set(), []
    for m in _re.finditer(r'\(pad "([^"]+)"', txt):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            pads.append(m.group(1))
    return pads


def _map_placeholders():
    """Symbols drawn with P1..Pn numbers get real pad names of their footprint."""
    for d in SYMBOLS.values():
        nums = [n for p in d["pins"] for n in (p[0] if isinstance(p[0], list) else [p[0]])]
        if not any(isinstance(n, str) and _re.fullmatch(r"P\d+", n) for n in nums) or not d["footprint"]                 or d["footprint"].startswith("HG1:"):
            continue
        free = [x for x in _footprint_pads(d["footprint"]) if x not in nums]
        it = iter(free)
        remap = {}
        for n in nums:
            if isinstance(n, str) and _re.fullmatch(r"P\d+", n):
                remap[n] = next(it)
        d["pins"] = [((([remap.get(n, n) for n in p[0]]) if isinstance(p[0], list) else remap.get(p[0], p[0])),)
                     + tuple(p[1:]) for p in d["pins"]]


_map_placeholders()


# ---------------------------------------------------------------- writer
def _fmt(v):
    return f"{v:.3f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def write_library(path):
    out = ['(kicad_symbol_lib', '\t(version 20251024)', '\t(generator "hg1_symbols")', '\t(generator_version "10.0")']
    for name, d in SYMBOLS.items():
        sides = {"L": [], "R": [], "T": [], "B": []}
        for p in d["pins"]:
            sides[p[3]].append(p)
        n_lr = max(len(sides["L"]), len(sides["R"]), 2)
        n_tb = max(len(sides["T"]), len(sides["B"]), 1)
        ll = max([len(p[1]) for p in sides["L"]] + [0])
        lr = max([len(p[1]) for p in sides["R"]] + [0])
        w = max(2.54 * (n_tb + 1), 1.35 * (ll + lr) + 7.62, 15.24)
        w = 2.54 * round(w / 2.54)
        h = 2.54 * (n_lr + 1)
        x0, x1, y0, y1 = -w / 2, w / 2, h / 2, -h / 2
        x0, x1 = 2.54 * round(x0 / 2.54), 2.54 * round(x1 / 2.54)
        y0, y1 = 2.54 * round(y0 / 2.54), 2.54 * round(y1 / 2.54)
        L = 2.54
        lines = [f'\t(symbol "{name}"', '\t\t(pin_names (offset 1.016))', '\t\t(exclude_from_sim no)',
                 '\t\t(in_bom yes)', '\t\t(on_board yes)']

        def prop(k, v, x, y, hide=False):
            v = v.replace('"', "'")
            return (f'\t\t(property "{k}" "{v}" (at {_fmt(x)} {_fmt(y)} 0) (effects (font (size 1.27 1.27))'
                    + (' (hide yes)' if hide else '') + '))')
        lines += [prop("Reference", d["ref"], x0, y0 + 1.27), prop("Value", d["value"], x0, y1 - 1.27),
                  prop("Footprint", d["footprint"], 0, y1 - 3.81, True), prop("Datasheet", "", 0, 0, True),
                  prop("Description", d["desc"], 0, 0, True)]
        lines += [f'\t\t(symbol "{name}_0_1"',
                  f'\t\t\t(rectangle (start {_fmt(x0)} {_fmt(y0)}) (end {_fmt(x1)} {_fmt(y1)})'
                  ' (stroke (width 0.254) (type default)) (fill (type background)))', '\t\t)',
                  f'\t\t(symbol "{name}_1_1"']

        def pin(nums, pname, t, x, y, rot):
            nums = nums if isinstance(nums, list) else [nums]
            res = []
            # stacked pins stay VISIBLE: hidden power-input pins become implicit
            # global nets named after the pin in KiCad and would merge rails
            for num in nums:
                res.append(f'\t\t\t(pin {t} line (at {_fmt(x)} {_fmt(y)} {rot}) (length {L})'
                           f' (name "{pname}" (effects (font (size 1.27 1.27))))'
                           f' (number "{num}" (effects (font (size 1.27 1.27)))))')
            return res
        for i, p in enumerate(sides["L"]):
            lines += pin(p[0], p[1], p[2], x0 - L, y0 - 2.54 * (i + 1), 0)
        for i, p in enumerate(sides["R"]):
            lines += pin(p[0], p[1], p[2], x1 + L, y0 - 2.54 * (i + 1), 180)
        for i, p in enumerate(sides["T"]):
            lines += pin(p[0], p[1], p[2], x0 + 2.54 * (i + 1), y0 + L, 270)
        for i, p in enumerate(sides["B"]):
            lines += pin(p[0], p[1], p[2], x0 + 2.54 * (i + 1), y1 - L, 90)
        lines += ['\t\t)', '\t)']
        out += lines
    out.append(')')
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    return list(SYMBOLS)

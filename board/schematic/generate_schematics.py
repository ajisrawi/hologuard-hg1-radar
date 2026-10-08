"""Generate the HoloGuard HG-1 KiCad schematics (one A0 sheet per board).

  board/kicad/HG1-ANT.kicad_sch   antenna / RF board
  board/kicad/HG1-DSP.kicad_sch   processing board
  board/kicad/HG1-PWR.kicad_sch   power / IO board
  board/kicad/HG1.kicad_sym       project symbol library (+ sym-lib-table)

Connectivity is by net labels on every connected pin, explicit no-connect
flags on unused pins and PWR_FLAGs where a power net has no driver, so KiCad
ERC is meaningful. Net names match the PCB (routed RF / IF / JESD / LO nets).
Board-to-board nets use identical names on both sides (J2/J3/J4 mezzanines,
J5 FFC, Micro-Fit power links).

Run with the project venv (kicad-sch-api):
  .venv/Scripts/python board/schematic/generate_schematics.py
"""
import json
import os
import re
import subprocess
import sys

import kicad_sch_api as ksa

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
KDIR = os.path.join(ROOT, "board", "kicad")
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import hg1_symbols as HS  # noqa: E402
import hg1_params as P  # noqa: E402

KICAD_CLI = os.environ.get("KICAD_CLI", r"C:/Program Files/KiCad/10.0/bin/kicad-cli.exe")
R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
L0805 = "Inductor_SMD:L_0805_2012Metric"


class Part:
    def __init__(self, ref, lib, value, nets, footprint=None, on_board=True, group="", in_bom=True):
        self.ref, self.lib, self.value, self.nets = ref, lib, value, nets
        self.footprint, self.on_board, self.group, self.in_bom = footprint, on_board, group, in_bom


def R(ref, a, b, value, group=""):
    return Part(ref, "Device:R", value, {"1": a, "2": b}, R0402, group=group)


def C(ref, a, b, value, fp=C0402, group=""):
    return Part(ref, "Device:C", value, {"1": a, "2": b}, fp, group=group)


def L(ref, a, b, value, fp=L0805, group=""):
    return Part(ref, "Device:L", value, {"1": a, "2": b}, fp, group=group)


def pcb_pad_nets(board, ref):
    """pad -> net of a footprint in the generated PCB (routed nets)."""
    txt = open(os.path.join(KDIR, board + ".kicad_pcb"), encoding="utf-8").read()
    for m in re.finditer(r'\n\t\(footprint "([^"]+)"(.*?)\n\t\)', txt, re.S):
        body = m.group(2)
        if re.search(r'\(property "Reference" "%s"' % re.escape(ref), body):
            pads = {}
            for pm in re.finditer(r'\(pad "([^"]*)" (\w+) (\w+)(.*?)\n\t\t\)', body, re.S):
                n = re.search(r'\(net "([^"]*)"\)', pm.group(4))
                if n and pm.group(1):
                    pads[pm.group(1)] = n.group(1)
            return pads
    return {}


# ======================================================================
# shared board-to-board pin-outs
# ======================================================================
J4_MAP = {1: "SPI_SCLK", 2: "GND", 3: "SPI_MOSI", 4: "CS_RFIC0", 5: "CS_RFIC1", 6: "CS_RFIC2", 7: "CS_RFIC3",
          8: "CS_RFIC4", 9: "CS_RFIC5", 10: "CS_ADC0", 11: "CS_ADC1", 12: "CS_ADC2", 13: "CS_ADC3",
          14: "CS_ADC4", 15: "CS_ADC5", 16: "CS_PLL_TX", 17: "CS_PLL_LO", 18: "CS_CLK", 19: "CHIRP_TRIG",
          20: "JESD_SYNC", 21: "PLL_LD_TX", 22: "PLL_LD_LO", 23: "FPGA_REFCLK", 24: "FPGA_SYSREF",
          25: "MCU_SPI_SCK", 26: "MCU_SPI_MOSI", 27: "MCU_SPI_MISO", 28: "CS_BF0", 29: "CS_BF1",
          30: "TX_MUTE_N", 31: "TX_LOAD", 32: "EN_DRAIN_SW", 33: "I2C3_SCL", 34: "I2C3_SDA", 35: "GNSS_RF",
          36: "RID_RF", 37: "-5V_BIAS", 38: "RF_RESET_N", 39: "GND", 40: "GND"}
FFC_MAP = {1: "PHY_MD1", 2: "PHY_MD2", 3: "GND", 4: "PHY_MD3", 5: "PHY_MD4", 6: "GND", 7: "PHY_MD5",
           8: "PHY_MD6", 9: "GND", 10: "PHY_MD7", 11: "PHY_MD8", 12: "GND", 13: "RS485_TX", 14: "RS485_RX",
           15: "RS485_DE", 16: "PPS_EXT", 17: "DISC_IN", 18: "EN_28V", 19: "EN_NEG5", 20: "EN_RF_5V",
           21: "EN_HEATER", 22: "VIN_SENSE", 23: "V28_SENSE", 24: "V5_SENSE", 25: "-5V_BIAS", 26: "-5V_BIAS",
           27: "+3V3_IO", 28: "GND", 29: "GND", 30: "GND"}


def mezz_maps():
    """J2/J3 pin -> net: JESD lanes from the PCB, PA current sense on J3 spares, rest GND."""
    out = {}
    for ref in ("J2", "J3"):
        pads = pcb_pad_nets("HG1-ANT", ref)
        m = {n: "GND" for n in range(1, 101)}
        for p, net in pads.items():
            if p.isdigit():
                m[int(p)] = net
        out[ref] = m
    spare = [n for n in range(1, 101, 2) if out["J3"][n] == "GND" and out["J3"].get(n + 1) == "GND"]
    for i, n in enumerate(spare[1:7]):
        out["J3"][n] = f"ID_PA{i + 1}"
    spare2 = [n for n in range(1, 101, 2) if out["J2"][n] == "GND"]
    out["J2"][spare2[1]] = "CAL_PROBE"
    return out


MEZZ = None


def holes(n, value, fp, net="GND"):
    return [Part(f"H{i + 1}", "Mechanical:MountingHole_Pad", value, {"1": net}, fp, group="mech", in_bom=False)
            for i in range(n)]


def conn(ref, lib, value, fp, pinmap, group=""):
    return Part(ref, lib, value, {str(k): v for k, v in pinmap.items()}, fp, group=group)


# ======================================================================
# HG1-ANT
# ======================================================================
def ant_parts():
    ps = []
    rx = P.rx_positions()
    for i in range(len(rx)):
        ps.append(Part(f"AE{10 + i}", "Device:Antenna", f"RX{i + 1:02d} stacked patch", {"1": f"RX{i + 1:02d}"},
                       on_board=False, group="elements"))
    for i in range(6):
        ps.append(Part(f"AE{60 + i}", "Device:Antenna", f"TX{i + 1} stacked patch", {"1": f"TX{i + 1}"},
                       on_board=False, group="elements"))
    ps.append(Part("AE70", "Device:Antenna", "Remote-ID 2.4/5.8 GHz patch", {"1": "RID_RF"}, on_board=False,
                   group="elements"))
    ps.append(Part("AE71", "Device:Antenna", "OTA cal probe", {"1": "CAL_PROBE"}, on_board=False, group="elements"))
    ps.append(Part("AE1", "HG1:GNSS_PATCH", "GNSS L1/L5 patch", {"FEED": "GNSS_RF", "GND": "GND"}, "HG1:GNSS_PATCH_18x18", group="elements"))

    for k in range(6):
        nets = {"LO_IN": "LO_CHIRP", "SCLK": "SPI_SCLK", "SDIO": "SPI_MOSI", "CSB": f"CS_RFIC{k}",
                "RESETB": "RF_RESET_N", "PD": "GND", "VCM_IN": f"VCM{k + 1}", "VCC_LNA": f"VCC_RX{k + 1}",
                "VCC_MIX": f"VCC_RX{k + 1}", "VCC_IF": f"VCC_RX{k + 1}", "VCC_LO": f"VCC_RX{k + 1}", "GND": "GND"}
        for i in range(len(rx)):
            col, row = i % P.RX_NX, i // P.RX_NX
            if col // 2 == k:
                nets[f"RFIN{row * 2 + col % 2 + 1}"] = f"RX{i + 1:02d}"
        for c in range(1, 9):
            nets[f"IF{c}I"] = f"IF{k + 1}_CH{c}I"
            nets[f"IF{c}Q"] = f"IF{k + 1}_CH{c}Q"
        ps.append(Part(f"U{10 + k}", "HG1:HRX-8", "HRX-8", nets, group=f"rx{k}"))
        an = {"CLK+": f"ADC_CLK{k + 1}", "SYSREF+": f"ADC_SYSREF{k + 1}", "SCLK": "SPI_SCLK", "SDIO": "SPI_MOSI",
              "CSB": f"CS_ADC{k}", "PWDN": "GND", "SYNCINB": "JESD_SYNC", "VCM_OUT": f"VCM{k + 1}",
              "VDD1": "+1V0_ADC", "VDD1P8": f"AVDD1P8_{k + 1}", "GND": "GND"}
        for c in range(1, 9):
            an[f"VIN{2 * (c - 1)}"] = f"IF{k + 1}_CH{c}I"
            an[f"VIN{2 * (c - 1) + 1}"] = f"IF{k + 1}_CH{c}Q"
        for n in range(4):
            an[f"SERDOUT{n}"] = f"JESD{k + 1}_L{n}"
        ps.append(Part(f"U{20 + k}", "HG1:AD9083", "AD9083BBCZ", an, group=f"rx{k}"))
        ps.append(Part(f"U{30 + k}", "Regulator_Linear:LT3045xDD", "LT3045 3.3 V",
                       {"IN": "+5V", "EN/UV": "+5V", "PG": None, "ILIM": None, "PGFB": None,
                        "SET": f"SET_RX{k + 1}", "OUTS": f"VCC_RX{k + 1}", "OUT": f"VCC_RX{k + 1}", "GND": "GND"},
                       "Package_DFN_QFN:DFN-10-1EP_3x3mm_P0.5mm_EP1.65x2.38mm", group=f"rx{k}"))
        ps.append(R(f"R{30 + k}", f"SET_RX{k + 1}", "GND", "33.2k 0.1%", f"rx{k}"))
        ps.append(C(f"C{30 + k}", f"VCC_RX{k + 1}", "GND", "10u", C0805, f"rx{k}"))
        ps.append(Part(f"U{40 + k}", "HG1:ADP7159", "ADP7159 1.8 V",
                       {"VIN": "+3V3_RF", "EN": "+3V3_RF", "REF": f"REF_ADC{k + 1}", "VOUT": f"AVDD1P8_{k + 1}",
                        "GND": "GND"}, group=f"rx{k}"))
        ps.append(C(f"C{40 + k}", f"REF_ADC{k + 1}", "GND", "1u", group=f"rx{k}"))
        ps.append(C(f"C{50 + k}", f"VCM{k + 1}", "GND", "100n", group=f"rx{k}"))

    # ---- TX: beamformers, GaN PAs, current sense, NTCs, drain switch
    bf_map = {"U51": {"RF1": 2, "RF2": 6, "RF3": 4}, "U50": {"RF1": 5, "RF2": 1, "RF3": 3}}
    for ref, cs in (("U50", "CS_BF0"), ("U51", "CS_BF1")):
        n = {"RF_COM": "TX_CHIRP", "SCLK": "MCU_SPI_SCK", "SDIO": "MCU_SPI_MOSI", "SDO": "MCU_SPI_MISO",
             "CSB": cs, "ADDR0": "GND", "ADDR1": "GND", "TR": "TX_MUTE_N", "TX_LOAD": "TX_LOAD",
             "PA_ON": "TX_MUTE_N", "RF4": None, "PA_BIAS4": None, "VDD": "+3V3_RF", "VSS_NEG": "-5V_BIAS",
             "GND": "GND"}
        for j, (rf, pa) in enumerate(bf_map[ref].items()):
            n[rf] = f"TXDRV{pa}"
            n[f"PA_BIAS{j + 1}"] = f"VG_PA{pa}"
        ps.append(Part(ref, "HG1:ADAR1000", "ADAR1000", n, group="tx"))
    for i in range(6):
        ps.append(Part(f"U{60 + i}", "HG1:GaN_PA_Ku", "GaN PA 1 W", {"RFIN": f"TXDRV{i + 1}", "RFOUT": f"TX{i + 1}",
                       "VG": f"VG_PA{i + 1}", "VD": f"PA_D{i + 1}", "GND": "GND"}, group="tx"))
        ps.append(C(f"C{2 * i + 1}", f"PA_D{i + 1}", "GND", "10u 50V", "Capacitor_SMD:C_1210_3225Metric", "tx"))
        ps.append(C(f"C{2 * i + 2}", f"PA_D{i + 1}", "GND", "10u 50V", "Capacitor_SMD:C_1210_3225Metric", "tx"))
        ps.append(R(f"RS{i + 1}", "+28V_SW", f"PA_D{i + 1}", "10m 1% 0805", "tx"))
        ps.append(Part(f"U{70 + i}", "HG1:INA186", "INA186A3", {"IN+": "+28V_SW", "IN-": f"PA_D{i + 1}",
                       "OUT": f"ID_PA{i + 1}", "REF": "GND", "VS": "+3V3_RF", "GND": "GND"}, group="tx"))
        ps.append(Part(f"RT{i + 1}", "Device:Thermistor_NTC", "10k B3435", {"1": f"NTC_PA{i + 1}", "2": "GND"},
                       R0402, group="tx"))
        ps.append(R(f"RP{i + 1}", "+3V3_RF", f"NTC_PA{i + 1}", "10k 0.1%", "tx"))
    ps.append(Part("U39", "HG1:ADS7138", "ADS7138", dict(
        {f"AIN{i}": f"NTC_PA{i + 1}" for i in range(6)}, SCL="I2C3_SCL", SDA="I2C3_SDA", ADDR="GND",
        AVDD="+3V3_RF", GND="GND"), group="tx"))
    ps.append(Part("Q1", "HG1:PMOS_SO8", "P-MOSFET -60 V drain switch",
                   {"S": "+28V_PA", "G": "DRAIN_GATE", "D": "+28V_SW"}, group="tx"))
    ps.append(Part("Q2", "HG1:NMOS_SOT23", "2N7002", {"G": "EN_DRAIN_SW", "D": "DRAIN_PD", "S": "GND"}, group="tx"))
    ps.append(R("RG1", "+28V_PA", "DRAIN_GATE", "10k", "tx"))
    ps.append(R("RG2", "DRAIN_GATE", "DRAIN_PD", "10k", "tx"))
    ps.append(R("RG3", "EN_DRAIN_SW", "GND", "100k", "tx"))

    # ---- chirp synthesis + clocking
    for ref, vco, amp, pre, cs, ld in (("U1", "U2", "U8", "TX", "CS_PLL_TX", "PLL_LD_TX"),
                                       ("U3", "U4", "U5", "LO", "CS_PLL_LO", "PLL_LD_LO")):
        ps.append(Part(ref, "HG1:ADF4159", "ADF4159", {"REF_IN": "REF_100M", "RFIN": f"{pre}_VCO_DIV",
                       "CLK": "SPI_SCLK", "DATA": "SPI_MOSI", "LE": cs, "CE": "+3V3_RF", "TXDATA": "CHIRP_TRIG",
                       "CP_OUT": f"{pre}_VCO_TUNE", "MUXOUT": ld, "RSET": f"RSET_{pre}", "VDD": "+3V3_RF",
                       "GND": "GND"}, group="synth"))
        ps.append(R(f"R{ref[1]}0", f"RSET_{pre}", "GND", "5.1k", "synth"))
        ps.append(C(f"CLF{ref[1]}", f"{pre}_VCO_TUNE", "GND", "2.2n C0G loop filter", group="synth"))
        ps.append(Part(vco, "HG1:HMC733", "HMC733LC4B", {"VTUNE": f"{pre}_VCO_TUNE", "RFOUT": f"{pre}_VCO_OUT",
                       "RFOUT_DIV2": f"{pre}_VCO_DIV", "VCC": "+5V", "GND": "GND"}, group="synth"))
        ps.append(Part(amp, "HG1:HMC903", "HMC903LP3E", {"RFIN": f"{pre}_VCO_OUT",
                       "RFOUT": "TX_CHIRP" if pre == "TX" else "LO_CHIRP", "VDD": "+3V3_RF", "GND": "GND"},
                       group="synth"))
    ps.append(Part("Y1", "HG1:OCXO_4P", "100 MHz OCXO", {"EN": "+3V3_RF", "OUT": "REF_100M", "VCC": "+3V3_RF",
                   "GND": "GND"}, group="synth"))
    hm = {"CLKIN0": "REF_100M", "SCLK": "SPI_SCLK", "SLEN": "CS_CLK", "SDATA": "SPI_MOSI", "RESET": "GND",
          "SYNC": "GND", "VCC": "+3V3_RF", "GND": "GND", "DCLK6": "FPGA_REFCLK", "SYSREF6": "FPGA_SYSREF"}
    for k in range(6):
        hm[f"DCLK{k}"] = f"ADC_CLK{k + 1}"
        hm[f"SYSREF{k}"] = f"ADC_SYSREF{k + 1}"
    ps.append(Part("U9", "HG1:HMC7044", "HMC7044", hm, group="synth"))

    # ---- power
    ps.append(Part("U36", "Regulator_Linear:LT3045xDD", "LT3045 3.3 V (RF)",
                   {"IN": "+5V", "EN/UV": "+5V", "PG": None, "ILIM": None, "PGFB": None, "SET": "SET_RF",
                    "OUTS": "+3V3_RF", "OUT": "+3V3_RF", "GND": "GND"},
                   "Package_DFN_QFN:DFN-10-1EP_3x3mm_P0.5mm_EP1.65x2.38mm", group="power"))
    ps.append(R("R36", "SET_RF", "GND", "33.2k 0.1%", "power"))
    ps.append(Part("U37", "HG1:TPS62913", "TPS62913 1.0 V", {"VIN": "+5V", "EN": "+5V", "FB": "FB_1V0",
                   "SW": "SW_1V0", "PG": None, "GND": "GND"}, group="power"))
    ps.append(L("L1", "SW_1V0", "+1V0_ADC", "1u", group="power"))
    ps.append(R("R37", "+1V0_ADC", "FB_1V0", "20k", "power"))
    ps.append(R("R38", "FB_1V0", "GND", "80.6k", "power"))
    ps.append(C("C37", "+1V0_ADC", "GND", "47u", C0805, "power"))
    ps.append(conn("J1", "Connector_Generic:Conn_01x04", "Micro-Fit 4p power in",
                   "Connector_Molex:Molex_Micro-Fit_3.0_43650-0400_1x04_P3.00mm_Horizontal",
                   {1: "+28V_PA", 2: "+5V", 3: "GND", 4: "GND"}, "power"))
    for ref in ("J2", "J3"):
        ps.append(conn(ref, "HG1:Conn_02x50", "LSHM-150 JESD mezzanine", None, MEZZ[ref], "mezz"))
    ps.append(conn("J4", "HG1:Conn_02x20_SM", "LSHM-120 control mezzanine", None, J4_MAP, "mezz"))
    ps += holes(10, "M2.5", "MountingHole:MountingHole_2.7mm_M2.5_Pad_Via")
    return ps


# ======================================================================
# HG1-DSP
# ======================================================================
def dsp_parts():
    ps = []
    vn = {"GTREFCLK": "FPGA_REFCLK", "SYSREF_IN": "FPGA_SYSREF", "JESD_SYNC": "JESD_SYNC",
          "SPI_SCLK": "SPI_SCLK", "SPI_MOSI": "SPI_MOSI", "SPI_MISO": None, "CHIRP_TRIG": "CHIRP_TRIG",
          "TX_LOAD": "TX_LOAD", "PLL_LD_TX": "PLL_LD_TX", "PLL_LD_LO": "PLL_LD_LO",
          "CS_PLL_TX": "CS_PLL_TX", "CS_PLL_LO": "CS_PLL_LO", "CS_CLK": "CS_CLK",
          "UART_MCU_TX": "UART_V2M", "UART_MCU_RX": "UART_M2V", "PMB_SCL": "I2C3_SCL", "PMB_SDA": "I2C3_SDA",
          "GNSS_RX": "GNSS_RX", "GNSS_TX": "GNSS_TX", "PPS": "PPS", "TCK": "JTAG_TCK", "TMS": "JTAG_TMS",
          "TDI": "JTAG_TDI", "TDO": "JTAG_TDO", "POR_B": "POR_B", "PS_REFCLK": "PS_REFCLK",
          "VCCINT": "VCCINT_0V8", "VCC_AIE": "VCC_AIE_0V8", "VCCAUX": "+1V5_AUX", "VCCO_DDR": "+1V1_DDR",
          "VCCO_1V8": "+1V8", "VCCO_3V3": "+3V3", "GTYP_AVCC": "+0V88_GT", "GTYP_AVTT": "+1V2_GT", "GND": "GND"}
    for k in range(1, 7):
        for l in range(4):
            vn[f"GTYP_RX_{k}_{l}"] = f"JESD{k}_L{l}"
    for i in range(6):
        vn[f"CS_RFIC{i}"] = f"CS_RFIC{i}"
        vn[f"CS_ADC{i}"] = f"CS_ADC{i}"
    for nm in ([f"DDR{ch}_{s}" for ch in "AB" for s in HS._ddr] + ["EMMC_CLK", "EMMC_CMD", "EMMC_RST_N",
               "QSPI_CLK", "QSPI_CS_N", "RGMII_TXC", "RGMII_TX_CTL", "MDC", "PHY_RST_N", "RGMII_RXC",
               "RGMII_RX_CTL", "PHY_INT_N", "MDIO", "IMU_SCLK", "IMU_MOSI", "IMU_MISO", "IMU_CS", "MAG_CS",
               "IMU_INT", "BLE_TX", "BLE_RX", "WIFI_SCK", "WIFI_MOSI", "WIFI_MISO", "WIFI_CS", "WIFI_IRQ",
               "WIFI_EN", "RS485_TX", "RS485_RX", "RS485_DE", "PPS_EXT", "DISC_IN", "RF_RESET_N"]
               + [f"EMMC_D{i}" for i in range(8)] + [f"QSPI_DQ{i}" for i in range(4)]
               + [f"RGMII_TXD{i}" for i in range(4)] + [f"RGMII_RXD{i}" for i in range(4)]):
        vn[nm] = nm
    ps.append(Part("U1", "HG1:XCVE2302", "XCVE2302-1LSESFVA784", vn, group="versal"))
    for ref, ch in (("U2", "A"), ("U3", "B")):
        n = {s: f"DDR{ch}_{s}" for s in HS._ddr}
        n.update(VDD1="+1V8", VDD2="+1V1_DDR", VDDQ="+1V1_DDR", VSS="GND")
        ps.append(Part(ref, "HG1:LPDDR4_x32", "MT53E1G32D2 LPDDR4", n, group="mem"))
    ps.append(Part("U4", "HG1:eMMC_5.1", "eMMC 64 GB pSLC", dict(
        {f"DAT{i}": f"EMMC_D{i}" for i in range(8)}, CLK="EMMC_CLK", CMD="EMMC_CMD", RST_N="EMMC_RST_N",
        VCC="+3V3", VCCQ="+1V8", VDDI="EMMC_VDDI", VSS="GND"), group="mem"))
    ps.append(C("C4", "EMMC_VDDI", "GND", "1u", group="mem"))
    ps.append(Part("U5", "Memory_Flash:MT25QUxxxxxx1xW7", "MT25QU512 QSPI", {
        "~{S}": "QSPI_CS_N", "C": "QSPI_CLK", "DQ0": "QSPI_DQ0", "DQ1": "QSPI_DQ1", "~{W}/DQ2": "QSPI_DQ2",
        "~{RESET}/DQ3": "QSPI_DQ3", "VCC": "+1V8", "VSS": "GND", "PAD": "GND"},
        "Package_SON:WSON-8-1EP_8x6mm_P1.27mm_EP3.4x4.3mm", group="mem"))
    phy = {"TX_CLK": "RGMII_TXC", "TX_CTRL": "RGMII_TX_CTL", "RX_CLK": "RGMII_RXC", "RX_CTRL": "RGMII_RX_CTL",
           "MDC": "MDC", "MDIO": "MDIO", "RESET_N": "PHY_RST_N", "INT_N": "PHY_INT_N", "XI": "PHY_XI",
           "VDDA2P5": "+2V5", "VDD1P0": "+1V0_PHY", "VDDIO": "+1V8", "GND": "GND"}
    for i in range(4):
        phy[f"TX_D{i}"] = f"RGMII_TXD{i}"
        phy[f"RX_D{i}"] = f"RGMII_RXD{i}"
    for i, p in enumerate(["A+", "A-", "B+", "B-", "C+", "C-", "D+", "D-"]):
        phy[f"TD_{p}"] = f"PHY_MD{i + 1}"
    ps.append(Part("U6", "HG1:DP83867IR", "DP83867IRRGZ", phy, group="io"))
    ps.append(Part("Y3", "HG1:OCXO_4P", "25 MHz XO", {"EN": "+1V8", "OUT": "PHY_XI", "VCC": "+1V8", "GND": "GND"},
                   "Oscillator:Oscillator_SMD_EuroQuartz_XO53-4Pin_5.0x3.2mm", group="io"))
    ps.append(Part("Y2", "HG1:OCXO_4P", "33.333 MHz XO (PS_REFCLK)", {"EN": "+1V8", "OUT": "PS_REFCLK",
                   "VCC": "+1V8", "GND": "GND"}, "Oscillator:Oscillator_SMD_EuroQuartz_XO53-4Pin_5.0x3.2mm",
                   group="io"))
    stm = {"PA0": "VIN_SENSE", "PA1": "V28_SENSE", "PA2": "V5_SENSE", "PA3": "V3V3_SENSE", "PC0": "VNEG_SENSE",
           "PB1": "VNEG_SENSE", "PC1": "ID_PA1", "PC2": "ID_PA2", "PC3": "ID_PA3", "PB14": "ID_PA4",
           "PF0": "ID_PA5", "PB12": "ID_PA6", "PB11": "NTC_HOUSING", "PB0": "NTC_RFIC", "PB4": "EN_NEG5",
           "PB5": "EN_28V", "PA8": "EN_DRAIN_SW", "PB7": "EN_RF_5V", "PB6": "TX_MUTE_N", "PC6": "EN_VERSAL",
           "PC7": "EN_HEATER", "PC10": "PLL_LD_TX", "PC11": "PLL_LD_LO", "PC12": "NEG_PGOOD", "PA4": "CS_BF0",
           "PA15": "CS_BF1", "PA5": "MCU_SPI_SCK", "PA6": "MCU_SPI_MISO", "PA7": "MCU_SPI_MOSI",
           "PC8": "I2C3_SCL", "PC9": "I2C3_SDA", "PA9": "UART_M2V", "PA10": "UART_V2M", "PA13": "SWDIO",
           "PA14": "SWCLK", "PG10": "NRST", "VBAT": "+3V3", "VDD": "+3V3", "VDDA": "+3V3", "VREF+": "+3V3",
           "VSS": "GND", "VSSA": "GND"}
    ps.append(Part("U7", "MCU_ST_STM32G4:STM32G474RETx", "STM32G474RET6", stm, "Package_QFP:LQFP-64_10x10mm_P0.5mm",
                   group="mcu"))
    ps.append(C("C7", "NRST", "GND", "100n", group="mcu"))
    ps.append(conn("J8", "Connector_Generic:Conn_01x05", "SWD (Tag-Connect TC2030)",
                   "Connector_PinHeader_1.27mm:PinHeader_1x05_P1.27mm_Vertical",
                   {1: "+3V3", 2: "SWDIO", 3: "SWCLK", 4: "NRST", 5: "GND"}, "mcu"))
    for ref, net in (("RT1", "NTC_HOUSING"), ("RT2", "NTC_RFIC")):
        ps.append(Part(ref, "Device:Thermistor_NTC", "10k B3435", {"1": net, "2": "GND"}, R0402, group="mcu"))
        ps.append(R(f"RP{ref[-1]}", "+3V3", net, "10k 0.1%", "mcu"))
    ps.append(R("RD1", "+3V3", "V3V3_SENSE", "10k", "mcu"))
    ps.append(R("RD2", "V3V3_SENSE", "GND", "10k", "mcu"))
    ps.append(R("RN1", "+3V3", "VNEG_SENSE", "20k 0.1%", "mcu"))
    ps.append(R("RN2", "VNEG_SENSE", "-5V_BIAS", "40.2k 0.1%", "mcu"))
    ps.append(Part("U30", "HG1:TPS3700", "TPS3700 -5 V window", {"INA+": "VNEG_SENSE", "INB-": "VNEG_SENSE",
                   "OUTA": "NEG_PGOOD", "OUTB": "NEG_PGOOD", "VDD": "+3V3", "GND": "GND"}, group="mcu"))
    ps.append(R("RPG", "+3V3", "NEG_PGOOD", "10k", "mcu"))
    ps.append(Part("U8", "RF_GPS:NEO-M9N", "NEO-F10T (NEO footprint)", {
        "TXD/SPI_MISO": "GNSS_TX", "RXD/SPI_MOSI": "GNSS_RX", "TIMEPULSE": "PPS", "RF_IN": "GNSS_RF",
        "VCC": "+3V3", "V_BCKP": "+3V3", "VDD_USB": "GND", "GND": "GND"}, "RF_GPS:ublox_NEO", group="io"))
    ps.append(Part("U9", "RF_Module:MDBT50Q-1MV2", "MDBT50Q nRF52840", {"P0.06": "BLE_TX", "P0.08": "BLE_RX",
                   "VDD": "+3V3", "VDDH": "+3V3", "GND": "GND"}, "RF_Module:Raytac_MDBT50Q", group="io"))
    ps.append(Part("U10", "HG1:nRF7002", "nRF7002", {"SPI_SCK": "WIFI_SCK", "SPI_MOSI": "WIFI_MOSI",
                   "SPI_MISO": "WIFI_MISO", "SPI_CS": "WIFI_CS", "HOST_IRQ": "WIFI_IRQ", "BUCKEN": "WIFI_EN",
                   "IOVDD_EN": "WIFI_EN", "RF": "RID_RF", "VBAT": "+3V3", "VDDIO": "+1V8", "GND": "GND"},
                   "Package_DFN_QFN:QFN-40-1EP_6x6mm_P0.5mm_EP4.6x4.6mm", group="io"))
    ps.append(Part("U11", "Sensor_Motion:ISM330DHCX", "ISM330DHCX", {"CS": "IMU_CS", "SCL": "IMU_SCLK",
                   "SDA": "IMU_MOSI", "SDO/SA0": "IMU_MISO", "INT1": "IMU_INT", "VDD": "+1V8", "VDDIO": "+1V8",
                   "GND": "GND"}, "Package_LGA:Bosch_LGA-14_3x2.5mm_P0.5mm", group="io"))
    ps.append(Part("U12", "Sensor_Magnetic:LIS2MDL", "LIS2MDL", {"SCL/SPC": "IMU_SCLK", "SDA/SDI/SDO": "IMU_MOSI",
                   "~{CS}": "MAG_CS", "C1": "MAG_C1", "Vdd": "+1V8", "Vdd_IO": "+1V8", "GND": "GND"},
                   "Package_LGA:LGA-12_2x2mm_P0.5mm", group="io"))
    ps.append(C("C12", "MAG_C1", "GND", "220n", group="io"))

    # ---- power tree: +12V in -> PoLs
    for ref, rail, sw, lref in (("U20", "VCCINT_0V8", "SW_VCCINT", "L1"), ("U21", "VCC_AIE_0V8", "SW_AIE", "L2")):
        ps.append(Part(ref, "HG1:TPS546D24A", "TPS546D24A 0.8 V", {"VIN": "+12V", "EN": "EN_VERSAL",
                       "PMB_CLK": "I2C3_SCL", "PMB_DATA": "I2C3_SDA", "VOSNS+": rail, "VOSNS-": "GND", "SW": sw,
                       "PGOOD": "POR_B", "ADRSEL": "GND", "GND": "GND"}, group="power"))
        ps.append(L(lref, sw, rail, "XAL6030 0.22u", "Inductor_SMD:L_Coilcraft_XAL6030-XXX", "power"))
        ps.append(C(f"C{lref}", rail, "GND", "470u polymer", C0805, "power"))
    ps.append(R("RPOR", "+3V3", "POR_B", "4.7k", "power"))
    ps.append(Part("U22", "HG1:LT8640S", "LT8640S 3.3 V", {"VIN": "+12V", "EN/UV": "EN_VERSAL", "FB": "FB_3V3",
                   "RT": "RT_3V3", "SW": "SW_3V3", "PG": None, "BST": "BST_3V3", "INTVCC": "INTVCC_3V3",
                   "GND": "GND"}, group="power"))
    ps.append(L("L3", "SW_3V3", "+3V3", "XAL6030 1.0u", "Inductor_SMD:L_Coilcraft_XAL6030-XXX", "power"))
    ps += [R("R22A", "+3V3", "FB_3V3", "1M", "power"), R("R22B", "FB_3V3", "GND", "316k", "power"),
           R("R22C", "RT_3V3", "GND", "18.2k", "power"), C("C22A", "BST_3V3", "SW_3V3", "100n", group="power"),
           C("C22B", "INTVCC_3V3", "GND", "1u", group="power"), C("C22C", "+3V3", "GND", "47u", C0805, "power")]
    for ref, rail, vin, val in (("U23", "+1V8", "+12V", "TPS62913 1.8 V"), ("U24", "+1V1_DDR", "+12V",
                                "TPS62913 1.1 V")):
        sw, fb = f"SW_{ref}", f"FB_{ref}"
        ps.append(Part(ref, "HG1:TPS62913", val, {"VIN": vin, "EN": "EN_VERSAL", "FB": fb, "SW": sw, "PG": None,
                       "GND": "GND"}, group="power"))
        ps += [L(f"L{ref[1:]}", sw, rail, "2.2u", group="power"), R(f"R{ref[1:]}A", rail, fb, "100k", "power"),
               R(f"R{ref[1:]}B", fb, "GND", "49.9k", "power"), C(f"C{ref[1:]}", rail, "GND", "22u", C0805, "power")]
    for ref, rail, vin, val in (("U25", "+1V5_AUX", "+3V3", "1.5 V LDO"), ("U26", "+0V88_GT", "+1V8", "0.88 V LDO"),
                                ("U27", "+1V2_GT", "+1V8", "1.2 V LDO"), ("U28", "+2V5", "+3V3", "2.5 V LDO"),
                                ("U29", "+1V0_PHY", "+1V8", "1.0 V LDO")):
        ps.append(Part(ref, "HG1:ADP7159", f"ADP7159 {val}", {"VIN": vin, "EN": vin, "REF": f"REF_{ref}",
                       "VOUT": rail, "GND": "GND"}, group="power"))
        ps.append(C(f"CR{ref[1:]}", f"REF_{ref}", "GND", "1u", group="power"))
    for ref in ("J2", "J3"):
        ps.append(conn(ref, "HG1:Conn_02x50", "LSHM-150 (mate ANT)", None, MEZZ[ref], "mezz"))
    ps.append(conn("J4", "HG1:Conn_02x20_SM", "LSHM-120 (mate ANT)", None, J4_MAP, "mezz"))
    ps.append(conn("J5", "Connector_Generic:Conn_01x30", "FFC to PWR/IO",
                   "Connector_FFC-FPC:Hirose_FH12-30S-0.5SH_1x30-1MP_P0.50mm_Horizontal", FFC_MAP, "mezz"))
    ps.append(conn("J6", "Connector_Generic:Conn_01x04", "Micro-Fit +12V in",
                   "Connector_Molex:Molex_Micro-Fit_3.0_43650-0400_1x04_P3.00mm_Horizontal",
                   {1: "+12V", 2: "+12V", 3: "GND", 4: "GND"}, "mezz"))
    ps.append(conn("J7", "Connector_Generic:Conn_01x06", "JTAG",
                   "Connector_PinHeader_1.27mm:PinHeader_1x06_P1.27mm_Vertical",
                   {1: "+1V8", 2: "JTAG_TCK", 3: "JTAG_TMS", 4: "JTAG_TDI", 5: "JTAG_TDO", 6: "GND"}, "mezz"))
    ps.append(R("RIO", "+3V3", "+3V3_IO", "0R (3.3 V to PWR/IO board)", "mezz"))
    ps += holes(6, "M2.5", "MountingHole:MountingHole_2.7mm_M2.5_Pad_Via")
    ps.append(Part("J9", "Connector:Conn_Coaxial", "U.FL OTA-cal port", {"1": "CAL_PROBE", "2": "GND"},
                   "Connector_Coaxial:U.FL_Hirose_U.FL-R-SMT-1_Vertical", group="mezz"))
    return ps


# ======================================================================
# HG1-PWR
# ======================================================================
def pwr_parts():
    ps = []
    ps.append(conn("J1", "HG1:M12_8P", "M12 A-coded 8p power/IO", None,
                   {1: "VIN_RAW", 2: "VIN_RAW", 3: "GND", 4: "GND", 5: "RS485_A", 6: "RS485_B", 7: "PPS_EXT",
                    8: "DISC_IN", "SHELL": "CHASSIS"}, "in"))
    ps[-1].nets = {"1": "VIN_RAW", "2": "VIN_RAW", "3": "GND", "4": "GND", "5": "RS485_A", "6": "RS485_B",
                   "7": "PPS_EXT", "8": "DISC_IN", "SHELL": "CHASSIS"}
    ps.append(Part("D1", "Device:D_TVS", "SMCJ36CA", {"1": "VIN_RAW", "2": "GND"}, "Diode_SMD:D_SMC", group="in"))
    ps.append(Part("Q1", "HG1:NMOS_PWR", "N-MOSFET 80 V pass FET", {"D": "VIN_RAW", "G": "SURGE_GATE",
                   "S": "VIN_SNS"}, group="in"))
    ps.append(R("RS1", "VIN_SNS", "VIN_PROT", "5m 1%", "in"))
    ps.append(Part("U1", "HG1:LT4363", "LT4363", {"VCC": "VIN_RAW", "SNS": "VIN_SNS", "UV": "UV_DIV", "OV": "OV_DIV",
                   "GATE": "SURGE_GATE", "OUT": "VIN_PROT", "FB": "FB_SURGE", "TMR": "TMR", "FLT": None,
                   "GND": "GND"}, group="in"))
    ps += [R("R1A", "VIN_RAW", "UV_DIV", "100k", "in"), R("R1B", "UV_DIV", "GND", "10k", "in"),
           R("R1C", "VIN_RAW", "OV_DIV", "100k", "in"), R("R1D", "OV_DIV", "GND", "2.7k", "in"),
           R("R1E", "VIN_PROT", "FB_SURGE", "100k", "in"), R("R1F", "FB_SURGE", "GND", "3.3k", "in"),
           C("C1T", "TMR", "GND", "47n", group="in")]
    ps.append(L("L1", "VIN_PROT", "VIN_FILT", "DM filter 4.7u", "Inductor_SMD:L_12x12mm_H6mm", "in"))
    ps.append(Part("C1", "Device:C_Polarized", "100u 50V hold-up", {"1": "VIN_FILT", "2": "GND"},
                   "Capacitor_SMD:CP_Elec_8x10", group="in"))
    ps.append(Part("U2", "HG1:LT8640S", "LT8640S 12 V", {"VIN": "VIN_FILT", "EN/UV": "VIN_FILT", "FB": "FB_12",
                   "RT": "RT_12", "SW": "SW_12", "PG": None, "BST": "BST_12", "INTVCC": "INTVCC_12", "GND": "GND"},
                   group="buck"))
    ps += [L("L2", "SW_12", "+12V_DSP", "XAL6030 4.7u", "Inductor_SMD:L_Coilcraft_XAL6030-XXX", "buck"),
           R("R2A", "+12V_DSP", "FB_12", "1M", "buck"), R("R2B", "FB_12", "GND", "73.2k", "buck"),
           R("R2C", "RT_12", "GND", "18.2k", "buck"), C("C2B", "BST_12", "SW_12", "100n", group="buck"),
           C("C2I", "INTVCC_12", "GND", "1u", group="buck"), C("C2O", "+12V_DSP", "GND", "47u", C0805, "buck")]
    ps.append(Part("U5", "HG1:LT8640S", "LT8640S 5 V", {"VIN": "VIN_FILT", "EN/UV": "EN_RF_5V", "FB": "FB_5",
                   "RT": "RT_5", "SW": "SW_5", "PG": None, "BST": "BST_5", "INTVCC": "INTVCC_5", "GND": "GND"},
                   group="buck"))
    ps += [L("L5", "SW_5", "+5V_RF", "XAL6030 2.2u", "Inductor_SMD:L_Coilcraft_XAL6030-XXX", "buck"),
           R("R5A", "+5V_RF", "FB_5", "1M", "buck"), R("R5B", "FB_5", "GND", "191k", "buck"),
           R("R5C", "RT_5", "GND", "18.2k", "buck"), C("C5B", "BST_5", "SW_5", "100n", group="buck"),
           C("C5I", "INTVCC_5", "GND", "1u", group="buck"),
           Part("C2", "Device:C_Polarized", "100u 50V", {"1": "+5V_RF", "2": "GND"}, "Capacitor_SMD:CP_Elec_8x10",
                group="buck")]
    ps.append(Part("U3", "HG1:LT8390", "LT8390 28 V buck-boost", {"VIN": "VIN_FILT", "EN/UVLO": "EN_28V",
                   "FB": "FB_28", "ISP": "ISP_28", "ISN": "+28V_PA", "TG1": "TG1", "BG1": "BG1", "TG2": "TG2",
                   "BG2": "BG2", "SW1": "SW1_28", "SW2": "SW2_28", "PG": None, "INTVCC": "INTVCC_28", "GND": "GND"},
                   group="bb"))
    for q, d, g, s in (("Q2", "VIN_FILT", "TG1", "SW1_28"), ("Q3", "SW1_28", "BG1", "GND"),
                       ("Q4", "ISP_28", "TG2", "SW2_28"), ("Q5", "SW2_28", "BG2", "GND")):
        ps.append(Part(q, "HG1:NMOS_PWR", "N-MOSFET 60 V", {"D": d, "G": g, "S": s}, group="bb"))
    ps += [L("L3", "SW1_28", "SW2_28", "10u 6A", "Inductor_SMD:L_12x12mm_H6mm", "bb"),
           R("R3S", "ISP_28", "+28V_PA", "4m 1%", "bb"), R("R3A", "+28V_PA", "FB_28", "1M", "bb"),
           R("R3B", "FB_28", "GND", "35.7k", "bb"), C("C3I", "INTVCC_28", "GND", "4.7u", group="bb"),
           C("C3O", "+28V_PA", "GND", "10u 50V", "Capacitor_SMD:C_1210_3225Metric", "bb")]
    ps.append(Part("U4", "HG1:LT3462", "LT3462 -5 V", {"VIN": "+5V_RF", "SHDN": "EN_NEG5", "FB": "FB_NEG",
                   "SW": "SW_NEG", "VOUT": "-5V_BIAS", "GND": "GND"}, group="bb"))
    ps += [L("L4", "+5V_RF", "SW_NEG", "10u", group="bb"), R("R4A", "-5V_BIAS", "FB_NEG", "402k", "bb"),
           R("R4B", "FB_NEG", "GND", "100k", "bb"), C("C4O", "-5V_BIAS", "GND", "4.7u", group="bb")]
    ps.append(Part("U6", "HG1:THVD1450", "THVD1450", {"R": "RS485_RX", "~{RE}": "GND", "DE": "RS485_DE",
                   "D": "RS485_TX", "A": "RS485_A", "B": "RS485_B", "VCC": "+3V3_IO", "GND": "GND"}, group="io"))
    mag = {}
    for i, p in enumerate(["A+", "A-", "B+", "B-", "C+", "C-", "D+", "D-"]):
        mag[f"P{p}"] = f"PHY_MD{i + 1}"
        mag[f"C{p}"] = f"MDI_{i + 1}"
    ps.append(Part("T1", "HG1:GBE_MAG", "HX1188NL", mag, "HG1:GBE_MAG_16P", group="io"))
    ps.append(conn("J2", "HG1:M12_8P", "M12 X-coded Ethernet", None,
                   {**{str(i): f"MDI_{i}" for i in range(1, 9)}, "SHELL": "CHASSIS"}, "io"))
    ps[-1].nets = {**{str(i): f"MDI_{i}" for i in range(1, 9)}, "SHELL": "CHASSIS"}
    ps.append(conn("J3", "Connector_Generic:Conn_01x04", "Micro-Fit to ANT",
                   "Connector_Molex:Molex_Micro-Fit_3.0_43650-0400_1x04_P3.00mm_Horizontal",
                   {1: "+28V_PA", 2: "+5V_RF", 3: "GND", 4: "GND"}, "io"))
    ps.append(conn("J4", "Connector_Generic:Conn_01x04", "Micro-Fit to DSP",
                   "Connector_Molex:Molex_Micro-Fit_3.0_43650-0400_1x04_P3.00mm_Horizontal",
                   {1: "+12V_DSP", 2: "+12V_DSP", 3: "GND", 4: "GND"}, "io"))
    ps.append(conn("J5", "Connector_Generic:Conn_01x30", "FFC to DSP",
                   "Connector_FFC-FPC:Hirose_FH12-30S-0.5SH_1x30-1MP_P0.50mm_Horizontal", FFC_MAP, "io"))
    ps += [R("RV1", "VIN_PROT", "VIN_SENSE", "150k", "io"), R("RV2", "VIN_SENSE", "GND", "10k", "io"),
           R("RV3", "+28V_PA", "V28_SENSE", "100k", "io"), R("RV4", "V28_SENSE", "GND", "10k", "io"),
           R("RV5", "+5V_RF", "V5_SENSE", "10k", "io"), R("RV6", "V5_SENSE", "GND", "10k", "io"),
           R("RCH", "CHASSIS", "GND", "1M", "io"), C("CCH", "CHASSIS", "GND", "10n 2kV", C0805, "io")]
    ps.append(Part("Q6", "HG1:NMOS_PWR", "N-MOSFET heater switch", {"D": "HEATER_N", "G": "EN_HEATER", "S": "GND"},
                   group="io"))
    ps.append(R("RHT", "EN_HEATER", "GND", "100k", "io"))
    ps += holes(4, "M3", "MountingHole:MountingHole_3.2mm_M3_Pad_Via")
    ps.append(conn("J6", "Connector_Generic:Conn_01x02", "Radome / board heater 10 W",
                   "Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical",
                   {1: "VIN_FILT", 2: "HEATER_N"}, "io"))
    return ps


# ======================================================================
# schematic builder
# ======================================================================
def normalise_refs(parts):
    """Keep valid unique refs (PCB-placed parts keep theirs); renumber the rest from 100."""
    used, fixed = set(), []
    for pt in parts:
        ok = re.fullmatch(r"[A-Z]+[0-9]+", pt.ref) and pt.ref not in used
        if ok:
            used.add(pt.ref)
        fixed.append(ok)
    nxt = {}
    for pt, ok in zip(parts, fixed):
        if ok:
            continue
        pre = re.match(r"[A-Z]+", pt.ref).group(0)
        n = nxt.get(pre, 100)
        while f"{pre}{n}" in used:
            n += 1
        pt.ref = f"{pre}{n}"
        used.add(pt.ref)
        nxt[pre] = n + 1
    return parts


def build(name, title, parts, paper="A0"):
    parts = normalise_refs(parts)
    cache = ksa.get_symbol_cache()
    s = ksa.create_schematic(name)
    try:
        s.set_paper_size(paper)
    except Exception:
        pass
    try:
        s.set_title_block(title=title, company="HoloGuard HG-1", rev="A", date="2026-10-07")
    except Exception:
        pass
    W, H = (1189, 841) if paper == "A0" else (841, 594)
    margin, x, y, row_h = 25.4, 25.4, 30.48, 0.0
    group = None
    placed = []
    flags = 0
    for pt in parts:
        sd = cache.get_symbol(pt.lib) if hasattr(cache, "get_symbol") else ksa.get_symbol_info(pt.lib)
        if sd is None:
            sd = ksa.get_symbol_info(pt.lib)
        pins = sd.pins
        xs = [p.position.x for p in pins] or [0]
        ys = [p.position.y for p in pins] or [0]
        nets_by_side = {"L": 0, "R": 0}
        for p in pins:
            net = pt.nets.get(p.number, pt.nets.get(p.name))
            if net:
                side = "L" if p.position.x <= min(xs) + 0.01 else "R"
                nets_by_side[side] = max(nets_by_side[side], len(net))
        left = min(xs) - 3 - nets_by_side["L"] * 1.3
        right = max(xs) + 3 + nets_by_side["R"] * 1.3
        top, bot = max(ys) + 6, min(ys) - 6
        w, h = right - left + 6, top - bot + 4
        if pt.group != group and group is not None:
            x += 7.62                         # visual gap between functional groups
        group = pt.group
        if x + w > W - margin:
            x, y, row_h = margin, y + row_h + 5.08, 0.0
        X = 2.54 * round((x - left) / 2.54)
        Y = 2.54 * round((y + top) / 2.54)
        fp = pt.footprint
        if fp is None and pt.lib.startswith("HG1:"):
            fp = HS.SYMBOLS[pt.lib[4:]]["footprint"]
        c = s.components.add(pt.lib, reference=pt.ref, value=pt.value, position=(X, Y), footprint=fp or None)
        try:
            if not pt.on_board:
                c.on_board = False
                c.in_bom = False
            if not pt.in_bom:
                c.in_bom = False
        except Exception:
            pass
        placed.append((pt, c, sd))
        x += w
        row_h = max(row_h, h)
    if y + row_h > H:
        print(f"  WARNING {name}: content {y + row_h:.0f} mm exceeds sheet height {H} mm")

    # labels / no-connects
    net_types = {}
    for pt, c, sd in placed:
        seen = set()
        for p in sd.pins:
            pos = s.get_component_pin_position(pt.ref, p.number)
            key = (round(pos.x, 2), round(pos.y, 2))
            net = pt.nets.get(p.number, pt.nets.get(p.name)) if (p.number in pt.nets or p.name in pt.nets) else "NC"
            if key in seen:
                continue
            seen.add(key)
            if net is None or net == "NC":
                s.no_connects.add(position=(pos.x, pos.y))
                continue
            # label points away from the body: pin rotation 0 = left-side pin, etc.
            ang = {0: 180, 180: 0, 90: 270, 270: 90}.get(int(round(p.rotation)) % 360, 0)
            s.add_label(net, position=(pos.x, pos.y), rotation=ang)
            net_types.setdefault(net, set()).add(p.pin_type.value)
    # PWR_FLAG on nets that carry power inputs but no power output
    fx, fy = 25.4, H - 40.64
    for net, types in sorted(net_types.items()):
        if "power_in" in types and "power_out" not in types:
            flags += 1
            ref = f"#FLG{flags:02d}"
            s.components.add("power:PWR_FLAG", reference=ref, value="PWR_FLAG", position=(fx, fy))
            s.add_label(net, pin=(ref, "1"))
            fx += 2.54 * round((len(net) * 1.3 + 12) / 2.54)
            if fx > W - 60:
                fx, fy = 25.4, fy + 12.7
    out = os.path.join(KDIR, name + ".kicad_sch")
    s.save(out)
    to_global_labels(out)
    return out, len(placed), len(net_types), flags


def to_global_labels(path):
    """Local labels on the root sheet become '/NET'; global labels keep the bare net
    name used by the PCB, so convert every label to a passive global label."""
    txt = open(path, encoding="utf-8").read()

    def rep(m):
        name, x, y, a = m.group(1), m.group(2), m.group(3), int(float(m.group(4)))
        just = "right" if a in (180, 270) else "left"
        return (f'(global_label "{name}" (shape passive) (at {x} {y} {a}) (fields_autoplaced yes)'
                f' (effects (font (size 1.27 1.27)) (justify {just}))')
    txt, n = re.subn(r'\(label "([^"]+)"\s*\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\)\s*\(effects\s*\(font\s*\(size [\d.]+ [\d.]+\)\s*\)\s*'
                     r'\(justify [^)]*\)\s*\)', rep, txt)
    open(path, "w", encoding="utf-8").write(txt)
    return n


def erc(path):
    rpt = path.replace(".kicad_sch", "_erc.json")
    subprocess.run([KICAD_CLI, "sch", "erc", "--format", "json", "--severity-all", "-o", rpt, path],
                   capture_output=True)
    d = json.load(open(rpt))
    kinds = {}
    for sh in d.get("sheets", []):
        for v in sh.get("violations", []):
            key = (v["severity"], v["type"])
            kinds[key] = kinds.get(key, 0) + 1
    return kinds


def main():
    global MEZZ
    lib = os.path.join(KDIR, "HG1.kicad_sym")
    names = HS.write_library(lib)
    with open(os.path.join(KDIR, "fp-lib-table"), "w") as fh:
        fh.write('(fp_lib_table\n\t(version 7)\n\t(lib (name "HG1")(type "KiCad")(uri "${KIPRJMOD}/HG1.pretty")'
                 '(options "")(descr "HoloGuard HG-1 project footprints"))\n)\n')
    with open(os.path.join(KDIR, "sym-lib-table"), "w") as fh:
        fh.write('(sym_lib_table\n\t(version 7)\n\t(lib (name "HG1")(type "KiCad")(uri "${KIPRJMOD}/HG1.kicad_sym")'
                 '(options "")(descr "HoloGuard HG-1 project symbols"))\n)\n')
    ksa.get_symbol_cache().add_library_path(lib)
    print(f"HG1.kicad_sym: {len(names)} symbols")
    MEZZ = mezz_maps()
    for name, title, fn in (("HG1-ANT", "HG-1 antenna / RF board", ant_parts),
                            ("HG1-DSP", "HG-1 processing board", dsp_parts),
                            ("HG1-PWR", "HG-1 power / IO board", pwr_parts)):
        path, n, nn, fl = build(name, title, fn())
        kinds = erc(path)
        errs = sum(v for (sev, _), v in kinds.items() if sev == "error")
        warns = sum(v for (sev, _), v in kinds.items() if sev == "warning")
        print(f"{name}.kicad_sch: {n} symbols, {nn} nets, {fl} PWR_FLAGs -> ERC errors {errs}, warnings {warns}")
        subprocess.run([KICAD_CLI, "sch", "export", "netlist", "--format", "kicadxml", "-o",
                        os.path.join(KDIR, name + ".net.xml"), path], capture_output=True)
        for (sev, t), v in sorted(kinds.items()):
            print(f"     {sev:8s} {t:32s} {v}")


if __name__ == "__main__":
    main()

"""HoloGuard HG-1 -- independent raw-ADC scenario generator.

Synthesises the dechirped complex-baseband ADC cube the HG-1 receivers
deliver (48 RX x chirps x samples, int16 I/Q) for a C-UAS scene:
  * exact TX->target->RX delays for all 6 x 48 MIMO paths (near/far field
    agnostic), DDMA slow-time phase codes on the 6 GaN transmitters
  * quadcopter rotor-blade micro-Doppler, bird wing-beat, static clutter,
    TX->RX leakage, thermal noise; amplitudes from the radar equation
    (analysis/radarlib.py, same Pt / G / NF / losses as the link budget)
Writes  sim/out/scenario.iq  (+ truth.json) for firmware/dsp hg1_radard.

The generator shares NO code with the C++ chain -- it is the independent
reference used to verify the firmware.
    python firmware/sim/gen_scenario.py [--frames 24] [--period 0.1]
"""
import argparse
import json
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "analysis"))
import hg1_params as P  # noqa: E402
from radarlib import staring_snr_db  # noqa: E402

C = 299_792_458.0
# ---- sim profile (must match RadarConfig::sim_long_range) ------------------
F0 = P.F0_GHZ * 1e9
BW = 50e6
T_CHIRP = 75e-6
T_PRI = 80e-6
NS = 512
NL = 128
NSUB = 8
FS = NS / T_CHIRP
SLOPE = BW / T_CHIRP
LAM = C / F0

TX = np.array([[x * 1e-3, y * 1e-3, 0.0] for (x, y) in P.tx_positions()])     # array frame
RX = np.array([[x * 1e-3, y * 1e-3, 0.0] for (x, y) in P.rx_positions()])     # X right, Y up, Z boresight
NTX, NRX = len(TX), len(RX)


def sph(r, az_deg, el_deg):
    a, e = np.radians(az_deg), np.radians(el_deg)
    return np.array([r * np.cos(e) * np.sin(a), r * np.sin(e), r * np.cos(e) * np.cos(a)])


class Target:
    def __init__(self, name, kind, rcs, pos, vel, rotors=0, rpm=0.0, blade=0.12, wing_hz=0.0):
        self.name, self.kind, self.rcs = name, kind, rcs
        self.p0, self.v = np.asarray(pos, float), np.asarray(vel, float)
        self.rotors, self.rpm, self.blade, self.wing_hz = rotors, rpm, blade, wing_hz
        rng = np.random.default_rng(abs(hash(name)) % 2**32)
        self.phi = rng.uniform(0, 2 * np.pi, size=max(rotors, 2) * 2)

    def pos(self, t):
        return self.p0 + self.v * t

    def modulation(self, t_l, los):
        """Per-chirp complex modulation from moving parts (slow-time)."""
        m = np.ones_like(t_l, dtype=np.complex64)
        if self.rotors:
            arm = 0.17
            for q in range(self.rotors):
                ca = np.array([np.cos(q * np.pi / 2 + np.pi / 4), 0, np.sin(q * np.pi / 2 + np.pi / 4)]) * arm
                for b in range(2):
                    th = 2 * np.pi * self.rpm / 60.0 * t_l + self.phi[2 * q + b] + b * np.pi
                    off = ca[None, :] + 0.7 * self.blade * np.stack([np.cos(th), 0 * th, np.sin(th)], 1)
                    dr = off @ los
                    m += 0.22 * np.exp(1j * 4 * np.pi * dr / LAM).astype(np.complex64)
        if self.wing_hz:
            for b in range(2):
                dr = 0.04 * np.sin(2 * np.pi * self.wing_hz * t_l + b * np.pi)
                m += 0.30 * np.exp(1j * 4 * np.pi * dr / LAM).astype(np.complex64)
        return m


def scene():
    T = []
    # Phantom-4 class quad, inbound + crossing, climbing slightly
    T.append(Target("phantom4", "UAS-rotary", 0.02, sph(560, 20, 6), [-3.5, 0.6, -11.0], rotors=4, rpm=5600))
    # FPV racer, fast inbound, low
    T.append(Target("fpv", "UAS-rotary", 0.006, sph(360, -30, 3), [14.0, 0.2, -24.0], rotors=4, rpm=9000,
                    blade=0.065))
    # bird (gull), crossing
    T.append(Target("gull", "bird", 0.012, sph(280, 6, 11), [7.0, 0.4, 2.0], wing_hz=3.5))
    # static clutter: building, mast, ground patches
    for name, rcs, r, az, el in (("building", 300, 1100, -12, 0.5), ("mast", 40, 700, 35, 2.0),
                                 ("trees", 20, 450, -45, 0.3), ("berm", 15, 260, 15, -1.0),
                                 ("fence", 8, 150, -8, -2.0)):
        T.append(Target(name, "clutter", rcs, sph(r, az, el), [0, 0, 0]))
    return T


def snr_total(rcs, r):
    """Coherent SNR (linear) of one CPI over all 288 virtual channels."""
    db = staring_snr_db(pt_w=P.PT_TOTAL_W, g_tx_dbi=P.G_ELEM_DBI, g_rx_elem_dbi=P.G_ELEM_DBI,
                        n_rx=NRX, f_hz=F0, rcs_m2=rcs, r_m=r, t_coh_s=NL * T_PRI,
                        nf_db=P.NF_DB, loss_db=P.LOSS_DB - 3.6)   # processing losses applied by the DSP
    return 10 ** (db / 10)


def synth_frame(targets, t0, rng):
    n = np.arange(NS, dtype=np.float64) / FS
    l = np.arange(NL)
    t_l = t0 + l * T_PRI
    cube = (rng.standard_normal((NRX, NL, NS)) + 1j * rng.standard_normal((NRX, NL, NS))).astype(np.complex64)
    cube *= np.float32(np.sqrt(0.5))
    # TX->RX leakage (direct coupling, ~0.4 ns), strong but well below full scale
    tau_leak = 0.4e-9
    cube += np.complex64(25.0) * np.exp(1j * 2 * np.pi * (F0 * tau_leak + SLOPE * tau_leak * n)).astype(
        np.complex64)[None, None, :]
    for tg in targets:
        p = tg.pos(t_l[:, None])                                             # (NL, 3)
        r_mean = np.linalg.norm(tg.pos(t0))
        a = np.sqrt(snr_total(tg.rcs, r_mean) / (NS * NL * NTX * NRX))
        los = tg.pos(t0) / r_mean
        mod = tg.modulation(t_l, los)                                        # (NL,)
        d_rx = np.linalg.norm(p[:, None, :] - RX[None, :, :], axis=2)         # (NL, NRX)
        for k in range(NTX):
            d_tx = np.linalg.norm(p - TX[k][None, :], axis=1)                 # (NL,)
            tau = (d_tx[:, None] + d_rx) / C                                  # (NL, NRX)
            code = np.exp(1j * 2 * np.pi * k * l / NSUB)                      # DDMA slow-time code
            ph0 = (2 * np.pi * F0 * tau).astype(np.float64)
            beat = (2 * np.pi * SLOPE * tau)[:, :, None] * n[None, None, :]
            sig = np.exp(1j * (ph0[:, :, None] + beat)).astype(np.complex64)
            sig *= (a * code * mod)[:, None, None].astype(np.complex64)
            cube += sig.transpose(1, 0, 2)
    return cube


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=24)
    ap.add_argument("--period", type=float, default=0.1)
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rng = np.random.default_rng(7)
    targets = scene()
    scale = 8.5                                   # noise sigma ~6 LSB per I/Q (AD9083 back-off)
    path = os.path.join(a.out, "scenario.iq")
    truth = {"profile": "sim_long_range", "frame_period_s": a.period, "frames": []}
    with open(path, "wb") as fh:
        fh.write(struct.pack("<8sIIIIId", b"HG1IQ\0\0\0", 1, a.frames, NRX, NL, NS, a.period))
        for fi in range(a.frames):
            t0 = fi * a.period
            cube = synth_frame(targets, t0, rng)
            iq = np.empty((NRX, NL, NS, 2), np.int16)
            iq[..., 0] = np.clip(np.round(cube.real * scale), -32768, 32767)
            iq[..., 1] = np.clip(np.round(cube.imag * scale), -32768, 32767)
            fh.write(iq.tobytes())
            fr = []
            for tg in targets:
                p = tg.pos(t0)
                r = float(np.linalg.norm(p))
                fr.append({"name": tg.name, "kind": tg.kind, "rcs": tg.rcs,
                           # radar frame: x right, y boresight, z up
                           "x": float(p[0]), "y": float(p[2]), "z": float(p[1]), "r": r,
                           "az": float(np.degrees(np.arctan2(p[0], p[2]))),
                           "el": float(np.degrees(np.arcsin(p[1] / r))),
                           "vr": float(np.dot(tg.v, p) / r),
                           "snr_db": float(10 * np.log10(snr_total(tg.rcs, r)))})
            truth["frames"].append(fr)
            print(f"frame {fi:2d}  " + "  ".join(f"{d['name']}: r={d['r']:.0f} vr={d['vr']:+.1f} "
                                               f"snr={d['snr_db']:.1f}" for d in fr[:3]), flush=True)
    with open(os.path.join(a.out, "truth.json"), "w") as fh:
        json.dump(truth, fh, indent=1)
    print("wrote", path, os.path.getsize(path) / 1e6, "MB")


if __name__ == "__main__":
    main()

"""HoloGuard HG-1 system budget: detection range, accuracy, waveform,
power and mass budgets. Writes figures to analysis/figures and a JSON
summary consumed by the design documents.

Run:  python analysis/system_budget.py
"""
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import hg1_params as P  # noqa: E402
from radarlib import (C0, db, shnidman_snr_db, staring_snr_db, max_range_m,  # noqa: E402
                      angle_accuracy_deg)

FIG = os.path.join(HERE, "figures")
os.makedirs(FIG, exist_ok=True)

plt.rcParams.update({"font.size": 10, "axes.grid": True, "grid.alpha": 0.3,
                     "figure.dpi": 130, "savefig.bbox": "tight"})
COL = ["#2a6fdb", "#e0663a", "#1a9e77", "#8e5cc4", "#c9a227", "#5f6b7a"]

f0 = P.F0_GHZ * 1e9
lam = C0 / f0
t_cpi = P.CPI_CHIRPS * P.T_PRI_US * 1e-6
n_rx = P.RX_NX * P.RX_NY
n_tx = len(P.tx_positions())
n_virt = n_rx * n_tx

# ---------------------------------------------------------------- waveform
slope = P.BW_MHZ * 1e6 / (P.T_CHIRP_US * 1e-6)              # Hz/s
prf = 1.0 / (P.T_PRI_US * 1e-6)
wave = {
    "range_resolution_m": C0 / (2 * P.BW_MHZ * 1e6),
    "chirp_slope_MHz_per_us": slope / 1e12,
    "prf_kHz": prf / 1e3,
    "instrumented_range_m": P.IF_MAX_MHZ * 1e6 / slope * C0 / 2,
    "cpi_ms": t_cpi * 1e3,
    "window_ms": t_cpi * P.N_CPI_WINDOW * 1e3,
    # empty-band DDMA restores full-PRF unambiguous Doppler
    "v_unambiguous_mps": lam * prf / 4,
    "velocity_resolution_mps": lam / (2 * t_cpi),
    "ddma_subbands": n_tx + 2,
    "doppler_bins_per_cpi": P.CPI_CHIRPS,
    "range_bins": int(round(P.IF_MAX_MHZ * 1e6 * P.T_CHIRP_US * 1e-6)),
}
wave["data_rate_Gbps"] = (n_rx * 2 * P.IF_MAX_MHZ * 1e6 * 1.25 * 16) / 1e9  # IQ, 1.25x oversample, 16 b
wave["beamforming_TMACs"] = (wave["range_bins"] * P.CPI_CHIRPS * (32 * 16 / 2 * np.log2(32 * 16)) * 4
                             / t_cpi) / 1e12

# -------------------------------------------------------------- detection
PFA = 1e-6
req = {
    "pd90": shnidman_snr_db(0.9, PFA, P.N_CPI_WINDOW, 2),
    "pd50": shnidman_snr_db(0.5, PFA, P.N_CPI_WINDOW, 2),
}
common = dict(pt_w=P.PT_TOTAL_W, g_tx_dbi=P.G_ELEM_DBI, g_rx_elem_dbi=P.G_ELEM_DBI,
              n_rx=n_rx, f_hz=f0, t_coh_s=t_cpi, nf_db=P.NF_DB, loss_db=P.LOSS_DB)
SPOT_GAIN_DB = db(n_tx)      # coherent TX "spotlight" on a confirmed track

targets = [
    ("Micro FPV / Mini-3 (-25 dBsm)", 10 ** -2.5),
    ("Mavic-class (-20 dBsm)", 0.01),
    ("Phantom 4 (-17 dBsm)", 0.02),
    ("Matrice 600 (-10 dBsm)", 0.1),
    ("Fixed-wing Grp 2 (-3 dBsm)", 0.5),
    ("Walking human (0 dBsm)", 1.0),
    ("Vehicle (+10 dBsm)", 10.0),
]
ranges = []
for name, rcs in targets:
    r90 = max_range_m(req["pd90"], rcs_m2=rcs, **common)
    r50 = max_range_m(req["pd50"], rcs_m2=rcs, **common)
    r_spot = max_range_m(req["pd90"] - SPOT_GAIN_DB, rcs_m2=rcs, **common)
    ranges.append({"target": name, "rcs_m2": rcs, "R_pd90_m": r90, "R_pd50_m": r50,
                   "R_track_spotlight_m": r_spot})

# Long-range mode (B=50 MHz, 7.5 km instrumented, CPI 100 ms x 4)
req_lr = shnidman_snr_db(0.9, PFA, 4, 2)
lr = dict(common)
lr["t_coh_s"] = 0.1
r_vehicle_lr = max_range_m(req_lr, rcs_m2=10.0, **lr)
r_human_lr = max_range_m(req_lr, rcs_m2=1.0, **lr)

# ------------------------------------------------------- angle accuracy
virt = np.array(P.virtual_positions())
ap_x = virt[:, 0].max() - virt[:, 0].min() + P.D
ap_y = virt[:, 1].max() - virt[:, 1].min() + P.D
bw_az = np.degrees(0.886 * lam * 1e3 / ap_x) * 1.18      # Taylor -30 dB broadening
bw_el = np.degrees(0.886 * lam * 1e3 / ap_y) * 1.18
CAL_BIAS = 0.10                                          # deg, residual after OTA cal

# --------------------------------------------------------- power budget
power = [
    ("GaN PA x6 (1.0 W RF each, 30% PAE)", P.PT_TOTAL_W / 0.30),
    ("TX drivers / switches", 1.2),
    ("RX RFIC HRX-8 x6 (48 ch @ 75 mW)", 48 * 0.075),
    ("Chirp synth + LO distribution", 2.5),
    ("ADC AD9083 x6 (96 ch @ 50 mW)", 96 * 0.050),
    ("Versal AI Edge + LPDDR4 + flash", 9.5),
    ("Eth PHY, GNSS/IMU, MCU, RID rx", 1.5),
]
p_load = sum(p for _, p in power)
p_in = p_load / 0.92
power.append(("DC-DC conversion loss (92%)", p_in - p_load))

mass = [
    ("Housing (AlSi10Mg cast, finned)", 455),
    ("Radome (PC/ABS 1.0 mm)", 62),
    ("Antenna/RF PCB (hybrid RO4003C)", 118),
    ("RF shield / heat-spreader frame (Al)", 96),
    ("Digital PCB", 72),
    ("Power & I/O PCB", 28),
    ("Connectors (2x M12) + vent", 46),
    ("Gaskets, TIM, fasteners", 38),
]
m_total = sum(m for _, m in mass)

# ----------------------------------------------------------------- plots
# 1) SNR vs range
R = np.linspace(100, 4000, 400)
fig, ax = plt.subplots(figsize=(7.2, 4.2))
for (name, rcs), c in zip(targets[:5], COL):
    ax.plot(R / 1e3, staring_snr_db(rcs_m2=rcs, r_m=R, **common), color=c, label=name)
ax.axhline(req["pd90"], color="k", ls="--", lw=1)
ax.text(3.95, req["pd90"] + 0.6, f"Pd=0.9 / Pfa=1e-6, {P.N_CPI_WINDOW}-CPI window ({req['pd90']:.1f} dB)",
        ha="right", fontsize=8)
ax.axvline(1.0, color="#999", ls=":", lw=1)
ax.text(1.02, 33, "EchoGuard spec:\nPhantom 4 > 1 km", fontsize=8, color="#555")
ax.set(xlabel="Range (km)", ylabel="SNR per 50 ms CPI (dB)", ylim=(-10, 40),
       title="HG-1 staring (holographic) link budget, 16.0 GHz, 6 W GaN, 48 RX")
ax.legend(fontsize=8, loc="upper right")
fig.savefig(os.path.join(FIG, "snr_vs_range.png"))
plt.close(fig)

# 2) Range comparison vs EchoGuard
cmp_names = ["Phantom 4", "Matrice 600", "Human", "Vehicle"]
echo = [1.0, 1.4, 2.2, 3.5]
hg = [ranges[2]["R_pd90_m"] / 1e3, ranges[3]["R_pd90_m"] / 1e3, r_human_lr / 1e3, r_vehicle_lr / 1e3]
hg_spot = [ranges[2]["R_track_spotlight_m"] / 1e3, ranges[3]["R_track_spotlight_m"] / 1e3, None, None]
x = np.arange(len(cmp_names))
fig, ax = plt.subplots(figsize=(7.2, 3.8))
ax.bar(x - 0.27, echo, 0.27, color="#9aa5b1", label="Echodyne EchoGuard (datasheet, '>')")
ax.bar(x, hg, 0.27, color=COL[0], label="HG-1 detect (Pd 0.9)")
ax.bar(x[:2] + 0.27, [v for v in hg_spot[:2]], 0.27, color=COL[2], label="HG-1 track w/ GaN spotlight")
for xi, v in zip(x, hg):
    ax.text(xi, v + 0.08, f"{v:.1f}", ha="center", fontsize=8)
for xi, v in zip(x[:2], hg_spot[:2]):
    ax.text(xi + 0.27, v + 0.08, f"{v:.1f}", ha="center", fontsize=8)
for xi, v in zip(x, echo):
    ax.text(xi - 0.27, v + 0.08, f"{v:.1f}", ha="center", fontsize=8)
ax.set_xticks(x, cmp_names)
ax.set(ylabel="Range (km)", title="Detection / tracking range, same 16.3 x 20.3 x 5.7 cm envelope")
ax.legend(fontsize=8)
fig.savefig(os.path.join(FIG, "range_vs_echoguard.png"))
plt.close(fig)

# 3) Angle accuracy vs range (Phantom 4)
Rr = np.linspace(200, ranges[2]["R_pd90_m"], 200)
snr = staring_snr_db(rcs_m2=0.02, r_m=Rr, **common) + db(P.N_CPI_WINDOW)  # window-integrated
fig, ax = plt.subplots(figsize=(7.2, 3.6))
ax.plot(Rr / 1e3, angle_accuracy_deg(bw_az, snr, CAL_BIAS), color=COL[0], label="HG-1 azimuth")
ax.plot(Rr / 1e3, angle_accuracy_deg(bw_el, snr, CAL_BIAS), color=COL[1], label="HG-1 elevation")
ax.axhline(1.0, color=COL[0], ls="--", lw=1, alpha=0.6)
ax.axhline(1.5, color=COL[1], ls="--", lw=1, alpha=0.6)
ax.text(0.25, 1.03, "EchoGuard az spec < 1.0 deg", fontsize=8, color=COL[0])
ax.text(0.25, 1.53, "EchoGuard el spec < 1.5 deg", fontsize=8, color=COL[1])
ax.set(xlabel="Range (km)", ylabel="1-sigma measurement accuracy (deg)", ylim=(0, 1.8),
       title="Phantom-4 angle accuracy per 50 ms update (before track filtering)")
ax.legend(fontsize=8)
fig.savefig(os.path.join(FIG, "angle_accuracy.png"))
plt.close(fig)

# 4) Power budget
fig, ax = plt.subplots(figsize=(7.2, 3.4))
labels = [p[0] for p in power]
vals = [p[1] for p in power]
ax.barh(labels[::-1], vals[::-1], color=COL[0])
for i, v in enumerate(vals[::-1]):
    ax.text(v + 0.2, i, f"{v:.1f} W", va="center", fontsize=8)
ax.set(xlabel="W", title=f"DC power budget: {p_in:.1f} W input (EchoGuard: 50 W)")
ax.set_xlim(0, max(vals) * 1.25)
fig.savefig(os.path.join(FIG, "power_budget.png"))
plt.close(fig)

# 5) Time-on-target: staring vs scanning (illustrative)
fov_beams = (120 / 6.0) * (80 / 8.0)        # equivalent pencil beams in FoV
frame = 0.1
fig, ax = plt.subplots(figsize=(7.2, 2.6))
ax.barh(["Scanning ESA (1 beam at a time)", "HG-1 holographic (all beams at once)"],
        [frame / fov_beams * 1e3, t_cpi * 1e3 * P.N_CPI_WINDOW], color=["#9aa5b1", COL[0]])
ax.set_xscale("log")
ax.set(xlabel="Dwell on each target per 100 ms update (ms, log)",
       title=f"Time-on-target over a 120 x 80 deg FoV (~{fov_beams:.0f} beam positions)")
ax.text(frame / fov_beams * 1e3 * 1.1, 0, f"{frame / fov_beams * 1e3:.2f} ms", va="center", fontsize=8)
ax.text(1.0, 1, "400 ms coherent + diversity window, refreshed every 50 ms", va="center", fontsize=8,
        color="white")
fig.savefig(os.path.join(FIG, "time_on_target.png"))
plt.close(fig)

summary = {
    "n_rx": n_rx, "n_tx": n_tx, "n_virtual": n_virt,
    "lambda_mm": lam * 1e3,
    "virtual_aperture_mm": [ap_x, ap_y],
    "beamwidth_deg": [bw_az, bw_el],
    "waveform": wave,
    "snr_required_db": req,
    "ranges": ranges,
    "long_range_mode": {"vehicle_m": r_vehicle_lr, "human_m": r_human_lr},
    "spotlight_gain_db": SPOT_GAIN_DB,
    "power_W": {k: v for k, v in power}, "power_input_W": p_in,
    "mass_g": {k: v for k, v in mass}, "mass_total_g": m_total,
    "accuracy_at_1km_deg": [float(angle_accuracy_deg(bw_az, staring_snr_db(rcs_m2=0.02, r_m=1000, **common)
                                                     + db(P.N_CPI_WINDOW), CAL_BIAS)),
                            float(angle_accuracy_deg(bw_el, staring_snr_db(rcs_m2=0.02, r_m=1000, **common)
                                                     + db(P.N_CPI_WINDOW), CAL_BIAS))],
}
with open(os.path.join(HERE, "system_summary.json"), "w") as fh:
    json.dump(summary, fh, indent=2, default=float)

print(json.dumps({k: summary[k] for k in ("n_virtual", "virtual_aperture_mm", "beamwidth_deg",
                                          "snr_required_db", "power_input_W", "mass_total_g",
                                          "accuracy_at_1km_deg", "long_range_mode")},
                 indent=1, default=float))
print(json.dumps(wave, indent=1, default=float))
for r in ranges:
    print(f"{r['target']:32s} Pd.9 {r['R_pd90_m']:6.0f} m  Pd.5 {r['R_pd50_m']:6.0f} m  "
          f"spot {r['R_track_spotlight_m']:6.0f} m")

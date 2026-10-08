"""HoloGuard HG-1 antenna design.

* 6 TX x 48 RX MIMO layout -> 24 x 12 filled virtual (sum co-) array
* aperture-coupled stacked-patch element: first-cut dimensions
* embedded-element model, 3D (u,v) beam patterns, scan/grating-lobe check
* GaN coherent "spotlight" transmit pattern
Outputs: antenna/figures/*.png, antenna/element_positions.csv,
         antenna/element_design.json

Run:  python antenna/array_design.py
"""
import csv
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch
from scipy.signal.windows import taylor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import hg1_params as P  # noqa: E402

FIG = os.path.join(HERE, "figures")
os.makedirs(FIG, exist_ok=True)
plt.rcParams.update({"font.size": 9, "figure.dpi": 130, "savefig.bbox": "tight"})

C = 299.792458  # mm*GHz

# =====================================================================
# 1. Element: aperture-coupled stacked patch, H-polarised (E-plane = az)
# =====================================================================
ER_CORE = 3.55          # RO4003C design Dk
ER_PP = 3.52            # RO4450F prepreg
H_PAR = 1.016           # L1-L2 (parasitic above driven): 0.813 RO4003C + 0.203 RO4450F, EM-optimised
H_DRV = 0.508           # L2-L3 (driven above slotted ground)
H_FEED_TOP = 0.203      # L3-L4
H_FEED_BOT = 0.203      # L4-L5 (RO4450F 0.1 + RO4003C 0.1)
T_CU = 0.018


def patch_length(f_ghz, er, h, w):
    eeff = (er + 1) / 2 + (er - 1) / 2 * (1 + 12 * h / w) ** -0.5
    dl = 0.412 * h * (eeff + 0.3) * (w / h + 0.264) / ((eeff - 0.258) * (w / h + 0.8))
    return C / (2 * f_ghz * np.sqrt(eeff)) - 2 * dl, eeff


def stripline_z0(w, b, t, er):
    """Cohn/Wheeler thin-strip stripline approximation."""
    weff = w + t / np.pi * (1 + np.log(4 * np.pi * w / t)) if t > 0 else w
    return 60 / np.sqrt(er) * np.log(4 * b / (0.67 * np.pi * weff * (0.8 + t / w)))


f0 = P.F0_GHZ
lam0 = C / f0
w_drv = 5.0
l_single, eeff = patch_length(f0, ER_CORE, H_DRV, w_drv)
# Stacked patch: driven ~4% shorter, parasitic ~6% longer than a single
# resonator; the two coupled resonances straddle f0 for ~12 % VSWR<2 BW.
l_drv_analytic = 0.96 * l_single
l_par_analytic = 1.06 * l_single
w_par = 5.6
# Full-wave (EMerge FEM, infinite-array unit cell with the element via-fence cavity) optimised
# dimensions, docs/06_EM_Simulation.md. The superstrate-loaded patches resonate far lower than
# the closed-form estimate above, so these replace it.
EM = {"drv_l": 3.21, "par_l": 4.48, "slot_l": 3.02, "arm_l": 2.14, "stub": 1.50}
l_drv = EM["drv_l"]
l_par = EM["par_l"]
b = H_FEED_TOP + H_FEED_BOT
er_strip = (ER_CORE + ER_PP) / 2
ws = np.linspace(0.05, 0.4, 400)
z = np.array([stripline_z0(w, b, T_CU, er_strip) for w in ws])
w50 = float(ws[np.argmin(abs(z - 50))])
lam_g_strip = lam0 / np.sqrt(er_strip)
element = {
    "polarisation": "linear horizontal (E-plane = azimuth)",
    "type": "aperture-coupled stacked patch, H-slot (dogbone), stripline fed",
    "f0_GHz": f0,
    "band_GHz": [P.F_LO_GHZ, P.F_HI_GHZ],
    "lambda0_mm": lam0,
    "pitch_mm": P.D,
    "pitch_over_lambda_at_fmax": P.D / (C / P.F_HI_GHZ),
    "single_patch_eeff": eeff,
    "driven_patch_LxW_mm": [round(l_drv, 2), w_drv],
    "parasitic_patch_LxW_mm": [round(l_par, 2), w_par],
    "slot": {"length_mm": EM["slot_l"], "width_mm": 0.30, "end_arms_mm": [EM["arm_l"], 0.30]},
    "stub_beyond_slot_mm": EM["stub"],
    "analytic_start": {"driven_l_mm": round(l_drv_analytic, 2), "parasitic_l_mm": round(l_par_analytic, 2),
                       "slot_l_mm": 3.3, "arm_l_mm": 1.2, "stub_mm": round(0.21 * lam_g_strip, 2),
                       "h_par_mm": 0.813},
    "element_fence": "blind L1-L5 GND via rows on every cell boundary, 1.0 mm pitch",
    "stripline_50ohm_width_mm": round(w50, 3),
    "stripline_ground_spacing_mm": b,
    "lambda_g_stripline_mm": lam_g_strip,
    "layer_heights_mm": {"L1-L2 parasitic gap RO4003C": H_PAR, "L2-L3 driven RO4003C": H_DRV,
                         "L3-L4 RO4003C": H_FEED_TOP, "L4-L5 RO4450F+RO4003C": H_FEED_BOT},
    "embedded_pattern_model": "E-plane cos^0.9, H-plane cos^1.3 (power), 4.7 dBi RX / 5.5 dBi TX",
    "target_bandwidth_vswr2": "15.1-16.9 GHz (11 %) incl. +/-60 deg az active-match",
    "em_result": "active |S11| < -10 dB over >= 0.52 GHz centred ~16.0-16.1 GHz at every scan to "
                 "60 deg az / 40 deg el / 45 deg diagonal; -5.6 to -8.6 dB at the 15.5/16.5 GHz "
                 "allocation edges (covers the 250 MHz chirp anywhere in ~15.7-16.3 GHz)",
}
with open(os.path.join(HERE, "element_design.json"), "w") as fh:
    json.dump(element, fh, indent=2)


def element_pattern(theta_az, theta_el):
    """Power pattern of the embedded element; angles in radians in a
    az-over-el (u = sin az cos el, v = sin el) sense."""
    return np.clip(np.cos(theta_az), 0, None) ** 0.9 * np.clip(np.cos(theta_el), 0, None) ** 1.3


# =====================================================================
# 2. Layout
# =====================================================================
rx = np.array(P.rx_positions())
tx = np.array(P.tx_positions())
virt = np.array(P.virtual_positions())

with open(os.path.join(HERE, "element_positions.csv"), "w", newline="") as fh:
    wr = csv.writer(fh)
    wr.writerow(["name", "role", "x_mm", "y_mm", "channel"])
    for k, (x, y) in enumerate(tx):
        wr.writerow([f"TX{k + 1}", "TX", f"{x:.3f}", f"{y:.3f}", f"PA{k + 1}"])
    for k, (x, y) in enumerate(rx):
        wr.writerow([f"RX{k + 1:02d}", "RX", f"{x:.3f}", f"{y:.3f}",
                     f"HRX{k // 8 + 1}.CH{k % 8 + 1}"])

fig, axs = plt.subplots(1, 2, figsize=(10.5, 6.2), gridspec_kw={"width_ratios": [1, 1.25]})
ax = axs[0]
ax.add_patch(FancyBboxPatch((-P.ANT_PCB_W / 2, -P.ANT_PCB_H / 2), P.ANT_PCB_W, P.ANT_PCB_H,
                            boxstyle="round,pad=0,rounding_size=4", fc="#f3efe2", ec="#8a7d55"))
ax.add_patch(Rectangle((-P.ANT_PCB_W / 2 + 3, P.FENCE_Y - 1.5), P.ANT_PCB_W - 6, 3, fc="#555",
                       ec="none"))
ax.text(0, P.FENCE_Y + 3, "choke fence + absorber (TX/RX isolation >= 60 dB)", ha="center",
        fontsize=7)
for (x, y) in rx:
    ax.add_patch(Rectangle((x - l_par / 2, y - w_par / 2), l_par, w_par, fc="#2a6fdb", ec="k",
                           lw=0.3))
for k, (x, y) in enumerate(tx):
    ax.add_patch(Rectangle((x - l_par / 2, y - w_par / 2), l_par, w_par, fc="#e0663a", ec="k",
                           lw=0.3))
    ax.text(x, y + 6, f"TX{k + 1}", ha="center", fontsize=7)
ax.add_patch(Rectangle((-17, 25), 34, 34, fc="#c9a227", ec="k", lw=0.4, alpha=0.8))
ax.text(0, 42, "Remote-ID /\n2.4-5.8 GHz\nRF-detect", ha="center", va="center", fontsize=6.5)
ax.add_patch(Rectangle((-4, -8), 8, 8, fc="#1a9e77", ec="k", lw=0.4))
ax.text(0, -12.5, "OTA cal probe", ha="center", fontsize=6.5)
ax.text(0, -86, "RX: 12 x 4 = 48 (HRX-8 RFIC x6)", ha="center", fontsize=7, color="#2a6fdb")
ax.set(xlim=(-80, 80), ylim=(-100, 100), aspect="equal", xlabel="x / azimuth (mm)",
       ylabel="y / elevation (mm)", title=f"Physical aperture {P.ANT_PCB_W:.0f} x {P.ANT_PCB_H:.0f} mm")

ax = axs[1]
ax.scatter(virt[:, 0], virt[:, 1], s=14, c="#8e5cc4", marker="s", label="virtual element (288)")
ax.scatter(rx[:, 0], rx[:, 1], s=6, c="#2a6fdb", label="RX (48)")
ax.scatter(tx[:, 0], tx[:, 1], s=30, c="#e0663a", marker="^", label="TX (6)")
ax.add_patch(Rectangle((-P.ENV_W / 2, -P.ENV_H / 2), P.ENV_W, P.ENV_H, fill=False, ls="--",
                       ec="#777"))
ax.text(-P.ENV_W / 2 + 2, P.ENV_H / 2 - 7, "housing outline", fontsize=7, color="#777")
ap = (virt.max(0) - virt.min(0)) + P.D
ax.set(aspect="equal", xlabel="mm", title=f"Sum co-array: 24 x 12 filled lambda/2 grid, "
       f"{ap[0]:.0f} x {ap[1]:.0f} mm\n(az aperture larger than the housing)")
ax.legend(fontsize=7, loc="upper right")
fig.savefig(os.path.join(FIG, "array_layout.png"))
plt.close(fig)

# =====================================================================
# 3. Beam patterns (virtual array, Taylor -35/-30 dB)
# =====================================================================
vx = np.sort(np.unique(np.round(virt[:, 0], 3)))
vy = np.sort(np.unique(np.round(virt[:, 1], 3)))
wx = taylor(len(vx), nbar=4, sll=35, norm=False)
wy = taylor(len(vy), nbar=4, sll=30, norm=False)
WX = dict(zip(vx, wx))
WY = dict(zip(vy, wy))
wv = np.array([WX[round(x, 3)] * WY[round(y, 3)] for x, y in virt])


def array_factor(pos, w, f_ghz, u, v, u0=0.0, v0=0.0):
    k = 2 * np.pi * f_ghz / C
    ph = k * (np.outer(u - u0, pos[:, 0]) + np.outer(v - v0, pos[:, 1]))
    return np.abs(np.exp(1j * ph) @ w) / np.sum(np.abs(w))


def uv_from_azel(az, el):
    return np.sin(az) * np.cos(el), np.sin(el)


def cut(f_ghz, az0, el0, plane):
    a = np.radians(np.linspace(-90, 90, 1441))
    u0, v0 = uv_from_azel(np.radians(az0), np.radians(el0))
    if plane == "az":
        u, v = uv_from_azel(a, np.radians(el0) * np.ones_like(a))
        ep = element_pattern(a, np.radians(el0))
    else:
        u, v = uv_from_azel(np.radians(az0) * np.ones_like(a), a)
        ep = element_pattern(np.radians(az0), a)
    af = array_factor(virt, wv, f_ghz, u, v, u0, v0)
    return np.degrees(a), 20 * np.log10(af + 1e-9) + 10 * np.log10(ep + 1e-12)


fig, axs = plt.subplots(1, 2, figsize=(11, 3.8))
for az0, c in zip((0, 30, 60), ("#2a6fdb", "#1a9e77", "#e0663a")):
    a, g = cut(f0, az0, 0, "az")
    axs[0].plot(a, g, color=c, lw=1, label=f"steer az {az0} deg")
for el0, c in zip((0, 20, 40), ("#2a6fdb", "#1a9e77", "#e0663a")):
    a, g = cut(f0, 0, el0, "el")
    axs[1].plot(a, g, color=c, lw=1, label=f"steer el {el0} deg")
for ax, t in zip(axs, ("Azimuth cut (24-element virtual, Taylor -35 dB)",
                       "Elevation cut (12-element virtual, Taylor -30 dB)")):
    ax.set(ylim=(-60, 2), xlim=(-90, 90), xlabel="angle (deg)", ylabel="normalised two-way gain (dB)",
           title=t)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7)
fig.savefig(os.path.join(FIG, "beam_cuts.png"))
plt.close(fig)

# 2-D (u,v) pattern, steered to (az 35, el 20) at band edge 16.7 GHz
N = 361
uu, vv = np.meshgrid(np.linspace(-1, 1, N), np.linspace(-1, 1, N))
mask = uu ** 2 + vv ** 2 <= 1
u0, v0 = uv_from_azel(np.radians(35), np.radians(20))
af = np.full(uu.shape, np.nan)
af[mask] = 20 * np.log10(array_factor(virt, wv, P.F_HI_GHZ, uu[mask], vv[mask], u0, v0) + 1e-9)
fig, ax = plt.subplots(figsize=(5.4, 4.8))
im = ax.imshow(af, extent=(-1, 1, -1, 1), origin="lower", vmin=-50, vmax=0, cmap="viridis")
fov_az = np.radians(np.linspace(-60, 60, 100))
for el in (-40, 40):
    uf, vf = uv_from_azel(fov_az, np.radians(el) * np.ones_like(fov_az))
    ax.plot(uf, vf, "w--", lw=0.8)
for az in (-60, 60):
    eln = np.radians(np.linspace(-40, 40, 50))
    ue, ve = uv_from_azel(np.radians(az) * np.ones_like(eln), eln)
    ax.plot(ue, ve, "w--", lw=0.8)
ax.set(xlabel="u = sin(az)cos(el)", ylabel="v = sin(el)",
       title="3D beam at 16.5 GHz steered (35, 20) deg\nno grating lobes in visible space")
fig.colorbar(im, ax=ax, label="dB")
fig.savefig(os.path.join(FIG, "beam_uv_map.png"))
plt.close(fig)

# Beamwidths / sidelobes at broadside
a, g = cut(f0, 0, 0, "az")
bw_az = np.ptp(a[g > g.max() - 3])
a2, g2 = cut(f0, 0, 0, "el")
bw_el = np.ptp(a2[g2 > g2.max() - 3])


def peak_sll(a, g, bw):
    main = np.abs(a) < bw * 1.4
    return float((g[~main]).max() - g.max())


patterns = {
    "beamwidth_az_deg": float(bw_az), "beamwidth_el_deg": float(bw_el),
    "psll_az_dB": peak_sll(a, g, bw_az), "psll_el_dB": peak_sll(a2, g2, bw_el),
    "grating_lobe_free_scan_deg_at_fmax": float(np.degrees(np.arcsin(min(1.0, C / P.F_HI_GHZ / P.D - 1)))),  # 90 = never
    "n_beams_fft": [32, 16],
    "rx_coherent_gain_dBi": 4.7 + 10 * np.log10(len(rx)),
}

# =====================================================================
# 4. GaN spotlight: 6 TX phased coherently on a confirmed track
# =====================================================================
a = np.radians(np.linspace(-90, 90, 2001))
fig, axs = plt.subplots(1, 2, figsize=(11, 3.4))
for ax, plane in zip(axs, ("az", "el")):
    if plane == "az":
        u, v = uv_from_azel(a, 0 * a)
        u0, v0 = uv_from_azel(np.radians(20), 0)
        ep = element_pattern(a, 0)
    else:
        u, v = uv_from_azel(0 * a, a)
        u0, v0 = uv_from_azel(0, np.radians(10))
        ep = element_pattern(0, a)
    k = 2 * np.pi * f0 / C
    afc = np.abs(np.exp(1j * k * (np.outer(u - u0, tx[:, 0]) + np.outer(v - v0, tx[:, 1]))).sum(1))
    gain_coh = 10 * np.log10(afc ** 2 / len(tx) * ep + 1e-12) + 5.5  # dBi, total power fixed
    ax.plot(np.degrees(a), gain_coh, color="#e0663a", lw=1, label="spotlight (coherent 6 TX)")
    ax.plot(np.degrees(a), 10 * np.log10(ep + 1e-12) + 5.5, color="#2a6fdb", lw=1,
            label="holographic (orthogonal DDMA)")
    ax.set(ylim=(-15, 16), xlim=(-90, 90), xlabel=f"{plane} (deg)", ylabel="TX gain (dBi)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7)
axs[0].set_title("Spotlight on track at az 20 deg: +7.8 dB on target")
axs[1].set_title("Spotlight on track at el 10 deg")
fig.savefig(os.path.join(FIG, "spotlight_tx.png"))
plt.close(fig)

# =====================================================================
# 5. Embedded element pattern (model)
# =====================================================================
th = np.linspace(-90, 90, 361)
fig, ax = plt.subplots(figsize=(5.6, 3.2))
ax.plot(th, 4.7 + 10 * np.log10(element_pattern(np.radians(th), 0) + 1e-9), label="E-plane (az)")
ax.plot(th, 4.7 + 10 * np.log10(element_pattern(0, np.radians(th)) + 1e-9), label="H-plane (el)")
ax.axvspan(-60, 60, color="#2a6fdb", alpha=0.07)
ax.axvspan(-40, 40, color="#e0663a", alpha=0.07)
ax.set(ylim=(-15, 8), xlabel="angle (deg)", ylabel="realised gain (dBi)",
       title="Embedded element pattern (design target)")
ax.grid(alpha=0.3)
ax.legend(fontsize=7)
fig.savefig(os.path.join(FIG, "element_pattern.png"))
plt.close(fig)

# =====================================================================
# 6. Element cross-section / top view drawing
# =====================================================================
fig, axs = plt.subplots(1, 2, figsize=(10, 3.6), gridspec_kw={"width_ratios": [1, 1.4]})
ax = axs[0]
cell = P.D
ax.add_patch(Rectangle((-cell / 2, -cell / 2), cell, cell, fc="#f3efe2", ec="#aaa"))
ax.add_patch(Rectangle((-l_par / 2, -w_par / 2), l_par, w_par, fc="none", ec="#e0663a", lw=1.4,
                       label=f"parasitic {l_par:.2f} x {w_par:.1f}"))
ax.add_patch(Rectangle((-l_drv / 2, -w_drv / 2), l_drv, w_drv, fc="#c9a22755", ec="#c9a227", lw=1.2,
                       label=f"driven {l_drv:.2f} x {w_drv:.1f}"))
sl = element["slot"]
ax.add_patch(Rectangle((-sl["width_mm"] / 2, -sl["length_mm"] / 2), sl["width_mm"], sl["length_mm"],
                       fc="k"))
for s in (-1, 1):
    ax.add_patch(Rectangle((-sl["end_arms_mm"][0] / 2, s * sl["length_mm"] / 2 - 0.15),
                           sl["end_arms_mm"][0], 0.3, fc="k"))
stub = element["stub_beyond_slot_mm"]
ax.add_patch(Rectangle((-cell / 2, -w50 / 2), cell / 2 + stub, w50, fc="#2a6fdb", ec="none",
                       label=f"50 ohm stripline w={w50:.2f}, stub {stub:.2f}"))
ax.set(xlim=(-5, 5), ylim=(-5, 5), aspect="equal", title=f"Unit cell {cell:.1f} mm (top view)",
       xlabel="x (az, E-field) mm", ylabel="y mm")
ax.legend(fontsize=6.5, loc="lower left")

ax = axs[1]
layers = [("L1 parasitic patch", 0.035, "#c87f33"), ("RO4003C", H_PAR, "#e9dfb8"),
          ("L2 driven patch", 0.035, "#c87f33"), ("RO4003C", H_DRV, "#e9dfb8"),
          ("L3 GND + H-slot", 0.035, "#c87f33"), ("RO4003C", H_FEED_TOP, "#e9dfb8"),
          ("L4 stripline feed", 0.035, "#c87f33"), ("RO4450F/RO4003C", H_FEED_BOT, "#e9dfb8"),
          ("L5 GND", 0.035, "#c87f33"), ("FR-4 370HR (L5-L8)", 0.9, "#a9c28a"),
          ("L9/L10 RO4350B + RFIC side", 0.17, "#e9dfb8")]
y = 0
for name, t, col in layers:
    ax.add_patch(Rectangle((0, y - t), 10, t, fc=col, ec="k", lw=0.3))
    ax.text(10.3, y - t / 2, f"{name}  {t:.3f} mm", va="center", fontsize=6.8)
    y -= max(t, 0.035)
ax.set(xlim=(0, 22), ylim=(y - 0.1, 0.2), title="Hybrid stack-up (antenna side up)")
ax.axis("off")
fig.savefig(os.path.join(FIG, "element_geometry.png"))
plt.close(fig)

out = {"element": element, "patterns": patterns,
       "n_tx": len(tx), "n_rx": len(rx), "n_virtual": len(virt),
       "virtual_aperture_mm": ap.tolist()}
with open(os.path.join(HERE, "antenna_summary.json"), "w") as fh:
    json.dump(out, fh, indent=2, default=float)
print(json.dumps(out, indent=1, default=float))

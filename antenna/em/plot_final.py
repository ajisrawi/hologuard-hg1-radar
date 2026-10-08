"""Figures for docs/06_EM_Simulation.md from antenna/em/results.

  python antenna/em/plot_final.py
-> antenna/em/results/final_scan_s11.png, final_optimisation.png, final_pattern.png (if isolated_final exists)
"""
import csv
import json
import os

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
SCANS = [(0, 0), (20, 0), (30, 0), (40, 0), (50, 0), (60, 0), (20, 90), (40, 90), (45, 45)]


def load(name):
    with open(os.path.join(RES, name + ".json")) as fh:
        return json.load(fh)


def scan_plot():
    fig, axs = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    cm = plt.get_cmap("viridis")
    for th, ph in SCANS:
        d = load(f"periodic_final_t{th}_p{ph}")
        ax = axs[0] if ph == 0 else axs[1]
        c = cm(th / 60) if ph == 0 else ({20: "tab:orange", 40: "tab:red"}[th] if ph == 90 else "tab:purple")
        ls = "-" if ph != 45 else "--"
        lbl = f"{th} deg az" if ph == 0 else (f"{th} deg el" if ph == 90 else f"{th} deg diagonal")
        ax.plot(d["raw_freq_GHz"], d["raw_s11_db"], ls, color=c, marker="o", ms=3, label=lbl)
    for ax, t in zip(axs, ("E-plane (azimuth) scan", "H-plane (elevation) and diagonal scan")):
        ax.axhline(-10, color="k", lw=0.6, ls=":")
        ax.axvspan(15.5, 16.5, color="tab:green", alpha=0.08)
        ax.axvspan(15.875, 16.125, color="tab:green", alpha=0.15)
        ax.set(xlabel="Frequency (GHz)", title=t, ylim=(-30, 0), xlim=(15, 17))
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7)
    axs[0].set_ylabel("Active |S11| (dB)")
    fig.suptitle("HG-1 element in the infinite 9 mm array (EMerge FEM, Floquet port, via-fence cavity)\n"
                 "light band: 15.5-16.5 GHz allocation; dark band: one 250 MHz chirp at 16 GHz", fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "final_scan_s11.png"), dpi=130)


def opt_plot():
    rows = list(csv.DictReader(open(os.path.join(RES, "optm_log.csv"))))
    rows = [r for r in rows if r["gen"] != "gen"]
    g = np.array([int(r["gen"]) for r in rows])
    c = np.array([float(r["cost_dB"]) for r in rows])
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.scatter(g + np.random.default_rng(0).uniform(-0.2, 0.2, g.size), c, s=8, alpha=0.5, label="candidate")
    best = [c[g <= k].min() for k in range(g.max() + 1)]
    ax.plot(range(g.max() + 1), best, "r-o", ms=4, label="best so far")
    ax.set(xlabel="generation (24 candidates each, 3 scan angles per candidate)",
           ylabel="worst-angle mean in-band |S11|^2 (dB)", ylim=(-12, 2),
           title="Differential evolution on Modal\n(72 parallel FEM solves per generation)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "final_optimisation.png"), dpi=130)


def pattern_plot():
    p = os.path.join(RES, "isolated_final.json")
    if not os.path.exists(p):
        return
    d = load("isolated_final")
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.8))
    for name, v in d["farfield_16GHz"].items():
        axs[0].plot(v["ang_deg"], v["gain_dbi"], label=name.replace("_", " "))
    axs[0].set(xlabel="angle from broadside (deg)", ylabel="realised gain (dBi)", xlim=(-180, 180), ylim=(-25, 10),
               title="Single element on 24 mm board, 16 GHz")
    axs[0].grid(alpha=0.3)
    axs[0].legend(fontsize=8)
    axs[1].plot(d["raw_freq_GHz"], d["raw_s11_db"], "o-", ms=3)
    axs[1].axhline(-10, color="k", lw=0.6, ls=":")
    axs[1].axvspan(15.5, 16.5, color="tab:green", alpha=0.08)
    axs[1].set(xlabel="Frequency (GHz)", ylabel="|S11| (dB)", title="Isolated element (TX case)", ylim=(-30, 0))
    axs[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "final_pattern.png"), dpi=130)


if __name__ == "__main__":
    scan_plot()
    opt_plot()
    pattern_plot()
    print("figures written to", RES)

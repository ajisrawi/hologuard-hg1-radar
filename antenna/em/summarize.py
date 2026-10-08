"""Tabulate and plot the EMerge element runs in antenna/em/results.

  python antenna/em/summarize.py                      # table of every run
  python antenna/em/summarize.py --plot V X AD        # |S11| plot of selected tags -> results/s11_<tags>.png
"""
import argparse
import glob
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
KEYS = ("drv_l", "par_l", "slot_l", "arm_l", "stub", "par_on")


def load(path):
    with open(path) as fh:
        d = json.load(fh)
    f = np.asarray(d["freq_GHz"])
    s = np.asarray(d["s11_db"])
    bw = f[s < -10]
    return d, f, s, (bw.min(), bw.max()) if bw.size else None


def table():
    print(f"{'run':34s} " + " ".join(f"{k:>7s}" for k in KEYS) + "   min dB @ GHz     -10 dB band")
    for p in sorted(glob.glob(os.path.join(RES, "*.json")), key=os.path.getmtime):
        d, f, s, bw = load(p)
        g = d["geom"]
        i = int(np.argmin(s))
        band = f"{bw[0]:.2f}-{bw[1]:.2f}" if bw else "-"
        print(f"{os.path.basename(p)[:-5]:34s} " + " ".join(f"{g.get(k, 1):7.2f}" for k in KEYS)
              + f"   {s[i]:6.1f} @ {f[i]:5.2f}   {band}")


def plot(tags):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 4))
    for t in tags:
        p = next(iter(glob.glob(os.path.join(RES, f"*_{t}_*.json")) + glob.glob(os.path.join(RES, f"*_{t}.json"))))
        d, f, s, _ = load(p)
        ax.plot(f, s, label=os.path.basename(p)[:-5])
    ax.axhline(-10, color="k", lw=0.6, ls="--")
    ax.axvspan(15.5, 16.5, color="tab:green", alpha=0.1, label="HG-1 band")
    ax.set(xlabel="Frequency (GHz)", ylabel="|S11| (dB)", ylim=(-30, 0), title="HG-1 element, EMerge FEM")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7)
    out = os.path.join(RES, "s11_" + "_".join(tags) + ".png")
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    print(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--plot", nargs="*")
    a = ap.parse_args()
    if a.plot:
        plot(a.plot)
    else:
        table()

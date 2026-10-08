"""Nelder-Mead tuning of the HG-1 element in the infinite-array unit cell (broadside).

Cost = mean in-band reflected power 10*log10(mean |S11|^2) over 15.5-16.5 GHz (fitted curve and
raw solver points), evaluated
by running element_em.py periodic in a subprocess (one ~1 min FEM solve per evaluation).

  .venv/Scripts/python antenna/em/optimize.py --maxev 60 --set h_par=1.524
Log: antenna/em/results/opt_log.csv, best: antenna/em/results/opt_best.json
"""
import argparse
import csv
import json
import os
import subprocess
import sys

import numpy as np
from scipy.optimize import minimize

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
VARS = {  # name: (start, lo, hi)
    "drv_l": (3.6, 2.4, 4.6),
    "par_l": (4.6, 3.4, 5.6),
    "slot_l": (3.6, 2.0, 4.6),
    "arm_l": (1.0, 0.3, 2.2),
    "stub": (2.5, 1.5, 3.2),
}
BAND = (15.5, 16.5)


def evaluate(x, fixed, n, log):
    g = {k: float(np.clip(v, VARS[k][1], VARS[k][2])) for k, v in zip(VARS, x)}
    sets = [f"{k}={v:.3f}" for k, v in {**fixed, **g}.items()]
    tag = f"_opt{n:03d}"
    cmd = [sys.executable, os.path.join(HERE, "element_em.py"), "periodic", "--nf", "9", "--f1", "15",
           "--f2", "17", "--tag", tag, "--set", *sets]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with open(os.path.join(RES, f"periodic{tag}_t0_p0.json")) as fh:
            d = json.load(fh)
    except FileNotFoundError:
        return 0.0, g
    f, s = np.asarray(d["freq_GHz"]), np.asarray(d["s11_db"])
    fr, sr = np.asarray(d["raw_freq_GHz"]), np.asarray(d["raw_s11_db"])
    inb = (f >= BAND[0]) & (f <= BAND[1])
    inr = (fr >= BAND[0]) & (fr <= BAND[1])
    # mean reflected power in band (smooth; rewards spreading the match) + raw-point check so a
    # rational-fit artefact cannot fake a deep notch
    gam2 = np.concatenate([10 ** (s[inb] / 10), 10 ** (sr[inr] / 10)])
    cost = 10 * np.log10(gam2.mean())
    # penalty for leaving the box keeps the simplex inside the manufacturable range
    cost += 5 * sum(max(0, VARS[k][1] - v) + max(0, v - VARS[k][2]) for k, v in zip(VARS, x))
    log.writerow([n, *[f"{g[k]:.3f}" for k in VARS], f"{cost:.2f}"])
    return cost, g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--maxev", type=int, default=60)
    ap.add_argument("--set", nargs="*", default=[])
    ap.add_argument("--x0", nargs="*", default=[], help="override start values k=v")
    ap.add_argument("--steps", nargs=5, default=[0.25, 0.3, 0.4, 0.3, 0.3], help="initial simplex steps (mm)")
    a = ap.parse_args()
    fixed = {kv.split("=")[0]: float(kv.split("=")[1]) for kv in a.set}
    x0 = {k: v[0] for k, v in VARS.items()}
    x0.update({kv.split("=")[0]: float(kv.split("=")[1]) for kv in a.x0})
    best = {"cost": 1e9}
    n = [0]
    with open(os.path.join(RES, "opt_log.csv"), "a", newline="") as fh:
        log = csv.writer(fh)
        log.writerow(["n", *VARS, "cost_dB"])

        def fun(x):
            n[0] += 1
            c, g = evaluate(x, fixed, n[0], log)
            fh.flush()
            print(f"eval {n[0]:3d} " + " ".join(f"{k}={v:.3f}" for k, v in g.items()) + f"  cost {c:6.2f} dB",
                  flush=True)
            if c < best["cost"]:
                best.update(cost=c, geom={**fixed, **g}, eval=n[0])
                with open(os.path.join(RES, "opt_best.json"), "w") as fb:
                    json.dump(best, fb, indent=1)
            return c

        steps = np.array([float(s) for s in a.steps])
        x = np.array([x0[k] for k in VARS])
        simplex = np.vstack([x] + [x + np.eye(len(x))[i] * steps[i] for i in range(len(x))])
        minimize(fun, x, method="Nelder-Mead",
                 options={"maxfev": a.maxev, "initial_simplex": simplex, "xatol": 0.03, "fatol": 0.3})
    print("BEST", json.dumps(best), flush=True)


if __name__ == "__main__":
    main()

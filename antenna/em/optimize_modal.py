"""Parallel element optimisation on Modal: differential evolution, one container per candidate.

Every generation's population is solved at once (big-CPU containers, frequency points in parallel,
finer mesh than the laptop runs). Cost as in optimize.py: 10*log10(mean |S11|^2) over 15.5-16.5 GHz
in the infinite-array unit cell at broadside; --scan adds the worst of extra scan angles.

  .venv/Scripts/python antenna/em/optimize_modal.py --popsize 5 --maxiter 12 --res 0.16 \
      --set h_par=1.524 --x0 drv_l=3.0 par_l=4.25 slot_l=4.088 arm_l=1.6 stub=2.772
Log: results/optm_log.csv, best: results/optm_best.json, all candidate JSONs: results/optm/
"""
import argparse
import csv
import json
import os

import modal
import numpy as np
from scipy.optimize import differential_evolution

from modal_em import FUNCS, app

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
OUT = os.path.join(RES, "optm")
VARS = {"drv_l": (2.4, 4.4), "par_l": (3.4, 5.6), "slot_l": (2.4, 4.8), "arm_l": (0.3, 2.2), "stub": (1.5, 3.4),
        "h_par": (0.8, 1.6)}
# parasitic spacer is built from RO4003C cores (+ thin prepreg): snap to buildable stacks
H_PAR_STACKS = (0.813, 1.016, 1.219, 1.524)
BAND = (15.5, 16.5)


def snap(name, v):
    return min(H_PAR_STACKS, key=lambda h: abs(h - v)) if name == "h_par" else v


def band_cost(d):
    f, s = np.asarray(d["freq_GHz"]), np.asarray(d["s11_db"])
    fr, sr = np.asarray(d["raw_freq_GHz"]), np.asarray(d["raw_s11_db"])
    gam2 = np.concatenate([10 ** (s[(f >= BAND[0]) & (f <= BAND[1])] / 10),
                           10 ** (sr[(fr >= BAND[0]) & (fr <= BAND[1])] / 10)])
    return float(10 * np.log10(gam2.mean()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--popsize", type=int, default=5)
    ap.add_argument("--maxiter", type=int, default=12)
    ap.add_argument("--res", type=float, default=0.16)
    ap.add_argument("--nf", type=int, default=11)
    ap.add_argument("--scan", nargs="*", default=[], help="extra scan angles theta:phi, e.g. 45:0 40:90")
    ap.add_argument("--set", nargs="*", default=[])
    ap.add_argument("--x0", nargs="*", default=[])
    ap.add_argument("--kind", default="mid", help="Modal container type (big/mid/a100/l4)")
    ap.add_argument("--fix", nargs="*", default=[], help="optimisation variables to hold at their --x0 value")
    a = ap.parse_args()
    for k in a.fix:
        VARS.pop(k)
    run_fn = FUNCS[a.kind]
    fixed = dict(kv.split("=") for kv in a.set)
    x0d = {k: float(v) for k, v in (kv.split("=") for kv in a.x0)}
    os.makedirs(OUT, exist_ok=True)
    angles = [(0.0, 0.0)] + [tuple(float(t) for t in s.split(":")) for s in a.scan]
    state = {"gen": 0, "best": 1e9}
    logf = open(os.path.join(RES, "optm_log.csv"), "a", newline="")
    log = csv.writer(logf)
    log.writerow(["gen", "idx", *VARS, "cost_dB", "per_angle_dB"])

    def mapper(_func, xs):
        xs = [np.asarray(x) for x in xs]
        gen = state["gen"]
        state["gen"] += 1
        jobs = []
        for i, x in enumerate(xs):
            sets = [f"{k}={v}" for k, v in fixed.items()] + [f"{k}={snap(k, v):.4f}" for k, v in zip(VARS, x)]
            for th, ph in angles:
                jobs.append(["periodic", "--theta", f"{th:g}", "--phi", f"{ph:g}", "--nf", str(a.nf),
                             "--f1", "15", "--f2", "17", "--res", str(a.res), "--workers", str(min(a.nf, 8)),
                             "--tag", f"_optm_g{gen:02d}_{i:02d}", "--set", *sets])
        outs = list(run_fn.map(jobs, order_outputs=True, return_exceptions=True))
        costs = []
        for i, x in enumerate(xs):
            per = []
            for j in range(len(angles)):
                o = outs[i * len(angles) + j]
                if isinstance(o, Exception) or not o[0]:
                    per.append(0.0)
                    continue
                name, text = o[0][0]
                with open(os.path.join(OUT, name), "w") as fh:
                    fh.write(text)
                per.append(band_cost(json.loads(text)))
            c = max(per)            # worst over the requested scan angles
            costs.append(c)
            log.writerow([gen, i, *[f"{snap(k, v):.4f}" for k, v in zip(VARS, x)], f"{c:.2f}", " ".join(f"{p:.2f}" for p in per)])
            if c < state["best"]:
                state["best"] = c
                with open(os.path.join(RES, "optm_best.json"), "w") as fh:
                    json.dump({"cost": c, "per_angle": per, "angles": angles, "gen": gen, "idx": i,
                               "geom": {**{k: float(v) for k, v in fixed.items()},
                                        **{k: float(snap(k, v)) for k, v in zip(VARS, x)}}}, fh, indent=1)
        logf.flush()
        print(f"gen {gen:2d}: {len(xs)} candidates, best this gen {min(costs):6.2f} dB, "
              f"overall best {state['best']:6.2f} dB", flush=True)
        return costs

    x0 = np.array([x0d.get(k, sum(b) / 2) for k, b in VARS.items()]) if x0d else None
    with modal.enable_output(), app.run():
        r = differential_evolution(lambda x: 0.0, list(VARS.values()), popsize=a.popsize, maxiter=a.maxiter,
                                   workers=mapper, updating="deferred", polish=False, x0=x0, seed=1,
                                   mutation=(0.5, 0.9), recombination=0.7, tol=0.0)
    print("BEST", json.dumps(json.load(open(os.path.join(RES, "optm_best.json")))), flush=True)
    print("DE finished:", r.message, flush=True)


if __name__ == "__main__":
    main()

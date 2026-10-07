"""Score hg1_radard output against the scenario ground truth.

    python firmware/sim/verify.py
Reads sim/out/radard_output.jsonl + truth.json; writes sim/results/*.png and
sim/results/verification.json. Exit code 1 if acceptance criteria fail.
"""
import json
import math
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
RES = os.path.join(HERE, "results")
os.makedirs(RES, exist_ok=True)

frames = [json.loads(l) for l in open(os.path.join(OUT, "radard_output.jsonl"))]
truth = json.load(open(os.path.join(OUT, "truth.json")))["frames"]
movers = [d["name"] for d in truth[0] if d["kind"] != "clutter"]
expected_cls = {d["name"]: ("UAS-rotary" if d["kind"] == "UAS-rotary" else "bird") for d in truth[0]
                if d["kind"] != "clutter"}

# ---------------- plot-level accuracy (each truth mover vs nearest plot) ----
plot_err = {n: [] for n in movers}
for f, fr in enumerate(frames):
    for d in truth[f]:
        if d["kind"] == "clutter":
            continue
        best = None
        for p in fr["plots"]:
            dr = abs(p["r"] - d["r"])
            if dr < 15 and abs(p["vr"] - d["vr"]) < 3 and (best is None or dr < abs(best["r"] - d["r"])):
                best = p
        if best:
            plot_err[d["name"]].append((best["r"] - d["r"], best["az"] - d["az"], best["el"] - d["el"],
                                        best["vr"] - d["vr"], best["snr"]))
false_plots = 0
for f, fr in enumerate(frames):
    for p in fr["plots"]:
        if not any(abs(p["r"] - d["r"]) < 15 and abs(p["vr"] - d["vr"]) < 3 for d in truth[f] if d["kind"] != "clutter"):
            false_plots += 1

# ---------------- track-level: association of confirmed tracks --------------
trk = {n: {"frames": 0, "pos_err": [], "cls": None, "ids": set(), "first": None} for n in movers}
false_tracks = set()
for f, fr in enumerate(frames):
    for t in fr["tracks"]:
        best, bd = None, 1e9
        for d in truth[f]:
            if d["kind"] == "clutter":
                continue
            e = math.dist((t["x"], t["y"], t["z"]), (d["x"], d["y"], d["z"]))
            if e < bd:
                best, bd = d["name"], e
        if best and bd < 25:
            s = trk[best]
            s["frames"] += 1
            s["pos_err"].append(bd)
            s["cls"] = t["cls"]
            s["ids"].add(t["id"])
            s["first"] = f if s["first"] is None else s["first"]
        else:
            false_tracks.add(t["id"])

summary = {"n_frames": len(frames), "false_plots_total": false_plots, "false_confirmed_tracks": len(false_tracks),
           "mean_proc_ms": float(np.mean([fr["proc_ms"] for fr in frames])), "targets": {}}
ok = len(false_tracks) == 0
for n in movers:
    e = np.array(plot_err[n]) if plot_err[n] else np.zeros((0, 5))
    s = trk[n]
    row = {
        "plot_detections": int(len(e)), "pd_per_cpi": round(len(e) / len(frames), 2),
        "range_rmse_m": round(float(np.sqrt(np.mean(e[:, 0] ** 2))), 2) if len(e) else None,
        "az_rmse_deg": round(float(np.sqrt(np.mean(e[:, 1] ** 2))), 2) if len(e) else None,
        "el_rmse_deg": round(float(np.sqrt(np.mean(e[:, 2] ** 2))), 2) if len(e) else None,
        "vr_rmse_mps": round(float(np.sqrt(np.mean(e[:, 3] ** 2))), 2) if len(e) else None,
        "mean_snr_db": round(float(np.mean(e[:, 4])), 1) if len(e) else None,
        "confirmed_frames": s["frames"], "first_confirmed_frame": s["first"],
        "track_ids": sorted(s["ids"]),
        "track_pos_rmse_m": round(float(np.sqrt(np.mean(np.square(s["pos_err"])))), 2) if s["pos_err"] else None,
        "class": s["cls"], "class_expected": expected_cls[n],
    }
    row["class_ok"] = row["class"] == row["class_expected"]
    ok &= row["class_ok"] and s["frames"] > 0 and len(s["ids"]) == 1
    summary["targets"][n] = row
summary["pass"] = bool(ok)
json.dump(summary, open(os.path.join(RES, "verification.json"), "w"), indent=1)
print(json.dumps(summary, indent=1))

# ---------------- figures ----------------------------------------------------
col = {"phantom4": "#2a6fdb", "fpv": "#e0663a", "gull": "#1a9e77"}
fig, ax = plt.subplots(1, 2, figsize=(12, 5.2))
for n in movers:
    tx = [d["x"] for f in truth for d in f if d["name"] == n]
    ty = [d["y"] for f in truth for d in f if d["name"] == n]
    ax[0].plot(tx, ty, "-", color=col.get(n, "k"), lw=6, alpha=0.25, label=f"{n} truth")
clut = [d for d in truth[0] if d["kind"] == "clutter"]
ax[0].scatter([d["x"] for d in clut], [d["y"] for d in clut], marker="s", c="#777", s=30, label="static clutter")
tracks = {}
for f, fr in enumerate(frames):
    for t in fr["tracks"]:
        tracks.setdefault(t["id"], []).append((t["x"], t["y"], t["cls"]))
for tid, pts in tracks.items():
    xs, ys = zip(*[(p[0], p[1]) for p in pts])
    ax[0].plot(xs, ys, ".-", ms=4, lw=1, label=f"track {tid}: {pts[-1][2]}")
for f, fr in enumerate(frames):
    ax[0].scatter([p["r"] * math.sin(math.radians(p["az"])) * math.cos(math.radians(p["el"])) for p in fr["plots"]],
                  [p["r"] * math.cos(math.radians(p["az"])) * math.cos(math.radians(p["el"])) for p in fr["plots"]],
                  s=4, c="k", alpha=0.3)
ax[0].plot([0, 1400 * math.sin(math.radians(-60))], [0, 1400 * math.cos(math.radians(-60))], "k:", lw=0.8)
ax[0].plot([0, 1400 * math.sin(math.radians(60))], [0, 1400 * math.cos(math.radians(60))], "k:", lw=0.8)
ax[0].set(xlabel="x (m)", ylabel="y / boresight (m)", title="Firmware tracks vs ground truth (top view)",
          xlim=(-500, 500), ylim=(0, 1200), aspect="equal")
ax[0].legend(fontsize=7, loc="upper left")
ax[0].grid(alpha=0.3)

for n in movers:
    e = np.array(plot_err[n])
    if len(e):
        ax[1].scatter(e[:, 1], e[:, 2], s=18, color=col.get(n, "k"), label=f"{n} (SNR {np.mean(e[:, 4]):.0f} dB)")
th = np.linspace(0, 2 * np.pi, 100)
ax[1].plot(np.cos(th) * 1.0, np.sin(th) * 1.5, "k--", lw=0.8)
ax[1].text(0.6, 1.45, "EchoGuard spec\n1.0 x 1.5 deg", fontsize=7)
ax[1].set(xlabel="azimuth error (deg)", ylabel="elevation error (deg)", xlim=(-2, 2), ylim=(-2, 2),
          title="Per-CPI angle error of every detection (10 ms CPI)", aspect="equal")
ax[1].legend(fontsize=7)
ax[1].grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(RES, "tracks_vs_truth.png"), dpi=130)

fig, ax = plt.subplots(figsize=(7, 3.2))
for n in movers:
    md = [(f, p["md"]) for f, fr in enumerate(frames) for p in fr["plots"]
          for d in truth[f] if d["name"] == n and abs(p["r"] - d["r"]) < 15 and abs(p["vr"] - d["vr"]) < 3]
    if md:
        ax.plot(*zip(*md), "o-", ms=3, color=col.get(n, "k"), label=n)
ax.axhline(0.08, color="k", ls="--", lw=0.8)
ax.text(0.2, 0.09, "rotor threshold", fontsize=7)
ax.set(xlabel="frame", ylabel="micro-Doppler off-line / body energy", yscale="symlog",
       title="Micro-Doppler classifier feature: rotors vs wings")
ax.legend(fontsize=7)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(RES, "microdoppler_feature.png"), dpi=130)
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)

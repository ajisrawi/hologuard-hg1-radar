"""HoloGuard HG-1 -- full-wave FEM simulation of the radiating element (EMerge).

Two models of the aperture-coupled stacked patch (H-pol, E-field along x):

  isolated : single element on a 24 x 24 mm board, via-fenced stripline cavity,
             50-ohm lumped port, spherical air region + absorbing boundary.
             -> S11, realised-gain E/H-plane cuts (the TX element case)
  periodic : 9 x 9 mm unit cell in an infinite array (Floquet periodic BCs)
             -> active reflection coefficient vs scan angle (the RX lattice)

Stack (z = 0 at the L5 ground):
  L5 GND | 0.203 RO4450F/RO4003C | L4 stripline | 0.203 RO4003C | L3 GND + H-slot
        | 0.508 RO4003C | L2 driven patch | 0.813 RO4003C | L1 parasitic patch

Run with the project venv:
  .venv/Scripts/python antenna/em/element_em.py isolated
  .venv/Scripts/python antenna/em/element_em.py periodic --theta 45 --phi 0
Geometry overrides: --set par_l=5.2 drv_l=4.5 slot_l=3.6 stub=2.0 ...
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import emerge as em

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
RES = os.path.join(HERE, "results")
os.makedirs(RES, exist_ok=True)
mm = 1e-3

with open(os.path.join(ROOT, "antenna", "element_design.json")) as fh:
    EL = json.load(fh)

GEOM = {
    "par_l": EL["parasitic_patch_LxW_mm"][0], "par_w": EL["parasitic_patch_LxW_mm"][1],
    "drv_l": EL["driven_patch_LxW_mm"][0], "drv_w": EL["driven_patch_LxW_mm"][1],
    "slot_l": EL["slot"]["length_mm"], "slot_w": EL["slot"]["width_mm"],
    "arm_l": EL["slot"]["end_arms_mm"][0], "arm_w": EL["slot"]["end_arms_mm"][1],
    "stub": EL["stub_beyond_slot_mm"], "w_strip": 0.15,
    "h_feed_bot": 0.203, "h_feed_top": 0.203, "h_drv": 0.508,
    "h_par": EL["layer_heights_mm"]["L1-L2 parasitic gap RO4003C"],
    "pitch": 9.0, "board": 24.0, "cav": 1, "cav_in": 0.25,
}
RO4003C = dict(er=3.55, tand=0.0027)
FEEDMIX = dict(er=3.53, tand=0.0034)


def plate(w, d, cx, cy, z):
    return em.geo.XYPlate(w * mm, d * mm, position=((cx - w / 2) * mm, (cy - d / 2) * mm, z * mm))


def build(model, g, periodic, cell=None):
    z4 = g["h_feed_bot"]
    z3 = z4 + g["h_feed_top"]
    z2 = z3 + g["h_drv"]
    z1 = z2 + g["h_par"]
    B = g["pitch"] if periodic else g["board"]
    P = g["pitch"]

    def layer(za, zb, mat, size):
        if periodic:
            v = cell.volume(za * mm, zb * mm)
        else:
            v = em.geo.Box(size * mm, size * mm, (zb - za) * mm, position=(-size / 2 * mm, -size / 2 * mm, za * mm))
        v.set_material(em.Material(**mat, color="#e9dfb8", opacity=0.4))
        return v

    # Feed region: the stripline layers span the board/cell; a cross-shaped
    # via fence (modelled as thin PEC wall sheets L5-L3) encloses a narrow
    # corridor along the stripline plus a pocket around the full slot. Every
    # cavity mode of the fenced region is > 30 GHz, so the slot couples to the
    # patches instead of a parallel-plate / cavity resonance.
    x_port = -P / 2 + 0.6
    a_c = g.get("chan_half", 1.2)                       # corridor half-width
    bx = g["arm_l"] / 2 + 0.5                            # slot pocket half-width (x)
    py = g["slot_l"] / 2 + 0.6                           # slot pocket half-length (y)
    x0, x1 = x_port - 0.3, g["stub"] + 0.6
    d_feed_bot = layer(0, z4, FEEDMIX, B)
    d_feed_top = layer(z4, z3, RO4003C, B)
    d_drv = layer(z3, z2, RO4003C, B)
    d_par = layer(z2, z1, RO4003C, B)
    outline = [(x0, -a_c), (-bx, -a_c), (-bx, -py), (bx, -py), (bx, -a_c), (x1, -a_c),
               (x1, a_c), (bx, a_c), (bx, py), (-bx, py), (-bx, a_c), (x0, a_c)]
    walls = []
    for (xa, ya), (xb, yb) in zip(outline, outline[1:] + outline[:1]):
        walls.append(em.geo.Plate(np.array([xa * mm, ya * mm, 0.0]), np.array([(xb - xa) * mm, (yb - ya) * mm, 0.0]),
                                  np.array([0.0, 0.0, z3 * mm])).set_material(em.lib.PEC))

    # Element cavity: the L1->L5 via fence around every element (board design) modelled as PEC
    # walls through the antenna layers L3..L1, inset cav_in from the cell edge. It suppresses the
    # TM0 surface wave of the patch stack that otherwise causes E-plane scan blindness (~60 deg).
    if g.get("cav", 1):
        c = P / 2 - g.get("cav_in", 0.25)
        sq = [(-c, -c), (c, -c), (c, c), (-c, c)]
        for (xa, ya), (xb, yb) in zip(sq, sq[1:] + sq[:1]):
            walls.append(em.geo.Plate(np.array([xa * mm, ya * mm, z3 * mm]),
                                      np.array([(xb - xa) * mm, (yb - ya) * mm, 0.0]),
                                      np.array([0.0, 0.0, (z1 - z3) * mm])).set_material(em.lib.PEC))

    gnd5 = plate(B, B, 0, 0, 0).set_material(em.lib.PEC)
    gnd3 = plate(B, B, 0, 0, z3)
    for (w, d, cx, cy) in ((g["slot_w"], g["slot_l"], 0, 0),
                           (g["arm_l"], g["arm_w"], 0, g["slot_l"] / 2),
                           (g["arm_l"], g["arm_w"], 0, -g["slot_l"] / 2)):
        gnd3 = em.geo.remove(gnd3, plate(w, d, cx, cy, z3))
    gnd3.set_material(em.lib.PEC)

    strip = plate(g["stub"] - x_port, g["w_strip"], (x_port + g["stub"]) / 2, 0, z4).set_material(em.lib.PEC)
    drv = plate(g["drv_l"], g["drv_w"], 0, 0, z2).set_material(em.lib.PEC)
    par = plate(g["par_l"], g["par_w"], 0, 0, z1).set_material(em.lib.PEC) if g.get("par_on", 1) else None
    vias = walls
    port = em.geo.Plate(np.array([x_port * mm, -g["w_strip"] / 2 * mm, 0.0]),
                        np.array([0.0, g["w_strip"] * mm, 0.0]), np.array([0.0, 0.0, z4 * mm]))
    if periodic:
        air = cell.volume(z1 * mm, (z1 + g.get("h_air", 10.0)) * mm)
    else:
        air = em.geo.Sphere(g.get("r_air", 21.0) * mm).background()
    return dict(air=air, port=port, metals=[m for m in [gnd5, gnd3, strip, drv, par] if m is not None] + vias,
                patches=[m for m in (drv, par) if m is not None],
                z1=z1, strip=strip, gnd3=gnd3, feed_layers=(d_feed_bot, d_feed_top))


def run(mode, g, theta=0.0, phi=0.0, f1=14.0e9, f2=18.5e9, nf=19, res=0.22, tag="", workers=1):
    t0 = time.time()
    model = em.Simulation(f"HG1_element_{mode}{tag}")
    cell = None
    if mode == "periodic":
        cell = em.RectCell(g["pitch"] * mm, g["pitch"] * mm)
        model.set_periodic_cell(cell)
    geo = build(model, g, mode == "periodic", cell)
    model.mw.set_resolution(res)
    model.mw.set_frequency_range(f1, f2, nf)
    model.commit_geometry()
    for p in geo["patches"]:
        model.mesher.set_boundary_size(p, 0.6 * mm)
    model.mesher.set_boundary_size(geo["gnd3"], 0.5 * mm)
    model.mesher.set_boundary_size(geo["strip"], 0.35 * mm)
    model.mesher.set_face_size(geo["port"], 0.08 * mm)
    model.generate_mesh()
    model.mw.bc.LumpedPort(geo["port"], 1, width=g["w_strip"] * mm, height=g["h_feed_bot"] * mm,
                           direction=em.ZAX, Z0=50)
    if mode == "periodic":
        # Floquet port on the cell top (.back is the +z cap): Robin term j*k0*cos(theta)
        # absorbs the scanned beam exactly, unlike a normal-incidence ABC.
        model.mw.bc.floquet_port(geo["air"].back, 2)
        cell.set_scanangle(theta, phi)
        boundary = None

    else:
        boundary = geo["air"].boundary()
        model.mw.bc.AbsorbingBoundary(boundary)

    # workers=1: sequential PARDISO (~2 GB RAM, laptop); workers>1: frequency points in parallel (Modal)
    data = model.mw.run_sweep(parallel=workers > 1, n_workers=max(workers, 1))
    fd = np.linspace(f1, f2, 451)
    s11 = data.scalar.grid.model_S(1, 1, fd)
    f_raw = np.asarray(data.scalar.grid.freq).ravel()
    s_raw = np.asarray(data.scalar.grid.S(1, 1)).ravel()
    out = {"mode": mode, "theta": theta, "phi": phi, "geom": g, "freq_GHz": (fd / 1e9).tolist(),
           "s11_db": (20 * np.log10(np.abs(s11) + 1e-12)).tolist(), "runtime_s": time.time() - t0,
           "raw_freq_GHz": (f_raw / 1e9).tolist(), "raw_s11_db": (20 * np.log10(np.abs(s_raw) + 1e-12)).tolist(),
           "raw_s11_re": np.real(s_raw).tolist(), "raw_s11_im": np.imag(s_raw).tolist()}
    print("RAW S11:", " ".join(f"{f / 1e9:.2f}GHz:{20 * np.log10(abs(v) + 1e-12):.1f}dB" for f, v in zip(f_raw, s_raw)),
          flush=True)
    if mode == "isolated":
        fld = data.field.find(freq=16.0e9)
        cuts = {}
        # farfield_2d takes the rotation axis of the cut: y-axis -> xz (E) plane.
        for name, ax in (("E_plane_xz", (0, 1, 0)), ("H_plane_yz", (1, 0, 0))):
            ff = fld.farfield_2d((0, 0, 1), ax, boundary)
            cuts[name] = {"ang_deg": (np.asarray(ff.ang) * 180 / np.pi).tolist(),
                          "gain_dbi": (20 * np.log10(np.abs(np.asarray(ff.gain.norm)) + 1e-12)).tolist()}
        out["farfield_16GHz"] = cuts
        out["gain_db_20log"] = True
        out["cut_labels_fixed"] = True
    name = f"{mode}{tag}" + (f"_t{theta:g}_p{phi:g}" if mode == "periodic" else "")
    with open(os.path.join(RES, name + ".json"), "w") as fh:
        json.dump(out, fh)
    bw = [f for f, s in zip(out["freq_GHz"], out["s11_db"]) if s < -10]
    print(f"RESULT {name}: |S11|<-10 dB from {min(bw) if bw else 0:.2f} to {max(bw) if bw else 0:.2f} GHz, "
          f"min {min(out['s11_db']):.1f} dB @ {out['freq_GHz'][int(np.argmin(out['s11_db']))]:.2f} GHz, "
          f"{out['runtime_s']:.0f} s", flush=True)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["isolated", "periodic"])
    ap.add_argument("--theta", type=float, default=0.0)
    ap.add_argument("--phi", type=float, default=0.0)
    ap.add_argument("--nf", type=int, default=19)
    ap.add_argument("--res", type=float, default=0.22)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--tag", default="")
    ap.add_argument("--set", nargs="*", default=[])
    ap.add_argument("--f1", type=float, default=14.0)
    ap.add_argument("--f2", type=float, default=18.5)
    a = ap.parse_args()
    g = dict(GEOM)
    for kv in a.set:
        k, v = kv.split("=")
        g[k] = float(v)
    run(a.mode, g, a.theta, a.phi, f1=a.f1 * 1e9, f2=a.f2 * 1e9, nf=a.nf, res=a.res, tag=a.tag, workers=a.workers)

"""Run element_em.py jobs in parallel on Modal (one container per job).

Four container types:
  big  : 32 vCPU / 128 GB, PARDISO, frequency points solved in parallel (--workers)  [default]
  mid  : 8 vCPU / 32 GB, PARDISO (optimiser populations)
  a100 : A100-80GB + 16 vCPU / 128 GB, NVIDIA cuDSS sparse direct solver (large isolated models)
  l4   : L4 + cuDSS (cheap GPU)
Each job is an argument list for element_em.py; each result JSON is written back into
antenna/em/results/ exactly as a local run would. EMerge's numba kernels are cached in a volume.

  .venv/Scripts/python -m modal run antenna/em/modal_em.py --smoke
  .venv/Scripts/python -m modal run antenna/em/modal_em.py --jobs antenna/em/jobs_scan.json [--kind a100]

jobs file: [["periodic", "--theta", "45", "--tag", "_final", "--set", "h_par=1.524", ...], ...]
"""
import glob
import json
import os
import subprocess
import sys

import modal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
REMOTE = "/root/hg1"

app = modal.App("hg1-element-em")
# EMerge's numba kernels take ~6 min to JIT-compile on a fresh container; keep the cache in a volume.
numba_cache = modal.Volume.from_name("hg1-numba-cache", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libglu1-mesa", "libgl1", "libxrender1", "libxcursor1", "libxft2", "libxinerama1",
                 "libxext6", "libgomp1")
    .pip_install("emerge[cudss]", "pypardiso")
    .env({"NUMBA_CACHE_DIR": "/cache/numba"})
    .add_local_file(os.path.join(HERE, "element_em.py"), f"{REMOTE}/antenna/em/element_em.py")
    .add_local_file(os.path.join(ROOT, "antenna", "element_design.json"), f"{REMOTE}/antenna/element_design.json")
)
VOL = {"/cache": numba_cache}


def _run(args, solver):
    env = dict(os.environ)
    if solver:
        env["EMERGE_MP_SOLVER"] = solver
    res = f"{REMOTE}/antenna/em/results"
    os.makedirs(res, exist_ok=True)
    before = set(glob.glob(f"{res}/*.json"))
    p = subprocess.run([sys.executable, f"{REMOTE}/antenna/em/element_em.py", *args], env=env,
                       capture_output=True, text=True)
    try:
        numba_cache.commit()
    except Exception:
        pass
    new = sorted(set(glob.glob(f"{res}/*.json")) - before)
    log = "\n".join([ln for ln in p.stdout.splitlines() if ln.startswith(("RESULT", "RAW"))]
                    + p.stderr.splitlines()[-15:] * (p.returncode != 0))
    return [(os.path.basename(f), open(f).read()) for f in new], log


@app.function(image=image, cpu=32, memory=131072, timeout=3600, volumes=VOL)
def run_big(args):
    return _run(args, None)


@app.function(image=image, cpu=8, memory=32768, timeout=3600, volumes=VOL)
def run_mid(args):
    return _run(args, None)


@app.function(image=image, gpu="A100-80GB", cpu=16, memory=131072, timeout=3600, volumes=VOL)
def run_a100(args):
    return _run(args, "CUDSS")


@app.function(image=image, gpu="L4", memory=16384, timeout=3600, volumes=VOL)
def run_gpu(args):
    return _run(args, "CUDSS")


FUNCS = {"big": run_big, "mid": run_mid, "a100": run_a100, "l4": run_gpu}


@app.local_entrypoint()
def main(jobs: str = "", kind: str = "big", smoke: bool = False):
    if smoke:
        job_list = [["periodic", "--nf", "5", "--f1", "15", "--f2", "17", "--tag", "_modal_smoke",
                     "--set", "h_par=1.524"]]
    else:
        with open(jobs) as fh:
            job_list = json.load(fh)
    out_dir = os.path.join(HERE, "results")
    for files, log in FUNCS[kind].map(job_list, order_outputs=False):
        print(log, flush=True)
        for name, text in files:
            with open(os.path.join(out_dir, name), "w") as fh:
                fh.write(text)
            print("saved", name, flush=True)

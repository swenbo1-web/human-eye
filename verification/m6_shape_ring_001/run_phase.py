"""Execute one named ring-probe phase and retain every monitored attempt."""

import os
for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from process_runner import process_metrics, run


def main():
    started, cpu = time.perf_counter(), time.process_time()
    names = {"prepare": "prepare.py", "fit": "geometry_fit.py", "qa": "synthetic_qa.py",
             "calibrate": "calibrate.py", "evaluate": "evaluate.py", "verify": "verify.py", "summary": "summarize.py"}
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=names)
    parser.add_argument("--label")
    args = parser.parse_args()
    label = args.label or args.phase
    directory = HERE / "private/processes"
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / (label + ".json")).exists() or (directory / (label + ".controller.json")).exists():
        raise ValueError("phase_label_used_inspect_before_explicit_recovery")
    for row in json.loads((HERE / "PLAN_FREEZE.json").read_bytes())["files"]:
        if hashlib.sha256((HERE / row["path"]).read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("frozen_plan_changed_" + row["path"])
    if args.phase == "evaluate":
        binding = json.loads((HERE / "CALIBRATION_BINDING.json").read_bytes())
        for filename in ("CALIBRATION.json", "CALIBRATION_FREEZE.json"):
            path = "verification/m6_shape_ring_001/" + filename
            committed = subprocess.check_output(["git", "show", binding["commit"] + ":" + path], cwd=HERE.parents[1])
            if committed != (HERE / filename).read_bytes():
                raise ValueError("calibration_changed_after_fixed_commit")
    previous = [json.loads(path.read_bytes()) for path in directory.glob("*.controller.json")]
    used = sum(row["main_wall_s_including_worker_before_write"] for row in previous)
    remaining = 7200 - used
    if remaining <= 0:
        raise RuntimeError("frozen_compute_budget_exhausted")
    script = HERE / names[args.phase]
    source_sha = hashlib.sha256(script.read_bytes()).hexdigest()
    python = HERE.parent / "m6_shape_train_001/private/venv/Scripts/python.exe"
    result = run([str(python), "-I", "-B", "-X", "utf8", str(script)], label,
                 timeout_s=remaining, rss_limit_bytes=4294967296)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    controller = {"phase": args.phase, "label": label, "worker_source_sha256": source_sha,
                  "main_wall_s_including_worker_before_write": time.perf_counter() - started,
                  "main_CPU_s_excluding_worker": time.process_time() - cpu,
                  "process_lifetime_before_final_write": process_metrics(ctypes.windll.kernel32.GetCurrentProcess()),
                  "compute_used_before_phase_s": used, "returncode": result["returncode"],
                  "scope": "controller main excludes imports/final write; worker tree covers startup/exit, sampled discovery and peak"}
    (directory / (label + ".controller.json")).write_text(json.dumps(controller, indent=2) + "\n", encoding="utf8", newline="\n")
    if result["returncode"]:
        raise SystemExit(result["returncode"])


if __name__ == "__main__":
    main()

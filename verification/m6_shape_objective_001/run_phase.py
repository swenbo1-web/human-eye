"""Measure one explicit objective-diagnostic phase and preserve its ledger."""

import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from process_runner import process_metrics, run


def main():
    started, cpu = time.perf_counter(), time.process_time()
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("decompose", "qa", "surface", "repair", "summary", "verify"))
    parser.add_argument("--label")
    args = parser.parse_args()
    names = {"decompose": "decompose.py", "qa": "meter_qa.py", "surface": "evaluate_surface.py",
             "repair": "repair_surface_metadata.py", "summary": "summarize.py", "verify": "verify.py"}
    for row in json.loads((HERE / "PLAN_FREEZE.json").read_bytes())["files"]:
        if hashlib.sha256((HERE / row["path"]).read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("frozen_plan_changed_" + row["path"])
    python = HERE.parent / "m6_shape_train_001/private/venv/Scripts/python.exe"
    script = HERE / names[args.phase]
    label = args.label or args.phase
    record = run([str(python), "-I", "-B", "-X", "utf8", str(script)], label,
                 timeout_s=1800, rss_limit_bytes=2147483648)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    controller = {"phase": args.phase, "label": label, "worker_source_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
                  "main_wall_s_including_worker_before_write": time.perf_counter() - started,
                  "main_CPU_s_excluding_worker": time.process_time() - cpu,
                  "process_lifetime_before_final_write": process_metrics(ctypes.windll.kernel32.GetCurrentProcess()),
                  "returncode": record["returncode"],
                  "scope": "controller main excludes imports/final serialization/exit; worker tree includes worker startup and exit"}
    (HERE / "private/processes" / (label + ".controller.json")).write_text(
        json.dumps(controller, indent=2) + "\n", encoding="utf-8", newline="\n")
    if record["returncode"]:
        raise SystemExit(record["returncode"])


if __name__ == "__main__":
    main()

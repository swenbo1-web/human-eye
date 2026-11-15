"""Measure one explicitly requested diagnostic phase and preserve every attempt."""

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
    started, cpu_started = time.perf_counter(), time.process_time()
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("audit", "retrieval", "trace", "render", "summary", "verify"))
    parser.add_argument("--label")
    args = parser.parse_args()
    sources = {"audit": "audit_inputs.py", "retrieval": "retrieval.py", "trace": "trace.py",
               "render": "render_evidence.py", "summary": "summarize.py", "verify": "verify.py"}
    frozen = json.loads((HERE / "PLAN_FREEZE.json").read_bytes())
    for row in frozen["files"]:
        if hashlib.sha256((HERE / row["path"]).read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("frozen_plan_changed_" + row["path"])
    python = HERE.parent / "m6_shape_train_001/private/venv/Scripts/python.exe"
    if args.phase == "render":
        python = Path(sys.base_prefix) / "python.exe"
    label = args.label or args.phase
    worker = HERE / sources[args.phase]
    record = run([str(python), "-I", "-B", "-X", "utf8", str(worker)], label,
                 timeout_s=1800, rss_limit_bytes=2147483648)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    controller = {"phase": args.phase, "label": label,
                  "worker_source_sha256": hashlib.sha256(worker.read_bytes()).hexdigest(),
                  "wall_s_including_worker_before_write": time.perf_counter() - started,
                  "main_window_cpu_s_excluding_worker": time.process_time() - cpu_started,
                  "process_lifetime_before_final_write": process_metrics(ctypes.windll.kernel32.GetCurrentProcess()),
                  "returncode": record["returncode"],
                  "scope": "main-window wall includes worker; CPU excludes worker; final controller JSON serialization and exit unmeasured"}
    (HERE / "private/processes" / (label + ".controller.json")).write_text(
        json.dumps(controller, indent=2) + "\n", encoding="utf-8", newline="\n")
    if record["returncode"]:
        raise SystemExit(record["returncode"])


if __name__ == "__main__":
    main()

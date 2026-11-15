"""Run one explicit phase with preserved failures and the frozen compute budget."""

import os
for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"

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
    names = {"prepare": "prepare_payload.py", "inputs": "build_inputs.py", "qa": "verify_adapter.py",
             "inference": "inference.py", "evaluate": "evaluate.py", "summary": "summarize.py",
             "verify": "verify_results.py"}
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=names)
    parser.add_argument("--label")
    args = parser.parse_args()
    label = args.label or args.phase
    log_dir = HERE / "private/processes"
    log_dir.mkdir(parents=True, exist_ok=True)
    if (log_dir / (label + ".json")).exists() or (log_dir / (label + ".controller.json")).exists():
        raise ValueError("phase_label_already_used_inspect_before_explicit_recovery")
    for row in json.loads((HERE / "PLAN_FREEZE.json").read_bytes())["files"]:
        if hashlib.sha256((HERE / row["path"]).read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("frozen_plan_changed_" + row["path"])
    previous = [json.loads(path.read_bytes()) for path in log_dir.glob("*.controller.json")]
    compute_used = sum(row["main_wall_s_including_worker_before_write"] for row in previous if row["phase"] != "prepare")
    remaining = 7200 - compute_used
    if args.phase != "prepare" and remaining <= 0:
        raise RuntimeError("frozen_compute_budget_exhausted")
    python = HERE.parent / "m6_shape_train_001/private/venv/Scripts/python.exe"
    script = HERE / names[args.phase]
    source_sha = hashlib.sha256(script.read_bytes()).hexdigest()
    record = run([str(python), "-I", "-B", "-X", "utf8", str(script)], label,
                 timeout_s=1200 if args.phase == "prepare" else remaining,
                 rss_limit_bytes=4294967296)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    result = {"phase": args.phase, "label": label, "worker_source_sha256": source_sha,
              "main_wall_s_including_worker_before_write": time.perf_counter() - started,
              "main_CPU_s_excluding_worker": time.process_time() - cpu,
              "process_lifetime_before_final_write": process_metrics(ctypes.windll.kernel32.GetCurrentProcess()),
              "compute_used_before_phase_s": compute_used, "compute_remaining_before_phase_s": remaining,
              "returncode": record["returncode"],
              "scope": "controller imports/final write excluded; worker tree covers worker startup/exit, discovery and peak sampled"}
    (log_dir / (label + ".controller.json")).write_text(json.dumps(result, indent=2) + "\n", encoding="utf8", newline="\n")
    if record["returncode"]:
        raise SystemExit(record["returncode"])


if __name__ == "__main__":
    main()

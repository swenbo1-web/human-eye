"""Single-threaded phase runner with retained failures and bounded compute/storage."""

import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
MONITOR = HERE.parent / "m6_shape_train_001/process_runner.py"
spec = importlib.util.spec_from_file_location("_data_process_monitor", MONITOR)
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)
monitor.HERE = HERE


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("acquire", "metadata", "source_views", "generate", "qa", "simulate", "render_views", "verify_sampling", "current_qa", "finalize"))
    parser.add_argument("--label")
    args = parser.parse_args()
    label = args.label or args.phase
    records = HERE / "private/processes"
    records.mkdir(parents=True, exist_ok=True)
    if (records / (label + ".json")).exists() or (records / (label + ".controller.json")).exists():
        raise RuntimeError("phase_label_already_used")
    prior = [json.loads(path.read_bytes()) for path in records.glob("*.controller.json")]
    compute_used = sum(row["wall_s"] for row in prior if row["compute_budget_counted"])
    counted = args.phase not in ("acquire", "finalize")
    if counted and compute_used >= 1800:
        raise RuntimeError("data_compute_budget_exhausted")
    if sum(p.stat().st_size for p in HERE.rglob("*") if p.is_file()) >= 2 * 1024**3:
        raise RuntimeError("new_storage_budget_exhausted")
    if args.phase in ("generate", "qa", "simulate", "render_views", "verify_sampling", "current_qa"):
        frozen = json.loads((HERE / "PLAN_FREEZE.json").read_bytes())
        for row in frozen["files"]:
            if hashlib.sha256((HERE / row["path"]).read_bytes()).hexdigest() != row["sha256"]:
                raise RuntimeError("frozen_plan_changed_" + row["path"])
    script = HERE / (args.phase + ".py")
    python = HERE.parent / "m6_shape_train_001/private/venv/Scripts/python.exe"
    started = time.perf_counter()
    result = monitor.run([str(python), "-I", "-B", "-X", "utf8", str(script)], label,
                         timeout_s=1800 - compute_used if counted else 1800, rss_limit_bytes=4 * 1024**3)
    report = dict(phase=args.phase, label=label, compute_budget_counted=counted, compute_used_before_s=compute_used,
                  wall_s=time.perf_counter() - started, worker_source_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),
                  monitor_source_sha256=hashlib.sha256(MONITOR.read_bytes()).hexdigest(), returncode=result["returncode"],
                  measurement="worker tree sampled50ms, single-thread correctness run, nonexclusive")
    (records / (label + ".controller.json")).write_text(json.dumps(report, indent=2) + "\n", encoding="utf8", newline="\n")
    if result["returncode"]:
        raise SystemExit(result["returncode"])


if __name__ == "__main__":
    main()

"""Single-thread numerical phases with retained attempts and a two-hour budget."""

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
spec = importlib.util.spec_from_file_location("_task_perception_monitor", MONITOR)
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)
monitor.HERE = HERE
PHASES = {"prepare": ["prepare.py"], "features": ["features.py"], "train_v1": ["train.py", "--version", "v1"],
          "train_v2": ["train.py", "--version", "v2"], "initial": ["evaluate.py", "--version", "v1"],
          "evaluate": ["evaluate.py", "--version", "v2"], "focus_qa": ["focus_qa.py"],
          "consumer_prepare": ["consumer_prepare.py"], "runtime_qa": ["runtime_qa.py"], "inspect_reports": ["inspect_reports.py"],
          "score": ["score_consumers.py"], "verify": ["verify.py"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=PHASES)
    parser.add_argument("--label")
    args = parser.parse_args()
    label = args.label or args.phase
    directory = HERE / "private/processes"
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / (label + ".json")).exists() or (directory / (label + ".controller.json")).exists():
        raise RuntimeError("phase_label_already_used")
    frozen = json.loads((HERE / "PLAN_FREEZE.json").read_bytes())
    for row in frozen["files"]:
        if hashlib.sha256((HERE / row["path"]).read_bytes()).hexdigest() != row["sha256"]:
            raise RuntimeError("frozen_plan_changed_" + row["path"])
    previous = [json.loads(path.read_bytes()) for path in directory.glob("*.controller.json")]
    used = sum(row["wall_s"] for row in previous)
    if used >= 7200:
        raise RuntimeError("numerical_budget_exhausted")
    command = PHASES[args.phase]
    script = HERE / command[0]
    archive = HERE / "private/executed" / (label + ".py")
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(script.read_bytes())
    python = HERE.parent / "m6_shape_train_001/private/venv/Scripts/python.exe"
    started = time.perf_counter()
    result = monitor.run([str(python), "-I", "-B", "-X", "utf8", str(script), *command[1:]], label,
                         timeout_s=7200-used, rss_limit_bytes=4*1024**3)
    report = dict(phase=args.phase, label=label, wall_s=time.perf_counter()-started, numerical_used_before_s=used,
                  worker_source=archive.relative_to(HERE).as_posix(), worker_source_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                  returncode=result["returncode"], measurement="single-thread, nonexclusive, Windows descendants discovered50ms")
    (directory / (label + ".controller.json")).write_text(json.dumps(report, indent=2) + "\n", encoding="utf8", newline="\n")
    if result["returncode"]:
        raise SystemExit(result["returncode"])


if __name__ == "__main__":
    main()

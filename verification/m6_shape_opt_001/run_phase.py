"""Run one explicit phase once, preserving its process and controller costs."""

import argparse
import ctypes
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
    parser.add_argument("phase", choices=("train", "calibrate", "evaluate", "summarize", "render", "online"))
    args = parser.parse_args()
    phase = args.phase
    commands = {"train": ("train.py", [], 1900), "calibrate": ("calibrate.py", [], 120),
                "evaluate": ("evaluate.py", ["--final"], 180),
                "summarize": ("summarize_results.py", [], 120),
                "render": ("render_results.py", [str(HERE / "RESULTS.json")], 120),
                "online": ("run_online.py", [], 180)}
    script, arguments, timeout = commands[phase]
    python = HERE.parent / "m6_shape_train_001/private/venv/Scripts/python.exe"
    if phase == "render":
        python = Path(sys.base_prefix) / "python.exe"
    command = [str(python), "-I", "-B", "-X", "utf8", str(HERE / script), *arguments]
    record = run(command, phase, timeout_s=timeout, rss_limit_bytes=2147483648)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    controller = {"phase": phase, "wall_s_including_worker_before_write": time.perf_counter() - started,
                  "controller_cpu_s_excluding_worker": time.process_time() - cpu_started,
                  "controller_process": process_metrics(ctypes.windll.kernel32.GetCurrentProcess()),
                  "nested_worker_ledger": str(HERE / "private/processes" / (phase + ".json")),
                  "worker_returncode": record["returncode"]}
    (HERE / "private/processes" / (phase + ".controller.json")).write_text(
        json.dumps(controller, indent=2) + "\n", encoding="utf-8", newline="\n")
    if record["returncode"]:
        raise SystemExit(record["returncode"])


if __name__ == "__main__":
    main()

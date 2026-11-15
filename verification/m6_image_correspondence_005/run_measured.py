"""Run a batch-owned numerical helper with the existing Windows tree monitor."""

import argparse
import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import PYTHON, write


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--timeout", type=float, default=7200)
    parser.add_argument("script")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    script = (HERE / args.script).resolve()
    if not script.is_relative_to(HERE):
        raise ValueError("helper_must_belong_to_current_batch")
    spec = importlib.util.spec_from_file_location("matched_monitor", HERE.parent / "m6_shape_train_001/process_runner.py")
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    monitor.HERE = HERE
    command = [str(PYTHON), "-I", "-B", "-X", "utf8", str(script), *args.arguments]
    record = monitor.run(command, args.label, timeout_s=args.timeout, rss_limit_bytes=4 * 1024**3)
    write(Path("private/measured") / (args.label + ".json"), record)
    print({key: record.get(key) for key in ("status", "returncode", "full_process_wall_s", "tree_cpu_s", "tree_sampled_peak_working_set_bytes")})
    if record["returncode"]:
        raise SystemExit(record["returncode"])


if __name__ == "__main__":
    main()

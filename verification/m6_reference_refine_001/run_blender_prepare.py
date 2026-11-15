"""Bound the original-source and context preparation under a measured process tree."""

import argparse
import importlib.util
import os
from pathlib import Path
import sys
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import PYTHON, write


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare_sources", "prepare_views", "observe", "verify_observation"))
    args = parser.parse_args()
    specification = importlib.util.spec_from_file_location("_reference_monitor", HERE.parent / "m6_shape_train_001/process_runner.py")
    monitor = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(monitor)
    monitor.HERE = HERE
    label = "prepare_" + args.phase
    if (HERE / "private/processes" / (label + ".json")).exists():
        raise ValueError("phase_already_attempted")
    record = monitor.run([str(PYTHON), "-I", "-B", "-X", "utf8", str(HERE / (args.phase + ".py"))],
        label, timeout_s=7200, rss_limit_bytes=4*1024**3)
    write("private/processes/" + label + ".controller.json", dict(phase=args.phase, process=record,
        scope="inclusive numerical/controller process tree, nested Blender has separate job receipts"))
    if record["returncode"]:
        raise SystemExit(record["returncode"])


if __name__ == "__main__":
    main()

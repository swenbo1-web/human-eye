"""Run the existing protocol checks and retain the v1 public summary bytes."""

import hashlib
import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def main():
    original_report = HERE / "CONSUMER_PREFLIGHT.json"
    original_sha = hashlib.sha256(original_report.read_bytes()).hexdigest()
    specification = importlib.util.spec_from_file_location("_v2_shared_runtime_preflight", HERE / "consumer_preflight.py")
    preflight = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(preflight)
    save = preflight.write

    def stage_write(path, value):
        target = Path(path)
        if target.resolve() == original_report:
            target = HERE / "CONSUMER_PREFLIGHT_v2.json"
        save(target, value)

    preflight.write = stage_write
    preflight.main()
    if hashlib.sha256(original_report.read_bytes()).hexdigest() != original_sha:
        raise ValueError("v1_protocol_preflight_summary_changed")


if __name__ == "__main__":
    main()

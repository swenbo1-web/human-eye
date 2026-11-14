"""One train-only MLS threshold and full development/validation comparison."""
import os
for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"

import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from baseline_eval import calibrate_mls, evaluate_baselines
from data_io import cases_at


def main():
    started, cpu_started = time.perf_counter(), time.process_time()
    train_root = HERE.parent / "m6_shape_data_001"
    train_cases = cases_at(train_root / "DATASET_INDEX.json")
    validation = cases_at(HERE / "PUBLIC_DATASET_INDEX.json", "validation")
    assert len(train_cases) == 231 and len(validation) == 117
    cache = HERE / "private/mls_cache"
    calibration = calibrate_mls(train_cases, train_root / "private/patches", cache)
    tau = calibration["tau"]
    development = evaluate_baselines(train_cases, train_root / "private/patches", tau, HERE / "private/baseline/development", cache)
    validation_result = evaluate_baselines(validation, HERE / "private/public_data/patches", tau, HERE / "private/baseline/validation")
    result = {"cycle_id": "M6-SHAPE-TRAIN-001", "tau": tau, "calibration": calibration,
              "development": development, "validation": validation_result, "Bunny_MLS_scores": 0,
              "main_wall_s": time.perf_counter() - started, "main_cpu_s": time.process_time() - cpu_started}
    (HERE / "BASELINE_RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"tau": tau, "development": 231, "validation": 117, "wall_s": result["main_wall_s"]}), flush=True)


if __name__ == "__main__":
    main()

"""Fix one normal patch-max q95 threshold after the single head training run."""

import time
BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()

import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from perception_metrics import measure, process_resources
import numpy as np


def write(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def main():
    started, cpu = time.perf_counter(), time.process_time()
    if (HERE / "CALIBRATION.json").exists():
        raise RuntimeError("calibration_exists_inspect_before_explicit_recovery")
    timings, identities = {}, {}

    def record(path, expected=None):
        path = Path(path)
        if not path.is_absolute():
            path = HERE / path
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if expected is not None and sha != expected:
            raise ValueError("calibration_input_identity_changed_" + str(path))
        identities[str(path)] = {"path": str(path), "bytes": len(data), "sha256": sha}
        return path

    with measure(timings, "development_prediction_and_training_identity_read"):
        training = json.loads(record(HERE / "TRAIN_LOG.json").read_bytes())
        model_identity = json.loads(record(HERE / "MODEL_IDENTITY.json").read_bytes())
        predictions = json.loads(record(HERE / "PREDICTIONS_DEVELOPMENT.json").read_bytes())
        features = json.loads(record(HERE / "FEATURES.json").read_bytes())
        whitelist = json.loads((HERE / "INPUT_WHITELIST.json").read_bytes())
        cases = {row["id"]: row for row in whitelist["cases"] if row["purpose"] == "development_train_pool"}
        prediction_rows = {row["id"]: row for row in predictions["cases"]}
        if len(cases) != 231 or set(cases) != set(prediction_rows) or len(prediction_rows) != len(predictions["cases"]):
            raise ValueError("calibration_requires_all231_development_predictions")
        feature_development = [row for row in features["cases"] if row["id"] in cases]
        if len(feature_development) != 231 or {row["id"] for row in feature_development} != set(cases):
            raise ValueError("calibration_requires231_development_feature_identities")
        for row in feature_development:
            record(row["path"], row["sha256"])
        for row in predictions["cases"]:
            record(row["path"], row["sha256"])
        for name in ("initial_checkpoint", "final_checkpoint", "normalization"):
            row = training[name]
            record(row["path"], row["sha256"])
            if row.get("json_path"):
                record(row["json_path"], row["json_sha256"])
    normal_rows = []
    with measure(timings, "normal33_prediction_score_read"):
        for case_id, case in sorted(cases.items()):
            if not case["normal_control"]:
                continue
            row = prediction_rows[case_id]
            with np.load(record(row["path"], row["sha256"]), allow_pickle=False) as saved:
                scores = saved["scores"].reshape(-1).astype(np.float64)
                valid = saved["valid_mask"].astype(bool)
                source_ids = saved["free_source_ids"]
            if scores.shape != valid.shape or source_ids.shape != scores.shape or not np.isfinite(scores).all():
                raise ValueError("invalid_normal_prediction")
            if np.any(scores[~valid] != 0):
                raise ValueError("unavailable_predictions_must_be_zero")
            normal_rows.append({"id": case_id, "patch_id": case["patch_id"], "maximum_score": float(scores.max()) if len(scores) else 0.0,
                                "F_points": len(scores), "unavailable_points": int(np.count_nonzero(~valid)),
                                "path": row["path"], "sha256": row["sha256"]})
    if len(normal_rows) != 33 or len({row["patch_id"] for row in normal_rows}) != 33:
        raise ValueError("calibration_requires33_distinct_development_normal_patches")
    with measure(timings, "linear_patch_max_q95_once"):
        threshold = float(np.quantile([row["maximum_score"] for row in normal_rows], .95, method="linear"))
        false = [row["id"] for row in normal_rows if row["maximum_score"] > threshold]
    report = {"cycle_id": "M6-PERCEPTION-001", "status": "completed_once_development_normal_q95_calibration",
              "calibration_count": 1, "normal_patches": 33, "normal_F_points": sum(row["F_points"] for row in normal_rows),
              "threshold": threshold, "quantile": .95, "quantile_method": "linear", "comparison": "strictly_greater",
              "cases": normal_rows, "development_normal_false_case_ids": false,
              "development_reuse_scope": "normal controls also occur in head training, calibration error is descriptive and dependent",
              "model_identity": model_identity, "input_file_identities": list(identities.values()), "timings": timings,
              "source_sha256": {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in ("calibrate.py", "perception_metrics.py")},
              "wall_s_before_final_write": time.perf_counter() - started, "CPU_s_before_final_write": time.process_time() - cpu,
              "bootstrap_to_report_wall_s": time.perf_counter() - BOOT_WALL, "bootstrap_to_report_CPU_s": time.process_time() - BOOT_CPU,
              "own_process_before_report": process_resources(), "validation_label_arrays_read": 0,
              "new_training_or_network_forwards": 0}
    write("CALIBRATION.json", report)
    record(HERE / "CALIBRATION.json")
    write("CALIBRATION_FREEZE.json", {"cycle_id": report["cycle_id"], "before_validation_label_evaluation": True,
          "files": list(identities.values())})
    print(json.dumps({"status": report["status"], "threshold": threshold, "false_development_normals": len(false)}))


if __name__ == "__main__":
    main()

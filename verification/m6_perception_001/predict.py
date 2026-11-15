"""Infer the frozen final head on label-free validation feature caches."""

import time
BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()

import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from head import PerceptionHead, configure_torch, file_record, measure, process_resources, save_predictions, write_json
import numpy as np
import torch


def main():
    started, cpu = time.perf_counter(), time.process_time()
    configure_torch()
    if (HERE / "PREDICTIONS_VALIDATION.json").exists():
        raise RuntimeError("validation_prediction_report_exists_inspect_before_recovery")
    timings = {}
    with measure(timings, "fixed_training_calibration_binding_read"):
        binding = json.loads((HERE / "CALIBRATION_BINDING.json").read_bytes())
        identity = json.loads((HERE / "MODEL_IDENTITY.json").read_bytes())
        training = json.loads((HERE / "TRAIN_LOG.json").read_bytes())
        features = json.loads((HERE / "FEATURES.json").read_bytes())
        if training["completed_steps"] != 1200 or training["status"] != "completed_exact1200_step_head_training":
            raise ValueError("final1200_step_training_required")
        selected = sorted([case for case in features["cases"] if case["purpose"] == "validation"], key=lambda row: row["id"])
        if len(selected) != 117:
            raise ValueError("fixed117_validation_feature_cases_required")
    with measure(timings, "normalization_and_final_head_load"):
        checkpoint_record = training["final_checkpoint"]
        if file_record(checkpoint_record["path"])["sha256"] != identity["head_final_sha256"]:
            raise ValueError("final_head_file_changed")
        checkpoint = torch.load(checkpoint_record["path"], map_location="cpu", weights_only=True)
        model = PerceptionHead().cpu().eval()
        model.load_state_dict(checkpoint["state_dict"], strict=True)
        path = training["normalization"]["path"]
        if file_record(path)["sha256"] != identity["normalization_sha256"]:
            raise ValueError("normalization_file_changed")
        with np.load(path, allow_pickle=False) as package:
            normalization = {name: package[name].copy() for name in ("mean", "divisor")}
    predictions = save_predictions(selected, model, normalization, "PREDICTIONS_VALIDATION.json", timings, identity["head_final_sha256"])
    predictions.update(calibration_binding=binding, wall_s_before_final_report=time.perf_counter() - started,
                       CPU_s_before_final_report=time.process_time() - cpu,
                       bootstrap_wall_s_before_final_report=time.perf_counter() - BOOT_WALL,
                       bootstrap_CPU_s_before_final_report=time.process_time() - BOOT_CPU,
                       own_process_before_report=process_resources())
    write_json("PREDICTIONS_VALIDATION.json", predictions)
    development = json.loads((HERE / "PREDICTIONS_DEVELOPMENT.json").read_bytes())
    all_cases = sorted(development["cases"] + predictions["cases"], key=lambda row: row["id"])
    if len(all_cases) != 348 or len({row["id"] for row in all_cases}) != 348:
        raise ValueError("full_prediction_union_not348")
    write_json("PREDICTIONS.json", {"cycle_id": "M6-PERCEPTION-001", "status": "completed_fixed348_final_head_predictions",
               "cases": all_cases, "case_count": 348, "development_cases": 231, "validation_cases": 117,
               "head_final_sha256": identity["head_final_sha256"], "normalization_sha256": identity["normalization_sha256"],
               "calibration_binding": binding, "validation_reference_or_label_arrays_read": 0,
               "encoder_or_decoder_forwards_in_this_phase": 0, "repair_outputs": 0})
    print(json.dumps({"validation_cases": 117, "all_prediction_cases": 348, "label_arrays_read": 0}))


if __name__ == "__main__":
    main()

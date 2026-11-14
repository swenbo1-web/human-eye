"""Preserve the existing evaluator's metre-frame boundary on native-unit data."""
import hashlib
import importlib.util
import json
from pathlib import Path
import time

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    started, cpu_started = time.perf_counter(), time.process_time()
    results = json.loads((HERE / "RESULTS.json").read_bytes())
    validation = [case for case in results["model_cases"] if case["purpose"] == "validation"]
    selected = []
    for position in ("center", "offcenter"):
        rows = [case for case in validation if case["position_group"] == position and not case["normal_control"]]
        selected.append(max(rows, key=lambda case: (case["support_rmse_ratio_to_noop"], case["id"])))
    selected.append(max((case for case in validation if case["normal_control"]), key=lambda case: (case["errors"]["N"]["max_over_scale"], case["id"])))
    chosen = selected[0]
    with np.load(HERE / "private/public_data/sources/Stanford_Armadillo/snapshot.npz", allow_pickle=False) as saved:
        source, triangles = saved["vertices"], saved["triangles"]
    with np.load(chosen["mapping_path"], allow_pickle=False) as saved:
        context, allowed = saved["context_source_ids"], saved["allowed_source_ids"]
    before = source.copy()
    before[context] = np.load(chosen["observed_path"], allow_pickle=False)
    after = before.copy()
    after[context] = np.load(chosen["candidate_path"], allow_pickle=False)
    evaluator = ROOT / "verification/m6_coupled_probe_002/evaluate.py"
    spec = importlib.util.spec_from_file_location("unchanged_coupled002_native_domain_probe", evaluator)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    packet = {"state": {"source_id": "Stanford_Armadillo_saved_native", "frame": 1,
                         "coordinate_frame": "saved_native_binary64_physical_unit_unconfirmed"},
              "vertices_before": before.tolist(), "vertices_candidate": after.tolist(), "triangles": triangles.tolist(),
              "write_ids": allowed.tolist(), "target_vertices": None, "protected_ids": [], "shape_tolerance_m": 0.,
              "preservation_tolerance_m": 0., "require_no_new_intersections": True}
    value, prepared, scanned = module.evaluate(packet, deadline=time.perf_counter() + 60)
    assert value["joint_status"] == "invalid" and value["reason"] == "coordinate_semantics"
    assert prepared is None and scanned is None
    output = {"cycle_id": "M6-SHAPE-TRAIN-001", "status": "unknown_outside_existing_coordinate_domain",
              "attempted_case": chosen["id"], "preselected_case_ids": [case["id"] for case in selected],
              "evaluator_validation_calls": 1, "endpoint_surface_queries": 0, "remaining_cases_not_queried": 2,
              "remaining_reason": "same native-unit source and same rejected coordinate semantics",
              "evaluator": str(evaluator), "evaluator_sha256": hashlib.sha256(evaluator.read_bytes()).hexdigest(),
              "supplied_coordinate_frame": packet["state"]["coordinate_frame"], "required_frame": "saved_world_binary64_m",
              "physical_unit_established": False, "unit_conversion_or_evaluator_modification": False,
              "result": value, "complete_coupling_acceptance": None,
              "wall_s": time.perf_counter() - started, "cpu_s": time.process_time() - cpu_started}
    (HERE / "COUPLING_STATUS.json").write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": output["status"], "reason": value["reason"], "endpoint_queries": 0}))


if __name__ == "__main__":
    main()

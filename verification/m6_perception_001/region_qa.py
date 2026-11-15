"""Synthetic arithmetic and empty-report checks for the region contract."""

import time
BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()

from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np
from region_common import (components, file_identity, geometry_facts, model_identity_values,
                           process_resources, reference_for, source_ids_digest, write_json)
from regions import compact_text


def main():
    started, cpu = time.perf_counter(), time.process_time()
    checks = []

    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})

    selected = np.array([True, True, False, True, True])
    edges = np.array([[0, 1, 2, 3], [1, 2, 3, 4]], dtype=np.int64)
    groups = components(selected, edges)
    check("selected_source_topology_components", [row.tolist() for row in groups] == [[0, 1], [3, 4]])
    check("empty_components", components(np.zeros(5, dtype=bool), edges) == [])
    check("isolated_selected_points", [row.tolist() for row in components(np.array([True, False, True]), np.empty((2, 0), dtype=np.int64))] == [[0], [2]])
    points = np.array([[0.0, 0.0, 0.0], [2.0, 1.0, 0.0]])
    facts = geometry_facts(points, np.array([1.0, 3.0]))
    check("area_weighted_centroid", np.allclose(facts["centroid_native"], [1.5, .75, 0.0]))
    check("current_bbox", facts["bbox_native"] == {"min": [0.0, 0.0, 0.0], "max": [2.0, 1.0, 0.0]})
    zero = geometry_facts(points, np.zeros(2))
    check("zero_area_centroid_fallback", zero["centroid_native"] == [1.0, .5, 0.0] and zero["centroid_definition"] == "vertex_mean_zero_area")
    ids = np.array([1, 7, 9], dtype=np.int64)
    check("ID_digest_fixed_endianness", source_ids_digest(ids) == source_ids_digest(ids.astype(">i8")))
    check("ID_digest_binds_members", source_ids_digest(ids) != source_ids_digest(np.array([1, 7, 10])))
    final_model = {"encoder_final_tensor_sha256": "1" * 64, "head_final_sha256": "2" * 64, "normalization_sha256": "3" * 64}
    canonical_model = model_identity_values(final_model)
    check("encoder_final_identity_alias", canonical_model["encoder_tensor_sha256"] == "1" * 64)
    identity = {"source_id": "synthetic_source", "observation_id": "synthetic_observation", "model": canonical_model,
                "selection_mode": "attention", "region_source_ids_sha256": source_ids_digest(ids)}
    reference = reference_for(identity)
    reordered = dict(reversed(list(identity.items())))
    check("reference_dictionary_order_invariant", reference_for(reordered) == reference)
    changed = dict(identity, selection_mode="threshold")
    check("reference_binds_selection_mode", reference_for(changed) != reference)
    changed_model = dict(canonical_model, head_final_sha256="4" * 64)
    check("reference_binds_head_identity", reference_for(dict(identity, model=changed_model)) != reference)
    check("reference_binds_observation", reference_for(dict(identity, observation_id="changed")) != reference)
    empty = {"source_id": "synthetic_source", "observation_id": "synthetic_observation",
             "inspection_scope": {"points": 5},
             "attention": {"region_count": 0, "selected_points": 0, "selected_area_fraction_of_F": 0.0,
                           "top_regions": [], "remaining_region_count": 0, "remaining_area_native": 0.0,
                           "remaining_area_fraction_of_F": 0.0},
             "threshold_anomaly_prediction": {"threshold": .9, "selected_points": 0, "region_count": 0},
             "full_region_catalog": {"path": "synthetic_fixture_only"}}
    text = compact_text(empty)
    check("empty_attention_readable", "注意力预算内候选为空" in text)
    check("empty_threshold_readable", "没有分数超过异常报告阈值" in text)
    check("prediction_separate_from_geometry", "属于模型预测" in text and "当前事实由保存的几何计算" in text)
    check("no_embedding_values_or_ground_truth_in_text", "embedding" not in text and "normal_control" not in text and "damaged_mask" not in text)
    failures = [row["name"] for row in checks if not row["passed"]]
    output = {"cycle_id": "M6-PERCEPTION-001", "status": "passed_synthetic_region_contract_QA" if not failures else "failed_synthetic_region_contract_QA",
              "check_count": len(checks), "checks": checks, "failures": failures,
              "scope": "synthetic I/O and arithmetic fixtures, no real observations or model computation",
              "real_case_reads": 0, "model_forwards": 0, "training": 0, "new_scores_or_repairs": 0,
              "source_sha256": {name: file_identity(HERE / name)["sha256"] for name in ("region_qa.py", "region_common.py", "regions.py")},
              "wall_s_before_final_report": time.perf_counter() - started, "CPU_s_before_final_report": time.process_time() - cpu,
              "bootstrap_to_report_wall_s": time.perf_counter() - BOOT_WALL, "bootstrap_to_report_CPU_s": time.process_time() - BOOT_CPU,
              "own_process_before_report": process_resources()}
    write_json("REGION_QA.json", output)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

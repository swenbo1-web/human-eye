"""Evaluate attention budgets and thresholded anomaly reports on the same F."""

import time
BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()

import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from perception_metrics import (CONFIGURATIONS, budget_selection, detection_metrics, distribution,
    measure, operation_summary, patch_macro, process_resources, rank_metrics)
import numpy as np


def write(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def summarize_group(rows, arrays, timings):
    result = {"requested_cases": len(rows), "normal_controls": sum(row["normal_control"] for row in rows),
              "dented_cases": sum(not row["normal_control"] for row in rows),
              "patches": len({row["patch_id"] for row in rows}), "sources": sorted({row["source"] for row in rows}),
              "F_points": sum(row["F_points"] for row in rows), "support_points": sum(row["support_points"] for row in rows),
              "strong_points": sum(row["strong_points"] for row in rows),
              "weak_damaged_as_strong_task_negative_points": sum(row["weak_damaged_as_strong_task_negative_points"] for row in rows),
              "configurations": {}, "B": {}}
    for configuration in CONFIGURATIONS:
        with measure(timings, "group_A_" + configuration):
            entry = {"requested_cases": len(rows),
                     "available_cases": sum(row["configurations"][configuration]["score_available"] for row in rows),
                     "unavailable_case_ids": [row["id"] for row in rows if not row["configurations"][configuration]["score_available"]],
                     "unavailable_points": sum(row["configurations"][configuration]["unavailable_points"] for row in rows),
                     "rank": {}, "A": {}}
            for task in ("support", "strong"):
                labels = np.concatenate([arrays[row["id"]][task] for row in rows]) if rows else np.empty(0, dtype=bool)
                scores = np.concatenate([arrays[row["id"]][configuration] for row in rows]) if rows else np.empty(0)
                entry["rank"][task] = {"point_pool": rank_metrics(labels, scores),
                    "per_case_ROC_AUC": distribution(row["configurations"][configuration]["rank"][task]["ROC_AUC"] for row in rows),
                    "per_case_AP": distribution(row["configurations"][configuration]["rank"][task]["AP"] for row in rows),
                    "patch_macro_ROC_AUC": patch_macro(rows, lambda row: row["configurations"][configuration]["rank"][task]["ROC_AUC"]),
                    "patch_macro_AP": patch_macro(rows, lambda row: row["configurations"][configuration]["rank"][task]["AP"])}
                entry["A"][task] = operation_summary([row["configurations"][configuration]["A"][task] for row in rows])
                entry["A"][task]["patch_macro_area_recall"] = patch_macro(rows,
                    lambda row: row["configurations"][configuration]["A"][task]["area_recall"])
            entry["A"]["per_case_budget_fraction"] = distribution(row["configurations"][configuration]["budget"]["actual_area_fraction"] for row in rows)
            entry["A"]["normal_candidates_are_confirmed_defects"] = False
            result["configurations"][configuration] = entry
    with measure(timings, "group_B_perception"):
        for task in ("support", "strong"):
            result["B"][task] = operation_summary([row["B"][task] for row in rows])
            result["B"][task]["patch_macro_area_recall"] = patch_macro(rows, lambda row: row["B"][task]["area_recall"])
        result["B"]["normal_false_patch_ids"] = sorted({row["patch_id"] for row in rows
            if row["normal_control"] and row["B"]["support"]["normal_case_any_selection"]})
        result["B"]["normal_false_case_ids"] = [row["id"] for row in rows
            if row["normal_control"] and row["B"]["support"]["normal_case_any_selection"]]
        result["B"]["empty_result_case_ids"] = [row["id"] for row in rows if row["B"]["selected_points"] == 0]
        result["B"]["per_case_selected_points"] = distribution(row["B"]["selected_points"] for row in rows)
        result["B"]["per_case_maximum_score"] = distribution(row["score_distribution"]["max"] for row in rows)
    return result


def decisions(groups):
    attention, anomaly = {}, {}
    for name in ("validation_center", "validation_offcenter"):
        configs = groups[name]["configurations"]
        proposed, baseline = configs["perception"], configs["old_p"]
        auc = proposed["rank"]["support"]["patch_macro_ROC_AUC"]["value"]
        ap = proposed["rank"]["support"]["patch_macro_AP"]["value"]
        baseline_ap = baseline["rank"]["support"]["patch_macro_AP"]["value"]
        recall = proposed["A"]["support"]["patch_macro_area_recall"]["value"]
        baseline_recall = baseline["A"]["support"]["patch_macro_area_recall"]["value"]
        values = {"patch_macro_AUC": auc, "patch_macro_AP": ap, "old_p_patch_macro_AP": baseline_ap,
                  "patch_macro_area_recall": recall, "old_p_patch_macro_area_recall": baseline_recall}
        gates = {"all_four_score_case_comparisons_available": all(result["available_cases"] == result["requested_cases"]
                 for result in configs.values()),
                 "patch_macro_AUC_ge080": auc is not None and auc >= .80,
                 "patch_macro_AP_gain_over_old_p_ge005": ap is not None and baseline_ap is not None and ap - baseline_ap >= .05,
                 "patch_macro_area_recall_ge060": recall is not None and recall >= .60,
                 "patch_macro_area_recall_gain_over_old_p_ge010": recall is not None and baseline_recall is not None and recall - baseline_recall >= .10}
        attention[name] = {"gates": gates, "values": values, "passed": all(gates.values())}
        b_recall = groups[name]["B"]["support"]["patch_macro_area_recall"]["value"]
        anomaly[name] = {"patch_macro_area_recall_ge060": b_recall is not None and b_recall >= .60,
                         "value": b_recall}
    normal = groups["validation_normal_controls"]
    false = len(normal["B"]["normal_false_patch_ids"])
    all_new_available = all(groups[name]["configurations"]["perception"]["available_cases"] == groups[name]["requested_cases"]
                            for name in ("validation_center", "validation_offcenter"))
    return {"A_attention": {"positions": attention, "passed": all(row["passed"] for row in attention.values()),
                            "scope": "25percent current F area attention allocation, candidates remain unconfirmed"},
            "B_abnormality": {"positions": anomaly, "validation_normal_false_patches": false,
                               "validation_normal_patches": normal["patches"],
                               "normal_false_patches_le1": false <= 1,
                               "all_new_prediction_cases_available": all_new_available,
                               "passed": all_new_available and false <= 1 and all(row["patch_macro_area_recall_ge060"] for row in anomaly.values()),
                               "scope": "fixed dependent-development-normal q95, score probability calibration unmeasured"}}


def main():
    started, cpu = time.perf_counter(), time.process_time()
    if (HERE / "EVALUATION.json").exists():
        raise RuntimeError("evaluation_exists_inspect_before_explicit_recovery")
    timings, identities = {}, {}

    def record(path, expected=None):
        path = Path(path)
        if not path.is_absolute():
            path = HERE / path
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if expected is not None and sha != expected:
            raise ValueError("evaluation_input_identity_changed_" + str(path))
        identities[str(path)] = {"path": str(path), "bytes": len(data), "sha256": sha}
        return path

    with measure(timings, "frozen_calibration_and_model_index_read"):
        binding = json.loads((HERE / "CALIBRATION_BINDING.json").read_bytes())
        for row in json.loads((HERE / "CALIBRATION_FREEZE.json").read_bytes())["files"]:
            record(row["path"], row["sha256"])
        calibration = json.loads((HERE / "CALIBRATION.json").read_bytes())
        threshold = calibration["threshold"]
        model_identity = json.loads(record(HERE / "MODEL_IDENTITY.json").read_bytes())
        predictions = json.loads(record(HERE / "PREDICTIONS.json").read_bytes())
        prediction_index = {row["id"]: row for row in predictions["cases"]}
        whitelist = json.loads((HERE / "INPUT_WHITELIST.json").read_bytes())
        selected_ids = {row["id"] for row in whitelist["cases"]}
        if len(selected_ids) != 348 or set(prediction_index) - selected_ids or len(prediction_index) != len(predictions["cases"]):
            raise ValueError("prediction_ids_outside_fixed348")
        ring = HERE.parent / "m6_shape_ring_001"
        residuals = json.loads(record(ring / "RESIDUALS.json").read_bytes())
        residual_index = {row["id"]: row for row in residuals["cases"]}
        ring_evaluation = json.loads(record(ring / "EVALUATION.json").read_bytes())
        ring_scores = {row["id"]: row for row in ring_evaluation["cases"]}
        old_cases = {}
        for path in (HERE.parent / "m6_shape_data_001/DATASET_INDEX.json", HERE.parent / "m6_shape_train_001/PUBLIC_DATASET_INDEX.json"):
            old_cases.update({row["id"]: row for row in json.loads(record(path).read_bytes())["cases"] if row["purpose"] != "reserved_test"})
        for path in (ring / "ring_metrics.py", ring / "evaluate.py"):
            record(path)
    rows, arrays, selections = [], {}, []
    for white in sorted(whitelist["cases"], key=lambda row: row["id"]):
        case_id = white["id"]
        old_case, residual_row, historical_row = old_cases[case_id], residual_index[case_id], ring_scores[case_id]
        with measure(timings, "current_geometry_cache_and_evaluation_labels_read"):
            with np.load(record(residual_row["path"], residual_row["sha256"]), allow_pickle=False) as saved:
                values = {key: saved[key].copy() for key in ("free_source_ids", "free_context_ids", "free_edge_index", "area")}
            source_ids, free_context, area, edge_index = (values[key] for key in ("free_source_ids", "free_context_ids", "area", "free_edge_index"))
            ell = residual_row["ell"]
            observed = np.load(record(white["observed"]["path"], white["observed"]["sha256"]), allow_pickle=False)
            folder = Path(white["observed"]["path"]).parents[1]
            reference = np.load(record(folder / "reference_local.npy"), allow_pickle=False)
            with np.load(record(white["mapping_path"]), allow_pickle=False) as saved:
                context = saved["context_source_ids"]
            if not np.array_equal(context[free_context], source_ids):
                raise ValueError("cached_F_source_mapping_mismatch")
            with np.load(record(old_case["labels"]["path"], old_case["labels"]["sha256"]), allow_pickle=False) as saved:
                support = saved["damaged_mask"].astype(bool)[free_context]
            strong = np.linalg.norm(reference[free_context] - observed[free_context], axis=1) > .10 * ell
        scores = {configuration: np.zeros(len(source_ids), dtype=np.float64) for configuration in CONFIGURATIONS}
        available = {configuration: False for configuration in CONFIGURATIONS}
        valid = np.zeros(len(source_ids), dtype=bool)
        with measure(timings, "new_prediction_read"):
            prediction = prediction_index.get(case_id)
            prediction_path = Path(prediction["path"]) if prediction else None
            if prediction_path is not None and not prediction_path.is_absolute():
                prediction_path = HERE / prediction_path
            if prediction_path is not None and prediction_path.exists():
                with np.load(record(prediction["path"], prediction["sha256"]), allow_pickle=False) as saved:
                    scores["perception"] = saved["scores"].reshape(-1).astype(np.float64)
                    valid = saved["valid_mask"].reshape(-1).astype(bool)
                    if not np.array_equal(saved["free_source_ids"], source_ids):
                        raise ValueError("prediction_F_source_mapping_mismatch")
                if scores["perception"].shape != area.shape or valid.shape != area.shape or not np.isfinite(scores["perception"]).all():
                    raise ValueError("invalid_perception_prediction_shape_or_score")
                if np.any(scores["perception"][~valid] != 0):
                    raise ValueError("unavailable_prediction_not_zero")
                available["perception"] = True
        with measure(timings, "three_frozen_baseline_scores_read"):
            path = Path(historical_row["score_path"])
            if path.exists():
                with np.load(record(path, historical_row["score_sha256"]), allow_pickle=False) as saved:
                    if not np.array_equal(saved["free_source_ids"], source_ids):
                        raise ValueError("baseline_F_source_mapping_mismatch")
                    for configuration in ("old_p", "solid_point", "ring_point"):
                        if configuration in saved.files:
                            scores[configuration] = saved[configuration].reshape(-1).astype(np.float64)
                            available[configuration] = historical_row["configurations"][configuration]["status"] == "available"
        row = {key: old_case.get(key) for key in ("id", "patch_id", "source", "source_group", "purpose", "stratum", "normal_control", "radius_ratio", "amplitude_ratio")}
        row.update(position_group=residual_row["position_group"], ell=ell, F_points=len(source_ids),
                   support_points=int(support.sum()), strong_points=int(strong.sum()),
                   weak_damaged_as_strong_task_negative_points=int(np.count_nonzero(support & ~strong)),
                   prediction_unavailable_points=int(np.count_nonzero(~valid)), configurations={})
        payload = {**values, "new_score": scores["perception"], "valid_mask": valid}
        for configuration in CONFIGURATIONS:
            with measure(timings, "case_A_evaluation_" + configuration):
                selected, budget = budget_selection(scores[configuration], source_ids, area)
                row["configurations"][configuration] = {"score_available": available[configuration],
                    "unavailable_points": int(np.count_nonzero(~valid)) if configuration == "perception" else (0 if available[configuration] else len(source_ids)),
                    "rank": {task: rank_metrics(label, scores[configuration]) for task, label in (("support", support), ("strong", strong))},
                    "budget": budget, "A": {task: detection_metrics(label, selected, area, ell, edge_index) for task, label in (("support", support), ("strong", strong))}}
                payload["attention_mask" if configuration == "perception" else "A_" + configuration + "_selected"] = selected
        with measure(timings, "case_B_evaluation_perception"):
            selected = scores["perception"] > threshold
            row["B"] = {task: detection_metrics(label, selected, area, ell, edge_index) for task, label in (("support", support), ("strong", strong))}
            row["B"].update(threshold=threshold, comparison="strictly_greater", selected_points=int(selected.sum()),
                            prediction_nature="model threshold decision, probability calibration unmeasured")
            row["score_distribution"] = distribution(scores["perception"])
            payload["abnormal_mask"] = selected
        with measure(timings, "selection_payload_save_and_hash"):
            patch, sample = case_id.split("/")
            path = HERE / "private/selections" / patch / (sample + ".npz")
            path.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(path, **payload)
            data = path.read_bytes()
            row.update(selection_path=str(path), selection_sha256=hashlib.sha256(data).hexdigest())
            selection_row = {key: row[key] for key in ("id", "patch_id", "source", "purpose", "normal_control", "position_group", "ell")}
            selection_row.update(path=str(path), sha256=row["selection_sha256"], bytes=len(data),
                                 observed_path=white["observed"]["path"], observed=white["observed"], mapping_path=white["mapping_path"],
                                 snapshot=white["snapshot"], model_identity=model_identity,
                                 attention_budget=row["configurations"]["perception"]["budget"], B_threshold=threshold)
            selections.append(selection_row)
        rows.append(row)
        arrays[case_id] = {"support": support, "strong": strong, **scores}
    groups = {"all": rows, "development_center": [row for row in rows if row["purpose"] == "development_train_pool"],
              "validation_center": [row for row in rows if row["purpose"] == "validation" and row["position_group"] == "center"],
              "validation_offcenter": [row for row in rows if row["purpose"] == "validation" and row["position_group"] == "offcenter"],
              "development_normal_controls": [row for row in rows if row["purpose"] == "development_train_pool" and row["normal_control"]],
              "validation_normal_controls": [row for row in rows if row["purpose"] == "validation" and row["normal_control"]]}
    for field in ("source", "patch_id", "stratum", "amplitude_ratio"):
        for value in sorted({row[field] for row in rows}, key=str):
            groups[field + "_" + str(value)] = [row for row in rows if row[field] == value]
    for name in ("development_center", "validation_center", "validation_offcenter"):
        for amplitude in (.05, .15, .3):
            groups[name + "_amplitude_" + str(amplitude)] = [row for row in groups[name] if row["amplitude_ratio"] == amplitude]
    summaries = {name: summarize_group(chosen, arrays, timings) for name, chosen in groups.items()}
    report = {"cycle_id": "M6-PERCEPTION-001", "status": "completed_fixed348_A_B_evaluation", "case_count": len(rows),
              "normal_controls": sum(row["normal_control"] for row in rows), "cases": rows, "configurations": list(CONFIGURATIONS),
              "groups": summaries, "decision_gates": decisions(summaries), "calibration_binding": binding,
              "model_identity": model_identity, "B_threshold": threshold,
              "metric_conventions": {"A": "25percent fullF current area prefix, descending scores ascending sourceIDs ties, stop at first excess",
                  "B": "strictly exceed one development33 normal patch-max linearq95 threshold",
                  "strong": "norm(reference-observed)>.10ell on same F, weak damaged negatives explicit",
                  "patch_macro": "average eligible case metrics within patch then equal mean patches, missing-class counts retained",
                  "gate_area_recall": "patch equal macro of case area recalls, both center and offcenter",
                  "mixed_source_native_area": "descriptive only, ell2 normalized pool also provided",
                  "unavailable": "fixed zero scores keep allF, baseline availability required for A gain gates",
                  "largest_missed_component": "damaged unselected inducedF component with maximum current native area, point count and ell2 area retained"},
              "timings": timings, "input_file_identities": list(identities.values()),
              "source_sha256": {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in ("evaluate.py", "perception_metrics.py")},
              "wall_s_before_final_report": time.perf_counter() - started, "CPU_s_before_final_report": time.process_time() - cpu,
              "bootstrap_to_report_wall_s": time.perf_counter() - BOOT_WALL, "bootstrap_to_report_CPU_s": time.process_time() - BOOT_CPU,
              "own_process_before_report": process_resources(), "training_or_neural_forwards_in_evaluation": 0,
              "Bunny_arrays": 0, "measurement_scope": "cached geometry/baselines reused with read/hash cost, every A/B score evaluation and labels separated, final serialization/write outside self window"}
    write("EVALUATION.json", report)
    write("SELECTION_INDEX.json", {"cycle_id": report["cycle_id"], "cases": selections, "case_count": len(selections),
          "B_threshold": threshold, "model_identity": model_identity,
          "model_identity_file": identities[str(HERE / "MODEL_IDENTITY.json")],
          "package_scope": "current geometry IDs, masks and scalar predictions only, embeddings and labels absent"})
    print(json.dumps({"status": report["status"], "cases": len(rows), "A_passed": report["decision_gates"]["A_attention"]["passed"],
                      "B_passed": report["decision_gates"]["B_abnormality"]["passed"]}))


if __name__ == "__main__":
    main()

"""Summarize the fixed hard candidate against immutable first-round and MLS data."""

import hashlib
import importlib.util
import json
from pathlib import Path
import time

import numpy as np


HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / "m6_shape_train_001"
_spec = importlib.util.spec_from_file_location("m6_train001_summary", PRIOR / "summarize_results.py")
_previous = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_previous)
quantiles = _previous.quantiles


def location_summary(rows):
    available = [row["classification"] for row in rows if row.get("classification") is not None]
    counts = {key: sum(item[key] for item in available) for key in ("TP", "FP", "FN", "TN")}
    tp, fp, fn, tn = (counts[key] for key in ("TP", "FP", "FN", "TN"))
    denominators = {"free": tp + fp + fn + tn, "selected": tp + fp,
                    "true_support": tp + fn, "normal_free": fp + tn}
    return {"cases": len(rows), "available_cases": len(available),
            "unavailable_case_ids": [row["id"] for row in rows if row.get("classification") is None],
            **counts, "denominators": denominators,
            "empty_denominators": [name for name, value in denominators.items() if not value],
            "pooled_precision": tp / (tp + fp) if tp + fp else None,
            "pooled_recall": tp / (tp + fn) if tp + fn else None,
            "pooled_FPR": fp / (fp + tn) if fp + tn else None,
            "per_case_precision": quantiles([item["precision"] for item in available if item["precision"] is not None]),
            "per_case_recall": quantiles([item["recall"] for item in available if item["recall"] is not None]),
            "per_case_FPR": quantiles([item["FPR"] for item in available if item["FPR"] is not None]),
            "scope": "pooled counts over free vertices; cases repeat source vertices across synthetic variants"}


def summarize(rows, with_location=False):
    result = _previous.summarize(rows)
    result["entire_context_bitwise_noop_cases"] = sum(row["entire_context_bitwise_noop"] for row in rows)
    result["actual_changed_free_vertices_sum_over_cases"] = sum(row["actual_changed_free_vertices"] for row in rows)
    result["region_error_quantiles"] = {
        domain: {metric: quantiles([row["errors"][domain][metric] for row in rows
                                   if row["errors"][domain][metric] is not None])
                 for metric in ("rmse_over_scale", "p95_over_scale", "max_over_scale")}
        for domain in ("A", "S", "N", "N_F")
    }
    if with_location:
        result["classification"] = location_summary(rows)
    if any("support_improvement_to_MLS" in row for row in rows):
        result["support_improvement_to_MLS"] = quantiles([row["support_improvement_to_MLS"] for row in rows
                                                         if row.get("support_improvement_to_MLS") is not None])
    return result


def selections_for(rows):
    selections = {
        "development_center": [row["id"] for row in rows if row["purpose"] == "development_train_pool"],
        "validation_center": [row["id"] for row in rows if row["purpose"] == "validation" and row["position_group"] == "center"],
        "validation_offcenter": [row["id"] for row in rows if row["purpose"] == "validation" and row["position_group"] == "offcenter"],
        "development_normal_controls": [row["id"] for row in rows if row["purpose"] == "development_train_pool" and row["normal_control"]],
        "validation_normal_controls": [row["id"] for row in rows if row["purpose"] == "validation" and row["normal_control"]],
    }
    for purpose in ("development_train_pool", "validation"):
        prefix = "development" if purpose == "development_train_pool" else "validation"
        for source in sorted({row["source"] for row in rows if row["purpose"] == purpose}):
            selections[prefix + "_source_" + source] = [row["id"] for row in rows if row["purpose"] == purpose and row["source"] == source]
        for position in ("center", "offcenter"):
            for radius in (.35, .55):
                for amplitude in (.05, .15, .3):
                    ids = [row["id"] for row in rows if row["purpose"] == purpose
                           and row["position_group"] == position and row["radius_ratio"] == radius
                           and row["amplitude_ratio"] == amplitude]
                    if ids:
                        selections[f"{prefix}_{position}_r{radius}_a{amplitude}"] = ids
    return selections


def quality_gates(summary, rows):
    ratio = summary["support_RMSE_ratio_to_noop"]
    dents = [row for row in rows if not row["normal_control"]]
    member_medians = {source: float(np.median([row["support_rmse_ratio_to_noop"] for row in dents if row["source"] == source]))
                      for source in sorted({row["source"] for row in dents})}
    gates = {"support_median_070": ratio["median"] <= .70,
             "source_file_median_085": all(value <= .85 for value in member_medians.values()),
             "support_p95_105": ratio["p95"] <= 1.05, "support_worst_125": ratio["max"] <= 1.25,
             "allowed_median_improvement_020": summary["allowed_improvement_to_noop"]["median"] >= .20,
             "MLS_median_improvement_010": summary["support_improvement_to_MLS"]["median"] >= .10,
             "normal_point_preservation": summary["normal_point_gate_failures"] == 0,
             "normal_controls": summary["normal_control_gate_failures"] == 0 if summary["controls"] else None,
             "no_new_degenerate_or_reversed_faces": summary["face_quality_failed_cases"] == 0,
             "incident_coverage_complete": summary["incident_coverage_complete"],
             "bitwise_fixed": summary["all_fixed_and_boundary_bitwise_preserved"],
             "no_inference_fallback": summary["whole_case_noop_fallbacks"] == 0}
    return gates, member_medians


def main():
    started = time.perf_counter()
    final = json.loads((HERE / "EVAL_FINAL_HARD.json").read_bytes())
    original_bytes = (PRIOR / "RESULTS.json").read_bytes()
    original = json.loads(original_bytes)
    training = json.loads((HERE / "TRAIN_LOG.json").read_bytes())
    calibration_bytes = (HERE / "LOC_CALIBRATION.json").read_bytes()
    calibration = json.loads(calibration_bytes)
    if final["step"] != 1200 or training["steps_completed"] != 1200 or final["output_mode"] != "hard":
        raise ValueError("summary_requires_final_fixed_hard_candidate")
    if final["weights_sha256"] != training["final_weights"]["sha256"] or final["tau"] != calibration["tau"]:
        raise ValueError("summary_identity_mismatch")
    model = final["development"]["cases"] + final["validation"]["cases"]
    baseline = original["baseline_cases"]
    first_round = original["model_cases"]
    if len(model) != 348 or len({row["id"] for row in model}) != 348:
        raise ValueError("hard_summary_case_denominator_mismatch")
    baseline_lookup = {row["id"]: row for row in baseline}
    if set(baseline_lookup) != {row["id"] for row in model} or {row["id"] for row in first_round} != set(baseline_lookup):
        raise ValueError("comparison_case_identity_mismatch")
    for row in model:
        row["support_improvement_to_MLS"] = None
        if not row["normal_control"]:
            denominator = baseline_lookup[row["id"]]["mls"]["errors"]["S"]["rmse_native"]
            error = row["errors"]["S"]["rmse_native"]
            floor = 1e-6 * row["scale_native"]
            row["support_improvement_to_MLS"] = (0. if error <= floor else -error / floor) if denominator <= floor else 1 - error / denominator
    selections = selections_for(model)
    summaries, gates, member_medians = {}, {}, {}
    for name, ids in selections.items():
        selected = set(ids)
        rows = [row for row in model if row["id"] in selected]
        summaries[name] = {
            "model": summarize(rows, with_location=True),
            "first_round": summarize([row for row in first_round if row["id"] in selected]),
            "mls": summarize([row["mls"] for row in baseline if row["id"] in selected]),
            "no_op": summarize([row["no_op"] for row in baseline if row["id"] in selected]),
        }
        if name in ("development_center", "validation_center", "validation_offcenter"):
            gates[name], member_medians[name] = quality_gates(summaries[name]["model"], rows)
    passed = all(value is not False for group in gates.values() for value in group.values())
    decision = "local_quality_candidate_pending_independent_review" if passed else "close_current_learning_candidate_after_one_optimization"
    result = {"cycle_id": "M6-SHAPE-OPT-001", "step": 1200, "weight": training["final_weights"],
              "tau": calibration["tau"], "calibration_count": calibration["calibration_count"],
              "calibration_sha256": hashlib.sha256(calibration_bytes).hexdigest(),
              "model_cases": model, "first_round_cases": first_round, "baseline_cases": baseline,
              "comparison_prior_commit": "9c29a9f0990421c607ee821e838394e73dcaa9f3",
              "comparison_prior_results_sha256": hashlib.sha256(original_bytes).hexdigest(),
              "selections": selections, "summaries": summaries, "quality_gates": gates,
              "source_file_support_medians": member_medians, "all_quality_gates_passed": passed,
              "offcenter_control_applicability": "same nine validation controls counted under center, no additional normal controls",
              "Bunny_model_or_MLS_scores": 0, "optimization_training_runs": 1,
              "decision": decision,
              "full_repair_acceptance": "unknown; complete coupling and reserved-test evaluation remain pending",
              "native_physical_unit": "unconfirmed for Stanford sources",
              "summary_wall_s": time.perf_counter() - started}
    (HERE / "RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"decision": decision, "quality_passed": passed,
                      "groups": {name: {"support": summaries[name]["model"]["support_RMSE_ratio_to_noop"],
                                        "allowed_improvement": summaries[name]["model"]["allowed_improvement_to_noop"],
                                        "classification": summaries[name]["model"]["classification"]}
                                 for name in gates}}, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Aggregate fixed final-step outcomes without changing model or data selection."""
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent


def quantiles(values):
    if not values:
        return {"count": 0, "median": None, "p95": None, "max": None}
    return {"count": len(values), "median": float(np.median(values)), "p95": float(np.quantile(values, .95)), "max": float(max(values))}


def summarize(rows):
    dented = [case for case in rows if not case["normal_control"]]
    controls = [case for case in rows if case["normal_control"]]
    normal_failures = []
    control_failures = []
    for case in rows:
        if any(case["errors"][mask]["count"] and (case["errors"][mask]["p95_over_scale"] > .02 or case["errors"][mask]["max_over_scale"] > .10) for mask in ("N", "N_F")):
            normal_failures.append(case["id"])
    for case in controls:
        error = case["errors"]["A"]
        if error["rmse_over_scale"] > .01 or error["p95_over_scale"] > .02 or error["max_over_scale"] > .05:
            control_failures.append(case["id"])
    normal_sse_fractions = []
    for case in dented:
        total = case["errors"]["A"]["rmse_native"] ** 2 * case["errors"]["A"]["count"]
        normal = case["errors"]["N"]["rmse_native"] ** 2 * case["errors"]["N"]["count"]
        if total > 0:
            normal_sse_fractions.append(normal / total)
    ratios = [case["support_rmse_ratio_to_noop"] for case in dented]
    improvement = [case["allowed_improvement_to_noop"] for case in dented]
    return {"cases": len(rows), "dented": len(dented), "controls": len(controls),
            "support_RMSE_ratio_to_noop": quantiles(ratios), "dented_support_improved_cases": sum(ratio < 1 for ratio in ratios),
            "allowed_improvement_to_noop": quantiles(improvement),
            "normal_point_gate_failures": len(normal_failures), "normal_point_gate_failed_case_ids": normal_failures,
            "normal_control_gate_failures": len(control_failures), "normal_control_gate_failed_case_ids": control_failures,
            "normal_control_RMSE_over_scale": quantiles([case["errors"]["A"]["rmse_over_scale"] for case in controls]),
            "normal_free_p95_over_scale_worst": max((case["errors"]["N_F"]["p95_over_scale"] for case in rows), default=None),
            "normal_free_max_over_scale_worst": max((case["errors"]["N_F"]["max_over_scale"] for case in rows), default=None),
            "normal_point_fraction_of_final_squared_error": quantiles(normal_sse_fractions),
            "new_degenerate_faces_sum_over_cases": sum(case["incident_quality"]["new_degenerate_faces"] for case in rows),
            "normal_reversals_from_input_sum_over_cases": sum(case["incident_quality"]["normal_reversals_from_input"] for case in rows),
            "face_quality_failed_cases": sum(case["incident_quality"]["new_degenerate_faces"] > 0 or case["incident_quality"]["normal_reversals_from_input"] > 0 for case in rows),
            "incident_coverage_complete": all(case["incident_quality"]["complete"] for case in rows),
            "all_fixed_and_boundary_bitwise_preserved": all(case["fixed_bitwise_preserved"] and case["boundary_bitwise_preserved"] and case["outside_allowed_bitwise_preserved"] for case in rows),
            "whole_case_noop_fallbacks": sum(case["fallback_noop"] for case in rows)}


def main():
    final = json.loads((HERE / "EVAL_STEP_1200.json").read_bytes())
    baselines = json.loads((HERE / "BASELINE_RESULTS.json").read_bytes())
    training = json.loads((HERE / "TRAIN_LOG.json").read_bytes())
    assert training["steps_completed"] == final["step"] == 1200
    model = final["development"]["cases"] + final["validation"]["cases"]
    baseline = baselines["development"]["cases"] + baselines["validation"]["cases"]
    lookup = {case["id"]: case for case in baseline}
    for case in model:
        if case["normal_control"]:
            case["support_improvement_to_MLS"] = None
            continue
        denominator = lookup[case["id"]]["mls"]["errors"]["S"]["rmse_native"]
        error = case["errors"]["S"]["rmse_native"]
        floor = 1e-6 * case["scale_native"]
        case["support_improvement_to_MLS"] = (0. if error <= floor else -error / floor) if denominator <= floor else 1 - error / denominator
    selections = {"development_center": [case["id"] for case in model if case["purpose"] == "development_train_pool"],
                  "validation_center": [case["id"] for case in model if case["purpose"] == "validation" and case["position_group"] == "center"],
                  "validation_offcenter": [case["id"] for case in model if case["purpose"] == "validation" and case["position_group"] == "offcenter"]}
    for source in ("Yanyite", "Richie", "Chipow", "Yunhex"):
        selections["development_" + source] = [case["id"] for case in model if case["source"] == source]
    for position in ("center", "offcenter"):
        for radius in (.35, .55):
            for amplitude in (.05, .15, .3):
                selections[f"validation_{position}_r{radius}_a{amplitude}"] = [case["id"] for case in model if case["purpose"] == "validation" and case["position_group"] == position and case["radius_ratio"] == radius and case["amplitude_ratio"] == amplitude]
    summaries = {}
    for name, ids in selections.items():
        selected = set(ids)
        rows = [case for case in model if case["id"] in selected]
        model_summary = summarize(rows)
        model_summary["support_improvement_to_MLS"] = quantiles([case["support_improvement_to_MLS"] for case in rows if not case["normal_control"]])
        summaries[name] = {"model": model_summary,
                           "mls": summarize([case["mls"] for case in baseline if case["id"] in selected]),
                           "no_op": summarize([case["no_op"] for case in baseline if case["id"] in selected])}
    gates = {}
    for name in ("development_center", "validation_center", "validation_offcenter"):
        value = summaries[name]["model"]
        ratio = value["support_RMSE_ratio_to_noop"]
        subset = [case for case in model if case["id"] in set(selections[name]) and not case["normal_control"]]
        member_medians = {source: float(np.median([case["support_rmse_ratio_to_noop"] for case in subset if case["source"] == source])) for source in sorted({case["source"] for case in subset})}
        gates[name] = {"support_median_070": ratio["median"] <= .70,
                       "source_file_median_085": all(value <= .85 for value in member_medians.values()),
                       "support_p95_105": ratio["p95"] <= 1.05, "support_worst_125": ratio["max"] <= 1.25,
                       "allowed_median_improvement_020": value["allowed_improvement_to_noop"]["median"] >= .20,
                       "MLS_median_improvement_010": value["support_improvement_to_MLS"]["median"] >= .10,
                       "normal_point_preservation": value["normal_point_gate_failures"] == 0,
                       "normal_controls": value["normal_control_gate_failures"] == 0 if value["controls"] else None,
                       "no_new_degenerate_or_reversed_faces": value["face_quality_failed_cases"] == 0,
                       "bitwise_fixed": value["all_fixed_and_boundary_bitwise_preserved"],
                       "no_inference_fallback": value["whole_case_noop_fallbacks"] == 0}
    result = {"cycle_id": "M6-SHAPE-TRAIN-001", "weight": training["final_weights"], "step": 1200,
              "model_cases": model, "baseline_cases": baseline, "summaries": summaries, "quality_gates": gates,
              "all_quality_gates_passed": all(all(value for value in group.values() if value is not None) for group in gates.values()),
              "offcenter_control_applicability": "same9validation controls counted under center, no extra normal controls created",
              "Bunny_model_or_MLS_scores": 0,
              "most_valuable_optimization_problem": "Preserve originally normal free vertices while correcting dents; current broad corrections also introduce face-normal reversals.",
              "center_pressure_observation": "Offcenter support ratios are better than center in this pressure set; normal-point preservation is the strongest demonstrated gap, with no arbitrary-location generalization claim.",
              "full_repair_acceptance": "not_passed; quality gates fail and complete all-case coupling/product evaluation is not established"}
    (HERE / "RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({name: {"cases": summaries[name]["model"]["cases"], "support_median": summaries[name]["model"]["support_RMSE_ratio_to_noop"]["median"],
                            "allowed_improvement_median": summaries[name]["model"]["allowed_improvement_to_noop"]["median"]}
                      for name in ("development_center", "validation_center", "validation_offcenter")}, ensure_ascii=False))


if __name__ == "__main__":
    main()

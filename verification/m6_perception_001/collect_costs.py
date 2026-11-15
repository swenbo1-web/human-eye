"""Collect the complete frozen-encoder perception pipeline and audit costs."""

import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE / name).read_bytes())


def main():
    started, cpu = time.perf_counter(), time.process_time()
    phases = {}
    for path in sorted((HERE / "private/processes").glob("*.controller.json")):
        label = path.name.removesuffix(".controller.json")
        phases[label] = {"controller": json.loads(path.read_bytes()),
                         "worker_tree": read("private/processes/" + label + ".json")}
    nested = {}
    names = ("ENVIRONMENT.json", "FEATURES.json", "NORMALIZATION.json", "TRAIN_LOG.json",
             "PREDICTIONS_DEVELOPMENT.json", "PREDICTIONS_VALIDATION.json", "CALIBRATION.json", "EVALUATION.json",
             "REGION_REPORTS.json", "REGION_QA.json", "REGION_VERIFY.json", "INDEPENDENT_VERIFY.json", "SUMMARY.json")
    for name in names:
        if (HERE / name).exists():
            value = read(name)
            nested[name] = {key: row for key, row in value.items()
                            if any(word in key.lower() for word in ("timing", "wall", "cpu", "process", "resource", "cache", "measurement", "cost"))}
    features = read("FEATURES.json")
    training = read("TRAIN_LOG.json")
    identity = read("MODEL_IDENTITY.json")
    per_case = {}
    for row in features["cases"]:
        per_case[row["id"]] = {"encoder_data_preparation_extraction_and_cache_wall_s": row["full_case_wall_s"],
                              "encoder_stage_timings": row["timings"]}
    for filename in ("PREDICTIONS_DEVELOPMENT.json", "PREDICTIONS_VALIDATION.json"):
        if (HERE / filename).exists():
            for row in read(filename)["cases"]:
                per_case[row["id"]]["head_prediction_recorded_cost"] = {
                    key: value for key, value in row.items() if any(word in key.lower() for word in ("timing", "wall", "cpu", "resource"))}
    if (HERE / "REGION_REPORTS.json").exists():
        for row in read("REGION_REPORTS.json")["cases"]:
            per_case[row["id"]]["region_aggregation_and_facts_cost"] = {
                key: value for key, value in row.items() if any(word in key.lower() for word in ("timing", "wall", "cpu", "resource"))}
    private = [path for path in (HERE / "private").rglob("*") if path.is_file()]
    report = {"cycle_id": "M6-PERCEPTION-001", "phases": phases,
              "sequential_controller_wall_sum_s": sum(row["controller"]["main_wall_s_including_worker_before_write"] for row in phases.values()),
              "worker_tree_CPU_sum_s": sum(row["worker_tree"]["tree_cpu_s"] for row in phases.values()),
              "controller_lifetime_CPU_sum_s": sum(row["controller"]["process_lifetime_before_final_write"]["cpu_s"] for row in phases.values()),
              "maximum_sampled_tree_RSS_bytes": max(row["worker_tree"]["tree_sampled_peak_working_set_bytes"] for row in phases.values()),
              "nested_reports": nested, "per_case_complete_inference_components": per_case,
              "inference_scope": "percase current-source read/index/PCA/sampling/encoder/cache, head load/prediction and region facts retained; global imports/model load and training/evaluation/QA windows separately recorded",
              "cache_accounting": "encoder features extracted once and consumed by1200 head steps, first extraction/cache cost remains included; no head-only latency claim",
              "aggregation": "root phases sequential, nested stages included within outer phase, shared imports and model loads counted once per actual process, do not sum nested costs twice",
              "preparation": {"plan_metadata_and_contract_copy": read("PLAN.json")["preparation"],
                  "read_thread_argument_recovery": "first22000 char limit rejected,18000 succeeded before registration, no scientific computation",
                  "delegation_limit_recovery": "new QA agent hit thread limit, existing evaluation agent reused for internal formula verification",
                  "model_agent_AST_command_wall_s": [0.1624981, 0.1593728, 0.2158388],
                  "model_agent_early_missing_directory": "functions outer1.6s, nested wall/CPU/peak unknown, arrays/forwards0",
                  "model_agent_cross_module_source_reads_outer_wall_s": [1.7, 1.8, 1.6],
                  "evaluation_agent_AST_command_wall_s": [0.1717891, 0.2274008],
                  "evaluation_agent_verifier_AST_command_wall_s": 0.1744726,
                  "evaluation_agent_actual_JSON_review_command_wall_s": [0.2157131, 0.2268422],
                  "model_agent_actual_identity_and_group_review_command_wall_s": [0.2313429, 0.2280618],
                  "final_model_report_review_command_wall_s": [0.1835574, 0.1846546, 0.1633931],
                  "final_model_report_review_recovery": "one pure-JSON KeyError0 from indexing cost dictionary as list, corrected to dictionary schema, no array/forward/training",
                  "final_evaluation_report_review": {"checks": 308, "tool_wall_s": [0.18666, 0.2271105], "new_scientific_runs": 0},
                  "final_region_report_review_command_wall_s": 0.2037878,
                  "region_agent_missing_directory_read_wall_s": 0.2797022,
                  "region_agent_AST_command_wall_s": [0.2048865, 0.2123597],
                  "region_presentation_refinement_known_command_wall_s": [0.1605974, 0.1629822, 0.1581446],
                  "missing": "preparation/read command CPU/peak and some nested walls, complete authoring/tool/model interaction and money"},
              "failures_and_recovery": {"phase_failures": [label for label, row in phases.items() if row["worker_tree"]["returncode"] != 0],
                  "invalid_feature_query_records": features.get("failures", []),
                  "presentation_refinement": read("REGION_REFINEMENT.json"),
                  "extra_recovery": read("RECOVERY.json") if (HERE / "RECOVERY.json").exists() else None},
              "actual_scope": {"cases": 348, "F_point_observations": 109443, "head_training_runs": identity["training_runs"],
                  "head_training_steps": identity["head_steps"], "encoder_parameters_trained": 0,
                  "encoder_forward_batches": features["encoder_forward_batches"], "decoder_forward_calls": identity["decoder_forward_calls"],
                  "feature_encoder_valid_query_points": sum(row["valid_points"] for row in features["cases"]),
                  "feature_unavailable_query_points_fixed_zero": sum(row["unavailable_points"] for row in features["cases"]),
                  "verification_existing_encoder_query_replays": read("INDEPENDENT_VERIFY.json")["coverage"]["encoder_existing_query_replays"],
                  "verification_optimizer_step_replays": 0,
                  "repair_outputs": 0, "other_candidate_training_or_seed_search": 0, "Bunny_arrays_or_scores": 0,
                  "LLM_consumer_or_product_integration": 0, "Blender_or_original_assets": 0, "Google_Key_API_or_paid_calls": 0,
                  "dependency_installations": 0},
              "storage": {"private_files": len(private), "private_bytes": sum(path.stat().st_size for path in private)},
              "limits": "singlethread existing CPU environment, exclusivity unverified; process discovery and simultaneous peaks sampled50ms; self final write/exit outside some windows",
              "missing": ["complete product and LLM task-net-benefit performance", "formal speedup comparison", "some preparation CPU/peak and complete authoring/money"],
              "collector_wall_s_before_write": time.perf_counter() - started,
              "collector_CPU_s_before_write": time.process_time() - cpu,
              "final_integrity_cost_reference": "FINAL_CHECKS.json"}
    (HERE / "COSTS.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"phases": len(phases), "wall_s": report["sequential_controller_wall_sum_s"],
                      "CPU_s": report["worker_tree_CPU_sum_s"], "sampled_peak_RSS": report["maximum_sampled_tree_RSS_bytes"]}))


if __name__ == "__main__":
    main()

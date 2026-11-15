"""Check saved evidence and inventory this batch without rerunning geometry."""

import ast
import hashlib
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE / name).read_bytes())


def identity(path):
    data = path.read_bytes()
    return {"path": path.relative_to(HERE).as_posix(), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def write(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                             encoding="utf-8", newline="\n")


def main():
    started, cpu = time.perf_counter(), time.process_time()
    checks = []

    def check(name, passed):
        checks.append({"name": name, "passed": bool(passed)})
        if not passed:
            raise ValueError(name)

    plan = read("PLAN.json")
    frozen = read("PLAN_FREEZE.json")
    for row in frozen["files"]:
        check("frozen_" + row["path"], identity(HERE / row["path"])["sha256"] == row["sha256"])
    for path in sorted(HERE.glob("*.py")):
        ast.parse(path.read_bytes(), filename=str(path))
    check("all_public_Python_sources_parse", True)

    decomposition = read("DECOMPOSITION.json")
    surface = read("SURFACE_RESULTS.json")
    qa = read("METER_QA.json")
    verification = read("INDEPENDENT_VERIFY.json")
    repair = read("SURFACE_METADATA_REPAIR.json")
    summary = read("SUMMARY.json")
    costs = read("COSTS.json")
    reused = read("REUSED_INPUTS.json")
    check("306_decomposition_cases", len(decomposition["cases"]) == 306 and not decomposition["failures"])
    denominator = decomposition["summaries"]["all"]["denominators"]
    check("10767_support_points_all_valid", denominator["support_points"] == 10767
          and denominator["decomposable_points"] == 10767
          and denominator["invalid_normal_points"] == 0 and denominator["nonfinite_target_points"] == 0)
    check("54_decomposition_summary_groups", len(decomposition["summaries"]) == 54)
    check("34_meter_QA_checks", qa["status"] == "passed_synthetic_metric_QA"
          and len(qa["checks"]) == 34 and all(row["passed"] for row in qa["checks"]))
    for name, expected in qa["source_sha256"].items():
        check("QA_source_" + name, identity(HERE / name)["sha256"] == expected)
    check("six_cases_24_saved_candidates", len(surface["cases"]) == 6
          and sum(len(case["methods"]) for case in surface["cases"]) == 24)
    directions = [method[direction] for case in surface["cases"] for method in case["methods"].values()
                  for direction in ("candidate_to_reference", "reference_to_candidate")]
    check("48_directions_18432_saved_queries", len(directions) == 48
          and sum(row["query_points"] for row in directions) == 18432)
    check("all_directions_complete", all(row["distance"]["complete"]
          and row["distance"]["valid_points"] == 384 for row in directions))
    check("all_10_domain_counters_populated", all(len(row["metric_domain_diagnostics"]) == 10 for row in directions))
    check("zero_cut_boundary_hits", summary["cut_boundary_hits_all_48_directions"] == 0)
    check("saved_surface_domain_retained", not surface["triangle_domain_expanded"]
          and not surface["full_source_geometry_used_for_distances"])
    for row in directions:
        check("saved_detail_" + Path(row["detail_path"]).relative_to(HERE).as_posix(),
              hashlib.sha256(Path(row["detail_path"]).read_bytes()).hexdigest() == row["detail_sha256"])
    check("metadata_repair_no_distance_or_boundary_requery", repair["new_nearest_points_calls"] == 0
          and repair["new_boundary_queries"] == 0 and repair["original_48_distance_details_unchanged"])
    check("metadata_repair_scientific_payload_unchanged",
          repair["original_scientific_payload_sha256"] == repair["postrepair_scientific_payload_sha256"])
    for path_key, sha_key in (("original_report_path", "original_report_sha256"),
                              ("executed_source_snapshot_path", "executed_source_sha256")):
        check("recovery_" + path_key, hashlib.sha256(Path(repair[path_key]).read_bytes()).hexdigest() == repair[sha_key])
    check("corrected_surface_caller_identity", identity(HERE / "evaluate_surface.py")["sha256"]
          == repair["current_corrected_caller_sha256"])
    check("13439_independent_saved_result_checks", verification["status"]
          == "passed_independent_saved_result_verification" and verification["check_count"] == 13439
          and not verification["failures"])
    check("96_repeated_QA_no_new_unique_queries", verification["repeated_scalar_nearest_triangle_QA_queries"] == 96
          and verification["new_unique_surface_query_points"] == 0)
    check("independent_core_identity", identity(HERE / "surface_distance.py")["sha256"]
          == verification["core_meter_sha256"])
    check("one_nonbest_rank_change_six_best_sets_equal",
          summary["rank_change_case_ids"] == ["Yunhex_patch_05/sample_00"]
          and summary["best_method_set_changed_case_ids"] == []
          and all(row["coordinate_best_method_set"] == row["surface_best_method_set"]
                  for row in summary["coordinate_vs_surface"]))
    check("original_acceptance_and_bounded_closure", not summary["old_candidate_engineering_acceptance_changed"]
          and summary["decision"] == "close_surface_objective_alone_resolves_current_failure_explanation"
          and summary["new_future_training_objective_proposal"] is None)
    check("zero_new_operations", all(value == 0 for value in summary["zero_operations"].values()))
    check("1088_old_input_identities_verified", reused["status"] == "passed"
          and reused["reused_count"] == len(reused["reused_input_files"]) == 1088
          and reused["Bunny_files_opened"] == 0)
    check("eight_phase_ledgers_failure_retained", len(costs["phases"]) == 8
          and costs["failures_and_recovery"]["phase_process_failures"] == ["summary"]
          and costs["phases"]["summary_final"]["controller"]["returncode"] == 0)
    check("final_summary_source_matches_executed_identity", identity(HERE / "summarize.py")["sha256"]
          == costs["phases"]["summary_final"]["controller"]["worker_source_sha256"])
    check("reused_hash_cost_included", costs["reused_input_identity_verification"]["reused_count"] == 1088)

    private = [identity(path) for path in sorted((HERE / "private").rglob("*")) if path.is_file()]
    report = {"cycle_id": plan["cycle_id"], "status": "passed_saved_evidence_final_checks",
              "checks": checks, "check_count": len(checks), "new_geometry_or_metric_queries": 0,
              "new_model_or_training_operations": 0,
              "readonly_report_review": "objective_meter confirmed six identical best sets and bounded future-loss interpretation",
              "wall_s_before_final_writes": time.perf_counter() - started,
              "CPU_s_before_final_writes": time.process_time() - cpu,
              "measurement_limit": "JSON reads, source parse and current private-file hashing included; final JSON/manifest writes, Git, callbacks and authoring interaction unmeasured",
              "scope_disclosures": ["three old snapshot arrays schema-read before final PLAN commit, after PLAN written",
                                    "surface first-run counters repaired after computation without changing scientific payload",
                                    "summary status mismatch failed once, original source and cost retained",
                                    "historical path read and WindowsApps static Python precheck failed and recovered",
                                    "finite allowed vertices and saved context surface only; future surface-loss training unmeasured"]}
    write("FINAL_CHECKS.json", report)
    public = [identity(path) for path in sorted(HERE.iterdir())
              if path.is_file() and path.name not in ("EVIDENCE_MANIFEST.json", "HANDOFF.json")]
    write("EVIDENCE_MANIFEST.json", {"cycle_id": plan["cycle_id"], "base_commit": plan["base_commit"],
          "contract_commit": plan["contract_commit"], "plan_commit": "38d772333cc8daf2fcf61585a4af1d65ba19d974",
          "public_files": public, "private_files": private,
          "public_file_count": len(public), "private_file_count": len(private),
          "private_bytes": sum(row["bytes"] for row in private),
          "reused_inputs": {"path": "REUSED_INPUTS.json", "count": 1088},
          "exclusions": ["manifest self", "postcommit HANDOFF.json"],
          "tracking_scope": "public top-level files only; private geometry/details/process logs remain local"})
    print(json.dumps({"status": report["status"], "checks": len(checks),
                      "public_files": len(public), "private_files": len(private)}))


if __name__ == "__main__":
    main()

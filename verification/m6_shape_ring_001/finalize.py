"""Hash and check the completed fixed ring probe without new geometry scores."""

import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def read(name):
    return json.loads((HERE / name).read_bytes())


def write(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                             encoding="utf8", newline="\n")


def identity(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    started, cpu = time.perf_counter(), time.process_time()
    checks = []

    def check(name, value):
        checks.append({"name": name, "passed": bool(value)})
        if not value:
            raise ValueError(name)

    for row in read("PLAN_FREEZE.json")["files"]:
        check("frozen_" + row["path"], identity(HERE / row["path"])["sha256"] == row["sha256"])
    for path in sorted(HERE.glob("*.py")):
        ast.parse(path.read_bytes(), filename=str(path))
    check("all_public_Python_parse", True)
    residuals, calibration, evaluation, verification, summary = (read(name) for name in
        ("RESIDUALS.json", "CALIBRATION.json", "EVALUATION.json", "INDEPENDENT_VERIFY.json", "SUMMARY.json"))
    wanted = sorted(row["id"] for row in read("INPUT_WHITELIST.json")["cases"])
    check("348_identical_case_denominators", len(wanted) == 348 and
          sorted(row["id"] for row in residuals["cases"]) == wanted and sorted(row["id"] for row in evaluation["cases"]) == wanted)
    check("42_normal109443_F", evaluation["normal_controls"] == 42 and residuals["free_point_observations"] == 109443)
    check("10548_unique_BFS_queries", residuals["BFS_unique_queries"] == 10548)
    check("fit_completed_without_case_failures", residuals["status"] == "completed_all348_fixed_residuals" and not residuals["failures"])
    check("38_synthetic_QA", read("SYNTHETIC_QA.json")["status"] == "passed_closed_form_ring_QA" and read("SYNTHETIC_QA.json")["check_count"] == 38)
    check("1217744_independent_checks", verification["status"] == "passed_independent_ring_verification"
          and verification["check_count"] == 1217744 and not verification["failures"])
    check("2088_repeated_fit_checks", verification["coverage"]["independent_fit_queries"] == 2088)
    check("calibration_exact33normal10405F_once", calibration["normal_patches"] == 33
          and calibration["normal_F_points"] == 10405 and calibration["calibration_count"] == 1
          and calibration["reference_or_label_arrays_read"] == 0)
    binding = read("CALIBRATION_BINDING.json")
    for name in ("CALIBRATION.json", "CALIBRATION_FREEZE.json"):
        data = subprocess.check_output(["git", "show", binding["commit"] + ":verification/m6_shape_ring_001/" + name], cwd=HERE.parents[1])
        check("calibration_committed_" + name, data == (HERE / name).read_bytes())
    freeze = read("CALIBRATION_FREEZE.json")
    check("67_calibration_identities", len(freeze["files"]) == 67)
    for row in freeze["files"]:
        check("frozen_calibration_" + str(Path(row["path"]).relative_to(HERE)), identity(Path(row["path"]))["sha256"] == row["sha256"])
    check("33_score_reuses315_new_scores", evaluation["normal_calibration_score_cache_reused_cases"] == 33
          and evaluation["new_case_score_generation_cases"] == 315)
    check("depth_and_localization_goals_fail", not evaluation["decision_gates"]["depth_signal_goals_passed"]
          and not evaluation["decision_gates"]["any_new_configuration_localization_goals_passed"])
    for group in ("validation_center", "validation_offcenter"):
        values = evaluation["groups"][group]
        for config in evaluation["configurations"]:
            result = values["configurations"][config]
            check(group + "_sameF_" + config, result["rank"]["support"]["point_pool"]["points"] == values["F_points"]
                  and result["rank"]["strong"]["point_pool"]["points"] == values["F_points"])
            check(group + "_zero_operation_" + config, result["operation"]["support"]["TP"] == 0
                  and result["operation"]["support"]["FP"] == 0
                  and result["operation"]["support"]["zero_true_detection_cases"] == 54)
    check("single_next_proposal_only", summary["unique_next_recommendation"]["count"] == 1
          and summary["unique_next_recommendation"]["status"] == "proposal_only_no_training_authorized_by_this_result")
    check("zero_training_forward_repair_Bunny", all(summary[key] == 0 for key in
          ("training", "new_network_forwards", "repair_outputs", "Bunny_arrays_or_scores")))
    check("three_saved_witnesses", read("WITNESSES.json")["count"] == 3)

    used = {}
    for name in ("RESIDUALS.json", "CALIBRATION.json", "EVALUATION.json", "INDEPENDENT_VERIFY.json"):
        for row in read(name)["input_file_identities"]:
            path = Path(row["path"]).resolve()
            if not path.is_relative_to(HERE):
                check("reused_array_is_not_Bunny", "Stanford_Bunny" not in str(path))
                if path in used:
                    check("reused_read_identity_consistent_" + path.name, used[path]["sha256"] == row["sha256"])
                used[path] = row
    reused_started, reused_cpu = time.perf_counter(), time.process_time()
    reused = []
    for path, expected in sorted(used.items(), key=lambda item: str(item[0])):
        current = identity(path)
        check("old_input_hash_" + str(path), current["sha256"] == expected["sha256"])
        reused.append(current)
    write("REUSED_INPUTS.json", {"cycle_id": "M6-SHAPE-RING-001", "status": "passed_final_reused_input_bytehashes",
          "reused_count": len(reused), "files": reused, "Bunny_arrays": 0,
          "wall_s_before_write": time.perf_counter() - reused_started, "CPU_s_before_write": time.process_time() - reused_cpu,
          "scope": "rehashed actual old inputs recorded by residual generation, scoring and internal independent verification, no new scores"})
    import collect_costs
    collect_costs.main()
    costs = read("COSTS.json")
    check("nine_phase_ledgers_one_preserved_QA_failure", len(costs["phases"]) == 9
          and costs["failures_and_recovery"]["phase_failures"] == ["qa"])
    check("compute_budget7200s_peak4GiB", costs["sequential_controller_wall_sum_s"] < 7200
          and costs["maximum_sampled_tree_RSS_bytes"] < 4294967296)
    archive = {"qa": HERE / "private/recovery/synthetic_qa_initial_executed.py",
               "summary": HERE / "private/recovery/summarize_initial_executed.py"}
    sources = {"prepare": "prepare.py", "fit": "geometry_fit.py", "qa": "synthetic_qa.py",
               "calibrate": "calibrate.py", "evaluate": "evaluate.py", "verify": "verify.py", "summary": "summarize.py"}
    for label, row in costs["phases"].items():
        path = archive.get(label, HERE / sources[row["controller"]["phase"]])
        check("executed_phase_source_" + label, identity(path)["sha256"] == row["controller"]["worker_source_sha256"])
    for report in (residuals, calibration, evaluation):
        for name, sha in report["source_sha256"].items():
            check("scientific_source_" + name, identity(HERE / name)["sha256"] == sha)
    private = [identity(path) for path in sorted((HERE / "private").rglob("*")) if path.is_file()]
    write("FINAL_CHECKS.json", {"cycle_id": "M6-SHAPE-RING-001", "status": "passed_saved_ring_evidence_integrity",
          "checks": checks, "check_count": len(checks), "reused_input_files": len(reused),
          "wall_s_before_final_writes": time.perf_counter() - started, "CPU_s_before_final_writes": time.process_time() - cpu,
          "new_fits_scores_forwards_or_repairs": 0,
          "implementation_disclosures": ["witness primary-ring and RMSE-over-ell interpretation refined within three fixed selection categories",
              "NumPy bool report serialization recovered without assertion or tolerance changes",
              "cost-audit old CPU formula recovered after collector definition included shared context",
              "independent complete perconfig cost is conservative measured-component composition, cold standalone execution unmeasured"],
          "measurement_limits": "final byte hashing/cost aggregation included, final JSON/manifest writes, Git, callback and whole authoring/money unmeasured"})
    public = [identity(path) for path in sorted(HERE.iterdir())
              if path.is_file() and path.name not in ("EVIDENCE_MANIFEST.json", "HANDOFF.json")]
    for row in public + private:
        row["path"] = Path(row["path"]).relative_to(HERE).as_posix()
    write("EVIDENCE_MANIFEST.json", {"cycle_id": "M6-SHAPE-RING-001", "base_commit": read("PLAN.json")["base_commit"],
          "contract_commit": read("PLAN.json")["contract_commit"], "plan_commit": "1e9926a126a7d83725a69905a72136f7229376bf",
          "calibration_commit": binding["commit"], "public_files": public, "private_files": private,
          "public_file_count": len(public), "private_file_count": len(private), "private_bytes": sum(row["bytes"] for row in private),
          "exclusions": ["manifest self", "postcommit HANDOFF.json"], "reused_inputs": "REUSED_INPUTS.json",
          "Git_scope": "top-level public code/json/md only, private arrays/cache/logs stay local"})
    print(json.dumps({"status": "passed_saved_ring_evidence_integrity", "checks": len(checks),
                      "public_files": len(public), "private_files": len(private), "reused": len(reused)}))


if __name__ == "__main__":
    main()

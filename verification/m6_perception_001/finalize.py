"""Check fixed identities and inventory perception evidence without new scores."""

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

    def check(name, passed):
        checks.append({"name": name, "passed": bool(passed)})
        if not passed:
            raise ValueError(name)

    for row in read("PLAN_FREEZE.json")["files"]:
        check("frozen_" + row["path"], identity(HERE / row["path"])["sha256"] == row["sha256"])
    for path in sorted(HERE.glob("*.py")):
        ast.parse(path.read_bytes(), filename=str(path))
    check("all_public_Python_sources_parse", True)
    features, training, model, calibration, evaluation, regions, verification, region_verify, summary = (read(name) for name in
        ("FEATURES.json", "TRAIN_LOG.json", "MODEL_IDENTITY.json", "CALIBRATION.json", "EVALUATION.json", "REGION_REPORTS.json",
         "INDEPENDENT_VERIFY.json", "REGION_VERIFY.json", "SUMMARY.json"))
    cases = read("INPUT_WHITELIST.json")["cases"]
    ids = sorted(row["id"] for row in cases)
    for name, report in (("features", features), ("predictions", read("PREDICTIONS.json")), ("evaluation", evaluation), ("regions", regions)):
        check("348_fixed_IDs_" + name, sorted(row["id"] for row in report["cases"]) == ids and len(ids) == 348)
    check("231dev117val_predictions", len(read("PREDICTIONS_DEVELOPMENT.json")["cases"]) == 231
          and len(read("PREDICTIONS_VALIDATION.json")["cases"]) == 117)
    check("109443_F_and12_unavailable_kept", sum(row["points"] for row in features["cases"]) == 109443
          and sum(row["unavailable_points"] for row in features["cases"]) == 12
          and sum(row["unavailable_points"] for row in features["cases"] if row["purpose"] == "validation") == 0)
    check("single1200step_seed1729_training", training["training_runs"] == 1 and training["completed_steps"] == 1200
          and len(training["steps"]) == 1200 and training["seed"] == 1729 and training["batch_size"] == 1024)
    check("active768129_params", model["encoder_parameters"] == 702464 and model["head_parameters"] == 65665
          and model["active_parameters"] == 768129)
    check("encoder_and_BN_identity_frozen", len({model[key] for key in ("encoder_initial_tensor_sha256", "encoder_final_tensor_sha256",
          "encoder_feature_initial_tensor_sha256", "encoder_feature_final_tensor_sha256")}) == 1
          and model["encoder_parameter_or_BN_training_updates"] == 0 and model["decoder_forward_calls"] == 0)
    check("head_tensor_changed", model["head_initial_tensor_sha256"] != model["head_final_tensor_sha256"])
    check("validation_labels_zero_in_training", training["validation_labels_read"] == 0 and calibration["validation_label_arrays_read"] == 0)
    for row in read("SOURCE_INDEX.json")["files"] + read("SOURCE_INDEX.json")["reused_helpers"]:
        check("reused_encoder_source_" + Path(row["path"]).name, identity(Path(row["path"]))["sha256"] == row["sha256"])
    binding = read("CALIBRATION_BINDING.json")
    for name in ("FEATURES.json", "NORMALIZATION.json", "TRAIN_LOG.json", "MODEL_IDENTITY.json", "PREDICTIONS_DEVELOPMENT.json", "CALIBRATION.json", "CALIBRATION_FREEZE.json"):
        data = subprocess.check_output(["git", "show", binding["commit"] + ":verification/m6_perception_001/" + name], cwd=HERE.parents[1])
        check("training_calibration_committed_" + name, data == (HERE / name).read_bytes())
    freeze = read("CALIBRATION_FREEZE.json")
    check("471_training_calibration_members", len(freeze["files"]) == 471 and calibration["calibration_count"] == 1 and calibration["normal_patches"] == 33)
    for row in freeze["files"]:
        check("frozen_training_calibration_" + Path(row["path"]).name, identity(Path(row["path"]))["sha256"] == row["sha256"])
    check("A_B_both_failed", not evaluation["decision_gates"]["A_attention"]["passed"]
          and not evaluation["decision_gates"]["B_abnormality"]["passed"])
    check("internal_model_verification_passed", verification["status"] == "passed_internal_perception_verification" and not verification["failures"])
    check("1044_existing_encoder_replays_no_optimizer", verification["coverage"]["encoder_existing_query_replays"] == 1044
          and verification["coverage"]["optimizer_step_replays"] == 0 and verification["coverage"]["full_training_replays"] == 0)
    check("region_QA17_and_roundtrip45890", read("REGION_QA.json")["status"] == "passed_synthetic_region_contract_QA"
          and read("REGION_QA.json")["check_count"] == 17 and region_verify["status"] == "passed_region_reference_contract_verification"
          and region_verify["check_count"] == 45890 and not region_verify["failures"])
    check("2324_references_348reports", regions["reference_count"] == 2324 and regions["case_count"] == 348)
    initial_reports = read("private/recovery/regions_initial_reports/REGION_REPORTS.json")
    initial_refs = read("private/recovery/regions_initial_reports/REGION_REFERENCES.json")
    check("presentation_refinement_preserves_all_references_geometry", initial_refs["regions"] == read("REGION_REFERENCES.json")["regions"])
    for row in initial_reports["cases"]:
        for key in ("structured_report", "text_report", "catalog"):
            relative = Path(row[key]["path"]).relative_to(HERE / "private/region_reports")
            archived = HERE / "private/recovery/regions_initial_reports" / relative
            check("initial_report_preserved_" + relative.as_posix(), identity(archived)["sha256"] == row[key]["sha256"])
    check("three_fixed_text_inspections", read("MANUAL_REPORT_QA.json")["status"] == "completed_fixed_three_text_inspections"
          and sorted(row["id"] for row in read("MANUAL_REPORT_QA.json")["cases"]) == sorted(regions["audit_case_ids"]))
    check("one_next_data_contract_proposal", summary["unique_next_recommendation"]["count"] == 1
          and summary["unique_next_recommendation"]["status"] == "proposal_only_no_new_acquisition_or_training_in_this_batch")

    used = {}
    reports = (features, training, calibration, evaluation, regions, verification, region_verify)
    for report in reports:
        for row in report["input_file_identities"]:
            path = Path(row["path"]).resolve()
            if not path.is_relative_to(HERE):
                check("old_input_is_not_Bunny", "Stanford_Bunny" not in str(path))
                if path in used:
                    check("old_input_read_hash_consistent_" + path.name, used[path]["sha256"] == row["sha256"])
                used[path] = row
    for row in read("SOURCE_INDEX.json")["files"] + read("SOURCE_INDEX.json")["reused_helpers"]:
        used[Path(row["path"]).resolve()] = row
    reused_started, reused_cpu = time.perf_counter(), time.process_time()
    reused = []
    for path, expected in sorted(used.items(), key=lambda item: str(item[0])):
        current = identity(path)
        check("old_input_rehash_" + str(path), current["sha256"] == expected["sha256"])
        reused.append(current)
    write("REUSED_INPUTS.json", {"cycle_id": "M6-PERCEPTION-001", "status": "passed_reused_input_bytehashes", "reused_count": len(reused),
          "files": reused, "Bunny_arrays": 0, "wall_s_before_write": time.perf_counter() - reused_started,
          "CPU_s_before_write": time.process_time() - reused_cpu,
          "scope": "byte rehash of recorded old geometry/labels/baseline/runtime/source inputs, no new model or scores"})
    import collect_costs
    collect_costs.main()
    costs = read("COSTS.json")
    check("15_phases_no_process_failure", len(costs["phases"]) == 15 and not costs["failures_and_recovery"]["phase_failures"])
    check("budget7200s4GiB", costs["sequential_controller_wall_sum_s"] < 7200 and costs["maximum_sampled_tree_RSS_bytes"] < 4294967296)
    source_names = {"prepare": "prepare.py", "features": "features.py", "train": "train_head.py", "calibrate": "calibrate.py",
                    "predict": "predict.py", "evaluate": "evaluate.py", "region_qa": "region_qa.py", "regions": "regions.py",
                    "verify_regions": "verify_regions.py", "verify": "verify.py", "summary": "summarize.py"}
    archived_sources = {"regions": HERE / "private/recovery/regions_initial_executed.py",
                        "summary": HERE / "private/recovery/summarize_initial_executed.py"}
    for label, row in costs["phases"].items():
        path = archived_sources.get(label, HERE / source_names[row["controller"]["phase"]])
        check("executed_phase_source_" + label, identity(path)["sha256"] == row["controller"]["worker_source_sha256"])
    for report in reports:
        source = report["source_sha256"]
        if isinstance(source, dict):
            for name, sha in source.items():
                check("reported_scientific_source_" + name, identity(HERE / name)["sha256"] == sha)
        else:
            check("internal_verifier_source", identity(HERE / "verify.py")["sha256"] == source)
    private = [identity(path) for path in sorted((HERE / "private").rglob("*")) if path.is_file()]
    write("FINAL_CHECKS.json", {"cycle_id": "M6-PERCEPTION-001", "status": "passed_frozen_perception_evidence_integrity",
          "checks": checks, "check_count": len(checks), "reused_input_files": len(reused),
          "wall_s_before_final_writes": time.perf_counter() - started, "CPU_s_before_final_writes": time.process_time() - cpu,
          "new_neural_training_forwards_or_scores": 0,
          "disclosures": ["twelve unavailable development F point observations kept withscore0",
             "region remainder and native-unit text refined, all initial reports archived,2324ref records identical",
             "first metadata comparison used wrong references key, recovered to regions",
             "one readonly cost dictionary/list access error recovered",
             "QA formulas are internal, planner independent review pending",
             "consumer/product/full-scene/semantic and independent-source benefits unmeasured"],
          "measurement_limits": "final byte hashing and aggregation included, final JSON/manifest/Git/callback and whole authoring/money unmeasured"})
    public = [identity(path) for path in sorted(HERE.iterdir()) if path.is_file() and path.name not in ("EVIDENCE_MANIFEST.json", "HANDOFF.json")]
    for row in public + private:
        row["path"] = Path(row["path"]).relative_to(HERE).as_posix()
    write("EVIDENCE_MANIFEST.json", {"cycle_id": "M6-PERCEPTION-001", "base_commit": read("PLAN.json")["base_commit"],
          "contract_commit": read("PLAN.json")["contract_commit"], "plan_commit": "cf9ad6c5ac2c64915fb883dfac41d91272d9ce3f",
          "training_calibration_commit": binding["commit"], "public_files": public, "private_files": private,
          "public_file_count": len(public), "private_file_count": len(private), "private_bytes": sum(row["bytes"] for row in private),
          "reused_input_index": "REUSED_INPUTS.json", "exclusions": ["manifest self", "postcommit HANDOFF.json"],
          "Git_scope": "top-level public py/json/md only, weights/features/geometry/complete region payloads stay private"})
    print(json.dumps({"status": "passed_frozen_perception_evidence_integrity", "checks": len(checks),
                      "public_files": len(public), "private_files": len(private), "reused": len(reused)}))


if __name__ == "__main__":
    main()

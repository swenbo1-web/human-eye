"""Verify final byte identities and inventory the fixed pretrained screen."""

import ast
import base64
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def read(name):
    return json.loads((HERE / name).read_bytes())


def write(name, report):
    (HERE / name).write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                             encoding="utf8", newline="\n")


def identity(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    started, cpu = time.perf_counter(), time.process_time()
    checks = []

    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        if not condition:
            raise ValueError(name)

    plan = read("PLAN.json")
    for row in read("PLAN_FREEZE.json")["files"]:
        check("frozen_" + row["path"], identity(HERE / row["path"])["sha256"] == row["sha256"])
    for path in sorted(HERE.glob("*.py")):
        ast.parse(path.read_bytes(), filename=str(path))
    check("all_public_Python_sources_parse", True)
    input_index, model, evaluation, qa, verification, summary = (read(name) for name in
        ("INPUT_INDEX.json", "MODEL_OUTPUTS.json", "EVALUATION.json", "TETRAHEDRON_CHECK.json", "INDEPENDENT_VERIFY.json", "SUMMARY.json"))
    ids = sorted(row["id"] for row in read("CASE_SELECTION.json")["cases"])
    check("37_fixed_input_model_evaluation_ids", len(ids) == 37 and
          all(sorted(row["id"] for row in report["cases"]) == ids for report in (input_index, model, evaluation)))
    check("74_case_methods_148_iterations", model["completed_case_methods"] == 74
          and sum(len(result["iterations"]) for case in model["cases"] for result in case["methods"].values()) == 148
          and not model["failures"])
    check("all37_first_sampling_equal", all(row["first_iteration_sampled_ids_equal"] for row in model["cases"]))
    check("386_main_network_batches_23126_queries", model["network_forward_batches"] == 386 and model["network_forward_query_count"] == 23126)
    check("37_actual_denominators", evaluation["actual_denominators"] ==
          {"normal_controls": 7, "development_dents": 12, "validation_center_dents": 9, "validation_offcenter_dents": 9})
    check("1555_official_adapter_checks", qa["status"] == "passed_official_adapter_workflow_QA"
          and qa["check_count"] == 1555 and not qa["failures"])
    check("256_official_queries4_repeated", qa["official_unique_query_points"] == 256 and qa["additional_repeated_forward_queries"] == 4)
    check("102538_independent_checks", verification["status"] == "passed_independent_saved_result_verification"
          and verification["check_count"] == 102538 and not verification["failures"])
    check("independent_222_directions444_repeated_queries", verification["coverage"]["surface_directions"] == 222
          and verification["coverage"]["repeated_scalar_triangle_queries"] == 444)
    check("85248_first_run_surface_queries", evaluation["directed_vertex_surface_queries"] == 85248)
    check("direct_candidate_rejected_single_training_proposal", summary["direct_pretrained_candidate"] == "rejected_shape_quality_failed"
          and not summary["model_selected_for_product"] and summary["unique_next_recommendation"]["count"] == 1
          and summary["unique_next_recommendation"]["status"] == "proposal_only_training_not_run")
    pf = evaluation["summaries"]["all"]["pointfilter"]
    check("seven_normal37_protection_failures", len(pf["normal_control_gate_failed_case_ids"]) == 7
          and len(pf["normal_point_gate_failed_case_ids"]) == 37)
    check("759_flips0_new_degenerate", pf["normal_reversals_sum_over_cases"] == 759 and pf["new_degenerate_faces_sum_over_cases"] == 0)
    check("all_fixed_and_full_incident_preserved", pf["all_fixed_and_boundary_bitwise_preserved"]
          and pf["full_source_incident_coverage_complete"])
    check("zero_training_and_Bunny", summary["training"] == 0 and summary["Bunny_arrays_or_scores"] == 0)
    for name, expected in qa["source_sha256"].items():
        check("QA_source_identity_" + name, identity(HERE / name)["sha256"] == expected)
    for row in read("SOURCE_INDEX.json")["files"]:
        check("official_source_" + row["upstream_path"], identity(Path(row["path"]))["sha256"] == row["sha256"])

    old = {}
    for name, key in (("INPUT_PROVENANCE.json", "files"), ("EVALUATION.json", "input_file_identities"),
                      ("INDEPENDENT_VERIFY.json", "input_file_identities"), ("TRANSFER_DIAGNOSTIC.json", "input_file_identities")):
        for row in read(name)[key]:
            path = Path(row["path"]).resolve()
            if not path.is_relative_to(HERE):
                check("old_input_is_not_Bunny_" + path.name, "Stanford_Bunny" not in str(path))
                if path in old:
                    check("old_read_identity_consistent_" + path.name, old[path]["sha256"] == row["sha256"])
                old[path] = row
    reused_started, reused_cpu = time.perf_counter(), time.process_time()
    reused = []
    for path, expected in sorted(old.items(), key=lambda item: str(item[0])):
        current = identity(path)
        check("old_input_rehash_" + str(path.relative_to(HERE.parents[1])), current["sha256"] == expected["sha256"])
        reused.append(current)
    write("REUSED_INPUTS.json", {"cycle_id": plan["cycle_id"], "status": "passed_final_old_input_rehash",
          "reused_count": len(reused), "files": reused, "Bunny_arrays": 0,
          "wall_s_before_write": time.perf_counter() - reused_started,
          "CPU_s_before_write": time.process_time() - reused_cpu,
          "scope": "byte hashes compared to actual input identities recorded by construction/evaluation/independent verification, no new array scoring"})

    runtime_started, runtime_cpu = time.perf_counter(), time.process_time()
    packages = []
    for distribution in importlib.metadata.distributions(path=[str(HERE / "private/deps")]):
        count, unhashed, total = 0, 0, 0
        for item in distribution.files or []:
            path = Path(distribution.locate_file(item)).resolve()
            check("runtime_file_inside_private_target", path.is_relative_to(HERE / "private/deps"))
            if item.hash is None:
                unhashed += 1
                continue
            data = path.read_bytes()
            actual = base64.urlsafe_b64encode(hashlib.new(item.hash.mode, data).digest()).decode().rstrip("=")
            check("wheel_RECORD_" + str(item), actual == item.hash.value)
            count += 1
            total += len(data)
        metadata = Path(distribution._path)
        packages.append({"name": distribution.metadata["Name"], "version": distribution.version,
                         "RECORD": identity(metadata / "RECORD"), "hashed_files_verified": count,
                         "verified_bytes": total, "unhashed_RECORD_or_generated_files": unhashed})
    check("four_private_dependency_distributions", len(packages) == 4)
    write("RUNTIME_LOCK.json", {"cycle_id": plan["cycle_id"], "status": "passed_installed_wheel_RECORD_hashes",
          "packages": packages, "existing_Torch_NumPy_readonly": read("ENVIRONMENT.json")["versions"],
          "wall_s_before_write": time.perf_counter() - runtime_started,
          "CPU_s_before_write": time.process_time() - runtime_cpu,
          "scope": "private installed distributions checked against their wheel RECORD hashes; generated pyc/unhashed RECORD entries counted"})

    import collect_costs
    collect_costs.main()
    costs = read("COSTS.json")
    check("eight_complete_phase_ledgers", len(costs["phases"]) == 8 and not costs["failures"]["phase_process_failures"])
    check("compute_under7200seconds", costs["compute_controller_main_wall_excluding_prepare_s"] < 7200)
    check("sampled_peak_under4GiB", all(row["worker_tree"]["tree_sampled_peak_working_set_bytes"] < 4294967296 for row in costs["phases"].values()))
    archive = {"prepare": HERE / "private/recovery/prepare_payload_initial_executed.py",
               "summary": HERE / "private/recovery/summarize_initial_executed.py"}
    source_names = {"prepare": "prepare_payload.py", "inputs": "build_inputs.py", "qa": "verify_adapter.py",
                    "inference": "inference.py", "evaluate": "evaluate.py", "verify": "verify_results.py", "summary": "summarize.py"}
    for label, row in costs["phases"].items():
        path = archive.get(label, HERE / source_names[row["controller"]["phase"]])
        check("executed_phase_source_" + label, identity(path)["sha256"] == row["controller"]["worker_source_sha256"])
    private = [identity(path) for path in sorted((HERE / "private").rglob("*"))
               if path.is_file() and not path.is_relative_to(HERE / "private/deps")]
    write("FINAL_CHECKS.json", {"cycle_id": plan["cycle_id"], "status": "passed_final_evidence_and_runtime_checks",
          "checks": checks, "check_count": len(checks), "reused_input_files": len(reused),
          "wall_s_before_final_writes": time.perf_counter() - started,
          "CPU_s_before_final_writes": time.process_time() - cpu,
          "new_model_forwards_or_surface_queries": 0,
          "late_independent_direction_arithmetic_checks": 666,
          "source_amendments": ["precompute identical per-case RNG clarification", "post-run pip -B rerun guard with archived original", "final report denominator wording, archived initial summary source"],
          "recovered_readonly_review_errors": ["missing guessed old path", "Windows rg glob", "early ENVIRONMENT/COSTS read", "QA stdin parse"],
          "measurement_limit": "final bytes/runtime hashing and cost collection included; final checks/manifest writes, Git, callbacks and authoring interaction unmeasured"})
    public = [identity(path) for path in sorted(HERE.iterdir())
              if path.is_file() and path.name not in ("EVIDENCE_MANIFEST.json", "HANDOFF.json")]
    for row in public + private:
        row["path"] = Path(row["path"]).relative_to(HERE).as_posix()
    write("EVIDENCE_MANIFEST.json", {"cycle_id": plan["cycle_id"], "base_commit": plan["base_commit"],
          "contract_commit": plan["contract_commit"], "plan_commit": "da7e2d7ebb784ef67c1cacd4b2d0e6f633b7d5a1",
          "public_files": public, "private_files": private, "public_file_count": len(public), "private_file_count": len(private),
          "private_bytes_excluding_dependencies": sum(row["bytes"] for row in private),
          "reused_input_index": "REUSED_INPUTS.json", "private_dependency_integrity_index": "RUNTIME_LOCK.json",
          "exclusions": ["manifest self", "postcommit HANDOFF.json", "private/deps enumerated and hash-checked via installed RECORD in RUNTIME_LOCK"],
          "Git_scope": "public top-level py/json/md only; all geometry, weights, official copies and dependencies stay private"})
    print(json.dumps({"status": "passed_final_evidence_and_runtime_checks", "checks": len(checks),
                      "public_files": len(public), "private_files_excluding_dependencies": len(private), "reused": len(reused)}))


if __name__ == "__main__":
    main()

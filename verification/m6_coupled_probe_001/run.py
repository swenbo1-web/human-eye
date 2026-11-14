"""Run the frozen controls and one real perturbation; retain every attempt."""
import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from evaluate import digest, evaluate, serializable_result
from oracle import verify_plan
from spatial_oracle import candidates as independent_candidates


def record(path):
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def main():
    started, cpu_started = time.perf_counter(), time.process_time()
    deadline = started + 600
    private = HERE / "private"
    private.mkdir(exist_ok=True)
    logs = HERE / "RUN_LOG.json"
    history = json.loads(logs.read_bytes()) if logs.exists() else {"attempts": []}
    attempt = {"attempt": len(history["attempts"]) + 1, "status": "running"}
    history["attempts"].append(attempt)
    write(logs, history)
    result = {"cycle_id": "M6-COUPLED-PROBE-001", "status": "running", "failures": [],
              "plan_commit": "d69f433dff9e24834267f79faf5a691c02ef42b0",
              "environment": {"python": sys.version, "numpy": np.__version__, "platform": platform.platform(),
                              "thread_limits": {key: os.environ[key] for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")}}}
    try:
        plan = json.loads((HERE / "CASE_PLAN.json").read_bytes())
        run_plan = json.loads((HERE / "RUN_PLAN.json").read_bytes())
        for name in ("CASE_PLAN.json", "RUN_PLAN.json", "oracle.py"):
            frozen = subprocess.check_output(["git", "show", f"d69f433dff9e24834267f79faf5a691c02ef42b0:verification/m6_coupled_probe_001/{name}"], cwd=ROOT)
            assert (HERE / name).read_bytes() == frozen, "frozen_plan_or_oracle_changed"
        assert record(HERE / "CASE_PLAN.json")["sha256"] == run_plan["case_plan_sha256"]
        assert record(ROOT / "human_eye_plugin/surface_geometry.py")["sha256"] == run_plan["product_surface_geometry_sha256"]
        print("Running independent exact control oracle", flush=True)
        oracle = verify_plan(plan)
        write(HERE / "ORACLE_RESULTS.json", oracle)
        controls = []
        for case, expected in zip(plan["cases"], oracle["results"]):
            tested_case = dict(case)
            for field in ("vertices_before", "vertices_candidate"):
                tested_case[field] = [[float("nan") if value == "NaN" else value for value in point] for point in case[field]]
            observed, _, _ = evaluate(tested_case, deadline=deadline)
            fields = ["joint_status"] if expected["joint_status"] == "invalid" else [
                "joint_status", "affected_face_ids", "scope_complete", "shape_ok", "preservation_ok", "contact_ok"]
            if expected.get("scope_complete"):
                fields += ["before_pairs", "after_pairs", "new_pairs"]
            mismatches = {key: {"expected": expected.get(key), "actual": observed.get(key)}
                          for key in fields if expected.get(key) != observed.get(key)}
            controls.append({"name": case["name"], "passed": not mismatches, "mismatches": mismatches,
                             "nonfinite_sentinel_decoded": any(value == "NaN" for point in case["vertices_candidate"] for value in point),
                             "observed": serializable_result(observed)})
        result["controls"] = {"cases": len(controls), "passed": sum(row["passed"] for row in controls), "results": controls}
        write(HERE / "CONTROL_RESULTS.json", result["controls"])
        assert all(row["passed"] for row in controls), "control_oracle_mismatch"
        print(f"Controls passed {len(controls)}/{len(controls)}", flush=True)

        cache_bytes = (HERE / "CACHE_CASE_PLAN.json").read_bytes()
        assert cache_bytes == subprocess.check_output(["git", "show", "9c2599eab3c54444dea328a5726bbe68d4403bd9:verification/m6_coupled_probe_001/CACHE_CASE_PLAN.json"], cwd=ROOT)
        cache_plan = json.loads(cache_bytes)
        cache_case = next(case for case in plan["cases"] if case["name"] == cache_plan["base_geometry_case"])
        cache_result, cache_prepared, _ = evaluate(cache_case, deadline=deadline)
        stale_scan, _, _ = evaluate(cache_case, prepared_before=cache_prepared, scan_before=cache_result["after_scan"], deadline=deadline)
        changed_prepared = cache_prepared.updated(cache_case["vertices_candidate"], cache_case["write_ids"], deadline)
        stale_preparation, _, _ = evaluate(cache_case, prepared_before=changed_prepared, deadline=deadline)
        cache_rows = []
        for planned, observed in zip(cache_plan["cases"], (stale_scan, stale_preparation)):
            passed = observed["joint_status"] == planned["expected_joint_status"] and observed["reason"] == planned["expected_reason"]
            cache_rows.append({"name": planned["name"], "passed": passed, "observed": observed})
        assert changed_prepared.source != cache_prepared.source
        result["cache_regressions"] = {"cases": len(cache_rows), "passed": sum(row["passed"] for row in cache_rows), "results": cache_rows}
        write(HERE / "CACHE_RESULTS.json", result["cache_regressions"])
        assert all(row["passed"] for row in cache_rows), "cache_source_binding_regression"

        old = ROOT / "verification/m6_real_data_001"
        for name in ("SOURCE_MANIFEST.json", "INVENTORY.json", "COUPLED_CONTEXT.json"):
            frozen = subprocess.check_output(["git", "show", f"ddd541cf087dc2bbec19e551b8fe3820578077ef:verification/m6_real_data_001/{name}"], cwd=ROOT)
            assert (old / name).read_bytes() == frozen, "old_public_source_metadata_changed"
        old_manifest = json.loads((old / "SOURCE_MANIFEST.json").read_bytes())
        old_inventory = json.loads((old / "INVENTORY.json").read_bytes())
        context = json.loads((old / "COUPLED_CONTEXT.json").read_bytes())
        raw_path = old / "private/capture_02/raw_selected.json"
        patch_path = old / "private/ARM_REGION.json"
        for row in old_manifest["captures"][1]["export_files"]:
            assert record(Path(row["path"])) == row
        assert record(patch_path) == old_inventory["arm_region"]["private_patch"], "frozen_patch_changed"
        assert record(old / "private/COUPLED_REGION_CONTEXT.json") == context["private_context"], "frozen_coupling_context_changed"
        assert record(raw_path)["sha256"] == context["state"]["raw_export_sha256"]
        state_fields = {key: value for key, value in context["state"].items() if key != "snapshot_sha256"}
        assert digest(state_fields) == context["state"]["snapshot_sha256"], "snapshot_binding_invalid"
        raw = json.loads(raw_path.read_bytes())
        patch = json.loads(patch_path.read_bytes())
        before = np.asarray(raw["vertices_world"], dtype="<f8")
        after = before.copy()
        writes = patch["source_vertex_ids"]
        write_set = set(writes)
        after[writes, 1] += np.float64(.001)
        np.save(private / "candidate_vertices.npy", after, allow_pickle=False)
        state = {"source_id": context["state"]["snapshot_sha256"], "frame": 1, "subframe": 0.,
                 "coordinate_frame": "saved_world_binary64_m"}
        packet = {"state": state, "vertices_before": before.tolist(), "vertices_candidate": after.tolist(),
                  "triangles": raw["triangles"], "write_ids": writes, "target_vertices": None,
                  "protected_ids": [i for i in range(len(before)) if i not in write_set],
                  "shape_tolerance_m": 0., "preservation_tolerance_m": 0., "require_no_new_intersections": True}
        print("Real control and full candidate preparation/evaluation", flush=True)
        full, prepared, initial_scan = evaluate(packet, deadline=deadline)
        assert len(full["affected_face_ids"]) == 898
        write(private / "REAL_FULL_RESULTS.json", serializable_result(full))
        print(f"Full query exact pairs before={full['before_scan']['exact_tests']} after={full['after_scan']['exact_tests']}", flush=True)
        print("Independent blocked AABB enumeration", flush=True)
        aabb_checks = {}
        for name, values, scan in (("before", before, full["before_scan"]), ("candidate", after, full["after_scan"])):
            reference, stats = independent_candidates(values, raw["triangles"], full["affected_face_ids"], deadline)
            equal = reference == scan["candidates"]
            aabb_checks[name] = {"matches_bvh": equal, "pair_sha256": digest(reference), **stats}
            assert equal and stats["domain_pairs"] == scan["pair_domain"], "spatial_candidate_coverage_mismatch"
        print("Shared static preparation candidate evaluation", flush=True)
        shared, _, _ = evaluate(packet, shared=True, prepared_before=prepared, scan_before=initial_scan, deadline=deadline)
        write(private / "REAL_SHARED_RESULTS.json", serializable_result(shared))
        same_fields = ["before_pairs", "after_pairs", "new_pairs", "removed_pairs", "changed_relations", "shape", "preservation",
                       "shape_ok", "preservation_ok", "contact_ok", "joint_status", "scope_complete", "affected_face_ids"]
        same = all(full[key] == shared[key] for key in same_fields)
        same &= full["after_scan"]["candidates"] == shared["after_scan"]["candidates"]
        same &= full["after_scan"]["intersections"] == shared["after_scan"]["intersections"]
        same &= full["after_scan"]["unresolved"] == shared["after_scan"]["unresolved"]
        assert same, "full_shared_result_mismatch"
        def scan_summary(value):
            return {key: item for key, item in value.items() if key not in ("intersections", "candidates", "unresolved")} | {
                "extra_intersection_pairs": len(value["intersections"]),
                "extra_pair_sha256": digest(sorted(value["intersections"])), "candidate_pair_sha256": digest(value["candidates"])}
        delta = after - before
        input_records = [record(raw_path), record(patch_path), record(old / "private/COUPLED_REGION_CONTEXT.json")]
        result["real"] = {"source_state": context["state"], "input_files": input_records,
                          "coordinate_semantics": "Exact dyadic values of saved world binary64 arrays, identity frame; no original affine reapplication",
                          "before_coordinates_le_f8_sha256": hashlib.sha256(before.tobytes()).hexdigest(),
                          "candidate_coordinates_le_f8_sha256": hashlib.sha256(after.tobytes()).hexdigest(),
                          "triangles_sha256": digest(raw["triangles"]), "writes": len(writes), "write_ids_sha256": digest(writes),
                          "affected_faces": len(full["affected_face_ids"]), "affected_face_ids_sha256": digest(full["affected_face_ids"]),
                          "crossing_faces": len(set(full["affected_face_ids"]) - set(patch["source_triangle_ids"])),
                          "max_selected_displacement_m": float(np.linalg.norm(delta[writes], axis=1).max()),
                          "max_unselected_displacement_m": float(np.linalg.norm(delta[packet["protected_ids"]], axis=1).max()),
                          "binary64_delta_y_minmax_m": [float(delta[writes, 1].min()), float(delta[writes, 1].max())],
                          "accepted_target": False, "task_acceptance_status": "unknown_missing_accepted_target",
                          "engineering_joint_status": full["joint_status"], "shape": full["shape"], "preservation": full["preservation"],
                          "contact_requirement": full["contact_requirement"], "contact_condition": full["contact_ok"],
                          "before": scan_summary(full["before_scan"]), "candidate": scan_summary(full["after_scan"]),
                          "new_extra_pairs": len(full["new_pairs"]), "removed_extra_pairs": len(full["removed_pairs"]),
                          "changed_existing_relations": len(full["changed_relations"]), "independent_aabb": aabb_checks,
                          "comparison": {"results_equal": bool(same), "common_before_preparation": full["before_preparation"],
                                         "full_evaluate_call_wall_s": full["total_evaluation_wall_s"],
                                         "full_evaluate_call_cpu_s": full["total_evaluation_cpu_s"],
                                         "shared_evaluate_call_wall_s": shared["total_evaluation_wall_s"],
                                         "shared_evaluate_call_cpu_s": shared["total_evaluation_cpu_s"],
                                         "shared_cold_task_wall_s_with_common_before": shared["total_evaluation_wall_s"] + full["before_preparation"]["wall_s"] + initial_scan["work"]["wall_s"],
                                         "shared_cold_task_cpu_s_with_common_before": shared["total_evaluation_cpu_s"] + full["before_preparation"]["cpu_s"] + initial_scan["work"]["cpu_s"],
                                         "full_candidate_preparation": full["candidate_preparation"],
                                         "shared_candidate_preparation": shared["candidate_preparation"],
                                         "full_candidate_query": full["after_scan"]["work"], "shared_candidate_query": shared["after_scan"]["work"],
                                         "initial_query": initial_scan["work"], "before_evaluations_executed": 1,
                                         "same_candidate_evaluations_executed": 2, "distinct_candidates": 1},
                          "private_outputs": [record(private / name) for name in ("candidate_vertices.npy", "REAL_FULL_RESULTS.json", "REAL_SHARED_RESULTS.json")]}
        for row in input_records:
            assert record(Path(row["path"])) == row, "old_private_input_changed"
        result["status"] = "passed_finite_offline_probe"
    except Exception as exc:
        result["status"] = "failed"
        result["failures"].append({"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
        print(traceback.format_exc(), flush=True)
    result["not_evaluated"] = ["general distance", "volume containment", "signed penetration", "motion path", "artistic correction quality",
                               "live residency", "external Cube geometry", "Blender", "M5 writing", "models or training", "formal performance"]
    result["run_wall_s"] = time.perf_counter() - started
    result["run_cpu_s"] = time.process_time() - cpu_started
    result["run_plan_sha256"] = record(HERE / "RUN_PLAN.json")["sha256"]
    attempt.update(status=result["status"], wall_s=result["run_wall_s"], cpu_s=result["run_cpu_s"], failures=result["failures"])
    write(logs, history)
    write(HERE / "RESULTS.json", result)
    print(json.dumps({"status": result["status"], "wall_s": result["run_wall_s"], "cpu_s": result["run_cpu_s"]}), flush=True)
    return 0 if result["status"] == "passed_finite_offline_probe" else 1


if __name__ == "__main__":
    raise SystemExit(main())

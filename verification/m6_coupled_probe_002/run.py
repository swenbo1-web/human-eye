"""One finite replay of the query-completeness correction; old evidence is read-only."""
import os
for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"

import hashlib
import importlib.util
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
OLD = ROOT / "verification/m6_coupled_probe_001"
sys.path.insert(0, str(HERE))
from separation_oracle import case_reference, real_witnesses


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def scan_facts(scan):
    return {key: value for key, value in scan.items() if key != "work"}


def main():
    started, cpu_started = time.perf_counter(), time.process_time()
    deadline = started + 600
    private = HERE / "private"
    private.mkdir(exist_ok=True)
    log_path = HERE / "RUN_LOG.json"
    log = json.loads(log_path.read_bytes()) if log_path.exists() else {"attempts": []}
    attempt = {"attempt": len(log["attempts"]) + 1, "status": "running"}
    log["attempts"].append(attempt)
    attempt["source_scripts_before_run"] = [record(HERE / name) for name in ("run.py", "evaluate.py", "separation_oracle.py")]
    write(log_path, log)
    result = {"cycle_id": "M6-COUPLED-PROBE-002", "status": "running", "checks": [], "failures": [],
              "plan_commit": "323fd713db5c89e13a593f4034d366e6d39380e6",
              "environment": {"python": sys.version, "numpy": np.__version__, "platform": platform.platform(),
                              "thread_limits": {name: os.environ[name] for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")}}}

    def check(name, condition):
        result["checks"].append({"name": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)

    try:
        for name in ("CASE_PLAN.json", "evaluate.py"):
            fixed = subprocess.check_output(["git", "show", f"323fd713db5c89e13a593f4034d366e6d39380e6:verification/m6_coupled_probe_002/{name}"], cwd=ROOT)
            check("new frozen source " + name, (HERE / name).read_bytes() == fixed)
        old_paths = subprocess.check_output(["git", "diff", "--name-only", "ddd541cf087dc2bbec19e551b8fe3820578077ef", "696e8e2ad46ecf1524a7c8549a1d390c0de8f43d"], cwd=ROOT).decode().splitlines()
        old_records = []
        for relative in old_paths:
            fixed = subprocess.check_output(["git", "show", f"696e8e2ad46ecf1524a7c8549a1d390c0de8f43d:{relative}"], cwd=ROOT)
            check("old committed bytes " + relative, (ROOT / relative).read_bytes() == fixed)
            old_records.append(record(ROOT / relative))
        old_manifest = json.loads((OLD / "EVIDENCE_MANIFEST.json").read_bytes())
        for entry in old_manifest["local_private_files"] + old_manifest["real_inputs"] + [old_manifest["product_surface_source"]]:
            check("old source bytes " + entry["path"], record(Path(entry["path"])) == entry)
            old_records.append(entry)
        plan = json.loads((HERE / "CASE_PLAN.json").read_bytes())
        old = load("probe001_evaluator", OLD / "evaluate.py")
        new = load("probe002_evaluator", HERE / "evaluate.py")
        oracle = load("probe001_independent_oracle", OLD / "oracle.py")
        check("minimal change retains product limits", old.surface.LIMITS == new.surface.LIMITS)
        print("Running three predeclared old/new scope controls", flush=True)
        cases = []
        for case in plan["cases"]:
            reference = case_reference(case)
            previous, _, _ = old.evaluate(case, deadline=deadline)
            current, prepared, initial = new.evaluate(case, deadline=deadline)
            shared, _, _ = new.evaluate(case, shared=True, prepared_before=prepared, scan_before=initial, deadline=deadline)
            expected = case["expected"]
            check(case["name"] + " independent reference", reference["new_joint_status"] == expected["new_joint"] and reference["new_contact_ok"] is expected["new_contact"])
            check(case["name"] + " old/new joint", previous["joint_status"] == expected["old_joint"] and current["joint_status"] == expected["new_joint"])
            check(case["name"] + " new contact", current["contact_ok"] is expected["new_contact"])
            for stage, expected_prefix, scan_name in (("before", "before", "before_scan"), ("after", "after", "after_scan")):
                check(case["name"] + " " + stage + " separation", reference["proofs"][stage]["axis"] == expected[expected_prefix + "_separation_axis"])
                check(case["name"] + " " + stage + " completeness", current[scan_name]["scan_complete"] == expected["new_" + stage + "_complete"])
                check(case["name"] + " " + stage + " candidates", current[scan_name]["spatial_candidates"] == expected[stage + "_candidates"])
                check(case["name"] + " " + stage + " quality retained", current[scan_name]["degenerate_face_ids"] == [1])
                check(case["name"] + " " + stage + " full/shared", scan_facts(current[scan_name]) == scan_facts(shared[scan_name]))
            cases.append({"name": case["name"], "reference": reference, "old": old.serializable_result(previous),
                          "new": new.serializable_result(current), "shared": new.serializable_result(shared)})
        result["scope_controls"] = cases
        original_plan = json.loads((OLD / "CASE_PLAN.json").read_bytes())
        references = oracle.verify_plan(original_plan)
        regressions = []
        for case, reference in zip(original_plan["cases"], references["results"]):
            packet = dict(case)
            for field in ("vertices_before", "vertices_candidate"):
                packet[field] = [[float("nan") if value == "NaN" else value for value in point] for point in case[field]]
            observed, _, _ = new.evaluate(packet, deadline=deadline)
            fields = ["joint_status"] if reference["joint_status"] == "invalid" else ["joint_status", "shape_ok", "preservation_ok", "contact_ok", "affected_face_ids", "scope_complete"]
            if reference.get("scope_complete"):
                fields += ["before_pairs", "after_pairs", "new_pairs"]
            check("original control " + case["name"], all(observed.get(key) == reference.get(key) for key in fields))
            regressions.append({"name": case["name"], "joint_status": observed["joint_status"], "fields_compared": fields})
        cache_plan = json.loads((OLD / "CACHE_CASE_PLAN.json").read_bytes())
        cache_case = next(case for case in original_plan["cases"] if case["name"] == cache_plan["base_geometry_case"])
        base, prepared, _ = new.evaluate(cache_case, deadline=deadline)
        bad_scan, _, _ = new.evaluate(cache_case, prepared_before=prepared, scan_before=base["after_scan"], deadline=deadline)
        updated = prepared.updated(cache_case["vertices_candidate"], cache_case["write_ids"], deadline)
        bad_preparation, _, _ = new.evaluate(cache_case, prepared_before=updated, deadline=deadline)
        cache_rows = []
        for planned, observed in zip(cache_plan["cases"], (bad_scan, bad_preparation)):
            check("cache regression " + planned["name"], observed["joint_status"] == planned["expected_joint_status"] and observed["reason"] == planned["expected_reason"])
            cache_rows.append({"name": planned["name"], "observed": observed})
        result["original_regressions"] = regressions
        result["cache_regressions"] = cache_rows
        print("Original 18 controls and two cache regressions passed", flush=True)

        metadata = ROOT / "verification/m6_real_data_001"
        context = json.loads((metadata / "COUPLED_CONTEXT.json").read_bytes())
        raw = json.loads((metadata / "private/capture_02/raw_selected.json").read_bytes())
        patch = json.loads((metadata / "private/ARM_REGION.json").read_bytes())
        before = np.asarray(raw["vertices_world"], dtype="<f8")
        after = before.copy()
        writes = patch["source_vertex_ids"]
        write_set = set(writes)
        after[writes, 1] += np.float64(.001)
        recorded = json.loads((OLD / "RESULTS.json").read_bytes())["real"]
        check("same original coordinate bytes", hashlib.sha256(before.tobytes()).hexdigest() == recorded["before_coordinates_le_f8_sha256"])
        check("same fixed candidate bytes", hashlib.sha256(after.tobytes()).hexdigest() == recorded["candidate_coordinates_le_f8_sha256"])
        check("same written source IDs", new.digest(writes) == recorded["write_ids_sha256"])
        packet = {"state": {"source_id": context["state"]["snapshot_sha256"], "frame": 1, "subframe": 0., "coordinate_frame": "saved_world_binary64_m"},
                  "vertices_before": before.tolist(), "vertices_candidate": after.tolist(), "triangles": raw["triangles"], "write_ids": writes,
                  "target_vertices": None, "protected_ids": [i for i in range(len(before)) if i not in write_set],
                  "shape_tolerance_m": 0., "preservation_tolerance_m": 0., "require_no_new_intersections": True}
        print("Real input full and shared query, same fixed candidate", flush=True)
        full, prepared, initial = new.evaluate(packet, deadline=deadline)
        shared, _, _ = new.evaluate(packet, shared=True, prepared_before=prepared, scan_before=initial, deadline=deadline)
        check("same complete incident closure", len(full["affected_face_ids"]) == 898 and new.digest(full["affected_face_ids"]) == recorded["affected_face_ids_sha256"])
        check("real contact now decided, joint still unknown", full["contact_ok"] is True and full["joint_status"] == "unknown" and full["shape"]["status"] == "missing")
        check("real full/shared task quantities", all(full[key] == shared[key] for key in ["shape", "preservation", "contact_ok", "contact_complete", "joint_status", "new_pairs", "removed_pairs", "changed_relations"]))
        states = []
        witnesses = {}
        for name, values, scan_name, expected_axes in (("before", before, "before_scan", [8683, 287, 10]), ("candidate", after, "after_scan", [8683, 284, 13])):
            scan = full[scan_name]
            old_record = recorded[name]
            check(name + " full/shared complete scan facts", scan_facts(scan) == scan_facts(shared[scan_name]))
            check(name + " same pair candidates", new.digest(scan["candidates"]) == old_record["candidate_pair_sha256"])
            check(name + " all spatial/leaf accounting", scan["pair_domain"] == 47427421 and scan["aabb_pruned"] + scan["spatial_candidates"] == scan["pair_domain"] and
                  scan["exact_tests"] == scan["spatial_candidates"] and scan["unknown_pairs"] == scan["unstarted_exact_pairs"] == scan["unaccounted_domain_pairs"] == 0)
            check(name + " original intersection facts", scan["legal_simplex_pairs"] == old_record["legal_simplex_pairs"] and scan["empty_pairs"] == old_record["empty_pairs"] and not scan["intersections"])
            check(name + " quality markers retained", scan["degenerate_face_ids"] == old_record["degenerate_face_ids"] and len(scan["degenerate_face_ids"]) == 10)
            check(name + " query complete with no pending reason", scan["scan_complete"] and scan["reason"] is None)
            rows, stats = real_witnesses(values, raw["triangles"], full["affected_face_ids"], scan["degenerate_face_ids"])
            check(name + " independent Fraction separation witnesses", stats["pair_witnesses"] == 8980 and stats["by_first_axis"] == expected_axes)
            witnesses[name] = rows
            states.append({"name": name, "query_complete": scan["scan_complete"], "reason": scan["reason"], "degenerate_face_ids": scan["degenerate_face_ids"],
                           "pair_domain": scan["pair_domain"], "aabb_pruned": scan["aabb_pruned"], "candidates": scan["spatial_candidates"],
                           "exact_tests": scan["exact_tests"], "legal_simplex": scan["legal_simplex_pairs"], "empty": scan["empty_pairs"],
                           "extra_pairs": len(scan["intersections"]), "unknown_pairs": scan["unknown_pairs"],
                           "candidate_pair_sha256": new.digest(scan["candidates"]), "fraction_separation": stats, "query_work": scan["work"]})
        write(private / "REAL_FULL_RESULTS.json", new.serializable_result(full))
        write(private / "REAL_SHARED_RESULTS.json", new.serializable_result(shared))
        write(private / "SEPARATION_WITNESSES.json", witnesses)
        np.save(private / "candidate_vertices.npy", after, allow_pickle=False)
        result["real"] = {"source_state": context["state"], "independent_assets": 1, "distinct_candidates": 1,
                          "before_coordinates_sha256": hashlib.sha256(before.tobytes()).hexdigest(), "candidate_coordinates_sha256": hashlib.sha256(after.tobytes()).hexdigest(),
                          "writes": len(writes), "affected_faces": len(full["affected_face_ids"]), "states": states,
                          "contact_ok_before_revision": recorded["contact_condition"], "contact_ok_after_revision": full["contact_ok"],
                          "joint_status": full["joint_status"], "shape": full["shape"], "preservation": full["preservation"],
                          "new_pairs": len(full["new_pairs"]), "shared_task_results_equal": True,
                          "common_before_preparation": full["before_preparation"], "full_candidate_preparation": full["candidate_preparation"],
                          "shared_candidate_preparation": shared["candidate_preparation"],
                          "full_evaluate_wall_s": full["total_evaluation_wall_s"], "shared_evaluate_wall_s": shared["total_evaluation_wall_s"],
                          "full_evaluate_cpu_s": full["total_evaluation_cpu_s"], "shared_evaluate_cpu_s": shared["total_evaluation_cpu_s"],
                          "shared_cold_wall_s": shared["total_evaluation_wall_s"] + full["before_preparation"]["wall_s"] + initial["work"]["wall_s"]}
        for entry in old_records:
            check("old evidence unchanged after replay " + entry["path"], record(Path(entry["path"])) == entry)
        result["old_evidence_checked"] = old_records
        result["status"] = "passed_query_scoped_completeness"
    except Exception as exc:
        result["status"] = "failed"
        result["failures"].append({"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
        print(traceback.format_exc(), flush=True)
    result["cost"] = {"main_wall_s_before_publication": time.perf_counter() - started,
                      "main_cpu_s_before_publication": time.process_time() - cpu_started,
                      "real_queries": 3 if "real" in result else None,
                      "real_distinct_candidates": 1 if "real" in result else None,
                      "new_small_old_queries": 6 if "scope_controls" in result else None,
                      "new_small_revised_full_shared_queries": 9 if "scope_controls" in result else None,
                      "old_geometry_control_evaluations": len(result["original_regressions"]) if "original_regressions" in result else None,
                      "cache_setup_evaluations": 1 if "cache_regressions" in result else None,
                      "cache_rejections": len(result["cache_regressions"]) if "cache_regressions" in result else None,
                      "private_bytes": sum(path.stat().st_size for path in private.rglob("*") if path.is_file()),
                      "full_process_cpu_including_imports": None, "peak_rss": None, "formal_performance": False}
    result["not_evaluated"] = ["low-dimensional intersection", "mesh repair", "general distance", "volume containment", "motion path", "artistic acceptance", "Blender", "M5", "training", "model consumers", "paid API"]
    result["probe_closed_after_this_batch"] = result["status"] == "passed_query_scoped_completeness"
    attempt.update(status=result["status"], failures=result["failures"], cost=result["cost"])
    publication_start = time.perf_counter()
    write(HERE / "RESULTS.json", result)
    write(log_path, log)
    publication = {"results_and_log_write_wall_s": time.perf_counter() - publication_start,
                   "main_wall_s_through_result_publication": time.perf_counter() - started,
                   "scope": "After Python imports through RESULTS/log publication; this publication receipt serialization is outside its own timing."}
    write(HERE / "PUBLICATION.json", publication)
    print(json.dumps({"status": result["status"], "checks": len(result["checks"]), **publication}), flush=True)
    return 0 if result["status"] == "passed_query_scoped_completeness" else 1


if __name__ == "__main__":
    raise SystemExit(main())

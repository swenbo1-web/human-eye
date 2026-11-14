"""Generate the frozen pairs, evaluate one method and publish actual geometry."""
import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from generate import generate
from method import reconstruct
from metrics import errors, triangle_quality, support_normal_alignment
from render import render_preview


def record(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def load_contact():
    path = ROOT / "verification/m6_coupled_probe_002/evaluate.py"
    fixed = subprocess.check_output(["git", "show", "8a99c344caf4560ee87fbb9f7540bf67ff3f2469:verification/m6_coupled_probe_002/evaluate.py"], cwd=ROOT)
    assert path.read_bytes() == fixed
    spec = importlib.util.spec_from_file_location("shape_pairs_contact002", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def export_obj(path, vertices, triangles, name):
    with path.open("w", encoding="utf8", newline="\n") as stream:
        stream.write("# world coordinates in metres; OBJ vertex index = original source ID + 1\n")
        stream.write("# OBJ face row = original source triangle ID + 1\n")
        stream.write("o " + name + "\n")
        for x, y, z in vertices:
            stream.write(f"v {x:.17g} {y:.17g} {z:.17g}\n")
        for a, b, c in triangles:
            stream.write(f"f {a+1} {b+1} {c+1}\n")


def contact_summary(module, before, after, triangles, region, source, private_path, deadline):
    packet = {"state": {"source_id": source, "frame": 1, "coordinate_frame": "saved_world_binary64_m"},
              "vertices_before": before.tolist(), "vertices_candidate": after.tolist(), "triangles": triangles.tolist(),
              "write_ids": region, "target_vertices": None, "protected_ids": [],
              "shape_tolerance_m": 0., "preservation_tolerance_m": 0., "require_no_new_intersections": True}
    result, _, _ = module.evaluate(packet, deadline=deadline)
    write(private_path, module.serializable_result(result))
    return {"query_complete": result["contact_complete"], "no_new_extra_pairs": result["contact_ok"],
            "new_pairs": len(result["new_pairs"]), "removed_pairs": len(result["removed_pairs"]),
            "changed_existing_relations": len(result["changed_relations"]),
            "before_extra_pairs": len(result["before_pairs"]), "after_extra_pairs": len(result["after_pairs"]),
            "before_candidate_pairs": result["before_scan"]["spatial_candidates"], "after_candidate_pairs": result["after_scan"]["spatial_candidates"],
            "before_exact_tests": result["before_scan"]["exact_tests"], "after_exact_tests": result["after_scan"]["exact_tests"],
            "degenerate_faces_before": len(result["before_scan"]["degenerate_face_ids"]),
            "degenerate_faces_after": len(result["after_scan"]["degenerate_face_ids"]),
            "unresolved_before": result["before_scan"]["unknown_pairs"], "unresolved_after": result["after_scan"]["unknown_pairs"],
            "affected_faces": len(result["affected_face_ids"]), "full_evaluate_wall_s": result["total_evaluation_wall_s"],
            "full_evaluate_cpu_s": result["total_evaluation_cpu_s"], "private_facts": record(private_path)}


def main():
    started, cpu_started = time.perf_counter(), time.process_time()
    deadline = started + 1200
    private = HERE / "private"
    private.mkdir(exist_ok=True)
    log_path = HERE / "RUN_LOG.json"
    log = json.loads(log_path.read_bytes()) if log_path.exists() else {"attempts": []}
    attempt = {"attempt": len(log["attempts"]) + 1, "status": "running",
               "scripts_before_run": [record(HERE / name) for name in ("run.py", "generate.py", "method.py", "metrics.py", "render.py")]}
    log["attempts"].append(attempt)
    write(log_path, log)
    result = {"cycle_id": "M6-SHAPE-PAIRS-001", "status": "running", "checks": [], "cases": [], "failures": [],
              "plan_commit": "ce5b2fd38e0a362ecc90df03586dbc139c9dc8ef"}

    def check(name, value):
        result["checks"].append({"name": name, "passed": bool(value)})
        if not value:
            raise AssertionError(name)

    try:
        for name in ("CASE_PLAN.json", "generate.py", "method.py"):
            fixed = subprocess.check_output(["git", "show", f"ce5b2fd38e0a362ecc90df03586dbc139c9dc8ef:verification/m6_shape_pairs_001/{name}"], cwd=ROOT)
            check("frozen source " + name, (HERE / name).read_bytes() == fixed)
        plan = json.loads((HERE / "CASE_PLAN.json").read_bytes())
        old = ROOT / "verification/m6_real_data_001"
        raw_path, patch_path = old / "private/capture_02/raw_selected.json", old / "private/ARM_REGION.json"
        check("frozen raw mesh", record(raw_path)["sha256"] == plan["raw_export_sha256"])
        check("frozen allowed region", record(patch_path)["sha256"] == plan["patch_sha256"])
        inputs_before = [record(raw_path), record(patch_path), record(old / "private/COUPLED_REGION_CONTEXT.json")]
        raw = json.loads(raw_path.read_bytes())
        patch = json.loads(patch_path.read_bytes())
        reference = np.asarray(raw["vertices_world"], dtype=np.float64)
        triangles = np.asarray(raw["triangles"], dtype=np.int64)
        region = patch["source_vertex_ids"]
        region_set = set(region)
        external = [index for index in range(len(reference)) if index not in region_set]
        closure = np.flatnonzero(np.any(np.isin(triangles, region), axis=1))
        load_wall = time.perf_counter() - started
        print("Generating one normal control and six fixed dent variants", flush=True)
        generation_start = time.perf_counter()
        labels = generate(reference, triangles, region, private)
        generation_wall = time.perf_counter() - generation_start
        check("seven cases in one asset group", len(labels["cases"]) == 7 and labels["asset_group"] == plan["asset_group"])
        check("fixed region and boundary", len(region) == 410 and len(labels["boundary_ids"]) == 72 and len(closure) == 898)
        check("algorithm signature has only observation fields", list(inspect.signature(reconstruct).parameters) == ["abnormal_vertices", "triangles", "allowed_region_ids"])
        np.save(private / "triangles.npy", triangles, allow_pickle=False)
        np.save(private / "source_polygon_ids.npy", np.asarray(raw["polygon_ids_by_triangle"], dtype=np.int64), allow_pickle=False)
        reference_obj = private / "reference.obj"
        export_obj(reference_obj, reference, triangles, "reference")
        contact = load_contact()
        triangles.setflags(write=False)
        preview = {"reference_npy": labels["reference_npy"], "triangles_npy": str(private / "triangles.npy"),
                   "region_ids": region, "center_vertex_id": labels["center_vertex_id"], "center_normal": labels["center_normal"], "cases": []}
        for case in labels["cases"]:
            print("Evaluating " + case["id"], flush=True)
            case_started = time.perf_counter()
            abnormal = np.load(case["abnormal_npy"], allow_pickle=False)
            abnormal.setflags(write=False)
            observed_hash = hashlib.sha256(abnormal.tobytes()).hexdigest()
            method_start = time.perf_counter()
            repaired, solver = reconstruct(abnormal, triangles, region)
            method_wall = time.perf_counter() - method_start
            check(case["id"] + " observed input remains immutable", hashlib.sha256(abnormal.tobytes()).hexdigest() == observed_hash)
            check(case["id"] + " full-rank fixed method", solver["rank"] == 338 and solver["matrix_shape"] == [403, 338] and solver["context_columns"] == 480)
            check(case["id"] + " boundary bitwise unchanged", np.array_equal(repaired[labels["boundary_ids"]], abnormal[labels["boundary_ids"]]))
            check(case["id"] + " external bitwise unchanged", np.array_equal(repaired[external], abnormal[external]))
            repaired_path = private / f"{case['id']}_repaired.npy"
            np.save(repaired_path, repaired, allow_pickle=False)
            export_start = time.perf_counter()
            abnormal_obj = reference_obj if case["id"] == "sample_00" else private / f"{case['id']}_abnormal.obj"
            if case["id"] != "sample_00":
                export_obj(abnormal_obj, abnormal, triangles, case["id"] + "_abnormal")
            repaired_obj = private / f"{case['id']}_repaired.obj"
            export_obj(repaired_obj, repaired, triangles, case["id"] + "_repaired")
            export_wall = time.perf_counter() - export_start
            scale = labels["reference_mean_region_edge_length_m"]
            unchanged_error = errors(reference, abnormal, region, scale)
            repaired_error = errors(reference, repaired, region, scale)
            support_before = errors(reference, abnormal, case["true_support_ids"], scale)
            support_after = errors(reference, repaired, case["true_support_ids"], scale)
            damage_contact = contact_summary(contact, reference, abnormal, triangles, region, "shape-pairs-reference/" + labels["asset_group"],
                                             private / f"{case['id']}_damage_contact.json", deadline)
            repair_contact = contact_summary(contact, abnormal, repaired, triangles, region, "shape-pairs-observed/" + observed_hash,
                                             private / f"{case['id']}_repair_contact.json", deadline)
            actual_repair_ids = np.flatnonzero(np.any(repaired != abnormal, axis=1)).tolist()
            actual_repair_closure = np.flatnonzero(np.any(np.isin(triangles, actual_repair_ids), axis=1))
            row = {"id": case["id"], "radius_ratio": case["radius_ratio"], "amplitude_ratio": case["amplitude_ratio"],
                   "radius_m": case["radius_m"], "amplitude_m": case["amplitude_m"], "asset_group": labels["asset_group"],
                   "true_support_vertices": len(case["true_support_ids"]), "generation_actual_incident_faces": len(case["actual_incident_face_ids"]),
                   "max_damage_displacement_m": case["max_actual_displacement_m"], "algorithm_allowed_vertices": 410,
                   "repair_actual_changed_vertices": len(actual_repair_ids), "repair_actual_incident_faces": len(actual_repair_closure),
                   "normal_control": case["amplitude_ratio"] == 0., "no_op_region_error": unchanged_error, "repaired_region_error": repaired_error,
                   "no_op_support_error": support_before, "repaired_support_error": support_after,
                   "region_recovery_fraction": None if unchanged_error["rmse_m"] == 0 else 1 - repaired_error["rmse_m"] / unchanged_error["rmse_m"],
                   "support_recovery_fraction": None if support_before["rmse_m"] in (None, 0.) else 1 - support_after["rmse_m"] / support_before["rmse_m"],
                   "damage_quality_vs_reference": triangle_quality(reference, abnormal, triangles[closure]),
                   "repair_quality_vs_reference": triangle_quality(reference, repaired, triangles[closure]),
                   "repair_quality_vs_observed": triangle_quality(abnormal, repaired, triangles[closure]),
                   "support_normal_alignment": support_normal_alignment(reference, triangles, case["true_support_ids"], np.asarray(labels["center_normal"])),
                   "damage_contact": damage_contact, "repair_contact": repair_contact, "solver": solver,
                   "method_wall_s": method_wall, "export_wall_s": export_wall, "case_wall_s": time.perf_counter() - case_started,
                   "input_sha256": observed_hash, "output_sha256": hashlib.sha256(repaired.tobytes()).hexdigest(),
                   "private_outputs": [record(Path(case["abnormal_npy"])), record(repaired_path), record(abnormal_obj), record(repaired_obj)]}
            result["cases"].append(row)
            preview["cases"].append({"id": case["id"], "radius_ratio": case["radius_ratio"], "amplitude_ratio": case["amplitude_ratio"],
                                     "abnormal_npy": case["abnormal_npy"], "repaired_npy": str(repaired_path)})
        write(private / "PREVIEW_INPUT.json", preview)
        print("Rendering actual mesh comparisons and local viewer", flush=True)
        render_start = time.perf_counter()
        rendered = render_preview(private / "PREVIEW_INPUT.json")
        result["visualization"] = rendered
        result["cost"] = {"load_and_source_guard_wall_s": load_wall, "generation_wall_s": generation_wall,
                          "render_call_wall_s": time.perf_counter() - render_start,
                          "method_wall_s_total": sum(case["method_wall_s"] for case in result["cases"]),
                          "export_wall_s_total": sum(case["export_wall_s"] for case in result["cases"]),
                          "contact_evaluate_calls": 14, "contact_endpoint_queries": 28,
                          "contact_wall_s_total": sum(case[stage]["full_evaluate_wall_s"] for case in result["cases"] for stage in ("damage_contact", "repair_contact")),
                          "contact_cpu_s_total": sum(case[stage]["full_evaluate_cpu_s"] for case in result["cases"] for stage in ("damage_contact", "repair_contact")),
                          "contact_exact_pair_attempts": sum(case[stage][state] for case in result["cases"] for stage in ("damage_contact", "repair_contact") for state in ("before_exact_tests", "after_exact_tests"))}
        for entry in inputs_before:
            check("old input unchanged " + entry["path"], record(Path(entry["path"])) == entry)
        result["source_inputs"] = inputs_before
        result["generation"] = {key: value for key, value in labels.items() if key not in ("cases", "region_ids", "boundary_ids")}
        result["information_barrier"] = {"method_signature": str(inspect.signature(reconstruct)), "calls": 7,
                                         "same_allowed_region_for_all": True, "normal_labels_passed_to_method": False,
                                         "parameters_or_support_passed_to_method": False, "normal_control_uses_same_method": True}
        result["status"] = "completed_single_family_opportunity_probe"
    except Exception as exc:
        result["status"] = "failed"
        result["failures"].append({"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
        print(traceback.format_exc(), flush=True)
    result["cost_before_publication"] = {"wall_s": time.perf_counter() - started, "cpu_s": time.process_time() - cpu_started,
                                         "private_bytes": sum(path.stat().st_size for path in private.rglob("*") if path.is_file()),
                                         "full_process_cpu_with_imports": None, "peak_rss": None, "formal_performance": False}
    result["not_run"] = ["second method or anomaly family", "hyperparameter search", "network training", "cross-asset generalization",
                         "Blender", "M5", "paid API", "artist-accepted repair", "distance/volume/path contact semantics"]
    attempt.update(status=result["status"], cost=result["cost_before_publication"], failures=result["failures"])
    publication_start = time.perf_counter()
    write(HERE / "RESULTS.json", result)
    write(log_path, log)
    write(HERE / "PUBLICATION.json", {"result_log_write_wall_s": time.perf_counter() - publication_start,
                                      "main_wall_s_through_publication": time.perf_counter() - started})
    print(json.dumps({"status": result["status"], "cases": len(result["cases"]), **result["cost_before_publication"]}), flush=True)
    return 0 if result["status"] == "completed_single_family_opportunity_probe" else 1


if __name__ == "__main__":
    raise SystemExit(main())

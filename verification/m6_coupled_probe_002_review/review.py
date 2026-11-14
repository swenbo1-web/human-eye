"""Fixed-byte, non-mutating review of query-scope change 8a99c344."""
import os
for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[key] = "1"
import copy
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SNAP = HERE / "snapshot"
ONE = SNAP / "verification/m6_coupled_probe_001"
TWO = SNAP / "verification/m6_coupled_probe_002"
DATA = ROOT / "verification/m6_real_data_001_review/snapshot/verification/m6_real_data_001"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def check(name, yes):
    if not yes:
        raise AssertionError(name)
    checks.append(name)


def identity(path):
    b = Path(path).read_bytes()
    return {"path": str(path), "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}


def box(points, face):
    values = [points[i] for i in face]
    return [[min(p[a] for p in values) for a in range(3)], [max(p[a] for p in values) for a in range(3)]]


def axis(a, b):
    return next((i for i in range(3) if a[1][i] < b[0][i] or b[1][i] < a[0][i]), None)


def facts(scan):
    return {k: v for k, v in scan.items() if k != "work"} | {"work_counts": scan["work"]["counts"]}


started, cpu_started = time.perf_counter(), time.process_time()
checks = []
manifest = json.loads((HERE / "SNAPSHOT.json").read_bytes())
for row in manifest["snapshot_files"]:
    check("frozen source " + row["relative_path"], identity(row["copy"]["path"]) == row["copy"])
old = load("old_evaluator", ONE / "evaluate.py")
new = load("new_evaluator", TWO / "evaluate.py")
oracle = load("independent_triangle_oracle", ONE / "oracle.py")
new_plan = json.loads((TWO / "CASE_PLAN.json").read_bytes())
scope_results = []
for case in new_plan["cases"]:
    prior, _, _ = old.evaluate(case)
    result, prepared, initial = new.evaluate(case)
    shared, _, _ = new.evaluate(case, shared=True, prepared_before=prepared, scan_before=initial)
    axes = []
    for field, stage in (("vertices_before", "before_scan"), ("vertices_candidate", "after_scan")):
        values = [tuple(Fraction(x) for x in p) for p in case[field]]
        witness = axis(*(box(values, face) for face in case["triangles"]))
        axes.append(witness)
        expected = witness is not None
        check(case["name"] + " " + stage, result[stage]["scan_complete"] == expected and
              result[stage]["spatial_candidates"] == (0 if expected else 1) and
              result[stage]["unknown_pairs"] == (0 if expected else 1) and result[stage]["degenerate_face_ids"] == [1])
        check(case["name"] + " same shared " + stage, facts(result[stage]) == facts(shared[stage]))
        check(case["name"] + " reason " + stage, result[stage]["reason"] == (None if expected else "degenerate_candidate_pairs_unresolved"))
    check(case["name"] + " joint", result["joint_status"] == ("pass" if all(x is not None for x in axes) else "unknown"))
    check(case["name"] + " old status retained", prior["joint_status"] == "unknown")
    scope_results.append({"name": case["name"], "independent_strict_separation_axes": axes,
                          "old_joint": prior["joint_status"], "new_joint": result["joint_status"],
                          "new_contact": result["contact_ok"], "new_shape": result["shape_ok"],
                          "new_preservation": result["preservation_ok"], "full_shared_equal": True})

plan = json.loads((ONE / "CASE_PLAN.json").read_bytes())
references = oracle.verify_plan(plan)
regressions = []
for case, expected in zip(plan["cases"], references["results"]):
    packet = copy.deepcopy(case)
    for field in ("vertices_before", "vertices_candidate"):
        packet[field] = [[float("nan") if x == "NaN" else x for x in p] for p in packet[field]]
    result, _, _ = new.evaluate(packet)
    fields = ["joint_status"] if expected["joint_status"] == "invalid" else ["joint_status", "shape_ok", "preservation_ok", "contact_ok", "affected_face_ids", "scope_complete"]
    if expected.get("scope_complete"):
        fields += ["before_pairs", "after_pairs", "new_pairs"]
    check("original " + case["name"], all(result.get(k) == expected.get(k) for k in fields))
    regressions.append({"name": case["name"], "status": result["joint_status"]})
cache_plan = json.loads((ONE / "CACHE_CASE_PLAN.json").read_bytes())
case = next(x for x in plan["cases"] if x["name"] == cache_plan["base_geometry_case"])
base, prep, _ = new.evaluate(case)
bad_scan, _, _ = new.evaluate(case, prepared_before=prep, scan_before=base["after_scan"])
bad_prep, _, _ = new.evaluate(case, prepared_before=prep.updated(case["vertices_candidate"], case["write_ids"]))
for planned, actual in zip(cache_plan["cases"], (bad_scan, bad_prep)):
    check(planned["name"], actual["joint_status"] == planned["expected_joint_status"] and actual["reason"] == planned["expected_reason"])

old_manifest = json.loads((ONE / "EVIDENCE_MANIFEST.json").read_bytes())
for row in old_manifest["real_inputs"]:
    rel = Path(row["path"]).relative_to(Path(manifest["author_workspace"]) / "verification/m6_real_data_001")
    current = identity(DATA / rel)
    check("reviewer real snapshot " + rel.as_posix(), current["sha256"] == row["sha256"] and current["bytes"] == row["bytes"])
raw = json.loads((DATA / "private/capture_02/raw_selected.json").read_bytes())
patch = json.loads((DATA / "private/ARM_REGION.json").read_bytes())
context = json.loads((DATA / "COUPLED_CONTEXT.json").read_bytes())
prior_review = json.loads((ROOT / "verification/m6_coupled_probe_001_review/INDEPENDENT_RESULTS.json").read_bytes())
recorded = json.loads((ONE / "RESULTS.json").read_bytes())["real"]
before = np.asarray(raw["vertices_world"], dtype="<f8")
after = before.copy(); writes = patch["source_vertex_ids"]; active = set(writes); after[writes, 1] += np.float64(.001)
packet = {"state": {"source_id": context["state"]["snapshot_sha256"], "frame": 1, "subframe": 0., "coordinate_frame": "saved_world_binary64_m"},
          "vertices_before": before.tolist(), "vertices_candidate": after.tolist(), "triangles": raw["triangles"],
          "write_ids": writes, "target_vertices": None, "protected_ids": [i for i in range(len(before)) if i not in active],
          "shape_tolerance_m": 0., "preservation_tolerance_m": 0., "require_no_new_intersections": True}
full, prep, first = new.evaluate(packet)
shared, _, _ = new.evaluate(packet, shared=True, prepared_before=prep, scan_before=first)
check("exact frozen before coordinate hash", hashlib.sha256(before.tobytes()).hexdigest() == recorded["before_coordinates_le_f8_sha256"])
check("exact frozen candidate coordinate hash", hashlib.sha256(after.tobytes()).hexdigest() == recorded["candidate_coordinates_le_f8_sha256"])
check("finite contact true, real target missing", full["contact_ok"] is True and full["shape_ok"] is None and full["joint_status"] == "unknown")
check("same complete affected domain", full["affected_face_ids"] == [i for i, f in enumerate(raw["triangles"]) if any(v in active for v in f)] and len(full["affected_face_ids"]) == 898)
real = []
for field, values, previous in (("before_scan", before, prior_review["real"]["stages"][0]), ("after_scan", after, prior_review["real"]["stages"][1])):
    scan = full[field]
    check(field + " full/shared facts", facts(scan) == facts(shared[field]))
    check(field + " same independently covered candidate set", new.digest(scan["candidates"]) == previous["candidate_pair_sha256"])
    check(field + " same exact facts", scan["legal_simplex_pairs"] == previous["legal_simplex"] and scan["empty_pairs"] == previous["empty"] and not scan["intersections"])
    check(field + " actual complete", scan["scan_complete"] and scan["candidate_complete"] and scan["reason"] is None and not scan["unresolved"])
    check(field + " quality flag retained", scan["degenerate_face_ids"] == previous["independent_degenerates"] and scan["pairs_involving_degenerate_faces"] == 8980)
    face_ids = full["affected_face_ids"] + scan["degenerate_face_ids"]
    vertices = {v for f in face_ids for v in raw["triangles"][f]}
    rational = {i: tuple(Fraction(float(x)) for x in values[i]) for i in vertices}
    bounds = {i: box(rational, raw["triangles"][i]) for i in face_ids}
    counts = [0, 0, 0]
    for a in full["affected_face_ids"]:
        for d in scan["degenerate_face_ids"]:
            witness = axis(bounds[a], bounds[d])
            if witness is None:
                raise AssertionError("real separation missing")
            counts[witness] += 1
    check(field + " independent separation", counts == previous["strict_separation_witnesses_by_axis"] and sum(counts) == 8980)
    real.append({"state": field, "candidate_count": len(scan["candidates"]), "query_complete": scan["scan_complete"],
                 "degenerate_faces": len(scan["degenerate_face_ids"]), "independent_axis_witness_counts": counts,
                 "candidate_pair_sha256": new.digest(scan["candidates"]), "extra_intersections": len(scan["intersections"])})
for row in manifest["manifest_entries"] + [manifest["original_asset"]]:
    check("source unchanged " + row["path"], identity(row["path"]) == row)
result = {"fixed_commit": manifest["commit"], "decision": "accepted_query_scope_fix_close_evaluator_probe",
          "checks_passed": len(checks), "checks": checks, "scope_controls": scope_results, "original_18_controls": regressions,
          "cache_controls": [bad_scan, bad_prep], "real": {"assets": 1, "distinct_candidates": 1, "contact_ok": full["contact_ok"],
          "joint_status": full["joint_status"], "shape": full["shape"], "states": real, "full_shared_equal": True},
          "cost": {"main_wall_s_before_publication": time.perf_counter() - started, "main_cpu_s": time.process_time() - cpu_started,
                   "real_queries": 3, "real_exact_attempts": full["before_scan"]["exact_tests"] + 2 * full["after_scan"]["exact_tests"],
                   "scope_control_queries_old": 6, "scope_control_queries_new": 9, "original_fixture_evaluations": 18,
                   "extra_cache_setup_evaluations": 1, "cache_rejections": 2, "independent_real_separation_witnesses": 17960,
                   "formal_performance": False},
          "scope": "Replayed revised evaluator in isolated fixed-byte snapshot. Independent scalar Fraction separation; existing independent triangle oracle replay. Full candidate-set coverage and face-rank evidence reused from 001 with verified identical geometry and candidate sets.",
          "not_run": ["author mutating runner", "new all-domain AABB enumeration", "training", "models", "Blender", "M5", "artistic correction acceptance", "formal performance"]}
(HERE / "INDEPENDENT_RESULTS.json").write_bytes((json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
print(json.dumps({"decision": result["decision"], "checks_passed": len(checks), "contact_ok": full["contact_ok"], "joint_status": full["joint_status"], "wall_s": result["cost"]["main_wall_s_before_publication"]}))

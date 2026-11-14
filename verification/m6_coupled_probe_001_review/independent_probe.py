"""Read-only replay of fixed 696e8e2a plus query-relevant degeneracy proofs.

Never runs the author's mutating runner. Full real arrays stay in prior local
snapshots; only counts, hashes and constructed controls are published here.
"""
import os
for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[key] = "1"

import copy
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SNAP = HERE / "snapshot"
AUTHOR = SNAP / "verification/m6_coupled_probe_001"
OLD = ROOT / "verification/m6_real_data_001_review/snapshot/verification/m6_real_data_001"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def fingerprint(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def write(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    checks.append(name)


def relevant(value):
    if isinstance(value, dict):
        return {k: relevant(v) for k, v in value.items()
                if k not in ("wall_s", "cpu_s")}
    if isinstance(value, list):
        return [relevant(v) for v in value]
    return value


def exact_box(points, triangle):
    selected = [points[i] for i in triangle]
    return (tuple(min(p[a] for p in selected) for a in range(3)),
            tuple(max(p[a] for p in selected) for a in range(3)))


def separated_axis(a, b):
    return next((i for i in range(3) if a[1][i] < b[0][i] or b[1][i] < a[0][i]), None)


def reviewer_fixture(remote):
    # A normal triangle and a distinct zero-area triangle. Positive x gap is
    # an exact separation witness, regardless of the second primitive's rank.
    tail = [[10, 0, 0], [11, 0, 0], [12, 0, 0]] if remote else [[0, 0, 0], [1, 0, 0], [2, 0, 0]]
    vertices = [[0, 0, 0], [2, 0, 0], [0, 2, 0]] + tail
    return {"state": {"source_id": "reviewer-degenerate-scope", "frame": 1,
                      "coordinate_frame": "saved_world_binary64_m"},
            "vertices_before": vertices, "vertices_candidate": copy.deepcopy(vertices),
            "triangles": [[0, 1, 2], [3, 4, 5]], "write_ids": [0],
            "target_vertices": {"0": [0, 0, 0]}, "shape_tolerance_m": 0,
            "protected_ids": [1, 2, 3, 4, 5], "preservation_tolerance_m": 0,
            "require_no_new_intersections": True}


started, cpu_started = time.perf_counter(), time.process_time()
checks = []
ev = module("reviewed_evaluator", AUTHOR / "evaluate.py")
oracle = module("reviewed_independent_oracle", AUTHOR / "oracle.py")
spatial = module("reviewed_independent_aabb", AUTHOR / "spatial_oracle.py")
manifest = json.loads((HERE / "SNAPSHOT.json").read_bytes())
for row in manifest["snapshot_files"]:
    check("snapshot bytes " + row["relative_path"], fingerprint(Path(row["copy"]["path"])) == row["copy"])

plan = json.loads((AUTHOR / "CASE_PLAN.json").read_bytes())
reference = oracle.verify_plan(plan)
controls = []
for case, expected in zip(plan["cases"], reference["results"]):
    packet = copy.deepcopy(case)
    for field in ("vertices_before", "vertices_candidate"):
        packet[field] = [[float("nan") if x == "NaN" else x for x in p] for p in packet[field]]
    result, _, _ = ev.evaluate(packet)
    fields = ["joint_status"] if expected["joint_status"] == "invalid" else [
        "joint_status", "shape_ok", "preservation_ok", "contact_ok", "affected_face_ids", "scope_complete"]
    if expected.get("scope_complete"):
        fields += ["before_pairs", "after_pairs", "new_pairs"]
    check("frozen control " + case["name"], all(result.get(k) == expected.get(k) for k in fields))
    controls.append({"name": case["name"], "result": result["joint_status"], "fields_compared": fields})

cache_plan = json.loads((AUTHOR / "CACHE_CASE_PLAN.json").read_bytes())
case = next(c for c in plan["cases"] if c["name"] == cache_plan["base_geometry_case"])
base_result, prepared, _ = ev.evaluate(case)
stale_scan, _, _ = ev.evaluate(case, prepared_before=prepared, scan_before=base_result["after_scan"])
changed_preparation = prepared.updated(case["vertices_candidate"], case["write_ids"])
stale_preparation, _, _ = ev.evaluate(case, prepared_before=changed_preparation)
for planned, actual in zip(cache_plan["cases"], (stale_scan, stale_preparation)):
    check("cache " + planned["name"], actual["joint_status"] == planned["expected_joint_status"] and
          actual["reason"] == planned["expected_reason"])

reviewer_cases = []
for remote in (True, False):
    packet = reviewer_fixture(remote)
    result, _, _ = ev.evaluate(packet)
    rational = [tuple(Fraction(x) for x in p) for p in packet["vertices_before"]]
    witness = separated_axis(*(exact_box(rational, f) for f in packet["triangles"]))
    check("reviewer separation witness " + str(remote), (witness is not None) == remote)
    check("current degenerate status " + str(remote), result["contact_ok"] is None and result["joint_status"] == "unknown")
    check("candidate relevance " + str(remote), result["after_scan"]["spatial_candidates"] == (0 if remote else 1))
    reviewer_cases.append({"name": "remote_degenerate" if remote else "overlapping_degenerate",
                           "input": packet, "separating_axis": witness,
                           "expected_contact": True if remote else None,
                           "expected_joint": "pass" if remote else "unknown",
                           "observed": {k: result[k] for k in ("shape_ok", "preservation_ok", "contact_ok", "joint_status")},
                           "demonstrated_false_unknown": remote})

old_manifest = json.loads((AUTHOR / "EVIDENCE_MANIFEST.json").read_bytes())
inputs = []
for row in old_manifest["real_inputs"]:
    rel = Path(row["path"]).relative_to(Path(manifest["author"]) / "verification/m6_real_data_001")
    current = fingerprint(OLD / rel)
    check("prior frozen input " + rel.as_posix(), current["sha256"] == row["sha256"] and current["bytes"] == row["bytes"])
    inputs.append(current)
raw = json.loads((OLD / "private/capture_02/raw_selected.json").read_bytes())
patch = json.loads((OLD / "private/ARM_REGION.json").read_bytes())
context = json.loads((OLD / "COUPLED_CONTEXT.json").read_bytes())
before = np.asarray(raw["vertices_world"], dtype="<f8")
after = before.copy()
writes = patch["source_vertex_ids"]
after[writes, 1] += np.float64(.001)
write_set = set(writes)
triangles = raw["triangles"]
incident = [i for i, face in enumerate(triangles) if any(v in write_set for v in face)]
check("410 writes and 898 incident faces including 150 boundary faces", len(writes) == 410 and len(incident) == 898 and
      len(set(incident) - set(patch["source_triangle_ids"])) == 150)
packet = {"state": {"source_id": context["state"]["snapshot_sha256"], "frame": 1, "subframe": 0.,
                    "coordinate_frame": "saved_world_binary64_m"},
          "vertices_before": before.tolist(), "vertices_candidate": after.tolist(), "triangles": triangles,
          "write_ids": writes, "target_vertices": None, "protected_ids": [i for i in range(len(before)) if i not in write_set],
          "shape_tolerance_m": 0., "preservation_tolerance_m": 0., "require_no_new_intersections": True}
full, prepared, scan = ev.evaluate(packet)
shared, _, _ = ev.evaluate(packet, shared=True, prepared_before=prepared, scan_before=scan)
recorded = json.loads((AUTHOR / "RESULTS.json").read_bytes())["real"]
check("candidate identity", hashlib.sha256(after.tobytes()).hexdigest() == recorded["candidate_coordinates_le_f8_sha256"])
check("source identity", hashlib.sha256(before.tobytes()).hexdigest() == recorded["before_coordinates_le_f8_sha256"])
check("unchanged outside writes", np.array_equal(before[packet["protected_ids"]], after[packet["protected_ids"]]))
for stage in ("before_scan", "after_scan"):
    check("full versus shared " + stage, relevant(full[stage]) == relevant(shared[stage]))
for field in ("shape", "preservation", "contact_ok", "contact_complete", "joint_status", "new_pairs", "removed_pairs", "changed_relations"):
    check("full versus shared " + field, full[field] == shared[field])

real_stages = []
for name, values, stage in (("before", before, full["before_scan"]), ("candidate", after, full["after_scan"])):
    pairs, stats = spatial.candidates(values, triangles, incident)
    check("independent AABB set " + name, pairs == stage["candidates"])
    check("full unordered denominator " + name, stats["domain_pairs"] == 898 * 52366 + 898 * 897 // 2 == 47427421)
    check("same author pair set " + name, ev.digest(pairs) == recorded[name]["candidate_pair_sha256"])
    # Fresh Fraction coordinates, exact cross products and scalar separation
    # witnesses: independent from both the product normal/BVH and NumPy oracle.
    point_values = [tuple(Fraction(float(x)) for x in p) for p in values]
    degenerates = []
    for i, face in enumerate(triangles):
        a, b, c = (point_values[v] for v in face)
        u = tuple(b[k] - a[k] for k in range(3)); v = tuple(c[k] - a[k] for k in range(3))
        if all(u[(k+1)%3] * v[(k+2)%3] == u[(k+2)%3] * v[(k+1)%3] for k in range(3)):
            degenerates.append(i)
    check("exact independent degenerates " + name, degenerates == stage["degenerate_face_ids"] and len(degenerates) == 10)
    check("all degenerate faces outside incident set " + name, not set(degenerates).intersection(incident))
    boxes = {i: exact_box(point_values, triangles[i]) for i in incident + degenerates}
    witness_axes = [0, 0, 0]
    for d in degenerates:
        for a in incident:
            axis = separated_axis(boxes[a], boxes[d])
            check_name = "strict separating witness for every degenerate pair " + name
            if axis is None:
                raise AssertionError(check_name)
            witness_axes[axis] += 1
    check("8980 independently separated degenerate pairs " + name, sum(witness_axes) == 8980)
    check("no unresolved candidate pairs " + name, stage["unknown_pairs"] == stage["unstarted_exact_pairs"] == stage["unaccounted_domain_pairs"] == 0)
    check("no extra intersections " + name, not stage["intersections"])
    real_stages.append({"state": name, "domain": stage["pair_domain"], "aabb_candidates": len(pairs),
                        "candidate_pair_sha256": ev.digest(pairs), "exact_leaf_attempts": stage["exact_tests"],
                        "legal_simplex": stage["legal_simplex_pairs"], "empty": stage["empty_pairs"],
                        "independent_degenerates": degenerates, "strict_separation_witnesses_by_axis": witness_axes,
                        "known_disjoint_degenerate_pairs": sum(witness_axes), "original_contact_ok": full["contact_ok"],
                        "query_complete_despite_mesh_quality_flag": True, "independent_aabb": stats})

for row in manifest["manifest_files_checked"] + [manifest["original_asset"]]:
    check("source unchanged " + row["path"], fingerprint(Path(row["path"])) == row)
for row in inputs:
    check("review input unchanged " + row["path"], fingerprint(Path(row["path"])) == row)
check("missing real target remains unknown", full["shape_ok"] is None and full["joint_status"] == "unknown")
result = {"reviewed_commit": manifest["commit"], "status": "review_completed_one_confirmed_false_unknown",
          "checks_passed": len(checks), "checks": checks, "frozen_control_replays": controls,
          "cache_rejections": [stale_scan, stale_preparation], "reviewer_constructed_cases": reviewer_cases,
          "real": {"assets": 1, "distinct_candidates": 1, "writes": len(writes), "affected_faces": len(incident),
                   "stages": real_stages, "new_pairs": full["new_pairs"], "shape_missing": True,
                   "full_shared_equal": True, "full_evaluation_wall_s": full["total_evaluation_wall_s"],
                   "shared_evaluation_wall_s": shared["total_evaluation_wall_s"],
                   "shared_cold_wall_s": shared["total_evaluation_wall_s"] + full["before_preparation"]["wall_s"] + scan["work"]["wall_s"],
                   "candidate_preparation_full": full["candidate_preparation"], "candidate_preparation_shared": shared["candidate_preparation"]},
          "cost": {"wall_s_before_publication": time.perf_counter() - started, "cpu_s_before_publication": time.process_time() - cpu_started,
                   "real_queries": 3, "real_exact_pair_attempts": full["before_scan"]["exact_tests"] + 2 * full["after_scan"]["exact_tests"],
                   "frozen_fixture_evaluations": 18, "extra_cache_setup_evaluations": 1, "cache_rejections": 2,
                   "reviewer_fixture_evaluations": 2, "independent_rational_face_rank_checks": 2 * len(triangles),
                   "independent_scalar_degenerate_pair_witnesses": 17960, "formal_performance": False},
          "not_run": ["Blender", "M5", "training", "model consumer", "artistic acceptance", "all-real-pair independent triangle oracle"],
          "inputs": inputs, "python": sys.version}
write(HERE / "INDEPENDENT_RESULTS.json", result)
print(json.dumps({"status": result["status"], "checks_passed": len(checks), "real_candidates": [r["aabb_candidates"] for r in real_stages],
                  "degenerate_pairs_independently_separated_each_state": 8980, "wall_s": result["cost"]["wall_s_before_publication"]}))

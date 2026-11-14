"""Independent geometry and input-information checks on a fixed Git export."""
import os
for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[key] = "1"

from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import types

import numpy as np

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE / "snapshot"
sys.path.insert(0, str(SNAPSHOT))
package = types.ModuleType("human_eye_plugin")
package.__path__ = [str(SNAPSHOT / "human_eye_plugin")]
sys.modules["human_eye_plugin"] = package
from human_eye_plugin.arm_twist_expert import extract_features
from human_eye_plugin.arm_twist_correction import preview_axial_redistribution


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def areas(vertices, sections):
    """Oriented triangle fans, independent of covariance and saved area code."""
    result = []
    vertices = np.asarray(vertices, dtype=float)
    for section in sections:
        points = vertices[section]
        triangles = np.cross(points[1:-1] - points[0], points[2:] - points[0])
        result.append(float(np.linalg.norm(triangles.sum(axis=0)) * .5))
    return np.asarray(result)


def yaw(degrees):
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return np.array([[c, 0, s, 0], [0, 1, 0, 0], [-s, 0, c, 0], [0, 0, 0, 1]], dtype=float)


def pose_parameters(patch):
    rests = [np.asarray(bone["rest_matrix"]) for bone in patch["bone_chain"]]
    poses = [np.asarray(bone["pose_matrix"]) for bone in patch["bone_chain"]]
    angles = []
    for i in (1, 2):
        rest_relative = np.linalg.solve(rests[i-1], rests[i])
        posed_relative = np.linalg.solve(poses[i-1], poses[i])
        basis = np.linalg.solve(rest_relative, posed_relative)
        angles.append(math.degrees(math.atan2(basis[0, 2], basis[0, 0])))
    return rests, poses, sum(angles)


def geometry_at(patch, u):
    rests, before, theta = pose_parameters(patch)
    poses = [before[0]]
    for i, angle in ((1, u), (2, theta-u)):
        poses.append(poses[-1] @ np.linalg.solve(rests[i-1], rests[i]) @ yaw(angle))
    homogeneous = np.column_stack((np.asarray(patch["rest_vertices"]), np.ones(len(patch["rest_vertices"]))))
    weights = np.asarray(patch["weights"])
    current = np.zeros((len(homogeneous), 3))
    for i in range(len(rests)):
        current += weights[:, i, None] * (poses[i] @ np.linalg.solve(rests[i], homogeneous.T)).T[:, :3]
    ratios = areas(current, patch["sections"]) / areas(patch["rest_vertices"], patch["sections"])
    return current, poses, float(max(0, (1-ratios).max()))


def main():
    data_path = SNAPSHOT / "verification/m6_arm_expert_001/run_01/dataset.json.gz"
    cases = json.loads(gzip.decompress(data_path.read_bytes()))
    splits = {}
    signatures = {}
    duplicates = {decimals: {} for decimals in (8, 10, 12)}
    errors = Counter()
    for case in cases:
        packet, meta = case["packet"], case["metadata"]
        split = meta["split"]
        record = splits.setdefault(split, {"assets": set(), "cases": 0, "sections": 0, "tp": 0, "fp": 0, "fn": 0})
        record["assets"].add(meta["asset_id"]); record["cases"] += 1
        labels = np.asarray(case["label_severity"])
        measured = np.maximum(0, 1-areas(packet["current_vertices"], packet["sections"])/areas(packet["rest_vertices"], packet["sections"]))
        positive, predicted = labels >= .15, measured >= .15
        record["sections"] += len(labels)
        for name, mask in (("tp", positive & predicted), ("fp", ~positive & predicted), ("fn", positive & ~predicted)):
            record[name] += int(mask.sum())
        if not np.array_equal(positive, predicted):
            raise AssertionError(("geometric diagnosis differs", meta["case_id"]))
        static = {key: packet[key] for key in ("rest_vertices", "weights", "triangles", "sections", "vertex_ids")}
        static["bone_rest"] = [{key: bone[key] for key in ("name", "parent", "rest_matrix")} for bone in packet["bone_chain"]]
        signature = hashlib.sha256(encoded(static)).hexdigest()
        signatures.setdefault(signature, set()).add(split)
        features, context = extract_features(packet)
        if context["reason"]:
            raise AssertionError(context["reason"])
        for decimals, groups in duplicates.items():
            for feature, label in zip(features, labels):
                key = tuple(round(float(value), decimals) for value in feature)
                groups.setdefault(key, []).append((split, float(label)))
    assert all(len(value) == 1 for value in signatures.values())
    for record in splits.values():
        record["assets"] = len(record["assets"])
    duplicate_counts = {}
    for decimals, groups in duplicates.items():
        shared = [rows for rows in groups.values() if {split for split, label in rows} >= {"train", "test"}]
        duplicate_counts[decimals] = {
            "unique_vectors": len(groups), "train_test_shared_vectors": len(shared),
            "test_shared_rows": sum(split == "test" for rows in shared for split, label in rows),
            "test_shared_positive_rows": sum(split == "test" and label >= .15 for rows in shared for split, label in rows),
        }
    assert all(row == {"unique_vectors": 298, "train_test_shared_vectors": 5, "test_shared_rows": 202, "test_shared_positive_rows": 0} for row in duplicate_counts.values())

    packets = json.loads((SNAPSHOT / "verification/arm_twist_correction_preview_001/cpu_final/INPUT_PACKETS.json").read_bytes())
    selected = {row["case_id"]: row for row in packets if row["case_id"] in ("round_120", "unreachable_120")}
    assert selected["round_120"]["patch"] == selected["unreachable_120"]["patch"]
    probes = []
    for name, row in selected.items():
        patch, task = row["patch"], row["task"]
        lo, hi = task["u_interval_deg"]
        grid = np.linspace(lo, hi, int(round(hi-lo))+1)
        losses = [geometry_at(patch, float(u))[2] for u in grid]
        best_u = float(grid[int(np.argmin(losses))])
        product = preview_axial_redistribution(patch, task)
        current, poses, loss = geometry_at(patch, best_u)
        assert abs(best_u-product["optimal_u_deg"]) < 1e-10
        assert abs(loss-product["objective"]["after"]["max_section_area_loss"]) < 1e-10
        before_end = np.asarray(patch["bone_chain"][-1]["pose_matrix"])
        assert np.max(np.abs(poses[-1]-before_end)) < 1e-12
        if product["candidate"] is not None:
            assert np.max(np.abs(current-np.asarray(product["candidate"]["current_vertices"]))) < 1e-12
        probes.append({"case": name, "status": product["status"], "measured_grid_points": len(grid), "grid_best_u_deg": best_u, "measured_loss": loss, "target": task["max_section_area_loss"], "method": "FK and direct per-vertex LBS; independent triangle-fan area, one-degree grid, not a global optimum proof"})
    original = json.loads((SNAPSHOT / "verification/m6_select_001/RESULTS.json").read_bytes())
    replay = json.loads((HERE / "author_replay/RESULTS.json").read_bytes())
    assert original["actual_this_batch"] == replay["actual_this_batch"]
    result = {
        "status": "passed", "reviewed_commit": "12d46730b94e758c3c426f5c0d3122a40eecad9e",
        "author_audit_replayed_checks": len(replay["actual_this_batch"]["checks"]),
        "author_replay_actual_results_equal_saved": True,
        "root_independent_geometry_diagnostics": len(cases), "root_splits": splits,
        "static_bindings": len(signatures), "feature_duplicate_counts": duplicate_counts,
        "root_independent_task_probes": probes,
        "frozen_weights_imported": "human_eye_plugin.arm_twist_weights" in sys.modules,
        "not_run": ["training", "frozen network inference", "Blender", "formal performance", "real-character quality"],
        "scope": "Supports the finite synthetic-domain audit and requirement to include task conditions. Does not select an architecture or establish absence of learning value on real assets.",
    }
    (HERE / "INDEPENDENT_RESULTS.json").write_bytes((json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode())
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

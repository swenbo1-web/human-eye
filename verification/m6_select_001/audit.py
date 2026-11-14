"""Replay the frozen M6 inventory and correctness probes without training.

Run with Python -I -B. Only this script's output directory is written.
The package stub avoids the Blender add-on initializer.
"""
from __future__ import annotations

import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
import ast
from collections import Counter, defaultdict
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import platform
import subprocess
import sys
import types

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
DISPATCH = "c1ba88d233df052688b62e293a7ad61f5ba7dcef"
ACCEPTED = "d01d49bc0ec82583b24a8faf22e622e6f6ea8c5d"
PRODUCT_FILES = [f"human_eye_plugin/arm_twist_{name}.py"
                 for name in ("expert", "weights", "source", "correction")]
DATA = "verification/m6_arm_expert_001/run_01/dataset.json.gz"
PACKETS = "verification/arm_twist_correction_preview_001/cpu_final/INPUT_PACKETS.json"
HISTORY_NAMES = [
    "M6_ARM_EXPERT_001_REVIEW.md", "M6_ARM_EXPERT_OPT_001_REVIEW.md",
    "M6_ARM_SOURCE_OPT_001_REVIEW.md", "ARCH_EXPERT_ENTRY_OPT_001_REVIEW.md",
    "ARM_CORRECTION_PREVIEW_OPT_001_REVIEW.md",
    "ARM_CORRECTION_EXECUTION_OPT_001_REVIEW.md", "ARCHITECTURE_STAGE_CLOSEOUT.md",
]
sys.path.insert(0, str(ROOT))
package = types.ModuleType("human_eye_plugin")
package.__path__ = [str(ROOT / "human_eye_plugin")]
sys.modules["human_eye_plugin"] = package

import numpy as np
from human_eye_plugin.arm_twist_expert import FEATURE_NAMES, extract_features
from human_eye_plugin.arm_twist_correction import preview_axial_redistribution
from verification.m6_arm_expert_001.geometry_baseline import predict as geometry_predict
from verification.arm_twist_correction_preview_001.cases import CASE_DEFINITIONS
from verification.arm_twist_correction_preview_001.oracle import known_objective


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def file_record(path):
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": sha(raw)}


def static_fields(packet):
    return {key: packet[key] for key in
            ("rest_vertices", "weights", "triangles", "sections", "vertex_ids")} | {
        "bone_chain": [{key: bone[key] for key in ("name", "parent", "rest_matrix")}
                       for bone in packet["bone_chain"]]}


def metrics(truth, scores):
    positive = np.asarray(truth) >= .15
    predicted = np.asarray(scores) >= .15
    tp = int(np.sum(positive & predicted))
    fp = int(np.sum(~positive & predicted))
    fn = int(np.sum(positive & ~predicted))
    return {"sections": len(truth), "mae": float(np.mean(np.abs(np.asarray(truth) - scores))),
            "max_error": float(np.max(np.abs(np.asarray(truth) - scores))),
            "tp": tp, "fp": fp, "fn": fn, "f1": 2 * tp / max(1, 2 * tp + fp + fn)}


def duplicate_audit(rows, decimals):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(np.round(row["features"], decimals))].append(row)
    split_keys = {split: {key for key, group in groups.items()
                         if any(row["split"] == split for row in group)}
                  for split in ("train", "validation", "test")}
    cross = {}
    for left, right in itertools.combinations(split_keys, 2):
        common = split_keys[left] & split_keys[right]
        cross[f"{left}:{right}"] = {
            "shared_vectors": len(common),
            f"{left}_rows": sum(row["split"] == left for key in common for row in groups[key]),
            f"{right}_rows": sum(row["split"] == right for key in common for row in groups[key]),
            "positive_rows": sum(row["label"] >= .15 for key in common for row in groups[key]),
        }
    return {"round_decimal_places": decimals, "rows": len(rows), "unique_vectors": len(groups),
            "repeated_vector_groups": sum(len(group) > 1 for group in groups.values()),
            "label_conflicting_groups_at_1e_8": sum(
                max(row["label"] for row in group) - min(row["label"] for row in group) > 1e-8
                for group in groups.values()), "cross_split": cross}


def run(out, history_root):
    checks = []

    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)

    sources = []
    for relative in PRODUCT_FILES:
        current = (ROOT / relative).read_bytes()
        dispatch = git("show", f"{DISPATCH}:{relative}")
        accepted = git("show", f"{ACCEPTED}:{relative}")
        equal = current.replace(b"\r\n", b"\n") == dispatch.replace(b"\r\n", b"\n")
        check(f"unchanged product {relative}", equal and dispatch == accepted)
        sources.append({"path": relative, "working_sha256": sha(current),
                        "dispatch_git_sha256": sha(dispatch), "accepted_git_sha256": sha(accepted),
                        "working_matches_dispatch_normalized_lf": equal})
    tree = ast.parse((ROOT / PRODUCT_FILES[1]).read_text(encoding="utf8"))
    weights = next(ast.literal_eval(node.value) for node in tree.body
                   if isinstance(node, ast.Assign) and any(
                       isinstance(target, ast.Name) and target.id == "PARAMETERS" for target in node.targets))
    parameter_count = sum(np.asarray(weights[key]).size for key in ("w1", "b1", "w2", "b2"))
    check("145 frozen trained parameters", parameter_count == 145)
    raw = gzip.decompress((ROOT / DATA).read_bytes())
    check("dataset hash equals frozen weight declaration", sha(raw) == weights["training"]["dataset_sha256"])
    cases = json.loads(raw)
    assets = defaultdict(list)
    rows = []
    case_rows = []
    max_label_error = 0.
    for index, case in enumerate(cases):
        meta, packet = case["metadata"], case["packet"]
        assets[meta["asset_id"]].append(case)
        features, context = extract_features(packet)
        if context["reason"]:
            raise AssertionError((meta["case_id"], context["reason"]))
        scores = geometry_predict(packet)
        labels = np.asarray(case["label_severity"])
        expected = []
        for section in packet["sections"]:
            alpha = sum(packet["weights"][section[0]][meta["joint_index"]:])
            severity = (4 * alpha * (1 - alpha) * np.sin(np.deg2rad(meta["angle_deg"]) / 2)**2
                        if meta["pose_family"] == "anomalous_twist" else 0.)
            expected.append(severity)
        max_label_error = max(max_label_error, float(np.max(np.abs(labels - expected))))
        for section_index, feature in enumerate(features):
            rows.append({"case_id": meta["case_id"], "split": meta["split"],
                         "section": section_index, "features": feature, "label": float(labels[section_index])})
        case_rows.append({"dataset_index": index, "case_id": meta["case_id"], "asset_id": meta["asset_id"],
                          "split": meta["split"], "pose_family": meta["pose_family"],
                          "pair_id": meta["pair_id"], "sections": len(labels),
                          "positive_sections_at_0_15": int(np.sum(labels >= .15)),
                          "geometry_scores": scores.tolist(), "labels": labels.tolist()})
    check("11 assets and 77 poses", len(assets) == 11 and len(cases) == 77)
    check("analytic diagnostic labels independently recomputed", max_label_error < 1e-12)
    asset_records = []
    for asset_id, selected in sorted(assets.items()):
        packet, meta = selected[0]["packet"], selected[0]["metadata"]
        signatures = {sha(encode(static_fields(case["packet"]))) for case in selected}
        check(f"static binding and split stable {asset_id}", len(signatures) == 1 and
              len({case["metadata"]["split"] for case in selected}) == 1)
        asset_records.append({"asset_id": asset_id, "split": meta["split"], "poses": len(selected),
                              "shape_family": meta["shape_family"], "skeleton_family": meta["skeleton_family"],
                              "weight_family": meta["weight_family"], "bones": len(packet["bone_chain"]),
                              "vertices": len(packet["rest_vertices"]), "triangles": len(packet["triangles"]),
                              "sections_per_pose": len(packet["sections"]), "static_sha256": next(iter(signatures)),
                              "rest_sha256": sha(encode(packet["rest_vertices"])),
                              "weights_sha256": sha(encode(packet["weights"])),
                              "topology_sha256": sha(encode(packet["triangles"]))})
    overlaps = {}
    for left, right in itertools.combinations(("train", "validation", "test"), 2):
        overlaps[f"{left}:{right}"] = {}
        for field in ("asset_id", "static_sha256", "rest_sha256", "weights_sha256", "shape_family",
                      "skeleton_family", "weight_family", "topology_sha256"):
            a = {row[field] for row in asset_records if row["split"] == left}
            b = {row[field] for row in asset_records if row["split"] == right}
            overlaps[f"{left}:{right}"][field] = sorted(a & b)
        check(f"asset and static binding split isolation {left}:{right}",
              not overlaps[f"{left}:{right}"]["asset_id"] and
              not overlaps[f"{left}:{right}"]["static_sha256"])
    splits = {}
    recomputed_geometry = {}
    for split in ("train", "validation", "test"):
        selected = [row for row in case_rows if row["split"] == split]
        splits[split] = {"assets": sum(row["split"] == split for row in asset_records),
                         "cases": len(selected), "sections": sum(row["sections"] for row in selected),
                         "positive_sections_at_0_15": sum(row["positive_sections_at_0_15"] for row in selected),
                         "positive_cases_at_0_15": sum(row["positive_sections_at_0_15"] > 0 for row in selected),
                         "pose_families": dict(Counter(row["pose_family"] for row in selected))}
        truth = np.concatenate([row["labels"] for row in selected])
        scores = np.concatenate([row["geometry_scores"] for row in selected])
        recomputed_geometry[split] = metrics(truth, scores)
        recomputed_geometry[split]["positive_case_localization_iou"] = float(np.mean([
            np.sum((np.asarray(row["labels"]) >= .15) & (np.asarray(row["geometry_scores"]) >= .15)) /
            np.sum((np.asarray(row["labels"]) >= .15) | (np.asarray(row["geometry_scores"]) >= .15))
            for row in selected if row["positive_sections_at_0_15"]]))
    duplicates = [duplicate_audit(rows, decimals) for decimals in (8, 10, 12)]
    pairs = defaultdict(list)
    for case in cases:
        if case["metadata"]["pose_family"] in ("anomalous_twist", "same_angle_preserved"):
            pairs[case["metadata"]["pair_id"]].append(case)
    check("22 same-angle abnormal/preserved pairs", len(pairs) == 22 and all(len(pair) == 2 for pair in pairs.values()))
    check("geometry diagnostic threshold and localization controls", all(
        value["fp"] == value["fn"] == 0 and value["positive_case_localization_iou"] == 1.
        for value in recomputed_geometry.values()))

    frozen = json.loads((ROOT / PACKETS).read_bytes())
    definitions = {row[0]: row for row in CASE_DEFINITIONS}
    previews = {}
    replay = []
    for row in frozen:
        _, _, theta, current_u, interval, expected_status, _ = definitions[row["case_id"]]
        lower, upper = interval if interval is not None else (min(0., theta), max(0., theta))
        optimal = min(upper, max(lower, theta / 2))
        expected_u = current_u if expected_status == "no_op" else optimal
        report = preview_axial_redistribution(row["patch"], row["task"])
        previews[row["case_id"]] = report
        check(f"frozen correction status {row['case_id']}", report["status"] == expected_status)
        check(f"zero model calls {row['case_id']}", report["work"]["model_calls"] == 0)
        if report["objective"] is not None:
            check(f"independent objective {row['case_id']}",
                  abs(report["objective"]["before"]["max_section_area_loss"] - known_objective(theta, current_u)) < 1e-10 and
                  abs(report["objective"]["after"]["max_section_area_loss"] - known_objective(theta, expected_u)) < 1e-10)
            check(f"independent optimal angle {row['case_id']}", abs(report["optimal_u_deg"] - optimal) < 1e-10)
            preservation = report["preservation"]
            check(f"frozen preservation {row['case_id']}",
                  preservation["max_fixed_end_matrix_delta"] <= row["task"]["angle_tolerance_deg"] and
                  preservation["max_centerline_delta_m"] <= row["task"]["position_tolerance_m"] and
                  preservation["max_protected_vertex_delta_m"] <= row["task"]["position_tolerance_m"])
        replay.append({"case_id": row["case_id"], "status": report["status"],
                       "optimal_u_deg": report.get("optimal_u_deg"), "reason": report["reason"],
                       "objective": report["objective"], "preservation": report["preservation"], "work": report["work"]})
    control = next(row for row in frozen if row["case_id"] == "round_120")
    constrained = next(row for row in frozen if row["case_id"] == "unreachable_120")
    f1, _ = extract_features(control["patch"])
    f2, _ = extract_features(constrained["patch"])
    changed_fields = [key for key in control["task"] if control["task"][key] != constrained["task"][key]]
    check("task probe identical input geometry and diagnostic features", control["patch"] == constrained["patch"] and np.array_equal(f1, f2))
    check("task probe changes only allowed interval", changed_fields == ["u_interval_deg"])
    check("task probe independent closed-form optima", abs(previews["round_120"]["optimal_u_deg"] - 60) < 1e-10 and
          abs(previews["unreachable_120"]["optimal_u_deg"] - 110) < 1e-10)
    task_probe = {"source": PACKETS, "constructed_cases_this_batch": 0,
                  "case_ids": [control["case_id"], constrained["case_id"]],
                  "patch_sha256": sha(encode(control["patch"])), "features_bitwise_equal": bool(np.array_equal(f1, f2)),
                  "changed_task_fields": changed_fields, "intervals_deg": [control["task"]["u_interval_deg"], constrained["task"]["u_interval_deg"]],
                  "area_target": control["task"]["max_section_area_loss"],
                  "correct_outputs": [{"status": previews[name]["status"], "optimal_u_deg": previews[name]["optimal_u_deg"]}
                                      for name in ("round_120", "unreachable_120")],
                  "finding": "A correction predictor needs task constraints. Full-input geometry correctly handles both tasks."}
    author_path = ROOT / "verification/m6_arm_expert_001/run_01/result.json"
    author = json.loads(author_path.read_bytes())
    history = []
    for name in HISTORY_NAMES:
        path = history_root / name
        history.append(file_record(path) if path.exists() else {"path": str(path), "missing": True})
    inputs = [file_record(ROOT / relative) for relative in
              [DATA, PACKETS, "verification/m6_value_baseline_001/BASELINE.json",
               "verification/m6_arm_expert_001/run_01/result.json", "verification/m6_arm_expert_001/synthetic.py",
               "verification/m6_arm_expert_001/geometry_baseline.py",
               "verification/arm_twist_correction_preview_001/cases.py",
               "verification/arm_twist_correction_preview_001/oracle.py"]]
    inventory = {"cycle_id": "M6-SELECT-001", "dispatch_commit": DISPATCH, "workspace": str(ROOT),
                 "sources": sources, "evidence_files": inputs, "historical_reviews_read_only": history,
                 "dataset_uncompressed_bytes": len(raw), "dataset_uncompressed_sha256": sha(raw),
                 "provenance": "11 procedural tube assets from one generator; no captured real-character asset in this dataset",
                 "counts": {"assets": len(assets), "poses": len(cases), "section_rows": len(rows),
                            "same_angle_pairs": len(pairs), "unique_static_bindings": len({row['static_sha256'] for row in asset_records}),
                            "unique_topologies": len({row['topology_sha256'] for row in asset_records})},
                 "assets": asset_records, "splits": splits, "cross_split_overlaps": overlaps,
                 "feature_names": list(FEATURE_NAMES), "feature_duplicates": duplicates,
                 "labels": {"diagnostic_severity_cases": 77, "analytic_reference_vertex_cases": 77,
                            "artist_accepted_corrections": 0, "task_conditioned_training_cases": 0,
                            "candidate_preference_labels": 0, "temporal_sequences": 0,
                            "separate_frozen_geometric_task_fixtures": 8,
                            "reference_meaning": "SO(2) section rotation for axial poses, nominal LBS for bending; supervision only",
                            "missing": ["real source-bound independent characters", "artist/task acceptance labels",
                                        "diagnostic training-task constraints", "temporal ordering/winding",
                                        "face examples", "shape-basis or corrective coefficient labels"]},
                 "case_index": [{key: value for key, value in row.items() if key not in ("geometry_scores", "labels")} for row in case_rows]}
    results = {"cycle_id": "M6-SELECT-001", "status": "passed", "dispatch_commit": DISPATCH,
               "environment": {"python": sys.version, "executable": sys.executable, "numpy": np.__version__,
                               "platform": platform.platform(), "thread_limits": {key: os.environ[key] for key in
                               ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")}},
               "command": "python -I -B -X utf8 verification/m6_select_001/audit.py",
               "trained_parameter_count": parameter_count, "fitted_preprocessing_scalars": 20,
               "actual_this_batch": {"label_max_abs_error": max_label_error,
                                     "geometry_diagnostic_metrics": recomputed_geometry,
                                     "feature_duplicates": duplicates, "frozen_correction_replays": replay,
                                     "task_information_probe": task_probe, "checks": checks},
               "historical_author_results_not_rerun": {"path": str(author_path), "sha256": sha(author_path.read_bytes()),
                                                        "test_model": author["results"]["test"]["model"],
                                                        "test_geometry": author["results"]["test"]["geometry_baseline"],
                                                        "timing": author["timing"]},
               "execution_counts": {"dataset_feature_extractions": 77, "task_probe_feature_extractions": 2,
                                    "geometry_diagnostic_cases": 77, "frozen_correction_previews": 8,
                                    "constructed_cases": 0, "training": 0, "model_inference": 0,
                                    "blender": 0, "formal_performance": 0, "paid_api": 0, "model_consumer": 0},
               "not_run": ["new model training/search", "frozen network inference", "formal CPU timing",
                           "Blender source/consumer/execution", "real-character correction acceptance"],
               "model_shortlist": [], "decision": "No demonstrated learning opportunity within the frozen task. Obtain a real source-bound task before choosing a model."}
    out.mkdir(parents=True, exist_ok=True)
    for name, value in (("DATA_INVENTORY.json", inventory), ("RESULTS.json", results)):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"status": results["status"], "checks": len(checks), "assets": len(assets), "poses": len(cases),
                      "sections": len(rows), "shortlist": [], "output": str(out)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).parent)
    parser.add_argument("--history-root", type=Path, default=Path("D:/hefe/verification/fixes/20261109_architecture_completion"))
    args = parser.parse_args()
    run(args.output.resolve(), args.history_root.resolve())

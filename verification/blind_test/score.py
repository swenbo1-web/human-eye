"""Blind numerical scoring. This module never reads trial condition labels."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from geometry import LIMITS, apply_raw_action, build_meshes, score_pose, self_check, validate_action


def score_trial(case, response, trial_id):
    from human_eye_foveated_renderer import SE3AlignmentMath
    from module_3_2_vlm_grounding_closed_loop_agent import VLMSpatialGroundingAndClosedLoopAgent
    from module_3_3_closed_loop_control_engine import ClosedLoopActionController
    try:
        action = validate_action(response, trial_id)
        rotation, center = apply_raw_action(case, action)
        raw = score_pose(case, rotation, center)
        raw["applied_action"] = {key: action[key] for key in ("rotation_euler_deg_xyz", "translation_xyz_m")}
        raw["final_center_world"] = center.tolist()
        raw["final_rotation_matrix"] = rotation.tolist()
    except (ValueError, TypeError, OverflowError) as exc:
        return {"trial_id": trial_id, "scene_id": case["scene_id"], "valid_action": False,
                "error": str(exc), "raw": {"success": False}, "assisted": {"success": False}}
    # Apply the same optional assistance to every answer, before group labels are
    # revealed. Which result is the primary endpoint is fixed in protocol.json.
    try:
        meshes = build_meshes(case)
        args = {k: action[k] for k in ("focal_mark", "reference_mark", "rotation_euler_deg_xyz", "translation_xyz_m")}
        command = SE3AlignmentMath.euler_xyz_to_matrix(*args["rotation_euler_deg_xyz"])
        quaternion, _ = SE3AlignmentMath.matrix_to_quat_and_euler(command)
        args["rotation_quaternion_wxyz"] = list(quaternion)
        agent = VLMSpatialGroundingAndClosedLoopAgent()
        parsed = agent.parse_vlm_response_to_mcp_tool_call({"tool": "human_eye_apply_se3_closed_loop", "arguments": args})
        fused, audit = agent.fuse_vlm_semantic_intent_with_analytical_se3(parsed, meshes, yaw_symmetry_order=2)
        controller = ClosedLoopActionController(enable_zero_copy_ipc=True)
        aligned, recheck, fsm = controller.apply_se3_prescription_and_recheck(
            focal_mesh=meshes[1], reference_mesh=meshes[0], mcp_arguments=fused["arguments"],
            scene_meshes=meshes, enable_ecbf_shield=True)
        final_rotation = np.asarray(aligned.local_axes).T
        final_center = np.mean(aligned.vertices, axis=0)
        assisted = score_pose(case, final_rotation, final_center)
        assisted.update({"product_reported_passed": bool(recheck.verification_passed),
                         "audit_flags": list(audit.anomaly_flags), "fsm_state": fsm.current_state.value,
                         "fused_arguments": fused["arguments"],
                         "applied_action": {"rotation_euler_deg_xyz": list(recheck.applied_rotation_euler_deg),
                                            "translation_xyz_m": list(recheck.applied_translation_m)},
                         "final_center_world": final_center.tolist(),
                         "final_rotation_matrix": final_rotation.tolist()})
        shield = controller._last_ecbf_report
        assisted["shield_activated"] = bool(shield and (shield.barrier_activated or shield.jamming_shield_activated))
        assisted["action_changed"] = bool(np.max(np.abs(final_rotation-rotation)) > 1e-8
                                          or np.max(np.abs(final_center-center)) > 1e-8)
    except Exception as exc:
        assisted = {"success": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"trial_id": trial_id, "scene_id": case["scene_id"], "valid_action": True,
            "raw": raw, "assisted": assisted}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    run = args.run_dir.resolve()
    self_check()
    protocol = json.loads((run/"protocol.json").read_text(encoding="utf-8"))
    for relative, digest in protocol["frozen_source_sha256"].items():
        if hashlib.sha256((ROOT/relative).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Scoring source changed after protocol freeze: {relative}")
    cases = {case["scene_id"]: case for case in json.loads((run/"private/cases.json").read_text(encoding="utf-8"))}
    index = json.loads((run/"private/evaluation_index.json").read_text(encoding="utf-8"))
    results = []
    missing = []
    for item in index:
        path = run/"responses"/(item["trial_id"]+".json")
        if not path.exists():
            missing.append(item["trial_id"])
            continue
        try:
            response = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            response = {"invalid_response_error": str(exc)}
        row = score_trial(cases[item["scene_id"]], response, item["trial_id"])
        row["response_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        results.append(row)
    if missing and not args.allow_incomplete:
        raise RuntimeError(f"Missing {len(missing)} responses; no final report written")
    output = {"complete": not missing, "missing": missing, "scoring_limits": LIMITS, "results": results}
    target = run/"blind_scores.json"
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"complete": not missing, "scored": len(results), "missing": len(missing), "path": str(target)}))


if __name__ == "__main__":
    main()

"""Run a supplied deterministic adjustment plan in the disposable v1 fixture.

This is real Blender integration with manually supplied actions, not a model
benchmark or double-blind experiment.  The caller must always clean the fixture.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from human_eye_plugin.blender_mcp_host import BlenderMCPHost
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
from human_eye_plugin.task_verification import evaluate_spatial_goal, _goal as _validate_goal


def _load(path):
    def reject(value):
        raise ValueError("Nonfinite JSON: " + value)
    return json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=reject)


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _identified(value, fixture):
    result = copy.deepcopy(value)
    for name in ("focal_id", "reference_id"):
        if name in result and result[name] != fixture[name]:
            raise ValueError("The fixture plan must address the manifest's " + name)
        result[name] = fixture[name]
    return result


def _rotation(degrees):
    x, y, z = [math.radians(value) for value in degrees]
    rx = np.array([[1, 0, 0], [0, math.cos(x), -math.sin(x)], [0, math.sin(x), math.cos(x)]])
    ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    rz = np.array([[math.cos(z), -math.sin(z), 0], [math.sin(z), math.cos(z), 0], [0, 0, 1]])
    return rz @ ry @ rx


def _pair(snapshot, fixture):
    objects = {mesh["object_id"]: mesh for mesh in snapshot["meshes"]}
    return objects[fixture["focal_id"]], objects[fixture["reference_id"]]


def fixture_truth(snapshot, fixture):
    """Direct snapshot arithmetic for this horizontal-box fixture only."""
    focal, reference = _pair(snapshot, fixture)
    vertices, base = np.asarray(focal["vertices"]), np.asarray(reference["vertices"])
    low, high = base.min(axis=0), base.max(axis=0)
    axes = np.asarray(reference["local_axes"])
    horizontal = bool(np.allclose(axes, np.eye(3), atol=1e-7, rtol=0))
    contained = bool(np.all(vertices[:, :2] >= low[:2] - 1e-7)
                     and np.all(vertices[:, :2] <= high[:2] + 1e-7))
    tangent = np.asarray(focal["local_axes"])[0]
    return {"source": "direct_actual_world_vertices_pivot_and_host_axes",
            "independent_of_engine_probes": True,
            "scope": "known_horizontal_base_box_fixture_only",
            "horizontal_base": horizontal, "focal_xy_within_base_footprint": contained,
            "clearance_valid": horizontal and contained,
            "clearance_m": float(vertices[:, 2].min() - high[2]) if horizontal and contained else None,
            "pivot_world_m": focal["pivot_world"],
            "yaw_deg": math.degrees(math.atan2(float(tangent[1]), float(tangent[0])))}


def actual_transform_check(before, after, action, fixture, tolerance=1e-6):
    """Independent Rz Ry Rx arithmetic checks request versus host readback."""
    part_before, _ = _pair(before, fixture)
    part_after, _ = _pair(after, fixture)
    pivot = np.asarray(part_before["pivot_world"])
    delta = np.asarray(action.get("translation", [0, 0, 0]))
    rotation = _rotation(action.get("rotation_euler_deg", [0, 0, 0]))
    expected_vertices = (np.asarray(part_before["vertices"]) - pivot) @ rotation.T + pivot + delta
    expected_axes = np.asarray(part_before["local_axes"]) @ rotation.T
    actual_vertices = np.asarray(part_after["vertices"])
    vertex_error = float(np.max(np.abs(expected_vertices - actual_vertices)))
    axis_error = float(np.max(np.abs(expected_axes - np.asarray(part_after["local_axes"]))))
    pivot_error = float(np.linalg.norm(pivot + delta - np.asarray(part_after["pivot_world"])))
    others_before = [mesh for mesh in before["meshes"] if mesh["object_id"] != fixture["focal_id"]]
    others_after = [mesh for mesh in after["meshes"] if mesh["object_id"] != fixture["focal_id"]]
    passed = vertex_error <= tolerance and axis_error <= tolerance and pivot_error <= tolerance and others_before == others_after
    return {"passed": bool(passed), "source": "independent_rz_ry_rx_and_actual_snapshot_arithmetic",
            "max_world_vertex_error_m": vertex_error, "max_axis_component_error": axis_error,
            "pivot_error_m": pivot_error, "coordinate_tolerance_m": tolerance,
            "nonfocal_objects_unchanged": others_before == others_after}


def expected_truth_check(truth, expected):
    checks = {}
    tolerance = expected.get("position_tolerance_m", 1e-6)
    if "clearance_m" in expected:
        error = abs(truth["clearance_m"] - expected["clearance_m"]) if truth["clearance_valid"] else None
        checks["clearance"] = {"passed": error is not None and error <= tolerance, "absolute_error_m": error}
    if "pivot_world_m" in expected:
        error = math.dist(truth["pivot_world_m"], expected["pivot_world_m"])
        checks["pivot"] = {"passed": error <= tolerance, "absolute_error_m": error}
    if "yaw_deg" in expected:
        error = abs((truth["yaw_deg"] - expected["yaw_deg"] + 180) % 360 - 180)
        checks["yaw"] = {"passed": error <= expected.get("angle_tolerance_deg", 1e-4), "absolute_error_deg": error}
    return {"passed": all(item["passed"] for item in checks.values()) if checks else None, "checks": checks,
            "scope": "explicit_supplied_goal_against_known_fixture_actual_snapshot_arithmetic"}


def _validate_plan(plan, fixture):
    if not isinstance(plan, dict) or not isinstance(plan.get("steps"), list) or not plan["steps"]:
        raise ValueError("Plan requires a nonempty steps list")
    for step in plan["steps"]:
        if (not isinstance(step, dict) or not isinstance(step.get("name"), str)
                or not isinstance(step.get("action"), dict) or not isinstance(step.get("goal"), dict)):
            raise ValueError("Each step needs name, action and goal objects")
        action = _identified(step["action"], fixture)
        allowed = {"focal_id", "reference_id", "translation", "rotation_euler_deg"}
        if set(action) - allowed or not {"translation", "rotation_euler_deg"}.intersection(action):
            raise ValueError("Only explicit rigid transforms are supported")
        for key in ("translation", "rotation_euler_deg"):
            if key in action and (not isinstance(action[key], list) or len(action[key]) != 3
                    or any(type(x) not in (int, float) or not math.isfinite(x) for x in action[key])):
                raise ValueError("Action vectors must contain three finite numbers")
        _validate_goal(_identified(step["goal"], fixture))
        if "expect_task_succeeded" in step and type(step["expect_task_succeeded"]) is not bool:
            raise ValueError("expect_task_succeeded must be boolean")
        expected = step.get("expected_truth", {})
        if not isinstance(expected, dict) or set(expected) - {"clearance_m", "pivot_world_m", "yaw_deg", "position_tolerance_m", "angle_tolerance_deg"}:
            raise ValueError("Unsupported expected_truth fields")
        for key, value in expected.items():
            values = value if key == "pivot_world_m" else [value]
            if (key == "pivot_world_m" and (not isinstance(values, list) or len(values) != 3)
                    or any(type(x) not in (int, float) or not math.isfinite(x) for x in values)):
                raise ValueError("Expected fixture truth must contain finite numeric values")
            if key.endswith("tolerance_m") or key.endswith("tolerance_deg"):
                if value < 0:
                    raise ValueError("Truth tolerances cannot be negative")


def run(output, plan_path, *, host_port=9876):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT) or output == ROOT:
        raise ValueError("Use a dedicated evidence directory within the project")
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "blender_v1_acceptance.json"
    if report_path.exists():
        raise RuntimeError("Acceptance report already exists; use a fresh fixture/run directory")
    report = {"kind": "manual_supplied_plan_real_blender_v1_adjustment_acceptance",
              "model_api_calls": 0, "double_blind": False, "automatic_host_hook_activation_proven": False,
              "execution_scope": "terminal_geometry_only", "steps": [], "tests": [], "passed": False}
    began = time.perf_counter()
    host = None
    def check(name, valid, **facts):
        report["tests"].append({"test": name, "passed": bool(valid), **facts})
        if not valid:
            raise AssertionError(name)
    def save_observation(value, name):
        value = copy.deepcopy(value)
        routing = value.get("routing") or {}
        image = routing.pop("image", None)
        if image:
            png = base64.b64decode(image["data"], validate=True)
            if not png.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("Observation did not contain PNG")
            path = output / (name + ".png")
            path.write_bytes(png)
            value["image_artifact"] = {"path": str(path), "sha256": hashlib.sha256(png).hexdigest()}
        return value
    try:
        fixture = _load(output / "live_fixture.json")
        plan = _load(Path(plan_path))
        _validate_plan(plan, fixture)
        report.update(blender_version=fixture["blender_version"], plan=copy.deepcopy(plan),
                      scene_name=fixture["scene_name"], plan_path=str(Path(plan_path).resolve()),
                      goal_truth_note="Goal evaluator reuses engine geometry; separate horizontal-box arithmetic is independently recorded.")
        state_path, audit_path, config_path = [output / filename for filename in
            ("v1-state.json", "v1-events.jsonl", "v1-connector.json")]
        if any(path.exists() for path in (state_path, audit_path, config_path)):
            raise RuntimeError("V1 runtime files already exist; never reset or reuse a prior state")
        config = {"schema_version": "1.0", "enabled": True, "observe_on_prompt": False,
                  "project_root": str(ROOT), "state_file": str(state_path), "audit_file": str(audit_path),
                  "quad_size": 384, "max_sessions": 4, "readback_atol_m": 1e-6,
                  "blender": {"host": "127.0.0.1", "port": host_port, "timeout_s": 15},
                  "focal_name": fixture["focal_name"], "reference_name": fixture["reference_name"]}
        _write(config_path, config)
        host = BlenderMCPHost(ROOT, port=host_port)
        service = LiveSpatialService(config_path, host=host)
        mcp = LiveSpatialMCPServer(service)
        sid = "manual-v1-" + fixture["scene_name"]
        initial = host.capture_scene()
        _write(output / "before_snapshot.json", initial)
        observed = service.observe(sid, focal_id=fixture["focal_id"], reference_id=fixture["reference_id"])
        report["before_observation"] = save_observation(observed, "before")
        check("actual_far_origin_observation", observed["status"] == "observed")
        check("far_origin_native_png_generated", "image_artifact" in report["before_observation"])
        focal, _ = _pair(initial, fixture)
        obstacle = next(mesh for mesh in initial["meshes"] if mesh["object_id"] == fixture["obstacle_id"])
        truth = fixture_truth(initial, fixture)
        check("initial_horizontal_fixture_truth_valid", truth["clearance_valid"])
        bad_actions = [
            ("fifty_micrometre_penetration", {"translation": [0, 0, -truth["clearance_m"] - .00005]}),
            ("third_object_collision", {"translation": (np.asarray(obstacle["pivot_world"]) - np.asarray(focal["pivot_world"])).tolist()}),
        ]
        for label, raw in bad_actions:
            action = _identified(raw, fixture)
            before = host.capture_scene()
            preview = service.preview_action(sid, action)
            rejected = service.transform(sid, action)
            after = host.capture_scene()
            report.setdefault("guard_checks", []).append({"name": label, "original_action": raw,
                "resolved_action": action, "preview": save_observation(preview, label + "_preview"),
                "execution": save_observation(rejected, label + "_execution"),
                "before_revision": before["revision"], "after_revision": after["revision"]})
            check(label + "_preview_denied", preview.get("allow_action") is False)
            check(label + "_inner_gate_denied", rejected.get("status") == "blocked"
                  and rejected.get("executed") is False and rejected.get("verified") is False
                  and "candidate_collision" in (rejected.get("routing") or {}).get("reason_codes", []))
            check(label + "_host_unchanged", before == after)
        no_op_before = host.capture_scene()
        noop = service.transform(sid, _identified({"translation": [0, 0, 0]}, fixture))
        report["noop"] = save_observation(noop, "noop")
        check("noop_no_host_mutation", noop["status"] == "no_op" and host.capture_scene() == no_op_before)
        for index, step in enumerate(plan["steps"], 1):
            started = time.perf_counter()
            action = _identified(step["action"], fixture)
            goal = _identified(step["goal"], fixture)
            before = host.capture_scene()
            item = {"name": step["name"], "original_action": copy.deepcopy(step["action"]),
                    "resolved_action": action, "goal": goal, "before_revision": before["revision"]}
            report["steps"].append(item)
            item["goal_before"] = evaluate_spatial_goal(before, goal)
            item["preview"] = save_observation(service.preview_action(sid, action), f"step_{index:02d}_preview")
            check(f"step_{index}_preview_allowed", item["preview"].get("allow_action") is True)
            item["execution"] = save_observation(service.transform(sid, action, goal=goal), f"step_{index:02d}_execution")
            after = host.capture_scene()
            item["elapsed_ms"] = (time.perf_counter() - started) * 1000
            item["after_revision"] = after["revision"]
            item["action_verified"] = item["execution"].get("verified") is True
            item["independent_transform_check"] = actual_transform_check(before, after, action, fixture)
            item["goal_after"] = evaluate_spatial_goal(after, goal)
            item["task_succeeded"] = item["goal_after"]["task_succeeded"]
            item["independent_fixture_truth"] = fixture_truth(after, fixture)
            item["independent_goal_check"] = expected_truth_check(item["independent_fixture_truth"], step.get("expected_truth", {}))
            _write(output / f"step_{index:02d}_snapshot.json", after)
            check(f"step_{index}_action_verified", item["action_verified"])
            check(f"step_{index}_actual_request_readback", item["independent_transform_check"]["passed"])
            check(f"step_{index}_goal_outcome", item["task_succeeded"] is step.get("expect_task_succeeded", True))
            check(f"step_{index}_service_goal_matches_actual_readback",
                  item['execution'].get('task_succeeded') is item['task_succeeded']
                  and item['execution']['goal_verification']['scene_revision'] == after['revision'])
            if item["independent_goal_check"]["passed"] is not None:
                check(f"step_{index}_independent_goal_truth", item["independent_goal_check"]["passed"])
        final = host.capture_scene()
        request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {
            'name': 'human_eye_scene_observe', 'arguments': {'session_id': sid,
                'focal_id': fixture['focal_id'], 'reference_id': fixture['reference_id'],
                'goal': plan['steps'][-1]['goal']}}}
        response = mcp.handle_jsonrpc_message(json.loads(json.dumps(request)))
        tool_result = response['result']
        wire_metadata = json.loads(next(part['text'] for part in tool_result['content'] if part['type'] == 'text'))
        report['mcp_goal_observation'] = {'scope': 'in_process_jsonrpc_handler_with_real_blender_backend',
            'metadata': wire_metadata, 'native_png_content_block': any(part['type'] == 'image' for part in tool_result['content'])}
        check('mcp_goal_observation_actual_scene', not tool_result['isError']
              and wire_metadata.get('task_succeeded') is plan['steps'][-1].get('expect_task_succeeded', True)
              and wire_metadata['goal_verification']['scene_revision'] == final['revision'])
        _write(output / "after_snapshot.json", final)
        report["after_observation"] = save_observation(service.observe(sid, focal_id=fixture["focal_id"],
            reference_id=fixture["reference_id"]), "after")
        status = service.status()
        report["final_service_status"] = status
        check("no_inflight_or_quarantine", not status["inflight_operation"] and not status["quarantined"])
        report["passed"] = all(item["passed"] for item in report["tests"])
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        if host is not None:
            host.close()
        report["elapsed_ms"] = (time.perf_counter() - began) * 1000
        report["test_count"] = len(report["tests"])
        report["cleanup_required_by_caller"] = True
        _write(report_path, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--port", type=int, default=9876)
    parser.add_argument("--validate-only", action="store_true", help="Read plan/fixture only; do not contact Blender or create runtime files")
    args = parser.parse_args(argv)
    if args.validate_only:
        _validate_plan(_load(args.plan), _load(args.output_dir / "live_fixture.json"))
        print(json.dumps({"plan_valid": True, "blender_contacted": False}))
        return 0
    report = run(args.output_dir, args.plan, host_port=args.port)
    print(json.dumps({"passed": report["passed"], "tests": report["test_count"],
                      "report": str(args.output_dir / "blender_v1_acceptance.json")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

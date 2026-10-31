"""Independent release acceptance fixtures; never connect to a user's Blender.

Historical box scoring is reused unchanged.  The mutable host below applies
explicit matrices and returns its actual state; it does not trust engine receipts.
This is an in-memory integration check, not independent real-host certification.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "verification/blind_test") not in sys.path:
    sys.path.insert(0, str(ROOT / "verification/blind_test"))
from geometry import apply_raw_action, build_meshes, euler_matrix, obb_intersection, score_pose, vertices


TRUST_ANCHORS = {
    "verification/blind_test/runs/20261021_02_vision_only/protocol.json":
        "c5dbe9a370a956d92994bc4394316c28174981ba9d499438c93cc3b856e9fc53",
    "verification/blind_test/runs/20261021_01/final_manifest.json":
        "b5072aabbefdb955edabf304d0004dca94b5f7c2dae9d3b21ef6f7c17f3b1966",
    "verification/fixes/20261021_optimized_merge/replay_results.json":
        "2da84c3e54f646f01c1d5f17b3beca03fa27376bb45f7ca37d79ed063b7fe777",
    "verification/fixes/20261023_cloud_package/build_result.json":
        "dbeb2250ce305ee1f751baab7c2b56269392f0566bdb3b48d7b9d718b66b0be0",
}
REPAIR_SCENES = {"S006", "S010", "S021", "S022", "S024", "S025"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_file(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def checked_inventory(root, inventory):
    root = Path(root).resolve()
    problems = []
    for relative, digest in inventory.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            problems.append({"path": relative, "reason": "outside_root"})
        elif not path.is_file():
            problems.append({"path": relative, "reason": "missing"})
        elif sha(path) != digest:
            problems.append({"path": relative, "reason": "sha256_mismatch"})
    return {"passed": not problems, "files": len(inventory), "problems": problems}


def preservation_checks(root=ROOT):
    root = Path(root)
    anchors = checked_inventory(root, TRUST_ANCHORS)
    if not anchors["passed"]:
        return {"passed": False, "trust_anchors": anchors}
    protocol = json_file(root / next(iter(TRUST_ANCHORS)))
    original = root / "verification/blind_test/runs/20261021_01"
    historical = json_file(original / "final_manifest.json")["file_sha256"]
    build = json_file(root / "verification/fixes/20261023_cloud_package/build_result.json")
    # Relative filename avoids assuming the publisher's Windows staging path.
    uploaded = {"dist/" + build["file"]: build["sha256"]}
    result = {"trust_anchors": anchors,
              "frozen_source": checked_inventory(root, protocol["frozen_source_sha256"]),
              "historical_inputs": checked_inventory(original, historical),
              "uploaded_release": checked_inventory(root, uploaded)}
    result["passed"] = all(value["passed"] for value in result.values())
    return result


def source_manifest(root=ROOT):
    root = Path(root)
    paths = set(root.glob("*.py"))
    for folder in ("human_eye_plugin", "human_eye_module1_operators", "examples/agents"):
        paths.update((root / folder).glob("*.py"))
    paths.update(root / value for value in (
        "pyproject.toml", "human_eye_plugin/plugin.json", "human_eye_plugin/mcp_config.json",
        "verification/run_release_gate.py", "verification/release_gate_helpers.py",
        "verification/test_release_gate.py", "verification/replay_alignment_fix.py"))
    inventory = {path.relative_to(root).as_posix(): sha(path) for path in sorted(paths) if path.is_file()}
    digest = hashlib.sha256(json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"revision_kind": "sha256_source_inventory", "build_id": "sha256:" + digest,
            "source_sha256": inventory}


def analytical_case():
    return {"scene_id": "release_gate_analytic_box",
            "reference": {"center": [0, 0, .1], "rotation": np.eye(3).tolist(), "size": [1.4, 1.2, .2]},
            "focal": {"center": [0, 0, .35], "rotation": np.eye(3).tolist(), "size": [.28, .20, .1]},
            "target": {"plane_point": [0, 0, .2], "normal": [0, 0, 1],
                       "rotation": np.eye(3).tolist(), "center": [0, 0, .25]}, "occluders": []}


class AnalyticalMemoryHost:
    """Strict mutable host double.  No networking and no Blender imports."""
    def __init__(self, case, *, supported=True, corrupt_readback=False, missing_capability=False):
        self.case = copy.deepcopy(case)
        self.scene = {"revision": "memory-r0", "unit": "m", "coordinate_frame": "world",
                      "source": "release_gate_in_memory_analytical_boxes",
                      "meshes": [mesh.to_dict() for mesh in build_meshes(case)],
                      "host_execution": {"schema_version": "1.0", "operation": "rigid_transform",
                          "supported": supported, "scope": "independent_static_rigid_meshes",
                          "reasons": [] if supported else [{"object_id": "part_0",
                              "object_name": "Part_A", "reason": "unsupported_test_capability"}]}}
        if missing_capability:
            self.scene.pop("host_execution")
        self.calls = 0
        self.captures = 0
        self._depth = 0
        self.corrupt_readback = corrupt_readback

    @contextmanager
    def transaction(self):
        self._depth += 1
        try:
            yield
        finally:
            self._depth -= 1

    def capture_scene(self):
        self.captures += 1
        return copy.deepcopy(self.scene)

    def apply_transform(self, action, expected_revision, expected_fingerprint=None):
        from human_eye_plugin.auto_router import _validated_scene
        if not self._depth:
            raise RuntimeError("Mutation must be inside host transaction")
        if self.scene.get("host_execution", {}).get("supported") is not True:
            raise RuntimeError("Host execution capability is unavailable")
        if expected_revision != self.scene["revision"]:
            raise RuntimeError("Revision conflict")
        if expected_fingerprint != _validated_scene(self.scene)[2]:
            raise RuntimeError("Fingerprint conflict")
        focal = next(mesh for mesh in self.scene["meshes"] if mesh["object_id"] == action["focal_id"])
        rotation = euler_matrix(action.get("rotation_euler_deg", [0, 0, 0]))
        pivot = np.asarray(focal["pivot_world"], dtype=float)
        translation = np.asarray(action.get("translation", [0, 0, 0]), dtype=float)
        focal["vertices"] = ((np.asarray(focal["vertices"]) - pivot) @ rotation.T + pivot + translation).tolist()
        focal["local_axes"] = (np.asarray(focal["local_axes"]) @ rotation.T).tolist()
        focal["pivot_world"] = (pivot + translation).tolist()
        self.calls += 1
        self.scene["revision"] = "memory-r" + str(self.calls)
        if self.corrupt_readback:
            focal["vertices"][0][0] += .001
        return {"scene": self.capture_scene(), "receipt": {"source": "in_memory_host_double"}}

    def independent_score(self):
        focal = next(mesh for mesh in self.scene["meshes"] if mesh["object_id"] == "part_1")
        rotation, center = np.asarray(focal["local_axes"]).T, np.asarray(focal["pivot_world"])
        result = score_pose(self.case, rotation, center)
        reconstructed = vertices({"rotation": rotation, "center": center,
                                  "size": self.case["focal"]["size"]})
        error = float(np.max(np.abs(np.asarray(focal["vertices"]) - reconstructed)))
        result["actual_vertices_consistent_with_box_pose"] = error <= 1e-10
        result["actual_vertex_residual_m"] = error
        result["success"] = result["success"] and error <= 1e-10
        return result


def goal_for(case):
    # This is a stricter point goal; region membership is independently scored
    # by the frozen box scorer, not claimed as a native production region field.
    return {"target_clearance_m": 0., "clearance_tolerance_m": .0005,
            "target_focal_pivot_world_m": case["target"]["center"], "position_tolerance_m": .005,
            "max_contact_normal_angle_deg": 1., "max_tangent_yaw_mismatch_deg": 1.,
            "yaw_symmetry_order": 2}


def strict_candidate_penetrates(case, legacy_action):
    """Independent OBB SAT at the production threshold, not legacy tolerance."""
    rotation, center = apply_raw_action(case, legacy_action)
    pose = {"rotation": rotation, "center": center, "size": case["focal"]["size"]}
    return any(obb_intersection(pose, other, tolerance=1e-9)[0]
               for other in [case["reference"], *case.get("occluders", [])])


def analytical_exact_target_action(case):
    """Full-precision fixture answer, explicitly not a model/controller answer."""
    rotation = np.asarray(case["target"]["rotation"]) @ np.asarray(case["focal"]["rotation"]).T
    pitch = math.asin(float(np.clip(-rotation[2, 0], -1, 1)))
    if abs(math.cos(pitch)) > 1e-10:
        roll = math.atan2(rotation[2, 1], rotation[2, 2])
        yaw = math.atan2(rotation[1, 0], rotation[0, 0])
    else:
        roll = 0.
        yaw = math.atan2(-rotation[0, 1], rotation[1, 1])
    euler = [math.degrees(value) for value in (roll, pitch, yaw)]
    if not np.allclose(euler_matrix(euler), rotation, atol=1e-12, rtol=0):
        raise ValueError("Analytical fixture Euler extraction failed")
    return {"focal_id": "part_1", "reference_id": "part_0", "rotation_euler_deg": euler,
            "translation": (np.asarray(case["target"]["center"]) - case["focal"]["center"]).tolist()}


def make_service(folder, host):
    from human_eye_plugin.live_service import LiveSpatialService
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    config = folder / "connector.json"
    config.write_text(json.dumps({"schema_version": "1.0", "project_root": str(ROOT),
        "state_file": "state.json", "audit_file": "audit.jsonl", "quad_size": 64}), encoding="utf-8")
    return LiveSpatialService(config, host=host, production_mode=True)


def mcp_transform(service, action, goal):
    from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
    result = LiveSpatialMCPServer(service, default_session_id="release-gate").handle_jsonrpc_message({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "human_eye_transform", "arguments": {"action": action, "goal": goal}}})
    if "error" in result:
        raise RuntimeError("MCP request failed: " + str(result["error"]))
    blocks = result["result"]["content"]
    text = next(block["text"] for block in blocks if block["type"] == "text")
    return json.loads(text)


def evaluate_case(folder, case, action, *, entry, expected_task, expected_execution=True,
                  supported=True, corrupt_readback=False, missing_capability=False):
    from human_eye_plugin.host_runtime import GuardedHostRuntime
    host = AnalyticalMemoryHost(case, supported=supported, corrupt_readback=corrupt_readback,
                                missing_capability=missing_capability)
    goal = goal_for(case)
    if entry == "guarded_runtime":
        runtime = GuardedHostRuntime(host, quad_size=64, require_execution_capability=True)
        runtime.before_model(session_id="release-gate", task_instruction="Release acceptance fixture",
            focal_id="part_1", reference_id="part_0", include_image=False, messages=[])
        result = runtime.execute_action(session_id="release-gate", action=action, goal=goal)
        quarantined = runtime.status["quarantined"]
    else:
        service = make_service(folder, host)
        result = (mcp_transform(service, action, goal) if entry == "live_mcp"
                  else service.transform("release-gate", action, goal=goal))
        quarantined = service.status()["quarantined"]
    actual = host.independent_score()
    execution = result.get("execution_verified") is True
    # A blocked action leaves the initial pose unchanged and is expected to fail
    # its target.  Merely reporting a failed optional goal must not imply failure
    # to execute an otherwise valid transform.
    engine_task = result.get("task_succeeded") is True
    passed = execution == expected_execution and actual["success"] == expected_task
    if expected_execution:
        passed = passed and engine_task == expected_task and host.calls == 1
    else:
        passed = passed and host.calls == (1 if corrupt_readback else 0)
        passed = passed and result.get("status") == ("host_readback_rejected" if corrupt_readback else "blocked")
        passed = passed and quarantined is corrupt_readback and not engine_task
    return {"passed": bool(passed), "entry": entry,
            "host_kind": "in_memory_analytical_boxes_not_real_blender",
            "model_original_action": None, "engine_recommendation": None,
            "requested_action": copy.deepcopy(action),
            "actual_pose": {"pivot_world_m": host.scene["meshes"][1]["pivot_world"],
                            "local_axes": host.scene["meshes"][1]["local_axes"]},
            "execution_consistency": execution, "engine_task_succeeded": result.get("task_succeeded"),
            "independent_joint_task": actual, "expected_task": expected_task,
            "expected_execution": expected_execution, "mutations": host.calls,
            "capture_count": host.captures, "status": result.get("status"),
            "host_quarantined": quarantined,
            "goal_evaluation": result.get("goal_evaluation"), "result": result}

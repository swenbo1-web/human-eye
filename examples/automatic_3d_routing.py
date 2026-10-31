"""Run real engine routing and five message formats with an explicit model stub.

No model API, host application, credentials, or benchmark is involved. The
scene mutation below is an in-memory host simulation, not Blender execution.
Run from the project checkout: python examples/automatic_3d_routing.py
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PIL import Image

from human_eye_module1_operators import MeshEntity3D, SE3AlignmentMath
from human_eye_plugin.agent_adapters import AgentRuntimeAdapter, SUPPORTED_FORMATS
from human_eye_plugin.auto_router import HumanEyeAutoRouter


TASK = "Inspect the part/base clearance, then consider moving part +0.05 m along world Z."
_SIGNS = np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
                   [-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]], dtype=float)
_FACES = np.array([[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
                   [2,3,7],[2,7,6],[1,2,6],[1,6,5],[3,0,4],[3,4,7]])


def _box(object_id, center, size, focal=False):
    return MeshEntity3D(
        object_id, "#" + object_id, object_id,
        _SIGNS * np.asarray(size) / 2 + np.asarray(center), _FACES.copy(),
        None, (70, 140, 210), focal, local_axes=np.eye(3),
    )


def make_scene():
    """An explicit, known world-space fixture; no engine demo-scene fallback."""
    return {"revision": "r1", "unit": "m", "coordinate_frame": "world",
            "source": "example_in_memory_host_simulation", "meshes": [
                _box("base", [0, 0, .1], [1.4, 1.2, .2]).to_dict(),
                _box("part", [0, 0, .35], [.3, .2, .1], True).to_dict(),
            ]}


def _original_messages(format):
    if format == "gemini":
        return [{"role": "user", "parts": [{"text": TASK}]}]
    return [{"role": "user", "content": TASK}]


def _extract_delivered_png(messages, format):
    blocks = messages[-1]["parts" if format == "gemini" else "content"]
    if format == "openai_responses":
        encoded = blocks[1]["image_url"].split(",", 1)[1]
    elif format == "openai_chat":
        encoded = blocks[1]["image_url"]["url"].split(",", 1)[1]
    elif format == "anthropic":
        encoded = blocks[1]["source"]["data"]
    elif format == "gemini":
        encoded = blocks[1]["inline_data"]["data"]
    else:
        encoded = blocks[1]["data"]
    raw = base64.b64decode(encoded, validate=True)
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
        if image.format != "PNG":
            raise AssertionError("Expected a real PNG observation")
        size = list(image.size)
    return raw, size


class StubModel:
    """A deterministic callback fixture, not a model or perception evaluation."""

    def __init__(self, format):
        self.format, self.calls = format, 0

    def __call__(self, messages):
        self.calls += 1
        if messages[:-1] != _original_messages(self.format):
            raise AssertionError("The original task changed")
        _extract_delivered_png(messages, self.format)
        # A fixed selected action only exercises the host gate/readback wiring.
        # The callback does not infer an answer or optimize the action.
        return {"kind": "stub_selected_action", "action": {
            "focal_id": "part", "reference_id": "base",
            "translation": [0, 0, .05], "rotation_euler_deg": [0, 0, 0],
        }}


def _simulate_host_action(scene, action, gate):
    """Mutate a copied scene and return an independent versioned readback."""
    if gate["allow_action"] is not True:
        raise RuntimeError("The simulated executor refused a blocked action")
    # The simulation is synchronous with no other writer. A real host needs an
    # atomic revision/fingerprint comparison at its actual execution boundary.
    if scene["revision"] != gate["scene_revision"]:
        raise RuntimeError("The simulated scene changed after checking")
    changed = copy.deepcopy(scene)
    for index, item in enumerate(changed["meshes"]):
        if item["object_id"] == action["focal_id"]:
            mesh = MeshEntity3D.from_dict(item)
            rotation = SE3AlignmentMath.euler_xyz_to_matrix(*action["rotation_euler_deg"])
            changed["meshes"][index] = mesh.rotated_around_pivot(rotation).translated(
                action["translation"]).to_dict()
            break
    else:
        raise RuntimeError("Missing selected object")
    changed["revision"] = "r2"
    return changed


def run_example(format, quad_size=64):
    router = HumanEyeAutoRouter(quad_size=quad_size)
    adapter = AgentRuntimeAdapter(router, format=format, supports_images=True)
    scene = make_scene()
    original_messages = _original_messages(format)
    input_copy = copy.deepcopy(original_messages)
    event = {"event": "before_model", "session_id": "example-" + format,
             "task_kind": "spatial_3d", "task_instruction": TASK,
             "focal_id": "part", "reference_id": "base", "scene": scene}
    prepared = adapter.before_model(event, original_messages)
    if prepared["routing"]["route"] != "engine":
        raise RuntimeError("Automatic observation failed: " + str(prepared["routing"]["reason_codes"]))
    raw_png, png_size = _extract_delivered_png(prepared["messages"], format)

    # The host owns its model function. Exactly one explicit stub call follows
    # automatic observation; no model decision to call a viewing tool is needed.
    stub = StubModel(format)
    selected = stub(prepared["messages"])
    gate = router.handle_event({
        "event": "before_action", "session_id": event["session_id"],
        "observation_id": prepared["routing"]["observation_id"],
        "focal_id": "part", "reference_id": "base", "action": selected["action"],
        "scene": scene,
    })
    readback_scene = _simulate_host_action(scene, selected["action"], gate)
    readback = router.handle_event({
        "event": "after_action", "session_id": event["session_id"],
        "focal_id": "part", "reference_id": "base", "scene": readback_scene,
        "task_instruction": TASK,
    })
    if readback["route"] != "engine":
        raise RuntimeError("Simulated host readback failed: " + str(readback["reason_codes"]))
    return {
        "format": format, "route": prepared["routing"]["route"],
        "delivery": prepared["delivery"], "png_size": png_size,
        "png_sha256": hashlib.sha256(raw_png).hexdigest(),
        "task_sha256": hashlib.sha256(TASK.encode()).hexdigest(),
        "scene_fingerprint": prepared["routing"]["scene_fingerprint"],
        "original_task_preserved": prepared["messages"][:-1] == input_copy,
        "original_input_unchanged": original_messages == input_copy,
        "model_callback_kind": "deterministic_stub", "model_callback_calls": stub.calls,
        "live_model_called": False, "host_execution_kind": "in_memory_simulation",
        "action_allowed": gate["allow_action"], "action_scope": gate["execution_scope"],
        "readback_route": readback["route"], "readback_revision": readback["scene_revision"],
        "readback_clearance_m": json.loads(readback["context_text"])["measurement"]["signed_clearance_m"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="Optionally save the local wiring report as JSON")
    parser.add_argument("--quad-size", type=int, default=64)
    args = parser.parse_args()
    results = [run_example(format, args.quad_size) for format in SUPPORTED_FORMATS]
    summary = {
        "kind": "local_protocol_and_in_memory_simulation",
        "live_model_calls": 0, "task": TASK,
        "same_task_all_formats": len({r["task_sha256"] for r in results}) == 1,
        "same_scene_all_formats": len({r["scene_fingerprint"] for r in results}) == 1,
        "same_png_all_formats": len({r["png_sha256"] for r in results}) == 1,
        "results": results,
    }
    for result in results:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    print(json.dumps({key: value for key, value in summary.items() if key != "results"},
                     ensure_ascii=False, separators=(",", ":")))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

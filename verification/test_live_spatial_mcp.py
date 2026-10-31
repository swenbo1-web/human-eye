"""Contract checks for the live MCP transport; no Blender or model calls."""
from __future__ import annotations

import base64
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

from human_eye_plugin.live_spatial_mcp import (
    LIVE_MCP_TOOLS_SCHEMA, LiveSpatialMCPServer, handle_jsonrpc_message,
    run_stdio_mcp_server,
)


def png_content():
    buffer = io.BytesIO()
    Image.new("RGB", (2, 3), (20, 100, 200)).save(buffer, format="PNG")
    return {"type": "image", "mimeType": "image/png",
            "data": base64.b64encode(buffer.getvalue()).decode("ascii")}


class FakeService:
    def __init__(self):
        self.calls = []
        self.observation = {
            "status": "observed", "session_id": "session",
            "objects": [{"object_id": "moving"}, {"object_id": "fixed"}],
            "routing": {"route": "engine", "observation_id": "obs-1", "image": png_content(),
                        "context_text": "gap=0.100m", "execution_scope": "endpoint_geometry"},
        }
        self.transformation = {"status": "verified", "executed": True, "verified": True,
                               "routing": {"route": "engine", "image": png_content()}}

    def observe(self, session_id, **kwargs):
        self.calls.append(("observe", session_id, kwargs))
        return self.observation

    def transform(self, session_id, action):
        self.calls.append(("transform", session_id, action))
        return self.transformation

    def status(self):
        self.calls.append(("status",))
        return {"status": "configured", "transport": "blender_tcp"}


class LiveSpatialMCPTests(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()
        self.server = LiveSpatialMCPServer(self.service)

    def request(self, method, params=None, request_id=1):
        req = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            req["params"] = params
        return self.server.handle_jsonrpc_message(req)

    def call(self, name, arguments=None):
        params = {"name": name}
        if arguments is not None:
            params["arguments"] = arguments
        return self.request("tools/call", params)["result"]

    @staticmethod
    def action():
        return {"focal_id": "moving", "reference_id": "fixed", "translation": [0.05, 0, 0]}

    def test_initialize_is_read_only_and_matches_supported_protocol(self):
        response = self.request("initialize", {"protocolVersion": "2025-03-26"})
        self.assertEqual(response["result"]["protocolVersion"], "2025-03-26")
        self.assertEqual(response["result"]["serverInfo"]["name"], "human-eye-live-spatial")
        self.assertEqual(self.service.calls, [])

    def test_tool_list_preserves_three_tools_and_adds_bounded_goal(self):
        tools = self.request("tools/list")["result"]["tools"]
        self.assertEqual([tool["name"] for tool in tools], [
            "human_eye_scene_observe", "human_eye_transform", "human_eye_connection_status",
            "human_eye_clearance_segment"])
        for tool in tools:
            self.assertFalse(tool["inputSchema"]["additionalProperties"])
        action = tools[1]["inputSchema"]["properties"]["action"]
        self.assertFalse(action["additionalProperties"])
        self.assertEqual(action["required"], ["focal_id", "reference_id"])
        self.assertEqual(len(action["anyOf"]), 2)
        tools[0]["name"] = "mutated"
        self.assertEqual(LIVE_MCP_TOOLS_SCHEMA[0]["name"], "human_eye_scene_observe")
        self.assertEqual(self.service.calls, [])

    def test_legacy_six_tools_unchanged(self):
        from human_eye_plugin.llm_tool_schemas import MCP_TOOLS_SCHEMA
        self.assertEqual(len(MCP_TOOLS_SCHEMA), 6)
        self.assertTrue(set(tool["name"] for tool in MCP_TOOLS_SCHEMA).isdisjoint(
            tool["name"] for tool in LIVE_MCP_TOOLS_SCHEMA))

    def test_observe_delivers_native_png_without_duplicate_base64(self):
        snapshot = copy.deepcopy(self.service.observation)
        result = self.call("human_eye_scene_observe", {"task_instruction": "Measure 三维间隙"})
        self.assertFalse(result["isError"])
        text, picture = result["content"]
        self.assertEqual(text["type"], "text")
        self.assertEqual(picture["type"], "image")
        self.assertEqual(picture["mimeType"], "image/png")
        self.assertNotIn(picture["data"], text["text"])
        self.assertNotIn("image", json.loads(text["text"])["routing"])
        with Image.open(io.BytesIO(base64.b64decode(picture["data"]))) as opened:
            self.assertEqual(opened.size, (2, 3))
        self.assertEqual(self.service.observation, snapshot)

    def test_process_default_session_is_stable_across_observe_and_transform(self):
        self.call("human_eye_scene_observe")
        self.call("human_eye_transform", {"action": self.action()})
        sessions = [call[1] for call in self.service.calls]
        self.assertTrue(sessions[0].startswith("mcp-"))
        self.assertEqual(sessions[0], sessions[1])

    def test_explicit_session_and_object_pair_are_preserved(self):
        args = {"session_id": "a-session", "focal_id": "moving", "reference_id": "fixed"}
        self.call("human_eye_scene_observe", args)
        self.assertEqual(self.service.calls[0], ("observe", "a-session", {
            "task_instruction": "", "focal_id": "moving", "reference_id": "fixed"}))

    def test_separate_process_instances_use_different_sessions(self):
        other = LiveSpatialMCPServer(self.service)
        self.assertNotEqual(self.server.default_session_id, other.default_session_id)

    def test_caller_can_supply_a_stable_session_default(self):
        server = LiveSpatialMCPServer(self.service, default_session_id="trusted-host")
        server.handle_jsonrpc_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                      "params": {"name": "human_eye_scene_observe"}})
        self.assertEqual(self.service.calls[0][1], "trusted-host")

    def test_invalid_explicit_default_session_is_rejected(self):
        for value in ("", "  ", 0, False):
            with self.subTest(value=value), self.assertRaises(ValueError):
                LiveSpatialMCPServer(self.service, default_session_id=value)

    def test_transform_requires_successful_verification(self):
        for status in ("blocked", "observation_required", "executed", "unverified", "error"):
            with self.subTest(status=status):
                self.service.transformation["status"] = status
                self.assertTrue(self.call("human_eye_transform", {"action": self.action()})["isError"])
        for status in ("verified", "no_op"):
            with self.subTest(status=status):
                self.service.transformation["status"] = status
                self.assertFalse(self.call("human_eye_transform", {"action": self.action()})["isError"])

    def test_overview_is_usable_but_blocked_observation_is_error(self):
        self.service.observation.update(status="overview", routing=None)
        result = self.call("human_eye_scene_observe")
        self.assertFalse(result["isError"])
        self.assertEqual(len(result["content"]), 1)
        self.service.observation["status"] = "blocked"
        self.assertTrue(self.call("human_eye_scene_observe")["isError"])

    def test_status_only_calls_status(self):
        result = self.call("human_eye_connection_status")
        self.assertFalse(result["isError"])
        self.assertEqual(self.service.calls, [("status",)])

    def test_arbitrary_arguments_and_code_are_rejected_before_service(self):
        invalid = [
            ("human_eye_connection_status", {"execute": True}),
            ("human_eye_scene_observe", {"code": "bpy.ops.wm.quit_blender()"}),
            ("human_eye_scene_observe", {"session_id": "  "}),
            ("human_eye_scene_observe", {"task_instruction": ["invalid"]}),
            ("human_eye_transform", {"action": dict(self.action(), code="arbitrary")}),
            ("human_eye_transform", {"action": self.action(), "allow_all": True}),
            ("human_eye_transform", {}),
            ("human_eye_transform", {"action": {"translation": [0, 0, 0]}}),
            ("human_eye_transform", {"action": {"focal_id": "a", "reference_id": "b"}}),
            ("human_eye_transform", {"action": dict(self.action(), focal_id="fixed")}),
            ("unknown_tool", {}),
        ]
        for name, args in invalid:
            with self.subTest(name=name, args=args):
                self.assertTrue(self.call(name, args)["isError"])
        self.assertEqual(self.service.calls, [])

    def test_nonfinite_boolean_or_nonvector_transforms_are_rejected(self):
        for vector in ([True, 0, 0], [float("nan"), 0, 0], [float("inf"), 0, 0],
                       ["0", 0, 0], [0, 0], {"x": 0}, None):
            with self.subTest(vector=vector):
                action = dict(self.action(), translation=vector)
                self.assertTrue(self.call("human_eye_transform", {"action": action})["isError"])
        self.assertEqual(self.service.calls, [])

    def test_rotation_only_is_valid_and_input_request_is_unchanged(self):
        action = {"focal_id": "moving", "reference_id": "fixed", "rotation_euler_deg": [0, 0, 90]}
        args = {"session_id": "session", "action": action}
        saved = copy.deepcopy(args)
        self.assertFalse(self.call("human_eye_transform", args)["isError"])
        self.assertEqual(args, saved)
        self.service.calls[0][2]["rotation_euler_deg"][0] = 100
        self.assertEqual(args, saved)

    def test_bad_image_content_is_an_error(self):
        for value in ({"type": "image", "mimeType": "image/png", "data": "!!!"},
                      {"type": "image", "mimeType": "image/png", "data": "bm90LXBuZw=="},
                      {"type": "image", "mimeType": "image/jpeg", "data": "abc"}):
            with self.subTest(value=value):
                self.service.observation["routing"]["image"] = value
                result = self.call("human_eye_scene_observe")
                self.assertTrue(result["isError"])
                self.assertEqual(len(result["content"]), 1)

    def test_service_exception_remains_a_tool_error(self):
        def fail(*args, **kwargs):
            raise RuntimeError("Connection unavailable")
        self.service.observe = fail
        result = self.call("human_eye_scene_observe")
        self.assertTrue(result["isError"])
        self.assertIn("Connection unavailable", result["content"][0]["text"])

    def test_notifications_do_not_run_actions_or_receive_responses(self):
        for method, params in (("notifications/initialized", {}), ("notifications/cancelled", {}),
                               ("tools/call", {"name": "human_eye_transform", "arguments": {"action": self.action()}})):
            self.assertIsNone(self.server.handle_jsonrpc_message({"jsonrpc": "2.0", "method": method, "params": params}))
        self.assertEqual(self.service.calls, [])

    def test_invalid_requests_and_params_have_protocol_errors(self):
        for value in ([], None, "bad", {}, {"jsonrpc": "2.0", "method": "ping", "id": True},
                      {"jsonrpc": "1.0", "method": "ping", "id": 1}):
            with self.subTest(value=value):
                self.assertEqual(self.server.handle_jsonrpc_message(value)["error"]["code"], -32600)
        response = self.request("tools/call", ["bad"])
        self.assertEqual(response["error"]["code"], -32602)
        response = self.request("tools/call", {})
        self.assertEqual(response["error"]["code"], -32602)
        response = self.request("unknown_method")
        self.assertEqual(response["error"]["code"], -32601)
        self.assertEqual(self.request("ping")["result"], {})

    def test_function_handler_requires_a_service_and_supports_existing_server(self):
        with self.assertRaises(ValueError):
            handle_jsonrpc_message({"jsonrpc": "2.0", "method": "ping", "id": 1})
        result = handle_jsonrpc_message({"jsonrpc": "2.0", "method": "ping", "id": "id"}, server=self.server)
        self.assertEqual(result["id"], "id")

    def test_stdio_recovers_after_invalid_input_and_only_writes_json(self):
        source = io.StringIO("\n{broken\n[1,2]\n"
                             '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
                             '{"jsonrpc":"2.0","id":2,"method":"ping"}\n'
                             '{"jsonrpc":"2.0","id":3,"method":"ping","params":{"bad":NaN}}\n')
        output = io.StringIO()
        run_stdio_mcp_server(self.service, source, output)
        lines = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(lines), 4)
        self.assertEqual([lines[0]["error"]["code"], lines[1]["error"]["code"]], [-32700, -32600])
        self.assertEqual(lines[2], {"jsonrpc": "2.0", "id": 2, "result": {}})
        self.assertEqual(lines[3]["error"]["code"], -32700)
        self.assertEqual(self.service.calls, [])

    def test_source_entry_runs_help_from_external_working_directory(self):
        entry = Path(__file__).resolve().parents[1] / "examples" / "agents" / "live_entry.py"
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(entry), "serve", "--help"], cwd=directory,
                                    capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--config", result.stdout)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()

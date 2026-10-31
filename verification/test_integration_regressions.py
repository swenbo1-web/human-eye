"""Regression coverage for scene state, MCP vision, entropy, protocol and A/B.

Run from the project root: python -B -m unittest discover -s verification -v
"""

from __future__ import annotations

import base64
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import numpy as np
from PIL import Image

import human_eye_foveated_renderer as core
from human_eye_module1_operators.submodule_1_6_quad_compositor import QuadCognitiveCanvasCompositor
from human_eye_plugin import HumanEyeLLMPlugin, handle_jsonrpc_message
from module_3_1_mcp_protocol_ipc_engine import McpProtocolEngine, McpSessionState


ROOT = Path(__file__).resolve().parent.parent


def rpc_call(plugin, name, arguments=None):
    response = handle_jsonrpc_message(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": name, "arguments": arguments or {}}}, plugin
    )
    if response["result"]["isError"]:
        raise AssertionError(response["result"]["content"])
    return response["result"]["content"]


class SceneAndVisionTests(unittest.TestCase):
    def setUp(self):
        self.plugin = HumanEyeLLMPlugin()

    def test_action_delta_tracks_only_the_moved_part(self):
        before = self.plugin.dispatch_tool_call("human_eye_sync_low_token_scene_delta")
        action = self.plugin.dispatch_tool_call("human_eye_apply_se3_closed_loop",
                                               {"focal_mark": "#B", "reference_mark": "#A"})
        after = self.plugin.dispatch_tool_call("human_eye_sync_low_token_scene_delta")
        unchanged = self.plugin.dispatch_tool_call("human_eye_sync_low_token_scene_delta")
        self.assertTrue(action["verification_passed"])
        self.assertEqual(set(before["changed_count"]), {"#A", "#B"})
        self.assertEqual(after["changed_count"], ["#B"])
        self.assertIn("step=2", after["dsl_text"])
        self.assertIn("state=ALIGNED_FLUSH", after["dsl_text"])
        self.assertIn("gap_mm=+0.00", after["dsl_text"])
        self.assertEqual(unchanged["changed_count"], [])

    def test_replacing_scene_rebinds_existing_ipc_owners(self):
        self.plugin.dispatch_tool_call("human_eye_apply_se3_closed_loop")
        original = list(self.plugin.meshes)
        self.plugin.set_scene_meshes(original)
        self.assertIs(self.plugin.meshes, self.plugin.scene_bridge.meshes)
        for owner in (self.plugin.vlm_agent, self.plugin.controller):
            self.assertIs(owner._scene_bridge, self.plugin.scene_bridge)
            if owner._mcp_ipc_engine is not None:
                self.assertIs(owner._mcp_ipc_engine.bridge_server, self.plugin.scene_bridge)
        self.assertIs(self.plugin.scratchpad, self.plugin.scene_bridge.scratchpad)

    def test_mcp_inspection_returns_png_pixels_and_som_anchors(self):
        blocks = rpc_call(self.plugin, "human_eye_inspect_scene_quad_canvas")
        self.assertEqual([b["type"] for b in blocks], ["text", "image"])
        metadata = json.loads(blocks[0]["text"])
        self.assertEqual(set(metadata["som_anchor_table"]), {"#A", "#B"})
        self.assertNotIn("mcp_image_content", metadata)
        self.assertEqual(blocks[1]["mimeType"], "image/png")
        png = base64.b64decode(blocks[1]["data"], validate=True)
        actual = np.asarray(Image.open(io.BytesIO(png)))
        expected = np.asarray(self.plugin.build_llm_observation_bundle()["canvas_image"])
        np.testing.assert_array_equal(actual, expected)
        self.assertEqual(actual.shape, (768, 768, 3))

    def test_baseline_mcp_image_is_the_q3_view(self):
        full = self.plugin.build_llm_observation_bundle()["canvas_image"]
        blocks = rpc_call(self.plugin, "human_eye_inspect_scene_quad_canvas",
                          {"enable_human_eye_plugin": False})
        metadata = json.loads(blocks[0]["text"])
        actual = Image.open(io.BytesIO(base64.b64decode(blocks[1]["data"])))
        expected = full.crop((0, 384, 384, 768)).resize((768, 768), Image.Resampling.BILINEAR)
        np.testing.assert_array_equal(np.asarray(actual), np.asarray(expected))
        self.assertEqual(metadata["som_anchor_table"], {})

    def test_recommended_action_is_advertised_and_executable(self):
        blocks = rpc_call(self.plugin, "human_eye_inspect_scene_quad_canvas")
        action = json.loads(blocks[0]["text"])["canonical_mcp_tool_call"]
        names = {t["name"] for t in self.plugin.get_tools_schema("mcp")}
        self.assertIn(action["tool"], names)
        result = json.loads(rpc_call(self.plugin, action["tool"], action["arguments"])[0]["text"])
        self.assertTrue(result["verification_passed"])

    def test_all_six_public_tools_are_serializable(self):
        requests = [
            ("human_eye_inspect_scene_quad_canvas", {}),
            ("human_eye_probe_spatial_clearance", {"enable_multi_locus_ior": True}),
            ("human_eye_sync_low_token_scene_delta", {}),
            ("human_eye_unproject_2d_click_to_3d", {"focal_click_or_box": [576, 576]}),
            ("human_eye_apply_se3_closed_loop", {"focal_mark": "#B", "reference_mark": "#A"}),
            ("human_eye_issue_digital_twin_certificate", {}),
        ]
        for name, args in requests:
            with self.subTest(tool=name):
                blocks = rpc_call(self.plugin, name, args)
                self.assertIsInstance(json.loads(blocks[0]["text"]), dict)

    def test_observation_estimate_changes_with_prompt_content(self):
        short = self.plugin.build_llm_observation_bundle(task_instruction="Align.")
        long = self.plugin.build_llm_observation_bundle(task_instruction="Align. " * 100)
        self.assertGreater(long["total_tokens"], short["total_tokens"])
        self.assertEqual(short["token_count_basis"], "estimated_observation")

    def test_stdio_returns_native_image_without_startup_warning(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "human_eye_inspect_scene_quad_canvas", "arguments": {}}},
        ]
        process = subprocess.run(
            [sys.executable, "-B", "-m", "human_eye_plugin.mcp_server"], cwd=ROOT,
            input="\n".join(json.dumps(r) for r in requests) + "\n",
            capture_output=True, text=True, encoding="utf-8", timeout=20,
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stderr, "")
        replies = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual([r["id"] for r in replies], [1, 2, 3])
        self.assertEqual(len(replies[1]["result"]["tools"]), 6)
        self.assertEqual([b["type"] for b in replies[2]["result"]["content"]], ["text", "image"])


class EntropyTests(unittest.TestCase):
    def test_both_renderers_match_independent_wide_integer_reference(self):
        meshes = core.build_test_scene_penetrating_peg()
        eye = np.array([1.35, -1.55, 1.45])
        target = np.array([0.0, 0.0, 0.45])
        for compositor_class in (core.QuadCognitiveCanvasCompositor, QuadCognitiveCanvasCompositor):
            with self.subTest(renderer=compositor_class.__module__):
                comp = compositor_class(quad_size=384)
                image, telemetry = comp.render_quad_cognitive_canvas(meshes, eye, target)
                pixels_before = np.asarray(image).copy()
                # A separate integer dot product provides an overflow-free reference.
                luma = np.asarray(image, dtype=np.uint64) @ np.array([77, 150, 29], dtype=np.uint64)
                luma = (luma // 256).astype(np.uint8)
                counts = np.bincount(luma.ravel(), minlength=256)
                probabilities = counts[counts > 0] / luma.size
                entropy = -float(np.sum(probabilities * np.log2(probabilities)))
                active = float((luma.reshape(16, 48, 16, 48).std(axis=(1, 3)) > 6).mean() * 100)
                report = comp.audit_quad_canvas_information_entropy_and_token_efficiency(meshes, eye, target)
                self.assertEqual(report.total_canvas_entropy_bits, round(entropy, 4))
                self.assertEqual(report.active_vit_patch_ratio_pct, round(active, 2))
                np.testing.assert_array_equal(comp._pbo_luma_u8, luma)
                np.testing.assert_array_equal(np.asarray(image), pixels_before)
                self.assertGreater(int(luma.max()), 200)
                self.assertGreater(active, 35)
                q = report.quadrant_shannon_entropy_bits
                gain = q["Q4_FOVEA"] / max(q["Q3_GIST"], 0.1) * min(float(telemetry["foveal_optical_zoom"]), 12)
                self.assertEqual(report.token_efficiency_certified, gain >= 5 and active >= 35)
                self.assertIn(f"certified={report.token_efficiency_certified}", report.summary_message)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.engine = McpProtocolEngine()
        self.focal = np.array([[0., 0., 0.42], [0.1, 0.1, 0.62]])
        self.reference = np.array([[-1., -1., 0.0], [1., 1., 0.3]])
        self.engine.arena.publish_tensor(0, self.focal)
        self.engine.arena.publish_tensor(1, self.reference)

    def dispatch(self, params, request_id=1, method="inspect_spatial_clearance"):
        request = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}).encode()
        return json.loads(self.engine.dispatch_raw_jsonrpc(request))

    def test_second_inspect_replays_in_resulting_state_with_current_request_id(self):
        a = self.dispatch({"focal_slot": 0, "reference_slot": 1}, 10)
        b = self.dispatch({"focal_slot": 0, "reference_slot": 1}, 11)
        self.assertEqual(a["result"], b["result"])
        self.assertEqual(b["id"], 11)
        self.assertEqual(self.engine._cache_hits, 1)
        self.assertEqual(self.engine.state, McpSessionState.INSPECTED_PENDING_ACTION)

    def test_default_slots_invalidate_cache_when_geometry_changes(self):
        a = self.dispatch({})
        self.engine.arena.publish_tensor(0, self.focal + [0, 0, 0.05])
        b = self.dispatch({})
        self.assertAlmostEqual(b["result"]["signed_clearance_m"] - a["result"]["signed_clearance_m"], 0.05)

    def test_nondefault_slots_invalidate_cache_when_geometry_changes(self):
        self.engine.arena.publish_tensor(4, self.focal)
        self.engine.arena.publish_tensor(5, self.reference)
        params = {"focal_slot": 4, "reference_slot": 5}
        a = self.dispatch(params)
        self.dispatch(params)
        self.engine.arena.publish_tensor(4, self.focal + [0, 0, 0.05])
        b = self.dispatch(params)
        self.assertAlmostEqual(b["result"]["signed_clearance_m"] - a["result"]["signed_clearance_m"], 0.05)

    def test_identity_quaternion_action_aligns_and_preserves_exact_vertices(self):
        result = self.dispatch({"focal_slot": 0, "reference_slot": 1, "output_slot": 2,
                                "rotation_quaternion_wxyz": [1, 0, 0, 0],
                                "translation_xyz_m": [0, 0, -0.12]}, method="apply_se3_prescription_and_recheck")
        self.assertTrue(result["result"]["verification_passed"])
        output, _ = self.engine.arena.resolve_tensor_view(2)
        np.testing.assert_array_equal(output, self.focal + [0, 0, -0.12])


class ABTests(unittest.TestCase):
    def setUp(self):
        self.plugin = HumanEyeLLMPlugin()
        self.baseline = {"rotation_euler_deg_xyz": [0, 0, 0], "translation_xyz_m": [0, 0, 0]}
        self.response = copy.deepcopy(self.plugin.build_llm_observation_bundle()["prompt_bundle"].canonical_mcp_tool_call)

    def test_estimated_counts_come_from_observations(self):
        result = self.plugin.evaluate_llm_response_ab_comparison(self.baseline, self.response)
        baseline = self.plugin.build_llm_observation_bundle(enable_human_eye_plugin=False)
        enabled = self.plugin.build_llm_observation_bundle()
        self.assertEqual(result.baseline_total_tokens, baseline["total_tokens"])
        self.assertEqual(result.plugin_total_tokens, enabled["total_tokens"])
        self.assertEqual(result.token_count_basis, "estimated_observation")
        self.assertEqual(result.evaluation_mode, "provided_responses")
        self.assertEqual(result.token_saving_ratio_pct, round((1-enabled["total_tokens"]/baseline["total_tokens"])*100, 2))

    def test_caller_usage_controls_reported_savings(self):
        result = self.plugin.evaluate_llm_response_ab_comparison(
            self.baseline, self.response, baseline_token_usage=2000, plugin_token_usage=500)
        self.assertEqual(result.baseline_total_tokens, 2000)
        self.assertEqual(result.plugin_total_tokens, 500)
        self.assertEqual(result.token_saving_ratio_pct, 75)
        self.assertEqual(result.token_count_basis, "caller_reported_usage")

    def test_missing_or_invalid_usage_is_rejected(self):
        for kwargs in ({"baseline_token_usage": 1}, {"plugin_token_usage": 1},
                       {"baseline_token_usage": 0, "plugin_token_usage": 1},
                       {"baseline_token_usage": 1, "plugin_token_usage": -1},
                       {"baseline_token_usage": True, "plugin_token_usage": 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.plugin.evaluate_llm_response_ab_comparison(self.baseline, self.response, **kwargs)

    def test_analytical_fallback_is_explicit_and_does_not_change_live_scene(self):
        before = [m.vertices.copy() for m in self.plugin.meshes]
        state = self.plugin.controller.fsm_state
        result = self.plugin.evaluate_llm_response_ab_comparison(self.baseline)
        self.assertEqual(result.evaluation_mode, "analytical_reference")
        self.assertIn("analytical_reference", result.summary_message)
        self.assertEqual(self.plugin.controller.fsm_state, state)
        for mesh, expected in zip(self.plugin.meshes, before):
            np.testing.assert_array_equal(mesh.vertices, expected)

    def test_ecbf_activation_is_measured_from_the_controller(self):
        # A 10mm overtravel is below the 15mm hallucination threshold, so the
        # actual controller, rather than the model sanitizer, must remove it.
        self.response["arguments"]["translation_xyz_m"][2] -= 0.01
        result = self.plugin.evaluate_llm_response_ab_comparison(self.baseline, self.response)
        self.assertFalse(result.plugin_hallucination_intercepted)
        self.assertTrue(result.plugin_ecbf_shield_activated)
        self.assertLess(result.plugin_residual_clearance_mm, result.baseline_residual_clearance_mm)

    def test_baseline_quaternion_only_response_is_supported(self):
        baseline = {"rotation_quaternion_wxyz": [1, 0, 0, 0], "translation_xyz_m": [0, 0, 0]}
        result = self.plugin.evaluate_llm_response_ab_comparison(baseline, self.response)
        self.assertEqual(result.baseline_residual_clearance_mm, 23)


if __name__ == "__main__":
    unittest.main()

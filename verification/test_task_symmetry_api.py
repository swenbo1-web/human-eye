"""Task symmetry must survive observation caches, fusion and public tool calls."""

import json
from pathlib import Path
import sys
import unittest

from human_eye_plugin import HumanEyeLLMPlugin
from human_eye_foveated_renderer import SpatialAnomalySniffer

sys.path.insert(0, str(Path(__file__).resolve().parent / "blind_test"))
from geometry import apply_raw_action, build_meshes, score_pose


class TaskSymmetryApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).parent / "blind_test/runs/20261021_01/private/cases.json"
        cls.cases = {c["scene_id"]: c for c in json.loads(path.read_text(encoding="utf-8"))}

    def test_public_observation_and_fusion_preserve_requested_order(self):
        for scene_id in ("S006", "S010"):
            case = self.cases[scene_id]
            plugin = HumanEyeLLMPlugin(meshes=build_meshes(case))
            for order in (4, 2, 4, 2):
                with self.subTest(scene=scene_id, order=order):
                    obs = plugin.dispatch_tool_call("human_eye_inspect_scene_quad_canvas", {"yaw_symmetry_order": order})
                    call = obs["canonical_mcp_tool_call"]
                    self.assertEqual(call["arguments"]["yaw_symmetry_order"], order)
                    rotation, center = apply_raw_action(case, call["arguments"])
                    metric = score_pose(case, rotation, center)
                    self.assertEqual(metric["success"], order == 2)
                    parsed = plugin.vlm_agent.parse_vlm_response_to_mcp_tool_call(call)
                    wrong_probe = SpatialAnomalySniffer.probe_closest_clearance(
                        plugin.meshes[1], plugin.meshes[0], yaw_symmetry_order=4 if order == 2 else 2)
                    fused, _ = plugin.vlm_agent.fuse_vlm_semantic_intent_with_analytical_se3(
                        parsed, plugin.meshes, precomputed_probe=wrong_probe)
                    self.assertEqual(fused["arguments"]["yaw_symmetry_order"], order)
                    rotation, center = apply_raw_action(case, fused["arguments"])
                    self.assertEqual(score_pose(case, rotation, center)["success"], order == 2)

    def test_public_execution_keeps_same_symmetry_as_observation(self):
        for order in (2, 4):
            plugin = HumanEyeLLMPlugin(meshes=build_meshes(self.cases["S006"]))
            obs = plugin.dispatch_tool_call("human_eye_inspect_scene_quad_canvas", {"yaw_symmetry_order": order})
            call = obs["canonical_mcp_tool_call"]
            result = plugin.dispatch_tool_call(call["tool"], call["arguments"])
            self.assertTrue(result["verification_passed"])
            probe = SpatialAnomalySniffer.probe_closest_clearance(
                plugin.meshes[1], plugin.meshes[0], yaw_symmetry_order=2)
            self.assertEqual(probe.is_aligned_flush, order == 2)

    def test_invalid_orders_rejected_by_public_api(self):
        plugin = HumanEyeLLMPlugin(meshes=build_meshes(self.cases["S012"]))
        for value in (True, 2.0, "2", 0, 3, 8):
            with self.subTest(value=value), self.assertRaises(ValueError):
                plugin.build_llm_observation_bundle(yaw_symmetry_order=value)

    def test_model_cannot_relax_outer_task_symmetry(self):
        plugin = HumanEyeLLMPlugin(meshes=build_meshes(self.cases["S006"]))
        call = plugin.build_llm_observation_bundle(yaw_symmetry_order=4)["prompt_bundle"].canonical_mcp_tool_call
        with self.assertRaisesRegex(ValueError, "cannot override"):
            plugin.vlm_agent.execute_single_perception_action_recheck_step(
                plugin.meshes, vlm_response_or_callable=call, yaw_symmetry_order=2)
        with self.assertRaisesRegex(ValueError, "cannot override"):
            plugin.evaluate_llm_response_ab_comparison(call, call, yaw_symmetry_order=2)

    def test_legacy_telemetry_without_symmetry_is_remeasured(self):
        case = self.cases["S006"]
        plugin = HumanEyeLLMPlugin(meshes=build_meshes(case))
        _, telemetry = plugin.vlm_agent.compositor.render_quad_cognitive_canvas(
            plugin.meshes, plugin.vlm_agent.default_cam_eye, plugin.vlm_agent.default_cam_target,
            yaw_symmetry_order=4)
        telemetry = json.loads(json.dumps(telemetry))
        telemetry["clearance_probe"].pop("yaw_symmetry_order")
        prompt = plugin.vlm_agent.compile_256_token_quad_grounding_prompt(
            plugin.meshes, telemetry=telemetry, yaw_symmetry_order=2)
        rotation, center = apply_raw_action(case, prompt.canonical_mcp_tool_call["arguments"])
        self.assertTrue(score_pose(case, rotation, center)["success"])

    def test_wrong_pair_precomputed_probe_cannot_poison_prompt_cache(self):
        plugin = HumanEyeLLMPlugin(meshes=build_meshes(self.cases["S016"]))
        reference, focal, other = plugin.meshes[:3]
        agent = plugin.vlm_agent
        wrong = SpatialAnomalySniffer.probe_closest_clearance(focal, other)
        right = SpatialAnomalySniffer.probe_closest_clearance(focal, reference)
        for probe in (wrong, right):
            prompt = agent.compile_256_token_quad_grounding_prompt(
                plugin.meshes, precomputed_probe=probe, focal_mesh=focal, ref_mesh=reference)
            self.assertEqual(prompt.canonical_mcp_tool_call["arguments"]["reference_mark"], "#A")


if __name__ == "__main__":
    unittest.main()

"""Optional task criteria enter existing tools without becoming authority."""
from __future__ import annotations

import copy
import json
import math
import unittest

from human_eye_plugin.live_spatial_mcp import LIVE_MCP_TOOLS_SCHEMA, LiveSpatialMCPServer
from verification.test_live_spatial_mcp import FakeService, png_content


class GoalService:
    def __init__(self):
        self.calls = []
        self.goal_succeeded = False

    def observe(self, session_id, *, task_instruction="", focal_id=None, reference_id=None, goal=None):
        self.calls.append(("observe", session_id, {"task_instruction": task_instruction,
            "focal_id": focal_id, "reference_id": reference_id, "goal": goal}))
        return self._result("observed")

    def transform(self, session_id, action, *, goal=None):
        self.calls.append(("transform", session_id, action, goal))
        return {**self._result("verified"), "verified": True, "execution_verified": True, "executed": True}

    def _result(self, status):
        return {"status": status, "task_succeeded": self.goal_succeeded,
                "goal_verification": {"task_succeeded": self.goal_succeeded,
                    "target_source": "caller_supplied", "human_intent_independently_verified": False,
                    "ground_truth_independent": False},
                "routing": {"route": "engine", "image": png_content()}}

    def status(self):
        self.calls.append(("status",))
        return {"status": "configured"}


class MCPGoalVerificationTests(unittest.TestCase):
    def setUp(self):
        self.service = GoalService()
        self.server = LiveSpatialMCPServer(self.service, default_session_id="goal-contract")

    def call(self, name="human_eye_scene_observe", arguments=None):
        return self.server.handle_jsonrpc_message({"jsonrpc": "2.0", "id": 1,
            "method": "tools/call", "params": {"name": name, "arguments": arguments or {}}})["result"]

    @staticmethod
    def action():
        return {"focal_id": "part", "reference_id": "base", "translation": [0, 0, .001]}

    @staticmethod
    def goal(**changes):
        result = {"target_clearance_m": .1, "clearance_tolerance_m": .001}
        result.update(changes)
        return result

    def test_three_tools_remain_and_goal_is_optional_with_strict_schema(self):
        self.assertEqual(len(LIVE_MCP_TOOLS_SCHEMA), 4)
        self.assertEqual([tool['name'] for tool in LIVE_MCP_TOOLS_SCHEMA[:3]], [
            'human_eye_scene_observe', 'human_eye_transform', 'human_eye_connection_status'])
        for tool in LIVE_MCP_TOOLS_SCHEMA[:2]:
            schema = tool["inputSchema"]
            self.assertNotIn("goal", schema.get("required", []))
            goal = schema["properties"]["goal"]
            self.assertFalse(goal["additionalProperties"])
            self.assertNotIn("required", goal)
            self.assertEqual(len(goal["anyOf"]), 4)
            self.assertEqual(goal["dependentRequired"]["target_clearance_m"], ["clearance_tolerance_m"])
            self.assertEqual(goal["dependentRequired"]["position_tolerance_m"], ["target_focal_pivot_world_m"])
            self.assertEqual(goal["properties"]["yaw_symmetry_order"]["enum"], [1, 2, 4])
        self.assertNotIn("goal", LIVE_MCP_TOOLS_SCHEMA[2]["inputSchema"]["properties"])

    def test_observe_forwards_omitted_goal_ids_without_inventing_binding(self):
        supplied = self.goal()
        result = self.call(arguments={"goal": supplied})
        self.assertFalse(result["isError"])
        forwarded = self.service.calls[0][2]["goal"]
        self.assertEqual(forwarded, supplied)
        self.assertNotIn("focal_id", forwarded)
        self.assertNotIn("reference_id", forwarded)

    def test_transform_forwards_goal_separately_from_action(self):
        supplied = {"max_tangent_yaw_mismatch_deg": .5, "yaw_symmetry_order": 4}
        result = self.call("human_eye_transform", {"action": self.action(), "goal": supplied})
        self.assertFalse(result["isError"])
        self.assertEqual(self.service.calls[0][2], self.action())
        self.assertEqual(self.service.calls[0][3], supplied)
        self.assertNotIn("goal", self.service.calls[0][2])

    def test_explicit_matching_goal_ids_and_position_target_are_supported(self):
        supplied = self.goal(focal_id="part", reference_id="base",
            target_focal_pivot_world_m=[12, -7, 3], position_tolerance_m=.001)
        result = self.call(arguments={"focal_id": "part", "reference_id": "base", "goal": supplied})
        self.assertFalse(result["isError"])
        self.assertEqual(self.service.calls[0][2]["goal"], supplied)

    def test_one_explicit_goal_id_does_not_require_both_at_transport_layer(self):
        for supplied in (self.goal(focal_id="part"), self.goal(reference_id="base")):
            self.assertFalse(self.call(arguments={"goal": supplied})["isError"])
        self.assertEqual(len(self.service.calls), 2)

    def test_goal_ids_cannot_contradict_selected_pair_before_service(self):
        invalid = [
            ("human_eye_scene_observe", {"focal_id": "part", "goal": self.goal(focal_id="other")}),
            ("human_eye_scene_observe", {"reference_id": "base", "goal": self.goal(reference_id="other")}),
            ("human_eye_transform", {"action": self.action(), "goal": self.goal(reference_id="other")}),
            ("human_eye_transform", {"action": self.action(), "goal": self.goal(focal_id="other")}),
        ]
        for name, arguments in invalid:
            with self.subTest(name=name, arguments=arguments):
                self.assertTrue(self.call(name, arguments)["isError"])
        self.assertEqual(self.service.calls, [])

    def test_invalid_or_empty_goals_are_rejected_before_service(self):
        invalid = [None, [], True, "target", {}, {"yaw_symmetry_order": 2},
            self.goal(unrecognized="value"), self.goal(verified=True),
            self.goal(target_source="human_confirmed"), self.goal(focal_id=""),
            self.goal(reference_id=" "), self.goal(focal_id="same", reference_id="same"),
            {"target_clearance_m": .1}, {"clearance_tolerance_m": .001},
            {"target_focal_pivot_world_m": [0, 0, 0]},
            {"position_tolerance_m": .001, "max_contact_normal_angle_deg": .5}]
        for goal in invalid:
            with self.subTest(goal=goal):
                self.assertTrue(self.call(arguments={"goal": goal})["isError"])
                self.assertTrue(self.call("human_eye_transform", {"action": self.action(), "goal": goal})["isError"])
        self.assertEqual(self.service.calls, [])

    def test_nonfinite_bool_string_and_out_of_range_criteria_are_rejected(self):
        for field, values in {
            "target_clearance_m": [True, "0.1", math.nan, math.inf, -.1],
            "clearance_tolerance_m": [True, "0.1", math.nan, math.inf, -.1],
            "max_contact_normal_angle_deg": [True, "1", math.nan, math.inf, -1, 181],
            "max_tangent_yaw_mismatch_deg": [True, "1", math.nan, math.inf, -1, 181],
            "yaw_symmetry_order": [True, "2", 2.0, 0, 3],
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    self.assertTrue(self.call(arguments={"goal": self.goal(**{field: value})})["isError"])
        self.assertEqual(self.service.calls, [])

    def test_position_vector_is_a_strict_json_array_and_requires_finite_values(self):
        for vector in ((0, 0, 0), [0, 0], [0, 0, False], [0, 0, math.inf], [0, 0, "1"]):
            goal = {"target_focal_pivot_world_m": vector, "position_tolerance_m": .001}
            self.assertTrue(self.call(arguments={"goal": goal})["isError"])
        self.assertEqual(self.service.calls, [])

    def test_absent_goal_does_not_add_new_service_keyword(self):
        legacy = FakeService()
        server = LiveSpatialMCPServer(legacy, default_session_id="legacy")
        for name, arguments in (("human_eye_scene_observe", {}),
                                 ("human_eye_transform", {"action": self.action()})):
            result = server.handle_jsonrpc_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": name, "arguments": arguments}})["result"]
            self.assertFalse(result["isError"])
        self.assertNotIn("goal", legacy.calls[0][2])
        self.assertEqual(legacy.calls[1], ("transform", "legacy", self.action()))

    def test_goal_failure_is_not_mislabeled_as_execution_failure(self):
        result = self.call("human_eye_transform", {"action": self.action(), "goal": self.goal()})
        self.assertFalse(result["isError"])
        metadata = json.loads(result["content"][0]["text"])
        self.assertTrue(metadata["execution_verified"])
        self.assertFalse(metadata["task_succeeded"])
        self.assertFalse(metadata["goal_verification"]["ground_truth_independent"])
        self.assertEqual(metadata["goal_verification"]["target_source"], "caller_supplied")
        self.assertFalse(metadata["goal_verification"]["human_intent_independently_verified"])

    def test_goal_payload_and_native_png_are_not_mutated_or_duplicated(self):
        arguments = {"action": self.action(), "goal": self.goal()}
        original = copy.deepcopy(arguments)
        result = self.call("human_eye_transform", arguments)
        self.assertEqual(arguments, original)
        self.service.calls[0][3]["target_clearance_m"] = 7
        self.assertEqual(arguments, original)
        self.assertEqual(result["content"][1]["type"], "image")
        self.assertNotIn(result["content"][1]["data"], result["content"][0]["text"])

    def test_mutating_notification_with_goal_still_never_executes(self):
        result = self.server.handle_jsonrpc_message({"jsonrpc": "2.0", "method": "tools/call",
            "params": {"name": "human_eye_transform", "arguments": {"action": self.action(), "goal": self.goal()}}})
        self.assertIsNone(result)
        self.assertEqual(self.service.calls, [])

    def test_status_tool_never_accepts_or_forwards_goals(self):
        self.assertTrue(self.call("human_eye_connection_status", {"goal": self.goal()})["isError"])
        self.assertEqual(self.service.calls, [])


if __name__ == "__main__":
    unittest.main()

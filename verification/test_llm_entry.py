"""CPU contract tests for the task-level MCP dispatcher."""

import base64
import json
from types import SimpleNamespace
import unittest

from human_eye_fast.control import Action, ClearanceReadback, Goal, Outcome, Translate
from human_eye_fast.fast_bvh_clearance import SurfaceDistance
from human_eye_fast.llm_entry import Binding, LLMEntry, PROTOCOL_VERSION


TARGETS = ("moving", "reference")
GOAL = Goal(*TARGETS, 0.025, 0.002)
RUN = {"task": "close_gap", "target_gap_m": GOAL.distance_m, "tolerance_m": GOAL.tolerance_m}
PNG = b"\x89PNG\r\n\x1a\n" + "图像证据".encode("utf-8")


def readback(observation_id, frame_id, distance_m):
    return ClearanceReadback(observation_id, frame_id, TARGETS,
                             SurfaceDistance(distance_m, 11, 29, (0., 0., 0.), (distance_m, 0., 0.)))


class StubTaskSession:
    def __init__(self, events):
        self.events = events
        self.behaviors = []
        self.gap_m = 0.05
        self.frame = 0

    def run(self, *, before_id, after_id):
        self.events.append(("run", before_id, after_id))
        self.frame += 1
        before = readback(before_id, self.frame, self.gap_m)
        behavior = self.behaviors.pop(0) if self.behaviors else "complete"
        command = Translate((0.03, 0., 0.))
        result = SimpleNamespace(status="reached", reason=None, write_status="not_written", stage=None,
                                 before=before, outcome=None, command=None, planned_after_m=None)
        if behavior == "before_failure":
            result.status, result.reason, result.stage = "error", "unavailable", "prepare"
            return result
        if abs(self.gap_m - GOAL.distance_m) <= GOAL.tolerance_m:
            result.status, result.reason = "no_action", "already_reached"
            return result
        result.command = command
        result.planned_after_m = GOAL.distance_m
        self.events.append(("write",))
        if behavior == "unknown_readback":
            result.status, result.stage, result.write_status = "error", "readback", "unknown"
            return result
        actual_gap_m = 0.024 if behavior == "complete" else 0.034
        actual_delta = self.gap_m - actual_gap_m
        action = Action("action", before_id, command)
        self.frame += 1
        after = readback(after_id, self.frame, actual_gap_m)
        result.write_status = "written"
        result.outcome = Outcome(GOAL, action, before, after, (0., 0., 0.), (actual_delta, 0., 0.),
                                 -actual_delta, behavior == "complete")
        self.gap_m = actual_gap_m
        if behavior == "after_failure":
            result.status, result.reason, result.stage = "error", "unavailable", "verify"
        elif behavior == "not_reached":
            result.status, result.reason = "not_reached", "outside_tolerance"
        return result

    def close(self):
        self.events.append(("close",))


class LLMEntryTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.session = StubTaskSession(self.events)
        self.binding = Binding(*TARGETS, self.open_task, self.open_renderer, labels=("移动件", "参考件"))
        self.connect(self.binding)
        self.request_id = 0

    def connect(self, binding):
        self.entry = LLMEntry(binding)
        self.addCleanup(self.entry.close)

    def open_task(self, target_gap_m, tolerance_m):
        self.events.append(("open_task", target_gap_m, tolerance_m))
        return self.session

    def render_image(self, session, readback, mode):
        self.assertIs(session, self.session)
        self.events.append(("render_image", readback, mode))
        return PNG, {"mode": mode, "mesh_ids": list(TARGETS), "section": None,
                     "meters_per_blender_unit": .001, "views": {"global": {"mode": mode}}}

    def open_renderer(self):
        self.events.append(("open_renderer",))
        return SimpleNamespace(render=self.render_image,
                               close=lambda: self.events.append(("close_renderer",)))

    def rpc(self, method, params=None, *, notification=False):
        request = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            request["params"] = params
        if not notification:
            self.request_id += 1
            request["id"] = self.request_id
        wire = self.entry.handle_line(json.dumps(request, allow_nan=False).encode("utf-8") + b"\n")
        if notification:
            self.assertIsNone(wire)
            return None
        self.assertTrue(wire.endswith(b"\n"))
        self.assertEqual(wire.count(b"\n"), 1)
        response = json.loads(wire.decode("utf-8"), parse_constant=self.reject_nonfinite)
        self.assertEqual((response["jsonrpc"], response["id"]), ("2.0", self.request_id))
        return response

    def reject_nonfinite(self, value):
        self.fail(f"Illegal JSON number in response: {value}")

    def initialize(self, offered=PROTOCOL_VERSION):
        params = {"protocolVersion": offered, "capabilities": {},
                  "clientInfo": {"name": "cpu-task-fixture", "version": "1"}}
        reply = self.rpc("initialize", params)["result"]
        self.assertEqual(reply["protocolVersion"], PROTOCOL_VERSION)
        self.assertIn("tools", reply["capabilities"])
        self.rpc("notifications/initialized", notification=True)

    def call(self, name, arguments):
        return self.rpc("tools/call", {"name": name, "arguments": arguments})["result"]

    def run_task(self, **arguments):
        return self.call("eye_run", {**RUN, **arguments})

    def inspect(self, task_id, evidence, **arguments):
        return self.call("eye_inspect", {"task_id": task_id, "evidence": evidence, **arguments})

    def count(self, event):
        return sum(item[0] == event for item in self.events)

    def fields(self, reply):
        self.assertNotIn("structuredContent", reply)
        block = reply["content"][0]
        self.assertEqual(block["type"], "text")
        return json.loads(block["text"], parse_constant=self.reject_nonfinite)

    def test_handshake_notifications_and_tool_list(self):
        self.assertIn("error", self.rpc("tools/list"))
        self.initialize("2025-11-25")
        self.assertEqual(self.rpc("ping")["result"], {})
        tools = self.rpc("tools/list")["result"]["tools"]
        self.assertEqual([tool["name"] for tool in tools], ["eye_run", "eye_inspect"])
        self.assertTrue(all(tool["inputSchema"]["type"] == "object" for tool in tools))
        self.rpc("tools/call", {"name": "eye_run", "arguments": RUN}, notification=True)
        rejected = self.rpc("tools/call", {"name": "eye_open", "arguments": {}})
        self.assertIn("error", rejected)
        self.assertEqual(self.events, [])

    def test_directory_has_only_bound_roles_and_never_opens_a_task(self):
        self.initialize()
        directory = self.call("eye_inspect", {"evidence": "directory"})
        self.assertEqual(len(directory["content"]), 1)
        self.assertEqual(self.fields(directory), {
            "status": "available", "evidence": "directory", "unit": "m", "tasks": ["close_gap"],
            "objects": [{"id": "moving", "name": "移动件", "role": "moving"},
                        {"id": "reference", "name": "参考件", "role": "reference"}],
        })
        self.assertEqual(self.events, [])

    def test_bad_task_or_evidence_is_rejected_before_dispatch(self):
        self.initialize()
        bad_runs = [
            {}, {**RUN, "task": "move"}, {**RUN, "moving_id": "another"},
            {**RUN, "target_gap_m": True}, {**RUN, "target_gap_m": -0.01},
            {**RUN, "tolerance_m": 10 ** 350}, {**RUN, "image_mode": "extra"},
        ]
        for arguments in bad_runs:
            with self.subTest(arguments=arguments):
                self.assertTrue(self.call("eye_run", arguments)["isError"])
        for task_id, evidence in [("", "witness"), ("gap-99", "image"), ("gap-99", "ao")]:
            with self.subTest(task_id=task_id, evidence=evidence):
                self.assertTrue(self.inspect(task_id, evidence)["isError"])
        request = (b'{"jsonrpc":"2.0","id":91,"method":"tools/call","params":{"name":"eye_run",'
                   b'"arguments":{"task":"close_gap","target_gap_m":0.025,"tolerance_m":@}}}\n')
        for invalid_constant in (b"NaN", b"Infinity"):
            wire = self.entry.handle_line(request.replace(b"@", invalid_constant))
            self.assertEqual(json.loads(wire)["error"]["code"], -32700)
        overflow = self.entry.handle_line(request.replace(b"@", b"1e1000"))
        self.assertTrue(json.loads(overflow)["result"]["isError"])
        self.assertEqual(self.events, [])

    def test_run_publishes_actual_result_with_no_optional_evidence_work(self):
        self.initialize()
        reply = self.run_task()
        fields = self.fields(reply)
        self.assertFalse(reply.get("isError", False))
        self.assertEqual((fields["task_id"], fields["task"]), ("gap-1", "close_gap"))
        self.assertEqual((fields["moving_id"], fields["reference_id"]), TARGETS)
        self.assertEqual((fields["unit"], fields["observation_id"], fields["frame_id"]), ("m", "gap-1-after", 2))
        self.assertEqual((fields["target_gap_m"], fields["tolerance_m"]), (0.025, 0.002))
        self.assertEqual((fields["before_gap_m"], fields["after_gap_m"]), (0.05, 0.024))
        self.assertAlmostEqual(fields["error_m"], 0.001)
        self.assertEqual(fields["write_status"], "written")
        self.assertTrue(fields["goal_reached"])
        self.assertEqual(fields["delta_world_m"], [0.03, 0., 0.])
        self.assertAlmostEqual(fields["actual_delta_world_m"][0], 0.026)
        self.assertEqual(fields["actual_delta_world_m"][1:], [0., 0.])
        self.assertEqual(len(reply["content"]), 1)
        self.assertTrue({"ao", "images", "schema", "prediction", "witness"}.isdisjoint(fields))
        self.assertEqual((self.count("run"), self.count("write"), self.count("open_renderer")), (1, 1, 0))
        self.assertEqual(self.events[0], ("open_task", 0.025, 0.002))

    def test_new_same_goal_uses_fresh_measurement_and_does_not_write_again(self):
        self.initialize()
        first = self.fields(self.run_task())
        second = self.fields(self.run_task())
        self.assertNotEqual(first["task_id"], second["task_id"])
        self.assertTrue(second["goal_reached"])
        self.assertEqual(second["before_gap_m"], first["after_gap_m"])
        self.assertIsNone(second["after_gap_m"])
        self.assertEqual(second["write_status"], "not_written")
        self.assertEqual((self.count("open_task"), self.count("run"), self.count("write")), (1, 2, 1))
        self.assertTrue(self.inspect(first["task_id"], "witness")["isError"])
        witness = self.fields(self.inspect(second["task_id"], "witness"))
        self.assertEqual(witness["observation_id"], "gap-2-before")
        self.assertEqual(witness["gap_m"], 0.024)

    def test_current_witness_is_read_only_and_image_is_lazily_cached(self):
        self.initialize()
        fields = self.fields(self.run_task())
        task_id = fields["task_id"]
        witness = self.inspect(task_id, "witness")
        self.assertFalse(witness.get("isError", False))
        self.assertEqual(self.fields(witness), {
            "task_id": task_id, "status": "available", "evidence": "witness", "observation_id": "gap-1-after",
            "frame_id": 2, "unit": "m", "moving_id": "moving", "reference_id": "reference",
            "gap_m": 0.024, "moving_point_m": [0., 0., 0.], "reference_point_m": [0.024, 0., 0.],
            "moving_triangle": 11, "reference_triangle": 29,
        })
        self.assertEqual(len(witness["content"]), 1)
        self.assertEqual(self.inspect(task_id, "witness"), witness)
        self.assertEqual(self.count("render_image"), 0)

        self.assertTrue(self.run_task(tolerance_m=-1)["isError"])
        self.assertEqual(self.inspect(task_id, "witness"), witness)

        image = self.inspect(task_id, "image")
        self.assertFalse(image.get("isError", False))
        self.assertEqual(self.fields(image), {
            "task_id": task_id, "status": "available", "evidence": "image", "observation_id": "gap-1-after",
            "frame_id": 2, "unit": "m", "moving_id": "moving", "reference_id": "reference",
            "mode": "NATURAL", "image_id": "gap-1-image-1", "scene_object_ids": list(TARGETS), "section": None,
            "panels": ["scene_context", "witness"],
        })
        self.assert_png(image)
        self.assertEqual(self.inspect(task_id, "image"), image)
        self.assertEqual((self.count("run"), self.count("write"), self.count("render_image")), (1, 1, 1))
        rendered = next(item[1] for item in self.events if item[0] == "render_image")
        self.assertEqual(rendered.surface.distance_m, fields["after_gap_m"])

    def assert_png(self, reply):
        self.assertEqual(len(reply["content"]), 2)
        self.fields(reply)
        block = reply["content"][1]
        self.assertEqual((block["type"], block["mimeType"]), ("image", "image/png"))
        self.assertEqual(base64.b64decode(block["data"], validate=True), PNG)

    def test_one_visual_run_delivers_terminal_png_and_reuses_it_on_inspect(self):
        self.initialize()
        reply = self.run_task(image_mode="SECTION")
        fields = self.fields(reply)
        self.assertTrue(fields["goal_reached"])
        self.assertEqual(fields["image"]["mode"], "SECTION")
        self.assert_png(reply)
        self.assertEqual([event[0] for event in self.events],
                         ["open_task", "run", "write", "open_renderer", "render_image"])
        self.assertEqual(self.events[-1][1].observation_id, fields["observation_id"])
        self.assertEqual(self.events[-1][2], "SECTION")
        cached = self.inspect(fields["task_id"], "image")
        self.assertEqual(self.fields(cached)["observation_id"], fields["observation_id"])
        self.assertEqual(cached["content"][1], reply["content"][1])
        self.assertEqual(self.count("render_image"), 1)
        task_id = fields["task_id"]
        result = self.inspect(task_id, "result")
        self.assertEqual(result["content"], reply["content"][:1])
        camera_reply = self.inspect(task_id, "camera")
        self.assertEqual(len(camera_reply["content"]), 1)
        camera = self.fields(camera_reply)
        self.assertEqual(camera["image_id"], fields["image"]["image_id"])
        self.assertEqual(camera["meters_per_blender_unit"], .001)
        self.assertEqual(camera["views"], {"global": {"mode": "SECTION"}})
        self.assertEqual(self.count("render_image"), 1)
        natural = self.inspect(task_id, "image", image_mode="NATURAL")
        natural_id = self.fields(natural)["image_id"]
        self.assertNotEqual(natural_id, camera["image_id"])
        self.assertEqual(self.inspect(task_id, "image"), natural)
        self.assertEqual(self.fields(self.inspect(task_id, "camera"))["views"], {"global": {"mode": "NATURAL"}})
        self.assertEqual(self.fields(self.inspect(task_id, "result")), fields)
        self.assertEqual((self.count("run"), self.count("write"), self.count("render_image"),
                          self.count("open_renderer")), (1, 1, 2, 1))
        next_id = self.fields(self.run_task())["task_id"]
        self.assertTrue(self.inspect(task_id, "result")["isError"])
        self.assertEqual(self.fields(self.inspect(next_id, "camera"))["reason"], "no_current_image")
        self.entry.close()
        self.entry.close()
        self.assertEqual((self.count("close"), self.count("close_renderer")), (1, 1))

    def test_disabled_and_unavailable_images_are_explicit(self):
        self.entry.close()
        self.connect(Binding(*TARGETS, self.open_task))
        self.initialize()
        disabled = self.run_task(image_mode="NATURAL")
        self.assertTrue(disabled["isError"])
        self.assertEqual(self.fields(disabled)["write_status"], "not_written")
        self.assertEqual(self.count("write"), 0)
        task_id = self.fields(self.run_task())["task_id"]
        reply = self.inspect(task_id, "image")
        self.assertEqual(self.fields(reply)["reason"], "image_disabled")
        self.assertFalse(reply["isError"])
        self.assertEqual(len(reply["content"]), 1)
        self.assertEqual(self.count("render_image"), 0)

        self.entry.close()
        self.connect(Binding(*TARGETS, self.open_task,
                             lambda: SimpleNamespace(render=lambda *args: None, close=lambda: None)))
        self.initialize()
        run = self.run_task(image_mode="NATURAL")
        self.assertTrue(run["isError"])
        self.assertTrue(self.fields(run)["goal_reached"])
        task_id = self.fields(run)["task_id"]
        reply = self.inspect(task_id, "image")
        self.assertEqual(self.fields(reply)["reason"], "image_unavailable")
        self.assertFalse(reply["isError"])
        self.assertEqual(len(reply["content"]), 1)

    def test_write_failures_keep_their_known_actual_state(self):
        self.initialize()
        self.session.behaviors.extend(["before_failure", "after_failure"])
        before = self.run_task()
        self.assertTrue(before["isError"])
        self.assertEqual(self.fields(before)["write_status"], "not_written")
        self.assertEqual(self.fields(before)["before_gap_m"], 0.05)
        self.assertEqual(self.fields(before)["stage"], "prepare")
        self.assertEqual(self.count("write"), 0)

        after = self.run_task()
        self.assertTrue(after["isError"])
        fields = self.fields(after)
        self.assertEqual(fields["write_status"], "written")
        self.assertEqual(fields["after_gap_m"], 0.034)
        self.assertEqual(fields["stage"], "verify")
        self.assertFalse(fields["goal_reached"])
        evidence = self.fields(self.inspect(fields["task_id"], "witness"))
        self.assertEqual(evidence["reason"], "no_measured_surface")
        self.assertEqual(fields["witness"]["gap_m"], 0.034)
        self.assertEqual((self.count("open_task"), self.count("run"), self.count("write")), (1, 2, 1))
        self.assertEqual(self.inspect(fields["task_id"], "result"), after)
        next_result = self.run_task(target_gap_m=0.02)
        self.assertEqual(self.fields(next_result)["before_gap_m"], 0.034)
        self.assertEqual((self.count("open_task"), self.count("run"), self.count("write")), (2, 3, 2))

    def test_measured_miss_remains_inspectable_and_allows_a_fresh_explicit_task(self):
        self.initialize()
        self.session.behaviors.append("not_reached")
        result = self.run_task()
        fields = self.fields(result)
        self.assertEqual((fields["status"], fields["write_status"]), ("not_reached", "written"))
        self.assertFalse(fields["goal_reached"])
        self.assertEqual(fields["after_gap_m"], 0.034)
        self.assertAlmostEqual(fields["error_m"], 0.009)
        witness = self.fields(self.inspect(fields["task_id"], "witness"))
        self.assertEqual(witness["gap_m"], 0.034)
        self.assertEqual((self.count("run"), self.count("write")), (1, 1))
        retried = self.run_task()
        self.assertFalse(retried["isError"])
        self.assertEqual(self.fields(retried)["before_gap_m"], 0.034)
        self.assertEqual((self.count("run"), self.count("write")), (2, 2))

    def test_unknown_write_does_not_retry_and_allows_fresh_explicit_run(self):
        self.initialize()
        self.session.behaviors.append("unknown_readback")
        error = self.run_task()
        self.assertTrue(error["isError"])
        fields = self.fields(error)
        self.assertEqual(fields["write_status"], "unknown")
        self.assertFalse(fields["goal_reached"])
        self.assertIsNone(fields["after_gap_m"])
        before = self.fields(self.inspect(fields["task_id"], "witness"))
        self.assertEqual((before["status"], before["reason"]), ("unavailable", "no_measured_surface"))
        self.assertEqual((self.count("run"), self.count("write")), (1, 1))
        self.assertEqual(self.inspect(fields["task_id"], "result"), error)
        self.assertFalse(self.run_task()["isError"])
        self.assertEqual((self.count("run"), self.count("write")), (2, 2))
        self.entry.close()

        self.connect(self.binding)
        self.initialize()
        self.assertFalse(self.run_task()["isError"])
        self.assertEqual((self.count("run"), self.count("write")), (3, 2))

    def test_host_close_releases_resources_once(self):
        self.initialize()
        self.run_task()
        self.entry.close()
        self.entry.close()
        self.assertEqual(self.count("close"), 1)
        self.assertIn("error", self.rpc("tools/list"))


if __name__ == "__main__":
    unittest.main()

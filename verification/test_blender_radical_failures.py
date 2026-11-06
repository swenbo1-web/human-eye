"""Portable staged-failure and ownership checks of the production session."""

from contextlib import nullcontext
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_fast import (
    ActionStageError, BlenderRadicalSession, CaptureChange, CFDeployment, Goal, MeshChange,
    ObservationRequest, ReferenceFrame, Translate,
)
from human_eye_fast import blender_radical_session as radical
from verification.test_integration_preflight import _StubBridge, _StubObject


class _UncertainSetter(_StubObject):
    @_StubObject.matrix_world.setter
    def matrix_world(self, matrix):
        _StubObject.matrix_world.fset(self, matrix)
        raise RuntimeError("setter failed after a partial host change")


class _ReusingBridge(_StubBridge):
    def capture(self, key, obj, graph, scale, changes=0):
        previous = self.meshes.get(key)
        if previous is not None and not changes:
            return previous
        if (self.case == "second-target" and key == "reference"
                and any(event[0] == "write" for event in self.events)):
            self.case = "owned"
            raise RuntimeError("second capture failed after moving world array changed")
        replacement = super().capture(key, obj, graph, scale, changes)
        if previous is not None:
            previous.world_m[:] = replacement.world_m
            previous.world_from_local[:] = replacement.world_from_local
            self.meshes[key] = previous
            return previous
        return replacement


def _deployment():
    return CFDeployment(
        v_mean=np.zeros(5), v_scale=np.ones(5), v_weights=np.zeros(6),
        v_quadratic=False, v_lambda=0.0,
        a_mean=np.zeros(23), a_scale=np.ones(23), a_weights=np.zeros(24),
        a_quadratic=False, a_lambda=0.0, retrieval_scale=np.ones((16, 5)),
        v_keys=np.empty((0, 16, 5)), v_values=np.empty((0, 16, 2)),
        v_known=np.empty((0, 16), dtype=bool), a_keys=np.empty((0, 23)),
        a_values=np.empty((0, 1)), a_known=np.empty((0, 1), dtype=bool),
    )


def _request(observation_id):
    return ObservationRequest(observation_id, None, "F")


class ProductionFailures(unittest.TestCase):
    def _session(self, case):
        events = []
        objects = {key: (_UncertainSetter if case == "setter" and key == "moving" else _StubObject)(
            key, x, events) for key, x in (("moving", 0.), ("reference", 2.), ("context", 4.))}
        layer = SimpleNamespace(name="explicit")
        scene = SimpleNamespace(frame_current=17, view_layers={layer.name: layer},
                                unit_settings=SimpleNamespace(scale_length=1.))
        graph = object()
        context = SimpleNamespace(temp_override=lambda **_: nullcontext(),
                                  evaluated_depsgraph_get=lambda: graph)
        changes = {key: CaptureChange(MeshChange.VERTICES | MeshChange.TRANSFORM) for key in objects}
        reference = ReferenceFrame(16, 1, [[1., 0., 0.], [1., 1., 0.], [1., 0., 1.]])
        with patch.dict(sys.modules, {"bpy": SimpleNamespace(context=context)}):
            session = BlenderRadicalSession(
                scene, layer, objects, Goal("moving", "reference", 0., 0.),
                dict(zip(objects, (1, 2, 3), strict=True)), reference=reference, deployment=_deployment(),
            )
        bridge_type = _ReusingBridge if case in ("owned", "second-target") else _StubBridge
        session._controller.bridge = bridge_type(case, events)
        self.addCleanup(session.close)
        return session, changes, events

    def test_real_stage_and_outcome_are_preserved(self):
        cases = {
            "prepare": ("prepare", "not_written", False, None),
            "setter": ("write", "unknown", True, None),
            "target-readback": ("target_readback", "written", True, None),
            "control-after": ("target_readback", "written", True, None),
            "after-context": ("context", "written", True, -.25),
            "td": ("td", "written", True, -.25),
            "render": ("render", "written", True, -.25),
            "ao": ("ao", "written", True, -.25),
        }
        for case, (stage, status, written, measured) in cases.items():
            with self.subTest(case=case):
                session, changes, events = self._session(case)
                session.observe(_request("before"), changes=changes)
                plan = session.predict_action("before", "act", Translate((.25, 0., 0.)), predictor="L")
                target = {
                    "prepare": (session._controller._context, "evaluated_depsgraph_get"),
                    "td": (radical, "compute_cross_frame_deformation_tensor"),
                    "render": (session, "_render"),
                    "ao": (radical, "encode"),
                }.get(case)
                fault = patch.object(*target, side_effect=RuntimeError(case)) if target else nullcontext()
                with fault, self.assertRaises(ActionStageError) as caught:
                    session.execute(plan, _request("after"), changes=changes)
                error = caught.exception
                self.assertEqual((error.stage, error.write_status), (stage, status))
                self.assertEqual([event for event in events if event[0] == "write"],
                                 [("write", "moving", .25)] if written else [])
                self.assertIsNone(session._current)
                self.assertIsNone(session._controller._latest)
                if measured is None:
                    self.assertIsNone(error.outcome)
                    self.assertIsNone(error.action_ticket)
                else:
                    self.assertEqual(error.outcome.measured_delta_m, measured)
                    self.assertEqual(error.outcome.control_after, (.25, 0., 0.))
                    session.action_feedback(error.action_ticket)
                    self.assertEqual(session._model.actions.writes, 1)
                    with self.assertRaises(ValueError):
                        session.action_feedback(error.action_ticket)
                with self.assertRaises(ValueError):
                    session.execute(plan, _request("after-retry"), changes=changes)

    def test_after_overwrite_keeps_before_fact_and_invalidates_other_plans(self):
        session, changes, events = self._session("owned")
        before = session.observe(_request("before"), changes=changes)
        self.assertIsNone(session._renderer)
        plan = session.predict_action("before", "act", Translate((.25, 0., 0.)), predictor="G")
        stale = session.predict_action("before", "other", Translate((.5, 0., 0.)), predictor="NONE")
        action = session.execute(plan, _request("after"), changes=changes)
        with self.assertRaises(ValueError):
            session.execute(stale, _request("never"), changes=changes)
        self.assertEqual([event for event in events if event[0] == "write"], [("write", "moving", .25)])
        session.close()
        old_rows = json.loads(before.ao_bytes)[3]
        joint_rows = json.loads(action.ao_bytes)[3]
        self.assertEqual(joint_rows[0], old_rows[0])
        self.assertNotEqual(joint_rows[0][4][7][0][-1], joint_rows[1][4][7][0][-1])
        self.assertEqual(list(action.attachments), [])

    def test_fresh_observation_recovers_index_after_partial_capture(self):
        session, changes, _ = self._session("second-target")
        session.observe(_request("before"), changes=changes)
        plan = session.predict_action("before", "act", Translate((.25, 0., 0.)), predictor="NONE")
        with self.assertRaises(ActionStageError) as caught:
            session.execute(plan, _request("after"), changes=changes)
        self.assertEqual(caught.exception.stage, "target_readback")
        self.assertIsNone(caught.exception.outcome)
        unchanged = {key: CaptureChange(MeshChange.NONE) for key in changes}
        restored = session.observe(_request("fresh"), changes=unchanged)
        clearance = json.loads(restored.ao_bytes)[3][0][3]
        self.assertEqual(clearance[2], .75)
        self.assertEqual(clearance[3][1][0], 1.25)


if __name__ == "__main__":
    unittest.main()

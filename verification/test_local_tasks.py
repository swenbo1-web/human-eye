"""CPU tests of the typed close_gap action boundary, with a Blender control double."""

from contextlib import nullcontext
from dataclasses import replace
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

from human_eye_fast.blender_resident_bridge import MeshChange
from human_eye_fast.control import ActionStageError, ClearanceReadback, Goal, Outcome
from human_eye_fast.fast_bvh_clearance import SurfaceDistance
from human_eye_fast.local_tasks import CloseGapSession, CloseGapTask


_IDS = "moving", "reference"


def _object(name, *, kind="MESH"):
    return SimpleNamespace(name=name, type=kind)


def _surface(distance=5.):
    return SurfaceDistance(distance, 0, 1, (0., 0., 0.), (.6 * distance, .8 * distance, 0.))


class CloseGapTests(unittest.TestCase):
    def setUp(self):
        self.moving, self.reference = [_object(key) for key in _IDS]
        self.objects = dict(zip(_IDS, (self.moving, self.reference)))
        self.layer = SimpleNamespace(name="Layer", objects=self.objects.copy())
        self.scene = SimpleNamespace(view_layers={"Layer": self.layer}, frame_current=17, frame_subframe=0.,
                                     unit_settings=SimpleNamespace(scale_length=.001))
        self.bpy_context = Mock()
        self.bpy_context.temp_override.side_effect = lambda **_: nullcontext()
        self.graph = object()
        self.bpy_context.evaluated_depsgraph_get.return_value = self.graph
        blender_patch = patch.dict(sys.modules, {"bpy": SimpleNamespace(context=self.bpy_context)})
        blender_patch.start()
        self.addCleanup(blender_patch.stop)
        self.control = Mock()
        self.meshes = {key: object() for key in _IDS}
        self.control.bridge.capture.side_effect = lambda key, *_: self.meshes[key]
        controller_patch = patch("human_eye_fast.local_tasks.BlenderControl", return_value=self.control)
        self.open_control = controller_patch.start()
        self.addCleanup(controller_patch.stop)
        self.before = ClearanceReadback("before", 17, _IDS, _surface())
        self.control.observe.return_value = self.before

    def session(self, target=2., tolerance=1e-7):
        task = CloseGapTask(*_IDS, target, tolerance)
        session = CloseGapSession(self.scene, self.layer, self.objects, task)
        self.addCleanup(session.close)
        return session

    def _make_outcome(self, gap, action, *, reached, before=None, after_id="after"):
        before = before or self.before
        after = ClearanceReadback(after_id, before.frame_id, _IDS, _surface(gap))
        return Outcome(self.open_control.call_args.args[2], action, before, after,
                       (0., 0., 0.), action.command.delta_world_m,
                       gap - before.surface.distance_m, reached)

    def test_one_action_along_global_world_witness_and_measured_after(self):
        parent = _object("static parent", kind="EMPTY")
        self.moving.parent = self.reference.parent = parent
        session = self.session()
        self.control.execute.side_effect = lambda action, *a, **k: self._make_outcome(2., action, reached=True)
        result = session.run(before_id="before", after_id="after")
        self.open_control.assert_called_once_with(self.scene, self.objects, Goal(*_IDS, 2., 1e-7),
                                                  view_layer=self.layer)
        self.control.observe.assert_called_once_with("before")
        self.control.execute.assert_called_once()
        args, kwargs = self.control.execute.call_args
        action, after_id = args
        self.assertEqual((result.status, result.write_status, result.reason), ("reached", "written", None))
        self.assertEqual((action.before_observation_id, after_id, result.planned_after_m), ("before", "after", 2.))
        for actual, wanted in zip(action.command.delta_world_m, (1.8, 2.4, 0.)):
            self.assertAlmostEqual(actual, wanted)
        self.assertEqual(action.predicted_delta_m, -3.)
        self.assertEqual(kwargs, {"target_changes": dict.fromkeys(_IDS, MeshChange.VERTICES | MeshChange.TRANSFORM)})
        self.assertIs(result.before, self.before)
        self.assertEqual(result.outcome.after.surface.distance_m, 2.)
        self.assertEqual(result.outcome.measured_delta_m, -3.)
        self.assertEqual(session.evidence_meshes(result.outcome.after), (self.meshes, .001))
        self.control.bridge.capture.assert_any_call(
            "moving", self.moving, self.graph, .001, MeshChange.APPEARANCE)
        self.control.bridge.capture.assert_any_call(
            "reference", self.reference, self.graph, .001, MeshChange.APPEARANCE)
        with self.assertRaises(ValueError):
            session.evidence_meshes(replace(result.outcome.after))
        with self.assertRaises(ValueError):
            session.evidence_meshes(result.before)

    def test_already_in_either_side_of_tolerance_empty_and_increase_never_write(self):
        cases = ((5.01, .02, _surface(), "no_action", "already_reached"),
                 (4.99, .02, _surface(), "no_action", "already_reached"),
                 (0., 0., _surface(0.), "no_action", "already_reached"),
                 (2., 0., SurfaceDistance(float("inf"), None, None, None, None),
                  "no_action", "empty_surface"),
                 (6., 0., _surface(), "rejected", "would_increase_gap"),
                 (1., 0., _surface(0.), "rejected", "would_increase_gap"))
        for target, tolerance, surface, status, reason in cases:
            with self.subTest(reason=reason, target=target, distance=surface.distance_m):
                self.control.observe.return_value = replace(self.before, surface=surface)
                result = self.session(target, tolerance).run(before_id="before", after_id="after")
                self.assertEqual((result.status, result.reason, result.write_status),
                                 (status, reason, "not_written"))
                self.assertIsNone(result.outcome)
        self.control.execute.assert_not_called()

    def test_zero_target_from_positive_gap_is_a_single_contact_step(self):
        session = self.session(target=0.)
        self.control.execute.side_effect = lambda action, *a, **k: self._make_outcome(0., action, reached=True)
        result = session.run(before_id="before", after_id="after")
        self.assertEqual(result.command.delta_world_m, (3., 4., 0.))
        self.assertEqual(result.outcome.after.surface.distance_m, 0.)
        self.control.execute.assert_called_once()

    def test_finite_witness_roundoff_does_not_prevent_measured_execution(self):
        distance = .000999998934674593
        point_b = distance + 5.14e-11
        target = .00075
        self.before = replace(self.before, surface=replace(_surface(distance), point_b=(point_b, 0., 0.)))
        self.control.observe.return_value = self.before
        session = self.session(target=target, tolerance=8e-9)
        self.control.execute.side_effect = lambda action, *a, **k: self._make_outcome(target, action, reached=True)
        result = session.run(before_id="before", after_id="after")
        self.assertEqual(result.status, "reached")
        self.assertAlmostEqual(result.command.delta_world_m[0], (distance - target) / distance * point_b, places=15)
        self.assertEqual(result.outcome.after.surface.distance_m, target)
        self.control.execute.assert_called_once()

    def test_actual_gap_can_fail_even_with_correct_requested_translation(self):
        session = self.session()
        self.control.execute.side_effect = lambda action, *a, **k: self._make_outcome(4.5, action, reached=False)
        result = session.run(before_id="before", after_id="after")
        self.assertEqual((result.status, result.reason, result.write_status),
                         ("not_reached", "outside_tolerance", "written"))
        self.assertEqual(result.planned_after_m, 2.)
        self.assertEqual(result.outcome.after.surface.distance_m, 4.5)
        self.assertEqual(result.outcome.measured_delta_m, -.5)
        self.assertEqual(session.evidence_meshes(result.outcome.after), (self.meshes, .001))
        self.control.execute.assert_called_once()
        new_before = replace(self.before, observation_id="new-before", surface=_surface(4.5))
        self.control.observe.return_value = new_before
        self.control.execute.side_effect = lambda action, *a, **k: self._make_outcome(
            2., action, reached=True, before=new_before, after_id="new-after")
        next_task = session.run(before_id="new-before", after_id="new-after")
        self.assertEqual(next_task.status, "reached")
        self.assertEqual(next_task.before.surface.distance_m, 4.5)
        self.assertEqual(next_task.outcome.after.observation_id, "new-after")
        self.assertEqual(self.control.execute.call_count, 2)

    def test_stage_failure_preserves_outcome_clears_evidence_and_allows_fresh_run(self):
        cases = (("not_written", "prepare"), ("unknown", "write"), ("written", "context"))
        for status, stage in cases:
            with self.subTest(write_status=status):
                self.control.reset_mock()
                session = self.session()
                self.control.observe.return_value = replace(
                    self.before, observation_id="prior-before", surface=_surface(2.))
                prior = session.run(before_id="prior-before", after_id="prior-after")
                self.assertEqual(prior.status, "no_action")
                self.control.observe.return_value = self.before
                error = ActionStageError(stage, status)

                def failed_execute(action, *args, **kwargs):
                    if status == "written":
                        error.outcome = self._make_outcome(4.5, action, reached=False)
                    raise error

                self.control.execute.side_effect = failed_execute
                result = session.run(before_id="before", after_id="after")
                self.assertEqual((result.status, result.reason, result.write_status, result.stage),
                                 ("error", "execution_failed", status, stage))
                self.assertIs(result.outcome, error.outcome)
                invalid_evidence = [prior.before, result.before]
                if result.outcome is not None:
                    self.assertEqual(result.outcome.after.surface.distance_m, 4.5)
                    invalid_evidence.append(result.outcome.after)
                for readback in invalid_evidence:
                    with self.assertRaises(ValueError):
                        session.evidence_meshes(readback)
                self.control.execute.assert_called_once()

                fresh = replace(self.before, observation_id="new-before", surface=_surface(3.5))
                self.control.observe.return_value = fresh
                self.control.execute.side_effect = lambda action, *a, **k: self._make_outcome(
                    2., action, reached=True, before=fresh, after_id="new-after")
                again = session.run(before_id="new-before", after_id="new-after")
                self.assertEqual(again.status, "reached")
                self.assertIs(again.before, fresh)
                self.assertEqual(self.control.observe.call_args_list,
                                 [call("prior-before"), call("before"), call("new-before")])
                self.assertEqual(self.control.execute.call_count, 2)

    def test_written_without_finite_readback_has_no_success_or_borrowed_evidence(self):
        session = self.session()
        self.control.execute.side_effect = lambda action, *a, **k: replace(
            self._make_outcome(float("inf"), action, reached=False), measured_delta_m=None)
        result = session.run(before_id="before", after_id="after")
        self.assertEqual((result.status, result.reason, result.write_status),
                         ("error", "unmeasured_after", "written"))
        self.assertIsNotNone(result.outcome)
        for readback in (result.before, result.outcome.after):
            with self.assertRaises(ValueError):
                session.evidence_meshes(readback)

    def test_invalid_request_never_reads_or_writes(self):
        for target, tolerance in ((True, 0.), (0., "0.1"), (float("nan"), 0.),
                                  (0., float("inf")), (-1., 0.), (0., -1.), (10**1000, 0.)):
            with self.subTest(target=type(target), tolerance=tolerance), self.assertRaises(ValueError):
                CloseGapTask(*_IDS, target, tolerance)
        session = self.session()
        with self.assertRaises(ValueError):
            session.run(before_id="same", after_id="same")
        self.control.observe.assert_not_called()
        self.control.execute.assert_not_called()

    def test_invalid_read_and_witness_refuse_without_writing(self):
        session = self.session()
        self.control.observe.side_effect = RuntimeError("capture failure")
        failed = session.run(before_id="before", after_id="after")
        self.assertEqual((failed.reason, failed.stage, failed.write_status),
                         ("observation_failed", "observe", "not_written"))
        self.control.observe.side_effect = None
        self.control.observe.return_value = replace(
            self.before, surface=replace(_surface(), point_b=(float("nan"), 0., 0.)))
        failed = session.run(before_id="before", after_id="after")
        self.assertEqual((failed.reason, failed.stage, failed.write_status),
                         ("invalid_witness", "plan", "not_written"))
        with self.assertRaises(ValueError):
            session.evidence_meshes(failed.before)
        self.control.execute.assert_not_called()

    def test_visual_evidence_preserves_bound_context_order_and_never_recaptures_target_geometry(self):
        session = self.session(target=5.)
        result = session.run(before_id="before", after_id="after")
        context = {"panel-z": _object("Z"), "panel-a": _object("A")}
        self.layer.objects.update({obj.name: obj for obj in context.values()})
        self.meshes.update(dict.fromkeys(context, object()))
        meshes, scale = session.evidence_meshes(result.before, context_objects=context)
        self.assertEqual(list(meshes), [*_IDS, *context])
        self.assertEqual((meshes, scale), (self.meshes, .001))
        self.bpy_context.temp_override.assert_called_once_with(scene=self.scene, view_layer=self.layer)
        self.bpy_context.evaluated_depsgraph_get.assert_called_once()
        captures = [call.args for call in self.control.bridge.capture.call_args_list]
        self.assertEqual(captures, [
            ("moving", self.moving, self.graph, .001, MeshChange.APPEARANCE),
            ("reference", self.reference, self.graph, .001, MeshChange.APPEARANCE),
            ("panel-z", context["panel-z"], self.graph, .001, MeshChange.TOPOLOGY | MeshChange.APPEARANCE),
            ("panel-a", context["panel-a"], self.graph, .001, MeshChange.TOPOLOGY | MeshChange.APPEARANCE),
        ])
        self.control.observe.assert_called_once_with("before")
        self.control.execute.assert_not_called()

    def test_visual_evidence_rejects_changed_frame_subframe_scale_and_context_aliases(self):
        session = self.session(target=5.)
        result = session.run(before_id="before", after_id="after")
        for owner, key, value in ((self.scene, "frame_current", 18), (self.scene, "frame_subframe", .1),
                                  (self.scene.unit_settings, "scale_length", 1.)):
            with self.subTest(key=key), patch.object(owner, key, value), self.assertRaises(ValueError):
                session.evidence_meshes(result.before)
        for context in ({"moving": _object("outside")}, {"alias": self.moving},
                        {"outside": _object("outside")}):
            with self.subTest(context=context), self.assertRaises(ValueError):
                session.evidence_meshes(result.before, context_objects=context)
        self.control.bridge.capture.assert_not_called()

    def test_close_releases_control_and_evidence_once(self):
        session = self.session(target=5.)
        result = session.run(before_id="before", after_id="after")
        self.assertEqual(session.evidence_meshes(result.before), (self.meshes, .001))
        session.close()
        session.close()
        self.control.close.assert_called_once()
        with self.assertRaises(ValueError):
            session.evidence_meshes(result.before)
        with self.assertRaises(RuntimeError):
            session.run(before_id="before", after_id="after")


if __name__ == "__main__":
    unittest.main()

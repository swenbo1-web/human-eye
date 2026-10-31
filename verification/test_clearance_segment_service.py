"""Behavioral checks for bounded clearance segments and durable replay.

These tests use an independent mutable host and temporary connector state.
They never connect to Blender.  In particular, a lost result must not cause
another host write, even when the next call uses a new service instance.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin.live_service import LiveSpatialService
from verification.test_host_runtime import mesh
from verification.test_live_service import SelfLockingHost


class SegmentHost(SelfLockingHost):
    """Keep trusted capture metadata while retaining existing failure modes."""

    def __init__(self, gap=.004):
        super().__init__()
        self.scene['meshes'][1] = mesh('part', [0, 0, .25 + gap], [.2, .3, .1], True)
        self.scene['host_identity'] = {
            'schema_version': '1.0',
            'document_epoch': 'doc-1',
            'object_instances': {'base': 'i-base', 'part': 'i-part'},
            'capture_scope': 'complete_scene_meshes',
        }
        self.after_capture = None
        self.after_mutation = None
        self.change_between_steps = None
        self._first_step_post_captures = 0

    def capture_scene(self):
        # The first capture after a mutation is the independent readback.  A
        # subsequent capture can model an editor changing the scene between
        # steps without corrupting that preceding, confirmed readback.
        if self.calls == 1:
            self._first_step_post_captures += 1
            if self._first_step_post_captures == 2 and self.change_between_steps:
                self.change_between_steps(self)
        result = super().capture_scene()
        if self.after_capture:
            self.after_capture(self)
        return result

    def apply_transform(self, action, expected_revision, expected_fingerprint=None, **kwargs):
        result = super().apply_transform(action, expected_revision, expected_fingerprint)
        if self.after_mutation:
            self.after_mutation(self)
        return result

    def actual_gap(self):
        base, part = self.scene['meshes'][:2]
        return min(v[2] for v in part['vertices']) - max(v[2] for v in base['vertices'])


class SegmentClock:
    def __init__(self):
        self.value = 0.

    def monotonic(self):
        return self.value

    def expire(self, _host=None):
        self.value = 100.


class ClearanceSegmentServiceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.config_path = self.folder / 'live.json'
        self.state_path = self.folder / 'state.json'
        self.config_path.write_text(json.dumps({
            'schema_version': '1.0',
            'project_root': str(Path(__file__).resolve().parents[1]),
            'state_file': 'state.json',
            'audit_file': 'events.jsonl',
            'quad_size': 64,
            'max_sessions': 4,
            'enabled': True,
        }), encoding='utf-8')
        self.host = SegmentHost()
        self.service = self.new_service()

    def new_service(self):
        return LiveSpatialService(self.config_path, host=self.host)

    @staticmethod
    def request(**changes):
        value = {
            'focal_id': 'part',
            'reference_id': 'base',
            'target_clearance_m': .001,
            'clearance_tolerance_m': 1e-6,
            'axis': '+z',
            'max_steps': 4,
            'max_step_translation_m': .01,
            'max_total_translation_m': .04,
            'max_duration_s': 5.,
        }
        value.update(changes)
        return value

    def run_segment(self, *, service=None, request_id='request-1', request=None,
                    session_id='segment-test', execute=True, **kwargs):
        return (service or self.service).run_clearance_segment(
            session_id, request_id, self.request() if request is None else request,
            execute=execute, include_image=False, **kwargs)

    def read_state(self):
        return json.loads(self.state_path.read_text(encoding='utf-8'))

    def assert_no_more_host_work(self, calls, captures):
        self.assertEqual(self.host.calls, calls)
        self.assertEqual(self.host.captures, captures)

    def test_default_preview_does_not_write_state_or_move_host(self):
        before = copy.deepcopy(self.host.scene)
        result = self.service.run_clearance_segment('segment-test', 'preview-1', self.request())
        self.assertEqual(result['status'], 'preview', result)
        self.assertEqual(self.host.calls, 0)
        self.assertGreater(self.host.captures, 0)
        self.assertEqual(self.host.scene, before)
        self.assertFalse(self.state_path.exists())

    def test_preview_preserves_existing_state_bytes(self):
        self.service.observe('old-session', focal_id='part', reference_id='base', include_image=False)
        before = self.state_path.read_bytes()
        result = self.run_segment(execute=False)
        self.assertEqual(result['status'], 'preview', result)
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertEqual(self.host.calls, 0)

    def test_preview_does_not_consume_the_execution_request_identity(self):
        self.assertEqual(self.run_segment(execute=False)['status'], 'preview')
        result = self.run_segment()
        self.assertEqual(result['status'], 'satisfied', result)
        self.assertEqual(self.host.calls, 1)

    def test_one_step_reaches_real_target_without_caller_translation(self):
        request = self.request()
        original = copy.deepcopy(request)
        result = self.run_segment(request=request)
        self.assertEqual(result['status'], 'satisfied', result)
        self.assertEqual(self.host.calls, 1)
        self.assertLessEqual(abs(self.host.actual_gap() - .001), 1e-6)
        self.assertEqual(request, original)
        self.assertIsNone(self.read_state()['inflight'])

    def test_already_satisfied_goal_does_not_call_host_mutation(self):
        self.host = SegmentHost(gap=.001)
        self.service = self.new_service()
        result = self.run_segment()
        self.assertEqual(result['status'], 'satisfied', result)
        self.assertEqual(self.host.calls, 0)

    def test_step_limit_causes_confirmed_multiple_moves(self):
        self.host = SegmentHost(gap=.024)
        self.service = self.new_service()
        result = self.run_segment()
        self.assertEqual(result['status'], 'satisfied', result)
        # Admission may reserve room for the host readback error, so the
        # implementation need not use exactly the ideal arithmetic step count.
        self.assertGreaterEqual(self.host.calls, 3)
        self.assertLessEqual(self.host.calls, 4)
        self.assertLessEqual(abs(self.host.actual_gap() - .001), 1e-6)
        self.assertIsNone(self.read_state()['inflight'])

    def test_step_budget_stops_with_actual_partial_progress(self):
        self.host = SegmentHost(gap=.024)
        self.service = self.new_service()
        result = self.run_segment(request=self.request(max_steps=1))
        self.assertEqual(result['status'], 'review_required', result)
        self.assertEqual(self.host.calls, 1)
        self.assertGreater(self.host.actual_gap(), .001 + 1e-6)
        self.assertLess(self.host.actual_gap(), .024)
        self.assertIsNone(self.read_state()['inflight'])

    def test_motion_budget_never_allows_excess_total_motion(self):
        self.host = SegmentHost(gap=.024)
        self.service = self.new_service()
        before = self.host.actual_gap()
        result = self.run_segment(request=self.request(max_total_translation_m=.005))
        self.assertIn(result['status'], {'blocked', 'review_required'}, result)
        self.assertLessEqual(abs(before - self.host.actual_gap()), .005 + 1e-6)
        self.assertGreater(self.host.actual_gap(), .001 + 1e-6)

    def test_duplicate_request_returns_receipt_without_capture_or_write(self):
        first = self.run_segment()
        self.assertEqual(first['status'], 'satisfied', first)
        calls, captures = self.host.calls, self.host.captures
        state_before = self.state_path.read_bytes()
        second = self.run_segment()
        self.assertEqual(second['status'], 'satisfied', second)
        self.assert_no_more_host_work(calls, captures)
        self.assertEqual(self.state_path.read_bytes(), state_before)

    def test_replay_after_restart_returns_prior_result_not_fresh_scene_claim(self):
        self.assertEqual(self.run_segment()['status'], 'satisfied')
        # Later external scene edits do not authorize repeating a completed ID.
        self.host.scene['meshes'][1] = mesh('part', [0, 0, .27], [.2, .3, .1], True)
        self.host.scene['revision'] = 'r90'
        calls, captures = self.host.calls, self.host.captures
        result = self.run_segment(service=self.new_service())
        self.assertEqual(result['status'], 'satisfied', result)
        self.assert_no_more_host_work(calls, captures)
        self.assertAlmostEqual(self.host.actual_gap(), .02)

    def test_same_request_identity_with_changed_target_is_conflict(self):
        self.assertEqual(self.run_segment()['status'], 'satisfied')
        calls, captures = self.host.calls, self.host.captures
        result = self.run_segment(request=self.request(target_clearance_m=.002))
        self.assertEqual(result['status'], 'request_conflict', result)
        self.assert_no_more_host_work(calls, captures)

    def test_same_request_identity_with_changed_budget_is_conflict(self):
        self.assertEqual(self.run_segment()['status'], 'satisfied')
        calls, captures = self.host.calls, self.host.captures
        result = self.run_segment(request=self.request(max_steps=3))
        self.assertEqual(result['status'], 'request_conflict', result)
        self.assert_no_more_host_work(calls, captures)

    def test_receipt_capacity_does_not_evict_old_request_identity(self):
        from human_eye_plugin import goal_execution
        self.host = SegmentHost(gap=.001)
        self.service = self.new_service()
        with patch.object(goal_execution, 'MAX_SEGMENT_RECEIPTS', 2):
            for identity in ('first', 'second'):
                self.assertEqual(self.run_segment(request_id=identity)['status'], 'satisfied')
            calls, captures = self.host.calls, self.host.captures
            result = self.run_segment(request_id='third')
            self.assertEqual(result['status'], 'receipt_capacity_exhausted', result)
            self.assert_no_more_host_work(calls, captures)
            self.assertEqual(self.run_segment(request_id='first')['status'], 'satisfied')
            self.assert_no_more_host_work(calls, captures)

    def test_missing_host_identity_cannot_authorize_real_segment(self):
        self.host.scene.pop('host_identity')
        result = self.run_segment()
        self.assertEqual(result['status'], 'blocked', result)
        self.assertEqual(self.host.calls, 0)

    def test_incomplete_instance_binding_cannot_authorize_real_segment(self):
        self.host.scene['host_identity']['object_instances'].pop('part')
        try:
            result = self.run_segment()
        except ValueError:
            pass
        else:
            self.assertEqual(result['status'], 'blocked', result)
        self.assertEqual(self.host.calls, 0)

    def test_lost_host_result_never_advances_or_resends(self):
        self.host.mode = 'partial_failure'
        result = self.run_segment()
        self.assertEqual(result['status'], 'execution_uncertain', result)
        self.assertEqual(self.host.calls, 1)
        self.assertIsNotNone(self.read_state()['inflight'])
        for identity in ('request-1', 'new-request'):
            replay = self.run_segment(service=self.new_service(), request_id=identity)
            self.assertIn(replay['status'], {'execution_uncertain', 'blocked', 'segment_interrupted'}, replay)
            self.assertEqual(self.host.calls, 1)

    def test_legacy_transform_cannot_bypass_unresolved_segment(self):
        self.host.mode = 'partial_failure'
        self.run_segment()
        result = self.new_service().transform('other', {
            'focal_id': 'part', 'reference_id': 'base', 'translation': [0, 0, .001],
        })
        self.assertIn(result['status'], {'host_quarantined', 'blocked', 'segment_interrupted'}, result)
        self.assertEqual(self.host.calls, 1)

    def test_intent_persist_failure_occurs_before_any_mutation(self):
        from human_eye_plugin.live_service import _atomic_write
        def refuse_intent(path, data, **kwargs):
            if data.get('inflight') is not None:
                raise OSError('Cannot persist the step intent')
            return _atomic_write(path, data, **kwargs)
        with patch('human_eye_plugin.live_service._atomic_write', side_effect=refuse_intent):
            try:
                self.run_segment()
            except OSError:
                pass
        self.assertEqual(self.host.calls, 0)

    def test_result_persist_failure_retains_uncertainty_and_no_reexecution(self):
        from human_eye_plugin.live_service import _atomic_write
        def refuse_after_commit(path, data, **kwargs):
            if self.host.calls and data.get('inflight') is None:
                raise OSError('Crash before persisting the confirmed step result')
            return _atomic_write(path, data, **kwargs)
        with patch('human_eye_plugin.live_service._atomic_write', side_effect=refuse_after_commit):
            try:
                self.run_segment()
            except OSError:
                pass
        self.assertEqual(self.host.calls, 1)
        self.assertIsNotNone(self.read_state()['inflight'])
        result = self.run_segment(service=self.new_service())
        self.assertIn(result['status'], {'execution_uncertain', 'blocked', 'segment_interrupted'}, result)
        self.assertEqual(self.host.calls, 1)

    def test_running_record_from_interrupted_process_does_not_resume(self):
        self.assertEqual(self.run_segment()['status'], 'satisfied')
        state = self.read_state()
        record = state['goal_segments']['records']['request-1']
        record['status'] = 'running'
        record['result'] = None
        self.state_path.write_text(json.dumps(state), encoding='utf-8')
        calls = self.host.calls
        result = self.run_segment(service=self.new_service())
        self.assertEqual(result['status'], 'segment_interrupted', result)
        self.assertEqual(self.host.calls, calls)

    def test_old_state_without_goal_ledger_remains_usable(self):
        self.service.observe('legacy', focal_id='part', reference_id='base', include_image=False)
        state = self.read_state()
        state.pop('goal_segments', None)
        self.state_path.write_text(json.dumps(state), encoding='utf-8')
        result = self.run_segment(service=self.new_service())
        self.assertEqual(result['status'], 'satisfied', result)
        self.assertEqual(self.host.calls, 1)
        final = self.read_state()
        self.assertEqual(final['schema_version'], '1.0')
        self.assertIn('runtime', final)
        self.assertIsNone(final['inflight'])

    def test_deadline_after_capture_prevents_first_write(self):
        from human_eye_plugin import goal_execution
        clock = SegmentClock()
        self.host.after_capture = clock.expire
        with patch.object(goal_execution.time, 'monotonic', side_effect=clock.monotonic):
            result = self.run_segment()
        self.assertIn(result['status'], {'review_required', 'blocked'}, result)
        self.assertEqual(self.host.calls, 0)

    def test_deadline_after_commit_keeps_readback_but_stops_next_step(self):
        from human_eye_plugin import goal_execution
        clock = SegmentClock()
        self.host = SegmentHost(gap=.024)
        self.host.after_mutation = clock.expire
        self.service = self.new_service()
        with patch.object(goal_execution.time, 'monotonic', side_effect=clock.monotonic):
            result = self.run_segment()
        self.assertEqual(result['status'], 'review_required', result)
        self.assertEqual(self.host.calls, 1)
        self.assertGreaterEqual(self.host._first_step_post_captures, 1)
        self.assertIsNone(self.read_state()['inflight'])

    def test_document_change_between_confirmed_steps_stops_local_loop(self):
        self.host = SegmentHost(gap=.024)
        self.host.change_between_steps = lambda host: host.scene['host_identity'].update(document_epoch='doc-2')
        self.service = self.new_service()
        result = self.run_segment()
        self.assertIn(result['status'], {'review_required', 'blocked', 'execution_uncertain'}, result)
        self.assertEqual(self.host.calls, 1)

    def test_same_name_recreated_object_between_steps_is_not_old_target(self):
        self.host = SegmentHost(gap=.024)
        def replace_instance(host):
            host.scene['host_identity']['object_instances']['part'] = 'different-instance'
        self.host.change_between_steps = replace_instance
        self.service = self.new_service()
        result = self.run_segment()
        self.assertIn(result['status'], {'review_required', 'blocked', 'execution_uncertain'}, result)
        self.assertEqual(self.host.calls, 1)

    def test_nonfocal_instance_replaced_after_commit_makes_readback_uncertain(self):
        # Geometry, names and numeric transforms stay the same.  The new
        # instance must still invalidate execution evidence for the old scene.
        def replace_base_instance(host):
            host.scene['host_identity']['object_instances']['base'] = 'base-recreated'
        self.host.after_mutation = replace_base_instance
        result = self.run_segment()
        self.assertEqual(result['status'], 'execution_uncertain', result)
        self.assertIsNone(result['executed'])
        self.assertEqual(self.host.calls, 1)
        state = self.read_state()
        self.assertIsNotNone(state['inflight'])
        step = state['goal_segments']['records']['request-1']['steps'][0]
        self.assertEqual(step['state'], 'uncertain')
        self.assertFalse(step['result']['execution_verified'])
        replay = self.run_segment(service=self.new_service())
        self.assertEqual(replay['status'], 'execution_uncertain', replay)
        self.assertEqual(self.host.calls, 1)

    def test_corrupt_persisted_receipt_is_rejected_before_host_access(self):
        self.assertEqual(self.run_segment()['status'], 'satisfied')
        baseline = self.read_state()
        calls, captures = self.host.calls, self.host.captures

        def wrong_status(record):
            record['result']['status'] = 'blocked'

        def wrong_request(record):
            record['result']['request_id'] = 'unrelated-request'

        def missing_step_result(record):
            record['steps'][0]['result'] = None
            record['result']['steps'][0]['result'] = None

        def empty_step_result(record):
            # An empty dictionary is valid JSON, but cannot prove what
            # happened to a step marked complete.  Corrupt both copies so the
            # check exercises receipt validity, not merely copy equality.
            record['steps'][0]['result'] = {}
            record['result']['steps'][0]['result'] = {}

        for corrupt in (wrong_status, wrong_request, missing_step_result, empty_step_result):
            with self.subTest(corruption=corrupt.__name__):
                state = copy.deepcopy(baseline)
                corrupt(state['goal_segments']['records']['request-1'])
                self.state_path.write_text(json.dumps(state), encoding='utf-8')
                with self.assertRaises(ValueError):
                    self.run_segment(service=self.new_service())
                self.assert_no_more_host_work(calls, captures)

    def test_zero_step_goal_evaluator_failure_is_a_finished_review_result(self):
        self.host = SegmentHost(gap=.001)
        self.service = self.new_service()
        with patch('human_eye_plugin.task_verification.evaluate_spatial_goal',
                   side_effect=RuntimeError('Goal evaluator temporarily unavailable')):
            result = self.run_segment()
        self.assertEqual(result['status'], 'review_required', result)
        self.assertIn('goal_evaluation_unavailable', result['reason_codes'])
        self.assertFalse(result['task_succeeded'])
        self.assertEqual(self.host.calls, 0)
        state = self.read_state()
        self.assertIsNone(state['inflight'])
        entry = state['goal_segments']['records']['request-1']
        self.assertEqual(entry['status'], 'review_required')
        self.assertEqual(entry['steps'], [])
        captures = self.host.captures
        replay = self.run_segment(service=self.new_service())
        self.assertEqual(replay['status'], 'review_required', replay)
        self.assert_no_more_host_work(0, captures)

    def test_deadline_expiring_after_inner_geometry_gate_prevents_commit(self):
        from human_eye_plugin import goal_execution
        from human_eye_plugin.auto_router import HumanEyeAutoRouter
        clock = SegmentClock()
        original = HumanEyeAutoRouter.handle_event
        accepted_gates = []

        def expire_after_geometry(router, event):
            result = original(router, event)
            if event.get('event') == 'before_action':
                accepted_gates.append(result.get('allow_action'))
                clock.expire()
            return result

        with patch.object(goal_execution.time, 'monotonic', side_effect=clock.monotonic), \
                patch.object(HumanEyeAutoRouter, 'handle_event', new=expire_after_geometry):
            result = self.run_segment()
        self.assertEqual(accepted_gates, [True])
        self.assertEqual(result['status'], 'blocked', result)
        self.assertIn('segment_time_budget_exhausted_before_commit', result['reason_codes'])
        self.assertEqual(self.host.calls, 0)
        self.assertIsNone(self.read_state()['inflight'])
        self.assertNotEqual(self.read_state()['goal_segments']['records']['request-1']['status'], 'running')

    def test_metrics_failure_cannot_change_confirmed_execution_or_enable_retry(self):
        with patch('human_eye_plugin.goal_execution.summarize_goal_segment_metrics',
                   side_effect=RuntimeError('Metrics unavailable')):
            result = self.run_segment()
        self.assertEqual(result['status'], 'satisfied', result)
        self.assertEqual(result['metrics']['status'], 'unavailable')
        self.assertTrue(result['executed'])
        self.assertEqual(self.host.calls, 1)
        self.assertLessEqual(abs(self.host.actual_gap() - .001), 1e-6)
        self.assertIsNone(self.read_state()['inflight'])
        calls, captures = self.host.calls, self.host.captures
        replay = self.run_segment(service=self.new_service())
        self.assertEqual(replay['status'], 'satisfied', replay)
        self.assert_no_more_host_work(calls, captures)

    def test_invalid_request_bounds_do_not_mutate_host(self):
        invalid = (
            {'max_steps': 9}, {'max_steps': True}, {'max_step_translation_m': 1.01},
            {'max_total_translation_m': 4.01}, {'max_duration_s': 30.01},
            {'clearance_tolerance_m': -1}, {'target_clearance_m': -1},
            {'axis': 'guess'}, {'axis': [0, 0, 1]},
        )
        for changes in invalid:
            with self.subTest(changes=changes):
                try:
                    result = self.run_segment(request=self.request(**changes))
                except (TypeError, ValueError):
                    continue
                self.assertEqual(result['status'], 'blocked', result)
        self.assertEqual(self.host.calls, 0)


if __name__ == '__main__':
    unittest.main()

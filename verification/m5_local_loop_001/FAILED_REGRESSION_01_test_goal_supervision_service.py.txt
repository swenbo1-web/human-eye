"""Durable service fault windows using an independent mutable host.

No Blender connection, production state or provider is used. The host meter
observes actual setters separately from the segment receipt under test.
"""
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin.goal_budget import GoalBudgetLimits
from human_eye_plugin.goal_journal import GoalJournalError
from human_eye_plugin.goal_supervision import GoalSupervisorContext
from human_eye_plugin.live_service import LiveSpatialService, _atomic_write
from verification.test_clearance_segment_service import SegmentHost


class MeteredHost(SegmentHost):
    def __init__(self):
        super().__init__()
        self.paths = []

    def apply_transform(self, action, expected_revision, expected_fingerprint=None, **kwargs):
        before = self.scene['meshes'][1]['vertices'][0][:]
        before_revision = self.scene['revision']
        try:
            result = super().apply_transform(action, expected_revision, expected_fingerprint, **kwargs)
            result['receipt'].update(host_execution_verified=True, focal_id=action['focal_id'],
                before_revision=before_revision, after_revision=self.scene['revision'])
            return result
        finally:
            after = self.scene['meshes'][1]['vertices'][0][:]
            if before != after:
                self.paths.append(math.dist(before, after))


class GoalSupervisionServiceTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.config = self.folder/'config.json'
        self.state = self.folder/'state.json'
        self.config.write_text(json.dumps({'schema_version':'1.0',
            'project_root':str(Path(__file__).resolve().parents[1]), 'state_file':'state.json',
            'audit_file':'audit.jsonl', 'quad_size':64}), encoding='utf-8')
        self.host = MeteredHost()
        self.domain = 'owned-unit-boot-1'
        self.allowed = True
        self.meter_calls = 0
        self.context = GoalSupervisorContext(lambda:self.domain,
            lambda *args:self.allowed, self.meter)
        self.service = self.new_service()

    def new_service(self, *, trusted=True):
        return LiveSpatialService(self.config, host=self.host,
            supervisor_context=self.context if trusted else None)

    def meter(self, goal_id, request_id, child):
        self.meter_calls += 1
        count = len(child['steps'])
        return {'complete':True, 'actual_setter_count':len(self.host.paths),
            'actual_cumulative_translation_m':math.fsum(self.host.paths),
            'step_motions_m':self.host.paths[-count:] if count else [], 'rollback_count':0}

    def read(self):
        return json.loads(self.state.read_text(encoding='utf-8'))

    def prepare(self, *, limits=None, request_id='child-1', max_steps=8):
        self.service.goal_supervision('begin', 'goal-1', 'session-1', limits=limits)
        caps = self.service.goal_supervision('caps', 'goal-1')['caps']
        request = {'focal_id':'part', 'reference_id':'base', 'axis':'+z',
            'target_clearance_m':.001, 'clearance_tolerance_m':1e-6,
            **caps, 'max_steps':min(max_steps, caps['max_steps'])}
        return self.service.goal_supervision('reserve', 'goal-1', request_id=request_id,
                                               request=request)['request']

    def execute(self, request, *, service=None):
        return (service or self.service).run_supervised_clearance_segment(
            'goal-1', 'session-1', 'child-1', request)

    def reconcile(self, *, service=None):
        return (service or self.service).goal_supervision('reconcile', 'goal-1', request_id='child-1')

    def assert_no_bypass(self):
        calls = self.host.calls
        service = self.new_service(trusted=False)
        result = service.transform('other', {'focal_id':'part','reference_id':'base',
                                              'translation':[0,0,.0001]})
        self.assertEqual(result['status'], 'segment_interrupted')
        result = service.run_clearance_segment('other', 'fresh-id', {
            'focal_id':'part','reference_id':'base','axis':'+z',
            'target_clearance_m':.001,'clearance_tolerance_m':1e-6}, execute=True)
        self.assertEqual(result['status'], 'segment_interrupted')
        self.assertEqual(self.host.calls, calls)
        return service

    def test_committed_child_reconciles_after_new_service_without_more_writes(self):
        request = self.prepare()
        result = self.execute(request)
        self.assertEqual(result['status'], 'satisfied', result)
        calls = self.host.calls
        other = self.assert_no_bypass()
        self.assertEqual(other.status()['goal_supervision']['blocking_goal_id'], 'goal-1')
        self.assertIn('status', other.observe('read', focal_id='part', reference_id='base', include_image=False))
        receipt = self.reconcile(service=self.new_service())
        self.assertEqual(receipt['confirmed_steps'], calls)
        self.assertEqual(receipt['stopped_reason'], 'goal_satisfied')
        self.assertIsNone(other.status()['goal_supervision']['blocking_goal_id'])
        again = self.reconcile(service=self.new_service())
        self.assertEqual(again['confirmed_steps'], calls)
        self.assertEqual(self.host.calls, calls)

    def test_commit_then_lost_ack_does_not_resend(self):
        request = self.prepare()
        failed = []
        def lose_ack(path, value, **kwargs):
            result = _atomic_write(path, value, **kwargs)
            child = value.get('goal_segments', {}).get('records', {}).get('child-1')
            if child and child['status'] == 'satisfied' and not failed:
                failed.append(True)
                raise OSError('owned simulated lost acknowledgement after commit')
            return result
        with patch('human_eye_plugin.live_service._atomic_write', side_effect=lose_ack):
            with self.assertRaises(OSError):self.execute(request)
        calls = self.host.calls
        self.assertGreater(calls, 0)
        self.assertEqual(self.read()['goal_segments']['records']['child-1']['status'], 'satisfied')
        result = self.reconcile(service=self.new_service())
        self.assertEqual(result['confirmed_steps'], calls)
        replay = self.execute(request, service=self.new_service())
        self.assertTrue(replay['historical_receipt'])
        self.assertEqual(self.host.calls, calls)

    def test_partial_step_commit_with_clear_inflight_remains_unknown(self):
        request = self.prepare()
        failed = []
        def crash(path, value, **kwargs):
            result = _atomic_write(path, value, **kwargs)
            child = value.get('goal_segments', {}).get('records', {}).get('child-1')
            if (child and child['status'] == 'running' and child['steps']
                    and child['steps'][-1].get('state') == 'complete'
                    and 'actual_translation_m' not in child['steps'][-1] and not failed):
                failed.append(True)
                raise OSError('owned simulated crash before independent motion accounting')
            return result
        with patch('human_eye_plugin.live_service._atomic_write', side_effect=crash):
            with self.assertRaises(OSError):self.execute(request)
        self.assertEqual(self.host.calls, 1)
        self.assertIsNone(self.read()['inflight'])
        with self.assertRaises(GoalJournalError):self.reconcile(service=self.new_service())
        self.assertEqual(self.meter_calls, 0)
        self.assert_no_bypass()
        self.assertEqual(self.host.calls, 1)

    def test_dispatch_commit_before_capture_failure_never_becomes_safe_retry(self):
        request = self.prepare()
        with patch.object(self.host, 'capture_scene', side_effect=OSError('owned capture failure')):
            with self.assertRaises(OSError):self.execute(request)
        self.assertEqual(self.host.calls, 0)
        self.assertNotIn('goal_segments', self.read())
        with self.assertRaises(GoalJournalError):self.reconcile(service=self.new_service())
        with self.assertRaises(GoalJournalError):self.execute(request, service=self.new_service())
        self.assert_no_bypass()
        self.assertEqual(self.host.calls, 0)

    def test_failed_dispatch_persistence_prevents_even_capture(self):
        request = self.prepare()
        captures = self.host.captures
        with patch('human_eye_plugin.live_service._atomic_write', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.execute(request)
        self.assertEqual(self.host.calls, 0)
        self.assertEqual(self.host.captures, captures)
        self.assert_no_bypass()

    def test_denied_trusted_authorization_does_not_touch_host(self):
        request = self.prepare()
        self.allowed = False
        with self.assertRaises(GoalJournalError):self.execute(request)
        self.assertEqual(self.host.calls, 0)
        self.assertEqual(self.host.captures, 0)
        self.assert_no_bypass()

    def test_json_cannot_supply_trusted_context(self):
        with self.assertRaises(ValueError):
            LiveSpatialService(self.config, host=self.host,
                supervisor_context={'clock_domain':self.domain, 'authorize_dispatch':True})
        with self.assertRaises(GoalJournalError):
            self.new_service(trusted=False).goal_supervision('begin', 'fake', 's')
        self.assertEqual(self.host.calls, 0)

    def test_reserved_child_cannot_enter_standalone_route(self):
        request = self.prepare()
        result = self.new_service().run_clearance_segment('session-1', 'child-1', request, execute=True)
        self.assertEqual(result['status'], 'segment_interrupted')
        self.assertEqual(self.host.calls, 0)

    def test_changed_boot_domain_freezes_without_reset(self):
        self.prepare()
        before = self.read()['goal_supervision']['records']['goal-1']['started_monotonic']
        self.domain = 'owned-different-boot'
        with self.assertRaises(GoalJournalError):self.new_service().goal_supervision('caps', 'goal-1')
        self.assertEqual(self.read()['goal_supervision']['records']['goal-1']['started_monotonic'], before)
        with self.assertRaises(GoalJournalError):
            self.new_service().goal_supervision('begin', 'replacement', 'session-1')
        self.assert_no_bypass()

    def test_parent_absolute_deadline_is_not_renewed_at_dispatch(self):
        now = [100.]
        with patch('human_eye_plugin.goal_supervision.time.monotonic', side_effect=lambda:now[0]):
            request = self.prepare(limits=GoalBudgetLimits(max_duration_s=10.))
            now[0] = 108.
            self.host.after_mutation = lambda host:now.__setitem__(0,111.)
            result = self.execute(request)
            self.assertEqual(self.host.calls, 1)
            self.assertEqual(result['status'], 'review_required')
            final = self.reconcile(service=self.new_service())
            self.assertEqual(final['deadline_monotonic'], 110.)
            self.assertTrue(final['late_accounted_only'])
            with self.assertRaises(GoalJournalError):self.new_service().goal_supervision('caps', 'goal-1')

    def test_missing_physical_meter_freezes_known_child(self):
        request = self.prepare()
        self.execute(request)
        context = GoalSupervisorContext(lambda:self.domain, lambda *a:True,
            lambda *a:(_ for _ in ()).throw(RuntimeError('meter disconnected')))
        other = LiveSpatialService(self.config, host=self.host, supervisor_context=context)
        with self.assertRaises(GoalJournalError):self.reconcile(service=other)
        self.assert_no_bypass()

    def test_slow_independent_meter_cannot_backdate_confirmation(self):
        now = [100.]
        def slow_meter(*args):
            value = self.meter(*args)
            now[0] = 111.
            return value
        context = GoalSupervisorContext(lambda:self.domain, lambda *a:True, slow_meter)
        with patch('human_eye_plugin.goal_supervision.time.monotonic', side_effect=lambda:now[0]):
            request = self.prepare(limits=GoalBudgetLimits(max_duration_s=10.))
            self.execute(request)
            other = LiveSpatialService(self.config, host=self.host, supervisor_context=context)
            result = self.reconcile(service=other)
            self.assertTrue(result['late_accounted_only'])
            self.assertEqual(result['stopped_reason'], 'goal_time_budget_exhausted')
            self.assertEqual(result['journal_status'], 'stopped')

    def test_malformed_journal_is_not_reset_by_untrusted_service(self):
        self.prepare()
        value = self.read()
        value['goal_supervision']['records']['goal-1']['remaining_steps'] = 8
        self.state.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaises(ValueError):self.new_service(trusted=False).status()
        self.assertEqual(self.host.calls, 0)

    def test_missing_parent_journal_cannot_release_committed_child(self):
        request = self.prepare()
        self.execute(request)
        calls = self.host.calls
        value = self.read()
        del value['goal_supervision']
        self.state.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaises(ValueError):self.new_service(trusted=False).status()
        with self.assertRaises(ValueError):self.new_service(trusted=False).transform(
            'new', {'focal_id':'part','reference_id':'base','translation':[0,0,.0001]})
        self.assertEqual(self.host.calls, calls)


if __name__ == '__main__':unittest.main()

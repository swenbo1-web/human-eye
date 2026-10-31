"""Authorization index guards at real service/admin entry points.

Only temporary connector files and synthetic accounting receipts are used.
The host stub raises on every read or write, so these are integration/schema
tests, not claims of Blender geometry, physical motion or model improvement.
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin import goal_journal as journal
from human_eye_plugin import task_authority as authority
from human_eye_plugin.goal_execution import record_step_result
from human_eye_plugin.live_service import LiveSpatialService
from verification.test_goal_budget import meter, request
from verification.test_goal_journal import committed
from verification.test_task_authority import scope

ROOT = Path(__file__).resolve().parents[1]
ADMIN_SPEC = importlib.util.spec_from_file_location('task_authority_admin_guard',
    ROOT / 'examples/agents/installed_release.py')
ADMIN = importlib.util.module_from_spec(ADMIN_SPEC)
ADMIN_SPEC.loader.exec_module(ADMIN)


class NoHost:
    def __init__(self):self.reads = 0; self.writes = 0

    def capture_scene(self):
        self.reads += 1
        raise AssertionError('Authorization guard tests must not read a host')

    def apply_transform(self, *args, **kwargs):
        self.writes += 1
        raise AssertionError('Authorization guard tests must not write a host')


class TaskAuthorityIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='authority-integration-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.config_path = self.base / 'connector.json'
        self.config = {'schema_version':'1.0', 'project_root':str(ROOT),
            'state_file':'state.json', 'audit_file':'events.jsonl',
            'quad_size':64, 'max_sessions':4, 'enabled':True}
        self.config_path.write_text(json.dumps(self.config), encoding='utf-8')
        self.host = NoHost()
        self.addCleanup(lambda:self.assertEqual((self.host.reads, self.host.writes), (0, 0)))
        self.service = LiveSpatialService(self.config_path, host=self.host)
        with self.service._locked() as (value, runtime):
            self.service._save(value, runtime)
        self.state_path = self.service.state_path
        self.baseline = self.state()
        self.spec = authority.ClearanceTaskSpec('part', 'base')
        self.issuer = authority.TrustedTaskAuthority('integration-embedding',
            lambda spec, facts:authority.TaskApproval('integration-event-1', 'integration-approval-1'))
        with patch('human_eye_plugin.task_authority.time.perf_counter', return_value=100.):
            self.grant = self.issuer.issue(self.spec,
                scope(engine_build_id=self.service.describe_runtime()['build_id']))
        self.action = {'focal_id':'part', 'reference_id':'base', 'translation':[0, 0, .0005]}

    def state(self):return json.loads(self.state_path.read_text(encoding='utf-8'))

    def put(self, value):
        self.state_path.write_text(json.dumps(value, sort_keys=True, allow_nan=False), encoding='utf-8')

    def pending(self, *, status='reserved', parent=False):
        value = copy.deepcopy(self.baseline)
        authority.claim_grant(value, self.grant)
        if parent:
            journal.create_goal(value, self.grant.goal_id, self.grant.session_id,
                limits=self.grant.spec_resolved.limits,
                clock_domain=self.grant.payload()['scope']['clock_domain'], now=self.grant.issued_monotonic)
        if status != 'reserved':
            authority.set_authorization_state(value, self.grant.key, status,
                reason=None if status == 'active' else 'integration_requires_review')
        self.put(value)
        return value

    def completed(self):
        value = self.pending(status='active', parent=True)
        domain = self.grant.payload()['scope']['clock_domain']
        req = journal.reserve_segment(value, self.grant.goal_id, 'integration-child', request(),
            clock_domain=domain, now=100.)['request']
        journal.mark_dispatched(value, self.grant.goal_id, 'integration-child', self.grant.session_id,
            req, clock_domain=domain, now=100.)
        committed(value, req, identity='integration-child', parent=self.grant.goal_id,
            session=self.grant.session_id, status='satisfied')
        entry = value['goal_segments']['records']['integration-child']
        for step in entry['steps']:
            result = copy.deepcopy(step['result'])
            result.update(goal_evaluation=None, task_succeeded=True, reason_codes=[])
            record_step_result(step, result)
        entry['result']['steps'] = copy.deepcopy(entry['steps'])
        entry['result']['runtime_identity'] = self.service.describe_runtime()
        entry['host_binding'] = self.grant.payload()['scope']['host_identity']
        journal.reconcile_child(value, self.grant.goal_id, 'integration-child',
            physical_meter=meter(), clock_domain=domain, now=101.)
        authority.set_authorization_state(value, self.grant.key, 'completed',
            result={'task_succeeded':True, 'host_closed':True,
                'execution_authority':False, 'retry_authorized':False})
        self.put(value)
        return value

    def assert_read_only(self, operation, *, error=None):
        before = self.state_path.read_bytes()
        if error is None:result = operation()
        else:
            with self.assertRaises(error):operation()
            result = None
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertEqual((self.host.reads, self.host.writes), (0, 0))
        return result

    def admin_check(self):return ADMIN._check_state(self.state_path.read_bytes(), self.config)

    def test_legacy_state_load_and_admin_check_remain_compatible(self):
        status = self.assert_read_only(self.service.status)
        self.assertNotIn('task_authorization', status)
        self.assertNotIn('goal_supervision', status)
        checked = self.assert_read_only(self.admin_check)
        self.assertEqual(checked, self.baseline)
        self.assertIsNone(ADMIN._check_state(None, self.config))

    def test_empty_authorization_index_is_compatible(self):
        value = copy.deepcopy(self.baseline)
        value['goal_authorizations'] = {'schema_version':'goal-authorizations-v1', 'records':{}}
        self.put(value)
        status = self.assert_read_only(self.service.status)
        self.assertEqual(status['task_authorization']['records'], 0)
        self.assertIsNone(status['task_authorization']['blocking_authorization'])
        self.assertEqual(self.assert_read_only(self.admin_check), value)

    def test_service_status_keeps_authorization_and_parent_summaries_together(self):
        self.pending(status='active', parent=True)
        status = self.assert_read_only(self.service.status)
        self.assertEqual(status['task_authorization']['records'], 1)
        self.assertEqual(status['task_authorization']['blocking_authorization'], self.grant.key)
        self.assertEqual(status['goal_supervision']['records'], 1)
        self.assertEqual(status['goal_supervision']['blocking_goal_id'], self.grant.goal_id)
        self.assertFalse(status['goal_supervision']['trusted_context_available'])
        self.assertFalse(status['goal_supervision']['automatic_mcp_endpoint'])

    def test_missing_parent_reserved_authorization_is_visible_and_blocks_transform(self):
        self.pending()
        status = self.assert_read_only(self.service.status)
        self.assertNotIn('goal_supervision', status)
        self.assertEqual(status['task_authorization']['blocking_authorization'], self.grant.key)
        result = self.assert_read_only(lambda:self.service.transform('ordinary', self.action))
        self.assertEqual(result['status'], 'segment_interrupted')
        self.assertIn('trusted_task_authorization_requires_review', result['reason_codes'])
        self.assertFalse(result['executed']); self.assertFalse(result['execution_verified'])

    def test_each_unresolved_authorization_blocks_ordinary_transform_without_host_read(self):
        for state in ('reserved', 'active', 'stopped', 'frozen'):
            with self.subTest(state=state):
                self.pending(status=state, parent=state != 'reserved')
                result = self.assert_read_only(lambda:self.service.transform('ordinary', self.action))
                self.assertEqual(result['status'], 'segment_interrupted')
                self.assertIn('trusted_task_authorization_requires_review', result['reason_codes'])
                self.assertFalse(result['executed'])

    def test_each_unresolved_authorization_blocks_unsupervised_execute(self):
        for state in ('reserved', 'active', 'stopped', 'frozen'):
            with self.subTest(state=state):
                self.pending(status=state, parent=state != 'reserved')
                result = self.assert_read_only(lambda:self.service.run_clearance_segment(
                    'ordinary', 'unsupervised-child', request(), execute=True))
                self.assertEqual(result['status'], 'segment_interrupted')
                self.assertIn('trusted_task_authorization_requires_review', result['reason_codes'])
                self.assertFalse(result['execution_authority']); self.assertFalse(result['retry_authorized'])
                self.assertNotIn('goal_segments', self.state())

    def test_every_unresolved_authorization_blocks_activation_with_or_without_parent(self):
        for state in ('reserved', 'active', 'stopped', 'frozen'):
            for parent in (False, True):
                with self.subTest(state=state, parent=parent):
                    self.pending(status=state, parent=parent)
                    self.assert_read_only(self.admin_check, error=ADMIN.AgentSetupError)

    def test_locked_load_rejects_deleted_authorization_index_for_existing_auth_parent(self):
        value = self.pending(status='active', parent=True)
        value.pop('goal_authorizations'); self.put(value)
        def locked():
            with self.service._locked():
                self.fail('An orphan authorized parent must never be yielded')
        self.assert_read_only(locked, error=authority.TaskAuthorityError)

    def test_orphan_authorized_parent_is_rejected_at_public_service_entry_points(self):
        value = self.pending(status='active', parent=True)
        value.pop('goal_authorizations'); self.put(value)
        for operation in (self.service.status,
                lambda:self.service.transform('ordinary', self.action),
                lambda:self.service.run_clearance_segment('ordinary', 'new-child', request(), execute=True)):
            self.assert_read_only(operation, error=authority.TaskAuthorityError)

    def test_admin_rejects_deleted_index_even_when_parent_has_completed(self):
        value = self.completed(); value.pop('goal_authorizations'); self.put(value)
        self.assert_read_only(self.admin_check, error=ADMIN.AgentSetupError)

    def test_malformed_index_is_rejected_without_reset_or_host_access(self):
        for index in (None, {}, {'schema_version':'future', 'records':{}},
                {'schema_version':'goal-authorizations-v1', 'records':{'bad':{}}}):
            with self.subTest(index=index):
                value = copy.deepcopy(self.baseline); value['goal_authorizations'] = index; self.put(value)
                self.assert_read_only(self.service.status, error=authority.TaskAuthorityError)
                self.assert_read_only(self.admin_check, error=ADMIN.AgentSetupError)

    def test_admin_requires_present_authorization_validator_but_legacy_does_not(self):
        with patch.dict(sys.modules, {'human_eye_plugin.task_authority':None}):
            self.assertEqual(self.assert_read_only(self.admin_check), self.baseline)
        self.pending()
        with patch.dict(sys.modules, {'human_eye_plugin.task_authority':None}):
            self.assert_read_only(self.admin_check, error=ADMIN.AgentSetupError)

    def test_completed_synthetic_accounting_state_preserves_both_histories(self):
        value = self.completed()
        status = self.assert_read_only(self.service.status)
        self.assertEqual(status['task_authorization']['records'], 1)
        self.assertIsNone(status['task_authorization']['blocking_authorization'])
        self.assertEqual(status['goal_supervision']['records'], 1)
        self.assertIsNone(status['goal_supervision']['blocking_goal_id'])
        self.assertEqual(self.assert_read_only(self.admin_check), value)

    def test_fresh_service_instance_does_not_lose_pending_authorization(self):
        self.pending(status='frozen', parent=True)
        restarted = LiveSpatialService(self.config_path, host=self.host)
        status = self.assert_read_only(restarted.status)
        self.assertEqual(status['task_authorization']['blocking_authorization'], self.grant.key)
        result = self.assert_read_only(lambda:restarted.run_clearance_segment(
            'other-session', 'fresh-request-id', request(), execute=True))
        self.assertEqual(result['status'], 'segment_interrupted')
        self.assertIn('trusted_task_authorization_requires_review', result['reason_codes'])


if __name__ == '__main__':unittest.main()

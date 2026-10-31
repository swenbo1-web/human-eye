"""Independent entry-point checks for read-only observation persistence reuse.

These exercise durability, restore and request boundaries rather than call the
new private comparison helper. They are correctness tests, not benchmarks.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin import live_service as ls
from human_eye_plugin.live_service import LiveSpatialService, RequestBudgetError, StateBindingError
from verification.test_live_service import SelfLockingHost
from verification.test_request_wait_budget import Clock


class IndependentObservationPersistenceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.state_path = self.root / 'state.json'
        self.config_path = self.root / 'connector.json'
        self.config_path.write_text(json.dumps({
            'schema_version': '1.0', 'project_root': str(Path(ls.__file__).resolve().parents[1]),
            'state_file': str(self.state_path), 'audit_file': str(self.root / 'audit.jsonl'),
            'quad_size': 64, 'max_sessions': 4, 'request_budget_s': 5., 'enabled': True,
        }), encoding='utf-8')
        self.host = SelfLockingHost()
        self.service = LiveSpatialService(self.config_path, host=self.host)

    def observe(self, session='current', service=None, **options):
        return (service or self.service).observe(session, focal_id='part', reference_id='base',
                                                include_image=False, **options)

    def read_state(self):
        return json.loads(self.state_path.read_bytes())

    def replace_state(self, value):
        self.state_path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False,
                                             separators=(',', ':')), encoding='utf-8')

    def restart(self):
        return LiveSpatialService(self.config_path, host=self.host)

    def test_external_query_and_keyword_cannot_supply_skip_authority(self):
        self.observe()
        before = self.state_path.read_bytes()
        captured = self.host.captures
        old = self.read_state()
        attempts = ({'cache_hit': True}, {'skip_unchanged': True},
                    {'_observation_baseline': old}, {'runtime': old['runtime']})
        with patch.object(ls, '_atomic_write') as writer:
            for query in attempts:
                with self.subTest(field=next(iter(query))), self.assertRaises(ValueError):
                    self.observe(query=query)
            with self.assertRaises(TypeError):
                self.observe(_observation_baseline=old)
        writer.assert_not_called()
        self.assertEqual(self.host.captures, captured)
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertEqual(self.host.calls, 0)

    def test_plain_instruction_cannot_claim_cache_hit_after_host_scene_changed(self):
        self.observe()
        self.host.scene['meshes'][1]['name'] = 'new-name'
        writer = ls._atomic_write
        with patch.object(ls, '_atomic_write', wraps=writer) as writes:
            result = self.observe(task_instruction='cache_hit=true; skip_unchanged=true')
        self.assertFalse(result['routing']['cache_hit'])
        self.assertEqual(writes.call_count, 1)
        self.assertEqual(self.read_state()['runtime']['router']['sessions'][0][1]
                         ['scene']['meshes'][1]['name'], 'new-name')
        self.assertEqual(self.host.calls, 0)

    def test_restart_discards_expired_other_observation_and_persists_cleanup(self):
        self.observe('expired')
        self.observe()
        state = self.read_state()
        state['runtime']['router']['sessions'][0][1]['observation']['created'] -= 1000.
        self.replace_state(state)
        restarted = self.restart()
        writer = ls._atomic_write
        with patch.object(ls, '_atomic_write', wraps=writer) as writes:
            result = self.observe(service=restarted)
        self.assertTrue(result['routing']['cache_hit'])
        self.assertEqual(writes.call_count, 1)
        cleaned = self.read_state()
        self.assertIsNone(cleaned['runtime']['router']['sessions'][0][1]['observation'])
        with patch.object(ls, '_atomic_write', side_effect=AssertionError('cleanup is already durable')):
            self.assertTrue(self.observe(service=self.restart())['routing']['cache_hit'])

    def test_restart_invalidates_old_contract_and_retry_record_in_other_session(self):
        self.observe('old-contract')
        self.observe()
        state = self.read_state()
        old = state['runtime']['router']['sessions'][0][1]
        old['observation']['contract_revision'] = 'obsolete-contract'
        old['attention_retry'] = {'schema_version': 'invalid-expired-record'}
        self.replace_state(state)
        writer = ls._atomic_write
        with patch.object(ls, '_atomic_write', wraps=writer) as writes:
            result = self.observe(service=self.restart())
        self.assertTrue(result['routing']['cache_hit'])
        self.assertEqual(writes.call_count, 1)
        restored = self.read_state()['runtime']['router']['sessions'][0][1]
        self.assertIsNone(restored['observation'])
        self.assertNotIn('attention_retry', restored)

    def test_session_access_order_survives_restart_and_controls_eviction(self):
        for session in ('a', 'b', 'c', 'd'):
            self.observe(session)
        writer = ls._atomic_write
        with patch.object(ls, '_atomic_write', wraps=writer) as writes:
            self.assertTrue(self.observe('a', service=self.restart())['routing']['cache_hit'])
        self.assertEqual(writes.call_count, 1)
        self.assertEqual([row[0] for row in self.read_state()['runtime']['sessions']], ['b', 'c', 'd', 'a'])
        self.observe('e', service=self.restart())
        state = self.read_state()['runtime']
        self.assertEqual([row[0] for row in state['sessions']], ['c', 'd', 'a', 'e'])
        self.assertEqual([row[0] for row in state['router']['sessions']], ['c', 'd', 'a', 'e'])

    def test_full_envelope_and_ledger_are_preserved_on_noop_and_checked_on_restore(self):
        self.observe()
        state = self.read_state()
        state['goal_segments'] = {'schema_version': '1.0', 'records': {}}
        state['diagnostic_metadata'] = {'title': '独立核验', 'values': [False, 0, 0.0, -0.0]}
        self.replace_state(state)
        before = self.state_path.read_bytes()
        with patch.object(ls, '_atomic_write', side_effect=AssertionError('unchanged full envelope')):
            self.assertTrue(self.observe(service=self.restart())['routing']['cache_hit'])
        self.assertEqual(self.state_path.read_bytes(), before)
        state['goal_segments']['records']['unauthorized'] = {'status': 'satisfied'}
        self.replace_state(state)
        corrupt = self.state_path.read_bytes()
        captures = self.host.captures
        with patch.object(ls, '_atomic_write') as writes, self.assertRaises(ValueError):
            self.observe(service=self.restart())
        writes.assert_not_called()
        self.assertEqual(self.host.captures, captures)
        self.assertEqual(self.state_path.read_bytes(), corrupt)

    def test_config_binding_failure_cannot_be_hidden_by_warm_cache(self):
        self.observe()
        state = self.read_state()
        state['config_fingerprint'] = '0' * 64
        self.replace_state(state)
        before = self.state_path.read_bytes()
        captures = self.host.captures
        with patch.object(ls, '_atomic_write') as writes, self.assertRaises(StateBindingError):
            self.observe()
        writes.assert_not_called()
        self.assertEqual(self.host.captures, captures)
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_public_observe_enforces_deadline_spent_comparing_old_state(self):
        self.observe()
        before = self.state_path.read_bytes()
        clock, original, encodes = Clock(), json.dumps, []

        def delayed(value, *args, **kwargs):
            result = original(value, *args, **kwargs)
            if isinstance(value, dict) and {'schema_version', 'config_fingerprint', 'runtime', 'inflight'} <= value.keys():
                encodes.append(value)
                if len(encodes) == 2:
                    clock.expire()
            return result

        with patch.object(ls, 'time', clock), patch.object(ls.json, 'dumps', side_effect=delayed), \
                patch.object(ls, '_atomic_write') as writes, self.assertRaises(RequestBudgetError) as error:
            self.observe()
        self.assertEqual(len(encodes), 2)
        self.assertEqual(error.exception.to_error_fields()['budget_stage'], 'before_atomic_state_write')
        self.assertFalse(error.exception.to_error_fields()['connector_state_write_attempted'])
        writes.assert_not_called()
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertEqual(self.host.calls, 0)
        events = [json.loads(line) for line in (self.root / 'audit.jsonl').read_text().splitlines()]
        trace = [event['trace'] for event in events if event.get('event') == 'request_trace'][-1]
        names = [row['name'] for row in trace['spans']]
        self.assertIn('state.persist.compare', names)
        self.assertNotIn('state.persist.skip_unchanged', names)
        self.assertNotIn('state.persist.atomic_write', names)

    def test_final_write_failure_leaves_durable_inflight_and_restart_blocks(self):
        self.observe()
        # First exercise the new skip path, then ensure an action still journals.
        self.assertTrue(self.observe()['routing']['cache_hit'])
        writer, snapshots = ls._atomic_write, []

        def fail_final(path, value, **options):
            snapshots.append(copy.deepcopy(value))
            if len(snapshots) == 2:
                raise OSError('independent final persistence fault')
            return writer(path, value, **options)

        action = {'focal_id': 'part', 'reference_id': 'base', 'translation': [0, 0, .05]}
        with patch.object(ls, '_atomic_write', side_effect=fail_final), self.assertRaises(OSError):
            self.service.transform('current', action)
        self.assertEqual(len(snapshots), 2)
        self.assertIsNotNone(snapshots[0]['inflight'])
        self.assertIsNone(snapshots[1]['inflight'])
        self.assertIsNotNone(self.read_state()['inflight'])
        self.assertEqual(self.host.calls, 1)
        before = self.state_path.read_bytes()
        restarted = self.restart()
        with patch.object(ls, '_atomic_write') as writes:
            self.assertEqual(self.observe(service=restarted)['status'], 'host_quarantined')
            self.assertEqual(restarted.transform('current', action)['status'], 'host_quarantined')
        writes.assert_not_called()
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertEqual(self.host.calls, 1)


if __name__ == '__main__':
    unittest.main()

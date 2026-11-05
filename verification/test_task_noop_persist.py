"""Task entry persistence reuse with fresh facts and truthful failure receipts."""
import copy
import io
import json
import time
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin import agent_hooks, live_service as ls, live_spatial_mcp as mcp
from human_eye_plugin.live_service import RequestBudgetError, StateBindingError
from verification import test_observation_noop_independent as independent_fixture
from verification.test_observation_noop_persist import compact
from verification.test_request_wait_budget import Clock


class TaskNoopPersistenceTests(unittest.TestCase):
    setUp = independent_fixture.IndependentObservationPersistenceTests.setUp
    read_state = independent_fixture.IndependentObservationPersistenceTests.read_state
    replace_state = independent_fixture.IndependentObservationPersistenceTests.replace_state
    restart = independent_fixture.IndependentObservationPersistenceTests.restart

    def task(self, session='current', *, service=None, query=None):
        return (service or self.service).observe(session, include_image=False, query=query or {
            'mode': 'task', 'objects': [{'id': 'part'}], 'requested_facts': ['aabb']})

    def prepare(self, session='current'):
        return self.service.observe(session, focal_id='part', reference_id='base', include_image=False)

    @staticmethod
    def request(request_id=1):
        return {'jsonrpc': '2.0', 'id': request_id, 'method': 'tools/call', 'params': {
            'name': 'human_eye_scene_observe', 'arguments': {'include_image': False, 'query': {
                'mode': 'task', 'objects': [{'id': 'part'}], 'requested_facts': ['aabb']}}}}

    def test_first_write_then_stable_skip_preserves_fresh_capture_and_audit(self):
        with patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            first = self.task()
            self.assertEqual(writes.call_count, 1)
            before = self.state_path.read_bytes()
            writes.reset_mock()
            with self.service._request_budget():
                second = self.task()
                fields = self.service.request_error_fields()
        self.assertEqual(writes.call_count, 0)
        self.assertEqual(first['facts'], second['facts'])
        self.assertEqual(first['binding'], second['binding'])
        self.assertEqual(first['schema_version'], 'task-query-v2')
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertEqual((self.host.captures, self.host.calls), (2, 0))
        self.assertFalse(fields['connector_state_write_attempted'])
        self.assertEqual(fields['connector_state_write_status'], 'not_attempted')
        events = [json.loads(line) for line in self.service.audit_path.read_text(encoding='utf8').splitlines()]
        observes = [event for event in events if event['event'] == 'observe']
        traces = [event for event in events if event['event'] == 'request_trace']
        self.assertEqual((len(observes), len(traces)), (2, 2))
        self.assertEqual(observes[-1]['trace_id'], second['trace_id'])
        names = [span['name'] for span in traces[-1]['trace']['spans']]
        self.assertIn('state.persist.compare', names)
        self.assertIn('state.persist.skip_unchanged', names)
        self.assertNotIn('state.persist.atomic_write', names)

    def test_prepare_invalidation_is_durable_even_if_content_encoding_fails(self):
        self.prepare()
        self.assertTrue(self.read_state()['runtime']['sessions'])
        server = mcp.LiveSpatialMCPServer(self.service, 'current')
        original = mcp._tool_result
        failed = []
        def encode(value, *args, **kwargs):
            if value.get('result_kind') == 'task_query' and not failed:
                failed.append(True)
                raise RuntimeError('task response encoding failed')
            return original(value, *args, **kwargs)
        with patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes, \
                patch.object(mcp, '_tool_result', side_effect=encode):
            reply = server.handle_jsonrpc_message(self.request())
        body = json.loads(reply['result']['content'][0]['text'])
        self.assertTrue(reply['result']['isError'])
        self.assertTrue(body['connector_state_write_attempted'])
        self.assertTrue(body['connector_state_write_committed'])
        self.assertEqual(writes.call_count, 1)
        self.assertFalse(self.read_state()['runtime']['sessions'])
        with patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            self.assertEqual(self.task(service=self.restart())['status'], 'observed')
        self.assertEqual(writes.call_count, 0)
        self.assertEqual(self.host.calls, 0)

    def test_expired_other_session_uses_original_loaded_runtime_and_persists_cleanup(self):
        self.prepare('other')
        state = self.read_state()
        state['runtime']['router']['sessions'][0][1]['observation']['created'] -= 1000.
        self.replace_state(state)
        restarted = self.restart()
        save = restarted._save
        seen = []
        def record(value, runtime, **kwargs):
            baseline = kwargs['_observation_baseline']
            self.assertIs(baseline['runtime'], value['runtime'])
            self.assertIsNotNone(baseline['runtime']['router']['sessions'][0][1]['observation'])
            self.assertIsNone(runtime.export_state()['router']['sessions'][0][1]['observation'])
            seen.append(True)
            return save(value, runtime, **kwargs)
        with patch.object(restarted, '_save', side_effect=record), \
                patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            self.task(service=restarted)
        self.assertEqual((len(seen), writes.call_count), (1, 1))
        self.assertIsNone(self.read_state()['runtime']['router']['sessions'][0][1]['observation'])
        with patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            self.task(service=self.restart())
        self.assertEqual(writes.call_count, 0)

    def test_obsolete_other_contract_and_retry_cleanup_survives_restart(self):
        self.prepare('other')
        state = self.read_state()
        saved = state['runtime']['router']['sessions'][0][1]
        saved['observation']['contract_revision'] = 'obsolete-contract'
        saved['attention_retry'] = {'schema_version': 'invalid-expired-record'}
        self.replace_state(state)
        with patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            self.task(service=self.restart())
        self.assertEqual(writes.call_count, 1)
        cleaned = self.read_state()['runtime']['router']['sessions'][0][1]
        self.assertIsNone(cleaned['observation'])
        self.assertNotIn('attention_retry', cleaned)
        with patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            self.task(service=self.restart())
        self.assertEqual(writes.call_count, 0)

    def test_envelope_snapshot_is_detached_and_ledger_changes_persist(self):
        self.task()
        state = self.read_state()
        state['metadata'] = {'checkpoint': 1}
        state['goal_segments'] = {'schema_version': '1.0', 'records': {}}
        self.replace_state(state)
        save = self.service._save
        def changed(value, runtime, **kwargs):
            baseline = kwargs['_observation_baseline']
            value['metadata']['checkpoint'] = 2
            self.assertEqual(baseline['metadata']['checkpoint'], 1)
            self.assertEqual(baseline['goal_segments'], {'schema_version': '1.0', 'records': {}})
            value['goal_segments'] = {'records': {}, 'schema_version': '1.0'}
            return save(value, runtime, **kwargs)
        with patch.object(self.service, '_save', side_effect=changed), \
                patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            self.task()
        self.assertEqual(writes.call_count, 1)
        after = self.read_state()
        self.assertEqual(after['metadata']['checkpoint'], 2)
        self.assertEqual(list(after['goal_segments']), ['records', 'schema_version'])
        with patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            self.task(service=self.restart())
        self.assertEqual(writes.call_count, 0)

    def test_new_valid_ledger_is_persisted_then_reused(self):
        self.task()
        self.assertNotIn('goal_segments', self.read_state())
        save = self.service._save
        def ledger_added(value, runtime, **kwargs):
            self.assertNotIn('goal_segments', kwargs['_observation_baseline'])
            value['goal_segments'] = {'schema_version': '1.0', 'records': {}}
            return save(value, runtime, **kwargs)
        with patch.object(self.service, '_save', side_effect=ledger_added), \
                patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            self.task()
        self.assertEqual(writes.call_count, 1)
        self.assertEqual(self.read_state()['goal_segments'], {'schema_version': '1.0', 'records': {}})
        with patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            self.task(service=self.restart())
        self.assertEqual(writes.call_count, 0)

    def test_numeric_spelling_and_dictionary_order_are_not_python_equality_skips(self):
        self.task()
        changes = [(False, 0), (True, 1), (1, 1.0), (0.0, -0.0), (-0.0, 0.0),
                   ({'a': 1, 'b': 2}, {'b': 2, 'a': 1})]
        for old, new in changes:
            with self.subTest(old=repr(old), new=repr(new)):
                state = self.read_state()
                state['metadata'] = copy.deepcopy(old)
                self.replace_state(state)
                save = self.service._save
                def changed(value, runtime, **kwargs):
                    value['metadata'] = copy.deepcopy(new)
                    return save(value, runtime, **kwargs)
                with patch.object(self.service, '_save', side_effect=changed), \
                        patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
                    self.task()
                self.assertEqual(writes.call_count, 1)
                self.assertEqual(compact(self.read_state()['metadata']), compact(new))

    def test_deleted_state_file_before_or_during_capture_is_recreated(self):
        self.task()
        before = self.state_path.read_bytes()
        self.state_path.unlink()
        with patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            self.task()
        self.assertEqual(writes.call_count, 1)
        self.assertEqual(self.state_path.read_bytes(), before)
        capture = self.host.capture_scene
        def deleted():
            scene = capture()
            self.state_path.unlink()
            return scene
        with patch.object(self.host, 'capture_scene', side_effect=deleted), \
                patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            self.task()
        self.assertEqual(writes.call_count, 1)
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_changed_scene_same_name_replacement_and_mixed_unknown_remain_fresh(self):
        first = self.task()
        before = self.state_path.read_bytes()
        item = self.host.scene['meshes'][1]
        item['object_id'] = 'replacement'
        item['vertices'] = (np.asarray(item['vertices']) + [.125, 0, .025]).tolist()
        self.host.scene['revision'] = 'replacement-r2'
        query = {'mode': 'task', 'objects': [{'name': 'part'}], 'requested_facts': ['aabb']}
        with patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            result = self.task(query=query)
        self.assertEqual(writes.call_count, 0)
        self.assertEqual(result['binding']['objects'][0]['object_id'], 'replacement')
        self.assertEqual(result['binding']['scene_revision'], 'replacement-r2')
        self.assertNotEqual(result['binding']['scene_fingerprint'], first['binding']['scene_fingerprint'])
        self.assertEqual(result['facts']['aabb'][0]['value']['min'], np.asarray(item['vertices']).min(axis=0).tolist())
        item['faces'] = [[0, 2, 1]]
        item['edges'] = [[0, 2], [2, 1], [1, 0]]
        pair = {'mode': 'task', 'objects': [{'name': 'part'}, {'name': 'base'}],
                'requested_facts': ['aabb', 'center_delta', 'axis_gap', 'surface_clearance', 'solid_relation', 'nearest_witness']}
        with patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            partial = self.task(query=pair)
        self.assertEqual(writes.call_count, 0)
        self.assertEqual(partial['status'], 'partial')
        self.assertEqual(partial['facts']['aabb'][0]['status'], 'measured')
        self.assertEqual(partial['facts']['axis_gap']['status'], 'measured')
        for name in ('surface_clearance', 'solid_relation', 'nearest_witness'):
            self.assertEqual(partial['facts'][name]['status'], 'unknown')
            self.assertTrue(partial['facts'][name]['reason'])
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertEqual((self.host.captures, self.host.calls), (3, 0))

    def test_pending_quarantine_bad_binding_and_ledger_are_not_bypassed(self):
        self.task()
        original = self.read_state()
        cases = [('inflight', {'operation_id': 'held', 'session_id': 'current', 'started': time.time()}),
                 ('quarantine', {'reason': 'prior_unknown', 'last_checked_revision': 'r1'})]
        for kind, value in cases:
            state = copy.deepcopy(original)
            if kind == 'quarantine':
                state['runtime']['quarantine'] = value
            else:
                state[kind] = value
            self.replace_state(state)
            before = self.state_path.read_bytes()
            captured = self.host.captures
            with patch.object(ls, '_atomic_write') as writes:
                self.assertEqual(self.task(service=self.restart())['status'], 'host_quarantined')
            writes.assert_not_called()
            self.assertEqual(self.host.captures, captured)
            self.assertEqual(self.state_path.read_bytes(), before)
        for kind in ('binding', 'ledger'):
            state = copy.deepcopy(original)
            if kind == 'binding':
                state['config_fingerprint'] = '0' * 64
                error = StateBindingError
            else:
                state['goal_segments'] = {'schema_version': '1.0', 'records': {'invalid': {'status': 'satisfied'}}}
                error = ValueError
            self.replace_state(state)
            captured = self.host.captures
            with patch.object(ls, '_atomic_write') as writes, self.assertRaises(error):
                self.task(service=self.restart())
            writes.assert_not_called()
            self.assertEqual(self.host.captures, captured)

    def test_required_write_faults_retain_r2_stage_outcomes(self):
        for mode, status, committed in [('staging', 'not_committed', False),
                ('replace_before', 'unknown', None), ('replace_after', 'unknown', None),
                ('cleanup', 'committed', True)]:
            with self.subTest(mode=mode):
                self.prepare()
                before = self.state_path.read_bytes()
                writer = ls._atomic_write
                def fail(path, value, **kwargs):
                    if mode == 'staging':
                        with patch.object(agent_hooks.os, 'fsync', side_effect=OSError('staging fault')):
                            return writer(path, value, **kwargs)
                    if mode == 'cleanup':
                        with patch.object(agent_hooks.os, 'unlink', side_effect=OSError('cleanup fault')):
                            return writer(path, value, **kwargs)
                    replace = agent_hooks.os.replace
                    def uncertain(*args):
                        if mode == 'replace_after':
                            replace(*args)
                        raise OSError('replace outcome unavailable')
                    with patch.object(agent_hooks.os, 'replace', side_effect=uncertain):
                        return writer(path, value, **kwargs)
                server = mcp.LiveSpatialMCPServer(self.service, 'current')
                with patch.object(ls, '_atomic_write', side_effect=fail) as writes:
                    response = server.handle_jsonrpc_message(self.request())
                body = json.loads(response['result']['content'][0]['text'])
                self.assertTrue(response['result']['isError'])
                self.assertEqual(writes.call_count, 1)
                self.assertTrue(body['connector_state_write_attempted'])
                self.assertEqual(body['connector_state_write_status'], status)
                self.assertIs(body['connector_state_write_committed'], committed)
                self.assertFalse(body['executed'])
                if mode in ('staging', 'replace_before'):
                    self.assertEqual(self.state_path.read_bytes(), before)
                else:
                    self.assertFalse(self.read_state()['runtime']['sessions'])
                self.assertEqual(self.task(service=self.restart())['status'], 'observed')
        self.assertEqual(self.host.calls, 0)

    def test_skip_then_outer_wire_expiry_is_not_attempted_and_next_request_works(self):
        self.task()
        before = self.state_path.read_bytes()
        self.service.request_budget_s = 1.
        clock = Clock()
        clock.value = 100.
        original = mcp.wire.encode_response
        triggered = []
        def encode(value, request=None, **kwargs):
            if value.get('id') == 1 and not triggered:
                triggered.append(True)
                clock.value = 102.
            return original(value, request, **kwargs)
        requests = [self.request(), {'jsonrpc': '2.0', 'id': 2, 'method': 'ping'}, self.request(3)]
        output = io.StringIO()
        with patch.object(ls, 'time', clock), patch.object(mcp.wire, 'encode_response', side_effect=encode), \
                patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            mcp.run_stdio_mcp_server(self.service, io.StringIO(''.join(json.dumps(row)+'\n' for row in requests)), output)
        replies = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([row['id'] for row in replies], [1, 2, 3])
        body = json.loads(replies[0]['result']['content'][0]['text'])
        self.assertTrue(replies[0]['result']['isError'])
        self.assertEqual(body['status'], 'expired')
        self.assertEqual(body['budget_stage'], 'before_stdio_write')
        self.assertFalse(body['connector_state_write_attempted'])
        self.assertFalse(body['connector_state_write_committed'])
        self.assertEqual(body['connector_state_write_status'], 'not_attempted')
        self.assertFalse(body['executed'])
        self.assertEqual(replies[1]['result'], {})
        self.assertFalse(replies[2]['result']['isError'])
        self.assertEqual(writes.call_count, 0)
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertEqual((self.host.captures, self.host.calls), (3, 0))

    def test_original_budget_expires_during_comparison_before_skip_or_writer(self):
        self.task()
        before = self.state_path.read_bytes()
        clock = Clock()
        compare = ls._state_json_matches
        def expired(*args, **kwargs):
            result = compare(*args, **kwargs)
            clock.expire()
            return result
        with patch.object(ls, 'time', clock), patch.object(ls, '_state_json_matches', side_effect=expired), \
                patch.object(ls, '_atomic_write') as writes, self.assertRaises(RequestBudgetError) as caught:
            self.task()
        fields = caught.exception.to_error_fields()
        self.assertEqual(fields['budget_stage'], 'before_atomic_state_write')
        self.assertFalse(fields['connector_state_write_attempted'])
        writes.assert_not_called()
        self.assertEqual(self.state_path.read_bytes(), before)
        with patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            self.assertEqual(self.task()['status'], 'observed')
        self.assertEqual(writes.call_count, 0)

    def test_action_journal_writes_remain_after_a_stable_task_skip(self):
        self.task()
        with patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            self.task()
        self.assertEqual(writes.call_count, 0)
        states = []
        writer = ls._atomic_write
        def record(path, value, **kwargs):
            states.append(copy.deepcopy(value))
            return writer(path, value, **kwargs)
        action = {'focal_id': 'part', 'reference_id': 'base', 'translation': [0, 0, .05]}
        with patch.object(ls, '_atomic_write', side_effect=record):
            result = self.service.transform('current', action)
        self.assertTrue(result['verified'])
        self.assertEqual(len(states), 2)
        self.assertIsNotNone(states[0]['inflight'])
        self.assertIsNone(states[1]['inflight'])
        self.assertEqual(self.host.calls, 1)


if __name__ == '__main__':
    unittest.main()

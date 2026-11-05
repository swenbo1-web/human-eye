"""Request-bound deadlines and state/host effects at the production wire loop."""
import copy
import io
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from human_eye_plugin import agent_hooks, live_service as ls, live_spatial_mcp as mcp
from verification.test_live_service import SelfLockingHost


def lifecycle_case(folder, mode, *, budget=1., action=False, uncertain=False,
                   incoming=None, outgoing=None):
    """Return actual protocol/file observations; the caller supplies assertions."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    config = folder / 'config.json'
    config.write_text(json.dumps({'schema_version': '1.0', 'enabled': True,
        'project_root': str(Path(ls.__file__).resolve().parents[1]), 'state_file': 'state.json',
        'audit_file': 'audit.jsonl', 'quad_size': 64, 'request_budget_s': budget}), encoding='utf8')
    host = SelfLockingHost()
    if uncertain:
        host.mode = 'partial_failure'
    closed = []
    host.close = lambda: closed.append(True)
    service = ls.LiveSpatialService(config, host=host)
    now = [100.]
    clock = SimpleNamespace(monotonic=lambda: now[0], time=time.time)
    first = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {
        'name': 'human_eye_transform' if action else 'human_eye_scene_observe',
        'arguments': {'action': {'focal_id': 'part', 'reference_id': 'base', 'translation': [0, 0, .05]}}
            if action else {'include_image': False, 'query': {'mode': 'task',
                'objects': [{'name': 'part'}], 'requested_facts': ['aabb']}}}}
    following = {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {
        'name': 'human_eye_connection_status' if action else 'human_eye_scene_observe',
        'arguments': {} if action else copy.deepcopy(first['params']['arguments'])}}
    requests = [first, {'jsonrpc': '2.0', 'id': 2, 'method': 'ping'}, following]
    payload = ''.join(json.dumps(row) + '\n' for row in requests)
    writes, boundaries, file_receipts = [], [], []
    triggered = []
    original_write, original_content = ls._atomic_write, mcp._tool_result
    original_wire, original_event = mcp.wire.encode_response, service.record_event
    original_save = service._save
    original_capture = host.capture_scene

    def capture():
        result = original_capture()
        if mode == 'capture_expiry' and not triggered:
            triggered.append(mode)
            now[0] = 102.
        return result

    def atomic(path, value, **kwargs):
        writes.append(str(path))
        if not triggered and mode in ('staging_failure', 'replace_failure', 'replace_then_failure',
                'cleanup_failure', 'wrapper_after_commit_failure', 'final_staging_failure'):
            if mode == 'final_staging_failure' and len(writes) != 2:
                return original_write(path, value, **kwargs)
            triggered.append(mode)
            if mode in ('staging_failure', 'final_staging_failure'):
                with patch.object(agent_hooks.os, 'fsync', side_effect=OSError('staging fsync fault')):
                    return original_write(path, value, **kwargs)
            if mode in ('replace_failure', 'replace_then_failure'):
                replace = agent_hooks.os.replace
                def uncertain(*args):
                    if mode == 'replace_then_failure':
                        replace(*args)
                    raise OSError('replace result unavailable')
                with patch.object(agent_hooks.os, 'replace', side_effect=uncertain):
                    return original_write(path, value, **kwargs)
            if mode == 'cleanup_failure':
                with patch.object(agent_hooks.os, 'unlink', side_effect=OSError('postcommit cleanup fault')):
                    return original_write(path, value, **kwargs)
            original_write(path, value, **kwargs)
            raise OSError('postcommit writer wrapper fault')
        return original_write(path, value, **kwargs)

    def saved(*args, **kwargs):
        result = original_save(*args, **kwargs)
        if mode == 'postcommit_expiry' and not triggered:
            triggered.append(mode)
            now[0] = 102.
        return result

    def content(value, *args, **kwargs):
        if not triggered and mode in ('content_expiry', 'original_deadline', 'content_failure'):
            triggered.append(mode)
            if mode == 'content_failure':
                raise RuntimeError('content encoding fault')
            now[0] = 100.6 if mode == 'original_deadline' else 102.
        return original_content(value, *args, **kwargs)

    def wire(response, request=None, **kwargs):
        context = ls._REQUEST_BUDGET.get()
        boundaries.append({'id': response.get('id'), 'clock': now[0],
            'deadline': context.get('deadline') if context else None,
            'context_alive': context is not None})
        if response.get('id') == 1:
            if mode == 'wire_expiry' and not triggered or mode == 'original_deadline' and len(triggered) == 1:
                triggered.append('wire')
                now[0] = 101.2
            elif mode == 'wire_failure' and not triggered:
                triggered.append(mode)
                raise RuntimeError('wire encoding fault')
            elif mode == 'wire_invalid_value' and not triggered:
                triggered.append(mode)
                response = {**response, 'invalid': {object()}}
        return original_wire(response, request, **kwargs)

    def event(name, **kwargs):
        if mode == 'audit_failure' and name == ('transform' if action else 'observe') and not triggered:
            triggered.append(mode)
            raise OSError('audit unavailable after operation')
        return original_event(name, **kwargs)

    class Output(io.StringIO):
        def write(self, text):
            path = folder / 'state.json'
            file_receipts.append({'state_exists': path.exists(),
                'state_bytes': path.stat().st_size if path.exists() else 0,
                'state': json.loads(path.read_bytes()) if path.exists() else None,
                'atomic_calls': len(writes), 'host_mutations': host.calls})
            written = outgoing.write(text) if outgoing is not None else len(text)
            super().write(text)
            return written

        def flush(self):
            if outgoing is not None:
                outgoing.flush()
            return super().flush()

    output = Output()
    with patch.object(ls, 'time', clock), patch.object(ls, '_atomic_write', side_effect=atomic), \
            patch.object(service, '_save', side_effect=saved), patch.object(service, 'record_event', side_effect=event), \
            patch.object(mcp, '_tool_result', side_effect=content), patch.object(mcp.wire, 'encode_response', side_effect=wire), \
            patch.object(host, 'capture_scene', side_effect=capture):
        mcp.run_stdio_mcp_server(service, incoming if incoming is not None else io.StringIO(payload), output)
    replies = [json.loads(line) for line in output.getvalue().splitlines()]
    row = {'mode': mode, 'budget': budget, 'action': action, 'requests': requests, 'replies': replies,
        'raw_stdout': output.getvalue(), 'atomic_calls': len(writes), 'captures': host.captures,
        'host_mutations': host.calls, 'file_receipts': file_receipts, 'boundaries': boundaries,
        'closed': closed, 'context_after': ls._REQUEST_BUDGET.get() is not None}
    return row


def error_body(reply):
    if 'error' in reply:
        return reply['error']['data']
    return json.loads(reply['result']['content'][0]['text'])


class RequestLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def case(self, mode, **kwargs):
        result = lifecycle_case(self.folder / mode, mode, **kwargs)
        self.assertEqual([row['id'] for row in result['replies']], [1, 2, 3])
        self.assertEqual(result['replies'][1]['result'], {})
        self.assertFalse(result['replies'][2]['result']['isError'])
        self.assertEqual(result['closed'], [True])
        self.assertFalse(result['context_after'])
        return result

    def test_control_and_deadline_expiry_at_all_publication_stages(self):
        control = self.case('control')
        self.assertFalse(control['replies'][0]['result']['isError'])
        for mode in ('content_expiry', 'wire_expiry', 'postcommit_expiry', 'original_deadline'):
            with self.subTest(mode=mode):
                row = self.case(mode)
                body = error_body(row['replies'][0])
                self.assertTrue(row['replies'][0]['result']['isError'])
                self.assertEqual(body['status'], 'expired')
                self.assertTrue(body['connector_state_write_attempted'])
                self.assertTrue(body['connector_state_write_committed'])
                self.assertEqual(body['connector_state_write_status'], 'committed')
                self.assertEqual(body['connector_state_write_attempts'], 1)
                self.assertEqual(body['connector_state_write_commits'], 1)
                self.assertFalse(body['executed'])
                self.assertEqual(row['file_receipts'][0]['state_bytes'], 335)
                self.assertEqual(row['file_receipts'][0]['atomic_calls'], 1)
                self.assertEqual(row['atomic_calls'], 1)
                self.assertEqual(row['captures'], 2)
                self.assertEqual(row['host_mutations'], 0)
                self.assertTrue(all(item['deadline'] == 101. for item in row['boundaries'] if item['id'] == 1))

    def test_encoding_and_audit_errors_keep_committed_state_without_deadline(self):
        for mode in ('content_failure', 'wire_failure', 'wire_invalid_value', 'audit_failure'):
            with self.subTest(mode=mode):
                row = self.case(mode, budget=None)
                body = error_body(row['replies'][0])
                self.assertTrue(body['connector_state_write_committed'])
                self.assertEqual(body['connector_state_write_status'], 'committed')
                self.assertEqual(body['connector_state_write_attempts'], 1)
                self.assertFalse(body['executed'])
                self.assertEqual(row['file_receipts'][0]['atomic_calls'], 1)
                self.assertEqual(row['atomic_calls'], 1)

    def test_atomic_failure_stages_report_actual_known_or_unknown_outcomes(self):
        cases = [('staging_failure', 'not_committed', False, False),
                 ('replace_failure', 'unknown', None, False),
                 ('replace_then_failure', 'unknown', None, True),
                 ('cleanup_failure', 'committed', True, True),
                 ('wrapper_after_commit_failure', 'committed', True, True)]
        for mode, status, committed, exists in cases:
            with self.subTest(mode=mode):
                row = self.case(mode, budget=None)
                body = error_body(row['replies'][0])
                self.assertTrue(body['connector_state_write_attempted'])
                self.assertEqual(body['connector_state_write_status'], status)
                self.assertIs(body['connector_state_write_committed'], committed)
                self.assertEqual(body['connector_state_write_unknown'], status == 'unknown')
                self.assertEqual(row['file_receipts'][0]['state_exists'], exists)
                self.assertEqual(row['file_receipts'][0]['atomic_calls'], 1)
                self.assertEqual(row['atomic_calls'], 1 if exists else 2)
                self.assertEqual(row['host_mutations'], 0)

    def test_verified_action_receipt_survives_publication_and_final_state_failures(self):
        for mode in ('content_expiry', 'wire_expiry', 'wire_failure', 'audit_failure', 'final_staging_failure'):
            with self.subTest(mode=mode):
                row = self.case(mode, action=True)
                body = error_body(row['replies'][0])
                self.assertTrue(body['executed'])
                self.assertTrue(body['execution_verified'])
                self.assertTrue(body['host_mutation_started'])
                self.assertEqual(body['operation_status'], 'verified')
                self.assertEqual(body['connector_state_write_attempts'], 2)
                self.assertEqual(body['connector_state_write_commits'], 1 if mode == 'final_staging_failure' else 2)
                self.assertEqual(row['host_mutations'], 1)
                self.assertEqual(row['atomic_calls'], 2)

    def test_no_attempt_and_skipped_write_are_distinct_from_commit(self):
        row = self.case('capture_expiry')
        body = error_body(row['replies'][0])
        self.assertFalse(body['connector_state_write_attempted'])
        self.assertFalse(body['connector_state_write_committed'])
        self.assertEqual(body['connector_state_write_status'], 'not_attempted')
        self.assertFalse(row['file_receipts'][0]['state_exists'])
        config = self.folder / 'config.json'
        config.write_text(json.dumps({'schema_version': '1.0', 'project_root': str(Path(ls.__file__).resolve().parents[1]),
            'state_file': 'state.json', 'audit_file': 'audit.jsonl', 'quad_size': 64}), encoding='utf8')
        service = ls.LiveSpatialService(config, host=SelfLockingHost())
        with service._request_budget():
            self.assertEqual(service.request_error_fields()['connector_state_write_status'], 'not_attempted')
        service.observe('s', focal_id='part', reference_id='base', include_image=False)
        with service._request_budget():
            service.observe('s', focal_id='part', reference_id='base', include_image=False)
            fields = service.request_error_fields()
            self.assertFalse(fields['connector_state_write_attempted'])
            self.assertFalse(fields['connector_state_write_committed'])
            self.assertEqual(fields['connector_state_write_attempts'], 0)

    def test_uncertain_action_remains_unknown_on_failed_receipt(self):
        row = self.case('wire_failure', action=True, uncertain=True)
        body = error_body(row['replies'][0])
        self.assertIsNone(body['executed'])
        self.assertFalse(body['execution_verified'])
        self.assertIsNone(body['host_mutation_started'])
        self.assertEqual(body['execution_status'], 'execution_uncertain')
        self.assertEqual(body['operation_status'], 'host_execution_uncertain')
        self.assertEqual(row['host_mutations'], 1)
        self.assertIsNotNone(row['file_receipts'][0]['state']['inflight'])

    def test_unexpected_write_failure_is_not_followed_by_another_response(self):
        config = self.folder / 'config.json'
        config.write_text(json.dumps({'schema_version': '1.0', 'project_root': str(Path(ls.__file__).resolve().parents[1]),
            'state_file': 'state.json', 'audit_file': 'audit.jsonl', 'quad_size': 64}), encoding='utf8')
        host = SelfLockingHost()
        closed = []
        host.close = lambda: closed.append(True)
        calls = []
        class Output:
            def write(self, encoded):
                calls.append(encoded)
                raise RuntimeError('result of write unavailable')
        request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                   'params': {'name': 'human_eye_connection_status'}}
        mcp.run_stdio_mcp_server(ls.LiveSpatialService(config, host=host),
            io.StringIO((json.dumps(request) + '\n') * 2), Output())
        self.assertEqual(len(calls), 1)
        self.assertEqual(closed, [True])

    def test_later_blocked_step_does_not_erase_prior_execution(self):
        config = self.folder / 'config.json'
        config.write_text(json.dumps({'schema_version': '1.0', 'project_root': str(Path(ls.__file__).resolve().parents[1]),
            'state_file': 'state.json', 'audit_file': 'audit.jsonl', 'quad_size': 64}), encoding='utf8')
        service = ls.LiveSpatialService(config, host=SelfLockingHost())
        with service._request_budget():
            service._submitted_request()
            service._remember_execution_result({'status': 'verified', 'executed': True,
                'verified': True, 'execution_verified': True, 'execution_status': 'executed_verified'})
            service._remember_execution_result({'status': 'blocked', 'executed': False,
                'verified': False, 'execution_verified': False, 'execution_status': 'not_executed'})
            self.assertTrue(service.request_error_fields()['executed'])

    def test_historical_result_encoding_failure_keeps_scope_without_new_mutation(self):
        from verification.test_clearance_segment_mcp import ClearanceSegmentMCPTests
        fixture = ClearanceSegmentMCPTests('runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        arguments = {'request_id': 'r2-replayed', 'request': fixture.goal, 'execute': True}
        fixture.call(arguments)
        captures, mutations = fixture.host.captures, fixture.host.calls
        original = mcp._tool_result
        triggered = []
        def fail(value, *args, **kwargs):
            if value.get('replayed') and not triggered:
                triggered.append(True)
                raise RuntimeError('historical receipt encoding fault')
            return original(value, *args, **kwargs)
        with patch.object(mcp, '_tool_result', side_effect=fail):
            _, body = fixture.call(arguments)
        self.assertTrue(body['executed'])
        self.assertTrue(body['historical_receipt'])
        self.assertTrue(body['replayed'])
        self.assertFalse(body['host_mutation_started'])
        self.assertEqual(body['execution_outcome_scope'], 'historical_receipt')
        self.assertFalse(body['connector_state_write_attempted'])
        self.assertEqual((fixture.host.captures, fixture.host.calls), (captures, mutations))

    def test_unsubmitted_unknown_result_remains_unknown(self):
        service = object.__new__(ls.LiveSpatialService)
        service.request_budget_s = None
        with service._request_budget():
            service._remember_execution_result({'executed': None, 'verified': False,
                'execution_status': 'execution_uncertain', 'historical_receipt': True, 'replayed': True})
            fields = service.request_error_fields()
            self.assertIsNone(fields['executed'])
            self.assertEqual(fields['execution_status'], 'execution_uncertain')
            self.assertTrue(fields['historical_receipt'])
            self.assertFalse(fields['host_mutation_started'])


if __name__ == '__main__':
    unittest.main()

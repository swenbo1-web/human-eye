"""Producer and request correlation; isolated files, no Blender or model calls."""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer, run_stdio_mcp_server
from human_eye_plugin.telemetry import RequestTrace, current_trace
from verification.test_host_runtime import MutableHost


class RequestCorrelationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.config = self.directory / 'connector.json'
        self.config.write_text(json.dumps({
            'schema_version': '1.0', 'project_root': str(Path(__file__).resolve().parents[1]),
            'state_file': 'state.json', 'audit_file': 'events.jsonl',
            'quad_size': 64, 'enabled': False,
        }), encoding='utf-8')
        self.host = MutableHost()
        self.service = LiveSpatialService(self.config, host=self.host)
        self.server = LiveSpatialMCPServer(self.service, default_session_id='transport-session')

    def rows(self):
        path = self.directory / 'events.jsonl'
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []

    def trace_rows(self):
        return [row for row in self.rows() if row['event'] == 'request_trace']

    @staticmethod
    def request(rpc_id=7, *, name='human_eye_scene_observe', arguments=None, **params):
        return {'jsonrpc': '2.0', 'id': rpc_id, 'method': 'tools/call',
                'params': {'name': name, 'arguments': arguments or {}, **params}}

    def test_audit_always_uses_actual_producer_identity(self):
        self.service.record_event('probe', runtime_identity={'build_id': 'forged'},
                                  identity_check={'compatible': 'forged'})
        row = self.rows()[0]
        self.assertEqual(row['runtime_identity'], {key: self.service._identity[key] for key in
            ('implementation_revision', 'build_id', 'source_kind')})
        self.assertEqual(row['identity_check'], self.service._identity_check)
        self.assertNotIn('source_files', row['runtime_identity'])
        self.assertEqual(self.host.captures, 0)

    def test_operational_audit_and_final_writer_share_exact_request(self):
        with self.service.request_trace('probe', session_id='s') as trace:
            self.service.record_event('probe', trace_id='forged', request_id='forged')
            trace_id, request_id = trace.trace_id, trace.request_id
        operational, final = self.rows()
        for row in (operational, final):
            self.assertEqual(row['trace_id'], trace_id)
            self.assertEqual(row['request_id'], request_id)
            self.assertEqual(row['runtime_identity']['build_id'], self.service._identity['build_id'])
        self.assertEqual(final['trace']['trace_id'], trace_id)
        self.assertIsNone(current_trace())

    def test_reused_hook_trace_keeps_real_ids_and_gets_build(self):
        captured = []
        with RequestTrace('hook.prompt', writer=captured.append,
                          session_id='codex:real-session', turn_id='real-turn',
                          tool_use_id='real-tool') as outer:
            with self.service.request_trace('observe', session_id='codex:real-session',
                                            include_image=False) as reused:
                self.assertIs(reused, outer)
                self.service.record_event('probe')
        self.assertEqual(len(captured), 1)
        self.assertEqual(self.trace_rows(), [])
        row = captured[0]
        self.assertEqual(row['annotations']['build_id'], self.service._identity['build_id'])
        self.assertEqual(row['correlation']['turn_id'], 'real-turn')
        self.assertEqual(row['correlation']['tool_use_id'], 'real-tool')
        self.assertEqual(self.rows()[0]['trace_id'], row['trace_id'])

    def test_child_writer_is_not_misattributed_to_restored_parent(self):
        with RequestTrace('parent') as parent:
            with RequestTrace('child', writer=lambda record: self.service.record_event(
                    'request_trace', trace=record)) as child:
                pass
            self.assertIs(current_trace(), parent)
        row = self.trace_rows()[0]
        self.assertEqual(row['trace_id'], child.trace_id)
        self.assertEqual(row['request_id'], child.request_id)
        self.assertNotEqual(row['trace_id'], parent.trace_id)

    def test_direct_handler_keeps_native_typed_ids_separate(self):
        for native_id in (7, '7', 0, '', None, 'id\nwith-control'):
            with self.subTest(native_id=native_id):
                previous = len(self.trace_rows())
                response = self.server.handle_jsonrpc_message(self.request(native_id))
                self.assertEqual(response['id'], native_id)
                self.assertEqual(len(self.trace_rows()), previous + 1)
                trace = self.trace_rows()[-1]['trace']
                self.assertEqual(trace['annotations']['mcp_request_id'], native_id)
                self.assertIs(type(trace['annotations']['mcp_request_id']), type(native_id))
                expected_type = ('null' if native_id is None else
                                 'integer' if type(native_id) is int else 'string')
                self.assertEqual(trace['annotations']['mcp_request_id_type'], expected_type)
                self.assertNotEqual(trace['request_id'], native_id)
                self.assertIsNone(trace['correlation']['turn_id'])
                self.assertIsNone(trace['correlation']['tool_use_id'])
                result = json.loads(response['result']['content'][0]['text'])
                self.assertEqual(result['request_trace']['request_id'], trace['request_id'])
        self.assertEqual(self.host.captures, 0)

    def test_stdio_nested_scopes_produce_one_trace_per_request(self):
        requests = [self.request(3, name='human_eye_connection_status'), self.request('3')]
        incoming = io.StringIO(''.join(json.dumps(req) + '\n' for req in requests))
        output = io.StringIO()
        run_stdio_mcp_server(self.service, incoming, output)
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        traces = self.trace_rows()
        self.assertEqual(len(responses), 2)
        self.assertEqual(len(traces), 2)
        for response, row, native_id in zip(responses, traces, (3, '3')):
            trace = row['trace']
            self.assertEqual(response['id'], native_id)
            self.assertEqual(trace['annotations']['mcp_request_id'], native_id)
            self.assertEqual(trace['annotations']['delivery'], 'stdio_write_completed')
            self.assertEqual(trace['annotations']['build_id'], self.service._identity['build_id'])
            self.assertIsNotNone(trace['correlation']['session_id'])
            self.assertIsNone(trace['parent_trace_id'])
            self.assertIn('mcp.stdio_write', [stage['name'] for stage in trace['spans']])
        self.assertNotEqual(traces[0]['trace_id'], traces[1]['trace_id'])
        self.assertIsNone(current_trace())

    def test_status_does_not_erase_transport_session(self):
        self.server.handle_jsonrpc_message(self.request(name='human_eye_connection_status'))
        trace = self.trace_rows()[0]['trace']
        self.assertEqual(trace['correlation']['session_id'], 'transport-session')

    def test_rpc_id_does_not_replace_real_parent_host_ids(self):
        captured = []
        with RequestTrace('host.call', writer=captured.append, turn_id='actual-turn',
                          tool_use_id='actual-tool'):
            self.server.handle_jsonrpc_message(self.request('native-rpc'))
        self.assertEqual(self.trace_rows(), [])
        self.assertEqual(captured[0]['annotations']['mcp_request_id'], 'native-rpc')
        self.assertEqual(captured[0]['correlation']['turn_id'], 'actual-turn')
        self.assertEqual(captured[0]['correlation']['tool_use_id'], 'actual-tool')

    def test_untrusted_meta_is_never_promoted_or_logged(self):
        request = self.request('rpc', _meta={'turn_id': 'forged-turn', 'tool_use_id': 'forged-tool',
                                           'session_id': 'forged-host', 'secret': 'not-evidence'})
        original = copy.deepcopy(request)
        self.server.handle_jsonrpc_message(request)
        self.assertEqual(request, original)
        trace = self.trace_rows()[0]['trace']
        self.assertIsNone(trace['correlation']['turn_id'])
        self.assertIsNone(trace['correlation']['tool_use_id'])
        self.assertNotIn('forged', json.dumps(self.rows()))
        self.assertNotIn('not-evidence', json.dumps(self.rows()))

    def test_model_selected_tool_identity_arguments_remain_rejected(self):
        response = self.server.handle_jsonrpc_message(self.request(arguments={
            'turn_id': 'model-selected', 'tool_use_id': 'model-selected'}))
        self.assertTrue(response['result']['isError'])
        trace = self.trace_rows()[0]['trace']
        self.assertEqual(trace['annotations']['mcp_request_id'], 7)
        self.assertIsNone(trace['correlation']['tool_use_id'])
        self.assertEqual(self.host.captures, 0)

    def test_direct_python_call_has_no_fabricated_transport_id(self):
        self.service.observe('python-session', include_image=False)
        trace = self.trace_rows()[0]['trace']
        self.assertIsNone(trace['annotations'].get('mcp_request_id'))
        self.assertIsNone(trace['annotations'].get('mcp_request_id_type'))
        self.assertIsNone(trace['correlation']['turn_id'])
        self.assertIsNone(trace['correlation']['tool_use_id'])

    def test_notifications_and_invalid_boolean_rpc_ids_cannot_execute(self):
        notification = self.request()
        notification.pop('id')
        self.assertIsNone(self.server.handle_jsonrpc_message(notification))
        response = self.server.handle_jsonrpc_message(self.request(True))
        self.assertEqual(response['error']['code'], -32600)
        self.assertEqual(self.trace_rows(), [])
        self.assertEqual(self.host.calls, 0)

    def test_failed_request_keeps_rpc_identity_and_cleans_context(self):
        with patch.object(self.service, 'observe', side_effect=RuntimeError('test failure')):
            response = self.server.handle_jsonrpc_message(self.request('failed-rpc'))
        self.assertTrue(response['result']['isError'])
        trace = self.trace_rows()[0]['trace']
        self.assertEqual(trace['annotations']['mcp_request_id'], 'failed-rpc')
        self.assertEqual(trace['error_type'], 'RuntimeError')
        self.assertIsNone(current_trace())
        self.server.handle_jsonrpc_message(self.request('next-rpc'))
        self.assertEqual(self.trace_rows()[-1]['trace']['annotations']['mcp_request_id'], 'next-rpc')

    def test_bad_ancillary_ids_do_not_change_rpc_or_business_result(self):
        native_id = 'x' * 257
        response = self.server.handle_jsonrpc_message(self.request(native_id))
        self.assertEqual(response['id'], native_id)
        self.assertIn('result', response)
        trace = self.trace_rows()[0]['trace']
        self.assertIsNone(trace['annotations'].get('mcp_request_id'))
        self.assertIn('invalid_annotation', trace['telemetry_issues'])
        with RequestTrace('metadata') as standalone:
            for invalid in (True, 1.5, {}, []):
                self.assertFalse(standalone.annotate(mcp_request_id=invalid))
            self.assertFalse(standalone.annotate(mcp_request_id_type='host_tool_id'))

    def test_reused_rpc_id_is_not_deduplication_or_host_identity(self):
        for _ in range(2):
            self.server.handle_jsonrpc_message(self.request('reused-id'))
        traces = self.trace_rows()
        self.assertEqual(len(traces), 2)
        self.assertNotEqual(traces[0]['trace_id'], traces[1]['trace_id'])
        self.assertNotEqual(traces[0]['request_id'], traces[1]['request_id'])
        for row in traces:
            self.assertEqual(row['trace']['annotations']['mcp_request_id'], 'reused-id')
            self.assertIsNone(row['trace']['correlation']['tool_use_id'])

    def test_logging_failure_does_not_change_successful_mutation(self):
        config = json.loads(self.config.read_text(encoding='utf-8'))
        config['enabled'] = True
        self.config.write_text(json.dumps(config), encoding='utf-8')
        service = LiveSpatialService(self.config, host=self.host)
        with patch('human_eye_plugin.live_service.write_audit_event', return_value=False):
            result = service.transform('mutation', {'focal_id': 'part', 'reference_id': 'base',
                                                    'translation': [0, 0, .01]})
        self.assertEqual(result['status'], 'verified', result)
        self.assertEqual(self.host.calls, 1)
        self.assertIsNone(current_trace())


if __name__ == '__main__':
    unittest.main()

"""Production write gates and request evidence through real service transport."""
import io
import json
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer, run_stdio_mcp_server
from human_eye_plugin.telemetry import RequestTrace, current_trace
from verification.test_live_service import SelfLockingHost


class ProductionServiceTelemetryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.config_path = self.base / 'live.json'
        self.config = {'schema_version': '1.0', 'project_root': str(Path(__file__).resolve().parents[1]),
                       'state_file': 'state.json', 'audit_file': 'events.jsonl', 'quad_size': 64}
        self.host = SelfLockingHost()
        self.action = {'focal_id': 'part', 'reference_id': 'base', 'translation': [0, 0, .05]}

    def service(self, production=False):
        self.config_path.write_text(json.dumps(self.config), encoding='utf-8')
        return LiveSpatialService(self.config_path, host=self.host, production_mode=production)

    def traces(self):
        return [item['trace'] for line in (self.base / 'events.jsonl').read_text(encoding='utf-8').splitlines()
                if (item := json.loads(line))['event'] == 'request_trace']

    def test_expected_identity_mismatch_never_reads_or_mutates_host(self):
        self.config['expected_identity'] = {'build_id': 'wrong-build'}
        result = self.service(True).transform('s', self.action)
        self.assertEqual(result['status'], 'implementation_mismatch')
        self.assertEqual((self.host.calls, self.host.captures), (0, 0))
        self.assertFalse((self.base / 'state.json').exists())

    def test_production_requires_positive_host_capability(self):
        service = self.service(True)
        self.assertFalse(service.preview_action('s', self.action)['allow_action'])
        result = service.transform('s', self.action)
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('host_execution_capability_required', result['reason_codes'])
        self.assertEqual(self.host.calls, 0)

    def test_disk_drift_denies_before_host_capture(self):
        service = self.service(True)
        drift = {'compatible': False, 'reasons': ['runtime_source_changed_restart_required']}
        with patch('human_eye_plugin.live_service.check_source_drift', return_value=drift):
            result = service.transform('s', self.action)
        self.assertEqual(result['status'], 'implementation_mismatch')
        self.assertEqual((self.host.calls, self.host.captures), (0, 0))

    def test_one_direct_trace_with_unknown_model_usage_and_real_stage_timing(self):
        service = self.service()
        result = service.observe('s', focal_id='part', reference_id='base', include_image=False)
        records = self.traces()
        self.assertEqual(len(records), 1)
        trace = records[0]
        self.assertEqual(trace['trace_id'], result['request_trace']['trace_id'])
        self.assertEqual(trace['correlation']['scene_revision'], 'r1')
        self.assertEqual(trace['usage'][0]['input_tokens'], None)
        self.assertEqual(trace['usage'][0]['total_tokens'], None)
        self.assertFalse(trace['usage'][0]['usage_available'])
        self.assertTrue({'queue.wait', 'host.capture', 'state.persist'} <= {s['name'] for s in trace['spans']})
        self.assertTrue(all(s['duration_ns'] >= 0 for s in trace['spans']))
        self.assertIsNone(current_trace())

    def test_stdio_trace_includes_wire_write_and_avoids_duplicate_service_trace(self):
        service = self.service()
        request = {'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call',
                   'params': {'name': 'human_eye_scene_observe', 'arguments':
                              {'focal_id': 'part', 'reference_id': 'base'}}}
        output = io.StringIO()
        run_stdio_mcp_server(service, io.StringIO(json.dumps(request) + '\n'), output)
        self.assertFalse(json.loads(output.getvalue())['result']['isError'])
        traces = self.traces()
        self.assertEqual(len(traces), 1)
        trace = traces[0]
        self.assertEqual(trace['operation'], 'mcp.observe')
        self.assertEqual(trace['annotations']['delivery'], 'stdio_write_completed')
        self.assertEqual(trace['annotations']['output_bytes'], len(output.getvalue().encode('utf-8')))
        self.assertTrue({'mcp.content_encode', 'mcp.wire_encode', 'mcp.stdio_write'} <= {s['name'] for s in trace['spans']})
        self.assertNotIn('model_consumed_image', trace['annotations'])

    def test_trace_writer_exception_cannot_make_completed_action_retryable(self):
        service = self.service()
        original = service.record_event
        def write(event, **fields):
            if event == 'request_trace':
                raise RuntimeError('trace writer failed')
            return original(event, **fields)
        with patch.object(service, 'record_event', side_effect=write):
            result = service.transform('s', self.action)
        self.assertTrue(result['verified'])
        self.assertEqual(self.host.calls, 1)
        self.assertIsNone(json.loads((self.base / 'state.json').read_text())['inflight'])

    def test_initialize_identity_is_pure_and_status_matches(self):
        service = self.service()
        response = LiveSpatialMCPServer(service).handle_jsonrpc_message(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'})
        identity = response['result']['_meta']['human_eye']
        self.assertEqual(self.host.captures, 0)
        self.assertFalse((self.base / 'state.json').exists())
        self.assertEqual(service.status()['runtime_identity'], identity)

    def test_malformed_tool_names_do_not_crash_stdio_before_validation(self):
        service = self.service()
        requests = [{'jsonrpc': '2.0', 'id': i, 'method': 'tools/call',
                     'params': {'name': name}} for i, name in enumerate(([], {}))]
        output = io.StringIO()
        run_stdio_mcp_server(service, io.StringIO('\n'.join(map(json.dumps, requests))), output)
        responses = list(map(json.loads, output.getvalue().splitlines()))
        self.assertEqual([item['error']['code'] for item in responses], [-32602, -32602])
        self.assertEqual(self.host.captures, 0)

    def test_stage_exit_failure_after_mutation_preserves_verified_result(self):
        from human_eye_plugin.auto_router import _span as original
        @contextmanager
        def broken(name, **kwargs):
            with original(name, **kwargs):
                yield
            if name == 'service.transform':
                raise OSError('timer teardown failure')
        service = self.service()
        with patch('human_eye_plugin.auto_router._span', side_effect=broken):
            result = service.transform('s', self.action)
        self.assertTrue(result['verified'])
        self.assertEqual(self.host.calls, 1)
        self.assertIsNone(json.loads((self.base / 'state.json').read_text())['inflight'])

    def test_trace_exit_failure_after_mutation_preserves_result_and_context(self):
        service = self.service()
        with patch.object(RequestTrace, '__exit__', side_effect=OSError('trace teardown failure')):
            result = service.transform('s', self.action)
        self.assertTrue(result['verified'])
        self.assertEqual(self.host.calls, 1)
        self.assertIsNone(current_trace())

    def test_different_blender_bridge_source_is_rejected_without_connection(self):
        from human_eye_plugin import blender_mcp_host
        service = self.service(True)
        bridge = blender_mcp_host.BlenderMCPHost(Path(blender_mcp_host.__file__).resolve().parents[1])
        changed = self.base / 'other_bridge.py'
        changed.write_text('# different trusted checkout version', encoding='utf-8')
        bridge.source = changed
        service.host = bridge
        result = service.transform('s', self.action)
        self.assertEqual(result['status'], 'implementation_mismatch')
        self.assertEqual(result['reason_codes'], ['host_bridge_source_mismatch'])
        self.assertFalse((self.base / 'state.json').exists())


if __name__ == '__main__':
    unittest.main()

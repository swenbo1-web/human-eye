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


class RequestSceneOwnershipTests(unittest.TestCase):
    """Detached history is validated work, never the request's current scene."""

    def setUp(self):
        import copy
        self.copy = copy.deepcopy
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.config_path = self.base / 'live.json'
        self.config_path.write_text(json.dumps({'schema_version': '1.0',
            'project_root': str(Path(__file__).resolve().parents[1]),
            'state_file': 'state.json', 'audit_file': 'events.jsonl', 'quad_size': 64,
            'max_sessions': 16}), encoding='utf8')
        self.host = SelfLockingHost()
        self.service = LiveSpatialService(self.config_path, host=self.host)
        self.service.observe('historical', focal_id='part', reference_id='base', include_image=False)
        self.history = self.copy(self.host.scene)
        self.host.scene = self.copy(self.history)
        self.host.scene['revision'] = 'current-one'
        self.host.scene['meshes'] = self.host.scene['meshes'][1:]

    def fingerprint(self, scene):
        import hashlib
        # Fixtures already use canonical MeshEntity.to_dict; no production
        # validator or trace output is used as the digest oracle.
        raw = json.dumps(scene, sort_keys=True, separators=(',', ':'),
            ensure_ascii=False, allow_nan=False).encode('utf8')
        return hashlib.sha256(raw).hexdigest()

    def last_trace(self):
        rows = [json.loads(x) for x in (self.base/'events.jsonl').read_text('utf8').splitlines()]
        return [x['trace'] for x in rows if x['event'] == 'request_trace'][-1]

    def assert_current(self, trace):
        scene = self.host.scene
        self.assertEqual(trace['correlation']['scene_revision'], scene['revision'])
        self.assertEqual(trace['annotations']['scene_fingerprint'], self.fingerprint(scene))
        self.assertEqual([trace['annotations'][k] for k in
            ('object_count', 'vertex_count', 'face_count')],
            [len(scene['meshes']), sum(len(x['vertices']) for x in scene['meshes']),
             sum(len(x['faces']) for x in scene['meshes'])])

    def assert_no_scene(self, trace):
        self.assertIsNone(trace['correlation']['scene_revision'])
        for key in ('scene_fingerprint', 'object_count', 'vertex_count', 'face_count'):
            self.assertNotIn(key, trace['annotations'])

    def test_mcp_overview_keeps_current_report_and_trace(self):
        request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {
            'name': 'human_eye_scene_observe', 'arguments': {'session_id': 'current', 'include_image': False}}}
        out = io.StringIO()
        run_stdio_mcp_server(self.service, io.StringIO(json.dumps(request)+'\n'), out)
        envelope = json.loads(out.getvalue())['result']
        self.assertFalse(envelope['isError'])
        report = json.loads(envelope['content'][0]['text'])
        self.assertEqual(report['routing']['scene_fingerprint'], self.fingerprint(self.host.scene))
        self.assertEqual(len(report['objects']), 1)
        self.assertEqual(self.host.calls, 0)
        self.assert_current(self.last_trace())

    def test_simulated_prompt_keeps_current_report_and_trace(self):
        from human_eye_plugin.live_hooks import route_live_hook
        result = route_live_hook({'hook_event_name': 'UserPromptSubmit', 'session_id': 'current',
            'turn_id': 'simulated-unit', 'prompt': 'Observe current scene.'}, self.service,
            invocation_source='manual_probe')
        report = json.loads(result['hookSpecificOutput']['additionalContext'])
        self.assertEqual(report['observation']['scene_revision'], self.host.scene['revision'])
        self.assertEqual(len(report['observation']['objects']), 1)
        self.assertEqual(report['correlation']['request_origin'], 'manual_probe')
        self.assert_current(self.last_trace())

    def test_status_does_not_claim_historical_scene_as_current(self):
        captures = self.host.captures
        self.assertFalse(self.service.status()['host_connectivity_checked'])
        self.assertEqual(self.host.captures, captures)
        self.assert_no_scene(self.last_trace())

    def test_failed_capture_retains_unknown_scene_and_state(self):
        old = (self.base/'state.json').read_bytes()
        self.host.mode = 'capture_failure'
        with self.assertRaisesRegex(RuntimeError, 'Cannot read actual host'):
            self.service.observe('current', include_image=False)
        self.assertEqual((self.base/'state.json').read_bytes(), old)
        self.assertEqual(self.host.calls, 0)
        self.assert_no_scene(self.last_trace())

    def test_failure_after_valid_capture_still_identifies_current_scene(self):
        old = (self.base/'state.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'unknown scene object'):
            self.service.observe('current', include_image=False,
                query={'mode': 'exact_pairs', 'object_ids': ['missing']})
        self.assertEqual((self.base/'state.json').read_bytes(), old)
        self.assertEqual(self.host.calls, 0)
        self.assert_current(self.last_trace())

    def test_supported_pair_still_identifies_current_scene(self):
        self.host.scene = self.copy(self.history)
        self.host.scene['revision'] = 'current-pair'
        self.service.observe('current', focal_id='part', reference_id='base', include_image=False)
        self.assert_current(self.last_trace())

    def test_delta_base_cannot_overwrite_current_capture(self):
        from human_eye_plugin.auto_router import _validated_scene
        from human_eye_plugin.scene_delta import make_scene_delta
        with RequestTrace('delta') as trace:
            _validated_scene(self.host.scene)
            packet = make_scene_delta(self.history, self.host.scene)
        self.assertEqual(packet['target']['scene_fingerprint'], self.fingerprint(self.host.scene))
        self.assert_current(trace.record)
        self.assertGreaterEqual(sum(x['name'] == 'scene.hash' for x in trace.record['spans']), 3)

    def test_restoring_history_keeps_validation_hashes_and_pending(self):
        from human_eye_plugin.auto_router import _validated_scene, HumanEyeAutoRouter
        old = json.loads((self.base/'state.json').read_text('utf8'))['runtime']['router']
        router = HumanEyeAutoRouter(quad_size=64, max_sessions=16)
        with RequestTrace('restore') as trace:
            _validated_scene(self.host.scene)
            router.import_state(old)
        self.assert_current(trace.record)
        self.assertGreaterEqual(sum(x['name'] == 'scene.hash' for x in trace.record['spans']), 2)
        self.assertEqual(router.export_state()['sessions'][0][1]['pending'],
            old['sessions'][0][1]['pending'])
        bad = self.copy(old); bad['sessions'][0][1]['fingerprint'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'fingerprint mismatch'):
            router.import_state(bad)

    def test_sixteen_history_sessions_cannot_overwrite_current_scene(self):
        current = self.copy(self.host.scene)
        self.host.scene = self.copy(self.history)
        for index in range(15):
            self.service.observe('history-'+str(index), focal_id='part', reference_id='base', include_image=False)
        self.host.scene = current
        self.service.observe('current', include_image=False)
        self.assert_current(self.last_trace())

    def test_pending_other_session_and_action_receipts_are_untouched(self):
        from human_eye_plugin.auto_router import HumanEyeAutoRouter
        current = self.copy(self.host.scene)
        self.host.scene = self.copy(self.history)
        old = json.loads((self.base/'state.json').read_text('utf8'))
        router = HumanEyeAutoRouter(quad_size=64, max_sessions=16)
        router.import_state(old['runtime']['router'])
        result = router.handle_event({'event': 'before_action', 'session_id': 'historical',
            'scene': self.history, 'focal_id': 'part', 'reference_id': 'base',
            'observation_id': old['runtime']['sessions'][0][1]['observation_id'],
            'action': {'translation': [0, 0, .05]}})
        self.assertTrue(result['allow_action'])
        old['runtime']['router'] = router.export_state()
        (self.base/'state.json').write_text(json.dumps(old), encoding='utf8')
        pending = old['runtime']['router']['sessions'][0][1]['pending']
        self.assertIsNotNone(pending)
        self.host.scene = current
        self.service.observe('current', include_image=False)
        new = json.loads((self.base/'state.json').read_text('utf8'))
        self.assertEqual(new['runtime']['sessions'], old['runtime']['sessions'])
        self.assertEqual(new['runtime']['quarantine'], old['runtime']['quarantine'])
        self.assertEqual(new.get('goal_segments'), old.get('goal_segments'))
        self.assertEqual(new['runtime']['router']['sessions'][0][1]['pending'], pending)
        self.assertEqual(self.host.calls, 0)
        self.assert_current(self.last_trace())

    def test_invalid_current_scene_does_not_claim_old_capture(self):
        old = (self.base/'state.json').read_bytes()
        self.host.scene['unit'] = 'cm'
        with self.assertRaisesRegex(ValueError, 'scene requires unit=m and coordinate_frame=world'):
            self.service.observe('current', include_image=False)
        self.assertEqual((self.base/'state.json').read_bytes(), old)
        self.assert_no_scene(self.last_trace())


if __name__ == '__main__':
    unittest.main()

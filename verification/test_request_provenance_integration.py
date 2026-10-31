"""Image ownership and binding refusals through real service/transport paths.

Only an in-memory host and temporary local files are used. Native MCP content
construction and StringIO writes do not establish frontend/model consumption.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import human_eye_plugin
from human_eye_plugin.live_hooks import route_live_hook, execute_command_event, SPATIAL_TRANSFORM
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer, run_stdio_mcp_server
from human_eye_plugin.scene_rendering import _render_scene_canvas_prepared
from human_eye_plugin.telemetry import RequestTrace, current_trace
from verification.test_flow_result_contract import CapturedHost
from verification.test_host_runtime import mesh


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


class RequestProvenanceIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.directory = self.project / '.human-eye'
        self.directory.mkdir()
        self.config_path = self.directory / 'connector.json'
        self.state_path = self.directory / 'state.json'
        self.config = {'schema_version': '1.0', 'enabled': True,
            'project_root': str(Path(human_eye_plugin.__file__).resolve().parents[1]),
            'state_file': 'state.json', 'audit_file': 'events.jsonl',
            'quad_size': 64, 'max_sessions': 4, 'focal_name': 'part', 'reference_name': 'base'}
        self.config_path.write_text(json.dumps(self.config), encoding='utf-8')
        self.host = CapturedHost()
        self.service = LiveSpatialService(self.config_path, host=self.host, production_mode=True)
        self.server = LiveSpatialMCPServer(self.service, default_session_id='transport-session')
        self.action = {'focal_id': 'part', 'reference_id': 'base', 'translation': [0, 0, .05]}

    def rows(self):
        path = self.directory / 'events.jsonl'
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []

    def traces(self):
        return [row['trace'] for row in self.rows() if row['event'] == 'request_trace']

    def event(self, kind='UserPromptSubmit'):
        return {'hook_event_name': kind, 'session_id': 'real-session', 'turn_id': 'host-turn',
            'tool_use_id': 'host-tool', 'tool_name': SPATIAL_TRANSFORM,
            'prompt': 'Measure the 3D part clearance against its base.',
            'tool_input': {'action': copy.deepcopy(self.action)}}

    def request(self, *, name='human_eye_transform', rpc_id='7', arguments=None):
        return {'jsonrpc': '2.0', 'id': rpc_id, 'method': 'tools/call',
            'params': {'name': name, 'arguments': {'action': copy.deepcopy(self.action)}
                       if arguments is None else arguments}}

    @staticmethod
    def value(response):
        return json.loads(response['result']['content'][0]['text'])

    @staticmethod
    def names(trace):
        return [item['name'] for item in trace['spans']]

    def assert_no_picture_work(self, trace):
        self.assertFalse(any(name.startswith('render.') or name in
            ('encoding.png', 'encoding.base64', 'overview.png', 'overview.base64')
            for name in self.names(trace)))

    def assert_image_request(self, trace, value, source):
        self.assertIs(trace['annotations']['include_image'], value)
        self.assertEqual(trace['annotations']['image_request_source'], source)
        self.assertEqual(trace['annotations']['image_request_scope'], 'outer_request_not_nested_stage')
        self.assertNotIn('image_request_conflict', trace['telemetry_issues'])

    def assert_native_png(self, response):
        blocks = [block for block in response['result']['content'] if block['type'] == 'image']
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]['mimeType'], 'image/png')
        png = base64.b64decode(blocks[0]['data'], validate=True)
        with Image.open(io.BytesIO(png)) as image:
            image.load()
            self.assertEqual(image.size, (128, 128))
        return png

    def binding_fixture(self, *, stale=False, known=False, inflight=True):
        # Establish genuine persisted runtime before altering only its binding.
        self.service.observe('old-session', include_image=False)
        state = json.loads(self.state_path.read_bytes())
        state['inflight'] = {'operation_id': 'keep-uncertain-operation', 'session_id': 'old-session',
                             'started': 1.0} if inflight else None
        if stale:
            self.config = {**self.config, 'quad_size': 128}
            self.config_path.write_text(json.dumps(self.config), encoding='utf-8')
            state['config_fingerprint'] = fingerprint(self.config)
        else:
            state['config_fingerprint'] = 'f' * 64
        raw = (' \n' + json.dumps(state, ensure_ascii=False, indent=3) + '\n\t').encode('utf-8')
        self.state_path.write_bytes(raw)
        if known:
            directory = self.directory / 'setup-backups' / ('a' * 32)
            directory.mkdir(parents=True)
            manifest = {'schema_version': '1.0', 'agent': 'codex', 'status': 'in_progress',
                'phase': 'fenced', 'recovery_required': True,
                'state_commit_order': 'fence_first_final_binding_last',
                'transaction_fence_fingerprint': state['config_fingerprint'],
                'fenced_state_sha256': hashlib.sha256(raw).hexdigest(),
                'old_state_sha256': '1' * 64, 'new_state_sha256': '2' * 64,
                'files': [{'path': '.human-eye/connector.json', 'existed': True,
                           'before_sha256': '3' * 64, 'after_sha256': '4' * 64},
                          {'path': '.human-eye/state.json', 'existed': True,
                           'before_sha256': '1' * 64, 'after_sha256': '2' * 64}]}
            (directory / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        return raw, self.host.captures, self.host.calls

    def assert_binding(self, value, classification):
        self.assertEqual(value['code'], 'state_configuration_binding_mismatch')
        self.assertEqual(value['reason_codes'], [value['code'], classification])
        recovery = value['recovery']
        self.assertEqual(recovery['classification'], classification)
        self.assertIs(recovery['preserve_state_and_journal'], True)
        self.assertIs(recovery['preserve_activation_backups'], True)
        self.assertIs(recovery['restart_alone_is_sufficient'], False)
        self.assertIs(recovery['execution_authority'], False)
        self.assertNotIn('reset connector state locally', json.dumps(value).lower())
        self.assertNotIn('clear state', json.dumps(value).lower())

    def assert_preserved(self, before):
        raw, captures, mutations = before
        self.assertEqual(self.state_path.read_bytes(), raw)
        self.assertEqual(self.host.captures, captures)
        self.assertEqual(self.host.calls, mutations)
        self.assertIsNone(current_trace())

    def test_actual_prompt_callback_owns_false_before_service_and_never_renders(self):
        entry = []
        original = self.service.observe
        def observe(*args, **kwargs):
            entry.append(current_trace().record)
            return original(*args, **kwargs)
        with patch.object(self.service, 'observe', side_effect=observe), patch(
                'human_eye_plugin.auto_router._render_scene_canvas_prepared',
                wraps=_render_scene_canvas_prepared) as render:
            output = route_live_hook(self.event(), self.service)
        self.assertIn('additionalContext', output['hookSpecificOutput'])
        self.assert_image_request(entry[0], False, 'host_hook')
        trace = self.traces()[-1]
        self.assert_image_request(trace, False, 'host_hook')
        self.assertIs(trace['annotations']['service_image_present'], False)
        self.assertIsNone(trace['annotations'].get('mcp_native_image_block_count'))
        self.assert_no_picture_work(trace)
        self.assertEqual((render.call_count, self.host.captures, self.host.calls), (0, 1, 0))

    def test_actual_pre_callback_owns_false_without_weakening_gate(self):
        entry = []
        original = self.service.preview_action
        def preview(*args, **kwargs):
            entry.append(current_trace().record)
            self.assertIs(kwargs['include_image'], False)
            return original(*args, **kwargs)
        with patch.object(self.service, 'preview_action', side_effect=preview):
            output = route_live_hook(self.event('PreToolUse'), self.service)
        self.assertNotEqual(output['hookSpecificOutput'].get('permissionDecision'), 'deny')
        self.assertIs(json.loads(output['hookSpecificOutput']['additionalContext'])['allow_action'], True)
        self.assert_image_request(entry[0], False, 'host_hook')
        self.assert_image_request(self.traces()[-1], False, 'host_hook')
        self.assertIs(self.traces()[-1]['annotations']['service_image_present'], False)
        self.assert_no_picture_work(self.traces()[-1])
        self.assertEqual((self.host.captures, self.host.calls), (1, 0))

    def test_unknown_prompt_and_post_skip_do_not_read_even_corrupt_state(self):
        self.state_path.write_bytes(b'not JSON; preserve bytes')
        for event in ({**self.event(), 'prompt': 'Summarize the project notes.'},
                      self.event('PostToolUse')):
            with self.subTest(kind=event['hook_event_name']):
                self.assertEqual(route_live_hook(event, self.service), {})
                self.assert_image_request(self.traces()[-1], False, 'host_hook')
                self.assert_no_picture_work(self.traces()[-1])
        self.assertEqual((self.host.captures, self.host.calls), (0, 0))
        self.assertEqual(self.state_path.read_bytes(), b'not JSON; preserve bytes')

    def test_mcp_transform_declares_true_before_callback_and_delivers_one_actual_png(self):
        entry = []
        original = self.service.transform
        def transform(*args, **kwargs):
            entry.append(current_trace().record)
            return original(*args, **kwargs)
        with patch.object(self.service, 'transform', side_effect=transform), patch(
                'human_eye_plugin.auto_router._render_scene_canvas_prepared',
                wraps=_render_scene_canvas_prepared) as render:
            response = self.server.handle_jsonrpc_message(self.request(rpc_id='7'))
        self.assertEqual(self.value(response)['status'], 'verified')
        self.assert_image_request(entry[0], True, 'mcp_transport')
        trace = self.traces()[-1]
        self.assert_image_request(trace, True, 'mcp_transport')
        self.assertIs(trace['annotations']['service_image_present'], True)
        self.assertEqual(trace['annotations']['mcp_native_image_block_count'], 1)
        self.assertEqual(trace['annotations']['mcp_request_id'], '7')
        self.assertEqual(trace['annotations']['mcp_request_id_type'], 'string')
        self.assertNotEqual(trace['request_id'], '7')
        self.assertIsNone(trace['correlation']['tool_use_id'])
        self.assertEqual(trace['annotations']['delivery'], 'mcp_content_constructed')
        self.assert_native_png(response)
        self.assertEqual((render.call_count, self.host.captures, self.host.calls), (1, 3, 1))

    def test_stdio_transform_retains_true_and_typed_id_in_one_trace(self):
        incoming = io.StringIO(json.dumps(self.request(rpc_id=0)) + '\n')
        outgoing = io.StringIO()
        run_stdio_mcp_server(self.service, incoming, outgoing)
        response = json.loads(outgoing.getvalue())
        self.assertEqual(response['id'], 0)
        self.assertIs(type(response['id']), int)
        self.assertEqual(len(self.traces()), 1)
        trace = self.traces()[0]
        self.assert_image_request(trace, True, 'mcp_transport')
        self.assertEqual(trace['annotations']['mcp_request_id_type'], 'integer')
        self.assertEqual(trace['annotations']['delivery'], 'stdio_write_completed')
        self.assertEqual(trace['annotations']['mcp_native_image_block_count'], 1)
        self.assertIn('mcp.stdio_write', self.names(trace))
        self.assert_native_png(response)
        self.assertEqual((self.host.captures, self.host.calls), (3, 1))

    def test_requested_true_with_renderer_fallback_records_actual_zero_images(self):
        with patch('human_eye_plugin.auto_router._render_scene_canvas_prepared',
                   side_effect=ValueError('independent bounded-render failure')):
            response = self.server.handle_jsonrpc_message(self.request())
        self.assertEqual(self.value(response)['status'], 'verified')
        trace = self.traces()[-1]
        self.assert_image_request(trace, True, 'mcp_transport')
        self.assertIs(trace['annotations']['service_image_present'], False)
        self.assertEqual(trace['annotations']['mcp_native_image_block_count'], 0)
        self.assertFalse(any(c['type'] == 'image' for c in response['result']['content']))
        self.assertNotIn('encoding.png', self.names(trace))
        self.assertIn('render.scene_canvas', self.names(trace))
        self.assertEqual((self.host.captures, self.host.calls), (3, 1))

    def test_status_is_explicit_unknown_image_request_without_host_capture(self):
        response = self.server.handle_jsonrpc_message(self.request(
            name='human_eye_connection_status', arguments={}))
        self.assertFalse(response['result']['isError'])
        trace = self.traces()[-1]
        self.assert_image_request(trace, None, 'mcp_transport')
        self.assertIs(trace['annotations']['service_image_present'], False)
        self.assertEqual(trace['annotations']['mcp_native_image_block_count'], 0)
        self.assert_no_picture_work(trace)
        self.assertEqual((self.host.captures, self.host.calls), (0, 0))

    def test_failed_trace_writer_does_not_retry_or_change_verified_mutation(self):
        records = []
        def failed_writer(record):
            records.append(record)
            raise OSError('independent audit writer failure')
        with RequestTrace('transport.owner', writer=failed_writer) as outer:
            response = self.server.handle_jsonrpc_message(self.request())
        self.assertEqual(outer.delivery_status, 'failed')
        self.assertEqual(self.value(response)['status'], 'verified')
        self.assertEqual(len(records), 1)
        self.assert_image_request(records[0], True, 'mcp_transport')
        self.assertEqual(records[0]['annotations']['mcp_native_image_block_count'], 1)
        self.assert_native_png(response)
        self.assertEqual((self.host.captures, self.host.calls), (3, 1))
        self.assertIsNone(json.loads(self.state_path.read_bytes())['inflight'])

    def test_stdio_writer_failure_after_commit_is_not_successful_wire_delivery(self):
        class BrokenOutput:
            def write(self, _):
                raise OSError('independent transport write failure')
            def flush(self):
                raise AssertionError('Flush after failed write')
        with self.assertRaisesRegex(OSError, 'transport write failure'):
            run_stdio_mcp_server(self.service,
                io.StringIO(json.dumps(self.request()) + '\n'), BrokenOutput())
        trace = self.traces()[-1]
        self.assert_image_request(trace, True, 'mcp_transport')
        self.assertIs(trace['annotations']['service_image_present'], True)
        self.assertEqual(trace['annotations']['mcp_native_image_block_count'], 1)
        self.assertNotEqual(trace['annotations'].get('delivery'), 'stdio_write_completed')
        self.assertEqual(trace['error_type'], 'OSError')
        self.assertEqual((self.host.captures, self.host.calls), (3, 1))
        self.assertIsNone(json.loads(self.state_path.read_bytes())['inflight'])
        self.assertIsNone(current_trace())

    def test_mcp_stale_status_and_transform_preserve_structured_refusal_and_journal(self):
        before = self.binding_fixture(stale=True)
        for name, arguments in (('human_eye_connection_status', {}),
                                ('human_eye_transform', {'action': self.action})):
            with self.subTest(tool=name):
                response = self.server.handle_jsonrpc_message(self.request(name=name, arguments=arguments))
                self.assertTrue(response['result']['isError'])
                value = self.value(response)
                self.assert_binding(value, 'stale_configuration_snapshot')
                self.assertIs(value['executed'], False)
                self.assertIs(value['execution_verified'], False)
                self.assertIs(value['allow_action'], False)
                self.assertEqual(value['recovery']['action'], 'restart_and_revalidate_current_configuration')
                self.assert_preserved(before)

    def test_real_command_callback_stale_pre_denies_without_losing_diagnostic(self):
        before = self.binding_fixture(stale=True)
        with patch('human_eye_plugin.live_hooks.LiveSpatialService', return_value=self.service):
            output = execute_command_event(self.event('PreToolUse'), self.config_path)
        self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
        value = json.loads(output['hookSpecificOutput']['additionalContext'])
        self.assert_binding(value, 'stale_configuration_snapshot')
        self.assertIs(value['allow_action'], False)
        self.assertEqual(value['execution_status'], 'not_executed')
        self.assert_preserved(before)

    def test_unknown_fence_is_not_guessed_and_both_generations_refuse_without_reset(self):
        before = self.binding_fixture()
        self.config = {**self.config, 'quad_size': 128}
        self.config_path.write_text(json.dumps(self.config), encoding='utf-8')
        fresh = LiveSpatialService(self.config_path, host=self.host, production_mode=True)
        for service in (self.service, fresh):
            with self.subTest(generation=service.config_fingerprint):
                response = LiveSpatialMCPServer(service).handle_jsonrpc_message(self.request())
                self.assertTrue(response['result']['isError'])
                self.assert_binding(self.value(response), 'state_binding_cause_unconfirmed')
                self.assertNotIn('matching_activation_record', self.value(response)['recovery'])
                self.assert_preserved(before)

    def test_known_uncommitted_fence_retains_evidence_in_mcp_and_hook_refusals(self):
        before = self.binding_fixture(known=True)
        manifest_path = self.directory / 'setup-backups' / ('a' * 32) / 'manifest.json'
        manifest_raw = manifest_path.read_bytes()
        response = self.server.handle_jsonrpc_message(self.request())
        value = self.value(response)
        self.assertTrue(response['result']['isError'])
        self.assert_binding(value, 'known_uncommitted_activation_fence')
        self.assertEqual(value['recovery']['matching_activation_record']['evidence'],
                         'matching_fingerprint_state_bytes_and_paths')
        output = route_live_hook(self.event('PreToolUse'), self.service)
        self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assert_binding(json.loads(output['hookSpecificOutput']['additionalContext']),
                            'known_uncommitted_activation_fence')
        self.assertEqual(manifest_path.read_bytes(), manifest_raw)
        self.assert_preserved(before)

    def test_restart_with_proven_current_binding_preserves_pending_uncertainty(self):
        before = self.binding_fixture(stale=True)
        fresh = LiveSpatialService(self.config_path, host=self.host, production_mode=True)
        response = LiveSpatialMCPServer(fresh).handle_jsonrpc_message(self.request())
        value = self.value(response)
        self.assertEqual(value['status'], 'host_quarantined')
        self.assertTrue(response['result']['isError'])
        self.assertIs(value['executed'], False)
        self.assertNotIn('recovery', value)  # Correct binding alone grants no authority.
        self.assert_preserved(before)

    def test_pre_allow_does_not_remove_fresh_inner_collision_gate(self):
        output = route_live_hook(self.event('PreToolUse'), self.service)
        self.assertNotEqual(output['hookSpecificOutput'].get('permissionDecision'), 'deny')
        self.assertIs(json.loads(output['hookSpecificOutput']['additionalContext'])['allow_action'], True)
        self.host.scene['meshes'].append(mesh('new-obstacle', [0, 0, .45], [.3, .3, .04]))
        self.host.scene['revision'] = 'external-change'
        response = self.server.handle_jsonrpc_message(self.request())
        self.assertIn('candidate_collision', self.value(response)['reason_codes'])
        self.assertTrue(response['result']['isError'])
        self.assertEqual(self.host.calls, 0)
        self.assertGreater(self.host.captures, 1)
        self.assert_image_request(self.traces()[-1], True, 'mcp_transport')

    def test_uncertain_commit_remains_quarantined_and_post_does_not_retry(self):
        self.host.mode = 'incorrect'
        response = self.server.handle_jsonrpc_message(self.request())
        self.assertTrue(response['result']['isError'])
        self.assertEqual(self.value(response)['status'], 'host_readback_rejected')
        self.assertEqual(self.value(response)['execution_status'], 'execution_uncertain')
        before = (self.state_path.read_bytes(), self.host.captures, self.host.calls)
        self.assertIsNotNone(json.loads(before[0])['inflight'])
        self.assertEqual(route_live_hook(self.event('PostToolUse'), self.service), {})
        again = self.server.handle_jsonrpc_message(self.request(rpc_id='retry-refused'))
        self.assertEqual(self.value(again)['status'], 'host_quarantined')
        self.assertTrue(again['result']['isError'])
        self.assert_preserved(before)

    def test_direct_service_defaults_and_status_have_distinct_explicit_ownership(self):
        result = self.service.observe('direct-api')
        self.assertEqual(result['status'], 'observed')
        self.assertIsNotNone(result['routing']['image'])
        self.assert_image_request(self.traces()[-1], True, 'service')
        self.assertIs(self.traces()[-1]['annotations']['service_image_present'], True)
        self.assertNotIn('mcp_native_image_block_count', self.traces()[-1]['annotations'])
        captures = self.host.captures
        self.service.status()
        self.assert_image_request(self.traces()[-1], None, 'service')
        self.assertIs(self.traces()[-1]['annotations']['service_image_present'], False)
        self.assert_no_picture_work(self.traces()[-1])
        self.assertEqual(self.host.captures, captures)


if __name__ == '__main__':
    unittest.main()

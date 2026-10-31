"""Fresh execution, query transport and final image delivery contracts."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin.host_runtime import GuardedHostRuntime
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
from human_eye_plugin.live_hooks import route_live_hook, SPATIAL_TRANSFORM
from human_eye_plugin.scene_rendering import _render_scene_canvas_prepared
from verification.test_live_service import SelfLockingHost
from verification.test_host_runtime import mesh
from verification.test_live_hooks import HookService


class DeliveryPipelineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.config = self.folder / 'config.json'
        self.config.write_text(json.dumps({'schema_version': '1.0',
            'project_root': str(Path(__file__).resolve().parents[1]), 'state_file': 'state.json',
            'audit_file': 'audit.jsonl', 'quad_size': 64}), encoding='utf-8')
        self.host = SelfLockingHost()
        self.service = LiveSpatialService(self.config, host=self.host)
        self.action = {'focal_id': 'part', 'reference_id': 'base', 'translation': [0, 0, .05]}

    def rpc(self, name, arguments):
        response = LiveSpatialMCPServer(self.service, default_session_id='s').handle_jsonrpc_message({
            'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}})
        result = response['result']
        return result, json.loads(result['content'][0]['text'])

    def test_transform_prepares_without_image_and_delivers_only_final_image(self):
        with patch('human_eye_plugin.auto_router._render_scene_canvas_prepared', wraps=_render_scene_canvas_prepared) as render:
            result = self.service.transform('s', self.action)
        self.assertTrue(result['execution_verified'])
        self.assertIsNotNone(result['routing']['image'])
        self.assertEqual(result['routing']['scene_revision'], self.host.scene['revision'])
        self.assertEqual(render.call_count, 1)
        self.assertEqual(self.host.calls, 1)
        self.assertEqual(self.host.captures, 3)  # prepare, mandatory gate, independent readback

    def test_preview_uses_one_capture_and_no_render_without_granting_execution(self):
        with patch('human_eye_plugin.auto_router._render_scene_canvas_prepared', wraps=_render_scene_canvas_prepared) as render:
            result = self.service.preview_action('s', self.action)
        self.assertTrue(result['allow_action'])
        self.assertEqual(result['action_eligibility']['status'], 'eligible_preview')
        self.assertFalse(result['action_eligibility']['execution_authority'])
        self.assertEqual(self.host.captures, 1)
        self.assertEqual(self.host.calls, 0)
        self.assertEqual(render.call_count, 0)

    def test_invalid_preview_envelope_does_not_capture_host(self):
        for session in ('', None, 4):
            with self.subTest(session=session), self.assertRaises(ValueError):
                self.service.preview_action(session, self.action)
        with self.assertRaises(ValueError):
            self.service.preview_action('s', self.action, include_image=1)
        self.assertEqual(self.host.captures, 0)

    def test_preview_cannot_hide_new_obstacle_before_actual_execution(self):
        self.assertTrue(self.service.preview_action('s', self.action)['allow_action'])
        self.host.scene['meshes'].append(mesh('new_obstacle', [0, 0, .45], [.3, .3, .04]))
        self.host.scene['revision'] = 'external-change'
        result = self.service.transform('s', self.action)
        self.assertFalse(result['executed'])
        self.assertIn('candidate_collision', result['reason_codes'])
        self.assertEqual(self.host.calls, 0)

    def test_preparation_and_final_preferences_are_independent(self):
        runtime = GuardedHostRuntime(self.host, quad_size=64)
        prepared = runtime.before_model(session_id='s', task_instruction='Inspect current part.',
            focal_id='part', reference_id='base', messages=[], include_image=False, final_include_image=True)
        self.assertIsNone(prepared['routing']['image'])
        result = runtime.execute_action(session_id='s', action=self.action)
        self.assertTrue(result['execution_verified'])
        self.assertIsNotNone(result['routing']['image'])

    def test_false_final_preference_does_not_gain_an_unrequested_picture(self):
        runtime = GuardedHostRuntime(self.host, quad_size=64)
        runtime.before_model(session_id='s', task_instruction='Inspect current part.', focal_id='part',
            reference_id='base', messages=[], include_image=False, final_include_image=False)
        result = runtime.execute_action(session_id='s', action=self.action)
        self.assertTrue(result['execution_verified'])
        self.assertIsNone(result['routing']['image'])

    def test_invalid_delivery_preferences_do_not_capture_host(self):
        runtime = GuardedHostRuntime(self.host, quad_size=64)
        for value in ('yes', 1, []):
            with self.subTest(value=value), self.assertRaises(ValueError):
                runtime.before_model(session_id='s', task_instruction='Inspect part.', focal_id='part',
                    reference_id='base', messages=[], final_include_image=value)
        self.assertEqual(self.host.captures, 0)

    def test_posthook_does_not_recapture_or_infer_success_from_response_text(self):
        for response in ({'status': 'verified'}, {'status': 'error'}, None):
            service = HookService()
            event = {'hook_event_name': 'PostToolUse', 'tool_name': SPATIAL_TRANSFORM,
                'session_id': 's', 'tool_input': {'action': self.action}, 'tool_response': response}
            self.assertEqual(route_live_hook(event, service), {})
            self.assertEqual(service.calls, [])
            self.assertTrue(any(item[1].get('scene_read') is False for item in service.records))

    def test_invalid_query_is_rejected_before_host_access(self):
        for query in ({'mode': 'anything'}, {'mode': 'nearest', 'max_exact_pairs': True}, {'extra': 1}):
            with self.subTest(query=query), self.assertRaises(ValueError):
                self.service.observe('s', focal_id='part', reference_id='base', query=query)
        self.assertEqual(self.host.captures, 0)

    def test_nearest_query_crosses_real_mcp_and_does_not_rank_lower_bounds(self):
        self.host.scene['meshes'].extend([
            mesh('diagonal', [.84, .8, .35], [.2, .2, .1]),
            mesh('axial', [.94, 0, .35], [.2, .2, .1])])
        query = {'mode': 'nearest', 'object_ids': ['diagonal', 'axial']}
        original = copy.deepcopy(query)
        wire, value = self.rpc('human_eye_scene_observe', {'focal_id': 'part', 'reference_id': 'base', 'query': query})
        self.assertFalse(wire['isError'])
        self.assertEqual(value['query_result']['status'], 'complete')
        self.assertEqual(value['query_result']['ranked_object_ids'], ['axial', 'diagonal'])
        self.assertEqual(query, original)
        self.assertEqual(self.host.calls, 0)

    def test_query_without_pair_is_explicitly_unresolved_but_keeps_overview(self):
        self.host.scene['meshes'] = self.host.scene['meshes'][:1]
        wire, value = self.rpc('human_eye_scene_observe', {'query': {'mode': 'nearest'}})
        self.assertFalse(wire['isError'])
        self.assertEqual(value['status'], 'overview')
        self.assertEqual(value['query_result']['status'], 'unknown')
        self.assertIn('query_pair_required', value['query_result']['reason_codes'])

    def test_action_schema_rejects_query_as_an_execution_shortcut(self):
        wire, _ = self.rpc('human_eye_transform', {'action': self.action, 'query': {'mode': 'overview'}})
        self.assertTrue(wire['isError'])
        self.assertEqual(self.host.captures, 0)
        self.assertEqual(self.host.calls, 0)

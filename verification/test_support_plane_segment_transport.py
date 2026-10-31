"""The explicit support-plane branch reaches the same guarded MCP and hooks.

These checks exercise real envelopes and a private-state mutable host; they
never connect to Blender or certify automatic host hook activation.
"""
import copy
import json
from pathlib import Path
import re
import tempfile
import unittest

from human_eye_plugin import agent_setup
from human_eye_plugin.goal_segment import CLEARANCE_SEGMENT_REQUEST_SCHEMA
from human_eye_plugin.live_hooks import route_live_hook, SPATIAL_CLEARANCE_SEGMENT
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LIVE_MCP_TOOLS_SCHEMA, LiveSpatialMCPServer
from verification.test_clearance_segment_hooks import NoSceneHookService, goal_event
from verification.test_clearance_segment_service import SegmentHost
from verification.test_support_plane_candidate import tilted_scene


def support_request(**changes):
    request = {'solver': 'support_plane', 'focal_id': 'part', 'reference_id': 'base',
        'reference_triangle_index': 2, 'direction_world': [0., 0., 7.],
        'target_clearance_m': .001, 'clearance_tolerance_m': 1e-6}
    request.update(changes)
    return request


class RecordingService:
    """A transport double records delivery; it provides no geometry authority."""
    def __init__(self):
        self.calls = []
        self.result = {'status': 'preview', 'executed': False,
                       'execution_authority': False, 'candidate': {'status': 'unsupported'}}

    def run_clearance_segment(self, session_id, request_id, request, **kwargs):
        self.calls.append((session_id, request_id, request, kwargs))
        return copy.deepcopy(self.result)


class SupportPlaneTransportTests(unittest.TestCase):
    def setUp(self):
        self.service = RecordingService()
        self.server = LiveSpatialMCPServer(self.service, default_session_id='transport-session')

    def envelope(self, arguments):
        return {'jsonrpc': '2.0', 'id': 'call-1', 'method': 'tools/call',
            'params': {'name': 'human_eye_clearance_segment', 'arguments': arguments}}

    def call(self, arguments):
        response = self.server.handle_jsonrpc_message(self.envelope(arguments))
        wire = response['result']
        return wire, json.loads(wire['content'][0]['text'])

    def test_explicit_request_uses_existing_tool_and_keeps_direction_without_mutating_input(self):
        arguments = {'request_id': 'plane-1', 'request': support_request()}
        before = copy.deepcopy(arguments)
        wire, body = self.call(arguments)
        self.assertFalse(wire['isError'], body)
        self.assertEqual(self.service.calls, [('transport-session', 'plane-1', before['request'],
            {'execute': False, 'include_image': False})])
        self.assertEqual(arguments, before)
        self.service.calls[0][2]['direction_world'][2] = 99
        self.assertEqual(arguments, before)

    def test_explicit_execute_and_final_image_flags_reach_service(self):
        wire, _ = self.call({'session_id': 'real-session', 'request_id': 'plane-1',
            'request': support_request(), 'execute': True, 'include_image': True})
        self.assertFalse(wire['isError'])
        self.assertEqual(self.service.calls[0][0], 'real-session')
        self.assertEqual(self.service.calls[0][3], {'execute': True, 'include_image': True})

    def test_nested_schema_has_two_disjoint_complete_branches_and_no_global_axis_requirement(self):
        tools = self.server.handle_jsonrpc_message({'jsonrpc': '2.0', 'id': 1,
            'method': 'tools/list'})['result']['tools']
        self.assertEqual([t['name'] for t in tools], ['human_eye_scene_observe',
            'human_eye_transform', 'human_eye_connection_status', 'human_eye_clearance_segment'])
        schema = tools[-1]['inputSchema']['properties']['request']
        self.assertEqual(schema, CLEARANCE_SEGMENT_REQUEST_SCHEMA)
        self.assertNotIn('axis', schema['required'])
        self.assertEqual(len(schema['oneOf']), 2)
        legacy, support = schema['oneOf']
        self.assertIn('axis', legacy['required'])
        self.assertNotIn('solver', legacy['properties'])
        self.assertIn('solver', support['required'])
        self.assertEqual(support['properties']['solver']['enum'], ['support_plane'])
        self.assertNotIn('axis', support['properties'])
        for branch in schema['oneOf']:
            self.assertFalse(branch['additionalProperties'])
        self.assertIn('reference_triangle_index', support['required'])
        self.assertIn('direction_world', support['required'])
        self.assertEqual(tools[-1]['inputSchema']['properties']['execute']['default'], False)
        schema['oneOf'][1]['properties']['solver']['enum'][0] = 'mutated'
        self.assertEqual(LIVE_MCP_TOOLS_SCHEMA[-1]['inputSchema']['properties']['request']
                         ['oneOf'][1]['properties']['solver']['enum'], ['support_plane'])

    def test_branch_confusion_missing_selectors_and_coercible_inputs_fail_before_service(self):
        invalid = []
        for key in ('solver', 'reference_triangle_index', 'direction_world'):
            value = support_request(); value.pop(key); invalid.append(value)
        invalid += [support_request(axis='+z'), support_request(solver='nearest_plane'),
            support_request(reference_triangle_index=True), support_request(reference_triangle_index=2.),
            support_request(direction_world=[0., False, 1.]), support_request(direction_world=[0., 0., 0.]),
            support_request(direction_world=[0., 0., float('nan')]),
            support_request(target_clearance_m=True), support_request(max_steps=True),
            support_request(max_duration_s=0), support_request(force=True),
            support_request(candidate={'translation': [0., 0., -.003]})]
        for request in invalid:
            with self.subTest(request=request):
                wire, _ = self.call({'request_id': 'invalid', 'request': request, 'execute': True})
                self.assertTrue(wire['isError'])
        self.assertEqual(self.service.calls, [])

    def test_invalid_outer_flags_and_notification_have_no_service_effect(self):
        for changes in ({'execute': 1}, {'include_image': 'true'}, {'reference_triangle_index': 2},
                        {'solver': 'support_plane'}, {'request_id': ''}):
            wire, _ = self.call({'request_id': 'invalid', 'request': support_request(), **changes})
            self.assertTrue(wire['isError'])
        event = self.envelope({'request_id': 'silent', 'request': support_request(), 'execute': True})
        event.pop('id')
        self.assertIsNone(self.server.handle_jsonrpc_message(event))
        self.assertEqual(self.service.calls, [])

    def test_uncertain_result_preserves_unknown_execution_and_never_grants_retry(self):
        self.service.result = {'status': 'execution_uncertain', 'executed': None,
            'execution_authority': False, 'retry_authorized': False,
            'reason_codes': ['host_step_outcome_uncertain'], 'steps': [{'state': 'uncertain'}]}
        wire, result = self.call({'request_id': 'uncertain', 'request': support_request(), 'execute': True})
        self.assertTrue(wire['isError'])
        self.assertIsNone(result['executed'])
        self.assertFalse(result['retry_authorized'])
        self.assertFalse(result['execution_authority'])
        self.assertEqual(len(self.service.calls), 1)


class SupportPlaneHookTests(unittest.TestCase):
    @staticmethod
    def event(kind='PreToolUse', **changes):
        event = goal_event(kind)
        event['tool_input']['request'] = support_request()
        event.update(changes)
        return event

    def test_all_supported_host_adapters_use_shape_only_hook_without_scene_or_motion(self):
        for adapter in ('codex', 'claude'):
            service = NoSceneHookService(); event = self.event(); before = copy.deepcopy(event)
            result = route_live_hook(event, service, agent=adapter)
            output = result['hookSpecificOutput']
            self.assertNotIn('permissionDecision', output)
            body = json.loads(output['additionalContext'])
            self.assertEqual(body['human_eye_live'], 'goal_request_structure_valid')
            self.assertEqual(body['validation_scope'], 'request_shape_only')
            self.assertEqual(body['session_id'], adapter + ':host-session')
            self.assertFalse(body['execution_authority'])
            self.assertFalse(body['scene_read'])
            self.assertFalse(body['engine_invoked'])
            self.assertFalse(body['retry_authorized'])
            self.assertTrue(body['inner_execution_gate_required'])
            self.assertEqual(event, before)

    def test_default_preview_and_receipt_replay_need_no_hook_host_work(self):
        event = self.event(); event['tool_input'].pop('execute')
        for _ in range(2):
            output = route_live_hook(event, NoSceneHookService())['hookSpecificOutput']
            self.assertFalse(json.loads(output['additionalContext'])['execute_requested'])

    def test_mixed_or_missing_branch_is_denied_and_payload_not_leaked(self):
        for request in (support_request(axis='+z'), support_request(solver='unknown')):
            event = self.event(); event['tool_input']['request'] = request
            output = route_live_hook(event, NoSceneHookService())['hookSpecificOutput']
            self.assertEqual(output['permissionDecision'], 'deny')
            self.assertNotIn('direction_world', json.dumps(output))

    def test_posttool_does_not_recapture_or_repeat_even_with_claimed_success(self):
        service = NoSceneHookService()
        event = self.event('PostToolUse', tool_response={'task_succeeded': True})
        self.assertEqual(route_live_hook(event, service), {})
        self.assertTrue(any(fields.get('status') == 'tool_result_delivery_retained'
                            for _, fields in service.records))

    def test_tool_matchers_remain_exact_and_unrelated_tools_do_not_gain_coverage(self):
        self.assertTrue(re.fullmatch(agent_setup.CLEARANCE_SEGMENT_MATCHER, SPATIAL_CLEARANCE_SEGMENT))
        self.assertIsNone(re.fullmatch(agent_setup.CLEARANCE_SEGMENT_MATCHER, SPATIAL_CLEARANCE_SEGMENT+'_other'))
        self.assertIsNone(re.fullmatch(agent_setup.TRANSFORM_MATCHER, SPATIAL_CLEARANCE_SEGMENT))


class SupportPlaneActualMCPTests(unittest.TestCase):
    """Exercise the real service and inner gate using only temporary test state."""
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name); self.path = self.folder/'config.json'
        self.path.write_text(json.dumps({'schema_version': '1.0',
            'project_root': str(Path(__file__).resolve().parents[1]), 'state_file': 'state.json',
            'audit_file': 'audit.jsonl', 'quad_size': 64}), encoding='utf-8')
        self.host = SegmentHost(); identity = self.host.scene['host_identity']
        self.host.scene = tilted_scene(); self.host.scene['revision'] = 'r1'
        self.host.scene['host_identity'] = identity
        self.service = LiveSpatialService(self.path, host=self.host)
        self.server = LiveSpatialMCPServer(self.service, default_session_id='guarded-plane-session')

    def call(self, **changes):
        args = {'request_id': 'plane-real', 'request': support_request(), **changes}
        value = self.server.handle_jsonrpc_message({'jsonrpc': '2.0', 'id': 42,
            'method': 'tools/call', 'params': {'name': 'human_eye_clearance_segment', 'arguments': args}})['result']
        return value, json.loads(value['content'][0]['text'])

    def test_actual_preview_is_supported_and_keeps_private_state_and_host_unchanged(self):
        before = copy.deepcopy(self.host.scene)
        wire, result = self.call()
        self.assertFalse(wire['isError'], result)
        self.assertEqual(result['status'], 'preview')
        self.assertEqual(result['candidate']['status'], 'candidate')
        self.assertFalse(result['executed'])
        self.assertEqual(self.host.scene, before)
        self.assertEqual(self.host.calls, 0)
        self.assertFalse((self.folder/'state.json').exists())

    def test_explicit_full_scene_transport_exposes_original_face_selector_with_current_binding(self):
        wire = self.server.handle_jsonrpc_message({'jsonrpc': '2.0', 'id': 7,
            'method': 'tools/call', 'params': {'name': 'human_eye_scene_observe', 'arguments': {
                'focal_id': 'part', 'reference_id': 'base', 'include_image': False,
                'scene_delta': {}}}})['result']
        result = json.loads(wire['content'][0]['text'])
        self.assertFalse(wire['isError'], result)
        packet = result['scene_transport']
        self.assertEqual(packet['status'], 'full')
        self.assertFalse(packet['execution_authority'])
        self.assertEqual(packet['target']['scene_revision'], result['routing']['scene_revision'])
        self.assertEqual(packet['target']['scene_fingerprint'], result['routing']['scene_fingerprint'])
        reference = next(m for m in packet['payload']['meshes'] if m['object_id'] == 'base')
        self.assertEqual(reference['faces'], self.host.scene['meshes'][0]['faces'])
        self.assertEqual(reference['vertices'], self.host.scene['meshes'][0]['vertices'])
        self.assertEqual(self.host.calls, 0)

    def test_actual_guarded_execution_and_durable_replay_do_not_repeat_host_work(self):
        wire, result = self.call(execute=True)
        self.assertFalse(wire['isError'], result)
        self.assertEqual(result['status'], 'satisfied', result)
        self.assertEqual(self.host.calls, 1)
        self.assertLessEqual(abs(self.host.actual_gap()-.001), 1e-6)
        self.assertEqual(result['task_succeeded_scope'],
                         'requested_original_support_triangle_pair_clearance_at_segment_end')
        count = self.host.captures
        self.host.mode = 'capture_failure'
        self.service = LiveSpatialService(self.path, host=self.host)
        self.server = LiveSpatialMCPServer(self.service, default_session_id='guarded-plane-session')
        _, historical = self.call(execute=True)
        self.assertTrue(historical['historical_receipt'])
        self.assertFalse(historical['current_scene_revalidated'])
        self.assertEqual(self.host.calls, 1)
        self.assertEqual(self.host.captures, count)

    def test_final_native_image_is_delivered_once_and_not_written_in_ledger(self):
        wire, result = self.call(execute=True, include_image=True)
        self.assertFalse(wire['isError'], result)
        images = [item for item in wire['content'] if item['type'] == 'image']
        self.assertEqual(len(images), 1, result)
        self.assertNotIn(images[0]['data'], (self.folder/'state.json').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()

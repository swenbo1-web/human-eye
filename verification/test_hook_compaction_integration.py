"""Real service/host hook projection boundaries; no Blender or model calls.

The independent decoder reconstructs the display format to compare it with the
previous hook summary. It is not an action, measurement or reference resolver
used by production code.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import human_eye_plugin
from human_eye_plugin.live_hooks import route_live_hook, SPATIAL_TRANSFORM
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.scene_rendering import _render_scene_canvas_prepared
from verification.test_flow_result_contract import CapturedHost
from verification.test_host_runtime import mesh
from verification.test_rigid_frame_contract import nonbox_scene


SCOPED_FIELDS = ('observation_status', 'scene_assessment', 'action_eligibility',
    'pair_goal', 'execution_status', 'task_succeeded_scope', 'host_execution')
GATE_FIELDS = ('geometry_work_budget', 'rigid_frame_valid', 'rigid_frame',
    'requires_reobserve', 'source_check')


def expanded_context(document):
    """Resolve declared local copies, rejecting dangling/cyclic/overriding refs."""
    if document.get('context_projection', {}).get('reference_encoding') == 'disabled_reserved_key':
        return copy.deepcopy(document)

    def target(pointer):
        if not isinstance(pointer, str) or not pointer.startswith('#/'):
            raise AssertionError('Nonlocal reference')
        value = document
        for part in pointer[2:].split('/'):
            part = part.replace('~1', '/').replace('~0', '~')
            value = value[int(part)] if isinstance(value, list) else value[part]
        return value

    def visit(value, active=()):
        if isinstance(value, dict):
            if '$ref' in value:
                if set(value) - {'$ref', 'object_id'}:
                    raise AssertionError('Unexpected reference sibling')
                pointer = value['$ref']
                if pointer in active:
                    raise AssertionError('Cyclic reference')
                result = visit(target(pointer), active + (pointer,))
                if not isinstance(result, dict):
                    raise AssertionError('Reference must copy a dictionary')
                for key in value.keys() - {'$ref'}:
                    if key in result:
                        raise AssertionError('Reference sibling overrides copied data')
                    result[key] = visit(value[key], active)
                return result
            return {key: visit(item, active) for key, item in value.items()}
        if isinstance(value, list):
            return [visit(item, active) for item in value]
        return copy.deepcopy(value)

    return visit(document)


class RecordingService(LiveSpatialService):
    """Track outputs without replacing the actual service or its inner gate."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outputs = []

    def observe(self, *args, **kwargs):
        result = super().observe(*args, **kwargs)
        self.outputs.append(copy.deepcopy(result))
        return result

    def preview_action(self, *args, **kwargs):
        result = super().preview_action(*args, **kwargs)
        self.outputs.append(copy.deepcopy(result))
        return result


class HookCompactionIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        config = self.directory / 'connector.json'
        config.write_text(json.dumps({'schema_version': '1.0', 'enabled': True,
            'project_root': str(Path(human_eye_plugin.__file__).resolve().parents[1]),
            'state_file': 'state.json', 'audit_file': 'events.jsonl',
            'quad_size': 64, 'max_sessions': 4, 'focal_name': 'part',
            'reference_name': 'base'}), encoding='utf-8')
        self.host = CapturedHost()
        self.service = RecordingService(config, host=self.host, production_mode=True)
        self.action = {'focal_id': 'part', 'reference_id': 'base', 'translation': [0, 0, .05]}

    def event(self, kind='UserPromptSubmit', **changes):
        event = {'hook_event_name': kind, 'session_id': 'compact', 'turn_id': 'actual-turn',
            'tool_use_id': 'actual-tool', 'tool_name': SPATIAL_TRANSFORM,
            'prompt': '检查 Blender 场景中 part 与 base 的间隙，只观察，不移动。',
            'tool_input': {'action': copy.deepcopy(self.action)}}
        event.update(changes)
        return event

    def route(self, kind='UserPromptSubmit', **changes):
        return route_live_hook(self.event(kind, **changes), self.service)

    def summary(self, output):
        raw = json.loads(output['hookSpecificOutput']['additionalContext'])
        return raw, expanded_context(raw)

    def state(self):
        return json.loads((self.directory / 'state.json').read_text(encoding='utf-8'))

    def compare_previous_semantics(self, output):
        """Original fields must survive, apart from the two named stats dicts."""
        raw, context = self.summary(output)
        result = self.service.outputs[-1]
        route = result.get('routing') or {}
        original = route.get('context_text', '')
        try:
            observation = json.loads(original)
        except (ValueError, TypeError):
            observation = original
        expected_omitted = []
        if isinstance(observation, dict):
            for field in ('scene_memory', 'measurement_cache'):
                if isinstance(observation.get(field), dict) and 'stats' in observation[field]:
                    del observation[field]['stats']
                    expected_omitted.append('observation.' + field + '.stats')
        self.assertEqual(context['observation'], observation)
        self.assertEqual(context['human_eye_live'], result['status'])
        self.assertEqual(context['allow_action'], result.get('allow_action'))
        self.assertEqual(context['execution_scope'], route.get('execution_scope', 'terminal_geometry_only'))
        self.assertEqual(context['delivery'], 'text_only_hook_no_native_image')
        self.assertTrue(context['inner_execution_gate_required'])
        self.assertEqual(context['scene_revision'], route.get('scene_revision'))
        self.assertEqual(context['observation_id'], route.get('observation_id'))
        self.assertEqual(context['context_projection']['omitted_diagnostics'], expected_omitted)
        self.assertFalse(context['context_projection']['execution_authority'])
        for field in (*SCOPED_FIELDS, *GATE_FIELDS):
            if field in result:
                self.assertEqual(context[field], result[field], field)
            elif field in GATE_FIELDS and field in route:
                self.assertEqual(context[field], route[field], field)
        self.assertEqual(context['correlation']['turn_id'], 'actual-turn')
        self.assertEqual(context['correlation']['tool_use_id'], 'actual-tool')
        self.assertEqual(context['correlation']['request_origin'], 'hook_command')
        self.assertIsInstance(context['correlation']['trace_id'], str)
        self.assertIsInstance(context['correlation']['request_id'], str)
        identity = self.service.describe_runtime()
        for field in ('implementation_revision', 'build_id', 'source_kind', 'production_mode'):
            self.assertEqual(context['runtime_identity'][field], identity.get(field))
        return raw, context

    def add_unknown_surface(self):
        surface = mesh('open_surface', [20, 0, .2], [.6, .4, .02])
        surface['faces'] = surface['faces'][:2]
        surface['edges'] = None
        self.host.scene['meshes'].append(surface)
        self.host.scene['revision'] = 'r2'

    def test_prompt_keeps_measurements_frames_contacts_and_one_capture(self):
        scene = copy.deepcopy(self.host.scene)
        with patch('human_eye_plugin.auto_router._render_scene_canvas_prepared', wraps=_render_scene_canvas_prepared) as render:
            output = self.route()
        raw, context = self.compare_previous_semantics(output)
        self.assertEqual(self.host.captures, 1)
        self.assertEqual(self.host.calls, 0)
        self.assertEqual(render.call_count, 0)
        self.assertEqual(self.host.scene, scene)
        self.assertEqual(context['execution_scope'], 'observation_only')
        self.assertFalse(context['action_eligibility']['execution_authority'])
        self.assertEqual(context['observation']['measurement']['signed_clearance_m'],
                         context['observation']['scene_contacts'][0]['signed_clearance_m'])
        self.assertIn('object_id', context['observation']['scene_contacts'][0])
        self.assertEqual(raw['context_projection']['reference_encoding'], 'local_pointer_with_object_id')

    def test_safe_pre_keeps_advisory_permission_and_single_capture(self):
        output = self.route('PreToolUse')
        _, context = self.compare_previous_semantics(output)
        self.assertNotIn('permissionDecision', output['hookSpecificOutput'])
        self.assertTrue(context['allow_action'])
        self.assertEqual(context['action_eligibility']['status'], 'eligible_preview')
        self.assertFalse(context['action_eligibility']['execution_authority'])
        self.assertEqual(self.host.captures, 1)
        self.assertEqual(self.host.calls, 0)
        self.assertIsNone(self.state()['inflight'])

    def test_partial_prompt_and_pre_retain_every_unknown_object_without_token(self):
        self.add_unknown_surface()
        for kind in ('UserPromptSubmit', 'PreToolUse'):
            with self.subTest(kind=kind):
                output = self.route(kind)
                _, context = self.compare_previous_semantics(output)
                self.assertEqual(context['observation_status'], 'partial')
                self.assertIn('open_surface', context['scene_assessment']['unknown_object_ids'])
                self.assertIsNone(context['observation_id'])
                self.assertFalse(context['action_eligibility']['execution_authority'])
                self.assertEqual(self.state()['runtime']['sessions'], [])
                if kind == 'PreToolUse':
                    self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
                    self.assertFalse(context['allow_action'])
        self.assertEqual(self.host.captures, 2)
        self.assertEqual(self.host.calls, 0)

    def test_real_budget_rejection_preserves_exact_estimates_and_limits(self):
        capability = self.host.scene['host_execution']
        self.host.scene = nonbox_scene(sides=16, both_prisms=True)
        self.host.scene['host_execution'] = capability
        for kind in ('UserPromptSubmit', 'PreToolUse'):
            with self.subTest(kind=kind):
                output = self.route(kind)
                _, context = self.compare_previous_semantics(output)
                self.assertIn('geometry_resource_limit', context['reason_codes'])
                budget = context['geometry_work_budget']
                self.assertFalse(budget['within_budget'])
                self.assertGreater(budget['estimates']['largest_sat_projection_elements'],
                                   budget['limits']['sat_projection_elements'])
                if kind == 'PreToolUse':
                    self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
                    # Some agents expose only this reason on a denied tool.
                    # Its budget must be self-contained, not a dangling ref
                    # into the separate additionalContext document.
                    reason = output['hookSpecificOutput']['permissionDecisionReason']
                    brief = json.loads(reason.split(': ', 1)[1])
                    self.assertEqual(brief['geometry_work_budget'], budget)
                    self.assertGreater(brief['geometry_work_budget']['estimates']['largest_sat_projection_elements'],
                                       brief['geometry_work_budget']['limits']['sat_projection_elements'])
                    self.assertEqual(brief['geometry_work_budget']['limits']['sat_projection_elements'], 2_000_000)
                    self.assertEqual(brief['requires_reobserve'], context['requires_reobserve'])
        self.assertEqual(self.host.captures, 2)
        self.assertEqual(self.host.calls, 0)
        self.assertIsNone(self.state()['inflight'])
        # The same wire boundary must retain concrete invalid-frame evidence,
        # even when no full observation is visible with the denial.
        self.host.scene = CapturedHost().scene
        self.host.scene['meshes'][1]['axes_source'] = 'unverified_imported_frame'
        output = self.route('PreToolUse')
        _, context = self.compare_previous_semantics(output)
        self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
        brief = json.loads(output['hookSpecificOutput']['permissionDecisionReason'].split(': ', 1)[1])
        self.assertEqual(brief['rigid_frame'], context['rigid_frame'])
        self.assertFalse(brief['rigid_frame']['valid'])
        self.assertIn('focal:axes_source_not_host', brief['rigid_frame']['reason_codes'])
        self.assertEqual(brief['requires_reobserve'], context['requires_reobserve'])
        self.assertTrue(brief['requires_reobserve'])
        self.assertEqual((self.host.captures, self.host.calls), (3, 0))

    def test_collision_deny_preserves_reason_detail_without_repeating_full_context(self):
        scene = copy.deepcopy(self.host.scene)
        action = {**self.action, 'translation': [0, 0, -.15]}
        output = self.route('PreToolUse', tool_input={'action': action})
        _, context = self.compare_previous_semantics(output)
        self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertIn('candidate_collision', context['reason_codes'])
        self.assertEqual(context['observation']['reason'], 'candidate_collision')
        reason = output['hookSpecificOutput']['permissionDecisionReason']
        self.assertIn('candidate_collision', reason)
        self.assertLess(len(reason), len(output['hookSpecificOutput']['additionalContext']))
        self.assertEqual(self.host.scene, scene)
        self.assertEqual((self.host.captures, self.host.calls), (1, 0))

    def test_unknown_prompt_and_post_do_not_capture_or_upgrade_tool_result(self):
        self.assertEqual(self.route(prompt='Hello.'), {})
        for response in ({'status': 'verified'}, {'status': 'error'}, None):
            self.assertEqual(self.route('PostToolUse', tool_response=response), {})
        self.assertEqual(self.service.outputs, [])
        self.assertEqual((self.host.captures, self.host.calls), (0, 0))
        self.assertFalse((self.directory / 'state.json').exists())

    def test_pre_does_not_replace_fresh_inner_gate_after_new_obstacle(self):
        self.assertNotIn('permissionDecision', self.route('PreToolUse')['hookSpecificOutput'])
        self.host.scene['meshes'].append(mesh('new_obstacle', [0, 0, .45], [.3, .3, .04]))
        self.host.scene['revision'] = 'r2'
        result = self.service.transform('codex:compact', self.action)
        self.assertFalse(result['executed'])
        self.assertIn('candidate_collision', result['reason_codes'])
        self.assertEqual(self.host.calls, 0)
        self.assertEqual(self.host.captures, 3)

    def test_pre_then_real_transform_keeps_final_image_and_post_no_io(self):
        with patch('human_eye_plugin.auto_router._render_scene_canvas_prepared', wraps=_render_scene_canvas_prepared) as render:
            self.route('PreToolUse')
            result = self.service.transform('codex:compact', self.action)
            before = self.host.captures
            self.assertEqual(self.route('PostToolUse', tool_response=result), {})
        self.assertTrue(result['execution_verified'])
        self.assertIsNotNone(result['routing']['image'])
        self.assertEqual(render.call_count, 1)
        self.assertEqual(self.host.captures, before)
        self.assertEqual((self.host.captures, self.host.calls), (4, 1))

    def test_quarantine_projection_never_clears_journal_or_touches_host(self):
        self.host.mode = 'partial_failure'
        result = self.service.transform('failed', self.action)
        self.assertFalse(result['execution_verified'])
        state_path = self.directory / 'state.json'
        original = state_path.read_bytes()
        captures, calls = self.host.captures, self.host.calls
        for kind in ('PreToolUse', 'UserPromptSubmit'):
            output = self.route(kind)
            _, context = self.compare_previous_semantics(output)
            self.assertEqual(context['human_eye_live'], 'host_quarantined')
            self.assertFalse(context['action_eligibility']['execution_authority'])
            if kind == 'PreToolUse':
                self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual(state_path.read_bytes(), original)
        self.assertEqual((self.host.captures, self.host.calls), (captures, calls))
        self.assertIsNotNone(self.state()['inflight'])

    def test_existing_ref_key_is_literal_and_disables_document_dedup(self):
        source = {'$ref': '#/observation/measurement', 'meaning': 'literal host metadata'}
        self.host.scene['source'] = source
        output = self.route()
        raw, context = self.compare_previous_semantics(output)
        self.assertEqual(raw['context_projection']['reference_encoding'], 'disabled_reserved_key')
        self.assertEqual(context['observation']['scene_source'], source)
        self.assertEqual(self.host.scene['source'], source)
        self.assertEqual(self.host.calls, 0)

    def test_display_projection_is_detached_from_result_host_and_state(self):
        output = self.route()
        raw, _ = self.summary(output)
        original_result = copy.deepcopy(self.service.outputs[-1])
        original_host = copy.deepcopy(self.host.scene)
        state_path = self.directory / 'state.json'
        original_state = state_path.read_bytes()
        raw['observation']['measurement']['signed_clearance_m'] = 999
        raw['allow_action'] = True
        self.assertEqual(self.service.outputs[-1], original_result)
        self.assertEqual(self.host.scene, original_host)
        self.assertEqual(state_path.read_bytes(), original_state)

    def test_projection_failure_fails_closed_after_same_preview_without_mutation(self):
        with patch('human_eye_plugin.live_hooks.compact_hook_summary', side_effect=ValueError('display failure')):
            output = self.route('PreToolUse')
        self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertTrue(self.service.outputs[-1]['allow_action'])
        self.assertEqual((self.host.captures, self.host.calls), (1, 0))
        self.assertIsNone(self.state()['inflight'])


if __name__ == '__main__':
    unittest.main()

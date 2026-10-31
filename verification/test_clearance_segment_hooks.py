"""Goal hooks never authorize movement or recapture historical receipt requests."""
import copy
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

import human_eye_hook as bootstrap
from human_eye_plugin import agent_setup as setup
from human_eye_plugin.live_hooks import route_live_hook, SPATIAL_CLEARANCE_SEGMENT


class NoSceneHookService:
    def __init__(self):
        self.config = {'enabled': True}
        self.records = []

    def describe_runtime(self):
        return {'implementation_revision': 'test', 'build_id': 'test-build',
                'source_kind': 'test', 'production_mode': False}

    def record_event(self, event, **fields):
        self.records.append((event, fields))

    def observe(self, *args, **kwargs):
        raise AssertionError('Goal hook must not observe the host')

    preview_action = observe
    run_clearance_segment = observe


def goal_event(kind='PreToolUse', **changes):
    value = {'hook_event_name': kind, 'session_id': 'host-session',
        'turn_id': 'turn', 'tool_use_id': 'call', 'tool_name': SPATIAL_CLEARANCE_SEGMENT,
        'tool_input': {'request_id': 'same-receipt-id', 'execute': True,
            'request': {'focal_id': 'part', 'reference_id': 'base', 'axis': '+z',
                'target_clearance_m': .001, 'clearance_tolerance_m': 1e-6}}}
    value.update(changes)
    return value


class ClearanceSegmentHookTests(unittest.TestCase):
    def test_request_shape_check_does_not_read_scene_execute_or_grant_permission(self):
        for agent in ('codex', 'claude'):
            service = NoSceneHookService()
            result = route_live_hook(goal_event(), service, agent=agent)
            output = result['hookSpecificOutput']
            self.assertNotIn('permissionDecision', output)
            context = json.loads(output['additionalContext'])
            self.assertEqual(context['human_eye_live'], 'goal_request_structure_valid')
            self.assertFalse(context['execution_authority'])
            self.assertTrue(context['inner_execution_gate_required'])
            self.assertFalse(context['scene_read'])
            self.assertFalse(context['retry_authorized'])
            self.assertNotIn('task_succeeded', context)
            self.assertEqual(context['session_id'], agent + ':host-session')

    def test_preview_default_and_receipt_replay_require_no_extra_host_work(self):
        service = NoSceneHookService()
        event = goal_event()
        event['tool_input'].pop('execute')
        before = copy.deepcopy(event)
        for _ in range(2):
            output = route_live_hook(event, service)['hookSpecificOutput']
            self.assertFalse(json.loads(output['additionalContext'])['execute_requested'])
            self.assertNotIn('permissionDecision', output)
        self.assertEqual(event, before)

    def test_invalid_goal_or_envelope_is_denied_without_scene_access(self):
        invalid = [None, {}, {'request_id': 'x', 'request': {}},
            {**goal_event()['tool_input'], 'execute': 1},
            {**goal_event()['tool_input'], 'include_image': 'yes'},
            {**goal_event()['tool_input'], 'scene': {'private': 'never forwarded'}}]
        for arguments in invalid:
            with self.subTest(arguments=type(arguments).__name__):
                result = route_live_hook(goal_event(tool_input=arguments), NoSceneHookService())
                self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')
                self.assertNotIn('never forwarded', json.dumps(result))

    def test_disabled_or_missing_session_denies_new_tool(self):
        service = NoSceneHookService()
        service.config['enabled'] = False
        result = route_live_hook(goal_event(), service)
        self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')
        result = route_live_hook(goal_event(session_id=''), NoSceneHookService())
        self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_goal_post_is_delivery_only_and_ignores_claimed_success(self):
        service = NoSceneHookService()
        result = route_live_hook(goal_event('PostToolUse', tool_response={'task_succeeded': True}), service)
        self.assertEqual(result, {})
        self.assertTrue(any(fields.get('status') == 'tool_result_delivery_retained'
                            for _, fields in service.records))

    def test_bootstrap_exact_tool_scope_and_failure_are_closed(self):
        parsed = bootstrap._parse_event(json.dumps(goal_event()).encode(), 'PreToolUse')
        self.assertEqual(parsed['tool_name'], SPATIAL_CLEARANCE_SEGMENT)
        for tool in (SPATIAL_CLEARANCE_SEGMENT + '_other', 'mcp__blender__execute_blender_code'):
            with self.assertRaises(ValueError):
                bootstrap._parse_event(json.dumps(goal_event(tool_name=tool)).encode(), 'PreToolUse')
        result = bootstrap._failure_output(goal_event())
        self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_bootstrap_dispatches_goal_pre_to_core_and_post_remains_light(self):
        event = goal_event()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text(json.dumps({'schema_version': '1.0', 'enabled': True}), encoding='utf-8')
            incoming = io.TextIOWrapper(io.BytesIO(json.dumps(event).encode()), encoding='utf-8')
            outgoing = io.StringIO()
            with patch.object(sys, 'stdin', incoming), patch.object(sys, 'stdout', outgoing), \
                    patch.object(bootstrap, '_engine_entry') as loader:
                loader.return_value.return_value = {'core_dispatch': True}
                bootstrap.main(['--config', str(path), '--event', 'PreToolUse'])
                loader.return_value.assert_called_once()
            self.assertEqual(json.loads(outgoing.getvalue()), {'core_dispatch': True})
        service = NoSceneHookService()
        handled, output, _ = bootstrap.try_light_route(goal_event('PostToolUse'), service)
        self.assertTrue(handled)
        self.assertEqual(output, {})


class ClearanceSegmentSetupTests(unittest.TestCase):
    @staticmethod
    def spec(event=None, config='/project/config.json'):
        argv = ['/engine/python', '-B', '/engine/live_entry.py', 'hook', '--agent', 'claude']
        if event is not None:
            argv += ['--event', event]
        return setup._hook_spec([*argv, '--config', config], 'claude', 'posix')[0]

    def merge(self, value):
        return setup._merge_hooks(value, self.spec(), '/engine/live_entry.py', 'posix',
            event_specs={event: self.spec(event) for event in bootstrap.HOOK_EVENTS})

    def test_legacy_group_is_retained_new_group_added_once_without_widening_matcher(self):
        legacy = {'hooks': {event: [{**({'matcher': setup.TRANSFORM_MATCHER}
                    if event != 'UserPromptSubmit' else {}), 'hooks': [self.spec()]}]
                    for event in bootstrap.HOOK_EVENTS}, 'permissions': {'deny': ['retained']}}
        before = copy.deepcopy(legacy)
        self.assertTrue(self.merge(legacy))
        for event in bootstrap.HOOK_EVENTS:
            self.assertEqual(legacy['hooks'][event][0], before['hooks'][event][0])
            expected_count = 1 if event == 'UserPromptSubmit' else 2
            self.assertEqual(len(legacy['hooks'][event]), expected_count)
            if event != 'UserPromptSubmit':
                self.assertEqual(legacy['hooks'][event][1]['matcher'], setup.CLEARANCE_SEGMENT_MATCHER)
        self.assertFalse(self.merge(legacy))
        self.assertEqual(legacy['permissions'], before['permissions'])
        self.assertIsNone(re.fullmatch(setup.TRANSFORM_MATCHER, SPATIAL_CLEARANCE_SEGMENT))
        self.assertIsNone(re.fullmatch(setup.CLEARANCE_SEGMENT_MATCHER, bootstrap.SPATIAL_TRANSFORM))

    def test_goal_duplicate_wrong_config_or_unknown_matcher_remain_conflicts(self):
        original = {}
        self.merge(original)
        for mode in ('duplicate', 'wrong_config', 'wide_matcher', 'wrong_event'):
            value = copy.deepcopy(original)
            group = value['hooks']['PreToolUse'][1]
            if mode == 'duplicate':
                value['hooks']['PreToolUse'].append(copy.deepcopy(group))
            elif mode == 'wrong_config':
                group['hooks'] = [self.spec('PreToolUse', config='/other/config.json')]
            elif mode == 'wide_matcher':
                group['matcher'] = '.*'
            else:
                group['hooks'] = [self.spec('PostToolUse')]
            with self.subTest(mode=mode), self.assertRaises(setup.AgentSetupError):
                self.merge(value)

    def test_append_only_json_preserves_every_original_byte(self):
        original = {'unrelated': {'escape': '中文', 'number': 1.0},
                    'hooks': {'PreToolUse': [{'matcher': setup.TRANSFORM_MATCHER,
                                             'hooks': [self.spec()]}]}, 'tail': [1, 2]}
        raw = b'\xef\xbb\xbf' + (json.dumps(original, ensure_ascii=True, indent=4)
                                 .replace('\n', '\r\n') + '\r\n').encode()
        after = copy.deepcopy(original)
        self.merge(after)
        actual = setup._append_hook_json(raw, original, after)
        self.assertEqual(json.loads(actual), after)
        self.assertTrue(actual.startswith(b'\xef\xbb\xbf'))
        # Insertions may split existing arrays/objects, but cannot remove or
        # normalize any original byte, including escape spelling and CRLF.
        cursor = iter(actual)
        self.assertTrue(all(any(value == byte for value in cursor) for byte in raw))
        self.assertIn(b'"escape": "\\u4e2d\\u6587"', actual)
        self.assertIn(b'"number": 1.0', actual)
        self.assertEqual(setup._append_hook_json(actual, after, after), actual)

    def test_append_only_json_refuses_removal_or_replacement(self):
        original = {'hooks': {'PreToolUse': [{'matcher': 'other', 'hooks': []}]}, 'keep': 2}
        raw = json.dumps(original).encode()
        for modified in ({'hooks': {}}, {**original, 'keep': 3}, {**original, 'keep': 2.0},
                         {**original, 'hooks': {'PreToolUse': []}}):
            with self.assertRaises(setup.AgentSetupError):
                setup._append_hook_json(raw, original, modified)


if __name__ == '__main__':
    unittest.main()

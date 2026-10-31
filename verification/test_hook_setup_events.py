"""Trusted hook registration metadata with no runtime/Blender execution."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

from human_eye_plugin import agent_setup as setup


EVENTS = ('UserPromptSubmit', 'PreToolUse', 'PostToolUse')


class HookSetupEventTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='trusted hook setup ')
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name).resolve()
        self.project = self.folder / "project 中文 ' & $"
        self.project.mkdir()
        self.engine = self.folder / 'engine'
        for relative in ('examples/agents/live_entry.py', 'human_eye_plugin/live_service.py', 'human_eye_hook.py'):
            path = self.engine / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# Synthetic setup path fixture; never executed.\n', encoding='utf-8')

    def plan(self, agent='claude', **kwargs):
        return setup.build_setup_plan(agent, self.project, engine_root=self.engine, **kwargs)

    def settings(self, agent='claude'):
        path = self.project / ('.claude/settings.json' if agent == 'claude' else '.codex/hooks.json')
        return path, json.loads(path.read_text(encoding='utf-8'))

    def test_each_fresh_command_binds_the_registered_event_and_exact_spatial_tools(self):
        plan = self.plan()
        preview = plan.preview()
        plan.apply()
        _, settings = self.settings()
        for event in EVENTS:
            matchers = [None] if event == 'UserPromptSubmit' else [setup.TRANSFORM_MATCHER, setup.CLEARANCE_SEGMENT_MATCHER]
            self.assertEqual([group.get('matcher') for group in settings['hooks'][event]], matchers)
            for group in settings['hooks'][event]:
                hook, = group['hooks']
                argv = setup._command_argv(hook, 'windows' if sys.platform == 'win32' else 'posix')
                self.assertEqual(argv, preview['hook_argv_by_event'][event])
                self.assertEqual(argv.count('--event'), 1)
                self.assertEqual(argv[argv.index('--event') + 1], event)
                self.assertEqual(argv[-2:], ['--config', (self.project / '.human-eye/live-connector.json').as_posix()])
        self.assertNotIn('--event', preview['hook_argv'])  # Compatible common-argv display.

    def test_windows_encoded_commands_round_trip_trusted_event(self):
        plan = self.plan('codex', platform='windows')
        plan.apply()
        _, settings = self.settings('codex')
        for event in EVENTS:
            hook = settings['hooks'][event][0]['hooks'][0]
            self.assertEqual(setup._command_argv(hook, 'windows'), plan.hook_argv_by_event[event])
            self.assertIn("'--event' '" + event + "'", plan.hook_scripts_by_event[event])

    def test_legal_legacy_common_commands_are_preserved_without_duplication(self):
        plan = self.plan()
        legacy_spec, _ = setup._hook_spec(plan.hook_argv, 'claude', 'posix')
        document = {'hooks': {event: [{**({'matcher': setup.TRANSFORM_MATCHER} if event != 'UserPromptSubmit' else {}),
            'hooks': [copy.deepcopy(legacy_spec)]}] for event in EVENTS}}
        path = self.project / '.claude/settings.json'
        path.parent.mkdir()
        path.write_bytes(setup._encode(document))
        before = path.read_bytes()
        self.plan(platform='posix').apply()
        updated = json.loads(path.read_bytes())
        for event in EVENTS:
            self.assertEqual(updated['hooks'][event][0], document['hooks'][event][0])
            if event != 'UserPromptSubmit':
                self.assertEqual(len(updated['hooks'][event]), 2)
                self.assertEqual(updated['hooks'][event][1]['matcher'], setup.CLEARANCE_SEGMENT_MATCHER)
        self.assertNotEqual(path.read_bytes(), before)
        self.assertEqual(self.plan(platform='posix').changes, [])

    def test_mixed_legacy_and_trusted_commands_remain_idempotent(self):
        plan = self.plan(platform='posix')
        plan.apply()
        path, settings = self.settings()
        legacy, _ = setup._hook_spec(plan.hook_argv, 'claude', 'posix')
        settings['hooks']['PostToolUse'][0]['hooks'] = [legacy]
        path.write_bytes(setup._encode(settings))
        before = path.read_bytes()
        self.assertEqual(self.plan(platform='posix').changes, [])
        self.assertEqual(path.read_bytes(), before)

    def test_wrong_trusted_event_is_a_conflict_and_preserves_configuration(self):
        self.plan().apply()
        path, settings = self.settings()
        args = settings['hooks']['PreToolUse'][0]['hooks'][0]['args']
        args[args.index('--event') + 1] = 'UserPromptSubmit'
        path.write_bytes(setup._encode(settings))
        before = path.read_bytes()
        with self.assertRaisesRegex(setup.AgentSetupError, 'Conflicting'):
            self.plan()
        self.assertEqual(path.read_bytes(), before)

    def test_duplicate_legacy_and_event_command_requires_review(self):
        plan = self.plan(platform='posix')
        plan.apply()
        path, settings = self.settings()
        legacy, _ = setup._hook_spec(plan.hook_argv, 'claude', 'posix')
        settings['hooks']['PreToolUse'][0]['hooks'].append(legacy)
        path.write_bytes(setup._encode(settings))
        with self.assertRaisesRegex(setup.AgentSetupError, 'Duplicate'):
            self.plan(platform='posix')

    def test_new_root_and_console_entries_cannot_hide_conflicting_engine(self):
        for command in ('python -m human_eye_hook --config wrong.json',
                        'human-eye-hook --config wrong.json',
                        'python /other/human_eye_hook.py --config wrong.json'):
            with self.subTest(command=command):
                settings = {'hooks': {'PreToolUse': [{'matcher': setup.TRANSFORM_MATCHER,
                    'hooks': [{'type': 'command', 'command': command, 'timeout': 30}]}]}}
                spec, _ = setup._hook_spec(self.plan().hook_argv, 'claude', 'posix')
                with self.assertRaisesRegex(setup.AgentSetupError, 'Conflicting'):
                    setup._merge_hooks(settings, spec, self.engine, 'posix')

    def test_passive_mcp_has_no_trusted_hook_registration(self):
        preview = self.plan('mcp').preview()
        self.assertEqual(preview['hook_argv_by_event'], {})
        self.assertEqual(preview['hook_scripts_by_event'], {})
        self.assertIsNone(preview['hook_argv'])


if __name__ == '__main__':
    unittest.main()

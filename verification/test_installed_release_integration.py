"""Temporary-project administration tests; no real project or host writes."""
import base64
import copy
from contextlib import contextmanager
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin import agent_setup
from human_eye_plugin.host_runtime import GuardedHostRuntime
from human_eye_plugin.runtime_identity import runtime_identity
from verification.test_host_runtime import MutableHost


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = Path(agent_setup.__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('test_installed_release_tool', ROOT / 'examples/agents/installed_release.py')
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)
GOAL_MATCHER = '^mcp__human_eye_live__human_eye_clearance_segment$'


class InstalledIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="installed release ' 中文 ")
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name).resolve()
        self.config_path = self.project / '.human-eye/custom-connector.json'
        self.state_path = self.project / '.human-eye/custom-state.json'
        self.config = {'schema_version': '1.0', 'enabled': False, 'observe_on_prompt': True,
            'project_root': str(ROOT), 'state_file': self.state_path.name,
            'audit_file': 'custom-events.jsonl', 'quad_size': 64, 'max_sessions': 16,
            'readback_atol_m': 1e-6, 'blender': {'host': '127.0.0.1', 'port': 9876, 'timeout_s': 10},
            'expected_identity': {'build_id': 'sha256:old', 'implementation_revision': 'old'}}
        self.put(self.config_path, agent_setup._encode(self.config))
        runtime = GuardedHostRuntime(MutableHost(), quad_size=64, max_sessions=16)
        runtime.before_model(session_id='retained', task_instruction='Measure the gap.',
            focal_id='part', reference_id='base', messages=[], include_image=False)
        self.state = {'schema_version': '1.0', 'config_fingerprint': tool._fingerprint(self.config),
                      'runtime': runtime.export_state(), 'inflight': None,
                      'operator_note': '保留此原文及排版'}
        self.state = json.loads(json.dumps(self.state))
        self.put(self.state_path, b'\xef\xbb\xbf' + json.dumps(self.state, ensure_ascii=False, indent=3).replace('\n', '\r\n').encode())
        identity = runtime_identity(mode='live')
        identity.pop('source_files', None)
        identity.update(source_kind='installed_distribution', build_id='sha256:new-test-build')
        self.target = {'identity': identity, 'python': str(Path(sys.executable).resolve()),
                       'prefix': str(Path(sys.prefix).resolve()), 'module_root': str(RUNTIME_ROOT),
                       'module_origins': {'human_eye_plugin.agent_setup': str(Path(agent_setup.__file__).resolve())}}
        self.proof_patch = patch.object(tool, '_installed_runtime', side_effect=lambda: copy.deepcopy(self.target))
        self.proof_patch.start()
        self.addCleanup(self.proof_patch.stop)
        self.server_path = self.project / '.codex/config.toml'
        self.hook_path = self.project / '.codex/hooks.json'
        self.register()

    def put(self, path, raw):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return path

    def register(self, agent='codex'):
        server = {'command': str(Path(sys.executable).resolve()),
            'args': ['-I', '-B', '-m', 'human_eye_plugin.production_server', '--config', str(self.config_path)],
            'enabled': False, 'startup_timeout_sec': 42, 'tool_timeout_sec': 65,
            'cwd': str(self.project), 'env': {'USER_SETTING': 'preserve'}}
        if agent == 'codex':
            text = ('# untouched learning settings\r\n[mcp_servers.agent_learning]\r\nenabled = false\r\ncommand = "learning"\r\n\r\n'
                    '[mcp_servers.human_eye_live]\r\n')
            for key, value in server.items():
                if key != 'env':
                    text += key + ' = ' + json.dumps(value, ensure_ascii=False) + '\r\n'
            text += '[mcp_servers.human_eye_live.env]\r\nUSER_SETTING = "preserve"\r\n'
            self.put(self.server_path, text.encode())
        else:
            self.put(self.project / '.mcp.json', agent_setup._encode({'mcpServers': {'thirdparty': {'command': 'other'},
                                                                                      'human_eye_live': server}}))
        hooks = {'hooks': {}, 'user_preference': {'disabled': True}}
        for event in tool.EVENTS:
            argv = [server['command'], '-I', '-B', '-m', 'human_eye_plugin.live_hooks',
                    '--agent', agent, '--config', str(self.config_path)]
            spec, _ = tool._hook_spec(argv, agent, 'windows')
            spec['timeout'] = 81
            group = {'hooks': [{'type': 'command', 'command': 'agent-learning-safe-helper', 'timeout': 4}, spec]}
            if event != 'UserPromptSubmit':
                group['matcher'] = tool.TRANSFORM_MATCHER
            hooks['hooks'][event] = [group]
        path = self.hook_path if agent == 'codex' else self.project / '.claude/settings.json'
        self.put(path, agent_setup._encode(hooks))

    def plan(self, agent='codex', **kwargs):
        return tool.build_plan(agent, self.project, expected_build='sha256:new-test-build', platform='windows', **kwargs)

    def tree(self):
        return {path.relative_to(self.project).as_posix(): path.read_bytes() for path in self.project.rglob('*') if path.is_file()}

    def goal_group(self, event, *, thirdparty=False):
        document = json.loads(self.hook_path.read_text(encoding='utf-8-sig'))
        original = document['hooks'][event][0]
        group = {'matcher': GOAL_MATCHER, 'hooks': [copy.deepcopy(original['hooks'][-1])],
                 'user_metadata': {'keep': True}}
        group['hooks'][0]['timeout'] = 93
        if thirdparty:
            group['hooks'].insert(0, {'type': 'command', 'command': 'independent-goal-audit', 'timeout': 17})
        return group

    def test_declared_goal_capability_adds_exact_pre_and_post_scopes(self):
        self.plan().apply()
        document = json.loads(self.hook_path.read_text(encoding='utf-8-sig'))
        self.assertEqual(len(document['hooks']['UserPromptSubmit']), 1)
        for event in ('PreToolUse', 'PostToolUse'):
            groups = document['hooks'][event]
            goals = [group for group in groups if group.get('matcher') == GOAL_MATCHER]
            self.assertEqual(len(goals), 1)
            self.assertEqual(len(goals[0]['hooks']), 1)
            argv = tool._strict_hook_argv(goals[0]['hooks'][0], 'windows', 'codex')
            self.assertEqual(argv[argv.index('--event')+1], event)
            self.assertEqual(argv[argv.index('--config')+1], str(self.config_path))

    def test_existing_goal_scope_preserves_thirdparty_metadata_and_owned_timeout(self):
        document = json.loads(self.hook_path.read_text(encoding='utf-8-sig'))
        for event in ('PreToolUse', 'PostToolUse'):
            document['hooks'][event].append(self.goal_group(event, thirdparty=True))
        self.put(self.hook_path, tool._encode(document))
        self.plan().apply()
        actual = json.loads(self.hook_path.read_text(encoding='utf-8-sig'))
        for event in ('PreToolUse', 'PostToolUse'):
            group = next(group for group in actual['hooks'][event] if group.get('matcher') == GOAL_MATCHER)
            self.assertEqual(group['hooks'][0], document['hooks'][event][-1]['hooks'][0])
            self.assertEqual(group['user_metadata'], {'keep': True})
            self.assertEqual(group['hooks'][1]['timeout'], 93)
            argv = tool._strict_hook_argv(group['hooks'][1], 'windows', 'codex')
            self.assertEqual(argv[3:5], ['-m', 'human_eye_hook'])

    def test_replanning_goal_capable_install_does_not_duplicate_hooks(self):
        self.plan().apply()
        before = self.hook_path.read_bytes()
        again = self.plan()
        self.assertFalse(any(change.path == self.hook_path for change in again.changes))
        self.assertEqual(before, self.hook_path.read_bytes())
        document = json.loads(before)
        for event in ('PreToolUse', 'PostToolUse'):
            self.assertEqual(sum(group.get('matcher') == GOAL_MATCHER for group in document['hooks'][event]), 1)

    def test_goal_capability_requires_explicit_boolean_true(self):
        for capabilities in (None, {}, {'bounded_clearance_segment': False},
                             {'bounded_clearance_segment': 1}, {'bounded_clearance_segment': 'true'}):
            with self.subTest(capabilities=capabilities):
                self.register()
                if capabilities is None:
                    self.target['identity'].pop('capabilities', None)
                else:
                    self.target['identity']['capabilities'] = capabilities
                self.plan().apply()
                document = json.loads(self.hook_path.read_text(encoding='utf-8-sig'))
                for event in ('PreToolUse', 'PostToolUse'):
                    self.assertFalse(any(group.get('matcher') == GOAL_MATCHER for group in document['hooks'][event]))

    def test_old_target_removes_only_owned_goal_hooks_and_keeps_thirdparty_scope(self):
        document = json.loads(self.hook_path.read_text(encoding='utf-8-sig'))
        for event in ('PreToolUse', 'PostToolUse'):
            document['hooks'][event].append(self.goal_group(event, thirdparty=True))
        self.put(self.hook_path, tool._encode(document))
        self.target['identity'].pop('capabilities', None)
        self.plan().apply()
        actual = json.loads(self.hook_path.read_text(encoding='utf-8-sig'))
        for event in ('PreToolUse', 'PostToolUse'):
            group = next(group for group in actual['hooks'][event] if group.get('matcher') == GOAL_MATCHER)
            self.assertEqual(group['hooks'], [document['hooks'][event][-1]['hooks'][0]])
            self.assertEqual(group['user_metadata'], {'keep': True})
            self.assertEqual(actual['hooks'][event][0]['hooks'][1]['timeout'], 81)

    def test_old_target_removes_empty_owned_goal_groups(self):
        document = json.loads(self.hook_path.read_text(encoding='utf-8-sig'))
        for event in ('PreToolUse', 'PostToolUse'):
            group = self.goal_group(event)
            group.pop('user_metadata')
            document['hooks'][event].append(group)
        self.put(self.hook_path, tool._encode(document))
        self.target['identity']['capabilities']['bounded_clearance_segment'] = False
        self.plan().apply()
        actual = json.loads(self.hook_path.read_text(encoding='utf-8-sig'))
        for event in ('PreToolUse', 'PostToolUse'):
            self.assertFalse(any(group.get('matcher') == GOAL_MATCHER for group in actual['hooks'][event]))

    def test_duplicate_owned_goal_hooks_refuse_even_on_downgrade(self):
        for supported in (True, False):
            with self.subTest(supported=supported):
                self.register()
                document = json.loads(self.hook_path.read_text(encoding='utf-8-sig'))
                group = self.goal_group('PreToolUse')
                document['hooks']['PreToolUse'].extend([group, copy.deepcopy(group)])
                self.put(self.hook_path, tool._encode(document))
                self.target['identity']['capabilities']['bounded_clearance_segment'] = supported
                before = self.tree()
                with self.assertRaisesRegex(agent_setup.AgentSetupError, 'Duplicate'):
                    self.plan()
                self.assertEqual(self.tree(), before)

    def test_broad_goal_matcher_and_wrong_goal_connector_are_not_rewritten(self):
        for mutation in ('broad_scope', 'wrong_connector', 'wrong_event'):
            with self.subTest(mutation=mutation):
                self.register()
                document = json.loads(self.hook_path.read_text(encoding='utf-8-sig'))
                group = self.goal_group('PreToolUse')
                if mutation == 'broad_scope':
                    group['matcher'] = GOAL_MATCHER + '|other_tool'
                else:
                    argv = tool._strict_hook_argv(group['hooks'][0], 'windows', 'codex')
                    if mutation == 'wrong_connector':
                        argv[argv.index('--config')+1] = str(self.project/'.human-eye/other.json')
                    else:
                        argv += ['--event', 'PostToolUse']
                    group['hooks'][0], _ = tool._hook_spec(argv, 'codex', 'windows')
                document['hooks']['PreToolUse'].append(group)
                self.put(self.hook_path, tool._encode(document))
                before = self.tree()
                with self.assertRaises(agent_setup.AgentSetupError):
                    self.plan()
                self.assertEqual(self.tree(), before)

    def test_helper_import_and_legacy_target_do_not_require_new_setup_constant(self):
        value = agent_setup.__dict__.pop('CLEARANCE_SEGMENT_MATCHER')
        try:
            spec = importlib.util.spec_from_file_location('legacy_setup_compatible_release_tool', ROOT/'examples/agents/installed_release.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertTrue(callable(module.build_plan))
        finally:
            agent_setup.CLEARANCE_SEGMENT_MATCHER = value

    def test_plan_and_preview_write_no_files_directories_or_locks(self):
        before, directories = self.tree(), sorted(str(p) for p in self.project.rglob('*') if p.is_dir())
        preview = self.plan().preview()
        self.assertFalse(preview['applied'])
        self.assertEqual(before, self.tree())
        self.assertEqual(directories, sorted(str(p) for p in self.project.rglob('*') if p.is_dir()))
        self.assertFalse((self.project / '.human-eye/setup.lock').exists())
        self.assertFalse(self.state_path.with_name(self.state_path.name+'.lock').exists())
        self.assertEqual(preview['connector_path'], str(self.config_path))

    def test_fp_only_migration_preserves_runtime_journal_and_non_fp_bytes(self):
        before = self.state_path.read_bytes()
        old_binding = tool._fingerprint(self.config)
        plan = self.plan(); preview = plan.preview()
        result = plan.apply(plan_sha256=preview['plan_sha256'])
        after = self.state_path.read_bytes()
        expected = tool._state_binding_bytes(before, old_binding, preview['state_migration']['new_config_fingerprint'])
        self.assertEqual(after, expected)
        self.assertTrue(after.startswith(b'\xef\xbb\xbf'))
        actual = tool._json_object(after, 'state')
        self.assertEqual(actual['runtime'], self.state['runtime'])
        self.assertEqual(actual['inflight'], self.state['inflight'])
        self.assertEqual(len(actual['runtime']['sessions']), 1)
        self.assertTrue(result['restart_required']); self.assertFalse(result['hot_reload'])
        self.assertFalse(tool._json_object(self.config_path.read_bytes(), 'config')['enabled'])
        manifest = tool._json_object(Path(result['backup_manifest']).read_bytes(), 'manifest')
        self.assertEqual(manifest['status'], 'applied')
        self.assertEqual(manifest['files'][-1]['path'], '.human-eye/custom-state.json')

    def test_thirdparty_config_disabled_settings_and_existing_hook_timeout_survive(self):
        original_hooks = json.loads(self.hook_path.read_text(encoding='utf-8-sig'))
        self.plan().apply()
        toml = tool.tomllib.loads(self.server_path.read_text(encoding='utf-8-sig'))
        self.assertEqual(toml['mcp_servers']['agent_learning'], {'enabled': False, 'command': 'learning'})
        server = toml['mcp_servers']['human_eye_live']
        self.assertFalse(server['enabled']); self.assertEqual(server['tool_timeout_sec'], 65)
        self.assertEqual(server['env'], {'USER_SETTING': 'preserve'})
        self.assertTrue(self.server_path.read_bytes().startswith(b'# untouched learning settings\r\n'))
        hooks = json.loads(self.hook_path.read_text(encoding='utf-8-sig'))
        self.assertEqual(hooks['user_preference'], original_hooks['user_preference'])
        for event in tool.EVENTS:
            group = hooks['hooks'][event][0]
            self.assertEqual(group['hooks'][0], original_hooks['hooks'][event][0]['hooks'][0])
            self.assertEqual(group['hooks'][1]['timeout'], 81)
            argv = tool._strict_hook_argv(group['hooks'][1], 'windows', 'codex')
            self.assertEqual(argv[1:5], ['-I', '-B', '-m', 'human_eye_hook'])
            self.assertEqual(argv[argv.index('--event')+1], event)
            self.assertEqual(argv[argv.index('--config')+1], str(self.config_path))

    def test_claude_direct_spawn_preserves_other_mcp_servers(self):
        self.register('claude')
        self.plan('claude').apply()
        doc = json.loads((self.project/'.mcp.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(doc['mcpServers']['thirdparty'], {'command': 'other'})
        hooks = json.loads((self.project/'.claude/settings.json').read_text(encoding='utf-8-sig'))
        for event in tool.EVENTS:
            hook = hooks['hooks'][event][0]['hooks'][1]
            self.assertIn('args', hook)
            self.assertEqual(hook['args'][hook['args'].index('--event')+1], event)

    def test_generic_manifest_is_not_registered_agent_hooks(self):
        before_codex = self.hook_path.read_bytes()
        plan = self.plan('genericmcp', config_path=self.config_path)
        self.assertEqual(plan.preview()['hooks']['registration'], 'host_integration_required')
        plan.apply()
        manifest = json.loads((self.project/'.human-eye/installed-hooks.json').read_text(encoding='utf-8-sig'))
        self.assertFalse(manifest['actual_host_dispatch_verified'])
        self.assertEqual(set(manifest['argv_by_event']), set(tool.EVENTS))
        self.assertEqual(self.hook_path.read_bytes(), before_codex)

    def test_unknown_encoded_outer_shell_prefix_suffix_flags_or_executable_are_refused(self):
        original = json.loads(self.hook_path.read_text(encoding='utf-8-sig'))
        command = original['hooks']['PreToolUse'][0]['hooks'][1]['command']
        bad_commands = ['cmd.exe /c echo THIRD_PARTY && ' + command,
                        command + ' && echo THIRD_PARTY', command + '; echo THIRD_PARTY',
                        command.replace(' -NoProfile', ' -NoLogo -NoProfile'),
                        command.replace('powershell.exe', 'untrusted-powershell.exe'),
                        command.replace('-EncodedCommand ', '-EncodedCommand not_base64_')]
        for value in bad_commands:
            with self.subTest(command=value[:100]):
                document = copy.deepcopy(original)
                document['hooks']['PreToolUse'][0]['hooks'][1]['command'] = value
                raw = agent_setup._encode(document); self.put(self.hook_path, raw)
                with self.assertRaises(agent_setup.AgentSetupError):
                    self.plan()
                self.assertEqual(self.hook_path.read_bytes(), raw)

    def test_encoded_payload_inside_directspawn_args_is_not_left_as_second_hook(self):
        self.register('claude')
        path = self.project/'.claude/settings.json'
        original = json.loads(path.read_text(encoding='utf-8'))
        argv = original['hooks']['PreToolUse'][0]['hooks'][1]
        inner = [argv['command'], *argv['args']]
        _, source = tool._hook_spec(inner, 'codex', 'windows')
        payload = base64.b64encode(source.encode('utf-16-le')).decode('ascii')
        for command, args in (('powershell.exe', ['-NoProfile', '-EncodedCommand', payload]),
                              ('powershell.exe', ['-enc', payload]),
                              ('pwsh.exe', ['-ec', payload]),
                              ('cmd.exe', ['/c', 'powershell.exe', '-EncodedCommand', payload])):
            with self.subTest(command=command, flag=args[-2]):
                document = copy.deepcopy(original)
                document['hooks']['PreToolUse'][0]['hooks'][1] = {'type': 'command', 'command': command, 'args': args}
                raw = agent_setup._encode(document); self.put(path, raw)
                with self.assertRaises(agent_setup.AgentSetupError): self.plan('claude')
                self.assertEqual(path.read_bytes(), raw)

    def test_all_encodedcommand_prefixes_cannot_hide_engine_ownership(self):
        self.register('claude')
        path = self.project/'.claude/settings.json'
        original = json.loads(path.read_text(encoding='utf-8'))
        old_hook = original['hooks']['PreToolUse'][0]['hooks'][1]
        _, source = tool._hook_spec([old_hook['command'], *old_hook['args']], 'codex', 'windows')
        payload = base64.b64encode(source.encode('utf-16-le')).decode('ascii')
        desired = self.plan('claude').hooks['argv_by_event']
        prefixes = ['encodedcommand'[:length] for length in range(1, len('encodedcommand')+1)] + ['ec']
        for prefix in prefixes:
            for layout in ('args', 'command', 'colon', 'outer_chain'):
                with self.subTest(prefix=prefix, layout=layout):
                    flag = '-' + prefix[0].upper() + prefix[1:]
                    if layout == 'args':
                        hook = {'type': 'command', 'command': 'powershell.exe', 'args': ['-NoProfile', flag, payload]}
                    else:
                        command = 'powershell.exe '+flag+(':' if layout == 'colon' else ' ')+payload
                        if layout == 'outer_chain': command = 'cmd.exe /c echo THIRD_PARTY && '+command
                        hook = {'type': 'command', 'command': command}
                    document = copy.deepcopy(original)
                    document['hooks']['PreToolUse'][0]['hooks'][1] = hook
                    with self.assertRaises(agent_setup.AgentSetupError):
                        tool._merge_installed_hooks(document, desired, 'claude', 'windows', self.config_path)

    def test_encoded_argument_prefixes_and_unknown_flag_payloads_are_conservative(self):
        self.register('claude')
        original = json.loads((self.project/'.claude/settings.json').read_text(encoding='utf-8'))
        hook = original['hooks']['PreToolUse'][0]['hooks'][1]
        _, source = tool._hook_spec([hook['command'], *hook['args']], 'codex', 'windows')
        payload = base64.b64encode(source.encode('utf-16-le')).decode('ascii')
        desired = self.plan('claude').hooks['argv_by_event']
        flags = ['encodedarguments'[:length] for length in range(1,len('encodedarguments')+1)]
        flags += ['ea', 'an_unrecognized_flag']
        for flag in flags:
            with self.subTest(flag=flag):
                document = copy.deepcopy(original)
                document['hooks']['PreToolUse'][0]['hooks'][1] = {'type': 'command', 'command': 'pwsh.exe',
                    'args': ['-'+flag, payload]}
                with self.assertRaises(agent_setup.AgentSetupError):
                    tool._merge_installed_hooks(document, desired, 'claude', 'windows', self.config_path)

    def test_first_registration_and_repeated_plan_are_byte_idempotent(self):
        for agent in ('codex', 'claude'):
            with self.subTest(agent=agent):
                self.put(self.config_path, agent_setup._encode(self.config))
                self.put(self.state_path, agent_setup._encode(self.state))
                self.register(agent)
                hook_path = self.hook_path if agent == 'codex' else self.project/'.claude/settings.json'
                hook_path.unlink()
                self.plan(agent).apply()
                before = self.tree()
                preview = self.plan(agent).preview()
                self.assertEqual(preview['changes'], [])
                result = self.plan(agent).apply(plan_sha256=preview['plan_sha256'])
                self.assertIsNone(result['backup_manifest'])
                self.assertEqual(self.tree(), before)

    def test_complete_canonical_powershell_for_claude_is_owned_and_migrated(self):
        self.register('claude')
        path = self.project/'.claude/settings.json'
        document = json.loads(path.read_text(encoding='utf-8'))
        for event in tool.EVENTS:
            hook = document['hooks'][event][0]['hooks'][1]
            document['hooks'][event][0]['hooks'][1] = tool._hook_spec([hook['command'], *hook['args']], 'codex', 'windows')[0]
        self.put(path, agent_setup._encode(document))
        self.plan('claude').apply()
        actual = json.loads(path.read_text(encoding='utf-8'))
        for event in tool.EVENTS:
            self.assertEqual(len(actual['hooks'][event]), 1 if event == 'UserPromptSubmit' else 2)
            group = actual['hooks'][event][0]
            self.assertEqual(len(group['hooks']), 2)
            self.assertIn('--event', group['hooks'][1]['args'])
            if event != 'UserPromptSubmit':
                goal = next(item for item in actual['hooks'][event] if item.get('matcher') == GOAL_MATCHER)
                self.assertEqual(len(goal['hooks']), 1)
                self.assertEqual(goal['hooks'][0]['args'][goal['hooks'][0]['args'].index('--event')+1], event)

    def test_real_thirdparty_encoded_payload_is_preserved(self):
        document = json.loads(self.hook_path.read_text(encoding='utf-8'))
        payload = base64.b64encode("Write-Output 'thirdparty-only'".encode('utf-16-le')).decode('ascii')
        thirdparty = {'type': 'command', 'command': 'powershell.exe',
                      'args': ['-NoProfile', '-EncodedCommand', payload], 'timeout': 7}
        document['hooks']['PreToolUse'][0]['hooks'].insert(0, thirdparty)
        self.put(self.hook_path, agent_setup._encode(document))
        self.plan().apply()
        actual = json.loads(self.hook_path.read_text(encoding='utf-8'))
        self.assertEqual(actual['hooks']['PreToolUse'][0]['hooks'][0], thirdparty)
        self.assertEqual(len(actual['hooks']['PreToolUse'][0]['hooks']), 3)

    def test_malformed_hook_args_refuse_instead_of_appending_another_hook(self):
        original = json.loads(self.hook_path.read_text(encoding='utf-8'))
        for args in (None, '-EncodedCommand mystery', [1, '--config']):
            with self.subTest(args=args):
                document = copy.deepcopy(original)
                document['hooks']['PreToolUse'][0]['hooks'][1]['args'] = args
                self.put(self.hook_path, agent_setup._encode(document))
                before = self.tree()
                with self.assertRaises(agent_setup.AgentSetupError): self.plan()
                self.assertEqual(self.tree(), before)

    def test_wrong_connector_duplicate_hooks_and_wrong_event_pin_are_refused(self):
        original = json.loads(self.hook_path.read_text(encoding='utf-8-sig'))
        for kind in ('connector', 'duplicate', 'event'):
            with self.subTest(kind=kind):
                document = copy.deepcopy(original)
                group = document['hooks']['PreToolUse'][0]
                if kind == 'duplicate':
                    group['hooks'].append(copy.deepcopy(group['hooks'][1]))
                else:
                    argv = tool._strict_hook_argv(group['hooks'][1], 'windows', 'codex')
                    if kind == 'connector':
                        argv[-1] = str(self.project/'.human-eye/other.json')
                    else:
                        argv += ['--event', 'PostToolUse']
                    group['hooks'][1] = tool._hook_spec(argv, 'codex', 'windows')[0]
                self.put(self.hook_path, agent_setup._encode(document))
                with self.assertRaises(agent_setup.AgentSetupError):
                    self.plan()

    def test_pending_quarantine_inflight_malformed_state_and_bad_binding_refuse_without_writes(self):
        for kind in ('pending', 'quarantine', 'inflight', 'schema', 'binding', 'incompatible'):
            with self.subTest(kind=kind):
                state = copy.deepcopy(self.state)
                if kind == 'pending': state['runtime']['router']['sessions'][0][1]['pending'] = {'operation': 'retained'}
                elif kind == 'quarantine': state['runtime']['quarantine'] = {'reason': 'uncertain', 'last_checked_revision': 'r1'}
                elif kind == 'inflight': state['inflight'] = {'operation_id': 'retained', 'session_id': 'retained', 'started': 1.0}
                elif kind == 'schema': state['schema_version'] = '2.0'
                elif kind == 'binding': state['config_fingerprint'] = 'changed'
                else: state['runtime']['schema_version'] = 'future'
                self.put(self.state_path, agent_setup._encode(state))
                before = self.tree()
                with self.assertRaises(agent_setup.AgentSetupError): self.plan()
                self.assertEqual(self.tree(), before)

    def test_plan_then_state_or_configuration_change_refuses(self):
        for path in (self.state_path, self.hook_path, self.config_path):
            with self.subTest(path=path.name):
                plan = self.plan(); before = path.read_bytes()
                path.write_bytes(before + b'\n')
                with self.assertRaises(agent_setup.AgentSetupError): plan.apply()
                self.assertEqual(path.read_bytes(), before+b'\n')
                path.write_bytes(before)

    def test_dirty_state_arriving_while_waiting_for_live_lock_is_rechecked(self):
        plan = self.plan()
        @contextmanager
        def pending_lock(*args, **kwargs):
            state = copy.deepcopy(self.state); state['inflight'] = {'operation_id': 'arrived'}
            self.put(self.state_path, agent_setup._encode(state))
            yield
        before_config = self.config_path.read_bytes()
        with patch.object(tool, '_state_lock', pending_lock):
            with self.assertRaises(agent_setup.AgentSetupError): plan.apply()
        self.assertEqual(self.config_path.read_bytes(), before_config)
        self.assertEqual(json.loads(self.state_path.read_text(encoding='utf-8-sig'))['inflight'], {'operation_id': 'arrived'})

    def test_failure_rolls_back_exact_bytes_and_preserves_old_backup(self):
        prior = self.put(self.project/'.human-eye/setup-backups/older/manifest.json', b'{"status":"prepared","retained":true}')
        before = self.tree(); original_atomic = tool._atomic_bytes
        def fail(path, raw):
            if path == self.hook_path:
                raise OSError('injected write failure')
            return original_atomic(path, raw)
        with patch.object(tool, '_atomic_bytes', side_effect=fail):
            with self.assertRaisesRegex(agent_setup.AgentSetupError, 'rolled_back'): self.plan().apply()
        for relative, raw in before.items():
            self.assertEqual((self.project/relative).read_bytes(), raw)
        self.assertEqual(prior.read_bytes(), before[prior.relative_to(self.project).as_posix()])
        self.assertFalse((self.project/'.human-eye/setup.lock').exists())

    def test_concurrent_user_edit_is_not_overwritten_by_rollback(self):
        plan = self.plan(); original_atomic = tool._atomic_bytes
        def fail(path, raw):
            if path == self.hook_path:
                self.server_path.write_bytes(b'# concurrent user change\n')
                raise OSError('injected after concurrent edit')
            return original_atomic(path, raw)
        with patch.object(tool, '_atomic_bytes', side_effect=fail):
            with self.assertRaisesRegex(agent_setup.AgentSetupError, 'rollback_incomplete'): plan.apply()
        self.assertEqual(self.server_path.read_bytes(), b'# concurrent user change\n')
        fp = json.loads(self.state_path.read_text(encoding='utf-8-sig'))['config_fingerprint']
        self.assertNotIn(fp, {tool._fingerprint(self.config), plan.preview()['state_migration']['new_config_fingerprint']})
        self.assertEqual(len(fp), 64)
        self.assertEqual(json.loads(self.state_path.read_text(encoding='utf-8-sig'))['runtime'], self.state['runtime'])

    def test_missing_state_refuses_without_creating_directories_or_locks(self):
        self.state_path.unlink()
        before = self.tree()
        with self.assertRaisesRegex(agent_setup.AgentSetupError, 'state_initialization_required'):
            self.plan()
        self.assertEqual(self.tree(), before)
        self.assertFalse((self.project/'.human-eye/setup.lock').exists())
        self.assertFalse(self.state_path.with_name(self.state_path.name+'.lock').exists())

    def test_crash_after_fence_or_connector_keeps_both_generations_blocked(self):
        for stage in ('fence', 'connector'):
            with self.subTest(stage=stage):
                # Each subcase starts with the same persisted runtime, never a
                # cleaned journal manufactured to get the next attempt through.
                self.put(self.config_path, agent_setup._encode(self.config))
                self.put(self.state_path, agent_setup._encode(self.state))
                self.register()
                plan = self.plan(); original_atomic = tool._atomic_bytes
                old_fp = tool._fingerprint(self.config)
                new_fp = plan.preview()['state_migration']['new_config_fingerprint']
                def crash(path, raw):
                    original_atomic(path, raw)
                    if stage == 'fence' and path == self.state_path:
                        raise SystemExit('simulated process death after fence')
                    if stage == 'connector' and path == self.config_path:
                        raise SystemExit('simulated process death after connector')
                with patch.object(tool, '_atomic_bytes', side_effect=crash):
                    with self.assertRaises(SystemExit): plan.apply()
                actual = json.loads(self.state_path.read_text(encoding='utf-8-sig'))
                self.assertNotIn(actual['config_fingerprint'], {old_fp, new_fp})
                self.assertEqual(actual['runtime'], self.state['runtime'])
                self.assertIsNone(actual['inflight'])
                self.assertFalse((self.project/'.human-eye/setup.lock').exists())
                manifests = [json.loads(path.read_text(encoding='utf-8-sig')) for path in (self.project/'.human-eye/setup-backups').glob('*/manifest.json')]
                self.assertTrue(any(item['recovery_required'] for item in manifests))

    def test_caught_failure_after_connector_restores_config_before_old_binding(self):
        before = self.tree(); plan = self.plan(); original_atomic = tool._atomic_bytes
        tripped = False
        def fail(path, raw):
            nonlocal tripped
            original_atomic(path, raw)
            if path == self.config_path and not tripped:
                tripped = True
                raise OSError('simulated error after connector replacement')
            if path == self.state_path and raw == before['.human-eye/custom-state.json']:
                for relative in ('.codex/config.toml', '.codex/hooks.json', '.human-eye/custom-connector.json'):
                    self.assertEqual((self.project/relative).read_bytes(), before[relative])
        with patch.object(tool, '_atomic_bytes', side_effect=fail):
            with self.assertRaisesRegex(agent_setup.AgentSetupError, 'rolled_back'): plan.apply()
        for relative, raw in before.items():
            self.assertEqual((self.project/relative).read_bytes(), raw)

    def test_state_between_eight_and_thirtytwo_mib_uses_state_limit(self):
        state = copy.deepcopy(self.state); state['operator_note'] = 'x' * (8*1024*1024+32)
        self.put(self.state_path, agent_setup._encode(state))
        plan = self.plan(); plan.apply()
        self.assertEqual(json.loads(self.state_path.read_text(encoding='utf-8-sig'))['operator_note'], state['operator_note'])

    def test_exact_config_and_state_reader_boundaries(self):
        path = self.project/'.human-eye/reader-boundary.bin'
        for limit in (8*1024*1024, 32*1024*1024):
            for offset in (-1, 0, 1):
                with self.subTest(limit=limit, offset=offset):
                    raw = b'x' * (limit + offset)
                    self.put(path, raw)
                    if offset <= 0:
                        self.assertEqual(len(tool._read(path, limit)), limit + offset)
                    else:
                        with self.assertRaises(agent_setup.AgentSetupError): tool._read(path, limit)

    def test_reader_rechecks_growth_after_stat(self):
        path = self.put(self.project/'.human-eye/reader-growth.bin', b'x')
        original = Path.read_bytes
        def grew(current):
            return b'x' * 9 if current == path else original(current)
        with patch.object(Path, 'read_bytes', grew):
            with self.assertRaisesRegex(agent_setup.AgentSetupError, 'grew'):
                tool._read(path, 8)

    def test_full_state_at_exact_thirtytwo_mib_migrates_without_changing_other_bytes(self):
        limit = 32*1024*1024
        state = copy.deepcopy(self.state); state['operator_note'] = ''
        empty = json.dumps(state, ensure_ascii=True, separators=(',', ':')).encode('utf-8')
        state['operator_note'] = 'x' * (limit - len(empty))
        raw = json.dumps(state, ensure_ascii=True, separators=(',', ':')).encode('utf-8')
        self.assertEqual(len(raw), limit)
        self.put(self.state_path, raw)
        plan = self.plan(); preview = plan.preview()
        plan.apply()
        actual = self.state_path.read_bytes()
        expected = tool._state_binding_bytes(raw, tool._fingerprint(self.config), preview['state_migration']['new_config_fingerprint'])
        self.assertEqual(len(actual), limit)
        self.assertEqual(actual, expected)

    def test_output_config_eight_mib_limit_is_checked_before_fencing(self):
        base = copy.deepcopy(self.config); base['user_padding'] = ''
        updated = copy.deepcopy(base)
        updated['project_root'] = self.target['module_root']
        updated['expected_identity'] = {key: self.target['identity'][key] for key in tool._PIN_FIELDS}
        padding = tool.MAX_CONFIG - len(tool._encode(updated))
        for offset in (-1, 0, 1):
            with self.subTest(offset=offset):
                config = copy.deepcopy(base); config['user_padding'] = 'x' * (padding + offset)
                self.put(self.config_path, tool._encode(config))
                state = copy.deepcopy(self.state); state['config_fingerprint'] = tool._fingerprint(config)
                self.put(self.state_path, tool._encode(state))
                if offset > 0:
                    before = self.tree()
                    with self.assertRaisesRegex(agent_setup.AgentSetupError, 'Planned output exceeds'):
                        self.plan()
                    self.assertEqual(self.tree(), before)
                else:
                    plan = self.plan()
                    change = next(c for c in plan.changes if c.path == self.config_path)
                    self.assertEqual(len(change.after), tool.MAX_CONFIG + offset)
                    if offset == 0:
                        plan.apply()
                        self.assertEqual(len(self.config_path.read_bytes()), tool.MAX_CONFIG)

    def test_releases_backups_sidecars_and_device_path_reservations_refuse_early(self):
        values = ('releases/old/state.json', 'RELEASES/new/state.json', 'setup-backups/x/state.json',
                  'setup', 'setup.lock', 'mcp-client.json', 'installed-hooks.json',
                  '../outside.json', 'NUL.json', 'state.json:stream', 'trailing. ')
        for field in ('state_file', 'audit_file'):
            for value in values:
                with self.subTest(field=field, value=value):
                    config = copy.deepcopy(self.config); config[field] = value
                    self.put(self.config_path, tool._encode(config))
                    before = self.tree()
                    with self.assertRaisesRegex(agent_setup.AgentSetupError,
                            '(?i)(path|overlap|reserved|reservation|device|distinct|ambiguous)'):
                        self.plan()
                    self.assertEqual(self.tree(), before)

    def test_state_audit_and_sidecar_aliases_are_refused(self):
        for field, value in (('audit_file', self.state_path.name),
                             ('audit_file', self.state_path.name+'.lock'),
                             ('state_file', self.config_path.name)):
            with self.subTest(field=field, value=value):
                config = copy.deepcopy(self.config); config[field] = value
                self.put(self.config_path, tool._encode(config))
                with self.assertRaisesRegex(agent_setup.AgentSetupError, '(?i)(distinct|alias)'):
                    self.plan()

    def test_hardlinked_state_and_audit_are_refused_without_writing_either(self):
        audit = self.project/'.human-eye/custom-events.jsonl'
        try:
            os.link(self.state_path, audit)
        except OSError as exc:
            self.skipTest('Host cannot create a hard link: '+str(exc))
        before = self.tree()
        with self.assertRaisesRegex(agent_setup.AgentSetupError, 'alias'):
            self.plan()
        self.assertEqual(self.tree(), before)

    def test_hardlinked_state_lock_is_refused_before_locking(self):
        sidecar = self.state_path.with_name(self.state_path.name+'.lock')
        try:
            os.link(self.state_path, sidecar)
        except OSError as exc:
            self.skipTest('Host cannot create a hard link: '+str(exc))
        before = self.state_path.read_bytes()
        with self.assertRaisesRegex(agent_setup.AgentSetupError, 'alias'):
            self.plan()
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_symlinked_state_and_linked_parent_are_refused(self):
        target = self.project/'.human-eye/state-real.json'
        self.state_path.rename(target)
        try:
            os.symlink(target, self.state_path)
        except OSError as exc:
            self.skipTest('Host cannot create a symlink: '+str(exc))
        with self.assertRaisesRegex(agent_setup.AgentSetupError, '(?i)linked'):
            self.plan()
        self.state_path.unlink(); target.rename(self.state_path)
        directory = self.project/'.human-eye/actual-audit'; directory.mkdir()
        link = self.project/'.human-eye/linked-audit'
        os.symlink(directory, link, target_is_directory=True)
        config = copy.deepcopy(self.config); config['audit_file'] = 'linked-audit/events.jsonl'
        self.put(self.config_path, tool._encode(config))
        with self.assertRaisesRegex(agent_setup.AgentSetupError, '(?i)linked'):
            self.plan()
        self.assertFalse((directory/'events.jsonl').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows junction boundary')
    def test_windows_junction_parent_is_refused_without_symlink_privilege(self):
        directory = self.project/'.human-eye/actual-junction-audit'; directory.mkdir()
        link = self.project/'.human-eye/junction-audit'
        result = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(link), str(directory)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if result.returncode:
            self.skipTest('Host cannot create a directory junction')
        try:
            config = copy.deepcopy(self.config); config['audit_file'] = 'junction-audit/events.jsonl'
            self.put(self.config_path, tool._encode(config))
            with self.assertRaisesRegex(agent_setup.AgentSetupError, '(?i)linked'):
                self.plan()
            self.assertFalse((directory/'events.jsonl').exists())
        finally:
            link.rmdir()

    def test_duplicate_nonfinite_and_overflow_json_are_rejected_without_writes(self):
        original = self.state_path.read_bytes()
        variants = (original.replace(b'"inflight": null', b'"inflight":null,"inflight":null'),
                    original[:-1]+b',"extra":NaN}',
                    original[:-1]+b',"extra":1e999}')
        for raw in variants:
            with self.subTest(ending=raw[-45:]):
                self.put(self.state_path, raw); before = self.tree()
                with self.assertRaises(agent_setup.AgentSetupError): self.plan()
                self.assertEqual(self.tree(), before)

    def test_timeout_and_resource_numeric_boundaries_are_not_coerced(self):
        cases = [('quad_size', 63), ('quad_size', 513), ('quad_size', True),
                 ('max_sessions', 0), ('max_sessions', 257),
                 ('readback_atol_m', 0), ('readback_atol_m', math.nextafter(1e-5, math.inf))]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                config = copy.deepcopy(self.config); config[key] = value
                self.put(self.config_path, tool._encode(config))
                with self.assertRaisesRegex(agent_setup.AgentSetupError, '(?i)(option|tolerance)'):
                    self.plan()
        config = copy.deepcopy(self.config); config['blender']['timeout_s'] = 10**1000
        self.put(self.config_path, tool._encode(config))
        with self.assertRaisesRegex(agent_setup.AgentSetupError, 'positive connector option'):
            self.plan()

    def test_nested_same_name_fingerprint_and_unicode_key_escapes_keep_exact_spans(self):
        state = copy.deepcopy(self.state)
        state['nested'] = {'config_fingerprint': 'do-not-change'}
        old = tool._fingerprint(self.config); new = 'f' * 64
        raw = tool._encode(state).replace(b'"config_fingerprint": "'+old.encode()+b'"',
                                           b'"config_\\u0066ingerprint": "'+old.encode()+b'"', 1)
        changed = tool._state_binding_bytes(raw, old, new)
        self.assertIn(b'"config_\\u0066ingerprint": "'+new.encode()+b'"', changed)
        self.assertEqual(tool._json_object(changed,'state')['nested'], state['nested'])

    def test_noncooperating_state_edit_while_fenced_is_preserved_and_reported(self):
        plan = self.plan(); original_atomic = tool._atomic_bytes
        injected = None
        def edit(path, raw):
            nonlocal injected
            original_atomic(path, raw)
            if path == self.config_path:
                current = tool._json_object(self.state_path.read_bytes(), 'fenced state')
                current['inflight'] = {'operation_id': 'external-preserved', 'session_id': 'other', 'started': 1.0}
                injected = tool._encode(current)
                self.state_path.write_bytes(injected)
        with patch.object(tool, '_atomic_bytes', side_effect=edit):
            with self.assertRaisesRegex(agent_setup.AgentSetupError, 'rollback_incomplete'):
                plan.apply()
        self.assertEqual(self.state_path.read_bytes(), injected)
        self.assertEqual(tool._json_object(injected,'state')['inflight']['operation_id'], 'external-preserved')

    def test_operator_saved_status_is_explicitly_not_live(self):
        status = self.put(self.project/'status.json', agent_setup._encode({'content': [{'type': 'text',
            'text': json.dumps({'runtime_identity': {'build_id': 'old'}, 'quarantined': False})}]}))
        connection = self.plan(current_status=status).preview()['current_connection']
        self.assertEqual(connection['source'], 'operator_saved_file')
        self.assertFalse(connection['live_probe_performed'])
        self.assertEqual(connection['runtime_identity']['build_id'], 'old')

    def test_reviewed_plan_sha_and_target_build_are_bound(self):
        plan = self.plan()
        with self.assertRaises(agent_setup.AgentSetupError): plan.apply(plan_sha256='wrong')
        self.target['identity']['build_id'] = 'sha256:other'
        with self.assertRaises(agent_setup.AgentSetupError): plan.apply()

    def test_existing_setup_lock_and_no_config_discovery_are_not_bypassed(self):
        lock = self.put(self.project/'.human-eye/setup.lock', b'prior transaction')
        with self.assertRaises(agent_setup.AgentSetupError): self.plan().apply()
        self.assertEqual(lock.read_bytes(), b'prior transaction')
        self.server_path.unlink()
        with self.assertRaises(agent_setup.AgentSetupError): self.plan()


if __name__ == '__main__':
    unittest.main()

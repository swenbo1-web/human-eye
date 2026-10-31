"""Lightweight command boundary, authority and actual import-graph contracts."""
from __future__ import annotations
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import human_eye_hook as bootstrap
from human_eye_plugin.runtime_identity import runtime_identity

ENTRY = Path(bootstrap.__file__).resolve()
ROOT = ENTRY.parent
INSPECT = """import json,runpy,sys
scope=runpy.run_path(sys.argv[1],run_name='_tested_bootstrap')
scope['main'](sys.argv[2:])
print('IMPORT_PROOF:'+json.dumps({n:n in sys.modules for n in ('numpy','PIL','human_eye_plugin')}),file=sys.stderr)
"""


class HookBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.config_path = self.directory / 'connector.json'
        self.config = {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': True,
            'project_root': str(ROOT), 'state_file': 'state.json', 'audit_file': 'audit.jsonl',
            'blender': {'host': '127.0.0.1', 'port': 1, 'timeout_s': .01}}
        self.config_path.write_text(json.dumps(self.config), encoding='utf-8')

    def event(self, kind='UserPromptSubmit', **fields):
        return {'hook_event_name': kind, 'session_id': 'bootstrap-contract',
            'tool_name': bootstrap.SPATIAL_TRANSFORM, 'turn_id': 'host-turn', 'tool_use_id': 'host-call',
            'prompt': '继续', **fields}

    def command(self, event=None, *, raw=None, declared=None, legacy=False):
        args = ['--config', str(self.config_path), '--agent', 'codex', '--probe']
        if declared:
            args += ['--event', declared]
        prefix = ['-m', 'human_eye_plugin.live_hooks'] if legacy else ['-c', INSPECT, str(ENTRY)]
        # The installed/source process location is explicit for each mode;
        # source legacy uses -c to import the tested checkout intentionally.
        if legacy:
            prefix = ['-c', 'import sys;sys.path.insert(0,' + repr(str(ROOT)) +
                      ');from human_eye_plugin.live_hooks import main;main()', *args]
            args = []
        value = raw if raw is not None else json.dumps(event)
        completed = subprocess.run([sys.executable, '-I', '-B', *prefix, *args], input=value,
            capture_output=True, text=True, encoding='utf-8', cwd=self.directory, timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stderr[-3000:])
        result = json.loads(completed.stdout)
        proof = None
        if not legacy:
            proof = json.loads(next(line.split(':', 1)[1] for line in completed.stderr.splitlines()
                                    if line.startswith('IMPORT_PROOF:')))
        return result, proof

    def records(self):
        path = self.directory / 'audit.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_ordinary_unknown_and_2d_prompts_load_no_engine_and_write_no_state(self):
        for prompt in ('继续', '翻译这段文本。', '读取Blender截图里的文字。'):
            with self.subTest(prompt=prompt):
                output, proof = self.command(self.event(prompt=prompt), declared='UserPromptSubmit')
                self.assertEqual(output, {})
                self.assertFalse(any(proof.values()), proof)
                self.assertFalse((self.directory / 'state.json').exists())
        skips = [row for row in self.records() if row['event'] == 'host_hook_skip']
        self.assertEqual(len(skips), 3)
        self.assertTrue(all(row['scene_read'] is False for row in skips))
        self.assertTrue(all(row['invocation_source'] == 'manual_probe' for row in skips))

    def test_post_ignores_claimed_tool_success_without_reading_corrupt_state(self):
        path = self.directory / 'state.json'
        path.write_bytes(b'{corrupt pending host operation')
        for response in ({'verified': True}, {'error': 'readback failed'}, None):
            with self.subTest(response=response):
                output, proof = self.command(self.event('PostToolUse', tool_response=response), declared='PostToolUse')
                self.assertEqual(output, {})
                self.assertFalse(any(proof.values()), proof)
                self.assertEqual(path.read_bytes(), b'{corrupt pending host operation')
        self.assertFalse(path.with_name('state.json.lock').exists())
        self.assertTrue(all(r['status'] == 'tool_result_delivery_retained'
                            for r in self.records() if r['event'] == 'host_hook_skip'))

    def test_mismatched_pin_is_audited_truthfully_and_never_certifies_geometry(self):
        self.config['expected_identity'] = {'build_id': 'sha256:wrong'}
        self.config_path.write_text(json.dumps(self.config), encoding='utf-8')
        output, proof = self.command(self.event('PostToolUse'))
        self.assertEqual(output, {})
        self.assertFalse(any(proof.values()))
        for row in self.records():
            self.assertFalse(row['identity_check']['compatible'])
            self.assertNotEqual(row['runtime_identity']['build_id'], 'sha256:wrong')
            self.assertNotIn('execution_verified', row)

    def test_event_and_config_cannot_select_leaf_source_root(self):
        evil = self.directory / 'evil'
        (evil / 'human_eye_plugin').mkdir(parents=True)
        marker = self.directory / 'executed.txt'
        (evil / 'human_eye_plugin/task_intent.py').write_text(
            'from pathlib import Path;Path(' + repr(str(marker)) + ').write_text("ran")')
        self.config['project_root'] = str(evil)
        self.config_path.write_text(json.dumps(self.config), encoding='utf-8')
        output, proof = self.command(self.event(project_root=str(evil)))
        self.assertEqual(output, {})
        self.assertFalse(any(proof.values()))
        self.assertFalse(marker.exists())
        self.assertEqual(self.records()[0]['runtime_identity']['build_id'], runtime_identity()['build_id'])

    def test_trusted_pre_registration_denies_all_unparseable_or_mismatched_input(self):
        for raw in ('{', '[]', '{"value":NaN}', 'x'*(1024*1024+1),
                    json.dumps(self.event('UserPromptSubmit')),
                    json.dumps(self.event('PreToolUse', tool_name='unregistered'))):
            with self.subTest(raw=raw[:50]):
                result, proof = self.command(raw=raw, declared='PreToolUse')
                self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')
                self.assertFalse(any(proof.values()))

    def test_legacy_and_bootstrap_trusted_invalid_pre_have_identical_denial(self):
        first, _ = self.command(raw='{', declared='PreToolUse')
        legacy, _ = self.command(raw='{', declared='PreToolUse', legacy=True)
        self.assertEqual(first, legacy)

    def test_failure_output_survives_missing_support_module(self):
        with patch.object(bootstrap, '_leaf', side_effect=FileNotFoundError('missing leaf')):
            self.assertEqual(bootstrap._failure_output({}, 'PreToolUse')['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_aliasing_audit_to_state_lock_is_rejected_without_writes(self):
        self.config['audit_file'] = 'state.json.lock'
        self.config_path.write_text(json.dumps(self.config), encoding='utf-8')
        result, proof = self.command(self.event('PostToolUse'))
        self.assertEqual(result, {})
        self.assertFalse(any(proof.values()))
        self.assertFalse((self.directory / 'state.json.lock').exists())

    def test_spatial_prompt_and_pre_use_ordinary_production_path(self):
        for event, declared in ((self.event(prompt='Measure the part clearance in Blender.'), 'UserPromptSubmit'),
                               (self.event('PreToolUse', tool_input={'action': {}}), 'PreToolUse')):
            with self.subTest(declared=declared):
                result, proof = self.command(event, declared=declared)
                self.assertTrue(proof['human_eye_plugin'])
                self.assertTrue(proof['numpy'])
                if declared == 'PreToolUse':
                    self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_bootstrap_and_normal_skip_policy_keep_same_audit_meaning(self):
        for event in (self.event(), self.event('PostToolUse', tool_response={'verified': True})):
            with self.subTest(kind=event['hook_event_name']):
                self.assertEqual(self.command(event)[0], self.command(event, legacy=True)[0])
        statuses = [r['status'] for r in self.records() if r['event'] == 'host_hook_skip']
        self.assertEqual(statuses, ['intent_unknown', 'intent_unknown',
                                   'tool_result_delivery_retained', 'tool_result_delivery_retained'])


if __name__ == '__main__':
    unittest.main()

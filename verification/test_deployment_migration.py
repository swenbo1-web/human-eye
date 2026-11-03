"""Public counterexamples for explicit prior-launcher trust and stale plans.

Actual 78/124 source binding and migration are separately exercised by the
offline qualification runner. These tiny bootstraps are declared test doubles.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from verification import test_installed_release_integration as existing

tool = existing.tool
OLD_BUILD = 'sha256:' + 'a' * 64


class DeploymentMigrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = existing.InstalledIntegrationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.project = self.fixture.project
        self.entry = self.project/'.human-eye/releases/trusted-prior/admin/target_runtime_entry.py'
        proof = {'entry': str(self.entry), 'dependency_python': self.fixture.target['python'],
                 'identity': {'build_id': OLD_BUILD}, 'roles': {'mcp': 'serve', 'hook': 'hook'},
                 'binding': 'test-double', 'source_file_count': 0}
        self.fixture.put(self.entry, ('def validate_binding(*, expected_python=None):\n    return ' + repr(proof) + '\n').encode())
        self.digest = hashlib.sha256(self.entry.read_bytes()).hexdigest()
        old_config = copy.deepcopy(self.fixture.config)
        self.fixture.config['expected_identity']['build_id'] = OLD_BUILD
        self.fixture.config_path.write_bytes(tool._encode(self.fixture.config))
        state = tool._state_binding_bytes(self.fixture.state_path.read_bytes(), tool._fingerprint(old_config),
                                         tool._fingerprint(self.fixture.config))
        self.fixture.state_path.write_bytes(state)
        raw = self.fixture.server_path.read_bytes()
        _, server = tool._load_server(raw, 'codex')
        updated = copy.deepcopy(server)
        updated['args'] = ['-I', '-B', str(self.entry), 'serve', '--config', str(self.fixture.config_path)]
        self.fixture.server_path.write_bytes(tool._replace_toml_server(raw, server, updated))
        self.pin = (str(self.entry), self.digest, OLD_BUILD)

    def plan(self, pins=None):
        return self.fixture.plan(prior_launcher_pins=[self.pin] if pins is None else pins)

    def unchanged_refusal(self, pins, reason):
        paths = [self.fixture.server_path, self.fixture.hook_path, self.fixture.config_path, self.fixture.state_path]
        before = {path: path.read_bytes() for path in paths}
        with self.assertRaisesRegex(tool.AgentSetupError, reason):
            self.plan(pins)
        self.assertEqual(before, {path: path.read_bytes() for path in paths})
        self.assertFalse((self.project/'.human-eye/setup.lock').exists())

    def test_registered_different_bootstrap_without_pin_refuses(self):
        self.unchanged_refusal([], 'Unknown or modified fixed target bootstrap')

    def test_explicit_sha_build_pin_is_in_reviewed_plan_and_preserves_state_bytes(self):
        before = self.fixture.state_path.read_bytes()
        plan = self.plan()
        preview = plan.preview()
        self.assertEqual(preview['prior_launcher_pins'][str(self.entry)]['entry_sha256'], self.digest)
        plan.apply(plan_sha256=preview['plan_sha256'])
        after = self.fixture.state_path.read_bytes()
        migrated = tool._state_binding_bytes(after, preview['state_migration']['new_config_fingerprint'],
                                            preview['state_migration']['old_config_fingerprint'])
        self.assertEqual(migrated, before)

    def test_wrong_sha_refuses_without_writes(self):
        self.unchanged_refusal([(str(self.entry), 'f'*64, OLD_BUILD)], 'Unknown or modified')

    def test_explicit_build_mismatch_refuses(self):
        self.unchanged_refusal([(str(self.entry), self.digest, 'sha256:'+'b'*64)], 'explicit expected build')

    def test_registered_connector_build_is_independent_anchor(self):
        config = copy.deepcopy(self.fixture.config)
        config['expected_identity']['build_id'] = 'sha256:'+'c'*64
        self.fixture.state_path.write_bytes(tool._state_binding_bytes(self.fixture.state_path.read_bytes(),
            tool._fingerprint(self.fixture.config), tool._fingerprint(config)))
        self.fixture.config_path.write_bytes(tool._encode(config))
        self.unchanged_refusal([self.pin], 'registered connector identity')

    def test_unused_trust_pin_is_not_silently_accepted(self):
        extra = self.project/'.human-eye/releases/unregistered/admin/target_runtime_entry.py'
        self.unchanged_refusal([self.pin, (str(extra), self.digest, OLD_BUILD)], 'Unused prior launcher pin')

    def test_duplicate_and_malformed_pins_refuse(self):
        for pins in ([self.pin, self.pin], [self.pin]*17, [('relative/target_runtime_entry.py', self.digest, OLD_BUILD)],
                     [(str(self.entry), self.digest.upper(), OLD_BUILD)], [(str(self.entry), self.digest, 'old')],
                     [(str(self.project/'target_runtime_entry.py'), self.digest, OLD_BUILD)]):
            with self.subTest(pins=str(pins)[:160]), self.assertRaises(tool.AgentSetupError):
                self.plan(pins)

    def test_entry_changed_after_plan_refuses_before_state_mutation(self):
        plan = self.plan()
        before = self.fixture.state_path.read_bytes()
        self.entry.write_bytes(self.entry.read_bytes() + b'# external edit\n')
        with self.assertRaisesRegex(tool.AgentSetupError, 'Unknown or modified'):
            plan.apply()
        self.assertEqual(before, self.fixture.state_path.read_bytes())
        self.assertFalse((self.project/'.human-eye/setup.lock').exists())

    def test_bootstrap_read_race_never_executes_unpinned_second_bytes(self):
        first = self.entry.read_bytes()
        with patch.object(tool, '_read', side_effect=[first, first+b'raise RuntimeError("untrusted")\n']):
            with self.assertRaisesRegex(tool.AgentSetupError, 'Modified fixed target bootstrap'):
                tool._target_entry_proof(self.entry, Path(self.fixture.target['python']), expected_sha256=self.digest)

    def test_plan_hash_binds_prior_trust_anchor(self):
        plan = self.plan()
        preview = plan.preview()
        altered = copy.deepcopy(preview)
        altered['prior_launcher_pins'][str(self.entry)]['entry_sha256'] = 'f'*64
        altered.pop('plan_sha256')
        with self.assertRaisesRegex(tool.AgentSetupError, 'Plan SHA differs'):
            plan.apply(plan_sha256=tool._fingerprint(altered))


if __name__ == '__main__':
    unittest.main()

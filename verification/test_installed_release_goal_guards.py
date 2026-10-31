"""Candidate administration rejects unresolved whole-goal journals.

Only new temporary projects and already sealed test packets are used. These
tests exercise the source candidate helper; they do not alter installed admin.
"""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from verification import test_installed_release_integration as existing

ROOT = Path(__file__).resolve().parents[1]
PACKETS = ROOT/'verification/fixes/20261030_v21_supervisor_ledger/owned_work/run_002'


class InstalledGoalGuardTests(unittest.TestCase):
    def setUp(self):
        self.fixture = existing.InstalledIntegrationTests(
            'test_declared_goal_capability_adds_exact_pre_and_post_scopes')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.tool = existing.tool

    def state(self, packet=None):
        state = copy.deepcopy(self.fixture.state)
        if packet is not None:
            captured = json.loads((PACKETS/packet).read_text(encoding='utf-8'))
            for key in ('goal_segments', 'goal_supervision'):
                if key in captured:
                    state[key] = copy.deepcopy(captured[key])
        return state

    def put(self, state):
        raw = self.tool._encode(state)
        self.fixture.put(self.fixture.state_path, raw)
        return raw

    def refuses_without_writes(self, state):
        self.put(state)
        before = self.fixture.tree()
        with self.assertRaises(existing.agent_setup.AgentSetupError):self.fixture.plan()
        self.assertEqual(self.fixture.tree(), before)

    def test_legacy_state_without_goal_ledgers_is_unchanged(self):
        raw = self.fixture.state_path.read_bytes()
        loaded = self.tool._check_state(raw, self.fixture.config)
        self.assertEqual(loaded, self.fixture.state)
        self.assertEqual(self.fixture.state_path.read_bytes(), raw)

    def test_empty_child_ledger_remains_compatible(self):
        state = self.state()
        state['goal_segments'] = {'schema_version':'1.0', 'records':{}}
        self.put(state)
        plan = self.fixture.plan()
        self.assertTrue(plan.apply()['applied'])
        migrated = json.loads(self.fixture.state_path.read_text(encoding='utf-8-sig'))
        self.assertEqual(migrated['goal_segments'], state['goal_segments'])

    def test_running_child_blocks_even_when_inflight_is_clear(self):
        state = self.state('STATE_AFTER_CRASH.json')
        state.pop('goal_supervision')
        entry = state['goal_segments']['records']['owned-child-1']
        entry.pop('parent_goal_id')
        entry.update(status='running', result=None)
        entry['steps'][0].pop('actual_translation_m')
        entry['end_revision'] = entry['base_revision']
        self.assertIsNone(state['inflight'])
        self.refuses_without_writes(state)

    def test_committed_child_with_parent_ack_missing_blocks(self):
        self.refuses_without_writes(self.state('STATE_AFTER_CRASH.json'))

    def test_confirmed_child_but_still_active_parent_blocks(self):
        self.refuses_without_writes(self.state('STATE_AFTER_RECONCILE_1.json'))

    def test_frozen_parent_blocks_without_silently_recovering(self):
        state = self.state('STATE_AFTER_CRASH.json')
        record = state['goal_supervision']['records']['owned-goal']
        record.update(status='frozen', reason='owned_failure_requires_review')
        self.refuses_without_writes(state)

    def test_malformed_child_ledger_blocks(self):
        for ledger in (None, {}, {'schema_version':'future','records':{}},
                       {'schema_version':'1.0','records':{'bad':{}}}):
            with self.subTest(ledger=ledger):
                state = self.state();state['goal_segments'] = ledger
                self.refuses_without_writes(state)

    def test_unknown_parent_schema_blocks(self):
        state = self.state('FINAL_STATE.json')
        state['goal_supervision']['schema_version'] = 'future'
        self.refuses_without_writes(state)

    def test_terminal_unknown_or_interrupted_child_still_blocks(self):
        for status in ('execution_uncertain', 'segment_interrupted'):
            with self.subTest(status=status):
                state = self.state('STATE_AFTER_CRASH.json')
                state.pop('goal_supervision')
                entry = state['goal_segments']['records']['owned-child-1']
                entry.pop('parent_goal_id')
                entry['status'] = status
                entry['result']['status'] = status
                self.refuses_without_writes(state)

    def test_entire_parent_journal_missing_blocks_orphan_child(self):
        state = self.state('FINAL_STATE.json')
        state.pop('goal_supervision')
        self.refuses_without_writes(state)

    def test_target_missing_parent_validator_fails_closed(self):
        state = self.state('FINAL_STATE.json')
        self.put(state)
        before = self.fixture.tree()
        with patch.dict(sys.modules, {'human_eye_plugin.goal_journal':None}):
            with self.assertRaises(existing.agent_setup.AgentSetupError):self.fixture.plan()
        self.assertEqual(self.fixture.tree(), before)

    def test_confirmed_child_request_corruption_blocks(self):
        state = self.state('FINAL_STATE.json')
        state['goal_segments']['records']['owned-child-1']['request']['target_clearance_m'] = .0005
        self.refuses_without_writes(state)

    def test_completed_parent_migration_preserves_all_journal_bytes(self):
        state = self.state('FINAL_STATE.json')
        raw = self.put(state)
        plan = self.fixture.plan()
        expected = self.tool._state_binding_bytes(raw, self.tool._fingerprint(self.fixture.config),
            plan.preview()['state_migration']['new_config_fingerprint'])
        self.assertTrue(plan.apply()['applied'])
        self.assertEqual(self.fixture.state_path.read_bytes(), expected)

    def test_new_unknown_parent_cannot_be_treated_as_legacy_payload(self):
        state = self.state()
        state['goal_supervision'] = {'records':{}, 'schema_version':'malformed'}
        self.refuses_without_writes(state)


if __name__ == '__main__':unittest.main()

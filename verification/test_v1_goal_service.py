"""Goals use the current host readback and remain separate from execution."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin.live_service import LiveSpatialService
from verification.test_live_service import SelfLockingHost


class V1GoalServiceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.config = self.folder / 'live.json'
        self.config.write_text(json.dumps({'schema_version': '1.0',
            'project_root': str(Path(__file__).resolve().parents[1]), 'state_file': 'state.json',
            'audit_file': 'events.jsonl', 'quad_size': 64}), encoding='utf-8')
        self.host = SelfLockingHost()
        self.service = LiveSpatialService(self.config, host=self.host)
        self.action = {'focal_id': 'part', 'reference_id': 'base', 'translation': [0, 0, .05]}

    def goal(self, clearance=.15):
        return {'target_clearance_m': clearance, 'clearance_tolerance_m': 1e-8}

    def test_success_is_evaluated_on_actual_readback(self):
        target = self.goal()
        original = copy.deepcopy(target)
        result = self.service.transform('s', self.action, goal=target)
        self.assertTrue(result['execution_verified'])
        self.assertTrue(result['task_succeeded'])
        self.assertEqual(result['goal_evaluation'], 'goal_satisfied')
        self.assertEqual(result['goal_verification']['scene_revision'], self.host.scene['revision'])
        self.assertEqual(result['goal_verification']['goal_source'], 'caller_supplied_not_verified_user_intent')
        self.assertEqual(target, original)

    def test_execution_can_succeed_without_satisfying_target(self):
        result = self.service.transform('s', self.action, goal=self.goal(.002))
        self.assertTrue(result['execution_verified'])
        self.assertFalse(result['task_succeeded'])
        self.assertEqual(result['goal_evaluation'], 'goal_not_satisfied')
        self.assertFalse(self.service.status()['quarantined'])
        self.assertFalse(self.service.status()['inflight_operation'])

    def test_invalid_goal_never_journals_or_calls_host(self):
        for target in ({}, {'target_clearance_m': .1}, {'target_clearance_m': -1, 'clearance_tolerance_m': .1},
                       {**self.goal(), 'focal_id': 'base'}, {**self.goal(), 'scale': 2}):
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.service.transform('s', self.action, goal=target)
        self.assertEqual(self.host.calls, 0)
        self.assertEqual(self.host.captures, 0)
        self.assertFalse((self.folder / 'state.json').exists())

    def test_observation_goal_uses_the_single_host_capture(self):
        result = self.service.observe('s', focal_id='part', reference_id='base',
                                      include_image=False, goal=self.goal(.1))
        self.assertTrue(result['task_succeeded'])
        self.assertEqual(self.host.captures, 1)
        self.assertEqual(self.host.calls, 0)

    def test_no_op_can_report_an_already_satisfied_goal(self):
        result = self.service.transform('s', {**self.action, 'translation': [0, 0, 0]}, goal=self.goal(.1))
        self.assertEqual(result['status'], 'no_op')
        self.assertFalse(result['execution_verified'])
        self.assertTrue(result['task_succeeded'])
        self.assertEqual(self.host.calls, 0)

    def test_optional_evaluator_failure_does_not_authorize_a_duplicate_write(self):
        with patch('human_eye_plugin.host_runtime.evaluate_spatial_goal', side_effect=RuntimeError('evaluator unavailable')):
            result = self.service.transform('s', self.action, goal=self.goal())
        self.assertTrue(result['execution_verified'])
        self.assertFalse(result['task_succeeded'])
        self.assertEqual(result['goal_evaluation'], 'evaluation_failed')
        self.assertEqual(self.host.calls, 1)
        self.assertFalse(self.service.status()['inflight_operation'])

    def test_omitted_goal_does_not_claim_task_completion(self):
        result = self.service.transform('s', self.action)
        self.assertEqual(result['goal_evaluation'], 'not_requested')
        self.assertIsNone(result['task_succeeded'])


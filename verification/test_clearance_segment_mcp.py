"""Actual goal-service delivery through MCP envelopes, without a live host."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
from verification.test_clearance_segment_service import SegmentHost


class ClearanceSegmentMCPTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        path = self.folder/'config.json'
        path.write_text(json.dumps({'schema_version': '1.0',
            'project_root': str(Path(__file__).resolve().parents[1]),
            'state_file': 'state.json', 'audit_file': 'audit.jsonl', 'quad_size': 64}), encoding='utf-8')
        self.host = SegmentHost()
        self.service = LiveSpatialService(path, host=self.host)
        self.server = LiveSpatialMCPServer(self.service, default_session_id='actual-agent-session')
        self.goal = {'focal_id': 'part', 'reference_id': 'base', 'axis': '+z',
                     'target_clearance_m': .001, 'clearance_tolerance_m': 1e-6}

    def call(self, arguments):
        response = self.server.handle_jsonrpc_message({'jsonrpc': '2.0', 'id': 42,
            'method': 'tools/call', 'params': {'name': 'human_eye_clearance_segment', 'arguments': arguments}})
        result = response['result']
        return result, json.loads(result['content'][0]['text'])

    def test_default_is_read_only_and_does_not_reserve_request(self):
        wire, result = self.call({'request_id': 'goal-1', 'request': self.goal})
        self.assertFalse(wire['isError'], result)
        self.assertEqual(result['status'], 'preview')
        self.assertEqual(self.host.calls, 0)
        self.assertFalse((self.folder/'state.json').exists())

    def test_goal_runs_and_replays_without_duplicate_motion_or_capture(self):
        arguments = {'request_id': 'goal-1', 'request': self.goal, 'execute': True}
        original = copy.deepcopy(arguments)
        wire, result = self.call(arguments)
        self.assertFalse(wire['isError'], result)
        self.assertEqual(result['status'], 'satisfied')
        self.assertTrue(result['task_succeeded'])
        self.assertEqual(result['execution_scope'], 'terminal_geometry_only')
        self.assertLessEqual(abs(self.host.actual_gap()-.001), 1e-6)
        self.assertEqual(arguments, original)
        count = self.host.captures
        _, replay = self.call(arguments)
        self.assertTrue(replay['historical_receipt'])
        self.assertFalse(replay['current_scene_revalidated'])
        self.assertEqual(self.host.calls, 1)
        self.assertEqual(self.host.captures, count)

    def test_native_final_image_not_in_persisted_receipt(self):
        wire, result = self.call({'request_id': 'image-goal', 'request': self.goal,
                                  'execute': True, 'include_image': True})
        self.assertFalse(wire['isError'], result)
        pictures = [item for item in wire['content'] if item['type'] == 'image']
        self.assertEqual(len(pictures), 1, result)
        self.assertNotIn(pictures[0]['data'], (self.folder/'state.json').read_text(encoding='utf-8'))

    def test_malformed_goal_never_captures_or_moves(self):
        for changes in ({'execute': 1}, {'include_image': 'yes'}, {'request': dict(self.goal, axis='guess')},
                        {'request': dict(self.goal, target_clearance_m=True)}, {'unknown': 1}):
            args = {'request_id': 'bad', 'request': self.goal, **changes}
            with self.subTest(changes=changes):
                wire, _ = self.call(args)
                self.assertTrue(wire['isError'])
        self.assertEqual(self.host.captures, 0)
        self.assertEqual(self.host.calls, 0)

    def test_notification_does_not_execute_goal(self):
        self.assertIsNone(self.server.handle_jsonrpc_message({'jsonrpc': '2.0', 'method': 'tools/call',
            'params': {'name': 'human_eye_clearance_segment', 'arguments': {
                'request_id': 'silent', 'request': self.goal, 'execute': True}}}))
        self.assertEqual(self.host.calls, 0)
        self.assertEqual(self.host.captures, 0)

    def test_scene_identity_change_during_commit_is_uncertain(self):
        self.host.after_mutation = lambda host: host.scene['host_identity'].update(document_epoch='other-doc')
        wire, result = self.call({'request_id': 'identity-switch', 'request': self.goal, 'execute': True})
        self.assertTrue(wire['isError'], result)
        self.assertEqual(result['status'], 'execution_uncertain')
        self.assertIsNone(result['executed'])
        self.assertEqual(self.host.calls, 1)
        self.assertTrue(self.service.status()['inflight_operation'])


if __name__ == '__main__':
    unittest.main()

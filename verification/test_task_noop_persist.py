"""Task queries capture current geometry independently of the durable action journal."""
import copy
import json
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin import live_service as ls
from verification import test_observation_noop_independent as fixture


class TaskReadPersistenceTests(unittest.TestCase):
    setUp = fixture.IndependentObservationPersistenceTests.setUp

    def task(self, *, query=None):
        return self.service.observe('current', include_image=False, query=query or {
            'mode': 'task', 'objects': [{'id': 'part'}], 'requested_facts': ['aabb']})

    def test_task_checks_current_capture_on_each_read_without_creating_action_state(self):
        with patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            first = self.task()
            second = self.task()
        writes.assert_not_called()
        self.assertFalse(self.state_path.exists())
        self.assertEqual((self.host.captures, self.host.calls), (2, 0))
        self.assertEqual(first['facts'], second['facts'])
        self.assertEqual(first['binding'], second['binding'])
        events = [json.loads(line) for line in self.service.audit_path.read_text(encoding='utf8').splitlines()]
        observations = [event for event in events if event['event'] == 'observe']
        self.assertEqual(len(observations), 2)
        self.assertEqual(observations[-1]['trace_id'], second['trace_id'])

    def test_read_leaves_established_action_session_untouched(self):
        self.service.observe('current', focal_id='part', reference_id='base', include_image=False)
        state = self.state_path.read_bytes()
        self.assertTrue(json.loads(state)['runtime']['sessions'])
        with patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            result = self.task()
        self.assertEqual(result['status'], 'observed')
        writes.assert_not_called()
        self.assertEqual(self.state_path.read_bytes(), state)
        self.assertEqual(self.host.calls, 0)

    def test_changed_scene_same_name_replacement_and_mixed_unknown_remain_fresh(self):
        first = self.task()
        self.assertFalse(self.state_path.exists())
        item = self.host.scene['meshes'][1]
        item['object_id'] = 'replacement'
        item['vertices'] = (np.asarray(item['vertices']) + [.125, 0, .025]).tolist()
        self.host.scene['revision'] = 'replacement-r2'
        query = {'mode': 'task', 'objects': [{'name': 'part'}], 'requested_facts': ['aabb']}
        with patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            result = self.task(query=query)
        self.assertEqual(writes.call_count, 0)
        self.assertEqual(result['binding']['objects'][0]['object_id'], 'replacement')
        self.assertEqual(result['binding']['scene_revision'], 'replacement-r2')
        self.assertNotEqual(result['binding']['scene_fingerprint'], first['binding']['scene_fingerprint'])
        self.assertEqual(result['facts']['aabb'][0]['value']['min'], np.asarray(item['vertices']).min(axis=0).tolist())
        item['faces'] = [[0, 2, 1]]
        item['edges'] = [[0, 2], [2, 1], [1, 0]]
        pair = {'mode': 'task', 'objects': [{'name': 'part'}, {'name': 'base'}],
                'requested_facts': ['aabb', 'center_delta', 'axis_gap', 'surface_clearance', 'solid_relation', 'nearest_witness']}
        with patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            partial = self.task(query=pair)
        self.assertEqual(writes.call_count, 0)
        self.assertEqual(partial['status'], 'partial')
        self.assertEqual(partial['facts']['aabb'][0]['status'], 'measured')
        self.assertEqual(partial['facts']['axis_gap']['status'], 'measured')
        for name in ('surface_clearance', 'solid_relation', 'nearest_witness'):
            self.assertEqual(partial['facts'][name]['status'], 'unknown')
            self.assertTrue(partial['facts'][name]['reason'])
        self.assertFalse(self.state_path.exists())
        self.assertEqual((self.host.captures, self.host.calls), (3, 0))

    def test_action_journal_writes_remain_after_a_stable_task_skip(self):
        self.task()
        with patch.object(ls, '_atomic_write', wraps=ls._atomic_write) as writes:
            self.task()
        self.assertEqual(writes.call_count, 0)
        states = []
        writer = ls._atomic_write
        def record(path, value, **kwargs):
            states.append(copy.deepcopy(value))
            return writer(path, value, **kwargs)
        action = {'focal_id': 'part', 'reference_id': 'base', 'translation': [0, 0, .05]}
        with patch.object(ls, '_atomic_write', side_effect=record):
            result = self.service.transform('current', action)
        self.assertTrue(result['verified'])
        self.assertEqual(len(states), 2)
        self.assertIsNotNone(states[0]['inflight'])
        self.assertIsNone(states[1]['inflight'])
        self.assertEqual(self.host.calls, 1)


if __name__ == '__main__':
    unittest.main()

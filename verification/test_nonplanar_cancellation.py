"""Exercise cancellation inside independent proof work and public retry quotas."""
import copy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from human_eye_plugin import nonplanar_replay as consumer
from human_eye_plugin.nonplanar_exact import ExactLocalIndex
from verification.test_nonplanar_protocol import example
from verification.nonplanar_dense_fixtures import dense_case, local_limit_source
from human_eye_plugin import nonplanar_focus as producer
import time
from verification import test_structure_task as task_tests


class NonplanarCancellationTests(unittest.TestCase):
    def test_local_limit_complete_no_image_and_over_limit_refusal(self):
        native, edges = local_limit_source(61)
        deadline = time.perf_counter_ns()+30_000_000_000
        plan = producer.choose(native, 'target', edges, deadline, locality_policy='visual_nearplanar', acceleration='auto')
        self.assertTrue(plan['search_complete'])
        self.assertIsNone(plan['selected'])
        self.assertEqual(max(p['visited_face_count'] for r in plan['candidates'] for p in r['local_surfaces']), 128)
        _, _, detail = consumer.decision(plan, native, 'target', edges, 'nonplanar_dense_v1', deadline)
        self.assertIsNone(detail)
        native, edges = local_limit_source(62)
        with self.assertRaisesRegex(ValueError, 'face_visit_budget'):
            producer.choose(native, 'target', edges, deadline, locality_policy='visual_nearplanar', acceleration='auto')

    def test_expiry_inside_each_stage_stops_before_continuing_proof(self):
        plan, native, edges, _ = example(dense_case(12))
        frozen = copy.deepcopy(plan)
        for owner, name in ((consumer, 'replay'), (consumer, 'Fraction'),
                            (ExactLocalIndex, 'reconstruct'), (consumer, 'ray')):
            with self.subTest(stage=name):
                armed = False
                calls = 0
                original = getattr(owner, name)
                def clock():
                    return 100 if armed else 99
                def expire(*args, **kwargs):
                    nonlocal armed, calls
                    armed = True
                    calls += 1
                    return original(*args, **kwargs)
                with patch.object(consumer, 'time', SimpleNamespace(perf_counter_ns=clock)), \
                     patch.object(owner, name, expire):
                    with self.assertRaisesRegex(ValueError, 'deadline_expired'):
                        consumer.decision(plan, native, 'target', edges, 'nonplanar_dense_v1', 100)
                self.assertTrue(armed)
                # At most one 3-coordinate dot may have started before expiry.
                self.assertLessEqual(calls, 7)
                self.assertEqual(plan, frozen)

    def test_local_work_is_not_reset_when_checkpoint_stops(self):
        target = {'world_vertices': [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]],
                  'faces': [[0, 1, 2]]}
        local = ExactLocalIndex(target, 100)
        used = local.work
        def stop():
            raise ValueError('deadline_expired')
        local.checkpoint = stop
        with self.assertRaisesRegex(ValueError, 'deadline'):
            local.reserve(5)
        self.assertEqual(local.work, used+5)

    def test_attempted_image_timeout_preserves_quota_and_duplicate_receipt(self):
        # This tests public MCP/ledger failure semantics with an injected typed
        # host timeout. It does not claim a real installed host fault trial.
        case = task_tests.StructureTaskTests('test_four_tools_no_registration_no_host')
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.service.config['structure_patch_mode'] = 'nonplanar_dense_v1'
        case.host.nonplanar_observation_capabilities = lambda: {}
        attempts = []
        def timed_out(*args):
            attempts.append(args)
            raise ValueError('nonplanar_deadline_expired')
        case.host.observe_nonplanar_patch = timed_out
        case.register()
        first, _ = case.call('diagnose')
        original_deadline = case.state()['deadline_ns']
        reference = first['patch_refs'][0]['patch_ref']
        with patch('human_eye_plugin.nonplanar_observation.validate_capabilities', return_value={}):
            result, response = case.call('timeout', operation='patch', ref=reference, images=True)
        self.assertEqual(result['image_status'], 'unavailable')
        self.assertIn('deadline', result['image_reason'])
        self.assertEqual([b['type'] for b in response['content']], ['text'])
        state = case.state()
        self.assertEqual(state['spent']['images'], 2)
        self.assertEqual(state['spent']['png_bytes'], 16*1024*1024)
        self.assertEqual(state['spent']['queries'], 2)
        receipt, response = case.call('timeout', operation='patch', ref=reference, images=True)
        self.assertEqual(receipt['status'], 'receipt')
        self.assertEqual(case.state()['spent'], state['spent'])
        self.assertEqual(case.state()['deadline_ns'], original_deadline)
        self.assertEqual(len(attempts), 1)
        self.assertFalse(receipt['current_evidence'])
        self.assertEqual([b['type'] for b in response['content']], ['text'])


if __name__ == '__main__':
    unittest.main()

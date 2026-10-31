"""Business routing and conservative obstacle coverage through the real router."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin.auto_router import HumanEyeAutoRouter
from human_eye_plugin.geometry_safety import measure_pair_geometry
from human_eye_plugin.host_runtime import GuardedHostRuntime
from verification.agent_acceptance import route_corpus
from verification.test_auto_router import observation, scene, box, action
from verification.test_host_runtime import MutableHost


def sparse_scene(count=100):
    result = scene()
    for index in range(count - 2):
        result['meshes'].append(box('far' + str(index), [10 + 2 * index, 0, .35], [.2, .3, .1]))
    return result


class RoutingSpatialIntegrationTests(unittest.TestCase):
    def test_original_preregistered_corpus_now_meets_all_business_expectations(self):
        result = route_corpus(Path(__file__).parent / 'fixtures/agent_routes_v1.json')
        self.assertEqual(result['total'], 100)
        self.assertEqual(result['matched'], 100, [r for r in result['rows'] if not r['business_expectation_met']])

    def test_natural_spatial_request_requires_a_real_scene(self):
        result = HumanEyeAutoRouter(quad_size=64).handle_event({'event': 'before_model',
            'session_id': 'new', 'task_instruction': 'Rotate the peg 45 degrees about world Z.'})
        self.assertEqual(result['route'], 'blocked')
        self.assertEqual(result['reason_codes'], ['scene_required'])

    def test_native_background_scene_does_not_enter_geometry_or_keep_old_authority(self):
        router = HumanEyeAutoRouter(quad_size=64)
        old = router.handle_event(observation(include_image=False))
        event = observation(task_kind=None, task_instruction='请总结开发会议纪要。')
        event['scene']['meshes'][0]['vertices'] = ['invalid background scene']
        with patch('human_eye_plugin.auto_router._validated_scene') as validate:
            native = router.handle_event(event)
        validate.assert_not_called()
        self.assertEqual(native['route'], 'native')
        self.assertFalse(router.handle_event(action(old))['allow_action'])

    def test_bad_metadata_is_unknown_and_does_not_crash_or_capture(self):
        for value in ([], {}, 4, 'unrecognized'):
            event = observation(task_kind=value)
            with patch('human_eye_plugin.auto_router._validated_scene') as validate:
                result = HumanEyeAutoRouter(quad_size=64).handle_event(event)
            validate.assert_not_called()
            self.assertEqual(result['task_intent']['kind'], 'unknown')
            self.assertEqual(result['route'], 'native')

    def test_action_cannot_bypass_safety_with_a_native_task_label(self):
        router = HumanEyeAutoRouter(quad_size=64)
        observed = router.handle_event(observation(include_image=False))
        result = router.handle_event(action(observed, task_kind='general',
            task_instruction='Tell a joke.', action={'translation': [0, 0, -.15]}))
        self.assertFalse(result['allow_action'])
        self.assertEqual(result['reason_codes'], ['candidate_collision'])

    def test_python_host_auto_intent_classifies_before_capture(self):
        host = MutableHost()
        host.mode = 'capture_failure'
        runtime = GuardedHostRuntime(host, quad_size=64)
        for instruction in ('请总结开发会议纪要。', 'Describe this Blender screenshot.', 'move it'):
            prepared = runtime.before_model(session_id='s', task_instruction=instruction,
                focal_id='part', reference_id='base', messages=[], task_kind=None)
            self.assertEqual(prepared['routing']['route'], 'native')
        self.assertEqual(host.captures, 0)
        self.assertFalse(runtime.status['quarantined'])
        self.assertEqual(runtime.execute_action(session_id='s', action={'translation': [0, 0, .1]})['status'],
                         'observation_required')

    def test_python_host_auto_spatial_intent_captures_and_uses_native_image_adapter(self):
        host = MutableHost()
        runtime = GuardedHostRuntime(host, quad_size=64)
        prepared = runtime.before_model(session_id='s', task_instruction='Measure part clearance.',
            focal_id='part', reference_id='base', messages=[], task_kind=None)
        self.assertEqual(host.captures, 1)
        self.assertEqual(prepared['routing']['route'], 'engine')
        self.assertTrue(prepared['delivery']['image_delivered'])

    def test_closed_host_does_not_block_a_native_message_or_enter_transaction(self):
        class ClosedHost(MutableHost):
            def transaction(self):
                raise ConnectionError('closed host must not be consulted for ordinary text')
        host = ClosedHost()
        prepared = GuardedHostRuntime(host, quad_size=64).before_model(session_id='s',
            task_instruction='Translate this paragraph.', focal_id='part', reference_id='base',
            messages=[], task_kind=None)
        self.assertEqual(prepared['routing']['route'], 'native')
        self.assertEqual(host.captures, 0)

    def test_hundred_object_observation_measures_reference_and_accounts_for_all_others(self):
        router = HumanEyeAutoRouter(quad_size=64)
        with patch('human_eye_plugin.auto_router.measure_pair_geometry', wraps=measure_pair_geometry) as kernel:
            result = router.handle_event(observation(scene=sparse_scene(), include_image=False))
        self.assertEqual(result['route'], 'engine', result)
        self.assertEqual(kernel.call_count, 1)
        facts = json.loads(result['context_text'])
        self.assertEqual(len(facts['scene_contacts']), 99)
        self.assertEqual(facts['spatial_index']['exact_pair_count'], 1)
        self.assertEqual(facts['spatial_index']['separated_pair_count'], 98)
        self.assertAlmostEqual(facts['measurement']['signed_clearance_m'], .1)
        for contact in facts['scene_contacts']:
            if contact['object_id'] == 'base':
                continue
            self.assertIsNone(contact['signed_clearance_m'])
            self.assertFalse(contact['clearance_exact'])
            self.assertFalse(contact['measurement_valid'])
            self.assertTrue(contact['collision_assessment_valid'])
            self.assertGreater(contact['clearance_lower_bound_m'], 0)
            self.assertIsNone(contact['point_a_world'])

    def test_candidate_index_uses_transformed_focal_and_never_omits_far_obstacle(self):
        router = HumanEyeAutoRouter(quad_size=64)
        observed = router.handle_event(observation(scene=sparse_scene(), include_image=False))
        result = router.handle_event(action(observed, action={'translation': [10, 0, 0]}))
        self.assertFalse(result['allow_action'])
        self.assertEqual(result['reason_codes'], ['candidate_collision'])
        self.assertIn('far0', result['context_text'])

    def test_safe_hundred_object_candidate_has_an_account_for_every_obstacle(self):
        router = HumanEyeAutoRouter(quad_size=64)
        observed = router.handle_event(observation(scene=sparse_scene(), include_image=False))
        with patch('human_eye_plugin.auto_router.measure_pair_geometry', wraps=measure_pair_geometry) as kernel:
            result = router.handle_event(action(observed, action={'translation': [0, 0, .05]}))
        self.assertTrue(result['allow_action'], result)
        self.assertEqual(kernel.call_count, 1)
        checks = json.loads(result['context_text'])['checks']
        self.assertEqual(len(checks), 99)
        self.assertEqual(len({item['object_id'] for item in checks}), 99)

    def test_far_open_mesh_never_receives_a_separation_authorization(self):
        actual = sparse_scene(3)
        actual['meshes'][-1]['faces'] = actual['meshes'][-1]['faces'][:-1]
        result = HumanEyeAutoRouter(quad_size=64).handle_event(observation(scene=actual, include_image=False))
        self.assertEqual(result['route'], 'engine')
        self.assertEqual(result['observation_status'], 'partial')
        self.assertIsNone(result['observation_id'])
        self.assertFalse(result['allow_action'])
        self.assertEqual(result['scene_assessment']['unknown_object_ids'], ['far0'])
        unknown = next(row for row in json.loads(result['context_text'])['scene_contacts']
                       if row['object_id'] == 'far0')
        self.assertFalse(unknown['collision_assessment_valid'])
        self.assertIsNone(unknown['is_penetrating'])

    def test_real_readback_requeries_tiny_gap_even_when_pose_drift_fits_readback_tolerance(self):
        class DriftHost(MutableHost):
            def apply_transform(self, *args, **kwargs):
                result = super().apply_transform(*args, **kwargs)
                focal = MeshEntity3D.from_dict(self.scene['meshes'][1]).translated([5e-7, 0, 0])
                self.scene['meshes'][1] = focal.to_dict()
                return result
        host = DriftHost()
        host.scene['meshes'].append(box('near_obstacle', [.1500002, 0, .4], [.1, .3, .1]))
        runtime = GuardedHostRuntime(host, quad_size=64, readback_atol_m=1e-6)
        runtime.before_model(session_id='s', task_instruction='Measure clearance.',
            focal_id='part', reference_id='base', messages=[], include_image=False)
        result = runtime.execute_action(session_id='s', action={'translation': [0, 0, .05]})
        self.assertEqual(host.calls, 1)
        self.assertFalse(result['verified'])
        self.assertTrue(runtime.status['quarantined'])
        self.assertEqual(result['routing']['reason_codes'], ['host_collision_detected'])


if __name__ == '__main__':
    unittest.main()

"""Real router queries with independent distances, budgets and full write gates."""
import copy
import importlib.util
import json
import math
import unittest
from unittest.mock import patch

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin.auto_router import HumanEyeAutoRouter
from human_eye_plugin import auto_router
from human_eye_plugin.geometry_safety import measure_pair_geometry, work_budget_status
from verification.test_auto_router import action, box, observation, scene
from verification.test_partial_observation import open_plane, partial_scene


def ranking_scene():
    # Direct box interval truth: A=sqrt(.6^2+.6^2), B=.7, reference=2.
    # Conservative L-infinity bounds rank A before B, which is the wrong order.
    value = scene()
    value['meshes'] = [box('part', [0., 0., 0.], [1., 1., 1.], True),
        box('base', [0., 0., 3.], [1., 1., 1.]),
        box('diagonal-A', [1.6, 1.6, 0.], [1., 1., 1.]),
        box('axial-B', [1.7, 0., 0.], [1., 1., 1.])]
    return value


def facts(result):
    return json.loads(result['context_text'])


class ObservationQueryTests(unittest.TestCase):
    def setUp(self):
        self.router = HumanEyeAutoRouter(quad_size=64)

    def observe(self, **changes):
        return self.router.handle_event(observation(include_image=False, **changes))

    def test_default_overview_retains_bounds_and_reference_contract(self):
        result = self.observe(scene=ranking_scene())
        self.assertEqual(result['observation_status'], 'complete')
        self.assertEqual(result['query_result']['status'], 'complete')
        contacts = {record['object_id']: record for record in facts(result)['scene_contacts']}
        self.assertTrue(facts(result)['measurement']['clearance_exact'])
        for identity in ('diagonal-A', 'axial-B'):
            self.assertEqual(contacts[identity]['measurement_kind'], 'lower_bound')
            self.assertFalse(contacts[identity]['clearance_exact'])
            self.assertIsNone(contacts[identity]['signed_clearance_m'])
        self.assertLess(contacts['diagonal-A']['clearance_lower_bound_m'],
                        contacts['axial-B']['clearance_lower_bound_m'])

    def test_nearest_exactly_resolves_the_real_distance_bound_order_reversal(self):
        result = self.observe(scene=ranking_scene(), query={'mode': 'nearest'})
        self.assertEqual(result['route'], 'engine', result)
        queried = result['query_result']
        self.assertEqual(queried['status'], 'complete')
        self.assertEqual(queried['ranked_object_ids'], ['axial-B', 'diagonal-A', 'base'])
        contacts = {record['object_id']: record for record in facts(result)['scene_contacts']}
        self.assertAlmostEqual(contacts['diagonal-A']['signed_clearance_m'], math.sqrt(.72))
        self.assertAlmostEqual(contacts['axial-B']['signed_clearance_m'], .7)
        for record in contacts.values():
            self.assertEqual(record['measurement_kind'], 'exact')
            self.assertTrue(record['clearance_exact'])
            self.assertEqual(record['method'], record['strict_geometry']['clearance_method'])
        self.assertEqual(queried, facts(result)['query_result'])

    def test_exact_subset_retains_all_other_scene_contacts_and_counts_reference_slot(self):
        value = ranking_scene()
        with patch('human_eye_plugin.auto_router.measure_pair_geometry', wraps=measure_pair_geometry) as measured:
            result = self.observe(scene=value, query={'mode': 'exact_pairs',
                'object_ids': ['axial-B'], 'max_exact_pairs': 2})
        self.assertEqual(measured.call_count, 2)
        self.assertEqual(result['query_result']['status'], 'complete')
        self.assertEqual(result['query_result']['requested_object_ids'], ['axial-B'])
        self.assertEqual(len(facts(result)['scene_contacts']), 3)
        contacts = {record['object_id']: record for record in facts(result)['scene_contacts']}
        self.assertEqual(contacts['diagonal-A']['measurement_kind'], 'lower_bound')
        self.assertEqual(set(result['query_result']['exact_object_ids']), {'base', 'axial-B'})

    def test_insufficient_budget_keeps_pair_and_image_but_has_no_false_rank_or_authority(self):
        event = observation(scene=ranking_scene(), query={'mode': 'nearest', 'max_exact_pairs': 1})
        with patch('human_eye_plugin.auto_router.measure_pair_geometry', wraps=measure_pair_geometry) as measured:
            result = self.router.handle_event(event)
        self.assertEqual(measured.call_count, 1)
        self.assertEqual(result['route'], 'engine', result)
        self.assertIsNotNone(result['image'])
        self.assertTrue(result['measurement_valid'])
        self.assertEqual(result['observation_status'], 'partial')
        self.assertIsNone(result['observation_id'])
        self.assertFalse(result['allow_action'])
        self.assertEqual(result['query_result']['status'], 'unknown')
        self.assertIsNone(result['query_result']['ranked_object_ids'])
        self.assertEqual(set(result['query_result']['unresolved_object_ids']), {'diagonal-A', 'axial-B'})
        self.assertIn('query_exact_pair_budget_exhausted', result['query_result']['reason_codes'])
        self.assertEqual(result['scene_assessment']['geometry_support'], 'supported')
        self.assertFalse(self.router.handle_event(action(result))['allow_action'])

    def test_query_mode_subset_and_budget_are_part_of_observation_cache_key(self):
        self.observe(scene=ranking_scene())
        low = self.observe(scene=ranking_scene(), query={'mode': 'nearest', 'max_exact_pairs': 1})
        self.assertFalse(low['cache_hit'])
        warm = self.observe(scene=ranking_scene(), query={'mode': 'nearest', 'max_exact_pairs': 1})
        self.assertTrue(warm['cache_hit'])
        self.assertIsNone(warm['observation_id'])
        high = self.observe(scene=ranking_scene(), query={'mode': 'nearest', 'max_exact_pairs': 3})
        self.assertFalse(high['cache_hit'])
        self.assertEqual(high['query_result']['status'], 'complete')
        subset = self.observe(scene=ranking_scene(), query={'mode': 'nearest', 'object_ids': ['diagonal-A']})
        self.assertFalse(subset['cache_hit'])
        self.assertEqual(subset['query_result']['ranked_object_ids'], ['diagonal-A'])

    def test_persisted_previous_visual_contract_cannot_reuse_its_cached_png(self):
        with patch.object(auto_router, 'OBSERVATION_CONTRACT_REVISION', 'v1-explicit-query-20261023'):
            self.router.handle_event(observation())
        saved = self.router.export_state()
        stored = dict(saved['sessions'])['a']['observation']['result']
        stored['image']['data'] = 'previous-layout-png-sentinel'
        restored = HumanEyeAutoRouter(quad_size=64)
        restored.import_state(saved)
        result = restored.handle_event(observation())
        self.assertFalse(result['cache_hit'])
        self.assertNotEqual(result['image']['data'], 'previous-layout-png-sentinel')
        self.assertEqual(facts(result)['canvas']['view_layout_version'], 'layered-four-view-v2-20261023')

    def test_same_contract_cache_key_is_stable_across_independent_module_import(self):
        self.observe(query={'mode': 'nearest'})
        spec = importlib.util.spec_from_file_location('human_eye_plugin._independent_query_cache_test', auto_router.__file__)
        independent = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(independent)
        self.assertEqual(independent.OBSERVATION_CONTRACT_REVISION, auto_router.OBSERVATION_CONTRACT_REVISION)
        restored = independent.HumanEyeAutoRouter(quad_size=64)
        restored.import_state(self.router.export_state())
        result = restored.handle_event(observation(include_image=False, query={'mode': 'nearest'}))
        self.assertTrue(result['cache_hit'])

    def test_invalid_query_retires_old_observation_and_does_not_enter_measurement(self):
        for query in ({'mode': 'nearest', 'object_ids': ['missing']},
                      {'mode': 'nearest', 'object_ids': ['part']},
                      {'mode': 'nearest', 'max_exact_pairs': True}):
            with self.subTest(query=query):
                complete = self.observe()
                with patch('human_eye_plugin.auto_router.measure_pair_geometry', side_effect=AssertionError('invalid query computed')):
                    result = self.observe(query=query)
                self.assertEqual(result['reason_codes'], ['invalid_query'])
                self.assertFalse(self.router.handle_event(action(complete))['allow_action'])

    def test_partial_unsupported_object_is_unresolved_and_never_assigned_exact_witnesses(self):
        result = self.observe(scene=partial_scene(), query={'mode': 'nearest'})
        self.assertEqual(result['observation_status'], 'partial')
        self.assertEqual(result['query_result']['unresolved_object_ids'], ['open'])
        self.assertIsNone(result['query_result']['ranked_object_ids'])
        unknown = next(record for record in facts(result)['scene_contacts'] if record['object_id'] == 'open')
        self.assertFalse(unknown['clearance_exact'])
        self.assertIsNone(unknown['signed_clearance_m'])
        self.assertIsNone(unknown['point_a_world'])
        self.assertIsNone(unknown['point_b_world'])

    def test_unsupported_target_does_not_waste_exact_slot_or_remove_unknown_inventory(self):
        value = ranking_scene()
        value['meshes'].append(open_plane())
        result = self.observe(scene=value, query={'mode': 'exact_pairs',
            'object_ids': ['open', 'axial-B'], 'max_exact_pairs': 2})
        self.assertIn('axial-B', result['query_result']['exact_object_ids'])
        self.assertEqual(result['query_result']['unresolved_object_ids'], ['open'])
        self.assertEqual(result['scene_assessment']['unknown_object_ids'], ['open'])

    def test_exact_pair_budget_cannot_shorten_candidate_or_actual_readback_safety_gates(self):
        value = scene()
        value['meshes'].append(box('obstacle', [.5, 0., .35], [.2, .2, .2]))
        result = self.observe(scene=value, query={'mode': 'exact_pairs', 'object_ids': ['base'], 'max_exact_pairs': 1})
        self.assertEqual(result['query_result']['status'], 'complete')
        self.assertEqual(result['spatial_index']['exact_pair_count'], 1)
        self.assertEqual(result['spatial_index']['count_scope'], 'observation_measurement_results')
        checked = self.router.handle_event(action(result, action={'translation': [.5, 0., 0.]},
            query={'mode': 'exact_pairs', 'object_ids': ['base'], 'max_exact_pairs': 1}))
        self.assertFalse(checked['allow_action'])
        self.assertEqual(checked['reason_codes'], ['candidate_collision'])

    def test_actual_readback_query_cannot_hide_an_unrequested_obstacle(self):
        value = scene()
        value['meshes'].append(box('obstacle', [2., 0., .4], [.2, .2, .2]))
        observed = self.observe(scene=value, query={'mode': 'exact_pairs', 'object_ids': ['base']})
        allowed = self.router.handle_event(action(observed, action={'translation': [0., 0., .05]}))
        self.assertTrue(allowed['allow_action'])
        pending = dict(self.router.export_state()['sessions'])['a']['pending']
        actual = copy.deepcopy(value)
        actual['revision'] = 'r2'
        actual['meshes'][1] = pending['candidate']
        actual['meshes'][2] = box('obstacle', [0., 0., .4], [.2, .2, .2])
        result = self.router.handle_event(observation(scene=actual, event='after_action',
            query={'mode': 'exact_pairs', 'object_ids': ['base'], 'max_exact_pairs': 1}, include_image=False))
        self.assertFalse(result['allow_action'])
        self.assertEqual(result['reason_codes'], ['host_collision_detected'])

    def test_geometry_resource_limit_in_optional_exact_target_keeps_valid_pair_unresolved(self):
        real_budget = work_budget_status
        def budget(meshes, **options):
            pairs = options.get('query_pairs') or []
            result = real_budget(meshes, **options)
            if any('axial-B' in pair for pair in pairs):
                result.update(within_budget=False, reason_codes=['sat_projection_work_limit'])
            return result
        with patch('human_eye_plugin.auto_router.work_budget_status', side_effect=budget):
            result = self.observe(scene=ranking_scene(), query={'mode': 'nearest'})
        self.assertEqual(result['route'], 'engine', result)
        self.assertTrue(result['measurement_valid'])
        self.assertEqual(result['query_result']['unresolved_object_ids'], ['axial-B'])
        self.assertIn('query_geometry_resource_limit', result['query_result']['reason_codes'])
        self.assertIsNone(result['query_result']['ranked_object_ids'])

    def test_penetration_retains_strict_negative_but_is_not_display_zero_or_exact_depth_rank(self):
        value = scene()
        value['meshes'][1] = MeshEntity3D.from_dict(value['meshes'][1]).translated([0., 0., -.10005]).to_dict()
        observed = self.observe(scene=value)
        self.assertEqual(observed['observation_status'], 'complete')
        metric = facts(observed)['measurement']
        self.assertLess(metric['signed_clearance_m'], 0.)
        self.assertNotIn('alignment_state', metric)
        self.assertTrue(metric['legacy_display']['alignment_state_is_display_only'])
        self.assertEqual(metric['clearance_state'], 'negative_clearance')
        self.assertEqual(metric['measurement_kind'], 'certified_penetration')
        self.assertFalse(metric['clearance_exact'])
        result = self.observe(scene=value, query={'mode': 'nearest'})
        self.assertEqual(result['query_result']['status'], 'unknown')
        self.assertIsNone(result['query_result']['ranked_object_ids'])
        self.assertIn('exact_penetration_depth_not_certified', result['query_result']['reason_codes'])

    def test_exact_ties_sort_by_stable_id_instead_of_scene_or_request_order(self):
        value = ranking_scene()
        value['meshes'][2] = box('z', [2., 0., 0.], [1., 1., 1.])
        value['meshes'][3] = box('a', [-2., 0., 0.], [1., 1., 1.])
        result = self.observe(scene=value, query={'mode': 'nearest', 'object_ids': ['z', 'a']})
        self.assertEqual(result['query_result']['ranked_object_ids'], ['a', 'z'])


if __name__ == '__main__':
    unittest.main()

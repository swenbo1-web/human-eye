"""Independent interval-truth tests for opt-in nearest-one certification.

Only synthetic represented boxes and the real router are used. These tests do
not access Blender, installed configuration, or production state. Bounds and
engine distances are not used to generate the independent box distance truth.
"""
from __future__ import annotations

import copy
import json
import math
import random
import unittest
from unittest.mock import patch

from human_eye_plugin.auto_router import HumanEyeAutoRouter
from human_eye_plugin.geometry_safety import measure_pair_geometry, work_budget_status
from human_eye_plugin.query_policy import validate_query
from human_eye_plugin.top1_query import summarize_top1
from verification.test_auto_router import action, box, observation, scene
from verification.test_partial_observation import open_plane


def boxes(*objects, revision='top1-independent-r1'):
    value = scene(revision)
    value['meshes'] = [box(identity, center, size, identity == 'part')
                       for identity, center, size in objects]
    return value


def interval_distance(left, right):
    """Independent Euclidean distance between two axis-aligned box intervals."""
    gaps = []
    for axis in range(3):
        a = [vertex[axis] for vertex in left['vertices']]
        b = [vertex[axis] for vertex in right['vertices']]
        gaps.append(max(min(a) - max(b), min(b) - max(a), 0.0))
    return math.hypot(*gaps)


def contacts(result):
    return {row['object_id']: row for row in json.loads(result['context_text'])['scene_contacts']}


def near_reference_scene():
    return boxes(('part', [0, 0, 0], [1, 1, 1]),
                 ('base', [1.5, 0, 0], [1, 1, 1]),
                 ('far-east', [5, 0, 0], [1, 1, 1]),
                 ('far-west', [-7, 0, 0], [1, 1, 1]))


def reversal_scene():
    # L-infinity AABB gaps are .6 and .7, but surface distances are sqrt(.72)
    # and .7. Sorting the lower bounds as if they were exact gives the wrong one.
    return boxes(('part', [0, 0, 0], [1, 1, 1]),
                 ('base', [0, 0, 3], [1, 1, 1]),
                 ('diagonal', [1.6, 1.6, 0], [1, 1, 1]),
                 ('axial', [1.7, 0, 0], [1, 1, 1]))


class Top1QueryIndependentTests(unittest.TestCase):
    def setUp(self):
        self.router = HumanEyeAutoRouter(quad_size=64)

    def observe(self, value, query=None, **changes):
        event = observation(scene=value, include_image=False,
                            query={'mode': 'top1'} if query is None else query)
        event.update(changes)
        return self.router.handle_event(event)

    def assert_complete(self, result, expected_ids, expected_distance):
        self.assertEqual(result['route'], 'engine', result)
        query = result['query_result']
        self.assertEqual(query['status'], 'complete', query)
        self.assertIsNone(query['ranked_object_ids'])
        self.assertEqual(query['unresolved_object_ids'], [])
        top = query['top1']
        self.assertEqual(top['status'], 'complete')
        self.assertEqual(top['nearest_object_ids'], expected_ids)
        self.assertIs(top['unique'], len(expected_ids) == 1)
        self.assertAlmostEqual(top['signed_clearance_m'], expected_distance, places=12)
        self.assertEqual(top['proof_method'], 'exact_candidates_and_strict_outward_aabb_lower_bounds')
        self.assertEqual(top['tie_scope'], 'equal_unrounded_engine_distances_not_physical_equivalence')
        self.assertIs(top['execution_authority'], False)
        self.assertEqual(query, json.loads(result['context_text'])['query_result'])
        return top

    def assert_unknown(self, result):
        self.assertEqual(result['route'], 'engine', result)
        query = result['query_result']
        self.assertEqual(query['status'], 'unknown')
        self.assertIsNone(query['ranked_object_ids'])
        top = query['top1']
        self.assertEqual(top['status'], 'unknown')
        self.assertIsNone(top['nearest_object_ids'])
        self.assertIsNone(top['unique'])
        self.assertIsNone(top['signed_clearance_m'])
        self.assertIs(top['execution_authority'], False)
        self.assertEqual(result['observation_status'], 'partial')
        self.assertIsNone(result['observation_id'])
        self.assertIs(result['allow_action'], False)
        return query

    def test_one_exact_reference_proves_nearest_without_measuring_far_objects(self):
        value = near_reference_scene()
        expected = interval_distance(value['meshes'][0], value['meshes'][1])
        with patch('human_eye_plugin.auto_router.measure_pair_geometry', wraps=measure_pair_geometry) as measured:
            result = self.observe(value, {'mode': 'top1', 'max_exact_pairs': 1})
        top = self.assert_complete(result, ['base'], expected)
        self.assertEqual(measured.call_count, 1)
        self.assertEqual(result['query_result']['exact_pair_count'], 1)
        self.assertEqual(result['query_result']['measured_pair_count'], 1)
        self.assertEqual(set(top['excluded_by_lower_bound_ids']), {'far-east', 'far-west'})
        rows = contacts(result)
        self.assertEqual(set(rows), {'base', 'far-east', 'far-west'})
        for identity in top['excluded_by_lower_bound_ids']:
            self.assertFalse(rows[identity]['clearance_exact'])
            self.assertIsNone(rows[identity]['signed_clearance_m'])
            self.assertEqual(rows[identity]['measurement_kind'], 'lower_bound')

    def test_lower_bound_order_reversal_is_resolved_by_actual_surface_distance(self):
        value = reversal_scene()
        distances = {row['object_id']: interval_distance(value['meshes'][0], row)
                     for row in value['meshes'][1:]}
        self.assertLess(distances['axial'], distances['diagonal'])
        result = self.observe(value, {'mode': 'top1', 'max_exact_pairs': 3})
        self.assert_complete(result, ['axial'], distances['axial'])
        self.assertEqual(result['query_result']['exact_pair_count'], 3)

    def test_unrequested_closer_reference_is_not_a_candidate_or_free_slot(self):
        value = near_reference_scene()
        result = self.observe(value, {'mode': 'top1', 'object_ids': ['far-west', 'far-east'],
                                      'max_exact_pairs': 2})
        self.assert_complete(result, ['far-east'], interval_distance(value['meshes'][0], value['meshes'][2]))
        self.assertEqual(result['query_result']['exact_pair_count'], 2)
        self.assertIn('base', result['query_result']['exact_object_ids'])
        limited = self.observe(value, {'mode': 'top1', 'object_ids': ['far-east'],
                                       'max_exact_pairs': 1})
        query = self.assert_unknown(limited)
        self.assertEqual(query['unresolved_object_ids'], ['far-east'])
        self.assertIn('query_exact_pair_budget_exhausted', query['reason_codes'])

    def test_equal_distances_are_joint_nearest_not_a_unique_id_tiebreak(self):
        value = boxes(('part', [0, 0, 0], [1, 1, 1]),
                      ('base', [0, 0, 3], [1, 1, 1]),
                      ('z', [2, 0, 0], [1, 1, 1]),
                      ('a', [-2, 0, 0], [1, 1, 1]))
        for requested in (['z', 'a'], ['a', 'z']):
            with self.subTest(requested=requested):
                result = self.observe(value, {'mode': 'top1', 'object_ids': requested,
                                              'max_exact_pairs': 3})
                top = self.assert_complete(result, ['a', 'z'], 1.0)
                self.assertEqual(top['excluded_by_lower_bound_ids'], [])
                self.assertEqual(result['query_result']['exact_pair_count'], 3)

    def test_budget_cannot_hide_an_unmeasured_equal_nearest(self):
        value = boxes(('part', [0, 0, 0], [1, 1, 1]),
                      ('base', [0, 0, 3], [1, 1, 1]),
                      ('z', [2, 0, 0], [1, 1, 1]),
                      ('a', [-2, 0, 0], [1, 1, 1]))
        query = self.assert_unknown(self.observe(value, {'mode': 'top1', 'max_exact_pairs': 2}))
        self.assertTrue(set(query['unresolved_object_ids']) & {'a', 'z'})
        self.assertIn('query_exact_pair_budget_exhausted', query['reason_codes'])

    def test_reference_equal_to_requested_winner_is_reported_when_both_requested(self):
        value = boxes(('part', [0, 0, 0], [1, 1, 1]),
                      ('base', [2, 0, 0], [1, 1, 1]),
                      ('other', [-2, 0, 0], [1, 1, 1]))
        result = self.observe(value, {'mode': 'top1', 'max_exact_pairs': 2})
        self.assert_complete(result, ['base', 'other'], 1.0)

    def test_unsupported_far_object_is_not_pruned_into_false_completeness(self):
        value = near_reference_scene()
        value['meshes'].append(open_plane('open', center=(50, 0, 0)))
        result = self.observe(value, {'mode': 'top1', 'max_exact_pairs': 1})
        query = self.assert_unknown(result)
        self.assertIn('open', query['unresolved_object_ids'])
        self.assertNotIn('open', query['top1']['excluded_by_lower_bound_ids'])
        self.assertIn('open', {row['object_id'] for row in json.loads(result['context_text'])['unknown_objects']})

    def test_unsupported_unrequested_object_keeps_its_unknown_scene_fact(self):
        value = near_reference_scene()
        value['meshes'].append(open_plane('open', center=(50, 0, 0)))
        result = self.observe(value, {'mode': 'top1', 'object_ids': ['base'], 'max_exact_pairs': 1})
        self.assert_complete(result, ['base'], .5)
        self.assertIn('open', contacts(result))
        self.assertEqual(result['observation_status'], 'partial')
        self.assertIsNone(result['observation_id'])

    def test_geometry_resource_rejection_keeps_reference_but_cannot_prove_top1(self):
        value = near_reference_scene()
        value['meshes'].append(box('heavy', [1.2, 0, 0], [1, 1, 1]))
        real_budget = work_budget_status

        def deny_heavy(meshes, **options):
            result = real_budget(meshes, **options)
            if any('heavy' in pair for pair in options.get('query_pairs') or []):
                result.update(within_budget=False, reason_codes=['sat_projection_work_limit'])
            return result

        with patch('human_eye_plugin.auto_router.work_budget_status', side_effect=deny_heavy):
            result = self.observe(value, {'mode': 'top1', 'max_exact_pairs': 2})
        query = self.assert_unknown(result)
        self.assertIn('heavy', query['unresolved_object_ids'])
        self.assertIn('query_geometry_resource_limit', query['reason_codes'])
        self.assertTrue(result['measurement_valid'])
        self.assertEqual(contacts(result)['base']['measurement_kind'], 'exact')

    def test_negative_clearance_does_not_become_an_exact_nearest_depth(self):
        value = boxes(('part', [0, 0, 0], [1, 1, 1]),
                      ('base', [.9, 0, 0], [1, 1, 1]),
                      ('far', [5, 0, 0], [1, 1, 1]))
        result = self.observe(value, {'mode': 'top1', 'max_exact_pairs': 2})
        query = self.assert_unknown(result)
        self.assertIn('base', query['unresolved_object_ids'])
        self.assertEqual(contacts(result)['base']['measurement_kind'], 'certified_penetration')
        self.assertLess(contacts(result)['base']['signed_clearance_m'], 0)
        self.assertIn('exact_penetration_depth_not_certified', query['reason_codes'])

    def test_zero_metric_can_win_but_does_not_assert_physical_contact(self):
        value = boxes(('part', [0, 0, 0], [1, 1, 1]),
                      ('base', [1, 0, 0], [1, 1, 1]),
                      ('far', [5, 0, 0], [1, 1, 1]))
        result = self.observe(value, {'mode': 'top1', 'max_exact_pairs': 1})
        self.assert_complete(result, ['base'], 0.0)
        self.assertEqual(contacts(result)['base']['clearance_state'], 'zero_clearance')

    def test_micro_gap_and_large_origin_match_represented_interval_truth(self):
        for origin, gap in [(0, 25e-6), (1e6, .004), (1e9, .004)]:
            with self.subTest(origin=origin, gap=gap):
                value = boxes(('part', [origin, origin, origin], [1, 1, 1]),
                              ('base', [origin + 1 + gap, origin, origin], [1, 1, 1]),
                              ('far', [origin + 5, origin, origin], [1, 1, 1]))
                result = self.observe(value, {'mode': 'top1', 'max_exact_pairs': 1})
                self.assert_complete(result, ['base'], interval_distance(value['meshes'][0], value['meshes'][1]))

    def test_query_mode_and_budget_do_not_reuse_an_incompatible_cached_proof(self):
        value = near_reference_scene()
        one = self.observe(value, {'mode': 'top1', 'max_exact_pairs': 1})
        self.assert_complete(one, ['base'], .5)
        hit = self.observe(value, {'mode': 'top1', 'max_exact_pairs': 1})
        self.assertTrue(hit['cache_hit'])
        self.assertEqual(hit['query_result'], one['query_result'])
        nearest = self.observe(value, {'mode': 'nearest', 'max_exact_pairs': 1})
        self.assertFalse(nearest['cache_hit'])
        self.assertEqual(nearest['query_result']['status'], 'unknown')
        self.assertIsNone(nearest['query_result']['ranked_object_ids'])
        self.assertNotIn('top1', nearest['query_result'])

    def test_nearest_keeps_complete_ranking_and_old_exact_tie_id_order(self):
        value = boxes(('part', [0, 0, 0], [1, 1, 1]),
                      ('base', [0, 0, 3], [1, 1, 1]),
                      ('z', [2, 0, 0], [1, 1, 1]),
                      ('a', [-2, 0, 0], [1, 1, 1]))
        result = self.observe(value, {'mode': 'nearest', 'max_exact_pairs': 3})
        self.assertEqual(result['query_result']['ranked_object_ids'], ['a', 'z', 'base'])
        self.assertNotIn('top1', result['query_result'])
        self.assertEqual(result['query_result']['exact_pair_count'], 3)

    def test_top1_cannot_bypass_fresh_before_action_collision_check(self):
        value = scene()
        value['meshes'].append(box('obstacle', [.5, 0, .35], [.2, .2, .2]))
        result = self.observe(value, {'mode': 'top1', 'max_exact_pairs': 1})
        self.assert_complete(result, ['base'], interval_distance(value['meshes'][1], value['meshes'][0]))
        checked = self.router.handle_event(action(result, action={'translation': [.5, 0, 0]},
                                                 query={'mode': 'top1', 'max_exact_pairs': 1}))
        self.assertFalse(checked['allow_action'])
        self.assertEqual(checked['reason_codes'], ['candidate_collision'])

    def test_after_action_actual_readback_keeps_all_obstacle_checks(self):
        value = scene()
        value['meshes'].append(box('obstacle', [2, 0, .4], [.2, .2, .2]))
        observed = self.observe(value, {'mode': 'top1', 'max_exact_pairs': 1})
        allowed = self.router.handle_event(action(observed, action={'translation': [0, 0, .05]}))
        self.assertTrue(allowed['allow_action'])
        pending = dict(self.router.export_state()['sessions'])['a']['pending']
        actual = copy.deepcopy(value)
        actual['revision'] = 'top1-independent-readback-r2'
        actual['meshes'][1] = pending['candidate']
        actual['meshes'][2] = box('obstacle', [0, 0, .4], [.2, .2, .2])
        checked = self.router.handle_event(observation(scene=actual, event='after_action',
            include_image=False, query={'mode': 'top1', 'max_exact_pairs': 1}))
        self.assertFalse(checked['allow_action'])
        self.assertEqual(checked['reason_codes'], ['host_collision_detected'])

    def test_top1_validation_retains_fresh_membership_and_budget_types(self):
        self.assertEqual(validate_query({'mode': 'top1'}), {'mode': 'top1', 'max_exact_pairs': 255})
        for query in [{'mode': 'top1', 'max_exact_pairs': True},
                      {'mode': 'top1', 'object_ids': []},
                      {'mode': 'top1', 'object_ids': ['part']},
                      {'mode': 'top1', 'object_ids': ['missing']}]:
            with self.subTest(query=query), self.assertRaises(ValueError):
                validate_query(query, object_ids={'base', 'part'}, focal_id='part')

    def test_cumulative_geometry_admission_cannot_reset_for_each_new_pair(self):
        value = boxes(('part', [0, 0, 0], [1, 1, 1]),
                      ('base', [0, 0, 3], [1, 1, 1]),
                      ('a', [2, 0, 0], [1, 1, 1]),
                      ('z', [-2, 0, 0], [1, 1, 1]))
        attempts = []

        def deny_third_pair(meshes, **options):
            result = work_budget_status(meshes, **options)
            pairs = options.get('query_pairs') or []
            attempts.append(copy.deepcopy(pairs))
            if len(pairs) > 2:
                result.update(within_budget=False, reason_codes=['scene_geometry_work_limit'])
            return result

        with patch('human_eye_plugin.auto_router.work_budget_status', side_effect=deny_third_pair), \
                patch('human_eye_plugin.auto_router.measure_pair_geometry', wraps=measure_pair_geometry) as measured:
            result = self.observe(value, {'mode': 'top1', 'max_exact_pairs': 3})
        query = self.assert_unknown(result)
        self.assertTrue(any(len(pairs) == 3 for pairs in attempts))
        self.assertEqual(measured.call_count, 2)
        self.assertEqual(query['exact_pair_count'], 2)
        self.assertIn('query_geometry_resource_limit', query['reason_codes'])

    def test_bound_equal_to_guarded_threshold_is_not_a_strict_exclusion(self):
        # Controlled proof-boundary values exercise the mathematical strictness
        # independently of how much padding a real object's AABB happens to get.
        best = {'object_id': 'best', 'measurement_kind': 'exact', 'clearance_exact': True,
                'measurement_valid': True, 'signed_clearance_m': 1.0, 'is_penetrating': False}
        threshold = math.nextafter(1.0, math.inf)
        bound = {'object_id': 'other', 'measurement_kind': 'lower_bound',
                 'clearance_exact': False, 'measurement_valid': False,
                 'signed_clearance_m': None, 'numeric_bound_valid': True,
                 'method': 'outward_aabb_linf_lower_bound'}
        for value, complete in [(threshold, False), (math.nextafter(threshold, math.inf), True)]:
            with self.subTest(bound=value):
                row = dict(bound, clearance_lower_bound_m=value)
                top, unresolved = summarize_top1(requested_ids=['best', 'other'],
                    contacts=[best, row], supported_ids=['best', 'other'], comparison_guard_m=0.0)
                self.assertEqual(top['status'], 'complete' if complete else 'unknown')
                self.assertEqual(unresolved, [] if complete else ['other'])
                self.assertEqual(top['nearest_object_ids'], ['best'] if complete else None)

    def test_fixed_seed_multi_candidate_sets_match_independent_interval_oracle(self):
        generator = random.Random(20261028)
        for sample in range(32):
            specs = [('part', [0, 0, 0], [1, 1, 1]),
                     ('base', [0, 0, 4], [1, 1, 1])]
            for number in range(8):
                coordinate = [0, 0, 0]
                coordinate[generator.randrange(3)] = generator.choice([-1, 1]) * generator.randrange(5, 33) / 4
                specs.append((f'candidate-{number}', coordinate, [1, 1, 1]))
            value = boxes(*specs, revision=f'top1-oracle-{sample}')
            truth = {row['object_id']: interval_distance(value['meshes'][0], row)
                     for row in value['meshes'][1:]}
            distance = min(truth.values())
            winners = sorted(identity for identity, amount in truth.items() if amount == distance)
            with self.subTest(sample=sample, winners=winners):
                result = self.observe(value, {'mode': 'top1', 'max_exact_pairs': 9})
                self.assert_complete(result, winners, distance)
                limited = self.observe(value, {'mode': 'top1', 'max_exact_pairs': 1})
                if limited['query_result']['status'] == 'complete':
                    self.assert_complete(limited, winners, distance)
                    self.assertEqual(winners, ['base'])
                else:
                    self.assert_unknown(limited)


if __name__ == '__main__':
    unittest.main()

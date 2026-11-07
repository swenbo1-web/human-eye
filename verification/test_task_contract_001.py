"""Pair task contract checks using the existing independent analytic fixtures."""
import copy
import json
import math
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin import geometry_safety as geometry
from human_eye_plugin import live_spatial_mcp as mcp
from human_eye_plugin.live_service import LiveSpatialService
from verification import test_task_complete_001 as previous
from verification.perf030_002_cases import closed_counterexample
from verification.test_concave_geometry import box, changed, ring
from verification.test_selected_task_query import SelectedHost
from verification.test_task_complete_001 import (
    changed_control_target, control_pair,
    independent_corner_gap, large_world_pair,
)


LEGACY_FACTS = ['surface_clearance', 'solid_relation', 'nearest_witness']


class PairRelationContractTests(unittest.TestCase):
    setUp = previous.CurrentTaskEvidenceTests.setUp
    set_pair = previous.CurrentTaskEvidenceTests.set_pair
    work = previous.CurrentTaskEvidenceTests.work

    def observe(self, facts=('pair_relation',), order=('a', 'b')):
        return self.service.observe('task-contract', include_image=False,
            query={'mode': 'task', 'objects': [{'id': name} for name in order],
                   'requested_facts': list(facts)})

    def assert_relation(self, result, relation, *, status='measured'):
        fact = result['facts']['pair_relation']
        self.assertEqual(fact['status'], status)
        self.assertEqual(fact['value']['relation'], relation)
        self.assertEqual(fact['relation_tolerance_m'], 0)
        return fact['value']

    def test_separation_reuses_legacy_demands_and_one_witness_traversal(self):
        with patch('human_eye_plugin.task_query.measure_pair_geometry',
                   wraps=geometry.measure_pair_geometry) as measured, \
             patch.object(geometry, '_surface_distance',
                          side_effect=AssertionError('Duplicate scalar traversal')), \
             patch.object(geometry, '_surface_distance_with_witness',
                          wraps=geometry._surface_distance_with_witness) as witness:
            legacy = self.observe(LEGACY_FACTS)
            result = self.observe()
        self.assertEqual(measured.call_count, 1)
        self.assertEqual(witness.call_count, 1)
        self.assertEqual(self.host.captures, 2)
        self.assertTrue(self.work()['pair_cache_hit'])
        self.assertEqual(self.work()['exact_pair_count'], 0)
        self.assertEqual(set(result['facts']), {'pair_relation'})
        value = self.assert_relation(result, 'separated')
        self.assertAlmostEqual(value['surface_gap_m'], .01, delta=1e-14)
        self.assertEqual(value['surface_gap_m'], legacy['facts']['surface_clearance']['value'])
        self.assertEqual(value['nearest_witness'], legacy['facts']['nearest_witness']['value'])
        self.assertEqual(result['status'], 'observed')

    def test_swapped_pair_reverses_direction_and_keeps_original_witnesses(self):
        forward = self.assert_relation(self.observe(), 'separated')
        reverse = self.assert_relation(self.observe(order=('b', 'a')), 'separated')
        self.assertEqual(forward['surface_gap_m'], reverse['surface_gap_m'])
        np.testing.assert_allclose(forward['nearest_witness']['direction_a_to_b'],
                                   [1, 0, 0], rtol=0, atol=1e-14)
        np.testing.assert_allclose(reverse['nearest_witness']['direction_a_to_b'],
                                   [-1, 0, 0], rtol=0, atol=1e-14)
        points = reverse['nearest_witness']
        self.assertAlmostEqual(math.dist(points['a'], points['b']), .01, delta=1e-14)
        self.assertAlmostEqual(points['a'][0], .06, delta=1e-14)
        self.assertAlmostEqual(points['b'][0], .05, delta=1e-14)

    def test_rotated_pair_preserves_independent_gap_and_direction(self):
        angle = .37
        rotation = np.array([[math.cos(angle), -math.sin(angle), 0],
                             [math.sin(angle), math.cos(angle), 0], [0, 0, 1.]])
        left, right = control_pair()
        self.set_pair(changed(left, vertices=left.vertices @ rotation.T),
                      changed(right, vertices=right.vertices @ rotation.T))
        value = self.assert_relation(self.observe(), 'separated')
        self.assertAlmostEqual(value['surface_gap_m'], .01, delta=1e-14)
        points = value['nearest_witness']
        self.assertAlmostEqual(math.dist(points['a'], points['b']), .01, delta=1e-14)
        np.testing.assert_allclose(points['direction_a_to_b'], rotation @ [1, 0, 0],
                                   rtol=0, atol=1e-13)

    def test_exact_touch_is_complete_without_a_direction_or_unrequested_fact(self):
        self.set_pair(box((0, 0, 0), (1, 1, 1), 'a'),
                      box((1, 0, 0), (1, 1, 1), 'b'))
        result = self.observe()
        value = self.assert_relation(result, 'touching')
        self.assertEqual(value['surface_gap_m'], 0)
        self.assertNotIn('direction_a_to_b', value)
        self.assertNotIn('nearest_witness', value)
        self.assertEqual(set(result['facts']), {'pair_relation'})
        self.assertEqual(result['status'], 'observed')

    def test_penetration_reuses_evidence_and_explicit_nearest_remains_unknown(self):
        left, right = control_pair()
        self.set_pair(changed_control_target(left), right)
        with patch('human_eye_plugin.task_query.measure_pair_geometry',
                   wraps=geometry.measure_pair_geometry) as measured, \
             patch.object(geometry, '_surface_distance_with_witness',
                          side_effect=AssertionError('Overlap surface witness traversal')):
            result = self.observe()
            explicit = self.observe(['pair_relation', 'nearest_witness'])
            legacy = self.observe(LEGACY_FACTS)
        self.assertEqual(measured.call_count, 1)
        self.assertEqual(result['status'], 'observed')
        value = self.assert_relation(result, 'penetrating')
        self.assertNotIn('surface_gap_m', value)
        self.assertNotIn('nearest_witness', value)
        evidence = value['evidence']
        self.assertEqual(evidence, legacy['facts']['solid_relation']['evidence'])
        self.assertAlmostEqual(evidence['escape_distance_m'], .005, delta=1e-14)
        np.testing.assert_allclose(evidence['escape_vector_a_world_m'], [-.005, 0, 0],
                                   rtol=0, atol=1e-14)
        self.assertFalse(evidence['world_apply_verified'])
        self.assertIn('not_nearest_direction_or_global_minimum', evidence['escape_scope'])
        self.assertEqual(explicit['facts']['pair_relation'], result['facts']['pair_relation'])
        self.assertEqual(explicit['facts']['nearest_witness'], legacy['facts']['nearest_witness'])
        self.assertEqual(explicit['facts']['nearest_witness']['reason'],
                         'no_surface_witness_for_escape_metric')
        self.assertEqual(explicit['status'], 'partial')

    def test_tolerance_suppressed_overlap_and_legacy_relation_are_distinct(self):
        overlap = 2.0 ** -32
        self.set_pair(box((0, 0, 0), (1, 1, 1), 'a'),
                      box((1 - overlap, 0, 0), (1, 1, 1), 'b'))
        result = self.observe(['pair_relation', 'solid_relation', 'surface_clearance'])
        value = self.assert_relation(result, 'penetrating')
        self.assertTrue(value['evidence']['zero_tolerance_is_penetrating'])
        self.assertEqual(value['evidence']['escape_distance_m'], overlap)
        legacy = result['facts']['solid_relation']
        self.assertEqual(legacy['value'], 'not_penetrating')
        self.assertEqual(legacy['tolerance_m'], geometry.COLLISION_TOLERANCE_M)
        self.assertEqual(result['facts']['surface_clearance']['value'], -overlap)

    def test_sub_tolerance_positive_gap_remains_separated(self):
        gap = 2.0 ** -32
        self.set_pair(box((0, 0, 0), (1, 1, 1), 'a'),
                      box((1 + gap, 0, 0), (1, 1, 1), 'b'))
        value = self.assert_relation(self.observe(), 'separated')
        self.assertEqual(value['surface_gap_m'], gap)
        self.assertGreater(value['surface_gap_m'], 0)
        np.testing.assert_array_equal(value['nearest_witness']['direction_a_to_b'], [1, 0, 0])

    def test_large_world_publication_failure_preserves_known_gap_and_reason(self):
        left, right = large_world_pair()
        self.set_pair(left, right)
        result = self.observe()
        value = self.assert_relation(result, 'separated', status='unknown')
        self.assertEqual(result['status'], 'partial')
        self.assertAlmostEqual(value['surface_gap_m'], independent_corner_gap(left, right), delta=1e-14)
        self.assertNotIn('nearest_witness', value)
        self.assertEqual(result['facts']['pair_relation']['reason'],
                         'original_surface_witness_precision_exceeded')

    def test_unsupported_geometry_keeps_pair_unknown(self):
        self.host.scene['meshes'][0]['faces'] = [[0, 2, 1]]
        self.host.scene['meshes'][0]['edges'] = [[0, 2], [2, 1], [1, 0]]
        result = self.observe(['pair_relation', 'surface_clearance', 'solid_relation'])
        self.assertEqual(result['status'], 'partial')
        for fact in result['facts'].values():
            self.assertEqual(fact['status'], 'unknown')
            self.assertTrue(fact['reason'])
        self.assertIsNone(result['facts']['pair_relation']['value'])

    def test_ambiguous_selector_does_not_compute_a_pair(self):
        other = copy.deepcopy(self.host.scene['meshes'][0])
        other['object_id'] = 'other'
        self.host.scene['meshes'].append(other)
        with patch('human_eye_plugin.task_query.measure_pair_geometry',
                   side_effect=AssertionError('Unresolved pair solver')):
            result = self.service.observe('ambiguous', include_image=False, query={
                'mode': 'task', 'objects': [{'name': 'a'}, {'name': 'b'}],
                'requested_facts': ['pair_relation']})
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['binding']['objects'][0]['reason'], 'object_name_ambiguous')
        self.assertEqual(result['facts']['pair_relation']['reason'], 'selector_unresolved')

    def test_runtime_hash_stays_fixed_while_current_scene_binding_and_answer_change(self):
        with patch('human_eye_plugin.task_query.measure_pair_geometry',
                   wraps=geometry.measure_pair_geometry) as measured:
            initial = self.observe()
            self.host.scene['revision'] = 'r2'
            revised = self.observe()
            self.assertTrue(self.work()['pair_cache_hit'])
            left, right = control_pair()
            self.set_pair(changed_control_target(left), right, 'r3')
            updated = self.observe()
        self.assertEqual(measured.call_count, 2)
        self.assertEqual(initial['schema_version'], 'task-query-v3')
        for result in (initial, revised, updated):
            self.assertEqual(result['binding']['runtime_source_sha256'],
                             self.service._identity['source_sha256'])
            self.assertNotIn('source_sha256', result['binding'])
        self.assertEqual(initial['facts'], revised['facts'])
        self.assertEqual(revised['binding']['scene_revision'], 'r2')
        self.assertNotEqual(initial['binding']['scene_fingerprint'], revised['binding']['scene_fingerprint'])
        self.assertEqual(updated['binding']['scene_revision'], 'r3')
        self.assertNotEqual(updated['binding']['scene_fingerprint'], revised['binding']['scene_fingerprint'])
        self.assert_relation(updated, 'penetrating')

    def test_orthogonal_penetration_retains_actual_method_without_convex_sat_claim(self):
        self.set_pair(box((.025, 0, 0), identity='a'), ring())
        result = self.observe(order=('a', 'ring'))
        value = self.assert_relation(result, 'penetrating')
        evidence = value['evidence']
        self.assertEqual(evidence['method'], 'exact_orthogonal_cell_union_escape')
        self.assertGreater(evidence['escape_distance_m'], 0)
        self.assertNotIn('convex_sat', json.dumps(evidence))
        self.assertNotIn('surface_gap_m', value)

    def test_existing_multi_component_separation_keeps_original_surface_witness(self):
        left, right = closed_counterexample()
        self.set_pair(left, right)
        value = self.assert_relation(self.observe(), 'separated')
        self.assertAlmostEqual(value['surface_gap_m'], .25, delta=1e-14)
        witness = value['nearest_witness']
        self.assertAlmostEqual(math.dist(witness['a'], witness['b']), .25, delta=1e-14)

    def test_multi_component_overlap_keeps_existing_escape_method(self):
        _, right = closed_counterexample()
        self.set_pair(box((1.5, .25, -.25), (.2, .2, .2), 'a'), right)
        value = self.assert_relation(self.observe(), 'penetrating')
        evidence = value['evidence']
        self.assertEqual(evidence['method'], 'convex_components_escape')
        self.assertGreater(evidence['escape_distance_m'], 0)
        self.assertFalse(evidence['world_apply_verified'])
        self.assertNotIn('surface_gap_m', value)

    def test_incomplete_penetration_evidence_does_not_promote_fact_to_complete(self):
        strict = {'measurement_valid': True, 'is_penetrating': True,
                  'signed_clearance_m': -.25}
        with patch('human_eye_plugin.task_query.measure_pair_geometry', return_value=strict):
            result = self.observe()
        self.assert_relation(result, 'penetrating', status='unknown')
        self.assertEqual(result['status'], 'partial')
        self.assertTrue(result['facts']['pair_relation']['reason'])

    def test_conflicting_penetration_flag_and_zero_metric_remain_unknown(self):
        strict = {'measurement_valid': True, 'is_penetrating': True,
                  'signed_clearance_m': 0.0}
        with patch('human_eye_plugin.task_query.measure_pair_geometry', return_value=strict):
            result = self.observe()
        fact = result['facts']['pair_relation']
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(fact['status'], 'unknown')
        self.assertIsNone(fact['value'])
        self.assertEqual(fact['reason'], 'strict_measurement_conflict')

    def test_conflicting_zero_tolerance_evidence_and_zero_metric_remain_unknown(self):
        strict = {'measurement_valid': True, 'is_penetrating': False,
                  'signed_clearance_m': 0.0,
                  'relation_evidence': {'zero_tolerance_is_penetrating': True}}
        with patch('human_eye_plugin.task_query.measure_pair_geometry', return_value=strict):
            result = self.observe()
        fact = result['facts']['pair_relation']
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(fact['status'], 'unknown')
        self.assertIsNone(fact['value'])
        self.assertEqual(fact['reason'], 'strict_relation_conflict')


class PairRelationTransportTests(unittest.TestCase):
    setUp = previous.CurrentTaskEvidenceTests.setUp
    set_pair = previous.CurrentTaskEvidenceTests.set_pair

    def test_selected_pair_is_captured_once_and_encoded_once(self):
        current_scene = self.host.scene
        self.host = SelectedHost()
        self.host.scene = current_scene
        self.host.instances = {'a': '11', 'b': '12'}
        self.service = LiveSpatialService(self.service.config_path, host=self.host)
        with patch.object(self.host, 'capture_scene', side_effect=AssertionError('Full scene capture')):
            result = self.service.observe('selected-pair', include_image=False, query={
                'mode': 'task', 'objects': [{'id': 'a'}, {'id': 'b'}],
                'requested_facts': ['pair_relation']})
        self.assertEqual(len(self.host.selected_calls), 1)
        self.assertEqual(result['binding']['selected_count'], 2)
        with patch.object(mcp.json, 'dumps', wraps=json.dumps) as encoded, \
             patch.object(mcp.copy, 'deepcopy', side_effect=AssertionError('Duplicate response copy')):
            reply = mcp._tool_result(result, is_error=False, response_detail='brief')
        self.assertEqual(encoded.call_count, 1)
        self.assertEqual(json.loads(reply['content'][0]['text']), result)
        self.assertEqual(len(reply['content']), 1)


if __name__ == '__main__':
    unittest.main()

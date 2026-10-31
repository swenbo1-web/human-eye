"""Independent geometry and compact-output boundaries for support discovery."""
from __future__ import annotations

import copy
import json
import math
import unittest
from unittest.mock import patch

from human_eye_plugin.auto_router import _validated_scene
from human_eye_plugin.support_plane_discovery import (
    SUPPORT_PLANE_DISCOVERY_REQUEST_SCHEMA, validate_support_plane_discovery_request,
    discover_support_planes,
)
from human_eye_plugin.support_plane_candidate import _rational_mesh
from human_eye_plugin.geometry_safety import measure_pair_geometry
from verification.test_support_plane_candidate import (
    flat_scene, tilted_scene, slope_scene, tetra_scene, normal_gap, host_frame,
)
from verification.test_auto_router import box
from verification.test_concave_geometry import ring


def discover(scene=None, request=None):
    return discover_support_planes(flat_scene() if scene is None else scene,
                                   'part', 'base', {} if request is None else request)


class DiscoveryRequestTests(unittest.TestCase):
    def test_defaults_and_schema_are_small_and_explicit(self):
        self.assertEqual(validate_support_plane_discovery_request({}), {'max_candidates': 4})
        self.assertFalse(SUPPORT_PLANE_DISCOVERY_REQUEST_SCHEMA['additionalProperties'])
        self.assertNotIn('direction_world', validate_support_plane_discovery_request({}))
        self.assertEqual(set(SUPPORT_PLANE_DISCOVERY_REQUEST_SCHEMA['properties']),
                         {'direction_world', 'max_candidates'})

    def test_candidate_limit_requires_bounded_integer(self):
        for invalid in (True, False, 0, 7, -1, 1.0, '2', None):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_support_plane_discovery_request({'max_candidates': invalid})
        for valid in (1, 4, 6):
            self.assertEqual(validate_support_plane_discovery_request({'max_candidates': valid}),
                             {'max_candidates': valid})

    def test_direction_rejects_bad_shapes_types_and_nonfinite_values(self):
        for invalid in ([0, 0, 0], [0, 1], [0, 0, 1, 0], [True, 0, 1],
                        [0, '0', 1], [0, float('nan'), 1], [0, float('inf'), 1],
                        [0, 0, 10**1000], 'z', None):
            with self.subTest(kind=type(invalid).__name__), self.assertRaises(ValueError):
                validate_support_plane_discovery_request({'direction_world': invalid})

    def test_validation_is_idempotent_and_does_not_mutate_input(self):
        supplied = {'direction_world': [1, 2, 3], 'max_candidates': 6}
        initial = copy.deepcopy(supplied)
        normalized = validate_support_plane_discovery_request(supplied)
        self.assertEqual(normalized['direction_world'], [1., 2., 3.])
        expected = copy.deepcopy(normalized)
        for _ in range(50):
            normalized = validate_support_plane_discovery_request(normalized)
            self.assertEqual(normalized, expected)
        self.assertEqual(supplied, initial)

    def test_unknown_fields_and_nonobjects_are_not_silently_ignored(self):
        for invalid in (None, True, [], 'auto', {'axis': '+z'}, {'execute': True},
                        {'selection_binding': {}}, {'max_candidates': 4, 'force': True}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_support_plane_discovery_request(invalid)


class SupportDiscoveryTests(unittest.TestCase):
    def test_flat_pair_merges_two_original_top_triangles(self):
        value = discover()
        self.assertEqual(value['status'], 'complete', value)
        self.assertEqual(value['total_candidate_count'], 1)
        self.assertEqual(value['returned_candidate_count'], 1)
        self.assertEqual(value['omitted_candidate_count'], 0)
        self.assertTrue(value['all_candidates_returned'])
        self.assertTrue(value['enumeration_complete'])
        self.assertFalse(value['ambiguous'])
        candidate = value['candidates'][0]
        self.assertEqual(candidate['coplanar_triangle_count'], 2)
        self.assertEqual(candidate['selector']['reference_triangle_index'], 2)
        self.assertEqual(candidate['plane_normal_world'], [0., 0., 1.])
        self.assertAlmostEqual(candidate['clearance_m'], .004, places=12)
        self.assertEqual(value['scanned_reference_triangle_count'], 12)
        self.assertEqual(value['exact_plane_group_count'], 6)

    def test_binding_names_the_actual_current_pair_revision_and_fingerprint(self):
        scene = flat_scene()
        result = discover(scene)
        selector = result['candidates'][0]['selector']
        self.assertEqual(set(selector), {'reference_triangle_index', 'selection_binding'})
        self.assertEqual(selector['selection_binding'], {
            'scene_revision': scene['revision'], 'scene_fingerprint': _validated_scene(scene)[2],
            'focal_id': 'part', 'reference_id': 'base'})

    def test_tilted_part_uses_actual_vertex_plane_gap(self):
        scene = tilted_scene()
        result = discover(scene, {'direction_world': [0, 0, 1]})
        self.assertEqual(result['status'], 'complete', result)
        self.assertAlmostEqual(result['current_clearance_m'], normal_gap(scene), places=12)
        self.assertEqual(result['candidates'][0]['directional_derivative'], 1.)

    def test_wedge_reports_normal_distance_and_oblique_derivative(self):
        scene = slope_scene()
        result = discover(scene, {'direction_world': [0, 0, 4]})
        self.assertEqual(result['status'], 'complete', result)
        candidate = result['candidates'][0]
        self.assertAlmostEqual(candidate['clearance_m'], .015/math.sqrt(1.25), places=10)
        self.assertAlmostEqual(candidate['clearance_m'], normal_gap(scene, (-.5, 0., 1.)), places=12)
        self.assertAlmostEqual(candidate['directional_derivative'], 1/math.sqrt(1.25), places=14)
        self.assertNotAlmostEqual(candidate['clearance_m'], .015, places=5)

    def test_no_direction_is_invented_for_geometry_only_request(self):
        result = discover()
        self.assertIsNone(result['direction_world'])
        self.assertIsNone(result['candidates'][0]['directional_derivative'])
        self.assertNotIn('direction_world', result['request'])

    def test_direction_is_locally_normalized_but_request_retains_input(self):
        request = {'direction_world': [0, 0, 7]}
        result = discover(request=request)
        self.assertEqual(result['request']['direction_world'], [0., 0., 7.])
        self.assertEqual(result['direction_world'], [0., 0., 1.])
        self.assertEqual(request, {'direction_world': [0, 0, 7]})

    def test_reverse_direction_changes_derivative_not_geometric_selector(self):
        forward = discover(request={'direction_world': [0, 0, 1]})['candidates'][0]
        reverse = discover(request={'direction_world': [0, 0, -1]})['candidates'][0]
        self.assertEqual(forward['selector'], reverse['selector'])
        self.assertEqual(forward['clearance_m'], reverse['clearance_m'])
        self.assertEqual(reverse['directional_derivative'], -1.)

    def test_parallel_and_near_parallel_directions_return_no_usable_selector(self):
        for direction in ([1, 0, 0], [1, 0, 1e-10]):
            with self.subTest(direction=direction):
                result = discover(request={'direction_world': direction})
                self.assertEqual(result['status'], 'unsupported')
                self.assertEqual(result['candidates'], [])
                self.assertTrue(result['enumeration_complete'])
                self.assertEqual(result['direction_filtered_plane_count'], 1)

    def test_representative_triangle_itself_must_contain_the_original_foot(self):
        # q lies strictly in the other half of the top rectangle. Selecting
        # the lowest coplanar index 2 without testing its footprint is wrong.
        result = discover(tetra_scene((-.05, .05, .104)))
        self.assertEqual(result['status'], 'complete', result)
        self.assertEqual(result['candidates'][0]['coplanar_triangle_count'], 2)
        self.assertEqual(result['candidates'][0]['selector']['reference_triangle_index'], 3)

    def test_exact_diagonal_foot_is_legal_and_chooses_lowest_valid_index(self):
        result = discover(tetra_scene((.05, .05, .104)))
        self.assertEqual(result['status'], 'complete', result)
        self.assertEqual(result['candidates'][0]['selector']['reference_triangle_index'], 2)

    def test_one_ulp_outside_finite_top_is_never_rounded_onto_surface(self):
        inside = tetra_scene((math.nextafter(.1, 0), 0., .104))
        outside = tetra_scene((math.nextafter(.1, math.inf), 0., .104))
        self.assertEqual(discover(inside)['status'], 'complete')
        result = discover(outside)
        self.assertEqual(result['status'], 'unsupported', result)
        self.assertEqual(result['candidates'], [])

    def test_open_reversed_and_nonconvex_original_shells_are_not_hull_fitted(self):
        variants = []
        open_scene = flat_scene(); open_scene['meshes'][0]['faces'].pop(); variants.append(open_scene)
        reverse_scene = flat_scene(); reverse_scene['meshes'][0]['faces'] = [list(reversed(f)) for f in reverse_scene['meshes'][0]['faces']]; variants.append(reverse_scene)
        cavity = flat_scene(); concave = ring().to_dict(); concave.update(object_id='base', mark_label='#base'); cavity['meshes'][0] = host_frame(concave); variants.append(cavity)
        for scene in variants:
            with self.subTest(name=scene['meshes'][0]['name']):
                result = discover(scene)
                self.assertEqual(result['status'], 'unsupported', result)
                self.assertEqual(result['candidates'], [])

    def test_contact_and_penetration_do_not_become_positive_support(self):
        for gap in (0., -.001):
            with self.subTest(gap=gap):
                result = discover(flat_scene(gap))
                self.assertEqual(result['status'], 'unsupported', result)
                self.assertEqual(result['candidates'], [])

    def test_boolean_or_string_coordinates_are_not_coerced_to_geometry(self):
        for invalid in (True, '0.1'):
            scene = flat_scene(); scene['meshes'][0]['vertices'][0][0] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                discover(scene)

    def test_pair_resource_limit_stops_before_geometry_conversion(self):
        scene = flat_scene(); scene['meshes'][0]['vertices'] += [[0., 0., 0.]] * 57
        with patch('human_eye_plugin.auto_router._validated_scene') as conversion:
            result = discover(scene)
        conversion.assert_not_called()
        self.assertEqual(result['status'], 'unknown')
        self.assertIn('resource_limit', result['reason_codes'][0])

    def test_fraction_input_complexity_is_bounded_without_approximate_repair(self):
        scene = flat_scene(); scene['meshes'][0]['vertices'][0][0] = 1e-200
        result = discover(scene)
        self.assertEqual(result['status'], 'unknown', result)
        self.assertEqual(result['reason_codes'], ['support_plane_rational_resource_limit'])

    def test_exact_mesh_validation_is_once_per_pair_and_strict_metric_once(self):
        with patch('human_eye_plugin.support_plane_candidate._rational_mesh', wraps=_rational_mesh) as rational:
            with patch('human_eye_plugin.support_plane_candidate.measure_pair_geometry', wraps=measure_pair_geometry) as strict:
                result = discover(slope_scene())
        self.assertEqual(result['status'], 'complete', result)
        self.assertEqual(rational.call_count, 2)
        self.assertEqual(strict.call_count, 1)

    def test_unknown_or_conflicting_strict_metric_cancels_all_candidates(self):
        records = [
            {'measurement_valid': False, 'is_penetrating': None, 'signed_clearance_m': None},
            {'measurement_valid': True, 'is_penetrating': False, 'signed_clearance_m': .005},
            {'measurement_valid': True, 'is_penetrating': True, 'signed_clearance_m': .004},
        ]
        for record in records:
            with self.subTest(record=record):
                with patch('human_eye_plugin.support_plane_candidate.measure_pair_geometry', return_value=record):
                    result = discover()
                self.assertEqual(result['status'], 'unknown', result)
                self.assertEqual(result['candidates'], [])

    def test_known_strict_kernel_exception_is_unknown_without_partial_selector(self):
        with patch('human_eye_plugin.support_plane_candidate.measure_pair_geometry', side_effect=ValueError('bad kernel')):
            result = discover()
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['reason_codes'], ['strict_pair_measurement_failed'])
        self.assertEqual(result['candidates'], [])

    def test_host_frame_unavailable_remains_unsupported_for_the_solver_domain(self):
        scene = flat_scene(); scene['meshes'][1]['axes_source'] = 'inferred'
        result = discover(scene)
        self.assertEqual(result['status'], 'unsupported')
        self.assertEqual(result['reason_codes'], ['rigid_frame_unavailable'])

    def test_pair_selector_is_not_whole_scene_collision_or_execution_proof(self):
        scene = flat_scene(); obstacle = host_frame(box('obstacle', [0, 0, .151], [.1, .1, .01]))
        obstacle['faces'] = obstacle['faces'][:2]; obstacle['edges'] = None; scene['meshes'].append(obstacle)
        result = discover(scene)
        self.assertEqual(result['status'], 'complete', result)
        for field in ('execution_authority', 'whole_scene_collision_certified',
                      'swept_path_certified', 'task_success_certified'):
            self.assertIs(result[field], False)
        self.assertIs(result['candidates'][0]['execution_authority'], False)

    def test_geometry_and_request_are_unchanged_and_selector_is_detached(self):
        scene = tilted_scene(); request = {'direction_world': [1, 0, 2]}
        scene_before, request_before = copy.deepcopy(scene), copy.deepcopy(request)
        result = discover(scene, request)
        self.assertEqual(scene, scene_before); self.assertEqual(request, request_before)
        result['candidates'][0]['selector']['selection_binding']['focal_id'] = 'elsewhere'
        self.assertEqual(scene, scene_before)

    def test_compact_candidate_has_no_mesh_arrays_or_exact_fraction_dump(self):
        result = discover(slope_scene(), {'direction_world': [0, 0, 1]})
        encoded = json.dumps(result, allow_nan=False)
        for absent in ('"vertices"', '"faces"', '"barycentric_exact"', '"point_a_world"'):
            self.assertNotIn(absent, encoded)
        self.assertLess(len(encoded.encode('utf-8')), 3000)

    def test_changed_scene_revision_produces_different_selector_binding(self):
        scene = flat_scene(); first = discover(scene)
        scene['revision'] = 'new-scene-revision'; second = discover(scene)
        self.assertNotEqual(first['candidates'][0]['selector'], second['candidates'][0]['selector'])

    def test_revision_too_long_for_execution_binding_cannot_publish_selector(self):
        scene = flat_scene(); scene['revision'] = 'r' * 257
        result = discover(scene)
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['candidates'], [])
        self.assertEqual(result['reason_codes'], ['selection_binding_revision_outside_supported_range'])


if __name__ == '__main__':
    unittest.main()

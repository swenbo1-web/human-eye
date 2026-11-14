"""Lossless region-to-world descriptions using exact source-corner answers."""

import copy
from fractions import Fraction
import json
import unittest
from unittest.mock import patch

from human_eye_plugin.active_observation import Region, prepare_scene, region_world_description
from verification.test_active_observation_patches import camera_pool, rectangle_mesh


WORLD_FIELDS = ('center_world_m', 'half_edge_u_world_m', 'half_edge_v_world_m', 'front_direction_world')


def source_region(q0, edge_u, edge_v):
    q0 = tuple(Fraction(value) for value in q0)
    u, v = (tuple(Fraction(value) for value in edge) for edge in (edge_u, edge_v))
    q1 = tuple(a + b for a, b in zip(q0, u))
    q3 = tuple(a + b for a, b in zip(q0, v))
    q2 = tuple(a + b + c for a, b, c in zip(q0, u, v))
    normal = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    return Region('source-quad', 0, 'Source', (0, 1), (q0, q1, q2, q3), normal)


def decoded_vectors(description):
    return {name: tuple(Fraction(value) for value in description[name]) for name in WORLD_FIELDS}


def reconstructed_corners(description):
    values = decoded_vectors(description)
    center, u, v = (values[name] for name in WORLD_FIELDS[:3])
    return tuple(tuple(c + su * a + sv * b for c, a, b in zip(center, u, v))
                 for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)))


def world_table(session):
    return {row['roi_id']: {name: row[name] for name in WORLD_FIELDS} for row in session.short_facts()['regions']}


class ActiveObservationRegionWorldTests(unittest.TestCase):
    def assert_source_corners_and_front(self, region, description):
        self.assertEqual(reconstructed_corners(description), region.vertices)
        direction = decoded_vectors(description)['front_direction_world']
        largest = max(abs(value) for value in region.normal)
        self.assertEqual(direction, tuple(value / largest for value in region.normal))
        self.assertEqual(max(abs(value) for value in direction), 1)

    def test_non_axis_aligned_rectangle_matches_direct_source_corners(self):
        region = source_region((Fraction(1, 3), Fraction(-2, 5), Fraction(7, 11)), (2, 2, 0), (2, -2, 4))
        description = region_world_description(region)
        self.assert_source_corners_and_front(region, description)
        self.assertEqual(description['front_direction_world'], [1, -1, -1])
        self.assertNotEqual(sum(value * value for value in decoded_vectors(description)['front_direction_world']), 1)

    def test_simple_numbers_and_fraction_strings_preserve_exact_values(self):
        region = source_region((0, 0, Fraction(1, 8)), (Fraction(1, 2), 0, 0), (0, 1, 0))
        description = region_world_description(region)
        self.assertEqual(description['center_world_m'], [0.25, 0.5, 0.125])
        self.assertTrue(all(type(value) is float for value in description['center_world_m']))
        self.assertTrue(all(type(value) is int for value in description['front_direction_world']))
        third = source_region((0, 0, Fraction(1, 3)), (1, 0, 0), (0, 1, 0))
        third_description = region_world_description(third)
        self.assertEqual(third_description['center_world_m'][2], '1/3')
        parsed = json.loads(json.dumps(third_description, allow_nan=False))
        self.assert_source_corners_and_front(third, parsed)

    def test_huge_and_underflowing_rationals_are_lossless(self):
        region = source_region((Fraction(10 ** 400, 3), Fraction(1, 3), Fraction(1, 2 ** 1100)),
                               (Fraction(1, 5), 0, 0), (0, Fraction(1, 7), 0))
        description = json.loads(json.dumps(region_world_description(region), allow_nan=False))
        self.assertTrue(all(type(value) is str for value in description['center_world_m']))
        self.assert_source_corners_and_front(region, description)
        integral = source_region((10 ** 400, 0, 0), (2, 0, 0), (0, 2, 0))
        integral_description = region_world_description(integral)
        self.assertEqual(integral_description['center_world_m'][0], 10 ** 400 + 1)
        self.assertIs(type(integral_description['center_world_m'][0]), int)
        self.assert_source_corners_and_front(integral, integral_description)

    def test_prepare_computes_once_and_short_facts_do_not_recompute(self):
        scene = {'objects': [rectangle_mesh()]}
        with patch('human_eye_plugin.active_observation.region_world_description', wraps=region_world_description) as describe:
            session = prepare_scene(scene, camera_pool(), diagnostics=True)
            self.assertEqual(describe.call_count, len(session.regions))
            original = session.short_facts()
            original['regions'][0]['center_world_m'][0] = 'changed-by-caller'
            fresh = session.short_facts()
            self.assertNotEqual(fresh['regions'][0]['center_world_m'][0], 'changed-by-caller')
            self.assertEqual(describe.call_count, len(session.regions))
        for region, row in zip(session.regions, fresh['regions']):
            self.assert_source_corners_and_front(region, row)
        stage = session.diagnostics['stages']['world_descriptions']
        self.assertEqual(stage['elapsed_ns'], stage['closed_ns'] - stage['started_ns'])

    def test_reorder_and_legal_subdivision_preserve_world_descriptions(self):
        first = rectangle_mesh('First')
        second = rectangle_mesh('Second', x=3, z=1)
        original = prepare_scene({'objects': [first, second]}, camera_pool())
        divided = rectangle_mesh('Renamed', segments=4)
        order = list(reversed(range(len(divided['vertices']))))
        old_to_new = {old: new for new, old in enumerate(order)}
        divided['vertices'] = [divided['vertices'][old] for old in order]
        divided['triangles'] = [[old_to_new[index] for index in face] for face in reversed(divided['triangles'])]
        changed = prepare_scene({'objects': [second, divided]}, camera_pool())
        self.assertEqual(world_table(original), world_table(changed))
        for region in changed.regions:
            source = changed.objects[region.object_index]
            source_corners = {source[0][index] for face_index in region.triangle_indices
                              for index in source[1][face_index] if source[0][index] in region.vertices}
            self.assertEqual(set(reconstructed_corners(world_table(changed)[region.roi_id])), source_corners)

    def test_rebind_replaces_descriptions_from_the_new_prepared_source(self):
        session = prepare_scene({'objects': [rectangle_mesh()]}, camera_pool())
        before = world_table(session)
        replacement = {'objects': [rectangle_mesh(x=Fraction(1, 3))]}
        with patch('human_eye_plugin.active_observation.region_world_description', wraps=region_world_description) as describe:
            self.assertTrue(session.rebind(replacement, camera_pool()))
            self.assertEqual(describe.call_count, len(session.regions))
            after = world_table(session)
            self.assertNotEqual(before, after)
            self.assertEqual(describe.call_count, len(session.regions))
        for region in session.regions:
            self.assert_source_corners_and_front(region, after[region.roi_id])

    def test_short_facts_retain_pixel_locations_with_existing_status(self):
        session = prepare_scene({'objects': [rectangle_mesh()]}, camera_pool())
        identity = session.regions[0].roi_id
        pixel_row = {'roi_id': identity, 'object_index': 0, 'view': 'SCENE', 'front_facing': True,
                     'visible_surface_pixels': 1, 'contrasting_boundary_pixels': 0, 'readable': False,
                     'visible_pixel_bounds': [5, 7, 5, 7], 'visible_pixel_anchor': [5, 7]}
        session.state.observed_views['SCENE'] = {'image_path': 'synthetic.png', 'image_ref': 'synthetic',
                                               'image_sha256': 'synthetic', 'readable_roi_ids': [],
                                               'pixel_rows': [copy.deepcopy(pixel_row)]}
        facts = session.short_facts()
        self.assertEqual(facts['observations'][0]['pixel_rows'], [pixel_row])
        self.assertEqual(facts['regions'][0]['status'], 'unknown')
        self.assertEqual(facts['regions'][0]['reason'], 'pixel_evidence_insufficient')


if __name__ == '__main__':
    unittest.main()

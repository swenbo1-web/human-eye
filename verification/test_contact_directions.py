"""Bounded contact views must clear full geometry, not just local surfaces."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin.attention_policy import AttentionPolicy, _contact_directions
from human_eye_plugin.attention_rendering import _attention_camera, _visible_witness
from verification.test_attention_policy import fixture
from verification.test_auto_router import box


def legacy_directions():
    raw = ((1., 0., .3), (-1., 0., .3), (0., -1., .3), (0., 1., .3),
           (1., 0., -.3), (-1., 0., -.3), (0., -1., -.3), (0., 1., -.3),
           (1., 0., 0.), (-1., 0., 0.), (0., -1., 0.), (0., 1., 0.),
           (0., 0., 1.), (0., 0., -1.))
    return [tuple(float(component) for component in np.array(value) / np.linalg.norm(value))
            for value in raw]


def cavity_fixture(case):
    path = (Path(__file__).parent / 'fixes' / '20261025_recovery_current_practice'
            / 'fixture_spec.json')
    value = json.loads(path.read_text(encoding='utf-8'))['cases'][case]
    meshes = [MeshEntity3D.from_dict(item) for item in value['scene']['meshes']]
    points = {
        'square_hole_1mm': ([.024, -.006, .0036], [.025, -.006, .0036]),
        'L_slot_1mm': ([-.024, .015, -.01], [-.025, .015, -.01]),
        'square_hole': ([-.006, -.006, -.0036], [-.025, -.006, -.0036]),
        'L_slot': ([.015, .015, -.01], [.015, -.025, -.01]),
    }
    pa, pb = points[case]
    contact = {'object_id': value['reference'], 'measurement_valid': True,
               'signed_clearance_m': value['oracle']['clearance_m'],
               'point_a_world': pa, 'point_b_world': pb}
    options = dict(focal_id=value['focal'], reference_id=value['reference'],
                   contacts=[contact], quad_size=384, include_image=True,
                   scene_fingerprint='contact-directions-' + case, now_s=100.)
    return meshes, options


def exact_visibility(meshes):
    def visible(plan):
        view = _attention_camera(meshes, plan)[0]
        return all(_visible_witness(point, meshes, view, plan['view_span_m'])
                   for point in plan['witness_points_world_m'])
    return visible


class ContactDirectionTests(unittest.TestCase):
    def test_small_contact_quotas_skip_contact_frame_work(self):
        legacy = legacy_directions()
        with patch('human_eye_plugin.attention_policy.np.linalg.norm',
                   side_effect=AssertionError('No spare direction budget')):
            for budget in (0, 1, 6, 12, 14):
                self.assertEqual(_contact_directions(object(), object(), legacy, budget),
                                 legacy[:budget])

    def test_legacy_prefix_is_exact_and_spare_quota_is_bounded(self):
        legacy = legacy_directions()
        for budget in (15, 17, 21, 24):
            values = _contact_directions(np.zeros(3), np.array([.001, 0., 0.]),
                                         legacy, budget)
            self.assertEqual(values[:14], legacy)
            self.assertEqual(len(values), min(budget, 22))
            self.assertEqual(len(set(values)), len(values))

    def test_new_views_are_unit_diagonals_with_shallow_segment_component(self):
        legacy = legacy_directions()
        for sign in (1., -1.):
            normal = np.array([sign, 0., 0.])
            values = _contact_directions(np.zeros(3), normal * .001, legacy, 24)
            for value in values[14:]:
                self.assertAlmostEqual(np.linalg.norm(value), 1., places=14)
                self.assertAlmostEqual(abs(np.dot(value, normal)),
                                       .3 / np.sqrt(1.09), places=14)
                self.assertNotEqual(value[1], 0.)
                self.assertNotEqual(value[2], 0.)

    def test_near_equivalent_existing_direction_is_not_appended_or_snapped(self):
        legacy = legacy_directions()
        known = np.array([.3, 1 / np.sqrt(2), 1 / np.sqrt(2)]) / np.sqrt(1.09)
        known[0] += 5e-13
        legacy[-1] = tuple(float(component) for component in known)
        values = _contact_directions(np.zeros(3), np.array([.001, 0., 0.]), legacy, 24)
        self.assertEqual(values[:14], legacy)
        self.assertEqual(len(values), 21)
        self.assertFalse(any(np.allclose(value, known, rtol=0, atol=1e-12)
                             for value in values[14:]))

    def test_z_views_keep_legacy_priority_and_real_new_diagonals(self):
        legacy = legacy_directions()
        for sign in (1., -1.):
            values = _contact_directions(np.zeros(3), np.array([0., 0., sign * .001]),
                                         legacy, 24)
            self.assertEqual(values[:14], legacy)
            self.assertEqual(len(values), 22)
            for value in values[14:]:
                self.assertTrue(all(abs(component) > 0 for component in value))
                self.assertFalse(any(np.allclose(value, old, rtol=0, atol=1e-12)
                                     for old in legacy))

    def test_oblique_frame_is_deterministic_and_keeps_witnesses_intact(self):
        legacy = legacy_directions()
        pa = np.array([.1, -.2, .3])
        pb = pa + np.array([.001, -.002, .003])
        before = (pa.copy(), pb.copy(), copy.deepcopy(legacy))
        first = _contact_directions(pa, pb, legacy, 24)
        second = _contact_directions(pa, pb, legacy, 24)
        self.assertEqual(first, second)
        self.assertLessEqual(len(first), 22)
        for index, value in enumerate(first):
            self.assertAlmostEqual(np.linalg.norm(value), 1., places=13)
            self.assertFalse(any(np.allclose(value, old, rtol=0, atol=1e-12)
                                 for old in first[:index]))
        np.testing.assert_array_equal(pa, before[0])
        np.testing.assert_array_equal(pb, before[1])
        self.assertEqual(legacy, before[2])

    def test_zero_segment_adds_no_directions(self):
        legacy = legacy_directions()
        self.assertEqual(_contact_directions(np.zeros(3), np.zeros(3), legacy, 24), legacy)

    def test_square_hole_axis_tangent_eventually_hits_opposite_wall(self):
        meshes, options = cavity_fixture('square_hole_1mm')
        contact = options['contacts'][0]
        points = np.array([contact['point_a_world'], contact['point_b_world']])
        direction = np.array([-.3, -1., 0.])
        direction /= np.linalg.norm(direction)
        plan = {'target_world_m': points.mean(axis=0).tolist(),
                'direction': direction.tolist(), 'up': [0., 0., 1.],
                'view_span_m': .001 * 383 / 12}
        view = _attention_camera(meshes, plan)[0]
        # Leaving B toward the opening is insufficient: this complete ray
        # reaches y=-.025 with x about .0193 and z=.0036, inside another wall.
        self.assertFalse(_visible_witness(points[1], meshes, view, plan['view_span_m']))

    def test_one_mm_cavities_get_full_scene_ray_visible_proposals(self):
        for case in ('square_hole_1mm', 'L_slot_1mm'):
            with self.subTest(case=case):
                meshes, options = cavity_fixture(case)
                before = [copy.deepcopy(mesh.to_dict()) for mesh in meshes]
                visible = exact_visibility(meshes)
                with patch('human_eye_plugin.attention_policy._contact_directions',
                           side_effect=lambda pa, pb, legacy, budget: legacy[:budget]):
                    old = AttentionPolicy().propose(meshes, candidate_visible=visible, **options)
                self.assertEqual(old['reason_codes'], ['no_visible_candidate_with_projected_gain'])
                result = AttentionPolicy().propose(meshes, candidate_visible=visible, **options)
                self.assertEqual(result['decision'], 'propose', result)
                self.assertEqual(result['candidate_count'], 22)
                self.assertTrue(visible(result['camera_plan']))
                self.assertAlmostEqual(result['candidate_projected_gap_px'],
                                       12 / np.sqrt(1.09), places=10)
                contact = options['contacts'][0]
                self.assertEqual(result['camera_plan']['witness_points_world_m'],
                                 [contact['point_a_world'], contact['point_b_world']])
                self.assertIsNone(result['state_to_commit'])
                self.assertFalse(result['visibility_verified'])
                self.assertFalse(result['model_quality_gain_proven'])
                self.assertTrue(result['execution_pair_unchanged'])
                self.assertEqual(before, [mesh.to_dict() for mesh in meshes])

    def test_enclosed_cavity_cannot_obtain_a_visible_proposal(self):
        meshes, options = cavity_fixture('square_hole_1mm')
        meshes.append(MeshEntity3D.from_dict(box('enclosure', [0, 0, 0], [1, 1, 1])))
        result = AttentionPolicy().propose(meshes, candidate_visible=exact_visibility(meshes), **options)
        self.assertEqual(result['reason_codes'], ['no_visible_candidate_with_projected_gain'])
        self.assertIsNone(result['state_to_commit'])
        self.assertLessEqual(result['candidate_count'], 24)

    def test_wide_cavities_keep_the_original_eligibility_gate(self):
        for case in ('square_hole', 'L_slot'):
            with self.subTest(case=case):
                meshes, options = cavity_fixture(case)
                with patch('human_eye_plugin.attention_policy._contact_directions') as directions:
                    result = AttentionPolicy().propose(meshes, **options)
                directions.assert_not_called()
                self.assertEqual(result['decision'], 'hold')
                self.assertEqual(result['eligible_contact_count'], 0)
                self.assertEqual(result['candidate_count'], 0)

    def test_multiple_contacts_keep_the_global_and_per_contact_quotas(self):
        for count in (2, 4):
            with self.subTest(count=count):
                meshes, contacts = fixture()
                for index in range(1, count):
                    item = meshes[0].to_dict()
                    item['object_id'] = 'base-' + str(index)
                    meshes.append(MeshEntity3D.from_dict(item))
                    contact = copy.deepcopy(contacts[0])
                    contact['object_id'] = item['object_id']
                    contacts.append(contact)
                with patch('human_eye_plugin.attention_policy._contact_directions',
                           wraps=_contact_directions) as directions:
                    result = AttentionPolicy().propose(meshes, focal_id='part', reference_id='base',
                        contacts=contacts, scene_fingerprint='many-contacts', now_s=100.,
                        candidate_visible=lambda plan: False)
                self.assertEqual(result['examined_contact_count'], count)
                self.assertEqual(result['candidate_count'], 24)
                self.assertEqual([call.args[3] for call in directions.call_args_list],
                                 [24 // count] * count)


if __name__ == '__main__':
    unittest.main()

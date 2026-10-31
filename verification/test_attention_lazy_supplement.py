"""Prune supplemental views only when conservative score bounds prove order.

Synthetic visibility callbacks exercise policy ordering; cavity cases use the
unchanged full-scene ray check. Product rendering still owns measured cost,
depth, ownership and readability confirmation.
"""
import copy
import json
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_module1_operators import MeshEntity3D, SpatialAnomalySniffer
from human_eye_plugin.attention_policy import (
    AttentionLimits, AttentionPolicy, _contact_directions, _plan_signature,
    _beats_supplement_bounds, _supplement_score_bounds, confirm_attention,
)
from verification.test_attention_policy import fixture
from verification.test_contact_directions import (
    cavity_fixture, exact_visibility, legacy_directions,
)


def options(contacts, **changes):
    value = dict(focal_id='part', reference_id='base', contacts=contacts,
                 quad_size=128, include_image=True, scene_fingerprint='lazy-pool', now_s=100.)
    value.update(changes)
    return value


class LazySupplementTests(unittest.TestCase):
    def legacy_only(self, pa, pb, legacy, budget):
        self.assertLessEqual(budget, 14, 'A bound-winning view must skip supplemental generation')
        return _contact_directions(pa, pb, legacy, budget)

    def test_usable_normal_and_thin_pools_do_not_build_supplement(self):
        for gap in (.002, .000025):
            with self.subTest(gap=gap):
                meshes, contacts = fixture(gap)
                probe = SpatialAnomalySniffer.probe_closest_clearance(meshes[1], meshes[0])
                contacts[0].update(point_a_world=probe.point_a_world.tolist(),
                                   point_b_world=probe.point_b_world.tolist())
                with patch('human_eye_plugin.attention_policy._contact_directions',
                           side_effect=self.legacy_only) as directions:
                    result = AttentionPolicy().propose(meshes, candidate_visible=exact_visibility(meshes),
                                                        **options(contacts))
                self.assertEqual(result['decision'], 'propose')
                self.assertEqual(result['candidate_count'], 14)
                self.assertEqual([call.args[3] for call in directions.call_args_list], [14])
                self.assertIsNone(result['state_to_commit'])
                self.assertFalse(result['visibility_verified'])

    def test_no_visibility_callback_keeps_legacy_proposal_priority(self):
        meshes, contacts = fixture()
        with patch('human_eye_plugin.attention_policy._contact_directions',
                   side_effect=self.legacy_only):
            result = AttentionPolicy().propose(meshes, **options(contacts))
        self.assertEqual(result['decision'], 'propose')
        self.assertEqual(result['candidate_count'], 14)
        self.assertEqual(result['visibility_precheck_count'], 0)

    def test_possible_better_supplement_keeps_original_global_score_order(self):
        meshes, contacts = fixture()
        # Policy-order fixture: a caller-supplied oblique segment is fully in
        # both bounds. This test makes no claim that its callback proves pixels.
        contacts[0].update(signed_clearance_m=.0025,
                           point_a_world=[0., 0., .202], point_b_world=[.0015, 0., .2])
        legacy = legacy_directions()
        preferred = legacy[0]
        checked = []
        def visible(plan):
            direction = tuple(plan['direction'])
            checked.append(direction)
            return direction == preferred or direction not in legacy
        with patch('human_eye_plugin.attention_policy._contact_directions',
                   wraps=_contact_directions) as directions:
            result = AttentionPolicy().propose(meshes, candidate_visible=visible, **options(contacts))
        self.assertNotIn(tuple(result['camera_plan']['direction']), legacy)
        self.assertAlmostEqual(result['candidate_projected_gap_px'], 12 / np.sqrt(1.09))
        self.assertNotIn(preferred, checked, 'Expand before paying for a losing successful precheck')
        self.assertEqual(result['candidate_count'], 22)
        self.assertEqual([call.args[3] for call in directions.call_args_list], [14, 24])

    def test_equal_bound_does_not_hide_possible_same_focus_priority(self):
        candidate = {'projected_net_gain_px_before_compute': 10., 'same_focus': False}
        self.assertFalse(_beats_supplement_bounds(candidate, (0, 0), [(10., (0, 14))], True))
        self.assertTrue(_beats_supplement_bounds(candidate, (0, 0), [(10., (0, 14))], None))
        candidate['same_focus'] = True
        self.assertTrue(_beats_supplement_bounds(candidate, (-1, -1), [(10., (0, 14))], True))

    def test_custom_target_uses_actual_witness_norm_within_clearance_tolerance(self):
        meshes, contacts = fixture(.8e-9)
        contacts[0].update(signed_clearance_m=1e-9, point_a_world=[0., 0., .2 + 1.52e-9],
                           point_b_world=[1.14e-9, 0., .2])
        legacy = legacy_directions()
        checked = []
        def visible(plan):
            direction = tuple(plan['direction'])
            checked.append(direction)
            return direction == legacy[0] or direction not in legacy
        policy = AttentionPolicy(AttentionLimits(target_gap_px=64.))
        result = policy.propose(meshes, candidate_visible=visible, **options(contacts))
        self.assertEqual(result['decision'], 'propose')
        self.assertNotIn(tuple(result['camera_plan']['direction']), legacy)
        self.assertNotIn(legacy[0], checked)
        strict_distance_bound = 127 / 4 / np.sqrt(1.09)
        self.assertGreater(result['candidate_projected_gap_px'], strict_distance_bound * 1.5)
        self.assertEqual(result['candidate_count'], 22)

    def test_extreme_nonzero_underflow_norm_uses_universal_capped_bound(self):
        pa, pb = np.zeros(3), np.array([2e-162, 1e-162, 0.])
        self.assertGreater(np.linalg.norm(pb - pa), 0.)
        considered = [(False, 1e-162, 'other', pa, pb, 0., True)]
        bounds = _supplement_score_bounds(considered, previous=None, quad_size=128,
            limits=AttentionLimits(target_gap_px=64.), legacy_count=14)
        self.assertEqual(bounds, [(63., (0, 14))])
        candidate = {'projected_net_gain_px_before_compute': 62., 'same_focus': False}
        self.assertFalse(_beats_supplement_bounds(candidate, (0, 0), bounds, None))

    def test_earlier_contact_supplement_wins_original_cross_contact_stable_tie(self):
        meshes, contacts = fixture()
        item = meshes[0].to_dict()
        item['object_id'] = 'base-copy'
        meshes.append(MeshEntity3D.from_dict(item))
        contacts.append({**contacts[0], 'object_id': 'base-copy'})
        legacy = legacy_directions()
        checked = []
        def visible(plan):
            identity = plan['target_object_ids'][1]
            direction = tuple(plan['direction'])
            checked.append((identity, direction))
            return ((identity == 'base' and direction not in legacy)
                    or (identity == 'base-copy' and direction == legacy[0]))
        result = AttentionPolicy(AttentionLimits(max_candidates=96)).propose(
            meshes, candidate_visible=visible, **options(contacts))
        self.assertEqual(result['camera_plan']['target_object_ids'], ['part', 'base'])
        self.assertNotIn(tuple(result['camera_plan']['direction']), legacy)
        self.assertNotIn(('base-copy', legacy[0]), checked)
        self.assertEqual(result['candidate_count'], 44)

    def test_global_resort_reuses_only_exact_failed_prechecks(self):
        meshes, contacts = fixture()
        item = meshes[0].to_dict()
        item['object_id'] = 'base-copy'
        meshes.append(MeshEntity3D.from_dict(item))
        contacts.append({**contacts[0], 'object_id': 'base-copy'})
        legacy = legacy_directions()
        checked = []
        def visible(plan):
            checked.append(json.dumps(plan, sort_keys=True, separators=(',', ':')))
            return plan['target_object_ids'][1] == 'base-copy' and tuple(plan['direction']) == legacy[0]
        result = AttentionPolicy(AttentionLimits(max_candidates=96)).propose(
            meshes, candidate_visible=visible, **options(contacts))
        self.assertEqual(result['camera_plan']['target_object_ids'], ['part', 'base-copy'])
        self.assertEqual(tuple(result['camera_plan']['direction']), legacy[0])
        self.assertEqual(len(checked), len(set(checked)))
        self.assertEqual(result['visibility_precheck_count'], len(checked))
        self.assertEqual(result['candidate_count'], 44)

    def test_real_one_mm_cavities_open_supplement_after_legacy_visibility_failure(self):
        legacy = legacy_directions()
        for case in ('square_hole_1mm', 'L_slot_1mm'):
            with self.subTest(case=case):
                meshes, request = cavity_fixture(case)
                events = []
                exact = exact_visibility(meshes)
                def generate(pa, pb, initial, budget):
                    events.append(('generate', budget))
                    return _contact_directions(pa, pb, initial, budget)
                def visible(plan):
                    events.append(('visible', tuple(plan['direction'])))
                    return exact(plan)
                with patch('human_eye_plugin.attention_policy._contact_directions', side_effect=generate):
                    result = AttentionPolicy().propose(meshes, candidate_visible=visible, **request)
                self.assertEqual(result['decision'], 'propose', result)
                self.assertEqual(result['candidate_count'], 22)
                self.assertTrue(exact(result['camera_plan']))
                self.assertNotIn(tuple(result['camera_plan']['direction']), legacy)
                supplement_index = events.index(('generate', 24))
                earlier_checks = [item[1] for item in events[:supplement_index] if item[0] == 'visible']
                self.assertTrue(earlier_checks)
                self.assertTrue(all(direction in legacy for direction in earlier_checks))
                checked = [item[1] for item in events if item[0] == 'visible']
                self.assertEqual(len(checked), len(set(checked)))
                self.assertEqual(result['visibility_precheck_count'], len(checked))
                self.assertIsNone(result['state_to_commit'])
                self.assertFalse(result['model_quality_gain_proven'])

    def test_all_occluded_pools_do_not_repeat_old_visibility_checks(self):
        meshes, request = cavity_fixture('square_hole_1mm')
        checked = []
        def invisible(plan):
            checked.append(tuple(plan['direction']))
            return False
        with patch('human_eye_plugin.attention_policy._contact_directions',
                   wraps=_contact_directions) as directions:
            result = AttentionPolicy().propose(meshes, candidate_visible=invisible, **request)
        self.assertEqual([call.args[3] for call in directions.call_args_list], [14, 24])
        self.assertEqual(result['candidate_count'], 22)
        self.assertEqual(result['reason_codes'], ['no_visible_candidate_with_projected_gain'])
        self.assertEqual(len(checked), len(set(checked)))
        self.assertEqual(result['visibility_precheck_count'], len(checked))
        self.assertIsNone(result['state_to_commit'])

    def test_precheck_exception_or_invalid_type_cannot_open_another_pool(self):
        meshes, contacts = fixture()
        def failed(plan):
            raise TimeoutError('Current evidence is unavailable')
        for callback in (failed, lambda plan: 1):
            with self.subTest(callback=callback):
                with patch('human_eye_plugin.attention_policy._contact_directions',
                           side_effect=self.legacy_only):
                    result = AttentionPolicy().propose(meshes, candidate_visible=callback,
                                                        **options(contacts))
                self.assertEqual(result['reason_codes'], ['attention_visibility_precheck_failed'])
                self.assertEqual(result['candidate_count'], 14)
                self.assertEqual(result['visibility_precheck_count'], 1)

    def test_retained_supplemental_camera_is_in_the_first_pool(self):
        meshes, request = cavity_fixture('square_hole_1mm')
        exact = exact_visibility(meshes)
        first = AttentionPolicy().propose(meshes, candidate_visible=exact, **request)
        state = confirm_attention(first, witness_visible=[True, True],
            actual_projected_gap_px=first['candidate_projected_gap_px'], additional_cost_ms=1.,
            scene_fingerprint=request['scene_fingerprint'], now_s=100.)['state_to_commit']
        self.assertIsNotNone(state)
        repeated = {**request, 'previous': state, 'now_s': 100.1}
        with patch('human_eye_plugin.attention_policy._contact_directions',
                   side_effect=self.legacy_only):
            result = AttentionPolicy().propose(meshes, candidate_visible=exact, **repeated)
        self.assertEqual(result['decision'], 'retain')
        self.assertEqual(result['candidate_count'], 15)
        self.assertEqual(result['camera_plan'], state['camera_plan'])
        retained = confirm_attention(result, witness_visible=[True, True],
            actual_projected_gap_px=result['candidate_projected_gap_px'], additional_cost_ms=1.,
            scene_fingerprint=request['scene_fingerprint'], now_s=100.1)
        self.assertEqual(retained['decision'], 'retained')
        self.assertEqual(retained['state_to_commit']['last_shift_s'], 100.)

    def test_identical_plan_keeps_both_projection_scores_for_global_order(self):
        meshes, contacts = fixture()
        first = AttentionPolicy().propose(meshes, **options(contacts))
        state = confirm_attention(first, witness_visible=[True, True],
            actual_projected_gap_px=first['candidate_projected_gap_px'], additional_cost_ms=1.,
            scene_fingerprint='lazy-pool', now_s=100.)['state_to_commit']
        # Controlled floating-evaluation difference: a retained 2D projection
        # lies several round10 buckets below the generated perpendicular norm.
        # Camera equality cannot erase the higher-scoring generated record.
        retained_px = first['candidate_projected_gap_px'] - 3e-10
        checked = []
        with patch('human_eye_plugin.attention_policy._orthographic_plan_gap',
                   return_value=(retained_px, True)):
            result = AttentionPolicy().propose(meshes,
                candidate_visible=lambda plan: checked.append(plan) or True,
                **options(contacts, previous=state, now_s=100.1))
        self.assertEqual(result['camera_plan'], state['camera_plan'])
        self.assertEqual(result['candidate_projected_gap_px'], first['candidate_projected_gap_px'])
        self.assertGreater(result['candidate_projected_gap_px'], result['previous_projected_gap_px'])
        self.assertEqual(result['candidate_count'], 15)
        self.assertEqual(len(checked), 1)

    def test_dwell_does_not_admit_a_new_focus_through_supplement(self):
        meshes, contacts = fixture()
        first = AttentionPolicy().propose(meshes, **options(contacts))
        state = confirm_attention(first, witness_visible=[True, True],
            actual_projected_gap_px=first['candidate_projected_gap_px'], additional_cost_ms=1.,
            scene_fingerprint='lazy-pool', now_s=100.)['state_to_commit']
        state['camera_plan']['target_world_m'][1] += 10.
        state['plan_signature'] = _plan_signature(state['camera_plan'])
        checked = []
        result = AttentionPolicy().propose(meshes,
            candidate_visible=lambda plan: checked.append(plan) or True,
            **options(contacts, previous=state, now_s=100.1))
        self.assertEqual(result['reason_codes'], ['attention_dwell_active'])
        self.assertEqual(checked, [])
        self.assertIsNone(result['state_to_commit'])

    def test_failed_retained_plan_is_checked_once_but_current_reframe_is_rechecked(self):
        meshes, request = cavity_fixture('square_hole_1mm')
        first = AttentionPolicy().propose(meshes, candidate_visible=exact_visibility(meshes), **request)
        state = confirm_attention(first, witness_visible=[True, True],
            actual_projected_gap_px=first['candidate_projected_gap_px'], additional_cost_ms=1.,
            scene_fingerprint=request['scene_fingerprint'], now_s=100.)['state_to_commit']
        for witness_shift, expected_checks in ((0., 1), (.001, 2)):
            with self.subTest(witness_shift=witness_shift):
                current = copy.deepcopy(request)
                for field in ('point_a_world', 'point_b_world'):
                    current['contacts'][0][field][1] += witness_shift
                checked = []
                def invisible(plan):
                    checked.append(json.dumps(plan, sort_keys=True, separators=(',', ':')))
                    return False
                result = AttentionPolicy().propose(meshes, candidate_visible=invisible,
                    **dict(current, previous=state, now_s=100.1))
                self.assertEqual(result['reason_codes'], ['no_visible_candidate_with_projected_gain'])
                self.assertEqual(result['candidate_count'], 23)
                self.assertEqual(result['visibility_precheck_count'], expected_checks)
                self.assertEqual(len(checked), len(set(checked)))
                self.assertEqual(len(checked), expected_checks)
                self.assertIsNone(result['state_to_commit'])

    def test_both_pools_share_the_original_candidate_cap(self):
        meshes, request = cavity_fixture('square_hole_1mm')
        for cap, expected in ((2, 2), (14, 14), (15, 15), (24, 22)):
            with self.subTest(cap=cap):
                policy = AttentionPolicy(AttentionLimits(max_candidates=cap))
                result = policy.propose(meshes, candidate_visible=lambda plan: False, **request)
                self.assertEqual(result['candidate_count'], expected)
                self.assertLessEqual(result['candidate_count'], cap)
                self.assertEqual(result['candidate_budget_exhausted'], expected == cap)

    def test_supplement_does_not_rewrite_meshes_contacts_or_callback_plans(self):
        meshes, request = cavity_fixture('L_slot_1mm')
        before = ([copy.deepcopy(mesh.to_dict()) for mesh in meshes], copy.deepcopy(request))
        legacy = legacy_directions()
        def callback(plan):
            old = tuple(plan['direction']) in legacy
            plan['direction'][0] = 42.
            plan['witness_points_world_m'][0][0] = 42.
            return not old
        result = AttentionPolicy().propose(meshes, candidate_visible=callback, **request)
        self.assertEqual(result['decision'], 'propose')
        self.assertAlmostEqual(np.linalg.norm(result['camera_plan']['direction']), 1.)
        self.assertEqual(result['camera_plan']['witness_points_world_m'],
                         [request['contacts'][0]['point_a_world'], request['contacts'][0]['point_b_world']])
        self.assertEqual(before, ([mesh.to_dict() for mesh in meshes], request))

    def test_supplemented_proposal_still_cannot_bypass_measured_cost_limit(self):
        meshes, request = cavity_fixture('square_hole_1mm')
        proposal = AttentionPolicy().propose(meshes, candidate_visible=exact_visibility(meshes), **request)
        result = confirm_attention(proposal, witness_visible=[True, True],
            actual_projected_gap_px=proposal['candidate_projected_gap_px'], additional_cost_ms=41.,
            scene_fingerprint=request['scene_fingerprint'], now_s=100., readability={'passed': True})
        self.assertEqual(result['reason_codes'], ['attention_additional_compute_budget_exceeded'])
        self.assertIsNone(result['state_to_commit'])


if __name__ == '__main__':
    unittest.main()

"""Attention must buy visible, measured sampling gain and retain no authority."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin.attention_policy import AttentionLimits, AttentionPolicy, confirm_attention
from human_eye_plugin.scene_rendering import _camera, _look_at, _projection
from verification.test_auto_router import box


def fixture(gap=.002, offset=(0, 0, 0), scale=1):
    origin = np.array(offset)
    values = [box('base', origin + np.array([0, 0, .1]) * scale, np.array([1.4, 1.2, .2]) * scale),
              box('part', origin + np.array([0, 0, .25 + gap]) * scale, np.array([.3, .2, .1]) * scale, True)]
    contacts = [{'object_id': 'base', 'measurement_valid': True, 'signed_clearance_m': gap * scale,
                 'point_a_world': (origin + np.array([0, 0, .2 + gap]) * scale).tolist(),
                 'point_b_world': (origin + np.array([0, 0, .2]) * scale).tolist()}]
    return [MeshEntity3D.from_dict(value) for value in values], contacts


def propose(gap=.002, *, policy=None, **changes):
    meshes, contacts = fixture(gap)
    options = dict(focal_id='part', reference_id='base', contacts=contacts,
                   quad_size=128, include_image=True, scene_fingerprint='scene-a', now_s=10)
    options.update(changes)
    return (policy or AttentionPolicy()).propose(meshes, **options)


def confirm(proposal, **changes):
    options = dict(witness_visible=[True, True],
                   actual_projected_gap_px=proposal['candidate_projected_gap_px'],
                   additional_cost_ms=1, scene_fingerprint=proposal['scene_fingerprint'], now_s=10)
    options.update(changes)
    return confirm_attention(proposal, **options)


class AttentionPolicyTests(unittest.TestCase):
    def test_small_gap_has_positive_projected_gain_and_requires_confirmation(self):
        result = propose()
        self.assertEqual(result['decision'], 'propose', result)
        self.assertGreater(result['capped_gain_px'], 4)
        self.assertIsNone(result['state_to_commit'])
        self.assertFalse(result['visibility_verified'])
        self.assertFalse(result['model_quality_gain_proven'])
        self.assertTrue(result['execution_pair_unchanged'])

    def test_large_resolved_gap_does_not_spend_attention(self):
        result = propose(.5)
        self.assertEqual(result['decision'], 'hold')
        self.assertIsNone(result['camera_plan'])

    def test_baseline_is_actual_existing_q4_projection(self):
        meshes, contacts = fixture()
        result = propose()
        view, projection, _ = _camera('Q4 TARGET', meshes, [meshes[1], meshes[0]],
                                     128, 'perspective', [2.4, -3.2, 2.4])
        points = np.c_[np.array([contacts[0]['point_a_world'], contacts[0]['point_b_world']]), np.ones(2)]
        clip = (projection @ view @ points.T).T
        ndc = clip[:, :3] / clip[:, 3:]
        independently_projected = np.linalg.norm(ndc[1, :2] - ndc[0, :2]) * 127 / 2
        self.assertAlmostEqual(result['baseline_projected_gap_px'], independently_projected, places=10)

    def test_planned_orthographic_gain_matches_camera_matrices(self):
        result = propose()
        plan = result['camera_plan']
        center = np.array(plan['target_world_m'])
        view = _look_at(center + np.array(plan['direction']) * 2, center, np.array(plan['up']))
        projection = _projection('orthographic', plan['view_span_m'] / 2, .08, 10)
        points = np.c_[np.array(plan['witness_points_world_m']), np.ones(2)]
        clip = (projection @ view @ points.T).T
        measured = np.linalg.norm(clip[1, :2] - clip[0, :2]) * (plan['quad_size'] - 1) / 2
        self.assertAlmostEqual(result['candidate_projected_gap_px'], measured, places=8)

    def test_visibility_failure_discards_proposal_and_cannot_commit(self):
        result = confirm(propose(), witness_visible=[True, False])
        self.assertFalse(result['applied'])
        self.assertIsNone(result['state_to_commit'])
        self.assertIn('contact_witness_occluded_or_outside_render', result['reason_codes'])

    def test_compute_cost_can_outweigh_projected_benefit(self):
        policy = AttentionPolicy(AttentionLimits(cost_px_per_ms=5))
        proposal = propose(policy=policy)
        result = confirm(proposal, additional_cost_ms=3)
        self.assertFalse(result['applied'])
        self.assertLess(result['net_gain_px'], 0)
        self.assertIn('attention_measured_gain_does_not_cover_cost', result['reason_codes'])

    def test_hard_cost_budget_applies_even_when_gain_would_pay(self):
        result = confirm(propose(), additional_cost_ms=41)
        self.assertFalse(result['applied'])
        self.assertIn('attention_additional_compute_budget_exceeded', result['reason_codes'])

    def test_success_is_observational_and_requires_current_scene(self):
        proposal = propose()
        result = confirm(proposal)
        self.assertTrue(result['applied'])
        self.assertTrue(result['shifted'])
        self.assertIn('no_execution_authority', result['state_to_commit']['scope'])
        self.assertFalse(result['model_quality_gain_proven'])
        result = confirm(proposal, scene_fingerprint='scene-b')
        self.assertIsNone(result['state_to_commit'])

    def test_unchanged_focus_retains_without_resetting_dwell_clock(self):
        first = confirm(propose())['state_to_commit']
        second = propose(previous=first, now_s=10.1)
        self.assertEqual(second['decision'], 'retain')
        confirmation = confirm(second, now_s=10.1)
        self.assertEqual(confirmation['decision'], 'retained')
        self.assertEqual(confirmation['state_to_commit']['last_shift_s'], 10)
        self.assertFalse(confirmation['shifted'])

    def test_small_scene_changes_recompute_world_roi_before_retaining(self):
        first = confirm(propose())['state_to_commit']
        meshes, contacts = fixture(offset=(.001, -.001, .001))
        second = AttentionPolicy().propose(meshes, focal_id='part', reference_id='base', contacts=contacts,
                                          scene_fingerprint='scene-b', previous=first, now_s=10.1)
        self.assertEqual(second['decision'], 'retain')
        self.assertNotEqual(first['camera_plan']['witness_points_world_m'], second['camera_plan']['witness_points_world_m'])
        np.testing.assert_allclose(second['camera_plan']['witness_points_world_m'][0], [.001, -.001, .203])
        self.assertEqual(confirm(second, now_s=10.1)['state_to_commit']['scene_fingerprint'], 'scene-b')

    def test_large_translation_or_zoom_requires_new_shift_and_dwell(self):
        first = confirm(propose())['state_to_commit']
        for gap, offset in ((.002, (12, -7, 3)), (.00002, (0, 0, 0))):
            meshes, contacts = fixture(gap, offset=offset)
            options = dict(focal_id='part', reference_id='base', contacts=contacts,
                           scene_fingerprint='scene-b', previous=first)
            early = AttentionPolicy().propose(meshes, now_s=10.1, **options)
            self.assertEqual(early['reason_codes'], ['attention_dwell_active'])
            late = AttentionPolicy().propose(meshes, now_s=11.1, **options)
            self.assertEqual(late['decision'], 'propose')
            self.assertEqual(late['switch_cost_px'], 1)

    def test_future_clock_cannot_retain_same_focus(self):
        first = confirm(propose())['state_to_commit']
        result = propose(previous=first, now_s=9)
        self.assertEqual(result['reason_codes'], ['attention_clock_reversed'])

    def test_invisible_best_candidate_falls_back_to_visible_direction(self):
        checked = []
        def visibility(plan):
            checked.append(plan['direction'])
            return plan['direction'] == [-1., 0., 0.]
        result = propose(candidate_visible=visibility)
        self.assertEqual(result['camera_plan']['direction'], [-1., 0., 0.])
        self.assertEqual(result['visibility_precheck_count'], 2)
        self.assertFalse(result['visibility_verified'])
        self.assertIsNone(result['state_to_commit'])

    def test_all_occluded_or_visibility_budget_failure_holds(self):
        result = propose(candidate_visible=lambda plan: False)
        self.assertEqual(result['reason_codes'], ['no_visible_candidate_with_projected_gain'])
        def budget_failure(plan):
            raise TimeoutError('Visibility budget exceeded')
        result = propose(candidate_visible=budget_failure)
        self.assertEqual(result['reason_codes'], ['attention_visibility_precheck_failed'])
        self.assertEqual(result['visibility_precheck_count'], 1)

    def test_corrupted_previous_camera_does_not_suppress_switch_cost(self):
        first = confirm(propose())['state_to_commit']
        first['camera_plan']['view_span_m'] = 1000
        result = propose(previous=first, now_s=11)
        self.assertEqual(result['decision'], 'propose')
        self.assertEqual(result['switch_cost_px'], 1)

    def test_recent_different_focus_holds_and_clock_reversal_holds(self):
        previous = confirm(propose())['state_to_commit']
        previous['camera_plan']['target_world_m'][1] += 10
        previous['plan_signature'] = hashlib.sha256(json.dumps(previous['camera_plan'], sort_keys=True,
            separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        result = propose(previous=previous, now_s=10.1)
        self.assertEqual(result['reason_codes'], ['attention_dwell_active'])
        result = propose(previous=previous, now_s=9)
        self.assertEqual(result['reason_codes'], ['attention_clock_reversed'])
        self.assertEqual(propose(previous=previous, now_s=11.1)['decision'], 'propose')

    def test_current_camera_already_resolves_gap_so_no_redundant_zoom_shift(self):
        first = confirm(propose())['state_to_commit']
        result = propose(.004, previous=first, now_s=15)
        self.assertEqual(result['decision'], 'retain')
        self.assertEqual(result['camera_plan']['view_span_m'], first['camera_plan']['view_span_m'])
        self.assertGreater(result['candidate_projected_gap_px'], 12)

    def test_real_shift_compares_default_and_current_camera_on_new_geometry(self):
        first = confirm(propose())['state_to_commit']
        result = propose(.00002, previous=first, now_s=15)
        self.assertEqual(result['decision'], 'propose')
        self.assertGreater(result['previous_projected_gap_px'], result['baseline_default_projected_gap_px'])
        self.assertEqual(result['baseline_projected_gap_px'], result['previous_projected_gap_px'])
        self.assertIn('max_default_and_previous', result['baseline_scope'])

    def test_oblique_unit_direction_can_expose_real_corner_contact(self):
        from human_eye_module1_operators import SpatialAnomalySniffer
        from human_eye_plugin.attention_rendering import _attention_camera, _visible_witness
        meshes, contacts = fixture()
        probe = SpatialAnomalySniffer.probe_closest_clearance(meshes[1], meshes[0])
        contacts[0].update(point_a_world=probe.point_a_world.tolist(), point_b_world=probe.point_b_world.tolist())
        def visible(plan):
            view, _, _, _ = _attention_camera(meshes, plan)
            return all(_visible_witness(point, meshes, view, plan['view_span_m'])
                       for point in plan['witness_points_world_m'])
        result = AttentionPolicy().propose(meshes, focal_id='part', reference_id='base', contacts=contacts,
                                          scene_fingerprint='s', now_s=1, candidate_visible=visible)
        self.assertEqual(result['decision'], 'propose', result)
        self.assertAlmostEqual(np.linalg.norm(result['camera_plan']['direction']), 1)
        self.assertTrue(0 < abs(result['camera_plan']['direction'][2]) < 1)
        self.assertGreater(result['candidate_projected_gap_px'], 10)

    def test_text_only_does_no_camera_or_geometry_work_and_no_state_update(self):
        with patch('human_eye_plugin.attention_policy.work_budget_status', side_effect=AssertionError('No probe')):
            with patch('human_eye_plugin.scene_rendering._camera', side_effect=AssertionError('No render')):
                result = propose(include_image=False)
        self.assertEqual(result['reason_codes'], ['text_only_no_visual_shift'])
        self.assertIsNone(result['state_to_commit'])

    def test_zero_negative_unknown_and_mismatched_witnesses_never_invent_focus(self):
        _, contacts = fixture()
        cases = [dict(signed_clearance_m=0), dict(signed_clearance_m=-.002),
                 dict(measurement_valid=False), dict(signed_clearance_m=.001),
                 dict(point_a_world=[100, 0, .202]), dict(point_a_world=None)]
        for changes in cases:
            bad = copy.deepcopy(contacts)
            bad[0].update(changes)
            with self.subTest(changes=changes):
                result = propose(contacts=bad)
                self.assertEqual(result['decision'], 'hold')
                self.assertEqual(result['eligible_contact_count'], 0)

    def test_limits_bound_candidate_work_and_no_new_clearance_probes(self):
        policy = AttentionPolicy(AttentionLimits(max_candidates=2))
        with patch('human_eye_plugin.geometry_safety.measure_pair_geometry', side_effect=AssertionError('No repeated geometry')):
            result = propose(policy=policy)
        self.assertEqual(result['candidate_count'], 2)
        self.assertTrue(result['candidate_budget_exhausted'])

    def test_candidate_determinism_and_input_immutability(self):
        meshes, contacts = fixture()
        before = [mesh.to_dict() for mesh in meshes], copy.deepcopy(contacts)
        options = dict(focal_id='part', reference_id='base', contacts=contacts,
                       scene_fingerprint='s', now_s=100)
        first, second = AttentionPolicy().propose(meshes, **options), AttentionPolicy().propose(meshes, **options)
        self.assertEqual(first, second)
        self.assertEqual(before, ([mesh.to_dict() for mesh in meshes], contacts))
        self.assertEqual(json.loads(json.dumps(first, allow_nan=False)), first)

    def test_gain_is_consistent_across_units_scale_and_world_translation(self):
        baseline = propose()
        for offset, scale in (((100000, -50000, 10000), 1), ((0, 0, 0), .001), ((10, 20, 30), 10000)):
            meshes, contacts = fixture(offset=offset, scale=scale)
            result = AttentionPolicy().propose(meshes, focal_id='part', reference_id='base', contacts=contacts,
                                              scene_fingerprint='s', now_s=100)
            self.assertEqual(result['decision'], 'propose')
            self.assertAlmostEqual(result['candidate_projected_gap_px'], baseline['candidate_projected_gap_px'], places=5)
            # The existing perspective camera uses its near-depth floor on
            # millimetre scenes, so its relative gap is allowed to differ.
            self.assertGreater(result['capped_gain_px'], 4)

    def test_tampered_camera_and_disagreeing_projection_cannot_commit(self):
        proposal = propose()
        proposal['camera_plan']['view_span_m'] *= 2
        self.assertFalse(confirm(proposal)['applied'])
        self.assertFalse(confirm(propose(), actual_projected_gap_px=8)['applied'])

    def test_bad_options_and_unmeasured_cost_are_rejected(self):
        for options in ({'quad_size': True}, {'quad_size': 32}, {'scene_fingerprint': ''},
                        {'now_s': float('nan')}, {'focal_id': 'missing'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                propose(**options)
        for changes in ({'additional_cost_ms': None}, {'additional_cost_ms': float('nan')},
                        {'actual_projected_gap_px': -1}, {'witness_visible': [1, 1]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                confirm(propose(), **changes)
        for options in ({'min_gain_px': 0}, {'max_candidates': True}, {'cost_px_per_ms': -1},
                        {'min_gain_ratio': .5}, {'max_additional_cost_ms': 0}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                AttentionLimits(**options)


if __name__ == '__main__':
    unittest.main()

"""Independent controlled-cost checks; no performance claims from these clocks."""
from contextlib import ExitStack
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin import attention_rendering as ar
from human_eye_plugin import scene_rendering as sr
from verification.test_attention_precheck_reuse import prepared_fixture


class EarlyAttentionRejectionTests(unittest.TestCase):
    def run_candidate(self, *, at_raster_ms=0., after_overlay_ms=None,
                      near_gain=False, zero_cost=False, retain=False,
                      raster_kind='ordinary', visible=True):
        value = prepared_fixture()
        image, metadata, meshes, options, token = value
        # Build an ordinary, valid geometric proposal before controlling cost.
        def candidate_visible(plan):
            camera = ar._attention_camera(meshes, plan)
            return all(ar._visible_witness(point, meshes, camera[0], plan['view_span_m'])
                       for point in plan['witness_points_world_m'])
        proposal = ar.AttentionPolicy().propose(meshes, **options,
            quad_size=128, include_image=True, candidate_visible=candidate_visible)
        self.assertIn(proposal['decision'], ('propose', 'retain'))
        if near_gain:
            # A real projected gain that passes geometric minima but fails net
            # gain once 20ms have actually been charged; no future cost guess.
            proposal['baseline_projected_gap_px'] = proposal['candidate_projected_gap_px'] - 4.2
        if zero_cost:
            proposal['policy']['cost_px_per_ms'] = 0.
        if retain:
            proposal.update(decision='retain', previous_last_shift_s=98., switch_cost_px=0.)
        before_pixels = np.array(image)
        before_metadata = copy.deepcopy(metadata)
        clock = [0.]
        raster_original, overlay_original = ar.rasterize_attention, ar._contact_overlay
        def raster(*args, **kwargs):
            color, depth, owners = raster_original(*args, **kwargs)
            clock[0] = at_raster_ms / 1000.
            if raster_kind == 'two_arrays':
                return color, depth
            if raster_kind == 'same_color':
                color[:] = 0
            return color, depth, owners
        def overlay(*args, **kwargs):
            result = overlay_original(*args, **kwargs)
            if after_overlay_ms is not None:
                clock[0] = after_overlay_ms / 1000.
            return result
        with ExitStack() as stack:
            stack.enter_context(patch.object(ar, 'time', SimpleNamespace(perf_counter=lambda: clock[0])))
            stack.enter_context(patch.object(ar.AttentionPolicy, 'propose', return_value=proposal))
            raster_mock = stack.enter_context(patch.object(ar, 'rasterize_attention', side_effect=raster))
            annotation = stack.enter_context(patch.object(ar, '_annotate', wraps=ar._annotate))
            overlay_mock = stack.enter_context(patch.object(ar, '_contact_overlay', side_effect=overlay))
            confirm = stack.enter_context(patch.object(ar, 'confirm_attention', wraps=ar.confirm_attention))
            if not visible:
                stack.enter_context(patch.object(ar, '_visible_witness', return_value=False))
            output, visual, state = ar.apply_attention_to_canvas(image, metadata, meshes,
                **options, prepared_render=token)
        np.testing.assert_array_equal(np.asarray(image), before_pixels)
        self.assertEqual(metadata, before_metadata)
        self.assertFalse(visual['attention'].get('execution_authority', False))
        return SimpleNamespace(value=value, output=output, visual=visual, state=state,
                               raster=raster_mock, annotation=annotation,
                               overlay=overlay_mock, confirm=confirm)

    def assert_hold(self, result, reason, *, annotations=0):
        self.assertIs(result.output, result.value[0])
        self.assertIsNone(result.state)
        self.assertIsNone(result.visual['attention']['state_to_commit'])
        self.assertEqual(result.visual['attention']['reason_codes'], [reason])
        self.assertEqual(result.annotation.call_count, annotations)
        self.assertEqual(result.overlay.call_count, annotations)

    def test_measured_gain_rejection_skips_drawing_and_keeps_measured_receipt(self):
        result = self.run_candidate(at_raster_ms=20., near_gain=True)
        self.assert_hold(result, 'attention_measured_gain_does_not_cover_cost')
        self.assertTrue(result.visual['attention']['readability_verified'])
        self.assertTrue(result.visual['attention']['visibility_verified'])
        self.assertTrue(result.visual['attention']['aborted_before_annotations'])
        self.assertEqual(result.visual['attention']['additional_cost_ms'], 20.)
        self.assertEqual(result.confirm.call_count, 1)

    def test_gain_hold_preserves_deferred_target_fallback(self):
        result = self.run_candidate(at_raster_ms=20., near_gain=True)
        self.assert_hold(result, 'attention_measured_gain_does_not_cover_cost')
        self.assertFalse(result.visual['raster_schedule']['canvas_complete'])
        finished, metadata = sr._finalize_prepared_scene_q4(result.output, result.visual,
            result.value[4], scene_fingerprint=result.value[3]['scene_fingerprint'])
        self.assertTrue(metadata['raster_schedule']['canvas_complete'])
        self.assertEqual(metadata['raster_schedule']['final_q4'], 'target')
        np.testing.assert_array_equal(np.asarray(finished)[:128], np.asarray(result.value[0])[:128])
        np.testing.assert_array_equal(np.asarray(finished)[128:, :128], np.asarray(result.value[0])[128:, :128])

    def test_surface_readability_rejection_never_draws_labels_as_evidence(self):
        result = self.run_candidate(raster_kind='same_color')
        self.assert_hold(result, 'candidate_surface_readability_insufficient')
        self.assertTrue(result.visual['attention']['visibility_verified'])
        self.assertFalse(result.visual['attention']['readability_verified'])
        self.assertEqual(result.visual['attention']['readability']['contrasting_boundary_pixels'], [0, 0])

    def test_two_array_compatibility_cannot_invent_owner_readability(self):
        result = self.run_candidate(raster_kind='two_arrays')
        self.assert_hold(result, 'candidate_surface_readability_insufficient')
        self.assertEqual(result.visual['attention']['readability']['visible_surface_pixels'], [0, 0])
        self.assertEqual(result.raster.call_count, 1)

    def test_occlusion_never_allocates_a_candidate_raster_or_commits(self):
        result = self.run_candidate(visible=False)
        self.assert_hold(result, 'contact_witness_occluded_or_outside_render')
        result.raster.assert_not_called()
        self.assertEqual(result.visual['attention']['raster_witness_supported'], [False, False])

    def test_provisional_success_still_rechecks_final_gain(self):
        result = self.run_candidate(at_raster_ms=0., after_overlay_ms=20., near_gain=True)
        self.assert_hold(result, 'attention_measured_gain_does_not_cover_cost', annotations=1)
        self.assertEqual(result.confirm.call_count, 2)
        self.assertEqual([c.kwargs['additional_cost_ms'] for c in result.confirm.call_args_list], [0., 20.])

    def test_provisional_success_cannot_commit_after_final_budget_overrun(self):
        result = self.run_candidate(at_raster_ms=0., after_overlay_ms=40.000001)
        self.assert_hold(result, 'attention_additional_compute_budget_exceeded', annotations=1)
        self.assertEqual(result.confirm.call_count, 2)
        self.assertGreater(result.visual['attention']['additional_cost_ms'], 40.)

    def test_exact40_with_zero_cost_still_requires_and_passes_final_confirmation(self):
        result = self.run_candidate(at_raster_ms=40., zero_cost=True, near_gain=True)
        self.assertIsNotNone(result.state)
        self.assertEqual(result.confirm.call_count, 2)
        self.assertEqual(result.annotation.call_count, 1)
        self.assertEqual(result.visual['attention']['additional_cost_ms'], 40.)
        self.assertEqual(result.visual['attention']['compute_cost_equivalent_px'], 0.)

    def test_zero_cost_does_not_disable_the_hard_budget(self):
        result = self.run_candidate(at_raster_ms=40.000001, zero_cost=True)
        self.assert_hold(result, 'attention_additional_compute_budget_exceeded')

    def test_retained_success_keeps_original_shift_timestamp(self):
        result = self.run_candidate(at_raster_ms=5., retain=True)
        self.assertIsNotNone(result.state)
        self.assertEqual(result.visual['attention']['decision'], 'retained')
        self.assertFalse(result.visual['attention']['shifted'])
        self.assertEqual(result.state['last_shift_s'], 98.)
        self.assertEqual(result.state['confirmed_at_s'], 100.)
        self.assertEqual(result.confirm.call_count, 2)

    def test_readability_reason_precedes_overbudget_reason(self):
        result = self.run_candidate(at_raster_ms=45., raster_kind='same_color')
        self.assert_hold(result, 'candidate_surface_readability_insufficient')
        self.assertEqual(result.visual['attention']['additional_cost_ms'], 45.)

    def test_retained_proposal_also_needs_final_cost_confirmation(self):
        result = self.run_candidate(at_raster_ms=0., after_overlay_ms=41., retain=True)
        self.assert_hold(result, 'attention_additional_compute_budget_exceeded', annotations=1)
        self.assertEqual(result.confirm.call_count, 2)


if __name__ == '__main__':
    unittest.main()

"""CONTACT adoption may save Q4 work, never its required fallback image."""
import base64
import copy
import io
import json
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from human_eye_plugin.attention_raster import rasterize_attention
from human_eye_plugin.attention_rendering import apply_attention_to_canvas
from human_eye_plugin.auto_router import HumanEyeAutoRouter
from human_eye_plugin.scene_rendering import (
    _raster_with_owners, finalize_scene_q4, render_scene_canvas,
)
from human_eye_plugin.telemetry import RequestTrace
from verification.test_attention_rendering import fixture, near_scene
from verification.test_auto_router import observation


def deferred(meshes):
    return render_scene_canvas(meshes, 128, focal_id='part', reference_id='base', defer_q4=True)


def finished_attention(meshes, options):
    image, meta = deferred(meshes)
    image, meta, state = apply_attention_to_canvas(image, meta, meshes, **options)
    image, meta = finalize_scene_q4(image, meta, meshes)
    return image, meta, state


class DeferredQ4Tests(unittest.TestCase):
    def test_deferred_fallback_matches_full_default_and_is_idempotent(self):
        expected, expected_meta, meshes, _ = fixture()
        before = [copy.deepcopy(mesh.to_dict()) for mesh in meshes]
        with patch('human_eye_plugin.scene_rendering._raster_with_owners', wraps=_raster_with_owners) as raster:
            image, meta = deferred(meshes)
            self.assertEqual(raster.call_count, 3)
            self.assertFalse(meta['raster_schedule']['canvas_complete'])
            self.assertNotIn('geometry_depth_pixels', meta['views'][3])
            output, visual = finalize_scene_q4(image, meta, meshes)
            self.assertEqual(raster.call_count, 4)
            again, same = finalize_scene_q4(output, visual, meshes)
            self.assertEqual(raster.call_count, 4)
        self.assertIs(again, output)
        self.assertIs(same, visual)
        np.testing.assert_array_equal(np.asarray(expected), np.asarray(output))
        without_schedule = {key: value for key, value in visual.items() if key != 'raster_schedule'}
        self.assertEqual(expected_meta, without_schedule)
        self.assertFalse(meta['raster_schedule']['canvas_complete'])
        self.assertEqual(before, [mesh.to_dict() for mesh in meshes])
        self.assertNotIn('raster_schedule', expected_meta)

    def test_confirmed_contact_skips_only_default_q4_with_identical_final_pixels(self):
        image, meta, meshes, options = fixture()
        with patch('human_eye_plugin.attention_rendering.time.perf_counter', return_value=0.):
            expected, old_visual, old_state = apply_attention_to_canvas(image, meta, meshes, **options)
            with patch('human_eye_plugin.scene_rendering._raster_with_owners', wraps=_raster_with_owners) as default_raster, \
                 patch('human_eye_plugin.attention_rendering.rasterize_attention', wraps=rasterize_attention) as contact_raster:
                output, visual, state = finished_attention(meshes, options)
        self.assertIsNotNone(state)
        self.assertEqual(old_state, state)
        self.assertEqual(default_raster.call_count, 3)
        self.assertEqual(contact_raster.call_count, 1)
        self.assertEqual(visual['raster_schedule']['default_q4'], 'skipped_after_confirmed_contact')
        self.assertTrue(visual['raster_schedule']['canvas_complete'])
        self.assertEqual(old_visual['views'], visual['views'])
        np.testing.assert_array_equal(np.asarray(expected), np.asarray(output))
        self.assertTrue(visual['views'][3]['readability']['passed'])
        self.assertFalse(visual['views'][3]['readability']['visible_gap_certified'])

    def test_no_proposal_has_one_complete_default_q4_and_no_candidate_raster(self):
        expected, _, meshes, options = fixture()
        options['contacts'] = []
        with patch('human_eye_plugin.scene_rendering._raster_with_owners', wraps=_raster_with_owners) as default_raster, \
             patch('human_eye_plugin.attention_rendering.rasterize_attention') as contact_raster:
            output, visual, state = finished_attention(meshes, options)
        self.assertIsNone(state)
        self.assertEqual(default_raster.call_count, 4)
        contact_raster.assert_not_called()
        self.assertEqual(visual['views'][3]['name'], 'Q4 TARGET')
        np.testing.assert_array_equal(np.asarray(expected), np.asarray(output))

    def test_enclosing_obstacle_prevents_contact_and_is_in_default_depth(self):
        expected, expected_meta, meshes, options = fixture(enclosed=True)
        with patch('human_eye_plugin.attention_rendering.time.perf_counter', return_value=0.), \
             patch('human_eye_plugin.attention_rendering.rasterize_attention') as contact_raster:
            output, visual, state = finished_attention(meshes, options)
        self.assertIsNone(state)
        contact_raster.assert_not_called()
        np.testing.assert_array_equal(np.asarray(expected), np.asarray(output))
        self.assertEqual(expected_meta['views'], visual['views'])
        self.assertIn('enclosure', visual['views'][3]['occlusion_object_ids'])
        self.assertTrue(visual['views'][3]['all_supplied_geometry_participates_in_depth'])

    def test_candidate_cost_overrun_after_raster_gets_full_default_fallback(self):
        expected, _, meshes, options = fixture()
        clock = [0.]
        def slow_candidate(*args, **kwargs):
            result = rasterize_attention(*args, **kwargs)
            clock[0] = .041
            return result
        with patch('human_eye_plugin.attention_rendering.time.perf_counter', side_effect=lambda: clock[0]), \
             patch('human_eye_plugin.scene_rendering._raster_with_owners', wraps=_raster_with_owners) as default_raster, \
             patch('human_eye_plugin.attention_rendering.rasterize_attention', side_effect=slow_candidate) as contact_raster:
            output, visual, state = finished_attention(meshes, options)
        self.assertIsNone(state)
        self.assertEqual(default_raster.call_count, 4)
        self.assertEqual(contact_raster.call_count, 1)
        self.assertIn('attention_additional_compute_budget_exceeded', visual['attention']['reason_codes'])
        np.testing.assert_array_equal(np.asarray(expected), np.asarray(output))

    def test_unreadable_candidate_cannot_leave_contact_or_pending_pixels(self):
        expected, _, meshes, options = fixture()
        def unreadable(*args, **kwargs):
            color, depth, owners = rasterize_attention(*args, **kwargs)
            color[:] = (70, 70, 70)
            return color, depth, owners
        with patch('human_eye_plugin.attention_rendering.time.perf_counter', return_value=0.), \
             patch('human_eye_plugin.attention_rendering.rasterize_attention', side_effect=unreadable):
            output, visual, state = finished_attention(meshes, options)
        self.assertIsNone(state)
        self.assertIn('candidate_surface_readability_insufficient', visual['attention']['reason_codes'])
        self.assertTrue(visual['raster_schedule']['canvas_complete'])
        self.assertEqual(visual['views'][3]['name'], 'Q4 TARGET')
        np.testing.assert_array_equal(np.asarray(expected), np.asarray(output))

    def test_empty_raster_falls_back_without_committing_attention(self):
        expected, _, meshes, options = fixture()
        empty = (np.zeros((128, 128, 3), dtype=np.uint8), np.full((128, 128), np.inf))
        with patch('human_eye_plugin.attention_rendering.time.perf_counter', return_value=0.), \
             patch('human_eye_plugin.attention_rendering.rasterize_attention', return_value=empty):
            output, visual, state = finished_attention(meshes, options)
        self.assertIsNone(state)
        self.assertEqual(visual['attention']['raster_witness_supported'], [False, False])
        np.testing.assert_array_equal(np.asarray(expected), np.asarray(output))

    def test_planning_timeout_does_not_skip_default_q4(self):
        expected, _, meshes, options = fixture()
        with patch('human_eye_plugin.attention_rendering.time.perf_counter', side_effect=[0.] + [1.] * 100), \
             patch('human_eye_plugin.attention_rendering.rasterize_attention') as raster:
            output, visual, state = finished_attention(meshes, options)
        self.assertIsNone(state)
        raster.assert_not_called()
        self.assertTrue(visual['raster_schedule']['canvas_complete'])
        np.testing.assert_array_equal(np.asarray(expected), np.asarray(output))

    def test_router_exception_delivers_complete_target_and_preserves_measurement(self):
        _, _, meshes, _ = fixture()
        records = []
        with patch('human_eye_plugin.auto_router.apply_attention_to_canvas', side_effect=RuntimeError('optional candidate')), \
             patch('human_eye_plugin.scene_rendering._raster_with_owners', wraps=_raster_with_owners) as raster, \
             RequestTrace('test.router_fallback', writer=records.append):
            result = HumanEyeAutoRouter(quad_size=128).handle_event(observation(scene=near_scene()))
        actual = Image.open(io.BytesIO(base64.b64decode(result['image']['data']))).convert('RGB')
        facts = json.loads(result['context_text'])
        self.assertEqual(facts['canvas']['task_labels']['core_object_ids'], ['part', 'base'])
        expected, expected_meta = render_scene_canvas(meshes, 128, focal_id='part', reference_id='base',
            label_plan=facts['canvas']['task_labels'])
        self.assertEqual(raster.call_count, 4)
        self.assertEqual(facts['canvas']['views'], expected_meta['views'])
        np.testing.assert_array_equal(np.asarray(expected), np.asarray(actual))
        self.assertEqual(facts['attention']['error_type'], 'RuntimeError')
        self.assertEqual(facts['canvas']['attention'], facts['attention'])
        self.assertTrue(facts['canvas']['raster_schedule']['canvas_complete'])
        self.assertAlmostEqual(facts['measurement']['signed_clearance_m'], .002)
        self.assertEqual((facts['focal_id'], facts['reference_id']), ('part', 'base'))
        names = [s['name'] for s in records[0]['spans']]
        self.assertEqual(names.count('render.scene_canvas'), 1)
        self.assertEqual(names.count('render.q4_fallback'), 1)

    def test_router_adopted_and_retained_contacts_never_raster_default_q4(self):
        router = HumanEyeAutoRouter(quad_size=128)
        with patch('human_eye_plugin.attention_rendering.time.perf_counter', return_value=0.), \
             patch('human_eye_plugin.scene_rendering._raster_with_owners', wraps=_raster_with_owners) as default_raster, \
             patch('human_eye_plugin.attention_rendering.rasterize_attention', wraps=rasterize_attention) as contact_raster:
            first = router.handle_event(observation(scene=near_scene(), task_instruction='first view'))
            second = router.handle_event(observation(scene=near_scene(), task_instruction='second view'))
        self.assertEqual(default_raster.call_count, 6)
        self.assertEqual(contact_raster.call_count, 2)
        a, b = (json.loads(r['context_text']) for r in (first, second))
        self.assertEqual(a['attention']['decision'], 'applied')
        self.assertEqual(b['attention']['decision'], 'retained')
        self.assertTrue(a['canvas']['raster_schedule']['canvas_complete'])
        self.assertTrue(b['canvas']['raster_schedule']['canvas_complete'])

    def test_failed_fallback_omits_image_instead_of_delivering_blank_q4(self):
        with patch('human_eye_plugin.auto_router.apply_attention_to_canvas', side_effect=ValueError('candidate')), \
             patch('human_eye_plugin.auto_router._finalize_prepared_scene_q4', side_effect=ValueError('fallback budget')):
            result = HumanEyeAutoRouter().handle_event(observation(scene=near_scene()))
        facts = json.loads(result['context_text'])
        self.assertIsNone(result.get('image'))
        self.assertIn('omitted', facts['canvas'])
        self.assertTrue(result['measurement_valid'])
        self.assertAlmostEqual(facts['measurement']['signed_clearance_m'], .002)

    def test_defer_option_must_be_an_explicit_boolean(self):
        _, _, meshes, _ = fixture()
        for value in (1, None, 'true'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                render_scene_canvas(meshes, 128, defer_q4=value)

    def test_fallback_refuses_to_drop_an_obstacle_from_the_supplied_scene(self):
        _, _, meshes, _ = fixture(enclosed=True)
        image, meta = deferred(meshes)
        with self.assertRaisesRegex(ValueError, 'occlusion geometry differs'):
            finalize_scene_q4(image, meta, meshes[:2])
        self.assertFalse(meta['raster_schedule']['canvas_complete'])


if __name__ == '__main__':
    unittest.main()

"""Actual pixels, occlusion and measured-gain integration, without host writes."""
import copy
import json
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_module1_operators import MeshEntity3D, SpatialAnomalySniffer
from human_eye_plugin.auto_router import HumanEyeAutoRouter, _validated_scene
from human_eye_plugin.attention_rendering import apply_attention_to_canvas
from human_eye_plugin.scene_rendering import render_scene_canvas
from verification.test_auto_router import box, scene, observation


def near_scene():
    value = scene()
    for point in value['meshes'][1]['vertices']:
        point[2] -= .098
    value['meshes'][1]['pivot_world'][2] -= .098
    return value


def fixture(enclosed=False):
    value = near_scene()
    if enclosed:
        value['meshes'].append(box('enclosure', [0, 0, 0], [10, 10, 10]))
    _, meshes, fingerprint = _validated_scene(value)
    probe = SpatialAnomalySniffer.probe_closest_clearance(meshes[1], meshes[0])
    contacts = [{'object_id': 'base', 'measurement_valid': True, 'signed_clearance_m': .002,
                 'point_a_world': probe.point_a_world.tolist(), 'point_b_world': probe.point_b_world.tolist()}]
    image, meta = render_scene_canvas(meshes, 128, focal_id='part', reference_id='base')
    return image, meta, meshes, {'focal_id': 'part', 'reference_id': 'base', 'contacts': contacts,
                                'scene_fingerprint': fingerprint, 'now_s': 100.}


class AttentionRenderingTests(unittest.TestCase):
    def test_actual_visible_gap_improves_and_only_q4_changes(self):
        image, meta, meshes, options = fixture()
        before = [copy.deepcopy(mesh.to_dict()) for mesh in meshes]
        output, visual, state = apply_attention_to_canvas(image, meta, meshes, **options)
        self.assertIsNotNone(state, visual['attention'])
        self.assertEqual(visual['attention']['decision'], 'applied')
        self.assertGreater(visual['attention']['actual_projected_gap_px'], 10)
        self.assertGreater(visual['attention']['net_gain_px'], 2)
        self.assertEqual(visual['attention']['raster_witness_supported'], [True, True])
        self.assertEqual(visual['views'][:3], meta['views'][:3])
        np.testing.assert_array_equal(np.asarray(output)[:128], np.asarray(image)[:128])
        np.testing.assert_array_equal(np.asarray(output)[128:, :128], np.asarray(image)[128:, :128])
        self.assertFalse(np.array_equal(np.asarray(output)[128:, 128:], np.asarray(image)[128:, 128:]))
        self.assertEqual(before, [mesh.to_dict() for mesh in meshes])
        self.assertFalse(visual['visibility_certified'])

    def test_enclosure_cannot_be_turned_into_xray_visibility(self):
        image, meta, meshes, options = fixture(enclosed=True)
        with patch('human_eye_plugin.attention_rendering.rasterize_attention') as raster:
            output, visual, state = apply_attention_to_canvas(image, meta, meshes, **options)
        raster.assert_not_called()
        self.assertIs(output, image)
        self.assertIsNone(state)
        self.assertEqual(visual['attention']['decision'], 'hold')

    def test_empty_raster_does_not_commit_even_when_exact_rays_are_visible(self):
        image, meta, meshes, options = fixture()
        with patch('human_eye_plugin.attention_rendering.rasterize_attention',
                   return_value=(np.zeros((128, 128, 3), dtype=np.uint8), np.full((128, 128), np.inf))):
            output, visual, state = apply_attention_to_canvas(image, meta, meshes, **options)
        self.assertIsNone(state)
        self.assertIs(output, image)
        self.assertEqual(visual['attention']['raster_witness_supported'], [False, False])

    def test_invalid_contact_evidence_never_enters_an_extra_raster(self):
        image, meta, meshes, options = fixture()
        options['contacts'][0]['signed_clearance_m'] = .00001
        with patch('human_eye_plugin.attention_rendering.rasterize_attention') as raster:
            output, visual, state = apply_attention_to_canvas(image, meta, meshes, **options)
        raster.assert_not_called()
        self.assertIs(output, image)
        self.assertIsNone(state)

    def test_planning_time_budget_stops_extra_rendering(self):
        image, meta, meshes, options = fixture()
        with patch('human_eye_plugin.attention_rendering.time.perf_counter', side_effect=[0.] + [1.] * 100):
            with patch('human_eye_plugin.attention_rendering.rasterize_attention') as raster:
                output, visual, state = apply_attention_to_canvas(image, meta, meshes, **options)
        raster.assert_not_called()
        self.assertIs(output, image)
        self.assertIsNone(state)

    def test_router_retains_verified_focus_and_measurement_pair(self):
        router = HumanEyeAutoRouter(quad_size=128)
        first = router.handle_event(observation(scene=near_scene(), task_instruction='first'))
        second = router.handle_event(observation(scene=near_scene(), task_instruction='second'))
        a, b = json.loads(first['context_text']), json.loads(second['context_text'])
        self.assertEqual(a['attention']['decision'], 'applied')
        self.assertEqual(b['attention']['decision'], 'retained')
        self.assertFalse(b['attention']['shifted'])
        self.assertEqual((b['focal_id'], b['reference_id']), ('part', 'base'))
        self.assertAlmostEqual(b['measurement']['signed_clearance_m'], .002)

    def test_text_delivery_skips_attention_planning_and_raster(self):
        with patch('human_eye_plugin.auto_router.apply_attention_to_canvas') as attention:
            result = HumanEyeAutoRouter().handle_event(observation(scene=near_scene(), include_image=False))
        attention.assert_not_called()
        self.assertEqual(json.loads(result['context_text'])['attention']['reason_codes'], ['image_not_requested'])

    def test_dwell_expiry_rechecks_attention_before_normal_observation_ttl(self):
        clock = [100.]
        router = HumanEyeAutoRouter(quad_size=128, clock=lambda: clock[0])
        first = router.handle_event(observation(scene=near_scene()))
        self.assertEqual(json.loads(first['context_text'])['attention']['decision'], 'applied')
        changed = near_scene()
        changed['revision'] = 'r2'
        for point in changed['meshes'][1]['vertices']:
            point[2] -= .00198
        changed['meshes'][1]['pivot_world'][2] -= .00198
        clock[0] = 100.1
        held = router.handle_event(observation(scene=changed))
        self.assertIn('attention_dwell_active', json.loads(held['context_text'])['attention']['reason_codes'])
        clock[0] = 100.2
        self.assertTrue(router.handle_event(observation(scene=changed))['cache_hit'])
        clock[0] = 101.1
        refreshed = router.handle_event(observation(scene=changed))
        self.assertFalse(refreshed['cache_hit'])
        self.assertNotIn('attention_dwell_active', json.loads(refreshed['context_text'])['attention']['reason_codes'])


if __name__ == '__main__':
    unittest.main()

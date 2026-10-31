"""Precision and delivery checks through the real v1 observation boundary."""
import json
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin.auto_router import HumanEyeAutoRouter
from human_eye_plugin.live_hooks import route_live_hook
from verification.test_auto_router import observation, scene
from verification import test_live_hooks as hook_fixtures


class V1ObservationFlowTests(unittest.TestCase):
    def test_raw_geometry_limits_are_checked_before_array_allocation(self):
        class OversizedList(list):
            def __len__(self):
                return 500_001
        source = scene()
        source['meshes'][0]['vertices'] = OversizedList()
        event = observation(scene=source)
        with patch('human_eye_plugin.auto_router.np.asarray') as conversion:
            result = HumanEyeAutoRouter(quad_size=64).handle_event(event)
        conversion.assert_not_called()
        self.assertEqual(result['reason_codes'], ['invalid_scene'])

    def test_excess_duplicate_edge_hints_do_not_enter_array_allocation(self):
        source = scene()
        source['meshes'][0]['edges'] = [[0, 1]] * (3 * len(source['meshes'][0]['faces']) + 1)
        event = observation(scene=source)
        with patch('human_eye_plugin.auto_router.np.asarray') as conversion:
            result = HumanEyeAutoRouter(quad_size=64).handle_event(event)
        conversion.assert_not_called()
        self.assertEqual(result['reason_codes'], ['invalid_scene'])

    def test_explicit_native_tasks_do_not_enter_geometry_work(self):
        with patch('human_eye_plugin.auto_router.work_budget_status') as budget:
            result = HumanEyeAutoRouter(quad_size=64).handle_event(observation(task_kind='general'))
        self.assertEqual(result['route'], 'native')
        budget.assert_not_called()

    def test_text_host_skips_raster_work_but_keeps_real_measurements(self):
        router = HumanEyeAutoRouter(quad_size=64)
        event = observation(include_image=False)
        with patch('human_eye_plugin.auto_router._render_scene_canvas_prepared') as renderer:
            result = router.handle_event(event)
        renderer.assert_not_called()
        self.assertEqual(result['route'], 'engine')
        self.assertIsNone(result['image'])
        facts = json.loads(result['context_text'])
        self.assertAlmostEqual(facts['measurement']['signed_clearance_m'], .1)
        self.assertEqual(facts['canvas']['omitted'], 'text_only_host_delivery')

    def test_image_delivery_change_does_not_reuse_a_text_only_cache(self):
        router = HumanEyeAutoRouter(quad_size=64)
        text = router.handle_event(observation(include_image=False))
        image = router.handle_event(observation(include_image=True))
        self.assertFalse(image['cache_hit'])
        self.assertNotEqual(text['observation_id'], image['observation_id'])
        self.assertIsNotNone(image['image'])
        cached = router.handle_event(observation(include_image=True))
        self.assertTrue(cached['cache_hit'])

    def test_micrometre_clearance_is_not_rounded_to_flush_in_model_input(self):
        actual = scene()
        target = next(m for m in actual['meshes'] if m['is_focal_target'])
        target['vertices'] = (np.array(target['vertices']) + [0, 0, -.09995]).tolist()
        target['pivot_world'] = (np.array(target['pivot_world']) + [0, 0, -.09995]).tolist()
        result = HumanEyeAutoRouter(quad_size=64).handle_event(observation(scene=actual, include_image=False))
        facts = json.loads(result['context_text'])
        self.assertAlmostEqual(facts['measurement']['signed_clearance_m'], .00005, places=12)
        self.assertNotIn('display_signed_clearance_m', facts['measurement'])
        self.assertNotIn('alignment_state', facts['measurement'])
        self.assertEqual(facts['measurement']['legacy_display']['display_signed_clearance_m'], 0)
        self.assertTrue(facts['measurement']['legacy_display']['alignment_state_is_display_only'])
        self.assertEqual(facts['measurement']['clearance_state'], 'positive_clearance')
        self.assertFalse(facts['measurement']['is_penetrating'])

    def test_image_numeric_failure_does_not_fabricate_or_remove_geometry(self):
        with patch('human_eye_plugin.auto_router._render_scene_canvas_prepared', side_effect=ValueError('camera range')):
            result = HumanEyeAutoRouter(quad_size=64).handle_event(observation())
        self.assertEqual(result['route'], 'engine')
        self.assertTrue(result['measurement_valid'])
        self.assertIsNone(result['image'])
        self.assertEqual(json.loads(result['context_text'])['canvas']['omitted'], 'rendering_resource_or_numeric_limit')

    def test_invalid_image_policy_is_rejected(self):
        for value in (None, 0, 1, 'false'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                HumanEyeAutoRouter(quad_size=64).handle_event(observation(include_image=value))

    def test_live_text_hooks_explicitly_skip_images(self):
        service = hook_fixtures.HookService()
        event = hook_fixtures.LiveHooksTests().event()
        route_live_hook(event, service)
        self.assertFalse(service.calls[0][2]['include_image'])
        route_live_hook({**event, 'hook_event_name': 'PostToolUse'}, service)
        self.assertFalse(service.calls[-1][2]['include_image'])


if __name__ == '__main__':
    unittest.main()

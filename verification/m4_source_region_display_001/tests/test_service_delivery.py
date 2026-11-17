"""Exercise current display selection and native feedback with mocked pixels."""

import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from human_eye_plugin import source_region
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer, _tool_result

ROOT = Path(__file__).resolve().parents[3]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LEGACY = load('_display_service_legacy', ROOT / 'verification/m4_m5_source_region_001/transport_tests/test_transport.py')
IMAGES = load('_display_service_images', Path(__file__).with_name('test_display_images.py'))


class DisplayServiceTests(unittest.TestCase):
    capture_scene = LEGACY.ServiceTests.capture_scene
    validate_ref = LEGACY.ServiceTests.validate_ref
    measure = LEGACY.ServiceTests.measure
    patches = LEGACY.ServiceTests.patches
    observe = LEGACY.ServiceTests.observe

    def setUp(self):
        LEGACY.ServiceTests.setUp(self)
        self.current['display_snapshot'] = IMAGES.snapshot(self.current, (True, False, True))

    def prepare(self, current, query, check_budget, **options):
        value = LEGACY.ServiceTests.prepare(self, current, query, check_budget, **options)
        value.display = source_region.display_state(current)
        value.binding['display_identity'] = value.display['identity']
        value.binding['image_scope'] = copy.deepcopy(value.display)
        value.binding['binding_sha256'] = LEGACY.digest(value.binding)
        return value

    def observe_core(self, prepared, directory, **options):
        value = LEGACY.ServiceTests.observe_core(self, prepared, directory, **options)
        requested = options['include_image']
        shown = prepared.display['status'] == 'captured' and prepared.display['participation_mask'][0]
        insufficient = requested and not shown
        value.update(status='partial' if insufficient else 'complete',
            observation_status='evidence_insufficient' if insufficient else
                'locally_observed' if requested else 'image_not_requested')
        visibility = value['facts']['visibility']
        visibility.update(status='observed_samples' if requested and shown else 'unknown',
            selected_surface_pixels=16 if requested and shown else 0,
            unknown=['complete_surface_visibility'])
        if insufficient:
            visibility['reason'] = 'selected_region_not_displayed'
        elif not requested:
            visibility['reason'] = 'image_not_requested'
        for frame in value['frames']:
            frame.update(display_identity=prepared.display['identity'],
                         image_scope_identity=prepared.display['identity'])
        return value

    def set_visible(self, index, visible):
        row = self.current['display_snapshot']['objects'][index]
        row.update(visible_get=visible, hide_get=not visible)
        IMAGES.resign(self.current)

    def test_same_generation_display_change_and_restore_select_current_cache(self):
        with self.patches():
            initial = self.observe()
            self.set_visible(0, False)
            hidden = self.observe()
            self.set_visible(0, True)
            restored = self.observe()
        self.assertEqual(initial['region_ref'], hidden['region_ref'])
        self.assertEqual((self.prepare_calls, self.render_calls), (2, 2))
        self.assertNotEqual(initial['binding']['display_identity'], hidden['binding']['display_identity'])
        self.assertEqual(restored['binding'], initial['binding'])
        self.assertEqual(restored['work']['frame_reuses'], 1)
        self.assertEqual(hidden['status'], 'partial')
        self.assertEqual(restored['status'], 'complete')

    def test_same_geometry_layer_change_isolated(self):
        with self.patches():
            first = self.observe()
            self.current['display_snapshot']['view_layer']['instance_id'] = 'layer:2'
            IMAGES.resign(self.current)
            second = self.observe()
        self.assertNotEqual(first['binding']['display_identity'], second['binding']['display_identity'])
        self.assertEqual(self.render_calls, 2)

    def test_default_brief_and_full_preserve_partial_and_measured_task(self):
        with self.patches():
            self.set_visible(0, False)
            first = self.observe()
            repeated = self.observe()
        for detail in ('brief', 'full'):
            content = _tool_result(repeated, is_error=False, response_detail=detail)
            text = json.loads(content['content'][0]['text'])
            self.assertEqual(text['status'], 'partial')
            self.assertEqual(text['observation_status'], 'evidence_insufficient')
            visible = text['visibility'] if detail == 'brief' else text['facts']['visibility']
            self.assertEqual(visible['status'], 'unknown')
            self.assertEqual(visible['selected_surface_pixels'], 0)
            self.assertEqual(text['task_result']['status'], 'complete')
            self.assertEqual(text['task_result']['facts']['surface_proximity']['value']['distance_m'], 1.25)
            self.assertFalse(content['isError'])
            if detail == 'brief':
                self.assertIn({'scope': 'image_evidence', 'reason': 'selected_region_not_displayed'}, text['unknowns'])
        self.assertEqual(first['status'], repeated['status'])
        self.assertEqual(repeated['work']['raster_attempts'], 0)

    def test_mcp_public_partial_is_successful_evidence_response(self):
        self.set_visible(0, False)
        with self.patches():
            response = LiveSpatialMCPServer(self.service)._call_tool('human_eye_scene_observe', {'query': LEGACY.QUERY})
        self.assertFalse(response['isError'])
        text = json.loads(response['content'][0]['text'])
        self.assertEqual(text['status'], 'partial')
        self.assertEqual(text['observation_status'], 'evidence_insufficient')

    def test_no_image_keeps_normal_measured_task(self):
        with self.patches():
            value = self.observe(include_image=False)
        self.assertEqual(value['status'], 'complete')
        self.assertEqual(value['observation_status'], 'image_not_requested')
        self.assertEqual(value['frames'], [])
        self.assertEqual(self.render_calls, 0)
        self.assertEqual(value['task_result']['status'], 'complete')

    def test_missing_display_cannot_reuse_previous_valid_observation(self):
        with self.patches():
            first = self.observe()
            del self.current['display_snapshot']
            missing = self.observe()
        self.assertNotEqual(first['binding']['display_identity'], missing['binding']['display_identity'])
        self.assertEqual(missing['status'], 'partial')
        self.assertEqual(missing['task_result']['status'], 'complete')

    def test_display_validation_preserves_original_budget_check(self):
        with self.patches(), patch.object(self.service, '_check_request_budget',
                side_effect=lambda stage: (_ for _ in ()).throw(InterruptedError('cancelled'))
                if stage == 'after_source_region_display_validation' else None):
            with self.assertRaisesRegex(InterruptedError, 'cancelled'):
                self.observe()
        self.assertEqual(self.render_calls, 0)


if __name__ == '__main__':
    unittest.main()

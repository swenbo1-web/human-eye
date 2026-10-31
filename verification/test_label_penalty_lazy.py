"""Do not build annotation weights when no usable task label reaches layout."""
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from human_eye_plugin import scene_rendering as sr
from human_eye_plugin.task_labels import build_task_label_plan


class LazyLabelPenaltyTests(unittest.TestCase):
    def setUp(self):
        self.meshes = [SimpleNamespace(object_id=name, mark_label='#'+name, name=name)
                       for name in ('base', 'part', 'outer', 'requested')]

    def plan(self, explicit=False):
        return build_task_label_plan(self.meshes, focal_id='part', reference_id='base',
            visual_focus_ids=['requested'] if explicit else [],
            scene_revision='r1', scene_fingerprint='lazy-penalty')

    def draw(self, owners, *, plan=True, contact=False, caption=None, frame=False,
             navigation=None, same_color=False):
        size = owners.shape[0]
        picture = Image.new('RGB', (size, size), (80, 80, 80) if same_color else (18, 22, 30))
        metadata = {'name': 'Q4 CONTACT' if contact else 'Q2 WORK XY',
                    'projection': 'orthographic', 'target_object_ids': ['part', 'base'],
                    'm_per_pixel': .001}
        source = owners.copy()
        label_plan = self.plan() if plan is True else None if plan is False else plan
        original_plan = copy.deepcopy(label_plan)
        with patch.object(sr, '_label_penalty_map', wraps=sr._label_penalty_map) as weight:
            sr._annotate(picture, self.meshes, np.eye(4), np.eye(4), metadata, owners,
                label_plan=label_plan, caption_reserved_region=caption,
                frame_safe_labels=frame, navigation_reserved_region=navigation)
        np.testing.assert_array_equal(owners, source)
        self.assertEqual(label_plan, original_plan)
        return picture, metadata, weight.call_count

    def test_fully_occluded_core_skips_weights_but_preserves_omissions(self):
        owners = np.full((128, 128), 2, dtype=np.int32)
        _, meta, count = self.draw(owners)
        self.assertEqual(count, 0)
        self.assertEqual(meta['projected_labels'], [])
        self.assertEqual(meta['object_visible_pixels']['outer'], 128*128)
        self.assertEqual(meta['label_layout']['omitted_object_count'], 4)
        self.assertEqual(meta['label_layout']['eligible_object_count'], 1)
        self.assertEqual(meta['label_layout']['omitted_reason_counts'],
                         {'not_surface_visible': 3, 'outside_task_label_focus': 1})

    def test_empty_and_too_small_surface_skip_weights(self):
        for pixels in (0, 1, 7):
            owners = np.full((128, 128), -1, dtype=np.int32)
            owners[30, :pixels] = 1
            with self.subTest(pixels=pixels):
                _, meta, count = self.draw(owners)
                self.assertEqual(count, 0)
                self.assertEqual(meta['projected_labels'], [])

    def test_small_views_keep_view_too_small_receipt(self):
        owners = np.zeros((64, 64), dtype=np.int32)
        _, meta, count = self.draw(owners)
        self.assertEqual(count, 0)
        self.assertEqual(meta['label_layout']['omitted_reason_counts']['view_too_small'], 1)

    def test_caption_or_frame_hiding_all_usable_surface_skips_weights(self):
        for kind in ('caption', 'frame', 'navigation'):
            owners = np.full((128, 128), -1, dtype=np.int32)
            if kind == 'caption':
                owners[100:110, 20:40] = 1
                options = {'contact': True, 'caption': (0, 90, 128, 128)}
                reason = 'no_surface_anchor_outside_caption'
            else:
                owners[5:10, 20:40] = 1
                options = {'frame': True} if kind == 'frame' else {'navigation': (0, 85, 128, 113)}
                reason = 'no_surface_anchor_outside_' + ('frame_overlay' if kind == 'frame' else 'navigation_overlay')
            with self.subTest(kind=kind):
                _, meta, count = self.draw(owners, **options)
                self.assertEqual(count, 0)
                self.assertEqual(meta['label_layout']['omitted_reason_counts'][reason], 1)

    def test_normal_dense_and_low_contrast_layouts_construct_once(self):
        for dense in (False, True):
            owners = (np.indices((128, 128)).sum(axis=0) % 2 if dense
                      else np.indices((128, 128))[1] >= 64).astype(np.int32)
            for same_color in (False, True):
                with self.subTest(dense=dense, same_color=same_color):
                    _, meta, count = self.draw(owners, same_color=same_color)
                    self.assertEqual(count, 1)
                    self.assertEqual(len(meta['projected_labels']), 2)

    def test_explicit_hidden_identity_stays_undrawn_without_weights(self):
        owners = np.full((128, 128), 2, dtype=np.int32)
        _, meta, count = self.draw(owners, plan=self.plan(explicit=True))
        self.assertEqual(count, 0)
        self.assertEqual(meta['label_layout']['visual_focus_coverage']['drawn_object_ids'], [])
        self.assertEqual(meta['label_layout']['visual_focus_coverage']['undrawn_objects'],
                         [{'object_id': 'requested', 'reason': 'not_surface_visible'}])

    def test_public_contact_compatibility_still_constructs_once(self):
        owners = (np.indices((128, 128))[1] >= 64).astype(np.int32)
        _, meta, count = self.draw(owners, plan=False, contact=True)
        self.assertEqual(count, 1)
        self.assertEqual(len(meta['projected_labels']), 2)
        self.assertEqual(meta['label_layout_profile'], sr.CONTACT_LABEL_PROFILE)

    def test_exact_minimum_surface_can_reach_layout_once(self):
        owners = np.full((128, 128), -1, dtype=np.int32)
        owners[50:52, 60:64] = 1
        _, meta, count = self.draw(owners)
        self.assertEqual(count, 1)
        self.assertEqual(meta['object_visible_pixels']['part'], 8)
        self.assertEqual(len(meta['projected_labels']), 1)


if __name__ == '__main__':
    unittest.main()

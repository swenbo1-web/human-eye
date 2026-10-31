"""Surface-label priorities stay separate from camera framing and visibility."""
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin import scene_rendering as rendering
from verification.test_auto_router import box


def ownership_fixture(counts, size=512):
    """Supply exact visible-owner pixels without invoking a geometry renderer."""
    meshes = [SimpleNamespace(object_id=identity, mark_label=f'#B{index:04d}')
              for index, identity in enumerate(counts)]
    owners = np.full((size, size), -1, dtype=np.int32)
    columns = 3
    rows = max(1, (len(meshes) + columns - 1) // columns)
    xs = np.linspace(12, size - 20, columns).astype(int)
    ys = np.linspace(24, size - 24, rows).astype(int)
    for index, count in enumerate(counts.values()):
        y, x = ys[index // columns], xs[index % columns]
        dy, dx = np.unravel_index(np.arange(count), (6, 6))
        owners[y + dy, x + dx] = index
    return meshes, owners


def annotate(meshes, owners, priority_ids=None, *, target_ids=None):
    size = owners.shape[0]
    image = Image.new('RGB', (size, size), (18, 22, 30))
    metadata = {'name': 'Q1 XY TOP', 'projection': 'orthographic',
                'm_per_pixel': .001,
                'target_object_ids': (list(target_ids) if target_ids is not None
                                      else [mesh.object_id for mesh in meshes])}
    if priority_ids is not None:
        metadata['label_priority_object_ids'] = list(priority_ids)
    rendering._annotate(image, meshes, None, None, metadata, owners)
    return image, metadata


class LabelPriorityTests(unittest.TestCase):
    def dense_fixture(self):
        counts = {f'obstacle-{index:02d}': 9 for index in range(10)}
        counts.update(focal=9, reference=9)
        return ownership_fixture(counts)

    def test_pair_at_end_of_whole_scene_enumeration_gets_first_budget_slots(self):
        meshes, owners = self.dense_fixture()
        before = owners.copy()
        _, metadata = annotate(meshes, owners, ['focal', 'reference'])
        ids = [row['object_id'] for row in metadata['projected_labels']]
        self.assertEqual(ids, ['focal', 'reference'] +
                         [f'obstacle-{index:02d}' for index in range(6)])
        self.assertEqual(metadata['target_object_ids'], [mesh.object_id for mesh in meshes])
        self.assertEqual(metadata['label_priority_object_ids'], ['focal', 'reference'])
        layout = metadata['label_layout']
        self.assertEqual(layout['max_labels'], 8)
        self.assertEqual(layout['minimum_surface_pixels'], 8)
        self.assertEqual(layout['eligible_object_count'], 12)
        self.assertEqual(layout['displayed_label_count'], 8)
        self.assertEqual(layout['omitted_objects'], [
            {'object_id': f'obstacle-{index:02d}', 'reason': 'label_budget_exhausted'}
            for index in range(6, 10)])
        self.assertFalse(metadata['labels_certify_visibility'])
        np.testing.assert_array_equal(owners, before)

    def test_nonpriority_objects_use_surface_area_then_object_id(self):
        meshes, owners = ownership_fixture({'small': 8, 'z-large': 25,
                                             'a-large': 25, 'focal': 9, 'reference': 9})
        _, metadata = annotate(meshes, owners, ['focal', 'reference'])
        self.assertEqual([row['object_id'] for row in metadata['projected_labels']],
                         ['focal', 'reference', 'a-large', 'z-large', 'small'])

    def test_omission_details_are_bounded_but_counts_include_every_object(self):
        counts = {f'hidden-{index:02d}': 0 for index in range(30)}
        counts.update(focal=0, reference=7)
        meshes, owners = ownership_fixture(counts)
        _, metadata = annotate(meshes, owners, ['focal', 'reference'])
        layout = metadata['label_layout']
        self.assertEqual(metadata['projected_labels'], [])
        self.assertEqual(layout['omitted_object_count'], 32)
        self.assertEqual(layout['omitted_reason_counts'],
                         {'not_surface_visible': 31, 'insufficient_surface_pixels': 1})
        self.assertEqual(layout['omitted_objects'], [
            {'object_id': 'focal', 'reason': 'not_surface_visible'},
            {'object_id': 'reference', 'reason': 'insufficient_surface_pixels'}] + [
            {'object_id': f'hidden-{index:02d}', 'reason': 'not_surface_visible'}
            for index in range(14)])
        self.assertEqual(len(layout['omitted_objects']), 16)
        self.assertEqual(layout['omitted_objects_truncated'], 16)
        self.assertEqual(layout['omitted_object_count'],
                         len(layout['omitted_objects']) + layout['omitted_objects_truncated'])

    def test_scene_enumeration_and_host_marks_do_not_change_selected_layout(self):
        meshes, owners = self.dense_fixture()
        first_image, first = annotate(meshes, owners, ['focal', 'reference'])
        reordered = list(reversed(copy.deepcopy(meshes)))
        new_index = {mesh.object_id: index for index, mesh in enumerate(reordered)}
        remapped = np.full_like(owners, -1)
        for index, mesh in enumerate(meshes):
            remapped[owners == index] = new_index[mesh.object_id]
        for index, mesh in enumerate(reordered):
            mesh.mark_label = f'#RENAMED-{index}'
        second_image, second = annotate(reordered, remapped, ['focal', 'reference'])
        rows = lambda metadata: [{key: value for key, value in row.items() if key != 'mark_label'}
                                 for row in metadata['projected_labels']]
        self.assertEqual(rows(first), rows(second))
        self.assertEqual(first['label_layout'], second['label_layout'])
        self.assertEqual(first['object_visible_pixels'], second['object_visible_pixels'])
        self.assertEqual(first_image.tobytes(), second_image.tobytes())

    def test_priority_cannot_create_visibility_or_bypass_minimum_surface_pixels(self):
        meshes, owners = ownership_fixture({'hidden': 0, 'faint': 7, 'threshold': 8,
                                             'visible': 12})
        _, metadata = annotate(meshes, owners, ['hidden', 'faint', 'threshold'])
        self.assertEqual([row['object_id'] for row in metadata['projected_labels']],
                         ['threshold', 'visible'])
        self.assertEqual(metadata['label_layout']['eligible_object_count'], 2)
        self.assertEqual(metadata['label_layout']['omitted_objects'], [
            {'object_id': 'hidden', 'reason': 'not_surface_visible'},
            {'object_id': 'faint', 'reason': 'insufficient_surface_pixels'}])
        self.assertFalse(metadata['labels_certify_visibility'])

    def test_small_view_retains_surface_counts_and_explains_missing_labels(self):
        meshes, owners = ownership_fixture({'focal': 9, 'reference': 9}, size=64)
        _, metadata = annotate(meshes, owners, ['focal', 'reference'])
        self.assertEqual(metadata['projected_labels'], [])
        self.assertEqual(metadata['object_visible_pixels'], {'focal': 9, 'reference': 9})
        self.assertEqual(metadata['label_layout']['eligible_object_count'], 2)
        self.assertEqual(metadata['label_layout']['omitted_objects'], [
            {'object_id': identity, 'reason': 'view_too_small'}
            for identity in ('focal', 'reference')])

    def test_selected_boxes_remain_bounded_disjoint_and_anchored_to_the_owner(self):
        meshes, owners = self.dense_fixture()
        _, metadata = annotate(meshes, owners, ['focal', 'reference'])
        indices = {mesh.object_id: index for index, mesh in enumerate(meshes)}
        rows = metadata['projected_labels']
        for index, row in enumerate(rows):
            x, y = row['projected_center_px']
            self.assertEqual(owners[y, x], indices[row['object_id']])
            a = row['label_box_px']
            self.assertTrue(2 <= a[0] < a[2] <= 510)
            self.assertTrue(19 <= a[1] < a[3] <= 493)
            for other in rows[index + 1:]:
                b = other['label_box_px']
                self.assertFalse(a[0] < b[2] + 2 and a[2] > b[0] - 2
                                 and a[1] < b[3] + 2 and a[3] > b[1] - 2)

    def test_unavailable_local_layout_keeps_nonoverlap_gate_and_reports_omission(self):
        image = Image.new('RGB', (128, 128))
        self.assertIsNone(rendering._label_box(ImageDraw.Draw(image), 'O12345678',
            (64, 64), 128, [(0, 0, 127, 127)], np.zeros((128, 128))))
        meshes, owners = ownership_fixture({'focal': 9, 'reference': 9})
        with patch.object(rendering, '_label_box', return_value=None):
            _, metadata = annotate(meshes, owners, ['focal', 'reference'])
        self.assertEqual(metadata['projected_labels'], [])
        self.assertEqual(metadata['label_layout']['displayed_label_count'], 0)
        self.assertEqual(metadata['label_layout']['omitted_objects'], [
            {'object_id': identity, 'reason': 'no_nonoverlapping_local_box'}
            for identity in ('focal', 'reference')])

    def test_contact_without_override_prioritizes_its_actual_attention_pair(self):
        meshes, owners = self.dense_fixture()
        _, metadata = annotate(meshes, owners, target_ids=['reference', 'focal'])
        self.assertEqual(metadata['label_priority_object_ids'], ['reference', 'focal'])
        self.assertEqual([row['object_id'] for row in metadata['projected_labels'][:2]],
                         ['reference', 'focal'])

    def test_scene_and_deferred_target_keep_camera_framing_and_label_pair_separate(self):
        meshes = [MeshEntity3D.from_dict(value) for value in (
            box('base', [0, 0, 0], [1, 1, .2]),
            box('part', [0, 0, .3], [.2, .2, .2], True))]
        for deferred in (False, True):
            with self.subTest(deferred=deferred):
                _, metadata = rendering.render_scene_canvas(meshes, 128,
                    focal_id='part', reference_id='base', defer_q4=deferred)
                for view in metadata['views']:
                    self.assertEqual(view['label_priority_object_ids'], ['part', 'base'])
                for view in metadata['views'][:3]:
                    self.assertEqual(view['target_object_ids'], ['base', 'part'])
                self.assertEqual(metadata['views'][3]['target_object_ids'], ['part', 'base'])
                if deferred:
                    self.assertEqual(metadata['views'][3]['render_status'], 'deferred')

    def test_unrequested_pair_does_not_make_whole_scene_enumeration_a_priority(self):
        meshes, owners = ownership_fixture({'small-first': 8, 'large-last': 25})
        _, metadata = annotate(meshes, owners, [])
        self.assertEqual(metadata['label_priority_object_ids'], [])
        self.assertEqual([row['object_id'] for row in metadata['projected_labels']],
                         ['large-last', 'small-first'])


if __name__ == '__main__':
    unittest.main()

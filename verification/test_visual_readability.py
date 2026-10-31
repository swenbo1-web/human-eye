"""Synthetic readback-image contracts; no Blender or historical fixture reads."""
import copy
import json
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin.attention_raster import rasterize_attention
from human_eye_plugin.attention_rendering import apply_attention_to_canvas, _attention_camera
from human_eye_plugin.scene_rendering import render_scene_canvas, _camera, _SceneRasterizer, _raster_with_owners
from verification.test_auto_router import box
from verification.test_attention_rendering import fixture


def dispersed_meshes():
    values = [box('base', [0, 0, .1], [1.4, 1.2, .2]),
              box('part', [0, 0, .252], [.3, .2, .1], True)]
    values.extend(box(f'far-{i}', [100 + i * 4, 100 + (i % 7) * 8, .2], [.08, .08, .08])
                  for i in range(98))
    return [MeshEntity3D.from_dict(value) for value in values]


def synthetic_contact_picture():
    """Pure synthetic PNG/metadata source for installed-wheel artifact checks."""
    image, metadata, meshes, options = fixture()
    return apply_attention_to_canvas(image, metadata, meshes, **options)[:2]


class VisualReadabilityTests(unittest.TestCase):
    def test_dispersed_scene_has_honest_navigation_and_readable_workspaces(self):
        meshes = dispersed_meshes()
        image, meta = render_scene_canvas(meshes, 128, focal_id='part', reference_id='base')
        self.assertEqual(image.size, (256, 256))
        self.assertEqual(meta['view_layout'], 'navigation_workspace_target')
        nav, top, front, _ = meta['views']
        self.assertEqual(nav['navigation']['position_count'], 100)
        self.assertEqual(nav['navigation']['scope'], 'object_positions_not_visible_surfaces')
        self.assertLess(nav['geometry_depth_pixels'], 100)
        self.assertEqual(nav['projected_labels'], [])
        for view, axes in ((top, 'XY'), (front, 'XZ')):
            self.assertEqual(view['projection'], 'orthographic')
            self.assertEqual(view['world_axes'], axes)
            self.assertEqual(view['view_scope'], 'target_workspace')
            self.assertGreater(view['geometry_depth_pixels'], 100)
            self.assertGreater(view['object_visible_pixels']['part'], 16)
            self.assertEqual(set(view['occlusion_object_ids']), {mesh.object_id for mesh in meshes})
        json.dumps(meta, allow_nan=False)

    def test_labels_are_stable_across_scene_enumeration_and_host_renumbering(self):
        meshes = dispersed_meshes()[:2]
        before = copy.deepcopy([mesh.to_dict() for mesh in meshes])
        _, a = render_scene_canvas(meshes, 128, focal_id='part', reference_id='base')
        changed = [MeshEntity3D.from_dict(mesh.to_dict()) for mesh in reversed(meshes)]
        for index, mesh in enumerate(changed):
            mesh.mark_label = f'#B{index + 90:04d}'
        _, b = render_scene_canvas(changed, 128, focal_id='part', reference_id='base')
        labels = lambda meta: {row['object_id']: row['stable_label'] for row in meta['object_labels']}
        self.assertEqual(labels(a), labels(b))
        self.assertEqual(before, [mesh.to_dict() for mesh in meshes])

    def test_fully_hidden_object_has_no_surface_label(self):
        values = [box('hidden', [0, 0, 0], [.2, .2, .2], True),
                  box('occluder', [0, 0, 1], [2, 2, .3])]
        meshes = [MeshEntity3D.from_dict(value) for value in values]
        _, metadata = render_scene_canvas(meshes, 128, focal_id='hidden', reference_id='occluder')
        top = metadata['views'][0]
        self.assertEqual(top['object_visible_pixels']['hidden'], 0)
        self.assertNotIn('hidden', [row['object_id'] for row in top['projected_labels']])
        self.assertGreater(top['object_visible_pixels']['occluder'], 100)

    def test_visible_label_boxes_do_not_overlap(self):
        meshes = dispersed_meshes()[:2]
        _, metadata = render_scene_canvas(meshes, 256, focal_id='part', reference_id='base')
        for view in metadata['views']:
            rows = view['projected_labels']
            for i, first in enumerate(rows):
                self.assertGreaterEqual(first['surface_visible_pixels'], 8)
                a = first['label_box_px']
                for second in rows[i + 1:]:
                    b = second['label_box_px']
                    self.assertFalse(a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1])

    def test_local_camera_does_not_start_inside_foreground_scene_geometry(self):
        meshes = [MeshEntity3D.from_dict(value) for value in
                  [box('part', [0, 0, 0], [.1, .1, .1], True),
                   box('foreground', [20, -20, 20], [2, 2, 2])]]
        view, _, _ = _camera('local', meshes, meshes[:1], 128, 'perspective', [2.4, -3.2, 2.4])
        depth = np.concatenate([-mesh.vertices @ view[2, :3] - view[2, 3] for mesh in meshes])
        self.assertGreaterEqual(float(depth.min()), .08)

    def test_contact_has_identifiable_surfaces_scale_and_honest_measurement_annotation(self):
        image, meta, meshes, options = fixture()
        output, visual, state = apply_attention_to_canvas(image, meta, meshes, **options)
        self.assertIsNotNone(state, visual['attention'])
        contact = visual['views'][3]
        evidence = contact['readability']
        self.assertTrue(evidence['passed'])
        self.assertGreaterEqual(min(evidence['visible_surface_pixels']), 16)
        self.assertGreaterEqual(min(evidence['contrasting_boundary_pixels']), 4)
        self.assertFalse(evidence['annotations_count_as_evidence'])
        self.assertFalse(evidence['visible_gap_certified'])
        self.assertAlmostEqual(contact['measurement_overlay']['signed_clearance_m'], .002)
        self.assertEqual([row['marker'] for row in contact['measurement_overlay']['object_markers']], ['A', 'B'])
        self.assertGreater(contact['scale_bar']['length_m'], 0)
        self.assertTrue(visual['measurement_overlay'])
        self.assertEqual(output.size, image.size)
        self.assertEqual(meta['views'][:3], visual['views'][:3])

    def test_annotations_cannot_make_a_flat_unreadable_surface_pass(self):
        image, meta, meshes, options = fixture()
        actual_raster = rasterize_attention
        def flat_surface(*args, **kwargs):
            color, depth, owners = actual_raster(*args, **kwargs)
            color[:] = (70, 70, 70)
            return color, depth, owners
        with patch('human_eye_plugin.attention_rendering.rasterize_attention', side_effect=flat_surface):
            output, visual, state = apply_attention_to_canvas(image, meta, meshes, **options)
        self.assertIsNone(state)
        self.assertIs(output, image)
        self.assertIn('candidate_surface_readability_insufficient', visual['attention']['reason_codes'])
        self.assertEqual(visual['attention']['readability']['contrasting_boundary_pixels'], [0, 0])

    def test_optional_owner_buffer_is_actual_depth_winner_and_preserves_raster(self):
        _, _, meshes, options = fixture()
        proposal = __import__('human_eye_plugin.attention_policy', fromlist=['AttentionPolicy']).AttentionPolicy().propose(
            meshes, focal_id='part', reference_id='base', contacts=options['contacts'], scene_fingerprint='synthetic')
        view, projection, _, _ = _attention_camera(meshes, proposal['camera_plan'])
        color, depth = rasterize_attention(meshes, view, projection, 128)
        owned_color, owned_depth, owners = rasterize_attention(meshes, view, projection, 128, return_owner=True)
        np.testing.assert_array_equal(color, owned_color)
        np.testing.assert_array_equal(depth, owned_depth)
        np.testing.assert_array_equal(np.isfinite(depth), owners >= 0)
        self.assertTrue(set(np.unique(owners)) <= {-1, 0, 1})

    def test_scene_owner_window_matches_independent_full_buffer_tracking(self):
        meshes = dispersed_meshes()[:2] + dispersed_meshes()[2:3]
        for kind, direction, axes in (('orthographic', [0, 0, 1], 'XY'),
                                      ('perspective', [2.4, -3.2, 2.4], None)):
            with self.subTest(kind=kind):
                view, projection, _ = _camera('work', meshes, meshes[:2], 128, kind, direction, axes)
                color, depth, owners = _raster_with_owners(_SceneRasterizer(128), meshes, view, projection, 128)
                reference_color = np.full((128, 128, 3), (18, 22, 30), dtype=np.uint8)
                reference_depth = np.full((128, 128), np.inf)
                reference_owner = np.full((128, 128), -1, dtype=np.int32)
                raster = _SceneRasterizer(128)
                for index, mesh in enumerate(meshes):
                    previous = reference_depth.copy()
                    raster._rasterize_meshes_zbuffer(reference_color, reference_depth, [mesh], view, projection,
                        is_foveal_micro_view=False, foveal_xray_focus_world=None)
                    reference_owner[reference_depth < previous] = index
                np.testing.assert_array_equal(color, reference_color)
                np.testing.assert_array_equal(depth, reference_depth)
                np.testing.assert_array_equal(owners, reference_owner)


if __name__ == '__main__':
    unittest.main()

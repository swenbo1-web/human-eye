"""Operation-local prepared render inputs save cloning without cross-frame trust."""
import copy
import json
import pickle
import unittest
from unittest.mock import patch

import numpy as np
from PIL import ImageDraw

from human_eye_plugin.auto_router import _validated_scene
from human_eye_plugin.attention_rendering import apply_attention_to_canvas
from human_eye_plugin.scene_rendering import (
    _finalize_prepared_scene_q4, _render_inputs, _render_scene_canvas_prepared,
    _render_view, finalize_scene_q4, render_scene_canvas,
)
from verification.test_attention_rendering import fixture, near_scene
from verification.test_visual_readability import dispersed_meshes


def prepare(meshes, fingerprint, size=128):
    return _render_scene_canvas_prepared(meshes, size, focal_id='part', reference_id='base',
                                         scene_fingerprint=fingerprint)


def finish(image, metadata, token, fingerprint):
    return _finalize_prepared_scene_q4(image, metadata, token, scene_fingerprint=fingerprint)


class PreparedRenderInputsTests(unittest.TestCase):
    def test_one_normalization_and_clone_for_a_complete_hundred_object_fallback(self):
        meshes = dispersed_meshes()
        expected, expected_meta = render_scene_canvas(meshes, 64, focal_id='part', reference_id='base', defer_q4=True)
        expected, expected_meta = finalize_scene_q4(expected, expected_meta, meshes)
        with patch('human_eye_plugin.scene_rendering._render_inputs', wraps=_render_inputs) as inputs:
            image, meta, token = prepare(meshes, 'current-100-object-snapshot', 64)
            output, visual = finish(image, meta, token, 'current-100-object-snapshot')
        self.assertEqual(inputs.call_count, 1)
        np.testing.assert_array_equal(np.asarray(expected), np.asarray(output))
        self.assertEqual(expected_meta, visual)
        self.assertEqual(json.dumps(expected_meta), json.dumps(visual))
        self.assertEqual(visual['views'][3]['occlusion_object_ids'], [m.object_id for m in meshes])

    def test_public_legacy_finalization_still_uses_its_supplied_mesh_contract(self):
        _, _, meshes, _ = fixture()
        with patch('human_eye_plugin.scene_rendering._render_inputs', wraps=_render_inputs) as inputs:
            image, meta = render_scene_canvas(meshes, 128, focal_id='part', reference_id='base', defer_q4=True)
            finalize_scene_q4(image, meta, meshes)
        self.assertEqual(inputs.call_count, 2)

    def test_prepared_fallback_does_not_call_normalizer_again(self):
        expected, expected_meta, meshes, options = fixture()
        image, meta, token = prepare(meshes, options['scene_fingerprint'])
        with patch('human_eye_plugin.scene_rendering._render_inputs', side_effect=AssertionError('duplicate clone')):
            output, visual = finish(image, meta, token, options['scene_fingerprint'])
        np.testing.assert_array_equal(np.asarray(expected), np.asarray(output))
        self.assertEqual(expected_meta, {k:v for k,v in visual.items() if k!='raster_schedule'})

    def test_attention_hold_diagnostics_are_allowed_without_weakening_camera_binding(self):
        expected, _, meshes, options = fixture()
        image, meta, token = prepare(meshes, options['scene_fingerprint'])
        options['contacts'] = []
        held_image, held_meta, state = apply_attention_to_canvas(image, meta, meshes, **options)
        self.assertIsNone(state)
        self.assertIsNot(held_meta, meta)
        output, visual = finish(held_image, held_meta, token, options['scene_fingerprint'])
        self.assertEqual(visual['attention']['decision'], 'hold')
        self.assertTrue(visual['raster_schedule']['canvas_complete'])
        np.testing.assert_array_equal(np.asarray(expected), np.asarray(output))
        self.assertFalse(meta['raster_schedule']['canvas_complete'])

    def test_confirmed_contact_needs_no_fallback_and_matches_public_canvas(self):
        image, metadata, meshes, options = fixture()
        with patch('human_eye_plugin.attention_rendering.time.perf_counter', return_value=0.):
            expected, old_meta, old_state = apply_attention_to_canvas(image, metadata, meshes, **options)
            image, meta, token = prepare(meshes, options['scene_fingerprint'])
            with patch('human_eye_plugin.scene_rendering._render_view', wraps=_render_view) as default_view:
                output, visual, state = apply_attention_to_canvas(image, meta, meshes, **options)
            default_view.assert_not_called()
        self.assertIsNotNone(state)
        self.assertEqual(state, old_state)
        self.assertEqual(visual['views'], old_meta['views'])
        np.testing.assert_array_equal(np.asarray(expected), np.asarray(output))
        self.assertTrue(visual['raster_schedule']['canvas_complete'])

    def test_new_canvas_cannot_reuse_another_frames_token_even_with_identical_geometry(self):
        _, _, meshes, options = fixture()
        first, first_meta, token = prepare(meshes, options['scene_fingerprint'])
        second, second_meta, _ = prepare(meshes, options['scene_fingerprint'])
        with self.assertRaisesRegex(ValueError, 'different or modified canvas'):
            finish(second, second_meta, token, options['scene_fingerprint'])
        with self.assertRaisesRegex(ValueError, 'different or modified canvas'):
            finish(first.copy(), first_meta, token, options['scene_fingerprint'])

    def test_changed_geometry_with_same_revision_has_a_new_hash_and_cannot_finish_old_frame(self):
        value = near_scene()
        _, meshes, fingerprint = _validated_scene(value)
        image, meta, token = prepare(meshes, fingerprint)
        for point in value['meshes'][1]['vertices']:
            point[0] += .01
        _, _, updated_fingerprint = _validated_scene(value)
        self.assertNotEqual(fingerprint, updated_fingerprint)
        with patch('human_eye_plugin.scene_rendering._render_view') as raster:
            with self.assertRaisesRegex(ValueError, 'different current snapshot'):
                finish(image, meta, token, updated_fingerprint)
        raster.assert_not_called()

    def test_source_mutation_cannot_pollute_the_owned_original_snapshot(self):
        expected, _, meshes, options = fixture()
        image, meta, token = prepare(meshes, options['scene_fingerprint'])
        # Finishing this operation still represents the original snapshot. A
        # new current scene must use its newly validated hash (separate test).
        meshes[0].vertices[:] += 100
        meshes[1].mark_label = '#changed-after-prepare'
        output, _ = finish(image, meta, token, options['scene_fingerprint'])
        np.testing.assert_array_equal(np.asarray(expected), np.asarray(output))

    def test_fallback_owned_geometry_is_readonly_and_retains_the_enclosing_obstacle(self):
        expected, _, meshes, options = fixture(enclosed=True)
        original_writeable = [m.vertices.flags.writeable for m in meshes]
        image, meta, token = prepare(meshes, options['scene_fingerprint'])
        with patch('human_eye_plugin.scene_rendering._render_view', wraps=_render_view) as raster:
            output, visual = finish(image, meta, token, options['scene_fingerprint'])
        actual_meshes = raster.call_args.args[1]
        self.assertTrue(all(not m.vertices.flags.writeable and not m.faces.flags.writeable for m in actual_meshes))
        self.assertIn('enclosure', [m.object_id for m in actual_meshes])
        self.assertEqual(original_writeable, [m.vertices.flags.writeable for m in meshes])
        np.testing.assert_array_equal(np.asarray(expected), np.asarray(output))
        self.assertTrue(visual['views'][3]['all_supplied_geometry_participates_in_depth'])

    def test_mutated_camera_size_scope_or_labels_are_rejected_before_raster(self):
        _, _, meshes, options = fixture()
        image, original, token = prepare(meshes, options['scene_fingerprint'])
        variants = []
        value = copy.deepcopy(original); value['views'][3]['view_matrix'][0][3] += .1; variants.append(value)
        value = copy.deepcopy(original); value['quad_size'] = 256; variants.append(value)
        value = copy.deepcopy(original); value['views'][3]['occlusion_object_ids'] = ['part']; variants.append(value)
        value = copy.deepcopy(original); value['object_labels'][0]['stable_label'] = 'fake'; variants.append(value)
        value = copy.deepcopy(original); value['views'][0]['geometry_depth_pixels'] = 0; variants.append(value)
        for modified in variants:
            with self.subTest(modified=modified['quad_size']), patch('human_eye_plugin.scene_rendering._render_view') as raster:
                with self.assertRaisesRegex(ValueError, 'metadata was modified'):
                    finish(image, modified, token, options['scene_fingerprint'])
                raster.assert_not_called()

    def test_ordinary_pillow_pixel_mutations_invalidate_the_canvas_binding(self):
        _, _, meshes, options = fixture()
        for method in ('putpixel', 'paste', 'draw'):
            image, meta, token = prepare(meshes, options['scene_fingerprint'])
            if method == 'putpixel': image.putpixel((20,20),(1,2,3))
            elif method == 'paste': image.paste((1,2,3),(0,0,10,10))
            else: ImageDraw.Draw(image).point((20,20),fill=(1,2,3))
            with self.subTest(method=method), self.assertRaisesRegex(ValueError, 'modified canvas'):
                finish(image, meta, token, options['scene_fingerprint'])

    def test_pixel_access_is_readonly_and_token_cannot_be_serialized_or_forged(self):
        _, _, meshes, options = fixture()
        image, meta, token = prepare(meshes, options['scene_fingerprint'])
        with self.assertRaises(ValueError): image.load()[20,20] = (1,2,3)
        for operation in (copy.copy, copy.deepcopy, pickle.dumps, json.dumps):
            with self.subTest(operation=operation), self.assertRaises(TypeError): operation(token)
        with self.assertRaises(AttributeError): token.scene_fingerprint = 'different'
        with self.assertRaises(TypeError): finish(image, meta, {'verified':True}, options['scene_fingerprint'])
        self.assertEqual(json.loads(json.dumps(meta,allow_nan=False)),meta)

    def test_completion_consumes_internal_token_without_changing_public_idempotence(self):
        _, _, meshes, options = fixture()
        image, meta, token = prepare(meshes, options['scene_fingerprint'])
        with patch('human_eye_plugin.scene_rendering._render_view', wraps=_render_view) as raster:
            output, visual = finish(image, meta, token, options['scene_fingerprint'])
            with self.assertRaisesRegex(ValueError,'already completed'):
                finish(output, visual, token, options['scene_fingerprint'])
        self.assertEqual(raster.call_count,1)
        again,same=finalize_scene_q4(output,visual,meshes)
        self.assertIs(again,output)
        self.assertIs(same,visual)
        with self.assertRaisesRegex(ValueError,'already completed'):
            finish(image,meta,token,options['scene_fingerprint'])
        output.putpixel((20,20),(1,2,3))
        with self.assertRaisesRegex(ValueError,'already completed'):
            finish(output,visual,token,options['scene_fingerprint'])

    def test_failed_fallback_does_not_publish_or_mutate_a_partially_completed_canvas(self):
        expected, _, meshes, options = fixture()
        image, meta, token = prepare(meshes, options['scene_fingerprint'])
        before=np.asarray(image).copy(); metadata_before=copy.deepcopy(meta)
        with patch('human_eye_plugin.scene_rendering._render_view', side_effect=ValueError('raster budget')):
            with self.assertRaisesRegex(ValueError,'raster budget'):
                finish(image,meta,token,options['scene_fingerprint'])
        np.testing.assert_array_equal(before,np.asarray(image))
        self.assertEqual(meta,metadata_before)
        self.assertFalse(meta['raster_schedule']['canvas_complete'])
        output,_=finish(image,meta,token,options['scene_fingerprint'])
        np.testing.assert_array_equal(np.asarray(expected),np.asarray(output))

    def test_resource_limits_still_apply_before_any_clone_or_prepared_object(self):
        _, _, meshes, options = fixture()
        with patch('human_eye_plugin.scene_rendering.work_budget_status', return_value={'within_budget':False}), \
             patch('human_eye_plugin.scene_rendering.MeshEntity3D.from_dict', side_effect=AssertionError('clone before budget')):
            with self.assertRaisesRegex(ValueError,'resource budget'):
                prepare(meshes,options['scene_fingerprint'])


if __name__=='__main__':
    unittest.main()

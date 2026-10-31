"""Adversarial coverage of operation-local caption layout, independent of RGB."""
from __future__ import annotations

import copy
import pickle
import unittest
from unittest.mock import patch

import numpy as np
from PIL import ImageDraw

from human_eye_plugin import scene_rendering as rendering
from human_eye_plugin.attention_rendering import (_annotate_orthogonal_target_measurement,
                                                _orthogonal_caption_contact)
from verification.test_complex_scene_quality import fixture
from verification.test_orthogonal_contact_visual import caption_fixture, copy_options


class CaptionLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = caption_fixture(size=256)

    def annotate(self, value=None, *, image=None, metadata=None, options=None):
        original, facts, meshes, args = value or self.fixture
        return _annotate_orthogonal_target_measurement(
            original if image is None else image,
            facts if metadata is None else metadata,
            meshes, **(args if options is None else options))

    def assert_retained(self, value):
        image, metadata, *_ = value
        pixels, facts = np.asarray(image).copy(), copy.deepcopy(metadata)
        with patch('human_eye_plugin.attention_rendering._orthogonal_caption_contact',
                   side_effect=AssertionError('Rejected layouts must skip witnesses')) as witness:
            output, visual = self.annotate(value)
        self.assertIs(output, image)
        self.assertIs(visual, metadata)
        np.testing.assert_array_equal(np.asarray(output), pixels)
        self.assertEqual(visual, facts)
        witness.assert_not_called()

    def test_safe_real_fixture_captions_only_inside_interior_rectangle(self):
        image, metadata, *_ = self.fixture
        output, visual = self.annotate()
        box = visual['views'][3]['measurement_overlay']['caption_box_px']
        self.assertEqual(box, [1, 227, 255, 255])
        changed = np.any(np.asarray(output) != np.asarray(image), axis=2)
        allowed = np.zeros(changed.shape, dtype=bool)
        allowed[256+box[1]:256+box[3], 256+box[0]:256+box[2]] = True
        self.assertTrue(changed.any())
        self.assertFalse(np.any(changed & ~allowed))
        self.assertEqual(visual['views'][3]['measurement_overlay']['caption_layout_source'],
                         'current_depth_and_drawn_annotations_empty_interior_band')
        target = copy.deepcopy(visual['views'][3]);target.pop('measurement_overlay')
        self.assertEqual(target, metadata['views'][3])

    def test_frame_border_pixels_are_preserved(self):
        image, *_ = self.fixture
        output, _ = self.annotate()
        before, after = np.asarray(image)[256:, 256:], np.asarray(output)[256:, 256:]
        for first, second in ((before[0], after[0]), (before[-1], after[-1]),
                              (before[:, 0], after[:, 0]), (before[:, -1], after[:, -1])):
            np.testing.assert_array_equal(first, second)

    def test_title_labels_and_original_surface_pixels_are_preserved(self):
        image, metadata, *_ = self.fixture
        output, _ = self.annotate()
        before, after = np.asarray(image)[256:, 256:], np.asarray(output)[256:, 256:]
        np.testing.assert_array_equal(before[:17], after[:17])
        for label in metadata['views'][3]['projected_labels']:
            x0,y0,x1,y1=label['label_box_px']
            np.testing.assert_array_equal(before[y0:y1+1,x0:x1+1], after[y0:y1+1,x0:x1+1])

    def test_missing_opaque_layout_token_is_not_replaced_by_claimed_json(self):
        image, metadata, meshes, options = self.fixture
        args=copy_options(options);args.pop('prepared_render')
        facts=copy.deepcopy(metadata)
        facts['caption_region']=[1,227,255,255]
        facts['views'][3]['safe_caption_region']=[1,227,255,255]
        self.assert_retained((image,facts,meshes,args))

    def test_fake_token_with_lookalike_method_cannot_supply_region(self):
        class Fake:
            def _caption_inputs(self,*args):return ((1,227,255,255), ())
        image, metadata, meshes, options = self.fixture
        args=copy_options(options);args['prepared_render']=Fake()
        self.assert_retained((image,metadata,meshes,args))

    def test_copy_of_complete_canvas_cannot_replay_original_token(self):
        image, metadata, meshes, options = self.fixture
        self.assert_retained((image.copy(),metadata,meshes,options))

    def test_identical_separate_frame_cannot_replay_another_token(self):
        other=caption_fixture(size=256)
        args=copy_options(other[3]);args['prepared_render']=self.fixture[3]['prepared_render']
        np.testing.assert_array_equal(np.asarray(self.fixture[0]),np.asarray(other[0]))
        self.assert_retained((*other[:3],args))

    def test_modified_canvas_including_other_quadrant_invalidates_layout(self):
        image, metadata, meshes, options=caption_fixture(size=256)
        image.putpixel((2,40),(255,0,255))
        self.assert_retained((image,metadata,meshes,options))

    def test_same_pixel_pillow_write_still_invalidates_layout(self):
        image, metadata, meshes, options=caption_fixture(size=256)
        image.putpixel((2,40),image.getpixel((2,40)))
        self.assert_retained((image,metadata,meshes,options))

    def test_draw_mutation_invalidates_current_core(self):
        image, metadata, meshes, options=caption_fixture(size=256)
        ImageDraw.Draw(image).line((1,20,10,20),fill=(0,0,0))
        self.assert_retained((image,metadata,meshes,options))

    def test_finished_layout_pixels_are_readonly(self):
        image, *_=caption_fixture(size=256)
        pixels=image.load()
        with self.assertRaises(ValueError):
            pixels[0,0]=(0,0,0)

    def test_finished_layout_token_cannot_be_copied_or_persisted(self):
        token=self.fixture[3]['prepared_render']
        for operation in (copy.copy,copy.deepcopy,pickle.dumps):
            with self.subTest(operation=operation.__name__), self.assertRaises(TypeError):
                operation(token)

    def test_camera_metadata_mutation_invalidates_layout_before_witness_work(self):
        image, metadata, meshes, options=self.fixture
        facts=copy.deepcopy(metadata);facts['views'][3]['target_plane_m_per_pixel']*=2
        self.assert_retained((image,facts,meshes,options))

    def test_new_unbound_metadata_field_cannot_authorize_current_layout(self):
        image, metadata, meshes, options=self.fixture
        facts=copy.deepcopy(metadata);facts['safe_caption_region']=[1,227,255,255]
        self.assert_retained((image,facts,meshes,options))

    def test_label_metadata_mutation_invalidates_layout(self):
        image, metadata, meshes, options=self.fixture
        facts=copy.deepcopy(metadata);facts['views'][3]['projected_labels'][0]['label_box_px']=[0,0,1,1]
        self.assert_retained((image,facts,meshes,options))

    def test_pending_token_has_no_completed_layout(self):
        image, metadata, meshes, options=self.fixture
        _,_,pending=rendering._render_scene_canvas_prepared(meshes,256,
            focal_id=options['focal_id'],reference_id=options['reference_id'],scene_fingerprint='pending-fixture')
        args=copy_options(options);args['prepared_render']=pending
        self.assert_retained((image,metadata,meshes,args))

    def test_captioning_does_not_rasterize_or_rebuild_protected_mask(self):
        with patch.object(rendering,'_raster_with_owners',side_effect=AssertionError), \
             patch.object(rendering,'_empty_caption_region',side_effect=AssertionError):
            _,visual=self.annotate()
        self.assertTrue(visual['measurement_overlay'])

    def test_small_views_skip_layout_and_witness_work(self):
        for size in (64,128,255):
            with self.subTest(size=size):
                value=caption_fixture(size=size)
                with patch('human_eye_plugin.attention_rendering._prepared_caption_inputs',side_effect=AssertionError):
                    self.assert_retained(value)

    def raster_fixture(self, depth_pixel=True, owner_pixel=True):
        def synthetic(rasterizer,meshes,view,projection,size):
            color=np.empty((size,size,3),dtype=np.uint8);color[:]=(18,22,30)
            depth=np.full((size,size),np.inf)
            owners=np.full((size,size),-1,dtype=np.int32)
            if depth_pixel:depth[size-5,20]=1.
            if owner_pixel:owners[size-5,20]=0
            return color,depth,owners
        # The mock changes raster evidence without changing any RGB pixel in
        # the candidate band; it deliberately challenges colour-only guards.
        with patch.object(rendering,'_raster_with_owners',side_effect=synthetic):
            return caption_fixture(size=256)

    def test_surface_with_background_rgb_is_protected_by_depth_and_owner(self):
        self.assert_retained(self.raster_fixture())

    def test_finite_depth_is_protected_even_when_owner_is_missing(self):
        self.assert_retained(self.raster_fixture(owner_pixel=False))

    def test_owner_is_protected_even_when_depth_is_nonfinite(self):
        self.assert_retained(self.raster_fixture(depth_pixel=False))

    def test_drawn_label_box_crossing_band_is_protected(self):
        with patch.object(rendering,'_label_box',return_value=(10,228,75,242)):
            value=caption_fixture(size=256)
        self.assertTrue(value[1]['views'][3]['projected_labels'])
        self.assert_retained(value)

    def test_leader_crossing_band_without_label_box_overlap_is_protected(self):
        def synthetic(rasterizer,meshes,view,projection,size):
            color=np.empty((size,size,3),dtype=np.uint8);color[:]=(18,22,30)
            depth=np.full((size,size),np.inf);owners=np.full((size,size),-1,dtype=np.int32)
            depth[-1,100:108]=1.;owners[-1,100:108]=0
            return color,depth,owners
        with patch.object(rendering,'_raster_with_owners',side_effect=synthetic), \
             patch.object(rendering,'_label_box',return_value=(10,180,75,194)):
            value=caption_fixture(size=256)
        label=value[1]['views'][3]['projected_labels'][0]
        self.assertLess(label['label_box_px'][3],227)
        self.assertGreater(label['projected_center_px'][1],254)
        self.assert_retained(value)

    def test_empty_real_footer_caption_preserves_strict_value_and_no_authority(self):
        _,visual=self.annotate()
        caption=visual['views'][3]['measurement_overlay']
        self.assertEqual(caption['signed_clearance_m'],.019)
        self.assertFalse(caption['camera_changed'])
        self.assertFalse(caption['execution_authority'])
        self.assertFalse(caption['visible_gap_certified'])

    def test_oversized_glyphs_skip_instead_of_drawing_outside_region(self):
        image,metadata,*_=self.fixture
        with patch.object(ImageDraw.ImageDraw,'textbbox',return_value=(0,0,999,999)):
            output,visual=self.annotate()
        self.assertIs(output,image);self.assertIs(visual,metadata)

    def moved_fixture(self, dx):
        value=fixture('square_hole')
        for mesh in value['scene']['meshes']:
            if mesh['object_id']==value['focal']:
                mesh['vertices']=[[x+dx,y,z]for x,y,z in mesh['vertices']]
        with patch('verification.test_orthogonal_contact_visual.fixture',return_value=value):
            return caption_fixture(size=256)

    def test_19mm_stale_mesh_and_contact_cannot_caption_current_1mm_frame(self):
        current=self.moved_fixture(.018)
        self.assertAlmostEqual(current[3]['contact']['signed_clearance_m'],.001)
        image,metadata=current[:2]
        args=copy_options(self.fixture[3]);args['prepared_render']=current[3]['prepared_render']
        self.assert_retained((image,metadata,self.fixture[2],args))

    def test_stale_witness_on_current_surface_still_rejects_old_geometry(self):
        current=self.moved_fixture(.008)
        self.assertAlmostEqual(current[3]['contact']['signed_clearance_m'],.011)
        old=self.fixture[3]
        # Here both stale endpoints still lie on original current surfaces,
        # but their 19mm segment is not the current nearest 11mm gap.
        self.assertIsNotNone(_orthogonal_caption_contact(old['contact'],current[2],
            old['focal_id'],old['reference_id']))
        args=copy_options(old);args['prepared_render']=current[3]['prepared_render']
        self.assert_retained((current[0],current[1],self.fixture[2],args))

    def test_copied_equal_geometry_remains_acceptable_without_rehashing(self):
        image,metadata,meshes,options=self.fixture
        copied=[type(mesh).from_dict(mesh.to_dict())for mesh in meshes]
        output,visual=self.annotate((image,metadata,copied,options))
        self.assertIsNot(output,image);self.assertTrue(visual['measurement_overlay'])

    def test_mesh_list_order_does_not_change_the_bound_geometry_set(self):
        image,metadata,meshes,options=self.fixture
        _,visual=self.annotate((image,metadata,list(reversed(meshes)),options))
        self.assertTrue(visual['measurement_overlay'])

    def test_changed_world_vertices_invalidate_bound_geometry_before_witness_work(self):
        image,metadata,meshes,options=self.fixture
        copied=[type(mesh).from_dict(mesh.to_dict())for mesh in meshes]
        copied[0].vertices[0,0]+=.000001
        self.assert_retained((image,metadata,copied,options))

    def test_changed_faces_invalidate_bound_geometry_before_witness_work(self):
        image,metadata,meshes,options=self.fixture
        copied=[type(mesh).from_dict(mesh.to_dict())for mesh in meshes]
        copied[0].faces[0]=copied[0].faces[0][::-1]
        self.assert_retained((image,metadata,copied,options))

    def test_omitted_or_duplicate_mesh_ids_cannot_reuse_layout(self):
        image,metadata,meshes,options=self.fixture
        for supplied in (meshes[:-1],[meshes[0]]*len(meshes)):
            with self.subTest(length=len(supplied)):
                self.assert_retained((image,metadata,supplied,options))

    def test_non_mesh_objects_cannot_reuse_bound_layout(self):
        image,metadata,meshes,options=self.fixture
        self.assert_retained((image,metadata,[object()for _ in meshes],options))


if __name__=='__main__':
    unittest.main()

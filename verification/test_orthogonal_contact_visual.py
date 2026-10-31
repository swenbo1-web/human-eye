"""Strict orthogonal caption evidence without camera or execution authority."""
from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin.auto_router import HumanEyeAutoRouter, _validated_scene
from human_eye_plugin.attention_rendering import (
    _annotate_orthogonal_target_measurement, _orthogonal_caption_contact)
from human_eye_plugin.scene_rendering import (
    _render_scene_canvas_prepared, _finalize_prepared_scene_q4)
from verification.test_complex_scene_quality import fixture, observe, decode


def caption_fixture(name='square_hole', size=256):
    value = fixture(name)
    _, meshes, fingerprint = _validated_scene(value['scene'])
    observed = observe(value)
    facts = json.loads(observed['context_text'])
    contact = {'object_id': value['reference'], **facts['measurement']}
    canvas, metadata, prepared = _render_scene_canvas_prepared(meshes, size,
        focal_id=value['focal'], reference_id=value['reference'], scene_fingerprint=fingerprint)
    metadata['attention'] = {'decision':'hold', 'reason_codes':['no_proven_projected_sampling_gain']}
    canvas, metadata = _finalize_prepared_scene_q4(canvas, metadata, prepared,
                                                scene_fingerprint=fingerprint)
    return canvas, metadata, meshes, dict(focal_id=value['focal'],
                                        reference_id=value['reference'], contact=contact,
                                        prepared_render=prepared)


def copy_options(options):
    return {key: (value if key == 'prepared_render' else copy.deepcopy(value))
            for key, value in options.items()}


class OrthogonalContactCaptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.square = caption_fixture()
        cls.slot = caption_fixture('L_slot')

    def call(self, value=None, change=None, metadata_change=None):
        image, original, meshes, options = value or self.square
        metadata = copy.deepcopy(original)
        options = copy_options(options)
        if change:
            change(options['contact'])
        if metadata_change:
            metadata_change(metadata)
        output, visual = _annotate_orthogonal_target_measurement(image, metadata, meshes, **options)
        return output, visual, image, metadata, meshes, options

    def assert_rejected(self, change=None, metadata_change=None):
        output, visual, image, metadata, *_ = self.call(change=change, metadata_change=metadata_change)
        self.assertIs(output, image)
        self.assertIs(visual, metadata)
        self.assertFalse(visual['measurement_overlay'])

    def test_square_hole_caption_uses_current_unrounded_clearance(self):
        out, visual, *_ = self.call()
        overlay = visual['views'][3]['measurement_overlay']
        self.assertEqual(overlay['signed_clearance_m'], .019)
        self.assertIn('MEASURED 19 mm', overlay['caption_lines'])
        self.assertFalse(overlay['visible_gap_certified'])
        self.assertFalse(overlay['camera_changed'])
        self.assertFalse(overlay['execution_authority'])
        self.assertFalse(overlay['independent_ground_truth'])
        self.assertEqual(out.mode, 'RGB')

    def test_L_slot_caption_uses_exact_surface_witnesses(self):
        _, visual, _, _, _, options = self.call(value=self.slot)
        overlay = visual['views'][3]['measurement_overlay']
        self.assertEqual(overlay['signed_clearance_m'], .04)
        self.assertEqual(overlay['witness_points_world_m'], [options['contact'][k]
                         for k in ('point_a_world','point_b_world')])
        self.assertEqual(overlay['source'], 'current_original_full_mesh_surface_features')

    def test_only_default_q4_caption_band_pixels_change(self):
        output, visual, image, metadata, *_ = self.call()
        size = metadata['quad_size']
        top = visual['views'][3]['measurement_overlay']['caption_box_px'][1]
        a, b = np.asarray(output), np.asarray(image)
        np.testing.assert_array_equal(a[:size], b[:size])
        np.testing.assert_array_equal(a[size:, :size], b[size:, :size])
        np.testing.assert_array_equal(a[size:size+top, size:], b[size:size+top, size:])
        self.assertFalse(np.array_equal(a[size+top:, size:], b[size+top:, size:]))

    def test_camera_and_attention_decision_are_unchanged(self):
        _, visual, _, metadata, *_ = self.call()
        target = copy.deepcopy(visual['views'][3]);target.pop('measurement_overlay')
        self.assertEqual(target, metadata['views'][3])
        self.assertEqual(visual['attention'], metadata['attention'])
        self.assertEqual(visual['raster_schedule'], metadata['raster_schedule'])
        self.assertEqual(visual['focus_scope'], metadata['focus_scope'])

    def test_input_meshes_and_inputs_remain_unchanged(self):
        image, metadata, meshes, options = self.square
        old_pixels = np.array(image);old_metadata=copy.deepcopy(metadata)
        before=[copy.deepcopy(m.to_dict()) for m in meshes];old_options=copy_options(options)
        _annotate_orthogonal_target_measurement(image, metadata, meshes, **options)
        np.testing.assert_array_equal(np.asarray(image), old_pixels)
        self.assertEqual(metadata, old_metadata)
        self.assertEqual([m.to_dict() for m in meshes], before)
        self.assertEqual(options, old_options)

    def test_annotation_never_calls_camera_planner_or_rasterizer(self):
        with patch('human_eye_plugin.attention_rendering._attention_camera', side_effect=AssertionError), \
             patch('human_eye_plugin.attention_rendering.AttentionPolicy.propose', side_effect=AssertionError), \
             patch('human_eye_plugin.attention_rendering.rasterize_attention', side_effect=AssertionError):
            _, visual, *_ = self.call()
        self.assertTrue(visual['measurement_overlay'])

    def test_missing_current_reference_contact_is_rejected(self):
        self.assert_rejected(lambda c: c.update(object_id='different-reference'))

    def test_q4_must_show_same_pair_in_same_order(self):
        for ids in (['probe','nearest-other'],['square-ring','probe'],['probe'],[]):
            with self.subTest(ids=ids):
                self.assert_rejected(metadata_change=lambda m: m['views'][3].update(target_object_ids=ids))

    def test_accepted_attention_is_not_overwritten(self):
        for decision in ('applied','retained','propose','retain'):
            with self.subTest(decision=decision):
                self.assert_rejected(metadata_change=lambda m: m['attention'].update(decision=decision))

    def test_wrong_q4_name_is_not_relabelled(self):
        self.assert_rejected(metadata_change=lambda m: m['views'][3].update(name='Q4 CONTACT'))

    def test_pending_q4_is_not_annotated_or_marked_complete(self):
        self.assert_rejected(metadata_change=lambda m: m['raster_schedule'].update(canvas_complete=False))

    def test_preexisting_overlay_is_idempotently_retained(self):
        output, visual, _, _, meshes, options = self.call()
        same, meta = _annotate_orthogonal_target_measurement(output, visual, meshes, **options)
        self.assertIs(same, output);self.assertIs(meta, visual)

    def test_old_convex_method_does_not_activate_new_path(self):
        self.assert_rejected(lambda c: c.update(measurement_method='convex_components_sat'))

    def test_uncertified_and_lower_bound_measurements_are_rejected(self):
        for fields in ({'measurement_valid':False},{'clearance_exact':False},
                       {'measurement_kind':'lower_bound'},{'clearance_state':'unknown'}):
            with self.subTest(fields=fields):
                self.assert_rejected(lambda c:c.update(fields))

    def test_zero_negative_boolean_and_nonfinite_clearances_are_rejected(self):
        for value in (0.,-.001,True,float('nan'),float('inf'),-float('inf')):
            with self.subTest(value=value):
                self.assert_rejected(lambda c:c.update(signed_clearance_m=value))

    def test_escape_certificate_is_not_presented_as_positive_surface_gap(self):
        self.assert_rejected(lambda c:c.update(measurement_method='exact_orthogonal_cell_union_escape'))

    def test_penetrating_pair_is_not_annotated(self):
        self.assert_rejected(lambda c:c.update(is_penetrating=True))

    def test_strict_geometry_must_match_scalar_method_and_validity(self):
        for fields in ({'measurement_method':'convex_components_sat'},{'measurement_valid':False},
                       {'signed_clearance_m':.02},{'signed_clearance_m':True},{'is_penetrating':True}):
            with self.subTest(fields=fields):
                self.assert_rejected(lambda c:c['strict_geometry'].update(fields))

    def test_display_probe_or_internal_faces_are_not_witness_sources(self):
        self.assert_rejected(lambda c:c.update(witness_source='legacy_display_probe'))
        self.assert_rejected(lambda c:c['strict_geometry'].update(witness_scope='internal_cell_face'))

    def test_strict_and_summary_witness_mismatch_is_rejected(self):
        self.assert_rejected(lambda c:c.update(point_b_world=[.025,0,0]))

    def test_same_wrong_witness_off_original_surface_is_rejected(self):
        def change(c):
            a=np.array(c['point_a_world']);b=np.array(c['point_b_world'])
            a[2]+=.000123;b[2]+=.000123
            # Original chosen witnesses may lie on a vertical side. Shift into
            # the probe interior as well, while retaining their vector length.
            a[0]+=.000123;b[0]+=.000123
            for field,value in [('point_a_world',a.tolist()),('point_b_world',b.tolist())]:
                c[field]=value;c['strict_geometry'][field]=value
        self.assert_rejected(change)

    def test_boolean_or_nonfinite_witness_coordinates_are_rejected(self):
        for value in ([True,0.,0.],[float('nan'),0.,0.],[float('inf'),0.,0.],['0',0.,0.]):
            with self.subTest(value=value):
                self.assert_rejected(lambda c:c.update(point_a_world=value))

    def test_witness_segment_must_match_strict_distance(self):
        def change(c):
            c['signed_clearance_m']=.018;c['strict_geometry']['signed_clearance_m']=.018
        self.assert_rejected(change)

    def test_legitimate_display_diagnostic_does_not_override_strict_value(self):
        _, visual, *_ = self.call(change=lambda c:c['legacy_display'].update(
            alignment_state='ALIGNED_FLUSH',display_signed_clearance_m=0))
        self.assertEqual(visual['views'][3]['measurement_overlay']['signed_clearance_m'],.019)

    def test_supported_sizes_keep_numeric_metadata_unrounded(self):
        for size in (256,384,512):
            with self.subTest(size=size):
                _, visual, *_ = self.call(value=caption_fixture(size=size))
                overlay=visual['views'][3]['measurement_overlay']
                self.assertEqual(overlay['signed_clearance_m'],.019)
                self.assertTrue(any('MEASURED' in line for line in overlay['caption_lines']))
                self.assertFalse(overlay['dimension_line_drawn'])

    def test_small_views_keep_original_pixels_and_metadata_without_witness_work(self):
        for size in (64,128,255):
            with self.subTest(size=size):
                image, metadata, meshes, options = caption_fixture(size=size)
                pixels = np.array(image)
                original_metadata = copy.deepcopy(metadata)
                with patch('human_eye_plugin.attention_rendering._orthogonal_caption_contact',
                           side_effect=AssertionError('Small views must skip caption validation')) as witness:
                    output, visual = _annotate_orthogonal_target_measurement(
                        image, metadata, meshes, **options)
                witness.assert_not_called()
                self.assertIs(output, image)
                self.assertIs(visual, metadata)
                np.testing.assert_array_equal(np.asarray(output), pixels)
                self.assertEqual(visual, original_metadata)
                self.assertFalse(visual['measurement_overlay'])


class OrthogonalContactRouterTests(unittest.TestCase):
    def test_hole_and_L_hold_without_gain_but_show_strict_caption(self):
        for name in ('square_hole','L_slot'):
            with self.subTest(name=name):
                result=observe(fixture(name),router=HumanEyeAutoRouter(quad_size=256),include_image=True)
                facts=json.loads(result['context_text']);canvas=facts['canvas']
                self.assertEqual(facts['attention']['decision'],'hold')
                self.assertEqual(facts['attention']['reason_codes'],['no_proven_projected_sampling_gain'])
                self.assertEqual(canvas['views'][3]['name'],'Q4 TARGET')
                self.assertEqual(canvas['raster_schedule']['final_q4'],'target')
                self.assertEqual(canvas['views'][3]['measurement_overlay']['signed_clearance_m'],
                                 facts['measurement']['signed_clearance_m'])
                self.assertEqual(decode(result).size,(512,512))

    def test_text_only_observation_does_not_render_caption(self):
        with patch('human_eye_plugin.auto_router._annotate_orthogonal_target_measurement') as caption:
            result=observe(fixture('square_hole'),include_image=False)
        caption.assert_not_called()
        self.assertIsNone(result['image'])

    def test_unknown_oblique_concavity_never_gets_promoted_for_visuals(self):
        value=fixture('L_slot')
        for mesh in value['scene']['meshes']:
            if mesh['object_id']==value['reference']:
                mesh['vertices']=[[x+.125*z,y,z] for x,y,z in mesh['vertices']]
        with patch('human_eye_plugin.auto_router._annotate_orthogonal_target_measurement')as caption:
            result=observe(value,include_image=True)
        caption.assert_not_called()
        self.assertIn('reference_pair_geometry_unknown',result['reason_codes'])
        self.assertIsNone(result['image'])

    def test_convex_observation_never_uses_new_membership_checks(self):
        with patch('human_eye_plugin.attention_rendering._point_triangle_min_sq',side_effect=AssertionError):
            result=observe(fixture('thin_25um'),include_image=True)
        facts=json.loads(result['context_text'])
        self.assertEqual(facts['measurement']['clearance_state'],'positive_clearance')
        self.assertIn('image',result)

    def test_old_whole_observation_contract_is_invalidated(self):
        value=fixture('square_hole');router=HumanEyeAutoRouter(quad_size=256)
        observe(value,router=router,include_image=True)
        state=router.export_state()
        state['sessions'][0][1]['observation']['contract_revision']='v1-orthogonal-solids-precise-presentation-20261024'
        other=HumanEyeAutoRouter(quad_size=256);other.import_state(state)
        updated=observe(value,router=other,include_image=True)
        self.assertFalse(updated['cache_hit'])
        self.assertTrue(json.loads(updated['context_text'])['canvas']['measurement_overlay'])

    def test_repeat_whole_observation_retains_caption_without_new_authority(self):
        value=fixture('square_hole');router=HumanEyeAutoRouter(quad_size=256)
        first=observe(value,router=router,include_image=True)
        second=observe(value,router=router,include_image=True)
        self.assertTrue(second['cache_hit'])
        self.assertEqual(first['image'],second['image'])
        overlay=json.loads(second['context_text'])['canvas']['views'][3]['measurement_overlay']
        self.assertFalse(overlay['execution_authority'])


if __name__=='__main__':
    unittest.main()

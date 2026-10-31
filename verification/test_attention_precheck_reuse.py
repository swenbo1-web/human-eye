"""Contract checks for operation-local prechecks; controlled clocks are not benchmarks."""
import copy
import json
import unittest
from unittest.mock import patch

import numpy as np
from PIL import ImageDraw

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin import attention_rendering as ar
from human_eye_plugin import scene_rendering as sr
from human_eye_plugin.attention_policy import AttentionPolicy, _plan_signature
from human_eye_plugin.auto_router import HumanEyeAutoRouter
from verification.test_attention_rendering import fixture, near_scene
from verification.test_auto_router import observation


def prepared_fixture(enclosed=False):
    _, _, meshes, options = fixture(enclosed=enclosed)
    image, metadata, token = sr._render_scene_canvas_prepared(meshes, 128,
        focal_id=options['focal_id'], reference_id=options['reference_id'],
        scene_fingerprint=options['scene_fingerprint'])
    return image, metadata, meshes, options, token


def apply(value, **extra):
    image, metadata, meshes, options, token = value
    return ar.apply_attention_to_canvas(image, metadata, meshes, **dict(options, **extra),
                                       prepared_render=token)


class AttentionPrecheckReuseTests(unittest.TestCase):
    def assert_rejected_before_work(self, value, reason='attention_prepared_inputs_invalid'):
        with patch.object(ar, '_attention_camera') as camera, \
             patch.object(ar, '_visible_witness') as ray, \
             patch.object(ar, 'rasterize_attention') as raster:
            output, visual, state = apply(value)
        self.assertIs(output, value[0]); self.assertIsNone(state)
        self.assertEqual(visual['attention']['reason_codes'], [reason])
        camera.assert_not_called(); ray.assert_not_called(); raster.assert_not_called()

    def test_owned_selected_candidate_builds_one_camera_and_two_rays(self):
        value = prepared_fixture()
        with patch.object(ar.time, 'perf_counter', return_value=0.), \
             patch.object(ar, '_attention_camera', wraps=ar._attention_camera) as camera, \
             patch.object(ar, '_visible_witness', wraps=ar._visible_witness) as ray, \
             patch.object(ar, 'rasterize_attention', wraps=ar.rasterize_attention) as raster:
            _, visual, state = apply(value)
        self.assertIsNotNone(state, visual['attention'])
        plan = visual['attention']['proposal']['camera_plan']
        selected_view = ar._attention_camera(value[2], plan)[0]
        self.assertEqual(camera.call_count, visual['attention']['proposal']['visibility_precheck_count'])
        self.assertEqual(sum(call.args[1] == plan for call in camera.call_args_list), 1)
        self.assertEqual(sum(np.array_equal(call.args[2], selected_view) for call in ray.call_args_list), 2)
        self.assertEqual(raster.call_count, 1)
        self.assertTrue(visual['attention']['precheck_reused'])
        self.assertTrue(visual['attention']['visibility_verified'])
        self.assertTrue(visual['attention']['readability_verified'])

    def test_public_no_token_path_still_recomputes(self):
        image, metadata, meshes, options = fixture()
        with patch.object(ar.time, 'perf_counter', return_value=0.), \
             patch.object(ar, '_attention_camera', wraps=ar._attention_camera) as camera, \
             patch.object(ar, '_visible_witness', wraps=ar._visible_witness) as ray:
            _, visual, state = ar.apply_attention_to_canvas(image, metadata, meshes, **options)
        self.assertIsNotNone(state)
        plan = visual['attention']['proposal']['camera_plan']
        selected_view = ar._attention_camera(meshes, plan)[0]
        self.assertEqual(camera.call_count, visual['attention']['proposal']['visibility_precheck_count'] + 1)
        self.assertEqual(sum(call.args[1] == plan for call in camera.call_args_list), 2)
        self.assertEqual(sum(np.array_equal(call.args[2], selected_view) for call in ray.call_args_list), 4)
        self.assertFalse(visual['attention']['precheck_reused'])

    def test_owned_and_public_paths_keep_pixels_plan_and_depth_evidence(self):
        image, metadata, meshes, options = fixture()
        value = prepared_fixture()
        with patch.object(ar.time, 'perf_counter', return_value=0.):
            expected, old_visual, old_state = ar.apply_attention_to_canvas(image, metadata, meshes, **options)
            output, visual, state = apply(value)
        np.testing.assert_array_equal(np.asarray(output), np.asarray(expected))
        self.assertEqual(visual['views'], old_visual['views'])
        self.assertEqual(state, old_state)
        for field in ('actual_projected_gap_px', 'witness_visible', 'raster_witness_supported',
                      'readability', 'net_gain_px'):
            self.assertEqual(visual['attention'][field], old_visual['attention'][field])

    def test_inputs_are_unmodified_and_metadata_is_serializable(self):
        value = prepared_fixture(); image, metadata, meshes, options, _ = value
        old_image = np.array(image); old_metadata = copy.deepcopy(metadata)
        old_meshes = [m.to_dict() for m in meshes]; old_options = copy.deepcopy(options)
        with patch.object(ar.time, 'perf_counter', return_value=0.):
            _, visual, _ = apply(value)
        np.testing.assert_array_equal(image, old_image)
        self.assertEqual(metadata, old_metadata); self.assertEqual(options, old_options)
        self.assertEqual([m.to_dict() for m in meshes], old_meshes)
        self.assertEqual(json.loads(json.dumps(visual, allow_nan=False)), visual)

    def test_actual_camera_ray_and_raster_use_operation_owned_readonly_geometry(self):
        value = prepared_fixture(); source = value[2]; seen = []
        original = ar.rasterize_attention
        def raster(meshes, *args, **kwargs):
            seen.extend(meshes)
            self.assertTrue(all(m is not s for m, s in zip(meshes, source)))
            self.assertTrue(all(not getattr(m, field).flags.writeable
                                for m in meshes for field in ('vertices','faces','edges','pivot_world')))
            return original(meshes, *args, **kwargs)
        with patch.object(ar.time, 'perf_counter', return_value=0.), \
             patch.object(ar, 'rasterize_attention', side_effect=raster):
            _, _, state = apply(value)
        self.assertIsNotNone(state); self.assertEqual(len(seen), len(source))

    def test_equivalent_mesh_copies_can_bind_the_same_current_render(self):
        value = list(prepared_fixture())
        value[2] = [MeshEntity3D.from_dict(m.to_dict()) for m in value[2]]
        with patch.object(ar.time, 'perf_counter', return_value=0.):
            _, visual, state = apply(value)
        self.assertIsNotNone(state); self.assertTrue(visual['attention']['precheck_reused'])

    def test_foreign_token_with_same_scene_and_ids_is_rejected(self):
        value = list(prepared_fixture()); other = prepared_fixture(); value[4] = other[4]
        self.assert_rejected_before_work(value)

    def test_copied_canvas_cannot_borrow_current_token(self):
        value = list(prepared_fixture()); value[0] = value[0].copy()
        self.assert_rejected_before_work(value)

    def test_ordinary_pillow_mutation_detaches_the_bound_core(self):
        value = prepared_fixture(); ImageDraw.Draw(value[0]).point((20,20), fill=(1,2,3))
        self.assert_rejected_before_work(value)

    def test_metadata_camera_scope_size_and_label_mutations_are_rejected(self):
        for change in (lambda m:m['views'][3]['view_matrix'][0].__setitem__(3,.1),
                       lambda m:m.update(quad_size=256),
                       lambda m:m['views'][3].update(occlusion_object_ids=['part']),
                       lambda m:m['object_labels'][0].update(stable_label='invented')):
            value = list(prepared_fixture()); value[1] = copy.deepcopy(value[1]); change(value[1])
            with self.subTest(change=change):self.assert_rejected_before_work(value)

    def test_same_fingerprint_does_not_hide_source_vertex_changes(self):
        value = prepared_fixture(); value[2][0].vertices[0,0] += .01
        self.assert_rejected_before_work(value)

    def test_same_ids_do_not_hide_source_face_changes(self):
        value = prepared_fixture(); value[2][0].faces[0] = value[2][0].faces[1]
        self.assert_rejected_before_work(value)

    def test_source_color_change_cannot_borrow_old_readability(self):
        value = prepared_fixture(); value[2][0].color_rgb = (18,22,30)
        self.assert_rejected_before_work(value)

    def test_other_render_inputs_and_order_must_match(self):
        changes = [lambda m:m[0].edges.__setitem__((0,0),1),
                   lambda m:m[0].pivot_world.__setitem__(0,.1),
                   lambda m:setattr(m[0],'mark_label','changed'),
                   lambda m:setattr(m[0],'name','changed'),lambda m:m.reverse()]
        for change in changes:
            value = list(prepared_fixture()); change(value[2])
            with self.subTest(change=change):self.assert_rejected_before_work(value)

    def test_changed_scene_fingerprint_is_rejected_despite_identical_geometry(self):
        value = list(prepared_fixture()); value[3] = dict(value[3], scene_fingerprint='new-frame')
        self.assert_rejected_before_work(value)

    def test_json_claim_is_not_an_opaque_render_token(self):
        value = list(prepared_fixture()); value[4] = {'verified':True,'scene_fingerprint':value[3]['scene_fingerprint']}
        self.assert_rejected_before_work(value)

    def test_completed_render_cannot_start_a_precheck_operation(self):
        value = list(prepared_fixture())
        value[0], value[1] = sr._finalize_prepared_scene_q4(value[0],value[1],value[4],
                                                scene_fingerprint=value[3]['scene_fingerprint'])
        self.assert_rejected_before_work(value)

    def test_pending_token_can_be_claimed_for_attention_only_once(self):
        value = prepared_fixture()
        with patch.object(ar.time, 'perf_counter', return_value=0.):apply(value)
        self.assert_rejected_before_work(value)

    def test_empty_contact_hold_consumes_only_attention_claim_not_fallback(self):
        value = list(prepared_fixture()); value[3] = dict(value[3],contacts=[])
        with patch.object(ar.time, 'perf_counter', return_value=0.):
            image, visual, state = apply(value)
        self.assertIsNone(state)
        output, finished = sr._finalize_prepared_scene_q4(image,visual,value[4],
                                                scene_fingerprint=value[3]['scene_fingerprint'])
        self.assertTrue(finished['raster_schedule']['canvas_complete'])
        expected, *_ = fixture()
        np.testing.assert_array_equal(output, expected)

    def test_source_mutation_after_callback_prevents_reuse_and_raster(self):
        value = prepared_fixture(); original = AttentionPolicy.propose
        def propose(policy, *args, **kwargs):
            result = original(policy,*args,**kwargs)
            value[2][0].vertices[0,0] += .01
            return result
        with patch.object(ar.time,'perf_counter',return_value=0.), \
             patch.object(AttentionPolicy,'propose',new=propose), \
             patch.object(ar,'rasterize_attention') as raster:
            output,visual,state=apply(value)
        self.assertIs(output,value[0]); self.assertIsNone(state); raster.assert_not_called()
        self.assertEqual(visual['attention']['reason_codes'],['attention_prepared_inputs_changed'])

    def test_source_color_mutation_after_callback_cannot_commit_old_colors(self):
        value = prepared_fixture(); original = AttentionPolicy.propose
        def propose(policy,*args,**kwargs):
            result=original(policy,*args,**kwargs);value[2][0].color_rgb=(70,70,70);return result
        with patch.object(ar.time,'perf_counter',return_value=0.), \
             patch.object(AttentionPolicy,'propose',new=propose), \
             patch.object(ar,'rasterize_attention') as raster:
            _,visual,state=apply(value)
        self.assertIsNone(state);raster.assert_not_called()
        self.assertEqual(visual['attention']['reason_codes'],['attention_prepared_inputs_changed'])

    def test_metadata_mutation_after_callback_is_not_reused(self):
        value = prepared_fixture();original=AttentionPolicy.propose
        def propose(policy,*args,**kwargs):
            result=original(policy,*args,**kwargs);value[1]['views'][0]['name']='changed';return result
        with patch.object(ar.time,'perf_counter',return_value=0.), \
             patch.object(AttentionPolicy,'propose',new=propose), \
             patch.object(ar,'rasterize_attention') as raster:
            _,visual,state=apply(value)
        self.assertIsNone(state);raster.assert_not_called()
        self.assertEqual(visual['attention']['reason_codes'],['attention_prepared_inputs_changed'])

    def test_complete_plan_extra_nested_value_change_requires_fresh_precheck(self):
        value=prepared_fixture();original=AttentionPolicy.propose
        def propose(policy,*args,**kwargs):
            result=original(policy,*args,**kwargs)
            result['camera_plan']['extra_current_detail']={'nested':[1,2,3]}
            result['plan_signature']=_plan_signature(result['camera_plan'])
            return result
        with patch.object(ar.time,'perf_counter',return_value=0.), \
             patch.object(AttentionPolicy,'propose',new=propose), \
             patch.object(ar,'_attention_camera',wraps=ar._attention_camera) as camera, \
             patch.object(ar,'_visible_witness',wraps=ar._visible_witness) as ray:
            _,visual,state=apply(value)
        self.assertIsNotNone(state);self.assertFalse(visual['attention']['precheck_reused'])
        self.assertEqual(camera.call_count,visual['attention']['proposal']['visibility_precheck_count']+1)
        selected_view=ar._attention_camera(value[2],visual['attention']['proposal']['camera_plan'])[0]
        self.assertEqual(sum(np.array_equal(call.args[2],selected_view)for call in ray.call_args_list),4)

    def test_mutated_witness_plan_must_not_reuse_old_ray_results(self):
        value=prepared_fixture();original=AttentionPolicy.propose
        def propose(policy,*args,**kwargs):
            result=original(policy,*args,**kwargs)
            result['camera_plan']['witness_points_world_m'][0][0]+=.0001
            result['plan_signature']=_plan_signature(result['camera_plan'])
            return result
        with patch.object(ar.time,'perf_counter',return_value=0.), \
             patch.object(AttentionPolicy,'propose',new=propose), \
             patch.object(ar,'_attention_camera',wraps=ar._attention_camera) as camera:
            _,visual,_=apply(value)
        self.assertFalse(visual['attention']['precheck_reused'])
        self.assertEqual(camera.call_count,visual['attention']['proposal']['visibility_precheck_count']+1)

    def test_only_last_fully_successful_visibility_candidate_is_reused(self):
        value=prepared_fixture();original=ar._visible_witness;count=[0]
        def ray(*args,**kwargs):
            count[0]+=1
            return False if count[0]==1 else original(*args,**kwargs)
        with patch.object(ar.time,'perf_counter',return_value=0.), \
             patch.object(ar,'_visible_witness',side_effect=ray), \
             patch.object(ar,'_attention_camera',wraps=ar._attention_camera) as camera:
            _,visual,state=apply(value)
        self.assertIsNotNone(state);self.assertTrue(visual['attention']['precheck_reused'])
        self.assertEqual(camera.call_count,visual['attention']['proposal']['visibility_precheck_count'])
        self.assertGreater(camera.call_count,1)

    def test_failed_partial_callback_does_not_supply_a_success_memo(self):
        value=prepared_fixture();original=AttentionPolicy.propose
        def propose(policy,*args,**kwargs):
            callback=kwargs.pop('candidate_visible')
            result=original(policy,*args,**kwargs)
            callback(result['camera_plan'])
            return result
        with patch.object(ar.time,'perf_counter',return_value=0.), \
             patch.object(AttentionPolicy,'propose',new=propose), \
             patch.object(ar,'_visible_witness',return_value=False) as ray, \
             patch.object(ar,'_attention_camera',wraps=ar._attention_camera) as camera, \
             patch.object(ar,'rasterize_attention') as raster:
            _,visual,state=apply(value)
        self.assertIsNone(state);self.assertFalse(visual['attention']['precheck_reused'])
        self.assertEqual(camera.call_count,2);self.assertEqual(ray.call_count,3);raster.assert_not_called()

    def test_exact_pre_raster_budget_boundary_is_a_conservative_abort(self):
        original=AttentionPolicy.propose
        for elapsed in (.04,.040001,.1):
            value=prepared_fixture();clock=[0.]
            def propose(policy,*args,**kwargs):
                result=original(policy,*args,**kwargs);clock[0]=elapsed;return result
            with self.subTest(elapsed=elapsed),patch.object(ar.time,'perf_counter',side_effect=lambda:clock[0]), \
                 patch.object(AttentionPolicy,'propose',new=propose), \
                 patch.object(ar,'rasterize_attention') as raster, \
                 patch.object(ar,'_readability_evidence') as readability:
                output,visual,state=apply(value)
            self.assertIs(output,value[0]);self.assertIsNone(state)
            self.assertTrue(visual['attention']['aborted_before_raster'])
            self.assertFalse(visual['attention']['raster_performed'])
            self.assertFalse(visual['attention']['visibility_verified'])
            self.assertFalse(visual['attention']['readability_verified'])
            self.assertIsNone(visual['attention']['readability'])
            self.assertIsNone(visual['attention']['raster_witness_supported'])
            self.assertAlmostEqual(visual['attention']['additional_cost_ms'],elapsed*1000)
            raster.assert_not_called();readability.assert_not_called()

    def test_just_below_budget_can_rasterize_and_confirm(self):
        value=prepared_fixture();clock=[0.];original=AttentionPolicy.propose
        def propose(policy,*args,**kwargs):
            result=original(policy,*args,**kwargs);clock[0]=.039999;return result
        with patch.object(ar.time,'perf_counter',side_effect=lambda:clock[0]), \
             patch.object(AttentionPolicy,'propose',new=propose), \
             patch.object(ar,'rasterize_attention',wraps=ar.rasterize_attention) as raster:
            _,visual,state=apply(value)
        self.assertIsNotNone(state);self.assertEqual(raster.call_count,1)
        self.assertFalse(visual['attention']['aborted_before_raster'])

    def test_post_raster_exact_forty_ms_confirmation_gate_is_unchanged(self):
        value=prepared_fixture();clock=[0.];original=ar.rasterize_attention
        def raster(*args,**kwargs):
            result=original(*args,**kwargs);clock[0]=.04;return result
        with patch.object(ar.time,'perf_counter',side_effect=lambda:clock[0]), \
             patch.object(ar,'rasterize_attention',side_effect=raster):
            _,visual,state=apply(value)
        self.assertIsNotNone(state);self.assertEqual(visual['attention']['additional_cost_ms'],40.)

    def test_raster_overrun_still_rejects_after_measured_work(self):
        value=prepared_fixture();clock=[0.];original=ar.rasterize_attention
        def raster(*args,**kwargs):
            result=original(*args,**kwargs);clock[0]=.040001;return result
        with patch.object(ar.time,'perf_counter',side_effect=lambda:clock[0]), \
             patch.object(ar,'rasterize_attention',side_effect=raster) as calls:
            output,visual,state=apply(value)
        self.assertIsNone(state);self.assertIs(output,value[0]);self.assertEqual(calls.call_count,1)
        self.assertIn('attention_additional_compute_budget_exceeded',visual['attention']['reason_codes'])
        self.assertFalse(visual['attention']['aborted_before_raster'])

    def test_owned_geometry_validation_cost_is_inside_original_timer(self):
        value=prepared_fixture();clock=[0.];original=ar._claim_prepared_attention_inputs
        def claim(*args,**kwargs):
            result=original(*args,**kwargs);clock[0]=.041;return result
        with patch.object(ar.time,'perf_counter',side_effect=lambda:clock[0]), \
             patch.object(ar,'_claim_prepared_attention_inputs',side_effect=claim), \
             patch.object(ar,'_attention_camera') as camera, \
             patch.object(ar,'rasterize_attention') as raster:
            _,visual,state=apply(value)
        self.assertIsNone(state);camera.assert_not_called();raster.assert_not_called()
        self.assertTrue(visual['attention']['aborted_before_raster'])
        self.assertAlmostEqual(visual['attention']['additional_cost_ms'],41.)

    def test_pre_raster_abort_keeps_default_finalization_available(self):
        value=prepared_fixture();original=AttentionPolicy.propose;clock=[0.]
        def propose(policy,*args,**kwargs):
            result=original(policy,*args,**kwargs);clock[0]=.041;return result
        with patch.object(ar.time,'perf_counter',side_effect=lambda:clock[0]), \
             patch.object(AttentionPolicy,'propose',new=propose):
            image,visual,state=apply(value)
        self.assertIsNone(state);self.assertFalse(visual['raster_schedule']['canvas_complete'])
        output,final=sr._finalize_prepared_scene_q4(image,visual,value[4],
                                                scene_fingerprint=value[3]['scene_fingerprint'])
        expected,*_=fixture();np.testing.assert_array_equal(output,expected)
        self.assertTrue(final['raster_schedule']['canvas_complete'])

    def test_empty_depth_and_low_readability_still_cannot_commit(self):
        original=ar.rasterize_attention
        for mode in ('empty','low_contrast'):
            value=prepared_fixture()
            def raster(*args,**kwargs):
                color,depth,owners=original(*args,**kwargs)
                if mode=='empty':depth[:]=np.inf;owners[:]=-1
                else:color[:]=(70,70,70)
                return color,depth,owners
            with self.subTest(mode=mode),patch.object(ar.time,'perf_counter',return_value=0.), \
                 patch.object(ar,'rasterize_attention',side_effect=raster):
                output,visual,state=apply(value)
            self.assertIsNone(state);self.assertIs(output,value[0])
            self.assertTrue(visual['attention']['precheck_reused'])

    def test_fully_enclosed_scene_remains_a_hold_without_xray(self):
        value=prepared_fixture(enclosed=True)
        with patch.object(ar.time,'perf_counter',return_value=0.), \
             patch.object(ar,'rasterize_attention') as raster:
            output,visual,state=apply(value)
        self.assertIs(output,value[0]);self.assertIsNone(state);raster.assert_not_called()
        self.assertEqual(visual['attention']['decision'],'hold')

    def test_router_supplies_token_but_text_only_does_not_plan(self):
        original=ar.apply_attention_to_canvas
        with patch('human_eye_plugin.auto_router.apply_attention_to_canvas',wraps=original) as renderer:
            result=HumanEyeAutoRouter(quad_size=128).handle_event(observation(scene=near_scene()))
        self.assertEqual(renderer.call_count,1)
        self.assertIsNotNone(renderer.call_args.kwargs.get('prepared_render'))
        self.assertEqual(json.loads(result['context_text'])['measurement']['clearance_state'],'positive_clearance')
        with patch('human_eye_plugin.auto_router.apply_attention_to_canvas') as renderer:
            HumanEyeAutoRouter(quad_size=128).handle_event(observation(scene=near_scene(),include_image=False))
        renderer.assert_not_called()


if __name__=='__main__':unittest.main()

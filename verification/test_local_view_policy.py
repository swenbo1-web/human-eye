"""Gain-confirmed local views preserve the original observation and occlusion."""
import copy
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin.local_view import append_gain_local_view, local_view_clock, _readable_focus
from human_eye_plugin.scene_rendering import render_scene_canvas
from human_eye_plugin.task_labels import build_task_label_plan
from verification.test_auto_router import box


def as_mesh(identity, center, size, color):
    row=box(identity,center,size,identity=='part')
    row['color_rgb']=list(color)
    return MeshEntity3D.from_dict(row)


def nav_scene():
    meshes=[as_mesh('base',[0,0,-.02],[.14,.12,.04],[120,120,120]),
            as_mesh('part',[0,0,.024],[.06,.05,.04],[30,50,210])]
    ids=[]
    for i,(x,y) in enumerate([(-.6,-1.),(0,-1.),(.6,-1.),(-.6,1.),(0,1.),(.6,1.)]):
        identity='peripheral-'+str(i);ids.append(identity)
        meshes.append(as_mesh(identity,[x,y,.025],[.12,.12,.05],[30,180,80]))
    return meshes,ids


def rendered(meshes, ids, size=256):
    plan=build_task_label_plan(meshes,focal_id='part',reference_id='base',
        visual_focus_ids=ids,scene_revision='local-test-r1',scene_fingerprint='snapshot')
    canvas,meta=render_scene_canvas(meshes,size,focal_id='part',reference_id='base',label_plan=plan)
    return canvas,meta


def append(canvas,meta,meshes,**changes):
    kwargs={'scene_fingerprint':'snapshot','remaining_budget_ms':40.}
    kwargs.update(changes)
    return append_gain_local_view(canvas,meta,meshes,**kwargs)


class LocalViewPolicyTests(unittest.TestCase):
    def controlled_readability(self, *, contrast=24, side=4, top=50, damage=False):
        meshes=[as_mesh('base',[0,0,0],[1,1,1],[80,80,80]),
                as_mesh('part',[0,0,.6],[.1]*3,[80+contrast,80,80])]
        plan=build_task_label_plan(meshes,focal_id='part',reference_id='base',
                                  visual_focus_ids=['part'],scene_fingerprint='snapshot')
        color=np.full((128,128,3),80,dtype=np.uint8)
        color[top:top+side,50:50+side]=[80+contrast,80,80]
        owners=np.zeros((128,128),dtype=np.int32)
        owners[top:top+side,50:50+side]=1
        depth=np.ones((128,128))
        picture=Image.fromarray(color.copy());draw=ImageDraw.Draw(picture)
        box=[70,30,83,44]
        draw.rectangle(box,fill=(18,22,30),outline=(150,145,110))
        draw.text((73,30),'A',fill=(255,245,180))
        row={'object_id':'part','display_label':'A','label_box_px':box,
             'projected_center_px':[51,top+1]}
        if damage:
            mask=Image.new('L',(128,128));ImageDraw.Draw(mask).text((73,30),'A',fill=255)
            ys,xs=np.nonzero(np.asarray(mask)>0);picture.putpixel((int(xs[0]),int(ys[0])),(0,0,0))
        return _readable_focus(picture,(color,depth,owners),{'projected_labels':[row]},
                               meshes,{'part'},plan)

    def test_exact_contrast_and_surface_thresholds_are_not_legacy_eight_pixel_labels(self):
        readable,evidence=self.controlled_readability(contrast=23)
        self.assertEqual(readable,[]);self.assertEqual(evidence[0]['contrasting_boundary_pixels'],0)
        readable,evidence=self.controlled_readability(contrast=24)
        self.assertEqual(readable,['part']);self.assertEqual(evidence[0]['visible_surface_pixels'],16)
        readable,evidence=self.controlled_readability(contrast=24,side=3)
        self.assertEqual(readable,[]);self.assertEqual(evidence[0]['visible_surface_pixels'],9)

    def test_title_pixels_cannot_fill_surface_quota_and_real_row17_pixels_can(self):
        readable,evidence=self.controlled_readability(top=0)
        self.assertEqual(readable,[]);self.assertEqual(evidence[0]['visible_surface_pixels'],0)
        self.assertFalse(evidence[0]['anchor_exact_owner'])
        readable,evidence=self.controlled_readability(top=17)
        self.assertEqual(readable,['part']);self.assertTrue(evidence[0]['anchor_exact_owner'])

    def test_final_glyph_damage_rejects_otherwise_readable_surface(self):
        readable,evidence=self.controlled_readability(damage=True)
        self.assertEqual(readable,[]);self.assertFalse(evidence[0]['complete_final_glyph'])

    def test_bound_monotonic_clock_is_independent_of_stdlib_attribute_mock(self):
        with patch('time.perf_counter',return_value=-123.):
            self.assertGreaterEqual(local_view_clock(),0.)

    def test_missing_NAV_identity_recovers_with_same_original_pixels_roles_and_metadata(self):
        meshes,ids=nav_scene();canvas,meta=rendered(meshes,ids)
        before=copy.deepcopy(meta);mesh_before=[mesh.to_dict() for mesh in meshes]
        original=np.asarray(canvas).copy()
        base_drawn={r['object_id'] for v in meta['views'] for r in v['projected_labels']}
        initial_missing=sorted(set(ids)-base_drawn)
        # Q1 alone misses three southern objects; another original view
        # already shows the middle one, so it must never count as new gain.
        self.assertEqual(initial_missing,[ids[0],ids[2]])
        with patch('human_eye_plugin.local_view.local_view_clock',return_value=0.):
            out,visual,receipt=append(canvas,meta,meshes)
        self.assertTrue(receipt['applied'],receipt)
        self.assertEqual(receipt['candidate_raster_count'],1)
        self.assertEqual(receipt['new_readable_object_ids'],initial_missing)
        self.assertEqual(receipt['still_missing_ids'],[])
        self.assertEqual(out.size,(640,512))
        self.assertTrue(np.array_equal(np.asarray(out)[:,:512],original))
        self.assertEqual(meta,before)
        self.assertEqual(visual['views'],before['views'])
        self.assertEqual(visual['object_labels'],before['object_labels'])
        self.assertEqual([mesh.to_dict() for mesh in meshes],mesh_before)
        local=visual['supplemental_views'][0]
        self.assertEqual(local['source_view_index'],0)
        self.assertEqual(local['panel_offset_px'],[512,0])
        self.assertEqual(local['panel_size_px'],[128,512])
        self.assertEqual(local['view_size_px'],[128,128])
        self.assertEqual(local['occlusion_object_ids'],[mesh.object_id for mesh in meshes])
        self.assertTrue(set(initial_missing).issubset(local['readable_focus_object_ids']))
        self.assertFalse(local['execution_authority'])

    def test_all_already_delivered_does_not_create_a_candidate_or_copy_originals(self):
        meshes,ids=nav_scene();canvas,meta=rendered(meshes,ids[3:])
        with patch('human_eye_plugin.local_view._render_view') as raster:
            out,visual,receipt=append(canvas,meta,meshes)
        self.assertIs(out,canvas);self.assertIs(visual,meta)
        self.assertFalse(receipt['applied']);self.assertEqual(receipt['candidate_raster_count'],0)
        self.assertEqual(receipt['reason'],'all_requested_identities_already_drawn')
        raster.assert_not_called()

    def test_no_visual_request_preserves_originals(self):
        meshes,_=nav_scene();canvas,meta=rendered(meshes,[])
        out,visual,receipt=append(canvas,meta,meshes)
        self.assertIs(out,canvas);self.assertIs(visual,meta)
        self.assertEqual(receipt['reason'],'no_explicit_visual_focus')

    def test_contact_section_priority_and_scene_binding(self):
        meshes,ids=nav_scene();canvas,meta=rendered(meshes,ids)
        for changes,reason in [({'diagnostic_requested':True},'existing_visual_diagnostic_requested'),
                               ({'scene_fingerprint':'new-frame'},'local_scene_binding_mismatch')]:
            with self.subTest(changes=changes),patch('human_eye_plugin.local_view._render_view') as raster:
                out,visual,receipt=append(canvas,meta,meshes,**changes)
                self.assertIs(out,canvas);self.assertIs(visual,meta)
                self.assertEqual(receipt['reason'],reason);raster.assert_not_called()

    def test_same_namespace_and_bounds_cannot_bind_changed_vertices_colour_or_role(self):
        for mutation in ['vertices','colour','role']:
            with self.subTest(mutation=mutation):
                meshes,ids=nav_scene();canvas,meta=rendered(meshes,ids)
                old_bounds=(meshes[2].bbox_min.copy(),meshes[2].bbox_max.copy())
                if mutation=='vertices':meshes[2].vertices[0,0]+=.001
                elif mutation=='colour':meshes[2].color_rgb=(1,2,3)
                else:meshes[2].is_focal_target=True
                self.assertTrue(np.array_equal(meshes[2].bbox_min,old_bounds[0]))
                self.assertTrue(np.array_equal(meshes[2].bbox_max,old_bounds[1]))
                with patch('human_eye_plugin.local_view._render_view') as raster, \
                        patch('human_eye_plugin.local_view.local_view_clock',return_value=0.):
                    out,visual,receipt=append(canvas,meta,meshes)
                self.assertIs(out,canvas);self.assertIs(visual,meta)
                self.assertEqual(receipt['reason'],'current_display_snapshot_changed')
                self.assertEqual(receipt['candidate_raster_count'],0);raster.assert_not_called()

    def test_tiny_original_and_bad_remaining_budget_never_raster(self):
        meshes,ids=nav_scene();tiny,meta=rendered(meshes,ids,96)
        out,visual,receipt=append(tiny,meta,meshes)
        self.assertIs(out,tiny);self.assertEqual(receipt['reason'],'original_view_too_small')
        canvas,meta=rendered(meshes,ids)
        for budget in [0.,-1.,None,True,float('nan'),float('inf')]:
            with self.subTest(budget=budget),patch('human_eye_plugin.local_view._render_view') as raster:
                out,visual,receipt=append(canvas,meta,meshes,remaining_budget_ms=budget)
                self.assertIs(out,canvas);self.assertIs(visual,meta)
                self.assertEqual(receipt['candidate_raster_count'],0);raster.assert_not_called()

    def test_fully_enclosed_regular_target_does_not_search_or_remove_occluder(self):
        meshes=[as_mesh('base',[0,0,0],[1,1,1],[120,120,120]),
                as_mesh('part',[0,0,0],[.08,.08,.04],[30,50,210])]
        canvas,meta=rendered(meshes,['part'])
        with patch('human_eye_plugin.local_view._render_view') as raster, \
                patch('human_eye_plugin.local_view._visible_witness') as witness:
            out,visual,receipt=append(canvas,meta,meshes)
        self.assertIs(out,canvas);self.assertEqual(receipt['candidate_raster_count'],0)
        self.assertEqual(receipt['reason'],'no_recoverable_local_source')
        raster.assert_not_called();witness.assert_not_called()

    def test_zero_sample_tiny_target_requires_a_real_full_scene_ray(self):
        meshes=[as_mesh('base',[0,0,0],[1,1,1],[120,120,120]),
                as_mesh('part',[0,0,.6],[1e-7]*3,[30,50,210])]
        canvas,meta=rendered(meshes,['part'])
        self.assertTrue(all(v['object_visible_pixels']['part']==0 for v in meta['views']))
        with patch('human_eye_plugin.local_view.local_view_clock',return_value=0.):
            out,visual,receipt=append(canvas,meta,meshes)
        self.assertTrue(receipt['applied'],receipt)
        self.assertEqual(receipt['new_readable_object_ids'],['part'])
        self.assertTrue(receipt['tiny_surface_prechecks'][0]['confirmed'])
        self.assertEqual(visual['supplemental_views'][0]['occlusion_object_ids'],['base','part'])

    def test_large_original_views_remain_unchanged_with_bounded_128_local_panel(self):
        for size in [256,384,512]:
            with self.subTest(source_size=size):
                meshes=[as_mesh('base',[0,0,0],[1,1,1],[120,120,120]),
                        as_mesh('part',[0,0,.6],[1e-7]*3,[30,50,210])]
                canvas,meta=rendered(meshes,['part'],size)
                original_pixels=np.asarray(canvas).copy();original_meta=copy.deepcopy(meta)
                with patch('human_eye_plugin.local_view.local_view_clock',return_value=0.):
                    output,visual,receipt=append(canvas,meta,meshes)
                self.assertTrue(receipt['applied'],receipt)
                self.assertEqual(receipt['candidate_raster_count'],1)
                self.assertEqual(receipt['new_readable_object_ids'],['part'])
                self.assertEqual(output.size,(2*size+128,2*size))
                self.assertTrue(np.array_equal(np.asarray(output)[:,:2*size],original_pixels))
                self.assertEqual(meta,original_meta)
                self.assertEqual(visual['views'],original_meta['views'])
                self.assertEqual(visual['quad_size'],size)
                self.assertEqual(visual['natural_canvas_size'],[2*size,2*size])
                local=visual['supplemental_views'][0]
                self.assertEqual(local['view_size_px'],[128,128])
                self.assertEqual(local['panel_offset_px'],[2*size,0])
                self.assertEqual(local['panel_size_px'],[128,2*size])

    def test_zero_sample_tiny_enclosed_target_ray_blocks_raster(self):
        meshes=[as_mesh('base',[0,0,0],[1,1,1],[120,120,120]),
                as_mesh('part',[0,0,0],[1e-7]*3,[30,50,210])]
        canvas,meta=rendered(meshes,['part'])
        with patch('human_eye_plugin.local_view._render_view') as raster, \
                patch('human_eye_plugin.local_view.local_view_clock',return_value=0.):
            out,visual,receipt=append(canvas,meta,meshes)
        self.assertIs(out,canvas);self.assertFalse(receipt['applied'])
        self.assertEqual(receipt['reason'],'tiny_surface_witness_unconfirmed')
        self.assertEqual(receipt['candidate_raster_count'],0)
        self.assertFalse(receipt['tiny_surface_prechecks'][0]['confirmed']);raster.assert_not_called()

    def test_spent_cooperative_budget_does_not_adopt_after_real_raster(self):
        meshes,ids=nav_scene();canvas,meta=rendered(meshes,ids)
        from human_eye_plugin.local_view import _render_view as actual_render
        spent=[False]
        def draw(*args,**kwargs):
            result=actual_render(*args,**kwargs);spent[0]=True;return result
        def clock():return .02 if spent[0] else 0.
        with patch('human_eye_plugin.local_view.local_view_clock',side_effect=clock), \
                patch('human_eye_plugin.local_view._render_view',side_effect=draw):
            out,visual,receipt=append(canvas,meta,meshes)
        self.assertIs(out,canvas);self.assertIs(visual,meta)
        self.assertEqual(receipt['candidate_raster_count'],1)
        self.assertEqual(receipt['reason'],'local_budget_exhausted_after_raster')
        self.assertFalse(receipt['applied']);self.assertGreater(receipt['additional_cost_ms'],10.)

    def test_optional_failure_preserves_original_objects_and_missing_identities(self):
        meshes,ids=nav_scene();canvas,meta=rendered(meshes,ids)
        with patch('human_eye_plugin.local_view._camera',side_effect=ValueError('candidate failure')):
            out,visual,receipt=append(canvas,meta,meshes)
        self.assertIs(out,canvas);self.assertIs(visual,meta)
        self.assertEqual(receipt['error_type'],'ValueError')
        self.assertEqual(receipt['still_missing_ids'],[ids[0],ids[2]]);self.assertFalse(receipt['applied'])


if __name__=='__main__':unittest.main()

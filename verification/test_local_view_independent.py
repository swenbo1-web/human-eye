"""Independent one-shot local-view readability, rollback and delivery boundaries."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

from human_eye_plugin import local_view
from human_eye_plugin.local_view import append_gain_local_view
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.task_brief import project_task_brief
from human_eye_plugin.task_labels import build_task_label_plan, task_display_label
from verification.test_label_coverage_delivery import ReadOnlyHost
from verification.test_local_view_policy import as_mesh, nav_scene, rendered
from verification.test_local_view_delivery import route, raw as raw_nav


def append(base, meta, meshes):
    return append_gain_local_view(base,meta,meshes,scene_fingerprint='snapshot',remaining_budget_ms=40.)


def readability_fixture(background=(80,80,80), first=(140,80,80), *, second=None, top=50):
    meshes=[as_mesh('base',[0,0,0],[1,1,1],[80,80,80]),
            as_mesh('part',[0,0,.6],[.1]*3,[140,80,80])]
    requested=['part']
    if second is not None:
        meshes.append(as_mesh('other',[.2,0,.6],[.1]*3,[85,80,80]));requested.append('other')
    plan=build_task_label_plan(meshes,focal_id='part',reference_id='base',
                              visual_focus_ids=requested,scene_fingerprint='snapshot')
    colors=np.empty((128,128,3),dtype=np.uint8);colors[:]=background
    colors[top:top+4,50:54]=first
    owners=np.zeros((128,128),dtype=np.int32);owners[top:top+4,50:54]=1
    depth=np.ones((128,128),dtype=np.float64)
    rows=[{'object_id':'part','display_label':'A','projected_center_px':[51,top+1],
           'label_box_px':[70,30,83,44]}]
    if second is not None:
        colors[80:84,20:24]=second;owners[80:84,20:24]=2
        alias=task_display_label('other',plan)
        width=ImageDraw.Draw(Image.new('RGB',(128,128))).textbbox((0,0),alias)[2]+6
        rows.append({'object_id':'other','display_label':alias,'projected_center_px':[21,81],
                     'label_box_px':[70,60,70+width,74]})
    picture=Image.fromarray(colors.copy());draw=ImageDraw.Draw(picture)
    for row in rows:
        box=row['label_box_px'];draw.rectangle(box,fill=(18,22,30),outline=(150,145,110))
        draw.text((box[0]+3,box[1]),row['display_label'],fill=(255,245,180))
    return picture,(colors,depth,owners),{'projected_labels':rows},meshes,set(requested),plan


class IndependentLocalViewTests(unittest.TestCase):
    def test_small_decreasing_uint8_difference_does_not_wrap_into_contrast(self):
        args=readability_fixture(background=(250,250,250),first=(245,250,250))
        readable,evidence=local_view._readable_focus(*args)
        self.assertEqual(readable,[])
        self.assertEqual(evidence[0]['visible_surface_pixels'],16)
        self.assertEqual(evidence[0]['contrasting_boundary_pixels'],0)

    def test_one_owner_boundary_pixel_does_not_count_as_multiple_neighbors(self):
        picture,(colors,depth,owners),view,meshes,requested,plan=readability_fixture(first=(80,80,80))
        colors[50,50]=(250,80,80)
        readable,evidence=local_view._readable_focus(picture,(colors,depth,owners),view,meshes,requested,plan)
        self.assertEqual(readable,[])
        self.assertEqual(evidence[0]['visible_surface_pixels'],16)
        self.assertEqual(evidence[0]['contrasting_boundary_pixels'],1)

    def test_readability_is_decided_per_identity_not_all_painted_aliases(self):
        args=readability_fixture(second=(85,80,80))
        readable,evidence=local_view._readable_focus(*args)
        by_id={row['object_id']:row for row in evidence}
        self.assertEqual(readable,['part'])
        self.assertTrue(by_id['part']['passed'])
        self.assertFalse(by_id['other']['passed'])
        self.assertTrue(by_id['other']['complete_final_glyph'])
        self.assertTrue(by_id['other']['anchor_exact_owner'])
        self.assertEqual(by_id['other']['contrasting_boundary_pixels'],0)

    def test_inconsistent_raw_depth_or_owner_namespace_cannot_certify_readability(self):
        for failure in ['depth','owner']:
            with self.subTest(failure=failure):
                picture,(colors,depth,owners),view,meshes,requested,plan=readability_fixture()
                if failure=='depth':depth[50,50]=float('nan')
                else:owners[50,50]=len(meshes)
                with self.assertRaises(ValueError):
                    local_view._readable_focus(picture,(colors,depth,owners),view,meshes,requested,plan)

    def test_raw_surface_in_final_scale_band_cannot_fill_readability_quota(self):
        readable,evidence=local_view._readable_focus(*readability_fixture(top=118))
        self.assertEqual(readable,[])
        self.assertEqual(evidence[0]['visible_surface_pixels'],0)
        self.assertFalse(evidence[0]['anchor_exact_owner'])

    def test_large_source_adds_capped_column_and_keeps_original_pixel_rectangle(self):
        for size in [256,384,512]:
            with self.subTest(size=size):
                meshes=[as_mesh('base',[0,0,0],[1,1,1],[120,120,120]),
                        as_mesh('part',[0,0,.6],[1e-7]*3,[30,50,210])]
                canvas,meta=rendered(meshes,['part'],size)
                before=copy.deepcopy(meta)
                with patch.object(local_view,'local_view_clock',return_value=0.):
                    out,visual,receipt=append(canvas,meta,meshes)
                self.assertTrue(receipt['applied'],receipt)
                self.assertEqual(out.size,(2*size+128,2*size))
                np.testing.assert_array_equal(np.asarray(out)[:,:2*size],np.asarray(canvas))
                self.assertEqual(visual['views'],before['views'])
                self.assertEqual(receipt['panel_offset_px'],[2*size,0])
                self.assertEqual(receipt['view_size_px'],[128,128])
                self.assertEqual(receipt['panel_size_px'],[128,2*size])
                self.assertAlmostEqual((out.width-canvas.width)/canvas.width,128/(2*size))
                self.assertFalse(receipt['execution_authority'])

    def test_already_appended_canvas_never_creates_a_second_candidate(self):
        meshes,ids=nav_scene();canvas,meta=rendered(meshes,ids)
        with patch.object(local_view,'local_view_clock',return_value=0.):
            out,visual,receipt=append(canvas,meta,meshes)
        self.assertTrue(receipt['applied'])
        with patch.object(local_view,'_render_view',side_effect=AssertionError('second raster')):
            again,again_meta,second=append(out,visual,meshes)
        self.assertIs(again,out);self.assertIs(again_meta,visual)
        self.assertFalse(second['applied']);self.assertEqual(second['candidate_raster_count'],0)
        self.assertEqual(second['reason'],'complete_unextended_canvas_required')

    def test_existing_diagnostic_supplement_or_deferred_Q4_blocks_raster_before_work(self):
        meshes,ids=nav_scene();canvas,meta=rendered(meshes,ids)
        for change in [{'diagnostic_panel':{'kind':'contact_section'}},
                       {'supplemental_views':[{'name':'already_here'}]},
                       {'raster_schedule':{'canvas_complete':False}}]:
            modified=copy.deepcopy(meta);modified.update(change)
            with self.subTest(change=change),patch.object(local_view,'_render_view') as raster:
                out,visual,receipt=append(canvas,modified,meshes)
                self.assertIs(out,canvas);self.assertIs(visual,modified)
                self.assertEqual(receipt['candidate_raster_count'],0)
                self.assertEqual(receipt['reason'],'complete_unextended_canvas_required')
                raster.assert_not_called()

    def test_face_or_pose_change_is_rejected_even_when_IDs_and_bounds_match(self):
        for mutation in ['faces','axes']:
            with self.subTest(mutation=mutation):
                meshes,ids=nav_scene();canvas,meta=rendered(meshes,ids)
                subject=meshes[2];old_bounds=(subject.bbox_min.copy(),subject.bbox_max.copy())
                if mutation=='faces':subject.faces=subject.faces[:,[0,2,1]].copy()
                else:subject.local_axes=np.array([[0.,1.,0.],[-1.,0.,0.],[0.,0.,1.]])
                np.testing.assert_array_equal(subject.bbox_min,old_bounds[0])
                np.testing.assert_array_equal(subject.bbox_max,old_bounds[1])
                with patch.object(local_view,'local_view_clock',return_value=0.), \
                     patch.object(local_view,'_render_view') as raster:
                    out,visual,receipt=append(canvas,meta,meshes)
                self.assertIs(out,canvas);self.assertIs(visual,meta)
                self.assertEqual(receipt['reason'],'current_display_snapshot_changed')
                raster.assert_not_called()

    def test_readability_cost_overrun_keeps_originals_and_incurred_raster(self):
        meshes,ids=nav_scene();canvas,meta=rendered(meshes,ids);before=copy.deepcopy(meta)
        actual=local_view._readable_focus;spent=[False]
        def measure(*args,**kwargs):
            value=actual(*args,**kwargs);spent[0]=True;return value
        with patch.object(local_view,'local_view_clock',side_effect=lambda:.011 if spent[0] else 0.), \
             patch.object(local_view,'_readable_focus',side_effect=measure):
            out,visual,receipt=append(canvas,meta,meshes)
        self.assertIs(out,canvas);self.assertIs(visual,meta);self.assertEqual(meta,before)
        self.assertFalse(receipt['applied']);self.assertEqual(receipt['candidate_raster_count'],1)
        self.assertEqual(receipt['reason'],'local_budget_exhausted_before_append')
        self.assertAlmostEqual(receipt['additional_cost_ms'],11.)

    def test_metadata_copy_overrun_discards_fully_composited_panel_atomically(self):
        meshes,ids=nav_scene();canvas,meta=rendered(meshes,ids);before=copy.deepcopy(meta)
        actual=copy.deepcopy;spent=[False]
        def clone(value,*args,**kwargs):
            result=actual(value,*args,**kwargs)
            if value is meta:spent[0]=True
            return result
        with patch.object(local_view,'local_view_clock',side_effect=lambda:.011 if spent[0] else 0.), \
             patch.object(local_view.copy,'deepcopy',side_effect=clone):
            out,visual,receipt=append(canvas,meta,meshes)
        self.assertIs(out,canvas);self.assertIs(visual,meta);self.assertEqual(meta,before)
        self.assertFalse(receipt['applied']);self.assertEqual(receipt['candidate_raster_count'],1)
        self.assertEqual(receipt['reason'],'local_budget_exhausted_before_commit')
        self.assertAlmostEqual(receipt['additional_cost_ms'],11.)

    def test_real_low_contrast_candidate_is_not_appended_despite_new_painted_labels(self):
        meshes,ids=nav_scene()
        for mesh in meshes[2:]:mesh.color_rgb=(18,22,30)
        canvas,meta=rendered(meshes,ids);before=copy.deepcopy(meta)
        actual_render=local_view._render_view;local_sizes=[]
        def record_render(*args,**kwargs):
            local_sizes.append(args[0].quad_size)
            return actual_render(*args,**kwargs)
        with patch.object(local_view,'local_view_clock',return_value=0.), \
             patch.object(local_view,'_render_view',side_effect=record_render):
            out,visual,receipt=append(canvas,meta,meshes)
        self.assertIs(out,canvas);self.assertIs(visual,meta);self.assertEqual(meta,before)
        self.assertEqual(receipt['candidate_raster_count'],1)
        self.assertEqual(receipt['reason'],'no_new_readable_identity')
        self.assertEqual(receipt['new_readable_object_ids'],[])
        self.assertEqual(receipt['still_missing_ids'],[ids[0],ids[2]])
        self.assertEqual(local_sizes,[128])

    def test_cap128_long_alias_crowding_never_promotes_unqualified_identities(self):
        meshes,ids=nav_scene()
        # These real SHA prefixes collide through seven hex characters,
        # forcing the full observation namespace to use nine-character R labels.
        replacements={ids[0]:'contact-edge-4375',ids[2]:'contact-edge-20515'}
        for mesh in meshes:
            if mesh.object_id in replacements:
                mesh.object_id=replacements[mesh.object_id]
                mesh.name=mesh.object_id;mesh.mark_label='#'+mesh.object_id
        requested=[replacements.get(identity,identity) for identity in ids]
        canvas,meta=rendered(meshes,requested)
        self.assertEqual(meta['task_labels']['related_alias_hex_chars'],8)
        base_drawn={row['object_id'] for view in meta['views'] for row in view['projected_labels']}
        missing=set(requested)-base_drawn
        self.assertTrue(missing)
        actual_render=local_view._render_view;rasters=[]
        def record_render(*args,**kwargs):
            picture=actual_render(*args,**kwargs)
            rasters.append((args[0].quad_size,args[1],kwargs['raw_evidence_out'][0]))
            return picture
        with patch.object(local_view,'local_view_clock',return_value=0.), \
             patch.object(local_view,'_render_view',side_effect=record_render):
            out,visual,receipt=append(canvas,meta,meshes)
        self.assertEqual(receipt['candidate_raster_count'],1)
        self.assertEqual(len(rasters),1);self.assertEqual(rasters[0][0],128)
        np.testing.assert_array_equal(np.asarray(out)[:,:512],np.asarray(canvas))
        if not receipt['applied']:
            self.assertIs(out,canvas);self.assertIs(visual,meta)
            self.assertEqual(receipt['reason'],'no_new_readable_identity')
            self.assertEqual(set(receipt['still_missing_ids']),missing)
            return
        self.assertEqual(out.size,(640,512))
        self.assertTrue(set(receipt['new_readable_object_ids']).issubset(missing))
        self.assertGreaterEqual(len(receipt['new_readable_object_ids']),1)
        local=visual['supplemental_views'][0];raw=rasters[0][2]
        colors,depth,owners=raw;current_meshes=rasters[0][1]
        by_id={mesh.object_id:i for i,mesh in enumerate(current_meshes)}
        rows={row['object_id']:row for row in local['projected_labels']}
        final_local=np.asarray(out)[:128,512:640]
        for identity in receipt['new_readable_object_ids']:
            row=rows[identity];owner_index=by_id[identity]
            x,y=row['projected_center_px']
            self.assertTrue(1<=x<127 and 17<=y<113)
            self.assertEqual(int(owners[y,x]),owner_index)
            self.assertTrue(np.isfinite(depth[y,x]))
            safe=np.zeros(owners.shape,dtype=bool);safe[17:113,1:127]=True
            selected=safe & (owners==owner_index)
            self.assertGreaterEqual(int(np.count_nonzero(selected)),16)
            unique_boundary=set()
            for py,px in zip(*np.nonzero(selected)):
                for dy,dx in [(0,-1),(0,1),(-1,0),(1,0)]:
                    ny,nx=py+dy,px+dx
                    if safe[ny,nx] and owners[ny,nx]!=owner_index:
                        delta=colors[py,px].astype(float)-colors[ny,nx].astype(float)
                        if float(np.linalg.norm(delta))>=24:
                            unique_boundary.add((int(px),int(py)))
            self.assertGreaterEqual(len(unique_boundary),4)
            x0,y0,x1,y1=row['label_box_px']
            expected=Image.new('RGB',(x1-x0+1,y1-y0+1),(18,22,30))
            draw=ImageDraw.Draw(expected);draw.rectangle((0,0,expected.width-1,expected.height-1),
                fill=(18,22,30),outline=(150,145,110))
            draw.text((3,0),row['display_label'],fill=(255,245,180))
            alpha=Image.new('L',expected.size);ImageDraw.Draw(alpha).text((3,0),row['display_label'],fill=255)
            glyph=np.asarray(alpha)>0
            self.assertTrue(glyph.any())
            np.testing.assert_array_equal(final_local[y0:y1+1,x0:x1+1][glyph],np.asarray(expected)[glyph])

    def test_direct_helper_exception_keeps_known_elapsed_but_unknown_raster_count(self):
        with patch('human_eye_plugin.auto_router.append_gain_local_view',side_effect=RuntimeError('direct fault')), \
             patch('human_eye_plugin.auto_router.local_view_clock',side_effect=[0.,.010,.016]):
            value=route()
        facts=json.loads(value['context_text']);receipt=facts['local_view']
        self.assertFalse(receipt['applied']);self.assertEqual(receipt['reason'],'local_view_unavailable')
        self.assertAlmostEqual(receipt['current_event_local_view_cost_ms'],6.)
        self.assertIsNone(receipt['candidate_raster_count'])
        self.assertIsNone(receipt['attempted'])
        self.assertTrue(receipt['unknown_attempt_or_raster_count_is_not_zero'])
        self.assertEqual(receipt['still_missing_ids'],['peripheral-0','peripheral-2'])
        self.assertNotIn('supplemental_views',facts['canvas'])

    def test_rejected_returned_delivery_preserves_spent_and_known_candidate_count(self):
        actual=append_gain_local_view
        def corrupt(*args,**kwargs):
            out,visual,receipt=actual(*args,**kwargs)
            self.assertTrue(receipt['applied'])
            visual['canvas_size']=[1,1]
            return out,visual,receipt
        with patch.object(local_view,'local_view_clock',return_value=0.), \
             patch('human_eye_plugin.auto_router.append_gain_local_view',side_effect=corrupt), \
             patch('human_eye_plugin.auto_router.local_view_clock',side_effect=[0.,.010,.016]):
            value=route()
        facts=json.loads(value['context_text']);receipt=facts['local_view']
        self.assertFalse(receipt['applied']);self.assertEqual(receipt['candidate_raster_count'],1)
        self.assertTrue(receipt['attempted'])
        self.assertAlmostEqual(receipt['current_event_local_view_cost_ms'],6.)
        self.assertEqual(receipt['new_readable_object_ids'],[])
        self.assertEqual(receipt['candidate_readable_object_ids'],['peripheral-0','peripheral-2'])
        self.assertEqual(receipt['still_missing_ids'],['peripheral-0','peripheral-2'])
        self.assertEqual(facts['canvas']['canvas_size'],[512,512])
        self.assertNotIn('supplemental_views',facts['canvas'])

    def test_malformed_supplemental_projection_falls_back_to_full_response(self):
        scene,ids=raw_nav()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.json'
            path.write_text(json.dumps({'schema_version':'1.0','project_root':str(Path(__file__).resolve().parents[1]),
                'state_file':'state.json','audit_file':'audit.jsonl','quad_size':128,'max_sessions':2}),encoding='utf-8')
            host=ReadOnlyHost();host.raw=scene
            value=LiveSpatialService(path,host=host).observe('brief-shape',focal_id='part',reference_id='base',
                query={'label_object_ids':ids})
        self.assertIsNotNone(project_task_brief(value))
        for malformed in [{'not':'a list'},['invalid'],[{},{}]]:
            with self.subTest(malformed=malformed):
                modified=copy.deepcopy(value);facts=json.loads(modified['routing']['context_text'])
                facts['canvas']['supplemental_views']=malformed
                modified['routing']['context_text']=json.dumps(facts)
                self.assertIsNone(project_task_brief(modified))


if __name__=='__main__':unittest.main()

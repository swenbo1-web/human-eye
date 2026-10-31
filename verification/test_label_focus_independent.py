"""Independent boundary checks for label focus and display-coverage evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin.auto_router import HumanEyeAutoRouter, OBSERVATION_CONTRACT_REVISION
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.task_brief import project_task_brief
from human_eye_plugin import scene_rendering as rendering
from human_eye_plugin.task_labels import build_task_label_plan
from verification.test_auto_router import box, observation, scene
from verification.test_label_coverage_delivery import NEIGHBORS, raw_scene, query, ReadOnlyHost


def negative(identity):
    return {'object_id':identity,'measurement_valid':True,
            'measurement_kind':'certified_penetration','clearance_exact':False,
            'signed_clearance_m':-.001,'is_penetrating':True}

def annotate_controlled_surface_ids(identities, plan, target_ids):
    """Exercise the actual annotation layer with disjoint current owner tiles.

    This controls sampled visibility only; it does not claim a geometry oracle.
    """
    meshes=[MeshEntity3D.from_dict(box(identity,[i*.03,0,.1],[.02]*3))
            for i,identity in enumerate(identities)]
    owners=np.full((256,256),-1,dtype=np.int32)
    for i in range(len(meshes)):
        x=12+(i%10)*22;y=30+(i//10)*25
        owners[y:y+12,x:x+12]=i
    meta={'name':'Q4 CONTACT','projection':'perspective',
          'target_object_ids':target_ids}
    picture=Image.new('RGB',(256,256),(20,25,30))
    rendering._annotate(picture,meshes,np.eye(4),np.eye(4),meta,owners,label_plan=plan)
    return meta


class IndependentLabelFocusTests(unittest.TestCase):
    def test_unpaired_explicit_focus_reports_unavailability_and_preserves_overview(self):
        host=ReadOnlyHost();host.raw['meshes']=host.raw['meshes'][:1]
        with tempfile.TemporaryDirectory() as folder:
            config=Path(folder)/'config.json'
            config.write_text(json.dumps({'schema_version':'1.0','project_root':'D:/hefe','quad_size':128,
                'state_file':'state.json','audit_file':'audit.jsonl','max_sessions':2}),encoding='utf-8')
            value=LiveSpatialService(config,host=host).observe('unpaired',query={'label_object_ids':['base']})
            facts=json.loads(value['routing']['context_text'])
            self.assertEqual(value['status'],'overview')
            report=facts['label_presentation']
            self.assertEqual(report['status'],'unavailable')
            self.assertEqual(report['reason'],'target_pair_not_established')
            self.assertEqual(report['visual_focus_requested_ids'],['base'])
            self.assertFalse(report['execution_authority'])
            self.assertIsNotNone(value['routing']['image'])
            brief=project_task_brief(value)
            self.assertIsNotNone(brief)
            self.assertEqual(brief['observation']['label_presentation'],report)
            self.assertEqual(host.applies,0)

    def test_no_image_explicit_focus_is_not_reported_as_drawn(self):
        event=observation(sid='text-only',query={'label_object_ids':['part','base']},include_image=False)
        value=HumanEyeAutoRouter(quad_size=128).handle_event(event)
        facts=json.loads(value['context_text'])
        self.assertIsNone(value['image'])
        self.assertEqual(facts['label_presentation']['status'],'unavailable')
        self.assertEqual(facts['label_presentation']['reason'],'image_not_requested')
        self.assertEqual(facts['label_presentation']['visual_focus_requested_ids'],['base','part'])
        self.assertTrue(facts['measurement']['measurement_valid'])

    def test_failed_canvas_reports_visual_unavailability_without_losing_geometry(self):
        event=observation(sid='failed-canvas',query={'label_object_ids':['part']})
        with patch('human_eye_plugin.auto_router._render_scene_canvas_prepared',side_effect=ValueError('render-budget-test')):
            value=HumanEyeAutoRouter(quad_size=128).handle_event(event)
        facts=json.loads(value['context_text'])
        self.assertIsNone(value['image'])
        self.assertEqual(facts['label_presentation']['reason'],'scene_canvas_unavailable')
        self.assertEqual(facts['label_presentation']['visual_focus_requested_ids'],['part'])
        self.assertEqual(facts['canvas']['detail'],'render-budget-test')
        self.assertTrue(facts['measurement']['measurement_valid'])

    def test_focus_omissions_survive_the_general_sixteen_row_diagnostic_cap(self):
        focus=['zz-visual-'+str(i) for i in range(6)]
        identities=['focus','reference']+['a-peripheral-'+str(i).zfill(2) for i in range(24)]+focus
        plan=build_task_label_plan([{'object_id':i} for i in identities],
            focal_id='focus',reference_id='reference',visual_focus_ids=focus)
        meta=annotate_controlled_surface_ids(identities,plan,['focus','reference'])
        layout=meta['label_layout']
        self.assertEqual(len(layout['omitted_objects']),16)
        self.assertGreater(layout['omitted_objects_truncated'],0)
        self.assertTrue(set(focus).isdisjoint(row['object_id'] for row in layout['omitted_objects']))
        requested=layout['visual_focus_coverage']
        self.assertEqual(requested['drawn_object_ids'],[])
        self.assertEqual({row['object_id'] for row in requested['undrawn_objects']},set(focus))
        self.assertEqual({row['reason'] for row in requested['undrawn_objects']},{'outside_task_label_focus'})

    def test_contact_pair_outside_natural_selection_does_not_claim_complete_risk_display(self):
        identities=['focus','reference','a','b','c','d']
        plan=build_task_label_plan([{'object_id':i} for i in identities],focal_id='focus',
            reference_id='reference',contacts=[negative(i) for i in 'abcd'],visual_focus_ids=['d'])
        self.assertEqual(plan['related_object_ids'],['d','a'])
        view=annotate_controlled_surface_ids(identities,plan,['focus','b'])
        labels={row['object_id']:row['display_label'] for row in view['projected_labels']}
        self.assertEqual(set(labels),{'focus','b'})
        self.assertEqual(labels['focus'],'A');self.assertTrue(labels['b'].startswith('R'))
        summary=rendering._task_label_coverage_summary({'task_labels':plan,'views':[view]})
        self.assertEqual(summary['known_penetration_candidate_count'],4)
        self.assertEqual(summary['unselected_known_penetration_count'],2)
        self.assertEqual(summary['visual_focus_not_drawn_ids'],['d'])
        self.assertIn('not_complete_scene_risk_scan',summary['scope'])
        self.assertFalse(summary['execution_authority'])
        self.assertNotIn('unlabelled_known_penetration_count',summary)

    def test_real_depth_occlusion_remains_an_explicit_focus_omission(self):
        values=[box('reference',[0,0,-.02],[.2,.2,.04]),
                box('focus',[0,0,.04],[.1,.1,.04],True),
                box('hidden',[0,0,.005],[.02,.02,.004])]
        meshes=[MeshEntity3D.from_dict(row) for row in values]
        plan=build_task_label_plan(meshes,focal_id='focus',reference_id='reference',visual_focus_ids=['hidden'])
        _,meta=rendering.render_scene_canvas(meshes,128,focal_id='focus',reference_id='reference',label_plan=plan)
        q1=meta['views'][0]
        self.assertEqual(q1['object_visible_pixels']['hidden'],0)
        coverage=q1['label_layout']['visual_focus_coverage']
        self.assertEqual(coverage['drawn_object_ids'],[])
        self.assertEqual(coverage['undrawn_objects'],[{'object_id':'hidden','reason':'not_surface_visible'}])
        self.assertTrue(all(row['object_id']!='hidden' for row in q1['projected_labels']))

    def test_focus_withdrawal_restores_default_selection_and_does_not_reuse_pinned_image(self):
        router=HumanEyeAutoRouter(quad_size=128)
        event={'event':'before_model','session_id':'withdraw','scene':raw_scene(),
               'task_kind':'spatial_3d','focal_id':'part','reference_id':'base','query':query(['south','west'])}
        first=router.handle_event(event)
        self.assertEqual(set(json.loads(first['context_text'])['canvas']['task_labels']['related_object_ids']),{'south','west'})
        event['query']=query()
        withdrawn=router.handle_event(event)
        self.assertFalse(withdrawn['cache_hit'])
        facts=json.loads(withdrawn['context_text'])
        self.assertEqual(facts['canvas']['task_labels']['visual_focus_object_ids'],[])
        self.assertEqual(facts['canvas']['task_labels']['related_object_ids'],['east','north'])
        self.assertEqual(facts['label_presentation']['selection_mode'],'pair_context')
        self.assertEqual(facts['label_presentation']['visual_focus_count'],0)

    def test_removing_requested_object_invalidates_observation_before_any_reuse(self):
        router=HumanEyeAutoRouter(quad_size=128)
        event={'event':'before_model','session_id':'removed','scene':raw_scene(),
               'task_kind':'spatial_3d','focal_id':'part','reference_id':'base','query':query(['west'])}
        first=router.handle_event(event)
        self.assertEqual(first['route'],'engine')
        self.assertIsNotNone(first['image'])
        changed=copy.deepcopy(event)
        changed['scene']['revision']='removed-r2'
        changed['scene']['meshes']=[m for m in changed['scene']['meshes'] if m['object_id']!='west']
        changed['query']={'label_object_ids':['west']}
        rejected=router.handle_event(changed)
        self.assertIn('invalid_query',rejected['reason_codes'])
        self.assertIsNone(router.export_state()['sessions'][0][1]['observation'])
        self.assertFalse(rejected.get('allow_action',False))

    def test_persisted_v1_visual_receipt_cannot_reenter_current_cache(self):
        router=HumanEyeAutoRouter(quad_size=64)
        first=router.handle_event(observation(sid='legacy'))
        saved=router.export_state()
        saved['sessions'][0][1]['observation']['contract_revision']='v1-task-attention-labels-20261026'
        other=HumanEyeAutoRouter(quad_size=64);other.import_state(saved)
        self.assertIsNone(other.export_state()['sessions'][0][1]['observation'])
        fresh=other.handle_event(observation(sid='legacy'))
        self.assertFalse(fresh['cache_hit'])
        self.assertNotEqual(fresh['observation_id'],first['observation_id'])
        self.assertEqual(other.export_state()['sessions'][0][1]['observation']['contract_revision'],OBSERVATION_CONTRACT_REVISION)

    def test_old_plan_cannot_be_presented_as_current_coverage(self):
        meshes=[MeshEntity3D.from_dict(row) for row in scene()['meshes']]
        plan=build_task_label_plan(meshes,focal_id='part',reference_id='base')
        plan['schema_revision']='observation-task-labels-v1-20261026'
        with self.assertRaises(ValueError):
            rendering.render_scene_canvas(meshes,128,focal_id='part',reference_id='base',label_plan=plan)

    def test_eight_label_maximum_uses_all_requested_surface_ids_without_alias_collisions(self):
        identities=['focus','reference']+['visual-'+str(i) for i in range(6)]
        plan=build_task_label_plan([{'object_id':i} for i in identities],focal_id='focus',
            reference_id='reference',visual_focus_ids=identities[2:])
        # Use a normal task view, where all eight selected current surfaces are active.
        meshes=[MeshEntity3D.from_dict(box(identity,[i*.03,0,.1],[.02]*3)) for i,identity in enumerate(identities)]
        owners=np.full((256,256),-1,dtype=np.int32)
        for i in range(8):owners[40+i//4*80:60+i//4*80,20+i%4*56:40+i%4*56]=i
        meta={'name':'Q1 XY TOP','projection':'orthographic','m_per_pixel':.001,'target_object_ids':['focus','reference']}
        rendering._annotate(Image.new('RGB',(256,256)),meshes,np.eye(4),np.eye(4),meta,owners,label_plan=plan)
        rows=meta['projected_labels']
        self.assertEqual(len(rows),8)
        self.assertEqual({r['object_id'] for r in rows},set(identities))
        self.assertEqual(len({r['display_label'] for r in rows}),8)
        self.assertEqual(meta['label_layout']['max_labels'],8)

    def _controlled_endpoint_case(self, core_on_new_line, *, visual=True, contact=False):
        identities=['focus','reference','subject']
        meshes=[MeshEntity3D.from_dict(box(identity,[i*.03,0,.1],[.02]*3)) for i,identity in enumerate(identities)]
        owners=np.full((256,256),-1,dtype=np.int32)
        owners[98:103,98:103]=2
        if core_on_new_line:owners[109:113,83:87]=0
        else:owners[190:194,10:14]=0
        owners[190:194,210:214]=1
        plan=build_task_label_plan(meshes,focal_id='focus',reference_id='reference',requested_ids=['subject'],
            visual_focus_ids=['subject'] if visual else [])
        meta={'name':'Q4 CONTACT' if contact else 'Q1 XY TOP',
              'projection':'perspective','target_object_ids':['focus','subject'] if contact else ['focus','reference']}
        label_to_box={'A':(2,20,14,34),'B':(2,42,14,56)}
        subject_box=(30,120,70,134);old=(30,127)
        def fixed_placement(draw,text,anchor,size,occupied,*args,**kwargs):
            box_=label_to_box.get(text,subject_box)
            return box_,(box_[0],box_[1]+7),False,False
        with patch.object(rendering,'_adaptive_context_label',side_effect=fixed_placement):
            rendering._annotate(Image.new('RGB',(256,256)),meshes,np.eye(4),np.eye(4),meta,owners,label_plan=plan)
        row=next(r for r in meta['projected_labels'] if r['object_id']=='subject')
        anchor=row['projected_center_px']
        nearest=rendering._label_leader_endpoint(anchor,subject_box)
        def independent_owner_coverage(endpoint):
            from PIL import ImageDraw
            mask=Image.new('1',(256,256));draw=ImageDraw.Draw(mask)
            draw.rectangle(subject_box,fill=1);draw.line((*anchor,*endpoint),fill=1,width=1)
            selected=owners[np.asarray(mask,dtype=bool)]
            return np.bincount(selected[selected>=0],minlength=3)
        return row,meta,old,nearest,independent_owner_coverage(old),independent_owner_coverage(nearest)

    def test_focus_endpoint_replacement_is_rejected_if_any_core_pixel_coverage_increases(self):
        row,meta,old,nearest,old_counts,new_counts=self._controlled_endpoint_case(True)
        self.assertNotEqual(old,nearest)
        self.assertGreater(new_counts[0],old_counts[0])
        self.assertEqual(row['leader_endpoint_px'],list(old))

    def test_focus_endpoint_replacement_admits_only_nonincreasing_coverage(self):
        row,meta,old,nearest,old_counts,new_counts=self._controlled_endpoint_case(False)
        self.assertLessEqual(new_counts.sum(),old_counts.sum())
        self.assertTrue(np.all(new_counts[:2]<=old_counts[:2]))
        self.assertEqual(row['leader_endpoint_px'],list(nearest))

    def test_endpoint_adjustment_is_not_applied_to_default_or_contact_paths(self):
        for visual,contact in [(False,False),(True,True)]:
            with self.subTest(visual=visual,contact=contact):
                row,meta,old,nearest,_,_=self._controlled_endpoint_case(False,visual=visual,contact=contact)
                self.assertNotEqual(old,nearest)
                self.assertEqual(row.get('leader_endpoint_px',list(old)),list(old))
                self.assertEqual(meta['label_layout'].get('visual_focus_endpoint_adjustments',0),0)


if __name__=='__main__':unittest.main()

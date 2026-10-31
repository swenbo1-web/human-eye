"""Public raw evidence tests; no host/model actions or engine geometry oracle."""
from __future__ import annotations
import copy
import hashlib
import json
import math
import unittest

from human_eye_plugin.goal_continuation import ContinuationPolicy, review_continuation

BUILD='sha256:'+'1'*64
FACES=[[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
       [2,3,7],[2,7,6],[1,2,6],[1,6,5],[3,0,4],[3,4,7]]
SIGNS=[(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
       (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]

def digest(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),
                                    ensure_ascii=True,allow_nan=False).encode()).hexdigest()

def native_box(oid,name,size,z):
    vertices=[[s[k]*size[k]/2 for k in range(3)] for s in SIGNS]
    matrix=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,z],[0.,0.,0.,1.]]
    world=[[v[0],v[1],v[2]+z] for v in vertices]
    return {'object_id':oid,'name':name,'local_vertices':vertices,'world_vertices':world,
            'faces':copy.deepcopy(FACES),'matrix':matrix,'color':[.1,.4,.8,1.]}

def envelope(z,revision):
    objects=[native_box('base','GreyBase',[.2,.2,.2],0.),
             native_box('part','BluePart',[.1,.1,.1],z)]
    meshes=[]
    for index,obj in enumerate(objects):
        meshes.append({'object_id':obj['object_id'],'name':obj['name'],
            'mark_label':'#B%04d'%index,'is_focal_target':obj['object_id']=='part',
            'color_rgb':[25,100,200],'vertices':copy.deepcopy(obj['world_vertices']),
            'faces':copy.deepcopy(obj['faces']),'edges':sorted([list(e) for e in
                {tuple(sorted((a,b))) for f in FACES for a,b in zip(f,f[1:]+f[:1])}]),
            'local_axes':[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]],
            'pivot_world':[0.,0.,obj['matrix'][2][3]],'axes_source':'host',
            'axes_confidence':'explicit','axes_reason':'native_world_matrix'})
    capture={'revision':revision,'unit':'m','coordinate_frame':'world','source':'blender','meshes':meshes,
             'host_execution':{'schema_version':'1.0','supported':True,'operation':'rigid_transform',
                               'scope':'independent_static_rigid_meshes','reasons':[]},
             'host_identity':{'schema_version':'1.0','document_epoch':'doc-1',
                              'object_instances':{'base':'instance-base','part':'instance-part'},
                              'capture_scope':'complete_scene_meshes'}}
    native={'unit':'m','coordinate_frame':'world','revision':'native:'+digest(objects),'objects':objects}
    return {'capture':capture,'native_scene':native,'capture_confirmation':copy.deepcopy(capture)}

def fixture(satisfied=False):
    end=.151 if satisfied else .154-.00099
    start=end+.00099
    before,current=envelope(start,'host-before'),envelope(end,'host-after')
    gap=end-.05-.1;motion=start-end
    request={'focal_id':'part','reference_id':'base','solver':'support_plane',
             'reference_triangle_index':2,'direction_world':[0.,0.,1.],
             'target_clearance_m':.001,'clearance_tolerance_m':1e-6,'max_steps':8,
             'max_step_translation_m':.001,'max_total_translation_m':.008,'max_duration_s':30.,
             'selection_binding':{'focal_id':'part','reference_id':'base',
                'scene_revision':'host-before','scene_fingerprint':digest(before['capture'])}}
    receipt={'status':'satisfied' if satisfied else 'review_required',
             'reason_codes':[] if satisfied else ['contact_feature_changed_after_rounded_translation'],
             'task_succeeded':satisfied,'review_required':not satisfied,'executed':True,
             'execution_status':'executed_verified','replayed':False,'historical_receipt':False,
             'runtime_identity':{'build_id':BUILD,'mode':'live'},'request':request,
             'request_id':'request1','segment_id':'segment1','base_revision':'host-before',
             'end_revision':'host-after','actual_total_translation_m':motion,
             'steps':[{'step_id':'step1','step_index':0,'operation_id':'op1','state':'complete',
                 'action':{'focal_id':'part','reference_id':'base','translation':[0.,0.,-motion],
                           'rotation_euler_deg':[0.,0.,0.]},'actual_translation_m':motion,
                 'result':{'status':'verified','executed':True,'verified':True,'execution_verified':True,
                     'actual_scene_revision':'host-after','goal_evaluation':'goal_satisfied' if satisfied else 'goal_not_satisfied',
                     'task_succeeded':satisfied,'receipt':{'source':'blender','host_execution_verified':True,
                         'focal_id':'part','before_revision':'host-before','after_revision':'host-after',
                         'coordinate_tolerance_m':1e-6}}}],
             'residual':{'status':'goal_satisfied' if satisfied else 'feature_changed',
                 'reason_codes':[] if satisfied else ['contact_feature_changed_after_rounded_translation'],
                 'measurement_valid':True,'goal_satisfied':satisfied,'candidate':None,
                 'scene_revision':'host-after','scene_fingerprint':digest(current['capture']),
                 'focal_id':'part','reference_id':'base','unit':'m','coordinate_frame':'world',
                 'current_clearance_m':gap,'signed_error_m':gap-.001,'absolute_error_m':abs(gap-.001)}}
    return before,current,receipt,ContinuationPolicy('part','base',expected_engine_build_id=BUILD)

def rebind_current(current,receipt):
    current['capture_confirmation']=copy.deepcopy(current['capture'])
    receipt['residual']['scene_fingerprint']=digest(current['capture'])

class ContinuationTests(unittest.TestCase):
    def test_known_feature_stop_is_non_authorizing_eligibility(self):
        args=fixture();before=copy.deepcopy(args[:3]);r=review_continuation(*args)
        self.assertEqual(r['decision'],'eligible_for_fresh_preview',r)
        self.assertFalse(r['execution_authority']);self.assertFalse(r['retry_authorized'])
        self.assertTrue(r['requires_fresh_discovery']);self.assertTrue(r['requires_fresh_preview'])
        self.assertFalse(r['whole_goal_budget_checked']);self.assertFalse(r['permission_checked'])
        self.assertEqual(args[:3],before)

    def test_satisfied_is_independently_checked_and_non_authorizing(self):
        args=fixture(True);r=review_continuation(*args)
        self.assertEqual(r['decision'],'completed',r);self.assertFalse(r['execution_authority'])
        args[2]['residual']['current_clearance_m']+=.0001
        self.assertEqual(review_continuation(*args)['decision'],'stop')

    def test_policy_is_frozen_and_explicit_build_required(self):
        a,b,r,p=fixture()
        with self.assertRaises(Exception):p.max_steps=9
        self.assertEqual(review_continuation(a,b,r,ContinuationPolicy('part','base'))['decision'],'stop')
        for kw in ({'direction_world':[0,0,1]},{'max_steps':True},{'max_steps':9},
                   {'max_step_translation_m':.002},{'max_recoveries':3},
                   {'measurement_agreement_m':1e-3},{'max_segment_duration_s':31}):
            with self.subTest(kw=kw),self.assertRaises(ValueError):ContinuationPolicy('part','base',**kw)

    def test_missing_joint_or_changed_bracket_refuses(self):
        for field in ('capture','native_scene','capture_confirmation'):
            a,b,r,p=fixture();b.pop(field)
            self.assertEqual(review_continuation(a,b,r,p)['decision'],'stop')
        a,b,r,p=fixture();b['capture_confirmation']['source']='other'
        self.assertEqual(review_continuation(a,b,r,p)['reason_codes'],['capture_window_changed'])

    def test_reasons_unknown_replay_and_rollback_refuse(self):
        mutations=[lambda r:r.update(status='execution_uncertain',executed=None),
                   lambda r:r.update(replayed=True),lambda r:r.update(historical_receipt=True),
                   lambda r:r.update(reason_codes=['segment_step_budget_exhausted']),
                   lambda r:r.update(reason_codes=['contact_feature_changed']),
                   lambda r:r['steps'][0].update(state='uncertain'),
                   lambda r:r['steps'][0]['result']['receipt'].update(rollback_performed=True),
                   lambda r:r['steps'][0]['result'].update(execution_verified=False),
                   lambda r:r['steps'][0]['result'].update(task_succeeded=None),
                   lambda r:r['steps'][0]['result']['receipt'].update(coordinate_tolerance_m=.01)]
        for mutation in mutations:
            a,b,r,p=fixture();mutation(r)
            with self.subTest(mutation=mutation):self.assertEqual(review_continuation(a,b,r,p)['decision'],'stop')

    def test_typed_goal_and_step_fields_reject_bool_nan_or_change(self):
        changes=[('target_clearance_m',.002),('clearance_tolerance_m',1e-5),('direction_world',[0,False,1]),
                 ('direction_world',[1,0,0]),('reference_id','part'),('reference_triangle_index',True),
                 ('max_steps',True),('max_step_translation_m',float('nan')),('max_total_translation_m',.009),
                 ('max_duration_s',True),('max_duration_s',31)]
        for field,value in changes:
            a,b,r,p=fixture();r['request'][field]=value
            with self.subTest(field=field,value=value):self.assertEqual(review_continuation(a,b,r,p)['decision'],'stop')
        for field,value in [('step_index',False),('actual_translation_m',True)]:
            a,b,r,p=fixture();r['steps'][0][field]=value
            self.assertEqual(review_continuation(a,b,r,p)['decision'],'stop')
        a,b,r,p=fixture();r['steps'][0]['action']['rotation_euler_deg']=[False,0,0]
        self.assertEqual(review_continuation(a,b,r,p)['decision'],'stop')

    def test_revision_fingerprint_and_chain_must_bind_actual_readback(self):
        for mutation in [lambda r:r.update(end_revision='other'),
                lambda r:r['residual'].update(scene_revision='stale'),
                lambda r:r['residual'].update(scene_fingerprint='0'*64),
                lambda r:r['request']['selection_binding'].update(scene_fingerprint='0'*64),
                lambda r:r['steps'][0]['result']['receipt'].update(before_revision='other'),
                lambda r:r['steps'][0]['result'].update(actual_scene_revision='other')]:
            a,b,r,p=fixture();mutation(r)
            self.assertEqual(review_continuation(a,b,r,p)['decision'],'stop')

    def test_host_document_instance_capability_or_frame_change_refuses(self):
        changes=[lambda c:c['host_identity'].update(document_epoch='new-doc'),
                 lambda c:c['host_identity']['object_instances'].update(part='new-instance'),
                 lambda c:c['host_execution'].update(supported=False),
                 lambda c:c.update(source='other'),lambda c:c.update(unit='mm'),
                 lambda c:c['host_identity'].pop('object_instances')]
        for change in changes:
            a,b,r,p=fixture();change(b['capture']);rebind_current(b,r)
            self.assertEqual(review_continuation(a,b,r,p)['decision'],'stop')

    def test_exact_pose_xy_and_local_geometry_preservation(self):
        for field in ('rotation','xy','local'):
            a,b,r,p=fixture();obj=b['native_scene']['objects'][1];mesh=b['capture']['meshes'][1]
            if field=='rotation':obj['matrix'][0][0]+=1e-8
            elif field=='xy':
                obj['matrix'][0][3]+=1e-9;mesh['pivot_world'][0]+=1e-9
                for v in obj['world_vertices']:v[0]+=1e-9
                for v in mesh['vertices']:v[0]+=1e-9
            else:
                for v in obj['local_vertices']:v[0]*=(1+1e-8)
            rebind_current(b,r)
            with self.subTest(field=field):self.assertEqual(review_continuation(a,b,r,p)['decision'],'stop')

    def test_nonfocal_metadata_and_capture_deformation_refuse(self):
        a,b,r,p=fixture();b['native_scene']['objects'][0]['color'][0]+=.01
        self.assertEqual(review_continuation(a,b,r,p)['decision'],'stop')
        a,b,r,p=fixture();b['capture']['meshes'][1]['vertices'][0][2]+=1e-8;rebind_current(b,r)
        self.assertEqual(review_continuation(a,b,r,p)['reason_codes'],['capture_not_native_local_pose_forward_map'])

    def test_local_topology_or_domain_violation_refuse(self):
        for role in (0,1):
            a,b,r,p=fixture();b['native_scene']['objects'][role]['faces'].pop()
            b['capture']['meshes'][role]['faces'].pop();rebind_current(b,r)
            self.assertEqual(review_continuation(a,b,r,p)['decision'],'stop')

    def test_fresh_measurement_and_reported_error_consistency(self):
        for mutation in [lambda r:r['residual'].update(current_clearance_m=.008),
                        lambda r:r['residual'].update(signed_error_m=0),
                        lambda r:r['residual'].update(status='candidate'),
                        lambda r:r['residual'].update(reason_codes=[]),
                        lambda r:r['residual'].update(goal_satisfied=True),
                        lambda r:r.update(actual_total_translation_m=.0001),
                        lambda r:r.update(runtime_identity={'build_id':'sha256:'+'2'*64,'mode':'live'})]:
            a,b,r,p=fixture();mutation(r)
            self.assertEqual(review_continuation(a,b,r,p)['decision'],'stop')

    def test_representation_bound_does_not_allow_actual_pose_drift(self):
        a,b,r,p=fixture()
        # Native binary32 world coordinates may differ slightly from the
        # binary64 engine forward map; the matrix and local mesh remain exact.
        b['native_scene']['objects'][1]['world_vertices'][0][2]+=1e-8
        b['native_scene']['revision']='native:'+digest(b['native_scene']['objects'])
        decision=review_continuation(a,b,r,p)
        self.assertEqual(decision['decision'],'eligible_for_fresh_preview',decision)
        b['native_scene']['objects'][1]['matrix'][0][3]+=1e-9
        self.assertEqual(review_continuation(a,b,r,p)['decision'],'stop')

    def test_native_snapshot_digest_must_bind_actual_objects(self):
        for which in (0,1):
            a,b,r,p=fixture();(a,b)[which]['native_scene']['revision']='native:'+'0'*64
            result=review_continuation(a,b,r,p)
            self.assertEqual(result['reason_codes'],['native_snapshot_revision_mismatch'])

    def test_request_permission_claim_never_grants_authority(self):
        a,b,r,p=fixture();r['execution_authority']=True;r['retry_authorized']=True
        result=review_continuation(a,b,r,p)
        self.assertEqual(result['decision'],'eligible_for_fresh_preview',result)
        self.assertFalse(result['execution_authority']);self.assertFalse(result['retry_authorized'])

if __name__=='__main__':unittest.main()

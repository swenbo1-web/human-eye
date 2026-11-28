"""Independent scalar-map checks for the source-bound cross-frame projection.

These authored internal proofs are not native source-admission evidence. The
real-process acceptance lives separately; no private task truth is imported.
"""
import copy
from dataclasses import replace
import hashlib
import json
import time
import unittest
from unittest.mock import patch

from human_eye_plugin import deformation_anchors as anchors
from human_eye_plugin import deformation_context as context
from human_eye_plugin import deformation_core_facts as core
from human_eye_plugin import deformation_closure as closure
from human_eye_plugin import surface_deformation as surface
from verification.test_deformation_anchors import proof as anchor_proof
from verification.test_deformation_context import setup
from verification.test_deformation_core_facts import validation


def analytic_proof(*, frame=1, scales=None, unknown=(), empty=False):
    """Four disjoint original triangles; exact diagonal maps supply the oracle."""
    if scales is None:
        scales=[(1.,1.),(2.,1.),(1.,.5),(4.,.5)]
    p=anchor_proof();original=[];current=[];triangles=[]
    for index,(sx,sy) in enumerate(scales):
        x=2. if empty or index==3 else index*.25
        y=0.;first=len(original)
        original.extend([[x,y,0.],[x+.125,y,0.],[x,y+.125,0.]])
        current.extend([[x,y,0.],[x+.125*sx,y,0.],[x,y+.125*sy,0.]])
        triangles.append([first,first+1,first+2])
    p.update(original=original,current=current,triangles=triangles,
             unweighted=[i for index in unknown for i in triangles[index]],bones_total=2)
    p['source_sha256']=format(frame,'x')*64
    p['source'].update(scene_sha256=format(frame+2,'x')*64,
                       frame=dict(number=frame,subframe=0.),
                       document_epoch=format(frame+4,'x')*32,process_id=100+frame)
    return p


def frame_fixture(*, frame=1, scales=None, unknown=(), empty=False):
    data,_=setup(analytic_proof(frame=frame,scales=scales,unknown=unknown,empty=empty),
                 core=.75,primary=8.,candidates=(1.,))
    full,audit=core.plan(data['proof'],data['query'],policy=data['policy'],
        policy_sha256=data['policy_sha256'],pins=data['pins'],rows=data['rows'],
        source_validation=validation(),deadline_ns=data['deadline_ns'])
    data.update(core_report=full,core_audit=audit)
    return data


def inputs(*, first=None, second=None):
    first=frame_fixture(frame=1) if first is None else first
    second=frame_fixture(frame=2,scales=[(1.,1.),(2.,.5),(1.,.5),(4.,.5)]) if second is None else second
    task=dict(task_sha256='e'*64,condition_id='authored-public-condition',sources={})
    frames=[]
    for label,data in [('source_left',first),('source_right',second)]:
        policy=data['policy']
        task['sources'][label]=dict(source_ref=copy.deepcopy(policy['source_ref']),
            catalog_sha256=policy['catalog_sha256'],anchor_id=policy['anchor_id'],
            policy_sha256=data['policy_sha256'])
        frame={key:data[key] for key in ('proof','rows','policy','policy_sha256','query','pins')}
        frame.update(label=label,membership=data['core_audit']['core_membership'],source_validation=validation())
        frames.append(frame)
    return task,frames


def call(task,frames,**kwargs):
    values=dict(candidates_by_label={'source_left':[],'source_right':[1]},deadline_ns=time.perf_counter_ns()+5_000_000_000)
    values.update(kwargs)
    return closure.project(task,frames,**values)


def get_frame(view,label):
    return next(row for row in view['core_summary_by_frame'] if row['label']==label)


def get_trajectory(view,face):
    return next(row for row in view['candidate_witness_trajectories'] if row['selected_triangle']==face)


class CrossFrameClosureTests(unittest.TestCase):
    def test_candidate_seen_only_in_second_source_is_complete_in_both(self):
        task,frames=inputs();view,audit=call(task,frames)
        self.assertEqual(view['schema'],'surface-deformation-cross-frame-view-v1')
        self.assertEqual(view['task_sha256'],task['task_sha256'])
        self.assertEqual(view['condition_id'],task['condition_id'])
        trajectories=view['candidate_witness_trajectories'];self.assertEqual(len(trajectories),1)
        self.assertIs(type(trajectories[0]['selected_triangle']),int)
        self.assertEqual(trajectories[0]['selected_triangle'],1)
        rows={r['label']:r for r in trajectories[0]['frames']}
        self.assertEqual(set(rows),set(task['sources']))
        for source in frames:
            expected=surface._verified_rows(source['proof'],source['rows'],deadline_ns=time.perf_counter_ns()+1_000_000_000)[1]
            row=rows[source['label']]
            self.assertEqual(set(row),{'label','file_sha256','principal_stretches','area_ratio','state','reason','in_core','has_confirmed_mixed_witness'})
            for key in ('principal_stretches','area_ratio','state','reason'):self.assertEqual(row[key],expected[key])
            self.assertEqual(row['file_sha256'],source['proof']['source']['scene_sha256'])
            self.assertTrue(row['in_core'])
        self.assertEqual(rows['source_left']['principal_stretches'],[2.,1.])
        self.assertEqual(rows['source_right']['principal_stretches'],[2.,.5])
        self.assertIs(rows['source_left']['has_confirmed_mixed_witness'],False)
        self.assertIs(rows['source_right']['has_confirmed_mixed_witness'],True)

    def test_source_label_join_does_not_depend_on_frame_list_order(self):
        task,frames=inputs();forward,_=call(task,frames);reverse,_=call(task,list(reversed(frames)))
        self.assertEqual(forward['candidate_witness_trajectories'],reverse['candidate_witness_trajectories'])
        self.assertEqual(forward['core_summary_by_frame'],reverse['core_summary_by_frame'])

    def test_duplicate_missing_and_unknown_labels_reject(self):
        task,frames=inputs()
        bad=copy.deepcopy(frames);bad[1]['label']=bad[0]['label']
        for changed,reason in ((bad,'source_labels'),(frames[:1],'frames'),(frames+[frames[0]],'frames'),
                ([dict(frames[0],label='unregistered'),frames[1]],'source_labels')):
            with self.subTest(labels=[f['label'] for f in changed]),self.assertRaisesRegex(ValueError,'deformation_closure_'+reason):call(task,changed)
        for candidates in ({'source_left':[0]}, {'source_left':[],'source_right':[1],'extra':[]}):
            with self.subTest(candidates=candidates),self.assertRaisesRegex(ValueError,'deformation_closure_candidate_labels'):call(task,frames,candidates_by_label=candidates)

    def test_wrong_source_scene_mesh_rig_or_saved_frame_rejects(self):
        task,frames=inputs()
        for edits in (dict(scene_sha256='0'*64),dict(mesh_object_id='replacement'),dict(rig_object_id='replacement'),dict(frame=dict(number=999,subframe=0.))):
            bad=copy.deepcopy(task);bad['sources']['source_right']['source_ref'].update(edits)
            with self.subTest(edits=edits),self.assertRaisesRegex(ValueError,'deformation_closure_source_binding'):call(bad,frames)

    def test_bool_saved_frame_values_do_not_pass_python_numeric_equality(self):
        task,frames=inputs()
        for key,value in (('number',True),('subframe',False)):
            bad=copy.deepcopy(task);bad['sources']['source_left']['source_ref']['frame'][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'deformation_context_frame'):call(bad,frames)

    def test_malformed_frame_shapes_are_rejected_before_attribute_access(self):
        task,frames=inputs()
        for key,value in (('proof',None),('membership',None),('proof',{'triangles':None})):
            bad=copy.deepcopy(frames);bad[0][key]=value
            with self.subTest(key=key,value=value),self.assertRaisesRegex(ValueError,'deformation_closure_frame_fields'):call(task,bad)

    def test_wrong_external_catalog_anchor_and_policy_reject(self):
        task,frames=inputs()
        for key,value in [('catalog_sha256','0'*64),('anchor_id','bone-anchor:'+'0'*64),('policy_sha256','0'*64)]:
            bad=copy.deepcopy(task);bad['sources']['source_right'][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'deformation_closure_selection_binding'):call(bad,frames)

    def test_source_proof_frame_change_invalidates_bound_rows(self):
        task,frames=inputs();bad=copy.deepcopy(frames);bad[1]['proof']['source']['frame']['number']+=1
        with self.assertRaisesRegex(ValueError,'deformation_closure_source_binding'):call(task,bad)

    def test_same_mesh_id_cannot_hide_original_face_order_or_winding_change(self):
        for change in ('face_order','vertex_order','winding'):
            task,frames=inputs();bad=copy.deepcopy(frames);proof=bad[1]['proof']
            if change=='face_order':proof['triangles'][0],proof['triangles'][1]=proof['triangles'][1],proof['triangles'][0]
            elif change=='vertex_order':proof['triangles'][0]=proof['triangles'][0][1:]+proof['triangles'][0][:1]
            else:proof['triangles'][0]=list(reversed(proof['triangles'][0]))
            bad[1]['rows']=surface._geometry_rows(proof,deadline_ns=time.perf_counter_ns()+1_000_000_000)
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'deformation_closure_original_topology'):call(task,bad)

    def test_same_ids_and_triangle_indices_cannot_hide_changed_reference_geometry(self):
        task,frames=inputs();bad=copy.deepcopy(frames);bad[1]['proof']['original'][0][0]+=.03125
        bad[1]['rows']=surface._geometry_rows(bad[1]['proof'],deadline_ns=time.perf_counter_ns()+1_000_000_000)
        with self.assertRaisesRegex(ValueError,'deformation_closure_original_topology'):call(task,bad)

    def test_duplicate_candidate_bool_out_of_range_and_more_than_four_union_reject(self):
        task,frames=inputs()
        for ids in ([1,1],[True],[-1],[4],[1.0]):
            with self.subTest(ids=ids),self.assertRaisesRegex(ValueError,'deformation_closure_candidate_indices'):call(task,frames,candidates_by_label={'source_left':ids,'source_right':[]})
        one=frame_fixture(frame=1,scales=[(1.,1.)]*5);two=frame_fixture(frame=2,scales=[(1.,1.)]*5)
        task,frames=inputs(first=one,second=two)
        with self.assertRaisesRegex(ValueError,'deformation_closure_candidate_union_limit'):call(task,frames,candidates_by_label={'source_left':[0,1,2,3],'source_right':[4]})

    def test_missing_duplicate_and_unbound_rows_do_not_become_unknown_defaults(self):
        task,frames=inputs();raw=json.loads(frames[1]['rows'].payload)
        for changed in (raw[:-1],[raw[0],raw[0],*raw[2:]]):
            bad=copy.deepcopy(frames);bad[1]['rows']=replace(bad[1]['rows'],payload=core.r.encoded(changed))
            with self.subTest(rows=len(changed)),self.assertRaisesRegex(ValueError,'deformation_rows_binding'):call(task,bad)
        bad=copy.deepcopy(frames);bad[1]['rows']=raw
        with self.assertRaisesRegex(ValueError,'deformation_rows_binding'):call(task,bad)

    def test_incomplete_or_changed_region_membership_rejects(self):
        task,frames=inputs()
        for edits in (dict(membership_complete=False),dict(source_sha256='0'*64),dict(matched_triangle_indices=[0,0]),dict(triangles_scanned=1)):
            bad=copy.deepcopy(frames);bad[1]['membership'].update(edits)
            with self.subTest(edits=edits),self.assertRaisesRegex(ValueError,'deformation_core_facts_membership'):call(task,bad)
        bad=copy.deepcopy(frames);bad[1]['membership']['region']['bounds'][0][0]-=.125
        with self.assertRaisesRegex(ValueError,'deformation_closure_membership_region'):call(task,bad)

    def test_malformed_noncore_rows_do_not_hide_behind_valid_core(self):
        task,frames=inputs()
        for edit in (dict(area_ratio=False),dict(principal_stretches=[True,.5]),dict(reason='invented_reason')):
            bad=copy.deepcopy(frames);values=json.loads(bad[1]['rows'].payload);values[3].update(edit)
            bad[1]['rows']=replace(bad[1]['rows'],payload=core.r.encoded(values))
            with self.subTest(edit=edit),self.assertRaisesRegex(ValueError,'deformation_closure_rows'):call(task,bad)

    def test_complete_core_summaries_equal_ordinary_full_core_facts(self):
        first=frame_fixture(frame=1,unknown=(2,));second=frame_fixture(frame=2)
        task,frames=inputs(first=first,second=second)
        view,_=call(task,frames,candidates_by_label={'source_left':[3],'source_right':[]})
        for label,data in [('source_left',first),('source_right',second)]:
            summary=get_frame(view,label)
            self.assertEqual(summary['facts'],data['core_report']['facts'])
            self.assertEqual(summary['core_witnesses'],data['core_report']['core_witnesses'])
            self.assertEqual(summary['core_ref'],data['core_report']['core_ref'])
        self.assertEqual(get_frame(view,'source_left')['facts']['core_triangle_count'],3)
        self.assertEqual(get_frame(view,'source_left')['facts']['core_states']['unknown'],1)
        self.assertEqual(len(view['candidate_witness_trajectories']),1)

    def test_core_outside_extrema_are_not_promoted_to_core_or_confirmation(self):
        task,frames=inputs(second=frame_fixture(frame=2));view,_=call(task,frames,candidates_by_label={'source_left':[3],'source_right':[]})
        candidate=get_trajectory(view,3)
        for row in candidate['frames']:
            self.assertFalse(row['in_core']);self.assertIs(row['has_confirmed_mixed_witness'],False)
            self.assertEqual(row['principal_stretches'],[4.,.5])
        for summary in view['core_summary_by_frame']:
            self.assertEqual(summary['facts']['core_extrema']['max_principal_stretch'],2.)
            self.assertEqual(summary['facts']['core_extrema']['min_principal_stretch'],.5)
            self.assertNotIn(3,summary['core_witnesses'].values())

    def test_separate_faces_crossing_each_threshold_are_not_one_mixed_witness(self):
        task,frames=inputs(second=frame_fixture(frame=2));view,_=call(task,frames)
        for summary in view['core_summary_by_frame']:
            self.assertGreater(summary['facts']['core_extrema']['max_principal_stretch'],1.1)
            self.assertLess(summary['facts']['core_extrema']['min_principal_stretch'],.9)
            self.assertIs(summary['has_confirmed_mixed_witness'],False)

    def test_unknown_confirmation_is_tristate_not_bool_cast(self):
        first=frame_fixture(frame=1,unknown=(2,));second=frame_fixture(frame=2,scales=[(1.,1.),(2.,.5),(1.,.5),(4.,.5)],unknown=(2,))
        task,frames=inputs(first=first,second=second);view,_=call(task,frames)
        self.assertIs(get_frame(view,'source_left')['has_confirmed_mixed_witness'],None)
        self.assertIs(get_frame(view,'source_right')['has_confirmed_mixed_witness'],True)
        for row in get_trajectory(view,1)['frames']:
            self.assertIs(row['has_confirmed_mixed_witness'],None if row['label']=='source_left' else True)

    def test_empty_core_remains_empty_with_real_peripheral_candidate(self):
        task,frames=inputs(first=frame_fixture(frame=1,empty=True),second=frame_fixture(frame=2,empty=True))
        view,_=call(task,frames)
        for summary in view['core_summary_by_frame']:
            self.assertEqual(summary['facts']['core_triangle_count'],0)
            self.assertEqual(summary['facts']['core_states'],dict(measured=0,collapsed=0,unknown=0))
            self.assertIs(summary['has_confirmed_mixed_witness'],False)
        self.assertTrue(all(not r['in_core'] for r in get_trajectory(view,1)['frames']))

    def test_all_unknown_rows_are_real_null_facts_in_all_frames(self):
        task,frames=inputs(first=frame_fixture(frame=1,unknown=(0,1,2)),second=frame_fixture(frame=2,unknown=(0,1,2)))
        view,_=call(task,frames)
        for row in get_trajectory(view,1)['frames']:
            self.assertEqual(row['state'],'unknown');self.assertEqual(row['reason'],'unweighted_vertex_source')
            self.assertIsNone(row['principal_stretches']);self.assertIsNone(row['area_ratio'])
            self.assertIsNone(row['has_confirmed_mixed_witness'])
        for summary in view['core_summary_by_frame']:
            self.assertEqual(summary['facts']['core_states']['unknown'],3)
            self.assertEqual(summary['facts']['core_extrema'],dict.fromkeys(core.METRICS))

    def test_collapsed_zero_is_retained_but_not_counted_as_measured_mixed(self):
        task,frames=inputs(first=frame_fixture(frame=1,scales=[(1.,1.),(2.,0.),(1.,.5),(4.,.5)]),second=frame_fixture(frame=2,scales=[(1.,1.),(2.,0.),(1.,.5),(4.,.5)]))
        view,_=call(task,frames)
        for row in get_trajectory(view,1)['frames']:
            self.assertEqual(row['state'],'collapsed');self.assertEqual(row['reason'],'current_zero_area')
            self.assertEqual(row['principal_stretches'],[2.,0.]);self.assertEqual(row['area_ratio'],0.)
            self.assertIs(row['has_confirmed_mixed_witness'],False)
        self.assertEqual(get_frame(view,'source_left')['facts']['core_states']['collapsed'],1)

    def test_empty_candidate_union_does_not_invent_a_face(self):
        task,frames=inputs();view,_=call(task,frames,candidates_by_label={'source_left':[],'source_right':[]})
        self.assertEqual(view['candidate_witness_trajectories'],[])
        self.assertEqual(len(view['core_summary_by_frame']),2)

    def test_explicit_mixed_thresholds_include_their_exact_boundary(self):
        task,frames=inputs();view,_=call(task,frames,threshold_high=2.,threshold_low=.5)
        self.assertIs(get_frame(view,'source_left')['has_confirmed_mixed_witness'],False)
        self.assertIs(get_frame(view,'source_right')['has_confirmed_mixed_witness'],True)

    def test_thresholds_cannot_be_nonfinite_or_bool(self):
        task,frames=inputs()
        for edits in (dict(threshold_high=True),dict(threshold_low=False),dict(threshold_high=float('inf')),dict(threshold_low=float('nan'))):
            with self.subTest(edits=edits),self.assertRaisesRegex(ValueError,'deformation_closure_thresholds'):call(task,frames,**edits)

    def test_model_publication_and_complete_sidecar_have_independent_exact_hashes(self):
        task,frames=inputs();view,audit=call(task,frames)
        blob=context.publication_bytes(view);evidence=context.publication_bytes(audit['evidence_sidecar'])
        self.assertEqual(audit['published_publication_bytes'],len(blob))
        self.assertEqual(audit['published_publication_sha256'],hashlib.sha256(blob).hexdigest())
        self.assertEqual(view['evidence_ref']['sha256'],hashlib.sha256(evidence).hexdigest())
        self.assertEqual(audit['evidence_sidecar_sha256'],view['evidence_ref']['sha256'])
        self.assertNotEqual(audit['published_publication_sha256'],view['evidence_ref']['sha256'])
        self.assertEqual(audit['evidence_sidecar']['schema'],'surface-deformation-cross-frame-evidence-v1')
        self.assertIn('original',evidence.decode('ascii'))
        self.assertIn('triangles',evidence.decode('ascii'))
        self.assertNotIn('original',view)

    def test_identical_qualified_inputs_have_stable_view_and_evidence_across_deadlines(self):
        task,frames=inputs();now=time.perf_counter_ns()
        first,first_audit=call(task,frames,deadline_ns=now+5_000_000_000)
        second,second_audit=call(task,frames,deadline_ns=now+6_000_000_000)
        self.assertEqual(context.publication_bytes(first),context.publication_bytes(second))
        self.assertEqual(context.publication_bytes(first_audit['evidence_sidecar']),context.publication_bytes(second_audit['evidence_sidecar']))
        self.assertEqual(first['evidence_ref'],second['evidence_ref'])
        self.assertNotEqual(first_audit['original_deadline_ns'],second_audit['original_deadline_ns'])
        self.assertNotIn('core_audit',first_audit['evidence_sidecar']['frames']['source_left'])
        self.assertIn('core_verification_audits_by_label',first_audit)

    def test_source_labels_with_slash_and_tilde_have_resolvable_row_pointers(self):
        task,frames=inputs();old=list(task['sources']);names=['left/~','right~/']
        task['sources']={new:task['sources'][key] for key,new in zip(old,names)}
        for frame,name in zip(frames,names):frame['label']=name
        view,audit=call(task,frames,candidates_by_label={names[0]:[],names[1]:[1]})
        refs=get_trajectory(view,1)['evidence_rows_by_label']
        for label,pointer in refs.items():
            parts=pointer.split('/')[1:];value=audit['evidence_sidecar']
            for part in parts:
                key=part.replace('~1','/').replace('~0','~')
                value=value[int(key)] if isinstance(value,list) else value[key]
            self.assertEqual(value,audit['evidence_sidecar']['frames'][label]['rows'][1])
        self.assertEqual(refs['left/~'],'/frames/left~1~0/rows/1')

    def test_projection_preserves_numeric_precision_and_does_not_mutate_inputs(self):
        first=frame_fixture(frame=1,scales=[(1.,1.),(1.2345678912345,.71234567891234),(1.,.5),(4.,.5)])
        task,frames=inputs(first=first);snapshot=copy.deepcopy((task,frames));view,audit=call(task,frames)
        expected=surface._verified_rows(frames[0]['proof'],frames[0]['rows'],deadline_ns=time.perf_counter_ns()+1_000_000_000)[1]
        row=get_trajectory(view,1)['frames'][0]
        self.assertEqual(row['principal_stretches'],expected['principal_stretches']);self.assertEqual(row['area_ratio'],expected['area_ratio'])
        self.assertEqual((task,frames),snapshot)
        self.assertIs(type(row['area_ratio']),float)
        audit['evidence_sidecar']['mutated_test_marker']=True
        self.assertNotIn('mutated_test_marker',view)
        audit['evidence_sidecar']['frames']['source_left']['rows'][1]['area_ratio']=999.
        self.assertEqual(get_trajectory(view,1)['frames'][0]['area_ratio'],expected['area_ratio'])

    def test_original_deadline_expiry_before_projection_is_not_success(self):
        task,frames=inputs()
        with self.assertRaisesRegex(ValueError,'original_deadline'):call(task,frames,deadline_ns=0)

    def test_deadline_expiring_while_publishing_view_is_not_success(self):
        task,frames=inputs();now=time.perf_counter_ns();deadline=now+5_000_000_000;clock=[now]
        publication=context.publication_bytes;seen=[]
        def late(report):
            blob=publication(report)
            if report.get('schema')=='surface-deformation-cross-frame-view-v1':
                seen.append(report['schema']);clock[0]=deadline
            return blob
        with patch.object(context.r.time,'perf_counter_ns',side_effect=lambda:clock[0]),patch.object(context,'publication_bytes',side_effect=late):
            with self.assertRaisesRegex(ValueError,'original_deadline'):call(task,frames,deadline_ns=deadline)
        self.assertTrue(seen,'must reach final view publication before expiring')


if __name__=='__main__':unittest.main()

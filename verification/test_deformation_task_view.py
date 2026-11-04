"""Analytic task witnesses and global scope, not native source admission."""
import copy
import hashlib
import time
import unittest

from human_eye_plugin import deformation_context as context
from human_eye_plugin import deformation_task_view as task_view
from human_eye_plugin import surface_deformation as surface
from verification.test_deformation_closure import frame_fixture,inputs,get_trajectory,get_frame


def task_fixture(*,first=None,second=None,question='Track a same-face mixed witness and distinguish local from global unknowns.'):
    legacy,frames=inputs(first=first,second=second)
    spec=dict(schema='surface-deformation-task-request-v1',question=question,
        thresholds=dict(high=1.1,low=.9),sources={})
    for frame in frames:
        label=frame['label'];policy=frame['policy']
        spec['sources'][label]=dict(source_ref=copy.deepcopy(policy['source_ref']),
            catalog_sha256=policy['catalog_sha256'],anchor_id=policy['anchor_id'],
            core_half_extents_m=policy['required_core_half_extents_m'][:],
            profile_sha256=frame['pins']['profile_sha256'])
    task=dict(spec=spec,task_sha256=task_view.task_digest(spec),condition_id='analytic-task-view',run_nonce='a'*32)
    return task,frames


def mixed_counterexample():
    first=frame_fixture(frame=1,scales=[(1.,1.)]*4)
    second=frame_fixture(frame=2,scales=[(3.,1.),(1.,.3),(1.2,.8),(1.,1.)])
    return task_fixture(first=first,second=second),first,second


def produce(task,frames,**kwargs):
    params=dict(deadline_ns=time.perf_counter_ns()+5_000_000_000)
    params.update(kwargs)
    return task_view.produce(task,frames,**params)


def globals_by_label(view):return {row['label']:row for row in view['global_summary_by_frame']}


class TaskWitnessViewTests(unittest.TestCase):
    def test_required_mixed_nonextremum_face_is_really_joined_across_sources(self):
        (task,frames),first,second=mixed_counterexample()
        old={face for source in (first,second) for face in source['core_report']['core_witnesses'].values() if face is not None}
        self.assertNotIn(2,old,'Counterexample must actually defeat old extrema-only selection')
        view,audit=produce(task,frames)
        self.assertEqual(view['schema'],'surface-deformation-task-witness-view-v2')
        track=get_trajectory(view,2)
        rows={r['label']:r for r in track['frames']}
        self.assertEqual(set(rows),set(task['spec']['sources']))
        self.assertEqual(rows['source_left']['principal_stretches'],[1.,1.])
        self.assertAlmostEqual(rows['source_right']['principal_stretches'][0],1.2,delta=1e-12)
        self.assertAlmostEqual(rows['source_right']['principal_stretches'][1],.8,delta=1e-12)
        self.assertIs(rows['source_left']['has_confirmed_mixed_witness'],False)
        self.assertIs(rows['source_right']['has_confirmed_mixed_witness'],True)
        self.assertTrue(rows['source_right']['in_core'])
        self.assertLessEqual(len(view['candidate_witness_trajectories']),4)

    def test_explicit_existing_choices_cannot_displace_a_required_witness(self):
        (task,frames),_,_=mixed_counterexample()
        view,_=produce(task,frames,explicit_candidates_by_label={'source_left':[0],'source_right':[1]})
        actual={t['selected_triangle'] for t in view['candidate_witness_trajectories']}
        self.assertTrue({0,1,2}<=actual)

    def test_overflow_of_explicit_plus_required_witness_is_not_silently_truncated(self):
        (task,frames),_,_=mixed_counterexample()
        with self.assertRaisesRegex(ValueError,'deformation_task_view_candidate_budget'):
            produce(task,frames,explicit_candidates_by_label={'source_left':[0,1,3],'source_right':[]},max_candidates=3)

    def test_two_distinct_source_required_witnesses_need_two_slots(self):
        first=frame_fixture(frame=1,scales=[(1.2,.8),(1.,1.),(1.,1.),(1.,1.)])
        second=frame_fixture(frame=2,scales=[(1.,1.),(1.,1.),(1.2,.8),(1.,1.)])
        task,frames=task_fixture(first=first,second=second)
        with self.assertRaisesRegex(ValueError,'deformation_task_view_candidate_budget'):
            produce(task,frames,max_candidates=1)
        view,_=produce(task,frames,max_candidates=2)
        self.assertEqual({t['selected_triangle'] for t in view['candidate_witness_trajectories']},{0,2})

    def test_one_shared_same_face_witness_can_cover_both_positive_sources(self):
        first=frame_fixture(frame=1,scales=[(1.2,.8),(1.,1.),(1.2,.8),(1.,1.)])
        second=frame_fixture(frame=2,scales=[(1.,1.),(1.,1.),(1.2,.8),(1.,1.)])
        task,frames=task_fixture(first=first,second=second);view,_=produce(task,frames,max_candidates=1)
        self.assertEqual([t['selected_triangle'] for t in view['candidate_witness_trajectories']],[2])
        self.assertTrue(all(get_frame(view,label)['has_confirmed_mixed_witness'] is True for label in task['spec']['sources']))

    def test_collapsed_triangle_does_not_supply_a_measured_mixed_witness(self):
        first=frame_fixture(frame=1,scales=[(1.,1.)]*4)
        second=frame_fixture(frame=2,scales=[(3.,0.),(1.,1.),(1.,1.),(1.,1.)])
        task,frames=task_fixture(first=first,second=second);view,_=produce(task,frames)
        self.assertIs(get_frame(view,'source_right')['has_confirmed_mixed_witness'],False)
        row=next(r for r in get_trajectory(view,0)['frames'] if r['label']=='source_right')
        self.assertEqual(row['state'],'collapsed');self.assertEqual(row['reason'],'current_zero_area')
        self.assertEqual(row['area_ratio'],0.)

    def test_two_different_extreme_faces_never_become_one_mixed_witness(self):
        first=frame_fixture(frame=1,scales=[(1.,1.)]*4)
        second=frame_fixture(frame=2,scales=[(3.,1.),(1.,.3),(1.,1.),(1.,1.)])
        task,frames=task_fixture(first=first,second=second);view,_=produce(task,frames)
        self.assertIs(get_frame(view,'source_right')['has_confirmed_mixed_witness'],False)
        for item in view['candidate_witness_trajectories']:
            row=next(r for r in item['frames'] if r['label']=='source_right')
            self.assertFalse(row['state']=='measured' and row['principal_stretches'][0]>=1.1 and row['principal_stretches'][1]<=.9)

    def test_unknown_outside_the_core_remains_a_global_partial_fact(self):
        task,frames=task_fixture(first=frame_fixture(frame=1,unknown=(3,)),second=frame_fixture(frame=2,unknown=(3,)))
        view,_=produce(task,frames)
        for label,row in globals_by_label(view).items():
            self.assertEqual(row['states'],dict(measured=3,collapsed=0,unknown=1))
            self.assertEqual(row['triangles_total'],4)
            self.assertEqual(row['unknown_triangle_indices'],[3])
            self.assertEqual(row['unknown_reasons'],{'unweighted_vertex_source':1})
            self.assertEqual(row['status'],'partial')
            core=get_frame(view,label)
            self.assertEqual(core['facts']['core_states']['unknown'],0)
            scope=row['source_validation_scope']
            self.assertEqual(scope['applies_to'],'complete_dependency_source_replay_consistency')
            self.assertIs(scope['physical_measurement_error_certified'],False)
            self.assertIs(scope['geometric_unknowns_remain'],True)

    def test_unknown_core_confirmation_keeps_none_without_false_negative(self):
        first=frame_fixture(frame=1,scales=[(1.,1.)]*4,unknown=(0,))
        second=frame_fixture(frame=2,scales=[(1.,1.)]*4,unknown=(0,1,2))
        task,frames=task_fixture(first=first,second=second);view,_=produce(task,frames)
        self.assertIsNone(get_frame(view,'source_left')['has_confirmed_mixed_witness'])
        self.assertIsNone(get_frame(view,'source_right')['has_confirmed_mixed_witness'])
        self.assertEqual(globals_by_label(view)['source_right']['states']['unknown'],3)

    def test_changed_question_or_threshold_invalidates_existing_task_digest(self):
        task,frames=task_fixture()
        for field in ('question','thresholds'):
            bad=copy.deepcopy(task)
            if field=='question':bad['spec']['question']+=' Changed.'
            else:bad['spec']['thresholds']['high']=1.2
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'deformation_task_view_task_binding'):
                produce(bad,frames)

    def test_wrong_source_anchor_profile_or_core_is_rejected(self):
        task,frames=task_fixture()
        for field in ('source_ref','anchor_id','catalog_sha256','profile_sha256','core_half_extents_m'):
            bad=copy.deepcopy(task);entry=bad['spec']['sources']['source_left']
            if field=='source_ref':entry[field]['frame']['number']+=1
            elif field=='anchor_id':entry[field]='bone-anchor:'+'0'*64
            elif field=='core_half_extents_m':entry[field]=[.5,.5,.5]
            else:entry[field]='0'*64
            bad['task_sha256']=task_view.task_digest(bad['spec'])
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'deformation_task_view_source_binding'):
                produce(bad,frames)

    def test_changed_topology_cannot_keep_same_original_face_identity(self):
        task,frames=task_fixture();changed=copy.deepcopy(frames)
        changed[1]['proof']['triangles'][0]=list(reversed(changed[1]['proof']['triangles'][0]))
        changed[1]['rows']=surface._geometry_rows(changed[1]['proof'],deadline_ns=time.perf_counter_ns()+1_000_000_000)
        with self.assertRaisesRegex(ValueError,'deformation_closure_original_topology'):
            produce(task,changed)

    def test_new_view_keeps_separate_exact_evidence_hash_and_task_binding(self):
        task,frames=task_fixture();view,audit=produce(task,frames)
        self.assertEqual(view['task_binding']['task_sha256'],task['task_sha256'])
        self.assertEqual(view['task_binding']['run_nonce'],task['run_nonce'])
        self.assertEqual(view['task_binding']['condition_id'],task['condition_id'])
        self.assertEqual(view['task_binding']['question'],task['spec']['question'])
        self.assertEqual(view['task_binding']['thresholds'],task['spec']['thresholds'])
        side=context.publication_bytes(audit['evidence_sidecar'])
        self.assertEqual(hashlib.sha256(side).hexdigest(),view['evidence_ref']['sha256'])
        self.assertEqual(len(side),view['evidence_ref']['bytes'])
        published=context.publication_bytes(view)
        self.assertEqual(hashlib.sha256(published).hexdigest(),audit['published_publication_sha256'])
        self.assertEqual(len(published),audit['published_publication_bytes'])

    def test_expired_original_deadline_never_returns_success(self):
        task,frames=task_fixture()
        with self.assertRaisesRegex(ValueError,'rig_pose_original_deadline'):
            produce(task,frames,deadline_ns=1)


if __name__=='__main__':unittest.main()

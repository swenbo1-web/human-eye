"""Regression counterexamples for post-filter witnesses and discrete writes."""
import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from human_eye_plugin import mesh_structure as raw,surface_geometry as g
from human_eye_plugin.surface_reference import (ReferenceIntent,ReferenceRegistry,diagnose,make_view_patch,
    preview_restore,validate_restore_orientation)
from human_eye_plugin.surface_restore import RestoreController,RestoreJournal,MIN_STEP_SHAPE_RATIO
from verification.test_surface_geometry import prepared


def witness_fixture(second=.0003):
    triangles=[[0,1,2],[3,4,5]]
    reference=prepared([[0,0,0],[1,0,0],[0,1,0],[3,0,0],[4,0,0],[3,1,0]],triangles)
    reference['raw']['edges'].append([2,3]);reference=raw.prepare_raw(reference['raw'],{k:reference['source'][k] for k in ('object_id','object_instance','document_epoch','capture_id')})
    value=copy.deepcopy(reference['raw'])
    for i,p in enumerate(value['vertices']):p[2]=.003 if i<3 else second
    target=raw.prepare_raw(value,{k:reference['source'][k] for k in ('object_id','object_instance','document_epoch','capture_id')})
    registry=ReferenceRegistry();ref=registry.bind(reference,target,triangles,[0,1],intent=ReferenceIntent('owned regression','witness filtering','same_index_from_owned_copy'))
    binding=registry.resolve(ref,target);report=diagnose(binding,target,budget=raw.WorkBudget(),threshold_m=.0002)
    return registry,ref,reference,target,binding,report


class WitnessFilterGuards(unittest.TestCase):
    def test_largest_relative_filter_leaving_one_witness_refuses_patch(self):
        _,ref,_,target,binding,report=witness_fixture()
        self.assertEqual(report['changed_count'],6);self.assertEqual(report['cluster_count'],1)
        # Both centroids exceed .0002; only the .003 displacement survives the
        # >= half-largest magnitude filter. Old code emitted a one-item patch.
        with self.assertRaisesRegex(ValueError,'surface_view_witnesses_unavailable'):
            make_view_patch(binding,target,report,0,ref,budget=raw.WorkBudget())

    def test_two_witnesses_surviving_relative_filter_still_publish(self):
        _,ref,_,target,binding,report=witness_fixture(.002)
        result=make_view_patch(binding,target,report,0,ref,budget=raw.WorkBudget())
        self.assertEqual(len(result['witnesses']),2);self.assertEqual({w['triangle'] for w in result['witnesses']},{0,1})

    def test_service_omits_invalid_reference_but_keeps_reference_facts(self):
        from verification.test_surface_tasks import SurfaceTaskTests
        from human_eye_plugin.surface_geometry import PROTOCOL
        harness=SurfaceTaskTests(methodName='runTest');harness.setUp()
        try:
            harness.register();harness.enable();harness.service.config['surface_reference_images_enabled']=True
            registry,ref,_,target,_,_=witness_fixture();harness.host.p=target;harness.host.triangles=[[0,1,2],[3,4,5]]
            harness.service._surface_references=registry
            def capture(request_id,object_id,deadline_ns):
                return dict(schema=PROTOCOL,request_id=request_id,source=copy.deepcopy(target['source']),raw=copy.deepcopy(target['raw']),
                    triangles=[[0,1,2],[3,4,5]],triangle_polygons=[0,1])
            harness.host.capture_surface_source=capture
            value,response=harness.call('post_filter',operation='reference',reference_ref=ref,threshold_m=.0002)
            self.assertFalse(response['isError']);self.assertEqual(value['diagnostic']['changed_count'],6)
            self.assertEqual(value['feature_refs'],[]);self.assertEqual(value['feature_clusters_not_referenced'],1)
            self.assertEqual(len(value['feature_ref_omissions']),1)
            self.assertEqual(value['feature_ref_omissions'][0]['reason'],'surface_view_witnesses_unavailable')
        finally:harness.doCleanups()


class DiscreteRestoreGuards(unittest.TestCase):
    def controller(self,current_points,reference_points,mode='ok'):
        reference=prepared(reference_points,[[0,1,2]]);current=prepared(current_points,[[0,1,2]])
        self.state=copy.deepcopy(current);self.calls=[];registry=ReferenceRegistry();ref=registry.bind(reference,current,[[0,1,2]],[0],
            intent=ReferenceIntent('owned regression','reference oriented triangle','same_index_from_owned_copy'))
        def capture():return raw.prepare_raw(self.state['raw'],{k:current['source'][k] for k in ('object_id','object_instance','document_epoch','capture_id')})
        def setter(index,position):
            self.calls.append((index,position[:]));self.state['raw']['vertices'][index]=position[:]
            if mode=='commit_then_error' and len(self.calls)==1:raise OSError('committed before reply error')
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup);journal=RestoreJournal(Path(folder.name).resolve());self.addCleanup(journal.close)
        return RestoreController(registry,journal=journal,capture=capture,set_vertex=setter,
            approve=lambda scope:dict(approved=True,scope_sha256=g.digest(scope))),ref,reference,current

    def test_final_valid_two_vertex_rotation_cannot_flip_first_step(self):
        a=.0002;initial=[[a,0,0],[0,a,0],[0,0,0]];goal=[[-a,0,0],[0,-a,0],[0,0,0]]
        controller,ref,reference,current=self.controller(initial,goal)
        preview=preview_restore(controller.registry.resolve(ref,current),current,[0,1],budget=raw.WorkBudget())
        self.assertEqual(preview['status'],'preview_only')
        result=controller.restore(ref,[0,1],event_id='intermediate_flip')
        self.assertEqual(result['status'],'failed_checkpoint_restored');self.assertEqual(result['reason'],'surface_restore_orientation_step')
        self.assertEqual((result['setter_attempts'],result['confirmed_changed_setters'],result['rollback_setters']),(0,0,0))
        self.assertEqual(self.state['raw'],current['raw']);self.assertFalse(self.calls)

    def test_final_valid_triangle_cannot_collapse_first_step(self):
        a=.0002;initial=[[a,0,0],[0,a,0],[0,0,0]];goal=[[0,-a,0],[a,0,0],[0,0,0]]
        controller,ref,_,current=self.controller(initial,goal)
        result=controller.restore(ref,[0,1],event_id='intermediate_zero_area')
        self.assertEqual(result['reason'],'surface_restore_degenerate_step');self.assertEqual(result['setter_attempts'],0)
        self.assertEqual(self.state['raw'],current['raw']);self.assertFalse(self.calls)

    def test_preview_unchanged_execution_shape_margin_has_both_sides(self):
        a=.0002;initial=[[a,0,0],[0,a,0],[0,0,0]]
        for factor,expected in ((1,'failed_checkpoint_restored'),(8,'completed')):
            goal=[[factor*MIN_STEP_SHAPE_RATIO*a,-a,0],[a,0,0],[0,0,0]]
            controller,ref,_,current=self.controller(initial,goal)
            self.assertEqual(preview_restore(controller.registry.resolve(ref,current),current,[0,1],budget=raw.WorkBudget())['status'],'preview_only')
            result=controller.restore(ref,[0,1],event_id='margin_'+str(factor));self.assertEqual(result['status'],expected)
            if factor==1:
                self.assertEqual(result['reason'],'surface_restore_near_degenerate_step');self.assertEqual(result['setter_attempts'],0)
            else:self.assertEqual(result['setter_attempts'],2)

    def test_exact_margin_is_scale_and_translation_invariant(self):
        for scale in (1e-4,1.,1e4):
            for origin in (0.,.25):
                for factor,allowed in ((.5,False),(2.,True)):
                    shape=[[origin,origin,0],[origin+scale,origin,0],[origin,origin+scale*factor*MIN_STEP_SHAPE_RATIO,0]]
                    reference=prepared([[origin,origin,0],[origin+scale,origin,0],[origin,origin+scale,0]],[[0,1,2]])
                    binding=dict(reference=reference,triangles=[[0,1,2]])
                    if allowed:validate_restore_orientation(binding,dict(vertices=shape),[2],budget=raw.WorkBudget(),minimum_shape_ratio=MIN_STEP_SHAPE_RATIO)
                    else:
                        with self.assertRaisesRegex(ValueError,'surface_restore_near_degenerate_step'):
                            validate_restore_orientation(binding,dict(vertices=shape),[2],budget=raw.WorkBudget(),minimum_shape_ratio=MIN_STEP_SHAPE_RATIO)

    def test_rollback_cannot_reintroduce_wrong_reference_orientation(self):
        a=.0002;initial=[[-a,0,0],[0,a,0],[0,0,0]];goal=[[a,0,0],[0,a,0],[0,0,0]]
        controller,ref,reference,_=self.controller(initial,goal,'commit_then_error')
        result=controller.restore(ref,[0],event_id='rollback_flip')
        self.assertEqual(result['status'],'unknown_quarantined');self.assertTrue(result['quarantined'])
        self.assertEqual((result['setter_attempts'],result['confirmed_changed_setters'],result['rollback_setters']),(1,1,0))
        self.assertEqual(len(self.calls),1);self.assertEqual(self.state['raw'],reference['raw'])
        # The committed correction remains; never report a restored checkpoint.
        self.assertNotEqual(result['status'],'failed_checkpoint_restored')

    def test_normal_recovery_checks_both_setters_and_preserves_counts(self):
        a=.0002;initial=[[a,0,-.0001],[0,a,0],[0,0,0]];goal=[[a,0,0],[0,a,0],[0,0,0]]
        controller,ref,_,current=self.controller(initial,goal,'commit_then_error')
        with patch('human_eye_plugin.surface_restore.validate_restore_orientation',wraps=validate_restore_orientation) as guard:
            result=controller.restore(ref,[0],event_id='normal_recovery')
        self.assertEqual(result['status'],'failed_checkpoint_restored');self.assertEqual(guard.call_count,2)
        self.assertEqual((result['setter_attempts'],result['confirmed_changed_setters'],result['rollback_setters']),(2,1,1))
        self.assertEqual(self.state['raw'],current['raw'])


if __name__=='__main__':unittest.main()

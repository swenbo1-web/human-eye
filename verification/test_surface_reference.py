import copy,time,unittest,tempfile
from pathlib import Path
from human_eye_plugin import mesh_structure as raw,surface_geometry as g
from human_eye_plugin.surface_reference import ReferenceIntent,ReferenceRegistry,diagnose,preview_restore
from human_eye_plugin.surface_restore import RestoreController,RestoreJournal
from verification.test_surface_geometry import prepared


def fixture():
    triangles=[[0,1,4],[1,2,4],[2,3,4],[3,0,4]]
    reference=prepared([[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0],[0,0,0]],triangles)
    target=copy.deepcopy(reference);target['raw']['vertices'][4][2]=-.0005
    target=raw.prepare_raw(target['raw'],{k:target['source'][k] for k in ('object_id','object_instance','document_epoch','capture_id')})
    registry=ReferenceRegistry();ref=registry.bind(reference,target,triangles,list(range(4)),intent=ReferenceIntent('owned_copy_event','restore approved center','same_index_from_owned_copy'))
    return registry,ref,reference,target,triangles


class ReferenceTests(unittest.TestCase):
    def test_signed_dent_and_normal_groove_negative(self):
        registry,ref,reference,target,_=fixture();binding=registry.resolve(ref,target)
        report=diagnose(binding,target,budget=raw.WorkBudget())
        self.assertEqual(report['changed_count'],1);self.assertAlmostEqual(report['vertices'][0]['signed_normal_m'],-.0005)
        self.assertEqual(report['vertices'][0]['tangential_m'],0)
        # An already grooved trusted reference compared to itself is unchanged.
        binding['reference']=copy.deepcopy(target)
        self.assertEqual(diagnose(binding,target,budget=raw.WorkBudget())['changed_count'],0)

    def test_tangential_is_not_called_normal_dent(self):
        registry,ref,reference,target,_=fixture();target['raw']['vertices'][4]=[.0004,0,0]
        report=diagnose(registry.resolve(ref,target),target,budget=raw.WorkBudget())
        self.assertEqual(report['vertices'][0]['signed_normal_m'],0);self.assertAlmostEqual(report['vertices'][0]['tangential_m'],.0004)

    def test_wrong_topology_frame_scale_or_incarnation(self):
        for change in ('topology','frame','scale','instance','epoch'):
            registry,ref,_,target,_=fixture()
            if change=='topology':target['raw']['polygons'][0].reverse()
            if change=='frame':target['raw']['matrix_world'][0][3]=1
            if change=='scale':target['raw']['unit_scale']=.001
            if change=='instance':target['source']['object_instance']='recreated'
            if change=='epoch':target['source']['document_epoch']='reload'
            with self.assertRaises(ValueError):registry.resolve(ref,target)

    def test_revocation_and_json_cannot_bind_reference(self):
        registry,ref,reference,target,triangles=fixture();registry.revoke(ref)
        with self.assertRaises(ValueError):registry.resolve(ref,target)
        with self.assertRaises(ValueError):registry.bind(reference,target,triangles,list(range(4)),intent={'approved':True})

    def test_reversed_normals_unknown_not_healthy(self):
        registry,ref,reference,target,_=fixture();binding=registry.resolve(ref,target);binding['triangles'][1].reverse()
        report=diagnose(binding,target,budget=raw.WorkBudget())
        self.assertEqual(report['status'],'partial');self.assertGreater(report['unreliable_normal_count'],0)
        self.assertEqual(report['changed_count'],1)
        self.assertEqual(report['changed_with_unreliable_normal_count'],1)
        self.assertIsNone(report['vertices'][0]['signed_normal_m'])

    def test_far_origin_translation_cancels(self):
        registry,ref,reference,target,_=fixture();binding=registry.resolve(ref,target)
        binding['reference']['raw']['matrix_world'][0][3]=target['raw']['matrix_world'][0][3]=2**40
        self.assertAlmostEqual(diagnose(binding,target,budget=raw.WorkBudget())['vertices'][0]['signed_normal_m'],-.0005)

    def test_preview_no_mutation_protection_and_size_gate(self):
        registry,ref,reference,target,_=fixture();before=copy.deepcopy(target)
        proposal=preview_restore(registry.resolve(ref,target),target,[4],budget=raw.WorkBudget())
        self.assertEqual(target,before);self.assertEqual(proposal['protected_vertex_count'],4);self.assertFalse(proposal['execution_authority'])
        with self.assertRaises(ValueError):preview_restore(registry.resolve(ref,target),target,[4],budget=raw.WorkBudget(),max_displacement_m=.0001)


class RestoreTests(unittest.TestCase):
    def setup_controller(self,mode='ok',answer=True):
        registry,ref,reference,target,_=fixture();self.state=copy.deepcopy(target);self.calls=[];self.reads=0
        def capture():
            self.reads+=1
            if mode=='read_loss' and self.calls:raise OSError('lost readback')
            return raw.prepare_raw(self.state['raw'],{k:self.state['source'][k] for k in ('object_id','object_instance','document_epoch','capture_id')})
        def setter(i,p):
            self.calls.append((i,p));self.state['raw']['vertices'][i]=p[:]
            if mode=='commit_then_error' and len(self.calls)==1:raise OSError('committed before exception')
            if mode=='rollback_error':raise OSError('every setter committed then raised')
            if mode=='protected_edit':self.state['raw']['vertices'][0][0]+=.01
        def approve(scope):return dict(approved=answer,scope_sha256=g.digest(scope))
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);journal=RestoreJournal(Path(tmp.name).resolve());self.addCleanup(journal.close)
        return RestoreController(registry,journal=journal,capture=capture,set_vertex=setter,approve=approve),ref,reference,target

    def test_native_contract_success_and_duplicate_no_retry(self):
        controller,ref,reference,target=self.setup_controller()
        result=controller.restore(ref,[4],event_id='goal1')
        self.assertEqual(result['status'],'completed');self.assertEqual(result['confirmed_changed_setters'],1)
        self.assertEqual(self.state['raw'],reference['raw'])
        with self.assertRaises(ValueError):controller.restore(ref,[4],event_id='goal1')
        self.assertEqual(len(self.calls),1)

    def test_no_effect_is_zero_setters_when_already_restored(self):
        controller,ref,reference,target=self.setup_controller();self.state['raw']=copy.deepcopy(reference['raw'])
        result=controller.restore(ref,[4],event_id='satisfied');self.assertEqual(result['setter_attempts'],0)

    def test_numeric_approval_and_wrong_scope_never_write(self):
        for answer in (False,1,None):
            controller,ref,_,_=self.setup_controller(answer=answer)
            with self.assertRaises(ValueError):controller.restore(ref,[4],event_id='denied')
            self.assertFalse(self.calls)
        controller,ref,_,_=self.setup_controller();controller.approve=lambda scope:dict(approved=True,scope_sha256='wrong')
        with self.assertRaises(ValueError):controller.restore(ref,[4],event_id='wrong');self.assertFalse(self.calls)

    def test_committed_exception_counted_then_checkpoint_restored(self):
        controller,ref,_,target=self.setup_controller('commit_then_error');r=controller.restore(ref,[4],event_id='exception')
        self.assertEqual(r['status'],'failed_checkpoint_restored');self.assertEqual(r['setter_attempts'],2)
        self.assertEqual(r['confirmed_changed_setters'],1);self.assertEqual(r['rollback_setters'],1)
        self.assertEqual(self.state['raw'],target['raw'])

    def test_unknown_after_apply_quarantines_and_never_retries(self):
        controller,ref,_,_=self.setup_controller('read_loss');r=controller.restore(ref,[4],event_id='unknown')
        self.assertEqual(r['status'],'unknown_quarantined');self.assertIsNone(r['protected_vertices_unchanged'])
        self.assertEqual(len(self.calls),1)
        with self.assertRaises(ValueError):controller.restore(ref,[4],event_id='new_budget')
        self.assertEqual(len(self.calls),1)

    def test_protected_mutation_no_blind_recovery(self):
        controller,ref,_,_=self.setup_controller('protected_edit');r=controller.restore(ref,[4],event_id='protect')
        self.assertEqual(r['status'],'unknown_quarantined');self.assertEqual(len(self.calls),1)

    def test_rollback_exception_quarantines(self):
        controller,ref,_,_=self.setup_controller('rollback_error');r=controller.restore(ref,[4],event_id='rollback')
        self.assertEqual(r['status'],'unknown_quarantined');self.assertEqual(len(self.calls),2)

    def test_original_deadline_not_renewed_during_approval(self):
        controller,ref,_,_=self.setup_controller();now=time.perf_counter_ns();controller.clock=lambda:now
        def expired(scope):
            nonlocal now
            now=scope['deadline_ns'];return dict(approved=True,scope_sha256=g.digest(scope))
        controller.approve=expired
        with self.assertRaises(ValueError):controller.restore(ref,[4],event_id='expired')
        self.assertFalse(self.calls)

    def test_callback_reentry_cannot_start_second_goal(self):
        controller,ref,_,_=self.setup_controller();original=controller.approve
        def reenter(scope):
            with self.assertRaisesRegex(ValueError,'restore_busy'):controller.restore(ref,[4],event_id='nested')
            return original(scope)
        controller.approve=reenter
        self.assertEqual(controller.restore(ref,[4],event_id='outer')['status'],'completed')
        self.assertEqual(len(self.calls),1)

    def test_revoked_in_approval_cannot_dispatch(self):
        controller,ref,_,_=self.setup_controller()
        def revoked(scope):
            controller.registry.revoke(ref);return dict(approved=True,scope_sha256=g.digest(scope))
        controller.approve=revoked
        result=controller.restore(ref,[4],event_id='revoked')
        self.assertEqual(result['status'],'unknown_quarantined');self.assertFalse(self.calls)

    def test_restart_after_unknown_never_restores_budget(self):
        controller,ref,_,_=self.setup_controller('read_loss');controller.restore(ref,[4],event_id='uncertain')
        journal=controller.journal;root=journal.root;journal.close()
        fresh=RestoreJournal(root);self.addCleanup(fresh.close)
        self.assertTrue(fresh.poisoned);self.assertIsNone(fresh.history['rows'][0]['setter_count'])
        other=RestoreController(controller.registry,journal=fresh,capture=controller.capture,set_vertex=controller.set_vertex,approve=controller.approve)
        with self.assertRaises(ValueError):other.restore(ref,[4],event_id='new_attempt')
        self.assertEqual(len(self.calls),1)

    def test_restart_historical_completion_not_reexecution(self):
        controller,ref,_,_=self.setup_controller();controller.restore(ref,[4],event_id='done')
        root=controller.journal.root;controller.journal.close();fresh=RestoreJournal(root);self.addCleanup(fresh.close)
        self.assertFalse(fresh.poisoned);self.assertEqual(fresh.history['rows'][0]['setter_count'],1)
        self.assertEqual(fresh.history['rows'][0]['scope']['indices'],[4])
        self.assertEqual(fresh.history['rows'][0]['scope']['event_id'],'done')
        other=RestoreController(controller.registry,journal=fresh,capture=controller.capture,set_vertex=controller.set_vertex,approve=controller.approve)
        with self.assertRaises(ValueError):other.restore(ref,[4],event_id='done')
        self.assertEqual(len(self.calls),1)

    def test_second_writer_and_unfinished_slot_rejected(self):
        controller,_,_,_=self.setup_controller();root=controller.journal.root
        with self.assertRaises(OSError):RestoreJournal(root)
        controller.journal.begin('crashed_before_first_setter');controller.journal.close()
        fresh=RestoreJournal(root);self.addCleanup(fresh.close);self.assertTrue(fresh.poisoned)
        self.assertIsNone(fresh.history['rows'][0]['setter_count'])

    def test_journal_commit_failure_after_physical_write_preserves_uncertainty(self):
        controller,ref,_,_=self.setup_controller();publish=controller.journal.update
        def failure(ticket,event,stage,**fields):
            if stage=='finished':raise OSError('final acknowledgement lost')
            return publish(ticket,event,stage,**fields)
        controller.journal.update=failure
        result=controller.restore(ref,[4],event_id='commit_lost')
        self.assertEqual(result['status'],'unknown_journal_commit');self.assertEqual(len(self.calls),1)
        self.assertTrue(RestoreJournal.inspect(controller.journal.root)['unknown'])


if __name__=='__main__':unittest.main()

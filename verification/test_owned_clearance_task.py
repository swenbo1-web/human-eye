"""Real rigid authority/ledger with host doubles; no physical or human claims."""
import copy,hashlib,json,time,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from human_eye_plugin.owned_clearance_task import OperatorClearanceTask
from human_eye_plugin.runtime_identity import runtime_identity
from human_eye_plugin.task_entry import TrustedTaskEntry
from human_eye_plugin.task_authority import TaskApproval,ClearanceTaskSpec
from human_eye_plugin.surface_restore import RestoreJournal,RestoreController
from verification import test_task_entry as setup
from verification.test_surface_reference import fixture


class ClearanceOperatorTests(unittest.TestCase):
    setUp=setup.TaskEntryTests.setUp
    approve=setup.TaskEntryTests.approve
    mock_entry=setup.TaskEntryTests.mock_entry
    state=setup.TaskEntryTests.state
    write=setup.TaskEntryTests.write

    def task(self,*,name='task',extra=None):
        self.root=self.root.resolve();scene=self.root/'fixture.blend';binary=self.root/'blender.exe'
        scene.write_bytes(b'owned test scene');binary.write_bytes(b'operator binary double')
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        profile=dict(schema='owned-clearance-operator-profile-v1',scene_file=str(scene),scene_sha256=sha(scene),
            blender_executable=str(binary),blender_sha256=sha(binary),connector_config=str(self.config.resolve()),
            connector_config_sha256=sha(self.config),runtime_source_sha256=runtime_identity()['source_sha256'],
            task=dict(focal_id='part',reference_id='base',reference_triangle_index=2))
        if extra:profile.update(extra)
        path=self.root/(name+'-PROFILE.json');path.write_text(json.dumps(profile),encoding='utf8')
        from human_eye_plugin import blender_process
        worker=Path(blender_process.__file__).resolve().with_name('blender_worker.py')
        self.host._process.args=[str(binary),'--factory-startup','--disable-autoexec','--background',str(scene),'--python',str(worker),'--',str(worker.parents[1])]
        self.profile=path;return OperatorClearanceTask(path,self.root/name,clock=lambda:self.now)

    def entry_factory(self,config,host,authority,*,source_observer):
        entry=TrustedTaskEntry(config,host,authority,source_observer=source_observer);self.mock_entry(entry)
        entry.execute=Mock(return_value=dict(status='review_required',new_setter_count=0,execution_authority=False))
        self.minted=entry;return entry

    def run_task(self,task):
        with patch('human_eye_plugin.owned_clearance_task.owned_host_counter'),patch('human_eye_plugin.owned_clearance_task.TrustedTaskEntry',side_effect=self.entry_factory):
            return task.run(self.host)

    def test_real_grant_and_ledger_receive_original_window_once(self):
        task=self.task();self.now+=2.;result=self.run_task(task)
        admission=result['admission'];self.assertEqual(admission['original_started_monotonic'],100.)
        self.assertEqual(admission['original_deadline_monotonic'],130.);self.assertEqual(task.approval_used,True)
        self.assertEqual(result['authorization_mode'],'explicit_operator_rigid_task');self.assertIs(result['human_form_verified'],False)
        self.assertTrue((task.root/'APPROVAL.json').is_file());self.assertTrue((task.root/'RESULT.json').is_file())
        self.minted.execute.assert_called_once()
        with self.assertRaises(ValueError):self.run_task(task)
        self.minted.execute.assert_called_once()

    def test_root_never_reissues_even_if_receipt_incomplete(self):
        task=self.task()
        with self.assertRaises(FileExistsError):OperatorClearanceTask(self.profile,task.root,clock=lambda:self.now)

    def test_wrong_domain_profile_or_model_authority_fields_rejected(self):
        for name,extra in [('surface',{'schema':'owned-surface-operator-config-v1'}),('fake',{'approved':True})]:
            with self.assertRaises(ValueError):self.task(name=name,extra=extra)

    def test_json_duplicate_nonfinite_and_indices_cannot_be_rigid_task(self):
        task=self.task();value=json.loads(self.profile.read_text())
        for invalid in ({'indices':[12]},{'focal_id':'part','reference_id':'base','approved':True},
                {'focal_id':'part','reference_id':'base','target_clearance_m':True}):
            value['task']=invalid;path=self.root/'INVALID.json';path.write_text(json.dumps(value))
            with self.assertRaises((ValueError,TypeError)):OperatorClearanceTask(path,self.root/'bad',clock=lambda:self.now)

    def test_original_deadline_not_renewed_by_initialization(self):
        task=self.task();self.now=130.
        with self.assertRaises(ValueError):self.run_task(task)
        self.assertFalse(self.config.with_name('state.json').exists())

    def test_profile_config_scene_or_runtime_pin_change_prevents_registration(self):
        for which in ('profile','config','scene','runtime'):
            task=self.task(name=which);original=self.config.read_bytes()
            if which=='profile':self.profile.write_bytes(self.profile.read_bytes()+b' ')
            elif which=='config':self.config.write_bytes(original+b' ')
            elif which=='scene':(self.root/'fixture.blend').write_bytes(b'changed')
            else:task.profile['runtime_source_sha256']='0'*64
            with self.assertRaises(ValueError):self.run_task(task)
            self.config.write_bytes(original)

    def test_wrong_host_cannot_become_trusted_by_profile(self):
        task=self.task()
        with self.assertRaises(ValueError):task.run(self.host)
        self.assertFalse(self.config.with_name('state.json').exists())

    def test_fixed_worker_protocol_is_not_enough_with_another_input_scene(self):
        task=self.task();self.host._process.args[4]=str(self.root/'different.blend')
        with self.assertRaisesRegex(ValueError,'actual_worker_launch'):self.run_task(task)
        self.assertFalse(self.config.with_name('state.json').exists())

    def test_approval_record_failure_prevents_execute(self):
        task=self.task();publish=task._publish
        def failed(name,value):
            if name=='APPROVAL.json':raise OSError('cannot record approval')
            return publish(name,value)
        task._publish=failed
        with self.assertRaises(ValueError):self.run_task(task)
        self.minted.execute.assert_not_called();self.assertFalse(self.minted._live)

    def test_pending_record_failure_stops_live_entry_before_execute(self):
        task=self.task();publish=task._publish
        def failed(name,value):
            if name=='EXECUTE_PENDING.json':raise OSError('cannot record dispatch intent')
            return publish(name,value)
        task._publish=failed
        with self.assertRaises(OSError):self.run_task(task)
        self.minted.execute.assert_not_called();self.assertTrue(task.closed)
        self.assertFalse(self.minted.snapshot(task.admitted['registration_id'])['live_registration_available'])

    def test_result_publish_failure_preserves_known_kernel_count_and_unknown_receipt(self):
        task=self.task();publish=task._publish
        def failed(name,value):
            if name=='RESULT.json':raise OSError('lost post-execution receipt')
            return publish(name,value)
        task._publish=failed
        result=self.run_task(task)
        self.assertEqual(result['new_setter_count'],0);self.assertEqual(result['status'],'review_required')
        self.assertEqual(result['task_receipt_persistence'],'unknown')
        self.assertTrue(task.started_execution);self.assertTrue(task.closed);self.minted.execute.assert_called_once()

    def test_wrong_scope_or_typed_vertex_authority_cannot_approve(self):
        task=self.task();real=task._approve
        def wrong(spec,scope):scope=copy.deepcopy(scope);scope['process_id']+=1;return real(spec,scope)
        task._approve=wrong
        with self.assertRaises(ValueError):self.run_task(task)
        self.minted.execute.assert_not_called()

    def test_scope_binding_rejects_other_task_budget_before_authority(self):
        task=self.task();real=task._bind_source
        def changed(spec,scope,packet):
            from dataclasses import replace
            return real(replace(spec,target_clearance_m=.002),scope,packet)
        task._bind_source=changed
        with self.assertRaises(ValueError):self.run_task(task)
        self.minted.execute.assert_not_called();self.assertFalse(task.approval_used)

    def test_protection_includes_reference_local_mesh_frame_and_world_xy(self):
        task=self.task();before=copy.deepcopy(self.packet)
        self.assertTrue(task._protected(before,copy.deepcopy(before)))
        for mutation in (lambda v:v['capture']['host_identity'].__setitem__('document_epoch','b'*64),
                lambda v:v['native_scene']['objects'][0]['local_vertices'][0].__setitem__(0,99),
                lambda v:v['native_scene']['objects'][0]['matrix'][0].__setitem__(3,99),
                lambda v:v['native_scene']['objects'][1]['matrix'][2].__setitem__(0,.1)):
            after=copy.deepcopy(before);mutation(after);self.assertFalse(task._protected(before,after))

    def test_rigid_typed_approval_cannot_authorize_vertex_kernel(self):
        import tempfile
        registry,ref,reference,target,triangles=fixture();calls=[]
        with tempfile.TemporaryDirectory() as folder:
            journal=RestoreJournal(Path(folder).resolve())
            try:
                controller=RestoreController(registry,journal=journal,capture=lambda:copy.deepcopy(target),
                    set_vertex=lambda *v:calls.append(v),approve=lambda _:TaskApproval('rigid','operator'))
                with self.assertRaises(ValueError):controller.restore(ref,[4],event_id='cross-domain')
                self.assertFalse(calls)
            finally:journal.close()


if __name__=='__main__':unittest.main()

"""Real ledger/authority, isolated host/evidence doubles; never physical proof."""
import copy,json,tempfile,unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from human_eye_plugin import task_authority as a
from human_eye_plugin.task_entry import TrustedTaskEntry,TaskEntryError
from human_eye_plugin.forward_deadline import counter_descriptor
from verification.test_owned_goal_trial_adapter import original_packet


class TaskEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.config=self.root/'config.json';self.config.write_text(json.dumps(dict(schema_version='1.0',enabled=True,
            project_root=str(Path(__file__).resolve().parents[1]),state_file='state.json',audit_file='audit.jsonl',quad_size=64,max_sessions=4)))
        self.now=100.;self.packet=original_packet();self.event='event1';self.approval='approval1';self.callback=None;self.calls=0
        def forbidden(*args,**kwargs):raise AssertionError('unit host I/O forbidden')
        self.host=SimpleNamespace(_process=SimpleNamespace(pid=1234),capture_scene=forbidden,apply_transform=forbidden)
        self.authority=a.TrustedTaskAuthority('local-test',self.approve)
        self.entry=TrustedTaskEntry(self.config,self.host,self.authority)
        self.mock_entry(self.entry)
        self.clock=patch('human_eye_plugin.task_entry.time.perf_counter',side_effect=lambda:self.now)
        self.clock.start();self.addCleanup(self.clock.stop)
        self.cap=patch('human_eye_plugin.task_entry.owned_host_counter',return_value=counter_descriptor())
        self.cap.start();self.addCleanup(self.cap.stop)
        self.spec=a.ClearanceTaskSpec('part','base',reference_triangle_index=2)

    def approve(self,spec,scope):
        self.calls+=1
        if self.callback is not None:return self.callback(spec,scope)
        return a.TaskApproval(self.event,self.approval)

    def mock_entry(self,entry):
        entry._scheduler._capture=lambda:copy.deepcopy(self.packet)
        entry._scheduler._discover=lambda *args:dict(reference_triangle_index=2)

    def state(self):return json.loads(self.entry.service.state_path.read_text())
    def write(self,state):self.entry.service.state_path.write_text(json.dumps(state))
    def registered(self):
        value=self.entry.register(self.spec);self.assertEqual(value['status'],'registered',value);return value

    def test_registration_uses_original_ledger_and_never_calls_scheduler_run(self):
        with patch.object(self.entry._scheduler,'run',side_effect=AssertionError('dispatch forbidden')):
            value=self.registered()
        state=self.state();self.assertEqual(len(state['goal_authorizations']['records']),1)
        parent=state['goal_supervision']['records'][value['goal_id']]
        self.assertEqual(parent['children'],[]);self.assertEqual(parent['started_monotonic'],100.)
        self.assertTrue(value['live_registration_available']);self.assertFalse(value['execution_authority']);self.assertEqual(value['new_setter_count'],0)
        self.assertEqual(value['original_deadline_monotonic'],100+self.spec.limits.max_duration_s)

    def test_model_JSON_cannot_create_task_or_authority(self):
        for value in (self.spec.to_dict(),dict(approved=True,execution_authority=True),None):
            with self.assertRaisesRegex(TaskEntryError,'not_JSON'):self.entry.register(value)
        with self.assertRaises(ValueError):TrustedTaskEntry(self.config,self.host,dict(approved=True))
        self.assertEqual(self.calls,0);self.assertFalse(self.entry.service.state_path.exists())

    def test_denial_and_JSON_approval_cannot_persist_authorization(self):
        for returned in (None,False,dict(event_id='e',authorization_id='a')):
            self.callback=lambda *args:returned
            with self.assertRaises(TaskEntryError):self.entry.register(self.spec)
        self.assertFalse(self.entry.service.state_path.exists());self.assertFalse(self.entry._live)

    def test_capture_and_callback_spend_original_window(self):
        def approve(*args):self.now+=2.;return a.TaskApproval(self.event,self.approval)
        self.callback=approve;value=self.registered()
        self.assertEqual(value['original_started_monotonic'],100.)
        self.assertEqual(value['original_deadline_monotonic'],100+self.spec.limits.max_duration_s)

    def test_expired_callback_does_not_get_fresh_window(self):
        def approve(*args):self.now+=self.spec.limits.max_duration_s;return a.TaskApproval(self.event,self.approval)
        self.callback=approve
        with self.assertRaises(TaskEntryError):self.entry.register(self.spec)
        self.assertFalse(self.entry.service.state_path.exists());self.assertFalse(self.entry._live)

    def test_duplicate_preserves_first_grant_deadline_budget_and_snapshot(self):
        first=self.registered();before=self.state();grant=self.entry._live[first['registration_id']]['grant'];self.now+=3
        again=self.entry.register(self.spec);self.assertTrue(again['duplicate_event'])
        self.assertEqual(again['original_deadline_monotonic'],first['original_deadline_monotonic'])
        self.assertEqual(self.state(),before);self.assertIs(self.entry._live[first['registration_id']]['grant'],grant)

    def test_duplicate_spec_conflict_cannot_rebind(self):
        first=self.registered();state=self.state();changed=replace(self.spec,target_clearance_m=.002)
        value=self.entry.register(changed);self.assertEqual(value['status'],'review_required');self.assertFalse(value['live_registration_available'])
        self.assertEqual(self.state()['goal_authorizations']['records'][first['registration_id']]['grant'],
            state['goal_authorizations']['records'][first['registration_id']]['grant'])

    def test_duplicate_snapshot_change_cannot_rebind(self):
        first=self.registered();old=self.state()['goal_authorizations']['records'][first['registration_id']]['grant']
        self.packet['capture']['revision']='external-edit'
        self.packet['capture_confirmation']['revision']='external-edit'
        value=self.entry.register(self.spec);self.assertEqual(value['status'],'review_required');self.assertFalse(value['live_registration_available'])
        self.assertEqual(self.state()['goal_authorizations']['records'][first['registration_id']]['grant'],old)

    def test_restart_cannot_restore_live_registration_from_JSON(self):
        first=self.registered();new=TrustedTaskEntry(self.config,self.host,a.TrustedTaskAuthority('local-test',self.approve));self.mock_entry(new)
        receipt=new.snapshot(first['registration_id']);self.assertFalse(receipt['live_registration_available']);self.assertFalse(receipt['current_scene_revalidated'])
        self.now+=1;again=new.register(self.spec);self.assertEqual(again['status'],'review_required')
        self.assertEqual(again['original_deadline_monotonic'],first['original_deadline_monotonic'])

    def test_revoke_and_repeat_revoke_block_without_clearing_history(self):
        first=self.registered();key=first['registration_id'];result=self.entry.revoke(key)
        self.assertEqual(result['status'],'revoked');self.assertFalse(result['live_registration_available'])
        state=self.state();self.assertEqual(state['goal_supervision']['records'][first['goal_id']]['status'],'frozen')
        self.assertEqual(self.entry.revoke(key)['status'],'revoked');self.assertEqual(self.state(),state)
        replay=self.entry.register(self.spec);self.assertEqual(replay['original_deadline_monotonic'],first['original_deadline_monotonic'])
        self.assertFalse(replay['live_registration_available'])

    def test_different_event_cannot_reset_blocked_budget(self):
        self.registered();before=self.state();self.event='event2'
        with self.assertRaises(TaskEntryError):self.entry.register(self.spec)
        self.assertEqual(self.state(),before)

    def test_unknown_or_other_issuer_cannot_read_or_revoke(self):
        first=self.registered();other=TrustedTaskEntry(self.config,self.host,a.TrustedTaskAuthority('other',self.approve));self.mock_entry(other)
        for call in (lambda:other.snapshot(first['registration_id']),lambda:other.revoke(first['registration_id']),lambda:self.entry.snapshot('0'*64)):
            with self.assertRaises(ValueError):call()
        self.assertTrue(self.entry.snapshot(first['registration_id'])['live_registration_available'])

    def test_scene_change_during_approval_does_not_claim(self):
        def approve(*args):self.packet['capture']['revision']='changed';return a.TaskApproval(self.event,self.approval)
        self.callback=approve
        with self.assertRaises(TaskEntryError):self.entry.register(self.spec)
        self.assertFalse(self.entry.service.state_path.exists());self.assertFalse(self.entry._live)

    def test_config_change_during_approval_does_not_claim(self):
        def approve(*args):self.config.write_text(self.config.read_text()+' ');return a.TaskApproval(self.event,self.approval)
        self.callback=approve
        with self.assertRaises(TaskEntryError):self.entry.register(self.spec)
        self.assertFalse(self.entry.service.state_path.exists())

    def test_live_snapshot_rechecks_source_config_process_and_scene(self):
        first=self.registered();key=first['registration_id'];self.assertTrue(self.entry.snapshot(key)['current_scene_revalidated'])
        self.host._process=SimpleNamespace(pid=5678)
        value=self.entry.snapshot(key);self.assertFalse(value['live_registration_available']);self.assertEqual(value['status'],'review_required')

    def test_expiry_keeps_original_deadline_and_freezes(self):
        first=self.registered();self.now=first['original_deadline_monotonic']
        receipt=self.entry.snapshot(first['registration_id']);self.assertFalse(receipt['live_registration_available'])
        self.assertEqual(receipt['original_deadline_monotonic'],first['original_deadline_monotonic'])
        self.assertEqual(receipt['durable_status'],'frozen')

    def test_corrupt_ledger_revokes_memory_on_snapshot_and_revoke(self):
        first=self.registered();key=first['registration_id'];path=self.entry.service.state_path;path.write_text('{}')
        with self.assertRaises(ValueError):self.entry.revoke(key)
        self.assertTrue(self.entry._live[key]['revoked'].is_set())
        with self.assertRaises(ValueError):self.entry.snapshot(key)

    def test_postcommit_lost_ack_preserves_blocker_without_live_capability(self):
        original=self.entry.service._save;calls=[0]
        def save(*args,**kwargs):
            original(*args,**kwargs);calls[0]+=1
            if calls[0]==1:raise OSError('lost commit acknowledgment')
        with patch.object(self.entry.service,'_save',side_effect=save):result=self.entry.register(self.spec)
        self.assertEqual(result['status'],'review_required');self.assertFalse(result['live_registration_available'])
        state=self.state();self.assertEqual(len(state['goal_authorizations']['records']),1)
        self.assertEqual(next(iter(state['goal_authorizations']['records'].values()))['status'],'frozen')

    def test_precommit_failure_never_returns_live_and_same_process_will_not_reclaim(self):
        with patch.object(self.entry.service,'_save',side_effect=OSError('before commit')):
            with self.assertRaises(TaskEntryError):self.entry.register(self.spec)
        self.assertFalse(self.entry.service.state_path.exists());self.assertFalse(self.entry._live)
        with self.assertRaises(TaskEntryError):self.entry.register(self.spec)
        self.assertFalse(self.entry.service.state_path.exists())

    def test_revoke_save_failure_still_revokes_memory(self):
        first=self.registered();key=first['registration_id']
        with patch.object(self.entry.service,'_save',side_effect=OSError('disk unavailable')):receipt=self.entry.revoke(key)
        self.assertEqual(receipt['persistence'],'unknown');self.assertFalse(receipt['live_registration_available'])

    def test_parent_budget_or_frozen_state_cannot_be_eligible(self):
        first=self.registered();state=self.state();state['goal_supervision']['records'][first['goal_id']].update(status='frozen',reason='operator_review')
        self.write(state)
        with self.assertRaises(TaskEntryError):self.entry.snapshot(first['registration_id'])
        self.assertTrue(self.entry._live[first['registration_id']]['revoked'].is_set())

    def test_parent_budget_tamper_revokes_live_memory(self):
        first=self.registered();state=self.state();state['goal_supervision']['records'][first['goal_id']]['limits']['max_steps']=1
        self.write(state)
        with self.assertRaises(ValueError):self.entry.snapshot(first['registration_id'])
        self.assertTrue(self.entry._live[first['registration_id']]['revoked'].is_set())

    def test_source_rejection_freezes_without_reissuing(self):
        first=self.registered()
        with patch.object(self.entry.service,'_identity_rejection',return_value={'status':'rejected'}):result=self.entry.snapshot(first['registration_id'])
        self.assertEqual(result['durable_status'],'frozen');self.assertFalse(result['live_registration_available'])

    def test_clock_domain_change_freezes(self):
        first=self.registered()
        with patch('human_eye_plugin.task_entry.owned_host_counter',return_value={'other_clock':'untrusted'}):result=self.entry.snapshot(first['registration_id'])
        self.assertEqual(result['durable_status'],'frozen');self.assertFalse(result['live_registration_available'])

    def test_config_bytes_are_durable_and_restart_does_not_relabel_them(self):
        first=self.registered();self.config.write_text(self.config.read_text()+' ')
        new=TrustedTaskEntry(self.config,self.host,a.TrustedTaskAuthority('local-test',self.approve));self.mock_entry(new)
        receipt=new.snapshot(first['registration_id'])
        self.assertEqual(receipt['config_sha256'],first['config_sha256']);self.assertFalse(receipt['live_registration_available'])
        self.assertNotEqual(receipt['config_sha256'],new._config_sha)
        replay=new.register(self.spec);self.assertFalse(replay['live_registration_available'])
        self.assertEqual(replay['config_sha256'],first['config_sha256'])

    def test_changed_geometry_at_live_check_freezes(self):
        first=self.registered();self.packet['native_scene']['objects'][0]['world_vertices'][0][0]+=.01
        receipt=self.entry.snapshot(first['registration_id'])
        self.assertFalse(receipt['live_registration_available']);self.assertEqual(receipt['durable_status'],'frozen')

    def test_missing_state_cannot_reclaim_an_accepted_event_in_live_entry(self):
        first=self.registered();self.entry.service.state_path.unlink()
        with self.assertRaises(TaskEntryError):self.entry.register(self.spec)
        self.assertTrue(self.entry._live[first['registration_id']]['revoked'].is_set())
        self.assertFalse(self.entry.service.state_path.exists())

    def test_revoke_marks_memory_before_waiting_for_entry_lock(self):
        import threading
        first=self.registered();key=first['registration_id'];results=[]
        thread=threading.Thread(target=lambda:results.append(self.entry.revoke(key)))
        with self.entry._lock:
            thread.start();self.assertTrue(self.entry._live[key]['revoked'].wait(timeout=1))
        thread.join(timeout=3);self.assertFalse(thread.is_alive());self.assertEqual(results[0]['status'],'revoked')

    def test_config_change_during_construction_is_rejected(self):
        from human_eye_plugin.goal_scheduler import OwnedGoalScheduler
        def build(*args):
            scheduler=OwnedGoalScheduler(*args);self.config.write_bytes(self.config.read_bytes()+b' ');return scheduler
        with patch('human_eye_plugin.task_entry.OwnedGoalScheduler',side_effect=build):
            with self.assertRaisesRegex(TaskEntryError,'during_construction'):TrustedTaskEntry(self.config,self.host,self.authority)

    def test_config_ABA_during_construction_must_match_loaded_values(self):
        from human_eye_plugin.goal_scheduler import OwnedGoalScheduler
        original=self.config.read_bytes();changed=json.loads(original);changed['enabled']=False
        def build(*args):
            self.config.write_text(json.dumps(changed));scheduler=OwnedGoalScheduler(*args);self.config.write_bytes(original);return scheduler
        with patch('human_eye_plugin.task_entry.OwnedGoalScheduler',side_effect=build):
            with self.assertRaisesRegex(TaskEntryError,'loaded_config_binding'):TrustedTaskEntry(self.config,self.host,self.authority)


class ReceiptWindowTests(unittest.TestCase):
    def test_default_authority_behavior_and_optional_original_start(self):
        from verification.test_task_authority import scope
        spec=a.ClearanceTaskSpec('part','base');issuer=a.TrustedTaskAuthority('test',lambda *args:a.TaskApproval('e','a'))
        with patch('human_eye_plugin.task_authority.time.perf_counter',return_value=100.):
            self.assertEqual(issuer.issue(spec,scope()).issued_monotonic,100.)
            self.assertEqual(issuer.issue(spec,scope(),received_monotonic=98.).issued_monotonic,98.)
            for start in (101.,True,100-spec.limits.max_duration_s,float('nan')):
                with self.assertRaises(ValueError):issuer.issue(spec,scope(),received_monotonic=start)


if __name__=='__main__':unittest.main()

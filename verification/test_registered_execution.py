"""Entry/commit contracts with doubles; physical proof lives in owned preflight."""
import copy,threading,unittest
from unittest.mock import patch
from human_eye_plugin.task_entry import TrustedTaskEntry,_TaskHandoff
from human_eye_plugin.task_authority import TrustedTaskAuthority
from human_eye_plugin.host_runtime import GuardedHostRuntime
from verification import test_task_entry as setup
from verification.test_host_runtime import MutableHost


class RegisteredExecutionTests(unittest.TestCase):
    setUp=setup.TaskEntryTests.setUp
    approve=setup.TaskEntryTests.approve
    mock_entry=setup.TaskEntryTests.mock_entry
    registered=setup.TaskEntryTests.registered
    state=setup.TaskEntryTests.state
    write=setup.TaskEntryTests.write

    def test_JSON_and_foreign_objects_cannot_handoff(self):
        for value in (None,{},dict(approved=True)):
            with self.assertRaises(ValueError):self.entry._scheduler.run_registered(value)
        with self.assertRaises(ValueError):_TaskHandoff()

    def test_one_live_handoff_never_reissues_or_reclaims(self):
        r=self.registered();key=r['registration_id'];live=self.entry._live[key];original=live['grant'];before=self.state()
        # Real registered branch reaches transaction() after take(), and stops
        # because this unit host intentionally has no execution capabilities.
        with (patch.object(self.authority,'issue',side_effect=AssertionError('reissue')),
              patch.object(self.entry._scheduler,'_claim',side_effect=AssertionError('reclaim'))):
            result=self.entry.execute(key)
        self.assertEqual(result['status'],'review_required');self.assertIs(live['grant'],original)
        self.assertEqual(self.calls,1);self.assertTrue(live['handoff'].used)
        state=self.state();parent=state['goal_supervision']['records'][r['goal_id']]
        old=before['goal_supervision']['records'][r['goal_id']]
        self.assertEqual(parent['started_monotonic'],old['started_monotonic'])
        self.assertEqual(parent['deadline_monotonic'],old['deadline_monotonic'])
        self.assertEqual(parent['children'],[])
        self.assertEqual(result['new_setter_count'],0)
        replay=self.entry.execute(key);self.assertTrue(replay['historical_receipt']);self.assertTrue(replay['review_event']['historical'])
        self.assertEqual(replay['review_event']['event_id'],result['review_event']['event_id'])
        with self.assertRaises(ValueError):self.entry._scheduler.run_registered(live['handoff'])

    def test_rebuilt_entry_cannot_execute_persisted_index(self):
        r=self.registered();other=TrustedTaskEntry(self.config,self.host,TrustedTaskAuthority('local-test',self.approve));self.mock_entry(other)
        with patch.object(other._scheduler,'run_registered',side_effect=AssertionError('dispatch')):
            result=other.execute(r['registration_id'])
        self.assertFalse(result['live_registration_available']);self.assertTrue(self.entry.snapshot(r['registration_id'])['live_registration_available'])

    def test_commit_guard_accepts_pending_parent_but_rejects_changed_binding(self):
        r=self.registered();key=r['registration_id']
        def kernel(handoff):
            handoff.take(self.entry._scheduler);state=self.state();parent=state['goal_supervision']['records'][r['goal_id']]
            for status in ('active','pending'):
                parent['status']=status;self.assertIsNone(handoff.commit_guard(state))
            for status in ('completed','frozen','stopped'):
                parent['status']=status;self.assertIn('binding_changed',handoff.commit_guard(state))
            parent['status']='pending';state['goal_authorizations']['records'][key]['grant']['scope']['process_id']=999
            self.assertIn('binding_changed',handoff.commit_guard(state))
            return dict(status='review_required',executed_this_call=False,new_setter_count=0,task_succeeded=False)
        with patch.object(self.entry._scheduler,'run_registered',side_effect=kernel):self.entry.execute(key)

    def test_other_scheduler_cannot_take_live_handoff(self):
        r=self.registered()
        def kernel(handoff):
            with self.assertRaises(ValueError):handoff.take(object())
            self.assertFalse(handoff.used);handoff.take(self.entry._scheduler)
            with self.assertRaises(ValueError):handoff.take(self.entry._scheduler)
            return dict(status='review_required',executed_this_call=False,new_setter_count=0,task_succeeded=False)
        with patch.object(self.entry._scheduler,'run_registered',side_effect=kernel):self.entry.execute(r['registration_id'])

    def test_changed_snapshot_and_expiry_block_before_handoff(self):
        r=self.registered();self.now=r['original_deadline_monotonic']
        with patch.object(self.entry._scheduler,'run_registered',side_effect=AssertionError('dispatch')):
            result=self.entry.execute(r['registration_id'])
        self.assertEqual(result['status'],'review_required');self.assertFalse(result['live_registration_available'])

    def test_execute_exception_remains_unknown_and_consumed(self):
        r=self.registered()
        with patch.object(self.entry._scheduler,'run_registered',side_effect=OSError('lost reply')):
            result=self.entry.execute(r['registration_id'])
        self.assertIsNone(result['executed_this_call']);self.assertIsNone(result['new_setter_count'])
        self.assertEqual(self.state()['goal_authorizations']['records'][r['registration_id']]['status'],'frozen')
        self.assertTrue(self.entry.execute(r['registration_id'])['historical_receipt'])

    def test_concurrent_read_revoke_do_not_wait_for_executor_or_overwrite_ledger(self):
        r=self.registered();key=r['registration_id'];started=threading.Event();release=threading.Event();rows=[]
        def kernel(handoff):
            handoff.take(self.entry._scheduler);started.set()
            if not release.wait(5):raise AssertionError('test executor timed out')
            self.assertIn('revoked',handoff.commit_guard(self.state()))
            return dict(status='review_required',executed_this_call=True,new_setter_count=1,task_succeeded=False)
        with patch.object(self.entry._scheduler,'run_registered',side_effect=kernel):
            worker=threading.Thread(target=lambda:rows.append(self.entry.execute(key)));worker.start()
            try:
                self.assertTrue(started.wait(5));before=self.state()
                self.assertEqual(self.entry.snapshot(key)['status'],'execution_in_progress')
                self.assertEqual(self.entry.execute(key)['status'],'execution_in_progress')
                revoke=self.entry.revoke(key);self.assertEqual(revoke['persistence'],'pending_executor_stop')
                self.assertEqual(self.state(),before)
            finally:release.set();worker.join(5)
        self.assertFalse(worker.is_alive());self.assertEqual(rows[0]['new_setter_count'],1)

    def test_runtime_commit_guard_blocks_and_invalidates_observation(self):
        for guard in (lambda:'task_entry_revoked',lambda:False,lambda:1/0):
            host=MutableHost();runtime=GuardedHostRuntime(host,quad_size=64)
            runtime.before_model(session_id='s',task_instruction='Measure current part clearance.',focal_id='part',reference_id='base',messages=[])
            result=runtime.execute_action(session_id='s',action={'translation':[0,0,.001]},_commit_guard=guard)
            self.assertEqual(result['status'],'blocked');self.assertEqual(host.calls,0)
            self.assertEqual(runtime.execute_action(session_id='s',action={'translation':[0,0,.001]})['status'],'observation_required')


if __name__=='__main__':unittest.main()

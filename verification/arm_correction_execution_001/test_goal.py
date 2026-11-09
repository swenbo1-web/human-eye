"""Arm event durability/replay faults plus two maintained clearance checks."""
from contextlib import contextmanager
from copy import deepcopy
import json
import threading
import unittest

from human_eye_plugin.goal_execution import (
    ArmAxialTaskSpec, run_arm_axial_step, validate_arm_axial_ledger)
from human_eye_plugin.goal_scheduler import OwnedGoalScheduler


def task(event='arm1', target=.4):
    return ArmAxialTaskSpec(event_id=event, selection=dict(mesh_name='Arm', armature_name='Rig',
        bone_names=['root','middle','last'], vertex_indices=list(range(6)), sections=[[0,1,2],[3,4,5]]),
        u_interval_deg=[0.,120.], max_section_area_loss=target, protected_vertex_ids=[0,1,2],
        sentinel_name='Outside')


def receipt(status='satisfied', *, attempts=2, returned=2, executed=True):
    return dict(schema='arm-axial-execution-result-v1', event_id='arm1', status=status,
        reason='actual_after_target_met' if status=='satisfied' else 'readback_failed',
        setter_attempts=attempts, setter_returns=returned, executed=executed,
        task_succeeded=status=='satisfied', feedback={'actual_j':.25})


class Host:
    def __init__(self):self.calls=0;self.result=receipt();self.error=None;self.before_call=None
    def correct_arm_axial(self, request):
        self.calls+=1
        if self.before_call:self.before_call(request)
        if self.error:raise self.error
        return deepcopy(self.result)


class Service:
    def __init__(self, *, disk=None, host=None):
        self.host=host or Host();self.disk=deepcopy(disk) if disk is not None else {'inflight':None}
        self.config={'enabled':True};self.saves=0;self.fail_save=None;self.commit_then_fail=False
        self.submitted=0;self.runtime=type('Runtime',(),{'status':{'quarantined':False}})()
    @contextmanager
    def _locked(self):yield deepcopy(self.disk),self.runtime
    def _save(self, value, runtime):
        self.saves+=1
        if self.saves==self.fail_save and not self.commit_then_fail:raise OSError('fake state write failure')
        self.disk=deepcopy(value)
        if self.saves==self.fail_save:raise OSError('fake lost save acknowledgement')
    def _identity_rejection(self):return None
    def _submitted_request(self):self.submitted+=1


class ArmGoalTests(unittest.TestCase):
    def test_spec_freezes_request_and_rejects_write_payload(self):
        spec=task();request=spec.to_request();request['selection']['bone_names'][1]='other'
        self.assertEqual(spec.to_request()['selection']['bone_names'][1],'middle')
        with self.assertRaises(Exception):spec._payload='changed'
        with self.assertRaises(ValueError):task(target=True)

    def test_pending_precedes_single_rpc_and_replay_returns_original(self):
        service=Service()
        def pending(request):
            self.assertEqual(service.disk['arm_axial_events']['records']['arm1']['state'],'pending')
            self.assertEqual(service.disk['inflight']['event_id'],'arm1')
        service.host.before_call=pending
        first=run_arm_axial_step(service,task())
        replay=run_arm_axial_step(service,task())
        self.assertEqual(first['status'],'satisfied');self.assertEqual(first['setter_returns'],2)
        self.assertTrue(replay['replayed']);self.assertFalse(replay['executed_this_call'])
        self.assertEqual(replay['setter_returns'],2);self.assertEqual(replay['new_setter_count'],0)
        self.assertEqual((service.host.calls,service.saves,service.submitted),(1,2,1))
        validate_arm_axial_ledger(service.disk)

    def test_changed_payload_same_event_is_conflict(self):
        service=Service();run_arm_axial_step(service,task())
        result=run_arm_axial_step(service,task(target=.3))
        self.assertEqual(result['status'],'event_conflict');self.assertEqual(service.host.calls,1)

    def test_restart_reads_completed_event_without_second_rpc(self):
        first=Service();run_arm_axial_step(first,task())
        restarted=Service(disk=first.disk,host=first.host)
        result=run_arm_axial_step(restarted,task())
        self.assertTrue(result['replayed']);self.assertEqual(result['setter_returns'],2)
        self.assertEqual(first.host.calls,1);self.assertEqual(restarted.saves,0)

    def test_lost_receipt_pending_blocks_same_and_other_events_after_restart(self):
        service=Service();service.host.error=OSError('lost pipe after actual setter')
        result=run_arm_axial_step(service,task())
        self.assertIsNone(result['executed']);self.assertIsNone(result['setter_returns'])
        restarted=Service(disk=service.disk,host=service.host)
        for spec in (task(),task('arm2')):
            again=run_arm_axial_step(restarted,spec)
            self.assertEqual(again['status'],'execution_uncertain')
        self.assertEqual(service.host.calls,1)

    def test_structured_partial_mutation_error_preserves_known_counts(self):
        service=Service();error=OSError('second setter failed')
        error.mutation_result=receipt('execution_uncertain',attempts=2,returned=1,executed=True)
        service.host.error=error
        result=run_arm_axial_step(service,task())
        self.assertEqual((result['setter_attempts'],result['setter_returns']),(2,1))
        self.assertIs(result['executed'],True);self.assertIsNotNone(service.disk['inflight'])
        self.assertEqual(run_arm_axial_step(Service(disk=service.disk,host=service.host),task())['setter_returns'],1)
        self.assertEqual(service.host.calls,1)

    def test_after_write_unknown_and_invalid_receipt_never_restart(self):
        for malformed in (receipt('execution_uncertain'),{'status':'satisfied'}):
            with self.subTest(malformed=malformed):
                service=Service();service.host.result=malformed
                result=run_arm_axial_step(service,task())
                self.assertEqual(result['status'],'execution_uncertain')
                self.assertIsNotNone(service.disk['inflight'])
                run_arm_axial_step(Service(disk=service.disk,host=service.host),task())
                self.assertEqual(service.host.calls,1)

    def test_completion_save_failure_keeps_known_outcome_and_durable_pending(self):
        service=Service();service.fail_save=2
        result=run_arm_axial_step(service,task())
        self.assertEqual(result['status'],'satisfied');self.assertEqual(result['setter_returns'],2)
        self.assertEqual(result['completion_persistence'],'failed_or_unknown')
        self.assertEqual(service.disk['arm_axial_events']['records']['arm1']['state'],'pending')
        self.assertEqual(run_arm_axial_step(service,task())['setter_returns'],2)
        restart=run_arm_axial_step(Service(disk=service.disk,host=service.host),task())
        self.assertIsNone(restart['setter_returns']);self.assertEqual(service.host.calls,1)

    def test_completion_commit_then_ack_failure_does_not_resend(self):
        service=Service();service.fail_save=2;service.commit_then_fail=True
        run_arm_axial_step(service,task())
        restarted=Service(disk=service.disk,host=service.host)
        result=run_arm_axial_step(restarted,task())
        self.assertEqual(result['setter_returns'],2);self.assertEqual(service.host.calls,1)

    def test_pending_save_failure_prevents_dispatch(self):
        service=Service();service.fail_save=1
        result=run_arm_axial_step(service,task())
        self.assertEqual(result['setter_returns'],0);self.assertIs(result['executed'],False)
        run_arm_axial_step(service,task());self.assertEqual(service.host.calls,0)

    def test_pending_barrier_corruption_fails_closed(self):
        service=Service();service.fail_save=2;run_arm_axial_step(service,task())
        service.disk['inflight']=None
        with self.assertRaisesRegex(ValueError,'pending_barrier'):
            run_arm_axial_step(Service(disk=service.disk,host=service.host),task('arm2'))
        self.assertEqual(service.host.calls,1)

    def test_uncertain_counter_contradictions_reject_raw_receipts_and_disk(self):
        invalid = [(None,None,True),(2,None,True),(2,0,True),(0,None,None),(0,0,None),
                   (2,1,None),(None,1,None),(2,1,False),(2,None,False),(0,0,True)]
        for attempts,returned,executed in invalid:
            with self.subTest(attempts=attempts,returned=returned,executed=executed):
                malformed=receipt('execution_uncertain',attempts=attempts,returned=returned,executed=executed)
                service=Service();service.host.result=malformed
                result=run_arm_axial_step(service,task())
                self.assertEqual(result['status'],'execution_uncertain')
                self.assertIsNone(result['setter_attempts']);self.assertIsNone(result['setter_returns'])
                self.assertIsNone(result['executed'])
                run_arm_axial_step(Service(disk=service.disk,host=service.host),task())
                self.assertEqual(service.host.calls,1)
                service.disk['arm_axial_events']['records']['arm1']['result']=malformed
                with self.assertRaisesRegex(ValueError,'contradictory_arm_execution_receipt'):
                    validate_arm_axial_ledger(service.disk)

    def test_same_scheduler_lock_routes_arm_without_clearance(self):
        scheduler=OwnedGoalScheduler.__new__(OwnedGoalScheduler)
        scheduler._run_lock=threading.Lock();scheduler.service=Service()
        def forbidden(spec):raise AssertionError('Arm task entered ClearanceTaskSpec branch')
        scheduler._run=forbidden
        result=scheduler.run(task())
        self.assertEqual(result['status'],'satisfied');self.assertEqual(scheduler.service.host.calls,1)


class ExistingClearanceRegression(unittest.TestCase):
    def check_existing(self, method):
        from verification.test_clearance_segment_service import ClearanceSegmentServiceTests
        result=unittest.TestResult();ClearanceSegmentServiceTests(method).run(result)
        self.assertEqual(result.errors+result.failures,[])
    def test_unchanged_clearance_success(self):
        self.check_existing('test_one_step_reaches_real_target_without_caller_translation')
    def test_unchanged_clearance_unknown_without_retry(self):
        self.check_existing('test_lost_host_result_never_advances_or_resends')


if __name__=='__main__':unittest.main()

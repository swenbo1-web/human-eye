"""Scheduler exception control flow with explicit nonphysical service seams.

The real task authority, request grammar and scheduler are used. These
tests do not stand in for owned Blender fault-injection acceptance.
"""
from contextlib import contextmanager
import copy
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from human_eye_plugin import goal_scheduler as product
from human_eye_plugin import task_authority as authority
from human_eye_plugin.auto_router import _validated_scene
from verification.test_goal_continuation import envelope, BUILD


class ServiceSeam:
    def __init__(self):
        self.value={}; self.config={'enabled':True}; self.runtime=NS(status={'quarantined':False})
        self.dispatches=0; self.reconciles=0; self.receipts=[]
        self.preview_error=None; self.reconcile_error=None

    def _identity_rejection(self):return None
    def describe_runtime(self):return {'build_id':BUILD}
    @contextmanager
    def _locked(self):yield self.value,self.runtime
    def _save(self,value,runtime):authority.validate_authorizations(value)
    def goal_supervision(self,operation,goal,**kwargs):
        if operation=='caps':return {'caps':{'max_steps':8,'max_step_translation_m':.001,
            'max_total_translation_m':.008,'max_duration_s':30.}}
        if operation=='reserve':return {'fresh_reservation':True,'request':copy.deepcopy(kwargs['request'])}
        if operation=='reconcile':
            if self.reconcile_error:raise self.reconcile_error
            self.reconciles+=1
            return {'confirmed_steps':self.reconciles,'actual_total_translation_m':self.reconciles*.001,
                'started_monotonic':0.,'deadline_monotonic':30.,'segments_reserved':self.reconciles,
                'recoveries_used':0,'journal_status':'active','journal_reason':None,'late_accounted_only':False}
        raise AssertionError(operation)
    def run_clearance_segment(self,*args,**kwargs):
        if self.preview_error:raise self.preview_error
        return {'status':'preview','executed':False,'candidate':{'status':'candidate'}}
    def run_supervised_clearance_segment(self,*args,**kwargs):
        self.dispatches+=1
        value=self.receipts.pop(0)
        if isinstance(value,Exception):raise value
        return copy.deepcopy(value)


class SchedulerExceptionReceiptTests(unittest.TestCase):
    def setUp(self):
        self.service=ServiceSeam()
        packet=envelope(.154,'unit-scene')
        packet['capture']['host_identity']['document_epoch']='a'*64
        packet['capture_confirmation']=copy.deepcopy(packet['capture'])
        binding={**packet['capture']['host_identity'],'focal_id':'part','reference_id':'base'}
        report={'binding':binding,'physical_meter':{'actual_setter_count':0},'reserved_event_count':0,
            'remaining_setters':8,'remaining_translation_m':.008}
        host=NS(_process=NS(pid=1234),is_alive=True,transaction=lambda:self.service._locked(),
            begin_motion_goal=lambda *a,**kw:None,motion_goal_status=lambda *a:copy.deepcopy(report))
        issuer=authority.TrustedTaskAuthority('unit-exception',lambda spec,scope:authority.TaskApproval('event','auth'))
        self.patchers=[patch.object(product,'LiveSpatialService',return_value=self.service),
            patch.object(product,'owned_host_counter',return_value={}),
            patch.object(product,'owned_clock_domain',return_value='unit-clock'),
            patch.object(product,'make_owned_host_context',return_value=NS(clock_domain=lambda:'unit-clock')),
            patch.object(product,'validate_owned_motion_report',side_effect=lambda host,goal,report,**kw:report),
            patch.object(product,'inspect_current_clearance',return_value={'decision':'not_satisfied','reason_codes':[]}),
            patch.object(product,'review_continuation',return_value={'decision':'eligible_for_fresh_preview','reason_codes':[]})]
        for patcher in self.patchers:patcher.start();self.addCleanup(patcher.stop)
        self.scheduler=product.OwnedGoalScheduler('unused',host,issuer)
        self.scheduler._capture=lambda:copy.deepcopy(packet)
        self.scheduler._discover=lambda *args:{'reference_triangle_index':2,'selection_binding':{
            'focal_id':'part','reference_id':'base','scene_revision':'unit-scene',
            'scene_fingerprint':_validated_scene(packet['capture'])[2]}}
        self.spec=authority.ClearanceTaskSpec('part','base',reference_triangle_index=2)

    def run_stopped(self):
        result=self.scheduler.run(self.spec)
        self.assertEqual(result['status'],'review_required',result)
        self.assertFalse(result['task_succeeded'],result)
        self.assertFalse(result['retry_authorized'])
        self.assertFalse(result['execution_authority'])
        record=next(iter(self.service.value['goal_authorizations']['records'].values()))
        self.assertEqual(record['status'],'frozen')
        return result

    def test_pre_dispatch_failure_is_known_zero(self):
        self.service.preview_error=OSError('preview unavailable')
        result=self.run_stopped()
        self.assertIs(result['executed_this_call'],False)
        self.assertEqual(result['new_setter_count'],0)
        self.assertEqual(self.service.dispatches,0)

    def test_exception_inside_dispatch_is_unknown_not_zero(self):
        self.service.receipts=[OSError('could be after host setter')]
        result=self.run_stopped()
        self.assertIsNone(result['executed_this_call'])
        self.assertIsNone(result['new_setter_count'])
        self.assertEqual(result['engine_confirmed_steps'],0)

    def test_receipt_then_failed_reconcile_keeps_count_unknown(self):
        self.service.receipts=[{'executed':True,'status':'review_required'}]
        self.service.reconcile_error=OSError('reconcile commit failed')
        result=self.run_stopped()
        self.assertIs(result['executed_this_call'],True)
        self.assertIsNone(result['new_setter_count'])
        self.assertEqual(result['engine_confirmed_steps'],0)

    def test_later_dispatch_exception_preserves_confirmed_lower_bound(self):
        self.service.receipts=[{'executed':True,'status':'review_required'},OSError('second dispatch failed')]
        result=self.run_stopped()
        self.assertEqual(self.service.dispatches,2)
        self.assertIs(result['executed_this_call'],True)
        self.assertIsNone(result['new_setter_count'])
        self.assertEqual(result['engine_confirmed_steps'],1)

    def test_later_unknown_receipt_does_not_erase_prior_confirmed_execution(self):
        self.service.receipts=[{'executed':True,'status':'review_required'},{'executed':None,'status':'execution_uncertain'}]
        original=self.service.goal_supervision
        def reconcile(operation,*args,**kwargs):
            if operation=='reconcile' and self.service.dispatches==2:raise OSError('unknown cannot reconcile')
            return original(operation,*args,**kwargs)
        self.service.goal_supervision=reconcile
        result=self.run_stopped()
        self.assertIs(result['executed_this_call'],True)
        self.assertIsNone(result['new_setter_count'])
        self.assertEqual(result['engine_confirmed_steps'],1)


if __name__=='__main__':unittest.main()

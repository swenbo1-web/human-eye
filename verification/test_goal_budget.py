"""Behavioral checks for one non-authorizing goal accounting session."""
from __future__ import annotations
import copy
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
import math
import unittest

from human_eye_plugin.goal_budget import GoalBudget,GoalBudgetLimits,GoalBudgetError,GoalBudgetStopped


class Clock:
    def __init__(self): self.value=100.
    def __call__(self): return self.value


def request(**changes):
    value={'solver':'support_plane','focal_id':'part','reference_id':'base',
        'reference_triangle_index':2,'direction_world':[0,0,1],
        'target_clearance_m':.001,'clearance_tolerance_m':1e-6,
        'max_steps':8,'max_step_translation_m':.001,
        'max_total_translation_m':.008,'max_duration_s':30.}
    value.update(changes);return value


def receipt(req,*,identity='r1',segment='s1',motions=(.0005,),status='review_required',base='native0'):
    steps=[];previous=base
    for index,motion in enumerate(motions):
        after=base+':'+str(index+1)
        steps.append({'step_id':segment+'-step-'+str(index),'step_index':index,'state':'complete',
            'operation_id':segment+'-op-'+str(index),
            'action':{'focal_id':'part','reference_id':'base','translation':[0.,0.,-motion],
                      'rotation_euler_deg':[0.,0.,0.]},
            'result':{'status':'verified','executed':True,'verified':True,'execution_verified':True,
                'actual_scene_revision':after,'receipt':{'host_execution_verified':True,
                    'focal_id':'part','before_revision':previous,'after_revision':after}},
            'actual_translation_m':motion})
        previous=after
    return {'request_id':identity,'segment_id':segment,'request':copy.deepcopy(req),'steps':steps,
        'status':status,'reason_codes':['contact_feature_changed_after_rounded_translation'] if status=='review_required' else [],
        'executed':bool(steps),'task_succeeded':status=='satisfied',
        'actual_total_translation_m':float(sum((Fraction(v) for v in motions),Fraction(0))),
        'base_revision':base,'end_revision':previous,'replayed':False,'historical_receipt':False}


def meter(motions=(.0005,),*,count=None,total=None):
    return {'actual_setter_count':len(motions) if count is None else count,
        'actual_cumulative_translation_m':float(sum((Fraction(v) for v in motions),Fraction(0))) if total is None else total,
        'step_motions_m':list(motions),'rollback_count':0,'complete':True}


class GoalBudgetTests(unittest.TestCase):
    def setUp(self):self.clock=Clock();self.budget=GoalBudget(clock=self.clock)

    def reserve(self,identity='r1',**changes):
        return self.budget.reserve_segment(identity,request(**changes))

    def confirm_first(self,**changes):
        reserved=self.reserve();r=receipt(reserved['request'],**changes)
        return r,self.budget.confirm_segment(r,physical_meter=meter(tuple(s['actual_translation_m'] for s in r['steps'])))

    def test_shared_remaining_caps_never_refill(self):
        r,_=self.confirm_first()
        self.clock.value+=7
        caps=self.budget.next_request_caps()
        self.assertEqual(caps['max_steps'],7)
        self.assertLessEqual(caps['max_total_translation_m'],.0075)
        self.assertEqual(caps['max_duration_s'],23)
        second=request(**caps);second['reference_triangle_index']=3
        reserved=self.budget.reserve_segment('r2',second)
        r2=receipt(reserved['request'],identity='r2',segment='s2',base=r['end_revision'],status='satisfied')
        final=self.budget.confirm_segment(r2,physical_meter=meter((.0005,),count=2,total=.001))
        self.assertEqual(final['confirmed_steps'],2);self.assertEqual(final['recoveries_used'],1)
        self.assertEqual(final['actual_total_translation_m'],.001)
        self.assertFalse(final['execution_authority']);self.assertFalse(final['physical_meter_authenticity_verified'])
        with self.assertRaises(GoalBudgetStopped):self.budget.next_request_caps()

    def test_ageing_caps_time_is_atomically_narrowed(self):
        caps=self.budget.next_request_caps();self.clock.value+=.02
        original=request(**caps);reserved=self.budget.reserve_segment('r1',original)
        self.assertLess(reserved['request']['max_duration_s'],original['max_duration_s'])
        self.assertEqual(reserved['request']['max_duration_s'],self.budget.deadline-self.clock())
        a=self.budget.reserve_segment('r1',original)
        b=self.budget.reserve_segment('r1',reserved['request'])
        self.assertFalse(a['fresh_reservation']);self.assertFalse(b['fresh_reservation'])
        self.assertEqual(a['request'],b['request'])
        self.assertEqual(self.budget.snapshot()['segments_reserved'],1)

    def test_pending_prevents_a_second_request(self):
        self.reserve()
        with self.assertRaises(GoalBudgetStopped):self.budget.reserve_segment('r2',request())
        self.assertEqual(self.budget.snapshot()['recoveries_used'],0)

    def test_reservation_is_detached_from_caller(self):
        original=request();reserved=self.budget.reserve_segment('r1',original)
        original['max_steps']=1;reserved['request']['direction_world'][2]=-1
        r=receipt(request())
        self.budget.confirm_segment(r,physical_meter=meter())
        self.assertEqual(self.budget.snapshot()['confirmed_steps'],1)

    def test_invalid_limits_and_requests_do_not_reserve(self):
        for kw in ({'max_steps':True},{'max_steps':9},{'max_duration_s':181},
                   {'max_duration_s':float('nan')},{'max_recoveries':3},{'max_segments':4},
                   {'max_step_translation_m':.0011},{'max_total_translation_m':.0081}):
            with self.subTest(kw=kw),self.assertRaises(GoalBudgetError):GoalBudgetLimits(**kw)
        for changes in ({'max_steps':True},{'max_steps':0},{'target_clearance_m':False},
            {'clearance_tolerance_m':float('nan')},{'max_total_translation_m':float('inf')},
            {'direction_world':[0,0,True]},{'direction_world':[1,0,0]},
            {'solver':'guess'},{'focal_id':'base'},{'max_duration_s':31},
            {'target_clearance_m':10**1000},{'direction_world':[0,0,10**1000]}):
            with self.subTest(changes=changes),self.assertRaises(GoalBudgetError):self.reserve(**changes)
        self.assertIsNone(self.budget.snapshot()['pending_request_id'])

    def test_oversized_request_is_rejected_without_retention(self):
        with self.assertRaises(GoalBudgetError):self.reserve(comment='x'*70000)
        self.assertEqual(self.budget.snapshot()['segments_reserved'],0)

    def test_request_identity_conflict_poisoned_forever(self):
        self.reserve()
        with self.assertRaises(GoalBudgetStopped):self.budget.reserve_segment('r1',request(target_clearance_m=.002))
        self.assertTrue(self.budget.poisoned)
        with self.assertRaises(GoalBudgetStopped):self.budget.next_request_caps()

    def test_goal_role_target_direction_tolerance_cannot_change(self):
        for change in ({'target_clearance_m':.002},{'clearance_tolerance_m':.0001},
                       {'direction_world':[0,0,-1]},{'reference_id':'other'}):
            budget=GoalBudget(clock=self.clock)
            first=budget.reserve_segment('r1',request())
            r=receipt(first['request']);budget.confirm_segment(r,physical_meter=meter())
            with self.subTest(change=change),self.assertRaises(GoalBudgetError):
                budget.reserve_segment('r2',request(**budget.next_request_caps(),**change))

    def test_remaining_steps_and_path_are_hard_caps(self):
        self.confirm_first()
        with self.assertRaises(GoalBudgetError):self.budget.reserve_segment('r2',request())
        caps=self.budget.next_request_caps()
        for field in ('max_steps','max_total_translation_m'):
            bad=dict(caps);bad[field]=caps[field]+(1 if field=='max_steps' else 1e-6)
            with self.subTest(field=field),self.assertRaises(GoalBudgetError):self.budget.reserve_segment('r2',request(**bad))

    def test_recovery_and_segment_budgets_are_shared(self):
        r,_=self.confirm_first()
        second=self.budget.reserve_segment('r2',request(**self.budget.next_request_caps()))
        r2=receipt(second['request'],identity='r2',segment='s2',base=r['end_revision'])
        self.budget.confirm_segment(r2,physical_meter=meter(count=2,total=.001))
        with self.assertRaises(GoalBudgetStopped):self.budget.next_request_caps()
        zero=GoalBudget(GoalBudgetLimits(max_recoveries=0),clock=self.clock)
        a=zero.reserve_segment('r1',request());zero.confirm_segment(receipt(a['request']),physical_meter=meter())
        with self.assertRaises(GoalBudgetStopped):zero.next_request_caps()
        one=GoalBudget(GoalBudgetLimits(max_segments=1,max_recoveries=2),clock=self.clock)
        a=one.reserve_segment('r1',request());one.confirm_segment(receipt(a['request']),physical_meter=meter())
        with self.assertRaises(GoalBudgetStopped):one.next_request_caps()

    def test_duplicate_confirmation_is_idempotent(self):
        r,first=self.confirm_first()
        replay=copy.deepcopy(r);replay.update(replayed=True,historical_receipt=True)
        second=self.budget.confirm_segment(replay,physical_meter=meter())
        self.assertTrue(second['deduplicated'])
        for field in ('confirmed_steps','actual_total_translation_m','recoveries_used','segments_reserved'):
            self.assertEqual(first[field],second[field])

    def test_first_historical_receipt_is_not_a_new_execution(self):
        for field in ('replayed','historical_receipt'):
            budget=GoalBudget(clock=self.clock);a=budget.reserve_segment('r1',request());r=receipt(a['request']);r[field]=True
            with self.subTest(field=field),self.assertRaises(GoalBudgetStopped):budget.confirm_segment(r,physical_meter=meter())
            self.assertTrue(budget.poisoned)

    def test_same_request_receipt_payload_conflict_poisoned(self):
        r,_=self.confirm_first();bad=copy.deepcopy(r);bad['residual']={'current_clearance_m':.9}
        with self.assertRaises(GoalBudgetStopped):self.budget.confirm_segment(bad,physical_meter=meter())
        self.assertTrue(self.budget.poisoned)

    def test_concurrent_duplicate_confirmation_charges_once(self):
        a=self.reserve();r=receipt(a['request'])
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda _:self.budget.confirm_segment(r,physical_meter=meter()),range(20)))
        self.assertEqual(sum(not r['deduplicated'] for r in results),1)
        self.assertEqual(self.budget.snapshot()['confirmed_steps'],1)

    def test_concurrent_requests_reserve_only_one_pending(self):
        def reserve(index):
            try:return self.budget.reserve_segment('r'+str(index),request())['fresh_reservation']
            except GoalBudgetStopped:return False
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(reserve,range(20)))
        self.assertEqual(sum(results),1)
        self.assertEqual(self.budget.snapshot()['segments_reserved'],1)

    def test_unknown_incomplete_unreserved_receipts_stop(self):
        for mutation in ({'status':'execution_uncertain','executed':None},{'steps':None},
                         {'request_id':'not-reserved'},{'executed':None},{'actual_total_translation_m':float('nan')}):
            budget=GoalBudget(clock=self.clock);a=budget.reserve_segment('r1',request());r=receipt(a['request']);r.update(mutation)
            with self.subTest(mutation=mutation),self.assertRaises(GoalBudgetStopped):budget.confirm_segment(r,physical_meter=meter())
            self.assertTrue(budget.poisoned)
            with self.assertRaises(GoalBudgetStopped):budget.reserve_segment('r2',request())

    def test_unconfirmed_or_false_verified_step_poisoned(self):
        for field,value in [('state','uncertain'),('executed',False),('verified',False),('execution_verified',False)]:
            budget=GoalBudget(clock=self.clock);a=budget.reserve_segment('r1',request());r=receipt(a['request'])
            target=r['steps'][0] if field=='state' else r['steps'][0]['result'];target[field]=value
            with self.subTest(field=field),self.assertRaises(GoalBudgetStopped):budget.confirm_segment(r,physical_meter=meter())

    def test_receipt_revision_chain_must_be_complete(self):
        for mutation in ('host_before','host_after','segment_end','missing_host'):
            budget=GoalBudget(clock=self.clock);a=budget.reserve_segment('r1',request());r=receipt(a['request'])
            if mutation=='host_before':r['steps'][0]['result']['receipt']['before_revision']='other'
            if mutation=='host_after':r['steps'][0]['result']['receipt']['after_revision']='other'
            if mutation=='segment_end':r['end_revision']='other'
            if mutation=='missing_host':r['steps'][0]['result']['receipt']=None
            with self.subTest(mutation=mutation),self.assertRaises(GoalBudgetStopped):budget.confirm_segment(r,physical_meter=meter())

    def test_segment_and_step_ids_cannot_be_reused(self):
        for kind in ('segment','step','operation'):
            budget=GoalBudget(clock=self.clock);a=budget.reserve_segment('r1',request());r=receipt(a['request'])
            budget.confirm_segment(r,physical_meter=meter())
            b=budget.reserve_segment('r2',request(**budget.next_request_caps()))
            next_r=receipt(b['request'],identity='r2',segment='s2',base=r['end_revision'])
            if kind=='segment':next_r['segment_id']='s1'
            elif kind=='step':next_r['steps'][0]['step_id']=r['steps'][0]['step_id']
            else:next_r['steps'][0]['operation_id']=r['steps'][0]['operation_id']
            with self.subTest(kind=kind),self.assertRaises(GoalBudgetStopped):budget.confirm_segment(next_r,physical_meter=meter(count=2,total=.001))

    def test_physical_meter_complete_count_path_and_step_motion_required(self):
        for changes in ({'complete':False},{'actual_setter_count':True},{'actual_setter_count':2},
                        {'actual_cumulative_translation_m':0.},{'step_motions_m':[]},
                        {'step_motions_m':[.0004]},{'rollback_count':1}):
            budget=GoalBudget(clock=self.clock);a=budget.reserve_segment('r1',request());r=receipt(a['request']);m=meter();m.update(changes)
            with self.subTest(changes=changes),self.assertRaises(GoalBudgetStopped):budget.confirm_segment(r,physical_meter=m)
            self.assertTrue(budget.poisoned)

    def test_over_step_and_fractional_total_cap_never_relaxed(self):
        a=self.reserve();r=receipt(a['request'],motions=(math.nextafter(.001,math.inf),))
        with self.assertRaises(GoalBudgetStopped):self.budget.confirm_segment(r,physical_meter=meter((r['steps'][0]['actual_translation_m'],)))
        budget=GoalBudget(GoalBudgetLimits(max_total_translation_m=.001),clock=self.clock)
        a=budget.reserve_segment('r1',request(max_total_translation_m=.001))
        motions=(.0005,math.nextafter(.0005,math.inf));r=receipt(a['request'],motions=motions)
        # Float cumulative summary can round down to the cap; exact step sum cannot.
        with self.assertRaises(GoalBudgetStopped):budget.confirm_segment(r,physical_meter=meter(motions))

    def test_world_XY_rotation_and_role_changes_stop(self):
        for mutation in ('x','rotation','role'):
            budget=GoalBudget(clock=self.clock);a=budget.reserve_segment('r1',request());r=receipt(a['request'])
            action=r['steps'][0]['action']
            if mutation=='x':action['translation'][0]=1e-9
            elif mutation=='rotation':action['rotation_euler_deg'][2]=1e-9
            else:action['reference_id']='other'
            with self.subTest(mutation=mutation),self.assertRaises(GoalBudgetStopped):budget.confirm_segment(r,physical_meter=meter())

    def test_receipt_cannot_expand_or_change_reserved_request(self):
        for change in ({'max_total_translation_m':.0081},{'max_steps':9},{'target_clearance_m':.002}):
            budget=GoalBudget(clock=self.clock);a=budget.reserve_segment('r1',request());r=receipt(a['request']);r['request'].update(change)
            with self.subTest(change=change),self.assertRaises(GoalBudgetStopped):budget.confirm_segment(r,physical_meter=meter())

    def test_late_confirmed_motion_accounted_but_cannot_complete_or_resume(self):
        a=self.reserve();r=receipt(a['request'],status='satisfied');self.clock.value=131
        state=self.budget.confirm_segment(r,physical_meter=meter())
        self.assertEqual(state['confirmed_steps'],1)
        self.assertEqual(state['stopped_reason'],'goal_time_budget_exhausted')
        self.assertTrue(state['late_accounted_only'])
        with self.assertRaises(GoalBudgetStopped):self.budget.next_request_caps()

    def test_zero_write_satisfied_or_blocked_is_terminal(self):
        for status in ('satisfied','blocked'):
            budget=GoalBudget(clock=self.clock);a=budget.reserve_segment('r1',request());r=receipt(a['request'],motions=(),status=status)
            state=budget.confirm_segment(r,physical_meter=meter(()))
            self.assertEqual(state['confirmed_steps'],0)
            with self.assertRaises(GoalBudgetStopped):budget.next_request_caps()

    def test_backward_clock_and_manual_poison_cannot_revive(self):
        self.clock.value=99
        with self.assertRaises(GoalBudgetStopped):self.budget.next_request_caps()
        self.assertTrue(self.budget.poisoned)
        other=GoalBudget(clock=lambda:100.)
        with self.assertRaises(GoalBudgetStopped):other.poison('unknown_write')
        with self.assertRaises(GoalBudgetStopped):other.reserve_segment('new',request())


if __name__=='__main__':unittest.main()

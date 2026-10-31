"""Offline shared-clock/loop/compute checks; no provider or Blender access."""
from __future__ import annotations

from decimal import Decimal
import json
import time
import unittest
from unittest.mock import patch

from verification.model_trial import compute as compute_module
from verification.model_trial.compute import ComputeError, RestrictedCompute
from verification.model_trial.deadline import DeadlineExceeded, EpisodeDeadline
from verification.model_trial.loop import (
    EpisodeLimits, Reservation, RunBinding, SyntheticTransport, run_episode,
)
from verification.model_trial.spend import SharedRunBudget
from verification.model_trial.tools import TrialRouter, ToolRejected, UnconfirmedToolOutcome


class Clock:
    def __init__(self, now=0.): self.now = now
    def __call__(self): return self.now


class BoundNative:
    """Protocol-only test stub, never an actual host adapter."""
    def __init__(self, clock=None):
        self.clock = clock
        self.bound_deadline = None
        self.binds = 0
        self.calls = []
        self.on_call = None
    @property
    def deadline_enforced(self): return self.bound_deadline is not None
    def bind_deadline(self, budget):
        if self.bound_deadline is not None and self.bound_deadline is not budget:
            raise ValueError('no renewal')
        self.bound_deadline = budget
        self.binds += 1
    def call(self, name, args):
        self.calls.append((name, args))
        if self.on_call: self.on_call()
        if name == 'native_scene_query':
            return {'unit':'m','coordinate_frame':'world','revision':'r1','objects':[]}
        return {'ok':True}


class BoundReservationOnly:
    identity = 'offline-no-provider-contract'
    usage_verified = True
    def __init__(self, cost=.8, clock=None, expire_reserve=False, broken=False):
        self.cost, self.clock, self.expire_reserve, self.broken = cost, clock, expire_reserve, broken
        self.bound_deadline = None
        self.binds = self.calls = self.reservations = 0
    @property
    def deadline_enforced(self): return self.bound_deadline is not None and not self.broken
    def bind_deadline(self, budget):
        self.binds += 1
        self.bound_deadline = budget
    def reserve(self, request):
        self.reservations += 1
        if self.expire_reserve: self.clock.now += 181.
        return Reservation(100,10,self.cost,10.,'USD',True,
                           'offline-fixed-contract','reservation-'+str(self.cost))
    def __call__(self, request):
        self.calls += 1
        raise AssertionError('a real or even local provider callable must not run')


def binding():
    return RunBinding('formal','offline-contract-only','no-provider',
        {'reasoning':'contract','sampling':'contract','images':'contract'},1.,'USD',
        BoundReservationOnly.identity,True,True,True,'offline-stub','offline-stub')


class TrialComputeDeadlineTests(unittest.TestCase):
    def test_deadline_is_set_before_ast_parse(self):
        clock=Clock(); original=compute_module.ast.parse
        def late_parse(*args,**kwargs):
            tree=original(*args,**kwargs); clock.now=2.; return tree
        with patch.object(compute_module.ast,'parse',side_effect=late_parse):
            with self.assertRaises(ComputeError):
                RestrictedCompute(clock=clock).run('result=1',{},deadline=1.)

    def test_deepcopy_cannot_reset_remaining_budget(self):
        clock=Clock(); original=compute_module.copy.deepcopy
        def late_copy(*args,**kwargs):
            result=original(*args,**kwargs); clock.now=2.; return result
        with patch.object(compute_module.copy,'deepcopy',side_effect=late_copy):
            with self.assertRaises(ComputeError):
                RestrictedCompute(clock=clock).run('result=1',{},deadline=1.)

    def test_serialization_cannot_return_late_success(self):
        clock=Clock(); original=json.dumps
        def late_dump(*args,**kwargs):
            result=original(*args,**kwargs); clock.now=2.; return result
        with patch.object(json,'dumps',side_effect=late_dump):
            with self.assertRaises(ComputeError):
                RestrictedCompute(clock=clock).run('result=[1,2]',{},deadline=1.)

    def test_local_limit_is_capped_by_absolute_remaining_time(self):
        clock=Clock(20.)
        vm=RestrictedCompute(clock=clock)
        self.assertEqual(vm.run('result=1',{},deadline=20.25)['result'],1)
        self.assertEqual(vm.deadline,20.25)
        clock.now=20.25
        with self.assertRaises(ComputeError): vm.run('result=1',{},deadline=20.25)
        for invalid in (True,float('nan'),float('inf'),'1'):
            with self.subTest(invalid=invalid),self.assertRaises(ComputeError):
                vm.run('result=1',{},deadline=invalid)


class TrialRouterDeadlineTests(unittest.TestCase):
    def budget(self,clock=None,seconds=1.):
        budget=EpisodeDeadline(seconds,clock=clock or time.monotonic,watchdog=clock is None)
        self.addCleanup(budget.close)
        return budget

    def test_one_shared_binding_and_no_renewal_or_eager_call(self):
        clock=Clock(10.); native,plugin=BoundNative(),BoundNative()
        router=TrialRouter('B',native,plugin)
        budget=self.budget(clock)
        router.bind_deadline(budget)
        self.assertIs(native.bound_deadline,budget)
        self.assertIs(plugin.bound_deadline,budget)
        self.assertIs(router.compute.clock,clock)
        self.assertEqual(native.calls+plugin.calls,[])
        self.assertEqual(router.deadline,11.)
        router.bind_deadline(budget)
        with self.assertRaises(ToolRejected): router.bind_deadline(self.budget(clock,.5))
        self.assertEqual(native.binds,1)

    def test_late_return_is_withheld_and_no_later_channel_call(self):
        clock=Clock(); native,plugin=BoundNative(),BoundNative()
        router=TrialRouter('B',native,plugin,clock=clock)
        router.bind_deadline(self.budget(clock))
        native.on_call=lambda: setattr(clock,'now',2.)
        with self.assertRaises((ToolRejected,DeadlineExceeded)):
            router.call('native_scene_query',{})
        self.assertEqual(router.events,[])
        with self.assertRaises((ToolRejected,DeadlineExceeded)):
            router.call('human_eye_scene_observe',{})
        self.assertEqual(len(native.calls),1)
        self.assertEqual(plugin.calls,[])

    def test_expiry_while_fake_call_sleeps_rejects_late_result(self):
        native=BoundNative()
        native.on_call=lambda:time.sleep(.03)
        router=TrialRouter('A',native)
        router.bind_deadline(self.budget(seconds=.01))
        with self.assertRaises((ToolRejected,DeadlineExceeded)):
            router.call('native_scene_query',{})
        self.assertTrue(router.closed)
        self.assertEqual(router.events,[])

    def test_compute_receives_original_absolute_deadline(self):
        clock=Clock(); native=BoundNative()
        router=TrialRouter('A',native,clock=clock)
        router.bind_deadline(self.budget(clock))
        native.on_call=lambda:setattr(clock,'now',.9)
        original=router.compute.run
        seen=[]
        def checked(code,scene,**kwargs):
            seen.append(kwargs['deadline'])
            return original(code,scene,**kwargs)
        with patch.object(router.compute,'run',side_effect=checked):
            self.assertEqual(router.call('native_compute',{'code':'result=1'})['result'],1)
        self.assertEqual(seen,[1.])
        self.assertEqual(router.compute.deadline,1.)

    def test_unknown_still_blocks_other_channel(self):
        clock=Clock(); native,plugin=BoundNative(),BoundNative()
        plugin.call=lambda *_:{'executed':None,'status':'execution_uncertain'}
        router=TrialRouter('B',native,plugin,clock=clock)
        router.bind_deadline(self.budget(clock))
        with self.assertRaises(UnconfirmedToolOutcome):
            router.call('human_eye_scene_observe',{})
        with self.assertRaises(UnconfirmedToolOutcome):
            router.call('native_scene_query',{})
        self.assertEqual(native.calls,[])


class TrialLoopDeadlineTests(unittest.TestCase):
    def remember(self,router):
        self.addCleanup(lambda:router.bound_deadline.close() if router.bound_deadline else None)
        return router

    def test_bad_formal_binding_has_zero_adapter_side_effects(self):
        native=BoundNative(); provider=BoundReservationOnly()
        result=run_episode(provider,self.remember(TrialRouter('A',native)),'task')
        self.assertEqual(result.status,'disabled')
        self.assertEqual((native.binds,provider.binds,provider.reservations,provider.calls),(0,0,0,0))

    def test_boolean_capability_without_binding_is_not_formal(self):
        class Legacy:
            deadline_enforced=usage_verified=True
            identity=BoundReservationOnly.identity
            calls=0
            def reserve(self,*_): raise AssertionError('no reserve')
            def __call__(self,*_): self.calls+=1; raise AssertionError('no call')
        provider=Legacy()
        result=run_episode(provider,self.remember(TrialRouter('A',BoundNative())),'task',binding(),
            run_budget=SharedRunBudget(1,'USD'),episode_id='legacy')
        self.assertEqual(result.status,'disabled')
        self.assertEqual(provider.calls,0)
        self.assertTrue(any('cannot bind' in failure for failure in result.failures))

    def test_bind_then_verify_dynamic_capability_without_provider_request(self):
        provider=BoundReservationOnly(broken=True); native=BoundNative()
        router=self.remember(TrialRouter('A',native))
        result=run_episode(provider,router,'task',binding(),
            run_budget=SharedRunBudget(1,'USD'),episode_id='bad-bound')
        self.assertEqual(result.status,'disabled')
        self.assertEqual((provider.calls,provider.reservations),(0,0))
        self.assertIs(provider.bound_deadline,native.bound_deadline)
        self.assertEqual(provider.binds,1)

    def test_reserve_expiry_stops_dispatch_and_retains_shared_money(self):
        shared=SharedRunBudget(1,'USD'); clock=Clock(7.)
        first=BoundReservationOnly(.8,clock,expire_reserve=True)
        native=BoundNative(); router=self.remember(TrialRouter('A',native))
        outcome=run_episode(first,router,'task',binding(),clock=clock,
            run_budget=shared,episode_id='first')
        self.assertEqual(outcome.status,'budget_stopped')
        self.assertEqual(shared.total_reserved,Decimal('.8'))
        self.assertEqual(first.calls,0)
        self.assertEqual(router.bound_deadline.started,7.)
        self.assertEqual(router.bound_deadline.expires_at,187.)
        self.assertIs(first.bound_deadline,router.bound_deadline)
        second=BoundReservationOnly(.4)
        outcome2=run_episode(second,self.remember(TrialRouter('A',BoundNative())),'task',binding(),
            clock=Clock(),run_budget=shared,episode_id='second')
        self.assertEqual(outcome2.stop_reason,'preflight_reservation_failed')
        self.assertEqual(shared.total_reserved,Decimal('.8'))
        self.assertEqual(second.calls,0)
        self.assertEqual(outcome.provider_requests+outcome2.provider_requests,0)

    def test_late_synthetic_model_response_cannot_schedule_tools(self):
        clock=Clock(); provider=SyntheticTransport([]); native=BoundNative()
        router=self.remember(TrialRouter('A',native))
        def late_response(request):
            provider.requests.append(request); clock.now=2.
            return {'text':'late','tool_calls':[{'name':'native_scene_query','arguments':{}}]}
        with patch.object(SyntheticTransport,'__call__',side_effect=late_response):
            outcome=run_episode(provider,router,'task',synthetic=True,clock=clock,
                                limits=EpisodeLimits(wall_seconds=1))
        self.assertEqual(outcome.status,'budget_stopped')
        self.assertEqual(outcome.tool_requests,0)
        self.assertEqual(native.calls,[])
        self.assertFalse(outcome.formal)
        self.assertEqual(outcome.provider_requests,0)

    def test_normal_finish_seals_router_and_preserves_harness_watchdog(self):
        clock=Clock(); router=self.remember(TrialRouter('A',BoundNative()))
        outcome=run_episode(SyntheticTransport([{'text':'done'}]),router,'task',synthetic=True,clock=clock)
        self.assertEqual(outcome.status,'completed')
        self.assertTrue(router.closed)
        self.assertFalse(router.bound_deadline.snapshot()['timer_closed'])
        with self.assertRaises(ToolRejected): router.call('native_scene_query',{})


if __name__=='__main__': unittest.main()

"""Independent owner-bridge contracts, never physical execution evidence.

The real typed specs, normalization and TaskAuthority issue/verify are used.
Only installed identity metadata, capability RPC and scheduler dispatch are
isolated. A __new__ fixed-host instance has a non-OS process double. No host,
provider, socket or native setter is started. Root runs separate installed
Blender acceptance for actual origins, native quality and durable unknowns.
"""
from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

from human_eye_plugin.auto_router import _validated_scene
from human_eye_plugin.blender_process import BlenderProcessHost
from human_eye_plugin.forward_deadline import counter_descriptor
from human_eye_plugin.goal_budget import GoalBudgetLimits
from human_eye_plugin.goal_supervision import owned_clock_domain
from human_eye_plugin.runtime_identity import runtime_identity
from human_eye_plugin.task_authority import ClearanceTaskSpec, TaskAuthorizationDenied
from verification.model_trial.deadline import EpisodeDeadline
from verification.model_trial import owned_goal_adapter as adapter
from verification.test_goal_continuation import envelope


ROOT=Path(__file__).resolve().parents[1]
LEGACY={
    'tools.py':'a9e6ada9e94dc4d53d35f22c0ce054b827dd4ada275e4e4424a6e359702107e8',
    'loop.py':'34057c3c46ca90f9fb065679bf3af6d8205540b18a34ce3d389ca3304095170c',
    'native_client.py':'ae3d71913a6989ebf909fc0b8db69d49f2135a80ab7053c8b8766b2de3effa5e',
    'native_fixture.py':'88e916aead07556e653366a693f8db01fb93ef25d0ba0271c59a15a892acd7c0',
    'plugin_client.py':'e585420a2429e4879c49d03aebe93a14ac607840f4c2eaa5d943cc5d7ac50a46',
    'oracle.py':'41e635be106a18aff5bce307ef91e59b0dbfb5594f9e245413153d6bdc387948',
}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),
        ensure_ascii=True,allow_nan=False).encode('utf8')).hexdigest()


class ProcessDouble:
    def __init__(self,pid):self.pid=pid;self.returncode=None;self.kill_calls=0
    def poll(self):return self.returncode
    def kill(self):self.kill_calls+=1;self.returncode=-9


def original_packet():
    packet=envelope(.154,'owner-original')
    packet['capture']['host_identity']['document_epoch']='a'*64
    packet['capture_confirmation']=copy.deepcopy(packet['capture'])
    return packet


def successful_result():
    return {'status':'completed','task_succeeded':True,'host_closed':True,
        'executed_this_call':True,'new_setter_count':4,
        'clearance_at_task_end_m':.0010000057573859179,
        'execution_authority':False,'retry_authorized':False}


class OwnedGoalTrialAdapterTests(unittest.TestCase):
    def setUp(self):
        self.spawn_guard=patch('subprocess.Popen',side_effect=AssertionError('unit test must not start subprocess'))
        self.spawn_guard.start();self.addCleanup(self.spawn_guard.stop)
        self.identity=runtime_identity(mode='live')
        self.identity.update(source_kind='installed_distribution',
            distribution_version='9.7.2+20261030.goal.autonomy.r1')
        self.packet=original_packet()
        self.spec=ClearanceTaskSpec('part','base',reference_triangle_index=2)
        self.schedulers=[]
        self.behavior=lambda scheduler,spec:successful_result()
        case=self
        class DispatchDouble:
            def __init__(self,config,host,authority):
                self.config=config;self.host=host;self.authority=authority;self.calls=[];self.grants=[]
                self.service=SimpleNamespace(describe_runtime=lambda:copy.deepcopy(case.identity))
                case.schedulers.append(self)
            def run(self,spec):
                self.calls.append(copy.deepcopy(spec))
                return case.behavior(self,spec)
        self.dispatch_type=DispatchDouble
        self.patchers=[
            patch('human_eye_plugin.runtime_identity.runtime_identity',side_effect=lambda **kw:copy.deepcopy(self.identity)),
            patch('human_eye_plugin.goal_supervision.owned_host_counter',return_value=counter_descriptor()),
            patch('human_eye_plugin.goal_scheduler.OwnedGoalScheduler',self.dispatch_type),
        ]
        for patcher in self.patchers:
            patcher.start();self.addCleanup(patcher.stop)

    def episode(self,*,task=None,packet=None,deadline=None,host=None,expected=None,issuer='unit-owner'):
        if deadline is None:
            deadline=EpisodeDeadline(180,clock=time.perf_counter,watchdog=True)
            self.addCleanup(deadline.close)
        if host is None:
            host=object.__new__(BlenderProcessHost)
            host._process=ProcessDouble(1234+len(self.schedulers))
            host._default_worker=True;host._closed=False;host._poisoned=False
        ep=adapter.OwnedGoalEpisode(ROOT/'verification/private-unit-only-never-opened.json',host,
            task=task or adapter.OwnedTaskIntent(self.spec,'owner-event','owner-authorization'),
            initial_evidence=self.packet if packet is None else packet,deadline=deadline,
            expected_build_id=self.identity['build_id'] if expected is None else expected,issuer_id=issuer)
        def cleanup():
            if ep._process.poll() is None:ep._process.returncode=0
            ep.close()
        self.addCleanup(cleanup)
        return ep,host,deadline

    def authorize(self,scheduler,spec,*,change=None):
        normalized=_validated_scene(self.packet['capture'])[0]
        scope={'engine_build_id':self.identity['build_id'],'process_id':scheduler.host._process.pid,
            'host_identity':copy.deepcopy(normalized['host_identity']),
            'reference_triangle_index':spec.reference_triangle_index,
            'initial_capture_sha256':digest(normalized),
            'initial_native_sha256':digest(self.packet['native_scene']),
            'clock_domain':owned_clock_domain(normalized['host_identity']['document_epoch'],counter_descriptor())}
        if change is not None:change(scope)
        grant=scheduler.authority.issue(spec,scope)
        scheduler.grants.append(grant)
        return grant

    def test_raw_json_is_neither_typed_intent_nor_typed_spec(self):
        with self.assertRaises(ValueError):adapter.OwnedTaskIntent(self.spec.to_dict(),'event','authorization')
        with self.assertRaises(ValueError):
            self.episode(task={'spec':self.spec.to_dict(),'event_id':'event','authorization_id':'authorization'})
        self.assertEqual(self.schedulers,[])

    def test_intent_rejects_missing_triangle_bool_fields_and_unbounded_limits(self):
        with self.assertRaises(ValueError):adapter.OwnedTaskIntent(ClearanceTaskSpec('part','base'),'event','auth')
        for changes in ({'event_id':True},{'authorization_id':False},{'read_only':1}):
            fields={'spec':self.spec,'event_id':'event','authorization_id':'auth'};fields.update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):adapter.OwnedTaskIntent(**fields)
        for changes in ({'max_steps':9},{'max_steps':True},{'max_total_translation_m':.009},
                        {'max_step_translation_m':.0011},{'max_duration_s':181}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):GoalBudgetLimits(**changes)

    def test_task_and_limit_copies_are_frozen_and_detached(self):
        task=adapter.OwnedTaskIntent(self.spec,'event','auth')
        self.assertIsNot(task.spec,self.spec)
        self.assertIsNot(task.spec.limits,self.spec.limits)
        with self.assertRaises(FrozenInstanceError):task.event_id='changed'
        with self.assertRaises(FrozenInstanceError):task.spec.limits.max_steps=9
        episode,host,deadline=self.episode(task=task)
        self.assertEqual(episode.private_snapshot()['registered_task']['spec'],self.spec.to_dict())

    def test_constructor_has_no_dispatch_and_real_authority_accepts_exact_registration(self):
        ep,host,deadline=self.episode()
        self.assertEqual(len(self.schedulers),1);self.assertEqual(self.schedulers[0].calls,[])
        def behavior(scheduler,spec):
            grant=self.authorize(scheduler,spec)
            payload=scheduler.authority.verify(grant)
            self.assertEqual(payload['event_id'],'owner-event')
            self.assertEqual(payload['authorization_id'],'owner-authorization')
            self.assertEqual(payload['spec'],self.spec.to_dict())
            self.assertEqual(payload['deadline_monotonic'],payload['issued_monotonic']+self.spec.limits.max_duration_s)
            return successful_result()
        self.behavior=behavior
        first=ep.run();self.assertTrue(first['task_succeeded'])
        self.assertTrue(ep.private_snapshot()['authority_events'][0]['approved'])
        self.assertIs(ep.bound_deadline,deadline)

    def test_real_authority_rejects_each_changed_original_scope(self):
        changes=[lambda s:s.update(engine_build_id='sha256:'+'f'*64),
            lambda s:s.update(process_id=s['process_id']+1),
            lambda s:s['host_identity'].update(document_epoch='b'*64),
            lambda s:s['host_identity']['object_instances'].update(part='new-instance'),
            lambda s:s.update(initial_capture_sha256='1'*64),
            lambda s:s.update(initial_native_sha256='2'*64),lambda s:s.update(clock_domain='wrong-clock')]
        for change in changes:
            ep,host,deadline=self.episode()
            scheduler=self.schedulers[-1]
            with self.subTest(change=change),self.assertRaises(ValueError):self.authorize(scheduler,self.spec,change=change)
            self.assertFalse(ep.private_snapshot()['authority_events'][-1]['approved'])
            self.assertEqual(scheduler.calls,[])

    def test_core_rejects_scope_triangle_conflict_before_owner_callback(self):
        ep,host,deadline=self.episode();scheduler=self.schedulers[-1]
        with self.assertRaises(ValueError):
            self.authorize(scheduler,self.spec,change=lambda s:s.update(reference_triangle_index=3))
        self.assertEqual(ep.private_snapshot()['authority_events'],[])
        self.assertEqual(scheduler.calls,[])

    def test_real_authority_rejects_changed_task_target_or_limit(self):
        ep,host,deadline=self.episode();scheduler=self.schedulers[-1]
        for spec in (replace(self.spec,target_clearance_m=.0015),
                     replace(self.spec,limits=GoalBudgetLimits(max_steps=2)),
                     replace(self.spec,reference_triangle_index=3)):
            with self.subTest(spec=spec),self.assertRaises(ValueError):self.authorize(scheduler,spec)
        self.assertEqual(scheduler.calls,[])

    def test_original_evidence_and_owner_snapshots_are_detached(self):
        original=copy.deepcopy(self.packet)
        ep,host,deadline=self.episode()
        self.packet['capture']['meshes'][0]['name']='post-registration mutation'
        self.packet['native_scene']['objects'][0]['matrix'][0][0]=99
        snapshot=ep.private_snapshot()
        self.assertEqual(snapshot['original_scope']['initial_capture_sha256'],digest(_validated_scene(original['capture'])[0]))
        self.assertEqual(snapshot['original_scope']['initial_native_sha256'],digest(original['native_scene']))
        snapshot['registered_task']['event_id']='changed'
        snapshot['original_evidence']['native_scene']['objects'].clear()
        self.assertEqual(ep.private_snapshot()['registered_task']['event_id'],'owner-event')
        self.assertEqual(len(ep.private_snapshot()['original_evidence']['native_scene']['objects']),2)

    def test_wrong_clock_missing_watchdog_expired_deadline_and_source_runtime_refuse(self):
        for clock,watchdog in ((time.monotonic,True),(time.perf_counter,False)):
            deadline=EpisodeDeadline(180,clock=clock,watchdog=watchdog);self.addCleanup(deadline.close)
            with self.subTest(clock=clock,watchdog=watchdog),self.assertRaises(ValueError):self.episode(deadline=deadline)
        deadline=EpisodeDeadline(180,clock=time.perf_counter);self.addCleanup(deadline.close);deadline.expire()
        with self.assertRaises((ValueError,TimeoutError)):self.episode(deadline=deadline)
        self.identity['source_kind']='source_checkout'
        with self.assertRaises(ValueError):self.episode()

    def test_explicit_expected_build_mismatch_refuses_before_scheduler(self):
        for value in (True,'not-a-build','sha256:'+'0'*64):
            with self.subTest(value=value),self.assertRaises(ValueError):self.episode(expected=value)
        self.assertEqual(self.schedulers,[])

    def test_deadline_cannot_be_rebound_or_renewed(self):
        ep,host,deadline=self.episode()
        same=ep.bind_deadline(deadline);self.assertIs(same,ep)
        other=EpisodeDeadline(180,clock=time.perf_counter);self.addCleanup(other.close)
        with self.assertRaises(ValueError):ep.bind_deadline(other)
        self.assertIs(ep.bound_deadline,deadline)
        self.assertEqual(deadline.expires_at,ep.private_snapshot()['episode_deadline']['deadline_monotonic'])

    def test_readonly_never_calls_scheduler_or_issues_approval(self):
        ep,host,deadline=self.episode(task=adapter.OwnedTaskIntent(self.spec,'read','read-auth',True))
        result=ep.run()
        self.assertFalse(result['task_succeeded']);self.assertFalse(result['executed_this_call'])
        self.assertEqual(result['new_setter_count_this_call'],0)
        self.assertEqual(self.schedulers[-1].calls,[])
        self.assertEqual(ep.private_snapshot()['authority_events'],[])
        self.assertEqual(host._process.kill_calls,0)

    def test_run_has_no_untrusted_proposal_entry_and_replay_does_not_redispatch(self):
        ep,host,deadline=self.episode()
        with self.assertRaises(TypeError):ep.run({'event_id':'invented','limits':{'max_steps':8}})
        first=ep.run();replay=ep.run()
        self.assertTrue(first['task_succeeded']);self.assertTrue(replay['historical_receipt'])
        self.assertFalse(replay['executed_this_call']);self.assertEqual(replay['new_setter_count_this_call'],0)
        self.assertEqual(len(self.schedulers[-1].calls),1)
        self.assertIs(ep.bound_deadline,deadline)

    def test_unknown_result_and_exception_are_absorbing_with_unknown_counts(self):
        for outcome in ({'status':'review_required','task_succeeded':False,'executed_this_call':None,'new_setter_count':None},
                        RuntimeError('private-path D:/secret/private-state.json owner-token')):
            def behavior(scheduler,spec):
                if isinstance(outcome,Exception):raise outcome
                return outcome
            self.behavior=behavior;ep,host,deadline=self.episode()
            result=ep.run();again=ep.run()
            self.assertEqual(result['status'],'unknown');self.assertIsNone(result['executed_this_call'])
            self.assertIsNone(result['new_setter_count_this_call']);self.assertIsNone(result['recorded_task_setter_count'])
            self.assertTrue(ep.uncertain_outcome);self.assertEqual(len(self.schedulers[-1].calls),1)
            self.assertFalse(again['executed_this_call']);self.assertEqual(again['new_setter_count_this_call'],0)
            self.assertNotIn('owner-token',json.dumps(result))

    def test_known_review_stop_is_absorbing_without_inventing_fresh_event(self):
        self.behavior=lambda scheduler,spec:{'status':'review_required','task_succeeded':False,
            'executed_this_call':True,'new_setter_count':1}
        ep,host,deadline=self.episode();first=ep.run();second=ep.run()
        self.assertEqual(first['status'],'review_required');self.assertTrue(ep.uncertain_outcome)
        self.assertEqual(second['new_setter_count_this_call'],0);self.assertEqual(len(self.schedulers[-1].calls),1)
        self.assertEqual(ep.private_snapshot()['registered_task']['event_id'],'owner-event')

    def test_product_historical_receipt_is_not_new_goal_completion(self):
        raw=successful_result()
        raw.update(historical_receipt=True,replayed=True,current_scene_revalidated=False,
            executed_this_call=False,new_setter_count=0)
        self.behavior=lambda scheduler,spec:raw
        ep,host,deadline=self.episode();result=ep.run()
        self.assertTrue(result['historical_receipt']);self.assertFalse(result['task_succeeded'])
        self.assertFalse(result['current_scene_revalidated']);self.assertFalse(result['executed_this_call'])
        self.assertEqual(result['new_setter_count_this_call'],0)
        self.assertEqual(len(self.schedulers[-1].calls),1)

    def test_non_object_scheduler_return_remains_unknown_without_redispatch(self):
        for raw in (None,True,[],{'task_succeeded':False}):
            self.behavior=lambda scheduler,spec:raw
            ep,host,deadline=self.episode();result=ep.run();ep.run()
            self.assertEqual(result['status'],'unknown')
            self.assertIsNone(result['executed_this_call']);self.assertIsNone(result['new_setter_count_this_call'])
            self.assertEqual(len(self.schedulers[-1].calls),1)

    def test_public_allowlist_omits_all_private_raw_fields_and_exception_text(self):
        raw=successful_result()
        raw.update(native_scene={'private_normal':[0,0,1]},initial_native_sha256='secret-hash',
            authorization_key='secret-authorization',grant={'secret':'grant-key'},
            reason_codes=['D:/hidden/private.json owner-secret'],last_preview={'owner_token':'secret'})
        self.behavior=lambda scheduler,spec:raw
        ep,host,deadline=self.episode();public=ep.run();encoded=json.dumps(public)
        for secret in ('private_normal','secret-hash','secret-authorization','grant-key','owner-secret','D:/hidden','owner_token'):
            self.assertNotIn(secret,encoded)
        self.assertIn('recorded_clearance_m',public)
        self.assertFalse(public['execution_authority']);self.assertFalse(public['retry_authorized'])
        self.assertFalse(public['formal_eligible']);self.assertFalse(public['common_native_parity'])
        self.assertEqual(public['provider_requests'],0)
        self.assertNotIn(public['branch'],('A','B','C'))
        self.assertEqual(ep.private_snapshot()['scheduler_result']['grant'],{'secret':'grant-key'})
        public['status']='forged'
        self.assertEqual(ep.public_receipt()['status'],'completed')

    def test_expiry_kills_only_captured_process_even_if_host_process_is_replaced(self):
        ep,host,deadline=self.episode();original=host._process;replacement=ProcessDouble(9999)
        host._process=replacement
        self.assertFalse(ep.deadline_enforced)
        deadline.expire()
        self.assertEqual(original.kill_calls,1);self.assertEqual(replacement.kill_calls,0)
        result=ep.run()
        self.assertFalse(result['task_succeeded']);self.assertIsNone(result['new_setter_count_this_call'])
        self.assertEqual(self.schedulers[-1].calls,[])

    def test_expiry_during_dispatch_cannot_publish_late_success_or_redispatch(self):
        ep,host,deadline=self.episode()
        def behavior(scheduler,spec):
            deadline.expire();return successful_result()
        self.behavior=behavior
        first=ep.run();second=ep.run()
        self.assertEqual(first['status'],'expired');self.assertFalse(first['task_succeeded'])
        self.assertIsNone(first['executed_this_call']);self.assertIsNone(first['recorded_task_setter_count'])
        self.assertFalse(second['executed_this_call']);self.assertEqual(len(self.schedulers[-1].calls),1)
        self.assertEqual(host._process.kill_calls,1)

    def test_close_requires_original_process_exit_and_revokes_deadline_guarantee(self):
        ep,host,deadline=self.episode()
        with self.assertRaises(ValueError):ep.close()
        self.assertTrue(ep.deadline_enforced)
        host._process.returncode=0;ep.close()
        self.assertFalse(ep.deadline_enforced)
        deadline.expire();self.assertEqual(host._process.kill_calls,0)

    def test_frozen_legacy_arm_files_remain_byte_identical(self):
        for relative,expected in LEGACY.items():
            path=ROOT/'verification/model_trial'/relative
            with self.subTest(path=path):self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),expected)


if __name__=='__main__':unittest.main()

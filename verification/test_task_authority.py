"""Pure capability and durable accounting checks; no host is started.

Synthetic receipts below test schema/accounting only. They are not physical
execution evidence and never stand in for the separate owned-host tests.
"""
from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import unittest
from unittest.mock import patch

from human_eye_plugin import goal_journal as journal
from human_eye_plugin import task_authority as authority
from human_eye_plugin.goal_budget import GoalBudgetLimits
from human_eye_plugin.goal_execution import record_step_result
from verification.test_goal_budget import meter, receipt, request


def scope(**changes):
    value = {'engine_build_id':'sha256:' + '1' * 64, 'process_id':1234,
        'host_identity':{'schema_version':'1.0', 'document_epoch':'a' * 64,
            'object_instances':{'part':'part-instance', 'base':'base-instance'},
            'capture_scope':'complete_scene_meshes'}, 'reference_triangle_index':2,
        'initial_capture_sha256':'2' * 64, 'initial_native_sha256':'3' * 64,
        'clock_domain':'owned-qpc-parent-v1:unit'}
    value.update(changes)
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False).encode()).hexdigest()


class TaskAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.spec = authority.ClearanceTaskSpec('part', 'base')
        self.event = 'trusted-event-1'; self.approval = 'approval-1'; self.value = {}
        self.issuer = authority.TrustedTaskAuthority('unit-embedding',
            lambda spec, facts:authority.TaskApproval(self.event, self.approval))

    def grant(self, *, spec=None, facts=None, now=100., issuer=None):
        with patch('human_eye_plugin.task_authority.time.perf_counter', return_value=now):
            return (issuer or self.issuer).issue(self.spec if spec is None else spec,
                scope() if facts is None else facts)

    def claimed(self, grant=None, *, parent=True):
        grant = self.grant() if grant is None else grant
        authority.claim_grant(self.value, grant)
        if parent:
            journal.create_goal(self.value, grant.goal_id, grant.session_id,
                limits=grant.spec_resolved.limits, clock_domain=grant.payload()['scope']['clock_domain'],
                now=grant.issued_monotonic)
        return grant

    def active(self, grant=None, *, parent=True):
        grant = self.claimed(grant, parent=parent)
        authority.set_authorization_state(self.value, grant.key, 'active')
        return grant

    def child(self, grant, *, identity='child1', status='satisfied', confirm=True):
        facts = grant.payload(); spec = grant.spec_resolved
        kwargs = {'clock_domain':facts['scope']['clock_domain'], 'now':grant.issued_monotonic}
        req = request(focal_id=spec.focal_id, reference_id=spec.reference_id,
            target_clearance_m=spec.target_clearance_m,
            clearance_tolerance_m=spec.clearance_tolerance_m,
            direction_world=list(spec.direction_world),
            reference_triangle_index=spec.reference_triangle_index)
        req = journal.reserve_segment(self.value, grant.goal_id, identity, req, **kwargs)['request']
        journal.mark_dispatched(self.value, grant.goal_id, identity, grant.session_id, req, **kwargs)
        result = receipt(req, identity=identity, segment='segment:' + identity, status=status)
        for step in result['steps']:
            raw = copy.deepcopy(step['result'])
            raw.update(goal_evaluation=None, task_succeeded=status == 'satisfied', reason_codes=[])
            record_step_result(step, raw)
        result['runtime_identity'] = {'mode':'live', 'build_id':facts['scope']['engine_build_id']}
        entry = {'request_fingerprint':digest({'session_id':grant.session_id, 'request':req}),
            'parent_goal_id':grant.goal_id, 'segment_id':result['segment_id'],
            'session_id':grant.session_id, 'request':copy.deepcopy(req), 'status':status,
            'steps':copy.deepcopy(result['steps']), 'result':result,
            'base_revision':result['base_revision'], 'end_revision':result['end_revision'],
            'host_binding':copy.deepcopy(facts['scope']['host_identity'])}
        self.value.setdefault('goal_segments', {'schema_version':'1.0', 'records':{}})['records'][identity] = entry
        if confirm:
            journal.confirm_segment(self.value, grant.goal_id, identity, physical_meter=meter(),
                clock_domain=kwargs['clock_domain'], now=grant.issued_monotonic + 1.)
        return entry

    def completed(self, grant=None, *, identity='child1'):
        grant = self.active(grant); self.child(grant, identity=identity)
        authority.set_authorization_state(self.value, grant.key, 'completed',
            result={'task_succeeded':True, 'host_closed':True,
                    'execution_authority':False, 'retry_authorized':False})
        return grant

    def rejection_preserves_state(self, fn):
        previous = copy.deepcopy(self.value)
        with self.assertRaises(authority.TaskAuthorityError):fn()
        self.assertEqual(previous, self.value)

    def test_frozen_proposal_requires_explicit_valid_world_z_scope(self):
        self.assertEqual(self.spec.to_dict()['direction_world'], [0., 0., 1.])
        with self.assertRaises(FrozenInstanceError):self.spec.focal_id = 'other'
        for changes in ({'focal_id':'base'}, {'direction_world':[0, 0, 1]},
                {'direction_world':(1, 0, 0)}, {'direction_world':(0, 0, True)},
                {'reference_triangle_index':True}, {'reference_triangle_index':-1},
                {'target_clearance_m':0}, {'target_clearance_m':float('nan')},
                {'target_clearance_m':10 ** 1000}, {'clearance_tolerance_m':.001},
                {'limits':{'max_steps':8}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):replace(self.spec, **changes)

    def test_missing_or_extra_scope_is_not_authorized(self):
        for key in scope():
            facts = scope(); del facts[key]
            with self.subTest(key=key), self.assertRaises(authority.TaskAuthorityError):self.grant(facts=facts)
        facts = scope(); facts['approved'] = True
        with self.assertRaises(authority.TaskAuthorityError):self.grant(facts=facts)

    def test_invalid_scope_identity_build_clock_and_evidence_fail(self):
        cases = [{'engine_build_id':'v21'}, {'process_id':True}, {'clock_domain':'bad domain'},
            {'clock_domain':':bad-start'}, {'initial_capture_sha256':'2' * 63},
            {'initial_native_sha256':'X' * 64}, {'reference_triangle_index':True}]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(authority.TaskAuthorityError):
                self.grant(facts=scope(**changes))
        for change in ({'document_epoch':'invalid'}, {'capture_scope':'selected_objects'},
                {'object_instances':{'part':'same', 'base':'same'}},
                {'object_instances':{'other':'i1', 'base':'i2'}}, {'extra':True}):
            facts = scope(); facts['host_identity'].update(change)
            with self.subTest(change=change), self.assertRaises(authority.TaskAuthorityError):self.grant(facts=facts)

    def test_discovery_resolves_original_triangle_before_approval(self):
        seen = []
        def approve(spec, facts):
            seen.append((spec, copy.deepcopy(facts)))
            facts['initial_capture_sha256'] = 'f' * 64
            return authority.TaskApproval('e', 'a')
        issuer = authority.TrustedTaskAuthority('resolver', approve)
        grant = self.grant(issuer=issuer)
        self.assertEqual(seen[0][0].reference_triangle_index, 2)
        self.assertEqual(grant.spec_resolved.reference_triangle_index, 2)
        self.assertEqual(grant.payload()['scope']['initial_capture_sha256'], '2' * 64)
        with self.assertRaises(authority.TaskAuthorityError):
            self.grant(spec=replace(self.spec, reference_triangle_index=3))

    def test_exact_typed_approval_is_required(self):
        class DerivedApproval(authority.TaskApproval):pass
        for reply in (True, 'approved', {'event_id':'e', 'authorization_id':'a'}, DerivedApproval('e', 'a')):
            issuer = authority.TrustedTaskAuthority('bad-approval', lambda *args:reply)
            with self.subTest(reply=reply), self.assertRaises(authority.TaskAuthorityError):self.grant(issuer=issuer)
        for denied in (None, False):
            issuer = authority.TrustedTaskAuthority('denied', lambda *args:denied)
            with self.assertRaises(authority.TaskAuthorizationDenied):self.grant(issuer=issuer)

    def test_model_dictionary_cannot_issue_or_claim_a_capability(self):
        with self.assertRaises(authority.TaskAuthorityError):self.grant(spec=self.spec.to_dict())
        with self.assertRaises(authority.TaskAuthorityError):authority.TaskGrant()
        self.rejection_preserves_state(lambda:authority.claim_grant(self.value, self.grant().payload()))

    def test_grant_seal_is_bound_to_exact_issuer_instance(self):
        grant = self.grant()
        other = authority.TrustedTaskAuthority('unit-embedding', lambda *args:authority.TaskApproval('e', 'a'))
        with self.assertRaises(authority.TaskAuthorityError):other.verify(grant)
        with self.assertRaises(AttributeError):grant._raw = b'{}'
        forged = object.__new__(authority.TaskGrant)
        for name in ('_issuer', '_raw', '_seal'):object.__setattr__(forged, name, getattr(grant, name))
        object.__setattr__(forged, '_raw', grant._raw.replace(b'approval-1', b'approval-2'))
        with self.assertRaises(authority.TaskAuthorityError):forged.payload()

    def test_payload_and_source_scope_are_detached(self):
        facts = scope(); grant = self.grant(facts=facts)
        facts['host_identity']['object_instances']['part'] = 'changed'
        payload = grant.payload(); payload['spec']['limits']['max_steps'] = 999
        payload['scope']['host_identity']['object_instances']['base'] = 'changed'
        self.assertEqual(grant.payload()['spec']['limits']['max_steps'], 8)
        self.assertEqual(grant.payload()['scope'], scope())

    def test_qpc_deadline_begins_at_issue_and_is_not_duration_plus_setup(self):
        grant = self.grant(now=123.)
        self.assertEqual(grant.issued_monotonic, 123.)
        self.assertEqual(grant.deadline_monotonic, 153.)
        self.claimed(grant)
        snapshot = journal.snapshot(self.value, grant.goal_id,
            clock_domain=scope()['clock_domain'], now=140.)
        self.assertEqual(snapshot['deadline_monotonic'], 153.)
        self.assertEqual(snapshot['remaining_duration_s'], 13.)

    def test_claim_reserves_one_deterministic_event_mapping(self):
        grant = self.grant(); result = authority.claim_grant(self.value, grant)
        self.assertTrue(result['fresh_claim']); self.assertFalse(result['execution_authority'])
        self.assertEqual(result['goal_id'], 'auth-goal:' + digest(['unit-embedding', self.event]))
        self.assertEqual(authority.blocking_authorization(self.value), grant.key)
        result['record']['grant']['issued_monotonic'] = 0
        self.assertEqual(self.value['goal_authorizations']['records'][grant.key]['grant']['issued_monotonic'], 100.)

    def test_duplicate_never_renews_anchors_or_replaces_initial_evidence(self):
        grant = self.claimed(parent=False); previous = copy.deepcopy(self.value)
        facts = scope(initial_capture_sha256='4' * 64, initial_native_sha256='5' * 64)
        replay = authority.claim_grant(self.value, self.grant(facts=facts, now=500.))
        self.assertEqual(replay['goal_id'], grant.goal_id); self.assertFalse(replay['fresh_claim'])
        self.assertEqual(replay['mode'], 'needs_review'); self.assertEqual(previous, self.value)
        self.assertEqual(replay['record']['grant']['deadline_monotonic'], 130.)

    def test_recreated_trusted_issuer_cannot_refill_existing_event(self):
        grant = self.claimed(parent=False)
        restored = json.loads(json.dumps(self.value))
        issuer = authority.TrustedTaskAuthority('unit-embedding',
            lambda *args:authority.TaskApproval(self.event, self.approval))
        replay = authority.claim_grant(restored, self.grant(issuer=issuer, now=900.))
        self.assertEqual(replay['record']['grant']['issued_monotonic'], grant.issued_monotonic)
        self.assertEqual(replay['mode'], 'needs_review')

    def test_same_event_cannot_change_spec_authorization_or_static_binding(self):
        self.claimed(parent=False)
        for spec in (replace(self.spec, target_clearance_m=.002),
                replace(self.spec, limits=GoalBudgetLimits(max_steps=7)),
                replace(self.spec, direction_world=(0., 0., -1.))):
            self.rejection_preserves_state(lambda spec=spec:authority.claim_grant(self.value, self.grant(spec=spec)))
        self.approval = 'different-approval'
        self.rejection_preserves_state(lambda:authority.claim_grant(self.value, self.grant()))
        self.approval = 'approval-1'
        for changes in ({'engine_build_id':'sha256:' + '9' * 64}, {'process_id':1235},
                {'clock_domain':'another-boot'}, {'reference_triangle_index':3}):
            self.rejection_preserves_state(lambda changes=changes:authority.claim_grant(self.value,
                self.grant(facts=scope(**changes))))
        for field, changed in (('document_epoch','b' * 64),
                ('object_instances',{'part':'new-instance', 'base':'base-instance'})):
            facts = scope(); facts['host_identity'][field] = changed
            self.rejection_preserves_state(lambda facts=facts:authority.claim_grant(self.value, self.grant(facts=facts)))

    def test_new_event_cannot_bypass_reserved_active_stopped_or_frozen_task(self):
        for status in ('reserved', 'active', 'stopped', 'frozen'):
            with self.subTest(status=status):
                self.value = {}; self.event = 'old-event'; grant = self.claimed(parent=False)
                if status != 'reserved':
                    authority.set_authorization_state(self.value, grant.key, status,
                        reason=None if status == 'active' else 'review_required')
                self.event = 'new-event'
                self.rejection_preserves_state(lambda:authority.claim_grant(self.value, self.grant()))

    def test_preexisting_legacy_parent_or_inflight_blocks_first_claim(self):
        journal.create_goal(self.value, 'legacy', 'session', clock_domain='boot1', now=100.)
        self.rejection_preserves_state(lambda:authority.claim_grant(self.value, self.grant()))
        self.value = {'inflight':{'session_id':'unknown'}}
        self.rejection_preserves_state(lambda:authority.claim_grant(self.value, self.grant()))

    def test_reserved_or_active_missing_parent_loads_but_never_releases(self):
        grant = self.active(parent=False)
        authority.validate_authorizations(self.value)
        self.assertEqual(authority.blocking_authorization(self.value), grant.key)
        self.rejection_preserves_state(lambda:authority.set_authorization_state(self.value, grant.key,
            'completed', result={'task_succeeded':True, 'host_closed':True}))

    def test_parent_clock_start_deadline_session_and_limits_are_crosschecked(self):
        grant = self.claimed(); original = copy.deepcopy(self.value)
        for field, changed in (('clock_domain','other-clock'), ('session_id','other-session'),
                ('started_monotonic',101.), ('deadline_monotonic',131.)):
            value = copy.deepcopy(original); value['goal_supervision']['records'][grant.goal_id][field] = changed
            with self.subTest(field=field), self.assertRaises(authority.TaskAuthorityError):authority.validate_authorizations(value)
        value = copy.deepcopy(original)
        value['goal_supervision']['records'][grant.goal_id]['limits']['max_steps'] = 7
        with self.assertRaises(authority.TaskAuthorityError):authority.validate_authorizations(value)

    def test_parent_child_must_preserve_granted_object_target_and_triangle(self):
        grant = self.active()
        for changes in ({'target_clearance_m':.002}, {'reference_triangle_index':3},
                {'focal_id':'other'}, {'direction_world':[0, 0, -1]}):
            value = copy.deepcopy(self.value)
            journal.reserve_segment(value, grant.goal_id, 'wrong-child', request(**changes),
                clock_domain=scope()['clock_domain'], now=100.)
            with self.subTest(changes=changes), self.assertRaises(authority.TaskAuthorityError):authority.validate_authorizations(value)

    def test_child_host_binding_and_build_are_checked_before_parent_confirmation(self):
        grant = self.active(); entry = self.child(grant, confirm=False)
        authority.validate_authorizations(self.value)
        original = copy.deepcopy(self.value)
        for field, changed in (('host_binding',None), ('host_binding',scope()['host_identity'] | {'document_epoch':'b' * 64})):
            value = copy.deepcopy(original); value['goal_segments']['records']['child1'][field] = changed
            with self.assertRaises(authority.TaskAuthorityError):authority.validate_authorizations(value)
        for identity in (None, {'mode':'demo', 'build_id':scope()['engine_build_id']},
                {'mode':'live', 'build_id':'sha256:' + 'f' * 64}):
            entry['result']['runtime_identity'] = identity
            with self.assertRaises(authority.TaskAuthorityError):authority.validate_authorizations(self.value)

    def test_malformed_child_ledger_fails_even_without_authorization_index(self):
        with self.assertRaises(authority.TaskAuthorityError):
            authority.validate_authorizations({'goal_segments':{'schema_version':'broken', 'records':{}}})

    def test_completion_requires_completed_parent_and_verified_host_closure(self):
        grant = self.active()
        self.rejection_preserves_state(lambda:authority.set_authorization_state(self.value, grant.key,
            'completed', result={'task_succeeded':True, 'host_closed':True}))
        self.child(grant)
        for result in ({'task_succeeded':True}, {'task_succeeded':True, 'host_closed':False},
                {'task_succeeded':False, 'host_closed':True}, {'task_succeeded':'true', 'host_closed':True},
                {'task_succeeded':True, 'host_closed':1}):
            self.rejection_preserves_state(lambda result=result:authority.set_authorization_state(
                self.value, grant.key, 'completed', result=result))
        authority.set_authorization_state(self.value, grant.key, 'completed',
            result={'task_succeeded':True, 'host_closed':True})
        self.assertIsNone(authority.blocking_authorization(self.value))

    def test_committed_but_unconfirmed_child_never_releases(self):
        grant = self.active(); self.child(grant, confirm=False)
        self.rejection_preserves_state(lambda:authority.set_authorization_state(self.value, grant.key,
            'completed', result={'task_succeeded':True, 'host_closed':True}))
        self.assertEqual(authority.blocking_authorization(self.value), grant.key)

    def test_pending_host_operation_blocks_completion(self):
        grant = self.active(); self.child(grant)
        self.value['inflight'] = {'session_id':grant.session_id}
        self.rejection_preserves_state(lambda:authority.set_authorization_state(self.value, grant.key,
            'completed', result={'task_succeeded':True, 'host_closed':True}))

    def test_completed_task_replay_is_historical_and_a_distinct_new_event_can_start(self):
        grant = self.completed(); original = copy.deepcopy(self.value)
        replay = authority.claim_grant(self.value, self.grant(now=900.))
        self.assertEqual(replay['mode'], 'historical'); self.assertEqual(original, self.value)
        self.event = 'trusted-event-2'; second = self.claimed(self.grant(now=110.))
        self.assertNotEqual(second.goal_id, grant.goal_id)
        authority.validate_authorizations(self.value)
        self.assertEqual(authority.blocking_authorization(self.value), second.key)

    def test_completed_history_does_not_block_a_later_known_child(self):
        self.completed(identity='child1'); self.event = 'trusted-event-2'
        second = self.active(self.grant(now=110.)); self.child(second, identity='child2', confirm=False)
        authority.validate_authorizations(self.value)
        self.assertEqual(authority.blocking_authorization(self.value), second.key)

    def test_completed_or_stopped_or_frozen_authorization_cannot_be_reopened(self):
        for state in ('completed', 'stopped', 'frozen'):
            self.value = {}; self.event = 'terminal-event'
            grant = self.completed() if state == 'completed' else self.active(parent=False)
            if state != 'completed':authority.set_authorization_state(self.value, grant.key, state, reason='requires_review')
            record = copy.deepcopy(self.value['goal_authorizations']['records'][grant.key])
            authority.set_authorization_state(self.value, grant.key, state, result=record['result'], reason=record['reason'])
            for target in ('reserved', 'active'):
                self.rejection_preserves_state(lambda target=target:authority.set_authorization_state(self.value, grant.key, target))

    def test_terminal_result_cannot_self_grant_rights_or_exceed_bound(self):
        grant = self.active(parent=False)
        for result in ({'execution_authority':True}, {'retry_authorized':True},
                {'task_succeeded':'yes'}, {'host_closed':1}, {'too_large':'x' * 8192},
                {'bad_number':float('nan')}, {'not_plain':object()}):
            self.rejection_preserves_state(lambda result=result:authority.set_authorization_state(
                self.value, grant.key, 'frozen', reason='review', result=result))

    def test_parent_success_can_be_retained_when_host_close_is_unknown_but_stays_blocked(self):
        grant = self.active(); self.child(grant)
        authority.set_authorization_state(self.value, grant.key, 'frozen', reason='host_close_ack_unknown',
            result={'task_succeeded':True, 'host_closed':None})
        self.assertEqual(authority.blocking_authorization(self.value), grant.key)

    def test_changed_mapping_digest_and_orphan_authorized_parent_fail_closed(self):
        grant = self.claimed(); original = copy.deepcopy(self.value)
        for mutate in (
            lambda v:v['goal_authorizations']['records'][grant.key].update(grant_sha256='f' * 64),
            lambda v:v['goal_authorizations']['records'][grant.key]['grant'].update(goal_id='auth-goal:other'),
            lambda v:v.pop('goal_authorizations')):
            value = copy.deepcopy(original); mutate(value)
            with self.assertRaises(authority.TaskAuthorityError):authority.validate_authorizations(value)

    def test_capacity_never_evicts_an_old_event_or_refreshes_its_budget(self):
        first = None
        for number in range(authority.MAX_AUTHORIZATIONS):
            self.event = 'bounded-event-' + str(number)
            grant = self.completed(identity='bounded-child-' + str(number))
            if first is None:first = grant
        self.event = 'bounded-event-overflow'
        self.rejection_preserves_state(lambda:authority.claim_grant(self.value, self.grant()))
        self.assertEqual(len(self.value['goal_authorizations']['records']), 16)
        self.event = 'bounded-event-0'
        replay = authority.claim_grant(self.value, self.grant(now=900.))
        self.assertEqual(replay['goal_id'], first.goal_id)
        self.assertEqual(replay['record']['grant']['deadline_monotonic'], 130.)


if __name__ == '__main__':unittest.main()

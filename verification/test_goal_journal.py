"""Behavioral restart, reconciliation and ownership checks for durable goals."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import unittest
from unittest.mock import patch

from human_eye_plugin import goal_journal as journal
from human_eye_plugin.goal_budget import GoalBudgetLimits
from verification.test_goal_budget import request, receipt, meter


def committed(value, req, *, identity='r1', parent='g1', session='session1',
              segment='s1', status='review_required', base='native0', motions=(.0005,)):
    result = receipt(req, identity=identity, segment=segment, status=status, base=base, motions=motions)
    fingerprint = hashlib.sha256(json.dumps({'session_id': session, 'request': req},
        sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode()).hexdigest()
    entry = {'request_fingerprint': fingerprint, 'parent_goal_id': parent,
        'segment_id': segment, 'session_id': session, 'request': copy.deepcopy(req),
        'status': status, 'steps': copy.deepcopy(result['steps']), 'result': result,
        'base_revision': result['base_revision'], 'end_revision': result['end_revision']}
    value.setdefault('goal_segments', {'schema_version': '1.0', 'records': {}})['records'][identity] = entry
    return result


class GoalJournalTests(unittest.TestCase):
    def setUp(self):
        self.value = {}; self.now = 100.; self.domain = 'boot1'
        journal.create_goal(self.value, 'g1', 'session1', clock_domain=self.domain, now=self.now)

    def kw(self): return {'clock_domain': self.domain, 'now': self.now}

    def snap(self): return journal.snapshot(self.value, 'g1', **self.kw())

    def reserve(self, identity='r1', req=None):
        return journal.reserve_segment(self.value, 'g1', identity, request() if req is None else req, **self.kw())

    def dispatch(self, identity='r1', req=None):
        if req is None:
            req = next(c['request'] for c in self.value['goal_supervision']['records']['g1']['children'] if c['request_id'] == identity)
        return journal.mark_dispatched(self.value, 'g1', identity, 'session1', req, **self.kw())

    def first(self, *, status='review_required', confirmation=102.):
        first = self.reserve(); self.now = 101.; self.dispatch(req=first['request'])
        r = committed(self.value, first['request'], status=status)
        self.now = confirmation
        s = journal.confirm_segment(self.value, 'g1', 'r1', physical_meter=meter(), **self.kw())
        return r, s

    def reload(self): self.value = json.loads(json.dumps(self.value))

    def test_no_io_authority_or_cached_budget(self):
        s = self.snap()
        self.assertFalse(s['execution_authority']); self.assertFalse(s['retry_authorized'])
        self.assertFalse(s['physical_meter_authenticity_verified'])
        self.assertNotIn('budget', self.value['goal_supervision']['records']['g1'])
        self.assertEqual(s['confirmed_steps'], 0)

    def test_process_reload_keeps_start_deadline_time_and_spend(self):
        r, _ = self.first(); self.reload(); self.now = 112.
        s = self.snap(); caps = journal.next_caps(self.value, 'g1', **self.kw())
        self.assertEqual(s['started_monotonic'], 100.)
        self.assertEqual(s['deadline_monotonic'], 130.)
        self.assertEqual(caps['max_duration_s'], 18.)
        self.assertEqual(s['confirmed_steps'], 1); self.assertEqual(s['actual_total_translation_m'], .0005)
        self.assertEqual(caps['max_steps'], 7); self.assertLessEqual(caps['max_total_translation_m'], .0075)
        req = request(**caps)
        req['selection_binding'] = {'scene_revision': r['end_revision'], 'scene_fingerprint': 'a'*64,
            'focal_id': 'part', 'reference_id': 'base'}
        reserved = self.reserve('r2', req); self.dispatch('r2', reserved['request'])
        committed(self.value, reserved['request'], identity='r2', segment='s2',
            base=r['end_revision'], status='satisfied')
        self.now = 115.
        final = journal.confirm_segment(self.value, 'g1', 'r2', physical_meter=meter(count=2, total=.001), **self.kw())
        self.assertEqual(final['confirmed_steps'], 2); self.assertEqual(final['recoveries_used'], 1)
        self.assertEqual(final['journal_status'], 'completed'); self.assertIsNone(journal.blocking_goal(self.value))

    def test_reserve_before_dispatch_survives_reload_without_reset(self):
        a = self.reserve(); self.reload(); self.now = 105.
        s = self.snap()
        self.assertEqual(s['pending_request_id'], 'r1'); self.assertEqual(journal.blocking_goal(self.value), 'g1')
        duplicate = self.reserve(req=a['request']); self.assertFalse(duplicate['fresh_reservation'])
        self.assertEqual(s['segments_reserved'], 1)
        with self.assertRaises(journal.GoalJournalStopped): journal.next_caps(self.value, 'g1', **self.kw())

    def test_raw_and_effective_reservations_are_both_idempotent_after_reload(self):
        self.now = 103.; raw = request(); a = self.reserve(req=raw)
        self.assertEqual(a['request']['max_duration_s'], 27.)
        self.reload(); self.now = 106.
        for req in (raw, a['request']):
            again = self.reserve(req=req)
            self.assertFalse(again['fresh_reservation']); self.assertEqual(again['request'], a['request'])
        self.assertEqual(self.snap()['segments_reserved'], 1)

    def test_missing_child_after_reserve_is_unknown_not_zero_write(self):
        self.reserve(); self.reload()
        with self.assertRaises(journal.GoalJournalStopped):
            journal.reconcile_child(self.value, 'g1', 'r1', physical_meter=meter(()), **self.kw())
        self.assertEqual(self.snap()['journal_status'], 'frozen')
        self.assertEqual(journal.blocking_goal(self.value), 'g1')

    def test_dispatched_without_child_is_valid_state_but_cannot_retry(self):
        self.reserve(); self.dispatch(); self.reload()
        journal.validate_goal_journal(self.value)
        with self.assertRaises(journal.GoalJournalStopped): self.dispatch()
        self.assertEqual(self.snap()['journal_status'], 'frozen')
        self.assertEqual(journal.blocking_goal(self.value), 'g1')

    def test_commit_without_parent_ack_reconciles_raw_child_without_move(self):
        reserved = self.reserve(); self.dispatch(req=reserved['request'])
        committed(self.value, reserved['request'], status='satisfied'); self.reload(); self.now = 104.
        before = copy.deepcopy(self.value['goal_segments'])
        s = journal.reconcile_child(self.value, 'g1', 'r1', physical_meter=meter(), **self.kw())
        self.assertEqual(s['journal_status'], 'completed'); self.assertEqual(s['confirmed_steps'], 1)
        self.assertEqual(before, self.value['goal_segments'])
        again = journal.reconcile_child(self.value, 'g1', 'r1', physical_meter=meter(), **self.kw())
        self.assertTrue(again['deduplicated']); self.assertEqual(again['confirmed_steps'], 1)

    def test_late_commit_is_accounted_but_never_goal_completion_after_restart(self):
        _, s = self.first(status='satisfied', confirmation=135.)
        self.assertTrue(s['late_accounted_only']); self.assertEqual(s['confirmed_steps'], 1)
        self.assertEqual(s['journal_status'], 'stopped')
        self.assertEqual(s['journal_reason'], 'goal_time_budget_exhausted')
        self.reload(); self.now = 140.
        s = self.snap(); self.assertTrue(s['late_accounted_only']); self.assertEqual(s['confirmed_steps'], 1)
        with self.assertRaises(journal.GoalJournalStopped): journal.next_caps(self.value, 'g1', **self.kw())

    def test_known_completed_goal_cannot_become_active_on_later_clock(self):
        self.first(status='satisfied'); self.reload(); self.now = 500.
        s = self.snap(); self.assertEqual(s['journal_status'], 'completed')
        with self.assertRaises(journal.GoalJournalStopped): journal.next_caps(self.value, 'g1', **self.kw())
        self.assertEqual(self.snap()['journal_status'], 'completed')

    def test_pending_expiry_never_releases_parent(self):
        self.reserve(); self.dispatch(); self.now = 200.
        self.assertEqual(self.snap()['journal_status'], 'pending')
        with self.assertRaises(journal.GoalJournalStopped): journal.next_caps(self.value, 'g1', **self.kw())
        self.assertEqual(journal.blocking_goal(self.value), 'g1')
        with self.assertRaises(journal.GoalJournalStopped):
            journal.create_goal(self.value, 'g2', 'session1', **self.kw())

    def test_clock_domain_change_absorbs_without_renewing_deadline(self):
        self.reserve(); self.dispatch(); self.reload(); self.domain = 'boot2'; self.now = 0.
        with self.assertRaises(journal.GoalJournalStopped): self.snap()
        r = self.value['goal_supervision']['records']['g1']
        self.assertEqual(r['deadline_monotonic'], 130.)
        self.assertEqual(r['status'], 'frozen'); journal.validate_goal_journal(self.value)
        self.domain = 'boot1'; self.now = 105.
        self.assertEqual(self.snap()['journal_status'], 'frozen')

    def test_backward_clock_fails_closed(self):
        self.now = 104.; self.snap(); self.now = 103.
        with self.assertRaises(journal.GoalJournalStopped): self.snap()
        self.assertEqual(journal.blocking_goal(self.value), 'g1')

    def test_nonfinite_and_boolean_clock_rejected(self):
        for now in (True, float('nan'), float('inf'), -1., 10**1000):
            value = {}; before = copy.deepcopy(value)
            with self.subTest(now=str(now)[:20]), self.assertRaises(journal.GoalJournalError):
                journal.create_goal(value, 'g', 's', clock_domain='boot', now=now)
            self.assertEqual(value, before)

    def test_create_same_identity_is_idempotent_not_budget_reset(self):
        self.first(); self.now = 110.; before = self.snap()
        again = journal.create_goal(self.value, 'g1', 'session1', **self.kw())
        self.assertEqual(again['confirmed_steps'], before['confirmed_steps'])
        self.assertEqual(again['deadline_monotonic'], 130.)
        with self.assertRaises(journal.GoalJournalStopped):
            journal.create_goal(self.value, 'g1', 'other', **self.kw())
        self.assertEqual(self.snap()['journal_status'], 'frozen')

    def test_new_parent_refused_while_active(self):
        with self.assertRaises(journal.GoalJournalStopped):
            journal.create_goal(self.value, 'g2', 'session2', **self.kw())
        self.assertEqual(set(self.value['goal_supervision']['records']), {'g1'})

    def test_child_identity_cannot_be_reused_after_known_terminal_parent(self):
        self.first(status='satisfied')
        self.now = 103.; journal.create_goal(self.value, 'g2', 'session2', **self.kw())
        with self.assertRaises(journal.GoalJournalStopped):
            journal.reserve_segment(self.value, 'g2', 'r1', request(), **self.kw())
        self.assertEqual(journal.child_owner(self.value, 'r1'), 'g1')

    def test_existing_standalone_child_cannot_be_claimed_by_parent(self):
        committed(self.value, request(), parent='other')
        self.value['goal_segments']['records']['r1'].pop('parent_goal_id')
        with self.assertRaises(journal.GoalJournalStopped): self.reserve()
        self.assertEqual(self.snap()['journal_status'], 'frozen')

    def test_child_dispatch_checks_session_request_and_fixed_deadline(self):
        for change in ('session', 'request', 'deadline'):
            self.setUp(); a = self.reserve(); req = a['request']; session = 'session1'
            if change == 'session': session = 'another'
            if change == 'request': req = dict(req, target_clearance_m=.002)
            if change == 'deadline': self.now = 130.
            with self.subTest(change=change), self.assertRaises(journal.GoalJournalStopped):
                journal.mark_dispatched(self.value, 'g1', 'r1', session, req, **self.kw())
            self.assertEqual(self.value['goal_supervision']['records']['g1']['status'], 'frozen')

    def test_running_child_cannot_be_confirmed_or_retried(self):
        a = self.reserve(); self.dispatch(req=a['request'])
        committed(self.value, a['request']); self.value['goal_segments']['records']['r1'].update(status='running', result=None)
        self.reload()
        with self.assertRaises(journal.GoalJournalStopped):
            journal.reconcile_child(self.value, 'g1', 'r1', physical_meter=meter(), **self.kw())
        self.assertEqual(self.snap()['journal_status'], 'frozen')

    def test_child_parent_link_session_and_request_must_match(self):
        for change in ('parent_goal_id', 'session_id', 'request_fingerprint'):
            self.setUp(); a = self.reserve(); self.dispatch(req=a['request'])
            committed(self.value, a['request']); self.value['goal_segments']['records']['r1'][change] = 'wrong'
            with self.subTest(change=change), self.assertRaises(journal.GoalJournalError):
                journal.confirm_segment(self.value, 'g1', 'r1', physical_meter=meter(), **self.kw())

    def test_inflight_blocks_dispatch_and_even_known_child_reconciliation(self):
        self.reserve(); self.value['inflight'] = {'operation_id': 'unknown'}
        with self.assertRaises(journal.GoalJournalStopped): self.dispatch()
        self.assertEqual(self.snap()['journal_status'], 'frozen')
        self.setUp(); a = self.reserve(); self.dispatch(req=a['request']); committed(self.value, a['request'])
        self.value['inflight'] = {'operation_id': 'unknown'}
        with self.assertRaises(journal.GoalJournalStopped):
            journal.confirm_segment(self.value, 'g1', 'r1', physical_meter=meter(), **self.kw())
        self.assertEqual(self.snap()['confirmed_steps'], 0)

    def test_orphan_supervised_child_or_child_before_dispatch_invalidates_state(self):
        committed(self.value, request())
        with self.assertRaises(journal.GoalJournalError): journal.validate_goal_journal(self.value)
        self.setUp(); a = self.reserve(); committed(self.value, a['request'])
        with self.assertRaises(journal.GoalJournalError): journal.validate_goal_journal(self.value)

    def test_entire_missing_parent_journal_does_not_hide_supervised_child(self):
        self.first(status='satisfied'); self.value.pop('goal_supervision')
        with self.assertRaises(journal.GoalJournalError): journal.validate_goal_journal(self.value)
        with self.assertRaises(journal.GoalJournalError): journal.blocking_goal(self.value)

    def test_tool_historical_wrapper_is_not_first_confirmation(self):
        a = self.reserve(); self.dispatch(req=a['request'])
        result = committed(self.value, a['request']); result['historical_receipt'] = True
        with self.assertRaises(journal.GoalJournalStopped):
            journal.confirm_segment(self.value, 'g1', 'r1', physical_meter=meter(), **self.kw())

    def test_incomplete_or_extra_setter_meter_freezes_parent(self):
        for physical in (None, dict(meter(), complete=False), meter(count=2), dict(meter(), rollback_count=1)):
            self.setUp(); a = self.reserve(); self.dispatch(req=a['request']); committed(self.value, a['request'])
            with self.subTest(physical=physical), self.assertRaises(journal.GoalJournalStopped):
                journal.confirm_segment(self.value, 'g1', 'r1', physical_meter=physical, **self.kw())
            self.assertEqual(self.snap()['journal_status'], 'frozen')

    def test_extra_physical_meter_payload_is_rejected_without_persisting_blob(self):
        a = self.reserve(); self.dispatch(req=a['request']); committed(self.value, a['request'])
        before = copy.deepcopy(self.value['goal_supervision']['records']['g1']['children'][0])
        physical = dict(meter(), extra='x'*(256*1024))
        with self.assertRaises(journal.GoalJournalStopped):
            journal.confirm_segment(self.value, 'g1', 'r1', physical_meter=physical, **self.kw())
        record = self.value['goal_supervision']['records']['g1']
        self.assertEqual(record['status'], 'frozen'); self.assertEqual(record['children'][0], before)
        self.assertLess(len(json.dumps(self.value['goal_supervision'])), 4096)
        self.reload(); journal.validate_goal_journal(self.value)

    def test_whole_journal_bound_failure_does_not_commit_prospective_child(self):
        self.first(status='satisfied'); self.now = 103.
        journal.create_goal(self.value, 'g2', 'session2', **self.kw())
        second = journal.reserve_segment(self.value, 'g2', 'r2', request(), **self.kw())
        journal.mark_dispatched(self.value, 'g2', 'r2', 'session2', second['request'], **self.kw())
        committed(self.value, second['request'], identity='r2', segment='s2', parent='g2',
                  session='session2', status='satisfied')
        before = copy.deepcopy(self.value['goal_supervision']['records']['g2']['children'][0])
        limit = len(json.dumps(self.value['goal_supervision'], sort_keys=True,
                              ensure_ascii=True, separators=(',', ':')).encode())
        with patch.object(journal, 'MAX_JOURNAL_BYTES', limit):
            journal.validate_goal_journal(self.value)
            with self.assertRaises(journal.GoalJournalStopped):
                journal.confirm_segment(self.value, 'g2', 'r2', physical_meter=meter(), **self.kw())
            record = self.value['goal_supervision']['records']['g2']
            self.assertEqual(record['status'], 'frozen'); self.assertEqual(record['children'][0], before)
            self.reload(); journal.validate_goal_journal(self.value)

    def test_changed_confirmed_raw_child_is_rejected_on_load(self):
        self.first(); self.reload()
        self.value['goal_segments']['records']['r1']['result']['actual_total_translation_m'] = 0.
        with self.assertRaises(journal.GoalJournalError): journal.validate_goal_journal(self.value)

    def test_cached_status_deadline_chronology_and_unknown_fields_cannot_forge_completion(self):
        self.first(); original = copy.deepcopy(self.value)
        for change in ('status', 'deadline', 'event_time', 'budget_cache', 'duplicate_child'):
            self.value = copy.deepcopy(original); record = self.value['goal_supervision']['records']['g1']
            if change == 'status': record.update(status='completed', reason='goal_satisfied')
            if change == 'deadline': record['deadline_monotonic'] += 30
            if change == 'event_time': record['children'][0]['confirmed_monotonic'] = 99.
            if change == 'budget_cache': record['remaining_steps'] = 8
            if change == 'duplicate_child': record['children'].append(copy.deepcopy(record['children'][0]))
            with self.subTest(change=change), self.assertRaises(journal.GoalJournalError): journal.validate_goal_journal(self.value)

    def test_fixed_original_triangle_and_goal_roles_cannot_change(self):
        self.first(); caps = journal.next_caps(self.value, 'g1', **self.kw())
        for change in ({'reference_triangle_index': 3}, {'focal_id': 'another'}, {'target_clearance_m': .002}):
            req = request(**caps); req.update(change)
            with self.subTest(change=change), self.assertRaises(journal.GoalJournalError): self.reserve('r2', req)
        self.assertEqual(self.snap()['segments_reserved'], 1)

    def test_remaining_recovery_budget_does_not_reset_after_restart(self):
        self.value = {}; journal.create_goal(self.value, 'g1', 'session1',
            limits=GoalBudgetLimits(max_recoveries=0), **self.kw())
        self.first(); self.reload()
        with self.assertRaises(journal.GoalJournalStopped): journal.next_caps(self.value, 'g1', **self.kw())
        self.assertEqual(self.snap()['journal_reason'], 'goal_recovery_budget_exhausted')

    def test_old_state_compatible_and_malformed_ledgers_fail_closed(self):
        journal.validate_goal_journal({'old': 'state'}); self.assertIsNone(journal.blocking_goal({}))
        for bad in (None, [], {'schema_version': 'wrong', 'records': {}},
                    {'schema_version': 'goal-supervision-v1', 'records': {}, 'cache': 1}):
            with self.subTest(bad=bad), self.assertRaises(journal.GoalJournalError):
                journal.validate_goal_journal({'goal_supervision': bad})

    def test_malformed_field_types_always_raise_validation_error(self):
        original = copy.deepcopy(self.value)
        for field, bad in (('status', []), ('clock_domain', {}), ('children', {}),
                           ('limits', False), ('started_monotonic', True)):
            value = copy.deepcopy(original); value['goal_supervision']['records']['g1'][field] = bad
            with self.subTest(field=field), self.assertRaises(journal.GoalJournalError):
                journal.validate_goal_journal(value)
        for value in (None, [], 0, True):
            with self.subTest(value=value), self.assertRaises(journal.GoalJournalError):
                journal.validate_goal_journal(value)

    def test_dispatch_cannot_coerce_boolean_into_numeric_request_field(self):
        a = self.reserve(); req = copy.deepcopy(a['request']); req['direction_world'][0] = False
        with self.assertRaises(journal.GoalJournalStopped): self.dispatch(req=req)
        self.assertEqual(self.snap()['journal_status'], 'frozen')

    def test_no_silent_eviction_at_capacity(self):
        self.value = {}
        for index in range(journal.MAX_GOALS):
            goal = 'g'+str(index); child = 'r'+str(index); session = 's'+str(index)
            journal.create_goal(self.value, goal, session, **self.kw())
            a = journal.reserve_segment(self.value, goal, child, request(), **self.kw())
            journal.mark_dispatched(self.value, goal, child, session, a['request'], **self.kw())
            committed(self.value, a['request'], identity=child, parent=goal, session=session,
                      segment='seg'+str(index), status='satisfied')
            journal.confirm_segment(self.value, goal, child, physical_meter=meter(), **self.kw())
        before = copy.deepcopy(self.value)
        with self.assertRaises(journal.GoalJournalStopped):
            journal.create_goal(self.value, 'overflow', 'session', **self.kw())
        self.assertEqual(before, self.value)


if __name__ == '__main__': unittest.main()

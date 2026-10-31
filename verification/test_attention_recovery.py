"""V2 recovery contracts with genuine raster/geometry and controlled costs.

Only elapsed optional-attention cost is prescribed; these are scheduling and
quality-gate checks, never measured performance or model quality evidence.
"""
import copy
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin import auto_router as router_module
from human_eye_plugin import attention_rendering as ar
from human_eye_plugin.auto_router import HumanEyeAutoRouter, _attention_retry_record, _attention_retry_state
from verification import test_attention_retry as retry_tests


class RecoveryRecordTests(unittest.TestCase):
    def test_failure_count_and_exact_deadline_are_bound(self):
        for failures, delay in ((1, 1.), (2, 4.), (3, 8.)):
            record = _attention_retry_record('a' * 64, 100., failures=failures)
            self.assertEqual(record['retry_at_s'], 100. + delay)
            self.assertNotIn('pending_plan_signature', record)
            self.assertEqual(_attention_retry_state(record, 100.), record)
            for other_delay in (0., .5, 1., 4., 8.):
                if other_delay == delay:
                    continue
                invalid = dict(record, retry_at_s=100. + other_delay)
                with self.subTest(failures=failures, other_delay=other_delay):
                    self.assertIsNone(_attention_retry_state(invalid, 100.))

    def test_fractional_valid_timestamps_round_trip(self):
        for at in (0., .1, 100.1, 1_725_000_000.125):
            for failures in (1, 2, 3):
                record = _attention_retry_record('a' * 64, at, failures=failures)
                self.assertEqual(_attention_retry_state(record, at), record)

    def test_v1_record_and_its_pending_plan_are_not_v2_state(self):
        old = dict(_attention_retry_record('a' * 64, 100.),
                   schema_version='bounded_cost_retry_v1', retry_at_s=104.,
                   pending_plan_signature='b' * 64)
        self.assertIsNone(_attention_retry_state(old, 100.))
        current_with_legacy_field = _attention_retry_record('a' * 64, 100.)
        current_with_legacy_field['pending_plan_signature'] = None
        self.assertIsNone(_attention_retry_state(current_with_legacy_field, 100.))


class RecoveryFlowTests(unittest.TestCase):
    setUp = retry_tests.AttentionRetryTests.setUp
    observe = retry_tests.AttentionRetryTests.observe
    feedback = retry_tests.AttentionRetryTests.feedback

    def test_first_short_retry_boundary_is_inclusive(self):
        self.observe(41.)
        self.now = float(np.nextafter(101., 100.))
        _, facts, calls, raster = self.observe()
        self.assertEqual((calls, raster), (0, 0))
        self.assertTrue(facts['attention']['retry']['unattempted_due_to_cooldown'])
        self.now = 101.
        _, facts, calls, raster = self.observe()
        self.assertEqual((calls, raster), (1, 1))
        self.assertTrue(facts['attention']['applied'])
        self.assertIsNone(self.feedback())

    def test_second_failure_waits_four_seconds_and_recovers_on_first_pass(self):
        self.observe(41.); self.now = 101.; self.observe(41.)
        self.assertEqual(self.feedback()['retry_at_s'], 105.)
        self.now = 104.9
        _, _, calls, raster = self.observe()
        self.assertEqual((calls, raster), (0, 0))
        self.now = 105.
        _, facts, calls, raster = self.observe()
        self.assertEqual((calls, raster), (1, 1))
        self.assertTrue(facts['attention']['applied'])
        self.assertFalse(facts['attention']['retry']['confirmed_opportunity_withheld'])
        self.assertIsNone(self.feedback())

    def test_nonbudget_rejection_resets_sustained_overload_to_first_failure(self):
        self.observe(41.); self.now = 101.; self.observe(41.)
        self.now = 105.; _, facts, _, _ = self.observe(unreadable=True)
        self.assertFalse(facts['attention']['applied'])
        self.assertIsNone(self.feedback())
        self.now = 106.; self.observe(41.)
        self.assertEqual(self.feedback()['budget_failures'], 1)
        self.assertEqual(self.feedback()['retry_at_s'], 107.)

    def test_transient_error_rechecks_after_one_second_despite_long_ttl(self):
        self.router.observation_ttl_s = 120.
        _, facts, calls, _ = self.observe(error=True)
        self.assertEqual(calls, 1)
        self.assertEqual(facts['attention']['reason_codes'], ['attention_unavailable'])
        self.assertIsNone(self.feedback())
        state = self.router.export_state()['sessions'][0][1]
        self.assertEqual(state['observation']['attention_recheck_after'], 101.)
        self.now = 100.5
        result, facts, calls, _ = self.observe()
        self.assertTrue(result['cache_hit']); self.assertEqual(calls, 0)
        self.assertFalse(facts['attention']['retry']['candidate_attempted'])
        self.now = 101.
        result, facts, calls, raster = self.observe()
        self.assertFalse(result['cache_hit']); self.assertEqual((calls, raster), (1, 1))
        self.assertTrue(facts['attention']['applied'])

    def test_error_ends_budget_chain_but_preserves_its_own_short_retry(self):
        self.router.observation_ttl_s = 120.
        self.observe(41.); self.now = 101.
        _, facts, _, _ = self.observe(error=True)
        self.assertEqual(facts['attention']['reason_codes'], ['attention_unavailable'])
        self.assertIsNone(self.feedback())
        self.assertEqual(self.router.export_state()['sessions'][0][1]['observation']['attention_recheck_after'], 102.)
        self.now = 102.
        _, facts, _, _ = self.observe(41.)
        self.assertFalse(facts['attention']['applied'])
        self.assertEqual(self.feedback()['budget_failures'], 1)
        self.assertEqual(self.feedback()['retry_at_s'], 103.)

    def test_legacy_feedback_import_invalidates_cached_wait_and_reobserves(self):
        self.router.observation_ttl_s = 120.
        self.observe(41.)
        saved = self.router.export_state(); state = saved['sessions'][0][1]
        state['attention_retry'].update(schema_version='bounded_cost_retry_v1',
                                        retry_at_s=104., pending_plan_signature='b' * 64)
        state['observation']['contract_revision'] = 'v1-attention-bounded-retry-20261025'
        self.now = 100.5
        fresh = HumanEyeAutoRouter(quad_size=128, observation_ttl_s=120., clock=lambda: self.now)
        fresh.import_state(saved)
        self.assertIsNone(fresh.export_state()['sessions'][0][1]['observation'])
        self.assertNotIn('attention_retry', fresh.export_state()['sessions'][0][1])
        result, facts, calls, raster = self.observe(router=fresh)
        self.assertFalse(result['cache_hit']); self.assertEqual((calls, raster), (1, 1))
        self.assertTrue(facts['attention']['applied'])

    def test_legacy_observation_contract_cannot_replay_even_without_feedback(self):
        self.router.observation_ttl_s = 120.; self.observe()
        saved = self.router.export_state()
        saved['sessions'][0][1]['observation']['contract_revision'] = 'v1-snapshot-capabilities-task-delta-20261026'
        self.now = 100.5
        fresh = HumanEyeAutoRouter(quad_size=128, observation_ttl_s=120., clock=lambda: self.now)
        fresh.import_state(saved)
        self.assertIsNone(fresh.export_state()['sessions'][0][1]['observation'])
        result, _, calls, _ = self.observe(router=fresh)
        self.assertFalse(result['cache_hit']); self.assertEqual(calls, 1)

    def test_forged_first_failure_eight_second_deadline_is_discarded(self):
        self.router.observation_ttl_s = 120.; self.observe(41.)
        saved = self.router.export_state()
        saved['sessions'][0][1]['attention_retry']['retry_at_s'] = 108.
        self.now = 100.5
        fresh = HumanEyeAutoRouter(quad_size=128, observation_ttl_s=120., clock=lambda: self.now)
        fresh.import_state(saved)
        result, facts, calls, _ = self.observe(router=fresh)
        self.assertFalse(result['cache_hit']); self.assertEqual(calls, 1)
        self.assertTrue(facts['attention']['applied'])

    def test_confirmed_recovery_keeps_all_current_cost_depth_owner_and_readability_gates(self):
        self.observe(41.); self.now = 101.
        _, facts, calls, raster = self.observe(40.)
        attention = facts['attention']
        self.assertEqual((calls, raster), (1, 1))
        self.assertTrue(attention['applied'])
        self.assertEqual(attention['additional_cost_ms'], 40.)
        self.assertGreaterEqual(attention['net_gain_px'], 2.)
        self.assertEqual(attention['raster_witness_supported'], [True, True])
        self.assertTrue(attention['visibility_verified'])
        self.assertTrue(attention['readability_verified'])
        self.assertTrue(attention['readability']['passed'])
        self.assertTrue(facts['canvas']['views'][3]['all_supplied_geometry_participates_in_depth'])
        self.assertFalse(attention['retry']['confirmed_opportunity_withheld'])

    def test_recovery_cannot_adopt_when_current_raster_depth_is_unsupported(self):
        self.observe(41.); self.now = 101.
        real_raster = ar.rasterize_attention
        def missing_depth(*args, **kwargs):
            value = real_raster(*args, **kwargs); value[1][:] = np.inf
            return value
        with patch.object(ar, 'rasterize_attention', side_effect=missing_depth):
            _, facts, _, _ = self.observe()
        self.assertFalse(facts['attention']['applied'])
        self.assertIsNone(facts['attention']['state_to_commit'])
        self.assertEqual(facts['attention']['raster_witness_supported'], [False, False])
        self.assertEqual(facts['canvas']['raster_schedule']['final_q4'], 'target')
        self.assertIsNone(self.feedback())

    def test_recovery_cannot_adopt_when_current_owner_readability_is_missing(self):
        self.observe(41.); self.now = 101.
        real_raster = ar.rasterize_attention
        def missing_owners(*args, **kwargs):
            value = real_raster(*args, **kwargs); value[2][:] = -1
            return value
        with patch.object(ar, 'rasterize_attention', side_effect=missing_owners):
            _, facts, _, _ = self.observe()
        self.assertFalse(facts['attention']['applied'])
        self.assertFalse(facts['attention']['readability']['passed'])
        self.assertIsNone(facts['attention']['state_to_commit'])
        self.assertEqual(facts['canvas']['raster_schedule']['final_q4'], 'target')
        self.assertIsNone(self.feedback())

    def test_sustained_failure_then_stable_success_has_bounded_no_double_confirmation_recovery(self):
        for at in (100., 101., 105.):
            self.now = at; self.observe(41.)
        self.assertEqual(self.feedback()['retry_at_s'], 113.)
        for at in (106., 108., 110., 112.):
            self.now = at; _, facts, calls, raster = self.observe()
            self.assertEqual((calls, raster), (0, 0))
            self.assertFalse(facts['attention']['retry']['confirmed_opportunity_withheld'])
        self.now = 114.; _, facts, calls, raster = self.observe()
        self.assertEqual((calls, raster), (1, 1))
        self.assertTrue(facts['attention']['applied'])
        self.assertIsNone(self.feedback())

    def test_alternating_short_failures_have_no_confirmed_or_unattempted_view_loss(self):
        adopted = attempted = skipped = withheld = 0
        for index in range(12):
            self.now = 100. + 2 * index
            _, facts, calls, _ = self.observe(41. if index % 2 == 0 else 0.)
            retry = facts['attention']['retry']
            attempted += retry['candidate_attempted']; skipped += retry['unattempted_due_to_cooldown']
            withheld += retry['confirmed_opportunity_withheld']; adopted += bool(facts['attention']['applied'])
            self.assertEqual(calls, 1)
        self.assertEqual((attempted, skipped, withheld, adopted), (12, 0, 0, 6))

    def test_valid_cost_record_limits_cache_when_derived_deadline_is_missing_or_overlong(self):
        for altered_deadline in ('missing', 1e12):
            with self.subTest(altered_deadline=altered_deadline):
                self.setUp(); self.router.observation_ttl_s = 120.; self.observe(41.)
                saved = self.router.export_state(); state = saved['sessions'][0][1]
                self.assertEqual(state['attention_retry']['retry_at_s'], 101.)
                if altered_deadline == 'missing':
                    state['observation'].pop('attention_recheck_after')
                else:
                    state['observation']['attention_recheck_after'] = altered_deadline
                self.now = 101.
                fresh = HumanEyeAutoRouter(quad_size=128, observation_ttl_s=120., clock=lambda: self.now)
                fresh.import_state(saved)
                result, facts, calls, raster = self.observe(router=fresh)
                self.assertFalse(result['cache_hit']); self.assertEqual((calls, raster), (1, 1))
                self.assertTrue(facts['attention']['applied'])
                self.assertNotIn('attention_retry', fresh.export_state()['sessions'][0][1])

    def test_malformed_derived_deadline_invalidates_cache_without_losing_current_geometry(self):
        for malformed in ('bad', None, True, float('nan'), float('inf'), 10**400, []):
            with self.subTest(malformed=malformed):
                self.setUp(); self.router.observation_ttl_s = 120.; self.observe(41.)
                saved = self.router.export_state()
                saved['sessions'][0][1]['observation']['attention_recheck_after'] = malformed
                self.now = 101.
                fresh = HumanEyeAutoRouter(quad_size=128, observation_ttl_s=120., clock=lambda: self.now)
                fresh.import_state(saved)
                result, facts, calls, raster = self.observe(router=fresh)
                self.assertFalse(result['cache_hit']); self.assertEqual((calls, raster), (1, 1))
                self.assertTrue(facts['measurement']['measurement_valid'])
                self.assertTrue(facts['attention']['applied'])

    def test_error_context_reconstructs_short_deadline_after_persistence(self):
        for altered_deadline in ('missing', 1e12):
            with self.subTest(altered_deadline=altered_deadline):
                self.setUp(); self.router.observation_ttl_s = 120.; self.observe(error=True)
                saved = self.router.export_state(); state = saved['sessions'][0][1]
                self.assertNotIn('attention_retry', state)
                if altered_deadline == 'missing':
                    state['observation'].pop('attention_recheck_after')
                else:
                    state['observation']['attention_recheck_after'] = altered_deadline
                self.now = 100.5
                fresh = HumanEyeAutoRouter(quad_size=128, observation_ttl_s=120., clock=lambda: self.now)
                fresh.import_state(saved)
                result, _, calls, _ = self.observe(router=fresh)
                self.assertTrue(result['cache_hit']); self.assertEqual(calls, 0)
                self.now = 101.
                result, facts, calls, raster = self.observe(router=fresh)
                self.assertFalse(result['cache_hit']); self.assertEqual((calls, raster), (1, 1))
                self.assertTrue(facts['attention']['applied'])

    def test_malformed_cached_context_is_discarded_instead_of_blocking_current_observation(self):
        malformed_contexts = ('not-json', '[]', 'null', '{"attention":[]}',
                              '{"attention":{"reason_codes":"attention_unavailable"}}',
                              '{"attention":{"reason_codes":[],"retry":[]}}',
                              '[' * 2000 + '0' + ']' * 2000)
        for context in malformed_contexts:
            with self.subTest(context=context[:80]):
                self.setUp(); self.router.observation_ttl_s = 120.; self.observe()
                saved = self.router.export_state()
                saved['sessions'][0][1]['observation']['result']['context_text'] = context
                self.now = 100.5
                fresh = HumanEyeAutoRouter(quad_size=128, observation_ttl_s=120., clock=lambda: self.now)
                fresh.import_state(saved)
                result, facts, calls, _ = self.observe(router=fresh)
                self.assertFalse(result['cache_hit']); self.assertEqual(calls, 1)
                self.assertTrue(facts['measurement']['measurement_valid'])

    def test_static_nonbudget_hold_missing_deadline_keeps_normal_cache_fastpath(self):
        self.router.observation_ttl_s = 120.; self.observe(unreadable=True)
        saved = self.router.export_state(); state = saved['sessions'][0][1]
        self.assertNotIn('attention_retry', state)
        state['observation'].pop('attention_recheck_after', None)
        self.now = 102.
        fresh = HumanEyeAutoRouter(quad_size=128, observation_ttl_s=120., clock=lambda: self.now)
        fresh.import_state(saved)
        cached_context = state['observation']['result']['context_text']
        real_loads = router_module.json.loads
        with patch.object(router_module.json, 'loads', wraps=real_loads) as loads:
            result, facts, calls, raster = self.observe(router=fresh)
        self.assertTrue(result['cache_hit']); self.assertEqual((calls, raster), (0, 0))
        self.assertFalse(facts['attention']['applied'])
        self.assertTrue(facts['attention']['evidence_reused'])
        # Other modules and the harness also use the shared json module. The
        # original cached facts, specifically, are parsed only once in product.
        self.assertEqual(sum(call.args[0] == cached_context for call in loads.call_args_list), 1)

    def test_normal_cache_hit_with_valid_deadline_preserves_current_attempt_accounting(self):
        self.router.observation_ttl_s = 120.; self.observe()
        self.now = 100.5
        result, facts, calls, raster = self.observe()
        self.assertTrue(result['cache_hit']); self.assertEqual((calls, raster), (0, 0))
        self.assertFalse(facts['attention']['retry']['candidate_attempted'])
        self.assertFalse(facts['attention']['retry']['unattempted_due_to_cooldown'])
        self.assertFalse(facts['attention']['retry']['confirmed_opportunity_withheld'])


if __name__ == '__main__':
    unittest.main()

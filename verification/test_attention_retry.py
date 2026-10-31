"""Bounded retry contracts using real rendering with explicitly controlled clocks.

These tests verify scheduling, actual raster/geometry/readability gates and PNG
delivery. Controlled costs are boundary evidence, never performance results.
"""
import base64
import copy
import io
import json
import math
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from human_eye_plugin import attention_rendering as ar
from human_eye_plugin import auto_router as router_module
from human_eye_plugin.auto_router import (HumanEyeAutoRouter, _attention_retry_record,
                                         _attention_retry_state)
from verification.test_attention_rendering import near_scene
from verification.test_auto_router import observation, action


class RetryRecordTests(unittest.TestCase):
    def record(self):
        return _attention_retry_record('a' * 64, 100.)

    def test_valid_record_is_copied_and_clock_bounds_are_inclusive(self):
        record = self.record()
        restored = _attention_retry_state(record, 100., key='a' * 64)
        self.assertEqual(record, restored)
        self.assertIsNot(record, restored)
        self.assertIsNotNone(_attention_retry_state(record, 130.))
        self.assertIsNone(_attention_retry_state(record, 130.000001))
        self.assertIsNone(_attention_retry_state(record, 99.999999))

    def test_malformed_records_are_discarded(self):
        variants = [None, [], {}, True]
        for field, values in {
            'schema_version': ['old', None], 'key': ['a', 'A' * 64, [], None],
            'last_attempt_s': [True, '100', math.nan, math.inf, -math.inf, 101., 10**400],
            'retry_at_s': [False, '104', math.nan, math.inf, -math.inf, 99., 108.000001, 10**400],
            'budget_failures': [True, 0, 4, 1., '1'],
            'pending_plan_signature': ['x', 'A' * 64, 0, []],
        }.items():
            for value in values:
                variant = self.record(); variant[field] = value; variants.append(variant)
        extra = self.record(); extra['unauthorized_field'] = 1; variants.append(extra)
        for value in variants:
            with self.subTest(value=value):
                self.assertIsNone(_attention_retry_state(value, 100.))
        for invalid_now in (True, '100', math.nan, math.inf, -math.inf, 10**400):
            self.assertIsNone(_attention_retry_state(self.record(), invalid_now))

    def test_complete_key_mismatch_discards_and_large_failure_count_is_bounded(self):
        self.assertIsNone(_attention_retry_state(self.record(), 101., key='b' * 64))
        self.assertEqual(_attention_retry_record('a' * 64, 100., failures=999)['budget_failures'], 3)


class AttentionRetryTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.
        self.router = HumanEyeAutoRouter(quad_size=128, observation_ttl_s=.25,
                                        clock=lambda: self.now)
        self.event = observation(scene=near_scene())

    def observe(self, cost_ms=0., *, router=None, event=None, error=False,
                early=False, unreadable=False):
        """Use genuine full-scene pixels; substitute elapsed cost only."""
        clock = [0.]
        real_raster = ar.rasterize_attention
        real_claim = ar._claim_prepared_attention_inputs
        real_apply = ar.apply_attention_to_canvas
        def raster(*args, **kwargs):
            value = real_raster(*args, **kwargs)
            clock[0] = cost_ms / 1000
            if unreadable:
                value[0][:] = (70, 70, 70)
            return value
        def claim(*args, **kwargs):
            value = real_claim(*args, **kwargs)
            if early:
                clock[0] = cost_ms / 1000
            return value
        def apply(*args, **kwargs):
            if error:
                raise RuntimeError('controlled optional attention failure')
            return real_apply(*args, **kwargs)
        with patch.object(ar.time, 'perf_counter', side_effect=lambda: clock[0]), \
             patch.object(ar, 'rasterize_attention', side_effect=raster) as raster_calls, \
             patch.object(ar, '_claim_prepared_attention_inputs', side_effect=claim), \
             patch.object(router_module, 'apply_attention_to_canvas', side_effect=apply) as calls:
            result = (router or self.router).handle_event(event or self.event)
        self.assertEqual(result['route'], 'engine', result)
        facts = json.loads(result['context_text'])
        if (event or self.event).get('include_image', True):
            self.assertIsNotNone(result['image'])
            self.assertTrue(facts['canvas']['raster_schedule']['canvas_complete'])
        return result, facts, calls.call_count, raster_calls.call_count

    def feedback(self):
        return self.router.export_state()['sessions'][0][1].get('attention_retry')

    def test_initial_success_adopts_without_artificial_double_confirmation(self):
        _, facts, calls, raster = self.observe()
        self.assertEqual((calls, raster), (1, 1))
        self.assertTrue(facts['attention']['applied'])
        self.assertIsNone(self.feedback())
        self.assertTrue(facts['attention']['retry']['candidate_attempted'])

    def test_budget_failure_cools_without_camera_or_raster_attempt(self):
        _, failed, _, _ = self.observe(41.)
        self.assertIn('attention_additional_compute_budget_exceeded', failed['attention']['reason_codes'])
        record = self.feedback()
        self.assertEqual(record['retry_at_s'], 101.)
        self.now = 100.5
        _, held, calls, raster = self.observe()
        self.assertEqual((calls, raster), (0, 0))
        self.assertEqual(held['attention']['reason_codes'], ['attention_cost_cooldown'])
        self.assertTrue(held['attention']['retry']['unattempted_due_to_cooldown'])
        self.assertFalse(held['attention']['retry']['unattempted_counterfactual_eligibility_known'])
        self.assertEqual(record, self.feedback())
        self.assertEqual(held['canvas']['raster_schedule']['final_q4'], 'target')
        self.assertTrue(held['measurement']['measurement_valid'])

    def test_pre_raster_budget_exhaustion_also_enters_bounded_cooldown(self):
        _, facts, calls, raster = self.observe(41., early=True)
        self.assertEqual((calls, raster), (1, 0))
        self.assertEqual(facts['attention']['reason_codes'], ['attention_budget_exhausted_before_raster'])
        self.assertEqual(self.feedback()['retry_at_s'], 101.)

    def test_actual_forty_ms_confirmation_still_adopts_and_gate_is_unchanged(self):
        _, facts, _, raster = self.observe(40.)
        self.assertEqual(raster, 1)
        self.assertTrue(facts['attention']['applied'])
        self.assertEqual(facts['attention']['additional_cost_ms'], 40.)
        self.assertIsNone(self.feedback())

    def test_retry_deadline_is_eligible_and_confirmed_recovery_displays_immediately(self):
        first, _, _, _ = self.observe(41.)
        self.now = 101.
        second, facts, calls, raster = self.observe()
        self.assertEqual((calls, raster), (1, 1))
        attention = facts['attention']
        self.assertTrue(attention['applied'])
        self.assertIsNotNone(attention['state_to_commit'])
        self.assertFalse(attention['retry']['confirmed_opportunity_withheld'])
        self.assertFalse(attention['retry']['requires_same_plan_two_consecutive_confirmations'])
        self.assertTrue(attention['visibility_verified'])
        self.assertTrue(attention['readability_verified'])
        self.assertGreaterEqual(attention['net_gain_px'], 2.)
        self.assertIsNotNone(self.router.export_state()['sessions'][0][1]['attention_state'])
        self.assertIsNone(self.feedback())
        self.assertEqual(facts['canvas']['raster_schedule']['final_q4'], 'contact')
        a = np.asarray(Image.open(io.BytesIO(base64.b64decode(first['image']['data']))))
        b = np.asarray(Image.open(io.BytesIO(base64.b64decode(second['image']['data']))))
        np.testing.assert_array_equal(a[:128], b[:128])
        np.testing.assert_array_equal(a[128:, :128], b[128:, :128])
        self.assertFalse(np.array_equal(a[128:, 128:], b[128:, 128:]))

    def test_new_budget_failure_after_recovery_restarts_short_retry_without_pending_plan(self):
        self.observe(41.); self.now = 101.; self.observe()
        self.now = 102.; _, facts, _, _ = self.observe(41.)
        self.assertFalse(facts['attention']['applied'])
        self.assertEqual(self.feedback()['budget_failures'], 1)
        self.assertEqual(self.feedback()['retry_at_s'], 103.)
        self.assertNotIn('pending_plan_signature', self.feedback())
        self.now = 103.; _, facts, _, _ = self.observe()
        self.assertTrue(facts['attention']['applied'])

    def test_geometric_readability_rejection_ends_budget_failure_chain(self):
        self.observe(41.)
        self.now = 101.; _, facts, _, _ = self.observe(unreadable=True)
        self.assertFalse(facts['attention']['applied'])
        self.assertIsNone(self.feedback())
        self.now = 102.; _, facts, _, _ = self.observe()
        self.assertTrue(facts['attention']['applied'])

    def test_exception_ends_budget_failure_chain_and_cannot_commit_pose(self):
        self.observe(41.)
        self.now = 101.; _, facts, _, _ = self.observe(error=True)
        self.assertEqual(facts['attention']['reason_codes'], ['attention_unavailable'])
        self.assertIsNone(self.feedback())
        self.assertEqual(facts['canvas']['raster_schedule']['final_q4'], 'target')
        self.now = 102.; _, facts, _, _ = self.observe()
        self.assertTrue(facts['attention']['applied'])

    def test_repeated_budget_failure_is_bounded_at_eight_seconds(self):
        self.observe(41.)
        self.now = 101.; self.observe(41.)
        self.assertEqual(self.feedback()['budget_failures'], 2)
        self.assertEqual(self.feedback()['retry_at_s'], 105.)
        for now in (105., 113., 121.):
            self.now = now; _, facts, calls, _ = self.observe(41.)
            self.assertEqual(calls, 1)
            self.assertFalse(facts['attention']['applied'])
            self.assertEqual(self.feedback()['retry_at_s'], now + 8.)
            self.assertEqual(self.feedback()['budget_failures'], 3)
        self.now = 129.; _, facts, _, _ = self.observe()
        self.assertTrue(facts['attention']['applied'])

    def test_skipped_events_do_not_refresh_expiry(self):
        self.observe(41.)
        original = self.feedback()
        for now in (100.3, 100.5, 100.7, 100.99):
            self.now = now; _, _, calls, raster = self.observe()
            self.assertEqual((calls, raster), (0, 0))
            self.assertEqual(self.feedback(), original)
        self.now = 131.
        _, facts, _, _ = self.observe()
        self.assertTrue(facts['attention']['applied'])
        self.assertIsNone(self.feedback())

    def test_cache_replay_never_counts_a_new_attempt_or_opportunity(self):
        self.router.observation_ttl_s = 120.
        self.observe(41.)
        self.now = 100.5; result, facts, calls, _ = self.observe()
        self.assertTrue(result['cache_hit']); self.assertEqual(calls, 0)
        self.assertFalse(facts['attention']['retry']['candidate_attempted'])
        self.assertFalse(facts['attention']['retry']['unattempted_due_to_cooldown'])
        self.now = 101.; _, facts, calls, _ = self.observe()
        self.assertEqual(calls, 1)
        self.assertTrue(facts['attention']['applied'])
        self.assertFalse(facts['attention']['retry']['confirmed_opportunity_withheld'])
        saved = self.feedback()
        self.now = 101.5; result, facts, calls, _ = self.observe()
        self.assertTrue(result['cache_hit']); self.assertEqual(calls, 0)
        self.assertFalse(facts['attention']['retry']['confirmed_opportunity_withheld'])
        self.assertEqual(saved, self.feedback())
        self.assertTrue(facts['attention']['applied'])

    def test_complete_scene_pair_task_query_and_size_changes_reset_feedback(self):
        for change in ('geometry', 'pair', 'task', 'query', 'size', 'backend'):
            with self.subTest(change=change):
                self.setUp(); self.observe(41.); self.now = 100.5
                event = copy.deepcopy(self.event)
                if change == 'geometry':
                    event['scene']['meshes'][1]['color_rgb'] = [71, 140, 210]
                elif change == 'pair':
                    event['focal_id'], event['reference_id'] = 'base', 'part'
                elif change == 'task':
                    event['task_instruction'] = 'Inspect the same clearance.'
                elif change == 'query':
                    event['query'] = {'mode': 'nearest', 'max_exact_pairs': 1}
                elif change == 'size':
                    self.router.quad_size = 256
                with patch.object(router_module, '_ATTENTION_COST_CONTRACT',
                                  'changed' if change == 'backend' else router_module._ATTENTION_COST_CONTRACT):
                    _, facts, calls, _ = self.observe(event=event)
                self.assertEqual(calls, 1)
                self.assertFalse(facts['attention']['retry']['unattempted_due_to_cooldown'])
                self.assertFalse(facts['attention']['retry']['confirmed_opportunity_withheld'])

    def test_text_only_does_not_advance_or_reset_feedback(self):
        self.observe(41.); saved = self.feedback(); self.now = 100.5
        event = dict(self.event, include_image=False)
        result, facts, calls, raster = self.observe(event=event)
        self.assertEqual((calls, raster), (0, 0))
        self.assertIsNone(result['image'])
        self.assertEqual(self.feedback(), saved)
        self.now = 100.75; _, facts, calls, _ = self.observe()
        self.assertEqual(calls, 0)
        self.assertTrue(facts['attention']['retry']['unattempted_due_to_cooldown'])

    def test_export_import_retains_short_retry_and_immediate_confirmed_recovery(self):
        self.observe(41.); self.now = 100.5
        fresh = HumanEyeAutoRouter(quad_size=128, observation_ttl_s=.25, clock=lambda: self.now)
        fresh.import_state(self.router.export_state())
        _, facts, calls, _ = self.observe(router=fresh)
        self.assertEqual(calls, 0)
        self.now = 101.; _, facts, _, _ = self.observe(router=fresh)
        self.assertTrue(facts['attention']['applied'])
        self.assertFalse(facts['attention']['retry']['confirmed_opportunity_withheld'])
        again = HumanEyeAutoRouter(quad_size=128, observation_ttl_s=.25, clock=lambda: self.now)
        again.import_state(fresh.export_state())
        self.now = 102.; _, facts, _, _ = self.observe(router=again)
        self.assertTrue(facts['attention']['applied'])

    def test_cross_size_import_does_not_replay_cached_picture(self):
        self.router.observation_ttl_s = 120.
        self.observe(41.); self.now = 100.5
        fresh = HumanEyeAutoRouter(quad_size=256, observation_ttl_s=120., clock=lambda: self.now)
        fresh.import_state(self.router.export_state())
        result, facts, calls, _ = self.observe(router=fresh)
        self.assertFalse(result['cache_hit']); self.assertEqual(calls, 1)
        self.assertEqual(facts['canvas']['quad_size'], 256)
        self.assertFalse(facts['attention']['retry']['confirmed_opportunity_withheld'])

    def test_corrupt_imported_feedback_discards_cached_cooldown(self):
        self.router.observation_ttl_s = 120.
        self.observe(41.); self.now = 100.5
        for field, value in (('retry_at_s', math.nan), ('retry_at_s', 1e12),
                             ('last_attempt_s', 200.), ('last_attempt_s', 10**400),
                             ('retry_at_s', 10**400), ('budget_failures', True)):
            with self.subTest(field=field, value=value):
                saved = self.router.export_state()
                saved['sessions'][0][1]['attention_retry'][field] = value
                fresh = HumanEyeAutoRouter(quad_size=128, observation_ttl_s=120., clock=lambda: self.now)
                fresh.import_state(saved)
                self.assertNotIn('attention_retry', fresh.export_state()['sessions'][0][1])
                result, facts, calls, _ = self.observe(router=fresh)
                self.assertFalse(result['cache_hit']); self.assertEqual(calls, 1)
                self.assertTrue(facts['attention']['applied'])

    def test_wall_clock_rollback_discards_feedback_and_future_pose(self):
        self.observe(); self.now = 101.; self.observe(41.)
        self.now = 99.
        result, facts, calls, _ = self.observe()
        self.assertEqual(calls, 1)
        self.assertFalse(result['cache_hit'])
        self.assertTrue(facts['attention']['applied'])
        self.assertTrue(facts['attention']['retry']['discarded_invalid_pose_time'])
        self.assertIsNone(self.feedback())

    def test_future_or_nonfinite_pose_time_cannot_create_permanent_hold(self):
        self.observe()
        for value in (1e12, math.nan, math.inf, True, '100', 10**400):
            with self.subTest(value=value):
                self.router._sessions['a']['attention_state']['last_shift_s'] = value
                self.now += 1.
                _, facts, calls, _ = self.observe()
                self.assertEqual(calls, 1)
                self.assertTrue(facts['attention']['applied'])
                self.assertTrue(facts['attention']['retry']['discarded_invalid_pose_time'])

    def test_retry_deadline_and_existing_dwell_use_earliest_future_time(self):
        self.router.observation_ttl_s = 120.
        self.observe(); self.now = 100.1
        changed = dict(self.event, task_instruction='fresh observation key')
        self.observe(41., event=changed, early=True)
        state = self.router.export_state()['sessions'][0][1]
        # The cost checkpoint can reject a dwell-hold too; choose its valid
        # future dwell boundary before the later bounded retry deadline.
        self.assertEqual(state['observation']['attention_recheck_after'], 101.)
        self.assertEqual(state['attention_retry']['retry_at_s'], 101.1)
        self.now = 101.
        result, facts, calls, _ = self.observe(event=changed)
        self.assertFalse(result['cache_hit']); self.assertEqual(calls, 0)
        self.assertTrue(facts['attention']['retry']['unattempted_due_to_cooldown'])
        self.now = 101.1
        result, _, calls, _ = self.observe(event=changed)
        self.assertFalse(result['cache_hit']); self.assertEqual(calls, 1)

    def test_before_action_gate_does_not_gain_authority_from_retry(self):
        result, _, _, _ = self.observe(41.)
        saved = self.feedback()
        self.now = 101.
        stale = action(result, observation_id='wrong-token')
        blocked = self.router.handle_event(stale)
        self.assertEqual(blocked['route'], 'blocked')
        self.assertFalse(blocked['allow_action'])
        self.assertEqual(blocked['reason_codes'], ['stale_or_missing_observation'])
        self.assertEqual(saved, self.feedback())

    def test_isolated_budget_failures_do_not_suppress_eligible_following_views(self):
        sequence = [(100., 41.), (102., 0.), (104., 0.), (106., 41.),
                    (108., 0.), (110., 0.), (112., 0.), (114., 0.),
                    (116., 0.), (118., 0.)]
        attempted = suppressed = withheld = adopted = 0
        for now, cost in sequence:
            self.now = now
            _, facts, calls, _ = self.observe(cost)
            retry = facts['attention']['retry']
            attempted += int(retry['candidate_attempted'])
            suppressed += int(retry['unattempted_due_to_cooldown'])
            withheld += int(retry['confirmed_opportunity_withheld'])
            adopted += int(facts['attention'].get('applied', False))
            self.assertEqual(calls, int(retry['candidate_attempted']))
        self.assertEqual((attempted, suppressed, withheld, adopted), (10, 0, 0, 8))


if __name__ == '__main__':
    unittest.main()

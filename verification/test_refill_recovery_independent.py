"""Independent public-router checks for bounded recovery of optional labels.

The geometry, raw collection, glyph qualification and delivered PNGs are real.
Only clocks are controlled. These are scheduling boundary tests, not latency
measurements or model task-benefit scores.
"""
import copy
import json
import math
import unittest
from unittest.mock import patch

from human_eye_plugin import attention_rendering
from human_eye_plugin import auto_router
from human_eye_plugin import visible_refill
from verification.test_visible_refill_delivery import raw, refill_rows


class RefillRecoveryIndependentTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.
        self.router = self.new_router()
        self.event = {
            'event': 'before_model', 'session_id': 'independent-refill-recovery',
            'task_kind': 'spatial_3d', 'scene': raw(),
            'focal_id': 'focus', 'reference_id': 'reference',
        }

    def new_router(self, *, ttl=120., size=256):
        return auto_router.HumanEyeAutoRouter(
            quad_size=size, observation_ttl_s=ttl, clock=lambda: self.now)

    def observe(self, cost_ms=0., *, router=None, event=None, forbid_pool=False,
                annotation_cost_ms=0.):
        """Make the genuine proposal, then charge root's final commit clock."""
        ticks = [0.]
        helper_ticks = [0.]
        original = visible_refill.VisibleRefillCollector.finish
        glyph_check = visible_refill._boxed_glyph_survives
        finishes = []

        def glyph(*args, **kwargs):
            result = glyph_check(*args, **kwargs)
            if annotation_cost_ms:
                ticks[0] = helper_ticks[0] = annotation_cost_ms / 1000.
            return result

        def finish(collector, *args, **kwargs):
            result = original(collector, *args, **kwargs)
            finishes.append(result[2].get('status'))
            ticks[0] = max(ticks[0], cost_ms / 1000.)
            return result

        pool = (patch.object(auto_router, '_build_task_label_bundle',
                             side_effect=AssertionError('recovery must skip setup'))
                if forbid_pool else patch.object(
                    auto_router, '_build_task_label_bundle',
                    wraps=auto_router._build_task_label_bundle))
        with patch.object(auto_router, 'visible_refill_clock',
                          side_effect=lambda: ticks[0]), \
             patch.object(visible_refill, 'visible_refill_clock',
                          side_effect=lambda: helper_ticks[0]), \
             patch.object(visible_refill, '_boxed_glyph_survives', new=glyph), \
             patch.object(attention_rendering.time, 'perf_counter', return_value=0.), \
             patch.object(visible_refill.VisibleRefillCollector, 'finish', new=finish), \
             pool as pool_calls:
            result = (router or self.router).handle_event(event or self.event)
        self.assertEqual(result['route'], 'engine', result)
        facts = json.loads(result['context_text'])
        return result, facts, finishes, pool_calls.call_count

    def record(self, router=None):
        state = (router or self.router).export_state()['sessions'][0][1]
        return state.get('refill_retry')

    def assert_actual_gain(self, result, facts):
        self.assertTrue(facts['label_refill']['applied'], facts['label_refill'])
        self.assertEqual(facts['label_refill']['new_readable_object_ids'],
                         ['risk-02-visible'])
        self.assertEqual(len(refill_rows(result)), 1)
        self.assertTrue(facts['measurement']['measurement_valid'])
        self.assertAlmostEqual(facts['measurement']['signed_clearance_m'], .004)
        self.assertFalse(facts['label_refill']['execution_authority'])

    def test_cache_hold_is_reused_without_new_work_then_recovers_at_deadline(self):
        first, failed, finishes, _ = self.observe(6.)
        self.assertEqual(finishes, ['proposal_ready'])
        self.assertFalse(failed['label_refill']['applied'])
        self.assertAlmostEqual(failed['label_refill']['additional_cost_ms'], 6.)
        saved = self.record()
        self.assertEqual(saved['attempts'], 1)
        self.assertEqual(saved['retry_cost_ms'], 0.)
        self.assertEqual(saved['retry_at_s'], 101.)
        for instant in (100.1, 100.5, 100.999):
            self.now = instant
            result, facts, finishes, pools = self.observe(forbid_pool=True)
            receipt = facts['label_refill']
            self.assertTrue(result['cache_hit'])
            self.assertEqual((finishes, pools), ([], 0))
            self.assertEqual(result['observation_id'], first['observation_id'])
            self.assertTrue(receipt['evidence_reused'])
            self.assertEqual(receipt['current_event_refill_cost_ms'], 0.)
            self.assertEqual(receipt['current_event_candidate_raster_count'], 0)
            self.assertAlmostEqual(receipt['additional_cost_ms'], 6.)
            self.assertFalse(receipt['retry']['attempted'])
            self.assertEqual(self.record(), saved)
        self.now = 101.
        result, facts, finishes, pools = self.observe()
        self.assertFalse(result['cache_hit'])
        self.assertEqual((finishes, pools), (['proposal_ready'], 1))
        self.assertNotEqual(result['observation_id'], first['observation_id'])
        self.assert_actual_gain(result, facts)
        self.assertIsNone(self.record())

    def test_expired_cache_during_cooldown_skips_setup_collection_and_finish(self):
        self.router.observation_ttl_s = .1
        _, initial, _, _ = self.observe(6.)
        saved = self.record()
        self.now = 100.5
        result, facts, finishes, pools = self.observe(forbid_pool=True)
        self.assertFalse(result['cache_hit'])
        self.assertEqual((finishes, pools), ([], 0))
        receipt = facts['label_refill']
        self.assertEqual(receipt['reason'], 'visible_refill_retry_cooldown')
        self.assertEqual(receipt['current_event_refill_cost_ms'], 0.)
        self.assertFalse(receipt['retry']['attempted'])
        self.assertEqual(self.record(), saved)
        self.assertEqual(facts['measurement'], initial['measurement'])
        self.assertEqual(facts['scene_contacts'], initial['scene_contacts'])
        self.assertEqual(refill_rows(result), [])
        self.assertTrue(facts['canvas']['raster_schedule']['canvas_complete'])

    def test_restart_preserves_cooldown_and_does_not_hide_due_retry_behind_ttl(self):
        self.observe(6.)
        saved = self.router.export_state()
        self.now = 100.5
        restarted = self.new_router()
        restarted.import_state(saved)
        result, _, finishes, pools = self.observe(router=restarted, forbid_pool=True)
        self.assertTrue(result['cache_hit'])
        self.assertEqual((finishes, pools), ([], 0))
        self.assertEqual(self.record(restarted), self.record())
        self.now = 101.
        result, facts, _, _ = self.observe(router=restarted)
        self.assertFalse(result['cache_hit'])
        self.assert_actual_gain(result, facts)
        self.assertIsNone(self.record(restarted))

    def test_expired_cache_restart_preserves_episode_bound(self):
        self.router.observation_ttl_s = .1
        self.observe(6.)
        saved = self.record()
        self.now = 100.5
        restarted = self.new_router(ttl=.1)
        restarted.import_state(self.router.export_state())
        self.assertEqual(self.record(restarted), saved)
        result, facts, finishes, pools = self.observe(router=restarted,
                                                     forbid_pool=True)
        self.assertFalse(result['cache_hit'])
        self.assertEqual((finishes, pools), ([], 0))
        self.assertEqual(facts['label_refill']['reason'],
                         'visible_refill_retry_cooldown')
        self.assertEqual(self.record(restarted), saved)

    def test_two_additional_attempts_exhaust_and_skips_do_not_extend_episode(self):
        self.router.observation_ttl_s = .1
        self.observe(6.)
        for instant, attempts in ((101., 2), (103., 3)):
            self.now = instant
            _, facts, finishes, _ = self.observe(6.)
            self.assertEqual(finishes, ['proposal_ready'])
            self.assertFalse(facts['label_refill']['applied'])
            self.assertEqual(self.record()['attempts'], attempts)
        saved = self.record()
        self.assertAlmostEqual(saved['retry_cost_ms'], 12.)
        self.assertIsNone(saved['retry_at_s'])
        for instant in (103.5, 110., 129.99):
            self.now = instant
            _, facts, finishes, pools = self.observe(forbid_pool=True)
            self.assertEqual((finishes, pools), ([], 0))
            self.assertEqual(facts['label_refill']['reason'],
                             'visible_refill_retry_exhausted')
            self.assertEqual(self.record(), saved)
        self.now = 130.001
        result, facts, finishes, pools = self.observe()
        self.assertEqual((finishes, pools), (['proposal_ready'], 1))
        self.assert_actual_gain(result, facts)

    def test_actual_retry_overrun_is_retained_and_prevents_second_extra_attempt(self):
        self.router.observation_ttl_s = .1
        self.observe(6.)
        self.now = 101.
        _, facts, _, _ = self.observe(12.)
        self.assertAlmostEqual(facts['label_refill']['additional_cost_ms'], 12.)
        self.assertEqual(self.record()['attempts'], 2)
        self.assertAlmostEqual(self.record()['retry_cost_ms'], 12.)
        self.assertIsNone(self.record()['retry_at_s'])
        self.now = 103.
        _, facts, finishes, pools = self.observe(forbid_pool=True)
        self.assertEqual((finishes, pools), ([], 0))
        self.assertEqual(facts['label_refill']['reason'],
                         'visible_refill_retry_exhausted')

    def test_initial_overrun_does_not_consume_additional_retry_allowance(self):
        self.observe(20.)
        self.assertEqual(self.record()['retry_cost_ms'], 0.)
        self.now = 101.
        result, facts, finishes, pools = self.observe()
        self.assertEqual((finishes, pools), (['proposal_ready'], 1))
        self.assert_actual_gain(result, facts)

    def test_helper_annotation_budget_hold_is_recoverable_not_permanently_cached(self):
        result, facts, finishes, pools = self.observe(annotation_cost_ms=6.)
        receipt = facts['label_refill']
        self.assertEqual((finishes, pools), (['hold'], 1))
        self.assertEqual(receipt['reason'], 'refill_budget_exceeded_after_annotation')
        self.assertEqual(receipt['budget_failure_scope'], 'local')
        self.assertEqual(receipt['new_readable_object_ids'], [])
        self.assertEqual(refill_rows(result), [])
        self.assertIsNotNone(self.record())
        self.now = 101.
        result, facts, _, _ = self.observe()
        self.assert_actual_gain(result, facts)
        self.assertIsNone(self.record())

    def test_scene_task_yaw_size_and_contract_changes_invalidate_old_hold(self):
        for change in ('scene', 'task', 'yaw', 'size', 'contract'):
            with self.subTest(change=change):
                self.setUp()
                self.observe(6.)
                self.now = 100.5
                event = copy.deepcopy(self.event)
                if change == 'scene':
                    event['scene']['meshes'][0]['color_rgb'] = [35, 65, 95]
                elif change == 'task':
                    event['task_instruction'] = 'Inspect the same three-dimensional gap.'
                elif change == 'yaw':
                    event['yaw_symmetry_order'] = 4
                elif change == 'size':
                    self.router.quad_size = 384
                revision = (auto_router.OBSERVATION_CONTRACT_REVISION + '-independent'
                            if change == 'contract' else
                            auto_router.OBSERVATION_CONTRACT_REVISION)
                with patch.object(auto_router, 'OBSERVATION_CONTRACT_REVISION', revision):
                    result, facts, finishes, pools = self.observe(event=event)
                self.assertFalse(result['cache_hit'])
                self.assertEqual((finishes, pools), (['proposal_ready'], 1))
                self.assert_actual_gain(result, facts)
                self.assertIsNone(self.record())

    def test_explicit_focus_skips_refill_and_does_not_acquire_retry_authority(self):
        self.observe(6.)
        self.now = 100.5
        event = dict(self.event, query={'label_object_ids': ['focus']})
        result, facts, finishes, pools = self.observe(event=event, forbid_pool=True)
        self.assertEqual((finishes, pools), ([], 0))
        self.assertNotIn('label_refill', facts)
        self.assertEqual(refill_rows(result), [])
        self.assertIsNone(result['allow_action'])

    def test_text_only_does_not_consume_or_refresh_recovery(self):
        self.observe(6.)
        saved = self.record()
        self.now = 100.5
        event = dict(self.event, include_image=False)
        result, _, finishes, pools = self.observe(event=event, forbid_pool=True)
        self.assertIsNone(result['image'])
        self.assertEqual((finishes, pools), ([], 0))
        self.assertEqual(self.record(), saved)

    def test_text_only_then_restart_retains_original_image_episode(self):
        self.observe(6.)
        saved = self.record()
        self.now = 100.5
        self.observe(event=dict(self.event, include_image=False), forbid_pool=True)
        restarted = self.new_router()
        restarted.import_state(self.router.export_state())
        self.assertEqual(self.record(restarted), saved)
        self.now = 100.75
        result, facts, finishes, pools = self.observe(router=restarted,
                                                     forbid_pool=True)
        self.assertFalse(result['cache_hit'])
        self.assertEqual((finishes, pools), ([], 0))
        self.assertEqual(facts['label_refill']['reason'],
                         'visible_refill_retry_cooldown')
        self.assertEqual(self.record(restarted), saved)
        self.now = 101.
        result, facts, _, _ = self.observe(router=restarted)
        self.assert_actual_gain(result, facts)

    def test_corrupt_persisted_retry_cannot_pin_hold_or_inflate_wait(self):
        self.observe(6.)
        self.now = 100.5
        for field, value in (('retry_at_s', math.nan), ('retry_at_s', 1e12),
                             ('started_s', 200.), ('attempts', True),
                             ('retry_cost_ms', -1.), ('retry_cost_ms', math.inf),
                             ('key', 'b' * 64)):
            with self.subTest(field=field, value=value):
                state = self.router.export_state()
                state['sessions'][0][1]['refill_retry'][field] = value
                restarted = self.new_router()
                restarted.import_state(state)
                result, facts, finishes, pools = self.observe(router=restarted)
                self.assertFalse(result['cache_hit'])
                self.assertEqual((finishes, pools), (['proposal_ready'], 1))
                self.assert_actual_gain(result, facts)

    def test_future_wall_clock_record_cannot_suppress_current_observation(self):
        self.observe(6.)
        self.now = 99.
        result, facts, finishes, pools = self.observe()
        self.assertFalse(result['cache_hit'])
        self.assertEqual((finishes, pools), (['proposal_ready'], 1))
        self.assert_actual_gain(result, facts)

    def test_refill_due_does_not_wait_for_later_attention_deadline(self):
        self.observe(6.)
        state = self.router.export_state()
        session = state['sessions'][0][1]
        session['attention_retry'] = auto_router._attention_retry_record(
            session['refill_retry']['key'], 100., failures=2)
        attention_record = copy.deepcopy(session['attention_retry'])
        session['observation']['attention_recheck_after'] = 104.
        restarted = self.new_router()
        restarted.import_state(state)
        self.now = 101.
        result, facts, finishes, pools = self.observe(router=restarted)
        self.assertFalse(result['cache_hit'])
        self.assertEqual((finishes, pools), (['proposal_ready'], 1))
        self.assert_actual_gain(result, facts)
        self.assertTrue(facts['attention']['retry']['unattempted_due_to_cooldown'])
        restored = restarted.export_state()['sessions'][0][1]
        self.assertEqual(restored['attention_retry'], attention_record)
        self.assertNotIn('refill_retry', restored)

    def test_earlier_attention_due_does_not_spend_refill_attempt(self):
        self.observe(6.)
        state = self.router.export_state()
        session = state['sessions'][0][1]
        refill_record = copy.deepcopy(session['refill_retry'])
        session['attention_retry'] = auto_router._attention_retry_record(
            session['refill_retry']['key'], 99.75)
        session['observation']['attention_recheck_after'] = 100.75
        restarted = self.new_router()
        restarted.import_state(state)
        self.now = 100.75
        result, facts, finishes, pools = self.observe(router=restarted,
                                                     forbid_pool=True)
        self.assertFalse(result['cache_hit'])
        self.assertEqual((finishes, pools), ([], 0))
        self.assertTrue(facts['attention']['retry']['candidate_attempted'])
        self.assertEqual(facts['label_refill']['reason'],
                         'visible_refill_retry_cooldown')
        self.assertEqual(self.record(restarted), refill_record)


if __name__ == '__main__':
    unittest.main()

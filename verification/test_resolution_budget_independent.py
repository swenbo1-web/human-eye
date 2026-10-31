"""Independent public-delivery checks for bounded resolution allowances.

Rendering, ownership, final glyphs and PNG delivery are real. Only clocks are
controlled, so these checks establish budget semantics rather than speed.
"""
import io
import json
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from PIL import Image

from human_eye_plugin import attention_rendering, auto_router, refill_budget, visible_refill
from human_eye_plugin.attention_policy import AttentionLimits
from human_eye_plugin.refill_recovery import MAX_RETRY_COST_MS
from verification.test_visible_refill_delivery import raw, refill_rows, png
from verification.test_visible_refill_policy import prepared, finish


class ResolutionBudgetIndependentTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.
        self.event = {'event': 'before_model', 'session_id': 'resolution-independent',
                      'task_kind': 'spatial_3d', 'scene': raw(),
                      'focal_id': 'focus', 'reference_id': 'reference'}

    def router(self, size):
        return auto_router.HumanEyeAutoRouter(quad_size=size, clock=lambda: self.now)

    def observe(self, size=384, *, cost_ms=0., before_ms=0., mode='resolution',
                router=None, event=None, forged_limit=False, forbid_finish=False):
        ticks = [0.]
        original_finish = visible_refill.VisibleRefillCollector.finish
        original_caption = auto_router._annotate_orthogonal_target_measurement
        proposals = []

        def caption(*args, **kwargs):
            value = original_caption(*args, **kwargs)
            ticks[0] = before_ms / 1000.
            return value

        def deliver(*args, **kwargs):
            if forbid_finish:
                raise AssertionError('A valid cached delivery must not redo refill')
            value = original_finish(*args, **kwargs)
            proposals.append(value[2]['status'])
            if forged_limit:
                value[2].update(budget_ms=10**9, shared_budget_limit_ms=10**9,
                                budget_policy={'incremental_ms': 10**9, 'shared_ms': 10**9})
            ticks[0] = (before_ms + cost_ms) / 1000.
            return value

        with patch.object(refill_budget, 'POLICY_MODE', mode), \
             patch.object(auto_router, 'visible_refill_clock', side_effect=lambda: ticks[0]), \
             patch.object(visible_refill, 'visible_refill_clock', return_value=0.), \
             patch.object(attention_rendering.time, 'perf_counter', return_value=0.), \
             patch.object(auto_router, '_annotate_orthogonal_target_measurement', new=caption), \
             patch.object(visible_refill.VisibleRefillCollector, 'finish', new=deliver):
            result = (router or self.router(size)).handle_event(event or self.event)
        self.assertEqual(result['route'], 'engine', result)
        facts = json.loads(result['context_text'])
        return result, facts, proposals

    def assert_gain(self, result, facts):
        receipt = facts['label_refill']
        self.assertTrue(receipt['applied'], receipt)
        self.assertEqual(receipt['new_readable_object_ids'], ['risk-02-visible'])
        self.assertEqual(len(refill_rows(result)), 1)
        self.assertTrue(facts['measurement']['measurement_valid'])
        self.assertAlmostEqual(facts['measurement']['signed_clearance_m'], .004)
        self.assertFalse(receipt['execution_authority'])

    def test_six_ms_final_work_holds_at_256_but_delivers_at_384(self):
        result, small, proposals = self.observe(256, cost_ms=6.)
        self.assertEqual(proposals, ['proposal_ready'])
        self.assertFalse(small['label_refill']['applied'])
        self.assertEqual(small['label_refill']['budget_ms'], 5.)
        self.assertEqual(small['label_refill']['budget_failure_scope'], 'local')
        result, large, proposals = self.observe(384, cost_ms=6.)
        self.assertEqual(proposals, ['proposal_ready'])
        self.assert_gain(result, large)
        self.assertEqual(large['label_refill']['budget_ms'], 8.)
        self.assertEqual(large['label_refill']['shared_budget_limit_ms'], 64.)
        self.assertAlmostEqual(large['label_refill']['additional_cost_ms'], 6.)

    def test_384_final_local_limit_and_actual_overrun_remain_bounded(self):
        result, boundary, _ = self.observe(cost_ms=8.)
        self.assert_gain(result, boundary)
        result, late, _ = self.observe(cost_ms=9.)
        receipt = late['label_refill']
        self.assertFalse(receipt['applied'])
        self.assertEqual(receipt['reason'], 'visible_refill_integration_budget_exceeded')
        self.assertEqual(receipt['budget_failure_scope'], 'local')
        self.assertAlmostEqual(receipt['additional_cost_ms'], 9.)
        self.assertEqual(refill_rows(result), [])

    def test_shared_budget_45_ms_is_resolution_specific_not_an_unbounded_pass(self):
        small_result, small, _ = self.observe(256, before_ms=45.)
        self.assertFalse(small['label_refill']['applied'])
        self.assertEqual(small['label_refill']['budget_failure_scope'], 'shared')
        result, large, _ = self.observe(384, before_ms=45.)
        self.assert_gain(result, large)
        self.assertAlmostEqual(large['label_refill']['shared_budget_elapsed_before_ms'], 45.)
        result, expired, _ = self.observe(384, before_ms=65.)
        self.assertFalse(expired['label_refill']['applied'])
        self.assertEqual(expired['label_refill']['budget_failure_scope'], 'shared')
        self.assertEqual(expired['label_refill']['reason'], 'shared_refill_budget_unavailable')

    def test_root_ignores_forged_helper_allowances(self):
        result, facts, proposals = self.observe(cost_ms=9., forged_limit=True)
        self.assertEqual(proposals, ['proposal_ready'])
        receipt = facts['label_refill']
        self.assertFalse(receipt['applied'])
        self.assertEqual(receipt['budget_ms'], 8.)
        self.assertEqual(receipt['shared_budget_limit_ms'], 64.)
        self.assertEqual(receipt['budget_policy']['incremental_ms'], 8.)
        self.assertEqual(receipt['budget_failure_scope'], 'local')
        self.assertEqual(refill_rows(result), [])
        result, facts, proposals = self.observe(cost_ms=5., before_ms=60., forged_limit=True)
        self.assertEqual(proposals, ['proposal_ready'])
        receipt = facts['label_refill']
        self.assertFalse(receipt['applied'])
        self.assertEqual(receipt['shared_budget_limit_ms'], 64.)
        self.assertEqual(receipt['budget_failure_scope'], 'shared')
        self.assertEqual(refill_rows(result), [])

    def test_matched_contact_pixels_metadata_and_facts_survive_new_allowance(self):
        baseline, old, _ = self.observe(cost_ms=9.)
        candidate, new, _ = self.observe(cost_ms=6.)
        self.assertFalse(old['label_refill']['applied'])
        self.assert_gain(candidate, new)
        self.assertEqual(old['canvas']['views'][3]['name'], 'Q4 CONTACT')
        self.assertEqual(old['canvas']['views'][3], new['canvas']['views'][3])
        first, second = Image.open(io.BytesIO(png(baseline))), Image.open(io.BytesIO(png(candidate)))
        self.assertEqual(first.crop((384,384,768,768)).tobytes(),
                         second.crop((384,384,768,768)).tobytes())
        for field in ('measurement', 'objects', 'scene_contacts', 'unknown_objects', 'rigid_frame'):
            self.assertEqual(old.get(field), new.get(field), field)
        self.assertFalse(candidate['allow_action'])

    def test_same_profile_cache_reuse_has_zero_current_cost_and_no_finish(self):
        router = self.router(384)
        first, original, _ = self.observe(router=router, cost_ms=6.)
        self.now += .1
        reused, facts, proposals = self.observe(router=router, forbid_finish=True)
        self.assertTrue(reused['cache_hit'])
        self.assertEqual(proposals, [])
        self.assertEqual(first['observation_id'], reused['observation_id'])
        receipt = facts['label_refill']
        self.assertEqual(receipt['current_event_refill_cost_ms'], 0.)
        self.assertEqual(receipt['budget_policy'], original['label_refill']['budget_policy'])

    def test_mode_change_invalidates_imported_cache_and_recovery_binding(self):
        router = self.router(384)
        first, _, _ = self.observe(router=router, cost_ms=9.)
        saved = router.export_state()
        self.assertEqual(saved['sessions'][0][1]['refill_retry']['attempts'], 1)
        self.now += .1
        restarted = self.router(384)
        restarted.import_state(saved)
        result, facts, proposals = self.observe(router=restarted, mode='fixed')
        self.assertFalse(result['cache_hit'])
        self.assertNotEqual(first['observation_id'], result['observation_id'])
        self.assertEqual(proposals, ['proposal_ready'])
        self.assert_gain(result, facts)
        self.assertEqual(facts['label_refill']['budget_ms'], 5.)
        self.assertEqual(facts['label_refill']['shared_budget_limit_ms'], 40.)
        self.assertEqual(facts['label_refill']['budget_policy']['mode'], 'fixed')
        self.assertNotIn('refill_retry', restarted.export_state()['sessions'][0][1])

    def test_policy_revision_change_invalidates_cache_even_without_size_change(self):
        router = self.router(384)
        first, _, _ = self.observe(router=router)
        with patch.object(refill_budget, 'POLICY_REVISION', 'independent-next-policy'):
            result, facts, proposals = self.observe(router=router)
        self.assertFalse(result['cache_hit'])
        self.assertNotEqual(first['observation_id'], result['observation_id'])
        self.assertEqual(proposals, ['proposal_ready'])
        self.assertEqual(facts['label_refill']['budget_policy']['policy_revision'],
                         'independent-next-policy')

    def test_collector_honors_new_limit_before_finish_and_keeps_legacy_default(self):
        with patch.object(visible_refill, 'visible_refill_clock', return_value=0.):
            collector, canvas, metadata, meshes, _ = prepared(384, setup_cost_ms=6., quad_size=384)
            self.assertEqual(len(collector._views), 3)
            result = finish(collector, canvas, metadata, meshes, remaining_budget_ms=64.)
            self.assertTrue(result[2]['applied'], result[2])
            self.assertEqual(result[2]['budget_ms'], 8.)
            self.assertAlmostEqual(result[2]['additional_cost_ms'], 6.)
            legacy, canvas, metadata, meshes, _ = prepared(384, setup_cost_ms=6.)
            result = finish(legacy, canvas, metadata, meshes)
            self.assertFalse(result[2]['applied'])
            self.assertEqual(result[2]['budget_ms'], 5.)
            self.assertEqual(result[2]['reason'], 'refill_setup_budget_exceeded')
            exceeded, canvas, metadata, meshes, _ = prepared(384, setup_cost_ms=8.1, quad_size=384)
            result = finish(exceeded, canvas, metadata, meshes, remaining_budget_ms=64.)
            self.assertFalse(result[2]['applied'])
            self.assertEqual(result[2]['budget_ms'], 8.)
            self.assertEqual(result[2]['reason'], 'refill_setup_budget_exceeded')

    def test_collector_rejects_declared_size_binding_changes(self):
        with patch.object(visible_refill, 'visible_refill_clock', return_value=0.):
            collector, canvas, metadata, meshes, _ = prepared(384, quad_size=256)
            result = finish(collector, canvas, metadata, meshes)
        self.assertFalse(result[2]['applied'])
        self.assertEqual(result[2]['reason'], 'current_refill_resolution_changed')
        self.assertEqual(collector._views, {})

    def test_policy_limits_are_monotonic_bounded_and_descriptors_are_defensive(self):
        previous = (5., 40.)
        with patch.object(refill_budget, 'POLICY_MODE', 'resolution'):
            for size in range(64, 513):
                policy = refill_budget.refill_budget_for_quad_size(size)
                value = (policy.incremental_ms, policy.shared_ms)
                self.assertGreaterEqual(value[0], previous[0])
                self.assertGreaterEqual(value[1], previous[1])
                self.assertLessEqual(value[0], 12.)
                self.assertLessEqual(value[1], 96.)
                if size <= 256:
                    self.assertEqual(value, (5.,40.))
                previous = value
            self.assertEqual(previous, (12.,96.))
            policy = refill_budget.refill_budget_for_quad_size(384)
            description = policy.descriptor()
            description['incremental_ms'] = 10**9
            self.assertEqual(policy.descriptor()['incremental_ms'], 8.)
            with self.assertRaises(FrozenInstanceError):
                policy.incremental_ms = 1000.

    def test_policy_rejects_untrusted_numeric_sizes_and_unknown_mode(self):
        for value in (True,False,'384',384.,384.1,-1,0,63,513,10**1000,
                      float('nan'),float('inf'),[],{}):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                refill_budget.refill_budget_for_quad_size(value)
        with patch.object(refill_budget, 'POLICY_MODE', 'unknown'):
            with self.assertRaises(ValueError):
                refill_budget.refill_budget_for_quad_size(384)

    def test_attention_and_retry_allowances_are_not_silently_scaled(self):
        self.assertEqual(AttentionLimits().max_additional_cost_ms, 40.)
        self.assertEqual(MAX_RETRY_COST_MS, 10.)
        result, facts, _ = self.observe(cost_ms=9.)
        self.assertEqual(facts['label_refill']['retry']['retry_cost_limit_ms'], 10.)
        self.assertEqual(facts['label_refill']['retry']['max_additional_attempts'], 2)


if __name__ == '__main__':
    unittest.main()

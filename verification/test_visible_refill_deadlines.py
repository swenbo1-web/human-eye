"""Independent refill windows account for time before and after finish entry."""
import copy
import unittest
from unittest.mock import patch

from human_eye_plugin import visible_refill as refill
from verification.test_visible_refill_policy import prepared, finish


class EntryClock:
    """The first sample starts finish; subsequent samples share one duration."""

    def __init__(self, duration_ms):
        self.duration_ms = duration_ms
        self.entered = False

    def __call__(self):
        if not self.entered:
            self.entered = True
            return 0.
        return self.duration_ms / 1000.


class VisibleRefillDeadlineTests(unittest.TestCase):
    def prepared(self, setup_cost_ms=0.):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            return prepared(setup_cost_ms=setup_cost_ms)

    def assert_original(self, output, visual, receipt, canvas, metadata):
        self.assertIs(output, canvas)
        self.assertIs(visual, metadata)
        self.assertFalse(receipt['applied'])
        self.assertEqual(receipt['new_readable_object_ids'], [])

    def test_pre_entry_cost_does_not_consume_post_entry_shared_allowance(self):
        # Four milliseconds already paid locally precede the shared remainder.
        # The old min(5, remaining) comparison rejected this legal 4.75ms case.
        for proposal_only in (False, True):
            with self.subTest(proposal_only=proposal_only):
                collector, canvas, metadata, meshes, _ = self.prepared(4.)
                with patch.object(refill, 'visible_refill_clock', new=EntryClock(.75)):
                    output, visual, receipt = finish(collector, canvas, metadata, meshes,
                        remaining_budget_ms=1., proposal_only=proposal_only)
                self.assertEqual(receipt['status'], 'proposal_ready' if proposal_only else 'applied')
                self.assertAlmostEqual(receipt['additional_cost_ms'], 4.75)
                self.assertAlmostEqual(receipt['finish_elapsed_ms'], .75)
                self.assertEqual(receipt['incremental_cost_before_finish_ms'], 4.)
                self.assertEqual(receipt['budget_ms'], 5.)
                self.assertEqual(receipt['shared_remaining_budget_ms'], 1.)
                self.assertIsNone(receipt['budget_failure_scope'])
                self.assertEqual(receipt['budget_exceeded'], [])
                self.assertIsNot(visual, metadata)
                if proposal_only:
                    self.assertIs(type(output), refill.VisibleRefillProposal)
                    self.assertTrue(collector.claim_proposal(output, canvas=canvas, metadata=metadata))
                else:
                    self.assertTrue(receipt['applied'])
                    self.assertNotEqual(output.tobytes(), canvas.tobytes())

    def test_each_window_rejects_its_own_overrun_and_reports_both_when_needed(self):
        cases = ((4.5, .6, 40., 'local', ['local']),
                 (.1, 2., 1., 'shared', ['shared']),
                 (4.5, 2., 1., 'both', ['local', 'shared']))
        for paid, duration, remaining, scope, exceeded in cases:
            with self.subTest(scope=scope):
                collector, canvas, metadata, meshes, _ = self.prepared(paid)
                with patch.object(refill, 'visible_refill_clock', new=EntryClock(duration)):
                    result = finish(collector, canvas, metadata, meshes, remaining_budget_ms=remaining)
                self.assert_original(*result, canvas, metadata)
                receipt = result[2]
                self.assertEqual(receipt['reason'], 'refill_budget_exhausted_before_qualification')
                self.assertEqual(receipt['budget_failure_scope'], scope)
                self.assertEqual(receipt['budget_exceeded'], exceeded)
                self.assertEqual(receipt['budget_checkpoint'], 'before_qualification')
                self.assertAlmostEqual(receipt['additional_cost_ms'], paid + duration)
                self.assertAlmostEqual(receipt['finish_elapsed_ms'], duration)
                self.assertEqual(collector._views, {})

    def test_exact_limits_are_inclusive_for_both_windows(self):
        collector, canvas, metadata, meshes, _ = self.prepared(4.)
        with patch.object(refill, 'visible_refill_clock', new=EntryClock(1.)):
            output, _, receipt = finish(collector, canvas, metadata, meshes, remaining_budget_ms=1.)
        self.assertTrue(receipt['applied'], receipt)
        self.assertEqual(receipt['additional_cost_ms'], 5.)
        self.assertEqual(receipt['finish_elapsed_ms'], 1.)
        self.assertIsNone(receipt['budget_failure_scope'])
        self.assertIsNot(output, canvas)

    def test_no_shared_allowance_does_not_start_qualification(self):
        collector, canvas, metadata, meshes, _ = self.prepared(.5)
        with patch.object(refill, 'visible_refill_clock', return_value=0.), \
                patch.object(refill, '_candidate_source_pixels', side_effect=AssertionError('no allowance')):
            result = finish(collector, canvas, metadata, meshes, remaining_budget_ms=0.)
        self.assert_original(*result, canvas, metadata)
        receipt = result[2]
        self.assertEqual(receipt['reason'], 'shared_refill_budget_unavailable')
        self.assertEqual(receipt['budget_failure_scope'], 'shared')
        self.assertEqual(receipt['budget_exceeded'], ['shared'])
        self.assertEqual(receipt['additional_cost_ms'], .5)
        self.assertEqual(receipt['candidate_count'], 0)

    def test_invalid_shared_allowance_is_distinct_and_keeps_paid_cost(self):
        values = (None, True, False, '1', -1., float('nan'), float('inf'),
                  -float('inf'), 10 ** 1000)
        for value in values:
            with self.subTest(value=repr(value)):
                collector, canvas, metadata, meshes, _ = self.prepared(.5)
                with patch.object(refill, 'visible_refill_clock', return_value=0.):
                    result = finish(collector, canvas, metadata, meshes, remaining_budget_ms=value)
                self.assert_original(*result, canvas, metadata)
                receipt = result[2]
                self.assertEqual(receipt['reason'], 'shared_refill_budget_unavailable')
                self.assertEqual(receipt['budget_failure_scope'], 'invalid')
                self.assertEqual(receipt['budget_exceeded'], [])
                self.assertEqual(receipt['additional_cost_ms'], .5)
                self.assertIsNone(receipt['shared_remaining_budget_ms'])

    def test_local_setup_failure_is_classified_without_erasing_sunk_cost(self):
        collector, canvas, metadata, meshes, _ = self.prepared(5.1)
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            result = finish(collector, canvas, metadata, meshes)
        self.assert_original(*result, canvas, metadata)
        receipt = result[2]
        self.assertEqual(receipt['reason'], 'refill_setup_budget_exceeded')
        self.assertEqual(receipt['budget_failure_scope'], 'local')
        self.assertEqual(receipt['budget_checkpoint'], 'setup')
        self.assertEqual(receipt['budget_exceeded'], ['local'])
        self.assertGreaterEqual(receipt['additional_cost_ms'], 5.1)

    def test_local_capture_failure_is_classified_before_finish(self):
        collector, canvas, metadata, meshes, _ = self.prepared()
        collector._cost_ms = 5.2
        collector._disable('refill_capture_budget_exceeded')
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            result = finish(collector, canvas, metadata, meshes)
        self.assert_original(*result, canvas, metadata)
        self.assertEqual(result[2]['budget_checkpoint'], 'capture')
        self.assertEqual(result[2]['budget_failure_scope'], 'local')
        self.assertGreaterEqual(result[2]['additional_cost_ms'], 5.2)

    def test_shared_expiry_after_annotation_discards_all_pixels_and_metadata(self):
        collector, canvas, metadata, meshes, _ = self.prepared(.2)
        original_pixels, original_metadata = canvas.tobytes(), copy.deepcopy(metadata)
        clock = EntryClock(0.)
        verifier = refill._boxed_glyph_survives

        def glyph_then_expire(*args):
            result = verifier(*args)
            clock.duration_ms = 2.
            return result

        with patch.object(refill, 'visible_refill_clock', new=clock), \
                patch.object(refill, '_boxed_glyph_survives', side_effect=glyph_then_expire):
            result = finish(collector, canvas, metadata, meshes, remaining_budget_ms=1.)
        self.assert_original(*result, canvas, metadata)
        receipt = result[2]
        self.assertEqual(receipt['reason'], 'refill_budget_exceeded_after_annotation')
        self.assertEqual(receipt['budget_checkpoint'], 'after_annotation')
        self.assertEqual(receipt['budget_failure_scope'], 'shared')
        self.assertAlmostEqual(receipt['additional_cost_ms'], 2.2)
        self.assertEqual(canvas.tobytes(), original_pixels)
        self.assertEqual(metadata, original_metadata)
        self.assertIsNone(collector._issued_proposal)

    def test_proposal_construction_expiry_cannot_leave_a_claimable_patch(self):
        collector, canvas, metadata, meshes, _ = self.prepared(.2)
        clock = EntryClock(0.)
        proposal_type = refill.VisibleRefillProposal

        def construct_then_expire(*args):
            proposal = proposal_type(*args)
            clock.duration_ms = 2.
            return proposal

        with patch.object(refill, 'visible_refill_clock', new=clock), \
                patch.object(refill, 'VisibleRefillProposal', side_effect=construct_then_expire):
            result = finish(collector, canvas, metadata, meshes,
                remaining_budget_ms=1., proposal_only=True)
        self.assert_original(*result, canvas, metadata)
        receipt = result[2]
        self.assertEqual(receipt['reason'], 'refill_budget_exceeded_before_proposal_commit')
        self.assertEqual(receipt['budget_checkpoint'], 'before_proposal_commit')
        self.assertEqual(receipt['budget_failure_scope'], 'shared')
        self.assertIsNone(collector._issued_proposal)

    def test_evidence_failure_is_not_misclassified_as_a_budget_retry(self):
        collector, canvas, metadata, meshes, _ = self.prepared(.2)
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            result = finish(collector, canvas, metadata, meshes, scene_fingerprint='stale')
        self.assert_original(*result, canvas, metadata)
        self.assertEqual(result[2]['reason'], 'current_refill_binding_changed')
        self.assertIsNone(result[2]['budget_failure_scope'])
        self.assertEqual(result[2]['budget_exceeded'], [])


if __name__ == '__main__':
    unittest.main()

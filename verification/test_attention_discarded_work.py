"""Cost boundaries use controlled clocks; these are not performance measurements."""
import unittest
from unittest.mock import patch

from human_eye_plugin import attention_rendering as ar
from human_eye_plugin import scene_rendering as sr
from verification.test_attention_precheck_reuse import prepared_fixture, apply


class DiscardedCandidateWorkTests(unittest.TestCase):
    def run_at_raster_cost(self, milliseconds):
        value = prepared_fixture()
        clock = [0.]
        original = ar.rasterize_attention
        def raster(*args, **kwargs):
            result = original(*args, **kwargs)
            clock[0] = milliseconds / 1000
            return result
        with patch.object(ar.time, 'perf_counter', side_effect=lambda: clock[0]), \
             patch.object(ar, 'rasterize_attention', side_effect=raster), \
             patch.object(ar, '_annotate', wraps=ar._annotate) as annotate, \
             patch.object(ar, '_contact_overlay', wraps=ar._contact_overlay) as overlay:
            output, metadata, state = apply(value)
        return value, output, metadata, state, annotate.call_count, overlay.call_count

    def test_over_budget_candidate_skips_discarded_annotations_and_preserves_fallback(self):
        value, output, metadata, state, labels, overlay = self.run_at_raster_cost(40.000001)
        attention = metadata['attention']
        self.assertEqual((labels, overlay), (0, 0))
        self.assertIs(output, value[0]); self.assertIsNone(state)
        self.assertEqual(attention['reason_codes'], ['attention_additional_compute_budget_exceeded'])
        self.assertTrue(attention['aborted_before_annotations'])
        self.assertFalse(attention['aborted_before_raster'])
        self.assertTrue(attention['raster_performed'])
        self.assertTrue(attention['visibility_verified'])
        self.assertTrue(attention['readability_verified'])
        self.assertGreater(attention['additional_cost_ms'], 40.)
        _, finished = sr._finalize_prepared_scene_q4(output, metadata, value[4],
            scene_fingerprint=value[3]['scene_fingerprint'])
        self.assertTrue(finished['raster_schedule']['canvas_complete'])
        self.assertEqual(finished['raster_schedule']['final_q4'], 'target')

    def test_exactly40_is_not_rejected_by_the_new_checkpoint(self):
        _, _, metadata, state, labels, overlay = self.run_at_raster_cost(40.)
        self.assertEqual((labels, overlay), (1, 1))
        self.assertIsNotNone(state, metadata['attention'])
        self.assertEqual(metadata['attention']['additional_cost_ms'], 40.)

    def test_under_budget_candidate_still_draws_and_confirms(self):
        _, _, metadata, state, labels, overlay = self.run_at_raster_cost(39.)
        self.assertEqual((labels, overlay), (1, 1))
        self.assertIsNotNone(state, metadata['attention'])
        self.assertTrue(metadata['attention']['visibility_verified'])
        self.assertTrue(metadata['attention']['readability_verified'])


if __name__ == '__main__':
    unittest.main()

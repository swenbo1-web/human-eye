"""Planning refuses impossible reserves before a real owned apply is sent."""
import copy
import math
import unittest

from human_eye_plugin.goal_scheduler import _forward_caps_with_rollback_reserve as bound


class SchedulerRollbackReserveTests(unittest.TestCase):
    def caps(self, **changes):
        return dict(max_steps=8, max_step_translation_m=.001,
            max_total_translation_m=.008, max_duration_s=30., **changes)

    def test_one_slot_is_a_known_pre_dispatch_refusal(self):
        for slots in (0, 1, True, 1., None):
            with self.subTest(slots=slots), self.assertRaises(ValueError):
                bound(self.caps(), {'remaining_setters':slots, 'remaining_translation_m':.008})

    def test_two_slots_allow_only_one_forward_within_the_original_goal(self):
        caps = self.caps(); report = {'remaining_setters':2, 'remaining_translation_m':.008}
        result = bound(caps, report)
        self.assertEqual(result['max_steps'], 1)
        self.assertEqual(result['max_duration_s'], caps['max_duration_s'])
        self.assertEqual(caps, self.caps())
        self.assertEqual(report, {'remaining_setters':2, 'remaining_translation_m':.008})

    def test_every_possible_count_retains_a_rollback_slot(self):
        for slots in range(2, 9):
            result = bound(self.caps(), {'remaining_setters':slots, 'remaining_translation_m':.008})
            self.assertLessEqual(result['max_steps'] + 1, slots)

    def test_path_retains_return_capacity_for_the_largest_planned_step(self):
        for path in (.008, .002, .001, 1e-5, 1e-9):
            result = bound(self.caps(), {'remaining_setters':8, 'remaining_translation_m':path})
            step = result['max_step_translation_m']; total = result['max_total_translation_m']
            self.assertLessEqual(2 * step, path)
            self.assertLessEqual(total + step, path + math.ulp(path))

    def test_original_tighter_caps_and_time_never_expand(self):
        caps = self.caps(); caps.update(max_steps=1, max_step_translation_m=.0002,
            max_total_translation_m=.0004, max_duration_s=.5)
        original = copy.deepcopy(caps)
        result = bound(caps, {'remaining_setters':8, 'remaining_translation_m':.008})
        for key in caps:self.assertLessEqual(result[key], caps[key])
        self.assertEqual(caps, original)

    def test_invalid_or_exhausted_path_is_not_sent_to_host(self):
        for path in (0., -1., float('nan'), float('inf'), .009, True, None):
            with self.subTest(path=path), self.assertRaises(ValueError):
                bound(self.caps(), {'remaining_setters':8, 'remaining_translation_m':path})


if __name__ == '__main__':unittest.main()

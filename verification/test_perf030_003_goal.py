"""The retained 0.25m goal regressions, for conditional candidate validation.

Stage A does not load or run this suite. Its two expected answers are fixed
before topology qualification and use the existing single closed fixture.
"""
import copy
import unittest

from human_eye_plugin.task_verification import evaluate_spatial_goal
from verification.perf030_002_cases import closed_counterexample


class RetainedClearanceGoalTests(unittest.TestCase):
    def check_goal(self, target, expected):
        pair = closed_counterexample()
        scene = {'revision': 'perf030-003-fixed-goal', 'unit': 'm',
                 'coordinate_frame': 'world', 'source': 'perf030_003_fixed_meshes',
                 'meshes': [mesh.to_dict() for mesh in pair]}
        before = copy.deepcopy(scene)
        result = evaluate_spatial_goal(scene, {'focal_id': pair[0].object_id,
            'reference_id': pair[1].object_id, 'target_clearance_m': target,
            'clearance_tolerance_m': 1e-9})
        self.assertTrue(result['measurement_valid'], result)
        self.assertEqual(result['task_succeeded'], expected, result)
        self.assertEqual(result['measurements']['signed_clearance_m'], .25)
        self.assertEqual(scene, before)

    def test_zero_target_is_not_satisfied(self):
        self.check_goal(0., False)

    def test_quarter_metre_target_is_satisfied(self):
        self.check_goal(.25, True)


if __name__ == '__main__':
    unittest.main()

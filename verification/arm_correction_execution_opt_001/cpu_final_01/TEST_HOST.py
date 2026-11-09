"""OPT regression uses the sealed 11 host cases plus root's ignored-write probe.

The sealed fixture's BoundView.capture already forwards **kwargs to the real
source adapter, so no adapter change or old evidence rewrite is needed.  Native
geometry is still independently evaluated by that fixture's NumPy FK/LBS.  The
ignored-write probe changes only the RNA-double setter, not capture or feedback.
"""
from unittest.mock import patch

from verification.arm_correction_execution_001 import test_host as accepted


DETAILS = {}


class ArmHostTests(accepted.ArmHostTests):
    def fixture(self, **kwargs):
        result = super().fixture(**kwargs)
        self.last_fixture = result
        return result

    def test_normal_pair_has_one_preview_and_shared_after_capture(self):
        super().test_normal_pair_has_one_preview_and_shared_after_capture()
        f = self.last_fixture
        self.assertEqual(f.last_bound.work_totals()['preparations'], 0)
        self.assertIsNone(f.last_bound.prepared)
        self.assertEqual(f.last_bound.work_totals()['static_reads'], 2)
        DETAILS['normal_pair_work'] = f.last_bound.work_totals()

    def test_no_op_uses_before_state_and_zero_writes(self):
        super().test_no_op_uses_before_state_and_zero_writes()
        f = self.last_fixture
        self.assertEqual(f.last_bound.work_totals()['preparations'], 0)
        self.assertIsNone(f.last_bound.prepared)
        self.assertEqual(f.last_bound.work_totals()['static_reads'], 1)
        DETAILS['no_op_work'] = f.last_bound.work_totals()

    def test_two_returned_setters_with_unchanged_actual_geometry_do_not_verify(self):
        f = self.fixture()
        original = accepted.PoseBone.matrix_basis

        def returned_without_change(pose, value):
            pose.fixture.attempted.append(pose.name)
            pose.fixture.returned.append(pose.name)
            pose.fixture.dirty = True

        with patch.object(accepted.PoseBone, 'matrix_basis',
                          property(original.fget, returned_without_change)):
            result = f.invoke()
        points = [f.f.mesh.evaluated.data.vertices.rows[index].co
                  for index in range(len(f.packet['rest_vertices']))]
        truth = accepted.oracle.section_objective(
            f.packet['rest_vertices'], points, f.packet['sections'])
        DETAILS['returned_but_unchanged'] = {
            'result': result, 'independent_actual_objective': truth,
            'attempted': f.attempted, 'returned': f.returned,
            'preview_calls': f.preview_calls,
            'capture_attempts': f.capture_attempts,
            'work': f.last_bound.work_totals(),
        }
        self.assertEqual(result['status'], 'feedback_failed', result)
        self.assertIs(result['executed'], True)
        self.assertIs(result['task_succeeded'], False)
        self.assertEqual((result['setter_attempts'], result['setter_returns']), (2, 2))
        self.assertEqual(f.attempted, ['arm_1', 'arm_2'])
        self.assertEqual(f.returned, ['arm_1', 'arm_2'])
        self.assertEqual(f.preview_calls, 1)
        self.assertEqual(f.capture_attempts, 2)
        self.assertIs(result['feedback']['target_met'], False)
        self.assertGreater(truth['max_section_area_loss'], f.task['max_section_area_loss'])
        self.assertAlmostEqual(result['feedback']['max_section_area_loss'],
                               truth['max_section_area_loss'], places=12)
        self.assertGreater(result['feedback']['candidate_points_error_m'],
                           f.task['position_tolerance_m'])
        self.assertEqual(f.last_bound.work_totals()['preparations'], 0)
        self.assertIsNone(f.last_bound.prepared)

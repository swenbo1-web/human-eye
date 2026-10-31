"""Certification gates and pose reports checked against actual mesh vertices."""
from __future__ import annotations

import dataclasses
import unittest
from unittest import mock

import numpy as np

from human_eye_module1_operators import MeshEntity3D, SE3AlignmentMath, SpatialAnomalySniffer
from human_eye_module1_operators.submodule_1_5_alignment_verifier import SpatialAlignmentVerifier
from module_3_3_closed_loop_control_engine import ClosedLoopActionController, ServoFSMState


SIGNS = np.array([[-1,-1,-1], [1,-1,-1], [1,1,-1], [-1,1,-1],
                  [-1,-1,1], [1,-1,1], [1,1,1], [-1,1,1]], dtype=float)
FACES = np.array([[0,2,1], [0,3,2], [4,5,6], [4,6,7], [0,1,5], [0,5,4],
                  [2,3,7], [2,7,6], [1,2,6], [1,6,5], [3,0,4], [3,4,7]], dtype=np.int32)


def box(mark, size, center, open_hull=False):
    return MeshEntity3D(mark, mark, mark, SIGNS * np.asarray(size) / 2 + center,
                        FACES[:-2].copy() if open_hull else FACES.copy(),
                        np.empty((0, 2), dtype=np.int32), (80, 120, 180), mark == '#B',
                        local_axes=np.eye(3))


def contact_pair():
    return box('#B', [.3, .2, .14], np.array([.07, -.03, .42])), box(
        '#A', [1.4, 1.2, .35], np.array([0., 0., .175]))


def action(euler=(0., 0., 0.), translation=(0., 0., 0.), shield=False):
    return {'rotation_euler_deg_xyz': list(euler), 'translation_xyz_m': list(translation),
            'enable_ecbf_safety_shield': shield}


class CertificationContractTests(unittest.TestCase):
    def setUp(self):
        ClosedLoopActionController._CTRL_STEP_CACHE.clear()
        ClosedLoopActionController._ECBF_SHIELD_CACHE.clear()
        SpatialAlignmentVerifier._RECHECK_CACHE.clear()

    def assert_pose_matches(self, before, after, report):
        matrix = np.asarray(report.posed_se3_4x4)
        np.testing.assert_allclose(before.vertices @ matrix[:3, :3].T + matrix[:3, 3],
                                   after.vertices, atol=2e-14, rtol=0)

    def test_fast_verifier_cache_binds_returned_geometry_and_report(self):
        for mutation in ('vertices', 'pose_report'):
            with self.subTest(mutation=mutation):
                self.setUp()
                focal, reference = contact_pair()
                focal = focal.translated((0., 0., .02))
                run = lambda: SpatialAlignmentVerifier.execute_alignment_and_recheck(
                    focal, reference, strict_recheck=False)
                moved, report = run()
                self.assertTrue(report.verification_passed)
                self.assertIs(run()[0], moved)
                expected = moved.vertices.copy()
                if mutation == 'vertices':
                    moved.vertices[:, 2] -= .1
                    independent = SpatialAnomalySniffer.probe_closest_clearance(moved, reference)
                    self.assertTrue(independent.is_penetrating)
                else:
                    report.posed_se3_4x4 = tuple(tuple(row) for row in np.eye(4))
                repaired, fresh_report = run()
                self.assertIsNot(fresh_report, report)
                self.assertTrue(fresh_report.verification_passed)
                np.testing.assert_allclose(repaired.vertices, expected, atol=2e-14, rtol=0)
                self.assertFalse(SpatialAnomalySniffer.probe_closest_clearance(repaired, reference).is_penetrating)
                self.assert_pose_matches(focal, repaired, fresh_report)

    def test_fast_controller_cache_binds_both_nominal_and_custom_outputs(self):
        for custom in (False, True):
            for mutation in ('vertices', 'pose_report'):
                with self.subTest(custom=custom, mutation=mutation):
                    self.setUp()
                    focal, reference = contact_pair()
                    focal = focal.translated((0., 0., .02))
                    ctrl = ClosedLoopActionController()
                    args = action(translation=(0., 0., -.02)) if custom else None
                    run = lambda: ctrl.apply_se3_prescription_and_recheck(
                        focal, reference, mcp_arguments=args, strict_recheck=False)
                    moved, report, _ = run()
                    self.assertTrue(report.verification_passed)
                    self.assertIs(run()[0], moved)
                    expected = moved.vertices.copy()
                    if mutation == 'vertices':
                        moved.vertices[:, 2] -= .1
                        self.assertTrue(SpatialAnomalySniffer.probe_closest_clearance(moved, reference).is_penetrating)
                    else:
                        report.posed_se3_4x4 = tuple(tuple(row) for row in np.eye(4))
                    repaired, fresh_report, _ = run()
                    self.assertIsNot(fresh_report, report)
                    self.assertTrue(fresh_report.verification_passed)
                    np.testing.assert_allclose(repaired.vertices, expected, atol=2e-14, rtol=0)
                    self.assertFalse(SpatialAnomalySniffer.probe_closest_clearance(repaired, reference).is_penetrating)
                    self.assert_pose_matches(focal, repaired, fresh_report)

    def test_invalid_flags_stop_nominal_custom_and_cached_execution(self):
        for invalid_field in ('measurement_valid', 'axes_valid'):
            for strict in (True, False):
                for custom in (False, True):
                    with self.subTest(field=invalid_field, strict=strict, custom=custom):
                        focal, reference = contact_pair()
                        probe = SpatialAnomalySniffer.probe_closest_clearance(focal, reference)
                        invalid = dataclasses.replace(probe, **{invalid_field: False})
                        # Prime both caches with a valid result at exactly the same geometry.
                        SpatialAlignmentVerifier.execute_alignment_and_recheck(focal, reference, strict_recheck=False)
                        ctrl = ClosedLoopActionController()
                        args = action() if custom else None
                        ctrl.apply_se3_prescription_and_recheck(focal, reference, mcp_arguments=args, strict_recheck=False)
                        with mock.patch.object(SpatialAnomalySniffer, 'probe_closest_clearance', return_value=invalid):
                            moved, report = SpatialAlignmentVerifier.execute_alignment_and_recheck(
                                focal, reference, strict_recheck=strict)
                            controlled, control_report, fsm = ctrl.apply_se3_prescription_and_recheck(
                                focal, reference, mcp_arguments=args, strict_recheck=strict)
                        self.assertIs(moved, focal)
                        self.assertIs(controlled, focal)
                        np.testing.assert_array_equal(controlled.vertices, focal.vertices)
                        self.assertFalse(report.verification_passed)
                        self.assertFalse(control_report.verification_passed)
                        self.assertFalse(fsm.locked_certified)
                        self.assertEqual(control_report.applied_translation_m, (0., 0., 0.))
                        self.assert_pose_matches(focal, controlled, control_report)

    def test_invalid_depth_cannot_amplify_zero_command(self):
        focal, reference = contact_pair()
        probe = SpatialAnomalySniffer.probe_closest_clearance(focal, reference)
        invalid = dataclasses.replace(probe, measurement_valid=False,
                                      signed_clearance_m=-.9, is_penetrating=True)
        ctrl = ClosedLoopActionController()
        shield = ctrl.filter_action_with_ecbf_and_jamming_shield(
            focal, reference, (0., 0., 0.), probe_result=invalid)
        np.testing.assert_array_equal(shield.safe_filtered_twist_6d, np.zeros(6))
        with mock.patch.object(SpatialAnomalySniffer, 'probe_closest_clearance', return_value=invalid):
            moved, report, fsm = ctrl.apply_se3_prescription_and_recheck(
                focal, reference, mcp_arguments=action(shield=True), enable_ecbf_shield=True)
        np.testing.assert_array_equal(moved.vertices, focal.vertices)
        self.assertFalse(report.verification_passed)
        self.assertFalse(fsm.locked_certified)

    def test_real_open_hull_intersection_is_rejected_without_motion(self):
        reference = box('#A', [2., .2, .2], np.zeros(3))
        focal = box('#B', [.2, 2., .2], np.array([0., .9, 0.]), open_hull=True)
        # Independent exact AABB intersection, not the product's collision predicate.
        extent = np.minimum(focal.vertices.max(0), reference.vertices.max(0)) - np.maximum(
            focal.vertices.min(0), reference.vertices.min(0))
        self.assertGreater(float(np.prod(extent)), 0)
        probe = SpatialAnomalySniffer.probe_closest_clearance(focal, reference)
        self.assertFalse(probe.measurement_valid)
        ctrl = ClosedLoopActionController(enable_zero_copy_ipc=True)
        moved, report, fsm = ctrl.apply_se3_prescription_and_recheck(
            focal, reference, mcp_arguments=action(shield=True), scene_meshes=[reference, focal],
            enable_ecbf_shield=True)
        self.assertIs(moved, focal)
        self.assertFalse(report.verification_passed)
        self.assertFalse(fsm.locked_certified)
        output, _ = ctrl._mcp_ipc_engine.arena.resolve_tensor_view(2)
        np.testing.assert_array_equal(output, focal.vertices)

    def test_deadband_reports_identity_and_ipc_commits_identity(self):
        for strict in (True, False):
            for ipc in (False, True):
                with self.subTest(strict=strict, ipc=ipc):
                    focal, reference = contact_pair()
                    ctrl = ClosedLoopActionController(enable_zero_copy_ipc=ipc)
                    moved, report, fsm = ctrl.apply_se3_prescription_and_recheck(
                        focal, reference, mcp_arguments=action((0., 0., .04)), strict_recheck=strict)
                    np.testing.assert_array_equal(moved.vertices, focal.vertices)
                    np.testing.assert_array_equal(report.posed_se3_4x4, np.eye(4))
                    self.assertEqual(report.applied_rotation_euler_deg, (0., 0., 0.))
                    self.assertAlmostEqual(report.commanded_rotation_euler_deg[2], .04)
                    self.assertAlmostEqual(report.filtered_rotation_euler_deg[2], .04)
                    np.testing.assert_array_equal(ctrl._inflight_rot_ring[-1], np.eye(3))
                    self.assert_pose_matches(focal, moved, report)
                    response = ctrl.build_mcp_closed_loop_response_package(report, fsm, detail_level='full')
                    self.assertEqual(response['applied_se3_action']['rotation_euler_deg_xyz'], [0., 0., 0.])
                    if ipc:
                        output, _ = ctrl._mcp_ipc_engine.arena.resolve_tensor_view(2)
                        np.testing.assert_array_equal(output, focal.vertices)

    def test_nonzero_custom_pose_reproduces_vertices_independently(self):
        focal, reference = contact_pair()
        rotation = SE3AlignmentMath.euler_xyz_to_matrix(0., 0., .2)
        translation = np.array([.002, -.001, .01])
        ctrl = ClosedLoopActionController(enable_zero_copy_ipc=True)
        moved, report, _ = ctrl.apply_se3_prescription_and_recheck(
            focal, reference, mcp_arguments=action((0., 0., .2), translation))
        center = focal.vertices.mean(axis=0)
        expected = (focal.vertices - center) @ rotation.T + center + translation
        np.testing.assert_allclose(moved.vertices, expected, atol=2e-14, rtol=0)
        self.assert_pose_matches(focal, moved, report)
        output, _ = ctrl._mcp_ipc_engine.arena.resolve_tensor_view(2)
        np.testing.assert_array_equal(output, moved.vertices)

    def test_nominal_small_angle_and_cached_pose_report_actual_identity(self):
        focal, reference = contact_pair()
        focal = focal.rotated_around_pivot(SE3AlignmentMath.euler_xyz_to_matrix(0., 0., .04))
        for strict in (True, False, False):
            with self.subTest(strict=strict):
                moved, report = SpatialAlignmentVerifier.execute_alignment_and_recheck(
                    focal, reference, strict_recheck=strict)
                np.testing.assert_array_equal(moved.vertices, focal.vertices)
                np.testing.assert_array_equal(report.posed_se3_4x4, np.eye(4))
                self.assertEqual(report.applied_rotation_euler_deg, (0., 0., 0.))
                self.assert_pose_matches(focal, moved, report)

    def test_command_filter_and_executed_translation_have_distinct_meanings(self):
        focal, reference = contact_pair()
        focal = focal.translated((0., 0., .02))
        ctrl = ClosedLoopActionController(trans_quantization_step_m=.001)
        args = action(translation=(.004, -.002, -.08), shield=True)
        args['damping_gain_alpha'] = .5
        moved, report, fsm = ctrl.apply_se3_prescription_and_recheck(
            focal, reference, mcp_arguments=args, enable_ecbf_shield=True)
        np.testing.assert_allclose(report.commanded_translation_m, [.004, -.002, -.08], atol=1e-14)
        np.testing.assert_allclose(report.filtered_translation_m, [.002, -.001, -.02], atol=1e-14)
        np.testing.assert_allclose(report.applied_translation_m, [.002, -.001, -.02], atol=1e-14)
        np.testing.assert_allclose(moved.vertices, focal.vertices + [.002, -.001, -.02], atol=1e-14)
        self.assertAlmostEqual(float(moved.vertices[:, 2].min()), .35)
        self.assert_pose_matches(focal, moved, report)
        serialized = dataclasses.asdict(report)
        for field in ('commanded_rotation_euler_deg', 'commanded_translation_m',
                      'filtered_rotation_euler_deg', 'filtered_translation_m'):
            self.assertEqual(serialized[field], getattr(report, field))
            self.assertIsNotNone(serialized[field])
        # Reports constructed by older callers leave the appended fields unset.
        legacy_report = dataclasses.replace(
            report, commanded_rotation_euler_deg=None, commanded_translation_m=None,
            filtered_rotation_euler_deg=None, filtered_translation_m=None)
        response = ctrl.build_mcp_closed_loop_response_package(legacy_report, fsm)
        applied = response['applied_se3_action']
        self.assertEqual(applied['commanded_rotation_euler_deg_xyz'], list(report.applied_rotation_euler_deg))
        self.assertEqual(applied['filtered_rotation_euler_deg_xyz'], list(report.applied_rotation_euler_deg))
        self.assertEqual(applied['commanded_translation_xyz_m'], list(report.applied_translation_m))
        self.assertEqual(applied['filtered_translation_xyz_m'], list(report.applied_translation_m))

    def test_invalid_post_probe_rolls_back_with_identity_pose_and_ipc(self):
        focal, reference = contact_pair()
        probe = SpatialAnomalySniffer.probe_closest_clearance(focal, reference)
        invalid = dataclasses.replace(probe, measurement_valid=False)
        ctrl = ClosedLoopActionController(enable_zero_copy_ipc=True)
        with mock.patch.object(SpatialAnomalySniffer, 'probe_closest_clearance',
                               side_effect=[probe, invalid]):
            moved, report, fsm = ctrl.apply_se3_prescription_and_recheck(
                focal, reference, mcp_arguments=action(translation=(0., 0., .01)))
        self.assertIs(moved, focal)
        self.assertEqual(ctrl.rollback_count, 1)
        self.assertEqual(fsm.current_state, ServoFSMState.EMERGENCY_SAFE_ROLLBACK)
        self.assertFalse(report.verification_passed)
        np.testing.assert_array_equal(report.posed_se3_4x4, np.eye(4))
        self.assertEqual(report.applied_translation_m, (0., 0., 0.))
        self.assertEqual(report.commanded_translation_m, (0., 0., .01))
        output, _ = ctrl._mcp_ipc_engine.arena.resolve_tensor_view(2)
        np.testing.assert_array_equal(output, focal.vertices)

    def test_invalid_probe_cannot_lock_fsm_or_issue_certificate(self):
        focal, reference = contact_pair()
        probe = SpatialAnomalySniffer.probe_closest_clearance(focal, reference)
        invalid = dataclasses.replace(probe, axes_valid=False)
        ctrl = ClosedLoopActionController(lock_required_consecutive_steps=1)
        self.assertTrue(ctrl.evaluate_fsm_state_transition(probe).locked_certified)
        self.assertFalse(ctrl.evaluate_fsm_state_transition(invalid).locked_certified)
        self.assertEqual(ctrl.consecutive_flush_steps, 0)
        with mock.patch.object(SpatialAnomalySniffer, 'probe_closest_clearance', return_value=invalid):
            moved, certificate = SpatialAlignmentVerifier.generate_closed_loop_digital_twin_audit_certificate(
                focal, reference)
            ctrl.fsm_state = ServoFSMState.LOCKED_CERTIFIED
            _, issued, package = ctrl.issue_mcp_closed_loop_audit_certificate(focal, reference)
        self.assertIs(moved, focal)
        self.assertFalse(certificate.overall_certified)
        self.assertFalse(certificate.recheck_passed)
        self.assertFalse(issued.overall_certified)
        self.assertNotEqual(package['fsm_terminal_state'], 'LOCKED_CERTIFIED')


if __name__ == '__main__':
    unittest.main()

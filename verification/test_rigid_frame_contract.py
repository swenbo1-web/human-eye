"""World-delta frame contracts independent of legacy face-alignment axes."""
import copy
import json
import math
import unittest

import numpy as np

from human_eye_module1_operators import MeshEntity3D, SE3AlignmentMath
from human_eye_module1_operators.submodule_1_4_spatial_sniffer import validate_local_axes
from human_eye_plugin.agent_adapters import build_agent_observation
from human_eye_plugin.auto_router import HumanEyeAutoRouter, _validated_scene
from human_eye_plugin.host_runtime import GuardedHostRuntime
from human_eye_plugin.rigid_frame import rigid_frame_status
from human_eye_plugin.task_verification import evaluate_spatial_goal
from verification.test_host_runtime import MutableHost, mesh


def prism(identity, sides, pivot, *, rotation=None, height=.03, radius=.06):
    rotation = np.eye(3) if rotation is None else np.asarray(rotation)
    vertices = np.array([[radius * math.cos(i * math.tau / sides),
                          radius * math.sin(i * math.tau / sides), z]
                         for z in (-height / 2, height / 2) for i in range(sides)])
    faces = [(0, i + 1, i) for i in range(1, sides - 1)]
    faces += [(sides, sides + i, sides + i + 1) for i in range(1, sides - 1)]
    for i in range(sides):
        next_i = (i + 1) % sides
        faces.extend(((i, next_i, next_i + sides), (i, next_i + sides, i + sides)))
    return MeshEntity3D(identity, '#' + identity, identity,
        vertices @ rotation.T + np.array(pivot), np.array(faces), None,
        (180, 100, 60), identity == 'part', local_axes=rotation.T.copy(),
        pivot_world=np.array(pivot, dtype=float)).to_dict()


def nonbox_scene(*, sides=6, both_prisms=False):
    rotation = SE3AlignmentMath.euler_xyz_to_matrix(0, 11, 23)
    if both_prisms:
        rotation = np.eye(3)
        meshes = [prism('base', sides, [0, 0, -.01], height=.02, radius=.04),
                  prism('part', sides, [0, 0, .012], height=.02, radius=.04)]
    else:
        base = MeshEntity3D.from_dict(mesh('base', [0, 0, -.02], [.42, .26, .04]))
        base = base.rotated_around_pivot(rotation, pivot=np.zeros(3)).to_dict()
        meshes = [base, prism('part', sides, rotation @ np.array([0, 0, .019]), rotation=rotation)]
    return {'revision': 'r1', 'unit': 'm', 'coordinate_frame': 'world',
            'source': 'independent_rigid_frame_fixture', 'meshes': meshes}


def observe(router, scene, *, sid='s'):
    return router.handle_event({'event': 'before_model', 'session_id': sid,
        'scene': scene, 'task_kind': 'spatial_3d', 'task_instruction': 'Measure the part clearance.',
        'focal_id': 'part', 'reference_id': 'base', 'include_image': False})


def command(observation, translation, *, sid='s'):
    return {'event': 'before_action', 'session_id': sid,
        'observation_id': observation['observation_id'], 'focal_id': 'part',
        'reference_id': 'base', 'action': {'translation': list(translation)}}


class RigidFrameValueTests(unittest.TestCase):
    def test_explicit_frame_has_no_face_normal_requirement(self):
        value = nonbox_scene()['meshes'][1]
        self.assertFalse(validate_local_axes(MeshEntity3D.from_dict(value))[0])
        status = rigid_frame_status(value)
        self.assertTrue(status['valid'], status)
        self.assertFalse(status['face_normal_alignment_required'])
        self.assertFalse(status['execution_authority'])
        self.assertEqual(status['local_axes_row_basis'], value['local_axes'])
        self.assertEqual(status['pivot_world_m'], value['pivot_world'])
        self.assertEqual(status['axes_reason'], value['axes_reason'])

    def test_returned_evidence_cannot_mutate_current_input(self):
        value = MutableHost().scene['meshes'][1]
        before = copy.deepcopy(value)
        status = rigid_frame_status(value)
        status['local_axes_row_basis'][0][0] = 99
        status['pivot_world_m'][0] = 99
        self.assertEqual(value, before)
        self.assertTrue(rigid_frame_status(value)['valid'])

    def test_missing_host_fields_cannot_become_authoritative_on_roundtrip(self):
        for field in ('local_axes', 'pivot_world', 'axes_source', 'axes_confidence', 'axes_reason'):
            with self.subTest(field=field):
                scene = MutableHost().scene
                scene['meshes'][1].pop(field)
                self.assertFalse(rigid_frame_status(scene['meshes'][1])['valid'])
                first, _, _ = _validated_scene(scene)
                second, _, _ = _validated_scene(first)
                for normalized in (first, second):
                    self.assertFalse(rigid_frame_status(normalized['meshes'][1])['valid'])
                route = observe(HumanEyeAutoRouter(quad_size=64), first)
                self.assertFalse(route['rigid_frame_valid'])
                self.assertTrue(route['requires_reobserve'])

    def test_numeric_coercion_does_not_launder_bool_or_string_axes(self):
        for axes in ([[True, 0, 0], [0, 1, 0], [0, 0, 1]],
                     [['1', '0', '0'], ['0', '1', '0'], ['0', '0', '1']]):
            with self.subTest(axes=axes):
                scene = MutableHost().scene
                scene['meshes'][1]['local_axes'] = axes
                self.assertFalse(rigid_frame_status(scene['meshes'][1])['valid'])
                normalized, _, _ = _validated_scene(scene)
                self.assertFalse(rigid_frame_status(normalized['meshes'][1])['valid'])
                self.assertEqual(normalized['meshes'][1]['axes_confidence'], 'ambiguous')

    def test_bad_bases_are_rejected_without_repair(self):
        matrices = (np.diag([2., 1, 1]), np.diag([-1., 1, 1]), np.zeros((3, 3)),
                    np.array([[1., .01, 0], [0, 1, 0], [0, 0, 1]]),
                    np.array([[math.nan, 0, 0], [0, 1, 0], [0, 0, 1]]),
                    np.array([[math.inf, 0, 0], [0, 1, 0], [0, 0, 1]]))
        for axes in matrices:
            with self.subTest(axes=axes):
                value = MutableHost().scene['meshes'][1]
                value['local_axes'] = axes.tolist()
                before = copy.deepcopy(value)
                status = rigid_frame_status(value)
                self.assertFalse(status['valid'])
                json.dumps(status, allow_nan=False)
                np.testing.assert_array_equal(value['local_axes'], before['local_axes'])

    def test_pivot_must_be_explicit_finite_numeric_vector(self):
        for pivot in (None, [0, 0], [False, 0, 0], ['0', 0, 0], [math.nan, 0, 0]):
            with self.subTest(pivot=pivot):
                value = MutableHost().scene['meshes'][1]
                value['pivot_world'] = pivot
                self.assertFalse(rigid_frame_status(value)['valid'])

    def test_inferred_or_ambiguous_sources_stay_observation_only(self):
        for source, confidence in (('inferred_surface', 'geometry'),
                                   ('ambiguous_geometry', 'ambiguous'),
                                   ('unverified_imported_frame', 'explicit')):
            with self.subTest(source=source):
                scene = MutableHost().scene
                scene['meshes'][1].update(axes_source=source, axes_confidence=confidence)
                route = observe(HumanEyeAutoRouter(quad_size=64), scene)
                self.assertEqual(route['route'], 'engine')
                self.assertFalse(route['rigid_frame_valid'])
                self.assertTrue(route['requires_reobserve'])
                self.assertIn('rigid_frame_unverified', route['reason_codes'])


class RigidFrameRouterTests(unittest.TestCase):
    def test_nonbox_observation_retains_legacy_and_separate_rigid_evidence(self):
        router = HumanEyeAutoRouter(quad_size=64, clock=lambda: 1000.)
        scene = nonbox_scene()
        first = observe(router, scene)
        second = observe(router, scene)
        for route in (first, second):
            self.assertEqual(route['route'], 'engine', route)
            self.assertTrue(route['measurement_valid'])
            self.assertFalse(route['axes_valid'])
            self.assertTrue(route['rigid_frame_valid'])
            self.assertFalse(route['requires_reobserve'])
            facts = json.loads(route['context_text'])
            self.assertFalse(facts['measurement']['axes_valid'])
            self.assertIn('not_parallel_to_any_face', facts['measurement']['axes_check'])
            self.assertFalse(facts['measurement']['control_frame_trustworthy'])
            self.assertTrue(facts['measurement']['rigid_frame_valid'])
        self.assertTrue(second['cache_hit'])
        self.assertEqual(first['observation_id'], second['observation_id'])

    def test_adapter_delivers_both_contracts_without_equating_them(self):
        route = observe(HumanEyeAutoRouter(quad_size=64), nonbox_scene())
        prepared = build_agent_observation(route, format='mcp')
        data = json.loads(prepared['content'][0]['text'])
        self.assertFalse(data['routing']['axes_valid'])
        self.assertTrue(data['routing']['rigid_frame_valid'])
        self.assertFalse(data['routing']['rigid_frame']['execution_authority'])

    def test_nonbox_fresh_action_uses_rigid_frame_and_full_geometry_gate(self):
        router = HumanEyeAutoRouter(quad_size=64)
        route = observe(router, nonbox_scene())
        normal = SE3AlignmentMath.euler_xyz_to_matrix(0, 11, 23)[:, 2]
        accepted = router.handle_event(command(route, normal * -.002))
        self.assertTrue(accepted['allow_action'], accepted)
        self.assertTrue(accepted['rigid_frame_valid'])
        self.assertFalse(accepted['axes_valid'])

    def test_nonbox_penetrating_candidate_is_still_refused(self):
        router = HumanEyeAutoRouter(quad_size=64)
        route = observe(router, nonbox_scene())
        normal = SE3AlignmentMath.euler_xyz_to_matrix(0, 11, 23)[:, 2]
        refused = router.handle_event(command(route, normal * -.005))
        self.assertFalse(refused['allow_action'])
        self.assertEqual(refused['reason_codes'], ['candidate_collision'])

    def test_partial_scene_remains_unactionable_with_valid_pair_frames(self):
        scene = nonbox_scene()
        third = mesh('obstacle', [2, 0, 0], [.1, .1, .1])
        third['faces'] = third['faces'][:-2]
        scene['meshes'].append(third)
        router = HumanEyeAutoRouter(quad_size=64)
        route = observe(router, scene)
        self.assertTrue(route['rigid_frame_valid'])
        self.assertEqual(route['observation_status'], 'partial')
        self.assertIsNone(route['observation_id'])
        self.assertFalse(router.handle_event(command(route, [0, 0, .1]))['allow_action'])

    def test_old_observation_contract_is_invalidated_without_clearing_pending(self):
        router = HumanEyeAutoRouter(quad_size=64)
        route = observe(router, nonbox_scene())
        router.handle_event(command(route, [0, 0, .001]))
        state = router.export_state()
        state['sessions'][0][1]['observation']['contract_revision'] = 'old_contract'
        pending = copy.deepcopy(state['sessions'][0][1]['pending'])
        restored = HumanEyeAutoRouter(quad_size=64)
        restored.import_state(state)
        actual = restored.export_state()['sessions'][0][1]
        self.assertIsNone(actual['observation'])
        self.assertEqual(actual['pending'], pending)
        self.assertFalse(restored.handle_event(command(route, [0, 0, .001]))['allow_action'])


class RigidFrameHostTests(unittest.TestCase):
    def prepare(self, host, *, production=False):
        runtime = GuardedHostRuntime(host, quad_size=64, require_execution_capability=production)
        prepared = runtime.before_model(session_id='s', task_instruction='Measure the part gap.',
            focal_id='part', reference_id='base', messages=[], include_image=False)
        return runtime, prepared

    def test_hex_rigid_move_readback_verified_despite_legacy_alignment_rejection(self):
        host = MutableHost(); host.scene = nonbox_scene()
        runtime, prepared = self.prepare(host)
        normal = SE3AlignmentMath.euler_xyz_to_matrix(0, 11, 23)[:, 2]
        result = runtime.execute_action(session_id='s', action={'translation': (normal * -.002).tolist()},
            goal={'target_clearance_m': .002, 'clearance_tolerance_m': 2e-6})
        self.assertTrue(prepared['routing']['rigid_frame_valid'])
        self.assertEqual(result['status'], 'verified', result)
        self.assertTrue(result['task_succeeded'])
        self.assertFalse(result['routing']['axes_valid'])
        self.assertTrue(result['routing']['rigid_frame_valid'])
        self.assertFalse(runtime.status['quarantined'])
        self.assertEqual(host.calls, 1)
        base, focal = host.scene['meshes']
        gap = min(np.array(focal['vertices']) @ normal) - max(np.array(base['vertices']) @ normal)
        self.assertAlmostEqual(gap, .002, places=12)

    def test_fifteen_side_budget_control_moves_one_mm_and_verifies(self):
        host = MutableHost(); host.scene = nonbox_scene(sides=15, both_prisms=True)
        runtime, prepared = self.prepare(host)
        self.assertFalse(prepared['routing']['axes_valid'])
        result = runtime.execute_action(session_id='s', action={'translation': [0, 0, -.001]},
            goal={'target_clearance_m': .001, 'clearance_tolerance_m': 2e-6})
        self.assertEqual(result['status'], 'verified', result)
        self.assertTrue(result['task_succeeded'])
        self.assertEqual(host.calls, 1)

    def test_bad_frame_at_preparation_retains_reason_without_calling_host_mutator(self):
        host = MutableHost(); host.scene = nonbox_scene()
        host.scene['meshes'][1].pop('pivot_world')
        runtime = GuardedHostRuntime(host, quad_size=64)
        result = runtime._prepare_and_preview(session_id='s',
            action={'focal_id': 'part', 'reference_id': 'base', 'translation': [0, 0, .001]})
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(result['allow_action'])
        self.assertIn('unverified_geometry_or_frame', result['reason_codes'])
        self.assertFalse(result['routing']['rigid_frame_valid'])
        self.assertEqual(host.calls, 0)

    def test_changed_provenance_and_missing_capability_cannot_reuse_session(self):
        for change in ('source', 'capability'):
            with self.subTest(change=change):
                host = MutableHost(); host.scene = nonbox_scene()
                runtime, _ = self.prepare(host, production=change == 'capability')
                if change == 'source':
                    host.scene['meshes'][1]['axes_source'] = 'unverified_imported_frame'
                result = runtime.execute_action(session_id='s', action={'translation': [0, 0, .01]})
                self.assertFalse(result['verified'])
                self.assertEqual(host.calls, 0)

    def test_explicit_rigid_frame_does_not_certify_legacy_angular_goal(self):
        scene = nonbox_scene()
        result = evaluate_spatial_goal(scene, {'focal_id': 'part', 'reference_id': 'base',
            'max_tangent_yaw_mismatch_deg': 1.0})
        self.assertFalse(result['task_succeeded'])
        self.assertIn('angular_measurement_invalid', result['reason_codes'])


if __name__ == '__main__':
    unittest.main()

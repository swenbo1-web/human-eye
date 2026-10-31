"""Actual alignment/gaze memoization must describe the current supplied scene.

Only new in-memory meshes are used. Cold calls after clearing scene caches are
the oracle; geometry functions and camera predicates are never replaced.
"""
from __future__ import annotations

import copy
import dataclasses
import unittest

import numpy as np

from human_eye_foveated_renderer import MeshEntity3D
from human_eye_module1_operators.submodule_1_2_sub_frustum_gaze import SubFrustumMathEngine
from human_eye_module1_operators.submodule_1_5_alignment_verifier import SpatialAlignmentVerifier

VERIFIER = SpatialAlignmentVerifier
GAZE = SubFrustumMathEngine
SIGNS = np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
                  [-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]], dtype=float)
FACES = np.array([[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
                  [2,3,7],[2,7,6],[1,2,6],[1,6,5],[3,0,4],[3,4,7]], dtype=np.int32)


def box(name, center, size):
    return MeshEntity3D(name, '#'+name, name,
        SIGNS*np.asarray(size, dtype=float)/2 + np.asarray(center, dtype=float),
        FACES.copy(), None, (70,140,210), local_axes=np.eye(3))


def fixture():
    focal = box('part', [0,0,.35], [.15,.1,.1])
    reference = box('base', [0,0,.1], [.5,.5,.2])
    background = box('background', [5,5,5], [.2,.2,.2])
    return focal, reference, background, np.array([.4,-.6,.5])


def prewarm_fixture():
    # Seed521/index3 was reduced to one deterministic, successful alignment.
    focal = box('part', [.0847617804044214,-.05807198590450957,.6630056052127864],
                [.0478460180223131,.12069648003970203,.16563491713749162])
    reference = box('base', [0,0,.1], [.8,.8,.2])
    eye = np.array([-.5124522465760114,.5104549334712387,.44831127110916036])
    return focal, reference, eye


def clear_caches():
    VERIFIER._RECHECK_CACHE.clear()
    GAZE._GAZE_CACHE.clear()


def normalized(value):
    if dataclasses.is_dataclass(value):
        value = dataclasses.asdict(value)
    if isinstance(value, dict):
        # Computation timings and their human-readable summary are not scene
        # geometry, action, verification or camera facts.
        return {key:normalized(child) for key,child in value.items()
                if key not in {'compute_time_ms','summary_message'}}
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (tuple,list)):
        return [normalized(child) for child in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def execute(focal, reference, scene, eye, **kwargs):
    return VERIFIER.execute_alignment_and_recheck(focal, reference,
        cam_eye=eye, scene_meshes=scene, strict_recheck=False, **kwargs)


class AlignmentSceneCacheTests(unittest.TestCase):
    def setUp(self):
        clear_caches()

    def tearDown(self):
        clear_caches()

    def assert_cold_equal(self, warmed, focal, reference, scene, eye, **kwargs):
        clear_caches()
        fresh = execute(focal, reference, scene, eye, **kwargs)
        np.testing.assert_array_equal(warmed[0].vertices, fresh[0].vertices)
        np.testing.assert_array_equal(warmed[0].local_axes, fresh[0].local_axes)
        self.assertEqual(normalized(warmed[1]), normalized(fresh[1]))
        return fresh

    def test_unchanged_scene_retains_actual_recheck_hit(self):
        f,r,b,eye = fixture();scene=[f,r,b]
        first = execute(f,r,scene,eye)
        again = execute(f,r,scene,eye)
        self.assertIs(again[0],first[0])
        self.assertIs(again[1],first[1])
        self.assertTrue(again[1].verification_passed)

    def test_background_movement_changes_real_camera_decision_like_cold_call(self):
        f,r,b,eye = fixture();scene=[f,r,b]
        first = execute(f,r,scene,eye)
        self.assertFalse(first[1].camera_auto_orbited)
        b.vertices += [-4.8,-5.3,-4.65]
        warmed = execute(f,r,scene,eye)
        fresh = self.assert_cold_equal(warmed,f,r,scene,eye)
        self.assertTrue(fresh[1].camera_auto_orbited)
        self.assertIsNot(warmed[1],first[1])

    def test_background_guard_is_refreshed_before_recheck_hit(self):
        f,r,b,eye = fixture();scene=[f,r,b]
        first = execute(f,r,scene,eye);old_token=b._last_crc_token
        b.vertices[0,2] += .125
        warmed = execute(f,r,scene,eye)
        self.assertNotEqual(b._last_crc_token,old_token)
        self.assertIsNot(warmed[1],first[1])
        self.assert_cold_equal(warmed,f,r,scene,eye)

    def test_same_shape_background_topology_edit_cannot_reuse_report(self):
        f,r,b,eye = fixture();scene=[f,r,b]
        first = execute(f,r,scene,eye);old_token=b._last_crc_token
        b.faces[[0,1]] = b.faces[[1,0]]
        warmed = execute(f,r,scene,eye)
        self.assertNotEqual(b._last_crc_token,old_token)
        self.assertIsNot(warmed[1],first[1])
        self.assert_cold_equal(warmed,f,r,scene,eye)

    def test_background_axis_edit_cannot_reuse_report(self):
        f,r,b,eye = fixture();scene=[f,r,b]
        first = execute(f,r,scene,eye);old_token=b._last_crc_token
        angle=.1;c,s=np.cos(angle),np.sin(angle)
        b.local_axes[:]=[[c,s,0],[-s,c,0],[0,0,1]]
        warmed = execute(f,r,scene,eye)
        self.assertNotEqual(b._last_crc_token,old_token)
        self.assertIsNot(warmed[1],first[1])
        self.assert_cold_equal(warmed,f,r,scene,eye)

    def test_replacement_with_same_object_id_is_a_fresh_scene(self):
        f,r,b,eye = fixture();scene=[f,r,b]
        first = execute(f,r,scene,eye)
        replacement=box(b.object_id,[.2,-.3,.35],[.2,.2,.2])
        replacement._compute_full_crc_token()
        scene[2]=replacement
        warmed=execute(f,r,scene,eye)
        self.assertIsNot(warmed[1],first[1])
        self.assert_cold_equal(warmed,f,r,scene,eye)

    def test_scene_tail_after_32_objects_is_not_omitted(self):
        f,r,b,eye = fixture()
        scene=[f,r]+[box('far'+str(i),[8+i,8,8],[.1,.1,.1]) for i in range(34)]+[b]
        first=execute(f,r,scene,eye)
        b.vertices += [-4.8,-5.3,-4.65]
        warmed=execute(f,r,scene,eye)
        self.assertIsNot(warmed[1],first[1])
        self.assert_cold_equal(warmed,f,r,scene,eye)

    def test_scene_reorder_and_removal_do_not_hit_prior_context(self):
        f,r,b,eye=fixture();scene=[f,r,b]
        first=execute(f,r,scene,eye)
        for changed in ([b,r,f],[f,r]):
            with self.subTest(count=len(changed)):
                warmed=execute(f,r,changed,eye)
                self.assertIsNot(warmed[1],first[1])
                self.assert_cold_equal(warmed,f,r,changed,eye)

    def test_explicit_background_invalidation_changes_cache_generation(self):
        f,r,b,eye=fixture();scene=[f,r,b]
        first=execute(f,r,scene,eye)
        b.invalidate_caches()
        warmed=execute(f,r,scene,eye)
        self.assertIsNot(warmed[1],first[1])
        self.assert_cold_equal(warmed,f,r,scene,eye)

    def test_post_action_report_uses_actual_transformed_occlusion(self):
        f,r,eye=prewarm_fixture();scene=[f,r]
        aligned,report=execute(f,r,scene,eye)
        self.assertTrue(report.verification_passed)
        roi=(report.post_probe.point_a_world+report.post_probe.point_b_world)*.5
        GAZE._GAZE_CACHE.clear()
        fresh_eye,fresh_orbit=GAZE.resolve_unoccluded_camera_eye(eye,roi,[aligned,r])
        self.assertTrue(fresh_orbit)
        self.assertEqual(report.camera_auto_orbited,fresh_orbit)

    def test_post_action_prewarm_matches_cold_actual_scene(self):
        f,r,eye=prewarm_fixture()
        aligned,report=execute(f,r,[f,r],eye)
        roi=(report.post_probe.point_a_world+report.post_probe.point_b_world)*.5
        warmed=GAZE.resolve_unoccluded_camera_eye(eye,roi,[aligned,r])
        GAZE._GAZE_CACHE.clear()
        fresh=GAZE.resolve_unoccluded_camera_eye(eye,roi,[aligned,r])
        np.testing.assert_array_equal(warmed[0],fresh[0])
        self.assertEqual(warmed[1],fresh[1])

    def test_original_scene_meshes_and_list_are_not_modified(self):
        f,r,b,eye=fixture();scene=[f,r,b]
        items=list(scene);snapshots=[mesh.vertices.copy() for mesh in scene]
        execute(f,r,scene,eye)
        self.assertEqual([id(m) for m in scene],[id(m) for m in items])
        for mesh,before in zip(scene,snapshots):np.testing.assert_array_equal(mesh.vertices,before)

    def test_same_id_distinct_occluder_is_preserved_in_post_action_scene(self):
        f,r,eye=prewarm_fixture()
        duplicate=box(f.object_id,[-.16,.29,.32],[.2,.2,.2])
        scene=[f,r,duplicate]
        aligned,report=execute(f,r,scene,eye)
        roi=(report.post_probe.point_a_world+report.post_probe.point_b_world)*.5
        warmed=GAZE.resolve_unoccluded_camera_eye(eye,roi,[aligned,r,duplicate])
        GAZE._GAZE_CACHE.clear()
        fresh=GAZE.resolve_unoccluded_camera_eye(eye,roi,[aligned,r,duplicate])
        np.testing.assert_array_equal(warmed[0],fresh[0])
        self.assertEqual(warmed[1],fresh[1])
        self.assertEqual(report.camera_auto_orbited,fresh[1])

    def test_subrounded_translation_request_is_not_conflated(self):
        f,r,b,eye=fixture();scene=[f,r,b]
        first=execute(f,r,scene,eye,custom_translation=(0.,0.,-.1))
        requested=(0.,0.,-.1+1e-8)
        warmed=execute(f,r,scene,eye,custom_translation=requested)
        self.assertEqual(tuple(warmed[1].applied_translation_m),requested)
        self.assertIsNot(warmed[1],first[1])
        self.assert_cold_equal(warmed,f,r,scene,eye,custom_translation=requested)

    def test_subrounded_preferred_direction_has_distinct_context(self):
        f,r,b,eye=fixture();scene=[f,r,b]
        first=execute(f,r,scene,eye,preferred_view_dir=np.array([0.,1.,0.]))
        direction=np.array([1e-8,1.,0.])
        warmed=execute(f,r,scene,eye,preferred_view_dir=direction)
        self.assertIsNot(warmed[1],first[1])
        self.assert_cold_equal(warmed,f,r,scene,eye,preferred_view_dir=direction)

    def test_subrounded_camera_request_has_distinct_context(self):
        f,r,b,eye=fixture();scene=[f,r,b]
        first=execute(f,r,scene,eye)
        changed=eye.copy();changed[0]+=1e-8
        warmed=execute(f,r,scene,changed)
        self.assertIsNot(warmed[1],first[1])
        self.assert_cold_equal(warmed,f,r,scene,changed)

    def test_gaze_close_camera_requests_equal_their_own_cold_results(self):
        _,r,_,eye=fixture();focus=np.array([0.,0.,.2])
        first=GAZE.resolve_unoccluded_camera_eye(eye,focus,[r])
        changed=eye.copy();changed[0]+=1e-8
        warmed=GAZE.resolve_unoccluded_camera_eye(changed,focus,[r])
        GAZE._GAZE_CACHE.clear()
        fresh=GAZE.resolve_unoccluded_camera_eye(changed,focus,[r])
        np.testing.assert_array_equal(warmed[0],fresh[0])
        self.assertEqual(warmed[1],fresh[1])


if __name__=='__main__':unittest.main()

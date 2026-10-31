"""Valid pair observations survive unrelated unknown geometry without authority."""
import base64
import io
import json
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin.auto_router import HumanEyeAutoRouter
from human_eye_plugin.geometry_safety import measure_pair_geometry
from human_eye_plugin.scene_rendering import _render_scene_canvas_prepared
from human_eye_plugin.spatial_index import SpatialSceneIndex
from verification.test_auto_router import action, box, observation, scene


def open_plane(identity='open', center=(5., 0., .3)):
    vertices = np.array([[-.1, -.1, 0.], [.1, -.1, 0.], [.1, .1, 0.], [-.1, .1, 0.]])
    return MeshEntity3D(identity, '#' + identity, identity, vertices + center,
        np.array([[0, 1, 2], [0, 2, 3]]), None, (180, 110, 70), False,
        local_axes=np.eye(3), pivot_world=np.asarray(center)).to_dict()


def concave_prism(identity='concave'):
    # A sheared connected L extrusion remains outside exact world-axis solids.
    polygon = np.array([[0., 0.], [2., 0.], [2., 1.], [1., 1.], [1., 2.], [0., 2.]])
    vertices = np.vstack((np.c_[polygon, np.zeros(6)], np.c_[polygon, np.ones(6)])) + [5., 5., 5.]
    vertices[:, 0] += .125 * vertices[:, 2]
    top = np.array([[0, 1, 3], [1, 2, 3], [0, 3, 5], [3, 4, 5]])
    faces = top[:, ::-1].tolist() + (top + 6).tolist()
    for start in range(6):
        end = (start + 1) % 6
        faces.extend([[start, end, end + 6], [start, end + 6, start + 6]])
    return MeshEntity3D(identity, '#' + identity, identity, vertices, np.array(faces),
        None, (90, 160, 120), False, local_axes=np.eye(3),
        pivot_world=vertices.mean(axis=0)).to_dict()


def partial_scene(*extras):
    value = scene()
    value['meshes'].extend(extras or [open_plane()])
    return value


def facts(result):
    return json.loads(result['context_text'])


class PartialObservationTests(unittest.TestCase):
    def setUp(self):
        self.router = HumanEyeAutoRouter(quad_size=64)

    def observe(self, **changes):
        return self.router.handle_event(observation(**changes))

    def assert_readonly_partial(self, result, expected_unknown):
        self.assertEqual(result['route'], 'engine', result)
        self.assertEqual(result['observation_status'], 'partial')
        self.assertTrue(result['measurement_valid'])
        self.assertIsNone(result['observation_id'])
        self.assertIs(result['allow_action'], False)
        self.assertTrue(result['requires_reobserve'])
        context = facts(result)
        self.assertEqual(context['observation_status'], 'partial')
        assessment = result['scene_assessment']
        self.assertEqual(assessment, context['scene_assessment'])
        self.assertEqual(assessment['status'], 'unknown')
        self.assertEqual(assessment['scope'], 'all_scene_objects')
        self.assertEqual(set(assessment['unknown_object_ids']), set(expected_unknown))
        self.assertEqual({item['object_id'] for item in context['unknown_objects']}, set(expected_unknown))
        self.assertTrue(all(item['reason_codes'] for item in context['unknown_objects']))
        self.assertAlmostEqual(context['measurement']['signed_clearance_m'], .1)
        json.dumps(result, allow_nan=False)
        return context

    def test_complete_observation_does_not_claim_whole_scene_clear_or_allow_action(self):
        result = self.observe(include_image=False)
        self.assertEqual(result['observation_status'], 'complete')
        self.assertIsNone(result['allow_action'])
        self.assertIsInstance(result['observation_id'], str)
        assessment = result['scene_assessment']
        self.assertEqual(assessment['status'], 'not_evaluated')
        self.assertEqual(assessment['geometry_support'], 'supported')
        self.assertEqual(assessment['unknown_object_ids'], [])
        self.assertEqual(assessment, facts(result)['scene_assessment'])

    def test_open_near_far_and_connected_concave_preserve_pair_and_real_png(self):
        for extra in (open_plane(), open_plane(center=(.2, 0., .35)), concave_prism()):
            with self.subTest(extra=extra['object_id'], center=extra['pivot_world']):
                value = partial_scene(extra)
                with patch('human_eye_plugin.auto_router._render_scene_canvas_prepared', wraps=_render_scene_canvas_prepared) as rendered:
                    result = self.observe(scene=value)
                context = self.assert_readonly_partial(result, [extra['object_id']])
                self.assertEqual(len(context['scene_contacts']), 2)
                self.assertEqual({mesh.object_id for mesh in rendered.call_args.args[0]},
                                 {item['object_id'] for item in value['meshes']})
                with Image.open(io.BytesIO(base64.b64decode(result['image']['data'], validate=True))) as image:
                    self.assertEqual(image.format, 'PNG')
                    self.assertEqual(image.size, (128, 128))

    def test_every_unknown_and_known_obstacle_is_reported_without_fabricated_witness(self):
        value = partial_scene(open_plane('open-a'), open_plane('open-b', (0., 0., .3)),
                              concave_prism(), box('known-far', [9., 0., 0.], [.2, .2, .2]))
        with patch('human_eye_plugin.auto_router.measure_pair_geometry', wraps=measure_pair_geometry) as kernel:
            result = self.observe(scene=value, include_image=False)
        context = self.assert_readonly_partial(result, ['open-a', 'open-b', 'concave'])
        self.assertEqual(kernel.call_count, 1)
        self.assertEqual({row['object_id'] for row in context['scene_contacts']},
                         {'base', 'open-a', 'open-b', 'concave', 'known-far'})
        for row in context['scene_contacts']:
            if row['object_id'] not in {'open-a', 'open-b', 'concave'}:
                continue
            self.assertFalse(row['measurement_valid'])
            self.assertFalse(row['collision_assessment_valid'])
            self.assertFalse(row['clearance_exact'])
            self.assertIsNone(row['signed_clearance_m'])
            self.assertIsNone(row['is_penetrating'])
            self.assertIsNone(row['point_a_world'])
            self.assertIsNone(row['point_b_world'])
            self.assertTrue(row['reason_codes'])
        index = SpatialSceneIndex([MeshEntity3D.from_dict(item) for item in value['meshes']])
        plan = index.query(MeshEntity3D.from_dict(value['meshes'][1]), force_ids=['base'])
        self.assertFalse(index.supported)
        self.assertFalse(plan['supported'])
        self.assertTrue({'open-a', 'open-b', 'concave'}.issubset(plan['candidate_ids']))

    def test_warm_partial_cache_preserves_png_unknown_scope_and_no_authority(self):
        value = partial_scene()
        first = self.observe(scene=value)
        first_png = first['image']['data']
        first['scene_assessment']['unknown_object_ids'].clear()
        first['image']['data'] = 'caller mutation'
        with patch('human_eye_plugin.auto_router._render_scene_canvas_prepared', side_effect=AssertionError('cache missed')), \
                patch('human_eye_plugin.auto_router.measure_pair_geometry', side_effect=AssertionError('cache missed')):
            second = self.observe(scene=value)
        self.assertTrue(second['cache_hit'])
        self.assertEqual(second['image']['data'], first_png)
        self.assert_readonly_partial(second, ['open'])
        checked = self.router.handle_event(action(second))
        self.assertFalse(checked['allow_action'])
        self.assertEqual(checked['reason_codes'], ['partial_observation_not_actionable'])

    def test_partial_new_task_reuses_only_valid_pair_memo_not_unknown_results(self):
        value = partial_scene()
        self.observe(scene=value, include_image=False)
        with patch('human_eye_plugin.auto_router.measure_pair_geometry', side_effect=AssertionError('pair cache missed')):
            second = self.observe(scene=value, include_image=False, task_instruction='Measure again.')
        context = self.assert_readonly_partial(second, ['open'])
        self.assertFalse(second['cache_hit'])
        self.assertEqual(context['measurement_cache']['hits'], 1)
        self.assertEqual(context['measurement_cache']['misses'], 0)

    def test_partial_roundtrip_and_forged_or_omitted_tokens_cannot_drive_action(self):
        result = self.observe(scene=partial_scene(), include_image=False)
        restored = HumanEyeAutoRouter(quad_size=64)
        restored.import_state(self.router.export_state())
        for token in (None, '', 'forged'):
            with self.subTest(token=token), patch('human_eye_plugin.auto_router.measure_pair_geometry',
                                                 side_effect=AssertionError('partial entered execution')):
                request = action(result, observation_id=token, task_kind='general')
                checked = restored.handle_event(request)
                self.assertFalse(checked['allow_action'])
                self.assertEqual(checked['reason_codes'], ['partial_observation_not_actionable'])

    def test_old_complete_token_is_invalidated_when_unknown_mesh_is_added(self):
        complete = self.observe(include_image=False)
        self.assertTrue(complete['observation_id'])
        partial = self.observe(scene=partial_scene(), include_image=False)
        self.assert_readonly_partial(partial, ['open'])
        result = self.router.handle_event(action(complete))
        self.assertFalse(result['allow_action'])
        self.assertEqual(result['reason_codes'], ['partial_observation_not_actionable'])

    def test_same_revision_removing_unknown_object_restores_complete_fresh_observation(self):
        self.observe(scene=partial_scene(), include_image=False)
        result = self.observe(scene=scene(), include_image=False)
        self.assertEqual(result['observation_status'], 'complete')
        self.assertFalse(result['cache_hit'])
        self.assertEqual(facts(result)['unknown_objects'], [])
        self.assertTrue(self.router.handle_event(action(result))['allow_action'])

    def test_after_action_unknown_geometry_is_still_rejected_by_full_scene_gate(self):
        observed = self.observe(include_image=False)
        self.assertTrue(self.router.handle_event(action(observed))['allow_action'])
        pending = dict(self.router.export_state()['sessions'])['a']['pending']
        actual = partial_scene()
        actual['revision'] = 'r2'
        actual['meshes'][1] = pending['candidate']
        result = self.router.handle_event(observation(scene=actual, event='after_action', include_image=False))
        self.assertEqual(result['route'], 'blocked')
        self.assertEqual(result['reason_codes'], ['host_geometry_unknown'])
        self.assertFalse(result['allow_action'])

    def test_unavailable_focal_or_reference_does_not_become_partial_success(self):
        for identity, position in (('base', 0), ('part', 1)):
            with self.subTest(identity=identity):
                value = partial_scene()
                bad = open_plane(identity)
                bad['is_focal_target'] = identity == 'part'
                value['meshes'][position] = bad
                result = self.observe(scene=value, include_image=False)
                self.assertEqual(result['route'], 'blocked')
                self.assertEqual(result['reason_codes'], ['reference_pair_geometry_unknown'])
                self.assertIsNone(result['observation_id'])

    def test_global_work_budget_cannot_be_bypassed_by_marking_large_unknown_partial(self):
        large = open_plane('large')
        large['vertices'] = [[0., 0., 0.]] * 1001
        large['faces'] = [[0, 1, 2]] * 1001
        large['edges'] = None
        with patch('human_eye_plugin.auto_router.SpatialSceneIndex', side_effect=AssertionError('resource bypass')):
            result = self.observe(scene=partial_scene(large), include_image=False)
        self.assertEqual(result['route'], 'blocked')
        self.assertEqual(result['reason_codes'], ['geometry_resource_limit'])

    def test_nonfinite_unrelated_input_is_invalid_not_partial_and_retires_old_token(self):
        for value in (float('nan'), float('inf'), -float('inf')):
            with self.subTest(value=value):
                complete = self.observe(include_image=False)
                altered = partial_scene()
                altered['meshes'][-1]['vertices'][0][0] = value
                result = self.observe(scene=altered, include_image=False)
                self.assertEqual(result['route'], 'blocked')
                self.assertEqual(result['reason_codes'], ['invalid_scene'])
                self.assertFalse(self.router.handle_event(action(complete))['allow_action'])

    def test_partial_render_resource_failure_is_explicit_and_never_fabricates_png(self):
        with patch('human_eye_plugin.auto_router._render_scene_canvas_prepared', side_effect=ValueError('render budget')):
            result = self.observe(scene=partial_scene())
        context = self.assert_readonly_partial(result, ['open'])
        self.assertIsNone(result['image'])
        self.assertEqual(context['canvas']['omitted'], 'rendering_resource_or_numeric_limit')

    def test_known_support_but_unknown_extra_measurement_is_reported_partial(self):
        value = scene()
        value['meshes'].append(box('near', [.3, 0., .35], [.2, .2, .2]))
        def measured(focal, other, **options):
            if other.object_id == 'near':
                return {'measurement_valid': False, 'signed_clearance_m': None,
                        'is_penetrating': None, 'reason': 'geometry_evaluation_failed'}
            return measure_pair_geometry(focal, other, **options)
        with patch('human_eye_plugin.auto_router.measure_pair_geometry', side_effect=measured):
            result = self.observe(scene=value, include_image=False)
        context = self.assert_readonly_partial(result, ['near'])
        self.assertEqual(result['scene_assessment']['geometry_support'], 'supported')
        self.assertIn('scene_pair_measurement_unknown', result['scene_assessment']['reason_codes'])
        self.assertEqual(context['unknown_objects'][0]['reason_codes'], ['geometry_evaluation_failed'])

    def test_invalid_reference_measurement_is_unavailable_even_with_other_readable_objects(self):
        def measured(focal, other, **options):
            return {'measurement_valid': False, 'signed_clearance_m': None,
                    'is_penetrating': None, 'reason': 'geometry_evaluation_failed'}
        with patch('human_eye_plugin.auto_router.measure_pair_geometry', side_effect=measured):
            result = self.observe(scene=partial_scene(), include_image=False)
        self.assertEqual(result['route'], 'blocked')
        self.assertEqual(result['reason_codes'], ['reference_pair_measurement_unknown'])
        self.assertIsNone(result['observation_id'])

    def test_extra_measurement_resource_rejection_is_not_hidden_as_partial(self):
        value = scene()
        value['meshes'].append(box('near', [.3, 0., .35], [.2, .2, .2]))
        def measured(focal, other, **options):
            if other.object_id == 'near':
                return {'measurement_valid': False, 'signed_clearance_m': None,
                        'is_penetrating': None, 'reason': 'geometry_resource_limit'}
            return measure_pair_geometry(focal, other, **options)
        with patch('human_eye_plugin.auto_router.measure_pair_geometry', side_effect=measured):
            result = self.observe(scene=value, include_image=False)
        self.assertEqual(result['route'], 'blocked')
        self.assertEqual(result['reason_codes'], ['geometry_resource_limit'])
        self.assertFalse(result['allow_action'])
        self.assertIsNone(result['observation_id'])

    def test_old_partial_assessment_without_status_still_cannot_drive_action(self):
        self.observe(scene=partial_scene(), include_image=False)
        state = self.router.export_state()
        saved = dict(state['sessions'])['a']['observation']['result']
        saved.pop('observation_status')
        saved['observation_id'] = 'old-partial-id'
        restored = HumanEyeAutoRouter(quad_size=64)
        restored.import_state(state)
        checked = restored.handle_event(action({'observation_id': 'old-partial-id'}))
        self.assertEqual(checked['reason_codes'], ['partial_observation_not_actionable'])
        self.assertFalse(checked['allow_action'])


if __name__ == '__main__':
    unittest.main()

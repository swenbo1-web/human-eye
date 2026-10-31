"""Content-based observation reuse preserves independent complete write gates."""
import copy
import json
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin import scene_cache as history_module
from human_eye_plugin.auto_router import HumanEyeAutoRouter, _validated_scene
from human_eye_plugin.geometry_safety import solid_support_status
from human_eye_plugin.scene_cache import SpatialSceneCache
from human_eye_plugin.spatial_index import SpatialSceneIndex
from verification.test_auto_router import action, box, observation, scene


def sparse_scene(count=100):
    value = scene()
    value['meshes'].extend(box('far' + str(i), [10 + 2 * i, 0, .35], [.2, .3, .1])
                           for i in range(count - 2))
    return value


class NormalizedOperationReuseTests(unittest.TestCase):
    def test_100_mesh_warm_observation_builds_current_meshes_once_and_covers_all(self):
        router = HumanEyeAutoRouter(quad_size=64, clock=lambda: 1000)
        event = observation(scene=sparse_scene(), include_image=False)
        first = router.handle_event(event)
        self.assertEqual(first['route'], 'engine')
        with patch.object(MeshEntity3D, 'from_dict', wraps=MeshEntity3D.from_dict) as build:
            second = router.handle_event(copy.deepcopy(event))
        self.assertTrue(second['cache_hit'])
        self.assertEqual(build.call_count, 100)
        self.assertEqual(first['observation_id'], second['observation_id'])
        self.assertEqual(len(json.loads(second['context_text'])['scene_contacts']), 99)

    def test_normalized_payload_and_arrays_do_not_alias_mutable_caller(self):
        source = scene()
        normalized, meshes, fingerprint, payload = _validated_scene(source, _return_payload=True)
        expected = copy.deepcopy(normalized)
        source['meshes'][1]['vertices'][0][0] += 50
        meshes[0].vertices[:] += 1
        self.assertEqual(normalized, expected)
        self.assertEqual(json.loads(payload), expected)
        self.assertEqual(len(fingerprint), 64)

    def test_current_normalization_bypasses_only_duplicate_history_validation(self):
        router = HumanEyeAutoRouter(quad_size=64, clock=lambda: 1000)
        event = observation(include_image=False)
        with patch.object(history_module, '_validate_scene', side_effect=AssertionError('repeat validation')):
            first = router.handle_event(event)
            second = router.handle_event(event)
        self.assertEqual(first['route'], 'engine')
        self.assertTrue(second['cache_hit'])
        malformed = scene()
        malformed['meshes'][0]['vertices'][0][0] = float('nan')
        with self.assertRaises(ValueError):
            router.scene_cache.record_scene(malformed)

    def test_same_revision_mutation_is_fresh_content_and_changes_measurement(self):
        router = HumanEyeAutoRouter(quad_size=64)
        event = observation(include_image=False)
        before = router.handle_event(event)
        part = event['scene']['meshes'][1]
        part['vertices'] = (np.asarray(part['vertices']) + [0, 0, .01]).tolist()
        part['pivot_world'][2] += .01
        after = router.handle_event(event)
        self.assertFalse(after['cache_hit'])
        self.assertNotEqual(before['scene_fingerprint'], after['scene_fingerprint'])
        self.assertNotEqual(before['observation_id'], after['observation_id'])
        self.assertAlmostEqual(json.loads(after['context_text'])['measurement']['signed_clearance_m'], .11)

    def test_same_revision_bad_topology_retires_previous_authority(self):
        router = HumanEyeAutoRouter(quad_size=64)
        event = observation(include_image=False)
        old = router.handle_event(event)
        event['scene']['meshes'][0]['faces'][0][0] = 99999
        rejected = router.handle_event(event)
        self.assertEqual(rejected['reason_codes'], ['invalid_scene'])
        self.assertFalse(router.handle_event(action(old))['allow_action'])

    def test_same_revision_unsupported_far_object_becomes_partial_and_is_not_dropped(self):
        router = HumanEyeAutoRouter(quad_size=64)
        event = observation(scene=sparse_scene(), include_image=False)
        old = router.handle_event(event)
        event['scene']['meshes'][-1]['faces'].pop()
        changed = router.handle_event(event)
        self.assertEqual(changed['route'], 'engine')
        self.assertEqual(changed['observation_status'], 'partial')
        self.assertEqual(changed['scene_assessment']['unknown_object_ids'], ['far97'])
        self.assertEqual(len(json.loads(changed['context_text'])['scene_contacts']), 99)
        self.assertIsNone(changed['observation_id'])
        self.assertFalse(changed['allow_action'])
        self.assertFalse(router.handle_event(action(old))['allow_action'])

    def test_moved_obstacle_is_freshly_checked_by_inner_action_gate(self):
        router = HumanEyeAutoRouter(quad_size=64)
        event = observation(scene=sparse_scene(), include_image=False)
        router.handle_event(event)
        obstacle = event['scene']['meshes'][-1]
        obstacle['vertices'] = (np.asarray(obstacle['vertices']) - [204, 0, 0]).tolist()
        obstacle['pivot_world'][0] -= 204
        changed = router.handle_event(event)
        self.assertEqual(changed['observation_status'], 'complete')
        self.assertEqual(len(json.loads(changed['context_text'])['scene_contacts']), 99)
        with patch.object(router.scene_cache, '_observation_solid_support',
                          side_effect=AssertionError('action must not reuse observation support')):
            rejected = router.handle_event(action(changed, action={'translation': [0, 0, 0]}))
        self.assertEqual(rejected['reason_codes'], ['candidate_collision'])
        self.assertFalse(rejected['allow_action'])


class ObservationSupportMemoTests(unittest.TestCase):
    def test_unchanged_99_objects_reuse_only_exact_support_with_full_coverage(self):
        cache = SpatialSceneCache()
        meshes = [MeshEntity3D.from_dict(value) for value in sparse_scene()['meshes']]
        index = SpatialSceneIndex(meshes, observation_cache=cache)
        index.query(meshes[1], force_ids=['base'])
        meshes[-1] = meshes[-1].translated([0, 0, .00001])
        with patch('human_eye_plugin.geometry_safety.solid_support_status', wraps=solid_support_status) as check:
            changed = SpatialSceneIndex(meshes, observation_cache=cache)
            result = changed.query(meshes[1], force_ids=['base'])
        self.assertEqual(check.call_count, 1)
        self.assertEqual(result['coverage_object_count'], 99)
        self.assertEqual(set(row['object_id'] for row in result['pairs']),
                         set(mesh.object_id for mesh in meshes if mesh.object_id != 'part'))

    def test_faces_edges_axes_metadata_and_components_invalidate_exact_keys(self):
        original = scene()['meshes'][0]
        variants = []
        for change in (lambda v: v['faces'].pop(),
                       lambda v: v['edges'].pop(),
                       lambda v: v['local_axes'][0].__setitem__(0, .999),
                       lambda v: v.update(axes_reason='new host provenance'),
                       lambda v: v['vertices'][0].__setitem__(0, v['vertices'][0][0] + .001)):
            value = copy.deepcopy(original)
            change(value)
            variants.append(value)
        mixed = copy.deepcopy(original)
        mixed['vertices'] += (np.asarray(original['vertices']) + [10, 0, 0]).tolist()
        mixed['faces'] += [[i + 8 for i in face[::-1]] for face in original['faces']]
        mixed['edges'] = None
        variants.append(mixed)
        for value in variants:
            with self.subTest(value=value):
                cache = SpatialSceneCache()
                self.assertTrue(cache._observation_solid_support(original)['supported'])
                with patch('human_eye_plugin.geometry_safety.solid_support_status', wraps=solid_support_status) as check:
                    result = cache._observation_solid_support(value)
                self.assertEqual(check.call_count, 1)
                self.assertEqual(result, solid_support_status(value))
        self.assertFalse(solid_support_status(mixed)['supported'])

    def test_returned_support_payload_cannot_poison_later_lookups(self):
        cache = SpatialSceneCache()
        value = scene()['meshes'][0]
        expected = cache._observation_solid_support(value)
        mutated = cache._observation_solid_support(value)
        mutated['supported'] = False
        mutated['work_budget']['limits'].clear()
        self.assertEqual(cache._observation_solid_support(value), expected)

    def test_unknown_and_resource_rejection_are_never_cached_as_support(self):
        open_value = scene()['meshes'][0]
        open_value['faces'].pop()
        huge = copy.deepcopy(open_value)
        huge['vertices'] *= 300
        huge['faces'] *= 200
        for value in (open_value, huge):
            cache = SpatialSceneCache()
            with patch('human_eye_plugin.geometry_safety.solid_support_status', wraps=solid_support_status) as check:
                for _ in range(2):
                    self.assertFalse(cache._observation_solid_support(value)['supported'])
            self.assertEqual(check.call_count, 2)
            self.assertEqual(cache.stats()['solid_support_entries'], 0)

    def test_default_index_always_validates_and_never_uses_observation_memo(self):
        cache = SpatialSceneCache()
        values = [MeshEntity3D.from_dict(value) for value in scene()['meshes']]
        SpatialSceneIndex(values, observation_cache=cache)
        with patch('human_eye_plugin.spatial_index.solid_support_status', wraps=solid_support_status) as check:
            fresh = SpatialSceneIndex(values)
            fresh.query(values[1], force_ids=['base'])
        self.assertEqual(check.call_count, 3)
        self.assertTrue(fresh.supported)

    def test_support_memo_is_bounded_detached_and_not_imported(self):
        cache = SpatialSceneCache(max_bytes=12 * 1024, max_measurements=3)
        cache.record_scene(scene())
        for i in range(10):
            cache._observation_solid_support(box(str(i), [i, 0, 0], [1, 1, 1]))
            self.assertLessEqual(cache.stats()['accounted_bytes'], cache.max_bytes)
            self.assertLessEqual(cache.stats()['solid_support_entries'], 3)
        exported = cache.export_state()
        self.assertEqual(set(exported), {'schema_version', 'purpose', 'blobs', 'frames'})
        fresh = SpatialSceneCache(max_bytes=12 * 1024, max_measurements=3)
        fresh.import_state(exported)
        self.assertEqual(fresh.stats()['solid_support_entries'], 0)
        with patch('human_eye_plugin.geometry_safety.solid_support_status', wraps=solid_support_status) as check:
            fresh._observation_solid_support(box('9', [9, 0, 0], [1, 1, 1]))
        self.assertEqual(check.call_count, 1)

    def test_immutable_history_payload_is_charged_and_survives_no_alias_shortcut(self):
        cache = SpatialSceneCache(max_bytes=12 * 1024)
        normalized, _, _, payload = _validated_scene(scene(), _return_payload=True)
        first = cache._record_validated_scene(normalized, canonical_scene_payload=payload)
        self.assertTrue(first['retained'])
        accounted = cache.stats()['accounted_bytes']
        public = SpatialSceneCache(max_bytes=12 * 1024)
        public.record_scene(normalized)
        self.assertGreaterEqual(accounted - public.stats()['accounted_bytes'], len(payload))
        returned = cache._record_validated_scene(normalized, canonical_scene_payload=bytes(payload))
        returned['changes']['unchanged'].clear()
        self.assertEqual(cache._record_validated_scene(normalized,
            canonical_scene_payload=payload)['changes']['unchanged'], ['base', 'part'])
        normalized['meshes'][0]['vertices'][0][0] = float('nan')
        with self.assertRaises(ValueError):
            cache.record_scene(normalized)
        self.assertLessEqual(cache.stats()['accounted_bytes'], cache.max_bytes)

    def test_observation_support_cannot_be_forged_through_imported_history(self):
        cache = SpatialSceneCache()
        value = scene()
        cache.record_scene(value)
        cache._observation_solid_support(value['meshes'][0])
        exported = cache.export_state()
        exported['solid_support'] = {'forged': {'supported': True}}
        with self.assertRaises(ValueError):
            cache.import_state(exported)
        # A rejected import must preserve the old complete history atomically.
        self.assertEqual(cache.snapshot(), value)

    def test_history_gc_links_and_duplicate_bytes_preserve_exact_snapshots(self):
        router = HumanEyeAutoRouter(quad_size=64)
        router.scene_cache = SpatialSceneCache(max_frames=2)
        event = observation(include_image=False)
        for i in range(6):
            event['scene']['revision'] = str(i)
            event['scene']['meshes'][1]['name'] = 'part-' + str(i)
            result = router.handle_event(event)
            self.assertEqual(result['route'], 'engine')
            self.assertEqual(router.scene_cache.snapshot(), router.export_state()['sessions'][0][1]['scene'])
        expected = router.scene_cache.export_state()
        with patch.object(history_module, '_encode', side_effect=AssertionError('duplicate history re-encode')):
            repeated = router.handle_event(event)
        self.assertTrue(repeated['cache_hit'])
        self.assertEqual(router.scene_cache.export_state(), expected)
        repeated['scene_assessment']['unknown_object_ids'].append('forged')
        self.assertEqual(router.handle_event(event)['scene_assessment']['unknown_object_ids'], [])


if __name__ == '__main__':
    unittest.main()

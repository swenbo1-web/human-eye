"""Independent lifecycle and geometry contracts for observation-local rays."""
import copy
import gc
import json
import pickle
import unittest
import weakref
from unittest.mock import patch

import numpy as np

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin import attention_rendering as ar
from human_eye_plugin import scene_rendering as sr
from human_eye_plugin.attention_policy import AttentionPolicy
from verification.test_host_runtime import mesh
from verification.test_attention_rendering import fixture


def owned_box(oid='cube', center=(0, 0, 0), size=(2, 2, 2)):
    value = MeshEntity3D.from_dict(mesh(oid, center, size))
    value.vertices.setflags(write=False)
    value.faces.setflags(write=False)
    return value


def view(direction=(0, 0, 1)):
    value = np.eye(4)
    value[2, :3] = direction
    return value


def prepared():
    _, _, meshes, options = fixture()
    image, metadata, token = sr._render_scene_canvas_prepared(meshes, 128,
        focal_id=options['focal_id'], reference_id=options['reference_id'],
        scene_fingerprint=options['scene_fingerprint'])
    return image, metadata, meshes, options, token


def apply(value):
    image, metadata, meshes, options, token = value
    return ar.apply_attention_to_canvas(image, metadata, meshes, **options, prepared_render=token)


class VisibilityTriangleReuseIndependentTests(unittest.TestCase):
    def test_front_surface_visible_back_surface_occluded_and_off_surface_unknown(self):
        box = owned_box()
        cache = ar._WitnessGeometry([box])
        for point, expected in [((.2, .3, 1), True), ((.2, .3, -1), False), ((3, 0, 1), False)]:
            with self.subTest(point=point):
                self.assertEqual(ar._visible_witness(point, cache, view(), 2), expected)
                self.assertEqual(ar._visible_witness(point, [box], view(), 2), expected)

    def test_full_scene_foreground_blocker_remains_an_occluder(self):
        first = owned_box('foreground', (0, 0, 3), (4, 4, 1))
        target = owned_box('target')
        self.assertFalse(ar._visible_witness((.2, .3, 1), ar._WitnessGeometry([first, target]), view(), 2))

    def test_early_occluder_does_not_prepare_unvisited_meshes(self):
        first = owned_box('foreground', (0, 0, 3), (4, 4, 1))
        target = owned_box('target')
        cache = ar._WitnessGeometry([first, target])
        calls = []
        original = ar._WitnessGeometry.for_mesh
        def traced(current, index):
            calls.append(index)
            return original(current, index)
        with patch.object(ar._WitnessGeometry, 'for_mesh', new=traced):
            self.assertFalse(ar._visible_witness((.2, .3, 1), cache, view(), 2))
        self.assertEqual(calls, [0])
        self.assertEqual(cache.retained_bytes, len(first.faces) * 128)

    def test_coplanar_triangle_rays_are_not_certified_unobstructed(self):
        box = owned_box()
        box.faces = np.array([[4, 5, 6], [4, 6, 7]], dtype=int)
        box.faces.setflags(write=False)
        self.assertFalse(ar._visible_witness((0, 0, 1), ar._WitnessGeometry([box]), view((1, 0, 0)), 2))

    def test_closed_face_edges_keep_boundary_behavior(self):
        box = owned_box()
        cache = ar._WitnessGeometry([box])
        for point in [(1, 1, 1), (-1, -1, 1), (0, 0, 1), (1, 0, 1)]:
            with self.subTest(point=point):
                self.assertEqual(ar._visible_witness(point, cache, view(), 2),
                                 ar._visible_witness(point, [box], view(), 2))

    def test_non_float64_inventory_uses_complete_legacy_geometry(self):
        box = owned_box()
        box.vertices = box.vertices.astype(np.float32)
        box.vertices.setflags(write=False)
        cache = ar._WitnessGeometry([box])
        self.assertIsNone(cache.for_mesh(0))
        self.assertEqual(cache.retained_bytes, 0)
        self.assertTrue(ar._visible_witness((.2, .3, 1), cache, view(), 2))

    def test_one_byte_short_cap_falls_back_without_preparing_norms(self):
        box = owned_box()
        cache = ar._WitnessGeometry([box])
        with patch.object(ar, '_WITNESS_GEOMETRY_MAX_BYTES', len(box.faces) * 128 - 1), \
             patch.object(ar.np.linalg, 'norm', side_effect=AssertionError('allocation before admission')):
            self.assertIsNone(cache.for_mesh(0))
        self.assertEqual(cache.retained_bytes, 0)
        self.assertTrue(ar._visible_witness((.2, .3, 1), cache, view(), 2))

    def test_exact_cap_retains_first_mesh_and_keeps_later_mesh_full_geometry(self):
        first = owned_box('target')
        second = owned_box('foreground', (0, 0, 3), (4, 4, 1))
        cache = ar._WitnessGeometry([first, second])
        with patch.object(ar, '_WITNESS_GEOMETRY_MAX_BYTES', len(first.faces) * 128):
            self.assertIsNotNone(cache.for_mesh(0))
            self.assertIsNone(cache.for_mesh(1))
        self.assertEqual(cache.retained_bytes, len(first.faces) * 128)
        self.assertFalse(ar._visible_witness((.2, .3, 1), cache, view(), 2))

    def test_constructor_is_lazy_and_readonly_data_cannot_be_reassigned(self):
        box = owned_box()
        with patch.object(ar.np.linalg, 'norm', side_effect=AssertionError('eager norm')):
            cache = ar._WitnessGeometry([box])
        self.assertEqual(cache.retained_bytes, 0)
        data = cache.for_mesh(0)
        for array in data:
            self.assertFalse(array.flags.writeable)
            with self.assertRaises(ValueError):
                array.flat[0] = 123
        with self.assertRaises(AttributeError):
            cache.retained_bytes = 1

    def test_private_geometry_cannot_be_copied_serialized_or_used_as_a_claim(self):
        cache = ar._WitnessGeometry([owned_box()])
        for operation in (copy.copy, copy.deepcopy, pickle.dumps, json.dumps):
            with self.subTest(operation=operation), self.assertRaises(TypeError):
                operation(cache)

    def test_fresh_container_uses_changed_geometry_without_cross_call_cache(self):
        box = owned_box()
        old = ar._WitnessGeometry([box])
        self.assertTrue(ar._visible_witness((.2, .3, 1), old, view(), 2))
        moved = owned_box(center=(0, 0, 4))
        fresh = ar._WitnessGeometry([moved])
        self.assertFalse(ar._visible_witness((.2, .3, 1), fresh, view(), 2))
        self.assertIsNot(old.for_mesh(0), fresh.for_mesh(0))

    def test_direct_public_attention_keeps_mutable_legacy_path(self):
        image, metadata, meshes, options = fixture()
        with patch.object(ar.time, 'perf_counter', return_value=0.), \
             patch.object(ar, '_WitnessGeometry', side_effect=AssertionError('private cache on public mutable path')):
            _, _, state = ar.apply_attention_to_canvas(image, metadata, meshes, **options)
        self.assertIsNotNone(state)

    def test_no_candidate_does_not_construct_or_scan_witness_geometry(self):
        value = prepared()
        value[3]['contacts'] = []
        with patch.object(ar.time, 'perf_counter', return_value=0.), \
             patch.object(ar, '_WitnessGeometry', side_effect=AssertionError('unused geometry construction')) as cache:
            image, metadata, state = apply(value)
        self.assertIs(image, value[0])
        self.assertIsNone(state)
        self.assertFalse(metadata['attention'].get('applied', False))
        cache.assert_not_called()

    def test_source_change_after_claim_cannot_commit_a_cached_ray(self):
        value = prepared()
        original = AttentionPolicy.propose
        def mutate(policy, *args, **kwargs):
            proposal = original(policy, *args, **kwargs)
            value[2][0].vertices[0, 0] += .025
            return proposal
        with patch.object(ar.time, 'perf_counter', return_value=0.), \
             patch.object(AttentionPolicy, 'propose', new=mutate), \
             patch.object(ar, 'rasterize_attention') as raster:
            _, metadata, state = apply(value)
        self.assertIsNone(state)
        self.assertEqual(metadata['attention']['reason_codes'], ['attention_prepared_inputs_changed'])
        raster.assert_not_called()

    def test_lazy_preparation_cost_is_inside_existing_adoption_budget(self):
        clock = [0.]
        original = ar._WitnessGeometry.for_mesh
        def costly_prepare(current, index):
            data = original(current, index)
            clock[0] = .05
            return data
        with patch.object(ar.time, 'perf_counter', side_effect=lambda: clock[0]), \
             patch.object(ar._WitnessGeometry, 'for_mesh', new=costly_prepare), \
             patch.object(ar, 'rasterize_attention') as raster:
            _, metadata, state = apply(prepared())
        self.assertIsNone(state)
        self.assertEqual(metadata['attention']['reason_codes'], ['attention_budget_exhausted_before_raster'])
        self.assertGreaterEqual(metadata['attention']['additional_cost_ms'], 50.)
        raster.assert_not_called()

    def test_cache_lifetime_ends_on_success_and_on_caught_allocation_failure(self):
        original = ar._WitnessGeometry
        references = []
        class Tracked(original):
            __slots__ = ('__weakref__',)
            def __init__(self, meshes):
                super().__init__(meshes)
                references.append(weakref.ref(self))
        with patch.object(ar, '_WitnessGeometry', Tracked), \
             patch.object(ar.time, 'perf_counter', return_value=0.):
            _, _, state = apply(prepared())
        self.assertIsNotNone(state)
        gc.collect()
        self.assertIsNone(references[-1]())
        with patch.object(ar, '_WitnessGeometry', Tracked), \
             patch.object(Tracked, 'for_mesh', side_effect=MemoryError('controlled allocation failure')), \
             patch.object(ar.time, 'perf_counter', return_value=0.):
            _, metadata, state = apply(prepared())
        self.assertIsNone(state)
        self.assertEqual(metadata['attention']['reason_codes'], ['attention_visibility_precheck_failed'])
        self.assertEqual(metadata['attention']['visibility_precheck_error_type'], 'MemoryError')
        gc.collect()
        self.assertIsNone(references[-1]())


if __name__ == '__main__':
    unittest.main()

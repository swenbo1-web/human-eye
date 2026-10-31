"""Observation-local witness geometry contracts; clocks here are not benchmarks."""
import copy
import gc
import json
import pickle
from types import SimpleNamespace
import unittest
import weakref
from unittest.mock import patch

import numpy as np

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin import attention_rendering as ar
from verification.test_attention_precheck_reuse import prepared_fixture, apply
from verification.test_attention_rendering import fixture
from verification.test_host_runtime import mesh


def boxes(*values):
    return [MeshEntity3D.from_dict(mesh(str(i), center, size))
            for i, (center, size) in enumerate(values)]


def own(values):
    output = [MeshEntity3D.from_dict(value.to_dict()) for value in values]
    for value in output:
        value.vertices.setflags(write=False)
        value.faces.setflags(write=False)
    return tuple(output)


def view(direction):
    result = np.eye(4)
    direction = np.asarray(direction, dtype=float)
    result[2, :3] = direction / np.linalg.norm(direction)
    return result


class WitnessTriangleReuseTests(unittest.TestCase):
    def test_mutable_arrays_cannot_enable_retention(self):
        values = boxes(([0, 0, 0], [2, 2, 2]))
        with self.assertRaises(ValueError):
            ar._WitnessGeometry(values)
        values[0].vertices.setflags(write=False)
        with self.assertRaises(ValueError):
            ar._WitnessGeometry(values)

    def test_local_container_is_not_copyable_or_serializable(self):
        value = ar._WitnessGeometry(own(boxes(([0, 0, 0], [2, 2, 2]))))
        for operation in (copy.copy, copy.deepcopy, pickle.dumps):
            with self.subTest(operation=operation), self.assertRaises(TypeError):
                operation(value)
        with self.assertRaises(AttributeError):
            value.meshes = ()

    def test_construction_is_lazy(self):
        with patch.object(np.linalg, 'norm', side_effect=AssertionError('eager preparation')):
            value = ar._WitnessGeometry(own(boxes(([0, 0, 0], [2, 2, 2]))))
        self.assertEqual(value.retained_bytes, 0)

    def test_preparation_is_once_per_mesh_and_retained_bytes_include_base(self):
        values = own(boxes(([0, 0, 0], [2, 2, 2])))
        value = ar._WitnessGeometry(values)
        original = np.linalg.norm
        with patch.object(np.linalg, 'norm', wraps=original) as norms:
            first = value.for_mesh(0)
            second = value.for_mesh(0)
        self.assertIs(first, second)
        self.assertEqual(norms.call_count, 2)
        self.assertEqual(value.retained_bytes, len(values[0].faces) * 128)
        a, e1, e2, scale = first
        self.assertEqual(a.base.nbytes + e1.nbytes + e2.nbytes + scale.nbytes,
                         value.retained_bytes)
        self.assertTrue(all(not array.flags.writeable for array in (a.base, *first)))
        with self.assertRaises(ValueError):
            first[1][0, 0] = 1

    def test_exact_cap_fits_one_mesh_and_next_mesh_uses_original_path(self):
        values = own(boxes(([0, 0, 0], [2, 2, 2]), ([3, 0, 0], [2, 2, 2])))
        cap = len(values[0].faces) * 128
        with patch.object(ar, '_WITNESS_GEOMETRY_MAX_BYTES', cap):
            value = ar._WitnessGeometry(values)
            self.assertIsNotNone(value.for_mesh(0))
            self.assertIsNone(value.for_mesh(1))
            self.assertEqual(value.retained_bytes, cap)
            for point in ([0, 0, 1], [3, 0, 1], [3, 0, -1]):
                self.assertEqual(ar._visible_witness(point, value, view([0, 0, 1]), 1),
                                 ar._visible_witness(point, values, view([0, 0, 1]), 1))
        self.assertEqual(value.retained_bytes, cap)

    def test_over_cap_fallback_does_not_prepare_then_discard(self):
        values = own(boxes(([0, 0, 0], [2, 2, 2])))
        with patch.object(ar, '_WITNESS_GEOMETRY_MAX_BYTES', 0):
            value = ar._WitnessGeometry(values)
            with patch.object(np.linalg, 'norm', side_effect=AssertionError('prepared outside cap')):
                self.assertIsNone(value.for_mesh(0))
                self.assertIsNone(value.for_mesh(0))
            self.assertEqual(value.retained_bytes, 0)

    def test_first_occluder_early_exit_leaves_later_mesh_unprepared(self):
        values = own(boxes(([0, 0, 0], [2, 2, 2]), ([3, 0, 0], [2, 2, 2])))
        value = ar._WitnessGeometry(values)
        self.assertFalse(ar._visible_witness([0, 0, 0], value, view([0, 0, 1]), 1))
        self.assertEqual(value.retained_bytes, len(values[0].faces) * 128)
        # A later ray still checks the second mesh, instead of treating the
        # unprepared tail as empty geometry after a previous early return.
        self.assertTrue(ar._visible_witness([3, 0, 1], value, view([0, 0, 1]), 1))
        self.assertEqual(value.retained_bytes, sum(len(m.faces) for m in values) * 128)

    def test_directions_and_spans_reuse_only_direction_free_arrays(self):
        values = own(boxes(([0, 0, 0], [2, 2, 2])))
        value = ar._WitnessGeometry(values)
        for point in ([0, 0, 1], [0, 0, -1], [1, 0, 0], [0, 0, 0]):
            for direction in ([0, 0, 1], [0, 0, -1], [1, 0, 0], [1, 2, 3]):
                for span in (.00001, 1., 10000.):
                    with self.subTest(point=point, direction=direction, span=span):
                        self.assertEqual(ar._visible_witness(point, value, view(direction), span),
                                         ar._visible_witness(point, values, view(direction), span))
        self.assertEqual(value.retained_bytes, len(values[0].faces) * 128)

    def test_coplanar_grazing_surface_remains_rejected(self):
        vertices = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
        faces = np.array([[0, 1, 2]], dtype=int)
        vertices.setflags(write=False); faces.setflags(write=False)
        values = (SimpleNamespace(vertices=vertices, faces=faces),)
        value = ar._WitnessGeometry(values)
        self.assertFalse(ar._visible_witness([.25, .25, 0], value, view([1, 0, 0]), 1))
        self.assertEqual(ar._visible_witness([.25, .25, 0], value, view([1, 0, 0]), 1),
                         ar._visible_witness([.25, .25, 0], values, view([1, 0, 0]), 1))

    def test_thin_wall_and_large_coordinates_match_original_path(self):
        for offset in (0., 1e6, 1e9):
            values = own(boxes(([offset, offset, offset], [1, 1, .000025]),
                              ([offset, offset, offset + .00002], [.8, .8, .000001])))
            value = ar._WitnessGeometry(values)
            for z in (offset, offset + .0000125, offset + .0000205):
                for direction in ([0, 0, 1], [0, 0, -1], [1, 1, .3]):
                    with self.subTest(offset=offset, z=z, direction=direction):
                        point = [offset, offset, z]
                        self.assertEqual(ar._visible_witness(point, value, view(direction), .001),
                                         ar._visible_witness(point, values, view(direction), .001))

    def test_new_owned_snapshot_does_not_reuse_old_arrays(self):
        mutable = boxes(([0, 0, 0], [2, 2, 2]))
        first = ar._WitnessGeometry(own(mutable)); data = first.for_mesh(0)
        mutable[0].vertices[:, 2] += 4.
        second = ar._WitnessGeometry(own(mutable)); changed = second.for_mesh(0)
        self.assertFalse(np.array_equal(data[0], changed[0]))
        self.assertFalse(any(np.shares_memory(a, b) for a, b in zip(data, changed)))
        self.assertTrue(ar._visible_witness([0, 0, 1], first, view([0, 0, 1]), 1))
        self.assertFalse(ar._visible_witness([0, 0, 1], second, view([0, 0, 1]), 1))

    def test_empty_triangle_geometry_does_not_create_visibility(self):
        vertices = np.empty((0, 3), dtype=float); faces = np.empty((0, 3), dtype=int)
        vertices.setflags(write=False); faces.setflags(write=False)
        values = (SimpleNamespace(vertices=vertices, faces=faces),)
        value = ar._WitnessGeometry(values)
        self.assertFalse(ar._visible_witness([0, 0, 0], value, np.eye(4), 1))
        self.assertEqual(value.retained_bytes, 0)

    def test_preparation_exception_retains_no_partial_entry(self):
        value = ar._WitnessGeometry(own(boxes(([0, 0, 0], [2, 2, 2]))))
        with patch.object(np.linalg, 'norm', side_effect=MemoryError('test allocation failure')):
            with self.assertRaises(MemoryError):
                value.for_mesh(0)
        self.assertEqual(value.retained_bytes, 0)
        self.assertIsNotNone(value.for_mesh(0))

    def test_public_mutable_path_does_not_construct_local_container(self):
        image, metadata, meshes, options = fixture()
        with patch.object(ar, '_WitnessGeometry', side_effect=AssertionError('mutable retention')), \
             patch.object(ar.time, 'perf_counter', return_value=0.):
            output, visual, state = ar.apply_attention_to_canvas(image, metadata, meshes, **options)
        self.assertIsNotNone(state)
        self.assertTrue(visual['attention']['applied'])
        self.assertEqual(output.size, image.size)

    def test_no_contacts_does_not_construct_or_scan_local_container(self):
        value = prepared_fixture()
        with patch.object(ar, '_WitnessGeometry', side_effect=AssertionError('no candidate allocation')) as prepare, \
             patch.object(ar, '_visible_witness') as ray, \
             patch.object(ar.time, 'perf_counter', return_value=0.):
            output, metadata, state = apply(value, contacts=[])
        prepare.assert_not_called(); ray.assert_not_called()
        self.assertIs(output, value[0]); self.assertIsNone(state)
        self.assertEqual(metadata['attention']['decision'], 'hold')

    def test_prepared_and_public_paths_keep_pixels_and_complete_view_evidence(self):
        image, metadata, meshes, options = fixture()
        prepared = prepared_fixture()
        with patch.object(ar.time, 'perf_counter', return_value=0.):
            expected, old_metadata, old_state = ar.apply_attention_to_canvas(image, metadata, meshes, **options)
            output, new_metadata, new_state = apply(prepared)
        np.testing.assert_array_equal(output, expected)
        self.assertEqual(new_metadata['views'], old_metadata['views'])
        self.assertEqual(new_state, old_state)
        self.assertEqual(new_metadata['attention']['readability'], old_metadata['attention']['readability'])
        self.assertNotIn('witness_geometry', json.dumps(new_metadata, allow_nan=False))

    def test_cached_arrays_are_released_after_success_or_visibility_exception(self):
        original = ar._WitnessGeometry.for_mesh
        for fail in (False, True):
            references = []
            def prepare(value, index):
                data = original(value, index)
                if data:
                    references.extend(weakref.ref(array) for array in data)
                return data
            def ray(*args):
                result = original_ray(*args)
                if fail:
                    raise ValueError('visibility callback failed after preparation')
                return result
            original_ray = ar._visible_witness
            value = prepared_fixture()
            with patch.object(ar._WitnessGeometry, 'for_mesh', new=prepare), \
                 patch.object(ar, '_visible_witness', new=ray), \
                 patch.object(ar.time, 'perf_counter', return_value=0.):
                _, _, state = apply(value)
            self.assertTrue(references)
            self.assertEqual(state is None, fail)
            gc.collect()
            self.assertTrue(all(reference() is None for reference in references))

    def test_preparation_cost_is_inside_existing_attention_budget(self):
        original = ar._WitnessGeometry.for_mesh
        clock = [0.]
        def prepare(value, index):
            data = original(value, index)
            clock[0] += .041
            return data
        with patch.object(ar._WitnessGeometry, 'for_mesh', new=prepare), \
             patch.object(ar.time, 'perf_counter', side_effect=lambda: clock[0]), \
             patch.object(ar, 'rasterize_attention') as raster:
            _, metadata, state = apply(prepared_fixture())
        self.assertIsNone(state)
        self.assertGreaterEqual(metadata['attention']['additional_cost_ms'], 41.)
        self.assertEqual(metadata['attention']['reason_codes'], ['attention_budget_exhausted_before_raster'])
        raster.assert_not_called()


if __name__ == '__main__':
    unittest.main()

"""Independent M3 regressions against fixed E and analytic surface distances.

The archived E module is read only from its accepted commit. These tests do
not measure performance, invoke Blender, or depend on any competing branch.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import subprocess
import types
import unittest

import numpy as np

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin import geometry_safety as candidate
from verification.test_concave_geometry import box, changed, entity, ring


ROOT = Path(__file__).resolve().parents[1]
ACCEPTED_E = '11c8fc7332e530ead2f8fa30d2a35c7eb14e7d15'


def accepted_geometry():
    source = subprocess.run(
        ['git', 'show', f'{ACCEPTED_E}:human_eye_plugin/geometry_safety.py'],
        cwd=ROOT, check=True, capture_output=True, text=True, encoding='utf8',
    ).stdout
    module = types.ModuleType('human_eye_plugin._perf030_001_e_baseline')
    module.__package__ = 'human_eye_plugin'
    exec(compile(source, f'{ACCEPTED_E}/geometry_safety.py', 'exec'), module.__dict__)
    return module


def compound_boxes(centers, identity):
    parts = [box(center, (1, 1, 1), identity) for center in centers]
    return entity(identity, np.vstack([part.vertices for part in parts]),
                  np.vstack([part.faces + 8 * index for index, part in enumerate(parts)]))


class Perf030PruningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = accepted_geometry()
        cls.inputs = json.loads((ROOT / 'verification/fixes/perf030_001/inputs.json').read_text('utf8'))
        if cls.inputs['baseline'] != ACCEPTED_E:
            raise AssertionError('Frozen M3 inputs must use accepted E')

    def assert_kernel_pair(self, left, right, expected):
        old_scalar = self.baseline._surface_distance(left, right)
        new_scalar = candidate._surface_distance(left, right)
        self.assertAlmostEqual(new_scalar, old_scalar, delta=max(1e-15, abs(old_scalar) * 1e-12))
        self.assertAlmostEqual(new_scalar, expected, delta=max(1e-15, abs(expected) * 1e-12))
        old_witness = self.baseline._surface_distance_with_witness(left, right)
        new_witness = candidate._surface_distance_with_witness(left, right)
        self.assertAlmostEqual(new_witness[0], old_witness[0], delta=max(1e-15, abs(old_witness[0]) * 1e-12))
        self.assertAlmostEqual(new_witness[0], expected, delta=max(1e-15, abs(expected) * 1e-12))
        np.testing.assert_allclose(new_witness[1:], old_witness[1:], rtol=0, atol=1e-13)
        if expected > 0:
            self.assertGreater(new_scalar, 0)
            self.assertGreater(new_witness[0], 0)

    def test_frozen_inputs_preserve_public_classification_and_clearance(self):
        self.assertLessEqual(len(self.inputs['cases']), 12)
        for case in self.inputs['cases']:
            with self.subTest(case=case['name']):
                old_pair = [MeshEntity3D.from_dict(value) for value in case['meshes']]
                new_pair = [MeshEntity3D.from_dict(value) for value in case['meshes']]
                old = self.baseline.measure_pair_geometry(*old_pair, need_clearance=True)
                new = candidate.measure_pair_geometry(*new_pair, need_clearance=True)
                for field in ('measurement_valid', 'is_penetrating', 'reason',
                              'measurement_method', 'clearance_method', 'witness_scope'):
                    self.assertEqual(new.get(field), old.get(field), field)
                if old['measurement_valid']:
                    expected = case['expected_clearance_m']
                    self.assertAlmostEqual(new['signed_clearance_m'], old['signed_clearance_m'], delta=1e-14)
                    self.assertAlmostEqual(new['signed_clearance_m'], expected, delta=1e-14)
                    if old.get('point_a_world') is not None:
                        np.testing.assert_allclose(
                            [new['point_a_world'], new['point_b_world']],
                            [old['point_a_world'], old['point_b_world']], rtol=0, atol=1e-13)

    def test_analytic_boxes_and_edge_interior_minimum(self):
        self.assert_kernel_pair(box(size=(1, 1, 1), identity='a'),
                                box((2, 0, 0), (1, 1, 1), 'b'), 1.)
        self.assert_kernel_pair(box(size=(2, .1, .1), identity='a'),
                                box((0, 0, .2), (.1, 2, .1), 'b'), .1)

    def test_ring_witness_and_subnanometre_boundary(self):
        self.assert_kernel_pair(box(), ring(), .019)
        self.assert_kernel_pair(box((.019 - 1e-12, 0, 0)), ring(), 1e-12)
        self.assert_kernel_pair(box((.019, 0, 0)), ring(), 0.)

    def test_rotated_probe_has_analytic_hole_gap(self):
        angle = .37
        rotation = np.array([[math.cos(angle), -math.sin(angle), 0],
                             [math.sin(angle), math.cos(angle), 0], [0, 0, 1]])
        original = box()
        probe = changed(original, vertices=original.vertices @ rotation.T)
        self.assert_kernel_pair(probe, ring(), .025 - np.max(np.abs(probe.vertices[:, :2])))

    def test_large_translation_uses_represented_geometry(self):
        shift = np.full(3, 1e12)
        probe, reference = box(), ring()
        probe = changed(probe, vertices=probe.vertices + shift)
        reference = changed(reference, vertices=reference.vertices + shift)
        expected = float((shift[0] + .025) - np.max(probe.vertices[:, 0]))
        self.assert_kernel_pair(probe, reference, expected)

    def test_original_witness_priority_across_64_feature_boundaries(self):
        left = compound_boxes([(3 * index, 0, 0) for index in range(9)], 'a')
        right = box((12, 0, 3), (26, 2, 1), 'b')
        self.assertGreater(len(left.vertices), 64)
        self.assertGreater(len(left.faces), 64)
        self.assertTrue(candidate.work_budget_status([left, right])['within_budget'])
        self.assert_kernel_pair(left, right, 2.)
        self.assertEqual(candidate._surface_distance_with_witness(left, right),
                         self.baseline._surface_distance_with_witness(left, right))

    def test_point_rows_are_reconsidered_for_each_original_face_block(self):
        left = compound_boxes([(0, 0, 0), (100, 0, 0)], 'a')
        centers = [(x, y, 3) for x in (-.4, 0., .4) for y in (-.4, 0., .4)]
        centers += [(-.2, -.2, 3), (.2, .2, 3), (100, 0, 2)]
        parts = [box(center, (.05, .05, .05), 'b') for center in centers[:-1]]
        parts.append(box(centers[-1], (4, 4, .05), 'b'))
        right = entity('b', np.vstack([part.vertices for part in parts]),
                       np.vstack([part.faces + 8 * index for index, part in enumerate(parts)]))
        self.assertGreater(len(right.faces), 128)
        self.assert_kernel_pair(left, right, 1.475)

    def test_aabb_cartesian_filter_retains_original_index_order(self):
        left = np.array([[2., 0, 0], [0., 0, 0], [100., 0, 0]])
        right = np.array([[0., 0, 0], [2., 0, 0], [200., 0, 0]])
        rows, columns = candidate._aabb_candidates(left, left, right, right, 0.)
        np.testing.assert_array_equal(rows, [0, 1])
        np.testing.assert_array_equal(columns, [0, 1])

    def test_aabb_keeps_equal_and_roundoff_uncertain_bounds(self):
        left = np.array([[0., 0, 0]])
        right = np.array([[1., 0, 0], [np.nextafter(1., np.inf), 0, 0], [2., 0, 0]])
        rows, columns = candidate._aabb_candidates(left, left, right, right, 1.)
        np.testing.assert_array_equal(rows, [0])
        np.testing.assert_array_equal(columns, [0, 1])

    def test_nonfinite_and_overflow_bounds_retain_every_feature(self):
        for value in (float('nan'), float('inf'), -float('inf'), 1e308):
            with self.subTest(value=value), np.errstate(over='raise', invalid='raise'):
                left = np.array([[value, 0, 0], [0., 0, 0]])
                right = np.array([[-1e308, 0, 0], [0., 0, 0]])
                rows, columns = candidate._aabb_candidates(left, left, right, right, 0.)
                np.testing.assert_array_equal(rows, [0, 1])
                np.testing.assert_array_equal(columns, [0, 1])

    def test_infinite_incumbent_keeps_initial_kernel_input(self):
        left = np.zeros((2, 1, 3))
        right = np.ones((3, 3, 3))
        selected_left, selected_right = candidate._surface_candidates(left, right, math.inf)
        self.assertIs(selected_left, left)
        self.assertIs(selected_right, right)

    def test_degenerate_original_face_remains_public_unknown(self):
        reference = ring()
        faces = reference.faces.copy()
        faces[-1, 2] = faces[-1, 1]
        reference = changed(reference, faces=faces)
        for geometry in (self.baseline, candidate):
            result = geometry.measure_pair_geometry(box(), reference, need_clearance=True)
            self.assertFalse(result['measurement_valid'])
            self.assertIsNone(result['signed_clearance_m'])


if __name__ == '__main__':
    unittest.main()

"""Exact group-reuse contracts and frozen-v21 discovery differentials.

The baseline is the immutable pre-change source saved for this optimization.
Synthetic helper certificates only test candidate bookkeeping, not feasibility.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import importlib.util
import json
import math
from pathlib import Path
import random
import unittest
from unittest.mock import patch

from human_eye_plugin import support_plane_candidate as candidate
from human_eye_plugin import support_plane_discovery as current
from verification.test_support_plane_candidate import (
    flat_scene, slope_scene, tetra_scene, tilted_scene,
)


BASELINE = (Path(__file__).parent / 'fixes/20261030_v21_deterministic_reuse'
            / 'before/human_eye_plugin/support_plane_discovery.py')


def baseline_module():
    spec = importlib.util.spec_from_file_location(
        'human_eye_plugin._group_reuse_frozen_baseline', BASELINE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def subdivided_scene(divisions=3):
    """Retriangulate the same closed box without altering its six exact planes.

    Fraction interpolation preserves constant coordinates exactly, and shared
    boundary vertices are deduplicated before constructing outward triangles.
    Three divisions give 56 vertices/108 faces, within the original limits.
    """
    scene = flat_scene()
    mesh = scene['meshes'][0]
    original = [[Fraction(x) for x in vertex] for vertex in mesh['vertices']]
    vertices, faces, by_vertex = [], [], {}

    def point(a, b, c, i, j):
        value = tuple(float(((divisions-i-j)*a[k]+i*b[k]+j*c[k])/divisions)
                      for k in range(3))
        if value not in by_vertex:
            by_vertex[value] = len(vertices)
            vertices.append(list(value))
        return by_vertex[value]

    for face in mesh['faces']:
        a, b, c = (original[index] for index in face)
        for i in range(divisions):
            for j in range(divisions-i):
                faces.append([point(a, b, c, i, j), point(a, b, c, i+1, j),
                              point(a, b, c, i, j+1)])
                if i+j <= divisions-2:
                    faces.append([point(a, b, c, i+1, j), point(a, b, c, i+1, j+1),
                                  point(a, b, c, i, j+1)])
    mesh.update(vertices=vertices, faces=faces, edges=None)
    return scene


def invoke(module, scene, request=None):
    return module.discover_support_planes(scene, 'part', 'base',
                                         {} if request is None else request)


@unittest.skipUnless(BASELINE.is_file(), 'Frozen pre-change discovery is unavailable')
class DiscoveryGroupReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = baseline_module()

    def assertEquivalent(self, scene, request=None):
        frozen_scene = copy.deepcopy(scene)
        frozen_request = copy.deepcopy(request)
        before = invoke(self.old, scene, request)
        after = invoke(current, scene, request)
        self.assertEqual(before, after)
        self.assertEqual(json.dumps(before, sort_keys=True, allow_nan=False),
                         json.dumps(after, sort_keys=True, allow_nan=False))
        self.assertEqual(scene, frozen_scene)
        self.assertEqual(request, frozen_request)
        return after

    def test_complete_fields_identical_for_real_supported_pairs_and_directions(self):
        scenes = [flat_scene(), tilted_scene(), slope_scene(), subdivided_scene()]
        requests = [{}, {'max_candidates': 1}, {'max_candidates': 6},
                    {'direction_world': [0, 0, 1]}, {'direction_world': [0, 0, -1]},
                    {'direction_world': [1, 0, 0]}, {'direction_world': [1, 0, 1e-10]}]
        for scene in scenes:
            for request in requests:
                with self.subTest(faces=len(scene['meshes'][0]['faces']), request=request):
                    self.assertEquivalent(scene, request)

    def test_first_footprint_failure_does_not_cancel_the_plane_group(self):
        for point, index in [((-.05, .05, .104), 3), ((.05, .05, .104), 2)]:
            with self.subTest(point=point):
                result = self.assertEquivalent(tetra_scene(point))
                self.assertEqual(result['status'], 'complete')
                self.assertEqual(result['candidates'][0]['selector']['reference_triangle_index'], index)

    def test_exact_one_ulp_footprint_boundary_preserves_refusal(self):
        for x, status in [(math.nextafter(.1, 0.), 'complete'),
                          (math.nextafter(.1, math.inf), 'unsupported')]:
            with self.subTest(x=x):
                self.assertEqual(self.assertEquivalent(tetra_scene((x, 0., .104)))['status'], status)

    def test_refusal_and_unknown_outputs_are_identical(self):
        scenes = [flat_scene(0.), flat_scene(-.001), tetra_scene((.2, .2, .104))]
        opened = flat_scene(); opened['meshes'][0]['faces'].pop(); scenes.append(opened)
        reversed_mesh = flat_scene()
        reversed_mesh['meshes'][0]['faces'] = [face[::-1] for face in reversed_mesh['meshes'][0]['faces']]
        scenes.append(reversed_mesh)
        degenerate = flat_scene(); degenerate['meshes'][0]['faces'][0] = [0, 0, 1]; scenes.append(degenerate)
        excessive = flat_scene(); excessive['meshes'][0]['vertices'] += [[0., 0., 0.]]*57; scenes.append(excessive)
        complex_ratio = flat_scene(); complex_ratio['meshes'][0]['vertices'][0][0] = 1e-200; scenes.append(complex_ratio)
        missing_axes = flat_scene(); missing_axes['meshes'][1]['axes_source'] = 'inferred'; scenes.append(missing_axes)
        disabled = flat_scene()
        disabled['host_execution'] = {'schema_version': '1.0', 'operation': 'rigid_transform',
            'supported': False, 'scope': 'independent_static_rigid_meshes',
            'reasons': [{'object_id': 'part', 'object_name': 'part', 'reason': 'test_disabled'}]}
        scenes.append(disabled)
        long_revision = flat_scene(); long_revision['revision'] = 'r'*257; scenes.append(long_revision)
        for index, scene in enumerate(scenes):
            with self.subTest(index=index):
                self.assertEquivalent(scene)

    def test_near_coplanar_original_planes_are_not_rounded_into_one(self):
        scene = tetra_scene((.03, -.03, .104))
        scene['meshes'][0]['vertices'][6][2] = math.nextafter(.1, math.inf)
        result = self.assertEquivalent(scene)
        self.assertEqual(result['status'], 'complete', result)
        self.assertEqual(result['exact_plane_group_count'], 7)

    def test_seeded_translation_scale_and_small_gap_differential(self):
        rng = random.Random(20261030)
        for index in range(36):
            scene = flat_scene(rng.choice((1e-8, .001, .004, .02)))
            scale = rng.choice((.125, 1., 8.))
            origin = [rng.choice((-.5, 0., .5)) for _ in range(3)]
            for mesh in scene['meshes']:
                mesh['vertices'] = [[x*scale+origin[k] for k, x in enumerate(vertex)]
                                    for vertex in mesh['vertices']]
                mesh['pivot_world'] = [x*scale+origin[k] for k, x in enumerate(mesh['pivot_world'])]
            with self.subTest(index=index, scale=scale, origin=origin):
                self.assertEquivalent(scene, {'direction_world': [0, 0, rng.choice((-7., 3.))]})

    def test_each_exact_plane_still_counted_when_reusing_certificates(self):
        for divisions in (1, 2, 3):
            scene = subdivided_scene(divisions)
            with self.subTest(divisions=divisions):
                with patch.object(candidate, '_certificate_from_rationals',
                                  wraps=candidate._certificate_from_rationals) as calls:
                    before = invoke(self.old, scene)
                old_count = calls.call_count
                with patch.object(candidate, '_certificate_from_rationals',
                                  wraps=candidate._certificate_from_rationals) as calls:
                    after = invoke(current, scene)
                self.assertEqual(before, after)
                self.assertEqual(old_count, 12*divisions*divisions)
                self.assertEqual(after['exact_plane_group_count'], 6)
                self.assertEqual(after['scanned_reference_triangle_count'], old_count)
                self.assertEqual(after['candidates'][0]['coplanar_triangle_count'], 2*divisions*divisions)
                self.assertLess(calls.call_count, old_count)
                self.assertEqual(calls.call_count, 6)

    def test_all_group_and_truncation_fields_with_synthetic_certificates(self):
        scene = flat_scene()
        from human_eye_plugin.auto_router import _validated_scene
        _, meshes, _ = _validated_scene(scene)
        fv, _ = candidate._rational_mesh(meshes[1])
        rv, rf = candidate._rational_mesh(meshes[0])
        template = candidate._certificate_from_rationals(fv, rv, rf, 2)

        def synthetic(focal, reference, triangles, index):
            row = copy.deepcopy(template)
            a, b, c = [reference[i] for i in triangles[index]]
            normal = candidate._cross(candidate._sub(b, a), candidate._sub(c, a))
            length = math.hypot(*(float(x) for x in normal))
            row.update(reference_triangle_index=index,
                       plane_normal_world=[float(x)/length for x in normal])
            return row

        # Deliberately synthetic: all six planes receive a helper certificate,
        # solely to exercise total/omitted/ambiguous and direction bookkeeping.
        for request in ({'max_candidates': 1}, {'max_candidates': 6},
                        {'max_candidates': 1, 'direction_world': [0, 0, 1]}):
            with self.subTest(request=request), patch.object(candidate, '_certificate_from_rationals', synthetic):
                result = self.assertEquivalent(scene, request)
                self.assertTrue(result['enumeration_complete'])
                self.assertTrue(result['ambiguous'])
                expected = 2 if 'direction_world' in request else 6
                self.assertEqual(result['total_candidate_count'], expected)
                self.assertEqual(result['omitted_candidate_count'], max(0, expected-request['max_candidates']))

    def test_strict_measurement_failure_still_discards_all_selectors(self):
        with patch.object(candidate, 'measure_pair_geometry', side_effect=ValueError('kernel failure')):
            result = self.assertEquivalent(subdivided_scene())
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['candidates'], [])
        self.assertEqual(result['reason_codes'], ['strict_pair_measurement_failed'])

    def test_invalid_requests_and_geometry_retain_error_types(self):
        variants = [(flat_scene(), {'max_candidates': True}),
                    (flat_scene(), {'direction_world': [0, 0, 0]}),
                    (flat_scene(), {'execute': True})]
        boolean_vertex = flat_scene(); boolean_vertex['meshes'][0]['vertices'][0][0] = True
        variants.append((boolean_vertex, {}))
        for scene, request in variants:
            outcomes = []
            for module in (self.old, current):
                try:
                    invoke(module, scene, request)
                except Exception as exc:
                    outcomes.append((type(exc), exc.args))
            self.assertEqual(len(outcomes), 2)
            self.assertEqual(outcomes[0], outcomes[1])


if __name__ == '__main__':
    unittest.main()

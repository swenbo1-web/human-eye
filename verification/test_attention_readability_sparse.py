"""Exact original evidence comparison; these are not latency measurements."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin.attention_rendering import _readability_evidence


def full_frame_oracle(color, owners, meshes, target_ids, pixels):
    """Frozen v8 float64/norm algorithm, independent of the optimized path."""
    by_id = {mesh.object_id: index for index, mesh in enumerate(meshes)}
    boundary = np.zeros(owners.shape, dtype=bool)
    for axis in (0, 1):
        first = (slice(None, -1), slice(None)) if axis == 0 else (slice(None), slice(None, -1))
        second = (slice(1, None), slice(None)) if axis == 0 else (slice(None), slice(1, None))
        contrast = np.linalg.norm(color[first].astype(float) - color[second].astype(float), axis=2)
        changed = (owners[first] != owners[second]) & (contrast >= 24.)
        boundary[first] |= changed
        boundary[second] |= changed
    counts = [int(np.count_nonzero(owners == by_id[identity])) for identity in target_ids]
    edges = [int(np.count_nonzero(boundary & (owners == by_id[identity]))) for identity in target_ids]
    fraction = np.linspace(.1, .9, 17)
    samples = pixels[0] + fraction[:, None] * (pixels[1] - pixels[0])
    xy = np.rint(samples).astype(int)
    xy[:, 0] = np.clip(xy[:, 0], 0, owners.shape[1] - 1)
    xy[:, 1] = np.clip(owners.shape[0] - 1 - xy[:, 1], 0, owners.shape[0] - 1)
    background = int(np.count_nonzero(owners[xy[:, 1], xy[:, 0]] < 0))
    return {'passed': min(counts) >= 16 and min(edges) >= 4,
        'target_object_ids': list(target_ids), 'visible_surface_pixels': counts,
        'contrasting_boundary_pixels': edges, 'minimum_surface_pixels': 16,
        'minimum_boundary_pixels': 4, 'minimum_rgb_boundary_contrast': 24.,
        'measurement_stage': 'before_any_annotations_full_scene_depth_winners',
        'scope': 'two_object_surface_localization_and_contrasting_boundaries_not_gap_visibility',
        'gap_background_samples': background, 'gap_segment_samples': len(fraction),
        'visible_gap_certified': False, 'annotations_count_as_evidence': False,
        'model_quality_gain_proven': False}


class SparseAttentionReadabilityTests(unittest.TestCase):
    def setUp(self):
        self.meshes = [SimpleNamespace(object_id=f'object-{i}') for i in range(4)]
        self.ids = ['object-0', 'object-1']

    def assert_oracle(self, color, owners, pixels=None, ids=None):
        if pixels is None:
            pixels = np.array([[0., 0.], [owners.shape[1] - 1., owners.shape[0] - 1.]])
        targets = self.ids if ids is None else ids
        before_color, before_owners = color.copy(), owners.copy()
        expected = full_frame_oracle(color, owners, self.meshes, targets, pixels)
        actual = _readability_evidence(color, owners, self.meshes, targets, pixels)
        self.assertEqual(actual, expected)
        np.testing.assert_array_equal(color, before_color)
        np.testing.assert_array_equal(owners, before_owners)
        return actual

    def test_uniform_owner_and_complete_occlusion_have_no_invented_boundary(self):
        rng = np.random.default_rng(4101)
        for size in (1, 8, 64, 256, 384, 512):
            color = rng.integers(0, 256, (size, size, 3), dtype=np.uint8)
            for owner in (-1, 0, 2):
                with self.subTest(size=size, owner=owner):
                    owners = np.full((size, size), owner, dtype=np.int32)
                    actual = self.assert_oracle(color, owners)
                    self.assertEqual(actual['contrasting_boundary_pixels'], [0, 0])
                    self.assertFalse(actual['passed'])

    def test_dense_checkerboards_uint8_extremes_and_same_color(self):
        for size in (8, 64, 256, 384, 512):
            owners = (np.indices((size, size)).sum(axis=0) % 2).astype(np.int32)
            for high in (0, 23, 24, 25, 255):
                with self.subTest(size=size, high=high):
                    color = np.zeros((size, size, 3), dtype=np.uint8)
                    color[owners == 1, 0] = high
                    actual = self.assert_oracle(color, owners)
                    expected = size * size // 2 if high >= 24 else 0
                    self.assertEqual(actual['contrasting_boundary_pixels'], [expected, expected])

    def test_inclusive_squared_threshold_and_both_edge_sides(self):
        owners = np.zeros((8, 8), dtype=np.int32)
        owners[:, 4:] = 1
        for rgb, passes in (((23, 6, 0), False), ((24, 0, 0), True),
                            ((16, 16, 8), True), ((24, 1, 0), True),
                            ((255, 255, 255), True)):
            with self.subTest(rgb=rgb):
                color = np.zeros((8, 8, 3), dtype=np.uint8)
                color[:, 4:] = rgb
                actual = self.assert_oracle(color, owners)
                self.assertEqual(actual['contrasting_boundary_pixels'], [8, 8] if passes else [0, 0])
                self.assertEqual(actual['passed'], passes)
                # Reverse the signed color difference without changing owners.
                self.assert_oracle(255 - color, owners)

    def test_seeded_random_evidence_matches_all_fields(self):
        rng = np.random.default_rng(4102)
        for size in (1, 2, 7, 32, 64, 128, 256, 384, 512):
            for case in range(6):
                with self.subTest(size=size, case=case):
                    owners = rng.integers(-1, 4, (size, size), dtype=np.int32)
                    color = rng.integers(0, 256, (size, size, 3), dtype=np.uint8)
                    pixels = rng.uniform(-size, size * 2, (2, 2))
                    self.assert_oracle(color, owners, pixels,
                        ids=['object-0', 'object-1', 'object-2', 'object-3'])

    def test_noncontiguous_readonly_rectangular_arrays(self):
        rng = np.random.default_rng(4103)
        base_color = rng.integers(0, 256, (66, 98, 3), dtype=np.uint8)
        base_owners = rng.integers(-1, 4, (66, 98), dtype=np.int32)
        for color, owners in ((base_color[::2, ::2], base_owners[::2, ::2]),
                              (base_color[::-1, ::-1], base_owners[::-1, ::-1]),
                              (base_color.transpose(1, 0, 2), base_owners.T)):
            color.setflags(write=False)
            owners.setflags(write=False)
            self.assert_oracle(color, owners)

    def test_fixed_density_threshold_below_exact_and_above_matches_oracle(self):
        # Eight rows of eight horizontal pairs = 64 pairs. One transition
        # per selected row yields exactly7/64,8/64,9/64; vertical transitions
        # are evaluated separately using the same immutable threshold.
        rng = np.random.default_rng(4104)
        for count in (7, 8, 9):
            owners = np.zeros((8, 9), dtype=np.int32)
            owners[:min(count, 8), 4:] = 1
            if count == 9:
                owners[0, 7:] = 0
            self.assertEqual(int(np.count_nonzero(owners[:, :-1] != owners[:, 1:])), count)
            color = rng.integers(0, 256, (8, 9, 3), dtype=np.uint8)
            self.assert_oracle(color, owners)
            # Exact RGB squared threshold on both sides of the density switch.
            color[:] = 0
            color[owners == 1] = [16, 16, 8]
            self.assert_oracle(color, owners)
            self.assert_oracle(255 - color, owners)

    def test_dense_owner_changes_avoid_coordinate_gathers(self):
        owners = (np.indices((64, 64)).sum(axis=0) % 2).astype(np.int32)
        color = np.zeros((64, 64, 3), dtype=np.uint8)
        color[owners == 1] = 255
        # This is a resource-shape guarantee, not a wall-time assertion.
        with patch('human_eye_plugin.attention_rendering.np.nonzero',
                   side_effect=AssertionError('dense path must not allocate coordinates')):
            self.assert_oracle(color, owners)

    def test_non_uint8_uses_original_fractional_and_wide_numeric_rules(self):
        owners = np.zeros((8, 8), dtype=np.int32)
        owners[:, 4:] = 1
        for dtype in (np.float32, np.float64, np.int16, np.uint16, np.int64):
            for level in (23.999, 24., 24.001, 300., 65535.):
                # 65535 is intentionally omitted for signed int16: these
                # fixtures test existing numeric semantics, not invalid casts.
                if dtype == np.int16 and level > np.iinfo(dtype).max:
                    continue
                with self.subTest(dtype=dtype, level=level):
                    color = np.zeros((8, 8, 3), dtype=dtype)
                    color[:, 4:, 0] = level
                    self.assert_oracle(color, owners)
        for level in (np.nan, np.inf, -np.inf):
            color = np.zeros((8, 8, 3), dtype=np.float64)
            color[:, 4:, 0] = level
            with np.errstate(invalid='ignore'):
                self.assert_oracle(color, owners)

    def test_unknown_and_empty_target_contract_is_unchanged(self):
        color = np.zeros((8, 8, 3), dtype=np.uint8)
        owners = np.full((8, 8), -1, dtype=np.int32)
        pixels = np.zeros((2, 2))
        for targets, error in (([], ValueError), (['unknown'], KeyError)):
            for function in (full_frame_oracle, _readability_evidence):
                with self.subTest(targets=targets, function=function.__name__):
                    with self.assertRaises(error):
                        function(color, owners, self.meshes, targets, pixels)
        self.assert_oracle(color, owners, ids=['object-0', 'object-0'])


if __name__ == '__main__':
    unittest.main()

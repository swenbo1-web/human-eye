"""Exact ROI annotation accounting against full-frame and frozen-v7 oracles.

Zero clocks exercise policy/evidence equivalence only, not delivery performance.
"""
import copy
import importlib.util
import inspect
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin import scene_rendering as rendering
from human_eye_plugin import visible_refill as refill
from verification.test_visible_refill_policy import bundle, priority_scene


def full_dilation(changed):
    result = changed.copy()
    result[:-1] |= changed[1:]
    result[1:] |= changed[:-1]
    result[:, :-1] |= changed[:, 1:]
    result[:, 1:] |= changed[:, :-1]
    return result


def frozen_v7():
    path = Path(__file__).resolve().parents[1] / (
        'verification/fixes/20261027_refill_budget_recovery/validation/'
        'candidate_runtime/human_eye_plugin/visible_refill.py')
    name = 'human_eye_plugin._pixel_region_frozen_v7'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


class RefillingPixelRegionTests(unittest.TestCase):
    def test_changed_neighborhood_matches_full_frame_at_edges_and_disjoint_regions(self):
        rng = np.random.default_rng(72931)
        for height, width in ((1, 1), (2, 3), (9, 13), (64, 64), (384, 384)):
            for _ in range(75):
                x0, x1 = sorted(rng.choice(width + 1, 2, replace=False))
                y0, y1 = sorted(rng.choice(height + 1, 2, replace=False))
                x0, x1, y0, y1 = map(int, (x0, x1, y0, y1))
                local = rng.random((y1-y0, x1-x0)) < .17
                changed = np.zeros((height, width), dtype=bool)
                changed[y0:y1, x0:x1] = local
                rx0, rx1 = sorted(rng.choice(width + 1, 2, replace=False))
                ry0, ry1 = sorted(rng.choice(height + 1, 2, replace=False))
                region = (slice(int(ry0), int(ry1)), slice(int(rx0), int(rx1)))
                actual = refill._changed_neighborhood_in_region(local, (x0, y0, x1, y1), region)
                np.testing.assert_array_equal(actual, full_dilation(changed)[region])

    def test_roi_surface_and_boundary_counts_match_independent_full_frame_arithmetic(self):
        rng = np.random.default_rng(89567)
        for _ in range(150):
            height, width = 31, 37
            owners = rng.integers(-1, 5, (height, width))
            usable = rng.random((height, width)) > .2
            source_region = (slice(3, 27), slice(4, 34))
            boundary = np.zeros((height, width), dtype=bool)
            boundary[source_region] = rng.random((24, 30)) > .7
            changed_box = (0, 2, 20, 31)
            changed_local = rng.random((29, 20)) < .1
            changed = np.zeros((height, width), dtype=bool)
            changed[2:31, :20] = changed_local
            target = owners == 2
            expected_surface = np.count_nonzero(usable & target & ~changed)
            expected_edges = np.count_nonzero(boundary & target & ~full_dilation(changed))
            actual_surface = np.count_nonzero(usable & target) - np.count_nonzero(
                changed_local & usable[2:31, :20] & target[2:31, :20])
            near = refill._changed_neighborhood_in_region(changed_local, changed_box, source_region)
            actual_edges = np.count_nonzero(boundary[source_region] & target[source_region] & ~near)
            self.assertEqual(actual_surface, expected_surface)
            self.assertEqual(actual_edges, expected_edges)

    def test_actual_fixtures_keep_frozen_v7_pixels_metadata_and_readability_counts(self):
        baseline = frozen_v7()
        receipt_fields = ('applied', 'status', 'reason', 'source_view_index', 'donor_object_id',
            'donor_reason', 'candidate_object_id', 'new_readable_object_ids',
            'candidate_readable_object_ids', 'readability', 'new_changed_pixels',
            'new_changed_foreground_pixels', 'core_new_changed_pixels',
            'actual_delivered_default_related_count')
        for size in (128, 256, 384, 512):
            for variant in ('standard', 'same_color', 'small_target'):
                with self.subTest(size=size, variant=variant), \
                     patch.object(refill, 'visible_refill_clock', return_value=0.), \
                     patch.object(baseline, 'visible_refill_clock', return_value=0.):
                    meshes = priority_scene()
                    if variant == 'same_color':
                        row = meshes[-1].to_dict()
                        row['color_rgb'] = meshes[1].to_dict()['color_rgb']
                        meshes[-1] = MeshEntity3D.from_dict(row)
                    elif variant == 'small_target':
                        row = meshes[-1].to_dict()
                        center = np.mean(row['vertices'], axis=0)
                        row['vertices'] = (center + (np.asarray(row['vertices']) - center) * .12).tolist()
                        meshes[-1] = MeshEntity3D.from_dict(row)
                    plan, pool = bundle(meshes)
                    current_args = {'scene_fingerprint': 'snapshot'}
                    if 'quad_size' in inspect.signature(refill.VisibleRefillCollector).parameters:
                        current_args['quad_size'] = size
                    current = refill.VisibleRefillCollector(plan, pool, **current_args)
                    previous = baseline.VisibleRefillCollector(plan, pool, scene_fingerprint='snapshot')

                    def observer(*parts):
                        current.observe_view(*parts)
                        previous.observe_view(*parts)

                    canvas, metadata = rendering._render_scene_canvas_impl(meshes, size,
                        focal_id='focus', reference_id='reference', label_plan=plan, raw_observer=observer)
                    before = copy.deepcopy(metadata)
                    new = current.finish(canvas, metadata, meshes, scene_fingerprint='snapshot', remaining_budget_ms=80.)
                    old = previous.finish(canvas, metadata, meshes, scene_fingerprint='snapshot', remaining_budget_ms=80.)
                    self.assertEqual(new[0].tobytes(), old[0].tobytes())
                    self.assertEqual(new[1], old[1])
                    self.assertEqual(metadata, before)
                    self.assertEqual({key: new[2].get(key) for key in receipt_fields},
                                     {key: old[2].get(key) for key in receipt_fields})


if __name__ == '__main__':
    unittest.main()

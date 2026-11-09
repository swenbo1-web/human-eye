"""Independent correctness and real arithmetic-work checks for decoder reuse.

Synthetic wire packets exercise the public codec directly; no Blender, model,
producer encoder, or private decoder cache representation is required.
"""
from __future__ import annotations

import builtins
import copy
import importlib.util
import math
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]


def load_codec():
    spec = importlib.util.spec_from_file_location(
        "independent_world_reuse_codec", ROOT / "human_eye_plugin/scene_residency.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def matrix(tx=0., ty=0., tz=0.):
    return [[1., 0., 0., tx], [0., 1., 0., ty], [0., 0., 1., tz], [0., 0., 0., 1.]]


def packet():
    return {
        "schema": "human-eye-scene-delta-v1",
        "capture": {
            "unit": "m", "coordinate_frame": "world", "source": "blender", "revision": "r1",
            "capture_state": dict(instance_id="worker-A", epoch=1, revision=1, selection_key="pair"),
            "meshes": [
                dict(object_id="A", name="Alpha", color_rgb=[1, 2, 3], is_focal_target=True,
                     _scene_resource=dict(id="local-A", revision=1, matrix=matrix(2., 3., 4.), scale=1.)),
                dict(object_id="B", name="Beta", color_rgb=[4, 5, 6], is_focal_target=False,
                     _scene_resource=dict(id="local-B", revision=1, matrix=matrix(-2., 0., 1.), scale=1.)),
            ],
        },
        "resources": [
            dict(id="local-A", revision=1, vertices_local=[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]],
                 faces=[[0, 1, 2]], edges=[[0, 1], [0, 2], [1, 2]]),
            dict(id="local-B", revision=1,
                 vertices_local=[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]],
                 faces=[[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]],
                 edges=[[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]]),
        ],
        "live_resources": ["local-A", "local-B"],
    }


def warm(full):
    result = copy.deepcopy(full)
    result["resources"] = []
    return result


def legacy_vertices(local, transform, scale):
    # The exact pre-optimization order: sum three products, add translation,
    # then scale; do not replace this with fsum, fma, or regrouped arithmetic.
    return [[(builtins.sum(transform[r][c] * p[c] for c in range(3))
              + transform[r][3]) * scale for r in range(3)] for p in local]


def float_bits(vertices):
    return [[struct.pack("!d", x) for x in point] for point in vertices]


class DecoderWorldReuseTests(unittest.TestCase):
    def setUp(self):
        self.module = load_codec()
        self.decoder = self.module.SceneDeltaDecoder()

    def apply_counted(self, value):
        calls = []

        def counted(values, start=0):
            calls.append(None)
            return builtins.sum(values, start)

        with patch.dict(self.module.__dict__, {"sum": counted}):
            result = self.decoder.apply(value)
        return result, len(calls)

    def totals(self):
        value = self.decoder.work_totals()
        self.assertEqual(set(value), {"world_transforms", "transformed_vertices"})
        self.assertTrue(all(type(v) is int and v >= 0 for v in value.values()))
        return value

    def test_cold_then_zero_resource_warm_has_zero_coordinate_sums(self):
        full = packet()
        initial, cold = self.apply_counted(full)
        self.assertEqual(cold, 3 * 7)
        before = self.totals()
        self.assertEqual(before, dict(world_transforms=2, transformed_vertices=7))
        again, hot = self.apply_counted(warm(full))
        self.assertEqual(again, initial)
        self.assertEqual(hot, 0)
        self.assertEqual(self.totals(), before)

    def test_metadata_only_update_is_fresh_without_geometry_arithmetic(self):
        full = packet()
        first, _ = self.apply_counted(full)
        changed = warm(full)
        changed["capture"]["revision"] = "r2"
        changed["capture"]["capture_state"]["revision"] = 2
        changed["capture"]["meshes"][0].update(name="Renamed", color_rgb=[9, 9, 9], is_focal_target=False)
        before = self.totals()
        result, calls = self.apply_counted(changed)
        self.assertEqual(calls, 0)
        self.assertEqual(result["meshes"][0]["name"], "Renamed")
        self.assertEqual(result["meshes"][0]["color_rgb"], [9, 9, 9])
        self.assertEqual(result["meshes"][0]["vertices"], first["meshes"][0]["vertices"])
        self.assertEqual(self.totals(), before)

    def test_pose_change_recomputes_only_changed_object(self):
        full = packet()
        self.decoder.apply(full)
        changed = warm(full)
        changed["capture"]["meshes"][0]["_scene_resource"]["matrix"][0][3] = 8.
        before = self.totals()
        result, calls = self.apply_counted(changed)
        self.assertEqual(calls, 3 * 3)
        self.assertEqual(result["meshes"][0]["vertices"][0], [8., 3., 4.])
        self.assertEqual(result["meshes"][1]["vertices"][0], [-2., 0., 1.])
        self.assertEqual(self.totals(), dict(world_transforms=before["world_transforms"] + 1,
                                          transformed_vertices=before["transformed_vertices"] + 3))

    def test_one_resource_revision_recomputes_only_its_vertices(self):
        full = packet()
        self.decoder.apply(full)
        changed = warm(full)
        resource = copy.deepcopy(full["resources"][1])
        resource["revision"] = 2
        resource["vertices_local"][0] = [0.25, 0., 0.]
        changed["resources"] = [resource]
        changed["capture"]["meshes"][1]["_scene_resource"]["revision"] = 2
        result, calls = self.apply_counted(changed)
        self.assertEqual(calls, 3 * 4)
        self.assertEqual(result["meshes"][1]["vertices"][0], [-1.75, 0., 1.])

    def test_repeated_payload_same_revision_still_overrides_previous_geometry(self):
        full = packet()
        self.decoder.apply(full)
        changed = warm(full)
        resource = copy.deepcopy(full["resources"][0])
        resource["vertices_local"][0] = [0.5, 0., 0.]
        changed["resources"] = [resource]
        result, calls = self.apply_counted(changed)
        self.assertEqual(calls, 3 * 3)
        self.assertEqual(result["meshes"][0]["vertices"][0], [2.5, 3., 4.])

    def test_unit_scale_changes_recompute_with_original_formula(self):
        full = packet()
        self.decoder.apply(full)
        changed = warm(full)
        for mesh in changed["capture"]["meshes"]:
            mesh["_scene_resource"]["scale"] = 0.01
        result, calls = self.apply_counted(changed)
        self.assertEqual(calls, 3 * 7)
        self.assertEqual(result["meshes"][0]["vertices"][0], [0.02, 0.03, 0.04])
        again, calls = self.apply_counted(changed)
        self.assertEqual(calls, 0)
        self.assertEqual(again, result)

    def test_instance_and_epoch_reset_do_not_share_old_world_cache(self):
        for field, value in (("instance_id", "worker-B"), ("epoch", 2)):
            with self.subTest(field=field):
                self.decoder = self.module.SceneDeltaDecoder()
                full = packet()
                self.decoder.apply(full)
                changed = copy.deepcopy(full)
                changed["capture"]["capture_state"][field] = value
                result, calls = self.apply_counted(changed)
                self.assertEqual(calls, 3 * 7)
                self.assertEqual(result["capture_state"][field], value)

    def test_selection_reorder_subset_and_return_preserve_live_resource_reuse(self):
        full = packet()
        first = self.decoder.apply(full)
        subset = warm(full)
        subset["capture"]["capture_state"]["selection_key"] = "A-only"
        subset["capture"]["meshes"] = subset["capture"]["meshes"][:1]
        _, calls = self.apply_counted(subset)
        self.assertEqual(calls, 0)
        restored = warm(full)
        restored["capture"]["capture_state"]["selection_key"] = "reverse-pair"
        restored["capture"]["meshes"].reverse()
        result, calls = self.apply_counted(restored)
        self.assertEqual(calls, 0)
        self.assertEqual(result["meshes"][0]["vertices"], first["meshes"][1]["vertices"])

    def test_deleted_resource_is_removed_and_reintroduced_geometry_is_not_stale(self):
        full = packet()
        self.decoder.apply(full)
        deleted = warm(full)
        deleted["capture"]["meshes"] = deleted["capture"]["meshes"][:1]
        deleted["live_resources"] = ["local-A"]
        self.decoder.apply(deleted)
        self.assertEqual(set(self.decoder.baseline()["resources"]), {"local-A"})
        restored = warm(full)
        changed = copy.deepcopy(full["resources"][1])
        changed["vertices_local"][0] = [0.75, 0., 0.]
        restored["resources"] = [changed]
        result, calls = self.apply_counted(restored)
        self.assertEqual(calls, 3 * 4)
        self.assertEqual(result["meshes"][1]["vertices"][0], [-1.25, 0., 1.])

    def test_mutable_returned_mesh_and_wire_cannot_poison_cached_geometry(self):
        full = packet()
        output = self.decoder.apply(full)
        output["meshes"][0]["vertices"][0][0] = -999.
        output["meshes"][0]["faces"][0][0] = 999
        full["resources"][0]["vertices_local"][0][0] = 999.
        good, calls = self.apply_counted(warm(packet()))
        self.assertEqual(calls, 0)
        self.assertEqual(good["meshes"][0]["vertices"][0], [2., 3., 4.])
        self.assertEqual(good["meshes"][0]["faces"], [[0, 1, 2]])

    def test_failure_after_first_mesh_does_not_commit_cache_baseline_or_work(self):
        full = packet()
        self.decoder.apply(full)
        baseline, totals = copy.deepcopy(self.decoder.baseline()), self.totals()
        bad = warm(full)
        bad["capture"]["meshes"][0]["_scene_resource"]["matrix"][0][3] = 19.
        bad["capture"]["meshes"][1]["_scene_resource"]["id"] = "missing-resource"
        with self.assertRaises(ValueError):
            self.apply_counted(bad)
        self.assertEqual(self.decoder.baseline(), baseline)
        self.assertEqual(self.totals(), totals)
        good = copy.deepcopy(bad)
        good["capture"]["meshes"][1]["_scene_resource"]["id"] = "local-B"
        result, calls = self.apply_counted(good)
        self.assertEqual(calls, 3 * 3)
        self.assertEqual(result["meshes"][0]["vertices"][0], [19., 3., 4.])

    def test_nonfinite_failure_does_not_replace_prior_valid_world_geometry(self):
        full = packet()
        before = self.decoder.apply(full)
        baseline, totals = copy.deepcopy(self.decoder.baseline()), self.totals()
        bad = warm(full)
        bad["capture"]["meshes"][0]["_scene_resource"]["matrix"][0][0] = math.inf
        with self.assertRaises(ValueError):
            self.decoder.apply(bad)
        self.assertEqual(self.decoder.baseline(), baseline)
        self.assertEqual(self.totals(), totals)
        again, calls = self.apply_counted(warm(full))
        self.assertEqual(calls, 0)
        self.assertEqual(again, before)

    def test_same_resource_multiple_poses_reuse_both_world_entries(self):
        full = packet()
        full["resources"] = full["resources"][:1]
        full["live_resources"] = ["local-A"]
        full["capture"]["meshes"][1]["_scene_resource"]["id"] = "local-A"
        initial, calls = self.apply_counted(full)
        self.assertEqual(calls, 3 * 3 * 2)
        again, calls = self.apply_counted(warm(full))
        self.assertEqual(calls, 0)
        self.assertEqual(initial, again)
        self.assertNotEqual(initial["meshes"][0]["vertices"], initial["meshes"][1]["vertices"])

    def test_float64_bits_match_legacy_order_for_cancellation_and_subnormals(self):
        cases = [
            ([[float(2**53), 1., -float(2**53)], [1e308, 1., -1e308], [1., -1., -0.]],
             [[1., 1., 1., 0.], [0., 0., 0., -0.], [1., -1., 0., 0.], [0., 0., 0., 1.]], 1.),
            ([[1e-300, -2e-300, 4e-300], [5e-324, -5e-324, 0.], [-5e-324, 0., 0.]],
             matrix(), 1e-20),
        ]
        for points, transform, scale in cases:
            with self.subTest(points=points[0]):
                self.decoder = self.module.SceneDeltaDecoder()
                full = packet()
                full["resources"] = full["resources"][:1]
                full["resources"][0]["vertices_local"] = points
                full["live_resources"] = ["local-A"]
                full["capture"]["meshes"] = full["capture"]["meshes"][:1]
                ref = full["capture"]["meshes"][0]["_scene_resource"]
                ref["matrix"], ref["scale"] = transform, scale
                expected = float_bits(legacy_vertices(points, transform, scale))
                result, calls = self.apply_counted(full)
                self.assertEqual(calls, 3 * len(points))
                self.assertEqual(float_bits(result["meshes"][0]["vertices"]), expected)
                result, calls = self.apply_counted(warm(full))
                self.assertEqual(calls, 0)
                self.assertEqual(float_bits(result["meshes"][0]["vertices"]), expected)

    def test_signed_zero_scale_does_not_alias_a_different_legacy_float64_result(self):
        # Real Blender scale_length is positive. The pre-existing public codec
        # also accepts finite zero scales; preserve its bits rather than using
        # Python's +0.0 == -0.0 as a sufficient cache identity.
        full = packet()
        full["capture"]["meshes"][0]["_scene_resource"]["scale"] = 0.0
        self.decoder.apply(full)
        changed = warm(full)
        reference = changed["capture"]["meshes"][0]["_scene_resource"]
        reference["scale"] = -0.0
        expected = legacy_vertices(full["resources"][0]["vertices_local"],
                                   reference["matrix"], reference["scale"])
        result, calls = self.apply_counted(changed)
        self.assertEqual(float_bits(result["meshes"][0]["vertices"]), float_bits(expected))
        self.assertEqual(calls, 3 * 3)


if __name__ == "__main__":
    unittest.main()

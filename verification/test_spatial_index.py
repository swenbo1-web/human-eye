"""Independent analytic AABB coverage, strict semantics and purpose budgets."""
import copy
import json
import math
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_module1_operators import MeshEntity3D, SE3AlignmentMath
from human_eye_plugin.geometry_safety import (COLLISION_TOLERANCE_M,
    measure_pair_geometry, solid_support_status, work_budget_status)
from human_eye_plugin.spatial_index import SpatialSceneIndex
from human_eye_plugin.scene_rendering import render_scene_canvas
from human_eye_plugin.attention_policy import AttentionPolicy
from verification.test_host_runtime import mesh


def box(identity, center, size=(1, 1, 1), focal=False):
    return MeshEntity3D.from_dict(mesh(identity, center, size, focal))


def sparse_scene(count=100):
    return [box("focal", [0, 0, 0], focal=True), box("reference", [0, 0, 1.01])] + [
        box("obstacle-" + str(i), [3 * i, 0, 0]) for i in range(1, count - 1)]


def analytic_box_gap(left, right):
    # Direct interval geometry, independent of the spatial index/SAT code.
    lo_a, hi_a = left.vertices.min(axis=0), left.vertices.max(axis=0)
    lo_b, hi_b = right.vertices.min(axis=0), right.vertices.max(axis=0)
    gap = [max(float(lo_b[k] - hi_a[k]), float(lo_a[k] - hi_b[k]), 0.) for k in range(3)]
    return math.sqrt(sum(value * value for value in gap))


def analytic_box_collision(left, right):
    lo_a, hi_a = left.vertices.min(axis=0), left.vertices.max(axis=0)
    lo_b, hi_b = right.vertices.min(axis=0), right.vertices.max(axis=0)
    return all(min(float(hi_a[k]), float(hi_b[k])) - max(float(lo_a[k]), float(lo_b[k]))
               > COLLISION_TOLERANCE_M for k in range(3))


def benchmark_spatial_index(*, repeats=12, counts=(10, 20, 100), include_dense=True):
    """Optional strict terminal-collision stage, not old/new production timing.

    The explicit full-scan reference ignores the legacy *global* scene budget
    but retains each pair's strict budget and evaluator. This distinction is
    essential for 100 objects, which legacy production refuses to process.
    New samples include index construction, validation of all solids, query,
    and strict selected pairs. Only collision classifications are compared;
    no exact far-object distances or observation bytes are compared. Inputs
    are rebuilt each sample to avoid giving
    the reference warmed mutable-mesh caches an unfair advantage.
    """
    if type(repeats) is not int or repeats < 2:
        raise ValueError("Use at least two benchmark repeats")
    reports = []
    cases = [(count, False) for count in counts]
    if include_dense:
        cases.append((20, True))
    for count, dense in cases:
        samples = {"full_scan_reference_ms": [], "indexed_ms": []}
        calls = {"full_scan_reference": [], "indexed": []}
        for sample in range(repeats + 1):
            # Alternate execution order to reduce simple warm/order bias.
            order = ("full_scan_reference", "indexed") if sample % 2 else ("indexed", "full_scan_reference")
            for mode in order:
                values = sparse_scene(count)
                if dense:
                    values = [box("focal", [0, 0, 0], focal=True), box("reference", [0, 0, .5])] + [
                        box("obstacle-" + str(i), [0, 0, 0]) for i in range(1, count - 1)]
                started = time.perf_counter_ns()
                if mode == "indexed":
                    plan = SpatialSceneIndex(values).query(values[0], force_ids=["reference"])
                    if not plan["supported"]:
                        raise AssertionError("Supported analytic fixture declined")
                    by_id = {value.object_id: value for value in values}
                    selected = [by_id[identity] for identity in plan["candidate_ids"]]
                else:
                    selected = values[1:]
                results = [measure_pair_geometry(values[0], other) for other in selected]
                elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
                if not all(result["measurement_valid"] for result in results):
                    raise AssertionError("Analytic fixture measurement failed")
                for other, result in zip(selected, results):
                    if result["is_penetrating"] != analytic_box_collision(values[0], other):
                        raise AssertionError("Strict classification differs from analytic box oracle")
                if sample:
                    samples[mode + "_ms"].append(elapsed_ms)
                    calls[mode].append(len(selected))
        reports.append({"objects": count, "scene_kind": "dense_overlapping" if dense else "sparse",
            "repeats_excluding_initial": repeats,
            "legacy_production_budget_accepts": work_budget_status(sparse_scene(count))["within_budget"],
            "scope": "strict_terminal_collision_full_scan_reference_vs_complete_aabb_plan",
            "compared_contract": "collision_classification_only_not_exact_clearance_or_observation_bytes",
            "samples": samples, "strict_pair_calls": calls,
            "percentiles": {mode: {"p50_ms": float(np.percentile(values, 50)),
                "p95_ms": float(np.percentile(values, 95)), "p99_ms": float(np.percentile(values, 99))}
                for mode, values in samples.items()}})
    return {"reference_kind": "explicit_pairwise_reference_not_legacy_production_on_rejected_scenes",
            "model_requests": 0, "provider_usage": None, "reports": reports}


class SpatialIndexCoverageTests(unittest.TestCase):
    def test_100_sparse_objects_have_complete_detached_nonexact_records(self):
        values = sparse_scene()
        index = SpatialSceneIndex(values, scene_fingerprint="snapshot")
        result = index.query(values[0], force_ids=["reference"])
        self.assertTrue(index.supported)
        self.assertTrue(result["supported"])
        self.assertEqual(result["candidate_ids"], ["reference"])
        self.assertEqual(len(result["separated_records"]), 98)
        self.assertEqual(result["coverage_object_count"], 99)
        self.assertEqual({row["object_id"] for row in result["pairs"]}, {m.object_id for m in values[1:]})
        by_id = {m.object_id: m for m in values}
        for row in result["pairs"]:
            self.assertLessEqual(row["clearance_lower_bound_m"], analytic_box_gap(values[0], by_id[row["object_id"]]))
            self.assertIsNone(row["signed_clearance_m"])
            self.assertIsNone(row["point_a_world"])
            self.assertFalse(row["measurement_valid"])
            self.assertFalse(row["clearance_exact"])
        self.assertEqual(result["query_pairs"], [["focal", "reference"]])
        json.dumps(result, allow_nan=False)

    def test_all_100_single_solids_are_validated_even_when_far_away(self):
        values = sparse_scene()
        with patch("human_eye_plugin.spatial_index.solid_support_status", wraps=solid_support_status) as check:
            index = SpatialSceneIndex(values)
        self.assertEqual(check.call_count, 100)
        self.assertEqual(len(index.support_status), 100)

    def test_dense_scene_has_all_obstacles_and_no_top_k_truncation(self):
        values = [box("focal", [0, 0, 0], focal=True)] + [box(str(i), [0, 0, 0]) for i in range(99)]
        result = SpatialSceneIndex(values).query(values[0])
        self.assertEqual(len(result["candidate_ids"]), 99)
        self.assertEqual(len(result["query_pairs"]), 99)
        self.assertEqual(result["separated_records"], [])

    def test_strict_collision_tolerance_sides_never_false_pruned(self):
        left = box("a", [0, 0, 0])
        for gap in (-.2, -50e-6, -2e-9, -.5e-9, 0., .5e-9, 2e-9, 1e-6, .1):
            right = box("b", [1 + gap, 0, 0])
            with self.subTest(gap=gap):
                result = SpatialSceneIndex([left, right]).query(left)
                expected = analytic_box_collision(left, right)
                strict = measure_pair_geometry(left, right)
                self.assertTrue(strict["measurement_valid"])
                self.assertEqual(strict["is_penetrating"], expected)
                if expected or gap == 0:
                    self.assertIn("b", result["candidate_ids"])
                for row in result["separated_records"]:
                    self.assertFalse(expected)
                    self.assertLessEqual(row["clearance_lower_bound_m"], analytic_box_gap(left, right))

    def test_face_edge_and_point_contacts_are_retained(self):
        left = box("a", [0, 0, 0])
        for center in ([1, 0, 0], [1, 1, 0], [1, 1, 1]):
            other = box("b", center)
            self.assertEqual(SpatialSceneIndex([left, other]).query(left)["candidate_ids"], ["b"])

    def test_rotated_crossing_rods_remain_candidates(self):
        left = box("a", [0, 0, 0], [2, .1, .1])
        right = box("b", [0, 0, 0], [2, .1, .1]).rotated_around_pivot(
            SE3AlignmentMath.euler_xyz_to_matrix(0, 0, 90))
        result = SpatialSceneIndex([left, right]).query(left)
        self.assertEqual(result["candidate_ids"], ["b"])
        self.assertTrue(measure_pair_geometry(left, right)["is_penetrating"])

    def test_overlapping_aabbs_of_separated_rotated_rods_are_not_called_clear(self):
        rotation = SE3AlignmentMath.euler_xyz_to_matrix(0, 0, 45)
        left = box("a", [0, 0, 0], [2, .1, .1]).rotated_around_pivot(rotation)
        right = box("b", [0, 0, 0], [2, .1, .1]).rotated_around_pivot(rotation).translated(
            [.2 / math.sqrt(2), -.2 / math.sqrt(2), 0])
        result = SpatialSceneIndex([left, right]).query(left)
        self.assertEqual(result["candidate_ids"], ["b"])
        self.assertFalse(result["pairs"][0]["collision_assessment_valid"])
        strict = measure_pair_geometry(left, right, need_clearance=True)
        self.assertFalse(strict["is_penetrating"])
        self.assertAlmostEqual(strict["signed_clearance_m"], .1, places=12)

    def test_candidate_focal_can_differ_from_original_indexed_focal(self):
        left, right = box("a", [0, 0, 0]), box("b", [3, 0, 0])
        index = SpatialSceneIndex([left, right])
        self.assertEqual(index.query(left)["candidate_ids"], [])
        candidate = left.translated([3, 0, 0])
        self.assertEqual(index.query(candidate)["candidate_ids"], ["b"])

    def test_independent_focal_identity_need_not_be_in_index(self):
        other = box("b", [0, 0, 0])
        query = box("new-focal", [0, 0, 0])
        result = SpatialSceneIndex([other]).query(query)
        self.assertEqual(result["candidate_ids"], ["b"])

    def test_observation_radius_and_force_reference_keep_complete_coverage(self):
        values = [box("a", [0, 0, 0]), box("near", [1.1, 0, 0]), box("reference", [10, 0, 0])]
        result = SpatialSceneIndex(values).query(values[0], max_distance_m=.2, force_ids=["reference"])
        self.assertEqual(result["candidate_ids"], ["near", "reference"])
        self.assertEqual(result["coverage_object_count"], 2)

    def test_large_world_offset_preserves_candidates_and_conservative_lower_bounds(self):
        for offset in (1e5, 1e9, 1e12):
            left = box("a", [offset, offset, offset])
            right = box("b", [offset + 1.1, offset, offset])
            result = SpatialSceneIndex([left, right]).query(left)
            # Existing support limits may decline an extreme offset. That
            # must retain the object, never invent a clear certificate.
            if not result["supported"]:
                self.assertIn("b", result["candidate_ids"])
            for row in result["separated_records"]:
                self.assertLessEqual(row["clearance_lower_bound_m"], analytic_box_gap(left, right))

    def test_dictionary_and_entity_inputs_have_same_support(self):
        values = sparse_scene(5)
        entity_index = SpatialSceneIndex(values)
        dict_index = SpatialSceneIndex([value.to_dict() for value in values])
        self.assertTrue(dict_index.supported)
        self.assertEqual(entity_index.query(values[0])["candidate_ids"], dict_index.query(values[0].to_dict())["candidate_ids"])

    def test_index_is_snapshot_immutable_and_returns_detached_support_records(self):
        left, right = box("a", [0, 0, 0]), box("b", [3, 0, 0])
        index = SpatialSceneIndex([left, right])
        right.vertices[:, 0] -= 3
        self.assertEqual(index.query(left)["candidate_ids"], [])
        self.assertEqual(SpatialSceneIndex([left, right]).query(left)["candidate_ids"], ["b"])
        status = index.support_status
        status["b"]["supported"] = False
        self.assertTrue(index.support_status["b"]["supported"])
        result = index.query(left)
        result["separated_records"][0]["clearance_lower_bound_m"] = -10
        self.assertGreaterEqual(index.query(left)["separated_records"][0]["clearance_lower_bound_m"], 0)

    def test_open_far_obstacle_is_validated_and_cannot_be_pruned_as_supported(self):
        left = box("a", [0, 0, 0])
        raw = box("open", [1000, 0, 0]).to_dict()
        raw["faces"] = raw["faces"][:-1]
        other = MeshEntity3D.from_dict(raw)
        index = SpatialSceneIndex([left, other])
        self.assertFalse(index.supported)
        self.assertFalse(index.support_status["open"]["supported"])
        result = index.query(left)
        self.assertFalse(result["supported"])
        self.assertIn("open", result["candidate_ids"])
        self.assertEqual(result["separated_records"], [])
        unknown = result['pairs'][0]
        self.assertFalse(unknown['collision_assessment_valid'])
        self.assertIsNone(unknown['is_penetrating'])
        self.assertIsNone(unknown['point_a_world'])
        self.assertIsNone(unknown['point_b_world'])

    def test_support_wrapper_ignores_mutable_callers_injected_shell_cache(self):
        item = box("open", [0, 0, 0]).to_dict()
        item["faces"] = item["faces"][:-1]
        other = MeshEntity3D.from_dict(item)
        token = other._compute_full_crc_token()
        other._certified_convex_shells = (token, [("forged support",)])
        self.assertFalse(solid_support_status(other)["supported"])

    def test_support_wrapper_does_not_cast_fractional_face_indices_into_valid_topology(self):
        item = box("fractional", [0, 0, 0]).to_dict()
        item["faces"][0][0] += .5
        self.assertFalse(solid_support_status(item)["supported"])

    def test_unsupported_query_focal_retains_every_obstacle(self):
        values = sparse_scene(10)
        raw = values[0].to_dict()
        raw["faces"] = raw["faces"][:-1]
        result = SpatialSceneIndex(values).query(MeshEntity3D.from_dict(raw))
        self.assertFalse(result["supported"])
        self.assertEqual(len(result["candidate_ids"]), 9)

    def test_budget_failure_is_unknown_before_support_kernel_or_vertex_allocation(self):
        huge = SimpleNamespace(object_id="huge", vertices=range(30_000), faces=range(60_000), edges=range(90_000))
        with patch("human_eye_plugin.geometry_safety._convex_shells", side_effect=AssertionError("No unbounded kernel")):
            status = solid_support_status(huge)
            index = SpatialSceneIndex([huge])
        self.assertFalse(status["supported"])
        self.assertEqual(status["reason"], "geometry_resource_limit")
        self.assertFalse(index.supported)
        result = index.query(box("focal", [0, 0, 0]))
        self.assertFalse(result["supported"])
        self.assertEqual(result["candidate_ids"], ["huge"])

    def test_uncertain_infinite_bounds_are_retained_without_nonfinite_json(self):
        values = [box("a", [0, 0, 0]), box("b", [3, 0, 0])]
        index = SpatialSceneIndex(values)
        # Simulate outward expansion reaching numeric range limits.
        index._lower = np.array([[-1., -1., -1.], [-np.inf, -1., -1.]])
        index._upper = np.array([[1., 1., 1.], [np.inf, 1., 1.]])
        result = index.query(values[0])
        self.assertIn("b", result["candidate_ids"])
        self.assertFalse(result["pairs"][0]["numeric_bound_valid"])
        json.dumps(result, allow_nan=False)

    def test_bad_query_options_and_bad_object_identity_are_rejected(self):
        values = sparse_scene(3)
        index = SpatialSceneIndex(values)
        for distance in (-1, True, float("nan"), float("inf"), "0"):
            with self.assertRaises(ValueError):
                index.query(values[0], max_distance_m=distance)
        for forced in (["unknown"], ["focal"], "reference", [1]):
            with self.assertRaises(ValueError):
                index.query(values[0], force_ids=forced)
        with self.assertRaises(ValueError):
            SpatialSceneIndex([values[0], values[0]])


class SpatialPurposeBudgetTests(unittest.TestCase):
    def test_default_100_box_budget_compatible_but_explicit_query_admits_actual_work(self):
        values = sparse_scene()
        original = work_budget_status(values)
        self.assertFalse(original["within_budget"])
        self.assertEqual(original["estimates"]["scene_work_elements"], 112_632_000)
        scoped = work_budget_status(values, query_pairs=[["focal", "reference"]])
        self.assertTrue(scoped["within_budget"])
        self.assertEqual(scoped["planned_pair_count"], 1)
        self.assertTrue(scoped["mesh_validation_included"])
        self.assertLess(scoped["estimates"]["scene_work_elements"], 40_000)

    def test_noncollision_purposes_do_not_allocate_or_charge_unrelated_pairs(self):
        values = sparse_scene()
        for purpose in ("mesh_validation", "render", "attention"):
            budget = work_budget_status(values, purpose=purpose)
            self.assertTrue(budget["within_budget"])
            self.assertEqual(budget["planned_pair_count"], 0)
            self.assertEqual(budget["estimates"]["largest_sat_projection_elements"], 0)

    def test_explicit_plan_validates_ids_repeated_pairs_and_purpose(self):
        values = sparse_scene(3)
        for pairs in ([["focal", "unknown"]], [["focal", "focal"]], [["focal"]], "focal",
                      [["focal", "reference"], ["reference", "focal"]]):
            with self.assertRaises(ValueError):
                work_budget_status(values, query_pairs=pairs)
        with self.assertRaises(ValueError):
            work_budget_status(values, query_pairs=[["focal", "reference"]], purpose="render")
        with self.assertRaises(ValueError):
            work_budget_status(values, purpose="unbounded")

    def test_empty_query_plan_still_charges_all_single_solid_validation(self):
        values = sparse_scene(10)
        budget = work_budget_status(values, query_pairs=[])
        self.assertEqual(budget["estimates"]["scene_work_elements"], 10 * 8 * 12)
        self.assertTrue(budget["mesh_validation_included"])

    def test_100_object_render_and_attention_are_not_blocked_by_sat_all_pairs(self):
        values = sparse_scene()
        image, metadata = render_scene_canvas(values, 64, focal_id="focal", reference_id="reference")
        self.assertEqual(image.size, (128, 128))
        self.assertTrue(metadata["work_budget"]["within_budget"])
        self.assertEqual(metadata["work_budget"]["purpose"], "render")
        proposal = AttentionPolicy().propose(values, focal_id="focal", reference_id="reference",
            contacts=[], quad_size=64, include_image=True, scene_fingerprint="fixture", now_s=0)
        self.assertNotIn("attention_geometry_budget_exceeded", proposal["reason_codes"])


class SpatialBenchmarkContractTests(unittest.TestCase):
    def test_strict_reference_compares_same_endpoint_collision_contract(self):
        report = benchmark_spatial_index(repeats=2, counts=(10,), include_dense=False)
        row = report["reports"][0]
        self.assertEqual(row["strict_pair_calls"]["full_scan_reference"], [9, 9])
        self.assertEqual(row["strict_pair_calls"]["indexed"], [1, 1])
        self.assertEqual(row["compared_contract"], "collision_classification_only_not_exact_clearance_or_observation_bytes")
        self.assertIsNone(report["provider_usage"])
        self.assertEqual(report["model_requests"], 0)

    def test_isolated_observation_fixture_is_deterministic_and_modes_change_only_expected_object(self):
        from verification.measure_spatial_index import make_scene, _percentiles
        static = make_scene(10, 3, "whole_cache")
        self.assertEqual(static, make_scene(10, 7, "whole_cache"))
        moved = make_scene(10, 3, "focal_move")
        self.assertNotEqual(moved["meshes"][0], static["meshes"][0])
        self.assertEqual(moved["meshes"][1:], static["meshes"][1:])
        unrelated = make_scene(10, 3, "unrelated_move")
        self.assertEqual(unrelated["meshes"][:-1], static["meshes"][:-1])
        self.assertNotEqual(unrelated["meshes"][-1], static["meshes"][-1])
        self.assertEqual(_percentiles([])["p95_ms"], None)
        self.assertAlmostEqual(_percentiles([1, 5, 9])["p95_ms"], 8.6)


if __name__ == "__main__":
    unittest.main()

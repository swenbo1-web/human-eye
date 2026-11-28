"""Focused convex task evidence checks with independent small geometry.

Prepared before the coordinated run. No Blender or model requests occur here.
"""
from decimal import Decimal, localcontext
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_module1_operators import submodule_1_4_spatial_sniffer as sniffer
from human_eye_plugin import geometry_safety as geometry
from human_eye_plugin.live_service import LiveSpatialService
from verification.perf030_002_cases import closed_counterexample, triangle_truth
from verification.test_concave_geometry import box, changed, ring
from verification.test_live_service import SelfLockingHost


def control_pair():
    return (box((0, 0, 0), (.1, .1, .1), "a"),
            box((.07, 0, 0), (.02, .02, .02), "b"))


def changed_control_target(target):
    vertices = target.vertices.copy()
    vertices[vertices[:, 0] > 0, 0] = .065
    return changed(target, vertices=vertices)


def large_world_pair():
    angle = .75
    rotation = np.array([[math.cos(angle), -math.sin(angle), 0],
                         [math.sin(angle), math.cos(angle), 0], [0, 0, 1.]])
    probe = box(identity="a")
    reference = box((0, 0, 0), (.12, .12, .03), "b")
    probe = changed(probe, vertices=probe.vertices @ rotation.T +
                    np.array([1e8 + .075, 1e8 + .075, 1e8]))
    reference = changed(reference, vertices=reference.vertices + 1e8)
    return probe, reference


def independent_corner_gap(probe, reference):
    """Exact represented XY corner-to-polygon distance, with overlapping Z."""
    corner = np.max(reference.vertices[:, :2], axis=0)
    if not (np.min(probe.vertices[:, :2], axis=0) > corner).all():
        raise AssertionError("The independent corner construction changed")
    with localcontext() as context:
        context.prec = 90
        point = [Decimal(float(value)) for value in corner]
        corners = [[Decimal(float(value)) for value in row]
                   for row in probe.vertices[:4, :2]]
        values = []
        for start, end in zip(corners, corners[1:] + corners[:1]):
            delta = [end[k] - start[k] for k in range(2)]
            offset = [point[k] - start[k] for k in range(2)]
            t = sum(offset[k] * delta[k] for k in range(2)) / sum(v * v for v in delta)
            t = max(Decimal(0), min(Decimal(1), t))
            values.append(sum((offset[k] - t * delta[k]) ** 2 for k in range(2)))
        return float(min(values).sqrt())


class GeometryTaskEvidenceTests(unittest.TestCase):
    def assert_original_witness(self, result, left, right, expected):
        self.assertTrue(result["measurement_valid"], result)
        self.assertAlmostEqual(result["signed_clearance_m"], expected, delta=1e-14)
        points = result["point_a_world"], result["point_b_world"]
        self.assertAlmostEqual(math.dist(*points), expected,
                               delta=geometry.COLLISION_TOLERANCE_M)
        for point, mesh in zip(points, (left, right)):
            error_sq = min(triangle_truth(point, mesh.vertices[face])["distance_sq"]
                           for face in mesh.faces)
            self.assertLessEqual(error_sq, geometry.COLLISION_TOLERANCE_M ** 2)

    def test_control_separation_and_swapped_original_witnesses(self):
        left, right = control_pair()
        for a, b, direction in ((left, right, [1, 0, 0]),
                                (right, left, [-1, 0, 0])):
            with self.subTest(focal=a.object_id):
                result = geometry.measure_pair_geometry(a, b, need_clearance=True,
                                                        need_witness=True)
                self.assert_original_witness(result, a, b, .01)
                delta = np.asarray(result["point_b_world"]) - result["point_a_world"]
                np.testing.assert_allclose(delta / np.linalg.norm(delta), direction,
                                           rtol=0, atol=1e-14)

    def test_rotated_non_axis_aligned_witness_has_independent_gap(self):
        rotation = np.array([[.6, -.8, 0], [.8, .6, 0], [0, 0, 1.]])
        left = box((0, 0, 0), (1, 1, 1), "a")
        right = box((1.2, 0, 0), (.4, .6, .8), "b")
        left = changed(left, vertices=left.vertices @ rotation.T)
        right = changed(right, vertices=right.vertices @ rotation.T)
        result = geometry.measure_pair_geometry(left, right, need_clearance=True,
                                                need_witness=True)
        self.assert_original_witness(result, left, right, .5)
        delta = np.asarray(result["point_b_world"]) - result["point_a_world"]
        np.testing.assert_allclose(delta / np.linalg.norm(delta), [.6, .8, 0],
                                   rtol=0, atol=1e-13)

    def test_unrequested_convex_witness_never_enters_witness_kernel(self):
        left, right = control_pair()
        with patch.object(geometry, "_surface_distance_with_witness",
                          side_effect=AssertionError("Unrequested witness traversal")), \
             patch.object(geometry, "_surface_distance", wraps=geometry._surface_distance) as scalar:
            gate = geometry.measure_pair_geometry(left, right)
            measured = geometry.measure_pair_geometry(left, right, need_clearance=True)
        self.assertTrue(gate["measurement_valid"])
        self.assertTrue(measured["measurement_valid"])
        self.assertEqual(scalar.call_count, 1)

    def test_requested_witness_replaces_one_full_scalar_traversal(self):
        left, right = control_pair()
        with patch.object(geometry, "_surface_distance",
                          side_effect=AssertionError("Duplicate scalar traversal")), \
             patch.object(geometry, "_surface_distance_with_witness",
                          wraps=geometry._surface_distance_with_witness) as witness:
            result = geometry.measure_pair_geometry(left, right, need_clearance=True,
                                                    need_witness=True)
        self.assertEqual(witness.call_count, 1)
        self.assert_original_witness(result, left, right, .01)

    def test_penetration_evidence_reuses_one_sat_metric_without_witness(self):
        left = box((0, 0, 0), (1, 1, 1), "a")
        right = box((.75, 0, 0), (1, 1, 1), "b")
        with patch.object(sniffer, "_sat_metric", wraps=sniffer._sat_metric) as metric, \
             patch.object(geometry, "_surface_distance_with_witness",
                          side_effect=AssertionError("Penetration witness traversal")):
            result = geometry.measure_pair_geometry(left, right, need_clearance=True,
                                                    need_relation_evidence=True)
        self.assertEqual(metric.call_count, 1)
        self.assertTrue(result["measurement_valid"], result)
        self.assertTrue(result["is_penetrating"])
        evidence = result["relation_evidence"]
        self.assertEqual(evidence["method"], "convex_sat")
        self.assertEqual(evidence["classification_tolerance_m"], geometry.COLLISION_TOLERANCE_M)
        self.assertTrue(evidence["zero_tolerance_is_penetrating"])
        self.assertAlmostEqual(evidence["escape_distance_m"], .25, delta=1e-14)
        np.testing.assert_allclose(evidence["escape_vector_a_world_m"], [-.25, 0, 0],
                                   rtol=0, atol=1e-14)
        self.assertEqual(evidence["escape_scope"],
                         "single_convex_sat_separating_translation_of_A_not_nearest_direction_or_global_minimum")
        self.assertFalse(evidence["world_apply_verified"])

    def test_relation_only_request_does_not_compute_surface_distance(self):
        left, right = control_pair()
        left = changed_control_target(left)
        with patch.object(geometry, "_surface_distance",
                          side_effect=AssertionError("Unrequested scalar traversal")), \
             patch.object(geometry, "_surface_distance_with_witness",
                          side_effect=AssertionError("Unrequested witness traversal")):
            result = geometry.measure_pair_geometry(left, right, need_relation_evidence=True)
        self.assertTrue(result["measurement_valid"], result)
        self.assertTrue(result["is_penetrating"])
        self.assertIsNone(result["signed_clearance_m"])
        self.assertIn("relation_evidence", result)

    def test_large_world_publication_failure_keeps_independent_scalar_and_relation(self):
        left, right = large_world_pair()
        expected = independent_corner_gap(left, right)
        with patch.object(geometry, "_surface_distance",
                          side_effect=AssertionError("Precision fallback double traversal")), \
             patch.object(geometry, "_surface_distance_with_witness",
                          wraps=geometry._surface_distance_with_witness) as witness:
            result = geometry.measure_pair_geometry(left, right, need_clearance=True,
                                                    need_witness=True, need_relation_evidence=True)
        self.assertEqual(witness.call_count, 1)
        self.assertTrue(result["measurement_valid"], result)
        self.assertFalse(result["is_penetrating"])
        self.assertAlmostEqual(result["signed_clearance_m"], expected, delta=1e-14)
        self.assertEqual(result["witness_reason"], "original_surface_witness_precision_exceeded")
        self.assertIsNone(result.get("point_a_world"))
        self.assertIsNone(result.get("point_b_world"))

    def test_orthogonal_hole_witness_remains_on_original_surfaces(self):
        left, right = box(), ring()
        result = geometry.measure_pair_geometry(left, right, need_clearance=True,
                                                need_witness=True)
        self.assert_original_witness(result, left, right, .019)
        wall = result["point_b_world"]
        self.assertLess(min(abs(abs(wall[0]) - .025), abs(abs(wall[1]) - .025)), 1e-14)

    def test_orthogonal_tiny_overlap_keeps_existing_strict_zero_semantics(self):
        from human_eye_plugin import orthogonal_solid
        overlap = 2.0 ** -32
        left = box((.019 + overlap, 0, 0), identity="a")
        right = ring()
        actual_overlap = float(np.max(left.vertices[:, 0]) - .025)
        self.assertGreater(actual_overlap, 0)
        self.assertLess(actual_overlap, geometry.COLLISION_TOLERANCE_M)
        with patch.object(geometry, "_surface_distance_with_witness",
                          side_effect=AssertionError("Orthogonal true overlap has no nearest points")), \
             patch.object(orthogonal_solid, "certified_orthogonal_collision",
                          wraps=orthogonal_solid.certified_orthogonal_collision) as classify:
            result = geometry.measure_pair_geometry(left, right, need_clearance=True,
                                                    need_witness=True)
        self.assertEqual(classify.call_count, 1)
        self.assertTrue(result["measurement_valid"], result)
        self.assertTrue(result["is_penetrating"])
        self.assertEqual(result["classification_tolerance_m"], 0)
        self.assertLess(result["signed_clearance_m"], 0)
        self.assertEqual(result["penetration_metric_scope"],
                         "certified_separating_translation_not_minimum_depth")
        self.assertIsNone(result.get("point_a_world"))
        self.assertIsNone(result.get("point_b_world"))
        self.assertEqual(result["witness_reason"], "no_surface_witness_for_escape_metric")

    def test_multi_component_witness_remains_on_original_triangles(self):
        left, right = closed_counterexample()
        result = geometry.measure_pair_geometry(left, right, need_clearance=True,
                                                need_witness=True)
        self.assert_original_witness(result, left, right, .25)


class CurrentTaskEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        config = self.base / "live.json"
        config.write_text(json.dumps({"schema_version": "1.0", "enabled": True,
            "project_root": str(Path(__file__).resolve().parents[1]), "quad_size": 64,
            "state_file": "state.json", "audit_file": "audit.jsonl"}), encoding="utf8")
        self.host = SelfLockingHost()
        self.set_pair(*control_pair())
        self.service = LiveSpatialService(config, host=self.host)

    def set_pair(self, left, right, revision="r1"):
        self.host.scene = {"revision": revision, "unit": "m", "coordinate_frame": "world",
                           "source": "task_complete_001_analytic",
                           "meshes": [left.to_dict(), right.to_dict()]}

    def observe(self, facts):
        return self.service.observe("task-complete", include_image=False,
            query={"mode": "task", "objects": [{"id": "a"}, {"id": "b"}],
                   "requested_facts": list(facts)})

    def work(self):
        events = [json.loads(line) for line in self.service.audit_path.read_text("utf8").splitlines()]
        return [event["task_work"] for event in events if event["event"] == "observe"][-1]

    def test_control_three_states_have_current_witness_or_sat_evidence(self):
        facts = ["surface_clearance", "solid_relation", "nearest_witness"]
        initial = self.observe(facts)
        again = self.observe(facts)
        self.assertEqual(initial["facts"], again["facts"])
        self.assertEqual(initial["binding"], again["binding"])
        self.assertEqual(again["facts"]["nearest_witness"]["status"], "measured")
        np.testing.assert_allclose(again["facts"]["nearest_witness"]["value"]["direction_a_to_b"],
                                   [1, 0, 0], rtol=0, atol=1e-14)
        self.assertEqual(self.work()["exact_pair_count"], 0)
        self.assertTrue(self.work()["pair_cache_hit"])
        left, right = control_pair()
        self.set_pair(changed_control_target(left), right, "r2")
        changed_result = self.observe(facts)
        self.assertNotEqual(changed_result["binding"]["scene_fingerprint"],
                            initial["binding"]["scene_fingerprint"])
        self.assertEqual(changed_result["binding"]["scene_revision"], "r2")
        self.assertEqual(changed_result["facts"]["solid_relation"]["value"], "penetrating")
        self.assertIn("evidence", changed_result["facts"]["solid_relation"])
        self.assertAlmostEqual(changed_result["facts"]["surface_clearance"]["value"], -.005, delta=1e-14)
        self.assertEqual(changed_result["facts"]["nearest_witness"]["reason"],
                         "no_surface_witness_for_escape_metric")
        self.assertEqual(self.work()["exact_pair_count"], 1)
        self.assertEqual(self.host.captures, 3)

    def test_scalar_then_witness_cache_demand_and_current_revision_binding(self):
        with patch("human_eye_plugin.task_query.measure_pair_geometry",
                   wraps=geometry.measure_pair_geometry) as measured:
            self.observe(["surface_clearance"])
            with_witness = self.observe(["surface_clearance", "nearest_witness"])
            self.assertFalse(self.work()["pair_cache_hit"])
            again = self.observe(["surface_clearance", "nearest_witness"])
            self.assertTrue(self.work()["pair_cache_hit"])
            self.assertEqual(measured.call_count, 2)
            self.host.scene["revision"] = "r2"
            current = self.observe(["surface_clearance", "nearest_witness"])
        self.assertEqual(measured.call_count, 2)
        self.assertEqual(with_witness["facts"], again["facts"])
        self.assertEqual(current["facts"], with_witness["facts"])
        self.assertEqual(current["binding"]["scene_revision"], "r2")
        self.assertNotEqual(current["binding"]["scene_fingerprint"],
                            with_witness["binding"]["scene_fingerprint"])

    def test_relation_evidence_demand_is_part_of_cache_key(self):
        left, right = control_pair()
        self.set_pair(changed_control_target(left), right)
        with patch("human_eye_plugin.task_query.measure_pair_geometry",
                   wraps=geometry.measure_pair_geometry) as measured:
            self.observe(["surface_clearance"])
            evidence = self.observe(["surface_clearance", "solid_relation"])
            self.assertFalse(self.work()["pair_cache_hit"])
            self.observe(["surface_clearance", "solid_relation"])
        self.assertEqual(measured.call_count, 2)
        self.assertTrue(self.work()["pair_cache_hit"])
        self.assertIn("evidence", evidence["facts"]["solid_relation"])

    def test_exact_touch_has_original_points_and_undefined_direction(self):
        self.set_pair(box((0, 0, 0), (1, 1, 1), "a"),
                      box((1, 0, 0), (1, 1, 1), "b"))
        result = self.observe(["surface_clearance", "solid_relation", "nearest_witness"])
        self.assertEqual(result["facts"]["surface_clearance"]["value"], 0)
        self.assertEqual(result["facts"]["solid_relation"]["value"], "not_penetrating")
        witness = result["facts"]["nearest_witness"]
        self.assertEqual(witness["status"], "measured")
        self.assertEqual(math.dist(witness["value"]["a"], witness["value"]["b"]), 0)
        self.assertIsNone(witness["value"]["direction_a_to_b"])
        self.assertEqual(witness["direction_reason"], "undefined_zero_distance")

    def test_tolerance_suppressed_true_overlap_never_gets_separation_witness(self):
        overlap = 2.0 ** -32
        self.set_pair(box((0, 0, 0), (1, 1, 1), "a"),
                      box((1 - overlap, 0, 0), (1, 1, 1), "b"))
        with patch.object(geometry, "_surface_distance_with_witness",
                          side_effect=AssertionError("True overlap is not a separation witness")):
            result = self.observe(["surface_clearance", "solid_relation", "nearest_witness"])
        self.assertEqual(result["facts"]["solid_relation"]["value"], "not_penetrating")
        self.assertEqual(result["facts"]["surface_clearance"]["value"], -overlap)
        self.assertTrue(result["facts"]["solid_relation"]["evidence"]["zero_tolerance_is_penetrating"])
        self.assertEqual(result["facts"]["nearest_witness"]["status"], "unknown")
        self.assertEqual(result["facts"]["nearest_witness"]["reason"],
                         "no_surface_witness_for_escape_metric")

    def test_precision_unknown_is_limited_to_requested_witness_fact(self):
        left, right = large_world_pair()
        self.set_pair(left, right)
        result = self.observe(["surface_clearance", "solid_relation", "nearest_witness"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["facts"]["surface_clearance"]["status"], "measured")
        self.assertAlmostEqual(result["facts"]["surface_clearance"]["value"],
                               independent_corner_gap(left, right), delta=1e-14)
        self.assertEqual(result["facts"]["solid_relation"]["value"], "not_penetrating")
        self.assertEqual(result["facts"]["nearest_witness"]["reason"],
                         "original_surface_witness_precision_exceeded")


if __name__ == "__main__":
    unittest.main()

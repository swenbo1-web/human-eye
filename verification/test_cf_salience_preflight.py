"""Portable CF-S preflight with a dense, independent deformation oracle."""

from itertools import combinations
import json
import unittest

import numpy as np

from human_eye_fast.fast_affordance_out import (
    AffordancePackage,
    DeformationFact,
    ObjectFact,
    ObservationFact,
    encode,
    public_schema,
)
from human_eye_fast.tensor_deform import compute_cross_frame_deformation_tensor
from verification.cf_salience_fixtures import (
    EVALUATION_FAMILIES,
    SEEDS,
    TRAIN_FAMILIES,
    bucket_chart,
    bucket_ids,
    build_fixture,
    fixture_manifest,
)


RAW_FIELDS = (
    "max_principal_stretch",
    "min_principal_stretch",
    "max_area_strain",
    "max_normal_angle_deg",
    "max_centroid_displacement",
)
LANES = ("stretch", "area", "normal", "displacement")
THRESHOLDS = dict(zip(LANES, (.01, .01, 1., .005), strict=True))
FACE_BUDGET = 6
BUCKET_BUDGET = 2
_CENTERED = np.array([[-1., -1., 0.], [1., -1., 0.], [0., 2., 0.]])
_TRAIN_ORDINALS = (0, 81, 162, 3)


def all_face_oracle(reference, current, triangles):
    """Compute every original row using QR/SVD and independent 3-D geometry."""
    rows = []
    for ids in triangles:
        old, new = reference[ids], current[ids]
        old_edges = (old[1:] - old[0]).T
        new_edges = (new[1:] - new[0]).T
        old_cross = np.cross(old_edges[:, 0], old_edges[:, 1])
        new_cross = np.cross(new_edges[:, 0], new_edges[:, 1])
        old_area = np.linalg.norm(old_cross)
        new_area = np.linalg.norm(new_cross)
        displacement = np.linalg.norm((new - old).mean(axis=0))
        if old_area == 0:
            rows.append((np.nan, np.nan, np.nan, np.nan, displacement))
            continue

        _, chart = np.linalg.qr(old_edges, mode="reduced")
        gradient = np.linalg.solve(chart.T, new_edges.T).T
        larger, smaller = np.linalg.svd(gradient, compute_uv=False)
        if new_area == 0:
            smaller = 0.
            angle = np.nan
        else:
            old_unit, new_unit = old_cross / old_area, new_cross / new_area
            cross_length = np.linalg.norm(np.cross(old_unit, new_unit))
            angle = np.degrees(np.arctan2(cross_length, np.dot(old_unit, new_unit)))
        rows.append((larger, smaller, abs(new_area / old_area - 1.), angle, displacement))
    columns = np.asarray(rows, dtype=float).reshape(-1, len(RAW_FIELDS))
    return dict(zip(RAW_FIELDS, columns.T, strict=True))


def lane_values(metrics, reference, triangles):
    """Rank physical lanes separately, with scale-free displacement selection."""
    stretch = np.maximum(metrics["max_principal_stretch"] - 1., 0.)
    indexed = reference[np.unique(triangles)]
    diagonal = np.linalg.norm(np.ptp(indexed, axis=0)) if len(indexed) else 0.
    displacement = metrics["max_centroid_displacement"]
    relative = displacement / (diagonal or 1.)
    return dict(zip(LANES, (stretch, metrics["max_area_strain"], metrics["max_normal_angle_deg"],
                           relative), strict=True))


def exact_ids(values, budget, *, floor):
    """Direct selection from complete current facts, ordered by value and ID."""
    eligible = np.flatnonzero(np.isfinite(values) & (values >= floor))
    order = np.lexsort((eligible, -values[eligible]))
    return eligible[order[:budget]]


def exact_buckets(buckets, face_ids, budget=BUCKET_BUDGET):
    """Independent oracle for the largest possible target coverage per query."""
    counts = np.bincount(buckets[face_ids], minlength=16)
    nonzero = np.flatnonzero(counts)
    order = np.lexsort((nonzero, -counts[nonzero]))
    return nonzero[order[:budget]], counts


def _translated_faces(count):
    centers = np.array([(4. * (i % 4), 5. * (i // 4), 0.) for i in range(count)])
    faces = np.arange(3 * count, dtype=np.int64).reshape(count, 3)
    return centers, (_CENTERED + centers[:, None, :]).reshape(-1, 3), faces


def _composite_case():
    centers, reference, faces = _translated_faces(9)
    current = reference.copy()
    # Distinct extrema in stretch, angle, and displacement. Six area-heavy
    # distractors all outscore them under the native composite TD score.
    current[faces[0]] = _CENTERED * [3., 1. / 3., 1.] + centers[0]
    cosine, sine = -.5, np.sqrt(3.) / 2
    rotation = np.array([[1., 0., 0.], [0., cosine, -sine], [0., sine, cosine]])
    current[faces[1]] = _CENTERED @ rotation.T + centers[1]
    current[faces[2]] += [0., 0., 3.]
    current[faces[3:]] = 2. * _CENTERED + centers[3:, None, :]
    return reference, current, faces


def _assert_td(reference, current, faces, budget=FACE_BUDGET):
    actual = compute_cross_frame_deformation_tensor(
        (current,), faces, reference_vertices=reference, top_k=budget
    )
    oracle = all_face_oracle(reference, current, faces)
    for field in RAW_FIELDS:
        np.testing.assert_allclose(actual[field], oracle[field], rtol=5e-11, atol=5e-12)
    return actual, oracle


def _train_results():
    specs = fixture_manifest(seed=SEEDS[0], split="train")
    rows = []
    for ordinal in _TRAIN_ORDINALS:
        fixture = build_fixture(specs[ordinal])
        actual, oracle = _assert_td(fixture.reference_m, fixture.current_m, fixture.triangles)
        bucket = bucket_ids(fixture.reference_m, fixture.triangles)
        direct = {}
        expected_lanes = lane_values(oracle, fixture.reference_m, fixture.triangles)
        for lane, values in lane_values(actual, fixture.reference_m, fixture.triangles).items():
            expected_values = expected_lanes[lane]
            # For mathematical ties, independent floating-point kernels can
            # place nearly equal IDs differently. Compare the ranked severities.
            ids = exact_ids(values, FACE_BUDGET, floor=THRESHOLDS[lane])
            expected = exact_ids(expected_values, FACE_BUDGET, floor=THRESHOLDS[lane])
            np.testing.assert_allclose(values[ids], expected_values[expected],
                                       rtol=5e-11, atol=5e-12)
            best, counts = exact_buckets(bucket, expected)
            direct[lane] = {
                "face_ids": ids.tolist(),
                "oracle_bucket_ids": best.tolist(),
                "oracle_bucket_hits": int(counts[best].sum()),
                "target_faces": int(len(expected)),
            }
        error = {}
        for field in RAW_FIELDS:
            finite = np.isfinite(oracle[field])
            error[field] = float(np.max(np.abs(actual[field][finite] - oracle[field][finite]),
                                        initial=0.))
        rows.append({
            "group_id": fixture.spec.group_id,
            "family": fixture.spec.family,
            "mechanism": fixture.spec.mechanism,
            "indexed_faces": int(len(fixture.triangles)),
            "nonempty_buckets": int(np.unique(bucket).size),
            "raw_metric_max_abs_error": error,
            "lanes": direct,
        })
    return rows


def _composite_result():
    reference, current, faces = _composite_case()
    actual, oracle = _assert_td(reference, current, faces)
    direct = {lane: exact_ids(values, 1, floor=THRESHOLDS[lane]).tolist()
              for lane, values in lane_values(oracle, reference, faces).items()}
    composite = actual["witness_triangle_ids"].tolist()
    return reference, current, faces, actual, direct, composite


def preflight_report():
    """Return machine-readable train-only and analytic evidence."""
    _, _, _, _, direct, composite = _composite_result()
    return {
        "train": _train_results(),
        "composite_counterexample": {
            "direct_metric_top_face_ids": direct,
            "native_composite_top_6": composite,
        },
    }


class SaliencePreflightTests(unittest.TestCase):
    def test_dense_td_oracle_and_direct_order_on_predeclared_train_families(self):
        rows = _train_results()
        self.assertEqual({row["family"] for row in rows}, set(TRAIN_FAMILIES))
        self.assertEqual([row["mechanism"] for row in rows], ["stretch", "dilate", "buckle", "drift"])

    def test_analytic_identity_area_preserving_stretch_turn_and_translation(self):
        reference, current, faces, actual, direct, composite = _composite_result()
        self.assertEqual(direct, {"stretch": [0], "area": [3], "normal": [1], "displacement": [2]})
        self.assertEqual(composite, list(range(3, 9)))
        np.testing.assert_allclose(actual["max_principal_stretch"][:3], [3., 1., 1.], atol=1e-14)
        np.testing.assert_allclose(actual["min_principal_stretch"][:3], [1. / 3., 1., 1.], atol=1e-14)
        np.testing.assert_allclose(actual["max_area_strain"][:3], [0., 0., 0.], atol=1e-14)
        np.testing.assert_allclose(actual["max_normal_angle_deg"][:3], [0., 120., 0.], atol=1e-12)
        np.testing.assert_allclose(actual["max_centroid_displacement"][:3], [0., 0., 3.], atol=1e-14)

        identity, _ = _assert_td(reference, reference, faces)
        for lane, values in lane_values(identity, reference, faces).items():
            self.assertEqual(exact_ids(values, FACE_BUDGET, floor=THRESHOLDS[lane]).tolist(), [])
        self.assertTrue(np.isfinite(current).all())

    def test_degenerate_reference_collapse_and_original_rows(self):
        valid = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
        line = np.array([[0., 0., 0.], [1., 0., 0.], [2., 0., 0.]])
        faces = np.arange(6).reshape(2, 3)
        reference = np.vstack((line, valid))
        current = np.vstack((line + [0., 0., 5.], line))
        actual, _ = _assert_td(reference, current, faces)
        self.assertTrue(np.isnan(actual["max_area_strain"][0]))
        self.assertEqual(actual["max_area_strain"][1], 1.)
        self.assertTrue(np.isnan(actual["max_normal_angle_deg"]).all())
        self.assertEqual(actual["min_principal_stretch"][1], 0.)
        self.assertEqual(exact_ids(actual["max_centroid_displacement"], 2, floor=1e-9).tolist(), [0, 1])
        self.assertEqual(exact_ids(actual["max_area_strain"], 2, floor=.01).tolist(), [1])

        coincident = np.zeros((3, 3))
        point = np.array([[0, 1, 2]])
        actual, oracle = _assert_td(coincident, coincident + [0., 0., .25], point)
        for metrics in (actual, oracle):
            lanes = lane_values(metrics, coincident, point)
            self.assertEqual(lanes["displacement"].tolist(), [.25])
            self.assertTrue(all(np.isnan(lanes[lane][0]) for lane in LANES[:3]))

    def test_current_exact_selection_maximizes_recall_and_value_at_budget(self):
        values = np.array([0., 1., 4., 4., 3., 2., np.nan])
        truth = set(exact_ids(values, 4, floor=1.))
        exact = exact_ids(values, 2, floor=1.)
        self.assertIn(1, exact_ids(values, FACE_BUDGET, floor=1.))
        self.assertEqual(exact.tolist(), [2, 3])
        self.assertEqual(len(set(exact) & truth), 2)
        for other in combinations(np.flatnonzero(np.isfinite(values)), 2):
            self.assertLessEqual(len(set(other) & truth), len(set(exact) & truth))
            self.assertLessEqual(values[list(other)].sum(), values[exact].sum())

    def test_bucket_oracle_maximizes_hit_count_and_preserves_id_tie(self):
        buckets = np.array([3, 5, 5, 3, 7, 7, 15], dtype=np.int8)
        target = np.arange(6)
        best, counts = exact_buckets(buckets, target)
        self.assertEqual(best.tolist(), [3, 5])
        self.assertEqual(counts[best].sum(), 4)
        for other in combinations(range(16), BUCKET_BUDGET):
            self.assertLessEqual(counts[list(other)].sum(), counts[best].sum())
        empty, _ = exact_buckets(buckets, target[:0])
        self.assertEqual(empty.size, 0)

    def test_pre_td_partial_samples_cannot_identify_unobserved_hotspot(self):
        centers = np.repeat(np.array([[0., 0., 0.], [8., 0., 0.], [16., 0., 0.]]), 5, axis=0)
        reference = (_CENTERED + centers[:, None, :]).reshape(-1, 3)
        faces = np.arange(len(reference)).reshape(-1, 3)
        buckets = bucket_ids(reference, faces)
        self.assertEqual(len(np.unique(buckets)), 3)
        # Each bucket has five identical centroids and disjoint vertex IDs.
        # The prescribed four-sample rule breaks each tie by original face ID.
        hidden_ids = (4, 9, 14)
        sampled_ids = np.setdiff1d(np.arange(len(faces)), hidden_ids)
        observed = reference[faces[sampled_ids]]
        distinct = set()
        for hidden in hidden_ids:
            current = reference.copy()
            current[faces[hidden]] = _CENTERED * [2., .5, 1.] + centers[hidden]
            np.testing.assert_array_equal(current[faces[sampled_ids]], observed)
            lane = lane_values(all_face_oracle(reference, current, faces), reference, faces)["stretch"]
            target = exact_ids(lane, 1, floor=THRESHOLDS["stretch"])
            self.assertEqual(target.tolist(), [hidden])
            distinct.update(buckets[target])
        # Identical observed vertices, reference, and undeformed history still
        # admit three different sole target buckets for a two-bucket budget.
        self.assertEqual(len(distinct), 3)
        self.assertGreater(len(distinct), BUCKET_BUDGET)

    def test_ao_keeps_composite_and_adds_explicit_metric_witnesses(self):
        _, current, faces, actual, direct, composite = _composite_result()
        selected = tuple(row[0] for row in direct.values())
        fact = DeformationFact("panel", 0, (1,), actual, faces, 1, current, selected)
        observation = ObservationFact("inspect", 1, (ObjectFact("panel", 1),), deformation=fact)
        schema = public_schema()["columns"]
        packet = dict(zip(schema["package"], json.loads(encode(AffordancePackage((observation,)))),
                          strict=True))
        record = dict(zip(schema["observation"], packet["observations"][0], strict=True))
        deformation = dict(zip(schema["deformation"], record["deformation"], strict=True))
        output = [dict(zip(schema["face"], row, strict=True)) for row in deformation["faces"]]
        self.assertEqual(deformation["top_face_ids"], composite)
        self.assertEqual([row["original_face_id"] for row in output], [*composite, 0, 1, 2])
        for row in output:
            face_id = row["original_face_id"]
            for field in RAW_FIELDS:
                self.assertEqual(row[field], actual[field][face_id])
            np.testing.assert_allclose(row["position_m"], current[faces[face_id]].mean(axis=0),
                                       atol=1e-14)

    def test_bucket_exact_boundaries_orphans_axis_ties_and_zero_span(self):
        reference = np.array([[0., 0., 0.], [4., 4., 0.], [1., 1., 0.], [2., 3., 0.],
                              [4., 0., 0.], [0., 4., 0.], [1e9, 1e10, 1e11]])
        faces = np.repeat(np.arange(6)[:, None], 3, axis=1)
        self.assertEqual(bucket_chart(reference, faces).axes, (0, 1))
        expected = [0, 15, 5, 11, 12, 3]
        np.testing.assert_array_equal(bucket_ids(reference, faces), expected)
        np.testing.assert_array_equal(bucket_ids(reference * 8, faces), expected)
        np.testing.assert_array_equal(bucket_ids(reference[:-1], faces), expected)
        line = reference * [0., 1., 0.]
        self.assertEqual(bucket_chart(line, faces).axes, (1, 0))
        np.testing.assert_array_equal(bucket_ids(line, faces), [0, 12, 4, 12, 0, 12])
        self.assertEqual(bucket_ids(reference, faces[:0]).size, 0)

    def test_reference_local_chart_and_topology_replacement(self):
        reference, current, faces = _composite_case()
        original = bucket_ids(reference, faces)
        permutation = (1, 2, 0)  # Proper 3-D rotation.
        translation = np.array([4., 2., 8.])
        world_reference = reference[:, permutation] * .125 + translation
        world_current = current[:, permutation] * .125 + translation
        # The chart inputs remain in the reference local frame.
        restored = ((world_reference - translation) * 8)[:, np.argsort(permutation)]
        np.testing.assert_array_equal(bucket_ids(restored, faces), original)
        baseline = all_face_oracle(reference, current, faces)
        transformed = all_face_oracle(world_reference, world_current, faces)
        for field in RAW_FIELDS[:-1]:
            np.testing.assert_allclose(transformed[field], baseline[field], atol=2e-13)
        field = RAW_FIELDS[-1]
        np.testing.assert_allclose(transformed[field] * 8, baseline[field], atol=2e-13)

        reference = np.array([[0., 0., 0.], [8., 2., 0.], [4., 1., 0.], [0., 2., 16.]])
        before = np.repeat(np.array([0, 1, 2])[:, None], 3, axis=1)
        after = np.repeat(np.array([0, 3, 2])[:, None], 3, axis=1)
        self.assertEqual(bucket_chart(reference, before).axes, (0, 1))
        self.assertEqual(bucket_chart(reference, after).axes, (2, 0))
        np.testing.assert_array_equal(bucket_ids(reference, before), [0, 15, 10])
        np.testing.assert_array_equal(bucket_ids(reference, after), [0, 12, 3])

    def test_frozen_specs_group_isolation_without_holdout_materialization(self):
        all_groups = set()
        for seed in SEEDS:
            train, validation, evaluation = (
                fixture_manifest(seed=seed, split=split)
                for split in ("train", "validation", "evaluation")
            )
            self.assertEqual((len(train), len(validation), len(evaluation)), (240, 60, 60))
            self.assertEqual({spec.family for spec in train}, set(TRAIN_FAMILIES))
            self.assertEqual({spec.family for spec in validation}, set(TRAIN_FAMILIES))
            self.assertEqual({spec.family for spec in evaluation}, set(EVALUATION_FAMILIES))
            groups = [{spec.group_id for spec in split} for split in (train, validation, evaluation)]
            for a, b in combinations(groups, 2):
                self.assertFalse(a & b)
            self.assertEqual(tuple(map(len, groups)), (240, 60, 60))
            diagnostic = fixture_manifest(seed=seed, split="diagnostic")
            diagnostic_ids = {spec.group_id for spec in diagnostic}
            self.assertEqual((len(diagnostic), len(diagnostic_ids)), (6, 3))
            self.assertEqual(len({spec.episode_id for spec in diagnostic}), 6)
            current_groups = set.union(*groups)
            self.assertFalse(current_groups & diagnostic_ids)
            self.assertFalse(all_groups & (current_groups | diagnostic_ids))
            all_groups.update(current_groups | diagnostic_ids)


if __name__ == "__main__":
    unittest.main()

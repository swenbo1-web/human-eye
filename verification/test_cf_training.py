"""Independent portable checks for frozen CF fitting and deployed state."""

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_fast import cerebellar_flash as runtime
from verification import cf_baselines as frozen
from verification import cf_training as training


def _samples(n):
    rng = np.random.default_rng(6)
    views = rng.random((n, 16, 5))
    views[..., 1] = 1
    safe = views[..., 2] > .5
    feedback = np.stack((safe, np.broadcast_to(np.arange(1, 17), (n, 16))), axis=-1)
    actions = rng.normal(size=(n, 23))
    actions[:, 2] = 1.
    scales = np.linspace(.01, .06, n)
    delta = (actions[:, 1] + .05 + .3 * actions[:, 6]) * scales
    return views, feedback, actions, scales, delta


def _view_validation(seed, rows):
    return {
        arm: [
            {"id": f"V-{seed}-validation-example-{i}", "family": i % 3,
             "rays": 10 if arm in ("F", "R") else 7, "success": True}
            for i in range(rows)
        ]
        for arm in training.VIEW_ARMS
    }


class FrozenTrainingTests(unittest.TestCase):
    def test_view_step_count_and_train_scaling(self):
        view, feedback, *_ = _samples(9)
        learned, = training.fit_view(view, feedback, (2,))
        transformed = view.reshape(-1, 5).copy()
        transformed[:, 2:] = np.log1p(transformed[:, 2:])
        mean = transformed.mean(axis=0)
        deviation = transformed.std(axis=0)
        deviation[deviation == 0] = 1.
        standardized = (transformed - mean) / deviation
        products = [standardized[:, j] * standardized[:, k]
                    for j in range(5) for k in range(j, 5)]
        x = np.column_stack((standardized, *products, np.ones(len(standardized))))
        np.testing.assert_allclose(learned.mean, mean, rtol=0., atol=1e-15)
        np.testing.assert_allclose(learned.scale, deviation, rtol=0., atol=1e-15)
        np.testing.assert_allclose(learned.design(view.reshape(-1, 5)), x, rtol=0., atol=1e-15)
        y = feedback[..., 0].ravel()
        regularization = .001
        rate = 1. / (.25 * np.linalg.norm(x, ord=2)**2 / len(y) + regularization)
        regularizer = np.r_[np.full(x.shape[1] - 1, regularization), 0.]
        w = np.zeros(x.shape[1])
        for _ in range(200):
            w -= rate * (x.T @ ((1. + np.exp(-x @ w))**-1 - y) / len(y) + regularizer * w)
        np.testing.assert_allclose(learned.weights, w, rtol=0., atol=4e-15)
        self.assertTrue(np.array_equal(runtime.sigmoid(np.array([-1000., 0., 1000.])),
                                       [0., .5, 1.]))

    def test_action_normal_equation_and_meter_prediction(self):
        _, _, keys, scales, measured = _samples(25)
        heads = training.fit_action(keys, scales, measured)
        for head, (quadratic, regularization) in zip(heads, training.CONFIGS, strict=True):
            self.assertEqual(head.quadratic, quadratic)
            x = head.design(keys)
            residual = measured / scales - keys[:, 1]
            penalty = regularization * np.r_[head.weights[:-1], 0.]
            np.testing.assert_allclose(x.T @ (x @ head.weights - residual) / len(x) + penalty,
                                       0., atol=2e-14)
            self.assertAlmostEqual(head.predict_delta(keys[0], scales[0]),
                                   (keys[0, 1] + x[0] @ head.weights) * scales[0], places=15)

    def test_native_validation_comparison_priorities_and_binding(self):
        rows = _view_validation(3, 6)
        rows["L0"][0].update(rays=1, success=False)
        for row in rows["L1"]:
            row["rays"] = 8
        selected, scores = training.select_view(rows)
        self.assertEqual(selected, 2)
        self.assertEqual(scores["L0"][:2], (1, 1))
        rows["L3"].reverse()
        with self.assertRaisesRegex(ValueError, "binding mismatch"):
            training.select_view(rows)
        _, _, keys, scales, _ = _samples(6)
        keys[:, 1] = 0
        labels = np.zeros(6)
        groups = [("set_shape_key", 1, 1)] * 6
        heads = training.fit_action(keys, scales, labels)
        constant = frozen.ConditionalConstant(groups, labels)
        self.assertEqual(training.select_action(heads, constant, keys, scales, labels, groups)[:2],
                         (0, "G"))

    def test_worker_receipts_and_session_isolation(self):
        seed, train_rows, validation_rows = 20261105, 8, 5
        root = Path(__file__).resolve().parents[1]
        scratch = (root / "artifacts" / "cf").resolve()
        self.assertTrue(scratch.is_relative_to(root))
        scratch.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="cf-training-test-", dir=scratch) as directory:
            d = Path(directory)
            vt, at, vv, av = (d / name for name in ("vt.npz", "at.npz", "vv.json", "av.npz"))
            candidates, snapshot, provenance = (d / name for name in
                                                ("fit.npz", "frozen.npz", "provenance.json"))
            view, feedback, keys, scales, measured = _samples(train_rows)
            np.savez(vt, keys=view, feedback=feedback)
            np.savez(at, keys=keys, scales=scales, labels_m=measured,
                     groups=np.tile(("set_shape_key", "1", "1"), (train_rows, 1)))
            vv.write_text(json.dumps(_view_validation(seed, validation_rows)), encoding="utf-8")
            np.savez(av, keys=keys[:validation_rows], scales=scales[:validation_rows],
                     labels_m=measured[:validation_rows],
                     groups=np.tile(("set_shape_key", "1", "1"), (validation_rows, 1)))
            ids = {name: [f"{prefix}-{seed}-train-example-{i}" for i in range(train_rows)]
                   for name, prefix in (("view", "V"), ("action", "A"))}
            provenance.write_text(json.dumps(ids), encoding="utf-8")
            with patch.multiple(training, TRAIN_ROWS=train_rows, VALIDATION_ROWS=validation_rows):
                fit = training.fit_worker(vt, at, candidates)
                self.assertEqual([Path(row["path"]).name for row in fit["actual_reads"]],
                                 ["vt.npz", "at.npz"])
                report = training.seal_worker(seed, candidates, vv, av, vt, at, snapshot,
                                              provenance=provenance)
            self.assertEqual(report["train_bank_rows"], ids)
            self.assertEqual(report["snapshot_sha256"], sha256(snapshot.read_bytes()).hexdigest())
            self.assertEqual(report["selection_sha256"],
                             sha256(snapshot.with_suffix(".selection.json").read_bytes()).hexdigest())
            self.assertEqual(set(report["shuffle_view_train_indices"]), set(range(train_rows)))
            self.assertEqual(set(report["shuffle_action_train_indices"]), set(range(train_rows)))
            saved = training.load_frozen(snapshot)
            self.assertEqual(saved.view_config, 0)
            zero = saved.session(view="zero")
            self.assertEqual(zero.rank_view(view[0], "L"), tuple(range(16)))
            zero.close()
            replay, learning = saved.session(), saved.session()
            np.testing.assert_array_equal(saved.banks.retrieval_scale, frozen.train_scale(view))
            self.assertEqual(replay.rank_view(view[0], "R"),
                             frozen.nearest_view_order(view[0], view, feedback, frozen.train_scale(view)))
            before_view = replay.view_head.weights.copy()
            before_action = replay.action_head.weights.copy()
            learning.learn_view(view[0], 2, True, 5)
            learning.learn_action(keys[0], scales[0], measured[0] + .01)
            self.assertFalse(np.array_equal(learning.view_head.weights, before_view))
            self.assertFalse(np.array_equal(learning.action_head.weights, before_action))
            np.testing.assert_array_equal(replay.view_head.weights, before_view)
            np.testing.assert_array_equal(replay.action_head.weights, before_action)
            self.assertEqual(len(learning.views), train_rows + 1)
            self.assertEqual(len(replay.views), train_rows)
            self.assertEqual(len(learning.actions), train_rows + 1)
            self.assertEqual(len(replay.actions), train_rows)
            self.assertEqual(np.flatnonzero(learning.views.known[train_rows]).tolist(), [2])
            pressure = training.capacity_check(saved)
            self.assertEqual(pressure["occupancy"], [[0, 0], [1, 1], [4096, 4096], [4096, 4096]])
            self.assertTrue(pressure["closed"] and pressure["session_isolation"])
            learning.close()
            replay.close()

    def test_bank_live_order_and_partial_feedback(self):
        session = runtime.CerebellarFlash(None, None, retrieval_scale=np.ones((16, 5)), capacity=2)
        key = np.zeros((16, 5))
        self.assertEqual(session.rank_view(key, "R"), tuple(range(16)))
        session.learn_view(key, 7, True, 9, update_model=False)
        session.learn_view(key, 2, True, 1, update_model=False)
        self.assertEqual(session.rank_view(key, "R")[:3], (7, 0, 1))
        session.learn_view(key, 3, False, 1, update_model=False)
        self.assertEqual(session.rank_view(key, "R")[:3], (2, 0, 1))
        session.learn_view(key, 4, False, 1, update_model=False)
        self.assertEqual(session.rank_view(key, "R"), (*range(3), *range(4, 16), 3))
        self.assertEqual(session.views.writes, 4)
        session.close()

    def test_runtime_feature_and_geometric_reference_equivalence(self):
        rng = np.random.default_rng(103)
        theta = np.arange(16) * (np.pi / 8)
        directions = np.column_stack((np.cos(theta), np.sin(theta), np.zeros(16)))
        faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
        a, b = np.array([0., 0., 0.]), np.array([0., 0., .003])
        for section in (False, True):
            for geometry in ((), ((rng.normal(size=(4, 3)), faces),)):
                expected = frozen.view_features(a, b, directions, geometry, section=section)
                actual = runtime.view_features(a, b, directions, geometry, section=section)
                np.testing.assert_allclose(actual, expected, rtol=8e-15, atol=2e-15)
        mesh = np.array([[-.03, -.01, 0.], [.03, -.01, 0.], [.03, .01, 0.], [-.03, .01, 0.]])
        for unit in (1., .001):
            moving = (unit * mesh, faces)
            reference = (unit * (mesh + b), faces)
            witness = SimpleNamespace(point_a=tuple(a), point_b=tuple(unit * b), triangle_a=0,
                                      triangle_b=0, distance_m=unit * b[-1])
            shape_basis = unit * rng.normal(scale=.01, size=mesh.shape)
            command_pairs = [
                (runtime.FiniteAction.shape_key(.4, .5, shape_basis),
                 frozen.FiniteAction.shape_key(.4, .5, shape_basis)),
                (runtime.FiniteAction.translation(unit * b / 3., tuple(a)),
                 frozen.FiniteAction.translation(unit * b / 3., tuple(a))),
            ]
            for actual_command, expected_command in command_pairs:
                x, meters = runtime.action_features(moving, reference, witness, actual_command)
                expected_x, expected_m = frozen.action_features(moving, reference, witness,
                                                                expected_command)
                np.testing.assert_allclose(x, expected_x, rtol=8e-15, atol=2e-15)
                self.assertAlmostEqual(meters, expected_m, places=15)
                self.assertAlmostEqual(runtime.geometry_delta(moving, reference, witness, actual_command),
                                       frozen.geometry_delta(moving, reference, witness, expected_command),
                                       places=15)


if __name__ == "__main__":
    unittest.main()

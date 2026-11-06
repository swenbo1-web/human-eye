"""Portable tests of the strict CF deployment startup boundary."""

from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np

from human_eye_fast.cerebellar_flash import EXPERIENCE_CAPACITY, FIXED_ORDER
from human_eye_fast.cf_deployment import CFDeployment, load_cf_deployment


def _fields(views=0, actions=0):
    return {
        "version": np.asarray(1, dtype=np.uint16),
        "v_mean": np.zeros(5), "v_scale": np.ones(5), "v_weights": np.zeros(6),
        "v_quadratic": np.asarray(False), "v_lambda": np.asarray(0.0),
        "a_mean": np.zeros(23), "a_scale": np.ones(23), "a_weights": np.zeros(300),
        "a_quadratic": np.asarray(True), "a_lambda": np.asarray(.05),
        "retrieval_scale": np.ones((16, 5)),
        "v_keys": np.zeros((views, 16, 5)), "v_values": np.zeros((views, 16, 2)),
        "v_known": np.zeros((views, 16), dtype=bool),
        "a_keys": np.zeros((actions, 23)), "a_values": np.zeros((actions, 1)),
        "a_known": np.zeros((actions, 1), dtype=bool),
    }


def _archive(fields):
    stream = BytesIO()
    np.savez(stream, **fields)
    stream.seek(0)
    return stream


class CFDeploymentTests(unittest.TestCase):
    def test_immutable_detached_parameters_and_explicit_file(self):
        data = _fields(views=2, actions=1)
        data["v_keys"][0, 0, 0] = 7.5
        data["v_known"][0, 2] = True
        direct = CFDeployment(**data)
        data["v_keys"].fill(15)
        self.assertEqual(direct.v_keys[0, 0, 0], 7.5)
        with self.assertRaises(FrozenInstanceError):
            direct.version = 2
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
            path = Path(folder) / "model.npz"
            path.write_bytes(_archive(data).getvalue())
            loaded = load_cf_deployment(path)
        for name, value in data.items():
            actual = getattr(loaded, name)
            np.testing.assert_array_equal(actual, value)
            if value.ndim:
                self.assertFalse(actual.flags.writeable)
                with self.assertRaises(ValueError):
                    actual.setflags(write=True)

    def test_empty_banks_and_independent_learning(self):
        deployment = CFDeployment(**_fields())
        first, second = deployment.session(), deployment.session()
        v_key, a_key = np.zeros((16, 5)), np.zeros(23)
        self.assertEqual(first.rank_view(v_key, "R"), FIXED_ORDER)
        self.assertEqual(first.predict_delta(a_key, .01), 0.0)
        first.learn_view(v_key, 7, True, 13)
        first.learn_action(a_key, .01, -.001)
        self.assertEqual(first.views.writes, 1)
        self.assertEqual(first.actions.writes, 1)
        self.assertEqual(first.rank_view(v_key, "R")[0], 7)
        self.assertNotEqual(first.predict_delta(a_key, .01), 0)
        self.assertEqual(second.views.writes, 0)
        self.assertEqual(second.actions.writes, 0)
        self.assertEqual(second.predict_delta(a_key, .01), 0.0)
        first.close()
        self.assertEqual(second.rank_view(v_key, "R"), FIXED_ORDER)

    def test_full_live_order_and_masks_survive_first_wrap(self):
        data = _fields(views=EXPERIENCE_CAPACITY, actions=3)
        for row, direction in enumerate((4, 5, 6)):
            data["v_values"][row, direction] = (1, 13)
            data["v_known"][row, direction] = True
        data["a_values"][:, 0] = (.1, .2, .3)
        data["a_known"][1, 0] = True
        deployment = CFDeployment(**data)
        session = deployment.session()
        self.assertEqual(session.views.writes, EXPERIENCE_CAPACITY)
        self.assertEqual(session.actions.writes, 3)
        np.testing.assert_array_equal(session.views.known, data["v_known"])
        np.testing.assert_array_equal(session.actions.values[:3], data["a_values"])
        np.testing.assert_array_equal(session.actions.known[:3], data["a_known"])
        query = data["v_keys"][0]
        self.assertEqual(session.rank_view(query, "R")[0], 4)
        session.learn_view(query, 9, True, 13, update_model=False)
        self.assertEqual(session.rank_view(query, "R")[0], 5)
        self.assertEqual(deployment.session().rank_view(query, "R")[0], 4)

    def test_rejects_invalid_version_shape_types_and_values(self):
        bad_inputs = (
            ("version", np.asarray(True)),
            ("version", np.asarray(1.0)),
            ("version", np.asarray(2)),
            ("version", np.asarray([1])),
            ("v_quadratic", np.asarray(0)),
            ("a_lambda", np.asarray(-1.0)),
            ("v_weights", np.zeros(21)),
            ("a_mean", np.zeros(23, dtype=np.float32)),
            ("a_weights", np.full(300, np.inf)),
            ("v_scale", np.zeros(5)),
            ("retrieval_scale", np.ones((5, 16))),
            ("v_keys", np.zeros((EXPERIENCE_CAPACITY + 1, 16, 5))),
            ("a_keys", np.zeros((3, 23))),
            ("a_known", np.zeros((0, 1), dtype=np.uint8)),
            ("a_values", np.asarray([], dtype=object)),
        )
        for name, value in bad_inputs:
            with self.subTest(name=name, shape=value.shape, dtype=value.dtype):
                with self.assertRaises(ValueError):
                    load_cf_deployment(_archive({**_fields(), name: value}))
        for label_and_rays in ((.5, 13), (1, -1), (0, 1.5)):
            with self.subTest(label_and_rays=label_and_rays):
                data = _fields(views=1)
                data["v_values"][0, 0] = label_and_rays
                data["v_known"][0, 0] = True
                with self.assertRaises(ValueError):
                    load_cf_deployment(_archive(data))

    def test_rejects_missing_extra_and_non_archive(self):
        missing = _fields()
        del missing["v_known"]
        for data in (missing, {**_fields(), "training": np.zeros(1)}):
            with self.assertRaises(ValueError):
                load_cf_deployment(_archive(data))
        stream = BytesIO()
        np.save(stream, np.asarray([1]))
        stream.seek(0)
        with self.assertRaises(ValueError):
            load_cf_deployment(stream)


if __name__ == "__main__":
    unittest.main()

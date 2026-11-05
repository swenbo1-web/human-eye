"""Exact wire equivalence and fresh-fact semantics of the AO refinement."""

import importlib.util
import json
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location('human_eye_fast.' + name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class EncodingRefinement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = load('verification/baselines/ao_implementation.py', '_test_ao_A')
        cls.r = load('verification/candidates/ao_streamlined.py', '_test_ao_R')

    def package(self, vertices, triangles, ids, extra=()):
        a = self.a
        count = len(triangles)
        values = np.array([0., -0., np.nan, np.inf, -np.inf, 1.0000000000000002,
                           1e-150, 1e150])[:count]
        metrics = {name: values.copy() for name in a._METRICS}
        metrics['witness_triangle_ids'] = np.asarray(ids, dtype=np.int32)
        fact = a.DeformationFact('对象😀\\"\n', 3, (7, 11, 19), metrics, triangles, 19, vertices, extra)
        observation = a.ObservationFact('观察\t', 19, (a.ObjectFact(fact.object_id, 2),), deformation=fact)
        return a.AffordancePackage((observation,))

    def test_single_and_multiface_exact_wire_across_scales_and_dtypes(self):
        rng = np.random.default_rng(42061)
        count = 0
        for dtype in (np.float64, np.float32):
            for scale, offset in ((1., 0.), (1e-6, 0.), (1., 1e6), (1e6, -1e9)):
                for faces in (0, 1, 2, 8):
                    vertices = (rng.normal(size=(3 * faces, 3)) * scale + offset).astype(dtype)
                    triangles = np.arange(3 * faces).reshape(-1, 3)
                    for ids, extra in (([], []), ([0] if faces else [], []),
                                       (list(range(faces)), [0, 0] if faces else [])):
                        package = self.package(vertices, triangles, ids, extra)
                        self.assertEqual(self.a.encode(package), self.r.encode(package))
                        count += 1
        self.assertEqual(count, 96)

    def test_fresh_calls_reflect_mutated_facts_and_old_bytes_stay_frozen(self):
        vertices = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
        package = self.package(vertices, np.array([[0, 1, 2]]), [0])
        old = self.r.encode(package)
        parsed = json.loads(old)
        vertices += (2., 3., 4.)
        current = self.r.encode(package)
        self.assertNotEqual(old, current)
        self.assertEqual(current, self.a.encode(package))
        self.assertEqual(parsed, json.loads(old))

    def test_schema_and_signed_zero_are_preserved(self):
        self.assertEqual(self.a.public_schema(), self.r.public_schema())
        self.assertEqual(self.a._json_bytes([-0.0, 0.0, '中文😀\n\\"']),
                         self.r._json_bytes([-0.0, 0.0, '中文😀\n\\"']))
        self.assertIn(b'-0.0', self.r._json_bytes([-0.0]))
        for value in (float('nan'), float('inf'), -float('inf')):
            with self.assertRaises(ValueError): self.r._json_bytes([value])


if __name__ == '__main__':
    unittest.main()

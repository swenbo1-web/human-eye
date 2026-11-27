"""Kernel-041 targeted regression and negative-control suite (K01-K07).

Self-contained (no scratch paths required) so CI and experiment branches can run directly via unittest.
"""
from __future__ import annotations

from fractions import Fraction
import json
import math
from pathlib import Path
import sys
import tracemalloc
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks import bvh_eval
from benchmarks import run_ablation_and_assets as raa
from benchmarks import verify_review_suite as vrs
from human_eye_plugin import surface_geometry as sg
from human_eye_plugin import surface_proximity as sp
from verification import m3_asset_cases as mac


NOOP = bvh_eval.NOOP


def _freeze(oid: str, verts, faces):
    return SimpleNamespace(
        object_id=oid,
        name=oid,
        vertices=tuple(tuple(float(c) for c in p) for p in verts),
        faces=tuple(tuple(int(i) for i in f) for f in faces),
    )


def _tilted_plate(nx: int, z_off: float, reverse: bool = False):
    ca, sa = math.cos(0.6), math.sin(0.6)

    def rot(p):
        x, y, z = p
        x1, z1 = ca * x + sa * z, -sa * x + ca * z
        y2, z2 = ca * y - sa * z1, sa * y + ca * z1
        return [x1, y2, z2]

    verts, faces = [], []
    for i in range(nx):
        for j in range(4):
            b = len(verts)
            x, y = i * 0.4, j * 0.4
            verts.extend([rot([x, y, z_off]), rot([x + 0.3, y, z_off]), rot([x, y + 0.3, z_off])])
            faces.append([b, b + 1, b + 2])
    if reverse:
        faces = list(reversed(faces))
    return verts, faces


def _box_mesh(oid: str, origin, size, subdiv: int = 1, *, as_tuples: bool = True):
    ox, oy, oz = origin
    sx, sy, sz = size
    verts = []
    idx = {}

    def vid(ix, iy, iz):
        key = (ix, iy, iz)
        if key not in idx:
            idx[key] = len(verts)
            verts.append((
                float(ox + sx * ix / subdiv),
                float(oy + sy * iy / subdiv),
                float(oz + sz * iz / subdiv),
            ))
        return idx[key]

    faces = []
    # Six faces of [0, subdiv]^3, outward oriented
    for u in range(subdiv):
        for v in range(subdiv):
            # -Z, +Z
            a, b, c, d = vid(u, v, 0), vid(u + 1, v, 0), vid(u + 1, v + 1, 0), vid(u, v + 1, 0)
            faces.extend([(a, c, b), (a, d, c)])
            a, b, c, d = vid(u, v, subdiv), vid(u + 1, v, subdiv), vid(u + 1, v + 1, subdiv), vid(u, v + 1, subdiv)
            faces.extend([(a, b, c), (a, c, d)])
            # -Y, +Y
            a, b, c, d = vid(u, 0, v), vid(u + 1, 0, v), vid(u + 1, 0, v + 1), vid(u, 0, v + 1)
            faces.extend([(a, b, c), (a, c, d)])
            a, b, c, d = vid(u, subdiv, v), vid(u + 1, subdiv, v), vid(u + 1, subdiv, v + 1), vid(u, subdiv, v + 1)
            faces.extend([(a, c, b), (a, d, c)])
            # -X, +X
            a, b, c, d = vid(0, u, v), vid(0, u + 1, v), vid(0, u + 1, v + 1), vid(0, u, v + 1)
            faces.extend([(a, c, b), (a, d, c)])
            a, b, c, d = vid(subdiv, u, v), vid(subdiv, u + 1, v), vid(subdiv, u + 1, v + 1), vid(subdiv, u, v + 1)
            faces.extend([(a, b, c), (a, c, d)])
    if as_tuples:
        return SimpleNamespace(object_id=oid, name=oid, vertices=tuple(verts), faces=tuple(faces))
    return SimpleNamespace(object_id=oid, name=oid, vertices=[list(p) for p in verts], faces=[list(f) for f in faces])


class _TrapVertsArray:
    """Array-like wrapper around a real ndarray that fails if bulk .tolist() is invoked on vertices."""

    def __init__(self, arr: np.ndarray):
        self._arr = arr
        self.full_tolist_calls = 0
        self.shape = arr.shape
        self.ndim = arr.ndim
        self.dtype = arr.dtype
        self.base = arr.base
        self.flags = arr.flags

    def __len__(self):
        return len(self._arr)

    def __getitem__(self, idx):
        return self._arr[idx]

    def item(self, idx):
        return self._arr.item(idx)

    def tolist(self):
        self.full_tolist_calls += 1
        raise AssertionError("K01 violation: bulk vertex array .tolist() was called")


class TestK01ReferencedGeometryAndBoundedPrep(unittest.TestCase):
    def test_040_nine_row_trap_uncached_and_cached(self):
        arr_a = np.full((9, 3), np.nan, dtype=np.float64)
        arr_a[0] = [0.0, 0.0, 0.0]
        arr_a[4] = [1.0, 0.0, 0.0]
        arr_a[8] = [0.0, 1.0, 0.0]
        arr_b = np.full((9, 3), np.inf, dtype=np.float64)
        arr_b[1] = [0.0, 0.0, 1.0]
        arr_b[5] = [1.0, 0.0, 1.0]
        arr_b[7] = [0.0, 1.0, 1.0]

        trap_a = _TrapVertsArray(arr_a)
        trap_b = _TrapVertsArray(arr_b)
        fa = np.asarray([(0, 4, 8)] * 17, dtype=np.int32)
        fb = np.asarray([(1, 5, 7)] * 17, dtype=np.int32)
        # Patch _is_numpy_2d_vertices lightly only to let _TrapVertsArray reach the same item/row reader
        real_is_np = sp._is_numpy_2d_vertices
        with patch.object(sp, "_is_numpy_2d_vertices", lambda v: isinstance(v, _TrapVertsArray) or real_is_np(v)):
            ma = SimpleNamespace(object_id="trap_a", name="trap_a", vertices=trap_a, faces=fa)
            mb = SimpleNamespace(object_id="trap_b", name="trap_b", vertices=trap_b, faces=fb)
            r_nc = sp.measure_surface_proximity(ma, mb, NOOP, retain_exact_rank=True)
            r_c = sp.measure_surface_proximity(ma, mb, NOOP, retain_exact_rank=True, _mesh_cache={})
        self.assertEqual(trap_a.full_tolist_calls, 0)
        self.assertEqual(trap_b.full_tolist_calls, 0)
        self.assertTrue(r_nc["measurement_valid"])
        self.assertTrue(r_c["measurement_valid"])
        self.assertEqual(r_nc["distance_m"], 1.0)
        self.assertEqual(r_c["distance_m"], 1.0)
        self.assertEqual(r_nc["work"]["referenced_vertices"], 6)

    def test_large_loose_nan_tail_and_noncontiguous_ndarray_flat_memory(self):
        peaks = {}
        for n_rows in (10, 1_000, 100_000):
            raw_a = np.full((n_rows * 2, 3), np.nan, dtype=np.float64)
            arr_a = raw_a[::2]  # non-contiguous stride
            arr_a[1] = [0.0, 0.0, 0.0]
            arr_a[n_rows // 2] = [1.0, 0.0, 0.0]
            arr_a[-1] = [0.0, 1.0, 0.0]

            raw_b = np.full((n_rows * 2, 3), np.inf, dtype=np.float64)
            arr_b = raw_b[::2]
            arr_b[0] = [0.0, 0.0, 2.0]
            arr_b[n_rows // 3] = [1.0, 0.0, 2.0]
            arr_b[-2] = [0.0, 1.0, 2.0]

            ma = SimpleNamespace(object_id="na", name="na", vertices=arr_a, faces=[(1, n_rows // 2, n_rows - 1)])
            mb = SimpleNamespace(object_id="nb", name="nb", vertices=arr_b, faces=[(0, n_rows // 3, n_rows - 2)])

            orig_to = sp._numpy_2d_list
            calls = []
            def spy_to(a, kinds=('f', 'i', 'u'), _o=orig_to):
                calls.append(getattr(a, "shape", None))
                return _o(a, kinds)
            tracemalloc.start()
            try:
                with patch.object(sp, "_numpy_2d_list", spy_to):
                    res = sp.measure_surface_proximity(ma, mb, NOOP, retain_exact_rank=True)
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()

            self.assertTrue(res["measurement_valid"])
            self.assertEqual(res["distance_m"], 2.0)
            self.assertEqual(res["work"]["referenced_vertices"], 6)
            # Only small face buffer conversion allowed; huge vertex buffers must not call _numpy_2d_list
            self.assertEqual([s for s in calls if s and s[0] > 3], [])
            peaks[n_rows] = peak

        self.assertLess(peaks[100_000], 64 * 1024, peaks)
        # Verify referenced NaN still fails cleanly
        bad = np.array([[0.0, np.nan, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float64)
        good = np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0]], dtype=np.float64)
        r_bad = sp.measure_surface_proximity(
            SimpleNamespace(object_id="ba", name="ba", vertices=bad, faces=[(0, 1, 2)]),
            SimpleNamespace(object_id="bg", name="bg", vertices=good, faces=[(0, 1, 2)]),
            NOOP,
        )
        self.assertFalse(r_bad["measurement_valid"])

    def test_mid_prep_cancellation_does_not_commit_cache(self):
        class _Cancel(RuntimeError):
            pass

        tv, tf = _tilted_plate(8, 0.0)
        ma = _freeze("ca", tv, tf)
        mb = _freeze("cb", [[p[0], p[1], p[2] + 0.5] for p in tv], tf)
        stage_forbidden = {
            "surface_proximity_validated_faces": ("admission", "frame", "local_tris", "tree"),
            "surface_proximity_referenced_vertices": ("frame", "local_tris", "tree"),
            "surface_proximity_triangle_prepare": ("local_tris", "tree"),
            "surface_proximity_surface_bvh_build": ("tree",),
        }
        for st, forbidden_keys in stage_forbidden.items():
            cache = {}
            seen = 0
            def cp(stage, target=st):
                nonlocal seen
                if stage == target:
                    seen += 1
                    if seen == 4:
                        raise _Cancel(stage)
            with self.assertRaises(_Cancel):
                sp.measure_surface_proximity(ma, mb, cp, _mesh_cache=cache)
            if st == "surface_proximity_validated_faces":
                self.assertEqual(len(cache), 0)
            else:
                for ent in cache.values():
                    if "tree" in forbidden_keys:
                        self.assertNotIn("tree", ent)
                    if "frame" in forbidden_keys:
                        self.assertNotIn("frame", ent)
                    if "local_tris" in forbidden_keys:
                        self.assertNotIn("local_tris", ent)
            # Clean retry with the exact same cache dict MUST produce exact parity with uncached
            r_uncached = sp.measure_surface_proximity(ma, mb, NOOP, retain_exact_rank=True)
            r_retry = sp.measure_surface_proximity(ma, mb, NOOP, retain_exact_rank=True, _mesh_cache=cache)
            self.assertEqual(bvh_eval._surface_sig(r_uncached), bvh_eval._surface_sig(r_retry))


class TestK02SettledCreditAndBudgetSemantics(unittest.TestCase):
    def test_credit_ledger_identity_and_interval_threshold_preservation(self):
        tl, tr = _tilted_plate(12, 0.0), _tilted_plate(12, 0.5, reverse=True)
        ml, mr = _freeze("tl", *tl), _freeze("tr", *tr)
        r_on = sp.measure_surface_proximity(ml, mr, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        w = r_on["work"]
        self.assertEqual(
            w["witness_projection_credit_balance"],
            w["witness_projection_credit_node_units"]
            + w["witness_projection_credit_narrow_units"]
            + w["witness_projection_credit_node_prune_units"]
            - w["witness_projection_credit_spent_units"],
        )
        self.assertGreaterEqual(w["witness_projection_credit_balance"], 0)
        self.assertLessEqual(w["witness_projection_credit_spent_units"],
                             w["witness_projection_credit_node_units"]
                             + w["witness_projection_credit_narrow_units"]
                             + w["witness_projection_credit_node_prune_units"])

        # Local interval threshold sweep relative to OFF min completion budget (delta 0..32 -> 0 holes)
        with patch.object(sp._FastWitnessProjection, "build", classmethod(lambda cls, *a, **kw: None)):
            m_off = sp.measure_surface_proximity(ml, mr, NOOP, retain_exact_rank=True)["work"]["work_units"]
        sv, sf = mac.sheet(17)
        sp_l = vrs._freeze_mesh("sp_l", sv, sf)
        sp_r = vrs._freeze_mesh("sp_r", [[p[0], p[1], p[2] + 5e-6] for p in sv], sf)
        with patch.object(sp._FastWitnessProjection, "build", classmethod(lambda cls, *a, **kw: None)):
            m_off_sheet = sp.measure_surface_proximity(sp_l, sp_r, NOOP, retain_exact_rank=True)["work"]["work_units"]

        orig_init = sp._Work.__init__
        for label, a_m, b_m, base_off in (("tilted48", ml, mr, m_off), ("sheet_5um", sp_l, sp_r, m_off_sheet)):
            for delta in (0, 1, 2, 4, 8, 16, 32):
                def pinit(inst, cp, diag, init_w=sp.MAX_WORK_UNITS - (base_off + delta)):
                    orig_init(inst, cp, diag)
                    inst.counts["work_units"] = init_w
                with patch.object(sp._Work, "__init__", pinit):
                    ro = sp.measure_surface_proximity(a_m, b_m, NOOP, retain_exact_rank=True)
                self.assertTrue(ro["measurement_valid"], (label, delta, ro.get("reason")))
                self.assertLessEqual(ro["work"]["work_units"], sp.MAX_WORK_UNITS)

    def test_failed_proof_debits_actual_work_no_refund_and_no_retry(self):
        ml, mr = _freeze("tl", *_tilted_plate(12, 0.0)), _freeze("tr", *_tilted_plate(12, 0.5, reverse=True))
        with patch.object(sp, "_fast_descriptor_direction", return_value=None):
            res = sp.measure_surface_proximity(ml, mr, NOOP, retain_exact_rank=True)
        self.assertTrue(res["measurement_valid"])
        w = res["work"]
        self.assertEqual(w.get("witness_projection_direction_builds", 0), 1)
        self.assertEqual(w.get("witness_projection_directions", 0), 0)
        self.assertEqual(w["witness_projection_credit_spent_units"], 8)

    def test_narrow_phase_limit_and_spatial_support_budget_stop(self):
        # Asymmetric monotone-center 3800x200 stack (4000 <= MAX_FACES) deterministically hits real MAX_NARROW_PHASE_PAIRS (16,384)
        la_v, la_f = [], []
        rb_v, rb_f = [], []
        na_n, nb_n = 3800, 200
        for k in range(na_n):
            w = float(na_n - k) * 100.0
            b = len(la_v)
            la_v.extend([[0.0, 0.0, 0.0], [w, 0.0, 0.0], [0.0, 1.0, 0.0]])
            la_f.append([b, b + 1, b + 2])
        for m in range(nb_n):
            wb = 1.0 + float(nb_n - m) * 1e-4
            b2 = len(rb_v)
            rb_v.extend([[-wb, 0.0, 1.0], [0.01, 0.0, 1.0], [0.0, 1.0, 1.0]])
            rb_f.append([b2, b2 + 1, b2 + 2])

        na = _freeze("np_a", la_v, la_f)
        nb = _freeze("np_b", rb_v, rb_f)
        r_np = sp.measure_surface_proximity(na, nb, NOOP)
        self.assertFalse(r_np["measurement_valid"])
        self.assertEqual(r_np["reason"], "surface_pair_budget")
        self.assertEqual(r_np["work"]["narrow_phase_pairs"], sp.MAX_NARROW_PHASE_PAIRS)
        self.assertLessEqual(r_np["work"]["work_units"], sp.MAX_WORK_UNITS)

        # Spatial relation support budget stop: enough work to finish surface proximity, tight before _referenced_support_evidence
        box_a = _box_mesh("sa", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), subdiv=1)
        box_b = _box_mesh("sb", (1.2, 0.0, 0.0), (1.0, 1.0, 1.0), subdiv=1)
        surf_only = sp.measure_surface_proximity(box_a, box_b, NOOP, retain_exact_rank=True)["work"]["work_units"]
        orig_init = sp._Work.__init__
        def tight_support(inst, cp, diag, init_w=sp.MAX_WORK_UNITS - (surf_only + 2)):
            orig_init(inst, cp, diag)
            inst.counts["work_units"] = init_w
        with patch.object(sp._Work, "__init__", tight_support):
            rel = sp.measure_spatial_relation(box_a, box_b, NOOP, retain_exact_rank=True)
        self.assertTrue(rel["surface"]["measurement_valid"])
        self.assertTrue(rel["budget_stopped"] or not rel["spatial"]["measurement_valid"])
        if rel["budget_stopped"]:
            self.assertEqual(rel["stop_reason"], "surface_work_budget")


class TestK03CacheOwnershipAndLifetime(unittest.TestCase):
    def test_rejects_mutable_aliases_and_forged_seal_allows_owned_readonly_numpy(self):
        v_list = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        f_list = [(0, 1, 2)]
        fixed = _freeze("fixed", [[0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0]], f_list)

        # 1. Tuple of lists + forged __sealed_query_meshes__
        cache_tol = {"__sealed_query_meshes__": True}
        m_tol = SimpleNamespace(object_id="tol", name="tol", vertices=tuple(v_list), faces=tuple(f_list))
        self.assertEqual(sp.measure_surface_proximity(m_tol, fixed, NOOP, _mesh_cache=cache_tol)["distance_m"], 1.0)
        self.assertEqual(cache_tol, {"__sealed_query_meshes__": True})
        v_list[0][2] = -2.0; v_list[1][2] = -2.0; v_list[2][2] = -2.0
        self.assertEqual(sp.measure_surface_proximity(m_tol, fixed, NOOP, _mesh_cache=cache_tol)["distance_m"], 3.0)

        # 2. Read-only NumPy view backed by writable owner array -> MUST reject and observe mutation
        owner = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float64)
        ro_view = owner.view()
        ro_view.flags.writeable = False
        cache_view = {"__sealed_query_meshes__": True}
        m_view = SimpleNamespace(object_id="view", name="view", vertices=ro_view, faces=((0, 1, 2),))
        self.assertEqual(sp.measure_surface_proximity(m_view, fixed, NOOP, _mesh_cache=cache_view)["distance_m"], 1.0)
        owner[:, 2] = -1.0
        self.assertEqual(sp.measure_surface_proximity(m_view, fixed, NOOP, _mesh_cache=cache_view)["distance_m"], 2.0)

        # 3. Face list mutation with same container size -> rejected cleanly
        mut_faces = [[0, 1, 2]]
        m_f = SimpleNamespace(object_id="mf", name="mf", vertices=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, -3.0), (1.0, 0.0, -3.0), (0.0, 1.0, -3.0)), faces=mut_faces)
        self.assertEqual(sp.measure_surface_proximity(m_f, fixed, NOOP, _mesh_cache=cache_tol)["distance_m"], 1.0)
        mut_faces[0] = [3, 4, 5]
        self.assertEqual(sp.measure_surface_proximity(m_f, fixed, NOOP, _mesh_cache=cache_tol)["distance_m"], 4.0)

        # 4. R3 C01: Even owned read-only float64 ndarray MUST fail closed in _mesh_cache
        owned_ro = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float64)
        owned_ro.flags.writeable = False
        cache_ok = {}
        m_ok = SimpleNamespace(object_id="owned", name="owned", vertices=owned_ro, faces=((0, 1, 2),))
        r1 = sp.measure_surface_proximity(m_ok, fixed, NOOP, _mesh_cache=cache_ok)
        r2 = sp.measure_surface_proximity(m_ok, fixed, NOOP, _mesh_cache=cache_ok)
        self.assertEqual(r1["distance_m"], 1.0)
        self.assertEqual(r2["distance_m"], 1.0)
        self.assertEqual(r2["work"].get("mesh_cache_hits", 0), 0)
        self.assertEqual(len(cache_ok), 0)

        # 5. Cache cap <= 256 across > 300 distinct immutable meshes
        cap_cache = {}
        for k in range(280):
            mk = _freeze(f"m{k}", [[0.0, 0.0, 2.0 + k * 0.01], [1.0, 0.0, 2.0 + k * 0.01], [0.0, 1.0, 2.0 + k * 0.01]], [(0, 1, 2)])
            sp.measure_surface_proximity(fixed, mk, NOOP, _mesh_cache=cap_cache)
        self.assertLessEqual(len(cap_cache), 256)
        self.assertIn(id(fixed), cap_cache)


class TestK04SubtreeProjectionAudit(unittest.TestCase):
    def test_predicate_boundaries_and_epoch_invalidation(self):
        bud = sp._Work(NOOP, {})
        # Zero and oversized-bit descriptor axes (co-prime so gcd normalization stays > 1024 bits) refused cleanly
        self.assertIsNone(sp._FastWitnessProjection.build((1, 1, ("points", (0, 0, 0), (0, 0, 0))), [], [], 0, bud))
        big = 1 << 1025
        self.assertIsNone(sp._FastWitnessProjection.build((1, 1, ("points", (0, 0, 0), (big, 1, 0))), [], [], 0, bud))

        # Cutoff exact equality: gap == cutoff must NOT prune; gap == cutoff + 1 MUST prune
        prep_a = [(((0, 0, 0), (0, 1, 0), (1, 0, 0)), (0, 0, 1), 1, (), ((0, 1), (0, 1), (0, 0)))]
        prep_b = [(((0, 0, 2), (0, 1, 2), (1, 0, 2)), (0, 0, 1), 1, (), ((0, 1), (0, 1), (2, 2)))]
        # best = 4 / 1 -> axis = (0, 0, 2) normalized (0, 0, 1), cutoff_strict = 2, cutoff_tie = 1
        fp = sp._FastWitnessProjection.build((4, 1, ("points", (0, 0, 0), (0, 0, 2))), prep_a, prep_b, 0, bud)
        self.assertIsNotNone(fp)
        na = (0, 0, 0, 1, 1, 0, 1, (0,), None, None, 0, 1, 1, 0)
        nb_eq = (0, 0, 2, 1, 1, 2, 1, (0,), None, None, 0, 1, 1, 4)
        nb_gt = (0, 0, 3, 1, 1, 3, 1, (0,), None, None, 0, 1, 1, 6)
        self.assertFalse(fp.prunes_nodes(na, nb_eq, True, bud, use_vertex_slab=True))   # gap=2 == cutoff=2
        self.assertTrue(fp.prunes_nodes(na, nb_eq, False, bud, use_vertex_slab=True))   # tie gap=2 > 1
        self.assertTrue(fp.prunes_nodes(na, nb_gt, True, bud, use_vertex_slab=True))    # gap=3 > 2


class TestK05SAHScalingAndMedianCompatibility(unittest.TestCase):
    def test_13_box_exact_dyadic_scale_and_translation_invariance(self):
        bounds = [
            ((1, 0, 0), (3, 1, 0)), ((9, 1, 0), (11, 3, 0)),
            ((7, 8, 0), (8, 13, 0)), ((3, 5, 0), (6, 10, 0)),
            ((4, 0, 0), (5, 4, 0)), ((6, 7, 0), (8, 9, 0)),
            ((0, 2, 0), (4, 4, 0)), ((4, 8, 0), (8, 10, 0)),
            ((6, 0, 0), (9, 5, 0)), ((2, 5, 0), (6, 7, 0)),
            ((1, 2, 0), (2, 4, 0)), ((8, 3, 0), (13, 8, 0)),
            ((8, 6, 0), (10, 9, 0)),
        ]

        def topo(node):
            lo, hi, cnt, ids, l, r = node
            if ids is not None:
                return ("L", tuple(ids))
            return ("N", cnt, topo(l), topo(r))

        b0 = sg._bvh(bounds, sp._Work(NOOP, {}), leaf_size=2)
        t0 = topo(b0)
        for scale in (1, 2, 4, 1024):
            for shift in ((0, 0, 0), (-100, 37, -19)):
                scaled = [
                    (tuple(lo[k] * scale + shift[k] for k in range(3)),
                     tuple(hi[k] * scale + shift[k] for k in range(3)))
                    for lo, hi in bounds
                ]
                bi = sg._bvh(scaled, sp._Work(NOOP, {}), leaf_size=2)
                self.assertEqual(topo(bi), t0, (scale, shift))

        # All-zero span + duplicate centroids must still build valid BVH without division by zero
        dup_bounds = [((2, 2, 2), (2, 2, 2)) for _ in range(10)]
        bd = sg._bvh(dup_bounds, sp._Work(NOOP, {}), leaf_size=2)
        self.assertEqual(bd[2], 10)


class TestK06ClosedSolidWitnessCompatibility(unittest.TestCase):
    def test_040_crossed_boxes_and_sah_prepared_trees_guard(self):
        b1 = _box_mesh("b1", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), subdiv=2)
        b2 = _box_mesh("b2", (0.875, 0.1875, 0.3125), (1.0, 1.0, 1.0), subdiv=2)
        res = sg.classify_closed_solids(b1, b2, NOOP)
        self.assertTrue(res["measurement_valid"])
        self.assertEqual(res["relation"], "penetrating")
        self.assertEqual(res["certificate"], "transverse_boundary_interiors")
        # Independent rational intersection check on returned witness triangle pair
        witness_idx = res["local_evidence"]["triangle_indices"]
        ta = [tuple(Fraction.from_float(c) for c in b1.vertices[k]) for k in b1.faces[witness_idx[0]]]
        tb = [tuple(Fraction.from_float(c) for c in b2.vertices[k]) for k in b2.faces[witness_idx[1]]]
        pts = sg.triangle_intersection_points(ta, tb) if hasattr(sg, "triangle_intersection_points") else sp._intersection(ta, tb, sp._normal(ta), sp._normal(tb), sp._Work(NOOP, {}))
        self.assertTrue(pts, f"Witness {witness_idx} did not intersect cleanly")

        # Verify prepared_trees with tree_kind == 'sah_bvh' is ignored by classify_closed_solids
        fake_sah = {"tree_kind": "sah_bvh", "roots": (None, None)}
        res2 = sg.classify_closed_solids(b1, b2, NOOP, prepared_trees=fake_sah)
        self.assertTrue(res2["measurement_valid"])
        self.assertEqual(res2["local_evidence"]["triangle_indices"], witness_idx)

        # Verify measure_spatial_relation reproduces identical witness even alongside SAH proximity trees
        rel = sp.measure_spatial_relation(b1, b2, NOOP, retain_exact_rank=True)
        self.assertTrue(rel["measurement_valid"])
        self.assertEqual(rel["spatial"]["relation"], "penetrating")
        self.assertEqual(rel["closed"]["local_evidence"]["triangle_indices"], witness_idx)


class TestK07ComparatorNegativeControls(unittest.TestCase):
    def test_comparator_and_ablation_guards_fail_closed(self):
        comp = bvh_eval.verify_comparator_negative_controls()
        self.assertTrue(comp["passed"], comp)
        self.assertGreaterEqual(comp["controls_checked"], 27)

        # _analyze_sig must NOT derive complete=True from status=='complete' or scan_complete=False
        sig_false = bvh_eval._analyze_sig({
            "measurement_valid": True,
            "status": "complete",
            "scan_complete": False,
            "pair_accounting_complete": True,
            "relation_summary": {},
        })
        self.assertFalse(sig_false["complete"])

        # _time_interleaved must reject an arm whose repeat outputs change between repeats (R3 C04 raises RuntimeError)
        arm = raa._load_arm_modules(ROOT)
        seq = iter([1, 1, 2])  # warmup=1 -> 1; repeat 0 -> 1; repeat 1 -> 2 != 1!
        with self.assertRaises((AssertionError, RuntimeError)):
            raa._time_interleaved(
                [("cur", (arm, lambda: next(seq)))],
                warmup=1, repeats=2, measure_mem=False, sig_fn=lambda x: {"v": x},
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)

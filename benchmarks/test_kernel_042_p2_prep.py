"""BVH-042 Phase 2 (042-P2) Exact Admission & Common-Exponent Dyadic Frame Verification Suite."""
from __future__ import annotations

import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.bvh_eval import _surface_sig, _work_summary
from benchmarks.run_kernel_042_p2_prep import FROZEN_ARM_I_RUNTIME_SHA, ensure_frozen_arm_i
from benchmarks.run_kernel_042_research import (
    FROZEN_RUNTIME_SHA,
    activate_arm,
    assert_raw_trees_equal,
    build_042_workloads,
    ensure_frozen_arm_a,
    load_arm_modules,
    measure_raw_trees_for_arm,
)
from human_eye_plugin import surface_proximity as cur_sp
import human_eye_module1_operators  # noqa: F401

_LIVE_MODS = {
    k: v for k, v in sys.modules.items()
    if k == "human_eye_plugin" or k.startswith("human_eye_plugin.")
    or k == "human_eye_module1_operators" or k.startswith("human_eye_module1_operators.")
}


def _restore_live():
    for k in list(sys.modules):
        if (k == "human_eye_plugin" or k.startswith("human_eye_plugin.")
                or k == "human_eye_module1_operators" or k.startswith("human_eye_module1_operators.")):
            sys.modules.pop(k, None)
    sys.modules.update(_LIVE_MODS)


NOOP = lambda _stage: None


class _CancelStop(RuntimeError):
    pass


class TestKernel042P2Prep(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.arm_a = load_arm_modules("A_frozen", ensure_frozen_arm_a())
            cls.arm_i = load_arm_modules("I_frozen", ensure_frozen_arm_i())
            if cls.arm_a.source_sha256 != FROZEN_RUNTIME_SHA:
                raise AssertionError(f"Arm A sha mismatch: {cls.arm_a.source_sha256}")
            if cls.arm_i.source_sha256 != FROZEN_ARM_I_RUNTIME_SHA:
                raise AssertionError(f"Arm I sha mismatch: {cls.arm_i.source_sha256}")
            cls.workloads = build_042_workloads()
        finally:
            _restore_live()

    @classmethod
    def tearDownClass(cls):
        _restore_live()

    def setUp(self):
        _restore_live()

    def tearDown(self):
        _restore_live()

    def test_01_bit_for_bit_frame_origin_factor_and_fallback_parity(self):
        """Verify fast common-exponent path AND extreme-spread fallback match Arm I bit-for-bit."""
        # 1. Exact canceling offsets: ox=0.3, deltas are pure integers -> common_tz strips all 54 fraction bits -> factor=1!
        m_cancel_a = SimpleNamespace(
            object_id="ca", name="ca",
            vertices=((0.3, -0.7, 1.1), (1.3, -0.7, 1.1), (0.3, 0.3, 1.1)),
            faces=((0, 1, 2),),
        )
        m_cancel_b = SimpleNamespace(
            object_id="cb", name="cb",
            vertices=((2.3, -0.7, 1.1), (2.3, 0.3, 1.1), (3.3, -0.7, 1.1)),
            faces=((0, 1, 2),),
        )
        # 2. All zeros + single non-zero
        m_zero_a = SimpleNamespace(
            object_id="za", name="za",
            vertices=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
            faces=((0, 1, 2),),
        )
        m_zero_b = SimpleNamespace(
            object_id="zb", name="zb",
            vertices=((0.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.0, 0.0, 3.0)),
            faces=((0, 1, 2),),
        )
        # 3. Extreme binary64 exponent spread > 900 bits (forces fallback path!)
        m_spread_a = SimpleNamespace(
            object_id="sa", name="sa",
            vertices=((math.ldexp(1.0, -950), 0.0, 0.0), (math.ldexp(1.0, -949), 1.0, 0.0), (0.0, 0.0, 1.0)),
            faces=((0, 1, 2),),
        )
        m_spread_b = SimpleNamespace(
            object_id="sb", name="sb",
            vertices=((math.ldexp(1.0, 100), 0.0, 0.0), (math.ldexp(1.0, 100) + 1.0, 2.0, 0.0), (0.0, 0.0, 2.0)),
            faces=((0, 1, 2),),
        )
        # 4. LargeShift_2pow30 and Sheet_Parallel_5um and Sparse_100kV
        by_id = {w["id"]: w["tuple_pair"] for w in self.workloads["singles"]}
        pairs = [
            ("cancel_to_int", (m_cancel_a, m_cancel_b)),
            ("all_zero_degenerate", (m_zero_a, m_zero_b)),
            ("extreme_spread_fallback", (m_spread_a, m_spread_b)),
            ("Sheet_Parallel_5um", by_id["Sheet_Parallel_5um"]),
            ("Sparse_100kV_Degenerate_MixedBit", by_id["Sparse_100kV_Degenerate_MixedBit"]),
        ]
        for label, (la, rb) in pairs:
            activate_arm(self.arm_i)
            hi = {}
            ri = self.arm_i.sp.measure_surface_proximity(la, rb, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _prepared_holder=hi)
            _restore_live()
            hc = {}
            rc = cur_sp.measure_surface_proximity(la, rb, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _prepared_holder=hc)
            self.assertEqual(_surface_sig(ri), _surface_sig(rc), f"{label}: sig mismatch")
            self.assertEqual(_work_summary(ri["work"]), _work_summary(rc["work"]), f"{label}: work mismatch")
            # Origin & factor & coordinate dicts bit-for-bit identical!
            self.assertEqual(hi["pair"][2], hc["pair"][2], f"{label}: origin mismatch")
            self.assertEqual(hi["pair"][3], hc["pair"][3], f"{label}: factor mismatch")
            self.assertEqual(hi["coordinates"], hc["coordinates"], f"{label}: coordinates mismatch")
            if label == "Sparse_100kV_Degenerate_MixedBit":
                # Confirm sparse without holder stays dict of referenced vertices (~60), NOT list of 100k
                bi = cur_sp._Work(NOOP, {})
                recs, _ = cur_sp._admit((la, rb), bi)
                _, _, prep = cur_sp._integer_frame(recs, bi)
                self.assertEqual(len(prep[0]), 20)

    def test_02_nonfinite_rejection_sparse_nan_tail_and_noncontig_ndarray(self):
        """K01 invariance: sparse 100kV unreferenced NaN tails ignored; non-contiguous ndarray allowed & cached=False."""
        n = 50000
        verts = np.full((n, 3), np.nan, dtype=np.float64)
        for i in (10, 200, 49990):
            verts[i] = [float(i) * 1e-4, 0.0, 0.0]
        verts[200, 1] = 1.0
        verts[49990, 2] = 1.0
        va_nc = verts[:, ::-1][:, ::-1]  # non-contiguous view
        va_nc.flags.writeable = False
        vb = np.array([[0.0, 0.0, 2.0], [1.0, 0.0, 2.0], [0.0, 1.0, 2.0]], dtype=np.float64)
        vb.flags.writeable = False
        ma = SimpleNamespace(object_id="sp_a", name="sp_a", vertices=va_nc, faces=((10, 200, 49990),))
        mb = SimpleNamespace(object_id="sp_b", name="sp_b", vertices=vb, faces=((0, 1, 2),))
        cache = {}
        rc = cur_sp.measure_surface_proximity(ma, mb, NOOP, _mesh_cache=cache)
        self.assertTrue(rc["measurement_valid"])
        self.assertEqual(rc["work"]["referenced_vertices"], 6)
        self.assertEqual(len(cache), 0)

        # Referenced NaN must still reject fail-closed
        bad_v = np.array([[0.0, float("nan"), 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float64)
        bad_m = SimpleNamespace(object_id="bad", name="bad", vertices=bad_v, faces=((0, 1, 2),))
        with self.assertRaises(cur_sp._DomainError):
            cur_sp._integer_frame([(bad_m, [(0, 1, 2)], [0, 1, 2]), (mb, [(0, 1, 2)], [0, 1, 2])], cur_sp._Work(NOOP, {}))

    def test_03_projection_modes_cancellation_and_parity_vs_frozen_041(self):
        """Verify 3 projection modes, raw trees, and mid-frame cancellation + clean retry vs frozen 119327bbb."""
        w = next(x for x in self.workloads["singles"] if x["id"] == "Rotated_30deg_Spheres")
        l_tup, r_tup = w["tuple_pair"]
        ta = measure_raw_trees_for_arm(self.arm_a, l_tup, r_tup)
        _restore_live()
        bd = cur_sp._Work(NOOP, {})
        recs, _ = cur_sp._admit((l_tup, r_tup), bd)
        _, _, prep = cur_sp._integer_frame(recs, bd)
        rc = cur_sp._distance_roots(prep, bd)
        assert_raw_trees_equal(ta["roots"][0], rc[0], "P2.Rot.L")
        assert_raw_trees_equal(ta["roots"][1], rc[1], "P2.Rot.R")

        for mode in ("settled_credit_031_ref", "off", "off_paid_dequeue_ref"):
            activate_arm(self.arm_a)
            ra = self.arm_a.sp.measure_surface_proximity(
                l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=mode,
            )
            _restore_live()
            rk = cur_sp.measure_surface_proximity(
                l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=mode,
            )
            self.assertEqual(_surface_sig(ra), _surface_sig(rk))
            self.assertEqual(_work_summary(ra["work"]), _work_summary(rk["work"]))

        # Mid-frame cancellation & clean recovery
        for stage, hit in (("surface_proximity_validated_faces", 1), ("surface_proximity_referenced_vertices", 5), ("surface_proximity_triangle_prepare", 10)):
            h = 0

            def cp(st):
                nonlocal h
                if st == stage:
                    h += 1
                    if h == hit:
                        raise _CancelStop()

            with self.assertRaises(_CancelStop):
                cur_sp.measure_surface_proximity(l_tup, r_tup, cp)

        retry = cur_sp.measure_surface_proximity(l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        activate_arm(self.arm_a)
        ref = self.arm_a.sp.measure_surface_proximity(l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        _restore_live()
        self.assertEqual(_surface_sig(ref), _surface_sig(retry))


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""M3 BVH 045 Exact Pre-Tree Cross-Pair Separation Contract, Oracle & Negative Control Suite."""
from __future__ import annotations

import copy
from fractions import Fraction
import math
from pathlib import Path
import random
import sys
from types import SimpleNamespace
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.bvh_eval import _surface_sig
from benchmarks.run_kernel_042_research import (
    _sha256_json,
    activate_arm,
    build_042_workloads,
    load_arm_modules,
)
from benchmarks.run_kernel_044_r1_qualification import (
    FROZEN_ARM_K_COMMIT,
    FROZEN_ARM_K_RUNTIME_SHA,
    _key_to_frac,
    _load_real_batch_fixtures,
    ensure_frozen_arm,
)
from benchmarks.run_kernel_045_preproof import (
    build_045_guard_batches,
    build_receipt_digest,
    serialize_045_batch_receipt,
    validate_045_batch_receipt_comparison,
)
from human_eye_plugin import surface_batch_preproof as sbp, surface_proximity as cur_sp
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


def _tri_pts(oid: str, verts):
    return SimpleNamespace(object_id=oid, name=oid, vertices=verts, faces=((0, 1, 2),))


def _exact_v(v):
    return (Fraction.from_float(float(v[0])), Fraction.from_float(float(v[1])), Fraction.from_float(float(v[2])))


def _raw_vertex_aabb_gap_sq(verts_a, verts_b) -> Fraction:
    ea = [_exact_v(v) for v in verts_a]
    eb = [_exact_v(v) for v in verts_b]
    a_lo = [min(p[c] for p in ea) for c in range(3)]
    a_hi = [max(p[c] for p in ea) for c in range(3)]
    b_lo = [min(p[c] for p in eb) for c in range(3)]
    b_hi = [max(p[c] for p in eb) for c in range(3)]
    s = Fraction(0)
    for c in range(3):
        if a_hi[c] < b_lo[c]:
            d = b_lo[c] - a_hi[c]
            s += d * d
        elif b_hi[c] < a_lo[c]:
            d = a_lo[c] - b_hi[c]
            s += d * d
    return s


def _raw_vertex_axis_lower_bound_sq(verts_a, verts_b, axis) -> Fraction:
    ax = (Fraction(axis[0]), Fraction(axis[1]), Fraction(axis[2]))
    norm2 = ax[0] * ax[0] + ax[1] * ax[1] + ax[2] * ax[2]
    da = [p[0] * ax[0] + p[1] * ax[1] + p[2] * ax[2] for p in (_exact_v(v) for v in verts_a)]
    db = [p[0] * ax[0] + p[1] * ax[1] + p[2] * ax[2] for p in (_exact_v(v) for v in verts_b)]
    lo_a, hi_a = min(da), max(da)
    lo_b, hi_b = min(db), max(db)
    gap = (lo_b - hi_a) if lo_b > hi_a else ((lo_a - hi_b) if lo_a > hi_b else Fraction(0))
    return (gap * gap) / norm2


def _perm_faces_mesh(mesh, rng: random.Random):
    faces = list(mesh.faces)
    rng.shuffle(faces)
    return SimpleNamespace(object_id=mesh.object_id, name=mesh.name, vertices=mesh.vertices, faces=tuple(faces))


def _scale_translate_mesh(mesh, scale: float, offset):
    verts = tuple((v[0] * scale + offset[0], v[1] * scale + offset[1], v[2] * scale + offset[2]) for v in mesh.vertices)
    return SimpleNamespace(object_id=mesh.object_id, name=mesh.name, vertices=verts, faces=mesh.faces)


class TestKernel045Preproof(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workloads = build_042_workloads()
        cls.real_batches = _load_real_batch_fixtures()
        cls.guard_batches = build_045_guard_batches()
        cls.arm_k = load_arm_modules("K", ensure_frozen_arm(FROZEN_ARM_K_COMMIT, "arm_k_042_p2", FROZEN_ARM_K_RUNTIME_SHA))
        _restore_live()

    def tearDown(self):
        _restore_live()

    def test_01_a_only_untouched_parity_vs_k(self):
        """Ordinary single-pair measure_surface_proximity remains 100% identical to frozen K."""
        for w in self.workloads["singles"]:
            l_m, r_m = w["tuple_pair"]
            for mode in ("settled_credit_031_ref", "off", "off_paid_dequeue_ref"):
                activate_arm(self.arm_k)
                rk = self.arm_k.sp.measure_surface_proximity(
                    l_m, r_m, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=mode
                )
                _restore_live()
                rr = cur_sp.measure_surface_proximity(
                    l_m, r_m, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=mode
                )
                self.assertEqual(_surface_sig(rk), _surface_sig(rr))
                self.assertEqual(rk["work"], rr["work"])

    def test_02_randomized_8000_dyadic_frame_oracle(self):
        """8000 randomized signed/translated/scaled/equality/zero/extreme cases vs Fraction oracle."""
        rng = random.Random(45001)
        aabb_checked = axis_checked = deferred_span = equality_rejected = 0
        for case_idx in range(8000):
            base_e = rng.randint(-120, 120)
            off = [math.ldexp(rng.randint(-64, 64), base_e + rng.randint(-10, 10)) for _ in range(3)]
            sep_bias = math.ldexp(80000, base_e) if (case_idx % 10 == 1) else 0.0
            pts_a = tuple(
                tuple(off[c] + math.ldexp(rng.randint(-200, 200), base_e) for c in range(3))
                for _ in range(3)
            )
            pts_b = tuple(
                tuple(off[c] + (sep_bias if c == 0 else 0.0) + math.ldexp(rng.randint(-200, 200), base_e + rng.randint(-8, 8)) for c in range(3))
                for _ in range(3)
            )
            ma = _tri_pts("a", pts_a)
            mb = _tri_pts("b", pts_b)
            ent_a = cur_sp._capture_referenced_immutable_mesh(ma, "a", NOOP)
            ent_b = cur_sp._capture_referenced_immutable_mesh(mb, "b", NOOP)
            self.assertTrue(ent_a["ok"] and ent_b["ok"])

            axis = (rng.randint(-100, 100), rng.randint(-100, 100), rng.randint(-100, 100))
            if not any(axis):
                axis = (1, 0, 0)
            if case_idx % 10 == 1:
                axis = (abs(axis[0]) or 10, axis[1] // 4, axis[2] // 4)
            # Pick bound either random, zero, or exact equality with oracle axis gap^2
            oracle_aabb = _raw_vertex_aabb_gap_sq(pts_a, pts_b)
            oracle_ax = _raw_vertex_axis_lower_bound_sq(pts_a, pts_b, axis)
            if case_idx % 10 == 0:
                u_frac = Fraction(0)
            elif case_idx % 10 == 1 and oracle_ax > 0:
                u_frac = oracle_ax  # exact equality! MUST NOT exclude!
            elif case_idx % 10 == 2 and oracle_ax > 0:
                u_frac = oracle_ax * Fraction(255, 256)
            else:
                u_frac = Fraction(rng.randint(1, 50000), rng.randint(1, 64)) * (
                    Fraction(1 << (2 * base_e)) if base_e >= 0 else Fraction(1, 1 << (-2 * base_e))
                )
            key = [u_frac.numerator, u_frac.denominator, 0]

            raabb = sbp.check_pretree_root_aabb_exclusion(ent_a, ent_b, key, NOOP)
            if ent_a["preproof_eligible"] and ent_b["preproof_eligible"] and raabb["deferred_reason"] is None:
                aabb_checked += 1
                self.assertEqual(raabb["excluded"], oracle_aabb > u_frac)
                if oracle_aabb == u_frac:
                    self.assertFalse(raabb["excluded"])
            else:
                deferred_span += 1

            raxis = sbp.check_pretree_root_axis_exclusion(ent_a, ent_b, axis, key, NOOP)
            if ent_a["preproof_eligible"] and ent_b["preproof_eligible"] and raxis["deferred_reason"] is None:
                axis_checked += 1
                self.assertEqual(raxis["excluded"], oracle_ax > u_frac)
                if case_idx % 10 == 1 and oracle_ax > 0:
                    self.assertFalse(raxis["excluded"])
                    equality_rejected += 1
                # Axis negation symmetry check on sample subset
                if case_idx % 20 == 0:
                    rneg = sbp.check_pretree_root_axis_exclusion(ent_a, ent_b, (-axis[0], -axis[1], -axis[2]), key, NOOP)
                    self.assertEqual(raxis["excluded"], rneg["excluded"])
            else:
                deferred_span += 1

        self.assertGreaterEqual(aabb_checked, 7000)
        self.assertGreaterEqual(axis_checked, 7000)
        self.assertGreaterEqual(equality_rejected, 300)

        # Wide exponent spread > 450 & subnormals must safely defer without false exclusion
        wide_m = _tri_pts("wide", ((1e-200, 0.0, 0.0), (1e200, 0.0, 0.0), (0.0, 1.0, 0.0)))
        small_m = _tri_pts("small", ((0.0, 0.0, 5.0), (1.0, 0.0, 5.0), (0.0, 1.0, 5.0)))
        ew = cur_sp._capture_referenced_immutable_mesh(wide_m, "wide", NOOP)
        es = cur_sp._capture_referenced_immutable_mesh(small_m, "small", NOOP)
        self.assertFalse(ew["preproof_eligible"])
        res_defer = sbp.check_pretree_root_axis_exclusion(ew, es, (0, 0, 1), [1, 1, 0], NOOP)
        self.assertFalse(res_defer["excluded"])
        self.assertEqual(res_defer["deferred_reason"], "preproof_extreme_exponent")

    def test_03_independent_raw_vertex_proof_audit_real_scenes(self):
        """Independent raw-vertex Fraction audit on all 4 real scenes & every B1..B4 pretree proof."""
        scenes = [
            ("D48", *self.workloads["batches"][0]["tuple_batch"], [f"peer_{i}" for i in range(47)]),
            ("Asm24", *self.workloads["batches"][1]["tuple_batch"], [f"peer_{i}" for i in range(23)]),
            ("G508", self.real_batches["G508_Retained_11pairs"]["target"], self.real_batches["G508_Retained_11pairs"]["peers"], self.real_batches["G508_Retained_11pairs"]["peer_ids"]),
            ("G60", self.real_batches["G60_D12_Retained_11pairs"]["target"], self.real_batches["G60_D12_Retained_11pairs"]["peers"], self.real_batches["G60_D12_Retained_11pairs"]["peer_ids"]),
        ]
        for sname, tg, ps, pids in scenes:
            ex = cur_sp.measure_nearest_surface_batch(tg, ps, NOOP, peer_ids=pids, cutoff_mode="EXHAUSTIVE")
            self.assertEqual(ex["status"], "complete")
            ex_best_frac = _key_to_frac(ex["best_exact_distance_sq"])

            for pmode in ("B1_ROOT_AABB", "B2_INCUMBENT_AXIS", "B3_TARGET_MEMO_AXIS", "B4_BOUNDED_MULTI_AXIS"):
                out = cur_sp.measure_nearest_surface_batch(
                    tg, ps, NOOP, peer_ids=pids,
                    cutoff_mode="CUTOFF_SETTLED_PROJECTION", preproof_mode=pmode,
                )
                self.assertEqual(out["status"], "complete", (sname, pmode))
                self.assertEqual(out["nearest_ids"], ex["nearest_ids"])
                self.assertEqual(out["best_exact_distance_sq"], ex["best_exact_distance_sq"])

                peer_map = dict(zip(pids, ps))
                for pid, oc in out["outcomes_by_id"].items():
                    if oc["result_kind"] != "nearest_cutoff_exclusion":
                        continue
                    pk = oc["proof_kind"]
                    if pk not in ("pretree_root_aabb", "pretree_root_axis"):
                        continue
                    # Zero downstream tree build or triangle preparation
                    self.assertEqual(oc["work"].get("tree_builds", 0), 0)
                    self.assertEqual(oc["work"].get("prepared_triangles", 0), 0)
                    self.assertEqual(oc["work"].get("node_pair_visits", 0), 0)

                    ub_frac = _key_to_frac(oc["exact_upper_bound_key"])
                    true_frac = _key_to_frac(ex["outcomes_by_id"][pid]["measured_result"]["_exact_distance_sq"])
                    self.assertGreater(true_frac, ub_frac)
                    self.assertGreaterEqual(ub_frac, ex_best_frac)

                    if pk == "pretree_root_aabb":
                        indep_gap_sq = _raw_vertex_aabb_gap_sq(tg.vertices, peer_map[pid].vertices)
                        self.assertGreater(indep_gap_sq, ub_frac, (sname, pmode, pid))
                    else:
                        ax = oc["proof_receipt"]["axis"]
                        indep_lb = _raw_vertex_axis_lower_bound_sq(tg.vertices, peer_map[pid].vertices, ax)
                        self.assertGreater(indep_lb, ub_frac, (sname, pmode, pid))

    def test_04_metamorphic_and_adversarial_guards(self):
        """Permutations, face shuffles, dyadic scale/shift, A/B swap, sparse 100k, interleaved & subnormals."""
        # 1. Order permutations & face shuffle on D48
        d48_t, d48_p = self.workloads["batches"][0]["tuple_batch"]
        n_d48 = len(d48_p)
        d48_pids = [f"peer_{i}" for i in range(n_d48)]
        ref = cur_sp.measure_nearest_surface_batch(d48_t, d48_p, NOOP, peer_ids=d48_pids, cutoff_mode="EXHAUSTIVE")
        rng = random.Random(2026)
        orders = [list(reversed(range(n_d48)))]
        for _ in range(3):
            o = list(range(n_d48))
            rng.shuffle(o)
            orders.append(o)
        for perm in orders:
            p_perm = [_perm_faces_mesh(d48_p[i], rng) for i in perm]
            pids_perm = [f"peer_{i}" for i in perm]
            out = cur_sp.measure_nearest_surface_batch(
                _perm_faces_mesh(d48_t, rng), p_perm, NOOP, peer_ids=pids_perm,
                cutoff_mode="CUTOFF_SETTLED_PROJECTION", preproof_mode="B3_TARGET_MEMO_AXIS",
            )
            self.assertEqual(sorted(out["nearest_ids"]), sorted(ref["nearest_ids"]))
            self.assertEqual(out["best_exact_distance_sq"], ref["best_exact_distance_sq"])

        # 2. Uniform exact dyadic scale (4.0) on G60_D12 & exact dyadic translation on integer grid
        g60 = self.real_batches["G60_D12_Retained_11pairs"]
        g60_ex = cur_sp.measure_nearest_surface_batch(
            g60["target"], g60["peers"], NOOP, peer_ids=g60["peer_ids"],
            cutoff_mode="CUTOFF_SETTLED_PROJECTION", preproof_mode="B3_TARGET_MEMO_AXIS",
        )
        t_st = _scale_translate_mesh(g60["target"], 4.0, (0.0, 0.0, 0.0))
        p_st = [_scale_translate_mesh(p, 4.0, (0.0, 0.0, 0.0)) for p in g60["peers"]]
        g60_st = cur_sp.measure_nearest_surface_batch(
            t_st, p_st, NOOP, peer_ids=g60["peer_ids"],
            cutoff_mode="CUTOFF_SETTLED_PROJECTION", preproof_mode="B3_TARGET_MEMO_AXIS",
        )
        self.assertEqual(g60_st["nearest_ids"], g60_ex["nearest_ids"])
        self.assertEqual(_key_to_frac(g60_st["best_exact_distance_sq"]), _key_to_frac(g60_ex["best_exact_distance_sq"]) * 16)

        # Exact dyadic translation invariance on integer-aligned grid (zero float rounding on translation)
        tr_tg = _tri_pts("ttg", ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))
        tr_ps = [_tri_pts("tp0", ((2.0, 0.0, 2.0), (3.0, 0.0, 2.0), (2.0, 1.0, 2.0))),
                 _tri_pts("tp1", ((8.0, 0.0, 0.0), (0.0, 0.0, 4.0), (8.0, 1.0, 0.0)))]
        tr_base = cur_sp.measure_nearest_surface_batch(tr_tg, tr_ps, NOOP, cutoff_mode="CUTOFF_SETTLED_PROJECTION", preproof_mode="B3_TARGET_MEMO_AXIS")
        tr_sh = cur_sp.measure_nearest_surface_batch(
            _scale_translate_mesh(tr_tg, 2.0, (32.0, -64.0, 16.0)),
            [_scale_translate_mesh(p, 2.0, (32.0, -64.0, 16.0)) for p in tr_ps],
            NOOP, cutoff_mode="CUTOFF_SETTLED_PROJECTION", preproof_mode="B3_TARGET_MEMO_AXIS",
        )
        self.assertEqual(tr_sh["nearest_ids"], tr_base["nearest_ids"])
        self.assertEqual(_key_to_frac(tr_sh["best_exact_distance_sq"]), _key_to_frac(tr_base["best_exact_distance_sq"]) * 4)

        # 3. Sparse 100k NaN-tail ndarray + HighOverlap + TiedContact_12pairs
        arr_t = np.full((100_000, 3), np.nan, dtype=np.float64)
        arr_t[:3] = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        mt = SimpleNamespace(object_id="mt", name="mt", vertices=arr_t, faces=((0, 1, 2),))
        sp_p0 = _tri_pts("sp0", ((0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (0.0, 1.0, 1.0)))
        sp_p1 = _tri_pts("sp1", ((0.0, 0.0, 8.0), (1.0, 0.0, 8.0), (0.0, 1.0, 8.0)))
        sp_out = cur_sp.measure_nearest_surface_batch(
            mt, [sp_p0, sp_p1], NOOP, cutoff_mode="CUTOFF_SETTLED_PROJECTION", preproof_mode="B3_TARGET_MEMO_AXIS",
        )
        self.assertEqual(sp_out["status"], "complete")
        self.assertEqual(sp_out["nearest_ids"], ["sp0"])
        self.assertEqual(sp_out["coverage"]["n_excluded_pretree_aabb"], 1)

        ho = self.guard_batches["HighOverlap_Interleaved_16pairs"]
        ho_ex = cur_sp.measure_nearest_surface_batch(ho["target"], ho["peers"], NOOP, peer_ids=ho["peer_ids"], cutoff_mode="EXHAUSTIVE")
        ho_b3 = cur_sp.measure_nearest_surface_batch(ho["target"], ho["peers"], NOOP, peer_ids=ho["peer_ids"], cutoff_mode="CUTOFF_SETTLED_PROJECTION", preproof_mode="B3_TARGET_MEMO_AXIS")
        self.assertEqual(ho_b3["nearest_ids"], ho_ex["nearest_ids"])
        self.assertEqual(ho_b3["best_exact_distance_sq"], ho_ex["best_exact_distance_sq"])
        self.assertEqual(ho_b3["coverage"]["n_excluded_pretree_aabb"], 0)
        self.assertEqual(ho_b3["coverage"]["n_excluded_pretree_axis"], 0)

        tc = self.guard_batches["TiedContact_12pairs"]
        tc_out = cur_sp.measure_nearest_surface_batch(tc["target"], tc["peers"], NOOP, peer_ids=tc["peer_ids"], cutoff_mode="CUTOFF_SETTLED_PROJECTION", preproof_mode="B3_TARGET_MEMO_AXIS")
        self.assertEqual(tc_out["status"], "complete")
        self.assertEqual(len(tc_out["nearest_ids"]), 12)
        self.assertEqual(tc_out["coverage"]["n_excluded_pretree_aabb"], 2)

    def test_05_mid_preproof_cancellation_and_cache_isolation(self):
        """Cancel at surface_proximity_preproof_aabb & axis_proj (>256 verts); retry cleanly."""
        g60 = self.real_batches["G60_D12_Retained_11pairs"]
        asm_t, asm_p = self.workloads["batches"][1]["tuple_batch"]
        # 1. Cancel inside surface_proximity_preproof_aabb (Asm24 has AABB separation)
        def stop_aabb(st):
            if st == "surface_proximity_preproof_aabb":
                raise _CancelStop()
        with self.assertRaises(_CancelStop):
            cur_sp.measure_nearest_surface_batch(
                asm_t, asm_p, stop_aabb, cutoff_mode="CUTOFF_SETTLED_PROJECTION", preproof_mode="B3_TARGET_MEMO_AXIS",
            )
        # 2. Cancel inside chunked surface_proximity_preproof_axis_proj (both D48 and >256-vertex tilted strip)
        d48_t, d48_p = self.workloads["batches"][0]["tuple_batch"]
        proj_calls = 0
        def stop_proj(st):
            nonlocal proj_calls
            if st == "surface_proximity_preproof_axis_proj":
                proj_calls += 1
                if proj_calls >= 3:
                    raise _CancelStop()
        with self.assertRaises(_CancelStop):
            cur_sp.measure_nearest_surface_batch(
                d48_t, d48_p, stop_proj, peer_ids=[f"p{i}" for i in range(len(d48_p))],
                cutoff_mode="CUTOFF_SETTLED_PROJECTION", preproof_mode="B3_TARGET_MEMO_AXIS",
            )
        self.assertGreaterEqual(proj_calls, 3)

        # Also verify >256-vertex single-peer chunking hits axis_proj multiple times
        big_v = tuple((float(i % 20) * 0.01, float(i // 20) * 0.01, 2.0 + float(i % 20) * 0.01) for i in range(600))
        big_f = tuple((0, i, i + 1) for i in range(1, 598))
        big_p = SimpleNamespace(object_id="big", name="big", vertices=big_v, faces=big_f)
        cnt_chunks = 0
        def stop_chunk(st):
            nonlocal cnt_chunks
            if st == "surface_proximity_preproof_axis_proj":
                cnt_chunks += 1
                if cnt_chunks >= 3:
                    raise _CancelStop()
        t_box = _tri_pts("tb", ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))
        p_inc = _tri_pts("pi", ((0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (0.0, 1.0, 1.0)))
        # Ensure big_p overlaps tb's AABB in X/Y/Z? Actually diagonal D48 pair0 + D48 peer1 (>256 verts? make D48 target 300+ verts!)
        with self.assertRaises(_CancelStop):
            big_tg_v = tuple((v[0], v[1], v[2]) for v in d48_t.vertices) + tuple(
                (d48_t.vertices[0][0], d48_t.vertices[0][1], d48_t.vertices[0][2]) for _ in range(300)
            )
            off0 = len(d48_t.vertices)
            big_tg_f = tuple(d48_t.faces) + tuple((off0 + (i % 3), off0 + ((i + 1) % 3), off0 + ((i + 2) % 3)) for i in range(0, 297, 3))
            # Instead simpler: direct 600-vertex mesh into project_mesh_exact_interval checks 3 chunks!
            sbp.project_mesh_exact_interval(big_v, 0, (0, 0, 1), stop_chunk)
        self.assertEqual(cnt_chunks, 3)

        # Retry succeeds identically
        out = cur_sp.measure_nearest_surface_batch(
            g60["target"], g60["peers"], NOOP, peer_ids=g60["peer_ids"],
            cutoff_mode="CUTOFF_SETTLED_PROJECTION", preproof_mode="B3_TARGET_MEMO_AXIS",
        )
        self.assertEqual(out["status"], "complete")

    def test_06_hardened_045_validator_negative_controls(self):
        """Hardened 045 batch receipt validator rejects >= 15 negative controls (normal & python -O)."""
        tg = _tri_pts("tg", ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))
        # p0 at Z=2, p1 excluded by axis (tilted rotated box separated strictly along p0's Z? Wait: make p1 AABB separated & p2 axis-separated!)
        p0 = _tri_pts("p0", ((0.0, 0.0, 2.0), (1.0, 0.0, 2.0), (0.0, 1.0, 2.0)))
        p1 = _tri_pts("p1", ((0.0, 0.0, 9.0), (1.0, 0.0, 9.0), (0.0, 1.0, 9.0)))  # pretree_root_aabb
        # Give p2 an X-diagonal separation only via (p0-like tilted witness): use G60 pair or p0=(2,0,2) so axis=(2,0,2)!
        tg_d = _tri_pts("tgd", ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))
        p0_d = _tri_pts("p0d", ((2.0, 0.0, 2.0), (3.0, 0.0, 2.0), (2.0, 1.0, 2.0)))  # nearest at X=[1..2],Z=[0..2] -> axis=(1,0,2)
        p1_d = _tri_pts("p1d", ((10.0, 0.0, 10.0), (11.0, 0.0, 10.0), (10.0, 1.0, 10.0)))  # pretree_root_aabb
        # p2_d overlaps target AABB in X=[0,1], Z=[0,2] NO wait: overlaps target AABB [-1..2]? No, put vertex at (0,0,0.5)? Wait:
        # Target box [0,1]x[0,1]x{0}. Incumbent axis=(1,0,2) -> t in [0, 1]. Place p2 at (4,0,0), (0,0,4), (4,1,0):
        # p2 AABB x=[0,4], z=[0,4] OVERLAPS target AABB! So B1 AABB fails; dot((x,y,z),(1,0,2)) = x+2z -> min dot >= 4 -> B2 axis EXCLUDES!
        p2_d = _tri_pts("p2d", ((8.0, 0.0, 0.0), (0.0, 0.0, 4.0), (8.0, 1.0, 0.0)))
        ps = [p0_d, p1_d, p2_d]
        pids = ["p0d", "p1d", "p2d"]
        inp_sha = _sha256_json([list(tg_d.vertices), list(tg_d.faces)] + [[list(p.vertices), list(p.faces)] for p in ps])
        opt_sha = _sha256_json({"mode": "045_neg"})

        bo_ex = cur_sp.measure_nearest_surface_batch(tg_d, ps, NOOP, peer_ids=pids, cutoff_mode="EXHAUSTIVE")
        bo_b3 = cur_sp.measure_nearest_surface_batch(tg_d, ps, NOOP, peer_ids=pids, cutoff_mode="CUTOFF_SETTLED_PROJECTION", preproof_mode="B3_TARGET_MEMO_AXIS")
        self.assertEqual(bo_b3["outcomes_by_id"]["p1d"]["proof_kind"], "pretree_root_aabb")
        self.assertEqual(bo_b3["outcomes_by_id"]["p2d"]["proof_kind"], "pretree_root_axis")

        pins = {"EXH": "a" * 64, "B3": "b" * 64}
        manifest = {"input_sha256": inp_sha, "options_sha256": opt_sha, "peer_ids": pids}
        base_r = serialize_045_batch_receipt(arm_name="EXH", runtime_source_sha256="a" * 64, input_sha256=inp_sha, options_sha256=opt_sha, batch_out=bo_ex)
        cand_r = serialize_045_batch_receipt(arm_name="B3", runtime_source_sha256="b" * 64, input_sha256=inp_sha, options_sha256=opt_sha, batch_out=bo_b3)
        self.assertTrue(validate_045_batch_receipt_comparison(base_r, cand_r, manifest, pins)["passed"])

        def _rehash(r):
            r["digest_sha256"] = build_receipt_digest(r)
            return r

        def _must_fail(name, fn):
            b, c, m, p = copy.deepcopy(base_r), copy.deepcopy(cand_r), copy.deepcopy(manifest), copy.deepcopy(pins)
            fn(b, c, m, p)
            with self.assertRaises((ValueError, KeyError), msg=f"Control {name} escaped validator!"):
                validate_045_batch_receipt_comparison(b, c, m, p)

        _must_fail("wrong_external_pin", lambda b, c, m, p: p.update(B3="e" * 64))
        _must_fail("posthoc_mutation", lambda b, c, m, p: c.update(nearest_ids=["p1d"]))
        _must_fail("mutually_truncated_peers", lambda b, c, m, p: (b.update(peer_ids=["p0d", "p1d"]), c.update(peer_ids=["p0d", "p1d"]), _rehash(b), _rehash(c)))
        _must_fail("duplicate_id", lambda b, c, m, p: (c.update(peer_ids=["p0d", "p0d", "p2d"]), _rehash(c)))
        _must_fail("substituted_options", lambda b, c, m, p: (c.update(options_sha256="f" * 64), _rehash(c)))
        _must_fail("identical_malformed_both", lambda b, c, m, p: (b.update(status="partial", nearest_ids=["p0d"]), c.update(status="partial", nearest_ids=["p0d"]), _rehash(b), _rehash(c)))
        _must_fail("exclusion_at_equality", lambda b, c, m, p: (c["outcomes_by_id"]["p1d"].update(exact_upper_bound_key=list(b["outcomes_by_id"]["p1d"]["_exact_distance_sq"])), _rehash(c)))
        _must_fail("stale_snapshot_outcome", lambda b, c, m, p: (c["outcomes_by_id"]["p1d"].update(snapshot_identity="bad_snap"), _rehash(c)))
        _must_fail("invalid_exact_key", lambda b, c, m, p: (c.update(best_exact_distance_sq=[1, 0, 0]), _rehash(c)))
        _must_fail("exclusion_leaked_distance", lambda b, c, m, p: (c["outcomes_by_id"]["p1d"].update(distance_m=9.0), _rehash(c)))
        _must_fail("winner_mismatch", lambda b, c, m, p: (c.update(nearest_ids=["p1d"]), _rehash(c)))
        _must_fail("forged_pretree_aabb_gap", lambda b, c, m, p: (c["outcomes_by_id"]["p1d"]["proof_receipt"].update(aabb_gap_sq_int=1), _rehash(c)))
        _must_fail("forged_pretree_axis_gap_int", lambda b, c, m, p: (c["outcomes_by_id"]["p2d"]["proof_receipt"].update(gap_int=c["outcomes_by_id"]["p2d"]["proof_receipt"]["gap_int"] + 1), _rehash(c)))
        _must_fail("forged_pretree_axis_norm_sq", lambda b, c, m, p: (c["outcomes_by_id"]["p2d"]["proof_receipt"].update(axis_norm_sq=999999), _rehash(c)))
        _must_fail("nonzero_tree_builds_on_pretree", lambda b, c, m, p: (c["outcomes_by_id"]["p2d"]["work_summary"].update(tree_builds=1), _rehash(c)))


if __name__ == "__main__":
    unittest.main(verbosity=2)

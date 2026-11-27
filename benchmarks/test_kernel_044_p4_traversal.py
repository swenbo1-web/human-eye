"""BVH-044 (P4): Exact Traversal Hot-Loop (P4-A) & Cross-Pair Cutoff Batch Nearest (P4-B) Verification Suite."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.bvh_eval import _analyze_sig, _closed_sig, _surface_sig, _work_summary
from benchmarks.run_kernel_042_research import (
    FROZEN_RUNTIME_SHA,
    activate_arm,
    build_042_workloads,
    ensure_frozen_arm_a,
    load_arm_modules,
    measure_raw_trees_for_arm,
    assert_raw_trees_equal,
)
from benchmarks.run_kernel_044_p4_traversal import FROZEN_ARM_K_RUNTIME_SHA, ensure_frozen_arm_k
from human_eye_plugin import mesh_structure as cur_ms, surface_geometry as cur_sg, surface_proximity as cur_sp
import human_eye_module1_operators  # noqa: F401
from verification import test_surface_geometry as tsg

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


def _tri_mesh(oid, z, dx=0.0, dy=0.0):
    return SimpleNamespace(
        object_id=oid, name=oid,
        vertices=((0.0 + dx, 0.0 + dy, z), (1.0 + dx, 0.0 + dy, z), (0.0 + dx, 1.0 + dy, z)),
        faces=((0, 1, 2),),
    )


class TestKernel044P4Traversal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.arm_a = load_arm_modules("A_frozen", ensure_frozen_arm_a())
            cls.arm_k = load_arm_modules("K_frozen", ensure_frozen_arm_k())
            if cls.arm_a.source_sha256 != FROZEN_RUNTIME_SHA:
                raise AssertionError(f"Arm A sha mismatch: {cls.arm_a.source_sha256}")
            if cls.arm_k.source_sha256 != FROZEN_ARM_K_RUNTIME_SHA:
                raise AssertionError(f"Arm K sha mismatch: {cls.arm_k.source_sha256}")
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

    def test_01_p4a_exact_surface_sig_and_work_ledger_equality_vs_arm_k(self):
        """P4-A preserves 100% _surface_sig, raw trees, _work_summary, and projection ledgers vs Arm K."""
        for w in self.workloads["singles"]:
            l_tup, r_tup = w["tuple_pair"]
            tk = measure_raw_trees_for_arm(self.arm_k, l_tup, r_tup)
            _restore_live()
            bd = cur_sp._Work(NOOP, {})
            recs, _ = cur_sp._admit((l_tup, r_tup), bd)
            _, _, prep = cur_sp._integer_frame(recs, bd)
            roots_cur = cur_sp._distance_roots(prep, bd)
            assert_raw_trees_equal(tk["roots"][0], roots_cur[0], f"{w['id']}.L")
            assert_raw_trees_equal(tk["roots"][1], roots_cur[1], f"{w['id']}.R")

            for mode in ("settled_credit_031_ref", "off", "off_paid_dequeue_ref"):
                activate_arm(self.arm_k)
                rk = self.arm_k.sp.measure_surface_proximity(
                    l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=mode
                )
                _restore_live()
                rp = cur_sp.measure_surface_proximity(
                    l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=mode
                )
                self.assertEqual(_surface_sig(rk), _surface_sig(rp), f"{w['id']}/{mode}")
                self.assertEqual(rk["work"], rp["work"], f"{w['id']}/{mode} ledger mismatch")

    def test_02_p4b_cutoff_exactness_ties_zero_and_bit_budget(self):
        """Verify _upper_bound_sq_key exact tie preservation, strict pruning, zero-dist, extreme bits & bad inputs."""
        # Non-linear BVH pair (> LINEAR_PAIR_LIMIT = 256)
        sheet_w = next(x for x in self.workloads["singles"] if x["id"] == "Sheet_Parallel_5um")
        sl, sr = sheet_w["tuple_pair"]
        ref = cur_sp.measure_surface_proximity(sl, sr, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        exact_key = ref["_exact_distance_sq"]

        # Exact tie cutoff == true distance MUST NOT prune!
        tie_out = cur_sp.measure_surface_proximity(
            sl, sr, NOOP, retain_exact_rank=True, retain_witness_triangles=True,
            _upper_bound_sq_key=exact_key,
        )
        self.assertFalse(tie_out.get("cutoff_pruned", False))
        self.assertEqual(_surface_sig(ref), _surface_sig(tie_out))

        # Strictly tighter cutoff < true distance MUST prune cleanly
        tight_key = [1, 10**12, exact_key[2]]  # tiny positive distance << true distance
        pruned_out = cur_sp.measure_surface_proximity(
            sl, sr, NOOP, retain_exact_rank=True, _upper_bound_sq_key=tight_key,
        )
        self.assertTrue(pruned_out["measurement_valid"])
        self.assertTrue(pruned_out["cutoff_pruned"])
        self.assertTrue(pruned_out["pruned_strictly_above_cutoff"])
        self.assertGreater(pruned_out["work"].get("cutoff_pruned_pairs", 0), 0)

        # Linear path (< LINEAR_PAIR_LIMIT): tie vs strict
        la = _tri_mesh("la", 0.0)
        lb = _tri_mesh("lb", 2.0)  # d^2 = 4 -> exact key [1, 1, 2]
        lin_ref = cur_sp.measure_surface_proximity(la, lb, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        lin_tie = cur_sp.measure_surface_proximity(
            la, lb, NOOP, retain_exact_rank=True, retain_witness_triangles=True,
            _upper_bound_sq_key=lin_ref["_exact_distance_sq"],
        )
        self.assertFalse(lin_tie.get("cutoff_pruned", False))
        self.assertEqual(_surface_sig(lin_ref), _surface_sig(lin_tie))

        lin_pruned = cur_sp.measure_surface_proximity(
            la, lb, NOOP, retain_exact_rank=True, _upper_bound_sq_key=[3, 1, 0],  # 3 < 4
        )
        self.assertTrue(lin_pruned["cutoff_pruned"])

        # Zero distance touching pair with cutoff=[0, 1, 0] MUST NOT prune
        lc = _tri_mesh("lc", 0.0)
        z_out = cur_sp.measure_surface_proximity(la, lc, NOOP, retain_exact_rank=True, _upper_bound_sq_key=[0, 1, 0])
        self.assertFalse(z_out.get("cutoff_pruned", False))
        self.assertEqual(z_out["distance_m"], 0.0)

        # Extreme shift > MAX_BITS must fail closed (run exact instead of overflow/prune)
        extreme_out = cur_sp.measure_surface_proximity(
            la, lb, NOOP, retain_exact_rank=True, retain_witness_triangles=True,
            _upper_bound_sq_key=[1, 1, 100000],
        )
        self.assertFalse(extreme_out.get("cutoff_pruned", False))
        self.assertEqual(_surface_sig(lin_ref), _surface_sig(extreme_out))

        # Invalid _upper_bound_sq_key raises ValueError
        for bad in ([1, 0, 0], [-1, 1, 0], [1, 1], "bad", [1.0, 1, 0]):
            with self.assertRaises(ValueError):
                cur_sp.measure_surface_proximity(la, lb, NOOP, _upper_bound_sq_key=bad)

    def test_03_p4b_batch_nearest_exact_parity_d48_assembly24_and_permutations(self):
        """Verify measure_nearest_surface_batch matches _rank_surface_results on D48, Assembly24, reversed & ties."""
        for bid in ("D48_Real_47pairs", "Assembly24_Obj014_23pairs"):
            b = next(x for x in self.workloads["batches"] if x["id"] == bid)
            tg, ps = b["tuple_batch"]
            ex_map = {
                str(i): cur_sp.measure_surface_proximity(
                    tg, p, NOOP, retain_exact_rank=True, retain_witness_triangles=True
                )
                for i, p in enumerate(ps)
            }
            ranked = cur_sp._rank_surface_results(ex_map, NOOP)
            exp_idx = [int(i) for i in ranked["ordered_object_id_groups"][0]]
            exp_sq = ex_map[str(exp_idx[0])]["_exact_distance_sq"]

            for sort_aabb in (False, True):
                for use_cache in (False, True):
                    res = cur_sp.measure_nearest_surface_batch(
                        tg, ps, NOOP, use_mesh_cache=use_cache, use_cutoff=True,
                        sort_by_aabb=sort_aabb, retain_witness_triangles=True,
                    )
                    self.assertTrue(res["measurement_valid"])
                    self.assertEqual(res["nearest_indices"], exp_idx)
                    self.assertEqual(res["best_exact_distance_sq"], exp_sq)
                    self.assertEqual(
                        [_surface_sig(res["results_by_index"][i]) for i in res["nearest_indices"]],
                        [_surface_sig(ex_map[str(i)]) for i in exp_idx],
                    )
                    if sort_aabb:
                        min_pruned = 40 if bid == "D48_Real_47pairs" else 17
                        self.assertGreaterEqual(res["cutoff_pruned_count"], min_pruned)

            # Reversed peer ordering parity
            rev_res = cur_sp.measure_nearest_surface_batch(
                tg, list(reversed(ps)), NOOP, use_mesh_cache=True, use_cutoff=True, sort_by_aabb=True
            )
            mapped_idx = sorted(len(ps) - 1 - i for i in rev_res["nearest_indices"])
            self.assertEqual(mapped_idx, exp_idx)
            self.assertEqual(rev_res["best_exact_distance_sq"], exp_sq)

        # Synthetic batch with 3 exact tied nearest peers at mixed offsets & far distractors
        target = _tri_mesh("t", 0.0)
        peers = [
            _tri_mesh("far0", 10.0),
            _tri_mesh("tieA", 1.5, dx=0.1),
            _tri_mesh("mid1", 2.0),
            _tri_mesh("tieB", -1.5, dy=0.2),
            _tri_mesh("far2", 99.0),
            _tri_mesh("tieC", 1.5, dx=0.3),
        ]
        res_ties = cur_sp.measure_nearest_surface_batch(
            target, peers, NOOP, use_mesh_cache=True, use_cutoff=True, sort_by_aabb=True,
            retain_witness_triangles=True,
        )
        self.assertTrue(res_ties["measurement_valid"])
        self.assertEqual(res_ties["nearest_indices"], [1, 3, 5])
        self.assertEqual(res_ties["cutoff_pruned_count"], 3)

    def test_04_cancellation_cache_and_shared_consumers(self):
        """Verify cancellation + clean retry, _prepared_holder ABI, analyze, and closed-solid parity."""
        w = next(x for x in self.workloads["singles"] if x["id"] == "Sheet_Dented_2mm")
        l_tup, r_tup = w["tuple_pair"]
        activate_arm(self.arm_a)
        ref = self.arm_a.sp.measure_surface_proximity(l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        _restore_live()

        for stage, hit in (("surface_proximity_aabb_bound_tests", 5), ("surface_proximity_publish", 1)):
            hits = 0

            def cp(st):
                nonlocal hits
                if st == stage:
                    hits += 1
                    if hits == hit:
                        raise _CancelStop()

            with self.assertRaises(_CancelStop):
                cur_sp.measure_surface_proximity(l_tup, r_tup, cp)

        retry = cur_sp.measure_surface_proximity(l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        self.assertEqual(_surface_sig(ref), _surface_sig(retry))

        hc = {}
        rh = cur_sp.measure_surface_proximity(
            l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _prepared_holder=hc
        )
        self.assertIn("trees", hc)
        self.assertEqual(_surface_sig(ref), _surface_sig(rh))

        # analyze & closed-solid parity
        tube = next(x for x in self.workloads["singles"] if x["id"] == "Tube_Coiled_Loose")
        tl, _ = tube["tuple_pair"]
        faces = [list(t) for t in tl.faces]
        raw = tsg.prepared(tl.vertices, faces)
        activate_arm(self.arm_a)
        an_a = self.arm_a.sg.analyze(raw, faces, list(range(len(faces))), budget=self.arm_a.ms.WorkBudget(), near_m=0.0)
        cs_a = self.arm_a.sg.classify_closed_solids(*self.workloads["singles"][5]["tuple_pair"], NOOP)
        _restore_live()
        an_c = cur_sg.analyze(raw, faces, list(range(len(faces))), budget=cur_ms.WorkBudget(), near_m=0.0)
        cs_c = cur_sg.classify_closed_solids(*self.workloads["singles"][5]["tuple_pair"], NOOP)
        self.assertEqual(_analyze_sig(an_a), _analyze_sig(an_c))
        self.assertEqual(_closed_sig(cs_a), _closed_sig(cs_c))


if __name__ == "__main__":
    unittest.main(verbosity=2)

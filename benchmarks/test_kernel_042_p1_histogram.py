"""BVH-042 Phase 1 (042-P1) Exact 11-Cut Histogram & SAH Eval Verification Suite."""
from __future__ import annotations

from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.bvh_eval import _analyze_sig, _closed_sig, _surface_sig, _work_summary
from benchmarks.run_kernel_042_p1_histogram import FROZEN_ARM_F_RUNTIME_SHA, ensure_frozen_arm_f
from benchmarks.run_kernel_042_research import (
    FROZEN_RUNTIME_SHA,
    activate_arm,
    assert_raw_trees_equal,
    build_042_workloads,
    ensure_frozen_arm_a,
    load_arm_modules,
    measure_raw_trees_for_arm,
)
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


class _BudgetStub:
    def __init__(self, checkpoint=None):
        self.units = 0
        self.checkpoint = checkpoint

    def consume(self, amount, stage):
        if self.checkpoint is not None:
            self.checkpoint("surface_proximity_" + stage)
        self.units += amount


def _classify_11cut(cval, cmin, cspan):
    acc = cspan + 11
    t1 = cmin + acc // 12; acc += cspan
    t2 = cmin + acc // 12; acc += cspan
    t3 = cmin + acc // 12; acc += cspan
    t4 = cmin + acc // 12; acc += cspan
    t5 = cmin + acc // 12; acc += cspan
    t6 = cmin + acc // 12; acc += cspan
    t7 = cmin + acc // 12; acc += cspan
    t8 = cmin + acc // 12; acc += cspan
    t9 = cmin + acc // 12; acc += cspan
    t10 = cmin + acc // 12; acc += cspan
    t11 = cmin + acc // 12
    if cval < t6:
        if cval < t3:
            return 0 if cval < t1 else (1 if cval < t2 else 2)
        return 3 if cval < t4 else (4 if cval < t5 else 5)
    if cval < t9:
        return 6 if cval < t7 else (7 if cval < t8 else 8)
    return 9 if cval < t10 else (10 if cval < t11 else 11)


class TestKernel042P1Histogram(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.arm_a = load_arm_modules("A_frozen", ensure_frozen_arm_a())
            cls.arm_f = load_arm_modules("F_frozen", ensure_frozen_arm_f())
            if cls.arm_a.source_sha256 != FROZEN_RUNTIME_SHA:
                raise AssertionError(f"Arm A sha mismatch: {cls.arm_a.source_sha256}")
            if cls.arm_f.source_sha256 != FROZEN_ARM_F_RUNTIME_SHA:
                raise AssertionError(f"Arm F sha mismatch: {cls.arm_f.source_sha256}")
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

    def test_01_11cut_bin_classification_over_100000_exact_checks(self):
        """Exhaustive tiny spans 1..24 + colliding cuts + random + 1024-bit boundaries."""
        rng = random.Random(202604201)
        checks = 0
        # Exhaustive for all tiny spans 1..24 across cmin in {0, -17}
        for cmin in (0, -17):
            for cspan in range(1, 25):
                for cval in range(cmin, cmin + cspan + 1):
                    old_b = min(11, ((cval - cmin) * 12) // cspan)
                    new_b = _classify_11cut(cval, cmin, cspan)
                    self.assertEqual(old_b, new_b, f"cmin={cmin} span={cspan} c={cval}")
                    checks += 1
        # Spans 25..512 and power-of-2 neighbors through 1024 bits
        spans = list(range(25, 513))
        for bits in range(10, 1025, 11):
            p2 = 1 << bits
            spans.extend((p2 - 1, p2, p2 + 1))
        spans.append((1 << 1024) - 1)
        for cspan in spans:
            cmin = -((cspan * 5) // 13) if cspan % 2 else 0
            acc = cspan + 11
            cuts = []
            for _ in range(11):
                cuts.append(cmin + acc // 12)
                acc += cspan
            pts = {cmin, cmin + cspan}
            for t in cuts:
                for cand in (t - 1, t, t + 1):
                    if cmin <= cand <= cmin + cspan:
                        pts.add(cand)
            for _ in range(140):
                pts.add(cmin + rng.randint(0, cspan))
            for cval in pts:
                old_b = min(11, ((cval - cmin) * 12) // cspan)
                new_b = _classify_11cut(cval, cmin, cspan)
                self.assertEqual(old_b, new_b, f"cmin={cmin} span={cspan} c={cval}")
                checks += 1
        self.assertGreaterEqual(checks, 100000)

    def test_02_complete_raw_tree_parity_manifest_and_edge_spans(self):
        """Complete raw-tree node/leaf parity vs frozen 119327bbb and 5102f1fef."""
        for w in self.workloads["singles"]:
            l_tup, r_tup = w["tuple_pair"]
            ta = measure_raw_trees_for_arm(self.arm_a, l_tup, r_tup)
            _restore_live()
            budget = cur_sp._Work(NOOP, {})
            rec, _ = cur_sp._admit((l_tup, r_tup), budget)
            _, _, prep = cur_sp._integer_frame(rec, budget)
            rc = cur_sp._distance_roots(prep, budget)
            assert_raw_trees_equal(ta["roots"][0], rc[0], f"{w['id']}.L")
            assert_raw_trees_equal(ta["roots"][1], rc[1], f"{w['id']}.R")

        edge_bounds = []
        # Tiny collapsing spans cspan = 1, 2, 5, 11, 12 across > 12 faces
        for span in (1, 2, 5, 11, 12):
            pts = [((i % (span + 1), (i * 2) % (span + 1), (i * 3) % (span + 1)),
                    ((i % (span + 1)) + 1, ((i * 2) % (span + 1)) + 1, ((i * 3) % (span + 1)) + 1))
                   for i in range(40)]
            edge_bounds.append((f"tiny_span_{span}", pts, 2))
        # Empty bins + 1100-bit + dyadic scaling + leaf_size=16 & n=14
        huge = 1 << 1100
        edge_bounds.append((
            "huge_1100bit",
            [((-huge + i * (1 << 1085), -10, i), (-huge + i * (1 << 1085) + 3, 20, i + 5)) for i in range(48)],
            2,
        ))
        edge_bounds.append(("leaf16_n14", [((i, 0, 0), (i + 1, 1, 1)) for i in range(14)], 16))
        for name, bounds, leaf_size in edge_bounds:
            activate_arm(self.arm_a)
            ba = _BudgetStub()
            ta = self.arm_a.sg._bvh(bounds, ba, leaf_size=leaf_size)
            _restore_live()
            bc = _BudgetStub()
            tc = cur_sg._bvh(bounds, bc, leaf_size=leaf_size)
            self.assertEqual(ba.units, bc.units)
            assert_raw_trees_equal(ta, tc, name)

    def test_03_empty_bin_skip_and_scalar_first_tie_breaking_stress(self):
        """Construct equal-cost ties across axes and across empty bins; assert identical choices vs Arm A."""
        # Symmetric boxes spaced so intermediate bins stay empty and X/Y/Z axes produce exact equal SAH cost
        sym_bounds = []
        for k in range(20):
            # Two separated clusters on X, Y, Z symmetrically
            off = 0 if k < 10 else 100
            sym_bounds.append(((off + (k % 10), off + (k % 10), off + (k % 10)),
                               (off + (k % 10) + 2, off + (k % 10) + 2, off + (k % 10) + 2)))
        activate_arm(self.arm_a)
        ta = self.arm_a.sg._bvh(sym_bounds, _BudgetStub(), leaf_size=2)
        _restore_live()
        tc = cur_sg._bvh(sym_bounds, _BudgetStub(), leaf_size=2)
        assert_raw_trees_equal(ta, tc, "symmetric_equal_cost_tie")

        # Sparse middle empty bins with varied box sizes inducing cross-axis cost ties
        rng = random.Random(777)
        for trial in range(25):
            bset = []
            for i in range(36):
                grp = 0 if i < 12 else (1000 if i < 24 else 5000)
                x = grp + rng.randint(0, 4)
                y = (i % 3) * rng.randint(0, 2)
                z = (i % 2) * rng.randint(0, 5)
                bset.append(((x, y, z), (x + 1 + (i % 2), y + 2, z + 3)))
            activate_arm(self.arm_a)
            ta_i = self.arm_a.sg._bvh(bset, _BudgetStub(), leaf_size=2)
            _restore_live()
            tc_i = cur_sg._bvh(bset, _BudgetStub(), leaf_size=2)
            assert_raw_trees_equal(ta_i, tc_i, f"empty_bin_tie_{trial}")

    def test_04_mid_histogram_cancellation_and_shared_consumers(self):
        """Verify mid-histogram n>=512 cancellation, retry, analyze(), and closed-solid parity."""
        w = next(x for x in self.workloads["singles"] if x["id"] == "Sheet_Dented_2mm")
        l_tup, r_tup = w["tuple_pair"]
        activate_arm(self.arm_a)
        ref = self.arm_a.sp.measure_surface_proximity(l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        _restore_live()

        cp_hits = {}
        _ = cur_sp.measure_surface_proximity(l_tup, r_tup, lambda st: cp_hits.__setitem__(st, cp_hits.get(st, 0) + 1))
        # Fused loop (every 256) + 3 axes histogram loop (every 256) + partition loop -> elevated checkpoints
        self.assertGreater(cp_hits.get("surface_proximity_surface_bvh_build", 0), 8)

        for hit_target in (2, 5, 10):
            hits = 0

            def cp(st):
                nonlocal hits
                if st == "surface_proximity_surface_bvh_build":
                    hits += 1
                    if hits == hit_target:
                        raise _CancelStop()

            with self.assertRaises(_CancelStop):
                cur_sp.measure_surface_proximity(l_tup, r_tup, cp)

        retry = cur_sp.measure_surface_proximity(l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        self.assertEqual(_surface_sig(ref), _surface_sig(retry))
        self.assertEqual(_work_summary(ref["work"]), _work_summary(retry["work"]))

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

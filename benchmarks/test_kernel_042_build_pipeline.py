"""BVH-042 Exact Build-Pipeline Verification & Differential Regression Suite."""
from __future__ import annotations

import math
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.bvh_eval import _analyze_sig, _closed_sig, _surface_sig, _work_summary
from benchmarks.run_kernel_042_research import (
    ARMS_ROOT,
    FROZEN_RUNTIME_SHA,
    activate_arm,
    assert_raw_trees_equal,
    build_042_workloads,
    ensure_frozen_arm_a,
    load_arm_modules,
    measure_raw_trees_for_arm,
)
from human_eye_plugin import mesh_structure as cur_ms, runtime_identity as cur_rid, surface_geometry as cur_sg, surface_proximity as cur_sp
import human_eye_module1_operators  # noqa: F401
from verification import test_surface_geometry as tsg

_LIVE_MODS = {
    k: v for k, v in sys.modules.items()
    if k == "human_eye_plugin" or k.startswith("human_eye_plugin.")
    or k == "human_eye_module1_operators" or k.startswith("human_eye_module1_operators.")
}


def _restore_live_modules():
    for k in list(sys.modules):
        if (k == "human_eye_plugin" or k.startswith("human_eye_plugin.")
                or k == "human_eye_module1_operators" or k.startswith("human_eye_module1_operators.")):
            sys.modules.pop(k, None)
    sys.modules.update(_LIVE_MODS)


NOOP = lambda _stage: None


class _CancelStop(RuntimeError):
    pass


def _collect_ids_and_check_bounds(node, flat_bounds, min_id_out=None):
    lo, hi, count, ids, left, right = node
    if ids is not None:
        assert len(ids) == count
        ex_lo = tuple(min(flat_bounds[i][k] for i in ids) for k in range(3))
        ex_hi = tuple(max(flat_bounds[i][3 + k] for i in ids) for k in range(3))
        if lo != ex_lo or hi != ex_hi:
            raise AssertionError(f"Leaf bounds mismatch: {lo, hi} != {ex_lo, ex_hi}")
        return list(ids)
    l_ids = _collect_ids_and_check_bounds(left, flat_bounds)
    r_ids = _collect_ids_and_check_bounds(right, flat_bounds)
    all_ids = l_ids + r_ids
    assert len(all_ids) == count
    ex_lo = tuple(min(left[0][k], right[0][k]) for k in range(3))
    ex_hi = tuple(max(left[1][k], right[1][k]) for k in range(3))
    if lo != ex_lo or hi != ex_hi:
        raise AssertionError(f"Internal bounds mismatch: {lo, hi} != {ex_lo, ex_hi}")
    return all_ids


class _BudgetStub:
    def __init__(self, checkpoint=None):
        self.units = 0
        self.checkpoint = checkpoint

    def consume(self, amount, stage):
        if self.checkpoint is not None:
            self.checkpoint("surface_proximity_" + stage)
        self.units += amount


def _bounds_to_flat(bounds):
    return [(a[0], a[1], a[2], b[0], b[1], b[2], a[0] + b[0], a[1] + b[1], a[2] + b[2]) for a, b in bounds]


class TestKernel042BuildPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            arm_a_dir = ensure_frozen_arm_a()
            cls.arm_a = load_arm_modules("A_frozen", arm_a_dir)
            if cls.arm_a.source_sha256 != FROZEN_RUNTIME_SHA:
                raise AssertionError(f"Frozen Arm A digest mismatch: {cls.arm_a.source_sha256}")
            cls.workloads = build_042_workloads()
        finally:
            _restore_live_modules()

    @classmethod
    def tearDownClass(cls):
        _restore_live_modules()

    def setUp(self):
        _restore_live_modules()

    def tearDown(self):
        _restore_live_modules()

    def test_01_b2_local_predicate_equivalence_over_92449_cases(self):
        """Repeat B2 vs old division predicate equivalence across spans 1..512 and up to 1024-bit boundaries."""
        rng = random.Random(2026042)
        spans = list(range(1, 513))
        for bits in range(10, 1025, 17):
            p2 = 1 << bits
            spans.extend((p2 - 1, p2, p2 + 1))
        spans.append((1 << 1024) - 1)
        B = 12
        max_bin = B - 1
        checks = 0
        for span in spans:
            cmin = -((span * 3) // 7) if (span % 3 == 0) else 0
            for split in range(1, B):
                cut = cmin + (split * span + B - 1) // B
                pts = {cmin, cmin + span}
                for cand in (cut - 1, cut, cut + 1):
                    if cmin <= cand <= cmin + span:
                        pts.add(cand)
                for _ in range(10):
                    pts.add(cmin + rng.randint(0, span))
                for c in pts:
                    b = ((c - cmin) * B) // span
                    if b > max_bin:
                        b = max_bin
                    old_left = (b < split)
                    new_left = (c < cut)
                    self.assertEqual(
                        old_left, new_left,
                        f"span={span}, cmin={cmin}, split={split}, c={c}, cut={cut}, b={b}",
                    )
                    checks += 1
        self.assertGreaterEqual(checks, 92449)

    def test_02_complete_raw_tree_equivalence_manifest_and_synthetic_edges(self):
        """Compare complete recursive raw trees against frozen 119327b on all manifest + edge cases."""
        # A. Manifest workloads
        for w in self.workloads["singles"]:
            l_tup, r_tup = w["tuple_pair"]
            trees_a = measure_raw_trees_for_arm(self.arm_a, l_tup, r_tup)
            _restore_live_modules()
            # Current tree on live package
            budget_cur = cur_sp._Work(NOOP, {})
            rec_cur, _ = cur_sp._admit((l_tup, r_tup), budget_cur)
            _, _, prep_cur = cur_sp._integer_frame(rec_cur, budget_cur)
            roots_cur = cur_sp._distance_roots(prep_cur, budget_cur)
            assert_raw_trees_equal(trees_a["roots"][0], roots_cur[0], f"{w['id']}.L")
            assert_raw_trees_equal(trees_a["roots"][1], roots_cur[1], f"{w['id']}.R")

        # B. Synthetic edge suite directly on _bvh vs frozen Arm A _bvh & _bvh_from_flat_bounds
        edge_cases = []
        edge_cases.append(("n1", [((0, 0, 0), (1, 2, 3))], 2))
        edge_cases.append(("n2", [((0, 0, 0), (1, 1, 1)), ((2, 3, 4), (5, 6, 7))], 2))
        for n in (3, 7, 12, 13):
            edge_cases.append((f"n{n}", [((i, -i, 0), (i + 2, -i + 3, 1)) for i in range(n)], 2))
        # leaf_size=16 and n=14 -> must stop as single leaf without wasted SAH
        edge_cases.append(("leaf16_n14", [((i, 0, 0), (i + 1, 1, 1)) for i in range(14)], 16))
        # Duplicate centroids & all-zero spans
        edge_cases.append(("dup_zero_span", [((-5, 3, 9), (5, -3 + 10, 19)) for _ in range(32)], 2))
        # Mixed empty bins (two clusters far apart + tiny cluster inside)
        edge_cases.append((
            "mixed_empty_bins",
            [((0, 0, 0), (1, 1, 1)) for _ in range(15)]
            + [((100000 + i, 0, 0), (100001 + i, 1, 1)) for i in range(15)]
            + [((500000, 0, 0), (500001, 1, 1)) for _ in range(3)],
            2,
        ))
        # Min-side rejection (1 outlier far away on one axis, huge tight cluster)
        edge_cases.append((
            "min_side_reject",
            [((0, i, 0), (1, i + 1, 1)) for i in range(32)] + [((1000000, 0, 0), (1000001, 1, 1))],
            2,
        ))
        # Depth >= 20 fallback (exponentially shrinking ladder forcing depth > 20)
        deep_bounds = []
        pos = 0
        for k in range(48):
            step = 1 << max(1, 30 - k)
            deep_bounds.append(((pos, 0, 0), (pos + 1, 1, 1)))
            pos += step
        edge_cases.append(("depth_fallback_48", deep_bounds, 1))
        # Skewed IDs & signed >1024-bit integer coordinates
        huge = 1 << 1100
        edge_cases.append((
            "signed_huge_1100bit",
            [((-huge + i * (1 << 1080), -100, i), (-huge + i * (1 << 1080) + 7, 100, i + 5)) for i in range(40)],
            2,
        ))

        for name, bounds, leaf_size in edge_cases:
            ba = _BudgetStub()
            activate_arm(self.arm_a)
            ta = self.arm_a.sg._bvh(bounds, ba, leaf_size=leaf_size)
            _restore_live_modules()
            bc1 = _BudgetStub()
            tc1 = cur_sg._bvh(bounds, bc1, leaf_size=leaf_size)
            bc2 = _BudgetStub()
            tc2 = cur_sg._bvh_from_flat_bounds(_bounds_to_flat(bounds), bc2, leaf_size=leaf_size)
            self.assertEqual(ba.units, bc1.units, f"{name}: work unit mismatch")
            self.assertEqual(ba.units, bc2.units, f"{name}: flat work unit mismatch")
            assert_raw_trees_equal(ta, tc1, f"{name}.bvh")
            assert_raw_trees_equal(ta, tc2, f"{name}.flat")
            flat = _bounds_to_flat(bounds)
            covered_ids = _collect_ids_and_check_bounds(tc2, flat)
            self.assertEqual(sorted(covered_ids), list(range(len(bounds))), f"{name}: triangle coverage")

        # 13-box dyadic scaling & translation invariance on SAH tree & solver
        rng = random.Random(4242)
        base_bounds = []
        for i in range(25):
            x = rng.randint(-1000, 1000)
            y = rng.randint(-1000, 1000)
            z = rng.randint(-1000, 1000)
            base_bounds.append(((x, y, z), (x + 13, y + 17, z + 19)))
        t_base = cur_sg._bvh(base_bounds, _BudgetStub(), leaf_size=2)
        # Dyadic scale by 2^5 + translate by (100, -200, 300)
        tx, ty, tz = 100, -200, 300
        scaled_bounds = [
            (((lo[0] << 5) + tx, (lo[1] << 5) + ty, (lo[2] << 5) + tz),
             ((hi[0] << 5) + tx, (hi[1] << 5) + ty, (hi[2] << 5) + tz))
            for lo, hi in base_bounds
        ]
        t_scaled = cur_sg._bvh(scaled_bounds, _BudgetStub(), leaf_size=2)
        # Exact structural tree topology + leaf IDs must remain invariant under uniform dyadic scaling + translation
        def strip_bounds(node):
            _lo, _hi, cnt, ids, l, r = node
            if ids is not None:
                return (cnt, list(ids))
            return (cnt, strip_bounds(l), strip_bounds(r))
        self.assertEqual(strip_bounds(t_base), strip_bounds(t_scaled))

    def test_03_b4_holder_abi_compile_parity_and_projection_modes(self):
        """Verify prepared_holder['trees'] ABI, compiled tree parity, and 3 projection modes vs frozen A."""
        w = next(x for x in self.workloads["singles"] if x["id"] == "Rotated_30deg_Spheres")
        l_tup, r_tup = w["tuple_pair"]
        for mode in ("settled_credit_031_ref", "off", "off_paid_dequeue_ref"):
            activate_arm(self.arm_a)
            res_a = self.arm_a.sp.measure_surface_proximity(
                l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=mode,
            )
            ha = {}
            _ = self.arm_a.sp.measure_surface_proximity(
                l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True,
                _prepared_holder=ha, _projection_mode=mode,
            )
            comp_a0 = self.arm_a.sp._compile_bvh_node(ha["trees"]["roots"][0], 2)
            _restore_live_modules()

            hc = {}
            res_c = cur_sp.measure_surface_proximity(
                l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True,
                _prepared_holder=hc, _projection_mode=mode,
            )
            self.assertEqual(_surface_sig(res_a), _surface_sig(res_c))
            self.assertEqual(_work_summary(res_a["work"]), _work_summary(res_c["work"]), f"work mismatch on {mode}")
            self.assertEqual(set(ha["trees"].keys()), set(hc["trees"].keys()))
            self.assertEqual(ha["trees"]["tree_kind"], hc["trees"]["tree_kind"])
            self.assertEqual(ha["trees"]["bounds"], hc["trees"]["bounds"])
            assert_raw_trees_equal(ha["trees"]["roots"][0], hc["trees"]["roots"][0], f"holder.{mode}.L")
            assert_raw_trees_equal(ha["trees"]["roots"][1], hc["trees"]["roots"][1], f"holder.{mode}.R")
            # Compiled trees node-for-node equality
            comp_c0 = cur_sp._compile_bvh_node(hc["trees"]["roots"][0], 2)
            self.assertEqual(comp_a0, comp_c0)

            # Reuse prepared_pair + prepared_trees cleanly
            res_reuse = cur_sp.measure_surface_proximity(
                l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True,
                _prepared_pair=hc["pair"], _prepared_trees=hc["trees"], _projection_mode=mode,
            )
            self.assertTrue(res_reuse["work"]["shared_preparation"])
            self.assertTrue(res_reuse["work"]["shared_trees"])
            self.assertEqual(_surface_sig(res_a), _surface_sig(res_reuse))

    def test_04_cancellation_inside_fused_loops_compile_cache_and_retry(self):
        """Verify cancellation inside n>=512 loops, compile, affine fallback, and clean retry without partial cache."""
        w = next(x for x in self.workloads["singles"] if x["id"] == "Sheet_Dented_2mm")
        l_tup, r_tup = w["tuple_pair"]
        activate_arm(self.arm_a)
        ref = self.arm_a.sp.measure_surface_proximity(l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        _restore_live_modules()

        # Count surface_proximity_surface_bvh_build checkpoints inside loop (n=512 > 256 -> multiple hits per root)
        cp_counts = {}

        def counting_cp(stage):
            cp_counts[stage] = cp_counts.get(stage, 0) + 1

        _ = cur_sp.measure_surface_proximity(l_tup, r_tup, counting_cp, retain_exact_rank=True, retain_witness_triangles=True)
        bvh_hits = cp_counts.get("surface_proximity_surface_bvh_build", 0)
        self.assertGreater(bvh_hits, 2)

        # Cancel uncached at mid-loop (n>=512 fires intra-loop bvh_build checkpoints), child recursion, compile, publish
        for target_stage, hit_target in (
            ("surface_proximity_admission", 1),
            ("surface_proximity_surface_bvh_build", 2),
            ("surface_proximity_surface_bvh_build", 8),
            ("surface_proximity_bvh_compile", 1),
            ("surface_proximity_publish", 1),
        ):
            hits = 0

            def cancelling_cp(stage):
                nonlocal hits
                if stage == target_stage:
                    hits += 1
                    if hits == hit_target:
                        raise _CancelStop(f"cancel:{stage}:{hits}")

            with self.assertRaises(_CancelStop, msg=f"missed cancel on {target_stage}@{hit_target}"):
                cur_sp.measure_surface_proximity(l_tup, r_tup, cancelling_cp)

        # Cancel in cache mode during tree construction, compile, and publish; verify no partial 'tree' stored
        cache = {}
        for target_stage, hit_target in (
            ("surface_proximity_surface_bvh_build", 3),
            ("surface_proximity_bvh_compile", 1),
            ("surface_proximity_publish", 1),
        ):
            hits = 0

            def cancelling_cache_cp(stage):
                nonlocal hits
                if stage == target_stage:
                    hits += 1
                    if hits == hit_target:
                        raise _CancelStop(f"cache_cancel:{stage}:{hits}")

            with self.assertRaises(_CancelStop, msg=f"missed cache cancel on {target_stage}@{hit_target}"):
                cur_sp.measure_surface_proximity(l_tup, r_tup, cancelling_cache_cp, _mesh_cache=cache)
            # Partial entry if admitted must NOT contain broken 'tree'
            for ent in list(cache.values()):
                if isinstance(ent, dict) and "tree" in ent:
                    self.assertIsNotNone(ent["tree"]["local_root"])

        # Fresh retry after cancellations matches frozen Arm A cleanly
        retry = cur_sp.measure_surface_proximity(
            l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _mesh_cache=cache,
        )
        self.assertEqual(_surface_sig(ref), _surface_sig(retry))

    def test_05_shared_sah_consumers_analyze_and_closed_solid(self):
        """Verify surface_geometry.analyze and classify_closed_solids match frozen Arm A identically."""
        tube = next(x for x in self.workloads["singles"] if x["id"] == "Tube_Coiled_Loose")
        l_tup, _ = tube["tuple_pair"]
        faces = [list(tri) for tri in l_tup.faces]
        raw = tsg.prepared(l_tup.vertices, faces)

        activate_arm(self.arm_a)
        an_a = self.arm_a.sg.analyze(raw, faces, list(range(len(faces))), budget=self.arm_a.ms.WorkBudget(), near_m=0.0)
        _restore_live_modules()
        an_c = cur_sg.analyze(raw, faces, list(range(len(faces))), budget=cur_ms.WorkBudget(), near_m=0.0)
        self.assertEqual(_analyze_sig(an_a), _analyze_sig(an_c))

        # Closed solid uses untouched _bvh_median + _nearest_tree
        rot = next(x for x in self.workloads["singles"] if x["id"] == "Rotated_30deg_Spheres")
        rl, rr = rot["tuple_pair"]
        activate_arm(self.arm_a)
        cs_a = self.arm_a.sg.classify_closed_solids(rl, rr, NOOP)
        _restore_live_modules()
        cs_c = cur_sg.classify_closed_solids(rl, rr, NOOP)
        self.assertEqual(_closed_sig(cs_a), _closed_sig(cs_c))
        self.assertEqual(cs_a["work"], cs_c["work"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

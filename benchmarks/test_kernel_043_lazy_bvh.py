"""BVH-043 (P3): Exact Demand-Driven Lazy SAH BVH Verification Suite."""
from __future__ import annotations

from pathlib import Path
import math
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

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
)
from benchmarks.run_kernel_043_lazy_bvh import (
    FROZEN_ARM_K_RUNTIME_SHA,
    assert_visited_lazy_matches_eager,
    ensure_frozen_arm_k,
    run_lazy_c03_paid_dequeue_audit,
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


class TestKernel043LazyBVH(unittest.TestCase):
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

    def test_01_visited_subtree_exact_structural_parity_and_pruned_savings(self):
        """Every expanded/created lazy node equals eager tree at same path; heavy suites expand <10%."""
        for w in self.workloads["singles"]:
            l_tup, r_tup = w["tuple_pair"]
            ta = measure_raw_trees_for_arm(self.arm_a, l_tup, r_tup)
            _restore_live()
            eager_nodes = (
                self._count_nodes(ta["roots"][0]) + self._count_nodes(ta["roots"][1])
            )
            bd = cur_sp._Work(NOOP, {})
            recs, _ = cur_sp._admit((l_tup, r_tup), bd)
            _, _, prep = cur_sp._integer_frame(recs, bd)
            if len(prep[0]) * len(prep[1]) <= cur_sp.LINEAR_PAIR_LIMIT:
                continue
            sink = []
            _ = cur_sp._nearest(prep, bd, _lazy_bvh=True, _lazy_roots_out=sink)
            c0, _, _ = assert_visited_lazy_matches_eager(ta["roots"][0], sink[0], None, f"{w['id']}.L")
            c1, _, _ = assert_visited_lazy_matches_eager(ta["roots"][1], sink[1], None, f"{w['id']}.R")
            created = c0 + c1
            self.assertEqual(created, bd.counts["lazy_bvh_nodes_created"])
            if w["id"] in ("HighRes_1536F_Pair", "Sheet_Dented_2mm", "Sheet_Parallel_5um"):
                self.assertLess(created * 10, eager_nodes, f"{w['id']}: expected <10% tree created ({created}/{eager_nodes})")

    @staticmethod
    def _count_nodes(node):
        if node[3] is not None:
            return 1
        return 1 + TestKernel043LazyBVH._count_nodes(node[4]) + TestKernel043LazyBVH._count_nodes(node[5])

    def test_02_three_projection_modes_and_unexpanded_fast_proj_node_interval(self):
        """Verify 3 projection modes + _FastWitnessProjection._node_interval without forcing expansion."""
        w = next(x for x in self.workloads["singles"] if x["id"] == "HighRes_1536F_Pair")
        l_tup, r_tup = w["tuple_pair"]
        for mode in ("settled_credit_031_ref", "off", "off_paid_dequeue_ref"):
            activate_arm(self.arm_a)
            ra = self.arm_a.sp.measure_surface_proximity(
                l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=mode,
            )
            _restore_live()
            rl = cur_sp.measure_surface_proximity(
                l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=mode,
            )
            self.assertEqual(_surface_sig(ra), _surface_sig(rl))
            self.assertLessEqual(rl["work"]["work_units"], ra["work"]["work_units"])

        # Direct unit check on _FastWitnessProjection._node_interval for unexpanded lazy node
        bd = cur_sp._Work(NOOP, {})
        recs, _ = cur_sp._admit((l_tup, r_tup), bd)
        _, _, prep = cur_sp._integer_frame(recs, bd)
        eager_roots = cur_sp._distance_roots(prep, bd)
        ec0 = cur_sp._compile_bvh_node(eager_roots[0], 0)
        # Construct corresponding unexpanded lazy internal node matching root L's right child
        r_child_eager = eager_roots[0][5]
        def _collect(node):
            return list(node[3]) if node[3] is not None else _collect(node[4]) + _collect(node[5])
        raw_ids = _collect(r_child_eager)
        unexpanded = [
            *r_child_eager[0], *r_child_eager[1], r_child_eager[2],
            None, None, None, min(raw_ids), 0, 0, 0, raw_ids, 1, True, None,
        ]
        fp = cur_sp._FastWitnessProjection.build((1, 1, ('points', (0, 0, 0), (1, 0, 0))), prep[0], prep[1], 1, bd)
        self.assertIsNotNone(fp)
        b_eager = fp._node_interval(ec0[9], fp.node_a, fp.tri_a, fp.prep_a, bd)
        b_lazy = fp._node_interval(unexpanded, fp.node_a, fp.tri_a, fp.prep_a, bd)
        self.assertEqual(b_eager, b_lazy)
        self.assertIsNone(unexpanded[8])  # Confirmed: projection did NOT force split!

    def test_03_lazy_c03_paid_dequeue_sweeps_zero_holes(self):
        """Verify 0 holes vs executed off_paid_dequeue_ref across [0..32] under Lazy BVH."""
        live_arm = load_arm_modules("Live_P3", ROOT)
        try:
            res = run_lazy_c03_paid_dequeue_audit(live_arm)
            for name, row in res.items():
                for vname, vrow in row["vs_M_paid_ref"].items():
                    self.assertEqual(vrow["total_holes"], 0, f"{name}.{vname}")
        finally:
            _restore_live()

    def test_04_cancellation_holder_cache_and_shared_consumers(self):
        """Verify mid-lazy cancellation, clean retry, holder ABI, cache, analyze, and closed-solid parity."""
        w = next(x for x in self.workloads["singles"] if x["id"] == "Sheet_Dented_2mm")
        l_tup, r_tup = w["tuple_pair"]
        activate_arm(self.arm_a)
        ref = self.arm_a.sp.measure_surface_proximity(l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        _restore_live()

        for stage, hit in (("surface_proximity_surface_bvh_build", 2), ("surface_proximity_bvh_compile", 5), ("surface_proximity_publish", 1)):
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

        # prepared_holder ABI & _mesh_cache keep eager roots & full work parity
        hc = {}
        rh = cur_sp.measure_surface_proximity(l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _prepared_holder=hc)
        self.assertIn("trees", hc)
        self.assertFalse(rh["work"].get("lazy_bvh_enabled", False))
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

    def test_05_lazy_tight_headroom_deferral_and_eager_review_parity(self):
        """Verify tight-headroom witness deferral under both lazy (_lazy_bvh=True) and eager (_lazy_bvh=False)."""
        ca_r, sa_r = math.cos(0.6), math.sin(0.6)

        def _rot_d(p):
            x, y, z = p
            x1, z1 = ca_r * x + sa_r * z, -sa_r * x + ca_r * z
            y2, z2 = ca_r * y - sa_r * z1, sa_r * y + ca_r * z1
            return (x1, y2, z2)

        dvl, dfl, dvr, dfr = [], [], [], []
        for i_d in range(12):
            for j_d in range(4):
                b_d = len(dvl)
                xd, yd = i_d * 0.4, j_d * 0.4
                dvl.extend([_rot_d((xd, yd, 0.0)), _rot_d((xd + 0.3, yd, 0.0)), _rot_d((xd, yd + 0.3, 0.0))])
                dfl.append((b_d, b_d + 1, b_d + 2))
                b2_d = len(dvr)
                dvr.extend([_rot_d((xd, yd, 0.5)), _rot_d((xd + 0.3, yd, 0.5)), _rot_d((xd, yd + 0.3, 0.5))])
                dfr.append((b2_d, b2_d + 1, b2_d + 2))
        dfr = list(reversed(dfr))
        for k_d in range(12):
            off_d = k_d * 0.02
            b_d = len(dvl); dvl.extend([(50.0 + off_d, 0.0, 0.16), (50.01 + off_d, 0.0, 0.16), (50.0 + off_d, 0.01, 0.16)]); dfl.append((b_d, b_d + 1, b_d + 2))
            b_d = len(dvl); dvl.extend([(53.0 + off_d, 0.0, 0.00), (53.01 + off_d, 0.0, 0.00), (53.0 + off_d, 0.01, 0.00)]); dfl.append((b_d, b_d + 1, b_d + 2))
            b_d = len(dvr); dvr.extend([(50.0 + off_d, 0.0, 0.85), (50.01 + off_d, 0.0, 0.85), (50.0 + off_d, 0.01, 0.85)]); dfr.append((b_d, b_d + 1, b_d + 2))
            b_d = len(dvr); dvr.extend([(53.0 + off_d, 0.0, 0.65), (53.01 + off_d, 0.0, 0.65), (53.0 + off_d, 0.01, 0.65)]); dfr.append((b_d, b_d + 1, b_d + 2))

        def_l = SimpleNamespace(object_id="def_l", name="def_l", vertices=tuple(dvl), faces=tuple(dfl))
        def_r = SimpleNamespace(object_id="def_r", name="def_r", vertices=tuple(dvr), faces=tuple(dfr))

        lazy_ref = cur_sp.measure_surface_proximity(def_l, def_r, NOOP, retain_exact_rank=True)
        eager_ref = cur_sp.measure_surface_proximity(def_l, def_r, NOOP, retain_exact_rank=True, _lazy_bvh=False)
        lazy_wu = lazy_ref["work"]["work_units"]
        eager_wu = eager_ref["work"]["work_units"]
        self.assertLess(lazy_wu, eager_wu)
        self.assertEqual(lazy_ref["_exact_distance_sq"], eager_ref["_exact_distance_sq"])

        orig_init = cur_sp._Work.__init__

        def _scan_defer(rem_range, lazy_flag, ref_res):
            for rem_try in rem_range:
                def defer_init(inst, cp, diag, base=cur_sp.MAX_WORK_UNITS - rem_try):
                    orig_init(inst, cp, diag)
                    inst.counts["work_units"] = base
                with patch.object(cur_sp._Work, "__init__", defer_init):
                    cand = cur_sp.measure_surface_proximity(
                        def_l, def_r, NOOP, retain_exact_rank=True, _lazy_bvh=lazy_flag
                    )
                if cand["measurement_valid"] and cand["work"].get("witness_projection_budget_deferrals", 0) > 0:
                    return cand
            return None

        r_lazy_def = _scan_defer(range(lazy_wu - 20, lazy_wu + 20), True, lazy_ref)
        self.assertIsNotNone(r_lazy_def, f"Expected lazy tight-headroom deferral around lazy_wu={lazy_wu}")
        self.assertEqual(r_lazy_def["_exact_distance_sq"], lazy_ref["_exact_distance_sq"])
        self.assertLessEqual(r_lazy_def["work"]["work_units"], cur_sp.MAX_WORK_UNITS)

        r_eager_def = _scan_defer(range(eager_wu - 180, eager_wu - 120), False, eager_ref)
        self.assertIsNotNone(r_eager_def, f"Expected eager tight-headroom deferral around eager_wu={eager_wu}")
        self.assertEqual(r_eager_def["_exact_distance_sq"], eager_ref["_exact_distance_sq"])
        self.assertLessEqual(r_eager_def["work"]["work_units"], cur_sp.MAX_WORK_UNITS)


if __name__ == "__main__":
    unittest.main(verbosity=2)

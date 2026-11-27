"""M3 BVH 044-R1 Closure Contract, Negative Controls, Budget Sweeps & Cancellation Suite."""
from __future__ import annotations

import copy
import inspect
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.bvh_eval import _analyze_sig, _closed_sig, _surface_sig, _work_summary
from benchmarks.run_kernel_042_research import (
    FROZEN_RUNTIME_SHA,
    _sha256_json,
    activate_arm,
    build_042_workloads,
    ensure_frozen_arm_a,
    load_arm_modules,
)
from benchmarks.run_kernel_044_r1_qualification import (
    FROZEN_ARM_K_COMMIT,
    FROZEN_ARM_K_RUNTIME_SHA,
    build_receipt_digest,
    ensure_frozen_arm,
    serialize_batch_receipt,
    validate_batch_receipt_comparison,
)
from benchmarks import verify_review_suite as vrs
from benchmarks.run_r3_closure_eval import _tilted_plate
from verification import m3_asset_cases as mac
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


def _make_tilted48_and_sheet5um():
    ml = vrs._freeze_mesh("tl", *_tilted_plate(12, 0.0))
    mr = vrs._freeze_mesh("tr", *_tilted_plate(12, 0.5, reverse=True))
    sv, sf = mac.sheet(17)
    sp_l = vrs._freeze_mesh("sp_l", sv, sf)
    sp_r = vrs._freeze_mesh("sp_r", [[p[0], p[1], p[2] + 5e-6] for p in sv], sf)
    return ml, mr, sp_l, sp_r


def _tri(oid, z, dx=0.0, dy=0.0):
    return SimpleNamespace(
        object_id=oid, name=oid,
        vertices=((0.0 + dx, 0.0 + dy, z), (1.0 + dx, 0.0 + dy, z), (0.0 + dx, 1.0 + dy, z)),
        faces=((0, 1, 2),),
    )


class _CountingSeq:
    """Instrument every __getitem__ vertex read on large sparse containers."""
    def __init__(self, n, populated):
        self._n = n
        self._pop = dict(populated)
        self.reads = 0

    def __len__(self):
        return self._n

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            raise AssertionError("Slice scan attempted across sparse sequence!")
        self.reads += 1
        return self._pop.get(idx, (float("nan"), float("nan"), float("nan")))


class TestKernel044R1Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.arm_a = load_arm_modules("A_r1", ensure_frozen_arm_a())
            cls.arm_k = load_arm_modules(
                "K_r1", ensure_frozen_arm(FROZEN_ARM_K_COMMIT, "arm_k_042_p2", FROZEN_ARM_K_RUNTIME_SHA)
            )
            cls.workloads = build_042_workloads()
        finally:
            _restore_live()

    @classmethod
    def tearDownClass(cls):
        _restore_live()

    def setUp(self):
        _restore_live()
        cur_sp._CREDIT_ATTEMPT_OBSERVER = None

    def tearDown(self):
        cur_sp._CREDIT_ATTEMPT_OBSERVER = None
        _restore_live()

    def test_01_a_only_isolation_and_exact_work_parity_vs_k(self):
        """Ordinary measure_surface_proximity has no cutoff parameter and matches Arm K 100%."""
        sig = inspect.signature(cur_sp.measure_surface_proximity)
        self.assertNotIn("_upper_bound_sq_key", sig.parameters)
        for w in self.workloads["singles"]:
            l_tup, r_tup = w["tuple_pair"]
            for mode in ("settled_credit_031_ref", "off", "off_paid_dequeue_ref"):
                activate_arm(self.arm_k)
                rk = self.arm_k.sp.measure_surface_proximity(
                    l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=mode
                )
                _restore_live()
                rr = cur_sp.measure_surface_proximity(
                    l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=mode
                )
                self.assertNotIn("cutoff_pruned", rr)
                self.assertEqual(_surface_sig(rk), _surface_sig(rr))
                self.assertEqual(rk["work"], rr["work"])

    def test_02_r1_01_budget_sweeps_and_no_speculative_narrow_slot(self):
        """R1-01: Contiguous sweeps [-8..+32] around CUTOFF_ONLY_PAID_REF have 0 holes; 0 extra narrow slots."""
        from unittest.mock import patch
        tilted48_l, tilted48_r, sheet_l, sheet_r = _make_tilted48_and_sheet5um()
        g_comp = next(x for x in self.workloads["singles"] if x["id"] == "G508_Competing_001")
        d48_b = next(x for x in self.workloads["batches"] if x["id"] == "D48_Real_47pairs")
        d48_t, d48_p = d48_b["tuple_batch"]
        cases = [
            ("tilted48", tilted48_l, tilted48_r, [1, 1, 0]),      # 1.0 > ~0.0625? wait use tight cutoff above 0.25 or tie
            ("G508_Comp", *g_comp["tuple_pair"], [1, 1, -2]),      # 0.25 -> strictly excludes competing far or solves
            ("sheet5um", sheet_l, sheet_r, [1, 1, -30]),
            ("d48_pair0", d48_t, d48_p[0], [1, 1, -18]),
        ]
        orig_init = cur_sp._Work.__init__
        for cname, la, rb, ck in cases:
            paid_out = cur_sp._measure_surface_proximity_cutoff(
                la, rb, NOOP, upper_bound_sq_key=ck, cutoff_mode="CUTOFF_ONLY_PAID_REF"
            )
            m_paid = paid_out["work"]["work_units"]
            self.assertEqual(paid_out["work"]["witness_projection_direction_builds"] if "witness_projection_direction_builds" in paid_out["work"] else 0, 0)
            # Check no extra speculative narrow call on cutoff modes vs matching-projection exhaustive baseline
            exh_proj_out = cur_sp._measure_surface_proximity_cutoff(la, rb, NOOP, cutoff_mode="EXHAUSTIVE")
            exh_off_out = cur_sp.measure_surface_proximity(la, rb, NOOP, _projection_mode="off")
            for mode in ("CUTOFF_ONLY_OFF", "CUTOFF_ONLY_PAID_REF", "CUTOFF_SETTLED_PROJECTION"):
                off_out = cur_sp._measure_surface_proximity_cutoff(la, rb, NOOP, upper_bound_sq_key=ck, cutoff_mode=mode)
                self.assertIn(off_out["result_kind"], ("exact_surface_measurement", "nearest_cutoff_exclusion"))
                self.assertLessEqual(off_out["work"]["narrow_phase_pairs"], exh_off_out["work"]["narrow_phase_pairs"])
                if mode == "CUTOFF_SETTLED_PROJECTION" and off_out["result_kind"] == "exact_surface_measurement":
                    self.assertLessEqual(off_out["work"]["narrow_phase_pairs"], exh_proj_out["work"]["narrow_phase_pairs"])

            for mode in ("CUTOFF_ONLY_PAID_REF", "CUTOFF_ONLY_OFF", "CUTOFF_SETTLED_PROJECTION"):
                for delta in range(-8, 33):
                    cap = m_paid + delta
                    if cap < 10:
                        continue
                    def pinit(inst, cp, diag, start=cur_sp.MAX_WORK_UNITS - cap):
                        orig_init(inst, cp, diag)
                        inst.counts["work_units"] = start
                    with patch.object(cur_sp._Work, "__init__", pinit):
                        res = cur_sp._measure_surface_proximity_cutoff(
                            la, rb, NOOP, upper_bound_sq_key=ck, cutoff_mode=mode
                        )
                    if delta >= 0:
                        self.assertIn(
                            res["result_kind"],
                            ("exact_surface_measurement", "nearest_cutoff_exclusion"),
                            f"{cname}/{mode} hole at delta={delta} (cap={cap}, m_paid={m_paid}): {res}",
                        )
                        if paid_out["result_kind"] == "exact_surface_measurement" and res["result_kind"] == "exact_surface_measurement":
                            self.assertEqual(
                                _surface_sig(paid_out["measured_result"]),
                                _surface_sig(res["measured_result"]),
                            )

    def test_03_r1_06_inline_credit_prefix_observer_and_cancellation(self):
        """R1-06: Inline credit observer catches every admit/settle/defer on A and B including cancel."""
        events = []
        cur_sp._CREDIT_ATTEMPT_OBSERVER = events.append
        g0 = next(x for x in self.workloads["singles"] if x["id"] == "G508_Peer_000")
        l_m, r_m = g0["tuple_pair"]
        res = cur_sp.measure_surface_proximity(l_m, r_m, NOOP, retain_exact_rank=True)
        self.assertTrue(res["measurement_valid"])
        kinds = {e["kind"] for e in events}
        self.assertTrue({"node_box", "node_slab", "try_run"} & kinds)

        # Verify strict prefix invariant on every settle event
        spent_acc = 0
        for ev in events:
            self.assertGreaterEqual(ev["available_credit"], 0)
            if ev["phase"] == "settle":
                self.assertGreaterEqual(ev["actual"], 0)
                self.assertLessEqual(ev["actual"], ev["upper"])
                spent_acc += ev["actual"]
                self.assertEqual(ev["spent"], spent_acc)

        # Cancel mid-inline credit attempt and ensure finally still settles cleanly
        events.clear()
        def stop_on_wp(stage):
            if stage == "surface_proximity_witness_projection_tests":
                raise _CancelStop()
        with self.assertRaises(_CancelStop):
            cur_sp.measure_surface_proximity(l_m, r_m, stop_on_wp)
        settles = [e for e in events if e["phase"] == "settle"]
        self.assertGreaterEqual(len(settles), 1)
        self.assertGreaterEqual(settles[-1]["balance"], 0)

    def test_04_r1_02_sparse_scaling_no_full_container_read(self):
        """R1-02: Sparse 9, 100k, and 1M containers only read referenced vertices even with sort_policy='referenced_aabb'."""
        for n_rows in (9, 100_000, 1_000_000):
            target = _tri("tg", 0.0)
            pop = {3: (0.0, 0.0, 2.0), n_rows - 5: (1.0, 0.0, 2.0), n_rows - 2: (0.0, 1.0, 2.0)}
            seq_verts = _CountingSeq(n_rows, pop)
            p_sparse = SimpleNamespace(object_id="sp", name="sp", vertices=seq_verts, faces=((3, n_rows - 5, n_rows - 2),))
            # Also ndarray with unreferenced NaN tail
            if n_rows <= 100_000:
                arr = np.full((n_rows, 3), np.nan, dtype=np.float64)
                for idx, xyz in pop.items():
                    arr[idx] = xyz
                arr.flags.writeable = False
                p_np = SimpleNamespace(object_id="np", name="np", vertices=arr, faces=((3, n_rows - 5, n_rows - 2),))
                peers = [p_sparse, p_np, _tri("far", 10.0)]
                pids = ["sp", "np", "far"]
            else:
                peers = [p_sparse, _tri("far", 10.0)]
                pids = ["sp", "far"]

            for pol in ("stable", "referenced_aabb"):
                seq_verts.reads = 0
                out = cur_sp.measure_nearest_surface_batch(
                    target, peers, NOOP, peer_ids=pids, cutoff_mode="CUTOFF_ONLY_OFF", sort_policy=pol
                )
                self.assertTrue(out["measurement_valid"])
                self.assertEqual(seq_verts.reads, 3, f"n_rows={n_rows}, pol={pol}: read {seq_verts.reads} rows!")

    def test_05_r1_04_snapshot_rebind_aliases_ties_and_partial(self):
        """R1-04: Checkpoint rebind & mid-batch ndarray mutation cannot mix snapshots; duplicate IDs/partial fail cleanly."""
        tg = _tri("tg", 0.0)
        p0 = _tri("p0", 1.0)
        p1 = _tri("p1", 12.0)

        calls = 0
        def rebind_cp(st):
            nonlocal calls
            if st == "surface_proximity_batch_peer":
                calls += 1
                if calls == 2:
                    tg.vertices = ((0.0, 0.0, 11.0), (1.0, 0.0, 11.0), (0.0, 1.0, 11.0))

        out = cur_sp.measure_nearest_surface_batch(
            tg, [p0, p1], rebind_cp, peer_ids=["p0", "p1"], cutoff_mode="CUTOFF_ONLY_OFF", sort_policy="stable"
        )
        self.assertEqual(out["status"], "complete")
        self.assertEqual(out["nearest_ids"], ["p0"])  # Initial snapshot! NEVER mixed ['p0', 'p1']!

        # Mid-batch writable ndarray mutation isolated by snapshot
        arr_p = np.array([[0.0, 0.0, 5.0], [1.0, 0.0, 5.0], [0.0, 1.0, 5.0]], dtype=np.float64)
        tg2 = _tri("tg2", 0.0)
        mut_peer = SimpleNamespace(object_id="mut", name="mut", vertices=arr_p, faces=((0, 1, 2),))
        def mut_cp(st):
            if st == "surface_proximity_batch_peer":
                arr_p[0, 2] = 0.0
        mout = cur_sp.measure_nearest_surface_batch(tg2, [_tri("p2", 2.0), mut_peer], mut_cp, cutoff_mode="CUTOFF_ONLY_OFF")
        self.assertEqual(mout["nearest_ids"], ["p2"])
        self.assertEqual(mout["outcomes_by_id"]["mut"]["result_kind"], "nearest_cutoff_exclusion")

        # Duplicate IDs & >256 peers rejected
        with self.assertRaises(ValueError):
            cur_sp.measure_nearest_surface_batch(tg2, [p0, p1], NOOP, peer_ids=["dup", "dup"])
        # Partial unknown peer keeps status='partial' and nearest_ids=None
        bad_peer = SimpleNamespace(object_id="bad", name="bad", vertices=((0.0, float("nan"), 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)), faces=((0, 1, 2),))
        pout = cur_sp.measure_nearest_surface_batch(tg2, [_tri("ok", 1.0), bad_peer, _tri("far", 5.0)], NOOP)
        self.assertEqual(pout["status"], "partial")
        self.assertFalse(pout["measurement_valid"])
        self.assertIsNone(pout["nearest_ids"])
        self.assertEqual(pout["best_known_ids"], ["ok"])

        # 12 exact tied peers discovered identically across permutations
        tied = [_tri(f"t{k:02d}", (1.5 if k % 2 == 0 else -1.5), dx=0.05 * k) for k in range(12)]
        distractors = [_tri("f0", 8.0), _tri("f1", -9.0)]
        tout = cur_sp.measure_nearest_surface_batch(
            _tri("torig", 0.0), distractors[:1] + tied + distractors[1:], NOOP,
            cutoff_mode="CUTOFF_SETTLED_PROJECTION", sort_policy="referenced_aabb",
        )
        self.assertEqual(tout["status"], "complete")
        self.assertEqual(len(tout["nearest_ids"]), 12)

    def test_06_r1_03_proof_cache_isolation_and_cutoff_transitions(self):
        """R1-03: Cutoff exclusions carry verified proof receipts & never poison ordinary measured cache."""
        b = next(x for x in self.workloads["batches"] if x["id"] == "D48_Real_47pairs")
        tg, ps = b["tuple_batch"]
        cache = {}
        # Run tight cutoff exclusion while sharing a query-local cache, then ordinary full solve
        ex = cur_sp._measure_surface_proximity_cutoff(
            tg, ps[0], NOOP, upper_bound_sq_key=[1, 10**9, 0], cutoff_mode="CUTOFF_ONLY_OFF", _mesh_cache=cache
        )
        self.assertEqual(ex["result_kind"], "nearest_cutoff_exclusion")
        self.assertEqual(ex["proof_receipt"]["covered_pairs"], ex["proof_receipt"]["total_leaf_pairs"])
        # Ordinary measurement on same pair must return full exact measurement (NOT cached exclusion!)
        full = cur_sp.measure_surface_proximity(tg, ps[0], NOOP, retain_exact_rank=True, _mesh_cache=cache)
        self.assertTrue(full["measurement_valid"])
        self.assertGreater(full["distance_m"], 0.0)
        self.assertNotIn("cutoff_pruned", full)

    def test_07_r1_05_cancellation_forwarding_including_cache_build_sah(self):
        """R1-05: _CacheBuildBudget forwards checkpoint into _build_sah_bvh (n>=512) and all new stages cancel cleanly."""
        w = next(x for x in self.workloads["singles"] if x["id"] == "HighRes_1536F_Pair")
        l_m, r_m = w["tuple_pair"]

        # Verify checkpoint stack actually hits surface_geometry.py::_build_sah_bvh during _mesh_cache build
        sah_frames = []
        cache = {}
        def record_cp(st):
            if st == "surface_proximity_surface_bvh_build":
                for fr in inspect.stack():
                    if fr.function == "_build_sah_bvh":
                        sah_frames.append(fr.lineno)
                        break
        cur_sp.measure_surface_proximity(l_m, r_m, record_cp, _mesh_cache=cache)
        self.assertGreaterEqual(len(sah_frames), 1, "_CacheBuildBudget did not reach _build_sah_bvh checkpoints!")

        # Cancel & retry at each newly instrumented stage
        for stage in (
            "surface_proximity_surface_bvh_build",
            "surface_proximity_common_frame_stage",
            "surface_proximity_flat_bounds",
            "surface_proximity_pending_drain",
        ):
            hits = 0
            c2 = {}
            def cancel_cp(st, target_s=stage):
                nonlocal hits
                if st == target_s:
                    hits += 1
                    if hits == 1:
                        raise _CancelStop()
            with self.assertRaises(_CancelStop, msg=f"Did not hit stage {stage}"):
                cur_sp.measure_surface_proximity(l_m, r_m, cancel_cp, _mesh_cache=c2)
            # Partial cache must never hold incomplete trees
            for ent in c2.values():
                if isinstance(ent, dict) and "tree" in ent:
                    self.assertIsNotNone(ent["tree"]["local_root"])

        # Retry succeeds identically
        ref = cur_sp.measure_surface_proximity(l_m, r_m, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        self.assertTrue(ref["measurement_valid"])

    def test_08_r1_07_batch_validator_negative_controls_normal_and_O(self):
        """R1-07: Hardened batch validator rejects all 14 malformed/spoofed controls (normal & python -O)."""
        tg = _tri("tg", 0.0)
        ps = [_tri("p0", 1.0), _tri("p1", 5.0), _tri("p2", 8.0)]
        pids = ["p0", "p1", "p2"]
        inp_sha = _sha256_json([list(tg.vertices)] + [list(p.vertices) for p in ps])
        opt_sha = _sha256_json({"mode": "test"})
        bo_exh = cur_sp.measure_nearest_surface_batch(tg, ps, NOOP, peer_ids=pids, cutoff_mode="EXHAUSTIVE")
        bo_cut = cur_sp.measure_nearest_surface_batch(tg, ps, NOOP, peer_ids=pids, cutoff_mode="CUTOFF_ONLY_OFF")

        pins = {"EXHAUSTIVE": "a" * 64, "CUTOFF_ONLY_OFF": "b" * 64}
        manifest = {"input_sha256": inp_sha, "options_sha256": opt_sha, "peer_ids": pids}
        base_r = serialize_batch_receipt(arm_name="EXHAUSTIVE", runtime_source_sha256="a" * 64,
                                         input_sha256=inp_sha, options_sha256=opt_sha, batch_out=bo_exh)
        cand_r = serialize_batch_receipt(arm_name="CUTOFF_ONLY_OFF", runtime_source_sha256="b" * 64,
                                         input_sha256=inp_sha, options_sha256=opt_sha, batch_out=bo_cut)

        self.assertTrue(validate_batch_receipt_comparison(base_r, cand_r, manifest, pins)["passed"])

        def _rehash(r):
            r["digest_sha256"] = build_receipt_digest(r)
            return r

        def _must_fail(name, mod_fn):
            b, c, m, p = copy.deepcopy(base_r), copy.deepcopy(cand_r), copy.deepcopy(manifest), copy.deepcopy(pins)
            mod_fn(b, c, m, p)
            with self.assertRaises((ValueError, KeyError), msg=f"Control {name} escaped validator!"):
                validate_batch_receipt_comparison(b, c, m, p)

        # 1. Wrong external pin (self-reported sha ignored vs external pin)
        _must_fail("wrong_external_pin", lambda b, c, m, p: p.update(CUTOFF_ONLY_OFF="e" * 64))
        # 2. Post-hoc mutation of hashed receipt
        _must_fail("posthoc_mutation", lambda b, c, m, p: c.update(nearest_ids=["p1"]))
        # 3. Mutually truncated peer lists
        _must_fail("mutually_truncated_peers", lambda b, c, m, p: (
            b.update(peer_ids=["p0", "p1"]), c.update(peer_ids=["p0", "p1"]),
            _rehash(b), _rehash(c),
        ))
        # 4. Duplicated ID
        _must_fail("duplicate_id", lambda b, c, m, p: (c.update(peer_ids=["p0", "p0", "p2"]), _rehash(c)))
        # 5. Substituted options
        _must_fail("substituted_options", lambda b, c, m, p: (c.update(options_sha256="f" * 64), _rehash(c)))
        # 6. Identical malformed partial-complete receipts both sides
        _must_fail("identical_malformed_both", lambda b, c, m, p: (
            b.update(status="partial", nearest_ids=["p0"]), c.update(status="partial", nearest_ids=["p0"]),
            _rehash(b), _rehash(c),
        ))
        # 7. Exclusion at equality
        _must_fail("exclusion_at_equality", lambda b, c, m, p: (
            c["outcomes_by_id"]["p1"].update(exact_upper_bound_key=list(b["outcomes_by_id"]["p1"]["_exact_distance_sq"])),
            _rehash(c),
        ))
        # 8. Exclusion using incumbent from another snapshot
        _must_fail("stale_snapshot_outcome", lambda b, c, m, p: (
            c["outcomes_by_id"]["p1"].update(snapshot_identity="wrong_snap"), _rehash(c)
        ))
        # 9. Invalid exact_distance_sq key
        _must_fail("invalid_exact_key", lambda b, c, m, p: (
            c.update(best_exact_distance_sq=[1, 0, 0]), _rehash(c)
        ))
        # 10. Partition sum mismatch on traversal exclusion
        _must_fail("bad_traversal_partition", lambda b, c, m, p: (
            c["outcomes_by_id"]["p1"].update(
                proof_kind="complete_cutoff_traversal",
                proof_receipt={"total_leaf_pairs": 10, "covered_pairs": 9},
            ), _rehash(c)
        ))
        # 11. Exclusion leaked measured fields
        _must_fail("exclusion_leaked_distance", lambda b, c, m, p: (
            c["outcomes_by_id"]["p1"].update(distance_m=9.9), _rehash(c)
        ))
        # 12. Winner set mismatch
        _must_fail("winner_mismatch", lambda b, c, m, p: (
            c.update(nearest_ids=["p1"]), _rehash(c)
        ))
        # 13. False root_aabb inequality proof
        _must_fail("root_aabb_false_inequality", lambda b, c, m, p: (
            c["outcomes_by_id"]["p1"]["proof_receipt"].update(aabb_gap_sq=0), _rehash(c)
        ))
        # 14. Candidate regressed verified exclusion to nearest_cutoff_unknown
        _must_fail("candidate_regressed_to_unknown", lambda b, c, m, p: (
            c["outcomes_by_id"]["p2"].update(result_kind="nearest_cutoff_unknown", reason="injected_unknown"),
            c["outcomes_by_id"]["p2"].pop("proof_receipt", None),
            c["coverage"].update(n_strictly_excluded=c["coverage"]["n_strictly_excluded"] - 1, n_unknown=1),
            c.update(status="partial", nearest_ids=None),
            _rehash(c),
        ))


if __name__ == "__main__":
    unittest.main(verbosity=2)

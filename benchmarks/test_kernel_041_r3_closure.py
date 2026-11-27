"""R3 Minimal Closure Test Suite (R3-F01 through R3-F06).

Covers every closure finding raised against commit 7f907d05c in direct-kernel scope.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks import bvh_eval
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


def _g508_pair(cand_name: str = "Peer_000"):
    snap = json.loads((ROOT / "verification/spatial_task_qualification_001/entry/run_01/ACTUAL_SNAPSHOT.json").read_bytes())
    objs = {r["name"]: r for r in snap["objects"]}
    gt = _freeze("Target", objs["Target"]["vertices_world"], objs["Target"]["triangles"])
    gp = _freeze(cand_name, objs[cand_name]["vertices_world"], objs[cand_name]["triangles"])
    return gt, gp


class TestR3Closure_F01_PaidDequeueRefAndInAdmissionFailures(unittest.TestCase):
    def test_paid_dequeue_reference_vs_old_overcount_and_in_admission_failures(self):
        tl, tr = _freeze("tl", *_tilted_plate(12, 0.0)), _freeze("tr", *_tilted_plate(12, 0.5, reverse=True))
        gt, gc = _g508_pair("Competing_001")  # Real multi-epoch fixture: builds=5, inval=4, slab=285, tests=305

        orig_init = sp._Work.__init__
        for label, a_m, b_m, expect_multi_epoch in (
            ("tilted48", tl, tr, False),
            ("G508_Competing_001", gt, gc, True),
        ):
            r_off = sp.measure_surface_proximity(a_m, b_m, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode="off")
            r_paid = sp.measure_surface_proximity(a_m, b_m, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode="off_paid_dequeue_ref")
            r_on = sp.measure_surface_proximity(a_m, b_m, NOOP, retain_exact_rank=True, retain_witness_triangles=True)

            self.assertEqual(r_paid["work"]["witness_projection_mode"], "off_paid_dequeue_ref")
            self.assertEqual(r_paid["work"]["witness_projection_credit_reference"], "paid_dequeue_reference")
            self.assertEqual(bvh_eval._surface_sig(r_paid), bvh_eval._surface_sig(r_off))
            self.assertEqual(bvh_eval._surface_sig(r_on), bvh_eval._surface_sig(r_off))

            m_off = r_off["work"]["work_units"]
            m_paid = r_paid["work"]["work_units"]
            deq = r_off["work"]["dequeue_reused_aabb_bounds"]
            # Exact reconciliation: paid reference equals OFF plus ONLY reused unshifted dequeue bounds (strictly < total aabb_bound_tests)
            self.assertEqual(m_paid, m_off + deq, (label, m_paid, m_off, deq))
            self.assertLess(m_paid, m_off + r_off["work"]["aabb_bound_tests"], label)

            if expect_multi_epoch:
                self.assertGreaterEqual(r_on["work"].get("witness_projection_direction_builds", 0), 2)
                self.assertGreaterEqual(r_on["work"].get("witness_projection_invalidations", 0), 1)
                self.assertGreater(r_on["work"].get("witness_projection_slab_admitted", 0), 0)
                self.assertGreater(r_on["work"].get("witness_projection_tests", 0), 0)

            ref_sig = bvh_eval._surface_sig(r_paid)
            for var in ("PAID_REF", "ON_normal", "ON_in_admission_fail_dir", "ON_in_admission_fail_slab"):
                for delta in range(0, 33):
                    cap = m_paid + delta
                    def pinit(inst, cp, diag, init_w=sp.MAX_WORK_UNITS - cap):
                        orig_init(inst, cp, diag)
                        inst.counts["work_units"] = init_w
                    pm = "off_paid_dequeue_ref" if var == "PAID_REF" else "settled_credit_031_ref"
                    if var == "ON_in_admission_fail_dir":
                        ctx = patch.object(sp, "_fast_descriptor_direction", return_value=None)
                    elif var == "ON_in_admission_fail_slab":
                        ctx = patch.object(sp._FastWitnessProjection, "_slab_exceeds_cutoff", staticmethod(lambda g, c: False))
                    else:
                        ctx = patch.object(sp, "_NODE_PRUNE_OBSERVER", None)
                    with patch.object(sp._Work, "__init__", pinit), ctx:
                        res = sp.measure_surface_proximity(a_m, b_m, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=pm)
                    self.assertTrue(res["measurement_valid"], (label, var, delta, res.get("reason")))
                    self.assertEqual(bvh_eval._surface_sig(res), ref_sig, (label, var, delta))

            # Prefix credit & cancellation under in-admission failure on real production try_run
            class _Cancelled(RuntimeError):
                pass
            trace = []
            orig_try = sp._ProjectionCredit.try_run
            def spy_try(self_c, upper, fn):
                ok, out = orig_try(self_c, upper, fn)
                earned = self_c.earned_bounds + self_c.earned_narrow + self_c.earned_node_prune
                trace.append((ok, upper, self_c.balance, self_c.spent, earned))
                self.assertGreaterEqual(self_c.balance, 0)
                self.assertLessEqual(self_c.spent, earned)
                return ok, out

            with patch.object(sp._ProjectionCredit, "try_run", spy_try), patch.object(
                sp._FastWitnessProjection, "_slab_exceeds_cutoff", staticmethod(lambda g, c: False)
            ):
                rf_fail = sp.measure_surface_proximity(a_m, b_m, NOOP, retain_exact_rank=True)
            self.assertTrue(rf_fail["measurement_valid"])
            self.assertGreater(len(trace), 0)
            self.assertEqual(rf_fail["work"].get("witness_projection_vertex_slab_pruned_pairs", 0), 0)

            seen_nv = 0
            def cp_cancel(stage):
                nonlocal seen_nv
                if stage == "surface_proximity_witness_projection_node_visits":
                    seen_nv += 1
                    if seen_nv == 2:
                        raise _Cancelled("slab_cancel")
            with self.assertRaises(_Cancelled):
                sp.measure_surface_proximity(a_m, b_m, cp_cancel)


class TestR3Closure_F02_AtomicCacheAdmissionAndTopologyIsolation(unittest.TestCase):
    def test_earlier_face_rebind_and_restore_at_every_stage_and_topology_isolation(self):
        v6 = (
            (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
            (0.0, 0.0, -4.0), (1.0, 0.0, -4.0), (0.0, 1.0, -4.0),
        )
        f_old = ((0, 1, 2),)
        f_new = ((3, 4, 5),)
        fixed = _freeze("fixed", [[0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0]], [(0, 1, 2)])

        # Exercise rebind right at: first face validation, validated_faces (inside _admit_one before loop!),
        # and referenced_vertices (frame stage), then restore f_old before next call.
        for target_stage, trigger_nth in (
            ("surface_proximity_face_validate", 1),
            ("surface_proximity_validated_faces", 1),
            ("surface_proximity_referenced_vertices", 1),
        ):
            m = SimpleNamespace(object_id="m", name="m", vertices=v6, faces=f_old)
            cache = {}
            seen = 0
            def cp_rebind(st, tgt=target_stage, nth=trigger_nth, mesh_obj=m):
                nonlocal seen
                if st == tgt:
                    seen += 1
                    if seen == nth:
                        mesh_obj.faces = f_new

            r1 = sp.measure_surface_proximity(m, fixed, cp_rebind, retain_exact_rank=True, retain_witness_triangles=True, _mesh_cache=cache)
            self.assertGreaterEqual(seen, trigger_nth)
            # Call 1 MUST atomically match frozen f_old (distance=1.0), NOT inconsistent f_new!
            self.assertEqual(r1["distance_m"], 1.0, (target_stage, r1))
            self.assertNotIn(id(m), cache)

            # While still rebound to f_new -> exact 5.0
            r_new = sp.measure_surface_proximity(m, fixed, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _mesh_cache=cache)
            self.assertEqual(r_new["distance_m"], 5.0)

            # Restore original reference f_old -> exact 1.0, never poisoned by prior rebind!
            m.faces = f_old
            r_restored = sp.measure_surface_proximity(m, fixed, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _mesh_cache=cache)
            self.assertEqual(r_restored["distance_m"], 1.0)

        # Also test rebind at BVH build (>256 pairs) and restore on same-length 17-face tuples
        f17_old = tuple((0, 1, 2) for _ in range(17))
        f17_new = tuple((3, 4, 5) for _ in range(17))
        fix17 = _freeze("fix17", [[0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0]], f17_old)
        m17 = SimpleNamespace(object_id="m17", name="m17", vertices=v6, faces=f17_old)
        bvh_cache = {}
        seen_bvh = 0
        def cp_bvh(st):
            nonlocal seen_bvh
            if st == "surface_proximity_surface_bvh_build":
                seen_bvh += 1
                if seen_bvh == 2:
                    m17.faces = f17_new
        r_bvh1 = sp.measure_surface_proximity(m17, fix17, cp_bvh, retain_exact_rank=True, _mesh_cache=bvh_cache)
        self.assertEqual(r_bvh1["distance_m"], 1.0)
        self.assertNotIn(id(m17), bvh_cache)
        m17.faces = f17_old
        r_bvh2 = sp.measure_surface_proximity(m17, fix17, NOOP, retain_exact_rank=True, _mesh_cache=bvh_cache)
        self.assertEqual(r_bvh2["distance_m"], 1.0)

        # Consumer topology dict mutation isolation across cache hits
        t_clean = _freeze("tc", v6, f_old)
        t_cache = {}
        res_a = sp.measure_surface_proximity(t_clean, fixed, NOOP, retain_exact_rank=True, _mesh_cache=t_cache)
        orig_boundary = res_a["topology"][0]["boundary_edge_count"]
        res_a["topology"][0]["boundary_edge_count"] = 999
        res_b = sp.measure_surface_proximity(t_clean, fixed, NOOP, retain_exact_rank=True, _mesh_cache=t_cache)
        self.assertEqual(res_b["work"].get("mesh_cache_hits", 0), 2)
        self.assertEqual(res_b["topology"][0]["boundary_edge_count"], orig_boundary)


class TestR3Closure_F03_F04_F05_VerifierAndExternalPins(unittest.TestCase):
    def test_cross_arm_entry_receipt_comparator_and_external_arm_pinning(self):
        sha_032 = "0" * 64
        sha_r3 = "8" * 64
        sha_bad = "f" * 64
        base_near = {
            "status": "complete", "nearest_ids": ["Obj_002"], "distance_m": 0.001,
            "unresolved": {}, "excluded": [], "measurement_notes": {}, "best_known_evidence": [],
            "binding": {"scene_revision": "r1", "runtime_source_sha256": sha_032, "runtime_source_sha256_valid": True},
        }
        cand_near = copy.deepcopy(base_near)
        cand_near["binding"]["runtime_source_sha256"] = sha_r3
        bvh_eval.assert_entry_receipts_equal(base_near, cand_near, ref_runtime_sha=sha_032, cand_runtime_sha=sha_r3, entry_kind="nearest")

        base_scan = {
            "status": "complete", "coverage": {"measured_match": 4}, "matches": [],
            "dispositions": [{"object_ids": ["Obj_014", "Obj_002"], "status": "measured_match", "distance_m": 0.001}],
            "binding": {"scene_revision": "r1", "runtime_source_sha256": sha_032, "runtime_source_sha256_valid": True},
        }
        cand_scan = copy.deepcopy(base_scan)
        cand_scan["binding"]["runtime_source_sha256"] = sha_r3
        bvh_eval.assert_entry_receipts_equal(base_scan, cand_scan, ref_runtime_sha=sha_032, cand_runtime_sha=sha_r3, entry_kind="scan")

        with self.assertRaises(RuntimeError):
            bvh_eval.assert_entry_receipts_equal(base_near, cand_near, ref_runtime_sha=sha_032, cand_runtime_sha=sha_bad, entry_kind="nearest")
        bad_scan = copy.deepcopy(cand_scan)
        bad_scan["dispositions"][0]["distance_m"] = 0.25
        with self.assertRaises(RuntimeError):
            bvh_eval.assert_entry_receipts_equal(base_scan, bad_scan, ref_runtime_sha=sha_032, cand_runtime_sha=sha_r3, entry_kind="scan")

        # External manifest wrong-pin refusal check on run_r3_closure_eval.py
        with tempfile.TemporaryDirectory() as td:
            manifest_path = Path(td) / "bad_manifest.json"
            manifest_path.write_text(json.dumps({
                "R3_default": {"expected_runtime_sha256": "deadbeef" * 8},
            }), encoding="utf8")
            proc = subprocess.run(
                [sys.executable, "-B", str(ROOT / "benchmarks/run_r3_closure_eval.py"),
                 "--arm-manifest", str(manifest_path), "--output-prefix", "UNUSED_TMP_CHECK"],
                cwd=str(ROOT), capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("pin mismatch", (proc.stdout + proc.stderr).lower())


class TestR3Closure_F06_ExactFrameAuditBoxContainmentAndAffineFallback(unittest.TestCase):
    def test_exact_frame_denominator_one_box_containment_and_fallback_stage(self):
        tl, tr = _freeze("tl", *_tilted_plate(12, 0.0)), _freeze("tr", *_tilted_plate(12, 0.5, True))
        holder = {}
        res = sp.measure_surface_proximity(tl, tr, NOOP, retain_exact_rank=True, _prepared_holder=holder)
        origin_frac, factor = holder["pair"][2], holder["pair"][3]
        for mesh in (tl, tr):
            for p in mesh.vertices:
                for k in range(3):
                    val = (Fraction.from_float(float(p[k])) - origin_frac[k]) * factor
                    self.assertEqual(val.denominator, 1)

        # Box-bound prune control with raw source containment check inside reported node AABB
        bud = sp._Work(NOOP, {})
        box_events = []
        raw_a = ((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0))
        raw_b = ((0.0, 0.0, 3.0), (0.0, 1.0, 3.0), (1.0, 0.0, 3.0))
        prep_a = [(((0, 0, 0), (0, 1, 0), (1, 0, 0)), (0, 0, 1), 1, (), ((0, 1), (0, 1), (0, 0)))]
        prep_b = [(((0, 0, 3), (0, 1, 3), (1, 0, 3)), (0, 0, 1), 1, (), ((0, 1), (0, 1), (3, 3)))]
        fp_box = sp._FastWitnessProjection.build((4, 1, ("points", (0, 0, 0), (0, 0, 2))), prep_a, prep_b, 0, bud)
        na = (0, 0, 0, 1, 1, 0, 1, (0,), None, None, 0, 1, 1, 0)
        nb = (0, 0, 3, 1, 1, 3, 1, (0,), None, None, 0, 1, 1, 6)
        for p in raw_a:
            for k in range(3):
                self.assertTrue(na[k] <= int(p[k]) <= na[3 + k])
        for p in raw_b:
            for k in range(3):
                self.assertTrue(nb[k] <= int(p[k]) <= nb[3 + k])
        with patch.object(sp, "_NODE_PRUNE_OBSERVER", lambda ev: box_events.append(ev)):
            ok_box = fp_box.prunes_nodes(na, nb, True, bud, use_vertex_slab=False)
        self.assertTrue(ok_box)
        self.assertEqual(box_events[0]["source"], "box")

        # Affine fallback dedicated checkpoint cancel & recovery
        ext_a = _freeze("ea", [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)], [(0, 1, 2)] * 17)
        ext_b = _freeze("eb", [(0.0, 0.0, math.ldexp(1.0, -520)), (1.0, 0.0, math.ldexp(1.0, -520)), (0.0, 1.0, math.ldexp(1.0, -520))], [(0, 1, 2)] * 17)
        class _Cancel(RuntimeError):
            pass
        seen_fb = 0
        fb_cache = {}
        def cp_fb(st):
            nonlocal seen_fb
            if st == "surface_proximity_mesh_cache_affine_fallback":
                seen_fb += 1
                if seen_fb == 1:
                    raise _Cancel("fb")
        with self.assertRaises(_Cancel):
            sp.measure_surface_proximity(ext_a, ext_b, cp_fb, _mesh_cache=fb_cache)
        self.assertEqual(seen_fb, 1)
        r_ok = sp.measure_surface_proximity(ext_a, ext_b, NOOP, retain_exact_rank=True, _mesh_cache=fb_cache)
        self.assertTrue(r_ok["measurement_valid"])
        self.assertEqual(r_ok["_exact_distance_sq"], sp.measure_surface_proximity(ext_a, ext_b, NOOP, retain_exact_rank=True)["_exact_distance_sq"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

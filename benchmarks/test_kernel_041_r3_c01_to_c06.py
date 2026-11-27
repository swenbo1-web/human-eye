"""R3 targeted closure & optimization verification suite (C01-C06).

Verifies every R3 requirement independently using pure Python Fraction / raw source
vertices and avoids modifying or overwriting any prior R2/historical artifacts.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import json
import math
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks import bvh_eval
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


def _box_mesh(oid: str, origin, size, subdiv: int = 1):
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
    for u in range(subdiv):
        for v in range(subdiv):
            a, b, c, d = vid(u, v, 0), vid(u + 1, v, 0), vid(u + 1, v + 1, 0), vid(u, v + 1, 0)
            faces.extend([(a, c, b), (a, d, c)])
            a, b, c, d = vid(u, v, subdiv), vid(u + 1, v, subdiv), vid(u + 1, v + 1, subdiv), vid(u, v + 1, subdiv)
            faces.extend([(a, b, c), (a, c, d)])
            a, b, c, d = vid(u, 0, v), vid(u + 1, 0, v), vid(u + 1, 0, v + 1), vid(u, 0, v + 1)
            faces.extend([(a, b, c), (a, c, d)])
            a, b, c, d = vid(u, subdiv, v), vid(u + 1, subdiv, v), vid(u + 1, subdiv, v + 1), vid(u, subdiv, v + 1)
            faces.extend([(a, c, b), (a, d, c)])
            a, b, c, d = vid(0, u, v), vid(0, u + 1, v), vid(0, u + 1, v + 1), vid(0, u, v + 1)
            faces.extend([(a, c, b), (a, d, c)])
            a, b, c, d = vid(subdiv, u, v), vid(subdiv, u + 1, v), vid(subdiv, u + 1, v + 1), vid(subdiv, u, v + 1)
            faces.extend([(a, b, c), (a, c, d)])
    return SimpleNamespace(object_id=oid, name=oid, vertices=tuple(verts), faces=tuple(faces))


def _g508_pair():
    snap = json.loads((ROOT / "verification/spatial_task_qualification_001/entry/run_01/ACTUAL_SNAPSHOT.json").read_bytes())
    objs = {r["name"]: r for r in snap["objects"]}
    gt = _freeze("Target", objs["Target"]["vertices_world"], objs["Target"]["triangles"])
    gp = _freeze("Peer_000", objs["Peer_000"]["vertices_world"], objs["Peer_000"]["triangles"])
    return gt, gp


class _TrackingTuple(tuple):
    """Unused directly; C02 checks use child access wrappers on internal node slots."""


class TestR3_C01_CacheOwnership(unittest.TestCase):
    def test_owning_readonly_numpy_view_and_toggle_mutations_fail_closed(self):
        v_owner = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float64)
        old_view = v_owner.view()
        v_owner.flags.writeable = False
        self.assertIsNone(v_owner.base)
        self.assertTrue(v_owner.flags.owndata)
        self.assertFalse(v_owner.flags.writeable)

        fixed = _freeze("fixed", [[0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0]], [(0, 1, 2)])
        m_v = SimpleNamespace(object_id="mv", name="mv", vertices=v_owner, faces=((0, 1, 2),))
        cache = {}

        r1 = sp.measure_surface_proximity(m_v, fixed, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _mesh_cache=cache)
        u1 = sp.measure_surface_proximity(m_v, fixed, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        self.assertEqual(bvh_eval._surface_sig(r1), bvh_eval._surface_sig(u1))
        self.assertEqual(r1["distance_m"], 1.0)
        self.assertEqual(len(cache), 0)
        self.assertEqual(r1["work"].get("mesh_cache_hits", 0), 0)

        # Pre-existing writable alias mutation on owning read-only ndarray
        old_view[:, 2] = -2.0
        r2 = sp.measure_surface_proximity(m_v, fixed, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _mesh_cache=cache)
        u2 = sp.measure_surface_proximity(m_v, fixed, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        self.assertEqual(r2["distance_m"], 3.0)
        self.assertEqual(bvh_eval._surface_sig(r2), bvh_eval._surface_sig(u2))
        self.assertEqual(len(cache), 0)

        # writeable flag toggle -> mutate -> read-only
        v_owner.flags.writeable = True
        v_owner[:, 2] = -3.0
        v_owner.flags.writeable = False
        r3 = sp.measure_surface_proximity(m_v, fixed, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _mesh_cache=cache)
        u3 = sp.measure_surface_proximity(m_v, fixed, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        self.assertEqual(r3["distance_m"], 4.0)
        self.assertEqual(bvh_eval._surface_sig(r3), bvh_eval._surface_sig(u3))
        self.assertEqual(len(cache), 0)

    def test_owning_readonly_face_ndarray_view_and_toggle_and_mixed_containers(self):
        v_two = (
            (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
            (0.0, 0.0, -4.0), (1.0, 0.0, -4.0), (0.0, 1.0, -4.0),
        )
        fixed = _freeze("fixed", [[0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0]], [(0, 1, 2)])
        f_owner = np.array([[0, 1, 2]], dtype=np.int32)
        f_view = f_owner.view()
        f_owner.flags.writeable = False
        m_f = SimpleNamespace(object_id="mf", name="mf", vertices=v_two, faces=f_owner)
        cache = {}

        rf1 = sp.measure_surface_proximity(m_f, fixed, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _mesh_cache=cache)
        self.assertEqual(rf1["distance_m"], 1.0)
        self.assertEqual(len(cache), 0)

        # Same object ID/shape, change referenced face indices via prior writable view
        f_view[0] = [3, 4, 5]
        rf2 = sp.measure_surface_proximity(m_f, fixed, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _mesh_cache=cache)
        uf2 = sp.measure_surface_proximity(m_f, fixed, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        self.assertEqual(rf2["distance_m"], 5.0)
        self.assertEqual(bvh_eval._surface_sig(rf2), bvh_eval._surface_sig(uf2))

        # Toggle writeable flag on face array back to first triangle
        f_owner.flags.writeable = True
        f_owner[0] = [0, 1, 2]
        f_owner.flags.writeable = False
        rf3 = sp.measure_surface_proximity(m_f, fixed, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _mesh_cache=cache)
        uf3 = sp.measure_surface_proximity(m_f, fixed, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        self.assertEqual(rf3["distance_m"], 1.0)
        self.assertEqual(bvh_eval._surface_sig(rf3), bvh_eval._surface_sig(uf3))

        # Writable array & read-only view over writable base & mixed ndarray/tuple
        w_arr = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float64)
        ro_view = w_arr.view()
        ro_view.flags.writeable = False
        for bad_verts, bad_faces in (
            (w_arr, ((0, 1, 2),)),
            (ro_view, ((0, 1, 2),)),
            (np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float64), np.array([[0, 1, 2]], dtype=np.int32)),
        ):
            mb = SimpleNamespace(object_id="mb", name="mb", vertices=bad_verts, faces=bad_faces)
            c_bad = {}
            r_b = sp.measure_surface_proximity(mb, fixed, NOOP, retain_exact_rank=True, _mesh_cache=c_bad)
            self.assertTrue(r_b["measurement_valid"])
            self.assertEqual(len(c_bad), 0)

    def test_deep_tuple_hits_same_length_replacement_stale_eviction_and_midcall_rebind(self):
        t1 = _freeze("t1", [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], [(0, 1, 2)])
        fixed = _freeze("fixed", [[0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0]], [(0, 1, 2)])
        cache = {"__sealed_query_meshes__": True}

        r1 = sp.measure_surface_proximity(t1, fixed, NOOP, retain_exact_rank=True, _mesh_cache=cache)
        r2 = sp.measure_surface_proximity(t1, fixed, NOOP, retain_exact_rank=True, _mesh_cache=cache)
        self.assertEqual(r2["work"].get("mesh_cache_hits", 0), 2)
        self.assertIn(id(t1), cache)

        # Same-length tuple replacement on t1.vertices -> stale entry evicted & re-admitted
        t1.vertices = ((0.0, 0.0, -1.0), (1.0, 0.0, -1.0), (0.0, 1.0, -1.0))
        r3 = sp.measure_surface_proximity(t1, fixed, NOOP, retain_exact_rank=True, _mesh_cache=cache)
        self.assertEqual(r3["distance_m"], 2.0)

        # Replace tuple vertices with ndarray -> stale cache entry evicted immediately on hit check!
        arr = np.array([[0.0, 0.0, -4.0], [1.0, 0.0, -4.0], [0.0, 1.0, -4.0]], dtype=np.float64)
        arr.flags.writeable = False
        t1.vertices = arr
        r4 = sp.measure_surface_proximity(t1, fixed, NOOP, retain_exact_rank=True, _mesh_cache=cache)
        self.assertEqual(r4["distance_m"], 5.0)
        self.assertNotIn(id(t1), cache)

        # Mid-call rebind isolation: mutating mesh.vertices at frame checkpoint must still read strong verts_ref captured at admission
        t2 = _freeze("t2", [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], [(0, 1, 2)])
        mut_verts = [[0.0, 0.0, -9.0], [1.0, 0.0, -9.0], [0.0, 1.0, -9.0]]
        reb_cache = {}
        triggered = False
        def cp_rebind(stage):
            nonlocal triggered
            if stage == "surface_proximity_referenced_vertices" and not triggered:
                triggered = True
                t2.vertices = mut_verts
        r_mid = sp.measure_surface_proximity(t2, fixed, cp_rebind, retain_exact_rank=True, _mesh_cache=reb_cache)
        self.assertEqual(r_mid["distance_m"], 1.0)
        # Subsequent call sees new mut_verts and rejects caching
        r_after = sp.measure_surface_proximity(t2, fixed, NOOP, retain_exact_rank=True, _mesh_cache=reb_cache)
        self.assertEqual(r_after["distance_m"], 10.0)
        self.assertNotIn(id(t2), reb_cache)


class TestR3_C02_ConstantTimeAdmission(unittest.TestCase):
    def test_o1_upper_bound_zero_descendant_traversal_and_single_estimate_per_node(self):
        # Build 16-triangle internal binary BVH tree and poison child slots [8],[9] to detect ANY descendant access
        # Leaf: (lx, ly, lz, hx, hy, hz, count, ids, None, None, min_id, cx2, cy2, cz2)
        class _PoisonNode(tuple):
            pass

        leaves = [
            (i, 0, 0, i + 1, 1, 0, 1, (i,), None, None, i, 2 * i + 1, 1, 0)
            for i in range(8)
        ]
        # Build internal level cleanly but inspect access via a custom proxy tuple on child slot
        child_l = (0, 0, 0, 4, 1, 0, 4, None, leaves[0], leaves[1], 0, 4, 1, 0)
        child_r = (4, 0, 0, 8, 1, 0, 4, None, leaves[2], leaves[3], 4, 12, 1, 0)

        # Use a custom object raising if indexed like node[8]/node[9] at child level
        accessed_descendants = []

        class _GuardTuple(tuple):
            def __getitem__(self, idx):
                if idx in (8, 9):
                    accessed_descendants.append(idx)
                    raise AssertionError("C02 violation: admission touched internal child pointers [8]/[9]")
                return super().__getitem__(idx)

        root_guarded = _GuardTuple((0, 0, 0, 8, 1, 0, 8, None, child_l, child_r, 0, 8, 1, 0))
        self.assertEqual(sp._FastWitnessProjection._cold_interval_upper(root_guarded, {}), 5 * 8 - 1)
        self.assertEqual(sp._FastWitnessProjection._cold_interval_upper(root_guarded, {id(root_guarded): (0, 1)}), 0)
        self.assertEqual(sp._FastWitnessProjection._cold_interval_upper(leaves[0], {}), 1 + 3 * 1)
        self.assertEqual(accessed_descendants, [])

        # Verify on G508_Peer_000 that every popped node admission calls _cold_interval_upper at most once per node check
        # and actual slab work never exceeds reserved upper bound, with zero duplicate preflight.
        gt, gp = _g508_pair()
        r_r3 = sp.measure_surface_proximity(gt, gp, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        w = r_r3["work"]
        self.assertGreater(w.get("witness_projection_upper_calls", 0), 0)
        self.assertGreater(w.get("witness_projection_slab_admitted", 0), 0)
        self.assertLessEqual(
            w.get("witness_projection_slab_actual_units", 0),
            w.get("witness_projection_slab_reserved_units", 0),
        )
        self.assertEqual(
            w["witness_projection_credit_balance"],
            w["witness_projection_credit_node_units"]
            + w["witness_projection_credit_narrow_units"]
            + w["witness_projection_credit_node_prune_units"]
            - w["witness_projection_credit_spent_units"],
        )

        # Also check degenerate 1-point and 2-point hulls fit actual <= U(node) and actually exercise vertex_slab (loose AABB z>=1 vs vertices at z=5)
        bud = sp._Work(NOOP, {})
        deg_a = [
            (((0, 0, 0),), (0, 0, 0), 0, (), ((0, 0), (0, 0), (0, 0))),
            (((0, 0, 0), (1, 0, 0)), (0, 0, 0), 0, [(0, 0, 0), (1, 0, 0), (1, 0, 0), 1], ((0, 1), (0, 0), (0, 0))),
        ]
        deg_b = [
            (((0, 0, 5), (1, 0, 5), (0, 1, 5)), (0, 0, 1), 1, (), ((0, 1), (0, 1), (5, 5))),
            (((2, 0, 5), (3, 0, 5), (2, 1, 5)), (0, 0, 1), 1, (), ((2, 3), (0, 1), (5, 5))),
        ]
        fp_deg = sp._FastWitnessProjection.build((4, 1, ("points", (0, 0, 0), (0, 0, 2))), deg_a, deg_b, 0, bud)
        la0 = (0, 0, 0, 0, 0, 0, 1, (0,), None, None, 0, 0, 0, 0)
        la1 = (0, 0, 0, 1, 0, 0, 1, (1,), None, None, 1, 1, 0, 0)
        na_int = (0, 0, 0, 1, 0, 0, 2, None, la0, la1, 0, 1, 0, 0)
        lb0 = (0, 0, 1, 1, 1, 5, 1, (0,), None, None, 0, 1, 1, 6)
        lb1 = (2, 0, 1, 3, 1, 5, 1, (1,), None, None, 1, 5, 1, 6)
        nb_int = (0, 0, 1, 3, 1, 5, 2, None, lb0, lb1, 0, 3, 1, 6)
        cred = sp._ProjectionCredit(bud)
        for _ in range(100):
            cred.saved_bound()
        pruned = fp_deg.prunes_nodes(na_int, nb_int, True, bud, use_vertex_slab=True, credit=cred)
        self.assertTrue(pruned)
        self.assertEqual(bud.counts.get("witness_projection_slab_admitted", 0), 1)
        self.assertEqual(bud.counts.get("witness_projection_vertex_slab_pruned_pairs", 0), 1)
        self.assertLessEqual(
            bud.counts["witness_projection_slab_actual_units"],
            bud.counts["witness_projection_slab_reserved_units"],
        )


class TestR3_C03_BudgetContract(unittest.TestCase):
    def test_explicit_projection_mode_contract_and_invalid_refusal(self):
        tl, tr = _tilted_plate(12, 0.0), _tilted_plate(12, 0.5, reverse=True)
        ml, mr = _freeze("tl", *tl), _freeze("tr", *tr)
        with self.assertRaises(ValueError):
            sp.measure_surface_proximity(ml, mr, NOOP, _projection_mode="unknown_mode")
        r_off = sp.measure_surface_proximity(ml, mr, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode="off")
        r_on = sp.measure_surface_proximity(ml, mr, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode="settled_credit_031_ref")
        self.assertEqual(bvh_eval._surface_sig(r_off), bvh_eval._surface_sig(r_on))
        self.assertEqual(r_off["work"]["witness_projection_mode"], "off")
        self.assertEqual(r_off["work"]["witness_projection_credit_reference"], "none")
        self.assertEqual(r_off["work"].get("witness_projection_tests", 0), 0)
        self.assertEqual(r_off["work"].get("witness_projection_credit_spent_units", 0), 0)
        self.assertEqual(r_off["work"].get("witness_projection_credit_node_units", 0), 0)
        self.assertEqual(r_on["work"]["witness_projection_mode"], "settled_credit_031_ref")
        self.assertEqual(r_on["work"]["witness_projection_credit_reference"], "mandatory_031_dequeue_aabb")

    def test_full_integer_budget_sweeps_m_off_and_m_ref_031_plus_prefix_ledger_and_diag_reset(self):
        tl, tr = _tilted_plate(12, 0.0), _tilted_plate(12, 0.5, reverse=True)
        ml, mr = _freeze("tl", *tl), _freeze("tr", *tr)
        sv, sf = mac.sheet(17)
        tris_sf = [list(f) for f in bvh_eval._triangulate(sf)]
        sp_l = _freeze("sp_l", sv, tris_sf)
        sp_r = _freeze("sp_r", [[p[0], p[1], p[2] + 5e-6] for p in sv], tris_sf)

        # Repeated-epoch staircase fixture (nested decreasing z across leaf order)
        st_vl, st_fl, st_vr, st_fr = [], [], [], []
        for k in range(36):
            x0, x1 = k * 0.08, k * 0.08 + 0.06
            z = 0.002 if k == 35 else 0.12 * (1.0 - k / 36.0)
            b = len(st_vl)
            st_vl.extend([[x0, 0.0, 0.0], [x1, 0.0, 0.0], [x0, 0.2, 0.0]])
            st_fl.append([b, b + 1, b + 2])
            st_vr.extend([[x0, 0.0, z + 0.5], [x1, 0.0, z + 0.5], [x0, 0.2, z + 0.5]])
            st_fr.append([b, b + 1, b + 2])
        ep_l = _freeze("ep_l", st_vl, st_fl)
        ep_r = _freeze("ep_r", st_vr, st_fr)

        orig_init = sp._Work.__init__

        def sweep_fixture(a_m, b_m):
            ref_off = sp.measure_surface_proximity(a_m, b_m, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode="off")
            ref_on = sp.measure_surface_proximity(a_m, b_m, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
            ref_sig = bvh_eval._surface_sig(ref_off)
            m_off = ref_off["work"]["work_units"]
            m_ref_031 = m_off + ref_off["work"]["aabb_bound_tests"]

            holes_m_off = {v: {"invalid": [], "prov_diff": []} for v in ("OFF", "ON_normal", "ON_fail_dir", "ON_fail_slab")}
            holes_m_031 = {v: {"invalid": [], "prov_diff": []} for v in ("OFF", "ON_normal", "ON_fail_dir", "ON_fail_slab")}

            for variant in ("OFF", "ON_normal", "ON_fail_dir", "ON_fail_slab"):
                for cap_base, hole_bucket in ((m_off, holes_m_off), (m_ref_031, holes_m_031)):
                    for delta in range(-8, 33):
                        cap = cap_base + delta
                        if cap <= 0 or cap > sp.MAX_WORK_UNITS:
                            continue
                        def pinit(inst, cp, diag, init_w=sp.MAX_WORK_UNITS - cap):
                            orig_init(inst, cp, diag)
                            inst.counts["work_units"] = init_w
                        pm = "off" if variant == "OFF" else "settled_credit_031_ref"
                        if variant == "ON_fail_dir":
                            ctx = patch.object(sp, "_fast_descriptor_direction", return_value=None)
                        elif variant == "ON_fail_slab":
                            ctx = patch.object(
                                sp._FastWitnessProjection, "prunes_nodes",
                                lambda self, l, r, st, bd, **kw: (self._node_interval(l, self.node_a, self.tri_a, self.prep_a, bd), False)[1],
                            )
                        else:
                            ctx = patch.object(sp, "_NODE_PRUNE_OBSERVER", None)
                        with patch.object(sp._Work, "__init__", pinit), ctx:
                            res = sp.measure_surface_proximity(a_m, b_m, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=pm)
                        self.assertLessEqual(res["work"]["work_units"], sp.MAX_WORK_UNITS)
                        if res["measurement_valid"]:
                            cur_sig = bvh_eval._surface_sig(res)
                            if delta >= 0:
                                if cur_sig != ref_sig:
                                    hole_bucket[variant]["prov_diff"].append(delta)
                            else:
                                # Negative delta (< M_off): exact core measurements must still match if complete; only optional provenance may be None
                                self.assertEqual(res["_exact_distance_sq"], ref_off["_exact_distance_sq"])
                                self.assertEqual(res["point_a_world"], ref_off["point_a_world"])
                                self.assertEqual(res["point_b_world"], ref_off["point_b_world"])
                        else:
                            self.assertEqual(res["reason"], "surface_work_budget")
                            if delta >= 0:
                                hole_bucket[variant]["invalid"].append(delta)
            return {
                "M_off": m_off,
                "M_ref_031": m_ref_031,
                "ON_normal_wu": ref_on["work"]["work_units"],
                "holes_vs_M_off": holes_m_off,
                "holes_vs_M_ref_031": holes_m_031,
            }

        tilt_res = sweep_fixture(ml, mr)
        sheet_res = sweep_fixture(sp_l, sp_r)
        epoch_res = sweep_fixture(ep_l, ep_r)
        # Option A: normal_ON has 0 invalid & 0 provenance diffs vs M_off, AND ALL 4 variants have 0 invalid & 0 provenance diffs vs M_ref_031!
        for rset in (tilt_res, sheet_res, epoch_res):
            self.assertEqual(rset["holes_vs_M_off"]["OFF"], {"invalid": [], "prov_diff": []})
            self.assertEqual(rset["holes_vs_M_off"]["ON_normal"], {"invalid": [], "prov_diff": []})
            for var, hd in rset["holes_vs_M_ref_031"].items():
                self.assertEqual(hd, {"invalid": [], "prov_diff": []}, (var, hd))

        # Step-by-step prefix ledger non-negativity trace across G508_Peer_000
        gt, gp = _g508_pair()
        prefix_events = []
        orig_try_run = sp._ProjectionCredit.try_run
        def trace_try_run(self_c, upper, fn):
            before_bal = self_c.balance
            before_spent = self_c.spent
            ok, val = orig_try_run(self_c, upper, fn)
            prefix_events.append((ok, upper, before_bal, self_c.balance, before_spent, self_c.spent))
            if self_c.balance < 0 or self_c.spent > (self_c.earned_bounds + self_c.earned_narrow + self_c.earned_node_prune):
                raise AssertionError("Prefix credit invariant violated mid-solve")
            return ok, val
        with patch.object(sp._ProjectionCredit, "try_run", trace_try_run):
            sp.measure_surface_proximity(gt, gp, NOOP, retain_exact_rank=True)
        self.assertGreater(len(prefix_events), 0)

        # Reused diagnostics dict MUST reset stale counters across calls
        shared_diag = {}
        r_g = sp.measure_surface_proximity(gt, gp, NOOP, diagnostics=shared_diag, retain_exact_rank=True)
        self.assertGreater(shared_diag.get("witness_projection_pruned_pairs", 0), 0)
        r_off_reuse = sp.measure_surface_proximity(ml, mr, NOOP, diagnostics=shared_diag, _projection_mode="off")
        self.assertEqual(shared_diag.get("witness_projection_pruned_pairs", 0), 0)
        self.assertEqual(shared_diag.get("witness_projection_slab_admitted", 0), 0)
        self.assertEqual(shared_diag.get("witness_projection_mode"), "off")


class TestR3_C04_VerifierHardening(unittest.TestCase):
    def test_comparator_negative_controls_normal_and_python_O(self):
        res = bvh_eval.verify_comparator_negative_controls()
        self.assertTrue(res["passed"])
        self.assertGreaterEqual(res["controls_checked"], 36)
        proc = subprocess.run(
            [sys.executable, "-B", "-O", str(ROOT / "benchmarks/bvh_eval.py"), "--verify-comparator"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        parsed = json.loads(proc.stdout)
        self.assertTrue(parsed["passed"])


class TestR3_C05_ProjectionCertAndClosedSolid(unittest.TestCase):
    def test_c05a_independent_source_vertex_projection_certificate_and_edge_controls(self):
        tl, tr = _tilted_plate(12, 0.0), _tilted_plate(12, 0.5, reverse=True)
        ml, mr = _freeze("tl", *tl), _freeze("tr", *tr)
        gt, gp = _g508_pair()

        def leaf_ids(node):
            if node[7] is not None:
                return node[7]
            return leaf_ids(node[8]) + leaf_ids(node[9])

        def independent_source_coords(mesh, origin_frac, factor):
            out = []
            for row in mesh.faces:
                pts = []
                for vid in row:
                    vx, vy, vz = (Fraction.from_float(float(c)) for c in mesh.vertices[vid])
                    pts.append((
                        int((vx - origin_frac[0]) * factor),
                        int((vy - origin_frac[1]) * factor),
                        int((vz - origin_frac[2]) * factor),
                    ))
                out.append(pts)
            return out

        for label, a_m, b_m, limit_events in (
            ("tilted48_exhaustive", ml, mr, None),
            ("g508_peer000_sampled_local", gt, gp, 50),
        ):
            events = []
            holder = {}
            with patch.object(sp, "_NODE_PRUNE_OBSERVER", lambda ev, lst=events: lst.append(ev)):
                res = sp.measure_surface_proximity(a_m, b_m, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _prepared_holder=holder)
            origin_frac = holder["pair"][2]
            factor = holder["pair"][3]
            src_a = independent_source_coords(a_m, origin_frac, factor)
            src_b = independent_source_coords(b_m, origin_frac, factor)

            sample = events
            if limit_events is not None and len(events) > limit_events:
                s_evs = [e for e in events if e["strict"]][: limit_events // 2]
                t_evs = [e for e in events if not e["strict"]][: limit_events - len(s_evs)]
                sample = s_evs + t_evs

            self.assertGreater(len(sample), 0)
            for ev in sample:
                ux, uy, uz = ev["axis"]
                norm_sq = ux * ux + uy * uy + uz * uz
                bn, bd = ev["best"]
                la_ids = leaf_ids(ev["left"])
                rb_ids = leaf_ids(ev["right"])
                self.assertEqual(len(la_ids), ev["left"][6])
                self.assertEqual(len(rb_ids), ev["right"][6])

                # Recompute projection intervals strictly from RAW SOURCE VERTICES + integer frame (never trust ev['gap'])
                if ev["source"] == "box":
                    lbox, rbox = ev["left"], ev["right"]
                    la_min = (ux * lbox[0] if ux >= 0 else ux * lbox[3]) + (uy * lbox[1] if uy >= 0 else uy * lbox[4]) + (uz * lbox[2] if uz >= 0 else uz * lbox[5])
                    la_max = (ux * lbox[3] if ux >= 0 else ux * lbox[0]) + (uy * lbox[4] if uy >= 0 else uy * lbox[1]) + (uz * lbox[5] if uz >= 0 else uz * lbox[2])
                    rb_min = (ux * rbox[0] if ux >= 0 else ux * rbox[3]) + (uy * rbox[1] if uy >= 0 else uy * rbox[4]) + (uz * rbox[2] if uz >= 0 else uz * rbox[5])
                    rb_max = (ux * rbox[3] if ux >= 0 else ux * rbox[0]) + (uy * rbox[4] if uy >= 0 else uy * rbox[1]) + (uz * rbox[5] if uz >= 0 else uz * rbox[2])
                else:
                    dots_a = [p[0] * ux + p[1] * uy + p[2] * uz for tid in la_ids for p in src_a[tid]]
                    dots_b = [p[0] * ux + p[1] * uy + p[2] * uz for tid in rb_ids for p in src_b[tid]]
                    la_min, la_max = min(dots_a), max(dots_a)
                    rb_min, rb_max = min(dots_b), max(dots_b)
                g = max(0, la_min - rb_max, rb_min - la_max)
                lhs = g * g * bd
                rhs = norm_sq * bn
                if ev["strict"]:
                    self.assertGreater(lhs, rhs, (label, ev["source"], g, lhs, rhs))
                else:
                    self.assertGreaterEqual(lhs, rhs, (label, ev["source"], g, lhs, rhs))
                    min_pair_in_sub = (min(la_ids), min(rb_ids))
                    self.assertGreaterEqual(min_pair_in_sub, ev["best_pair"])

        # Synthetic direct box-bound prune control + boundary equality + axis epoch change
        bud = sp._Work(NOOP, {})
        prep_a = [(((0, 0, 0), (0, 1, 0), (1, 0, 0)), (0, 0, 1), 1, (), ((0, 1), (0, 1), (0, 0)))]
        prep_b = [(((0, 0, 3), (0, 1, 3), (1, 0, 3)), (0, 0, 1), 1, (), ((0, 1), (0, 1), (3, 3)))]
        fp_box = sp._FastWitnessProjection.build((4, 1, ("points", (0, 0, 0), (0, 0, 2))), prep_a, prep_b, 1, bud)
        # Exact cutoff boundary equality: g^2 * D == N * ||u||^2 MUST NOT prune strict, MAY prune tie
        na_eq = (0, 0, 0, 1, 1, 0, 1, (0,), None, None, 0, 1, 1, 0)
        nb_eq = (0, 0, 2, 1, 1, 2, 1, (0,), None, None, 0, 1, 1, 4)
        self.assertFalse(fp_box.prunes_nodes(na_eq, nb_eq, True, bud, use_vertex_slab=False))
        self.assertTrue(fp_box.prunes_nodes(na_eq, nb_eq, False, bud, use_vertex_slab=False))

        box_events = []
        self.assertEqual(fp_box.epoch, 1)
        na = (0, 0, 0, 1, 1, 0, 1, (0,), None, None, 0, 1, 1, 0)
        nb = (0, 0, 3, 1, 1, 3, 1, (0,), None, None, 0, 1, 1, 6)
        with patch.object(sp, "_NODE_PRUNE_OBSERVER", lambda ev: box_events.append(ev)):
            ok_box = fp_box.prunes_nodes(na, nb, True, bud, use_vertex_slab=False)
        self.assertTrue(ok_box)
        self.assertEqual(box_events[0]["source"], "box")
        self.assertGreaterEqual(bud.counts.get("witness_projection_box_pruned_pairs", 0), 1)

    def test_c05b_properly_bound_sah_rejection_median_reuse_and_independent_rational_transverse(self):
        b1 = _box_mesh("b1", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), subdiv=2)
        b2 = _box_mesh("b2", (0.875, 0.1875, 0.3125), (1.0, 1.0, 1.0), subdiv=2)

        # 1. Clean direct classification truth
        clean = sg.classify_closed_solids(b1, b2, NOOP)
        self.assertTrue(clean["measurement_valid"])
        self.assertEqual(clean["relation"], "penetrating")
        self.assertEqual(clean["certificate"], "transverse_boundary_interiors")

        # 2. Properly BOUND actual SAH prepared_trees from measure_surface_proximity (matches BOTH pair AND triangles identity)
        holder = {}
        prox = sp.measure_surface_proximity(b1, b2, NOOP, retain_exact_rank=True, _prepared_holder=holder)
        self.assertTrue(prox["measurement_valid"])
        sah_pair = holder["pair"]
        sah_trees = holder["trees"]
        self.assertEqual(sah_trees.get("tree_kind"), "sah_bvh")
        self.assertIs(sah_trees["pair"], sah_pair)
        self.assertTrue(all(a is b for a, b in zip(sah_trees["triangles"], sah_pair[4])))

        diag_sah = {}
        res_sah = sg.classify_closed_solids(
            b1, b2, NOOP, diagnostics=diag_sah,
            prepared_pair=sah_pair, prepared_trees=sah_trees, prepared_holder=holder,
        )
        self.assertNotEqual(diag_sah.get("prepared_trees_reused"), True)
        self.assertEqual(bvh_eval._closed_sig(res_sah), bvh_eval._closed_sig(clean))
        self.assertEqual(holder["trees"].get("tree_kind"), "median_bvh_v1")

        # 3. Properly BOUND compatible median_bvh_v1 prepared_trees positive reuse control
        med_trees = holder["trees"]
        diag_med = {}
        res_med = sg.classify_closed_solids(
            b1, b2, NOOP, diagnostics=diag_med,
            prepared_pair=sah_pair, prepared_trees=med_trees,
        )
        self.assertIs(diag_med.get("prepared_trees_reused"), True)
        self.assertEqual(bvh_eval._closed_sig(res_med), bvh_eval._closed_sig(clean))

        # 4. Independent pure-Fraction transverse-interior predicate (NO call to sp._intersection)
        ev = clean["local_evidence"]
        fi, fj = ev["triangle_indices"]
        A = [tuple(Fraction.from_float(float(c)) for c in b1.vertices[k]) for k in b1.faces[fi]]
        B = [tuple(Fraction.from_float(float(c)) for c in b2.vertices[k]) for k in b2.faces[fj]]

        def sub(u, v): return (u[0] - v[0], u[1] - v[1], u[2] - v[2])
        def add(u, v): return (u[0] + v[0], u[1] + v[1], u[2] + v[2])
        def mul(u, s): return (u[0] * s, u[1] * s, u[2] * s)
        def dot(u, v): return u[0] * v[0] + u[1] * v[1] + u[2] * v[2]
        def cross(u, v): return (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])

        na = cross(sub(A[1], A[0]), sub(A[2], A[0]))
        nb = cross(sub(B[1], B[0]), sub(B[2], B[0]))
        line_dir = cross(na, nb)
        self.assertTrue(any(c != 0 for c in line_dir), "Winner triangles are parallel/coplanar, not transverse")

        def plane_tri_slice(T1, T2, n2):
            ds = [dot(n2, sub(p, T2[0])) for p in T1]
            pts = [p for p, d in zip(T1, ds) if d == 0]
            for idx in range(3):
                nxt = (idx + 1) % 3
                if ds[idx] * ds[nxt] < 0:
                    t = ds[idx] / (ds[idx] - ds[nxt])
                    pts.append(add(T1[idx], mul(sub(T1[nxt], T1[idx]), t)))
            return list(dict.fromkeys(pts))

        def strict_interior(p, T, n):
            n2 = dot(n, n)
            if dot(n, sub(p, T[0])) != 0:
                return False
            u = dot(cross(sub(T[2], T[0]), n), sub(p, T[0])) / n2
            v = dot(cross(n, sub(T[1], T[0])), sub(p, T[0])) / n2
            w = 1 - u - v
            return u > 0 and v > 0 and w > 0

        sa = plane_tri_slice(A, B, nb)
        sb = plane_tri_slice(B, A, na)
        self.assertTrue(len(sa) >= 2 and len(sb) >= 2)
        k_axis = max(range(3), key=lambda k: abs(line_dir[k]))
        sa.sort(key=lambda p: p[k_axis])
        sb.sort(key=lambda p: p[k_axis])
        lo = max(sa[0], sb[0], key=lambda p: p[k_axis])
        hi = min(sa[-1], sb[-1], key=lambda p: p[k_axis])
        self.assertLess(lo[k_axis], hi[k_axis])
        mid = tuple((lo[k] + hi[k]) / 2 for k in range(3))
        self.assertTrue(strict_interior(mid, A, na))
        self.assertTrue(strict_interior(mid, B, nb))


class TestR3_C06_BoundedPrepAndCacheAccounting(unittest.TestCase):
    def test_cancellation_in_every_new_prep_and_compile_stage(self):
        class _Cancelled(RuntimeError):
            pass

        tl, tr = _tilted_plate(8, 0.0), _tilted_plate(8, 0.5, reverse=True)
        ma, mb = _freeze("ca", *tl), _freeze("cb", *tr)

        for st in (
            "surface_proximity_face_validate",
            "surface_proximity_bvh_compile",
            "surface_proximity_validated_faces",
            "surface_proximity_referenced_vertices",
            "surface_proximity_triangle_prepare",
        ):
            cache = {}
            seen = 0
            def cp(s, target=st):
                nonlocal seen
                if s == target:
                    seen += 1
                    if seen == 4:
                        raise _Cancelled(s)
            with self.assertRaises(_Cancelled):
                sp.measure_surface_proximity(ma, mb, cp, _mesh_cache=cache)
            # Subsequent clean call with same cache MUST succeed with exact match
            r_clean = sp.measure_surface_proximity(ma, mb, NOOP, retain_exact_rank=True)
            r_retry = sp.measure_surface_proximity(ma, mb, NOOP, retain_exact_rank=True, _mesh_cache=cache)
            self.assertEqual(bvh_eval._surface_sig(r_clean), bvh_eval._surface_sig(r_retry))

        # Affine bit-domain fallback loop cancellation checkpoint
        ext_a = _freeze("ea", [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)], [(0, 1, 2)] * 17)
        ext_b = _freeze("eb", [(0.0, 0.0, math.ldexp(1.0, -520)), (1.0, 0.0, math.ldexp(1.0, -520)), (0.0, 1.0, math.ldexp(1.0, -520))], [(0, 1, 2)] * 17)
        fb_cache = {}
        seen_rv = 0
        def cp_fb(s):
            nonlocal seen_rv
            if s == "surface_proximity_referenced_vertices":
                seen_rv += 1
                if seen_rv == 9:  # hits inside affine fallback rel_r_in_l / materialization
                    raise _Cancelled("fallback_rv")
        with self.assertRaises(_Cancelled):
            sp.measure_surface_proximity(ext_a, ext_b, cp_fb, _mesh_cache=fb_cache)
        r_fb = sp.measure_surface_proximity(ext_a, ext_b, NOOP, retain_exact_rank=True, _mesh_cache=fb_cache)
        self.assertTrue(r_fb["measurement_valid"])
        self.assertGreater(r_fb["work"].get("mesh_cache_fallbacks", 0), 0)

    def test_bounded_cache_entry_cap_and_retained_geometry_accounting(self):
        fixed = _freeze("fixed", [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], [(0, 1, 2)])
        cap_cache = {}
        for k in range(280):
            mk = _freeze(f"m{k}", [[0.0, 0.0, 2.0 + k * 0.01], [1.0, 0.0, 2.0 + k * 0.01], [0.0, 1.0, 2.0 + k * 0.01]], [(0, 1, 2)])
            sp.measure_surface_proximity(fixed, mk, NOOP, _mesh_cache=cap_cache)
        self.assertLessEqual(len(cap_cache), sp._MESH_CACHE_MAX_ENTRIES)
        total_faces = sum(ent.get("face_count", 0) for ent in cap_cache.values() if isinstance(ent, dict))
        total_ref_v = sum(ent.get("ref_vertex_count", 0) for ent in cap_cache.values() if isinstance(ent, dict))
        self.assertGreater(total_faces, 0)
        self.assertGreater(total_ref_v, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

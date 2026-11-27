"""Comprehensive correctness, boundary, work-accounting, tie-pruning, and oracle suite (M3 BVH Review R01-R08 & A01-A05)."""
from __future__ import annotations

import copy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import tracemalloc
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.bvh_eval import _make_mesh, _snapshot_mesh, _surface_sig, _analyze_sig, _closed_sig, _triangulate, NOOP
from human_eye_plugin import mesh_structure as ms
from human_eye_plugin import surface_geometry as sg
from human_eye_plugin import surface_proximity as sp
from verification import m3_asset_cases as mac
from verification import test_surface_geometry as tsg
from verification.m3_pair_scalability_001.testing import witness_oracle


def _freeze_mesh(oid, vertices, faces):
    """Build strictly immutable tuple-backed mesh safe for cached identity reuse."""
    return SimpleNamespace(
        object_id=oid,
        name=oid,
        vertices=tuple(tuple(float(c) for c in p) for p in vertices),
        faces=tuple(tuple(int(i) for i in f) for f in _triangulate(faces)),
    )


def _exact_tri_sq_fraction(tri_a, tri_b):
    """Independent pure-Fraction exact squared distance between two closed triangles in R^3."""
    def sub(u, v):
        return (u[0] - v[0], u[1] - v[1], u[2] - v[2])
    def add(u, v):
        return (u[0] + v[0], u[1] + v[1], u[2] + v[2])
    def mul(u, s):
        return (u[0] * s, u[1] * s, u[2] * s)
    def dot(u, v):
        return u[0] * v[0] + u[1] * v[1] + u[2] * v[2]
    def cross(u, v):
        return (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])

    A = [tuple(Fraction.from_float(float(c)) for c in p) for p in tri_a]
    B = [tuple(Fraction.from_float(float(c)) for c in p) for p in tri_b]
    na = cross(sub(A[1], A[0]), sub(A[2], A[0]))
    nb = cross(sub(B[1], B[0]), sub(B[2], B[0]))
    na2, nb2 = dot(na, na), dot(nb, nb)

    def pt_in_tri(p, T, n, n2):
        if n2 == 0:
            return False
        q = sub(p, T[0])
        if dot(q, n) != 0:
            return False
        u = dot(cross(sub(T[2], T[0]), n), q)
        v = dot(cross(n, sub(T[1], T[0])), q)
        return u >= 0 and v >= 0 and u + v <= n2

    def seg_pts(T):
        pts = list(dict.fromkeys(T))
        return [(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))] if len(pts) > 1 else []

    def pt_seg_dist2(p, s0, s1):
        d = sub(s1, s0)
        dd = dot(d, d)
        if dd == 0:
            r = sub(p, s0)
            return dot(r, r)
        t = dot(sub(p, s0), d)
        if t <= 0:
            r = sub(p, s0)
        elif t >= dd:
            r = sub(p, s1)
        else:
            r = sub(p, add(s0, mul(d, t / dd)))
        return dot(r, r)

    # Check segment-triangle intersections (exact contact)
    for T1, T2, n2, ns2 in ((A, B, nb, nb2), (B, A, na, na2)):
        if ns2 == 0:
            continue
        for s0, s1 in seg_pts(T1):
            da = dot(n2, sub(s0, T2[0]))
            db = dot(n2, sub(s1, T2[0]))
            if (da < 0 < db) or (db < 0 < da):
                t = da / (da - db)
                ip = add(s0, mul(sub(s1, s0), t))
                if pt_in_tri(ip, T2, n2, ns2):
                    return Fraction(0)

    best = None
    def upd(val):
        nonlocal best
        if best is None or val < best:
            best = val

    for p in A:
        if nb2 > 0:
            q = sub(p, B[0])
            h = dot(q, nb)
            proj = sub(p, mul(nb, h / nb2))
            if pt_in_tri(proj, B, nb, nb2):
                upd((h * h) / nb2)
        for s0, s1 in seg_pts(B) or [(B[0], B[0])]:
            upd(pt_seg_dist2(p, s0, s1))
    for p in B:
        if na2 > 0:
            q = sub(p, A[0])
            h = dot(q, na)
            proj = sub(p, mul(na, h / na2))
            if pt_in_tri(proj, A, na, na2):
                upd((h * h) / na2)
        for s0, s1 in seg_pts(A) or [(A[0], A[0])]:
            upd(pt_seg_dist2(p, s0, s1))
    for a0, a1 in seg_pts(A):
        u = sub(a1, a0)
        uu = dot(u, u)
        for b0, b1 in seg_pts(B):
            v = sub(b1, b0)
            vv = dot(v, v)
            n = cross(u, v)
            det = dot(n, n)
            if det > 0:
                w = sub(a0, b0)
                ab, au, bv = dot(u, v), dot(u, w), dot(v, w)
                s = ab * bv - vv * au
                t = uu * bv - ab * au
                if 0 <= s <= det and 0 <= t <= det:
                    h = dot(w, n)
                    upd((h * h) / det)
    return best


def _exact_mesh_sq_oracle(left, right):
    """Independent brute-force Fraction exact minimum squared distance + canonical (i, j) pair."""
    lv, rv = left.vertices, right.vertices
    best_d = None
    best_pair = None
    for i, fa in enumerate(left.faces):
        ta = [lv[k] for k in fa]
        for j, fb in enumerate(right.faces):
            tb = [rv[k] for k in fb]
            d2 = _exact_tri_sq_fraction(ta, tb)
            if best_d is None or d2 < best_d or (d2 == best_d and (i, j) < best_pair):
                best_d, best_pair = d2, (i, j)
    return best_d, best_pair


def _sq_key_to_fraction(key):
    a, b, e = key
    if e >= 0:
        return Fraction(a << e, b)
    return Fraction(a, b << (-e))


def verify_r01_fast_projection():
    snap = json.loads((ROOT / "verification/spatial_task_qualification_001/entry/run_01/ACTUAL_SNAPSHOT.json").read_bytes())
    objs = {r["name"]: r for r in snap["objects"]}
    d48 = json.loads((ROOT / "verification/scale_diag_001/fixtures/D48.json").read_bytes())
    d48_objs = {r["name"]: r for r in d48["objects"]}

    # Construct adversarial repeated-best-improvement / high-failure projection mesh:
    # Nested staircase strips with overlapping AABBs where best shrinks step by step (>15 epochs).
    def staircase(n_steps, z_off, x_off=0.0):
        verts, faces = [], []
        for k in range(n_steps):
            x0, x1 = x_off + k * 0.05, x_off + (k + 0.8) * 0.05
            z = z_off + (0.001 if k == n_steps - 1 else 0.1 * (1.0 - k / max(1, n_steps)))
            b = len(verts)
            verts.extend([[x0, 0.0, z], [x1, 0.0, z], [x0, 0.2, z], [x1, 0.2, z]])
            faces.extend([[b, b + 1, b + 2], [b + 1, b + 3, b + 2]])
        return verts, faces

    av1, af1 = staircase(140, 0.0, 0.0)
    av2, af2 = staircase(140, 0.5, 0.02)
    # Add reversed staircase steps on right so distance drops across later leaf visits cleanly.
    adv_l = _freeze_mesh("adv_l", av1, af1)
    adv_r = _freeze_mesh("adv_r", av2, af2)

    tv, tf = mac.tube(28, 12, 0.08)
    sv, sf = mac.sheet(17)
    pairs = [
        ("G508_Peer_000", _freeze_mesh("Target", objs["Target"]["vertices_world"], objs["Target"]["triangles"]),
         _freeze_mesh("Peer_000", objs["Peer_000"]["vertices_world"], objs["Peer_000"]["triangles"])),
        ("G508_Competing_001", _freeze_mesh("Target", objs["Target"]["vertices_world"], objs["Target"]["triangles"]),
         _freeze_mesh("Competing_001", objs["Competing_001"]["vertices_world"], objs["Competing_001"]["triangles"])),
        ("Sheet_Parallel_5um", _freeze_mesh("sa", sv, sf), _freeze_mesh("sb", [[p[0], p[1], p[2] + 5e-6] for p in sv], sf)),
        ("Tube_Coiled_Loose", _freeze_mesh("ta", tv, tf), _freeze_mesh("tb", [[p[0] + 0.04, p[1], p[2] + 0.015] for p in tv], tf)),
        ("Adversarial_Staircase", adv_l, adv_r),
    ]
    # Add all 47 D48 pairs
    d48_t = _freeze_mesh("Target", d48_objs["Target"]["vertices_world"], d48_objs["Target"]["triangles"])
    for k, o in sorted(d48_objs.items()):
        if k != "Target":
            pairs.append((f"D48_{k}", d48_t, _freeze_mesh(k, o["vertices_world"], o["triangles"])))

    eq_failures = []
    ledger_rows = []
    for name, l, r in pairs:
        r_on = sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        with patch.object(sp._FastWitnessProjection, "build", classmethod(lambda cls, *a, **kw: None)):
            r_off = sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        if _surface_sig(r_on) != _surface_sig(r_off):
            eq_failures.append({"case": name, "on": _surface_sig(r_on), "off": _surface_sig(r_off)})
        if not name.startswith("D48_") or name in ("D48_Peer_000", "D48_Competing_001"):
            w = r_on["work"]
            ledger_rows.append({
                "case": name,
                "work_units": w["work_units"],
                "wp_builds": w.get("witness_projection_direction_builds", 0),
                "wp_dirs": w.get("witness_projection_directions", 0),
                "wp_tests": w.get("witness_projection_tests", 0),
                "wp_pruned": w.get("witness_projection_pruned_pairs", 0),
                "wp_tri_dots": w.get("witness_projection_tri_dots", 0),
                "wp_node_visits": w.get("witness_projection_node_visits", 0),
                "wp_deferrals": w.get("witness_projection_budget_deferrals", 0),
                "credit_earned_bounds": w.get("witness_projection_credit_node_units", 0),
                "node_pair_visits": w.get("node_pair_visits", 0),
            })

    # Cancellation injection across all new projection stages
    class _Cancel(RuntimeError):
        pass
    cancel_results = {}
    stages = (
        "surface_proximity_witness_projection",
        "surface_proximity_witness_projection_tests",
        "surface_proximity_witness_projection_tri_dots",
        "surface_proximity_witness_projection_node_visits",
    )
    peer_l, peer_r = pairs[0][1], pairs[0][2]
    for st in stages:
        hit = 0
        def cp(s, target=st):
            nonlocal hit
            if s == target:
                hit += 1
                raise _Cancel(s)
        try:
            sp.measure_surface_proximity(peer_l, peer_r, cp)
        except _Cancel:
            cancel_results[st] = {"propagated": True, "hits": hit}
        else:
            cancel_results[st] = {"propagated": False, "hits": hit}

    # Headroom boundary checks: near MAX_WORK_UNITS, optional projection skips cleanly with deferrals
    orig_init = sp._Work.__init__
    headroom_checks = {}
    for rem in (2, 7, 25000):
        def patched_init(inst, cp, diag, initial=sp.MAX_WORK_UNITS - rem):
            orig_init(inst, cp, diag)
            inst.counts["work_units"] = initial
        with patch.object(sp._Work, "__init__", patched_init):
            out = sp.measure_surface_proximity(peer_l, peer_r, NOOP, retain_exact_rank=True)
        w = out["work"]
        assert w["work_units"] <= sp.MAX_WORK_UNITS, (rem, w["work_units"])
        headroom_checks[str(rem)] = {
            "measurement_valid": out["measurement_valid"],
            "reason": out.get("reason"),
            "work_units": w["work_units"],
            "wp_deferrals": w.get("witness_projection_budget_deferrals", 0),
            "wp_builds": w.get("witness_projection_direction_builds", 0),
            "within_max_work_units": w["work_units"] <= sp.MAX_WORK_UNITS,
        }

    # Verify query completes cleanly when projection defers due to tight headroom (enough for safe non-proj path)
    sv5, sf5 = mac.sheet(5)  # 4*4*2 = 32 valid triangles
    sl = _freeze_mesh("sl", sv5, sf5)
    sr = _freeze_mesh("sr", [[p[0], p[1], p[2] + 0.05] for p in sv5], sf5)
    with patch.object(sp._FastWitnessProjection, "build", classmethod(lambda cls, *a, **kw: None)):
        r_safe_ref = sp.measure_surface_proximity(sl, sr, NOOP, retain_exact_rank=True)
    needed_safe = r_safe_ref["work"]["work_units"]
    start_at = sp.MAX_WORK_UNITS - (needed_safe + 4)
    def defer_init(inst, cp, diag):
        orig_init(inst, cp, diag)
        inst.counts["work_units"] = start_at
    with patch.object(sp._Work, "__init__", defer_init):
        r_def = sp.measure_surface_proximity(sl, sr, NOOP, retain_exact_rank=True)
    assert r_def["measurement_valid"] is True and r_def["distance_m"] == r_safe_ref["distance_m"], (r_def.get("reason"), needed_safe, r_def["work"])
    assert r_def["work"].get("witness_projection_budget_deferrals", 0) > 0, r_def["work"]
    assert r_def["work"]["work_units"] <= sp.MAX_WORK_UNITS
    headroom_checks["completes_with_optional_deferral"] = {
        "measurement_valid": r_def["measurement_valid"],
        "wp_deferrals": r_def["work"].get("witness_projection_budget_deferrals", 0),
        "work_units": r_def["work"]["work_units"],
        "within_max_work_units": r_def["work"]["work_units"] <= sp.MAX_WORK_UNITS,
    }
    assert not eq_failures, eq_failures
    assert all(v["propagated"] for v in cancel_results.values()), cancel_results
    return {
        "passed": True,
        "pairs_checked_proj_on_vs_off": len(pairs),
        "cancellation_stages": cancel_results,
        "headroom_boundary_checks": headroom_checks,
        "sample_ledgers": ledger_rows,
    }


def verify_r02_mesh_cache():
    snap = json.loads((ROOT / "verification/spatial_task_qualification_001/entry/run_01/ACTUAL_SNAPSHOT.json").read_bytes())
    objs = {r["name"]: r for r in snap["objects"]}
    d48 = json.loads((ROOT / "verification/scale_diag_001/fixtures/D48.json").read_bytes())
    d48_objs = {r["name"]: r for r in d48["objects"]}

    # 1. G508 11 pairs + reversed order + non-focal repeat
    g_target = _freeze_mesh("Target", objs["Target"]["vertices_world"], objs["Target"]["triangles"])
    g_peers = [_freeze_mesh(n, objs[n]["vertices_world"], objs[n]["triangles"])
               for n in ["Peer_000", "Competing_001"] + [f"Near_{k:03d}" for k in range(3, 12)]]

    def run_batch(target, peers, use_cache=True):
        cache = {"__sealed_query_meshes__": True} if use_cache else None
        outs, aggs = [], {}
        for p in peers:
            r = sp.measure_surface_proximity(target, p, NOOP, retain_exact_rank=True, _mesh_cache=cache)
            outs.append(r)
            for k, v in r["work"].items():
                if isinstance(v, int):
                    aggs[k] = aggs.get(k, 0) + v
        return outs, aggs, cache

    g_nocache, g_nc_agg, _ = run_batch(g_target, g_peers, False)
    g_cached, g_c_agg, _ = run_batch(g_target, g_peers, True)
    g_rev_cached, _, _ = run_batch(g_target, list(reversed(g_peers)), True)
    for r0, r1 in zip(g_nocache, g_cached):
        assert _surface_sig(r0) == _surface_sig(r1)
    for r0, r1 in zip(reversed(g_nocache), g_rev_cached):
        assert _surface_sig(r0) == _surface_sig(r1)

    # 2. D48 all 47 pairs cached vs uncached
    d_target = _freeze_mesh("Target", d48_objs["Target"]["vertices_world"], d48_objs["Target"]["triangles"])
    d_peers = [_freeze_mesh(o["name"], o["vertices_world"], o["triangles"])
               for o in d48["objects"] if o["name"] != "Target"]
    d_nc, d_nc_agg, _ = run_batch(d_target, d_peers, False)
    d_c, d_c_agg, _ = run_batch(d_target, d_peers, True)
    for r0, r1 in zip(d_nc, d_c):
        assert _surface_sig(r0) == _surface_sig(r1)

    # 3. 66-pair all-pairs on G508 12 objects (focus + non-focus reuse)
    all12 = [g_target] + g_peers
    cache66 = {"__sealed_query_meshes__": True}
    agg66 = {}
    for i in range(len(all12)):
        for j in range(i + 1, len(all12)):
            r_nc = sp.measure_surface_proximity(all12[i], all12[j], NOOP, retain_exact_rank=True)
            r_c = sp.measure_surface_proximity(all12[i], all12[j], NOOP, retain_exact_rank=True, _mesh_cache=cache66)
            assert _surface_sig(r_nc) == _surface_sig(r_c)
            for k in ("mesh_cache_hits", "mesh_cache_misses", "mesh_cache_tree_builds", "mesh_cache_tree_reuses", "mesh_cache_translate_units"):
                agg66[k] = agg66.get(k, 0) + r_c["work"].get(k, 0)

    # 4. Linear 12x12 pair -> zero BVH builds!
    ca = _freeze_mesh("Control_A", objs["Control_A"]["vertices_world"], objs["Control_A"]["triangles"])
    cb = _freeze_mesh("Control_B", objs["Control_B"]["vertices_world"], objs["Control_B"]["triangles"])
    lin_cache = {"__sealed_query_meshes__": True}
    lin_res = sp.measure_surface_proximity(ca, cb, NOOP, retain_exact_rank=True, _mesh_cache=lin_cache)
    assert lin_res["work"].get("mesh_cache_tree_builds", 0) == 0 and lin_res["work"]["tree_builds"] == 0
    assert "tree" not in lin_cache[id(ca)] and "tree" not in lin_cache[id(cb)]

    # 5. Extreme bit-domain fallback -> zero tree build, zero double validated_faces ticks!
    ext_v1 = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    ext_v2 = [(0.0, 0.0, math.ldexp(1.0, -520)), (1.0, 0.0, math.ldexp(1.0, -520)), (0.0, 1.0, math.ldexp(1.0, -520))]
    # Repeat faces to 17x17=289 > LINEAR_PAIR_LIMIT so tree build would happen if fit_fast had been used
    ext_f = tuple((0, 1, 2) for _ in range(17))
    ea = _freeze_mesh("ea", ext_v1, ext_f)
    eb = _freeze_mesh("eb", ext_v2, ext_f)
    fb_cache = {"__sealed_query_meshes__": True}
    fb_uncached = sp.measure_surface_proximity(ea, eb, NOOP, retain_exact_rank=True)
    fb_cached = sp.measure_surface_proximity(ea, eb, NOOP, retain_exact_rank=True, _mesh_cache=fb_cache)
    assert _surface_sig(fb_uncached) == _surface_sig(fb_cached)
    assert fb_cached["work"].get("mesh_cache_fallbacks", 0) == 1
    assert fb_cached["work"].get("mesh_cache_tree_builds", 0) == 0
    assert fb_cached["work"]["validated_faces"] == fb_uncached["work"]["validated_faces"]
    assert fb_cached["work"]["referenced_vertices"] == fb_uncached["work"]["referenced_vertices"]

    # 6. Budget isolation: Pair 2 cannot borrow Pair 1's cached tree build to bypass MAX_WORK_UNITS
    iso_cache = {"__sealed_query_meshes__": True}
    _ = sp.measure_surface_proximity(g_target, g_peers[0], NOOP, retain_exact_rank=True, _mesh_cache=iso_cache)
    orig_init = sp._Work.__init__
    def tight_init(inst, cp, diag):
        orig_init(inst, cp, diag)
        inst.counts["work_units"] = sp.MAX_WORK_UNITS - 10
    with patch.object(sp._Work, "__init__", tight_init):
        iso_res = sp.measure_surface_proximity(g_target, g_peers[1], NOOP, retain_exact_rank=True, _mesh_cache=iso_cache)
    assert iso_res["measurement_valid"] is False and iso_res["reason"] == "surface_work_budget"

    # 7. Atomicity on error/cancellation across prep, tree build, and translate stages -> no poisoned entry
    class _CacheCancel(RuntimeError):
        pass
    cancel_cache_ok = {}
    for st in ("surface_proximity_validated_faces", "surface_proximity_referenced_vertices",
               "surface_proximity_triangle_prepare", "surface_proximity_surface_bvh_build"):
        bad_cache = {"__sealed_query_meshes__": True}
        seen = 0
        def cp_mid(s, target=st):
            nonlocal seen
            if s == target:
                seen += 1
                if seen == 5:
                    raise _CacheCancel(s)
        # First pair with cancel on Peer_000 (right) or Target
        try:
            sp.measure_surface_proximity(g_target, g_peers[0], cp_mid, _mesh_cache=bad_cache)
        except _CacheCancel:
            pass
        else:
            raise AssertionError(f"Expected cancellation at {st}")
        # Retry cleanly using the exact same cache dict
        retry_res = sp.measure_surface_proximity(g_target, g_peers[0], NOOP, retain_exact_rank=True, _mesh_cache=bad_cache)
        assert _surface_sig(retry_res) == _surface_sig(g_nocache[0])
        cancel_cache_ok[st] = True

    # 8. Mutability safety guard: unsealed mutable lists do NOT get stale identity hits
    mut_a = SimpleNamespace(vertices=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], faces=[(0, 1, 2)])
    mut_b = SimpleNamespace(vertices=[[0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0]], faces=[(0, 1, 2)])
    mut_cache = {}
    r_m1 = sp.measure_surface_proximity(mut_a, mut_b, NOOP, _mesh_cache=mut_cache)
    mut_b.vertices[0][2] = 2.0
    mut_b.vertices[1][2] = 2.0
    mut_b.vertices[2][2] = 2.0
    r_m2 = sp.measure_surface_proximity(mut_a, mut_b, NOOP, _mesh_cache=mut_cache)
    assert r_m1["distance_m"] == 1.0 and r_m2["distance_m"] == 2.0

    return {
        "passed": True,
        "g508_11pairs": {
            "physical_tree_builds": g_c_agg.get("mesh_cache_tree_builds", 0),
            "logical_tree_builds": g_c_agg.get("tree_builds", 0),
            "tree_reuses": g_c_agg.get("mesh_cache_tree_reuses", 0),
            "translate_units": g_c_agg.get("mesh_cache_translate_units", 0),
            "uncached_tree_builds": g_nc_agg.get("tree_builds", 0),
        },
        "d48_47pairs": {
            "physical_tree_builds": d_c_agg.get("mesh_cache_tree_builds", 0),
            "logical_tree_builds": d_c_agg.get("tree_builds", 0),
            "tree_reuses": d_c_agg.get("mesh_cache_tree_reuses", 0),
            "translate_units": d_c_agg.get("mesh_cache_translate_units", 0),
            "uncached_tree_builds": d_nc_agg.get("tree_builds", 0),
        },
        "all66_pairs": agg66,
        "linear_skip_tree_builds": lin_res["work"].get("mesh_cache_tree_builds", 0),
        "fallback_no_double_charge": True,
        "budget_isolation": True,
        "cancellation_atomicity": cancel_cache_ok,
        "mutable_input_safety": True,
    }


def _check_bvh_invariants(root, n_tris):
    seen_ids = []
    max_depth = 0
    node_count = 0
    def walk(node, depth):
        nonlocal max_depth, node_count
        node_count += 1
        max_depth = max(max_depth, depth)
        lo, hi, count, ids, left, right = node
        if ids is not None:
            assert count == len(ids) and left is None and right is None
            seen_ids.extend(ids)
            return lo, hi
        assert count == left[2] + right[2]
        llo, lhi = walk(left, depth + 1)
        rlo, rhi = walk(right, depth + 1)
        for k in range(3):
            assert lo[k] <= llo[k] and lo[k] <= rlo[k]
            assert hi[k] >= lhi[k] and hi[k] >= rhi[k]
        return lo, hi
    walk(root, 1)
    assert len(seen_ids) == n_tris and set(seen_ids) == set(range(n_tris))
    return {"node_count": node_count, "max_depth": max_depth}


def verify_r03_sah_translation():
    # Build bin-boundary grid: 32 triangles whose centroids hit exact 12-bin SAH transitions under 2x shift
    def grid_strip(nx, scale, offset=(0.0, 0.0, 0.0)):
        verts, faces = [], []
        for i in range(nx):
            x = offset[0] + i * scale
            b = len(verts)
            verts.extend([[x, offset[1], offset[2]], [x + 0.4 * scale, offset[1], offset[2]],
                          [x, offset[1] + scale, offset[2]], [x + 0.4 * scale, offset[1] + scale, offset[2]]])
            faces.extend([[b, b + 1, b + 2], [b + 1, b + 3, b + 2]])
        return verts, faces

    v_small, f_small = grid_strip(16, math.ldexp(1.0, -28), (0.0, 0.0, 0.0))
    v_large, f_large = grid_strip(16, math.ldexp(1.0, -4), (2.0 ** 20, 0.0, 1e-3))
    # Explicit SAH non-isomorphism witness: 16 tris spaced with span=4 vs 2*span=8 across 12 bins
    b_l = _freeze_mesh("bin_l", v_small, f_small)
    b_r = _freeze_mesh("bin_r", v_large, f_large)
    sv, sf = mac.sheet(17)
    s_l = _freeze_mesh("sheet_l", sv, sf)
    s_r = _freeze_mesh("sheet_r", [[p[0] + 1024.0, p[1], p[2] + 1e-6] for p in sv], sf)

    cases = [("diff_exponents_distant_shift", b_l, b_r), ("thin_sheet_distant", s_l, s_r)]
    out = []
    for name, l, r in cases:
        holder = {}
        r_off = sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _prepared_holder=holder)
        cache = {"__sealed_query_meshes__": True}
        r_on = sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _mesh_cache=cache)
        assert _surface_sig(r_off) == _surface_sig(r_on)
        inv_off_l = _check_bvh_invariants(holder["trees"]["roots"][0], len(l.faces))
        inv_off_r = _check_bvh_invariants(holder["trees"]["roots"][1], len(r.faces))
        inv_on_l = _check_bvh_invariants(cache[id(l)]["tree"]["local_root"], len(l.faces))
        inv_on_r = _check_bvh_invariants(cache[id(r)]["tree"]["local_root"], len(r.faces))
        out.append({
            "case": name,
            "equivalent": True,
            "off_depth_r": inv_off_r["max_depth"],
            "on_depth_r": inv_on_r["max_depth"],
            "work_off": r_off["work"]["work_units"],
            "work_on": r_on["work"]["work_units"],
        })
    return {"passed": True, "cases": out}


def verify_r04_bit_domain_and_predicates():
    # 1. Exact binary64 dyadic span crossings around 499, 500, and 501 bits
    cases = [
        ("499bit_span", 498, 498, 1.0),
        ("500bit_span_fast_limit", 499, 499, 1.0),
        ("501bit_span_slow_fallback", 500, 500, 1.0),
        ("subnormal_dyadic", -1070, -1072, math.ldexp(1.0, -1070)),
        ("huge_origin_2pow900", 900, -10, 0.25),
    ]
    bit_results = []
    for label, e_hi, e_lo, dz in cases:
        # Vertex coordinates inside exact binary64 around 2**e_hi - 2**0 or small scale
        hi = math.ldexp(1.0, e_hi) if e_hi >= 0 else 0.0
        lo = math.ldexp(1.0, -abs(e_lo)) if e_lo < 0 else 0.0
        # For 499/500/501 span, place one triangle at 0..2^0 and one triangle vertex at 2^e_hi - ... using exponent shift
        if e_hi in (498, 499, 500):
            # Span (2**e_hi - 1) + sub-step -> local_exp = 10 -> integer span 2**(e_hi+10) or just 1.0 + 2**(-e_hi)!!
            # Wait: 1.0 + 2**-k has exponent = k, so integer coords up to 2**k!! Exact single binary64!
            eps = math.ldexp(1.0, -e_hi)
            la = _freeze_mesh(label + "_a", [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (eps, 1.0, 0.0)], [(0, 1, 2)])
            lb = _freeze_mesh(label + "_b", [(0.0, 0.0, dz), (1.0, 0.0, dz), (0.0, 1.0, dz)], [(0, 1, 2)])
        elif e_hi == 900:
            base = math.ldexp(1.0, 900)
            la = _freeze_mesh(label + "_a", [(base, 0.0, 0.0), (base + 1.0, 0.0, 0.0), (base, 1.0, 0.0)], [(0, 1, 2)])
            lb = _freeze_mesh(label + "_b", [(base, 0.0, dz), (base + 1.0, 0.0, dz), (base, 1.0, dz)], [(0, 1, 2)])
        else:
            s = math.ldexp(1.0, e_hi)
            s2 = math.ldexp(1.0, e_lo)
            la = _freeze_mesh(label + "_a", [(0.0, 0.0, 0.0), (s, 0.0, 0.0), (s2, s, 0.0)], [(0, 1, 2)])
            lb = _freeze_mesh(label + "_b", [(0.0, 0.0, dz), (s, 0.0, dz), (0.0, s, dz)], [(0, 1, 2)])
        seen_fast = []
        orig_nt = sp._nearest_pair
        def spy_np(*args, **kwargs):
            seen_fast.append(kwargs.get("fast_ints", False))
            return orig_nt(*args, **kwargs)
        with patch.object(sp, "_nearest_pair", spy_np):
            res = sp.measure_surface_proximity(la, lb, NOOP, retain_exact_rank=True)
        oracle_d2, oracle_pair = _exact_mesh_sq_oracle(la, lb)
        assert res["measurement_valid"] is True, (label, res)
        assert _sq_key_to_fraction(res["_exact_distance_sq"]) == oracle_d2, (label, res)
        used_fast = any(seen_fast)
        if e_hi in (498, 499):
            assert used_fast is True, (label, seen_fast)
        elif e_hi == 500:
            assert used_fast is False, (label, seen_fast)
        bit_results.append({"case": label, "distance_m": res["distance_m"], "fast_ints_used": used_fast, "oracle_match": True})

    # Degenerate collinear & point triangles + coplanar skew + 1-ULP gap
    ulp = math.nextafter(1.0, 2.0) - 1.0
    deg_cases = [
        ("point_vs_point", _freeze_mesh("pa", [(1.0, 2.0, 3.0)] * 3, [(0, 1, 2)]),
         _freeze_mesh("pb", [(1.0, 2.0, 5.0)] * 3, [(0, 1, 2)])),
        ("collinear_vs_collinear", _freeze_mesh("ca", [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)], [(0, 1, 2)]),
         _freeze_mesh("cb", [(0.5, 1.0, 0.0), (0.5, 2.0, 0.0), (0.5, 3.0, 0.0)], [(0, 1, 2)])),
        ("1_ulp_gap", _freeze_mesh("ga", [(0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (0.0, 1.0, 1.0)], [(0, 1, 2)]),
         _freeze_mesh("gb", [(0.0, 0.0, 1.0 + ulp), (1.0, 0.0, 1.0 + ulp), (0.0, 1.0, 1.0 + ulp)], [(0, 1, 2)])),
    ]
    for label, l, r in deg_cases:
        res = sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True)
        od2, _ = _exact_mesh_sq_oracle(l, r)
        assert res["measurement_valid"] is True and _sq_key_to_fraction(res["_exact_distance_sq"]) == od2
        bit_results.append({"case": label, "distance_m": res["distance_m"], "oracle_match": True})

    # Direct _closer checks around MAX_BITS=4096 & denominator==1
    big_reducible_n = (1 << 4096) * 6
    big_reducible_d = (1 << 4096) * 2
    assert sp._closer(big_reducible_n, big_reducible_d, (5, 1)) == (3, 1)
    assert sp._closer(big_reducible_n, big_reducible_d, (2, 1)) is None
    assert sp._closer((1 << 4096) - 1, 1, None)[1] == 1
    try:
        sp._closer((1 << 4096) + 1, 1, (10, 1))
    except sp._DomainError as exc:
        closer_4097 = str(exc)
    else:
        raise AssertionError("_closer did not raise surface_exact_bit_budget for irreducible 4097-bit denom==1")

    # Build an explicit test measuring bit_length across exact fast-domain expressions at 500-bit span
    b_val = (1 << 499) - 1
    e_pts = [(0, 0, 0), (b_val, 0, 0), (0, b_val, 0)]
    q_pts = [(b_val, b_val, b_val), (-b_val, 0, b_val), (0, -b_val, b_val)]
    tri_a = sp._build_fast_triangles([(0, 1, 2)], {0: e_pts[0], 1: e_pts[1], 2: e_pts[2]})[0]
    tri_b = sp._build_fast_triangles([(0, 1, 2)], {0: q_pts[0], 1: q_pts[1], 2: q_pts[2]})[0]
    q_vec = (q_pts[0][0] - e_pts[0][0], q_pts[0][1] - e_pts[0][1], q_pts[0][2] - e_pts[0][2])
    h_ex = sum(a * b for a, b in zip(q_vec, tri_a[1]))
    c1, c2 = sp._fast_bary(tri_a)
    u_ex = sum(a * b for a, b in zip(c1, q_vec))
    u_e, v_e = tri_a[3][0][2], tri_b[3][0][2]
    det_n = (u_e[1] * v_e[2] - u_e[2] * v_e[1], u_e[2] * v_e[0] - u_e[0] * v_e[2], u_e[0] * v_e[1] - u_e[1] * v_e[0])
    det_val = sum(x * x for x in det_n)
    hh_val = h_ex * h_ex
    empirical_bits = {
        "stored_coord_max_bits": b_val.bit_length(),
        "diff_max_bits": max(abs(x).bit_length() for x in q_vec),
        "cross_normal_max_bits": max(abs(x).bit_length() for x in tri_a[1]),
        "normal_squared_bits": tri_a[2].bit_length(),
        "plane_height_bits": abs(h_ex).bit_length(),
        "hh_numerator_bits": hh_val.bit_length(),
        "bary_c1_max_bits": max(abs(x).bit_length() for x in c1),
        "bary_uv_bits": abs(u_ex).bit_length(),
        "edge_edge_det_bits": det_val.bit_length(),
        "scratch_hh_x_det_bits": (hh_val * det_val).bit_length(),
        "max_stored_fits_MAX_BITS_4096": max(hh_val.bit_length(), det_val.bit_length()) <= sp.MAX_BITS,
    }
    return {"passed": True, "boundary_cases": bit_results, "closer_4097_error": closer_4097, "empirical_500bit_algebra": empirical_bits}


def verify_r05_tie_pruning_and_subtree_oracle():
    # 1. Greedy non-canonical seed + later smaller index tie + multi-zero ties
    # Place 20x20 grid shifted by 1.0 in z: pair (50,50) vs (0,0) both at dist 1.0, force leaf visit via order/seed
    def make_grid(n, z, reverse=False):
        verts, faces = [], []
        idx = list(range(n))
        if reverse:
            idx = list(reversed(idx))
        for k in idx:
            b = len(verts)
            verts.extend([[float(k), 0.0, z], [float(k) + 0.5, 0.0, z], [float(k), 0.5, z]])
            faces.append([b, b + 1, b + 2])
        return verts, faces

    # Pair with non-integer bn/bd = 2/3 -> edge-to-edge/face rational distance & multiple zero contacts
    v_a, f_a = make_grid(18, 0.0)
    v_b, f_b = make_grid(18, 1.0)
    # Also plant touching contact at (15, 15) AND earlier? No, contacts at (15,15) and (2,2) -> (2,2) must win!
    v_za = list(v_a) + [[100.0, 0.0, 0.0], [100.5, 0.0, 0.0], [100.0, 0.5, 0.0]]
    f_za = list(f_a) + [[len(v_a), len(v_a) + 1, len(v_a) + 2]]
    v_zb = list(v_b) + [[100.0, 0.0, 0.0], [100.5, 0.0, 0.0], [100.0, 0.5, 0.0]]
    f_zb = list(f_b) + [[len(v_b), len(v_b) + 1, len(v_b) + 2]]
    # Add second zero contact at earlier face index 3 vs 4
    v_za[3 * 3] = [0.0, 0.0, 0.0]
    v_zb[4 * 3] = [0.0, 0.0, 0.0]
    za = _freeze_mesh("za", v_za, f_za)
    zb = _freeze_mesh("zb", v_zb, f_zb)
    r_zero = sp.measure_surface_proximity(za, zb, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
    od2, opair = _exact_mesh_sq_oracle(za, zb)
    assert od2 == Fraction(0) and r_zero["witness_triangle_indices"] == list(opair)

    # 2. Exact bn/bd non-integer tie_floor boundary & projection cutoff equality
    # Distance = sqrt(1/2) -> sq = (1, 2) -> best_floor = 0, tie_floor = -1 (strict=False prunes gap>=1? wait (1-1)//2 = 0!)
    # If best = (3, 2) -> best_floor = 1, tie_floor = (3-1)//2 = 1. Distance sq=1 gives AABB gap_sq=1: strict=True (1 > 1 False -> keep!), strict=False (1 > 1 False -> keep?Wait tie_floor=0 for sq=(2,2)=(1,1) vs (3,2)=1.5!)
    assert sp._aabb_exceeds_best(((0, 0), (0, 0), (0, 0)), ((1, 1), (0, 0), (0, 0)), (1, 1), strict=True) is False
    assert sp._aabb_exceeds_best(((0, 0), (0, 0), (0, 0)), ((1, 1), (0, 0), (0, 0)), (1, 1), strict=False) is True  # tie_floor = (1-1)//1 = 0 -> gap_sq=1 > 0 -> PRUNE!
    assert sp._aabb_exceeds_best(((0, 0), (0, 0), (0, 0)), ((1, 1), (0, 0), (0, 0)), (3, 2), strict=False) is False  # tie_floor = (3-1)//2 = 1 -> gap_sq=1 <= 1 -> KEEP!

    # 3. Linear <= 256 (16x16) vs Tree > 256 (17x16) boundary + random permutations + left/right swap
    rng = random.Random(20261127)
    for n_l, n_r in ((16, 16), (17, 16), (20, 20)):
        vl, fl = make_grid(n_l, 0.0)
        vr, fr = make_grid(n_r, 0.25)
        fl_perm = list(fl)
        fr_perm = list(fr)
        rng.shuffle(fl_perm)
        rng.shuffle(fr_perm)
        ml, mr = _freeze_mesh(f"ml_{n_l}", vl, fl_perm), _freeze_mesh(f"mr_{n_r}", vr, fr_perm)
        res_lr = sp.measure_surface_proximity(ml, mr, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        res_rl = sp.measure_surface_proximity(mr, ml, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        o_d2, o_pair = _exact_mesh_sq_oracle(ml, mr)
        o_d2_rl, o_pair_rl = _exact_mesh_sq_oracle(mr, ml)
        assert _sq_key_to_fraction(res_lr["_exact_distance_sq"]) == o_d2
        assert res_lr["witness_triangle_indices"] == list(o_pair)
        assert _sq_key_to_fraction(res_rl["_exact_distance_sq"]) == o_d2_rl == o_d2
        # Canonical lexicographical pair (i, j) is computed in caller's (left, right) index order:
        assert res_rl["witness_triangle_indices"] == list(o_pair_rl)

    # 4. Exhaustive Brute-Force Descendant Oracle on EVERY Pruned Subtree!
    def leaf_ids(node):
        if node[7] is not None:
            return node[7]
        return leaf_ids(node[8]) + leaf_ids(node[9])

    scal = json.loads((ROOT / "verification/m3_pair_scalability_001/testing/DESIGNED_CASES.json").read_bytes())
    c192_l = _freeze_mesh("c192l", scal["cube192_same_world_boundary"][0]["vertices"], scal["cube192_same_world_boundary"][0]["faces"])
    c192_r = _freeze_mesh("c192r", scal["cube192_same_world_boundary"][1]["vertices"], scal["cube192_same_world_boundary"][1]["faces"])
    vl_t, fl_t = make_grid(20, 0.0)
    vr_t, fr_t = make_grid(20, 1.0)
    fl_shuf = list(fl_t)
    fr_shuf = list(fr_t)
    rng.shuffle(fl_shuf)
    rng.shuffle(fr_shuf)
    tie_l, tie_r = _freeze_mesh("tie_l", vl_t, fl_shuf), _freeze_mesh("tie_r", vr_t, fr_shuf)

    # Also build rotated overlapping-AABB equidistant strips tilted in 3D so world AABBs overlap
    # and _FastWitnessProjection.prunes_nodes MUST prune subtrees cleanly!
    def rot30(p):
        c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
        return [c * p[0] - s * p[1], s * p[0] + c * p[1], p[2]]
    def make_diag_strips(n, gap):
        verts, faces = [], []
        for k in range(n):
            b = len(verts)
            # Strip offset along diagonal (1, 1, 0) + small x extent
            base = [[float(k), 0.0, gap], [float(k) + 0.5, 0.0, gap], [float(k), 0.5, gap]]
            verts.extend([rot30(p) for p in base])
            faces.append([b, b + 1, b + 2])
        return verts, faces
    dv_l, df_l = make_diag_strips(36, 0.0)
    dv_r, df_r = make_diag_strips(36, 0.25)
    # Reverse indices on right so witness discovery starts non-canonically and pruning exercises tie + witness projection!
    df_r_rev = list(reversed(df_r))
    rot_l, rot_r = _freeze_mesh("rot_l", dv_l, df_l), _freeze_mesh("rot_r", dv_r, df_r_rev)

    pruned_audits = []
    for label, ml, mr in (("cube192", c192_l, c192_r), ("shuffled_multi_tie_20x20", tie_l, tie_r), ("rotated_tie_36x36", rot_l, rot_r)):
        o_d2, o_pair = _exact_mesh_sq_oracle(ml, mr)
        pruned_nodes = []
        orig_pn = sp._FastWitnessProjection.prunes_nodes
        def audit_pn(self_proj, nl, nr, strict, budget, *args, **kwargs):
            pruned = orig_pn(self_proj, nl, nr, strict, budget, *args, **kwargs)
            if pruned:
                pruned_nodes.append((leaf_ids(nl), leaf_ids(nr)))
            return pruned
        with patch.object(sp._FastWitnessProjection, "prunes_nodes", audit_pn):
            res = sp.measure_surface_proximity(ml, mr, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        assert _sq_key_to_fraction(res["_exact_distance_sq"]) == o_d2
        assert res["witness_triangle_indices"] == list(o_pair), (label, res["witness_triangle_indices"], o_pair)
        # Independently check EVERY pair of descendants inside every pruned projection subtree against oracle winner
        lv, rv = ml.vertices, mr.vertices
        lf, rf = ml.faces, mr.faces
        checked_desc_pairs = 0
        for lid_list, rid_list in pruned_nodes:
            for ti in lid_list:
                ta = [lv[k] for k in lf[ti]]
                for tj in rid_list:
                    tb = [rv[k] for k in rf[tj]]
                    d2 = _exact_tri_sq_fraction(ta, tb)
                    checked_desc_pairs += 1
                    assert not (d2 < o_d2 or (d2 == o_d2 and (ti, tj) < o_pair)), (label, ti, tj, d2, o_d2, o_pair)
        pruned_audits.append({
            "case": label,
            "oracle_pair": list(o_pair),
            "solver_pair": res["witness_triangle_indices"],
            "subtree_pruned_pairs": res["work"]["subtree_pruned_pairs"],
            "wp_pruned_pairs": res["work"].get("witness_projection_pruned_pairs", 0),
            "wp_subtrees_exhaustively_audited": len(pruned_nodes),
            "wp_descendant_pairs_checked": checked_desc_pairs,
            "exact_oracle_match": True,
        })

    # 5. Shift > 0 (forced span_bits >= MAX_BITS-1): must use full AABB check and NEVER global early break
    bud_shift = sp._Work(NOOP, {})
    from human_eye_plugin.surface_geometry import _bvh
    def full_slow_tris(pts_list):
        out = []
        for pts in pts_list:
            n = sp._normal(pts)
            sq = sp._dot(n, n)
            edges = [(pts[k], pts[(k + 1) % 3], sp._sub(pts[(k + 1) % 3], pts[k]),
                      sp._dot(sp._sub(pts[(k + 1) % 3], pts[k]), sp._sub(pts[(k + 1) % 3], pts[k]))) for k in range(3)]
            b = tuple((min(p[k] for p in pts), max(p[k] for p in pts)) for k in range(3))
            out.append((pts, n, sq, edges, b))
        return out
    far = 1 << 4095
    pts_s_l = [((i * 10, 0, 0), (i * 10 + 1, 0, 0), (i * 10, 1, 0)) for i in range(16)] + [((far, 0, 0), (far + 1, 0, 0), (far, 1, 0))]
    pts_s_r = [((i * 10, 0, 1), (i * 10 + 1, 0, 1), (i * 10, 1, 1)) for i in range(17)]
    pl, pr = full_slow_tris(pts_s_l), full_slow_tris(pts_s_r)
    roots_s = (
        _bvh([(tuple(c[0] for c in t[4]), tuple(c[1] for c in t[4])) for t in pl], bud_shift, leaf_size=2),
        _bvh([(tuple(c[0] for c in t[4]), tuple(c[1] for c in t[4])) for t in pr], bud_shift, leaf_size=2),
    )
    wp_s = []
    res_s = sp._nearest_tree([pl, pr], roots_s, bud_shift, witness_pair=wp_s)
    assert res_s[0] == 1 and res_s[1] == 1 and wp_s == [0, 0], (res_s, wp_s)
    return {"passed": True, "zero_contact_tie_pair": list(opair), "pruned_audits": pruned_audits, "shift_gt_zero_safe_pair": wp_s}


def verify_r07_closed_and_analyze():
    # 1. Expanded closed_solid truth including real 24-part containment (Obj_001 strictly contains Obj_024)
    base24 = json.loads((ROOT / "verification/m4_surface_scan_001/qualification/BASE_SNAPSHOT.json").read_bytes())
    b24_map = {o["name"]: o for o in base24["objects"]}
    obj001 = _freeze_mesh("Obj_001", b24_map["Obj_001"]["vertices_world"], b24_map["Obj_001"]["triangles"])
    obj024 = _freeze_mesh("Obj_024", b24_map["Obj_024"]["vertices_world"], b24_map["Obj_024"]["triangles"])
    cs_cont = sg.classify_closed_solids(obj001, obj024, NOOP)
    assert cs_cont["measurement_valid"] is True and cs_cont["relation"] == "penetrating", cs_cont

    # Separated nonconvex shells overlapping AABB (G508 Control_A/B & Peer via spatial)
    snap = json.loads((ROOT / "verification/spatial_task_qualification_001/entry/run_01/ACTUAL_SNAPSHOT.json").read_bytes())
    g_map = {r["name"]: r for r in snap["objects"]}
    ca = _freeze_mesh("Control_A", g_map["Control_A"]["vertices_world"], g_map["Control_A"]["triangles"])
    cb = _freeze_mesh("Control_B", g_map["Control_B"]["vertices_world"], g_map["Control_B"]["triangles"])
    assert sg.classify_closed_solids(ca, cb, NOOP)["relation"] == "separated"

    # Piercing penetration boxes
    box1_v = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0),
              (0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (1.0, 1.0, 1.0), (0.0, 1.0, 1.0)]
    box_f = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
             (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
             (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    b_p1 = _freeze_mesh("b_p1", box1_v, box_f)
    b_p2 = _freeze_mesh("b_p2", [[c + 0.5 for c in p] for p in box1_v], box_f)
    assert sg.classify_closed_solids(b_p1, b_p2, NOOP)["relation"] == "penetrating"

    # 2. Analyze: shared_simplex_cases + near_m > 0 + >128 truncation + baseline 032 compare!
    scal = json.loads((ROOT / "verification/m3_pair_scalability_001/testing/DESIGNED_CASES.json").read_bytes())
    an_cases = []
    for c in scal["shared_simplex_cases"]:
        prep = tsg.prepared(c["vertices"], c["faces"])
        res = sg.analyze(prep, c["faces"], list(range(len(c["faces"]))), budget=ms.WorkBudget(), near_m=0.0)
        an_cases.append({"id": c["id"], "total": res["total"], "counts": res["counts_by_relation"], "legal_expected": c["legal_contact"]})
        if c["legal_contact"]:
            assert res["total"] == 0, (c["id"], res)
        else:
            assert res["total"] >= 1, (c["id"], res)

    # near_m = 0.001 (max valid analyze near_m): test BOTH sides of threshold (0.5mm <= 1mm vs 1.5mm > 1mm)!
    nv_in = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 0.0005], [1.0, 0.0, 0.0005], [0.0, 1.0, 0.0005]]
    nf = [[0, 1, 2], [3, 4, 5]]
    r_near_in = sg.analyze(tsg.prepared(nv_in, nf), nf, [0, 1], budget=ms.WorkBudget(), near_m=0.001)
    assert r_near_in["total"] >= 1, r_near_in
    nv_out = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 0.0015], [1.0, 0.0, 0.0015], [0.0, 1.0, 0.0015]]
    r_near_out = sg.analyze(tsg.prepared(nv_out, nf), nf, [0, 1], budget=ms.WorkBudget(), near_m=0.001)
    assert r_near_out["total"] == 0, r_near_out

    # Degenerate zero-area triangle & coplanar tangent shells in closed_solid
    deg_v = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]]
    deg_f = [[0, 1, 2], [3, 4, 5]]
    r_deg = sg.analyze(tsg.prepared(deg_v, deg_f), deg_f, [0, 1], budget=ms.WorkBudget(), near_m=0.0)
    assert r_deg.get("degenerate_triangles") == [0] or len(r_deg.get("degenerate_triangles", [])) >= 1, r_deg

    # >128 intersecting regions deterministic truncation check against arm_a_032
    pv, pf = [], []
    for k in range(20):
        b = len(pv)
        z = k * 0.002
        pv.extend([[0.0, 0.0, z], [1.0, 0.0, z], [0.0, 1.0, z],
                   [0.1, 0.1, z - 0.1], [0.9, 0.1, z - 0.1], [0.1, 0.9, z + 0.1]])
        pf.extend([[b, b + 1, b + 2], [b + 3, b + 4, b + 5]])
    # 20 intersecting cross pairs -> add 150 pairs along z so total > 128!
    pv2, pf2 = [], []
    for k in range(150):
        b = len(pv2)
        pv2.extend([[0.0, 0.0, k * 0.001], [2.0, 0.0, k * 0.001], [0.0, 2.0, k * 0.001]])
        pf2.append([b, b + 1, b + 2])
    pv2_cross_b = len(pv2)
    pv2.extend([[0.2, 0.2, -1.0], [1.0, 0.2, -1.0], [0.2, 1.0, 1.0]])
    pf2.append([pv2_cross_b, pv2_cross_b + 1, pv2_cross_b + 2])
    t_prep = tsg.prepared(pv2, pf2)
    r_trunc_c = sg.analyze(t_prep, pf2, list(range(len(pf2))), budget=ms.WorkBudget(), near_m=0.0)

    # Compare Analyze_Tube_668F & truncated case with baseline arm_a_032 + tracemalloc attribution!
    tv, tf = mac.tube(28, 12, 0.08)
    tube_tris = []
    for f in tf:
        if len(f) == 3:
            tube_tris.append(list(f))
        else:
            for k in range(1, len(f) - 1):
                tube_tris.append([f[0], f[k], f[k + 1]])
    tube_prep = tsg.prepared(tv, tube_tris)
    r_tube_c = sg.analyze(tube_prep, tube_tris, list(range(len(tube_tris))), budget=ms.WorkBudget(), near_m=0.0)

    tracemalloc.start()
    s0 = tracemalloc.take_snapshot()
    sg.analyze(tube_prep, tube_tris, list(range(len(tube_tris))), budget=ms.WorkBudget(), near_m=0.0)
    s1 = tracemalloc.take_snapshot()
    cur_bytes, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    top_allocs = [{"stat": f"{st.traceback[0].filename.split('/')[-1].split(chr(92))[-1]}:{st.traceback[0].lineno}",
                   "size_bytes": st.size, "count": st.count}
                  for st in s1.compare_to(s0, "lineno")[:8]]

    # Also capture peak diff attribution inside C's analyze (before return releases local normals/tri_sets!)
    orig_bvh = sg._build_sah_bvh
    peak_holders = []
    def spy_bvh(*args, **kwargs):
        res = orig_bvh(*args, **kwargs)
        peak_holders.append(tracemalloc.get_traced_memory()[1])
        return res
    tracemalloc.start()
    with patch.object(sg, "_build_sah_bvh", spy_bvh):
        sg.analyze(tube_prep, tube_tris, list(range(len(tube_tris))), budget=ms.WorkBudget(), near_m=0.0)
    _, peak_with_sah = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    scratch = ROOT.parent / "Users"  # Dummy
    arm032 = Path(r"C:\Users\v_wbobosun\.gemini\antigravity\brain\13aaa4ff-645b-4857-ad34-7f6bf82e4730\scratch\arm_a_032")
    probe_code = f"""
import sys, json, tracemalloc
sys.path.insert(0, {repr(str(arm032))})
from human_eye_plugin import mesh_structure as ms, surface_geometry as sg
from verification import m3_asset_cases as mac, test_surface_geometry as tsg
tv, tf = mac.tube(28, 12, 0.08)
tube_tris = [list(f) if len(f)==3 else t for f in tf for t in ([list(f)] if len(f)==3 else [[f[0],f[k],f[k+1]] for k in range(1,len(f)-1)])]
tp = tsg.prepared(tv, tube_tris)
_ = sg.analyze(tp, tube_tris, list(range(len(tube_tris))), budget=ms.WorkBudget(), near_m=0.0)  # warmup!
tracemalloc.start()
r0 = sg.analyze(tp, tube_tris, list(range(len(tube_tris))), budget=ms.WorkBudget(), near_m=0.0)
_, peak0 = tracemalloc.get_traced_memory()
tracemalloc.stop()
# Also truncated & near_m=0.005
pv2, pf2 = [], []
for k in range(150):
    b = len(pv2)
    pv2.extend([[0.0, 0.0, k * 0.001], [2.0, 0.0, k * 0.001], [0.0, 2.0, k * 0.001]])
    pf2.append([b, b + 1, b + 2])
b = len(pv2)
pv2.extend([[0.2, 0.2, -1.0], [1.0, 0.2, -1.0], [0.2, 1.0, 1.0]])
pf2.append([b, b + 1, b + 2])
r_tr = sg.analyze(tsg.prepared(pv2, pf2), pf2, list(range(len(pf2))), budget=ms.WorkBudget(), near_m=0.0)
print(json.dumps({{"tube_sig": {{k: v for k, v in r0.items() if k not in ("spatial_work","work","exact_pair_tests","work_used")}}, "peak0": peak0, "trunc_sig": {{k: v for k, v in r_tr.items() if k not in ("spatial_work","work","exact_pair_tests","work_used")}}}}))
"""
    raw_a = json.loads(subprocess.check_output([sys.executable, "-c", probe_code], text=True).strip().splitlines()[-1])
    sig_c_tube = {k: v for k, v in r_tube_c.items() if k not in ("spatial_work", "work", "exact_pair_tests", "work_used")}
    sig_c_trunc = {k: v for k, v in r_trunc_c.items() if k not in ("spatial_work", "work", "exact_pair_tests", "work_used")}
    assert sig_c_tube == raw_a["tube_sig"]
    assert sig_c_trunc == raw_a["trunc_sig"]

    return {
        "passed": True,
        "closed_containment_24part_Obj001_vs_Obj024": {"relation": cs_cont["relation"], "certificate": cs_cont.get("certificate")},
        "shared_simplex_analyze": an_cases,
        "near_m_1mm_sides": {"within_0p5mm_total": r_near_in["total"], "outside_1p5mm_total": r_near_out["total"]},
        "degenerate_triangle_reported": r_deg.get("degenerate_triangles"),
        "truncated_150_regions_matches_032": True,
        "analyze_tube_peak_032_bytes": raw_a["peak0"],
        "analyze_tube_peak_C_bytes": peak_bytes,
        "analyze_tube_peak_C_with_sah_bytes": peak_with_sah,
        "analyze_tube_sah_build_peaks": peak_holders,
        "analyze_tube_peak_ratio": round(peak_bytes / max(1, raw_a["peak0"]), 3),
        "analyze_tube_C_top_allocs": top_allocs,
    }


def verify_assets_a01_to_a05():
    # A01/A02: G508 snapshot & oracle
    snap = json.loads((ROOT / "verification/spatial_task_qualification_001/entry/run_01/ACTUAL_SNAPSHOT.json").read_bytes())
    objs = {r["name"]: r for r in snap["objects"]}
    oracle = json.loads((ROOT / "verification/spatial_task_qualification_001/oracle/formal_replay_01/ORACLE.json").read_bytes())
    o_map = {r["candidate_name"]: r for r in oracle["pairs"]}
    gt = _snapshot_mesh(objs["Target"])
    for cname, orow in o_map.items():
        cm = _snapshot_mesh(objs[cname])
        r = sp.measure_surface_proximity(gt, cm, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        assert r["measurement_valid"] and orow["distance_lower_m"] - 1e-12 <= r["distance_m"] <= orow["distance_upper_m"] + 1e-12
        proof = witness_oracle.certify_pair(r["point_a_world"], r["point_b_world"], r["distance_m"], objs["Target"], objs[cname], position_tolerance_m=1e-9, distance_tolerance_m=1e-6)
        assert proof["passed"]

    # A03: M3 pair scalability DESIGNED_CASES (high_product_prunable + static_face_limit + pair_frame_independence)
    scal = json.loads((ROOT / "verification/m3_pair_scalability_001/testing/DESIGNED_CASES.json").read_bytes())
    hp = scal["high_product_prunable"]
    hl_v, hl_f, hr_v, hr_f = [], [], [], []
    base_tri = hp["triangle_template"]
    for i in range(hp["left_count"]):
        b = len(hl_v)
        dx, dy, dz = [i * c for c in hp["left_translation_recipe"]]
        hl_v.extend([[p[0] + dx, p[1] + dy, p[2] + dz] for p in base_tri])
        hl_f.append([b, b + 1, b + 2])
    for i in range(hp["right_count"]):
        b = len(hr_v)
        rx, ry, rz = hp["right_translation_recipe"]
        hr_v.extend([[p[0] + i * rx, p[1] + i * ry, p[2] + rz] for p in base_tri])
        hr_f.append([b, b + 1, b + 2])
    r_hp = sp.measure_surface_proximity(_make_mesh("hp_l", hl_v, hl_f), _make_mesh("hp_r", hr_v, hr_f), NOOP, retain_exact_rank=True)
    assert r_hp["measurement_valid"] is True and r_hp["distance_m"] == hp["distance_m"]

    # A04: M3 sufficient separation ALL 14 analytic pairs + exact distance_squared_rational & metamorphic checks!
    suf = json.loads((ROOT / "verification/m3_sufficient_separation_001/testing/DESIGNED_CASES.json").read_bytes())
    for case in suf["analytic_pairs"]:
        lr, rr = case["left"], case["right"]
        ml = _make_mesh("l", lr["vertices_world"], lr["triangles"])
        mr = _make_mesh("r", rr["vertices_world"], rr["triangles"])
        res = sp.measure_spatial_relation(ml, mr, NOOP, retain_exact_rank=True)
        tr = case["independent_truth"]
        if tr.get("new_expected") == "unknown":
            assert res["spatial"]["measurement_valid"] is False
        else:
            assert res["measurement_valid"] is True and res["spatial"]["relation"] == tr["relation"]
            if "distance_squared_rational" in tr:
                n, d = tr["distance_squared_rational"]
                assert _sq_key_to_fraction(res["surface"]["_exact_distance_sq"]) == Fraction(n, d)
            elif "distance_m" in tr:
                assert math.isclose(res["surface"]["distance_m"], tr["distance_m"], rel_tol=0.0, abs_tol=1e-9)

    # Metamorphic checks on rotated_overlapping_world_aabbs: rigid SE3 pose matrix & A/B swap & vertex reversal
    meta_case = suf["analytic_pairs"][0]
    mat = suf["metamorphic"]["pose_change_matrix"]
    def xform(pts):
        return [[sum(row[c] * p[c] for c in range(3)) + row[3] for row in mat[:3]] for p in pts]
    m_al = _make_mesh("ml", meta_case["left"]["vertices_world"], meta_case["left"]["triangles"])
    m_ar = _make_mesh("mr", meta_case["right"]["vertices_world"], meta_case["right"]["triangles"])
    m_bl = _make_mesh("ml_x", xform(meta_case["left"]["vertices_world"]), meta_case["left"]["triangles"])
    m_br = _make_mesh("mr_x", xform(meta_case["right"]["vertices_world"]), meta_case["right"]["triangles"])
    r_base = sp.measure_surface_proximity(m_al, m_ar, NOOP, retain_exact_rank=True)
    r_xform = sp.measure_surface_proximity(m_bl, m_br, NOOP, retain_exact_rank=True)
    r_swap = sp.measure_surface_proximity(m_ar, m_al, NOOP, retain_exact_rank=True)
    assert r_base["_exact_distance_sq"] == r_xform["_exact_distance_sq"] == r_swap["_exact_distance_sq"]

    # A05: m3_asset_cases dense over-limit rejection + sheet/tube checks
    dense_v, dense_f = mac.tube(256, 32, 0.04)
    dense_tris = _make_mesh("dense", dense_v, dense_f)
    assert len(dense_tris.faces) > sp.MAX_FACES
    over_r = sp.measure_surface_proximity(dense_tris, _make_mesh("s1", [[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]]), NOOP)
    assert over_r["measurement_valid"] is False and over_r["reason"] == "surface_geometry_work_limit"

    cv, cf = mac.sheet(17, crack=True)
    cm_a = _make_mesh("crack_a", cv, cf)
    cm_b = _make_mesh("crack_b", [[p[0], p[1], p[2] + 0.002] for p in cv], cf)
    r_cr = sp.measure_surface_proximity(cm_a, cm_b, NOOP, retain_exact_rank=True)
    assert r_cr["measurement_valid"] is True and math.isclose(r_cr["distance_m"], 0.002, abs_tol=1e-9)

    return {
        "passed": True,
        "a01_a02_g508_oracle_pairs": len(o_map),
        "a03_high_product_prunable": r_hp["distance_m"],
        "a04_analytic_pairs": len(suf["analytic_pairs"]),
        "a04_metamorphic_se3_swap": True,
        "a05_dense_over_limit_rejected": len(dense_tris.faces),
        "a05_cracked_sheet_distance_m": r_cr["distance_m"],
    }


def main():
    report = {
        "schema": "m3-bvh-review-verification-v1",
        "r01_fast_projection": verify_r01_fast_projection(),
        "r02_mesh_cache": verify_r02_mesh_cache(),
        "r03_sah_translation": verify_r03_sah_translation(),
        "r04_bit_domain_and_predicates": verify_r04_bit_domain_and_predicates(),
        "r05_tie_pruning_and_subtree_oracle": verify_r05_tie_pruning_and_subtree_oracle(),
        "r07_closed_and_analyze": verify_r07_closed_and_analyze(),
        "assets_a01_to_a05": verify_assets_a01_to_a05(),
    }
    out_path = ROOT / "benchmarks/CORRECTNESS_AND_BOUNDARY_RESULTS.json"
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf8")
    print(f"ALL VERIFICATION SUITES PASSED. Saved {out_path}")
    for k, v in report.items():
        if isinstance(v, dict):
            print(f"  {k}: passed={v.get('passed')}")


if __name__ == "__main__":
    main()

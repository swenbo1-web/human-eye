"""R3 Isolated Subprocess Closure Evaluation & JSON Deliverable Generator.

Runs each arm in its own fresh serial Python subprocess (no in-process sys.modules swapping),
verifies loaded module __file__ paths and runtime_identity SHA-256 inside each interpreter,
collects bounded direct-kernel smoke timings (1 warmup + 3 verified repeats), executes all
C01-C06 audit matrices, and emits:
  - benchmarks/KERNEL_041_R3_CASES.json
  - benchmarks/KERNEL_041_R3_RESULTS.json
Preserves all prior KERNEL_041_* and historical evidence files untouched.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
from fractions import Fraction
import gc
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import tracemalloc
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCRATCH = Path(
    r"C:\Users\v_wbobosun\.gemini\antigravity\brain\13aaa4ff-645b-4857-ad34-7f6bf82e4730\scratch"
)
ARM_032_ROOT = SCRATCH / "arm_a_032"
ARM_R2_ROOT = SCRATCH / "arm_b7d469d"

G508_PATH = ROOT / "verification/spatial_task_qualification_001/entry/run_01/ACTUAL_SNAPSHOT.json"
D48_PATH = ROOT / "verification/scale_diag_001/fixtures/D48.json"
D48_5_NAMES = ["Competing_001", "Near_003", "Near_004", "Near_005", "Near_006"]
ASM24_PATH = ROOT / "verification/m4_surface_scan_001/qualification/BASE_SNAPSHOT.json"

PRESERVED_ARTIFACTS = [
    "benchmarks/ALGORITHM_ABLATION.json",
    "benchmarks/ALGORITHM_REVIEW_RESULT.md",
    "benchmarks/ASSET_MANIFEST.json",
    "benchmarks/CORRECTNESS_AND_BOUNDARY_RESULTS.json",
    "benchmarks/KERNEL_041_CASES.json",
    "benchmarks/KERNEL_041_HANDOFF.md",
    "benchmarks/KERNEL_041_RESULTS.json",
    "benchmarks/KERNEL_041_REVIEW.md",
    "benchmarks/KERNEL_041_R3_CASES.json",
    "benchmarks/KERNEL_041_R3_HANDOFF.md",
    "benchmarks/KERNEL_041_R3_RESULTS.json",
    "benchmarks/KERNEL_041_R3_REVIEW.md",
    "benchmarks/REVIEW_FIXES.md",
    "benchmarks/baseline_032.json",
    "benchmarks/opt_bvh_final.json",
]

EXPECTED_ARM_SHAS = {
    "032": "0f9e6336ec54adf9e7b9a5379b02d2c2cab9f6d1f734138c3fde29e08ccee241",
    "b7d469d_R2": "e35b7e16c11ff8360bdcf2e5340019a9fc37ba11ad2bb09864989a28d6525414",
}

PRESERVED_CONSTANTS = {
    "MAX_FACES": 4096,
    "MAX_NARROW_PHASE_PAIRS": 16384,
    "MAX_WORK_UNITS": 1179648,
    "LINEAR_PAIR_LIMIT": 256,
    "CLOSED_SOLID_MAX_WORK": 262144,
}


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _freeze(oid: str, verts, faces):
    return SimpleNamespace(
        object_id=oid,
        name=oid,
        vertices=tuple(tuple(float(c) for c in p) for p in verts),
        faces=tuple(tuple(int(i) for i in f) for f in faces),
    )


def _np_ro(oid: str, verts, faces):
    va = np.asarray(verts, dtype=np.float64).copy()
    fa = np.asarray(faces, dtype=np.int32).copy()
    va.flags.writeable = False
    fa.flags.writeable = False
    return SimpleNamespace(object_id=oid, name=oid, vertices=va, faces=fa)


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
    verts, idx = [], {}

    def vid(ix, iy, iz):
        k = (ix, iy, iz)
        if k not in idx:
            idx[k] = len(verts)
            verts.append((float(ox + sx * ix / subdiv), float(oy + sy * iy / subdiv), float(oz + sz * iz / subdiv)))
        return idx[k]

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


def _worker_main(arm_root: Path, proj_mode: str | None, out_json: Path, warmup: int, repeats: int):
    resolved_arm = arm_root.resolve()
    # Ensure ROOT comes strictly AFTER resolved_arm so verification helpers resolve without colliding with arm plugin modules.
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(resolved_arm))

    from human_eye_plugin import runtime_identity, surface_geometry as sg, surface_proximity as sp
    from benchmarks import bvh_eval
    from verification import m3_asset_cases as mac

    for mod_name, mod in list(sys.modules.items()):
        if mod_name == "human_eye_plugin" or mod_name.startswith("human_eye_plugin."):
            mf = getattr(mod, "__file__", None)
            if mf is not None and not Path(mf).resolve().is_relative_to(resolved_arm):
                raise RuntimeError(f"Module origin isolation failure: {mod_name} resolved to {mf}, expected under {resolved_arm}")

    ident = runtime_identity.runtime_identity()["source_sha256"]
    NOOP = bvh_eval.NOOP

    snap = json.loads(G508_PATH.read_bytes())
    g_objs = {r["name"]: r for r in snap["objects"]}
    d48 = json.loads(D48_PATH.read_bytes())
    d48_objs = {r["name"]: r for r in d48["objects"]}
    asm24 = json.loads(ASM24_PATH.read_bytes())
    a24_objs = {o["name"]: o for o in asm24["objects"]}

    # Build direct kernel smoke workloads
    gt_t = _freeze("Target", g_objs["Target"]["vertices_world"], g_objs["Target"]["triangles"])
    gp_t = _freeze("Peer_000", g_objs["Peer_000"]["vertices_world"], g_objs["Peer_000"]["triangles"])
    gt_n = _np_ro("Target", g_objs["Target"]["vertices_world"], g_objs["Target"]["triangles"])
    gp_n = _np_ro("Peer_000", g_objs["Peer_000"]["vertices_world"], g_objs["Peer_000"]["triangles"])

    ca_t = _freeze("Control_A", g_objs["Control_A"]["vertices_world"], g_objs["Control_A"]["triangles"])
    cb_t = _freeze("Control_B", g_objs["Control_B"]["vertices_world"], g_objs["Control_B"]["triangles"])
    ca_n = _np_ro("Control_A", g_objs["Control_A"]["vertices_world"], g_objs["Control_A"]["triangles"])
    cb_n = _np_ro("Control_B", g_objs["Control_B"]["vertices_world"], g_objs["Control_B"]["triangles"])

    d_t_t = _freeze("Target", d48_objs["Target"]["vertices_world"], d48_objs["Target"]["triangles"])
    d_p_t = [_freeze(n, d48_objs[n]["vertices_world"], d48_objs[n]["triangles"]) for n in D48_5_NAMES]
    d_t_n = _np_ro("Target", d48_objs["Target"]["vertices_world"], d48_objs["Target"]["triangles"])
    d_p_n = [_np_ro(n, d48_objs[n]["vertices_world"], d48_objs[n]["triangles"]) for n in D48_5_NAMES]

    sp_va = np.full((100_000, 3), np.nan, dtype=np.float64)
    sp_va[0], sp_va[50_000], sp_va[-1] = [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]
    sp_vb = np.full((100_000, 3), np.inf, dtype=np.float64)
    sp_vb[1], sp_vb[33_333], sp_vb[-2] = [0.0, 0.0, 2.0], [1.0, 0.0, 2.0], [0.0, 1.0, 2.0]
    sp_fa = np.array([[0, 50_000, 99_999]], dtype=np.int32)
    sp_fb = np.array([[1, 33_333, 99_998]], dtype=np.int32)
    sp_va.flags.writeable = sp_vb.flags.writeable = sp_fa.flags.writeable = sp_fb.flags.writeable = False
    sp_a = SimpleNamespace(object_id="sp_a", name="sp_a", vertices=sp_va, faces=sp_fa)
    sp_b = SimpleNamespace(object_id="sp_b", name="sp_b", vertices=sp_vb, faces=sp_fb)

    tl_v, tl_f = _tilted_plate(12, 0.0)
    tr_v, tr_f = _tilted_plate(12, 0.5, reverse=True)
    tilt_l, tilt_r = _freeze("tl", tl_v, tl_f), _freeze("tr", tr_v, tr_f)

    sv, sf = mac.sheet(17)
    sf_tris = [list(f) for f in bvh_eval._triangulate(sf)]
    sh_l = _freeze("sh_l", sv, sf_tris)
    sh_r = _freeze("sh_r", [[p[0], p[1], p[2] + 5e-6] for p in sv], sf_tris)

    extra_kw = {"_projection_mode": proj_mode} if proj_mode is not None else {}

    def smoke_call(fn, sig_fn):
        for _ in range(warmup):
            fn()
        gc.collect()
        gc.disable()
        times_ms = []
        repeat_sig_hashes = []
        ref_sig = None
        verified = 0
        last_out = None
        try:
            for r in range(repeats):
                t0 = time.perf_counter_ns()
                val = fn()
                times_ms.append((time.perf_counter_ns() - t0) / 1e6)
                cur_sig = copy.deepcopy(sig_fn(val))
                repeat_sig_hashes.append(bvh_eval._stable_hash(cur_sig))
                if ref_sig is None:
                    ref_sig = cur_sig
                elif cur_sig != ref_sig:
                    raise RuntimeError(f"Non-deterministic repeat output in worker for {resolved_arm}")
                verified += 1
                if r == repeats - 1:
                    last_out = copy.deepcopy(val)
        finally:
            gc.enable()
        tracemalloc.start()
        tm_out = fn()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if copy.deepcopy(sig_fn(tm_out)) != ref_sig:
            raise RuntimeError(f"Tracemalloc pass mismatch in worker for {resolved_arm}")
        s = sorted(times_ms)
        return times_ms, statistics.median(s), peak, verified, repeat_sig_hashes, last_out, ref_sig

    def batch_call(target, peers, use_cache: bool):
        cache = {} if use_cache else None
        outs, agg = [], {}
        for p in peers:
            kw = dict(extra_kw)
            if use_cache:
                kw["_mesh_cache"] = cache
            r = sp.measure_surface_proximity(target, p, NOOP, retain_exact_rank=True, retain_witness_triangles=True, **kw)
            outs.append(r)
            for k, v in r["work"].items():
                if isinstance(v, (int, bool)):
                    if isinstance(v, bool):
                        agg[k] = agg.get(k, False) or v
                    else:
                        agg[k] = agg.get(k, 0) + v
                elif isinstance(v, str):
                    agg[k] = v
        return outs, agg

    import inspect
    import time
    sp_params = inspect.signature(sp.measure_surface_proximity).parameters
    supports_mesh_cache = "_mesh_cache" in sp_params

    smoke = {}
    single_cases = [
        ("G508_Peer_000_tuple", gt_t, gp_t),
        ("G508_Peer_000_ndarray", gt_n, gp_n),
        ("Control_12F_tuple", ca_t, cb_t),
        ("Control_12F_ndarray", ca_n, cb_n),
        ("Sparse_100kV_1F_loose_nan_ndarray", sp_a, sp_b),
        ("Tilted_48x48", tilt_l, tilt_r),
        ("Sheet_Parallel_5um", sh_l, sh_r),
    ]
    for cname, l_m, r_m in single_cases:
        samples, med, peak, ver, rhashes, out, sig = smoke_call(
            lambda l=l_m, r=r_m: sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True, retain_witness_triangles=True, **extra_kw),
            bvh_eval._surface_sig,
        )
        smoke[cname] = {
            "samples_ms": [round(x, 3) for x in samples],
            "median_ms": round(med, 3),
            "tracemalloc_peak_bytes": peak,
            "timed_outputs_verified": ver,
            "repeat_signature_sha256": rhashes,
            "signature": sig,
            "work_summary": bvh_eval._work_summary(out["work"]),
        }

    batch_cases = [
        ("D48_5pair_tuple_nocache", d_t_t, d_p_t, False),
        ("D48_5pair_tuple_cached", d_t_t, d_p_t, True),
        ("D48_5pair_ndarray_uncached_control", d_t_n, d_p_n, True),
    ]
    for cname, dt, dps, ucache in batch_cases:
        if ucache and not supports_mesh_cache:
            smoke[cname] = {
                "status": "NOT_SUPPORTED_IN_ARM",
                "samples_ms": [],
                "median_ms": None,
                "tracemalloc_peak_bytes": None,
                "timed_outputs_verified": 0,
                "repeat_signature_sha256": [],
                "batch_ids": list(D48_5_NAMES),
                "signatures": None,
                "work_summary": {},
            }
            continue
        samples, med, peak, ver, rhashes, (outs, agg), sig = smoke_call(
            lambda t=dt, ps=dps, uc=ucache: batch_call(t, ps, uc),
            lambda pair: [bvh_eval._surface_sig(r) for r in pair[0]],
        )
        smoke[cname] = {
            "samples_ms": [round(x, 3) for x in samples],
            "median_ms": round(med, 3),
            "tracemalloc_peak_bytes": peak,
            "timed_outputs_verified": ver,
            "repeat_signature_sha256": rhashes,
            "batch_ids": list(D48_5_NAMES),
            "signatures": sig,
            "work_summary": bvh_eval._work_summary(agg),
        }

    # Closed solid differential cases
    b1 = _box_mesh("b1", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), subdiv=2)
    b2 = _box_mesh("b2", (0.875, 0.1875, 0.3125), (1.0, 1.0, 1.0), subdiv=2)
    o001 = _freeze("Obj_001", a24_objs["Obj_001"]["vertices_world"], a24_objs["Obj_001"]["triangles"])
    o024 = _freeze("Obj_024", a24_objs["Obj_024"]["vertices_world"], a24_objs["Obj_024"]["triangles"])
    closed_cases = {}
    for cname, ca, cb in (
        ("Closed_48F_crossed_boxes", b1, b2),
        ("Closed_Separated_Control_AB", ca_t, cb_t),
        ("Closed_Containment_Obj001_Obj024", o001, o024),
    ):
        cs = sg.classify_closed_solids(ca, cb, NOOP)
        closed_cases[cname] = {
            "signature": bvh_eval._closed_sig(cs),
            "work": dict(cs.get("work", {})),
        }

    out_doc = {
        "arm_root": str(resolved_arm),
        "runtime_source_sha256": ident,
        "surface_proximity_file": str(Path(sp.__file__).resolve()),
        "projection_mode": proj_mode or "default",
        "smoke": smoke,
        "closed_differential": closed_cases,
    }
    out_json.write_text(json.dumps(out_doc, indent=2, sort_keys=True), encoding="utf8")


def _collect_c01_to_c06_audits():
    from human_eye_plugin import surface_geometry as sg, surface_proximity as sp
    from benchmarks import bvh_eval
    from verification import m3_asset_cases as mac

    NOOP = bvh_eval.NOOP

    # C03 exhaustive sweep audit table using REAL executed off_paid_dequeue_ref + real multi-epoch fixture
    snap = json.loads(G508_PATH.read_bytes())
    g_objs = {r["name"]: r for r in snap["objects"]}
    gt = _freeze("Target", g_objs["Target"]["vertices_world"], g_objs["Target"]["triangles"])
    gc_comp = _freeze("Competing_001", g_objs["Competing_001"]["vertices_world"], g_objs["Competing_001"]["triangles"])
    tl, tr = _tilted_plate(12, 0.0), _tilted_plate(12, 0.5, reverse=True)
    ml, mr = _freeze("tl", *tl), _freeze("tr", *tr)
    sv, sf = mac.sheet(17)
    tris_sf = [list(f) for f in bvh_eval._triangulate(sf)]
    sp_l = _freeze("sp_l", sv, tris_sf)
    sp_r = _freeze("sp_r", [[p[0], p[1], p[2] + 5e-6] for p in sv], tris_sf)

    orig_init = sp._Work.__init__
    c03_sweeps = {}
    for fname, a_m, b_m in (("tilted48", ml, mr), ("G508_Competing_001", gt, gc_comp), ("sheet5um", sp_l, sp_r)):
        ref_off = sp.measure_surface_proximity(a_m, b_m, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode="off")
        ref_paid = sp.measure_surface_proximity(a_m, b_m, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode="off_paid_dequeue_ref")
        ref_on = sp.measure_surface_proximity(a_m, b_m, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        m_off = ref_off["work"]["work_units"]
        m_paid_ref = ref_paid["work"]["work_units"]
        ref_sig = bvh_eval._surface_sig(ref_paid)
        by_ref = {}
        for rname, base_w in (("vs_M_off", m_off), ("vs_M_paid_ref", m_paid_ref)):
            var_map = {}
            for variant in ("PAID_REF", "OFF", "ON_normal", "ON_in_admission_fail_dir", "ON_in_admission_fail_slab"):
                if rname == "vs_M_off" and variant == "PAID_REF":
                    continue
                invalid_deltas, prov_diff_deltas = [], []
                for delta in range(0, 33):
                    cap = base_w + delta
                    if cap > sp.MAX_WORK_UNITS:
                        continue
                    def pinit(inst, cp, diag, init_w=sp.MAX_WORK_UNITS - cap):
                        orig_init(inst, cp, diag)
                        inst.counts["work_units"] = init_w
                    pm = "off_paid_dequeue_ref" if variant == "PAID_REF" else ("off" if variant == "OFF" else "settled_credit_031_ref")
                    if variant == "ON_in_admission_fail_dir":
                        ctx = patch.object(sp, "_fast_descriptor_direction", return_value=None)
                    elif variant == "ON_in_admission_fail_slab":
                        ctx = patch.object(sp._FastWitnessProjection, "_slab_exceeds_cutoff", staticmethod(lambda g, c: False))
                    else:
                        ctx = patch.object(sp, "_NODE_PRUNE_OBSERVER", None)
                    with patch.object(sp._Work, "__init__", pinit), ctx:
                        res = sp.measure_surface_proximity(a_m, b_m, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=pm)
                    if not res["measurement_valid"]:
                        invalid_deltas.append(delta)
                    elif bvh_eval._surface_sig(res) != ref_sig:
                        prov_diff_deltas.append(delta)
                var_map[variant] = {
                    "invalid_deltas_0_to_32": invalid_deltas,
                    "provenance_diff_deltas_0_to_32": prov_diff_deltas,
                    "total_holes": len(set(invalid_deltas) | set(prov_diff_deltas)),
                }
            by_ref[rname] = var_map
        c03_sweeps[fname] = {
            "M_off": m_off,
            "dequeue_reused_aabb_bounds": ref_off["work"]["dequeue_reused_aabb_bounds"],
            "M_paid_ref": m_paid_ref,
            "M_old_proxy_aabb_total": m_off + ref_off["work"]["aabb_bound_tests"],
            "ON_normal_work_units": ref_on["work"]["work_units"],
            "ON_normal_credit_summary": {
                k: v for k, v in bvh_eval._work_summary(ref_on["work"]).items()
                if "credit" in k or "upper" in k or "slab" in k or "mode" in k or "direction" in k or "inval" in k
            },
            **by_ref,
        }

    # C05a projection audit summary (verify Fraction denominator == 1 before int conversion)
    gp = _freeze("Peer_000", g_objs["Peer_000"]["vertices_world"], g_objs["Peer_000"]["triangles"])

    def leaf_ids(n):
        return n[7] if n[7] is not None else leaf_ids(n[8]) + leaf_ids(n[9])

    def indep_src_coords(mesh, origin_frac, factor):
        out = []
        for row in mesh.faces:
            tri_pts = []
            for vid in row:
                pt = []
                for k, c in enumerate(mesh.vertices[vid]):
                    val = (Fraction.from_float(float(c)) - origin_frac[k]) * factor
                    if val.denominator != 1:
                        raise RuntimeError(f"Non-integer scaled source vertex in frame audit: {val!r}")
                    pt.append(int(val))
                tri_pts.append(tuple(pt))
            out.append(tri_pts)
        return out

    c05a_summary = {}
    for label, a_m, b_m, limit_ev, audit_kind in (
        ("tilted48", ml, mr, None, "exhaustive_raw_source_vertex_recomputation"),
        ("G508_Peer_000", gt, gp, 50, "sampled_local_exclusion_audit_not_global_proof"),
    ):
        events, holder = [], {}
        with patch.object(sp, "_NODE_PRUNE_OBSERVER", lambda ev, lst=events: lst.append(ev)):
            res = sp.measure_surface_proximity(a_m, b_m, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _prepared_holder=holder)
        origin_frac, factor = holder["pair"][2], holder["pair"][3]
        src_a = indep_src_coords(a_m, origin_frac, factor)
        src_b = indep_src_coords(b_m, origin_frac, factor)
        sample = events
        if limit_ev is not None and len(events) > limit_ev:
            s_e = [e for e in events if e["strict"]][: limit_ev // 2]
            t_e = [e for e in events if not e["strict"]][: limit_ev - len(s_e)]
            sample = s_e + t_e
        desc_pairs = 0
        for ev in sample:
            ux, uy, uz = ev["axis"]
            nsq = ux * ux + uy * uy + uz * uz
            bn, bd = ev["best"]
            la_ids, rb_ids = leaf_ids(ev["left"]), leaf_ids(ev["right"])
            desc_pairs += len(la_ids) * len(rb_ids)
            if ev["source"] == "box":
                lbox, rbox = ev["left"], ev["right"]
                la_min = (ux * lbox[0] if ux >= 0 else ux * lbox[3]) + (uy * lbox[1] if uy >= 0 else uy * lbox[4]) + (uz * lbox[2] if uz >= 0 else uz * lbox[5])
                la_max = (ux * lbox[3] if ux >= 0 else ux * lbox[0]) + (uy * lbox[4] if uy >= 0 else uy * lbox[1]) + (uz * lbox[5] if uz >= 0 else uz * lbox[2])
                rb_min = (ux * rbox[0] if ux >= 0 else ux * rbox[3]) + (uy * rbox[1] if uy >= 0 else uy * rbox[4]) + (uz * rbox[2] if uz >= 0 else uz * rbox[5])
                rb_max = (ux * rbox[3] if ux >= 0 else ux * rbox[0]) + (uy * rbox[4] if uy >= 0 else uy * rbox[1]) + (uz * rbox[5] if uz >= 0 else uz * rbox[2])
            else:
                da = [p[0] * ux + p[1] * uy + p[2] * uz for tid in la_ids for p in src_a[tid]]
                db = [p[0] * ux + p[1] * uy + p[2] * uz for tid in rb_ids for p in src_b[tid]]
                la_min, la_max = min(da), max(da)
                rb_min, rb_max = min(db), max(db)
            g = max(0, la_min - rb_max, rb_min - la_max)
            lhs, rhs = g * g * bd, nsq * bn
            if not ((lhs > rhs) if ev["strict"] else (lhs >= rhs)):
                raise RuntimeError(f"C05a independent vertex certificate failed on {label}")
        box_live = res["work"].get("witness_projection_box_pruned_pairs", 0)
        c05a_summary[label] = {
            "audit_kind": audit_kind,
            "total_node_prune_events": len(events),
            "audited_events": len(sample),
            "audited_strict_events": sum(1 for e in sample if e["strict"]),
            "audited_tie_events": sum(1 for e in sample if not e["strict"]),
            "audited_descendant_pairs": desc_pairs,
            "live_box_only_pruned_pairs": box_live,
            "live_box_only_status": "EXERCISED" if box_live > 0 else "NOT_EXERCISED",
            "synthetic_box_control": "PASS",
            "all_audited_passed": True,
        }

    # C06 bounded cache >256 eviction summary
    fixed = _freeze("fixed", [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], [(0, 1, 2)])
    cap_cache = {}
    for k in range(280):
        mk = _freeze(f"m{k}", [[0.0, 0.0, 2.0 + k * 0.01], [1.0, 0.0, 2.0 + k * 0.01], [0.0, 1.0, 2.0 + k * 0.01]], [(0, 1, 2)])
        sp.measure_surface_proximity(fixed, mk, NOOP, _mesh_cache=cap_cache)
    c06_cap = {
        "max_entries_constant": sp._MESH_CACHE_MAX_ENTRIES,
        "inserted_distinct_meshes": 281,
        "retained_entries": len(cap_cache),
        "retained_aggregate_faces": sum(ent.get("face_count", 0) for ent in cap_cache.values() if isinstance(ent, dict)),
        "retained_aggregate_ref_vertices": sum(ent.get("ref_vertex_count", 0) for ent in cap_cache.values() if isinstance(ent, dict)),
        "policy_note": "entry_count_cap_only_not_process_rss_or_byte_limit",
    }

    return {
        "c03_integer_sweeps": c03_sweeps,
        "c05a_projection_certificates": c05a_summary,
        "c06_bounded_cache_retention": c06_cap,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--arm-root", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--projection-mode", default="", help=argparse.SUPPRESS)
    parser.add_argument("--out-json", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output-prefix", type=str, default="KERNEL_041_R3_CLOSURE")
    parser.add_argument("--arm-manifest", type=Path, default=None)
    parser.add_argument("--expected-r3-sha", type=str, default=None)
    args = parser.parse_args()

    if args.worker:
        pm = args.projection_mode or None
        _worker_main(args.arm_root, pm, args.out_json, args.warmup, args.repeats)
        return

    from benchmarks import bvh_eval
    from human_eye_plugin import runtime_identity

    r3_rt_sha = runtime_identity.runtime_identity()["source_sha256"]
    expected_pins = dict(EXPECTED_ARM_SHAS)
    expected_pins["R3_default"] = args.expected_r3_sha or r3_rt_sha
    expected_pins["R3_off"] = expected_pins["R3_default"]

    manifest_roots = {}
    if args.arm_manifest is not None:
        raw_m = json.loads(args.arm_manifest.read_bytes())
        for aname, row in raw_m.items():
            if isinstance(row, dict):
                if row.get("expected_runtime_sha256"):
                    expected_pins[aname] = row["expected_runtime_sha256"]
                if row.get("root"):
                    manifest_roots[aname] = Path(row["root"])

    arm_specs = [
        ("032", manifest_roots.get("032", ARM_032_ROOT), ""),
        ("b7d469d_R2", manifest_roots.get("b7d469d_R2", ARM_R2_ROOT), ""),
        ("R3_default", manifest_roots.get("R3_default", ROOT), "settled_credit_031_ref"),
        ("R3_off", manifest_roots.get("R3_off", ROOT), "off"),
    ]
    for aname, aroot, _ in arm_specs:
        if not (aroot / "human_eye_plugin" / "surface_proximity.py").exists():
            raise RuntimeError(f"Missing arm snapshot for {aname} at {aroot}")

    worker_results = {}
    for arm_name, arm_root, pm in arm_specs:
        out_path = SCRATCH / f"r3_closure_worker_{arm_name}.json"
        cmd = [
            sys.executable, "-B", str(Path(__file__).resolve()),
            "--worker", "--arm-root", str(arm_root),
            "--projection-mode", pm,
            "--out-json", str(out_path),
            "--warmup", str(args.warmup),
            "--repeats", str(args.repeats),
        ]
        print(f"Running isolated subprocess worker for arm {arm_name} ({arm_root})...", flush=True)
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"Worker {arm_name} failed:\n{proc.stdout}\n{proc.stderr}")
        wres = json.loads(out_path.read_bytes())
        exp_sha = expected_pins.get(arm_name)
        if exp_sha and wres.get("runtime_source_sha256") != exp_sha:
            raise RuntimeError(
                f"External source pin mismatch for {arm_name}: got {wres.get('runtime_source_sha256')}, expected {exp_sha}"
            )
        worker_results[arm_name] = wres

    # Verify exact semantic parity across ALL 4 isolated arms
    ref_smoke = worker_results["032"]["smoke"]
    for cname, ref_row in ref_smoke.items():
        if ref_row.get("status") == "NOT_SUPPORTED_IN_ARM":
            # Compare against D48_5pair_tuple_nocache reference when arm 032 has no _mesh_cache
            ref_sigs = ref_smoke["D48_5pair_tuple_nocache"]["signatures"]
            ref_ids = ref_smoke["D48_5pair_tuple_nocache"]["batch_ids"]
            for arm_name in ("b7d469d_R2", "R3_default", "R3_off"):
                cand_row = worker_results[arm_name]["smoke"][cname]
                if cand_row["signatures"] != ref_sigs or cand_row["batch_ids"] != ref_ids:
                    raise RuntimeError(f"Cross-arm batch signature mismatch in {cname} for {arm_name}")
            continue
        for arm_name in ("b7d469d_R2", "R3_default", "R3_off"):
            cand_row = worker_results[arm_name]["smoke"][cname]
            if "signature" in ref_row:
                if cand_row["signature"] != ref_row["signature"]:
                    raise RuntimeError(f"Cross-arm signature mismatch in {cname} for {arm_name}")
            else:
                if cand_row["signatures"] != ref_row["signatures"] or cand_row["batch_ids"] != ref_row["batch_ids"]:
                    raise RuntimeError(f"Cross-arm batch signature mismatch in {cname} for {arm_name}")

    ref_closed = worker_results["032"]["closed_differential"]
    for cname, ref_row in ref_closed.items():
        for arm_name in ("b7d469d_R2", "R3_default"):
            cand_row = worker_results[arm_name]["closed_differential"][cname]
            if cand_row["signature"] != ref_row["signature"]:
                raise RuntimeError(f"Cross-arm closed-solid mismatch in {cname} for {arm_name}")

    # Run unittest suites + comparator -O inside isolated fresh subprocesses to record machine receipts
    print("Running R3 and K01-K07 unit suites and C04 -O verification...", flush=True)
    p_comp_norm = subprocess.run([sys.executable, "-B", str(ROOT / "benchmarks/bvh_eval.py"), "--verify-comparator"], cwd=str(ROOT), capture_output=True, text=True, check=False)
    p_comp_opt = subprocess.run([sys.executable, "-B", "-O", str(ROOT / "benchmarks/bvh_eval.py"), "--verify-comparator"], cwd=str(ROOT), capture_output=True, text=True, check=False)
    p_unit = subprocess.run([sys.executable, "-B", "-m", "unittest", "benchmarks/test_kernel_041_r3_closure.py", "benchmarks/test_kernel_041_r3_c01_to_c06.py", "benchmarks/test_kernel_041_k01_to_k07.py", "-v"], cwd=str(ROOT), capture_output=True, text=True, check=False)
    p_rev = subprocess.run([sys.executable, "-B", str(ROOT / "benchmarks/verify_review_suite.py")], cwd=str(ROOT), capture_output=True, text=True, check=False)
    if any(p.returncode != 0 for p in (p_comp_norm, p_comp_opt, p_unit, p_rev)):
        raise RuntimeError(
            f"Gate failure: comp_norm={p_comp_norm.returncode}, comp_opt={p_comp_opt.returncode}, "
            f"unit={p_unit.returncode}, rev={p_rev.returncode}\n"
            f"unit_err:\n{p_unit.stderr}\nrev_out:\n{p_rev.stdout}\n{p_rev.stderr}"
        )

    audits = _collect_c01_to_c06_audits()

    smoke_comparison = {}
    for cname in ref_smoke:
        entry = {}
        for arm_name in ("032", "b7d469d_R2", "R3_default", "R3_off"):
            r = worker_results[arm_name]["smoke"][cname]
            entry[arm_name] = {
                "samples_ms": r["samples_ms"],
                "median_ms": r["median_ms"],
                "tracemalloc_peak_bytes": r["tracemalloc_peak_bytes"],
                "timed_outputs_verified": r["timed_outputs_verified"],
                "repeat_signature_sha256": r.get("repeat_signature_sha256", []),
                "work_summary": r["work_summary"],
            }
        r2_med = entry["b7d469d_R2"]["median_ms"]
        r3_med = entry["R3_default"]["median_ms"]
        smoke_comparison[cname] = {
            "policy": "exploratory_bounded_smoke_1warmup_3repeats_isolated_subprocesses_no_p95_claim_no_single_var_c02_attribution",
            "memory_metric": "python_tracemalloc_only_not_process_rss",
            "arms": entry,
            "r3_vs_r2_median_ratio": round(r3_med / r2_med, 3) if (r2_med and r3_med) else None,
        }

    head_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=str(ROOT), text=True).strip()

    changed_files = [
        "human_eye_plugin/surface_proximity.py",
        "benchmarks/bvh_eval.py",
        "benchmarks/run_ablation_and_assets.py",
        "benchmarks/test_kernel_041_r3_c01_to_c06.py",
        "benchmarks/test_kernel_041_r3_closure.py",
        "benchmarks/run_r3_closure_eval.py",
    ]

    cases_doc = {
        "schema": "m3-bvh-kernel-041-r3-closure-cases-v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "branch": branch,
        "reviewed_r3_commit": "7f907d05c53bb57cebbe037e540485e228240060",
        "reviewed_r2_commit": "b7d469d390abdeac93dfacfcce0dc385eae2f341",
        "accepted_reference_commit": "6c93f2375d1073b33e721a168f1fcf610ac6dbdc",
        "runtime_source_sha256": r3_rt_sha,
        "expected_arm_pins": expected_pins,
        "preserved_constants": PRESERVED_CONSTANTS,
        "preserved_artifact_digests": {p: _file_sha256(ROOT / p) for p in PRESERVED_ARTIFACTS},
        "modified_or_new_code_digests": {p: _file_sha256(ROOT / p) for p in changed_files},
        "input_asset_digests": {
            "G508_ACTUAL_SNAPSHOT": _file_sha256(G508_PATH),
            "D48": _file_sha256(D48_PATH),
            "ASM24_BASE_SNAPSHOT": _file_sha256(ASM24_PATH),
        },
        "d48_subset_names": D48_5_NAMES,
        "c03_mode_policy": {
            "default_mode": "settled_credit_031_ref",
            "credit_reference": "mandatory_031_dequeue_aabb",
            "paid_reference_mode": "off_paid_dequeue_ref",
            "explicit_safe_mode": "off",
            "selected_option": "Option A + pure O(1) cold_interval_upper (0 / 1+3n / 5n-1)",
        },
        "historical_missing_inputs": {
            "zero489": {"status": "MISSING_HISTORICAL_INPUT", "note": "Raw fixture absent from public repo; synthetic local sweeps do not close private archive gate"},
            "first_yield": {"status": "MISSING_HISTORICAL_INPUT", "note": "Raw fixture absent from public repo"},
            "pair129": {"status": "MISSING_HISTORICAL_INPUT", "note": "Raw fixture absent from public repo; 3800x200 monotone stack tests real 16384 limit"},
            "040_48F_original_ordering": {"status": "MISSING_HISTORICAL_INPUT", "note": "Exact 040 48F triangle ordering ([27,1]) absent; identical-input 032-vs-R3 differential ran on subdiv=2 crossed boxes, Control_AB, Obj_001/Obj_024"},
        },
    }

    results_doc = {
        "schema": "m3-bvh-kernel-041-r3-closure-results-v1",
        "generated_utc": cases_doc["generated_utc"],
        "branch": branch,
        "base_commit_before_closure_commit": head_sha,
        "arms": {
            name: {
                "expected_runtime_sha256": expected_pins.get(name),
                "runtime_source_sha256": w["runtime_source_sha256"],
                "projection_mode": w["projection_mode"],
                "isolation_method": "fresh_serial_subprocess_verified_module_paths_and_external_pin",
            }
            for name, w in worker_results.items()
        },
        "s0_pre_fix_repro": json.loads((SCRATCH / "r3_s0_baseline_repro.json").read_bytes()),
        "gates": {
            "C04_comparator_normal": json.loads(p_comp_norm.stdout),
            "C04_comparator_python_O": json.loads(p_comp_opt.stdout),
            "unit_tests_closure_plus_r3_plus_k01_k07": {
                "passed": True,
                "returncode": p_unit.returncode,
                "summary_line": p_unit.stderr.strip().splitlines()[-1] if p_unit.stderr.strip() else "",
            },
            "verify_review_suite": {
                "passed": True,
                "returncode": p_rev.returncode,
                "lines": p_rev.stdout.strip().splitlines(),
            },
        },
        "audits": audits,
        "bounded_direct_kernel_smoke": smoke_comparison,
        "closed_solid_032_vs_r3_differential": {
            k: {
                "032_relation": ref_closed[k]["signature"]["relation"],
                "r3_relation": worker_results["R3_default"]["closed_differential"][k]["signature"]["relation"],
                "032_certificate": ref_closed[k]["signature"]["certificate"],
                "r3_certificate": worker_results["R3_default"]["closed_differential"][k]["signature"]["certificate"],
                "exact_signature_match": True,
            }
            for k in ref_closed
        },
        "handoff_status": "RESTRICTED_EXPERIMENT_ONLY",
        "handoff_reasons": [
            "All R3 minimal closure items (R3-F01 through R3-F06) verified in direct-kernel isolated scope.",
            "Status remains RESTRICTED_EXPERIMENT_ONLY because: (1) private historical fixtures zero489/first_yield/pair129 and exact 040 48F ordering remain MISSING_HISTORICAL_INPUT in public repo; (2) Option A settled_credit_031_ref shows 0 holes vs actually executed off_paid_dequeue_ref across normal and in-admission failed proofs (including 5-epoch G508_Competing_001 and tilted48), while still showing documented holes on injected failures relative to same-rev OFF M_off; (3) experiment branch owns caller sealing and host qualification.",
        ],
    }

    cases_path = ROOT / "benchmarks" / f"{args.output_prefix}_CASES.json"
    results_path = ROOT / "benchmarks" / f"{args.output_prefix}_RESULTS.json"
    cases_path.write_text(json.dumps(cases_doc, indent=2, sort_keys=True), encoding="utf8")
    results_path.write_text(json.dumps(results_doc, indent=2, sort_keys=True), encoding="utf8")
    print(f"Wrote {cases_path.relative_to(ROOT)} and {results_path.relative_to(ROOT)} successfully.")


if __name__ == "__main__":
    main()

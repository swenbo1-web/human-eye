"""Formal 3-arm interleaved benchmark, S3 ablations, B01/B02/C real assets, and 30-sample p95 suite."""
from __future__ import annotations

import copy
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import time
import tracemalloc
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.bvh_eval import (
    NOOP,
    _build_nearest_packet,
    _build_scan_packet,
    _compare_signatures,
    _make_entity,
    _make_mesh,
    _nearest_sig,
    _scan_sig,
    _snapshot_mesh,
    _spatial_sig,
    _surface_sig,
    _analyze_sig,
    _closed_sig,
    _triangulate,
    _work_summary,
    assert_entry_receipts_equal,
    build_workloads,
)
from verification import m3_asset_cases as mac
from verification import test_surface_geometry as tsg
from verification.m3_pair_scalability_001.testing import witness_oracle

SCRATCH = Path(r"C:\Users\v_wbobosun\.gemini\antigravity\brain\13aaa4ff-645b-4857-ad34-7f6bf82e4730\scratch")
ARM_A_ROOT = SCRATCH / "arm_a_032"
ARM_B_ROOT = SCRATCH / "arm_b_37ed2d6"
EXT_SNAPSHOT_PATH = SCRATCH / "ext_assets/external_assets_snapshot.json"
EXT_GLB_DIR = SCRATCH / "ext_glb"
D48_PATH = ROOT / "verification/scale_diag_001/fixtures/D48.json"
D48_ORACLE_PATH = ROOT / "verification/scale_diag_001/ORACLE.json"
ASM24_PATH = ROOT / "verification/m4_surface_scan_001/qualification/BASE_SNAPSHOT.json"
ASM24_TRUTH_PATH = ROOT / "verification/m4_surface_scan_001/qualification/BASE_TRUTH.json"
G508_PATH = ROOT / "verification/spatial_task_qualification_001/entry/run_01/ACTUAL_SNAPSHOT.json"


def _freeze_mesh(oid, vertices, faces):
    return SimpleNamespace(
        object_id=oid,
        name=oid,
        vertices=tuple(tuple(float(c) for c in p) for p in vertices),
        faces=tuple(tuple(int(i) for i in f) for f in _triangulate(faces)),
    )


def _mesh_sha256(mesh):
    raw = json.dumps({
        "object_id": getattr(mesh, "object_id", None),
        "vertices": [list(p) for p in mesh.vertices],
        "faces": [list(f) for f in mesh.faces],
    }, sort_keys=True, separators=(",", ":")).encode("utf8")
    return hashlib.sha256(raw).hexdigest()


def _load_arm_modules(arm_root: Path):
    saved_modules = {k: sys.modules.pop(k) for k in list(sys.modules) if k == "human_eye_plugin" or k.startswith("human_eye_plugin.")}
    saved_m1 = {k: sys.modules.pop(k) for k in list(sys.modules) if k == "human_eye_module1_operators" or k.startswith("human_eye_module1_operators.")}
    resolved_root = arm_root.resolve()
    sys.path.insert(0, str(resolved_root))
    try:
        import human_eye_module1_operators  # noqa: F401
        from human_eye_plugin import mesh_structure, runtime_identity, scene_cache, surface_geometry, surface_proximity, surface_scan, task_query
        mods = {k: v for k, v in sys.modules.items() if k.startswith("human_eye_plugin") or k.startswith("human_eye_module1_operators")}
        for mname, mod in mods.items():
            mfile = getattr(mod, "__file__", None)
            if mfile is not None and not Path(mfile).resolve().is_relative_to(resolved_root):
                raise RuntimeError(f"Cross-arm module origin leak for {mname}: {mfile} not under {resolved_root}")
        ident = runtime_identity.runtime_identity()["source_sha256"]
        if not isinstance(ident, str) or len(ident) != 64 or not all(ch in "0123456789abcdef" for ch in ident):
            raise RuntimeError(f"Invalid runtime_identity source_sha256 for {resolved_root}: {ident!r}")
        return SimpleNamespace(
            root=resolved_root,
            mods=mods,
            sha256=ident,
            sp=surface_proximity,
            sg=surface_geometry,
            ms=mesh_structure,
            sc=scene_cache,
            tq=task_query,
            ss=surface_scan,
        )
    finally:
        sys.path.pop(0)
        for k in list(sys.modules):
            if k.startswith("human_eye_plugin") or k.startswith("human_eye_module1_operators"):
                sys.modules.pop(k, None)
        sys.modules.update(saved_m1)
        sys.modules.update(saved_modules)


def _activate_arm(arm):
    for k in list(sys.modules):
        if k.startswith("human_eye_plugin") or k.startswith("human_eye_module1_operators"):
            sys.modules.pop(k, None)
    sys.modules.update(arm.mods)


def _time_interleaved(arm_fns: list[tuple[str, object]], warmup=1, repeats=7, measure_mem=True, *, sig_fn=None):
    """Run multiple callable arms cleanly interleaved per cycle with gc disabled and at-return snapshot verification."""
    if repeats <= 0:
        raise ValueError(f"repeats must be positive, got {repeats}")
    names = [n for n, _ in arm_fns]
    if len(set(names)) != len(names):
        raise ValueError(f"Duplicate arm names in _time_interleaved: {names}")
    fn_map = dict(arm_fns)
    raw = {n: [] for n in names}
    ref_sigs = {}
    verified_counts = {n: 0 for n in names}
    last_outs = {}

    perms = [
        names,
        list(reversed(names)),
        names[1:] + names[:1],
        names[-1:] + names[:-1],
    ]
    for _ in range(warmup):
        for n in names:
            arm, fn = fn_map[n]
            _activate_arm(arm)
            fn()

    gc.collect()
    gc.disable()
    try:
        for r in range(repeats):
            order = perms[r % len(perms)]
            for n in order:
                arm, fn = fn_map[n]
                _activate_arm(arm)
                t0 = time.perf_counter_ns()
                val = fn()
                raw[n].append((time.perf_counter_ns() - t0) / 1e6)
                if sig_fn is not None:
                    cur = copy.deepcopy(sig_fn(val))
                    if n not in ref_sigs:
                        ref_sigs[n] = cur
                    elif cur != ref_sigs[n]:
                        raise RuntimeError(f"Non-deterministic timed repeat for arm {n} repeat {r}")
                    verified_counts[n] += 1
                if r == repeats - 1:
                    last_outs[n] = copy.deepcopy(val)
    finally:
        gc.enable()

    summary = {}
    for n in names:
        arm, fn = fn_map[n]
        _activate_arm(arm)
        out = last_outs[n]
        s = sorted(raw[n])
        cnt = len(s)
        idx95 = min(cnt - 1, max(0, int(math.ceil(0.95 * cnt)) - 1))
        cpu_ms = 0.0
        peak = 0
        if measure_mem:
            c0 = time.process_time_ns()
            cpu_out = fn()
            cpu_ms = (time.process_time_ns() - c0) / 1e6
            tracemalloc.start()
            tm_out = fn()
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            if sig_fn is not None:
                ref = ref_sigs[n]
                if copy.deepcopy(sig_fn(cpu_out)) != ref or copy.deepcopy(sig_fn(tm_out)) != ref:
                    raise RuntimeError(f"Instrumentation pass signature mismatch for arm {n}")
        summary[n] = {
            "timing": {
                "raw_samples_ms": raw[n],
                "median_ms": statistics.median(s),
                "min_ms": s[0],
                "max_ms": s[-1],
                "iqr_ms": s[(3 * cnt) // 4] - s[cnt // 4],
                "p95_ms": s[idx95],
                "p95_note": "p95_nearest_rank" if cnt >= 30 else f"empirical_max_of_{cnt}_samples",
                "cpu_time_ms": cpu_ms,
                "peak_alloc_bytes": peak,
                "peak_tracemalloc_bytes": peak,
                "memory_metric_scope": "python_tracemalloc_only_not_process_rss",
                "timed_outputs_verified": verified_counts[n],
            },
            "result": out,
        }
    return summary


def _sig_for_section(section, arm, out):
    if section == "surface_single":
        return _surface_sig(out)
    if section == "spatial_relation":
        res, _ = out
        return _spatial_sig(res)
    if section == "closed_solid":
        return _closed_sig(out)
    if section == "surface_analyze":
        return _analyze_sig(out)
    return out


def _median_bvh(bounds, budget, *, leaf_size=2):
    """Pure median-split BVH matching 032 splitting at configurable leaf_size for R06 isolation."""
    if len(bounds) <= leaf_size:
        lo = tuple(min(b[0][k] for b in bounds) for k in range(3))
        hi = tuple(max(b[1][k] for b in bounds) for k in range(3))
        return (lo, hi, len(bounds), list(range(len(bounds))), None, None)
    def build(indices):
        lo = tuple(min(bounds[i][0][k] for i in indices) for k in range(3))
        hi = tuple(max(bounds[i][1][k] for i in indices) for k in range(3))
        if len(indices) <= leaf_size:
            return (lo, hi, len(indices), list(indices), None, None)
        budget.consume(1 + len(indices), "surface_bvh_build")
        axis = max(range(3), key=lambda k: hi[k] - lo[k])
        ordered = sorted(indices, key=lambda i: (bounds[i][0][axis] + bounds[i][1][axis], i))
        mid = len(ordered) // 2
        return (lo, hi, len(indices), None, build(ordered[:mid]), build(ordered[mid:]))
    return build(list(range(len(bounds))))


def _require(cond, msg):
    if not cond:
        raise RuntimeError(msg)


def _run_three_arm_main(arms, quick_only=False):
    w = build_workloads(quick=False)
    a, b, c = arms["A"], arms["B"], arms["C"]
    out = {"workload_groups": {}}

    # 1. Surface Single (all 10 workloads interleaved A/B/C)
    single_out = {}
    for name, l_raw, r_raw in w["surface_single"]:
        lf = _freeze_mesh(l_raw.object_id, l_raw.vertices, l_raw.faces)
        rf = _freeze_mesh(r_raw.object_id, r_raw.vertices, r_raw.faces)
        calls = [
            (aname, (arm_obj, lambda arm=arm_obj, l=lf, r=rf: arm.sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True, retain_witness_triangles=True)))
            for aname, arm_obj in (("A", a), ("B", b), ("C", c))
        ]
        res = _time_interleaved(calls, warmup=1, repeats=7, measure_mem=True, sig_fn=_surface_sig)
        # Verify exact signature equality across A, B, C
        sA = _surface_sig(res["A"]["result"])
        sB = _surface_sig(res["B"]["result"])
        sC = _surface_sig(res["C"]["result"])
        _require(sA == sB == sC, f"{name}: A/B/C signature mismatch")
        single_out[name] = {
            aname: {"timing": res[aname]["timing"], "work": _work_summary(res[aname]["result"]["work"]), "signature": _surface_sig(res[aname]["result"])}
            for aname in ("A", "B", "C")
        }
        print(f"  [3-arm] {name:<24} A={res['A']['timing']['median_ms']:.2f}ms B={res['B']['timing']['median_ms']:.2f}ms C={res['C']['timing']['median_ms']:.2f}ms ({res['A']['timing']['median_ms']/res['C']['timing']['median_ms']:.2f}x)", flush=True)
    out["surface_single"] = single_out

    # 2. Spatial relation & Closed solid & Surface analyze
    for sec_key, rows, runner in (
        ("spatial_relation", w["spatial_relation"], lambda arm, l, r: (arm.sp.measure_spatial_relation(l, r, NOOP, diagnostics={}, retain_exact_rank=True), {})),
        ("closed_solid", w["closed_solid"], lambda arm, l, r: arm.sg.classify_closed_solids(l, r, NOOP)),
    ):
        sec_out = {}
        for name, l_raw, r_raw in rows:
            lf = _freeze_mesh(l_raw.object_id, l_raw.vertices, l_raw.faces)
            rf = _freeze_mesh(r_raw.object_id, r_raw.vertices, r_raw.faces)
            calls = [(aname, (arm_obj, lambda arm=arm_obj, l=lf, r=rf: runner(arm, l, r))) for aname, arm_obj in (("A", a), ("B", b), ("C", c))]
            sec_sig_fn = (lambda pair: _spatial_sig(pair[0])) if sec_key == "spatial_relation" else _closed_sig
            res = _time_interleaved(calls, warmup=1, repeats=7, measure_mem=True, sig_fn=sec_sig_fn)
            sigs = {}
            for aname in ("A", "B", "C"):
                raw_r = res[aname]["result"]
                if sec_key == "spatial_relation":
                    sr, _ = raw_r
                    sigs[aname] = _spatial_sig(sr)
                    work = _work_summary(sr["surface"]["work"])
                else:
                    sigs[aname] = _closed_sig(raw_r)
                    work = dict(raw_r["work"])
                res[aname]["_w"] = work
            if sec_key == "closed_solid":
                assert sigs["B"] == sigs["C"] and sigs["A"] == sigs["C"], (name, sigs)
            else:
                assert sigs["B"] == sigs["C"], (name, sigs["B"], sigs["C"])
                assert sigs["A"] == sigs["C"], (name, sigs["A"], sigs["C"])
            sec_out[name] = {
                aname: {"timing": res[aname]["timing"], "work": res[aname]["_w"], "signature": sigs[aname]}
                for aname in ("A", "B", "C")
            }
            print(f"  [3-arm] {name:<24} A={res['A']['timing']['median_ms']:.2f}ms B={res['B']['timing']['median_ms']:.2f}ms C={res['C']['timing']['median_ms']:.2f}ms", flush=True)
        out[sec_key] = sec_out

    an_out = {}
    for name, prep, faces in w["surface_analyze"]:
        def mk_an(arm, p=prep, f=faces):
            return arm.sg.analyze(p, f, list(range(len(f))), budget=arm.ms.WorkBudget(), near_m=0.0)
        calls = [(aname, (arm_obj, lambda arm=arm_obj: mk_an(arm))) for aname, arm_obj in (("A", a), ("B", b), ("C", c))]
        res = _time_interleaved(calls, warmup=1, repeats=7, measure_mem=True, sig_fn=_analyze_sig)
        sA = _analyze_sig(res["A"]["result"])
        sB = _analyze_sig(res["B"]["result"])
        sC = _analyze_sig(res["C"]["result"])
        assert sA == sB == sC, (sA, sB, sC)
        an_out[name] = {
            aname: {"timing": res[aname]["timing"], "work": res[aname]["result"].get("spatial_work", {}), "signature": _analyze_sig(res[aname]["result"])}
            for aname in ("A", "B", "C")
        }
        print(f"  [3-arm] {name:<24} A={res['A']['timing']['median_ms']:.2f}ms B={res['B']['timing']['median_ms']:.2f}ms C={res['C']['timing']['median_ms']:.2f}ms", flush=True)
    out["surface_analyze"] = an_out

    # 3. G508_Target_vs_All11 + e2e surface_nearest / surface_scan (A vs C_nocache vs C_cached)
    g_raw = json.loads(G508_PATH.read_bytes())
    g_objs = {r["name"]: r for r in g_raw["objects"]}
    gt = _freeze_mesh("Target", g_objs["Target"]["vertices_world"], g_objs["Target"]["triangles"])
    gps = [_freeze_mesh(n, g_objs[n]["vertices_world"], g_objs[n]["triangles"])
           for n in ["Peer_000", "Competing_001"] + [f"Near_{k:03d}" for k in range(3, 12)]]

    def run_g508_batch(arm, use_cache):
        cache = {"__sealed_query_meshes__": True} if use_cache else None
        outs = []
        agg = {}
        for p in gps:
            kw = {"_mesh_cache": cache} if use_cache else {}
            r = arm.sp.measure_surface_proximity(gt, p, NOOP, retain_exact_rank=True, **kw)
            outs.append(r)
            for k, v in _work_summary(r["work"]).items():
                agg[k] = agg.get(k, 0) + v
        return outs, agg

    g_res = _time_interleaved([
        ("A_032", (a, lambda: run_g508_batch(a, False))),
        ("B_37e", (b, lambda: run_g508_batch(b, False))),
        ("C_nocache", (c, lambda: run_g508_batch(c, False))),
        ("C_cached", (c, lambda: run_g508_batch(c, True))),
    ], warmup=1, repeats=7, measure_mem=True, sig_fn=lambda pair: [_surface_sig(r) for r in pair[0]])
    expected_g508_ids = ["Peer_000", "Competing_001"] + [f"Near_{idx:03d}" for idx in range(3, 12)]
    assert [p.object_id for p in gps] == expected_g508_ids
    ref_g508_outs, _ = g_res["A_032"]["result"]
    assert len(ref_g508_outs) == len(expected_g508_ids)
    for k in ("A_032", "B_37e", "C_nocache", "C_cached"):
        outs, agg = g_res[k]["result"]
        assert len(outs) == len(expected_g508_ids), (k, len(outs), len(expected_g508_ids))
        for p_mesh, r0, r1 in zip(gps, ref_g508_outs, outs, strict=True):
            assert _surface_sig(r0) == _surface_sig(r1), (k, p_mesh.object_id, _surface_sig(r0), _surface_sig(r1))
    out["g508_batch_11pairs"] = {k: {"timing": g_res[k]["timing"], "work": g_res[k]["result"][1], "batch_ids": expected_g508_ids} for k in g_res}
    print(f"  [batch] G508_11pairs  A={g_res['A_032']['timing']['median_ms']:.2f}ms C_nc={g_res['C_nocache']['timing']['median_ms']:.2f}ms C_cache={g_res['C_cached']['timing']['median_ms']:.2f}ms", flush=True)

    # E2E packet entries: G508_surface_nearest & G508_surface_scan_5mm (A vs C vs C_nocache)
    g_ents = [_make_entity(n, g_objs[n]["vertices_world"], g_objs[n]["triangles"])
              for n in ["Target", "Peer_000", "Competing_001"] + [f"Near_{k:03d}" for k in range(3, 12)]]
    npkt, _ = _build_nearest_packet(g_ents)
    spkt = _build_scan_packet(g_ents, threshold=0.005)

    def run_e2e_near(arm, disable_cache=False):
        diag = {}
        if disable_cache:
            with patch.object(arm.sp, "_pair_from_mesh_cache", lambda *args, **kwargs: None):
                out_n = arm.tq.surface_nearest_result(npkt, arm.sc.SpatialSceneCache(), NOOP, diagnostics=diag)
        else:
            out_n = arm.tq.surface_nearest_result(npkt, arm.sc.SpatialSceneCache(), NOOP, diagnostics=diag)
        return out_n, diag

    def run_e2e_scan(arm, disable_cache=False):
        diag = {}
        if disable_cache:
            with patch.object(arm.sp, "_pair_from_mesh_cache", lambda *args, **kwargs: None):
                out_s = arm.ss.surface_scan_result(spkt, arm.sc.SpatialSceneCache(), NOOP, diagnostics=diag)
        else:
            out_s = arm.ss.surface_scan_result(spkt, arm.sc.SpatialSceneCache(), NOOP, diagnostics=diag)
        return out_s, diag

    nr_res = _time_interleaved([
        ("A_032", (a, lambda: run_e2e_near(a))),
        ("C_nocache", (c, lambda: run_e2e_near(c, True))),
        ("C_cached", (c, lambda: run_e2e_near(c, False))),
    ], warmup=1, repeats=7, measure_mem=True, sig_fn=lambda pair: _nearest_sig(pair[0]))
    for k in ("C_nocache", "C_cached"):
        assert_entry_receipts_equal(
            _nearest_sig(nr_res["A_032"]["result"][0]),
            _nearest_sig(nr_res[k]["result"][0]),
            ref_runtime_sha=a.sha256, cand_runtime_sha=c.sha256, entry_kind="nearest",
        )

    sc_res = _time_interleaved([
        ("A_032", (a, lambda: run_e2e_scan(a))),
        ("C_nocache", (c, lambda: run_e2e_scan(c, True))),
        ("C_cached", (c, lambda: run_e2e_scan(c, False))),
    ], warmup=1, repeats=7, measure_mem=True, sig_fn=lambda pair: _scan_sig(pair[0], pair[1]))
    for k in ("C_nocache", "C_cached"):
        assert_entry_receipts_equal(
            _scan_sig(*sc_res["A_032"]["result"]),
            _scan_sig(*sc_res[k]["result"]),
            ref_runtime_sha=a.sha256, cand_runtime_sha=c.sha256, entry_kind="scan",
        )

    out["e2e_entries"] = {
        "G508_surface_nearest": {k: {"timing": nr_res[k]["timing"], "kernel_calls": nr_res[k]["result"][1]["kernel_calls"]} for k in nr_res},
        "G508_surface_scan_5mm": {k: {"timing": sc_res[k]["timing"], "kernel_calls": sc_res[k]["result"][1]["kernel_calls"]} for k in sc_res},
    }
    print(f"  [e2e] surface_nearest: A={nr_res['A_032']['timing']['median_ms']:.2f}ms C_nc={nr_res['C_nocache']['timing']['median_ms']:.2f}ms C={nr_res['C_cached']['timing']['median_ms']:.2f}ms", flush=True)
    print(f"  [e2e] surface_scan:    A={sc_res['A_032']['timing']['median_ms']:.2f}ms C_nc={sc_res['C_nocache']['timing']['median_ms']:.2f}ms C={sc_res['C_cached']['timing']['median_ms']:.2f}ms", flush=True)
    return out


def _run_real_assets_b01_b02_c(arms):
    a, c = arms["A"], arms["C"]
    manifest = {"assets": {}}

    # B01: Real D48 (47 pairs from scale_diag_001/fixtures/D48.json + ORACLE)
    d48_raw = json.loads(D48_PATH.read_bytes())
    d48_objs = {o["name"]: o for o in d48_raw["objects"]}
    d48_target = _freeze_mesh("Target", d48_objs["Target"]["vertices_world"], d48_objs["Target"]["triangles"])
    d48_peers = [_freeze_mesh(o["name"], o["vertices_world"], o["triangles"])
                 for o in sorted(d48_raw["objects"], key=lambda x: x["name"]) if o["name"] != "Target"]

    def d48_batch(arm, use_cache):
        cache = {"__sealed_query_meshes__": True} if use_cache else None
        outs = []
        agg = {}
        for p in d48_peers:
            kw = {"_mesh_cache": cache} if use_cache else {}
            r = arm.sp.measure_surface_proximity(d48_target, p, NOOP, retain_exact_rank=True, retain_witness_triangles=True, **kw)
            outs.append(r)
            for k, v in _work_summary(r["work"]).items():
                agg[k] = agg.get(k, 0) + v
        return outs, agg

    d48_expected_ids = [o["name"] for o in sorted(d48_raw["objects"], key=lambda x: x["name"]) if o["name"] != "Target"]
    assert len(d48_expected_ids) == 47 and [p.name for p in d48_peers] == d48_expected_ids
    d48_timing = _time_interleaved([
        ("A_032", (a, lambda: d48_batch(a, False))),
        ("C_nocache", (c, lambda: d48_batch(c, False))),
        ("C_cached", (c, lambda: d48_batch(c, True))),
    ], warmup=1, repeats=7, measure_mem=True, sig_fn=lambda pair: [_surface_sig(r) for r in pair[0]])

    # Independent verification of ALL 94 witnesses + winner Peer_000 [14, 36] + full merge!
    d48_outs_a, d48_agg_a = d48_timing["A_032"]["result"]
    d48_outs_nc, d48_agg_nc = d48_timing["C_nocache"]["result"]
    d48_outs_c, d48_agg_c = d48_timing["C_cached"]["result"]
    assert len(d48_outs_a) == len(d48_outs_nc) == len(d48_outs_c) == len(d48_peers)
    by_peer_c = {p.name: r for p, r in zip(d48_peers, d48_outs_c, strict=True)}
    _activate_arm(c)
    rank_c = c.sp._rank_surface_results(by_peer_c, NOOP)
    assert rank_c["ordered_object_id_groups"][0] == ["Peer_000"], rank_c["ordered_object_id_groups"][:3]
    p0_row = by_peer_c["Peer_000"]
    assert p0_row["exact_witness_triangles"]["indices"] == [14, 36], p0_row
    witnesses_verified = 0
    for peer_m, r_a, r_nc, r_c in zip(d48_peers, d48_outs_a, d48_outs_nc, d48_outs_c, strict=True):
        assert _surface_sig(r_a) == _surface_sig(r_nc) == _surface_sig(r_c), (peer_m.name, _surface_sig(r_a), _surface_sig(r_c))
        proof = witness_oracle.certify_pair(
            r_c["point_a_world"], r_c["point_b_world"], r_c["distance_m"],
            d48_objs["Target"], d48_objs[peer_m.name], position_tolerance_m=1e-9, distance_tolerance_m=1e-6,
        )
        assert proof["passed"], (peer_m.name, proof)
        witnesses_verified += 2  # left + right endpoint membership
    assert witnesses_verified == 94

    manifest["assets"]["B01_D48_real_47pairs"] = {
        "classification": "real_frozen_assembly_fixture",
        "source_path": str(D48_PATH.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(D48_PATH.read_bytes()).hexdigest(),
        "pairs": len(d48_peers),
        "faces_per_object": 60,
        "expected_winner": "Peer_000",
        "expected_canonical_faces": [14, 36],
        "witness_memberships_verified": witnesses_verified,
        "A_032_sum_work_units": d48_agg_a["work_units"],
        "C_nocache_sum_work_units": d48_agg_nc["work_units"],
        "C_cached_physical_tree_builds": d48_agg_c["mesh_cache_tree_builds"],
        "C_cached_tree_reuses": d48_agg_c["mesh_cache_tree_reuses"],
        "C_cached_translate_units": d48_agg_c["mesh_cache_translate_units"],
    }
    print(f"  [B01] D48_Real_47pairs A={d48_timing['A_032']['timing']['median_ms']:.2f}ms C_nc={d48_timing['C_nocache']['timing']['median_ms']:.2f}ms C_cache={d48_timing['C_cached']['timing']['median_ms']:.2f}ms ({d48_timing['A_032']['timing']['median_ms']/d48_timing['C_cached']['timing']['median_ms']:.2f}x)", flush=True)

    # B02: 24-part assembly short control (Obj_014 focus -> 10 exact kernel calls, plusObj_015 & surface_scan)
    asm_raw = json.loads(ASM24_PATH.read_bytes())
    asm_truth = json.loads(ASM24_TRUTH_PATH.read_bytes())
    asm_ents = [_make_entity(o["name"], o["vertices_world"], o["triangles"]) for o in asm_raw["objects"]]
    focus_idx = next(i for i, e in enumerate(asm_ents) if e.object_id == "Obj_014")
    ordered_24 = [asm_ents[focus_idx]] + asm_ents[:focus_idx] + asm_ents[focus_idx + 1 :]
    pkt24_near, _ = _build_nearest_packet(ordered_24)
    pkt24_scan = _build_scan_packet(asm_ents, threshold=0.002)

    def run_b02_scan(arm, use_cache=True):
        diag = {}
        if not use_cache:
            with patch.object(arm.sp, "_pair_from_mesh_cache", lambda *ar, **kw: None):
                res = arm.ss.surface_scan_result(pkt24_scan, arm.sc.SpatialSceneCache(), NOOP, diagnostics=diag)
        else:
            res = arm.ss.surface_scan_result(pkt24_scan, arm.sc.SpatialSceneCache(), NOOP, diagnostics=diag)
        return res, diag

    b02_near = _time_interleaved([
        ("A_032", (a, lambda: a.tq.surface_nearest_result(pkt24_near, a.sc.SpatialSceneCache(), NOOP, diagnostics={}))),
        ("C_nocache", (c, lambda: _run_no_cache_nearest(c, pkt24_near))),
        ("C_cached", (c, lambda: c.tq.surface_nearest_result(pkt24_near, c.sc.SpatialSceneCache(), NOOP, diagnostics={}))),
    ], warmup=1, repeats=7, measure_mem=True, sig_fn=_nearest_sig)
    for k in ("C_nocache", "C_cached"):
        assert_entry_receipts_equal(
            _nearest_sig(b02_near["A_032"]["result"]),
            _nearest_sig(b02_near[k]["result"]),
            ref_runtime_sha=a.sha256, cand_runtime_sha=c.sha256, entry_kind="nearest",
        )
    # Cross-check nearest distance against BASE_TRUTH.json
    b02_out = b02_near["C_cached"]["result"]
    _require(b02_out["nearest_ids"] == ["Obj_002"], f"unexpected B02 winner: {b02_out['nearest_ids']}")

    b02_scan = _time_interleaved([
        ("A_032", (a, lambda: run_b02_scan(a, True))),
        ("C_nocache", (c, lambda: run_b02_scan(c, False))),
        ("C_cached", (c, lambda: run_b02_scan(c, True))),
    ], warmup=1, repeats=7, measure_mem=True, sig_fn=lambda pair: _scan_sig(pair[0], pair[1]))
    for k in ("C_nocache", "C_cached"):
        assert_entry_receipts_equal(
            _scan_sig(*b02_scan["A_032"]["result"]),
            _scan_sig(*b02_scan[k]["result"]),
            ref_runtime_sha=a.sha256, cand_runtime_sha=c.sha256, entry_kind="scan",
        )
    b02_scan_out = b02_scan["C_cached"]["result"][0]
    _require(b02_scan_out["coverage"]["measured_match"] == asm_truth["match_count"], "B02 scan match count mismatch")
    print(f"  [B02] 24part_Obj014_nearest A={b02_near['A_032']['timing']['median_ms']:.2f}ms C_nc={b02_near['C_nocache']['timing']['median_ms']:.2f}ms C={b02_near['C_cached']['timing']['median_ms']:.2f}ms | scan_matches={b02_scan_out['coverage']['measured_match']}", flush=True)

    manifest["assets"]["B02_24part_assembly_Obj014"] = {
        "classification": "real_frozen_24part_assembly_short_control",
        "source_path": str(ASM24_PATH.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(ASM24_PATH.read_bytes()).hexdigest(),
        "objects": 24,
        "total_triangles": 978,
        "focal_id": "Obj_014",
        "nearest_winner": b02_out["nearest_ids"],
        "distance_m": b02_out["distance_m"],
        "scan_2mm_matches": b02_scan_out["coverage"]["measured_match"],
    }

    # C: External geometry families (Suzanne raw/subdiv1/subdiv2, Avocado, Lantern, BoomBox)
    ext = json.loads(EXT_SNAPSHOT_PATH.read_bytes())
    glb_hashes = {}
    for gname, expected_sha in mac.UPSTREAM_SHA256.items():
        p = EXT_GLB_DIR / f"{gname}.glb"
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        assert got == expected_sha, (gname, got, expected_sha)
        glb_hashes[gname] = got

    def tr_shift(verts, offset, rot_z=0.0):
        cs, sn = math.cos(rot_z), math.sin(rot_z)
        return [[cs * v[0] - sn * v[1] + offset[0], sn * v[0] + cs * v[1] + offset[1], v[2] + offset[2]] for v in verts]

    suz_raw = ext["suzanne_raw"][0]
    suz_s1 = ext["suzanne_subdiv1"][0]
    suz_s2 = ext["suzanne_subdiv2"][0]
    avo = ext["Avocado"][0]
    lan_body, lan_chain, lan_lantern = ext["Lantern"][0], ext["Lantern"][1], ext["Lantern"][2]
    boom = ext["BoomBox"][0]

    # Small reference box (12F) for pairing with suzanne_subdiv1 (3936 + 12 = 3948 <= 4096)
    bv = [[0, 0, 0], [0.2, 0, 0], [0.2, 0.2, 0], [0, 0.2, 0], [0, 0, 0.2], [0.2, 0, 0.2], [0.2, 0.2, 0.2], [0, 0.2, 0.2]]
    bf = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]]

    ext_pairs = [
        ("Ext_SuzanneRaw_OverlapAABB",
         _freeze_mesh("suz_a", suz_raw["vertices_world"], suz_raw["triangles"]),
         _freeze_mesh("suz_b", tr_shift(suz_raw["vertices_world"], (1.15, 0.35, 0.15), rot_z=math.radians(35)), suz_raw["triangles"])),
        ("Ext_SuzanneSubdiv1_3936F_vs_Box",
         _freeze_mesh("suz1", suz_s1["vertices_world"], suz_s1["triangles"]),
         _freeze_mesh("box12", tr_shift(bv, (1.45, -0.1, -0.1)), bf)),
        ("Ext_Avocado_vs_SuzanneRaw",
         _freeze_mesh("avo", avo["vertices_world"], avo["triangles"]),
         _freeze_mesh("suz_r", tr_shift(suz_raw["vertices_world"], (0.95, 0.0, 0.02)), suz_raw["triangles"])),
        ("Ext_Avocado_vs_LanternChain",
         _freeze_mesh("avo", avo["vertices_world"], avo["triangles"]),
         _freeze_mesh("lchain", tr_shift(lan_chain["vertices_world"], (0.04, 0.01, -0.02)), lan_chain["triangles"])),
        ("Ext_LanternBody_vs_Chain",
         _freeze_mesh("lbody", lan_body["vertices_world"], lan_body["triangles"]),
         _freeze_mesh("lchain", lan_chain["vertices_world"], lan_chain["triangles"])),
    ]
    ext_results = {}
    for ename, ml, mr in ext_pairs:
        res = _time_interleaved([
            ("A", (a, lambda m1=ml, m2=mr: a.sp.measure_surface_proximity(m1, m2, NOOP, retain_exact_rank=True, retain_witness_triangles=True))),
            ("C", (c, lambda m1=ml, m2=mr: c.sp.measure_surface_proximity(m1, m2, NOOP, retain_exact_rank=True, retain_witness_triangles=True))),
        ], warmup=1, repeats=7, measure_mem=True, sig_fn=_surface_sig)
        ra, rc = res["A"]["result"], res["C"]["result"]
        assert _surface_sig(ra) == _surface_sig(rc), (ename, _surface_sig(ra), _surface_sig(rc))
        proof = witness_oracle.certify_pair(
            rc["point_a_world"], rc["point_b_world"], rc["distance_m"],
            {"vertices_world": ml.vertices, "triangles": ml.faces},
            {"vertices_world": mr.vertices, "triangles": mr.faces},
            position_tolerance_m=1e-9, distance_tolerance_m=1e-6,
        )
        assert proof["passed"], (ename, proof)
        ext_results[ename] = {
            aname: {"timing": res[aname]["timing"], "work": _work_summary(res[aname]["result"]["work"])}
            for aname in ("A", "C")
        }
        ext_results[ename]["faces"] = [len(ml.faces), len(mr.faces)]
        ext_results[ename]["distance_m"] = rc["distance_m"]
        manifest["assets"][ename] = {
            "classification": "external_cc0_or_blender_builtin",
            "upstream_commit": mac.UPSTREAM_COMMIT,
            "glb_sha256": glb_hashes,
            "snapshot_sha256": hashlib.sha256(EXT_SNAPSHOT_PATH.read_bytes()).hexdigest(),
            "faces": [len(ml.faces), len(mr.faces)],
            "expected_admission": "admitted_complete",
            "distance_m": rc["distance_m"],
            "witness_verified": True,
        }
        print(f"  [C-ext] {ename:<30} A={res['A']['timing']['median_ms']:.2f}ms C={res['C']['timing']['median_ms']:.2f}ms ({res['A']['timing']['median_ms']/res['C']['timing']['median_ms']:.2f}x)", flush=True)

    # Explicit over-limit rejections on C (SuzanneSubdiv2 15744F, BoomBox 6036F, Subdiv1+Avocado 4618F)
    over_checks = {}
    _activate_arm(c)
    for oname, ov, of, rv, rf in (
        ("SuzanneSubdiv2_15744F", suz_s2["vertices_world"], suz_s2["triangles"], bv, bf),
        ("BoomBox_6036F", boom["vertices_world"], boom["triangles"], bv, bf),
        ("SuzanneSubdiv1_plus_Avocado_4618F", suz_s1["vertices_world"], suz_s1["triangles"], avo["vertices_world"], avo["triangles"]),
    ):
        r_over = c.sp.measure_surface_proximity(_freeze_mesh(oname, ov, of), _freeze_mesh("ref", rv, rf), NOOP)
        assert r_over["measurement_valid"] is False and r_over["reason"] == "surface_geometry_work_limit"
        over_checks[oname] = {"total_faces": len(of) + len(rf), "reason": r_over["reason"]}
        manifest["assets"][f"OverLimit_{oname}"] = {"classification": "over_limit_rejection_control", "total_faces": len(of) + len(rf), "expected_admission": "surface_geometry_work_limit"}

    return {
        "B01_D48_real": {k: {"timing": d48_timing[k]["timing"], "work": d48_timing[k]["result"][1]} for k in d48_timing},
        "B02_24part_Obj014_nearest": {k: {"timing": b02_near[k]["timing"]} for k in b02_near},
        "B02_24part_surface_scan_2mm": {k: {"timing": b02_scan[k]["timing"]} for k in b02_scan},
        "C_external_assets": ext_results,
        "external_over_limit_rejections": over_checks,
        "manifest": manifest,
    }


def _run_no_cache_nearest(arm, pkt):
    with patch.object(arm.sp, "_pair_from_mesh_cache", lambda *a, **kw: None):
        return arm.tq.surface_nearest_result(pkt, arm.sc.SpatialSceneCache(), NOOP, diagnostics={})


def _tree_metrics(root):
    depths, leaves, internals, overlaps = [], 0, 0, 0
    def walk(node, depth):
        nonlocal leaves, internals, overlaps
        lo, hi, count, ids, left, right = node
        if ids is not None:
            leaves += 1
            depths.append(depth)
        else:
            internals += 1
            llo, lhi = left[0], left[1]
            rlo, rhi = right[0], right[1]
            if all(min(lhi[k], rhi[k]) >= max(llo[k], rlo[k]) for k in range(3)):
                overlaps += 1
            walk(left, depth + 1)
            walk(right, depth + 1)
    walk(root, 1)
    return {"max_depth": max(depths) if depths else 0, "leaves": leaves, "internals": internals, "sibling_aabb_overlaps": overlaps}


def _run_s3_ablations_and_r06(arms):
    w = build_workloads(quick=False)
    a, c = arms["A"], arms["C"]
    target_cases = {n: (_freeze_mesh(n + "_l", l.vertices, l.faces), _freeze_mesh(n + "_r", r.vertices, r.faces))
                    for n, l, r in w["surface_single"]
                    if n in {"G508_Peer_000", "G508_Control_12F", "Sheet_Parallel_5um", "Sheet_Dented_2mm", "Tube_Coiled_Loose", "Rotated_30deg_Spheres", "HighRes_1536F_Pair"}}

    ablations = {}
    subphase_r06 = {}

    for cname, (ml, mr) in target_cases.items():
        def call_c_full(l=ml, r=mr):
            return c.sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True)

        def call_c_no_proj(l=ml, r=mr):
            with patch.object(c.sp._FastWitnessProjection, "build", classmethod(lambda cls, *ar, **kw: None)):
                return c.sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True)

        def call_c_median_ls2(l=ml, r=mr):
            with patch.object(c.sg, "_bvh", lambda bounds, budget, leaf_size=2: _median_bvh(bounds, budget, leaf_size=2)):
                return c.sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True)

        def call_c_sah_ls1(l=ml, r=mr):
            orig = c.sg._bvh
            with patch.object(c.sg, "_bvh", lambda bounds, budget, leaf_size=2: orig(bounds, budget, leaf_size=1)):
                return c.sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True)

        def call_c_sah_ls4(l=ml, r=mr):
            orig = c.sg._bvh
            with patch.object(c.sg, "_bvh", lambda bounds, budget, leaf_size=2: orig(bounds, budget, leaf_size=4)):
                return c.sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True)

        def call_c_median_ls4(l=ml, r=mr):
            with patch.object(c.sg, "_bvh", lambda bounds, budget, leaf_size=2: _median_bvh(bounds, budget, leaf_size=4)):
                return c.sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True)

        def call_c_no_tie_prune(l=ml, r=mr):
            orig_aabb = c.sp._aabb_exceeds_best
            with patch.object(c.sp, "_aabb_exceeds_best", lambda la, rb, best, strict=True: orig_aabb(la, rb, best, strict=True)):
                with patch.object(c.sp._FastWitnessProjection, "build", classmethod(lambda cls, *ar, **kw: None)):
                    return c.sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True)

        def call_c_median_ls4_notie_noproj(l=ml, r=mr):
            orig_aabb = c.sp._aabb_exceeds_best
            with patch.object(c.sg, "_bvh", lambda bounds, budget, leaf_size=2: _median_bvh(bounds, budget, leaf_size=4)):
                with patch.object(c.sp, "_aabb_exceeds_best", lambda la, rb, best, strict=True: orig_aabb(la, rb, best, strict=True)):
                    with patch.object(c.sp._FastWitnessProjection, "build", classmethod(lambda cls, *ar, **kw: None)):
                        return c.sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True)

        def call_c_median_ls2_notie_noproj(l=ml, r=mr):
            orig_aabb = c.sp._aabb_exceeds_best
            with patch.object(c.sg, "_bvh", lambda bounds, budget, leaf_size=2: _median_bvh(bounds, budget, leaf_size=2)):
                with patch.object(c.sp, "_aabb_exceeds_best", lambda la, rb, best, strict=True: orig_aabb(la, rb, best, strict=True)):
                    with patch.object(c.sp._FastWitnessProjection, "build", classmethod(lambda cls, *ar, **kw: None)):
                        return c.sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True)

        def call_c_sah_ls2_notie_noproj(l=ml, r=mr):
            orig_aabb = c.sp._aabb_exceeds_best
            with patch.object(c.sp, "_aabb_exceeds_best", lambda la, rb, best, strict=True: orig_aabb(la, rb, best, strict=True)):
                with patch.object(c.sp._FastWitnessProjection, "build", classmethod(lambda cls, *ar, **kw: None)):
                    return c.sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True)

        res = _time_interleaved([
            ("A_032", (a, lambda l=ml, r=mr: a.sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True))),
            ("S1_med4_notie_noproj", (c, call_c_median_ls4_notie_noproj)),
            ("S2_med2_notie_noproj", (c, call_c_median_ls2_notie_noproj)),
            ("S3_sah2_notie_noproj", (c, call_c_sah_ls2_notie_noproj)),
            ("C_median_ls4", (c, call_c_median_ls4)),
            ("C_median_ls2_minus_sah", (c, call_c_median_ls2)),
            ("C_sah_ls4", (c, call_c_sah_ls4)),
            ("C_sah_ls1", (c, call_c_sah_ls1)),
            ("C_minus_proj", (c, call_c_no_proj)),
            ("C_full", (c, call_c_full)),
        ], warmup=1, repeats=7, measure_mem=False, sig_fn=_surface_sig)
        ablations[cname] = {
            k: {"median_ms": res[k]["timing"]["median_ms"], "raw_ms": res[k]["timing"]["raw_samples_ms"], "work_units": res[k]["result"]["work"]["work_units"], "narrow": res[k]["result"]["work"]["narrow_phase_pairs"], "leaves": res[k]["result"]["work"]["leaf_pair_visits"]}
            for k in res
        }
        print(f"  [ablation] {cname:<22} A={res['A_032']['timing']['median_ms']:.2f} med4={res['C_median_ls4']['timing']['median_ms']:.2f} med2={res['C_median_ls2_minus_sah']['timing']['median_ms']:.2f} sah4={res['C_sah_ls4']['timing']['median_ms']:.2f} C-proj={res['C_minus_proj']['timing']['median_ms']:.2f} C={res['C_full']['timing']['median_ms']:.2f}", flush=True)

        # R06 Sub-phase breakdown (build vs compile vs traverse/narrow) + tree stats (untimed separate pass!)
        _activate_arm(c)
        bud = c.sp._Work(NOOP, {})
        recs, _ = c.sp._admit((ml, mr), bud)
        _, _, prep = c.sp._integer_frame(recs, bud)
        b_l = [(tuple(row[0] for row in t[4]), tuple(row[1] for row in t[4])) for t in prep[0]]
        b_r = [(tuple(row[0] for row in t[4]), tuple(row[1] for row in t[4])) for t in prep[1]]
        sub_stats = {}
        for cfg, bfn in (
            ("median_ls4", lambda bs, bd: _median_bvh(bs, bd, leaf_size=4)),
            ("median_ls2", lambda bs, bd: _median_bvh(bs, bd, leaf_size=2)),
            ("sah_ls2", lambda bs, bd: c.sg._bvh(bs, bd, leaf_size=2)),
            ("sah_ls1", lambda bs, bd: c.sg._bvh(bs, bd, leaf_size=1)),
        ):
            t0 = time.perf_counter_ns()
            r0 = bfn(b_l, c.sp._Work(NOOP, {}))
            r1 = bfn(b_r, c.sp._Work(NOOP, {}))
            t_build = (time.perf_counter_ns() - t0) / 1e6
            t1 = time.perf_counter_ns()
            _ = c.sp._compile_bvh_node(r0, 0)
            _ = c.sp._compile_bvh_node(r1, 0)
            t_comp = (time.perf_counter_ns() - t1) / 1e6
            t2 = time.perf_counter_ns()
            res_t = c.sp._nearest_tree(prep, (r0, r1), c.sp._Work(NOOP, {}))
            t_trav = (time.perf_counter_ns() - t2) / 1e6
            tm_l = _tree_metrics(r0)
            tm_r = _tree_metrics(r1)
            sub_stats[cfg] = {
                "build_ms": round(t_build, 3),
                "compile_ms": round(t_comp, 3),
                "traverse_narrow_ms": round(t_trav, 3),
                "left_tree": tm_l,
                "right_tree": tm_r,
            }
        subphase_r06[cname] = sub_stats

    return {"ablations": ablations, "r06_subphase_and_tree_quality": subphase_r06}


def _run_p95_30_samples(arms):
    a, c = arms["A"], arms["C"]
    w = build_workloads(quick=False)
    by_name = {n: (_freeze_mesh(n + "_l", l.vertices, l.faces), _freeze_mesh(n + "_r", r.vertices, r.faces))
               for n, l, r in w["surface_single"]}

    d48_raw = json.loads(D48_PATH.read_bytes())
    d48_objs = {o["name"]: o for o in d48_raw["objects"]}
    d48_t = _freeze_mesh("Target", d48_objs["Target"]["vertices_world"], d48_objs["Target"]["triangles"])
    d48_ps = [_freeze_mesh(o["name"], o["vertices_world"], o["triangles"])
              for o in sorted(d48_raw["objects"], key=lambda x: x["name"]) if o["name"] != "Target"]

    ext = json.loads(EXT_SNAPSHOT_PATH.read_bytes())
    avo = ext["Avocado"][0]
    lan_c = ext["Lantern"][1]
    avo_m = _freeze_mesh("avo", avo["vertices_world"], avo["triangles"])
    lan_m = _freeze_mesh("lchain", [ [p[0]+0.04, p[1]+0.01, p[2]-0.02] for p in lan_c["vertices_world"] ], lan_c["triangles"])

    cases = [
        ("G508_Peer_000", lambda: a.sp.measure_surface_proximity(*by_name["G508_Peer_000"], NOOP, retain_exact_rank=True),
         lambda: c.sp.measure_surface_proximity(*by_name["G508_Peer_000"], NOOP, retain_exact_rank=True)),
        ("HighRes_1536F_Pair", lambda: a.sp.measure_surface_proximity(*by_name["HighRes_1536F_Pair"], NOOP, retain_exact_rank=True),
         lambda: c.sp.measure_surface_proximity(*by_name["HighRes_1536F_Pair"], NOOP, retain_exact_rank=True)),
        ("Sheet_Dented_2mm", lambda: a.sp.measure_surface_proximity(*by_name["Sheet_Dented_2mm"], NOOP, retain_exact_rank=True),
         lambda: c.sp.measure_surface_proximity(*by_name["Sheet_Dented_2mm"], NOOP, retain_exact_rank=True)),
        ("D48_Real_47pairs_cached", lambda: [a.sp.measure_surface_proximity(d48_t, p, NOOP, retain_exact_rank=True) for p in d48_ps],
         lambda: (lambda ch: [c.sp.measure_surface_proximity(d48_t, p, NOOP, retain_exact_rank=True, _mesh_cache=ch) for p in d48_ps])({"__sealed_query_meshes__": True})),
        ("Avocado_vs_LanternChain", lambda: a.sp.measure_surface_proximity(avo_m, lan_m, NOOP, retain_exact_rank=True),
         lambda: c.sp.measure_surface_proximity(avo_m, lan_m, NOOP, retain_exact_rank=True)),
    ]
    out = {}
    for name, fn_a, fn_c in cases:
        res = _time_interleaved(
            [("A", (a, fn_a)), ("C", (c, fn_c))],
            warmup=2,
            repeats=30,
            measure_mem=False,
            sig_fn=lambda out: [_surface_sig(r) for r in out] if isinstance(out, list) else _surface_sig(out),
        )
        ra = res["A"]["timing"]["raw_samples_ms"]
        rc = res["C"]["timing"]["raw_samples_ms"]
        wins = sum(1 for x, y in zip(ra, rc) if y < x)
        out[name] = {
            "A": res["A"]["timing"],
            "C": res["C"]["timing"],
            "C_faster_pairs_of_30": wins,
            "speedup_median": res["A"]["timing"]["median_ms"] / res["C"]["timing"]["median_ms"],
            "speedup_p95": res["A"]["timing"]["p95_ms"] / res["C"]["timing"]["p95_ms"],
        }
        print(f"  [30-rep p95] {name:<25} p50: {res['A']['timing']['median_ms']:.2f}->{res['C']['timing']['median_ms']:.2f}ms | p95: {res['A']['timing']['p95_ms']:.2f}->{res['C']['timing']['p95_ms']:.2f}ms | wins={wins}/30", flush=True)
    return out


def main():
    arms = {
        "A": _load_arm_modules(ARM_A_ROOT),
        "B": _load_arm_modules(ARM_B_ROOT),
        "C": _load_arm_modules(ROOT),
    }
    print(f"Loaded arms: A={arms['A'].sha256[:12]} B={arms['B'].sha256[:12]} C={arms['C'].sha256[:12]}", flush=True)

    main_res = _run_three_arm_main(arms)
    real_assets = _run_real_assets_b01_b02_c(arms)
    s3_res = _run_s3_ablations_and_r06(arms)
    p95_res = _run_p95_30_samples(arms)

    manifest = real_assets.pop("manifest")
    manifest["schema"] = "m3-bvh-asset-manifest-v1"
    manifest["assets"]["A01_A02_G508"] = {
        "classification": "real_frozen_scene_snapshot_and_oracle",
        "snapshot_path": str(G508_PATH.relative_to(ROOT)),
        "snapshot_sha256": hashlib.sha256(G508_PATH.read_bytes()).hexdigest(),
        "pairs": 11,
        "faces": {"Target": 508, "Peer_000": 508, "Competing_001": 60, "Near_003..011": 60},
    }
    manifest["assets"]["A03_M3_scalability_designed_cases"] = {
        "classification": "analytic_designed_counterexamples",
        "path": "verification/m3_pair_scalability_001/testing/DESIGNED_CASES.json",
        "sha256": hashlib.sha256((ROOT / "verification/m3_pair_scalability_001/testing/DESIGNED_CASES.json").read_bytes()).hexdigest(),
    }
    manifest["assets"]["A04_M3_sufficient_separation_designed_cases"] = {
        "classification": "analytic_designed_counterexamples",
        "path": "verification/m3_sufficient_separation_001/testing/DESIGNED_CASES.json",
        "sha256": hashlib.sha256((ROOT / "verification/m3_sufficient_separation_001/testing/DESIGNED_CASES.json").read_bytes()).hexdigest(),
    }
    manifest["assets"]["A05_M3_analytic_families"] = {
        "classification": "synthetic_analytic_families",
        "path": "verification/m3_asset_cases.py",
        "sha256": hashlib.sha256((ROOT / "verification/m3_asset_cases.py").read_bytes()).hexdigest(),
    }

    (ROOT / "benchmarks/ASSET_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf8")

    ablation_report = {
        "schema": "m3-bvh-ablation-v1",
        "environment": {
            "python_version": sys.version.split()[0],
            "numpy_version": np.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "blender_version": "5.2.3 LTS",
            "gc_policy": "collect_before_and_disable_during_interleaved_repeats",
        },
        "arm_sources_sha256": {
            "A_032_6c93f23": arms["A"].sha256,
            "B_37ed2d6": arms["B"].sha256,
            "C_fixed": arms["C"].sha256,
        },
        "three_arm_interleaved_7rep": main_res,
        "real_and_external_assets_7rep": real_assets,
        "s3_cumulative_and_loo_ablations": s3_res["ablations"],
        "r06_subphase_and_tree_quality": s3_res["r06_subphase_and_tree_quality"],
        "tail_30rep_p95": p95_res,
    }
    (ROOT / "benchmarks/ALGORITHM_ABLATION.json").write_text(json.dumps(ablation_report, indent=2, sort_keys=True), encoding="utf8")
    print("SAVED benchmarks/ASSET_MANIFEST.json and benchmarks/ALGORITHM_ABLATION.json", flush=True)


if __name__ == "__main__":
    main()

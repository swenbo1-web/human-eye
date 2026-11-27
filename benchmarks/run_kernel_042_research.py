"""M3 BVH-042 Exact Build-Pipeline Research Harness.

Supports isolated uninstrumented paired timing, separate Win32/tracemalloc memory
measurement, separate instrumented phase profiling, complete raw-tree & solver
signature equivalence verification, and 30-repeat confirmatory runs.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import gc
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import platform
import shutil
import statistics
import sys
import time
import tracemalloc
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from benchmarks.bvh_eval import (
    _analyze_sig,
    _closed_sig,
    _compare_signatures,
    _is_sha256_hex,
    _make_mesh,
    _spatial_sig,
    _surface_sig,
    _triangulate,
    _work_summary,
    build_workloads,
)

BENCH_DIR = Path(__file__).resolve().parent
ARMS_ROOT = ROOT / "scratch" / "042_arms"
FROZEN_COMMIT = "119327bbb4e645c5de3bfbc0d30259736b9a2677"
FROZEN_RUNTIME_SHA = "eff6511223646c125ac05cd6080d3bcbe191d1c945a8b3b7293d2c1bc0ff1ee4"

G508_PATH = ROOT / "verification/spatial_task_qualification_001/entry/run_01/ACTUAL_SNAPSHOT.json"
D48_PATH = ROOT / "verification/scale_diag_001/fixtures/D48.json"
ASM24_PATH = ROOT / "verification/m4_surface_scan_001/qualification/BASE_SNAPSHOT.json"

NOOP = lambda _stage: None


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def _encoded(val) -> bytes:
    return json.dumps(val, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha256_json(val) -> str:
    return hashlib.sha256(_encoded(val)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mesh_input_sha256(mesh) -> str:
    import struct
    verts = mesh.vertices.tolist() if hasattr(mesh.vertices, "tolist") else [list(v) for v in mesh.vertices]
    faces = mesh.faces.tolist() if hasattr(mesh.faces, "tolist") else [list(f) for f in mesh.faces]
    enc_verts = [
        [c if math.isfinite(c) else ("nf_" + struct.pack("!d", float(c)).hex()) for c in p]
        for p in verts
    ]
    return _sha256_json({"object_id": getattr(mesh, "object_id", None), "vertices": enc_verts, "faces": faces})


def _pair_input_sha256(left, right) -> str:
    return _sha256_json([_mesh_input_sha256(left), _mesh_input_sha256(right)])


def _batch_input_sha256(target, peers) -> str:
    return _sha256_json([_mesh_input_sha256(target)] + [_mesh_input_sha256(p) for p in peers])


def _win32_env_info() -> dict:
    info = {
        "python_version": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "pid": os.getpid(),
    }
    try:
        kernel32 = ctypes.windll.kernel32
        proc_mask = ctypes.c_size_t()
        sys_mask = ctypes.c_size_t()
        handle = kernel32.GetCurrentProcess()
        if kernel32.GetProcessAffinityMask(handle, ctypes.byref(proc_mask), ctypes.byref(sys_mask)):
            info["win32_process_affinity_mask"] = hex(proc_mask.value)
            info["win32_system_affinity_mask"] = hex(sys_mask.value)
    except Exception as exc:
        info["win32_affinity_error"] = repr(exc)
    return info


class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _win32_process_mem() -> dict:
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.K32GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(_PROCESS_MEMORY_COUNTERS), wintypes.DWORD,
        ]
        kernel32.K32GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = _PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(_PROCESS_MEMORY_COUNTERS)
        if kernel32.K32GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return {
                "working_set_bytes": int(counters.WorkingSetSize),
                "peak_working_set_bytes": int(counters.PeakWorkingSetSize),
                "pagefile_bytes": int(counters.PagefileUsage),
            }
    except Exception as exc:
        return {"error": repr(exc)}
    return {}


def load_arm_modules(arm_name: str, arm_root: Path):
    saved_modules = {k: sys.modules.pop(k) for k in list(sys.modules)
                     if k == "human_eye_plugin" or k.startswith("human_eye_plugin.")}
    saved_m1 = {k: sys.modules.pop(k) for k in list(sys.modules)
                if k == "human_eye_module1_operators" or k.startswith("human_eye_module1_operators.")}
    resolved_root = arm_root.resolve()
    sys.path.insert(0, str(resolved_root))
    try:
        import human_eye_module1_operators  # noqa: F401
        from human_eye_plugin import (
            geometry_safety,
            mesh_structure,
            runtime_identity,
            scene_cache,
            surface_geometry,
            surface_proximity,
        )
        mods = {k: v for k, v in sys.modules.items()
                if k.startswith("human_eye_plugin") or k.startswith("human_eye_module1_operators")}
        for mname, mod in mods.items():
            mfile = getattr(mod, "__file__", None)
            if mfile is not None and not Path(mfile).resolve().is_relative_to(resolved_root):
                raise RuntimeError(f"Cross-arm leak for {arm_name}/{mname}: {mfile}")
        rid = runtime_identity.runtime_identity()
        ident = rid["source_sha256"]
        _require(_is_sha256_hex(ident), f"Invalid runtime source_sha256 for {arm_name}: {ident!r}")
        file_shas = {r["path"]: r["sha256"] for r in rid["source_files"]}
        return SimpleNamespace(
            name=arm_name,
            root=resolved_root,
            mods=mods,
            source_sha256=ident,
            sp_file_sha256=file_shas["human_eye_plugin/surface_proximity.py"],
            sg_file_sha256=file_shas["human_eye_plugin/surface_geometry.py"],
            sp_raw_sha256=_file_sha256(resolved_root / "human_eye_plugin/surface_proximity.py"),
            sg_raw_sha256=_file_sha256(resolved_root / "human_eye_plugin/surface_geometry.py"),
            sp=surface_proximity,
            sg=surface_geometry,
            gs=geometry_safety,
            ms=mesh_structure,
            sc=scene_cache,
        )
    finally:
        sys.path.pop(0)
        for k in list(sys.modules):
            if k.startswith("human_eye_plugin") or k.startswith("human_eye_module1_operators"):
                sys.modules.pop(k, None)
        sys.modules.update(saved_m1)
        sys.modules.update(saved_modules)


def activate_arm(arm) -> None:
    for k in list(sys.modules):
        if k.startswith("human_eye_plugin") or k.startswith("human_eye_module1_operators"):
            sys.modules.pop(k, None)
    sys.modules.update(arm.mods)


def _to_ndarray_mesh(mesh):
    return SimpleNamespace(
        object_id=mesh.object_id,
        name=getattr(mesh, "name", mesh.object_id),
        vertices=np.array(mesh.vertices, dtype=np.float64),
        faces=np.array(mesh.faces, dtype=np.int32),
    )


def _freeze_mesh(oid: str, verts, faces):
    return SimpleNamespace(
        object_id=oid,
        name=oid,
        vertices=tuple(tuple(float(c) for c in v) for v in verts),
        faces=tuple(tuple(int(i) for i in f) for f in _triangulate(faces)),
    )


def _build_sparse_mixed_bit_control():
    """Valid sparse 100kV container + loose NaN tail + >256 leaf pairs (20F vs 20F) + degenerate & mixed dyadic faces."""
    n_verts = 100000
    va = [(float("nan"), 0.0, 0.0)] * n_verts
    vb = [(0.0, float("nan"), 0.0)] * n_verts
    # Place referenced vertices at sparse offsets with mixed binary64 dyadic scales + 1 degenerate tri each
    fa = []
    fb = []
    # Mix exponents (1.0 + k * 2**-20, 4096.0 + k * 2**-10) cleanly representable in binary64
    step = math.ldexp(1.0, -20)
    shift = 0.015625
    # Tri 0 on A: degenerate zero-area collinear
    va[100] = (0.0, 0.0, 0.0)
    va[101] = (1.0 * step, 0.0, 0.0)
    va[102] = (2.0 * step, 0.0, 0.0)
    fa.append((100, 101, 102))
    # Tri 0 on B: degenerate zero-area collinear
    vb[100] = (shift, 0.0, 0.0)
    vb[101] = (shift + 1.0 * step, 0.0, 0.0)
    vb[102] = (shift + 2.0 * step, 0.0, 0.0)
    fb.append((100, 101, 102))
    for k in range(1, 20):
        base = 5000 * k
        va[base] = (k * 0.125, (k % 5) * step, 0.0)
        va[base + 1] = (k * 0.125 + 0.0625, ((k + 1) % 5) * step, 0.03125)
        va[base + 2] = (k * 0.125 + 0.03125, ((k + 2) % 5) * step, -0.03125)
        fa.append((base, base + 1, base + 2))
        vb[base] = (shift + k * 0.125, (k % 5) * step, 0.125)
        vb[base + 1] = (shift + k * 0.125 + 0.0625, ((k + 1) % 5) * step, 0.15625)
        vb[base + 2] = (shift + k * 0.125 + 0.03125, ((k + 2) % 5) * step, 0.09375)
        fb.append((base, base + 1, base + 2))
    ma = SimpleNamespace(object_id="SparseMixed_A", name="SparseMixed_A", vertices=tuple(va), faces=tuple(fa))
    mb = SimpleNamespace(object_id="SparseMixed_B", name="SparseMixed_B", vertices=tuple(vb), faces=tuple(fb))
    return ma, mb


def build_042_workloads() -> dict:
    """Build immutable frozen snapshot and analytic synthetic workloads."""
    base = build_workloads(quick=False)
    by_name = {name: (l, r) for name, l, r in base["surface_single"]}

    # Real snapshot D48 (47 pairs)
    d48_raw = json.loads(D48_PATH.read_bytes())
    d48_objs = {o["name"]: o for o in d48_raw["objects"]}
    d48_target = _freeze_mesh("Target", d48_objs["Target"]["vertices_world"], d48_objs["Target"]["triangles"])
    d48_peers = [
        _freeze_mesh(o["name"], o["vertices_world"], o["triangles"])
        for o in sorted(d48_raw["objects"], key=lambda x: x["name"])
        if o["name"] != "Target"
    ]

    # Real snapshot 24-part assembly (Obj_014 vs 23 others as direct-kernel pairs, NO host timing)
    asm_raw = json.loads(ASM24_PATH.read_bytes())
    asm_objs = {o["name"]: o for o in asm_raw["objects"]}
    asm_target = _freeze_mesh("Obj_014", asm_objs["Obj_014"]["vertices_world"], asm_objs["Obj_014"]["triangles"])
    asm_peers = [
        _freeze_mesh(o["name"], o["vertices_world"], o["triangles"])
        for o in sorted(asm_raw["objects"], key=lambda x: x["name"])
        if o["name"] != "Obj_014"
    ]

    sparse_a, sparse_b = _build_sparse_mixed_bit_control()

    singles = [
        ("G508_Peer_000", "real_frozen_snapshot_asset", by_name["G508_Peer_000"][0], by_name["G508_Peer_000"][1], "hotspot_balanced"),
        ("G508_Competing_001", "real_frozen_snapshot_asset", by_name["G508_Competing_001"][0], by_name["G508_Competing_001"][1], "hotspot_asymmetric"),
        ("HighRes_1536F_Pair", "analytic_synthetic_or_control", by_name["HighRes_1536F_Pair"][0], by_name["HighRes_1536F_Pair"][1], "construction_heavy"),
        ("Sheet_Dented_2mm", "analytic_synthetic_or_control", by_name["Sheet_Dented_2mm"][0], by_name["Sheet_Dented_2mm"][1], "construction_heavy"),
        ("Sheet_Parallel_5um", "analytic_synthetic_or_control", by_name["Sheet_Parallel_5um"][0], by_name["Sheet_Parallel_5um"][1], "construction_heavy_near"),
        ("Rotated_30deg_Spheres", "analytic_synthetic_or_control", by_name["Rotated_30deg_Spheres"][0], by_name["Rotated_30deg_Spheres"][1], "construction_heavy"),
        ("Tube_Coiled_Loose", "analytic_synthetic_or_control", by_name["Tube_Coiled_Loose"][0], by_name["Tube_Coiled_Loose"][1], "construction_heavy"),
        ("Control_12F_Linear", "analytic_synthetic_or_control", by_name["G508_Control_12F"][0], by_name["G508_Control_12F"][1], "linear_bypass_control"),
        ("Sparse_100kV_Degenerate_MixedBit", "analytic_synthetic_or_control", sparse_a, sparse_b, "sparse_degenerate_mixed_bit"),
    ]

    batches = [
        ("D48_Real_47pairs", "real_frozen_snapshot_asset", d48_target, d48_peers),
        ("Assembly24_Obj014_23pairs", "real_frozen_snapshot_asset", asm_target, asm_peers),
    ]

    single_specs = []
    for wid, cls, l_tup, r_tup, role in singles:
        single_specs.append({
            "id": wid,
            "classification": cls,
            "role": role,
            "left_faces": len(l_tup.faces),
            "right_faces": len(r_tup.faces),
            "tuple_pair": (l_tup, r_tup),
            "ndarray_pair": (_to_ndarray_mesh(l_tup), _to_ndarray_mesh(r_tup)),
            "input_sha256": _pair_input_sha256(l_tup, r_tup),
        })

    batch_specs = []
    for wid, cls, target_t, peers_t in batches:
        batch_specs.append({
            "id": wid,
            "classification": cls,
            "pair_count": len(peers_t),
            "peer_ids": [p.object_id for p in peers_t],
            "target_faces": len(target_t.faces),
            "peer_faces_total": sum(len(p.faces) for p in peers_t),
            "tuple_batch": (target_t, peers_t),
            "ndarray_batch": (_to_ndarray_mesh(target_t), [_to_ndarray_mesh(p) for p in peers_t]),
            "input_sha256": _batch_input_sha256(target_t, peers_t),
        })

    return {
        "singles": single_specs,
        "batches": batch_specs,
        "options": {"retain_exact_rank": True, "retain_witness_triangles": True, "projection_mode": "settled_credit_031_ref"},
        "options_sha256": _sha256_json({"retain_exact_rank": True, "retain_witness_triangles": True, "projection_mode": "settled_credit_031_ref"}),
        "source_assets": {
            "G508": {"path": str(G508_PATH.relative_to(ROOT)), "sha256": _file_sha256(G508_PATH)},
            "D48": {"path": str(D48_PATH.relative_to(ROOT)), "sha256": _file_sha256(D48_PATH)},
            "Assembly24": {"path": str(ASM24_PATH.relative_to(ROOT)), "sha256": _file_sha256(ASM24_PATH)},
        },
    }


def _tree_struct_summary(node) -> dict:
    nodes = 0
    leaves = 0
    max_depth = 0
    leaf_1 = 0
    leaf_2 = 0
    leaf_gt2 = 0

    def walk(cur, depth):
        nonlocal nodes, leaves, max_depth, leaf_1, leaf_2, leaf_gt2
        nodes += 1
        if depth > max_depth:
            max_depth = depth
        _lo, _hi, count, ids, left, right = cur
        if ids is not None:
            leaves += 1
            if count == 1:
                leaf_1 += 1
            elif count == 2:
                leaf_2 += 1
            else:
                leaf_gt2 += 1
            return [tuple(_lo), tuple(_hi), count, list(ids), None, None]
        return [tuple(_lo), tuple(_hi), count, None, walk(left, depth + 1), walk(right, depth + 1)]

    serial = walk(node, 0)
    return {
        "node_count": nodes,
        "leaf_count": leaves,
        "internal_nodes": nodes - leaves,
        "max_depth": max_depth,
        "leaf_1_count": leaf_1,
        "leaf_2_count": leaf_2,
        "leaf_gt2_count": leaf_gt2,
        "tree_sha256": _sha256_json(serial),
    }


def measure_raw_trees_for_arm(arm, left, right) -> dict:
    """Invoke direct admission+frame+_distance_roots on an arm to capture exact raw trees & digests."""
    activate_arm(arm)
    budget = arm.sp._Work(NOOP, {})
    records, _ = arm.sp._admit((left, right), budget)
    _, _, prepared = arm.sp._integer_frame(records, budget)
    roots = arm.sp._distance_roots(prepared, budget)
    s0 = _tree_struct_summary(roots[0])
    s1 = _tree_struct_summary(roots[1])
    return {
        "left": s0,
        "right": s1,
        "combined_tree_sha256": _sha256_json([s0["tree_sha256"], s1["tree_sha256"]]),
        "roots": roots,
    }


def assert_raw_trees_equal(tree_a, tree_b, path="root"):
    """Strict structural and content equality across every node of two raw BVH trees."""
    lo_a, hi_a, cnt_a, ids_a, l_a, r_a = tree_a
    lo_b, hi_b, cnt_b, ids_b, l_b, r_b = tree_b
    _require(lo_a == lo_b and hi_a == hi_b, f"{path}: bounds mismatch {lo_a, hi_a} != {lo_b, hi_b}")
    _require(cnt_a == cnt_b, f"{path}: count mismatch {cnt_a} != {cnt_b}")
    if ids_a is not None or ids_b is not None:
        _require(ids_a is not None and ids_b is not None, f"{path}: leaf vs internal mismatch")
        _require(list(ids_a) == list(ids_b), f"{path}: leaf ids/order mismatch {ids_a} != {ids_b}")
        _require(l_a is None and r_a is None and l_b is None and r_b is None, f"{path}: leaf children non-None")
        return list(ids_a)
    left_ids = assert_raw_trees_equal(l_a, l_b, path + ".L")
    right_ids = assert_raw_trees_equal(r_a, r_b, path + ".R")
    _require(len(left_ids) + len(right_ids) == cnt_a, f"{path}: descendant partition count mismatch")
    return left_ids + right_ids


def _percentile_linear(sorted_vals: list[float], q: float) -> float:
    """Explicit linear-interpolation quantile estimator on sorted samples (type-7, same as numpy default)."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = (len(sorted_vals) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(sorted_vals[lo])
    frac = pos - lo
    return float(sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac)


def _summarize_samples(wall_samples: list[float], cpu_samples: list[float]) -> dict:
    sw = sorted(wall_samples)
    sc = sorted(cpu_samples)
    return {
        "n": len(wall_samples),
        "raw_wall_ms": [round(x, 4) for x in wall_samples],
        "raw_cpu_ms": [round(x, 4) for x in cpu_samples],
        "median_ms": round(statistics.median(wall_samples), 4),
        "mean_ms": round(statistics.mean(wall_samples), 4),
        "min_ms": round(sw[0], 4),
        "max_ms": round(sw[-1], 4),
        "p95_ms": round(_percentile_linear(sw, 0.95), 4),
        "cpu_median_ms": round(statistics.median(cpu_samples), 4),
        "cpu_mean_ms": round(statistics.mean(cpu_samples), 4),
        "p95_estimator": "linear_interpolation_type7_on_sorted_direct_kernel_samples",
    }


def run_paired_timing(arms: list, make_call, *, warmup: int = 2, repeats: int = 7, sig_fn=None) -> dict:
    """Uninstrumented balanced-permutation interleaved paired timing across arms."""
    n_arms = len(arms)
    names = [a.name for a in arms]
    arm_map = {a.name: a for a in arms}
    fn_map = {a.name: make_call(a) for a in arms}

    # Build balanced order table cycling rotations + reversals
    base_orders = []
    for k in range(n_arms):
        rot = names[k:] + names[:k]
        base_orders.append(rot)
        if n_arms > 1:
            base_orders.append(list(reversed(rot)))

    for _ in range(warmup):
        for aname in names:
            activate_arm(arm_map[aname])
            fn_map[aname]()

    wall_raw = {n: [] for n in names}
    cpu_raw = {n: [] for n in names}
    repeat_sig_hashes = {n: [] for n in names}
    ref_sigs = {}
    last_outs = {}
    exec_orders = []

    gc.collect()
    gc.disable()
    try:
        for r in range(repeats):
            order = base_orders[r % len(base_orders)]
            exec_orders.append(order)
            for aname in order:
                activate_arm(arm_map[aname])
                fn = fn_map[aname]
                t0_c = time.process_time_ns()
                t0_w = time.perf_counter_ns()
                out = fn()
                t1_w = time.perf_counter_ns()
                t1_c = time.process_time_ns()
                wall_raw[aname].append((t1_w - t0_w) / 1e6)
                cpu_raw[aname].append((t1_c - t0_c) / 1e6)
                if sig_fn is not None:
                    sig = sig_fn(out)
                    sh = _sha256_json(sig)
                    repeat_sig_hashes[aname].append(sh)
                    if aname not in ref_sigs:
                        ref_sigs[aname] = (sig, sh)
                    else:
                        _require(sh == ref_sigs[aname][1], f"Within-arm repeat signature drift on {aname} repeat {r}")
                last_outs[aname] = out
    finally:
        gc.enable()

    # Cross-arm exact semantic signature equality check
    if sig_fn is not None and len(names) > 1:
        base_n = names[0]
        base_sig, base_hash = ref_sigs[base_n]
        for other_n in names[1:]:
            other_sig, other_hash = ref_sigs[other_n]
            _require(base_sig == other_sig and base_hash == other_hash,
                     f"Cross-arm signature mismatch between {base_n} and {other_n}")

    # Separate memory pass (excluded from timing loop)
    mem_stats = {}
    for aname in names:
        activate_arm(arm_map[aname])
        gc.collect()
        ws_before = _win32_process_mem()
        tracemalloc.start()
        try:
            _ = fn_map[aname]()
            cur_b, peak_b = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        ws_after = _win32_process_mem()
        mem_stats[aname] = {
            "tracemalloc_current_bytes": int(cur_b),
            "tracemalloc_peak_bytes": int(peak_b),
            "win32_before": ws_before,
            "win32_after": ws_after,
            "memory_metric_scope": "separate_post_timing_pass_tracemalloc_and_win32_process_working_set",
        }

    # Paired deltas against arms[0] (reference)
    ref_n = names[0]
    paired_vs_ref = {}
    for other_n in names[1:]:
        deltas_ms = [round(o - ref_v, 4) for o, ref_v in zip(wall_raw[other_n], wall_raw[ref_n])]
        pct_diffs = [round(((ref_v - o) / ref_v) * 100.0, 2) if ref_v > 0 else 0.0
                     for o, ref_v in zip(wall_raw[other_n], wall_raw[ref_n])]
        paired_vs_ref[other_n] = {
            "raw_paired_delta_ms_arm_minus_ref": deltas_ms,
            "raw_paired_reduction_pct": pct_diffs,
            "median_reduction_pct": round(statistics.median(pct_diffs), 2),
            "mean_reduction_pct": round(statistics.mean(pct_diffs), 2),
        }

    return {
        "execution_orders": exec_orders,
        "arms": {
            aname: {
                "timing": _summarize_samples(wall_raw[aname], cpu_raw[aname]),
                "memory": mem_stats[aname],
                "repeat_signature_sha256": repeat_sig_hashes[aname],
            }
            for aname in names
        },
        "paired_vs_ref": paired_vs_ref,
        "last_outs": last_outs,
    }


def _instrumented_sah_builder(flat_bounds, budget, ids, leaf_size, depth, *,
                              mode: str, timers: dict, counters: dict, known_bounds=None):
    """Exact instrumented twin of SAH builder sub-loops for separate S0 / residual phase profiling.

    Supported modes:
      - 'baseline' (Arm A)
      - 'b1' (Arm B: fused stats)
      - 'b2' (Arm C: division-free partition)
      - 'b1_b2' (Arm D: fused stats + division-free partition)
      - 'b1_b2_b3' (Arm E: + inherited SAH child bounds)
    """
    t_enter = time.perf_counter_ns()
    n = len(ids)
    budget.consume(1 + n, "surface_bvh_build")
    counters["nodes"] += 1
    if depth > counters["max_depth"]:
        counters["max_depth"] = depth
    if n == 1:
        counters["leaves"] += 1
        lo, hi = (known_bounds if known_bounds is not None
                  else ((flat_bounds[ids[0]][0], flat_bounds[ids[0]][1], flat_bounds[ids[0]][2]),
                        (flat_bounds[ids[0]][3], flat_bounds[ids[0]][4], flat_bounds[ids[0]][5])))
        timers["node_alloc_ns"] += time.perf_counter_ns() - t_enter
        return (lo, hi, 1, ids, None, None)
    if known_bounds is None and n == 2 and leaf_size >= 2:
        counters["leaves"] += 1
        r0, r1 = flat_bounds[ids[0]], flat_bounds[ids[1]]
        res = (
            (r0[0] if r0[0] <= r1[0] else r1[0], r0[1] if r0[1] <= r1[1] else r1[1], r0[2] if r0[2] <= r1[2] else r1[2]),
            (r0[3] if r0[3] >= r1[3] else r1[3], r0[4] if r0[4] >= r1[4] else r1[4], r0[5] if r0[5] >= r1[5] else r1[5]),
            2, ids, None, None,
        )
        timers["node_alloc_ns"] += time.perf_counter_ns() - t_enter
        return res

    use_fused = mode in ("b1", "b1_b2")
    use_divfree = mode in ("b2", "b1_b2", "b1_b2_b3")
    use_inherit = (mode == "b1_b2_b3")
    sah_eligible = (n > leaf_size and n > 12 and depth < 20)

    first = flat_bounds[ids[0]]
    sub_ns = 0

    if known_bounds is not None:
        lo, hi = known_bounds
        lx, ly, lz = lo
        hx, hy, hz = hi
        if n <= leaf_size:
            counters["leaves"] += 1
            timers["node_alloc_ns"] += time.perf_counter_ns() - t_enter
            return (lo, hi, n, ids, None, None)
        if sah_eligible:
            tg0 = time.perf_counter_ns()
            c0x = c1x = first[6]
            c0y = c1y = first[7]
            c0z = c1z = first[8]
            for idx in ids[1:]:
                row = flat_bounds[idx]
                cx, cy, cz = row[6], row[7], row[8]
                if cx < c0x: c0x = cx
                elif cx > c1x: c1x = cx
                if cy < c0y: c0y = cy
                elif cy > c1y: c1y = cy
                if cz < c0z: c0z = cz
                elif cz > c1z: c1z = cz
            dt = time.perf_counter_ns() - tg0
            timers["node_centroid_gather_ns"] += dt
            sub_ns += dt
    elif use_fused and sah_eligible:
        tg0 = time.perf_counter_ns()
        lx, ly, lz, hx, hy, hz, c0x, c0y, c0z = first
        c1x, c1y, c1z = c0x, c0y, c0z
        for idx in ids[1:]:
            r0, r1, r2, r3, r4, r5, cx, cy, cz = flat_bounds[idx]
            if r0 < lx: lx = r0
            if r1 < ly: ly = r1
            if r2 < lz: lz = r2
            if r3 > hx: hx = r3
            if r4 > hy: hy = r4
            if r5 > hz: hz = r5
            if cx < c0x: c0x = cx
            elif cx > c1x: c1x = cx
            if cy < c0y: c0y = cy
            elif cy > c1y: c1y = cy
            if cz < c0z: c0z = cz
            elif cz > c1z: c1z = cz
        dt = time.perf_counter_ns() - tg0
        timers["fused_stats_gather_ns"] += dt
        sub_ns += dt
        lo = (lx, ly, lz)
        hi = (hx, hy, hz)
    else:
        tg0 = time.perf_counter_ns()
        lx, ly, lz, hx, hy, hz = first[0], first[1], first[2], first[3], first[4], first[5]
        for idx in ids[1:]:
            row = flat_bounds[idx]
            if row[0] < lx: lx = row[0]
            if row[1] < ly: ly = row[1]
            if row[2] < lz: lz = row[2]
            if row[3] > hx: hx = row[3]
            if row[4] > hy: hy = row[4]
            if row[5] > hz: hz = row[5]
        dt = time.perf_counter_ns() - tg0
        timers["node_aabb_gather_ns"] += dt
        sub_ns += dt
        lo = (lx, ly, lz)
        hi = (hx, hy, hz)
        if n <= leaf_size:
            counters["leaves"] += 1
            timers["node_alloc_ns"] += (time.perf_counter_ns() - t_enter) - sub_ns
            return (lo, hi, n, ids, None, None)
        if sah_eligible:
            tc0 = time.perf_counter_ns()
            c0x = c1x = first[6]
            c0y = c1y = first[7]
            c0z = c1z = first[8]
            for idx in ids[1:]:
                row = flat_bounds[idx]
                cx, cy, cz = row[6], row[7], row[8]
                if cx < c0x: c0x = cx
                elif cx > c1x: c1x = cx
                if cy < c0y: c0y = cy
                elif cy > c1y: c1y = cy
                if cz < c0z: c0z = cz
                elif cz > c1z: c1z = cz
            dt_c = time.perf_counter_ns() - tc0
            timers["node_centroid_gather_ns"] += dt_c
            sub_ns += dt_c

    if n <= leaf_size:
        counters["leaves"] += 1
        timers["node_alloc_ns"] += (time.perf_counter_ns() - t_enter) - sub_ns
        return (lo, hi, n, ids, None, None)

    if sah_eligible:
        best_cost = None
        best_axis = -1
        best_split = 0
        best_cmin = 0
        best_cspan = 1
        best_left_bounds = None
        best_right_bounds = None
        min_side = max(1, n >> 4)
        cbounds = ((c0x, c1x), (c0y, c1y), (c0z, c1z))
        for axis in (0, 1, 2):
            cmin, cmax = cbounds[axis]
            if cmax <= cmin:
                continue
            th0 = time.perf_counter_ns()
            cspan = cmax - cmin
            bcnt = [0] * 12
            blx = [0] * 12
            bly = [0] * 12
            blz = [0] * 12
            bhx = [0] * 12
            bhy = [0] * 12
            bhz = [0] * 12
            ck = 6 + axis
            for idx in ids:
                row = flat_bounds[idx]
                b = ((row[ck] - cmin) * 12) // cspan
                counters["bin_divisions"] += 1
                if b > 11:
                    b = 11
                c = bcnt[b]
                if c == 0:
                    blx[b], bly[b], blz[b], bhx[b], bhy[b], bhz[b] = row[0], row[1], row[2], row[3], row[4], row[5]
                else:
                    if row[0] < blx[b]: blx[b] = row[0]
                    if row[1] < bly[b]: bly[b] = row[1]
                    if row[2] < blz[b]: blz[b] = row[2]
                    if row[3] > bhx[b]: bhx[b] = row[3]
                    if row[4] > bhy[b]: bhy[b] = row[4]
                    if row[5] > bhz[b]: bhz[b] = row[5]
                bcnt[b] = c + 1
            dt_h = time.perf_counter_ns() - th0
            timers["axis_histogram_build_ns"] += dt_h
            sub_ns += dt_h

            ts0 = time.perf_counter_ns()
            right_area = [0] * 12
            right_cnt = [0] * 12
            r_bounds = [None] * 12 if use_inherit else None
            rc = 0
            has_r = False
            rx0 = ry0 = rz0 = rx1 = ry1 = rz1 = 0
            for b in range(11, 0, -1):
                cnt = bcnt[b]
                if cnt:
                    rc += cnt
                    if not has_r:
                        rx0, ry0, rz0, rx1, ry1, rz1 = blx[b], bly[b], blz[b], bhx[b], bhy[b], bhz[b]
                        has_r = True
                    else:
                        if blx[b] < rx0: rx0 = blx[b]
                        if bly[b] < ry0: ry0 = bly[b]
                        if blz[b] < rz0: rz0 = blz[b]
                        if bhx[b] > rx1: rx1 = bhx[b]
                        if bhy[b] > ry1: ry1 = bhy[b]
                        if bhz[b] > rz1: rz1 = bhz[b]
                right_cnt[b - 1] = rc
                if has_r:
                    dx, dy, dz = rx1 - rx0, ry1 - ry0, rz1 - rz0
                    right_area[b - 1] = dx * dy + dy * dz + dz * dx
                    if use_inherit:
                        r_bounds[b - 1] = ((rx0, ry0, rz0), (rx1, ry1, rz1))
            lc = 0
            has_l = False
            lx0 = ly0 = lz0 = lx1 = ly1 = lz1 = 0
            for b in range(11):
                cnt = bcnt[b]
                if cnt:
                    lc += cnt
                    if not has_l:
                        lx0, ly0, lz0, lx1, ly1, lz1 = blx[b], bly[b], blz[b], bhx[b], bhy[b], bhz[b]
                        has_l = True
                    else:
                        if blx[b] < lx0: lx0 = blx[b]
                        if bly[b] < ly0: ly0 = bly[b]
                        if blz[b] < lz0: lz0 = blz[b]
                        if bhx[b] > lx1: lx1 = bhx[b]
                        if bhy[b] > ly1: ly1 = bhy[b]
                        if bhz[b] > lz1: lz1 = bhz[b]
                rc_s = right_cnt[b]
                if lc >= min_side and rc_s >= min_side:
                    dx, dy, dz = lx1 - lx0, ly1 - ly0, lz1 - lz0
                    larea = dx * dy + dy * dz + dz * dx
                    key = (lc * larea + rc_s * right_area[b], abs(lc - rc_s), axis, b + 1)
                    if best_cost is None or key < best_cost:
                        best_cost = key
                        best_axis = axis
                        best_split = b + 1
                        best_cmin = cmin
                        best_cspan = cspan
                        if use_inherit:
                            best_left_bounds = ((lx0, ly0, lz0), (lx1, ly1, lz1))
                            best_right_bounds = r_bounds[b]
            dt_s = time.perf_counter_ns() - ts0
            timers["prefix_suffix_sah_eval_ns"] += dt_s
            sub_ns += dt_s

        if best_axis >= 0:
            tp0 = time.perf_counter_ns()
            ck = 6 + best_axis
            left_ids = []
            right_ids = []
            if use_divfree:
                cut = best_cmin + (best_split * best_cspan + 11) // 12
                for idx in ids:
                    if flat_bounds[idx][ck] < cut:
                        left_ids.append(idx)
                    else:
                        right_ids.append(idx)
            else:
                for idx in ids:
                    b = ((flat_bounds[idx][ck] - best_cmin) * 12) // best_cspan
                    counters["partition_divisions"] += 1
                    if b > 11:
                        b = 11
                    if b < best_split:
                        left_ids.append(idx)
                    else:
                        right_ids.append(idx)
            dt_p = time.perf_counter_ns() - tp0
            timers["stable_partition_ns"] += dt_p
            sub_ns += dt_p
            if left_ids and right_ids:
                counters["sah_splits"] += 1
                timers["node_alloc_ns"] += (time.perf_counter_ns() - t_enter) - sub_ns
                lchild = _instrumented_sah_builder(
                    flat_bounds, budget, left_ids, leaf_size, depth + 1,
                    mode=mode, timers=timers, counters=counters,
                    known_bounds=best_left_bounds if use_inherit else None,
                )
                rchild = _instrumented_sah_builder(
                    flat_bounds, budget, right_ids, leaf_size, depth + 1,
                    mode=mode, timers=timers, counters=counters,
                    known_bounds=best_right_bounds if use_inherit else None,
                )
                t_post = time.perf_counter_ns()
                out_node = (lo, hi, n, None, lchild, rchild)
                timers["node_alloc_ns"] += time.perf_counter_ns() - t_post
                return out_node

    tm0 = time.perf_counter_ns()
    counters["median_fallbacks"] += 1
    dx, dy, dz = hx - lx, hy - ly, hz - lz
    axis = 0 if dx >= dy and dx >= dz else (1 if dy >= dz else 2)
    ck = 6 + axis
    ids.sort(key=lambda idx: (flat_bounds[idx][ck], idx))
    mid = n >> 1
    l_ids = ids[:mid]
    r_ids = ids[mid:]
    dt_m = time.perf_counter_ns() - tm0
    timers["median_fallback_ns"] += dt_m
    sub_ns += dt_m
    timers["node_alloc_ns"] += (time.perf_counter_ns() - t_enter) - sub_ns
    lchild = _instrumented_sah_builder(flat_bounds, budget, l_ids, leaf_size, depth + 1,
                                       mode=mode, timers=timers, counters=counters, known_bounds=None)
    rchild = _instrumented_sah_builder(flat_bounds, budget, r_ids, leaf_size, depth + 1,
                                       mode=mode, timers=timers, counters=counters, known_bounds=None)
    t_post = time.perf_counter_ns()
    out_node = (lo, hi, n, None, lchild, rchild)
    timers["node_alloc_ns"] += time.perf_counter_ns() - t_post
    return out_node


def profile_phases_single_pair(arm, left, right, *, builder_mode: str, direct_flat: bool = False) -> dict:
    """Separate instrumented pass measuring all 13 phase buckets without contaminating primary wall timing."""
    activate_arm(arm)
    sp = arm.sp
    timers = {
        "admission_and_vertex_prep_ns": 0,
        "bounds_materialization_and_flatten_ns": 0,
        "node_aabb_gather_ns": 0,
        "node_centroid_gather_ns": 0,
        "fused_stats_gather_ns": 0,
        "axis_histogram_build_ns": 0,
        "prefix_suffix_sah_eval_ns": 0,
        "stable_partition_ns": 0,
        "median_fallback_ns": 0,
        "node_alloc_ns": 0,
        "traversal_compile_ns": 0,
        "cache_translation_ns": 0,
        "heap_traverse_proj_narrow_ns": 0,
        "publication_ns": 0,
    }
    counters = {
        "nodes": 0,
        "leaves": 0,
        "max_depth": 0,
        "sah_splits": 0,
        "median_fallbacks": 0,
        "bin_divisions": 0,
        "partition_divisions": 0,
    }

    budget = sp._Work(NOOP, {})
    t0 = time.perf_counter_ns()
    records, topology = sp._admit((left, right), budget)
    origin, factor, prepared = sp._integer_frame(records, budget)
    t1 = time.perf_counter_ns()
    timers["admission_and_vertex_prep_ns"] += t1 - t0

    witness_pair = []
    budget.counts["witness_triangle_checks"] = 0
    is_linear = len(prepared[0]) * len(prepared[1]) <= sp.LINEAR_PAIR_LIMIT

    if is_linear:
        t_trav0 = time.perf_counter_ns()
        numerator, denominator, descriptor = sp._nearest_linear(prepared, budget, witness_pair)
        t_trav1 = time.perf_counter_ns()
        timers["heap_traverse_proj_narrow_ns"] += t_trav1 - t_trav0
    else:
        roots = []
        for triangles in prepared:
            budget.tick("tree_build_units", len(triangles))
            tf0 = time.perf_counter_ns()
            if direct_flat:
                flat_bounds = [None] * len(triangles)
                for row_idx, tri in enumerate(triangles):
                    b = tri[4]
                    ax, bx = b[0]
                    ay, by = b[1]
                    az, bz = b[2]
                    flat_bounds[row_idx] = (ax, ay, az, bx, by, bz, ax + bx, ay + by, az + bz)
            else:
                bounds = [(tuple(row[0] for row in tri[4]), tuple(row[1] for row in tri[4])) for tri in triangles]
                flat_bounds = [None] * len(bounds)
                for row_idx, (a, b) in enumerate(bounds):
                    ax, ay, az = a
                    bx, by, bz = b
                    flat_bounds[row_idx] = (ax, ay, az, bx, by, bz, ax + bx, ay + by, az + bz)
            tf1 = time.perf_counter_ns()
            timers["bounds_materialization_and_flatten_ns"] += tf1 - tf0
            budget.tick("tree_builds")
            root = _instrumented_sah_builder(
                flat_bounds, budget, list(range(len(flat_bounds))), 2, 0,
                mode=builder_mode, timers=timers, counters=counters,
            )
            roots.append(root)

        # Measure traversal compile + heap traversal separately (compile measured cleanly on roots below)
        t_trav0 = time.perf_counter_ns()
        numerator, denominator, descriptor = sp._nearest_tree(
            prepared, tuple(roots), budget, witness_pair, projection_mode="settled_credit_031_ref",
        )
        t_trav1 = time.perf_counter_ns()

    # Wait - fix recursive double count on _compile_bvh_node:
    # Let's avoid double-counting by restoring wrapped compile with a depth guard in the helper below.
    tp0 = time.perf_counter_ns()
    distance_m = sp._rounded_distance(numerator, denominator, factor)
    pts = sp._witness(descriptor)
    published = sp._publish_points(pts, origin, factor, distance_m, include_exact=True)
    _ = sp._exact_distance_key(numerator, denominator, factor)
    if published is not None and len(witness_pair) == 2:
        _ = sp._witness_triangle_provenance(
            published[0], published[1], pts, list(witness_pair), prepared, origin, factor, budget,
        )
    tp1 = time.perf_counter_ns()
    timers["publication_ns"] += tp1 - tp0

    # Because _compile_bvh_node recurses, re-measure pure compile once cleanly on roots if non-linear:
    if not is_linear:
        largest_span = max(max(a, b) - min(c, d)
                           for a, b, c, d in zip(roots[0][1], roots[1][1], roots[0][0], roots[1][0]))
        center_shift = max(0, largest_span.bit_length() - (sp.MAX_BITS - 4))
        tc0 = time.perf_counter_ns()
        _ = sp._compile_bvh_node(roots[0], center_shift, budget=None)
        _ = sp._compile_bvh_node(roots[1], center_shift, budget=None)
        pure_compile_ns = time.perf_counter_ns() - tc0
        # t_trav1 - t_trav0 included non-recursive wrapped_compile if compiled via _nearest_tree; adjust cleanly:
        timers["traversal_compile_ns"] = pure_compile_ns
        timers["heap_traverse_proj_narrow_ns"] = max(0, (t_trav1 - t_trav0) - pure_compile_ns)

    build_total_ns = (
        timers["bounds_materialization_and_flatten_ns"]
        + timers["node_aabb_gather_ns"]
        + timers["node_centroid_gather_ns"]
        + timers["fused_stats_gather_ns"]
        + timers["axis_histogram_build_ns"]
        + timers["prefix_suffix_sah_eval_ns"]
        + timers["stable_partition_ns"]
        + timers["median_fallback_ns"]
        + timers["node_alloc_ns"]
    )
    out = {k.replace("_ns", "_ms"): round(v / 1e6, 4) for k, v in timers.items()}
    out["build_pipeline_total_ms"] = round(build_total_ns / 1e6, 4)
    out["instrumented_total_ms"] = round((
        timers["admission_and_vertex_prep_ns"]
        + build_total_ns
        + timers["traversal_compile_ns"]
        + timers["cache_translation_ns"]
        + timers["heap_traverse_proj_narrow_ns"]
        + timers["publication_ns"]
    ) / 1e6, 4)
    out["counters"] = counters
    out["work"] = _work_summary(budget.counts)
    return out


def profile_cached_batch_translation(arm, target, peers) -> dict:
    """Measure cache_translation separately on the secondary cached deep-tuple batch."""
    activate_arm(arm)
    sp = arm.sp
    cache = {}
    t_translate_ns = 0
    orig_tb = sp._translate_bvh
    orig_tt = sp._translate_triangles

    def w_tb(*args, **kwargs):
        nonlocal t_translate_ns
        t0 = time.perf_counter_ns()
        r = orig_tb(*args, **kwargs)
        t_translate_ns += time.perf_counter_ns() - t0
        return r

    def w_tt(*args, **kwargs):
        nonlocal t_translate_ns
        t0 = time.perf_counter_ns()
        r = orig_tt(*args, **kwargs)
        t_translate_ns += time.perf_counter_ns() - t0
        return r

    sp._translate_bvh = w_tb
    sp._translate_triangles = w_tt
    try:
        agg = {}
        t_tot0 = time.perf_counter_ns()
        for p in peers:
            r = sp.measure_surface_proximity(target, p, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _mesh_cache=cache)
            for k, v in _work_summary(r["work"]).items():
                if isinstance(v, int):
                    agg[k] = agg.get(k, 0) + v
        t_tot1 = time.perf_counter_ns()
    finally:
        sp._translate_bvh = orig_tb
        sp._translate_triangles = orig_tt

    return {
        "total_instrumented_ms": round((t_tot1 - t_tot0) / 1e6, 4),
        "cache_translation_ms": round(t_translate_ns / 1e6, 4),
        "work_agg": agg,
    }


def ensure_frozen_arm_a() -> Path:
    """Materialize frozen 119327bbb runtime into scratch/042_arms/arm_a_frozen if missing."""
    arm_a = ARMS_ROOT / "arm_a_frozen"
    marker = arm_a / "human_eye_plugin/surface_proximity.py"
    if marker.exists():
        return arm_a
    import io
    import subprocess
    import tarfile
    arm_a.mkdir(parents=True, exist_ok=True)
    paths = [
        "pyproject.toml",
        "human_eye_hook.py",
        "human_eye_foveated_renderer.py",
        "native_3d_spatial_scratchpad.py",
        "module_2_low_token_mcp_scene_bridge.py",
        "module_3_1_mcp_protocol_ipc_engine.py",
        "module_3_2_vlm_grounding_closed_loop_agent.py",
        "module_3_3_closed_loop_control_engine.py",
        "human_eye_plugin",
        "human_eye_module1_operators",
    ]
    proc = subprocess.run(
        ["git", "archive", "--format=tar", FROZEN_COMMIT, "--", *paths],
        cwd=str(ROOT), check=True, stdout=subprocess.PIPE,
    )
    with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode="r:") as tf:
        tf.extractall(path=arm_a)
    _require(marker.exists(), f"Failed to extract frozen commit {FROZEN_COMMIT} into {arm_a}")
    return arm_a


def make_variant_arms_from_frozen() -> dict[str, Path]:
    """Create Arms B (B1 only), C (B2 only), D (B1+B2), E (D+B3), F (D+B4) in scratch/042_arms."""
    arm_a = ensure_frozen_arm_a()
    _require((arm_a / "human_eye_plugin/surface_geometry.py").exists(), "Arm A snapshot missing")

    def clone_from_a(arm_dir_name: str) -> Path:
        dst = ARMS_ROOT / arm_dir_name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(arm_a, dst)
        return dst

    # Arm B: B1 fused exact node statistics only
    arm_b = clone_from_a("arm_b_b1_only")
    _patch_b1(arm_b / "human_eye_plugin/surface_geometry.py")

    # Arm C: B2 exact division-free stable partition only
    arm_c = clone_from_a("arm_c_b2_only")
    _patch_b2(arm_c / "human_eye_plugin/surface_geometry.py")

    # Arm D: B1 + B2 combined
    arm_d = clone_from_a("arm_d_b1_b2")
    _patch_b1_b2(arm_d / "human_eye_plugin/surface_geometry.py")

    # Arm E: D + B3 inherited winning SAH child bounds
    arm_e = clone_from_a("arm_e_b1_b2_b3")
    _patch_b1_b2_b3(arm_e / "human_eye_plugin/surface_geometry.py")

    # Arm F: D + B4 native flat-bounds builder + direct proximity feed (no nested bounds)
    arm_f = clone_from_a("arm_f_b1_b2_b4")
    _patch_b1_b2(arm_f / "human_eye_plugin/surface_geometry.py")
    _patch_b4(arm_f / "human_eye_plugin/surface_geometry.py", arm_f / "human_eye_plugin/surface_proximity.py")

    return {
        "A": arm_a,
        "B": arm_b,
        "C": arm_c,
        "D": arm_d,
        "E": arm_e,
        "F": arm_f,
    }


def _replace_sah_builder(sg_path: Path, new_src: str) -> None:
    text = sg_path.read_text(encoding="utf-8")
    start_marker = "\n\ndef _build_sah_bvh(flat_bounds, budget, ids, leaf_size, depth):"
    end_marker = "\n\ndef _bvh_median(bounds, budget, ids=None, *, leaf_size=4):"
    i0 = text.index(start_marker)
    i1 = text.index(end_marker)
    updated = text[:i0] + "\n\n" + new_src.strip() + text[i1:]
    sg_path.write_text(updated, encoding="utf-8")


B1_FUNC = '''def _build_sah_bvh(flat_bounds, budget, ids, leaf_size, depth):
    n = len(ids)
    budget.consume(1 + n, 'surface_bvh_build')
    if n == 1:
        r = flat_bounds[ids[0]]
        return ((r[0], r[1], r[2]), (r[3], r[4], r[5]), 1, ids, None, None)
    if n == 2 and leaf_size >= 2:
        r0, r1 = flat_bounds[ids[0]], flat_bounds[ids[1]]
        return (
            (r0[0] if r0[0] <= r1[0] else r1[0], r0[1] if r0[1] <= r1[1] else r1[1], r0[2] if r0[2] <= r1[2] else r1[2]),
            (r0[3] if r0[3] >= r1[3] else r1[3], r0[4] if r0[4] >= r1[4] else r1[4], r0[5] if r0[5] >= r1[5] else r1[5]),
            2, ids, None, None,
        )
    first = flat_bounds[ids[0]]
    sah_eligible = (n > leaf_size and n > _SAH_MIN_N and depth < _SAH_MAX_DEPTH)
    cp = getattr(budget, 'checkpoint', None) if n >= 512 else None
    if sah_eligible:
        lx, ly, lz, hx, hy, hz, c0x, c0y, c0z = first
        c1x, c1y, c1z = c0x, c0y, c0z
        if cp is None:
            for idx in ids[1:]:
                r0, r1, r2, r3, r4, r5, cx, cy, cz = flat_bounds[idx]
                if r0 < lx: lx = r0
                if r1 < ly: ly = r1
                if r2 < lz: lz = r2
                if r3 > hx: hx = r3
                if r4 > hy: hy = r4
                if r5 > hz: hz = r5
                if cx < c0x: c0x = cx
                elif cx > c1x: c1x = cx
                if cy < c0y: c0y = cy
                elif cy > c1y: c1y = cy
                if cz < c0z: c0z = cz
                elif cz > c1z: c1z = cz
        else:
            for start in range(1, n, 256):
                cp('surface_proximity_surface_bvh_build')
                for idx in ids[start:start + 256]:
                    r0, r1, r2, r3, r4, r5, cx, cy, cz = flat_bounds[idx]
                    if r0 < lx: lx = r0
                    if r1 < ly: ly = r1
                    if r2 < lz: lz = r2
                    if r3 > hx: hx = r3
                    if r4 > hy: hy = r4
                    if r5 > hz: hz = r5
                    if cx < c0x: c0x = cx
                    elif cx > c1x: c1x = cx
                    if cy < c0y: c0y = cy
                    elif cy > c1y: c1y = cy
                    if cz < c0z: c0z = cz
                    elif cz > c1z: c1z = cz
    else:
        lx, ly, lz, hx, hy, hz = first[0], first[1], first[2], first[3], first[4], first[5]
        for idx in ids[1:]:
            row = flat_bounds[idx]
            if row[0] < lx: lx = row[0]
            if row[1] < ly: ly = row[1]
            if row[2] < lz: lz = row[2]
            if row[3] > hx: hx = row[3]
            if row[4] > hy: hy = row[4]
            if row[5] > hz: hz = row[5]
    lo = (lx, ly, lz)
    hi = (hx, hy, hz)
    if n <= leaf_size:
        return (lo, hi, n, ids, None, None)
    if sah_eligible:
        best_cost = None
        best_axis = -1
        best_split = 0
        best_cmin = 0
        best_cspan = 1
        min_side = max(1, n >> 4)
        cbounds = ((c0x, c1x), (c0y, c1y), (c0z, c1z))
        for axis in (0, 1, 2):
            cmin, cmax = cbounds[axis]
            if cmax <= cmin:
                continue
            cspan = cmax - cmin
            bcnt = [0] * _SAH_BINS
            blx = [0] * _SAH_BINS
            bly = [0] * _SAH_BINS
            blz = [0] * _SAH_BINS
            bhx = [0] * _SAH_BINS
            bhy = [0] * _SAH_BINS
            bhz = [0] * _SAH_BINS
            ck = 6 + axis
            max_bin = _SAH_BINS - 1
            for idx in ids:
                row = flat_bounds[idx]
                b = ((row[ck] - cmin) * _SAH_BINS) // cspan
                if b > max_bin:
                    b = max_bin
                c = bcnt[b]
                if c == 0:
                    blx[b], bly[b], blz[b], bhx[b], bhy[b], bhz[b] = row[0], row[1], row[2], row[3], row[4], row[5]
                else:
                    if row[0] < blx[b]: blx[b] = row[0]
                    if row[1] < bly[b]: bly[b] = row[1]
                    if row[2] < blz[b]: blz[b] = row[2]
                    if row[3] > bhx[b]: bhx[b] = row[3]
                    if row[4] > bhy[b]: bhy[b] = row[4]
                    if row[5] > bhz[b]: bhz[b] = row[5]
                bcnt[b] = c + 1
            right_area = [0] * _SAH_BINS
            right_cnt = [0] * _SAH_BINS
            rc = 0
            has_r = False
            rx0 = ry0 = rz0 = rx1 = ry1 = rz1 = 0
            for b in range(_SAH_BINS - 1, 0, -1):
                cnt = bcnt[b]
                if cnt:
                    rc += cnt
                    if not has_r:
                        rx0, ry0, rz0, rx1, ry1, rz1 = blx[b], bly[b], blz[b], bhx[b], bhy[b], bhz[b]
                        has_r = True
                    else:
                        if blx[b] < rx0: rx0 = blx[b]
                        if bly[b] < ry0: ry0 = bly[b]
                        if blz[b] < rz0: rz0 = blz[b]
                        if bhx[b] > rx1: rx1 = bhx[b]
                        if bhy[b] > ry1: ry1 = bhy[b]
                        if bhz[b] > rz1: rz1 = bhz[b]
                right_cnt[b - 1] = rc
                if has_r:
                    dx, dy, dz = rx1 - rx0, ry1 - ry0, rz1 - rz0
                    right_area[b - 1] = dx * dy + dy * dz + dz * dx
            lc = 0
            has_l = False
            lx0 = ly0 = lz0 = lx1 = ly1 = lz1 = 0
            for b in range(_SAH_BINS - 1):
                cnt = bcnt[b]
                if cnt:
                    lc += cnt
                    if not has_l:
                        lx0, ly0, lz0, lx1, ly1, lz1 = blx[b], bly[b], blz[b], bhx[b], bhy[b], bhz[b]
                        has_l = True
                    else:
                        if blx[b] < lx0: lx0 = blx[b]
                        if bly[b] < ly0: ly0 = bly[b]
                        if blz[b] < lz0: lz0 = blz[b]
                        if bhx[b] > lx1: lx1 = bhx[b]
                        if bhy[b] > ly1: bhy[b] = ly1  # NO! Fix below
''''''
'''


def _patch_b1(sg_path: Path) -> None:
    text = sg_path.read_text(encoding="utf-8")
    # Surgical replacement of lines 156..183 keeping exact prefix/suffix/partition code
    old_block = """    first = flat_bounds[ids[0]]
    lx, ly, lz, hx, hy, hz = first[0], first[1], first[2], first[3], first[4], first[5]
    for idx in ids[1:]:
        row = flat_bounds[idx]
        if row[0] < lx: lx = row[0]
        if row[1] < ly: ly = row[1]
        if row[2] < lz: lz = row[2]
        if row[3] > hx: hx = row[3]
        if row[4] > hy: hy = row[4]
        if row[5] > hz: hz = row[5]
    lo = (lx, ly, lz)
    hi = (hx, hy, hz)
    if n <= leaf_size:
        return (lo, hi, n, ids, None, None)
    if n > _SAH_MIN_N and depth < _SAH_MAX_DEPTH:
        c0x = c1x = first[6]
        c0y = c1y = first[7]
        c0z = c1z = first[8]
        for idx in ids[1:]:
            row = flat_bounds[idx]
            cx, cy, cz = row[6], row[7], row[8]
            if cx < c0x: c0x = cx
            elif cx > c1x: c1x = cx
            if cy < c0y: c0y = cy
            elif cy > c1y: c1y = cy
            if cz < c0z: c0z = cz
            elif cz > c1z: c1z = cz"""
    new_block = """    first = flat_bounds[ids[0]]
    sah_eligible = (n > leaf_size and n > _SAH_MIN_N and depth < _SAH_MAX_DEPTH)
    cp = getattr(budget, 'checkpoint', None) if n >= 512 else None
    if sah_eligible:
        lx, ly, lz, hx, hy, hz, c0x, c0y, c0z = first
        c1x, c1y, c1z = c0x, c0y, c0z
        if cp is None:
            for idx in ids[1:]:
                r0, r1, r2, r3, r4, r5, cx, cy, cz = flat_bounds[idx]
                if r0 < lx: lx = r0
                if r1 < ly: ly = r1
                if r2 < lz: lz = r2
                if r3 > hx: hx = r3
                if r4 > hy: hy = r4
                if r5 > hz: hz = r5
                if cx < c0x: c0x = cx
                elif cx > c1x: c1x = cx
                if cy < c0y: c0y = cy
                elif cy > c1y: c1y = cy
                if cz < c0z: c0z = cz
                elif cz > c1z: c1z = cz
        else:
            for start in range(1, n, 256):
                cp('surface_proximity_surface_bvh_build')
                for idx in ids[start:start + 256]:
                    r0, r1, r2, r3, r4, r5, cx, cy, cz = flat_bounds[idx]
                    if r0 < lx: lx = r0
                    if r1 < ly: ly = r1
                    if r2 < lz: lz = r2
                    if r3 > hx: hx = r3
                    if r4 > hy: hy = r4
                    if r5 > hz: hz = r5
                    if cx < c0x: c0x = cx
                    elif cx > c1x: c1x = cx
                    if cy < c0y: c0y = cy
                    elif cy > c1y: c1y = cy
                    if cz < c0z: c0z = cz
                    elif cz > c1z: c1z = cz
    else:
        lx, ly, lz, hx, hy, hz = first[0], first[1], first[2], first[3], first[4], first[5]
        for idx in ids[1:]:
            row = flat_bounds[idx]
            if row[0] < lx: lx = row[0]
            if row[1] < ly: ly = row[1]
            if row[2] < lz: lz = row[2]
            if row[3] > hx: hx = row[3]
            if row[4] > hy: hy = row[4]
            if row[5] > hz: hz = row[5]
    lo = (lx, ly, lz)
    hi = (hx, hy, hz)
    if n <= leaf_size:
        return (lo, hi, n, ids, None, None)
    if sah_eligible:"""
    _require(old_block in text, "old_block missing in _patch_b1")
    sg_path.write_text(text.replace(old_block, new_block, 1), encoding="utf-8")


def _patch_b2(sg_path: Path) -> None:
    text = sg_path.read_text(encoding="utf-8")
    old_part = """        if best_axis >= 0:
            ck = 6 + best_axis
            left_ids = []
            right_ids = []
            max_bin = _SAH_BINS - 1
            for idx in ids:
                b = ((flat_bounds[idx][ck] - best_cmin) * _SAH_BINS) // best_cspan
                if b > max_bin:
                    b = max_bin
                if b < best_split:
                    left_ids.append(idx)
                else:
                    right_ids.append(idx)"""
    new_part = """        if best_axis >= 0:
            ck = 6 + best_axis
            cut = best_cmin + (best_split * best_cspan + _SAH_BINS - 1) // _SAH_BINS
            left_ids = []
            right_ids = []
            append_l = left_ids.append
            append_r = right_ids.append
            cp_p = getattr(budget, 'checkpoint', None) if n >= 512 else None
            if cp_p is None:
                for idx in ids:
                    if flat_bounds[idx][ck] < cut:
                        append_l(idx)
                    else:
                        append_r(idx)
            else:
                for start in range(0, n, 256):
                    cp_p('surface_proximity_surface_bvh_build')
                    for idx in ids[start:start + 256]:
                        if flat_bounds[idx][ck] < cut:
                            append_l(idx)
                        else:
                            append_r(idx)"""
    _require(old_part in text, "old_part missing in _patch_b2")
    sg_path.write_text(text.replace(old_part, new_part, 1), encoding="utf-8")


def _patch_b1_b2(sg_path: Path) -> None:
    _patch_b1(sg_path)
    _patch_b2(sg_path)


def _patch_b1_b2_b3(sg_path: Path) -> None:
    text = sg_path.read_text(encoding="utf-8")
    start_marker = "def _build_sah_bvh(flat_bounds, budget, ids, leaf_size, depth):"
    end_marker = "\n\ndef _bvh_median(bounds, budget, ids=None, *, leaf_size=4):"
    i0 = text.index(start_marker)
    i1 = text.index(end_marker)
    new_func = """def _build_sah_bvh(flat_bounds, budget, ids, leaf_size, depth, known_bounds=None):
    n = len(ids)
    budget.consume(1 + n, 'surface_bvh_build')
    if n == 1:
        if known_bounds is not None:
            return (known_bounds[0], known_bounds[1], 1, ids, None, None)
        r = flat_bounds[ids[0]]
        return ((r[0], r[1], r[2]), (r[3], r[4], r[5]), 1, ids, None, None)
    if known_bounds is None and n == 2 and leaf_size >= 2:
        r0, r1 = flat_bounds[ids[0]], flat_bounds[ids[1]]
        return (
            (r0[0] if r0[0] <= r1[0] else r1[0], r0[1] if r0[1] <= r1[1] else r1[1], r0[2] if r0[2] <= r1[2] else r1[2]),
            (r0[3] if r0[3] >= r1[3] else r1[3], r0[4] if r0[4] >= r1[4] else r1[4], r0[5] if r0[5] >= r1[5] else r1[5]),
            2, ids, None, None,
        )
    sah_eligible = (n > leaf_size and n > _SAH_MIN_N and depth < _SAH_MAX_DEPTH)
    if known_bounds is not None:
        lo, hi = known_bounds
        lx, ly, lz = lo
        hx, hy, hz = hi
        if n <= leaf_size:
            return (lo, hi, n, ids, None, None)
        if sah_eligible:
            first = flat_bounds[ids[0]]
            c0x = c1x = first[6]
            c0y = c1y = first[7]
            c0z = c1z = first[8]
            for idx in ids[1:]:
                row = flat_bounds[idx]
                cx, cy, cz = row[6], row[7], row[8]
                if cx < c0x: c0x = cx
                elif cx > c1x: c1x = cx
                if cy < c0y: c0y = cy
                elif cy > c1y: c1y = cy
                if cz < c0z: c0z = cz
                elif cz > c1z: c1z = cz
    else:
        first = flat_bounds[ids[0]]
        if sah_eligible:
            lx, ly, lz, hx, hy, hz, c0x, c0y, c0z = first
            c1x, c1y, c1z = c0x, c0y, c0z
            for idx in ids[1:]:
                r0, r1, r2, r3, r4, r5, cx, cy, cz = flat_bounds[idx]
                if r0 < lx: lx = r0
                if r1 < ly: ly = r1
                if r2 < lz: lz = r2
                if r3 > hx: hx = r3
                if r4 > hy: hy = r4
                if r5 > hz: hz = r5
                if cx < c0x: c0x = cx
                elif cx > c1x: c1x = cx
                if cy < c0y: c0y = cy
                elif cy > c1y: c1y = cy
                if cz < c0z: c0z = cz
                elif cz > c1z: c1z = cz
        else:
            lx, ly, lz, hx, hy, hz = first[0], first[1], first[2], first[3], first[4], first[5]
            for idx in ids[1:]:
                row = flat_bounds[idx]
                if row[0] < lx: lx = row[0]
                if row[1] < ly: ly = row[1]
                if row[2] < lz: lz = row[2]
                if row[3] > hx: hx = row[3]
                if row[4] > hy: hy = row[4]
                if row[5] > hz: hz = row[5]
        lo = (lx, ly, lz)
        hi = (hx, hy, hz)
        if n <= leaf_size:
            return (lo, hi, n, ids, None, None)
    if sah_eligible:
        best_cost = None
        best_axis = -1
        best_split = 0
        best_cmin = 0
        best_cspan = 1
        best_left_bounds = None
        best_right_bounds = None
        min_side = max(1, n >> 4)
        cbounds = ((c0x, c1x), (c0y, c1y), (c0z, c1z))
        for axis in (0, 1, 2):
            cmin, cmax = cbounds[axis]
            if cmax <= cmin:
                continue
            cspan = cmax - cmin
            bcnt = [0] * _SAH_BINS
            blx = [0] * _SAH_BINS
            bly = [0] * _SAH_BINS
            blz = [0] * _SAH_BINS
            bhx = [0] * _SAH_BINS
            bhy = [0] * _SAH_BINS
            bhz = [0] * _SAH_BINS
            ck = 6 + axis
            max_bin = _SAH_BINS - 1
            for idx in ids:
                row = flat_bounds[idx]
                b = ((row[ck] - cmin) * _SAH_BINS) // cspan
                if b > max_bin:
                    b = max_bin
                c = bcnt[b]
                if c == 0:
                    blx[b], bly[b], blz[b], bhx[b], bhy[b], bhz[b] = row[0], row[1], row[2], row[3], row[4], row[5]
                else:
                    if row[0] < blx[b]: blx[b] = row[0]
                    if row[1] < bly[b]: bly[b] = row[1]
                    if row[2] < blz[b]: blz[b] = row[2]
                    if row[3] > bhx[b]: bhx[b] = row[3]
                    if row[4] > bhy[b]: bhy[b] = row[4]
                    if row[5] > bhz[b]: bhz[b] = row[5]
                bcnt[b] = c + 1
            right_area = [0] * _SAH_BINS
            right_cnt = [0] * _SAH_BINS
            r_bounds = [None] * _SAH_BINS
            rc = 0
            has_r = False
            rx0 = ry0 = rz0 = rx1 = ry1 = rz1 = 0
            for b in range(_SAH_BINS - 1, 0, -1):
                cnt = bcnt[b]
                if cnt:
                    rc += cnt
                    if not has_r:
                        rx0, ry0, rz0, rx1, ry1, rz1 = blx[b], bly[b], blz[b], bhx[b], bhy[b], bhz[b]
                        has_r = True
                    else:
                        if blx[b] < rx0: rx0 = blx[b]
                        if bly[b] < ry0: ry0 = bly[b]
                        if blz[b] < rz0: rz0 = blz[b]
                        if bhx[b] > rx1: rx1 = bhx[b]
                        if bhy[b] > ry1: ry1 = bhy[b]
                        if bhz[b] > rz1: rz1 = bhz[b]
                right_cnt[b - 1] = rc
                if has_r:
                    dx, dy, dz = rx1 - rx0, ry1 - ry0, rz1 - rz0
                    right_area[b - 1] = dx * dy + dy * dz + dz * dx
                    r_bounds[b - 1] = ((rx0, ry0, rz0), (rx1, ry1, rz1))
            lc = 0
            has_l = False
            lx0 = ly0 = lz0 = lx1 = ly1 = lz1 = 0
            for b in range(_SAH_BINS - 1):
                cnt = bcnt[b]
                if cnt:
                    lc += cnt
                    if not has_l:
                        lx0, ly0, lz0, lx1, ly1, lz1 = blx[b], bly[b], blz[b], bhx[b], bhy[b], bhz[b]
                        has_l = True
                    else:
                        if blx[b] < lx0: lx0 = blx[b]
                        if bly[b] < ly0: ly0 = bly[b]
                        if blz[b] < lz0: lz0 = blz[b]
                        if bhx[b] > lx1: lx1 = bhx[b]
                        if bhy[b] > ly1: bhy[b] = bhy[b]
                        if bhz[b] > lz1: lz1 = bhz[b]
                rc_s = right_cnt[b]
                if lc >= min_side and rc_s >= min_side:
                    dx, dy, dz = lx1 - lx0, ly1 - ly0, lz1 - lz0
                    larea = dx * dy + dy * dz + dz * dx
                    key = (lc * larea + rc_s * right_area[b], abs(lc - rc_s), axis, b + 1)
                    if best_cost is None or key < best_cost:
                        best_cost = key
                        best_axis = axis
                        best_split = b + 1
                        best_cmin = cmin
                        best_cspan = cspan
                        best_left_bounds = ((lx0, ly0, lz0), (lx1, ly1, lz1))
                        best_right_bounds = r_bounds[b]
        if best_axis >= 0:
            ck = 6 + best_axis
            cut = best_cmin + (best_split * best_cspan + _SAH_BINS - 1) // _SAH_BINS
            left_ids = []
            right_ids = []
            append_l = left_ids.append
            append_r = right_ids.append
            for idx in ids:
                if flat_bounds[idx][ck] < cut:
                    append_l(idx)
                else:
                    append_r(idx)
            if left_ids and right_ids:
                return (
                    lo, hi, n, None,
                    _build_sah_bvh(flat_bounds, budget, left_ids, leaf_size, depth + 1, best_left_bounds),
                    _build_sah_bvh(flat_bounds, budget, right_ids, leaf_size, depth + 1, best_right_bounds),
                )
    dx, dy, dz = hx - lx, hy - ly, hz - lz
    axis = 0 if dx >= dy and dx >= dz else (1 if dy >= dz else 2)
    ck = 6 + axis
    ids.sort(key=lambda idx: (flat_bounds[idx][ck], idx))
    mid = n >> 1
    return (
        lo, hi, n, None,
        _build_sah_bvh(flat_bounds, budget, ids[:mid], leaf_size, depth + 1, None),
        _build_sah_bvh(flat_bounds, budget, ids[mid:], leaf_size, depth + 1, None),
    )"""
    # Fix typo in bhy line above cleanly
    new_func = new_func.replace("if bhy[b] > ly1: bhy[b] = bhy[b]", "if bhy[b] > ly1: ly1 = bhy[b]")
    sg_path.write_text(text[:i0] + new_func + text[i1:], encoding="utf-8")


def _patch_b4(sg_path: Path, sp_path: Path) -> None:
    sg_text = sg_path.read_text(encoding="utf-8")
    old_bvh = """def _bvh(bounds,budget,ids=None,*,leaf_size=4):
    ids=list(range(len(bounds))) if ids is None else list(ids)
    if not ids:
        budget.consume(1,'surface_bvh_build')
        return ((0,0,0),(0,0,0),0,[],None,None)
    flat_bounds=[None]*len(bounds)
    for row_idx,row in enumerate(bounds):
        a,b=row
        ax,ay,az=a;bx,by,bz=b
        flat_bounds[row_idx]=(ax,ay,az,bx,by,bz,ax+bx,ay+by,az+bz)
    return _build_sah_bvh(flat_bounds,budget,ids,leaf_size,0)"""
    new_bvh = old_bvh + """


def _bvh_from_flat_bounds(flat_bounds, budget, ids=None, *, leaf_size=4):
    ids = list(range(len(flat_bounds))) if ids is None else list(ids)
    if not ids:
        budget.consume(1, 'surface_bvh_build')
        return ((0, 0, 0), (0, 0, 0), 0, [], None, None)
    return _build_sah_bvh(flat_bounds, budget, ids, leaf_size, 0)"""
    _require(old_bvh in sg_text, "old_bvh missing in _patch_b4")
    sg_path.write_text(sg_text.replace(old_bvh, new_bvh, 1), encoding="utf-8")

    sp_text = sp_path.read_text(encoding="utf-8")
    old_dr = """def _distance_roots(prepared, budget, holder=None):
    from .surface_geometry import _bvh
    roots = []
    retained_bounds = [] if holder is not None else None
    for triangles in prepared:
        budget.tick('tree_build_units', len(triangles))
        bounds = [(tuple(row[0] for row in triangle[4]), tuple(row[1] for row in triangle[4]))
                  for triangle in triangles]
        budget.tick('tree_builds')
        roots.append(_bvh(bounds, budget, leaf_size=2))
        if retained_bounds is not None:
            retained_bounds.append(bounds)"""
    new_dr = """def _distance_roots(prepared, budget, holder=None):
    from .surface_geometry import _bvh_from_flat_bounds
    roots = []
    retained_bounds = [] if holder is not None else None
    for triangles in prepared:
        n_tris = len(triangles)
        budget.tick('tree_build_units', n_tris)
        flat_bounds = [None] * n_tris
        if retained_bounds is None:
            for row_idx, triangle in enumerate(triangles):
                b = triangle[4]
                ax, bx = b[0]
                ay, by = b[1]
                az, bz = b[2]
                flat_bounds[row_idx] = (ax, ay, az, bx, by, bz, ax + bx, ay + by, az + bz)
        else:
            bounds = [None] * n_tris
            for row_idx, triangle in enumerate(triangles):
                b = triangle[4]
                ax, bx = b[0]
                ay, by = b[1]
                az, bz = b[2]
                bounds[row_idx] = ((ax, ay, az), (bx, by, bz))
                flat_bounds[row_idx] = (ax, ay, az, bx, by, bz, ax + bx, ay + by, az + bz)
            retained_bounds.append(bounds)
        budget.tick('tree_builds')
        roots.append(_bvh_from_flat_bounds(flat_bounds, budget, leaf_size=2))"""
    _require(old_dr in sp_text, "old_dr missing in _patch_b4")
    sp_text = sp_text.replace(old_dr, new_dr, 1)

    old_cache_build = """        from .surface_geometry import _bvh
        out_roots = []
        for ent, n_faces, dS, sx, sy, sz in (
            (el, nl, dL, 0, 0, 0),
            (er, nr, dR, tx, ty, tz),
        ):
            budget.tick('tree_build_units', n_faces)
            budget.tick('tree_builds', 1)
            tree_entry = ent.get('tree')
            if tree_entry is None:
                local_bounds = [((t[4][0][0], t[4][1][0], t[4][2][0]),
                                 (t[4][0][1], t[4][1][1], t[4][2][1])) for t in ent['local_tris']]
                b_proxy = _CacheBuildBudget(budget)
                local_root = _bvh(local_bounds, b_proxy, leaf_size=2)"""
    new_cache_build = """        from .surface_geometry import _bvh_from_flat_bounds
        out_roots = []
        for ent, n_faces, dS, sx, sy, sz in (
            (el, nl, dL, 0, 0, 0),
            (er, nr, dR, tx, ty, tz),
        ):
            budget.tick('tree_build_units', n_faces)
            budget.tick('tree_builds', 1)
            tree_entry = ent.get('tree')
            if tree_entry is None:
                local_tris = ent['local_tris']
                local_flat = [None] * len(local_tris)
                for row_idx, t in enumerate(local_tris):
                    b = t[4]
                    ax, bx = b[0]
                    ay, by = b[1]
                    az, bz = b[2]
                    local_flat[row_idx] = (ax, ay, az, bx, by, bz, ax + bx, ay + by, az + bz)
                b_proxy = _CacheBuildBudget(budget)
                local_root = _bvh_from_flat_bounds(local_flat, b_proxy, leaf_size=2)"""
    _require(old_cache_build in sp_text, "old_cache_build missing in _patch_b4")
    sp_path.write_text(sp_text.replace(old_cache_build, new_cache_build, 1), encoding="utf-8")


def _build_cases_manifest(workloads: dict, arm_a) -> dict:
    return {
        "schema": "m3-bvh-kernel-042-cases-v1",
        "frozen_reference_commit": FROZEN_COMMIT,
        "verified_runtime_source_sha256": arm_a.source_sha256,
        "frozen_surface_proximity_file_sha256": arm_a.sp_file_sha256,
        "frozen_surface_geometry_file_sha256": arm_a.sg_file_sha256,
        "options": workloads["options"],
        "options_sha256": workloads["options_sha256"],
        "source_assets": workloads["source_assets"],
        "workloads": {
            "singles": [
                {
                    "id": w["id"],
                    "classification": w["classification"],
                    "role": w["role"],
                    "left_faces": w["left_faces"],
                    "right_faces": w["right_faces"],
                    "input_sha256": w["input_sha256"],
                }
                for w in workloads["singles"]
            ],
            "batches": [
                {
                    "id": w["id"],
                    "classification": w["classification"],
                    "pair_count": w["pair_count"],
                    "peer_ids": w["peer_ids"],
                    "target_faces": w["target_faces"],
                    "peer_faces_total": w["peer_faces_total"],
                    "input_sha256": w["input_sha256"],
                }
                for w in workloads["batches"]
            ],
        },
        "historical_inputs_missing": {
            "zero489": "MISSING_HISTORICAL_INPUT",
            "first_yield": "MISSING_HISTORICAL_INPUT",
            "pair129": "MISSING_HISTORICAL_INPUT",
            "original_040_closed_solid_48F_ordering": "MISSING_HISTORICAL_INPUT",
        },
    }


def _evaluate_arms(arm_objs: list, workloads: dict, *, warmup: int, repeats: int, measure_s0_for: dict | None = None) -> dict:
    """Run paired uninstrumented timing + tree & signature checks across all arm_objs."""
    arm_a = arm_objs[0]
    singles_out = {}

    for w in workloads["singles"]:
        wid = w["id"]
        l_tup, r_tup = w["tuple_pair"]
        l_np, r_np = w["ndarray_pair"]

        # 1. Verify complete raw-tree equivalence vs Arm A (skip linear bypass if desired, check anyway)
        trees_a = measure_raw_trees_for_arm(arm_a, l_tup, r_tup)
        tree_digests = {"A": trees_a["combined_tree_sha256"], "struct": {"left": {k: v for k, v in trees_a["left"].items() if k != "tree_sha256"}, "right": {k: v for k, v in trees_a["right"].items() if k != "tree_sha256"}}}
        for arm in arm_objs[1:]:
            trees_x = measure_raw_trees_for_arm(arm, l_tup, r_tup)
            assert_raw_trees_equal(trees_a["roots"][0], trees_x["roots"][0], f"{wid}.{arm.name}.L")
            assert_raw_trees_equal(trees_a["roots"][1], trees_x["roots"][1], f"{wid}.{arm.name}.R")
            _require(trees_a["combined_tree_sha256"] == trees_x["combined_tree_sha256"],
                     f"{wid}.{arm.name}: raw tree digest mismatch")
            tree_digests[arm.name] = trees_x["combined_tree_sha256"]

        # 2. Verify ndarray never hits mesh_cache even if a cache dict is supplied
        for arm in arm_objs:
            activate_arm(arm)
            chk_cache = {}
            chk_res = arm.sp.measure_surface_proximity(l_np, r_np, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _mesh_cache=chk_cache)
            _require(chk_res["work"].get("mesh_cache_hits", 0) == 0 and len(chk_cache) == 0,
                     f"{wid}.{arm.name}: ndarray must never hit mesh_cache")

        # 3. Uncached Tuple paired timing
        tup_res = run_paired_timing(
            arm_objs,
            lambda a, l=l_tup, r=r_tup: (lambda: a.sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True, retain_witness_triangles=True)),
            warmup=warmup, repeats=repeats, sig_fn=_surface_sig,
        )
        # 4. Uncached ndarray paired timing
        np_res = run_paired_timing(
            arm_objs,
            lambda a, l=l_np, r=r_np: (lambda: a.sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True, retain_witness_triangles=True)),
            warmup=warmup, repeats=repeats, sig_fn=_surface_sig,
        )

        # Verify Linear control bypasses tree_builds & compare full _surface_sig + work ledgers
        work_by_arm_tup = {a.name: _work_summary(tup_res["last_outs"][a.name]["work"]) for a in arm_objs}
        work_by_arm_np = {a.name: _work_summary(np_res["last_outs"][a.name]["work"]) for a in arm_objs}
        if wid == "Control_12F_Linear":
            for aname, ws in work_by_arm_tup.items():
                _require(ws["tree_builds"] == 0, f"Control_12F_Linear {aname} unexpectedly built BVH trees")
        for other_n in [a.name for a in arm_objs[1:]]:
            _require(work_by_arm_tup[other_n]["work_units"] == work_by_arm_tup[arm_a.name]["work_units"],
                     f"{wid} {other_n}: tuple work_units drifted ({work_by_arm_tup[other_n]['work_units']} != {work_by_arm_tup[arm_a.name]['work_units']})")
            _require(work_by_arm_np[other_n]["work_units"] == work_by_arm_np[arm_a.name]["work_units"],
                     f"{wid} {other_n}: ndarray work_units drifted")

        s0_profiles = {}
        if measure_s0_for:
            for a in arm_objs:
                if a.name in measure_s0_for:
                    bmode, dflat = measure_s0_for[a.name]
                    s0_profiles[a.name] = profile_phases_single_pair(a, l_tup, r_tup, builder_mode=bmode, direct_flat=dflat)

        singles_out[wid] = {
            "classification": w["classification"],
            "role": w["role"],
            "tree_verification": tree_digests,
            "uncached_tuple": {
                "arms": tup_res["arms"],
                "paired_vs_ref": tup_res["paired_vs_ref"],
                "work": work_by_arm_tup,
                "execution_orders": tup_res["execution_orders"],
            },
            "uncached_ndarray": {
                "arms": np_res["arms"],
                "paired_vs_ref": np_res["paired_vs_ref"],
                "work": work_by_arm_np,
                "execution_orders": np_res["execution_orders"],
            },
            "instrumented_phase_profile": s0_profiles,
        }
        med_line = " ".join(
            f"{an}={tup_res['arms'][an]['timing']['median_ms']:.2f}ms"
            for an in [a.name for a in arm_objs]
        )
        print(f"  [single-tuple {wid:<32}] {med_line}", flush=True)

    # Batches: uncached tuple + uncached ndarray + secondary query-local cached tuple
    batches_out = {}
    for b in workloads["batches"]:
        bid = b["id"]
        t_tup, peers_tup = b["tuple_batch"]
        t_np, peers_np = b["ndarray_batch"]

        def run_batch(arm, target, peers, use_cache: bool):
            cache = {} if use_cache else None
            sigs = []
            agg = {}
            for p in peers:
                kw = {"_mesh_cache": cache} if use_cache else {}
                r = arm.sp.measure_surface_proximity(target, p, NOOP, retain_exact_rank=True, retain_witness_triangles=True, **kw)
                sigs.append(_surface_sig(r))
                for k, v in _work_summary(r["work"]).items():
                    if isinstance(v, int):
                        agg[k] = agg.get(k, 0) + v
            return sigs, agg

        uncached_t = run_paired_timing(
            arm_objs,
            lambda a, tg=t_tup, ps=peers_tup: (lambda: run_batch(a, tg, ps, False)),
            warmup=min(1, warmup), repeats=repeats, sig_fn=lambda pair: pair[0],
        )
        uncached_n = run_paired_timing(
            arm_objs,
            lambda a, tg=t_np, ps=peers_np: (lambda: run_batch(a, tg, ps, False)),
            warmup=min(1, warmup), repeats=repeats, sig_fn=lambda pair: pair[0],
        )
        cached_t = run_paired_timing(
            arm_objs,
            lambda a, tg=t_tup, ps=peers_tup: (lambda: run_batch(a, tg, ps, True)),
            warmup=min(1, warmup), repeats=repeats, sig_fn=lambda pair: pair[0],
        )
        for an in [a.name for a in arm_objs]:
            hits = cached_t["last_outs"][an][1].get("mesh_cache_hits", 0)
            _require(hits > 0, f"{bid}.{an}: secondary cached deep-tuple path recorded 0 mesh_cache_hits")
            _require(uncached_t["last_outs"][an][1].get("mesh_cache_hits", 0) == 0,
                     f"{bid}.{an}: uncached tuple path hit cache")

        trans_prof = {}
        if measure_s0_for:
            for a in arm_objs:
                if a.name in measure_s0_for:
                    trans_prof[a.name] = profile_cached_batch_translation(a, t_tup, peers_tup)

        batches_out[bid] = {
            "classification": b["classification"],
            "pair_count": b["pair_count"],
            "uncached_tuple": {
                "arms": uncached_t["arms"],
                "paired_vs_ref": uncached_t["paired_vs_ref"],
                "work_agg": {a.name: uncached_t["last_outs"][a.name][1] for a in arm_objs},
            },
            "uncached_ndarray": {
                "arms": uncached_n["arms"],
                "paired_vs_ref": uncached_n["paired_vs_ref"],
                "work_agg": {a.name: uncached_n["last_outs"][a.name][1] for a in arm_objs},
            },
            "secondary_cached_tuple": {
                "arms": cached_t["arms"],
                "paired_vs_ref": cached_t["paired_vs_ref"],
                "work_agg": {a.name: cached_t["last_outs"][a.name][1] for a in arm_objs},
            },
            "cached_translation_profile": trans_prof,
        }
        med_line = " ".join(f"{an}={uncached_t['arms'][an]['timing']['median_ms']:.2f}ms" for an in [a.name for a in arm_objs])
        print(f"  [batch-tuple  {bid:<32}] {med_line}", flush=True)

    return {"singles": singles_out, "batches": batches_out}


def _compute_decision(screen_results: dict, workloads: dict) -> dict:
    """Apply Section 9 pre-registered screening thresholds."""
    heavy_ids = [w["id"] for w in workloads["singles"] if "construction_heavy" in w["role"]]
    guard_ids = ["G508_Peer_000", "G508_Competing_001", "Control_12F_Linear", "Sparse_100kV_Degenerate_MixedBit"]
    candidates = [n for n in next(iter(screen_results["singles"].values()))["uncached_tuple"]["arms"].keys() if n != "A"]

    summary = {}
    for cname in candidates:
        heavy_wins = []
        build_phase_wins = []
        max_guard_reg_pct = 0.0
        for wid in heavy_ids:
            row = screen_results["singles"][wid]
            pct_tup = row["uncached_tuple"]["paired_vs_ref"][cname]["median_reduction_pct"]
            pct_np = row["uncached_ndarray"]["paired_vs_ref"][cname]["median_reduction_pct"]
            s0_a = row["instrumented_phase_profile"].get("A", {}).get("build_pipeline_total_ms", 0.0)
            s0_c = row["instrumented_phase_profile"].get(cname, {}).get("build_pipeline_total_ms", 0.0)
            bp_pct = ((s0_a - s0_c) / s0_a * 100.0) if s0_a > 0 else 0.0
            heavy_wins.append((wid, pct_tup, pct_np))
            build_phase_wins.append((wid, round(bp_pct, 2), s0_a, s0_c))
        for gid in guard_ids + [b["id"] for b in workloads["batches"]]:
            if gid in screen_results["singles"]:
                row = screen_results["singles"][gid]
                pct = row["uncached_tuple"]["paired_vs_ref"][cname]["median_reduction_pct"]
            else:
                row = screen_results["batches"][gid]
                pct = row["uncached_tuple"]["paired_vs_ref"][cname]["median_reduction_pct"]
            if -pct > max_guard_reg_pct:
                max_guard_reg_pct = round(-pct, 2)
        n_bp_ge10 = sum(1 for _, bp, _, _ in build_phase_wins if bp >= 10.0)
        n_wall_ge5 = sum(1 for _, pt, _ in heavy_wins if pt >= 5.0)
        summary[cname] = {
            "heavy_wall_reductions_pct": [{"id": wid, "tuple_pct": pt, "ndarray_pct": pn} for wid, pt, pn in heavy_wins],
            "build_phase_reductions_pct": [{"id": wid, "build_pct": bp, "A_ms": sa, "cand_ms": sc} for wid, bp, sa, sc in build_phase_wins],
            "count_build_ge_10pct": n_bp_ge10,
            "count_heavy_wall_ge_5pct": n_wall_ge5,
            "max_guard_regression_pct": max_guard_reg_pct,
            "meets_screen_bar": (n_bp_ge10 >= 2 and n_wall_ge5 >= 1 and max_guard_reg_pct < 5.0),
        }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="M3 BVH-042 Exact Build-Pipeline Research Runner")
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--screen-repeats", type=int, default=7)
    parser.add_argument("--confirm-repeats", type=int, default=30)
    parser.add_argument("--skip-confirm", action="store_true")
    args = parser.parse_args()

    arm_paths = make_variant_arms_from_frozen()
    arm_a = load_arm_modules("A", arm_paths["A"])
    _require(arm_a.source_sha256 == FROZEN_RUNTIME_SHA,
             f"Frozen runtime mismatch: {arm_a.source_sha256} != {FROZEN_RUNTIME_SHA}")
    workloads = build_042_workloads()
    cases_manifest = _build_cases_manifest(workloads, arm_a)
    (BENCH_DIR / "KERNEL_042_CASES.json").write_text(json.dumps(cases_manifest, indent=2), encoding="utf-8")

    # Stage 1: S0 + Arms A/B/C/D paired screening
    print("=== Stage S0 & A/B/C/D Screening (warmup={}, repeats={}) ===".format(args.warmup, args.screen_repeats), flush=True)
    arm_b = load_arm_modules("B", arm_paths["B"])
    arm_c = load_arm_modules("C", arm_paths["C"])
    arm_d = load_arm_modules("D", arm_paths["D"])
    s0_modes_abcd = {
        "A": ("baseline", False),
        "B": ("b1", False),
        "C": ("b2", False),
        "D": ("b1_b2", False),
    }
    screen_abcd = _evaluate_arms(
        [arm_a, arm_b, arm_c, arm_d], workloads,
        warmup=args.warmup, repeats=args.screen_repeats, measure_s0_for=s0_modes_abcd,
    )
    decision_abcd = _compute_decision(screen_abcd, workloads)
    print("A-D Decision:", json.dumps(decision_abcd, indent=2), flush=True)

    # Inspect S0 residual profile to decide conditionally whether E (B3) and/or F (B4) are justified
    heavy_names = ("HighRes_1536F_Pair", "Sheet_Dented_2mm", "Tube_Coiled_Loose", "Rotated_30deg_Spheres", "G508_Peer_000")
    residual_metrics = {}
    max_fused_share = 0.0
    max_flat_share = 0.0
    max_compile_share = 0.0
    for wid in heavy_names:
        prof_d = screen_abcd["singles"][wid]["instrumented_phase_profile"]["D"]
        prof_a = screen_abcd["singles"][wid]["instrumented_phase_profile"]["A"]
        tot_a = max(prof_a["instrumented_total_ms"], 1e-6)
        tot_d = max(prof_d["instrumented_total_ms"], 1e-6)
        b_d = max(prof_d["build_pipeline_total_ms"], 1e-6)
        fused_pct = round(prof_d["fused_stats_gather_ms"] / b_d * 100.0, 2)
        flat_pct = round(prof_d["bounds_materialization_and_flatten_ms"] / b_d * 100.0, 2)
        comp_pct = round(prof_d["traversal_compile_ms"] / tot_d * 100.0, 2)
        if wid != "G508_Peer_000":
            max_fused_share = max(max_fused_share, fused_pct)
            max_flat_share = max(max_flat_share, flat_pct)
            max_compile_share = max(max_compile_share, comp_pct)
        residual_metrics[wid] = {
            "A_build_share_pct": round(prof_a["build_pipeline_total_ms"] / tot_a * 100.0, 2),
            "D_fused_gather_share_of_build_pct": fused_pct,
            "D_bounds_flatten_share_of_build_pct": flat_pct,
            "D_compile_share_of_total_pct": comp_pct,
        }

    run_e = max_fused_share >= 8.0
    run_f = (max_flat_share >= 5.0) or (max_compile_share >= 5.0)
    cond_arms = [arm_a, arm_d]
    s0_modes_ef = {"A": ("baseline", False), "D": ("b1_b2", False)}
    arm_e = load_arm_modules("E", arm_paths["E"]) if run_e else None
    arm_f = load_arm_modules("F", arm_paths["F"]) if run_f else None
    if arm_e is not None:
        cond_arms.append(arm_e)
        s0_modes_ef["E"] = ("b1_b2_b3", False)
    if arm_f is not None:
        cond_arms.append(arm_f)
        s0_modes_ef["F"] = ("b1_b2", True)

    screen_ef = None
    decision_ef = {}
    if len(cond_arms) > 2:
        print(f"\n=== Stage Conditional Screening ({[a.name for a in cond_arms]}) ===", flush=True)
        screen_ef = _evaluate_arms(
            cond_arms, workloads,
            warmup=args.warmup, repeats=args.screen_repeats, measure_s0_for=s0_modes_ef,
        )
        decision_ef = _compute_decision(screen_ef, workloads)
        print("Conditional Decision:", json.dumps(decision_ef, indent=2), flush=True)
    else:
        print(f"\n=== Conditional E/F Skipped by Residual Gate (fused={max_fused_share}%, flat={max_flat_share}%, compile={max_compile_share}%) ===", flush=True)

    # Pick simplest best candidate meeting screen thresholds (prefer D over E/F unless E/F gives meaningful >3% net heavy edge)
    merged_decisions = dict(decision_abcd)
    merged_decisions.update({k: v for k, v in decision_ef.items() if k in ("E", "F")})

    winning_arm_name = None
    best_score = -1.0
    for cname in ("B", "C", "D", "E", "F"):
        d_info = merged_decisions.get(cname, {})
        if not d_info.get("meets_screen_bar"):
            continue
        avg_heavy = statistics.mean(x["tuple_pct"] for x in d_info["heavy_wall_reductions_pct"])
        if cname in ("E", "F") and "D" in merged_decisions and merged_decisions["D"]["meets_screen_bar"]:
            d_avg = statistics.mean(x["tuple_pct"] for x in merged_decisions["D"]["heavy_wall_reductions_pct"])
            # Require at least +2.0 percentage points net improvement over simpler D to justify added complexity
            if avg_heavy < d_avg + 2.0:
                continue
        if avg_heavy > best_score:
            best_score = avg_heavy
            winning_arm_name = cname

    # Confirmation 30 paired repeats on construction-heavy, real snapshot, and sparse/linear controls
    confirm30 = None
    if not args.skip_confirm and winning_arm_name is not None:
        win_arm = {"B": arm_b, "C": arm_c, "D": arm_d, "E": arm_e, "F": arm_f}[winning_arm_name]
        print(f"\n=== Stage 30-Repeat Confirmatory Paired Run (A vs {winning_arm_name}) ===", flush=True)
        confirm_workloads = {
            "singles": [
                w for w in workloads["singles"]
                if w["id"] in (
                    "HighRes_1536F_Pair", "Sheet_Dented_2mm", "Tube_Coiled_Loose", "Rotated_30deg_Spheres",
                    "G508_Peer_000", "G508_Competing_001", "Control_12F_Linear", "Sparse_100kV_Degenerate_MixedBit",
                )
            ],
            "batches": workloads["batches"],
        }
        confirm30 = _evaluate_arms(
            [arm_a, win_arm], confirm_workloads,
            warmup=args.warmup, repeats=args.confirm_repeats, measure_s0_for=None,
        )

    final_verdict = (
        f"CANDIDATE_{winning_arm_name}_VALIDATED_RESEARCH_ONLY"
        if winning_arm_name is not None
        else "NO_GAIN_KEEP_119327b"
    )

    out_doc = {
        "schema": "m3-bvh-kernel-042-results-v1",
        "branch": "codex/m3-bvh-exact-build-pipeline-042",
        "frozen_reference_commit": FROZEN_COMMIT,
        "frozen_runtime_source_sha256": FROZEN_RUNTIME_SHA,
        "environment": _win32_env_info(),
        "arm_identities": {
            arm.name: {
                "runtime_source_sha256": arm.source_sha256,
                "surface_proximity_sha256": arm.sp_raw_sha256,
                "surface_geometry_sha256": arm.sg_raw_sha256,
            }
            for arm in [a for a in (arm_a, arm_b, arm_c, arm_d, arm_e, arm_f) if a is not None]
        },
        "conditional_gate": {
            "max_heavy_fused_gather_share_of_build_pct": max_fused_share,
            "max_heavy_bounds_flatten_share_of_build_pct": max_flat_share,
            "max_heavy_compile_share_of_total_pct": max_compile_share,
            "ran_E_b3": run_e,
            "ran_F_b4": run_f,
        },
        "screening_thresholds": {
            "build_phase_reduction_target_pct": 10.0,
            "min_heavy_workloads_for_build_target": 2,
            "net_wall_reduction_target_pct": 5.0,
            "min_heavy_workloads_for_wall_target": 1,
            "max_allowed_guard_regression_pct": 5.0,
        },
        "s0_and_abcd_screening": screen_abcd,
        "residual_profile_metrics": residual_metrics,
        "conditional_ef_screening": screen_ef,
        "arm_decisions": merged_decisions,
        "selected_winner": winning_arm_name,
        "confirm_30_repeats": confirm30,
        "verdict": final_verdict,
    }
    (BENCH_DIR / "KERNEL_042_RESULTS.json").write_text(json.dumps(out_doc, indent=2), encoding="utf-8")
    print(f"\nDONE 042 harness. Verdict={final_verdict}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

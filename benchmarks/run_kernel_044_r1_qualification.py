"""M3 BVH 044-R1 Closure Qualification & Hardened Batch Receipt Validator.

Pins:
  - A        : Frozen 041 (119327bbb4e645c5de3bfbc0d30259736b9a2677)
  - K        : Frozen 042-P2 (b5b0df58bed75f3a259af8078630e1cb511ff769)
  - 044_orig : Reviewed 044 P4 head (535321c9c5bd543638426fa44c35ac9745b72cc9)
  - R1       : Live codex/m3-bvh-p4-traversal-cutoff-044 R1 closure candidate
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import gc
import hashlib
import io
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tarfile
import time
import tracemalloc
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.bvh_eval import _analyze_sig, _closed_sig, _surface_sig, _triangulate, _work_summary
from benchmarks.run_kernel_042_research import (
    FROZEN_COMMIT,
    FROZEN_RUNTIME_SHA,
    NOOP,
    _sha256_json,
    _win32_env_info,
    _win32_process_mem,
    activate_arm,
    build_042_workloads,
    ensure_frozen_arm_a,
    load_arm_modules,
    run_paired_timing,
)

BENCH_DIR = Path(__file__).resolve().parent
R1_ARMS_ROOT = ROOT / "scratch" / "044_r1_arms"
FROZEN_ARM_K_COMMIT = "b5b0df58bed75f3a259af8078630e1cb511ff769"
FROZEN_ARM_K_RUNTIME_SHA = "cc78597b4b4c9e336e7082bcb2fd99ba9739ead2e01104c095f8046fe048baf7"
REVIEWED_044_COMMIT = "535321c9c5bd543638426fa44c35ac9745b72cc9"
REVIEWED_044_RUNTIME_SHA = "7bfbd71982a7152cabf5cb04cf666fd8992bb016e6e09e01a6cd92a3c225b8d5"

_RUNTIME_FILES = [
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


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def _is_sha256(val) -> bool:
    return type(val) is str and len(val) == 64 and all(c in "0123456789abcdef" for c in val)


def _key_to_frac(k) -> Fraction:
    _check(
        type(k) in (list, tuple) and len(k) == 3 and all(type(v) is int for v in k)
        and k[0] >= 0 and k[1] > 0 and k[0].bit_length() <= 4096 and k[1].bit_length() <= 4096,
        f"invalid exact_distance_sq key: {k!r}",
    )
    return Fraction(k[0], k[1]) * (Fraction(2) ** k[2])


def ensure_frozen_arm(commit: str, dirname: str, expected_runtime_sha: str) -> Path:
    dst = R1_ARMS_ROOT / dirname
    marker = dst / "human_eye_plugin/surface_proximity.py"
    if not marker.exists():
        dst.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            ["git", "archive", "--format=tar", commit, "--", *_RUNTIME_FILES],
            cwd=str(ROOT), check=True, stdout=subprocess.PIPE,
        )
        with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode="r:") as tf:
            tf.extractall(path=dst)
        _check(marker.exists(), f"Failed to extract {commit} into {dst}")
    arm = load_arm_modules(f"chk_{dirname}", dst)
    _check(
        arm.source_sha256 == expected_runtime_sha,
        f"{dirname} runtime sha mismatch: {arm.source_sha256} != {expected_runtime_sha}",
    )
    return dst


def build_receipt_digest(receipt: dict) -> str:
    payload = {k: v for k, v in receipt.items() if k != "digest_sha256"}
    return _sha256_json(payload)


def serialize_batch_receipt(
    *,
    arm_name: str,
    runtime_source_sha256: str,
    input_sha256: str,
    options_sha256: str,
    batch_out: dict,
) -> dict:
    outcomes_summary = {}
    for pid in batch_out["peer_ids"]:
        o = batch_out["outcomes_by_id"][pid]
        rk = o["result_kind"]
        if rk == "exact_surface_measurement":
            mres = o["measured_result"]
            outcomes_summary[pid] = {
                "result_kind": rk,
                "snapshot_identity": o["snapshot_identity"],
                "source_identity": o.get("source_identity"),
                "measured_sig": _surface_sig(mres),
                "_exact_distance_sq": list(mres["_exact_distance_sq"]),
                "work_summary": _work_summary(mres["work"]),
            }
        elif rk == "nearest_cutoff_exclusion":
            pr = o["proof_receipt"]
            # Store compact deterministic proof audit fields without raw node dumps
            compact_receipt = {
                "origin": pr.get("origin"),
                "factor": pr.get("factor"),
                "local_cutoff": pr.get("local_cutoff"),
                "strict_inequality_verified": pr.get("strict_inequality_verified"),
                "aabb_gap_sq": pr.get("aabb_gap_sq"),
                "total_leaf_pairs": pr.get("total_leaf_pairs"),
                "covered_pairs": pr.get("covered_pairs"),
                "subtree_pruned_pairs": pr.get("subtree_pruned_pairs"),
                "aabb_pruned_pairs": pr.get("aabb_pruned_pairs"),
                "plane_pruned_pairs": pr.get("plane_pruned_pairs"),
                "wp_pruned_pairs": pr.get("wp_pruned_pairs"),
                "narrow_phase_pairs": pr.get("narrow_phase_pairs"),
                "cutoff_axis_used": pr.get("cutoff_axis_used"),
            }
            outcomes_summary[pid] = {
                "result_kind": rk,
                "disposition": o["disposition"],
                "snapshot_identity": o["snapshot_identity"],
                "source_identity": o.get("source_identity"),
                "exact_upper_bound_key": list(o["exact_upper_bound_key"]),
                "upper_bound_origin": o.get("upper_bound_origin"),
                "proof_kind": o["proof_kind"],
                "proof_receipt": compact_receipt,
                "work_summary": _work_summary(o["work"]),
            }
        else:
            outcomes_summary[pid] = {
                "result_kind": rk,
                "snapshot_identity": o.get("snapshot_identity"),
                "source_identity": o.get("source_identity"),
                "reason": o.get("reason"),
                "resource_stop": o.get("resource_stop"),
                "work_summary": _work_summary(o.get("work", {})),
            }

    rec = {
        "schema": "m3-bvh-044-r1-batch-receipt-v1",
        "arm": arm_name,
        "runtime_source_sha256": runtime_source_sha256,
        "input_sha256": input_sha256,
        "options_sha256": options_sha256,
        "snapshot_identity": batch_out["snapshot_identity"],
        "cutoff_mode": batch_out["cutoff_mode"],
        "sort_policy": batch_out["sort_policy"],
        "peer_ids": list(batch_out["peer_ids"]),
        "status": batch_out["status"],
        "nearest_ids": batch_out["nearest_ids"],
        "best_known_ids": batch_out["best_known_ids"],
        "best_exact_distance_sq": list(batch_out["best_exact_distance_sq"]) if batch_out["best_exact_distance_sq"] is not None else None,
        "distance_m": batch_out["distance_m"],
        "coverage": dict(batch_out["coverage"]),
        "outcomes_by_id": outcomes_summary,
    }
    rec["digest_sha256"] = build_receipt_digest(rec)
    return rec


def _validate_single_receipt(receipt: dict, expected_manifest: dict, expected_pin: str, label: str) -> None:
    req = {
        "schema", "arm", "runtime_source_sha256", "input_sha256", "options_sha256",
        "snapshot_identity", "peer_ids", "status", "nearest_ids",
        "best_exact_distance_sq", "coverage", "outcomes_by_id", "digest_sha256",
    }
    _check(type(receipt) is dict and req <= set(receipt), f"{label}: missing required receipt fields")
    _check(receipt["schema"] == "m3-bvh-044-r1-batch-receipt-v1", f"{label}: wrong schema")
    _check(_is_sha256(receipt["runtime_source_sha256"]), f"{label}: invalid runtime_source_sha256")
    _check(receipt["runtime_source_sha256"] == expected_pin,
           f"{label}: runtime pin mismatch {receipt['runtime_source_sha256']} != {expected_pin}")
    _check(_is_sha256(receipt["input_sha256"]) and receipt["input_sha256"] == expected_manifest["input_sha256"],
           f"{label}: input_sha256 mismatch")
    _check(_is_sha256(receipt["options_sha256"]), f"{label}: invalid options_sha256")
    _check(receipt["digest_sha256"] == build_receipt_digest(receipt), f"{label}: receipt digest_sha256 mismatch")

    pids = receipt["peer_ids"]
    _check(type(pids) is list and len(pids) > 0, f"{label}: empty or non-list peer_ids")
    _check(len(set(pids)) == len(pids), f"{label}: duplicate peer_ids")
    _check(pids == list(expected_manifest["peer_ids"]), f"{label}: peer_ids != manifest peer_ids")

    cov = receipt["coverage"]
    _check(type(cov) is dict, f"{label}: coverage must be dict")
    n_in = cov.get("n_input")
    n_m = cov.get("n_measured")
    n_ex = cov.get("n_strictly_excluded")
    n_un = cov.get("n_unknown")
    _check(all(type(v) is int and v >= 0 for v in (n_in, n_m, n_ex, n_un)), f"{label}: invalid coverage counts")
    _check(n_in == len(pids) and n_in == n_m + n_ex + n_un, f"{label}: coverage denominator mismatch")

    obid = receipt["outcomes_by_id"]
    _check(type(obid) is dict and set(obid) == set(pids), f"{label}: outcomes_by_id keys mismatch")
    cnt_m = cnt_ex = cnt_un = 0
    best_sq_frac = None
    min_measured_pids = []
    for pid in pids:
        o = obid[pid]
        _check(type(o) is dict, f"{label}.{pid}: outcome must be dict")
        _check(o.get("snapshot_identity") == receipt["snapshot_identity"],
               f"{label}.{pid}: outcome snapshot_identity mismatch")
        rk = o.get("result_kind")
        if rk == "exact_surface_measurement":
            cnt_m += 1
            sig = o.get("measured_sig")
            _check(
                type(sig) is dict and sig.get("measurement_valid") is True
                and type(sig.get("distance_m")) in (int, float) and sig["distance_m"] >= 0,
                f"{label}.{pid}: invalid measured_sig",
            )
            kf = _key_to_frac(o.get("_exact_distance_sq"))
            if best_sq_frac is None or kf < best_sq_frac:
                best_sq_frac = kf
                min_measured_pids = [pid]
            elif kf == best_sq_frac:
                min_measured_pids.append(pid)
        elif rk == "nearest_cutoff_exclusion":
            cnt_ex += 1
            _check(o.get("disposition") == "strictly_above_cutoff", f"{label}.{pid}: bad exclusion disposition")
            _check(all(bad not in o for bad in ("distance_m", "_exact_distance_sq", "measurement_valid")),
                   f"{label}.{pid}: exclusion leaked measured fields")
            ubf = _key_to_frac(o.get("exact_upper_bound_key"))
            pk = o.get("proof_kind")
            _check(pk in ("root_aabb", "root_axis", "complete_cutoff_traversal"), f"{label}.{pid}: invalid proof_kind")
            pr = o.get("proof_receipt")
            _check(type(pr) is dict, f"{label}.{pid}: missing proof_receipt")
            if pk == "root_aabb":
                lc = pr.get("local_cutoff")
                _check(type(lc) is list and len(lc) == 2 and lc[1] > 0, f"{label}.{pid}: bad root_aabb local_cutoff")
                _check(pr.get("strict_inequality_verified") is True
                       and type(pr.get("aabb_gap_sq")) is int
                       and pr["aabb_gap_sq"] * lc[1] > lc[0],
                       f"{label}.{pid}: root_aabb inequality not strictly verified")
            elif pk == "complete_cutoff_traversal":
                _check(type(pr.get("total_leaf_pairs")) is int and pr["total_leaf_pairs"] > 0
                       and pr.get("covered_pairs") == pr.get("total_leaf_pairs"),
                       f"{label}.{pid}: traversal partition sum != total_leaf_pairs")
        elif rk == "nearest_cutoff_unknown":
            cnt_un += 1
            _check(bool(o.get("reason")), f"{label}.{pid}: unknown missing reason")
        else:
            raise ValueError(f"{label}.{pid}: unsupported result_kind {rk!r}")

    _check((cnt_m, cnt_ex, cnt_un) == (n_m, n_ex, n_un), f"{label}: outcome counts != coverage summary")
    st = receipt["status"]
    if st == "complete":
        _check(cnt_un == 0 and cnt_m > 0, f"{label}: complete batch cannot have unknown or zero measured")
        _check(receipt["nearest_ids"] == sorted(min_measured_pids) or receipt["nearest_ids"] == min_measured_pids,
               f"{label}: nearest_ids mismatch vs measured minimum")
        _check(set(receipt["nearest_ids"]) == set(min_measured_pids), f"{label}: nearest_ids set mismatch")
        bf = _key_to_frac(receipt["best_exact_distance_sq"])
        _check(bf == best_sq_frac, f"{label}: best_exact_distance_sq != min measured")
    elif st == "partial":
        _check(receipt["nearest_ids"] is None, f"{label}: partial result must have nearest_ids=None")
        _check(cnt_un > 0 and cnt_m > 0, f"{label}: partial inconsistent with coverage")
    elif st == "unknown":
        _check(receipt["nearest_ids"] is None and cnt_m == 0, f"{label}: unknown inconsistent with coverage")
    else:
        raise ValueError(f"{label}: invalid batch status {st!r}")


def validate_batch_receipt_comparison(
    baseline_receipt: dict,
    candidate_receipt: dict,
    expected_manifest: dict,
    expected_pins: dict,
) -> dict:
    """Hardened fail-closed receipt validator (works identically under python -O)."""
    _check(type(expected_manifest) is dict and _is_sha256(expected_manifest.get("input_sha256")),
           "invalid expected_manifest")
    _check(type(baseline_receipt) is dict and type(candidate_receipt) is dict, "receipts must be dicts")
    b_arm = baseline_receipt.get("arm")
    c_arm = candidate_receipt.get("arm")
    _check(b_arm in expected_pins and c_arm in expected_pins, f"unknown arm in expected_pins: {b_arm!r}, {c_arm!r}")

    _validate_single_receipt(baseline_receipt, expected_manifest, expected_pins[b_arm], f"baseline[{b_arm}]")
    _validate_single_receipt(candidate_receipt, expected_manifest, expected_pins[c_arm], f"candidate[{c_arm}]")

    if "options_sha256" in expected_manifest:
        _check(candidate_receipt["options_sha256"] == expected_manifest["options_sha256"],
               "candidate options_sha256 != manifest options_sha256")
    else:
        _check(baseline_receipt["options_sha256"] == candidate_receipt["options_sha256"],
               "options_sha256 mismatch between baseline and candidate")

    _check(baseline_receipt["status"] == candidate_receipt["status"],
           f"batch status mismatch: {baseline_receipt['status']} vs {candidate_receipt['status']}")
    if baseline_receipt["status"] == "complete":
        _check(sorted(baseline_receipt["nearest_ids"]) == sorted(candidate_receipt["nearest_ids"]),
               "nearest_ids winner set mismatch")
        _check(_key_to_frac(baseline_receipt["best_exact_distance_sq"]) == _key_to_frac(candidate_receipt["best_exact_distance_sq"]),
               "best_exact_distance_sq mismatch")

    cand_best_frac = (_key_to_frac(candidate_receipt["best_exact_distance_sq"])
                      if candidate_receipt["best_exact_distance_sq"] is not None else None)

    for pid in expected_manifest["peer_ids"]:
        bo = baseline_receipt["outcomes_by_id"][pid]
        co = candidate_receipt["outcomes_by_id"][pid]
        brk, crk = bo["result_kind"], co["result_kind"]
        if crk == "exact_surface_measurement" and brk == "exact_surface_measurement":
            _check(bo["measured_sig"] == co["measured_sig"], f"peer {pid}: measured_sig mismatch")
        elif crk == "nearest_cutoff_exclusion":
            ubf = _key_to_frac(co["exact_upper_bound_key"])
            _check(cand_best_frac is not None and ubf >= cand_best_frac,
                   f"peer {pid}: upper bound {ubf} < candidate best {cand_best_frac}")
            if brk == "exact_surface_measurement":
                true_f = _key_to_frac(bo["_exact_distance_sq"])
                _check(true_f > ubf,
                       f"peer {pid}: false/equality exclusion true_d2={true_f} not strictly > bound={ubf}")
        elif crk == "nearest_cutoff_unknown" and brk != "nearest_cutoff_unknown":
            raise ValueError(f"peer {pid}: candidate regressed from {brk} to nearest_cutoff_unknown")

    return {"passed": True, "peers_checked": len(expected_manifest["peer_ids"])}


def _freeze_mesh(oid: str, verts, faces):
    return SimpleNamespace(
        object_id=oid, name=oid,
        vertices=tuple(tuple(float(c) for c in v) for v in verts),
        faces=tuple(tuple(int(i) for i in f) for f in _triangulate(faces)),
    )


def _load_real_batch_fixtures() -> dict:
    # 1. G508 retained 11 peers from ACTUAL_SNAPSHOT
    snap = json.loads((ROOT / "verification/spatial_task_qualification_001/entry/run_01/ACTUAL_SNAPSHOT.json").read_bytes())
    g_objs = {r["name"]: r for r in snap["objects"]}
    g_target = _freeze_mesh("Target", g_objs["Target"]["vertices_world"], g_objs["Target"]["triangles"])
    g_peer_names = ["Peer_000", "Competing_001"] + [f"Near_{k:03d}" for k in range(3, 12)]
    g_peers = [_freeze_mesh(n, g_objs[n]["vertices_world"], g_objs[n]["triangles"]) for n in g_peer_names]

    # 2. G60_D12 retained 11 peers
    g60 = json.loads((ROOT / "verification/scale_diag_001/fixtures/G60_D12.json").read_bytes())
    g60_objs = {r["name"]: r for r in g60["objects"]}
    g60_target = _freeze_mesh("Target", g60_objs["Target"]["vertices_world"], g60_objs["Target"]["triangles"])
    g60_peer_names = [r["name"] for r in g60["objects"] if r["name"] != "Target"]
    g60_peers = [_freeze_mesh(n, g60_objs[n]["vertices_world"], g60_objs[n]["triangles"]) for n in g60_peer_names]

    return {
        "G508_Retained_11pairs": {"target": g_target, "peers": g_peers, "peer_ids": g_peer_names},
        "G60_D12_Retained_11pairs": {"target": g60_target, "peers": g60_peers, "peer_ids": g60_peer_names},
    }


def _run_mem_worker(arm_key: str, mode_name: str, workload_name: str) -> dict:
    """Isolated single-arm OS memory probe executed in its own clean child process."""
    wl = build_042_workloads()
    real = _load_real_batch_fixtures()

    if arm_key == "A":
        arm = load_arm_modules("A", ensure_frozen_arm_a())
    elif arm_key == "K":
        arm = load_arm_modules("K", ensure_frozen_arm(FROZEN_ARM_K_COMMIT, "arm_k_042_p2", FROZEN_ARM_K_RUNTIME_SHA))
    else:
        arm = load_arm_modules("R1", ROOT)
    activate_arm(arm)

    if workload_name in ("G508_Peer_000", "HighRes_1536F_Pair"):
        spec = next(x for x in wl["singles"] if x["id"] == workload_name)
        l_m, r_m = spec["tuple_pair"]
        fn = lambda: arm.sp.measure_surface_proximity(l_m, r_m, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
    else:
        b = next(x for x in wl["batches"] if x["id"] == "D48_Real_47pairs")
        tg, ps = b["tuple_batch"]
        if mode_name == "exhaustive_loop":
            fn = lambda: [arm.sp.measure_surface_proximity(tg, p, NOOP, retain_exact_rank=True) for p in ps]
        else:
            fn = lambda: arm.sp.measure_nearest_surface_batch(tg, ps, NOOP, cutoff_mode=mode_name, sort_policy="stable")

    # Warm once, gc, then trace & capture independent process peak working set
    _ = fn()
    gc.collect()
    before = _win32_process_mem()
    tracemalloc.start()
    for _ in range(3):
        out = fn()
    _, tm_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    after = _win32_process_mem()
    return {
        "arm": arm_key,
        "mode": mode_name,
        "workload": workload_name,
        "runtime_source_sha256": arm.source_sha256,
        "tracemalloc_peak_bytes": int(tm_peak),
        "before": before,
        "after": after,
        "peak_working_set_bytes": after.get("peak_working_set_bytes"),
        "working_set_bytes": after.get("working_set_bytes"),
        "pagefile_bytes": after.get("pagefile_bytes"),
    }


def run_isolated_subprocess_memory_probes() -> dict:
    jobs = [
        ("A", "ordinary", "G508_Peer_000"),
        ("K", "ordinary", "G508_Peer_000"),
        ("R1", "ordinary", "G508_Peer_000"),
        ("A", "ordinary", "HighRes_1536F_Pair"),
        ("K", "ordinary", "HighRes_1536F_Pair"),
        ("R1", "ordinary", "HighRes_1536F_Pair"),
        ("K", "exhaustive_loop", "D48_Real_47pairs"),
        ("R1", "exhaustive_loop", "D48_Real_47pairs"),
        ("R1", "EXHAUSTIVE", "D48_Real_47pairs"),
        ("R1", "CUTOFF_ONLY_OFF", "D48_Real_47pairs"),
        ("R1", "CUTOFF_SETTLED_PROJECTION", "D48_Real_47pairs"),
    ]
    rows = []
    for arm_k, mode_n, wid in jobs:
        proc = subprocess.run(
            [sys.executable, "-B", __file__, "--mem-worker", arm_k, mode_n, wid],
            cwd=str(ROOT), check=True, stdout=subprocess.PIPE, text=True,
        )
        rows.append(json.loads(proc.stdout.strip().splitlines()[-1]))
    return {
        "scope": "independent_child_process_K32GetProcessMemoryInfo_PeakWorkingSetSize_and_tracemalloc",
        "runs": rows,
    }


def _paired_stats(ref_ms: list[float], cand_ms: list[float]) -> dict:
    reds = [((r - c) / r) * 100.0 for r, c in zip(ref_ms, cand_ms)]
    deltas = [c - r for r, c in zip(ref_ms, cand_ms)]
    med_r = statistics.median(ref_ms)
    med_c = statistics.median(cand_ms)
    return {
        "paired_median_reduction_pct": round(statistics.median(reds), 2),
        "aggregate_median_ratio": round(med_r / med_c, 4) if med_c > 0 else None,
        "paired_median_delta_ms": round(statistics.median(deltas), 4),
        "faster_count": sum(1 for r, c in zip(ref_ms, cand_ms) if c < r),
        "repeats": len(ref_ms),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="M3 BVH 044-R1 Qualification")
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument("--mem-worker", nargs=3, metavar=("ARM", "MODE", "WORKLOAD"))
    args = parser.parse_args()

    if args.mem_worker:
        print(json.dumps(_run_mem_worker(*args.mem_worker)))
        return 0

    arm_a_dir = ensure_frozen_arm_a()
    arm_k_dir = ensure_frozen_arm(FROZEN_ARM_K_COMMIT, "arm_k_042_p2", FROZEN_ARM_K_RUNTIME_SHA)
    arm_044_dir = ensure_frozen_arm(REVIEWED_044_COMMIT, "arm_044_orig", REVIEWED_044_RUNTIME_SHA)

    arm_a = load_arm_modules("A", arm_a_dir)
    arm_k = load_arm_modules("K", arm_k_dir)
    arm_044 = load_arm_modules("044_orig", arm_044_dir)
    arm_r1 = load_arm_modules("R1", ROOT)

    expected_pins = {
        "A": FROZEN_RUNTIME_SHA,
        "K": FROZEN_ARM_K_RUNTIME_SHA,
        "044_orig": REVIEWED_044_RUNTIME_SHA,
        "R1": arm_r1.source_sha256,
    }
    _check(arm_a.source_sha256 == expected_pins["A"], "Arm A pin mismatch")
    _check(arm_k.source_sha256 == expected_pins["K"], "Arm K pin mismatch")
    _check(arm_044.source_sha256 == expected_pins["044_orig"], "Arm 044 pin mismatch")

    workloads = build_042_workloads()
    real_batches = _load_real_batch_fixtures()

    # Write preregistered external manifest KERNEL_044_R1_CASES.json
    manifest_cases = {
        "schema": "m3-bvh-044-r1-cases-v1",
        "expected_pins": {
            "A": {"commit": FROZEN_COMMIT, "runtime_source_sha256": FROZEN_RUNTIME_SHA},
            "K": {"commit": FROZEN_ARM_K_COMMIT, "runtime_source_sha256": FROZEN_ARM_K_RUNTIME_SHA},
            "044_orig": {"commit": REVIEWED_044_COMMIT, "runtime_source_sha256": REVIEWED_044_RUNTIME_SHA},
            "R1_candidate": {"branch": "codex/m3-bvh-p4-traversal-cutoff-044", "runtime_source_sha256": arm_r1.source_sha256},
        },
        "historical_private_fixtures": {
            "zero489": "MISSING_HISTORICAL_INPUT",
            "first_yield": "MISSING_HISTORICAL_INPUT",
            "pair129": "MISSING_HISTORICAL_INPUT",
            "040_closed_solid": "MISSING_HISTORICAL_INPUT",
            "B02_10_retained_subset": "MISSING_HISTORICAL_INPUT",
        },
        "singles": [{"id": w["id"], "classification": w["classification"], "input_sha256": w["input_sha256"]} for w in workloads["singles"]],
        "batches": [
            {"id": b["id"], "provenance": b["classification"], "pair_count": b["pair_count"], "input_sha256": b["input_sha256"], "peer_ids": [f"peer_{i}" for i in range(b["pair_count"])]}
            for b in workloads["batches"]
        ] + [
            {"id": bid, "provenance": "real_frozen_scene_snapshot", "pair_count": len(fv["peers"]),
             "input_sha256": _sha256_json([list(fv["target"].vertices), list(fv["target"].faces)] + [[list(p.vertices), list(p.faces)] for p in fv["peers"]]),
             "peer_ids": fv["peer_ids"]}
            for bid, fv in real_batches.items()
        ],
    }
    (BENCH_DIR / "KERNEL_044_R1_CASES.json").write_text(json.dumps(manifest_cases, indent=2), encoding="utf-8")

    # 1. Exact A-only parity check vs Arm K across all 9 singles x 3 modes & 70 batch pairs
    print("=== 1. R1 A-Only Full Non-Work + Full Work Parity vs Frozen K ===", flush=True)
    for w in workloads["singles"]:
        l_m, r_m = w["tuple_pair"]
        for mode in ("settled_credit_031_ref", "off", "off_paid_dequeue_ref"):
            activate_arm(arm_k)
            rk = arm_k.sp.measure_surface_proximity(l_m, r_m, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=mode)
            activate_arm(arm_r1)
            rr = arm_r1.sp.measure_surface_proximity(l_m, r_m, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=mode)
            _check(_surface_sig(rk) == _surface_sig(rr), f"R1_A sig mismatch on {w['id']}/{mode}")
            _check(rk["work"] == rr["work"], f"R1_A full work dict mismatch on {w['id']}/{mode}")
    print("  100% R1_A == K verified (27 single runs + raw work dict).", flush=True)

    # 2. A-only 30-repeat paired confirmation (A vs K vs R1_A)
    print(f"\n=== 2. {args.repeats}-Repeat Paired A-Only Confirmation (A vs K vs R1_A) ===", flush=True)
    a_arms = [arm_a, arm_k, arm_r1]
    r1a_confirm = {"singles": {}, "batches": {}}
    for w in workloads["singles"]:
        wid = w["id"]
        tup_res = run_paired_timing(
            a_arms,
            lambda a, l=w["tuple_pair"][0], r=w["tuple_pair"][1]: (lambda: a.sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True, retain_witness_triangles=True)),
            warmup=args.warmup, repeats=args.repeats, sig_fn=_surface_sig,
        )
        np_res = run_paired_timing(
            a_arms,
            lambda a, l=w["ndarray_pair"][0], r=w["ndarray_pair"][1]: (lambda: a.sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True, retain_witness_triangles=True)),
            warmup=args.warmup, repeats=args.repeats, sig_fn=_surface_sig,
        )
        t_ps_k = _paired_stats(tup_res["arms"]["K"]["timing"]["raw_wall_ms"], tup_res["arms"]["R1"]["timing"]["raw_wall_ms"])
        t_ps_a = _paired_stats(tup_res["arms"]["A"]["timing"]["raw_wall_ms"], tup_res["arms"]["R1"]["timing"]["raw_wall_ms"])
        n_ps_k = _paired_stats(np_res["arms"]["K"]["timing"]["raw_wall_ms"], np_res["arms"]["R1"]["timing"]["raw_wall_ms"])
        n_ps_a = _paired_stats(np_res["arms"]["A"]["timing"]["raw_wall_ms"], np_res["arms"]["R1"]["timing"]["raw_wall_ms"])
        r1a_confirm["singles"][wid] = {
            "uncached_tuple": {"arms": tup_res["arms"], "paired_R1_vs_A": t_ps_a, "paired_R1_vs_K": t_ps_k},
            "uncached_ndarray": {"arms": np_res["arms"], "paired_R1_vs_A": n_ps_a, "paired_R1_vs_K": n_ps_k},
        }
        print(
            f"  [R1-A single {wid:<32}] A={tup_res['arms']['A']['timing']['median_ms']:6.2f} K={tup_res['arms']['K']['timing']['median_ms']:6.2f} "
            f"R1={tup_res['arms']['R1']['timing']['median_ms']:6.2f}ms "
            f"(vsA:{t_ps_a['paired_median_reduction_pct']:+5.2f}%, vsK:{t_ps_k['paired_median_reduction_pct']:+5.2f}%, {t_ps_k['faster_count']}/{args.repeats})",
            flush=True,
        )

    for b in workloads["batches"]:
        bid = b["id"]
        t_tup, peers_tup = b["tuple_batch"]
        t_np, peers_np = b["ndarray_batch"]

        def run_exhaust(arm, tg, ps, uc):
            c = {} if uc else None
            return [_surface_sig(arm.sp.measure_surface_proximity(tg, p, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _mesh_cache=c)) for p in ps]

        ut = run_paired_timing(a_arms, lambda a, tg=t_tup, ps=peers_tup: (lambda: run_exhaust(a, tg, ps, False)), warmup=min(1, args.warmup), repeats=args.repeats, sig_fn=lambda x: x)
        un = run_paired_timing(a_arms, lambda a, tg=t_np, ps=peers_np: (lambda: run_exhaust(a, tg, ps, False)), warmup=min(1, args.warmup), repeats=args.repeats, sig_fn=lambda x: x)
        ct = run_paired_timing(a_arms, lambda a, tg=t_tup, ps=peers_tup: (lambda: run_exhaust(a, tg, ps, True)), warmup=min(1, args.warmup), repeats=args.repeats, sig_fn=lambda x: x)
        ups_k = _paired_stats(ut["arms"]["K"]["timing"]["raw_wall_ms"], ut["arms"]["R1"]["timing"]["raw_wall_ms"])
        ups_a = _paired_stats(ut["arms"]["A"]["timing"]["raw_wall_ms"], ut["arms"]["R1"]["timing"]["raw_wall_ms"])
        unps_k = _paired_stats(un["arms"]["K"]["timing"]["raw_wall_ms"], un["arms"]["R1"]["timing"]["raw_wall_ms"])
        unps_a = _paired_stats(un["arms"]["A"]["timing"]["raw_wall_ms"], un["arms"]["R1"]["timing"]["raw_wall_ms"])
        cps_k = _paired_stats(ct["arms"]["K"]["timing"]["raw_wall_ms"], ct["arms"]["R1"]["timing"]["raw_wall_ms"])
        cps_a = _paired_stats(ct["arms"]["A"]["timing"]["raw_wall_ms"], ct["arms"]["R1"]["timing"]["raw_wall_ms"])
        r1a_confirm["batches"][bid] = {
            "uncached_tuple": {"arms": ut["arms"], "paired_R1_vs_A": ups_a, "paired_R1_vs_K": ups_k},
            "uncached_ndarray": {"arms": un["arms"], "paired_R1_vs_A": unps_a, "paired_R1_vs_K": unps_k},
            "secondary_cached_tuple": {"arms": ct["arms"], "paired_R1_vs_A": cps_a, "paired_R1_vs_K": cps_k},
        }
        print(
            f"  [R1-A batch  {bid:<32}] unc A={ut['arms']['A']['timing']['median_ms']:6.2f} K={ut['arms']['K']['timing']['median_ms']:6.2f} R1={ut['arms']['R1']['timing']['median_ms']:6.2f}ms (vsA:{ups_a['paired_median_reduction_pct']:+.2f}% vsK:{ups_k['paired_median_reduction_pct']:+.2f}%) | "
            f"cac K={ct['arms']['K']['timing']['median_ms']:6.2f} R1={ct['arms']['R1']['timing']['median_ms']:6.2f}ms (vsK:{cps_k['paired_median_reduction_pct']:+.2f}%)",
            flush=True,
        )

    # 3. B-Path 30-repeat same-reducer confirmation across EXHAUSTIVE vs CUTOFF_ONLY_OFF vs CUTOFF_ONLY_PAID_REF vs CUTOFF_SETTLED_PROJECTION
    print(f"\n=== 3. {args.repeats}-Repeat Paired R1-B Same-Reducer Qualification (Stable Natural Order) ===", flush=True)
    batch_inputs = {
        "D48_Real_47pairs": {"target": workloads["batches"][0]["tuple_batch"][0], "peers": workloads["batches"][0]["tuple_batch"][1],
                             "peer_ids": [f"peer_{i}" for i in range(47)], "input_sha256": workloads["batches"][0]["input_sha256"],
                             "ndarray_target": workloads["batches"][0]["ndarray_batch"][0], "ndarray_peers": workloads["batches"][0]["ndarray_batch"][1]},
        "Assembly24_Obj014_23pairs": {"target": workloads["batches"][1]["tuple_batch"][0], "peers": workloads["batches"][1]["tuple_batch"][1],
                                      "peer_ids": [f"peer_{i}" for i in range(23)], "input_sha256": workloads["batches"][1]["input_sha256"],
                                      "ndarray_target": workloads["batches"][1]["ndarray_batch"][0], "ndarray_peers": workloads["batches"][1]["ndarray_batch"][1]},
        **{k: {**v, "input_sha256": next(x["input_sha256"] for x in manifest_cases["batches"] if x["id"] == k)} for k, v in real_batches.items()},
    }

    r1b_results = {}
    b_modes = ("EXHAUSTIVE", "CUTOFF_ONLY_OFF", "CUTOFF_ONLY_PAID_REF", "CUTOFF_SETTLED_PROJECTION")
    for bid, bspec in batch_inputs.items():
        tg_t, ps_t, pids = bspec["target"], bspec["peers"], bspec["peer_ids"]
        ext_manifest = {"input_sha256": bspec["input_sha256"], "peer_ids": pids}

        class _ModeArm:
            def __init__(self, name, cmode, use_cache, tg, ps):
                self.name = name
                self.mods = arm_r1.mods
                self.cmode = cmode
                self.use_cache = use_cache
                self.tg = tg
                self.ps = ps

        variants_runs = [("tuple_uncached_stable", tg_t, ps_t, False), ("tuple_cached_stable", tg_t, ps_t, True)]
        if "ndarray_target" in bspec:
            variants_runs.append(("ndarray_uncached_stable", bspec["ndarray_target"], bspec["ndarray_peers"], False))

        vdict = {}
        for vlabel, t_in, p_in, use_c in variants_runs:
            m_arms = [_ModeArm(m, m, use_c, t_in, p_in) for m in b_modes]

            # Validate full receipts first using validate_batch_receipt_comparison!
            activate_arm(arm_r1)
            receipts = {}
            opt_shas = {}
            sample_outs = {}
            for m in b_modes:
                bo = arm_r1.sp.measure_nearest_surface_batch(
                    t_in, p_in, NOOP, peer_ids=pids, cutoff_mode=m, sort_policy="stable",
                    use_mesh_cache=use_c, retain_witness_triangles=True,
                )
                opt_sha = _sha256_json({"sort_policy": "stable", "use_mesh_cache": use_c, "retain_witness": True})
                rec = serialize_batch_receipt(
                    arm_name=m, runtime_source_sha256=arm_r1.source_sha256,
                    input_sha256=bspec["input_sha256"], options_sha256=opt_sha, batch_out=bo,
                )
                receipts[m] = rec
                opt_shas[m] = opt_sha
                sample_outs[m] = bo
                if m != "EXHAUSTIVE":
                    validate_batch_receipt_comparison(
                        receipts["EXHAUSTIVE"], rec,
                        {**ext_manifest, "options_sha256": opt_sha},
                        {"EXHAUSTIVE": arm_r1.source_sha256, m: arm_r1.source_sha256},
                    )

            paired = run_paired_timing(
                m_arms,
                lambda ma: (lambda: arm_r1.sp.measure_nearest_surface_batch(
                    ma.tg, ma.ps, NOOP, peer_ids=pids, cutoff_mode=ma.cmode, sort_policy="stable",
                    use_mesh_cache=ma.use_cache, retain_witness_triangles=True,
                )),
                warmup=min(1, args.warmup), repeats=args.repeats,
                sig_fn=lambda bo: (bo["status"], tuple(bo["nearest_ids"] or []), tuple(bo["best_exact_distance_sq"] or [])),
            )
            exh_s = paired["arms"]["EXHAUSTIVE"]["timing"]["raw_wall_ms"]
            b0_s = paired["arms"]["CUTOFF_ONLY_OFF"]["timing"]["raw_wall_ms"]
            b_paid_s = paired["arms"]["CUTOFF_ONLY_PAID_REF"]["timing"]["raw_wall_ms"]
            b_set_s = paired["arms"]["CUTOFF_SETTLED_PROJECTION"]["timing"]["raw_wall_ms"]

            ps_b0_vs_exh = _paired_stats(exh_s, b0_s)
            ps_paid_vs_exh = _paired_stats(exh_s, b_paid_s)
            ps_set_vs_exh = _paired_stats(exh_s, b_set_s)
            ps_set_vs_paid = _paired_stats(b_paid_s, b_set_s)
            ps_set_vs_b0 = _paired_stats(b0_s, b_set_s)

            covs = {m: sample_outs[m]["coverage"] for m in b_modes}
            wus = {m: sum(r.get("work", {}).get("work_units", 0) for r in sample_outs[m]["outcomes_by_index"]) for m in b_modes}
            vdict[vlabel] = {
                "arms": paired["arms"],
                "coverages": covs,
                "work_units_total": wus,
                "paired_B0_vs_EXHAUSTIVE": ps_b0_vs_exh,
                "paired_PAID_REF_vs_EXHAUSTIVE": ps_paid_vs_exh,
                "paired_SETTLED_vs_EXHAUSTIVE": ps_set_vs_exh,
                "paired_SETTLED_vs_PAID_REF": ps_set_vs_paid,
                "paired_SETTLED_vs_B0": ps_set_vs_b0,
                "receipt_digests": {m: receipts[m]["digest_sha256"] for m in b_modes},
            }
            print(
                f"  [R1-B {bid:<26} {vlabel:<23}] EXH={paired['arms']['EXHAUSTIVE']['timing']['median_ms']:6.2f} "
                f"B0={paired['arms']['CUTOFF_ONLY_OFF']['timing']['median_ms']:6.2f}({ps_b0_vs_exh['paired_median_reduction_pct']:+.1f}%) "
                f"PAID={paired['arms']['CUTOFF_ONLY_PAID_REF']['timing']['median_ms']:6.2f} "
                f"SETTLED={paired['arms']['CUTOFF_SETTLED_PROJECTION']['timing']['median_ms']:6.2f}"
                f"(vsEXH:{ps_set_vs_exh['paired_median_reduction_pct']:+.1f}% vsB0:{ps_set_vs_b0['paired_median_reduction_pct']:+.1f}% "
                f"excl={covs['CUTOFF_SETTLED_PROJECTION']['n_strictly_excluded']}/{covs['CUTOFF_SETTLED_PROJECTION']['n_input']})",
                flush=True,
            )
        r1b_results[bid] = vdict

    print("\n=== 4. Independent Subprocess Process Memory Probe ===", flush=True)
    mem_probes = run_isolated_subprocess_memory_probes()
    for row in mem_probes["runs"]:
        print(
            f"  [mem {row['arm']:<3} {row['mode']:<26} {row['workload']:<18}] "
            f"peak_ws={row['peak_working_set_bytes'] / (1024*1024):.2f} MiB "
            f"tm_peak={row['tracemalloc_peak_bytes'] / 1024:.1f} KB",
            flush=True,
        )

    # Evaluate formal R1 verdicts separately per roadmap §7.3 & §8
    a_g508_vs_a = r1a_confirm["singles"]["G508_Peer_000"]["uncached_tuple"]["paired_R1_vs_A"]["paired_median_reduction_pct"]
    a_d48_vs_a = r1a_confirm["batches"]["D48_Real_47pairs"]["uncached_tuple"]["paired_R1_vs_A"]["paired_median_reduction_pct"]
    a_g508_vs_k = r1a_confirm["singles"]["G508_Peer_000"]["uncached_tuple"]["paired_R1_vs_K"]["paired_median_reduction_pct"]
    a_d48_vs_k = r1a_confirm["batches"]["D48_Real_47pairs"]["uncached_tuple"]["paired_R1_vs_K"]["paired_median_reduction_pct"]
    a_guard_regs = []
    for sec in ("singles", "batches"):
        for wk, wv in r1a_confirm[sec].items():
            for kd, kv in wv.items():
                for ref_key in ("paired_R1_vs_K", "paired_R1_vs_A"):
                    ps = kv[ref_key]
                    reg_pct = -ps["paired_median_reduction_pct"]
                    delta_ms = ps["paired_median_delta_ms"]
                    if reg_pct > 5.0 and delta_ms > (5.0 if sec == "batches" else 1.0):
                        a_guard_regs.append((wk, kd, ref_key, reg_pct, delta_ms))
    a_verdict = "A_QUALIFIED" if (a_g508_vs_a > 5.0 and a_d48_vs_a > 5.0 and not a_guard_regs) else "BLOCKED_KEEP_K"

    d48_b0_red = r1b_results["D48_Real_47pairs"]["tuple_uncached_stable"]["paired_B0_vs_EXHAUSTIVE"]["paired_median_reduction_pct"]
    d48_set_red = r1b_results["D48_Real_47pairs"]["tuple_uncached_stable"]["paired_SETTLED_vs_EXHAUSTIVE"]["paired_median_reduction_pct"]
    asm_b0_red = r1b_results["Assembly24_Obj014_23pairs"]["tuple_uncached_stable"]["paired_B0_vs_EXHAUSTIVE"]["paired_median_reduction_pct"]
    asm_set_red = r1b_results["Assembly24_Obj014_23pairs"]["tuple_uncached_stable"]["paired_SETTLED_vs_EXHAUSTIVE"]["paired_median_reduction_pct"]
    if d48_set_red >= 10.0 and asm_set_red >= 10.0:
        b_verdict = "B_QUALIFIED_RESEARCH"
    elif asm_b0_red >= 10.0 and d48_b0_red >= 0.0 and d48_set_red < d48_b0_red - 5.0:
        b_verdict = "B_CUTOFF_ONLY_QUALIFIED_SETTLED_RESTRICTED"
    elif asm_b0_red >= 10.0 or asm_set_red >= 10.0 or d48_set_red >= 10.0:
        b_verdict = "B_RESTRICTED_RESEARCH"
    else:
        b_verdict = "B_REJECTED"

    if a_verdict != "A_QUALIFIED":
        combined_verdict = "BLOCKED_KEEP_K"
    elif b_verdict == "B_QUALIFIED_RESEARCH":
        combined_verdict = "A_AND_B_READY_FOR_RESTRICTED_EXPERIMENT"
    elif b_verdict in ("B_RESTRICTED_RESEARCH", "B_CUTOFF_ONLY_QUALIFIED_SETTLED_RESTRICTED"):
        combined_verdict = "A_READY_B_RESTRICTED_RESEARCH"
    else:
        combined_verdict = "A_ONLY_READY_FOR_EXPERIMENT"

    out = {
        "schema": "m3-bvh-kernel-044-r1-results-v1",
        "branch": "codex/m3-bvh-p4-traversal-cutoff-044",
        "environment": {**_win32_env_info(), "clock_resolution_ns": time.get_clock_info("perf_counter").resolution * 1e9},
        "arm_identities": {
            arm.name: {
                "runtime_source_sha256": arm.source_sha256,
                "surface_geometry_sha256": arm.sg_raw_sha256,
                "surface_proximity_sha256": arm.sp_raw_sha256,
            }
            for arm in (arm_a, arm_k, arm_044, arm_r1)
        },
        "manifest_sha256": _sha256_json(manifest_cases),
        "r1a_paired_confirm": r1a_confirm,
        "r1b_batch_qualification": r1b_results,
        "independent_process_memory_probes": mem_probes,
        "verdicts": {
            "a_verdict": a_verdict,
            "b_verdict": b_verdict,
            "combined_verdict": combined_verdict,
            "a_g508_paired_reduction_vs_a_pct": a_g508_vs_a,
            "a_d48_paired_reduction_vs_a_pct": a_d48_vs_a,
            "a_g508_paired_reduction_vs_k_pct": a_g508_vs_k,
            "a_d48_paired_reduction_vs_k_pct": a_d48_vs_k,
            "d48_b0_vs_exh_pct": d48_b0_red,
            "d48_settled_vs_exh_pct": d48_set_red,
            "asm24_b0_vs_exh_pct": asm_b0_red,
            "asm24_settled_vs_exh_pct": asm_set_red,
            "a_material_guard_regressions": a_guard_regs,
        },
    }
    (BENCH_DIR / "KERNEL_044_R1_RESULTS.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nDONE 044-R1. Verdicts={json.dumps(out['verdicts'])}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

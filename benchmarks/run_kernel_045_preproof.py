"""M3 BVH 045 Exact Pre-Tree Cross-Pair Separation Benchmark & Qualification.

Pins:
  - A      : Frozen 041       (119327bbb4e645c5de3bfbc0d30259736b9a2677)
  - K      : Frozen 042-P2    (b5b0df58bed75f3a259af8078630e1cb511ff769)
  - 044_R1 : Frozen 044-R1    (f4d7b762f555bafa1e7585dd43e95a45f6004c33)
  - 045    : Live codex/m3-bvh-exact-batch-preproof-045 candidate
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import gc
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import time
import tracemalloc
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.bvh_eval import _surface_sig, _work_summary
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
from benchmarks.run_kernel_044_r1_qualification import (
    FROZEN_ARM_K_COMMIT,
    FROZEN_ARM_K_RUNTIME_SHA,
    _check,
    _is_sha256,
    _key_to_frac,
    _load_real_batch_fixtures,
    _paired_stats,
    build_receipt_digest,
    ensure_frozen_arm,
)
from human_eye_plugin import surface_batch_preproof as sbp

BENCH_DIR = Path(__file__).resolve().parent
FROZEN_044_R1_COMMIT = "f4d7b762f555bafa1e7585dd43e95a45f6004c33"
FROZEN_044_R1_RUNTIME_SHA = "8825f1eb8e2ebca55ba2c97fc32a425a34865fb5697b4f5b301ad3f33692b897"


def _box_mesh(oid: str, x0: float, y0: float, z0: float, x1: float, y1: float, z1: float):
    verts = (
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    )
    faces = (
        (0, 1, 2), (0, 2, 3), (4, 5, 6), (4, 6, 7),
        (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
        (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
    )
    return SimpleNamespace(object_id=oid, name=oid, vertices=verts, faces=faces)


def build_045_guard_batches() -> dict:
    """Construct adversarial negative-proof, small-batch, and tied-contact guards."""
    # 1. HighOverlap_Interleaved_16pairs: large shells enclosing overlapping interleaving strips -> 0 preproof wins
    ho_target = _box_mesh("HO_Target", -2.0, -2.0, -0.05, 2.0, 2.0, 0.05)
    ho_peers = []
    for k in range(16):
        off = 0.05 * (k + 1)
        ho_peers.append(_box_mesh(f"ho_{k:02d}", -2.5 + 0.02 * k, -2.5 + 0.02 * k, 0.05 + off, 2.5 - 0.02 * k, 2.5 - 0.02 * k, 0.25 + off))
        # Wrap corners so its convex hull encloses ho_target in X/Y/Z while closest gap sits at Z > 0.05
    # Add diagonal corner whiskers on ho_peers[1:] so AABB + incumbent Z axis BOTH overlap target Z range [-0.05, 0.05]!
    ho_wrapped = [ho_peers[0]]  # peer 0 gives Z incumbent axis gap=0.05
    for k in range(1, 16):
        gap_z = 0.1 + 0.03 * k
        # Main face at Z=[gap_z, gap_z+0.2], plus two non-intersecting whiskers extending to Z=-1.0 outside target X/Y!
        # Since whiskers sit outside X in [-2,2] but overlap Z in [-1, 1], convex intervals in X, Y, Z, and Z-axis ALL overlap!
        verts = (
            (-0.5, -0.5, gap_z), (0.5, -0.5, gap_z), (0.5, 0.5, gap_z), (-0.5, 0.5, gap_z),
            (3.0, 3.0, -1.0), (3.5, 3.0, -1.0), (3.2, 3.5, -1.0), (3.2, 3.2, 1.0),
        )
        faces = (
            (0, 1, 2), (0, 2, 3),
            (4, 5, 6), (4, 5, 7), (5, 6, 7), (6, 4, 7),
        )
        ho_wrapped.append(SimpleNamespace(object_id=f"ho_{k:02d}", name=f"ho_{k:02d}", vertices=verts, faces=faces))

    # 2. SmallBatch_12F_Linear_10pairs: 10 light 12F close-by boxes with overlapping AABBs where preproof fails/close
    sb_target = _box_mesh("SB_Target", 0.0, 0.0, 0.0, 1.0, 1.0, 1.0)
    sb_peers = [_box_mesh(f"sb_{k:02d}", 0.1 * k, -0.1, 1.2 + 0.05 * k, 1.1 + 0.1 * k, 0.9, 2.2 + 0.05 * k) for k in range(10)]

    # 3. TiedContact_12pairs: 12 zero/positive tied peers + distractors
    tc_target = SimpleNamespace(object_id="TC_Target", name="TC_Target", vertices=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)), faces=((0, 1, 2),))
    tc_peers = []
    for k in range(12):
        z = 1.5 if k % 2 == 0 else -1.5
        dx = 0.04 * k
        tc_peers.append(SimpleNamespace(
            object_id=f"tc_{k:02d}", name=f"tc_{k:02d}",
            vertices=((dx, 0.0, z), (1.0 + dx, 0.0, z), (dx, 1.0, z)), faces=((0, 1, 2),),
        ))
    tc_peers.extend([
        SimpleNamespace(object_id="tc_far0", name="tc_far0", vertices=((0.0, 0.0, 9.0), (1.0, 0.0, 9.0), (0.0, 1.0, 9.0)), faces=((0, 1, 2),)),
        SimpleNamespace(object_id="tc_far1", name="tc_far1", vertices=((0.0, 0.0, -11.0), (1.0, 0.0, -11.0), (0.0, 1.0, -11.0)), faces=((0, 1, 2),)),
    ])

    return {
        "HighOverlap_Interleaved_16pairs": {"target": ho_target, "peers": ho_wrapped, "peer_ids": [p.object_id for p in ho_wrapped]},
        "SmallBatch_12F_Linear_10pairs": {"target": sb_target, "peers": sb_peers, "peer_ids": [p.object_id for p in sb_peers]},
        "TiedContact_12pairs": {"target": tc_target, "peers": tc_peers, "peer_ids": [p.object_id for p in tc_peers]},
    }


def serialize_045_batch_receipt(
    *,
    arm_name: str,
    runtime_source_sha256: str,
    input_sha256: str,
    options_sha256: str,
    batch_out: dict,
) -> dict:
    """Create canonical 045 batch receipt covering pretree_root_aabb and pretree_root_axis."""
    outcomes_summary = {}
    for pid, o in batch_out["outcomes_by_id"].items():
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
            pk = o["proof_kind"]
            if pk == "pretree_root_aabb":
                compact_receipt = {
                    "box_a": pr.get("box_a"),
                    "box_b": pr.get("box_b"),
                    "common_exp": pr.get("common_exp"),
                    "aabb_gap_sq_int": pr.get("aabb_gap_sq_int"),
                    "upper_bound_sq_key": pr.get("upper_bound_sq_key"),
                    "strict_inequality_verified": pr.get("strict_inequality_verified"),
                }
            elif pk == "pretree_root_axis":
                compact_receipt = {
                    "axis": pr.get("axis"),
                    "axis_norm_sq": pr.get("axis_norm_sq"),
                    "target_interval": pr.get("target_interval"),
                    "peer_interval": pr.get("peer_interval"),
                    "common_exp": pr.get("common_exp"),
                    "gap_int": pr.get("gap_int"),
                    "upper_bound_sq_key": pr.get("upper_bound_sq_key"),
                    "strict_inequality_verified": pr.get("strict_inequality_verified"),
                    "axis_epoch": pr.get("axis_epoch"),
                    "axis_source_peer_id": pr.get("axis_source_peer_id"),
                }
            else:
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
            ws = _work_summary(o.get("work", {}))
            ws["tree_builds"] = o.get("work", {}).get("tree_builds", 0)
            ws["prepared_triangles"] = o.get("work", {}).get("prepared_triangles", 0)
            outcomes_summary[pid] = {
                "result_kind": rk,
                "disposition": o["disposition"],
                "snapshot_identity": o["snapshot_identity"],
                "source_identity": o.get("source_identity"),
                "exact_upper_bound_key": list(o["exact_upper_bound_key"]),
                "upper_bound_origin": o.get("upper_bound_origin"),
                "proof_kind": pk,
                "proof_receipt": compact_receipt,
                "work_summary": ws,
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
        "schema": "m3-bvh-045-batch-receipt-v1",
        "arm": arm_name,
        "runtime_source_sha256": runtime_source_sha256,
        "input_sha256": input_sha256,
        "options_sha256": options_sha256,
        "snapshot_identity": batch_out["snapshot_identity"],
        "cutoff_mode": batch_out["cutoff_mode"],
        "preproof_mode": batch_out.get("preproof_mode", "NONE"),
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


def _validate_045_single_receipt(receipt: dict, expected_manifest: dict, expected_pin: str, label: str) -> None:
    req = {
        "schema", "arm", "runtime_source_sha256", "input_sha256", "options_sha256",
        "snapshot_identity", "peer_ids", "status", "nearest_ids",
        "best_exact_distance_sq", "coverage", "outcomes_by_id", "digest_sha256",
    }
    _check(type(receipt) is dict and req <= set(receipt), f"{label}: missing required receipt fields")
    _check(receipt["schema"] == "m3-bvh-045-batch-receipt-v1", f"{label}: wrong schema")
    _check(_is_sha256(receipt["runtime_source_sha256"]), f"{label}: invalid runtime_source_sha256")
    _check(receipt["runtime_source_sha256"] == expected_pin,
           f"{label}: runtime pin mismatch {receipt['runtime_source_sha256']} != {expected_pin}")
    _check(_is_sha256(receipt["input_sha256"]) and receipt["input_sha256"] == expected_manifest["input_sha256"],
           f"{label}: input_sha256 mismatch")
    _check(_is_sha256(receipt["options_sha256"]), f"{label}: invalid options_sha256")
    _check(receipt["digest_sha256"] == build_receipt_digest(receipt), f"{label}: digest_sha256 mismatch")

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
            _check(
                pk in ("root_aabb", "root_axis", "complete_cutoff_traversal", "pretree_root_aabb", "pretree_root_axis"),
                f"{label}.{pid}: invalid proof_kind {pk!r}",
            )
            pr = o.get("proof_receipt")
            _check(type(pr) is dict, f"{label}.{pid}: missing proof_receipt")
            if pk == "root_aabb":
                lc = pr.get("local_cutoff")
                _check(type(lc) is list and len(lc) == 2 and lc[1] > 0, f"{label}.{pid}: bad root_aabb local_cutoff")
                _check(pr.get("strict_inequality_verified") is True
                       and type(pr.get("aabb_gap_sq")) is int
                       and pr["aabb_gap_sq"] * lc[1] > lc[0],
                       f"{label}.{pid}: root_aabb inequality not strictly verified")
            elif pk == "pretree_root_aabb":
                ws = o.get("work_summary", {})
                _check(ws.get("tree_builds", 0) == 0 and ws.get("prepared_triangles", 0) == 0,
                       f"{label}.{pid}: pretree_root_aabb must not build tree or prepare triangles")
                gap_sq = pr.get("aabb_gap_sq_int")
                ce_exp = pr.get("common_exp")
                uk = pr.get("upper_bound_sq_key")
                _check(
                    pr.get("strict_inequality_verified") is True
                    and type(gap_sq) is int and gap_sq > 0
                    and type(ce_exp) is int
                    and list(o["exact_upper_bound_key"]) == list(uk or []),
                    f"{label}.{pid}: malformed pretree_root_aabb receipt",
                )
                un, ud, ue = uk
                gt, err = sbp._strict_dyadic_gt(gap_sq * ud, un, 2 * ce_exp - ue)
                _check(err is None and gt is True, f"{label}.{pid}: pretree_root_aabb strict inequality failed")
            elif pk == "pretree_root_axis":
                ws = o.get("work_summary", {})
                _check(ws.get("tree_builds", 0) == 0 and ws.get("prepared_triangles", 0) == 0,
                       f"{label}.{pid}: pretree_root_axis must not build tree or prepare triangles")
                ax = pr.get("axis")
                norm2 = pr.get("axis_norm_sq")
                t_int = pr.get("target_interval")
                p_int = pr.get("peer_interval")
                gap_int = pr.get("gap_int")
                ce_exp = pr.get("common_exp")
                uk = pr.get("upper_bound_sq_key")
                _check(
                    pr.get("strict_inequality_verified") is True
                    and type(ax) in (list, tuple) and len(ax) == 3 and all(type(v) is int for v in ax)
                    and any(v != 0 for v in ax)
                    and type(norm2) is int and norm2 == ax[0] * ax[0] + ax[1] * ax[1] + ax[2] * ax[2]
                    and type(t_int) in (list, tuple) and len(t_int) == 2 and all(type(v) is int for v in t_int) and t_int[0] <= t_int[1]
                    and type(p_int) in (list, tuple) and len(p_int) == 2 and all(type(v) is int for v in p_int) and p_int[0] <= p_int[1]
                    and type(gap_int) is int and gap_int > 0
                    and gap_int == max(0, p_int[0] - t_int[1], t_int[0] - p_int[1])
                    and type(ce_exp) is int
                    and list(o["exact_upper_bound_key"]) == list(uk or []),
                    f"{label}.{pid}: invalid pretree_root_axis receipt fields",
                )
                un, ud, ue = uk
                gt, err = sbp._strict_dyadic_gt(gap_int * gap_int * ud, un * norm2, 2 * ce_exp - ue)
                _check(err is None and gt is True, f"{label}.{pid}: pretree_root_axis strict inequality failed")
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
        _check(set(receipt["nearest_ids"]) == set(min_measured_pids), f"{label}: nearest_ids set mismatch")
        _check(receipt["nearest_ids"] == sorted(min_measured_pids) or receipt["nearest_ids"] == min_measured_pids,
               f"{label}: nearest_ids invalid order")
        bf = _key_to_frac(receipt["best_exact_distance_sq"])
        _check(bf == best_sq_frac, f"{label}: best_exact_distance_sq != min measured")
    elif st == "partial":
        _check(receipt["nearest_ids"] is None, f"{label}: partial must have nearest_ids=None")
        _check(cnt_un > 0 and cnt_m > 0, f"{label}: partial inconsistent with coverage")
    elif st == "unknown":
        _check(receipt["nearest_ids"] is None and cnt_m == 0, f"{label}: unknown inconsistent with coverage")
    else:
        raise ValueError(f"{label}: invalid batch status {st!r}")


def validate_045_batch_receipt_comparison(
    baseline_receipt: dict,
    candidate_receipt: dict,
    expected_manifest: dict,
    expected_pins: dict,
) -> dict:
    """Hardened fail-closed 045 receipt comparator (no bare assert)."""
    _check(type(expected_manifest) is dict and _is_sha256(expected_manifest.get("input_sha256")),
           "invalid expected_manifest")
    _check(type(baseline_receipt) is dict and type(candidate_receipt) is dict, "receipts must be dicts")
    b_arm = baseline_receipt.get("arm")
    c_arm = candidate_receipt.get("arm")
    _check(b_arm in expected_pins and c_arm in expected_pins, f"unknown arm in expected_pins: {b_arm!r}, {c_arm!r}")

    _validate_045_single_receipt(baseline_receipt, expected_manifest, expected_pins[b_arm], f"baseline[{b_arm}]")
    _validate_045_single_receipt(candidate_receipt, expected_manifest, expected_pins[c_arm], f"candidate[{c_arm}]")

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


def _run_mem_worker(arm_key: str, mode_spec: str, workload_name: str) -> dict:
    """Isolated child process OS PeakWorkingSetSize & tracemalloc probe."""
    wl = build_042_workloads()
    real = _load_real_batch_fixtures()
    guards = build_045_guard_batches()
    all_b = {
        "D48_Real_47pairs": {"target": wl["batches"][0]["tuple_batch"][0], "peers": wl["batches"][0]["tuple_batch"][1],
                             "peer_ids": [f"peer_{i}" for i in range(47)]},
        "G508_Retained_11pairs": real["G508_Retained_11pairs"],
        "HighOverlap_Interleaved_16pairs": guards["HighOverlap_Interleaved_16pairs"],
    }
    b = all_b[workload_name]
    tg, ps, pids = b["target"], b["peers"], b["peer_ids"]

    if arm_key == "044_R1":
        arm = load_arm_modules("044_R1", ensure_frozen_arm(FROZEN_044_R1_COMMIT, "arm_044_r1", FROZEN_044_R1_RUNTIME_SHA))
        activate_arm(arm)
        fn = lambda: arm.sp.measure_nearest_surface_batch(
            tg, ps, NOOP, peer_ids=pids, cutoff_mode="CUTOFF_SETTLED_PROJECTION", sort_policy="stable"
        )
    else:
        arm = load_arm_modules("045", ROOT)
        activate_arm(arm)
        if mode_spec == "EXHAUSTIVE":
            fn = lambda: arm.sp.measure_nearest_surface_batch(
                tg, ps, NOOP, peer_ids=pids, cutoff_mode="EXHAUSTIVE", sort_policy="stable"
            )
        else:
            fn = lambda: arm.sp.measure_nearest_surface_batch(
                tg, ps, NOOP, peer_ids=pids, cutoff_mode="CUTOFF_SETTLED_PROJECTION",
                preproof_mode=mode_spec, sort_policy="stable",
            )

    _ = fn()
    gc.collect()
    before = _win32_process_mem()
    tracemalloc.start()
    for _ in range(3):
        _ = fn()
    _, tm_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    after = _win32_process_mem()
    return {
        "arm": arm_key,
        "mode": mode_spec,
        "workload": workload_name,
        "runtime_source_sha256": arm.source_sha256,
        "tracemalloc_peak_bytes": int(tm_peak),
        "before": before,
        "after": after,
        "peak_working_set_bytes": after.get("peak_working_set_bytes"),
        "working_set_bytes": after.get("working_set_bytes"),
    }


def _profile_residual_build_cost(arm_045, batch_inputs: dict, winner_preproof: str) -> dict:
    """Measure isolated exclusive wall breakdown under 045 winner for §10 residual-build gate."""
    from unittest.mock import patch

    activate_arm(arm_045)
    sg_mod = arm_045.sg
    sp_mod = arm_045.sp
    sbp_mod = arm_045.mods["human_eye_plugin.surface_batch_preproof"]
    res = {}

    orig_build = sg_mod._build_sah_bvh
    orig_compile = sp_mod._compile_bvh_node
    orig_trans_bvh = sp_mod._translate_bvh
    orig_int_frame = sp_mod._integer_frame
    orig_cac_frame = sp_mod._ensure_cached_frame
    orig_trans_tri = sp_mod._translate_triangles
    orig_search = sp_mod._nearest_tree
    orig_aabb = sbp_mod.check_pretree_root_aabb_exclusion
    orig_axis = sbp_mod.check_pretree_root_axis_exclusion

    profile_bids = (
        "D48_Real_47pairs",
        "Assembly24_Obj014_23pairs",
        "G508_Retained_11pairs",
        "G60_D12_Retained_11pairs",
        "HighOverlap_Interleaved_16pairs",
    )
    for bid in profile_bids:
        b = batch_inputs[bid]
        tg, ps, pids = b["target"], b["peers"], b["peer_ids"]
        mode_map = {}
        mode_list = (("cached", True), ("uncached", False)) if bid != "HighOverlap_Interleaved_16pairs" else (("cached", True),)
        for cname, use_c in mode_list:
            spans = {
                "total": [],
                "build_sah": [],
                "bvh_compile_translate": [],
                "prep_frame_tri": [],
                "search_tree": [],
                "preproof": [],
            }
            for rep in range(5):
                acc = {k: 0.0 for k in spans if k != "total"}
                depth_build = 0
                depth_compile = 0

                def wrap_build(*a, **kw):
                    nonlocal depth_build
                    top = (depth_build == 0)
                    depth_build += 1
                    t0 = time.perf_counter_ns() if top else 0
                    try:
                        return orig_build(*a, **kw)
                    finally:
                        depth_build -= 1
                        if top:
                            acc["build_sah"] += (time.perf_counter_ns() - t0) / 1e6

                def wrap_compile(*a, **kw):
                    nonlocal depth_compile
                    top = (depth_compile == 0)
                    depth_compile += 1
                    t0 = time.perf_counter_ns() if top else 0
                    try:
                        return orig_compile(*a, **kw)
                    finally:
                        depth_compile -= 1
                        if top:
                            acc["bvh_compile_translate"] += (time.perf_counter_ns() - t0) / 1e6

                def wrap_trans_bvh(*a, **kw):
                    t0 = time.perf_counter_ns()
                    try:
                        return orig_trans_bvh(*a, **kw)
                    finally:
                        acc["bvh_compile_translate"] += (time.perf_counter_ns() - t0) / 1e6

                def wrap_int_frame(*a, **kw):
                    t0 = time.perf_counter_ns()
                    try:
                        return orig_int_frame(*a, **kw)
                    finally:
                        acc["prep_frame_tri"] += (time.perf_counter_ns() - t0) / 1e6

                def wrap_cac_frame(*a, **kw):
                    t0 = time.perf_counter_ns()
                    try:
                        return orig_cac_frame(*a, **kw)
                    finally:
                        acc["prep_frame_tri"] += (time.perf_counter_ns() - t0) / 1e6

                def wrap_trans_tri(*a, **kw):
                    t0 = time.perf_counter_ns()
                    try:
                        return orig_trans_tri(*a, **kw)
                    finally:
                        acc["prep_frame_tri"] += (time.perf_counter_ns() - t0) / 1e6

                def wrap_search(*a, **kw):
                    t0 = time.perf_counter_ns()
                    try:
                        return orig_search(*a, **kw)
                    finally:
                        acc["search_tree"] += (time.perf_counter_ns() - t0) / 1e6

                def wrap_aabb(*a, **kw):
                    t0 = time.perf_counter_ns()
                    try:
                        return orig_aabb(*a, **kw)
                    finally:
                        acc["preproof"] += (time.perf_counter_ns() - t0) / 1e6

                def wrap_axis(*a, **kw):
                    t0 = time.perf_counter_ns()
                    try:
                        return orig_axis(*a, **kw)
                    finally:
                        acc["preproof"] += (time.perf_counter_ns() - t0) / 1e6

                with patch.object(sg_mod, "_build_sah_bvh", wrap_build), \
                     patch.object(sp_mod, "_compile_bvh_node", wrap_compile), \
                     patch.object(sp_mod, "_translate_bvh", wrap_trans_bvh), \
                     patch.object(sp_mod, "_integer_frame", wrap_int_frame), \
                     patch.object(sp_mod, "_ensure_cached_frame", wrap_cac_frame), \
                     patch.object(sp_mod, "_translate_triangles", wrap_trans_tri), \
                     patch.object(sp_mod, "_nearest_tree", wrap_search), \
                     patch.object(sbp_mod, "check_pretree_root_aabb_exclusion", wrap_aabb), \
                     patch.object(sbp_mod, "check_pretree_root_axis_exclusion", wrap_axis):
                    t0 = time.perf_counter_ns()
                    sp_mod.measure_nearest_surface_batch(
                        tg, ps, NOOP, peer_ids=pids, cutoff_mode="CUTOFF_SETTLED_PROJECTION",
                        preproof_mode=winner_preproof, sort_policy="stable", use_mesh_cache=use_c,
                    )
                    tot = (time.perf_counter_ns() - t0) / 1e6
                if rep >= 2:
                    spans["total"].append(tot)
                    for k, v in acc.items():
                        spans[k].append(v)

            med_tot = statistics.median(spans["total"])
            med_bld = statistics.median(spans["build_sah"])
            med_cmp = statistics.median(spans["bvh_compile_translate"])
            med_prep = statistics.median(spans["prep_frame_tri"])
            med_src = statistics.median(spans["search_tree"])
            med_pre = statistics.median(spans["preproof"])
            mode_map[cname] = {
                "median_total_ms": round(med_tot, 4),
                "median_build_sah_ms": round(med_bld, 4),
                "median_bvh_compile_translate_ms": round(med_cmp, 4),
                "median_prep_frame_tri_ms": round(med_prep, 4),
                "median_search_tree_ms": round(med_src, 4),
                "median_preproof_ms": round(med_pre, 4),
                "residual_build_pct": round((med_bld / med_tot) * 100.0, 2) if med_tot > 0 else 0.0,
                "residual_build_all_pct": round(((med_bld + med_cmp) / med_tot) * 100.0, 2) if med_tot > 0 else 0.0,
                "residual_prep_plus_build_pct": round(((med_bld + med_cmp + med_prep) / med_tot) * 100.0, 2) if med_tot > 0 else 0.0,
            }
        res[bid] = mode_map
    return res


class _SpecArm:
    def __init__(self, name, base_arm, cmode, pmode, use_cache, sort_pol, tg, ps, pids):
        self.name = name
        self.mods = base_arm.mods
        self.base_arm = base_arm
        self.cmode = cmode
        self.pmode = pmode
        self.use_cache = use_cache
        self.sort_pol = sort_pol
        self.tg = tg
        self.ps = ps
        self.pids = pids

    def run(self):
        if self.pmode is None:
            return self.base_arm.sp.measure_nearest_surface_batch(
                self.tg, self.ps, NOOP, peer_ids=self.pids,
                cutoff_mode=self.cmode, sort_policy=self.sort_pol,
                use_mesh_cache=self.use_cache, retain_witness_triangles=True,
            )
        return self.base_arm.sp.measure_nearest_surface_batch(
            self.tg, self.ps, NOOP, peer_ids=self.pids,
            cutoff_mode=self.cmode, preproof_mode=self.pmode, sort_policy=self.sort_pol,
            use_mesh_cache=self.use_cache, retain_witness_triangles=True,
        )


def _batch_input_sha(tg, ps) -> str:
    return _sha256_json([list(tg.vertices), list(tg.faces)] + [[list(p.vertices), list(p.faces)] for p in ps])


def main() -> int:
    parser = argparse.ArgumentParser(description="M3 BVH 045 Exact Pre-Tree Cross-Pair Separation Qualification")
    parser.add_argument("--screen-repeats", type=int, default=7)
    parser.add_argument("--confirm-repeats", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--mem-worker", nargs=3, metavar=("ARM", "MODE", "WORKLOAD"))
    args = parser.parse_args()

    if args.mem_worker:
        print(json.dumps(_run_mem_worker(*args.mem_worker)))
        return 0

    arm_044_r1 = load_arm_modules("044_R1", ensure_frozen_arm(FROZEN_044_R1_COMMIT, "arm_044_r1", FROZEN_044_R1_RUNTIME_SHA))
    arm_045 = load_arm_modules("045", ROOT)
    _check(arm_044_r1.source_sha256 == FROZEN_044_R1_RUNTIME_SHA, "Frozen 044-R1 SHA mismatch")

    workloads = build_042_workloads()
    real_batches = _load_real_batch_fixtures()
    guard_batches = build_045_guard_batches()

    batch_inputs = {
        "D48_Real_47pairs": {
            "target": workloads["batches"][0]["tuple_batch"][0],
            "peers": workloads["batches"][0]["tuple_batch"][1],
            "peer_ids": [f"peer_{i}" for i in range(47)],
            "ndarray_target": workloads["batches"][0]["ndarray_batch"][0],
            "ndarray_peers": workloads["batches"][0]["ndarray_batch"][1],
            "provenance": "benchmark_real_d48_47",
        },
        "Assembly24_Obj014_23pairs": {
            "target": workloads["batches"][1]["tuple_batch"][0],
            "peers": workloads["batches"][1]["tuple_batch"][1],
            "peer_ids": [f"peer_{i}" for i in range(23)],
            "ndarray_target": workloads["batches"][1]["ndarray_batch"][0],
            "ndarray_peers": workloads["batches"][1]["ndarray_batch"][1],
            "provenance": "benchmark_assembly24_23",
        },
        "G508_Retained_11pairs": {**real_batches["G508_Retained_11pairs"], "provenance": "real_frozen_scene_snapshot"},
        "G60_D12_Retained_11pairs": {**real_batches["G60_D12_Retained_11pairs"], "provenance": "real_frozen_scene_snapshot"},
        **{k: {**v, "provenance": "constructed_045_guard"} for k, v in guard_batches.items()},
    }
    for bid, bspec in batch_inputs.items():
        bspec["input_sha256"] = _batch_input_sha(bspec["target"], bspec["peers"])

    cases_manifest = {
        "schema": "m3-bvh-045-cases-v1",
        "expected_pins": {
            "A": {"commit": FROZEN_COMMIT, "runtime_source_sha256": FROZEN_RUNTIME_SHA},
            "K": {"commit": FROZEN_ARM_K_COMMIT, "runtime_source_sha256": FROZEN_ARM_K_RUNTIME_SHA},
            "044_R1": {"commit": FROZEN_044_R1_COMMIT, "runtime_source_sha256": FROZEN_044_R1_RUNTIME_SHA},
            "045_candidate": {"branch": "codex/m3-bvh-exact-batch-preproof-045", "runtime_source_sha256": arm_045.source_sha256},
        },
        "historical_private_fixtures": {
            "zero489": "MISSING_HISTORICAL_INPUT",
            "first_yield": "MISSING_HISTORICAL_INPUT",
            "pair129": "MISSING_HISTORICAL_INPUT",
            "040_closed_solid": "MISSING_HISTORICAL_INPUT",
            "B02_10_retained_subset": "MISSING_HISTORICAL_INPUT",
        },
        "batches": [
            {
                "id": bid,
                "provenance": bspec["provenance"],
                "pair_count": len(bspec["peers"]),
                "input_sha256": bspec["input_sha256"],
                "peer_ids": bspec["peer_ids"],
            }
            for bid, bspec in batch_inputs.items()
        ],
    }
    (BENCH_DIR / "KERNEL_045_CASES.json").write_text(json.dumps(cases_manifest, indent=2), encoding="utf-8")

    # Stage 1: Screening (7 repeats)
    print(f"=== Stage 1: 045 Screening ({args.screen_repeats} repeats, stable order) ===", flush=True)
    screen_workloads = (
        "D48_Real_47pairs",
        "Assembly24_Obj014_23pairs",
        "G508_Retained_11pairs",
        "G60_D12_Retained_11pairs",
        "HighOverlap_Interleaved_16pairs",
        "SmallBatch_12F_Linear_10pairs",
    )
    screen_specs = [
        ("R_EXH", arm_045, "EXHAUSTIVE", "NONE"),
        ("B0_SETTLED_R1", arm_044_r1, "CUTOFF_SETTLED_PROJECTION", None),
        ("B1_AABB", arm_045, "CUTOFF_SETTLED_PROJECTION", "B1_ROOT_AABB"),
        ("B2_INC_AXIS", arm_045, "CUTOFF_SETTLED_PROJECTION", "B2_INCUMBENT_AXIS"),
        ("B3_MEMO_AXIS", arm_045, "CUTOFF_SETTLED_PROJECTION", "B3_TARGET_MEMO_AXIS"),
        ("B4_MULTI_AXIS", arm_045, "CUTOFF_SETTLED_PROJECTION", "B4_BOUNDED_MULTI_AXIS"),
    ]
    screening = {}
    for bid in screen_workloads:
        bspec = batch_inputs[bid]
        tg, ps, pids = bspec["target"], bspec["peers"], bspec["peer_ids"]
        ext_manifest = {"input_sha256": bspec["input_sha256"], "peer_ids": pids}
        arms = [_SpecArm(an, ba, cm, pm, True, "stable", tg, ps, pids) for an, ba, cm, pm in screen_specs]

        receipts = {}
        covs = {}
        opt_sha = _sha256_json({"sort_policy": "stable", "use_mesh_cache": True, "retain_witness": True})
        pins = {an: ba.source_sha256 for an, ba, _, _ in screen_specs}
        for sa in arms:
            activate_arm(sa.base_arm)
            bo = sa.run()
            covs[sa.name] = bo["coverage"]
            rec = serialize_045_batch_receipt(
                arm_name=sa.name, runtime_source_sha256=sa.base_arm.source_sha256,
                input_sha256=bspec["input_sha256"], options_sha256=opt_sha, batch_out=bo,
            )
            receipts[sa.name] = rec
            if sa.name != "R_EXH":
                validate_045_batch_receipt_comparison(
                    receipts["R_EXH"], rec, {**ext_manifest, "options_sha256": opt_sha}, pins,
                )

        pt = run_paired_timing(
            arms, lambda sa: sa.run, warmup=args.warmup, repeats=args.screen_repeats,
            sig_fn=lambda bo: (bo["status"], tuple(bo["nearest_ids"] or []), tuple(bo["best_exact_distance_sq"] or [])),
        )
        r1_s = pt["arms"]["B0_SETTLED_R1"]["timing"]["raw_wall_ms"]
        exh_s = pt["arms"]["R_EXH"]["timing"]["raw_wall_ms"]
        deltas_vs_r1 = {an: _paired_stats(r1_s, pt["arms"][an]["timing"]["raw_wall_ms"]) for an, *_ in screen_specs if an != "B0_SETTLED_R1"}
        deltas_vs_exh = {an: _paired_stats(exh_s, pt["arms"][an]["timing"]["raw_wall_ms"]) for an, *_ in screen_specs if an != "R_EXH"}
        screening[bid] = {
            "arms": pt["arms"],
            "coverages": covs,
            "paired_vs_044_R1": deltas_vs_r1,
            "paired_vs_EXH": deltas_vs_exh,
        }
        print(
            f"  [Screen {bid:<31}] EXH={pt['arms']['R_EXH']['timing']['median_ms']:6.2f} "
            f"R1={pt['arms']['B0_SETTLED_R1']['timing']['median_ms']:6.2f} | "
            f"B1={pt['arms']['B1_AABB']['timing']['median_ms']:6.2f} "
            f"B2={pt['arms']['B2_INC_AXIS']['timing']['median_ms']:6.2f} "
            f"B3={pt['arms']['B3_MEMO_AXIS']['timing']['median_ms']:6.2f}(vsR1:{deltas_vs_r1['B3_MEMO_AXIS']['paired_median_reduction_pct']:+.1f}%) "
            f"B4={pt['arms']['B4_MULTI_AXIS']['timing']['median_ms']:6.2f}(vsR1:{deltas_vs_r1['B4_MULTI_AXIS']['paired_median_reduction_pct']:+.1f}%)",
            flush=True,
        )

    # Deterministic screening winner selection
    real_4 = ("D48_Real_47pairs", "Assembly24_Obj014_23pairs", "G508_Retained_11pairs", "G60_D12_Retained_11pairs")
    b4_better_cnt = sum(
        1 for bid in real_4
        if _paired_stats(
            screening[bid]["arms"]["B3_MEMO_AXIS"]["timing"]["raw_wall_ms"],
            screening[bid]["arms"]["B4_MULTI_AXIS"]["timing"]["raw_wall_ms"],
        )["paired_median_reduction_pct"] >= 2.0
    )
    b4_guard_hurt = any(
        _paired_stats(
            screening[bid]["arms"]["B3_MEMO_AXIS"]["timing"]["raw_wall_ms"],
            screening[bid]["arms"]["B4_MULTI_AXIS"]["timing"]["raw_wall_ms"],
        )["paired_median_reduction_pct"] < -5.0
        for bid in ("HighOverlap_Interleaved_16pairs", "SmallBatch_12F_Linear_10pairs")
    )
    winner_mode = "B4_BOUNDED_MULTI_AXIS" if (b4_better_cnt >= 2 and not b4_guard_hurt) else "B3_TARGET_MEMO_AXIS"
    winner_label = "B4_MULTI_AXIS" if winner_mode == "B4_BOUNDED_MULTI_AXIS" else "B3_MEMO_AXIS"
    print(f"\n  Selected fixed Stage 2 winner: {winner_mode} (b4_better_cnt={b4_better_cnt}, b4_guard_hurt={b4_guard_hurt})", flush=True)

    # Stage 2: 30-Repeat Confirmation
    print(f"\n=== Stage 2: 045 Confirmation ({args.confirm_repeats} repeats) ===", flush=True)
    confirm = {}
    confirm_specs = [
        ("R_EXH", arm_045, "EXHAUSTIVE", "NONE"),
        ("B0_OFF", arm_045, "CUTOFF_ONLY_OFF", "NONE"),
        ("B0_SETTLED_R1", arm_044_r1, "CUTOFF_SETTLED_PROJECTION", None),
        (winner_label, arm_045, "CUTOFF_SETTLED_PROJECTION", winner_mode),
    ]
    pins_c = {an: ba.source_sha256 for an, ba, _, _ in confirm_specs}
    for bid in ("D48_Real_47pairs", "Assembly24_Obj014_23pairs", "G508_Retained_11pairs", "G60_D12_Retained_11pairs", "HighOverlap_Interleaved_16pairs", "SmallBatch_12F_Linear_10pairs", "TiedContact_12pairs"):
        bspec = batch_inputs[bid]
        ext_manifest = {"input_sha256": bspec["input_sha256"], "peer_ids": bspec["peer_ids"]}
        run_variants = [("tuple_cached_stable", bspec["target"], bspec["peers"], True, "stable")]
        if bid in real_4:
            run_variants.append(("tuple_uncached_stable", bspec["target"], bspec["peers"], False, "stable"))
        if "ndarray_target" in bspec:
            run_variants.append(("ndarray_cached_stable", bspec["ndarray_target"], bspec["ndarray_peers"], True, "stable"))
        if bid in ("D48_Real_47pairs", "Assembly24_Obj014_23pairs"):
            run_variants.append(("tuple_cached_referenced_aabb", bspec["target"], bspec["peers"], True, "referenced_aabb"))

        vdict = {}
        for vlabel, t_in, p_in, use_c, spol in run_variants:
            arms = [_SpecArm(an, ba, cm, pm, use_c, spol, t_in, p_in, bspec["peer_ids"]) for an, ba, cm, pm in confirm_specs]
            receipts = {}
            covs = {}
            opt_sha = _sha256_json({"sort_policy": spol, "use_mesh_cache": use_c, "retain_witness": True})
            for sa in arms:
                activate_arm(sa.base_arm)
                bo = sa.run()
                covs[sa.name] = bo["coverage"]
                rec = serialize_045_batch_receipt(
                    arm_name=sa.name, runtime_source_sha256=sa.base_arm.source_sha256,
                    input_sha256=bspec["input_sha256"], options_sha256=opt_sha, batch_out=bo,
                )
                receipts[sa.name] = rec
                if sa.name != "R_EXH":
                    validate_045_batch_receipt_comparison(
                        receipts["R_EXH"], rec, {**ext_manifest, "options_sha256": opt_sha}, pins_c,
                    )
            pt = run_paired_timing(
                arms, lambda sa: sa.run, warmup=args.warmup, repeats=args.confirm_repeats,
                sig_fn=lambda bo: (bo["status"], tuple(bo["nearest_ids"] or []), tuple(bo["best_exact_distance_sq"] or [])),
            )
            r1_s = pt["arms"]["B0_SETTLED_R1"]["timing"]["raw_wall_ms"]
            exh_s = pt["arms"]["R_EXH"]["timing"]["raw_wall_ms"]
            w_s = pt["arms"][winner_label]["timing"]["raw_wall_ms"]
            ps_vs_r1 = _paired_stats(r1_s, w_s)
            ps_vs_exh = _paired_stats(exh_s, w_s)
            vdict[vlabel] = {
                "arms": pt["arms"],
                "coverages": covs,
                "paired_045_vs_044_R1": ps_vs_r1,
                "paired_045_vs_EXH": ps_vs_exh,
                "receipt_digests": {k: v["digest_sha256"] for k, v in receipts.items()},
            }
            print(
                f"  [Confirm {bid:<30} {vlabel:<28}] EXH={pt['arms']['R_EXH']['timing']['median_ms']:6.2f} "
                f"R1={pt['arms']['B0_SETTLED_R1']['timing']['median_ms']:6.2f} "
                f"045={pt['arms'][winner_label]['timing']['median_ms']:6.2f}ms "
                f"(vsR1:{ps_vs_r1['paired_median_reduction_pct']:+5.1f}% [{ps_vs_r1['faster_count']}/{args.confirm_repeats}], "
                f"vsEXH:{ps_vs_exh['paired_median_reduction_pct']:+5.1f}%, "
                f"built={covs[winner_label]['n_trees_built']}/{covs[winner_label]['n_input']})",
                flush=True,
            )
        confirm[bid] = vdict

    # Stage 3: Independent Subprocess OS Memory Probes
    print("\n=== Stage 3: Independent Subprocess Memory Probes ===", flush=True)
    mem_jobs = [
        ("045", "EXHAUSTIVE", "D48_Real_47pairs"),
        ("044_R1", "CUTOFF_SETTLED_PROJECTION", "D48_Real_47pairs"),
        ("045", winner_mode, "D48_Real_47pairs"),
        ("045", "EXHAUSTIVE", "G508_Retained_11pairs"),
        ("044_R1", "CUTOFF_SETTLED_PROJECTION", "G508_Retained_11pairs"),
        ("045", winner_mode, "G508_Retained_11pairs"),
        ("044_R1", "CUTOFF_SETTLED_PROJECTION", "HighOverlap_Interleaved_16pairs"),
        ("045", winner_mode, "HighOverlap_Interleaved_16pairs"),
    ]
    mem_rows = []
    for ak, ms, wl_n in mem_jobs:
        proc = subprocess.run(
            [sys.executable, "-B", __file__, "--mem-worker", ak, ms, wl_n],
            cwd=str(ROOT), check=True, stdout=subprocess.PIPE, text=True,
        )
        row = json.loads(proc.stdout.strip().splitlines()[-1])
        mem_rows.append(row)
        print(
            f"  [mem {ak:<6} {ms:<24} {wl_n:<31}] "
            f"peak_ws={row['peak_working_set_bytes'] / (1024*1024):.2f} MiB tm={row['tracemalloc_peak_bytes'] / 1024:.1f} KB",
            flush=True,
        )

    # Stage 4: Residual Build-Cost Profile (§10 046 Gate Check)
    print("\n=== Stage 4: Residual Build-Cost Profile (§10 046 Gate Check) ===", flush=True)
    residual_profile = _profile_residual_build_cost(arm_045, batch_inputs, winner_mode)
    for bid, cmap in residual_profile.items():
        for cname, rp in cmap.items():
            print(
                f"  [Profile {bid:<31} {cname:<8}] total={rp['median_total_ms']:6.2f}ms "
                f"build_sah={rp['median_build_sah_ms']:6.2f}ms ({rp['residual_build_pct']:5.1f}%) "
                f"build_all={rp['residual_build_all_pct']:5.1f}% prep+build={rp['residual_prep_plus_build_pct']:5.1f}% "
                f"search={rp['median_search_tree_ms']:6.2f}ms pre={rp['median_preproof_ms']:5.2f}ms",
                flush=True,
            )

    # Evaluate formal 045 verdict
    qual_families = []
    for bid in real_4:
        ps = confirm[bid]["tuple_cached_stable"]["paired_045_vs_044_R1"]
        if ps["paired_median_reduction_pct"] >= 10.0 and ps["faster_count"] >= 21:
            qual_families.append(bid)
    guard_regs = []
    for bid in ("HighOverlap_Interleaved_16pairs", "SmallBatch_12F_Linear_10pairs", "TiedContact_12pairs"):
        ps = confirm[bid]["tuple_cached_stable"]["paired_045_vs_044_R1"]
        reg_pct = -ps["paired_median_reduction_pct"]
        if reg_pct > 5.0 and ps["paired_median_delta_ms"] > 1.0:
            guard_regs.append((bid, reg_pct, ps["paired_median_delta_ms"]))
    heavy_over_25_cached = [
        bid for bid, cmap in residual_profile.items()
        if bid in real_4 and cmap["cached"]["residual_build_pct"] > 25.0
    ]
    heavy_over_25_uncached = [
        bid for bid, cmap in residual_profile.items()
        if bid in real_4 and "uncached" in cmap and cmap["uncached"]["residual_build_pct"] > 25.0
    ]
    if guard_regs:
        verdict_045 = "BLOCKED_PROOF_OR_RESOURCE_CONTRACT"
    elif len(qual_families) >= 2:
        verdict_045 = "PRETREE_CANDIDATE_RESEARCH_ONLY"
    elif len(qual_families) == 1:
        verdict_045 = "RESTRICTED_WORKLOAD_ONLY"
    else:
        verdict_045 = "NO_NET_GAIN_KEEP_R1"

    out = {
        "schema": "m3-bvh-kernel-045-results-v1",
        "branch": "codex/m3-bvh-exact-batch-preproof-045",
        "environment": {**_win32_env_info(), "clock_resolution_ns": time.get_clock_info("perf_counter").resolution * 1e9},
        "arm_identities": {
            "044_R1": {
                "runtime_source_sha256": arm_044_r1.source_sha256,
                "surface_proximity_sha256": arm_044_r1.sp_raw_sha256,
                "surface_geometry_sha256": arm_044_r1.sg_raw_sha256,
            },
            "045": {
                "runtime_source_sha256": arm_045.source_sha256,
                "surface_proximity_sha256": arm_045.sp_raw_sha256,
                "surface_geometry_sha256": arm_045.sg_raw_sha256,
            },
        },
        "manifest_sha256": _sha256_json(cases_manifest),
        "selected_winner_mode": winner_mode,
        "screening": screening,
        "confirmation": confirm,
        "independent_process_memory_probes": {
            "scope": "independent_child_process_K32GetProcessMemoryInfo_PeakWorkingSetSize_and_tracemalloc",
            "runs": mem_rows,
        },
        "residual_build_profile": residual_profile,
        "verdicts": {
            "verdict_045": verdict_045,
            "qualified_families_vs_044_R1": qual_families,
            "guard_regressions": guard_regs,
            "families_residual_build_over_25pct_cached": heavy_over_25_cached,
            "families_residual_build_over_25pct_uncached": heavy_over_25_uncached,
            "gate_046_met_cached": len(heavy_over_25_cached) >= 2,
            "gate_046_met_uncached": len(heavy_over_25_uncached) >= 2,
        },
    }
    (BENCH_DIR / "KERNEL_045_RESULTS.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nDONE 045. Verdicts={json.dumps(out['verdicts'])}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

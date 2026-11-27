"""M3 BVH-044 (P4): Zero-Regression Traversal/Projection Hot-Loop & Exact Batch Cutoff Benchmark.

Evaluates:
  - A     : Frozen 041 (119327bbb, runtime_source_sha256 = eff6511223646c125ac05cd6080d3bcbe191d1c945a8b3b7293d2c1bc0ff1ee4)
  - K     : Frozen 042-P2 Arm K (b5b0df58b, runtime_source_sha256 = cc78597b4b4c9e336e7082bcb2fd99ba9739ead2e01104c095f8046fe048baf7)
  - P4_A  : Live default single-pair P4 (exact zero-topology, zero-work_units-change vs Arm K)
  - P4_AB : Exact cross-pair upper-bound cutoff batch nearest (measure_nearest_surface_batch)
"""
from __future__ import annotations

import argparse
import gc
import io
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.bvh_eval import _surface_sig, _work_summary
from benchmarks.run_kernel_042_research import (
    FROZEN_COMMIT,
    FROZEN_RUNTIME_SHA,
    NOOP,
    _require,
    _win32_env_info,
    _win32_process_mem,
    activate_arm,
    build_042_workloads,
    ensure_frozen_arm_a,
    load_arm_modules,
    run_paired_timing,
)

BENCH_DIR = Path(__file__).resolve().parent
P4_ARMS_ROOT = ROOT / "scratch" / "044_arms"
FROZEN_ARM_K_COMMIT = "b5b0df58bed75f3a259af8078630e1cb511ff769"
FROZEN_ARM_K_RUNTIME_SHA = "cc78597b4b4c9e336e7082bcb2fd99ba9739ead2e01104c095f8046fe048baf7"

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


def ensure_frozen_arm_k() -> Path:
    """Materialize frozen 042-P2 Arm K into scratch/044_arms/arm_k_042_p2 via git archive."""
    arm_k = P4_ARMS_ROOT / "arm_k_042_p2"
    marker = arm_k / "human_eye_plugin/surface_proximity.py"
    if marker.exists():
        return arm_k
    arm_k.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["git", "archive", "--format=tar", FROZEN_ARM_K_COMMIT, "--", *_RUNTIME_FILES],
        cwd=str(ROOT), check=True, stdout=subprocess.PIPE,
    )
    with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode="r:") as tf:
        tf.extractall(path=arm_k)
    _require(marker.exists(), f"Failed to extract frozen Arm K commit {FROZEN_ARM_K_COMMIT}")
    return arm_k


def verify_p4a_exact_work_and_sig_parity(arm_k, arm_p4, workloads: dict) -> dict:
    """Verify 100% _surface_sig and exact work-ledger equality between frozen K and live P4_A."""
    report = {"singles_checked": 0, "modes_checked": 0, "batches_checked": 0}
    for w in workloads["singles"]:
        wid = w["id"]
        for mode in ("settled_credit_031_ref", "off", "off_paid_dequeue_ref"):
            l_m, r_m = w["tuple_pair"]
            activate_arm(arm_k)
            rk = arm_k.sp.measure_surface_proximity(
                l_m, r_m, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=mode
            )
            activate_arm(arm_p4)
            rp = arm_p4.sp.measure_surface_proximity(
                l_m, r_m, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=mode
            )
            _require(_surface_sig(rk) == _surface_sig(rp), f"{wid}/{mode}: _surface_sig mismatch vs K")
            _require(rk["work"] == rp["work"], f"{wid}/{mode}: full work dict mismatch vs K")
            report["modes_checked"] += 1
        report["singles_checked"] += 1

    for b in workloads["batches"]:
        bid = b["id"]
        tg, ps = b["tuple_batch"]
        for use_cache in (False, True):
            ck = {} if use_cache else None
            cp = {} if use_cache else None
            for idx, peer in enumerate(ps):
                activate_arm(arm_k)
                rk = arm_k.sp.measure_surface_proximity(
                    tg, peer, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _mesh_cache=ck
                )
                activate_arm(arm_p4)
                rp = arm_p4.sp.measure_surface_proximity(
                    tg, peer, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _mesh_cache=cp
                )
                _require(_surface_sig(rk) == _surface_sig(rp), f"{bid}[{idx}]/cache={use_cache}: sig mismatch vs K")
                _require(rk["work"] == rp["work"], f"{bid}[{idx}]/cache={use_cache}: work dict mismatch vs K")
        report["batches_checked"] += 1
    return report


def run_single_and_batch_confirmation(arm_a, arm_k, arm_p4, workloads: dict, *, warmup: int, repeats: int) -> dict:
    """30-repeat paired confirmation across A, K, and P4_A."""
    arms = [arm_a, arm_k, arm_p4]
    singles_out = {}
    for w in workloads["singles"]:
        wid = w["id"]
        l_tup, r_tup = w["tuple_pair"]
        l_np, r_np = w["ndarray_pair"]
        tup_res = run_paired_timing(
            arms,
            lambda a, l=l_tup, r=r_tup: (lambda: a.sp.measure_surface_proximity(
                l, r, NOOP, retain_exact_rank=True, retain_witness_triangles=True
            )),
            warmup=warmup, repeats=repeats, sig_fn=_surface_sig,
        )
        np_res = run_paired_timing(
            arms,
            lambda a, l=l_np, r=r_np: (lambda: a.sp.measure_surface_proximity(
                l, r, NOOP, retain_exact_rank=True, retain_witness_triangles=True
            )),
            warmup=warmup, repeats=repeats, sig_fn=_surface_sig,
        )
        _require(
            _work_summary(tup_res["last_outs"]["P4_A"]["work"]) == _work_summary(tup_res["last_outs"]["K"]["work"]),
            f"{wid}: P4_A work_summary != K",
        )
        singles_out[wid] = {
            "classification": w["classification"],
            "role": w["role"],
            "uncached_tuple": {"arms": tup_res["arms"], "paired_vs_ref": tup_res["paired_vs_ref"]},
            "uncached_ndarray": {"arms": np_res["arms"], "paired_vs_ref": np_res["paired_vs_ref"]},
        }
        pa, pk, p4 = (
            tup_res["arms"]["A"]["timing"]["median_ms"],
            tup_res["arms"]["K"]["timing"]["median_ms"],
            tup_res["arms"]["P4_A"]["timing"]["median_ms"],
        )
        print(
            f"  [p4-single {wid:<32}] A={pa:6.2f}ms K={pk:6.2f}ms P4_A={p4:6.2f}ms "
            f"(vsK:{(pk - p4) / pk * 100.0:+5.2f}%)",
            flush=True,
        )

    batches_out = {}
    for b in workloads["batches"]:
        bid = b["id"]
        t_tup, peers_tup = b["tuple_batch"]
        t_np, peers_np = b["ndarray_batch"]

        def run_batch(arm, tg, ps, use_cache: bool):
            cache = {} if use_cache else None
            sigs = []
            agg = {}
            for p in ps:
                kw = {"_mesh_cache": cache} if use_cache else {}
                r = arm.sp.measure_surface_proximity(
                    tg, p, NOOP, retain_exact_rank=True, retain_witness_triangles=True, **kw
                )
                sigs.append(_surface_sig(r))
                for k, v in _work_summary(r["work"]).items():
                    if isinstance(v, int):
                        agg[k] = agg.get(k, 0) + v
            return sigs, agg

        unc_t = run_paired_timing(
            arms, lambda a, tg=t_tup, ps=peers_tup: (lambda: run_batch(a, tg, ps, False)),
            warmup=min(1, warmup), repeats=repeats, sig_fn=lambda p: p[0],
        )
        unc_n = run_paired_timing(
            arms, lambda a, tg=t_np, ps=peers_np: (lambda: run_batch(a, tg, ps, False)),
            warmup=min(1, warmup), repeats=repeats, sig_fn=lambda p: p[0],
        )
        cac_t = run_paired_timing(
            arms, lambda a, tg=t_tup, ps=peers_tup: (lambda: run_batch(a, tg, ps, True)),
            warmup=min(1, warmup), repeats=repeats, sig_fn=lambda p: p[0],
        )
        batches_out[bid] = {
            "classification": b["classification"],
            "pair_count": b["pair_count"],
            "uncached_tuple": {"arms": unc_t["arms"], "paired_vs_ref": unc_t["paired_vs_ref"]},
            "uncached_ndarray": {"arms": unc_n["arms"], "paired_vs_ref": unc_n["paired_vs_ref"]},
            "secondary_cached_tuple": {"arms": cac_t["arms"], "paired_vs_ref": cac_t["paired_vs_ref"]},
        }
        pa, pk, p4 = (
            unc_t["arms"]["A"]["timing"]["median_ms"],
            unc_t["arms"]["K"]["timing"]["median_ms"],
            unc_t["arms"]["P4_A"]["timing"]["median_ms"],
        )
        ca, ck, c4 = (
            cac_t["arms"]["A"]["timing"]["median_ms"],
            cac_t["arms"]["K"]["timing"]["median_ms"],
            cac_t["arms"]["P4_A"]["timing"]["median_ms"],
        )
        print(
            f"  [p4-batch  {bid:<32}] unc: A={pa:6.2f} K={pk:6.2f} P4_A={p4:6.2f}ms "
            f"| cac: A={ca:6.2f} K={ck:6.2f} P4_A={c4:6.2f}ms",
            flush=True,
        )

    return {"singles": singles_out, "batches": batches_out}


def run_p4b_batch_cutoff_benchmark(arm_k, arm_p4, workloads: dict, *, warmup: int, repeats: int) -> dict:
    """Benchmark exact cross-pair upper-bound cutoff batch nearest against unpruned K/P4_A loops."""
    out = {}
    for b in workloads["batches"]:
        bid = b["id"]
        t_tup, peers_tup = b["tuple_batch"]
        t_np, peers_np = b["ndarray_batch"]

        # Exhaustive ground truth via frozen K + _rank_surface_results
        activate_arm(arm_k)
        ex_res = {
            str(i): arm_k.sp.measure_surface_proximity(
                t_tup, p, NOOP, retain_exact_rank=True, retain_witness_triangles=True
            )
            for i, p in enumerate(peers_tup)
        }
        ranked = arm_k.sp._rank_surface_results(ex_res, NOOP)
        ex_best_indices = [int(i) for i in ranked["ordered_object_id_groups"][0]]
        ex_best_sq = ex_res[str(ex_best_indices[0])]["_exact_distance_sq"]
        ex_best_sigs = [_surface_sig(ex_res[str(i)]) for i in ex_best_indices]

        variants_out = {}
        for vname, (tg, ps, use_cache, sort_aabb) in (
            ("uncached_tuple_natural", (t_tup, peers_tup, False, False)),
            ("uncached_tuple_sorted", (t_tup, peers_tup, False, True)),
            ("uncached_ndarray_sorted", (t_np, peers_np, False, True)),
            ("cached_tuple_sorted", (t_tup, peers_tup, True, True)),
        ):
            def batch_sig(res):
                return (
                    tuple(res["nearest_indices"]),
                    tuple(res["best_exact_distance_sq"]),
                    res["distance_m"],
                    [_surface_sig(res["results_by_index"][i]) for i in res["nearest_indices"]],
                )

            activate_arm(arm_p4)
            sample_cut = arm_p4.sp.measure_nearest_surface_batch(
                tg, ps, NOOP, use_mesh_cache=use_cache, use_cutoff=True, sort_by_aabb=sort_aabb,
                retain_witness_triangles=True,
            )
            _require(sample_cut["measurement_valid"] is True, f"{bid}/{vname}: invalid batch result")
            _require(sample_cut["nearest_indices"] == ex_best_indices, f"{bid}/{vname}: nearest_indices mismatch")
            _require(sample_cut["best_exact_distance_sq"] == ex_best_sq, f"{bid}/{vname}: best_sq mismatch")
            _require(
                [_surface_sig(sample_cut["results_by_index"][i]) for i in sample_cut["nearest_indices"]] == ex_best_sigs,
                f"{bid}/{vname}: nearest sig mismatch",
            )

            def timed_arm(loader_arm, *, cutoff_flag: bool):
                activate_arm(loader_arm)
                if cutoff_flag:
                    return loader_arm.sp.measure_nearest_surface_batch(
                        tg, ps, NOOP, use_mesh_cache=use_cache, use_cutoff=True,
                        sort_by_aabb=sort_aabb, retain_witness_triangles=True,
                    )
                # Reference exhaustive batch ranking via Arm K / P4_A
                cache = {} if use_cache else None
                results_map = {}
                results_list = []
                for i, peer in enumerate(ps):
                    kw = {"_mesh_cache": cache} if use_cache else {}
                    r = loader_arm.sp.measure_surface_proximity(
                        tg, peer, NOOP, retain_exact_rank=True, retain_witness_triangles=True, **kw
                    )
                    results_map[str(i)] = r
                    results_list.append(r)
                rk = loader_arm.sp._rank_surface_results(results_map, NOOP)
                n_idx = [int(i) for i in rk["ordered_object_id_groups"][0]]
                return {
                    "nearest_indices": n_idx,
                    "best_exact_distance_sq": results_list[n_idx[0]]["_exact_distance_sq"],
                    "distance_m": results_list[n_idx[0]]["distance_m"],
                    "results_by_index": results_list,
                }

            class _WrapArm:
                def __init__(self, name, arm_obj, cutoff_flag):
                    self.name = name
                    self.mods = arm_obj.mods
                    self._arm = arm_obj
                    self._cutoff_flag = cutoff_flag

            w_arms = [
                _WrapArm("K_exhaustive", arm_k, False),
                _WrapArm("P4_A_exhaustive", arm_p4, False),
                _WrapArm("P4_AB_cutoff", arm_p4, True),
            ]
            paired = run_paired_timing(
                w_arms,
                lambda wa: (lambda: timed_arm(wa._arm, cutoff_flag=wa._cutoff_flag)),
                warmup=min(1, warmup), repeats=repeats, sig_fn=batch_sig,
            )
            agg_cut_wu = sum(r["work"]["work_units"] for r in sample_cut["results_by_index"])
            agg_ex_wu = sum(ex_res[str(i)]["work"]["work_units"] for i in range(len(peers_tup)))
            variants_out[vname] = {
                "cutoff_pruned_count": sample_cut["cutoff_pruned_count"],
                "evaluated_count": sample_cut["evaluated_count"],
                "exhaustive_work_units": agg_ex_wu,
                "cutoff_work_units": agg_cut_wu,
                "arms": paired["arms"],
                "paired_vs_ref": paired["paired_vs_ref"],
            }
            km = paired["arms"]["K_exhaustive"]["timing"]["median_ms"]
            p4am = paired["arms"]["P4_A_exhaustive"]["timing"]["median_ms"]
            p4bm = paired["arms"]["P4_AB_cutoff"]["timing"]["median_ms"]
            print(
                f"  [p4b-batch {bid:<24} {vname:<24}] K={km:6.2f}ms P4_A={p4am:6.2f}ms P4_AB={p4bm:6.2f}ms "
                f"(vsK:{km / p4bm:5.2f}x pruned={sample_cut['cutoff_pruned_count']}/{len(peers_tup)} "
                f"wu:{agg_ex_wu}->{agg_cut_wu})",
                flush=True,
            )
        out[bid] = {
            "pair_count": b["pair_count"],
            "ground_truth_nearest_indices": ex_best_indices,
            "ground_truth_exact_distance_sq": ex_best_sq,
            "variants": variants_out,
        }
    return out


def run_process_memory_probe(arm_a, arm_k, arm_p4, workloads: dict) -> dict:
    mem_probe = {"memory_metric_scope": "win32_K32GetProcessMemoryInfo_WorkingSet_and_PeakWorkingSet_bytes"}
    for wid in ("G508_Peer_000", "HighRes_1536F_Pair", "Sheet_Dented_2mm", "Tube_Coiled_Loose"):
        spec = next(x for x in workloads["singles"] if x["id"] == wid)
        l_tup, r_tup = spec["tuple_pair"]
        wrow = {}
        for arm in (arm_a, arm_k, arm_p4):
            activate_arm(arm)
            gc.collect()
            b0 = _win32_process_mem()
            for _ in range(3):
                _ = arm.sp.measure_surface_proximity(l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
            b1 = _win32_process_mem()
            wrow[arm.name] = {
                "before": b0,
                "after": b1,
                "ws_delta_bytes": (b1.get("working_set_bytes", 0) - b0.get("working_set_bytes", 0)) if b0 and b1 else None,
            }
        mem_probe[wid] = wrow
    return mem_probe


def main() -> int:
    parser = argparse.ArgumentParser(description="BVH-044 P4 Traversal & Batch Cutoff Benchmark")
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=30)
    args = parser.parse_args()

    arm_a = load_arm_modules("A", ensure_frozen_arm_a())
    arm_k = load_arm_modules("K", ensure_frozen_arm_k())
    arm_p4 = load_arm_modules("P4_A", ROOT)
    _require(arm_a.source_sha256 == FROZEN_RUNTIME_SHA, f"Arm A sha mismatch: {arm_a.source_sha256}")
    _require(arm_k.source_sha256 == FROZEN_ARM_K_RUNTIME_SHA, f"Arm K sha mismatch: {arm_k.source_sha256}")

    workloads = build_042_workloads()

    print("=== 1. P4_A Exact _surface_sig + Exact work Dict Parity vs Frozen 042-P2 Arm K ===", flush=True)
    parity = verify_p4a_exact_work_and_sig_parity(arm_k, arm_p4, workloads)
    print(f"  Verified {parity}", flush=True)

    print(f"\n=== 2. {args.repeats}-Repeat Paired Single/Batch Confirmation (A vs K vs P4_A) ===", flush=True)
    confirm = run_single_and_batch_confirmation(arm_a, arm_k, arm_p4, workloads, warmup=args.warmup, repeats=args.repeats)

    print(f"\n=== 3. {args.repeats}-Repeat Exact Cross-Pair Batch Cutoff Benchmark (K vs P4_A vs P4_AB) ===", flush=True)
    batch_cutoff = run_p4b_batch_cutoff_benchmark(arm_k, arm_p4, workloads, warmup=args.warmup, repeats=args.repeats)

    print("\n=== 4. Win32 Working Set & Peak Working Set Probe ===", flush=True)
    mem_probe = run_process_memory_probe(arm_a, arm_k, arm_p4, workloads)

    # Check regression gate of P4_A vs K
    max_reg_vs_k = 0.0
    max_reg_name = ""
    for sec in ("singles", "batches"):
        for k, v in confirm[sec].items():
            for kind in ("uncached_tuple", "uncached_ndarray", "secondary_cached_tuple"):
                if kind not in v:
                    continue
                km = v[kind]["arms"]["K"]["timing"]["median_ms"]
                pm = v[kind]["arms"]["P4_A"]["timing"]["median_ms"]
                reg_pct = ((pm - km) / km) * 100.0 if km > 0 else 0.0
                if reg_pct > max_reg_vs_k:
                    max_reg_vs_k = round(reg_pct, 2)
                    max_reg_name = f"{k}.{kind}"

    verdict = (
        "CANDIDATE_044_P4_VALIDATED_ZERO_REGRESSION"
        if max_reg_vs_k <= 2.0
        else "CANDIDATE_044_P4_REQUIRES_REVIEW"
    )
    out = {
        "schema": "m3-bvh-kernel-044-p4-results-v1",
        "branch": "codex/m3-bvh-p4-traversal-cutoff-044",
        "frozen_041_commit": FROZEN_COMMIT,
        "frozen_041_runtime_sha256": FROZEN_RUNTIME_SHA,
        "frozen_arm_k_commit": FROZEN_ARM_K_COMMIT,
        "frozen_arm_k_runtime_sha256": FROZEN_ARM_K_RUNTIME_SHA,
        "environment": _win32_env_info(),
        "arm_identities": {
            arm.name: {
                "runtime_source_sha256": arm.source_sha256,
                "surface_geometry_sha256": arm.sg_raw_sha256,
                "surface_proximity_sha256": arm.sp_raw_sha256,
            }
            for arm in (arm_a, arm_k, arm_p4)
        },
        "p4a_exact_work_parity": parity,
        "confirm_paired_results": confirm,
        "p4b_batch_cutoff_results": batch_cutoff,
        "win32_process_memory_probe": mem_probe,
        "max_regression_vs_k_pct": max_reg_vs_k,
        "max_regression_case": max_reg_name,
        "verdict": verdict,
    }
    (BENCH_DIR / "KERNEL_044_P4_RESULTS.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nDONE 044-P4. max_regression_vs_K={max_reg_vs_k}% ({max_reg_name}), Verdict={verdict}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

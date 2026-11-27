"""M3 BVH-043 (P3): Exact Demand-Driven Lazy SAH BVH Research Harness.

Compares:
  - Arm A: Frozen 041 reference (119327bbb)
  - Arm K: Promoted 042-P2 Eager reference (b5b0df58b)
  - Arm P3: Exact Lazy SAH BVH (HEAD)
across subtree structural parity, 3-projection-mode parity, C03/F01 [0..32]
paid-dequeue credit sweeps, expansion telemetry, 30-repeat paired confirmation,
and Win32/tracemalloc memory probes.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import gc
import io
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tarfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.bvh_eval import _surface_sig, _work_summary
from benchmarks.run_kernel_042_research import (
    FROZEN_COMMIT,
    FROZEN_RUNTIME_SHA,
    NOOP,
    _require,
    _sha256_json,
    _tree_struct_summary,
    _win32_env_info,
    _win32_process_mem,
    activate_arm,
    build_042_workloads,
    ensure_frozen_arm_a,
    load_arm_modules,
    measure_raw_trees_for_arm,
    run_paired_timing,
)
from benchmarks.run_r3_closure_eval import _freeze, _tilted_plate

BENCH_DIR = Path(__file__).resolve().parent
P3_ARMS_ROOT = ROOT / "scratch" / "043_arms"
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
    """Materialize Arm K (b5b0df58b) into scratch/043_arms/arm_k_042_p2 via git archive."""
    arm_k = P3_ARMS_ROOT / "arm_k_042_p2"
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


def assert_visited_lazy_matches_eager(eager_node, lazy_node, eager_min_id=None, path="root") -> tuple[int, int, int]:
    """Recursively verify EVERY created/expanded lazy node matches its exact eager counterpart.

    Returns (created_nodes, expanded_internal_nodes, compiled_eager_check_min_id).
    """
    elo, ehi, ecnt, eids, el, er = eager_node
    llo = (lazy_node[0], lazy_node[1], lazy_node[2])
    lhi = (lazy_node[3], lazy_node[4], lazy_node[5])
    lcnt, lids = lazy_node[6], lazy_node[7]
    ll, lr, lmin = lazy_node[8], lazy_node[9], lazy_node[10]

    # Compute expected min descendant id of eager_node
    def _min_id(node):
        if node[3] is not None:
            return min(node[3])
        return min(_min_id(node[4]), _min_id(node[5]))

    expected_min = _min_id(eager_node) if eager_min_id is None else eager_min_id
    _require(llo == elo and lhi == ehi, f"{path}: bounds mismatch {llo, lhi} != {elo, ehi}")
    _require(lcnt == ecnt, f"{path}: count mismatch {lcnt} != {ecnt}")
    _require(lmin == expected_min, f"{path}: min_id mismatch {lmin} != {expected_min}")

    if ll is None:
        # Either genuine leaf (n <= 2 -> lids == eids) or unexpanded internal node (lids is None, raw ids in lazy_node[14])
        _require(lr is None, f"{path}: asymmetric child None")
        if eids is not None:
            _require(lids is not None and list(lids) == list(eids), f"{path}: leaf ids mismatch {lids} != {eids}")
            return 1, 0, expected_min
        raw_ids = lazy_node[14]
        _require(lids is None and isinstance(raw_ids, list) and len(raw_ids) == ecnt,
                 f"{path}: unexpanded internal node missing intact ids list")
        return 1, 0, expected_min

    # Expanded internal lazy node must have eager children too
    _require(el is not None and er is not None and lids is None and lr is not None,
             f"{path}: expanded lazy node disagrees with eager leaf/internal structure")
    c0, e0, _ = assert_visited_lazy_matches_eager(el, ll, None, path + ".L")
    c1, e1, _ = assert_visited_lazy_matches_eager(er, lr, None, path + ".R")
    return 1 + c0 + c1, 1 + e0 + e1, expected_min


def verify_lazy_trees_and_3modes(arm_a, arm_k, arm_p3, workloads: dict) -> dict:
    """Verify visited-subtree structural parity, 3-mode sig parity, and expansion ratios."""
    telemetry = {}
    for w in workloads["singles"]:
        wid = w["id"]
        l_tup, r_tup = w["tuple_pair"]

        # 1. Eager trees on Arm A
        ta = measure_raw_trees_for_arm(arm_a, l_tup, r_tup)
        eager_total = ta["left"]["node_count"] + ta["right"]["node_count"]

        # 2. Capture actual partially-expanded lazy roots on Arm P3 (skip linear bypass)
        activate_arm(arm_p3)
        lazy_sink = []
        bd = arm_p3.sp._Work(NOOP, {})
        recs, _ = arm_p3.sp._admit((l_tup, r_tup), bd)
        _, _, prep = arm_p3.sp._integer_frame(recs, bd)
        is_linear = len(prep[0]) * len(prep[1]) <= arm_p3.sp.LINEAR_PAIR_LIMIT
        if not is_linear:
            _ = arm_p3.sp._nearest(prep, bd, _lazy_bvh=True, _lazy_roots_out=lazy_sink)
            _require(len(lazy_sink) == 2, f"{wid}: missing lazy roots sink")
            c0, e0, _ = assert_visited_lazy_matches_eager(ta["roots"][0], lazy_sink[0], None, f"{wid}.L")
            c1, e1, _ = assert_visited_lazy_matches_eager(ta["roots"][1], lazy_sink[1], None, f"{wid}.R")
            created, expanded = c0 + c1, e0 + e1
        else:
            created, expanded = 0, 0

        # 3. 3-projection-mode _surface_sig parity across Arm A, Arm K Eager, Arm P3 Lazy
        mode_stats = {}
        for mode in ("settled_credit_031_ref", "off", "off_paid_dequeue_ref"):
            activate_arm(arm_a)
            ra = arm_a.sp.measure_surface_proximity(
                l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=mode,
            )
            activate_arm(arm_k)
            rk = arm_k.sp.measure_surface_proximity(
                l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=mode,
            )
            activate_arm(arm_p3)
            rp3 = arm_p3.sp.measure_surface_proximity(
                l_tup, r_tup, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=mode,
            )
            sa, sk, sp3 = _surface_sig(ra), _surface_sig(rk), _surface_sig(rp3)
            _require(sa == sk == sp3, f"{wid}.{mode}: 3-arm signature mismatch")
            _require(rp3["work"]["work_units"] <= rk["work"]["work_units"],
                     f"{wid}.{mode}: lazy work_units exceeded eager ({rp3['work']['work_units']} > {rk['work']['work_units']})")
            mode_stats[mode] = {
                "eager_K_work_units": rk["work"]["work_units"],
                "lazy_P3_work_units": rp3["work"]["work_units"],
                "eager_K_tree_build_units": rk["work"]["tree_build_units"],
                "lazy_P3_tree_build_units": rp3["work"]["tree_build_units"],
            }

        ratio_pct = round((created / eager_total) * 100.0, 2) if eager_total > 0 else 0.0
        telemetry[wid] = {
            "linear_bypass": is_linear,
            "eager_total_nodes": eager_total,
            "lazy_nodes_created": created,
            "lazy_nodes_expanded": expanded,
            "created_pct_of_eager": ratio_pct,
            "modes": mode_stats,
        }
        print(
            f"  [lazy-parity {wid:<32}] created={created:4d}/{eager_total:4d} ({ratio_pct:5.1f}%) "
            f"wu: {mode_stats['settled_credit_031_ref']['eager_K_work_units']}->{mode_stats['settled_credit_031_ref']['lazy_P3_work_units']}",
            flush=True,
        )
    return telemetry


def run_lazy_c03_paid_dequeue_audit(arm_p3) -> dict:
    """Verify 0 holes vs executed off_paid_dequeue_ref (M_paid_ref_lazy) across [0..32] delta sweeps."""
    activate_arm(arm_p3)
    sp = arm_p3.sp
    w = build_042_workloads()
    by_id = {row["id"]: row["tuple_pair"] for row in w["singles"]}
    tl, tr = _tilted_plate(12, 0.0), _tilted_plate(12, 0.5, reverse=True)
    ml, mr = _freeze("tl", *tl), _freeze("tr", *tr)
    fixtures = {
        "tilted48": (ml, mr),
        "G508_Competing_001": by_id["G508_Competing_001"],
        "sheet5um": by_id["Sheet_Parallel_5um"],
    }
    orig_init = sp._Work.__init__
    out = {}
    for name, (la, rb) in fixtures.items():
        ref_on = sp.measure_surface_proximity(la, rb, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        ref_off = sp.measure_surface_proximity(la, rb, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode="off")
        ref_paid = sp.measure_surface_proximity(la, rb, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode="off_paid_dequeue_ref")
        m_off = ref_off["work"]["work_units"]
        m_paid = ref_paid["work"]["work_units"]
        m_on = ref_on["work"]["work_units"]
        ref_sig = _surface_sig(ref_paid)

        sweep_paid = {}
        for vname, pmode in (
            ("PAID_REF", "off_paid_dequeue_ref"),
            ("OFF", "off"),
            ("ON_normal", "settled_credit_031_ref"),
            ("ON_in_admission_fail_dir", "settled_credit_031_ref"),
            ("ON_in_admission_fail_slab", "settled_credit_031_ref"),
        ):
            inv_deltas = []
            prov_diff_deltas = []
            for d in range(33):
                cap = m_paid + d
                if cap > sp.MAX_WORK_UNITS:
                    continue

                def pinit(inst, cp, diag, init_w=sp.MAX_WORK_UNITS - cap):
                    orig_init(inst, cp, diag)
                    inst.counts["work_units"] = init_w

                if vname == "ON_in_admission_fail_dir":
                    ctx = patch.object(sp, "_fast_descriptor_direction", return_value=None)
                elif vname == "ON_in_admission_fail_slab":
                    ctx = patch.object(sp._FastWitnessProjection, "_slab_exceeds_cutoff", staticmethod(lambda _g, _c: False))
                else:
                    ctx = patch.object(sp, "_NODE_PRUNE_OBSERVER", None)
                with patch.object(sp._Work, "__init__", pinit), ctx:
                    r_d = sp.measure_surface_proximity(
                        la, rb, NOOP, retain_exact_rank=True, retain_witness_triangles=True, _projection_mode=pmode,
                    )
                if r_d.get("measurement_valid") is not True:
                    inv_deltas.append(d)
                elif _surface_sig(r_d) != ref_sig:
                    prov_diff_deltas.append(d)
            holes = sorted(set(inv_deltas) | set(prov_diff_deltas))
            sweep_paid[vname] = {
                "invalid_deltas_0_to_32": inv_deltas,
                "provenance_diff_deltas_0_to_32": prov_diff_deltas,
                "total_holes": len(holes),
            }
            _require(len(holes) == 0, f"Lazy C03 sweep failed vs M_paid_ref on {name}.{vname}: {holes}")

        out[name] = {
            "M_off_lazy": m_off,
            "M_paid_ref_lazy": m_paid,
            "M_on_lazy": m_on,
            "dequeue_reused_aabb_bounds": ref_on["work"].get("dequeue_reused_aabb_bounds", 0),
            "vs_M_paid_ref": sweep_paid,
        }
        print(f"  [lazy-c03 {name:<20}] M_off={m_off} M_paid_ref={m_paid} M_on={m_on} (0 holes vs M_paid_ref)", flush=True)
    return out


def _bench_suite(arm_objs: list, workloads: dict, *, warmup: int, repeats: int) -> dict:
    singles_out = {}
    for w in workloads["singles"]:
        wid = w["id"]
        l_tup, r_tup = w["tuple_pair"]
        l_np, r_np = w["ndarray_pair"]

        tup_res = run_paired_timing(
            arm_objs,
            lambda a, l=l_tup, r=r_tup: (lambda: a.sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True, retain_witness_triangles=True)),
            warmup=warmup, repeats=repeats, sig_fn=_surface_sig,
        )
        np_res = run_paired_timing(
            arm_objs,
            lambda a, l=l_np, r=r_np: (lambda: a.sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True, retain_witness_triangles=True)),
            warmup=warmup, repeats=repeats, sig_fn=_surface_sig,
        )
        singles_out[wid] = {
            "classification": w["classification"],
            "role": w["role"],
            "uncached_tuple": {"arms": tup_res["arms"], "paired_vs_ref": tup_res["paired_vs_ref"], "work": {a.name: _work_summary(tup_res["last_outs"][a.name]["work"]) for a in arm_objs}},
            "uncached_ndarray": {"arms": np_res["arms"], "paired_vs_ref": np_res["paired_vs_ref"]},
        }
        line = " ".join(f"{a.name}={tup_res['arms'][a.name]['timing']['median_ms']:.2f}ms" for a in arm_objs)
        print(f"  [043-single {wid:<32}] {line}", flush=True)

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
                r = arm.sp.measure_surface_proximity(tg, p, NOOP, retain_exact_rank=True, retain_witness_triangles=True, **kw)
                sigs.append(_surface_sig(r))
                for k, v in _work_summary(r["work"]).items():
                    if isinstance(v, int):
                        agg[k] = agg.get(k, 0) + v
            return sigs, agg

        unc_t = run_paired_timing(arm_objs, lambda a, tg=t_tup, ps=peers_tup: (lambda: run_batch(a, tg, ps, False)), warmup=min(1, warmup), repeats=repeats, sig_fn=lambda p: p[0])
        unc_n = run_paired_timing(arm_objs, lambda a, tg=t_np, ps=peers_np: (lambda: run_batch(a, tg, ps, False)), warmup=min(1, warmup), repeats=repeats, sig_fn=lambda p: p[0])
        cac_t = run_paired_timing(arm_objs, lambda a, tg=t_tup, ps=peers_tup: (lambda: run_batch(a, tg, ps, True)), warmup=min(1, warmup), repeats=repeats, sig_fn=lambda p: p[0])
        batches_out[bid] = {
            "classification": b["classification"],
            "pair_count": b["pair_count"],
            "uncached_tuple": {"arms": unc_t["arms"], "paired_vs_ref": unc_t["paired_vs_ref"], "work_agg": {a.name: unc_t["last_outs"][a.name][1] for a in arm_objs}},
            "uncached_ndarray": {"arms": unc_n["arms"], "paired_vs_ref": unc_n["paired_vs_ref"]},
            "secondary_cached_tuple": {"arms": cac_t["arms"], "paired_vs_ref": cac_t["paired_vs_ref"], "work_agg": {a.name: cac_t["last_outs"][a.name][1] for a in arm_objs}},
        }
        line = " ".join(f"{a.name}={unc_t['arms'][a.name]['timing']['median_ms']:.2f}ms" for a in arm_objs)
        print(f"  [043-batch  {bid:<32}] {line}", flush=True)

    return {"singles": singles_out, "batches": batches_out}


def main() -> int:
    parser = argparse.ArgumentParser(description="BVH-043 Exact Lazy SAH BVH Research Runner")
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=30)
    args = parser.parse_args()

    arm_a = load_arm_modules("A", ensure_frozen_arm_a())
    arm_k = load_arm_modules("K", ensure_frozen_arm_k())
    arm_p3 = load_arm_modules("P3_Lazy", ROOT)
    _require(arm_a.source_sha256 == FROZEN_RUNTIME_SHA, f"Arm A sha mismatch: {arm_a.source_sha256}")
    _require(arm_k.source_sha256 == FROZEN_ARM_K_RUNTIME_SHA, f"Arm K sha mismatch: {arm_k.source_sha256}")

    workloads = build_042_workloads()

    print("=== 1. Lazy Visited-Subtree Parity, 3 Projection Modes & Expansion Telemetry ===", flush=True)
    telemetry = verify_lazy_trees_and_3modes(arm_a, arm_k, arm_p3, workloads)

    print("\n=== 2. Lazy C03/F01 Paid-Dequeue Credit Sweeps [0..32] ===", flush=True)
    c03_audit = run_lazy_c03_paid_dequeue_audit(arm_p3)

    print(f"\n=== 3. {args.repeats}-Repeat Paired Confirmation (A vs K Eager vs P3 Lazy) ===", flush=True)
    confirm = _bench_suite([arm_a, arm_k, arm_p3], workloads, warmup=args.warmup, repeats=args.repeats)

    # Separate Win32 WorkingSet / PeakWorkingSet probe
    mem_probe = {"memory_metric_scope": "win32_K32GetProcessMemoryInfo_WorkingSet_and_PeakWorkingSet_bytes"}
    for wid in ("HighRes_1536F_Pair", "Sheet_Dented_2mm", "Tube_Coiled_Loose", "G508_Peer_000"):
        spec = next(x for x in workloads["singles"] if x["id"] == wid)
        l, r = spec["tuple_pair"]
        row = {}
        for arm in (arm_a, arm_k, arm_p3):
            activate_arm(arm)
            gc.collect()
            b = _win32_process_mem()
            _ = arm.sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
            a = _win32_process_mem()
            row[arm.name] = {"before": b, "after": a, "ws_delta_bytes": a["working_set_bytes"] - b["working_set_bytes"]}
        mem_probe[wid] = row

    out = {
        "schema": "m3-bvh-kernel-043-lazy-results-v1",
        "branch": "codex/m3-bvh-lazy-sah-043",
        "frozen_041_commit": FROZEN_COMMIT,
        "frozen_041_runtime_sha256": FROZEN_RUNTIME_SHA,
        "frozen_arm_k_commit": FROZEN_ARM_K_COMMIT,
        "frozen_arm_k_runtime_sha256": FROZEN_ARM_K_RUNTIME_SHA,
        "environment": _win32_env_info(),
        "arm_identities": {
            a.name: {"runtime_source_sha256": a.source_sha256, "surface_geometry_sha256": a.sg_raw_sha256, "surface_proximity_sha256": a.sp_raw_sha256}
            for a in (arm_a, arm_k, arm_p3)
        },
        "expansion_telemetry": telemetry,
        "lazy_c03_paid_dequeue_audit": c03_audit,
        "confirm_paired_results": confirm,
        "win32_process_memory_probe": mem_probe,
        "verdict": "CANDIDATE_043_LAZY_VALIDATED_RESEARCH_ONLY",
    }
    (BENCH_DIR / "KERNEL_043_LAZY_RESULTS.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("\nDONE 043 Lazy SAH BVH. Verdict=CANDIDATE_043_LAZY_VALIDATED_RESEARCH_ONLY", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

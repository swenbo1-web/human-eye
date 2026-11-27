# M3 BVH 044-R1 Freeze Handoff

- **Source Branch**: `codex/m3-bvh-p4-traversal-cutoff-044` (atop `044_orig` `535321c9c5bd543638426fa44c35ac9745b72cc9`)
- **Freeze Tag**: `freeze/m3-bvh-044-r1`
- **Combined Qualification Verdict**: `A_AND_B_READY_FOR_RESTRICTED_EXPERIMENT` (`a_verdict = A_QUALIFIED`, `b_verdict = B_QUALIFIED_RESEARCH`)
- **Runtime Identity (`runtime_source_sha256`)**: `8825f1eb8e2ebca55ba2c97fc32a425a34865fb5697b4f5b301ad3f33692b897`

## 1. Track Split & API Surfaces

1. **Path A (Ordinary Single-Pair API — Qualified Parity Upgrade over `K`)**:
   - [`measure_surface_proximity`](file:///e:/bvh/human_eye_plugin/surface_proximity.py) retains its exact original signature without any cutoff argument, matches frozen Arm `K` (`b5b0df58b`) 100% on non-work signatures and full `work` dictionaries (`27/27` checks), and reduces 30-repeat paired median wall time vs frozen 041 Arm `A` by `+17.83%` on `G508_Peer_000` (`+14.44%` vs `K`) and `+11.82%` on `D48_Real_47pairs` (`+10.52%` vs `K`) with zero material guard regressions.
2. **Path B (Proof-Bearing Cutoff & Nearest-Batch API — Restricted Experiment)**:
   - [`_measure_surface_proximity_cutoff`](file:///e:/bvh/human_eye_plugin/surface_proximity.py) strictly isolates `cutoff_mode` (`EXHAUSTIVE`, `CUTOFF_ONLY_OFF`, `CUTOFF_ONLY_PAID_REF`, `CUTOFF_SETTLED_PROJECTION`), returns discriminated `exact_surface_measurement` / `nearest_cutoff_exclusion` (never inserted into measured cache) / `nearest_cutoff_unknown`, and avoids speculative narrow-phase probes.
   - [`build_batch_snapshot`](file:///e:/bvh/human_eye_plugin/surface_proximity.py) & [`measure_nearest_surface_batch`](file:///e:/bvh/human_eye_plugin/surface_proximity.py) materialize immutable referenced-only geometry snapshots once (`BatchSnapshot`) and deliver `+66.55%` wall reduction on `D48_Real_47pairs`, `+64.0%` on `Assembly24_Obj014_23pairs`, `+49.4%` (`+59.1%` cached) on `G508_Retained_11pairs`, and `+56.6%` (`+58.8%` cached) on `G60_D12_Retained_11pairs` under `CUTOFF_SETTLED_PROJECTION` with zero missed winners or unverified exclusions.

## 2. Independent Integration-Branch Adapter Contract (Deferred Out-of-Scope)

Integrating `measure_nearest_surface_batch` into public scene operators (`task_query.py` / `surface_scan.py`) MUST happen on a separate integration branch and obey:
- **Caller Seal**: Call `build_batch_snapshot(target, peers, checkpoint, ...)` inside the caller's locked scene tick so `BatchSnapshot.snapshot_identity` binds target + peers atomically before any query begins.
- **Outcome Interpretation**:
  - Require `out["status"] == "complete"` and `out["measurement_valid"] is True` before consuming `out["nearest_ids"]` or `out["distance_m"]`.
  - When `out["status"] == "partial"`, `out["nearest_ids"]` is strictly `None`; consume `out["best_known_ids"]` only for diagnostics / partial reporting, never as the certified nearest winner.
  - Strictly exclude peers via `result_kind == "nearest_cutoff_exclusion"` only when accompanied by `proof_receipt` (`strict_inequality_verified` for root AABB or `covered_pairs == total_leaf_pairs` for traversal) and matching `snapshot_identity`.
- **Mode Selection**: Default batch nearest discovery to `cutoff_mode="CUTOFF_SETTLED_PROJECTION"` and `sort_policy="stable"`; never enable `CUTOFF_ONLY_OFF` as a general default (causes `-40.93%` to `-211.5%` regression when root AABBs overlap).
- **Provenance Gaps**: Private historical fixtures (`zero489`, `first_yield`, `pair129`, `040_closed_solid`, `B02_10_retained_subset`) remain `MISSING_HISTORICAL_INPUT`.

## 3. Next Research Target (`045`)

- Branch [`codex/m3-bvh-exact-batch-preproof-045`](file:///e:/bvh/benchmarks/KERNEL_044_R1_REVIEW.md) atop `freeze/m3-bvh-044-r1` to eliminate unnecessary peer SAH tree construction (`n_trees_built = 47` on `D48_Real_47pairs` where `45/47` peers are strictly excluded) via Exact Pre-Tree Cross-Pair Separation (`root_axis` + batch-shared `cutoff_axes`).

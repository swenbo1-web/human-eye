# M3 BVH 045 Freeze Handoff

- **Source Branch**: `codex/m3-bvh-exact-batch-preproof-045` (atop `freeze/m3-bvh-044-r1` `f4d7b762f555bafa1e7585dd43e95a45f6004c33`)
- **Freeze Tag**: `freeze/m3-bvh-045-preproof`
- **Verdict**: `PRETREE_CANDIDATE_RESEARCH_ONLY` (`selected_winner_mode = "B3_TARGET_MEMO_AXIS"`)
- **Runtime Identity (`runtime_source_sha256`)**: `1d13c3a67986954f8940f3770dff7b11fe92fb708b18611b73e2074c109f527f`

## 1. Summary of Changes & Contract

- [`human_eye_plugin/surface_batch_preproof.py`](file:///e:/bvh/human_eye_plugin/surface_batch_preproof.py): Self-contained exact dyadic-integer (`frexp`/`ldexp` common exponent alignment + bit-budgeted `_strict_dyadic_gt`) pre-tree root AABB (`B1_ROOT_AABB`) and shared-axis (`B2_INCUMBENT_AXIS`, `B3_TARGET_MEMO_AXIS`, `B4_BOUNDED_MULTI_AXIS`) separation proofs with `256`-vertex chunked cancellation checkpoints (`surface_proximity_preproof_aabb`, `surface_proximity_preproof_axis_proj`).
- [`human_eye_plugin/surface_proximity.py`](file:///e:/bvh/human_eye_plugin/surface_proximity.py): Ordinary A-only [`measure_surface_proximity`](file:///e:/bvh/human_eye_plugin/surface_proximity.py) is untouched and parity-identical to frozen Arm `K`; `_capture_referenced_immutable_mesh` records referenced vertex exponent spans without extra reads; [`measure_nearest_surface_batch`](file:///e:/bvh/human_eye_plugin/surface_proximity.py) adds opt-in `preproof_mode` (`default='NONE'`, preserving `044-R1` behavior unless opted in).
- [`benchmarks/run_kernel_045_preproof.py`](file:///e:/bvh/benchmarks/run_kernel_045_preproof.py) & [`benchmarks/test_kernel_045_preproof.py`](file:///e:/bvh/benchmarks/test_kernel_045_preproof.py): 8,000-case exact `Fraction` oracle, independent raw-vertex scene proof audits, metamorphic invariances, chunked cancellation, hardened non-`assert` receipt checks, 7-repeat screening, 30-repeat confirmation, clean subprocess OS memory probes, and §10 residual build profiling.

## 2. Independent Integration-Branch Adapter Contract (Deferred Out-of-Scope)

Host integration (`task_query.py` / `surface_scan.py`) remains untouched and deferred to a dedicated integration branch:
1. Enable `measure_nearest_surface_batch(..., cutoff_mode="CUTOFF_SETTLED_PROJECTION", preproof_mode="B3_TARGET_MEMO_AXIS", sort_policy="stable")` ONLY for nearest-peer queries where exclusion by strict incumbent upper bound (`>`) is valid (NEVER use cutoff or pretree separation for full fixed-threshold scan!).
2. Keep `build_batch_snapshot(...)` sealed inside caller lock before any query begins; verify `out["status"] == "complete"` and `out["measurement_valid"] is True` before publishing `nearest_ids` or `distance_m`.
3. Outcomes with `proof_kind in ("pretree_root_aabb", "pretree_root_axis")` carry exact mathematical proof certificates (`proof_receipt`) and `tree_builds == 0` / `prepared_triangles == 0`, with NO distance measurement fields (`distance_m`, `_exact_distance_sq`); handle cleanly as `nearest_cutoff_exclusion`.
4. Archived `043` (`archive/m3-bvh-043-p3-lazy-research`) stays research archive; `046` adaptive eager/lazy build did NOT meet the `> 25%` residual build-cost gate (`8.4%–15.4%` cached after `045`). Private historical assets remain `MISSING_HISTORICAL_INPUT`.

# M3 BVH Kernel 041 Handoff Manifest

## 1. Status Verdict

**`RESTRICTED_EXPERIMENT_ONLY`**

This revision resolves the confirmed kernel and verification defects (**K01–K07**) in isolated direct-kernel scope while preserving all hard numerical limits, exact binary64/rational semantics, and fail-closed safety fallbacks. It is **not** authorized for direct production replacement and is **not** labelled `READY_FOR_EXPERIMENT_BRANCH` unconditionally because:

1. **Historical Private-Archive Inputs (`MISSING_HISTORICAL_INPUT`)**: The raw meshes for the historical `032` boundary fixtures `zero489`, `first_yield`, and `pair129` are not in the public repository. Separately named local synthetic boundary controls were executed and passed (including a real `3800x200` `MAX_NARROW_PHASE_PAIRS = 16,384` `surface_pair_budget` trigger and local `[M_off..M_off+32]` budget interval sweeps), but the private-archive gate remains for the experiment branch to close.
2. **Caller Ownership Dependency for `_mesh_cache` (`task_query.py`, `surface_scan.py`)**: Per scope constraints, caller adapters were not modified. Because K03 removed trust in the unverified `__sealed_query_meshes__ == True` dictionary flag, unmodified callers passing writable `MeshEntity3D` objects safely execute on the **validated uncached exact fallback path** (`mesh_cache_hits = 0`), with no stale-cache hazard. Re-enabling `_mesh_cache` reuse for live `task_query` / `surface_scan` paths requires caller-side ownership sealing on the experiment branch.

---

## 2. Candidate Identity & Changed-File Manifest

- **Branch**: `codex/m3-bvh-deep-optimization`
- **Base Commit Reviewed**: `b045658c`
- **Runtime Source SHA-256**: `e35b7e16c11ff8360bdcf2e5340019a9fc37ba11ad2bb09864989a28d6525414`

| File | Role | SHA-256 |
|---|---|---|
| `human_eye_plugin/surface_proximity.py` | K01 referenced-row reader, K02 settled-credit fast projection, K03 strict ownership cache guard (`cap=256`), K04 test-only node-prune observer, K06 `tree_kind='sah_bvh'` tag | `b36024ec4874c10f1261e8fac868580d6d278cb84ba748ed95c516c9e123e9ca` |
| `human_eye_plugin/surface_geometry.py` | K05 homogeneous dyadic-scale-invariant SAH binning; K06 `_bvh_median` compatibility for closed solids & `prepared_trees` guard | `80f6adaaa24c50746e6e5c4259cbe1a48334344784b9af4912ac1da1165b1cb6` |
| `benchmarks/bvh_eval.py` | K07 `m3-bvh-eval-v3` comparator hardening, 27 negative controls, all-repeat verification, tracemalloc labeling | `8eb38e01839b365fb13247c896139e0c25fc55bab4f9885bf288ba8b712c8714` |
| `benchmarks/run_ablation_and_assets.py` | K07 fail-closed interleaved timing/sig checks, removal of `or True` / unchecked `zip`, full B02/D48/G508 signature checks | `3a42e79a3063403e3d479d7dc7da7fbc452d14b9f0ecb170f824573cddbc0241` |
| `benchmarks/verify_review_suite.py` | K02 credit-positive deferral check, K04 tilted/G508 observer descendant oracle, safe dry-run CLI preserving frozen JSON | `5fabd985d9c7c37ed07de59cada4ae6c2d52d9f32f5fe4f77362b929735c9123` |
| `benchmarks/test_kernel_041_k01_to_k07.py` | Self-contained `unittest` regression & negative-control suite for K01–K07 (no local scratch paths) | `dbd1deeb615be399bef729f3a02155e32a24ec293934beb2374f94bb108a675d` |
| `.gitignore` | Allowlist for `KERNEL_041_*` deliverables and `test_kernel_041_k01_to_k07.py` | `13204446ac5f0c0a13b1bf6581efbbcd6cc79069ef43e6d03c06c3a0b71ad044` |

Deliverable artifacts:
- `benchmarks/KERNEL_041_CASES.json`
- `benchmarks/KERNEL_041_RESULTS.json`
- `benchmarks/KERNEL_041_REVIEW.md`
- `benchmarks/KERNEL_041_HANDOFF.md`

---

## 3. Feature Eligibility & Policy

### Eligible for Isolated Experiment Branch Evaluation
1. **`measure_surface_proximity`** (direct kernel, tuple and ndarray inputs):
   - Referenced-row scalar `.item((idx, k))` NumPy vertex acquisition (K01).
   - Pop-only, lazy (`_FAST_WP_AFTER_COMPLETED = 16`), strictly non-borrowing `_ProjectionCredit`-governed `_FastWitnessProjection` (K02/K04).
   - Homogeneous dyadic-scale-invariant SAH BVH (`_build_sah_bvh`, `leaf_size=2`) (K05).
   - Query-local `_mesh_cache` **only** for verified deep immutable tuples or owned read-only NumPy arrays (`base is None and owndata and not writeable`), capped at `256` entries (K03).
2. **`classify_closed_solids` & `measure_spatial_relation`**:
   - Conservative `032` `_bvh_median` tree construction and traversal for closed-shell classification; ignores `tree_kind == 'sah_bvh'` `prepared_trees` (K06).
   - Preserves shared budget accounting across proximity + `_referenced_support_evidence` + witness provenance publication.
3. **`analyze_surface_pair`**:
   - Unaffected public schema; verified via `verify_r07_closed_and_analyze` and hardened `_analyze_sig`.

### Disabled / Safe-Fallback Paths
- **`__sealed_query_meshes__ == True` trust**: **Removed**. Unverified mutable containers (including `MeshEntity3D` from unmodified `task_query.py` / `surface_scan.py`) automatically use the uncached exact fallback (`mesh_cache_hits = 0`).
- **Fixed 4096-unit projection headroom heuristic**: **Removed**.
- **Speculative `push_pair` witness projection**: **Removed** (eliminates credit starvation and far-subtree dot-product waste).

---

## 4. Required Actions on the Independent Experiment Branch

Before promoting beyond `RESTRICTED_EXPERIMENT_ONLY`:

1. **Replay Private-Archive `032` Budget-Edge Controls**: Run `zero489`, `first_yield`, and `pair129` from the private `032` archive against `e35b7e16c11ff8360bdcf2e5340019a9fc37ba11ad2bb09864989a28d6525414` and compare exact completion status, squared distance key, canonical witness, and work ledger against `032` (`6c93f23`).
2. **Caller Ownership Sealing for `_mesh_cache` (if cache reuse is desired in production entries)**: Update `task_query.py` and `surface_scan.py` snapshot/capture boundaries to freeze query meshes into owned read-only `float64`/`int32` NumPy arrays (`arr.flags.writeable = False`, `arr.base is None`, `arr.flags.owndata is True`) or deep tuples, or introduce a caller-verified immutable generation token contract audited at the capture boundary. Do **not** restore the boolean `__sealed_query_meshes__` bypass.
3. **Formal Host / End-to-End Qualification**: Run independent Blender host, MCP/packet, and p95 latency/RSS qualification studies using the hardened `m3-bvh-eval-v3` comparator (`benchmarks/bvh_eval.py`) and independent source pins.
4. **Closed-Solid Witness Contract Sign-Off (optional)**: If future optimization wants SAH reuse inside `classify_closed_solids`, the product owner must formally decide whether first-found transverse witness identity (`triangle_indices`) is part of the public contract or only valid source-bound transverse crossing. Until then, retain the conservative `_bvh_median` compatibility path.
5. **Pre-Existing Upstream Failures**: Track separately (present identically on `032` `6c93f23`):
   - `verification.test_surface_proximity_pruning_001`: `test_algorithm_version_is_distinct_with_fresh_binding_and_zero_hot_work` (`recorded(..., before_compute=...)` signature mismatch).
   - `verification.m3_pair_scalability_001.testing.test_pair_scalability`: `test_g508_frozen_three_pairs_independent_intervals_and_complete_relations` (`closed_solid_work_budget` at `262,144`).

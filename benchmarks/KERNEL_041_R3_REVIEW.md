# M3 BVH Kernel 041 R3 Closure & Optimization Review

- **Branch**: `codex/m3-bvh-deep-optimization`
- **Reviewed R2 Base Commit**: `b7d469d390abdeac93dfacfcce0dc385eae2f341` (`runtime_source_sha256 = e35b7e16c11ff8360bdcf2e5340019a9fc37ba11ad2bb09864989a28d6525414`)
- **Accepted Historical Reference (`032`)**: `6c93f2375d1073b33e721a168f1fcf610ac6dbdc` (`runtime_source_sha256 = 0f9e6336ec54adf9e7b9a5379b02d2c2cab9f6d1f734138c3fde29e08ccee241`)
- **R3 Candidate Runtime Source SHA-256**: `84a2f68210631ba1b1b8e2059db6d98fd06e50570f6a9d85dc9ecbe5fd75edc0`
- **Selected Policy (R3 Plan)**: **Option A** (explicit credit reference `mandatory_031_dequeue_aabb` for `settled_credit_031_ref`, plus explicit fail-closed `_projection_mode='off'`) + **Pure O(1)** `_cold_interval_upper` (`0` / `1 + 3*n` / `5*n - 1`)
- **Status Verdict**: **`RESTRICTED_EXPERIMENT_ONLY`** (see `benchmarks/KERNEL_041_R3_HANDOFF.md`)

---

## 1. Preserved Limits & Historical Artifacts

- Preserved constants unchanged: `MAX_FACES = 4096`, `MAX_WORK_UNITS = 1_179_648`, `MAX_NARROW_PHASE_PAIRS = 16_384`, `LINEAR_PAIR_LIMIT = 256`, closed-solid `MAX_WORK_UNITS = 262_144`.
- Forbidden files untouched: `task_query.py`, `surface_scan.py`, Blender/MCP adapters, Hook dispatch, release configs, public schemas, persistent caches.
- All prior evidence artifacts preserved verbatim (`KERNEL_041_{REVIEW.md,CASES.json,RESULTS.json,HANDOFF.md}`, `ALGORITHM_ABLATION.json`, `ALGORITHM_REVIEW_RESULT.md`, `ASSET_MANIFEST.json`, `CORRECTNESS_AND_BOUNDARY_RESULTS.json`, `REVIEW_FIXES.md`, `baseline_032.json`, `opt_bvh_final.json`; SHA-256 digests recorded in `benchmarks/KERNEL_041_R3_CASES.json`).

---

## 2. R3 Closure Matrix (C01–C06)

| ID | Pre-Fix S0 Reproduction (`b7d469d39`) | R3 Repair Implemented | Post-Fix R3 Verification & Evidence | Disposition |
|---|---|---|---|---|
| **C04** | `_validate_input_sha` accepted `['a', 'not-a-hash']`; `_analyze_sig` returned `complete=True` without `pair_accounting_complete`; `_binding_sig` normalized distinct runtime hashes equal without per-arm pinning; `_time_fn` failed to catch aliased mutable dict return (`verified=3`). | Bumped schema to **`m3-bvh-eval-v4`** in [bvh_eval.py](file:///e:/bvh/benchmarks/bvh_eval.py); enforced lowercase 64-hex SHA-256 everywhere, mandatory `inputs_sha256`, recomputed `options_sha256` from `solver_options`, per-arm `runtime_identity_sha256` pinning BEFORE binding normalization, fail-closed `pair_accounting_complete is True`, required surface signature fields, at-return deep-copied snapshots in `_time_fn` & `_time_interleaved` (`timed_outputs_verified = 0` when unverified), external `expected_batch_manifest` support, full R2/R3 credit/C02 keys in `_work_summary`, module `__file__` origin verification in [run_ablation_and_assets.py](file:///e:/bvh/benchmarks/run_ablation_and_assets.py), and explicit exceptions replacing bare `assert`s. | `bvh_eval.py --verify-comparator`: **41/41** controls pass in BOTH normal mode and `python -O`; `alias_caught = True`. R3 S5 smoke executed in **4 fresh serial subprocesses** with per-interpreter path/SHA verification. | **CLOSED** |
| **C01** | Owning read-only `float64` vertex ndarray mutated via pre-created writable view returned stale `1.0` instead of `3.0`; `flags.writeable` toggle returned stale `1.0` instead of `4.0`; owning read-only `int32` face ndarray view returned stale `1.0` instead of `5.0`. | Removed `_is_owned_readonly_numpy` in [surface_proximity.py](file:///e:/bvh/human_eye_plugin/surface_proximity.py); `_mesh_cache` now rejects **all** NumPy ndarrays (including owning read-only and mixed tuple/ndarray) in O(1), keeping cache reuse strictly for validated deep immutable tuple trees with strong `verts_ref`/`faces_ref` captured at admission and immediate stale eviction on `cached_valid`. | `TestR3_C01_CacheOwnership` + `D48_5pair_ndarray_uncached_control`: **0** ndarray cache hits (`mesh_cache_hits = 0`), post-view/toggle/face-index mutations match uncached exact distance, key, witnesses, and topology; mid-call rebind isolates to `verts_ref`; stale tuples/ndarrays evicted cleanly. | **CLOSED** |
| **C02** | Recursive `_node_interval_upper` ran **20,491** times on `G508_Peer_000` (`wu = 61,595`) without `budget`/checkpoint checks, and ran twice per node check. | Deleted recursive `_node_interval_upper`; added O(1) `_cold_interval_upper` (`0` if cached else `1 + 3*n` leaf / `5*n - 1` internal); eliminated caller duplicate preflight in `_nearest_tree`; moved single-pass box-then-slab admission into `prunes_nodes` with `witness_projection_upper_calls`, `slab_admitted`, `slab_deferred`, `slab_reserved_units`, `slab_actual_units`, `box_pruned_pairs`. | `TestR3_C02_ConstantTimeAdmission`: internal node `_GuardTuple` proves **0** descendant accesses (`[8]`/`[9]`); `G508_Peer_000` makes `5,317` O(1) upper calls (`5,051` slabs admitted; `reserved = 13,404 >= actual = 4,244`), runs **10.2% faster** than R2 (`125.309 ms` vs `139.488 ms`) at near-identical `work_units` (`61,740` vs `61,598`). | **CLOSED** |
| **C03** | On `tilted48` (`M_off = 6,892` in R2 / `6,894` in R3), injected `fail_dir` produced **8 holes** (`delta=0..7`) and injected `fail_slab` produced **33/33 holes** (`delta=0..32`) relative to `M_off`. | Implemented **Option A** contract: explicit `_projection_mode` (`'settled_credit_031_ref'` default vs `'off'` mandatory-only safe route, `ValueError` on unknown mode), explicit `witness_projection_credit_reference` (`mandatory_031_dequeue_aabb` vs `none`), zero credit earnings under `'off'`, prefix non-negativity invariant checks, and `self.counts.clear()` in `_Work.__init__` so reused `diagnostics` dicts never retain stale counters. | Across `tilted48`, `sheet5um`, and `repeated_epoch_36` (`[0..32]` integer sweeps): `OFF` and `ON_normal` have **0 holes** (invalidity + provenance diff) vs `M_off`; **all 4 variants (`OFF`, `ON_normal`, `ON_fail_dir`, `ON_fail_slab`) have 0 holes vs `M_ref_031`**; `tilted48` `M_off` injected failures cleanly reported (`ON_fail_dir`: 8 holes `[0..5 invalid, 6..7 prov_diff]`, `ON_fail_slab`: 33 holes `[0..32 invalid]`). Private `zero489`, `first_yield`, `pair129` stay `MISSING_HISTORICAL_INPUT`. | **CLOSED per Option A (disclosed)** |
| **C05** | `G508` audit needed explicit sampled-local labeling & raw-vertex recomputation; `TestK06` used unbound `fake_sah` missing `pair`/`triangles` identity and called `sp._intersection`. | Added independent raw-source-vertex `Fraction` interval/gap recomputation in [test_kernel_041_r3_c01_to_c06.py](file:///e:/bvh/benchmarks/test_kernel_041_r3_c01_to_c06.py) (zero reliance on `ev['gap']`), properly bound real SAH `prepared_trees` rejection + properly bound `median_bvh_v1` reuse positive control, pure-`Fraction` transverse-interior barycentric predicate (no `sp._intersection`), and identical-input `032` vs R3 closed-solid differential. | `tilted48` exhaustive (**83/83** events, **614** pairs) & `G508_Peer_000` sampled (**50/823** events = 25 strict + 25 tie, **1,471** pairs, explicitly `sampled_local_exclusion_audit_not_global_proof`) pass; live box-only `NOT_EXERCISED` + synthetic box `PASS`; degenerate 1/2-pt & boundary equality pass; SAH rejected (`reused=False`), median reused (`reused=True`), pure-`Fraction` strict interior confirmed, `032` vs R3 closed-solid differential exact (`040` original 48F ordering `MISSING_HISTORICAL_INPUT`). | **CLOSED** |
| **C06** | Deep tuple check, `_compile_bvh_node`, `_ensure_cached_frame` integerization, `_prepare_triangles_from_relative`, and affine fallback loops lacked cancellation checkpoints / explicit charge mapping. | Added bounded `budget.checkpoint(...)` in all 5 stages (`surface_proximity_face_validate`, `surface_proximity_bvh_compile`, `surface_proximity_referenced_vertices` inside frame/prepare/fallback) without altering `work_units`. Clarified `_MESH_CACHE_MAX_ENTRIES = 256` as entry count cap (not RSS/byte cap) and distinguished diagnostic `mesh_cache_translate_units` from logical `_Work` charges. | All 6 stage cancellation tests abort promptly on custom `_Cancelled` exception and leave `_mesh_cache` clean; 280-mesh eviction retains **256** entries (`256` faces, `768` referenced vertices); K01 9-row trap & 100k sparse NaN control remain green. | **CLOSED** |

---

## 3. C06 Physical-to-Logical Charge Mapping

| Physical Stage | Bounded Checkpoint | Logical `_Work` Charge Mapping | Diagnostic-Only Field |
|---|---|---|---|
| Tuple eligibility check (`_mesh_cache_is_immutable`) | `surface_proximity_face_validate` (1 per face) | Covered by subsequent `_admit_one` `validated_faces` on miss; ndarrays bail out in O(1) | — |
| Admission (`_admit_one`) | `surface_proximity_validated_faces` | `1 * num_faces` (`validated_faces`) | — |
| Local frame & integerization (`_ensure_cached_frame`) | `surface_proximity_referenced_vertices` | `1 * num_ref_vertices` (`referenced_vertices`) | — |
| Triangle build / translate (`_build_fast_triangles` / `_translate_triangles` / `_prepare_triangles_from_relative`) | `surface_proximity_triangle_prepare` / `_referenced_vertices` | `1 * num_faces` (`prepared_triangles`) | `mesh_cache_translate_units` (diagnostic) |
| Local BVH build / reuse (`_bvh` / `_translate_bvh` / `_compile_bvh_node`) | `surface_proximity_surface_bvh_build` / `_bvh_compile` | Exact `tree_builds`, `tree_build_units` + cached `bvh_units` replay | `mesh_cache_translate_units` (diagnostic) |
| Optional C02 projection proof (`_cold_interval_upper` + `prunes_nodes`) | `surface_proximity_witness_projection_*` | `1` box test + actual `node_visits` & `tri_dots` (0 recursive preflight) | `witness_projection_upper_calls`, `slab_reserved_units` vs `slab_actual_units` |

---

## 4. Isolated Subprocess Bounded Smoke Summary (1 Warmup, 3 Verified Repeats)

> Separate fresh Python subprocesses (`run_r3_closure_eval.py`), module `__file__` & `runtime_source_sha256` verified per interpreter. All `timed_outputs_verified == 3`, cross-arm semantic parity exact. Memory is `python_tracemalloc_only_not_process_rss`.

| Smoke Case | `032` Median (ms) | `b7d469d` R2 Median (ms) | `R3_default` Median (ms) | `R3_off` Median (ms) | R3 vs R2 Ratio | R3 Work Units | Key R3 Telemetry |
|---|---:|---:|---:|---:|---:|---:|---|
| `G508_Peer_000_tuple` | 927.923 | 139.488 | **125.309** | 1566.687 | **0.898x** (-10.2%) | 61,740 (vs `032` 504,330) | `upper_calls=5317`, `admitted=5051`, `reserved=13404 >= actual=4244` |
| `G508_Peer_000_ndarray` | 965.178 | 137.380 | **129.567** | 1574.754 | **0.943x** (-5.7%) | 61,740 | `mesh_cache_hits=0` |
| `D48_5pair_tuple_nocache` | 548.282 | 90.026 | **75.263** | 198.048 | **0.836x** | 36,653 (vs `032` 101,169) | `upper_calls=2064`, `admitted=1846`, `actual=3743` |
| `D48_5pair_tuple_cached` | *n/a* | 81.710 | **68.381** | 192.869 | **0.837x** | 36,653 | `mesh_cache_hits=4` (deep tuple) |
| `D48_5pair_ndarray_uncached_control` | *n/a* | 76.631 *(R2 hit=4)* | **72.281** *(safe)* | 200.904 | **0.943x** | 36,653 | `mesh_cache_hits=0` (C01 fail-closed) |
| `Control_12F_tuple` | 25.130 | 5.241 | **4.667** | 4.818 | 0.890x | 4,633 (vs `032` 4,753) | Linear fallback |
| `Control_12F_ndarray` | 24.669 | 4.614 | **4.353** | 4.515 | 0.943x | 4,633 | Linear fallback |
| `Sparse_100kV_1F_loose_nan_ndarray` | 0.654 | 0.373 | **0.314** | 0.338 | 0.842x | 51 | `referenced_vertices=6` |
| `Tilted_48x48` | 25.966 | 12.405 | **10.761** | 11.266 | **0.867x** | 6,191 (`OFF` 6,894) | `upper_calls=246`, `admitted=221`, `actual=404 <= reserved=974` |
| `Sheet_Parallel_5um` | 2609.831 | 26.423 | **20.912** | 21.240 | **0.791x** | 14,246 | `032` speedup **124.8x** |

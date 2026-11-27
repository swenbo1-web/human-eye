# Kernel-041 R3 Minimal Closure Review (`KERNEL_041_R3_CLOSURE_REVIEW`)

> **Verdict**: `RESTRICTED_EXPERIMENT_ONLY`  
> **Base R3 Commit Reviewed**: `7f907d05c53bb57cebbe037e540485e228240060` (`codex/m3-bvh-deep-optimization`)  
> **Target Runtime Source SHA-256 (`human_eye_plugin/surface_proximity.py` normalized)**: `eff6511223646c125ac05cd6080d3bcbe191d1c945a8b3b7293d2c1bc0ff1ee4`  
> **Scope**: Minimal, versioned closure of independent re-review findings **R3-F01** through **R3-F06** against `surface_proximity.py` and benchmark/verifier harnesses, preserving all historical, R2, and earlier R3 artifacts byte-for-byte.

---

## 1. Executive Summary & Scope Decision

This review documents closure of the six findings raised in the independent R3 re-review (`R3-F01`–`R3-F06`) without touching sibling runtime modules (`task_query.py`, `surface_scan.py`, `surface_geometry.py`), Blender/MCP adapters, hook dispatch, public schemas, or any kernel budget constant (`MAX_FACES=4096`, `MAX_WORK_UNITS=1179648`, `MAX_NARROW_PHASE_PAIRS=16384`, `LINEAR_PAIR_LIMIT=256`, closed-solid `262144`).

- **Option A Retained**: Kept Option A (`settled_credit_031_ref`) as requested, eliminating C03 credit holes against an **actually executed** paid-dequeue reference mode (`_projection_mode='off_paid_dequeue_ref'`) rather than an unexecuted arithmetic proxy.
- **Honest Restrictions Preserved**:
  1. Verdict remains `RESTRICTED_EXPERIMENT_ONLY`.
  2. Private historical fixtures (`zero489`, `first_yield`, `pair129`, original `040` 48F ordering) remain `MISSING_HISTORICAL_INPUT` in this repository.
  3. On `tilted48` and 5-epoch `G508_Competing_001`, Option A has **0 holes** vs executed `M_paid_ref` across normal and injected in-admission failures, while documented holes remain relative to `M_off` (`tilted48`: 8 holes on failed direction, 33 on failed slab; `G508_Competing_001`: 33 holes on failed direction).
  4. On live `tilted48` and `G508_Peer_000`, `live_box_only_pruned_pairs = 0` (`live_box_only_status = NOT_EXERCISED`); box AABB raw-vertex containment is proved via `synthetic_box_control = PASS` and unit tests in `test_kernel_041_r3_closure.py`.
  5. Direct-kernel smoke timings use 1 warmup + 3 verified repeats in serial isolated subprocesses with `tracemalloc`; no p95 distribution claim or single-variable C02 speedup claim is made.

---

## 2. Finding-to-Fix Matrix (`R3-F01` – `R3-F06`)

| ID | Finding Summary | Minimal Fix Applied | Primary Evidence |
| --- | --- | --- | --- |
| **R3-F01** | `M_off + aabb_bound_tests` proxy overcounted (`032` reuses parent AABB bounds on `shift==0` dequeue without calling `aabb_bound_tests`); in-admission failure tests didn't exercise real `credit.try_run` / 5-epoch churn. | Added executed `_projection_mode='off_paid_dequeue_ref'` in `surface_proximity.py` (`dequeue_reused_aabb_bounds` charges `budget.tick('aabb_bound_tests')` when `shift==0 and best is not None`); added `_FastWitnessProjection._slab_exceeds_cutoff` called inside real `credit.try_run`; swept `[0..32]` across `tilted48`, real 5-epoch `G508_Competing_001` (5 direction builds, 4 invalidations), and `sheet5um`. | `KERNEL_041_R3_CLOSURE_RESULTS.json` (`audits.c03_integer_sweeps`), `test_kernel_041_r3_closure.py` (`TestR3Closure_F01_*`), `test_kernel_041_r3_c01_to_c06.py` (`TestR3_C03`) |
| **R3-F02** | Wrapper rebind-and-restore during `_pair_from_mesh_cache` admission could leave mismatched refs (`_admit_one` re-read live `mesh.vertices`/`mesh.faces`), and cached `topology` dicts returned directly allowed external mutation of cache internals. | `_pair_from_mesh_cache` captures `(l_verts, l_faces)` and `(r_verts, r_faces)` once before callbacks; `_admit_one(..., verts=verts_ref, faces=faces_ref)` admits solely from those frozen refs; `_mesh_cache_is_immutable(verts, faces, budget)` validates frozen refs without re-reading wrapper attrs; detects attribute rebinding (`is not`) at Stage 1 or Stage 2/3 checkpoints to evict/block cache insertion; returns `[dict(topo_l), dict(topo_r)]` detached copies. | `human_eye_plugin/surface_proximity.py` (`_admit_one`, `_pair_from_mesh_cache`), `test_kernel_041_r3_closure.py` (`TestR3Closure_F02_*`) |
| **R3-F03** | `benchmarks/run_ablation_and_assets.py` still compared cross-arm G508 and B02 entries with inline code / bare `assert`s instead of verifier helper, stripping bindings without verifying exact arm SHAs. | Added `check_entry_receipts` / `assert_entry_receipts_equal` in `benchmarks/bvh_eval.py` (verifies `ref_runtime_sha` and `cand_runtime_sha` BEFORE normalizing `runtime_source_sha256`, plus bidirectional `spatial_relation` and mandatory `dispositions` on `scan` entries); wired `run_ablation_and_assets.py` via `_require` (no bare `assert`, safe under `python -O`). | `benchmarks/bvh_eval.py`, `benchmarks/run_ablation_and_assets.py`, `test_kernel_041_r3_closure.py` (`TestR3Closure_F03_F04_F05_*`) |
| **R3-F04** | Surface/spatial/scan signature validation allowed malformed `distance_m`, invalid exact rank fields under `retain_exact_rank=True`, or inconsistent `witness_status`/`direction_status` under `valid=True`, plus missing binding/rank/option checks in comparator controls. | Tightened `_validate_surface_sig_struct` (finite `distance_m >= 0.0`, strict rank typing when `retain_exact_rank=True`, option-aware valid witness/direction invariants while permitting legitimate `None` provenance / `measurement_valid=False` stops); expanded `bvh_eval.verify_comparator_negative_controls()` to **54 controls**, verified passing under both normal Python and `python -O`. | `benchmarks/bvh_eval.py` (`54/54` controls normal & `-O`), `KERNEL_041_R3_CLOSURE_RESULTS.json` (`gates.C04_comparator_*`) |
| **R3-F05** | Subprocess evaluation script relied on self-reported metadata without external expected pin & workload manifests, and lacked per-repeat output hash trails or reproducible multi-arm CLI flags. | Added `expected_workload_manifest`, `expected_arm_pins`, and CLI flags `--expected-baseline-sha` / `--expected-current-sha` to `bvh_eval.py`; updated `run_r3_closure_eval.py` with `--output-prefix`, `--arm-manifest`, `--expected-r3-sha`, mandatory worker external pin assertions, per-repeat `repeat_signature_sha256` lists, and file SHA pinning in `KERNEL_041_R3_CLOSURE_CASES.json`. | `benchmarks/bvh_eval.py`, `benchmarks/run_r3_closure_eval.py`, `KERNEL_041_R3_CLOSURE_CASES.json`, `KERNEL_041_R3_CLOSURE_RESULTS.json` |
| **R3-F06** | C05a projection audit cast exact `Fraction` to `int(...)` directly, lacked explicit `live_box_only = NOT_EXERCISED` labeling, and affine fallback cache loop shared the top-level `'mesh_cache'` budget stage name. | Enforced `frac.denominator == 1` pre-check in C05a audit; separated `live_box_only_status = "NOT_EXERCISED"` from `"synthetic_box_control": "PASS"`; added `'mesh_cache_affine_fallback'` to `_WORK_STAGES` and switched `_pair_from_mesh_cache` affine fallback checkpoint to `'surface_proximity_mesh_cache_affine_fallback'`. | `human_eye_plugin/surface_proximity.py`, `benchmarks/run_r3_closure_eval.py`, `benchmarks/test_kernel_041_r3_c01_to_c06.py`, `benchmarks/test_kernel_041_r3_closure.py` |

---

## 3. Executed Verification Evidence

### 3.1 Paid-Dequeue Reference Audit (`R3-F01`, `[0..32]` Work-Unit Delta Sweep)

| Case | `M_off` | `dequeue_reused_aabb_bounds` | Old Arithmetic Proxy (`M_off + aabb_bound_tests`) | Exact Executed `M_paid_ref` (`off_paid_dequeue_ref`) | `ON_normal` Work Units (Credit Stats) | Holes vs `M_paid_ref` (ALL 5 variants) | Holes vs `M_off` (Documented Option A Property) |
| --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| `tilted48` | `6894` | `605` | `8022` (overcounted by `+523`) | **`7499`** | `6191` (`1` dir build, `0` inv, `221` slabs, `404 <= 974` reserved, `83` vertex_slab prunes) | **`0`** across `PAID_REF`, `OFF`, `ON_normal`, `ON_in_admission_fail_dir`, `ON_in_admission_fail_slab` | `OFF=0`, `ON_normal=0`, `fail_dir=8` (`invalid=[0..5], prov=[6,7]`), `fail_slab=33` (`invalid=[0..32]`) |
| `G508_Competing_001` (5-epoch churn) | `36755` | `1770` | `40594` (overcounted by `+2069`) | **`38525`** | `13406` (`5` dir builds, `4` inv, `285` slabs, `1026 <= 1804` reserved, `218` vertex_slab prunes, credit bal `33`) | **`0`** across all 5 variants | `OFF=0`, `ON_normal=0`, `fail_slab=0`, `fail_dir=33` (`invalid=[0..32]`) |
| `sheet5um` | `14246` | `51` | `14308` (overcounted by `+11`) | **`14297`** | `14246` (`0` dir builds, `0` inv, `0` slabs, credit bal `51`) | **`0`** across all 5 variants | **`0`** across all variants |

### 3.2 Structural & Gate Checks

- **`bvh_eval.py --verify-comparator`**: Passed under both normal execution and `python -B -O`, verifying **54/54** negative controls (`C04_comparator_normal`, `C04_comparator_python_O`).
- **Unit Suites**: Passed `test_kernel_041_r3_closure.py`, `test_kernel_041_r3_c01_to_c06.py`, and `test_kernel_041_k01_to_k07.py` (**26 tests, OK**).
- **`verify_review_suite.py`**: **7/7 PASS** (`r01_fast_projection`, `r02_mesh_cache`, `r03_sah_translation`, `r04_bit_domain_and_predicates`, `r05_tie_pruning_and_subtree_oracle`, `r07_closed_and_analyze`, `assets_a01_to_a05`; frozen JSON artifacts preserved).
- **Closed-Solid `032` vs `R3 Closure` Differential**: `exact_signature_match = true` on `Closed_48F_crossed_boxes` (`penetrating`, `transverse_boundary_interiors`), `Closed_Containment_Obj001_Obj024` (`penetrating`, `disjoint_boundaries_with_exact_parity`), and `Closed_Separated_Control_AB` (`separated`, `disjoint_boundaries_with_exact_parity`).
- **C05a Projection Exclusion & Containment Audit**:
  - `tilted48` (exhaustive raw vertex recomputation): `83/83` events passed (`55` strict, `28` tie, `614` descendant pairs); `live_box_only_status = "NOT_EXERCISED"`, `synthetic_box_control = "PASS"`.
  - `G508_Peer_000` (sampled local exclusion, not global proof): `50/823` events sampled (`25` strict, `25` tie, `1471` pairs), all passed; `live_box_only_status = "NOT_EXERCISED"`, `synthetic_box_control = "PASS"`.
- **C06 Cache Retention**: Inserting `281` distinct meshes retains `256` entries (`256` faces, `768` ref vertices); explicitly documented as an entry-count cap (`MAX_CACHED_MESHES = 256`), not a process RSS/byte cap.

### 3.3 Bounded Exploratory Direct-Kernel Smoke (`1` warmup + `3` repeats, serial isolated subprocesses, `tracemalloc`)

| Workload | `032` (`6c93f237`) | Prior `R2` (`b7d469d`) | `R3 Closure` Default | `R3 Closure` `OFF` |
| --- | --- | --- | --- | --- |
| `Control_12F_ndarray` | `22.272 ms` (`4753 wu`) | `4.454 ms` (`4633 wu`) | `4.326 ms` (`4633 wu`) | `5.066 ms` (`4633 wu`) |
| `Control_12F_tuple` | `21.834 ms` (`4753 wu`) | `4.444 ms` (`4633 wu`) | `4.301 ms` (`4633 wu`) | `4.840 ms` (`4633 wu`) |
| `D48_5pair_tuple_nocache` | `507.663 ms` (`101169 wu`) | `104.381 ms` (`36926 wu`) | `78.614 ms` (`36653 wu`) | `207.626 ms` (`101979 wu`) |
| `D48_5pair_tuple_cached` | `—` | `79.090 ms` (`hits=4`) | `73.820 ms` (`36653 wu, hits=4`) | `198.314 ms` (`hits=4`) |
| `D48_5pair_ndarray_uncached_control` | `—` | `73.643 ms` (`hits=4` unsafe) | `72.463 ms` (`36653 wu, hits=0`) | `221.814 ms` (`hits=0`) |
| `G508_Peer_000_tuple` | `950.356 ms` (`504330 wu`) | `132.199 ms` (`61598 wu`) | `134.851 ms` (`61740 wu`) | `1671.352 ms` (`489205 wu`) |
| `G508_Peer_000_ndarray` | `908.456 ms` (`504330 wu`) | `143.466 ms` (`61598 wu`) | `150.064 ms` (`61740 wu`) | `1784.708 ms` (`489205 wu`) |
| `Sheet_Parallel_5um` | `2325.386 ms` (`419636 wu`) | `20.957 ms` (`14246 wu`) | `24.143 ms` (`14246 wu`) | `23.095 ms` (`14246 wu`) |
| `Sparse_100kV_1F_loose_nan_ndarray` | `0.625 ms` (`54 wu`) | `0.318 ms` (`51 wu`) | `0.316 ms` (`51 wu`) | `0.348 ms` (`51 wu`) |
| `Tilted_48x48` | `23.886 ms` (`7193 wu`) | `10.590 ms` (`6179 wu`) | `10.538 ms` (`6191 wu`) | `10.938 ms` (`6894 wu`) |

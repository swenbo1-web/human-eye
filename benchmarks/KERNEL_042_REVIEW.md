# Kernel-042 Exact Build-Pipeline Architecture Review (`KERNEL_042_REVIEW`)

> **Verdict**: `CANDIDATE_F_VALIDATED_RESEARCH_ONLY` (**Isolated Research Candidate `B1 + B2 + B4`**)  
> **Research Branch**: `codex/m3-bvh-exact-build-pipeline-042`  
> **Frozen 041 Reference Commit**: `119327bbb4e645c5de3bfbc0d30259736b9a2677` (`runtime_source_sha256 = eff6511223646c125ac05cd6080d3bcbe191d1c945a8b3b7293d2c1bc0ff1ee4`)  
> **Promoted Candidate Runtime Identity (`source_sha256`)**: `b0e4093dadf3eff8c9be18442922d802a4fa59adf2035f37958e8d5f32597dcd`  
> - `human_eye_plugin/surface_geometry.py` SHA-256: `5c116d6a1e6d48dec2f0b927769a6386c857d6a643725612167230f9ab86dc2c`  
> - `human_eye_plugin/surface_proximity.py` SHA-256: `c39d76d84075af92b373e5e76fdd31cfe7210fcfa147115e9af6bcde907a2143`

---

## 1. Executive Summary & Isolation Boundary

BVH-042 investigated exact, topology-preserving build-pipeline reductions on `human_eye_plugin/surface_geometry.py` and `human_eye_plugin/surface_proximity.py` without changing the frozen 041 integration candidate (`119327bbb`) or any concurrent Hook / host path.

- **Selected Research Candidate — Arm F (`B1 + B2 + B4`)**:
  - **B1**: Fused single-pass geometry + doubled-centroid extrema scan in `_build_sah_bvh` strictly gated on `sah_eligible = (n > leaf_size and n > _SAH_MIN_N and depth < _SAH_MAX_DEPTH)` with bounded periodic cancellation checkpoints (`n >= 512`).
  - **B2**: Exact integer division-free stable partition `cut = best_cmin + (best_split * best_cspan + _SAH_BINS - 1) // _SAH_BINS`, eliminating all per-triangle floor divisions in the winning split pass while preserving exact order and fallback semantics.
  - **B4**: Added `_bvh_from_flat_bounds(...)` alongside preserved `_bvh(...)`, feeding pre-flattened 9-tuples directly from `surface_proximity._distance_roots` and `_pair_from_mesh_cache` (eliminating nested 3-tuple intermediate lists while preserving `holder['trees']['bounds']` when requested).
- **Rejected Alternatives**:
  - **Arm E (`B1 + B2 + B3` inheriting winning SAH child bounds)**: Explicitly **rejected** — allocating 12-bin child bound tuples (`r_bounds`) per axis caused a **`-19.0%`** median wall regression on `Assembly24_Obj014_23pairs`.
  - **Compile/translate fusion**: Explicitly **skipped** because S0 measured `_compile_bvh_node` at only `0.36%–1.42%` of total runtime (`0.22–1.43 ms`).
- **Scope & Experiment Integrity**:
  - Untouched: `task_query.py`, `surface_scan.py`, `_bvh_median`, closed-solid callers, host/Hook/launcher adapters, schemas, and all constants (`MAX_FACES=4096`, `MAX_WORK_UNITS=1179648`, `MAX_NARROW_PHASE_PAIRS=16384`, `LINEAR_PAIR_LIMIT=256`, closed-solid `262144`, `_SAH_BINS=12`, `_SAH_MIN_N=12`, `_SAH_MAX_DEPTH=20`).
  - Historical private fixtures (`zero489`, `first_yield`, `pair129`, original `040` 48F ordering) remain `MISSING_HISTORICAL_INPUT`.

---

## 2. S0 Baseline Phase Profiling (Frozen `119327bbb`)

Measured in a separate instrumented pass (`Python 3.14.10`, `Windows-11-10.0.26200-SP0`, 16-core `Intel64 Model 165 Stepping 5`), kept strictly separate from uninstrumented primary wall timings (`7`-repeat and `30`-repeat paired runs).

### 2.1 Real Frozen Snapshot Assets (`classification = "real_frozen_snapshot_asset"`)

| Workload | Uninstr Median (ms) | Build Total (ms, %) | Flat (ms) | AABB + Centroid (ms) | Hist (ms) | SAH Eval (ms) | Partition (ms) | Compile (ms, %) | Traverse (ms) | `bin_div` | `part_div` | `mesh_cache_hits` (unc / cached) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `G508_Peer_000` (508F x 508F) | `139.31` | `61.32` (`35.3%` instr) | `2.20` | `4.88 + 2.88` | `26.13` | `13.49` | `4.55` | `0.49` (`0.36%`) | `104.46` | `18417` | `6139` | `0` / `—` |
| `G508_Competing_001` (508F x 60F) | `29.49` | `13.85` (`46.4%` instr) | `0.85` | `1.07 + 0.60` | `5.79` | `2.93` | `0.99` | `0.37` (`1.24%`) | `11.27` | `9636` | `3212` | `0` / `—` |
| `D48_Real_47pairs` (47 x 60F) | `931.16` | *batch* | — | — | — | — | — | — | — | — | — | `0` / `46` |
| `Assembly24_Obj014_23pairs` (23 parts) | `127.80` | *batch* | — | — | — | — | — | — | — | — | — | `0` / `22` |

### 2.2 Analytic Synthetic & Control Workloads (`classification = "analytic_synthetic_or_control"`)

| Workload | Uninstr Median (ms) | Build Total (ms, %) | Flat (ms) | AABB + Centroid (ms) | Hist (ms) | SAH Eval (ms) | Partition (ms) | Compile (ms) | Traverse (ms) | `bin_div` | `part_div` | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `HighRes_1536F_Pair` | `112.61` | `86.81` (`76.6%`) | `3.86` | `6.78 + 4.25` | `39.75` | `16.80` | `6.99` | `1.43` | `3.75` | `68592` | `22864` | Dominant build bottleneck |
| `Sheet_Dented_2mm` | `26.02` | `20.27` (`72.3%`) | `1.19` | `1.79 + 1.16` | `8.03` | `3.69` | `1.87` | `0.43` | `0.33` | `13824` | `6144` | Dominant build bottleneck |
| `Sheet_Parallel_5um` | `24.08` | `16.05` (`69.0%`) | `1.35` | `1.65 + 1.08` | `5.64` | `2.17` | `1.81` | `0.38` | `0.67` | `10240` | `6144` | Dominant build bottleneck |
| `Rotated_30deg_Spheres` | `15.70` | `9.51` (`56.8%`) | `0.78` | `0.71 + 0.39` | `3.54` | `2.29` | `0.58` | `0.22` | `3.54` | `5904` | `1968` | Balanced build/traverse |
| `Tube_Coiled_Loose` | `64.00` | `35.01` (`55.7%`) | `1.88` | `2.65 + 1.58` | `14.87` | `7.80` | `2.56` | `0.69` | `17.82` | `25716` | `8572` | Build 55.7% |
| `Control_12F_Linear` | `4.45` | `0.00` | — | — | — | — | — | — | — | `0` | `0` | Verified `tree_builds == 0` |

> **Instrumentation Jitter Caveat**: In the conditional 1-shot instrumented pass, `HighRes_1536F_Pair` Arm F recorded a transient single-shot OS scheduling spike (`119.32 ms` vs A `83.54 ms`), whereas a separate 3-shot median instrumented probe measured `A = 88.708 ms -> F = 79.453 ms` (**`-10.43%`** build phase) and `G508_Peer_000` measured `A = 25.304 ms -> F = 22.485 ms` (**`-11.14%`**), consistent with all uninstrumented paired runs.

---

## 3. Paired Ablation Screening (`warmup=2, repeats=7`, Uncached Deep Tuple)

| Workload | A `119327b` (ms) | B (`B1`) Δ% | C (`B2`) Δ% | D (`B1+B2`) Δ% | E (`+B3`) Δ% | F (`B1+B2+B4`) Δ% | Decision Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `HighRes_1536F_Pair` | `112.61` | `-0.98%` | `+4.57%` | `+5.54%` | `+4.01%` | **`+6.87%`** | F wins |
| `Sheet_Dented_2mm` | `26.02` | `+1.81%` | `+4.99%` | `+4.93%` | `+7.35%` | **`+5.46%`** | F passes `>= 5%` |
| `Sheet_Parallel_5um` | `24.08` | `+1.68%` | `+1.77%` | `+1.92%` | `+5.98%` | **`+8.96%`** | F passes `>= 5%` |
| `Rotated_30deg_Spheres` | `15.70` | `-1.38%` | `+2.38%` | `+2.56%` | `+4.80%` | **`+5.20%`** | F passes `>= 5%` |
| `Tube_Coiled_Loose` | `64.00` | `+0.69%` | `+4.55%` | `+5.60%` | `+3.36%` | **`+4.87%`** | Positive |
| `G508_Peer_000` | `139.31` | `+1.00%` | `+0.63%` | `-0.15%` | `+2.14%` | **`+1.97%`** | Zero regression |
| `G508_Competing_001` | `29.49` | `-2.84%` | `-1.38%` | `+1.62%` | `+0.93%` | **`+3.25%`** | Zero regression |
| `D48_Real_47pairs` | `931.16` | `+0.91%` | `-1.90%` | `+1.98%` | `+0.31%` | **`+0.33%`** | Neutral/pos |
| `Assembly24_Obj014_23pairs` | `127.80` | `-0.33%` | `+0.51%` | `+0.54%` | **`-19.00%`** | **`+2.84%`** | **E rejected**; F positive |
| `Control_12F_Linear` | `4.45` | `+0.74%` | `-0.42%` | `+0.92%` | `-0.12%` | `-2.03%` | Within noise (`~0.09 ms`) |

*Pre-registered Gate Summary*: Only **Arm F** met all Section 9 screening bars (`count_build_ge_10pct = 3 >= 2`, `count_heavy_wall_ge_5pct = 4 >= 1`, `max_guard_regression_pct = 2.03% < 5.0%`).

---

## 4. 30-Repeat Paired Confirmation (`A vs F`, Uninstrumented)

> `p95_estimator = linear_interpolation_type7_on_sorted_direct_kernel_samples` (`n = 30`). Direct-kernel exploratory distribution only — **NOT a host p95 claim**.

| Workload | A Median (ms) | F Median (ms) | Paired Median Reduction % | Paired Mean Reduction % | A p95 (ms) | F p95 (ms) | `ndarray` Paired Median % | `tracemalloc` Peak (A -> F bytes) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `HighRes_1536F_Pair` | `102.33` | `95.02` | **`+7.19%`** | `+11.29%` | `142.23` | **`103.60`** | `+6.92%` | `8,769,253 -> 8,629,053` |
| `Sheet_Dented_2mm` | `29.92` | `28.32` | **`+9.42%`** | `+8.01%` | `35.66` | **`32.87`** | `+7.75%` | `2,712,029 -> 2,639,005` |
| `Rotated_30deg_Spheres` | `17.01` | `15.60` | **`+5.12%`** | `+4.67%` | `23.90` | `22.83` | `+3.63%` | `1,294,125 -> 1,265,341` |
| `Tube_Coiled_Loose` | `66.02` | `63.40` | **`+3.21%`** | `+4.88%` | `80.94` | `73.94` | `+4.97%` | `4,097,657 -> 4,006,065` |
| `G508_Peer_000` | `127.38` | `124.15` | **`+2.26%`** | `+3.59%` | `167.90` | `159.22` | `+1.90%` | `3,097,913 -> 3,036,857` |
| `G508_Competing_001` | `26.78` | `25.80` | **`+3.77%`** | `+5.32%` | `29.46` | `26.52` | `+3.98%` | `1,659,957 -> 1,591,141` |
| `Control_12F_Linear` | `5.18` | `5.10` | `+1.00%` | `-6.47%` | `5.73` | `8.17` | `+0.82%` | `51,116 -> 51,116` |
| `Sparse_100kV_Degenerate_MixedBit` | `1.43` | `1.39` | `+2.60%` | `+2.33%` | `1.54` | `1.51` | `+2.24%` | `141,673 -> 141,113` |
| `D48_Real_47pairs` (uncached) | `936.62` | `919.50` | `+0.83%` | — | — | — | — | — |
| `D48_Real_47pairs` (cached, `hits=46`) | `919.01` | `931.60` | `-1.13%` | — | — | — | — | — |
| `Assembly24_Obj014_23pairs` (uncached) | `130.45` | `125.94` | **`+4.07%`** | — | — | — | — | — |
| `Assembly24_Obj014_23pairs` (cached, `hits=22`) | `109.32` | `107.69` | `+0.59%` | — | — | — | — | — |

- **Win32 Process Working Set Probe** (`win32_K32GetProcessMemoryInfo_WorkingSet_and_PeakWorkingSet_bytes`, separate probe in `KERNEL_042_RESULTS.json`):
  - Both A and F share bounded peak process working set `119,877,632` bytes (`ws_delta_bytes = 0` on F across `HighRes_1536F_Pair`, `Sheet_Dented_2mm`, `Tube_Coiled_Loose`, `G508_Peer_000`; `tracemalloc` peak drops `-140 KB` on `HighRes_1536F_Pair`).

---

## 5. Exact Semantics, Tree Digests & Verification Receipts

- **Complete Raw Tree & Solver Equivalence**: 100% recursive `(lo, hi, count, leaf_ids, left, right)` equality and identical `tree_sha256` digests (`G508_Peer_000`: `c084a5e2b912...`, `HighRes_1536F_Pair`: `0d3fc963a4fb...`, `Tube_Coiled_Loose`: `e343891e36e1...`), identical `_surface_sig`, and zero drift in `work_units` across every repeat (`repeat_signature_sha256`).
- **Executed Gate Commands**:
  - `e:\bvh\.venv\Scripts\python.exe -B benchmarks/bvh_eval.py --verify-comparator`: **PASS (`54/54` controls, `alias_caught=true`)**.
  - `e:\bvh\.venv\Scripts\python.exe -B -O benchmarks/bvh_eval.py --verify-comparator`: **PASS (`54/54` controls under `-O`)**.
  - `e:\bvh\.venv\Scripts\python.exe -B benchmarks/verify_review_suite.py`: **PASS (`7/7` suites, frozen JSON preserved)**.
  - `e:\bvh\.venv\Scripts\python.exe -B -m unittest benchmarks/test_kernel_042_build_pipeline.py benchmarks/test_kernel_041_r3_closure.py benchmarks/test_kernel_041_r3_c01_to_c06.py benchmarks/test_kernel_041_k01_to_k07.py -v`:
    - `test_kernel_042_build_pipeline.py`: **5/5 OK** (`>92,449` B2 predicate checks, complete raw-tree + edge/1100-bit/dyadic-scaling suite, `prepared_holder` ABI + compile parity + 3 projection modes, `n>=512` loop/compile/cache/publish cancellation + clean retry, `analyze` & `_bvh_median` untouched parity).
    - `test_kernel_041_r3_closure.py` + `test_kernel_041_r3_c01_to_c06.py` + `test_kernel_041_k01_to_k07.py`: **26/26 OK**.

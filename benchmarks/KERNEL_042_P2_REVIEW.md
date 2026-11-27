# Kernel-042 Phase 2 Review: Exact Common-Exponent Dyadic Frame & Admission (`KERNEL_042_P2_REVIEW`)

> **Verdict**: `CANDIDATE_K_VALIDATED_P2_RESEARCH_ONLY` (**Arm K = Phase-1 Arm I + `P2-A` Direct Common-Exponent Dyadic Frame / Inlined Vertex Reader / Dense List Index Table**)  
> **Research Branch**: `codex/m3-bvh-exact-build-pipeline-042`  
> **Frozen 041 Reference Commit**: `119327bbb4e645c5de3bfbc0d30259736b9a2677` (`source_sha256 = eff6511223646c125ac05cd6080d3bcbe191d1c945a8b3b7293d2c1bc0ff1ee4`)  
> **Phase-0 Arm F**: `5102f1fefc6ebee8b0ca5d7ad0c03530b672add4` (`source_sha256 = b0e4093dadf3eff8c9be18442922d802a4fa59adf2035f37958e8d5f32597dcd`)  
> **Phase-1 Arm I**: `8d68d1a133cb2635920ddd83b8b7f12bdc6e3869` (`source_sha256 = 1db11b89a8513e571faf55fbd9bccc183c82c12b6bf43159cb7b1f28b1f7f7ab`)  
> **Promoted P2 Candidate Runtime Identity (`source_sha256`)**: `cc78597b4b4c9e336e7082bcb2fd99ba9739ead2e01104c095f8046fe048baf7`  
> - `human_eye_plugin/surface_proximity.py` SHA-256: `7210292168449c2da2f2de731179bd464abde021ed84ea7f04b3a9daa8626a80`  
> - `human_eye_plugin/surface_geometry.py` SHA-256 (unchanged from `8d68d1a13`): `84cb39427d78c4174868285019b3929f28a564c6287584d03336faa77175169e`

---

## 1. Executive Summary & Architectural Decisions

Phase 2 (`042-P2`) addressed the second-largest direct-kernel bottleneck exposed in Phase-0/P1 profiles: `admission_and_vertex_prep` (`15%–28%` of total runtime on heavy/sheet workloads), without modifying `surface_geometry.py`, BVH topology, budget accounting, or any 041 contract.

- **Winner Selected — Arm K (`P2-A` only)**:
  1. **Direct Common-Exponent Dyadic Frame (`_integer_frame`)**: When binary64 exponent spread across referenced vertices satisfies `max_e - min_e <= 900` and `-min_e <= 900`, shifts mantissas once to `E_upper = max(0, -min_e)` relative to origin, tracks exact trailing zero mask `or_all`, and strips exact common exponent `common_tz` globally — skipping per-vertex `_float_dyadic` TZ normalization, per-vertex `_sub_dyadic` normalization tuples, and intermediate `relative` dicts. Automatically preserves the exact `_sub_dyadic` fallback for extreme `> 900`-bit exponent spreads.
  2. **Inlined Finite Vertex Extraction & Dense Index List**: Inlines `is_np` vs Python sequence extraction in Pass 1 (with identical `len == 3` and `math.isfinite` fail-closed guards) and uses a flat Python `list` `[None] * (max_idx + 1)` only for dense un-held meshes (`holder is None and 0 <= max_idx < 65536 and max_idx < 4 * len(indices)`), keeping `dict` on sparse `100kV` containers and when `holder is not None` (`holder['coordinates']` ABI untouched).
- **Rejected Candidate Arms**:
  - **Arm L (`P2-B` tuple edges / 3-way `if` bounds in `_build_fast_triangles`)**: Rejected due to **`-11.64%`** guard regression on `Assembly24` (CPython built-in `min`/`max` + list edges outperformed branching Python `if/else`!).
  - **Arm M (`P2-C` bit-packed edge keys in `_admit_one`)**: Rejected (`meets_p2_bar = false`, small regression on several workloads vs CPython's fast small-int 2-tuple hashing).
  - **Arm N (`K+L+M` combined)**: Excluded by the simplicity & guard criteria (`L` dragged `Assembly24` down to `142.06 ms` vs `K`'s `120.60 ms`, while `K` achieved **`0.51%`** max guard regression with clean, localized diff).

---

## 2. Paired P2 Screening & 3-Shot Prep Probe (`vs Phase-1 Arm I`)

| Workload | `I` (`8d68d1a`) Prep 3-shot (ms) | `K` Prep 3-shot (ms, Δ%) | `I` Screen Wall (ms) | `K` Screen Wall Δ% | `L` Δ% | `M` Δ% | `N` Δ% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `HighRes_1536F_Pair` | `19.27` | `17.85` (`+7.4%`) | `84.89` | **`+3.24%`** | `+2.52%` | `+0.55%` | `+5.01%` |
| `Sheet_Dented_2mm` | `6.24` | `5.22` (**`+16.4%`**) | `20.57` | **`+3.34%`** | `-0.55%` | `-0.08%` | `+6.29%` |
| `Sheet_Parallel_5um` | `5.72` | `4.50` (**`+21.3%`**) | `18.11` | **`+5.38%`** | `+2.02%` | `+2.57%` | `+6.64%` |
| `Rotated_30deg_Spheres` | `2.52` | `2.16` (**`+14.2%`**) | `13.17` | `+1.13%` | `+2.12%` | `-1.35%` | `+1.02%` |
| `Tube_Coiled_Loose` | `9.11` | `7.83` (**`+14.1%`**) | `51.33` | `+1.97%` | `+0.15%` | `-1.41%` | `+1.33%` |
| `G508_Peer_000` | `6.27` | `5.20` (**`+17.0%`**) | `120.84` | zero reg | zero reg | zero reg | zero reg |
| `Assembly24_Obj014_23pairs` | — | — | `124.45` | **`120.60 ms`** | **`135.62 ms (-11.6% nd)`** | `122.52 ms` | `142.06 ms` |
| `D48_Real_47pairs` | — | — | `854.77` | `862.46 ms` (`-0.51%`) | `874.17 ms` | `865.53 ms` | `865.75 ms` |

---

## 3. 30-Repeat Confirmatory Paired Results (`A` vs `I` vs `K`, Uninstrumented)

> `p95_estimator = linear_interpolation_type7_on_sorted_direct_kernel_samples` (`n = 30`). Exploratory direct-kernel distribution only — **NOT a host p95 claim**.

| Workload | A `119327b` (ms) | I `8d68d1a` (ms) | K P2 (ms) | Paired vs I % (`ndarray` %) | **Cumulative vs 041 A %** | I -> K p95 (ms) | `tracemalloc` Peak (I -> K bytes) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `HighRes_1536F_Pair` | `105.28` | `87.10` | **`84.18`** | `+2.08%` (`+2.45%`) | **`+19.53%`** | `132.85 -> 113.58` | `8,623,105 -> 8,861,577` |
| `Sheet_Dented_2mm` | `26.34` | `21.59` | **`20.15`** | **`+5.87%`** (`+7.86%`) | **`+21.93%`** | `49.02 -> 32.09` | `2,632,357 -> 2,666,905` |
| `Sheet_Parallel_5um` | `21.41` | `18.04` | **`17.22`** | **`+4.50%`** (`+5.54%`) | **`+19.10%`** | `21.85 -> 38.88` | `2,405,529 -> 2,438,969` |
| `Rotated_30deg_Spheres` | `15.12` | `13.23` | **`12.95`** | `+2.04%` (`+0.07%`) | **`+14.07%`** | `16.59 -> 26.62` | `1,262,909 -> 1,274,865` |
| `Tube_Coiled_Loose` | `60.47` | `53.01` | **`52.19`** | `+1.76%` (`+1.26%`) | **`+13.21%`** | `101.32 -> 63.42` | `4,002,945 -> 4,045,177` |
| `G508_Peer_000` | `125.19` | `121.17` | **`120.00`** | `+0.74%` (`+1.28%`) | **`+4.54%`** | `168.60 -> 177.73` | `3,036,361 -> 3,128,261` |
| `G508_Competing_001` | `26.65` | `24.35` | **`24.02`** | `+1.43%` (`+3.20%`) | **`+9.97%`** | `25.08 -> 25.55` | `1,589,197 -> 1,615,469` |
| `Control_12F_Linear` | `4.30` | `4.30` | **`4.24`** | `+0.99%` (`+1.13%`) | **`+0.87%`** | `4.43 -> 4.42` | `50,924 -> 53,764` |
| `Sparse_100kV_Degenerate_MixedBit` | `1.26` | `1.21` | **`1.15`** | **`+5.49%`** (`+5.77%`) | **`+8.67%`** | `1.35 -> 1.24` | `140,537 -> 138,565` |
| `D48_Real_47pairs` (uncached) | `913.01` | `911.87` | **`895.60`** | `+0.06%` | **`+1.03%`** | — | — |
| `D48_Real_47pairs` (cached) | `882.56` | `854.92` | `858.61` | `-0.88%` | **`+1.60%`** | — | — |
| `Assembly24_Obj014_23pairs` (uncached) | `137.74` | `130.53` | **`128.52`** | `+0.61%` | **`+7.08%`** | — | — |
| `Assembly24_Obj014_23pairs` (cached) | `95.46` | `94.59` | **`93.84`** | `+1.25%` | **`+1.91%`** | — | — |

- Promoted post-promotion 3-shot direct prep (`_admit + _integer_frame`): `HighRes_1536F_Pair`: `A=21.52 -> I=19.43 -> K_promoted=18.23 ms`; `Sheet_Dented_2mm`: `I=6.46 -> K=5.34 ms` (`-17.3%`); `G508_Peer_000`: `I=6.51 -> K=5.01 ms` (`-23.0%`).
- Memory trade-off documented honestly: `raw_coords` staging adds `~23–90 KB` (`~2–3%`) temporary Python `tracemalloc` allocation vs I (`Sparse_100kV` stays `dict` and actually drops slightly `140,537 -> 138,565` bytes); Win32 peak working set unchanged.

---

## 4. Exactness, Compatibility & Executed Verification Receipts

- **Bit-for-Bit Frame & Tree Parity**: Identical `origin`, `factor`, `coordinates`, `prepared` triangle tuples, `topology`, and `tree_sha256` across tuple & ndarray inputs for all arms (`A, I, K, L, M, N`).
- **Gates Executed After Final Code Edit**:
  - `e:\bvh\.venv\Scripts\python.exe -B benchmarks/bvh_eval.py --verify-comparator`: **PASS (`54/54`)**
  - `e:\bvh\.venv\Scripts\python.exe -B -O benchmarks/bvh_eval.py --verify-comparator`: **PASS (`54/54` under `-O`)**
  - `e:\bvh\.venv\Scripts\python.exe -B benchmarks/verify_review_suite.py`: **PASS (`7/7`, frozen JSON preserved)**
  - `unittest` across **all 6 suites** (`test_kernel_042_p2_prep.py` + `test_kernel_042_p1_histogram.py` + `test_kernel_042_build_pipeline.py` + `test_kernel_041_r3_closure.py` + `test_kernel_041_r3_c01_to_c06.py` + `test_kernel_041_k01_to_k07.py`): **38/38 OK** in `89.127s`.

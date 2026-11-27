# Kernel-042 Phase 1 Review: Exact 11-Cut Histogram & SAH Evaluation (`KERNEL_042_P1_REVIEW`)

> **Verdict**: `CANDIDATE_I_VALIDATED_P1_RESEARCH_ONLY` (**Arm I = Phase-0 Arm F + `H1` 11-Cut Binary Decision Tree + `H2` Scratch Buffer Reuse / Empty-Bin Eval Skip / Scalar-First SAH Compare**)  
> **Research Branch**: `codex/m3-bvh-exact-build-pipeline-042`  
> **Frozen 041 Reference Commit**: `119327bbb4e645c5de3bfbc0d30259736b9a2677` (`source_sha256 = eff6511223646c125ac05cd6080d3bcbe191d1c945a8b3b7293d2c1bc0ff1ee4`)  
> **Phase-0 Arm F Baseline Commit**: `5102f1fefc6ebee8b0ca5d7ad0c03530b672add4` (`source_sha256 = b0e4093dadf3eff8c9be18442922d802a4fa59adf2035f37958e8d5f32597dcd`)  
> **Promoted P1 Candidate Runtime Identity (`source_sha256`)**: `1db11b89a8513e571faf55fbd9bccc183c82c12b6bf43159cb7b1f28b1f7f7ab`  
> - `human_eye_plugin/surface_geometry.py` SHA-256: `84cb39427d78c4174868285019b3929f28a564c6287584d03336faa77175169e`  
> - `human_eye_plugin/surface_proximity.py` SHA-256 (unchanged from `5102f1fef`): `c39d76d84075af92b373e5e76fdd31cfe7210fcfa147115e9af6bcde907a2143`

---

## 1. Executive Summary & Architectural Decisions

Phase 1 (`042-P1`) targets the residual ~70% of build cost remaining inside `surface_geometry._build_sah_bvh` after Phase 0 (`5102f1fef`): `axis_histogram_build` (`~45–50%` of build) and `prefix_suffix_sah_eval` (`~21–27%` of build), without altering tree topology, `surface_proximity.py`, budget ledgers, or any 041 contract.

- **Winner Selected — Arm I (`H1 + H2`)**:
  1. **`H1` Exact 11-Cut Division-Free Histogram**: Precomputes 11 exact integer bin thresholds per active axis (`t_s = cmin + ceil(s * cspan / 12)`) once per node and classifies every centroid with a 4-level balanced binary comparison tree instead of per-triangle `((c - cmin) * 12) // cspan` floor divisions (eliminating `68,592` divisions on `HighRes_1536F_Pair`, `25,716` on `Tube_Coiled_Loose`, `18,417` on `G508_Peer_000`, etc., with zero approximation and `n >= 512` periodic cancellation checkpoints preserved).
  2. **`H2` Scratch Reuse + Empty-Bin Eval Skip + Scalar-First SAH Compare**: Allocates one 9-list SAH working buffer (`_alloc_sah_scratch`) per root build (`n > leaf_size and n > _SAH_MIN_N`) rather than 9 lists per axis per internal node; caches unchanged suffix areas across empty bins; skips empty left bins in the prefix SAH loop (mathematically strict because any preceding non-empty bin yields an identical cost & count key with strictly smaller split index); compares scalar `cost = lc * larea + rc_s * right_area[b]` first and allocates tie tuples only on exact equality.
- **Rejected Candidate — Arm J (`H1 + H2 + H3` Fused 3-Axis Histogram)**:
  - Although Arm J achieved strong 1536F construction speedups (`-14.11%` vs F), allocating/packing 3 parallel scratch banks regressed the real 47-pair 60F assembly **`D48_Real_47pairs` by `-5.42%`** (`887.73 -> 921.00 ms`), triggering the pre-registered `< 5.0%` guard failure bar (`meets_p1_bar = false`). **Arm I achieved `0.0%` screening guard regression.**

---

## 2. Paired P1 Screening Results vs Phase-0 Arm F (`warmup=2, repeats=7`)

| Workload | F (`5102f1f`) ms | G (`H1`) Δ% | H (`H2`) Δ% | I (`H1+H2`) Δ% | J (`H1+H2+H3`) Δ% | Screen Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `HighRes_1536F_Pair` | `94.84` | `+4.12%` | `+5.54%` | **`+8.93%`** | `+14.11%` | I passes (`+8.93%`) |
| `Sheet_Dented_2mm` | `23.05` | `+3.64%` | `+5.99%` | **`+7.43%`** | `+9.51%` | I passes (`+7.43%`) |
| `Sheet_Parallel_5um` | `21.41` | `+3.96%` | `+10.82%` | **`+15.94%`** | `+13.51%` | I passes (`+15.94%`) |
| `Rotated_30deg_Spheres` | `14.02` | `+0.60%` | `+4.21%` | **`+6.22%`** | `+7.80%` | I passes (`+6.22%`) |
| `Tube_Coiled_Loose` | `57.06` | `+2.63%` | `+5.00%` | **`+7.21%`** | `+8.05%` | I passes (`+7.21%`) |
| `G508_Peer_000` | `130.17` | `+5.13%` (med ratio) | `+1.79%` | **`+6.21%`** | `+5.21%` | Zero regression |
| `G508_Competing_001` | `25.88` | `+2.32%` | `+3.44%` | **`+4.98%`** | `+8.11%` | Zero regression |
| `D48_Real_47pairs` (uncached) | `887.73` | `-1.11%` | `+0.21%` | **`+0.01%`** | **`-5.42%`** | **J rejected**; I neutral |
| `Assembly24_Obj014_23pairs` (uncached) | `122.29` | `+0.35%` | `+2.85%` | **`+2.60%`** | `+4.14%` | I positive |
| `Control_12F_Linear` (`tree_builds == 0`) | `4.34` | `+1.61%` | `+0.23%` | `+0.92%` | `+1.61%` | Guard clean |

- Separate direct `_distance_roots` 3-shot build probe (pre-promotion / post-promotion):
  - `HighRes_1536F_Pair`: `A=74.87ms -> F=70.38ms -> I_promoted=59.04ms` (`-16.1%` vs F, `-21.1%` vs A)
  - `Sheet_Dented_2mm`: `A=17.34ms -> F=15.32ms -> I_promoted=13.39ms` (`-12.6%` vs F, `-22.8%` vs A)
  - `G508_Peer_000`: `A=21.81ms -> F=19.38ms -> I_promoted=17.11ms` (`-11.7%` vs F, `-21.6%` vs A)

---

## 3. 30-Repeat Confirmatory Paired Results (`A` vs `F` vs `I`, Uninstrumented)

> `p95_estimator = linear_interpolation_type7_on_sorted_direct_kernel_samples` (`n = 30`). Exploratory direct-kernel distribution only — **NOT a host p95 claim**.

| Workload | A `119327b` (ms) | F `5102f1f` (ms) | I P1 (ms) | Paired vs F % (`ndarray` %) | **Cumulative vs 041 A %** | F -> I p95 (ms) | `tracemalloc` Peak (F -> I bytes) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `HighRes_1536F_Pair` | `99.52` | `93.24` | **`84.16`** | **`+9.39%`** (`+10.10%`) | **`+15.62%`** | `96.44 -> 91.23` | `8,628,421 -> 8,623,105` |
| `Sheet_Dented_2mm` | `24.38` | `22.55` | **`20.39`** | **`+9.64%`** (`+8.12%`) | **`+15.97%`** | `25.70 -> 24.64` | `2,638,469 -> 2,632,357` |
| `Sheet_Parallel_5um` | `20.19` | `18.38` | **`17.21`** | **`+5.82%`** (`+5.33%`) | **`+14.46%`** | `19.93 -> 18.72` | `2,410,881 -> 2,405,529` |
| `Rotated_30deg_Spheres` | `14.42` | `13.77` | **`12.72`** | **`+7.39%`** (`+6.91%`) | **`+11.57%`** | `20.86 -> 32.52` | `1,264,821 -> 1,262,909` |
| `Tube_Coiled_Loose` | `58.01` | `55.33` | **`51.11`** | **`+7.70%`** (`+7.00%`) | **`+11.69%`** | `81.52 -> 58.52` | `4,005,361 -> 4,002,945` |
| `G508_Peer_000` | `123.94` | `121.85` | **`119.76`** | `+1.66%` (`+1.66%`) | **`+2.87%`** | `165.34 -> 150.27` | `3,036,209 -> 3,036,361` |
| `G508_Competing_001` | `26.33` | `25.36` | **`24.13`** | **`+5.57%`** (`+4.72%`) | **`+8.56%`** | `42.91 -> 37.12` | `1,590,621 -> 1,589,197` |
| `Control_12F_Linear` | `4.45` | `4.42` | `4.48` | `-1.23%` (`-0.02%`) | `-0.49%` | `4.73 -> 5.02` | `50,924 -> 50,924` |
| `Sparse_100kV_Degenerate_MixedBit` | `1.25` | `1.22` | `1.21` | `+1.29%` (`+0.62%`) | **`+3.81%`** | `1.25 -> 1.27` | `140,921 -> 140,537` |
| `D48_Real_47pairs` (uncached) | `903.16` | `857.49` | `874.66` | `-0.71%` | **`+4.83%`** | — | — |
| `D48_Real_47pairs` (cached) | `849.66` | `834.00` | `849.52` | `-1.76%` | `-1.71%` | — | — |
| `Assembly24_Obj014_23pairs` (uncached) | `126.90` | `122.29` | **`119.64`** | `+2.71%` | **`+6.12%`** | — | — |
| `Assembly24_Obj014_23pairs` (cached) | `109.25` | `105.66` | `108.68` | `-0.77%` | `+0.41%` | — | — |

- Win32 `K32GetProcessMemoryInfo` probe (`KERNEL_042_P1_RESULTS.json`): Peak working set constant at `128,012,288` bytes across A, F, and `I_promoted` (`ws_delta_bytes <= 8,192` bytes on `I_promoted`).

---

## 4. Exactness, Compatibility & Executed Verification Receipts

- **Complete Raw-Tree Parity**: 100% node-by-node recursive equality and identical `tree_sha256` digests across all 6 arms (`A, F, G, H, I, J`) on every manifest workload.
- **Gates Executed After Final Code Edit**:
  - `e:\bvh\.venv\Scripts\python.exe -B benchmarks/bvh_eval.py --verify-comparator`: **PASS (`54/54` controls)**
  - `e:\bvh\.venv\Scripts\python.exe -B -O benchmarks/bvh_eval.py --verify-comparator`: **PASS (`54/54` controls under `-O`)**
  - `e:\bvh\.venv\Scripts\python.exe -B benchmarks/verify_review_suite.py`: **PASS (`7/7` suites, frozen JSON preserved)**
  - `e:\bvh\.venv\Scripts\python.exe -B -m unittest benchmarks/test_kernel_042_p1_histogram.py -v`: **4/4 OK** (`>100,000` exhaustive tiny-span & 1024-bit 11-Cut comparisons, manifest/edge/colliding-span/1100-bit tree parity, symmetric & empty-bin cross-axis tie stress tests, mid-histogram cancellation + retry + `analyze` & closed-solid `_bvh_median` parity)
  - `test_kernel_042_build_pipeline.py` (5/5 OK) + `test_kernel_041_r3_closure.py` (4/4 OK) + `test_kernel_041_r3_c01_to_c06.py` (11/11 OK) + `test_kernel_041_k01_to_k07.py` (11/11 OK) = **31/31 OK** on identical promoted runtime `1db11b89a8513e571faf55fbd9bccc183c82c12b6bf43159cb7b1f28b1f7f7ab`.

# Kernel-044 Phase 4 Handoff (`KERNEL_044_P4_HANDOFF`)

> **Verdict**: `CANDIDATE_044_P4_VALIDATED_ZERO_REGRESSION`  
> **Research Branch**: `codex/m3-bvh-p4-traversal-cutoff-044`  
> **Branched From (`freeze/m3-bvh-042-p2-arm-k`)**: `b5b0df58bed75f3a259af8078630e1cb511ff769` (`runtime_source_sha256 = cc78597b4b4c9e336e7082bcb2fd99ba9739ead2e01104c095f8046fe048baf7`)  
> **Frozen 041 Integration Reference (`freeze/m3-bvh-041-r3`)**: `119327bbb4e645c5de3bfbc0d30259736b9a2677` (`runtime_source_sha256 = eff6511223646c125ac05cd6080d3bcbe191d1c945a8b3b7293d2c1bc0ff1ee4`)  
> **Frozen P4 Runtime Identity (`runtime_source_sha256`)**: `7bfbd71982a7152cabf5cb04cf666fd8992bb016e6e09e01a6cd92a3c225b8d5`

---

## 1. Summary & Promotion Readiness

- **Exactness & Regression Gate (All Green)**:
  - `benchmarks/bvh_eval.py --verify-comparator` (normal & `-O`): **54/54 PASS** (`alias_caught=true`).
  - `benchmarks/verify_review_suite.py`: **100% PASS** (including tight-headroom deferral, credit invariants, R01–R08 & A01–A05).
  - Full unittest sweep (`test_kernel_044_p4_traversal.py`, `test_kernel_042_p2_prep.py`, `test_kernel_042_p1_histogram.py`, `test_kernel_042_build_pipeline.py`, `test_kernel_041_r3_closure.py`, `test_kernel_041_r3_c01_to_c06.py`, `test_kernel_041_k01_to_k07.py`): **42/42 OK** (`106.580s`).
  - Full `work` dict equality (`P4_A` vs `Arm K`): **100% identical** across 9 singles × 3 projection modes + `D48` & `Assembly24` (cached & uncached).
- **Performance Summary (`P4_A` Zero-Regression + `P4_B` Exact Batch Cutoff)**:
  - **`P4-A` vs Frozen `Arm K` (`b5b0df58b`)**: `G508_Peer_000` **`+15.21%` / `+15.98%`** (`118.49 -> 100.47 ms`), `G508_Competing_001` **`+7.20%`**, `D48_Real_47pairs` **`+13.57%`** unc / **`+14.14%`** cac (`845.94 -> 726.34 ms`), `Assembly24_Obj014_23pairs` **`+4.03%`** unc / **`+5.39%`** cac (`93.68 -> 88.64 ms`), `Tube_Coiled_Loose` **`+3.18%`**, `max_regression_vs_K = 0.83%` (`<= 2%` noise bar).
  - **`P4-B` (`measure_nearest_surface_batch`)**: `D48_Real_47pairs` **`1.64x–1.72x`** vs `K` (`864.49 -> 503.16 ms` cached; `879.31 -> 522.54 ms` uncached natural; `45/47` pruned), `Assembly24_Obj014_23pairs` **`3.10x–3.13x`** uncached / **`2.36x`** cached vs `K` (`116.67 -> 37.32 ms`).

---

## 2. Stage Freeze Tag Registry

| Stage | Git Tag | Commit | `runtime_source_sha256` |
| --- | --- | --- | --- |
| `041 R3 Closure` | `freeze/m3-bvh-041-r3` | `119327bbb4e645c5de3bfbc0d30259736b9a2677` | `eff6511223646c125ac05cd6080d3bcbe191d1c945a8b3b7293d2c1bc0ff1ee4` |
| `042 P0 Arm F` | `freeze/m3-bvh-042-p0-arm-f` | `5102f1fefc6ebee8b0ca5d7ad0c03530b672add4` | `b0e4093dadf3eff8c9be18442922d802a4fa59adf2035f37958e8d5f32597dcd` |
| `042 P1 Arm I` | `freeze/m3-bvh-042-p1-arm-i` | `8d68d1a133cb2635920ddd83b8b7f12bdc6e3869` | `1db11b89a8513e571faf55fbd9bccc183c82c12b6bf43159cb7b1f28b1f7f7ab` |
| `042 P2 Arm K` | `freeze/m3-bvh-042-p2-arm-k` | `b5b0df58bed75f3a259af8078630e1cb511ff769` | `cc78597b4b4c9e336e7082bcb2fd99ba9739ead2e01104c095f8046fe048baf7` |
| `043 P3 Lazy (Research Archive)` | `archive/m3-bvh-043-p3-lazy-research` | `ad93bc9d6` | `2f2d940dcfa1f16171642578b83c6ee5bac138eda563c2fd50aad7aaf5a97604` |
| `044 P4 Traversal + Cutoff` | `freeze/m3-bvh-044-p4-traversal` | *(HEAD on `codex/m3-bvh-p4-traversal-cutoff-044`)* | `7bfbd71982a7152cabf5cb04cf666fd8992bb016e6e09e01a6cd92a3c225b8d5` |

---

## 3. Exact Changed & Added File Manifest (`044-P4`)

- **Modified Runtime File** (`surface_geometry.py` untouched from `8d68d1a13`):
  - `human_eye_plugin/surface_proximity.py` (`8f7b08b6a5e5d9c5079470bd05e5c22d48b055f14cf49a93f8e5c845bb18af45`)
- **Allowlist & 044 Deliverables**:
  - `.gitignore`
  - `benchmarks/run_kernel_044_p4_traversal.py`
  - `benchmarks/test_kernel_044_p4_traversal.py`
  - `benchmarks/KERNEL_044_P4_RESULTS.json`
  - `benchmarks/KERNEL_044_P4_REVIEW.md`
  - `benchmarks/KERNEL_044_P4_HANDOFF.md`
- **Preserved Untouched**: `human_eye_plugin/surface_geometry.py`, `task_query.py`, `surface_scan.py`, `_bvh_median`, closed-solid callers, `benchmarks/verify_review_suite.py`, `benchmarks/bvh_eval.py`, and ALL `041`/`042` artifacts.

---

## 4. Reproducible Verification Commands

```powershell
e:\bvh\.venv\Scripts\python.exe -B benchmarks/bvh_eval.py --verify-comparator
e:\bvh\.venv\Scripts\python.exe -B -O benchmarks/bvh_eval.py --verify-comparator
e:\bvh\.venv\Scripts\python.exe -B benchmarks/verify_review_suite.py
e:\bvh\.venv\Scripts\python.exe -B -m unittest benchmarks/test_kernel_044_p4_traversal.py benchmarks/test_kernel_042_p2_prep.py benchmarks/test_kernel_042_p1_histogram.py benchmarks/test_kernel_042_build_pipeline.py benchmarks/test_kernel_041_r3_closure.py benchmarks/test_kernel_041_r3_c01_to_c06.py benchmarks/test_kernel_041_k01_to_k07.py -v
e:\bvh\.venv\Scripts\python.exe -B benchmarks/run_kernel_044_p4_traversal.py
```

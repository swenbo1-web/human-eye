# Kernel-042 Phase 1 Handoff (`KERNEL_042_P1_HANDOFF`)

> **Verdict**: `CANDIDATE_I_VALIDATED_P1_RESEARCH_ONLY`  
> **Research Branch**: `codex/m3-bvh-exact-build-pipeline-042`  
> **Frozen 041 Integration Reference (Untouched)**: `119327bbb4e645c5de3bfbc0d30259736b9a2677` (`source_sha256 = eff6511223646c125ac05cd6080d3bcbe191d1c945a8b3b7293d2c1bc0ff1ee4`)  
> **Phase-0 Arm F Baseline**: `5102f1fefc6ebee8b0ca5d7ad0c03530b672add4` (`source_sha256 = b0e4093dadf3eff8c9be18442922d802a4fa59adf2035f37958e8d5f32597dcd`)  
> **Promoted P1 Candidate Runtime Identity (`source_sha256`)**: `1db11b89a8513e571faf55fbd9bccc183c82c12b6bf43159cb7b1f28b1f7f7ab`

---

## 1. Handoff Summary & Scope Preservation

1. **Cumulative Exact Pipeline Gain (`119327bbb` -> `042-P1 Arm I`)**:
   - **Zero topology change**, **zero `work_units` change**, **zero public API / Hook / host change**.
   - 30-repeat paired median wall-time reductions vs frozen 041 (`119327bbb`): `HighRes_1536F_Pair` **`+15.62%`**, `Sheet_Dented_2mm` **`+15.97%`**, `Sheet_Parallel_5um` **`+14.46%`**, `Tube_Coiled_Loose` **`+11.69%`**, `Rotated_30deg_Spheres` **`+11.57%`**, `G508_Competing_001` **`+8.56%`**, `G508_Peer_000` **`+2.87%`**, `Assembly24_Obj014_23pairs` **`+6.12%`** (uncached), `D48_Real_47pairs` **`+4.83%`** (uncached).
2. **Untouched Production / Preserved Boundaries**:
   - `human_eye_plugin/surface_proximity.py` unchanged from `5102f1fef` (`c39d76d84075af92b373e5e76fdd31cfe7210fcfa147115e9af6bcde907a2143`).
   - `task_query.py`, `surface_scan.py`, closed-solid `_bvh_median`, host/Hook adapters, schemas, and all constants untouched.
   - All prior `KERNEL_042_{CASES,RESULTS,REVIEW,HANDOFF}*`, `KERNEL_041*`, and `KERNEL_041_R3*` deliverables preserved byte-for-byte.
   - Private fixtures `zero489`, `first_yield`, `pair129`, and original `040` closed-solid ordering remain `MISSING_HISTORICAL_INPUT`; `p95` metrics (`n=30`) are direct-kernel exploratory only.

---

## 2. Exact P1 Changed & Added File Manifest

- **Modified Runtime File**:
  - `human_eye_plugin/surface_geometry.py` (`84cb39427d78c4174868285019b3929f28a564c6287584d03336faa77175169e`)
- **Benchmark Allowlist**:
  - `.gitignore` (allowlists the 5 new `042-P1` files below)
- **Versioned P1 Deliverables**:
  - `benchmarks/run_kernel_042_p1_histogram.py`
  - `benchmarks/test_kernel_042_p1_histogram.py`
  - `benchmarks/KERNEL_042_P1_RESULTS.json`
  - `benchmarks/KERNEL_042_P1_REVIEW.md`
  - `benchmarks/KERNEL_042_P1_HANDOFF.md`

---

## 3. Reproducible Verification Commands

Run from `e:\bvh` on branch `codex/m3-bvh-exact-build-pipeline-042`:

```powershell
# 1. Verify comparator negative controls (normal & -O)
e:\bvh\.venv\Scripts\python.exe -B benchmarks/bvh_eval.py --verify-comparator
e:\bvh\.venv\Scripts\python.exe -B -O benchmarks/bvh_eval.py --verify-comparator

# 2. Verify frozen review suite preservation
e:\bvh\.venv\Scripts\python.exe -B benchmarks/verify_review_suite.py

# 3. Run P1 + Phase-0 + 041 regression suites (35 tests)
e:\bvh\.venv\Scripts\python.exe -B -m unittest benchmarks/test_kernel_042_p1_histogram.py benchmarks/test_kernel_042_build_pipeline.py benchmarks/test_kernel_041_r3_closure.py benchmarks/test_kernel_041_r3_c01_to_c06.py benchmarks/test_kernel_041_k01_to_k07.py -v

# 4. Reproduce full P1 screening + 30-repeat paired confirmation
e:\bvh\.venv\Scripts\python.exe -B benchmarks/run_kernel_042_p1_histogram.py
```

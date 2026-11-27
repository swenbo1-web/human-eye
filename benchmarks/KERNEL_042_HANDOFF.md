# Kernel-042 Exact Build-Pipeline Research Handoff (`KERNEL_042_HANDOFF`)

> **Verdict**: `CANDIDATE_F_VALIDATED_RESEARCH_ONLY`  
> **Research Branch**: `codex/m3-bvh-exact-build-pipeline-042`  
> **Frozen 041 Integration Reference (Preserved Untouched)**: `119327bbb4e645c5de3bfbc0d30259736b9a2677` (`source_sha256 = eff6511223646c125ac05cd6080d3bcbe191d1c945a8b3b7293d2c1bc0ff1ee4`)  
> **Research Candidate F Runtime Identity (`source_sha256`)**: `b0e4093dadf3eff8c9be18442922d802a4fa59adf2035f37958e8d5f32597dcd`

---

## 1. Handoff Status & Separation from 041

1. **Isolated Research Only**: Candidate F (`B1` fused node stats + `B2` exact division-free stable partition + `B4` native `_bvh_from_flat_bounds` direct feed) lives exclusively on `codex/m3-bvh-exact-build-pipeline-042`.
2. **Concurrent 041 Integration Unaffected**: The active 041 integration experiment on `119327bbb` (`eff65112...`) is NOT replaced or modified. No product installation, Hook dispatch edit, host adapter edit, or release bump was performed.
3. **Unchanged / Preserved Boundaries**:
   - Sibling runtime untouched: `human_eye_plugin/task_query.py`, `human_eye_plugin/surface_scan.py`, closed-solid `_bvh_median`, and all constants (`MAX_FACES=4096`, `MAX_WORK_UNITS=1179648`, `MAX_NARROW_PHASE_PAIRS=16384`, `LINEAR_PAIR_LIMIT=256`, closed-solid `262144`, `_SAH_BINS=12`, `_SAH_MIN_N=12`, `_SAH_MAX_DEPTH=20`).
   - All prior `KERNEL_041*`, `KERNEL_041_R3*`, `ALGORITHM_ABLATION.json`, `ASSET_MANIFEST.json`, `baseline_032.json`, `opt_bvh_final.json`, and historical artifacts preserved byte-for-byte.
4. **Known Research Gaps (`MISSING_HISTORICAL_INPUT`)**:
   - Private fixtures `zero489`, `first_yield`, `pair129`, and exact original `040` closed-solid 48F ordering remain `MISSING_HISTORICAL_INPUT` in the public repository and were not substituted.
   - `p95` metrics in `KERNEL_042_RESULTS.json` (`n=30`, linear interpolation) are **direct-kernel exploratory timing**, NOT host qualification `p95`.

---

## 2. Exact Changed & Added File Manifest (`codex/m3-bvh-exact-build-pipeline-042`)

- **Modified Runtime Sources** (`human_eye_plugin/`):
  - `human_eye_plugin/surface_geometry.py` (`5c116d6a1e6d48dec2f0b927769a6386c857d6a643725612167230f9ab86dc2c`)
  - `human_eye_plugin/surface_proximity.py` (`c39d76d84075af92b373e5e76fdd31cfe7210fcfa147115e9af6bcde907a2143`)
- **Benchmark Allowlist**:
  - `.gitignore` (allowlists the 6 new 042 deliverables below)
- **Versioned 042 Research Deliverables**:
  - `benchmarks/run_kernel_042_research.py`
  - `benchmarks/test_kernel_042_build_pipeline.py`
  - `benchmarks/KERNEL_042_CASES.json`
  - `benchmarks/KERNEL_042_RESULTS.json`
  - `benchmarks/KERNEL_042_REVIEW.md`
  - `benchmarks/KERNEL_042_HANDOFF.md`

---

## 3. Reproducible Direct-Kernel Verification Commands

Run from `e:\bvh` on branch `codex/m3-bvh-exact-build-pipeline-042`:

```powershell
# 1. Verify comparator negative controls (54 checks) under normal & -O modes
e:\bvh\.venv\Scripts\python.exe -B benchmarks/bvh_eval.py --verify-comparator
e:\bvh\.venv\Scripts\python.exe -B -O benchmarks/bvh_eval.py --verify-comparator

# 2. Run BVH-042 verification suite (auto-extracts frozen 119327bbb via git archive if needed) + 041 closure/regression suites
e:\bvh\.venv\Scripts\python.exe -B -m unittest benchmarks/test_kernel_042_build_pipeline.py benchmarks/test_kernel_041_r3_closure.py benchmarks/test_kernel_041_r3_c01_to_c06.py benchmarks/test_kernel_041_k01_to_k07.py -v

# 3. Verify frozen review suite preservation
e:\bvh\.venv\Scripts\python.exe -B benchmarks/verify_review_suite.py

# 4. Re-run isolated S0, paired A-F ablation, and 30-repeat confirmatory runner
e:\bvh\.venv\Scripts\python.exe -B benchmarks/run_kernel_042_research.py
```

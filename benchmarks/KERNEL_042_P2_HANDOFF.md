# Kernel-042 Phase 2 Handoff (`KERNEL_042_P2_HANDOFF`)

> **Verdict**: `CANDIDATE_K_VALIDATED_P2_RESEARCH_ONLY`  
> **Research Branch**: `codex/m3-bvh-exact-build-pipeline-042`  
> **Frozen 041 Integration Reference (Untouched)**: `119327bbb4e645c5de3bfbc0d30259736b9a2677` (`source_sha256 = eff6511223646c125ac05cd6080d3bcbe191d1c945a8b3b7293d2c1bc0ff1ee4`)  
> **Phase-0 Arm F**: `5102f1fefc6ebee8b0ca5d7ad0c03530b672add4` (`source_sha256 = b0e4093dadf3eff8c9be18442922d802a4fa59adf2035f37958e8d5f32597dcd`)  
> **Phase-1 Arm I**: `8d68d1a133cb2635920ddd83b8b7f12bdc6e3869` (`source_sha256 = 1db11b89a8513e571faf55fbd9bccc183c82c12b6bf43159cb7b1f28b1f7f7ab`)  
> **Promoted P2 Candidate Runtime Identity (`source_sha256`)**: `cc78597b4b4c9e336e7082bcb2fd99ba9739ead2e01104c095f8046fe048baf7`

---

## 1. Cumulative Research Gain & Preservation Boundaries

1. **Cumulative Exact Pipeline Gain (`119327bbb` -> `042-P2 Arm K`)**:
   - **Zero topology change**, **zero `work_units` change**, **zero Hook / host / schema change**.
   - 30-repeat paired median wall-time reductions vs frozen 041 (`119327bbb`): `Sheet_Dented_2mm` **`+21.93%`**, `HighRes_1536F_Pair` **`+19.53%`**, `Sheet_Parallel_5um` **`+19.10%`**, `Rotated_30deg_Spheres` **`+14.07%`**, `Tube_Coiled_Loose` **`+13.21%`**, `G508_Competing_001` **`+9.97%`**, `Sparse_100kV_Degenerate_MixedBit` **`+8.67%`**, `Assembly24_Obj014_23pairs` **`+7.08%`** (uncached), `G508_Peer_000` **`+4.54%`**, `D48_Real_47pairs` **`+1.03%`** (uncached) / **`+1.60%`** (cached).
2. **Preserved Boundaries**:
   - `human_eye_plugin/surface_geometry.py` untouched from `8d68d1a13` (`84cb39427d78c4174868285019b3929f28a564c6287584d03336faa77175169e`).
   - `task_query.py`, `surface_scan.py`, `_bvh_median`, host/Hook adapters, all `MAX_*` limits, and ALL prior `KERNEL_042*`, `KERNEL_042_P1*`, `KERNEL_041*`, `KERNEL_041_R3*` deliverables untouched byte-for-byte.
   - Private fixtures `zero489`, `first_yield`, `pair129`, and original `040` closed-solid ordering remain `MISSING_HISTORICAL_INPUT`; `p95` metrics (`n=30`) remain exploratory direct-kernel only.

---

## 2. Exact P2 Changed & Added File Manifest

- **Modified Runtime File**:
  - `human_eye_plugin/surface_proximity.py` (`7210292168449c2da2f2de731179bd464abde021ed84ea7f04b3a9daa8626a80`)
- **Benchmark Allowlist**:
  - `.gitignore` (allowlists the 5 new `042-P2` files below)
- **Versioned P2 Deliverables**:
  - `benchmarks/run_kernel_042_p2_prep.py`
  - `benchmarks/test_kernel_042_p2_prep.py`
  - `benchmarks/KERNEL_042_P2_RESULTS.json`
  - `benchmarks/KERNEL_042_P2_REVIEW.md`
  - `benchmarks/KERNEL_042_P2_HANDOFF.md`

---

## 3. Reproducible Verification Commands

Run from `e:\bvh` on branch `codex/m3-bvh-exact-build-pipeline-042`:

```powershell
# 1. Comparator negative controls (normal & -O)
e:\bvh\.venv\Scripts\python.exe -B benchmarks/bvh_eval.py --verify-comparator
e:\bvh\.venv\Scripts\python.exe -B -O benchmarks/bvh_eval.py --verify-comparator

# 2. Frozen review suite check
e:\bvh\.venv\Scripts\python.exe -B benchmarks/verify_review_suite.py

# 3. Full P2 + P1 + P0 + 041 regression suites (38 tests)
e:\bvh\.venv\Scripts\python.exe -B -m unittest benchmarks/test_kernel_042_p2_prep.py benchmarks/test_kernel_042_p1_histogram.py benchmarks/test_kernel_042_build_pipeline.py benchmarks/test_kernel_041_r3_closure.py benchmarks/test_kernel_041_r3_c01_to_c06.py benchmarks/test_kernel_041_k01_to_k07.py -v

# 4. Reproduce full P2 screening + 30-repeat paired confirmation
e:\bvh\.venv\Scripts\python.exe -B benchmarks/run_kernel_042_p2_prep.py
```

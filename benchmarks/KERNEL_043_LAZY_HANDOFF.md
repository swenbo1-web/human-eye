# Kernel-043 Phase 3 Handoff (`KERNEL_043_LAZY_HANDOFF`)

> **Verdict**: `CANDIDATE_043_LAZY_VALIDATED_RESEARCH_ONLY`  
> **Research Branch**: `codex/m3-bvh-lazy-sah-043`  
> **Branched From (`042-P2 Arm K`)**: `b5b0df58bed75f3a259af8078630e1cb511ff769` (`runtime_source_sha256 = cc78597b4b4c9e336e7082bcb2fd99ba9739ead2e01104c095f8046fe048baf7`)  
> **Frozen 041 Integration Reference (Untouched)**: `119327bbb4e645c5de3bfbc0d30259736b9a2677` (`runtime_source_sha256 = eff6511223646c125ac05cd6080d3bcbe191d1c945a8b3b7293d2c1bc0ff1ee4`)  
> **Candidate Runtime Identity (`P3_Lazy`)**: `runtime_source_sha256 = 2f2d940dcfa1f16171642578b83c6ee5bac138eda563c2fd50aad7aaf5a97604`

---

## 1. Summary & Promotion Guidance

- **Exactness & Regression Gate**:
  - `benchmarks/bvh_eval.py --verify-comparator`: **PASS (54/54, `alias_caught=true`)** in both normal and `-O` modes.
  - All `041` suites (`test_kernel_041_r3_closure.py`, `test_kernel_041_r3_c01_to_c06.py`, `test_kernel_041_k01_to_k07.py`) + `test_kernel_043_lazy_bvh.py`: all tests pass with `100%` `_surface_sig`, `_analyze_sig`, and `_closed_sig` equivalence, visited-subtree structural equality to `Arm A`, and **`0/33` holes** in C03 paid-dequeue sweeps (`[0..32]` across `tilted48`, `G508_Competing_001`, `sheet5um`).
- **Performance Summary (`30-repeat paired` vs `041 A` / `042-P2 K`)**:
  - **Strong Wins**: `Sheet_Dented_2mm` (`2.52x` vs A / `1.98x` vs K, `3.33%` tree built), `HighRes_1536F_Pair` (`2.30x` / `1.90x`, `3.82%`), `Sheet_Parallel_5um` (`2.19x` / `1.78x`, `6.07%`), `Tube_Coiled_Loose` (`1.52x` / `1.32x`, `17.40%`), `Rotated_30deg_Spheres` (`1.48x` / `1.30x`, `17.34%`), `G508_Competing_001` (`1.31x` / `1.18x`, `25.59%`), `Assembly24_Obj014_23pairs` (`1.21x` / `1.11x`).
  - **Known Tradeoff**: `G508_Peer_000` (`78.15%` expanded: `0.99x` vs A / `0.96x` vs K) and `D48_Real_47pairs` uncached (`0.98x` vs A / `0.96x` vs K). Recommended next research step (`P3.1`): adaptive lazy threshold / eager small-subtree fallback (`n <= 32`) on top of `codex/m3-bvh-lazy-sah-043`.
  - Keep `CANDIDATE_043_LAZY_VALIDATED_RESEARCH_ONLY` isolated on `codex/m3-bvh-lazy-sah-043`; do **not** merge into frozen `041` or `042-P2`.

---

## 2. Exact Changed & Added File Manifest

- **Modified Runtime Modules**:
  - `human_eye_plugin/surface_geometry.py` (`5d423f2298c40f6018c044ee11a480329002fe8dc0148c98298f5434c1d28470`)
  - `human_eye_plugin/surface_proximity.py` (`3cc88a633182649b01ee0c25c1fbc6ad45b3d6e9ad0f94eb2deace7b81b66c94`)
- **Allowlist & 043 Deliverables**:
  - `.gitignore`
  - `benchmarks/run_kernel_043_lazy_bvh.py`
  - `benchmarks/test_kernel_043_lazy_bvh.py`
  - `benchmarks/KERNEL_043_LAZY_RESULTS.json`
  - `benchmarks/KERNEL_043_LAZY_REVIEW.md`
  - `benchmarks/KERNEL_043_LAZY_HANDOFF.md`
- **Preserved Untouched**: `task_query.py`, `surface_scan.py`, `_bvh_median`, closed-solid callers, `_pair_from_mesh_cache`, `holder['trees']` raw ABI, all `MAX_*` constants, `benchmarks/verify_review_suite.py`, `benchmarks/bvh_eval.py`, and all `041` / `042` artifacts.

---

## 3. Reproducible Verification Commands

Run from `e:\bvh` on branch `codex/m3-bvh-lazy-sah-043`:

```powershell
# 1. Comparator negative controls (normal & -O)
e:\bvh\.venv\Scripts\python.exe -B benchmarks/bvh_eval.py --verify-comparator
e:\bvh\.venv\Scripts\python.exe -B -O benchmarks/bvh_eval.py --verify-comparator

# 2. P3 Lazy BVH suite (5 tests: structural parity, 3-mode + _FastWitnessProjection, C03 0-hole sweep, cancellation/ABI/solids, lazy+eager tight headroom deferral)
e:\bvh\.venv\Scripts\python.exe -B -m unittest benchmarks/test_kernel_043_lazy_bvh.py -v

# 3. P3 Lazy + full 041 regression suites (31 tests)
e:\bvh\.venv\Scripts\python.exe -B -m unittest benchmarks/test_kernel_043_lazy_bvh.py benchmarks/test_kernel_041_r3_closure.py benchmarks/test_kernel_041_r3_c01_to_c06.py benchmarks/test_kernel_041_k01_to_k07.py -v

# 4. Reproduce full P3 screening + 30-repeat paired confirmation
e:\bvh\.venv\Scripts\python.exe -B benchmarks/run_kernel_043_lazy_bvh.py
```

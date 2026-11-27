# Kernel-041 R3 Minimal Closure Handoff (`KERNEL_041_R3_CLOSURE_HANDOFF`)

> **Status**: `RESTRICTED_EXPERIMENT_ONLY`  
> **Branch**: `codex/m3-bvh-deep-optimization`  
> **Base R3 Commit Reviewed**: `7f907d05c53bb57cebbe037e540485e228240060`  
> **Runtime Source SHA-256 (`human_eye_plugin/surface_proximity.py` normalized)**: `eff6511223646c125ac05cd6080d3bcbe191d1c945a8b3b7293d2c1bc0ff1ee4`

---

## 1. Handoff Boundary & Restrictions

1. **Verdict**: `RESTRICTED_EXPERIMENT_ONLY`. All six independent R3 re-review items (`R3-F01`–`R3-F06`) are closed and verified within isolated direct-kernel / verifier scope.
2. **Untouched Production / Preserved Boundaries**:
   - Sibling modules untouched: `human_eye_plugin/task_query.py`, `human_eye_plugin/surface_scan.py`, `human_eye_plugin/surface_geometry.py`.
   - All budget constants untouched: `MAX_FACES=4096`, `MAX_WORK_UNITS=1179648`, `MAX_NARROW_PHASE_PAIRS=16384`, `LINEAR_PAIR_LIMIT=256`, closed-solid `262144`.
   - Earlier `KERNEL_041*`, `KERNEL_041_R3_*`, `ALGORITHM_ABLATION.json`, `ASSET_MANIFEST.json`, `baseline_032.json`, `opt_bvh_final.json`, `CORRECTNESS_AND_BOUNDARY_RESULTS.json`, `REVIEW_FIXES.md`, and `ALGORITHM_REVIEW_RESULT.md` preserved byte-for-byte.
3. **Open Experiment Limits (Do Not Overclaim)**:
   - Historical fixtures (`zero489`, `first_yield`, `pair129`, original `040` 48F ordering) remain `MISSING_HISTORICAL_INPUT`.
   - Option A (`settled_credit_031_ref`) matches executed `off_paid_dequeue_ref` (`M_paid_ref`) with **0 holes** (`tilted48`, 5-epoch `G508_Competing_001`, `sheet5um`), while injected in-admission failures still exhibit documented deltas against `M_off`.
   - `live_box_only = NOT_EXERCISED` on `tilted48` and `G508_Peer_000`; box AABB pruning safety rests on synthetic controls and unit tests (`synthetic_box_control = PASS`).
   - Host/caller qualification (`task_query.py`, Blender/MCP adapters, full C02 single-variable ablation, or multi-seed p95 qualification) remains out-of-scope of this closure and must be owned before production promotion.

---

## 2. Modified & Added Deliverable Paths (`KERNEL_041_R3_CLOSURE_*`)

- **Runtime Kernel**:
  - `human_eye_plugin/surface_proximity.py` (`a366cb104537ede9472a312f8e87ac446c7f3d27d5aa484d0e6f4f7eaff0093f`)
- **Verifier & Benchmark Harnesses**:
  - `benchmarks/bvh_eval.py` (`db9cde085c7accb5a626ccc4a4cea0ae5f280ab82a1bff80252dce061d15d0b3`)
  - `benchmarks/run_ablation_and_assets.py` (`12359a4f9a2fe0a23b0794f0cd9c776db811c85e0890d38c44bed927aa3b7f75`)
  - `benchmarks/run_r3_closure_eval.py` (`99fceaae11cd9383797167d299c73a24bd87bb75c73825d2d8607e2c44c0066b`)
  - `.gitignore` (allowlists `test_kernel_041_r3_closure.py` and `KERNEL_041_R3_CLOSURE_*`)
- **Unit Tests**:
  - `benchmarks/test_kernel_041_r3_c01_to_c06.py` (`3c14045c8546eabd7305d2a5eedf56f8a93fa76464be1f77ad37714d103143d3`)
  - `benchmarks/test_kernel_041_r3_closure.py` (`80bf3c1b4c358a2e0d434bb1b71b867b20d5cd0a1cdebdd94496f64bfdb6381a`)
- **Versioned R3 Closure Deliverables**:
  - `benchmarks/KERNEL_041_R3_CLOSURE_CASES.json`
  - `benchmarks/KERNEL_041_R3_CLOSURE_RESULTS.json`
  - `benchmarks/KERNEL_041_R3_CLOSURE_REVIEW.md`
  - `benchmarks/KERNEL_041_R3_CLOSURE_HANDOFF.md`

---

## 3. Pinned Runtime Identity Digests

| Arm / Revision | Runtime Source SHA-256 (`runtime_source_sha256`) |
| --- | --- |
| Historical `032` (`6c93f2375d1073b33e721a168f1fcf610ac6dbdc`) | `0f9e6336ec54adf9e7b9a5379b02d2c2cab9f6d1f734138c3fde29e08ccee241` |
| Prior `R2` (`b7d469d390abdeac93dfacfcce0dc385eae2f341`) | `e35b7e16c11ff8360bdcf2e5340019a9fc37ba11ad2bb09864989a28d6525414` |
| **Current `R3 Closure` (`R3_default` & `R3_off`)** | **`eff6511223646c125ac05cd6080d3bcbe191d1c945a8b3b7293d2c1bc0ff1ee4`** |

---

## 4. Exact Reproducible Verification Commands

Run from `e:\bvh`:

```powershell
# 1. Verify comparator negative controls (54 checks) under both normal & -O modes
e:\bvh\.venv\Scripts\python.exe -B benchmarks/bvh_eval.py --verify-comparator
e:\bvh\.venv\Scripts\python.exe -B -O benchmarks/bvh_eval.py --verify-comparator

# 2. Run F01-F06, R3 C01-C06, and K01-K07 unit suites
e:\bvh\.venv\Scripts\python.exe -B -m unittest benchmarks/test_kernel_041_r3_closure.py benchmarks/test_kernel_041_r3_c01_to_c06.py benchmarks/test_kernel_041_k01_to_k07.py -v

# 3. Run full review verification suite (preserves frozen artifacts)
e:\bvh\.venv\Scripts\python.exe -B benchmarks/verify_review_suite.py

# 4. Regenerate pinned R3 closure deliverables in isolated worker subprocesses
e:\bvh\.venv\Scripts\python.exe -B benchmarks/run_r3_closure_eval.py --output-prefix KERNEL_041_R3_CLOSURE
```

# M3 BVH Kernel 041 R3 Handoff Manifest

## 1. Handoff Status

**`RESTRICTED_EXPERIMENT_ONLY`**

All R3 kernel closure items (**C01–C06**) pass local isolated direct-kernel verification with clean subprocess arm separation (`032`, `b7d469d`, `R3_default`, `R3_off`) and exact cross-arm semantic parity. The candidate stays `RESTRICTED_EXPERIMENT_ONLY` (not unconditional `READY_FOR_COMMIT` / product integration) because:

1. **Private Historical Inputs Open (`MISSING_HISTORICAL_INPUT`)**: Raw fixtures `zero489`, `first_yield`, `pair129`, and exact `040` 48F triangle ordering (`[27, 1]`) are absent from the public repository.
2. **C03 Option A Reference Boundary (`settled_credit_031_ref` vs `off`)**: Default fast witness projection operates with explicit `mandatory_031_dequeue_aabb` reference (`0` holes on `[M_ref_031, M_ref_031+32]` across all normal and failure-injected sweeps; `0` holes on normal `[M_off, M_off+32]`). Under injected failed proofs (`ON_fail_dir`, `ON_fail_slab`) relative to same-revision `OFF` (`M_off`), `tilted48` exhibits 8 and 33 holes respectively because `OFF` also skips dequeue AABB charges. Callers needing zero speculative budget overhead can select `_projection_mode='off'` before execution (`0` holes everywhere; fallback cost disclosed: `G508_Peer_000` `489,205` wu / `1.57 s` vs `61,740` wu / `125.3 ms`).
3. **Host / Caller Sealing Boundary**: Live caller modules (`task_query.py`, `surface_scan.py`) were not modified per R3 scope rules. All ndarray-backed inputs fail closed in `_mesh_cache` (`mesh_cache_hits = 0`) and run safely on the indexed uncached exact fallback.

---

## 2. Candidate Identity & File Manifest

- **Branch**: `codex/m3-bvh-deep-optimization`
- **Superseded R2 Head**: `b7d469d390abdeac93dfacfcce0dc385eae2f341`
- **Accepted Historical Reference (`032`)**: `6c93f2375d1073b33e721a168f1fcf610ac6dbdc`
- **R3 Runtime Source SHA-256**: `84a2f68210631ba1b1b8e2059db6d98fd06e50570f6a9d85dc9ecbe5fd75edc0`

| File | Role |
|---|---|
| [human_eye_plugin/surface_proximity.py](file:///e:/bvh/human_eye_plugin/surface_proximity.py) | C01 ndarray cache rejection (deep tuples + strong `verts_ref` only); C02 O(1) `_cold_interval_upper` (`0` / `1+3n` / `5n-1`) & single-pass `prunes_nodes`; C03 `_projection_mode` (`settled_credit_031_ref` / `off`); C06 `_Work` dict clear & 5 preparation/compile checkpoints |
| [benchmarks/bvh_eval.py](file:///e:/bvh/benchmarks/bvh_eval.py) | C04 `m3-bvh-eval-v4`, lowercase 64-hex SHA enforcement, `options_sha256` recomputation, `inputs_sha256` mandatory, per-arm `runtime_identity_sha256` pinning, `_analyze_sig` fail-closed `pair_accounting_complete`, at-return `_time_fn` snapshots, R2/R3 `_work_summary` fields, 41 negative controls (explicit `RuntimeError`, survives `-O`) |
| [benchmarks/run_ablation_and_assets.py](file:///e:/bvh/benchmarks/run_ablation_and_assets.py) | C04 `__file__` origin verification per loaded arm + at-return deep-copied signature verification in `_time_interleaved` |
| [benchmarks/test_kernel_041_k01_to_k07.py](file:///e:/bvh/benchmarks/test_kernel_041_k01_to_k07.py) | Updated 2 R2-superseded assertions (`TestK03` owned read-only ndarray expects `mesh_cache_hits == 0`; `TestK07` accepts `(AssertionError, RuntimeError)`) |
| [benchmarks/test_kernel_041_r3_c01_to_c06.py](file:///e:/bvh/benchmarks/test_kernel_041_r3_c01_to_c06.py) | Self-contained R3 C01–C06 regression, certificate, budget-sweep, and instrumentation suite |
| [benchmarks/run_r3_closure_eval.py](file:///e:/bvh/benchmarks/run_r3_closure_eval.py) | Clean serial subprocess 4-arm smoke & R3 audit deliverable generator |

R3 Versioned Evidence Artifacts (all prior `KERNEL_041_*` and historical artifacts preserved byte-for-byte):
- [benchmarks/KERNEL_041_R3_CASES.json](file:///e:/bvh/benchmarks/KERNEL_041_R3_CASES.json)
- [benchmarks/KERNEL_041_R3_RESULTS.json](file:///e:/bvh/benchmarks/KERNEL_041_R3_RESULTS.json)
- [benchmarks/KERNEL_041_R3_REVIEW.md](file:///e:/bvh/benchmarks/KERNEL_041_R3_REVIEW.md)
- [benchmarks/KERNEL_041_R3_HANDOFF.md](file:///e:/bvh/benchmarks/KERNEL_041_R3_HANDOFF.md)

---

## 3. Reproducible R3 Verification Commands

```powershell
e:\bvh\.venv\Scripts\python.exe -B benchmarks/bvh_eval.py --verify-comparator
e:\bvh\.venv\Scripts\python.exe -B -O benchmarks/bvh_eval.py --verify-comparator
e:\bvh\.venv\Scripts\python.exe -B -m unittest benchmarks/test_kernel_041_r3_c01_to_c06.py benchmarks/test_kernel_041_k01_to_k07.py -v
e:\bvh\.venv\Scripts\python.exe -B benchmarks/verify_review_suite.py
```

- All checks above executed cleanly on final code: 41/41 comparator controls (normal & `-O`), 22/22 unit tests (`11` R3 + `11` K01–K07), 7/7 review sections, 4/4 isolated worker subprocesses verified.
- Remaining work on experiment branch: replay private `032` archive fixtures (`zero489`, `first_yield`, `pair129`, original `040` 48F ordering), verify caller-owned deep tuple snapshot creation if live caching is desired in `task_query.py`/`surface_scan.py`, and decide product default (`settled_credit_031_ref` vs `off`).

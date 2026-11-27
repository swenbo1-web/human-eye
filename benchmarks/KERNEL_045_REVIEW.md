# M3 BVH 045 Exact Pre-Tree Cross-Pair Separation Review

- **Source Branch**: `codex/m3-bvh-exact-batch-preproof-045` (atop frozen `freeze/m3-bvh-044-r1` `f4d7b762f555bafa1e7585dd43e95a45f6004c33`)
- **Runtime Identity (`runtime_source_sha256`)**: `1d13c3a67986954f8940f3770dff7b11fe92fb708b18611b73e2074c109f527f`
- **Modified/Added Runtime Files**:
  - Added [`human_eye_plugin/surface_batch_preproof.py`](file:///e:/bvh/human_eye_plugin/surface_batch_preproof.py)
  - Minimal wiring in [`human_eye_plugin/surface_proximity.py`](file:///e:/bvh/human_eye_plugin/surface_proximity.py) (`surface_proximity_sha256 = f10b6debaa9d7f7cc811cdd6c1b9b3560fc4e3adbf3e574376dd69ed5e81235c`; ordinary `measure_surface_proximity` untouched and 100% parity-identical vs Arm `K`; [`human_eye_plugin/surface_geometry.py`](file:///e:/bvh/human_eye_plugin/surface_geometry.py) untouched `84cb39427d78c4174868285019b3929f28a564c6287584d03336faa77175169e`).
- **Manifest (`manifest_sha256`)**: `42ecf4ebc70b1df5b9cf435268b38587054d85691bab7b5868d670fe409bb97c` in [KERNEL_045_CASES.json](file:///e:/bvh/benchmarks/KERNEL_045_CASES.json)
- **Full Results JSON**: [KERNEL_045_RESULTS.json](file:///e:/bvh/benchmarks/KERNEL_045_RESULTS.json)

## 1. Verdict & Architecture Decision

- **`verdict_045`**: **`PRETREE_CANDIDATE_RESEARCH_ONLY`**
- **Selected Fixed Candidate from Stage 1 Screening (7 repeats)**: **`B3_TARGET_MEMO_AXIS`** (`b4_better_cnt = 0` vs threshold `>= 2`; single-epoch target interval memo captures virtually all gains of multi-axis `B4` without testing extra fallback axes).
- **Qualified Real Scene Families (`>= 10%` and `>= 21/30` faster vs frozen `044-R1` `CUTOFF_SETTLED_PROJECTION`)**: All 4 families (`D48_Real_47pairs`, `Assembly24_Obj014_23pairs`, `G508_Retained_11pairs`, `G60_D12_Retained_11pairs`) won **`30/30`** on cached stable runs (`29–30/30` across uncached, ndarray, and `referenced_aabb` variants), with **`guard_regressions = []`**.
- **§10 `046` Conditional Gate (`residual_build_pct > 25%` on `>= 2` meaningful families)**: **`gate_046_met_cached = false`** (`[]`), **`gate_046_met_uncached = false`** (`["Assembly24_Obj014_23pairs"]`). With `045` eliminating `68%–96%` of peer BVH builds up front, residual time is search/traversal-dominated rather than BVH build-dominated; `046` (adaptive eager/lazy build) should NOT be initiated automatically.

## 2. Exact Confirmation Performance & Structural Tree-Build Avoidance (30 Repeats)

*Incremental improvements vs frozen `044-R1` and cumulative reductions vs `EXHAUSTIVE` are reported separately (never multiplied).*

| Workload & Variant | `EXH` Median (ms) | `044-R1` `SETTLED` (ms) | `045` `B3` (ms) | Incremental `045` vs `044-R1` | Faster Slots | Cumulative `045` vs `EXH` | Trees Built (`044-R1` -> `045`) | Pre-Tree Proof Breakdown (`aabb` / `axis` / `trav`) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `D48_Real_47pairs` (`tuple_cached_stable`) | `772.47` | `223.79` | **`26.76`** | **`+88.2%`** | `30/30` | `+96.5%` | `47 -> 2 / 47` | `0` / `45` / `0` (`45` memo hits) |
| `D48_Real_47pairs` (`tuple_uncached_stable`) | `786.59` | `254.82` | **`27.20`** | **`+89.4%`** | `30/30` | `+96.5%` | `47 -> 2 / 47` | `0` / `45` / `0` |
| `D48_Real_47pairs` (`ndarray_cached_stable`) | `728.51` | `221.19` | **`26.95`** | **`+87.8%`** | `30/30` | `+96.3%` | `47 -> 2 / 47` | `0` / `45` / `0` |
| `D48_Real_47pairs` (`tuple_cached_ref_aabb`) | `744.03` | `217.92` | **`26.57`** | **`+87.8%`** | `30/30` | `+96.4%` | `47 -> 2 / 47` | `0` / `45` / `0` |
| `Assembly24_Obj014_23pairs` (`tuple_cached_stable`) | `92.03` | `42.66` | **`22.29`** | **`+48.1%`** | `30/30` | `+75.9%` | `22 -> 7 / 23` | `16` / `0` / `5` (`5` memo hits) |
| `Assembly24_Obj014_23pairs` (`tuple_uncached_stable`) | `118.21` | `41.83` | **`28.62`** | **`+31.8%`** | `30/30` | `+75.8%` | `7 -> 7 / 23` | `16` / `0` / `5` |
| `Assembly24_Obj014_23pairs` (`ndarray_cached_stable`) | `92.39` | `42.65` | **`22.38`** | **`+47.9%`** | `29/30` | `+75.9%` | `22 -> 7 / 23` | `16` / `0` / `5` |
| `Assembly24_Obj014_23pairs` (`tuple_cached_ref_aabb`) | `91.73` | `45.43` | **`24.67`** | **`+46.0%`** | `29/30` | `+73.2%` | `22 -> 6 / 23` | `17` / `0` / `1` |
| `G508_Retained_11pairs` (`tuple_cached_stable`) | `578.40` | `237.43` | **`112.66`** | **`+52.6%`** | `30/30` | `+80.3%` | `11 -> 1 / 11` | `0` / `10` / `0` (`9` memo hits) |
| `G508_Retained_11pairs` (`tuple_uncached_stable`) | `689.72` | `350.20` | **`108.42`** | **`+69.0%`** | `30/30` | `+84.1%` | `11 -> 1 / 11` | `0` / `10` / `0` |
| `G60_D12_Retained_11pairs` (`tuple_cached_stable`) | `168.03` | `71.91` | **`25.29`** | **`+64.8%`** | `30/30` | `+84.7%` | `11 -> 2 / 11` | `0` / `9` / `0` (`9` memo hits) |
| `G60_D12_Retained_11pairs` (`tuple_uncached_stable`) | `166.86` | `73.31` | **`23.98`** | **`+67.8%`** | `30/30` | `+85.8%` | `11 -> 2 / 11` | `0` / `9` / `0` |
| `SmallBatch_12F_Linear_10pairs` (Guard) | `38.96` | `7.64` | **`5.02`** | **`+33.6%`** | `30/30` | `+86.8%` | `0 -> 0 / 10` | `9` / `0` / `0` |
| `HighOverlap_Interleaved_16pairs` (Adversarial) | `19.56` | `8.46` | **`8.90`** | `-5.5%` (`+0.44ms`) | `3/30` | `+54.8%` | `0 -> 0 / 16` | `0` / `0` / `15` (within `<1ms` guard) |
| `TiedContact_12pairs` (Tie Guard) | `6.38` | `5.62` | **`5.92`** | `-6.2%` (`+0.30ms`) | `4/30` | `+6.1%` | `0 -> 0 / 14` | `2` / `0` / `0` (within `<1ms` guard) |

## 3. Independent Subprocess OS Memory Probes (Clean Child Processes)

| Workload | `EXHAUSTIVE` Peak WS / `tracemalloc` | `044-R1` Peak WS / `tracemalloc` | `045 B3` Peak WS / `tracemalloc` |
| :--- | :--- | :--- | :--- |
| `D48_Real_47pairs` | `104.23 MiB` / `7985.4 KB` | `103.64 MiB` / `7856.2 KB` | **`104.34 MiB` / `1240.4 KB`** (`-84.2%` Python heap) |
| `G508_Retained_11pairs` | `103.36 MiB` / `4995.5 KB` | `104.26 MiB` / `4978.4 KB` | `104.12 MiB` / `4956.8 KB` |
| `HighOverlap_Interleaved_16pairs` | — | `103.69 MiB` / `408.7 KB` | `104.23 MiB` / `415.3 KB` |

## 4. Residual Build-Cost Profile (§10 Gate Check for `046`)

| Workload (under `045 B3`) | Mode | Total (ms) | `build_sah` (ms) | `residual_build_pct` | `build_all` (`+compile/trans`) | `prep+build` | `search_tree` (ms) | `preproof` (ms) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `D48_Real_47pairs` | `cached` | `27.82` | `2.35` | **`8.4%`** | `9.5%` | `12.7%` | `15.09` | `1.30` |
| `D48_Real_47pairs` | `uncached` | `26.67` | `2.89` | **`10.8%`** | `11.6%` | `15.6%` | `14.61` | `1.25` |
| `Assembly24_Obj014_23pairs` | `cached` | `22.87` | `2.82` | **`12.3%`** | `18.6%` | `35.5%` | `10.32` | `0.26` |
| `Assembly24_Obj014_23pairs` | `uncached` | `28.95` | `10.17` | `35.1%` | `38.1%` | `50.3%` | `10.28` | `0.25` |
| `G508_Retained_11pairs` | `cached` | `113.34` | `17.43` | **`15.4%`** | `16.5%` | `19.7%` | `81.19` | `0.46` |
| `G508_Retained_11pairs` | `uncached` | `119.79` | `20.17` | **`16.8%`** | `17.7%` | `22.4%` | `88.91` | `0.51` |
| `G60_D12_Retained_11pairs` | `cached` | `23.95` | `2.51` | **`10.5%`** | `12.0%` | `16.2%` | `16.37` | `0.35` |
| `G60_D12_Retained_11pairs` | `uncached` | `23.28` | `3.02` | **`13.0%`** | `13.9%` | `18.8%` | `15.70` | `0.34` |
| `HighOverlap_Interleaved_16pairs` | `cached` | `8.47` | `0.00` | `0.0%` | `0.0%` | `27.0%` | `0.00` | `0.25` |

## 5. Verification Ledger & Historical Provenance

- [`test_kernel_045_preproof.py`](file:///e:/bvh/benchmarks/test_kernel_045_preproof.py) under `-O` (`6/6 OK`) & normal mode + full historical regression (`044-R1`, `042-P2`, `041-R3`, `041-K01..K07`): **`32/32 OK`** (`138.923s`).
- Hardened receipt comparator (`validate_045_batch_receipt_comparison`, zero bare `assert`s) verified all 4 real scenes and guard variants across Screening + Confirmation, verifying `D_true > bound >= final_incumbent`, `tree_builds == 0`, `prepared_triangles == 0`, and independent `Fraction.from_float` raw-vertex intervals.
- Private historical fixtures (`zero489`, `first_yield`, `pair129`, `040_closed_solid`, `B02_10_retained_subset`) remain explicitly `MISSING_HISTORICAL_INPUT`.

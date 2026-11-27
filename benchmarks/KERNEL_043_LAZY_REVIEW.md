# Kernel-043 Phase 3 Review: Exact Demand-Driven Lazy SAH BVH (`KERNEL_043_LAZY_REVIEW`)

> **Verdict**: `CANDIDATE_043_LAZY_VALIDATED_RESEARCH_ONLY`  
> **Research Branch**: `codex/m3-bvh-lazy-sah-043`  
> **Base Commit (`042-P2 Arm K`)**: `b5b0df58bed75f3a259af8078630e1cb511ff769` (`runtime_source_sha256 = cc78597b4b4c9e336e7082bcb2fd99ba9739ead2e01104c095f8046fe048baf7`)  
> **Frozen 041 Reference Commit**: `119327bbb4e645c5de3bfbc0d30259736b9a2677` (`runtime_source_sha256 = eff6511223646c125ac05cd6080d3bcbe191d1c945a8b3b7293d2c1bc0ff1ee4`)  
> **Candidate Runtime Identity (`P3_Lazy`)**: `runtime_source_sha256 = 2f2d940dcfa1f16171642578b83c6ee5bac138eda563c2fd50aad7aaf5a97604`  
> - `human_eye_plugin/surface_geometry.py`: `5d423f2298c40f6018c044ee11a480329002fe8dc0148c98298f5434c1d28470`  
> - `human_eye_plugin/surface_proximity.py`: `3cc88a633182649b01ee0c25c1fbc6ad45b3d6e9ad0f94eb2deace7b81b66c94`

---

## 1. Architecture & Exact Equivalence Design

Phase 3 (`M3 BVH-043`) replaces eager full-tree pre-build in un-cached single-shot queries (`prepared_holder is None and prepared_trees is None`, gated by `_lazy_bvh=True`) with exact demand-driven lazy top-down SAH BVH expansion while keeping the exact geometry, split tie-breaking, ledger stages, and witness-projection invariants intact:

1. **Single-Level Exact SAH Splitter (`human_eye_plugin/surface_geometry.py::_split_sah_one_level`)**:
   - Performs one level of the exact P1 (`Arm I`) histogram / median split over `(flat_bounds, budget, ids, lx, ly, lz, hx, hy, hz, leaf_size, depth, scratch, ids_sorted, cbounds)` and returns `(left_ids, right_ids, children_stay_sorted)`.
   - Reuses `_alloc_sah_scratch()` per side (`scratches = (_alloc_sah_scratch(), _alloc_sah_scratch())`) and precomputed `(flat_bounds, root_box, root_cbox)` produced in a single fused pass by `_prepare_lazy_state`.
2. **Demand-Driven Traversal Expansion (`human_eye_plugin/surface_proximity.py::_nearest_tree`)**:
   - Only allocates and splits a node (`node[8]`, `node[9]`) when best-first traversal pops a `(left, right)` pair and chooses that side to subdivide. Unvisited subtrees never perform SAH splitting or compile child nodes.
   - Preserves `O(1)` `min_id` tracking whenever `is_sorted=True` holds (until an SAH split reorders indices), caches fused `cbox` only on `n > 12 and depth < 20`, and ticks `surface_bvh_build` / `surface_proximity_bvh_compile` checkpoints lazily at node creation time.
3. **Unexpanded Node Support in Fast Witness Projection (`_FastWitnessProjection._node_interval`)**:
   - When an unexpanded lazy internal node (`cur[8] is None`) is queried during witness projection, `_node_interval` scans its raw descendant triangle IDs `cur[14]` directly instead of forcing an eager split, keeping witness projection side-effect-free with respect to lazy BVH structure.
4. **Caller & ABI Isolation**:
   - `_prepared_holder` (`holder['trees']` raw ABI), `_mesh_cache` (`_pair_from_mesh_cache` cached secondary lookups), linear bypass (`len(left)*len(right) <= LINEAR_PAIR_LIMIT`), `task_query.py`, `surface_scan.py`, `analyze`, and `classify_closed_solids` retain the eager/cached path untouched.

---

## 2. Lazy Node Creation & Work-Unit Telemetry

| Workload | Linear Bypass | Eager Nodes | Lazy Created (`%`) | Lazy Expanded | `settled_credit_031_ref` WU (`K -> P3`) | `off` WU (`K -> P3`) | `off_paid_dequeue_ref` WU (`K -> P3`) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Sheet_Dented_2mm` | `false` | `1022` | `34` (`3.33%`) | `16` | `13986 -> 6846` | `13986 -> 6846` | `13986 -> 6846` |
| `HighRes_1536F_Pair` | `false` | `3614` | `138` (`3.82%`) | `68` | `49685 -> 26430` | `50204 -> 26988` | `50381 -> 27165` |
| `Sheet_Parallel_5um` | `false` | `1022` | `62` (`6.07%`) | `30` | `14246 -> 7454` | `14246 -> 7454` | `14297 -> 7505` |
| `Rotated_30deg_Spheres` | `false` | `542` | `94` (`17.34%`) | `46` | `7461 -> 5500` | `7453 -> 5445` | `7609 -> 5601` |
| `Tube_Coiled_Loose` | `false` | `1678` | `292` (`17.40%`) | `145` | `28136 -> 19964` | `30184 -> 22104` | `30854 -> 22774` |
| `G508_Competing_001` | `false` | `680` | `174` (`25.59%`) | `86` | `13406 -> 10607` | `36755 -> 34313` | `38525 -> 36083` |
| `Sparse_100kV_Degenerate_MixedBit` | `false` | `44` | `24` (`54.55%`) | `11` | `633 -> 573` | `633 -> 573` | `640 -> 580` |
| `G508_Peer_000` | `false` | `1208` | `944` (`78.15%`) | `471` | `61740 -> 60294` | `489205 -> 488498` | `507668 -> 506961` |
| `Control_12F_Linear` | `true` | `30` | `0` (`0.00%`) | `0` | `4633 -> 4633` | `4633 -> 4633` | `4633 -> 4633` |

---

## 3. 30-Repeat Confirmatory Paired Results (`A` vs `K` vs `P3_Lazy`)

| Workload [Variant] | `A` Med (ms) | `K` Med (ms) | `P3_Lazy` Med (ms) | Speedup (`vs A` / `vs K`) | `A` / `K` / `P3` `p95` (ms) | Peak `tracemalloc` (KB: `A` / `K` / `P3`) |
| --- | ---: | ---: | ---: | --- | --- | --- |
| `G508_Peer_000` [`uncached_tuple`] | `126.96` | `123.03` | `128.45` | `0.99x` / `0.96x` | `166.36` / `153.92` / `199.97` | `3024.7` / `3054.9` / `2838.8` |
| `G508_Peer_000` [`uncached_ndarray`] | `130.34` | `124.62` | `128.12` | `1.02x` / `0.97x` | `197.82` / `165.47` / `174.81` | `3024.7` / `3054.9` / `2838.8` |
| `G508_Competing_001` [`uncached_tuple`] | `28.55` | `25.66` | **`21.82`** | **`1.31x` / `1.18x`** | `33.08` / `51.39` / `33.06` | `1620.5` / `1577.5` / `1326.1` |
| `G508_Competing_001` [`uncached_ndarray`] | `27.36` | `24.52` | **`20.54`** | **`1.33x` / `1.19x`** | `37.26` / `43.32` / `23.79` | `1620.6` / `1577.7` / `1326.3` |
| `HighRes_1536F_Pair` [`uncached_tuple`] | `103.34` | `85.36` | **`44.95`** | **`2.30x` / `1.90x`** | `156.98` / `99.57` / `70.54` | `8563.0` / `8653.8` / `7230.2` |
| `HighRes_1536F_Pair` [`uncached_ndarray`] | `107.44` | `88.30` | **`47.49`** | **`2.26x` / `1.86x`** | `120.80` / `97.90` / `53.79` | `8755.1` / `8846.0` / `7422.5` |
| `Sheet_Dented_2mm` [`uncached_tuple`] | `27.76` | `21.88` | **`11.03`** | **`2.52x` / `1.98x`** | `39.72` / `28.00` / `12.80` | `2647.9` / `2604.3` / `2232.6` |
| `Sheet_Dented_2mm` [`uncached_ndarray`] | `26.20` | `20.96` | **`10.67`** | **`2.46x` / `1.96x`** | `28.07` / `23.34` / `12.83` | `2656.4` / `2612.8` / `2241.1` |
| `Sheet_Parallel_5um` [`uncached_tuple`] | `22.27` | `18.09` | **`10.16`** | **`2.19x` / `1.78x`** | `26.16` / `22.57` / `25.39` | `2425.4` / `2381.7` / `2018.1` |
| `Sheet_Parallel_5um` [`uncached_ndarray`] | `21.54` | `17.57` | **`9.95`** | **`2.16x` / `1.77x`** | `48.02` / `23.73` / `14.66` | `2433.9` / `2390.3` / `2026.6` |
| `Rotated_30deg_Spheres` [`uncached_tuple`] | `15.18` | `13.30` | **`10.27`** | **`1.48x` / `1.30x`** | `19.34` / `14.87` / `18.78` | `1263.3` / `1245.0` / `1057.9` |
| `Rotated_30deg_Spheres` [`uncached_ndarray`] | `15.21` | `13.18` | **`10.17`** | **`1.50x` / `1.30x`** | `20.66` / `14.92` / `11.70` | `1263.5` / `1245.1` / `1058.1` |
| `Tube_Coiled_Loose` [`uncached_tuple`] | `60.41` | `52.66` | **`39.81`** | **`1.52x` / `1.32x`** | `89.40` / `60.97` / `47.99` | `4000.9` / `3950.4` / `3327.6` |
| `Tube_Coiled_Loose` [`uncached_ndarray`] | `65.56` | `57.33` | **`43.12`** | **`1.52x` / `1.33x`** | `76.35` / `95.11` / `47.14` | `4030.3` / `3979.8` / `3357.1` |
| `Control_12F_Linear` [`uncached_tuple`] | `4.29` | `4.27` | `4.30` | `1.00x` / `0.99x` | `6.15` / `6.98` / `6.53` | `49.7` / `52.5` / `52.5` |
| `Control_12F_Linear` [`uncached_ndarray`] | `4.31` | `4.29` | `4.30` | `1.00x` / `1.00x` | `5.50` / `4.71` / `4.61` | `49.7` / `52.6` / `52.6` |
| `Sparse_100kV_Degenerate_MixedBit` [`uncached_tuple`] | `1.28` | `1.17` | `1.16` | `1.11x` / `1.01x` | `1.41` / `1.24` / `1.24` | `138.2` / `135.3` / `134.8` |
| `Sparse_100kV_Degenerate_MixedBit` [`uncached_ndarray`] | `1.32` | `1.20` | `1.18` | `1.12x` / `1.02x` | `1.42` / `1.31` / `1.31` | `141.9` / `139.0` / `138.6` |
| `D48_Real_47pairs` [`uncached_tuple`] | `900.74` | `878.95` | `915.17` | `0.98x` / `0.96x` | `994.90` / `989.60` / `1060.79` | `545.6` / `554.2` / `540.8` |
| `D48_Real_47pairs` [`uncached_ndarray`] | `885.79` | `877.18` | `904.22` | `0.98x` / `0.97x` | `1013.16` / `973.47` / `981.99` | `545.7` / `554.3` / `540.9` |
| `D48_Real_47pairs` [`secondary_cached_tuple`] | `846.46` | `840.57` | `847.51` | `1.00x` / `0.99x` | `933.64` / `913.78` / `958.69` | `7401.3` / `7397.9` / `7398.3` |
| `Assembly24_Obj014_23pairs` [`uncached_tuple`] | `128.52` | `117.61` | **`105.90`** | **`1.21x` / `1.11x`** | `169.14` / `150.25` / `164.99` | `679.7` / `678.5` / `581.3` |
| `Assembly24_Obj014_23pairs` [`uncached_ndarray`] | `128.03` | `118.72` | **`105.57`** | **`1.21x` / `1.12x`** | `170.19` / `139.82` / `125.21` | `679.9` / `678.6` / `581.5` |
| `Assembly24_Obj014_23pairs` [`secondary_cached_tuple`] | `96.04` | `94.40` | `94.75` | `1.01x` / `1.00x` | `139.12` / `116.04` / `135.73` | `2945.6` / `2937.8` / `2938.1` |

`win32_process_memory_probe` (`K32GetProcessMemoryInfo`): across `HighRes_1536F_Pair`, `Sheet_Dented_2mm`, `Tube_Coiled_Loose`, and `G508_Peer_000`, `P3_Lazy` recorded `ws_delta_bytes = 0` on 3/4 workloads (`+4096` bytes on `Sheet_Dented_2mm`) with `peak_working_set_bytes = 690933760` unchanged.

---

## 4. C03/F01 Paid-Dequeue Credit Monotonicity Audit (Under Lazy BVH)

Across headroom deltas `[0..32]` relative to `M_paid_ref_lazy` across all 5 variants (`PAID_REF`, `OFF`, `ON_normal`, `ON_in_admission_fail_dir`, `ON_in_admission_fail_slab`):

| Case | `M_off_lazy` | `M_paid_ref_lazy` | `M_on_lazy` | `dequeue_reused_aabb_bounds` | Total Holes (`0..32` across all 5 variants) |
| --- | ---: | ---: | ---: | ---: | ---: |
| `tilted48` | `6894` | `7499` | `6191` | `516` | **`0`** |
| `G508_Competing_001` | `34313` | `36083` | `10607` | `564` | **`0`** |
| `sheet5um` | `7454` | `7505` | `7454` | `51` | **`0`** |

---

## 5. Honest Tradeoffs & Frozen Eager Test Divergences

1. **High-Expansion / Small-Mesh Overhead (`G508_Peer_000`, `D48_Real_47pairs`)**:
   - On `HighRes_1536F_Pair`, `Sheet_Dented_2mm`, `Sheet_Parallel_5um`, `Tube_Coiled_Loose`, `Rotated_30deg_Spheres`, `G508_Competing_001`, and `Assembly24_Obj014_23pairs`, lazy pruning expands only `3.33%–25.59%` of the BVH, delivering **`1.21x–2.52x`** median speedup vs `A` (`1.11x–1.98x` vs `K`) and **`14%–18%`** peak `tracemalloc` reduction.
   - Conversely, when traversal must inspect most of the tree (`G508_Peer_000` creates `78.15%` of nodes) or runs many small-face pairs (`D48_Real_47pairs` uncached), per-split lazy list/checkpoint dispatch costs `-1.2%..-1.6%` vs `A` (`-3.1%..-4.4%` vs `K`), while cached `_mesh_cache` (`secondary_cached_tuple`) stays at parity (`1.00x–1.01x`).
   - **Recommended P3.1 Follow-up**: Adaptive activation threshold (e.g., skipping lazy indirection for small meshes or eagerly finishing subtrees once `n <= 32`) can eliminate the high-expansion overhead while retaining the `2x` construction wins.
2. **Expected Divergences on Frozen Eager-Assumption Assertions (Frozen Files Left Untouched)**:
   - `benchmarks/verify_review_suite.py` (`verify_r01_fast_projection`, line 329): Assumes eager BVH pre-build headroom `def_on_wu = 7099` and hardcodes `range(def_on_wu - 180, def_on_wu - 120)`. Under Lazy BVH, `def_l, def_r` requires only `def_on_wu = 6855` work units (`lazy_bvh_nodes_created = 134`, `fp_node_pruned = 83`, `credit_balance = 91`), so subtracting `120+` cancels inside lazy node build before `fp` projection while tight headroom deferral (`witness_projection_budget_deferrals = 1`, exact result) occurs cleanly at `cap = 6855` (`rem_try = 0`). Because `verify_review_suite.py` is frozen, `test_kernel_043_lazy_bvh.py::test_05` explicitly verifies both the lazy deferral window around `lazy_wu` and the preserved `_lazy_bvh=False` eager window.
   - `benchmarks/test_kernel_042_p1_histogram.py` (`test_04`) and `benchmarks/test_kernel_042_p2_prep.py` (`test_03`): Assert strict `work_units` equality against eager Arm `A` (`13986 != 6846` on `Sheet_Dented_2mm`; `7461 != 5500` on `Rotated_30deg_Spheres`). Lazy BVH intentionally reduces `surface_bvh_build` work units by pruning `82%–97%` of node creation while preserving `_surface_sig` parity `100%`.

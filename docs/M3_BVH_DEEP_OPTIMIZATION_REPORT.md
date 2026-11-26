# M3 BVH Deep Optimization Analysis & Experimental Report

- **Branch**: `codex/m3-bvh-deep-optimization`
- **Base Commit**: `codex/publish-m6-independent-pair-dual-spawn-039` (`716e9e8f7`, parent M3 032 product `6c93f2375`)
- **Optimized Runtime Source SHA-256**: `8b96993bcb3e77c1d904846a7e09f19ba45c56fc6b2a148225216ace07a3c66b` (`143` runtime modules)
- **Benchmark Harness**: [bvh_eval.py](file:///e:/bvh/benchmarks/bvh_eval.py) (`--warmup 1 --repeats 3`, GC disabled per sample, `tracemalloc` peak memory)
- **Golden Baseline & Final Data**: [baseline_032.json](file:///e:/bvh/benchmarks/baseline_032.json), [opt_bvh_final.json](file:///e:/bvh/benchmarks/opt_bvh_final.json)

---

## 1. Baseline Diagnosis (`032` / `039`)

Profiling baseline M3 BVH workloads (`G508_Peer_000`, `Sheet_Parallel_5um`, `G508_Control_12F`, `HighRes_1536F_Pair`, `Analyze_Tube_668F`, `Closed_Spheres_224F`) revealed five compounding algorithmic and implementation bottlenecks:

1. **Median Split + Coarse Leaf Size (`leaf_size=4`) in `_bvh`**:
   - Longest-axis count-median splitting grouped small curved/corner triangles with large spanning triangles, producing bloated node AABBs (`G508_Peer_000`: `127,670` leaf pair visits for only `268` narrow-phase calls — `99.79%` wasted).
2. **`key == 0` Breadth-First Degeneracy & Missing Initial Upper Bound**:
   - `_nearest_tree` pushed `(key, serial, left, right)`. Whenever node AABBs overlapped (`key == 0`), FIFO `serial` ordering turned best-first search into BFS, expanding roughly half the BVH before touching a leaf to initialize `best`.
   - Children were pushed blindly onto `pending` without push-time rejection or monotone early termination when `key > best_floor`.
3. **Lack of Canonical Tie-Break Equality Pruning (`>=`)**:
   - Canonical witness tie-breaking selects minimum `(i, j)` lexicographically among exact equal-distance pairs, yet `_aabb_exceeds_best` and `_plane_exceeds_best` only pruned on strict `>`. On coplanar/parallel surfaces (`Sheet_Parallel_5um`), all `8,464` equal-distance narrow pairs were exhaustively evaluated.
4. **Leaf-Only Witness Projection Starvation & High-Cost Inner Loops**:
   - `032` delayed `_WitnessProjection` until `64` completed exact pairs, lacked node-level projection pruning, recomputed AABB/plane/projection checks only at the leaf level, and incurred ~20M+ calls (`_bounded`, `zip`/generator expressions, redundant `math.gcd` in `_closer` before checking `best`, recomputed face cross products in `_point_faces`, and `Fraction.from_float` in `_integer_frame`).
5. **Cross-Pair Redundant Preparation in Multi-Object Entries**:
   - In `surface_nearest_result` (`11` pairs sharing `focal`) and `surface_scan_result` (`66` pairs over `12` meshes), `_admit`, `_integer_frame`, and `_bvh` re-validated topology, re-parsed coordinates, and rebuilt identical trees for every single pair.

---

## 2. Implemented Optimizations

### Round 1A: Exact Distance Micro-Kernel ([surface_proximity.py](file:///e:/bvh/human_eye_plugin/surface_proximity.py))
- **Pre-GCD & Unit-Denominator Fast Exit (`_closer`)**: Compare `numerator * best[1]` vs `best[0] * denominator` BEFORE calling `_ratio` (`math.gcd`), and skip `math.gcd` when `denominator == 1`, eliminating >99.9% of unnecessary GCD reductions while preserving full 4096-bit overflow checks.
- **Unboxed Exact Integer Domain Path (`_FAST_COORD_LIMIT = 1 << 500`)**: Proven exact bit-width bound (`7*500 + 16 = 3516 <= MAX_BITS = 4096` for all non-clipping integer operations) replaces per-op `_bounded` / `zip` / generator expressions with direct 3-tuple arithmetic for standard scenes (`<= 500`-bit relative coordinates), while automatically falling back to checked `_bounded` arithmetic for extreme inputs (`> 500` bits) and `_clip_coplanar` / `_plane_slice`.
- **Feature-Level Algebraic Reuse & Early Cutoffs (`_nearest_pair`, `_point_faces`, `_point_edges`, `_edge_edges`)**:
  - Recycle `da, db` plane heights from `_triangle_plane_bounds` / `_intersection_with_planes` directly into `_point_faces` to skip plane-exceeding tests before computing barycentric coordinates.
  - Lazily cache `(p2 - p0) x normal` and `normal x (p1 - p0)` per surviving triangle (`_fast_bary`).
  - Add exact O(1) point-to-segment and segment-to-segment integer AABB gap rejection in `_point_edges` / `_edge_edges`, plus infinite-line height rejection in `_edge_edges` prior to computing `(s, t)` parameters.
  - Propagate `tie_accept` cleanly inside `_nearest_pair` when `pair < best_pair` so `best` is still passed as a strict upper filter without ever breaking canonical `(i, j)` or feature-order determinism.

### Round 1B: SAH BVH, Priority Traversal & Tight Witness Projection ([surface_geometry.py](file:///e:/bvh/human_eye_plugin/surface_geometry.py), [surface_proximity.py](file:///e:/bvh/human_eye_plugin/surface_proximity.py))
- **12-Bin SAH `_bvh`**: Replaced longest-axis count-median splitting with exact integer binned Surface Area Heuristic (`_SAH_BINS = 12`, `_SAH_MIN_N = 12`, flat bin arrays, O(1) fast leaves for `n <= 2`) guarded by `_SAH_MAX_DEPTH = 20` (guaranteeing worst-case build work stays bounded cleanly below `MAX_WORK_UNITS`), using `leaf_size = 2` in `_distance_roots`.
- **Compiled Traversal Nodes + 1-Path Greedy DFS Seeding (`_compile_bvh_node`, `_nearest_tree`)**:
  - Compiles BVH nodes once per query into flat 14-tuples storing unboxed bounds, `min_id`, and shifted center coordinates `(cx2, cy2, cz2)`.
  - Executes an inline 1-path greedy DFS descent ordered by `(gap_sq, center_dist_sq, min_id)` to seed `best` before popping from the heap.
  - Orders the priority queue by `(gap_sq, center_dist_sq, serial)` to descend overlapping regions best-first instead of BFS.
- **Canonical Tie-Break Equality Pruning (`tie_floor = (bn - 1) // bd`), Push-Time Pruning & Monotone Early Break**:
  - Uses subtree `(left_min_id, right_min_id) > best_pair` to apply exact `>=` pruning at node push-time, pop-time, leaf AABB, plane bounds, and witness projection.
  - Terminates `_nearest_tree` immediately once `shift == 0` and popped `key > best_floor`.
- **Immediate Node & Leaf `_FastWitnessProjection`**:
  - Builds exact primitive witness-direction separator immediately upon initial `best` without waiting 64 pairs.
  - Checks O(1) 8-corner AABB projection first, then refines subtrees (`count <= 512`, `node_pair_visits >= 16`) with exact iterative bottom-up triangle-vertex intervals (`_node_interval`) and tests leaf triangle intervals BEFORE expensive 6-dot `_triangle_plane_bounds`.
- **Dyadic Float Frame (`_float_dyadic` via `math.frexp`), NumPy `.tolist()` Ingestion & Pre-Interned Stages**: Eliminated `Fraction.from_float` churn in `_integer_frame`, accelerated `_admit_one` via C-level `.tolist()` and `dict` edge counting, and pre-interned `_WORK_STAGES` / `_CLOSED_STAGES`.

### Round 2: `surface_geometry` & Cross-Pair Multi-Object Reuse ([surface_geometry.py](file:///e:/bvh/human_eye_plugin/surface_geometry.py), [task_query.py](file:///e:/bvh/human_eye_plugin/task_query.py), [surface_scan.py](file:///e:/bvh/human_eye_plugin/surface_scan.py))
- **`surface_geometry.py` Fast Paths**: Unboxed 3-tuple vector operations (`sub`, `add`, `mul`, `dot`, `normal`), early `da` plane separation in `intersection`, precomputed normals + shared-simplex half-space certificate in `analyze`, unrolled 3D box checks in `candidate_pairs`, `fast_ints` precheck in `_closed_precheck`, and small-side shared-anchor filtering in `_closed_node_simplex`.
- **Query-Local Mesh & Translation-Invariant BVH Reuse (`_mesh_cache`, `_pair_from_mesh_cache`, `_translate_bvh`, `_translate_triangles`)**:
  - Inside `surface_nearest_result` (`task_query.py`) and `surface_scan_result` (`surface_scan.py`), immutable mesh admission, dyadic vertices, triangles, and local SAH BVHs are prepared once per mesh and mathematically translated/scaled into each pair's exact dyadic frame without recomputing cross products, dot products, or BVH splits (with zero alteration to `SpatialSceneCache` pair keys or `algorithm_version`).

---

## 3. Equivalence & Verification Results

### Correctness Gates & Mathematical Equivalence
- `benchmarks/bvh_eval.py --compare baseline_032.json`: **`EQUIVALENCE CHECK PASSED`**
  - `g508_oracle`: **`pass`**
  - `analytic_pairs`: **`14` / `14` exact pass**
  - `scalability_controls`: **`pass`** (exact `MAX_WORK_UNITS`, `MAX_NARROW_PHASE_PAIRS`, checkpoint exception propagation preserved)
  - All `21` benchmark workloads match baseline bit-for-bit across `measurement_valid`, `reason`, `distance_m`, `_exact_distance_sq`, `point_a_world`, `point_b_world`, `direction_a_to_b`, `witness_status`, `direction_status`, `topology`, `witness_triangle_indices`, `spatial.relation`, `closed_solid.relation`, `analyze` relations/counts, `surface_nearest` `nearest_ids` & `coverage`, and `surface_scan` `coverage` & matches.

### Unit Test Verification
- Core M3 BVH / Spatial / Geometry / Surface Scan / Cache suite (`17` modules): **`311 / 311` passed** (`0` failures, `0` errors).
- `SurfaceAABBPruningTests` + `test_resident_nearest` + `test_selected_geometry`: **`52 / 52` passed** (`0` failures, `0` errors).
- `verification/run_portable_tests.py` (`187` modules, `3,203` tests): ran on `codex/m3-bvh-deep-optimization`; `24` failures / `21` errors / `12` skipped match pre-existing M6 branch drift on `716e9e8f7` (5-tool vs 4-tool schema assertions, missing untracked `fixes/` JSON fixture, Windows atomic file replacement semantics in `test_request_lifecycle`/`test_task_noop_persist`, native spawn tests, and OpenBLAS QR numerical precision in `test_local_sat_safety`), with zero regressions in BVH/M3 tests.

---

## 4. Benchmark Comparison Summary (`baseline_032.json` vs `opt_bvh_final.json`)

Measured with `--warmup 1 --repeats 3`, GC disabled per timed invocation:

| Group | Workload | Baseline (ms) | Optimized (ms) | Speedup | Nodes (Base -> Opt) | Leaves (Base -> Opt) | Narrow (Base -> Opt) | Work Units (Base -> Opt) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| surface_single | `Sheet_Parallel_5um` | 2416.704 | 22.709 | **106.42x** | 4111 -> 68 | 15040 -> 12 | 8464 -> 3 | 419636 -> 14246 |
| surface_single | `LargeShift_2pow30` | 113.118 | 1.972 | **57.37x** | 433 -> 61 | 2851 -> 13 | 2024 -> 5 | 27167 -> 1621 |
| surface_single | `G508_Competing_001` | 494.134 | 21.871 | **22.59x** | 1649 -> 167 | 8285 -> 110 | 1234 -> 21 | 88786 -> 9676 |
| surface_single | `Tube_Coiled_Loose` | 730.389 | 58.220 | **12.55x** | 10347 -> 641 | 20492 -> 601 | 1379 -> 74 | 161148 -> 26951 |
| surface_single | `G508_Peer_000` | 1007.492 | 89.504 | **11.26x** | 18597 -> 4417 | 127670 -> 3205 | 268 -> 113 | 504330 -> 46115 |
| surface_single | `G508_Near_003` | 245.651 | 33.598 | **7.31x** | 2983 -> 1275 | 18386 -> 709 | 222 -> 37 | 95296 -> 16322 |
| surface_single | `G508_Control_12F` | 21.667 | 4.215 | **5.14x** | 0 -> 0 | 144 -> 144 | 104 -> 104 | 4753 -> 4633 |
| surface_single | `Rotated_30deg_Spheres` | 26.072 | 14.602 | **1.79x** | 181 -> 103 | 168 -> 26 | 30 -> 11 | 6965 -> 6454 |
| surface_single | `HighRes_1536F_Pair` | 135.440 | 102.328 | **1.32x** | 359 -> 156 | 135 -> 36 | 50 -> 16 | 47118 -> 49192 |
| surface_single | `Sheet_Dented_2mm` | 42.898 | 43.428 | 0.99x | 271 -> 17 | 192 -> 4 | 10 -> 1 | 14132 -> 13986 |
| surface_batch | `G508_Target_vs_All11` | 9305.802 | 572.363 | **16.26x** | 47141 -> 18811 | 300002 -> 12237 | 20488 -> 1292 | 2151184 -> 256440 |
| surface_batch | `D48_Sim_47pairs` | 1437.263 | 240.770 | **5.97x** | 15647 -> 7374 | 79896 -> 5770 | 3732 -> 701 | 417167 -> 122131 |
| spatial_relation | `Spatial_G508_Competing` | 439.412 | 21.965 | **20.01x** | 1649 -> 167 | 8285 -> 110 | 1234 -> 21 | 89361 -> 10251 |
| spatial_relation | `Spatial_G508_Peer_000` | 901.585 | 89.078 | **10.12x** | 18597 -> 4417 | 127670 -> 3205 | 268 -> 113 | 505354 -> 47139 |
| spatial_relation | `Spatial_G508_Near_003` | 225.968 | 33.638 | **6.72x** | 2983 -> 1275 | 18386 -> 709 | 222 -> 37 | 95871 -> 16897 |
| spatial_relation | `Spatial_Control_12F` | 21.449 | 4.350 | **4.93x** | 0 -> 0 | 144 -> 144 | 104 -> 104 | 4786 -> 4666 |
| closed_solid | `Closed_G508_Control` | 3.578 | 2.266 | **1.58x** | 33 -> 33 | 132 -> 132 | 0 -> 0 | 1622 -> 1622 |
| closed_solid | `Closed_Spheres_224F` | 95.243 | 69.857 | **1.36x** | 9513 -> 8839 | 261 -> 261 | 0 -> 0 | 67578 -> 59164 |
| surface_analyze | `Analyze_Tube_668F` | 344.618 | 202.060 | **1.71x** | 8614 -> 4550 | 19294 -> 13272 | 0 -> 0 | — |
| e2e_entries | `G508_surface_nearest` | 9530.185 | 424.740 | **22.44x** | — | — | 11 kernel calls | — |
| e2e_entries | `G508_surface_scan_5mm` | 21104.526 | 986.507 | **21.39x** | — | — | 66 kernel calls | — |

Peak traced memory (`tracemalloc`): reduced on `G508_Peer_000` (`2707.2 -> 2120.1 KiB`), `G508_Target_vs_All11` (`4821.6 -> 2120.2 KiB`, `-56%`), `G508_surface_nearest` (`7558.6 -> 6475.9 KiB`), and `G508_surface_scan_5mm` (`7888.3 -> 6802.6 KiB`).

---

## 5. Reproducibility

```powershell
e:\bvh\.venv\Scripts\python.exe -B e:\bvh\benchmarks\bvh_eval.py --warmup 1 --repeats 3 --compare e:\bvh\benchmarks\baseline_032.json
e:\bvh\.venv\Scripts\python.exe -B -m unittest verification.test_surface_proximity_001 verification.test_surface_geometry verification.test_spatial_index verification.test_concave_geometry verification.test_contact_directions verification.test_concave_roundoff verification.test_region_summary verification.m3_pair_scalability_001.testing.test_node_certificates verification.m3_sufficient_separation_001.testing.test_sufficient_separation verification.test_surface_tasks verification.test_surface_owned verification.test_surface_owned_task verification.test_surface_scope_regression verification.test_task_query verification.test_surface_scan_host verification.test_cache_accounting verification.test_alignment_scene_cache verification.m4_surface_scan_001.tests.test_surface_scan
```

# Kernel-044 Phase 4 Review: Exact Traversal/Projection Hot-Loop & Separating-Axis Cross-Pair Cutoff (`KERNEL_044_P4_REVIEW`)

> **Verdict**: `CANDIDATE_044_P4_VALIDATED_ZERO_REGRESSION`  
> **Research Branch**: `codex/m3-bvh-p4-traversal-cutoff-044`  
> **Base Commit (`freeze/m3-bvh-042-p2-arm-k`)**: `b5b0df58bed75f3a259af8078630e1cb511ff769` (`runtime_source_sha256 = cc78597b4b4c9e336e7082bcb2fd99ba9739ead2e01104c095f8046fe048baf7`)  
> **Frozen 041 Reference Commit (`freeze/m3-bvh-041-r3`)**: `119327bbb4e645c5de3bfbc0d30259736b9a2677` (`runtime_source_sha256 = eff6511223646c125ac05cd6080d3bcbe191d1c945a8b3b7293d2c1bc0ff1ee4`)  
> **Candidate Runtime Identity (`P4_A / P4_AB`)**: `runtime_source_sha256 = 7bfbd71982a7152cabf5cb04cf666fd8992bb016e6e09e01a6cd92a3c225b8d5`  
> - `human_eye_plugin/surface_geometry.py` (untouched from `8d68d1a13`): `84cb39427d78c4174868285019b3929f28a564c6287584d03336faa77175169e`  
> - `human_eye_plugin/surface_proximity.py`: `8f7b08b6a5e5d9c5079470bd05e5c22d48b055f14cf49a93f8e5c845bb18af45`

---

## 1. Architecture Summary (`P4-A` & `P4-B`)

M3 BVH-044 (`P4`) targets traversal, witness-projection, narrowphase, and multi-pair batch upper-bound bottlenecks exposed after `042-P2` without modifying `surface_geometry.py`, BVH topology, or any `041`/`042` budget invariant:

1. **`P4-A` — Zero-Topology, Zero-`work_units`-Change Traversal / Projection / Narrowphase Hot-Loop**:
   - `_Work.tick` / `_Work.consume`: Cached `_WORK_STAGES.get` lookup and `counts[kind] += amount` fast update (`try/except KeyError` on first key init).
   - Closure-free, single-cache-lookup `_FastWitnessProjection.prunes_nodes` & `prunes_triangles`: Eliminates inner closures/lambdas (`_test_box`, `_test_slabs`, `_test_tris`, `_emit_prune` lambda), caches `node_a.get` / `node_b.get` hits before `_node_interval` dispatch, and executes the exact `credit` admission/debit invariant inline.
   - Generator-free, division-free `_plane_exceeds_best(..., fast_ints=fast_ints)` and `_aabb_exceeds_best(..., remaining=..., fast_ints=fast_ints)`: Direct 3-tuple unpacking + integer cross-multiplication (`gap * gap * d > n * nsq`) and precomputed floor reuse on `fast_ints` paths, preserving exact `_scratch` + `isqrt` fallback for large integers.
   - Tuple-free fast push (`shift == 0 and fast_ints`) inside `_nearest_tree` and pre-`_closer` quick rejection inside `_point_edges(..., fast_ints=True)`.
2. **`P4-B` — Exact Cross-Pair Upper-Bound Cutoff & Separating-Axis Cutoff Projection (`_upper_bound_sq_key` + `measure_nearest_surface_batch`)**:
   - Opt-in `_upper_bound_sq_key` validates and converts a world exact distance key `[num, den, exp]` into a local integer frame cutoff `(cut_n, cut_d, cut_n // cut_d)` (failing closed if exponent shift exceeds `MAX_BITS`), pruning strictly `> cutoff` (`strict=True`, `tie_accept=True`) at root AABB, BVH queue/DFS, linear path, and leaf triangle bounds while preserving **100% exact ties (`== cutoff`) and canonical witnesses**.
   - **Separating-Axis Cutoff Projection (`_FastWitnessProjection.build_for_cutoff`)**: Solves an initially discovered `D48_Real_47pairs` regression (`0.81x` with pure AABB cutoff alone due to axis-overlapping diagonal sleeves disabling `_FastWitnessProjection` while `best is None`): when DFS ends with `best is None` under `cutoff`, a single DFS leaf witness seeds an exact Cauchy-Schwarz axis (`math.isqrt((norm_sq * cut_n) // cut_d)`), immediately pruning overlapping diagonal subtrees (flipping `D48` from `0.81x` to **`1.64x–1.72x`** speedup!).
   - **`measure_nearest_surface_batch`**: Exact target-to-peers nearest reducer with optional ascending world-AABB sort (`sort_by_aabb`), `_mesh_cache`, `_upper_bound_sq_key` propagation, and tie-preserving canonical sorted `nearest_indices`.

---

## 2. P4-A Exact Ledger Parity & 30-Repeat Paired Confirmation (`A` vs `K` vs `P4_A`)

- **Ledger Parity (`verify_p4a_exact_work_and_sig_parity`)**: Across all `9` single workloads × `3` projection modes (`27` runs) and both batch workloads (`D48_Real_47pairs`, `Assembly24_Obj014_23pairs`, cached & uncached), live `P4_A` matched frozen `Arm K` **`100%` on `_surface_sig` and `100%` on the full `work` dictionary** (zero `work_units` or credit-counter change).
- **Regression Gate**: `max_regression_vs_K = 0.83%` (`Sheet_Dented_2mm.uncached_tuple`, noise band `<= 2.0%`), **`verdict = CANDIDATE_044_P4_VALIDATED_ZERO_REGRESSION`**.

| Workload [Variant] | `A` Med (ms) | `K` Med (ms) | `P4_A` Med (ms) | Speedup vs `A` | vs `K` (%) | `p95` (ms: `A` / `K` / `P4_A`) | Peak `tracemalloc` (KB: `A` / `K` / `P4_A`) |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `G508_Peer_000` [`uncached_tuple`] | `123.96` | `118.49` | **`100.47`** | **`1.23x`** | **`+15.21%`** | `151.94` / `122.04` / `124.44` | `3024.7` / `3054.9` / `3055.5` |
| `G508_Peer_000` [`uncached_ndarray`] | `125.08` | `119.93` | **`100.77`** | **`1.24x`** | **`+15.98%`** | `140.39` / `158.99` / `126.60` | `3024.7` / `3054.9` / `3055.5` |
| `G508_Competing_001` [`uncached_tuple`] | `26.60` | `23.95` | **`22.22`** | **`1.20x`** | **`+7.20%`** | `30.88` / `25.32` / `25.84` | `1620.5` / `1577.5` / `1576.9` |
| `G508_Competing_001` [`uncached_ndarray`] | `26.37` | `23.81` | **`22.31`** | **`1.18x`** | **`+6.31%`** | `44.65` / `27.29` / `23.43` | `1620.6` / `1577.7` / `1577.1` |
| `HighRes_1536F_Pair` [`uncached_tuple`] | `101.91` | `85.55` | `84.27` | `1.21x` | `+1.49%` | `135.93` / `104.52` / `98.44` | `8563.0` / `8653.8` / `8654.5` |
| `HighRes_1536F_Pair` [`uncached_ndarray`] | `105.18` | `86.21` | `85.83` | `1.23x` | `+0.44%` | `119.18` / `99.45` / `100.05` | `8755.1` / `8846.0` / `8846.6` |
| `Sheet_Dented_2mm` [`uncached_tuple`] | `24.94` | `19.78` | `19.94` | `1.25x` | `-0.83%` | `26.38` / `26.08` / `30.51` | `2647.9` / `2604.3` / `2604.9` |
| `Sheet_Dented_2mm` [`uncached_ndarray`] | `25.01` | `20.10` | `19.98` | `1.25x` | `+0.57%` | `26.17` / `22.02` / `20.82` | `2656.4` / `2612.8` / `2613.3` |
| `Sheet_Parallel_5um` [`uncached_tuple`] | `20.58` | `16.84` | `16.78` | `1.23x` | `+0.38%` | `42.41` / `18.94` / `20.30` | `2425.4` / `2381.7` / `2382.5` |
| `Sheet_Parallel_5um` [`uncached_ndarray`] | `20.99` | `17.20` | `17.28` | `1.21x` | `-0.48%` | `22.67` / `18.36` / `18.48` | `2433.9` / `2390.3` / `2390.9` |
| `Rotated_30deg_Spheres` [`uncached_tuple`] | `14.72` | `12.87` | `12.53` | `1.17x` | `+2.59%` | `15.77` / `13.59` / `13.32` | `1263.3` / `1245.0` / `1245.6` |
| `Rotated_30deg_Spheres` [`uncached_ndarray`] | `14.70` | `12.84` | `12.47` | `1.18x` | `+2.81%` | `15.99` / `22.85` / `13.26` | `1263.5` / `1245.1` / `1245.7` |
| `Tube_Coiled_Loose` [`uncached_tuple`] | `57.88` | `51.15` | **`49.52`** | `1.17x` | **`+3.18%`** | `60.36` / `54.48` / `50.96` | `4000.9` / `3950.4` / `3951.3` |
| `Tube_Coiled_Loose` [`uncached_ndarray`] | `58.70` | `51.09` | **`49.73`** | `1.18x` | **`+2.67%`** | `79.19` / `52.83` / `51.90` | `4030.3` / `3979.8` / `3980.7` |
| `Control_12F_Linear` [`uncached_tuple`] | `4.26` | `4.30` | `4.18` | `1.02x` | `+2.86%` | `8.78` / `9.77` / `16.11` | `49.7` / `52.5` / `52.5` |
| `Control_12F_Linear` [`uncached_ndarray`] | `4.28` | `4.22` | `4.17` | `1.03x` | `+1.16%` | `4.50` / `4.29` / `4.27` | `49.7` / `52.6` / `52.6` |
| `Sparse_100kV_Degenerate_MixedBit` [`uncached_tuple`] | `1.26` | `1.15` | `1.14` | `1.11x` | `+0.81%` | `1.38` / `1.19` / `1.25` | `138.2` / `135.3` / `135.8` |
| `Sparse_100kV_Degenerate_MixedBit` [`uncached_ndarray`] | `1.29` | `1.18` | `1.17` | `1.10x` | `+0.83%` | `1.36` / `1.27` / `1.21` | `141.9` / `139.0` / `139.5` |
| `D48_Real_47pairs` [`uncached_tuple`] | `882.57` | `847.17` | **`732.18`** | **`1.21x`** | **`+13.57%`** | `962.70` / `923.37` / `888.76` | `545.6` / `554.2` / `554.7` |
| `D48_Real_47pairs` [`uncached_ndarray`] | `895.37` | `868.54` | **`751.65`** | **`1.19x`** | **`+13.46%`** | `973.47` / `944.77` / `836.75` | `545.7` / `554.3` / `554.8` |
| `D48_Real_47pairs` [`secondary_cached_tuple`] | `854.40` | `845.94` | **`726.34`** | **`1.18x`** | **`+14.14%`** | `939.19` / `944.14` / `792.04` | `7401.3` / `7397.9` / `7395.4` |
| `Assembly24_Obj014_23pairs` [`uncached_tuple`] | `126.26` | `116.59` | **`111.89`** | `1.13x` | **`+4.03%`** | `162.22` / `154.11` / `149.00` | `679.7` / `678.5` / `678.1` |
| `Assembly24_Obj014_23pairs` [`uncached_ndarray`] | `127.46` | `117.72` | **`112.28`** | `1.14x` | **`+4.63%`** | `180.25` / `167.38` / `133.52` | `679.9` / `678.6` / `678.2` |
| `Assembly24_Obj014_23pairs` [`secondary_cached_tuple`] | `94.81` | `93.68` | **`88.64`** | `1.07x` | **`+5.39%`** | `138.68` / `144.16` / `138.10` | `2945.6` / `2937.8` / `2937.9` |

`win32_process_memory_probe`: `P4_A` recorded `ws_delta_bytes = 0` on all 4 probed workloads (`G508_Peer_000`, `HighRes_1536F_Pair`, `Sheet_Dented_2mm`, `Tube_Coiled_Loose`), with `peak_working_set_bytes = 130572288` unchanged.

---

## 3. P4-B 30-Repeat Exact Batch Nearest Cutoff Results (`K` vs `P4_A` vs `P4_AB`)

| Batch [Variant] | `K_exhaustive` (ms) | `P4_A_exhaustive` (ms) | `P4_AB_cutoff` (ms) | Speedup (`vs K` / `vs P4_A`) | `p95` (`K` / `P4_AB` ms) | Pruned Peers | Work Units (`exh -> cut`) |
| --- | ---: | ---: | ---: | --- | --- | ---: | --- |
| `D48_Real_47pairs` [`uncached_tuple_natural`] | `879.31` | `791.53` | **`522.54`** | **`1.68x` / `1.51x`** | `941.61` / `591.87` | `45/47` | `430147 -> 303443` |
| `D48_Real_47pairs` [`uncached_tuple_sorted`] | `862.22` | `767.32` | **`524.57`** | **`1.64x` / `1.46x`** | `955.72` / `623.94` | `45/47` | `430147 -> 303443` |
| `D48_Real_47pairs` [`uncached_ndarray_sorted`] | `891.09` | `730.58` | **`519.70`** | **`1.71x` / `1.41x`** | `970.41` / `613.41` | `45/47` | `430147 -> 303443` |
| `D48_Real_47pairs` [`cached_tuple_sorted`] | `864.49` | `760.88` | **`503.16`** | **`1.72x` / `1.51x`** | `1116.45` / `635.31` | `45/47` | `430147 -> 303443` |
| `Assembly24_Obj014_23pairs` [`uncached_tuple_natural`] | `116.67` | `111.87` | **`37.32`** | **`3.13x` / `3.00x`** | `151.20` / `38.51` | `21/23` | `83352 -> 26056` |
| `Assembly24_Obj014_23pairs` [`uncached_tuple_sorted`] | `117.20` | `112.03` | **`37.53`** | **`3.12x` / `2.98x`** | `159.45` / `53.04` | `18/23` | `83352 -> 25595` |
| `Assembly24_Obj014_23pairs` [`uncached_ndarray_sorted`] | `118.54` | `113.25` | **`38.29`** | **`3.10x` / `2.96x`** | `150.03` / `55.44` | `18/23` | `83352 -> 25595` |
| `Assembly24_Obj014_23pairs` [`cached_tuple_sorted`] | `95.84` | `90.45` | **`40.61`** | **`2.36x` / `2.23x`** | `134.17` / `65.91` | `18/23` | `83352 -> 51519` |

---

## 4. Stage Freeze Registry (Zero-Regression Promotion Chain vs Research Archive)

| Tag | Branch / Role | Commit | `runtime_source_sha256` | Status / Gate Basis |
| --- | --- | --- | --- | --- |
| `freeze/m3-bvh-041-r3` | `codex/m3-bvh-deep-optimization` | `119327bbb4e645c5de3bfbc0d30259736b9a2677` | `eff6511223646c125ac05cd6080d3bcbe191d1c945a8b3b7293d2c1bc0ff1ee4` | **Frozen Baseline (`041 R3`)** |
| `freeze/m3-bvh-042-p0-arm-f` | `codex/m3-bvh-exact-build-pipeline-042` (`B1+B2+B4`) | `5102f1fefc6ebee8b0ca5d7ad0c03530b672add4` | `b0e4093dadf3eff8c9be18442922d802a4fa59adf2035f37958e8d5f32597dcd` | **Frozen (`+5%–+9%` heavy, 0 reg)** |
| `freeze/m3-bvh-042-p1-arm-i` | `codex/m3-bvh-exact-build-pipeline-042` (11-cut no-div SAH) | `8d68d1a133cb2635920ddd83b8b7f12bdc6e3869` | `1db11b89a8513e571faf55fbd9bccc183c82c12b6bf43159cb7b1f28b1f7f7ab` | **Frozen (`+15%–+20%` heavy, 0 reg)** |
| `freeze/m3-bvh-042-p2-arm-k` | `codex/m3-bvh-exact-build-pipeline-042` (common-exp frame) | `b5b0df58bed75f3a259af8078630e1cb511ff769` | `cc78597b4b4c9e336e7082bcb2fd99ba9739ead2e01104c095f8046fe048baf7` | **Frozen (`+19%–+22%` cum heavy, 0 reg)** |
| `archive/m3-bvh-043-p3-lazy-research` | `codex/m3-bvh-lazy-sah-043` (Lazy SAH BVH) | `ad93bc9d6` | `2f2d940dcfa1f16171642578b83c6ee5bac138eda563c2fd50aad7aaf5a97604` | **Research-only Archive (NOT frozen)**: `1.3x–2.52x` wins on sparse/sheet vs `-1.6%..-4.4%` on `G508_Peer_000`/`D48` + eager ledger shift |
| `freeze/m3-bvh-044-p4-traversal` | `codex/m3-bvh-p4-traversal-cutoff-044` (`P4-A` + `P4-B`) | *(HEAD of `044`)* | `7bfbd71982a7152cabf5cb04cf666fd8992bb016e6e09e01a6cd92a3c225b8d5` | **Frozen Zero-Regression (`P4-A +15.2% G508 / +14.1% D48`; `P4-B 1.72x D48 / 3.13x Assembly24`; `max_reg=0.83%`)** |

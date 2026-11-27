# M3 BVH Deep Optimization — Review Fixes & Verification Record (`BVH-R01` .. `BVH-R08`)

**Target Branch:** `codex/m3-bvh-deep-optimization`  
**Prior Candidate (`B`):** [`37ed2d63439a5331f4fca1d61ebc56cd891d27cc`](https://github.com/swenbo1-web/human-eye/commit/37ed2d63439a5331f4fca1d61ebc56cd891d27cc)  
**Research Baseline (`A` / 032):** [`6c93f2375d1073b33e721a168f1fcf610ac6dbdc`](https://github.com/swenbo1-web/human-eye/commit/6c93f2375d1073b33e721a168f1fcf610ac6dbdc) (cross-checked against 039 archive [`716e9e8f7ff87b95f55bf730dee184e77b48a335`](https://github.com/swenbo1-web/human-eye/commit/716e9e8f7ff87b95f55bf730dee184e77b48a335))  
**Fixed Candidate (`C`) Runtime Source Set SHA-256:** `46c4d1645919082c5a673aae96eed0380272eb53c9844f599440eda6bb11192f`  
**Machine-Readable Evidence:** [CORRECTNESS_AND_BOUNDARY_RESULTS.json](CORRECTNESS_AND_BOUNDARY_RESULTS.json) (`schema: m3-bvh-review-verification-v1`), [ALGORITHM_ABLATION.json](ALGORITHM_ABLATION.json) (`schema: m3-bvh-ablation-v1`)

---

## Summary Status Table

| ID | Priority | Classification & Status | Primary Locations | Verification Gate |
| --- | --- | --- | --- | --- |
| **BVH-R01** | P1 | **Fixed & Verified** — `_FastWitnessProjection` wired to `_Work`, checkpoints, bounded headroom reserve, and pop-time credit | [surface_proximity.py](../human_eye_plugin/surface_proximity.py#L216-L231), [L961-L1160](../human_eye_plugin/surface_proximity.py#L961-L1160), [L1476-L1637](../human_eye_plugin/surface_proximity.py#L1476-L1637) | [verify_review_suite.py](verify_review_suite.py#L166-L306) (`r01_fast_projection`: `passed=True`, 52/52 pairs, 4 cancel stages, 4 headroom tests) |
| **BVH-R02** | P1 | **Fixed & Verified** — Lazy 3-stage `_pair_from_mesh_cache`, `_DummyBuildBudget` removed, `_CacheBuildBudget`, immutability guard, atomic stage commits, linear/fallback skip | [surface_proximity.py](../human_eye_plugin/surface_proximity.py#L433-L480), [L1871-L2162](../human_eye_plugin/surface_proximity.py#L1871-L2162), [task_query.py](../human_eye_plugin/task_query.py#L627-L633), [surface_scan.py](../human_eye_plugin/surface_scan.py#L237) | [verify_review_suite.py](verify_review_suite.py#L309-L454) (`r02_mesh_cache`: `passed=True`, G508/D48/all-66/linear/fallback/isolation/4 cancel stages/mutability) |
| **BVH-R03** | P2 | **Verified** — Conservative bounding & witness/work parity under SAH affine non-isomorphism | [surface_geometry.py](../human_eye_plugin/surface_geometry.py#L170-L292), [surface_proximity.py](../human_eye_plugin/surface_proximity.py#L1954-L2023) | [verify_review_suite.py](verify_review_suite.py#L457-L523) (`r03_sah_translation`: `passed=True`, 2/2 boundary cases + BVH invariants) |
| **BVH-R04** | P2 | **Verified** — Algebraic degree/bit-width table + 499/500/501-bit, subnormal, $2^{900}$ origin, degenerate & `_closer` checks | [surface_proximity.py](../human_eye_plugin/surface_proximity.py#L22-L125), [L528-L763](../human_eye_plugin/surface_proximity.py#L528-L763), [surface_geometry.py](../human_eye_plugin/surface_geometry.py#L792-L835) | [verify_review_suite.py](verify_review_suite.py#L526-L629) (`r04_bit_domain_and_predicates`: `passed=True`, 8 boundary cases + empirical bit audit) |
| **BVH-R05** | P2 | **Verified (with noted caveat)** — Exact tie-floor, `shift > 0` safe path, linear/tree boundary, permutation/swap invariance; see note on vertex-slab subtree count | [surface_proximity.py](../human_eye_plugin/surface_proximity.py#L725-L866), [L1476-L1640](../human_eye_plugin/surface_proximity.py#L1476-L1640) | [verify_review_suite.py](verify_review_suite.py#L632-L788) (`r05_tie_pruning_and_subtree_oracle`: `passed=True`) |
| **BVH-R06** | P2 | **Clarified & Profiled** — Build/compile/traverse/narrow breakdown, `median` vs `sah`, `leaf_size` 1/2/4, depth/overlap stats; no auto-tuning added | [surface_geometry.py](../human_eye_plugin/surface_geometry.py#L138-L305), [surface_proximity.py](../human_eye_plugin/surface_proximity.py#L869-L930) | [run_ablation_and_assets.py](run_ablation_and_assets.py#L626-L743) (`r06_subphase_and_tree_quality`) |
| **BVH-R07** | P2 | **Verified & Memory Attributed** — Closed containment/penetration/separation, 6 shared-simplex cases, `near_m=0.001` bilateral boundaries, degenerate faces, >128 truncation parity, `2.46×–2.95×` `tracemalloc` breakdown | [surface_geometry.py](../human_eye_plugin/surface_geometry.py#L24-L47), [L143-L380](../human_eye_plugin/surface_geometry.py#L143-L380), [L745-L835](../human_eye_plugin/surface_geometry.py#L745-L835) | [verify_review_suite.py](verify_review_suite.py#L791-L945) (`r07_closed_and_analyze`: `passed=True`) |
| **BVH-R08** | P2 | **Fixed & Verified** — Schema `m3-bvh-eval-v2`, hardened comparator (`extra`/`missing`/batch length & order/full `spatial`/`closed`/`analyze`/`e2e`), 13 negative controls, separated CPU/`tracemalloc`, raw samples | [bvh_eval.py](bvh_eval.py#L437-L1073) | `bvh_eval.py --verify-comparator` (`passed=True`, `controls_checked=13`) |

---

## Detailed Findings & Fixes

### BVH-R01 (P1) — Fast Witness Projection Work Accounting, Headroom Guard, Credit Definition & Cancellation

#### What `37ed2d6` Got Wrong
1. `_FastWitnessProjection.build`, `_tri_interval`, `_node_interval`, `prunes_nodes`, and `prunes_triangles` did not charge `_Work` or invoke cooperative `checkpoint(...)` callbacks, bypassing `MAX_WORK_UNITS = 1179648` and collaborative cancellation.
2. `_nearest_tree.push_pair` credited `credit.saved_bound()` at node push time (`1` unit per pushed internal node pair), violating the 032 credit definition (which earned credit only when an actually popped item avoided dequeue bound recomputation).

#### Changes Implemented in Candidate `C`
- Added projection stages to `_WORK_STAGES` ([surface_proximity.py](../human_eye_plugin/surface_proximity.py#L227-L229)): `'witness_projection'`, `'witness_projection_tests'`, `'witness_projection_direction_builds'`, `'witness_projection_tri_dots'`, `'witness_projection_node_visits'`.
- Added `_wp_optional_allowance(budget, amount, reserve=_FAST_WP_HEADROOM_RESERVE)` with `_FAST_WP_HEADROOM_RESERVE = 4096` ([surface_proximity.py](../human_eye_plugin/surface_proximity.py#L1152-L1159)). Whenever `MAX_WORK_UNITS - work_units < amount + reserve`, optional projection work is skipped cleanly, `witness_projection_budget_deferrals` is incremented, and execution continues along the mandatory exact path without raising `surface_work_budget` or exceeding `MAX_WORK_UNITS`.
- Wired real `_Work` accounting and checkpoints into `_FastWitnessProjection` ([surface_proximity.py](../human_eye_plugin/surface_proximity.py#L961-L1138)):
  - `build`: checks `budget.checkpoint('surface_proximity_witness_projection')`, requires headroom for `_BUILD_COST = 8`, calls `budget.consume(7, 'witness_projection')` and `budget.tick('witness_projection_direction_builds', 1)`.
  - `_tri_interval`: checks headroom for `cost = len(pts)` and charges `budget.tick('witness_projection_tri_dots', cost)`.
  - `_node_interval`: iterative post-order stack checks headroom and calls `budget.tick('witness_projection_node_visits', 1)` **before** committing `node_cache[cid]`, so partial/cancelled scans leave no poisoned interval cache.
  - `prunes_nodes` & `prunes_triangles`: check headroom and charge `budget.tick('witness_projection_tests', 1)` per test.
- Removed push-time `credit.saved_bound()` from `push_pair` ([surface_proximity.py](../human_eye_plugin/surface_proximity.py#L1532-L1561)) and restored 032 pop-time `budget.checkpoint('surface_proximity_aabb_bound_tests')`, `budget.counts['aabb_bound_tests'] += 1`, and `credit.saved_bound()` at `shift == 0` heap dequeue ([surface_proximity.py](../human_eye_plugin/surface_proximity.py#L1598-L1602)). `shift > 0` continues to evaluate `_aabb_exceeds_best` with `tick('aabb_bound_tests')` and never triggers the global `break`.

#### Verification ([verify_review_suite.py](verify_review_suite.py#L166-L306))
- **Projection ON vs OFF equivalence:** `52/52` pairs (`G508_Peer_000`, `G508_Competing_001`, `Sheet_Parallel_5um`, `Tube_Coiled_Loose`, `Adversarial_Staircase` with multiple best epochs, and all `47` real `D48` pairs) match identically on full `_surface_sig`.
- **Sample ledgers (C vs B uncharged):** On `G508_Peer_000`, `work_units` increased honestly from `46115` (`B`) to `61751` (`C`), recording `wp_builds=3`, `wp_tests=6918`, `wp_pruned=1302`, `wp_tri_dots=6231`, `wp_node_visits=2463`, `credit_earned_bounds=4399`, `node_pair_visits=4417`.
- **Cancellation injection:** All 4 new stages (`surface_proximity_witness_projection`, `..._tests`, `..._tri_dots`, `..._node_visits`) propagate `_Cancel` with `hits=1` and `propagated=True`.
- **Headroom boundaries:** Under remaining headroom `25000`, `7`, `2`, optional projection defers cleanly (`wp_deferrals=367` at `25000`) and total `work_units` stays bounded at `1179648 <= MAX_WORK_UNITS`; with tight headroom (`needed_safe + 4`), query completes validly (`measurement_valid=True`, `wp_deferrals=1`, `work_units=1179644 <= 1179648`).

---

### BVH-R02 (P1) — Query-Local Mesh Cache Lazy 3-Stage Preparation, Real Budget/Cancel & Immutability

#### What `37ed2d6` Got Wrong
`_prepare_cached_mesh` previously ran `NOOP`-checkpoint `_admit_one`, prepared all vertices/triangles eager-first, built SA-BVHs via `_DummyBuildBudget` before per-pair budget/cancellation checks, lacked checkpoint hooks inside `_translate_triangles` / `_translate_bvh`, double-charged `validated_faces` on fallback, and did not verify container immutability on `mesh_cache` hits.

#### Changes Implemented in Candidate `C`
- Deleted `_DummyBuildBudget` and added `_CacheBuildBudget` ([surface_proximity.py](../human_eye_plugin/surface_proximity.py#L1871-L1881)) forwarding `consume(amount, stage)` directly to caller `budget` (so `work_units` and checkpoints execute live during tree construction).
- Extracted shared helper `_prepare_triangles_from_relative` ([surface_proximity.py](../human_eye_plugin/surface_proximity.py#L433-L479)) used by both uncached `_integer_frame` and cache cross-pair extreme-exponent fallback.
- Enforced immutability check `_mesh_cache_is_immutable(mesh, cache)` ([surface_proximity.py](../human_eye_plugin/surface_proximity.py#L1884-L1893)): requires either caller-sealed `cache.get('__sealed_query_meshes__') is True` (explicitly set in [task_query.py#L627](../human_eye_plugin/task_query.py#L627) and [surface_scan.py#L237](../human_eye_plugin/surface_scan.py#L237)), or strictly `tuple` / read-only `numpy` array storage (`not flags.writeable`). Unsealed mutable lists bypass identity caching automatically (`return None`).
- Refactored `_pair_from_mesh_cache` ([surface_proximity.py](../human_eye_plugin/surface_proximity.py#L2026-L2162)) into three strictly lazy stages with atomic commits:
  1. **Stage 1 (Admission, L2048–2067):** Checks `nl_raw + nr_raw > MAX_FACES` up front; on miss calls `_admit_one(mesh, budget.tick, ...)` with live `validated_faces` checkpoints/ticks before committing `ent['admission']`; on hit still charges `budget.tick('validated_faces', len(rec[1]))` so per-pair logical budget bounds are preserved (no budget borrowing across pairs).
  2. **Stage 2 (Local Frame & Bit-Domain Gate, L1896–1951, L2069–2111):** Computes `_ensure_cached_frame` lazily with `referenced_vertices` ticks and cross-pair `exponent` / `t_bits` / `fit_fast` verification (`fl['max_bits'] + dL < 490 and max(t_bits, fr['max_bits'] + dR) + 1 < 490`). On failure, increments `mesh_cache_fallbacks += 1` and calls `_prepare_triangles_from_relative` using already-admitted `records` — **zero** BVH build and **zero** duplicate `_admit` ticks.
  3. **Stage 2b & Stage 3 (Lazy Triangles & Lazy BVH, L2114–2161):** Builds `local_tris` only when Stage 2 passes (`_build_fast_triangles(..., budget=budget)` with per-triangle checkpoints), translates with `_translate_triangles` (`surface_proximity_triangle_prepare` checkpoints + `prepared_triangles` ticks), and builds `local_root` BVH **only** when `need_trees and nl * nr > LINEAR_PAIR_LIMIT` (`_translate_bvh` charges per-node `surface_proximity_surface_bvh_build` checkpoints).
  - Records separate counters: `mesh_cache_hits`, `mesh_cache_misses`, `mesh_cache_tree_builds`, `mesh_cache_tree_build_units`, `mesh_cache_tree_reuses`, `mesh_cache_translate_units`, `mesh_cache_fallbacks`.

#### Verification ([verify_review_suite.py](verify_review_suite.py#L309-L454))
- **Batch Equivalence:** G508 (`11` pairs, forward and reversed peer order), D48 (`47` pairs), and G508 all-pairs (`66` pairs) match uncached `_surface_sig` identically (`10` reuses / `12` physical builds on G508; `46` reuses / `48` physical builds on D48; `120` hits / `12` builds / `9622` translate units on 66 pairs).
- **Linear & Fallback Skip:** `12×12` control (`nl * nr = 144 <= 256`) builds `0` trees (`"tree" not in entry`). `17×17` `ldexp(1.0, -520)` pair triggers `mesh_cache_fallbacks=1`, `mesh_cache_tree_builds=0`, and identical `validated_faces` / `referenced_vertices` counts vs uncached.
- **Budget Isolation & Cancellation Atomicity:** Pair 2 starting at `MAX_WORK_UNITS - 10` still refuses cleanly (`surface_work_budget`) even with `iso_cache` warm from Pair 1. Injecting cancellation on `validated_faces`, `referenced_vertices`, `triangle_prepare`, and `surface_bvh_build` leaves no poisoned entries — immediate retry against the same `bad_cache` produces exact match to uncached oracle.
- **Mutability Guard:** Unsealed `SimpleNamespace` with mutable `list` vertices re-evaluates accurately (`1.0 -> 2.0`) after in-place coordinate mutation.

---

### BVH-R03 (P2) — SAH Local Tree Translation/Scaling Non-Isomorphism

#### Geometric & Algorithmic Distinction
In [`_build_sah_bvh`](../human_eye_plugin/surface_geometry.py#L170-L282), bin index assignment uses `((cx - cmin) * 12) // (cmax - cmin + 1)`. Because of the `+ 1` integer denominator adjustment, uniform dyadic rescaling $x \mapsto x \cdot 2^{\Delta e}$ changes `+1` relative to `cmax - cmin`, which can alter bin boundaries and split choices between a local-frame tree and a pairwise-frame tree.

However, triangle indices still form an exact partition across leaves, and [`_translate_bvh`](../human_eye_plugin/surface_proximity.py#L1954-L1977) applies the exact affine map $(\text{lo} \ll \Delta e) + \mathbf{t}$ and $(\text{hi} \ll \Delta e) + \mathbf{t}$ to every node's conservative integer bounds. Thus bounding soundness ($B_{\text{parent}} \supseteq \bigcup_{\text{child}} B_{\text{child}}$ and leaf inclusion) holds identically regardless of split order.

#### Verification ([verify_review_suite.py](verify_review_suite.py#L457-L523))
- Checked `diff_exponents_distant_shift` ($2^{-28}$ vs $2^{-4}$ shifted by $2^{20}$ across 12-bin transition) and `thin_sheet_distant` ($1024$ shift, $1\text{ }\mu\text{m}$ separation):
  - Full `_surface_sig` (distance, exact rational squared key, witnesses, directions, `witness_triangle_indices`) is identical (`equivalent=True`, `work_off=784`, `work_on=784`; `thin_sheet_distant`: `work_off=14278`, `work_on=14278`).
  - `_check_bvh_invariants` confirms `node_count`, `count == left[2] + right[2]`, parent-contains-child on every axis, and exact `set(range(n_tris))` leaf partition on both local and pairwise trees.

---

### BVH-R04 (P2) — Algebraic Degree, Bit-Width Bounds & 500-Bit Domain Verification

#### Distinction: Stored vs Unbounded Scratch Quantities
Python integers in the `fast_ints` path ([surface_proximity.py#L57-L125](../human_eye_plugin/surface_proximity.py#L57-L125), [L553-L698](../human_eye_plugin/surface_proximity.py#L553-L698)) operate in exact arbitrary precision (never truncating). The fast path is admitted only when every prepared integer coordinate satisfies $|c| < \text{\_FAST\_COORD\_LIMIT} = 2^{500}$ (checked via `_bounds_fit_fast`, or in cache Stage 2 via `< 490`-bit margin).

Let $B = 500$ be the coordinate bound $|c| \le 2^{500} - 1$ ($\le 500$ bits). Exact worst-case algebraic degrees and observed bit widths from `verify_r04_bit_domain_and_predicates` (`b_val = (1 << 499) - 1`, stored coordinate max bits $= 499$) are:

| Quantity | Formula / Location | Algebraic Degree in Coords | Analytical Worst Case ($|c| < 2^{500}$) | Empirical at `b_val = 2^499 - 1` | Bounded / Enforced Where |
| --- | --- | --- | --- | --- | --- |
| Prepared vertex coords $p_k$ | `_prepare_triangles_from_relative` | $1$ | $\le 500\text{ b}$ | `499 b` | Admitted by `_bounds_fit_fast` ($< 2^{500}$) |
| Edge / point deltas $q, d_1, d_2, u, v, w$ | `_build_fast_triangles`, `_point_faces`, `_edge_edges` | $1$ | $\le 501\text{ b}$ | `499 b` | Implicitly $\le B+1$ |
| Triangle / edge cross normal $\mathbf{n}$ | `_normal`, `ny*vz - ...` | $2$ | $\le 1003\text{ b}$ | `998 b` | Exact Python `int` |
| Squared lengths `squared`, `dd`, `det` | `nx*nx + ny*ny + nz*nz` | $4$ | $\le 2008\text{ b}$ | `1996 b` (`normal_squared`, `det`) | Passed to `_closer(..., best)` |
| Plane height $h = q \cdot \mathbf{n}$ | `_point_faces`, `_edge_edges` | $3$ | $\le 1506\text{ b}$ | `1497 b` | Exact Python `int` |
| Squared height $h^2$ | `hh = height * height` | $6$ | $\le 3012\text{ b}$ | `2994 b` (`hh_numerator_bits`) | `_closer` reduces & checks `<= MAX_BITS (4096)` |
| Barycentric vectors `c1, c2` & `u, v` | `_fast_bary` (deg 3), `u, v` (deg 4) | $3, 4$ | $\le 1505\text{ b}, 2008\text{ b}$ | `1497 b`, `1996 b` | Sign/sum check `u >= 0, v >= 0, u+v <= sq` |
| Point-edge numerator $q^2 \cdot d^2 - (q \cdot d)^2$ | `_point_edges` | $4$ | $\le 2008\text{ b}$ | $\le 2008\text{ b}$ | `_closer` (`denominator = dd <= 2006b`) |
| **Unbounded scratch** $h^2 \cdot \text{best\_d}$ / `lhs, rhs` | `_closer` L537–547, `_point_faces` L567 | $6 + 4 = 10$ (within fast); up to $4096 + 3012$ against prior GCD'd `best` | $\le 5020\text{ b}$ (both fast deg-4/6) or $\le 7108\text{ b}$ (general) | **`4990 b`** (`scratch_hh_x_det_bits`) | **Unbounded scratch before comparison**; never stored directly! |
| **Stored result** `numerator, denominator` | `_closer` L541–549 ([surface_proximity.py#L533-L550](../human_eye_plugin/surface_proximity.py#L533-L550)) | $\le 6$ reduced via `gcd` | Stored checked against `MAX_BITS = 4096` | Fits `<= 4096` (`true`) | Wait: **`_bounded` checks both `denom == 1` and reduced `_ratio` (`_Work`/output $\le 4096\text{ b}$)** |
| Projection axis `ax, ay, az` | `_FastWitnessProjection.build` ([L981-L997](../human_eye_plugin/surface_proximity.py#L981-L997)) | $1..4$ reduced by `gcd` | Checked `<= 1024 b` per component | Bounded $\le 1024\text{ b}$ | Exceeding `1024 b` returns `None` cleanly |

> **Important Clarification:** Earlier shorthand (`7 * 500 + 16 <= 4096`) understated cross-product scratch integers like `hh * best[1]`. In reality, `_point_faces` (`hh` up to `3012 b` for fast inputs), `_closer`, and `_aabb_exceeds_best` deliberately perform exact cross-multiplication in Python's arbitrary-precision scratch integers (`4990 b` observed at 499-bit span), while **only** stored distance rationals (`<= 4096 b` in `_bounded`) and `_scratch` (`_MAX_SCRATCH_BITS = 8193 b` for `_plane_exceeds_best` / `_rounded_distance`) are bounded. Furthermore, `_closer` checks reducible ratios (`big_n / big_d` exceeding 4096b before GCD) via `_ratio` GCD first, and rejects irreducible $>4096$-bit integers even when `denominator == 1` (`closer_4097_error == "surface_exact_bit_budget"`).

#### Verification ([verify_review_suite.py](verify_review_suite.py#L526-L629))
- Exact binary64 span crossings match independent pure-`Fraction` oracle `_exact_mesh_sq_oracle`:
  - `499bit_span`: `fast_ints_used=True`, `oracle_match=True`
  - `500bit_span_fast_limit`: `fast_ints_used=True`, `oracle_match=True`
  - `501bit_span_slow_fallback`: `fast_ints_used=False`, `oracle_match=True`
  - `subnormal_dyadic` ($2^{-1070}$, $8\times 10^{-323}\text{ m}$): `fast_ints_used=True`, `oracle_match=True`
  - `huge_origin_2pow900` ($2^{900}$ origin): `fast_ints_used=True`, `oracle_match=True`
  - `point_vs_point`, `collinear_vs_collinear`, `1_ulp_gap` ($2.220446049250313\times 10^{-16}\text{ m}$): all `oracle_match=True`
  - `_closer` reducible $>4096$-bit GCD reduction (`6 * 2^4096 / (2 * 2^4096) == (3, 1)`), and irreducible `2^4096 + 1` raising `surface_exact_bit_budget`.

---

### BVH-R05 (P2) — Canonical Tie-Breaking & Conservative Pruning Bounds

#### Soundness Criteria Verified
- When `strict = (cand_min_pair < best_pair)`: subtree/triangle contains a pair capable of beating `best_pair` on exact ties, so pruning requires squared lower bound $L > B = \text{bn}/\text{bd} \iff L > \lfloor \text{bn}/\text{bd} \rfloor = \text{best\_floor}$ ([_aabb_exceeds_best](../human_eye_plugin/surface_proximity.py#L728-L745)).
- When `strict = False`: subtree/triangle cannot win an equality tie, so pruning holds on $L \ge \text{bn}/\text{bd} \iff L > \lfloor (\text{bn}-1)/\text{bd} \rfloor = \text{tie\_floor}$.
- Same exact strictness applies to `_plane_exceeds_best` ([L748-L762](../human_eye_plugin/surface_proximity.py#L748-L762)) and `_FastWitnessProjection.cutoff_strict` / `cutoff_tie` via `isqrt((norm_sq * bn) // bd)` and `isqrt((norm_sq * bn - 1) // bd)` ([L996-L997](../human_eye_plugin/surface_proximity.py#L996-L997)).
- Global `break` in `_nearest_tree` ([L1603-L1608](../human_eye_plugin/surface_proximity.py#L1603-L1608)) is guarded by `shift == 0` AND `key > best_floor` (strictly greater, never `>=`), because `key` is an exact unshifted integer AABB lower bound ordered monotonically in the min-heap. When `shift > 0`, `break` is never executed ([L1614-L1621](../human_eye_plugin/surface_proximity.py#L1614-L1621)).

#### Verification & Honest Caveat ([verify_review_suite.py](verify_review_suite.py#L632-L788))
- Verified exact match to `_exact_mesh_sq_oracle` (both exact distance squared AND canonical lexicographical `witness_triangle_indices`) on:
  - Multiple exact zero-distance contacts (`zero_contact_tie_pair == [0, 4]`),
  - Non-integer `tie_floor` boundaries (`(1, 1)` vs `(3, 2)` in `_aabb_exceeds_best`),
  - `LINEAR_PAIR_LIMIT` boundary (`16×16 = 256` linear vs `17×16 = 272` tree + `20×20`), with RNG-shuffled face order and `left`/`right` swap invariance,
  - Forced `shift > 0` (`1 << 4095` span) yielding exact `[0, 0]`,
  - Equidistant multi-tie grids (`cube192` -> `[32, 0]`, `shuffled_multi_tie_20x20` -> `[0, 18]`, `rotated_tie_36x36` -> `[0, 35]`).
- **Caveat observed in `CORRECTNESS_AND_BOUNDARY_RESULTS.json` (`r05_tie_pruning_and_subtree_oracle`):** Although `subtree_pruned_pairs` fired heavily on those 3 audited tie cases (`36856`, `396`, `1266`), the hook on `_FastWitnessProjection.prunes_nodes` recorded `wp_subtrees_exhaustively_audited = 0` on those three synthetic meshes because AABB heap/push `best_floor`/`tie_floor` bounds pruned every distant node pair before `_FastWitnessProjection.prunes_nodes` ran. `_FastWitnessProjection.prunes_nodes` itself IS exercised and verified against the exact oracle across nonconvex/coiled/real pairs in `r01_fast_projection` (e.g., `G508_Peer_000`: `wp_pruned=1302`, `G508_Competing_001`: `73`, `D48_Peer_000`: `193`, all matching `proj_on == proj_off`), leaving zero discrepancy against exact `off`-projection ground truth, while synthetic tie cases that reach `prunes_nodes` under strict vs non-strict tie cutoffs remain tested specifically at unit level + `r01` projection-on/off equivalence.

---

### BVH-R06 (P2) — SAH Complexity, Sub-Phase Timing & Strategy Sensitivity

#### Accounting & Depth Clarification
- `tree_builds` and `tree_build_units` (`_build_sah_bvh` charges `1 + n` per node via `budget.consume(1 + n, 'surface_bvh_build')`, [surface_geometry.py#L145](../human_eye_plugin/surface_geometry.py#L145)) remain cooperative-cancellation guarded per node.
- `_SAH_MAX_DEPTH = 20` ([surface_geometry.py#L140](../human_eye_plugin/surface_geometry.py#L140)) bounds only the 12-bin SAH splitting stage; once `depth >= 20` or `n <= _SAH_MIN_N (12)`, construction falls back cleanly to exact median longest-axis splitting ([L283-L292](../human_eye_plugin/surface_geometry.py#L283-L292)), so overall worst-case tree depth is bounded by `20 + ceil(log2(MAX_FACES))` (`MAX_FACES = 4096`), not `20`.

#### Sub-Phase Breakdown & Median/SAH × `leaf_size` Evaluation ([run_ablation_and_assets.py](run_ablation_and_assets.py#L626-L743))
From `ALGORITHM_ABLATION.json` (`r06_subphase_and_tree_quality` and `s3_cumulative_and_loo_ablations`):
- **Heavy nonconvex overlap (`G508_Peer_000`):**
  - `median_ls2`: `build=10.60 ms`, `compile=0.51 ms`, `traverse+narrow=192.21 ms` (full query median `224.56 ms`).
  - `sah_ls2` (default): `build=22.21 ms`, `compile=0.64 ms`, `traverse+narrow=71.40 ms` (full query median `104.40 ms` -> **`2.15×` net speedup** vs `median_ls2`; leaf visits `15607 -> 3205`).
  - `sah_ls4`: `median=98.33 ms`, `leaves=8245` (`work_units=60627`).
  - `sah_ls1`: `median=114.44 ms`, `leaves=1211` (`work_units=69640`).
- **Light / sparse curved shells (`HighRes_1536F_Pair`, 1536×1536 separated):**
  - `median_ls4`: `build=30.58 ms`, `compile=1.10 ms`, `traverse+narrow=14.35 ms` (full query median `67.74 ms`, `work_units=57321`).
  - `sah_ls2`: `build=74.91 ms`, `compile=1.80 ms`, `traverse+narrow=13.83 ms` (full query median `110.04 ms`, `work_units=60847`).
  - Same pattern on `Sheet_Dented_2mm` (`med_ls4=17.15 ms` vs `sah_ls2=27.21 ms`) and `Rotated_30deg_Spheres` (`med_ls4=11.97 ms` vs `sah_ls2=16.72 ms`).
  - Crucially, vs `A` (`032` baseline: `HighRes=138.46 ms`, `Sheet_Dented=45.58 ms`, `Rotated=27.69 ms`), default `sah_ls2` STILL beats `A` cleanly on every single one (`1.26×–1.68×` in ablation, `1.27×–1.77×` in main 7-rep table), while remaining a simple, uniform default without introducing unrequested auto-tuning heuristics.

---

### BVH-R07 (P2) — Closed Solids / Self-Intersection Truth Coverage & Memory Attribution

#### Correctness Expansion ([verify_review_suite.py](verify_review_suite.py#L791-L945))
- **`classify_closed_solids`:** Verified on `Obj_001` vs `Obj_024` from real 24-part `BASE_SNAPSHOT.json` (`relation="penetrating"`, `certificate="disjoint_boundaries_with_exact_parity"` for strict containment), piercing boxes (`"penetrating"`), and G508 nonconvex overlapping-AABB controls (`"separated"`).
- **`analyze`:**
  - All 6 `shared_simplex_cases` from `DESIGNED_CASES.json` match `legal_contact` (`0` for legal noncoplanar/opposite-coplanar edge and shared vertex; `>=1` for same-side coplanar overlap and transverse crossings).
  - `near_m = 0.001` tested on **both sides** of threshold: `0.5 mm` gap (`within_0p5mm_total=1`) vs `1.5 mm` gap (`outside_1p5mm_total=0`).
  - Collinear degenerate triangle reported explicitly in `degenerate_triangles == [0]`.
  - `>128`-region truncation (`150` intersecting strips) matches baseline `arm_a_032` identically (`truncated_150_regions_matches_032=True`).

#### Memory Attribution (`2.46×–2.95×` Traced Peak on `Analyze_Tube_668F`)
`tracemalloc` snapshots comparing `032` vs `C` on `Analyze_Tube_668F` (`668` triangles, `near_m=0.0`):
- Peak traced Python allocations: `032 = 255,112 B` -> `C = 627,824 B` (`2.461×`, and `212,424 -> 627,232 B = 2.95×` in the benchmark loop; peak inside `_build_sah_bvh` hit `647,292 B` with hook active).
- Top allocation sites in `C`:
  1. [surface_geometry.py:166-167](../human_eye_plugin/surface_geometry.py#L166-L167): SAH BVH node `(lo, hi)` tuples (`419 + 419` blocks, `30,168 + 30,168 = 60,336 B`),
  2. [surface_geometry.py:357](../human_eye_plugin/surface_geometry.py#L357) & [:28](../human_eye_plugin/surface_geometry.py#L28): precomputed triangle `points` & `normals` lists kept live alongside `tri_sets` (`18,144 + 18,144 = 36,288 B`), plus intermediate BVH recursion slices and precomputed per-face tuples holding memory live simultaneously during tree construction (`553,632 -> 647,292 B`).
- This ~`415 KB` absolute increase buys a `1.66×` speedup on `Analyze_Tube_668F` (`323.54 -> 194.83 ms`, `node_pair_visits` `8614 -> 4550`, `leaf_pair_visits` `19294 -> 13272`), well below any memory risk on bounded `4096`-triangle meshes.

---

### BVH-R08 (P2) — Comparator Hardening, Expanded Gates, Telemetry Separation & Negative Controls

#### Changes Implemented in [benchmarks/bvh_eval.py](bvh_eval.py#L437-L1073)
1. **Strict Comparator (`_compare_signatures` & `_canonical_row_sig`, L848–922):**
   - Schema bumped to `m3-bvh-eval-v2` (preserving original `baseline_032.json` and `opt_bvh_final.json` untouched on disk).
   - Validates all 6 required sections (`surface_single`, `spatial_relation`, `closed_solid`, `surface_analyze`, `e2e_entries`, `surface_batch`).
   - Rejects **both** missing baseline workloads (`partial=False`) and **extra candidate-only workloads** (even when `partial=True`).
   - Validates `input_sha256`, `batch_ids` exact order & length (rejecting truncated prefix matches), canonical `spatial_relation` (`spatial` + `surface` + top-level/nested consistency), complete `closed_solid` / `surface_analyze` (`status`, `total`, `regions`, `degenerate_triangles`), and complete `e2e_entries` (`nearest_ids`, `distance_m`, `unresolved`, `excluded`, `measurement_notes`, `best_known_evidence`, `coverage`, `dispositions`).
2. **Separated Instrumentation (`_time_fn`, L529–570):**
   - Runs warmup + timed `perf_counter_ns` repeats with `raw_samples_ms`, `median_ms`, `iqr_ms`, `min_ms`, `max_ms`, and notes small-$N$ `p95_note`.
   - Measures `cpu_time_ms` (`process_time_ns`) and `tracemalloc` peak memory (`peak_alloc_bytes`) in **separate** un-timed calls outside the wall-clock loop.
3. **Expanded Correctness Gates (`run_correctness_gates`, L573–656):**
   - Covers `G508` oracle + `witness_oracle` membership, all 14 `sufficient_separation` pairs checking `relation`, `certificate`, and `distance_m`, `work_boundaries` (`MAX_WORK_UNITS` exact accept and `+1` `surface_work_budget` refusal), `static_face_limit` (`MAX_FACES + 1` refusal), and collaborative cancellation across 3 core stages.
4. **Negative Controls (`verify_comparator_negative_controls`, L925–993):**
   - Verified via `bvh_eval.py --verify-comparator`: `passed: True, controls_checked: 13`, catching all 13 injected failure classes (missing workload, extra candidate workload under full & partial modes, truncated batch, prefix-match partial batch, swapped batch order, changed spatial relation, changed spatial certificate, shifted witness point, altered nearest `measurement_notes`, altered scan disposition distance, altered `analyze` regions, altered `analyze` `degenerate_triangles`).

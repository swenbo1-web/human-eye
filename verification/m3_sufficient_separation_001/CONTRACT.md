# Frozen spatial relation contract

This contract is fixed before product edits and product execution for M3-SUFFICIENT-SEPARATION-001. The starting product is 3beb3f809674658b086e50af194adaa16e226111, 137 sources with canonical SHA256 0770602e875c819dd424639fd7c750aaad4bca3bbe506aaf747ba337e5991139.

## Explicit facts and requests

The new requested fact is spatial_relation. Its measured value is one of separated, touching or penetrating. Unknown retains a null value and a specific reason. A successful strict support certificate establishes separated for the union of all represented triangles and the convex hulls of their referenced vertices. It makes no embedded-shell qualification assertion. The geometry scope is referenced_triangle_unions_and_their_vertex_convex_hulls. Unreferenced loose vertices and independent edges lie outside this fact's scope.

The support method is exact_sufficient_spatial_relation_v1 and the certificate category is strict_all_referenced_vertex_support. Support evidence contains the proposal policy, primitive direction, exact two support extrema and their source vertex indices, referenced vertex counts, and the common integer frame origin and factor. Projected support quantities are integer proof values. Actual surface gap uses the existing surface distance.

Fallback can supply separated, touching or penetrating only from a valid original closed classifier result. It carries the original classifier's actual scope and certificate. Invalid or unresolved fallback produces unknown. An optional certificate failure alone supplies no collision classification.

Task sets explicitly requesting spatial_relation and surface_proximity use task-query-set-v2. Existing closed_solid_relation plus surface_proximity requests retain task-query-set-v1. A mixed request may ask for both relation facts. Its summary uses spatial_relation, while its overall status includes every explicitly requested fact. A still-unknown explicit closed fact keeps that overall result partial. Single ordered-pair queries may request the new fact through the existing generic task-query-v3 facts envelope.

The existing scene-observe tool supplies the opt-in. The compact relation tool retains its existing parameters and default request. The collection binding and ranking implementation is shared. Unknown candidates remain in completeness accounting. Positive surface distance alone supplies no spatial classification.

## One direction and complete support

First execute the existing surface nearest solver once. Propose exactly the difference between that call's finite public nearest points, B minus A. Convert each public binary64 value to its exact dyadic rational before subtracting. Convert the resulting direction to a common dyadic integer vector, reduce it by a positive gcd and keep its sign. No axis search, alternate witness search or oracle direction is allowed.

Reuse the integer coordinate dictionaries already created by the existing pair frame. Retain every source index referenced by any triangle, including interior collinear vertices omitted from a degenerate triangle's reduced hull representation. Each such source index is visited once per support pass. Compute exact max_A(n dot v) and min_B(n dot v). Strict min_B greater than max_A proves separation through the convex-combination property. Equality remains unresolved by this certificate.

The two support extrema suffice for the proof. Their difference need not be constructed if it would enlarge the optional arithmetic domain. No normalized projection distance is substituted for the original surface nearest distance or exact rank.

## API and preparation

The new core entry measure_spatial_relation returns a JSON-safe bundle with measurement_valid, surface, spatial and closed. The top-level flag requires valid surface and spatial results. The optional closed result records an actual fallback invocation. A private query-local holder carries pair, work, full referenced coordinates and any world trees. Those runtime objects are excluded from cached results.

The original surface entry gains an optional private prepared holder. The integer-frame function can retain its already computed coordinate dictionaries. World trees can be returned when they are actually built. The original closed classifier gains only optional source-bound pair/tree preparation wiring. Its tree, cone and geometric algorithm remain fixed.

The new ordered-pair memo uses a distinct semantic version and includes source, units, frame and exact-rank demand. The old closed and surface memo versions remain intact. Mixed requests reuse an already executed fallback result. A support success followed by an explicitly requested closed fact runs that original classifier once. A memo hit has fresh current-call counters and retains current capture binding.

## Work and stopping rules

Distance and support share the same original surface Work instance and the 1,179,648-unit limit. Full narrow-pair limit remains 16,384. Support charges one support_direction_components unit per axis, one support_source_vertices unit for each unique referenced vertex enumeration and extrema update, and one support_vertex_dots unit for its actual exact dot product. A completed support pass therefore adds 2 times the referenced vertex count plus 3 work units. Reused coordinate dictionaries and world trees are already charged by their original preparation.

Surface or support work exhaustion, static admission limits and full-leaf exhaustion retain unknown and perform no fallback. Their counters are not reset. The bundle reports budget_stopped so a mixed request also leaves any unexecuted closed fact unknown at this same pair boundary. Original v1 requests continue their original independent path. The legal fallback conditions are zero or unavailable proposed direction, nonpositive strict support gap, or failure of the optional support arithmetic within the existing exact-bit domain. The closed path has its original pre-registered 262,144-unit, 16,384-pair and 16,384-ray boundaries and is invoked at most once. Original checkpoints and the request deadline propagate throughout. Cancellation and deadline exceptions are not fallback conditions.

The exact arithmetic bit limit remains 4096 and scratch limit remains 8193. The first candidate includes no zero-contact shortcut, distance-order adjustment, closed-tree tuning, topology patch or query-level single-shell cache.

## Fixed experiments

The QA design freezes all analytic counterexamples before execution. They cover separated/open/self-intersecting triangle sets, referenced remote extrema, unreferenced loose vertices, containment with positive surface distance, intersecting convex hulls with separated nonconvex shells, touching/zero direction, strict tiny gaps, large coordinates, candidate order and ties, mixed unknown completeness, source invalidation, reuse, cancellation, optional numeric fallback and actual work limits.

The finite timing consists of exactly 60 calls. Main G508 three pairs and the simple two-box control contribute 40 calls. Simple intersecting bars and complete containment contribute 20 calls. Each case has five alternating reference/candidate pairs and fresh input objects and holders, with no cross-call memo. The reference is the previous frozen fac9b437 diagnostic baseline with exactly its three original quantity overrides. Its original AABB pruning, leaf arithmetic, precision and 30-second deadline remain.

Each timing deadline starts at that call's earliest input preparation and remains in force through serialization. Source loading is measured separately. Input preparation, query preparation, solving, serialization and the complete window have explicit anchors. The primary samples have no additional function spies or per-checkpoint dictionaries. Product counters and the original deadline callback remain active. One separate fixed non-timing observation measures actual function work.

G508 summed complete-business medians must improve by at least 20 percent and each pair must avoid regression. Simple control permits at most max(1 ms, 5 percent) additional median cost. Each fallback control permits max(2 ms, 10 percent). Reference and candidate provide the common business facts with different additional shell guarantees, which must be disclosed.

After an initial candidate, review actual remaining cost and code once. At most one evidence-led substantive simplification is allowed. Then freeze one candidate commit and build one isolated installation. The actual MCP business sequence is directory, new explicit spatial assembly, old v1 assembly, new control. New spatial assembly runs first. Preserve the old v1 unknown result and all prior failures. Source, actual input, public witnesses, independent answers and process cleanup are verified together. Completion or fixed failure returns to the administrator for independent review.

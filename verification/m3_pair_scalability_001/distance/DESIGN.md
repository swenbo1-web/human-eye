# Surface distance candidate design

This document fixes the proposed surface implementation before source editing. Product editing awaits the root's frozen-budget authorization. The current public exact binary64 distance, original-surface witness and exact rank semantics continue through the existing leaf formulas.

## Admission and work

Static admission retains nonempty surfaces, total faces at most 4096, valid referenced indices and the current exact coordinate/bit checks. The theoretical face-product refusal is removed. Actual full narrow-phase leaf entries are bounded at 16384. Total logical work is bounded at `4096*32 + 16384*64 = 1179648` units.

The old admitted pair performs at most six point-face, eighteen point-edge and nine edge-edge feature tests. Coplanar convex clipping has at most fifteen charged polygon slots across its three clipping stages. Full-leaf entry, intersection, AABB and plane projections fit the remaining per-pair allowance. The face allowance covers at most three referenced vertices per face, validation, triangle preparation and balanced tree construction, including the existing per-node descendant aggregation charges. These units bound recorded logical operations, with the existing deadline additionally bounding elapsed execution. They do not count every Python instruction or bit operation.

`_Work.tick` and compatible `consume` charge preparation, build, queue, node, leaf, bounds, plane projections, features and clipping predicates. Budget exhaustion returns the existing unknown result shape with explicit `surface_work_budget` or `surface_pair_budget`. No incomplete search publishes a complete distance or rank key.

## Traversal and bounds

The fixed linear threshold is a face product of 256. That path retains original iteration, AABB rejection and first-witness behavior. Both paths use the same full-leaf kernel. The larger path uses the existing exact world-integer AABB tree representation and a near-first node-pair heap. No overlap-only candidate enumerator is used for positive distances.

Heap ordering uses squared integer box-gap distance. Extremely wide integer frames apply one common right shift solely to queue priorities, keeping priority temporaries within the existing 8193-bit scratch allowance. Every safe rejection still uses the original unshifted exact AABB comparator. Priority coarsening never certifies rejection.

At a leaf, prepared normal and triangle coordinates provide signed plane distances. For distances strictly sharing either sign, let `g` be the minimum absolute value and `n2` the plane normal squared. The exact strict bound test is `g > isqrt((best_n*n2)//best_d)`. This is equivalent to `g*g/n2 > best_n/best_d`. Both multiplicands have at most 4096 bits, so the sole cross-product fits 8192 scratch bits. Equality remains available. Degenerate normals and triangles straddling the plane supply no plane certificate. A successful first-side bound avoids computing the other side.

The first upper bound comes from a real evaluated full leaf. AABB and plane bounds never supply an actual distance. A global best additionally carries the original ordered triangle indices. Equal-distance later search results replace it only when their `(left_index,right_index)` precedes the current pair. Within one pair, the original feature order and strict improvement preserve its first attaining witness. Tree search completes all unpruned ties, including zero-distance ties.

## Shared preparation

The existing prepared-pair five-tuple remains intact. A query-local holder may additionally contain `trees={pair: prepared_pair, bounds:(left,right), roots:(left,right)}`. Surface accepts this through `_prepared_trees` only for the identical prepared-pair object. These are the original world-integer bounds. A separate projected tree used by closed-shell candidate enumeration cannot serve as a Euclidean distance bound.

The shared helper `_plane_distances(points,origin,normal,budget)` calculates one side. `_intersection` gains an optional keyword `plane_distances=(da,db)`. A missing side is computed by its existing exact formula, and an available side is reused. Closed-shell cheap certificates and surface-distance bounds can share these current-leaf values without another cache.

## Diagnostics

Existing counters remain. New fields include `work_units`, `prepared_triangles`, `tree_builds`, `tree_build_units`, `node_pair_visits`, `leaf_pair_visits`, `queue_pushes`, `queue_bound_tests`, `narrow_phase_pairs`, `plane_projection_tests`, `plane_bound_tests`, `plane_pruned_pairs`, `shared_trees` and `subtree_pruned_pairs`. `triangle_pairs` keeps actual leaf-candidate visits, including leaf-level AABB rejection. Bulk subtree pair coverage is reported separately and does not count as executed geometry work. Original leaf `intersection_tests` remains the comparable expensive-leaf count, including degenerate feature leaves.

The frozen Peer reference is 18791 expensive leaf entries with its original AABB early-out. The candidate acceptance ceiling is 9395. Full Cartesian size 258064 is a separate coverage quantity. The existing public method string may remain because the exact leaf/rank contract is unchanged, while the root updates private pair-memo versions.

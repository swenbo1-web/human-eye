# 047 independent source proof

This is an offline source/count argument for the unchanged installed A=032 and C=043. It does not import or execute either kernel. The accompanying certificate pins exact files and function text/line numbers. D is excluded. All inequalities are conservative, including charged work that a particular successful run will never perform simultaneously.

## 1. Precise unique-obligation statement

Let `n,m > 0` be the two admitted **original triangle-row counts**, `P=nm`, and `F=n+m`. A row remains a separate obligation even when its coordinates duplicate another row or its hull degenerates. `_admit` appends each source row once; integer-frame preparation constructs exactly one descriptor for each admitted row. It can reduce the hull of one degenerate triangle, but does not merge or reorder source rows.

For one successful or stopped `_nearest` invocation, each original pair `(i,j)` can enter `_nearest_pair` at most once. The statement is per invocation, not per object pair over a service lifetime, not per bundle of queries, and not per repeated host capture.

* Linear: nested original-row loops enumerate `(i,j)` in lexicographic order once. Pruning or zero-distance return deletes work and never revisits a row.
* A tree: every tree node owns a set of source IDs. Every internal split has two disjoint, nonempty child sets whose union is the parent. Splitting either side of `S×T` creates two disjoint rectangles with union `S×T`. Each child rectangle is enqueued once. There is no re-enqueue of an ancestor or a parent after its children.
* C greedy seed: the selected child continues the descent; exactly its unselected sibling rectangle is appended. The seeded terminal rectangle and all saved siblings partition the root rectangle. The seed is evaluated once and **is not re-enqueued**. Each sibling enters the same one-pass heap traversal as above. Changing priority does not change this partition invariant.
* Projection, AABB, plane and tie pruning only remove a rectangle or an unvisited row pair. No projection path calls `_nearest_pair` to manufacture a direction.
* Validated reused trees and translated cached trees preserve the same original row-ID partition. A stale or caller-forged private `prepared_trees` dictionary is outside this statement. Normal identity guards must hold; private dictionaries are not arbitrary public inputs.

If the conceptual unpruned product traversal has `L` terminal rectangles, `L ≤ nm`; its binary recursion has `2L−1 ≤ 2P−1` node occurrences. This counts a node pair by its owned rectangle, not by geometric box equality. Equal boxes do not imply a duplicate obligation.

It follows that a fresh distance invocation has `narrow_phase_pairs ≤ P`. Therefore `P ≤ actual_remaining_narrow` is a sufficient **narrow-cap** condition. It does not establish any other budget or that the returned result is known. 129×129 is 16,641 and is outside the 16,384 cap certificate; 125×125 is inside this narrow-only certificate. Their actual original results remain independent evidence.

## 2. Charged leaf upper bound

Use a deliberately loose bound of 75 work units per potentially visited native triangle pair:

| Charged operation | Upper bound |
|---|---:|
| leaf visit and triangle AABB entry | 2 |
| plane dots across both plane-bound and narrow layers | 12 |
| plane-bound entries | 2 |
| narrow admission and intersection entry | 2 |
| coplanar clipping predicate entries | 24 |
| point-face entries | 6 |
| point-edge entries | 18 |
| edge-edge entries | 9 |
| Total | 75 |

The clipping bound requires no unproved convex-polygon complexity claim. Each input polygon vertex emits at most two output entries. Before three clipping passes the lengths are at most 3, 6, and 12; the charged `1+len(polygon)` sums to at most 24. Deduplication and empty polygons only reduce it. Feature helpers contain no nested work charges beyond these entries. Degenerate point/segment hulls have fewer features. Some rows of this table are mutually exclusive; keeping all is safe.

For the linear path there is no BVH, heap or optional projection. Admission costs F; referenced vertices cost at most 3F; prepared triangles cost F. Up to four final rounded/exact native witness membership entries are reserved. Thus:

`U_linear = 75P + 5F + 4`, valid for the original `P≤256` linear dispatch.

## 3. Tree, preparation and settled credit

For C, ordinary node visits, heap pushes and child queue-bound entries are each bounded by 2P. Reserving another 2P for shifted enqueue bounds and 2P for shifted dequeue bounds gives ordinary tree work at most 10P. Unshifted traversal pays less; the reserve is retained.

The query-local projection account starts at zero. Every admitted optional attempt uses `try_run`, requires both settled credit and the original remaining total-work margin, and finally debits actual `_Work` delta. All failed builds/intervals are paid. No residual balance is carried to another query.

Earned bound credit is at most 2P. Strict triangle projection exclusions are disjoint original-row obligations and each earns at most 35. Node exclusions remove disjoint rectangles and earn at most twice their source-pair cardinality, including the singleton special case. Therefore:

`earned ≤ 2P + 35P + 2P = 39P`, and `optional_spent ≤ earned ≤ 39P`.

This is a deliberately loose independent upper bound. It does not add hypothetical descendant feature savings or assume that actual A and C traverse the same order. It does not equate credit with unspent total-work capacity.

The C SAH builder consumes exactly `1+s` per node owning `s` source faces. Children are nonempty. With leaf capacity two, the worst one-versus-rest recurrence is `T(1)=2`, `T(2)=3`, `T(s)=s+1+T(1)+T(s−1)`. Hence `T(s)≤s²+s`. The SAH depth cap then median fallback also prevents an unbounded skew recursion. Flattening/compilation performs checkpoints but has no additional abstract `_Work` charge; it still costs real CPU/time.

Fresh preparation is at most 5F. Tree-bound preparation adds F+2; the two builders add at most `n²+n+m²+m`. Final provenance reserves four entries. Therefore a sufficient **abstract total-work** inequality for the distance invocation is:

`U_tree = 124P + n² + m² + 7F + 6 ≤ actual_remaining_work`.

The same loose bound also dominates the original A distance path; C's extra reservations need not be spent by A. This is a proof about charged units, not an estimate derived from a measured low-water mark.

## 4. Reuse, cache, shared paths and ambient data

Ordinary C mesh-cache hits recharge admitted faces, referenced vertices, prepared triangles and stored BVH construction units. A warm cached tree is not free work for this theorem. Cold local-frame construction and affine fallback do not re-run face admission; the fallback reconstructs prepared descriptors once. Translation changes coordinates but preserves IDs. The formula conservatively reserves fresh charges even where a validated prepared pair/tree has already been paid elsewhere.

A whole-result cache hit has zero new distance invocation; its geometry/source contract and prior result validity must still be checked. If a logical query requests multiple distinct measurements or repeats a source pair using a different cache key, this theorem applies separately to each actual invocation. Do not replace that denominator with one unique object-label pair for the entire request/service.

Shared closed-solid-first preparation can supply a pair/tree to the surface suffix, but closed-shell validation, self/cross tests and ray work belong to the separate closed contract. `measure_spatial_relation` can share the surface `_Work` with later support work. The distance bound does not reserve all such suffix work or prove the full composite fact. When a decision is made after any shared expenditure, use the real remaining margin at that point, not the nominal 1,179,648.

Only referenced vertices contribute to the surface frame/preparation bound; `V_ref≤3F`. Arbitrarily many unreferenced ambient vertices are not new native triangle obligations, but capture/document/transport limits and real decoding costs remain outside this pair-work theorem.

## 5. Exact width, public output and canonical limits

The work certificate is **not** a general known-answer certificate. Finite binary64 input alone does not prevent common-frame bit overflow, exact rational overflow, distance range refusal, witness publication failure, deadline/cancel, source changes, or an independent closed-solid failure. Small `nm` does not rule these out.

One genuinely input-observable narrower analysis domain is two nondegenerate triangle unions, each lying in its own distinct global coordinate-axis plane, with all referenced coordinates in `[-2^16,2^16]∩2^-24 Z`. Their plane gap is at least 2^-24. Relative integer coordinates fit within 42 bits. Plane contact/coplanar clipping cannot occur across the two sides. Feature numerators/denominators and rank comparisons have bounded fixed algebraic degree (a conservative 1,024-bit reserve dominates the normal, edge, face and feature-comparison products here), and the current 4,096-bit kernel domain is ample. Positive public witnesses cannot collapse because their separating axis coordinates are distinct exactly representable input-grid values. Small absolute coordinates also bound binary64 point-rounding error well below the 1e-9 publication tolerance. This narrow geometry class is useful for separating the remaining numerical assumptions from the Work proof; **no claim is made that it contains the valuable G60 calls**. Standard-library floating distance/publication assumptions and actual source binding must still be part of any complete qualification.

For a normally completed `_nearest`, equal-distance pruning preserves potentially earlier native rows; the compiled rectangle's pair of minimum IDs is its earliest possible Cartesian pair. C only discards equality where that rectangle cannot contain an earlier winner. A similarly considers equal-distance earlier pairs; linear zero early return is lexicographically safe.

There is a distinct inherited limitation on the **validated zero boundary-contact bypass**. `_boundary_witness` verifies pair identity, indices and exact point membership, then `measure_surface_proximity` can publish its contact without `_nearest`. It does not establish that the supplied contact pair is the globally earliest zero-distance source pair. This is a valid contact witness but the full-traversal lexicographic proof cannot be extended to it by assertion. A result-cache hit only inherits the scope already established for its stored witness.

## 6. Release interpretation

The 129 counterexample is excluded by the narrow bound, and both 125 and 129 are excluded by the conservative tree Work bound. This neither contradicts 125's actual success nor certifies all smaller successful cases. The low-region artificial remaining-credit example also fails the stated remaining-Work inequality; it must not be treated as a fresh ordinary ledger.

G60 inclusion needs the frozen actual per-kernel-call n,m, prepared/cache state, source and remaining margin. The 66 possible object pairs are not automatically 66 fresh distance invocations. A pair-count or Work certificate cannot by itself justify mixed-entry acceleration, high-load coverage, or whole-request replacement. If actual valuable G60 calls are outside the certified domain or lack width/publication/composite evidence, the first unmet condition must remain explicit and routing/engineering extrapolation must stop.

# Exact closed-shell read-only classification

`surface_geometry.classify_closed_solids(left, right, checkpoint, diagnostics=...)`
classifies the represented world-coordinate triangle shells at zero tolerance.
It does not call or change the action/legacy tolerance solver and returns no
signed penetration distance or minimum escape vector.

The optional private `prepared_pair` is the exact tuple
`(records, topology, origin, factor, prepared)` from the existing surface-distance
admission/integer-frame functions. `prepared_holder['pair']` receives this tuple
after successful preparation, including when subsequent solid validation fails.
This enables a cold query's independent distance computation to reuse the same
conversion. The tuple is not placed in the public result or persistent cache.
Only the caller's current pair may supply it.

## Admission and embedded boundary proof

The existing checked dyadic-to-integer conversion supplies common exact points,
face normals, edge geometry and AABBs. Referenced zero-area faces are invalid for
a solid, although the independent surface-distance fact can retain their hulls.
The pair has at most 4096 vertices, at most 4096 faces in total and the unchanged
surface preparation's face-product admission bound of 16384. Duplicate faces,
unused vertices, open/nonmanifold edges, inconsistent edge orientation, multiple
face-connected shells, disconnected/non-cyclic vertex links and zero signed
volume are rejected. Reversing all face windings remains valid.

Both shells are fully validated before a cross-solid early answer. Their exact
BVHs visit possible self-intersections; every intersection must be precisely the
shared source vertex or edge. A nonadjacent touch or intersection, or adjacent
overlap beyond the shared simplex, is rejected. Together with the manifold
checks this establishes the promised embedded closed PL boundary; no global
convex hull or object-specific geometry is used.

The old self-BVH builder is factored into `_bvh`. `candidate_pairs` retains its
old call behavior and admits private cross-bounds/reused-root arguments. Each
shell tree is built once and reused for self and cross traversal, boundary-point
queries and exact ray traversal. The root's existing surface regression suite
must still verify legacy traversal/output behavior.

## Sufficient certificates and conservative degeneracies

* A noncoplanar boundary-intersection segment whose midpoint is strictly inside
  both triangles proves a positive-volume interior intersection. The two local
  interior half-spaces intersect in an open wedge regardless of global winding.
  This detects crossing solids even when neither has a vertex inside the other.
* With disjoint boundaries, a connected boundary has constant inside/outside
  membership relative to the other shell. Exact parity at one vertex in each
  direction therefore distinguishes containment from separation. A probe in a
  through-hole is outside the material, even when its AABB is enclosed.
* A boundary vertex or face centroid strictly inside the other solid is also a
  positive-volume witness: a neighbourhood inside the other solid contains a
  positive-volume one-sided neighbourhood of the validated source shell.
  Centroids are generated only when earlier vertex witnesses did not suffice.
* Contact plus a face plane supporting the complete two vertex sets on opposite
  closed sides proves touching with no interior overlap. This is independent of
  world axes and works under common exact rigid transforms.

If boundary intersections have no proper crossing or strict containment witness
and no global supporting plane proves nonoverlap, the result is explicit
`closed_solid_ambiguous_boundary_arrangement`. Coincident boundaries and some
mesh-edge degeneracies may consequently be unknown. They are never guessed
touching or penetrating from zero surface distance alone.

Point containment first tests exact boundary membership, then uses up to eight
deterministic positive integer ray directions. Only strict face-interior ray
hits count; any ray through an edge/vertex or along a candidate face is discarded
and another direction is tried. All arithmetic uses the existing checked
integer/Fraction operators. Exhausting the direction set gives explicit
`closed_solid_ray_degeneracy`, not a floating winding estimate.

## Work and limits

There are at most 16384 exact self/cross triangle-pair tests combined, 16384 ray
triangle tests and 262144 accounted work units. Checkpoints run during admission,
topology, tree traversal, pairs, parity queries and support-plane scans; request
deadline/cancellation exceptions propagate. Existing 4096-bit arithmetic guards
remain in force. Known domain/width/work refusals become explicit unknowns;
unrelated programming exceptions are not masked as geometric uncertainty.

`work` records preparation reuse, validated faces/referenced vertices, total and
self/cross pair tests, BVH node/leaf visits and pruned pairs, point queries, ray
attempts/tests and accounted work. These are local operation observations, not
CPU cycles, heap bytes or model benefit. A successful pair may use the existing
complete-geometry pair cache at the task layer; no new scene cache is introduced.

This core author performed source editing, AST parsing and static reasoning only.
Actual tests and QA are owned by the parent through the frozen verified loader.

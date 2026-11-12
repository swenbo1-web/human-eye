# Initial-candidate review and the single permitted optimization

The initial surface implementation is frozen at SHA256 ef909bed94344408c6ac53a3e40b8fac3886c6ea69d96dbcb2c2a51ce6cdbf98. It obtains the three G508 distances. Peer executes 7,324 expensive leaves against the frozen 18,791 reference. Competing executes 1,324 against the old 1,048, which remains an unfavorable observation. No distance-strategy adjustment is selected.

The initial closed implementation b2a5ae286aae568a9875e57a56ffa9a3ed2f83599fa8db4ee8d3bba60d2a3c3e fails all three G508 pairs at the original 262,144 work boundary, still checking Target self-intersection. The Peer attempt visits 56,031 node pairs and 17,032 leaf pairs and performs 73,950 plane projections. Full intersections account for 3,007 pairs. Shared fan anchors keep many boxes overlapping, so the traversal and per-pair projections remain the dominant observed cost. Original results are retained under closed/initial_counts_01.

The separately recorded prepared-pair binding correction produces source 8f3454ce06794098262b57245757f33e3db68941533cd4c07ff19899a74e8950. It corrects a deterministic foreign-pair reuse error. It does not change the search strategy or replace the initial performance evidence.

## Selected optimization

Use node-level shared-simplex certificates during same-mesh self traversal, reusing the initial invertible candidate frame and tree. No distance change, axis change, leaf-size sweep, input change or budget increase is selected. This uses the one permitted substantive optimization.

For each node and each source vertex common to every descendant face, retain an optional two-dimensional angular cone about that source anchor. A leaf constructs its cone only when its triangle projection is nondegenerate. An internal node merges the two child certificates for the same anchor. The chosen extreme rays must have strictly positive exact cross product and must contain all child extreme rays in their closed cone. This proves angular width below pi, including wraparound checks. Every boundary carries all source IDs lying on that ray. Degenerate projections, absent common anchors and unproved cones have no certificate.

For two different nodes in the same shell, try the fixed boundary lines of their cones about a common source anchor. A certificate requires all points of the first node on one closed side and all points of the second on the opposite closed side. The union of all source IDs lying on the line, including the anchor, must contain at most two IDs. If there are two IDs, their projected coordinates must differ. The optimization does not identify distinct source IDs by coordinate coincidence.

## Proof obligation

For any descendant triangle, its intersection with the separating line is the convex hull of its on-line vertices. With at most two distinct projected source points in the combined on-line set, two such sections intersect only in the hull of their common source IDs. A nondegenerate projection is injective on each triangle plane. Each shared projected point or edge therefore lifts to the identical original same-mesh source point or edge. Every discarded descendant pair has empty intersection or a legal shared simplex. The proof applies only to self traversal with common source identity. Cross-shell traversal keeps the original predicates.

## Charging and fallback

Charge metadata preparation, actual orientation tests, source-ID copying/merging, node certificate checks and original node visits to the unchanged closed work budget. Record covered pairs separately from executed work. No complete intersection is performed before deciding that it is avoidable. Exact arithmetic uses the unchanged 4,096-bit domain. Optional metadata or certificate overflow falls back to ordinary traversal. Cancellation, deadlines and total-work failures propagate.

The implementation should merge at most four child extreme rays with a bounded construction and final containment validation, avoiding descendant rescans and a generic hull framework. It retains all common anchors, at most three per node. The simple-input path stays on the existing linear/world-tree behavior.

## Acceptance and stopping

Keep all initial failures and the source-binding counterexample. Validate legal shared edges and points, same-side overlap, shared-anchor remote crossing, duplicate coordinates with different IDs, degenerate projection, half-turn cones and overflow fallback. Then freeze the resulting candidate, run the related regressions, the fixed forty kernel calls and the single three-business MCP sequence. If the original gates still fail, report the remaining bottleneck and close this batch with partial or failed acceptance. No additional strategy optimization is authorized in this batch.

The delayed historical E/F administrator review has been closed separately. It requires no restoration of current M3 sources and does not change this plan.

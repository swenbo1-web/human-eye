# Discovery implementation and single simplification review

Both variants consume the same already parsed Fraction vertices and source face indices. The common topology pass builds one undirected edge-incidence table while retaining directed occurrences. Internal edges require two reversed occurrences. A face-adjacency traversal requires connectivity. Referenced vertices must lie exactly in the first nondegenerate triangle's plane.

One directed boundary cycle must consume every boundary edge. A single pass over this cycle removes a vertex only when its incoming and outgoing vectors are collinear and have positive dot product. The remaining four corners must form an exact rectangle. All referenced vertices must lie inside its orthogonal coordinate intervals. The oriented triangle area must equal the rectangle area. These conditions use source vertex indices, with no coordinate welding or triangle-pair intersection loop.

The incidence cancellation makes the oriented triangle-chain boundary equal the directed rectangle. Every accepted triangle has positive orientation in that plane. Away from edges its signed coverage multiplicity equals the rectangle's boundary winding, so overlap or an uncovered positive-area region would violate that boundary. Single-cycle and connectivity checks additionally reject holes and disconnected components. The explicit area equality and vertex containment checks retain directly inspectable consistency conditions.

## Reference

For each triangle the reference computes the full three-component cross product, rejects zero area, checks its dot product with the plane normal, and accumulates the three-component oriented double area. It streams the triangle normals and keeps one current normal vector. It does not retain an artificial per-face normal list.

## One candidate

After the shared exact coplanarity proof, choose the first nonzero plane-normal component `k`. Every triangle normal is parallel to that plane normal. Its component `k` therefore vanishes exactly when the triangle is degenerate, and its sign relative to the plane normal determines winding. The candidate computes that component using one two-dimensional signed determinant and accumulates one scalar. Its sum is compared with twice component `k` of the canonical rectangle normal.

This replaces the reference area loop's full vector cross product, three-component dot product and vector accumulator. For an accepted triangle, the recorded area-loop arithmetic calls decrease from 9 multiplications, 9 subtractions and 6 additions to 2 multiplications, 5 subtractions and 1 addition. These are source-level rational arithmetic calls. Fraction implementation cost still depends on numerator and denominator bit lengths. Common plane, topology, boundary and coverage work is unchanged.

No second candidate is present. There is no change to camera choice, occlusion, rasterization, readability thresholds or state updates.

## Shared coverage and interfaces

`parse_geometry(scene, stats=None)` calls the frozen core's `geometry` once, including its original geometry identity hash. `regions_from_objects(objects, discovery_variant, stats=None)` discovers rectangles from that parsed representation. `build_index_from_parsed(objects, triangles, scene_identity, regions, cameras)` runs the original coverage `build_index` code object with a private globals snapshot. Only its geometry and region suppliers are rebound. Its occlusion variant is always `optimized`.

`build_from_parsed(objects, triangles, scene_identity, cameras, discovery_variant, stats=None)` performs one discovery and one shared coverage call. `build_index(scene, cameras, discovery_variant, stats=None)` adds one geometry parse. The driver can choose the explicitly separated stages without repeating geometry or discovery.

The frozen core is `verification/m4_active_coverage_001/coverage.py`, SHA-256 `2561ecaf2f2df98ec7c03ed48cb95dd08c34f10ce73c1e9ecc2e32f31c41daf4`. Its `Region`, `Triangle`, `CoverageIndex` and `CoverageState` classes are exported unchanged. The source module globals remain unchanged.

## Identity and counters

The directed corner cycle starts at the lexicographically smallest corner. The ROI hash uses the original `fingerprint(quad)` formula. Its normal is the full canonical rectangle `u × v`. The ROI identity therefore follows the four corners and front. All actual source face indices are retained in `triangle_indices`.

Discovery counters describe actual visits, edge insertions and area-loop arithmetic calls. Temporary payload fields count retained structural elements and current normal or accumulator components. They do not measure Python heap bytes, allocator behavior, CPU cycles or RSS. Bit-length fields cover the examined input coordinates and accepted final area sums. Intermediate Fraction maxima are unmeasured.

The discovery pass uses expected-linear dictionary and set operations in the number of referenced vertices, faces and boundary edges. The original geometry canonicalization and coverage calculations retain their existing costs. No claim of linear whole-index runtime is made.

## Verification state

Preparation performed source review and AST parsing only. No candidate function, correctness matrix, renderer or timing sample was executed by this source owner. Input equivalence proofs, the fixed correctness matrix, four observation chains and the one five-pair performance sequence are owned by the root controller.

The predeclared choice requires equal quality, reduced arithmetic work, a candidate/reference full-index paired-ratio median at most 1, and candidate full-index elapsed sum at most the reference sum. Otherwise the reference is selected. Small measured differences carry no significance claim.

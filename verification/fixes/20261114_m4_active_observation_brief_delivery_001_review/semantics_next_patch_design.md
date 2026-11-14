# PATCH-OWNERSHIP-001 bounded design review

Read-only design review of current `cdd2b116` core, host, images and shared raster. No product execution or new images. This is a proposal for root to incorporate into one implementation task, not an independent work order.

## 1. Extract maximal connected planar components, then reuse the rectangle proof

Keep normalized complete vertices/faces and build undirected edge incidence once per object. Flood-fill face adjacency only across exactly coplanar triangles. Group by the same **unoriented plane**; do not split an inconsistent-winding coplanar mesh into convenient separate valid regions. Run the existing oriented topology, single boundary, collinear-corner reduction and rectangle/area checks on each maximal planar component. The accepted component retains its original object/triangle indices. Rejected components remain domain-unknown and still occlude.

This supports six rectangular sides of a box and disconnected rectangular components in one mesh without adding arbitrary rectangular window search. Existing nonrectangular planar components must not be subdivided opportunistically until an easy rectangle appears. No tolerance fitting, welding, curved patches or same-coordinate vertex merging is needed. Unrelated rejected components must not discard valid components elsewhere in the object. A one-time face-membership map avoids repeated whole-object scans for every region.

The current ROI key derived from canonical oriented corners can remain invariant under triangle subdivision and split/join representation. Host/source and geometry identities should still change when object grouping changes. Do not force the entire source identity to stay equal merely because the world surface union is equal.

## 2. Only a region's own triangles are exempt from occlusion

At `active_observation.py:371`, replace the whole-object exemption with `(triangle.object_index == region.object_index and triangle.triangle_index in region_triangle_set)`. Construct membership once per region or use the face-to-region map. Other patches of that object, and its unsupported faces, remain ordinary blockers.

Keep the current per-view projected vertex/triangle/bounds reuse and exact clipped positive-area test. This batch does not need a new spatial service, global acceleration framework or relaxed tolerance. The expanded 28-object scene can have 138 supported rectangle faces (6 old plate ROIs plus 22 boxes × 6), so record actual regions, tested candidates and complete preparation cost. More supported targets legitimately cost more; compare equal delivered geometry coverage rather than claiming the old six-target computation is equivalent work.

## 3. Add patch ownership to the existing winning-depth write

Minimal option: one int32 patch-owner buffer, plus the existing RGB/depth/object-owner buffers. Create one face-to-patch lookup per original mesh. Whenever `_raster_triangle`'s existing `nearer` mask wins, write the same patch ID using that exact mask, including all clipped fan triangles. Keep existing caller return shapes unless the optional patch output is requested.

Use stable sorted ROI indices for supported patches, `-1` for background and `-2` for unsupported foreground. Preserve original unannotated RGB/shading; do not color patches merely to manufacture readable boundaries. At 512², one int32 buffer adds exactly 1,048,576 raw bytes per retained frame; count it in saved arrays/cache and complete costs.

The alternative of storing global triangle indices is workable but has a specific cache trap: current geometry and mesh-order digests canonicalize face order. Reordering faces can therefore reuse an old frame while a new triangle-index lookup maps pixels to different faces. A triangle-owner design must bind the exact face lookup/order, or invalidate that reuse. Stable patch-owner indices avoid this face-order dependency; bind the saved buffer to the ordered ROI mapping. Stored NPZ reload and current in-memory feedback must use the same mapping. Existing object owner remains useful for compatibility and for checking patch-to-object correspondence.

## 4. Aggregate the real pixels once per frame

Use one whole-frame surface histogram over nonnegative patch IDs. Compute four-neighbor boundary eligibility once from adjacent patch owners and the existing integer RGB-distance threshold, then one per-patch boundary histogram. Mark each qualifying pixel once rather than counting each adjacent edge repeatedly. Preserve 16 surface / 4 boundary / 24 RGB thresholds and front-facing gating.

Two visible patches of the same object can have a real shading boundary; the current object-owner equality would suppress it. Conversely, triangulation seams within the same patch are not region boundaries, and two distinct patches with no RGB contrast must not acquire a synthetic readable edge. Unsupported foreground contributes normal occlusion and can bound a supported patch, but cannot add its own pixels to that patch's counts. Avoid calling `_readability_evidence` once for each of 138 regions, since it rescans the entire frame each time. An active-specific helper beside `_pixel_rows` is sufficient; no generic replacement framework is needed.

## 5. Publish partial object support explicitly

Yes, brief/full must state an object's unsupported remainder. Existing `objects_without_supported_roi` only describes objects with zero ROI, so an object containing one valid rectangle plus an irregular triangle would otherwise disappear from the unknown scope.

A small per-object support table is sufficient: object index, total triangle count, supported triangle count, unsupported triangle count, and a domain-unknown reason where the remainder is nonzero. Full/internal diagnostics retain the actual component/triangle membership. The supported and unsupported triangle sets must be disjoint and exhaustive. Do not label this table as visibility coverage: even a fully supported box still has unobserved/occluded faces in the separate ROI coverage table. Keep one object identity table and all negative ROI/view pixel rows. Extend the versioned public contract explicitly rather than silently interpreting old whole-object scope as partial support; no new retrieval service is required.

## 6. One fixed scene pair, one bounded acceptance run

Derive a fixed, moderately complex fixture from the existing 28-object world scene, keeping its occlusion clutter and plate triangulations. Register a single additional nonrectangular component if needed to obtain a genuinely partial object. Before running candidates, freeze both versions:

- **Split:** supported rectangular surfaces and the relevant blockers are separate mesh objects/components as declared.
- **Joined:** precisely the same world vertices, oriented triangles, materials and camera parameters, but selected front and hidden surfaces/blockers are combined in one mesh. Do not move, remove or recolor geometry. Prefer retaining the source triangle iteration order to avoid confusing existing equal-depth tie behavior with patch correctness.

Required witnesses in that one scene pair: (a) one readable front patch and a different front-facing rear patch in the same joined object, with the rear fully depth-occluded; front must have its own positive counts while rear has zero winning pixels and remains unknown; (b) another patch with a visible but insufficient/negative row, preserving all negative evidence; (c) a joined object's nonrectangular remainder still reported unknown and participating in occlusion; (d) ordinary box faces discovered instead of treating all 22 boxes as ROI-free. Verify source triangle multiset and frozen camera matrices before comparing output. Compare ROI geometry, geometric blocker classification and patch counts, not host object IDs, which intentionally differ.

Use independent analytic interior witness points or simple reference ray/triangle calculations for the registered front/rear pair. Ensure the intended occlusion is positive-area and separated in depth, not an equal-depth tie. A handful of such independently derived witnesses supplements, rather than reuses, the candidate's visibility mask as its own expected answer. No model call is needed to establish this geometric correctness.

**New raster budget:** at most two actual installed Host/stdio executions × six frozen 512px views = **12 new rasters total**. Count every attempted raster, including failures; stop at the cap. A repeated same-source read can prove reuse with zero new rasters. Read default and full from the already completed result rather than opening another fresh capture/render cycle. Face-order, retriangulation, disconnected components, inconsistent winding and unsupported-partition tests should use geometry-only fixtures or synthetic owner buffers, with no extra raster calls. Public compatibility can reuse archived old replies.

The scene pair should have at least one discriminating old-failure witness fixed before candidate execution. Acceptance is (1) discovery and source partition correct, (2) same-object occlusion and actual depth-winning patch ownership correct, (3) public unknowns/brief/native images survive actual entry, and (4) complete cost is recorded for expanded target count. After one integrated pass and one targeted optimization, stop; do not add unlimited scenes, cameras or microbenchmarks to improve the score. If twelve attempts are exhausted by genuine wiring failure, report the exact completed/unknown state for root's next decision rather than erasing failed work.

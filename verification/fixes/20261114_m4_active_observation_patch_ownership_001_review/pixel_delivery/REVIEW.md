# PATCH-OWNERSHIP-001 independent pixel and delivery review

Candidate `efe7f77aabdab4f8de47fdb4f8714cb25f301503`, compared with `cdd2b116`. This scoped pixel/transport acceptance passes: **5289 final independent assertions, zero product findings that block the registered batch**. There is a distinct model-usability gap described below. No product, author oracle, raster, Blender, model or benchmark function was imported or called.

## What was actually checked

The independent script reads the original captured vertices/faces and the frozen construction's axis-aligned rectangles. It rebuilds face-to-patch membership using each rectangle's exact plane, orientation and bounds, rather than reading the candidate's face membership as the expected result. The actual split capture has 29 objects; joined has 1; both have 1913 vertices and 3337 triangles. Rebuilt membership accounts for 3336 supported triangles and exactly 1 unsupported triangle. The saved map, offsets, ordered source geometry digest and stable 138 ROI order agree with this reconstruction.

Six actual NPZ files contain the expected nine arrays. Their array metadata, hashes, source mapping identity and saved face maps match actual captured geometry. The six PNGs decode to the corresponding RGB arrays. RGB/depth/object-owner consistency and patch-to-object ownership hold. Split and joined RGB, depth and patch-owner buffers are identical for each corresponding selected view. The same patch indices retain semantic meaning while object indices change with representation.

For each of the six frames, a separate full-frame integer RGB-difference calculation constructs the union of eligible four-neighbor boundary pixels. Per-ROI mask counts independently reproduce all **828 pixel rows**, including front-facing, surface count, boundary count, readability and the 16/4/24 rules. The review did not invoke the product's sparse/dense boundary helper or histogram helper.

Each representation has 68 readable regions in SCENE, 47 in BACK and 46 in LEFT; union coverage is 115, leaving 23 unresolved. All negative rows remain. In SCENE the front witness has 354 surface pixels and 73 boundary pixels, while the front-facing hidden rear has zero of both and remains unreadable. Joined assigns both to object 0, so visible pixels of a different face do not confer coverage on the hidden rear. Unsupported foreground is real: 36, 77 and 110 pixels in SCENE/BACK/LEFT, respectively, without being assigned to a supported patch.

The seven actual protocol records contain five tool responses. All 15 native PNG blocks match saved image bytes, hashes and ordering and were independently decoded with Pillow. The four default results are brief-v2, with text sizes 27812, 27812, 24081 and 24081 UTF-8 bytes. Each preserves 138 regions and all 414 pixel rows, source/instance fields, image binding, observed/unknown sets, denominator tables and exact unknown component ranges. The fifth full result retains complete task facts and full region face mapping. Local consumer evidence remains distinct from the public `unconfirmed` consumer status.

These are 5289 checks of a fixed scene pair and its five deliveries, not thousands of independently sampled scenes. The 2070 delivered pixel rows are repeated consumption of the six frames; the actual independent pixel denominator is 828.

## Source review

`attention_raster.py:45` extends the existing winning-depth write: color, depth, object owner and patch owner use the same `nearer` mask. The clipped fan retains the original face's patch ID. The prior two- and three-result interfaces remain, and patch output is optional. No additional render or label coloring was introduced.

`active_observation_images.py:89` binds mapping identity to ordered actual vertices/faces, ROI order and the per-face map. `_synchronize` includes that identity in reuse decisions and binds the coverage state. `render_next` synchronizes before choosing a view. Saved NPZ metadata and current frame mapping are compared before feedback. Historical three-buffer derivation is restricted to objects having at most one whole-object patch; multi-patch and partial-patch cases require actual patch winners.

`_aggregate_patch_pixels` computes one boundary map and two histograms. Internal triangles of the same patch cannot become artificial patch boundaries. A boundary between different patches still requires real RGB contrast. The single `-1` patch sentinel denotes both background and unsupported surfaces, but original object owner distinguishes these; this does not award their pixels to supported patches.

The extraction of `_contrasting_boundaries` preserves the old object-readability calculations. `live_spatial_mcp.py:805` adds exhaustive support/unknown component accounting and readable inclusive index ranges. The actual delivery uses v2 rather than silently falling back to full.

## Independent audit correction retained

The first pass had five failing binding comparisons because it incorrectly expected the internal `binding.camera_specification` in public full/brief output. Existing `_active_observation_content` explicitly excludes it before either public representation, including the baseline. The first script and result are retained as `audit_first.py` and `RESULTS_FIRST.json`. Only the five binding comparisons were corrected and rerun by `correct_binding_check.py`; the six NPZ computations and 15 native-image decodes were not repeated. All other public binding and capture identity fields compare exactly under the declared representation.

## Next model-usability gap: ROI identity is not spatial localization

The actual joined default response's region columns are only `roi_id, object_index, status, reason, triangle_count`, and all regions point to object 0. The actual full response adds triangle indices, but does not supply the corresponding world vertices. Public full frame metadata omits pose; public binding omits the full camera specification. Native PNGs are unannotated and do not label these ROI hashes. Neither the inspected MCP input schema nor service exposes an active ROI-ID-to-world-geometry read path.

Consequently, the response can report which stable hash is covered, but a model cannot directly identify that hash as a particular face at a particular world location from the delivered data alone. It would need another native geometry read or access to private acceptance capture evidence. This does not invalidate the registered patch ownership/partial-scope contract, which intentionally kept complete maps internally/full, but it prevents treating this batch as proof that a model can now use the 138 facts to solve a spatial task.

A minimal next task is to emit one shared, source-bound geometric description per ROI, such as canonical world corners or an explicit center/basis/extent representation, and a lightweight actual-image location for each observed patch. An image anchor must fall on an owned visible pixel; a naive mask centroid or bounding-box center may lie outside the region. Preserve the actual unannotated image and all unknowns. No new service, model or repeated geometric acquisition is needed to add this connection. Its eventual quality gate should ask the model to identify concrete faces/positions and distinguish a hidden region, not merely echo a coverage count or hash.

# REGION-ANCHORS-001 short design review

This is a bounded proposal within the current root review. No current frame was recomputed, and no product, oracle, model or raster was executed. One standard-library JSON calculation on the frozen 138 rectangles compared representation sizes below; it is a layout estimate, not a candidate benchmark.

## World localization: center and two half-edge vectors

Use exactly one representation per ROI: `center_world_m`, `half_axis_u_world_m`, `half_axis_v_world_m`. For the canonical oriented rectangle q0,q1,q2,q3, c=(q0+q2)/2, u=(q1-q0)/2 and v=(q3-q0)/2. The ordered corners reconstruct as c-u-v, c+u-v, c+u+v, c-u+v. Orientation comes from u×v; a second normal, dimensions, corners and bounding box would duplicate the same information.

The center is directly useful to a model and u/v retain orientation and extent. State once that u and v are world-space vectors from the center toward the corresponding edge midpoints. Keep this geometry in the existing region table; no additional per-frame copy or extra lookup service is needed.

Compute c/u/v using the existing exact arithmetic. Emit an ordinary JSON number when it round-trips to the exact scalar; otherwise retain the scalar as an exact fraction string using one shared documented representation. Do not silently round thin offsets away or turn an out-of-range value into infinity. This is a representation rule, not a new tolerance or separate validation layer. For the fixed 138-region fixture, every c/u/v coordinate is exactly representable as binary64, so this fallback adds no sample overhead.

A raw JSON layout estimate on those fixed rectangles gives four-corner payload 21275 B versus c/u/v payload 10726 B, excluding field names and the existing table. There are 200 distinct corners, but introducing another point-index table would make a model perform extra joins. Prefer the direct c/u/v facts for this first usability batch; do not pursue a second compression experiment.

## Actual-image localization: inclusive bounds and an owned interior-oriented anchor

Publish `visible_bounds_px=[xmin,ymin,xmax,ymax]` and `visible_anchor_px=[x,y]` for every ROI/view row. Describe coordinates once: integer indices in the actual decoded image, x right, y down, origin at top-left, inclusive bounds. Image size is explicit once per image or once for the fixed pool. An anchor designates that image pixel; it is not an extra world-space witness.

Both fields are null **if and only if there are zero owned surface pixels**. A region with a few visible pixels, a visible back side, or inadequate contrast may still have an anchor while `readable=false`. Do not equate negative readability or a partial geometric blocker classification with complete invisibility.

Compute one flat set of nonnegative patch-owner pixels per frame and reuse it for surface histogram, bounds and anchors. Use indexed min/max reductions to obtain each patch's x/y bounds. To choose a useful anchor rather than the first boundary pixel, find the owned pixel nearest the bounding-box center. Compare integer distances `(2*x-(xmin+xmax))²+(2*y-(ymin+ymax))²`, then break ties by the smallest row-major flat index. An indexed minimum of distance, followed by an indexed minimum of eligible flat indices, gives a deterministic owned pixel. The box center itself is never emitted blindly.

This is a few shared O(P+R) array passes, with P the image pixels/visible samples and R the patch count. It does not scan a full frame R times, rerender, change image colors, modify coverage thresholds or need ray casting. The existing boundary histogram remains shared. Patch mapping/image/source identities bind these additions to the already verified data.

## One bounded quality and optimization acceptance

Freeze the original joined fixture and its geometry expectations. In the actual installed cold/hot/full sequence, verify all 138 world rectangles reconstruct exactly to the frozen canonical corners and all 414 ROI/view rows preserve existing counts/status. Recompute bounds with an independent simple per-ROI mask reference; every non-null anchor must index the actual ROI in the stored patch-owner buffer, satisfy the registered nearest-center rule and deterministic tie break, and fall within its bounds. The existing hidden rear remains null; the visible front has a valid anchor. Include synthetic disconnected masks, hollow shapes, single pixels, zero pixels and ties so a centroid or bounding-box-center shortcut demonstrably fails.

The frame identity and decoded original RGB must agree with the ownership buffers. The public delivery adds geometry only once per region and actual pixel localization once per ROI/view; default must remain brief. Full/cold/hot preserve the same facts and images, with no fresh capture geometry interpreted as cached evidence. Source changes still invalidate the existing bindings.

Run one frozen five-pair comparison on the same saved joined SCENE frame: a correct simple per-ROI bounds/anchor reference versus the shared aggregation candidate, both returning the same complete outputs. Count all calls and include the added anchor/bounds cost, not just the already-fast histogram. Report final text bytes and whole cold/hot/full times as well as local kernel time. No extra sample search, image-size reduction or field dropping if the result is disappointing.

Normal new raster count is at most three for the one joined cold observation; hot/full reuse. Hard cap four includes all failures. Other cases use synthetic buffers and existing frozen evidence. No model calls are needed in this batch. Once this representation works at the real entry, the next useful gate is model identification/localization of concrete visible and hidden faces against a controlled native baseline; do not detour into another indexing micro-optimization.

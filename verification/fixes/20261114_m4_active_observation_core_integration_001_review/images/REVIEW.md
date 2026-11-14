# Independent image feedback review

Reviewed author commit `cd863183b18e35d2ca38f75c0756e1c46e1a1ccb` against the current core-integration plan. **Accept the image-adapter migration within its stated finite rectangular-region domain.** The independent data-only audit passed **819/819 checks**. This finding does not activate a Host/MCP entry or establish general scene-perception quality.

## Actual independent work

Read the product image adapter, its full-scene raster and readability dependencies, the session/coverage boundary, the targeted test source, the isolated worker, and original retained source/installed records. `audit_images.py` imports only standard libraries, NumPy and Pillow; it never imports the candidate or invokes its algorithms.

Read all six actual PNG/NPZ pairs from both the sealed archive and their external original locations. The bytes and recorded hashes match. Independently rebuilt four-neighbour RGB-contrast boundary masks with integer squared distance, counted object-winner surface/boundary pixels, and derived front-facing orientation from the input mesh triangle winding. All **36 new pixel rows** agree with their stored records. Array shape, dtype, payload hashes, positive foreground depth, infinite background depth, owner ranges, PNG/RGB equality, full mesh counts and pose bindings agree.

Recomputed another **96 historical pixel rows** from eight distinct saved frame pairs used in 16 logical source/installed replays. These remain historical replay inputs, not newly constructed frames. Six intent records match the 12-line actual-render trace. This review constructed **0** new rasters, ran **0** product algorithm calls, **0** model calls and **0** Blender calls.

## Confirmed behavior

| Chain | Actual views | Newly covered per view | Final result |
|---|---|---|---|
| Normal pool | SCENE → BACK | 2 → 3 | 5 covered, Obj_006 unknown |
| BACK64 control | SCENE → BACK64 → LEFT → TOP | 2 → 0 → 2 → 1 | 5 covered, Obj_006 unknown |

The BACK64 image contributes zero readable regions. Its full prediction mask need not be inferred to verify that no coverage is added. Other views use the retained exact index masks, intersected with independently recomputed readable IDs. The finite-pool unknown remains explicitly named; neither chain claims complete scene understanding.

The adapter constructs meshes from every normalized object and retains their actual face arrays. A single full-scene raster receives all those meshes. Canonical four corners and the oriented front describe the discovered region for readability; they do not replace the actual subdivided mesh or remove occluders. The full-scene raster retains one shared depth/owner buffer and traverses all supplied faces.

Feedback first checks the current scene/camera identity, owner order and pose where supplied, stored NPZ versus in-process buffers, and PNG versus RGB. It computes the 16 surface / 4 boundary / RGB24 evidence before committing through CoverageState; state intersects readable regions with the exact predicted mask. Short facts remove triangle-index arrays while retaining object/ROI identity, view/image references, scalar pixels and unknown reasons.

Repeated reads and same-source rebind reuse the current frame cache in the reviewed code; changed source/camera identity resets coverage and clears frames. Original source and installed qualification receipts agree on duplicate-state stability and stale-source/stale-camera rejection. This review did not rerun those behavioral cases; those claims are supported by static review plus retained receipts, not a new execution.

## Concrete optimization opportunity

`_pixel_rows` currently invokes `_readability_evidence` once per ROI. That helper recomputes a whole-frame contrasting-owner boundary and object counts on each call. With six ROIs, the same frame boundary work is repeated six times. A subsequent single-purpose optimization could compute the boundary once, accumulate surface/boundary counts by owner, and distribute those scalars to each ROI while retaining its independent front predicate. This could change the pixel-evidence stage from repeated frame scans toward one frame scan plus owner/ROI lookup. The present single-rectangle-per-object domain makes that mapping straightforward; it does not justify a claim about multi-patch/self-occluding regions.

This is not a migration blocker: the plan intentionally froze the pixel algorithm during packaging, and this review measured no new timing. Do not claim a speedup from this suggestion or add it to the reported 2.24% index result. The next thin Host connection should preserve actual delivery status separately from the current `image_delivery_scope='local_core_validation'`.

## Limits and execution record

This audit recomputed facts from existing real buffers, rather than independently rerasterizing the scene or proving every depth winner. It verified source geometry/front association and full-scene routing statically. It did not change the source, installation, default configuration or any asset. No runtime audit failures occurred. One extra closing parenthesis in the new audit script was corrected before its first execution; it never invoked the author pipeline.

Machine-readable checks, per-frame facts and the hashes of every read source/evidence file are in `RESULTS.json`; the reusable offline script is `audit_images.py`.

# Host bridge capture, pixel and transport review

Reviewed fixed author commit `32a1c6eb47cfa84133d92199387339d407a33cb5`. **Accept the actual capture and local stdio delivery evidence within the stated finite rectangular-region domain.** Independent offline audit: **980/980 checks passed**. No product algorithm, Blender, renderer or model was run by this reviewer.

## What was independently verified

Read all 199 retained external artifacts through `EXTERNAL_ARCHIVE.json`, checked their hashes and byte equality with the external originals, including the short-path aliases for long PNG/NPZ paths. Inspected host/image source, the pixel-readability dependency and the existing endpoint evidence. The audit imports only standard libraries, NumPy and Pillow.

Reconstructed five expanded scene captures directly from the saved QA socket response envelopes and their incremental resource dictionaries. This implementation is independent of the product's delta decoder. The reconstructed world vertices, faces, edges and metadata match the five saved server captures. The full meshes are acquired even on the hot request; zero mesh counts in the hot `work` record describe new computation, not a physically empty scene.

Recomputed all 5730 fixture coordinates from the old rational input times the predeclared exact `375/256` scale and checked float32 exact roundtrips. Four rectangular-scene captures retain all 28 objects, 1910 vertices and 3336 triangles; each captured object's vertices and triangle set match its unique fixture geometry. Host order may change, so matching is by actual geometry and instance mapping rather than old array position. This verifies the controlled fixture conversion, not arbitrary asset precision.

For the three cold rectangular requests, matched every saved ROI record to the independent host-resolved representation in DIRECT, and compared all 36 view/ROI classifications and view masks. Both sides bind the same actual capture SHA. The fourth cold nonplanar request has six views with zero ROI classifications. These are equality checks of two retained product executions, not a new independent implementation of the geometric occlusion solver.

From the six new PNG/NPZ pairs, independently computed owner-winner pixel counts and four-neighbour boundary masks using squared integer RGB distance at the inclusive 24 threshold. Derived front orientation from actual captured triangle winding and the rational camera direction. All 36 pixel rows match surface/boundary counts, front flags, readability and host/object association. Shapes, dtypes, PNG/RGB equality, positive foreground depth, infinite background depth, owner ranges, hashes and payload sizes match. Full-scene depth correctness was not re-rasterized.

## Actual behavior

| Case | New rasters | Native images read | Actual result |
|---|---:|---:|---|
| First ordinary | 2 | 2 | SCENE→BACK, gains2/3, five covered and Obj_006 unknown |
| Same-source repeat | 0 | 2 | Same facts, frames and binding; no prepare/parse/raster |
| Recovery baseline | 2 | 2 | Same finite coverage through a fresh QA instance |
| Rename only | 2 | 2 | Same per-instance geometry and PNG bytes; updated name, host ID, source binding and image references |
| Nonplanar | 0 | 0 | Actual four vertices/two triangles with1/256 warp; no supported regions, unknown |

For each public response, checked ordered host ID, instance ID and name against the actual capture. Six supported ROI objects and 22 other objects are explicitly distinguished; those 22 remain in the occluder geometry. The no-ROI case retains its single-object scope and does not report scene understanding.

All 12 stdio TX/RX envelope IDs match. Their 12 received byte sequences concatenate exactly to the two complete stdout streams. There are seven tools/call requests, including the expected invalid-query error. Ping and the legacy directory request succeed after that error.

Eight native PNG blocks decode to512×512 RGB and equal their saved consumer and engine files. Public text is exactly what the consumer saved. It retains `local_core_validation` and `consumer_read_status=unconfirmed`; the external test consumer separately reports readback confirmation. Model calls are zero and model image consumption remains not tested. This is actual local protocol delivery, not evidence of a language model's visual understanding.

The first acceptance controller failed after ordinary and hot requests had completed. Its constructed images and delivered blocks remain in all counts. Recovery's extra baseline explains the increase from four expected to six actual new rasters, still within the fixed eight cap. This review does not alter that failure into a pass. Runtime cost and actor cleanup are covered by the separate cost/lifecycle review.

## Concrete delivery optimization opportunity

The ordinary public text is **24,549 UTF-8 bytes**, with five active responses totalling **101,824 bytes**. Compact-serialization sizes of its major values are facts11,495B, binding5,518B, frames3,536B, stages1,546B and generation_stages1,251B, plus work/generation_work and other fields. Public facts themselves include5,513B of observation rows and3,892B of scope inventory.

This is faithful traceable delivery but not minimal task-facing output. Full host mappings, duplicate generation/current timing and frame/file metadata expose sizable internal information to a future model consumer. The evidence suggests a bounded public projection with stable evidence references as an optimization candidate before growing ROI counts. It does not establish a token or model-latency saving: no model consumed this response, and these are byte measurements. Preserve the full audit data separately; the current correctness result is not invalidated by the verbosity.

## Audit corrections and limits

The initial exploratory schema read assumed the last MCP content block was text, causing a KeyError; the actual protocol carries mixed text/image blocks, so the audit selects `type=text`. Its first executable pass then used the internal host delivery key `external_consumer_verified` against the public projection, which correctly uses `consumer_read_status`. The initial script and correction are retained.

The next pass reported four region mismatches because INDEX stores regions as a list whereas DIRECT stores an ROI-keyed map with host identity resolved. After explicitly normalizing INDEX records to the same host/geometry representation, all four compare equal. The initial976/980 result, script and explanation remain alongside the final980/980 result. These were auditor representation errors; no product, renderer, model or new source capture executed during correction.

The review validates retained raw evidence and code routing. It does not independently reproduce the Blender process, prove arbitrary scenes, measure model usefulness or claim full-scene semantic coverage. `RESULTS.json` contains per-check results, per-pixel recomputation and all read-file SHA256 values.

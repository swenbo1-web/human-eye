# Host bridge semantics and model-facing output review

Reviewed fixed author commit `32a1c6eb47cfa84133d92199387339d407a33cb5`, baseline `cd863183`. **The functional Host/MCP connection is acceptable within the finite rectangle domain. The requested short-fact delivery still has a concrete P2 gap: active observation ignores `response_detail=brief` and publishes substantial internal diagnostics by default.** Recommend one bounded delivery projection repair before treating that requirement as closed.

The independent offline audit has **112/112 consistent checks**. This count covers source facts, semantic preservation and retained wire records; a positive check count does not dismiss the explicitly identified output gap. No product code was imported, and no product test, model, Blender, raster or benchmark was run by this reviewer.

## Core and Host integration

All prior core functions/classes except the deliberately split preparation entry retain exact ASTs, including discovery, coverage and state. `prepare_scene_from_parsed` calls discovery/coverage without reparsing geometry; the public preparation entry still parses once. Every prior image-level helper retains its AST, including `_pixel_rows` and its unchanged pixel thresholds. Image-class changes introduce prepared-mesh reuse and phase timing, not a new visibility algorithm.

`observe_capture` maps actual captured vertices/faces directly, parses once and creates one complete mesh-array tuple. The same tuple feeds fixed-camera fitting and the image adapter. All true mesh triangles remain available as occluders. The old camera fitting numeric loop is AST-identical after renaming the fixed order/size/direction constants and normalizing direction-list construction. The 375/256 QA scaling is not present in the runtime coordinate path.

`source_binding` includes complete-scene scope, metre/world units, document epoch, scene revision, capture state, ordered host IDs/instances/names and fixed camera policy. Cold computation adds actual camera specification and geometry identity. The service performs a fresh capture before activating existing ReadContext and querying its completed result. ReadContext includes both its version token and the complete binding selection in the key; without a valid token it cannot reuse a completed result. Cached results are deep-copied, so request timing and delivery metadata do not overwrite retained construction facts.

Same-generation image/no-image requests have distinct result keys. A name-only change changes the binding even when geometry is unchanged, and therefore runs a new computation and produces new source-bound image references. This is supported by static flow and retained author results, not a fresh invalidation execution. Every recorded request reports one capture; only the hot request has zero prepare and zero raster.

The new observation branch precedes the existing write-service path and does not invoke the old overview renderer. Zero supported ROIs avoid creating the image adapter; no-image mode retains empty observed coverage. Unsupported objects are listed explicitly and still participate in occlusion. Local verified frames, MCP construction and external receipt status are separated. The copied old `_tool_result` body is AST-identical after removing the active-specific early branch, preserving its ordinary image contracts.

## P2: short-fact delivery is not closed

Location: `human_eye_plugin/live_spatial_mcp.py`, `_active_observation_content` at line 800 and `_tool_result` at lines 866–874. The active early return does not pass `response_detail`. `_active_observation_content` has no detail parameter and always includes `work`, `generation_work`, `stages`, `generation_stages`, plus frame timing trees and local array paths. There is no existing compact active path that the acceptance caller merely forgot to select. Explicit brief behavior was established from the actual source flow, not by claiming a new executed brief request.

The general schema describes brief as omitting camera/raster diagnostics. Even allowing its documented fallback for unsupported projections, this active implementation has not achieved the plan's intended concise model-facing facts. The issue is visible in real accepted output, not a hypothetical malformed caller.

| Actual recorded active request | Text bytes | Bytes after dropping only work and all timing fields | Removed |
|---|---:|---:|---:|
| ordinary | 24,549 | 19,694 | 4,855 |
| same-source repeat | 23,266 | 19,694 | 3,572 |
| recovery baseline | 24,547 | 19,694 | 4,853 |
| renamed source | 24,588 | 19,738 | 4,850 |
| nonplanar source | 4,874 | 2,696 | 2,178 |
| Total | 101,824 | 81,516 | 20,308 |

The byte counts come directly from the five retained stdio RX text strings. Each was parsed and re-encoded to exactly equal its actual compact UTF-8 bytes; top-level field contributions partition that total including syntax. The 20,308B reduction, **19.94%**, is an offline representation calculation which preserves every fact, identity, path and image. It is not a measured model token, reasoning-time or quality gain, and no candidate was implemented.

For the ordinary request, `facts` is 11,495B and `binding` is 5,518B. Within binding, the repeated 28-object identity list is 4,163B. Facts contain the ROI identities, all unsupported object records, and repeated object information in per-image pixel rows. The broad object inventory is necessary to preserve unknown scope; the repeated representation is not. Per-frame metadata also repeats identifiers and local file/array details beyond what a model needs to map the two native images to their views.

## Minimum useful next repair

Use a single active display projection with a readable, versioned schema; default and explicit brief should use it. Keep explicit full and the retained internal result as the diagnostic evidence path. Do not change acquisition, geometry, view choice, cached construction or image bytes for this repair.

Preserve all these semantic facts:

- Current source/camera identity and revision, including the identifiers necessary to distinguish same-source repeat and rename.
- Object names and stable host/instance associations once, with ROI and unsupported-scope entries referencing that table.
- Every delivered ROI's covered/unknown state and actual reason, complete unsupported object scope, and finite-pool unknown.
- View-to-native-image ordering and image references/hashes, so the model can connect facts to the actual image blocks.
- Actual surface/boundary pixel evidence with front/readable status and the unchanged 16/4/24 criterion, expressed once where shared.
- Local validation, content construction and unconfirmed external/model consumption; reuse and new construction must not become the same claim.

Drop internal phase timestamps, duplicate generation timing, repeated work trees and local NPZ/debug paths from the default projection. Where fields repeat, use transparent object/ROI/view tables rather than opaque abbreviated encodings. Validate semantic equivalence against all five existing real responses and retain byte-identical native images. This can start from existing evidence without another Blender scene or model experiment.

An offline byte-budget illustration for the ordinary recorded response is **5,658B**, versus the actual 24,549B. It keeps all 28 object host IDs/names/instances once (2,657B), six ROI status/reason rows (467B), image references/hashes/native positions (400B), twelve pixel rows plus shared 16/4/24 criteria (470B), unsupported scope (293B), source identifiers (693B), and status/delivery/coverage. This supports an approximately 8KiB engineering target for this fixed response without dropping semantic facts. It is only a layout feasibility estimate, not a validated production projection, model-token measurement or general scene bound. `BRIEF_BYTE_BUDGET_ESTIMATE.json` records component costs and the source RX hash; implementation still needs explicit semantic round-trip validation.

The earlier per-ROI whole-frame readability scan remains a real algorithm optimization opportunity, but the present measured pipeline spends much more time in complete preparation and rasterization. It should not displace this immediate output gap just to demonstrate another tiny CPU gain. Multi-patch discovery and same-object visibility remain the next capability questions after the delivery contract is closed; none are solved by this Host bridge.

## Audit limits and correction

The retained 36 author tests include mocked image construction and compatibility/encoding-failure cases; this reviewer inspected the new tests but did not independently execute them. Ordinary, hot, rename and nonplanar dynamic behavior is corroborated by source and sealed records. Other reviewers own complete pixel reconstruction, source/install identity and cost accounting.

The first offline script used the text substring `256` to detect accidental fixture scaling and falsely matched SHA256 identifiers. The first script and its one-failure result remain as `audit_first.py` and `RESULTS_FIRST.json`. The final check uses AST calls and the exact direct vertex/face mapping instead; no product operation ran. The final `RESULTS.json` stores all 112 checks, five actual wire breakdowns, the P2 finding and read-source hashes.

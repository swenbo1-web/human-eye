# Core integration 001 — independent semantic review

Reviewed commit: `cd863183b18e35d2ca38f75c0756e1c46e1a1ccb`.
Baseline: `b638c499c049604902415965f500f50a9947d34f`.
Core SHA-256: `b99871b94ef74b9e92d422b09fabe4e32024a2a099a3e77d4248b94ff588f652`.

## Decision

Accept the pure-core migration within the registered finite-camera, single-object planar-rectangle domain. No blocking semantic migration defect was found. The next useful batch is the thin, source-bound Host connector; this review does not recommend another micro-optimization round or another complete model benchmark.

Independent checks: **280 passed / 280 checked**. `audit.py` parses source ASTs and archived JSON/Git blobs; it never imports or executes product code. It does not use the author's COMPARISON/AUDIT pass flags as proof. The source and installed result records remain author execution evidence; this review independently verifies their contents and relationship to the previously accepted fixed Git baseline.

## Algorithm migration

Nineteen core functions/classes, including Fraction conversion, canonical triangles, geometry normalization, clipping, camera frustum construction and the complete `CoverageState`, have identical ASTs after docstrings are removed.

The selected projected-area determinant, boundary proof and topology routine equal the accepted discovery code after removing instrumentation; topology also inlines the old temporary `point`. This retains exact coplanarity, consistent winding, edge incidence, connected faces, one boundary cycle, four canonical corners, orthogonal edges, all referenced vertices within that rectangle, and exact area matching. The determinant still uses a nonzero normal component only after coplanarity is established. No tolerance, rounding or replacement area algorithm was introduced.

The complete per-camera coverage loop has the same AST as the old `optimized` branch once counters and the inactive variant branch are removed. Projection caches, strict positive-area occlusion, front/frustum conditions, deterministic triangle order and the original blocker semantics remain. All source triangles remain available for occlusion; discovered rectangles retain every original triangle index.

`prepare_scene` calls geometry normalization once. Discovery and coverage consume the same parsed objects/triangles; neither reparses geometry. The product core contains no verification import, FunctionType mutation or sys.path injection. The default path contains no `work` dictionaries or bit-length scans; diagnostic clocks are gated by `diagnostics` and diagnostics report phase times plus aggregate sizes.

This removes experiment infrastructure without claiming a new general geometric solver. Coverage still scans candidate triangles per ROI and view after its projection/bounds filtering. Exact Fraction arithmetic and repeated per-view projection setup remain part of the accepted algorithm. They should only become a later performance task if actual Host task measurements identify them as the dominant cost.

## API and facts

The session keeps copied cameras and normalized immutable-coordinate tuples. It exposes preparation, next-view selection, feedback, summaries and short facts through normal product APIs. `CoverageState` still starts at SCENE, selects maximal predicted uncovered gain with stable pool ordering, and only adds the intersection of predicted-complete and readable regions after a bound PNG receipt. Repeating an observed view does not increment updates. Changes to the core geometry/camera identities clear prior coverage.

`short_facts` retains ROI/object references, observed view and image references, scalar pixel evidence and finite-pool unknown. It removes per-face indices from the default facts. `image_delivery_scope=local_core_validation` correctly distinguishes local consumption from delivery to a language model. Completed replay facts consistently map five covered regions to `observed_readable` and the remaining finite-pool region to unknown.

Source and installed qualifications each contain the exact ten representation/mode combinations and four control/mode combinations. Their semantic indexes match the fixed baseline and one another. All per-view masks were independently reconstructed from the saved classification rows. Both sets contain four two-frame historical replays with matching updates/final summaries and zero recorded new renders; the sixteen logical reads must remain distinguished from eight distinct historical frame files.

The saved scene/camera change case ends with changed identities and empty coverage/observations. This review does not independently rerun invalidation, image generation or the public API; that dynamic evidence is the sealed author execution. Actual new-pixel recomputation and package/source identity are separate review assignments.

## Host handoff implications

These are existing scope boundaries, not newly observed migration failures:

1. Core geometry identity is deliberately order independent and excludes names and host document/revision metadata. On a same-geometry rebind, the state can retain old observation receipts even when object order/name changed. The image adapter separately detects changed owner order, but that alone is not a Host generation contract. The connector must use its ordered instance mapping plus document/session/revision and camera binding to decide when to create a fresh session. Do not reuse a session solely because the core geometry hash matches.
2. Discovery silently skips objects outside the one-rectangle domain. The current short facts enumerate supported discovered ROIs; they do not constitute an inventory of every observed or rejected object. The connector can cheaply compute capture-object IDs minus discovered-region object indices and return that unsupported scope. An empty ROI list must not be presented as successful full-scene understanding. Per-object rejection reasons are not retained in this core and should not be fabricated.
3. The supplied coherent camera pool owns direction/matrix consistency; `target_to_eye_unit` is used by image readability while the core camera identity covers rational direction, matrices, size and name. The Host binding must cover the complete actual camera specification. The current source contract already documents this requirement.
4. Multiple rectangles inside one mesh, general same-object self-occlusion, near-planar fitting and arbitrary curved surfaces remain separate capability choices. The next connector should measure actual supported/unsupported scope without silently altering supplied world coordinates.

These can be handled within the planned small Host translation/binding entry. They do not require another generic validation layer, a new cache framework or more experiments on this closed pure-core batch.

## Audit correction and unrun work

The first offline AST audit stopped because its normalizer matched the legacy `variant not in (...)` validation as if it were `variant == 'optimized'`. The normalizer was restricted to the latter exact branch. This was a review-script error; no product code, render, timing or model call ran. The correction is preserved in `RESULTS.json`.

No source edits, Git changes, Blender operations, API calls, new raster generation or performance reruns were performed by this reviewer. No independent dynamic API rerun, broad-domain geometric proof or host integration test is claimed.

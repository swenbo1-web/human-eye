# Complete-witness correctness registry

One source case is frozen before any product qualification. Panel_A is the target rectangle at z=0, with corners [-2,-2] to [2,2]. Panel_B is the foreground rectangle at z=3, with XY bounds [3,5] and [-5,-3]. Each has two consistently wound source triangles. This registry supports exactly these fixed inputs and the registered six cameras.

The independent oracle uses exact Fraction coordinates and camera-ray directions. It projects the higher rectangle onto each lower target plane and intersects axis-aligned bounds. SCENE projects B to [-1,1] squared on A, a positive shadow area4 of target area16. The other five directions separate that shadow from A. B has no rectangle between it and any registered eye direction. Front-facing and full-viewport conditions are checked separately from shadow area. No product geometry, coverage or complete helper is used.

Readability is determined after the single qualification from actual saved RGB and raw source-triangle ownership. Triangles0/1 denote A and2/3 denote B. Each identity merges its two source triangles. Independent surface counts and unique contrasting four-neighbor boundary endpoints use the unchanged16/4/24 thresholds. Object owner and patch-owner mappings are checked against raw source IDs. Bounds and owned anchors are recomputed from actual pixels. Geometry alone never supplies readability. In particular, B can be geometrically complete but have no contrasting boundary in SCENE when it blends with A.

## Qualification

There is one qualification process, one actual active_observation call with images, no model and at most six charged rasters. The verifier reads the actual public result, producer SERVICE_RESULT, original requests/replies and saved frames. It checks all supported regions and all delivered pixel rows, then independently determines covered and remaining sets from complete geometry plus actual readability.

The case is realized only when A's first delivered readable row is geometrically incomplete and another actually delivered row is complete and readable. The public complete_witness_pixel_index must identify such a current row. It must not point at the first partial-readable row. Every covered region's witness is checked. Qualification does not require SCENE to cover B. Finite-pool unknowns remain unknown when no complete/readable witness exists.

The receipt at admin/QUALIFICATION.json uses status qualified, not_realized, product_incorrect or evidence_failed. Only passed=true and status=qualified permit the sole formal consumer. Source/prompt/freeze/qualification-run hashes and actual product/model/raster counts are bound. Missing evidence is a failure. There is no scene adjustment, second qualification or product fix within this batch.

## Formal quality and adoption

One fresh P session has one user turn,450 seconds,12 business admissions and six charged rasters. Qualification and formal work share a twelve-attempt total ledger, with independent processes/caches and six-attempt phases. Qualification frames and private truth are absent from the model context.

Normalization records claims from the actual final and its explicitly referenced tool facts/artifact, with exact source hashes and quoted spans. It cannot fill a missing view, reference, coverage row, pixel count or unknown reason from this oracle. The full supported set, observed/remaining declarations, finite-pool scope and target witness are separately checked. A correct target sentence alone is insufficient.

The target witness must name an actually delivered current-session view/reference and give actual surface/boundary pixel evidence. Any stated target-owned pixel must belong to A. A partial-readable view cannot be a complete witness, and multiple partial views cannot be combined. A valid full view may be chosen from any actual current evidence, including a genuinely new native observation, with its extra work retained.

Product delivery, final quality and direct adoption are separate outputs. Additional native observations or geometric/pixel recomputation are retained as supplemental/corrective use. A correct answer reached by those means can pass final quality while failing direct product-only adoption. A read of existing public JSON or cached image is distinct from constructing or recomputing new evidence. Ambiguous/missing adoption provenance stays unknown. Ordinary same-turn errors and corrections remain visible.

The full first result, including failure or not_realized, ends this batch. No N comparison, speed percentage, cost-saving claim, extra model sample or edited prompt follows. Quality/adoption receipts are sealed before cost interpretation. This author implements the oracle and scorer and declares that association in resulting reviews.

The target additionally reports its world center and an actual owned pixel in the selected full witness. Remaining/unknown declarations and unretracted contradictions are separately checked. Every answer tool/artifact source has an actual final-reference excerpt. Infrastructure request excerpts only support adoption tracing and never fill an answer. Repeated same-source cached active calls within the formal tool window are legitimate direct fact use. Qualification still permits exactly one active call. Equal opaque image-ref strings across qualification/formal do not demonstrate reuse; actual generation, current-owner files, source/PID/phase-ledger and byte delivery establish freshness.

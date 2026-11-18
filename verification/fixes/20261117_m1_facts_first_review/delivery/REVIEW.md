# M1 facts-first source and delivery review

The scoped source, compatibility and actual public-delivery review passes for author 544cf4f123c35fbca24b8f425acc30fd3308b178 and product 08a5f3b29283270c97b6d9d6e217bbee6ca7bfc1. Independent execution records 1,112 assertions. No source regression requiring a fix was identified in this scope.

## Source and format compatibility

The source diff changes live_spatial_mcp.py. B selects brief versus full before copying data. It extracts the original source-selection and frame-binding validation into one shared function, called before publication for both details. The brief creates the chosen output fields, then performs one deep copy. Full deep-copies the complete producer and retains its detailed source arrays and mappings. Query, source-region geometry/display handling and source-frame implementation files match the previous DISPLAY001 installed bytes exactly.

Nine independent pure projection or guard invocations verify the actual B definitions without invoking the full formatter. Six nested returned-value mutations leave the producer input unchanged. Source-ref mismatch, source-row mismatch and frame-binding mismatch all raise their original errors. A control containing an unknown metric and both unknown source witnesses preserves those values exactly.

The complete v1 region_ref remains unchanged in the new v2 brief. Default schema changes to source-region-brief-v2, and details points to the existing response_detail=full entry. Existing query validation accepts complete one-row and 4,096-row references after projection. Empty, duplicate, boolean and 4,097-row selections remain rejected.

The one-row and 4,096-row controls cover formatting and query structure. They do not execute corresponding host selections or recompute geometry. The 4,096-row synthetic projection is 24,248 bytes, exceeding the current CLI's 11,964-byte complete-text allowance. Therefore maximum-reference formatting compatibility does not establish complete model-context round-tripping at that size. The registered three-input 10,000-byte acceptance remains the tested scope.

## Original formatter outputs

Fifteen already-existing export RPCs were independently examined. A and B have identical complete default MCP content for each of the three cases. OLD, A and B have identical complete full MCP content for every case, including zero-sample partial observations. The full text equals its complete producer apart from the original transport delivery receipt replacement.

The three actual B defaults contain 9,964, 9,991 and 9,987 UTF-8 bytes. Their complete task facts, reference object, measurement scope, explicit metre unit and world coordinate frame equal the original producer. Their entire nearest source-witness mappings, original display scopes, image references, status and unknown fields also match. Visible and unseen source lists become exact counts. The original detailed arrays remain present in full.

| Case | Selected pixels | Faces with pixel samples | Faces without pixel samples | Original PNG bytes |
| --- | --- | --- | --- | --- |
| S1 | 35,452 | 385 | 363 | 24,734 |
| S2 | 0 | 0 | 748 | 1,895 |
| S3 | 0 | 0 | 748 | 1,881 |

The normal and both zero-sample cases preserve their original observation status and reason. Full curved-surface visibility remains unknown. Every default PNG exactly equals its historical PNG and original frame SHA, and decodes to 512 by 512 pixels. The review constructs no new image.

## Core placement and client budget

The complete facts occupy bytes 420–957 for S1 and 424–961 for S2/S3. Complete nearest source-witness mappings occupy 975–1387 and 979–1391. Distance keys appear at bytes 616/620/620. Pixel keys appear at 1683/1739/1729. Every complete image-reference array ends before byte 4,096. These are independently checked source-byte spans, with half-open endpoints recorded in RESULT.json.

Each complete default fits both stages of the previously pinned rust-v0.152.1 fallback pipeline. After the 33-byte or 34-byte wall-time header, the MCP stage permits at least 11,966 text bytes. The history stage permits 11,964 bytes under its 3,000 approximate-token budget. All three defaults remain unchanged, including their complete original references. Both content-item truncation passes retain PNG entries independently of this text budget.

This budget conclusion uses the same-tag source reconstruction already documented in the prior review and the current actual argv, which has no global or per-tool output-limit override. Provider payloads and a reproducible-build attestation between the installed CLI binary and public source tag remain unavailable. Actual image token accounting remains unmeasured.

## Actual consumers and protocol

All three new consumers each complete exactly one read_observation call with standard _meta and receive exactly one original PNG. Actual CLI tool content equals its owner response and frozen TOOL_RESULT. Original RPC wire requests and responses match the owner records. Each archive has one successful result binding and zero binding errors. The last public final message exactly matches both the runtime final and the sealed answer. Content grading belongs to the parallel independent answer review.

There are zero actual discovery calls in these three new sessions. The 13 original preflight checks cover historical metadata-bearing RPCs, empty discovery and archival replay, nonempty/other tools, rejection followed by legal reading, four-attempt enforcement, deadlines and missing EXIT. All 13 reports pass and their execution-source identities are pinned. This review additionally executes 12 pure classifier/accounting/identity controls and reclassifies all six actual historical empty-discovery completions successfully. It starts no server replay.

Source inspection confirms that the controlled event loop uses the new classifier, retains every completed tool for the four-call bound, distinguishes business calls and empty discoveries, and reports incomplete discovery explicitly. The adapter binds archive_turn to the revised archive implementation, which matches reader-only owner records while independently binding discovery to original protocol RPCs. The previous count and unexpected-discovery errors are addressed in both places.

## Independent-work denominator

This review verifies all 913 shared archive members against original SHA fields with no projected members. It separately parses 15 saved formatter export RPCs and the three actual public consumer streams. It executes nine pure projection/guard invocations, four invalid-reference controls, 12 pure protocol controls and six actual historical discovery classifications.

It reruns zero full formatter calls and zero of the author's 639 formatter invocations. New MCP calls, models, live Blender calls, rasters, PNG/NPZ encodings and paid calls are all zero. No reasoning or analysis event body is inspected or reported. Only this delivery directory is written, and nothing is deleted. The input-pin set is rehashed after the checks.

The reviewer's own AL handle retains its expired historical task740 assignment. The current explicit root task751 delegation supplies this review scope. Parent records remain untouched. No checker failure occurred in this batch.

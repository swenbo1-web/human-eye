# Independent brief transport review

Candidate `cdd2b11693a2586cfea07528c6bca27b93d02499`, baseline `32a1c6eb47cfa84133d92199387339d407a33cb5`.

The transport/image/input-provenance portion passes. No blocking finding was found in this review. This conclusion comes from independent parsing and byte comparisons of archived raw records, together with source inspection; it does not reuse the author's semantic decoder or run the product.

## Actual independent verification

`transport_review.py` recorded 685 checks, all passed, in `transport_results.json`.

- All 183 archived files match their recorded bytes and SHA256. The prior Host archive manifest matches the INPUTS provenance pin. Five historical RX files match the actual prior archive and its recorded origins. Eight copied input PNGs match their prior originals, historical native blocks, image references, sizes, hashes and paths.
- All 17 TX/RX pairs parse as one JSON-RPC record each, preserve matching IDs, and match the saved response objects. The sequence contains initialize, tools/list, then exactly five cases × default/brief/full = 15 tool responses. Concatenating the 17 RX records exactly reproduces stdout; stderr is empty.
- Ten short responses use `active-observation-brief-v1`. Each case's default and explicit brief result are exactly equal. This review validates their image table references and delivery states; the separate semantic review owns completeness of the other short facts.
- Each of the five full values is exactly equal to the prior complete public value after reversing only the registered `/frames/N/image_path` and `/facts/observations/N/image_path` entries. The injected service values also differ from the prior values only in those registered locations. No array path, fact, runtime digest, work counter or other diagnostic value is removed by this comparison.
- All 24 native image blocks match the prior blocks byte-for-byte and in order. Base64 was independently decoded, PNG was loaded through Pillow, and each 512×512 RGB hash matches the saved consumer readback. Image IDs, view names, SHA256 and short-form native block indices resolve to the same historical frames. The zero-ROI case delivers zero image blocks in all three forms.
- All 15 consumer text values match actual wire text. Public `consumer_read_status` remains `unconfirmed`; readback evidence is separate and reports zero model calls.
- Independent sums are TX 3,832 B, RX 311,634 B, public text 155,154 UTF-8 B, PNG 83,400 B, base64 111,216 characters. These are the complete fixed replay sequence, not per-task model token or cash savings.

## Source / installed entry inspection

The product diff changes only `human_eye_plugin/live_spatial_mcp.py` (201 added, 5 removed lines). The historical service, path mapping, bootstrap and audit wrappers are confined to `verification/m4_active_observation_brief_delivery_001/`.

`replay_entry.py:163–274` loads the installed source-bound module, wraps the existing projection/content/serializer callables and calls each original once. It passes the historical service into the existing stdio loop. No candidate-specific replay mode or test branch was added to product source. `run_replay.py:65–92` launches a subprocess and sends the actual protocol requests through pipes. Startup records point to `D:/he_brief_001/product/human_eye_plugin/live_spatial_mcp.py`; its recorded hash equals both that installed file and the candidate source. The launch cwd is outside the repository, and the final source check reports no error.

Historical `runtime_source_sha256` and work counters are intentionally preserved from the Host batch. The current replay receipts separately record zero new capture/prepare/raster/image construction. Therefore these records verify representation and installed transport of frozen inputs, not a new current-scene acquisition or model visual consumption.

## Scope and execution

This independent review made zero product, Blender, raster, model or RPC replay calls. It performed offline JSON/Python/Pillow operations only. No review failures occurred. Source, package and cost-lifecycle review conclusions beyond the bounded checks above remain with the parent and other reviewers.

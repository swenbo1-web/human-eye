# M2-M4-CAPTURE-QA-001 evidence index

REPORT.md is the human report; run_01/ANALYSIS.json independently reconstructs the raw observations without product/driver imports. HISTORY.json preserves offline analysis errors as well as the once-only real denominator.

Frozen QA sources were committed as367784d before any real Blender launch. launch.py,owned_driver.py,build_assets.py,test_preflight.py,PREREGISTRATION.md are byte-frozen in run_01/FROZEN_PLAN.json and rechecked after execution. Parent COMMAND.json includes the exact Python -c verified-source bootstrap. Product identity stays131-source776485105a0616b9aa19b4a7385e6fd01a15ef32bf535d9487444855b1a193e5.

- entry_preflight_01/02 contain source-verified entry checks, both zero Blender.
- run_01/COMMAND_RECEIPT.json records the complete real command and reaped controller.
- run_01/BUILDER_RECEIPT.json and builder_stdout/stderr preserve the one owned builder.
- run_01/assets/ASSETS.json contains the eleven exact recipes and final.blend hashes. FROZEN_ASSETS.json seals them before test workers.
- run_01/case_*/owned contains original NativeSession CONFIG,SESSION,READY,CLOSE,WORKER_CLOSED,WORKER_EVENTS,call SCRIPT/stdout/stderr and the protected input.blend copy. Original helper bytes were used, not modified.
- Each case folder has full/candidate_RAW.json and *_RECEIPT.json, preserving failures and per-ID M3 reasons, plus CASE_RESULT.json with main and cleanup states separately.
- analyze_records.py is a later offline-only reader. Its two initial errors are in HISTORY.json; final ANALYSIS.json validates the executed-text hash independently of Windows newline translation in stored files.
- DELIVERY_MANIFEST.json binds the exact stored bytes for all evidence files, excluding itself to avoid recursion.

The old verification/m4_capture_001 reports and product source remain unmodified. No real re-run is implicit. Asset and owned-copy binaries are retained as evidence; their identical blobs deduplicate in Git. Empty renders folders carry no images.

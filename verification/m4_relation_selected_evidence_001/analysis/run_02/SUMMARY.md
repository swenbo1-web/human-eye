# Saved engineering analysis

The saved-record checks passed with 1589 checks, zero failures and one optional unmeasured channel. All 153 source pins matched.

The seven sessions contain 92 relation requests, 38 native reads and one registered QA change. All 138 received worker RPCs include eight oracle reads and seven close/control requests. Session wall time totals 19.586934 seconds.

## Preparation and kernel work

All 42 same-cycle vertices/full versus OFF comparisons have zero extra received RPC, capture calls, resource builds, triangulation, world preparation, successful normalization/hash work or kernel/rank work. The six original cold sessions perform the same existing work. A geometry change rebuilds one changed resource and recomputes three pairs. FULL then reuses the new generation without additional preparation or solving.

## Default latency

Baseline warm OFF has ten samples with median 37.53295 ms. Candidate warm OFF has twenty samples with median 38.87395 ms. The observed increase is 1.341 ms, or 3.57286%. Every original candidate session has a higher OFF median than either baseline session.

The host.capture median increases by 1.20845 ms and the inclusive worker profile scope by 1.00590 ms. The trace interval outside host.capture changes by 0.00665 ms. These overlapping scopes and their median differences describe the saved run. They do not establish a cause. Default latency preservation remains unproven. The frozen contract has no numeric tolerance to apply.

## Same-field engineering route

Across twenty paired candidate cycles, FULL has median entry time 38.85990 ms. OFF plus the sequential native full-geometry read has median summed entry time 80.87030 ms. The median paired difference is -40.89665 ms. FULL uses one worker RPC while the sequential route uses two. Both carry two objects' world vertices and triangles.

Original-state bodies are 5,361 bytes for OFF, 8,192 for vertices and 9,015 for FULL. OFF plus native bodies total 9,004 bytes. The relation tool descriptor grows by 563 bytes, and the nearest descriptor has zero byte change. Geometry field values occupy 2,819 bytes for vertices and 3,642 for FULL. Actual per-field sizes and per-request response envelopes remain in RESULTS.json.

## Measurement limits

mcp.content_encode includes relation projection and content preparation. Peer timing ends before its final receipt publication, while entry timing includes it. Product RSS records OS process-lifetime high-water marks. QA profiling remains active in every measured runtime request. Its callback-only overhead, worker OS peak, isolated allocations, pure JSON-only duration and model-task benefit are unmeasured. The direct C profiler is empty even when host residency counters show actual mesh work.

The first analysis invocation had a QA-script syntax error before any input processing. Its source and stderr remain under history and attempt_01.stderr.txt. The corrected saved-only analysis is run_02. No runtime request was repeated.

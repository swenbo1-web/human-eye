# Independent cost review — M4-ACTIVE-COVERAGE-003

Fixed author commit: `f2b9dc01621d5b7adb330c096b6460eb3be9c552`. This review only reads existing records and binary payloads. It does not import the author's runner, validator, scorer or cost review, and runs no renderer, Blender, model or performance sample.

**Verdict: recorded cost arithmetic and per-run provenance/timing/count consistency pass.** The full geometry/pixel and source-identity decision belongs to the root review.

The initial audit passed 7,339 valid checks and recorded one reviewer schema mistake: BACK64 means a 64× orthographic span, not a 64×64 image. Both registered input and actual control remain 512×512. The original failure and script are retained unchanged; CONTROL_CLARIFICATION.json supplies five passing explicit corrective checks. No result, threshold, sample or denominator was changed.

## Exact paired result

All 12 preregistered main runs completed in alternating AB/BA order, forming six pairs. Both controls completed separately. There are no discarded or added 003 runs.

| Pair | A full interval (ms) | B full interval (ms) | B/A |
|---:|---:|---:|---:|
| 1 | 1101.0110 | 902.3100 | 0.819528597 |
| 2 | 1332.2047 | 977.1633 | 0.733493359 |
| 3 | 1425.6178 | 972.7417 | 0.682329934 |
| 4 | 1177.8669 | 929.7975 | 0.789390974 |
| 5 | 1268.6173 | 831.7812 | 0.655659670 |
| 6 | 1177.5229 | 871.9686 | 0.740510949 |

Median of paired B/A ratios = **231227282996199 / 313740308347526 = 0.7370021538324989**, a **26.2998%** reduction. All six pairs favor B. A median = 1223.2421 ms; B median = 916.05375 ms. Ratio of arm medians = 0.7488736285319153, a 25.1126% reduction; this is a different statistic.

Primary time starts immediately before Popen and ends after process exit, owned-handle cleanup and parent result/PNG/NPZ/trace verification. Command/output-directory preparation and frozen-source checks outside that interval remain in the separate whole-batch window. Every recorded stage and trace event is inside its original process interval; actual result/launch/trace PID, output directory, scene/camera hashes and published result digests agree.

## Count and byte ledger

| Cost, six main runs per arm | A | B |
|---|---:|---:|
| New full-scene renders | 36 | 12 |
| Returned child pixel rows | 216 | 72 |
| PNG bytes | 94410 | 41700 |
| Compressed NPZ bytes | 820512 | 289500 |
| Raw ndarray payload bytes | 141557760 | 47185920 |
| RESULT + TRACE + frame metadata + publication bytes | 1569705 | 976413 |
| All stored per-run artifact bytes | 2484627 | 1307613 |

Both main arms report six discovered regions, five actually covered and one unresolved region outside the finite camera pool. A uses SCENE/TOP/LEFT/RIGHT/FRONT/BACK; B uses SCENE/BACK. Same-version repeat query generates zero additional images. These set/count claims agree between raw records; independent pixel/geometry correctness is reviewed separately.

Controls cost 10 additional renders (A six; B four). B follows SCENE→BACK→LEFT→TOP, adding 2/0/2/1 regions. BACK has three geometric-complete candidates but zero readable pixel rows; its history of three shortfalls remains while final pixel shortfall is empty. New 003 cost is **58 renders**, below 60. The failed 002 retains its six renders, making **64/66** across the two batches.

All 14 new runs store 162627 PNG bytes, 1311542 NPZ bytes, 3021498 text-artifact bytes and 228065280 raw array payload bytes. All formal stdout/stderr files are empty. Raw payload is the sum of generated arrays, not peak resident memory. Local text bytes are not model tokens.

Four no-image qualification processes are accounted separately, each once: normal, nonzero, timeout and receipt failure. Actual Popen/child/handshake/environment PID agrees for all four; cleanup/streams/handle closure records are consistent. Timeout keeps its original 250 ms post-handshake deadline. Receipt failure retains the one executed harmless marker and does not retry it. Qualification storage detail is in CONTROL_CLARIFICATION.json.

## Full recorded windows and exclusions

| Window | Seconds |
|---|---:|
| 12 main full process intervals | 12.9686029 |
| 2 control full process intervals | 2.3298546 |
| Formal whole batch through analysis | 16.5020107 |
| Formal common parent setup, included above | 0.0814734 |
| Formal overhead outside primary intervals, included above | 1.2035532 |
| Qualification incl. RESULTS write/close | 3.1551422 |
| Qualification + formal recorded windows | 19.6571529 |
| Unclassified gap after qualification before formal batch | 128.6634619 |
| Wall-clock span from qualification start through formal analysis | 148.3206148 |
| Old failed 002 whole batch, separately retained | 1.2057816 |
| 002 + 003 sum of recorded active windows | 20.8629345 |

**19.6571529 seconds is the sum of two measured windows, not the entire development/preparation/model end-to-end time.** The intervening 128.6634619-second wall-clock gap has no reliable compute attribution. Controller startup/initial imports/FROZEN read, final self-publication, development and review time are not measured. They must not be silently described as zero.

The old 002 still has one failed main slot, eleven unrun main slots and two unrun controls; failed-slot time 1.0759542 s and batch time 1.2057816 s remain charged. Its PID ancestry remains unknown. It is not merged into the successful 003 denominator or retroactively relabeled passed.

## What this establishes

For this fixed small rectangular-region / six-camera engineering workload, two selected views reduce complete child-process time by about 26% and the render count by two thirds, despite paying the same startup, import and geometry-index work. Summed dependency imports remain 2.9005 s for A and 2.9510 s for B across six runs; B does not gain by bypassing these costs. This is evidence for acquisition efficiency, not a measured native-model comparison or generic human-like visual understanding.

Not measured: model answer quality, model input/output tokens, rounds, inference latency and price; semantic texture recognition; generic task coverage; peak RSS/heap; OS-cold-cache behavior. No external model/API/Blender call was added in this review or in the registered 003 experiment.

Reproduction: run audit_cost.py in a fresh output directory or change its output destination; it writes exclusively and will not overwrite these audit records. The follow-up clarification only resolves the explicitly preserved reviewer schema error. All original evidence remains read-only.

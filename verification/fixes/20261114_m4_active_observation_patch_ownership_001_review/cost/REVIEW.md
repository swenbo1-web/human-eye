# PATCH-OWNERSHIP-001 independent cost and lifecycle review

Candidate `efe7f77aabdab4f8de47fdb4f8714cb25f301503`; baseline `cdd2b11693a2586cfea07528c6bca27b93d02499`. Cost, construction accounting and lifecycle evidence pass this bounded review. No blocking defect was found in this portion.

The independent script reads archived original records, wire bytes, timestamps and NumPy arrays. It imports no product module or author oracle and makes no product, model, Blender, raster, MCP or benchmark calls. **523/523 assertions passed on the first audit execution.** The benchmark count oracle in this audit is independently written and run once on an existing frame, outside any measured benchmark. These assertions are not 523 independent scenes.

## Counts and delivery

Actual records contain 7 JSON-RPC requests: initialize/list plus 5 active requests. They correspond to split cold/hot, joined cold/hot and cached full. Every request performs one complete source capture, for 5 captures total. Only the two cold requests parse geometry, partition, prepare an index and establish a patch mapping. Each constructs SCENE/BACK/LEFT, for **6 new rasters and 6 new PNG frames**. The three cached requests each reuse three frames and have zero new prepare/raster/mapping and zero new PNG/NPZ payload counters.

Six durable intent slots match six INTENTS records and precede the actual rendering. The declared normal budget is 12 and hard budget 14; actual use remains 6. There is one world geometry represented as 29 split objects and one joined mesh, not two independent assets. Fifteen native image blocks and 2070 public pixel rows include repeat consumption of the six underlying frames; neither is an enlarged experimental scene denominator.

Raw RPC identity, response JSON, receipt byte counts and all seven RX concatenated into stdout match exactly. Stderr is empty. All fifteen native image blocks decode from base64 to their actual saved frame bytes. New and repeated representations have separate byte totals:

| Layer | Independently recomputed value |
| --- | ---: |
| Protocol TX / RX | 1328 / 485084 B |
| Five actual public text strings | 369723 UTF-8 B |
| Fifteen PNG deliveries / base64 | 44095 B / 58800 characters |
| Native image JSON blocks / text JSON blocks | 59610 / 395377 B |
| Six newly published PNG / NPZ files | 17638 / 187544 B |

JSON-block sizes come directly from original RX substrings rather than compact re-encoding. Layers are nested and must not be summed as a total. Four brief responses are 27812/27812/24081/24081 B; full is 265937 B. A full diagnostic query dominates this particular five-call public-text total. That sequence is an acceptance sequence, not the expected cost of one ordinary user question.

## Array and cache accounting

Six NPZ files contain **54 NPY arrays**. Their actual shapes/dtypes/payload sizes/hashes match the frame metadata. Total raw array payload published is **30060048 B**, including **6291456 B patch-owner** and **175632 B mapping metadata**.

Each int32 512×512 patch-owner is exactly 1048576 B. Mapping payload is 29384 B per split frame and 29160 B per joined frame. The mapping repeats in each saved NPZ; the image adapter shares its current mapping in process. Compressed files, raw published arrays and live resident memory are different quantities. No RSS/peak resident measurement exists, so none is inferred from these numbers.

## Time and optimization scope

Request-to-consumer intervals independently match original timestamps:

| Request | Time |
| --- | ---: |
| split cold | 4346.2748 ms |
| split hot | 51.0646 ms |
| joined cold | 4251.1099 ms |
| joined hot | 46.4293 ms |
| cached full | 56.2600 ms |

Whole integration outer wall time is **12.1903417 s**, with **12.1020008 s** from controller start to its final-record prepublication marker. Environment preparation is 8.3566917 s. R1/R2 build-and-install windows are 2.3647317/2.0596308 s. R1/R3 actual unit windows are 1.4027173/1.3470055 s; the separate R2 startup failure executed zero test methods. Kernel benchmark outer wall time is 0.7110997 s.

The frozen benchmark has exactly five alternating pairs, five calls per arm, no warmup and no additional render. Recomputed reference times are `[4329100,4221800,4204900,4168100,4198100]` ns; optimized times are `[1030800,952200,1002600,941600,1026100]` ns. Medians are **4.2049 → 1.0026 ms**, a **76.1564%** reduction. Sums are 21.1220 → 4.9533 ms; maxima are 4.3291 → 1.0308 ms. The ratio of medians (0.23843611) differs slightly from the median of paired ratios (0.23810954); both published definitions are correct.

This is a strong reference: both arms construct the shared contrast boundary once; the reference then scans each ROI mask, while the candidate uses two histograms. Original benchmark code calls each implementation once per recorded call and compares arrays after the timers. Each pair's recorded count array matches my independently recomputed first-frame counts. Optimized arrays are not separately serialized per pair, so pair equality rests on actual checked comparison code/receipts plus the separate full-frame pixel review, rather than two retained arrays per call.

The kernel result is local. Cold exact index times are **3.2330560 and 3.2784676 s**, together approximately **75.74% of the two full cold request-to-consumer intervals**. The six observed readability stages sum to about 8.714 ms, roughly 0.10% of those cold intervals. Further aggregation micro-tuning has little demonstrated whole-chain headroom. A former six-target observation is not an equal-quality comparator to this 138-target candidate.

Capture/index/result sidecars record original-call and serialization/write windows separately. Wrappers call originals once and return the same values; their serialization/fsync costs remain inside outer request and integration clocks. Prepare includes nested partition/index timing and evidence; render/publish includes nested frame stages. These intervals must not be added to manufacture complete task time. Model consumption, tokens, fees, RSS and a model/native task comparison were not measured here.

## Failure and process history

R1 executed 65 test methods with one failure and one error. Its records remain. R2 corrected source-vs-mapping error precedence, then the unit wrapper encountered `InvalidSpecError` before the loader/runner; no UNIT_RESULT exists for that zero-method attempt. The startup exception, original tool receipt and prior wrapper bytes are preserved in preparation evidence. R3 changes the wrapper and passes 65/65. Thus 130 methods actually executed across the two test runs, with one additional zero-method startup failure; the successful tests were not repeated after host Bad Request. The two recorded Python `--help` subprocesses exit zero. No unit test constructed a real raster or launched Blender.

Host Bad Request is conversation-level evidence reported by root; it cannot be diagnosed from successful unit files. Resume receipts and later execution ordering are consistent with starting the first integration after that interruption, without rebuilding identical product bytes or replaying successful units.

Blender QA PID **16604** agrees across launch/ready/cleanup and exits zero without force kill. The held stdio launcher PID **2376** exits zero with reader stopped, three pipes and handle closed, and no cleanup error. The inner server PID **26720** independently has START/FINISH, source-check success and its final counters; it ends before launcher cleanup. No held-inner-server handle proof is invented. The common 600-second deadline is preserved and completion is inside it.

The scoped cost evidence supports closing this capability batch if source and semantic reviews also pass. It does not establish model task benefit or justify another unlimited local-kernel optimization loop.

# ARCH-EXPERT-ENTRY-001 actual QA

Fixed product `c5116e30024ed12825aea6119c0f5172e6b9b46d`; 136-source SHA256 `239cc00a3cf09e9c18874cf0071e811e3244695c93590f806048fab97129b3b9`. Runtime identity and all 136 source file bytes match before/after and at offline audit. No product change was needed.

`actual_run_02` passed all 25 expected tool outcomes: 14 real estimated expert reports, two expected unsupported-source errors, and nine ordinary reads. The 14 reports match independent native-RNA packets evaluated by the same already-loaded expert/model: 25 section scores/flags/native IDs each, maximum absolute severity difference 0.0. This is a same-model source/integration oracle, not an independent validation of model accuracy.

The isolated synthetic fixture has 24,804 mesh vertices and 9,866 triangles. Its explicit patch selects 1,602 sparse native IDs 20000..24803 and 3,200 triangles; compact selection JSON is 19,374 bytes. The original and all three run fixture copies have SHA256 `29922da194a8a05b0399b670282e87d38db8f82007e040518e64d54f3df45cb9` after execution. The saved synthetic dataset and original model were reused; no training or external model API calls occurred.

Owned/shared exercise first, repeat, pose, static edit, DQ unsupported error, recovery, and file-load lifecycle; owned_task exercises first/repeat. Every successful analyze enters capture exactly once. Repeat reads current rows with no static read/preparation. Pose and recovery each perform one static read while reusing the prepared object and doing zero preparation. First/static/load each prepare once. Each DQ error enters capture once but increments successful `work.captures` by zero, and has no direct oracle. Across 16 expert calls there are 16 capture entries, 14 successful captures, 11 static reads and seven preparations.

Ordinary task/nearest reads are performed after unlinking arm mesh/rig from the scene, retaining the same objects in bpy.data; the original objects are relinked for expert queries. All three Blender workers report no NumPy/expert/weights modules before or after those initial ordinary reads. This proves lazy loading in a legal static scene and does not extend nearest support to armature scenes. All 25 read tools leave the opaque action-ledger bytes unchanged and have zero `_locked`, `_runtime`, `_save`, and `_atomic_write` entries.

Tool costs below are individual observed milliseconds, including instrumentation. Full tool RTT spans stdin write to complete stdout line and includes the separate direct oracle. Product method time stops before that oracle; oracle time is its independent native extraction, same-model analysis and artifact write. Inclusive nested profile times must not be summed. Private QA control/capabilities requests are outside these tool costs. Whole-session raw byte totals, including initialization/control/shutdown, are in ACTUAL_COSTS.json.

| Mode | Call | Full RTT ms | Product method ms | Direct oracle ms | Stdio TX/RX B | Host TX/RX B |
|---|---|---:|---:|---:|---:|---:|
| owned | ordinary_task_before_expert | 17.3839 | — | — | 255/1523 | 123/3896 |
| owned | ordinary_nearest_before_expert | 109.2220 | — | — | 219/1479 | 304/4731 |
| owned | first | 540.9740 | 466.3472 | 36.3358 | 19521/13416 | 19438/12745 |
| owned | repeat | 165.7644 | 89.3077 | 35.4802 | 19522/13417 | 19438/12745 |
| owned | pose | 323.4423 | 246.4330 | 34.5452 | 19522/13767 | 19439/13096 |
| owned | static | 461.1202 | 378.9322 | 40.6918 | 19522/13764 | 19439/13093 |
| owned | out_of_domain | 29.7115 | 4.4697 | — | 19522/838 | 19439/151 |
| owned | recovered | 321.0420 | 246.5623 | 34.7937 | 19522/13764 | 19439/13093 |
| owned | load_lifecycle | 438.6916 | 364.1797 | 35.0290 | 19522/13417 | 19439/12746 |
| owned | ordinary_nearest_after_expert | 112.7787 | — | — | 220/1480 | 305/6345 |
| shared | ordinary_task_before_expert | 41.0463 | — | — | 255/1523 | 81396/4257 |
| shared | ordinary_nearest_before_expert | 116.1973 | — | — | 219/1479 | 1470/5190 |
| shared | first | 533.7691 | 455.7407 | 35.1754 | 19521/13416 | 20541/13200 |
| shared | repeat | 163.6410 | 89.1792 | 33.9555 | 19521/13416 | 20541/13200 |
| shared | pose | 316.0652 | 241.0037 | 34.3172 | 19521/13766 | 20541/13550 |
| shared | static | 461.6933 | 364.1430 | 34.3570 | 19521/13763 | 20541/13547 |
| shared | out_of_domain | 30.3699 | 4.4550 | — | 19521/837 | 20541/301 |
| shared | recovered | 317.9960 | 242.5840 | 34.6228 | 19522/13764 | 20541/13547 |
| shared | load_lifecycle | 434.0879 | 359.0436 | 34.5939 | 19522/13417 | 20541/13200 |
| shared | ordinary_nearest_after_expert | 112.5895 | — | — | 220/1480 | 1470/6827 |
| owned_task | ordinary_task_before_expert | 17.5729 | — | — | 255/1523 | 123/3896 |
| owned_task | ordinary_nearest_before_expert | 109.8403 | — | — | 219/1479 | 304/4731 |
| owned_task | first | 520.5685 | 456.5863 | 34.8195 | 19521/13416 | 19438/12745 |
| owned_task | repeat | 152.4022 | 88.8381 | 34.5909 | 19522/13417 | 19438/12745 |
| owned_task | ordinary_nearest_after_expert | 110.0275 | — | — | 220/1480 | 305/4732 |

QA controls are separate: owned has 10 control+capabilities requests, shared has 10 private socket controls, and owned_task has five control+capabilities requests. ACTUAL_COSTS.json retains their individual times and raw stdio/socket byte sizes. Owned control host bytes remain in whole-session wire and are not individually isolated; native control times are nested within control+capabilities timing and must not be added. Default owned worker expressions were checked unchanged.

Source-work counters count selected rows returned/read by the adapter; they do not establish O(selected) native work. The accepted `_native_topology` path builds the whole native BMesh on static reads. Actual RNA bytes/copies and nonresident geometry internals are not exhaustively instrumented. This batch is correctness evidence with observed cost, not a topology performance matrix or performance guarantee.

Same-source M5 reuses the existing independent rigid fixtures/runner, in separate processes. The 0/1/4 cases all complete and agree with direct native horizontal-face gaps; the other three objects stay unchanged. Each case then passes separate task/nearest/task reads with unchanged ledger, outside scheduler-loop timing/counters/bytes.

| M5 case | Confirmed steps / actual setters | Scheduler ms | Lifecycle ms | Host requests | Worker `_capture` entries | Host evidence/full captures | Saves | Loop TX/RX B | Native gap error m |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| zero | 0/0 | 343.8256 | 1413.9261 | 15 | 15 | 5/1 | 8 | 1952/83802 | 6.556510924e-10 |
| one | 1/1 | 457.7133 | 2396.4639 | 19 | 20 | 5/2 | 9 | 4840/96113 | 7.092952728e-09 |
| multi | 4/4 | 786.3029 | 1814.5246 | 28 | 32 | 5/8 | 15 | 11186/132717 | 9.477138519e-09 |

M5 resident work records four to_mesh, four triangulations and four resource builds per case. Method capture entries above include wrappers/nested status work; they are not setter counts. Actual native `_assign_translation` is absent/one/four in zero/one/multi. Scheduler-loop scope ends at end_motion_goal. M5 reports no external model calls or user assets. The complete QA runner sequence was 19,534.3209 ms, including fixture creation/startup/control/oracle/M5; its M5 subrunner sequence was 5,660.1245 ms.

`actual_run_01` is preserved in full: two ordinary tools attempted, task passed, nearest returned the existing conservative static-source-domain error while the armature was still in-scene. Zero expert calls and setters occurred. Only the verification fixture was corrected by scene unlink/relink; nearest/product semantics and the fixed source did not change. Run01 retains its executing harness source snapshots and failure traceback. Across both expert-entry attempts there were 27 tool attempts: 26 expected outcomes and this one fixture-domain failure; M5 is reported separately.

Process records: run01 owned worker 7872, stdio exit0; run02 owned 37792 and owned_task 36444, stdio exit0; shared fixture 25376, its stdio server exit0 followed by explicit controlled terminate/wait return1. M5 workers 24328/35148/16248 each closed with exit0. The fixture creator returned0 and was synchronously waited; its PID was not recorded. PROCESS_CLEANUP.json records the final read-only process query: no task Blender/python command line remains. PID37792 has since been reused by unrelated Windows VSSVC.exe; it is not the completed Blender worker and was not touched.

Actual unknown expert-report behavior is not covered by this estimated fixture. Actual selection exceeds16KiB but not64KiB; larger legal input is CPU covered. Unknown normal semantics were statically reviewed, not dynamically covered in this batch. No actual run or product import was performed by this offline reporter.

Raw evidence: actual_run_02/RESULTS.json, each mode’s stdio/host binary captures, metrics.jsonl, Blender events, full native oracle packets/reports, controls, command files, source identities and fixture copies. ACTUAL_COSTS.json provides per-call costs, work/method counts, whole-session byte totals, M5 data and cleanup. Prior failed attempt is actual_run_01/.

# M4 consumer error contract 001 — independent artifact/replay review

Candidate: `cb5c33a158a9dea06c8151248cc42d2b87c5697b`.

Conclusion: **PASS for the existing replay evidence and retained history.** A separately written read-only parser produced **1558 / 1558 matching assertions, zero discrepancies**. This is an independent artifact inspection, not a rerun of the candidate matcher, archive function, common validator, or author replay script. It does not establish a new live-consumer success rate or performance result.

## What was independently checked

| Evidence | Result | Meaning |
| --- | --- | --- |
| Original owner/CLI transactions | 15 / 15 | Each extracted CLI line matches the original `stdout.raw.bin` at both the declared one-based line number and zero-based byte offset; raw-stream SHA, raw-line SHA, original request/response bytes, IDs, tool names and arguments match. |
| Recorded result projection | 13 success + 2 tool_error | Owner content is unchanged in the CLI result. The real projection has `structured_content: null`, `error: null`, and status `completed` or `failed` matching owner `isError`. |
| Registered matrix inputs | 47 / 47 | Independently reconstructed the declared change from original captures and compared the complete owner JSON tree and CLI item array. No undeclared change was found. Original raw CLI lines are retained separately in every case. |
| Pipeline outcomes and reasons | 45 / 45 | Recorded archive/common outcomes and primary rejection reasons agree with the registered expectations. Where a matcher reason is specified, the corresponding per-attempt rejection agrees too. |
| Direct matcher cases | 2 / 2 | Boolean/object owner IDs have recorded `protocol_mismatch / owner_response_envelope`; these two do not claim archive/common coverage. |
| Archive bytes and contents | 45 ZIPs / 560 members | ZIP SHA and byte size match receipts; member sets have no duplicates and exactly equal their source maps. All 560 members match both the recorded member SHA and the corresponding case consumer file byte-for-byte. |
| Old consumer history | 6 / 6 | The original run and six consumer records match their retained fixture copies. Final bytes, usage objects, raw usage events, usage semantics and original statuses agree. Original strict result remains 4 completed / 2 failed. |
| N3 top-level failure | Preserved | The reconnect/decode error remains present; `candidate_event_projection_only_valid` and original outer acceptance remain false. Interrupted-stream usage coverage remains `unknown`. |
| Local clock arithmetic | Consistent | `64928169200200 - 64923634054200 = 4535146000 ns = 4.535146 s`. Every case interval is ordered and lies inside that window; STARTED/RESULTS reference the same FROZEN digest. |

The denominator is **47 cases**, comprising six real-slot positive pipeline cases (covering the 15 captured tool transactions), four derived owner-style positive cases, 35 pipeline negative cases, and two direct matcher negative cases. It is not 47 independent real tool calls. The 15 transactions include two legitimate business-error responses; those are valid source bindings, not successful business operations. P1/P2/P3 have the same raw completed-line SHA but are verified against their separate original stream locations; they are three transactions, not three distinct response contents.

For owner-style negative cases, the owner-style envelope conversion is a declared baseline transform, then the named mutation is the sole change against that baseline. The positive owner-style fixtures are derived representations, not evidence that the real CLI emitted that alternate form.

## Raw source coordinates

All coordinates below were checked against the raw original files, not inferred from rewritten JSON. Full stream/line digests are in the inspected manifest and the read ledger; each raw-line equality assertion is in RESULTS.json.

| Fixture | One-based line | Zero-based byte offset | Classification |
| --- | ---: | ---: | --- |
| N1_a01 | 7 | 1167 | success |
| N1_a02 | 9 | 14627 | success |
| N1_a03 | 12 | 26394 | tool_error |
| N1_a04 | 14 | 35754 | success |
| N1_a05 | 17 | 44353 | success |
| P1_a01 | 7 | 997 | success |
| P2_a01 | 7 | 993 | success |
| N2_a01 | 7 | 1242 | success |
| N2_a02 | 9 | 15256 | success |
| N2_a03 | 12 | 21832 | success |
| N3_a01 | 7 | 1107 | success |
| N3_a02 | 10 | 14790 | tool_error |
| N3_a03 | 12 | 17226 | success |
| N3_a04 | 16 | 25045 | success |
| P3_a01 | 7 | 997 | success |

## Timing and execution limits

The **4.535146 s is the author's recorded offline matrix interval**, not new user-task latency. Static inspection of replay.py shows initial original/freeze verification before `started` (lines 279–286), candidate load and matrix/archive checks inside the interval, final original/freeze verification inside (319–320), and final RESULTS publication after the clock closes (336). It excludes the initial verification and final result publication. The reviewer independently checked clock arithmetic and boundaries, not wall-clock accuracy by rerunning the author's workload.

The author records no forbidden operations, no new Pro/provider/CLI/actor/Blender/raster calls and no original tool code execution. This review confirms those recorded values and does not claim independent historical process monitoring. The reviewer executed only a self-written local Python data parser (two runs; the second clarified the output label for zero new consumer calls). No candidate code or captured tool code string was imported/evaluated, and no CLI consumer, model, actor, server, Blender or renderer was started.

Not run: candidate matcher/archive/common execution, new live integration, model consumption, rendering, or end-to-end performance. Full 996-file freeze and 1323-file Git identity checks are assigned to the parent and are not duplicated here. Matcher logic and live global wiring correctness are separate sibling/parent review responsibilities.

## Reviewer outputs

- `audit_replay.py`: SHA256 `7b2d3c5ee6213f5f815a48f22f15e832fd8216a1720c477ff4acac979a3f71d0`.
- `RESULTS.json`: SHA256 `f1f3db6a01a15c4a921caa7083b546c90cd8dbb130dbba98c6ba56af7a53b83d`.
- `INPUTS.json`: SHA256 `3ef38303860e89c41eaac1ed16e0866b69c5a8463edbead1d261682f203c3a7d`; paths, sizes and SHA256 of files actually read.

All new output is under `D:/hefe/verification/fixes/20261113_m4_consumer_error_contract_001_review/replay/`. No author inputs, source, prior results, Git state or other agent state were modified. Agent Learning registration is unbound in this child context (`session_context` returned rebind_required; `work_memory_read` required a verified handle). No parent or other conversation handle was borrowed, and no parent's task record was changed.

# M5 owned returned-readback optimization QA

The fixed optimization candidate passes the three real owned tasks once:
zero steps, one step and four steps. Product commit
`7c573a0c982844219832b5803909df4e7b9ea2f3`; 133-source digest
`2f24189bc7c449d2a560bc1534c18ad88b75ed3a036999f8356260c7f5adbede`.
The fixed first-version comparison is the already accepted
`verification/m5_local_loop_001/candidate_run_01`, product `f7b8e5ee...`, source
`4de5ab80d371e4f8917d55005bd4ba95b14946cf5412bfad33643d6c51a875aa`.
That baseline was not rerun. Each new case copies its corresponding accepted
fixture bytes, and leaves them unchanged.

The run began only after the coordinator explicitly transferred the exclusive
Blender window from M6. There was no concurrent Blender run in this lane. All
three default owned workers shut down with return code 0 and `closed:true`.
`PROCESS_CLEANUP.json` finds no surviving recorded PID or scoped command line.

## Actual loop work and physical results

Each variant performs the same 0/1/4 physical setters and reaches the same final
pose. Native RNA world vertices and matrices show that the other three objects
remain unchanged. The target gap error is at most
`9.477138519266293e-9 m`. The native support-interval oracle is exact for these
plain horizontal fixture faces; it is not an arbitrary-mesh oracle.

| Metric, first version to optimization | Zero | One | Four |
| --- | ---: | ---: | ---: |
| capture RPCs | 6 to 6 | 8 to 7 | 17 to 13 |
| actual host `_capture` entries | 15 to 15 | 21 to 20 | 36 to 32 |
| resident capture entries | 1 to 1 | 3 to 2 | 12 to 8 |
| normalization | 6 to 6 | 10 to 10 | 19 to 19 |
| actual MeshEntity constructor | 24 to 24 | 57 to 57 | 134 to 134 |
| strict pair measurement | 3 to 3 | 8 to 8 | 27 to 27 |
| `_save` calls | 8 to 8 | 9 to 9 | 15 to 15 |
| observed complete loop ms | 346.5651 to 376.1688 | 470.0946 to 468.8603 | 842.7491 to 786.5983 |

The private owned readback consumer is entered 0/1/4 times. One capture RPC and
one actual worker capture are removed for each actual setter; no normalization,
strict geometric check, setter or save stage is removed. The observer still
publishes the loop worker counters after `end_motion_goal`, including final
status/end captures. It is byte-identical to the first-version worker observer.

Zero-step time is **29.6037 ms higher** in this observation. The one/four-step
observations are lower by 1.2343/56.1508 ms. These are single runs with profiling,
raw-byte copies, metrics and native snapshots included; observer overhead is
unquantified and not subtracted. They are not general speed guarantees. The
prior 25.1105 ms sum of removed RPC costs is not treated as a promised new loop
improvement.

Loop-only host TX/RX bytes are 1,952/83,799 to 1,952/83,801 (zero),
5,063/99,341 to 4,840/96,116 (one), and 12,078/145,627 to
11,186/132,722 (four). These are physical pipe bytes copied below UTF-8 decoding
and newline conversion. Whole-process byte files additionally include startup,
post-loop checks and shutdown. Nested profile durations must not be summed.

## Readback, delta continuity and state

The five actual apply responses retain their complete real `scene` fields
without any invented `capture_state`. Existing runtime validation consumes those
actual fields; the capture counts and private-consumer entries above correspond
to this reuse. This batch does not replace geometry with a receipt boolean.

After the complete loop and its counter boundary are frozen, every case performs
three read-only calls: task, nearest, task again. Their decoded world vertices
match direct native RNA within 1e-7 m; both task clearance answers and the nearest
distance match the current native gap, with GreyBase nearest. All nine decoded
tokens match the corresponding raw delta packet token exactly. The first and
third task tokens are identical, and the three reads share instance/epoch/
revision while retaining their appropriate selection keys. These tokens come
from actual subsequent captures, not the apply response.

Those checks are separate from loop timing, work counts and wire deltas. Their
durations are 42.0008/33.2906/32.0409 ms and each uses three RPCs. Their TX/RX
bytes are respectively 1,223/11,073, 1,223/11,068 and 1,223/11,067. Ledger hashes
remain unchanged and no extra `_save` call occurs. Candidate lifecycle timings
include this added validation work, so they are not compared as equal workloads
with the earlier baseline lifecycle. See each case's `post_loop_delta.json`.

The first completed step snapshots contain actual motion and matching end
revision, and the last is already satisfied. Inflight/submitting remains a
separate earlier save for each real setter. Final disk ledgers remain satisfied
with 0/1/4 completed steps and their recorded actual motion. Save-stage indices
and contents match the first-version behavior. The `_save` metric counts actual
function entries; the historical raw `committed:true` observer flag means normal
return, not proof of every atomic write. Whole-loop atomic write counts remain
unknown. Nonresident to_mesh, triangulation and world-map totals also remain
unknown; real Python capture/setter entries and resident counters are observed.

## Evidence and limits

`candidate_run_01` passes all three tasks without a retry or failure in this QA
batch. `compare_owned_01.log` and `OWNED_COMPARISON.json` verify raw request/
response IDs, commands, arguments, results, physical byte lengths, fixture
identity, phase snapshots and expected work-count changes.
`RAW_DELTA_AUDIT.json` additionally records exact raw-to-decoded token matches and
the five apply scenes' token absence. Source identities and all member bytes are
checked before and after the candidate run.

This real batch exercises successful geometry and state paths. Loss-of-receipt,
malformed-return, generic-host fallback and external-edit fault cases belong to
the separate targeted CPU regressions; they were not injected into another
Blender batch. There are no model/API calls, user assets or global configuration
changes. No additional optimization or actual probe was run after these three
cases. Original first-version evidence and its prewindow audit state are untouched.

Raw detail includes exact executing script snapshots, default verified worker
commands, source identities, binary pipes, host request/result records, native
and save snapshots, final ledgers, fixtures and close records. All further work
is left to parent packaging and review.

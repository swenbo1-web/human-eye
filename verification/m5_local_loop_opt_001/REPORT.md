# M5-LOCAL-LOOP-OPT-001

Status: implementation, CPU regressions and the three real owned QA cases pass.
Independent raw review passes; file bytes are sealed by `EVIDENCE_INDEX.json`. This is the
single follow-up; no third M5 optimization is part of this batch.

## Fixed product and scope

The single follow-up continues `codex/architecture-local-loop` from accepted
evidence `40eb3a017d927ba501d5786b238db554e3d18537` and product
`f7b8e5ee531918282e65d4cd6cfda573cdcaa93d`.
New product/test commit: `7c573a0c982844219832b5803909df4e7b9ea2f3`.
Its 133 runtime source digest is
`2f24189bc7c449d2a560bc1534c18ad88b75ed3a036999f8356260c7f5adbede`.

Two runtime files change, adding eleven lines and removing one. After the
default owned worker's existing setter, `_capture` and `_verify_readback`, its
current apply response already contains the actual complete scene.
`BlenderProcessHost._readback_after_apply` consumes that response only when the
existing `_default_worker` identity is exactly true. Custom-worker owned hosts
and generic SceneHosts retain their independent capture path.

The guarded runtime passes this actual scene into the existing
`_ValidatedObservation`, non-focal/identity/metadata checks, after-action geometry
verification and goal evaluation. No planned scene, receipt Boolean, old cache or
fabricated `capture_state` replaces geometry. A missing or malformed default
owned scene follows the existing uncertain-readback/quarantine path; there is no
fallback capture to conceal a broken owned response. Lost apply responses still
follow the earlier execution-unknown path, and next-step fresh-capture/external
edit detection is unchanged.

The delta decoder baseline is intentionally untouched by the plain apply scene.
Later task/nearest deltas must catch up using actual resource versions/matrices.
No BlenderSceneHost, blender_worker or live_service implementation, M6 file,
runtime lifecycle, journal boundary, protocol or budget platform changes in this batch.

## CPU verification

`affected_01.log/json`: **88/88 methods pass** across the affected host runtime,
owned process/delta bridge, forward deadline, segment failure/recovery and prior
M5 behavior checks. `new_tests_01.log/json`: **9/9 new methods pass**. Both runs
have no failures, errors or skips and retain the same source digest before/after.
These 97 method executions cover 97 distinct methods.

New checks prove default-owned reuse versus generic/custom fresh captures;
missing/malformed scene refusal; receipt flags not replacing geometry; unchanged
non-focal, metadata, topology, collision and revision checks; no resend after
setter/response loss or bad readback; next-step external edits; and real
fake-bpy host apply plus original delta encoder/decoder catch-up in task/nearest
orders. The latter is an in-process implementation test, not actual Blender QA.

An initial test-file AST parse failed because of a malformed multiline `with`.
`FAILED_SYNTAX_01.py.txt` preserves it. The fixture syntax was corrected before
the first unittest execution, which passed all nine methods; the AST attempt is
not counted as a failed unittest method. Product source was unchanged.

Independent static review passes for both product files and the prepared QA
boundary. The existing CRLF sources are preserved and
`git -c core.whitespace=cr-at-eol diff --check` passes.

## Actual owned QA

The coordinator explicitly handed back the exclusive Blender window after the
M6 process closed. No Blender was started before that handoff. `candidate_run_01`
then passes **3/3 cases once**, with no failed actual attempt. The runner copies
original `m5_local_loop_001/candidate_run_01` zero/one/multi fixture bytes and uses
those accepted results as the fixed baseline; that baseline was not rerun.

Both versions perform exactly **0 / 1 / 4 physical setters**, with the same final
native poses and unchanged other three objects. Rollback and unknown-event
counts are zero. Target clearances match within `9.477138519266293e-9 m`, the
same maximum error as the accepted first version. The fixture files remain
byte-identical before/after. Original inflight and completed journal stages and
actual motion/end revision are unchanged.

| Metric | Zero steps | One step | Four steps |
| --- | ---: | ---: | ---: |
| capture RPC, first version to follow-up | 6 to 6 | 8 to 7 | 17 to 13 |
| actual host `_capture` | 15 to 15 | 21 to 20 | 36 to 32 |
| normalization, unchanged | 6 | 10 | 19 |
| actual MeshEntity construction, unchanged | 24 | 57 | 134 |
| strict pair measurement, unchanged | 3 | 8 | 27 |
| `_save` calls, unchanged | 8 | 9 | 15 |
| first-version loop ms | 346.5651 | 470.0946 | 842.7491 |
| follow-up loop ms | 376.1688 | 468.8603 | 786.5983 |

Actual capture reductions are exactly one RPC and one host capture per setter,
as intended. Numerical algorithms, runtime lifecycle and distinct state
boundaries did not change. `_save` means function entries;
whole-loop atomic-write counts remain unknown, as in the first-version evidence.

Raw loop TX/RX bytes are 1,952/83,799 to 1,952/83,801 (zero), 5,063/99,341 to
4,840/96,116 (one), and 12,078/145,627 to 11,186/132,722 (four). These are actual
pipe bytes below decoding/newline conversion, not model tokens. Raw requests,
results, worker source guards, native snapshots, counters and state events are
preserved under `candidate_run_01`; comparison is in `OWNED_COMPARISON.json`.

Each case then performs **task to nearest to task**, three real delta reads
outside the frozen loop timing/count/byte boundaries. All nine post-loop reads
pass current native-point/distance checks and preserve ledger bytes and save
counts. The apply scene has no fabricated capture token; post-loop tokens come
from actual worker delta packets. The decoder catches up from its existing
baseline rather than being preloaded from the plain apply scene. Post-read
durations are separately 42.0008 / 33.2906 / 32.0409 ms.

Loop time brackets the complete `scheduler.run`. Lifecycle includes startup,
setup, independent verification, close and now these extra post-loop reads, so it
cannot be compared as identical work with the old lifecycle. Single-fixture
times include unquantified observer overhead. Zero-step time is **29.6037 ms
slower** in this observation; one/four are 1.2343/56.1508 ms lower. These samples
do not establish general speed improvement, and the old 25.1105 ms sum of four
extra RPCs is not promised as the new loop saving.

All three owned workers close normally with `closed:true` and exit 0. Scoped PID
cleanup and source-before/after checks are retained. No model/API/Google calls,
user assets, global configuration or M6 files were changed. `CPU_AUDIT.json` is
the historical pre-window CPU snapshot; the actual run results supersede its
then-pending Blender status. `ACTUAL_QA_REPORT.md`, `RAW_DELTA_AUDIT.json` and
`REVIEW.md` document the actual and independent checks. This completes the
authorized M5 follow-up and closes this lane's M5 hotspots; it does not start
another tuning pass.

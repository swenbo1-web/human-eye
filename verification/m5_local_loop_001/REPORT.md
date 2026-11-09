# M5-LOCAL-LOOP-001

First implementation: related regressions and owned zero/one/multiple-step QA
pass. Independent read-only product/raw-evidence review passes. This batch stops before
the coordinator's deep review and subsequent optimization pass.

## Fixed sources

Branch `codex/architecture-local-loop` starts at accepted integration evidence
`52cf0808bf93fe8c6dd87c34c0ef3d0749f67597`. The integration branch is preserved.
Product/test commit: `f7b8e5ee531918282e65d4cd6cfda573cdcaa93d`.
Its 133 runtime sources have canonical digest
`4de5ab80d371e4f8917d55005bd4ba95b14946cf5412bfad33643d6c51a875aa`.

The comparison baseline is fixed Git product
`081252633cdf49b5b35c4dfa33845c7d05438870`, source digest
`d5f3f7d29c201c21611014f0c963afd8c6b5f6fb501b0d94e60f79890d006936`.
`baseline_freeze.json` records all 133 runtime members plus `pyproject.toml`
exported directly from Git. The frozen ZIP digest is
`4105d44b1c833cad97cfd239665dfd17087e0bad84a8c028c6f80e8d5d860f90`.
No mutable competing checkout supplied source bytes, and the working branch was
not switched during QA. Before/after source manifests are retained per variant.

## Implementation

The existing scheduler, segment executor, guarded runtime and default owned
worker remain the execution chain. There is no second executor, new model tool,
authorization surface, global hash cache or timing/budget platform.

- Scheduler `_capture` validates the capture from one coherent
  `capture_evidence` traversal and keeps its original-pose native sidecar. The
  legacy three-field continuation envelope retains a detached
  `capture_confirmation` copy of that same capture; it no longer claims a second
  host sample. Existing native cross-checks and later fresh boundary captures
  remain. Discovery consumes the same validated observation directly, instead of
  calling public `service.observe` and capturing again. Public observation
  semantics are unchanged.
- The existing `_ValidatedObservation` owns detached normalized scene/meshes,
  fingerprint, and any raw capture token retained before normalization. A fork
  gives another synchronous router consumer the same parts. Its local pair
  measurements separate exact requirement options and current mesh ownership;
  collision-only results are never inferred from a clearance request, and
  projected candidates never reuse current-scene measurements. No measurement
  cache is carried into a newly captured observation.
- Private preview handoff retains a detached first plan, complete normalized
  request, scene fingerprint, host binding and readback tolerance. Execute still
  captures fresh state. It reuses the plan only when these all match, including
  the reservation's final caps and effective first-step precision margin.
  Same-revision content changes and changed budgets replan or reject stale
  selection bindings. The fresh observation objects also serve execution
  preparation without another normalization there.
- Execution independently captures its prewrite and actual readback snapshots.
  Each is normalized once for its consumers. Actual readback objects feed router
  verification, goal evaluation and the next residual solve; the strict current
  pair measurement is reused for matching demands. Actual pivot displacement is
  computed once by the runtime and passed into segment accounting. CAS, original
  deadlines, cancellation/commit guards, host nonce and checked readback remain.
- A private completion callback adds actual motion, end revision, next-plan or
  terminal receipt to the same completion save as the known step result. The
  preceding inflight/submitting save is retained. A residual-planning exception
  attempts to save known execution facts before propagating; failed persistence
  leaves the existing blocking state, so a setter cannot be resent as though
  unsubmitted. Final optional presentation/event publication
  runs only after acknowledged durable completion. Direct transform's two saves
  remain the distinct prewrite and post-result boundaries.

The product changes ten runtime files. Two maintained tests were updated to keep
their original fault scenarios meaningful: the deadline injection now hooks the
actual internal router gate, and an old incomplete-motion ledger is explicitly
persisted as a recovery fixture because M5 removes its former natural save gap.

## Python verification and retained attempts

Final `regressions_03.log/json`: **278/278 methods pass**, no errors/skips,
source unchanged at `4de5ab80...`. This includes 13 new behavior regressions,
248 affected maintained methods, 11 ReadContext selection methods and six
resident host/delta/service/MCP pipeline methods. The last six write their new
records under `regressions_03_read_pipeline`; accepted integration evidence was
not overwritten. The prior real 14-warm Blender matrix was not repeated; these
17 read regressions cover its affected cache contracts on the new source.

The new checks cover single evidence/discovery normalization, detached native
sidecars, fresh preview handoff and changed caps/content, exact-demand measurement
isolation, fresh-snapshot remeasurement, durable inflight before setter, complete
motion/end revision on the first completion, post-readback planning/save failure,
historical replay without setters, and optional final presentation failing only
after completion is on disk. The maintained checks include source, cancellation,
original forward deadline, native continuation, rollback reserve, missing/unknown
receipts and recovery behavior.

All local unittest attempts are retained and are not reported as one source:

| Attempt | Source prefix | Executions | Pass / fail |
| --- | --- | ---: | --- |
| `regressions_01` | d71d9321 | 248 | 246 / 2 |
| `new_methods_01` | d71d9321 | 43 | 40 / 3 |
| `new_methods_02` | d71d9321 | 12 | 12 / 0 |
| `regressions_02` | e3438d0d | 277 | 277 / 0 |
| `regressions_03` | 4de5ab80 | 278 | 278 / 0 |

Total: **858 method executions, 853 passes and five preserved fixture failures**,
with no errors/skips. The first maintained failures were the old gate injection
and the removed partial-motion save window described above. The first new-test
attempt accidentally discovered 31 imported fixture methods; two new checks also
compared an unresolved state path with an absolute path, and the imported old
deadline check failed. Original sources/logs and all variant source identities
and product patches are retained. Fixing those test fixtures did not weaken the
execution checks. Static review separately caught and corrected optional
presentation preceding completion persistence; its dedicated thirteenth test
passes on the final source.

Existing CRLF source files are retained. The appropriate byte-preserving check
`git -c core.whitespace=cr-at-eol diff --check` passes; a default whitespace check
had reported those CR characters as trailing whitespace.

## Real owned comparison

`baseline_run_02` and `candidate_run_01` each pass three generated-fixture cases.
The candidate copies the baseline's exact fixture bytes. Both variants use the
default guarded `BlenderProcessHost` worker, `OwnedGoalScheduler`, existing typed
task authority and private connector state/audit paths. A verification observer
precedes the unchanged default worker expression; no production worker path is
substituted. Runs are sequential in the allocated exclusive Blender window.

Physical setter counts are **0 / 1 / 4** in both variants. The final native
clearances match the requested 4 mm / 3.5 mm / 1 mm targets within
`9.477138519266293e-9 m`, with matching final physical poses and the other three
objects unchanged. Files are not saved after the in-memory movements; fixture
bytes before/after match. Raw receipts, native RNA snapshots, full ledgers,
source identities, host requests/responses, physical meters and close records
are retained. `OWNED_COMPARISON.json` contains the offline comparison.
`ACTUAL_QA_REPORT.md` defines the detailed counters, timings and raw-file scope.

Counts below are actual function entries over each complete `scheduler.run`.
They include the final motion status/end captures; they are not inferred from an
empty resource list.

| Metric, baseline to candidate | Zero steps | One step | Four steps |
| --- | ---: | ---: | ---: |
| capture RPCs | 16 to 6 | 18 to 8 | 27 to 17 |
| actual host `_capture` | 25 to 15 | 31 to 21 | 46 to 36 |
| normalization | 41 to 6 | 47 to 10 | 73 to 19 |
| actual MeshEntity construction | 168 to 24 | 206 to 57 | 351 to 134 |
| strict pair measurement | 6 to 3 | 13 to 8 | 35 to 27 |
| `_save` calls | 10 to 8 | 13 to 9 | 22 to 15 |
| `_runtime` construction | 9 to 7 | 9 to 7 | 9 to 7 |
| first-step planning | 2 to 1 | 2 to 1 | 2 to 1 |
| observed loop ms | 655.0154 to 346.5651 | 742.7938 to 470.0946 | 1169.7206 to 842.7491 |

`from_dict` is recorded separately from actual dataclass `__init__`; the two
counts happen to agree in these fixtures. The observer is calibrated for
dataclass-generated code filenames. Strict measurements keep projected and
actual geometry separate. Parent/worker profile times are inclusive and nested;
they must not be summed into a single cost.

The save metric is explicitly the `LiveSpatialService._save` function-entry
count. The historical `save_events.committed` observer field means normal
return, not proof of an atomic write: unchanged read-only observations can skip
the writer. Whole-loop atomic write/commit counts are unknown. Save-stage
snapshots and final ledgers separately demonstrate inflight before execution and
motion/end revision/terminal data in the first completed step state. No claim
that all `_save` calls fsync is made.

Independent review also counts distinct child completion content versions,
excluding repeats of identical child content: zero/one/four-step baseline
0/3/9 versus candidate 0/1/4. Inflight/submitting snapshots remain 0/1/4. These
are observed content-stage counts, not whole-loop atomic publication counts.

Actual owned pipe bytes are copied below text decoding and newline conversion.
Loop-only TX/RX B are 4,011/124,547 to 1,952/83,799 (zero), 7,120/140,067 to
5,063/99,341 (one), and 14,137/186,371 to 12,078/145,627 (four). Whole-process
transport and lifecycle costs are also in each result, with their wider scope.
Loop ms strictly surrounds `scheduler.run`; startup, setup, independent before/
after verification and close have separate lifecycle measurements. Profiling,
wire copies, metrics appends and native snapshots add unquantified overhead,
included and not subtracted. These single synthetic observations establish
work reduction, not a throughput or general wall-time guarantee.

The first real attempt, `baseline_run_01`, stopped in its zero case because the
verification `_save` wrapper omitted keyword passthrough. It made zero setters.
Its source snapshots, response, log and raw bytes remain. Fixing that wrapper
allowed the three baseline and three candidate cases above; the product was not
changed or retried to conceal a failed setter. Thus there are six successful
comparison cases plus one retained failed instrumentation case, not seven
successful tasks. Observer calibration and offline comparison are separate from
the unittest denominator.

## Remaining work and limits

Actual nonresident `to_mesh`, triangulation and world-map totals remain unknown;
the current probe records real Python capture/setter entries and existing
resident counters. It does not proxy Blender RNA objects or interpret empty
C-call events as zero. The readback and physical checks remain independent of
the proposed candidate even when normalized objects and exact-demand results are
shared within one actual capture.

The four-step candidate still makes 17 capture RPCs, 36 host `_capture` entries,
19 normalizations, 134 MeshEntity constructions, 27 strict measurements, 15
`_save` calls and seven runtime constructions. Repeated supervision/native
boundary capture and runtime restoration remain visible; this first batch does
not remove their requirements. Root review should select the next substantive
optimization from this evidence rather than extend this batch indefinitely.

There are no model/API/Google calls, user assets, global configuration edits or
M6 expert-file changes. Process cleanup is recorded in `PROCESS_CLEANUP.json`.
The evidence directory retains generated synthetic assets and frozen source
bytes only. `REVIEW.md` records independent scope/outcome;
`EVIDENCE_INDEX.json` seals this directory's file bytes.

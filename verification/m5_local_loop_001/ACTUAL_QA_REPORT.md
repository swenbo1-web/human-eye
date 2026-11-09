# M5 owned local-loop QA

The accepted Git baseline and fixed candidate both pass all three real owned
tasks: zero steps, one step and four steps. Candidate product commit:
`f7b8e5ee531918282e65d4cd6cfda573cdcaa93d`; 133-source SHA-256:
`4de5ab80d371e4f8917d55005bd4ba95b14946cf5412bfad33643d6c51a875aa`.
Baseline Git commit: `081252633cdf49b5b35c4dfa33845c7d05438870`; 133-source SHA:
`d5f3f7d29c201c21611014f0c963afd8c6b5f6fb501b0d94e60f79890d006936`.

The baseline's 133 runtime members plus `pyproject.toml` were exported from Git
blobs, individually checked against the accepted manifest, and saved under
`baseline_sources/`. No mutable donor checkout was read. The archive and full
member manifest are `baseline_sources.zip` and `baseline_freeze.json`.

## Actual sequence and geometry

`baseline_run_02` runs the fixed baseline; `candidate_run_01` runs the fixed
candidate. Each creates a new default `BlenderProcessHost` and typed
`OwnedGoalScheduler` task, with separate connector state/audit paths. The worker
path is not overridden: the default verified-source expression stays unchanged,
with a verification-only observer script executed before it. No new executor,
MCP action surface, model call, API call, user scene or global config is involved.

All scenes contain four generated plain independent meshes. BluePart initially
has about 4 mm clearance above GreyBase; two distant meshes do not participate.
Targets are 4 mm, 3.5 mm and 1 mm for zero/one/multiple-step tasks. The candidate
copies the baseline's original `.blend` bytes for each matching case. Both runs
leave these bytes unchanged.

The baseline and candidate execute the same 0/1/4 physical setters. Direct native
RNA world points and matrices confirm that all three non-target objects remain
unchanged, BluePart only translates on world Z, and its local mesh/topology,
color, world X/Y, rotation and scale are unchanged. The maximum candidate target
gap error is `9.477138519266293e-9 m`. Baseline/candidate final gap and displacement
agree within 1e-7 m. This native support-interval oracle is exact for these plain
horizontal fixture faces; it is not a general arbitrary-mesh oracle.

## Direct work counts

These are actual function-entry counts during `scheduler.run(spec)`, from the
same observers on both variants. A parent capture RPC and a worker `_capture`
are different scopes: the latter also includes native motion registration,
status, end and the host's internal action captures. In particular the worker
counter snapshot is published after `end_motion_goal` returns, covering the final
status/end traversals rather than stopping at the preceding capture response.

| Case | Setters | Capture RPC baseline → candidate | Worker `_capture` | Normalize | MeshEntity `from_dict` / actual constructor | Strict pair measurement | `_save` calls |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| zero | 0 | 16 → 6 | 25 → 15 | 41 → 6 | 168 → 24 / 168 → 24 | 6 → 3 | 10 → 8 |
| one | 1 | 18 → 8 | 31 → 21 | 47 → 10 | 206 → 57 / 206 → 57 | 13 → 8 | 13 → 9 |
| multi | 4 | 27 → 17 | 46 → 36 | 73 → 19 | 351 → 134 / 351 → 134 | 35 → 27 | 22 → 15 |

MeshEntity constructor entries are independently counted even though dataclass
generates their code with filename `<string>`. A pure-stdlib calibration verifies
that observer path in `observer_calibration_01.log`; it is separate from product
regressions and actual task executions.

The `_save` column counts **actual function entries**, not atomic writes. In raw
`save_events.jsonl`, the observer's historical `committed:true` field means only
that `_save` returned normally. `_save` may skip publication when its observation
baseline is unchanged. The full-loop atomic-write count is unknown and has not
been inferred from this field. `OWNED_COMPARISON.json` states this explicitly.

The actual save-state snapshots show the intended completion merge. In the
baseline, each first completed-step snapshot lacks `actual_translation_m` and
still carries the preceding end revision; a subsequent save adds that data and
another marks the final segment satisfied. In the candidate, every step's first
completed snapshot already has actual translation and matching end revision;
the final one also marks the segment satisfied. The earlier inflight/submitting
snapshot remains separate for every real step. The final persisted ledgers have
complete step receipts, displacement, end revision and satisfied segment state.
Later parent reconcile/authorization saves express different facts and are not
presented as duplicate step completion.

## Observed time and actual pipe bytes

| Case | Baseline loop ms | Candidate loop ms | Baseline lifecycle ms | Candidate lifecycle ms | Loop host TX/RX B baseline → candidate |
| --- | ---: | ---: | ---: | ---: | --- |
| zero | 655.0154 | 346.5651 | 2587.8946 | 1327.3705 | 4011/124547 → 1952/83799 |
| one | 742.7938 | 470.0946 | 2652.1709 | 2360.6777 | 7120/140067 → 5063/99341 |
| multi | 1169.7206 | 842.7491 | 3098.6215 | 1888.2587 | 14137/186371 → 12078/145627 |

Loop time brackets the complete `scheduler.run` call, including grant,
registration, discovery, preview/execute, readback, native review, journal work
and physical closure. Lifecycle additionally brackets owned startup, setup,
external verification captures and process shutdown. Fixture creation is outside
these two times; candidate fixture copies avoid extra creator processes. Runner
sequence stopwatches are 10492.6492 ms baseline and 5607.4314 ms candidate; they
exclude orchestrator imports/output setup and final result publication.

Raw pipes are copied below UTF-8 decoding and universal newline conversion;
`owned_tx.bin`/`owned_rx.bin` retain actual bytes, including startup/shutdown in
whole-session files. Loop byte deltas exclude those outside-loop boundaries.
Read-only comparison checks raw IDs/commands/arguments/results against request
records, actual file lengths against whole-session counters, and shutdown replies
with `closed:true`. Timing includes Python profiles, raw-byte appends, metrics
and direct worker native snapshots; this observer overhead is unquantified and
not subtracted. This is one small sequence, not a speed guarantee or benchmark.

Actual worker `_capture`, resident-capture and setter entries and existing
resident resource counters are observed. Nonresident `to_mesh`, triangulation
and world-map totals remain unknown. No RNA proxy or uncalibrated C-call hook is
used, and no empty event list is called zero work.

## Failure retention and cleanup

The first baseline zero-step attempt (`baseline_run_01`) stopped because the QA
save wrapper did not accept the existing `_observation_baseline` keyword.
It made zero setters and produced no save event. Its raw files, receipt, failure
trace and exact executing scripts are retained. Only the QA wrapper was changed
to forward `*args/**kwargs`; no product was changed. The corrected baseline run
and candidate run then pass six of six task cases without another real retry.
There are seven actual scheduler attempts in total: six accepted cases plus this
retained observer failure. These counts are separate from product unittest
methods, the observer calibration and read-only evidence checks.

All six accepted owned processes shut down normally with return code 0 and
`closed:true` replies. The failed attempt's context manager also closes its
owned process. `PROCESS_CLEANUP.json` checks all seven recorded owned worker PIDs
and the scoped QA command line; none remain. Each fixture creator was synchronously
waited. Source identities/member bytes are checked before and after each accepted
variant. No product source was changed during the actual run.

Remaining observed work includes 15/21/36 worker capture entries, 3/8/27 strict
measurements and 8/9/15 `_save` calls for the candidate's zero/one/multi cases.
These include mandatory native motion-accounting and distinct journal stages;
the report does not assume all are redundant. No further optimization or real
matrix was run after this first QA group.

Raw detail: each run's `RESULTS.json`, `identity_before.json`,
`identity_after.json`, case `host_requests.jsonl`, `worker_observer.jsonl`,
`save_events.jsonl`, saved default-worker command, exact script snapshots and
binary pipes. `OWNED_COMPARISON.json` and `compare_owned_02.log` add the offline
completion-state check; `OWNED_COMPARISON_01.json` preserves the first successful
comparison before that check was added.

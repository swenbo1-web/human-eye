# ARCH-INTEGRATION-001

Status: Python wiring and real Blender integration acceptance passed on the fixed
common product. Independent read-only review passed; evidence is sealed by
`EVIDENCE_INDEX.json`.

## Fixed common product

The branch `codex/architecture-integration` starts at accepted ReadContext evidence
`a656812f352798443b82fa0a81ec461d561c6de8`. It imports accepted M2 resident delivery
`c83304e4263df8654b3dfe9e062c69cd3b811e17` as `bde0e5388013d847c414aea3bdc8f1350a5e227f`,
and the accepted final M2 optimization
`003f87a99c9f2ad6590b2d0ea597eb25cc552f07` as
`defe4e35d865217c6ff8fdd6bee8bf7958201624`.

The final product commit is `081252633cdf49b5b35c4dfa33845c7d05438870`.
Its 133 runtime source members have canonical digest
`d5f3f7d29c201c21611014f0c963afd8c6b5f6fb501b0d94e60f79890d006936`.
The full member list is in `common_identity.json`.

Three necessary wiring corrections follow the two accepted component deliveries:

1. Each shared MCP resident host retains its own frozen scene-residency helper
   and helper instance. A second root's global module alias cannot redirect the
   first host's lazy helper lookup to another generation.
2. Production identity validation checks both frozen host and helper bytes against
   the service manifest, in addition to the existing on-disk host check.
3. Nearest reads use the owned host's configured `timeout` when it has no shared
   MCP `timeout_s` attribute.

These are nine added and two removed product lines in two files. This batch makes
no M5 scheduler/action changes and adds no product debug API. ReadContext and M2
hotspot optimization remain closed after their accepted follow-up passes.

## Python wiring and regression evidence

All 117 distinct selected test methods pass on the final product source:

| Evidence | Methods | What it proves |
| --- | ---: | --- |
| `service_pipeline_03.log` | 6 | Actual generated resident setup, delta decoder, service ReadContext and MCP JSON encoding composed over fake bpy; no socket or Blender |
| `entry_wiring_02.log` | 5 | Frozen helper identity, cross-root module isolation, owned host composition and timeout, pinned real Python stdio initialize |
| `final_python_m2/unit.log` and `unit.json` | 95 | Accepted M2 affected regressions, with source immutability check |
| `selection_regressions.log` | 11 | Selection switch-back, invalidation, isolation and bounded ReadContext caches |

After adding UTF-8 initialization to the verification-only owned launcher, the
same five entry methods pass again in `entry_wiring_03.log`, including the new
encoding-configuration assertion. Thus this fixed product has 122 passing method
executions across these logs, covering 117 distinct methods.

Earlier local runs are preserved rather than replaced. `service_pipeline_01.log`
contains six method executions: four pass and two fail because the new fixture
omitted the ordinary nearest tool's required explicit `session_id`. Its source
snapshot and records are retained in `FAILED_SERVICE_PIPELINE_01.py.txt` and
`service_pipeline_records_01.json`. Supplying the existing required field fixes
the fixture; no schema or product behavior was relaxed. The corrected preliminary
six methods and preliminary five entry methods pass in `service_pipeline_02.log`
and `entry_wiring_01.log` before the final M2 import. Preliminary and final source
digests are not conflated. These logs total 139 method executions: 137 passes and
two retained fixture failures, with no errors or skips.

The six pipeline methods instrument real Python implementation work over fake
bpy. Their `service_pipeline_records.json` is useful wiring evidence, but its
timings/bytes are not a substitute for actual Blender transport. It proves that
raw `capture_state` reaches ReadContext before normalization discards it, warm
task/nearest calls skip normalization and result recomputation, selection AB to AD
to AB reuses the earlier context, and ordinary tool responses do not expose
resource packets or internal tokens. Pure reads preserve the opaque action ledger.

## Isolated entrypoints

`prepare_entry.py` creates local connector configs with current source identity,
explicit fixture loopback port, and separate state/audit paths. It edits no user
config. `prepared_configs/ENTRYPOINTS.json` is an example pinned to an explicit
unused test port; actual runs generate their own configs from the fixture ready
file. `owned_service_stdio.py` composes the existing `BlenderProcessHost`,
`LiveSpatialService`, and stdio MCP server, configures UTF-8 like the normal
launchers, and closes the owned process through its context manager. Its
`--spatial-task-only` flag uses the existing narrow server option.

## Actual Blender evidence

`actual_run_01/RESULTS.json` preserves the one actual batch: **34/34 tool calls
passed**, comprising 21 shared calls, 11 owned ordinary calls and two owned narrow
calls. These include 33 pure reads and one verified owned transform. The
runner-measured sequence took 8,607.0412 ms including Blender/server startup,
fixture controls, observers and cleanup. Its historical field is
`complete_command_ms`; the stopwatch excludes the orchestrator's own Python
startup/imports, argument/output setup and final result-file publication. It used
background Blender `D:/Tools/blender5.2/blender.exe`; all
assets were generated in the evidence directory. No second Blender ran alongside
this batch.

Shared calls run through the existing `production_server.main`, the real stdio
MCP server, the existing `BlenderMCPHost`, an addon-shaped loopback socket, and
actual Blender. Owned calls use the verification-only composition launcher and
the existing default `BlenderProcessHost` worker (`worker_path` is not replaced),
source guard, service and MCP server. A verification observer is loaded before
the unchanged default worker expression. It records the actual host's resident
work counters and independent native RNA geometry after product calls. Both
ordinary and narrow tool surfaces are exercised in both host modes.

The shared sequence covers repeated reads, AB to AD selection switch and repeated
returns to both selections, color metadata, pose, mesh geometry, a Chinese object
name, frame and unit changes, connector restart, scene switch and saved-file
reload. The owned sequence covers task and nearest reads, selection switch-back,
a real verified 2 mm rigid transform, fresh reads of the changed scene, and warm
reads after the change. The owned scene is a private copy, and the worker does
not save its in-memory transform.

All 33 read answers match the independent native RNA oracle within 1e-7 m. The
maximum observed absolute difference is 9.313225746154785e-9 m on the distant
selection. This oracle uses direct native world-coordinate support intervals,
which give the exact distance for these plain generated boxes and the single
bottom-corner mesh edit; it is not a general mesh oracle. BluePart-to-GreyBase
answers track the current geometry: about 4 mm initially, 6 mm after pose change,
5 mm after the mesh edit, and 14 mm in the switched scene. Unit scaling and file
reload also match their current native snapshots.

The actual host token is present at the service capture boundary. Repeated AB and
AD reads retain their respective selection keys; color/pose/mesh/frame/unit
changes advance revision. A connector restart retains the resident host token
but starts a fresh client decoder/ReadContext, which correctly processes two
resources again. Scene switch advances epoch 1 to 2; file reload advances it to
3. The raw labels `shared_frame_epoch` and `shared_units_epoch` are historical
scenario labels: those two controls change revision within epoch 1.

Fourteen designated warm or returned-selection reads have **zero repeated
normalization, MeshEntity construction, task/nearest summarization, exact kernel
calls, resident to_mesh/triangulation/world maps, and client decoder world maps**.
They still capture/validate current state and transport/construct ordinary result
data. The following actual samples show each layer's observed work; timings are
single observations with unquantified observer overhead included.

| Shared narrow request | Host to_mesh / triangulations / world maps | Decoder world maps | Normalize / MeshEntity / task result | Full stdio RTT ms |
| --- | --- | ---: | --- | ---: |
| cold AB | 2 / 2 / 2 | 2 | 1 / 2 / 1 | 120.8897 |
| repeat AB | 0 / 0 / 0 | 0 | 0 / 0 / 0 | 6.7399 |
| first AD | 1 / 1 / 1 | 1 | 1 / 2 / 1 | 170.9599 |
| return AB | 0 / 0 / 0 | 0 | 0 / 0 / 0 | 6.6443 |
| color metadata | 0 / 0 / 0 | 0 | 1 / 2 / 1 | 90.7459 |
| pose change | 0 / 0 / 1 | 1 | 1 / 2 / 1 | 90.7308 |
| mesh change | 1 / 1 / 1 | 1 | 1 / 2 / 1 | 78.0090 |

Owned ordinary cold task is 99.4178 ms and its repeat is 8.3806 ms; first nearest
is 71.2905 ms and its repeat is 9.4482 ms. The real transform is 290.9241 ms,
with three service host capture requests, five normalizations, 94 MeshEntity
constructions, four strict pair measurements and two connector state saves. These
are observations of the current action path, not M5 changes. The worker's C-call
hook receives no Blender RNA events even when resident counters record two cold
to_mesh calls, so it is explicitly uncalibrated. Additional nonresident action
to_mesh/triangulation/world-map work is **unknown**, not zero. Resident counters
and decoder counters remain valid within their stated scopes.

All 33 pure reads preserve the pre-existing ledger bytes (or its absent state)
and make no connector `_runtime`, `_locked` or `_save` calls. The real transform
establishes a ledger, and every subsequent read preserves its digest. Internal
capture tokens, resource identifiers, resource arrays and local vertices are
absent from ordinary model-facing results.

The actual wire recorders copy bytes below decoding/newline conversion for the
owned pipes, actual send/recv bytes for the shared socket, and binary lines at the
outer stdio client. Tool-only totals are shared TX/RX 201,167/82,805 B, owned
TX/RX 5,059/105,032 B, and outer stdio TX/RX 7,962/201,898 B. Whole-session totals,
which additionally include initialization/catalogue and worker startup traffic,
are shared 201,167/82,805 B, owned 5,240/108,967 B, and outer stdio
9,122/258,156 B. Complete per-call costs and raw files are retained in the actual
directory; transport totals are not interchangeable with model tokens or fees.

Both generated `.blend` files retain SHA-256
`f8ac76c8f525aab3a2c5282a6d23bac62eb313027f4c1666732b190735b53589`.
All five stdio servers exit 0. Their owned workers close through the formal host
context manager. The isolated shared fixture is deliberately terminated after
the shared phase and its wait returns 1; it is gone before owned startup. This
is controlled fixture teardown, not a claim that every process exits 0. Runtime
source identities before and after the actual batch match the fixed common
product. No actual tool call failed and no actual retry batch was run.

The offline evidence inspector first used an incorrect MCP response prefix and
failed an assertion. `FAILED_ACTUAL_INSPECT_01.py.txt` and
`actual_inspect_01.log` preserve that attempt. Correcting the inspector to the
existing wire prefix yields **247 passing read-only audit checks** in
`actual_inspect_02.log` and `actual_run_01/SUMMARY.json`. This did not execute the
product or rerun Blender. Inspector attempts/checks are separate from the 139
unittest method executions and the 34 actual tool requests. `ACTUAL_REPORT.md`
contains the session cost table; `actual_run_01/RESULTS.json` contains every tool
cost and native snapshot.

`REVIEW.md` records the independent review scope and outcome. It rechecks source
bytes, requests/responses, work counts, raw transport lengths, native geometry,
ledger files and cleanup without importing or executing the product. No further
product changes or actual runs were needed after this review.

## Boundaries

The isolated fixture is synthetic; this is integration correctness and observed
work accounting, not a scale or wall-time performance guarantee. No model/API
calls, token or fee measurements, user scene assets, Google services, or global
configuration edits are part of this task. No M5 completion is claimed.

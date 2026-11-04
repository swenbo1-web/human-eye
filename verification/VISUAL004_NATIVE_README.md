# VISUAL-BENEFIT-004: neutral native execution fixture

This is a generic persistent Blender/Python transport. It provides no Human Eye
imports, inventory, object selection, relationship solver, task analysis, view
choice or answer. The N consumer writes its own ordinary Python/bpy code. P may
use this exact process transport for its existing `BlenderMCPHost` and the same
native fallback. The product wrapper and its actual costs remain separate.

The coordinator starts one owned worker per condition and keeps its `Popen`
owner alive until closure. P and N use the same lifetime rule:

```python
from verification.visual004_native import NativeSession, ImageLedger
session = NativeSession.start(blender=blender_path, asset=frozen_asset,
    workspace=own_workspace, deadline_ns=original_task_deadline,
    condition="N", expected_asset_sha256=frozen_asset_sha256)
# For P, connect its real BlenderMCPHost to session.host/session.port.
# For N, execute only code authored by its consumer:
result = session.run(consumer_code, timeout_s=30)
receipt = session.close()
```

The original task window is at most 600 seconds, starts before asset read/copy,
and never resets. Startup is bounded by its original window and 30 seconds.
The neutral worker maintains one bpy process and one Python namespace between
calls. Each request is synchronous. Individual timeouts are capped by the
remaining original deadline. The worker watchdog exits only its own process at
that deadline; it never changes a product native-observation lease.

Consumers may execute a saved script through the same session without starting
Blender again:

```powershell
python -B verification/visual004_native.py --workspace <own workspace> --script <own script.py> --timeout 30
```

`--script` must be inside that workspace, uses UTF-8 with optional BOM, and is
limited to 256 KiB. It receives `VISUAL004_WORKSPACE` in its environment. The
consumer can read geometry, vertices and matrices, perform its own math, choose
views, create temporary cameras/lights, render, zoom, or build its own montage.
No camera or math helper is injected. Ordinary scripts can retain variables in
the persistent namespace or save their own intermediate data in the workspace.
They must not edit source geometry, material/visibility, save a blend, read other
conditions or references, or import Human Eye in condition N.

The worker accepts the BlenderMCP-compatible wire shape
`{"type":"execute_code","params":{"code":"..."}}`; successful replies are
exactly `{"status":"success","result":{"executed":true,"result":"stdout"}}`.
This compatibility does not make N a Human Eye baseline: its code and output
contain no engine capture, validator or summary. Script exceptions retain full
bounded stdout/stderr and traceback, and can be fixed within the same task
window. There is no automatic retry. Output is limited to 8 MiB per Python text
stream; direct/native process logs are separately bounded by 64 MiB. Up to 64
execution requests are allowed by default, with a common configurable cap of at
most 128; rejected attempts count as worker requests.

Original scene bytes are copied once into the owned workspace and loaded there.
Before READY, the worker redirects only its in-memory default render filepath
to `workspace/renders/default.png`, identically for P and N. A saved asset's
original `initial.png` path is never the default destination. When present,
that public initial PNG is also hash-bound in CONFIG and checked before/after
calls and in closure/status. Rendering scripts must use owned QA output paths.
Every successful script checks source/copy file hashes and a neutral terminal
fingerprint of non-camera/light object identities, geometry, transforms,
materials, visibility and units. New non-camera/light objects invalidate it.
Temporary camera/light and render state are allowed in this owned process only.
This is soft isolation and final-state detection, **not a Python sandbox**: a
script could bypass rules or mutate and restore state mid-call. Auditing actual
scripts is required. No claim of continuous collision/source protection is made.

An ambiguous client transport failure writes `POISONED.json`; future controller
open/run and worker execution refuse it. If the coordinator retains the launcher
owner, `abort()` kills and waits that owned `Popen`. A reopened CLI controller has
no owner process handle and does **not** claim to kill or reap it: the coordinator
must invoke its owner abort/close, or the original watchdog eventually stops it.
Do not reopen, restart, extend or silently retry a poisoned condition. Closing
from a reopened CLI only requests closure; only the launcher can attest exit/reap.

## Images and actual delivery

`WORKER_EVENTS.jsonl` records actual render-pre, render-post and cancel events,
each code/hash, full output byte counts, failures, terminal checks and changed or
new workspace PNG files. Same-byte overwrites and in-memory/custom image work
cannot all be inferred from filesystem diffs; render events and script audit
must be retained too. The worker's PNG scanner checks signature/chunks/CRC and
dimensions only; it does not claim to decode pixels.

The parent adapter registers every constructed PNG that is offered for delivery:

```python
images = ImageLedger(own_workspace)
item = images.register_external_image(png_bytes, label="caller label",
    origin="native render or engine output")
reservation = images.reserve_delivery([item["image_id"]])
# Only the coordinator's real image tool / image block may now show it.
images.complete_delivery(reservation["reservation_id"], outcome="shown",
    host_event_id=actual_host_event_id)
```

Registration performs a parent-side Pillow `verify()` and full pixel `load()`;
Blender itself requires no Pillow. Each registration records full PNG bytes,
width/height/pixels/SHA and duplicate status, even if it is never delivered.
Construction is not charged as a delivery, but its work remains measured.
Reservations allow at most 8 total images, each dimension at most 1024 and each
image at most 1024² pixels, with at most `4*768²=2359296` pixels overall. A repeated
image is charged again. A montage is charged by its actual width×height and is
subject to the same single-image limit; panel names do not create free pixels.

Reservations are not refunded on failed/unknown delivery. Completion needs an
external host event and records shown/failed/unknown; `model_received` remains
null because this ledger does not attest actual model consumption. A file path,
saved PNG, API ack, reservation or helper flag alone is not delivery evidence.
Root must retain real image content blocks, dimensions/hash, exact host event,
consumer trajectory and any repetition/truncation/failure. Never infer image
tokens from pixels or bytes.

Qualification in 004A uses only independent calibration input and no formal
consumer answers. The coordinator schedules real Blender calibration serially.

## Persistent owner broker

`visual004_session.py` retains the actual `NativeSession` launcher/`Popen` in one
owned broker until closure, instead of leaving each CLI to pretend it can reap
a worker started by another process. Start exactly once per task/condition:

```powershell
python -I -B verification/visual004_session.py --serve --asset <frozen scene.blend> --blender <blender.exe> --condition N --workspace <new owned workspace> --seconds 600 --expected-asset-sha256 <frozen hash>
```

The broker writes `BROKER_READY.json` with a separate loopback port and its
original deadline; its NativeSession/Blender endpoint is separate. Its cold
measurement begins at broker entry before asset reads/copies. Interpreter
startup remains visible in the coordinator's external process wall time.
Both conditions use the same broker and original window. The owner never
reopens or restarts a worker. A P observe request alone dynamically imports
the existing product adapter; N/status/images/close have no product import.

Write an operation JSON file under the owned workspace, then send it through
the generic CLI:

```powershell
python -I -B verification/visual004_session.py --workspace <own workspace> --requestJSON <own request.json>
```

Request schema is exactly `request_id`, `operation`, `args`. No object ID,
task analysis, render viewpoint or solver is supplied by this broker.

- `native_run`: args are `code` (consumer-authored Python), optional
  `timeout_s` and `deliver_paths` (explicit PNG paths inside this workspace).
  Full native output/errors are retained; requested PNGs are decoded,
  registered and delivery-reserved, then returned as `image_refs`.
- `observe`: P only, args are `{"arguments": <actual read-only product args>}`.
  It forwards the actual product result and delivery-reserves its PNG blocks.
- `image_reserve`: args are `{"image_ids": [...]}`; repeated display costs
  again. It does not render, choose images or certify model consumption.
- `status`: empty args; neutral process/image/budget state only.
- `close`: empty args; always available for cleanup, including exhaustion.
  The same actual owner closes/reaps and returns that receipt. Repeated close
  returns the original receipt without repeating work.

Each public attempt, including malformed operations, duplicate IDs and failures,
is charged before execution. At most 48 calls may execute; request IDs cannot
replay earlier work. Script errors may be fixed with a new request in the same
window, but an ambiguous transport aborts the owner and poisons the task.
The close control is separately counted and available after public exhaustion.
P cleanup dynamically calls the product adapter's `close_product(session)` to
release its cached host/service before native owner close. N cleanup never
imports that module. Even product-context cleanup failure does not skip native
owner close/wait, and its error stays in the close receipt.

Public JSON result data is limited to 262,144 bytes. Normal protocol headers,
errors and close controls have a separate fixed 98,304-byte allowance (48×2048),
and both count actual serialized wire bytes: the maximum combined broker text
is 360,448 bytes. A normal result's JSON value bytes form the data part; the
remaining outer response bytes form the control part. No future-call reserve
silently shrinks the first data packet's 256 KiB allowance. Whole results remain in
`broker_calls/N/FULL_RESULT.json`; a text-budget refusal returns an explicit
error, never a truncated answer pretending to be complete. Generated full bytes,
actual public wire bytes, call/error state, elapsed spans and image reservations
are separate counters. If no control allowance remains, or a public request is
beyond the 48-call limit, no payload is sent; the CLI reports explicit budget
rejection. Cleanup still executes and its owner receipt stays in the ledger
even if no control text can be sent. External CLI/protocol error handling is
also retained in host usage/cost, never represented as free task information.

P public results forward `mcp_text` exactly once, image references and MCP/RPC
error fields. The private parsed `actual_product_metadata` alias remains in the
full retained result but is not duplicated into the consumer's text. N forwards
its actual stdout/stderr/script error once, without task-specific processing.
Outer `ok=true` means the broker obtained a valid reply; `operation_succeeded`
and the retained inner script/MCP error distinguish semantic failures. Each
event explicitly counts those observed suboperation failures, so a recoverable
script error is not reported as a successful analysis or hidden retry.

`image_refs` are paths and reservation metadata only. A consumer may combine
one CLI request and actual `view_image`/image-block forwarding in a single
tool orchestration, but only the real image blocks and their host records
establish image consumption. No broker acknowledgement changes
`model_image_consumption_confirmed` from null. All existing PNG count/pixel,
source/fingerprint and original-deadline protections still apply.
The broker also checks the original deadline after complete result/public
serialization and persistence. Expiry during these phases changes the public
reply to an explicit failure and retains the private complete candidate;
there is no valid late success. Close is a separate cleanup operation.

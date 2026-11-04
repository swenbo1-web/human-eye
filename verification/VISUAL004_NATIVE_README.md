# VISUAL-BENEFIT-004: neutral owner-broker contract

## Formal consumer entry: P and N

The only permitted formal scene-execution or observation entry is the owned
broker CLI below. Native scripts run through its `native_run` operation. P
observation runs through its P-only `observe` operation; P's native fallback
uses the same `native_run` as N. No task analysis, object selection, inventory,
best view or prepared solver is injected by this transport.

```powershell
python -I -B verification/visual004_session.py --workspace <own workspace> --requestJSON <own request.json>
```

Formal consumers must not invoke `visual004_native.py --script`, use
`NativeSession.start/open/run`, connect worker/broker sockets directly, run the
product wrapper directly, or import an alternative execution adapter. Those
paths bypass the public attempt/text/image/deadline accounting. Source APIs
and low-level examples later in this document are **coordinator qualification
and debug only**, not extra consumer permissions. Preparing owned request/code
files and forwarding already reserved image refs through the approved image
wrapper remain allowed as described in the common consumer contract.

The formal limit is **48 public broker attempts**, including the common initial
operation and failures. The separately available owner `close` is cleanup.
The low-level 64-default/128-maximum worker RPC limits are internal transport
bounds and confer no additional public calls. P and N have one persistent
owned process/namespace, the same original 600-second task window before asset
read/copy, and no worker/consumer restart or deadline refresh.

Consume the supplied public semantic supplement for all six cases. Its v2
contract and answer bind `public_contract_sha256`; echo the exact supplied
digest rather than guessing it. The supplement defines each public role and
fact, value type, exact enum/unit/tolerance and predicate polarity, including
the V06 inverse predicate. It provides neither correct values/object IDs nor a
solver. Do not infer these definitions from private references or prior tasks.

If a formal consumer bypasses this entry or another frozen rule, retain the
sample, original answer, refusals and all costs, and flag the protocol
deviation. Do not rerun, replace the sample, repair its answer after submission,
rewrite the transport, or silently move it to another allowance.

### Code and actual request size

Consumer code must be at most **262144 bytes as UTF-8**. It is additionally
bounded by the real serialized requests: the broker JSON request is at most
**294912 bytes** (`MAX_CODE+32768`), and the internal `execute_code` JSON request
is at most **266240 bytes** (`MAX_CODE+4096`). The neutral CLI/NativeSession
paths use `ensure_ascii=True` and a terminal LF. P's existing product connector
also imposes its own **32768-byte** complete request limit and fixed encoding;
it is not a consumer-configurable alternative. Quotes, backslashes, newlines,
Unicode escapes and framing consume real wire bytes. A UTF-8 script below
256 KiB is therefore not
guaranteed to fit the complete request. A size or encoding refusal is retained
as a failure; it is not permission to bypass the broker, change serialization
or add a compatibility shim. An ordinary script revision may be attempted
only if the existing broker remains usable and the original budgets allow it.

Through `native_run`, a consumer may inspect geometry/vertices/matrices, do its
own math, retain Python state, choose views, zoom, render, or create a montage.
Necessary temporary camera/light/render setup and owned workspace output are
allowed. Source geometry, transforms, material/visibility, animation and blend
files remain unchanged. N must not import/use Human Eye. No camera or math
helper is supplied. The next protection details describe implementation
limits; they do not add an execution path.

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

The coordinator adapter registers every constructed PNG offered for delivery.
This source API example is coordinator-only; formal consumers request/reserve
images through the broker and use the approved forwarding wrapper:

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

## Owner broker lifecycle and public operations

`visual004_session.py` retains the actual `NativeSession` launcher/`Popen` in one
owned broker until closure, instead of leaving each CLI to pretend it can reap
a worker started by another process. The following start command is for the
coordinator only, exactly once per task/condition:

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

Formal consumers write an operation JSON file under their owned workspace,
then use only the broker CLI:

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

## Coordinator-only qualification/debug internals

The following APIs/commands are not permitted formal consumer entries. The
coordinator may use them on a separately authorized independent calibration
fixture; their costs and failures remain qualification evidence, not consumer
benefit results.

```python
from verification.visual004_native import NativeSession
session = NativeSession.start(blender=blender_path, asset=frozen_asset,
    workspace=calibration_workspace, deadline_ns=original_calibration_deadline,
    condition="N", expected_asset_sha256=frozen_asset_sha256)
result = session.run(calibration_code, timeout_s=30)
receipt = session.close()
```

```powershell
python -B verification/visual004_native.py --workspace <calibration workspace> --script <calibration script.py> --timeout 30
```

That low-level file is UTF-8 with optional BOM and receives
`VISUAL004_WORKSPACE`. The worker's compatible internal request shape is
`{"type":"execute_code","params":{"code":"..."}}`; success is
`{"status":"success","result":{"executed":true,"result":"stdout"}}`.
Consumers must not send that shape directly. Internal Python output is bounded
by 8 MiB per stream and direct process logs by 64 MiB; neither raises the public
data/control allowance. Startup is bounded by the original window and 30
seconds. The existing native-observation lease is not extended.

Only the two readiness signals use the R2 publication path: a unique owned
sibling staging file is completely written, flushed, verified and then linked
once to READY.json or BROKER_READY.json without replacing an existing target.
Unsupported publication or a duplicate/corrupt existing target fails closed;
there is no replace fallback, parse retry, startup sleep workaround or restart.
The tested local filesystem supports this operation; no claim is made for all
filesystems. Other persistence paths retain their existing behavior.

Native startup checks the full record, owned PID, endpoint, helper, original
deadline and source/copy/binary bindings within min(original window,30s),
including after SESSION publication. A failed startup stays failed even if
its SESSION file exists. Worker failure stops and joins its owned watchdog;
launcher failure kills/reaps its own child. Broker readiness additionally
binds the session and owner state. Ordinary client reads and final JSON decode
remain inside the original task deadline. Only bound close cleanup can use
its fixed7s control window; it never extends the task or worker lease.

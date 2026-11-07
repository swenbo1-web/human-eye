This folder prepares SURFACE-NEAREST-ENTRY-001 only. No Blender, NativeSession,
real RPC, product import or actual prepare/run has been performed by its author.
The stdlib simulation exercises the exact QA profile callback body against an
explicit standin function; it does not certify bpy behavior.

After the parent commits the sole product candidate and its source-matched
offline run passes, the parent may run these commands from the repository root:

```powershell
& 'verification/fixes/surface_facts_001/engineering_b/venv/Scripts/python.exe' -I 'verification/surface_nearest_entry_001/qa_prepare/controller.py' prepare --identity 'verification/surface_nearest_entry_001/offline_run_02/EXECUTION_IDENTITY.json' --offline-proof 'verification/surface_nearest_entry_001/offline_run_02/RESULTS.json'
& 'verification/fixes/surface_facts_001/engineering_b/venv/Scripts/python.exe' -I 'verification/surface_nearest_entry_001/qa_prepare/launch.py'
```

Preparation checks 131 source hashes against current bytes AND HEAD blobs,
recomputes the canonical runtime identity using AST-read version constants,
requires the same source SHA in the successful offline proof, copies exact bytes
to a source-only root, and freezes controller/bootstrap/fixture/preregistration
hashes. It does not create a session. `run_01` must not already exist; there is no
retry/reset command. After STARTED.json, any failure remains an incomplete batch.
The run must begin before 16:49 UTC to reserve the original 600 seconds and 60
seconds cleanup before the parent deadline of 17:00 UTC.

The real run starts one owner-held NativeSession with max_calls=9 and one
persistent subprocess executing the original production stdio launcher from the
original verified-source loader. No installed/default MCP config is changed.
The config project_root is the frozen source-only root; state/cache/audit files
are in the isolated run folder. The endpoint is the owned READY host/port.

The 10 preregistered native RPCs are setup1/capture1/restore1,
setup2/capture2/restore2, setup3/capture3/restore3, close. Each capture is an
actual stdio human_eye_scene_observe tool call with known focal_id,
query.mode=surface_nearest and include_image=false. Setup installs a one-shot
bpy-side sys.setprofile hook targeting the original host method code filename
and name, additionally checking the original connector's loaded host SHA. It
mutates only the private Far mesh on call and restores on return, including
exception unwind; neutral helper pre/post fingerprint policy is unchanged.
Each state's controller finally disarms/restores through its registered RPC.
The original asset is never saved. Setup/restore and independent native oracle
scans are QA overhead, and their scans/vertex counts/profile time are recorded.

The packet arrives solely through the production connector's actual socket
response. No packet file is read by the client. MeterSocket delegates actual
socket sends/receives without replacing payloads; _request, _exchange, _code,
host capture and NativeSession helper remain original. The stdio bootstrap's
profile callback observes counts and returned packet work metadata, and calls
each original function normally. All socket TX/RX and stdio frames are saved
with byte counts and wall times. Initialize, initialized notification, tools/list,
one bad image request, ping and the three normal calls are all included.
The notification has no expected response; any stray stdout is retained at EOF.

A successful RESULTS.json also requires the stdio loader execution/namespace
witness, bound source generation, 3 product sockets and 10 total RPC attempts,
three independent answers, restored geometry receipts, original source/helper/
asset hashes, closed NativeSession response, and owner PID wait/reap exit0.
The worker's close event may retain status=unknown; the explicit closed response
and owner reap are the closure evidence. Raw wire bytes remain authoritative.
NativeSession's stored SCRIPT.py may use CRLF; compare decoded text separately
and use raw TX plus the worker script_sha256 for executed input identity.

Limitations: three fixed states prove the implemented entry chain and measured
delivery costs only. No model consumer, paid/external API, Google key, token cost,
formal A/B performance or model net benefit is measured. The profile fixture is
QA instrumentation and its cost must remain visible in all reported totals.

The outer launch.py records the complete controller subprocess command wall, including its interpreter startup/imports/source checks, exact argv, and captured stdout/stderr bytes. Preparation cost stays separate. Profile counters attribute only matched callback bodies: skipped-event filters and fixture persistence are excluded from those counters, while complete RPC, stdio and outer command walls include all instrumentation. Success also requires WORKER_CLOSED.json poisoned=false and final/initial geometry fingerprints both equal READY.initial_fingerprint.

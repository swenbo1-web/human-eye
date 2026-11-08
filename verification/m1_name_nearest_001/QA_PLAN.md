# M1-NAME-NEAREST-001: bounded real QA preparation

This is preparation only. No controller, MCP service, Blender, RPC or consumer was started by the preparing agent. Main agent remains the sole execution owner.

Use the existing `NativeSession` from `verification/consumption_run_001/materials/admin/visual004_native.py` (SHA256 `5bc1152aeafab89220c93edeec51cbe32ace458cc07d3e7d0507b6412b816fb3`) and the existing frozen-source public stdio bootstrap `verification/surface_nearest_entry_001/qa_prepare/stdio_bootstrap.py`. The old complete controller must not be run unchanged: it has the old assignment/window/deadline and a ten-RPC three-state fixture plan.

Use T01's already registered original read-only asset, copied by NativeSession:

`C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_capture_qa_001/run_01/assets/all_overlap.blend`

Expected SHA256: `574bcf2b5b636625ef3aa96e1c42af2a1d3fb83e75c6a04a30e83ff42882292a`. Do not mutate the original or install the old three-state geometry fixture. No asset modification is needed for the new entry check.

Existing binary/interpreter: `D:/Tools/blender5.2/blender.exe` and this checkout's `verification/fixes/surface_facts_001/engineering_b/venv/Scripts/python.exe`. All new sources/config/state/audit/stdout/stderr/socket evidence belongs below `verification/m1_name_nearest_001`. Freeze candidate source identity and exact source bytes before starting, using the existing verified-source loader path as in prior entry QA. Keep source_root fixed throughout the real run.

## Preferred six-RPC matrix with real capture counting

| Physical RPC | Operation | Expected observation |
|---|---|---|
| 1 | Native owner executes only prefixed `qa_profile_setup.py` | Read-only profile hook armed; no product capture or geometry mutation |
| 2 | Public MCP name selector: query mode surface_nearest, objects=[{name:M4_Focal}], include_image=false | Current direct nearest result; obtain legacy ID from this same returned focal.id |
| 3 | Public MCP legacy focal_id using the returned ID, query only mode | Same nearest objects/ties/distance/status as RPC 2 |
| 4 | Public MCP name selector for a fixed nonexistent name | Explicit controlled remote/tool error, no different focal object and no geometry result |
| 5 | Public MCP name selector M4_Focal again | Normal result equivalent to RPC 2; service remains usable after refusal |
| 6 | Native owner's close | Explicit closed response, original owner wait/reap, unchanged fingerprint and protected asset hashes |

Initialize, initialized notification, tools/list and an optional ping are stdio protocol frames, not physical Blender RPCs; prove this by the existing socket meter rather than assuming it. No connection_status, native capabilities, extra directory or pre-AABB request should be added. Set NativeSession max_calls=5, original worker deadline no more than 600 seconds and within the current QA window; preserve original request budgets. Assert exactly one session and no more than six total physical requests including close. No model context is needed.

The new ID-selector path is checked in the targeted offline tests. If main chooses to prove all three entry forms physically and does not require in-worker profile counting, use name → query.objects[id] → legacy focal_id → missing name → name recovery → close: still six RPCs, with no profile setup RPC. Do not combine this five-product-call alternative with an extra setup RPC.

## Reusing the existing public entry

The existing `Stdio` behavior in the prior QA controller sends full public JSON-RPC frames and captures TX/RX plus owned stdio PID/wait evidence. Reuse that structure with new output paths, the newly frozen runtime plan and this task's token. Child argv may be the existing interpreter with `-I`, the unchanged prior `stdio_bootstrap.py`, and the new `RUNTIME_PLAN.json`; no model CLI is involved.

Build the same isolated connector config as prior QA: project_root/source_root frozen to this candidate; `expected_identity.source_sha256` equals the new canonical digest; Blender host/port come only from this newly owned NativeSession READY; request_budget_s=20 and native_visual_timeout_s=10; no default9876 or shared GUI. Match SOURCE_IDENTITY/product manifest, helper, binary, original asset and copied asset before first request.

Meter Native owner setup and close wires separately, as prior `transaction` helper did. Existing stdio bootstrap records all connector-owned endpoint socket wires, exact original requests and connector call profiling. Save every public request/result/error and its local monotonic timing. For equivalence, compare semantic fields such as result_kind/status/focal/nearest_objects/best_known_objects/distance_m/coverage/unresolved/unit; trace/session metadata can differ and is not itself a result mismatch. Do not manufacture final nearest packets or supply a previously captured packet as input.

## Capture counts and safety boundary

`qa_profile_setup.py` is an unexecuted draft using the old fixture's existing `sys.setprofile` mechanism, with geometry mutation and truth scans removed. Main must prefix QA_PLAN with the fixed host source path/SHA, a new profile output path and expected_nearest_calls=4. It counts the four original host calls, `_objects`, `_capture`, capture_task_scene and capture_scene, recording callsite line numbers. It self-disarms after the fourth original nearest return, including the missing-name exception return. Profile body time remains inside RPC/outer wall and is reported separately; it must not be deducted as free work.

The inherited host currently has two `_objects(graph)` calls per successful nearest: the first primary directory enumeration and the final coherence recheck. Name resolution must add zero extra enumeration or RPC. Report both observed calls rather than falsely claiming a total of one or removing the existing coherence protection. The original geometry acquisition `_capture` should execute once on successful calls, and neither task capture nor a pre-AABB route should execute. Missing name should reject after primary resolution and before geometry capture. Offline fixture counters and raw RPC/profile evidence should agree.

`HostRemoteError` from a well-formed readonly host error does not poison the connector (`except HostRemoteError: raise`); the subsequent successful name call is the required real proof. Any unknown transport/execution outcome is retained and not blindly retried. A protocol error response alone is not a claim of correct refusal unless the raw error and zero geometry path are observed.

After finishing, close the stdio process by EOF and owner wait; record any fallback kill as such. Close the NativeSession with the original owning object, not `NativeSession.open`, since only the original Popen can attest exit/reap. Keep WORKER_CLOSED, close response, initial/final geometry fingerprint, original worker deadline, original/copied asset SHA, helper/source SHA and exact source drift check. Preserve missing receipts and errors without inventing graceful exit or exit0. No global process scans, signals to unrelated PIDs, source/original asset writes or consumer restarts are authorized by this preparation.

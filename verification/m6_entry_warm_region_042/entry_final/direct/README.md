The fixed endpoint is `127.0.0.1:48142`. Its immutable connector configuration is
`D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/E_FINAL_001/direct/CONFIG.json`
(674 bytes, SHA256 `1a416026a191a6b6f535fcd25c1acf55a2168cf8ca72aba98a7c7947f512ea2e`).
Use the same configuration for H0, H1, OFF and the normal MCP server named
`human_eye_live`. The exact model tool is `human_eye_connection_status({})` and
PostToolUse matcher `^mcp__human_eye_live__human_eye_connection_status$`.

The ordinary production command is recorded literally in external `PLAN.json`:
the bound 041 R3 dependency Python, `-I -B`, original installed
`target_runtime_entry.py serve --config CONFIG.json`. No product file, add-on or
worker method has been edited. `gui_owner.py` derives from the verified 036 owner
with only output root, cycle ID and the port reservation changed; the original
unmodified Blender add-on and worker sources are copied/pinned in `support/`.

An authorized coordinator can start a later endpoint using the bound Python:

```
python -I -B endpoint.py serve --output NEW_SESSION_DIRECTORY --window FRESH_WINDOW_JSON
```

`NEW_SESSION_DIRECTORY` must be a new directory under the external `direct/`
root. `FRESH_WINDOW_JSON` is a real coordinator exclusive-window receipt with
`status="available"`, `cycle_id="M6-042-E-FINAL-DIRECT"` and a nonempty `token`.
The preflight window only authorized the completed preflight; obtain a fresh
coordinator window for formal events. The owner writes `CONTROLLER_READY.json`
with actual controller/GUI PID, exact config, port, deadline and stop path. Wait
for that file before sending a desktop turn. The real GUI event loop/add-on queue
serves all requests directly; no relay exists. Only its expressly owned Popen can
be closed. A fixed owned deadline of at most 590 seconds remains in force.

To stop the same owned session, invoke:

```
python -I -B endpoint.py stop --output SAME_SESSION_DIRECTORY
```

This writes one explicit stop request; the owning controller performs the
original queued stop/unregister/GUI quit and verifies native exit, source bytes
and port absence. Wait for `CLOSE.json`. Restart with a new session directory and
the same immutable config/port. A busy port fails admission; no other listener or
resident session is terminated. The Python API `EndpointOwner(folder, window)`
exposes `.pid/.port/.host/.process/.workspace/.ready/.run/.close()` for an owning
coordinator that retains the object.

Preparation was completed once. Do not rerun `prepare` over the frozen plan:
`SOURCE_REPAIR_02.json` separately binds the recovered harness source after the
first rejected request. The original PLAN and first source remain unchanged.

Completed direct evidence is under `preflight_02/RESULT.json`. Two independent
ordinary GUI PIDs (18152, 16392) served the same port; both MCP EOF exits and both
ordinary GUI exits were zero, and both final native TCP tables had no listener.
Before/after snapshots prove the 12-mesh G60 geometry unchanged against original
local vertices, native triangles and transforms. The explicit nearest request
uses the published 041 `session_id="m3-bvh-040"`, `response_detail="full"`,
`include_image=false`, and `surface_nearest` for `Target`. The complete geometric
answer matches 041: `Peer_000`, 11 candidates, distance
`0.0030000059049562493` m and the same points/direction. Only trace/binding
metadata is excluded from cross-instance comparison.

The first attempt `preflight_01` preserved a genuine schema rejection because the
draft short request omitted required `session_id`. It executed no nearest
geometry and closed cleanly. The request was completed with the exact published
041 fields; no product or config patch was made.

The separate manual positive `hook --probe` consumed the literal unchanged
related prompt from `FORMAL_PROTOCOL_02.json`. Its actual audit contains one
`observe`, one `host_hook`, one request trace and no images. The literal output
retains 12 named mesh rows and `correlation.request_id`; `observation_id` is null.
It is manual evidence only. No model, automatic dispatch, trust provisioning or
desktop context delivery was performed or certified here. A status tool reply
declares `host_connectivity_checked=false`; it is not a socket connectivity
probe. The original queued add-on ping supplies separate real socket evidence.

`preflight_02/AUDIT_END_COPY.jsonl` and `AUDIT_CHECKPOINT.json` preserve a full
74,114-byte audit checkpoint (SHA256
`8d3e1557a5668675d23bc4600aa4a940d604a90fae5fd5a1b458e25388d57ff0`).
The absolute live audit path remains appendable for subsequent genuine events;
the checkpoint identifies a prefix rather than freezing the live file. Preserve
new slices and clocks separately. Direct preflight is not a formal timing sample.

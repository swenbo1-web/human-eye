# Bounded current public assembly probe

The controller is prepared only; its author performed source reads, writes and
AST parsing. No prepare/run, product import, Blender/session/RPC or model was
executed by this subagent.

Parent commands, using the existing engineering interpreter:

```powershell
python.exe -I verification/complex_reentry_001/qa_control.py prepare --source-freeze <absolute SOURCE_FREEZE.json>
python.exe -I verification/complex_reentry_001/qa_control.py run
```

Preparation uses the parent's exact new `sources` and `inputs`; it does not
replace inputs. It verifies 131 source bytes/current/Git/canonical identity,
the original asset/patch/snapshot/task hashes, fixed window and unchanged
patch-capable `verification/visual004_native.py` Git bytes. The accepted old
production stdio bootstrap and Stdio/MeterSocket definitions are reused.

The sole NativeSession has its original 600-second deadline and at most 15
non-close calls. The controller reserves one of 16 total physical RPCs for
close. Public observations are capped at nine. No setup/profile RPC occurs.

First request is exactly current public task selectors Object_01/Object_03,
requested_facts=['solid_relation']. A task_query partial or outer isError label
is not itself classified as transport/argument failure. The fact's own status
is checked only after source identity, object IDs, selection 2-of-4, metres and
raw selected capture bind to the exact original local/matrix geometry. Captured
triangles must partition the original polygons; no fixed quad diagonal is
assumed. The raw socket and public packets remain intact.

A bound unknown/unsupported first fact immediately ends the batch and closes
the owner (one observation plus close: two RPCs). The remaining eight planned
observations remain not_run. Final loaded-source witness must also verify
before the result is classified as confirmed capability gap. No surface-zero
or required global escape-vector inference is used.

Only if first solid_relation is measured, the same session continues: one
initial native readback, other two initial candidates, unchanged readback and
three observations, the original one-shot QA patch, changed readback and three
observations, close. Total 14 RPCs: nine observations, three readbacks, patch,
close. Continuation requests solid_relation and existing surface_proximity;
surface distance is never used to infer penetrating. The first minimal probe
intentionally did not request distance. If its measured value unexpectedly is
not_penetrating, the accuracy mismatch is retained, and that first pair's public
distance remains explicitly unmeasured; no tenth observation is added.

All readbacks verify original polygons, matrices, binary64 local/world points
against initial or changed sealed snapshots. QA advance uses the pre-existing
patch-enabled helper method, not a product action or an unrestricted fixture
script. The patch is never replayed after unknown execution. Parameter/source/
transport errors remain errors and do not become capability gaps.

Run output is `qa_01`; public frames are `mcp_frames/NN`, owned product socket
bytes are `stdio/socket_N`, control RPC bytes are `rpc_*`, and the helper's
SCRIPT/stdout/events/ready/closed/owner records remain under `owned`. LF logical
execution and Windows CRLF artifacts are distinct boundaries. Final worker
unknown close events remain unknown; a closed response/owner wait is separate.

The controller does not retry an unknown request, reopen a worker, alter source,
reset a deadline, use models, modify STATE, or create a new task framework.
Parent alone freezes, launches once, audits, seals and reports the batch.

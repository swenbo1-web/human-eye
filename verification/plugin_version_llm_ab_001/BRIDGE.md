# Identical installed-product MCP forwarding adapter

`bridge.py` is an experiment-only stdio MCP adapter, not a formal MCP release.
Run it with the selected wheel's independent venv interpreter:

```
<venv>/Scripts/python.exe -I -B -X utf8 bridge.py --cell <absolute-cell.json>
```

Both versions use identical adapter/initializer bytes and tool schema. The
adapter does not change sys.path or synthesize a `human_eye_plugin` namespace in
its controller: normal imports must resolve to the configured installed
site-packages and report `installed_distribution`. It checks the frozen runtime
source identity before creating the host.

Required cell fields: `audit_dir`, `fixture_input`, `blend_file`,
`expected_install_root`; optional `blender`, `expected_source_sha256`. The input
JSON contains exactly one `cases` row, using the frozen TASKS.json row. It is
private setup data; the public task description returns only TASK_FIELDS, scope,
saved frame and no-save condition. Case names, expected statuses, initial area
loss and treatment labels are not returned by describe_task.

The public tools are `describe_task({})` and
`run_arm_goal({"event_id":"<registered event>"})`. The latter builds the exact
frozen ArmAxialTaskSpec and calls the installed OwnedGoalScheduler.run. There is
no automatic task loop, geometry solver, candidate assignment or canned result
in this adapter. Product receipts are returned unchanged. Same-event repeats
are handled by the product's actual idempotent history and are recorded as
separate public calls, without replaying host writes.

MCP initialize creates one owned Blender worker eagerly, identically for both
versions, so even a consumer choosing no action has a real initial/terminal
state. The original default verified worker expression and source bytes remain
unchanged. The QA startup expression appends the actual installed site directory
to the *end* of Blender's path, so metadata can locate the wheel while Blender's
native NumPy remains first. The initializer reads the installed runtime_identity
through the existing SourceGuard executor and saves the child's actual
installed-distribution identity and 137-source manifest. This is read-only
metadata instrumentation, not a new product loader or an authorization claim.

The initializer creates one fixture and makes only three starting-basis
assignments. An optional shared rigid `fixture_world_matrix` is applied to mesh
and rig. It saves INITIAL_NATIVE, wraps the real product method to capture full
before/after RNA and actual consumed source, and times the existing expert
prepare/static-parser functions after their original loader returns. Cold
dependency loading stays in its original location. All candidate setters remain
inside the installed product method. Child NumPy version/path are saved with
each actual method record.

A read-only stdin iterator observes an original worker shutdown command, saves
FINAL_NATIVE, removes only QA-created objects/data and closes host residency,
then yields the original command text unchanged. It never changes a request,
candidate or receipt. After scheduler.run returns, the adapter closes/reaps the
owned host and finishes this QA *before* publishing the unchanged tool receipt.
The MCP process can still serve task metadata and product-retained same-event
replays; it does not start another host. This avoids relying on CLI stdin EOF,
because the actual CLI can terminate its MCP process tree at completion.
Normal stdin EOF remains an idempotent fallback. Lost or uncertain mutation
delivery is not automatically retried. A consumer that never invokes the goal,
or another forced early termination, can still lack terminal QA; that must stay
an incomplete result rather than a synthetic pass.

Evidence per audit_dir includes BRIDGE_RESULT (calls/RPC/cost/source identity),
MCP_PROTOCOL (complete public requests/responses), pipe text RX/TX, SOURCE_FREEZE,
PROCESS/COMMAND, installed child identity, initial/final native geometry,
case_01 (actual product transaction), durable product state and cleanup. Byte
counts cover returned tool catalogue and literal text blocks; image bytes are
zero. calls[].scheduler_entry_ns brackets only scheduler.run, while
post_run_close_ns brackets subsequent host close/QA. Original elapsed_ns is the
whole adapter tool implementation and includes close. total_bridge_ns ends at
owned-host close, with its scope explicitly recorded; the MCP process can remain
alive. Full model session wallclock, usage and final-answer timing belong to the
outer CLI runner and must not be replaced by these shorter inner measurements.

`preflight_01` contains exactly two auxiliary no-model protocol runs, A then B,
using the transformed reachable task. Both first calls returned satisfied with
two real setters; repeated event calls sent no additional mutation RPC. Each
owned process exited normally and all generated data was cleaned. These checks
are not part of the formal consumers. An actual initial consumer then exposed
the CLI process-tree shutdown behavior; its unchanged first bridge/initializer
bytes are archived in infra_attempt_01/code. preflight_02 repeats one auxiliary
A/B no-model protocol pair with the lifecycle fix, additionally proving close
completed before the first tool response was ready and replay sent no RPC. Its
exact f3a bridge bytes are preserved under preflight_02/code. The final b960
bridge only adds scheduler/close timing separation after that successful
preflight, was AST-checked, and did not run another product/model trial. No
failed preflight attempt ran; the earlier real-consumer infrastructure failure
remains separate evidence and must not be omitted from attempt totals.

# M1 eval runner interface

Preparation only. These adapters import without starting a model, product process or Blender. The root owns installation, scene generation, truth, scoring, fixed 27-cell sequence, no-model preflight and any later GO decision. No model consumer has been launched by this implementation task.

## Actor

Run `actor.py --config <config.json>` with the dependency interpreter. The JSON fields are:

| Field | Contract |
|---|---|
| `group` | Exactly `N`, `C` or `S`. |
| `task` | Root's task identifier; retained as configuration, not sent to the model. |
| `output` | New actor-owned directory; must not exist. |
| `endpoint` | Root's endpoint JSON publication path. |
| `asset`, `asset_sha256` | This cell's scene bytes and expected digest. |
| `blender` | Root's fixed Blender executable. |
| `worker_deadline_ns` | Absolute `perf_counter_ns` deadline fixed from the start of the complete 570-second cell. |
| `dependency_python`, `entry`, `install_root`, `source_sha256` | Copy unchanged from `installation/READY.json`; identical for C/S. |
| `read_schemas` | C/S only: read the respective `catalogues/C/PUBLIC_TOOLS.json` or `catalogues/S/PUBLIC_TOOLS.json` as a JSON array; exact actual-directory order and schema bytes. |

N exposes the original `execute_blender_code` schema alone. C adds only `human_eye_scene_observe` and `human_eye_connection_status`. S adds only `human_eye_spatial_relations` and `human_eye_surface_nearest`. The underlying C process retains the ordinary product directory, but the consumer broker exposes only the frozen two read tools. S launches the same entry with the single extra `--spatial-task-only` flag and verifies its complete product directory has exactly two tools.

C/S initialize the actual stdio product, record identity and complete `tools/list`, compare the exposed schemas with the frozen list, then issue the same `ping`. They do not privately call connection status or warm geometry. N does not start a product process. `PLUGIN_INITIALIZE.json`, `PLUGIN_TOOLS.json`, `PLUGIN_PING.json`, `plugin/START.json`, per-RPC raw TX/RX and `plugin/CLOSE.json` retain the actual provenance and lifecycle evidence.

The actor forwards original arguments. For ordinary scene observation, omitted or non-false `include_image` is rejected and counted; it is never rewritten to false. S passes its original task arguments and has no image field. An unexpected image content block is rejected before delivery. Native code capability is the original helper's capability, not a replacement solver.

Budgets remain 32 tool attempts (including errors and refusals), 128 actual worker requests, 1 MiB cumulative delivered tool-response bytes, 30 seconds per tool, 256 KiB native code, zero delivered images, zero transport retries. Startup/final snapshots and product collection also consume the same worker request budget. The root remains responsible for the complete-cell timer and actual worker-count verification. The inherited single-owner stdin broker lifetime is unchanged; send a newline and wait for actor exit to close the backend. The actor's `CLOSE.json` checks unchanged geometry/source, product exit and native exit.

## Consumer transport

`consume(slot, install, plan, prompt)` preserves the 005 function interface. `slot` must contain `cell` and `group`; `install['python']` is the same frozen dependency interpreter; `plan['max_session_seconds']` must be 450; `prompt` is the root's unchanged UTF-8 bytes. The root creates `cells/<cell>/cell.json` with `endpoint`, `audit_dir`, and preferably the matching `group`. No prompt, truth or fixture generator is loaded by the adapter.

The fresh consumer workspace is `.m1_task_entry_001_eval_runtime/work/<cell>`. Model argv/settings and the original 003 thin client are reused from 005, except the per-group tool approvals and workspace paths. Only the group's read tools are preapproved in the isolated CLI invocation. Native ability, requested model/effort, user-config exclusion, images/shell/web/plugins/hooks disablement, endpoint and original absolute deadline remain unchanged. `argv_for(python, cell, work, final, group=None)` is available for the root's command audit; omitting group reads it from cell JSON.

Provider request count, monetary fees and resolved effort remain unknown when not exposed. The transport adds no retries. All actual public messages, errors, usage, request/final timings and observed provider retry messages retain the 005 measurement scope.

The historical thin client can be terminated without publishing `EXIT.json`. New receipt inspection reports that as `bridge_cleanup.confirmed = null` / `receipt_status = unknown`, never as graceful closure. Invalid EXIT binding is false. Consumer `safe_to_continue` is explicitly limited to its own reaped CLI process/readers and absence of observed protocol or mutation uncertainty; missing thin EXIT remains separately unknown. It is not a backend closure claim. The root must independently finish the actor, check its backend receipts and verify owned processes before continuing.

## Explicit no-model stdio preflight

`preflight_client.probe(python, endpoint, output, messages)` starts only the original 003 `stdio_attach.py` against an already-owned actor. Output must be a fresh directory. Messages are explicit JSON-RPC objects, sent without argument rewriting; notifications retain the thin client's existing semantics. stdin EOF requests graceful thin-client completion. The helper records raw bytes, ordered reply IDs, actual client PID/exit, original endpoint deadline and bound STARTED/EXIT receipts. Product/tool errors remain visible replies for the root to assert; `confirmed` is a transport/lifecycle result, not a geometry score.

The command-line equivalent requires `--python`, `--endpoint`, `--output`, and `--requests` (a JSON array). It has no default launch action, model operation, actor ownership, backend close command or automatic retry. The root must run and review this preflight before any model GO. A normally closed explicit preflight does not erase historical missing EXIT records from other sessions.

## Reuse boundaries

`RUNNER_REUSE.json` pins original source hashes. Original 003/005 files, all product files and the sealed `verification/m1_task_entry_001` directory are unchanged by this implementation. The original native helper's terminal geometry/file checks plus script audit are retained; this does not claim a stronger Python filesystem sandbox or detection of reverted transient edits. The root's empty-workspace rule, neutral prompt and post-run script audit must keep truth, scoring, fixture sources and other cells out of consumer computations.

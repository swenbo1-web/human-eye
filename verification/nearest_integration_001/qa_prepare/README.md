# Three-state QA preparation

Prepared only. No Blender, NativeSession, RPC, product import/test, or candidate freeze was run by the preparation agent. The scripts were parsed with the standard-library AST parser. The preregistration compares the old asset recipe with the old full RAW world coordinates; it does not claim a new native observation.

Root must finish the offline gate and commit the unique candidate before these commands. The identity accepts either `source_sha256` + `files`, `candidate_source_sha256` + `source_files`, or a nested `identity` with `source_files`. Offline proof must have top-level `passed: true` or `successful: true` and matching `runtime_source_sha256` (or `candidate_source_sha256` / `source_sha256`).

```powershell
& 'verification/fixes/surface_facts_001/engineering_b/venv/Scripts/python.exe' -I -B 'verification/nearest_integration_001/qa_prepare/controller.py' prepare --identity 'verification/nearest_integration_001/CANDIDATE_IDENTITY.json' --offline-proof 'verification/nearest_integration_001/offline_01/RESULTS.json'
& 'verification/fixes/surface_facts_001/engineering_b/venv/Scripts/python.exe' -I -B 'verification/nearest_integration_001/qa_prepare/controller.py' run
```

Capture each command's actual stdout/stderr and process result externally. For outer entry byte evidence, root can read and SHA-check this controller's committed bytes, set `__file__`/`sys.argv`, then `exec(compile(the_same_bytes, path, 'exec', dont_inherit=True))`; do not substitute a cached module. Product execution independently uses the original `verified_source_loader`: prepare copies the committed 131-file snapshot into `run_01/sources`, and both client and remote host execute those exact manifest-bound bytes. The controller and worker files are hashed at prepare and rechecked at run; all three final RPC scripts and runtime original deadline are written and hashed before NativeSession starts.

`prepare` never starts a session. `run` refuses after 15:29Z to preserve the full 600-second original worker allowance and 60-second cleanup reserve before 15:40Z. `STARTED.json` makes a second run/session impossible. There is exactly one planned session, three state execute_code RPCs and one original-owner close RPC. The same original absolute deadline is passed to host capture and client summary checkpoints; it is never extended.

Each RPC mutates only the private in-memory Far coordinates, captures once, and restores coordinates in `finally`. Full native oracle reads and restoration checks are separate QA costs and never feed the product summary. Native owner fingerprints additionally enforce terminal state/protected-file preservation. Source, asset, binary and neutral NativeSession helper hashes are checked. Unknown/failed execution is not replayed; remaining states stay unrun, and close is still attempted by the owner.

Client summary calls `task_query.surface_nearest_result(packet, cache, checkpoint, diagnostics=...)`. The shared cache may legitimately miss after metadata changes; no assumed cross-state hits are asserted. Audited wrappers call the original functions unchanged and record each focal/target pair, kernel, `_nearest`, ranker, cache counters and diagnostics. Every retained nonfocal pair must occur once, kernel calls per pair at most once, and ranking once. Public output is checked against the three preregistered answers and must not contain `_exact_distance_sq`.

The initial scripts do not select/activate a public MCP mode, write scene history, install products, save a `.blend`, access a shared GUI/default port, or call a model/API. The remote worker entry is an isolated controlled QA entry, not desktop activation. `RESULTS.json` marks success only with all three restored replies, independent answer checks, source execution witnesses, no source/asset/helper drift, normal close and original-owner reap/exit0. All raw TX/RX, native worker scripts/events and state artifacts remain in `run_01`.

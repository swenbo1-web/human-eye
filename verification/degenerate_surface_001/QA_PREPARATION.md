# Fixed T04 QA preparation

The controller is prepared but has not been executed. The subagent performed only source reads and AST syntax parsing; no product import, Blender, stdio process, socket/RPC, model, external API, or asset copy was started.

The parent must finish all source/test changes, pass the bounded offline suite through the original verified loader, and commit the one candidate before preparation. Provide a candidate JSON with these fields:

```json
{
  "candidate_commit": "40 hex characters",
  "source_sha256": "131-source canonical SHA256",
  "source_root": "absolute new batch offline engine snapshot path",
  "product_manifest": [{"path": "relative product source path", "sha256": "SHA256"}],
  "offline_proof": {"path": "absolute RESULTS.json", "sha256": "SHA256"},
  "identity_proof": {"path": "absolute EXECUTION_IDENTITY.json", "sha256": "SHA256"},
  "expected_t04": {
    "distance_m": 0.0,
    "nearest_names": ["replace with independent oracle names"],
    "targets_excluding_focal": 4
  }
}
```

The expected values above are a schema example, not a T04 answer. Replace them with the independent offline oracle. The source root must be under this batch's directory. The identity proof may put its identity under `identity`, and may call its manifest `product_manifest`, `manifest`, `source_files`, or `files`. The source digest may be `candidate_source_sha256`, `runtime_source_sha256`, or `source_sha256`. The offline proof must have `passed=true` and the same source digest. The original loader proof must expose `identity.guard_verify_loaded=true` or `offline.loader_guard.verify_loaded=true`; if the latter additionally exposes `every_loaded_module_has_execution_or_namespace_witness`, it must be true.

Use the existing engineering interpreter, with an absolute freeze path:

```powershell
& 'verification/fixes/surface_facts_001/engineering_b/venv/Scripts/python.exe' -I 'verification/degenerate_surface_001/qa_control.py' prepare --candidate-freeze '<absolute candidate JSON path>'
& 'verification/fixes/surface_facts_001/engineering_b/venv/Scripts/python.exe' -I 'verification/degenerate_surface_001/qa_control.py' run
```

Preparation checks Git source blobs, both source copies, canonical identity, exact material/helper/Blender/assignment bytes, original T04 prompt/asset binding, offline proof hashes, and the matching root window. It copies only the already accepted production stdio bootstrap and freezes all controller/proof inputs. It performs no product import or actual session. Its output is `qa_01/PLAN.json` and `FREEZE.json`.

Only the parent runs the second command once, preferably inside its own outer Popen/wait/reap logger. `STARTED.json` is opened exclusively and prevents another session. The run uses the original NativeSession with its original 600-second worker deadline, 20-second product request budget and 10-second host/native timeout. Two execute calls are allowed, then one owner close: name `surface_nearest`, the first returned `focal.id` through the legacy route, close. No setup/profile fixture, scene modification, save, extra observation or retry is included. Initialization and tools/list are MCP frames but may not open a product socket.

Raw MCP/socket frames, both public results, executed worker scripts/events, source guard witness, exact argv/PIDs, owner close/reap, original/final geometry fingerprints, immutable asset/helper hashes, and timing/byte boundaries remain in `qa_01`. Unknown/incomplete evidence remains original. The close guard does not invent missing graceful events. Any actual failure ends the unique batch without a replacement session. Cache behavior is assessed mainly by offline kernel counts; QA cold/warm timings cannot establish model or task benefit.

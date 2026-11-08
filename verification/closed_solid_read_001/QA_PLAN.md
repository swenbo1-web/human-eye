# One fixed closed-solid read-only QA

Prepared from the accepted complex-entry controller. No prepare/run, product
import, model consumer, Blender session, RPC or process query was executed while
authoring these files. Syntax was checked with AST only.

The parent first finishes the bounded verified-loader offline checks, commits
the single candidate and supplies `SOURCE_FREEZE.json`:

```json
{
  "baseline_HEAD": "4ca1fdb2882ae31da2fd3ec49ac77e1710c69a3e",
  "candidate_commit": "new fixed candidate commit",
  "source_sha256": "new complete canonical source digest",
  "source_root": "absolute current batch source snapshot",
  "product_manifest": [{"path": "relative product source", "sha256": "sha256"}],
  "offline_proof": {"path": "absolute RESULTS.json", "sha256": "sha256"},
  "implementation_deadline_epoch_seconds": 1794152875
}
```

The offline proof must have `passed=true` and `runtime_source_sha256` or
`source_sha256` equal to the new digest. The controller rejects baseline82db as
the identity of changed source. Current HEAD must equal the new candidate;
manifest, frozen source, current bytes and that Git commit all match before
run. The fixed old patch-capable helper is checked against baseline Git.

Existing parent `inputs` are reused without overwrite: scene.blend, qa_patch,
author snapshots, tasks and TRUTH.json. Independent accepted truth is fixed to
run_02/author/assembly/TRUTH.json SHA
`d01b0006ef1d4416c8b40663e8aabb7ba64730c7c833b516c3ee1631651a38ff`.
Separation distances are compared to its nonzero certified intervals; rounded
example distances do not become exact truth. This is operator QA, with no
consumer and no prefilled model answer.

Parent commands, using the existing engineering Python:

```powershell
python.exe -I verification/closed_solid_read_001/qa_control.py prepare --source-freeze <absolute SOURCE_FREEZE.json>
# Run this only if prepare returned success, once through the existing outer logger.
python.exe -I verification/closed_solid_read_001/qa_control.py run
```

Preparation validates the fixed CLOSED_SOLID_WINDOW/assignment, current matching
STATE token/owner/caps/status/expiry, original inputs, full new source identity,
offline proof, helper and old bootstrap. It does not start a process or product.
The only bootstrap changes add two profile targets and retain their returned
work/diagnostics: `classify_closed_solids` and `_closed_solid_pair_measurement`.
These are real measured overhead, not free work. The original loader, service,
socket requests and outputs remain the execution path.

Every public pair requests exactly `closed_solid_relation` and
`surface_proximity`, include_image=false, via current task name selectors.
Initial order is Object_03 first, then Object_02/Object_04; unchanged and changed
each query 02/03/04. All nine use one current candidate and persistent service.
Raw selected captures bind IDs, revision, runtime identity and original exact
geometry. Independent native readback once per state checks all four objects.
The only mutation is the original accepted `qa_advance` four-point patch.

Full supported path is 14 physical RPC: 9 observations + 3 readbacks + 1 patch +
1 close, within16. At most one NativeSession, its original600-second deadline
cannot reset; request20/host10-second budgets and max9 observations remain.
Initialization/listing must not capture. The implementation deadline15:47:55Z
does not grow to the later resource-window expiry.

Any bound necessary relation unknown ends further qualification immediately.
For separated pairs, unavailable distance also ends further qualification;
known distance is retained even if only its witness is unknown. Other planned
observations stay not_run; no new session, retry or second candidate follows.
Known but wrong facts remain accuracy mismatches rather than unsupported.

`entry_and_cleanup_verified` records structural/source/owner validity.
`original_contract_complete` and `original_contract_checks_passed` separately
record all nine facts, all penetrating pieces and nearest separated object.
`passed` is true only for complete accurate three-state contract and cleanup.
A required unknown therefore exits1 as a concrete incomplete candidate. It is
not permission to retry the QA.

`audit_entry.py` runs only after the parent reports terminal actual execution.
It reads the original frames, socket code/event/stdout bindings, source guard,
geometric snapshots, independent truth and owner receipts. It adds no product,
test, RPC or PID query. Structural audit validity is separate from original
contract completion. Native initial/accepted/final fingerprints stay distinct
when the authorized patch applies. LF logical text and CRLF disk artifacts,
worker close unknown and self-PID/direct-owner-wait gaps are preserved.

Cold/unchanged/changed acquisition socket time, public wrapper time, closed-pair
profile/counter work and core invocation counts are recorded separately.
Intervals overlap and must not be summed. Cache reuse and engineering QA do not
establish model-level benefit, complete provider usage or fees.

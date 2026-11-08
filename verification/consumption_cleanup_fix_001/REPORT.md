# CLEANUP-RECEIPT-FIX-001

The offline repair preserves an OS observation that a registered process has stopped even when its optional EXIT file is absent. The candidate is copied from RUN-002 into this new directory; only `process_exited` and `registered_tree_cleanup` changed. No old runner, result, source product, approval setting or tool annotation changed.

`process_exited` now returns stopped/live/unknown as True/False/None. Access denial and unsupported wait results remain unknown. Only a valid positive DWORD PID reaches the Windows API facade. No process is signalled.

Cleanup first binds STARTED kind, integer PID and ledger to the current slot. Each bridge records `process_stopped` separately from `graceful_exit_receipt`. The latter holds the original EXIT content or None when absent; a present receipt can explicitly say `normal_exit=false`, so presence does not assert graceful success. No exit code or owner reap is inferred from OS stop evidence. Unreadable, malformed or contradictory existing receipts remain unconfirmed.

Native bridge stop can be confirmed without EXIT. HE also requires its existing HE_CHILD_STARTED identity in the bound bridge directory and a separate OS check of that child. HE_CHILD_EXIT and bridge EXIT child identities are cross-checked when present. Missing child identity, live/unknown child, invalid binding or conflicting PID still prevents continuation. A stopped HE child can be confirmed without its optional normal exit receipt. The existing consume/slot stopping logic, original deadlines and budgets are byte-identical.

One independent reviewer inspected the source without execution; a separate agent authored the bounded fixtures without running them. The main agent executed the six groups once against pinned source and test hashes, with subprocess, signal, real Windows process inspection and network operations blocked or mocked.

| Offline group | Scenarios | Outcome |
|---|---:|---|
| Native stopped, EXIT missing; retain STARTED and OS observation | 1 | passed |
| Existing EXIT control, nonzero code retained, conflicts/null/malformed | 6 | passed |
| Native live/unknown/denied/unbound; invalid PIDs; mocked Windows waits | 24 | passed |
| HE bridge stopped, child live/unknown/unidentified | 3 | passed |
| HE child stopped without receipts; existing identity conflicts | 7 | passed |
| Real cleanup unknown result drives unchanged slot loop: first only, 7 not_run | 1 | passed |

**6/6 methods and 42/42 scenarios passed; failures 0, errors 0, skips 0.** Test execution was 0.1586654 seconds. The eighth-slot denominator, original window argument, answer deadline and ledger bytes remained unchanged in the stop-path fixture. These are mock results, not real process or consumer certification.

Actual Codex CLI/model consumers/MCP services/Blender/RPC/paid API calls: **0**. Real target process starts or signals: **0**. The only executed test command was the existing Python interpreter running `-I verification/consumption_cleanup_fix_001/run_offline_checks.py`; it did not invoke the candidate runner entry point. No PLAN or approval is activated by this package. Tool trust remains under the root task's separate work.

Baseline HEAD: `63dd07f762c1e144a3bedfd5ca5d81d6461748fb`.

- Candidate runner SHA256: `1e87f432ea648613c30666dd06d5dde6cfd16697d7fbd5de10e36f25c997aaf9`.
- Tests SHA256: `412a6adbf4ecf83190e76f82b3adfb0ff3b36cfb73fa90e426893e3f7bc85794`.
- `SOURCE.diff` shows the two-function change; AST and exact prefix/suffix byte comparisons confirm all other code is unchanged.
- `OFFLINE_RESULTS.json` and raw stdout/stderr retain the actual denominator, outcomes, timing and protected-file hashes.
- `PROVENANCE.json` and `EVIDENCE_INDEX.json` record baseline/source/assignment identities and package bytes.

RUN-002 remains 1 error + 7 not_run, 1 returned final, 0 valid completions. RUN-001 remains 1 error + 7 not_run, 0 returned finals. Their tracked originals and RUN-002 evidence index are unchanged. No truth or answer body was interpreted. Product commit `17db41c481397965a9bae3f4571c59a5a80939c9` / 131 source entries / canonical `01c296b5dac9c8733670b7b82886fe774fb6e50222d1b935d6ac27efa04760de` is preserved by keeping all tracked changes inside this new directory.

Known limits remain: registered PID checks cannot establish arbitrary descendant cleanup or exclude PID reuse; no global scan or new guardian was added. Cleanup confirmation establishes registered process stop, not answer correctness, approved tool use, normal exit, owner reap or successful engine execution. The old false cleanup flags are not rewritten by this repair.

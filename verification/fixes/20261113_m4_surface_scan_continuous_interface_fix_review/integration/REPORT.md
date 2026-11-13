# Independent integration review — continuous interface fix 001

Delivery reviewed: `b51dc02eb4f25966f983033b42dad3c9cfec9393`. Author tree is `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe`. Result: **the narrow transport fix and its actual inner coordinator integration pass the examined scope**. Proceed to the six new formal episodes after the already necessary 002 driver adaptation below; no additional engineering batch is warranted.

## Independent work and denominator

`replay.py` imports the existing wrapper/pure comparison without invoking a consumer loop, reads the original a04 records, and independently asserts their linkage. **265/265 assertions pass**. No new fixture processes, model calls, Blender runs, product runs, paid API calls, author-file changes, or Git changes occurred. This is an independent audit of historical fixture execution, not an independent live integration run or evidence of a real model retaining context.

| a04 case | Scenario | Completed | Failed | Not run |
|---|---|---:|---:|---:|
| 8a16aa | Native, successful recorded CLI representation | 3 | 0 | 0 |
| 977485 | Compact/plugin, successful recorded CLI representation | 3 | 0 | 0 |
| ea8590 | Same-representation tool error in REPEAT | 3 | 0 | 0 |
| 993efc | Real error payload, cross-representation CLI error in REPEAT | 1 | 1 | 1 |
| Total | Four cases / twelve fixed slots | 10 | 1 | 1 |

Each of a01–a04 contains eleven `FAKE_TURN_*` receipts, eleven consumer launch/completion records, and eleven matching thin STARTED/EXIT identities. Total: **44 fake CLI invocation instances and 44 thin invocation instances** across sixteen historical test cases. These are invocation denominators, not a census of every OS process created by the Python environment. All 44 thin identities bind PID plus nonce and record normal exit. a03 has four passing fixture cases but retained publication failure (`FileNotFoundError`, main exit 1); subsequent archival of its existing records does not turn that original publication into a success.

The author describes a01 as tests plus end hashes, a02 as before/after source binding, a03 as source/archive publication addition, and a04 as the idempotent extended-path/numeric-directory correction. This review independently checks all four attempts' process/turn originals and the retained a03 failure receipt, but does not recreate a01/a02 source bytes absent from a pre-run source snapshot. The a04 result is the current acceptance instance; prior attempts are not additional formal samples.

## Mechanism confirmed from source and actual records

The new `runtime/episode.py` injects its new transport into the old coordinator. Import inspection confirms that the reused `run_episode.__globals__['transport']` is that exact new module, and the reused old `consume_turn.__globals__['archive_turn']` is the new archive function. Thus the tested process loop really reaches the changed result-binding check; this is not an unused helper test.

The new predicate is reached only after the old exact result comparison differs. All a04 ordinary successful records have owner `{content,isError:false}` and CLI `{content,structured_content:null}`, equal content and matching original request arguments. The new predicate accepts them. Original owner response copies remain byte-identical and tool events equal the recorded consumer items.

For ea8590/REPEAT, owner `isError=true`, owner ATTEMPT `is_error=true`, and CLI tool `status=failed` are all retained. The new success predicate returns false. The old exact result comparison is true, so its faithful receipt binds without introducing an error policy change. The coordinator records that turn completed because its existing lifecycle/final policy accepts it. **This is not tool success, task quality, or successful geometry evidence.**

For 993efc/REPEAT, the same real error payload has cross-representation results; old exact and new successful-result compatibility both return false. The recorded binding error is `CLI_result_differs_from_owner`; the turn retains its final text but is failed. EDIT has neither a consumer directory nor `FAKE_TURN_3.json`, and the owner records zero registered edits. Its third fixed slot remains not run. The proposed success-only shared-fault stop predicate is false for both actual tool-error forms.

Both normal N/C cases show one UUID across all three CLI receipts, explicit resume UUID on REPEAT/EDIT, the same work directory and retained marker, unchanged endpoint hash, exactly one owner finish, and normal thin exits with `backend_close_requested=false`. Controls occur before finish, and only the registered EDIT transition changes pose. These are real fixture transport/coordinator continuity facts; `model_continuity_attestation` remains `pending_actual_consumer`.

## Required 002 adaptation, not a new repair cycle

The existing formal 001 driver intentionally remains unchanged and still points its `COORDINATOR` and `TRANSPORT` to FIX1. `review/stop_recommendation.py` is explicitly a proposal, not hooked into a formal driver. Therefore 002 must freeze and load the new wrapper paths in its own driver and bind their hashes. Merely describing the fix in a plan will not apply it.

One concrete additional interface dependency is confirmed: old `driver.run_one` closes and reads back the owner, then calls `coordinator.pack.capture_cell(runtime, archive)`. The new wrapper exports `run_episode`, `transport`, and `legacy`, but no `pack`. Directly replacing only its path would raise `AttributeError` at outer archival after otherwise successful inner execution. The minimal 002 adaptation is to explicitly use **the same existing `coordinator.legacy.pack`** for this outer archive (or explicitly bind that exact existing pack module). Do not alter the frozen fix delivery to hide this integration requirement.

In 002, attach the success-only shared-binding-fault rule to its existing `stop_reasons` after sole cleanup. Bind the actual per-turn owner response and matching CLI event; preserve ordinary tool errors and quality failures under their current policy. If a new successful-response representation mismatches the fixed contract, retain that episode failure, stop remaining formal episodes, and do not silently requeue them.

The planned offline qualification should traverse the **actual new outer `run_one` through finish, postclose, outer originals archive, and publish** with fixtures. Testing only inner `run_episode`, a `run_batch` stub, or an argv helper would miss the proven `pack` integration dependency. This is a bounded preflight within the six-episode 002 batch, not a reason for another preparation-only cycle.

## Reviewer correction and limits

The first independent script incorrectly required the fixture's `os.getpid()` to equal the consumer launcher PID and required unique thin PIDs across sequential cases. Those assumptions are not part of the contract: the receipts distinguish actual script PID from reaped launcher PID, and one thin PID is reused with a distinct nonce. The initial 249/265 output is preserved in `REVIEWER_INITIAL_ASSERTIONS.json` and `REVIEWER_INITIAL_CHECKS.json`. The corrected checks bind each launch to its own cleanup receipt, require the actual fixture receipt, and bind thin close by PID **and nonce**. No author artifact was changed. Original records do not independently attest process ancestry, so no such claim is made.

No new live model context, task quality, cost, or 002 outer-driver success has been tested here. Existing six failed formal episodes and twelve not-run slots remain historical outcomes. Parent AL: a22c631e revision 1/write 628, not borrowed; child's historical assignment `83190789b8504a49bb04b5450cedf946` is not current and was not updated.

Artifacts: `RESULTS.json`, `CHECKS.json`, `INPUT_SHA256.json`, and `replay.py` in this directory. Re-run with the fixed local Python using `-I -B -X utf8`.

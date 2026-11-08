# CONSUMPTION-RUN-002 actual delivery

One authorized invocation finished. It received **1 public final**, but the frozen first-slot status is **error** with **0 valid completions**; the other **7 slots are not_run**. No retry, replacement answer, inline repair, resumed 001 run, or quality scoring occurred. A returned final does not establish task correctness or engine benefit.

| Slot | Task | Arm | Frozen status |
|---|---|---|---|
| 1 | T01 | N | error |
| 2 | T01 | P | not_run |
| 3 | T02 | P | not_run |
| 4 | T02 | N | not_run |
| 5 | T03 | N | not_run |
| 6 | T03 | P | not_run |
| 7 | T04 | P | not_run |
| 8 | T04 | N | not_run |

Every unstarted slot retains reason `previous_slot_cleanup_not_confirmed_no_further_start` and null dispatch. The first slot's original reason remains null. `actual_01/RESULTS.json`, per-slot `RESULT.json`, `CONSUMER.json`, and public final are unchanged originals.

## Observable failure and stopping boundary

The sole public `native.execute_blender_code` attempt failed with the captured message **`MCP tool call requires approval, but approval policy is never`**. It was not forwarded as MCP `tools/call` or native `execute_code`. This public approval error is distinct from the frozen slot invalidity: native bridge PID 14744 has STARTED but no EXIT receipt. The runner therefore kept `registered_tree_cleanup.confirmed=false`, `tree_reaped=false`, and `safe_to_continue=false`, and stopped before slot 2. No claim is made about why EXIT was absent.

The CLI terminal turn completed and its process exited 0. `complete=true` does not override `valid_completion=false`. The original 180-second answer timer did not fire. Three discarded ordinary stderr lines (554 bytes) and one discarded public error event remain unavailable under the frozen filter; no private log or replay was used to recover them.

## Calls, bytes, images and usage

- Actual CLI contexts: 1; returned finals: 1; original native Blender sessions: 1; P/HE slots started: 0.
- Public tool attempts: 1; admitted server tool actions: 0; native execute RPCs: 0; product capture RPCs: 0. The one physical native RPC was administrative close, outside the execute ledger.
- MCP frames: initialize, notifications/initialized, tools/list; TX 409 bytes / published RX 787 bytes. No tools/call frame. Native close TX 17 bytes / RX 62 bytes.
- Complete tools array: 563 UTF-8 bytes, one descriptor: 561 bytes. Actual model-delivered schema bytes are unexposed (`null`).
- Public text ledger: 2,093 bytes = prompt 911 + tools array 563 + final 619. The final artifact is 632 bytes because of 13 CRLF expansions. These are separate measurements.
- Render events, PNG files, generated image blocks: 0.
- Terminal usage counted once: input 48,129 tokens, cached input 35,456 (subset of input), output 1,328. Provider request count, fees, and actual backend are unexposed/null; no monetary estimate is substituted.

## Time and ownership

The full recorded argv is in `actual_invocation_001/STARTED.json` and `OWNED_PROCESS.json`. The exact root-provided runner ran once with the existing isolated Python interpreter and approval file. Controller start 2026-11-08T04:02:34.897320Z; end 04:03:34.254347Z.

| Observed interval | Seconds | Scope |
|---|---:|---|
| Outer Popen/wait/reap | 59.3571895 | Complete controller invocation |
| Runner wall | 59.2669521 | Through result construction |
| First whole cell | 58.9164216 | Dispatch through cleanup |
| Answer receive latency | 49.6407478 | Dispatch to received final; not certified completion |
| Consumer wall | 57.4009768 | Entry through consumer cleanup |
| Native close owner receipt | 0.1227544 | Administrative close and owner reap |
| Native close wire meter | 0.1352274 | Separate wrapper observation |

These intervals are nested and must not be summed. They do not measure engine speed or successful task completion. `MANAGEMENT_CLOCK.json` separately records this management turn's start, preparation interval, and elapsed lower bound through sealing; final commit/callback tail and prior preparation turns are outside that cutoff.

Controller 15456, CLI 20884, and Blender 18996 were owner-reaped with exit 0. Native close returned closed, poison=false, unchanged geometry fingerprint, unchanged original session deadline, and protected/source files unchanged. Bridge 14744 lacks EXIT. A later targeted scan found none of the four known PIDs alive; that observation does not repair the missing receipt or prove arbitrary descendant cleanup. All frozen false flags remain false.

## Identity and delivery evidence

Baseline HEAD: `34496064288ee8789da6e51a17a0dd894eeba11b`. Product remains commit `17db41c481397965a9bae3f4571c59a5a80939c9`, 131 source entries, canonical SHA256 `01c296b5dac9c8733670b7b82886fe774fb6e50222d1b935d6ac27efa04760de`. All 17 PLAN components and original assets were independently rechecked. The five activation files are byte-identical to the root package; PLAN SHA256 `11cbfa7445c5d4075ca291321bebcc48d116ad9a4928807d087cb54c52cb7980`.

`APPROVAL.snapshot.json`, `ASSIGNMENT.snapshot.md` and `AUTHORIZATION_SNAPSHOT.json` preserve authorization metadata. The root owns STATE/window release; no STATE write occurred. `NEUTRAL_RAW.zip` preserves all 10 raw files of this run's private neutral root; `NEUTRAL_RAW_INDEX.json` gives member hashes. It excludes shared/global logs. Original neutral files were neither deleted nor moved.

`COUNTS_AUDIT.json/.md` and `CLEANUP_AUDIT.json/.md` are independent read-only audits. `PRESERVATION.json` anchors frozen outputs and prior tracked actual results without interpreting answer bodies. Only new RUN-002 materials are submitted. Old RUN-001 stays 1 error + 7 not_run, 0 returned finals. No truth was read; root may score separately.

`EVIDENCE_INDEX.json` hashes every new RUN-002 evidence file except itself and Python bytecode/cache. All raw run frames and received answer artifacts are included. The delivery callback supplies the final commit and index SHA256 after the Git blob comparison.

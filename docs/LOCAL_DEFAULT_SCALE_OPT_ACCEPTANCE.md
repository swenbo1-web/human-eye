# Local default SCALE-OPT-001 upgrade

2026-11-10. User authorized upgrading the latest optimized local plugin and trying the same tasks. Fixed product commit: `df016079b0265ee327f884c90dd4815c392016b6`, from our `codex/architecture-arm-correction` worktree. This document is the root review and deployment record; producer evidence remains in `verification/scale_opt_001` at that commit.

**Installed and configured:** `9.7.2+20261110.scale.opt.r1`, 137 runtime sources, canonical `3fc2651e108ad7ac252394871d78e1abaee1200c92a018125984b2fc240193bd`. New-process checks and owned Blender task trials passed. **Current desktop process reload, live Blender connection and real host Hook activation remain pending.** They are not counted as passed.

## Independent review of the optimization

The product change is four lines in `_bounded`, removing redundant checks for exact builtin integers under the existing fixed 4096-bit budget. Fractions, bool and subclasses retain the original path. No geometry precision, eligibility, traversal, cache or deadline changed.

The root's independent raw-results audit reproduced all 78 logical outcomes across 18 chains, 60 initial/continuing states and receipts, and 192 worker events. It checked the 1203 sealed members, fixed Git bytes, both 137-source installations and candidate wheel/source equality. Thirty successful pairs and six unknown pairs retained identical facts, witnesses/reasons and complete kernel records.

| Fixed old/new engine comparison | Old | Candidate | Result |
| --- | ---: | ---: | --- |
| D48 cold request | 18.8255 s | 7.9272 s | 57.89% less time |
| T seven-state whole-chain median, three repeats | 121.1938 s | 49.6750 s | 59.01% less time |
| Correctly completed logical cases | 30/39 | 32/39 | No completed-case regression |

These are geometry-engine tasks, without an LLM consumer. They do not establish general complex-scene or model-task speedups. G508/G4092 retain six unknown results. D192 cold still expires; the first later successful response already cost 42.3877 seconds of cumulative request time, plus setup.

Independent code execution added 107 arithmetic equivalence checks, 24 resident/hull tests, three write-boundary tests and a prepared-action/read/colliding-action sequence. All passed. Source guards passed with product and test roots separated, including the actual installed launcher. The colliding action used two fresh captures and made zero host mutations.

The author's 191/193 regression result remains recorded. Its two old assertions conflict with previously accepted action-ledger preservation and degenerate segment-hull contracts; they were not edited to manufacture a green run. The author's 24-method run also retains its failed post-test source guard. The independent separated-root run resolves that deployment concern without rewriting the earlier failure. Extreme-input bbox overflow warnings remain recorded.

## Same-task trial through the installed ordinary MCP entry

The actual new controlled entry ran ordinary `serve`, without `--spatial-task-only`, using two owned copies of the same frozen scale-diagnostic assets. Each selected task had one cold and two warm requests. Full world-mesh readbacks matched before/after; MCP and Blender processes exited and were reaped.

| Query through ordinary MCP | Cold RTT | Warm RTTs | Whole owned test lifecycle |
| --- | ---: | ---: | ---: |
| G60 closed-solid relation and surface distance | 175.86 ms | 14.40 / 15.89 ms | 2.095 s |
| D48 complete nearest surface | 7742.81 ms | 45.64 / 54.30 ms | 9.853 s |

Selected acceptance: **6/6 correct**. One additional first G60 request is separately retained: its answer was correct, but the test adapter initially expected the dedicated tool's `candidates/context` fields instead of ordinary observation's `pairs/binding`. Only the test adapter changed. Total actual requests were seven; no product failure or slower sample was replaced. These external MCP timings are not directly substituted into the earlier in-process speedup calculation.

## Installation and activation evidence

The fixed source snapshot was built into a version-labelled wheel; all 137 runtime source bytes remain identical to the reviewed candidate. Wheel SHA256: `79f15db029de6404af30e6ba319c94e4e0d8f739eb8be3f1745dae7d2f834990`. Dependency Python remains the existing isolated dependency environment, with NumPy 2.3.5 and Pillow 12.3.0, matching the comparison.

New launcher SHA256: `e8f710dd283be03acf01a29f3b811a41ef767fd12b2fb6372fa8b628269617d2`. The existing migration helper is unchanged except for its launcher pin. Reviewed and applied plan SHA256: `7f594fda3e1f97578c4f00898716cb43a35d9c2d16b67166633a10ea092d7d14`.

The locked migration changed exactly four files: default MCP configuration, five existing Hook commands, connector root/identity, and the state configuration fingerprint. Independent comparison confirmed all other servers/settings and Hook structure unchanged. All runtime/journal bytes were preserved, including six sessions and two goal-segment records. No pending operation or quarantine was present. The old controlled release remains available; a reverse migration plan was generated. Any actual rollback must regenerate against the then-current state, not restore historical ledger bytes.

Fresh-process initialize, ping, tool listing and current-state health passed. Task and surface-nearest modes are present, together with the regular tools. Current live observation did not execute because BlenderMCP was unavailable; port 9876 had no listener. The original formal-check harness additionally asserted an identity field on that error envelope, so its first run failed. The raw error is retained, the harness was corrected, and a protocol-only recheck passed without retrying the unavailable scene read.

The current desktop tool returned `state_configuration_binding_mismatch` / `stale_configuration_snapshot`, confirming it still holds the previous process configuration. No MCP reload tool is exposed in this session. The host must reconnect/reload the MCP connection, then the reviewer will verify the actual desktop identity and state health. Real Hook activation must be checked after host reload/trust handling; it has not been replaced by a simulated pass.

The initial packaging attempt omitted README.md from the frozen copy, so portable-bundle creation failed. README was fetched from the same fixed commit; the partial bundle and error were retained, and the complete build used a new directory. Product bytes were unaffected.

## Evidence and next step

Local evidence lives in `D:/hefe/verification/fixes/20261110_local_upgrade/`, including `ROOT_QUALITY_REVIEW.json`, `ROOT_CODE_REVIEW.md`, `ENTRY_ACCEPTANCE_REVIEW.json`, `INSTALL/ISOLATED_INSTALL.json`, `APPLY_DIFF_REVIEW.json`, migration receipts and raw entry responses. Private configuration backups remain local and are not published with this review.

Next: reconnect Codex MCP, start/connect the Blender MCP service at the configured address, then verify the desktop runtime and a real read-only Hook observation. No repeated upgrade approval is needed. No further optimization batch is dispatched while this local-entry acceptance remains open. Google API/key/paid trials remain paused; no original assets, competitor branch, dedicated owned/reference services or host trust records were modified.

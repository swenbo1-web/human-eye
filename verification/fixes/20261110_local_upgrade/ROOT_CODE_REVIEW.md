# Independent code and contract review — SCALE-OPT-001

Reviewer: `/root/scale_opt_design_review`. Fixed commit: `df016079b0265ee327f884c90dd4815c392016b6`. Reviewed on 2026-11-10. This is independent review evidence; author records and historical failures were not changed.

**Verdict: no deployment blocker found in the four-line integer fastpath or the two reported legacy failures.** The author's post-test source-guard error was reproduced in its documented layout by code inspection, then closed by an independent successful run with product and test roots separated. Installed product code was also checked through the new controlled launcher, using fake hosts only. Desktop MCP/Hook reload and real Blender acceptance remain the parent review's separate work.

## Fixed identity and scope

- Product source: 137 files, canonical `3fc2651e108ad7ac252394871d78e1abaee1200c92a018125984b2fc240193bd`.
- Source under review: `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe`, HEAD verified as the fixed commit before execution.
- Frozen product root used for 24 current-contract tests: `D:/hefe/verification/fixes/20261110_local_upgrade/source_df016079`.
- Installed product root used for three write-boundary tests and one additional read/write sequence: `D:/hefe/.human-eye/releases/9.7.2+20261110.scale.opt.r1/site-packages`.
- Installed entry SHA256: `e8f710dd283be03acf01a29f3b811a41ef767fd12b2fb6372fa8b628269617d2`.
- No source, author evidence, default configuration, Blender state, asset or performance matrix was changed. No Blender session, network request, paid API or model consumer was used. Tests used temporary local fake-host ledgers; temporary directories were cleaned.

## Four-line arithmetic change

The only product change is the `type(value) is int` branch in `human_eye_plugin/surface_proximity.py::_bounded`. For an exact builtin integer, `value.bit_length()` equals `abs(value).bit_length()`, including negative values and zero. Both branches return the identical input object when accepted and raise the same `_DomainError('surface_exact_bit_budget')` when rejected. The removed denominator check is always `1.bit_length() > 4096`, hence false.

`type(...) is int` deliberately leaves bool, integer subclasses, Fraction and Fraction subclasses on the original branch, retaining their prior property/override/exception behavior. No bit width, face count, pair budget, exact predicate, rank key or result certificate changes.

Independent execution compared the fixed pre-change `_bounded` AST from commit `d01d49bc0ec82583b24a8faf22e622e6f6ea8c5d` with the guarded candidate across all 107 recorded input cases, checking return identity/type and exception type/message/args: **107 passed, 0 differences**. This reuses the disclosed case vectors; the equivalence argument above is the independent reasoning.

MAX_BITS=0 is not an equivalent arbitrary monkeypatch: old `_bounded(0)` rejects because denominator 1 exceeds zero bits; the candidate accepts zero. Product source fixes `MAX_BITS = 4096`, no production setter/configuration was found, and the relevant tests assert 4096. Other modules' MAX_BITS values are separate arithmetic implementations. This unsupported constant mutation does not block this release and does not justify an extra branch in this hot path.

## Two red historical assertions

The author's legacy run remains **191/193** on both baseline-restored and candidate arithmetic. This review did not rerun that 193-test suite or turn its red results green by omitting/editing tests.

1. `test_does_not_reuse_prior_write_prepare_context` expects every task read to clear persisted action sessions. The accepted resident read path now uses a separate ReadContext and performs no action-ledger I/O. Clearing persisted action bytes would violate the current contract, including preservation of pending/committed/quarantined and even opaque corrupt ledger contents during a read.

   Retaining those bytes is not permission to reuse an old observation. `live_service._transform_locked` prepares again before execution, and `host_runtime.execute_action` captures again inside the transaction before its geometric gate, then submits the current revision/fingerprint. Existing write-boundary regressions cover fresh checks and uncertain outcomes. This review independently reran three of them through the installed guarded runtime; all passed.

   An additional independent installed-runtime sequence prepared an allowed action, ran a task surface read, checked that the ledger remained byte-identical, then requested a colliding action. It returned `blocked`, made **two fresh captures** and **zero host mutations**. Thus persistence after a read is not a stale-action bypass in this sequence.

2. `test_g06_unknown_candidate_and_original_reason_remain` assumes a collinear three-point face is always `surface_degenerate_triangle`. Fixed d01 already contained hulls_v3, which represents that face by its closed segment, or a point if all vertices coincide. This is an earlier, separate surface-distance capability, not an effect of the integer fastpath. The specific old fixture has distance exactly 2: target x<=0, segment x>=2, attained at (0,0,0) and (2,0,0).

   The 12 current hull tests use an independent exact convex-QP/Gaussian-elimination oracle rather than the product predicates and passed here. Segment/point surface distance does **not** confer closed-solid qualification: `_closed_topology` separately rejects a degenerate face. The resident suite also passed its measured-surface/unknown-solid case, preserving partial status and incomplete penetration/nearest claims.

Recommended maintenance after this release: update the two live expectations to the accepted contracts while retaining the original failing evidence. Do not keep interpreting an expected 191/193 aggregate as a generic all-green regression gate.

## Source-guard failure attribution and independent closure

Author CURRENT_CONTRACT_REGRESSIONS recorded 24/24 test methods passing followed by `verified_source_preloaded_module:verification.test_blender_host_contracts`. SourceGuard treats unverified modules physically below its product root as internal. In that runner, verification fixtures shared the product workspace root. Its recorded post-test audit really failed; that failure must remain visible.

Independent run 1 installed the unchanged verified_source_loader over the 137 frozen product sources and compiled the four main test files from the fixed Git object with SHA-tagged filenames. Test fixtures and third-party dependencies were outside that product root. Results:

| Check | This review's actual result |
| --- | --- |
| Fixed old/new `_bounded` input cases | 107/107 equal |
| Resident task contract | 12/12 passed, 0 failures/errors/skips |
| Degenerate hull contract | 12/12 passed, 0 failures/errors/skips |
| Post-test `guard.verify_loaded()` | Passed |
| Post-test `check_source_drift()` | compatible=true |
| Post-test `check_task_source()` | compatible=true |
| Process completion | Exit 0 |

The extreme-input test still emitted `RuntimeWarning: overflow encountered in add` at `human_eye_foveated_renderer.py:151` while forming a bbox center. It was not hidden or converted into a new performance/correctness claim.

Independent run 2 used the actual installed entry bytes, the bound dependency Python with `-I -B`, `validate_binding(expected_python=sys.executable)` and `verify_imported_runtime` before and after tests. The product root contains the wheel; dependencies remain in the separate historical dependency venv. All three selected tests passed:

- `test_preview_does_not_eliminate_fresh_execution_check`.
- `test_failed_or_partial_mutation_persists_connector_wide_quarantine`.
- `test_final_state_write_failure_leaves_original_uncertainty_journal`.

The additional prepared-action/read/colliding-action sequence passed as described above. The final controlled entry verification passed with installed distribution `9.7.2+20261110.scale.opt.r1` and the expected canonical source identity. No network/subprocess operation was attempted after installing the test guards. This is direct evidence that the author's fixture-origin audit failure does not carry over to this installed product/dependency layout; it is not a claim that the existing desktop connection has reloaded.

## Test-byte identities and retained limits

Main test bytes in run 1 were checked against the fixed Git commit before compiling:

- `bounded_equivalence.py`: `bf5f11305a7415a3e81f529808306947bb04099a289993f738ae3a0b9523d7e2`.
- `test_surface_nearest_entry.py` (fixture dependency, its suite not run): `739fa86d14b6199b0ba9d438a944b4d26ed9c4b4e5947babdf5f42fcb4c4b46a`.
- `test_resident_task.py`: `25c4d6141e9f1d2536e82c7ff2bc9b4fc9aba07a1e931b0dd725bf887473305c`.
- `test_degenerate_surface.py`: `642399238ec5365bfbe212416fba8e4748ed1c936f69eb042d42c8f928af3bb7`.

This review adds **27 passing unittest methods, 107 arithmetic comparisons, and one explicit cross-read/write sequence**, not a full regression rerun. It does not establish new scene-scale limits, closed-solid support, LLM benefit, performance measurements, actual Blender mutation or desktop/Hook adoption. Existing large-scene unknowns and the author's legacy failures remain unchanged.

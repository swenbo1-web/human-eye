# Harness failures and corrections

Both original test logs and the complete failed test source are retained as
`baseline_checks_failed_01.log/json`, `candidate_checks_failed_01.log/json`,
and `verify_failed_01.py.txt`.

The first run expected `service.preview_action` to persist a pending router
record. Preview intentionally uses a detached probe router, so the assertion
failed on both baseline and candidate (`AssertionError: None is not true`,
verify.py line 154). Each first run discovered 15 tests: baseline 13 pass,
1 fail, 1 skip; candidate 14 pass, 1 fail. No product edit followed this
failure. The corrected fixture sends a public `router.handle_event` before_action
event using a prepared observation produced by public service.observe, then
persists it. No host mutation occurs. Both 15-test runs then passed (baseline
14 pass/1 skip; candidate 15 pass).

A separate cross-process comparison preflight initially excluded only config,
trace and source identity, and reported 12 differing rows (assertion failure in
the tool transcript). `equivalence_preflight_01.json` retains every difference.
These were fresh random observation UUIDs and JSON context strings containing
UUIDs and measured cache cost estimates. The final cross-process normalizer
consistently renames observation UUIDs, decodes nested context JSON, and drops
only config fingerprint, runtime source digest, trace ID, and
estimated_compute_ms_avoided. The final 12 saved-state/result rows match in
EQUIVALENCE.json. Within each process the tests and timing worker still assert
the entire actual persisted state equals its own original state after only the
expected prepared deletion and optional TTL/retry cleanup.

Two shell/harness setup errors appeared in the tool transcript before timing:

* A PowerShell-embedded Python one-liner intended to list differing leaves
  raised `SyntaxError: unterminated string literal (detected at line 1)`.
  It was replaced by the readable equivalence.py file.
* Its first isolated-mode launch raised `ModuleNotFoundError: No module named
  'timing'` at `from timing import normalized`. The script now inserts its own
  evidence directory before importing this local, product-free normalizer.

These three comparison/setup failures are not unittest methods, product
failures, or timing samples. Their messages above are excerpts copied from the
tool transcript; they are not presented as a raw command log. Two initial rg
discovery commands also named absent paths and returned 1; source discovery
continued with the existing verification tree.

The initial bare `git diff --check` reported CRLF as whitespace in added lines
of existing CRLF source files. `git -c core.whitespace=cr-at-eol diff --cached
--check` passed without rewriting line endings. One local edit initially
matched the identical surface_nearest invalidation block; review immediately
restored that block and changed task instead, before any verification or
product commit. The single frozen product candidate is 201fccc.

Timing was run exactly once after correctness checks and source freezing: 20
pairs, 40 successful children, no failed samples, no discarded or rerun batch.
Its immutable script hash appears in TIMING_PLAN.json and all source checks
match the frozen baseline/candidate hashes. Raw child stdout/stderr, exit codes,
process wall times and per-observe counts are in timing_samples.jsonl.

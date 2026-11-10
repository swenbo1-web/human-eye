# M1-NEAREST-EVIDENCE-001 independent validation review

GO for the bounded offline acceptance scope. No demonstrated candidate defect was removed from the denominator, and no additional mandatory case was identified. This reviewer inspected source and independently recomputed saved JSON, AST method counts, response bytes and hashes; no product, Blender, model or production service was executed.

Candidate: `107641ec19919d56aa843c1949261590fc338148`. Baseline runtime source: `0005ab437c8f330ed277bd49133348389fe7222bda3087f16450dce55ec9c05a`; candidate: `7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1`. Author implementation tree is `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe`. Relative references below are beneath that tree.

## Denominator and exclusions

AST independently counts 51 defined methods: CompactTaskEntry 14, SurfaceNearestEntry 19, NearestIntegration 10, new NearestEvidence 8. G06 was excluded before the original runs, giving 50. Both preserved `baseline_01` and `candidate_01` ran 50 with 49 passes and one identical FileNotFoundError; neither initial run passed. Excluding that obsolete action-journal assertion yields the final 49 = 14 + 18 + 9 + 8. Both `_02` results record 49 passes, no errors/failures/skips. These are selected current-contract results, not a rewrite of the historical 50-test failures. Selection and disclosed reasons are in `run_offline.py:178–189,238–246`.

- `SurfaceNearestEntryTests.test_03_one_actual_packet_reaches_real_summary_and_no_history`, `test_surface_nearest_entry.py:213–241`: both original runs passed the actual packet identity, capture/result/coverage assertions, then failed at line 236 reading a state file that a read-only ReadContext does not create. The failure does not distinguish the candidate. Current `test_task_entry.py:268–284` explicitly protects an existing opaque action journal, forbids `_locked`, `_save` and `_runtime`, checks two reads and stable default session, and verifies its bytes are unchanged. Current new real capture/result/count tests cover the remaining behavior. The excluded method's subsequent tail did not execute; its preceding assertions did execute in both retained original runs.
- `NearestIntegrationTests.test_g06_retained_unknown_partial_unknown_and_zero_unknown_tie`, `test_integration.py:255–267`: the test expects collinear triangle hulls to be refused, while the accepted v3 kernel supports them. `verification/arch_read_context_001/HARNESS_NOTES.md` already records this mismatch and replacement by a genuine exact-bit-budget unknown fixture. The existing degenerate-complete case and current partial/all-unknown bit-budget cases exercise the present contract. A zero winner combined with an unresolved candidate is not newly exercised; that missing combination alone does not establish a new defect in this evidence-projection change.

## New assertions and independent evidence

Eight new methods produce 18 observations: 17 MCP calls and one direct service call. They must not be advertised as 18 independent test methods. Per-record expected counters are asserted at `tests/test_nearest_evidence.py:127`, using wrappers that call the original pair/kernel/rank/nearest implementations (`:84–109`); closed-solid calls are forbidden. Independent sums of the saved observations agree for both versions:

| Capture | Pair | Kernel | Rank | Nearest | Closed solid |
|---:|---:|---:|---:|---:|---:|
| 18 | 24 | 24 | 16 | 20 | 0 |

Cases cover open-surface winner with strict pruning, positive and zero ties, partial and all-unknown results, valid distance with unpublished world witness, an exact-order winner despite rounded equal distances, and cold/warm/reversed focal order with returned-object mutation. Warm hits assert zero pair/kernel/rank/nearest work, while capture remains counted.

The evidence-to-original-measurement comparison is deliberate: this patch should expose measurements already obtained, without another solver pass. It is not the only correctness oracle. Candidate tests also check fixed independent expected distances/order/unknown status, witness distance, point membership on each captured mesh using a separate rational point-triangle minimum, and direction normalization (`test_nearest_evidence.py:150–177`). `verification/perf030_002_cases.py:21–44` implements that oracle with Fraction projection and constrained edge minima; it does not call the production solver. This avoids treating a projection of the solver's own output as independent geometric proof.

I independently checked all 18 cross-version original cores, full capture bindings, original measurements, packet work, diagnostics and counters. Only root `best_known_evidence`, `measurement_semantics` and `trace_id` are excluded from the original core; every runtime source value is validated before normalization. All 18 pairs match; no epoch, directory hash, source identity or fingerprint is dropped. The author's nine direct groups contain 11 observations and report full original-row equality; their comparison implementation was inspected, not rerun here.

## Bytes and benefit scope

I read and checked the actual contents, lengths and SHA-256 values of 104 saved representation files, also matching them back to raw evidence strings/objects.

| Representation | Records | Baseline B | Candidate B | Delta B |
|---|---:|---:|---:|---:|
| Compact body JSON re-encoding | 18 | 21,432 | 30,391 | +8,959 |
| Exact captured MCP content[0].text UTF-8 | 17 | 20,419 | 28,967 | +8,548 |
| Serialized complete MCP tool-result object | 17 | 23,076 | 32,440 | +9,364 |

The 17 text records are exact captured strings, but are not network frames. Complete tool-object bytes are a test serialization, not measured stdio wire bytes. The added-fields-only object total includes its own braces, so it is not the complete-response delta. The comparator labels these distinctions explicitly (`compare.py:103–128,268–276`).

Do not subtract +8,548 B from the earlier six consumer follow-up responses' wire bytes: they are different tasks/fixtures, record counts and serialization layers. This batch establishes unchanged original facts/work and added response content. It does not measure model tokens, eliminated follow-up requests, total task latency or monetary benefit.

## Independent rerun entrance and isolation detail

Minimal existing entrance: `verification/m1_nearest_evidence_001/run_offline.py`, with `--role baseline|candidate --expected-source-sha256 <exact digest above> --output <fresh direct child>`, using the existing dependency Python and `-I -B`. The runner requires Git access to the baseline, frozen source/tests/fixtures, and existing dependencies; it requires no Blender, model or production service. It guards external operations during tests. Read-only Git preparation occurs before those guards.

The parent's isolated wrapper has already reported both versions at 49/49 and matching 18-record comparisons. Its persistent output/engine directories are outside the implementation tree. However, changing `runner.HERE` alone does not redirect `SurfaceNearestEntryTests.setUp` (`test_surface_nearest_entry.py:123`), which explicitly uses `TemporaryDirectory(dir=TESTS)`. Those tests can create and then clean temporary directories under the implementation tests directory. This was an authorized local-test boundary, not a product defect. Do not claim zero implementation-tree writes. No source or sealed evidence modification is reported; the parent separately checks tracked status. No rerun is needed merely to rewrite that historical characterization.

No new combination matrix is required by the present findings. Known-zero plus unresolved and the rare direction bit-budget branch remain explicitly untested in this batch. Installed-entry, Blender and consumer benefit acceptance are separate from this offline result.
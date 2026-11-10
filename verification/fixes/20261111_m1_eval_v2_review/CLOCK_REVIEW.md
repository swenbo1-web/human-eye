# M1 EVAL READY V2 — independent clock review

Verdict: **GO for the reviewed timing changes; no blocking defect found.**

Reviewed preparation commit `81dcafec303bb867795f4474f5fe9bca2aa85c8e`, parent `82e976cd425fae9703399148a8938bd6099d486f`. Worktree: `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe`; paths below are relative to `verification/m1_task_entry_001_eval/`.

## Code findings

- `driver.py:34–42, 244–280`: `run_models` captures each cell origin before per-cell input hashes, snapshot validation and prompt construction. It passes that same origin to `prepare`; the return value cannot replace it. Standalone `prepare` captures its default origin before its TASKS/READY reads. The worker deadline remains the original cell origin plus 570 seconds.
- `driver.py:40, 53–93`: the separate actor startup deadline is `min(cell origin + 570 seconds, prepare origin + 40 seconds)`. The 40-second window starts at preparation entry, while the complete-cell budget includes preceding validation. Checks before spawning and after endpoint readiness preserve these absolute deadlines.
- `driver.py:278–300`: the original deadline is checked again before consumer launch. Cell duration covers validation, preparation, consumer work and owner close; setup uses the same original cell origin. Failed cells also use that origin.
- `consumer_transport.py:119–123`: consumer budget remains 450 seconds. This file has no diff from the parent commit; PLAN also retains 450/570. The fake-clock check substitutes the consumer, so preservation of the 450-second mechanism is established by code/diff inspection, not by pretending the fake consumer tests it.
- `driver.py:246, 292–332`: batch timing starts before GO/PLAN reads and ends after the last per-cell RUN_RESULT publication. It includes per-cell accounting that lies after cell end. It explicitly excludes the final timing-summary publication and caller overhead. The V2 report correctly says failures in batch setup may leave no completed batch measurement, and that 570 seconds is a worker deadline and cell acceptance threshold rather than a newly implemented universal consumer-process kill timer.

## Recorded evidence and independent recalculation

Read `finalize_v2/test_clock_check.py` and its existing `clock_check_01/RESULTS.json`; did not rerun the script. The script invokes the frozen real driver control/prepare code with fake clock, actor, transport and data. It asserts the actual launch configuration's original 570-second deadline and 40-second preparation window, including near-deadline cells.

Independently recalculated all recorded cells from JSON:

| Fake branch | Cells | Fake spawn / consumer | Cell wall | Batch wall | Outcome |
|---|---:|---:|---|---:|---|
| Successful, including last accounting | 27 | 27 / 27 | first 36 s; remaining 26 × 566 s | 14,894 s | all dispatched, no stop |
| Deadline exhausted during READY read | 1 | 0 / 0 | 576 s | 587 s | original deadline stop |

For all 28 records, duration equals end minus original start and worker deadline equals original start plus 570 seconds. All 27 consumer setup/whole-cell fields match those origins (31/561 seconds setup). Successful cell-wall sum is 14,752 seconds; batch adds 7 seconds of initial setup and 27 × 5 seconds of per-cell accounting. Expired batch is 7 + 576 + 4 seconds. Both recorded batch ends include the last per-cell publication and exclude the final summary's own 4 fake seconds. These are artificial-clock assertions, **not performance measurements**. Recorded real model and Blender calls are zero.

Verified hashes:

- driver: `21066d1a8b891784b2588626fb943e5b30a9ca8b6899dbcb7295724f562bf003`
- clock-check script: `cfa6f3a1347eb9460d9d8c77701b333cb828851692cdb3cff16963283303f753`
- recorded RESULTS: `d5a5a427d4ac29898c5699c04c793c4e72ec1011e501a075444e688101cb41f7`
- unchanged consumer transport: `bb7910f6d1fa2988d990fc3b6d11b469005c328d36f2031c6c8f64332e60602b`

This review independently inspected the timing diff, test implementation, recorded evidence and JSON arithmetic. It did not execute product code, Blender, models, the fake-clock test, the prior nine real preflight cells, geometry/oracle work or source matrix. The V2 report correctly retains those prior real preflight results as parent-commit evidence. No additional optimization or test matrix is requested by this review.

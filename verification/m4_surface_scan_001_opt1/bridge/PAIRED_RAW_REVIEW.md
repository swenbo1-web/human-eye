# OPT1 independent raw paired engineering review

## Inputs and method

The standard-library reviewer reads INPUT_BINDINGS.json and ten RESULTS.json files directly. Their SHA-256 values and all per-pair cache reuse mappings are retained in PAIRED_RAW_REVIEW.json. The script imports only the standard library and performs offline arithmetic and structural checks. Product, Blender and model execution counts are zero.

The expected fixed order is AB, BA, AB, BA, AB. Actual sequence timestamps match that order and show sequential execution. All 30 planned state rows are present exactly once. All errors are empty, automatic retries are zero and every business request has one actual host RPC. Sequence durations equal recorded end minus start, and each client duration equals its recorded request interval.

## Complete client request times

The following values are milliseconds. The paired ratios use each fixed pair directly.

| Pair | A cold | B cold | A repeat | B repeat | A edit | B edit | Edit B/A | Lifecycle prefix B/A |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1779.8854 | 1799.0802 | 41.6520 | 43.2680 | 1705.4856 | 160.1133 | 0.093881356 | 0.749871492 |
| 2 | 1765.2038 | 1774.6813 | 40.3287 | 40.9959 | 1696.2618 | 158.0728 | 0.093188917 | 0.729616572 |
| 3 | 1763.4408 | 1762.2169 | 40.2833 | 41.8994 | 1710.8078 | 160.3426 | 0.093723328 | 0.743986175 |
| 4 | 1757.9456 | 1770.6125 | 41.2554 | 54.1106 | 1723.8197 | 158.8843 | 0.092169906 | 0.758150468 |
| 5 | 1769.5204 | 1771.8144 | 40.9918 | 41.8090 | 1723.9927 | 158.1132 | 0.091713381 | 0.731982060 |

## Preregistered gates

| Gate | Independent result | Frozen bound | Passed |
|---|---:|---:|---|
| Median paired EDIT B/A | 0.093188916947 | <= 0.70 | true |
| Median paired cold B-A | 9.4775 ms | <= 88.2602 ms | true |
| Median paired repeat B-A | 1.6160 ms | <= 2.0496 ms | true |
| Median paired three-request sum B/A | 0.563041653431 | < 1 | true |
| Median paired lifecycle prefix B/A | 0.743986174814 | <= 1.05 | true |

The local-request engineering gates pass on this fixed sample. The recorded lifecycle prefix ratio is below one. The prefix includes startup, metadata, QA, per-state independent checks and exit, and ends before final RESULTS serialization, write and close. The exact complete lifecycle median remains unmeasured. Its separate conservative upper bound is 0.7537327451783967, established in LIFECYCLE_BOUND_REVIEW.md and ROOT_LIFECYCLE_BOUND.json. Server traces include wire encoding and stdio completion. Client windows additionally contain Peer evidence I/O. The measured five pairs describe this fixed engineering input. Model-task benefit remains a later acceptance step.

## Mechanism and capacity

Both versions execute 112 new computations for each cold request and zero for each static repeat. A executes 114 for each EDIT. B executes ten new computations and 104 measurement-cache hits for each EDIT.

Every B EDIT pair involving Obj_008 is a miss with one new computation. All 104 other pairs were present in that sequence’s cold record, preserve the exact ordered measurement key and ordered object-dependency digests, and report a cache hit with zero pair computations. All five sequences have the same counts. The JSON retains each of the 520 reuse mappings and fifty moving-pair misses.

Each EDIT reads zero resource vertices or faces and transforms exactly eight world vertices. Each cold reads 530 vertices and 978 faces. Repeated requests read zero resource coordinates and transform zero vertices.

All fifteen B requests have actual before/after cache telemetry. It reports a 2097152-byte capacity and 256 measurement slots, remains within the byte and entry limits, begins cold with zero entries and computations, and records the expected computation and hit deltas. B finishes each EDIT with 122 measurements. A’s frozen initial product omits actual cache telemetry. Its existing capacity policy is covered by its frozen installation/source binding in the parent’s review. The actual per-request counter checks in this report cover B.

## Exit and quality scope

All ten native closes report reaped processes, exit code zero, unchanged protected files and successful closure. All ten product launcher closes report reaped processes, stopped readers and exit code zero. All ten retained runtime handle checks confirm exited, zero exit code and closed handles. Twenty distinct native/launcher PIDs are present. The worker records report the registered QA edit, an unpoisoned session and matching final/accepted geometry fingerprints.

This review verifies raw timing, complete planned rows, reuse provenance, capacity telemetry and recorded exits. The parent separately verifies source binding, exact geometric truth and public witness quality. The original raw files retain their bytes.

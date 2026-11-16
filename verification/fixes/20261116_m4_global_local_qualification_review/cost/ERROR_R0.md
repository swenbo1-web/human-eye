# Independent checker R0 correction

The first saved-only run stopped at the registration wall-clock equality assertion. All preceding source, archive, session, budget and closure checks had passed.

`closeout.py` lines 111–112 obtain `closed_ns` and the reported registration duration from two successive `perf_counter_ns()` calls. R0 incorrectly required these separate samples to be equal within 10ns.

The corrected checker retains both observations. The registration-to-recorded-close span is 1774.8198905 seconds. The later duration sample is 1774.8198907 seconds, a 200ns residual. Their original fields remain preserved. Neither duration is labelled active work time.

The R0 source is preserved as `recompute_R0.py`. This correction rechecks saved files only. Product source, author evidence and actual calls remain unchanged.

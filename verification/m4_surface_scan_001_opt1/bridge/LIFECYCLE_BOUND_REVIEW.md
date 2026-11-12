# Complete lifecycle median bound review

The original `session_wall_ns` interval ends before final `RESULTS.json` serialization, write and close. My earlier raw paired review described its paired median ratio `0.743986174814158` as the complete lifecycle ratio. That label was incorrect. It is the recorded lifecycle prefix ratio. The paired review labels and JSON scope annotation now reflect that boundary. The original product and engineering raw records retain their bytes.

I independently read `sequence.py`, `run_pairs.py` and `common.py`, checked their hashes against the run's input binding, and reloaded all ten raw sequence results. Their hashes match `ROOT_LIFECYCLE_BOUND.json`.

`run_sequence` samples the prefix end, then synchronously calls `save` for its final result. `save` writes inside a `with` block and completes file close before returning. The serial controller waits for that return before beginning the next sequence. Therefore the next sequence's start is an upper bound on the preceding sequence's synchronous final-result save completion. This is a write-and-close boundary under the existing file API.

Each A prefix is a lower bound on that A sequence's complete duration. For every B with a following sequence, the elapsed interval from B start to the following start bounds B's complete duration above. Consequently, B's upper duration divided by its paired A prefix bounds that pair's complete B/A ratio above.

The independently recomputed finite bounds are `0.7537327451783967`, `0.7334767500030852`, `0.7481628670671135` and `0.762214492993534`, in paired order. Pair five B is the final sequence and has an unbounded upper endpoint in this proof.

For five ratios, the median is the third order statistic. Componentwise upper bounds preserve the order-statistic inequality. Keeping the fifth endpoint at positive infinity, the third smallest of the four finite bounds is `22248396 / 29517619`, approximately **0.7537327451783967**. It bounds the full five-ratio median above. The endpoint remains part of the denominator and no pair was discarded.

This upper bound is below the preregistered `1.05` lifecycle gate and below `1`. The complete lifecycle median gate and median net decrease are therefore established conservatively for these fixed five pairs. The exact complete lifecycle median is still unmeasured. The prefix median and complete-median upper bound should remain separately labeled.

This review performed standard-library offline arithmetic and source/hash inspection. It started zero product, Blender or model processes and changed no raw record.

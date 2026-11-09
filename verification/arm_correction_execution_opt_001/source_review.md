# Source preparation change and fixed diagnostic checks

`BoundArmPatch.capture` has one private `_prepare_expert=True` consumer choice.
The default changed-static path still calls `prepare_patch`, whose first step is
the existing `_parse_patch(dynamic=False)` in the same error order. The pure
geometry changed-static path calls that exact parser and discards its output;
it skips feature statistics only. No parsed arrays/cache or new validation
contract were introduced.

A detected change clears the old prepared object before validation. A later
default capture/analyze constructs from current static data whenever prepared
is absent, even when `static_changed=False`. Successful construction increments
`preparations` immediately, so a subsequent LBS/readback failure cannot conceal
already-performed work. `static_revision` still increments only at successful
capture commit with actual static change. Inspect, static/native reads,
same-index LBS and residency-version checks remain.

The expert's degenerate/nonplanar-reference `unknown` is not promoted to a parse
rejection. A dedicated test preserves this distinction and the exact diagnostic
output of accepted source bytes.

Final product source SHA256:
`9579805b0894b1505a46cf977a1715ab80155d53a97f469f448276059d8535ee`.
Final test SHA256:
`4841d20953f5d80d73615d16aeef903f97a3aeaadcb4c33fb32ca9639c9b46cc`.

`source_02/RESULT.json` records 10/10 methods, zero failures/errors/skips. Each
test compares exact accepted `a3a72b9` source bytes (verified SHA before compile)
against current source with the existing indexed 402-point RNA fixture and
unchanged real expert/weights. Fourteen explicit diagnostic prediction calls
are recorded separately from zero geometry model calls: seven old/seven new;
the two nonplanar-reference requests return unknown before network scoring.
Default model resolution is instrumented with a counting proxy that delegates
to the exact frozen default model. No Blender, new effect asset or training ran.

Coverage includes default capture/analyze; geometry then deferred analyze without
static revision change; retaining a valid unchanged preparation; changing real
native weights, invalidating and recomputing statistics; closed topology and
unsupported modifier rejection; same-index LBS rejection after/no construction;
preparation exception/recovery; default model resolution; and unknown semantics.

`source_01` is an earlier passing 8-method/10-call subset, not the final suite.
Its exact test bytes are retained as `source_01/TEST_SOURCE.py`. The final test
only added default-resolution and unknown checks plus robust result recording;
product source did not change between these two runs. No failed test attempt
occurred in this source subtask.

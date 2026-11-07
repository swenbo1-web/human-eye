# SURFACE-NEAREST-ENTRY-001 offline entry tests

Twelve groups in `test_surface_nearest_entry.py` cover the explicit mode and
mode-only schema, invalid envelopes before host access, actual single-capture
routing and zero complete-scene history, current named ties, retained degenerate
partial and unknown answers, genuine pair-cache reuse, loaded-source refusal,
the original request deadline across capture and MCP publication, compact
text-only delivery, and existing nearest/top1/task compatibility.

The parent controlled runner must first bind the legacy host-contract fixture
module and its BlenderSceneHost/BlenderHostError aliases to the current verified
blender_host source module, then import the acquisition and source-RNA fixtures.
The adapter executes the actual `capture_nearest_candidates`; the returned
packet reaches the actual accepted summary, exact ranker and surface kernel.
Only missing fake RNA fields use the previously accepted enrichment helper.
The tests never manufacture the final nearest answer. Static-plane x=2 gives
the independent complete/tie oracle. The late collinear triangle keeps a target
retained while forcing the genuine kernel's `surface_degenerate_triangle`
reason, yielding partial or unknown as appropriate.

All config/state/audit/cache writes are inside a TemporaryDirectory rooted in
this tests directory and removed by unittest cleanup. There is no real Blender,
NativeSession, RPC, consumer, paid API, install, or default configuration change.
At author handoff only Python syntax compilation is authorized; execution is
reserved for the parent's verified-source controlled runner. This document is
preregistration, not a passing-test claim.

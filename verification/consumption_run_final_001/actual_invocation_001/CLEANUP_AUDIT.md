# Postrun ownership and source audit

Read-only evidence audit for CONSUMPTION-RUN-001. No consumer/scorer, product import, process kill/restart, Blender, MCP service, RPC or model API was started by this audit. No truth, auth/key or hidden reasoning content was read.

The outer-owned controller PID23304 exited0 and was waited/reaped. The native owner records Blender PID28760 exited0 and was waited/reaped; its close response is `closed` with no error. WORKER_CLOSED records poison=false, equal initial/final geometry fingerprints and the original unchanged deadline. The worker's sole close event retains status=unknown; the independent closed response and owner wait/reap provide the terminal evidence rather than relabelling that event.

The frozen consumer record says its Codex parent exited1 and was reaped, but does not expose that CLI PID. It records tree_reaped=false and registered_tree_cleanup.confirmed=false because the native bridge STARTED receipt is absent. This audit does not infer an unrecorded PID or turn that missing receipt into proof that all children were absent. The original unsafe stop and remaining seven not_run slots must remain.

At02:47:07Z, bounded read-only process inspection found neither known PID alive and no python/blender/codex process matching the exact private runtime path markers. This is a scoped liveness observation, not full descendant-tree attestation; arbitrary descendants outside those markers remain unexposed. No foreign PID was signalled.

All17 pinned component SHA values match. All131 product files match their manifest, and the statically recomputed canonical source SHA is01c296b5dac9c8733670b7b82886fe774fb6e50222d1b935d6ac27efa04760de. The neutral helper matches5bc1152aeafab89220c93edeec51cbe32ace458cc07d3e7d0507b6412b816fb3. Original T01 asset, private neutral input and native-owned input all match574bcf2b5b636625ef3aa96e1c42af2a1d3fb83e75c6a04a30e83ff42882292a. PLAN remainscb78e4f754c7988d26296bbce7be34d8456e41329d11cd51e718cad1e4b49196.

The consumer stderr counter is71 bytes; its body was discarded by the frozen recorder and is unavailable here. No replay was performed to recover or guess the error text. The detailed fields, exact process-scan scope and source/asset rows are retained in CLEANUP_AUDIT.json. This report makes no answer-quality or engine-benefit claim.

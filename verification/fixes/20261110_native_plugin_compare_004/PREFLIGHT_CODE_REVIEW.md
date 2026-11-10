# COMPLEX-004 wrapper preflight code review

Fixed commit: `fde3c2f2f21d4b7b454c8cd76e0a28de70ddb796`.
Reviewer: `/root/scale_opt_design_review`, 2026-11-10.

**Recommendation: GO for the fixed 18-consumer trial after the root's freeze/source checks.** No obvious wrapper defect was found that requires another implementation round before these consumers. This is a focused read-only inspection, not a new product-safety audit. No tests, Blender, serve processes or model calls were started by this review.

## Inspected behavior

- `actor.Owner.close` uses nested `finally` blocks. Failure of final snapshot still reaches `peer.close`; failure of peer closure still reaches `native.close`. Each stage's failure remains in `errors`; `confirmed` requires unchanged geometry/asset, the native reap/exit/closed evidence, and successful peer closure when a peer exists. The prior skip-cleanup bug is fixed in this code.
- Plugin conditions launch the actual fixed entry with `serve --config <private config>` using the shared dependency Python. The actor obtains the ordinary live catalog, exposes only its unchanged `human_eye_scene_observe` item, checks equality with the frozen schema, and forwards the actual request to that process. Successful tool `result` content is passed through without geometry solving, answer projection or summary rewriting. The actor only wraps protocol errors as tool errors.
- N/O/C share the original native tool definition, helper and worker protocol. O/C alone expose the ordinary observe tool. Image requests without explicit `include_image=false` are openly rejected rather than silently rewritten. Product state/audit files remain within each cell's private output directory.
- The driver fixes 18 fresh cells: two tasks, N/O/C, three repetitions, balanced Latin group positions with task-order alternation. It uses the frozen prompt bytes plus the common rules, and includes setup, consumer and owner finalization in full-cell elapsed time. Failed cells and unrun cells remain in the denominator. Consumer replacement/retry is not implemented.
- Consumer settings retain one model/effort/login route and empty workspaces. Tool approval and deviation checks name `execute_blender_code` and `human_eye_scene_observe`. The stream retains public messages/usage/errors; unexposed fees remain unmeasured.

## Budget and attempt accounting

The model deadline is 450 seconds from consumer start; the worker has the original 570-second deadline from cell setup. No request resets either deadline. Actual native and plugin calls receive a 30-second backend limit. CLI's 40-second outer MCP timeout is a transport envelope, not a larger product-computation allowance. The first 32 tool attempts can reach a backend; later attempts receive a budget rejection and are still recorded. Tool response admission uses the common 1 MiB total; native code and worker bounds remain 256 KiB and 128 RPCs.

For normal JSON-RPC tool requests, successful responses, explicit refusals, backend exceptions and undeliverable oversized responses all reach the actor's `finally` accounting with request, elapsed time, exception and response size. Peer RPC attempts separately retain transmitted/received frames and receipts. Owner cleanup is independent of the CLI client lifecycle.

Two reporting distinctions should remain explicit during results analysis:

1. The tool log may contain more than 32 **attempts** if a consumer keeps requesting after exhaustion; only the first 32 are eligible to execute. Those additional rejections are not extra execution allowance and must not disappear from cost records.
2. `TOOLS.json` wire bytes are the response bytes admitted/intended for delivery. Actual client delivery is established from thin-client TX/RX records, not inferred solely from backend production.

## Existing evidence read, not rerun

- `WRAPPER_TESTS.json`: 9 fake-host tests, zero failures/errors/skips. Reviewed the tests for normal order, final-snapshot failure, peer-close failure, combined failure, request failures, zero-image refusal and an undeliverable error response.
- `PREFLIGHT_REVIEW.json`: six no-model scene chains, unchanged geometry and normal close in all six; common native equality and ordinary schema equality; four real plugin queries qualified against existing truth; failed attempts retained.

The root separately owns the source/install/freeze verification and the final GO file. No source, author evidence, default configuration or model-facing input was modified by this review. This note does not claim consumer quality, remote quota availability, resolved model effort or performance benefit before the real trial.

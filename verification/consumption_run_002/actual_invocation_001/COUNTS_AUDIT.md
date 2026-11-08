# RUN002 counts audit

Eight scheduled slots remain **1 error and 7 not_run**. One CLI context returned a final and terminal usage; the frozen valid-completion count remains **0** because the registered process tree was not confirmed closed. No answer-quality score is assigned.

| Order | Task | Arm | Raw status |
| --- | --- | --- | --- |
| 1 | T01 | N | error |
| 2 | T01 | P | not_run |
| 3 | T02 | P | not_run |
| 4 | T02 | N | not_run |
| 5 | T03 | N | not_run |
| 6 | T03 | P | not_run |
| 7 | T04 | P | not_run |
| 8 | T04 | N | not_run |

One public `mcp_tool_call` to `native.execute_blender_code` failed with `MCP tool call requires approval, but approval policy is never`. The stdio bridge received exactly 3 frames: `initialize`, `notifications/initialized`, and `tools/list`. There was no `tools/call` frame and no execute-code request reached Blender. MCP traffic was 409 TX / 787 published RX bytes. The compact complete tools array was 563 UTF-8 bytes (descriptor: 561); effective host/model-delivered schema bytes remain null. Exactly one physical native RPC was observed: closure, using 17 TX / 62 RX bytes. Image counts are zero.

The final was received 49.6407478 seconds after dispatch. Its artifact is 632 bytes, containing 13 CRLF pairs; the logical final-text ledger charge is 619 UTF-8 bytes. These are distinct disk and logical-text measurements, and are not counted twice as model output. The final body was not interpreted.

Terminal usage is recorded once: 48,129 input tokens, including 35,456 cached input tokens, and 1,328 output tokens. Provider requests and fees remain null; the backend is unexposed. Outer controller wall time was 59.3571895 seconds, first-cell wall time was 58.9164216 seconds, and consumer entry through cleanup was 57.4009768 seconds. Nested intervals are not added.

CLI PID 20884 exited 0 and was reaped; controller PID 15456 exited 0 and was reaped. The one Blender session, PID 18996, has a closed response and owned reap with exit 0, poison false, and equal terminal fingerprints. Its worker audit contains one raw `unknown` close event. Bridge PID 14744 has STARTED evidence but its EXIT receipt was missing at the frozen check. Later PID observations do not upgrade the frozen tree-confirmation flag or restart the remaining slots. All seven not-run reasons remain `previous_slot_cleanup_not_confirmed_no_further_start`.

`COUNTS_AUDIT.json` records raw clocks, exact slot states, process metadata, wire frame hashes, evidence paths and hashes, and access-path boundaries. The audit used only local metadata and public events. It did not read truth, score answers, inspect global private logs, or launch a consumer, model, Blender, service, socket, or RPC.

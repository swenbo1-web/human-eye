# Source-region consumption delivery and protocol review

Independent review of author 28cc6fc728c9fb62d46120f3be14b46d673f675a confirms two harness defects and a reproducible client-presentation mismatch. Original MCP and CLI completion records carry the full S2/S3 observations. The matching public CLI implementation applies a much smaller model-context budget after that logging boundary. Its reconstructed output loses the measured distance, witness and metre unit, while preserving end-of-report visibility reasons and unknowns.

## Actual delivery and protocol

S1 makes two read_observation calls. Both actual requests contain the expected empty arguments plus standard transport _meta. R0 compares the entire params object with a two-key dictionary, so both requests return empty_parameter_read_observation_required. Both actual CLI events are failed tool completions containing that error and no image. S1 has zero observation deliveries.

R1 changes exactly read_observation.py and run_slot.py among 178 direct frozen inputs. The original source bytes remain in protocol_revisions. R1 permits dictionary _meta, answers optional resource enumeration and writes the delivery ledger before returning. Fixed inputs, product bytes, prompt and scoring inputs retain their original identities. Recorded order is original freeze, S1 start and closure, protocol qualification, revised freeze, S2, S3. S1 is retained with zero replacement consumers.

S2 and S3 each have one successful original reader response and a byte-equivalent actual CLI tool completion. Their text lengths are 117,623 and 117,620 UTF-8 bytes. They contain the exact distance 0.37011719389236364, nearest witness, source mapping, metre semantics and zero-pixel reason. Each also contains its original 512 by 512 PNG, respectively 1,895 and 1,881 bytes. Original MCP content, actual CLI content and safe projected legacy ZIP stdout agree. Neither raw tool result contains a truncation marker. This establishes the public logging boundary's complete content.

All three consumers additionally make two Codex resource discovery calls. Every completed discovery returns exactly an empty resources or resourceTemplates list. S1's underlying server replies -32601 to the corresponding optional methods. R1's underlying replies are empty lists. There are six completed empty discoveries in total.

## Client model-context budget

Every actual consumer emits a public missing-model-metadata warning and selects fallback metadata. Actual argv and inherited settings have no tool_output_token_limit override. Per-tool configuration contains approval_mode alone, with user configuration ignored. Current local model caches belong to CLI 0.169.0, while the executed CLI is fixed at 0.152.1. Those caches are recorded as a separate observation and are excluded from the executed-policy inference.

The official rust-v0.152.1 source at commit 5adb68a49933ae446bf11935662c83dba55a0804 defines fallback truncation as 10,000 **bytes**. PreparedMcpCall.output_token_limit reads only the effective server configuration's per-tool output_token_limit. It obtains no override from the response _meta, tool content or schema. The actual frozen configuration supplies none. [Fallback model metadata](https://github.com/openai/codex/blob/5adb68a49933ae446bf11935662c83dba55a0804/codex-rs/models-manager/src/model_info.rs#L142) · [Per-tool override source](https://github.com/openai/codex/blob/5adb68a49933ae446bf11935662c83dba55a0804/codex-rs/codex-mcp/src/binding.rs#L271)

The MCP handler uses that policy, converts the original text and PNG into content items, prepends its wall-time header and truncates with a 1.2 serialization allowance. Text receives approximately 12,000 bytes minus the header. PNG content passes through without consuming that text budget. Logging separately uses the raw MCP result. The history stage then receives a 3,000 approximate-token override and applies a second truncation pass. Its estimator uses four bytes per token. [MCP policy selection](https://github.com/openai/codex/blob/5adb68a49933ae446bf11935662c83dba55a0804/codex-rs/core/src/tools/handlers/mcp.rs#L222) · [Independent logging and model payload paths](https://github.com/openai/codex/blob/5adb68a49933ae446bf11935662c83dba55a0804/codex-rs/core/src/tools/context.rs#L109) · [History truncation](https://github.com/openai/codex/blob/5adb68a49933ae446bf11935662c83dba55a0804/codex-rs/core/src/context_manager/history.rs#L238)

The exact header wall-time scalar was not captured. Both possible header lengths for these sub-100-second sessions were reconstructed from the fixed source algorithm. Both yield identical final retained original byte ranges, using zero-based half-open intervals.

| Case | Retained prefix | Retained suffix | Removed distance | Removed witness | Removed zero-pixel field |
| --- | --- | --- | --- | --- | --- |
| S2 | [0,5982) | [111641,117623) | 10595 | 10615 | 110437 |
| S3 | [0,5982) | [111638,117620) | 10595 | 10615 | 110449 |

Both variants remove the measured fact and method, coordinates, metre semantics, explicit unit m and coordinate-frame fields. Tail copies of measurement scope, complete_surface_visibility and the appropriate zero-sample reason survive. The source middle truncation adds its own marker at the model-payload stage, which explains why it is absent from the raw completion event. Four clearly labeled same-tag reconstruction text files and all field occurrence positions accompany RESULT.json. [Content-item budgeting](https://github.com/openai/codex/blob/5adb68a49933ae446bf11935662c83dba55a0804/codex-rs/utils/output-truncation/src/lib.rs#L114) · [Exact UTF-8 middle truncation](https://github.com/openai/codex/blob/5adb68a49933ae446bf11935662c83dba55a0804/codex-rs/utils/string/src/truncate.rs#L39)

This is a deterministic reconstruction from same-version public source, frozen configuration and observed fallback warnings. It identifies a concrete client-stage mechanism matching the missing facts. Provider request payloads were not captured, and a reproducible-build attestation connecting the installed binary to the public tag was not supplied. The saved full CLI event alone cannot establish the model's complete input.

## Harness correction required

The inherited event loop appends all completed MCP calls to tool_calls. The owner archive matcher compares that whole list with reader-only owner entries. This produces the original false count mismatches 2 versus 4, 1 versus 3 and 1 versus 3. The same collector also marks empty Codex discovery as unexpected because its allowlist only includes the reader. Fixing only the archive count leaves that second failure active.

The minimal harness change is to retain and account for all calls while binding only the declared server's read_observation calls to the reader ledger. Classify these exact empty discovery results separately. Preserve their time, usage and full call count, and preserve all original failed statuses. Actual complete tool counts are 4,3,3 and reader attempts are 2,1,1. Both accounting views satisfy the four-call bound in this batch. No tool-cap exhaustion occurred.

## Next delivery design

The parent's facts-first probe preserves the entire original self-contained v1 region_ref, task facts and nearest source witness, actual image_scope and image references. Independent pure-function evaluation reproduces its R0 lengths 10,048/10,075/10,071 bytes and revised lengths 9,698/9,725/9,721 bytes. Each remains completely unchanged through both reconstructed text-budget passes. A maximum 11,000-byte text plus its original PNG also fits these passes, whose smaller available text budget is 11,964 bytes. No input-budget increase is needed for these fixed examples.

The image branches unconditionally retain InputImage in both passes. This proves preservation through this text-budget mechanism. Actual image tokens, provider processing and future model adoption remain unmeasured. Product implementation and fresh model consumption of the probe remain unrun.

## Review boundaries and retained corrections

The checker independently verifies 253 archived identities, both source freezes, actual public tool completions, four business attempts, six discoveries and the two successful image deliveries. It reads only projected stdout for event semantics and explicitly skips analysis and reasoning event fields. No hidden reasoning body is read or reported. Official source excerpts, source URLs, SHA pins and the upstream LICENSE and NOTICE are saved under reference.

The initial passed review used a spaced lookup for a compact selected_surface_pixels key. The final lookup correctly records its original position and removal. The initial script and passed result remain as R0 history. No original evidence or failure was deleted.

This batch adds zero model calls, live calls, MCP calls, rasters, image encodings and paid calls. All writes are inside this delivery directory. The reviewer's own AL handle remains bound to its expired historical task740 assignment. Work follows the root's explicit task749 delegation without mutating parent records or borrowing another handle.

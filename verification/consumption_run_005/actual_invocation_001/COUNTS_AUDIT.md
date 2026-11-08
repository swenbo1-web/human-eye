# RUN005 counts audit

Eight frozen slots: {'completed': 8}. Returned finals 8; saved final artifacts 8; frozen valid completions 8. No quality score assigned.

| Slot | Task | Arm | Status | Public tools | Native/HE/close RPC | Input/cached/output tokens | Final receive seconds |
|---|---|---|---|---:|---|---|---:|
| 1 | T01 | N | completed | 3 | 3/0/1 | 73728/47488/1110 | 49.5093924 |
| 2 | T01 | P | completed | 2 | 1/1/1 | 60257/35712/809 | 36.8304213 |
| 3 | T02 | P | completed | 3 | 2/1/1 | 170402/152320/2017 | 104.1348622 |
| 4 | T02 | N | completed | 4 | 4/0/1 | 132862/115712/2407 | 86.7407862 |
| 5 | T03 | N | completed | 2 | 2/0/1 | 57448/32640/938 | 41.1443175 |
| 6 | T03 | P | completed | 2 | 1/1/1 | 59294/52224/864 | 45.8966539 |
| 7 | T04 | P | completed | 2 | 1/1/1 | 59630/35200/982 | 42.438985 |
| 8 | T04 | N | completed | 2 | 2/0/1 | 65232/36992/1139 | 44.3069215 |

Public tools observed 20; admitted server actions 20. MCP frames 56 with methods {'initialize': 12, 'notifications/initialized': 12, 'tools/list': 12, 'tools/call': 20}. MCP TX 33754 / generated RX 133118 / published RX 133118 bytes.

Physical RPCs 28: {'native_execute_code': 16, 'administrative_close': 8, 'HE_owned_socket': 4}. Administrative closes are separate from the execute ledger. HE socket RPC count measures owned physical requests, not the number of HE logical observe calls. Full returned catalogues and each descriptor are measured per tools/list frame in JSON; effective model-delivered schema bytes remain null.

Terminal usage counted once across 8 contexts: input 678853, cached subset 508288, output 10266. Provider requests and fees remain null; actual backend is unexposed.

MCP images generated/published 0/0; ledger generated 0; private PNG files 0; worker render events {}.

Outer controller wall 485.3558329s. Runner wall 485.2670674s. Per-cell and consumer clocks retain their own boundaries and are not added. Final receive latency does not establish task correctness or engine benefit.

Tool completion states: {'completed': 19, 'failed': 1}. The failed HE tool error messages, preserved verbatim as ordinary tool results, are {}. These tool errors do not rewrite the eight frozen slot states.

Failed public tool outcomes including non-exception unknown packets: [{'slot': 7, 'id': 'item_2', 'server': 'human_eye', 'tool': 'human_eye_scene_observe', 'status': 'failed', 'error': None, 'result_packet_metadata': [{'result_kind': 'surface_nearest', 'status': 'unknown', 'scope': 'surface_nearest_candidates', 'coverage': {'targets_excluding_focal': 4, 'distance_valid': 0, 'strictly_excluded': 0, 'unresolved': 4}, 'execution_authority': False, 'unresolved_reason_counts': {'surface_degenerate_triangle': 4}}], 'failed_tool_text_utf8_bytes': 1727}]. A physical execute response can be success while the public tool result reports unknown/isError; those layers are not merged.

Returned catalogue UTF-8 bytes across 12 tools/list frames total 77612. Actual catalogue shapes and descriptor byte counts are [{'bridge': 'bridge_native', 'full_server_catalogue_utf8_bytes': 563, 'descriptors': [{'name': 'execute_blender_code', 'utf8_bytes': 561, 'description_utf8_bytes': 320, 'description_JSON_string_utf8_bytes': 322}], 'occurrences': 8}, {'bridge': 'bridge_he', 'full_server_catalogue_utf8_bytes': 18277, 'descriptors': [{'name': 'human_eye_scene_observe', 'utf8_bytes': 9236, 'description_utf8_bytes': 1422, 'description_JSON_string_utf8_bytes': 1442}, {'name': 'human_eye_transform', 'utf8_bytes': 2666, 'description_utf8_bytes': 536, 'description_JSON_string_utf8_bytes': 538}, {'name': 'human_eye_connection_status', 'utf8_bytes': 217, 'description_utf8_bytes': 85, 'description_JSON_string_utf8_bytes': 87}, {'name': 'human_eye_clearance_segment', 'utf8_bytes': 6153, 'description_utf8_bytes': 716, 'description_JSON_string_utf8_bytes': 718}], 'occurrences': 4}]. Host/model filtering remains unexposed.

## P entry and subsequent native call ordering

| Slot | Frozen status | HE used | First HE route | First HE completed | Direct name nearest static shape | Entry parameter errors | Native starts after any/complete/unknown nearest |
|---|---|---|---|---|---|---:|---|
| 2 | completed | True | direct_name | True | True | 0 | 1/1/0 |
| 3 | completed | True | direct_name | True | True | 0 | 2/2/0 |
| 6 | completed | True | direct_name | True | True | 0 | 1/1/0 |
| 7 | completed | True | direct_name | False | True | 0 | 1/0/1 |

All four scheduled P slots remain in the denominator, including failure/not_run/non-use. Direct-name static shape checks do not establish lookup success or answer quality. First-request selector/fact shapes, raw public failure messages and nearest completion packet status/coverage are retained in JSON. Native-after-nearest means only a later item.started receive timestamp in the same consumer, not a claim about why it was called or whether an answer was correct.

Collaboration metadata is handled in the separate dedicated audit. Original discarded-event counters are retained here; they do not establish absence of collaboration or complete usage accounting. Missing participant usage, provider requests and fees are not filled with zero.

The audit parsed only public event metadata, numeric usage, tool/protocol envelopes, byte lengths and worker audit metadata. Final text was hashed and counted as bytes only. Disk CRLF bytes and logical final-text ledger bytes are recorded separately. Frozen results, cleanup flags, prior runs and source files were not modified. No private global log, truth, model, CLI consumer, Blender, service, socket or RPC was used by this audit.

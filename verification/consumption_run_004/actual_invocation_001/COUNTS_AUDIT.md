# RUN004 counts audit

Eight frozen slots: {'completed': 8}. Returned finals 8; saved final artifacts 8; frozen valid completions 8. No quality score assigned.

| Slot | Task | Arm | Status | Public tools | Native/HE/close RPC | Input/cached/output tokens | Final receive seconds |
|---|---|---|---|---:|---|---|---:|
| 1 | T01 | N | completed | 3 | 3/0/1 | 78991/49536/1198 | 65.5777855 |
| 2 | T01 | P | completed | 3 | 1/2/1 | 80594/74624/1016 | 66.5676602 |
| 3 | T02 | P | completed | 4 | 2/2/1 | 135885/84864/1801 | 79.0947193 |
| 4 | T02 | N | completed | 3 | 3/0/1 | 119185/83328/1927 | 109.9523433 |
| 5 | T03 | N | completed | 3 | 3/0/1 | 86474/72832/1729 | 89.2170558 |
| 6 | T03 | P | completed | 3 | 1/2/1 | 113493/81152/1163 | 91.6255108 |
| 7 | T04 | P | completed | 3 | 1/2/1 | 74889/61056/1306 | 55.4287033 |
| 8 | T04 | N | completed | 2 | 2/0/1 | 57931/33536/1014 | 50.2541361 |

Public tools observed 24; admitted server actions 24. MCP frames 60 with methods {'initialize': 12, 'notifications/initialized': 12, 'tools/list': 12, 'tools/call': 24}. MCP TX 40194 / generated RX 409622 / published RX 409622 bytes.

Physical RPCs 32: {'native_execute_code': 16, 'administrative_close': 8, 'HE_owned_socket': 8}. Administrative closes are separate from the execute ledger. HE socket RPC count measures owned physical requests, not the number of HE logical observe calls. Full returned catalogues and each descriptor are measured per tools/list frame in JSON; effective model-delivered schema bytes remain null.

Terminal usage counted once across 8 contexts: input 747442, cached subset 540928, output 11154. Provider requests and fees remain null; actual backend is unexposed.

MCP images generated/published 0/0; ledger generated 0; private PNG files 0; worker render events {}.

Outer controller wall 648.2442061s. Runner wall 648.1486877s. Per-cell and consumer clocks retain their own boundaries and are not added. Final receive latency does not establish task correctness or engine benefit.

Tool completion states: {'completed': 23, 'failed': 1}. The failed HE tool error messages, preserved verbatim as ordinary tool results, are {}. These tool errors do not rewrite the eight frozen slot states.

Returned catalogue UTF-8 bytes across 12 tools/list frames total 75752. Actual catalogue shapes and descriptor byte counts are [{'bridge': 'bridge_native', 'full_server_catalogue_utf8_bytes': 563, 'descriptors': [{'name': 'execute_blender_code', 'utf8_bytes': 561}], 'occurrences': 8}, {'bridge': 'bridge_he', 'full_server_catalogue_utf8_bytes': 17812, 'descriptors': [{'name': 'human_eye_scene_observe', 'utf8_bytes': 8771}, {'name': 'human_eye_transform', 'utf8_bytes': 2666}, {'name': 'human_eye_connection_status', 'utf8_bytes': 217}, {'name': 'human_eye_clearance_segment', 'utf8_bytes': 6153}], 'occurrences': 4}]. Host/model filtering remains unexposed.

Failed public tool outcomes, including non-exception unknown packets: [{'slot': 7, 'id': 'item_3', 'server': 'human_eye', 'tool': 'human_eye_scene_observe', 'status': 'failed', 'error': None, 'result_packet_metadata': [{'result_kind': 'surface_nearest', 'status': 'unknown', 'scope': 'surface_nearest_candidates', 'coverage': {'targets_excluding_focal': 4, 'distance_valid': 0, 'strictly_excluded': 0, 'unresolved': 4}, 'execution_authority': False, 'unresolved_reason_counts': {'surface_degenerate_triangle': 4}}], 'failed_tool_text_utf8_bytes': 1727}]. A physical execute response can be success while the public tool result reports unknown/isError; these layers are not merged.

Actual catalogue descriptor, plain-description and JSON-description-string byte boundaries: [{'bridge': 'bridge_native', 'full_server_catalogue_utf8_bytes': 563, 'descriptors': [{'name': 'execute_blender_code', 'utf8_bytes': 561, 'description_utf8_bytes': 320, 'description_JSON_string_utf8_bytes': 322}], 'occurrences': 8}, {'bridge': 'bridge_he', 'full_server_catalogue_utf8_bytes': 17812, 'descriptors': [{'name': 'human_eye_scene_observe', 'utf8_bytes': 8771, 'description_utf8_bytes': 1453, 'description_JSON_string_utf8_bytes': 1493}, {'name': 'human_eye_transform', 'utf8_bytes': 2666, 'description_utf8_bytes': 536, 'description_JSON_string_utf8_bytes': 538}, {'name': 'human_eye_connection_status', 'utf8_bytes': 217, 'description_utf8_bytes': 85, 'description_JSON_string_utf8_bytes': 87}, {'name': 'human_eye_clearance_segment', 'utf8_bytes': 6153, 'description_utf8_bytes': 716, 'description_JSON_string_utf8_bytes': 718}], 'occurrences': 4}]. Plain description bytes and serialized descriptor bytes are distinct.

## P entry and subsequent native call ordering

| Slot | Frozen status | HE used | First HE completed | First HE task shape | Name/ID entry parameter errors | Native starts after any/complete nearest |
|---|---|---|---|---|---:|---|
| 2 | completed | True | True | True | 0 | 1/1 |
| 3 | completed | True | True | True | 0 | 2/2 |
| 6 | completed | True | True | True | 0 | 1/1 |
| 7 | completed | True | True | True | 0 | 1/0 |

All four scheduled P slots remain in the denominator. First-request selector/fact shapes, raw public failure messages and nearest completion packet status/coverage are retained in JSON. Native-after-nearest means only a later item.started receive timestamp in the same consumer, not a claim about why it was called or whether an answer was correct.

The audit parsed only public event metadata, numeric usage, tool/protocol envelopes, byte lengths and worker audit metadata. Final text was hashed and counted as bytes only. Disk CRLF bytes and logical final-text ledger bytes are recorded separately. Frozen results, cleanup flags, prior runs and source files were not modified. No private global log, truth, model, CLI consumer, Blender, service, socket or RPC was used by this audit.

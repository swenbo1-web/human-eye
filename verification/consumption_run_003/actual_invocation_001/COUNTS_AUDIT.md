# RUN003 counts audit

Eight frozen slots: {'completed': 8}. Returned finals 8; saved final artifacts 8; frozen valid completions 8. No quality score assigned.

| Slot | Task | Arm | Status | Public tools | Native/HE/close RPC | Input/cached/output tokens | Final receive seconds |
|---|---|---|---|---:|---|---|---:|
| 1 | T01 | N | completed | 3 | 3/0/1 | 93250/78592/1532 | 95.033848 |
| 2 | T01 | P | completed | 5 | 1/2/1 | 109082/92288/1230 | 102.0917308 |
| 3 | T02 | P | completed | 5 | 1/2/1 | 219627/162816/1939 | 132.0593543 |
| 4 | T02 | N | completed | 3 | 3/0/1 | 117531/102656/2824 | 148.7092623 |
| 5 | T03 | N | completed | 2 | 2/0/1 | 64144/49792/891 | 58.7209187 |
| 6 | T03 | P | completed | 4 | 1/2/1 | 127866/111104/1830 | 105.0890825 |
| 7 | T04 | P | completed | 4 | 2/0/1 | 91623/76416/1111 | 83.4840441 |
| 8 | T04 | N | completed | 2 | 2/0/1 | 62239/48128/1027 | 59.4470359 |

Public tools observed 28; admitted server actions 28. MCP frames 64 with methods {'initialize': 12, 'notifications/initialized': 12, 'tools/list': 12, 'tools/call': 28}. MCP TX 43457 / generated RX 311969 / published RX 311969 bytes.

Physical RPCs 29: {'native_execute_code': 15, 'administrative_close': 8, 'HE_owned_socket': 6}. Administrative closes are separate from the execute ledger. HE socket RPC count measures owned physical requests, not the number of HE logical observe calls. Full returned catalogues and each descriptor are measured per tools/list frame in JSON; effective model-delivered schema bytes remain null.

Terminal usage counted once across 8 contexts: input 885362, cached subset 721792, output 12384. Provider requests and fees remain null; actual backend is unexposed.

MCP images generated/published 0/0; ledger generated 0; private PNG files 0; worker render events {}.

Outer controller wall 838.1542974s. Runner wall 838.0286539s. Per-cell and consumer clocks retain their own boundaries and are not added. Final receive latency does not establish task correctness or engine benefit.

Tool completion states: {'completed': 21, 'failed': 7}. The failed HE tool error messages, preserved verbatim as ordinary tool results, are {'task selector must contain exactly one nonempty id or name of at most 256 UTF-8 bytes': 4, 'task requested_facts must be a nonempty unique finite fact list': 3}. These tool errors do not rewrite the eight frozen slot states.

Returned catalogue UTF-8 bytes across all twelve tools/list frames total 75736. Each native catalogue is 563 bytes (descriptor 561). Each HE catalogue contains four tools and is 17,808 bytes; its human_eye_scene_observe descriptor is 8,767 bytes. Host/model filtering remains unexposed.

The audit parsed only public event metadata, numeric usage, tool/protocol envelopes, byte lengths and worker audit metadata. Final text was hashed and counted as bytes only. Disk CRLF bytes and logical final-text ledger bytes are recorded separately. Frozen results, cleanup flags, prior runs and source files were not modified. No private global log, truth, model, CLI consumer, Blender, service, socket or RPC was used by this audit.

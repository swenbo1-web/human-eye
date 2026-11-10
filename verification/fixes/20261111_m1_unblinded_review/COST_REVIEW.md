# Independent cost review — M1 formal 27 cells

All 27 fixed records included; root-sealed quality 27/27 unchanged. No additional consumer, product or Blender execution. N is native, C the ordinary large interface, S the compact interface on the same7411 product.

| Task | Arm | n | Full cell median / range (s) | Full cell sum (s) | Consumer median (s) | Calls / errors | Input tokens | Output tokens |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| T1 | N | 3 | 80.742 / 70.161–127.355 | 278.258 | 79.066 | 10 / 0 | 89012 | 6604 |
| T1 | C | 3 | 27.619 / 23.727–32.429 | 83.775 | 25.562 | 3 / 0 | 40721 | 880 |
| T1 | S | 3 | 24.545 / 22.400–25.965 | 72.910 | 22.493 | 3 / 0 | 36108 | 779 |
| T2 | N | 3 | 77.931 / 72.847–93.497 | 244.274 | 76.272 | 10 / 0 | 82952 | 7364 |
| T2 | C | 3 | 82.831 / 66.714–102.684 | 252.230 | 80.760 | 17 / 5 | 175216 | 5222 |
| T2 | S | 3 | 36.856 / 30.871–46.741 | 114.468 | 34.874 | 6 / 0 | 53695 | 1122 |
| T3 | N | 3 | 71.549 / 67.600–72.542 | 211.691 | 70.368 | 9 / 0 | 72672 | 6646 |
| T3 | C | 3 | 72.232 / 61.871–95.098 | 229.201 | 70.210 | 16 / 5 | 167072 | 4801 |
| T3 | S | 3 | 33.706 / 31.321–35.115 | 100.141 | 31.525 | 6 / 0 | 53960 | 1197 |

| Arm (9 cells each) | Full total / median (s) | Calls / errors | Input | Cached input subset | Output | Reasoning output subset |
|---|---:|---:|---:|---:|---:|---:|
| N | 734.224 / 72.847 | 29 / 0 | 244636 | 170112 | 20614 | 1670 |
| C | 565.206 / 66.714 | 36 / 10 | 383009 | 282880 | 10903 | 608 |
| S | 287.519 / 31.321 | 15 / 0 | 143763 | 70016 | 3098 | 14 |

Batch wall = 1587.8146511 s; sum of 27 full cells = 1586.9485602 s; batch setup/inter-cell accounting difference = 0.8660909 s. Startup, failed requests, fallback and owner cleanup remain included. Tool wall times are nested; do not add them to cell wall.

Cached tokens are already inside input; reasoning tokens are already inside output. Both subset counts are publicly reported in this run. Provider request counts, per-tool tokens, model-only reasoning time and dollar costs are not exposed. All stderr diagnostics and 10 tool errors are retained; no consumer replacement or observed provider retry marker was found. Missing thin-client EXIT receipts remain unknown independently of confirmed owner/worker cleanup.

## Six S nearest follow-up calls

| Cell | Nearest → second start (s) | Second public tool wall (s) | Second → final (s) | Nearest → final (s) | Second response wire / text bytes |
|---|---:|---:|---:|---:|---:|
| 05 | 7.720 | 0.066960 | 8.328 | 16.115 | 2935 / 2607 |
| 07 | 8.268 | 0.045801 | 7.810 | 16.124 | 3268 / 2906 |
| 10 | 6.254 | 0.067510 | 9.714 | 16.036 | 2935 / 2607 |
| 15 | 4.672 | 0.050076 | 12.535 | 17.257 | 3268 / 2906 |
| 20 | 4.585 | 0.036384 | 8.845 | 13.466 | 3268 / 2906 |
| 27 | 5.359 | 0.073053 | 10.569 | 16.001 | 2935 / 2607 |

The direct second-call owner work totals 0.2819606 s; public tool intervals total 0.3397841 s. The larger nearest-to-final span includes additional query construction and final generation/provider waiting; it is not all removable latency or pure reasoning. Session usage cannot identify tokens specific to the second call.

## Cost boundaries and retained limitations

Public tools/list RX frames are exactly 575 bytes (N), 11236 bytes (C), and 2447 bytes (S), each per session. These are serialized wire response sizes, not model tokens. Across the run there are 134 public ID-bearing requests (80 tools plus 54 handshake/list), 27 public notifications; internal product and worker requests remain separate. Thirty-three model-catalogue refresh timeout messages, 54 fallback-model-metadata warnings, and 27 unsupported PowerShell snapshot diagnostics were retained. They are not silently deducted from wall time or labelled provider retries. Requested model/effort settings are fixed; exact backend resolution is not demonstrated by these warnings. Non-error partial relation responses on open T3 meshes retain valid surface facts and are separate from the 10 failed calls. The historical preparation window is 3018.7268128 s (coding/review/waits and failed probes), shown separately. It is not this formal model batch and its intended /27 amortization cannot establish total project net benefit. Earlier analysis, later V2 preparation/review/sealing and coordinator model costs remain unknown.

All final cells retain original 570-second worker deadlines and 450-second consumer budgets; this is not a claim of a universal 570-second process kill timer. Actual owner tool work and worker code-call budgets are checked. Public MCP handshake/catalogue/tool TX/RX bytes and internal product RPC bytes are separately aggregated in JSON. Native script/stdout archival sizes are not TCP wire sizes. No output or cached token is double counted.

The JSON contains per-cell raw timestamp references, all 80 attempts, frame-level byte counts, per-task and per-arm sums/medians/ranges, source SHA256 bindings, anomalies, first-sufficient-fact timing and the independent recomputation script is `recompute_costs.py`. Results are descriptive for 3 samples per task/arm.

34/34 real tool requests passed on `081252633cdf49b5b35c4dfa33845c7d05438870` (133-source SHA `d5f3f7d29c201c21611014f0c963afd8c6b5f6fb501b0d94e60f79890d006936`).

The offline audit passed 247 checks. Shared: 21 tools; default owned ordinary: 11; default owned narrow: 2. All five stdio sessions exited 0. The shared fixture server was explicitly terminated and waited, returning 1. Owned worker PIDs 31840/19704 and the scoped fixture command line are absent in `process_check_02.json`. The shared fixture PID was not recorded.

The 14 repeated/return requests had zero normalization, MeshEntity.from_dict, task solver, geometry kernel and ranking calls, with zero additional resident to_mesh/triangulation/resource builds/world maps and zero decoder world maps. Each still performed a real capture request and decoder application. AB→AD built one new resource; returning to either selection reused both layers. Metadata color advanced revision with zero geometry work; pose remapped one object without to_mesh; the vertex edit rebuilt one resource and remapped one object. Scene and file load advanced epoch 1→2→3. Frame/units advanced revision, despite the historical record labels ending in `_epoch`.

Shared execution used the real production launcher in narrow and ordinary modes. Owned execution composed the default BlenderProcessHost, LiveSpatialService and stdio API, keeping the verified default worker expression and adding a validation-only observer before it. A real transform returned verified; following task/nearest reads kept the action ledger byte-identical. The initial shared opaque ledger also remained byte-identical. Model tool results contained no internal capture token, resource references or delta payloads.

Independent direct Blender RNA world-coordinate oracles agreed on all 33 reads; maximum absolute distance error was 9.31322574615e-09 m. This oracle is exact for the generated plain fixture faces and the edited bottom corner. Both generated blend files stayed byte-identical at SHA `f8ac76c8f525aab3a2c5282a6d23bac62eb313027f4c1666732b190735b53589`; no user asset was opened. Product source manifests were checked before and after, byte-for-byte equal.

Representative observed costs (one sequence, including observer overhead):

| Request | Full stdio RTT ms | Stdio TX/RX B | MCP or owned TX/RX B |
|---|---:|---:|---:|
| shared_cold_AB | 120.890 | 193/3447 | 58555/4258 |
| shared_repeat_AB | 6.740 | 193/3447 | 1393/2621 |
| shared_switch_AD | 170.960 | 190/3468 | 1390/3424 |
| shared_return_AB | 6.644 | 193/3447 | 1421/2643 |
| shared_metadata_color | 90.746 | 193/3447 | 1421/2639 |
| shared_pose | 90.731 | 194/3450 | 1421/2639 |
| shared_geometry | 78.009 | 194/3450 | 1421/3465 |
| ordinary_nearest_cold | 70.097 | 221/1479 | 1470/11426 |
| ordinary_nearest_repeat | 6.814 | 221/1479 | 1470/11426 |
| owned_task_cold | 99.418 | 313/3760 | 123/3897 |
| owned_task_repeat | 8.381 | 313/3760 | 237/2284 |
| owned_return_AB | 12.329 | 313/3760 | 259/2304 |
| owned_real_transform | 290.924 | 341/96911 | 1400/39073 |
| owned_task_after_transform | 93.912 | 314/3763 | 415/2445 |
| owned_nearest_after_transform_repeat | 9.381 | 222/1480 | 482/10903 |
| owned_narrow_repeat | 8.404 | 193/3447 | 237/2284 |

Tool-only bytes and whole-session bytes are distinct domains. Whole sessions include initialize/tools-list, plus owned capabilities, shutdown and Blender stdout banners. Socket and pipe data are copied as actual bytes; owned pipe copies occur below UTF-8 decoding and universal newline conversion. These nested stdio and host byte counts must not be added as a single payload cost.

| Session | Tools | Tool stdio TX/RX B | Whole stdio TX/RX B | Tool host TX/RX B | Whole host TX/RX B |
|---|---:|---:|---:|---:|---:|
| shared_narrow | 12 | 2319/41481 | 2551/44899 | 74152/34945 | 74152/34945 |
| shared_reconnect | 4 | 772/13871 | 1004/17289 | 62734/15505 | 62734/15505 |
| shared_ordinary | 5 | 1381/14238 | 1613/37240 | 64281/32355 | 64281/32355 |
| owned_ordinary | 11 | 3104/125414 | 3336/148416 | 4699/98851 | 4790/100819 |
| owned_narrow | 2 | 386/6894 | 618/10312 | 360/6181 | 450/8148 |

The runner-measured sequence took 8.607 seconds. The historical `complete_command_ms` field includes Blender/server startup, controls, tool calls and cleanup, but excludes orchestrator Python startup/imports, argument/output setup and final result-file publication. Per-tool full RTT runs from before stdin write through receiving the complete stdout line; child dispatch/content timing excludes final JSON encoding and stdout publication. Python profiling, byte copies/appends, metrics and independent worker RNA snapshots add unquantified overhead, which is included and not subtracted. This is a correctness and work-reuse observation, not a benchmark or performance target claim.

The actual residency counters are retained for every tool. The optional C-call probe did not receive Blender RNA to_mesh events (cold residency reported 2 extractions while C-call events were empty), so it failed calibration. Full capture work inside the owned action, including to_mesh, triangulation and world mapping, remains **unknown**. Resident action counts are narrower and must not be presented as total host work. No zero-work conclusion came from an empty delta resource list.

Raw stdin/stdout, socket/owned pipes, observer events, startup source identity, tool metrics, controls, native snapshots and exact executing harness source snapshots are retained under `actual_run_01/`. The earlier fake-RNA failed run and corrected run remain untouched. The first offline inspector used the owned response prefix for shared MCP and failed an assertion; its exact source and `actual_inspect_01.log` are retained. Correcting that parser constant produced the 247 passing checks in `actual_inspect_02.log`. No real retry was needed.

Artifacts: `actual_run_01/RESULTS.json`, `actual_run_01/SUMMARY.json`, `actual_run_01.log`, `actual_run_01/process_check_02.json`.

The offline inspector initially asserted an incorrect MCP response prefix; its failed source snapshot and `actual_inspect_01.log` are retained. Using the existing wire prefix passes all 247 audit checks in `actual_inspect_02.log`, without any new product or Blender execution. These inspector checks/attempts are separate from actual tool requests and unittest methods.

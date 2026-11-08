# CONSUMPTION-RUN-003 actual delivery

One authorized invocation completed all **8 frozen slots**, received and saved **8 public final answers**, and recorded **8 valid_completion=true** results. No quality score is assigned here. Valid completion is the runner's terminal/deadline/budget/cleanup check; it does not establish answer correctness or engine benefit.

The root-provided five-file activation package was copied byte-for-byte. Its accepted cleanup behavior and the user's two scoped tool approvals were used unchanged. There was no extra qualification consumer, operator retry, replay, replacement answer, inline repair, or old-run resumption. No truth, auth/key data, hidden reasoning or global private log was read. Google/paid API access remained paused.

## Eight-slot record

| Slot | Task | Arm | Frozen status | Final received s | Whole cell s | Tool attempts | Execute RPC | Input/cached/output tokens |
|---|---|---|---|---:|---:|---:|---:|---:|
| 1 | T01 | N | completed | 95.0338480 | 101.4114244 | 3 | 3 | 93250/78592/1532 |
| 2 | T01 | P | completed | 102.0917308 | 106.5005315 | 5 | 3 | 109082/92288/1230 |
| 3 | T02 | P | completed | 132.0593543 | 140.6888768 | 5 | 3 | 219627/162816/1939 |
| 4 | T02 | N | completed | 148.7092623 | 156.0313930 | 3 | 3 | 117531/102656/2824 |
| 5 | T03 | N | completed | 58.7209187 | 68.0690161 | 2 | 2 | 64144/49792/891 |
| 6 | T03 | P | completed | 105.0890825 | 112.0176633 | 4 | 3 | 127866/111104/1830 |
| 7 | T04 | P | completed | 83.4840441 | 86.9907070 | 4 | 2 | 91623/76416/1111 |
| 8 | T04 | N | completed | 59.4470359 | 65.9068784 | 2 | 2 | 62239/48128/1027 |

All original safe_to_continue and native cleanup checks are true. The original 180-second answer deadlines and budgets were retained; no deadline timer fired. The final-receive and whole-cell observations are nested intervals and must not be added or interpreted as quality-certified completion times.

## Calls, public errors and byte boundaries

- Eight fresh CLI contexts and eight private native sessions were used. Public tool starts and admitted server actions both total **28**: native.execute_blender_code **15**, P-only human_eye_scene_observe **13**.
- Public tool completion states: **21 completed, 7 failed**. All seven failures are HE argument-validation errors that reached the bridge; exact public errors remain in COUNTS_AUDIT and original events. They are not hidden, retried by the operator, or converted into successes. Parameter failures did not execute a native RPC. No client approval rejection was observed in these tool events.
- Physical RPCs: **29** = native execute **15** + HE-owned socket execute **6** + administrative close **8**. The execute ledger counts **21**; close is outside that ledger. Responses: **21 success, 8 closed**. Counts at these layers are intentionally distinct.
- MCP frames: **64** = 12 initialize + 12 notifications/initialized + 12 tools/list + 28 tools/call. MCP TX **43,457 B**, generated/published RX **311,969 B**. Physical RPC TX **33,490 B**, RX **232,217 B**. Each is its own wire boundary, not an extra model-token total.
- Native complete tools array is **563 B**, native descriptor **561 B**. Each HE complete server catalogue is **17,808 B** (four descriptors); the configured eligible observe descriptor is **8,767 B**. Complete catalogue arrays across eight native and four HE lists total **75,736 B**. The host filters tools; actual model-delivered schema bytes remain **null/unexposed**. Full catalogue bytes must not be substituted for effective model context.
- Public text ledger totals **300,059 B**. Logical final text totals **3,422 UTF-8 B**; saved final artifacts total **3,486 B**, with Windows CRLF expansion recorded per answer. Neither is substituted for provider tokens.
- Generated/published MCP images, image-ledger blocks, private PNG files and render events are all **0**. Observed image payload bytes are zero; no image construction/delivery duration is inferred.

## Usage and complete invocation cost

Each fresh context's terminal usage is counted once: input **885,362**, cached input **721,792** (a subset of input), output **12,384**. Provider request count and fees are **null**; actual backend is **unexposed**. Configured model/provider/effort/tier remain gpt-6.1-sol / openai_http / ultra / default with the existing Pro login. No monetary estimate or backend identity is inferred from these settings.

The full argv and owned controller identity are preserved in STARTED/OWNED_PROCESS/RESULT. Outer start **2026-11-08T05:28:54.939909+00:00**, end **2026-11-08T05:42:53.091562+00:00**; Popen/wait/reap wall **838.1542974 s**. Runner wall through result construction is **838.0286539 s**. Per-cell startup, tool receive, final receive, process exit and cleanup timestamps remain in COUNTS_AUDIT. Nested times are not summed. The outer controller's stdout/stderr are both empty; consumer stderr totals **12,060 B**, with the frozen allowlist's retention/redaction metadata preserved. Unavailable diagnostics are not recovered through private logs or new trials.

MANAGEMENT_START and MANAGEMENT_CLOCK separately record this chat turn's start, preparation before controller dispatch, and elapsed lower bound through sealing. That management interval includes the nested real invocation and parallel audits; final commit/callback tail and earlier preparation turns remain outside its cutoff. It is not reported as engine time.

## Resource and evidence closure

Controller PID **29000**, eight CLI processes and eight Native workers have owner wait/reap receipts with exit 0. All eight native close responses are closed, poison=false, with unchanged original deadlines, fingerprints and protected bytes. Registered bridge OS-stop evidence is separate from optional graceful EXIT content, and HE children are checked independently. All 12 bridge EXIT and four HE_CHILD_EXIT files are absent; their original process_stopped=true observations are retained without fabricating normal_exit, child owner reap or exit0. CLEANUP_AUDIT records a later read-only SYNCHRONIZE/zero-timeout observation of exactly 33 registered PIDs: 33 stopped, 0 live, 0 unknown. No signal or arbitrary scan occurred. Frozen checks are not rewritten by that later observation. The arbitrary-descendant/PID-reuse limitation remains.

Independent read-only COUNTS_AUDIT and CLEANUP_AUDIT accompany SOURCE_AUDIT. The count audit rehashed **407 original actual files** unchanged. The source audit confirms five exact activation copies, 17 runtime components, 131 product source entries, four original assets and the native helper. Product remains commit **17db41c481397965a9bae3f4571c59a5a80939c9**, canonical source SHA256 **01c296b5dac9c8733670b7b82886fe774fb6e50222d1b935d6ac27efa04760de**.

Baseline HEAD **493faf5f3574c0d6c288c684a056ab5bcc41f49e**; PLAN SHA256 **a6f98fdeb672c2d536f7a98e8e5916d83e1be33e729cad7ef26e74cebe91b65f**; approval SHA256 **6deb0f3750f1a056b5ba8a463d452f0a28862c0d171e5f14d04948cf6d2bc9f8**. PRECHECK and snapshots preserve authorization. The root owns STATE/window release; this task did not write STATE.

NEUTRAL_RAW.zip preserves this run's entire private neutral root, with member lengths/hashes in NEUTRAL_RAW_INDEX. No originals were deleted or moved. PRESERVATION pins the frozen RUN-003 outputs and prior tracked originals. RUN-001 remains 1 error + 7 not_run / 0 finals; RUN-002 remains 1 error + 7 not_run / 1 final / 0 valid completions. Old false flags are not changed.

EVIDENCE_INDEX hashes all new RUN-003 files except itself and Python bytecode/cache. The delivery callback supplies the final commit and report/index hashes after Git-blob verification. The root will independently score answers before analyzing comparative cost or engine benefit.

# 039 Windows scheduling evidence gate

The gate did not pass under the current token. No tiny compute workload, formal timing, Blender process, or product execution was started. No interval or physical-core overlap result is available.

The original receipt and decoder outputs are retained locally. See the public [trace summary](RESULTS.json).

| Actual attempt | Outcome |
| --- | --- |
| Custom WPR profile, own explicit instance `HumanEye039SchedulingPreflightWPR` | `0x80070005`, access denied |
| Raw `StartTraceW`, own named system logger, QPC clock, process/thread/context-switch flags `0x13` | Win32 `5`, access denied |
| Ordinary own ETW file session | Started successfully |
| Enable actual `SystemSchedulerProvider` on that own ordinary session | Win32 `5`, access denied |

The session ran with a medium-integrity token without system profiling rights. No permission or token changes were made. [SystemTraceProvider configuration](https://learn.microsoft.com/en-us/windows/win32/etw/configuring-and-starting-a-systemtraceprovider-session).

Native `GetLogicalProcessorInformationEx(RelationProcessorCore)` returned six physical cores with logical sibling pairs `(0,1)`, `(2,3)`, `(4,5)`, `(6,7)`, `(8,9)`, `(10,11)`, all in processor group zero. The raw 288-byte topology buffer is preserved. QPC frequency is 10 MHz, and the interpreter's monotonic performance clock uses QPC. This topology establishes a mapping; it provides no evidence that two workers actually ran concurrently. [Native topology API](https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/nf-sysinfoapi-getlogicalprocessorinformationex).

The ordinary session's ETL contains two trace metadata events, zero context-switch events, and reports zero lost events. That zero applies to the empty metadata trace and cannot establish lossless scheduling capture. `tracerpt` also reports a schema warning, preserved alongside the XML and summary. Per-task native TID/run boundaries, original scheduler QPC events, physical-core overlap union, and longest continuous overlap remain unavailable.

Only owned session names were controlled. The original ordinary-session `STOP` returned `ERROR_MORE_DATA=234`; Microsoft explicitly documents that a session is already stopped when this occurs during `STOP`. Independent final `ControlTraceW(QUERY)` calls return `ERROR_WMI_INSTANCE_NOT_FOUND=4201` for both owned raw session names. Exact-name `logman` queries also report that the collector does not exist. Before/after entire session listings are byte-identical. The first finalization incorrectly assumed a narrow `logman` HRESULT and is preserved as `FINALIZE_001.json`; the final receipt uses the independent native query instead. [ControlTraceW](https://learn.microsoft.com/en-us/windows/win32/api/evntrace/nf-evntrace-controltracew).

Accessible alternatives do not supply the required interval history. `GetCurrentProcessorNumber` identifies only the processor at the call; `PERFORMANCE_DATA` supplies cumulative context-switch counts and cycle totals; `QueryThreadCycleTime` supplies cycle totals rather than elapsed intervals. CPU sampling, affinity, and process coexistence therefore cannot fill this evidence gap. No existing trace session was borrowed or consumed. [Current processor](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getcurrentprocessornumber), [Thread profiling data](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-performance_data), [Thread cycle count](https://learn.microsoft.com/en-us/windows/win32/api/realtimeapiset/nf-realtimeapiset-querythreadcycletime).

The preserved first source is the code that actually attempted collection. The final source additionally restores the allocated control-buffer size, recognizes documented `STOP=234`, refuses a blocked classification on unexpected collection success, and permits a new output directory. It has not started another session.

The current evidence supports `not_passed_permission_block`. It does not support a physical dual-core qualification, and later tracking cannot be used to replace missing evidence for an already measured formal round.

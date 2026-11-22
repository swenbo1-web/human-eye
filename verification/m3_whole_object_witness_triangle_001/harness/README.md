# Whole-object witness triangle production replay

Canonical entry:

```
python -I -B -X utf8 verification/m3_whole_object_witness_triangle_001/harness/run.py --binding <PRODUCT_RUN_BINDING.json> --mode standard|evidence --output D:/he_m3_whole_object_witness_triangle_001/<fresh-arm>
```

Optional `--case P1|P2|P3` selects one fixed original. Each case gets a fresh
held process and sends original product request #2 twice, cold then hot. The
original JSON-RPC id and every argument value remain unchanged. Evidence mode
forwards the actual `--region-task-evidence` production option; standard omits
it. The candidate binding is the parent-owned new `install/PRODUCT_RUN_BINDING`.

Input identity is the fixed 4268e19f archive. Every original file must match its
RAW_INDEX SHA, on-disk member and sealed ZIP bytes. Task capture is the original
native WIRE/003 selected_objects delta in its original A/B order. Its resource
payload is empty: the worker first initializes the normal SceneDeltaDecoder
resource cache from original WIRE/002. That is explicitly replay setup, not an
extra service capture or solver call. Each actual cold/hot capture_task request
then applies the original WIRE/003 through that same normal decoder. The full
21-object capture is never substituted for the ordered two-object task capture.

The runtime uses actual installed production_server.main, construction, live
service, private eligibility keywords, solver, pair/result caches and formatter.
Service.observe forwards all positional/keyword arguments. Only capture RPC
transport is substituted. No producer value or geometry algorithm is replaced,
and no response is rewritten. A passive existing read-context helper records
retained mesh/array identities and result counts around the original service
call. Product events preserve task_work, candidate/work-unit counters, cache
flags and any candidate membership-check counters. Producer, wrapper and wire
timing scopes remain separate and nested.

The original supplementary model tool #4 is product invocation call_003, not
call_004. Its authentic producer and request are pinned as reference evidence.
The original P2 whole-object measurement is still valid even though that
historical overall task failed; the failed task and its archive remain intact.

Output under each arm is `cases/P1|P2|P3`:

- `cold|hot/{REQUEST,RESPONSE,PUBLIC,RECEIPT}.json` and exact `PUBLIC.txt`
- `wire/rpc_XX/{TX.bin,RX.bin,RECEIPT.json}`, raw stdout/stderr and held process
  spawn, start and close receipts
- `worker/INPUTS.json`, original request/response/producer/supplement, and
  resource-prime receipt with all original source pins
- `worker/CAPTURE_01.json` and `CAPTURE_02.json`: actual decoded task captures
- `worker/call_01|02/{SERVICE_RESULT,READ_CONTEXT,RECEIPT}.json`: same original
  returned service value before the installed formatter
- `worker/HOST_CALLS.jsonl`, `PRODUCT_EVENTS.jsonl`, audit, `EOF.json`, and
  `WORKER_EXIT.json`
- `HELD_EOF.json` and `CASE.json`; arm `INDEX.json`, source hashes and snapshots

Close requires actual stdin/stdout EOF, production return 0, installed source
verification, matching PID, host close and the original held-process/pipe/handle
receipt. Network, PNG access and writes into the old evidence tree are blocked;
their attempts are retained as counters. No model, Blender or raster is started.

Both baseline modes passed the three fixed cold/hot cases. Cold work reports
one surface pair; hot work reports zero surface pairs and result_cache_hit=true.
The three current standard bodies have the original byte counts and equal
values after removing only dynamic trace_id. This preparation does not assert
candidate correctness, source-triangle ownership or cross-version byte equality:
the independent root-owned packet and compatibility gates decide those after
the isolated candidate is installed. Source/runtime/schema and cost limitations
are preserved rather than inferring hidden measurements.

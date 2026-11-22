# Rounded-witness production replay

Canonical command uses the direct primary Python, never the Windows venv stub:

```
C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe -I -B -X utf8 verification/m3_whole_object_rounded_witness_001/harness/run.py --binding <PRODUCT_RUN_BINDING.json> --mode standard|evidence --output D:/he_m3_whole_object_rounded_witness_001/<fresh-arm>
```

The worker command also hard-binds this direct executable so its retained Popen
PID is the actual stdout/EOF writer. Each fresh arm runs seven independent
cases, cold then same-generation hot, with original argument values and IDs:

1. linear_m01_m03 and linear_m03_m01
2. linear_m16_m20 and linear_m20_m16
3. tree_n02_n03 (the plan's forward-only BVH holdout)
4. success_m16_m19 and success_m16_m14 (original successful forward controls)

The linear/tree families use authenticated actual complete native captures,
cross-checked against both closed terminal sources by checks/fixtures.py. Only
selected-scope metadata is derived for the ordered task pair; the original
world vertices, face row order, document and instance versions remain. The
normal current SceneDeltaDecoder accepts the resulting complete selected
capture. DERIVED_SELECTED_SOURCE records this provenance and never describes
it as a new live capture. The source helper is loaded only after the current
installed verified-source bootstrap and does not load historical product code.

The success controls preserve the previous actual B1 #1 and #2 request, response,
producer, generation and selected capture. M16/M19 uses original native WIRE002
with its two resources. M16/M14 primes only WIRE002's original resource state
in replay setup, then uses WIRE003 on each real capture_task request. This keeps
the old successful packet binding and field order comparable instead of using
a different document's derived scope.

The production launcher, service, private eligibility keywords, solver, pair
and result caches and public formatter run normally. No producer is replaced,
no triangle is scanned by the harness to make an answer, and no geometry
algorithm is monkeypatched. Original task queries explicitly request no image,
one surface_proximity fact, two ordered whole objects and full detail. Standard
omits the existing option; evidence passes --region-task-evidence. Only capture
transport is replaced. Optional fields are not manufactured or postprocessed.

Artifacts retain the accepted layout:

- arm INDEX.json, SOURCE.json and exact runtime source snapshots
- cases/<label>/cold|hot/{REQUEST,RESPONSE,PUBLIC,RECEIPT}.json, PUBLIC.txt
- wire/rpc_XX/{TX.bin,RX.bin,RECEIPT.json}, raw stdout/stderr and spawn/start/close
- worker/INPUTS.json, source pins, original successful artifacts where available
- worker/CAPTURE_01.json, CAPTURE_02.json, call_01|02/SERVICE_RESULT.json,
  READ_CONTEXT.json and service RECEIPT.json
- worker/HOST_CALLS.jsonl, PRODUCT_EVENTS.jsonl, raw audit, RESOURCE_PRIME.json,
  DERIVED_SELECTED_SOURCE.json where applicable, EOF.json, WORKER_EXIT.json
- HELD_EOF.json and CASE.json, including original PID and closed OS handle

PRODUCT_EVENTS preserves original request/service spans and task_work. When
the candidate emits rounded_source_membership, exact_source_membership and
exact_source_encode spans, those original boundaries are retained. Service,
wrapper and wire clocks are nested and must not be added together. No absence
of a clock is replaced with an inferred exact-path timing.

Baseline evidence and standard preflights each passed all seven cold/hot cases.
The four linear directions and tree holdout lack old source fields, while the
two successful controls retain source_triangles at 1,925/1,961 bytes. The tree
reproduces 99 visited nodes. Each cold call solves once; each hot call reports
result_cache_hit=true with zero new surface pair. Original capture sources
remain unchanged; no PNG access, renderer, Blender or model is used. The
independent parent-owned source/packet gate judges the new exact certificate,
numeric identity, compatibility and budgets after the single candidate install.

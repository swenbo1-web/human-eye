# COMPLEX-REENTRY-001 static public support map

Current public `task` has a real solid-relation path. This is source/archived-snapshot analysis, not a product execution or runtime capability result. No product source, asset or old evidence was changed.

## First minimal legal public request

```json
{
  "session_id": "complex-initial-01-03",
  "include_image": false,
  "query": {
    "mode": "task",
    "objects": [
      {
        "name": "Object_01"
      },
      {
        "name": "Object_03"
      }
    ],
    "requested_facts": [
      "solid_relation"
    ]
  }
}
```

`task_query.py:49-67` requires only mode/objects/requested_facts and exactly two ordered selectors for pair facts. `live_service.py:1031-1035` requires include_image=false and no top-level focal_id/reference_id/goal/scene_delta. Requesting only solid_relation sets need_clearance=false, need_witness=false, need_relation_evidence=true (`task_query.py:361-367`); it does not unnecessarily compute surface gap or witness first.

## Original-task requirement mapping

| Requirement | Existing public facts/path | Support and limits |
|---|---|---|
| per-candidate solid relation | task solid_relation; pair_relation for three-way separated/touching/penetrating | Public path exists. solid_relation is tolerance-based penetrating/not_penetrating, not all three categories. Pair_relation uses zero-tolerance signed-clearance and evidence, but shares strict solid support. |
| minimum surface gap of separated pieces | task surface_clearance or pair_relation; surface_proximity is independent unsigned face-distance quantity | Strict surface_clearance depends on supported solid classification. surface_proximity does not establish interior overlap; distance zero cannot replace solid relation. |
| all three candidates/all penetrating pieces/nearest separated piece | Three ordered target/candidate task requests and external finite aggregation of complete facts | Pair facts require exactly two selectors. selected_count=2/candidate_count=4 is directory binding, not full all-three relation coverage. surface_nearest cannot select nearest separated solid by itself. |
| currentness/unchanged/changed | fresh selected capture + validated scene revision/fingerprint/source + runtime identity; exact pair cache | Each observe captures again. Pair cache key covers algorithm, all evaluator parameters and both current meshes; failed/unknown measurements are not memoized. Actual process/cache reuse must be observed, not inferred from static availability. |
| rotation/AABB limitation | aabb/axis_gap finite observations plus mesh-based relation/distance | axis_gap is unsigned world-AABB interval gap, not surface distance or solid classification. Four inner-wall changes can preserve outer AABB while mesh coordinates/fingerprint change. |
| penetration evidence, without global minimum exit vector | solid_relation evidence or pair_relation evidence when supported | Original task does not require global minimum separating translation. Existing separating-translation scope must not be used as a new acceptance burden. |

## Entity-classification path and expected domain limit

`live_spatial_mcp.py:646` calls `LiveSpatialService.observe`; the task route enters `_observe_task` at `live_service.py:1287`. It checks read-only loaded source identity, makes a fresh selected host capture, validates it, and calls `task_result`. The current host binds explicit names against scene.objects before expanding only the selected meshes (`blender_host.py:575-605`, `:1109-1120`). Result bindings carry selected scope/directory count, object IDs/names, current scene revision/fingerprint/source, and runtime source hash.

`task_query.py:361-375` invokes `geometry_safety.measure_pair_geometry`. That function first applies the existing work budget, then certified convex-shell SAT, then the existing exact world-axis orthogonal-cell fallback (`geometry_safety.py:402-412`). `_convex_shells` explicitly accepts certified convex connected shells or disconnected convex components and rejects a connected concave shell (`submodule_1_4_spatial_sniffer.py:359-434`, concavity test at419). The thick annulus cannot be silently replaced with its convex hull.

The orthogonal fallback is not general rotated-concave support. `orthogonal_solid.py:24` caps coordinate planes at16/axis. `:214-215` checks that cap before face clipping; `:225-227` also requires each face to have exactly one constant world axis. Static reads of the original hash-fixed snapshots show Object_01 has48 vertices/96 faces,48 different represented world coordinates on each of x/y/z, and its first face has no constant world axis in both initial and changed states. Therefore the archived shape is outside this fallback. This is a predicate/domain observation, not a new geometry oracle or an executed product result. Actual source/object/geometry binding must still be confirmed by the real public probe.

If that binding matches, the expected public fact is `solid_relation: {status:unknown,value:null,reason:unsupported_solid_geometry}`. The fallback's coordinate-plane cause is not directly projected into the public fact by task_result; retain any natural internal receipt and otherwise distinguish static predicate evidence from an instrumented internal return.

## Stop rule and status interpretation

Unknown fact does not necessarily mean transport failure: task_result publishes top-level `status=partial` (`task_query.py:406-420`), and the MCP wrapper accepts partial with `isError=false` (`live_spatial_mcp.py:658`). Check the fact status/reason and its source/object/current geometry binding. A correctly bound unsupported/unknown necessary solid fact ends this runtime batch. Do not perform the other eight possible observations or changed-state patch merely to repeat the refusal. Parameter, transport, identity and geometry-binding failures are errors; they do not establish this capability gap.

`surface_proximity` uses the separate unsigned closed-face distance path, and surface distance zero cannot distinguish touching from penetrating or containment. `surface_nearest` is not a replacement for all three solid classifications and nearest *separated* piece. If supported, the original three candidate facts must all be obtained and aggregated; no missing candidate may be silently called clear.

Every task call captures current selected geometry. The pair cache uses algorithm/options/source/unit/tolerance and both complete current meshes (`scene_cache.py:394-421`); only measurement_valid results are memoized, unknown is not. Static code availability does not prove actual cache/process continuity or speed. The four inner-wall changes need current geometry evidence even though outer AABBs remain unchanged.

No global minimum exit vector is required by the original question. If bound runtime unknown confirms the limit, the only suggested next design is the original-task read-only relation support for this connected non-orthogonal concave solid class, to be reviewed by root. Do not implement a new classifier, new action/write domain, or penetration-depth solver in this batch.

Original task JSON SHA921298e2da3275812d7a7a64befa42ce91aa95022192534927c4a373423e4f7e and snapshot SHA5a089d22faad7c90b9a28c6ea408ea8b73e8b939e47a3cb66a193ba85f23fc14 were checked. Matrix JSON records all source hashes and exact coordinate-count metadata. Added runtime product/kernel/test/Blender/RPC/model-consumer calls: zero. Final verification-script elapsed is partial bookkeeping, not full reviewer cost; child tokens/fees are unmeasured.

# Selected geometry simplification review

The reviewed candidate changes only `task_query.py`, `live_service.py` and `live_spatial_mcp.py`. Its file hashes remain `def312ae4b67192e4a3e71feb80fa5122c08fd8a5c2853406c8de4f692df5fd8`, `aa77974ebfb4d5797db064af35b4e7ed4d54399e2f923746f531c66660adf191` and `b52f6468e6b71eb10b065a89b3417c1ee025e464b9be84d32b0b5625cd1b6275`, respectively. This review reads source only. Directed tests and actual-entry measurements are pending their authorized runners.

## Chosen decision

Keep the single projection helper and reuse `result.binding.objects`. It already contains the original validated task bindings, including unresolved selectors. This removes the need for another call to `bind_objects`, another selected-scene projection, or a new per-request geometry cache. The helper converts only explicitly requested objects and fields.

Repeated geometry selectors intentionally retain their requested order and multiplicity within the frozen limit of four. Each successful row gets newly converted arrays. Adding an ID-based array memo would introduce shared mutable output or additional copying rules for a bounded request. The present candidate provides no measured evidence that such a layer would improve this task, so this review selects no additional product edit.

The repeated `query_fields - {'geometry'}` expressions are small structural checks. They could be written once, but the current change preserves the existing task branches clearly and has no default-path performance result yet. Changing this during active QA would create another candidate without evidence of a material benefit. The current bytes remain fixed.

## Cache and generation audit

`live_service._observe_task` removes geometry before the existing ReadContext query key is computed. Capture still receives only the original relation `query.objects`, and `context.activate` uses that same ordered selection. Geometry aliases, request order, repetitions and `include_triangles` therefore do not alter the captured selection or relation-result key.

`ReadContext.result` returns `copy.deepcopy` on both misses and hits. The helper attaches geometry to this detached result while the observation lock is held, after relation-result retention and before `_bind_read_result`. Its arrays come from `mesh.vertices.tolist()` and optional `mesh.faces.tolist()`. Its selector and contract dictionaries are newly constructed. The relation cache receives no geometry attachment, and caller mutation has no source-array or cached-result reference through these new fields.

Existing generation activation, normalization and result invalidation retain their original implementation. Geometry comes from the same current normalized `meshes` as the relationship result. Existing scene revision, fingerprint, runtime source, host identity, unit and coordinate frame bind the attachment. No new snapshot token or saved response hash is introduced.

## Selector and unknown audit

Exact original unresolved selectors are checked before aliases and retain their original reason. This preserves an ambiguous original name even when a separately successful ID happens to have that name. Successful original rows are deduplicated by object ID only when checking alias uniqueness. Two distinct IDs with the same name continue to produce an `object_name_ambiguous` row. Explicit geometry repetitions remain repeated output rows.

Matching uses the selector's declared key and literal value. It does not reinterpret a name as an ID, trim or case-normalize names, pick the first ambiguous object, or search outside the original task bindings. An unmatched geometry selector raises the frozen out-of-set error. A successful geometry row does not change an unknown relationship, duplicate-candidate reason, same-object pair reason, summary or nearest result.

## Default path and branch scope

Geometry normalization is confined to the existing task-set shapes. Legacy task pair/AABB shapes and nearest retain their runtime rejection of this field. The existing compact relation tool maps the new option into that task normalizer, and compact output preserves the single attachment. The ordinary task-set schema exposes the same accepted query field so the existing bridge stays consistent with runtime validation.

Without geometry, the service skips the projection helper, alias lookup, geometry array conversion and new contract construction. The new option does add small parameter-presence and query-shape checks. Actual default-path elapsed time still requires the frozen measurements.

Vertices are already validated world-metre values in captured order. Triangles are the same normalized captured triplets indexing those vertices. The projection applies no matrix or unit conversion, triangulation, mesh evaluation or relation solver. Triangle conversion and its indexing description occur only when requested. A checkpoint runs before each requested object and after projection.

## Diagnostic interpretation

Existing `task_work` counts relation kernels and relation-result hits. This candidate does not add a new geometry-work telemetry counter. Consequently, a warm geometry response may correctly report `result_cache_hit=true` and `engine_invoked=false` while still performing the requested list conversion and serialization. Those fields cannot establish zero total CPU or allocation cost.

The frozen QA instrumentation and saved responses must establish actual capture, mesh evaluation, triangulation, world preparation, kernel and output counts. Invalid out-of-set selection can be detected after the relation result has been obtained, so its real acquisition and computation costs must also be preserved. This source review does not substitute for those measurements.

## Result

The candidate already makes the substantive simplification by reusing the validated result binding and existing detached cache result. Retain the current three-file implementation for directed validation. This review adds no product edit, helper layer, cache, acquisition path or new measurement run.

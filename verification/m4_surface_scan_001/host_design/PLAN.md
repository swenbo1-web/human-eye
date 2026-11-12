# Surface scan host acquisition

The host changes cover `blender_host.py`, `blender_mcp_host.py`, `blender_process.py` and `blender_worker.py`. The resident metadata helper may need a small source-qualification cache field. Product edits start after the root confirms the fixed input qualification.

## Capture contract

`capture_surface_scan(threshold_m, deadline_ns, max_response_bytes)` runs in one synchronous host lock and dependency-graph window. Its directory includes all scene mesh objects, including hidden meshes, with a 0..256 object envelope. The source domain remains independent static triangle meshes. Unsupported mesh sources retain their directory identity and generate unknown-source pair dispositions.

The internal packet uses `single-read-surface-scan-v1` and result kind `acquisition_only_not_surface_scan_result`. The `coverage` array contains object IDs, names, conservative bounds, bound status, source status and reason. The `pairs` array contains each unordered directory pair exactly once with canonical IDs, conservative lower bound and disposition. Dispositions are `retained`, `excluded_strict_bound` and `unknown_source`.

The full directory identity remains `complete_scene_meshes`. The captured endpoint union and its identity use `surface_scan_candidates`. Empty directory and empty union are valid. `scope_issues` preserves unsupported evaluated-instance coverage and prevents a complete full-scene claim. Directory and packet binding include the host source, frame, unit scale, document epoch and object incarnations.

Only a strict lower bound greater than the threshold excludes a pair. Unknown bounds keep supported geometry in the union. Source invalidity discovered during local qualification makes every related pair unknown. Bounds retain the existing outward affine L-infinity implementation. Independent input qualification checks actual exported vertices against API-derived bounds.

## Shared acquisition and residency

Extract the nearest acquisition's static directory inspection and observable-source recheck into shared private helpers. The scan performs source checks and bound reads before expanding the union once through the existing resident capture. Local geometry qualification can use resident source metadata and geometry dirtiness. It does not require a new geometric store.

Resident resource and pose reuse and nested capture delta encoding remain the existing mechanisms. Capture scope becomes an internal acquisition argument so both nearest and scan preserve their own scopes, selections and revision bindings. The scan packet cache can use the existing bounded resident acquisition cache with a threshold selection key.

Logical endpoint/capture size and per-request actual work are recorded separately. Current-request statistics include directory work, source qualification, resource construction, local vertices/faces read, world vertices transformed and delta encoding. A warm cached packet retains its logical coverage while reporting current work as zero where reused.

### Source qualification reuse and precision

`SceneResidency.source_checks` retains only the source stamp, status, reason and exact rational geometric summary. Its stamp uses object/data incarnation, geometry dirtiness, geometry guards and document epoch. Pose and name updates preserve local qualification. Reload, undo, deletion, data replacement and geometry dirtiness invalidate it. An existing matching M2 resource supplies immutable local geometry. Otherwise static triangle storage is read once. Local arrays for candidate endpoints are passed privately to resident capture, which constructs its existing resource without a second mesh extraction. Excluded objects retain the small qualification summary alone.

Each local triangle uses exact dyadic coordinates for its cross product. The summary stores the minimum nonzero cross-product infinity norm, maximum triangle edge infinity norm, and maximum absolute local coordinate per axis. A zero local cross product is an explicitly unsupported degenerate source. Finite coordinates alone cannot establish this property.

For the actual linear map `A = scale * matrix[:3,:3]`, the summary certifies a transformed exact cross-product lower bound `abs(det(A)) * min_cross_inf / norm_inf(transpose(A))`. The transformed edge upper bound is `norm_inf(A) * max_edge_inf`. These calculations use exact rational arithmetic, including a zero determinant test. The binary64 forward map uses three products, their ordered accumulation, translation and final scale. Its absolute error bound is propagated per operation using `u = 2**-52` and `eta = 2**-1074`, allowing subnormal error. A finite intermediate bound is required after each operation. If the maximum coordinate error is `delta`, nondegeneracy is certified only when `lower_cross > 8 * delta * edge_upper + 8 * delta**2`. The two edge perturbations have infinity norm at most `2 * delta`, which gives the stated cross-product error bound. Failure to establish the strict inequality produces `world_precision_unresolved`, including actual world-coordinate collapse or overflow cases. Pose checks use this summary and matrix alone, without a full world-vertex traversal.

Hidden scene meshes remain in the default directory. After the complete static-source guard passes, a hidden mesh unavailable as an evaluated object can use its original data and actual matrix, with an explicit `static_original_hidden` source mode. The fallback has the same triangle qualification and precision checks and cannot apply to modifiers, constraints, animation, parenting or instancing. API-derived bounds remain unknown if invalid, even when local qualification succeeds.

## Transport paths

The resident MCP bridge adds the fixed command to its read-only set, request validation, capture delta production and decoder. The process bridge adds the same API and original-deadline cap. The fixed worker dispatches the command, supports the same baseline parameter and checks the original deadline before publishing. The connector's deadline cap starts before request encoding.

## Validation

Directed host checks cover 0/1 objects, no retained pairs, equality of the bound and threshold, invalid bounds, unsupported and degenerate sources, hidden meshes, same-window mutation rejection, document epoch, rename, deletion, resident reuse, full-delta and both command paths. Existing nearest tests verify the shared helpers preserve its caller behavior.

The parent plans and this design were read with an unbound Agent Learning connection, host epoch 5. No task handle was borrowed. This design stage launched zero product, Blender, evaluation-consumer or business API processes.

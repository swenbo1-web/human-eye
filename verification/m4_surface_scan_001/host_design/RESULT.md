# Surface-scan host implementation and checks

Input qualification was frozen at `96fce78b98cb749885792112e039a406744d282b` before product implementation. The frozen input files were not edited. This task owns `blender_host.py`, `blender_mcp_host.py`, `blender_process.py`, `blender_worker.py` and the narrow `scene_residency.py` qualification metadata addition. It did not create a commit or run Blender, a fixed-scene engineering measurement, an evaluation consumer, an image request or a paid API.

## Implemented behavior

- `capture_surface_scan(threshold_m, deadline_ns, max_response_bytes)` reads a 0..256-object mesh directory, including hidden meshes, and partitions every canonical unordered pair in one synchronous main-thread lock window.
- The shared nearest directory helper retains existing nearest behavior. Only the new scan scope permits empty directories, empty endpoint unions and an explicitly qualified hidden static original-data fallback.
- Conservative bounds exclude only with a strict lower bound greater than the threshold. Invalid bounds retain supported geometry. Unsupported source, modifier, malformed triangles, local degeneracy and unproven world precision produce unknown-source pair dispositions.
- Exact dyadic local qualification caches small min-cross, max-edge and local-magnitude summaries. A matching M2 resource is reused. Otherwise local storage is read once, with candidate arrays passed to the existing resident resource path. Previously excluded sources retain the summary alone and are read once if they later enter the endpoint union.
- A rational affine roundoff bound certifies finite nondegenerate world triangles using the actual matrix and unit scale. Pose updates reuse local eligibility. The method reports `world_precision_unresolved` when the strict proof does not succeed.
- Fresh directory metadata, scope issues and full directory identity bind the inner scan revision. Scan-only residency signatures include mesh and non-mesh instancing flags and the evaluated-instance scope flag. Warm packet reuse checks current scope issues and full identity before returning cached data.
- MCP resident transport and the owned process worker dispatch the same fixed command, preserve parent deadlines, validate fixed fields and reuse the existing nested resource delta codec.
- `work` keeps logical union geometry counts separate from current-request `residency_delta` counters for bounds, source qualification, local reads, resource builds and world transformations. A cached packet updates only current counters and adjusts its pre-established document byte count using the small changed work section.

## Tests

The final fresh Python process passed **82 tests** across these modules.

- `verification.test_surface_scan_host`
- `verification.test_m4_capture_001`
- `verification.test_blender_process_residency`
- `verification.test_blender_host_contracts`
- `verification.test_blender_mcp_host`
- `verification.arch_resident_001.test_residency_contract`

`unit_final_82.log` records the final run. Tests include 0/1/256/257 objects, empty unions, equality retention, invalid bounds, invalid and degenerate sources, hidden raw fallback, exact local underflow/overflow cross cases, world precision refusal, no setters, source mutation rejection, warm state reuse, pose/name/geometry/document/deletion invalidation, previously excluded source entry, both bridge paths, worker dispatch and host-to-kernel reduction.

Eight directed warm-scope combinations cover evaluated instance creation, non-mesh `instance_type`, non-mesh `is_instancer` and mesh instancing, each with and without resident handlers. Every combination changes the scan revision and prevents a stale complete packet.

The original nearest fixture lacked real polygon loop fields and stored `None` loops. Its fixture now supplies loop starts/counts and vertex indices, including the changed-index witness case. Another old assertion expected an obsolete generated-code call spelling and now checks the existing `getattr` dispatch. These test-maintenance changes preserve the production nearest contract.

Intermediate logs are retained. The first run had one incorrect newly written deletion assertion caused by a shared list alias and the old generated-code spelling assertion. A later new integration assertion used a zero-argument checkpoint where the reducer supplies stage names. These assertions were corrected. Final unit results provide mock evidence only. Blender API behavior, isolated installation and the fixed five-sequence measurements remain the parent-owned qualification work.

## Cross-review

Host review found warm scope changes could bypass the old residency signature. The scan-specific signature and scope check repair this case. Cross-review also found service result reuse needed complete packet boundary binding because `ReadContext` uses capture-state tokens. The parent was notified and added per-request packet validation and binding/scope selection keys. The host change continues to bind its inner revision independently.

Agent Learning returned an unbound context with host epoch 5. No assignment handle was borrowed.

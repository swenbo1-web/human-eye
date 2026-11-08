# M1-NAME-ID-ENTRY-001

The single candidate moves a legal name-to-ID call to the start of human_eye_scene_observe's description. It uses a generic name selector with requested_facts=["aabb"], identifies the returned binding.objects[0].object_id as the next focal_id when resolved, and immediately gives the existing surface_nearest call shape. identity/object_identity are explicitly not facts. No case names, object IDs, answers or asset structure appear in the candidate.

The description is **1471 → 1453 UTF-8 bytes**, a reduction of **18 bytes**. Required pair_relation/escape, surface_proximity/zero-direction/topology, partial unknowns, source binding/revision/trace, goal criteria, image/expiry, mesh_structure and nearest complete/partial semantics remain. Only this literal changed: replacing it with the old literal makes the entire module AST identical to the baseline; bytes before and after the literal are also unchanged. The full tool descriptor list, including all inputSchema and dynamically appended fields, compares equal after removing only the observe description.

Validation reused existing code and tests. Both generic JSON examples were parsed from the candidate and accepted by the unchanged _validate_arguments entry. Three already-recorded RUN-003 successful aabb tool responses independently confirm a nonempty string at binding.objects[0].object_id: slots 02/03 frame 006 and slot 06 frame 005. Only field presence, type, response status and raw TX/RX hashes were recorded; concrete names, IDs, geometry and final answers were not copied or interpreted.

**6/6 existing methods passed, failures 0, errors 0, skips 0**:

- SurfaceNearestEntryTests.test_01_explicit_mode_schema_and_mode_only_query
- SurfaceNearestEntryTests.test_02_invalid_envelopes_fail_before_any_host_read
- TaskQueryTests.test_name_and_id_have_identical_facts_from_current_capture
- TaskQueryTests.test_query_prevalidation_rejects_ambiguous_shapes_and_unknown_facts
- TaskQueryTests.test_v3_keeps_trace_link_and_audited_work_without_wrapper_construction
- RuntimeIdentityTests.test_source_manifest_hash_is_reproducible_and_includes_identity

These are selected existing tests with fake hosts; no new test cases or description-mirroring test suite was added. Temporary fixtures were directed into this task's own directory. Process, signal and network interfaces were blocked during imports/validators/tests; forbidden calls were 0. No new consumer, Codex CLI, MCP service, Blender, RPC, API or paid API ran. The completed RUN-003 approval was not reused. Real consumer usability, time, token cost and net benefit were not re-tested or claimed.

The existing runtime_identity function generated the new identity through fresh ordinary imports. The source count remains **131** and the sole changed source entry is human_eye_plugin/live_spatial_mcp.py. No identity algorithm, implementation revision, fixed pin or historical summary was edited. This is an ordinary source identity check, not a claim of production verified-loader execution.

- Baseline: c77111f7076b4a1720a98e8c0f8f8af43feb1c34.
- Changed source SHA256: 3a0973c71a7f6525934cd9c8c79ac19e046fc95dee119961daf9620ec3d86d0a.
- New canonical runtime source SHA256: c389562d402f9177feefb9dd77621ed701a88369278c62826036ba641298fca6.
- Historical RUN-003 product identity remains 01c296b5dac9c8733670b7b82886fe774fb6e50222d1b935d6ac27efa04760de in its original evidence.

An independent reviewer inspected the final candidate without executing tests and found no material issue. SOURCE.diff is the minimal source patch; RESULTS.json, SOURCE_IDENTITY.json, EXAMPLES.json and raw check output preserve the actual checks. Historical RUN-001/002/003 result/index marker hashes were checked unchanged. No schema, selectors/FACTS, tools, errors, support domains, source binding, acquisition counts, geometry, algorithms, permissions or other product modules changed. Root review of this one candidate is the next gate; no new trial was started.

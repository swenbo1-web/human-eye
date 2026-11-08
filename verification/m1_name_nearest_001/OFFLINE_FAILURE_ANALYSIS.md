# Preserved offline attempt and correction

offline_01 ran 23 directed methods: ENTRY 19 (one failure, one error), CAPTURE_SOURCE_BUDGET 2 (one failure, one error), SOURCE_VALIDATION 2 passed. All logs, exact executed bytes and execution identity remain in that original directory. It started no Blender session or physical RPC.

The duplicate-name test changed both name and name_full, so the unchanged logical object_id algorithm also produced duplicate IDs. Its subsequent explicit-ID success expectation was invalid. The corrected fixture varies the exact-name field while preserving distinct name_full-derived IDs.

The replacement test assumed a different instance UID would change a name-derived logical ID. The corrected test preserves that ID, verifies current host_identity.object_instances changes from UID 101 to 909, keeps the same document epoch, and moves the replacement to x=0.5 so current nearest distance changes from 2 to 1.5. Both name and old logical ID must read the replacement geometry. A later rename changes name_full and its logical ID. No product ID algorithm or cache rule was changed to satisfy the test.

The two legacy M4 fixture methods used triangle doubles without the loop_start/loop_total/vertex_index RNA metadata required by the already accepted validator. The parent reuses existing bound_source_fix_001.enrich_data, which fills only missing fields and preserves explicit invalid fields. No product validator was weakened.

offline_02 reran the same 23 directed methods after those test/fixture corrections: all passed, zero failures/errors/skips. Both runs used the same 131-source product identity 74263d8b18aec48fac21e3c3b25e26c890739c6b697503a9f6b91acf7c30c0e3. The original production candidate was not modified between attempts. Real QA had not started during either attempt.

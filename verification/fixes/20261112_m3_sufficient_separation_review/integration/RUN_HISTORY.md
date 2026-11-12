# Independent harness execution history

1. `review_integration.py`, exit 1, before engine load: line 18 canonical identity assertion. Harness incorrectly hashed the manifest list alone (`54f819e0...30366`), omitting base_version and implementation_revision. Corrected harness to match documented runtime identity canonical input; fixed expected source identity unchanged.
2. Same script, exit 1 after first six check groups: `_validate_arguments` correctly rejected the harness MCP request without `include_image=false`: `task queries require include_image=false and selectors only in query.objects or query.target/query.candidates`. Added the required field to the harness request. No product change.
3. Same script, exit 0: `{"checks_passed":7,"executed_engine_modules":51,"source_count":137,"source_sha256":"2c453e56f3abf83a49f9c8ef37a3a77728dd8f05168db4fd5217d3bad465c390","status":"passed"}`. `RESULTS.json` contains final full outputs and counters.

No Blender, model, external API, install mutation, new dependencies, or product source changes. Worktree remained clean after execution.

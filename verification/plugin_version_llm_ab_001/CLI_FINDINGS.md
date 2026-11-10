# Read-only CLI findings for PLUGIN-VERSION-LLM-AB-001

No consumer, model, Blender or MCP service was started by this investigation.
No authentication content was read/copied and no formal Codex configuration was changed.

## Current executable and login

- Executable: `C:/Users/Administrator/AppData/Local/Programs/OpenAI/Codex/bin/codex.exe`.
- `codex --version`: `codex-cli 0.152.1`.
- SHA256: `01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6`.
- `codex login status`: `Logged in using ChatGPT` (exit0). This establishes ChatGPT login, not an independent inspection of the subscription tier, quota or new request success.
- Current `models_cache.json`, projected to public model fields only, advertises `gpt-6.1-sol` and supports requested `medium`; no request was used to probe availability. Requested/resolved effort must remain distinct.
- Current `exec --help` explicitly says `--ignore-user-config` does not load `$CODEX_HOME/config.toml`; auth still uses `CODEX_HOME`. Thus the known path does not require copying credentials or changing CODEX_HOME. Separate neutral cwd and explicit ignored-config CLI settings isolate the task configuration while retaining existing login.

## Real medium precedent (Git records, not the older failed runner)

The current checkout has removed historical implementation files but they remain available through Git. The relevant successful live-toolchain commit is `836da8a`:

- `verification/effort_toolchain_bridge_001/REPORT.md`, `RESULTS.json`, `invoke.py`.
- Four fresh N/P × ultra/medium chains completed with quality C1–C7. Requested `gpt-6.1-sol`, medium full-chain N 58.228828s and P 39.345274s. The backend resolved setting remains unexposed; the old timings are precedent, not new comparison data.
- Per-cell public consumer traces are under `verification/effort_toolchain_bridge_001/actual_cells/<random>/N|P/model/turn_01/CONSUMER.json` in that commit.
- Earlier snapshot effort study at `2fefd14846e55fce7cd0a7e7a072bd1714e676aa` has 12 correct fresh answers, described by `verification/effort_consume_001/{consume.py,REPORT.md,RESULTS.json}`.
- Root review records still present at `D:/hefe/verification/fixes/20261109_adoption_entry/EFFORT_CONSUME_001_REVIEW.md`, `effort_consume_review/FINAL.json` and `ROOT_USAGE_ROWS.json`.

Do not use `verification/consumption_run_final_001/actual_invocation_001` as a successful medium precedent: its first CLI exited1 with zero answers and seven slots not run. That old PLAN requested ultra, not medium. Its failures are retained history.

## Reusable configuration/transport anchors

At Git `2fefd14846e55fce7cd0a7e7a072bd1714e676aa`:

- `verification/consumer_completion_prep_001/runtime/adapter.py`: `cli_argv` and TOML value serializer.
- `.../cli_transport.py`: absolute watchdog, pre-enqueue JSON line receipt timestamps, public event/usage projection and lifecycle cleanup. It has dependencies on `reviewed.py`, `public_projection.py` and frozen historical runner helpers, so a small new runner may be simpler than restoring that platform wholesale.
- `.../MODEL_SETTINGS.json`: accepted provider and explicit configuration template. Its old executable/hash must be replaced with the current frozen binary above; effort becomes medium for both arms. Do not treat old binary availability as current execution.

Accepted provider configuration is `model_provider="openai_http"`, `wire_api="responses"`, `requires_openai_auth=true`, `supports_websockets=false`, `supports_standalone_web_search=true`, `base_url="https://chatgpt.com/backend-api/codex"`, `forced_login_method="chatgpt"`, `service_tier="default"`. This is existing ChatGPT-login transport, not an external key API.

Both arms should use the same `exec --ignore-user-config --strict-config --json --skip-git-repo-check`, current binary, requested `gpt-6.1-sol`/medium, neutral fresh cwd and stdin prompt. `--ephemeral` is currently documented by local help if new persistence is not required. No resume, --last, provider fallback or replacement answer.

Existing real argv used stdio MCP inline table with `command`, `args`, `cwd`, `required=true`, `startup_timeout_sec`, `tool_timeout_sec`, and `tools.<name>.approval_mode="approve"`. It did **not** require a `transport` field. For this task expose only the common thin bridge, with the same server and tool names/schema; the install or cell condition must not appear in public tool descriptions.

Disable unrelated capabilities explicitly for this experiment: hooks, apps, memories/use_memories, multi_agent/multi_agent_v2, goals, remote_plugin/plugins, bundled skills/include_instructions; `skip_host_skill_discovery=true`, `project_doc_max_bytes=0`. Old template has per-plugin `.enabled=false` including agent-learning. Current `features list` confirms shell_tool/view_image/hooks/apps/memories/multi_agent/plugins/remote_plugin/skip_host_skill_discovery names exist. This experiment should additionally set shell_tool and view_image false (unlike the old real-scene study); any unexpected built-in/file-change/collaboration action is a recorded protocol deviation, not quietly ignored.

Remove inherited chat selector and API environment keys before Popen without retrieving their values: CODEX_THREAD_ID, CODEX_SESSION_ID, CODEX_TOOL_CALL_ID, APP_TOOLS_PIPE_PATH, CODEX_APP_TOOLS_PIPE_PATH, CODEX_TASK_WORKSPACE_VERIFYING_IDENTITY, CODEX_PERMISSION_PROFILE; plus API_KEY/ACCESS_TOKEN suffixes and explicit OPENAI_API_KEY/CODEX_API_KEY/GOOGLE_API_KEY/GEMINI_API_KEY. Do not unset shared login home or print auth contents.

## Evidence semantics to retain

Public `turn.completed.usage` may expose input_tokens, cached_input_tokens, output_tokens, total_tokens, reasoning_tokens, reasoning_output_tokens. Preserve actual numeric fields and absence; cached is a subset, and reasoning/output must not be summed twice. CLI turn usage does not establish the number of provider requests, bill or resolved model/effort.

Keep each fresh thread ID, complete public tools/arguments/results, final answer bytes and absolute prompt-write/close→complete-final receive timestamp; model thought/system text is not needed. Keep startup and stderr failure diagnostics sufficiently to identify recoverable config errors without exporting credentials. Exit0 is lifecycle evidence only. Pair quality, actual native final state and timing separately; no favorable-result resampling.

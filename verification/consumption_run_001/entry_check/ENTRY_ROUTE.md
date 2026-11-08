# Installed normal MCP consumption entry — read-only preparation

The fixed candidate is the installed Desktop CLI at `C:/Users/Administrator/AppData/Local/OpenAI/Codex/bin/f71a721e0e6193a9/codex.exe`, version `0.167.0-alpha.3.2`, SHA256 `4b3286e35d7fe866c6b0eb3f07d7a4cdb5e96489576170dfd6b3a15aa1c67382`. PATH resolves a different installed `0.152.1` launcher first; do not use bare `codex` in the future runner. Both login-status commands report ChatGPT login. No auth/key/token file was opened, hashed, copied or exported.

Retain configured `gpt-6.1-sol`, `ultra`, `service_tier="default"`, and **openai_http**. Preserve that provider's existing six fields, including ChatGPT backend URL, responses wire API and requires_openai_auth=true. DESKTOP_CANDIDATE.json contains the exact safe definition and argv list template. No provider or model substitution is proposed. The cache associated with client0.167 lists this model, ultra, text/image and code_mode_only; actual model availability/backend is unexposed until the authorized consumer executes. The cache advertises priority but the configured tier is default; do not silently change tier based on that cache.

Use the ordinary `exec` command with registered MCP `command/args/cwd/required` and the production `enabled_tools` filter supplied by the parent. Consumer calls are normal function/MCP calls; there is no model-visible JSON forwarding protocol. `--ignore-user-config` only skips config.toml, while auth uses the original CODEX_HOME/default store. `--ephemeral` prevents persisted session files, and `--json` emits public event JSONL. These flags are present in exact local help. No consumer or MCP initialization was performed to preflight the four tasks. [Official noninteractive docs](https://learn.chatgpt.com/docs/non-interactive-mode), [MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

## Injection/configuration boundary

The current user config has global blender/node_repl/agent_learning MCP entries and enabled plugins, including Agent Learning. The global `.codex/AGENTS.md` exists and is empty. Root's supplemental ROUTE.md was read in full. Candidate process overrides explicitly disable known user MCP servers and plugins, hooks/apps/memories/multi-agent/goals/remote-plugin, bundled skills and automatic skill instructions, with exact per-skill paths and project_doc_max_bytes=0. They keep shell_tool and view_image enabled. The candidate also suppresses raw reasoning, disables hosted web search and records parent environment names requiring removal; no environment values were exported.

The installed Desktop `features list` successfully reports the requested feature states under process overrides. `--strict-config features list` is unsupported and failed before that check; this failure is preserved. Nonfeature overrides were checked syntactically as TOML and against local generated schemas/reference, not by running `exec`. Thus this does **not** prove the actual consumer's effective config, model-visible prompt, managed-layer behavior or complete registered tool list. Treat unremoved automatic injection or unexpected tools in the unique batch as a contamination failure. No clean-N or hard-blind claim is supported by these checks. [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference), [skill selectors](https://learn.chatgpt.com/docs/build-skills).

`debug prompt-input` was checked through help only. It can render model-visible system/developer input and lacks exec's ignore-user-config flag; its startup absence of managed hooks/MCP could not be proven without execution. It was deliberately not used and no full system prompt, hidden reasoning, encrypted context or model instructions were saved/exported. The cache/model inspection retained only public capability fields.

## Budget dependency

Neither local exec help nor either generated protocol/config schema exposes a confirmed max_tool_calls or hard final max_output_tokens setting. Therefore 4096 output tokens must be labelled not hard limited. A broker's eight MCP calls are not an eight-action cap across retained shell/view_image/write_stdin and code-mode carriers.

Current official hook documentation supports PreToolUse before shell, MCP and most local tools, including nested code-mode calls. It also documents exceptions: hosted/specialized tools can bypass hooks, and write_stdin transport does not fire a fresh PreToolUse. New nonmanaged hooks require trust of their exact definition; the task forbids changing trust/global policy or using a bypass flag. An owned hook therefore remains an unverified dependency, not a validated all-tools hard quota. Do not turn postdispatch JSON item counting into a predispatch hard-limit claim. A future threshold watchdog may invalidate/terminate a cell, but cannot retroactively prevent an already dispatched excess action. [Hook behavior and trust](https://learn.chatgpt.com/docs/hooks).

## Files and checks

- READONLY_COMMANDS.json plus help/version/status/feature outputs preserve the PATH0.152 inspection.
- DESKTOP_READONLY_COMMANDS.json and DESKTOP_CANDIDATE.json preserve the selected0.167 binary, exact provider/model/tier proposal and limits.
- USER_CONFIG_WHITELIST.json records safe settings; no auth contents or user instruction bodies.
- LOCAL_SCHEMA_EXTRACT.json / DESKTOP_SCHEMA_EXTRACT.json record generated static schema manifests and selected definitions. Raw generated directories are redundant with GENERATED_SCHEMAS.zip and can be excluded from the parent's seal.
- STATIC_CHECK.json is only syntax/TOML/archive validation, with actual-runtime/injection/hard-action-limit fields explicitly false.

Preparation errors retained: a Python `utf8-sig` spelling error failed before config parse; rg wildcard path was not expanded on Windows; strict-config was unsupported for features list. They caused no model, Blender, server or RPC execution. Subsequent safe checks corrected only preparation commands.

0 consumers, 0 answers, 0 Blender, 0 MCP/native/product RPC, 0 API calls. This preparation does not authorize starting the eight answers.

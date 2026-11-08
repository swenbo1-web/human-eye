# CONSUMPTION-ENTRY-STARTUP-FIX-001 — independent source review

Snapshot 2026-11-08T03:12:04Z. Parent task cfc7e2c5 revision1/write62 was verified through the reviewer's own child binding. This review inspected source/JSON/fixed Git bytes only. It did not execute candidate functions/tests, Codex parsing, exec, model prompts, product imports, Blender, MCP services, sockets/RPC, APIs or auth/key/private logs.

Candidate runner SHA256 `5a5feb16fb7a5a945db9e2ea3e130368d6eb054378cf65d5183e7fec7141bbd1`; PLAN SHA256 `89ecee986cb627ed8db32c85848220e25fb8565491e4aadff90e155c6488e778`.

## Source scope

AST comparison with fixed2195ac8 finds only two existing functions changed: safe_environment and consume. The sole new function is retain_startup_diagnostic, plus its re import. Public-event filtering, argv construction, retry/termination behavior, source/window guards and slot bookkeeping are otherwise unchanged. bridge.py remains byte-identical with SHA b8b2e876436578e82b21d5faf59fb8f27e1dbb3e188d3bba3d023d216a24f01b; he_bootstrap.py remains byte-identical with SHA5fc5236fd2d822d5f5dab772f222c52d0457974604335cae023176e8eebdae27.

The owned consumer PID is initialized null and recorded immediately after successful Popen, before the post-start deadline check. A configuration/startup failure that returns a Popen object can therefore retain its actual PID. This addition neither starts a second process nor changes cleanup success or retry eligibility.

CODEX_PERMISSION_PROFILE is added to the existing key-name exclusion set before any source[key] value access. Other environment filtering and original CODEX_HOME/client routing are unchanged; no global permission/configuration, managed restriction or trust bypass is introduced.

## Diagnostic boundary

The new stderr function retains only a small set of full-match ordinary CLI templates or normalized configuration-field/flag/profile categories. It does not store arbitrary Error-tail text. It rejects sensitive/system/developer/reasoning/encrypted markers and control characters, requires a raw line no larger than512 bytes, and bounds all retained UTF-8 text to4096 bytes. Complete incoming byte counts remain separate from normalized retained text. Rejected/truncated nonblank content receives redaction/unavailable accounting.

The literal bootstrap/configuration/Caused by/invalid transport templates can retain the independently demonstrated transport diagnosis. Config identifiers and unexpected flags use restricted identifier syntax. The profile/sandbox conflict branch exports a fixed category with details redacted. The ordinary stderr record does not alter the public JSON event allowlist or failure/cleanup decisions. This is a deliberately narrow diagnostic aid, not a promise to retain every possible future startup error or a general secret classifier.

## PLAN and preserved contract

Exactly four settings are removed, with no other common setting added or changed: mcp_servers.agent_learning.enabled, mcp_servers.blender.enabled, mcp_servers.cua_repl.enabled and mcp_servers.node_repl.enabled. Under ignore-user-config these declarations could create disabled entries with no transport. Their removal does not remove the complete native registration or P-only complete HumanEye registration built by argv_for. The runtime exec still contains strict-config.

The CLI executable/SHA, model, effort, provider and tier are identical to2195ac8. Product source identity/manifest, task order, limits, image limits, Blender/Python identities, neutral root and fixed material identity also compare unchanged. execution_ready is false. All17 runtime component resolved paths and SHA values match the snapshot. No new trial is authorized by this candidate.

The root TRANSPORT_PAIR evidence establishes an invalid disabled-only shape on the fixed CLI. It does not recover the previous discarded71-byte message or prove the old failure's unique cause. Likewise, a future features-list configuration result is not proof of exec's complete effective configuration, injection boundary, MCP registration, model/backend availability or consumption. Those remain unverified without a separately authorized real batch. The closed1error+7not_run result must remain unchanged.

## Evidence presentation

The first MINIMAL.diff snapshot was inflated because the baseline decoded CRLF and the candidate read_text-normalized LF were compared differently. This is a diff-rendering issue: the runtime files themselves retain CRLF. The parent was asked to normalize both inputs only for the human-readable diff, without rewriting fixed candidate bytes. No runtime change is required for this point.

No additional functional blocker was found within this narrow source scope. Parent-directed mocks and the two permitted zero-consumer configuration parses are separate evidence; this reviewer did not run or independently count them.

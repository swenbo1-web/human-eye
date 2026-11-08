# Final review resolutions

The original reviewer snapshots remain unedited. Their earlier hard-eight-action comments reflect the superseded draft. Root's CONSUMPTION_BUDGET_CLARIFICATION_001 was applied with0 model answers: reserve_action now only counts, two revised tests prove over-threshold MCP calls continue, the controller never rejects/terminates for more than8 events, and the scorer/README require no threshold quality penalty. Physical calls retain the existing neutral128 ceiling, independently proposed for the window; it is not an eight-action cap.

After FINAL_REVIEW.txt's01:41 snapshot, root implemented every reported refinement before freeze:

- Post-Popen reader/stdin setup is inside owned try/finally; BrokenPipe records CONSUMER.json and reaps the child. The corresponding synthetic test passes with an in-memory mock.
- taskkill has a3-second subprocess timeout and bounded wait/kill. A second synthetic test checks the bound.
- Same original answer deadline is checked immediately before Popen and also drives an independent local Timer, covering blocking I/O paths; late completion is rejected again after final construction/persistence. No coordinator polling renews time.
- PLAN pins the existing engineering Python binary SHA and version, alongside installed Codex/Blender and all helper/controller source hashes.
- STATE guard requires status starting granted, exact cycle/token/owner/caps, and checks an expiry if provided. Current execution_ready=false remains the earlier first guard.
- Native/HE physical reservations happen before connecting; remote poison/unknown halts, and cleanup preserves original owner.close/wait with separate raw wire metering.
- Credential and parent binding environment names are excluded before their values are read; no auth store or token/key is exported.
- Source case assets will first be copied to a private neutral input.blend before NativeSession.start, so its public runtime metadata does not inject the source case basename. No asset copy occurred during preparation.

Actual host injection/schema/model availability, optional-image delivery and complete builtin-output admission remain unverified. These are not converted into passing results by the source fixes. The final19 unique synthetic methods and static source/hash checks are preparation evidence only. Root still must review/freeze the executable output/context contract and grant the single batch; this report does not grant it.

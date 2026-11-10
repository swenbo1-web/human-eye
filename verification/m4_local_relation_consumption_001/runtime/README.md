# Three-arm consumption runtime preparation

Preparation only. No consumer, CLI, product or Blender process is started by this preparation. `prepare` and `run_models` were not called. The only executed checks are pure arm/GO-contract tests (with process/system/network sentinels) and `preflight_inputs`, which reads existing input bytes and metadata only.

`actor.py` and `consumer_transport.py` are byte-identical copies of the accepted `m4_observation_baseline_001/runtime` files. Their internal capability profiles remain exactly N/P. The old transport's workspace directory name is intentionally unchanged; new neutral cell IDs lrc01 through lrc09 avoid the old workspaces without clearing or modifying them.

The driver is the only adapter. External sequence groups remain N/P0/P1. `arm_runtime(plan, slot)` returns a new private slot with internal group N/P and `external_group` preserving the original external arm. Original slots and outer RUN_RESULT rows are unchanged. Actor configuration and cell metadata use internal N/P plus the external marker. Raw CONSUMER records therefore truthfully contain internal `group` and separate `external_group`; the nine-slot quality packager must validate that explicit binding, not require its internal group to equal an external P0/P1 name.

Required PLAN fields:

- `arms.N = {actor_group:N, installation_profile:P0, source_sha256:null}`.
- `arms.P0/P1` use actor_group P, their same-named installation profile and the fixed product source hash.
- `installations.P0/P1` contain the corresponding complete READY objects; runtime reads `installations/P0_READY.json` or `P1_READY.json` and requires equality.
- `installation_ready.dependency_python` is the common interpreter reference. Both installed versions must match it.
- `schemas/P0_PUBLIC_TOOLS.json` and `P1_PUBLIC_TOOLS.json` are the saved actual two-tool directories; the unchanged actor checks its newly loaded live directory against the selected schema.
- Inputs, T1 asset/snapshot, image, budgets, CLI/source hashes and dispatch input bindings retain the previous driver fields.

P0 is commit `107641ec19919d56aa843c1949261590fc338148`, canonical `7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1`; P1 is commit `e077fce38b5951efff8166b3b688d05ffa2ebf04`, canonical `53db41976085ce5f361d026196f4da5faf80d639af33dfced35ba58e328ef732`. N starts no product and uses the same existing P0 dependency interpreter for the common native worker.

The exact sequence is N/P0/P1, P0/P1/N, P1/N/P0, with three rounds and nine unique neutral cells. The pure `go_contract` requires this cycle `M4-LOCAL-RELATION-CONSUMPTION-001`, the frozen PLAN hash and maximum nine. Old six-cell GO is rejected. Default driver CLI remains input preflight only; future model execution needs the root's independent GO and explicit `run_models` invocation.

No lifecycle or timing core is replaced: the first cell origin, prepare's capped 40-second actor window, worker/full-cell 570 seconds, consumer 450 seconds, unchanged finish, source snapshot comparison, stop policy, image receipts, text/RPC/code limits and constructor observations remain. `read`, `save`, `load`, `finish` and `snapshot_binding` have identical AST to the original. The new arm selection immediately precedes the original final deadline check before consumption. Image provider receipt and model viewing remain pending/unknown; prepared attachment bytes are not model consumption.

`DRIVER_UNIFIED.diff` is the exact old/new driver text diff. `REUSE_BINDINGS.json` records byte hashes and reused common sources. Pure test logs and `PREPARED_INPUT.json` are preparation evidence, not a model trial or backend preflight. No old material, product, default configuration or installed release was edited or started.

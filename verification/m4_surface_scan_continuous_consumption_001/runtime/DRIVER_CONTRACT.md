# Outer driver contract

`driver.py` reuses the unchanged FIX1 coordinator, transport and actor. The FIX2
post-close helper is used only for terminal WIRE validation. Registered geometry
bindings use the original outer driver's snapshot normalization.

## Entry points

`run_one(slot, plan)` runs one planned episode. `run_batch(plan)` runs the fixed
sequence and preserves all eighteen planned turn slots in its aggregate counts.
`validate_preparation(frozen, require_committed=True)` checks the current batch,
its external dependencies and committed preparation bytes.

The default CLI validates inputs without launching a process. `--run-models`
checks the committed freeze, requires fresh episode paths and exclusively creates
`FORMAL_STARTED.json` before the formal sequence. No synthetic or model pretrial
is performed by that entry point.

## Original paths and publication

Each episode uses the short workspace path `ROOT/.m4cc1/<cell>`.

- `owner` contains the unchanged actor's audit and terminal `CLOSE.json`.
- `c` is initially absent and is created by the original coordinator.
- `w` is the consumer's shared three-turn workspace.
- `OWNER_FINISH.json` records the sole original `finish` operation.

Original short paths remain available. `BATCH/episodes/<cell>/ORIGINALS.zip`
archives all closed short-runtime files. `RUNTIME_MANIFEST.json` binds each
relative POSIX member using its byte count and SHA256.

`OUTER_RESULT.json` is written and closed after the outer archive and source,
registered geometry and terminal transport checks. `FINAL_TIMING.json` measures
through that close. Its `outer_valid_completion` is the authoritative outer
execution flag. Timing receipt publication is separately recorded in
`TIMING_PUBLICATION.json`. Reports retain buffered-write/close semantics.

`RUN_RESULT.json` records each entered episode's outer folder, runtime folder,
consumer output, owner output, exact coordinator result, execution rows and final
timing. Later episodes stopped by an unsafe boundary remain explicitly unrun.
A registered turn lacking a returned consumer record remains failed and triggers
the lifecycle-unknown stop. Recovery reads surviving originals and starts no new
work.

## Evidence boundaries

The driver preserves raw usage, actual thread IDs, actual product session IDs,
errors and provider retry observations. It performs no token summation or answer
scoring. A successful final completion distinguishes a recovered service warning
from terminal service unavailability while the original strict execution errors
remain recorded. Group costs and tool adoption stay out of CLI output.

`test_driver.py` uses local in-memory owners and temporary files. It checks the
fixed contract, single finish, original deadlines, complete outer write/close
scope, surviving-record recovery, failed/unrun projection, short paths and stop
policy without running CLI, Blender or a provider.

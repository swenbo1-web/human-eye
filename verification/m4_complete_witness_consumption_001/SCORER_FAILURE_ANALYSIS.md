# Frozen scorer failure analysis

I authored this scorer. During static preparation, I carried the Routed wrapper's per-record execution_state assumption into a single-slot producer that preserves the original route row. The current launcher writes execution_state at RUN_RESULT top level. The frozen scorer reads records[0] and then looks up execution_state on that row, raising KeyError at score_saved.py line79 before content/witness evaluation.

The first automatic result remains failed with SHA272f925f1f46b4140b7483fbeceb1ff0a2b58285d3b5c9cab6c417cbb6cb3a87. The quality seal remains93b0dde406a185bdb60c7921eb1f7d3f697e45e493763130d304828fdfdd30d9. This is a scoring integration defect. It does not establish an incorrect model answer.

## Saved terminal facts

RUN_RESULT reports completed, launcher_succeeded true, one route, one CLI and no terminal exceptions. The nested route reports outer_valid_completion true, an actual final and a terminal turn event. Actor29536 and CLI6356 have confirmed held-handle exit0, closed handles and no requested kill. Thin29156 has a confirmed held-handle exit1 while its EXIT receipt remains unknown. Those execution facts remain separate from semantic quality.

The existing sealed manual19-check and peer25-check reviews support the current TOP/index2 final and actual product-fact use. Both retain the extra raw geometry/camera and full pixel/normal verification, yielding direct-product-only false. This report does not rerun or replace semantic grading.

## Minimal later reader correction

A separately authorized derived grader can retain the complete RUN_RESULT object, select records[0] for original route fields, and read execution_state from that top-level object. Preserve the existing outer_valid_completion, CLI validity, actual runtime-binding and held-exit checks. Bind the known single-slot schema explicitly. Missing state must fail, without silently defaulting to completed or augmenting the saved row.

Any administrator-approved read-only regrade should write a separately versioned output with the same original evidence and criteria hashes. The first failed QUALITY and existing seal remain preserved. No model, qualification, observation, raster, prompt or product rerun is needed to correct this data reader.

This analysis only reads existing files and writes these two new analysis artifacts. Frozen source, rules, original records and sealed outputs remain untouched. No scorer, product or model was executed.

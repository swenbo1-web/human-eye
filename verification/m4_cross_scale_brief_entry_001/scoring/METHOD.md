# Independent scoring for the brief-entry slot

Use the historical formal nine-item rubric with one registered plugin slot, `P1`. Keep the historical P1 answer and scores in the comparison record. This scorer grades only the new slot. Keep admission, runtime completion, actual first-call treatment, and answer quality distinct.

Run `score_slot.py evidence` once the original public answer is sealed, or after a failed admission. Before checking the original PNGs, the scorer verifies the current admission and freeze, the same-slot start and publication, the original public answer and its sealed copy, and the fixed scene and truth. The inherited formal routines verify read-only identity using the generic process closure and both current source captures. They bind exact original images to the public CLI receipts and recompute the prescribed owner and contrast counts, framing and direction checks from the same-slot arrays and frozen truth.

Create `CLAIMS.json` from the actual sealed answer. Use the top-level key `P1` with `answer_sha256` and `gates`. Record all nine criteria independently, each with `status` of `pass`, `fail`, or `unverified`. Include a verbatim `quote` for each pass and a concrete `reason` for each fail or unverified criterion. A failure is an actual omission or contradiction. Use unverified when the necessary original evidence is unavailable. An unrun slot or one without a sealed answer takes no claims.

- `roster` includes `objects`, the complete region set stated in the answer.
- `geometry_M02`, `geometry_M06`, and `geometry_M09` each include `triangles`, `center_world_m`, `area_m2`, and `unit_normal`. Capture the actual source binding and printed numerals in the quote. Record decimal numerals as strings. The original numerical rounding contract applies.
- `witness_M02` and `witness_M09` each include `resolved_delivered_ref` and `direction`. If the answer uses an equivalent alias, record its actual quoted form and explain its resolution to the original delivery. Record `surface_pixels` and `contrasting_boundary_pixels` if the stated counts are part of the witness claim.
- `finite_pool_unknown_M06` needs a reason covering the finite set of six directions. Include `blocker` when the answer names one. The oracle verifies a positive-area occluder per direction and the named identity when supplied. The reviewer checks whether asserted actual occluder identity or raster observations have their cited tool support.
- `read_only_current_identity` uses the original answer and the independent read-only source and closure proof. `no_contradictory_claim` checks the answer as a whole for inaccurate completeness, direction, or source claims.

Run `score_slot.py grade --claims CLAIMS.json` after evidence and annotations. Only this post-run scorer and the original public answer are used for grading. Its execution uses no Blender, rasterization, model, or provider service.

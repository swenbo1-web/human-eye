# Assembly transfer answer scoring

Score the original sealed answer alongside the immutable public tool envelopes and original scene. Each arm has nine items.

| Item | Passing evidence |
| --- | --- |
| `roster` | Exactly the three eligible object surfaces |
| `geometry_N10`, `geometry_N11`, `geometry_N22` | Current object-local source rows, world center, positive area, directed world unit normal |
| `witness_N22` | Original delivered frame, current source and view, independent front clearance and pixel thresholds |
| `outcome_N10` | Qualifying originally delivered TOP frame, or observed TOP contrast deficiency on a geometrically complete, fitted surface |
| `finite_pool_unknown_N11` | All six directions have positive-area occlusion. A named blocker needs independent evidence for the directions claimed. |
| `read_only_current_identity` | Current ordered arrays and display before and after, bound to the saved assembly and closed worker |
| `no_contradictory_claim` | Review the entire final answer for unresolved contradictions and false claims of evidence or total invisibility |

Write `CLAIMS.json` keyed by each actual answered slot. Each row contains `answer_sha256` and `gates`. Every pass has a verbatim `quote` and its supporting values. Use `unverified` for unavailable necessary originals and `fail` for a missing or false criterion. Each non-pass has a reason.

For N10, use `outcome: contrast_insufficient` and `direction: TOP` for an observed shortfall. Exact pixel claims are optional and verified if supplied. A complete result uses `outcome: complete` with a current delivered frame reference. N11 may have visible pixels. Use `reason_kind: positive_area_occlusion_all_front_views` and add `blockers_by_direction` only when the original names a direction-specific blocker. `blocker` is reserved for an asserted blocker across the whole six-direction pool.

Run `score.py evidence` before grading. Run `score.py grade --claims CLAIMS.json` to recheck the original evidence and apply the nine criteria. Save claim annotations alongside the retained answer, quality and actual evidence.

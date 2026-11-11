# Saved-observation validation

`MANIFEST.json` pins `input_02` and three derived fixtures in `fixtures_02`. Every path in the manifest is relative to the batch directory. `SPEC.json` freezes the seed and transformation rules. `history/fixture_01` retains the original source-polygon fixture and its original scripts before the selected-capture topology correction.

`native_projection.py` exposes `directory(bundle)` and `selected_observation(bundle, request)`. It consumes the same retained dictionaries, fields, precision and existing relations as `prototype/final.py`. Both implementations can batch reads and retain inputs. Directory output contains IDs, names and AABBs. Selected output carries only explicitly requested geometry and ordered relation fields with explicit gaps.

The root runs the verifier with an unused result path.

```powershell
python -B verification/m4_batch_observation_coverage_001/validation/verify_projection.py --prototype verification/m4_batch_observation_coverage_001/prototype/final.py --output verification/m4_batch_observation_coverage_001/validation/RESULTS_01.json
```

The verifier checks original saved bytes, local vertices, matrices, units, four actual selected-resource triangle tables, local-evidence triangle ordinals, unchanged relation facts, derived geometry, mapped requests and detached field projection. Exact signed-coordinate transformations preserve the already recorded facts. The additional object has no recorded relations, so a new pair query exposes that gap. The verifier imports only the two named offline projection modules and standard-library modules.

The primary request has a four-object union. The optional request has an eight-object union and requires additional product integration or reads beyond the current selected-host limit of four. Offline field delivery establishes no current capture, automatic target discovery or new geometric relation result.

The root owns all verifier and performance executions. Generator execution and static parsing are recorded in `GENERATION_RECEIPT_02.json`. Any benchmark covers projection and JSON encoding of already supplied geometry and relations. Relation computation and input preparation remain outside that measured segment for every lane. A model task, token usage, transport cost and end-to-end benefit require separate evidence.

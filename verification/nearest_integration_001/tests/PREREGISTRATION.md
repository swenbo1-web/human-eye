# Ten offline integration groups, fixed before execution

These are offline packet fixtures, not host/source qualification. No Blender,
capture RPC, model consumer or product installation is used by this module.
The parent controlled runner must load the actual candidate bytes through the
existing verified source loader before compiling this test module.

| Group | Independent expected result |
|---|---|
| 01 Normal unique + scope | Parallel yz triangles at x=0 and x=2: nearest near, distance2; candidate normalization preserves scope, default entry rejects it, fingerprint differs from a complete-scope copy |
| 02 Exact positive/zero ties | Plane normal(1,1,1), height1 gives square1/3; two different-factor pairs tie exactly. Coincident/overlapping triangles give exact0. IDs remain sorted |
| 03 Same published float | Corner squares1 and1+2^-54 both publish1.0 but exact winner is a |
| 04 Different pair scale | a has square4+2^-400 and factor2^200; b is a positive-quadrant triangle with supporting edge x+y=6, square18 and factor1. b bounds overlap focal so both are retained; a wins |
| 05 Strictly excluded late degenerate | Far x100 with a later collinear face is strictly beyond near2, absent from retained capture and pair/kernel work; output contains only not_evaluated_pruned for it |
| 06 Retained unknown | A later collinear Far x1 is retained: partial, best-known near2 only. Exact known0 plus an unsupported collinear zero tie remains partial. No valid target distance gives unknown |
| 07 Unknown directory bounds/witness | Unknown bounds or no witness prevents pruning, but complete real pair measurement of healthy triangles may still give nearest near2 |
| 08 Witness publication failure | Known large-world box construction; independent Fraction XY corner-to-edge squared distance agrees, unavailable world witness does not erase valid nearest distance |
| 09 Boundary mismatches | Duplicate/missing directory IDs, retained capture mismatch, changed epoch/instance/source/scope reject before pair work |
| 10 Deadline including cache hit | Cold once, warm hit without kernel; deadline before entry and after an actual cache-hit pair both propagate unchanged, no extra solving |

The ten unittest methods may include the listed related subcases. Expected
distances are analytic or Fraction oracles; packet bounds/witness construction
does not supply the ranking answer. Instrumentation delegates the real pair
helper, kernel, `_nearest`, and ranker and preserves per-observation count deltas.
Only retained, nonfocal pairs are passed to the helper and retain is true on the
first call. Cache history frames remain zero; summaries contain no private key.

After the first controlled offline pass, a read-only review identified one
cheap metadata contradiction. Group09 now also reuses group05's exact geometry
while marking only the focal envelope unknown and retaining the old strict
exclusion. Current host logic would instead give lower0, so the boundary must
reject this packet before pair work. This is an explicit post-pass amendment,
not a new geometry case or an eleventh test method; the parent preserves the
initial run and executes the final candidate separately.

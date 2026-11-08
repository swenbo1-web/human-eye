# CLOSED-SOLID-READ-001 targeted test plan

Exactly sixteen methods are prepared before parent execution. No tests,
product imports, Blender sessions, RPCs or model consumers were run by the test
author. The parent uses the existing exact-byte verified product loader and
retains every execution attempt, including errors and unknown results.

| Group | Independent expected answer and fixed variants |
|---|---|
| 01 | Disjoint axis boxes: exact represented x gap 2; both argument orders. |
| 02 | Strict material containment despite positive surface gap 1.5; contained box touching outer boundary still has common open interior. Both orders. |
| 03 | Closed square through-hole frame: small box inside empty hole is separated; box strictly within wall material penetrates. Analytic coordinate intervals, both orders. |
| 04 | Perpendicular thin bars: no vertex of either lies in the other, but a fixed open cube is common interior. Both orders. |
| 05 | Unit-scaled face, edge and vertex contacts of two boxes are touching, not positive-volume penetration. Both orders. |
| 06 | Coincident and globally reversed coincident boundaries: certified penetrating or explicit unknown; never a false touching/separated answer. |
| 07 | Exactly representable axis permutation plus large translation; ordinary rounded rotation plus small translation with wide positive margins; swapped arguments and reversed full winding. |
| 08 | Open face list, duplicate/nonmanifold face, one reversed face and disconnected closed components remain explicit unknown, even against an AABB-disjoint valid mesh. |
| 09 | A cube with one vertex moved through its opposite boundary retains closed incidence but is self-intersecting; must be rejected before an early separated answer. |
| 10 | Represented dyadic subnanometre positive overlap and positive gap are distinct, proving zero-tolerance semantics. |
| 11 | Nonfinite coordinates, invalid indices, genuine extreme dyadic intermediate width, original triangle work cap and forced tiny work budget remain unknown. |
| 12 | Runtime cancellation, TimeoutError and RequestBudgetError propagate unchanged; no false geometry refusal. |
| 13 | Real task/service new fact only, exact zero-tolerance metadata and binding; legacy solver is forbidden for unrequested facts. |
| 14 | Successful complete-geometry cache cold/hot/revision/geometry-change; invalid/open unknown repeats compute rather than caching. |
| 15 | Mixed new relation/surface/legacy facts: old 1e-9 tolerance contract preserved, shared cold preparation counted once, hot pair kernel counts zero. |
| 16 | Original assembly initial/unchanged/changed, all three candidates, AABB-invariant edit, accepted Decimal80 truth and nonzero distance error bound, nearest separated piece, full-geometry cache hits/misses. |

The analytical cases use interval inequalities and explicit common open regions,
not the product kernel as an oracle. Original assembly truth is the accepted
`run_02/author/assembly/TRUTH.json` certificate, tied to snapshot SHA
`5a089d22faad7c90b9a28c6ea408ea8b73e8b939e47a3cb66a193ba85f23fc14`.
The accepted truth file is fixed at SHA256
`d01b0006ef1d4416c8b40663e8aabb7ba64730c7c833b516c3ee1631651a38ff`.
Distance comparison retains the existing rule
`abs(measured-d0)+distance_error_bound_m <= 1e-6`, rather than treating rounded
`.01` and `.04` examples as exact truth, and also checks membership in the
original nonzero-error distance interval. Reconstructed current world points must
match that original snapshot's local/matrix map.

Task tests execute the real service, task builder, relation kernel, surface
distance and existing cache over a fake host carrying explicit current meshes.
No final fact is fabricated. This is offline geometry/entry evidence; the
parent's single bounded private session provides actual Blender/source-binding
and original four-point patch evidence. CPU, heap, author usage and model-level
benefit are not inferred from feature counts or this suite's elapsed time.

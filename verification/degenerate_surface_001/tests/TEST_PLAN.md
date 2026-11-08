# DEGENERATE-SURFACE-001 directed mathematical plan

Exactly twelve new unittest methods are preregistered. Each method is one group;
the variants below are fixed before execution. The parent alone executes these
tests using the existing verified-source loader and preserves every attempt.
No model, Blender, RPC or product import was executed while preparing the file.

The independent oracle enumerates nonempty supports of each face's vertices,
solves the exact equality-constrained quadratic stationarity system with
Fraction Gaussian elimination, rejects singular/infeasible supports, and takes
the minimum feasible squared distance. It does not call any product primitive.
Explicit analytic squared answers additionally check this oracle for small
fixtures. Each tested rank key is converted independently to an exact Fraction.
Witness membership is independently bounded against the original face union.

| Group | Fixed cases and assertions |
|---|---|
| 01 | Point/point distance 5 and coincidence; repeated coordinates; zero direction; no face/edge-edge work. |
| 02 | Point/segment interior and endpoint distances; all six orders of three collinear distinct vertices; two duplicate-endpoint orders; actual convex hull endpoints; reversed pair order. |
| 03 | Point/triangle interior, edge, vertex and on-face contact; pair reversal. |
| 04 | Skew segment interiors, parallel offset, crossing, collinear overlap, endpoint touch and separation; pair reversal. |
| 05 | Two noncoplanar segment-through-face contacts with both segment endpoints strictly outside the face; axis-aligned and oblique; pair reversal. |
| 06 | Coplanar crossing with both endpoints outside; parallel above-plane crossing projection with positive distance; coplanar disjoint gap; pair reversal. |
| 07 | Ordinary separated triangle pair with original feature counts 1/6/18/9; disconnected point-face union cannot become a global convex hull; late degenerate point face remains eligible. |
| 08 | Integral scaled rotation plus 2^40 translation; rounded trigonometric rotation plus 2^25 translation. Independent truth uses the actual binary64 arrays and does not assume intended rank/length survived. |
| 09 | Exactly nonzero near-collinear triangle, retaining point-face work; positive segment/point gaps 2^-40 and 2^-600; exact rank and positive distance. |
| 10 | Negative/bool indices and NaN stay unknown; common frame requiring over-4096-bit squared intermediate stays unknown; unchanged constants; face limit checked before expansion; cancellation/Timeout/RequestBudgetError propagate. |
| 11 | Original T04 geometry from build_assets.py, with near Matrix value represented as binary32 then binary64; real host-capture/service/summarizer/kernel chain; all four targets complete. Added fixed duplicate-near tie variant; ordinary triangle ties retain strict AABB exclusion. Repeated requests bind current capture and hit rank cache without kernel work. |
| 12 | Seed recognizable values under old normal/rank cache versions; new normal and rank results ignore them, remain isolated, each compute once then hit. Large-world point/segment exact distance sqrt(2/5) stays valid when rounded witness publication exceeds tolerance; public fact must keep unknown witness without losing distance. |

Groups 01–09 and 12 use both argument orders for each measured mathematical
fixture unless explicitly noted in the source. Group 11's T04 geometry is not
claimed to be actual Blender evidence: it is the original asset-construction
coordinates executed through the real read-only chain with fake RNA. The
parent's unique three-RPC QA supplies actual asset/captured-coordinate proof.

The fake-RNA capture keeps original source validation, identity binding and
geometry acquisition; it does not inject a nearest answer. A degenerate focal
has no nondegenerate triangle witness for acquisition's finite upper bound, so
the T04 variants correctly retain all targets. Strict exclusion is tested in
the ordinary focal variant; no acquisition implementation is changed.

Fixed identities expected by the new contract:

- Method: `exact_binary64_triangle_surface_hulls_v3`.
- Normal cache: `task-surface-proximity-exact-aabb-v3`.
- Exact-rank cache: `task-surface-proximity-exact-world-rank-v2`.

Normal-path feature work and degenerate point work are retained in EVIDENCE,
alongside binary64 oracle fractions and cold/hot cache counts. These counts are
local work observations, not task/model performance claims or temporary-memory
measurements. No tolerance, size, arithmetic-width or deadline is relaxed.

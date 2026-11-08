# CLOSED-SOLID-READ-001 source and saved-evidence review

PASS, no blocking correctness issue found in the current candidate. This is
read-only source/record review; no product, test, Blender, RPC or PID call was
added. The reviewer authored the sixteen directed groups, so this is an
independent review of the implementation, not a second independent test suite.

The positive-volume answers have sufficient certificates. An exact transverse
intersection in the interiors of two embedded boundary triangles gives common
open interior locally. A shell boundary vertex or triangle centroid strictly
inside the other solid also gives positive-volume overlap. Positive boundary
distance alone is never treated as separation: disjoint connected boundaries
use exact parity on representative points in both directions, detecting material
containment and leaving the through-hole empty.

Touching requires actual boundary contact plus an exact global supporting plane:
all vertices of each solid lie in opposite closed half-spaces, with nonempty
strict sides. Thus the solid interiors cannot intersect. Unsupported contact
arrangements or coincident boundaries without a sufficient interior certificate
remain explicit unknown; zero surface distance is not a penetration proof.

The exact ray test rejects boundary hits/coplanar degeneracies and tries a fixed
bounded list of positive-component directions. It never assigns parity from a
degenerate direction or floating winding threshold; exhausting the list returns
unknown. Topological checks require edge incidence/orientation, connected face
adjacency, one-cycle vertex links, nonzero faces and volume. Exact self-BVH
intersection checks allow only the shared topological simplex and occur before
any cross-surface early answer. The cross-BVH keeps the left/right face indexes
distinct, while the original self traversal retains unordered-pair coverage.

All new arithmetic predicates use the existing checked integer/Fraction
operations. Existing width/face limits remain, with separate bounded work,
candidate and ray counts. Cancellation/deadline exceptions are not swallowed as
geometry unknown. Boundary ambiguity, self-intersection, invalid topology and
resource limits retain explicit refusals. The implementation does not guarantee
a measured answer for every degenerate boundary arrangement in the broad shell
class; that limitation is explicit rather than an approximate classification.

The public entry adds only the separate zero-tolerance closed_solid_relation
fact, with explicit shell scope. Existing geometry_safety, query_policy and
scene_cache bytes match the baseline. Old solid_relation still uses its original
1e-9 parameter and evaluator; no signed penetration depth or MTV is invented.
The only live_service change marks new-only kernel work in existing telemetry.
Mixed relation/surface requests pass a query-local exact preparation holder;
surface distance still uses its original admission/preparation path when absent.
Successful complete-geometry cache keys use a distinct algorithm and zero
tolerance; unknown results remain uncached. No global scene cache or new service
is added.

Current 131 source bytes match both saved engine snapshots and the second
133-member executed ZIP. Source identity is
1545da06b415864cf3f666f3a56432e91689d1a0565ea8589a19e3ecfff2b459.
The second ZIP includes all products plus the actual directed test and runner;
its original loader guard proof is true. The first attempt's missing execution
identity/ZIP/results remain missing and are not reconstructed as stronger
evidence.

Saved logs show the first attempt ran 127 methods: 125 passed and two failed.
Both failures are existing SelectedTaskBridge fixtures attempting to create a
local mock socket while the offline no-network guard was installed; the mock
raised before socket construction. They are not geometric counterexamples and
are retained. The final recording assertion prevented first-attempt final proof
artifacts. Only the new sixteen groups were then repeated: 16/16 passed with a
complete loader/executed-byte proof. Directed denominator is therefore two
attempts, 32 method executions, 32 passing; the 111 other methods were not
repeated. No claim that the first entire run passed is made.

Directed truth uses analytic intervals/common open regions and the old accepted
Decimal80 certificate, not the new classifier. Saved original three-state
evidence covers all nine candidate/state combinations: initial and unchanged
02/04 separated with 03 penetrating; changed 02/03 penetrating and 04 separated.
Separation distances satisfy both the old nonzero-error interval and the old
answer rule. Original target outer AABB remains identical after the patch.
Cold/changed relation computations and unchanged hits are recorded separately;
the shared surface preparation records zero repeated admission work. These are
offline task/service/cache observations, not actual Blender QA or model benefit.

CODE_REVIEW.json preserves exact source hashes, original log counts and all nine
saved relation/distance/cache rows. Public live QA, owner closure and actual
source/capture binding still require their separate bounded evidence.

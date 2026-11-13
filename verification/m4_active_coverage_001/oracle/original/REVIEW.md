# Prospective design review — not product acceptance

The design child inspected the fixed source and produced four draft files before quota interruption. Root read the draft generator, task, geometric oracle and relevant current source. The root next-task contract is authoritative; these drafts remain unchanged evidence of the proposal.

Existing functions that can be reused:

- attention_policy.py:232 proposes a Q4 replacement for an already specified distinct target/reference pair and positive clearance witnesses. It does not discover an all-scene target set.
- attention_rendering.py:158 constructs an arbitrary-direction orthographic camera outside all supplied geometry; attention_raster.py rasterize_attention can retain a common depth/owner buffer.
- local_view.py:165 handles an already selected focus/window, with existing16 surface-pixel/4 boundary-pixel qualification. reference_view.py:140 requires an object and patch.
- native_observation.py:279 validates the existing XY/XZ/SCENE multiscale convention. Its ordinary public camera contract cannot be silently treated as arbitrary new active-camera support.

The draft28-object/276-triangle scene has six geometric rectangular panels. Its oracle uses rational projected opaque-box shadows to test continuous open-interior visibility across six directions, and enumerates direction subsets. This is a useful independent geometric oracle, not a pixel-readability oracle or a model benchmark. The supplied oracle hashes match the supplied geometry/task files; root did not claim a new live render or complete qualification.

Root found a material task ambiguity: two directions covering all coverable panels do not imply two local images, since cameras can have different centers and spans. The next task fixes one complete global pose per direction, requires frame inclusion and actual depth/owner raster qualification, and keeps geometry/visibility/readability separate. The finite-pool unresolved result also cannot be called invisible from every possible viewpoint.

The proposed first gap is newly visible ROI coverage and next-view selection. It will use geometry-defined targets, shared projected bounds and exact narrow clipping, plus coverage bitsets; it will not import the oracle's target names or visibility matrix. An off-center blocker control is required because a visible center point cannot prove full panel visibility. One optimization follows the reference implementation, then the batch stops for review.

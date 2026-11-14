# BRIEF-DELIVERY-001 independent semantic review

Reviewer: child `brief001_semantics_review`, parent task `0fe03380-1fed-479d-9768-93d886075660` revision 1. Candidate `cdd2b11693a2586cfea07528c6bca27b93d02499`; compared product diff against `32a1c6eb47cfa84133d92199387339d407a33cb5`.

The scoped brief-delivery repair passes this review. No blocking product defect found. This conclusion concerns the five frozen historical responses and static representation routing; it does not claim wider geometry coverage or model task benefit.

## Independent checks actually executed

`semantics_independent.py` imports only standard-library JSON, pathlib, copy and hashing. It does not import product code or the author's semantic decoder and issues no new product, model, Blender, raster or stdio calls. It reads actual archived TX/RX and original inputs, independently expands all ten default/brief values, and reverses only registered image-path relocations for the five full values. Result: **1249/1249 assertions passed**. These are assertion checks, not 1249 independently sampled scenes.

- Each of the four rectangular historical cases reconstructs 28 object identities, 6 ROI records, 22 unsupported-object unknown records, 2 observations and 12 pixel rows, including all 7 unreadable/negative rows and 1 unresolved ROI.
- The nonplanar case reconstructs 1 object, no ROI or image, and retains unknown. No covered region is invented.
- Original top-level task status, read-only/authority values, full retained binding, capture instance/epoch/revision, unit/coordinate/scope, source status and check scope compare equal.
- Omitted frame scene/camera/host/revision aliases compare equal to retained binding before their omission is considered valid. Observation ROI IDs and all pixel fields reconstruct exactly from tables, including thresholds and readability values.
- All scope and coverage fields reconstruct exactly, including finite-pool unknowns, observation order, state updates and unsupported-object partition. Actual-source scope remains whole-object planar rectangles.
- All five full dictionaries compare equal to originals after reversing only registered `frames[].image_path` and `facts.observations[].image_path`. Every other diagnostic remains untouched.
- Request IDs and response-detail arguments match each actual response. Default and explicit brief are equal for every case.

## Static review

`live_spatial_mcp.py:805` implements a local versioned projection. `_active_observation_content` at line 989 retains existing native-image construction and the full metadata path; lines 1039–1044 select brief only for non-error results that can be represented, and record projection outcome. The dispatcher passes response_detail at line 1069. The public schema now advertises brief for active observation while other modes retain their defaults. Explicit full does not run the projection. The function deep-copies its result and retains source evidence separately.

The six new unit methods cover no-ROI and prediction-only omissions, reordered frames, default/brief/full equality, unsupported/ambiguous references and an encoder failure after one constructed image. I inspected these tests and the 33-test author receipt, but did not rerun them; their pass count is author evidence, separate from the 1249 independently executed JSON assertions.

The projector is a representation adapter, not a second complete validator of the geometric engine. It need not recompute geometry or duplicate every internal logical invariant. No observed current-source semantic contradiction or information loss warrants broadening this batch.

## Evidence provenance note

`SEMANTIC_CONTRACT.json.static_product_review.product_source_sha256` still references `5e2e2329729985bd8c7d14c887397fd88fe614933c1f16d2789378411a8cc0cb`, while my direct hash of the current product file is `89c86f29e4bd07e33cae15dfc431eefb21aa35b737c15634ac57bbfa5fc8cdc6`. Treat the contract's nested static-review hash as a stale preparation reference, not proof that the final product was statically reviewed under that hash. The actual frozen/runtime/Git identity chain is being independently reviewed by root. The semantic reconstruction above reads actual delivered values and does not depend on this stale nested hash.

Two exploratory reads guessed nonexistent `tests/` and `live_spatial_service.py` paths; they produced navigation errors only. Correct tests are under `verification/`, and runtime service is `live_service.py`. These reads caused no product execution or mutation. The actual offline semantic script passed on its first execution.

## Next capability implication

The next useful gap is still whole-object support: `active_observation.py:208` extracts at most one ROI covering the entire mesh; line 371 excludes every triangle from the ROI's object when checking blockers. `active_observation_images.py:98` computes readable pixels by whole-object owner. Multiple patches cannot safely be enabled solely by accepting more ROI: visibility and pixel ownership must distinguish a region's own triangles from other faces of the same object. This is a capability limit preserved in current output, not a regression caused by brief delivery.

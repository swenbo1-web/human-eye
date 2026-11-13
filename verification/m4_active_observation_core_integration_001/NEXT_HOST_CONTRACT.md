# Next host and MCP connection

## Existing collection point

The current `BlenderMCPHost.capture_scene()` requests the existing `capture` operation. `BlenderReadonlyHost` captures evaluated meshes, uses Blender `calc_loop_triangles`, maps evaluated local vertices through `matrix_world` and physical unit scale, and returns `unit='m'`, `coordinate_frame='world'`, a capture revision and a complete `meshes` collection. Each mesh carries `object_id`, `name`, world `vertices` and triangle `faces`.

The next connector can translate one accepted capture to `scene['objects']` with those same world vertices and triangles. The existing acquisition and geometry budgets, source identity, deadline, complete-scene scope and evaluated-mesh limitations remain attached to that capture. Selected-object captures require a separate explicit scope decision because the current coverage calculation consumes the full occluder set.

## Required outer binding

- Bind the existing host document/session identity, complete-scene capture scope, capture revision, source fingerprint, physical units and ordered object-instance IDs at the connector entry.
- Retain the mapping between host `object_id` and core `object_index`. Region geometry identity remains the canonical oriented four-corner identity.
- Bind camera names, matrices, image dimensions and both direction representations to the same explicit finite pool. The current core has no camera-generation algorithm.
- Hold the resulting session and image adapter within the existing request or task owner. Invalidate them when the host binding or camera pool changes. A core geometry hash alone excludes some host metadata and is insufficient as the entire host-generation key.
- Keep frame references, the raster source generation and actual RGB/depth/owner arrays attached to that session. Return short facts and a readable local image reference through the established image-delivery channel, with its actual delivery result.
- Map out-of-domain discovery and finite-pool unresolved regions to explicit unknown scope. Predicted completeness enters covered only after bound actual pixel feedback.

## Precision boundary

The current discovery contract uses exact coplanarity and orthogonality. Blender binary64 evaluation can produce a nearly rectangular or nearly planar shape whose stored coordinates fail those exact predicates. The next connection must preserve the actual coordinates and report the supported-domain result. Tolerance fitting, rounding and geometry repair require separate evidence before becoming source normalization.

Multiple patches within one mesh object, general same-object self-occlusion and nonplanar regions remain subsequent capability choices. The immediate host connection can begin with controlled exact-domain assets while measuring actual domain exits in author-created assets.

## Concrete next deliverable

Add one thin read-only entry that obtains a source-bound complete capture, translates it once, supplies the already validated camera pool, runs the installed core through actual frame feedback and returns its short facts plus delivered image reference. Verify real source changes and delivery status through that entry. Selection, saving and geometry setters are outside this read-only connection contract.

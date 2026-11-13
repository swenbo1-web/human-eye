# Finite active-observation core

## Inputs and ownership

The caller supplies complete current world-space geometry in metres and a coherent explicit orthographic camera pool. Each `scene['objects']` entry contains `vertices`, triangle index triples in `triangles`, and an optional `name`. Numeric coordinates retain the existing exact Fraction conversion, including the exact binary value of supplied floats. The caller owns physical units, capture completeness and host provenance.

Each camera contains `name`, `direction_rational`, `view_matrix`, `projection_matrix`, `size_px` and `target_to_eye_unit`. The rational direction, floating direction and matrices describe the same camera. Names are unique and the pool contains `SCENE`. Image adaptation supports square integer sizes from 64 to 512. The fixed integration inputs use 512.

One object is one connected, consistently wound, hole-free planar rectangle to become a discovered region. Occluders retain all their supplied triangles. The source domain and exact arithmetic semantics follow the accepted candidate. The session owns normalized immutable-coordinate tuples and a copied camera dictionary.

## API

```python
from human_eye_plugin.active_observation import prepare_scene
from human_eye_plugin.active_observation_images import ActiveObservationImages

session = prepare_scene(scene, cameras)
images = ActiveObservationImages(session, output_directory)
while session.next_view() is not None:
    frame = images.render_next()
    feedback = images.observe_frame(frame)
facts = session.short_facts()
```

`prepare_scene` parses complete geometry once, discovers with the accepted projected-area candidate and builds the static optimized coverage index. `diagnostics=True` adds phase clocks and aggregate counts. Default execution has no per-face work dictionaries, bit-length scans or counter updates.

`session.index` contains predicted complete-visibility masks and classifications. `session.state` commits actual observed coverage. `session.next_view()` begins at SCENE and then chooses the largest predicted uncovered gain from remaining views in their fixed order.

The image adapter constructs complete MeshEntity3D arrays from `session.objects` and uses all objects in one RGB/depth/owner raster. Canonical region corners and front drive readability. PNG and NPZ references include source and camera identities. Feedback verifies the PNG colour against actual RGB, NPZ contents against supplied in-process buffers, valid common depth/owner arrays, and the existing 16 surface / 4 boundary / RGB24 criteria before state submission.

Frame reads can replay explicitly historical files. Replay provenance is a caller-level designation and is recorded separately in this qualification. A new actual observation is recorded only after a fresh raster call. The reference string describes local core validation.

`session.summary()` returns observed views, covered ROI IDs, unresolved ROI IDs and finite-pool uncovered ROI IDs. `session.short_facts()` additionally supplies object names, ROI statuses and reasons, image references and scalar pixel evidence. Full triangle-index arrays remain in geometry and frame diagnostics.

Repeated reads reuse the existing state and current frame. `session.rebind(scene, cameras)` rebuilds from the new supplied source and applies the existing identity-based state invalidation. Changed scene or camera identities reset coverage. The image adapter also checks owner ordering and camera contents when deciding whether a frame can be reused.

## Evidence and deployment

The stable entry points are normal installed package imports. Product modules use static product imports and explicit data flow. The existing runtime source manifest automatically includes the two new modules. One controlled-loader qualification binds execution witnesses to the installed wheel source bytes.

This batch qualifies the isolated wheel and its installed API. Host collection, MCP exposure, Hook routing and formal default-install activation are separate deployment steps. Their concrete input binding is described in `NEXT_HOST_CONTRACT.md`.

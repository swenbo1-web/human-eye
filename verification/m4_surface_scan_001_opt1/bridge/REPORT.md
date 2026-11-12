# OPT1 bridge dependency handoff

## Implemented boundary

The plan SHA-256 was independently read as `2a8d8072175985c037e39a6662ee1ed158566b1cfcfc1ebeeccc00b4f4145541`. This child connection returned unbound Agent Learning context, host epoch 5. No context handle was borrowed and no task write was attributed to a different chat.

Changes are confined to `scene_residency.py`, `blender_mcp_host.py` and `blender_process.py`. The Blender host, worker, wire schema and ordinary decoded capture shape retain their existing definitions.

`SceneDeltaDecoder` constructs `SurfaceScanDependencies` only after a complete successful scan delta decode. Both connectors expose `surface_scan_dependencies(capture)`. The getter accepts the exact most-recent decoded payload, checks its captured state, scope and host identities, and takes the private token out of the decoder. The token exposes a read-only `objects` mapping and `matches_capture(payload)` for reducer verification. Its construction requires the module's private authority object. JSON scene fields cannot construct this Python token.

The token holds the current packet by reference until service/reducer processing ends. The measurement layer extracts immutable object tuples and retains no token or packet. The decoder releases its reference when the getter succeeds. Geometry arrays have no new permanent store. The per-resource admission map follows the decoder's existing live resource set. The object-token mapping is limited to the current scan's 256 objects.

## Per-object dependencies

| Field | Existing evidence | Changes that invalidate reuse |
| --- | --- | --- |
| Host source SHA | Scan binding checked against the connector and service's loaded implementation | Host code identity changes |
| Decoder owner | Private UUID of the current decoder | A new connection/decoder |
| Host instance and epoch | Validated M2 capture state | Host restart, reload or epoch reset |
| Document epoch | Current and full host identity agreement | Document identity change |
| Object incarnation | Union identity matched to the full identity | Same-name replacement or different object instance |
| Resource ID and revision | Delta reference resolved to the decoder's resource store | Local geometry/resource revision changes |
| Resource admission serial | Private serial assigned on resource admission/replacement | Removed live resource subsequently reappears, even under the same ID/revision |
| Matrix and scale | The exact binding used to reconstruct this object's world coordinates | Pose or unit changes, including distinct IEEE signed zero |

The tuple order is host source, decoder owner, host instance, host epoch, document epoch, object incarnation, resource ID, resource revision, admission serial, matrix and scale. Runtime source and solver/numerical parameters are added by the kernel measurement namespace.

Changing labels alone preserves geometry dependencies. Current object names continue to come from the fresh directory. Object-pair order remains the kernel's responsibility.

## Resource-version consistency

A scan packet that resends an existing resource ID and revision must preserve its exact resource content. Contradictory same-version content is rejected before publishing a new decoder baseline, world map, admission serial or private token. Resource comparison distinguishes signed zero. A duplicate identical version retains its admission serial.

Generic delta decoding retains its prior replacement behavior. Any generic incoming resource is conservatively assigned a new admission serial, so a later scan cannot use a result from superseded geometry. Live-resource trimming also removes the admission serial. Reintroducing the same resource ID/revision obtains a fresh serial.

Plain captures, missing scan identity, unrelated protocols and unknown bindings provide no token. They use the existing measurement path. No general task or solid cache key was widened.

## Tests and remaining evidence

Fourteen new directed tests pass. They cover typed/immutable metadata, packet identity, changed source metadata, ordinary JSON forgery, static reuse, one-object pose change, unchanged face-count geometry edits, same-version conflicts, signed-zero conflicts, duplicate retransmission, resource removal/reappearance, generic replacement compatibility, host/document/incarnation/unit resets, rename and both host getters.

One test traverses the complete ordinary tool chain using the existing native API double and actual delta codec, Process connector, getter, LiveSpatialService and kernel. Three planes produce three cold computations, zero repeat computations, then two new computations plus one unaffected hit after moving one plane. All edited public world witnesses and distances match the current plane positions.

The final suite combines those fourteen tests with forty-one relevant existing host/delta tests. The first legacy run named a nonexistent `verification.test_scene_residency` module, producing one preparation error. Its log remains in `LEGACY_01.txt`. The corrected suite uses actual repository modules. No Blender or main-asset performance process was launched by this child.

The plan's original transport-wait and conditional hidden-source limitations remain recorded. This bridge change introduces no transport redesign, geometry algorithm or image/model execution. Full installed two-host and fixed paired performance acceptance remain with the parent task.

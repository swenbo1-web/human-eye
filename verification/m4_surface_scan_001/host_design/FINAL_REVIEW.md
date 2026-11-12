# Frozen candidate host compatibility review

Candidate commit `c6355a01a4c6ee204a0d676cd9309f02428fe3ba` has source aggregate `b3654f6f943c3fb6feff0011397c0a8c20872e41f35973e6baf53e3a5e277314`. This review compared its product diff with the 137-source baseline commit `ea70339772159e5f0279784ebe18b1bf16e70439` and read the existing `unit_final_82.log`. It performed read-only source and Git inspection. It launched no product, mock suite, Blender, engineering sequence, image request, evaluation consumer or paid API and changed no product or frozen input.

## Material remaining issues

### Parent deadline does not bound every transport wait

The new scan caps and forwards the original absolute host deadline, checks before host work, checks host publication and rejects a successful response received after expiration. These boundaries prevent a late successful scan result. Existing unit checks establish argument forwarding and post-decode rejection.

The transport wait itself has an inherited gap.

- `BlenderMCPHost._exchange()` constructs its connection/send/read deadline from `time.monotonic() + self.timeout_s`. It receives only the payload. A parent deadline shorter than `timeout_s` does not shorten a stalled connection, blocked send or absent response wait. The connector eventually rejects expiration or returns an error, but it can do so later than the parent's allowed wait.
- `BlenderProcessHost._request()` creates `stop_ns` only for `apply` with `forward_deadline`. A scan supplies a relative timeout to response-queue waiting. Request encoding, baseline encoding and synchronous pipe write/flush do not consume that queue-wait allowance. A blocked pipe write has no scan deadline protection. The existing deadline-bound writer implementation is available to reuse.

This behavior predates scan in the nearest acquisition route. The candidate carries the limitation into its new route. It concerns bounded failure latency and cancellation responsiveness. It does not establish a false completed measurement or authorize a setter. The source-level limitation was reported to the parent before writing this review. Current mock results cannot establish an end-to-end hard wait limit.

A narrow subsequent change can give the scan's existing transport request the original absolute deadline. MCP should derive a remaining monotonic transport allowance once and share it across connection, send and response. Process should reuse its existing absolute-stop writer and queue waiting. Late decode and publication checks remain necessary. Delayed connection/send/read and blocked-pipe counterexamples should verify the change. Any product change requires a new candidate source freeze and corresponding engineering records.

### Hidden fallback has two untested conservative exits

The default hidden path exercised by the current tests returns an unevaluated original from `evaluated_get`, passes the full independent static guard, reads original triangle storage and matrix, and records `static_original_hidden`.

Two conditional code paths have different outcomes.

1. `evaluated_get(graph)` executes before the hidden fallback decision. If it raises `RuntimeError`, the directory marks the source unsupported. A `ReferenceError` escapes that directory catch. Neither path attempts the already-guarded original storage fallback.
2. The hidden fallback reads `getattr(obj, 'bound_box', ())` while constructing its adapter. A bound-box getter `RuntimeError` causes unsupported-source handling. The ordinary evaluated path catches that getter error and retains valid source geometry with unknown bounds.

This review does not assert that the fixed Blender scene triggers either API behavior. They are concrete untested code branches. The second branch is inconsistent with the intended valid-source/unknown-bounds rule. Both preserve conservative results. The affected pairs become unknown or the request fails, with no false complete scan. The parent was notified to correlate these paths with the actual hidden and excluded-view-layer checks before deciding on a subsequent narrow fix.

## Existing behavior compatibility

- `_objects()` retains its old default complete-scene checks, including 1..256 meshes, evaluated-instance rejection, unsupported geometry rejection and full `object_names` coverage. Only the explicit scan keyword opens 0..256 scene meshes.
- `_capture()` retains the old evaluated/to-mesh/triangulation path when no prepared local array is supplied. Its new prepared-local path is supplied only by scan. Native evidence and ordinary snapshots continue to refuse unavailable evaluation, including hidden original fallback cases.
- `_resource_stamp()` extracts the previous M2 resource stamp without changing its data-incarnation, geometry-dirty, dynamic-frame or guard dependencies. Scan resources use the same immutable local geometry and pose mechanism. A subsequent legacy capture still checks evaluation availability before resource reuse.
- The nearest directory refactor retains the same static-source restrictions, evaluated requirement, bounds calculation and witness qualification. Its additional instancer guard is already enforced by the preceding legacy `_objects()` check. The resident selected-acquisition cache token uses the explicit capture scope in place of the previous private literal. The token structure and published scene scope remain compatible. Existing nearest and resident tests passed in the recorded suite.
- No-handlers scan mode does not reuse source qualification, resources, capture-state tokens or whole-packet caches. It reads current static storage each time. Its empty union stays confined to the scan scope. The original no-handlers legacy fresh-read tests passed.
- Resident scan state includes the scene instancer flags and evaluated-instance presence. The fast cache checks current scope issues, full identity and host source binding. The scan scene revision also binds directory digest, scope issues and full identity. Warm instance transition cases with and without handlers passed in the recorded suite.
- The source-check metadata is cleared on residency reset and trimmed against live identities. Geometry/data incarnation and dirty stamps invalidate local eligibility. Pose and name updates retain the local rational summary. Previously excluded source entry reads its local arrays once and does not requalify unchanged geometry.

## Delta and request lifecycle review

The shared delta codec is unchanged. MCP and Process add scan to their existing nested-capture producer and decoder sets. The worker removes the internal baseline before validating the scan's exact public argument set and applies the existing codec after acquisition. Empty candidate unions are legal. Older non-delta connections use a complete plain packet. Native evidence and action commands have no new baseline behavior.

The host serializes its complete logical packet for the cold document-size check. Warm reuse adjusts the established size by the changed work subsection. Delta transport still has its own outer response-size limit. An outer encoding overrun fails the transport and cannot turn an oversized packet into successful evidence.

No product setter was added. The fixed worker keeps scan within its read-only command set and excludes it from the dedicated material-only worker. MCP observation transactions admit the fixed scan command while retaining the existing action restrictions.

## Shared source and service checks

The changed existing modules use opt-in arguments or explicit scan dispatch. The geometry normalizer accepts empty captures only under `_surface_scan_capture`. Pair-cache `before_compute` is optional and defaults to its previous behavior. ReadContext's `cache_partial` defaults to its previous behavior. Schema threshold widening is paired with a non-scan conditional restoring the existing positive/0.01 limit.

The service now validates the scan packet on every request, including result-cache hits. Its selection key binds query, full packet binding and scope issues. The kernel receives the prevalidated tuple on a compute path. This closes the cross-review issue in which unchanged endpoint geometry could otherwise reuse an obsolete complete result after a directory or scope change. The final service and kernel unit results are recorded separately by their owning agents.

## Conclusion

The recorded 82-test suite supports the inspected compatibility paths. Actual Blender behavior, isolated installation and five independent cold/repeat/edit sequences are being executed under the parent's frozen candidate. This offline review adds no performance or real-host acceptance claim. The transport wait limitation remains material to a hard end-to-end deadline claim. The hidden conditional paths remain conservative coverage and error-handling limitations pending real-host correlation.

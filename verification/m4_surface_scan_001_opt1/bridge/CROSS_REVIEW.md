# OPT1 frozen kernel and service review

## Scope and evidence

This review read candidate `c1cb2da32034e056a270384e691a2cde8dddbc0d`, runtime source aggregate `c4832b1a1ced9438f904e25a431e2327c2d7532e2f4efbb34e34ce58a7ed1943`. It inspected the committed versions of `scene_cache.py`, `task_query.py`, `surface_scan.py`, `live_service.py` and `read_context.py`, plus the new kernel test source and saved test records. Product files retained their frozen bytes. The review performed source and Git inspection only.

The parent supplied a saved 224-test passing combination. The kernel's own final record contains 18 new tests and 104 related tests, 122 passing executions. This review read those records and their test definitions. Actual paired Blender measurements and installation acceptance remain with the parent.

## Current-source binding and consumption

The service checks its loaded source identity, obtains the current host packet, checks the request threshold and validates the entire packet before requesting private dependencies. It then binds the current query, packet binding and scope issues into the ReadContext selection. The source-qualified packet and dependency token remain in this synchronous request's local scope.

The reducer separately verifies source, endpoint union IDs, names, document epoch and object incarnation correspondence after normalization. `_bind_surface_scan_meshes` requires the exact opaque token class and `matches_capture` against the current packet. Missing tokens, ordinary dictionaries, copied packets, changed metadata and old packet tokens use the established fallback key. Current normalized mesh object identity gates each fast lookup.

The specialized map retains the current meshes and short digests. It extracts scalar dependencies and releases the request token when the service returns. Its references point to existing normalized geometry. Reset or a new selection invokes `_bind_read_meshes`, clearing the specialized map before a later reducer binding.

## Measurement-key sufficiency

Each object digest includes runtime source SHA and the bridge tuple containing host source SHA, decoder owner, host instance/epoch, document epoch, incarnation, resource ID/revision/admission, actual matrix and scale. Matrix and scale preserve IEEE signed zero. Runtime and solver parameters are covered at separate key layers.

The complete measurement key still contains algorithm version, all supplied numerical parameters, source, unit, coordinate frame, witness tolerance and exact-rank option. `focal` and `reference` retain their order. The surface solver consumes referenced vertex and triangle data. Its topology checks derive from those arrays, so current label, pivot, display color and local axes can remain outside this scan-only geometry key.

The current directory supplies public object names and pair IDs. Rename can reuse the same geometric result while refreshing the label. Same-name replacement changes incarnation and normally resource admission. Local coordinate or topology edits change the resource revision. Removal and reappearance change admission. Pose and unit changes alter their exact dependencies. New host, document, decoder or runtime namespaces invalidate the corresponding old keys.

The saved ordered-pair test verifies that reversing inputs obtains a distinct measurement key and preserves world witness orientation. The newly specialized keyword is passed by the scan reducer. Ordinary task and solid paths keep their previous call options and metadata representation.

## Coverage, unknown and progress

Current pair dispositions, bounds and full directory are validated on every service request. Measurement reuse occurs after that validation. Scope issues still determine the public unknown status. Unsupported objects enter the current unknown partition before measurement lookup. Cached valid distances therefore preserve current scope uncertainty and cannot independently mark the current scan complete.

The shared measurement store retains values only when `measurement_valid` is true. Exceptions and ordinary unknown measurements remain retryable. The reducer retains valid completed summaries in the existing current progress map. A changed fingerprint, directory or threshold resets that progress, and a changed ReadContext generation resets current selection state while preserving the existing measurement store. This provides the intended path for unaffected pairs to survive a local scene update.

Cache hits occur before the new-computation budget callback. New computation consumes the existing callback and request checkpoint. Low-cap continuation preserves its unmeasured work and can use hits without charging additional kernel work. The saved unknown recovery, scope-change and low-cap tests match those control-flow conditions.

## Capacity and accounting

The implementation uses the existing `_measurements` OrderedDict, serialization, charge calculation and `_trim` path. ReadContext remains configured for 2 MiB and 256 measurement slots. New object keys remain short digests with the same accounted key length. Stored results continue through the same payload accounting and LRU eviction.

The saved tests include real eviction under the default 256 slots, eviction under two slots, and refusal to retain an oversized result under a 1024-byte budget. They compare maintained byte counters to independent recounts. New object metadata and existing geometry references are separately bounded by the current 256-object scan selection. Process RSS accounting remains a separate measured quantity.

## Conclusion and boundary

The reviewed data flow supports the proposed unaffected-pair reuse while preserving current coverage, ordered witness semantics, fallback behavior and measurement-store limits. Source inspection and the available directed records support proceeding with the frozen candidate's installed paired acceptance.

The inherited transport-wait and conditional hidden-source limitations remain in scope documentation. This review adds source-level assurance for the OPT1 cache change. It supplies no additional Blender result, performance sample, model-consumer result or hard transport-failure latency measurement.

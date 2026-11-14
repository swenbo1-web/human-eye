# Versioned view reuse fixture

This adapter implements M4-VIEW-REUSE-001 in the new worktree. It copies the accepted Routed bridge, native tools and bootstrap before making the changes below. The historical adapter and its frozen fresh-render contract retain their original bytes. This fixture does not install a default desktop, MCP or Hook route.

## Public contract

The MCP server identifies itself as `capture-replay-view-reuse`, version `2`. Its common tool order remains execute_python, scene_data, render_views and read_images. The P variant additionally exposes active_observation.

The Python signature is `render_views(names, include_images=False, fresh=False)`. The MCP render_views tool accepts names, include_images and fresh. Default fresh is false. It reuses a complete current-bound frame, including a verified product frame carrying genuine raw triangle IDs. A missing frame causes one native construction. Explicit fresh constructs one new frame per distinct view in that request. Repeated names within one request reuse the first result, including an explicit fresh request.

Results contain ref, view, buffer_key, buffer_handle, latest_buffer_alias, cached, reuse_reason, new_raster_attempts, triangle_id_capability, owner_schema, owner_mapping_identity, owner_capabilities and triangle_id_scope. The handle and key are the stable frame ref. Both `buffers[ref]` and the latest `buffers[view]` alias point to the same loaded array dictionary and the same read-only arrays. Fresh updates the view alias and leaves old references bound to their original arrays and files.

The creation record retains its original status, costs and metadata. Cache annotations appear in request results and cache_requests only. A hit has zero new raster attempts and performs no PNG/NPZ publication. It does not refund an earlier construction. Include_images retains input multiplicity, so repeated refs can create repeated image blocks. Each actual encoding and delivery remains in the existing image and transport records.

## Product registration

The normal installed LiveSpatialService and its default v4 MCP projection remain the product entry. Full frame NPZ files are read once when a newly owned product frame is registered. Their actual triangle_ids, patch_owners, object owners, depth, RGB and mapping metadata enter the same buffer table. No raw IDs are inferred from patch IDs. Product owner_schema and owner_mapping_identity are retained, while native frames identify their own global raw-owner schema.

Legacy product frames remain available as images. Their missing triangle_ids capability is explicit. A later default render_views request records raw_triangle_capability_missing, constructs one complete native frame and then reuses it. The active tool's original public JSON string still becomes last_observation_json only after successful socket delivery. The new array registration adds no array data to that string.

## Binding and invalidation

Cache checks use the existing frozen source identities, native mesh and source-face-array order/reference metadata, the complete small camera specification and the current owner schema/mapping generation. They perform no host capture, geometry collection or full-geometry hashing. Native meshes and their arrays are created through the original startup path. Product and native frames retain their actual creation pose and source metadata.

Supported camera pose or projection changes cause a miss and new construction. This versioned consumer keeps its registered six-camera, 512-by-512 domain. A different size is explicitly rejected with registered_512_camera_size_required before an old frame can be returned. The product itself retains its existing dynamic-size and rebind support, which is tested separately.

Changes to frozen scene/capture/camera/binding identities, object deletion/replacement/order, or source-face-array replacement require a fresh session. The request records source_or_object_order_changed_new_session_required and returns no stale hit. The adapter does not render old meshes under a changed source identity. Owner schema or mapping-generation changes invalidate cached matches. Old refs continue to address their original frames for explicit reading.

## Failure and accounting

Raster admission uses the original durable INTENT-before-call path. Each isolated testcase or paired variant has its own manifest-bound ledger. Per-owner actual-raster limit remains six. Container and phase limits come from that ledger's contract. A legacy value of 44 describes that container, and does not describe this batch's total construction cap.

Files, hashes, array metadata and the cache binding are prepared before publishing a complete cache entry. Native publication failure leaves a charged rendered attempt marked postprocess_failed and exposes no half-created buffer. A previous good reference remains valid. Product projection or image delivery failure leaves already completed product frames and construction costs intact. A later request may reuse a complete frame and retry image delivery, with encoding and delivery charged again.

cache_requests records completion, rejection or failure, requested names, fresh, returned frame facts, and the monotonic number of actual raster attempts. It is ordinary local bookkeeping alongside existing observations and transport records. It adds no new cache service or storage framework.

## Static integration boundary

The new bootstrap retains the accepted byte-exact binding and dependency setup. The candidate product source pin must be updated to the root-frozen new source digest before execution. The old isolated product remains read-only. The existing read audit additionally covers the actual old worktree and the new runtime root while retaining the explicitly public geometry/camera files and original three low-level product-source allowances.

No model, product observer, renderer or test was executed while authoring this fixture. Integration and bounded paired measurement are owned by the root and the dedicated harness author after source freeze.

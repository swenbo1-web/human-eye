# Source-region core R0

2026-11-17. Product code is ready for the root-owned first actual run. This worker started zero Blender processes and executed zero actual raster calls. Actual qualification remains pending in the root task.

## Product API

- `ordered_geometry_identity(capture, binding)` hashes the complete ordered host/instance/world-vertex/triangle arrays once per fresh capture. The service includes that digest in its current ReadContext selection.
- `prepare_region(capture, query, check_budget, _binding=..., _ordered_geometry_sha256=..., _validated_region_ref=...)` owns the complete parsed scene, immutable shared world mesh arrays, compact selected mesh, explicit source reverse maps and fixed camera pool. Its preparation stages separate source validation, geometry normalization, region-array construction and camera construction.
- `validate_region_ref(...)` checks the schema and region digest, document epoch, host object, object incarnation, capture generation, ordered complete geometry and canonical source-face set. The service validates a returned reference against every fresh capture before reusing preparation.
- `observe_region(prepared, directory, include_image=...)` constructs one SCENE frame through `SceneObservationImages`, with the complete scene supplied to rasterization. Empty rectangular patch sets keep full RGB/depth/object-owner/global-triangle-owner arrays. A repeated same-state call reuses the validated PNG/NPZ and their metadata. Returned dictionaries are detached from retained observations.
- `measure_region(prepared, reference, cache, check_budget, diagnostics)` invokes existing `measure_surface_proximity` and `_surface_proximity_fact` on the compact selected triangle union and the complete reference mesh. Its result contains the reference object, region reference, nearest points/direction and source mapping.

The region reference contains `schema`, `region_id`, `document_epoch`, `host_id`, `instance_id`, `capture_generation`, `ordered_geometry_sha256` and sorted `source_triangle_indices`. `region_id` is `source-region:` followed by the existing fingerprint of the other seven fields. Changing only the reference selector retains this region identity.

The source domain is current evaluated capture object-local triangle and vertex rows. The fixture's original-polygon correspondence is independently checked by the fixture worker. `source_mapping` records compact-to-source triangle/vertex indices and both compact and source triangle vertex triplets.

The M3 addition exposes its existing exact integer-frame `witness_points` through the private `_prepared_holder`. The holder already retained the exact preparation pair and coordinate map. Exact closed-triangle membership produces every valid source-face row, including shared-edge and duplicate-face ties. Public M3 results and arithmetic retain their existing implementation. The runtime source count becomes 143 through the new `source_region.py` module.

Actual sampled visibility lists visible and unseen selected source-face rows, selected pixel count, pixel bounds, frame identity and image reference. `complete_witness` remains null and complete surface visibility remains unknown. Measurement includes the entire selected source union.

## Offline evidence

The first raw run is preserved at `runs/R0_01`. Seven new core tests passed. Two historical R0 cross-scale assertions expected eight/six raster constructions, while the accepted R1 implementation produces three/one. The remaining original image and current cross-scale checks passed.

`runs/BASELINE_LEGACY_GUARDED_01` reruns those two assertions against the isolated accepted installation at `D:/he_m4_cross_scale_001/R1/product`. The original 142-source manifest and verified-source loader bind the imported product. Both assertions produce the same failures. Evidence includes actual module paths, hashes, complete `sys.path` and a successful source-guard verification. `runs/BASELINE_LEGACY_01` preserves the preceding unguarded comparison and its narrower provenance. Its four synthetic PNG publications were uninstrumented.

The current runner separately lists those two historical assertions and runs the other 54 checks. The new seven checks cover selected/whole distance controls, both references, compact reverse mappings, self-contained reference round-trip, fresh invalidation reasons and restored generation, invalid input, full-scene ownership, repeated frame reuse, a scene and target with zero rectangular regions, exact shared-edge/duplicate-face ties and text-only measurement. Every real raster entry in this suite is guarded to raise.

`runs/R0_02` passed all 54 current checks. It recorded 53 synthetic PNG encoding/publication calls taking 53,685,000 ns in aggregate. `runs/R0_01` recorded 57 calls taking 58,055,300 ns. The guarded baseline comparison recorded four calls taking 13,799,700 ns. These are synthetic test publication costs. They are separate from root-owned actual image and delivery accounting.

The first shell preflight found the Windows Python alias unusable. A second preflight used Blender's standalone Python 3.13 against Python 3.12 NumPy extensions and failed import. Subsequent checks used `D:/he_anchor_001/venv/Scripts/python.exe`, Python 3.12.14. These attempts started zero Blender processes, executed zero raster calls and encoded zero images.

The shared frame extraction and private M3 addition preserve original LF file encoding. Final-byte verification at `runs/R0_FINAL` passed 54 checks, with 53 synthetic PNG calls taking 52,254,000 ns. Its source pins bind the current source-region, shared-frame and M3 files. Product work stops here until the root freezes actual R0 results and identifies a permitted optimization candidate.

# M2 directory measurement contract

The three assets and the selected query are fixed before any candidate product edit. The old product is the existing isolated `9.7.2+sg.r1` installation, commit `00b13060a3cbe709b38f6e98ce04a6e5c3dabfb4`, canonical 137-source SHA `4ebc3910652ee461d9fa7476c8df0ecf6312580d6a02e1066c0eac88bef5c76c`.

## Inputs and requests

`assets_01/INPUTS.json` contains actual source-file SHA values and a separately enumerated evaluated-vertex oracle. It includes three boxes, the unchanged peripheral asset with 14 objects / 3474 vertices / 6146 polygons, and a rotated asymmetric tetrahedron control whose tight range differs from the transformed local eight-corner enclosure. Each scene has at least three mesh objects, preventing the legacy overview from automatically choosing a unique second object.

The old request is `human_eye_scene_observe`, explicit `include_image=false`, session `m2-tight-directory`, and query `{"mode":"overview","native_visual":{"mode":"projection"}}`. The new request changes that query to `{"mode":"directory"}`. Complete original replies and wire bytes are retained. A common value projection extracts all object IDs, names, tight bounds and their centers for correctness comparison. Its encoding is separate from actual public response bytes.

The frozen second step uses query `{"mode":"task","objects":[{"name":"M4_Focal"},{"name":"M4_Near"}],"requested_facts":["aabb","axis_gap","surface_proximity"]}`, with the same session and explicit no-image setting. These two names are fixed across all inputs. All three lanes make this same normal product selected request after their directory request. Native may use an optimized directory implementation and retained same-generation aggregates. Product bootstrap first required by the selected request remains charged to that step.

## Fixed samples

Pure directory measurements comprise 27 fresh owned background sessions. For each input, repetition one runs old/new/native, repetition two native/old/new, and repetition three new/native/old. Each session issues exactly one application-cold directory request and ten unchanged warm requests. Application-cold describes resident source/resource state, without claiming OS cache eviction. No selected query enters these 27 sessions.

Nine additional independent sessions each issue directory immediately followed by the frozen selected query, one session per input and lane. Both intervals and the continuous combined interval are recorded. Cold and warm samples remain separate, with nearest-rank p95. Setup, metadata, source bootstrap, request verification and close are individually recorded and retained in the complete session lifetime. They are never summed over overlapping nested intervals.

`baseline_01` is a pre-implementation old-path work confirmation with one cold and one warm peripheral request. It is excluded from the final paired performance samples. The original baseline scripts and replies are retained. Remaining native/controller adapters can be completed after this pre-record; they cannot change the assets, query, sample counts, order or gates.

## Measurement and fairness

The ordinary installed product stdio `Peer` and the original formal owned NativeSession lifecycle are reused. A documented socket wrapper retains the actual request/response UTF-8 bytes in memory and publishes them during worker shutdown, outside the request intervals. Its overhead applies to every lane. No profiler is installed. First source-establishment bytes remain within their actual request total and are reported separately when identifiable.

Existing residency counters and resource arrays are read before and after each actual host RPC. Array materialization counts identify real stored vertices, triangles and edges, with the existing to_mesh / triangulation / transform / hit counters. They do not claim to measure every loop iteration. Missing counters and unavailable process memory remain unknown. Tool receipt time, actual stdio bytes, bridge request bytes, bridge response bytes, and bridge sum are separate quantities. Product request-trace lifetime peak memory is labeled with its actual scope.

The native lane permits NumPy foreach_get, equivalent generation invalidation and cached directory summaries. It returns the same semantic object facts and uses the same source assets and selected task. It does not return all vertices as its directory response. Native code is a thin offline QA implementation inside the existing owned worker, with no daemon. Native-faster cells are reported without omission.

## Frozen gates and limits

All facts and freshness must pass independent source checks. The actual directory path must avoid plugin triangle/edge construction and full mesh transmission, retaining source generation semantics. Peripheral cold response bytes must fall by at least 50 percent, and three cold complete-tool median times by at least 10 percent. Thirty simple-control warm requests must have p95 increase no greater than `max(1 ms, old p95 * 0.05)`. Two-step costs and native comparisons are always reported. These gates remain fixed after measurement.

The batch uses owned copies/background Blender only, with zero models, images, GUI mutations, default activation or original-file saves. Preparation errors are preserved and may receive a deterministic fix. Final paired performance is one fixed matrix, without performance retries. Source changes or substantive fact mismatches stop execution. Actual runtime PID exit proof is retained when available and otherwise explicitly unknown.

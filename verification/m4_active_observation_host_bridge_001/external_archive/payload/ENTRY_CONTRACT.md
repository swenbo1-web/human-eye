# Active observation entry contract

The existing human_eye_scene_observe tool accepts query={"mode":"active_observation"}. The mode uses a complete world-metre evaluated Blender capture and the registered six-view 512px camera pool. include_image defaults to true. With include_image=false it returns prediction and unknown scope with no image construction or observed coverage.

The service confirms the actual source on every request. Its existing ReadContext stores serializable completed facts and frame references keyed by document epoch, capture revision/state, complete-scene scope, units, ordered host IDs/instances/names and fixed camera policy. Cold computation adds the full generated camera specification and geometry identity. A name-only change creates new source-bound image references despite equal geometry.

All captured objects participate in the common raster. Supported regions are whole-object connected, hole-free exact planar rectangles. Objects without a supported region are listed as unknown scope. An empty supported set returns no_supported_regions and performs no raster.

One capture mapping, one exact geometry parse and one shared mesh-array conversion feed camera fitting, coverage preparation and image feedback. The cold service target is one complete capture and one parse. The hot target is one real source-confirming capture with zero prepare and zero new raster.

PNG construction is charged before the actual raster. Local validation, MCP content construction and actual local consumer receipt have separate records. Native PNG data appears only in MCP image blocks. The explicit mode allows up to six 512px images while other existing image limits retain their original scope. Encoding failure retains cached completed geometry/image facts and charged construction.

The fixed private QA source is the archived 16-segment fixture scaled exactly by 375/256 before temporary Blender object creation. This is a new QA fixture with identity object matrices and metre scale 1.0. Its 5730 coordinates are binary32-exact. Runtime source conversion preserves the actual captured values.

The finite request list is frozen in EXECUTION_PLAN.json and HARNESS_PROTOCOL.json. Expected new rasters are ordinary 2, repeated 0, renamed 2 and nonplanar 0. The global hard cap is 8, including failed construction. No new model, Google/API inference or paired benchmark is part of this batch.

The trusted stdio harness records three wrappers. It saves the full object returned by the original capture call, saves the index returned by the original parsed-prepare alias, and durably records each pre-raster event. Each original callable runs once and its actual object is returned. Evidence writes and extra direct-core comparison costs are listed separately from product work.

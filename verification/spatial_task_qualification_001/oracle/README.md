# Independent qualification source and certificates

`verify_actual.py` uses the pinned original SCALE-DIAG oracle and never imports a production solver. Its pure `bind_actual(snapshot)` function can run immediately after the formal native QA export and before the three fixed business requests. It reads the fixed source files, writes nothing, and raises ValueError for a concrete source mismatch.

The actual snapshot must contain `unit`, `coordinate_frame`, `frame`, `subframe`, `scale_length` and `objects`. Each object carries `name`, `name_full`, `library_path`, `object_id`, `logical_id`, `matrix_world`, `vertices_local`, `vertices_world`, `triangles` and `source_polygon_count`. World coordinates use the frozen Python binary64 expression `(sum(matrix[r][c] * p[c] for c in range(3)) + matrix[r][3]) * scale_length` over the actual evaluated mesh. Object IDs retain the existing Blender name/library digest.

Binding checks all 14 objects. The original 12 retain the exact frozen local and world coordinates, matrix and oriented triangles. A bijective reindex is accepted only with unchanged coordinate values and oriented triangle multiset, with full current-to-frozen vertex and triangle mappings in the result. A one-ulp coordinate or pose change is rejected. No tolerance is applied to this source comparison. Controls bind to the exact generated two closed cubes. Unit, frame, subframe and all object identities bind to the frozen build snapshot.

The complete independent certificate replay is a separate saved-only command, run once after the formal snapshot is available.

```powershell
& 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe' -I -B verification/spatial_task_qualification_001/oracle/verify_actual.py --snapshot '<formal actual snapshot path>' --output verification/spatial_task_qualification_001/oracle/formal_replay_01
```

The output must be a new direct child of `oracle`. It contains complete ORACLE.json and RESULTS.json, including source hashes, timing and every exception. The CLI replays only Target with Peer_000, Competing_001 and Near_003 using exact support lower bounds, rational barycentric witnesses on actual triangles, and the original closed-prism embedding proof. The unchanged tolerance is 1e-6 m. Replayed intervals must also overlap the frozen intervals. The nearest conclusion applies to these three candidates.

Control separation uses exact X support planes at 11 m and 12 m, together with rational barycentric witnesses for `(11,0,0)` and `(12,0,0)` on the actual triangles. Each control closed shell is independently qualified using the original prism proof, giving a 1 m lower and upper bound.

`build_replay_01` passes on the fresh build's evaluated snapshot. It establishes the independent answer before the formal session. The formal current-source binding remains pending until the actual snapshot is supplied. `binding_checks_01` is an eight-case synthetic source-contract regression, including legal reindexing, exact mismatch reasons and unchanged input checks. Its checks do not increase the business task denominator.

One background process built the derived asset and exited normally. The original G508 asset is unchanged. Assets remain synthetic engineering fixtures reused from the SCALE-DIAG family. The files here make no model-performance or cross-task-generalization claim.

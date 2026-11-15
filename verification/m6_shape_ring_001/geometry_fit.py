"""Generate the two fixed observation-only height residuals for all348 cases."""

import time
BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()

import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ring_geometry import FAILURE_CODES, bfs_ten_hops, free_vertex_areas, full_topology, make_frame, measure, process_resources, robust_quadratic


def write(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                             encoding="utf8", newline="\n")


def file_record(path):
    path = Path(path)
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def distribution(values):
    values = np.asarray(values)
    finite = values[np.isfinite(values)]
    return {"count": len(values), "finite_count": len(finite), "nonfinite_count": len(values) - len(finite),
            "min": float(finite.min()) if len(finite) else None,
            "median": float(np.median(finite)) if len(finite) else None,
            "p95": float(np.quantile(finite, .95)) if len(finite) else None,
            "max": float(finite.max()) if len(finite) else None}


def main():
    started, cpu = time.perf_counter(), time.process_time()
    if (HERE / "RESIDUALS.json").exists():
        raise RuntimeError("residual_report_exists_inspect_before_retry")
    for row in json.loads((HERE / "PLAN_FREEZE.json").read_bytes())["files"]:
        if file_record(HERE / row["path"])["sha256"] != row["sha256"]:
            raise ValueError("frozen_plan_identity_changed_" + row["path"])
    timings, used = {}, {}

    def old_file(path, expected=None):
        path = Path(path)
        record = file_record(path)
        if expected is not None and record["sha256"] != expected:
            raise ValueError("old_file_identity_changed_" + str(path))
        used[str(path)] = record
        return path

    with measure(timings, "whitelist_read"):
        whitelist = json.loads((HERE / "INPUT_WHITELIST.json").read_bytes())
        cases = sorted(whitelist["cases"], key=lambda row: row["id"])
        if len(cases) != 348 or len({row["id"] for row in cases}) != 348:
            raise ValueError("fixed348_case_selection_required")
        if sum(row["normal_control"] for row in cases) != 42:
            raise ValueError("fixed42_normal_controls_required")
        if any("Bunny" in row["source"] for row in cases):
            raise ValueError("reserved_Bunny_arrays_locked")
    write("RESIDUALS_STARTED.json", {"cycle_id": "M6-SHAPE-RING-001", "requested_cases": 348,
          "source_sha256": {name: file_record(HERE / name)["sha256"] for name in ("geometry_fit.py", "ring_geometry.py")}})
    sources, patches = {}, {}
    for row in cases:
        source_name = row["source"]
        if source_name not in sources:
            with measure(timings, "source_snapshot_read_and_hash"):
                snapshot = row["snapshot"]
                path = old_file(snapshot["path"], snapshot.get("sha256", snapshot.get("sha")))
                with np.load(path, allow_pickle=False) as saved:
                    vertices = saved["vertices"].astype(np.float64)
                    triangles = saved["triangles"].astype(np.int64)
                if not np.isfinite(vertices).all():
                    raise ValueError("nonfinite_current_source_snapshot")
            with measure(timings, "complete_source_topology"):
                topology = full_topology(triangles, len(vertices))
            sources[source_name] = {"vertices": vertices, "triangles": triangles, "topology": topology,
                                    "query_ids": set(), "snapshot": file_record(path)}
        if row["patch_id"] not in patches:
            with measure(timings, "patch_domain_and_incident_topology"):
                mapping_path = old_file(row["mapping_path"])
                graph_path = old_file(row["graph_path"])
                with np.load(mapping_path, allow_pickle=False) as saved:
                    context = saved["context_source_ids"].astype(np.int64)
                with np.load(graph_path, allow_pickle=False) as saved:
                    free = saved["free_mask"].astype(bool)
                free_context = np.flatnonzero(free)
                order = np.argsort(context[free_context])
                free_context = free_context[order]
                free_source = context[free_context]
                source = sources[source_name]
                lookup = np.full(len(source["vertices"]), -1, dtype=np.int64)
                lookup[free_source] = np.arange(len(free_source))
                edges = source["topology"]["edges"]
                local_edges = lookup[edges]
                local_edges = local_edges[np.all(local_edges >= 0, axis=1)]
                incident = np.flatnonzero(np.any(lookup[source["triangles"]] >= 0, axis=1))
                patch = {"source": source_name, "context_source_ids": context, "free_context_ids": free_context,
                         "free_source_ids": free_source, "free_edge_index": local_edges.T,
                         "incident_source_triangle_ids": incident}
                sources[source_name]["query_ids"].update(free_source.tolist())
                patches[row["patch_id"]] = patch
    topology_records = []
    for source_name, source in sources.items():
        with measure(timings, "BFS10_unique_source_queries"):
            query_ids = np.asarray(sorted(source.pop("query_ids")), dtype=np.int64)
            neighbor_lists, hop_lists = [], []
            for source_id in query_ids:
                neighbors, hops = bfs_ten_hops(source["topology"]["indptr"], source["topology"]["indices"], source_id)
                neighbor_lists.append(neighbors)
                hop_lists.append(hops)
            lengths = np.asarray([len(values) for values in neighbor_lists], dtype=np.int64)
            offsets = np.concatenate((np.zeros(1, dtype=np.int64), np.cumsum(lengths)))
            neighbors = np.concatenate(neighbor_lists) if neighbor_lists else np.empty(0, dtype=np.int64)
            hops = np.concatenate(hop_lists) if hop_lists else np.empty(0, dtype=np.uint8)
            source.update(query_source_ids=query_ids, neighbor_offsets=offsets,
                          neighbor_source_ids=neighbors, neighbor_hops=hops)
        with measure(timings, "topology_cache_save_and_hash"):
            path = HERE / "private/topology" / (source_name + ".npz")
            path.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(path, query_source_ids=query_ids, neighbor_offsets=offsets,
                                neighbor_source_ids=neighbors, neighbor_hops=hops, **source["topology"])
            source["cache_record"] = file_record(path)
            topology_records.append({"source": source_name, **source["cache_record"],
                                     "full_source_vertices": len(source["vertices"]), "full_source_triangles": len(source["triangles"]),
                                     "unique_BFS_queries": len(query_ids), "neighbor_count": distribution(lengths),
                                     "BFS_array_bytes": query_ids.nbytes + offsets.nbytes + neighbors.nbytes + hops.nbytes,
                                     "adjacency_array_bytes": sum(value.nbytes for value in source["topology"].values())})
        del neighbor_lists, hop_lists
    for patch_id, patch in patches.items():
        source = sources[patch["source"]]
        patch["cache_query_rows"] = np.searchsorted(source["query_source_ids"], patch["free_source_ids"])
        with measure(timings, "patch_topology_cache_save_and_hash"):
            path = HERE / "private/topology/patches" / (patch_id + ".npz")
            path.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(path, **{name: value for name, value in patch.items() if isinstance(value, np.ndarray)})
            patch["cache_record"] = file_record(path)
    report = {"cycle_id": "M6-SHAPE-RING-001", "status": "running", "requested_cases": 348,
              "cases": [], "failures": [], "timings": timings, "topology": topology_records,
              "topology_patch_count": len(patches), "source_count": len(sources),
              "BFS_unique_queries": sum(row["unique_BFS_queries"] for row in topology_records),
              "BFS_cache_array_bytes": sum(row["BFS_array_bytes"] for row in topology_records),
              "adjacency_array_bytes": sum(row["adjacency_array_bytes"] for row in topology_records),
              "failure_codes": FAILURE_CODES, "training": 0, "model_forwards": 0, "repair_candidates": 0,
              "Bunny_arrays": 0, "input_label_reference_or_generation_fields_read": 0,
              "frame_convention": "columns[t1,t2,n], n=unit(float64 observed saved normal), t1=unit(cross(n,least-absolute-dot xyz axis)), t2=cross(n,t1)",
              "fit_scope": "all hop1-10 versus hop6-10, common current full hop1-10 maximum Euclidean R, no sampling",
              "source_sha256": {name: file_record(HERE / name)["sha256"] for name in ("geometry_fit.py", "ring_geometry.py")}}
    for row in cases:
        case_started, case_cpu = time.perf_counter(), time.process_time()
        case_timings = {}
        source, patch = sources[row["source"]], patches[row["patch_id"]]
        with measure(case_timings, "current_observation_and_normal_read"):
            observed_path = old_file(row["observed"]["path"], row["observed"].get("sha256", row["observed"].get("sha")))
            input_path = old_file(row["input"]["path"], row["input"].get("sha256", row["input"].get("sha")))
            observed = np.load(observed_path, allow_pickle=False)
            with np.load(input_path, allow_pickle=False) as saved:
                observed_normals = saved["normals"].astype(np.float64)
                ell = float(saved["scale_m"])
            if not np.isfinite(ell) or ell <= 0 or observed.shape != (len(patch["context_source_ids"]), 3):
                raise ValueError("invalid_saved_current_observation_or_scale")
        with measure(case_timings, "full_current_source_construction"):
            current = source["vertices"].copy()
            current[patch["context_source_ids"]] = observed
            normals = observed_normals[patch["free_context_ids"]]
        with measure(case_timings, "current_complete_F_incident_vertex_area"):
            area, area_counts = free_vertex_areas(current, source["triangles"], patch["incident_source_triangle_ids"], patch["free_source_ids"])
            if area_counts["nonfinite_area_incident_triangles"]:
                raise ValueError("nonfinite_current_F_vertex_area")
        count = len(patch["free_source_ids"])
        arrays = {"free_source_ids": patch["free_source_ids"], "free_context_ids": patch["free_context_ids"],
                  "context_source_ids": patch["context_source_ids"], "free_edge_index": patch["free_edge_index"],
                  "query_positions": current[patch["free_source_ids"]], "normal_unit": np.zeros((count, 3)),
                  "normal_valid": np.zeros(count, dtype=bool), "frame_basis": np.zeros((count, 3, 3)),
                  "area": area, "ell": np.asarray(ell), "R": np.zeros(count),
                  "cache_query_rows": patch["cache_query_rows"]}
        for branch in ("solid", "ring"):
            arrays.update({branch + "_r": np.zeros(count), branch + "_valid": np.zeros(count, dtype=bool),
                           branch + "_failure_code": np.zeros(count, dtype=np.int8),
                           branch + "_point_count": np.zeros(count, dtype=np.int64),
                           branch + "_rank": np.zeros(count, dtype=np.int64),
                           branch + "_condition": np.full(count, np.nan), branch + "_coefficients": np.zeros((count, 6)),
                           branch + "_rank_trace": np.zeros((count, 4), dtype=np.int64),
                           branch + "_condition_trace": np.full((count, 4), np.nan),
                           branch + "_completed_fits": np.zeros(count, dtype=np.int8)})
        for local_id, source_id in enumerate(patch["free_source_ids"]):
            with measure(case_timings, "shared_neighborhood_frame_R_coordinates"):
                cache_row = patch["cache_query_rows"][local_id]
                start, end = source["neighbor_offsets"][cache_row:cache_row + 2]
                neighbors = source["neighbor_source_ids"][start:end]
                hops = source["neighbor_hops"][start:end]
                relative = current[neighbors] - current[source_id]
                radius = float(np.linalg.norm(relative, axis=1).max()) if len(relative) else 0.0
                basis, normal_valid = make_frame(normals[local_id])
                arrays["frame_basis"][local_id] = basis
                arrays["normal_unit"][local_id] = basis[:, 2]
                arrays["normal_valid"][local_id] = normal_valid
                arrays["R"][local_id] = radius
                radius_valid = np.isfinite(radius) and radius > 0
                points = relative @ basis / radius if radius_valid and normal_valid else None
            for branch, selection in (("solid", np.ones(len(neighbors), dtype=bool)), ("ring", hops >= 6)):
                arrays[branch + "_point_count"][local_id] = np.count_nonzero(selection)
                if not normal_valid:
                    arrays[branch + "_failure_code"][local_id] = 1
                    continue
                if not radius_valid:
                    arrays[branch + "_failure_code"][local_id] = 2
                    continue
                with measure(case_timings, branch + "_robust_quadratic_fit"):
                    fitted = robust_quadratic(points[selection])
                for field in ("valid", "failure_code", "rank", "coefficients", "rank_trace", "condition_trace", "completed_fits"):
                    arrays[branch + "_" + field][local_id] = fitted[field]
                arrays[branch + "_condition"][local_id] = fitted["condition"] if fitted["condition"] is not None else np.nan
                if fitted["valid"]:
                    residual = fitted["height"] * radius
                    if np.isfinite(residual):
                        arrays[branch + "_r"][local_id] = residual
                    else:
                        arrays[branch + "_valid"][local_id] = False
                        arrays[branch + "_failure_code"][local_id] = 8
        with measure(case_timings, "residual_array_save_and_hash"):
            patch_id, sample = row["id"].split("/")
            path = HERE / "private/residuals" / patch_id / (sample + ".npz")
            path.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(path, **arrays)
            record = file_record(path)
        result = {key: row[key] for key in ("id", "patch_id", "source", "purpose", "normal_control", "position_group")}
        result.update(**record, ell=ell, free_vertices=count, full_source_vertices=len(current),
                      topology_cache=source["cache_record"], patch_topology_cache=patch["cache_record"],
                      normal_invalid_points=int(np.count_nonzero(~arrays["normal_valid"])),
                      R_over_ell=distribution(arrays["R"] / ell), area_counts=area_counts,
                      timings=case_timings, body_wall_s=time.perf_counter() - case_started,
                      body_CPU_s=time.process_time() - case_cpu)
        for branch in ("solid", "ring"):
            result[branch] = {"available_points": int(np.count_nonzero(arrays[branch + "_valid"])),
                              "unavailable_points": int(np.count_nonzero(~arrays[branch + "_valid"])),
                              "failure_counts": {reason: int(np.count_nonzero(arrays[branch + "_failure_code"] == code))
                                                 for code, reason in FAILURE_CODES.items()},
                              "point_count": distribution(arrays[branch + "_point_count"]),
                              "condition": distribution(arrays[branch + "_condition"])}
        report["cases"].append(result)
        for stage, values in case_timings.items():
            target = timings.setdefault(stage, {"wall_s": 0.0, "CPU_s": 0.0, "calls": 0})
            for key in target:
                target[key] += values[key]
        report["input_file_identities"] = list(used.values())
        report["wall_s_before_report_write"] = time.perf_counter() - started
        report["CPU_s_before_report_write"] = time.process_time() - cpu
        report["resources_before_report_write"] = process_resources()
        with measure(timings, "progress_report_serialization_and_write"):
            write("RESIDUALS.json", report)
        print(json.dumps({"case": row["id"], "free": count,
                          "solid_unavailable": result["solid"]["unavailable_points"],
                          "ring_unavailable": result["ring"]["unavailable_points"]}), flush=True)
    report.update(status="completed_all348_fixed_residuals", case_count=len(report["cases"]),
                  free_point_observations=sum(row["free_vertices"] for row in report["cases"]),
                  bootstrap_wall_s_before_final_write=time.perf_counter() - BOOT_WALL,
                  bootstrap_CPU_s_before_final_write=time.process_time() - BOOT_CPU,
                  measurement_scope="imports and stages included before serialization/write/exit, enclosing worker-tree ledger records lifecycle; cache counted once per source/query")
    write("RESIDUALS.json", report)


if __name__ == "__main__":
    main()

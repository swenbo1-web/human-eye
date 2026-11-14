"""Freeze public-source patches, generate bounded dents, and verify saved data."""
import time

PROCESS_WALL_START = time.perf_counter()
PROCESS_CPU_START = time.process_time()

import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

from collections import Counter, deque
import ctypes
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import sys
import tarfile
import traceback

import numpy as np

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "m6_shape_data_001"
PRIVATE = HERE / "private/public_data"
sys.path.insert(0, str(OLD))
from features import observe, prepare_topology
from geometry import boundary_ids, components, graph, normals, quality, shortest
from prepare_patches import order_candidates, precheck
from generate import hop_statistics

INPUT_KEYS = {"node_features", "edge_features", "positions", "normals", "origin_world_m", "scale_m", "feature_names"}
PLY_TYPES = {"char": "b", "int8": "b", "uchar": "B", "uint8": "B", "short": "h", "int16": "h",
             "ushort": "H", "uint16": "H", "int": "i", "int32": "i", "uint": "I", "uint32": "I",
             "float": "f", "float32": "f", "double": "d", "float64": "d"}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def record(path):
    path = Path(path)
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def peak_rss():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    process = ctypes.windll.kernel32.GetCurrentProcess
    process.restype = ctypes.c_void_p
    query = ctypes.windll.psapi.GetProcessMemoryInfo
    query.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    if not query(process(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return int(counters.PeakWorkingSetSize)


def ply_header(stream):
    assert stream.readline().strip() == b"ply"
    elements, header = [], ["ply"]
    while True:
        line = stream.readline().decode("ascii").strip()
        assert line, "unexpected_ply_header_eof"
        header.append(line)
        parts = line.split()
        if parts[0] == "end_header":
            break
        if parts[0] == "format":
            encoding = parts[1]
        elif parts[0] == "element":
            elements.append({"name": parts[1], "count": int(parts[2]), "properties": []})
        elif parts[0] == "property":
            elements[-1]["properties"].append(parts[1:])
    return encoding, elements, "\n".join(header)


def read_ply(path):
    """Consume each declared scalar/list in order, including face intensity."""
    vertices, faces = [], []
    with Path(path).open("rb") as stream:
        encoding, elements, header = ply_header(stream)
        endian = ">" if encoding == "binary_big_endian" else "<"
        for element in elements:
            for _ in range(element["count"]):
                values = {}
                tokens = iter(stream.readline().split()) if encoding == "ascii" else None
                for prop in element["properties"]:
                    if prop[0] == "list":
                        if tokens is not None:
                            count = int(next(tokens))
                            value = [int(next(tokens)) for _ in range(count)]
                        else:
                            count_type = endian + PLY_TYPES[prop[1]]
                            count = struct.unpack(count_type, stream.read(struct.calcsize(count_type)))[0]
                            value_type = endian + PLY_TYPES[prop[2]] * count
                            value = struct.unpack(value_type, stream.read(struct.calcsize(value_type)))
                        values[prop[-1]] = value
                    elif tokens is not None:
                        values[prop[-1]] = float(next(tokens))
                    else:
                        scalar_type = endian + PLY_TYPES[prop[0]]
                        values[prop[-1]] = struct.unpack(scalar_type, stream.read(struct.calcsize(scalar_type)))[0]
                if element["name"] == "vertex":
                    vertices.append([values[key] for key in ("x", "y", "z")])
                elif element["name"] == "face":
                    ids = values["vertex_indices"]
                    assert len(ids) == 3, "nontriangular_source_face"
                    faces.append(ids)
        assert not stream.read().strip(), "unexpected_trailing_ply_data"
    return np.asarray(vertices, dtype=np.float64), np.asarray(faces, dtype=np.int64), header


def independent_ply(path, name):
    """Use vectorized fixed records to cross-check the generic property parser."""
    with Path(path).open("rb") as stream:
        encoding, elements, _ = ply_header(stream)
        vertex_count, face_count = elements[0]["count"], elements[1]["count"]
        if name == "Stanford_Armadillo":
            assert encoding == "binary_big_endian"
            vertices = np.frombuffer(stream.read(vertex_count * 12), dtype=">f4").reshape(-1, 3).astype(np.float64)
            dtype = np.dtype([("intensity", "u1"), ("count", "u1"), ("ids", ">i4", (3,))])
            faces = np.frombuffer(stream.read(face_count * dtype.itemsize), dtype=dtype)
            assert np.all(faces["count"] == 3)
            triangles = faces["ids"].astype(np.int64)
        else:
            assert encoding == "ascii"
            vertices = np.asarray([[float(value) for value in stream.readline().split()] for _ in range(vertex_count)])[:, :3]
            rows = np.asarray([[int(value) for value in stream.readline().split()] for _ in range(face_count)])
            assert np.all(rows[:, 0] == 3)
            triangles = rows[:, 1:]
        assert not stream.read().strip()
    return vertices, triangles


def freeze_sources(plan):
    preflight = json.loads((HERE / "PUBLIC_SOURCE_PREFLIGHT.json").read_bytes())
    sources = {"cycle_id": plan["cycle_id"], "catalog_url": preflight["catalog_url"], "usage": preflight["usage"],
               "source_purposes_frozen_first": True, "sources": []}
    for item in preflight["sources"]:
        name = item["name"]
        folder = PRIVATE / "sources" / name
        folder.mkdir(parents=True, exist_ok=False)
        copied = {}
        for field in ("archive", "ply"):
            original = item[field]
            assert record(original["path"]) == original, "prefetched_source_hash_mismatch"
            destination = folder / Path(original["path"]).name
            shutil.copyfile(original["path"], destination)
            copied[field] = record(destination)
            assert all(copied[field][key] == original[key] for key in ("bytes", "sha256"))
        if item["archive_member"]:
            with tarfile.open(copied["archive"]["path"], "r:gz") as archive:
                archive_data = archive.extractfile(item["archive_member"]).read()
        else:
            with gzip.open(copied["archive"]["path"], "rb") as archive:
                archive_data = archive.read()
        assert hashlib.sha256(archive_data).hexdigest() == copied["ply"]["sha256"]
        vertices, triangles, header = read_ply(copied["ply"]["path"])
        independent_vertices, independent_triangles = independent_ply(copied["ply"]["path"], name)
        assert np.array_equal(vertices, independent_vertices) and np.array_equal(triangles, independent_triangles)
        expected = (172974, 345944) if name == "Stanford_Armadillo" else (35947, 69451)
        assert (len(vertices), len(triangles)) == expected
        assert np.isfinite(vertices).all() and triangles.min() >= 0 and triangles.max() < len(vertices)
        assert np.all(np.diff(np.sort(triangles, axis=1), axis=1) > 0)
        snapshot = folder / "snapshot.npz"
        np.savez_compressed(snapshot, vertices=vertices, triangles=triangles, source_polygon_ids=np.arange(len(triangles), dtype=np.int64))
        row = {"name": name, "purpose": item["purpose"], "source_group": "public_" + name,
               "url": item["url"], "archive_member": item["archive_member"], **copied,
               "snapshot": record(snapshot), "header": header, "vertices": len(vertices), "triangles": len(triangles),
               "unit": "native", "physical_unit_established": False, "coordinates_preserved": True,
               "independent_ply_readback_exact": True, "archive_member_exact": True,
               "attribution": "Stanford Computer Graphics Laboratory / Stanford 3D Scanning Repository"}
        sources["sources"].append(row)
        print(json.dumps({"source": name, "vertices": len(vertices), "triangles": len(triangles), "status": "source_frozen"}), flush=True)
    write(HERE / "PUBLIC_SOURCES.json", sources)
    return sources


def offcenter_check(vertices, triangles, unit, patch, seed):
    _, inside, _ = boundary_ids(triangles, patch["allowed"])
    _, _, _, adjacency = graph(vertices, inside)
    distances = shortest(adjacency, [seed], allowed=set(patch["allowed"].tolist()))
    depth = min(distances[int(index)] for index in patch["boundary"])
    counts, cosines = [], []
    boundary = set(patch["boundary"].tolist())
    for ratio, minimum in ((.35, 3), (.55, 7)):
        support = [index for index, distance in distances.items() if distance < ratio * depth and index not in boundary]
        if len(support) < minimum:
            return None, "insufficient_nonzero_dent_support"
        cosine = float((unit[support] @ unit[seed]).min())
        if cosine <= 0:
            return None, "support_normals_do_not_define_one_inward_direction"
        counts.append(len(support))
        cosines.append(cosine)
    return {"center_vertex_id": seed, "distance_to_boundary_native": depth, "center_normal": unit[seed].tolist(),
            "support_counts_r35_r55": counts, "support_normal_cosine_min_r35_r55": cosines}, None


def freeze_patches(plan, sources):
    selection = {"cycle_id": plan["cycle_id"], "candidate_orders": [], "candidate_checks": [], "patches": [],
                 "offcenter_candidate_orders": [], "offcenter_candidate_checks": [], "overlaps": [], "source_summary": []}
    for source in sources["sources"]:
        with np.load(source["snapshot"]["path"], allow_pickle=False) as data:
            vertices, triangles, polygons = data["vertices"], data["triangles"], data["source_polygon_ids"]
        name = source["name"]
        edges, edge_counts, _, adjacency = graph(vertices, triangles)
        unit, _, magnitude, coherence = normals(vertices, triangles)
        component, sizes = components(adjacency)
        bad = np.unique(np.concatenate((triangles[magnitude == 0].ravel(), edges[edge_counts > 2].ravel())))
        eligible = (sizes[component] >= 512) & (coherence >= .5)
        eligible[bad] = False
        curvature, variation = np.zeros(len(vertices)), np.zeros(len(vertices))
        for index, neighbors in enumerate(adjacency):
            if neighbors:
                ids = [neighbor for neighbor, _ in neighbors]
                average = np.mean([length for _, length in neighbors])
                if average > 0:
                    curvature[index] = float((vertices[ids] - vertices[index]).mean(axis=0) @ unit[index]) / average
                variation[index] = float(np.mean(1 - np.clip(unit[ids] @ unit[index], -1, 1)))
        boundary_hops = np.full(len(vertices), -1, dtype=np.int64)
        queue = deque(int(index) for index in np.unique(edges[edge_counts == 1]))
        for index in queue:
            boundary_hops[index] = 0
        while queue:
            index = queue.popleft()
            for neighbor, _ in adjacency[index]:
                if boundary_hops[neighbor] < 0:
                    boundary_hops[neighbor] = boundary_hops[index] + 1
                    queue.append(neighbor)
        ids = np.flatnonzero(eligible)
        positive, negative = ids[curvature[ids] > .01], ids[curvature[ids] < -.01]
        concave = positive[curvature[positive] >= np.quantile(curvature[positive], .8)] if len(positive) else positive
        convex = negative[curvature[negative] <= np.quantile(curvature[negative], .2)] if len(negative) else negative
        strata = {"natural_concave": (concave, curvature), "natural_convex": (convex, -curvature),
                  "curvature_change": (ids[variation[ids] >= np.quantile(variation[ids], .8)], variation),
                  "source_boundary_near": (ids[(boundary_hops[ids] >= 3) & (boundary_hops[ids] <= 6)], boundary_hops)}
        selected, used = [], set()
        for category, (candidates, priority) in strata.items():
            order = order_candidates(vertices, candidates, priority, 24)
            selection["candidate_orders"].append({"source": name, "stratum": category, "eligible_candidates": len(candidates), "ordered_centers": order})
            accepted = 0
            for rank, seed in enumerate(order):
                if accepted >= 3:
                    break
                checked = {"source": name, "stratum": category, "candidate_rank": rank, "center_vertex_id": seed}
                if seed in used:
                    checked.update(accepted=False, reason="center_already_selected_by_earlier_stratum")
                    selection["candidate_checks"].append(checked)
                    continue
                patch, reason = precheck(vertices, triangles, adjacency, unit, seed, 384)
                if patch is None:
                    checked.update(accepted=False, reason=reason)
                    selection["candidate_checks"].append(checked)
                    continue
                patch_id = f"{name}_patch_{len(selected):02d}"
                folder = PRIVATE / "patches" / patch_id
                folder.mkdir(parents=True, exist_ok=False)
                shared = patch["shared"]
                np.savez_compressed(folder / "graph.npz", **{key: shared[key] for key in ("edge_index", "allowed_mask", "boundary_mask", "free_mask")})
                np.savez_compressed(folder / "mapping.npz", context_source_ids=shared["context_ids"], allowed_source_ids=patch["allowed"],
                                    boundary_source_ids=patch["boundary"], context_source_face_ids=patch["context_face_ids"],
                                    context_triangles=patch["context_triangles"], source_polygon_ids=polygons[patch["context_face_ids"]],
                                    incident_source_face_ids=patch["closure"])
                np.save(folder / "reference_local.npy", vertices[shared["context_ids"]], allow_pickle=False)
                row = {"id": patch_id, "source": name, "source_group": source["source_group"], "purpose": source["purpose"],
                       "stratum": category, "center_vertex_id": seed, "candidate_rank": rank, "unit": "native",
                       "allowed_vertices": 384, "boundary_vertices": len(patch["boundary"]), "free_vertices": int(shared["free_mask"].sum()),
                       "context_vertices": len(shared["context_ids"]), "context_faces": len(patch["context_face_ids"]),
                       "incident_faces": len(patch["closure"]), "distance_to_boundary_native": patch["distance_to_boundary_m"],
                       "support_counts_r35_r55": patch["support_counts"], "support_normal_cosine_min_r35_r55": patch["support_normal_cosine_min"],
                       "center_normal": patch["center_normal"].tolist(), "signed_curvature_proxy": float(curvature[seed]),
                       "normal_variation_proxy": float(variation[seed]), "source_boundary_distance_hops": int(boundary_hops[seed]),
                       "component_vertices": int(sizes[component[seed]]), "private_directory": str(folder),
                       "graph": record(folder / "graph.npz"), "mapping": record(folder / "mapping.npz"),
                       "reference": record(folder / "reference_local.npy")}
                _, inside, _ = boundary_ids(triangles, patch["allowed"])
                _, _, _, induced = graph(vertices, inside)
                allowed_set = set(patch["allowed"].tolist())
                center_distances = shortest(induced, [seed], allowed=allowed_set)
                boundary_distances = shortest(induced, patch["boundary"].tolist(), allowed=allowed_set)
                depth = row["distance_to_boundary_native"]
                free = allowed_set - set(patch["boundary"].tolist())
                offorder = sorted((index for index in free if .25 * depth <= center_distances[index] <= .5 * depth
                                   and boundary_distances[index] >= .6 * depth), key=lambda index: (-center_distances[index], index))
                selection["offcenter_candidate_orders"].append({"patch_id": patch_id, "ordered_centers": offorder,
                      "center_distances_native": [center_distances[index] for index in offorder],
                      "boundary_distances_native": [boundary_distances[index] for index in offorder]})
                row["offcenter"] = None
                for offrank, offseed in enumerate(offorder):
                    result, reason = offcenter_check(vertices, triangles, unit, patch, offseed)
                    selection["offcenter_candidate_checks"].append({"patch_id": patch_id, "candidate_rank": offrank,
                          "center_vertex_id": offseed, "accepted": result is not None, "reason": reason or "support_precheck_passed"})
                    if result is not None:
                        row["offcenter"] = {**result, "candidate_rank": offrank, "offset_native": center_distances[offseed],
                                            "distance_to_original_boundary_native": boundary_distances[offseed]}
                        break
                row["offcenter_missing_reason"] = None if row["offcenter"] else "no_eligible_candidate_passed_original_support_rules"
                selected.append((row, allowed_set))
                selection["patches"].append(row)
                used.add(seed)
                accepted += 1
                checked.update(accepted=True, patch_id=patch_id, reason="source_only_precheck_passed")
                selection["candidate_checks"].append(checked)
        for index, (first, first_ids) in enumerate(selected):
            for second, second_ids in selected[index + 1:]:
                overlap = len(first_ids & second_ids)
                selection["overlaps"].append({"patches": [first["id"], second["id"]], "shared_allowed_vertices": overlap,
                                              "jaccard": overlap / len(first_ids | second_ids), "same_group": True})
        summary = {"source": name, "purpose": source["purpose"], "eligible_vertices": len(ids), "selected_patches": len(selected),
                   "offcenter_patches": sum(row["offcenter"] is not None for row, _ in selected),
                   "by_stratum": {category: sum(row["stratum"] == category for row, _ in selected) for category in strata},
                   "source_boundary_vertices": int(len(np.unique(edges[edge_counts == 1]))),
                   "source_vertices_excluded_by_components_below512": int(np.count_nonzero(sizes[component] < 512)),
                   "source_degenerate_faces": int(np.count_nonzero(magnitude == 0)), "source_nonmanifold_edges": int(np.count_nonzero(edge_counts > 2))}
        selection["source_summary"].append(summary)
        print(json.dumps(summary), flush=True)
        if len(selected) < 3:
            selection["status"] = "blocked_source_below_three_patches"
            write(HERE / "PUBLIC_PATCH_SELECTION.json", selection)
            raise RuntimeError("source_below_three_patches_" + name)
    selection.update(status="frozen_for_generation", patches_count=len(selection["patches"]),
                     maximum_observations=sum(7 + 6 * (patch["offcenter"] is not None) for patch in selection["patches"]))
    write(HERE / "PUBLIC_PATCH_SELECTION.json", selection)
    return selection


def error_statistics(delta, mask, mean_edge):
    length = np.linalg.norm(delta[mask], axis=1)
    if not len(length):
        return {"count": 0, "rmse_native": None, "p95_native": None, "max_native": None, "rmse_over_mean_edge": None}
    rmse = float(np.sqrt(np.mean(length * length)))
    return {"count": len(length), "rmse_native": rmse, "p95_native": float(np.quantile(length, .95)),
            "max_native": float(length.max()), "rmse_over_mean_edge": rmse / mean_edge}


def generate(sources, selection):
    dataset = {"cycle_id": "M6-SHAPE-TRAIN-001", "cases": [], "unit": "native_per_source", "training_calls": 0,
               "model_scoring_calls": 0, "mls_calls": 0, "input_legacy_unit_keys": "origin_world_m and scale_m contain native coordinate units for compatibility",
               "label_legacy_unit_keys": "target_world_m contains native coordinate displacement for compatibility",
               "frozen_selection": record(HERE / "PUBLIC_PATCH_SELECTION.json"), "timings": Counter()}
    for source in sources["sources"]:
        mesh = dict(np.load(source["snapshot"]["path"], allow_pickle=False))
        reference, triangles = mesh["vertices"], mesh["triangles"]
        for patch in (row for row in selection["patches"] if row["source"] == source["name"]):
            started = time.perf_counter()
            folder = Path(patch["private_directory"])
            mapping = dict(np.load(folder / "mapping.npz", allow_pickle=False))
            context, allowed = mapping["context_source_ids"], mapping["allowed_source_ids"]
            boundary, inside, _ = boundary_ids(triangles, allowed)
            edges, _, lengths, adjacency = graph(reference, inside)
            mean_edge = float(lengths.mean())
            shared = prepare_topology(triangles, len(reference), allowed)
            free = set(allowed.tolist()) - set(boundary.tolist())
            external = np.asarray(sorted(set(range(len(reference))) - free), dtype=np.int64)
            dataset["timings"]["topology_s"] += time.perf_counter() - started
            variants = [("center", patch, None, 0.)] + [("center", patch, radius, amplitude) for radius in (.35, .55) for amplitude in (.05, .15, .3)]
            if patch["offcenter"] is not None:
                variants += [("offcenter", patch["offcenter"], radius, amplitude) for radius in (.35, .55) for amplitude in (.05, .15, .3)]
            for subfolder in ("observed", "inputs", "labels"):
                (folder / subfolder).mkdir(exist_ok=False)
            distances_cache, hop_cache = {}, {}
            for ordinal, (position, center, radius_ratio, amplitude_ratio) in enumerate(variants):
                started = time.perf_counter()
                seed = center["center_vertex_id"]
                if seed not in distances_cache:
                    distances_cache[seed] = shortest(adjacency, [seed], allowed=set(allowed.tolist()))
                distances = distances_cache[seed]
                depth = min(distances[int(index)] for index in boundary)
                assert math.isclose(depth, center["distance_to_boundary_native"], rel_tol=1e-13, abs_tol=1e-15)
                normal = np.asarray(center["center_normal"])
                radius = None if radius_ratio is None else radius_ratio * depth
                amplitude = 0. if radius is None else amplitude_ratio * radius
                support = [] if radius is None else sorted(index for index in free if distances[index] < radius)
                observed = reference.copy()
                for index in support:
                    observed[index] -= amplitude * (1 - (distances[index] / radius) ** 2) ** 2 * normal
                assert np.array_equal(reference[external], observed[external])
                assert np.flatnonzero(np.any(reference != observed, axis=1)).tolist() == support
                delta = reference[context] - observed[context]
                damaged = np.isin(context, support)
                dataset["timings"]["damage_s"] += time.perf_counter() - started
                started = time.perf_counter()
                inputs = observe(observed, triangles, shared)
                assert set(inputs) == INPUT_KEYS
                target = (delta / float(inputs["scale_m"])).astype(np.float32)
                dataset["timings"]["observation_features_s"] += time.perf_counter() - started
                started = time.perf_counter()
                qc = quality(reference, observed, triangles[mapping["incident_source_face_ids"]])
                reasons = []
                if qc["degenerate_after"]:
                    reasons.append("degenerate_incident_triangle")
                if qc["normal_reversals"]:
                    reasons.append("incident_normal_reversal")
                if not np.isfinite(observed).all():
                    reasons.append("nonfinite_geometry")
                dataset["timings"]["quality_s"] += time.perf_counter() - started
                started = time.perf_counter()
                sample = f"sample_{ordinal:02d}"
                observed_path, input_path, labels_path = folder / "observed" / (sample + ".npy"), folder / "inputs" / (sample + ".npz"), folder / "labels" / (sample + ".npz")
                np.save(observed_path, observed[context], allow_pickle=False)
                np.savez_compressed(input_path, **inputs)
                np.savez_compressed(labels_path, target_normalized=target, target_world_m=delta, damaged_mask=damaged,
                                    normal_allowed_mask=shared["allowed_mask"] & ~damaged, normal_free_mask=shared["free_mask"] & ~damaged)
                dataset["timings"]["array_write_s"] += time.perf_counter() - started
                hop_key = (seed, radius_ratio)
                if hop_key not in hop_cache:
                    hop_cache[hop_key] = hop_statistics(shared["edge_index"], context, support, seed)
                masks = {"A": shared["allowed_mask"], "S": damaged, "N": shared["allowed_mask"] & ~damaged, "N_F": shared["free_mask"] & ~damaged}
                row = {"id": patch["id"] + "/" + sample, "sample_name": sample, "patch_id": patch["id"], "source": source["name"],
                       "source_group": source["source_group"], "purpose": source["purpose"], "stratum": patch["stratum"],
                       "position_group": position, "unit": "native", "normal_control": radius is None,
                       "accepted": not reasons, "rejection_reasons": reasons, "radius_ratio": radius_ratio, "amplitude_ratio": amplitude_ratio,
                       "radius_native": radius, "amplitude_native": amplitude, "center_vertex_id": seed,
                       "distance_to_boundary_native": depth, "mean_allowed_edge_native": mean_edge,
                       "allowed_vertices": len(allowed), "free_vertices": len(free), "context_vertices": len(context),
                       "damaged_vertices": len(support), "normal_allowed_vertices": len(allowed) - len(support),
                       "normal_free_vertices": len(free) - len(support), "boundary_vertices": len(boundary),
                       "damage_max_native": float(np.linalg.norm(delta, axis=1).max()), "observed_scale_native": float(inputs["scale_m"]),
                       "denominators": {key: int(mask.sum()) for key, mask in masks.items()},
                       "no_op_errors": {key: error_statistics(delta, mask, mean_edge) for key, mask in masks.items()},
                       "quality": qc, "boundary_external_bitwise_preserved": True, "hop_statistics": hop_cache[hop_key],
                       "observed": record(observed_path), "input": record(input_path), "labels": record(labels_path)}
                dataset["cases"].append(row)
            print(json.dumps({"patch": patch["id"], "generated_cases": len(variants)}), flush=True)
    dataset["source_counts"] = dict(Counter(case["source"] for case in dataset["cases"]))
    dataset["subsets"] = []
    for source in sources["sources"]:
        for position in ("center", "offcenter"):
            cases = [case for case in dataset["cases"] if case["source"] == source["name"] and case["position_group"] == position]
            dataset["subsets"].append({"source": source["name"], "purpose": source["purpose"], "position_group": position,
                      "observations": len(cases), "accepted": sum(case["accepted"] for case in cases), "rejected": sum(not case["accepted"] for case in cases),
                      "normal_controls": sum(case["normal_control"] for case in cases),
                      "point_denominators": {key: sum(case["denominators"][key] for case in cases) for key in ("A", "S", "N", "N_F")}})
    dataset.update(status="generated", attempted_observations=len(dataset["cases"]), accepted_observations=sum(case["accepted"] for case in dataset["cases"]),
                   rejected_observations=sum(not case["accepted"] for case in dataset["cases"]), normal_controls=sum(case["normal_control"] for case in dataset["cases"]))
    write(HERE / "PUBLIC_DATASET_INDEX.json", dataset)
    return dataset


def independent_distances(adjacency, starts):
    """Dense unvisited-min traversal independently checks the generation heap."""
    distances = dict.fromkeys(adjacency, math.inf)
    for seed in starts:
        distances[seed] = 0.
    unvisited = set(distances)
    while unvisited:
        index = min(unvisited, key=lambda vertex: (distances[vertex], vertex))
        unvisited.remove(index)
        for neighbor, length in adjacency[index]:
            distances[neighbor] = min(distances[neighbor], distances[index] + length)
    return distances


def verify():
    started, cpu = time.perf_counter(), time.process_time()
    report = {"cycle_id": "M6-SHAPE-TRAIN-001", "checks": [], "graph_statistics": [], "model_scoring_calls": 0, "mls_calls": 0,
              "label_formula_max_error_native": 0., "feature_roundtrips": 0, "source_mapping_checks": 0}
    def check(name, condition):
        report["checks"].append({"name": name, "passed": bool(condition)})
        if not condition:
            write(HERE / "PUBLIC_VERIFY.json", report)
            raise AssertionError(name)
    sources = json.loads((HERE / "PUBLIC_SOURCES.json").read_bytes())
    selection = json.loads((HERE / "PUBLIC_PATCH_SELECTION.json").read_bytes())
    dataset = json.loads((HERE / "PUBLIC_DATASET_INDEX.json").read_bytes())
    plan = json.loads((HERE / "PUBLIC_DATA_PLAN.json").read_bytes())
    for frozen in plan["reused_code"]:
        check("reused code " + Path(frozen["path"]).name, record(frozen["path"]) == frozen)
    check("data plan fixed source purposes", plan["source_purposes"] == {"Stanford_Armadillo": "validation", "Stanford_Bunny": "reserved_test"})
    check("frozen selection preserved", record(HERE / "PUBLIC_PATCH_SELECTION.json") == dataset["frozen_selection"])
    check("source uses", {row["name"]: row["purpose"] for row in sources["sources"]} == {"Stanford_Armadillo": "validation", "Stanford_Bunny": "reserved_test"})
    check("unique case ids", len({case["id"] for case in dataset["cases"]}) == len(dataset["cases"]))
    for source in sources["sources"]:
        for field in ("archive", "ply", "snapshot"):
            check(source["name"] + " hash " + field, record(source[field]["path"]) == source[field])
        mesh = dict(np.load(source["snapshot"]["path"], allow_pickle=False))
        reference, triangles = mesh["vertices"], mesh["triangles"]
        source_normals = normals(reference, triangles)[0]
        independent_vertices, independent_triangles = independent_ply(source["ply"]["path"], source["name"])
        check(source["name"] + " independent PLY readback", np.array_equal(reference, independent_vertices) and np.array_equal(triangles, independent_triangles))
        patches = [patch for patch in selection["patches"] if patch["source"] == source["name"]]
        check(source["name"] + " source patch bound", 3 <= len(patches) <= 12)
        for patch in patches:
            name = patch["id"]
            for field in ("graph", "mapping", "reference"):
                check(name + " hash " + field, record(patch[field]["path"]) == patch[field])
            mapping = dict(np.load(patch["mapping"]["path"], allow_pickle=False))
            saved_graph = dict(np.load(patch["graph"]["path"], allow_pickle=False))
            context, allowed = mapping["context_source_ids"], mapping["allowed_source_ids"]
            local_reference = np.load(patch["reference"]["path"], allow_pickle=False)
            check(name + " reference exact", np.array_equal(local_reference, reference[context]))
            allowed_set = set(allowed.tolist())
            inside = [face for face in triangles.tolist() if set(face).issubset(allowed_set)]
            edge_counts = Counter(tuple(sorted((face[index], face[(index + 1) % 3]))) for face in inside for index in range(3))
            boundary = sorted({index for edge, count in edge_counts.items() if count == 1 for index in edge})
            check(name + " independent boundary", np.array_equal(boundary, mapping["boundary_source_ids"]))
            adjacency = {int(index): [] for index in allowed}
            for first, second in edge_counts:
                distance = math.dist(reference[first].tolist(), reference[second].tolist())
                adjacency[first].append((second, distance))
                adjacency[second].append((first, distance))
            distance_cache, normal_cache = {}, {}
            for center in (patch, patch["offcenter"]):
                if center is None:
                    continue
                seed = center["center_vertex_id"]
                distances = independent_distances(adjacency, [seed])
                distance_cache[seed] = distances
                depth = min(distances[index] for index in boundary)
                check(name + " independent center distance " + str(seed), math.isclose(depth, center["distance_to_boundary_native"], rel_tol=1e-12, abs_tol=1e-15))
                center_faces = triangles[np.any(triangles == seed, axis=1)]
                normal = sum((np.cross(reference[face[1]] - reference[face[0]], reference[face[2]] - reference[face[0]]) for face in center_faces), np.zeros(3))
                normal /= np.linalg.norm(normal)
                normal_cache[seed] = normal
            center_distances = distance_cache[patch["center_vertex_id"]]
            boundary_distances = independent_distances(adjacency, boundary)
            depth = patch["distance_to_boundary_native"]
            free_ids = allowed_set - set(boundary)
            offorder = sorted((index for index in free_ids if .25 * depth <= center_distances[index] <= .5 * depth
                               and boundary_distances[index] >= .6 * depth), key=lambda index: (-center_distances[index], index))
            saved_order = next(row for row in selection["offcenter_candidate_orders"] if row["patch_id"] == name)
            check(name + " independent offcenter eligible order", offorder == saved_order["ordered_centers"])
            first_valid = None
            for offseed in offorder:
                distances = independent_distances(adjacency, [offseed])
                candidate_depth = min(distances[index] for index in boundary)
                supports = [[index for index in free_ids if distances[index] < ratio * candidate_depth] for ratio in (.35, .55)]
                valid = len(supports[0]) >= 3 and len(supports[1]) >= 7
                if valid:
                    valid = all(float((source_normals[support] @ source_normals[offseed]).min()) > 0 for support in supports)
                if valid:
                    first_valid = offseed
                    break
            selected_offcenter = None if patch["offcenter"] is None else patch["offcenter"]["center_vertex_id"]
            check(name + " independent first valid offcenter", selected_offcenter == first_valid)
            check(name + " source polygon mapping", np.array_equal(context[mapping["context_triangles"]], triangles[mapping["context_source_face_ids"]]) and np.array_equal(mapping["source_polygon_ids"], mesh["source_polygon_ids"][mapping["context_source_face_ids"]]))
            closure = np.flatnonzero(np.any(np.isin(triangles, allowed), axis=1))
            check(name + " incident closure", np.array_equal(closure, mapping["incident_source_face_ids"]))
            report["source_mapping_checks"] += 1
            shared = prepare_topology(triangles, len(reference), allowed)
            check(name + " graph exact and two-ring context", all(np.array_equal(saved_graph[key], shared[key]) for key in saved_graph) and np.array_equal(shared["context_ids"], context))
            local_adjacency = [[] for _ in context]
            for first, second in saved_graph["edge_index"].T:
                local_adjacency[first].append(int(second))
            def hops(starts):
                distances = np.full(len(context), -1, dtype=np.int64)
                queue = deque(starts)
                for index in queue:
                    distances[index] = 0
                while queue:
                    index = queue.popleft()
                    for neighbor in local_adjacency[index]:
                        if distances[neighbor] < 0:
                            distances[neighbor] = distances[index] + 1
                            queue.append(neighbor)
                return distances
            check(name + " graph connected", int(hops([0]).min()) == 0)
            graph_diameter = max(int(hops([index]).max()) for index in range(len(context)))
            fixed_hops = hops(np.flatnonzero(~saved_graph["free_mask"]).tolist())
            maximum_to_fixed = 0
            local = {int(source_id): index for index, source_id in enumerate(context)}
            cases = [case for case in dataset["cases"] if case["patch_id"] == name]
            check(name + " bounded cases and single control", len(cases) == 7 + 6 * (patch["offcenter"] is not None) and sum(case["normal_control"] for case in cases) == 1)
            for case in cases:
                case_name = case["id"]
                check(case_name + " sample name", case["sample_name"] == case_name.rsplit("/", 1)[1])
                for field in ("observed", "input", "labels"):
                    check(case_name + " hash " + field, record(case[field]["path"]) == case[field])
                observed_local = np.load(case["observed"]["path"], allow_pickle=False)
                inputs = dict(np.load(case["input"]["path"], allow_pickle=False))
                labels = dict(np.load(case["labels"]["path"], allow_pickle=False))
                seed = case["center_vertex_id"]
                distances = distance_cache[seed]
                depth = min(distances[index] for index in boundary)
                radius = None if case["normal_control"] else case["radius_ratio"] * depth
                support = [] if radius is None else [index for index in allowed if index not in boundary and distances[int(index)] < radius]
                damaged = np.isin(context, support)
                if damaged.any():
                    maximum_to_fixed = max(maximum_to_fixed, int(fixed_hops[damaged].max()))
                delta = local_reference - observed_local
                expected = np.zeros_like(delta)
                for index in support:
                    expected[local[int(index)]] = case["amplitude_ratio"] * radius * (1 - (distances[int(index)] / radius) ** 2) ** 2 * normal_cache[seed]
                max_error = float(np.max(np.abs(delta - expected)))
                report["label_formula_max_error_native"] = max(report["label_formula_max_error_native"], max_error)
                tolerance = max(float(np.max(np.abs(local_reference))) * np.finfo(float).eps * 8, 1e-16)
                check(case_name + " independent formula", np.allclose(delta, expected, rtol=1e-10, atol=tolerance))
                check(case_name + " complete inverse labels", np.array_equal(labels["target_world_m"], delta) and np.array_equal(labels["target_normalized"], (delta / float(inputs["scale_m"])).astype(np.float32)))
                masks = {"A": saved_graph["allowed_mask"], "S": damaged, "N": saved_graph["allowed_mask"] & ~damaged, "N_F": saved_graph["free_mask"] & ~damaged}
                check(case_name + " support masks denominators", np.array_equal(labels["damaged_mask"], damaged) and np.array_equal(labels["normal_allowed_mask"], masks["N"]) and np.array_equal(labels["normal_free_mask"], masks["N_F"]) and case["denominators"] == {key: int(mask.sum()) for key, mask in masks.items()} and masks["A"].sum() == 384)
                check(case_name + " unchanged fixed halo", np.array_equal(observed_local[~saved_graph["free_mask"]], local_reference[~saved_graph["free_mask"]]))
                check(case_name + " strict observation whitelist", set(inputs) == INPUT_KEYS and inputs["node_features"].shape == (len(context), 7) and inputs["edge_features"].shape == (saved_graph["edge_index"].shape[1], 4) and all(np.isfinite(inputs[key]).all() for key in INPUT_KEYS - {"feature_names"}))
                observed = reference.copy()
                observed[context] = observed_local
                subset = triangles[closure]
                before = np.cross(reference[subset[:, 1]] - reference[subset[:, 0]], reference[subset[:, 2]] - reference[subset[:, 0]])
                after = np.cross(observed[subset[:, 1]] - observed[subset[:, 0]], observed[subset[:, 2]] - observed[subset[:, 0]])
                bad = int(np.count_nonzero(np.linalg.norm(after, axis=1) == 0))
                flips = int(np.count_nonzero(np.einsum("ij,ij->i", before, after) < 0))
                check(case_name + " independent quality retention", bad == case["quality"]["degenerate_after"] and flips == case["quality"]["normal_reversals"] and case["accepted"] == (bad == flips == 0))
                check(case_name + " A/S/N/NF no-op statistics", all(math.isclose(case["no_op_errors"][key]["rmse_native"], math.sqrt(sum(float(value) ** 2 for value in np.linalg.norm(delta[mask], axis=1)) / int(mask.sum())), rel_tol=1e-12, abs_tol=1e-15) for key, mask in masks.items() if mask.any()))
                if case["normal_control"] or case_name.endswith("sample_06") or case_name.endswith("sample_12"):
                    recomputed = observe(observed, triangles, shared)
                    check(case_name + " observation readback", all(np.array_equal(inputs[key], recomputed[key]) for key in INPUT_KEYS))
                    report["feature_roundtrips"] += 1
            report["graph_statistics"].append({"patch_id": name, "input_vertices": len(context), "directed_edges": saved_graph["edge_index"].shape[1],
                     "input_graph_diameter_hops": graph_diameter, "damaged_to_fixed_halo_max_hops": maximum_to_fixed,
                     "damaged_to_clean_max_hops": max(case["hop_statistics"]["damaged_to_observed_clean_max_hops"] for case in cases),
                     "support_diameter_hops": max(case["hop_statistics"]["support_diameter_hops"] for case in cases)})
            print(name + " readback verified", flush=True)
        for overlap in (row for row in selection["overlaps"] if row["patches"][0].startswith(source["name"] + "_")):
            pair = [next(patch for patch in patches if patch["id"] == patch_id) for patch_id in overlap["patches"]]
            allowed_sets = [set(np.load(patch["mapping"]["path"], allow_pickle=False)["allowed_source_ids"].tolist()) for patch in pair]
            count = len(allowed_sets[0] & allowed_sets[1])
            check(" overlap " + " / ".join(overlap["patches"]), count == overlap["shared_allowed_vertices"] and math.isclose(count / len(allowed_sets[0] | allowed_sets[1]), overlap["jaccard"]))
    report.update(status="passed", assertion_count=len(report["checks"]), verified_observations=len(dataset["cases"]), verified_patches=len(selection["patches"]),
                  wall_s=time.perf_counter() - started, cpu_s=time.process_time() - cpu, process_peak_rss_bytes=peak_rss(),
                  scope="data format, geometry, generation formula and saved labels only")
    write(HERE / "PUBLIC_VERIFY.json", report)
    return report


def main():
    log_path = HERE / "PUBLIC_RUN_LOG.json"
    log = json.loads(log_path.read_bytes()) if log_path.exists() else {"events": []}
    event = {"operation": "verify" if "--verify" in sys.argv else "prepare_public", "status": "running"}
    log["events"].append(event)
    write(log_path, log)
    try:
        if "--verify" not in sys.argv:
            if (HERE / "PUBLIC_DATA_PLAN.json").exists():
                raise RuntimeError("existing_public_plan_inspect_before_retry")
            old_plan = json.loads((OLD / "DATA_PLAN.json").read_bytes())
            plan = {**old_plan, "cycle_id": "M6-SHAPE-TRAIN-001", "maximum_patches": 24, "maximum_observations": 312,
                    "source_grouping_file": "PUBLIC_SOURCES.json", "maximum_patches_per_source": 12,
                    "source_purposes": {"Stanford_Armadillo": "validation", "Stanford_Bunny": "reserved_test"},
                    "source_purposes_frozen_before_geometry": True, "source_unit": "native", "old_training_pool_reused_without_regeneration": True,
                    "offcenter_rule": "same allowed region; original-center distance [.25D,.5D], boundary distance >=.6D; descending center distance then ascending source ID; first candidate passing original support counts and orientation; recompute D; no extra control",
                    "reused_code": [record(OLD / name) for name in ("geometry.py", "features.py", "prepare_patches.py", "generate.py")],
                    "inputs_legacy_unit_names": "origin_world_m and scale_m retained as whitelist names; values are native source units",
                    "reserved_test_allowed_checks": "PLY, topology, generator formula, serialization; no model or MLS scoring"}
            write(HERE / "PUBLIC_DATA_PLAN.json", plan)
            sources = freeze_sources(plan)
            selection = freeze_patches(plan, sources)
            generate(sources, selection)
        report = verify()
        event.update(status="completed", verified_observations=report["verified_observations"], verified_patches=report["verified_patches"])
    except BaseException as error:
        event.update(status="failed", error=repr(error), traceback=traceback.format_exc())
        raise
    finally:
        event.update(whole_process_wall_s=time.perf_counter() - PROCESS_WALL_START,
                     whole_process_cpu_s=time.process_time() - PROCESS_CPU_START, process_peak_rss_bytes=peak_rss())
        write(log_path, log)
        print(json.dumps(event, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

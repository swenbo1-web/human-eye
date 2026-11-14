"""Freeze deterministic source-only patch choices before any damage is made."""
import json
from pathlib import Path
import sys
import time
from collections import deque

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from features import prepare_topology
from geometry import boundary_ids, components, graph, normals, shortest


def order_candidates(vertices, candidates, priority, maximum):
    if not len(candidates):
        return []
    chosen = []
    separation = np.full(len(candidates), np.inf)
    first = int(np.argmax(priority[candidates]))
    for step in range(min(maximum, len(candidates))):
        ordinal = first if step == 0 else int(np.argmax(separation))
        seed = int(candidates[ordinal])
        chosen.append(seed)
        separation = np.minimum(separation, np.sum((vertices[candidates] - vertices[seed]) ** 2, axis=1))
        separation[np.isin(candidates, chosen)] = -1
    return chosen


def precheck(vertices, triangles, adjacency, unit_normals, seed, allowed_count):
    distances = shortest(adjacency, [seed], limit=allowed_count)
    allowed = np.asarray(sorted(distances), dtype=np.int64)
    if len(allowed) != allowed_count:
        return None, "component_too_small"
    boundary, inside, counts = boundary_ids(triangles, allowed)
    closure = np.flatnonzero(np.any(np.isin(triangles, allowed), axis=1))
    if len(np.unique(inside)) != len(allowed) or np.any(counts > 2):
        return None, "induced_patch_dangling_or_nonmanifold"
    if seed in boundary or len(boundary) < 3 or len(allowed) - len(boundary) < 128:
        return None, "invalid_center_or_insufficient_free_interior"
    face_cross = np.cross(vertices[triangles[closure, 1]] - vertices[triangles[closure, 0]],
                          vertices[triangles[closure, 2]] - vertices[triangles[closure, 0]])
    if np.any(np.linalg.norm(face_cross, axis=1) == 0):
        return None, "degenerate_reference_incident_face"
    _, _, _, induced_adjacency = graph(vertices, inside)
    local_distances = shortest(induced_adjacency, [seed], allowed=set(allowed.tolist()))
    if len(local_distances) != len(allowed):
        return None, "induced_patch_not_connected"
    distance = min(local_distances[int(index)] for index in boundary)
    support_counts = []
    minimum_cosines = []
    boundary_set = set(boundary.tolist())
    for radius_ratio, minimum in ((.35, 3), (.55, 7)):
        support = [index for index, d in local_distances.items() if d < radius_ratio * distance and index not in boundary_set]
        if len(support) < minimum:
            return None, "insufficient_nonzero_dent_support"
        minimum_cosine = float((unit_normals[support] @ unit_normals[seed]).min())
        if minimum_cosine <= 0:
            return None, "support_normals_do_not_define_one_inward_direction"
        support_counts.append(len(support))
        minimum_cosines.append(minimum_cosine)
    shared = prepare_topology(triangles, len(vertices), allowed)
    context = shared["context_ids"]
    remap = np.full(len(vertices), -1, dtype=np.int64)
    remap[context] = np.arange(len(context))
    face_ids = np.flatnonzero(np.all(np.isin(triangles, context), axis=1))
    return {"allowed": allowed, "boundary": boundary, "closure": closure, "shared": shared,
            "distance_to_boundary_m": distance, "support_counts": support_counts,
            "support_normal_cosine_min": minimum_cosines, "context_face_ids": face_ids,
            "context_triangles": remap[triangles[face_ids]], "center_normal": unit_normals[seed]}, None


def main():
    started, cpu_started = time.perf_counter(), time.process_time()
    target = HERE / "PATCH_SELECTION.json"
    if target.exists():
        raise RuntimeError("patch_selection_already_exists_inspect_before_retry")
    plan = json.loads((HERE / "DATA_PLAN.json").read_bytes())
    audit = json.loads((HERE / "SOURCE_AUDIT.json").read_bytes())
    grouping = json.loads((HERE / "SOURCE_GROUPS.json").read_bytes())
    assert grouping["conservative_groups"] == 1 and not grouping["splits"]["validation"] and not grouping["splits"]["reserved_test"]
    selection = {"cycle_id": "M6-SHAPE-DATA-001", "source_groups_frozen_first": True,
                 "candidate_orders": [], "candidate_checks": [], "patches": [], "overlaps": [], "source_summary": []}
    for source in audit["sources"]:
        name = source["name"]
        with np.load(source["snapshot"]["path"], allow_pickle=False) as saved:
            vertices, triangles, polygon_ids = saved["vertices"], saved["triangles"], saved["source_polygon_ids"]
        edges, counts, lengths, adjacency = graph(vertices, triangles)
        unit, _, magnitude, coherence = normals(vertices, triangles)
        component, sizes = components(adjacency)
        bad = np.unique(np.concatenate((triangles[magnitude == 0].ravel(), edges[counts > 2].ravel())))
        eligible = (sizes[component] >= 512) & (coherence >= .5)
        eligible[bad] = False
        if name == "Yanyite":
            eligible[24205] = False
        curvature, variation = np.zeros(len(vertices)), np.zeros(len(vertices))
        for index, neighbors in enumerate(adjacency):
            if not neighbors:
                continue
            ids = [neighbor for neighbor, _ in neighbors]
            average_edge = np.mean([length for _, length in neighbors])
            if average_edge > 0:
                curvature[index] = float((vertices[ids] - vertices[index]).mean(axis=0) @ unit[index]) / average_edge
            variation[index] = float(np.mean(1 - np.clip(unit[ids] @ unit[index], -1, 1)))
        boundary_hops = np.full(len(vertices), -1, dtype=np.int64)
        queue = deque(int(index) for index in np.unique(edges[counts == 1]))
        for index in queue:
            boundary_hops[index] = 0
        while queue:
            index = queue.popleft()
            for neighbor, _ in adjacency[index]:
                if boundary_hops[neighbor] < 0:
                    boundary_hops[neighbor] = boundary_hops[index] + 1
                    queue.append(neighbor)
        ids = np.flatnonzero(eligible)
        positive = ids[curvature[ids] > .01]
        negative = ids[curvature[ids] < -.01]
        concave = positive[curvature[positive] >= np.quantile(curvature[positive], .8)] if len(positive) else positive
        convex = negative[curvature[negative] <= np.quantile(curvature[negative], .2)] if len(negative) else negative
        change = ids[variation[ids] >= np.quantile(variation[ids], .8)]
        near_boundary = ids[(boundary_hops[ids] >= 3) & (boundary_hops[ids] <= 6)]
        strata = {"natural_concave": (concave, curvature), "natural_convex": (convex, -curvature),
                  "curvature_change": (change, variation), "source_boundary_near": (near_boundary, boundary_hops)}
        source_patches = []
        used_centers = set()
        for category, (candidates, priority) in strata.items():
            order = order_candidates(vertices, candidates, priority, plan["candidate_limit_per_stratum"])
            selection["candidate_orders"].append({"source": name, "stratum": category, "eligible_candidates": len(candidates), "ordered_centers": order})
            accepted = 0
            for rank, seed in enumerate(order):
                if accepted >= plan["patch_quota_per_stratum"]:
                    break
                checked = {"source": name, "stratum": category, "candidate_rank": rank, "center_vertex_id": seed}
                if seed in used_centers:
                    checked.update(accepted=False, reason="center_already_selected_by_earlier_stratum")
                    selection["candidate_checks"].append(checked)
                    continue
                patch, reason = precheck(vertices, triangles, adjacency, unit, seed, plan["allowed_vertices"])
                if patch is None:
                    checked.update(accepted=False, reason=reason)
                    selection["candidate_checks"].append(checked)
                    continue
                patch_id = f"{name}_patch_{len(source_patches):02d}"
                folder = HERE / "private/patches" / patch_id
                folder.mkdir(parents=True)
                shared = patch["shared"]
                np.savez_compressed(folder / "graph.npz", edge_index=shared["edge_index"], allowed_mask=shared["allowed_mask"],
                                    boundary_mask=shared["boundary_mask"], free_mask=shared["free_mask"])
                np.savez_compressed(folder / "mapping.npz", context_source_ids=shared["context_ids"], allowed_source_ids=patch["allowed"],
                                    boundary_source_ids=patch["boundary"], context_source_face_ids=patch["context_face_ids"],
                                    context_triangles=patch["context_triangles"], source_polygon_ids=polygon_ids[patch["context_face_ids"]],
                                    incident_source_face_ids=patch["closure"])
                np.save(folder / "reference_local.npy", vertices[shared["context_ids"]], allow_pickle=False)
                item = {"id": patch_id, "source": name, "source_group": "group_000_unknown_upstream", "purpose": "development_train_pool",
                        "stratum": category, "center_vertex_id": seed, "candidate_rank": rank,
                        "allowed_vertices": len(patch["allowed"]), "boundary_vertices": len(patch["boundary"]),
                        "free_vertices": int(shared["free_mask"].sum()), "context_vertices": len(shared["context_ids"]),
                        "context_faces": len(patch["context_face_ids"]), "incident_faces": len(patch["closure"]),
                        "distance_to_boundary_m": patch["distance_to_boundary_m"], "support_counts_r35_r55": patch["support_counts"],
                        "support_normal_cosine_min_r35_r55": patch["support_normal_cosine_min"],
                        "center_normal": patch["center_normal"].tolist(), "signed_curvature_proxy": float(curvature[seed]),
                        "normal_variation_proxy": float(variation[seed]), "source_boundary_distance_hops": int(boundary_hops[seed]),
                        "component_vertices": int(sizes[component[seed]]), "private_directory": str(folder)}
                selection["patches"].append(item)
                source_patches.append((item, set(patch["allowed"].tolist())))
                used_centers.add(seed)
                checked.update(accepted=True, patch_id=patch_id, reason="source_only_precheck_passed")
                selection["candidate_checks"].append(checked)
                accepted += 1
        for i, (first, first_ids) in enumerate(source_patches):
            for second, second_ids in source_patches[i + 1:]:
                overlap = len(first_ids & second_ids)
                if overlap:
                    selection["overlaps"].append({"patches": [first["id"], second["id"]], "shared_allowed_vertices": overlap,
                                                  "jaccard": overlap / len(first_ids | second_ids), "same_group": True})
        selection["source_summary"].append({"source": name, "eligible_vertices": len(ids), "selected_patches": len(source_patches),
                                             "by_stratum": {category: sum(item["stratum"] == category for item, _ in source_patches) for category in strata},
                                             "source_vertices_excluded_by_components_below512": int(np.count_nonzero(sizes[component] < 512))})
        print(json.dumps(selection["source_summary"][-1]), flush=True)
    selection.update(status="frozen_for_generation", patches_count=len(selection["patches"]),
                     max_observations=7 * len(selection["patches"]), wall_s=time.perf_counter() - started,
                     cpu_s=time.process_time() - cpu_started,
                     normal_categories="geometric proxy strata under saved winding, source-shape preservation controls without artistic-quality labels")
    target.write_text(json.dumps(selection, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()

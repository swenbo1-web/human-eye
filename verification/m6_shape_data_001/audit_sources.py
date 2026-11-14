"""Inspect frozen source snapshots and conservative provenance groups."""
import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import hashlib
import itertools
import json
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from geometry import components, graph, normals, shortest


def sha(array):
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def nearest(points, target):
    distances, indices = [], []
    target_squared = np.einsum("ij,ij->i", target, target)
    for start in range(0, len(points), 128):
        block = points[start:start + 128]
        squared = np.einsum("ij,ij->i", block, block)[:, None] + target_squared[None, :] - 2 * block @ target.T
        index = squared.argmin(axis=1)
        distances.extend(np.maximum(squared[np.arange(len(block)), index], 0))
        indices.extend(index)
    return np.asarray(distances), np.asarray(indices)


def sample(points, maximum):
    return points[np.linspace(0, len(points) - 1, min(len(points), maximum), dtype=np.int64)]


def normalized(points):
    centered = points - points.mean(axis=0)
    scale = float(np.sqrt(np.mean(np.sum(centered * centered, axis=1))))
    _, _, frame = np.linalg.svd(centered, full_matrices=False)
    return centered @ frame.T / scale, scale


def align(first, second, final_count=2048):
    a, scale_a = normalized(first)
    b, scale_b = normalized(second)
    coarse_a, coarse_b = sample(a, 96), sample(b, 96)
    best = None
    for permutation in itertools.permutations(range(3)):
        for signs in itertools.product((-1., 1.), repeat=3):
            rotation = np.eye(3)[:, permutation] * np.asarray(signs)
            moved = coarse_a @ rotation
            score = float(nearest(moved, coarse_b)[0].mean() + nearest(coarse_b, moved)[0].mean())
            if best is None or score < best[0]:
                best = (score, rotation)
    rotation, translation = best[1], np.zeros(3)
    fit_a, fit_b = sample(a, 512), sample(b, 2048)
    for _ in range(10):
        moved = fit_a @ rotation + translation
        _, indices = nearest(moved, fit_b)
        matched = fit_b[indices]
        center_a, center_b = moved.mean(axis=0), matched.mean(axis=0)
        u, _, vt = np.linalg.svd((moved - center_a).T @ (matched - center_b))
        correction = u @ vt
        rotation = rotation @ correction
        translation = (translation - center_a) @ correction + center_b
    moved = a @ rotation + translation
    forward, _ = nearest(sample(moved, final_count), b)
    backward, _ = nearest(sample(b, final_count), moved)
    return {"normalized_symmetric_rmse": float(np.sqrt((forward.mean() + backward.mean()) / 2)),
            "normalized_p95": float(np.sqrt(np.quantile(np.concatenate((forward, backward)), .95))),
            "source_RMS_radius_m": [scale_a, scale_b], "reflection_allowed": True,
            "query_vertices_each_direction": min(len(a), final_count), "target_vertices": [len(a), len(b)],
            "scope": "deterministic PCA sign/permutation initialization plus 10 point-ICP steps; an approximate similarity diagnostic"}


def main():
    started, cpu_started = time.perf_counter(), time.process_time()
    manifest = json.loads((HERE / "SOURCE_MANIFEST.json").read_bytes())
    audit = {"cycle_id": "M6-SHAPE-DATA-001", "sources": [], "global_pairs": [], "local_pairs": []}
    meshes = {}
    for source in manifest["sources"]:
        name = source["name"]
        selected = source.get("evaluated", source["raw"])
        raw = json.loads(Path(source["raw"]["path"]).read_bytes())
        snapshot = json.loads(Path(selected["path"]).read_bytes())
        vertices = np.asarray(snapshot["vertices_world"], dtype=np.float64)
        triangles = np.asarray(snapshot["triangles"], dtype=np.int64)
        polygon_ids = np.asarray(snapshot["polygon_ids_by_triangle"], dtype=np.int64)
        assert len(vertices) == len(raw["vertices_world"])
        assert not any(modifier["type"] != "ARMATURE" for modifier in source["selected_object"]["modifiers"])
        assert np.isfinite(vertices).all() and triangles.min() >= 0 and triangles.max() < len(vertices)
        edges, counts, lengths, adjacency = graph(vertices, triangles)
        normal, _, magnitude, coherence = normals(vertices, triangles)
        labels, sizes = components(adjacency)
        out = HERE / "private" / name / "snapshot.npz"
        np.savez_compressed(out, vertices=vertices, triangles=triangles, source_polygon_ids=polygon_ids,
                            source_vertex_ids=np.arange(len(vertices), dtype=np.int64))
        row = {"name": name, "source_sha256": source["original"]["sha256"], "selected_export": selected,
               "snapshot": {"path": str(out), "bytes": out.stat().st_size, "sha256": hashlib.sha256(out.read_bytes()).hexdigest()},
               "geometry_state": "saved-frame evaluated mesh" if "evaluated" in source else "frozen raw mesh, verified equal evaluated",
               "frame": source["scenes"][0]["frame"], "scene_units": source["scenes"][0]["unit_system"],
               "scale_length": source["scenes"][0]["scale_length"], "world_coordinates_m": True,
               "vertex_mapping": "same-count original mesh vertex indices; only armature/shape-key deformation is present",
               "triangle_mapping": "frozen selected snapshot calc_loop_triangles order; source polygon mapping stored",
               "raw_triangles_equal_selected": raw["triangles"] == snapshot["triangles"],
               "raw_to_selected_max_displacement_m": float(np.linalg.norm(vertices - np.asarray(raw["vertices_world"]), axis=1).max()),
               "vertices": len(vertices), "triangles": len(triangles), "edges": len(edges), "components": len(sizes),
               "largest_component_sizes": sorted(sizes.tolist(), reverse=True)[:20],
               "boundary_edges": int(np.count_nonzero(counts == 1)), "nonmanifold_edges": int(np.count_nonzero(counts > 2)),
               "degenerate_triangles": int(np.count_nonzero(magnitude == 0)),
               "world_bounds_m": [vertices.min(axis=0).tolist(), vertices.max(axis=0).tolist()],
               "mean_edge_m": float(lengths.mean()), "median_edge_m": float(np.median(lengths)),
               "coordinate_array_sha256": sha(vertices), "triangle_array_sha256": sha(triangles),
               "sorted_edge_length_over_RMS_radius_sha256": sha(np.sort(lengths / normalized(vertices)[1]))}
        audit["sources"].append(row)
        eligible = np.flatnonzero((sizes[labels] >= 512) & (coherence > .25))
        local_seeds = []
        separation = np.full(len(eligible), np.inf)
        for _ in range(4):
            seed = int(eligible[np.argmax(separation)])
            local_seeds.append(seed)
            separation = np.minimum(separation, np.sum((vertices[eligible] - vertices[seed]) ** 2, axis=1))
        local = [vertices[list(shortest(adjacency, [seed], limit=256))] for seed in local_seeds]
        meshes[name] = (vertices, triangles, local, local_seeds)
    for first, second in itertools.combinations(meshes, 2):
        a, ta, local_a, seeds_a = meshes[first]
        b, tb, local_b, seeds_b = meshes[second]
        pair = {"sources": [first, second], "coordinate_arrays_exact": a.shape == b.shape and np.array_equal(a, b),
                "triangle_arrays_exact": ta.shape == tb.shape and np.array_equal(ta, tb), **align(a, b)}
        audit["global_pairs"].append(pair)
        comparisons = []
        for i, patch_a in enumerate(local_a):
            for j, patch_b in enumerate(local_b):
                comparisons.append({"centers": [seeds_a[i], seeds_b[j]], **align(patch_a, patch_b, final_count=256)})
        comparisons.sort(key=lambda item: item["normalized_symmetric_rmse"])
        audit["local_pairs"].append({"sources": [first, second], "patch_pairs_checked": 16, "best_three": comparisons[:3],
                                     "scope": "four deterministic spatial-coverage seeds per source; local similarity cannot establish lineage independence"})
        print(json.dumps({"pair": [first, second], "global_rmse": pair["normalized_symmetric_rmse"],
                          "best_local_rmse": comparisons[0]["normalized_symmetric_rmse"]}), flush=True)
    audit.update(wall_s=time.perf_counter() - started, cpu_s=time.process_time() - cpu_started,
                 conclusion="Distinct sampled geometry does not establish upstream base-mesh independence. Provenance remains unknown.")
    (HERE / "SOURCE_AUDIT.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    groups = {"cycle_id": "M6-SHAPE-DATA-001", "frozen_before_damage_generation": True,
              "verified_independent_groups": 0, "conservative_groups": 1,
              "groups": [{"id": "group_000_unknown_upstream", "members": list(meshes),
                          "reason": "upstream base-mesh lineage unresolved; conservative union mandated by contract",
                          "purpose": "development/train-eligible pool pending independent validation provenance"}],
              "splits": {"development_train_pool": list(meshes), "validation": [], "reserved_test": []},
              "historical_Yanyite": "seven PAIRS001 cases remain historical development diagnostics, never new blind test",
              "preferred_four_name_split_used": False,
              "independence_gap": {"minimum_verified_groups_for_train_val_test": 3, "current_usable_conservative_groups": 1,
                                   "additional_independently_evidenced_groups_needed": 2,
                                   "alternative": "obtain upstream records establishing at least three independent groups among existing sources"},
              "training_gate": "Do not start model selection training until independently grouped validation is available; preserve a reserved test group for final acceptance."}
    (HERE / "SOURCE_GROUPS.json").write_text(json.dumps(groups, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()

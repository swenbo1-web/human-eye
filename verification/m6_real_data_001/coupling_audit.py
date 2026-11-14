"""Derive same-snapshot coupling context from the existing private export."""
import ast
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
CONTRACT = "50c58fbae2036d4655521649522bc7a420a0c0f3"


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def record(path):
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def bounds(points):
    return [[min(point[axis] for point in points) for axis in range(3)],
            [max(point[axis] for point in points) for axis in range(3)]]


def main():
    started = time.perf_counter()
    manifest = json.loads((OUT / "SOURCE_MANIFEST.json").read_bytes())
    inventory = json.loads((OUT / "INVENTORY.json").read_bytes())
    capture = next(row for row in reversed(manifest["captures"]) if row["selected_object"] is not None)
    folder = OUT / "private" / capture["capture_id"]
    raw_path = folder / "raw_selected.json"
    native_path = folder / "native_inventory.json"
    patch_path = OUT / "private" / "ARM_REGION.json"
    raw = json.loads(raw_path.read_bytes())
    native = json.loads(native_path.read_bytes())
    patch = json.loads(patch_path.read_bytes())
    checks = []

    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)

    for row in capture["export_files"]:
        check(f"frozen export {Path(row['path']).name}", record(Path(row["path"])) == row)
    check("same original patch", record(patch_path) == inventory["arm_region"]["private_patch"])
    check("native source IDs are dense original indices", raw["vertex_ids"] == list(range(len(raw["vertices_world"]))))
    triangles = raw["triangles"]
    vertices = raw["vertices_world"]
    parent = list(range(len(vertices)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for triangle in triangles:
        roots = [find(index) for index in triangle]
        minimum = min(roots)
        for root in roots:
            parent[root] = minimum
    component_ids = [find(index) for index in range(len(vertices))]
    groups = {}
    for index, component_id in enumerate(component_ids):
        groups.setdefault(component_id, []).append(index)
    mesh = next(obj for obj in native["objects"] if obj["name"] == raw["object_name"])
    component_sizes = sorted((len(indices) for indices in groups.values()), reverse=True)
    check("triangle connectivity matches native edge component sizes", component_sizes == mesh["mesh"]["connected_component_vertex_counts"])
    ids = patch["source_vertex_ids"]
    selected = set(ids)
    component_counts = Counter(component_ids[index] for index in ids)
    edge_counts = Counter(tuple(sorted((ids[a], ids[b]))) for triangle in patch["triangles_local"]
                          for a, b in ((triangle[0], triangle[1]), (triangle[1], triangle[2]), (triangle[2], triangle[0])))
    boundary_edges = sorted([list(edge) for edge, count in edge_counts.items() if count == 1])
    boundary_vertices = sorted({index for edge in boundary_edges for index in edge})
    crossing = [index for index, triangle in enumerate(triangles)
                if selected.intersection(triangle) and not selected.issuperset(triangle)]
    halo = sorted({index for triangle_id in crossing for index in triangles[triangle_id]} - selected)
    check("boundary and crossing counts agree with original audit", len(boundary_edges) == inventory["arm_region"]["one_incident_triangle_edges"] and
          len(crossing) == inventory["arm_region"]["crossing_source_triangles_excluded"])
    selected_bounds = bounds([vertices[index] for index in ids])
    components = []
    for component_id, indices in groups.items():
        box = bounds([vertices[index] for index in indices])
        lower_bound = math.sqrt(sum(max(0., box[0][axis] - selected_bounds[1][axis],
                                         selected_bounds[0][axis] - box[1][axis])**2 for axis in range(3)))
        components.append({"component_id": component_id, "vertex_count": len(indices),
                           "selected_vertices": component_counts.get(component_id, 0), "world_bounds_m": box,
                           "aabb_distance_lower_bound_m": lower_bound})
    other_components = sorted([row for row in components if not row["selected_vertices"]],
                              key=lambda row: (row["aabb_distance_lower_bound_m"], row["component_id"]))
    scene = native["scenes"][0]
    state = {"source_sha256": manifest["source"]["sha256"], "scene": scene["name"], "frame": scene["frame"],
             "subframe": scene["subframe"], "object_name": raw["object_name"],
             "raw_export_sha256": record(raw_path)["sha256"],
             "evaluated_export_sha256": record(folder / "evaluated_selected.json")["sha256"],
             "native_inventory_sha256": record(native_path)["sha256"],
             "binding_scope": "saved-file read-only snapshot; no live adapter residency revision was captured"}
    state["snapshot_sha256"] = hashlib.sha256(encoded(state)).hexdigest()
    associated = [{"name": obj["name"], "type": obj["type"], "parent": obj["parent"],
                   "matrix_world": obj["matrix_world"], "relationship": "same_scene_and_saved_frame",
                   "full_geometry_exported": False, "contact_or_support_semantics": "unassessed"}
                  for obj in native["objects"] if obj["name"] != raw["object_name"]]
    correction_source = ROOT / "human_eye_plugin/arm_twist_correction.py"
    tree = ast.parse(correction_source.read_text(encoding="utf8"))
    unchecked = next(ast.literal_eval(value) for node in ast.walk(tree) if isinstance(node, ast.Dict)
                     for key, value in zip(node.keys, node.values) if isinstance(key, ast.Constant) and key.value == "not_checked")
    check("outside-patch and animation unknowns retained", "outside_patch_objects" in unchecked and "animation_winding" in unchecked)
    private_context = {"schema": "m6-native-coupling-context-v1", "state": state,
                       "source_patch": record(patch_path), "source_vertex_ids": ids,
                       "full_mesh_component_id_by_source_vertex": component_ids,
                       "component_identity_rule": "minimum original vertex ID in triangle-connected component",
                       "component_table": components,
                       "boundary_source_edges": boundary_edges, "boundary_source_vertex_ids": boundary_vertices,
                       "crossing_source_triangle_ids": crossing, "outside_vertex_halo_ids": halo,
                       "same_component_exterior_vertex_ids": [i for i in range(len(vertices)) if i not in selected and component_ids[i] in component_counts],
                       "associated_scene_objects": associated, "confirmed_anomaly_labels": None}
    context_path = OUT / "private" / "COUPLED_REGION_CONTEXT.json"
    context_path.write_bytes(encoded(private_context))
    coverage = [
        {"category": "local_shape", "available": "static vertices, triangles, component membership, cut boundary", "check_scope": "geometric facts can be computed", "diagnosis": "unknown_missing_target_and_anatomical_confirmation"},
        {"category": "skinning", "available": None, "check_scope": "missing_armature_and_weights", "diagnosis": "unknown_missing_input"},
        {"category": "pose_joint", "available": None, "check_scope": "missing_bones_rest_pose_and_joint_task", "diagnosis": "unknown_missing_input"},
        {"category": "contact_intersection", "available": "complete same-character static triangles, exterior patch and component references", "check_scope": "within-character geometric queries possible; contact queries not run", "diagnosis": "unknown_missing_allowed_contact_and_target"},
        {"category": "scene_spatial_relations", "available": "same-frame names/types/transforms for Cube, Camera and Light", "check_scope": "partial; Cube geometry and support/task semantics uncollected", "diagnosis": "unknown_incomplete_context"},
        {"category": "temporal_continuity", "available": "saved frame 1 only", "check_scope": "missing_sequence_and_animation", "diagnosis": "unknown_missing_input"},
    ]
    result = {"cycle_id": "M6-REAL-DATA-001", "supplement": "coupled_context", "main_commit": "7c615212e706994678bb4aeb8b9836928ff8e22a",
              "contract_commit": CONTRACT, "state": state, "private_context": record(context_path),
              "actual_relations": {"full_character_components": len(groups),
                                   "selection_components": [row for row in components if row["selected_vertices"]],
                                   "boundary_edges": len(boundary_edges), "boundary_vertices": len(boundary_vertices),
                                   "crossing_source_triangles": len(crossing), "outside_vertex_halo": len(halo),
                                   "other_component_aabb_candidates": other_components[:5],
                                   "aabb_overlap_is_anomaly_truth": False,
                                   "associated_scene_objects": associated},
              "coverage": coverage, "potential_coupling": {"pair": ["local_shape", "contact_intersection"],
              "status": "unvalidated", "reason": "An accepted local shape change may affect exterior geometry and contacts. No accepted target or contact constraints are supplied."},
              "legacy_geometry_not_checked": unchecked, "scene_or_character_all_clear": None,
              "checks": checks, "additional_blender_processes": 0, "model_calls": 0, "asset_edits": 0,
              "cost": {"offline_wall_s_before_publication": time.perf_counter() - started,
                       "new_private_context_bytes": context_path.stat().st_size,
                       "current_private_cache_bytes": sum(path.stat().st_size for path in (OUT / "private").rglob("*") if path.is_file()),
                       "scope": "offline reuse only; original main-phase acquisition/cost records preserved"}}
    (OUT / "COUPLED_CONTEXT.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8", newline="\n")
    contract = subprocess.check_output(["git", "show", f"{CONTRACT}:docs/M6_COUPLED_EXPERT_CONTRACT.md"], cwd=ROOT)
    (OUT / "M6_COUPLED_EXPERT_CONTRACT.md").write_bytes(contract)
    print(json.dumps({"status": "context_collected", "checks": len(checks), "selected_component_ids": sorted(component_counts),
                      "boundary_vertices": len(boundary_vertices), "halo_vertices": len(halo), "new_blender_processes": 0}))


if __name__ == "__main__":
    main()

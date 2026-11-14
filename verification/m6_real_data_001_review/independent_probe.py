"""Independent read-only checks on a fixed real-data export; no author imports."""
from collections import Counter, deque
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE / "snapshot"
DATA = SNAPSHOT / "verification/m6_real_data_001"
PRIVATE = DATA / "private"


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bounds(points):
    return [list(map(min, zip(*points))), list(map(max, zip(*points)))]


def main():
    saved = read(HERE / "SNAPSHOT.json")
    manifest = read(DATA / "SOURCE_MANIFEST.json")
    inventory = read(DATA / "INVENTORY.json")
    coupled = read(DATA / "COUPLED_CONTEXT.json")
    context = read(PRIVATE / "COUPLED_REGION_CONTEXT.json")
    patch = read(PRIVATE / "ARM_REGION.json")
    raw = read(PRIVATE / "capture_02/raw_selected.json")
    evaluated = read(PRIVATE / "capture_02/evaluated_selected.json")
    native = read(PRIVATE / "capture_02/native_inventory.json")
    checks = []

    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)

    for capture in manifest["captures"]:
        for item in capture["export_files"]:
            local = PRIVATE / capture["capture_id"] / Path(item["path"]).name
            check(f"export bytes {capture['capture_id']}/{local.name}",
                  local.stat().st_size == item["bytes"] and digest(local) == item["sha256"])
    check("original source identity", digest(Path(manifest["source"]["path"])) == saved["source"]["sha256"])
    check("isolated source identity", digest(PRIVATE / "Yanyite_Appearance.blend") == saved["source"]["sha256"])
    check("patch frozen bytes", digest(PRIVATE / "ARM_REGION.json") == inventory["arm_region"]["private_patch"]["sha256"])
    check("coupling frozen bytes", digest(PRIVATE / "COUPLED_REGION_CONTEXT.json") == coupled["private_context"]["sha256"])
    check("one saved scene, metric unit scale 1", len(native["scenes"]) == 1 and native["scenes"][0]["scale_length"] == 1.)
    check("offline frame binding", native["scenes"][0]["frame"] == 1 and native["scenes"][0]["subframe"] == 0.)
    check("autoexec disabled in retained capture", native["autoexec_enabled"] is False)
    check("all observed objects belong to saved scene", set(native["scenes"][0]["object_names"]) == {o["name"] for o in native["objects"]})
    check("no recorded rig, shape keys, actions", not native["armature_datablocks"] and not native["shape_key_datablocks"] and not native["actions"])
    mesh = next(o for o in native["objects"] if o["name"] == raw["object_name"])
    check("no modifier or weight data", not mesh["modifiers"] and not mesh["mesh"]["vertex_groups"] and not raw["vertex_groups"] and not any(raw["weights"]))
    for field in ("vertices_object", "vertices_world", "vertex_ids", "triangles", "polygon_ids_by_triangle", "matrix_world"):
        check(f"raw/evaluated {field}", raw[field] == evaluated[field])
    points = raw["vertices_world"]
    triangles = raw["triangles"]
    n = len(points)
    check("dense source vertex IDs", raw["vertex_ids"] == list(range(n)))
    check("finite triples", all(len(p) == 3 and all(math.isfinite(x) for x in p) for p in points))
    check("valid triangle indices", all(len(t) == 3 and len(set(t)) == 3 and all(type(i) is int and 0 <= i < n for i in t) for t in triangles))
    check("original polygon references", len(raw["polygon_ids_by_triangle"]) == len(triangles) and all(0 <= i < mesh["mesh"]["polygons"] for i in raw["polygon_ids_by_triangle"]))
    matrix = raw["matrix_world"]
    transform_error = max(abs(sum(matrix[j][k] * p[k] for k in range(3)) + matrix[j][3] - points[i][j])
                          for i, p in enumerate(raw["vertices_object"]) for j in range(3))
    check("coordinate transform agreement within float32 export scale", transform_error <= 1e-6)

    # Independent breadth-first components, not the author's union-find.
    neighbors = [set() for _ in range(n)]
    incident = [set() for _ in range(n)]
    for tid, (a, b, c) in enumerate(triangles):
        neighbors[a].update((b, c)); neighbors[b].update((a, c)); neighbors[c].update((a, b))
        for v in (a, b, c):
            incident[v].add(tid)
    components = {}
    component_by_vertex = [None] * n
    for seed in range(n):
        if component_by_vertex[seed] is not None:
            continue
        queue = deque([seed]); component_by_vertex[seed] = seed; members = []
        while queue:
            v = queue.popleft(); members.append(v)
            for u in neighbors[v]:
                if component_by_vertex[u] is None:
                    component_by_vertex[u] = seed; queue.append(u)
        components[seed] = sorted(members)
    check("native edge component sizes match triangle BFS", sorted(map(len, components.values()), reverse=True) == mesh["mesh"]["connected_component_vertex_counts"])
    check("full component ID map", component_by_vertex == context["full_mesh_component_id_by_source_vertex"])
    box = patch["selection"]["bounds_xyz_minmax"]
    selected = [i for i, p in enumerate(points) if all(box[2*a] <= p[a] <= box[2*a+1] for a in range(3))]
    selected_set = set(selected)
    check("exact selected source IDs", selected == patch["source_vertex_ids"] == context["source_vertex_ids"])
    check("patch world/object coordinate identity", patch["vertices_world"] == [points[i] for i in selected] and patch["vertices_object"] == [raw["vertices_object"][i] for i in selected])
    affected = set().union(*(incident[i] for i in selected))
    inside = {tid for tid in affected if all(i in selected_set for i in triangles[tid])}
    crossing = affected - inside
    check("inside triangle IDs", sorted(inside) == patch["source_triangle_ids"])
    check("crossing triangle IDs", sorted(crossing) == context["crossing_source_triangle_ids"])
    check("source triangle mapping", [[selected[i] for i in t] for t in patch["triangles_local"]] == [triangles[i] for i in sorted(inside)])
    check("source polygon mapping", patch["source_polygon_ids"] == [raw["polygon_ids_by_triangle"][i] for i in sorted(inside)])
    halo = sorted({v for tid in crossing for v in triangles[tid]} - selected_set)
    check("halo source IDs", halo == context["outside_vertex_halo_ids"])
    edges = Counter(tuple(sorted((a, b))) for tid in inside for a, b in zip(triangles[tid], triangles[tid][1:] + triangles[tid][:1]))
    boundary = sorted([list(e) for e, count in edges.items() if count == 1])
    boundary_vertices = sorted({v for edge in boundary for v in edge})
    check("exact boundary edges", boundary == context["boundary_source_edges"])
    check("exact boundary vertices", boundary_vertices == context["boundary_source_vertex_ids"])
    selected_components = {component_by_vertex[i] for i in selected}
    exterior = sorted({v for c in selected_components for v in components[c]} - selected_set)
    check("same-component exterior references", exterior == context["same_component_exterior_vertex_ids"])
    check("full affected dependency set", len(affected) == 898 and len(inside) == 748 and len(crossing) == 150)
    check("context contains all 102 component bounds", len(context["component_table"]) == len(components) == 102)
    for row in context["component_table"]:
        check(f"component bounds {row['component_id']}", bounds([points[i] for i in components[row["component_id"]]]) == row["world_bounds_m"])
    state = dict(context["state"]); state_hash = state.pop("snapshot_sha256")
    check("state digest", hashlib.sha256(json.dumps(state,sort_keys=True,separators=(",", ":"),allow_nan=False).encode()).hexdigest() == state_hash)
    check("summary/private state agreement", coupled["state"] == context["state"])
    check("unknowns remain unknown", coupled["scene_or_character_all_clear"] is None and all(r["diagnosis"].startswith("unknown") for r in coupled["coverage"]))
    check("all six coverage entries present", len(coupled["coverage"]) == 6 and len({r["category"] for r in coupled["coverage"]}) == 6)
    check("no repaired target or labels manufactured", all(patch[k] is None for k in ("bone_chain","weights","sections","paired_reference","supervision_label")) and context["confirmed_anomaly_labels"] is None)
    private_bytes = sum(p.stat().st_size for p in PRIVATE.rglob('*') if p.is_file())
    check("private byte accounting", private_bytes == coupled["cost"]["current_private_cache_bytes"] == 12049055)
    for row in saved["snapshot_files"]:
        check(f"snapshot unchanged {row['relative_path']}", digest(Path(row["path"])) == row["sha256"])
    check("original remains unchanged after checks", digest(Path(manifest["source"]["path"])) == saved["source"]["sha256"])
    result = {"status":"passed","reviewed_commit":saved["reviewed_commit"],"checks":checks,
              "method":"stdlib BFS components and incident-face closure; no author audit imports; no Blender run",
              "counts":{"vertices":n,"triangles":len(triangles),"components":len(components),"selected_vertices":len(selected),
                        "inside_triangles":len(inside),"crossing_triangles":len(crossing),"affected_triangles":len(affected),
                        "boundary_edges":len(boundary),"boundary_vertices":len(boundary_vertices),"halo_vertices":len(halo),
                        "same_component_exterior_vertices":len(exterior)},"coordinate_transform_max_error_m":transform_error,
              "private_bytes":private_bytes,"not_run":["native Blender recapture","exact contacts","target/candidate evaluation","expert inference/training","M5 execution","formal performance"],
              "limits":["Offline export consistency and current original identity; first author captures lack pre-launch collector hash",
                        "No confirmed defect, accepted correction target, or learned benefit established",
                        "Provisional spatial selection and saved-file snapshot, not live scene residency"]}
    (HERE/'INDEPENDENT_RESULTS.json').write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    print(json.dumps({"status":result["status"],"checks":len(checks),"counts":result["counts"],"coordinate_error_m":transform_error,"private_bytes":private_bytes}))


if __name__ == "__main__":
    main()

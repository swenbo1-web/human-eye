"""One root-launched Blender process builds the frozen extreme/origin pair."""

import hashlib
import json
from pathlib import Path
import struct
import sys


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, allow_nan=False, ensure_ascii=False, indent=2)
        stream.write("\n")


def world_points(local, matrix, scale):
    # Match the existing host scalar forward path over actual Blender readback.
    return [[(sum(matrix[r][c] * point[c] for c in range(3)) + matrix[r][3]) * scale
             for r in range(3)] for point in local]


def exact_binary32(points):
    return all(struct.unpack("<f", struct.pack("<f", value))[0] == value
               for point in points for value in point)


def inventory(bpy):
    graph = bpy.context.evaluated_depsgraph_get()
    objects = []
    for ordinal, obj in enumerate(bpy.context.scene.objects):
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(graph)
        mesh = evaluated.to_mesh()
        try:
            mesh.calc_loop_triangles()
            local = [[float(x) for x in vertex.co] for vertex in mesh.vertices]
            matrix = [[float(x) for x in row] for row in evaluated.matrix_world]
            objects.append({"name": obj.name, "name_full": obj.name_full, "library_path": "",
                "asset_object_ordinal": ordinal, "vertices_local": local,
                "matrix_world": matrix,
                "vertices_world": world_points(local, matrix, float(bpy.context.scene.unit_settings.scale_length)),
                "polygons": [list(face.vertices) for face in mesh.polygons],
                "source_triangles": [list(face.vertices) for face in mesh.loop_triangles]})
        finally:
            evaluated.to_mesh_clear()
    return {"objects": objects, "frame": bpy.context.scene.frame_current,
            "subframe": float(bpy.context.scene.frame_subframe),
            "scale_length": float(bpy.context.scene.unit_settings.scale_length),
            "unit_system": bpy.context.scene.unit_settings.system,
            "world_mapping": "host scalar sum over actual evaluated local/matrix readback"}


def create(bpy, name, vertices, faces, matrix):
    from mathutils import Matrix
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.frame_set(1)
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    obj.matrix_world = Matrix(matrix)
    bpy.context.view_layer.update()
    return inventory(bpy)


def main():
    import bpy
    arguments = sys.argv[sys.argv.index("--") + 1:]
    if len(arguments) != 2:
        raise ValueError("camera_builder_requires_frozen_plan_and_owned_output")
    plan_path, output = map(Path, arguments)
    plan = json.loads(plan_path.read_bytes())
    for pin in plan["source_pins"]:
        if digest(pin["path"]) != pin["sha256"]:
            raise ValueError("camera_builder_frozen_source_changed")
    target = plan["counterexample"]
    if not exact_binary32(target["local_vertices"]) or not exact_binary32(target["matrix_world"]):
        raise ValueError("camera_counterexample_not_exact_binary32")
    extreme = create(bpy, target["target"], target["local_vertices"], target["triangles"], target["matrix_world"])
    actual = extreme["objects"][0]
    save(output / "extreme.GEOMETRY.json", extreme)
    if (actual["vertices_local"] != target["local_vertices"]
            or actual["matrix_world"] != target["matrix_world"]
            or actual["source_triangles"] != target["triangles"]):
        raise ValueError("extreme_actual_local_matrix_or_faces_changed_readback_retained")
    extreme_path = output / "extreme.blend"
    if extreme_path.exists():
        raise FileExistsError(extreme_path)
    bpy.ops.wm.save_as_mainfile(filepath=str(extreme_path), check_existing=False)
    origin = [actual["matrix_world"][i][3] for i in range(3)]
    if origin != target["common_origin_world_m"]:
        raise ValueError("actual_common_origin_changed")
    translated = [[value - origin[axis] for axis, value in enumerate(point)]
                  for point in actual["vertices_world"]]
    if not exact_binary32(translated):
        save(output / "ORIGIN_UNREPRESENTABLE.json", {"actual_extreme_world": actual["vertices_world"],
             "common_origin": origin, "translated_points": translated})
        raise ValueError("quantized_origin_control_not_storable_as_binary32")
    identity = [[1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.], [0., 0., 0., 1.]]
    centered = create(bpy, target["target"], translated, target["triangles"], identity)
    save(output / "origin.GEOMETRY.json", centered)
    centered_actual = centered["objects"][0]
    if (centered_actual["vertices_local"] != translated or centered_actual["vertices_world"] != translated
            or centered_actual["source_triangles"] != target["triangles"]):
        raise ValueError("quantized_origin_dimensions_changed_actual_readback_retained")
    origin_path = output / "origin.blend"
    if origin_path.exists():
        raise FileExistsError(origin_path)
    bpy.ops.wm.save_as_mainfile(filepath=str(origin_path), check_existing=False)
    for pin in plan["source_pins"]:
        if digest(pin["path"]) != pin["sha256"]:
            raise ValueError("camera_builder_original_input_modified")
    save(output / "DERIVATION.json", {"schema": "m4-camera-owned-derivation-v1",
        "builder_sha256": digest(__file__), "input_plan_sha256": digest(plan_path),
        "blender_version": bpy.app.version_string, "builder_processes": 1,
        "source_local_matrix_faces_readback_exact": True,
        "actual_extreme_world": actual["vertices_world"],
        "offline_world_equal_actual_scalar_readback": actual["vertices_world"] == target["offline_world_vertices"],
        "common_origin_world_m": origin, "origin_local_vertices": translated,
        "origin_preserves_quantized_world_dimensions": True,
        "world_extents": [max(point[i] for point in actual["vertices_world"]) - min(point[i] for point in actual["vertices_world"]) for i in range(3)],
        "origin_extents": [max(point[i] for point in translated) - min(point[i] for point in translated) for i in range(3)],
        "original_sources_unchanged": True, "product_imports": 0, "raster_calls": 0,
        "assets": [{"name": name, "asset": str(output / (name + ".blend")),
                    "sha256": digest(output / (name + ".blend")),
                    "geometry_sha256": digest(output / (name + ".GEOMETRY.json"))} for name in ("extreme", "origin")]})


if __name__ == "__main__":
    main()

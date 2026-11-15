"""Build frozen world geometry as local/identity and derive target-only once."""

from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct
import sys


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


IDENTITY = [[1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.], [0., 0., 0., 1.]]


def points(record):
    result = []
    for vertex in record["world_vertices_m"]:
        row = []
        for value in vertex:
            exact = Fraction(value)
            converted = float(exact)
            stored = struct.unpack("<f", struct.pack("<f", converted))[0]
            if Fraction.from_float(converted) != exact or Fraction.from_float(stored) != exact:
                raise ValueError("frozen_world_coordinate_not_exact_binary32")
            row.append(converted)
        result.append(row)
    return result


def inventory(bpy, original_order):
    graph = bpy.context.evaluated_depsgraph_get()
    objects = []
    for ordinal, obj in enumerate(bpy.context.scene.objects):
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(graph)
        mesh = evaluated.to_mesh()
        try:
            mesh.calc_loop_triangles()
            local = [[float(value) for value in vertex.co] for vertex in mesh.vertices]
            matrix = [[float(value) for value in row] for row in evaluated.matrix_world]
            world = [[sum(matrix[axis][column] * vertex[column] for column in range(3)) + matrix[axis][3]
                      for axis in range(3)] for vertex in local]
            objects.append({"name": obj.name, "name_full": obj.name_full, "library_path": "",
                "asset_object_ordinal": ordinal, "frozen_object_ordinal": original_order[obj.name],
                "vertices_local": local, "vertices_world": world, "matrix_world": matrix,
                "polygons": [list(face.vertices) for face in mesh.polygons],
                "source_triangles": [list(face.vertices) for face in mesh.loop_triangles]})
        finally:
            evaluated.to_mesh_clear()
    return {"objects": objects, "frame": bpy.context.scene.frame_current,
            "subframe": float(bpy.context.scene.frame_subframe), "unit_system": bpy.context.scene.unit_settings.system,
            "scale_length": float(bpy.context.scene.unit_settings.scale_length),
            "construction": "frozen world coordinates stored directly as local binary32, identity transforms"}


def verify(actual, expected):
    if len(actual["objects"]) != len(expected):
        raise ValueError("owned_object_count_changed")
    for source, row in zip(expected, actual["objects"], strict=True):
        vertices = points(source)
        if (row["name"] != source["name"] or row["vertices_local"] != vertices
                or row["vertices_world"] != vertices or row["matrix_world"] != IDENTITY
                or row["polygons"] != source["triangles"] or row["source_triangles"] != source["triangles"]):
            raise ValueError("owned_readback_name_order_points_faces_or_identity_mismatch")
    if actual["scale_length"] != 1 or actual["frame"] != 1 or actual["subframe"] != 0:
        raise ValueError("owned_frame_or_scale_changed")


def main():
    import bpy
    from mathutils import Matrix
    arguments = sys.argv[sys.argv.index("--") + 1:]
    if len(arguments) != 2:
        raise ValueError("builder_requires_plan_and_owned_output")
    plan_path, output = map(Path, arguments)
    plan = json.loads(plan_path.read_bytes())
    for pin in plan["source_pins"]:
        if digest(pin["path"]) != pin["sha256"]:
            raise ValueError("frozen_input_changed_before_build")
    frozen = json.loads(Path(plan["frozen_geometry"]["path"]).read_bytes())
    records = frozen["objects"]
    original_order = {row["name"]: index for index, row in enumerate(records)}
    target = next(row for row in records if row["name"] == plan["target"])
    if (len(records) != 14 or sum(len(row["world_vertices_m"]) for row in records) != 3478
            or sum(len(row["triangles"]) for row in records) != 6148
            or len(target["world_vertices_m"]) != 293 or len(target["triangles"]) != 514):
        raise ValueError("frozen_input_counts_changed")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.frame_set(1)
    for row in records:
        mesh = bpy.data.meshes.new(row["name"] + "Mesh")
        mesh.from_pydata(points(row), [], row["triangles"])
        mesh.update()
        obj = bpy.data.objects.new(row["name"], mesh)
        scene.collection.objects.link(obj)
        obj.matrix_world = Matrix.Identity(4)
    bpy.context.view_layer.update()
    complete = inventory(bpy, original_order)
    save(output / "main.GEOMETRY.json", complete)
    verify(complete, records)
    main_path = output / "main.blend"
    if main_path.exists():
        raise FileExistsError(main_path)
    bpy.ops.wm.save_as_mainfile(filepath=str(main_path), check_existing=False)
    main_sha = digest(main_path)
    for obj in list(bpy.data.objects):
        if obj.name != target["name"]:
            bpy.data.objects.remove(obj, do_unlink=True)
    bpy.context.view_layer.update()
    only = inventory(bpy, original_order)
    save(output / "target_only.GEOMETRY.json", only)
    verify(only, [target])
    main_target = next(row for row in complete["objects"] if row["name"] == target["name"])
    if ({key: value for key, value in main_target.items() if key != "asset_object_ordinal"}
            != {key: value for key, value in only["objects"][0].items() if key != "asset_object_ordinal"}):
        raise ValueError("target_only_changed_retained_target_data")
    only_path = output / "target_only.blend"
    if only_path.exists():
        raise FileExistsError(only_path)
    bpy.ops.wm.save_as_mainfile(filepath=str(only_path), check_existing=False)
    if digest(main_path) != main_sha:
        raise ValueError("main_asset_changed_during_control_derivation")
    for pin in plan["source_pins"]:
        if digest(pin["path"]) != pin["sha256"]:
            raise ValueError("original_source_modified_by_builder")
    save(output / "DERIVATION.json", {"schema": "m4-selective-002-owned-assets-v1",
        "builder_sha256": digest(__file__), "input_plan_sha256": digest(plan_path),
        "frozen_geometry_sha256": plan["frozen_geometry"]["sha256"], "blender_version": bpy.app.version_string,
        "actual_readback_points_faces_identity_exact": True, "no_historical_translation_reapplied": True,
        "target_only_preserves_target_name_points_faces_order": True, "main_asset_stable": True,
        "original_sources_unchanged": True, "builder_processes": 1, "product_imports": 0, "rasters": 0,
        "counts": [{"name": name, "objects": len(value["objects"]),
                    "vertices": sum(len(row["vertices_local"]) for row in value["objects"]),
                    "triangles": sum(len(row["source_triangles"]) for row in value["objects"])}
                   for name, value in (("main", complete), ("target_only", only))]})


if __name__ == "__main__":
    main()

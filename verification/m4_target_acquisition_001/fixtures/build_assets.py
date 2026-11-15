"""Root-launched Blender builder for the two predeclared owned derivatives."""

import hashlib
import json
from pathlib import Path
import struct
import sys


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def scene_inventory(bpy):
    graph = bpy.context.evaluated_depsgraph_get()
    objects = []
    for ordinal, obj in enumerate(bpy.context.scene.objects):
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(graph)
        mesh = evaluated.to_mesh()
        try:
            mesh.calc_loop_triangles()
            objects.append({"asset_object_ordinal": ordinal, "name": obj.name,
                            "name_full": obj.name_full, "library_path": "",
                            "vertices_local": [[float(x) for x in vertex.co] for vertex in mesh.vertices],
                            "polygons": [list(face.vertices) for face in mesh.polygons],
                            "source_triangles": [list(face.vertices) for face in mesh.loop_triangles],
                            "matrix_world": [[float(x) for x in row] for row in evaluated.matrix_world]})
        finally:
            evaluated.to_mesh_clear()
    return {"objects": objects, "frame": bpy.context.scene.frame_current,
            "subframe": float(bpy.context.scene.frame_subframe),
            "scale_length": float(bpy.context.scene.unit_settings.scale_length),
            "unit_system": bpy.context.scene.unit_settings.system}


def main():
    import bpy
    args = sys.argv[sys.argv.index("--") + 1:]
    if len(args) != 2:
        raise ValueError("builder_requires_config_and_output")
    config = json.loads(Path(args[0]).read_bytes())
    output = Path(args[1]).resolve()
    pins = {row["path"]: row["sha256"] for row in config["source_pins"]}
    for path, expected in pins.items():
        if digest(path) != expected:
            raise ValueError("builder_frozen_source_changed")
    # The controller byte-copies simple_boxes into this owned directory first.
    simple = output / "simple_boxes_source.blend"
    if digest(simple) != config["simple_source_sha256"]:
        raise ValueError("builder_simple_copy_changed")
    bpy.ops.wm.open_mainfile(filepath=str(simple))
    before = scene_inventory(bpy)
    focal = next(row for row in before["objects"] if row["name"] == "M4_Focal")
    for obj in list(bpy.data.objects):
        if obj.name != "M4_Focal":
            bpy.data.objects.remove(obj, do_unlink=True)
    bpy.context.view_layer.update()
    after = scene_inventory(bpy)
    if (len(after["objects"]) != 1
            or {key: value for key, value in focal.items() if key != "asset_object_ordinal"}
            != {key: value for key, value in after["objects"][0].items() if key != "asset_object_ordinal"}
            or any(before[key] != after[key] for key in ("frame", "subframe", "scale_length", "unit_system"))):
        raise ValueError("focal_only_derivation_changed_retained_source")
    focal_path = output / "focal_only.blend"
    if focal_path.exists():
        raise FileExistsError(focal_path)
    bpy.ops.wm.save_as_mainfile(filepath=str(focal_path), check_existing=False)
    save(output / "focal_only.GEOMETRY.json", after)

    rack = json.loads(Path(config["rack_source"]).read_bytes())
    if len(rack["objects"]) != 12:
        raise ValueError("rack_source_count")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.frame_set(1)
    for source in rack["objects"]:
        vertices = source["vertices"]
        for point in vertices:
            for value in point:
                if struct.unpack("<f", struct.pack("<f", float(value)))[0] != value:
                    raise ValueError("rack_coordinate_not_binary32_exact")
        mesh = bpy.data.meshes.new(source["name"] + "Mesh")
        mesh.from_pydata(vertices, [], source["triangles"])
        mesh.update()
        obj = bpy.data.objects.new(source["name"], mesh)
        scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    inventory = scene_inventory(bpy)
    for source, actual in zip(rack["objects"], inventory["objects"], strict=True):
        if (source["name"] != actual["name"] or source["vertices"] != actual["vertices_local"]
                or source["triangles"] != actual["polygons"]
                or actual["matrix_world"] != [[1., 0., 0., 0.], [0., 1., 0., 0.],
                                              [0., 0., 1., 0.], [0., 0., 0., 1.]]):
            raise ValueError("rack_geometry_or_order_changed")
    rack_path = output / "rack.blend"
    if rack_path.exists():
        raise FileExistsError(rack_path)
    bpy.ops.wm.save_as_mainfile(filepath=str(rack_path), check_existing=False)
    save(output / "rack.GEOMETRY.json", inventory)
    for path, expected in pins.items():
        if digest(path) != expected:
            raise ValueError("builder_original_source_modified")
    save(output / "DERIVATION.json", {"schema": "m4-target-owned-derivation-v1",
        "blender_version": bpy.app.version_string,
        "builder_sha256": digest(__file__), "original_sources_unchanged": True,
        "focal_original": focal, "focal_retained": after["objects"][0],
        "created_assets": [{"name": name, "path": str(output / (name + ".blend")),
                            "sha256": digest(output / (name + ".blend"))} for name in ("focal_only", "rack")],
        "builder_processes": 1, "raster_calls": 0, "product_imports": 0})


if __name__ == "__main__":
    main()

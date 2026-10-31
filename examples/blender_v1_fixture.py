"""Disposable far-origin Blender scene for deterministic v1 adjustment tests.

Load this standalone file in Blender; the full engine is not imported here.
No .blend file is saved.  setup/cleanup must use the same new evidence folder.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import math
import struct
import sys
import uuid


KEY = "human_eye_v1_adjustment_fixture_20261022"


def _paths(project_root, output_dir):
    root, output = Path(project_root).resolve(), Path(output_dir).resolve()
    if not output.is_relative_to(root) or output == root:
        raise ValueError("Fixture evidence must use a dedicated folder within project_root")
    return root, output


def _mesh_summary(obj):
    if obj.type != "MESH":
        return None
    mesh, digest = obj.data, hashlib.sha256()
    for vertex in mesh.vertices:
        digest.update(struct.pack("<3d", *vertex.co))
    for edge in mesh.edges:
        digest.update(struct.pack("<2I", *edge.vertices))
    for polygon in mesh.polygons:
        digest.update(struct.pack("<I", len(polygon.vertices)))
        digest.update(struct.pack("<" + "I" * len(polygon.vertices), *polygon.vertices))
    return {"data_name": mesh.name, "vertices": len(mesh.vertices), "edges": len(mesh.edges),
            "polygons": len(mesh.polygons), "geometry_sha256": digest.hexdigest()}


def _summary(scene):
    return {obj.name: {"type": obj.type, "matrix_world": [list(row) for row in obj.matrix_world],
                       "mesh": _mesh_summary(obj)} for obj in scene.objects}


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def setup(project_root, output_dir):
    import bpy
    from mathutils import Matrix
    root, output = _paths(project_root, output_dir)
    if KEY in bpy.app.driver_namespace:
        raise RuntimeError("An earlier v1 fixture must be cleaned up first")
    if (output / "live_fixture.json").exists() or (output / "live_cleanup.json").exists():
        raise RuntimeError("Use a fresh v1 fixture evidence directory")
    window = bpy.context.window
    if window is None:
        raise RuntimeError("An open Blender window is required")
    source = root / "human_eye_plugin" / "blender_host.py"
    if not source.is_file():
        raise ValueError("project_root must contain the trusted Blender host")
    original, layer = window.scene, window.view_layer
    saved = {"original": original, "view_layer_name": layer.name, "output": str(output),
             "original_summary": _summary(original),
             "selection": sorted(obj.name for obj in original.objects if obj.select_get()),
             "active": getattr(layer.objects.active, "name", None), "objects": [], "meshes": []}
    bpy.app.driver_namespace[KEY] = saved
    output.mkdir(parents=True, exist_ok=True)
    prefix = "HumanEye_V1_Adjust_" + uuid.uuid4().hex[:10]
    scene = bpy.data.scenes.new(prefix)
    saved["test_scene"] = scene
    window.scene = scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1
    def box(label, center, size, yaw=0):
        signs = [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
        faces = [(0,3,2,1),(4,5,6,7),(0,1,5,4),(2,3,7,6),(1,2,6,5),(3,0,4,7)]
        data = bpy.data.meshes.new(prefix + "_" + label + "_mesh")
        saved["meshes"].append(data)
        data.from_pydata([[sign[i] * size[i] / 2 for i in range(3)] for sign in signs], [], faces)
        data.update()
        obj = bpy.data.objects.new(prefix + "_" + label, data)
        saved["objects"].append(obj)
        scene.collection.objects.link(obj)
        obj.matrix_world = Matrix.Translation(center) @ Matrix.Rotation(math.radians(yaw), 4, "Z")
        return obj
    base = box("base", [12, -7, 3.1], [1.4, 1.2, .2])
    part = box("part", [12.08, -7.04, 3.35], [.3, .2, .1], 17)
    obstacle = box("obstacle", [12.8, -7, 3.35], [.2, .2, .2])
    part.select_set(True)
    bpy.context.view_layer.objects.active = part
    bpy.context.view_layer.update()
    spec = importlib.util.spec_from_file_location("human_eye_v1_fixture_host_" + uuid.uuid4().hex, source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    manifest = {
        "kind": "disposable_far_origin_blender_v1_fixture", "blender_version": bpy.app.version_string,
        "scene_name": scene.name, "unit": "m", "coordinate_frame": "world", "file_saved": False,
        "focal_id": module.BlenderSceneHost.object_id(part),
        "reference_id": module.BlenderSceneHost.object_id(base),
        "obstacle_id": module.BlenderSceneHost.object_id(obstacle),
        "focal_name": part.name, "reference_name": base.name, "obstacle_name": obstacle.name,
        "initial_focal_pivot_world_m": [12.08, -7.04, 3.35], "initial_focal_yaw_deg": 17,
        "original_scene": original.name, "original_view_layer": layer.name,
        "original_selection": saved["selection"], "original_active": saved["active"],
        "original_summary": saved["original_summary"], "fixture_summary": _summary(scene),
        "truth_scope": "Independent direct world-vertex gap and host pivot/axes for known horizontal box fixture; not general mesh distance truth.",
    }
    _write(output / "live_fixture.json", manifest)
    return manifest


def cleanup(project_root, output_dir):
    import bpy
    _, output = _paths(project_root, output_dir)
    saved = bpy.app.driver_namespace.get(KEY)
    if not saved or saved["output"] != str(output):
        raise RuntimeError("No matching v1 fixture is registered for this evidence directory")
    original = saved["original"]
    bpy.context.window.scene = original
    bpy.context.window.view_layer = original.view_layers[saved["view_layer_name"]]
    for obj in original.objects:
        obj.select_set(obj.name in saved["selection"])
    bpy.context.view_layer.objects.active = original.objects.get(saved["active"]) if saved["active"] else None
    test_scene = saved.get("test_scene")
    test_name = test_scene.name if test_scene else None
    for obj in saved["objects"]:
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in saved["meshes"]:
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    if test_scene:
        bpy.data.scenes.remove(test_scene)
    result = {
        "original_scene_restored": bpy.context.window.scene == original,
        "original_objects_and_meshes_unchanged": _summary(original) == saved["original_summary"],
        "original_selection_restored": sorted(obj.name for obj in original.objects if obj.select_get()) == saved["selection"],
        "original_active_restored": getattr(bpy.context.view_layer.objects.active, "name", None) == saved["active"],
        "test_scene_removed": test_name not in bpy.data.scenes if test_name else True,
        "file_saved": False,
    }
    _write(output / "live_cleanup.json", result)
    bpy.app.driver_namespace.pop(KEY)
    return result

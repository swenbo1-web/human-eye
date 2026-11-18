"""Trusted current Blender reads for the assembly and terminal export."""

import hashlib
import json
import math
import os
from pathlib import Path
import time


def _object_id(obj):
    identity = [str(getattr(obj.library, "filepath", "")), str(obj.name_full)]
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "blender:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _matrix(matrix):
    return [[float(matrix[row][column]) for column in range(4)] for row in range(4)]


def _mesh_arrays(mesh, matrix, scale, *, include_polygons):
    points = [[float(vertex.co[axis]) for axis in range(3)] for vertex in mesh.vertices]
    # Blender's Matrix @ Vector rounds in float32. Match the ordered double
    # accumulation used by the complete-scene product capture.
    world = [
        [(sum(matrix[row][axis] * point[axis] for axis in range(3)) + matrix[row][3]) * scale
         for row in range(3)]
        for point in points
    ]
    if not all(math.isfinite(value) for point in world for value in point):
        raise ValueError("nonfinite_blender_world_points")
    mesh.calc_loop_triangles()
    arrays = {"vertices": points, "vertices_world_m": world,
              "triangles": [[int(value) for value in face.vertices] for face in mesh.loop_triangles],
              "polygon_count": len(mesh.polygons)}
    if include_polygons:
        arrays.update(polygons=[[int(value) for value in polygon.vertices] for polygon in mesh.polygons],
                      triangle_polygons=[int(face.polygon_index) for face in mesh.loop_triangles])
    return arrays


def _layer_collection(layer):
    return {"name": layer.name, "collection_name": layer.collection.name,
            "exclude": bool(layer.exclude), "hide_viewport": bool(layer.hide_viewport),
            "holdout": bool(layer.holdout), "indirect_only": bool(layer.indirect_only),
            "children": [_layer_collection(child) for child in layer.children]}


def _encode(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def capture_device(bpy, output_path, asset_sha256, *, terminal):
    started = time.perf_counter_ns()
    scene, layer = bpy.context.scene, bpy.context.view_layer
    graph = bpy.context.evaluated_depsgraph_get()
    units = scene.unit_settings
    scale = float(units.scale_length)
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("positive_finite_scene_unit_scale_required")
    source = {"kind": "actual_owned_Blender_evaluated_mesh", "pid": os.getpid(),
              "asset_sha256": asset_sha256, "asset_copy": bpy.data.filepath,
              "frame": int(scene.frame_current), "subframe": float(scene.frame_subframe),
              "view_layer": layer.name, "view_layer_id": "rna:" + str(int(layer.as_pointer())),
              "scene": scene.name, "scale_length": scale,
              "unit_settings": {"system": units.system, "length_unit": units.length_unit,
                                "scale_length": scale},
              "source_index_domain": "zero_based_object_local_current_evaluated_capture_triangle_rows"}
    objects = sorted((obj for obj in scene.objects if obj.type == "MESH"), key=lambda obj: obj.name)
    visible = [bool(obj.visible_get(view_layer=layer)) for obj in objects]
    display_closed = time.perf_counter_ns()
    meshes = []
    offsets = [0]
    for obj, participates in zip(objects, visible):
        evaluated = obj.evaluated_get(graph)
        if not evaluated.is_evaluated:
            raise ValueError("unevaluated_current_scene_mesh:" + obj.name)
        matrix = _matrix(evaluated.matrix_world)
        item = {
            "name": obj.name, "object_id": _object_id(obj), "instance_id": str(obj.session_uid),
            "visible_get": participates, "matrix_world": matrix,
        }
        if terminal:
            native_matrix = _matrix(obj.matrix_world)
            item.update(
                native_matrix_world=native_matrix,
                native=_mesh_arrays(obj.data, native_matrix, scale, include_polygons=True),
                mesh_name=obj.data.name, parent=None if obj.parent is None else obj.parent.name,
                modifiers=[{"name": modifier.name, "type": modifier.type} for modifier in obj.modifiers],
                display={"hide_get": bool(obj.hide_get(view_layer=layer)), "hide_viewport": bool(obj.hide_viewport),
                         "hide_render": bool(obj.hide_render), "display_type": obj.display_type,
                         "show_in_front": bool(obj.show_in_front),
                         "collections": sorted(collection.name for collection in obj.users_collection)},
            )
        temporary = evaluated.to_mesh()
        if temporary is None:
            raise ValueError("current_evaluated_mesh_unavailable:" + obj.name)
        try:
            arrays = _mesh_arrays(temporary, matrix, scale, include_polygons=True)
        finally:
            evaluated.to_mesh_clear()
        item["mesh_sha256"] = hashlib.sha256(_encode({"matrix_world": matrix, "scale_length": scale,
                                                       "evaluated": arrays})).hexdigest()
        if terminal:
            item["evaluated"] = arrays
        else:
            item.update(vertices=arrays["vertices_world_m"], vertices_local=arrays["vertices"],
                        triangles=arrays["triangles"], polygon_count=arrays["polygon_count"],
                        triangle_polygons=arrays["triangle_polygons"])
        meshes.append(item)
        offsets.append(offsets[-1] + len(arrays["triangles"]))
    geometry_closed = time.perf_counter_ns()
    packet = {
        "schema": "m4-live-assembly-terminal-source-v1" if terminal else "m4-live-assembly-native-scene-v1",
        "source": source, "objects": meshes, "source_face_offsets": offsets,
        "display_object_mask": visible,
        "display_scope": "active_view_layer_effective_viewport",
        "display_read": "Blender Object.visible_get(view_layer=current)",
        "started_ns": started, "display_read_closed_ns": display_closed,
        "geometry_read_closed_ns": geometry_closed,
    }
    if terminal:
        packet["layer_collections"] = _layer_collection(layer.layer_collection)
    raw = _encode(packet)
    encoded_closed = time.perf_counter_ns()
    with Path(output_path).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    print("M4_LIVE_ASSEMBLY_CAPTURE:" + json.dumps({
        "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        "pid": os.getpid(), "started_ns": started, "display_read_closed_ns": display_closed,
        "geometry_read_closed_ns": geometry_closed, "json_encoded_ns": encoded_closed,
        "file_closed_ns": time.perf_counter_ns(),
    }, separators=(",", ":")))

"""Shared Blender evidence metadata and batch-owned output validation."""

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def array_hash(values):
    values = np.ascontiguousarray(values)
    return digest(str(values.dtype).encode() + str(values.shape).encode() + values.tobytes())


def canonical_hash(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode())


def file_identity(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=digest(data))


def output_path(value, require_new=False):
    path = Path(value).resolve()
    if not path.is_relative_to(HERE):
        raise ValueError("output_outside_refine_batch")
    if require_new and path.exists():
        raise FileExistsError("output_exists_read_actual_state_before_retry_" + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path, value):
    path = output_path(path)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def resources():
    if os.name != "nt":
        return dict(CPU_s=time.process_time(), peak_working_set_bytes=None)
    class Memory(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    row = Memory()
    row.cb = ctypes.sizeof(row)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Memory), wintypes.DWORD]
    valid = psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(row), row.cb)
    return dict(CPU_s=time.process_time(), peak_working_set_bytes=int(row.PeakWorkingSetSize) if valid else None,
                working_set_bytes=int(row.WorkingSetSize) if valid else None)


def source_ids(mesh):
    attribute = mesh.attributes.get("m6_source_id")
    if attribute is None:
        return np.arange(len(mesh.vertices), dtype=np.int64)
    if attribute.domain != "POINT" or attribute.data_type != "INT":
        raise ValueError("source_ID_attribute_type_mismatch")
    values = np.empty(len(mesh.vertices), dtype=np.int32)
    attribute.data.foreach_get("value", values)
    values = values.astype(np.int64)
    if len(np.unique(values)) != len(values):
        raise ValueError("duplicated_mesh_source_IDs")
    return values


def mesh_arrays(obj):
    mesh = obj.data
    local = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", local)
    local = local.reshape(-1, 3)
    matrix = np.array(obj.matrix_world, dtype=np.float64)
    world = local.astype(np.float64) @ matrix[:3, :3].T + matrix[:3, 3]
    mesh.calc_loop_triangles()
    faces = np.array([tuple(face.vertices) for face in mesh.loop_triangles], dtype=np.int64).reshape(-1, 3)
    polygon_ids = np.array([face.polygon_index for face in mesh.loop_triangles], dtype=np.int64)
    counts = np.array([len(face.vertices) for face in mesh.polygons], dtype=np.int64)
    polygon_vertices = np.array([index for face in mesh.polygons for index in face.vertices], dtype=np.int64)
    return dict(vertices=world, vertices_world=world, vertices_local=local, faces=faces, source_ids=source_ids(mesh),
                matrix_world=matrix, poly_offsets=np.r_[0, np.cumsum(counts)], poly_vertices=polygon_vertices,
                triangle_polygon_ids=polygon_ids)


def socket_value(socket):
    if not hasattr(socket, "default_value"):
        return None
    value = socket.default_value
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "name"):
        return dict(ID_name=value.name)
    try:
        return list(value)
    except TypeError:
        return repr(value)


def node_tree_signature(tree):
    if tree is None:
        return None
    nodes = []
    for node in sorted(tree.nodes, key=lambda item: item.name):
        nodes.append(dict(name=node.name, type=node.bl_idname, mute=node.mute,
            image=getattr(getattr(node, "image", None), "name", None),
            inputs=[dict(name=socket.name, identifier=socket.identifier, value=socket_value(socket)) for socket in node.inputs]))
    links = sorted((link.from_node.name, link.from_socket.identifier, link.to_node.name, link.to_socket.identifier) for link in tree.links)
    return dict(nodes=nodes, links=links)


def mesh_metadata(obj, include_coordinates):
    mesh = obj.data
    arrays = mesh_arrays(obj)
    uv = []
    for layer in mesh.uv_layers:
        values = np.empty(len(layer.data) * 2, dtype=np.float32)
        layer.data.foreach_get("uv", values)
        uv.append(dict(name=layer.name, active_render=layer.active_render, uv_hash=array_hash(values)))
    groups = [[(item.group, item.weight) for item in vertex.groups] for vertex in mesh.vertices]
    result = dict(mesh_name=mesh.name, vertex_count=len(mesh.vertices), edge_count=len(mesh.edges), polygon_count=len(mesh.polygons),
        source_ids_hash=array_hash(arrays["source_ids"]), polygon_offsets_hash=array_hash(arrays["poly_offsets"]),
        polygon_vertices_hash=array_hash(arrays["poly_vertices"]),
        material_slots=[material.name if material else None for material in mesh.materials],
        material_indices_hash=array_hash(np.array([polygon.material_index for polygon in mesh.polygons], dtype=np.int32)),
        UV_layers=uv, active_UV=mesh.uv_layers.active.name if mesh.uv_layers.active else None,
        vertex_groups=[group.name for group in obj.vertex_groups], vertex_weights_hash=canonical_hash(groups),
        shape_keys=None if mesh.shape_keys is None else [dict(name=key.name, value=key.value,
            coordinates_hash=array_hash(np.array([tuple(v.co) for v in key.data], dtype=np.float32))) for key in mesh.shape_keys.key_blocks])
    if include_coordinates:
        result["vertices_local_hash"] = array_hash(arrays["vertices_local"])
    return result


def scene_signature(target):
    objects = []
    for obj in sorted(bpy.data.objects, key=lambda item: item.name):
        row = dict(name=obj.name, type=obj.type, data_name=getattr(obj.data, "name", None),
            matrix_world=[list(v) for v in obj.matrix_world], parent=obj.parent.name if obj.parent else None,
            hide_render=obj.hide_render, hide_viewport=obj.hide_viewport,
            modifiers=[dict(name=m.name, type=m.type, render=m.show_render, viewport=m.show_viewport) for m in obj.modifiers],
            constraints=[dict(name=c.name, type=c.type) for c in obj.constraints])
        if obj.type == "MESH":
            row["mesh"] = mesh_metadata(obj, include_coordinates=obj.name != target.name)
        elif obj.type == "CAMERA":
            row["camera"] = dict(type=obj.data.type, lens=obj.data.lens, ortho_scale=obj.data.ortho_scale,
                clip_start=obj.data.clip_start, clip_end=obj.data.clip_end)
        elif obj.type == "LIGHT":
            row["light"] = dict(type=obj.data.type, energy=obj.data.energy, color=list(obj.data.color))
        objects.append(row)
    materials = [dict(name=m.name, diffuse_color=list(m.diffuse_color), use_nodes=m.use_nodes,
                      nodes=node_tree_signature(m.node_tree)) for m in sorted(bpy.data.materials, key=lambda item: item.name)]
    images = []
    for image in sorted(bpy.data.images, key=lambda item: item.name):
        if image.source == "VIEWER":
            continue
        packed = bytes(image.packed_file.data) if image.packed_file else None
        images.append(dict(name=image.name, source=image.source, size=list(image.size), filepath=image.filepath,
            packed_bytes=len(packed) if packed is not None else 0, packed_sha256=digest(packed) if packed is not None else None,
            color_space=image.colorspace_settings.name))
    scenes = [dict(name=s.name, frame=s.frame_current, subframe=s.frame_subframe, objects=sorted(o.name for o in s.objects),
        camera=s.camera.name if s.camera else None, unit_system=s.unit_settings.system, unit_scale=s.unit_settings.scale_length,
        render_engine=s.render.engine, resolution=[s.render.resolution_x, s.render.resolution_y, s.render.resolution_percentage],
        world=s.world.name if s.world else None) for s in sorted(bpy.data.scenes, key=lambda item: item.name)]
    data = dict(objects=objects, materials=materials, images=images, scenes=scenes,
        libraries=[dict(name=item.name, filepath=item.filepath) for item in bpy.data.libraries])
    target_row = next(row for row in objects if row["name"] == target.name)
    return dict(**data, signature_sha256=canonical_hash(data),
        other_objects_sha256=canonical_hash([row for row in objects if row["name"] != target.name]),
        target_materials_sha256=canonical_hash(dict(materials=materials, images=images, target_mesh=target_row["mesh"])),
        scene_structure_sha256=canonical_hash(dict(scenes=scenes, object_structure=[{key:value for key,value in row.items() if key != "mesh"} for row in objects], libraries=data["libraries"])),
        target_topology_sha256=canonical_hash({key:target_row["mesh"][key] for key in ("vertex_count", "edge_count", "polygon_count", "source_ids_hash", "polygon_offsets_hash", "polygon_vertices_hash")}),
        scope="target native coordinates excluded here and exported separately. Derived loop triangles exported separately. Packed image bytes, node inputs, UVs, native polygon loops and non-target coordinates included.")


def get_target(job):
    target = bpy.data.objects.get(job["object_name"])
    if target is None or target.type != "MESH":
        raise ValueError("target_mesh_object_missing")
    return target


def assert_loaded(job):
    if Path(bpy.data.filepath).resolve() != Path(job["current_blend"]).resolve():
        raise ValueError("loaded_blend_does_not_match_job")


def execution_metadata(script, started, cpu):
    return dict(script=file_identity(script), shared_helper=file_identity(__file__), Blender_version=bpy.app.version_string,
        Blender_binary=bpy.app.binary_path, wall_s_before_write=time.perf_counter()-started,
        CPU_s_before_write=time.process_time()-cpu, resources=resources(), thread_limit=bpy.context.scene.render.threads)

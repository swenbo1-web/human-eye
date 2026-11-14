"""Read one isolated .blend in factory background Blender and export evidence."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import time

import bpy


def memory():
    if os.name != "nt":
        return {"status": "not_measured"}
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize",
            "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
            "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]
    row = Counters()
    row.cb = ctypes.sizeof(row)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(row), row.cb):
        return {"status": "failed", "winerror": ctypes.get_last_error()}
    return {"working_set_bytes": row.WorkingSetSize, "peak_working_set_bytes": row.PeakWorkingSetSize,
            "private_bytes": row.PrivateUsage, "scope": "collector process at sample; peak is process-lifetime"}


def animation(data):
    value = getattr(data, "animation_data", None)
    return {"has_animation_data": value is not None,
            "action": value.action.name if value and value.action else None,
            "drivers": len(value.drivers) if value else 0,
            "nla_tracks": len(value.nla_tracks) if value else 0}


def components(mesh):
    parent = list(range(len(mesh.vertices)))
    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index
    for edge in mesh.edges:
        a, b = (find(index) for index in edge.vertices)
        parent[b] = a
    groups = {}
    for vertex in mesh.vertices:
        groups.setdefault(find(vertex.index), []).append(vertex.index)
    return sorted((len(group) for group in groups.values()), reverse=True)


def mesh_summary(obj, depsgraph):
    mesh = obj.data
    mesh.calc_loop_triangles()
    assignments = sum(len(vertex.groups) for vertex in mesh.vertices)
    group_stats = [{"index": group.index, "name": group.name, "assignments": 0,
                    "nonzero_assignments": 0, "weight_sum": 0.} for group in obj.vertex_groups]
    totals = []
    for vertex in mesh.vertices:
        totals.append(sum(group.weight for group in vertex.groups))
        for group in vertex.groups:
            row = group_stats[group.group]
            row["assignments"] += 1
            row["nonzero_assignments"] += group.weight > 0
            row["weight_sum"] += group.weight
    evaluated = obj.evaluated_get(depsgraph)
    em = evaluated.to_mesh()
    try:
        em.calc_loop_triangles()
        evaluated_counts = {"vertices": len(em.vertices), "polygons": len(em.polygons),
                            "triangles": len(em.loop_triangles)}
    finally:
        evaluated.to_mesh_clear()
    keys = mesh.shape_keys
    return {"vertices": len(mesh.vertices), "edges": len(mesh.edges), "polygons": len(mesh.polygons),
            "triangles": len(mesh.loop_triangles), "connected_component_vertex_counts": components(mesh),
            "vertex_groups": group_stats, "weight_assignments": assignments,
            "vertex_weight_sum_min": min(totals, default=None), "vertex_weight_sum_max": max(totals, default=None),
            "shape_keys": None if keys is None else {
                "use_relative": keys.use_relative, "blocks": [{"name": block.name, "value": block.value,
                "vertices": len(block.data), "relative_key": block.relative_key.name if block.relative_key else None}
                for block in keys.key_blocks], "animation": animation(keys)},
            "mesh_animation": animation(mesh), "evaluated_counts": evaluated_counts}


def mesh_arrays(obj, mesh):
    mesh.calc_loop_triangles()
    return {"object_name": obj.name, "mesh_name": mesh.name, "matrix_world": [list(row) for row in obj.matrix_world],
            "vertex_ids": [vertex.index for vertex in mesh.vertices],
            "vertices_object": [list(vertex.co) for vertex in mesh.vertices],
            "vertices_world": [list(obj.matrix_world @ vertex.co) for vertex in mesh.vertices],
            "triangles": [list(triangle.vertices) for triangle in mesh.loop_triangles],
            "polygon_ids_by_triangle": [triangle.polygon_index for triangle in mesh.loop_triangles]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--object")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    started, cpu_started = time.perf_counter(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=True)
    before_memory = memory()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    objects = []
    for obj in sorted(bpy.data.objects, key=lambda item: item.name):
        row = {"name": obj.name, "type": obj.type, "data_name": getattr(obj.data, "name", None),
               "parent": obj.parent.name if obj.parent else None, "matrix_world": [list(v) for v in obj.matrix_world],
               "hide_render": obj.hide_render, "animation": animation(obj),
               "constraints": [{"name": constraint.name, "type": constraint.type} for constraint in obj.constraints],
               "modifiers": [{"name": mod.name, "type": mod.type, "show_viewport": mod.show_viewport,
                              "show_render": mod.show_render,
                              "armature_object": getattr(getattr(mod, "object", None), "name", None)}
                             for mod in obj.modifiers]}
        if obj.type == "MESH":
            row["mesh"] = mesh_summary(obj, depsgraph)
        if obj.type == "ARMATURE":
            row["bones"] = [{"name": bone.name, "parent": bone.parent.name if bone.parent else None,
                             "rest_matrix": [list(v) for v in bone.matrix_local],
                             "head_local": list(bone.head_local), "tail_local": list(bone.tail_local)}
                            for bone in obj.data.bones]
            row["pose"] = [{"name": bone.name, "matrix": [list(v) for v in bone.matrix],
                            "basis": [list(v) for v in bone.matrix_basis], "constraints": len(bone.constraints)}
                           for bone in obj.pose.bones]
        objects.append(row)
    images = []
    for image in bpy.data.images:
        path = image.filepath
        original_resolved = Path(bpy.path.abspath(path, start=str(args.original.parent))) if path else None
        copied_resolved = Path(bpy.path.abspath(path)) if path else None
        images.append({"name": image.name, "source": image.source, "size": list(image.size),
                       "packed": bool(image.packed_file), "packed_bytes": image.packed_file.size if image.packed_file else 0,
                       "filepath": path, "original_resolved": str(original_resolved) if original_resolved else None,
                       "original_external_exists": original_resolved.exists() if original_resolved else None,
                       "copy_external_exists": copied_resolved.exists() if copied_resolved else None})
    result = {"blender_version": bpy.app.version_string, "binary": bpy.app.binary_path,
              "loaded_file": bpy.data.filepath, "file_version": list(bpy.data.version),
              "autoexec_enabled": bpy.context.preferences.filepaths.use_scripts_auto_execute,
              "scenes": [{"name": scene.name, "frame": scene.frame_current, "subframe": scene.frame_subframe,
                          "unit_system": scene.unit_settings.system, "scale_length": scene.unit_settings.scale_length,
                          "object_names": [obj.name for obj in scene.objects]} for scene in bpy.data.scenes],
              "coordinate_frame": "Blender object local and world; right-handed, Z up; scene unit scale reported separately",
              "objects": objects, "images": images,
              "libraries": [{"name": lib.name, "filepath": lib.filepath} for lib in bpy.data.libraries],
              "armature_datablocks": [{"name": armature.name, "bones": len(armature.bones)} for armature in bpy.data.armatures],
              "shape_key_datablocks": [{"name": key.name, "blocks": len(key.key_blocks)} for key in bpy.data.shape_keys],
              "actions": [action.name for action in bpy.data.actions], "texts": [text.name for text in bpy.data.texts],
              "memory_at_entry": before_memory, "exported_object": None}
    if not args.object:
        candidates = [obj for obj in bpy.data.objects if obj.type == "MESH"]
        if not candidates:
            raise ValueError("no_mesh_objects")
        args.object = min(candidates, key=lambda obj: (-len(obj.data.vertices), obj.name)).name
    result["selection_rule"] = "largest raw mesh vertex count, ties by object name"
    if args.object:
        obj = bpy.data.objects[args.object]
        if obj.type != "MESH":
            raise ValueError("selected_object_is_not_mesh")
        raw = mesh_arrays(obj, obj.data)
        raw["vertex_groups"] = [{"index": group.index, "name": group.name} for group in obj.vertex_groups]
        raw["weights"] = [[[group.group, group.weight] for group in vertex.groups] for vertex in obj.data.vertices]
        evaluated = obj.evaluated_get(depsgraph)
        em = evaluated.to_mesh()
        try:
            final = mesh_arrays(evaluated, em)
        finally:
            evaluated.to_mesh_clear()
        equal = raw["triangles"] == final["triangles"] and raw["vertices_object"] == final["vertices_object"]
        result["exported_object"] = {"name": obj.name, "raw_file": "raw_selected.json", "evaluated_file": "evaluated_selected.json",
                                     "raw_evaluated_geometry_arrays_exactly_equal": equal,
                                     "same_index_status": "verified_equal_arrays_without_modifiers" if equal and not obj.modifiers else "not_established"}
        for name, value in (("raw_selected.json", raw), ("evaluated_selected.json", final)):
            (args.out / name).write_text(json.dumps(value, separators=(",", ":"), allow_nan=False), encoding="utf8")
    result["memory_at_end"] = memory()
    result["collector_wall_s"] = time.perf_counter() - started
    result["collector_cpu_s"] = time.process_time() - cpu_started
    (args.out / "native_inventory.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf8")
    print(json.dumps({"status": "collected", "objects": len(objects), "exported_object": args.object}))


main()

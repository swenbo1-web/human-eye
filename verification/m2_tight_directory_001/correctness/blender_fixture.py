"""Existing resident QA server with a finite asymmetric/concave input extension."""

import importlib.util
import math
from pathlib import Path
import sys

import bpy


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "verification/arch_resident_001/blender_fixture.py"
spec = importlib.util.spec_from_file_location("_existing_directory_resident_fixture", SOURCE)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
original_cube, original_control = base.cube, base.control


def custom_mesh(name, center, half):
    if name == "BluePart":
        points = [(0, 0, 0), (2 * half[0], 0, 0), (0, half[1], 0), (0, 0, half[2])]
        faces = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]
    elif name == "GreyBase":
        polygon = [(-1, -1), (1, -1), (1, -.25), (-.25, -.25), (-.25, 1), (-1, 1)]
        points = [(x * half[0], y * half[1], z * half[2]) for z in (-1, 1) for x, y in polygon]
        top = [(0, 1, 2), (0, 2, 3), (0, 3, 5), (3, 4, 5)]
        faces = [(c, b, a) for a, b, c in top] + [(a + 6, b + 6, c + 6) for a, b, c in top]
        for i in range(6):
            j = (i + 1) % 6
            faces.extend(((i, j, j + 6), (i, j + 6, i + 6)))
    else:
        obj = original_cube(name, center, half)
        if name == "Far00":
            # Preserve the old cube's surface and add one unreferenced extremal vertex.
            mesh = obj.data
            points = [tuple(vertex.co) for vertex in mesh.vertices] + [(4 * half[0], -.5 * half[1], 2 * half[2])]
            faces = [tuple(face.vertices) for face in mesh.polygons]
            mesh.clear_geometry()
            mesh.from_pydata(points, [], faces)
            mesh.update()
        return obj
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(points, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = center
    obj.rotation_euler = (math.radians(17), math.radians(-11), math.radians(37))
    return obj


def control(value):
    operation = value["op"]
    if operation == "oracle":
        rows = []
        graph = bpy.context.evaluated_depsgraph_get()
        for obj in bpy.context.scene.objects:
            if obj.type != "MESH":
                continue
            evaluated = obj.evaluated_get(graph)
            mesh = evaluated.to_mesh()
            try:
                rows.append({"name": obj.name, "name_full": obj.name_full,
                    "library_path": str(getattr(getattr(obj, "library", None), "filepath", "")),
                    "instance_id": str(obj.session_uid),
                    "vertices_local": [[float(value) for value in vertex.co] for vertex in mesh.vertices],
                    "matrix_world": [[float(value) for value in row] for row in evaluated.matrix_world],
                    "unit_scale_m": float(bpy.context.scene.unit_settings.scale_length)})
            finally:
                evaluated.to_mesh_clear()
        return {"objects": rows, "frame": bpy.context.scene.frame_current,
                "subframe": bpy.context.scene.frame_subframe, "pid": __import__("os").getpid()}
    if operation == "subframe":
        bpy.context.scene.frame_set(value['frame'], subframe=value['subframe'])
        bpy.context.view_layer.update()
        return {'ok': True}
    if operation == "rotate":
        bpy.data.objects[value["name"]].rotation_euler.z += value["radians"]
        bpy.context.view_layer.update()
        return {"ok": True}
    if operation == "redo":
        bpy.ops.ed.redo()
        bpy.context.view_layer.update()
        return {"ok": True}
    if operation == "quit":
        # The inherited blocking accept loop catches Exception only. Unwind the
        # background --python script so Blender can finish its normal teardown.
        raise SystemExit(0)
    return original_control(value)


base.cube, base.control = custom_mesh, control

if __name__ == "__main__":
    base.main()

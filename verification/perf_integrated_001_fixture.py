"""Author-only fixed Blender assets for PERF-INTEGRATED-001.

Run explicitly with a new output directory in a granted resource window.
Consumers receive the copied .blend and public question, not this source or
the author snapshots. This module has no Human Eye imports or solver.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from verification.visual004_assets import box

ROTATION = [[1 / 3, 2 / 3, -2 / 3, 0],
            [2 / 3, 1 / 3, 2 / 3, 0],
            [2 / 3, -2 / 3, -1 / 3, 0],
            [0, 0, 0, 1]]
IDENTITY = [[1, 0, 0, 0], [0, 1, 0, 0],
            [0, 0, 1, 0], [0, 0, 0, 1]]


def triangles(polygons):
    return [[face[0], face[index], face[index + 1]]
            for face in polygons for index in range(1, len(face) - 1)]


def annulus():
    tangent = 2 - math.sqrt(3)
    diagonal = math.sqrt(3) - 1
    outer = [[1, tangent], [diagonal, diagonal], [tangent, 1],
             [-tangent, 1], [-diagonal, diagonal], [-1, tangent],
             [-1, -tangent], [-diagonal, -diagonal], [-tangent, -1],
             [tangent, -1], [diagonal, -diagonal], [1, -tangent]]
    vertices = [[scale * x, scale * y, z]
                for z in (-0.1, 0.1) for scale in (1, 0.6)
                for x, y in outer]
    polygons = []
    for index in range(12):
        following = (index + 1) % 12
        polygons.extend([
            [index, following, following + 24, index + 24],
            [index + 12, index + 36, following + 36, following + 12],
            [following, index, index + 12, following + 12],
            [index + 24, following + 24, following + 36, index + 36],
        ])
    return vertices, polygons


def specifications(case):
    """Neutral object names and authored geometry only, with no answer fields."""
    if case == "control":
        objects = [
            ("Object_01", box([-0.05] * 3, [0.05] * 3), IDENTITY),
            ("Object_02", box([0.06, -0.01, -0.01],
                              [0.08, 0.01, 0.01]), IDENTITY),
        ]
        patch = {"target_name": "Object_01", "vertices": [
            {"index": index, "co": [0.065, y, z]}
            for index, y, z in [(1, -0.05, -0.05), (2, 0.05, -0.05),
                                (5, -0.05, 0.05), (6, 0.05, 0.05)]]}
        return objects, patch
    if case != "assembly":
        raise ValueError("Unknown fixed case")

    # The left probe has another exact rational rotation about the annulus
    # extrusion axis. Its matrix is R * Translation(-.605, 0, 0) * Rz(.6,.8).
    local = [[0.6, -0.8, 0, -0.605], [0.8, 0.6, 0, 0],
             [0, 0, 1, 0], [0, 0, 0, 1]]
    rotated_probe = [[sum(ROTATION[row][k] * local[k][column]
                          for k in range(4)) for column in range(4)]
                     for row in range(4)]
    objects = [
        ("Object_01", annulus(), ROTATION),
        ("Object_02", box([0.55, -0.02, -0.025],
                          [0.59, 0.02, 0.025]), ROTATION),
        ("Object_03", box([-0.02, -0.01, -0.025],
                          [0.02, 0.01, 0.025]), rotated_probe),
        ("Object_04", box([-0.025, 1.04, -0.025],
                          [0.025, 1.08, 0.025]), ROTATION),
    ]
    y = 0.6 * (2 - math.sqrt(3))
    patch = {"target_name": "Object_01", "vertices": [
        {"index": index, "co": [0.58, sign * y, z]}
        for index, sign, z in [(12, 1, -0.1), (23, -1, -0.1),
                               (36, 1, 0.1), (47, -1, 0.1)]]}
    return objects, patch


def snapshot(bpy, case, state):
    rows = []
    for obj in sorted(bpy.data.objects, key=lambda value: value.name):
        if obj.type != "MESH":
            raise ValueError("Fixture must contain only the fixed meshes")
        matrix = [[float(value) for value in row] for row in obj.matrix_world]
        points = [[float(value) for value in vertex.co]
                  for vertex in obj.data.vertices]
        # Preserve the actual float32 mesh/matrix values. Apply their affine
        # transform using Python float arithmetic for an auditable readback.
        world = [[sum(matrix[axis][k] * point[k] for k in range(3))
                  + matrix[axis][3] for axis in range(3)] for point in points]
        rows.append(dict(name=obj.name, vertices_local=points,
                         matrix_world=matrix, world_vertices=world,
                         faces=[list(face.vertices) for face in obj.data.polygons]))
    return dict(schema="perf-integrated-001-mesh-readback-v1", case=case,
                state=state, unit_scale_m=float(bpy.context.scene.unit_settings.scale_length),
                objects=rows)


def save_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def build(case, output):
    import bpy
    from mathutils import Matrix

    output = Path(output).resolve()
    allowed = (ROOT / "verification/fixes/perf_integrated_001").resolve()
    if not output.is_relative_to(allowed):
        raise ValueError("Output must be inside this batch's owned fixture directory")
    output.mkdir(parents=True, exist_ok=False)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    objects, patch = specifications(case)
    colors = [(0.12, 0.30, 0.65, 1), (0.75, 0.28, 0.12, 1),
              (0.34, 0.63, 0.22, 1), (0.64, 0.33, 0.62, 1)]
    for (name, (vertices, polygons), matrix), color in zip(objects, colors):
        mesh = bpy.data.meshes.new(name + "_Mesh")
        mesh.from_pydata(vertices, [], triangles(polygons))
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)
        obj.matrix_world = Matrix(matrix)
        obj.color = color
    bpy.context.view_layer.update()
    initial = snapshot(bpy, case, "initial")
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "scene.blend"))

    # Read both states from actual Blender data before either consumer starts.
    # The changed state remains unsaved, and the source asset is the initial one.
    mesh = bpy.data.objects[patch["target_name"]].data
    original = {row["index"]: tuple(mesh.vertices[row["index"]].co)
                for row in patch["vertices"]}
    try:
        for row in patch["vertices"]:
            mesh.vertices[row["index"]].co = row["co"]
        mesh.update()
        bpy.context.view_layer.update()
        changed = snapshot(bpy, case, "changed")
    finally:
        for index, co in original.items():
            mesh.vertices[index].co = co
        mesh.update()
        bpy.context.view_layer.update()
    if snapshot(bpy, case, "initial") != initial:
        raise ValueError("Author-only temporary patch did not restore the initial data")
    save_json(output / "qa_patch.json", patch)
    save_json(output / "author_mesh_snapshots.json", dict(initial=initial, changed=changed))
    save_json(output / "BUILD.json", dict(case=case, mesh_objects=len(objects),
              vertex_counts=[len(row[1][0]) for row in objects],
              triangle_counts=[len(triangles(row[1][1])) for row in objects],
              blend_state="initial", changed_snapshot="temporary unsaved QA mutation",
              product_calls=0, model_answers=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=("control", "assembly"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:]
                             if "--" in sys.argv else None)
    build(args.case, args.output)


if __name__ == "__main__":
    main()

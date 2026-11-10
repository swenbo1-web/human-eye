"""Reopen the new saved asset and only read its complete evaluated geometry."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import bpy

HERE = Path(__file__).resolve().parent


def need(value, reason):
    if not value:
        raise ValueError("T1_snapshot_" + reason)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--asset-sha256", required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    output = args.output.resolve()
    need(output.parent == HERE, "owned_output")
    asset = (output / "scene.blend").resolve()
    need(Path(bpy.data.filepath).resolve() == asset, "loaded_file_binding")
    before = hashlib.sha256(asset.read_bytes()).hexdigest()
    need(before == args.asset_sha256, "asset_pin")
    need(not any(name.startswith(("human_eye_plugin", "human_eye_module1_operators")) for name in sys.modules), "production_import")
    started = time.perf_counter_ns()
    graph = bpy.context.evaluated_depsgraph_get()
    rows = []
    for obj in sorted(bpy.context.scene.objects, key=lambda item: item.name):
        need(obj.type == "MESH", "nonmesh_object")
        evaluated = obj.evaluated_get(graph)
        mesh = evaluated.data
        rows.append({"name": obj.name, "mesh_name": mesh.name,
            "vertices_local": [list(vertex.co) for vertex in mesh.vertices],
            "matrix_world": [list(row) for row in evaluated.matrix_world],
            "faces": [list(poly.vertices) for poly in mesh.polygons],
            "parent": None if obj.parent is None else obj.parent.name,
            "modifiers": [modifier.type for modifier in obj.modifiers],
            "constraints": [constraint.type for constraint in obj.constraints],
            "animation_data": obj.animation_data is not None})
    need(hashlib.sha256(asset.read_bytes()).hexdigest() == before, "asset_changed_by_read")
    value = {"schema": "T1-complete-evaluated-snapshot-v1", "asset_sha256": before,
        "unit_scale_m": bpy.context.scene.unit_settings.scale_length,
        "frame": bpy.context.scene.frame_current, "objects": rows,
        "blender_version": bpy.app.version_string,
        "read_scope": "all scene mesh objects, all evaluated vertices, ordered triangles and full world matrices",
        "read_only": True, "setter_calls": 0, "save_calls": 0,
        "elapsed_ns": time.perf_counter_ns() - started}
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    need(len(raw) <= 131072, "snapshot_bytes")
    with (output / "SNAPSHOT.json").open("xb") as stream:
        stream.write(raw)


if __name__ == "__main__":
    main()

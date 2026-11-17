"""Construct one owned neutral mesh with source IDs and an explicit neutral world."""

import argparse
import json
from pathlib import Path
import sys
import time

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from blender_common import execution_metadata, file_identity, output_path, scene_signature, write_json


def main():
    started, cpu = time.perf_counter(), time.process_time()
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    job = json.loads(Path(args.job).read_bytes())
    source_before = file_identity(job["source_original"])
    output = output_path(job["output_blend"], require_new=True)
    with np.load(job["base_npz"], allow_pickle=False) as source:
        vertices = source["vertices"].astype(np.float64)
        faces = source["faces"].astype(np.int64)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mesh = bpy.data.meshes.new("surface_data")
    mesh.from_pydata(vertices.tolist(), [], faces.tolist())
    mesh.update()
    attribute = mesh.attributes.new("m6_source_id", "INT", "POINT")
    attribute.data.foreach_set("value", np.arange(len(vertices), dtype=np.int32))
    target = bpy.data.objects.new(job["object_name"], mesh)
    bpy.context.scene.collection.objects.link(target)
    bpy.context.view_layer.objects.active = target
    target.select_set(True)
    material = bpy.data.materials.new("neutral_surface")
    material.diffuse_color = (.6, .64, .7, 1.)
    mesh.materials.append(material)
    world = bpy.data.worlds.new("neutral_world")
    world.color = (.8, .8, .8)
    bpy.context.scene.world = world
    bpy.context.scene.unit_settings.system = "NONE"
    bpy.context.scene.unit_settings.scale_length = 1.
    bpy.context.scene.render.threads_mode = "FIXED"
    bpy.context.scene.render.threads = 1
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False, relative_remap=False)
    if file_identity(job["source_original"]) != source_before:
        raise ValueError("original_source_changed")
    write_json(job["receipt_path"], dict(status="saved", operation="create_baseline", output_blend=file_identity(output),
        input_packet=file_identity(job["base_npz"]), original_source=source_before, object_name=target.name,
        vertex_count=len(mesh.vertices), native_polygons=len(mesh.polygons),
        source_ID_mapping="POINT INT m6_source_id equals input packet row", unit="source_native_physical_length_unlabelled",
        scene_signature=scene_signature(target), execution=execution_metadata(__file__, started, cpu)))
    print(json.dumps(dict(status="saved", output_blend=str(output))), flush=True)


if __name__ == "__main__":
    main()

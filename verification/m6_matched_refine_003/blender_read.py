"""Independently export actual saved Blender mesh bytes in a fresh process."""

import argparse
import json
from pathlib import Path
import sys
import time
import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from blender_common import (assert_loaded, execution_metadata, file_identity, get_target,
    output_path, scene_signature, source_ids, write_json)


def main():
    started, cpu = time.perf_counter(), time.process_time()
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    job = json.loads(Path(args.job).read_bytes())
    assert_loaded(job)
    before_identity = file_identity(job["current_blend"])
    if job.get("expected_input_sha256") and before_identity["sha256"] != job["expected_input_sha256"]:
        raise ValueError("saved_blend_identity_mismatch")
    target = get_target(job)
    mesh = target.data
    # Export from the reopened Blender data blocks. No editor receipt arrays are read.
    native = np.array([tuple(vertex.co) for vertex in mesh.vertices], dtype=np.float32)
    transform = np.array([tuple(row) for row in target.matrix_world], dtype=np.float64)
    homogeneous = np.column_stack((native.astype(np.float64), np.ones(len(native))))
    world = (transform @ homogeneous.T).T[:, :3]
    mesh.calc_loop_triangles()
    triangles = np.array([tuple(face.vertices) for face in mesh.loop_triangles], dtype=np.int64).reshape(-1,3)
    polygon_ids = np.array([face.polygon_index for face in mesh.loop_triangles], dtype=np.int64)
    offsets = [0]
    polygon_vertices = []
    for polygon in mesh.polygons:
        polygon_vertices.extend(polygon.vertices)
        offsets.append(len(polygon_vertices))
    arrays = dict(vertices=world, vertices_world=world, vertices_local=native, matrix_world=transform,
        faces=triangles, source_ids=source_ids(mesh), poly_offsets=np.array(offsets, dtype=np.int64),
        poly_vertices=np.array(polygon_vertices, dtype=np.int64), triangle_polygon_ids=polygon_ids)
    path = output_path(job["readback_npz"], require_new=True)
    np.savez_compressed(path, **arrays)
    signature = scene_signature(target)
    write_json(job["scene_signature_json"], signature)
    if job.get("local_obj"):
        output = output_path(job["local_obj"], require_new=True)
        with np.load(job["base_npz"], allow_pickle=False) as region:
            selected = region["F_source_ids"].astype(np.int64)
        keep = np.isin(triangles, selected).all(axis=1)
        local_faces = triangles[keep]
        ids = np.unique(local_faces)
        lookup = {int(value): index+1 for index,value in enumerate(ids)}
        with output.open("x", encoding="utf8", newline="\n") as stream:
            stream.write("# Actual independent Blender readback, world coordinates, source vertex mapping follows comments\n")
            for index in ids:
                stream.write("# source_id " + str(int(arrays["source_ids"][index])) + "\n")
                stream.write("v " + " ".join(format(float(value), ".17g") for value in world[index]) + "\n")
            for face in local_faces:
                stream.write("f " + " ".join(str(lookup[int(value)]) for value in face) + "\n")
    after_identity = file_identity(job["current_blend"])
    if before_identity != after_identity:
        raise ValueError("reader_changed_saved_blend")
    result = dict(status="read_actual_saved_blend", input_blend=before_identity, input_unchanged=True,
        readback_npz=file_identity(path), scene_signature_json=file_identity(job["scene_signature_json"]),
        object_name=target.name, mesh_name=mesh.name, vertices=len(native), native_polygons=len(mesh.polygons), loop_triangles=len(triangles),
        coordinate_contract="local float32 values from Blender vertex.co, world computed in float64 from saved matrix and native values",
        scene_fingerprints={key:signature[key] for key in ("other_objects_sha256", "target_materials_sha256", "scene_structure_sha256", "target_topology_sha256")},
        writer_arrays_or_receipts_read=False, execution=execution_metadata(__file__, started, cpu))
    write_json(job["receipt_path"], result)
    print(json.dumps(dict(status=result["status"], vertices=len(native), polygons=len(mesh.polygons), readback=str(path))))


if __name__ == "__main__":
    main()

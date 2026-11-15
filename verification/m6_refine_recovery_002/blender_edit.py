"""Apply only consumer-submitted sparse coordinates to an isolated blend."""

import argparse
import json
from pathlib import Path
import sys
import time
import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from blender_common import (assert_loaded, execution_metadata, file_identity, get_target, mesh_arrays,
    output_path, scene_signature, source_ids, write_json)


def create_baseline(job):
    output = output_path(job["output_blend"], require_new=True)
    with np.load(job["base_npz"], allow_pickle=False) as source:
        vertices = source["vertices"].astype(np.float64)
        faces = source["faces"].astype(np.int64)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mesh = bpy.data.meshes.new("M6_face_current_surface")
    mesh.from_pydata(vertices.tolist(), [], faces.tolist())
    mesh.update()
    attribute = mesh.attributes.new("m6_source_id", "INT", "POINT")
    attribute.data.foreach_set("value", np.arange(len(vertices), dtype=np.int32))
    target = bpy.data.objects.new(job["object_name"], mesh)
    bpy.context.scene.collection.objects.link(target)
    bpy.context.view_layer.objects.active = target
    target.select_set(True)
    material = bpy.data.materials.new("M6 neutral current surface")
    material.diffuse_color = (.6, .64, .7, 1.)
    mesh.materials.append(material)
    bpy.context.scene.render.threads_mode = "FIXED"
    bpy.context.scene.render.threads = 1
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False, relative_remap=False)
    return dict(operation="create_baseline", output_blend=file_identity(output), input_packet=file_identity(job["base_npz"]),
        object_name=target.name, vertex_count=len(mesh.vertices), native_polygons=len(mesh.polygons),
        source_ID_mapping="POINT INT m6_source_id equals current packet row", scene_signature=scene_signature(target))


def edit(job):
    assert_loaded(job)
    output = output_path(job["output_blend"], require_new=True)
    current_identity = file_identity(job["current_blend"])
    if job.get("expected_input_sha256") and current_identity["sha256"] != job["expected_input_sha256"]:
        raise ValueError("input_blend_version_changed")
    target = get_target(job)
    before = mesh_arrays(target)
    signature_before = scene_signature(target)
    with np.load(job["allowed_ids_path"], allow_pickle=False) as source:
        allowed = source["I_ids"].astype(np.int64)
    with np.load(job["edit_payload"], allow_pickle=False) as payload:
        submitted = payload["source_ids"]
        if submitted.ndim != 1 or not np.issubdtype(submitted.dtype, np.integer):
            raise ValueError("sparse_source_IDs_require_integer_vector")
        submitted = submitted.astype(np.int64)
        modes = [name for name in ("positions_world", "displacements_world") if name in payload]
        if len(modes) != 1:
            raise ValueError("submit_positions_or_displacements_exclusively")
        values = payload[modes[0]].astype(np.float64)
    if len(submitted) == 0 or len(np.unique(submitted)) != len(submitted) or not np.isin(submitted, allowed).all():
        raise ValueError("sparse_IDs_empty_duplicated_or_outside_allowed_I")
    if values.shape != (len(submitted), 3) or not np.isfinite(values).all():
        raise ValueError("sparse_values_invalid_shape_or_nonfinite")
    mapping = {int(value): index for index, value in enumerate(source_ids(target.data))}
    indices = np.array([mapping[int(value)] for value in submitted], dtype=np.int64)
    requested_world = values if modes[0] == "positions_world" else before["vertices_world"][indices] + values
    inverse = np.linalg.inv(before["matrix_world"])
    local_positions = requested_world @ inverse[:3, :3].T + inverse[:3, 3]
    with np.errstate(over="ignore", invalid="ignore"):
        native_positions = local_positions.astype(np.float32)
    if not np.isfinite(native_positions).all():
        raise ValueError("submitted_values_not_representable_as_finite_Blender_coordinates")
    for index, position in zip(indices, local_positions):
        target.data.vertices[int(index)].co = position.tolist()
    target.data.update()
    bpy.context.view_layer.update()
    after = mesh_arrays(target)
    signature_after = scene_signature(target)
    outside = ~np.isin(before["source_ids"], submitted)
    if before["vertices_local"][outside].tobytes() != after["vertices_local"][outside].tobytes():
        raise ValueError("unsubmitted_native_coordinates_changed")
    if any(before[key].tobytes() != after[key].tobytes() for key in ("source_ids", "poly_offsets", "poly_vertices")):
        raise ValueError("native_polygon_topology_or_source_mapping_changed")
    if signature_before["signature_sha256"] != signature_after["signature_sha256"]:
        raise ValueError("scene_or_material_metadata_changed_in_edit")
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False, relative_remap=False)
    return dict(operation="sparse_edit_and_save", operation_id=job.get("operation_id"), input_blend=current_identity,
        output_blend=file_identity(output), submitted_payload=file_identity(job["edit_payload"]), submitted_source_ids=submitted.tolist(),
        submitted_mode=modes[0], actual_before_world=before["vertices_world"][indices].tolist(),
        actual_after_world=after["vertices_world"][indices].tolist(), actual_before_local=before["vertices_local"][indices].tolist(),
        actual_after_local=after["vertices_local"][indices].tolist(), maximum_world_quantization_error=float(np.linalg.norm(after["vertices_world"][indices]-requested_world, axis=1).max()),
        native_outside_submitted_bitwise=True, native_topology_preserved=True,
        derived_loop_triangles_unchanged=bool(np.array_equal(before["faces"], after["faces"])),
        scene_signature_before=signature_before, scene_signature_after=signature_after,
        clamping_or_direction_substitution=False, sparse_values_source="consumer submitted values only",
        independent_readback_required=True)


def main():
    started, cpu = time.perf_counter(), time.process_time()
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--operation", choices=("edit", "create_baseline"))
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    job = json.loads(Path(args.job).read_bytes())
    source_before = file_identity(job["source_original"]) if job.get("source_original") else None
    operation = args.operation or job.get("operation", "edit")
    result = create_baseline(job) if operation == "create_baseline" else edit(job)
    source_after = file_identity(job["source_original"]) if source_before else None
    if source_before != source_after:
        raise ValueError("original_source_file_changed")
    result.update(status="saved", original_source_before=source_before, original_source_after=source_after,
                  execution=execution_metadata(__file__, started, cpu))
    write_json(job["receipt_path"], result)
    print(json.dumps(dict(status="saved", output_blend=result["output_blend"]["path"], operation=operation)))


if __name__ == "__main__":
    main()

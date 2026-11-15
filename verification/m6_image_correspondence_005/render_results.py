"""Render final actual saved models with the shared four reference cameras."""

import argparse
import hashlib
from pathlib import Path
import struct
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from delivery_common import (absolute, ensure_job, existing_job, job_cost, merge_index, session_names,
                             snapshot_session, verify_identity, verify_snapshot)

CAMERA_FIELDS = ("specification", "camera_matrix_world", "world_to_image_affine_2_by_3",
                 "world_to_image_offset", "pixel_convention")


def check_png(image, resolution):
    verify_identity(image)
    with absolute(image["path"]).open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError("render_output_requires_actual_PNG_" + image["path"])
    if list(struct.unpack(">II", header[16:24])) != list(resolution):
        raise ValueError("render_PNG_dimensions_differ_from_frozen_camera")


def shared_inputs():
    cameras, binding, case = read("CAMERAS.json"), read("IMAGE_BINDING.json"), read("CASE_BINDING.json")
    specifications = cameras["views"]
    if cameras["geometry_scale"] != 1. or cameras["displacement_scale"] != 1. or len(specifications) != 4:
        raise ValueError("four_fixed_unscaled_delivery_views_required")
    expected_roles = [role + "_" + specification["name"] for role in ("normal", "current") for specification in specifications]
    if [row["role"] for row in binding["images"]] != expected_roles:
        raise ValueError("shared_normal_current_image_roles_changed")
    for index, specification in enumerate(specifications):
        normal, current = binding["images"][index], binding["images"][index + 4]
        if normal["camera"] != current["camera"] or normal["camera"]["specification"] != specification:
            raise ValueError("shared_input_camera_mismatch")
        check_png(normal, specification["resolution"])
        check_png(current, specification["resolution"])
    # Retain the exact renderer, material/shading setup and source helper used for the inputs.
    for provenance in binding["render_provenance"]:
        verify_identity(provenance["receipt"])
        verify_identity(provenance["run"])
        receipt = read(absolute(provenance["receipt"]["path"]))
        recorded_run = read(absolute(provenance["run"]["path"]))
        if recorded_run["receipt"] != receipt or recorded_run["process"]["returncode"] != 0:
            raise ValueError("reused_input_render_receipt_or_exit_changed")
        role = "normal" if provenance["label"] == "input_normal_render" else "current"
        if receipt["current_blend"]["sha256"] != binding[role + "_saved_blend"]["sha256"]:
            raise ValueError("reused_input_render_geometry_differs_from_fixed_saved_blend")
        for key, filename in (("script", "blender_render.py"), ("shared_helper", "blender_common.py")):
            if receipt["execution"][key]["sha256"] != identity(HERE / filename)["sha256"]:
                raise ValueError("shared_input_renderer_source_changed")
        if receipt["geometry_scale"] != 1. or receipt["displacement_scale"] != 1.:
            raise ValueError("shared_input_render_scale_changed")
    for key in ("normal_blend", "current_blend", "original"):
        verify_identity(case[key])
    return cameras, binding, case


def render_job(state, specifications, output):
    spec = read(absolute(state["source_spec"]))
    return dict(current_blend=str(absolute(state["current_blend"])), source_original=spec["source_original"],
        object_name=spec["object_name"], output_dir=str(output / "after_views"), views=specifications)


def geometry_hash(array):
    import numpy as np
    array = np.ascontiguousarray(array)
    return hashlib.sha256(str(array.dtype).encode() + str(array.shape).encode() + array.tobytes()).hexdigest()


def render_session(name, cameras, binding, case):
    started, cpu = time.perf_counter(), time.process_time()
    state, snapshot = snapshot_session(name)
    output = HERE / "private/results" / name
    output.mkdir(parents=True, exist_ok=True)
    result_path = output / "RESULT.json"
    audit_path = HERE / "private/final_verify" / name / "AUDIT.json"
    audit = read(audit_path)
    if audit["snapshot"] != snapshot or audit["audit_status"] != "pass":
        raise ValueError("render_requires_matching_final_saved_file_audit_" + name)
    for key in ("fresh_readback", "local_OBJ", "reader_receipt"):
        verify_identity(audit["artifacts"][key])
    input_identity = dict(cameras=identity(HERE / "CAMERAS.json"), image_binding=identity(HERE / "IMAGE_BINDING.json"),
                          case_binding=identity(HERE / "CASE_BINDING.json"), final_audit=identity(audit_path))
    label = "final_render_" + name
    job = render_job(state, cameras["views"], output)
    if result_path.exists():
        result = read(result_path)
        if result["snapshot"] != snapshot or result["inputs"] != input_identity:
            raise ValueError("final_render_inputs_changed_" + name)
        verify_snapshot(snapshot)
        for image in result["after_images"]:
            check_png(image, image["camera"]["specification"]["resolution"])
        for expected in result["models"].values():
            verify_identity(expected)
        existing_job("blender_render.py", job, label)
        return result, True
    record, reused_job = ensure_job("blender_render.py", job, label)
    receipt = record["receipt"]
    checks = dict(actual_saved_render=receipt["status"] == "rendered_actual_saved_full_character",
        correct_final_blend=receipt["current_blend"]["sha256"] == snapshot["saved_blend"]["sha256"],
        geometry_scale_one=receipt["geometry_scale"] == 1., displacement_scale_one=receipt["displacement_scale"] == 1.,
        render_changes_unsaved=receipt["scene_changes_saved"] is False,
        four_views=len(receipt["views"]) == 4)
    after_images, comparisons = [], []
    for index, specification in enumerate(cameras["views"]):
        view = receipt["views"][index]
        normal, current = binding["images"][index], binding["images"][index + 4]
        camera = {key: view[key] for key in CAMERA_FIELDS}
        checks["camera_matches_normal_and_current_" + specification["name"]] = camera == normal["camera"] == current["camera"]
        check_png(view["image"], specification["resolution"])
        image = dict(view["image"], role="after_" + specification["name"], camera=camera,
                     width=specification["resolution"][0], height=specification["resolution"][1], mimeType="image/png",
                     render_wall_s=view["render_wall_s"])
        after_images.append(image)
        comparisons.append(dict(view=specification["name"], normal=normal["path"], before=current["path"],
            after=image["path"], normal_sha256=normal["sha256"], before_sha256=current["sha256"], after_sha256=image["sha256"],
            camera_specification=specification, geometry_scale=1., displacement_scale=1.))
    from evaluate import packet
    fresh = packet(absolute(audit["artifacts"]["fresh_readback"]["path"]))
    for receipt_key, packet_key in (("native_coordinates_sha256", "vertices_local"), ("actual_loop_triangles_sha256", "faces")):
        checks["render_matches_final_readback_" + packet_key] = receipt[receipt_key] == geometry_hash(fresh[packet_key])
    verify_snapshot(snapshot)
    checks["session_and_model_preserved"] = True
    models = dict(normal=case["normal_blend"], before=case["current_blend"], after=snapshot["saved_blend"],
                  before_local_OBJ=identity(HERE / "private/cases/repair/before_local.obj"), after_local_OBJ=audit["artifacts"]["local_OBJ"])
    result = dict(session=name, stage=snapshot["stage"], route=snapshot["route"], version=state["version"],
        status="pass" if all(checks.values()) else "fail", checks=checks, snapshot=snapshot, inputs=input_identity,
        comparisons=comparisons, normal_images=[row["path"] for row in binding["images"][:4]],
        before_images=[row["path"] for row in binding["images"][4:]], after_images=after_images, models=models,
        geometry_scale=1., displacement_scale=1., job_label=label,
        world_export_hash_observation=dict(render=receipt["vertices_world_sha256"], fresh_readback=geometry_hash(fresh["vertices_world"]),
            equal=receipt["vertices_world_sha256"] == geometry_hash(fresh["vertices_world"]),
            coordinate_formulas="Renderer uses native @ matrix3x3.T + translation. Reader uses homogeneous matrix multiplication. Exact native values and actual faces are compared above."),
        render_receipt=identity(absolute(record["receipt_path"])), render_job=identity(HERE / "private/jobs" / label / "run.json"),
        Blender_cost=job_cost(record), job_reused_at_first_index=reused_job,
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
        shared_PNG_new_copy_count=0, new_after_PNG_count=4)
    write(result_path, result)
    return result, reused_job


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("v1", "v2", "all"), default="v1")
    args = parser.parse_args()
    started, cpu = time.perf_counter(), time.process_time()
    cameras, binding, case = shared_inputs()
    rows, reused, new_jobs = [], [], []
    for name in session_names(args.stage):
        result, cached = render_session(name, cameras, binding, case)
        rows.append(result)
        (reused if cached else new_jobs).append(result["job_label"])
        print(name, result["status"], "four saved-file views", flush=True)
    combined = merge_index(HERE / "VIEWABLES.json", args.stage, rows)
    result = dict(cycle_id="M6-IMAGE-CORRESPONDENCE-005", stage=args.stage,
        status="pass" if all(row["status"] == "pass" for row in combined) else "fail", sessions=combined,
        shared_images=binding["images"], unique_image_count=8 + 4 * len(combined),
        new_Blender_render_jobs=len(new_jobs), new_job_labels=new_jobs, reused_job_labels=reused,
        unique_Blender_render_labels=[row["job_label"] for row in combined],
        geometry_scale=1., displacement_scale=1., shared_PNG_new_copy_count=0,
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
        unique_nested_Blender_wall_s=sum(row["Blender_cost"]["wall_s"] for row in combined),
        source_identities=[identity(HERE / name) for name in ("render_results.py", "delivery_common.py", "blender_render.py", "blender_common.py")])
    write("VIEWABLES_" + args.stage + ".json", result)
    write("VIEWABLES.json", result)
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""Run the hidden smoothstep feasibility control on saved Blender copies."""

from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
import numpy as np
from background import run_job
from evaluate import evaluate_packets


def unit(vector):
    vector = np.asarray(vector, dtype=np.float64)
    length = float(np.linalg.norm(vector))
    if not np.isfinite(length) or length <= 0:
        raise ValueError("unavailable_reference_camera_direction")
    return vector / length


def freeze_render_spec(initial, spec):
    """Frame actual initial geometry and choose directions before editing."""
    vertices = initial["vertices"]
    faces = initial["faces"]
    selected = np.zeros(len(vertices), dtype=bool)
    selected[initial["F_source_ids"]] = True
    edges = np.unique(np.sort(np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]])), axis=1), axis=0)
    for _ in range(2):
        selected[edges[selected[edges].any(axis=1)].ravel()] = True
    displayed = vertices[np.unique(faces[selected[faces].all(axis=1)])]
    target = (displayed.min(axis=0) + displayed.max(axis=0)) / 2
    normal = unit(initial["n0"][int(spec["center_source_id"])])
    covariance = np.cov(displayed.T)
    _, axes = np.linalg.eigh(covariance)
    candidates = axes.T[::-1]
    projected = candidates - (candidates @ normal)[:, None] * normal
    tangent = unit(projected[int(np.argmax(np.linalg.norm(projected, axis=1)))])
    # Eigenvector sign is fixed so archived camera directions are reproducible.
    if tangent[int(np.argmax(np.abs(tangent)))] < 0:
        tangent = -tangent
    bitangent = unit(np.cross(normal, tangent))
    mean_normal = np.mean(initial["n0"][initial["F_source_ids"]], axis=0)
    return dict(
        target_world=target.tolist(),
        span=float(np.linalg.norm(np.ptp(displayed, axis=0))) * 1.2,
        view_directions=[unit(normal + .3*tangent + .15*bitangent).tolist(),
                         unit(tangent + .22*normal).tolist(),
                         unit(bitangent + .22*normal).tolist()],
        resolution=[640, 640], context_rings=2, samples=12,
        source="actual initial saved Blender readback, frozen before reference edit",
        direction_selection="center initial smoothed normal with covariance tangent of actual local two-ring context",
        center_source_id=int(spec["center_source_id"]),
        center_normal=normal.tolist(), normal_mean_F=mean_normal.tolist(),
        normal_mean_F_length=float(np.linalg.norm(mean_normal)),
        geometry_scale=1.0, displacement_scale=1.0,
        h=float(spec["h"]), ell=float(spec["ell"]), unit=spec["unit"])


def run_case(case):
    started, cpu = time.perf_counter(), time.process_time()
    case_id = case["case_id"]
    source_dir = HERE / "private/cases" / case_id
    directory = HERE / "private/reference" / case_id
    directory.mkdir(parents=True, exist_ok=False)
    initial_path, spec_path = source_dir / "initial.npz", source_dir / "spec.json"
    spec = read(spec_path)
    with np.load(initial_path, allow_pickle=False) as package:
        initial = {key: package[key] for key in package.files}
    original_before = identity(case["source_original"])
    before_blend = directory / "before.blend"
    shutil.copyfile(case["base_blend_path"], before_blend)
    if identity(before_blend)["sha256"] != identity(case["base_blend_path"])["sha256"]:
        raise ValueError("reference_baseline_copy_differs")
    I = initial["I_ids"].astype(np.int64)
    distance = initial["boundary_distance"][I]
    finite = np.isfinite(distance)
    maximum = float(distance[finite].max())
    if maximum <= 0 or maximum != float(spec["local_distance_max"]):
        raise ValueError("reference_distance_maximum_differs_from_fixed_spec")
    u = np.zeros(len(I), dtype=np.float64)
    u[finite] = distance[finite] / maximum
    amplitude = (u*u*(3-2*u)) * float(spec["h"])
    delta = amplitude[:, None] * initial["n0"][I]
    payload_path = directory / "reference_payload.npz"
    np.savez_compressed(payload_path, source_ids=I, displacements_world=delta)
    render_spec_path = directory / "render_spec.json"
    render_spec = freeze_render_spec(initial, spec)
    write(render_spec_path.relative_to(HERE), render_spec)
    jobs = []
    common_job = dict(case_id=case_id, object_name=case["object_name"],
                      base_npz=str(initial_path), source_original=case["source_original"])
    before_packet, before_scene = directory / "before_readback.npz", directory / "before_scene.json"
    jobs.append(run_job("blender_read.py", dict(common_job, current_blend=str(before_blend),
        readback_npz=str(before_packet), scene_signature_json=str(before_scene),
        local_obj=str(directory / "before_local.obj")), case_id + "_reference_before_read"))
    after_blend = directory / "after.blend"
    jobs.append(run_job("blender_edit.py", dict(common_job, current_blend=str(before_blend),
        output_blend=str(after_blend), allowed_ids_path=str(initial_path),
        edit_payload=str(payload_path), expected_input_sha256=identity(before_blend)["sha256"],
        operation_id=case_id + "_independent_reference"), case_id + "_reference_edit"))
    after_packet, after_scene = directory / "after_readback.npz", directory / "after_scene.json"
    jobs.append(run_job("blender_read.py", dict(common_job, current_blend=str(after_blend),
        readback_npz=str(after_packet), scene_signature_json=str(after_scene),
        local_obj=str(directory / "after_local.obj")), case_id + "_reference_after_read"))
    evaluation = evaluate_packets(before_packet, after_packet, initial_path, spec_path,
        before_state_path=before_scene, after_state_path=after_scene)
    quality_path = directory / "quality.json"
    write(quality_path.relative_to(HERE), evaluation)
    for state, blend_path in (("before", before_blend), ("after", after_blend)):
        jobs.append(run_job("blender_render.py", dict(common_job, current_blend=str(blend_path),
            output_dir=str(directory / (state + "_views")), render_spec=str(render_spec_path)),
            case_id + "_reference_" + state + "_render"))
    if identity(case["source_original"]) != original_before:
        raise ValueError("reference_control_changed_original_source")
    renders = [job for job in jobs if job["script"]["path"].endswith("blender_render.py")]
    if renders[0]["receipt"]["render_spec_sha256"] != renders[1]["receipt"]["render_spec_sha256"]:
        raise ValueError("reference_render_cameras_differ")
    row = dict(case_id=case_id, status=evaluation["status"], checks=evaluation["checks"],
        center_over_h=evaluation["displacement"]["center_over_h"],
        core_median_over_h=evaluation["displacement"]["core_median_over_h"],
        maximum_gradient=evaluation["transition"]["edge_displacement_gradient"]["maximum"],
        maximum_normal_change_deg=evaluation["template_faces"]["affected_normal_angle_deg"]["maximum"],
        reference_recipe="finite I smoothstep(D/Dmax)*h*n0, unreachable I zero displacement",
        unreachable_I=I[~finite].tolist(), reference_payload=identity(payload_path),
        initial=identity(initial_path), fixed_spec=identity(spec_path), quality=identity(quality_path),
        render_spec=identity(render_spec_path), camera_normal_mean_F_length=render_spec["normal_mean_F_length"],
        original_source_unchanged=True, original_source=original_before,
        jobs=[dict(label=job["label"], wall_s=job["wall_s"], receipt_path=job["receipt_path"],
                   process=job["process"], receipt=job["receipt"]) for job in jobs],
        wall_s=time.perf_counter()-started, cpu_s=time.process_time()-cpu,
        consumer_input_exposure=False, thresholds_changed=False)
    write((directory / "result.json").relative_to(HERE), row)
    print(case_id, "reference", row["status"], "center/h", row["center_over_h"],
          "core/h", row["core_median_over_h"], "gradient", row["maximum_gradient"],
          "normal_deg", row["maximum_normal_change_deg"], flush=True)
    return row


def main():
    started, cpu = time.perf_counter(), time.process_time()
    if (HERE / "REFERENCE_CONTROL.json").exists():
        raise RuntimeError("reference_control_already_recorded")
    sources = read("SOURCES.json")
    rows = []
    for case in sources["cases"]:
        rows.append(run_case(case))
        write("private/reference/progress.json", dict(completed_cases=rows))
    write("REFERENCE_CONTROL.json", dict(
        purpose="independent hidden feasibility control before consumer runs",
        cases=rows, source=identity(__file__),
        dependencies=[identity(HERE / name) for name in ("evaluate.py", "quality.py", "background.py",
            "blender_edit.py", "blender_read.py", "blender_render.py", "blender_common.py")],
        input_records=[identity(HERE / name) for name in ("SOURCES.json", "BASELINES.json", "GEOMETRY.json")],
        wall_s=time.perf_counter()-started, cpu_s=time.process_time()-cpu,
        nested_blender_wall_s=sum(job["wall_s"] for row in rows for job in row["jobs"]),
        image_count=12, geometry_and_displacements_rendered_at_actual_scale=True,
        all_render_cameras_frozen_before_edit=True, thresholds_changed=False,
        consumer_input_exposure=False))


if __name__ == "__main__":
    main()

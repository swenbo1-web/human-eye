"""Bind fixed cat sources, construct actual isolated assets and verify a hidden reachability control."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from background import run_job
from evaluate import evaluate_packets, packet
import numpy as np
from scipy.sparse import csr_matrix

DATA = HERE.parent / "m6_perception_data_001"
UNIT = "source_native_physical_length_unlabelled"
EXPECTED_ELL = 0.002567906610453878
NORMAL_LIMIT_RATIO = 0.014506080599458708


def save_npz(path, **arrays):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        with np.load(path, allow_pickle=False) as old:
            if set(old.files) != set(arrays) or any(old[key].dtype != value.dtype or old[key].shape != value.shape or old[key].tobytes() != value.tobytes() for key, value in arrays.items()):
                raise ValueError("existing_preparation_array_changed_" + str(path))
    else:
        np.savez_compressed(path, **arrays)


def execute(script, job, label):
    previous = HERE / "private/jobs" / label / "run.json"
    if previous.exists():
        record = read(previous)
        receipt = Path(record["receipt_path"])
        if record["process"]["returncode"] == 0 and receipt.exists():
            return record
        raise RuntimeError("prior_job_requires_actual_state_review_" + label)
    return run_job(script, job, label)


def normal_fields(vertices, faces):
    triangles = vertices[faces]
    cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    sums = np.zeros_like(vertices)
    for corner in range(3):
        np.add.at(sums, faces[:, corner], cross)
    lengths = np.linalg.norm(sums, axis=1)
    normals = np.divide(sums, lengths[:, None], out=np.zeros_like(sums), where=lengths[:, None] > 0)
    edges = np.unique(np.sort(np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]])), axis=1), axis=0)
    adjacency = csr_matrix((np.ones(len(edges) * 2), (np.r_[edges[:, 0], edges[:, 1]], np.r_[edges[:, 1], edges[:, 0]])), shape=(len(vertices), len(vertices)))
    degree = np.asarray(adjacency.sum(axis=1)).ravel()
    neighbor = np.divide(adjacency @ normals, degree[:, None], out=np.zeros_like(normals), where=degree[:, None] > 0)
    combined = .5 * normals + .5 * neighbor
    lengths = np.linalg.norm(combined, axis=1)
    n0 = np.divide(combined, lengths[:, None], out=np.zeros_like(combined), where=lengths[:, None] > 0)
    return normals, n0


def unit(value):
    norm = np.linalg.norm(value)
    if not np.isfinite(norm) or norm <= 0:
        raise ValueError("camera_direction_unavailable")
    return value / norm


def freeze_cameras(current, region, normals):
    vertices = current["vertices_world"]
    points = vertices[region]
    center = points.mean(axis=0)
    normal = unit(normals[region].mean(axis=0))
    _, _, vectors = np.linalg.svd(points - center, full_matrices=False)
    axis = vectors[0]
    if axis[np.argmax(np.abs(axis))] < 0:
        axis = -axis
    tangent = unit(axis - np.dot(axis, normal) * normal)
    diagonal = float(np.linalg.norm(np.ptp(vertices, axis=0)))
    distance = 2 * diagonal
    scale = 1.5 * float(np.linalg.norm(np.ptp(points, axis=0)))
    directions = (normal, unit(normal + tangent), unit(normal - tangent))
    local = [dict(name=name, location=(center + distance * direction).tolist(), target=center.tolist(), ortho_scale=scale, resolution=[640, 640])
        for name, direction in zip(("forearm_front", "forearm_side", "forearm_45"), directions)]
    whole_center = .5 * (vertices.min(axis=0) + vertices.max(axis=0))
    whole = dict(name="whole_front", location=(whole_center + distance * normal).tolist(), target=whole_center.tolist(),
                 ortho_scale=1.5 * diagonal, resolution=[640, 640])
    return dict(unit=UNIT, initial_packet=identity(HERE / "private/input/current.npz"),
        source="Actual saved current full-mesh geometry only", region_points=len(region), center=center.tolist(),
        mean_unit_vertex_normal=normal.tolist(), PCA_first_axis_positive_max_abs=axis.tolist(), tangent=tangent.tolist(),
        distance=distance, full_bbox_diagonal=diagonal, local_scale=scale, views=[whole] + local,
        construction="F mean, scale1.5 F bbox diagonal, mean area-weighted unit vertex normal, signed PCA first axis tangent, n/(n+u)/(n-u); normalized directions",
        private_clean_or_support_read_for_camera=False)


def main():
    started, cpu = time.perf_counter(), time.process_time()
    planning = read("PLANNING_PREFLIGHT.json")
    for row in planning["files"]:
        observed = identity(DATA / row["path"])
        if observed["sha256"] != row["sha256"] or observed["bytes"] != row["bytes"]:
            raise ValueError("fixed_source_identity_changed_" + row["path"])
    index = json.loads((DATA / "DATASET_INDEX.json").read_bytes())
    pair = next(row for row in index["pairs"] if row["split"] == "validation" and row["candidate_valid"] and row["usable_for_training"])
    if pair["id"] != planning["pair_id"]:
        raise ValueError("fixed_pair_order_changed")
    observations = {row["id"]: row for row in index["observations"]}
    specification = importlib.util.spec_from_file_location("_transfer_source_reader", DATA / "data_io.py")
    reader = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(reader)
    source_packets = [reader.read_current(observations[pair[key]]) for key in ("normal_observation_id", "damaged_observation_id")]
    clean_source, current_source = source_packets
    region = np.sort(current_source["region_source_ids"].astype(np.int64))
    vertices, faces = current_source["vertices"], current_source["faces"]
    if hashlib.sha256(vertices.tobytes()).hexdigest() != planning["current_vertices_sha256"]:
        raise ValueError("reconstructed_current_source_changed")
    local_faces = faces[np.isin(faces, region).all(axis=1)]
    edges, counts = np.unique(np.sort(np.concatenate((local_faces[:, [0, 1]], local_faces[:, [1, 2]], local_faces[:, [2, 0]])), axis=1), axis=0, return_counts=True)
    boundary = np.unique(edges[counts == 1])
    ring = np.setdiff1d(np.unique(edges[np.isin(edges, boundary).any(axis=1)]), boundary)
    editable = np.setdiff1d(region, np.union1d(boundary, ring))
    ell = float(np.linalg.norm(vertices[edges[:, 0]] - vertices[edges[:, 1]], axis=1).mean())
    if ell != EXPECTED_ELL or hashlib.sha256(editable.tobytes()).hexdigest() != planning["I_array_sha256"]:
        raise ValueError("fixed_domain_or_relative_budget_changed")
    original = DATA / "private/source/cat_reference.npz"
    jobs = []
    for index, source in enumerate(source_packets):
        folder = HERE / "private/construction" / ("p" + str(index))
        seed = folder / "seed.npz"
        save_npz(seed, vertices=source["vertices"], faces=source["faces"], F_source_ids=region)
        blend = folder / "model.blend"
        common = dict(object_name="surface", source_original=str(original), base_npz=str(seed), current_blend=str(blend))
        jobs.append(execute("blender_build.py", dict(common, operation="create_baseline", output_blend=str(blend)), "a0" + str(index) + "_build"))
        jobs.append(execute("blender_read.py", dict(common, expected_input_sha256=identity(blend)["sha256"],
            readback_npz=str(folder / "readback.npz"), scene_signature_json=str(folder / "scene.json")), "a0" + str(index) + "_read"))
    clean = packet(HERE / "private/construction/p0/readback.npz")
    current = packet(HERE / "private/construction/p1/readback.npz")
    for field in ("source_ids", "matrix_world", "faces", "poly_offsets", "poly_vertices", "triangle_polygon_ids"):
        if clean[field].dtype != current[field].dtype or clean[field].shape != current[field].shape or clean[field].tobytes() != current[field].tobytes():
            raise ValueError("normal_current_native_structure_differs_" + field)
    for packet_index, actual in enumerate((clean, current)):
        expected = source_packets[packet_index]["vertices"].astype(np.float32)
        if actual["vertices_local"].tobytes() != expected.tobytes():
            raise ValueError("actual_saved_native_differs_from_source_float32")
    normals, n0 = normal_fields(current["vertices_world"], current["faces"])
    public = dict(current, F_source_ids=region, I_ids=editable, protected_ids=np.setdiff1d(current["source_ids"], editable),
        B0_ids=boundary, B1_ids=ring, local_edges=edges, normals=normals, n0=n0)
    public_path = HERE / "private/input/current.npz"
    save_npz(public_path, **public)
    cameras = freeze_cameras(current, region, normals)
    write("CAMERAS.json", cameras)
    spec_path = HERE / "private/input/spec.json"
    spec = dict(case_id="sample_07", unit=UNIT, object_name="surface", source_original=str(original),
        base_blend_path=str(HERE / "private/construction/p1/model.blend"), initial_npz=str(public_path),
        baseline_scene=str(HERE / "private/construction/p1/scene.json"),
        max_operation_displacement_m=ell, max_cumulative_displacement_m=ell, max_displacement=ell,
        ell=ell, world_preservation_tol=float(8 * np.finfo(np.float32).eps * float(np.max(np.abs(current["vertices_world"])))),
        require_scene_preservation=True, geometry_gates={}, quality_gate={},
        normal_definition="Actual saved current full-mesh area-weighted vertex unit normals; n0 adds one equal one-ring averaging step and normalization",
        legacy_key_units="Historical _m field names contain source_native numerical units with physical length unlabelled", render_views=cameras["views"],
        normal_editable_RMS_limit_over_ell=NORMAL_LIMIT_RATIO, normal_editable_RMS_limit=ell * NORMAL_LIMIT_RATIO)
    write(spec_path, spec)
    saved_delta = current["vertices_world"] - clean["vertices_world"]
    support = np.flatnonzero(np.linalg.norm(saved_delta, axis=1) > 0)
    if len(support) != 43 or not np.isin(support, editable).all():
        raise ValueError("actual_saved_support_changed")
    scoring_target = HERE / "private/scoring_input/target.npz"
    save_npz(scoring_target, clean_vertices_world=clean["vertices_world"], initial_vertices_world=current["vertices_world"],
        source_ids=current["source_ids"], F_source_ids=region, I_ids=editable, support_ids=support)
    write("SCORING_BINDING.json", dict(cycle_id="M6-CALIBRATION-TRANSFER-007", target=identity(scoring_target),
        clean_actual_readback=identity(HERE / "private/construction/p0/readback.npz"),
        initial_actual_readback=identity(HERE / "private/construction/p1/readback.npz"), ell=ell, unit=UNIT,
        normal_editable_RMS_limit_over_ell=NORMAL_LIMIT_RATIO, normal_editable_RMS_limit=ell * NORMAL_LIMIT_RATIO,
        scoring_target_source="Independent actual saved normal model fresh readback; support derived privately from actual normal/current saved models"))
    image_rows = {"normal": [], "current": []}
    all_images = []
    for index, role in enumerate(("normal", "current")):
        blend = HERE / "private/construction" / ("p" + str(index)) / "model.blend"
        run = execute("blender_render.py", dict(object_name="surface", source_original=str(original), current_blend=str(blend),
            output_dir=str(HERE / "private/input" / ("p" + str(index) + "_images")), views=cameras["views"]), "a0" + str(index) + "_render")
        jobs.append(run)
        for view in run["receipt"]["views"]:
            row = dict(identity(Path(view["image"]["path"])), role=role + "_" + view["specification"]["name"],
                camera={key: view[key] for key in ("specification", "camera_matrix_world", "world_to_image_affine_2_by_3", "world_to_image_offset", "pixel_convention")})
            all_images.append(row)
            if view["specification"]["resolution"] == [640, 640] and view["specification"]["name"] != "whole_front":
                image_rows[role].append(row)
    write("IMAGE_BINDING.json", dict(cycle_id="M6-CALIBRATION-TRANSFER-007", images=all_images, calibration_images=image_rows,
        views=cameras["views"], render_source=identity(HERE / "blender_render.py"), matched_same_cameras=True,
        old_heavy_pair_preview_used=False, unit=UNIT))
    initial = dict(blend=identity(HERE / "private/construction/p1/model.blend"), packet=identity(public_path),
        scene=identity(HERE / "private/construction/p1/scene.json"), spec=identity(spec_path))
    binding = dict(cycle_id="M6-CALIBRATION-TRANSFER-007", original=identity(original),
        source_files=[identity(DATA / row["path"]) for row in planning["files"]], planning_preflight=identity(HERE / "PLANNING_PREFLIGHT.json"),
        selection_rule=planning["selection_rule"], pair_id=planning["pair_id"], lineage_group=planning["lineage_group"],
        prior_usage=planning["prior_usage"], unit=UNIT, ell=ell, operation_and_cumulative_budget=ell,
        initial=initial, images=image_rows, all_images=all_images, views=cameras["views"][1:], object_name="surface", alphas=[0, .5, 1],
        current_normals="Actual damaged saved current geometry only", source_clean_data_excluded_from_consumer=True,
        local_domain=dict(F=len(region), B0=len(boundary), B1=len(ring), I=len(editable), local_triangles=len(local_faces), local_edges=len(edges)),
        source_to_saved_quantization=[dict(role=role, maximum_native_quantization=float(np.max(np.abs(source_packets[index]["vertices"] - actual["vertices_world"]))),
            RMS_euclidean=float(np.sqrt(np.mean(np.sum((source_packets[index]["vertices"] - actual["vertices_world"]) ** 2, axis=1)))))
            for index, (role, actual) in enumerate(zip(("normal", "current"), (clean, current)))])
    write("SOURCE_INPUT_BINDING.json", binding)
    control = HERE / "private/control"
    payload = control / "target_payload.npz"
    save_npz(payload, source_ids=support, displacements_world=clean["vertices_world"][support] - current["vertices_world"][support])
    output = control / "model.blend"
    common = dict(object_name="surface", source_original=str(original), base_npz=str(public_path))
    jobs.append(execute("blender_edit.py", dict(common, current_blend=str(HERE / "private/construction/p1/model.blend"),
        expected_input_sha256=initial["blend"]["sha256"], output_blend=str(output), edit_payload=str(payload), allowed_ids_path=str(public_path),
        operation="edit", operation_id="hidden_correct_target_control"), "a02_control_write"))
    jobs.append(execute("blender_read.py", dict(common, current_blend=str(output), expected_input_sha256=identity(output)["sha256"],
        readback_npz=str(control / "readback.npz"), scene_signature_json=str(control / "scene.json")), "a02_control_read"))
    quality = evaluate_packets(public_path, control / "readback.npz", public_path, spec_path,
        before_state_path=HERE / "private/construction/p1/scene.json", after_state_path=control / "scene.json")
    write(control / "QUALITY.json", quality)
    actual_control = packet(control / "readback.npz")
    same_clean = actual_control["vertices_local"].dtype == clean["vertices_local"].dtype and actual_control["vertices_local"].tobytes() == clean["vertices_local"].tobytes()
    result = dict(cycle_id="M6-CALIBRATION-TRANSFER-007", status="pass" if quality["status"] == "pass" and same_clean else "fail",
        technical_status=quality["status"], actual_control_equals_saved_normal_native=same_clean,
        input_binding=identity(HERE / "SOURCE_INPUT_BINDING.json"), actual_control=identity(output), payload=identity(payload),
        readback=identity(control / "readback.npz"), quality=identity(control / "QUALITY.json"),
        technical_checks=quality["checks"], unit=UNIT, ell=ell, correct_target_maximum_displacement=float(np.linalg.norm(saved_delta, axis=1).max()),
        budget=ell, new_Blender_processes=len(jobs), new_Pro=0, new_training=0,
        jobs=[dict(label=job["label"], source=job["script"], job=job["job"], receipt_path=job["receipt_path"], wall_s=job["wall_s"],
            process=job["process"]) for job in jobs],
        scope="Private correct-target reachability control precedes the sole new consumer and remains excluded from consumer inputs.",
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu)
    write("ASSET_PREPARATION.json", result)
    print(json.dumps({key: result[key] for key in ("status", "technical_status", "new_Blender_processes", "wall_s", "CPU_s")}), flush=True)
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

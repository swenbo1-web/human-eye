"""Matched-PNG evidence projected onto the current displayed source mesh."""

import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy.spatial import cKDTree

from image_inputs import read_png_rgb


VIEW_NAMES = ("forearm_front", "forearm_side", "forearm_45")
PARAMETERS = dict(difference_floor_DN=2, core_point_budget=69, support_radius_m=.032,
    tie_depth_tolerance_m=1e-12, near_triangle_edge_barycentric_threshold=.02,
    score_rule="max_over_views_of_incident_triangle_signal_divided_by_visible_pixel_area",
    tie_rule="ascending_source_ID", support_rule="observed_zero_attention_within_32mm_of_core")


def array_digest(*arrays):
    digest = hashlib.sha256()
    for array in arrays:
        array = np.ascontiguousarray(array)
        digest.update(json.dumps(dict(dtype=str(array.dtype), shape=list(array.shape)), sort_keys=True).encode())
        digest.update(array.tobytes())
    return digest.hexdigest()


def file_identity(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def raster_buffers(vertices, faces, camera, width, height):
    """Orthographic pixel-center coverage with stable face-order depth ties."""
    affine = np.asarray(camera["world_to_image_affine_2_by_3"], dtype=np.float64)
    offset = np.asarray(camera["world_to_image_offset"], dtype=np.float64)
    matrix = np.asarray(camera["camera_matrix_world"], dtype=np.float64)
    pixels = vertices @ affine.T + offset
    triangles = pixels[faces]
    triangle_depths = (vertices @ matrix[:3, 2])[faces]
    depth = np.full((height, width), -np.inf)
    face_ids = np.full((height, width), -1, dtype=np.int32)
    minimum_weight = np.zeros((height, width), dtype=np.float64)
    coverage_count = np.zeros((height, width), dtype=np.int32)
    tie_mask = np.zeros((height, width), dtype=bool)
    lower = np.maximum(np.ceil(triangles.min(axis=1) - .5).astype(int), [0, 0])
    upper = np.minimum(np.floor(triangles.max(axis=1) - .5).astype(int), [width - 1, height - 1])
    eligible = np.flatnonzero(np.all(lower <= upper, axis=1))
    for face_id in eligible:
        first, second, third = triangles[face_id]
        denominator = ((second[1] - third[1]) * (first[0] - third[0])
                       + (third[0] - second[0]) * (first[1] - third[1]))
        if abs(denominator) < 1e-10:
            continue
        left, top = lower[face_id]
        right, bottom = upper[face_id]
        x = np.arange(left, right + 1)[None, :] + .5
        y = np.arange(top, bottom + 1)[:, None] + .5
        weight0 = ((second[1] - third[1]) * (x - third[0]) + (third[0] - second[0]) * (y - third[1])) / denominator
        weight1 = ((third[1] - first[1]) * (x - third[0]) + (first[0] - third[0]) * (y - third[1])) / denominator
        weight2 = 1 - weight0 - weight1
        candidate = (weight0 * triangle_depths[face_id, 0] + weight1 * triangle_depths[face_id, 1]
                     + weight2 * triangle_depths[face_id, 2])
        inside = (weight0 >= -1e-9) & (weight1 >= -1e-9) & (weight2 >= -1e-9)
        target = depth[top:bottom + 1, left:right + 1]
        coverage_count[top:bottom + 1, left:right + 1] += inside
        tie_mask[top:bottom + 1, left:right + 1] |= inside & np.isfinite(target) & (np.abs(candidate - target) <= 1e-12)
        keep = inside & (candidate > target)
        target[keep] = candidate[keep]
        face_ids[top:bottom + 1, left:right + 1][keep] = face_id
        minimum_weight[top:bottom + 1, left:right + 1][keep] = np.minimum(np.minimum(weight0, weight1), weight2)[keep]
    return dict(face_ids=face_ids, depth=depth, barycentric_minimum=minimum_weight,
                coverage_count=coverage_count, tie_event_mask=tie_mask, projected_vertices=pixels)


def raster(vertices, faces, camera, width, height):
    return raster_buffers(vertices, faces, camera, width, height)["face_ids"]


def checked_image_rows(image_rows, image_base):
    by_role = {row["role"]: dict(row) for row in image_rows}
    required = [role + "_" + name for name in VIEW_NAMES for role in ("normal", "current")]
    result = {}
    for role in required:
        row = by_role[role]
        path = Path(row["path"])
        path = path if path.is_absolute() else Path(image_base) / path
        actual = file_identity(path)
        if any(actual[key] != row[key] for key in ("bytes", "sha256")):
            raise ValueError("correspondence_PNG_identity_changed_" + role)
        result[role] = dict(row, path=actual["path"])
    for name in VIEW_NAMES:
        if result["normal_" + name]["camera"] != result["current_" + name]["camera"]:
            raise ValueError("matched_PNG_camera_metadata_mismatch")
    return result


def correspondence_binding(packet, image_rows):
    images = [{key: row[key] for key in ("role", "sha256", "bytes", "camera")}
              for row in image_rows.values()]
    return dict(component_source_sha256=file_identity(Path(__file__))["sha256"], parameters=PARAMETERS,
        current_geometry_sha256=array_digest(packet["vertices_world"], packet["faces"], packet["source_ids"]),
        scope_sha256=array_digest(packet["F_source_ids"], packet["I_ids"]),
        triangle_polygon_source_mapping_sha256=array_digest(packet["faces"], packet["triangle_polygon_ids"]),
        matched_images=images, data_scope="current displayed mesh, matched PNGs and camera metadata")


def derive_regions(vertices, faces, editable, attention, visible, core):
    positive = np.flatnonzero(attention > 0)
    excluded = np.union1d(core, positive)
    distance, _ = cKDTree(vertices[core]).query(vertices, k=1)
    supports = np.flatnonzero(visible & (attention == 0) & (distance <= PARAMETERS["support_radius_m"]))
    supports = np.setdiff1d(supports, excluded)
    incident = faces[np.isin(faces, core).any(axis=1)]
    transition = np.setdiff1d(np.intersect1d(np.unique(incident), editable), core)
    unobserved = editable[~visible[editable]]
    return dict(active_core_source_ids=core, positive_attention_source_ids=positive,
                fit_support_source_ids=supports, transition_source_ids=transition,
                unobserved_source_ids=unobserved, fit_exclusion_source_ids=excluded)


def compute_correspondence(packet, image_rows, image_base, output_dir):
    """Freeze current-only outputs before any caller performs private scoring."""
    started, cpu = time.perf_counter(), time.process_time()
    output_dir = Path(output_dir)
    rows = checked_image_rows(image_rows, image_base)
    binding = correspondence_binding(packet, rows)
    binding_path = output_dir / "BINDING.json"
    array_path = output_dir / "ARRAYS.npz"
    summary_path = output_dir / "SUMMARY.json"
    if binding_path.exists():
        previous = json.loads(binding_path.read_bytes())
        if previous["inputs"] != binding:
            raise ValueError("correspondence_cache_inputs_changed_within_version")
        if file_identity(array_path)["sha256"] != previous["arrays"]["sha256"]:
            raise ValueError("correspondence_cache_array_identity_changed")
        if file_identity(summary_path)["sha256"] != previous["summary"]["sha256"]:
            raise ValueError("correspondence_cache_summary_identity_changed")
        with np.load(array_path, allow_pickle=False) as archive:
            arrays = dict(archive)
        return dict(arrays=arrays, summary=json.loads(summary_path.read_bytes()), binding=binding,
            array_path=str(array_path), cost=dict(cache_hit=True, wall_s=time.perf_counter() - started,
                CPU_s=time.process_time() - cpu, retained_array_bytes=array_path.stat().st_size,
                in_memory_array_bytes=sum(value.nbytes for value in arrays.values())))
    if array_path.exists() or summary_path.exists():
        raise ValueError("incomplete_correspondence_cache_requires_attempt_inspection")
    vertices = np.asarray(packet["vertices_world"], dtype=np.float64)
    faces = np.asarray(packet["faces"], dtype=np.int64)
    source_ids = np.asarray(packet["source_ids"], dtype=np.int64)
    editable = np.asarray(packet["I_ids"], dtype=np.int64)
    region = np.asarray(packet["F_source_ids"], dtype=np.int64)
    if not np.array_equal(source_ids, np.arange(len(vertices))):
        raise ValueError("correspondence_requires_preserved_source_ID_row_mapping")
    if len(editable) < PARAMETERS["core_point_budget"]:
        raise ValueError("correspondence_core_budget_exceeds_editable_domain")
    touches_region = np.isin(faces, region).any(axis=1)
    view_arrays, details, stage_costs = [], [], []
    for name in VIEW_NAMES:
        read_started, read_cpu = time.perf_counter(), time.process_time()
        current, normal = rows["current_" + name], rows["normal_" + name]
        current_rgb = read_png_rgb(Path(current["path"]).read_bytes())
        normal_rgb = read_png_rgb(Path(normal["path"]).read_bytes())
        if current_rgb.shape != normal_rgb.shape or current_rgb.shape[:2] != (current["height"], current["width"]):
            raise ValueError("matched_PNG_dimensions_mismatch")
        difference = np.max(np.abs(current_rgb.astype(np.int16) - normal_rgb.astype(np.int16)), axis=2)
        energy = np.maximum(difference.astype(np.float64) - PARAMETERS["difference_floor_DN"], 0)
        costs = dict(view=name, PNG_read_decode_difference_wall_s=time.perf_counter() - read_started,
            PNG_read_decode_difference_CPU_s=time.process_time() - read_cpu,
            PNG_file_bytes=current["bytes"] + normal["bytes"], RGB_array_bytes=current_rgb.nbytes + normal_rgb.nbytes)
        raster_started, raster_cpu = time.perf_counter(), time.process_time()
        buffers = raster_buffers(vertices, faces, current["camera"], current["width"], current["height"])
        costs.update(raster_wall_s=time.perf_counter() - raster_started, raster_CPU_s=time.process_time() - raster_cpu)
        aggregate_started, aggregate_cpu = time.perf_counter(), time.process_time()
        face_ids = buffers["face_ids"]
        mapped, changed = face_ids >= 0, energy > 0
        face_area = np.bincount(face_ids[mapped], minlength=len(faces))
        face_signal = np.bincount(face_ids[mapped], weights=energy[mapped], minlength=len(faces))
        vertex_area, vertex_signal = np.zeros(len(vertices)), np.zeros(len(vertices))
        for corner in range(3):
            np.add.at(vertex_area, faces[:, corner], face_area / 3)
            np.add.at(vertex_signal, faces[:, corner], face_signal / 3)
        score = np.divide(vertex_signal, vertex_area, out=np.zeros(len(vertices)), where=vertex_area > 0)
        near_edge = mapped & (buffers["barycentric_minimum"] <= PARAMETERS["near_triangle_edge_barycentric_threshold"])
        altered_faces = face_ids[changed & mapped]
        projected = buffers["projected_vertices"]
        projected_inside = ((projected[:, 0] >= 0) & (projected[:, 0] < current["width"])
                            & (projected[:, 1] >= 0) & (projected[:, 1] < current["height"]))
        details.append(dict(view=name, image_pixels=int(energy.size), mesh_covered_pixels=int(mapped.sum()),
            changed_pixels=int(changed.sum()), changed_mapped_pixels=int(np.sum(changed & mapped)),
            changed_outside_F_incident_faces=int(np.sum(~touches_region[altered_faces])),
            changed_without_current_mesh=int(np.sum(changed & ~mapped)),
            projected_overlap_pixels=int(np.sum(buffers["coverage_count"] > 1)),
            raster_depth_tie_event_pixels=int(buffers["tie_event_mask"].sum()),
            near_triangle_edge_pixels=int(near_edge.sum()), changed_near_triangle_edge_pixels=int(np.sum(changed & near_edge)),
            incident_face_visible_source_points=int(np.sum(vertex_area > 0)),
            incident_face_visible_editable_points=int(np.sum(vertex_area[editable] > 0)),
            projected_inside_editable_points=int(np.sum(projected_inside[editable])),
            visibility_definition="Incident triangle owns pixel-center area; vertex-point ray visibility is separately validated",
            boundary_definition="Current triangle minimum barycentric weight at most 0.02; includes geometric edge proximity",
            unmatched_difference_definition="Positive PNG energy whose pixel center has no current triangle coverage"))
        costs.update(aggregation_wall_s=time.perf_counter() - aggregate_started,
            aggregation_CPU_s=time.process_time() - aggregate_cpu)
        stage_costs.append(costs)
        view_arrays.append(dict(score=score, area=vertex_area, signal=vertex_signal,
            face_ids=face_ids, depth=np.where(mapped, buffers["depth"], 0), boundary=near_edge,
            difference=difference, energy=energy, projected_inside=projected_inside,
            coverage_count=buffers["coverage_count"], tie_mask=buffers["tie_event_mask"]))
    per_view_score = np.column_stack([row["score"] for row in view_arrays])
    per_view_area = np.column_stack([row["area"] for row in view_arrays])
    visible_by_view = per_view_area > 0
    attention = per_view_score.max(axis=1)
    visible = visible_by_view.any(axis=1)
    ranked = editable[np.lexsort((editable, -attention[editable]))]
    core = ranked[:PARAMETERS["core_point_budget"]]
    rank = np.full(len(vertices), -1, dtype=np.int64)
    rank[ranked] = np.arange(len(ranked))
    regions = derive_regions(vertices, faces, editable, attention, visible, core)
    arrays = dict(attention=attention, per_view_score=per_view_score, incident_face_visible=visible_by_view,
        incident_face_pixel_area=per_view_area, incident_face_signal=np.column_stack([row["signal"] for row in view_arrays]),
        candidate_rank=rank, ranked_source_ids=ranked, **regions,
        pixel_center_face_ids=np.stack([row["face_ids"] for row in view_arrays]),
        pixel_center_depth=np.stack([row["depth"] for row in view_arrays]),
        pixel_center_boundary=np.stack([row["boundary"] for row in view_arrays]),
        pixel_center_RGBmax_difference=np.stack([row["difference"] for row in view_arrays]),
        pixel_center_energy=np.stack([row["energy"] for row in view_arrays]),
        pixel_center_coverage_count=np.stack([row["coverage_count"] for row in view_arrays]),
        pixel_center_depth_tie_event=np.stack([row["tie_mask"] for row in view_arrays]),
        vertex_projection_inside_image=np.column_stack([row["projected_inside"] for row in view_arrays]),
        triangle_polygon_ids=np.asarray(packet["triangle_polygon_ids"], dtype=np.int64),
        triangle_source_ids=faces)
    summary = dict(parameters=PARAMETERS, view_names=list(VIEW_NAMES), full_source_points=len(vertices),
        candidate_points=len(editable), observation_F_points=len(region), core_points=len(core),
        incident_face_visible_editable_points=int(visible[editable].sum()),
        positive_attention_editable_points=int(np.count_nonzero(attention[editable])),
        positive_attention_full_mesh_points=len(regions["positive_attention_source_ids"]),
        fit_support_points=len(regions["fit_support_source_ids"]), transition_points=len(regions["transition_source_ids"]),
        unobserved_editable_points=len(regions["unobserved_source_ids"]),
        score_peak_source_id=int(ranked[0]), score_maximum=float(attention[ranked[0]]),
        visibility_definition="incident_face_visible means an incident current source triangle owns visible pixel-center area",
        vertex_point_visibility="requires independent vertex projection ray test", details=details,
        fit_support_rule="Any current source point with observed incident face, zero attention, within 32mm of a core point; exclude all positive attention and core points",
        transition_rule="One-ring triangle co-members of core, intersected with I, excluding core",
        unobserved_reason_rule="Per-view projected outside image or no incident triangle owns a visible pixel center; full geometry remains readable",
        core_centroid_world=vertices[core].mean(axis=0).tolist(),
        core_bbox_world=[vertices[core].min(axis=0).tolist(), vertices[core].max(axis=0).tolist()],
        stage_costs=stage_costs, input_scope="current geometry, normal/current PNG and cameras")
    output_dir.mkdir(parents=True, exist_ok=True)
    save_started, save_cpu = time.perf_counter(), time.process_time()
    np.savez_compressed(array_path, **arrays)
    summary["array_serialization_wall_s"] = time.perf_counter() - save_started
    summary["array_serialization_CPU_s"] = time.process_time() - save_cpu
    summary["computed_wall_s"] = time.perf_counter() - started
    summary["computed_CPU_s"] = time.process_time() - cpu
    summary["in_memory_array_bytes"] = sum(value.nbytes for value in arrays.values())
    write_json(summary_path, summary)
    write_json(binding_path, dict(inputs=binding, arrays=file_identity(array_path), summary=file_identity(summary_path)))
    return dict(arrays=arrays, summary=summary, binding=binding, array_path=str(array_path),
        cost=dict(cache_hit=False, wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
            retained_array_bytes=array_path.stat().st_size, in_memory_array_bytes=summary["in_memory_array_bytes"]))

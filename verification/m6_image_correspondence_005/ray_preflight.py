"""Validate pixel ownership using independent orthographic Moller-Trumbore rays."""

import argparse
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
import numpy as np

VIEWS = ("forearm_front", "forearm_side", "forearm_45")


def ray_hits(vertices, faces, origin, direction):
    """Return every forward hit, independently of screen-space rasterization."""
    triangles = vertices[faces]
    edge1, edge2 = triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
    cross_direction = np.cross(direction, edge2)
    denominator = np.einsum("ij,ij->i", edge1, cross_direction)
    inverse = np.divide(1., denominator, out=np.zeros_like(denominator), where=np.abs(denominator) > 1e-20)
    relative = origin - triangles[:, 0]
    u = np.einsum("ij,ij->i", relative, cross_direction) * inverse
    cross_relative = np.cross(relative, edge1)
    v = cross_relative @ direction * inverse
    distance = np.einsum("ij,ij->i", edge2, cross_relative) * inverse
    keep = ((np.abs(denominator) > 1e-20) & (u >= -1e-9) & (v >= -1e-9)
            & (u + v <= 1 + 1e-9) & (distance >= 0))
    selected = np.flatnonzero(keep)
    if not len(selected):
        return selected, np.empty(0), np.empty((0, 3))
    order = np.lexsort((selected, distance[selected]))
    selected = selected[order]
    return selected, distance[selected], np.column_stack((1 - u[selected] - v[selected], u[selected], v[selected]))


def camera_ray(camera, pixel):
    affine = np.asarray(camera["world_to_image_affine_2_by_3"], np.float64)
    offset = np.asarray(camera["world_to_image_offset"], np.float64)
    matrix = np.asarray(camera["camera_matrix_world"], np.float64)
    camera_origin = matrix[:3, 3]
    origin = camera_origin + affine.T @ np.linalg.solve(affine @ affine.T, pixel - affine @ camera_origin - offset)
    backward = np.cross(affine[0], affine[1])
    backward /= np.linalg.norm(backward)
    if backward @ matrix[:3, 2] < 0:
        backward = -backward
    return origin, -backward


def check_polygon(packet, face_id):
    polygon_id = int(packet["triangle_polygon_ids"][face_id])
    offsets = packet["poly_offsets"]
    native = packet["poly_vertices"][offsets[polygon_id]:offsets[polygon_id + 1]]
    return polygon_id, bool(np.isin(packet["faces"][face_id], native).all())


def validate(packet_path, arrays_path, binding_path, output):
    started, cpu = time.perf_counter(), time.process_time()
    if not Path(output).resolve().is_relative_to(HERE):
        raise ValueError("ray_preflight_output_outside_current_batch")
    with np.load(packet_path, allow_pickle=False) as archive:
        packet = dict(archive)
    with np.load(arrays_path, allow_pickle=False) as archive:
        arrays = dict(archive)
    vertices, faces = packet["vertices_world"], packet["faces"]
    entries = {row["role"]: row for row in read(binding_path)["images"]}
    checks, pixel_rows, vertex_rows, view_rows = {}, [], [], []
    checks["source_ID_indexing"] = bool(np.array_equal(packet["source_ids"], np.arange(len(vertices))))
    checks["three_saved_face_maps"] = arrays["pixel_center_face_ids"].shape[0] == 3
    for view_index, view in enumerate(VIEWS):
        row, normal = entries["current_" + view], entries["normal_" + view]
        camera = row["camera"]
        width, height = row["width"], row["height"]
        checks[view + "_matching_normal_camera"] = camera == normal["camera"]
        for image in (row, normal):
            actual = identity(HERE / image["path"])
            checks[image["role"] + "_PNG_identity"] = actual["sha256"] == image["sha256"] and actual["bytes"] == image["bytes"]
        matrix = np.asarray(camera["camera_matrix_world"])
        affine = np.asarray(camera["world_to_image_affine_2_by_3"])
        offset = np.asarray(camera["world_to_image_offset"])
        checks[view + "_orthonormal_camera_axes"] = bool(np.allclose(matrix[:3, :3].T @ matrix[:3, :3], np.eye(3), atol=1e-12))
        _, forward = camera_ray(camera, np.asarray([width / 2, height / 2]))
        camera_backward = matrix[:3, 2] / np.linalg.norm(matrix[:3, 2])
        axis_difference = float(np.linalg.norm(camera_backward + forward))
        checks[view + "_projection_nullspace_camera_alignment"] = bool(axis_difference <= 16 * np.finfo(np.float32).eps)
        face_map, depth_map = arrays["pixel_center_face_ids"][view_index], arrays["pixel_center_depth"][view_index]
        checks[view + "_raster_dimensions"] = face_map.shape == depth_map.shape == (height, width)
        sample_x, sample_y = np.rint(np.linspace(0, width - 1, 11)).astype(int), np.rint(np.linspace(0, height - 1, 11)).astype(int)
        correct, mapped_count, ties, occluded_rays = 0, 0, 0, 0
        for y in sample_y:
            for x in sample_x:
                pixel = np.asarray([x + .5, y + .5])
                origin, direction = camera_ray(camera, pixel)
                hits, distances, barycentric = ray_hits(vertices, faces, origin, direction)
                raster_face = int(face_map[y, x])
                nearest_faces = hits[distances <= distances[0] + 1e-9] if len(hits) else hits
                same_owner = (raster_face < 0 and not len(hits)) or bool(raster_face in nearest_faces)
                witness = dict(view=view, x=int(x), y=int(y), pixel_center=pixel.tolist(), raster_face_id=raster_face,
                    ray_face_id=int(hits[0]) if len(hits) else -1, equal_depth_faces=nearest_faces.tolist(),
                    ray_hit_count=len(hits), owner_equivalent=same_owner)
                if len(hits):
                    mapped_count += 1
                    ties += int(len(nearest_faces) > 1)
                    occluded_rays += int(len(hits) > len(nearest_faces))
                    point = origin + distances[0] * direction
                    projection_error = float(np.linalg.norm(affine @ point + offset - pixel))
                    reconstructed = barycentric[0] @ vertices[faces[hits[0]]]
                    depth_error = abs(float(point @ matrix[:3, 2] - depth_map[y, x]))
                    polygon, polygon_valid = check_polygon(packet, int(hits[0]))
                    witness.update(world_point=point.tolist(), barycentric=barycentric[0].tolist(),
                        source_ids=faces[hits[0]].tolist(), polygon_id=polygon, native_polygon_contains_triangle=polygon_valid,
                        projection_error_pixels=projection_error, ray_triangle_reconstruction_error_m=float(np.linalg.norm(reconstructed - point)),
                        ray_raster_depth_error_m=depth_error)
                    same_owner = same_owner and polygon_valid and projection_error <= 1e-6 and depth_error <= 1e-8
                correct += int(same_owner)
                witness["passed"] = bool(same_owner)
                pixel_rows.append(witness)
        checks[view + "_121_ray_pixel_witnesses"] = correct == 121
        fixed_ids = np.sort(packet["I_ids"])[::17]
        for source_id in fixed_ids:
            point = vertices[source_id]
            pixel = affine @ point + offset
            origin, direction = camera_ray(camera, pixel)
            hits, distances, _ = ray_hits(vertices, faces, origin, direction)
            nearest_point = origin + distances[0] * direction if len(hits) else np.full(3, np.nan)
            error = float(np.linalg.norm(nearest_point - point)) if len(hits) else None
            vertex_rows.append(dict(view=view, source_id=int(source_id), projected_pixel=pixel.tolist(),
                within_image=bool(0 <= pixel[0] < width and 0 <= pixel[1] < height),
                ray_nearest_triangle=int(hits[0]) if len(hits) else -1,
                vertex_point_visible=bool(error is not None and error <= 1e-8), nearest_point_error_m=error,
                incident_face_visible=bool(arrays["incident_face_visible"][source_id, view_index]),
                interpretation="Vertex-point ray visibility is evaluated separately from incident triangle pixel area."))
        view_rows.append(dict(view=view, fixed_pixel_rays=121, mapped_ray_centers=mapped_count,
            equal_depth_ray_centers=ties, rays_with_occluded_hits=occluded_rays, witnesses_passed=correct,
            fixed_vertex_rays=len(fixed_ids), full_image_pixels=width * height,
            mapped_current_mesh_pixels=int((face_map >= 0).sum()), unmapped_current_mesh_pixels=int((face_map < 0).sum()),
            raster_boundary_pixels=int(arrays["pixel_center_boundary"][view_index].sum()),
            camera_basis_to_affine_nullspace_unit_vector_error=axis_difference,
            raw_affine_camera_back_axis_pixels_per_m=(affine @ camera_backward).tolist(),
            ray_direction_basis="Exact supplied projection-affine nullspace, oriented using camera matrix."))
    checks["sampling_plan_frozen_without_labels"] = read("RAY_SAMPLE_PLAN.json")["rule_frozen_before_correspondence_results_and_hidden_scoring"]
    result = dict(cycle_id="M6-IMAGE-CORRESPONDENCE-005", status="pass" if all(checks.values()) else "fail",
        checks=checks, passed=sum(checks.values()), total=len(checks), views=view_rows,
        pixel_witnesses=pixel_rows, vertex_projection_witnesses=vertex_rows,
        inputs=dict(current_geometry=identity(packet_path), correspondence_arrays=identity(arrays_path),
                    image_binding=identity(binding_path), sampling_plan=identity(HERE / "RAY_SAMPLE_PLAN.json")),
        source=identity(Path(__file__)), private_labels_read=False,
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu, actual_Blender_calls=0, actual_Pro_calls=0,
        scope="Fixed sampled pixel-center ownership and independent vertex-projection rays on the full displayed mesh. AA boundaries and depth ties are recorded.")
    write(output, result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, default=HERE / "private/cases/repair/initial.npz")
    parser.add_argument("--arrays", type=Path, default=HERE / "private/correspondence_preflight/baseline/ARRAYS.npz")
    parser.add_argument("--image-binding", type=Path, default=HERE / "IMAGE_BINDING.json")
    parser.add_argument("--output", type=Path, default=HERE / "RAY_PREFLIGHT.json")
    args = parser.parse_args()
    result = validate(args.packet.resolve(), args.arrays.resolve(), args.image_binding.resolve(), args.output.resolve())
    print(json.dumps({key: result[key] for key in ("status", "passed", "total", "wall_s", "CPU_s")}))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""Independently review saved real-asset source-region pixels and bounded rays.

Only saved JSON, NPZ and PNG bytes are consumed.  All foreground pixels are
checked against their claimed source triangle in O(pixels) work.  A fixed 16x16
grid and the first row-major pixel of each visible selected triangle receive
independent nearest-hit checks against the complete captured scene.  Selected
triangle centroids supply an additional, explicitly sampled occluder diagnosis.
No product module, Blender process, rasterizer or model is invoked.
"""

import argparse
import base64
from collections import Counter
from fractions import Fraction
import hashlib
from io import BytesIO
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PREVIOUS = REPO / 'verification/m4_m5_source_region_001/oracle/check_saved.py'
PREVIOUS_SHA = '10867672118d1ddfa15daff3debd62f0764f05f5afe2cc059f69795779a36d7f'
BARYCENTRIC_ALLOWANCE = 1e-8
DEPTH_ALLOWANCE_M = 1e-8
WORLD_ALLOWANCE_M = 1e-12
RAY_CHUNK = 16
GRID_SIDE = 16


def previous_helpers():
    # The existing helper imports only independent saved-evidence checkers.
    if hashlib.sha256(PREVIOUS.read_bytes()).hexdigest() != PREVIOUS_SHA:
        raise ValueError('sealed_previous_saved_reader_changed')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(PREVIOUS.parent))
    spec = importlib.util.spec_from_file_location('_real_asset_previous_saved_check', PREVIOUS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SAVED = previous_helpers()
np, Image = SAVED.np, SAVED.Image
fingerprint = SAVED.fingerprint


class Audit(SAVED.Audit):
    def __init__(self):
        super().__init__()
        self.file(__file__)
        self.file(PREVIOUS, PREVIOUS_SHA)
        self.file(SAVED.FRAME_PATH, SAVED.FRAME_SHA)
        self.file(SAVED.MATH_PATH, SAVED.MATH_SHA)


def scene_arrays(capture):
    meshes = capture['meshes']
    offsets = np.cumsum([0] + [len(mesh['faces']) for mesh in meshes], dtype=np.int64)
    triangles = np.concatenate([np.asarray(mesh['vertices'], dtype=np.float64)[
        np.asarray(mesh['faces'], dtype=np.int64)] for mesh in meshes])
    objects = np.repeat(np.arange(len(meshes), dtype=np.int32), np.diff(offsets))
    return triangles, objects, offsets


def snapshot_checks(snapshot, capture, binding, audit):
    audit.check(snapshot['schema'] == 'real-asset-source-v1', 'fresh_source_snapshot_schema')
    snapshots = {row['name']: row for row in snapshot['objects']}
    audit.check(len(snapshots) == len(snapshot['objects']) == len(capture['meshes'])
                and set(snapshots) == {mesh['name'] for mesh in capture['meshes']},
                'fresh_all_scene_mesh_names_and_counts')
    audit.check(binding['capture_scope'] == capture.get('capture_scope', 'complete_scene_meshes') == 'complete_scene_meshes'
                and binding['document_epoch'] == capture['host_identity']['document_epoch']
                and binding['scene_revision'] == capture['revision']
                and binding['capture_state'] == capture['capture_state'],
                'actual_capture_complete_scene_current_generation')
    audit.check(binding['unit'] == capture['unit'] == 'm'
                and binding['coordinate_frame'] == capture['coordinate_frame'] == 'world',
                'actual_capture_world_metres')
    scale = float(snapshot['unit_scale'])
    audit.check(np.isfinite(scale) and scale > 0, 'fresh_scene_unit_scale_positive')
    comparisons = []
    for index, mesh in enumerate(capture['meshes']):
        row = snapshots[mesh['name']]
        host = binding['objects'][index]
        audit.check(host == dict(object_index=index, host_id=mesh['object_id'], object_name=mesh['name'],
            instance_id=capture['host_identity']['object_instances'][mesh['object_id']]),
            'actual_capture_ordered_host_instance/' + mesh['name'])
        if row.get('instance_id') is not None:
            audit.check(row['instance_id'] == host['instance_id'], 'fresh_instance_id/' + mesh['name'])
        local = np.asarray(row['evaluated']['vertices'], dtype=np.float64)
        matrix = np.asarray(row['matrix_world'], dtype=np.float64)
        audit.check(matrix.shape == (4, 4) and np.all(np.isfinite(matrix))
                    and np.array_equal(matrix[3], [0, 0, 0, 1]), 'fresh_affine_matrix/' + mesh['name'])
        # This spells out world conversion and unit application.  A BLAS matrix
        # product can change rounding at the last bit of source packet values.
        world = (((local[:, 0, None] * matrix[:3, 0] + local[:, 1, None] * matrix[:3, 1])
                   + local[:, 2, None] * matrix[:3, 2]) + matrix[:3, 3]) * scale
        actual = np.asarray(mesh['vertices'], dtype=np.float64)
        audit.check(actual.shape == world.shape and np.all(np.isfinite(actual))
                    and np.allclose(actual, world, rtol=0, atol=WORLD_ALLOWANCE_M),
                    'fresh_ordered_evaluated_world_points/' + mesh['name'])
        audit.check(mesh['faces'] == row['evaluated']['triangles'],
                    'fresh_ordered_evaluated_triangle_rows/' + mesh['name'])
        comparisons.append(dict(object_index=index, object_name=mesh['name'], host_id=mesh['object_id'],
            instance_id=host['instance_id'], vertices=len(actual), triangles=len(mesh['faces']),
            maximum_world_coordinate_error_m=float(np.max(np.abs(actual - world))),
            hide_render=row['display']['hide_render'], participates_in_capture=True))
    ordered = [dict(host_id=host['host_id'], instance_id=host['instance_id'],
                    vertices=mesh['vertices'], faces=mesh['faces'])
               for host, mesh in zip(binding['objects'], capture['meshes'], strict=True)]
    audit.check(fingerprint(ordered) == binding['ordered_geometry_sha256'], 'fresh_capture_ordered_geometry_digest')
    appended = {'runtime_source_sha256', 'source_status', 'disk_status', 'source_check_scope'}
    unsigned = {key: value for key, value in binding.items() if key not in appended | {'binding_sha256'}}
    audit.check(fingerprint(unsigned) == binding['binding_sha256'], 'source_region_camera_binding_digest_preimage')
    base = {key: value for key, value in binding.items() if key not in appended | {
        'source_binding_sha256', 'binding_sha256', 'camera_specification', 'geometry_identity',
        'camera_identity', 'ordered_geometry_sha256'}}
    audit.check(fingerprint(base) == binding['source_binding_sha256'], 'source_region_source_binding_digest_preimage')
    audit.check(fingerprint(binding['camera_specification']) == binding['camera_identity'], 'source_region_camera_identity_preimage')
    return comparisons


def region_checks(full, capture, audit):
    reference = full['region_ref']
    binding = full['binding']
    source_index = next(index for index, host in enumerate(binding['objects'])
                        if host['host_id'] == reference['host_id'])
    source = capture['meshes'][source_index]
    selected = reference['source_triangle_indices']
    audit.check(selected == sorted(set(selected)) and bool(selected)
                and all(type(index) is int and 0 <= index < len(source['faces']) for index in selected),
                'selected_canonical_current_source_triangle_rows')
    audit.check(reference['document_epoch'] == binding['document_epoch']
                and reference['instance_id'] == binding['objects'][source_index]['instance_id']
                and reference['ordered_geometry_sha256'] == binding['ordered_geometry_sha256'],
                'selected_region_current_host_instance_geometry')
    generation = {key: binding['capture_state'][key] for key in ('instance_id', 'epoch', 'revision')}
    unsigned = {key: value for key, value in reference.items() if key != 'region_id'}
    audit.check(reference['capture_generation'] == generation
                and reference['region_id'] == 'source-region:' + fingerprint(unsigned), 'selected_region_identity_preimage')
    vertices = sorted({vertex for index in selected for vertex in source['faces'][index]})
    region = full['facts']['region']
    audit.check(region['source_triangle_indices'] == selected and region['source_vertex_indices'] == vertices
                and region['triangles_source_vertices'] == [source['faces'][index] for index in selected]
                and region['vertices_world_m'] == [source['vertices'][index] for index in vertices],
                'selected_source_triangle_vertex_and_world_rows')
    return source_index, selected, vertices


def camera_checks(pose, selected_points, capture, audit):
    view = np.asarray(pose['view_matrix'], dtype=np.float64)
    projection = np.asarray(pose['projection_matrix'], dtype=np.float64)
    audit.check(pose['projection'] == 'orthographic' and pose['size_px'] == [512, 512]
                and view.shape == projection.shape == (4, 4)
                and np.all(np.isfinite(view)) and np.all(np.isfinite(projection)), 'saved_finite_orthographic_camera')
    audit.check(np.allclose(view[:3, :3] @ view[:3, :3].T, np.eye(3), rtol=0, atol=1e-12)
                and np.array_equal(view[3], [0, 0, 0, 1]), 'saved_rigid_camera_view')
    expected = np.zeros((4, 4))
    expected[0, 0], expected[1, 1] = projection[0, 0], projection[1, 1]
    expected[2, 2] = -2 / (pose['far'] - pose['near'])
    expected[2, 3] = -(pose['far'] + pose['near']) / (pose['far'] - pose['near'])
    expected[3, 3] = 1
    audit.check(np.allclose(expected, projection, rtol=0, atol=1e-14)
                and projection[0, 0] > 0 and projection[1, 1] > 0,
                'published_inverse_camera_and_depth_clip')
    projected = selected_points @ view[:3, :3].T + view[:3, 3]
    ndc = projected @ projection[:3, :3].T + projection[:3, 3]
    audit.check(np.all(np.abs(ndc[:, :2]) <= 1 + 1e-12), 'all_selected_source_vertices_fit_XY')
    center = selected_points.min(axis=0) * .5 + selected_points.max(axis=0) * .5
    audit.check(np.allclose(center, pose['target'], rtol=0, atol=1e-12), 'selected_source_bbox_center_camera_target')
    relative = selected_points - center
    half_unpadded = float(np.max(np.abs(relative @ view[:2, :3].T)))
    audit.check(abs(pose['half_span_m'] - half_unpadded * 1.1) <= 1e-12,
                'selected_source_camera_ten_percent_span_padding')
    scene_points = np.concatenate([np.asarray(mesh['vertices'], dtype=np.float64) for mesh in capture['meshes']])
    depths = -(scene_points @ view[2, :3] + view[2, 3])
    audit.check(np.all(depths >= pose['near']) and np.all(depths <= pose['far']),
                'all_scene_source_vertices_inside_camera_depth_clip')
    return dict(selected_ndc_XY_min=ndc[:, :2].min(axis=0).tolist(),
                selected_ndc_XY_max=ndc[:, :2].max(axis=0).tolist(),
                source_vertex_count=len(selected_points), all_scene_camera_depth_min_m=float(depths.min()),
                all_scene_camera_depth_max_m=float(depths.max()), near_m=pose['near'], far_m=pose['far'])


def pixel_origins(xs, ys, pose):
    view = np.asarray(pose['view_matrix'], dtype=np.float64)
    projection = np.asarray(pose['projection_matrix'], dtype=np.float64)
    inverse = np.linalg.inv(view)
    width, height = pose['size_px']
    ndc_x = 2 * (np.asarray(xs) + .5) / (width - 1) - 1
    ndc_y = 1 - 2 * (np.asarray(ys) + .5) / (height - 1)
    camera_x, camera_y = ndc_x / projection[0, 0], ndc_y / projection[1, 1]
    origins = camera_x[:, None] * inverse[:3, 0] + camera_y[:, None] * inverse[:3, 1] + inverse[:3, 3]
    return origins, -inverse[:3, 2], (np.abs(ndc_x) <= 1) & (np.abs(ndc_y) <= 1)


def intersect_claimed(origins, direction, triangles):
    """Pairwise Moller-Trumbore intersections, one source face per sample."""
    a = triangles[:, 0]
    first, second = triangles[:, 1] - a, triangles[:, 2] - a
    h = np.cross(direction, second)
    determinant = np.einsum('ij,ij->i', first, h)
    reciprocal = np.divide(1., determinant, out=np.zeros_like(determinant), where=determinant != 0)
    delta = origins - a
    u = np.einsum('ij,ij->i', delta, h) * reciprocal
    q = np.cross(delta, first)
    v = q @ direction * reciprocal
    depths = np.einsum('ij,ij->i', second, q) * reciprocal
    minimum = np.minimum(np.minimum(u, v), 1 - u - v)
    return depths, minimum, determinant


def claimed_pixel_checks(frame, arrays, triangles, audit):
    mask = arrays['owners'] >= 0
    ys, xs = np.nonzero(mask)
    ids = arrays['triangle_ids'][mask]
    origins, direction, inside = pixel_origins(xs, ys, frame['pose'])
    depth, minimum, determinant = intersect_claimed(origins, direction, triangles[ids])
    actual = arrays['depth'][mask]
    audit.check(np.all(inside) and np.all(determinant != 0) and np.all(np.isfinite(depth))
                and np.all(minimum >= -BARYCENTRIC_ALLOWANCE),
                'every_foreground_pixel_independent_source_triangle_barycentric_membership')
    audit.check(np.all(depth >= frame['pose']['near'] - DEPTH_ALLOWANCE_M)
                and np.all(depth <= frame['pose']['far'] + DEPTH_ALLOWANCE_M)
                and np.all(np.abs(depth - actual) <= DEPTH_ALLOWANCE_M),
                'every_foreground_pixel_independent_camera_depth')
    first, second = triangles[ids, 1] - triangles[ids, 0], triangles[ids, 2] - triangles[ids, 0]
    normals = np.cross(first, second)
    light = np.asarray([.4, -.5, 1.])
    light /= np.linalg.norm(light)
    shade = .45 + .55 * np.abs(normals @ light) / np.linalg.norm(normals, axis=1)
    rgb = np.clip(shade[:, None] * np.asarray([180, 190, 205]), 0, 255).astype(np.uint8)
    audit.check(np.array_equal(rgb, arrays['color'][mask]), 'every_foreground_pixel_independent_source_normal_RGB')
    return dict(method='paired world-space Moller-Trumbore rays against each claimed original source triangle',
        foreground_pixels=len(xs), checked_source_memberships=len(xs), checked_depths=len(xs),
        maximum_depth_error_m=float(np.max(np.abs(depth - actual))) if len(xs) else 0.,
        minimum_barycentric_weight=float(minimum.min()) if len(xs) else None,
        source_edge_ambiguous_pixels=int(np.count_nonzero(minimum <= BARYCENTRIC_ALLOWANCE)),
        barycentric_allowance=BARYCENTRIC_ALLOWANCE, camera_depth_allowance_m=DEPTH_ALLOWANCE_M,
        nearest_surface_scope='separate fixed-grid and visible-selected-triangle representative rays')


def nearest_rays(origins, direction, triangles, near, far):
    """Bounded independent all-triangle nearest hits without a pixel raster."""
    a = triangles[:, 0]
    first, second = triangles[:, 1] - a, triangles[:, 2] - a
    h = np.cross(direction, second)
    determinant = np.einsum('ij,ij->i', first, h)
    reciprocal = np.divide(1., determinant, out=np.zeros_like(determinant), where=determinant != 0)
    best = np.full(len(origins), np.inf)
    winners = np.full(len(origins), -1, dtype=np.int64)
    edge = np.zeros(len(origins), dtype=bool)
    tied = np.zeros(len(origins), dtype=bool)
    for start in range(0, len(origins), RAY_CHUNK):
        stop = min(start + RAY_CHUNK, len(origins))
        delta = origins[start:stop, None, :] - a
        u = np.einsum('sti,ti->st', delta, h) * reciprocal
        q = np.cross(delta, first)
        v = np.einsum('sti,i->st', q, direction) * reciprocal
        depths = np.einsum('sti,ti->st', q, second) * reciprocal
        minimum = np.minimum(np.minimum(u, v), 1 - u - v)
        valid = ((determinant != 0) & (minimum >= -BARYCENTRIC_ALLOWANCE)
                 & (depths >= near) & (depths <= far) & np.isfinite(depths))
        candidates = np.where(valid, depths, np.inf)
        indices = np.argmin(candidates, axis=1)
        rows = np.arange(stop - start)
        closest = candidates[rows, indices]
        hit = np.isfinite(closest)
        best[start:stop] = closest
        winners[start:stop] = np.where(hit, indices, -1)
        edge[start:stop] = hit & (minimum[rows, indices] <= BARYCENTRIC_ALLOWANCE)
        difference = np.full(candidates.shape, np.inf)
        np.subtract(candidates, closest[:, None], out=difference, where=hit[:, None])
        tied[start:stop] = np.count_nonzero(valid & (np.abs(difference) <= DEPTH_ALLOWANCE_M), axis=1) > 1
    return best, winners, edge | tied


def sampled_nearest_checks(frame, arrays, triangles, object_ids, offsets, source_index, selected, audit):
    height, width = arrays['owners'].shape
    # Equal-stratum centre indices are fixed before looking at saved pixels.
    grid_x = np.floor((np.arange(GRID_SIDE) + .5) * width / GRID_SIDE).astype(int)
    grid_y = np.floor((np.arange(GRID_SIDE) + .5) * height / GRID_SIDE).astype(int)
    pixels = {(int(x), int(y)) for y in grid_y for x in grid_x}
    representatives = []
    flat = arrays['triangle_ids'].ravel()
    unique_ids, first_indices = np.unique(flat, return_index=True)
    first_by_id = dict(zip(unique_ids.tolist(), first_indices.tolist()))
    for local in selected:
        first_index = first_by_id.get(int(offsets[source_index] + local))
        if first_index is not None:
            y, x = divmod(first_index, width)
            pixels.add((x, y))
            representatives.append(dict(source_triangle_index=local, pixel=[x, y]))
    ordered = sorted(pixels, key=lambda point: (point[1], point[0]))
    xs, ys = np.asarray(ordered, dtype=int).T
    origins, direction, inside = pixel_origins(xs, ys, frame['pose'])
    best, winner, ambiguous = nearest_rays(origins, direction, triangles, frame['pose']['near'], frame['pose']['far'])
    best[~inside], winner[~inside] = np.inf, -1
    predicted = winner >= 0
    actual_ids = arrays['triangle_ids'][ys, xs]
    foreground = actual_ids >= 0
    audit.check(np.array_equal(predicted, foreground), 'fixed_sample_all_scene_nearest_foreground_mask')
    depths = arrays['depth'][ys, xs]
    audit.check(np.all(np.abs(depths[foreground] - best[foreground]) <= DEPTH_ALLOWANCE_M),
                'fixed_sample_all_scene_no_nearer_surface')
    certain = foreground & ~ambiguous
    audit.check(np.array_equal(actual_ids[certain], winner[certain])
                and np.array_equal(arrays['owners'][ys[certain], xs[certain]], object_ids[winner[certain]]),
                'fixed_sample_unambiguous_nearest_source_triangle_and_object')
    rows = []
    for index, pixel in enumerate(ordered):
        triangle = int(winner[index])
        obj = int(object_ids[triangle]) if triangle >= 0 else -1
        rows.append(dict(pixel=list(pixel), nearest_global_source_triangle=triangle, nearest_object_index=obj,
            nearest_local_source_triangle=int(triangle - offsets[obj]) if obj >= 0 else -1,
            camera_depth_m=float(best[index]) if predicted[index] else None,
            saved_global_source_triangle=int(actual_ids[index]), boundary_or_depth_tie=bool(ambiguous[index])))
    return dict(method='chunked independent Moller-Trumbore rays against every captured triangle',
        fixed_grid_side=GRID_SIDE, fixed_grid_samples=GRID_SIDE ** 2,
        visible_selected_triangle_representatives=representatives, deduplicated_samples=len(ordered),
        source_triangle_denominator=len(triangles), maximum_simultaneous_rays=RAY_CHUNK,
        ray_triangle_pairs=len(ordered) * len(triangles), checked_foreground_samples=int(foreground.sum()),
        checked_background_samples=int((~foreground).sum()), boundary_or_depth_tie_samples=int(ambiguous.sum()),
        all_image_pixels_checked_for_nearest_surface=False, samples=rows)


def closed_aabb(mesh):
    points = np.asarray(mesh['vertices'], dtype=np.float64)
    faces = np.asarray(mesh['faces'], dtype=np.int64)
    if points.shape != (8, 3) or faces.shape != (12, 3):
        return None
    low, high = points.min(axis=0), points.max(axis=0)
    if np.any(high <= low) or not np.all((points == low) | (points == high)):
        return None
    corners = {tuple(point) for point in points}
    if len(corners) != 8:
        return None
    sides = []
    for axis in range(3):
        free = [index for index in range(3) if index != axis]
        for boundary in (low[axis], high[axis]):
            rows = [face for face in faces if np.all(points[face, axis] == boundary)]
            if len(rows) != 2:
                return None
            shared = sorted(set(rows[0]) & set(rows[1]))
            if len(set(rows[0]) | set(rows[1])) != 4 or len(shared) != 2:
                return None
            if not np.all(points[shared[0], free] != points[shared[1], free]):
                return None
            sides.append(dict(axis=axis, boundary_m=float(boundary), triangle_vertex_rows=[row.tolist() for row in rows]))
    return dict(min_world_m=low.tolist(), max_world_m=high.tolist(), six_closed_rectangular_sides=sides)


def occluder_diagnosis(frame, capture, snapshot, triangles, object_ids, offsets, source_index, selected):
    pose = frame['pose']
    view = np.asarray(pose['view_matrix'], dtype=np.float64)
    inverse = np.linalg.inv(view)
    source_triangles = triangles[offsets[source_index] + np.asarray(selected)]
    centroids = source_triangles.mean(axis=1)
    camera = centroids @ view[:3, :3].T + view[:3, 3]
    origins = centroids + (-camera[:, 2, None]) * inverse[:3, 2]
    depths, winners, ambiguous = nearest_rays(origins, -inverse[:3, 2], triangles, pose['near'], pose['far'])
    blocked = (winners >= 0) & (depths < -camera[:, 2] - DEPTH_ALLOWANCE_M)
    counts = Counter(capture['meshes'][int(object_ids[index])]['name'] for index in winners[blocked])
    diagnoses = []
    for index, mesh in enumerate(capture['meshes']):
        cube = closed_aabb(mesh)
        if cube is None:
            continue
        low, high = np.asarray(cube['min_world_m']), np.asarray(cube['max_world_m'])
        minimum_margin = float(np.minimum(source_triangles - low, high - source_triangles).min())
        points = np.asarray(mesh['vertices'], dtype=np.float64)
        cube_depths = -(points @ view[2, :3] + view[2, 3])
        clip_complete = bool(np.all(cube_depths > pose['near']) and np.all(cube_depths < pose['far']))
        proven = minimum_margin > WORLD_ALLOWANCE_M and clip_complete
        original = next(row for row in snapshot['objects'] if row['name'] == mesh['name'])
        diagnoses.append(dict(object_index=index, object_name=mesh['name'], original_hide_render=original['display']['hide_render'],
            included_in_actual_surface_capture=True, closed_AABB_geometry=cube,
            selected_triangle_vertex_minimum_interior_margin_m=minimum_margin,
            cube_camera_depth_range_m=[float(cube_depths.min()), float(cube_depths.max())],
            cube_wholly_inside_positive_depth_clip=clip_complete,
            all_selected_continuous_triangle_surfaces_occluded_by_this_object=proven,
            proof=('Every selected triangle is a convex combination of strictly interior AABB vertices. '
                   'The complete closed box lies at positive camera depth inside the clipping interval. '
                   'Each orthographic ray reaching an interior point must first cross an included box surface.') if proven else None))
    rows = []
    for index, selected_row in enumerate(selected):
        global_row = int(winners[index])
        obj = int(object_ids[global_row]) if global_row >= 0 else -1
        rows.append(dict(selected_source_triangle_index=selected_row, centroid_world_m=centroids[index].tolist(),
            centroid_camera_depth_m=float(-camera[index, 2]), nearest_object_index=obj,
            nearest_object_name=capture['meshes'][obj]['name'] if obj >= 0 else None,
            nearest_local_source_triangle=int(global_row - offsets[obj]) if obj >= 0 else -1,
            nearest_camera_depth_m=float(depths[index]) if global_row >= 0 else None,
            centroid_occluded=bool(blocked[index]), boundary_or_depth_tie=bool(ambiguous[index])))
    return dict(centroid_sample_count=len(selected), occluded_centroid_samples=int(blocked.sum()),
        occluder_sample_counts=dict(counts), centroid_ray_triangle_pairs=len(selected) * len(triangles),
        centroid_visibility_scope='one fixed interior centroid per selected source triangle',
        closed_AABB_containment_proofs=diagnoses, centroid_samples=rows)


def check_frame(frame, full, capture, snapshot, triangles, object_ids, offsets, source_index, selected, vertices, audit):
    png = audit.file(frame['image_path'], frame['image_sha256'])
    raw = audit.file(frame['arrays_path'], frame['arrays_sha256'])
    with np.load(BytesIO(raw), allow_pickle=False) as saved:
        arrays = {name: saved[name] for name in saved.files}
    with Image.open(BytesIO(png)) as image:
        audit.check(image.format == 'PNG' and image.mode == 'RGB' and image.size == (512, 512)
                    and np.array_equal(np.asarray(image), arrays['color']), 'original_PNG_exact_RGB_array')
    for name, dtype, shape in (('color', 'uint8', (512, 512, 3)), ('depth', 'float64', (512, 512)),
                              ('owners', 'int32', (512, 512)), ('triangle_ids', 'int32', (512, 512)),
                              ('patch_owners', 'int32', (512, 512))):
        value = arrays[name]
        audit.check(value.dtype == np.dtype(dtype) and value.shape == shape, 'buffer_dtype_shape/' + name)
        audit.check(frame['arrays'][name] == dict(dtype=dtype, shape=list(shape), nbytes=value.nbytes,
            sha256=hashlib.sha256(value.tobytes()).hexdigest()), 'original_buffer_bytes/' + name)
    audit.check(len(png) == frame['PNG_bytes'] and len(raw) == frame['compressed_array_file_bytes'], 'original_encoded_frame_sizes')
    ids = np.full(len(triangles), -1, dtype=np.int32)
    audit.check(np.array_equal(arrays['face_patch_offsets'], offsets)
                and np.array_equal(arrays['face_patch_ids'], ids) and arrays['patch_roi_ids'].tolist() == [],
                'complete_original_source_triangle_offsets_empty_rectangular_patch_map')
    ordered = [(tuple(tuple(Fraction(value) for value in point) for point in mesh['vertices']), tuple(tuple(face) for face in mesh['faces']))
               for mesh in capture['meshes']]
    pixel_helper = SAVED.PIXELS
    mapping = fingerprint(dict(version=pixel_helper.PATCH_SCHEMA, roi_ids=(), ordered_geometry=ordered,
                               face_patch_ids=[[-1] * len(mesh['faces']) for mesh in capture['meshes']]))
    owner_mapping = fingerprint((pixel_helper.OWNER_SCHEMA, pixel_helper.TRIANGLE_SCOPE, mapping, offsets.tolist()))
    for name, expected in (('owner_schema', pixel_helper.OWNER_SCHEMA), ('triangle_id_scope', pixel_helper.TRIANGLE_SCOPE),
                          ('patch_mapping_version', pixel_helper.PATCH_SCHEMA), ('patch_mapping_identity', mapping),
                          ('owner_mapping_identity', owner_mapping)):
        audit.check(frame[name] == arrays[name].item() == expected, 'original_owner_mapping_preimage/' + name)
    binding = full['binding']
    audit.check(frame['host_binding_sha256'] == binding['binding_sha256']
                and frame['source_revision'] == binding['scene_revision']
                and frame['scene_identity'] == binding['geometry_identity']
                and frame['candidate_identity'] == binding['camera_identity'], 'original_frame_current_geometry_camera_binding')
    audit.check(frame['all_object_count'] == len(capture['meshes']) and frame['all_triangle_count'] == len(triangles),
                'original_frame_all_scene_occlusion_denominator')
    audit.check(frame['pose'] == next(pose for pose in binding['camera_specification']['views'] if pose['name'] == frame['view_name']),
                'original_frame_exact_published_pose')
    preimage = ((frame['scene_identity'], frame['candidate_identity']), pixel_helper.OWNER_SCHEMA,
                owner_mapping, frame['view_name'], 1, frame['image_sha256'])
    audit.check(frame['frame_identity'] == fingerprint(preimage)
                and frame['image_ref'] == 'source-region-image:' + fingerprint((full['region_ref']['region_id'],
                    frame['frame_identity'], frame['image_sha256'])), 'original_frame_and_region_image_identity_preimages')
    owners, source_ids, depth = arrays['owners'], arrays['triangle_ids'], arrays['depth']
    foreground = owners >= 0
    audit.check(np.all(owners >= -1) and np.all(owners < len(capture['meshes']))
                and np.all(source_ids >= -1) and np.all(source_ids < len(triangles))
                and np.array_equal(source_ids >= 0, foreground), 'all_image_source_owner_ranges')
    audit.check(np.all(source_ids[foreground] >= offsets[owners[foreground]])
                and np.all(source_ids[foreground] < offsets[owners[foreground] + 1])
                and np.all(arrays['patch_owners'] == -1), 'every_foreground_source_triangle_object_membership')
    audit.check(np.all(np.isposinf(depth[~foreground]))
                and np.all(np.isfinite(depth[foreground]) & (depth[foreground] > 0))
                and np.all(arrays['color'][~foreground] == [18, 22, 30]), 'background_RGB_infinite_depth_and_positive_foreground')
    source_points = np.asarray(capture['meshes'][source_index]['vertices'], dtype=np.float64)[vertices]
    camera = camera_checks(frame['pose'], source_points, capture, audit)
    pixel_review = claimed_pixel_checks(frame, arrays, triangles, audit)
    sample_review = sampled_nearest_checks(frame, arrays, triangles, object_ids, offsets, source_index, selected, audit)
    counts = np.bincount(source_ids[foreground], minlength=len(triangles))
    selected_counts = {str(index): int(counts[offsets[source_index] + index]) for index in selected}
    visible = [index for index in selected if selected_counts[str(index)] > 0]
    unseen = [index for index in selected if selected_counts[str(index)] == 0]
    mask = np.isin(source_ids, offsets[source_index] + np.asarray(selected))
    ys, xs = np.nonzero(mask)
    bounds = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None
    visibility = full['facts']['visibility']
    audit.check(visibility['visible_source_triangle_indices'] == visible
                and visibility['unseen_source_triangle_indices'] == unseen
                and visibility['selected_surface_pixels'] == len(xs) and visibility['visible_pixel_bounds'] == bounds
                and visibility['image_ref'] == frame['image_ref'], 'published_selected_visibility_matches_all_saved_source_pixels')
    audit.check(visibility['complete_witness'] is None
                and visibility['visibility_scope'] == 'actual_frame_source_triangle_samples'
                and 'complete_surface_visibility' in visibility['unknown'], 'published_visibility_complete_surface_unknown')
    occlusion = occluder_diagnosis(frame, capture, snapshot, triangles, object_ids, offsets, source_index, selected)
    return dict(frame_identity=frame['frame_identity'], image_ref=frame['image_ref'], image_path=frame['image_path'],
        image_sha256=frame['image_sha256'], view_name=frame['view_name'], camera_fit=camera,
        full_image_source_pixel_review=pixel_review, sampled_nearest_scene_review=sample_review,
        selected_region_image_evidence='pass' if len(xs) else 'unknown',
        selected_region_image_reason='actual_selected_source_triangle_samples' if len(xs) else 'saved_image_has_zero_selected_source_triangle_pixels',
        selected_surface_pixels=len(xs), selected_triangle_pixel_counts=selected_counts,
        visible_source_triangle_indices=visible, unseen_source_triangle_indices=unseen,
        complete_selected_surface_visibility='unknown', occluder_diagnosis=occlusion,
        visible_object_pixel_counts={mesh['name']: int(np.count_nonzero(owners == index)) for index, mesh in enumerate(capture['meshes'])})


def review(full, capture, snapshot, audit):
    started = time.perf_counter()
    audit.check(full['read_only'] is True and full['execution_authority'] is False, 'original_source_region_read_only')
    source = snapshot_checks(snapshot, capture, full['binding'], audit)
    source_index, selected, vertices = region_checks(full, capture, audit)
    triangles, object_ids, offsets = scene_arrays(capture)
    frames = [check_frame(frame, full, capture, snapshot, triangles, object_ids, offsets,
                          source_index, selected, vertices, audit) for frame in full['frames']]
    return dict(schema='m4-real-asset-saved-image-review-v1', passed_checked_scope=True,
        saved_image_integrity='pass' if frames else 'not_run',
        selected_region_image_evidence='pass' if any(frame['selected_surface_pixels'] for frame in frames) else 'unknown',
        selected_region_image_reason=None if any(frame['selected_surface_pixels'] for frame in frames)
            else ('saved_images_have_zero_selected_source_triangle_pixels' if frames else 'no_saved_image'),
        selected_source_triangle_count=len(selected), selected_source_vertex_count=len(vertices),
        source_object_index=source_index, source_object_name=capture['meshes'][source_index]['name'],
        fresh_source_capture_comparisons=source, all_scene_triangle_count=len(triangles), frames=frames,
        independent_check_elapsed_seconds=time.perf_counter() - started,
        precision=dict(barycentric_allowance=BARYCENTRIC_ALLOWANCE, camera_depth_allowance_m=DEPTH_ALLOWANCE_M,
                       snapshot_world_coordinate_allowance_m=WORLD_ALLOWANCE_M),
        nearest_ray_policy=dict(grid_side=GRID_SIDE, representative='first row-major visible pixel per selected triangle',
                               additional_diagnosis='one centroid per selected source triangle', ray_chunk=RAY_CHUNK),
        full_foreground_nearest_surface_claim=False, product_imports=0,
        author_association='Independent saved-image checker reuses the previous batch byte reader and wire decoder. It imports no product module.',
        new_operations=dict(Blender=0, raster=0, model=0, paid=0), checks=audit.checks,
        input_pins=list(audit.pins.values()))


def check_saved(full_path, capture_path, snapshot_path, output=None):
    audit = Audit()
    full, document, snapshot = [audit.read(path) for path in (full_path, capture_path, snapshot_path)]
    result = review(full, document.get('capture', document), snapshot, audit)
    result['original_public_delivery_checked'] = False
    if output is not None:
        Path(output).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n', encoding='utf8')
    return result


def check_session(session, run_binding, snapshot, call_index=1):
    session = Path(session).resolve()
    audit = Audit()
    installed = audit.read(run_binding)
    calls = [json.loads(line) for line in audit.file(session / 'PUBLIC_REQUESTS.jsonl').splitlines() if line.strip()]
    call = calls[call_index - 1]
    full = audit.read(call['producer_archive']['path'], call['producer_archive']['sha256'], session)
    request = audit.read(call['request_path'], call['request_sha256'], session)
    response = audit.read(call['response_path'], call['response_sha256'], session)
    audit.check(request == audit.read(call['actual_TX_path'], call['actual_TX_sha256'], session)
                and response == audit.read(call['actual_RX_path'], call['actual_RX_sha256'], session),
                'original_public_request_response_actual_stdio_bytes')
    audit.check(request['id'] == response['id'] and response['result']['isError'] is False
                and request['params']['name'] == 'human_eye_scene_observe'
                and request['params']['arguments']['query']['mode'] == 'source_region',
                'original_public_source_region_entry_and_success')
    blocks = response['result']['content']
    images = [block for block in blocks if block['type'] == 'image']
    texts = [json.loads(block['text']) for block in blocks if block['type'] == 'text']
    audit.check(len(texts) == 1 and texts[0]['region_ref'] == full['region_ref'], 'original_public_text_same_region_ref')
    audit.check(len(images) == len(full['frames']), 'original_public_native_image_count')
    for image, frame in zip(images, full['frames'], strict=True):
        audit.check(image['mimeType'] == 'image/png' and base64.b64decode(image['data'], validate=True)
                    == audit.file(frame['image_path'], frame['image_sha256'], session), 'original_public_native_PNG_exact_saved_bytes')
    captures, commands = SAVED.decode_captures(session, installed, audit)
    capture = SAVED.current_capture(captures, full['binding'], audit)
    result = review(full, capture, audit.read(snapshot), audit)
    result.update(session=str(session), call_index=call_index, original_wire_commands=commands,
                  original_public_delivery_checked=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', type=Path)
    parser.add_argument('--capture', type=Path)
    parser.add_argument('--session', type=Path)
    parser.add_argument('--run-binding', type=Path)
    parser.add_argument('--call-index', type=int, default=1)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.session is not None:
            result = check_session(args.session, args.run_binding, args.snapshot, args.call_index)
        else:
            result = check_saved(args.full, args.capture, args.snapshot)
    except Exception as error:
        result = dict(schema='m4-real-asset-saved-image-review-v1', passed_checked_scope=False,
            error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc(),
            new_operations=dict(Blender=0, raster=0, model=0, paid=0))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n', encoding='utf8')
    print(json.dumps(dict(passed_checked_scope=result['passed_checked_scope'], output=str(args.output.resolve()),
                         error=result.get('error'), selected_region_image_evidence=result.get('selected_region_image_evidence'))))
    if not result['passed_checked_scope']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

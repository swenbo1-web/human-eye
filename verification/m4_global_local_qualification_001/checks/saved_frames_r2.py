"""Read original, closed global/local sessions without importing product code.

This checker establishes delivered-byte, array, source-index and scope facts.
Geometric eligibility and exact occlusion are supplied by separate independent
oracles. A patch map that is internally consistent is not, alone, a geometry
qualification. No Blender, renderer, MCP or model is invoked here.
"""

import argparse
import ast
import base64
import copy
from fractions import Fraction as F
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import re
import sys
import zlib


DEPENDENCIES = Path('D:/he_anchor_001/venv/Lib/site-packages')
sys.path.insert(0, str(DEPENDENCIES))
import numpy as np
from PIL import Image


ORDER = ['SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK']
DIRECTIONS = [[4, -4, 3], [0, 0, 1], [-1, 0, 1], [1, 0, 1], [0, -1, 1], [0, 1, 1]]
OWNER_SCHEMA = 'active-dual-owner-v1'
TRIANGLE_SCOPE = 'zero-based-global-source-triangles-in-mesh-order'
PATCH_SCHEMA = 'active-patch-owner-v1'
NAMESPACE = Path(__file__).resolve().parent.parent


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fingerprint(value):
    encoded = json.dumps(value, default=str, sort_keys=True, separators=(',', ':')).encode('utf8')
    return hashlib.sha256(encoded).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


class Evidence:
    def __init__(self):
        self.pins = {}
        self.checks = []

    def file(self, path, expected=None, within=None):
        path = Path(path).resolve()
        if within is not None:
            require(path.is_relative_to(Path(within).resolve()), 'source_file_outside_current_session')
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        require(expected is None or digest == expected, 'original_file_sha256_changed')
        self.pins[str(path)] = {'path': str(path), 'sha256': digest, 'bytes': len(raw)}
        return raw

    def check(self, condition, name):
        require(condition, name)
        self.checks.append({'check': name, 'passed': True})


def contrasting_boundary(rgb, patches):
    """Independent direct integer squared RGB metric on four-neighbour pairs."""
    mask = np.zeros(patches.shape, dtype=bool)
    for vertical in (True, False):
        a = (slice(None, -1), slice(None)) if vertical else (slice(None), slice(None, -1))
        b = (slice(1, None), slice(None)) if vertical else (slice(None), slice(1, None))
        difference = rgb[a].astype(np.int32) - rgb[b].astype(np.int32)
        contrast = np.sum(difference * difference, axis=2) >= 576
        changed = (patches[a] != patches[b]) & contrast
        mask[a] |= changed
        mask[b] |= changed
    return mask


def pixel_location(mask):
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None, None
    low_x, high_x = int(xs.min()), int(xs.max())
    low_y, high_y = int(ys.min()), int(ys.max())
    metric = (2 * xs - low_x - high_x) ** 2 + (2 * ys - low_y - high_y) ** 2
    chosen = int(np.argmin(metric))
    return [low_x, low_y, high_x, high_y], [int(xs[chosen]), int(ys[chosen])]


def source_binding_checks(capture, binding, evidence):
    targeted = 'observation_target' in capture
    scope = 'target_observation_meshes' if targeted else 'complete_scene_meshes'
    identity = capture['host_identity']
    evidence.check(capture.get('capture_scope', 'complete_scene_meshes') == identity['capture_scope'] == binding['capture_scope'] == scope,
                   'parent_scope_preserved')
    evidence.check(binding['scene_revision'] == capture['revision']
                   and binding['document_epoch'] == identity['document_epoch']
                   and binding['capture_state'] == capture['capture_state'], 'current_capture_generation')
    expected_objects = [dict(object_index=index, host_id=mesh['object_id'], object_name=mesh['name'],
                             instance_id=identity['object_instances'][mesh['object_id']])
                        for index, mesh in enumerate(capture['meshes'])]
    evidence.check(binding['objects'] == expected_objects, 'actual_ordered_host_instance_mapping')
    evidence.check(binding['unit'] == capture['unit'] == 'm'
                   and binding['coordinate_frame'] == capture['coordinate_frame'] == 'world'
                   and binding['source'] == capture['source'] == 'blender', 'actual_source_units')
    base = {key: item for key, item in binding.items() if key not in {
        'source_binding_sha256', 'camera_specification', 'geometry_identity', 'camera_identity', 'binding_sha256',
        'runtime_source_sha256', 'source_status', 'disk_status', 'source_check_scope'}}
    evidence.check(fingerprint(base) == binding['source_binding_sha256'], 'source_binding_preimage')
    added_keys = {'runtime_source_sha256', 'source_status', 'disk_status', 'source_check_scope'}
    if set(binding) & added_keys:
        evidence.check(binding.get('runtime_source_sha256') == '7d2d4352f462c64a46e6fccf447c6f030c08b96e95517a3b2b6776ed50b69a6a'
                       and binding.get('source_status') == 'loaded_generation'
                       and binding.get('disk_status') == 'disk_not_checked'
                       and binding.get('source_check_scope') == 'bound_generation_identity',
                       'service_appended_frozen_runtime_source_attestation')
    complete = {key: item for key, item in binding.items() if key not in added_keys | {'binding_sha256'}}
    evidence.check(fingerprint(complete) == binding['binding_sha256'], 'camera_binding_preimage')
    cameras = binding['camera_specification']
    views = cameras['views']
    evidence.check([view['name'] for view in views] == ORDER
                   and [view['direction_rational'] for view in views] == DIRECTIONS,
                   'published_finite_six_view_policy')
    evidence.check(all(view['size_px'] == [512, 512] and view['projection'] == 'orthographic' for view in views),
                   'published_orthographic_512_devices')
    identity_rows = [{key: view[key] for key in (
        'name', 'direction_rational', 'view_matrix', 'projection_matrix', 'size_px')} for view in views]
    evidence.check(fingerprint(identity_rows) == binding['camera_identity'], 'published_camera_identity')
    if targeted:
        target = capture['observation_target']
        public = binding['observation_target']
        fields = ('schema', 'selector', 'target_object_id', 'target_instance_id', 'target_object_index',
                  'full_scene_identity', 'retained_object_ids', 'excluded_object_ids',
                  'directory_sha256', 'source_frame')
        evidence.check(all(public[key] == target[key] for key in fields)
                       and public['camera_plan_sha256'] == fingerprint(target['camera_plan'])
                       and target['camera_plan'] == cameras, 'current_target_metadata_and_camera_plan')
        directory_raw = json.dumps(target['scene_directory'], sort_keys=True, separators=(',', ':'),
                                   ensure_ascii=False, allow_nan=False).encode('utf8')
        evidence.check(hashlib.sha256(directory_raw).hexdigest() == public['directory_sha256'],
                       'complete_scene_directory_digest')
        retained = [mesh['object_id'] for mesh in capture['meshes']]
        evidence.check(retained == target['retained_object_ids']
                       and set(retained).isdisjoint(target['excluded_object_ids'])
                       and set(retained) | set(target['excluded_object_ids'])
                       == set(target['full_scene_identity']['object_instances']), 'retained_excluded_full_scene_partition')
    else:
        evidence.check('observation_target' not in binding, 'global_has_no_hidden_target_binding')
    return views


def partition_checks(full, capture, evidence):
    scope = full['facts']['scope']
    support = scope['patch_support']
    rows, regions = support['objects'], support['regions']
    meshes = capture['meshes']
    evidence.check(len(rows) == len(meshes) == scope['capture_object_count'], 'complete_captured_object_denominator')
    evidence.check([row['object_index'] for row in rows] == list(range(len(meshes))), 'partition_object_order')
    facts = {row['roi_id']: row for row in full['facts']['regions']}
    evidence.check(len(facts) == len(full['facts']['regions']) == len(regions)
                   and set(facts) == {row['roi_id'] for row in regions}, 'unique_region_partition_bijection')
    region_order = [row['roi_id'] for row in regions]
    evidence.check(region_order == sorted(region_order), 'canonical_unique_patch_order')
    face_patch = [np.full(len(mesh['faces']), -1, dtype=np.int32) for mesh in meshes]
    for patch_index, region in enumerate(regions):
        index = region['object_index']
        faces = region['triangle_indices']
        evidence.check(len(faces) == len(set(faces)) and bool(faces)
                       and all(type(face) is int and 0 <= face < len(face_patch[index]) for face in faces),
                       'object_local_source_triangle_indices')
        evidence.check(all(face_patch[index][face] == -1 for face in faces), 'unique_patch_source_triangle_membership')
        face_patch[index][faces] = patch_index
        host = full['binding']['objects'][index]
        fact = facts[region['roi_id']]
        evidence.check(fact['object_index'] == index and fact['object_name'] == host['object_name']
                       and fact['host_id'] == host['host_id'] and fact['instance_id'] == host['instance_id'],
                       'region_current_real_host_identity')
    for index, row in enumerate(rows):
        assigned = set(np.flatnonzero(face_patch[index] >= 0).tolist())
        unsupported = [face for component in row['unsupported_components'] for face in component['triangle_indices']]
        count = len(meshes[index]['faces'])
        evidence.check(row['source_triangle_count'] == count and set(row['supported_triangle_indices']) == assigned
                       and row['supported_triangle_count'] == len(assigned)
                       and row['unsupported_triangle_count'] == len(unsupported)
                       and len(set(unsupported)) == len(unsupported) and assigned.isdisjoint(unsupported),
                       'supported_unsupported_source_counts')
        if row['support_status'] == 'occluder_only':
            evidence.check(not assigned and not unsupported and row['coverage_role'] == 'occluder_only',
                           'non_target_is_occluder_only')
        else:
            evidence.check(assigned | set(unsupported) == set(range(count)), 'source_faces_exhaustive_partition')
        evidence.check(all(component['status'] == 'unknown' and component['reason']
                           for component in row['unsupported_components']), 'unsupported_reasons_remain_unknown')
    if 'observation_target' in capture:
        target = capture['observation_target']['target_object_index']
        evidence.check(all(region['object_index'] == target for region in regions), 'target_only_coverage_regions')
    return regions, face_patch


def frame_checks(frame, observation, full, capture, regions, face_patch, image_block, session, evidence):
    png = evidence.file(frame['image_path'], frame['image_sha256'], session)
    npz = evidence.file(frame['arrays_path'], frame['arrays_sha256'], session)
    evidence.check(len(png) == frame['PNG_bytes'] and len(npz) == frame['compressed_array_file_bytes'],
                   'actual_frame_encoded_sizes')
    evidence.check(image_block.get('type') == 'image' and image_block.get('mimeType') == 'image/png'
                   and base64.b64decode(image_block['data'], validate=True) == png, 'actual_stdio_native_png_bytes')
    with np.load(BytesIO(npz), allow_pickle=False) as saved:
        arrays = {key: saved[key] for key in saved.files}
    with Image.open(BytesIO(png)) as image:
        evidence.check(image.format == 'PNG' and image.mode == 'RGB' and image.size == (512, 512)
                       and np.array_equal(np.asarray(image), arrays['color']), 'PNG_RGB_array_exact_equality')
    expected = {'color': (np.dtype('uint8'), (512, 512, 3)), 'depth': (np.dtype('float64'), (512, 512)),
                'owners': (np.dtype('int32'), (512, 512)), 'triangle_ids': (np.dtype('int32'), (512, 512)),
                'patch_owners': (np.dtype('int32'), (512, 512))}
    for name, (dtype, shape) in expected.items():
        values = arrays[name]
        evidence.check(values.dtype == dtype and values.shape == shape, 'actual_buffer_shape_dtype_' + name)
        metadata = frame['arrays'][name]
        evidence.check(metadata == dict(dtype=str(dtype), shape=list(shape), nbytes=int(values.nbytes),
                                       sha256=hashlib.sha256(values.tobytes(order='C')).hexdigest()),
                       'raw_buffer_bytes_binding_' + name)
    rgb, depth, owners, triangles, patches = (arrays[key] for key in expected)
    offsets = np.cumsum([0] + [len(mesh['faces']) for mesh in capture['meshes']], dtype=np.int64)
    ids = np.concatenate(face_patch)
    roi_ids = [row['roi_id'] for row in regions]
    ordered = [(tuple(tuple(F(value) for value in point) for point in mesh['vertices']),
                tuple(tuple(face) for face in mesh['faces'])) for mesh in capture['meshes']]
    mapping = fingerprint(dict(version=PATCH_SCHEMA, roi_ids=tuple(roi_ids), ordered_geometry=ordered,
                               face_patch_ids=[values.tolist() for values in face_patch]))
    owner_identity = fingerprint((OWNER_SCHEMA, TRIANGLE_SCOPE, mapping, offsets.tolist()))
    evidence.check(arrays['face_patch_offsets'].dtype == np.int64
                   and np.array_equal(arrays['face_patch_offsets'], offsets)
                   and arrays['face_patch_ids'].dtype == np.int32 and np.array_equal(arrays['face_patch_ids'], ids)
                   and arrays['patch_roi_ids'].tolist() == roi_ids, 'actual_mesh_order_local_to_global_triangle_map')
    for key, value in (('owner_schema', OWNER_SCHEMA), ('triangle_id_scope', TRIANGLE_SCOPE),
                       ('patch_mapping_version', PATCH_SCHEMA), ('patch_mapping_identity', mapping),
                       ('owner_mapping_identity', owner_identity)):
        evidence.check(arrays[key].item() == value and frame[key] == value, 'saved_frame_mapping_' + key)
    foreground = owners >= 0
    evidence.check(np.all(owners >= -1) and np.all(owners < len(capture['meshes']))
                   and np.array_equal(triangles >= 0, foreground)
                   and np.all(triangles >= -1) and np.all(triangles < offsets[-1]), 'common_depth_owner_triangle_alignment')
    evidence.check(np.all(np.isposinf(depth[~foreground]))
                   and np.all(np.isfinite(depth[foreground]) & (depth[foreground] > 0)), 'foreground_depth_and_background_infinity')
    evidence.check(np.all(rgb[~foreground] == [18, 22, 30]) and np.all(patches[~foreground] == -1),
                   'background_color_and_patch')
    winner_ids, object_ids = triangles[foreground], owners[foreground]
    evidence.check(np.all(winner_ids >= offsets[object_ids]) and np.all(winner_ids < offsets[object_ids + 1])
                   and np.array_equal(patches[foreground], ids[winner_ids]), 'winning_raw_triangle_object_and_patch')
    binding = full['binding']
    evidence.check(frame['host_binding_sha256'] == binding['binding_sha256']
                   and frame['source_revision'] == binding['scene_revision']
                   and frame['scene_identity'] == full['facts']['scene_identity']
                   and frame['candidate_identity'] == full['facts']['candidate_identity'], 'frame_current_parent_binding')
    reference = (binding['binding_sha256'], frame['view_name'], frame['image_sha256'], mapping,
                 OWNER_SCHEMA, owner_identity, frame['frame_identity'])
    evidence.check(frame['image_ref'] == 'active-host-image:' + fingerprint(reference)
                   and observation['image_ref'] == frame['image_ref']
                   and observation['image_sha256'] == frame['image_sha256'], 'actual_image_reference_preimage')
    pose = next(view for view in binding['camera_specification']['views'] if view['name'] == frame['view_name'])
    evidence.check(frame['pose'] == pose, 'frame_exact_published_pose')
    boundary = contrasting_boundary(rgb, patches)
    pixel_rows = observation['pixel_rows']
    evidence.check(len(pixel_rows) == len(regions)
                   and {row['roi_id'] for row in pixel_rows} == set(roi_ids), 'complete_unique_actual_pixel_rows')
    row_by_id = {row['roi_id']: row for row in pixel_rows}
    facts = {row['roi_id']: row for row in full['facts']['regions']}
    counts = []
    for patch_index, region in enumerate(regions):
        roi = region['roi_id']
        mask = patches == patch_index
        surface = int(np.count_nonzero(mask))
        contrast = int(np.count_nonzero(mask & boundary))
        bounds, anchor = pixel_location(mask)
        front = float(np.dot(np.asarray([float(F(value)) for value in facts[roi]['front_direction_world']], dtype=float),
                             np.asarray(pose['target_to_eye_unit']))) > 0
        readable = front and surface >= 16 and contrast >= 4
        row = row_by_id[roi]
        evidence.check(row['visible_surface_pixels'] == surface and row['contrasting_boundary_pixels'] == contrast
                       and row['front_facing'] is front and row['readable'] is readable
                       and row['minimum_surface_pixels'] == 16 and row['minimum_boundary_pixels'] == 4
                       and row['minimum_rgb_boundary_contrast'] == 24
                       and row['visible_pixel_bounds'] == bounds and row['visible_pixel_anchor'] == anchor,
                       'recomputed_actual_pixel_evidence')
        counts.append(dict(roi_id=roi, object_index=region['object_index'], surface_pixels=surface,
                           boundary_pixels=contrast, readable=readable, visible_pixel_bounds=bounds))
    evidence.check(sorted(observation['readable_roi_ids']) == sorted(row['roi_id'] for row in counts if row['readable']),
                   'receipt_readable_set_matches_actual_pixels')
    ray_review = ray_winner_checks(frame, capture, arrays, evidence)
    return dict(view_name=frame['view_name'], image_ref=frame['image_ref'], pixels=counts,
                independent_ray_review=ray_review,
                foreground_pixels=int(np.count_nonzero(foreground)), source_triangle_count=int(offsets[-1]))


def pixel_bbox_upper(vertices, faces, pose):
    """Exact published binary64 matrix projection, with outward pixel margin.

    The fixed 2^-16 pixel margin is an independent analysis allowance registered
    by the geometric oracle. This is an upper bound on possible covered centres,
    not a raster invocation or proof that a pixel is visible.
    """
    view = [[F(value) for value in row] for row in pose['view_matrix']]
    projection = [[F(value) for value in row] for row in pose['projection_matrix']]
    points = []
    for index in sorted({index for face in faces for index in face}):
        point = [F(value) for value in vertices[index]] + [F(1)]
        camera = [sum(a * b for a, b in zip(row, point)) for row in view]
        clip = [sum(a * b for a, b in zip(row, camera)) for row in projection]
        require(clip[3] == 1, 'registered_orthographic_affine_projection')
        points.append(((clip[0] + 1) * F(511, 2), (1 - clip[1]) * F(511, 2)))
    margin = F(1, 65536)
    intervals, dimensions = [], []
    for axis in (0, 1):
        lower, upper = min(point[axis] for point in points), max(point[axis] for point in points)
        first = max(0, math.ceil(lower - margin - F(1, 2)))
        last = min(511, math.floor(upper + margin - F(1, 2)))
        dimensions.append(max(0, last - first + 1))
        intervals.append(dict(exact_min=str(lower), exact_max=str(upper),
                              outward_margin_px=str(margin), first_center_index=first, last_center_index=last))
    return dict(view_name=pose['name'], pixel_center_bbox_upper=dimensions[0] * dimensions[1],
                dimensions=dimensions, screen_intervals=intervals)


def decode_current_capture(session, expected_binding, evidence):
    """Decode original host packets and resident resource references as data."""
    run_binding = json.loads(evidence.file(NAMESPACE / 'B_RUN_BINDING.json'))
    manifest = {row['path']: row['sha256'] for row in run_binding['source_manifest']}
    resources, captures, steps, loaded = {}, [], [], {}
    for folder in sorted((Path(session) / 'native/WIRE').glob('[0-9]*')):
        request_path, response_path = folder / 'REQUEST.bin', folder / 'RESPONSE.bin'
        request = json.loads(evidence.file(request_path, within=session))
        response = json.loads(evidence.file(response_path, within=session))
        if request.get('type') != 'execute_code':
            continue
        code = request['params']['code']
        for node in ast.walk(ast.parse(code)):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == 'compile' and len(node.args) >= 2):
                continue
            expression = node.args[0]
            if not (isinstance(expression, ast.Call) and isinstance(expression.func, ast.Attribute)
                    and expression.func.attr == 'decompress'):
                continue
            compressed = ast.literal_eval(expression.args[0].args[0])
            source_bytes = zlib.decompress(base64.b64decode(compressed, validate=True))
            relative = Path(ast.literal_eval(node.args[1])).relative_to(Path(run_binding['install_root'])).as_posix()
            digest = hashlib.sha256(source_bytes).hexdigest()
            evidence.check(manifest.get(relative) == digest, 'actual_loaded_source_payload_pin')
            loaded[relative] = digest
        matched = re.search(r'_request = _json.loads\((.+)\)\n', code)
        if matched is None:
            continue
        command = json.loads(ast.literal_eval(matched.group(1)))
        lines = [line for line in response.get('result', {}).get('result', '').splitlines()
                 if line.startswith('HUMAN_EYE_BLENDER_MCP:')]
        evidence.check(response.get('status') == 'success' and len(lines) == 1,
                       'actual_host_packet_success_and_unique_marker')
        packet = json.loads(lines[0].split(':', 1)[1])
        evidence.check(packet.get('error') is None, 'actual_host_packet_without_error')
        value = packet.get('result')
        if type(value) is not dict:
            continue
        for resource in value.get('resources', []):
            key = (resource['id'], resource['revision'])
            evidence.check(key not in resources or resources[key] == resource, 'resident_resource_immutable_identity')
            resources[key] = resource
        capture = copy.deepcopy(value.get('capture', value))
        if not capture.get('meshes'):
            continue
        for mesh in capture['meshes']:
            reference = mesh.pop('_scene_resource', None)
            if reference is not None:
                resource = resources[(reference['id'], reference['revision'])]
                matrix, scale = reference['matrix'], reference['scale']
                mesh.update(vertices=[[(((matrix[axis][0] * point[0] + matrix[axis][1] * point[1])
                                           + matrix[axis][2] * point[2]) + matrix[axis][3]) * scale
                                       for axis in range(3)] for point in resource['vertices_local']],
                            faces=copy.deepcopy(resource['faces']), edges=copy.deepcopy(resource['edges']))
        captures.append(capture)
        steps.append(dict(wire_sequence=int(folder.name), command=command,
                          request_path=str(request_path), response_path=str(response_path)))
    evidence.check(loaded.get('human_eye_plugin/blender_host.py') == manifest['human_eye_plugin/blender_host.py'],
                   'fixed_host_source_loaded_from_actual_request')
    matches = [capture for capture in captures if capture.get('revision') == expected_binding['scene_revision']
               and capture.get('capture_scope', 'complete_scene_meshes') == expected_binding['capture_scope']]
    evidence.check(len(matches) == 1, 'unique_current_original_capture')
    return matches[0], steps


def ray_winner_checks(frame, capture, arrays, evidence):
    """Independent inverse-camera rays intersect original world triangles.

    The result is checked against the saved buffers. No frame is generated.
    Barycentric bands <=1e-8 and camera-depth ties <=1e-8 m are explicitly
    reported as numerically ambiguous for exact triangle ownership. All pixels
    still require an admissible closest intersection and matching object/depth.
    """
    pose = frame['pose']
    size = 512
    view = np.asarray(pose['view_matrix'], dtype=np.float64)
    projection = np.asarray(pose['projection_matrix'], dtype=np.float64)
    evidence.check(np.allclose(projection[:2, :], [[projection[0, 0], 0, 0, 0],
                                                 [0, projection[1, 1], 0, 0]], rtol=0, atol=0),
                   'ray_oracle_supported_diagonal_orthographic_camera')
    inverse = np.linalg.inv(view)
    ys, xs = np.indices((size, size), dtype=np.float64)
    camera_x = (2 * (xs.ravel() + .5) / 511 - 1) / projection[0, 0]
    camera_y = (1 - 2 * (ys.ravel() + .5) / 511) / projection[1, 1]
    sample_inside_xy_frustum = ((np.abs(2 * (xs.ravel() + .5) / 511 - 1) <= 1)
                                & (np.abs(1 - 2 * (ys.ravel() + .5) / 511) <= 1))
    origins = (camera_x[:, None] * inverse[:3, 0] + camera_y[:, None] * inverse[:3, 1]
               + inverse[:3, 3])
    ray = -inverse[:3, 2]
    pixel_count = size * size
    best = np.full(pixel_count, np.inf)
    best_object = np.full(pixel_count, -1, dtype=np.int32)
    best_triangle = np.full(pixel_count, -1, dtype=np.int32)
    best_rgb = np.zeros((pixel_count, 3), dtype=np.uint8)
    admissible_actual = np.zeros(pixel_count, dtype=bool)
    actual_triangles = arrays['triangle_ids'].ravel()
    actual_objects = arrays['owners'].ravel()
    actual_depth = arrays['depth'].ravel()
    ambiguous = np.zeros(pixel_count, dtype=bool)
    tolerance = 1e-8
    light = np.asarray([.4, -.5, 1.])
    light /= np.linalg.norm(light)
    global_index = 0
    for object_index, mesh in enumerate(capture['meshes']):
        vertices = np.asarray(mesh['vertices'], dtype=np.float64)
        for local_face, indices in enumerate(mesh['faces']):
            a, b, c = vertices[indices]
            edge_u, edge_v = b - a, c - a
            normal = np.cross(edge_u, edge_v)
            denominator = float(np.dot(normal, ray))
            if denominator == 0:
                global_index += 1
                continue
            depth = ((a - origins) @ normal) / denominator
            delta = origins + depth[:, None] * ray - a
            uu, uv, vv = float(edge_u @ edge_u), float(edge_u @ edge_v), float(edge_v @ edge_v)
            determinant = uu * vv - uv * uv
            require(determinant > 0, 'independent_ray_nondegenerate_source_triangle')
            pu, pv = delta @ edge_u, delta @ edge_v
            weight_u = (vv * pu - uv * pv) / determinant
            weight_v = (uu * pv - uv * pu) / determinant
            minimum = np.minimum(np.minimum(weight_u, weight_v), 1 - weight_u - weight_v)
            valid = (sample_inside_xy_frustum & (minimum >= -tolerance)
                     & (depth >= pose['near']) & (depth <= pose['far']))
            boundary = valid & (minimum <= tolerance)
            ambiguous |= boundary
            # Original order is retained for exact analytic ties. Approximate
            # ties are validated as an admissible set instead of guessed.
            closer = valid & (depth < best)
            equal = valid & np.isfinite(best) & (np.abs(depth - best) <= tolerance)
            ambiguous |= equal
            best[closer] = depth[closer]
            best_object[closer] = object_index
            best_triangle[closer] = global_index
            shade = .45 + .55 * abs(float(normal @ light)) / float(np.linalg.norm(normal))
            color = np.clip(np.asarray([180, 190, 205]) * shade, 0, 255).astype(np.uint8)
            best_rgb[closer] = color
            claimed = actual_triangles == global_index
            admissible_actual |= claimed & valid & (actual_objects == object_index) & (np.abs(actual_depth - depth) <= tolerance)
            global_index += 1
    predicted_foreground = np.isfinite(best)
    actual_foreground = actual_objects >= 0
    evidence.check(np.array_equal(predicted_foreground, actual_foreground), 'independent_ray_full_foreground_mask')
    evidence.check(np.all(admissible_actual[actual_foreground]), 'independent_ray_every_claimed_source_intersection')
    evidence.check(np.all(np.abs(actual_depth[actual_foreground] - best[actual_foreground]) <= tolerance),
                   'independent_ray_no_nearer_source_surface')
    certain = predicted_foreground & ~ambiguous
    evidence.check(np.array_equal(actual_objects[certain], best_object[certain])
                   and np.array_equal(actual_triangles[certain], best_triangle[certain]),
                   'independent_ray_unambiguous_closest_object_and_triangle')
    rgb = arrays['color'].reshape((-1, 3))
    evidence.check(np.array_equal(rgb[certain], best_rgb[certain]), 'independent_ray_unambiguous_lit_surface_RGB')
    return dict(method='inverse published camera world rays; world plane intersection and Gram barycentric membership',
                total_pixels=pixel_count, foreground_pixels=int(np.count_nonzero(predicted_foreground)),
                unambiguous_foreground_pixels=int(np.count_nonzero(certain)),
                triangle_edge_or_depth_tie_ambiguous_pixels=int(np.count_nonzero(ambiguous)),
                barycentric_allowance=tolerance, camera_depth_allowance_m=tolerance,
                exact_triangle_owner_claim_on_ambiguous_pixels=False,
                all_actual_foreground_pixels_checked_for_source_membership_and_no_nearer_surface=True)


def check_session(session, capture_path=None, *, eligible=None):
    session = Path(session).resolve()
    evidence = Evidence()
    evidence.file(__file__)
    initial_full = read(session / 'product_full/call_001/SERVICE_RESULT.json')
    capture, wire_steps = decode_current_capture(session, initial_full['binding'], evidence)
    if capture_path is not None:
        capture_document = json.loads(evidence.file(capture_path))
        exported_capture = capture_document.get('capture', capture_document)
        evidence.check(exported_capture == capture, 'export_matches_independently_decoded_original_capture')
    calls = [json.loads(line) for line in evidence.file(session / 'PUBLIC_REQUESTS.jsonl').splitlines() if line.strip()]
    evidence.check(len(calls) == 1, 'exactly_one_actual_public_observation_request')
    call = calls[0]
    request = json.loads(evidence.file(call['request_path'], call['request_sha256'], session))
    response = json.loads(evidence.file(call['response_path'], call['response_sha256'], session))
    evidence.check(request == call['request'] and response == call['response']
                   and json.loads(evidence.file(call['actual_TX_path'], call['actual_TX_sha256'], session)) == request
                   and json.loads(evidence.file(call['actual_RX_path'], call['actual_RX_sha256'], session)) == response,
                   'actual_public_stdio_request_reply_binding')
    arguments = request['params']['arguments']
    evidence.check(arguments['include_image'] is True and arguments['response_detail'] == 'full'
                   and arguments['query']['mode'] == 'active_observation'
                   and request['params']['name'] == 'human_eye_scene_observe', 'actual_full_image_entry')
    evidence.check(type(request['id']) is type(response['id']) and request['id'] == response['id']
                   and response['result']['isError'] is False and 'post_reply_binding_error' not in call,
                   'actual_success_response_delivered')
    if session.name == 'global':
        evidence.check(arguments['query'] == {'mode': 'active_observation'}, 'global_request_without_target')
    else:
        evidence.check(arguments['query'] == dict(mode='active_observation', objects=[capture['observation_target']['selector']]),
                       'explicit_local_selector_matches_actual_capture')
    entries = [json.loads(line) for line in evidence.file(session / 'product_full/INDEX.jsonl').splitlines() if line.strip()]
    evidence.check(len(entries) == 1 and entries[0] == call['producer_archive']
                   and call['producer_archive_index'] == entries[0]['index'] == 1, 'one_same_producer_archive')
    entry = entries[0]
    evidence.check(call['started_ns'] <= entry['started_ns'] <= entry['producer_returned_ns'] <= call['closed_ns'],
                   'same_producer_original_request_window')
    evidence.check(Path(entry['path']).resolve() == session / 'product_full/call_001/SERVICE_RESULT.json',
                   'same_producer_current_session_path')
    full = json.loads(evidence.file(entry['path'], entry['sha256'], session))
    blocks = response['result']['content']
    texts = [json.loads(block['text']) for block in blocks if block['type'] == 'text']
    evidence.check(len(texts) == 1, 'one_original_full_public_text')
    public = texts[0]
    evidence.check(public['facts'] == full['facts']
                   and public['binding'] == {key: value for key, value in full['binding'].items() if key != 'camera_specification'},
                   'full_public_facts_and_binding_unaltered')
    evidence.check(full['read_only'] is True and full['execution_authority'] is False, 'read_only_no_execution_authority')
    views = source_binding_checks(capture, full['binding'], evidence)
    regions, face_patch = partition_checks(full, capture, evidence)
    frames, observations = full['frames'], full['facts']['observations']
    names = [frame['view_name'] for frame in frames]
    evidence.check(len(names) == len(set(names)) <= 6 and set(names).issubset(ORDER)
                   and names == [row['view_name'] for row in observations], 'actual_unique_finite_rendered_views')
    images = [block for block in blocks if block['type'] == 'image']
    evidence.check(len(images) == len(frames) == len(public['frames']) == full['work']['raster_completed']
                   == full['work']['raster_attempts'], 'actual_image_and_raster_count')
    frame_reviews = []
    for index in range(len(frames)):
        frame, public_frame = frames[index], public['frames'][index]
        evidence.check(all(frame[key] == value for key, value in public_frame.items()), 'full_public_frame_metadata_exact')
        frame_reviews.append(frame_checks(frame, observations[index], full, capture, regions, face_patch,
                                         images[index], session, evidence))
    projections = []
    if eligible is not None:
        for row in eligible:
            meshes = [mesh for mesh in capture['meshes'] if mesh['name'] == row['object_name']]
            if not meshes:
                projections.append(dict(object_name=row['object_name'], retained=False))
                continue
            evidence.check(len(meshes) == 1, 'eligible_object_unique_in_actual_capture')
            mesh = meshes[0]
            source_faces = row['source_triangle_indices']
            faces = [mesh['faces'][index] for index in source_faces]
            projections.append(dict(object_name=row['object_name'], retained=True,
                source_triangle_indices=source_faces,
                views=[pixel_bbox_upper(mesh['vertices'], faces, pose) for pose in views]))
    return dict(schema='m4-global-local-saved-frame-check-v1', passed_checked_scope=True,
                author_association='Reviewer authored earlier product wiring and the present independent saved-byte checker.',
                session=str(session), current_capture=capture, source_wire_steps=wire_steps, checks=evidence.checks,
                check_count=len(evidence.checks), frames=frame_reviews, projection_upper_bounds=projections,
                rendered_views=names, unrendered_views=[name for name in ORDER if name not in names],
                scope='Saved delivery/array/source-index/scope consistency and actual-matrix pixel bounds. Geometric eligibility, exact occlusion and complete-witness entailment require the independent geometry oracle.',
                new_operations=dict(Blender=0, MCP=0, raster=0, model=0),
                input_pins=list(evidence.pins.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--capture', type=Path)
    parser.add_argument('--eligible', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    eligible_document = None if args.eligible is None else read(args.eligible)
    eligible = eligible_document
    if type(eligible_document) is dict:
        eligible = eligible_document['eligible']
    report = check_session(args.session, args.capture, eligible=eligible)
    if args.eligible is not None:
        report['input_pins'].append(dict(path=str(args.eligible.resolve()), sha256=sha(args.eligible),
                                         bytes=args.eligible.stat().st_size))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + '\n')
    print(json.dumps(dict(passed_checked_scope=True, check_count=report['check_count'], output=str(args.output))))


if __name__ == '__main__':
    main()

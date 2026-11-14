"""Independent frozen-axis and saved-buffer checks, with no rendering calls.

The reference computes a shared sparse contrast boundary once, then scans a
whole target mask separately for each patch. It does not import product
discovery, coverage, raster or pixel-count helpers.
"""

from fractions import Fraction
import hashlib
from io import BytesIO
import json
from pathlib import Path

import numpy as np


MAPPING_VERSION = 'active-patch-owner-v1'
COUNT_KEYS = ('visible_surface_pixels', 'contrasting_boundary_pixels')
LOCATION_KEYS = ('visible_pixel_bounds', 'visible_pixel_anchor')
FULL_KEYS = COUNT_KEYS + LOCATION_KEYS
ARRAY_KEYS = ('color', 'depth', 'owners', 'patch_owners', 'patch_mapping_version',
              'patch_mapping_identity', 'patch_roi_ids', 'face_patch_ids', 'face_patch_offsets')


def digest(value):
    raw = json.dumps(value, default=str, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _reference_boundary(color, patch_owners, region_count):
    """Build one independent sparse contrast boundary.

    Every horizontal or vertical pair must change patch ID and have Euclidean
    RGB distance at least 24. An endpoint belongs to the target patch and is
    counted once even when several qualifying neighbors touch it.
    """
    require(type(region_count) is int and region_count >= 0, 'reference_region_count')
    require(color.dtype == np.uint8 and color.shape == patch_owners.shape + (3,), 'reference_RGB_shape')
    require(patch_owners.dtype == np.int32 and patch_owners.ndim == 2, 'reference_patch_dtype')
    require(not np.any(patch_owners < -1) and not np.any(patch_owners >= region_count), 'reference_patch_range')
    boundary = np.zeros(patch_owners.shape, dtype=bool)
    height, width = patch_owners.shape
    for dy, dx in ((0, 1), (1, 0)):
        first = patch_owners[:height - dy, :width - dx]
        second = patch_owners[dy:, dx:]
        y, x = np.nonzero(first != second)
        delta = color[y, x].astype(np.int32) - color[y + dy, x + dx].astype(np.int32)
        contrasted = np.sum(delta * delta, axis=1) >= 24 ** 2
        y, x = y[contrasted], x[contrasted]
        boundary[y, x] = True
        boundary[y + dy, x + dx] = True
    return boundary


def reference_counts(color, patch_owners, region_count):
    boundary = _reference_boundary(color, patch_owners, region_count)
    surface = np.zeros(region_count, dtype=np.int64)
    boundary_counts = np.zeros(region_count, dtype=np.int64)
    for patch_index in range(region_count):
        target = patch_owners == patch_index
        surface[patch_index] = np.count_nonzero(target)
        boundary_counts[patch_index] = np.count_nonzero(target & boundary)
    return {'visible_surface_pixels': surface, 'contrasting_boundary_pixels': boundary_counts}


def reference_full(color, patch_owners, region_count):
    """Simple per-ROI scans with actual-pixel nearest-centre, row-major ties."""
    boundary = _reference_boundary(color, patch_owners, region_count)
    surface = np.zeros(region_count, dtype=np.int64)
    edges = np.zeros(region_count, dtype=np.int64)
    bounds, anchors = [], []
    for patch_index in range(region_count):
        target = patch_owners == patch_index
        y, x = np.nonzero(target)
        surface[patch_index] = len(x)
        edges[patch_index] = np.count_nonzero(target & boundary)
        if not len(x):
            bounds.append(None)
            anchors.append(None)
            continue
        left, top, right, bottom = int(x.min()), int(y.min()), int(x.max()), int(y.max())
        distance = (2 * x - left - right) ** 2 + (2 * y - top - bottom) ** 2
        nearest = int(np.argmin(distance))
        bounds.append([left, top, right, bottom])
        anchors.append([int(x[nearest]), int(y[nearest])])
    return {'visible_surface_pixels': surface, 'contrasting_boundary_pixels': edges,
            'visible_pixel_bounds': bounds, 'visible_pixel_anchor': anchors}


def historical_path(value):
    root = Path(__file__).resolve().parent
    relative = Path(value)
    require(not relative.is_absolute(), 'historical_reference_paths_must_be_task_relative')
    path = (root / relative).resolve()
    require(path.is_relative_to(root), 'historical_reference_path_outside_task')
    return path


def strict_equal(actual, expected):
    return (json.dumps(actual, sort_keys=True, allow_nan=False, separators=(',', ':'))
            == json.dumps(expected, sort_keys=True, allow_nan=False, separators=(',', ':')))


def independent_mapping(capture, expected, representation):
    """Bind the captured source faces to construction answers, never discovery."""
    require(representation in ('split', 'joined'), 'representation')
    require(expected['schema'] == 'patch-ownership-independent-axis-oracle-v1', 'expected_schema')
    require(capture['unit'] == 'm' and capture['coordinate_frame'] == 'world', 'capture_coordinates')
    meshes, source_maps = capture['meshes'], expected['source_maps']
    if representation == 'split':
        require(len(meshes) == len(source_maps), 'split_object_count')
        for mesh, source in zip(meshes, source_maps):
            require(mesh['name'] == source['name'], 'split_source_order')
            require(len(mesh['vertices']) == source['vertices'] and len(mesh['faces']) == source['triangles'],
                    'split_source_sizes')
    else:
        require(len(meshes) == 1 and meshes[0]['name'] == 'QA_Joined', 'joined_source')
        require(len(meshes[0]['vertices']) == sum(row['vertices'] for row in source_maps), 'joined_vertices')
        require(len(meshes[0]['faces']) == sum(row['triangles'] for row in source_maps), 'joined_faces')
    objects = []
    world_triangles = []
    for mesh in meshes:
        vertices = tuple(tuple(Fraction(value) for value in point) for point in mesh['vertices'])
        faces = tuple(tuple(face) for face in mesh['faces'])
        require(all(len(point) == 3 for point in vertices), 'source_point_dimensions')
        require(all(len(face) == 3 and all(type(i) is int and 0 <= i < len(vertices) for i in face)
                    for face in faces), 'source_triangle_indices')
        objects.append((vertices, faces))
        world_triangles.extend([[[str(value) for value in vertices[i]] for i in face] for face in faces])
    require(digest(world_triangles) == expected['draw_order_world_triangles_sha256'], 'frozen_world_triangle_order')
    patches = expected['regions']
    roi_ids = tuple(row['roi_id'] for row in patches)
    require(len(roi_ids) == expected['expected_patch_count'] and roi_ids == tuple(sorted(set(roi_ids))),
            'expected_unique_sorted_ROIs')
    face_ids = [np.full(len(faces), -1, dtype=np.int32) for _, faces in objects]
    object_indices = []
    source_indices = []
    for ordinal, patch in enumerate(patches):
        quad = tuple(tuple(Fraction(value) for value in point) for point in patch['quad'])
        require(patch['roi_id'] == 'roi_' + digest(quad)[:24], 'expected_canonical_ROI_hash')
        object_index = patch['split_object_index'] if representation == 'split' else 0
        indices = patch[representation + '_triangle_indices']
        vertices, faces = objects[object_index]
        axis, plane, sign = patch['axis'], Fraction(patch['plane']), patch['normal_sign']
        low = tuple(min(point[k] for point in quad) for k in range(3))
        high = tuple(max(point[k] for point in quad) for k in range(3))
        signed_area_twice = Fraction(0)
        u, v = (axis + 1) % 3, (axis + 2) % 3
        for face_index in indices:
            require(0 <= face_index < len(faces) and face_ids[object_index][face_index] == -1,
                    'expected_disjoint_source_faces')
            points = tuple(vertices[i] for i in faces[face_index])
            require(all(point[axis] == plane and all(low[k] <= point[k] <= high[k] for k in range(3))
                        for point in points), 'source_face_on_frozen_axis_patch')
            area = ((points[1][u] - points[0][u]) * (points[2][v] - points[0][v])
                    - (points[1][v] - points[0][v]) * (points[2][u] - points[0][u]))
            require(area * sign > 0, 'source_face_axis_winding')
            signed_area_twice += area
            face_ids[object_index][face_index] = ordinal
        require(signed_area_twice == 2 * Fraction(patch['normal'][axis]), 'source_patch_total_area')
        object_indices.append(object_index)
        source_indices.append(indices)
    supported = sum(int(np.count_nonzero(values >= 0)) for values in face_ids)
    unsupported = sum(int(np.count_nonzero(values == -1)) for values in face_ids)
    require(supported == expected['supported_triangles'] and unsupported == expected['unsupported_triangles'],
            'frozen_face_partition_counts')
    actual_unsupported = [(i, int(j)) for i, values in enumerate(face_ids) for j in np.flatnonzero(values == -1)]
    wanted = ([(expected['unsupported_split_object_index'], 0)] if representation == 'split'
              else [(0, expected['unsupported_joined_triangle_index'])])
    require(actual_unsupported == wanted, 'frozen_unsupported_face')
    identity = digest({'version': MAPPING_VERSION, 'roi_ids': roi_ids,
                       'ordered_geometry': objects, 'face_patch_ids': [values.tolist() for values in face_ids]})
    offsets = np.asarray([0] + [len(values) for values in face_ids], dtype=np.int64).cumsum()
    arrays = {'patch_mapping_version': np.asarray(MAPPING_VERSION),
              'patch_mapping_identity': np.asarray(identity), 'patch_roi_ids': np.asarray(roi_ids, dtype=str),
              'face_patch_ids': np.concatenate(face_ids), 'face_patch_offsets': offsets}
    return {'identity': identity, 'roi_ids': roi_ids, 'arrays': arrays,
            'object_indices': np.asarray(object_indices, dtype=np.int32), 'source_indices': source_indices,
            'objects': objects, 'supported_triangles': supported, 'unsupported_triangles': unsupported}


def verify_frame(capture, index, frame, feedback_rows, expected, representation, reference=None):
    """Return a receipt after strict independent checks, raising on mismatch.

    ``index`` is the evidence-only INDEX JSON sidecar. ``frame`` can be the
    full local descriptor or its public projection. Missing public pose is
    recovered from the bound sidecar cameras, never an oracle camera answer.
    """
    from PIL import Image

    mapping = independent_mapping(capture, expected, representation)
    capture_bytes = (json.dumps(capture, ensure_ascii=True, allow_nan=False, sort_keys=True,
                               separators=(',', ':')) + '\n').encode('ascii')
    require(index['actual_capture_sha256'] == hashlib.sha256(capture_bytes).hexdigest(), 'index_capture_binding')
    require(index['capture_revision'] == capture['revision'] and index['host_identity'] == capture['host_identity'],
            'index_host_binding')
    require(frame['scene_identity'] == index['scene_identity'] and frame['candidate_identity'] == index['candidate_identity'],
            'frame_index_binding')
    index_regions = index['regions']
    require([row['roi_id'] for row in index_regions] == list(mapping['roi_ids']), 'index_ROI_order')
    for ordinal, (actual, patch) in enumerate(zip(index_regions, expected['regions'])):
        require(actual['object_index'] == int(mapping['object_indices'][ordinal]), 'index_object_mapping')
        require(actual['object_name'] == capture['meshes'][actual['object_index']]['name'], 'index_object_name')
        require(actual['triangle_indices'] == mapping['source_indices'][ordinal], 'index_all_source_triangles')
        require(actual['vertices'] == patch['quad'] and actual['normal'] == patch['normal'], 'index_frozen_quad_front')
    poses = [pose for pose in index['cameras']['views'] if pose['name'] == frame['view_name']]
    require(len(poses) == 1, 'single_bound_camera')
    pose = poses[0]
    require(pose['size_px'] == [512, 512], 'frozen_512_frame')
    if 'pose' in frame:
        require(frame['pose'] == pose, 'frame_complete_pose')
    raw_npz = Path(frame['arrays_path']).read_bytes()
    require(hashlib.sha256(raw_npz).hexdigest() == frame['arrays_sha256'], 'NPZ_hash')
    require(len(raw_npz) == frame['compressed_array_file_bytes'], 'NPZ_bytes')
    with np.load(BytesIO(raw_npz), allow_pickle=False) as stored:
        require(set(stored.files) == set(ARRAY_KEYS), 'exact_saved_array_keys')
        arrays = {name: stored[name].copy() for name in ARRAY_KEYS}
    color, depth, owners, patches = (arrays[name] for name in ('color', 'depth', 'owners', 'patch_owners'))
    for name, dtype, shape in [('color', np.uint8, (512, 512, 3)), ('depth', np.float64, (512, 512)),
                               ('owners', np.int32, (512, 512)), ('patch_owners', np.int32, (512, 512))]:
        require(arrays[name].dtype == dtype and arrays[name].shape == shape, 'saved_' + name + '_dtype_shape')
    for name, wanted in mapping['arrays'].items():
        require(arrays[name].dtype == wanted.dtype and np.array_equal(arrays[name], wanted), 'saved_' + name)
    require(frame['patch_mapping_version'] == MAPPING_VERSION
            and frame['patch_mapping_identity'] == mapping['identity']
            and frame['patch_roi_ids'] == list(mapping['roi_ids']), 'frame_patch_mapping_metadata')
    require(not np.any(owners < -1) and not np.any(owners >= len(capture['meshes'])), 'owner_range')
    require(not np.any(patches < -1) and not np.any(patches >= len(mapping['roi_ids'])), 'patch_owner_range')
    background, assigned = owners == -1, patches >= 0
    require(np.all(np.isposinf(depth[background]))
            and np.all(np.isfinite(depth[~background]) & (depth[~background] > 0)), 'depth_owner_consistency')
    require(np.all(patches[background] == -1)
            and np.all(mapping['object_indices'][patches[assigned]] == owners[assigned]), 'patch_object_owner_consistency')
    payload = sum(values.nbytes for values in arrays.values())
    metadata_bytes = sum(values.nbytes for name, values in arrays.items() if name not in ('color', 'depth', 'owners', 'patch_owners'))
    require(frame['array_payload_bytes'] == payload and frame['patch_owner_array_bytes'] == patches.nbytes
            and frame['patch_mapping_array_bytes'] == metadata_bytes, 'array_payload_accounting')
    array_metadata = {}
    for name, values in arrays.items():
        array_metadata[name] = {'dtype': str(values.dtype), 'shape': list(values.shape), 'nbytes': int(values.nbytes),
                                'sha256': hashlib.sha256(values.tobytes(order='C')).hexdigest()}
    if 'arrays' in frame:
        require(frame['arrays'] == array_metadata, 'complete_saved_array_metadata')
    png = Path(frame['image_path']).read_bytes()
    require(hashlib.sha256(png).hexdigest() == frame['image_sha256'] and len(png) == frame['PNG_bytes'], 'PNG_hash_bytes')
    with Image.open(BytesIO(png)) as image:
        require(image.format == 'PNG' and image.mode == 'RGB' and image.size == (512, 512), 'PNG_type_dimensions')
        require(np.array_equal(np.asarray(image), color), 'PNG_equals_saved_RGB')
    require(len(feedback_rows) == len(mapping['roi_ids']), 'feedback_row_denominator')
    rows = {row['roi_id']: row for row in feedback_rows}
    require(len(rows) == len(feedback_rows) and set(rows) == set(mapping['roi_ids']), 'feedback_unique_all_ROIs')
    located = reference is not None or any('visible_pixel_anchor' in row for row in feedback_rows)
    counts = (reference_full if located else reference_counts)(color, patches, len(mapping['roi_ids']))
    direction = [Fraction(float(value)) for value in pose['target_to_eye_unit']]
    actual = {}
    for ordinal, patch in enumerate(expected['regions']):
        identity = patch['roi_id']
        front = sum(Fraction(value) * axis for value, axis in zip(patch['normal'], direction)) > 0
        surface, boundary = (int(counts[key][ordinal]) for key in COUNT_KEYS)
        wanted = {'object_index': int(mapping['object_indices'][ordinal]), 'view': frame['view_name'],
                  'front_facing': front, 'visible_surface_pixels': surface,
                  'contrasting_boundary_pixels': boundary, 'readable': front and surface >= 16 and boundary >= 4,
                  'minimum_surface_pixels': 16, 'minimum_boundary_pixels': 4, 'minimum_rgb_boundary_contrast': 24}
        if located:
            wanted.update({key: counts[key][ordinal] for key in LOCATION_KEYS})
        for name, value in wanted.items():
            require(type(rows[identity].get(name)) is type(value) and strict_equal(rows[identity][name], value),
                    'feedback_' + identity + '_' + name)
        if 'triangle_indices' in rows[identity]:
            require(rows[identity]['triangle_indices'] == mapping['source_indices'][ordinal], 'feedback_source_triangles')
        actual[identity] = wanted
    historical = None
    if reference is not None:
        require(reference['schema'] == 'region-anchors-independent-reference-v1'
                and reference['reference_path_base'] == 'task_namespace', 'historical_reference_schema')
        matches = [row for row in reference['pixel_frames'] if row['view_name'] == frame['view_name']]
        require(len(matches) == 1, 'single_historical_reference_view')
        entry = matches[0]
        old = entry['frame']
        require(all(entry[key] == old[key] for key in ('arrays_path', 'image_path', 'arrays_sha256', 'image_sha256')),
                'historical_flat_nested_bindings')
        require(old['scene_identity'] == frame['scene_identity'] and old['candidate_identity'] == frame['candidate_identity']
                and old['patch_mapping_identity'] == frame['patch_mapping_identity']
                and old['patch_roi_ids'] == frame['patch_roi_ids'], 'historical_geometry_camera_mapping_binding')
        old_raw = historical_path(old['arrays_path']).read_bytes()
        require(hashlib.sha256(old_raw).hexdigest() == old['arrays_sha256'], 'historical_NPZ_hash')
        with np.load(BytesIO(old_raw), allow_pickle=False) as previous:
            same_arrays = {key: arrays[key].dtype == previous[key].dtype and np.array_equal(arrays[key], previous[key])
                           for key in ('color', 'depth', 'owners', 'patch_owners')}
        require(all(same_arrays.values()), 'historical_color_depth_owner_changed')
        old_png = historical_path(old['image_path']).read_bytes()
        require(hashlib.sha256(old_png).hexdigest() == old['image_sha256'] and old_png == png, 'historical_PNG_changed')
        reference_rows = {row['roi_id']: row for row in entry['rows']}
        require(len(reference_rows) == len(entry['rows']) == 138 and set(reference_rows) == set(rows),
                'historical_all_138_location_rows')
        for identity, wanted in reference_rows.items():
            for key, value in wanted.items():
                actual_value = identity if key == 'roi_id' else actual[identity][key]
                require(strict_equal(actual_value, value), 'historical_reference_' + identity + '_' + key)
        historical = {'passed': True, 'reference_rows_checked': len(reference_rows),
                      'old_arrays_sha256': old['arrays_sha256'], 'old_image_sha256': old['image_sha256'],
                      'same_arrays': same_arrays, 'PNG_bytes_identical': True,
                      'reference_source_inputs': reference['source_inputs']}
    checkpoints = {}
    for name, checkpoint in expected['checkpoints'].items():
        if not (name.startswith(frame['view_name'] + '_') or name == 'all_six_back_facing'):
            continue
        row = actual[checkpoint['roi_id']]
        for key in ('front_facing', 'readable'):
            if key in checkpoint:
                require(row[key] is checkpoint[key], 'checkpoint_' + name + '_' + key)
        if name == 'all_six_back_facing':
            require(row['front_facing'] is False, 'checkpoint_all_six_back_facing_front')
        if 'surface_pixels' in checkpoint:
            count = row['visible_surface_pixels']
            require(count > 0 if checkpoint['surface_pixels'] == 'positive' else count == checkpoint['surface_pixels'],
                    'checkpoint_' + name + '_surface')
        checkpoints[name] = {'passed': True, 'roi_id': checkpoint['roi_id'], **row}
    joined_same_object = None
    if representation == 'joined' and frame['view_name'] == 'SCENE':
        rear = expected['checkpoints']['SCENE_hidden_same_object_rear']['roi_id']
        require(np.count_nonzero(owners == 0) > 0 and actual[rear]['visible_surface_pixels'] == 0,
                'joined_object_pixels_do_not_credit_hidden_rear')
        joined_same_object = True
    return {'schema': 'patch-ownership-independent-pixel-receipt-v1', 'passed': True,
            'representation': representation, 'view_name': frame['view_name'],
            'actual_capture_sha256': index['actual_capture_sha256'], 'patch_mapping_identity': mapping['identity'],
            'ROI_rows_checked': len(rows), 'front_count': sum(row['front_facing'] for row in actual.values()),
            'readable_count': sum(row['readable'] for row in actual.values()),
            'counts': {key: counts[key].tolist() for key in COUNT_KEYS}, 'array_metadata': array_metadata,
            'locations': {key: counts[key] for key in LOCATION_KEYS} if located else None,
            'locations_checked': len(rows) if located else 0, 'historical_reference': historical,
            'PNG_bytes': len(png), 'NPZ_bytes': len(raw_npz), 'array_payload_bytes': int(payload),
            'supported_triangles': mapping['supported_triangles'], 'unsupported_triangles': mapping['unsupported_triangles'],
            'checkpoints': checkpoints, 'joined_same_object_hidden_rear_checked': joined_same_object,
            'reference_count_calls': 1, 'new_raster_calls': 0,
            'scope': 'Frozen axis construction and actual saved buffers; source-owner reviewer implementation.'}

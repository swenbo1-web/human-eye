"""Source-bound object and saved-buffer normalization for target A/B evidence.

No product modules are imported.  The caller supplies frozen asset geometry
and current-slot source proof.  Observation/fact-schema adaptation is explicit
and remains outside these low-level identity and buffer primitives.
"""

from fractions import Fraction
import ast
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import zlib


VIEW_ORDER = ('SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK')
DIRECTIONS = ((4, -4, 3), (0, 0, 1), (-1, 0, 1), (1, 0, 1), (0, -1, 1), (0, 1, 1))
SERVICE_SOURCE_FIELDS = {'runtime_source_sha256', 'source_status', 'disk_status', 'source_check_scope'}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, default=str, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def independent_geometry_identity(capture):
    """Reconstruct the serialized geometry commitment from actual raw arrays."""
    keys = []
    for mesh in capture['meshes']:
        vertices = tuple(tuple(Fraction(value) for value in point) for point in mesh['vertices'])
        triangles = []
        for face in _faces(mesh['faces'], len(vertices)):
            points = tuple(vertices[index] for index in face)
            triangles.append(min(points[index:] + points[:index] for index in range(3)))
        keys.append((tuple(sorted(vertices)), tuple(sorted(triangles))))
    return fingerprint(tuple(sorted(keys)))


def reconstruct_target_binding(capture):
    """Rebuild hashes from the actual capture without executing product code."""
    metadata = capture['observation_target']
    identity = capture['host_identity']
    cameras = metadata['camera_plan']
    objects = [{'object_index': index, 'host_id': mesh['object_id'],
                'object_name': mesh['name'], 'instance_id': identity['object_instances'][mesh['object_id']]}
               for index, mesh in enumerate(capture['meshes'])]
    target = {key: copy.deepcopy(metadata[key]) for key in (
        'schema', 'selector', 'target_object_id', 'target_instance_id', 'target_object_index',
        'full_scene_identity', 'retained_object_ids', 'excluded_object_ids', 'directory_sha256', 'source_frame')}
    target['camera_plan_sha256'] = fingerprint(cameras)
    binding = {
        'schema': 'active-observation-host-source-v1', 'scene_revision': capture['revision'],
        'document_epoch': identity['document_epoch'], 'capture_scope': identity['capture_scope'],
        'unit': capture['unit'], 'coordinate_frame': capture['coordinate_frame'],
        'source': capture['source'], 'capture_state': copy.deepcopy(capture.get('capture_state')),
        'objects': objects,
        'camera_policy': {'order': list(VIEW_ORDER),
                          'directions': {name: list(direction) for name, direction in zip(VIEW_ORDER, DIRECTIONS)},
                          'size_px': [512, 512], 'margin_per_side': .05,
                          'projection': 'orthographic', 'scope': 'target_fitted_viewport_full_scene_depth'},
        'observation_target': target,
    }
    binding['source_binding_sha256'] = fingerprint(binding)
    binding['camera_specification'] = copy.deepcopy(cameras)
    binding['geometry_identity'] = independent_geometry_identity(capture)
    binding['camera_identity'] = fingerprint([
        {key: pose[key] for key in ('name', 'direction_rational', 'view_matrix', 'projection_matrix', 'size_px')}
        for pose in cameras['views']])
    binding['binding_sha256'] = fingerprint(binding)
    return binding


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sha(value, field):
    if (type(value) is not str or len(value) != 64
            or any(character not in '0123456789abcdef' for character in value)):
        raise ValueError(field + ' requires a SHA-256 string')
    return value


def validate_source_proof(proof):
    """Validate explicit external pins and actual current-slot runtime identity."""
    expected = _sha(proof['expected_source_sha256'], 'expected source')
    actual = proof['actual_runtime_identity']
    if (actual.get('source_kind') != 'installed_distribution'
            or actual.get('source_sha256') != expected):
        raise ValueError('current-slot installed source differs from frozen arm')
    host_sha = _sha(proof['expected_host_source_sha256'], 'expected host')
    if proof['actual_loaded_host_sha256'] != host_sha:
        raise ValueError('current-slot loaded host differs from frozen arm')
    material = proof['material_pins']
    if type(material) is not list or not material:
        raise ValueError('external saved-evidence pins are required')
    seen = set()
    verified = []
    for row in material:
        identity = (row['path'], row.get('wire_request'))
        if identity in seen:
            raise ValueError('duplicate saved-evidence pin')
        seen.add(identity)
        expected_sha = _sha(row['sha256'], 'saved evidence')
        if 'wire_request' in row:
            path = Path(row['wire_request']).resolve()
            request_blob = path.read_bytes()
            request = json.loads(request_blob)
            code = request['params']['code']
            matches = []
            for node in ast.walk(ast.parse(code)):
                if not isinstance(node, ast.Constant) or type(node.value) is not str:
                    continue
                try:
                    decoded = zlib.decompress(base64.b64decode(node.value, validate=True))
                except (ValueError, zlib.error):
                    continue
                if hashlib.sha256(decoded).hexdigest() == expected_sha:
                    matches.append(decoded)
            if len(matches) != 1 or len(matches[0]) != row['bytes']:
                raise ValueError('actual source bytes are absent or ambiguous in the recorded bootstrap')
            verified.append({'path': row['path'], 'source_sha256': expected_sha,
                             'wire_request': str(path),
                             'wire_sha256': hashlib.sha256(request_blob).hexdigest()})
        else:
            path = Path(row['path']).resolve()
            if file_sha256(path) != expected_sha:
                raise ValueError('saved-evidence bytes changed')
            verified.append({'path': str(path), 'sha256': expected_sha})
    return {'source_sha256': expected, 'host_source_sha256': host_sha,
            'verified_material': verified}


def _vertex_bytes(vertices):
    if type(vertices) is not list or not vertices:
        raise ValueError('complete world vertex arrays required')
    result = bytearray()
    for point in vertices:
        if type(point) is not list or len(point) != 3:
            raise ValueError('three world coordinates required')
        for value in point:
            if type(value) not in (int, float) or not math.isfinite(float(value)):
                raise ValueError('finite world coordinates required')
            result.extend(struct.pack('!d', float(value)))
    return bytes(result)


def _faces(faces, vertex_count):
    if type(faces) is not list or not faces:
        raise ValueError('complete local source triangles required')
    for face in faces:
        if (type(face) is not list or len(face) != 3
                or any(type(index) is not int or not 0 <= index < vertex_count for index in face)):
            raise ValueError('local source triangle index is invalid')
    return faces


def validate_object_mapping(capture, binding, asset_manifest, source_proof):
    """Check this slot before constructing a stable asset/object/face mapping."""
    source = validate_source_proof(source_proof)
    if capture.get('unit') != 'm' or capture.get('coordinate_frame') != 'world':
        raise ValueError('world metre capture required')
    identity = capture['host_identity']
    epoch = _sha(identity['document_epoch'], 'document epoch')
    if binding['document_epoch'] != epoch:
        raise ValueError('result is bound to a different current document')
    if binding['scene_revision'] != capture['revision']:
        raise ValueError('result is bound to a different current capture')
    if binding.get('capture_state') != capture.get('capture_state'):
        raise ValueError('result capture token differs from actual capture')
    binding_sha = _sha(binding['binding_sha256'], 'current result binding')
    binding_core = {key: value for key, value in binding.items()
                    if key != 'binding_sha256' and key not in SERVICE_SOURCE_FIELDS}
    actual_binding_sha = fingerprint(binding_core)
    if actual_binding_sha != binding_sha:
        raise ValueError('current result binding digest differs')
    instances = identity['object_instances']
    meshes = capture['meshes']
    if set(instances) != {mesh['object_id'] for mesh in meshes}:
        raise ValueError('current capture object-instance coverage differs')
    if (any(type(value) is not str or not value for value in instances.values())
            or len(set(instances.values())) != len(instances)):
        raise ValueError('current runtime object instances must be unique')
    assets = asset_manifest['objects']
    _sha(asset_manifest['asset_sha256'], 'asset')
    if ([row['source_order'] for row in assets] != list(range(len(assets)))
            or len({row['asset_key'] for row in assets}) != len(assets)
            or len({row['object_id'] for row in assets}) != len(assets)):
        raise ValueError('frozen asset objects require unique original-order keys')
    by_host_id = {row['object_id']: row for row in assets}
    binding_objects = binding['objects']
    if len(meshes) != len(binding_objects):
        raise ValueError('current binding and actual capture object count differ')
    asset_offsets = [0]
    for asset in assets:
        _vertex_bytes(asset['vertices_world'])
        _faces(asset['triangles'], len(asset['vertices_world']))
        asset_offsets.append(asset_offsets[-1] + len(asset['triangles']))
    mappings = []
    previous_order = -1
    current_offset = 0
    for index, (mesh, row) in enumerate(zip(meshes, binding_objects)):
        host_id = mesh['object_id']
        if host_id not in by_host_id:
            raise ValueError('capture contains an object outside the frozen asset')
        asset = by_host_id[host_id]
        if (row['object_index'] != index or row['host_id'] != host_id
                or row['instance_id'] != instances[host_id]
                or row['object_name'] != mesh['name'] or mesh['name'] != asset['object_name']):
            raise ValueError('current runtime object binding differs from captured object')
        if asset['source_order'] <= previous_order:
            raise ValueError('retained objects changed original asset order')
        previous_order = asset['source_order']
        if (_vertex_bytes(mesh['vertices']) != _vertex_bytes(asset['vertices_world'])
                or _faces(mesh['faces'], len(mesh['vertices'])) != asset['triangles']):
            raise ValueError('actual world geometry or local source face order differs from frozen asset')
        face_count = len(mesh['faces'])
        mappings.append({'object_index': index, 'host_id': host_id,
                         'instance_id': instances[host_id], 'asset_key': asset['asset_key'],
                         'asset_order': asset['source_order'], 'object_name': mesh['name'],
                         'current_face_offset': current_offset, 'face_count': face_count,
                         'asset_face_offset': asset_offsets[asset['source_order']]})
        current_offset += face_count
    targets = [row for row in mappings if row['asset_key'] == asset_manifest['target_asset_key']]
    if len(targets) != 1:
        raise ValueError('current capture must include the frozen target exactly once')
    metadata = capture['observation_target']
    target = targets[0]
    full_identity = metadata['full_scene_identity']
    directory = metadata['scene_directory']
    full_instances = full_identity['object_instances']
    if (capture.get('capture_scope') != 'target_observation_meshes'
            or identity.get('capture_scope') != 'target_observation_meshes'
            or metadata['target_object_id'] != target['host_id']
            or metadata['target_instance_id'] != target['instance_id']
            or metadata['target_object_index'] != target['object_index']
            or full_identity['document_epoch'] != epoch
            or set(full_instances) != set(by_host_id)
            or any(type(value) is not str or not value for value in full_instances.values())
            or len(set(full_instances.values())) != len(full_instances)
            or [row['object_id'] for row in directory] != [row['object_id'] for row in assets]
            or metadata['retained_object_ids'] != [row['host_id'] for row in mappings]
            or len(set(metadata['excluded_object_ids'])) != len(metadata['excluded_object_ids'])
            or set(metadata['excluded_object_ids']) != set(by_host_id) - {row['host_id'] for row in mappings}):
        raise ValueError('target scope and full frozen scene identity differ')
    if hashlib.sha256(json.dumps(directory, sort_keys=True, separators=(',', ':'),
                                 ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest() != metadata['directory_sha256']:
        raise ValueError('actual full-scene directory commitment differs')
    for row in directory:
        asset = by_host_id[row['object_id']]
        if (row['instance_id'] != full_identity['object_instances'][row['object_id']]
                or row['name'] != asset['object_name']):
            raise ValueError('actual directory object incarnation differs')
    selector = metadata['selector']
    if selector not in ({'id': target['host_id']}, {'name': target['object_name']}):
        raise ValueError('actual selector differs from the frozen target')
    if metadata['source_frame'] != asset_manifest['source_frame']:
        raise ValueError('actual saved frame or unit differs from frozen asset')
    reconstructed = reconstruct_target_binding(capture)
    if binding_core != {key: value for key, value in reconstructed.items() if key != 'binding_sha256'}:
        raise ValueError('actual target binding differs from independently reconstructed capture commitment')
    return {'schema': 'target-slot-asset-mapping-v1', 'source': source,
            'document_epoch': epoch, 'asset_sha256': asset_manifest['asset_sha256'],
            'target_asset_key': asset_manifest['target_asset_key'], 'objects': mappings,
            'total_current_triangles': current_offset, 'total_asset_triangles': asset_offsets[-1],
            'source_revision': capture['revision'], 'host_binding_sha256': binding_sha,
            'geometry_identity': binding['geometry_identity'],
            'camera_identity': binding['camera_identity'],
            'camera_specification': binding['camera_specification']}


def normalize_saved_buffers(buffers, mapping):
    """Normalize already loaded arrays after current-slot source validation."""
    import numpy as np

    color, depth, owners, triangles = [np.asarray(buffers[key])
                                      for key in ('color', 'depth', 'owners', 'triangle_ids')]
    if (color.shape != (512, 512, 3) or color.dtype != np.uint8
            or depth.shape != (512, 512) or depth.dtype != np.float64
            or owners.shape != depth.shape or owners.dtype != np.int32
            or triangles.shape != depth.shape or triangles.dtype != np.int32):
        raise ValueError('actual RGB/depth/object/triangle buffers have an invalid shape or dtype')
    objects = mapping['objects']
    background = owners == -1
    foreground = ~background
    if (np.any(owners < -1) or np.any(owners >= len(objects))
            or np.any(triangles[background] != -1)
            or np.any(~np.isposinf(depth[background]))
            or np.any(~np.isfinite(depth[foreground])) or np.any(depth[foreground] <= 0)):
        raise ValueError('actual foreground/background evidence is inconsistent')
    normalized_owner = np.full(owners.shape, -1, dtype=np.int32)
    normalized_triangle = np.full(triangles.shape, -1, dtype=np.int64)
    for row in objects:
        pixels = owners == row['object_index']
        local = triangles[pixels].astype(np.int64) - row['current_face_offset']
        if np.any(local < 0) or np.any(local >= row['face_count']):
            raise ValueError('triangle winner is outside its actual owning object')
        normalized_owner[pixels] = row['asset_order']
        normalized_triangle[pixels] = row['asset_face_offset'] + local
    return {'color': color, 'depth': depth, 'owners': normalized_owner,
            'triangle_ids': normalized_triangle}


def compare_normalized_buffers(left, right):
    import numpy as np

    result = {}
    for key in ('color', 'depth', 'owners', 'triangle_ids'):
        a, b = left[key], right[key]
        different = a != b
        positions = np.argwhere(different)
        result[key] = {'equal': not len(positions), 'different_elements': int(np.count_nonzero(different)),
                       'first_different_index': positions[0].tolist() if len(positions) else None}
    return {'equal': all(row['equal'] for row in result.values()), 'arrays': result,
            'comparison': 'exact element equality, with preserved positive-infinity background depth'}


def source_face_indices(ranges, face_count):
    """Validate complete direct source ranges without geometric reverse lookup."""
    if type(ranges) is not list or not ranges:
        raise ValueError('direct source ranges must be a nonempty list')
    indices = []
    previous_end = -2
    for row in ranges:
        if (type(row) is not list or len(row) != 2 or any(type(value) is not int for value in row)
                or not 0 <= row[0] <= row[1] < face_count or row[0] <= previous_end + 1):
            raise ValueError('source ranges require canonical sorted inclusive intervals')
        indices.extend(range(row[0], row[1] + 1))
        previous_end = row[1]
    return indices


def normalized_scalar(value):
    """Keep geometry numbers lossless across integer/float/rational spellings."""
    if type(value) is bool:
        raise ValueError('boolean is not a geometric scalar')
    if type(value) not in (int, float, str):
        raise ValueError('unsupported geometric scalar')
    if type(value) is float and not math.isfinite(value):
        raise ValueError('finite geometric scalar required')
    return str(Fraction(value))


def table(value):
    if value is None:
        return []
    columns = value['columns']
    if (type(columns) is not list or len(set(columns)) != len(columns)
            or any(type(row) is not list or len(row) != len(columns) for row in value['rows'])):
        raise ValueError('actual public table has malformed or duplicate columns')
    return [dict(zip(columns, row)) for row in value['rows']]


def validate_public_binding(public, binding, mapping):
    expected = {key: copy.deepcopy(value) for key, value in binding.items()
                if key not in ('schema', 'objects', 'camera_policy', 'camera_specification')
                and key not in SERVICE_SOURCE_FIELDS}
    target = expected['observation_target']
    compact = {key: target[key] for key in (
        'schema', 'selector', 'target_object_id', 'target_instance_id', 'target_object_index',
        'camera_plan_sha256', 'directory_sha256', 'source_frame')}
    compact['full_scene_identity_sha256'] = fingerprint(target['full_scene_identity'])
    expected['observation_target'] = compact
    if type(expected.get('capture_state')) is dict:
        expected['capture_state'].pop('selection_key')
    expected.update(runtime_source_sha256=mapping['source']['source_sha256'],
                    source_status='loaded_generation', disk_status='disk_not_checked',
                    source_check_scope='bound_generation_identity')
    if public['binding'] != expected:
        raise ValueError('actual brief binding differs from reconstructed current-slot source')
    expected_objects = [{key: row[key] for key in ('object_index', 'host_id', 'instance_id', 'object_name')}
                        for row in mapping['objects']]
    if table(public['objects']) != expected_objects:
        raise ValueError('actual brief objects differ from current-slot source binding')


def validate_region_geometry(region, indices, target_mesh):
    """Check claimed source faces against the explicitly delivered rectangle."""
    vectors = {name: tuple(Fraction(value) for value in region[name]) for name in
               ('center_world_m', 'half_edge_u_world_m', 'half_edge_v_world_m', 'front_direction_world')}
    center, u, v, front = [vectors[name] for name in
                           ('center_world_m', 'half_edge_u_world_m', 'half_edge_v_world_m', 'front_direction_world')]
    dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    u2, v2 = dot(u, u), dot(v, v)
    normal = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
    if (len(center) != 3 or u2 <= 0 or v2 <= 0 or dot(u, v) != 0
            or max(abs(value) for value in front) != 1
            or front != tuple(value / max(abs(item) for item in normal) for value in normal)):
        raise ValueError('actual public rectangle has an invalid directed frame')
    area = Fraction(0)
    for index in indices:
        points = []
        for vertex_index in target_mesh['faces'][index]:
            delta = tuple(Fraction(value) - offset
                          for value, offset in zip(target_mesh['vertices'][vertex_index], center))
            if dot(delta, normal) != 0:
                raise ValueError('declared source face lies outside the delivered rectangle plane')
            point = (dot(delta, u) / u2, dot(delta, v) / v2)
            if any(abs(value) > 1 for value in point):
                raise ValueError('declared source face lies outside the delivered rectangle')
            points.append(point)
        a, b, c = points
        oriented = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        if oriented <= 0:
            raise ValueError('declared source face has inconsistent rectangle winding')
        area += oriented / 2
    if area != 4:
        raise ValueError('declared source faces do not cover the delivered rectangular area')


def normalize_public_target(public, capture, binding, mapping, classifications, validated_frames):
    """Preserve complete brief facts after validating current source and scope.

    ``classifications`` must come from the actual observe audit event.  Array
    records come from ``saved_frame_arrays`` for this slot.  Missing material
    raises a validation error and cannot become a quality pass.
    """
    if (public.get('schema') != 'active-observation-brief-v5' or public.get('index_base') != 0
            or public.get('read_only') is not True or public.get('execution_authority') is not False):
        raise ValueError('actual target result must retain the accepted brief-v5 contract')
    validate_public_binding(public, binding, mapping)
    targets = [row for row in mapping['objects'] if row['asset_key'] == mapping['target_asset_key']]
    target = targets[0]
    target_index = target['object_index']
    regions = table(public.get('regions'))
    region_ids = [row['roi_id'] for row in regions]
    if len(set(region_ids)) != len(region_ids):
        raise ValueError('actual target regions are duplicated')
    supported = set()
    normalized_regions = []
    for region in regions:
        if region['object_index'] != target_index:
            raise ValueError('non-target region entered the target coverage denominator')
        indices = source_face_indices(region['source_triangle_index_ranges'], target['face_count'])
        if region['triangle_count'] != len(indices) or supported.intersection(indices):
            raise ValueError('target direct source faces have a wrong count or overlap')
        validate_region_geometry(region, indices, capture['meshes'][target_index])
        supported.update(indices)
        row = copy.deepcopy(region)
        row['object_index'] = target['asset_key']
        for key in ('center_world_m', 'half_edge_u_world_m', 'half_edge_v_world_m', 'front_direction_world'):
            row[key] = [normalized_scalar(value) for value in row[key]]
        normalized_regions.append(row)
    if regions and public.get('source_triangle_index_ranges_semantics') != (
            'zero_based_object_local_inclusive; object_index_in_objects; scoped_to_this_binding'):
        raise ValueError('actual source-face range meaning differs')

    scope = public['scope']
    support = scope['patch_support']
    support_rows = table(support['object_support'])
    if (support['schema'] != 'active-patch-support-v2'
            or support['triangle_index_scope'] != 'zero-based source triangles within each object'
            or support['all_triangles_participate_in_occlusion'] is not True
            or scope['capture_object_count'] != len(mapping['objects'])
            or scope['supported_roi_object_count'] != int(bool(regions))
            or scope['all_objects_participate_in_occlusion'] is not True
            or len(support_rows) != len(mapping['objects'])):
        raise ValueError('actual target scope does not match retained objects')
    for row, source in zip(support_rows, mapping['objects']):
        if row['object_index'] != source['object_index'] or row['source_triangle_count'] != source['face_count']:
            raise ValueError('actual source-face denominator differs from retained mesh')
        if source['object_index'] != target_index and (
                row['supported_triangle_count'] != 0 or row['unsupported_triangle_count'] != 0
                or row['support_status'] != 'occluder_only'):
            raise ValueError('an occluder was mislabeled as an unsupported target')
    rejected = set()
    components = table(support.get('unsupported_components'))
    for component in components:
        if component['object_index'] != target_index or component['status'] != 'unknown' or not component['reason']:
            raise ValueError('actual unsupported component does not belong to the target')
        indices = source_face_indices(component['triangle_index_ranges'], target['face_count'])
        if component['triangle_count'] != len(indices) or rejected.intersection(indices):
            raise ValueError('actual unsupported source faces have a wrong count or overlap')
        rejected.update(indices)
    target_support = support_rows[target_index]
    expected_status = ('unsupported' if not supported else 'partially_supported' if rejected else 'fully_supported')
    if (supported.intersection(rejected) or supported | rejected != set(range(target['face_count']))
            or target_support['supported_triangle_count'] != len(supported)
            or target_support['unsupported_triangle_count'] != len(rejected)
            or target_support['support_status'] != expected_status):
        raise ValueError('actual target supported/unsupported partition is incomplete')
    observation_scope = scope['observation_scope']
    if observation_scope != {
            'kind': 'target', 'target_object_index': target_index, 'target_object_count': 1,
            'occluder_only_object_count': len(mapping['objects']) - 1,
            'full_scene_object_count': len(binding['observation_target']['full_scene_identity']['object_instances']),
            'excluded_object_count': len(binding['observation_target']['excluded_object_ids'])}:
        raise ValueError('actual observation scope counters differ')
    without_regions = table(scope.get('objects_without_supported_roi'))
    if without_regions != ([] if regions else [{'object_index': target_index, 'status': 'unknown'}]):
        raise ValueError('actual unsupported target status differs')

    if type(classifications) is not dict or set(classifications) != set(VIEW_ORDER):
        raise ValueError('actual six-view classification evidence is missing')
    for rows in classifications.values():
        if set(rows) != set(region_ids):
            raise ValueError('actual six-view classifications have a different target region set')
        for row in rows.values():
            if row['status'] not in ('complete', 'back_facing', 'edge_on', 'outside_frustum', 'positive_area_occlusion'):
                raise ValueError('actual classification has an unknown status contract')
            if row['complete'] is not (row['status'] == 'complete'):
                raise ValueError('actual classification completeness disagrees with its status')

    images = table(public.get('images'))
    if len(images) != len(validated_frames) or len({row['view_name'] for row in images}) != len(images):
        raise ValueError('actual image sequence and validated array sequence differ')
    normalized_images = []
    stable_patch = fingerprint([(row['roi_id'], row['source_triangle_index_ranges']) for row in regions])
    for index, (image, arrays) in enumerate(zip(images, validated_frames)):
        frame = arrays['_validated_frame']
        if (any(image[key] != frame[key] for key in ('view_name', 'image_ref', 'image_sha256', 'patch_mapping_identity'))
                or image['native_content_block_index'] != index + 1):
            raise ValueError('actual delivered image differs from its validated saved frame')
        row = copy.deepcopy(image)
        row['image_ref'] = 'validated-view:' + row['view_name']
        row['patch_mapping_identity'] = stable_patch
        normalized_images.append(row)

    normalized = copy.deepcopy(public)
    for key in ('binding', 'objects', 'scope', 'session_id', 'images', 'regions'):
        normalized.pop(key, None)
    normalized['target_asset_key'] = target['asset_key']
    normalized['source_frame'] = copy.deepcopy(binding['observation_target']['source_frame'])
    normalized['camera_specification'] = copy.deepcopy(binding['camera_specification'])
    normalized['regions'] = normalized_regions
    normalized['images'] = normalized_images
    normalized['target_view_classifications'] = copy.deepcopy(classifications)
    normalized_scope = copy.deepcopy(scope)
    normalized_scope['capture_object_count'] = 1
    normalized_scope['observation_scope'] = {
        key: value for key, value in observation_scope.items()
        if key not in ('occluder_only_object_count', 'excluded_object_count')}
    normalized_scope['observation_scope']['target_object_index'] = target['asset_key']
    normalized_scope['patch_support']['object_support'] = [dict(target_support, object_index=target['asset_key'])]
    normalized_scope['patch_support']['unsupported_components'] = [
        dict(row, object_index=target['asset_key']) for row in components]
    normalized_scope['objects_without_supported_roi'] = [
        dict(row, object_index=target['asset_key']) for row in without_regions]
    normalized['scope'] = normalized_scope
    # image_delivery is kept whole. Work counters and source identities stay in
    # the raw pinned artifacts and are not relabeled as quality facts here.
    return {'comparison': normalized, 'scope_audit': copy.deepcopy(scope),
            'current_source_validated': True, 'current_target_instance_validated': True,
            'all_target_source_faces_accounted': True,
            'actual_raw_public_sha256': fingerprint(public)}


def saved_frame_arrays(path, expected_sha256, mapping, frame):
    """Read a pinned actual NPZ without constructing a replacement frame."""
    import numpy as np

    if (file_sha256(path) != _sha(expected_sha256, 'actual array file')
            or frame['arrays_sha256'] != expected_sha256):
        raise ValueError('actual saved array SHA differs')
    if (frame['host_binding_sha256'] != mapping['host_binding_sha256']
            or frame['source_revision'] != mapping['source_revision']
            or frame['scene_identity'] != mapping['geometry_identity']
            or frame['candidate_identity'] != mapping['camera_identity']):
        raise ValueError('actual frame is bound to a different current slot source')
    poses = {pose['name']: pose for pose in mapping['camera_specification']['views']}
    if (frame['view_name'] not in poses
            or 'pose' in frame and frame['pose'] != poses[frame['view_name']]):
        raise ValueError('actual frame pose differs from its current frozen camera')
    with np.load(path, allow_pickle=False) as arrays:
        buffers = {key: arrays[key] for key in ('color', 'depth', 'owners', 'triangle_ids')}
        for key in ('owner_schema', 'owner_mapping_identity', 'triangle_id_scope',
                    'patch_mapping_version', 'patch_mapping_identity'):
            if arrays[key].shape != () or arrays[key].item() != frame[key]:
                raise ValueError('saved frame owner or patch identity differs')
        if arrays['patch_roi_ids'].tolist() != frame['patch_roi_ids']:
            raise ValueError('saved frame region order differs')
        actual_offsets = arrays['face_patch_offsets'].tolist()
        expected_offsets = [row['current_face_offset'] for row in mapping['objects']]
        expected_offsets.append(mapping['total_current_triangles'])
        if actual_offsets != expected_offsets:
            raise ValueError('stored local face offsets differ from actual source face ordering')
        result = normalize_saved_buffers(buffers, mapping)
        result['_validated_frame'] = {key: frame[key] for key in
                                      ('view_name', 'image_ref', 'image_sha256', 'patch_mapping_identity')}
        return result

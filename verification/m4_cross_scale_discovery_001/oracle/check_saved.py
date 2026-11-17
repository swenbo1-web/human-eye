"""Independent saved-only source, task, frame and native delivery qualification."""

import argparse
import ast
import base64
import copy
from fractions import Fraction as F
import hashlib
from io import BytesIO
import importlib.util
import itertools
import json
from pathlib import Path
import re
import sys
import zlib

HERE = Path(__file__).resolve().parent
NS = HERE.parent
sys.path.insert(0, str(HERE))
import expected
import geometry_witness

FRAME_PATH = expected.PRIOR / 'checks/saved_frames_r2.py'
FRAME_SHA = 'a7e7fb4d42fc845e43b37e0870af10beb79da333a70f5017bcf534cb11390f34'
if hashlib.sha256(FRAME_PATH.read_bytes()).hexdigest() != FRAME_SHA:
    raise ValueError('sealed_saved_pixel_checker_changed')
SPEC = importlib.util.spec_from_file_location('_sealed_independent_frame_helpers', FRAME_PATH)
PIXELS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PIXELS)
np, Image = PIXELS.np, PIXELS.Image


def read(path):
    return json.loads(Path(path).read_bytes())


def fingerprint(value):
    return expected.fingerprint(value)


def key(row):
    return row['object_name'], tuple(row['source_triangle_indices'])


class Audit(PIXELS.Evidence):
    def read(self, path, digest=None, within=None):
        return json.loads(self.file(path, digest, within))


def decode_captures(session, binding, audit):
    resources, captures, loaded, commands = {}, [], {}, []
    manifest = {row['path']: row['sha256'] for row in binding['source_manifest']}
    for folder in sorted((session / 'native/WIRE').glob('[0-9]*')):
        request = audit.read(folder / 'REQUEST.bin', within=session)
        response = audit.read(folder / 'RESPONSE.bin', within=session)
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
            blob = zlib.decompress(base64.b64decode(ast.literal_eval(expression.args[0].args[0]), validate=True))
            relative = Path(ast.literal_eval(node.args[1])).relative_to(Path(binding['install_root'])).as_posix()
            digest = hashlib.sha256(blob).hexdigest()
            audit.check(digest == manifest[relative], 'actual_embedded_source/' + relative)
            loaded[relative] = digest
        matched = re.search(r'_request = _json.loads\((.+)\)\n', code)
        if matched is None:
            continue
        command = json.loads(ast.literal_eval(matched.group(1)))
        lines = [line for line in response.get('result', {}).get('result', '').splitlines()
                 if line.startswith('HUMAN_EYE_BLENDER_MCP:')]
        audit.check(response['status'] == 'success' and len(lines) == 1, 'actual_unique_host_packet')
        packet = json.loads(lines[0].split(':', 1)[1])
        audit.check(packet.get('error') is None, 'actual_host_packet_success')
        value = packet.get('result')
        commands.append(dict(wire_sequence=int(folder.name), command=command))
        if type(value) is not dict:
            continue
        for resource in value.get('resources', []):
            resource_key = resource['id'], resource['revision']
            audit.check(resource_key not in resources or resources[resource_key] == resource, 'stable_resource_identity')
            resources[resource_key] = resource
        capture = copy.deepcopy(value.get('capture', value))
        if not capture.get('meshes'):
            continue
        for mesh in capture['meshes']:
            reference = mesh.pop('_scene_resource', None)
            if reference is not None:
                resource = resources[reference['id'], reference['revision']]
                matrix, scale = reference['matrix'], reference['scale']
                mesh.update(vertices=[[(((matrix[axis][0] * point[0] + matrix[axis][1] * point[1])
                    + matrix[axis][2] * point[2]) + matrix[axis][3]) * scale for axis in range(3)]
                    for point in resource['vertices_local']], faces=copy.deepcopy(resource['faces']), edges=copy.deepcopy(resource['edges']))
        captures.append(capture)
    audit.check(loaded.get('human_eye_plugin/blender_host.py') == manifest['human_eye_plugin/blender_host.py'], 'current_host_source_loaded')
    return captures, commands


def current_capture(captures, source, audit):
    matches = [capture for capture in captures if capture['revision'] == source['scene_revision']
               and capture['capture_state'] == source['capture_state']
               and capture.get('capture_scope', 'complete_scene_meshes') == source['capture_scope']]
    audit.check(bool(matches), 'same_current_original_capture_available')
    signature = fingerprint(matches[0])
    audit.check(all(fingerprint(capture) == signature for capture in matches), 'same_current_capture_not_ambiguous')
    return matches[0]


def compare_geometry(capture, fixture, audit):
    wanted = {obj['name']: obj for obj in fixture}
    meshes = capture['meshes']
    audit.check(len(meshes) == len(wanted) == 9 and {mesh['name'] for mesh in meshes} == set(wanted), 'full_scene_nine_objects')
    for mesh in meshes:
        original = wanted[mesh['name']]
        audit.check([tuple(F(value) for value in point) for point in mesh['vertices']] == original['vertices']
                    and [tuple(face) for face in mesh['faces']] == original['triangles'], 'actual_ordered_world_geometry/' + mesh['name'])
    audit.check(sum(len(mesh['faces']) for mesh in meshes) == 56, 'full_scene_56_source_triangles')


def validate_region(fact, component, fixture_by_name, audit):
    audit.check(tuple(map(F, fact['center_world_m'])) == tuple(component['center_world_m']), 'exact_region_center')
    normal, published = tuple(component['plane_normal_integer']), tuple(map(F, fact['front_direction_world']))
    audit.check(expected.EXACT.cross(normal, published) == (0, 0, 0) and expected.EXACT.dot(normal, published) > 0,
                'oriented_rational_normal')
    center, u, v = [tuple(map(F, fact[field])) for field in ('center_world_m', 'half_edge_u_world_m', 'half_edge_v_world_m')]
    corners = {tuple(c + su * x + sv * y for c, x, y in zip(center, u, v)) for su, sv in itertools.product((-1, 1), repeat=2)}
    original = fixture_by_name[component['object_name']]
    audit.check(corners == {original['vertices'][index] for index in component['boundary_loops'][0]}, 'source_rectangle_corners')


def source_row(component, capture, binding):
    object_index = next(index for index, mesh in enumerate(capture['meshes']) if mesh['name'] == component['object_name'])
    host = binding['objects'][object_index]
    return dict(document_epoch=binding['document_epoch'], host_id=host['host_id'], instance_id=host['instance_id'],
        object_index=object_index, source_triangle_indices=component['source_triangle_indices'],
        ordered_geometry_sha256=expected.ordered_geometry(capture['meshes'][object_index]),
        parent_binding_sha256=binding['binding_sha256'], parent_source_binding_sha256=binding['source_binding_sha256'],
        scene_revision=binding['scene_revision'], capture_state=binding['capture_state'])


def source_binding_checks(capture, binding, installed, audit):
    audit.check(binding['capture_scope'] == capture.get('capture_scope', 'complete_scene_meshes')
                == capture['host_identity']['capture_scope'] == 'complete_scene_meshes', 'complete_parent_capture_scope')
    audit.check(binding['document_epoch'] == capture['host_identity']['document_epoch']
                and binding['scene_revision'] == capture['revision'] and binding['capture_state'] == capture['capture_state'],
                'parent_current_generation')
    objects = [dict(object_index=index, host_id=mesh['object_id'], object_name=mesh['name'],
                    instance_id=capture['host_identity']['object_instances'][mesh['object_id']])
               for index, mesh in enumerate(capture['meshes'])]
    audit.check(binding['objects'] == objects and binding['unit'] == capture['unit'] == 'm'
                and binding['coordinate_frame'] == capture['coordinate_frame'] == 'world'
                and binding['source'] == capture['source'] == 'blender', 'parent_object_order_and_world_units')
    appended = {'runtime_source_sha256','source_status','disk_status','source_check_scope'}
    base = {name: value for name, value in binding.items() if name not in appended | {
        'source_binding_sha256','binding_sha256','camera_specification','geometry_identity','camera_identity'}}
    audit.check(fingerprint(base) == binding['source_binding_sha256'], 'parent_source_digest_preimage')
    full = {name: value for name, value in binding.items() if name not in appended | {'binding_sha256'}}
    audit.check(fingerprint(full) == binding['binding_sha256'], 'parent_camera_binding_digest_preimage')
    audit.check(binding['runtime_source_sha256'] == installed['source_sha256']
                and binding['source_status'] == 'loaded_generation' and binding['disk_status'] == 'disk_not_checked'
                and binding['source_check_scope'] == 'bound_generation_identity', 'current_installed_runtime_attestation')
    views = binding['camera_specification']['views']
    audit.check([pose['name'] for pose in views] == PIXELS.ORDER
                and [pose['direction_rational'] for pose in views] == PIXELS.DIRECTIONS, 'fixed_six_camera_directions')
    camera_rows = [{name: pose[name] for name in ('name','direction_rational','view_matrix','projection_matrix','size_px')}
                   for pose in views]
    audit.check(fingerprint(camera_rows) == binding['camera_identity'], 'parent_camera_identity_preimage')


def local_binding_checks(scope, parent, source, audit):
    binding = scope['binding']
    audit.check(binding['schema'] == 'active-observation-region-source-v1'
                and binding['capture_scope'] == 'same_capture_region_view', 'local_scope_schema')
    for name in ('objects', 'scene_revision', 'document_epoch', 'capture_state', 'unit', 'coordinate_frame', 'source'):
        audit.check(binding[name] == parent[name], 'same_capture_local/' + name)
    audit.check(binding['region_source'] == source
                and binding['parent_binding_sha256'] == parent['binding_sha256']
                and binding['parent_source_binding_sha256'] == parent['source_binding_sha256'], 'current_parent_child_region_source')
    appended = {'runtime_source_sha256','source_status','disk_status','source_check_scope'}
    audit.check(all(binding[name] == parent[name] for name in appended), 'local_runtime_attestation')
    before = {name: value for name, value in binding.items() if name not in appended | {
        'source_binding_sha256', 'binding_sha256', 'camera_specification', 'geometry_identity', 'camera_identity'}}
    audit.check(fingerprint(before) == binding['source_binding_sha256'], 'local_source_digest_preimage')
    before = {name: value for name, value in binding.items() if name not in appended | {'binding_sha256'}}
    audit.check(fingerprint(before) == binding['binding_sha256'], 'local_binding_digest_preimage')
    audit.check(binding['geometry_identity'] == parent['geometry_identity'], 'same_original_geometry_identity')
    cameras = binding['camera_specification']
    views = [{name: pose[name] for name in ('name', 'direction_rational', 'view_matrix', 'projection_matrix', 'size_px')}
             for pose in cameras['views']]
    audit.check(binding['camera_identity'] == fingerprint(views), 'local_camera_identity')


def patch_maps(scope, capture, audit):
    full = dict(binding=scope['binding'], facts=scope['facts'])
    if scope['scope_id'] == 'global':
        return PIXELS.partition_checks(full, capture, audit)
    support = scope['facts']['scope']['patch_support']
    regions = support['regions']
    audit.check(support['schema'] == 'active-region-task-patch-support-v1'
                and support['all_triangles_participate_in_occlusion'] is True and len(regions) == 1, 'local_patch_scope_exact_region')
    audit.check(len(support['objects']) == len(capture['meshes']), 'local_all_objects_in_occlusion')
    face_patch = [np.full(len(mesh['faces']), -1, dtype=np.int32) for mesh in capture['meshes']]
    target = regions[0]
    face_patch[target['object_index']][target['triangle_indices']] = 0
    for index, (mesh, row) in enumerate(zip(capture['meshes'], support['objects'], strict=True)):
        selected = target['triangle_indices'] if index == target['object_index'] else []
        other = [face for face in range(len(mesh['faces'])) if face not in selected]
        audit.check(row['object_index'] == index and row['source_triangle_count'] == len(mesh['faces'])
                    and row['supported_triangle_indices'] == selected and row['supported_triangle_count'] == len(selected)
                    and row['occluder_only_triangle_indices'] == other, 'local_source_triangle_role_partition')
    return regions, face_patch


def check_frame(frame, observation, scope, capture, regions, face_patch, session, audit):
    png = audit.file(frame['image_path'], frame['image_sha256'], session)
    blob = audit.file(frame['arrays_path'], frame['arrays_sha256'], session)
    audit.check(len(png) == frame['PNG_bytes'] and len(blob) == frame['compressed_array_file_bytes'], 'frame_encoded_sizes')
    with np.load(BytesIO(blob), allow_pickle=False) as saved:
        arrays = {name: saved[name] for name in saved.files}
    with Image.open(BytesIO(png)) as image:
        audit.check(image.mode == 'RGB' and image.size == (512, 512) and image.format == 'PNG'
                    and np.array_equal(np.asarray(image), arrays['color']), 'PNG_exact_RGB_array')
    for name, dtype, shape in (('color', 'uint8', (512,512,3)), ('depth', 'float64', (512,512)),
                              ('owners', 'int32', (512,512)), ('triangle_ids', 'int32', (512,512)),
                              ('patch_owners', 'int32', (512,512))):
        value = arrays[name]
        audit.check(value.dtype == np.dtype(dtype) and value.shape == shape, 'array_shape_dtype/' + name)
        audit.check(frame['arrays'][name] == dict(dtype=dtype, shape=list(shape), nbytes=value.nbytes,
            sha256=hashlib.sha256(value.tobytes()).hexdigest()), 'array_original_bytes/' + name)
    offsets = np.cumsum([0] + [len(mesh['faces']) for mesh in capture['meshes']], dtype=np.int64)
    ids = np.concatenate(face_patch)
    ordered = [(tuple(tuple(F(value) for value in point) for point in mesh['vertices']), tuple(tuple(face) for face in mesh['faces']))
               for mesh in capture['meshes']]
    roi_ids = [region['roi_id'] for region in regions]
    mapping = fingerprint(dict(version=PIXELS.PATCH_SCHEMA, roi_ids=tuple(roi_ids), ordered_geometry=ordered,
                               face_patch_ids=[value.tolist() for value in face_patch]))
    owners_digest = fingerprint((PIXELS.OWNER_SCHEMA, PIXELS.TRIANGLE_SCOPE, mapping, offsets.tolist()))
    audit.check(np.array_equal(arrays['face_patch_offsets'], offsets) and np.array_equal(arrays['face_patch_ids'], ids)
                and arrays['patch_roi_ids'].tolist() == roi_ids, 'raw_triangle_to_local_patch_bijection')
    for name, value in (('owner_schema', PIXELS.OWNER_SCHEMA), ('triangle_id_scope', PIXELS.TRIANGLE_SCOPE),
                        ('patch_mapping_version', PIXELS.PATCH_SCHEMA), ('patch_mapping_identity', mapping),
                        ('owner_mapping_identity', owners_digest)):
        audit.check(frame[name] == arrays[name].item() == value, 'owner_mapping_preimage/' + name)
    rgb, depth, owners, triangles, patches = [arrays[name] for name in ('color','depth','owners','triangle_ids','patch_owners')]
    foreground = owners >= 0
    audit.check(np.all(owners >= -1) and np.all(owners < len(capture['meshes'])) and np.all(triangles >= -1)
                and np.all(triangles < offsets[-1]) and np.array_equal(triangles >= 0, foreground), 'source_owner_ranges')
    audit.check(np.all(np.isposinf(depth[~foreground])) and np.all(np.isfinite(depth[foreground]) & (depth[foreground] > 0))
                and np.all(rgb[~foreground] == [18,22,30]) and np.all(patches[~foreground] == -1), 'background_and_depth')
    audit.check(np.all(triangles[foreground] >= offsets[owners[foreground]])
                and np.all(triangles[foreground] < offsets[owners[foreground]+1])
                and np.array_equal(patches[foreground], ids[triangles[foreground]]), 'actual_winning_triangle_patch')
    binding = scope['binding']
    audit.check(frame['scope_id'] == scope['scope_id'] and frame['camera_identity'] == binding['camera_identity']
                and frame['host_binding_sha256'] == binding['binding_sha256'] and frame['source_revision'] == binding['scene_revision']
                and frame['scene_identity'] == binding['geometry_identity'] and frame['candidate_identity'] == binding['camera_identity'],
                'frame_scope_source_camera_identity')
    reference = (binding['binding_sha256'], frame['view_name'], frame['image_sha256'], mapping,
                 PIXELS.OWNER_SCHEMA, owners_digest, frame['frame_identity'])
    audit.check(frame['image_ref'] == 'active-host-image:' + fingerprint(reference), 'host_image_reference_preimage')
    audit.check(frame['pose'] == next(pose for pose in binding['camera_specification']['views'] if pose['name'] == frame['view_name']),
                'exact_scope_published_pose')
    audit.check(all(observation[name] == frame[name] for name in ('scope_id','frame_identity','view_name','image_ref','image_sha256')), 'observation_frame_identity')
    boundary = PIXELS.contrasting_boundary(rgb, patches)
    facts = {row['roi_id']: row for row in scope['facts']['regions']}
    by_roi = {row['roi_id']: row for row in observation['pixel_rows']}
    audit.check(len(by_roi) == len(observation['pixel_rows']) == len(regions), 'complete_unique_pixel_rows')
    counts = []
    for index, region in enumerate(regions):
        mask = patches == index
        surface, edge = int(np.count_nonzero(mask)), int(np.count_nonzero(mask & boundary))
        bounds, anchor = PIXELS.pixel_location(mask)
        normal = np.array([float(F(value)) for value in facts[region['roi_id']]['front_direction_world']])
        front = float(normal @ np.array(frame['pose']['target_to_eye_unit'])) > 0
        readable = front and surface >= 16 and edge >= 4
        pixel = by_roi[region['roi_id']]
        audit.check(pixel['visible_surface_pixels'] == surface and pixel['contrasting_boundary_pixels'] == edge
                    and pixel['visible_pixel_bounds'] == bounds and pixel['visible_pixel_anchor'] == anchor
                    and pixel['front_facing'] is front and pixel['readable'] is readable
                    and pixel['minimum_surface_pixels'] == 16 and pixel['minimum_boundary_pixels'] == 4
                    and pixel['minimum_rgb_boundary_contrast'] == 24, 'independent_actual_readability')
        counts.append(dict(roi_id=region['roi_id'], surface_pixels=surface, boundary_pixels=edge, readable=readable))
    audit.check(sorted(observation['readable_roi_ids']) == sorted(row['roi_id'] for row in counts if row['readable']), 'actual_readable_set')
    ray = PIXELS.ray_winner_checks(frame, capture, arrays, audit)
    return dict(scope_id=frame['scope_id'], frame_identity=frame['frame_identity'], image_ref=frame['image_ref'],
                view_name=frame['view_name'], pixels=counts, independent_ray_review=ray,
                array_hashes={name: frame['arrays'][name]['sha256'] for name in ('color','depth','owners','triangle_ids','patch_owners')})


def check_session(session, run_binding, variant, call_index=1, translated=False):
    session = Path(session).resolve()
    audit = Audit()
    for path in (Path(__file__), Path(expected.__file__), Path(geometry_witness.__file__), FRAME_PATH, HERE/'EXPECTATIONS.json'):
        audit.file(path)
    for record in expected.source_pins():
        audit.file(record['path'], record['sha256'])
    install = audit.read(run_binding)
    for record in install['source_manifest']:
        audit.file(Path(install['install_root']) / record['path'], record['sha256'])
    calls = [json.loads(line) for line in audit.file(session/'PUBLIC_REQUESTS.jsonl').splitlines() if line.strip()]
    call = calls[call_index-1]
    request = audit.read(call['request_path'], call['request_sha256'], session)
    response = audit.read(call['response_path'], call['response_sha256'], session)
    audit.check(request == audit.read(call['actual_TX_path'], call['actual_TX_sha256'], session)
                and response == audit.read(call['actual_RX_path'], call['actual_RX_sha256'], session), 'actual_original_stdio')
    audit.check(response.get('result', {}).get('isError') is False and request['id'] == response['id'], 'actual_public_success')
    arguments = request['params']['arguments']
    audit.check(request['params']['name'] == 'human_eye_scene_observe' and arguments['include_image'] is True
                and set(arguments['query']) == {'mode','region_task'}, 'only_public_geometric_task_conditions')
    original = call['producer_archive']
    full = audit.read(original['path'], original['sha256'], session)
    audit.check(call['started_ns'] <= original['started_ns'] <= original['producer_returned_ns'] <= call['closed_ns'], 'same_producer_window')
    audit.check(full['read_only'] is True and full['execution_authority'] is False, 'read_only_product')
    blocks = response['result']['content']
    texts = [json.loads(block['text']) for block in blocks if block['type'] == 'text']
    images = [block for block in blocks if block['type'] == 'image']
    audit.check(len(texts) == 1, 'one_original_public_text')
    public = texts[0]
    parent = full['binding']
    captures, commands = decode_captures(session, install, audit)
    capture = current_capture(captures, parent, audit)
    fixture = expected.fixture(F(1,4) if translated else F(0))
    fixture_by_name = {obj['name']: obj for obj in fixture}
    compare_geometry(capture, fixture, audit)
    source_binding_checks(capture, parent, install, audit)
    components, eligible = expected.task_components(fixture, arguments['query']['region_task'])
    scopes = {scope['scope_id']: scope for scope in full['scopes']}
    audit.check(len(scopes) == len(full['scopes']) and scopes['global']['binding'] == parent, 'unique_global_and_local_scopes')
    task = full['facts']['region_task']
    rows = {key(row): row for row in task['rows']}
    audit.check(task['conditions'] == arguments['query']['region_task']
                and len(rows) == len(task['rows']) == len(eligible)
                and set(rows) == {key(row) for row in eligible}, 'independently_discovered_task_eligible_set')
    global_scope = scopes['global']
    global_regions, _ = patch_maps(global_scope, capture, audit)
    independent = {(row['object_name'], tuple(row['source_triangle_indices'])): row for row in components if row['rectangle_supported']}
    global_keys = {(capture['meshes'][row['object_index']]['name'], tuple(row['triangle_indices'])) for row in global_regions}
    audit.check(global_keys == set(independent) and len(global_regions) == 22, 'all_independent_rectangles_retained')
    global_facts = {row['roi_id']: row for row in global_scope['facts']['regions']}
    for region in global_regions:
        component = independent[capture['meshes'][region['object_index']]['name'], tuple(region['triangle_indices'])]
        validate_region(global_facts[region['roi_id']], component, fixture_by_name, audit)
    unsupported = global_scope['facts']['scope']['patch_support']['objects']
    audit.check(sum(row['unsupported_triangle_count'] for row in unsupported) == 12
                and sum(row['supported_triangle_count'] for row in unsupported) == 44, 'supported_unsupported_source_denominator')
    all_frames = full['constructed_frames']
    frames_by_id = {frame['frame_identity']: frame for frame in all_frames}
    audit.check(len(frames_by_id) == len(all_frames) == full['work']['raster_completed'] == full['work']['local_verified_images'], 'complete_constructed_frame_denominator')
    frame_reviews = []
    for scope in scopes.values():
        scope_frames = [frames_by_id[identity] for identity in scope['frame_refs']]
        audit.check(len({frame['view_name'] for frame in scope_frames}) == len(scope_frames) <= 6, 'finite_unique_views_within_scope')
        if scope['scope_id'] != 'global':
            own_source = scope['binding']['region_source']
            match = next(component for component in eligible if source_row(component,capture,parent) == own_source)
            local_binding_checks(scope, parent, source_row(match,capture,parent), audit)
        regions, face_patch = patch_maps(scope, capture, audit)
        observations = {row['frame_identity']: row for row in scope['facts']['observations']}
        audit.check(set(observations) == set(scope['frame_refs']), 'one_observation_per_actual_scope_frame')
        for sequence, frame in enumerate(scope_frames, 1):
            frame_preimage = ((frame['scene_identity'],frame['candidate_identity']),frame['owner_schema'],
                              frame['owner_mapping_identity'],frame['view_name'],sequence,frame['image_sha256'])
            audit.check(fingerprint(frame_preimage) == frame['frame_identity'], 'frame_identity_preimage')
            frame_reviews.append(check_frame(frame, observations[frame['frame_identity']], scope, capture,
                                             regions, face_patch, session, audit))
    audit.check({frame['frame_identity'] for frame in all_frames} == {identity for scope in scopes.values() for identity in scope['frame_refs']}, 'scope_complete_frame_archive')
    outcomes = []
    for component in eligible:
        row = rows[key(component)]
        validate_region(row, component, fixture_by_name, audit)
        source = source_row(component,capture,parent)
        audit.check(row['source'] == source, 'task_current_source_parent_child')
        witness = row['complete_witness']
        if component['object_name'] == 'Obj_06':
            audit.check(row['status'] == 'unknown' and witness is None
                        and row['reason'] == 'positive_area_occlusion_all_front_views'
                        and set(row['view_reasons']['positive_area_occlusion']) == set(expected.EXACT.VIEWS), 'genuine_six_direction_occlusion_unknown')
            proof = read(expected.PRIOR/'oracle/STATIC_QUALIFICATION.json')['occlusion']
        else:
            audit.check(row['status'] == 'covered' and row['reason'] == 'observed_readable' and witness is not None, 'actual_open_region_covered')
            frame = frames_by_id[witness['frame_identity']]
            scope = scopes[witness['scope_id']]
            audit.check(frame['scope_id'] == witness['scope_id'] and frame['image_ref'] == witness['image_ref']
                        and frame['view_name'] == witness['view_name'] and frame in full['frames'], 'selected_local_witness_frame')
            observation = next(item for item in scope['facts']['observations'] if item['frame_identity'] == witness['frame_identity'])
            pixel = observation['pixel_rows'][witness['pixel_row_index']]
            audit.check(pixel['roi_id'] == row['roi_id'] and pixel['readable'] is True, 'witness_exact_current_pixel_row')
            proof = geometry_witness.prove(fixture, component, tuple(frame['pose']['direction_rational']))
        outcomes.append(dict(object_name=component['object_name'], source_triangle_indices=component['source_triangle_indices'],
                             roi_id=row['roi_id'], status=row['status'], reason=row['reason'], source=source,
                             complete_witness=witness, independent_geometry=proof))
    selected = full['frames']
    audit.check(len(selected) == len(images) == (1 + sum(row['status']=='covered' for row in outcomes)), 'selected_overview_and_witness_native_count')
    audit.check(selected[0]['scope_id'] == 'global' and selected[0]['view_name'] == 'SCENE', 'real_global_overview_selected')
    for frame, block in zip(selected, images, strict=True):
        audit.check(block['type'] == 'image' and block['mimeType'] == 'image/png'
                    and base64.b64decode(block['data'],validate=True) == audit.file(frame['image_path'],frame['image_sha256'],session), 'original_native_selected_image_bytes')
    if arguments.get('response_detail') == 'full':
        audit.check(public['facts']['region_task'] == task and public['scopes'] == full['scopes']
                    and public['constructed_frames'] == full['constructed_frames'], 'full_task_and_construction_archive_delivered')
    else:
        audit.check(public['schema'] == 'active-observation-region-task-brief-v1', 'default_task_brief_schema')
        brief_task = copy.deepcopy(public['region_task'])
        for row in brief_task['rows']:
            witness = row['complete_witness']
            if witness is not None:
                selected_index = next(index for index, frame in enumerate(selected)
                                      if frame['frame_identity'] == witness['frame_identity'])
                index = [index for index, block in enumerate(blocks) if block['type']=='image'][selected_index]
                audit.check(witness.pop('native_content_block_index') == index, 'brief_witness_exact_native_block_index')
        audit.check(brief_task == task, 'brief_direct_task_facts_lossless')
        table = public['images']
        expected_columns = ['scope_id','camera_identity','view_name','frame_identity','image_ref','image_sha256','native_content_block_index']
        audit.check(table['columns'] == expected_columns and len(table['rows']) == len(selected), 'brief_frame_identity_table')
        for frame, row in zip(selected, table['rows'], strict=True):
            fields = dict(zip(table['columns'],row,strict=True))
            audit.check(all(fields[name] == frame[name] for name in expected_columns[:-1])
                        and fields['native_content_block_index'] == 1 + selected.index(frame), 'brief_three_scope_image_indices')
    actual_work = full['work']
    work = full['generation_work'] if actual_work.get('result_cache_hit') else actual_work
    audit.check(work['capture_calls'] == work['geometry_parse_calls'] == work['mesh_conversions']
                == work['partition_calls'] == 1, 'single_capture_parse_mesh_partition')
    audit.check(work['captured_triangle_count'] == 56 and work['capture_object_count'] == 9, 'all_occlusion_geometry_preserved')
    audit.check(sum(frame['PNG_bytes'] for frame in all_frames) == work['PNG_bytes']
                and sum(frame['compressed_array_file_bytes'] for frame in all_frames) == work['NPZ_bytes'], 'all_construction_bytes_counted')
    if not actual_work.get('result_cache_hit'):
        audit.check(actual_work['raster_attempts'] == len(all_frames), 'all_new_raster_attempts_counted')
    else:
        audit.check(actual_work['raster_attempts'] == actual_work['raster_completed'] == 0,
                    'cached_task_has_zero_new_raster_attempts')
    expected_total = 8 if variant == 'initial' else 3
    if arguments['query']['region_task'] == expected.MAIN:
        audit.check(len(all_frames) == expected_total, 'variant_expected_finite_construction_count')
    return dict(schema='cross-scale-saved-quality-v1', passed_checked_scope=True, session=str(session), call_index=call_index,
        variant=variant, current_capture=capture, outcomes=outcomes, scopes=list(scopes), frames=frame_reviews,
        selected_frames=[dict(scope_id=frame['scope_id'],frame_identity=frame['frame_identity'],image_ref=frame['image_ref'],
                             camera_identity=frame['camera_identity'],image_sha256=frame['image_sha256']) for frame in selected],
        constructed_frames=len(all_frames), actual_native_images=len(images), work=actual_work, generation_work=work,
        check_count=len(audit.checks), checks=audit.checks,
        source_pins=expected.source_pins(), input_pins=list(audit.pins.values()),
        new_operations=dict(Blender=0,MCP=0,raster=0,model=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session',type=Path,required=True)
    parser.add_argument('--binding',type=Path)
    parser.add_argument('--variant',choices=('initial','optimized'),required=True)
    parser.add_argument('--call-index',type=int,default=1)
    parser.add_argument('--translated',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    binding = args.binding or Path(read(args.session/'SLOT_RESULT.json')['run_binding_path'])
    try:
        result = check_session(args.session,binding,args.variant,args.call_index,args.translated)
    except Exception as error:
        result = dict(schema='cross-scale-saved-quality-v1',passed_checked_scope=False,error=dict(type=type(error).__name__,message=str(error)))
    with args.output.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,sort_keys=True,ensure_ascii=False,allow_nan=False,indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=result['passed_checked_scope'],checks=result.get('check_count'),output=str(args.output),error=result.get('error'))))
    if not result['passed_checked_scope']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

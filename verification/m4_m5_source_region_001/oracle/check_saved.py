"""Review original public bytes, current source capture and saved source-region frames."""

import argparse
import ast
import base64
import copy
from fractions import Fraction as F
import hashlib
from io import BytesIO
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import traceback
import zlib

HERE = Path(__file__).resolve().parent
NS = HERE.parent
sys.path.insert(0, str(HERE))
import static_preflight

FRAME_PATH = NS.parent / 'm4_global_local_qualification_001/checks/saved_frames_r2.py'
MATH_PATH = NS.parent / 'm5_observe_measure_001/oracle.py'
FRAME_SHA = 'a7e7fb4d42fc845e43b37e0870af10beb79da333a70f5017bcf534cb11390f34'
MATH_SHA = '0133b8e69b34e9347cb48cf9220f9a880065f6dc95517e300295afd2c96a9acb'


def sealed_module(path, digest, name):
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('sealed_saved_helper_changed/' + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PIXELS = sealed_module(FRAME_PATH, FRAME_SHA, '_sealed_source_region_pixel_rays')
MATH = sealed_module(MATH_PATH, MATH_SHA, '_sealed_source_region_point_membership')
np, Image = PIXELS.np, PIXELS.Image
fingerprint = PIXELS.fingerprint


class Audit(PIXELS.Evidence):
    def read(self, path, digest=None, within=None):
        return json.loads(self.file(path, digest, within))


def decode_captures(session, binding, audit):
    """Decode original host packets, including resident local-resource transforms."""
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
    audit.check(loaded.get('human_eye_plugin/blender_host.py') == manifest['human_eye_plugin/blender_host.py'],
                'current_host_source_loaded')
    return captures, commands


def current_capture(captures, source, audit):
    matches = [capture for capture in captures if capture['revision'] == source['scene_revision']
               and capture['capture_state'] == source['capture_state']
               and capture.get('capture_scope', 'complete_scene_meshes') == source['capture_scope']]
    audit.check(bool(matches), 'same_current_original_capture_available')
    audit.check(len({fingerprint(capture) for capture in matches}) == 1, 'same_current_capture_not_ambiguous')
    return matches[0]


def compare_geometry(capture, translated, audit):
    recipe, objects = static_preflight.objects()
    wanted = {row['name']: row for row in objects}
    if translated:
        obj = wanted['Obj_07']
        obj['vertices'] = [tuple(value + (F(1, 4) if axis == 0 else 0) for axis, value in enumerate(point))
                           for point in obj['vertices']]
    meshes = capture['meshes']
    audit.check(len(meshes) == 11 and {mesh['name'] for mesh in meshes} == set(wanted), 'full_scene_eleven_objects')
    for mesh in meshes:
        row = wanted[mesh['name']]
        audit.check([tuple(map(F, point)) for point in mesh['vertices']] == row['vertices']
                    and [tuple(face) for face in mesh['faces']] == row['faces'],
                    'actual_ordered_world_geometry/' + mesh['name'])
    audit.check(sum(len(mesh['vertices']) for mesh in meshes) == 64
                and sum(len(mesh['faces']) for mesh in meshes) == 62, 'full_scene_64_vertices_62_triangles')
    return recipe


def binding_checks(capture, binding, installed, audit):
    audit.check(binding['capture_scope'] == capture.get('capture_scope', 'complete_scene_meshes')
                == capture['host_identity']['capture_scope'] == 'complete_scene_meshes', 'complete_scene_capture_scope')
    audit.check(binding['document_epoch'] == capture['host_identity']['document_epoch']
                and binding['scene_revision'] == capture['revision'] and binding['capture_state'] == capture['capture_state'],
                'parent_current_generation')
    objects = [dict(object_index=index, host_id=mesh['object_id'], object_name=mesh['name'],
                    instance_id=capture['host_identity']['object_instances'][mesh['object_id']])
               for index, mesh in enumerate(capture['meshes'])]
    audit.check(binding['objects'] == objects and binding['unit'] == capture['unit'] == 'm'
                and binding['coordinate_frame'] == capture['coordinate_frame'] == 'world'
                and binding['source'] == capture['source'] == 'blender', 'object_order_world_units')
    appended = {'runtime_source_sha256', 'source_status', 'disk_status', 'source_check_scope'}
    base = {name: value for name, value in binding.items() if name not in appended | {
        'source_binding_sha256', 'binding_sha256', 'camera_specification', 'geometry_identity', 'camera_identity',
        'ordered_geometry_sha256'}}
    audit.check(fingerprint(base) == binding['source_binding_sha256'], 'source_binding_digest_preimage')
    complete = {name: value for name, value in binding.items() if name not in appended | {'binding_sha256'}}
    audit.check(fingerprint(complete) == binding['binding_sha256'], 'camera_binding_digest_preimage')
    audit.check(binding['runtime_source_sha256'] == installed['source_sha256']
                and binding['source_status'] == 'loaded_generation' and binding['disk_status'] == 'disk_not_checked'
                and binding['source_check_scope'] == 'bound_generation_identity', 'installed_source_attestation')
    cameras = binding['camera_specification']['views']
    audit.check([pose['name'] for pose in cameras] == PIXELS.ORDER
                and [pose['direction_rational'] for pose in cameras] == PIXELS.DIRECTIONS,
                'published_six_camera_directions')
    audit.check(fingerprint(binding['camera_specification']) == binding['camera_identity'], 'published_camera_identity_preimage')


def region_checks(full, capture, audit):
    reference = full['region_ref']
    selected = reference['source_triangle_indices']
    source_index = next(index for index, mesh in enumerate(capture['meshes']) if mesh['name'] == 'Obj_07')
    source = capture['meshes'][source_index]
    binding = full['binding']
    host = binding['objects'][source_index]
    audit.check(selected == sorted(set(selected)) and selected and all(0 <= index < 6 for index in selected),
                'region_valid_original_source_rows')
    audit.check(reference['schema'] == 'human-eye-source-region-ref-v1'
                and reference['document_epoch'] == binding['document_epoch']
                and reference['host_id'] == host['host_id'] and reference['instance_id'] == host['instance_id'],
                'region_ref_current_host_instance')
    ordered = [dict(host_id=host['host_id'], instance_id=host['instance_id'], vertices=mesh['vertices'], faces=mesh['faces'])
               for host, mesh in zip(binding['objects'], capture['meshes'], strict=True)]
    audit.check(reference['ordered_geometry_sha256'] == binding['ordered_geometry_sha256'] == fingerprint(ordered),
                'region_ref_ordered_geometry_digest')
    unsigned = {name: value for name, value in reference.items() if name != 'region_id'}
    audit.check(reference['region_id'] == 'source-region:' + fingerprint(unsigned), 'region_id_complete_preimage')
    generation = {name: binding['capture_state'][name] for name in ('instance_id', 'epoch', 'revision')}
    audit.check(reference['capture_generation'] == generation, 'region_ref_current_capture_generation')
    vertices = sorted({index for fi in selected for index in source['faces'][fi]})
    region = full['facts']['region']
    audit.check(region['source_triangle_indices'] == selected and region['source_vertex_indices'] == vertices,
                'region_exact_triangle_vertex_sets')
    audit.check(region['triangles_source_vertices'] == [source['faces'][index] for index in selected]
                and region['vertices_world_m'] == [source['vertices'][index] for index in vertices],
                'region_exact_original_rows_and_world_points')
    points = np.asarray([source['vertices'][index] for index in vertices])
    audit.check(region['bbox_min_world_m'] == points.min(axis=0).tolist()
                and region['bbox_max_world_m'] == points.max(axis=0).tolist(), 'selected_region_exact_world_bounds')
    return source_index, selected, vertices


def check_frame(frame, full, capture, source_index, selected, session, audit):
    png = audit.file(frame['image_path'], frame['image_sha256'], session)
    raw = audit.file(frame['arrays_path'], frame['arrays_sha256'], session)
    with np.load(BytesIO(raw), allow_pickle=False) as saved:
        arrays = {name: saved[name] for name in saved.files}
    with Image.open(BytesIO(png)) as image:
        audit.check(image.format == 'PNG' and image.mode == 'RGB' and image.size == (512, 512)
                    and np.array_equal(np.asarray(image), arrays['color']), 'PNG_exact_original_RGB')
    for name, dtype, shape in (('color', 'uint8', (512, 512, 3)), ('depth', 'float64', (512, 512)),
                              ('owners', 'int32', (512, 512)), ('triangle_ids', 'int32', (512, 512)),
                              ('patch_owners', 'int32', (512, 512))):
        value = arrays[name]
        audit.check(value.dtype == np.dtype(dtype) and value.shape == shape, 'frame_dtype_shape/' + name)
        audit.check(frame['arrays'][name] == dict(dtype=dtype, shape=list(shape), nbytes=value.nbytes,
            sha256=hashlib.sha256(value.tobytes()).hexdigest()), 'raw_array_bytes/' + name)
    offsets = np.cumsum([0] + [len(mesh['faces']) for mesh in capture['meshes']], dtype=np.int64)
    ids = np.full(int(offsets[-1]), -1, dtype=np.int32)
    audit.check(np.array_equal(arrays['face_patch_offsets'], offsets)
                and np.array_equal(arrays['face_patch_ids'], ids) and arrays['patch_roi_ids'].tolist() == [],
                'independent_general_frame_empty_rectangle_map')
    ordered = [(tuple(tuple(F(value) for value in point) for point in mesh['vertices']), tuple(tuple(face) for face in mesh['faces']))
               for mesh in capture['meshes']]
    mapping = fingerprint(dict(version=PIXELS.PATCH_SCHEMA, roi_ids=(), ordered_geometry=ordered,
                               face_patch_ids=[[-1] * len(mesh['faces']) for mesh in capture['meshes']]))
    owner_mapping = fingerprint((PIXELS.OWNER_SCHEMA, PIXELS.TRIANGLE_SCOPE, mapping, offsets.tolist()))
    for name, value in (('owner_schema', PIXELS.OWNER_SCHEMA), ('triangle_id_scope', PIXELS.TRIANGLE_SCOPE),
                        ('patch_mapping_version', PIXELS.PATCH_SCHEMA), ('patch_mapping_identity', mapping),
                        ('owner_mapping_identity', owner_mapping)):
        audit.check(frame[name] == arrays[name].item() == value, 'owner_mapping_preimage/' + name)
    binding = full['binding']
    audit.check(frame['host_binding_sha256'] == binding['binding_sha256']
                and frame['source_revision'] == binding['scene_revision']
                and frame['scene_identity'] == binding['geometry_identity']
                and frame['candidate_identity'] == binding['camera_identity'], 'frame_current_geometry_camera_binding')
    audit.check(frame['all_object_count'] == 11 and frame['all_triangle_count'] == 62, 'frame_full_occlusion_denominator')
    audit.check(frame['pose'] == next(pose for pose in binding['camera_specification']['views'] if pose['name'] == frame['view_name']),
                'frame_exact_published_camera_pose')
    frame_preimage = ((frame['scene_identity'], frame['candidate_identity']), PIXELS.OWNER_SCHEMA,
                      owner_mapping, frame['view_name'], 1, frame['image_sha256'])
    audit.check(frame['frame_identity'] == fingerprint(frame_preimage), 'original_frame_identity_preimage')
    audit.check(frame['image_ref'] == 'source-region-image:' + fingerprint((full['region_ref']['region_id'],
                frame['frame_identity'], frame['image_sha256'])), 'public_region_image_reference_preimage')
    owners, triangles, patches, depth = [arrays[name] for name in ('owners', 'triangle_ids', 'patch_owners', 'depth')]
    foreground = owners >= 0
    audit.check(np.all(owners >= -1) and np.all(owners < 11) and np.all(triangles >= -1)
                and np.all(triangles < 62) and np.array_equal(triangles >= 0, foreground), 'all_scene_owner_ranges')
    audit.check(np.all(triangles[foreground] >= offsets[owners[foreground]])
                and np.all(triangles[foreground] < offsets[owners[foreground] + 1])
                and np.array_equal(patches[foreground], ids[triangles[foreground]])
                and np.all(patches[~foreground] == -1), 'all_actual_pixels_original_source_ownership')
    audit.check(np.all(np.isposinf(depth[~foreground]))
                and np.all(np.isfinite(depth[foreground]) & (depth[foreground] > 0))
                and np.all(arrays['color'][~foreground] == [18, 22, 30]), 'background_depth_RGB')
    counts = {str(index): int(np.count_nonzero(triangles == offsets[source_index] + index)) for index in selected}
    visible = [index for index in selected if counts[str(index)] > 0]
    unseen = [index for index in selected if counts[str(index)] == 0]
    visibility = full['facts']['visibility']
    selected_mask = np.isin(triangles, offsets[source_index] + np.asarray(selected))
    ys, xs = np.nonzero(selected_mask)
    bounds = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None
    audit.check(visibility['visible_source_triangle_indices'] == visible
                and visibility['unseen_source_triangle_indices'] == unseen
                and visibility['selected_surface_pixels'] == sum(counts.values())
                and visibility['visible_pixel_bounds'] == bounds
                and visibility['image_ref'] == frame['image_ref'], 'actual_selected_visibility_pixels')
    audit.check(visibility['complete_witness'] is None
                and visibility['visibility_scope'] == 'actual_frame_source_triangle_samples'
                and 'complete_surface_visibility' in visibility['unknown'], 'published_visibility_evidence_scope')
    ray = PIXELS.ray_winner_checks(frame, capture, arrays, audit)
    return dict(frame_identity=frame['frame_identity'], image_ref=frame['image_ref'], view_name=frame['view_name'],
        selected_pixel_counts=counts, visible_source_triangle_indices=visible, unseen_source_triangle_indices=unseen,
        independent_all_scene_ray_review=ray, full_selected_surface_visibility_claim=False,
        array_sha256={name: frame['arrays'][name]['sha256'] for name in ('color', 'depth', 'owners', 'triangle_ids', 'patch_owners')})


def measurement_checks(full, capture, source_index, selected, translated, audit):
    result = full['task_result']
    audit.check(result['region_ref'] == full['region_ref'], 'measurement_same_region_ref')
    name = result['reference']['name']
    target = capture['meshes'][source_index]
    reference = next(mesh for mesh in capture['meshes'] if mesh['name'] == name)
    audit.check(name in ('Ref_B', 'Ref_C'), 'fixed_reference_object')
    fact = result['facts']['surface_proximity']
    audit.check(fact['status'] == fact['witness_status'] == fact['direction_status'] == 'measured'
                and fact['semantics'] == 'current_evaluated_triangle_surfaces_world_metres', 'surface_fact_measured_world_metre_semantics')
    value = fact['value']
    expected_squared = dict(Ref_B=F(25, 16), Ref_C=F(137, 16))[name]
    if selected == list(range(6)):
        expected_squared = dict(Ref_B=F(1, 1024), Ref_C=F(2305, 1024))[name]
    if translated and name == 'Ref_B' and selected == list(range(4)):
        expected_squared = F(5, 4)
    distance = value['distance_m']
    independent = math.sqrt(float(expected_squared))
    audit.check(math.isfinite(distance) and abs(distance - independent) <= 1e-9, 'independent_coordinate_bound_distance')
    witness = value['nearest_witness']
    a, b = MATH.vector(witness['a']), MATH.vector(witness['b'])
    delta = MATH.subtract(b, a)
    squared = MATH.dot(delta, delta)
    audit.check(abs(math.sqrt(float(squared)) - independent) <= 1e-9, 'attaining_published_witness_length')
    memberships = []
    for side, point, mesh, rows in [('a', witness['a'], target, selected),
                                    ('b', witness['b'], reference, list(range(len(reference['faces']))))]:
        member = MATH.membership(point, mesh['vertices'], [mesh['faces'][index] for index in rows])
        exact_rows = [rows[index] for index in member['exact_source_triangle_indices']]
        tolerant_rows = [rows[index] for index in member['within_publication_tolerance_source_triangle_indices']]
        audit.check(bool(tolerant_rows), 'published_witness_current_source_membership/' + side)
        reverse = result['source_mapping']['nearest_witness'][side]
        audit.check(reverse['source_triangle_indices'] == exact_rows, 'witness_reverse_original_triangle_rows/' + side)
        exact_vertices = [index for index, vertex in enumerate(mesh['vertices']) if MATH.vector(vertex) == MATH.vector(point)]
        audit.check(reverse['source_vertex_indices'] == exact_vertices, 'witness_reverse_original_vertex_rows/' + side)
        memberships.append(dict(side=side, exact_source_rows=exact_rows, tolerance_source_rows=tolerant_rows,
                                minimum_squared_distance_m2=member['minimum_squared_distance_to_source']))
    direction = np.asarray(witness['direction_a_to_b'], dtype=float)
    audit.check(np.allclose(direction, np.asarray([float(x) for x in delta]) / distance, rtol=0, atol=1e-9),
                'published_source_to_reference_unit_direction')
    mapping = result['source_mapping']['region']
    vertices = sorted({index for fi in selected for index in target['faces'][fi]})
    audit.check(mapping['submesh_to_source_triangle_indices'] == selected
                and mapping['submesh_to_source_vertex_indices'] == vertices, 'prepared_submesh_reverse_original_rows')
    compact = {source: index for index, source in enumerate(vertices)}
    audit.check(mapping['triangles_source_vertices'] == [target['faces'][index] for index in selected]
                and mapping['triangles_submesh_vertices'] == [[compact[vertex] for vertex in target['faces'][index]] for index in selected],
                'prepared_submesh_face_vertex_bijection')
    return dict(reference=name, distance_m=distance, independent_distance_squared_m2=str(expected_squared),
                full_selected_triangle_count=len(selected), witness_source_membership=memberships,
                measured_scope='all_selected_source_triangles', image_visibility_scope='actual_visible_pixels')


def check_session(session, run_binding, call_index=1, translated=False):
    session = Path(session).resolve()
    audit = Audit()
    for path in (Path(__file__), Path(static_preflight.__file__), FRAME_PATH, MATH_PATH,
                 NS / 'fixture/GEOMETRY.json', HERE / 'STATIC_PREFLIGHT.json'):
        audit.file(path)
    installed = audit.read(run_binding)
    for row in installed['source_manifest']:
        audit.file(Path(installed['install_root']) / row['path'], row['sha256'])
    calls = [json.loads(line) for line in audit.file(session / 'PUBLIC_REQUESTS.jsonl').splitlines() if line.strip()]
    call = calls[call_index - 1]
    request = audit.read(call['request_path'], call['request_sha256'], session)
    response = audit.read(call['response_path'], call['response_sha256'], session)
    audit.check(request == audit.read(call['actual_TX_path'], call['actual_TX_sha256'], session)
                and response == audit.read(call['actual_RX_path'], call['actual_RX_sha256'], session), 'original_actual_public_stdio')
    audit.check(response.get('result', {}).get('isError') is False and request['id'] == response['id'], 'actual_public_success')
    args = request['params']['arguments']
    audit.check(request['params']['name'] == 'human_eye_scene_observe' and args['query']['mode'] == 'source_region',
                'actual_public_source_region_entry')
    record = call['producer_archive']
    full = audit.read(record['path'], record['sha256'], session)
    audit.check(call['started_ns'] <= record['started_ns'] <= record['producer_returned_ns'] <= call['closed_ns'], 'same_public_producer_window')
    audit.check(full['read_only'] is True and full['execution_authority'] is False, 'read_only_authority')
    captures, commands = decode_captures(session, installed, audit)
    capture = current_capture(captures, full['binding'], audit)
    compare_geometry(capture, translated, audit)
    binding_checks(capture, full['binding'], installed, audit)
    source_index, selected, vertices = region_checks(full, capture, audit)
    numeric = measurement_checks(full, capture, source_index, selected, translated, audit)
    blocks = response['result']['content']
    public_rows = [json.loads(block['text']) for block in blocks if block['type'] == 'text']
    images = [block for block in blocks if block['type'] == 'image']
    audit.check(len(public_rows) == 1 and public_rows[0]['region_ref'] == full['region_ref'], 'public_self_contained_current_region_ref')
    public = public_rows[0]
    audit.check(public['task_result'] == full['task_result'], 'public_complete_selected_measurement_and_mapping')
    if args.get('response_detail') == 'full':
        audit.check(public['facts'] == full['facts'] and public['binding'] == full['binding'], 'full_source_facts_and_camera_binding')
    else:
        audit.check(public['schema'] == 'source-region-brief-v1'
                    and public['region'] == full['facts']['region'] and public['visibility'] == full['facts']['visibility']
                    and public['measurement_scope'] == full['task_result']['measurement_scope'], 'default_brief_complete_scope_numeric_visibility')
    if 'region_ref' in args['query']:
        audit.check(args['query']['region_ref'] == full['region_ref'], 'reused_returned_region_identity')
    frames = full['frames']
    audit.check(len(frames) == len(images) == int(args['include_image']), 'native_delivered_image_count')
    frame_reviews = []
    if args.get('response_detail') != 'full':
        audit.check(len(public['images']) == len(frames)
                    and all(public_image['image_ref'] == frame['image_ref'] and public_image['image_block_index'] == index
                            for index, (public_image, frame) in enumerate(zip(public['images'], frames, strict=True), 1)),
                    'brief_native_image_block_reference_indices')
    for frame, image in zip(frames, images, strict=True):
        audit.check(image['mimeType'] == 'image/png'
                    and base64.b64decode(image['data'], validate=True) == audit.file(frame['image_path'], frame['image_sha256'], session),
                    'original_public_native_PNG_bytes')
        frame_reviews.append(check_frame(frame, full, capture, source_index, selected, session, audit))
    return dict(schema='m4-m5-source-region-saved-review-v1', passed=True, session=str(session), call_index=call_index,
        region_ref=full['region_ref'], source_region_triangle_indices=selected, source_region_vertex_indices=vertices,
        numeric=numeric, frames=frame_reviews, original_wire_commands=commands,
        author_association='The fixture and this product-independent saved oracle share an author. Root source review is separate.',
        geometric_full_selected_surface_visible_claim=False, new_live_Blender=0, new_raster=0, new_model=0,
        checks=audit.checks, input_pins=list(audit.pins.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', required=True)
    parser.add_argument('--run-binding', required=True)
    parser.add_argument('--call-index', type=int, default=1)
    parser.add_argument('--translated', action='store_true')
    parser.add_argument('--output', required=True)
    options = parser.parse_args()
    try:
        result = check_session(options.session, options.run_binding, options.call_index, options.translated)
    except Exception as error:
        result = dict(schema='m4-m5-source-region-saved-review-v1', passed=False,
            error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc(),
            session=options.session, call_index=options.call_index, new_live_Blender=0, new_raster=0, new_model=0)
    Path(options.output).write_text(json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(passed=result['passed'], output=str(Path(options.output).resolve()), error=result.get('error'))))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

"""Independent M5 current-source, published-number and saved-pixel audit.

Only original files from closed owned sessions are read. This module contains
no observation, Blender, renderer, product distance-kernel or model invocation.
"""

import argparse
import ast
import base64
import copy
from fractions import Fraction as F
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import zlib


HERE = Path(__file__).resolve().parent
PRIOR = HERE.with_name('m4_target_acquisition_002')
QUALITY_SHA = '09042774d0a33c9ddf215d68c6ea696859f22d2e975afff30ffb773874a040b6'
ASSET_SHA = '2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164'


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def dependencies():
    require(sha(PRIOR / 'quality_saved.py') == QUALITY_SHA, 'prior_quality_primitive_changed')
    quality = load(PRIOR / 'quality_saved.py', '_m5_accepted_quality')
    q, metrics = quality.dependencies()
    oracle = load(HERE / 'oracle.py', '_m5_independent_oracle')
    source = load(HERE / 'source_contract_r2.py', '_m5_public_source_r2')
    return quality, q, metrics, oracle, source


def asset_manifest(oracle, translation=F(0)):
    rows = sorted(oracle.frozen_objects().values(), key=lambda row: row['reference_object_id'])
    objects = []
    for index, row in enumerate(rows):
        points = [[float(F(value)) for value in point] for point in row['world_vertices_m']]
        if row['name'] == 'M4_Far_00':
            points = [[float(F(point[0])+translation), point[1], point[2]] for point in points]
        objects.append({'asset_key': 'main/' + row['name'], 'source_order': index,
                        'object_id': row['reference_object_id'], 'object_name': row['name'],
                        'vertices_world': points, 'triangles': row['triangles']})
    return {'asset_sha256': ASSET_SHA, 'objects': objects, 'target_asset_key': 'main/M4_Far_00',
            'source_frame': {'frame': 1, 'subframe': 0.0, 'scale_length': 1.0}}


def decode_original_wire(slot, build, manifest):
    """Independently expand current original packets without trusting exports."""
    resources, captures, materials, steps = {}, [], [], []
    expected_source = {row['path']: row['sha256'] for row in build['source_manifest']}
    expected_geometry = {row['object_id']: row for row in manifest['objects']}
    loaded_host = None
    for directory in sorted((slot / 'native/WIRE').glob('[0-9]*')):
        request_path, response_path = directory / 'REQUEST.bin', directory / 'RESPONSE.bin'
        request, response = read(request_path), read(response_path)
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
            raw = zlib.decompress(base64.b64decode(ast.literal_eval(expression.args[0].args[0]), validate=True))
            relative = Path(ast.literal_eval(node.args[1])).relative_to(Path(build['install_root'])).as_posix()
            digest = hashlib.sha256(raw).hexdigest()
            require(expected_source.get(relative) == digest, 'actual_loaded_product_source_changed')
            materials.append({'wire_request': str(request_path), 'path': relative, 'bytes': len(raw), 'sha256': digest})
            if relative == 'human_eye_plugin/blender_host.py':
                loaded_host = digest
        matched = re.search(r'_request = _json.loads\((.+)\)\n', code)
        if matched is None:
            continue
        command = json.loads(ast.literal_eval(matched.group(1)))
        lines = [line for line in response.get('result', {}).get('result', '').splitlines()
                 if line.startswith('HUMAN_EYE_BLENDER_MCP:')]
        require(response.get('status') == 'success' and len(lines) == 1, 'actual_host_packet_unsuccessful')
        packet = json.loads(lines[0].split(':', 1)[1])
        require(packet.get('error') is None, 'actual_host_packet_error')
        value = packet.get('result')
        if type(value) is not dict:
            continue
        for resource in value.get('resources', []):
            resources[(resource['id'], resource['revision'])] = resource
        capture = copy.deepcopy(value.get('capture', value))
        step = {'sequence': int(directory.name), 'command': command,
                'request': str(request_path), 'response': str(response_path),
                'request_sha256': sha(request_path), 'response_sha256': sha(response_path)}
        steps.append(step)
        if not capture.get('meshes'):
            continue
        world_mappings = []
        for mesh in capture['meshes']:
            reference = mesh.pop('_scene_resource', None)
            if reference is not None:
                resource = resources[(reference['id'], reference['revision'])]
                matrix, scale = reference['matrix'], reference['scale']
                mesh.update(vertices=[[(((matrix[axis][0]*point[0]+matrix[axis][1]*point[1])
                                           +matrix[axis][2]*point[2])+matrix[axis][3])*scale
                                       for axis in range(3)] for point in resource['vertices_local']],
                            faces=resource['faces'], edges=resource['edges'])
                world_mappings.append({'object_id': mesh['object_id'], 'resource_id': reference['id'],
                                       'resource_revision': reference['revision'], 'matrix': matrix, 'scale': scale,
                                       'local_vertices_sha256': hashlib.sha256(json.dumps(resource['vertices_local'], separators=(',', ':')).encode()).hexdigest()})
            expected = expected_geometry.get(mesh['object_id'])
            require(expected is not None and mesh['name'] == expected['object_name'], 'actual_source_object_outside_fixed_asset')
            require(mesh['vertices'] == expected['vertices_world'] and mesh['faces'] == expected['triangles'],
                    'actual_current_world_points_or_source_face_order')
        captures.append({'capture': capture, 'step': step, 'world_mappings': world_mappings})
    require(loaded_host == expected_source['human_eye_plugin/blender_host.py'], 'current_loaded_host_not_proved')
    return captures, materials, steps, loaded_host


def public_table(value):
    if value is None:
        return []
    columns = value['columns']
    require(len(columns) == len(set(columns)) and all(len(row) == len(columns) for row in value['rows']), 'public_table_shape')
    return [dict(zip(columns, row)) for row in value['rows']]


def validate_public_observation(public, full):
    if public.get('schema') != 'active-observation-brief-v5':
        require(public.get('facts') == full['facts'], 'full_public_observation_facts_changed')
        require(public.get('frames') == full['frames'], 'full_public_frames_changed')
        return 'full'
    require(public.get('index_base') == 0, 'brief_index_base')
    regions = public_table(public.get('regions'))
    source_rows = {row['roi_id']: row for row in full['facts']['scope']['patch_support']['regions']}
    full_regions = {row['roi_id']: row for row in full['facts']['regions']}
    require(len(regions) == len(full_regions) and {row['roi_id'] for row in regions} == set(full_regions), 'brief_region_bijection')
    for row in regions:
        require(all(value == full_regions[row['roi_id']][key] for key, value in row.items() if key in full_regions[row['roi_id']]), 'brief_region_fact')
        faces = [index for low, high in row['source_triangle_index_ranges'] for index in range(low, high+1)]
        require(faces == source_rows[row['roi_id']]['triangle_indices'] and row['triangle_count'] == len(faces), 'brief_region_source_faces')
    pixels = public_table(public.get('pixels'))
    expected = [row for observation in full['facts']['observations'] for row in observation['pixel_rows']]
    require(len(pixels) == len(expected), 'brief_pixels_bijection')
    for row, original in zip(pixels, expected):
        require(all(value == original[key] for key, value in row.items() if key in original), 'brief_pixel_fact')
    evidence = {row['roi_id']: row for row in full['facts']['region_evidence']}
    for index, row in enumerate(regions):
        witness = evidence[row['roi_id']]['complete_witness']
        pixel_index = row['complete_witness_pixel_index']
        if witness is None:
            require(pixel_index is None, 'brief_invented_complete_witness')
        else:
            require(type(pixel_index) is int and 0 <= pixel_index < len(pixels) and pixels[pixel_index]['region_index'] == index,
                    'brief_complete_witness_pixel_binding')
    require(public['inspection'] == full['facts']['inspection'], 'brief_inspection')
    for key in ('binding_sha256', 'source_binding_sha256', 'scene_revision', 'geometry_identity', 'camera_identity'):
        require(public['binding'][key] == full['binding'][key], 'brief_source_binding_' + key)
    images = public_table(public.get('images'))
    require(len(images) == len(full['frames']), 'brief_frame_count')
    for row, frame in zip(images, full['frames']):
        require(all(row[key] == frame[key] for key in ('view_name', 'image_ref', 'image_sha256', 'patch_mapping_identity')), 'brief_frame_provenance')
    return 'brief'


def validate_numeric(fact, target, reference, oracle, shift=F(0), missing=False):
    require(fact.get('status') == 'measured', 'surface_proximity_not_measured')
    require(fact.get('semantics') == 'current_evaluated_triangle_surfaces_world_metres', 'surface_proximity_semantics')
    require(fact.get('method') == 'exact_binary64_triangle_surface_hulls_v3', 'published_surface_method')
    value = fact.get('value', {})
    topology = []
    for mesh in (target, reference):
        edges = {}
        for face in mesh['faces']:
            for start, end in zip(face, face[1:] + face[:1]):
                key = tuple(sorted((start, end)))
                edges[key] = edges.get(key, 0) + 1
        topology.append({'boundary_edge_count': sum(count == 1 for count in edges.values()),
                         'nonmanifold_edge_count': sum(count > 2 for count in edges.values())})
    require(value.get('topology') == topology, 'independent_source_topology_counts')
    distance = value.get('distance_m')
    require(type(distance) in (int, float) and math.isfinite(distance), 'surface_distance_finite')
    state = read(HERE / 'scoring/STATE_TRUTH.json')['states']['matrix_changed' if shift else 'initial']
    expected = state['missing_Far11_distance_binary64_m'] if missing else state['main_distance_binary64_m']
    require(float(distance) == expected, 'independent_global_minimum_distance')
    witness = value.get('nearest_witness')
    require(type(witness) is dict, 'nearest_witness_must_be_nested_under_value')
    left = oracle.membership(witness['a'], target['vertices'], target['faces'])
    right = oracle.membership(witness['b'], reference['vertices'], reference['faces'])
    require(left['within_publication_tolerance_source_triangle_indices'] and right['within_publication_tolerance_source_triangle_indices'], 'witness_outside_actual_current_source')
    delta = oracle.subtract(oracle.vector(witness['b']), oracle.vector(witness['a']))
    squared = oracle.dot(delta, delta)
    tolerance = oracle.PUBLICATION_TOLERANCE_M
    require((F(expected)-tolerance)**2 <= squared <= (F(expected)+tolerance)**2, 'witness_length_not_nearest')
    direction = witness.get('direction_a_to_b')
    require(fact.get('witness_status') == 'measured' and fact.get('direction_status') == 'measured', 'witness_status')
    if not missing:
        require(oracle.vector(direction) == (-1, 0, 0), 'surface_A_to_B_direction')
    else:
        expected_delta = [float(F(value)) for value in oracle.subtract(oracle.vector(state['missing_Far11_one_witness']['b']), oracle.vector(state['missing_Far11_one_witness']['a']))]
        require(len(direction) == 3 and all(abs(float(actual)-wanted/expected) <= 1e-15 for actual, wanted in zip(direction, expected_delta)), 'missing_surface_A_to_B_direction')
    return {'passed_checked_scope': True, 'distance_m': distance, 'independent_distance_binary64_m': expected,
            'published_witness_squared_length_exact_m2': str(squared), 'nearest_witness': witness,
            'witness_a_current_source_membership': left, 'witness_b_current_source_membership': right,
            'same_particular_equal_distance_pair_required': False}


def audit_slot(slot, arm, translation=F(0), missing=False):
    slot = Path(slot).resolve()
    quality, q, metrics, oracle, source = dependencies()
    result = read(slot / 'RESULT.json')
    publication = read(slot / 'PUBLICATION.json')
    require(not result['errors'] and result['passed_before_publication'] and publication['passed_transport_scope'], 'closed_owned_session_failed')
    build = read(result['binding_path'])
    require(sha(result['binding_path']) == result['binding_sha256'] and result['source_sha256'] == build['source_sha256'], 'slot_install_binding')
    identity = read(slot / 'INITIALIZE.json')['result']['_meta']['human_eye']
    require(identity['source_sha256'] == result['source_sha256'] and identity['source_kind'] == 'installed_distribution', 'actual_runtime_source')
    require(result['asset_sha256'] == ASSET_SHA, 'frozen_asset_source')
    manifest = asset_manifest(oracle, translation)
    captures, materials, steps, loaded_host = decode_original_wire(slot, build, manifest)
    proof = {'expected_source_sha256': result['source_sha256'], 'expected_host_source_sha256': loaded_host,
             'actual_runtime_identity': identity, 'actual_loaded_host_sha256': loaded_host, 'material_pins': materials}
    require(loaded_host == next(row['sha256'] for row in build['source_manifest'] if row['path'] == 'human_eye_plugin/blender_host.py'), 'loaded_host_manifest')
    q.validate_source_proof(proof)
    sys.path.insert(0, build['dependency_root'])
    import numpy as np
    from PIL import Image
    request_rows = result['requests']
    require(len(request_rows) == (2 if arm == 'A' else 1), 'registered_public_request_count')
    reviews, arrays, task_review = [], [], None
    for request_row in request_rows:
        public = read(request_row['public_path'])
        response = request_row['response']
        require(response.get('result', {}).get('isError') is False, 'public_product_error')
        texts = [json.loads(block['text']) for block in response['result']['content'] if block.get('type') == 'text']
        require(texts == [public], 'actual_public_text_delivery')
        producer_pin = request_row['producer']
        require(sha(producer_pin['path']) == producer_pin['sha256'], 'same_producer_full_pin')
        full = read(producer_pin['path'])
        if request_row['request']['params']['arguments']['query']['mode'] != 'active_observation':
            require(public == full, 'ordinary_task_public_full_changed')
            task_review = audit_task(full, captures, None, None, oracle, source, translation, missing)
            continue
        current = []
        for capture_row in captures:
            if capture_row['capture'].get('capture_scope') != 'target_observation_meshes':
                continue
            reconstructed = q.reconstruct_target_binding(capture_row['capture'])
            if reconstructed['binding_sha256'] == full['binding']['binding_sha256']:
                current.append((capture_row, reconstructed))
        require(current and all(item[0]['capture'] == current[0][0]['capture'] for item in current), 'producer_parent_capture_binding')
        capture_row, binding = current[0]
        capture = capture_row['capture']
        require(all(full['binding'].get(key) == value for key, value in binding.items()), 'producer_full_source_binding')
        mapping = q.validate_object_mapping(capture, binding, manifest, proof)
        detail = validate_public_observation(public, full)
        facts = full['facts']
        sources = {row['roi_id']: row for row in facts['scope']['patch_support']['regions']}
        require(len(facts['regions']) == len(sources) == 2, 'entire_target_region_count')
        kinds = {}
        for region in facts['regions']:
            row = sources[region['roi_id']]
            faces = row['triangle_indices']
            kind = 'vertical' if faces == list(range(512)) else 'horizontal' if faces == [512, 513] else None
            require(kind is not None and kind not in kinds.values(), 'whole_original_source_region_set')
            kinds[region['roi_id']] = kind
            q.validate_region_geometry(region, faces, capture['meshes'][row['object_index']])
            require(region['front_direction_world'] == ([-1, 0, 0] if kind == 'vertical' else [0, 0, 1]), 'region_true_front')
        analytic = read(PRIOR / 'ANALYTIC_REVIEW.json')
        classifications = full['target_view_classifications']
        for roi, kind in kinds.items():
            expected = analytic['horizontal_main_geometric_classifications'] if kind == 'horizontal' else dict(analytic['vertical_main_geometric_classifications'])
            if kind == 'vertical' and translation:
                expected['LEFT'] = 'complete'
            for view, status in expected.items():
                actual = classifications[view][roi]
                require(actual['status'] == status and actual['complete'] is (status == 'complete'), 'independent_six_view_geometric_classification')
        require(len(full['frames']) == len(facts['observations']), 'actual_frame_observation_bijection')
        images = [block for block in response['result']['content'] if block.get('type') == 'image']
        require(len(images) == len(full['frames']), 'actual_MCP_image_count')
        frames = []
        for frame, observation, image in zip(full['frames'], facts['observations'], images):
            review, normalized = quality.check_frame(frame, observation, image, capture, mapping, sources,
                {row['roi_id']: row['front_direction_world'] for row in facts['regions']}, q, metrics, np, Image)
            frames.append(review)
            arrays.append(normalized)
        evidence = {row['roi_id']: row for row in facts['region_evidence']}
        region_reviews = []
        covered = 0
        for region in facts['regions']:
            roi = region['roi_id']
            witness = evidence[roi]['complete_witness']
            if witness is not None:
                observation = next(row for row in facts['observations'] if row['view_name'] == witness['view_name'])
                pixel = observation['pixel_rows'][witness['pixel_row_index']]
                require(pixel['roi_id'] == roi and pixel['readable'] is True and classifications[witness['view_name']][roi]['complete'] is True, 'actual_readable_complete_witness')
                require(region['status'] == 'covered', 'covered_region_status')
                covered += 1
            else:
                require(region['status'] == 'unknown', 'unknown_region_status')
                if not translation:
                    require(kinds[roi] == 'vertical' and evidence[roi]['unobserved_reason'] == 'positive_area_occlusion_all_front_views', 'initial_unknown_reason')
            region_reviews.append({'kind': kinds[roi], 'roi_id': roi, 'source_triangle_indices': sources[roi]['triangle_indices'],
                                   'status': region['status'], 'complete_witness': witness,
                                   'unobserved_reason': evidence[roi]['unobserved_reason']})
        counts = facts['inspection']['counts']
        require(counts['supported'] == 2 and counts['covered'] == covered and counts['unobserved'] == 2-covered, 'inspection_count_truth')
        if not translation:
            require(covered == 1, 'initial_main_2_support_1_complete_1_unknown')
        if arm == 'B':
            require(public.get('task_result') == full.get('task_result') and type(public.get('task_result')) is dict, 'actual_public_task_result_in_brief_and_full')
            task_review = audit_task(public['task_result'], captures, binding, capture, oracle, source, translation, missing)
        reviews.append({'public_detail': detail, 'public_path': request_row['public_path'],
                        'public_sha256': sha(request_row['public_path']), 'producer_sha256': producer_pin['sha256'],
                        'binding_sha256': binding['binding_sha256'], 'source_binding_sha256': binding['source_binding_sha256'],
                        'capture_state': capture['capture_state'], 'counts': counts, 'regions': region_reviews,
                        'all_six_classifications': classifications, 'frames': frames,
                        'view_sequence': [frame['view_name'] for frame in full['frames']],
                        'observation_parent_scope_preserved': capture['capture_scope'] == 'target_observation_meshes'})
    require(len(reviews) == 1 and task_review is not None, 'whole_slot_observe_and_measure_present')
    pins = [slot / filename for filename in ('RESULT.json', 'PUBLICATION.json', 'INITIALIZE.json', 'SAVED_WIRE.json', 'audit.jsonl')]
    pins += [Path(row['producer']['path']) for row in request_rows]
    pins += [Path(row['public_path']) for row in request_rows]
    pins += [Path(step[key]) for step in steps for key in ('request', 'response')]
    summary = {'schema': 'm5-actual-source-pixel-numeric-review-v1', 'passed_checked_scope': True,
               'slot': str(slot), 'arm': arm, 'source_sha256': result['source_sha256'], 'loaded_host_sha256': loaded_host,
               'observations': reviews, 'task': task_review, 'actual_product_packet_count': len(steps),
               'source_materials': materials, 'input_pins': [{'path': str(path), 'sha256': sha(path)} for path in pins],
               'checker_sha256': sha(Path(__file__)), 'new_actual_calls': 0, 'new_rasters': 0, 'new_models': 0}
    return summary, arrays


def audit_task(task, captures, parent_binding, parent_capture, oracle, source, translation, missing):
    require(task.get('schema_version') == 'task-query-v3', 'task_public_schema')
    require(task.get('pair_order') == 'A_to_B' and task.get('unit') == 'm'
            and task.get('coordinate_frame') == 'world' and task.get('execution_authority') is False,
            'read_only_world_metre_ordered_pair_task')
    require(set(task['facts']) == {'surface_proximity'}, 'registered_fact_set')
    bindings = task['binding']['objects']
    expected_names = ['M4_Far_00', 'M4_Far_11' if missing else 'M4_Near']
    meshes = {}
    actual_supplements = []
    if parent_capture is not None:
        meshes.update({mesh['object_id']: mesh for mesh in parent_capture['meshes']})
    else:
        matches = [row['capture'] for row in captures if row['capture'].get('capture_scope') == 'selected_objects']
        require(len(matches) == 1, 'ordinary_task_actual_capture')
        actual = matches[0]
        require(task['binding']['scene_revision'] == actual['revision']
                and task['binding']['capture_scope'] == actual['capture_scope']
                and task['binding']['source'] == actual['source'], 'ordinary_task_current_capture_binding')
        require(bindings == actual['task_selection']['bindings'], 'ordinary_task_current_selector_binding')
        meshes.update({mesh['object_id']: mesh for mesh in actual['meshes']})
    wanted = [row['object_id'] for row in bindings]
    missing_ids = set(wanted)-set(meshes)
    if missing_ids:
        matches = [row['capture'] for row in captures if set(mesh['object_id'] for mesh in row['capture']['meshes']) == missing_ids]
        require(len(matches) == 1, 'exact_missing_actual_capture')
        actual_supplements = matches
        meshes.update({mesh['object_id']: mesh for mesh in matches[0]['meshes']})
    require([meshes[identity]['name'] for identity in wanted] == expected_names, 'ordered_whole_object_pair')
    numeric = validate_numeric(task['facts']['surface_proximity'], meshes[wanted[0]], meshes[wanted[1]], oracle, translation, missing)
    binding_review = None
    if parent_capture is not None:
        binding_review = source.validate_source(task['binding']['observation_source'], parent_binding, parent_capture, bindings, actual_supplements)
    else:
        binding_review = {'schema': 'm5-ordinary-task-capture-binding-review-v1',
                          'scene_revision': actual['revision'], 'capture_scope': actual['capture_scope'],
                          'capture_state': actual['capture_state'],
                          'document_epoch': actual['host_identity']['document_epoch'],
                          'current_object_instances': actual['host_identity']['object_instances'],
                          'source_face_order_validated_from_actual_wire': True}
    return {'public_schema': task['schema_version'], 'numeric': numeric, 'source_binding': binding_review,
            'pair_object_ids': wanted, 'pair_names': expected_names,
            'measurement_scope': 'whole_objects', 'source_triangle_counts': [len(meshes[identity]['faces']) for identity in wanted]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slot', required=True, type=Path)
    parser.add_argument('--arm', required=True, choices=('A', 'B'))
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    summary, _ = audit_slot(args.slot, args.arm)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(summary, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': summary['passed_checked_scope'], 'arm': args.arm,
                      'output_sha256': sha(args.output)}))

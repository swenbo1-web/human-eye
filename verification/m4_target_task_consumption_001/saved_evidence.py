"""Validate current owned source packets and actual saved frames, without rendering."""

import ast
import base64
import copy
from fractions import Fraction as F
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import zlib


HERE = Path(__file__).resolve().parent
PRODUCT = '776b0f0914e116fece16d2b3875ee16ffebf4896a7e394861287ffaa6fe025be'
ASSET = '2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164'
DEVICE = '349120c56ef51295bb2d40f49e1c7031cd5ea09712f3b80cedcf1fad1a664337'
PRIOR = HERE.with_name('m4_target_acquisition_002')
QUALITY_SHA = '09042774d0a33c9ddf215d68c6ea696859f22d2e975afff30ffb773874a040b6'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def table(value):
    if value is None:
        return []
    columns, rows = value['columns'], value['rows']
    if len(set(columns)) != len(columns) or any(len(row) != len(columns) for row in rows):
        raise ValueError('public_table_shape')
    return [dict(zip(columns, row)) for row in rows]


def primitives():
    if sha(PRIOR / 'quality_saved.py') != QUALITY_SHA:
        raise ValueError('accepted_quality_primitive_changed')
    quality = load(PRIOR / 'quality_saved.py', '_consume_accepted_quality')
    q, metrics = quality.dependencies()
    return quality, q, metrics


def asset_manifest():
    frozen = read(HERE / 'reference/FROZEN_GEOMETRY.json')
    if sha(HERE / 'reference/FROZEN_GEOMETRY.json') != 'decdcc1532f31ceb5c75203705ba5b533520f7a525fa8c6ea0391ba3a1fa36da':
        raise ValueError('frozen_geometry_changed')
    objects = []
    for index, row in enumerate(sorted(frozen['objects'], key=lambda row: row['reference_object_id'])):
        objects.append({'asset_key': 'main/' + row['name'], 'source_order': index,
                        'object_id': row['reference_object_id'], 'object_name': row['name'],
                        'vertices_world': [[float(F(value)) for value in point] for point in row['world_vertices_m']],
                        'triangles': row['triangles']})
    return {'asset_sha256': ASSET, 'objects': objects, 'target_asset_key': 'main/M4_Far_00',
            'source_frame': {'frame': 1, 'subframe': 0.0, 'scale_length': 1.0}}


def wire_records(runtime):
    records = []
    for path in sorted((runtime / 'native/WIRE').glob('*/REQUEST.bin')):
        response_path = path.with_name('RESPONSE.bin')
        records.append({'request_path': path, 'response_path': response_path,
                        'request': read(path), 'response': read(response_path)})
    return records


def product_captures(records, binding, manifest, q):
    pins = {row['path']: row['sha256'] for row in binding['source_manifest']}
    by_id = {row['object_id']: row for row in manifest['objects']}
    resources, captures, materials = {}, [], []
    host_sha = None
    for record in records:
        request, response = record['request'], record['response']
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
            blob = zlib.decompress(base64.b64decode(compressed, validate=True))
            relative = Path(ast.literal_eval(node.args[1])).relative_to(Path(binding['install_root'])).as_posix()
            digest = hashlib.sha256(blob).hexdigest()
            if pins[relative] != digest:
                raise ValueError('actual_wire_loaded_product_changed')
            materials.append({'wire_request': str(record['request_path']), 'path': relative,
                              'bytes': len(blob), 'sha256': digest})
            if relative == 'human_eye_plugin/blender_host.py':
                host_sha = digest
        command_text = re.search(r'_request = _json.loads\((.+)\)\n', code)
        if command_text is None or response.get('status') != 'success':
            continue
        command = json.loads(ast.literal_eval(command_text.group(1)))
        stdout = response['result']['result']
        marked = [line for line in stdout.splitlines() if line.startswith('HUMAN_EYE_BLENDER_MCP:')]
        if len(marked) != 1:
            raise ValueError('actual_product_wire_marker')
        packet = json.loads(marked[0].split(':', 1)[1]).get('result')
        if type(packet) is not dict:
            continue
        for resource in packet.get('resources', []):
            resources[(resource['id'], resource['revision'])] = resource
        capture = copy.deepcopy(packet.get('capture', packet))
        if not capture.get('meshes'):
            continue
        for mesh in capture['meshes']:
            expected = by_id[mesh['object_id']]
            reference = mesh.pop('_scene_resource', None)
            if reference is not None:
                resource = resources[(reference['id'], reference['revision'])]
                matrix, scale = reference['matrix'], reference['scale']
                if matrix != [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]] or scale != 1:
                    raise ValueError('fixed_identity_world_mapping_changed')
                mesh.update(vertices=[[sum(matrix[r][k]*point[k] for k in range(3))+matrix[r][3]
                                       for r in range(3)] for point in resource['vertices_local']],
                            faces=resource['faces'], edges=resource['edges'])
            if (mesh['name'] != expected['object_name'] or mesh['vertices'] != expected['vertices_world']
                    or mesh['faces'] != expected['triangles']):
                raise ValueError('actual_product_source_points_or_face_order_changed')
        if command['command'] == 'capture_active_observation':
            actual_binding = q.reconstruct_target_binding(capture)
            captures.append({'capture': capture, 'binding': actual_binding, 'request_path': str(record['request_path']),
                             'response_path': str(record['response_path'])})
    if captures and host_sha != pins['human_eye_plugin/blender_host.py']:
        raise ValueError('current_loaded_host_not_proved')
    return captures, materials, host_sha


def validate_brief(brief, full, aliases, truth):
    if brief.get('schema') != 'active-observation-brief-v5' or brief.get('index_base') != 0:
        raise ValueError('default_brief_v5_required')
    regions = table(brief.get('regions'))
    expected = {row['roi_id']: row for row in full['facts']['regions']}
    sources = {row['roi_id']: row for row in full['facts']['scope']['patch_support']['regions']}
    if len(regions) != len(expected) or {row['roi_id'] for row in regions} != set(expected):
        raise ValueError('public_brief_region_bijection')
    pixels = table(brief.get('pixels'))
    for region in regions:
        original = expected[region['roi_id']]
        for key, value in region.items():
            if key in original and value != original[key]:
                raise ValueError('public_brief_region_field:' + key)
        faces = []
        for low, high in region['source_triangle_index_ranges']:
            faces.extend(range(low, high+1))
        if faces != sources[region['roi_id']]['triangle_indices'] or region['triangle_count'] != len(faces):
            raise ValueError('public_brief_source_face_ranges')
        if aliases[region['roi_id']] not in {row['id'] for row in truth['regions']}:
            raise ValueError('public_brief_region_not_independent')
        witness = next(row['complete_witness'] for row in full['facts']['region_evidence'] if row['roi_id'] == region['roi_id'])
        index = region['complete_witness_pixel_index']
        if witness is None:
            if index is not None:
                raise ValueError('public_brief_invented_witness')
        elif (type(index) is not int or not 0 <= index < len(pixels)
              or pixels[index]['region_index'] != regions.index(region)):
            raise ValueError('public_brief_witness_pixel_binding')
    full_pixels = [row for observation in full['facts']['observations'] for row in observation['pixel_rows']]
    if len(pixels) != len(full_pixels):
        raise ValueError('public_brief_pixel_count')
    for actual, expected_pixel in zip(pixels, full_pixels):
        for key, value in actual.items():
            if key in expected_pixel and value != expected_pixel[key]:
                raise ValueError('public_brief_pixel_field:' + key)
    if brief['inspection'] != full['facts']['inspection']:
        raise ValueError('public_brief_inspection')
    full_binding = full['binding']
    for key in ('binding_sha256', 'source_binding_sha256', 'scene_revision', 'geometry_identity', 'camera_identity'):
        if brief['binding'][key] != full_binding[key]:
            raise ValueError('public_brief_source_binding:' + key)
    images = table(brief.get('images'))
    if len(images) != len(full['frames']):
        raise ValueError('public_brief_frame_count')
    for actual, frame in zip(images, full['frames']):
        if any(actual[key] != frame[key] for key in ('view_name', 'image_ref', 'image_sha256', 'patch_mapping_identity')):
            raise ValueError('public_brief_frame_provenance')


def evaluate_slot(slot_root, truth):
    slot_root = Path(slot_root).resolve()
    index_paths = list(slot_root.rglob('SAVED_EVIDENCE.json'))
    if len(index_paths) != 1:
        raise ValueError('one_actual_runtime_evidence_index')
    index_path = index_paths[0]
    runtime = index_path.parent
    saved = read(index_path)
    if saved['schema'] != 'live-target-task-saved-evidence-v1' or saved['product_source_sha256'] != PRODUCT or saved['asset_sha256'] != ASSET:
        raise ValueError('current_runtime_source_or_asset')
    device = saved['device']
    if sha(device['path']) != device['sha256'] or device['sha256'] != DEVICE:
        raise ValueError('fixed_camera_device_changed')
    cameras = read(device['path'])
    binding = read(HERE / 'PRODUCT_RUN_BINDING.json')
    for row in binding['source_manifest']:
        if sha(Path(binding['install_root']) / row['path']) != row['sha256']:
            raise ValueError('fixed_product_source_changed')
    quality, q, metrics = primitives()
    sys.path.insert(0, binding['dependency_root'])
    sys.path.insert(0, 'D:/he_anchor_001/venv/Lib/site-packages')
    import numpy as np
    from PIL import Image
    pixel = load(HERE / 'pixel_oracle.py', '_consume_independent_pixels')
    manifest = asset_manifest()
    expected_objects = {row['object_name']: row for row in manifest['objects']}
    native_config = read(runtime / 'native/SESSION.json')
    initial_config = read(runtime / 'native/CONFIG.json')
    ready = read(runtime / 'native/READY.json')
    if (any(native_config[key] != value for key, value in initial_config.items())
            or native_config['pid'] != ready['pid']):
        raise ValueError('owned_native_session_ready_binding')
    if native_config['asset_sha256'] != ASSET or sha(native_config['asset']) != ASSET or sha(native_config['asset_copy']) != ASSET:
        raise ValueError('actual_owned_asset_changed')
    records = wire_records(runtime)
    source_refs, source_reviews = set(), []
    for row in saved['sources']:
        path = Path(row['path']).resolve()
        if not path.is_relative_to(runtime) or sha(path) != row['sha256']:
            raise ValueError('raw_source_file_pin')
        actual = read(path)
        source_refs.add(actual['source_ref'])
        packet = copy.deepcopy(actual)
        packet.pop('source_ref')
        packet['source'].pop('asset_sha256')
        matching = []
        for record in records:
            response = record['response']
            if response.get('status') == 'success':
                lines = response.get('result', {}).get('result', '').splitlines()
                matching.extend(record for line in lines if line.startswith('CURRENT_RAW_SCENE:')
                                and json.loads(line.split(':', 1)[1]) == packet)
        if not matching or actual['source']['pid'] != native_config['pid']:
            raise ValueError('raw_source_not_current_actual_wire')
        if {key: actual['source'][key] for key in ('frame', 'subframe', 'scale_length')} != manifest['source_frame']:
            raise ValueError('raw_source_saved_frame_changed')
        if [obj['object_id'] for obj in actual['objects']] != sorted(obj['object_id'] for obj in actual['objects']):
            raise ValueError('raw_source_original_object_order')
        for obj in actual['objects']:
            expected = expected_objects[obj['name']]
            if (obj['vertices'] != expected['vertices_world'] or obj['triangles'] != expected['triangles']
                    or obj['object_id'] != expected['object_id'] or not obj['instance_id']):
                raise ValueError('raw_source_points_faces_or_instance')
        source_reviews.append({'ref': actual['source_ref'], 'sha256': row['sha256'],
                               'current_instance': actual['source']['instance_id'], 'pid': actual['source']['pid'],
                               'object_names': [obj['name'] for obj in actual['objects']],
                               'wire_responses': [str(record['response_path']) for record in matching]})
    captures, materials, loaded_host = product_captures(records, binding, manifest, q)
    full_index = Path(saved['product_full_index']) if saved['product_full_index'] is not None else None
    full_entries = [json.loads(line) for line in full_index.read_bytes().splitlines() if line.strip()] if full_index and full_index.exists() else []
    aliases, fulls, product_reviews = {}, {}, []
    for entry in full_entries:
        path = Path(entry['path']).resolve()
        if not path.is_relative_to(runtime) or sha(path) != entry['sha256']:
            raise ValueError('same_producer_full_archive_pin')
        full = read(path)
        capture_rows = [row for row in captures if row['binding']['binding_sha256'] == full.get('binding', {}).get('binding_sha256')]
        if not capture_rows or any(row['binding'] != capture_rows[0]['binding']
                                   or row['capture']['meshes'] != capture_rows[0]['capture']['meshes']
                                   for row in capture_rows[1:]):
            raise ValueError('producer_full_current_capture_bijection')
        actual = capture_rows[0]
        for key, value in actual['binding'].items():
            if full['binding'].get(key) != value:
                raise ValueError('full_source_binding_field:' + key)
        identity = read(runtime / 'INITIALIZE.json')['result']['_meta']['human_eye']
        proof = {'expected_source_sha256': PRODUCT,
                 'expected_host_source_sha256': next(row['sha256'] for row in binding['source_manifest'] if row['path'] == 'human_eye_plugin/blender_host.py'),
                 'actual_runtime_identity': identity, 'actual_loaded_host_sha256': loaded_host, 'material_pins': materials}
        mapping = q.validate_object_mapping(actual['capture'], actual['binding'], manifest, proof)
        for pose, fixed_pose in zip(actual['binding']['camera_specification']['views'], cameras['views']):
            if any(pose[key] != fixed_pose[key] for key in ('name', 'view_matrix', 'projection_matrix', 'size_px', 'direction_rational')):
                raise ValueError('actual_product_camera_changed')
        sources = {row['roi_id']: row for row in full['facts']['scope']['patch_support']['regions']}
        if len(full['facts']['regions']) != len(truth['regions']):
            raise ValueError('product_entire_region_count')
        for region in full['facts']['regions']:
            source = sources[region['roi_id']]
            target = [row for row in truth['regions'] if row['source_triangle_indices'] == source['triangle_indices']]
            if len(target) != 1:
                raise ValueError('product_source_region_not_independent')
            target = target[0]
            aliases[region['roi_id']] = target['id']
            q.validate_region_geometry(region, source['triangle_indices'], actual['capture']['meshes'][source['object_index']])
            for view, status in target['geometric_classifications'].items():
                classification = full['target_view_classifications'][view][region['roi_id']]
                if classification['status'] != status or classification['complete'] is not (status == 'complete'):
                    raise ValueError('product_geometry_classification')
        for frame in full['frames']:
            if frame['image_ref'] in fulls and fulls[frame['image_ref']]['frame'] != frame:
                # Different request-level timings can accompany the same cached frame.
                old = fulls[frame['image_ref']]['frame']
                if any(old[key] != frame[key] for key in ('image_sha256', 'arrays_sha256', 'host_binding_sha256', 'frame_identity')):
                    raise ValueError('same_ref_conflicting_producer')
            fulls[frame['image_ref']] = {'frame': frame, 'full': full, 'actual': actual, 'mapping': mapping, 'sources': sources}
            source_refs.update((frame['image_ref'], frame['host_binding_sha256'], 'product-binding:' + frame['host_binding_sha256']))
        source_refs.update(full['binding'][key] for key in ('binding_sha256', 'source_binding_sha256', 'scene_revision'))
        product_reviews.append({'full_path': str(path), 'sha256': entry['sha256'],
                                'binding_sha256': full['binding']['binding_sha256'],
                                'counts': full['facts']['inspection']['counts']})
    by_ref, frame_reviews, normalized_arrays = {}, [], {}
    for frame in saved['frames']:
        for key in ('PNG', 'NPZ'):
            path = Path(frame[key]).resolve()
            if not path.is_relative_to(runtime) or sha(path) != frame[key + '_sha256']:
                raise ValueError('actual_frame_pin')
        if frame['camera_sha256'] != DEVICE:
            raise ValueError('frame_camera_device')
        with np.load(frame['NPZ'], allow_pickle=False) as archive:
            arrays = {key: archive[key] for key in archive.files}
        with Image.open(frame['PNG']) as image:
            image.load()
            if image.mode != 'RGB' or image.size != (512, 512) or not np.array_equal(np.asarray(image), arrays['color']):
                raise ValueError('actual_PNG_not_same_RGB_buffer')
        names, offsets = frame['object_names'], frame['source_face_offsets']
        if len(names) != len(set(names)) or any(name not in expected_objects for name in names):
            raise ValueError('frame_object_order')
        expected_offsets = [0]
        for name in names:
            expected_offsets.append(expected_offsets[-1] + len(expected_objects[name]['triangles']))
        if offsets != expected_offsets:
            raise ValueError('frame_source_face_order')
        if frame['origin'] == 'product':
            item = fulls[frame['ref']]
            if names != [mesh['name'] for mesh in item['actual']['capture']['meshes']]:
                raise ValueError('product_frame_actual_capture_order')
            producer = item['frame']
            if frame['PNG_sha256'] != producer['image_sha256'] or frame['NPZ_sha256'] != producer['arrays_sha256']:
                raise ValueError('product_frame_producer_hash')
            q.saved_frame_arrays(frame['NPZ'], frame['NPZ_sha256'], item['mapping'], producer)
            actual_images = []
            for response_path in slot_root.rglob('tool_*/RESPONSE.json'):
                if 'owner_turn' in response_path.parts:
                    continue
                response = read(response_path)
                actual_images.extend(block for block in response.get('result', {}).get('content', [])
                                     if block.get('type') == 'image'
                                     and hashlib.sha256(base64.b64decode(block['data'], validate=True)).hexdigest() == frame['PNG_sha256'])
            if not actual_images:
                raise ValueError('current_product_image_not_delivered')
            observation = next(row for row in item['full']['facts']['observations'] if row['image_ref'] == frame['ref'])
            quality.check_frame(producer, observation, actual_images[0], item['actual']['capture'], item['mapping'],
                item['sources'], {row['roi_id']: row['front_direction_world'] for row in item['full']['facts']['regions']},
                q, metrics, np, Image)
        elif frame['origin'] == 'common_native':
            if frame['source_ref'] not in source_refs or names != [row['object_name'] for row in manifest['objects']]:
                raise ValueError('native_frame_complete_current_source_order')
        else:
            raise ValueError('actual_frame_origin')
        rows = pixel.evaluate(np, arrays, names, offsets, truth, frame['view_name'])
        if frame['origin'] == 'product':
            for roi, identity in aliases.items():
                pixel_row = next(row for row in observation['pixel_rows'] if row['roi_id'] == roi)
                independent = rows[identity]
                if (pixel_row['visible_surface_pixels'] != independent['surface_pixels']
                        or pixel_row['contrasting_boundary_pixels'] != independent['boundary_pixels']
                        or pixel_row['readable'] is not independent['readable']):
                    raise ValueError('product_pixel_fact_not_independent')
        by_ref[frame['ref']] = {'view_name': frame['view_name'], 'current_source_verified': True, 'regions': rows}
        normalized_owner = np.full(arrays['owners'].shape, -1, dtype=np.int32)
        normalized_face = np.full(arrays['triangle_ids'].shape, -1, dtype=np.int32)
        asset_names = [row['object_name'] for row in manifest['objects']]
        for index, name in enumerate(names):
            mask = arrays['owners'] == index
            normalized_owner[mask] = asset_names.index(name)
            normalized_face[mask] = arrays['triangle_ids'][mask]-offsets[index]
        normalized_arrays[frame['ref']] = {'color': arrays['color'], 'depth': arrays['depth'],
                                          'asset_owner': normalized_owner, 'local_source_face': normalized_face}
        source_refs.add(frame['ref'])
        frame_reviews.append({'ref': frame['ref'], 'view_name': frame['view_name'], 'origin': frame['origin'],
                              'PNG_sha256': frame['PNG_sha256'], 'NPZ_sha256': frame['NPZ_sha256'], 'regions': rows})
    owner_paths = list(slot_root.rglob('TOOLS.json'))
    owner_paths = [path for path in owner_paths if all(part != 'owner_turn' for part in path.parts)]
    if len(owner_paths) != 1:
        raise ValueError('one_actual_bridge_tools_index')
    owner = owner_paths[0].parent
    tools = read(owner_paths[0])['tools']
    requests, responses, product_responses = [], [], []
    for tool in tools:
        directory = owner / ('tool_' + str(tool['attempt']).zfill(2))
        request_path, response_path = directory / 'REQUEST.json', directory / 'RESPONSE.json'
        request, response = read(request_path), read(response_path)
        if request['id'] != response['id']:
            raise ValueError('actual_tool_response_id')
        requests.append(str(request_path))
        responses.append(str(response_path))
        if request['params']['name'] == 'active_observation':
            product_responses.append(str(response_path))
            if response['result']['isError'] is False:
                briefs = [json.loads(block['text']) for block in response['result']['content'] if block.get('type') == 'text']
                if len(briefs) != 1:
                    raise ValueError('one_actual_public_product_brief')
                brief = briefs[0]
                full = next((read(entry['path']) for entry in full_entries
                             if read(entry['path'])['binding']['binding_sha256'] == brief['binding']['binding_sha256']), None)
                if full is None:
                    raise ValueError('public_brief_no_current_same_producer')
                validate_brief(brief, full, aliases, truth)
    first_request = read(requests[0]) if requests else None
    for entry in full_entries:
        full = read(entry['path'])
        evidence = {row['roi_id']: row for row in full['facts']['region_evidence']}
        covered = 0
        for region in full['facts']['regions']:
            identity = aliases[region['roi_id']]
            target = next(row for row in truth['regions'] if row['id'] == identity)
            witness = evidence[region['roi_id']]['complete_witness']
            if witness is None:
                if (region['status'] != 'unknown'
                        or evidence[region['roi_id']]['unobserved_reason'] != target['unknown_reason_code']):
                    raise ValueError('product_unknown_fact')
            else:
                observation = next(row for row in full['facts']['observations'] if row['view_name'] == witness['view_name'])
                pixel_row = observation['pixel_rows'][witness['pixel_row_index']]
                if (pixel_row['roi_id'] != region['roi_id'] or region['status'] != 'covered'
                        or not by_ref[observation['image_ref']]['regions'][identity]['complete_readable']):
                    raise ValueError('product_complete_witness_not_independent')
                covered += 1
        counts = full['facts']['inspection']['counts']
        if counts['supported'] != len(truth['regions']) or counts['covered'] != covered or counts['unobserved'] != len(truth['regions'])-covered:
            raise ValueError('product_inspection_derived_counts')
    return {'aliases': aliases, 'by_ref': by_ref, 'current_source_references': sorted(source_refs),
            'normalized_arrays': normalized_arrays,
            'actual_product_responses': product_responses,
            'initial_product_entry': bool(first_request and first_request['params']['name'] == 'active_observation'),
            'actual_business_tool_count': len(tools), 'actual_tool_requests': requests, 'actual_tool_results': responses,
            'owner_path': str(owner), 'runtime_path': str(runtime),
            'summary': {'saved_evidence_path': str(index_path), 'saved_evidence_sha256': sha(index_path),
                        'source_reviews': source_reviews, 'product_reviews': product_reviews, 'frames': frame_reviews,
                        'unconstructed_view_pixel_status': {name: 'not_run' for name in truth['directions']
                            if name not in {frame['view_name'] for frame in saved['frames']}},
                        'new_actual_calls': 0, 'new_rasters': 0, 'new_models': 0}}

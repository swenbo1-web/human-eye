"""Qualify the fixed task through the real common and product stdio entry."""

import base64
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from runpy import run_path
import sys
import time


NS = Path(__file__).resolve().parents[1]
TARGET = 'Obj_07'
INDICES = [0, 1, 2, 3]
REFERENCES = ('Obj_05', 'Obj_08')
NATIVE_READ = """import json
scope_capture = scene_data()
scope_meshes = {row['name']: row for row in scope_capture['objects']}
print(json.dumps({'source_ref': scope_capture['source_ref'], 'counts': [len(scope_meshes),
 sum(len(x['vertices']) for x in scope_meshes.values()),
 sum(len(x['triangles']) for x in scope_meshes.values())]}))"""
NATIVE_SOLVE = """scope_again = scene_data()
assert scope_again['source_ref'] == scope_capture['source_ref']
target = scope_meshes['Obj_07']
ring = np.asarray(scope_meshes['Obj_05']['vertices'])
other = np.asarray(scope_meshes['Obj_08']['vertices'])
vertices = np.asarray(target['vertices'])
selected = vertices[np.unique(np.asarray(target['triangles'][:4]))]
inner_x = float(np.min(np.abs(ring[:,0])))
out = []
for scope, pts in [('selected',selected),('whole',vertices)]:
    id_x = int(np.argmax(pts[:,0]))
    a = pts[id_x].tolist()
    b = [inner_x,a[1],float(ring[:,2].min())]
    out.append(dict(scope=scope,reference='Obj_05',distance_m=float(np.linalg.norm(np.asarray(a)-b)),witness_a=a,witness_b=b))
    a = min(pts.tolist(),key=lambda point:(point[1],point[0],point[2]))
    b = [a[0],float(other[:,1].max()),a[2]]
    out.append(dict(scope=scope,reference='Obj_08',distance_m=float(np.linalg.norm(np.asarray(a)-b)),witness_a=a,witness_b=b))
print(json.dumps(out))"""


def require(value, reason):
    if not value:
        raise ValueError(reason)


def image_proof(content, folder, runtime, ref):
    from PIL import Image
    import numpy as np

    images = [item for item in content if item['type'] == 'image']
    captions = [item['text'] for item in content if item['type'] == 'text' and item['text'].startswith(ref + ' ')]
    require(len(images) == len(captions) == 1 and images[0]['mimeType'] == 'image/png', 'unique_ordinary_original_required')
    caption = json.loads(captions[0].split('\n', 1)[1])
    declaration = Path(caption['local_image_path'])
    png = declaration.resolve(strict=True)
    require(declaration.is_absolute() and str(declaration) == str(png) and png.is_relative_to(folder), 'same_slot_PNG_path_required')
    row = runtime.device.by_ref[ref]
    raw = base64.b64decode(images[0]['data'], validate=True)
    digest = sha256(raw).hexdigest()
    require(Path(row['PNG']) == png and digest == caption['image_sha256'] == row['PNG_sha256']
            and png.read_bytes() == raw, 'common_PNG_copy_and_frame_differ')
    with Image.open(BytesIO(raw)) as image:
        require(image.format == 'PNG' and image.size == (512, 512), 'actual_local_512_PNG_required')
        rgb = np.asarray(image.convert('RGB'))
    evidence = runtime.device.buffers[ref]
    idx = row['object_names'].index(TARGET)
    offsets = row['source_face_offsets']
    counts = {str(i): int(np.count_nonzero((evidence['owners'] == idx) &
                       (evidence['triangle_ids'] == offsets[idx] + i))) for i in INDICES}
    require(all(counts.values()) and np.array_equal(rgb, evidence['color']), 'selected_face_samples_or_native_rgb_differ')
    return {'ref': ref, 'path': str(png), 'sha256': digest, 'bytes': len(raw),
            'source_samples_by_triangle': counts, 'continuous_surface_proved': False}


def ranked(rows, sort_scope):
    return min((r for r in rows if r['scope'] == sort_scope), key=lambda r: r['distance_m'])['reference']


def score(rows, oracle, truth, meshes, membership):
    return oracle['score_geometry']({'focus_object': TARGET, 'selected_source_triangle_ids': INDICES,
        'measurements': rows, 'ranking': {scope: ranked(rows, scope) for scope in ('selected', 'whole')}},
        truth, meshes, membership)


def solve_product(call, owner):
    rows, retained = [], None
    for scope in ('selected', 'whole'):
        for ref in REFERENCES:
            if scope == 'selected':
                query = {'mode': 'source_region', 'reference': {'name': ref}, 'requested_facts': ['surface_proximity'],
                         'region': {'object': {'name': TARGET}, 'source_triangle_indices': INDICES}}
            else:
                query = {'mode': 'task', 'objects': [{'name': TARGET}, {'name': ref}], 'requested_facts': ['surface_proximity']}
            image = scope == 'selected' and ref == REFERENCES[0]
            content = call('human_eye_scene_observe', {'query': query, 'include_image': image, 'response_detail': 'brief'})
            raw = json.loads(content[0]['text'])
            if scope == 'selected':
                measured = raw['task_result']
                require(measured['reference']['name'] == ref and raw['region']['object_name'] == TARGET
                        and measured['region_ref']['source_triangle_indices'] == INDICES
                        and measured['measurement_scope'] == 'complete_selected_source_triangle_union_to_reference_triangle_surface',
                        'actual_product_selected_scope_not_bound')
            else:
                measured = raw
                require(measured['pair_order'] == 'A_to_B'
                        and [row['name'] for row in measured['binding']['objects']] == [TARGET, ref],
                        'actual_product_whole_scope_not_bound')
            fact = measured['facts']['surface_proximity']
            require(fact['status'] == 'measured', 'current_product_distance_unknown/' + scope + '/' + ref)
            value = fact['value']
            point = value['nearest_witness']
            rows.append({'scope': scope, 'reference': ref, 'distance_m': value['distance_m'],
                         'witness_a': point['a'], 'witness_b': point['b']})
            if image:
                visibility = raw['visibility']
                ref = visibility['image_ref']
                require(visibility['status'] == 'observed_samples' and visibility['complete_witness'] is None
                        and visibility['unknown'] == ['complete_surface_visibility'] and ref in owner.runtime.device.by_ref,
                        'candidate_selected_image_or_visibility_not_available')
                images = [base64.b64decode(item['data'], validate=True) for item in content if item['type'] == 'image']
                require(len(images) == 1, 'source_region_did_not_deliver_one_original_PNG')
                retained = ref, sha256(images[0]).hexdigest()
    return rows, retained


def run_diagnostic(folder, endpoint, deadline, group, owner, result):
    from common import save, sha
    from runtime import transport

    oracle = run_path(str(NS/'checks/truth.py'))
    meshes, _ = oracle['frozen_meshes']()
    truth = json.loads((NS/'checks/TRUTH.json').read_bytes())
    membership = run_path(str(oracle['MEMBERSHIP']))
    proof = oracle['verifies_geometry'](json.loads((folder/'initial_capture/TERMINAL_SOURCE.json').read_bytes()), meshes)
    local = folder/'client'
    client = transport.StdioClient([sys.executable, '-I', '-B', '-X', 'utf8', str(NS/'consumer/thin_stdio.py'),
        '--endpoint', str(endpoint), '--audit', str(local/'attachments')], folder, local/'transport', deadline)

    def call(name, arguments):
        ordinal = len(result['diagnostic_calls']) + 1
        directory = local/f'call_{ordinal:02d}'
        directory.mkdir()
        request = {'jsonrpc': '2.0', 'id': f'qualification-{ordinal}', 'method': 'tools/call',
                   'params': {'name': name, 'arguments': arguments}}
        save(directory/'REQUEST.json', request)
        row = {'index': ordinal, 'name': name, 'request_sha256': sha(directory/'REQUEST.json'),
               'started_ns': time.perf_counter_ns()}
        result['diagnostic_calls'].append(row)
        response = client.call(request)
        row['returned_ns'] = time.perf_counter_ns()
        save(directory/'RESPONSE.json', response)
        save(directory/'RECEIPT.json', client.records[-1])
        row['response_sha256'] = sha(directory/'RESPONSE.json')
        require('error' not in response and response.get('result', {}).get('isError') is False,
                'qualification_real_call_failed/' + str(ordinal) + '/' + name + '/' + str(response)[:950])
        return response['result']['content']

    try:
        initialization = client.call({'jsonrpc': '2.0', 'id': 'initialize', 'method': 'initialize',
            'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                       'clientInfo': {'name': 'perf050-source-scope-rank-qualification', 'version': '1.0'}}})
        save(local/'INITIALIZE.json', initialization)
        client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        catalogue = client.call({'jsonrpc': '2.0', 'id': 'list', 'method': 'tools/list'})
        save(local/'TOOLS.json', catalogue)
        require(catalogue['result']['tools'] == owner.tools, 'actual_common_directory_differed')
        data = json.loads(json.loads(call('execute_python', {'code': NATIVE_READ})[0]['text'])['stdout'])
        require(data['counts'] == [11, 64, 62], 'live_ordinary_source_count_differs')
        computed = json.loads(json.loads(call('execute_python', {'code': NATIVE_SOLVE})[0]['text'])['stdout'])
        ordinary = score(computed, oracle, truth, meshes, membership)
        require(ordinary['passed'], 'ordinary_current_four_pairs_or_rank_mismatch/' + str(ordinary)[:1200])
        common = call('render_local', {'direction': 'SCENE', 'target_world_m': [4.375,4.375,1.0625],
                                      'view_span_m': 1.1667261889578036, 'include_image': True})
        ref = json.loads(common[0]['text'])['frame']['ref']
        ordinary_image = image_proof(common, folder, owner.runtime, ref)
        product = product_image = None
        if group == 'P':
            computed, (product_ref, product_sha) = solve_product(call, owner)
            product = score(computed, oracle, truth, meshes, membership)
            require(product['passed'], 'installed_product_current_four_pairs_or_rank_mismatch/' + str(product)[:1200])
            product_image = image_proof(call('read_images', {'refs': [product_ref]}), folder, owner.runtime, product_ref)
            require(product_image['sha256'] == product_sha, 'installed_source_region_PNG_changed_on_same_slot_read')
    finally:
        result['diagnostic_close'] = close = client.finish()
        require(close['confirmed'] and close['exit_code'] == 0, 'diagnostic_stdio_close_unconfirmed')
    proof = {'passed': True, 'qualification_only': True, 'geometry': proof, 'common_source': data,
             'common_numeric': ordinary, 'common_image': ordinary_image, 'product_numeric': product,
             'product_image': product_image, 'exact_scope_rows': 4, 'model_consumers': 0}
    save(folder/'QUALIFICATION.json', proof)
    result['qualification'] = proof

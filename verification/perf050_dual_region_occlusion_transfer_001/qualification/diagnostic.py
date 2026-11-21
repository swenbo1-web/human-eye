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
TARGET = 'Obj_02'
INDICES = [0, 1]
REFERENCE = 'Obj_03'
REGIONS = (TARGET, 'Obj_06')
NATIVE_READ = """import json
scope_capture = scene_data()
scope_meshes = {row['name']: row for row in scope_capture['objects']}
print(json.dumps({'source_ref': scope_capture['source_ref'], 'counts': [len(scope_meshes),
 sum(len(x['vertices']) for x in scope_meshes.values()),
 sum(len(x['triangles']) for x in scope_meshes.values())]}))"""
NATIVE_SOLVE = """from fractions import Fraction as F
scope_again = scene_data()
assert scope_again['source_ref'] == scope_capture['source_ref']
cap = np.asarray(scope_meshes['Obj_03']['vertices'])
bottom = cap.min(axis=0)
below = {}
out = []
for name in ['Obj_02','Obj_06']:
    mesh = scope_meshes[name]
    vertices = np.asarray(mesh['vertices'])
    selected = vertices[np.unique(np.asarray(mesh['triangles'][:2]))]
    if name == 'Obj_02':
        a = selected[np.argmax(selected[:,:2].sum(axis=1))].tolist()
        b = bottom.tolist()
    else:
        a = selected[np.argmin(selected[:,:2].sum(axis=1))].tolist()
        b = a[:2]+[float(bottom[2])]
        for view in cameras['views']:
            dx,dy,dz = map(F, view['direction_rational'])
            projected = [(F(x)+(F(float(bottom[2]))-F(z))*dx/dz, F(y)+(F(float(bottom[2]))-F(z))*dy/dz)
                         for x,y,z in selected.tolist()]
            below[view['name']] = all(F(float(bottom[axis])) < p[axis] < F(float(cap.max(axis=0)[axis]))
                                     for p in projected for axis in (0,1))
    out.append(dict(object_name=name,distance_m=float(np.linalg.norm(np.asarray(a)-b)),a=a,b=b))
print(json.dumps({'measurements':out,'blocked_by_Obj_03_bottom':below}))"""


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


def score(rows, oracle):
    require(set(row['object_name'] for row in rows)==set(REGIONS) and len(rows)==2, 'wrong_measurement_scope_rows')
    scored = [oracle['qualify_measurement'](row['object_name'],row['distance_m'],row['a'],row['b']) for row in rows]
    return {'passed': all(row['passed'] for row in scored), 'measurements': scored}


def product_arguments(name):
    args = {'query': {'mode':'source_region','reference':{'name':REFERENCE},'requested_facts':['surface_proximity'],
                      'region':{'object':{'name':name},'source_triangle_indices':INDICES}}, 'include_image':True}
    if name != TARGET:
        args['response_detail'] = 'full'
    return args


def solve_product(call, owner):
    rows, retained, blocked, visibility_proof = [], None, [], None
    for name in REGIONS:
        content = call('human_eye_scene_observe',product_arguments(name))
        raw = json.loads(content[0]['text'])
        facts = raw if name == TARGET else raw['facts']
        measured = raw['task_result']
        require(measured['reference']['name']==REFERENCE and facts['region']['object_name']==name
                and raw['region_ref']['source_triangle_indices']==INDICES
                and measured['measurement_scope']=='complete_selected_source_triangle_union_to_reference_triangle_surface',
                'actual_product_selected_scope_not_bound/' + name)
        fact = measured['facts']['surface_proximity']
        require(fact['status']=='measured','current_product_distance_unknown/' + name)
        value = fact['value']
        point = value['nearest_witness']
        rows.append({'object_name':name,'distance_m':value['distance_m'],'a':point['a'],'b':point['b']})
        visibility = facts['visibility']
        if name == TARGET:
            witness = visibility['complete_witness']
            ref = visibility['image_ref']
            image, = raw['images']
            require(witness is not None and witness['geometry_status']=='complete'
                    and witness['selected_surface_pixels']>=16 and witness['contrasting_boundary_pixels']>=4
                    and image['image_ref']==ref and ref in owner.runtime.device.by_ref and image['local_image_path'],
                    'candidate_original_complete_view_not_available')
            images = [base64.b64decode(item['data'],validate=True) for item in content if item['type']=='image']
            require(len(images)==1 and sha256(images[0]).hexdigest()==image['image_sha256'], 'priority_region_native_PNG_mismatch')
            retained = ref, image['image_sha256'], image['local_image_path']
            visibility_proof = witness
        else:
            blocked = raw['view_attempts']
            require(visibility['complete_witness'] is None and visibility['selected_surface_pixels']==0
                    and len(blocked)==6 and all(row['status']=='positive_area_occlusion' for row in blocked),
                    'all_forward_occlusion_not_established/' + str(blocked)[:900])
    return rows, retained, blocked, visibility_proof


def run_diagnostic(folder, endpoint, deadline, group, owner, result):
    from common import save, sha
    from runtime import previous

    oracle = run_path(str(NS/'checks/truth.py'))
    source = json.loads((folder/'initial_capture/TERMINAL_SOURCE.json').read_bytes())
    proof = oracle['verify_geometry'](source)
    local = folder/'client'
    client = previous.transport.StdioClient([sys.executable, '-I', '-B', '-X', 'utf8', str(NS/'consumer/thin_stdio.py'),
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
        require(data['counts'] == [9, 54, 56], 'live_ordinary_source_count_differs')
        computed = json.loads(json.loads(call('execute_python', {'code': NATIVE_SOLVE})[0]['text'])['stdout'])
        ordinary = score(computed['measurements'],oracle)
        blocked = computed['blocked_by_Obj_03_bottom']
        require(ordinary['passed'] and set(blocked)=={'SCENE','TOP','LEFT','RIGHT','FRONT','BACK'} and all(blocked.values()),
                'ordinary_measurement_or_forward_occlusion_mismatch')
        common = call('render_local', {'direction': 'SCENE', 'target_world_m': [0,0,1],
                                      'view_span_m': 0.1944543648263006, 'include_image': True})
        ref = json.loads(common[0]['text'])['frame']['ref']
        ordinary_image = image_proof(common, folder, owner.runtime, ref)
        ordinary_pixels = oracle['verify_image'](folder,owner.runtime.device.by_ref[ref],packet=source)
        require(ordinary_pixels['passed'],'ordinary_independent_image_visibility_or_contrast')
        product = product_image = product_blocked = product_witness = None
        if group == 'P':
            computed, (product_ref, product_sha, product_path), product_blocked, product_witness = solve_product(call, owner)
            product = score(computed,oracle)
            require(product['passed'], 'installed_product_current_measurement_mismatch/' + str(product)[:1200])
            product_image = image_proof(call('read_images', {'refs': [product_ref]}), folder, owner.runtime, product_ref)
            product_pixels = oracle['verify_image'](folder,owner.runtime.device.by_ref[product_ref],packet=source)
            require(product_image['sha256']==product_sha and Path(product_image['path'])==Path(product_path)
                    and product_pixels['passed'],'installed_source_region_PNG_changed_on_same_slot_read')
    finally:
        result['diagnostic_close'] = close = client.finish()
        require(close['confirmed'] and close['exit_code'] == 0, 'diagnostic_stdio_close_unconfirmed')
    proof = {'passed': True, 'qualification_only': True, 'geometry': proof, 'common_source': data,
             'common_numeric': ordinary, 'common_image': ordinary_image, 'product_numeric': product,
             'product_image': product_image, 'common_blocked_by_Obj_03_bottom':blocked,
             'product_blocked_views':product_blocked,'product_complete_witness':product_witness,
             'exact_scope_rows': 2, 'model_consumers': 0}
    save(folder/'QUALIFICATION.json', proof)
    result['qualification'] = proof

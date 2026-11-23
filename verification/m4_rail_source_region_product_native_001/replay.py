"""Qualify the rail task through real endpoints without launching Blender or Codex."""

import argparse
import ast
from base64 import b64decode
from copy import deepcopy
from hashlib import sha256
from inspect import getsource
import json
from math import dist
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import time
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
V = HERE.parent
sys.path.insert(0, str(HERE))
import host


PRE = host.RUN / 'preflight'
ROOT = PRE / 'score_replay'
PRIOR = V / 'm4_assembly_cross_asset_product_native_001'
SEED = ('perf050_readonly_product_transfer_001', 'P1', 'f74703cb')
DONOR = ('m4_rail_blocker_consumption_formal_001', 'B1', 'a17083c0')
TERMINAL_SHA = 'c93e4f8629e13bf8912b56d073bde4a6b17ea73dfb98747cdbd79c9d11acc5be'
WIRE_SHA = '3d356d6be536055337c6c20d54515a0e0792c5bfe9b51d85c2311abeef4dae3d'
BOXES = {'M19': ((20.4, -3.2, 3.2), (22.1, -.8, 4.8)),
         'M21': ((31.49, 1.99, 2.99), (33.1, 4.01, 3.01))}
REFERENCES = {'M19': 'M14', 'M21': 'M13'}
ROWS = {'M19': [0, 3, 8, 9, 10, 11], 'M21': [2, 3]}
COUNTS = {'M19': (6, 6), 'M21': (2, 4)}
KNOWN_DISTANCE = {'M19': 3 * 13**.5 / 8, 'M21': .5}
KNOWN_PIXELS = {'M19': (1866, 2), 'M21': (28348, 2)}
LABELS = ('N1', 'P1')
INIT = {'jsonrpc': '2.0', 'id': 'offline-initialize', 'method': 'initialize',
        'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                   'clientInfo': {'name': 'rail-closed-capture-preflight', 'version': '1'}}}
NOTIFY = {'jsonrpc': '2.0', 'method': 'notifications/initialized'}
LIST = {'jsonrpc': '2.0', 'id': 'offline-tools', 'method': 'tools/list'}
read, require = host.read, host.require


def digest(data):
    return {'bytes': len(data), 'sha256': sha256(data).hexdigest()}


def pin(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': host.sha(path)}


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as out:
        json.dump(value, out, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        out.write('\n')


def git_blob(commit, path):
    return subprocess.check_output(['git', '-C', str(V.parent), 'show',
                                    commit + ':' + path.relative_to(V.parent).as_posix()])


def original_inputs(fixture):
    name, label, commit = fixture
    path = (Path('D:/') / ('he_' + name)).resolve()
    index_path = V / name / 'RUNTIME_INDEX.json'
    require(index_path.read_bytes() == git_blob(commit, index_path), 'sealed_index_changed/' + name)
    index = read(index_path)
    bundle = path / 'ORIGINAL_RUNTIME.zip'
    require(index['archive'] == pin(bundle), 'sealed_archive_changed/' + name)
    by_name = {row['path']: row for row in index['files']}
    required = ['native/input.blend', 'TERMINAL_SOURCE.json', 'initial_capture/TERMINAL_SOURCE.json',
                'SLOT_RESULT.json', 'SLOT_PUBLICATION.json', 'RUNTIME_CLOSE.json', 'NATIVE_RUNTIME_PROOF.json']
    if fixture == DONOR:
        required += ['raw_sources/live-source-001.json', 'DEVICE_EVIDENCE.json',
                     'native/WIRE/INDEX.json', 'native/WIRE/002/REQUEST.bin', 'native/WIRE/002/RESPONSE.bin']
    original, receipts = {}, [pin(index_path), pin(bundle)]
    with ZipFile(bundle) as archived:
        require(len(by_name) == index['count'] == len(archived.namelist()), 'sealed_member_count_changed/' + name)
        for name_in_slot in required:
            short = f'slots/{label}/{name_in_slot}'
            member = path / short
            raw = member.read_bytes()
            require(by_name[short] == {'path':short, **digest(raw)} and archived.read(short) == raw,
                    'sealed_member_changed/' + short)
            receipts.append({'path':str(member), **digest(raw)})
            original[name_in_slot] = raw
    terminal = json.loads(original['TERMINAL_SOURCE.json'])
    initial = json.loads(original['initial_capture/TERMINAL_SOURCE.json'])
    result, pub, close, owned = (json.loads(original[key]) for key in (
        'SLOT_RESULT.json', 'SLOT_PUBLICATION.json', 'RUNTIME_CLOSE.json', 'NATIVE_RUNTIME_PROOF.json'))
    require(result['label'] == pub['label'] == label and result['status'] == pub['status'] == 'completed'
            and pub['result_sha256'] == digest(original['SLOT_RESULT.json'])['sha256']
            and result['terminal_source']['sha256'] == digest(original['TERMINAL_SOURCE.json'])['sha256']
            and result['closure_verification']['passed'] and result['independent_before_after']['passed']
            and owned['confirmed'] and owned['runtime_pid'] == terminal['source']['pid']
            and close['Blender_exit']['confirmed'] and close['Blender_exit']['exit_code'] == 0
            and close['errors'] == [] and close['public_MCP_close']['confirmed'],
            'historical_slot_was_not_closed_on_its_capture/' + label)
    require(terminal['source'] == initial['source'] and terminal['objects'] == initial['objects']
            and digest(original['native/input.blend'])['sha256'] == terminal['source']['asset_sha256']
                  == host.ASSET_SHA256, 'same_asset_or_initial_terminal_changed/' + label)
    return original, terminal, receipts


def archived_capture():
    seed, reference, seed_pins = original_inputs(SEED)
    donor, terminal, donor_pins = original_inputs(DONOR)
    require(digest(seed['TERMINAL_SOURCE.json'])['sha256'] == TERMINAL_SHA
            and digest(donor['native/WIRE/002/RESPONSE.bin'])['sha256'] == WIRE_SHA
            and seed['native/input.blend'] == donor['native/input.blend'],
            'fixed_rail_archive_anchor_changed')
    for key in ('display_object_mask', 'source_face_offsets', 'layer_collections', 'scene_cameras'):
        require(terminal[key] == reference[key], 'cross_capture_rail_scene_changed/' + key)
    for key in ('frame','subframe','view_layer','scene','scale_length','unit_settings','source_index_domain'):
        require(terminal['source'][key] == reference['source'][key], 'cross_capture_context_changed/' + key)
    require([len(terminal['objects']), sum(len(row['evaluated']['vertices']) for row in terminal['objects']),
             terminal['source_face_offsets'][-1]] == [21, 148, 184], 'rail_geometry_totals_changed')
    for a,b in zip(terminal['objects'], reference['objects'], strict=True):
        require(a.keys() == b.keys() and all(a[key] == b[key] for key in a if key != 'instance_id'),
                'cross_capture_rail_ordered_geometry_changed/' + a['name'])
    raw = json.loads(donor['raw_sources/live-source-001.json'])
    device = json.loads(donor['DEVICE_EVIDENCE.json'])
    receipt, = [row for row in device['sources'] if not row['terminal']]
    require(receipt['status'] == 'complete' and raw['source'] == terminal['source']
            and all(receipt[key] == val for key,val in digest(donor['raw_sources/live-source-001.json']).items()),
            'historical_ordinary_source_not_from_capture')
    for obj, recorded in zip(terminal['objects'], raw['objects'], strict=True):
        require(all(obj[key] == recorded[key] for key in (
            'name','object_id','instance_id','matrix_world','visible_get'))
                and all(obj['evaluated'][key] == recorded[other] for key,other in (
                    ('vertices_world_m','vertices'),('vertices','vertices_local'),('triangles','triangles'))),
                'historical_ordinary_evaluated_rows_changed/' + obj['name'])
    extractor_path = V / 'm1_source_region_world_box_001/inputs.py'
    extractor = run_path(str(extractor_path))['recorded_delta']
    slot = Path('D:/he_m4_rail_blocker_consumption_formal_001/slots/B1').resolve()
    delta, wire = extractor(slot, '002', 21, json.loads(donor['native/WIRE/INDEX.json']),
                            lambda filename: donor[filename.relative_to(slot).as_posix()])
    files = [*seed_pins, *donor_pins, pin(extractor_path), pin(Path(__file__))]
    return donor, terminal, raw, delta, wire, files


def check_decoded(cap, terminal):
    original = V / 'm4_source_region_nonplanar_short_circuit_001/harness/inputs.py'
    run_path(str(original))['verify_geometry'](cap,terminal)
    display = cap['display_snapshot']
    source = terminal['source']
    require(display['view_layer']['instance_id'] == source['view_layer_id']
            and display['view_layer']['name'] == source['view_layer']
            and [m['object_id'] for m in cap['meshes']] == [o['object_id'] for o in terminal['objects']],
            'capture_scope_or_order_does_not_match_donor')
    by_id = {o['object_id']:o for o in terminal['objects']}
    require(len(display['objects']) == len(by_id), 'incomplete_capture_display')
    for row in display['objects']:
        original = by_id[row['host_id']]
        require(row['instance_id'] == original['instance_id']
                and row['visible_get'] is original['visible_get']
                and all(row[k] is original['display'][k] for k in ('hide_get','hide_viewport','hide_render')),
                'capture_display_disagrees_with_donor/' + original['name'])


def installed_worker(slot):
    retained = run_path(str(PRIOR / 'product_preflight.py'))
    worker = retained['OLD']['retained_workers']()[0]['worker']
    _, terminal, _, delta, wire, files = archived_capture()
    # Both requests replay the same exact complete wire packet. No synthetic
    # delta is credited as native residency; the qualification concerns source.
    source = {'name':'rail_offline', 'calls':[{},{}],
              'capture_plan':[(delta,{'command':'capture','params':{}},terminal)] * 2,
              'source_pins':files}
    return worker(slot, host.PRODUCT_BINDING, 'rail_offline', False, source=source)


def replay_native_input(code, trusted=True, timeout_s=30, *, slot, raw, terminal):
    invocation, = ast.parse(code).body
    exec_call = invocation.value
    compile_call = exec_call.args[0]
    require(trusted is True and timeout_s == 30 and exec_call.func.id == 'exec'
            and compile_call.func.id == 'compile' and compile_call.args[1].value == '<m4-live-device-capture>',
            'offline_runtime_forbids_a_live_Bpy_or_other_request')
    capture_call = ast.parse(compile_call.args[0].value).body[-1].value
    out = Path(ast.literal_eval(capture_call.args[1])).resolve()
    terminal_request = ast.literal_eval(capture_call.keywords[0].value)
    require(capture_call.func.id == 'capture_device' and ast.literal_eval(capture_call.args[2]) == host.ASSET_SHA256
            and out.is_relative_to(slot) and out.parent.name == ('terminal_sources' if terminal_request else 'raw_sources'),
            'offline_capture_is_not_the_current_owned_route')
    packet = deepcopy(terminal if terminal_request else raw)
    packet['source']['asset_copy'] = str(slot / 'native/input.blend')
    save(out, packet)
    marker = {**digest(out.read_bytes()),'pid':packet['source']['pid'],
              'offline_recorded_source':True}
    return {'stdout':'M4_LIVE_SOURCE_CAPTURE:' + json.dumps(marker), 'error':None}


def ordinary_code():
    oracle = run_path(str(V / 'm4_yanyite_dual_curved_region_native_001/score/oracle.py'))
    contains = getsource(oracle['triangle_contains'])
    return f"""
import json
from itertools import product
from fractions import Fraction
{contains}
o = {{row['name']: row for row in scene_data()['objects']}}
boxes = {BOXES!r}
refs = {REFERENCES!r}
quantities = {{}}
triangles = {{}}
selected = {{}}
for name, (lo, hi) in boxes.items():
    a = np.asarray(o[name]['vertices'])
    f = np.asarray(o[name]['triangles'])
    b = np.asarray(o[refs[name]]['vertices'])
    g = np.asarray(o[refs[name]]['triangles'])
    rows = np.flatnonzero(((a>=lo)&(a<=hi)).all(axis=1)[f].all(axis=1))
    vertices = np.unique(f[rows])
    triangles[name], selected[name] = f, rows
    cloud = a[vertices]
    axes = []
    for x, y in zip(cloud.T, b.T):
        al, ah, bl, bh = x.min(), x.max(), y.min(), y.max()
        if ah < bl:
            axes.append([(ah,bl)])
        elif bh < al:
            axes.append([(al,bh)])
        else:
            low, high = max(al,bl), min(ah,bh)
            values = sorted({{low,high,(low+high)/2,*(t for t in [*x,*y] if low<=t<=high)}})
            axes.append([(t,t) for t in values])
    for pair in product(*axes):
        p,q = map(np.asarray,zip(*pair))
        if (any(triangle_contains(p.tolist(),face.tolist()) for face in a[f[rows]])
                and any(triangle_contains(q.tolist(),face.tolist()) for face in b[g])):
            break
    else:
        raise ValueError('no_ordinary_exact_surface_witness/'+name)
    delta = q-p
    distance = float(np.linalg.norm(delta))
    quantities[name] = {{'triangle_ids':rows.tolist(),'vertex_count':len(vertices),'distance_m':distance,
                         'direction':(delta/distance).tolist(),'a':p.tolist(),'b':q.tolist()}}
print(json.dumps(quantities))
"""


def render_code():
    return """
records = {}
for name, rows in selected.items():
    points = np.asarray(o[name]['vertices'])[np.unique(triangles[name][rows])]
    focus = (points.min(axis=0) + points.max(axis=0))*0.5
    frame = render_local('SCENE', focus.tolist(), 4.0)
    records[name] = frame['ref']
print(json.dumps(records))
"""


def args_for(name):
    lo,hi = BOXES[name]
    return {'include_image':True,'response_detail':'full',
            'query':{'mode':'source_region','region':{'object':{'name':name},
                     'world_box_m':{'min':list(lo),'max':list(hi)}},
                     'reference':{'name':REFERENCES[name]},'requested_facts':['surface_proximity']}}


def closed_capture_files(slot, original):
    history = slot / 'historical_capture'
    history.mkdir()
    for name in ('RUNTIME_CLOSE.json','NATIVE_RUNTIME_PROOF.json','TERMINAL_SOURCE.json',
                 'SLOT_RESULT.json','SLOT_PUBLICATION.json','native/WIRE/002/REQUEST.bin',
                 'native/WIRE/002/RESPONSE.bin','native/WIRE/INDEX.json'):
        out = history / name
        out.parent.mkdir(parents=True,exist_ok=True)
        with out.open('xb') as stream:
            stream.write(original[name])


def selected_sample(np, frame, name, claimed=None):
    with np.load(frame['NPZ'], allow_pickle=False) as arrays:
        owner, source = arrays['owners'], arrays['triangle_ids']
        index = frame['object_names'].index(name)
        offset = frame['source_face_offsets'][index]
        mask = (owner == index) & np.isin(source, np.asarray(ROWS[name])+offset)
        coordinates = np.argwhere(mask & ~mask.T)
        coordinates = coordinates[coordinates[:,0] != coordinates[:,1]]
        require(len(coordinates)>0,'no_asymmetric_selected_pixel/' + name)
        y,x = map(int,coordinates[len(coordinates)//2])
        observed = [y,x,int(source[y,x])-offset]
        if claimed is not None:
            row,column,face = claimed
            require(0<=row<owner.shape[0] and 0<=column<owner.shape[1]
                    and mask[row,column] and face==int(source[row,column])-offset,
                    'compact_sample_not_a_current_selected_pixel/' + name)
        return observed, (int(mask.sum()),len(np.unique(source[mask])))


def fixture_answer(slot,label,numeric,selected,events,close,terminal_receipt,source_pins):
    """Publish an explicitly synthetic answer/events made from genuine tool replies."""
    consumer = slot / 'consumer'
    consumer.mkdir()
    answer_lines = ['离线评分用合成答复。']
    claims = {}

    def claim(name, line, **fields):
        answer_lines.append(line)
        claims[name] = {'quote':line, **fields}

    for name in BOXES:
        source, final = numeric[name], selected[name]
        triangles,vertices = COUNTS[name]
        claim(name+'.counts', f'{name} 选中 {triangles} 个源三角和 {vertices} 个顶点。',
              triangles=triangles, vertices=vertices)
        distance = format(source['distance_m'], '.12f')
        claim(name+'.distance', f'{name} 到 {REFERENCES[name]} 整件最短表面距离 {distance} m。',
              distance_literal=distance, distance_unit='m')
        direction = source['direction']
        claim(name+'.direction', f'{name} 世界单位方向 {direction}。', world_unit_direction=direction)
        claim(name+'.nearest_pair', f'{name} 对应世界点 {source["a"]} 到 {source["b"]}。',
              selected_point_world_m=source['a'], reference_point_world_m=source['b'])
        above = source['distance_m'] >= 1
        claim(name+'.threshold', f'{name} {"达到" if above else "低于"} 1.0 m 阈值。', at_least_1_0_m=above)
        image = Path(final['frame']['PNG']).as_posix()
        claim(name+'.image', f'[{name} 本槽原图](<{image}>)', local_image_path=image)
        y,x,face = final['pixel']
        claim(name+'.pixel', f'{name} 像素行 {y} 列 {x}，对应当前选中源三角 {face}。',
              pixel_rc=[y,x],current_object_local_triangle=face)
        claim(name+'.scope', f'{name} 图只证明本次视角的实际采样，无法判定完整可见性或未采样面的遮挡。',
              observable_scope='actual_samples_in_one_frame',implies_complete_visibility=False,
              implies_all_unsampled_are_occluded=False)
    claim('nearer','M21 到参考整件更近。',value='M21')
    text = '\n'.join(answer_lines) + '\n'
    with (consumer/'PUBLIC_FINAL.txt').open('xb') as stream:
        stream.write(text.encode('utf8'))
    answer = pin(consumer/'PUBLIC_FINAL.txt')
    events += [{'type':'item.completed','item':{'id':'offline-final','type':'agent_message','text':text}},
               {'type':'turn.completed','usage':{}}]
    timed = [{'perf_ns':i,'event':event} for i,event in enumerate(events,1)]
    for path, records in ((consumer/'events.jsonl',timed),(consumer/'stdout.raw.bin',events)):
        with path.open('xb') as stream:
            for event in records:
                stream.write((json.dumps(event,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf8'))
    save(PRE/f'{label}_CLAIMS.json',{'slot':label,'answer_sha256':answer['sha256'],'claims':claims})
    save(slot/'SLOT_RESULT.json',{'label':label,'status':'completed','offline_fixture':True,
         'asset_sha256':host.ASSET_SHA256,'answer':answer,'consumer':{'valid_completion':True,'offline_fixture':True},
         'model_consumers':0,'terminal_source':terminal_receipt,'errors':[],
         'closure_verification':{'passed':True,'offline_fixture':True},
         'independent_before_after':{'passed':True,'offline_fixture':True}})
    save(slot/'SLOT_PUBLICATION.json',{'label':label,'status':'completed','offline_fixture':True,
                                     'result_sha256':pin(slot/'SLOT_RESULT.json')['sha256']})
    save(slot/'OFFLINE_FIXTURE.json',{'passed':True,'offline_fixture':True,'actual_Blender_starts':0,
         'actual_models':0,'source_pins':source_pins,'closure':close})


def arm(label):
    from functools import partial

    donor, terminal, raw, delta, wire_source, source_pins = archived_capture()
    slot = ROOT / 'slots' / label
    slot.mkdir(parents=True, exist_ok=False)
    (slot/'native').mkdir()
    with (slot/'native/input.blend').open('xb') as out:
        out.write(donor['native/input.blend'])
    closed_capture_files(slot, donor)
    common, mod, bridge, _, binding = host.runtime_graph(ROOT,label)
    sys.path.insert(0,binding['install_root'])
    import numpy as np
    from human_eye_plugin.attention_raster import rasterize_attention

    raster = Path(sys.modules[rasterize_attention.__module__].__file__).resolve(strict=True)
    require(raster.is_relative_to(Path(binding['install_root']).resolve(strict=True)),
            'ordinary_raster_not_from_the_fixed_installed_dependencies')
    deadline = time.perf_counter_ns()+120_000_000_000
    runtime = mod.Runtime(slot,label,deadline,deadline+30_000_000_000)
    native_read = partial(replay_native_input, slot=slot,raw=raw,terminal=terminal)
    runtime._native_call = runtime._terminal_call = native_read
    runtime.prepare_device(host.ASSET_SHA256)
    initial = deepcopy(terminal)
    initial['source']['asset_copy'] = str(slot/'native/input.blend')
    (slot/'initial_capture').mkdir()
    save(slot/'initial_capture/TERMINAL_SOURCE.json',initial)
    endpoint = thin = owner = None
    events, selected, ordinary = [], {}, {}
    try:
        if label=='P1':
            runtime.client = mod.ProductionStdioClient(
                [sys.executable,'-IB','-X','utf8',str(Path(__file__)), '--worker',label],
                slot,slot/'mcp',deadline,worker_evidence=slot/'mcp_io')
            runtime.mcp_handle = runtime._retain(runtime.client.process,'MCP_RUNTIME_PROOF.json')
            identity = runtime.client.call(INIT)['result']['_meta']['human_eye']
            runtime.client.call(NOTIFY)
            runtime.product_tools = runtime.client.call(LIST)['result']['tools']
            require(identity['source_sha256']==binding['source_sha256']
                    and identity['source_kind']=='installed_distribution'
                    and runtime.product_tools==read(host.catalogue_path('P1')),'offline_product_identity_or_tools_changed')
        owner = bridge.Owner(runtime, {'label':label,'group':label[0],'phase':'formal',
                            'worker_deadline_ns':deadline,'output':str(slot/'owner')},budget=runtime.budget)
        endpoint = owner.start(slot/'ENDPOINT.json')
        thin = mod.transport.StdioClient(
            [sys.executable,'-IB','-X','utf8',str(HERE/'thin_stdio.py'),'--endpoint',str(endpoint),
             '--audit',str(slot/'attachments')],slot,slot/'client_wire',deadline)
        thin.call(INIT)
        thin.call(NOTIFY)
        tools = thin.call(LIST)['result']['tools']
        require(tools==owner.tools and [t for t in tools if t['name']!=bridge.PRODUCT_TOOL]==bridge.TOOLS,
                'actual_common_tools_not_equivalent')

        def call(tool,args,*,error=False):
            ident = f'offline-tool-{len(events)+1}'
            q = {'jsonrpc':'2.0','id':ident,'method':'tools/call','params':{'name':tool,'arguments':args}}
            reply = thin.call(q)
            value = reply['result']
            require(reply['id']==ident and value['isError'] is error,
                    'actual_offline_thin_call_failed/'+ident+'/'+str(value['content'][0])[:650])
            events.append({'type':'item.completed','item':{'id':ident,'type':'mcp_tool_call',
                           'server':'arm_engine','tool':tool,'arguments':args,'result':value,'error':None}})
            return value['content']

        def execute(code):
            answer, = call('execute_python',{'code':code})
            item = json.loads(answer['text'])
            require(item['error'] is None,'actual_persistent_ordinary_python_failed')
            return json.loads(item['stdout'])

        numeric = execute(ordinary_code())
        for name, result in numeric.items():
            require(result['triangle_ids']==ROWS[name] and result['vertex_count']==COUNTS[name][1]
                    and abs(result['distance_m']-KNOWN_DISTANCE[name])<1e-12
                    and abs(dist(result['a'],result['b'])-result['distance_m'])<1e-12,
                    'ordinary_geometry_or_point_pair_changed/'+name)
        call('render_local',{'direction':'SCENE','target_world_m':[0,0,0],'view_span_m':0},error=True)
        refs = execute(render_code())
        content = call('read_images',{'refs':list(refs.values())})
        require(len(content)==4,'ordinary_two_originals_not_delivered')
        for i, (name,ref) in enumerate(refs.items()):
            caption, image = content[2*i:2*i+2]
            frame = runtime.device.by_ref[ref]
            path = json.loads(caption['text'].splitlines()[1])['local_image_path']
            require(path==Path(frame['PNG']).as_posix() and image['mimeType']=='image/png'
                    and Path(path).read_bytes()==b64decode(image['data'],validate=True),
                    'ordinary_original_png_binding_changed/'+name)
            sample,counts = selected_sample(np,frame,name)
            ordinary[name] = {'frame':frame,'pixel':sample,'samples':counts}
        selected = ordinary
        if label=='P1':
            invalid = args_for('M19')
            invalid['query']['region']['world_box_m']['max'][0] = -1
            call(bridge.PRODUCT_TOOL,invalid,error=True)
            product = {}
            for name in BOXES:
                body, image = call(bridge.PRODUCT_TOOL,args_for(name))
                public = json.loads(body['text'])
                media, = public['images']
                producer = runtime.public_requests[-1]['producer_archive']
                report = read(producer['path'])
                row, = report['frames']
                frame = runtime.device.by_ref[row['image_ref']]
                pixel = media['sampled_pixel']
                expected = numeric[name]
                fact = public['task_result']['facts']['surface_proximity']
                require(public['region_ref']==report['region_ref']
                        and public['region_ref']['source_triangle_indices']==ROWS[name]
                        and fact==report['task_result']['facts']['surface_proximity']
                        and fact['status']=='measured' and abs(fact['value']['distance_m']-expected['distance_m'])<1e-12
                        and media['local_image_path']==Path(frame['PNG']).as_posix()
                        and image['mimeType']=='image/png' and Path(frame['PNG']).read_bytes()==b64decode(image['data'],validate=True),
                        'actual_product_scope_distance_or_original_binding_changed/'+name)
                probe,counts = selected_sample(np,frame,name,
                     [pixel['row'],pixel['column'],pixel['source_triangle_index']])
                require(counts==KNOWN_PIXELS[name] and row['view_name']=='SCENE',
                        'actual_product_registered_sample_changed/'+name+'/'+str(counts))
                product[name] = {'frame':frame,'pixel':probe,'samples':counts,'producer':producer}
            selected = product
        terminal_receipt = runtime.device.export_terminal()
        require(read(slot/'TERMINAL_SOURCE.json')==read(slot/'initial_capture/TERMINAL_SOURCE.json'),
                'offline_initial_terminal_derived_sources_disagree')
    finally:
        try:
            thin_close = thin.finish() if thin else None
        finally:
            try:
                owner_close = owner.close() if owner else None
            finally:
                runtime_close = runtime.close('offline_preflight')
    require(thin_close and thin_close['confirmed'] and thin_close['exit_code']==0
            and owner_close and owner_close['confirmed'] and not owner_close['errors']
            and not owner_close['transport_errors'] and not runtime_close['errors'],
            'actual_offline_runtime_or_wire_close_failed')
    budget = runtime.budget.snapshot()['counts']
    require(budget['Blender_start_attempts']==budget['consumer_admissions']==0 and not runtime.native_start_entered,
            'offline_replay_crossed_Blender_or_model_boundary')
    source_pins.extend(pin(path) for path in (
        HERE/'host.py',HERE/'thin_stdio.py',host.PRODUCT_BINDING,Path(binding['wheel_path']),raster,
        V/'m4_source_region_nonplanar_short_circuit_001/harness/inputs.py',
        V/'m4_yanyite_dual_curved_region_native_001/score/oracle.py'))
    if label=='P1':
        require(runtime_close['public_MCP_close']['production_eof_and_exit_verified']
                and runtime_close['public_MCP_exit']['confirmed'], 'actual_offline_product_eof_missing')
        worker = read(slot/'REPLAY_CLOSE.json')
        require(worker['old_sources_unchanged'] and len(worker['calls'])==2
                and all(row['resource_count']==21 for row in worker['calls']),
                'offline_donor_full_capture_not_replayed_twice')
        for i in (1,2):
            check_decoded(read(slot/f'CAPTURE_{i:02d}.json'),terminal)
    require(all(Path(v['frame']['PNG']).is_file() and host.sha(v['frame']['PNG'])==v['frame']['PNG_sha256']
                and host.sha(v['frame']['NPZ'])==v['frame']['NPZ_sha256'] for v in selected.values()),
            'same_slot_original_did_not_survive_close')
    closure = {key:pin(slot/path) for key,path in (
        ('runtime','RUNTIME_CLOSE.json'),('thin','client_wire/CLOSE.json'),('owner','owner/BRIDGE_RESULT.json'),
        ('historical_close','historical_capture/RUNTIME_CLOSE.json'),
        ('historical_native','historical_capture/NATIVE_RUNTIME_PROOF.json'))}
    source_pins.extend(closure.values())
    if label=='P1':
        source_pins.append(pin(slot/'mcp/HELD_CLOSE.json'))
    fixture_answer(slot,label,numeric,selected,events,closure,terminal_receipt,source_pins)
    save(slot/'ARM.json',{'passed':True,'group':label,'tools':tools,'ordinary':ordinary,'selected':selected,
         'numeric':numeric,'actual_Blender_starts':0,'actual_models':0,'offline_rasters':budget['all_raster_upper'],
         'true_historical_wire':wire_source,'close':closure,'source_pins':source_pins,
         'fixture':pin(slot/'OFFLINE_FIXTURE.json'),'claims':pin(PRE/f'{label}_CLAIMS.json')})


def preflight():
    ROOT.mkdir(parents=True,exist_ok=False)
    results = {}
    for label in LABELS:
        argv = [sys.executable,'-IB','-X','utf8',str(Path(__file__)),'--arm',label]
        result = subprocess.run(argv,cwd=V.parent,capture_output=True,timeout=155)
        for suffix, data in (('STDOUT.bin',result.stdout),('STDERR.bin',result.stderr)):
            with (ROOT/f'{label}_{suffix}').open('xb') as stream:
                stream.write(data)
        require(result.returncode==0,'cold_actual_replay_failed/'+label+'/'+result.stderr.decode('utf8',errors='replace')[-1800:])
        results[label] = read(ROOT/'slots'/label/'ARM.json')
    n,p = (results[label] for label in LABELS)
    require(n['tools']==p['tools'][:-1] and n['numeric']==p['numeric']
            and all(n['ordinary'][name]['frame']['PNG_sha256']==p['ordinary'][name]['frame']['PNG_sha256']
                    and n['ordinary'][name]['pixel']==p['ordinary'][name]['pixel'] for name in BOXES),
            'ordinary_capture_or_result_differs_between_arms')
    by_path = {row['path']:row for arm in results.values() for row in arm['source_pins']}
    save(PRE/'REPLAY.json',{'passed':True,'offline_fixture':True,'actual_Blender_starts':0,'actual_models':0,
         'arms':results,'source_pins':list(by_path.values()),
         'product_git':host.PRODUCT['commit'],'proof_root':str(ROOT)})
    print(PRE/'REPLAY.json',flush=True)


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode and host.sha(sys.executable)==host.PYTHON_SHA,
            'fixed_isolated_replay_interpreter_required')
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--arm',choices=LABELS)
    mode.add_argument('--worker',choices=('P1',))
    args = parser.parse_args()
    if args.worker:
        raise SystemExit(installed_worker(ROOT/'slots'/args.worker))
    if args.arm:
        arm(args.arm)
    else:
        preflight()

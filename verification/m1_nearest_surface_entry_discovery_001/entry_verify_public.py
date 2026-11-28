"""Compare both installed MCP catalogues and the advertised call on sealed geometry."""
import argparse
import base64
import copy
from fractions import Fraction
import hashlib
import json
import os
import math
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
BATCH = 'M1-NEAREST-SURFACE-ENTRY-DISCOVERY-001'
ROOT = Path(os.environ['HE_ENTRY_DISCOVERY_ROOT']).resolve(strict=True)
PRE = ROOT / 'preflight'
FIXTURE = PRE / 'fixture'
PRIOR = ROOT.parent / 'M4-NEAREST-SURFACE-FIRST-FOCUS-001'
A_CUSTODY = PRIOR / 'preflight/INSTALL_CUSTODY.json'
OUT = PRE / 'entry-product-preflight'
PRODUCT_RESULT = PRE / 'ENTRY_PRODUCT_PREFLIGHT.json'
JOINT_RESULT = PRE / 'ENTRY_CATALOGUE_PARITY.json'
TOOL = 'human_eye_scene_observe'
PREFACE = 'Current Blender facts.'
EXAMPLE = {'query': {'mode': 'active_observation', 'objects': [{'name':'Target'}],
                     'focus': {'task_region': {'reference': {'name':'Reference'}, 'relation':'nearest_surface'}}}}
REFERENCE = {'K':'Module C', 'T':'Module D'}
TARGET = 'Piece N'

sys.path.insert(0,str(HERE.parent/'m4_nearest_surface_first_focus_001'))
from controls import on_triangle, vector, dot, subtract, get_body, pin, need, encode, sha, read, dump


def sealed_capture():
    source = read(FIXTURE/'EVALUATED_SOURCE.json')
    truth = read(FIXTURE/'TARGET_TRUTH.json')
    signature = pin(FIXTURE/'main.blend')['sha256']
    need(source['asset_sha256'] == truth['asset_sha256'] == signature
         and truth['evaluated_source_sha256'] == pin(FIXTURE/'EVALUATED_SOURCE.json')['sha256']
         and truth['target_name']==TARGET and set(truth['cases'])==set(REFERENCE)
         and all(truth['cases'][key]['reference_name']==name for key,name in REFERENCE.items()),
         'new_fixture_truth_or_asset_not_bound')
    old_path = PRIOR/'slots/B/post_capture.json'
    template = read(old_path)
    value = copy.deepcopy(template)
    value['revision'] = sha((signature+'/offline-evaluated').encode())
    value['capture_state'] = {'instance_id':signature[:32], 'epoch':1,'revision':1,'selection_key':signature}
    value['host_identity'].update(document_epoch=signature, object_instances={})
    value['meshes'] = []
    display = value['display_snapshot']
    display['view_layer'].update(name=source['view_layer'], instance_id='offline-evaluated-view-layer')
    display['objects'] = []
    for i, row in enumerate(source['objects']):
        host_id = 'offline:' + sha((signature+'/'+row['name']).encode())
        instance_id = f'offline-object-{i}'
        value['host_identity']['object_instances'][host_id] = instance_id
        edges = sorted({tuple(sorted((a,b))) for face in row['faces'] for a,b in zip(face,face[1:]+face[:1])})
        mesh = {**template['meshes'][i], 'name':row['name'], 'object_id':host_id,
                'mark_label':row['name'], 'vertices':row['vertices'], 'faces':row['faces'],
                'pivot_world':row['vertices'][0], 'edges':[list(edge) for edge in edges]}
        value['meshes'].append(mesh)
        display['objects'].append({'host_id':host_id, 'instance_id':instance_id,
            'visible_get':row['displayed'], 'hide_get':False,'hide_viewport':False,'hide_render':False})
    unsigned = {key:val for key,val in display.items() if key!='sha256'}
    display['sha256'] = sha(encode(unsigned,canonical=True,ensure_ascii=False))
    return value, truth, pin(old_path)


def substitute(example, reference):
    result = copy.deepcopy(example)
    result['query']['objects'][0]['name'] = TARGET
    result['query']['focus']['task_region']['reference']['name'] = reference
    return result


def requests():
    result = [
        ('init','initialize',{'protocolVersion':'2025-03-26','capabilities':{},
                              'clientInfo':{'name':'entry-discovery-offline','version':'1'}}),
        ('tools','tools/list',{}),
    ]

    def call(label, args):
        result.append((label,'tools/call',{'name':TOOL, 'arguments':args}))

    for key, reference in REFERENCE.items():
        args = substitute(EXAMPLE,reference)
        call(f'{key}_advert_default',args)
        call(f'{key}_text_only',{**args,'include_image':False})
    call('unknown_reference',substitute(EXAMPLE,'No fixture by this name'))
    unknown = substitute(EXAMPLE, REFERENCE['K'])
    unknown['query']['objects'][0]['name'] = 'No target by this name'
    call('unknown_target',unknown)
    call('unversioned',substitute(EXAMPLE,REFERENCE['K']))
    call('legacy_auto',{'query':{'mode':'active_observation','objects':[{'name':TARGET}],'focus':'auto'}})
    call('legacy_reference_only',{'query':{'mode':'active_observation','objects':[{'name':TARGET}],
          'focus':{'task_region':{'reference':{'name':REFERENCE['K']}}}}})
    call('directory',{'query':{'mode':'directory'},'include_image':False})
    call('after_rejections',substitute(EXAMPLE,REFERENCE['T']))
    return [{'jsonrpc':'2.0','id':i,'method':method,'params':params} for i,method,params in result]


def worker(folder, custody_path, capture_path):
    custody = read(custody_path)
    site = Path(custody['installation']['path']).resolve(strict=True)
    sys.path.insert(0,str(site))
    from human_eye_plugin import active_observation_images
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.live_spatial_mcp import run_stdio_mcp_server
    from human_eye_plugin.runtime_identity import runtime_identity
    identity = runtime_identity()
    need(identity['source_kind']=='installed_distribution' and identity['source_sha256']==custody['source_sha256']
         and identity['source_files']==custody['source_manifest'], 'actual_installed_release_identity_mismatch')
    capture = read(capture_path)
    current = None
    events, producer = [], {}

    class ReadOnlyHost:
        def capture_scene(self):
            value = copy.deepcopy(capture)
            if current == 'unversioned':
                value['capture_state'] = None
                value['revision'] += '-unversioned'
            events.append({'kind':'sealed_replay_capture','id':current})
            return value

        def capture_directory(self, deadline_ns, max_response_bytes):
            return self.capture_scene()

    class Input:
        def readline(self, size=-1):
            nonlocal current
            line = sys.stdin.readline(size)
            if line:
                current = json.loads(line)['id']
            return line

    config = folder/'PRODUCT_CONFIG.json'
    dump(config, {'schema_version':'1.0','enabled':True,'project_root':str(folder),'state_file':'state.json',
                  'audit_file':'audit.jsonl','request_budget_s':30,
                  'expected_identity':{'source_sha256':identity['source_sha256']}})
    service = LiveSpatialService(config,host=ReadOnlyHost(),production_mode=True)
    service.close = lambda:events.append({'kind':'production_stdin_EOF_close','id':current})
    before = service._observe_active_observation
    raster = active_observation_images.rasterize_attention

    def observed(*args, **kwargs):
        packet = before(*args, **kwargs)
        producer[current] = packet
        return packet

    def rendered(*args, **kwargs):
        events.append({'kind':'software_raster','id':current})
        return raster(*args, **kwargs)

    service._observe_active_observation = observed
    active_observation_images.rasterize_attention = rendered
    try:
        run_stdio_mcp_server(service,input_stream=Input())
    finally:
        dump(folder/'PRODUCER.json',producer)
        dump(folder/'EVENTS.json',events)


def invoke(folder, custody_path, capture_path, request):
    folder.mkdir()
    data = b''.join(encode(row)+b'\n' for row in request)
    (folder/'TX.bin').write_bytes(data)
    cmd = [sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),'worker',str(folder),
           str(custody_path),str(capture_path)]
    start = time.perf_counter_ns()
    proc = subprocess.run(cmd,cwd=folder,input=data,capture_output=True,timeout=65,
                          creationflags=subprocess.CREATE_NO_WINDOW)
    (folder/'RX.bin').write_bytes(proc.stdout)
    (folder/'STDERR.bin').write_bytes(proc.stderr)
    dump(folder/'PROCESS.json',{'command':cmd,'exit_code':proc.returncode,'started_ns':start,
                                'closed_ns':time.perf_counter_ns()})
    need(proc.returncode==0, 'actual_installed_production_stdio_failed/' + folder.name)
    messages = [json.loads(line) for line in proc.stdout.splitlines()]
    need([m['id'] for m in messages]==[packet['id'] for packet in request]
         and messages[0]['result']['_meta']['human_eye']['source_sha256']==read(custody_path)['source_sha256'],
         'actual_stdlib_product_entry_missing_calls')
    events = read(folder/'EVENTS.json')
    need(sum(e['kind']=='production_stdin_EOF_close' for e in events)==1, 'actual_stdio_close_missing')
    return {m['id']:m for m in messages}, read(folder/'PRODUCER.json'), events


def catalogue_difference(a,b):
    a,b = copy.deepcopy(a),copy.deepcopy(b)
    definitions = [next(tool for tool in rows if tool['name']==TOOL) for rows in (a,b)]
    left,right = [definition.pop('description') for definition in definitions]
    need(a==b and left!=right, 'A/B_catalogue_has_additional_or_missing_difference')
    untouched = left[len(PREFACE):]
    need(left.startswith(PREFACE) and right.startswith(PREFACE) and right.endswith(untouched),
         'old_description_text_not_preserved')
    inserted = right[len(PREFACE):len(right)-len(untouched)]
    start = inserted.index('{"query"')
    example,end = json.JSONDecoder().raw_decode(inserted[start:])
    need(example==EXAMPLE and inserted.count('{"query"')==1, 'advert_not_identical_to_tested_example')
    return {'A_description_bytes':len(left.encode('utf8')),'B_description_bytes':len(right.encode('utf8')),
            'added_description_bytes':len(inserted.encode('utf8')),'inserted':inserted,'example':example}


def proof_frame(folder, reply, producer, capture, truth_entry):
    import io
    import numpy as np
    from PIL import Image
    body = get_body(reply)
    focus = body['facts']['focus']
    sample = focus['sample']
    measured = focus['nearest_surface']
    witness = measured['witness']
    mesh_index, = [i for i,m in enumerate(capture['meshes']) if m['name']==TARGET]
    slots = [next(m for m in capture['meshes'] if m['name']==name)
             for name in (TARGET,truth_entry['reference_name'])]
    near = truth_entry['nearest_source_triangle_indices']
    rows = [witness[key]['source_triangle_index'] for key in ('a','b')]
    choices = {(r['target_source_triangle_index'],r['reference_source_triangle_index'])
               for r in truth_entry['nearest_triangle_pairs']}
    need(tuple(rows) in choices and rows[0] in near and rows[0]==focus['primary_source_triangle_index'],
         'M3_winner_not_on_independent_true_near_component')
    points = [vector(witness[key]['point_m']) for key in ('a','b')]
    for side,mesh,point,row in zip(('a','b'),slots,points,rows,strict=True):
        instance = capture['host_identity']['object_instances'][mesh['object_id']]
        need(witness[side]['host_id']==mesh['object_id'] and witness[side]['instance_id']==instance
             and on_triangle(point,[vector(mesh['vertices'][i]) for i in mesh['faces'][row]]),
             'source_triangle_witness_not_on_actual_reopened_mesh')
    squared = min(map(Fraction,truth_entry['distances_squared_m2']))
    distance = math.sqrt(float(squared))
    delta = subtract(*points)
    need(dot(delta,delta)==squared and math.isclose(measured['distance_m'],distance,rel_tol=1e-15,abs_tol=0),
         'published_global_nearest_distance_wrong')
    public, = body['frames']
    local, = producer['frames']
    paths = [Path(local[key]).resolve(strict=True) for key in ('image_path','arrays_path')]
    image,arrays = paths
    need(all(p.is_relative_to(folder) for p in paths) and Path(public['image_path']).resolve(strict=True)==image
         and all(public[key]==local[key]==sample[key] for key in ('frame_identity','image_ref','view_name')),
         'default_brief_path_or_frame_ref_not_bound')
    img, = [b for b in reply['result']['content'] if b['type']=='image']
    raw = base64.b64decode(img['data'],validate=True)
    need(img['mimeType']=='image/png' and raw==image.read_bytes() and sha(raw)==local['image_sha256']
         and public['image_sha256']==local['image_sha256'] and sha(arrays.read_bytes())==local['arrays_sha256'],
         'same_slot_original_PNG_or_NPZ_missing')
    pixel = sample['sampled_pixel']
    y,x = pixel['row'], pixel['column']
    with np.load(arrays,allow_pickle=False) as npz, Image.open(io.BytesIO(raw)) as png:
        valid = (npz['owners']==mesh_index)&np.isfinite(npz['depth'])
        local_ids = npz['triangle_ids']-npz['face_patch_offsets'][mesh_index]
        mask = valid & np.isin(local_ids,near)
        count = int(np.count_nonzero(mask))
        need(count>=16 and mask[y,x] and int(local_ids[y,x])==pixel['source_triangle_index']==rows[0]
             and np.array_equal(np.asarray(png),npz['color']), 'actual_finite_PNG_pixel_source_mismatch')
    return {'source_rows':rows,'distance_m':measured['distance_m'],'nearest_component_pixels':count,
            'first_surface_image':local['view_name'],'anchor':pixel,
            'frame_identity':local['frame_identity'],'image_ref':local['image_ref'],
            'PNG':pin(image),'NPZ':pin(arrays)}


def tools(result):
    return result['tools']['result']['tools']


def run(b_custody, *, existing=False):
    capture,truth,template = sealed_capture()
    capture_path = OUT/'OFFLINE_CAPTURE.json'
    arms = (('A',A_CUSTODY),('B',b_custody))
    if existing:
        need(read(capture_path)==capture, 'replay_capture_changed_after_first_attempt')
        history=[]
        for arm,custody in arms:
            folder=OUT/arm
            data=b''.join(encode(row)+b'\n' for row in requests())
            source=read(folder/'PROCESS.json')
            need((folder/'TX.bin').read_bytes()==data and source['exit_code']==0
                 and source['command'][-2:]==[str(custody),str(capture_path)],
                 'initial_custody_or_request_changed/'+arm)
            replies={m['id']:m for m in (json.loads(line) for line in (folder/'RX.bin').read_bytes().splitlines())}
            events=read(folder/'EVENTS.json')
            need(list(replies)==[r['id'] for r in requests()]
                 and replies['init']['result']['_meta']['human_eye']['source_sha256']==read(custody)['source_sha256']
                 and sum(e['kind']=='production_stdin_EOF_close' for e in events)==1,
                 'initial_endpoint_incomplete_or_misbound/'+arm)
            history.append((replies,read(folder/'PRODUCER.json'),events))
    else:
        OUT.mkdir()
        dump(capture_path,capture)
        history = [invoke(OUT/arm,custody,capture_path,requests()) for arm,custody in arms]
    a,b = [item[0] for item in history]
    diff = catalogue_difference(tools(a),tools(b))
    checks = {}
    for key in REFERENCE:
        label = key+'_advert_default'
        checks[label] = {arm:proof_frame(OUT/arm,result[label],raw[label],capture,truth['cases'][key])
                         for arm,(result,raw,events) in zip('AB',history,strict=True)}
        first,second = [checks[label][side] for side in 'AB']
        need(all(first[k]['sha256']==second[k]['sha256'] for k in ('PNG','NPZ')),'description_changed_frame_bytes')
        label = key+'_text_only'
        for result,_,_ in history:
            value = get_body(result[label])
            facts = value['facts']['focus']
            need(value['status']=='predicted' and value['frames']==[] and facts['sample'] is None
                 and facts['nearest_surface']['status']=='measured' and len(result[label]['result']['content'])==1,
                 'no_image_request_changed_or_rasterized')
        checks[label]={'A_B_same_measured_facts':get_body(a[label])['facts']==get_body(b[label])['facts']}
        need(checks[label]['A_B_same_measured_facts'],'text_only_semantic_drift')
    for label in ('unknown_reference','unknown_target'):
        left,right = [get_body(reply[label],error=True) for reply in (a,b)]
        need(left['error']==right['error'] and 'No ' not in left['error'],'unknown_public_error_changed')
        checks[label]={'same_exact_error':left['error']}
    for result,_,_ in history:
        unversioned = get_body(result['unversioned'])
        need(unversioned['status']=='unknown' and not unversioned['frames']
             and unversioned['facts']['focus']['nearest_surface']['reason']=='capture_generation_unavailable',
             'unversioned_source_falsely_admitted')
    checks['unversioned']={'unknown_without_frame':True}
    for name in ('legacy_auto','legacy_reference_only','after_rejections'):
        left,right = [get_body(x[name]) for x in (a,b)]
        need(left['facts']==right['facts'] and
             left['frames'][0]['image_sha256']==right['frames'][0]['image_sha256'],
             'legacy_or_recovery_contract_drift/'+name)
        checks[name] = {'same_facts_and_image':True}
    left,right=[get_body(x['directory'],error=True) for x in (a,b)]
    need(left['error']==right['error']=='directory_response_contract','legacy_directory_rejection_changed')
    checks['legacy_directory_missing_fixture_capture']={'same_exact_error':left['error'],
        'scope':'The fixture supplies a complete evaluated scene, not a native directory packet. Directory success is not claimed.'}
    dump(PRODUCT_RESULT,{'passed':True,'batch':BATCH,'catalogue':diff,'checks':checks,'controls_passed':len(checks),
         'offline_software_rasters':{arm:sum(e['kind']=='software_raster' for e in arm_result[2])
                                    for arm,arm_result in zip('AB',history,strict=True)},
         'Blender':0,'models':0,'script':pin(__file__),'transport_shape':'actual installed production stdio, replayed current fixture',
         'child_processes':2,'product_A':pin(A_CUSTODY),'product_B':pin(b_custody),
         'qualifier_correction':{'first_comparison_source_sha256':'3793ebb0c8c36116f037ef0cf35ac37b4f76261d345c1bc0330066d4c0505d54',
           'reason':'The extra directory case must reject the synthetic complete-capture reply consistently. First tool responses and legacy error are preserved.',
           'original_processes_replayed':existing},
         'fixture':[pin(p) for p in (FIXTURE/'main.blend',FIXTURE/'TARGET_TRUTH.json',FIXTURE/'EVALUATED_SOURCE.json',
                                    capture_path)],'synthetic_host_metadata_template':template,
         'arms':{arm:{key:pin(OUT/arm/key) for key in ('TX.bin','RX.bin','PRODUCER.json','EVENTS.json','PROCESS.json')}
                 for arm in 'AB'}})


def joint():
    smoke=read(PRODUCT_RESULT)
    natural=read(PRE/'NATURAL_COLD.json')
    need(smoke['passed'] and natural['passed'],'both_product_and_natural_cold_required')
    natural_tools={}
    raw_pins={}
    for arm in 'AB':
        raw=PRE/'natural_cold'/arm/'wire/002/RX.bin'
        actual=read(raw)['result']['tools']
        need(actual==natural['arms'][arm]['actual_tools'],'published_natural_tool_directory_changed')
        source_wire=smoke['arms'][arm]['RX.bin']
        need(pin(source_wire['path'])==source_wire,'frozen_actual_product_directory_changed')
        directory=next(json.loads(line)['result']['tools'] for line in Path(source_wire['path']).read_bytes().splitlines()
                       if json.loads(line)['id']=='tools')
        need(next(row for row in actual if row['name']==TOOL)==next(row for row in directory if row['name']==TOOL),
             'natural_caller_did_not_receive_actual_installed_tool_definition')
        natural_tools[arm]=actual
        raw_pins[arm]=pin(raw)
    difference=catalogue_difference(natural_tools['A'],natural_tools['B'])
    need(difference==smoke['catalogue'],'natural_caller_received_different_description_change')
    dump(JOINT_RESULT,{'passed':True,'parent':pin(PRODUCT_RESULT),'natural_cold':pin(PRE/'NATURAL_COLD.json'),
         'actual_natural_directories':raw_pins,'single_difference':difference,'Blender':0,'models':0})


if __name__ == '__main__':
    need(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_python_required')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('run','evaluate','worker','joint'))
    parser.add_argument('paths',nargs='*',type=Path)
    args=parser.parse_args()
    if args.mode=='worker':
        worker(*args.paths)
    elif args.mode in ('run','evaluate'):
        run(*args.paths,existing=args.mode=='evaluate')
    else:
        joint()

"""Verify both real installed closures and scoped component evidence on sealed Blender data."""
from collections import deque
from copy import deepcopy
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent/'m1_nearest_surface_entry_discovery_001'/'entry_verify_public.py'
spec = importlib.util.spec_from_file_location('sealed_frame_verifier', PRIOR)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
prior.TARGET = 'Item X'
BATCH = 'M4-NEAREST-SURFACE-COMPONENT-REF-001'
SCOPE = 'one_target_vertex_connected_component_to_reference_whole_object'
REFERENCES = {'K':'Item G', 'T':'Item Q'}
BASE = '5c3ee219ae51a095ef26ec6bc71e11cafe937413372cc65a245e601a5710de85'
need, pin, read, dump, encode = prior.need, prior.pin, prior.read, prior.dump, prior.encode
body = prior.get_body


def confirmed(record):
    need(pin(record['path']) == record, 'evidence_changed')
    return Path(record['path'])


def lines(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def ref_args(scope, reference):
    return {'query':{'mode':'source_region','region_ref':scope,'reference':{'name':reference},
                     'requested_facts':['surface_proximity']},'include_image':False,'response_detail':'brief'}


def component_rows(faces, origin):
    # Independent all-pairs overlap traversal. Offline fixture, independent of the production index.
    remaining = set(range(len(faces))) - {origin}
    queue = deque([origin])
    seen = {origin}
    while queue:
        face = set(faces[queue.popleft()])
        following = {row for row in remaining if face.intersection(faces[row])}
        remaining -= following
        seen |= following
        queue.extend(following)
    return sorted(seen)


def pin_exchange(row):
    return {key: pin(confirmed(row[key])) for key in ('tx','rx')}


def verify_close(folder, recorded):
    wire = lines(folder/'wire/INDEX.jsonl')
    both = [lines(folder/f'TRANSPORT_{side}.jsonl') for side in ('OWNER','THIN')]
    messages = lines(folder/'THIN_STDOUT.bin')
    closure = read(folder/'TRANSPORT_OWNER.json')
    need(closure == recorded and closure['closed'] and closure['zero_in_flight']
         and closure['paired_exchanges'] == len(wire) == len(messages)
         and all(len(part) == len(wire) for part in both)
         and closure['Thin_process']['exit_code'] == 0, 'actual_thin_close_or_inventory')
    for receipt, left, right, public in zip(wire, *both, messages, strict=True):
        tx, rx = (confirmed(receipt[key]) for key in ('tx','rx'))
        match = left['request']
        need(match == right['request'] and left['offer'] == right['offer'] and left['ack'] == right['ack']
             and left['peer_eof'] and right['peer_eof'] and match['request_sha256'] == pin(tx)['sha256']
             and match['response_sha256'] == pin(rx)['sha256'] and public == read(rx),
             'thin_both_sides_source_or_response_mismatch')
    need(closure['last_paired']['request']['ordinal'] == wire[-1]['ordinal'], 'last_exchange_mismatch')
    return wire


def focus_value(folder, request, capture, truth_entry, *, expect_component):
    tx, rx, producer = (read(folder/file) for file in ('TX.bin','RX.bin','PRODUCER.json'))
    need(tx['params']['arguments'] == request, 'advertised_call_changed')
    raw = body(rx)
    facts = raw['facts']['focus']
    raw_near = facts['nearest_surface']
    nearest = dict(raw_near)
    evidence = nearest.pop('component', None)
    frame = prior.proof_frame(folder.parents[1], rx, producer, capture, truth_entry)
    component_ref = None
    if expect_component:
        need(type(evidence) is dict and evidence['scope'] == SCOPE and evidence['status'] == 'measured'
             and evidence['distance_m'] == nearest['distance_m'], 'missing_component_witness')
        component_ref = evidence['region_ref']
        target = next(mesh for mesh in capture['meshes'] if mesh['name'] == prior.TARGET)
        winning = facts['primary_source_triangle_index']
        rows = component_rows(target['faces'], winning)
        need(rows == truth_entry['nearest_source_triangle_indices'] == component_ref['source_triangle_indices'],
             'component_failed_independent_full_connectivity')
        one = facts['region_ref']
        need(one['source_triangle_indices'] == [winning]
             and all(one[key]==component_ref[key] for key in one if key not in ('source_triangle_indices','region_id'))
             and component_ref['region_id'] != one['region_id']
             and evidence == producer['facts']['focus']['nearest_surface']['component'],
             'component_ref_does_not_share_original_source_binding')
        raw_size = len(encode(evidence, ensure_ascii=False))
        need(raw_size <= 1024, 'component_text_budget')
    else:
        need(evidence is None, 'baseline_contains_candidate_component')
        raw_size = 0
    return {'frame':frame,'nearest_without_component':nearest,'component':evidence,'component_ref':component_ref,
            'original_ref':facts['region_ref'],'visible_shape':facts['scope'],'selection':facts['task_source_triangle_indices'],
            'text_bytes':sum(len(row['text'].encode('utf8')) for row in rx['result']['content'] if row['type']=='text'),
            'new_component_bytes':raw_size,'work':producer.get('work'), 'stages':producer.get('stages'),
            'generation_work':producer.get('generation_work'), 'generation_stages':producer.get('generation_stages'),
            'producer':pin(folder/'PRODUCER.json')}


def measure(reply, request, scope, value, capture):
    result = body(reply)
    task = result['task_result']
    wanted = request['query']['reference']['name']
    reference = next(mesh for mesh in capture['meshes'] if mesh['name'] == wanted)
    fact = task['facts']['surface_proximity']
    observed = fact['value']
    provenance = task['source_mapping']['nearest_witness']
    need(result['region_ref'] == scope and task['reference']['name'] == wanted
         and task['reference']['object_id'] == reference['object_id']
         and task['reference']['instance_id'] == capture['host_identity']['object_instances'][reference['object_id']]
         and task['measurement_scope'] == 'complete_selected_source_triangle_union_to_reference_triangle_surface'
         and fact['status'] == 'measured' and observed['distance_m'] == value
         and not any(row['type']=='image' for row in reply['result']['content']), 'public_source_region_scope_or_fact_mismatch')
    points = observed['nearest_witness']
    if 'nearest_witness_exact' not in observed:
        a_mesh = next(mesh for mesh in capture['meshes'] if mesh['object_id'] == scope['host_id'])
        for side, mesh, acceptable in (('a',a_mesh, scope['source_triangle_indices']),
                                        ('b', reference, range(len(reference['faces'])))):
            rows = provenance[side]['source_triangle_indices']
            point = prior.vector(points[side])
            need(set(rows) <= set(acceptable) and any(
                prior.on_triangle(point,[prior.vector(mesh['vertices'][i]) for i in mesh['faces'][row]])
                for row in rows), 'returned_nearest_point_is_off_source')
    return {'rows':scope['source_triangle_indices'],'distance_m':value,'reference':wanted}


def verify_thin(root):
    capture = read(root/'preflight/SEALED_CAPTURE.json')
    current = read(root/'preflight/NATURAL_COLD.json')
    all_truth = read(root/'preflight/fixture/TARGET_TRUTH.json')['cases']
    need(current['passed'] and current['same_actual_catalogue'], 'actual_cold_directory_parity_failed')
    proof = {}
    catalogue = None
    for arm in ('A','B'):
        folder = root/'preflight/natural_cold'/arm
        arm_result = current['arms'][arm]
        need(arm_result['passed'], 'actual_cold_arm_fail_'+arm)
        wire = verify_close(folder,arm_result['closure'])
        tools = read(confirmed(wire[1]['rx']))['result']['tools']
        init = read(confirmed(wire[0]['rx']))['result']['_meta']['human_eye']
        expected = BASE if arm=='A' else read(root/'preflight/INSTALL_CUSTODY.json')['source_sha256']
        need(init['source_sha256']==expected and init['source_kind']=='installed_distribution'
             and tools==arm_result['actual_tools'] and len(tools)==5, 'wrong_actual_installed_directory_or_version')
        if catalogue is None:
            catalogue = tools
        need(tools == catalogue, 'actual_directory_diff')
        paired = {}
        for ordinal, label in ((6,'K'),(7,'T')):
            row = wire[ordinal-1]
            req = read(confirmed(row['tx']))['params']['arguments']
            need(req['query']['focus']['task_region']=={'reference':{'name':REFERENCES[label]},
                   'relation':'nearest_surface'}, 'preflight_reference_not_matched')
            paired[label] = focus_value(confirmed(row['tx']).parent,req,capture,all_truth[label],
                                        expect_component=arm=='B')
            value = paired[label]
            expected_ref = value['component_ref'] if arm=='B' else value['original_ref']
            probe = next(probe for probe in wire[7:] if read(confirmed(probe['tx']))['params']['arguments']
                         == ref_args(expected_ref, REFERENCES[label]))
            value['reference_probe'] = measure(read(confirmed(probe['rx'])),
                read(confirmed(probe['tx']))['params']['arguments'],expected_ref,
                value['nearest_without_component']['distance_m'],capture)
            value['wire'] = pin_exchange(row)
            value['reference_wire'] = pin_exchange(probe)
        if arm=='B':
            value = paired['K']
            ref = value['original_ref']
            probe = next(probe for probe in wire[7:] if read(confirmed(probe['tx']))['params']['arguments']
                         == ref_args(ref, REFERENCES['K']))
            value['original_single_ref_probe'] = measure(read(confirmed(probe['rx'])),
                read(confirmed(probe['tx']))['params']['arguments'], ref,
                value['nearest_without_component']['distance_m'],capture)
        proof[arm]={'cases':paired,'raw_wire':pin(folder/'wire/INDEX.jsonl'),
                    'closure':pin(folder/'TRANSPORT_OWNER.json'),'public_stdout':pin(folder/'THIN_STDOUT.bin'),
                    'catalogue':pin(confirmed(wire[1]['rx']))}
    for label in 'KT':
        a,b = (proof[arm]['cases'][label] for arm in ('A','B'))
        need(a['nearest_without_component']==b['nearest_without_component']
             and a['original_ref']==b['original_ref'] and a['selection']==b['selection']
             and a['visible_shape']==b['visible_shape']
             and all(a['frame'][key]['sha256']==b['frame'][key]['sha256'] for key in ('PNG','NPZ'))
             and a['frame']['anchor']==b['frame']['anchor']
             and a['frame']['nearest_component_pixels']==b['frame']['nearest_component_pixels'],
             'candidate_changed_single_face_or_raster')
        b['brief_added_bytes']=b['text_bytes']-a['text_bytes']
    return proof


def worker(folder, site, capture_path):
    sys.path.insert(0,str(site))
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.live_spatial_mcp import run_stdio_mcp_server
    capture = read(capture_path)
    target = 'Item X'
    current = None
    events = []
    producer = {}

    class Host:
        def capture_scene(self):
            value = deepcopy(capture)
            mesh = next(row for row in value['meshes'] if row['name'] == target)
            if current == 'old_instance':
                host_id = mesh['object_id']
                instance = 'qualification-replaced-instance'
                value['host_identity']['object_instances'][host_id] = instance
                display = value['display_snapshot']
                next(row for row in display['objects'] if row['host_id'] == host_id)['instance_id'] = instance
                display['sha256'] = prior.sha(encode({k:v for k,v in display.items() if k!='sha256'},
                                                      canonical=True,ensure_ascii=False))
            if current == 'old_generation':
                value['capture_state']['revision'] += 1
                value['revision'] += '-next-revision'
            if current == 'old_order':
                mesh['faces'][0],mesh['faces'][1] = mesh['faces'][1],mesh['faces'][0]
            if current == 'unversioned':
                value['capture_state'] = None
            events.append({'capture':current})
            return value

        def capture_directory(self, deadline_ns, max_response_bytes):
            return self.capture_scene()

        def close(self):
            events.append({'production_close':current})

    class Input:
        def readline(self, size=-1):
            nonlocal current
            line = sys.stdin.readline(size)
            if line:
                current = json.loads(line)['id']
            return line

    config = folder/'PRODUCT_CONFIG.json'
    dump(config, {'schema_version':'1.0','enabled':True,'project_root':str(folder),'state_file':'state.json',
                  'audit_file':'audit.jsonl','request_budget_s':30})
    service = LiveSpatialService(config,host=Host(),production_mode=True)
    orig = service._observe_active_observation

    def observe(*args,**kwargs):
        value=orig(*args,**kwargs)
        producer[current]=value
        return value

    service._observe_active_observation = observe
    try:
        run_stdio_mcp_server(service,input_stream=Input())
    finally:
        dump(folder/'PRODUCER.json',producer)
        dump(folder/'EVENTS.json',events)


def full_controls(root, proof):
    custody = read(root/'preflight/INSTALL_CUSTODY.json')
    site = Path(custody['installation']['path']).resolve(strict=True)
    capture_path = root/'preflight/SEALED_CAPTURE.json'
    capture = read(capture_path)
    candidate = proof['B']['cases']
    region = candidate['K']['component_ref']
    nearest = candidate['K']['nearest_without_component']
    requests = [{'jsonrpc':'2.0','id':'init','method':'initialize','params':{
        'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'component-ref-proof','version':'1'}}}]
    def call(label,args):
        requests.append({'jsonrpc':'2.0','id':label,'method':'tools/call','params':{'name':prior.TOOL,'arguments':args}})
    for tag in ('K','T'):
        original = read(confirmed(candidate[tag]['wire']['tx']))['params']['arguments']
        call('full_'+tag,{**original,'response_detail':'full'})
    exact = read(confirmed(candidate['K']['wire']['tx']))['params']['arguments']
    call('warm_K',{**exact,'response_detail':'full'})
    for tag in ('old_instance','old_generation','old_order','recovered'):
        call(tag,ref_args(region,REFERENCES['K']))
    call('unversioned',{**exact,'include_image':False})
    call('legacy',{'query':{'mode':'active_observation','objects':[{'name':prior.TARGET}],'focus':'auto'},
                   'include_image':False})
    folder = root/'preflight/full_controls'
    folder.mkdir(exist_ok=False)
    inp = folder/'TX.bin'
    inp.write_bytes(b''.join(encode(packet)+b'\n' for packet in requests))
    cmd = [sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),'worker',
           str(folder),str(site),str(capture_path)]
    started = time.perf_counter_ns()
    run = subprocess.run(cmd,input=inp.read_bytes(),capture_output=True,timeout=75,cwd=folder,
                         creationflags=subprocess.CREATE_NO_WINDOW)
    (folder/'STDOUT.bin').write_bytes(run.stdout)
    (folder/'STDERR.bin').write_bytes(run.stderr)
    dump(folder/'PROCESS.json',{'started_ns':started,'closed_ns':time.perf_counter_ns(),'exit':run.returncode,
                                'argv':cmd,'stdin':pin(inp),'stdout':pin(folder/'STDOUT.bin')})
    need(run.returncode==0,'production_stdio_full_control_exit')
    received = lines(folder/'STDOUT.bin')
    need([row['id'] for row in received]==[row['id'] for row in requests]
         and received[0]['result']['_meta']['human_eye']['source_sha256']==custody['source_sha256']
         and read(folder/'EVENTS.json')[-1]=={'production_close':'legacy'}, 'correct_stdio_init_close_or_inventory')
    lookup={row['id']:row for row in received}
    producer=read(folder/'PRODUCER.json')
    full={}
    all_truth=read(root/'preflight/fixture/TARGET_TRUTH.json')['cases']
    for tag in ('K','T'):
        label='full_'+tag
        packet=body(lookup[label])
        proof_frame=prior.proof_frame(folder,lookup[label],producer[label],capture,all_truth[tag])
        facts=packet['facts']['focus']
        need(facts['nearest_surface']['component']==candidate[tag]['component']
             and facts['region_ref']==candidate[tag]['original_ref']
             and proof_frame['PNG']['sha256']==candidate[tag]['frame']['PNG']['sha256']
             and proof_frame['NPZ']['sha256']==candidate[tag]['frame']['NPZ']['sha256'], 'actual_full_changed_image_or_component')
        full[tag]={'frame':proof_frame,'work':producer[label]['work'],'stages':producer[label]['stages'],
                   'text_bytes':sum(len(item['text'].encode('utf8')) for item in lookup[label]['result']['content']
                                    if item['type']=='text')}
    hot=body(lookup['warm_K'])
    need(hot['facts']['focus']['nearest_surface']['component']==candidate['K']['component']
         and producer['warm_K']['work']['raster_attempts']==0, 'hot_read_rebuilt_or_lost_component')
    errors={}
    for label,reason in (('old_instance','source_region_ref_object_instance_changed'),
                         ('old_generation','source_region_ref_capture_generation_changed'),
                         ('old_order','source_region_ref_ordered_geometry_changed')):
        response=body(lookup[label],error=True)
        need(reason in json.dumps(response,ensure_ascii=False),'mismatched_source_ref_rejection_reason_'+label)
        errors[label]=reason
    recovered=measure(lookup['recovered'],ref_args(region,REFERENCES['K']),region,nearest['distance_m'],capture)
    unknown=body(lookup['unversioned'])['facts']['focus']['nearest_surface']
    need(unknown['status']=='unknown' and unknown.get('component',{}).get('status')!='measured',
         'unversioned_result_emitted_component')
    need('nearest_surface' not in body(lookup['legacy'])['facts']['focus'], 'ordinary_focus_changed')
    return {'cases':full,'hot_work':producer['warm_K']['work'],'hot_stages':producer['warm_K']['stages'],
            'generation_work':producer['warm_K'].get('generation_work'),'reject':errors,'recovered':recovered,
            'unversioned':unknown, 'actual_process':pin(folder/'PROCESS.json'),'real_close':pin(folder/'EVENTS.json')}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=('verify','worker'))
    p.add_argument('paths',nargs='+',type=Path)
    args=p.parse_args()
    if args.phase=='worker':
        worker(*args.paths)
        return
    root,=args.paths
    need(root.name==BATCH and not (root/'slots').exists(),'unregistered_or_started_batch')
    stage='same_actual_thin'
    out=root/'preflight/COMPONENT_PRODUCT_PREFLIGHT.json'
    try:
        arms=verify_thin(root)
        stage='actual_production_stdio_controls'
        full=full_controls(root,arms)
        dump(out,{'passed':True,'batch':BATCH,'actual_cold':pin(root/'preflight/NATURAL_COLD.json'),
                  'custody':pin(root/'preflight/INSTALL_CUSTODY.json'),'script':pin(__file__),
                  'frame_verifier':pin(PRIOR),'source':pin(root/'preflight/FIXTURE_CUSTODY.json'),
                  'same_actual_catalogue':True,'arms':arms,'full_controls':full,'Blender':0,'models':0})
    except (ValueError,FileNotFoundError,IndexError,TypeError,KeyError,StopIteration,subprocess.TimeoutExpired) as error:
        dump(out,{'passed':False,'batch':BATCH,'stage':stage,'error':f'{type(error).__name__}: {error}',
                  'script':pin(__file__),'Blender':0,'models':0})
        raise


if __name__ == '__main__':
    main()


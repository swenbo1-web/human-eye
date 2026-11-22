"""Verify actual held-stdio replay outputs and the frozen paired thresholds."""

import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
from statistics import median


NS = Path(__file__).resolve().parent
V = NS.parent
H = run_path(str(NS/'qualification.py'))
pin, read, require, digest = (H[key] for key in ('pin','read','require','digest'))
PRIOR = run_path(str(V/'m4_local_coverage_object_bounds_001/checks/replay.py'))
CLI = run_path(str(V/'m1_region_task_first_packet_consumption_holdout_001/checks/evidence.py'))['fixed_cli']
PAIRS = (('N1','P1'),('N2','P2'),('N3','P3'),('HN','HP'),('RN','RP'),('CN','CP'))
ROI = ('0135bbc4-c6c7-4003-a402-6f2e0283497d','Cube')


def normal(value, paths, source):
    if isinstance(value,(list,tuple)):
        return [normal(item,paths,source) for item in value]
    if isinstance(value,dict):
        output = {}
        for key,item in value.items():
            if key in ('work','generation_work','stages','generation_stages','feedback_stages','request_trace','session_id',
                       'frame_reuses','new_raster_attempts'):
                continue
            if key == 'runtime_source_sha256':
                require(item==source,'result_is_not_bound_to_installed_package')
                output[key] = 'verified_runtime'
            else:
                output[key] = normal(item,paths,source)
        return output
    return paths.get(value,value) if isinstance(value,str) else value


def verify_wire(root, row, worker):
    live = row['wire']
    wire = root/'mcp'/f"rpc_{live['index']:02d}"
    receipt_path,tx_path,rx_path = (wire/name for name in ('RECEIPT.json','TX.bin','RX.bin'))
    receipt = read(receipt_path)
    require(receipt=={k:v for k,v in live.items() if k!='TX_sha256'},'stock_wire_receipt_changed')
    tx_raw,raw = tx_path.read_bytes(),rx_path.read_bytes()
    tx,rpc = json.loads(tx_raw),json.loads(raw)
    rx_lf = raw.replace(b'\r\n',b'\n')
    require(tx['id']==rpc['id']==worker['id']==worker['response_id']==live['id']
            and worker['sequence']==live['index'] and tx['method']=='tools/call'
            and digest(raw)=={'bytes':live['RX_bytes'],'sha256':live['RX_sha256']}
            and digest(tx_raw)=={'bytes':worker['TX_bytes'],'sha256':worker['TX_sha256']}
            and len(tx_raw)==live['TX_bytes']
            and digest(rx_lf)=={'bytes':worker['RX_text_UTF8_LF_bytes'],'sha256':worker['RX_text_UTF8_LF_sha256']},
            'actual_both_wire_ends_changed/'+root.name)
    blocks = rpc['result']['content']
    text, = [block['text'] for block in blocks if block['type']=='text']
    pngs = [base64.b64decode(block['data'],validate=True) for block in blocks if block['type']=='image']
    require(len(text.encode('utf8'))==row['text_bytes'] and sum(map(len,pngs))==row['PNG_bytes']
            and receipt['closed_ns']-receipt['started_ns']==receipt['elapsed_ns']>0,
            'wire_text_image_or_clock_changed/'+root.name)
    try:
        body = json.loads(text)
    except ValueError:
        require(rpc['result']['isError'],'success_output_not_json')
        body = text
    return tx,rpc,body,pngs,{'TX':pin(tx_path),'RX':pin(rx_path)}


def frame_roster(root, frames, historical):
    mapped = {}
    saved = []
    require(len(frames)==len(historical),'current_expected_constructed_roster')
    for row,old in zip(frames,historical,strict=True):
        require((row.get('scope_id'),row['view_name'])==(old.get('scope_id'),old['view_name']),
                'frame_view_or_scope_differs_from_frozen_original')
        clean = {'view_name':row['view_name']}
        for kind in ('png','arrays'):
            current = row[kind]
            file = PRIOR['check_pin'](current,root)
            require({key:current[key] for key in ('bytes','sha256')}==
                    {key:old[kind][key] for key in ('bytes','sha256')},'PNG_NPZ_changed_from_historical_original')
            mapped[str(file)] = mapped[file.as_posix()] = current['sha256']
            clean[kind] = current
        saved.append(clean)
    return saved,mapped


def verify_region(producer, body, pngs, root, fixture):
    frames = producer['frames']
    binding = producer['binding']
    visibility = producer['facts']['visibility']
    require(producer['read_only'] is True and producer['execution_authority'] is False
            and body['read_only'] is True and body['execution_authority'] is False
            and body['region_ref']==producer['region_ref']
            and body['task_result']['facts']==producer['task_result']['facts']
            and len(pngs)==len(frames),'source_region_result_projection_mismatch')
    if not frames:
        if fixture=='main' and len(producer['region_ref']['source_triangle_indices'])==331:
            fact = producer['task_result']['facts']['surface_proximity']
            value = fact['value']
            require(fact['status']=='measured' and value['distance_m']==0.4355468820753541
                    and value['nearest_witness']['direction_a_to_b']==[0.0,0.0,1.0],
                    'main_lower_no_image_measurement_changed')
        return None
    frame, = frames
    data, = pngs
    if 'images' in body:
        public, = body['images']
        require(public['image_block_index']==1 and all(public[k]==frame[k] for k in
                ('image_ref','view_name','frame_identity','image_sha256','host_binding_sha256')),
                'image_block_is_not_own_current_region_frame')
        public_path = public.get('local_image_path')
    else:
        public, = body['frames']
        require(pointwise_frame(public,frame),'full_image_is_not_own_current_frame')
        public_path = public['image_path']
    image = Path(frame['image_path']).resolve(strict=True)
    arrays = Path(frame['arrays_path']).resolve(strict=True)
    require(image.is_relative_to(root) and arrays.is_relative_to(root) and image.read_bytes()==data
            and sha256(data).hexdigest()==frame['image_sha256']
            and sha256(arrays.read_bytes()).hexdigest()==frame['arrays_sha256']
            and visibility['frame_identity']==frame['frame_identity']
            and visibility['image_ref']==frame['image_ref']
            and binding['binding_sha256']==frame['host_binding_sha256'],
            'closed_path_bytes_or_current_capture_frame_mismatch')
    if public_path is not None:
        require(Path(public_path).resolve(strict=True)==image and public_path in (image.as_posix(),str(image)),
                'noncanonical_or_wrong_public_path')
    vis = {'status':visibility['status'],'view':frame['view_name'],
           'samples':visibility['selected_surface_pixels'],'sampled_triangles':len(visibility['visible_source_triangle_indices']),
           'complete':visibility['complete_witness'] is not None,
           'png':pin(image),'arrays':pin(arrays),'closed_public_path_usable':public_path is not None}
    if fixture == 'main':
        fact = producer['task_result']['facts']['surface_proximity']
        value = fact['value']
        p1,p2 = ROI
        require((producer['facts']['region']['object_name'],producer['task_result']['reference']['name'])==(p1,p2)
                and len(producer['region_ref']['source_triangle_indices'])==311
                and (vis['view'],vis['samples'],vis['sampled_triangles'],vis['complete'])==('SCENE',49480,116,False)
                and vis['status']=='observed_samples' and vis['closed_public_path_usable']
                and fact['status']=='measured' and value['distance_m']==0.37011719389236364
                and value['nearest_witness']['direction_a_to_b']==[0.0,0.0,1.0],
                'main_Yanyite_same_region_pixel_or_measurement_changed')
    elif fixture == 'rectangle':
        require(producer['facts']['region']['object_name']=='N15'
                and producer['region_ref']['source_triangle_indices']==[20,21]
                and vis['view']=='RIGHT' and vis['complete'] and vis['closed_public_path_usable'],
                'rectangular_RIGHT_control_changed')
    else:
        require(vis['samples']>0 and vis['status']=='observed_samples' and not vis['complete'],
                'held_nonplanar_selected_evidence_changed')
    return vis


def pointwise_frame(a,b):
    return all(a[k]==b[k] for k in ('image_ref','view_name','frame_identity','image_sha256'))


def clocks(stages):
    found = {}
    for name,row in stages.items():
        if not isinstance(row,dict) or 'elapsed_ns' not in row:
            continue
        require(row['elapsed_ns']==row['closed_ns']-row['started_ns']>=0,'stage_clock_not_its_own_interval/'+name)
        found[name]=row['elapsed_ns']
    return found


def inspect_arm(root,fixture,control,binding):
    summary = read(root/'SUMMARY.json')
    product = summary['product']
    require(summary['passed'] is True and summary['fixture']==fixture
            and summary['controls']==control and summary['arm']==root.name
            and all(product[k]==binding[k] for k in ('source_sha256','preparation_git','wheel_sha256')),
            'arm_fixture_or_product_identity_changed')
    captured,close = PRIOR['closed_capture'](root,summary)
    frames,paths = frame_roster(root,summary['construct_frames'],summary['historical_frames'])
    stock = root/'mcp_io/MCP_IO.jsonl'
    worker_calls = [j for line in stock.read_bytes().splitlines() if (j:=json.loads(line))['method']=='tools/call']
    metrics = []
    semantics,captures = [],[]
    previous_image = None
    for i,(row,worker) in enumerate(zip(summary['requests'],worker_calls,strict=True),1):
        request,rpc,body,images,wire = verify_wire(root,row,worker)
        error = rpc['result']['isError']
        stage_file = root/'product_full'/f'call_{i:03d}'/'SERVICE_RESULT.json'
        stages = clocks(row['stages'])
        capture = root/f'CAPTURE_{i:02d}.json'
        if capture.is_file():
            captures.append(pin(capture)['sha256'])
        independent = None
        if not error:
            producer = read(stage_file)
            require(producer['stages']==row['stages'] and producer['work']==row['work']
                    and producer['work']['raster_attempts']==row['raster_attempts']==worker['raster_actual'],
                    'actual_generation_or_raster_accounting_changed')
            independent = verify_region(producer,body,images,root,fixture)
            if independent:
                if previous_image is not None:
                    require(independent==previous_image,'hot_read_did_not_return_own_current_identical_frame')
                previous_image = independent
            if not images:
                require('source_region_rectangle_selection' not in stages and row['raster_attempts']==0,
                        'noimage_measurement_unexpectedly_entered_raster_path')
            sem = (request,body,producer)
        else:
            require(not images and row['raster_attempts']==worker['raster_actual']==0,
                    'rejected_call_constructed_image')
            require(control and isinstance(body,dict)
                    and body['error']=='source_region_ref_capture_generation_changed',
                    'wrong_stale_generation_diagnosis')
            sem = (request,body)
        cli = None if error else CLI(rpc,require_all=True)
        observed = {'wire':wire,'wire_ns':row['wire']['elapsed_ns'],'raster_attempts':row['raster_attempts'],
                    'text_bytes':row['text_bytes'],'PNG_bytes':row['PNG_bytes'],'is_error':error,
                    'result_cache_hit':row['result_cache_hit'],'stages_ns':stages,'image':independent,'CLI':cli,
                    'worker_request_to_reply_ns':worker['request_to_reply_ns'],'producer':pin(stage_file) if stage_file.is_file() else None}
        if not error:
            service = producer['stages']['service_total']
            require(worker['request_received_ns']<=service['started_ns']<=service['closed_ns']<=worker['reply_completed_ns'],
                    'product_elapsed_not_in_worker_wire_window')
            observed['worker_service_end_to_flush_ns'] = worker['reply_completed_ns']-service['closed_ns']
        metrics.append(observed)
        semantics.append(normal(sem,paths,binding['source_sha256']))
    if control:
        state = [call['capture_state'] for call in captured['calls']]
        require(len(state)==3 and state[1]==state[2]
                and state[1]['revision']==state[0]['revision']+1
                and all(state[0][key]==state[1][key] for key in ('instance_id','epoch'))
                and not frames and [row['is_error'] for row in metrics]==[False,True,False]
                and not metrics[0]['is_error'] and not metrics[-1]['is_error']
                and all(row['raster_attempts']==0 for row in metrics),
                'cool_noimage_stale_and_recovery_sequence_changed')
    else:
        cold,warm = metrics[:2]
        expected = 2 if fixture=='rectangle' else 1
        require(cold['raster_attempts']==len(frames)==expected and not cold['result_cache_hit']
                and warm['raster_attempts']==0 and warm['result_cache_hit']
                and not any(item['is_error'] for item in metrics) and cold['image']==warm['image'],
                'cold_construction_or_same_capture_hot_hit_changed')
    return {'label':root.name,'fixture':fixture,'control':control,'product':product,
            'capture_exact_SHA256':captures, 'actual_capture_deltas':captured['calls'],
            'measurements':metrics,'frames':frames,'clock_whole_ns':summary['whole_window_ns'],
            'peak_memory':summary['memory'],'held_EOF':pin(summary['held_close']['path']),
            'same_result':semantics}


def paired(a,b):
    require(a['capture_exact_SHA256']==b['capture_exact_SHA256'] and a['same_result']==b['same_result'],
            'public_or_producer_binding_changed/'+a['label']+'/'+b['label'])
    require([{k:f[k]['sha256'] for k in ('png','arrays')} for f in a['frames']]==
            [{k:f[k]['sha256'] for k in ('png','arrays')} for f in b['frames']],
            'frame_file_sha_differs_in_pair')
    result = {'slots':[a['label'],b['label']],'actual_fields_and_content_equal':True}
    if not a['control']:
        aa,bb=(v['measurements'][0]['stages_ns'] for v in (a,b))
        result.update(rectangle_phase_reduction=1-bb['source_region_rectangle_selection']/aa['source_region_rectangle_selection'],
                      cold_service_reduction=1-bb['service_total']/aa['service_total'],
                      cold_rpc_reduction=1-b['measurements'][0]['wire_ns']/a['measurements'][0]['wire_ns'],
                      complete_MCP_reduction=1-b['clock_whole_ns']/a['clock_whole_ns'])
    return result


def score(root):
    freeze = H['verified_freeze']()
    seq = root/'FORMAL_SEQUENCE.jsonl'
    logs = [json.loads(line) for line in seq.read_bytes().splitlines()]
    schedule = freeze['schedule']
    require(logs[0]['schedule']==schedule and logs[0]['freeze_sha256']==pin(NS/'FROZEN.json')['sha256']
            and [row['event'] for row in logs]==['frozen']+['start','exit']*len(schedule)+['complete'],
            'official_frozen_replay_sequence_unfinished')
    exact = read(PRIOR['check_pin'](logs[0]['exact_receipt'],root))
    require(exact['passed'] is True and exact['binding_git']==freeze['candidate_git'],'scored_wrong_exact_candidate')
    arms = {}
    last = 0
    for (label,fixture,control),begin,done in zip(schedule,logs[1:-1:2],logs[2:-1:2],strict=True):
        binding_path = NS/'install/PRODUCT_RUN_BINDING.json' if label.startswith('P') or label.endswith('P') else H['BASE_BINDING']
        folder = root/('controls' if control else 'arms')/label
        require(begin['label']==done['label']==label and begin['fixture']==fixture and begin['control']==control
                and begin['binding']==pin(binding_path) and done['summary']==pin(folder/'SUMMARY.json')
                and done['exit_code']==0 and last<=begin['started_ns']<done['finished_ns']
                and done['wall_ns']==done['finished_ns']-begin['started_ns'],
                'formal_clock_or_bound_receipt_changed/'+label)
        last=done['finished_ns']
        arm = inspect_arm(folder,fixture,control,read(binding_path))
        arm['controller_ns'] = done['wall_ns']
        require(arm['clock_whole_ns']<arm['controller_ns'],'MCP_clock_is_not_inside_actual_replay_window')
        arms[label]=arm
    comparisons = [paired(arms[a],arms[b]) for a,b in PAIRS]
    reductions = {key:median(item[key] for item in comparisons[:3])
                  for key in ('rectangle_phase_reduction','cold_service_reduction','cold_rpc_reduction','complete_MCP_reduction')}
    quality = all(v['actual_fields_and_content_equal'] for v in comparisons)
    passed = quality and reductions['rectangle_phase_reduction']>=freeze['gate']['rectangle_phase_paired_median_reduction'] and (
        reductions['cold_service_reduction']>=freeze['gate']['cold_service_paired_median_reduction'])
    for arm in arms.values():
        arm.pop('same_result')
    rows = [r for arm in arms.values() for r in arm['measurements']]
    return {'passed':passed,'quality_passed':quality,'pairs':comparisons,'paired_median':reductions,
            'arms':arms,'sequence':pin(seq),'denominators':{'slots':len(arms),'calls':len(rows),'rasters':sum(r['raster_attempts'] for r in rows),
                                                         'rejections':sum(r['is_error'] for r in rows),'Blender':0,'models':0,'replacements':0}}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        result=score(args.runtime.resolve(strict=True))
    except (OSError,ValueError,KeyError,TypeError,IndexError) as exc:
        result={'passed':False,'quality_passed':False,'error':str(exc),'error_type':type(exc).__name__}
    H['write'](args.output,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('arms','pairs')},ensure_ascii=False),flush=True)
    raise SystemExit(0 if result['passed'] else 1)

"""Score the fixed held-stdio replay pairs and bind published evidence to original bytes."""

import argparse
import base64
import json
from pathlib import Path
from runpy import run_path
from statistics import median
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from fixture import CASES, NS, digest, pin, read, require, source


PLAN_ORDER = ('N1','P1','P2','N2','N3','P3','HN','HP')
PAIRS = (('N1','P1'),('N2','P2'),('N3','P3'),('HN','HP'))
M1 = NS.parent/'m1_region_task_witness_image_path_001/checks'
VERIFY = run_path(str(M1/'evidence.py'))
MUTATE = run_path(str(M1/'controls.py'))['mutate_frame_index']
ORIGINAL = NS.parent/'m1_region_task_first_packet_consumption_holdout_001'
MEASURE = run_path(str(ORIGINAL/'checks/evidence.py'))['verify_measurement']
VIEWS = ('SCENE','TOP','LEFT','RIGHT','FRONT','BACK')


def check_pin(evidence, root=None):
    path = Path(evidence['path']).resolve(strict=True)
    require(root is None or path.is_relative_to(root),'evidence_path_outside_arm/'+str(path))
    actual = pin(path)
    require(all(actual[k]==v for k,v in evidence.items()),'evidence_bytes_changed/'+str(path))
    return path


def normalized(value, files, source_sha):
    if isinstance(value,list):
        return [normalized(v,files,source_sha) for v in value]
    if isinstance(value,dict):
        clean = {}
        for key,val in value.items():
            if key in ('session_id','stages','feedback_stages','generation_stages','request_trace',
                       'frustum_proof_ns','local_coverage_projection'):
                continue
            if key=='runtime_source_sha256':
                require(val==source_sha,'wrong_runtime_source_in_published_result')
                clean[key] = 'verified installed source'
            else:
                clean[key] = normalized(val,files,source_sha)
        return clean
    if isinstance(value,str) and value in files:
        return files[value]
    return value


def num_stage(stages,name):
    if name not in stages:
        return 0
    row = stages[name]
    require(row['elapsed_ns']==row['closed_ns']-row['started_ns']>0,'invalid_stage_interval/'+name)
    return row['elapsed_ns']


def closed_capture(root, summary):
    path = check_pin(summary['held_close'],root)
    done = read(path)
    require(done['confirmed'] and done['exit_code']==0 and done['production_eof_and_exit_verified']
            and done['process_handle_closed'] and done['stdout_eof_seen']
            and not done['forced_kill'] and not done['unconsumed_response_lines'],
            'product_EOF_or_actual_held_exit_failed/'+root.name)
    check_pin(done['worker_eof'],root)
    exit_row = read(check_pin(done['worker_exit'],root))
    require(exit_row['pid']==done['pid'] and exit_row['source_sha256']==summary['product']['source_sha256']
            and exit_row['input_eof_observed'] and exit_row['installed_source_verified']
            and exit_row['production_returned'] and exit_row['production_return_code']==0,
            'actual_product_runtime_close_identity_failed/'+root.name)
    recorded = read(root/'REPLAY_CLOSE.json')
    require(recorded['old_sources_unchanged'] and recorded['memory']==summary['memory']
            and recorded['actual_models']==recorded['actual_Blender_starts']==0
            and recorded['worker_closed_ns']-recorded['worker_started_ns']==summary['worker_window_ns'],
            'capture_provider_close_or_memory_binding_changed/'+root.name)
    return recorded,done


def frames_and_files(root, summary, historical):
    records = summary['construct_frames']
    require(len(records)==len(historical),'constructed_frame_roster_changed/'+root.name)
    files, arrays, metadata = {},{},[]
    for record,previous in zip(records,historical,strict=True):
        coords = ('scope_id','view_name')
        require(all(record[k]==previous[k] for k in coords),'constructed_frame_scope_or_order_changed/'+root.name)
        entry = {k:record[k] for k in coords}
        for key,old in (('arrays','arrays'),('png','png')):
            receipt, expected = record[key],previous[old]
            here = check_pin(receipt,root)
            require(digest(here.read_bytes())==expected,'original_artifact_bytes_changed/'+str(here))
            for spelling in (str(here),here.as_posix()):
                files[spelling] = expected['sha256']
            arrays[key] = arrays.get(key,0)+expected['bytes']
            entry[key] = receipt
        metadata.append(entry)
    return files,arrays,metadata


def wire(root, request):
    row = request['wire']
    base = root/'mcp'/f"rpc_{row['index']:02d}"
    tx,rx = (base/filename for filename in ('TX.bin','RX.bin'))
    raw = rx.read_bytes()
    require(read(base/'RECEIPT.json')==row and digest(raw)=={'bytes':row['RX_bytes'],'sha256':row['RX_sha256']}
            and tx.stat().st_size==row['TX_bytes'] and not row['error']
            and row['closed_ns']-row['started_ns']==row['elapsed_ns']>0,
            'held_wire_receipt_changed/'+str(base))
    response,call = json.loads(raw),read(tx)
    require(call['id']==response['id']==row['id'] and call['method']=='tools/call'
            and not response['result']['isError'],'wire_request_response_identity_changed/'+str(base))
    content = response['result']['content']
    has_png = [base64.b64decode(item['data'],validate=True) for item in content if item['type']=='image']
    body_bytes = content[0]['text'].encode()
    require(content[0]['type']=='text' and len(body_bytes)==request['text_bytes']
            and sum(map(len,has_png))==request['PNG_bytes'],'published_content_byte_counts_changed/'+str(base))
    return call, response, json.loads(body_bytes), has_png, raw, {'TX':pin(tx),'RX':pin(rx)}


def cli_proof(row, body_bytes, require_all):
    phases = {(h,p) for h in (33,34,35) for p in ('MCP','history')}
    require(row['passed'] and row['original_text_bytes']==body_bytes and len(row['stages'])==6
            and {(p['head_bytes'],p['phase']) for p in row['stages']}==phases
            and all(p['original_images_exact'] and (not require_all or p['exact']) for p in row['stages']),
            'fixed_CLI_content_or_image_qualification_failed')


def check_main_proofs(reply, producer, arm, frames, wire_bytes, output=None):
    known = {f['image_ref']:pin(f['image_path']) for f in producer['frames']}
    require(len(known)==len(frames)==3,'main_actual_constructed_and_delivered_frames_changed')
    for frame in producer['frames']:
        need, = [r['png'] for r in frames if (r['scope_id'],r['view_name'])==(frame['scope_id'],frame['view_name'])]
        require(known[frame['image_ref']]==need,'main_producer_path_is_not_current_scoped_PNG')
    verify = VERIFY['verify_public_witnesses']
    props = {'slot':arm,'authoritative_paths':known,'require_paths':True}
    proof = verify(reply,producer,**props)
    require({r['object_name'] for r in proof['public_witnesses']}=={'Component_582','Component_736'}
            and len(proof['paths'])==2,'main_two_current_local_witnesses_changed')
    body = json.loads(reply['result']['content'][0]['text'])
    blockers = VERIFY['records'](body['blocker_evidence'])
    require([row['view_name'] for row in blockers]==list(VIEWS),'main_original_six_direction_blockers_changed')
    mutant,offset = MUTATE(wire_bytes,proof)
    try:
        verify(json.loads(mutant),producer,**props)
    except ValueError as error:
        require(str(error)==VERIFY['WITNESS_BINDING_ERROR'],'same_name_wrong_scope_refused_for_wrong_reason')
    else:
        raise ValueError('same_name_wrong_scope_was_accepted')
    if output is not None:
        with output.open('xb') as stream:
            stream.write(mutant)
    return {'witnesses':proof,'blockers':blockers,'single_byte_negative':{
            **digest(mutant),'offset':offset,'rejected_for':VERIFY['WITNESS_BINDING_ERROR']}}


def read_arm(root, fixture, binding, historical, output, controls=False):
    summary = read(root/'SUMMARY.json')
    sha = binding['source_sha256']
    require(summary['passed'] and summary['controls']==controls and summary['fixture']==fixture
            and summary['arm']==root.name and tuple(summary['source_dimensions'])==CASES[fixture][3]
            and summary['actual_Blender_starts']==summary['actual_models']==0
            and all(summary['product'][k]==binding[k] for k in ('preparation_git','source_sha256','wheel_sha256')),
            'replay_arm_identity_or_result_changed/'+root.name)
    original = {row['sha256'] for row in summary['source_pins']}
    require(CASES[fixture][2] in original,'historical_terminal_capture_pin_missing/'+root.name)
    close,closed = closed_capture(root,summary)
    requests,results,proofs,captures = [],[],{},[]
    files,arrays,frames = frames_and_files(root,summary,historical)
    count = 4 if controls else 3
    require(len(summary['requests'])==len(close['calls'])==count,'actual_call_count_changed/'+root.name)
    require([c['resource_count'] for c in close['calls']]==(
            [CASES[fixture][3][0],0,CASES[fixture][3][0],0] if controls else [CASES[fixture][3][0],0,0]),
            'original_capture_resource_count_changed/'+root.name)
    for index,(call,details) in enumerate(zip(close['calls'],summary['requests'],strict=True),1):
        capture_path = root/f'CAPTURE_{index:02d}.json'
        capture = read(capture_path)
        require(capture['capture_state']==call['capture_state'],'capture_not_its_own_current_revision/'+root.name)
        captures.append(pin(capture_path))
        producer_path = root/'product_full'/f'call_{index:03d}'/'SERVICE_RESULT.json'
        producer = read(producer_path)
        require(producer['stages']==details['stages'] and producer['work']==details['work']
                and producer['work']['raster_attempts']==details['raster_attempts']==(3 if index==1 and not controls else 0),
                'independent_stage_raster_or_work_mismatch/'+root.name)
        request,reply,body,pngs,raw,wire_pins = wire(root,details)
        cli_proof(details['CLI'],details['text_bytes'],not controls and (fixture=='main' or index<3))
        if not controls and index<3:
            known = [Path(row['png']['path']).read_bytes() for row in frames]
            require(pngs==(known if fixture=='main' else known[:1]),'publish_original_PNG_order_changed/'+root.name)
            if fixture=='main':
                proof = check_main_proofs(reply,producer,root,frames,raw,
                                          output/f'{root.name}_{index:02d}_WRONG_SCOPE_RX.bin' if output else None)
                proofs['cold' if index==1 else 'warm'] = proof
                if index==1:
                    parent_binding = producer['binding']
            else:
                constructed = producer['constructed_frames']
                public_frames = VERIFY['records'](body['frames'])
                require([raw for public,raw in zip(public_frames,constructed,strict=True)
                         if public['native_content_block_index'] is not None]==producer['frames'],
                        'holdout_delivered_frame_is_not_current_constructed_frame')
                proof = VERIFY['verify_public_witnesses'](reply,{**producer,'frames':constructed})
                require([w['object_name'] for w in proof['public_witnesses']]==['N22']
                        and proof['original_native_PNG_blocks']==1,
                        'holdout_N22_original_complete_witness_changed')
                row, = VERIFY['records'](body['pixel_shortfalls'])
                require(row['visible_surface_pixels']==8835 and row['contrasting_boundary_pixels']==0,
                        'holdout_N10_original_pixel_shortfall_changed')
                proofs['cold' if index==1 else 'warm'] = proof
        else:
            require(not pngs,'no_image_delivered_image/'+root.name)
            if not controls and fixture=='main':
                terminal = Path('D:/he_'+CASES[fixture][1])/'slots/P1/TERMINAL_SOURCE.json'
                proofs['noimage_measurement'] = MEASURE(reply,producer,parent_binding,read(terminal),
                                                       read(ORIGINAL/'fixture/TRUTH.json'))
        results.append((normalized(body,files,sha),normalized(producer,files,sha)))
        requests.append({**details,'request':request,'pins':{**wire_pins,'producer':pin(producer_path)}})
    revisions = [c['capture_state']['revision'] for c in close['calls']]
    if controls:
        require(revisions==[revisions[0],revisions[0],revisions[0]+1,revisions[0]+1]
                and all(not row['work'].get('local_coverage_projection') for row in requests)
                and all('local_object_bounds' not in row['stages'] for row in requests),
                'ordinary_noimage_or_generation_control_ran_local_candidate/'+root.name)
    else:
        require(len(set(revisions))==1,'same_capture_generation_drift/'+root.name)
        cold,warm = (dict(results[i][0]) for i in range(2))
        first,second = (b.pop('image_delivery') for b in (cold,warm))
        require([first.pop(k) for k in ('new_raster_attempts','frame_reuses')]==[3,0]
                and [second.pop(k) for k in ('new_raster_attempts','frame_reuses')]==[0,3 if fixture=='main' else 1]
                and first==second and cold==warm,'warm_text_or_evidence_changed/'+root.name)
    require([q['result_cache_hit'] for q in requests]==([False,True,False,False] if controls else [False,True,False])
            and all(not q['work'].get('local_coverage_projection') for q in requests[1:]),
            'warm_result_reuse_or_noimage_behavior_changed/'+root.name)
    first = requests[0]
    stages = first['stages']
    local = sum(num_stage(stages,name) for name in stages if name.startswith('index_local_'))
    points = first['work'].get('local_coverage_projection',{})
    for name in points:
        require(tuple(points[name])==tuple(sorted(VIEWS)) or set(points[name])==set(VIEWS),
                'local_projection_diagnostics_missing_view/'+root.name)
    measures = {'whole_MCP_window_ns':summary['whole_window_ns'],'worker_window_ns':summary['worker_window_ns'],
                'cold_RPC_ns':first['wire']['elapsed_ns'],'cold_service_ns':num_stage(stages,'service_total'),
                'local_index_ns':local,'shared_object_bounds_ns':num_stage(stages,'local_object_bounds'),
                'local_index_and_shared_boxes_ns':local+num_stage(stages,'local_object_bounds'),
                'object_bounds_filter_ns':sum(p['object_bounds_filter_ns'] for views in points.values() for p in views.values()),
                'projection_prepare_ns':sum(p['projection_prepare_ns'] for views in points.values() for p in views.values()),
                'cold_raster_publish_ns':sum(num_stage(stages,name) for name in stages if name.startswith('render_and_publish_')),
                'memory':summary['memory'],'constructed_disk_bytes':arrays,'closed_ns':closed['elapsed_ns']}
    return {'results':results,'requests':requests,'frames':frames,'captures':captures,'measures':measures,
            'formal_summary':pin(root/'SUMMARY.json'),'evidence_proofs':proofs,'product':summary['product'],
            'resource_count_by_call':[row['resource_count'] for row in close['calls']]}


def historical_frames(fixture):
    _,producer,source_pins = source(fixture)
    frames = [{'scope_id':frame['scope_id'],'view_name':frame['view_name'],
               'png':{'sha256':frame['image_sha256'],'bytes':frame['PNG_bytes']},
               'arrays':{'sha256':frame['arrays_sha256'],'bytes':frame['compressed_array_file_bytes']}}
              for frame in producer['constructed_frames']]
    return frames, source_pins


def paired(arms, labels):
    old,new = (arms[label] for label in labels)
    for index,(a,b) in enumerate(zip(old['results'],new['results'],strict=True),1):
        for where,av,bv in zip(('public','producer'),a,b,strict=True):
            require(av==bv,f'normalized_{where}_changed/{labels}/{index}')
    require([p['sha256'] for p in old['captures']]==[p['sha256'] for p in new['captures']],
            f'captured_world_or_display_changed/{labels}')
    require([r['request'] for r in old['requests']]==[r['request'] for r in new['requests']]
            and [r['CLI'] for r in old['requests']]==[r['CLI'] for r in new['requests']],
            f'request_or_fixed_CLI_delivery_changed/{labels}')
    report = {'labels':labels,'semantic_equal':True,'capture_and_request_equal':True,'CLI_equal':True}
    if new['frames']:
        for label,v in zip(labels,(old,new),strict=True):
            report[label] = v['measures']
        for key in ('local_index_ns','local_index_and_shared_boxes_ns','whole_MCP_window_ns','outer_wall_ns'):
            old_ns,new_ns = (v['measures'][key] for v in (old,new))
            report[key+'_relative_reduction'] = 1-new_ns/old_ns
    return report


def journal(root, baseline_path, candidate_path, exact_path, frozen_path):
    log = root/'FORMAL_SEQUENCE.jsonl'
    rows = [json.loads(line) for line in log.read_bytes().splitlines()]
    require(len(rows)==18 and [r['event'] for r in rows]==['frozen']+['start','exit']*8+['complete']
            and rows[0]['freeze_sha256']==pin(frozen_path)['sha256'] and rows[0]['exact_receipt']==pin(exact_path)
            and rows[-1]['new_Blender']==rows[-1]['new_models']==0,'formal_journal_incomplete_or_not_its_freeze')
    schedule = [(name,'holdout' if name.startswith('H') else 'main') for name in PLAN_ORDER]
    require(rows[0]['schedule']==[list(x) for x in schedule],'formal_replay_fixed_order_changed')
    result, previous = {},0
    for index,(label,fixture) in enumerate(schedule):
        started,finished = rows[2*index+1:2*index+3]
        binding = candidate_path if label.startswith('P') or label=='HP' else baseline_path
        require(started['label']==finished['label']==label and started['fixture']==fixture
                and started['binding']==pin(binding) and finished['summary']==pin(root/'arms'/label/'SUMMARY.json')
                and finished['wall_ns']==finished['finished_ns']-started['started_ns']>0
                and started['started_ns']>=previous and finished['exit_code']==0,
                'formal_held_launch_or_exit_order_changed/'+label)
        previous = finished['finished_ns']
        result[label] = {'start':started,'exit':finished}
    require(rows[-1]['finished_ns']>=previous,'formal_close_time_precedes_last_slot')
    return result,pin(log)


def preflight(root, baseline):
    reports = {}
    for fixture,label in (('main','main_02'),('holdout','holdout'),('main','controls')):
        frames,_ = historical_frames(fixture)
        result = read_arm(root/'preflight'/label,fixture,baseline,[] if label=='controls' else frames,None,label=='controls')
        result.pop('results')
        reports[label] = result
    return {'passed':True,'preflight':True,'arms':reports,'source_pins':[
            pin(path) for path in (M1/'evidence.py',M1/'controls.py',ORIGINAL/'checks/evidence.py',
             ORIGINAL/'fixture/TRUTH.json',NS.parent/'m4_dense_region_brief_001/checks/brief_schema.py',
             NS.parent/'m5_observe_measure_001/oracle.py')]}


def main(root, baseline_path, candidate_path, exact_path, frozen_path, output):
    base,candidate,exact,frozen = map(read,(baseline_path,candidate_path,exact_path,frozen_path))
    require(exact['passed'] and exact['candidate_checked'] and exact['installed_coverage_equal']
            and base['preparation_git']==frozen['baseline_git']==exact['baseline_git']
            and candidate['preparation_git']==frozen['candidate_git']==exact['candidate_git'],
            'correctness_receipt_not_same_frozen_candidate')
    launch,sequence = journal(root,baseline_path,candidate_path,exact_path,frozen_path)
    sources = {fixture:historical_frames(fixture) for fixture in CASES}
    arms = {}
    output.mkdir(exist_ok=False)
    for label in PLAN_ORDER:
        fixture = launch[label]['start']['fixture']
        binding = candidate if label.startswith('P') or label=='HP' else base
        armed = read_arm(root/'arms'/label,fixture,binding,sources[fixture][0],output)
        require(armed['measures']['whole_MCP_window_ns']<launch[label]['exit']['wall_ns'],
                'held_stdio_clock_not_inside_formal_process_clock/'+label)
        armed['measures']['outer_wall_ns'] = launch[label]['exit']['wall_ns']
        work = armed['requests'][0]['work'].get('local_coverage_projection',{})
        if binding is candidate:
            counts = [p for views in work.values() for p in views.values()]
            require(len(counts)==(12 if fixture=='main' else 6)
                    and all(row['input_triangles']==CASES[fixture][3][2] for row in counts)
                    and (fixture!='main' or sum(row['projected_triangles'] for row in counts)==1058),
                    'formal_projected_triangle_work_changed/'+label)
        else:
            require(not work and not armed['measures']['shared_object_bounds_ns'],
                    'baseline_unexpectedly_used_candidate_projection/'+label)
        arms[label] = armed
    comparisons = [paired(arms,labels) for labels in PAIRS]
    controls = {label:read_arm(path,'main',binding,[],None,True) for label,path,binding in
                (('baseline',root/'preflight/controls',base),('candidate',root/'controls/P',candidate))}
    comparison_control = paired(controls,('baseline','candidate'))
    measured = comparisons[:3]
    local = [r['local_index_and_shared_boxes_ns_relative_reduction'] for r in measured]
    windows = [r['whole_MCP_window_ns_relative_reduction'] for r in measured]
    outer = [r['outer_wall_ns_relative_reduction'] for r in measured]
    accepted = median(local)>=frozen['min_paired_median_local_improvement'] and median(windows)>0
    for report in (*arms.values(),*controls.values()):
        report.pop('results')
    return {'passed':accepted,'quality_passed':True,'candidacy_only':True,'formal_journal':sequence,
            'exact_receipt':pin(exact_path),'measure':{
                'local_index_plus_one_shared_box_build_paired_median_reduction':median(local),
                'held_MCP_window_paired_median_reduction':median(windows),
                'outer_slot_paired_median_reduction':median(outer),
                'local_reduction_target':frozen['min_paired_median_local_improvement'],
            },'comparisons':comparisons,'controls':comparison_control,'control_arms':controls,'arms':arms,
            'original_sources':{k:v[1] for k,v in sources.items()},
            'denominators':{'main_pairs':3,'holdout_pairs':1,'completed_replays':8,
                            'new_Blender':0,'new_models':0,'formal_calls':24,'formal_raster_attempts':24}}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',required=True,type=Path)
    parser.add_argument('--baseline',required=True,type=Path)
    parser.add_argument('--candidate',type=Path)
    parser.add_argument('--exact',type=Path)
    parser.add_argument('--frozen',type=Path,default=NS/'FROZEN.json')
    parser.add_argument('--output',required=True,type=Path)
    args = parser.parse_args()
    require(not args.output.exists(),'output_already_exists')
    try:
        if args.candidate:
            report = main(args.runtime.resolve(strict=True),args.baseline,args.candidate,args.exact,args.frozen,
                          args.output.with_suffix(''))
        else:
            report = preflight(args.runtime.resolve(strict=True),read(args.baseline))
    except (ValueError,KeyError,IndexError,OSError) as err:
        report = {'passed':False,'failure_type':type(err).__name__,'failure':str(err)}
    with args.output.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(report,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
        stream.write('\n')
    print(json.dumps({k:report[k] for k in ('passed','failure','measure') if k in report}),flush=True)
    raise SystemExit(0 if report['passed'] else 1)

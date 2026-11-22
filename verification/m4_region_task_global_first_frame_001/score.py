"""Check the actual isolated wire, frame binding and crossed cold RPC budget."""

import argparse
import base64
from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path
from statistics import median
from zipfile import ZipFile


NS = Path(__file__).resolve().parent
V = NS.parent
OLD_PATH = V/'m4_local_coverage_object_bounds_001/checks/replay.py'
OLD = run_path(str(OLD_PATH))
VERIFY = OLD['VERIFY']
read, pin, require = (OLD[name] for name in ('read', 'pin', 'require'))
VIEWS = OLD['VIEWS']
PAIRS = (('N1','P1'), ('N2','P2'), ('N3','P3'), ('HN','HP'), ('TN','TP'), ('FN','FP'), ('ON','OP'))
BASE = V/'m4_local_coverage_object_bounds_001/install/PRODUCT_RUN_BINDING.json'
CANDIDATE = NS/'install/PRODUCT_RUN_BINDING.json'


def normalize(value, paths, source_sha):
    if isinstance(value, (list, tuple)):
        return [normalize(item, paths, source_sha) for item in value]
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if key in ('session_id','work','generation_work','stages','generation_stages','feedback_stages','request_trace'):
                continue
            if key == 'runtime_source_sha256':
                require(item == source_sha, 'public_identity_changed')
                cleaned[key] = 'verified_runtime'
            else:
                cleaned[key] = normalize(item, paths, source_sha)
        return cleaned
    return paths.get(value, value) if isinstance(value, str) else value


def full_proof(body, content, producer, root):
    require(body['facts'] == producer['facts'] and body['scopes'] == producer['scopes']
            and body['frames'] == producer['frames'] and body['constructed_frames'] == producer['constructed_frames'],
            'public_full_not_its_validated_producer')
    by_id = {frame['frame_identity']: frame for frame in producer['constructed_frames']}
    require(len(by_id) == len(producer['constructed_frames']), 'duplicate_full_frames')
    pngs = [base64.b64decode(item['data'], validate=True) for item in content if item['type'] == 'image']
    delivered = {}
    for frame, data in zip(producer['frames'], pngs, strict=True):
        require(by_id[frame['frame_identity']] == frame, 'full_selected_not_current_constructed')
        path = Path(frame['image_path']).resolve(strict=True)
        require(path.is_relative_to(root) and path.read_bytes() == data, 'full_selected_original_unreadable')
        delivered[frame['frame_identity']] = pin(path)
    return delivered


def brief_proof(reply, body, producer, root, main, raw, negative_path):
    constructed, selected = producer['constructed_frames'], producer['frames']
    public = VERIFY['records'](body['frames'])
    require(len(public) == len(constructed), 'frame_table_constructed_roster')
    for row, original in zip(public, constructed, strict=True):
        idx = row['native_content_block_index']
        if idx is not None:
            require(type(idx) is int and 1 <= idx <= len(selected) and selected[idx-1] == original,
                    'public_frame_block_not_its_own_selected_original')
    known = {frame['image_ref']: pin(frame['image_path']) for frame in selected}
    wrapped = {**producer,'frames':constructed}
    props = {'slot':root,'authoritative_paths':known,'require_paths':main}
    proof = VERIFY['verify_public_witnesses'](reply, wrapped, **props)
    if main:
        require({row['object_name'] for row in proof['public_witnesses']} == {'Component_582','Component_736'}
                and len(proof['paths']) == 2 and
                [row['view_name'] for row in VERIFY['records'](body['blocker_evidence'])] == list(VIEWS),
                'main_lost_local_witness_or_six_direction_blockers')
        if negative_path is not None:
            if len(constructed) == 3:
                # Historical same-named local SCENE/global SCENE confusion.
                changed, index = OLD['MUTATE'](raw, proof)
            else:
                # After reindex, the former local SCENE index now names the LEFT frame.
                mutated = deepcopy(reply)
                value = json.loads(mutated['result']['content'][0]['text'])
                names = value['witnesses']['columns']
                rows = value['witnesses']['rows']
                fidx = names.index('frame_index')
                selected_witness, = [row for row in proof['public_witnesses'] if row['object_name'] == 'Component_582']
                rows[[row['region_index'] for row in VERIFY['records'](value['witnesses'])].index(
                    selected_witness['region_index'])][fidx] = 1
                mutated['result']['content'][0]['text'] = json.dumps(value, ensure_ascii=False, separators=(',',':'))
                changed, index = json.dumps(mutated, ensure_ascii=False, separators=(',',':')).encode(), None
            try:
                VERIFY['verify_public_witnesses'](json.loads(changed), wrapped, **props)
            except ValueError as exc:
                require(str(exc) == VERIFY['WITNESS_BINDING_ERROR'], 'frame_mutation_not_rejected_for_binding')
                negative_path.write_bytes(changed)
                proof['reindex_negative'] = {**pin(negative_path),'byte_offset':index,'reason':str(exc)}
            else:
                raise ValueError('stale_frame_index_accepted')
    return proof


def verify_capture_source(fixture):
    if fixture == 'main':
        case = OLD['CASES']['main']
        return Path('D:/he_'+case[1])/'slots/P1/TERMINAL_SOURCE.json'
    return None


def frame_roster(root, summary):
    paths, frames, byte_counts = {}, [], {'png':0,'arrays':0}
    for record in summary['construct_frames'] + summary['ordinary_constructed_frames']:
        if not summary['controls']:
            frames.append(record)
        for name in byte_counts:
            path = OLD['check_pin'](record[name],root)
            paths[str(path)] = paths[path.as_posix()] = record[name]['sha256']
            byte_counts[name] += record[name]['bytes']
    history = summary['historical_frames']
    fact = lambda row: (row['scope_id'], row['view_name'],
                       tuple((row[k]['sha256'],row[k]['bytes']) for k in ('png','arrays')))
    if len(frames) == len(history)-1:
        require(bool(history) and (history[0]['scope_id'],history[0]['view_name']) == ('global','SCENE'),
                'omitted_historical_frame_is_not_global_scene')
        history = history[1:]
    require(list(map(fact, frames)) == list(map(fact, history)),'constructed_PNG_NPZ_or_source_order_changed')
    return paths, frames, byte_counts


def score_arm(root, row, binding, negatives):
    summary = read(root/'SUMMARY.json')
    label, fixture, role = (row[key] for key in ('label','fixture','role'))
    ordinary = role == 'ordinary'
    full = role == 'main_full'
    require(summary['passed'] and (summary['arm'],summary['fixture']) == (label,fixture)
            and summary['controls'] == ordinary and summary['full_control'] == full
            and summary['actual_Blender_starts'] == summary['actual_models'] == 0
            and all(binding[k] == v for k,v in summary['product'].items()), 'unexpected_actual_arm_identity/'+label)
    closed, release = OLD['closed_capture'](root,summary)
    paths, frames, disk_bytes = frame_roster(root, summary)
    rows, proofs, captures, semantic = [], {}, [], []
    reqs = summary['requests']
    require(len(reqs) == len(closed['calls']) == (5 if ordinary else 3), 'wrong_actual_tool_count/'+label)
    source_count = summary['source_dimensions'][0]
    require([c['resource_count'] for c in closed['calls']] ==
            ([source_count,0,source_count,0,0] if ordinary else [source_count,0,0]),
            'wrong_capture_delta_or_old_source/'+label)
    require([bool(r['result_cache_hit']) for r in reqs] ==
            ([False,True,False,False,False] if ordinary else [False,True,False]), 'unexpected_hot_cache_behavior/'+label)
    audit = root/'mcp_io/MCP_IO.jsonl'
    worker_calls = [row for row in map(json.loads,audit.read_bytes().splitlines()) if row['method'] == 'tools/call']
    for i,(details,call,worker) in enumerate(zip(reqs,closed['calls'],worker_calls,strict=True),1):
        capture = root/f'CAPTURE_{i:02d}.json'
        require(read(capture)['capture_state'] == call['capture_state'],'capture_not_its_own_revision/'+label)
        captures.append(pin(capture))
        path = root/'product_full'/f'call_{i:03d}'/'SERVICE_RESULT.json'
        producer = read(path)
        tx,reply,body,pngs,raw,wires = OLD['wire'](root,details)
        fixed_rx = raw.replace(b'\r\n',b'\n')
        require(worker['id'] == worker['response_id'] == tx['id'] == details['wire']['id']
                and worker['sequence'] == details['wire']['index'] and worker['TX_bytes'] == wires['TX']['bytes']
                and worker['TX_sha256'] == wires['TX']['sha256']
                and OLD['digest'](fixed_rx) == {'bytes':worker['RX_text_UTF8_LF_bytes'],
                                              'sha256':worker['RX_text_UTF8_LF_sha256']}
                and worker['raster_actual'] == details['raster_attempts'],
                'changed_original_tool_request_or_response/'+label)
        raster_count = len(summary['ordinary_constructed_frames']) if ordinary and i == 5 else (len(frames) if i == 1 else 0)
        require(producer['stages'] == details['stages'] and producer['work'] == details['work']
                and producer['work']['raster_attempts'] == details['raster_attempts'] == raster_count,
                'producer_clock_or_raster_ledger_inconsistent/'+label)
        OLD['cli_proof'](details['CLI'],details['text_bytes'],not ordinary and not full and
                         (fixture != 'holdout' or i < 3))
        if i < 3 and not ordinary:
            actual = producer['constructed_frames']
            require(len(actual) == len(frames) and [
                (f['scope_id'],f['view_name'],f['image_sha256'],f['arrays_sha256']) for f in actual] == [
                (f['scope_id'],f['view_name'],f['png']['sha256'],f['arrays']['sha256']) for f in frames],
                'cold_or_warm_current_frame_roster_changed/'+label)
            require(pngs == [Path(frame['image_path']).read_bytes() for frame in producer['frames']],
                    'public_native_PNG_changed/'+label)
            if full:
                proof = full_proof(body,reply['result']['content'],producer,root)
            else:
                proof = brief_proof(reply,body,producer,root,fixture=='main',raw,
                                    negatives/f'{label}_{i:02d}_WRONG_FRAME.json' if fixture=='main' else None)
            proofs[str(i)] = proof
            if i == 1:
                parent = producer['binding']
        elif ordinary and i == 5:
            require(len(pngs) == len(summary['ordinary_constructed_frames']) >= 2
                    and [Path(f['png']['path']).read_bytes() for f in summary['ordinary_constructed_frames']] == pngs
                    and 'region_task' not in producer['facts'] and not producer['work'].get('global_first_frame_skipped'),
                    'ordinary_global_multiview_drift/'+label)
        else:
            require(not pngs,'unexpected_image_in_noimage_request/'+label)
            if not ordinary and fixture == 'main':
                original = OLD['ORIGINAL']
                terminal,truth = read(verify_capture_source(fixture)),read(original/'fixture/TRUTH.json')
                if full:
                    task,ref = body['task_result'],body['region_ref']
                    known, = [obj for obj in parent['objects'] if obj['object_name']=='Component_417']
                    fact = task['facts']['surface_proximity']
                    witness = fact['value']['nearest_witness']
                    require(task==producer['task_result'] and ref==producer['region_ref']==task['region_ref']
                            and ref['source_triangle_indices']==[0,1] and task['reference']['name']=='M4_Far_00'
                            and all(ref['capture_generation'][key]==parent['capture_state'][key]
                                    for key in ('instance_id','epoch','revision')) and not body['frames']
                            and all(ref[key]==known[key] for key in ('host_id','instance_id'))
                            and fact['status']=='measured'
                            and all(task['source_mapping']['nearest_witness'][key]['exact_membership'] is True
                                    for key in ('a','b')), 'standard_noimage_full_source_or_measure_changed')
                    proofs['measure'] = OLD['MEASURE'].__globals__['measured']({
                        'object_name':'Component_417','reference':'M4_Far_00','distance_m':fact['value']['distance_m'],
                        'a':witness['a'],'b':witness['b'],'direction_world':witness['direction_a_to_b'],
                    },terminal,OLD['MEASURE'].__globals__['normalize_truth'](truth))
                else:
                    proofs['measure'] = OLD['MEASURE'](reply,producer,parent,terminal,truth)
            elif not ordinary and fixture == 'transfer':
                task = body['task_result']
                fact = task['facts']['surface_proximity']
                point = fact['value']['nearest_witness']
                require(body['region_ref'] == producer['region_ref'] and body['region']['object_name']=='S034'
                        and body['region_ref']['source_triangle_indices']==[0,1] and task['reference']['name']=='M4_Far_00'
                        and fact['status']=='measured' and fact['value']['distance_m']==0.125
                        and point['a']==[1.46875,0.46875,1.875] and point['b']==[1.46875,0.46875,2.0]
                        and point['direction_a_to_b']==[0.0,0.0,1.0],
                        'transfer_historical_125mm_measure_changed')
                proofs['measure'] = {'distance_m':0.125,'a':point['a'],'b':point['b'],'direction':point['direction_a_to_b']}
        if not ordinary and i < 3:
            task = dict(producer['facts']['region_task'])
            summary_counts = dict(task['summary'])
            for key in ('selected_image_count','constructed_image_count'):
                require(summary_counts.pop(key) == len(producer['frames' if key.startswith('selected') else 'constructed_frames']),
                        'task_picture_count_changed/'+label)
            task['summary'] = summary_counts
            global_scope, *locals_ = producer['scopes']
            require(global_scope['scope_id'] == 'global', 'dropped_global_scope')
            if not any(frame['scope_id'] == 'global' for frame in producer['constructed_frames']):
                require(global_scope['frame_refs'] == global_scope['steps'] == global_scope['facts']['observations'] == [],
                        'would_publish_global_raster_without_frame/'+label)
                if not full:
                    require(VERIFY['records'](body['scopes'])[0]['constructed_frame_count'] == 0,
                            'fake_global_scope_count/'+label)
            # Global pixel observations may change. Its bound geometry and the complete local evidence may not.
            equal = (task, producer['binding'],global_scope['binding'],global_scope['facts']['scope'],locals_)
        else:
            equal = (body,producer)
        semantic.append(normalize(equal, paths, binding['source_sha256']))
        service = producer['stages']['service_total']
        client = details['wire']
        received,flushed = (worker[k] for k in ('request_received_ns','reply_completed_ns'))
        response_clock = {
            'worker_envelope_ns':flushed-received,
            'worker_before_service_ns':service['started_ns']-received,
            'service_after_to_worker_flush_ns':flushed-service['closed_ns'],
            'client_decode_ns':client['consumer_json_decoded_ns']-client['received_complete_ns'],
        }
        require(received <= service['started_ns'] <= service['closed_ns'] <= flushed
                and 0 <= response_clock['client_decode_ns']
                and response_clock['worker_envelope_ns'] == worker['request_to_reply_ns'],
                'unbound_service_or_transmit_clock/'+label)
        rows.append({**details,'tx':tx,'pins':{**wires,'producer':pin(path)},'body_schema':body.get('schema'),
                     'wire_times':response_clock,
                     'frame_identities':[(f.get('scope_id','global'),f['view_name'],f['frame_identity'])
                                         for f in producer.get('frames',[])]})
    cold = rows[0]
    stages = cold['stages']
    intervals = {name:OLD['num_stage'](stages,name) for name in stages}
    if not ordinary:
        has_global = any(frame['scope_id']=='global' for frame in frames)
        skip = cold['work'].get('global_first_frame_skipped',False)
        require(skip is not has_global,'global_first_frame_work_not_its_cold_raster/'+label)
        if skip:
            require('patch_mapping_global' not in stages and 'render_and_publish_global_SCENE' not in stages
                    and intervals.get('pixel_bounds_before_first_frame',0)>0,'hidden_global_raster_work/'+label)
            send_global = read(root/'product_full/call_001/SERVICE_RESULT.json')['scopes'][0]
            bounds = [r['upper_bound'] for d in send_global['skipped_views'] for r in d['regions']]
            require(bounds and max(bounds)==(9 if fixture=='transfer' else 6)
                    and all(d['actual_observation'] is False for d in send_global['skipped_views']),
                    'unqualified_first_frame_certificate/'+label)
        require(rows[0]['frame_identities']==rows[1]['frame_identities'],'warm_frame_ids_changed/'+label)
    return {'label':label,'fixture':fixture,'role':role,'requests':rows,'frames':frames,'proofs':proofs,'captures':captures,
            'product':summary['product'],'semantic':semantic,'verification':pin(root/'SUMMARY.json'),
            'worker_wire':pin(audit),
            'metrics':{'cold_RPC_ns':cold['wire']['elapsed_ns'],'complete_MCP_ns':summary['whole_window_ns'],
                       'service_ns':intervals.get('service_total',0),'stage_ns':intervals,'close_ns':release['elapsed_ns'],
                       'raster_publish_ns':sum(v for k,v in intervals.items() if k.startswith('render_and_publish_')),
                       'frame_file_bytes':disk_bytes,'memory':summary['memory']}}


def pair(old, new):
    labels = (old['label'],new['label'])
    require(old['semantic'] == new['semantic'], 'retained_semantics_drift/'+str(labels))
    require([p['sha256'] for p in old['captures']] == [p['sha256'] for p in new['captures']]
            and [r['tx'] for r in old['requests']] == [r['tx'] for r in new['requests']],
            'two_arms_did_not_use_same_capture_and_request/'+str(labels))
    a,b = (len(arm['frames']) for arm in (old,new))
    require((a,b) in ({'timed':{(3,2)},'main_full':{(3,2)},'held':{(3,3)},'ordinary':{(0,0)},
                'transfer':{(3,2)}}[old['role']]),'unexpected_cold_production_raster_pair/'+str(labels))
    if old['role'] == 'held':
        for slot in (old,new):
            require([row['object_name'] for row in slot['proofs']['1']['public_witnesses']] == ['N22']
                    and slot['proofs']['1']['original_native_PNG_blocks'] == 1,
                    'lost_N22_original_global_witness')
            req = slot['requests'][0]['pins']['RX']['path']
            body = json.loads(read(req)['result']['content'][0]['text'])
            pixel, = VERIFY['records'](body['pixel_shortfalls'])
            require((pixel['visible_surface_pixels'],pixel['contrasting_boundary_pixels']) == (8835,0),
                    'lost_N10_local_evidence_shortfall')
    return {'pair':labels,'rasters':[a,b],
            'relative':{name:1-new['metrics'][name]/old['metrics'][name] for name in
                        ('cold_RPC_ns','complete_MCP_ns','service_ns','raster_publish_ns')
                        if old['metrics'][name]>0}, 'retained_semantics_equal':True}


def main(runtime, exact_path, output):
    paths = {'N':BASE,'P':CANDIDATE}
    frozen = read(NS/'FROZEN.json')
    journal = runtime/'FORMAL_SEQUENCE.jsonl'
    rows = [json.loads(line) for line in journal.read_bytes().splitlines()]
    schedule = rows[0]['schedule']
    require([item[0] for item in schedule] == ['N1','P1','P2','N2','N3','P3','HN','HP','TN','TP','FN','FP','ON','OP']
            and rows[0]['freeze_sha256'] == pin(NS/'FROZEN.json')['sha256']
            and rows[0]['exact_receipt'] == pin(exact_path),'unexpected_frozen_sequence')
    require([item['event'] for item in rows] == ['frozen']+['start','exit']*len(schedule)+['complete'],
            'incomplete_frozen_run')
    negatives = output.with_suffix('')
    negatives.mkdir(exist_ok=False)
    arms = {}
    last = 0
    for (label,fixture,role,flag),started,finished in zip(schedule,rows[1:-1:2],rows[2:-1:2],strict=True):
        kind = 'P' if label.startswith('P') or label.endswith('P') else 'N'
        install = read(paths[kind])
        root = runtime/('controls' if flag else 'arms')/label
        require(install['preparation_git'] == frozen[{'N':'baseline_git','P':'candidate_git'}[kind]]
                and started['label'] == finished['label'] == label and started['fixture'] == fixture
                and started['role'] == role and started['binding'] == pin(paths[kind])
                and last <= started['started_ns'] < finished['finished_ns']
                and finished['exit_code'] == 0 and finished['summary'] == pin(root/'SUMMARY.json')
                and finished['wall_ns'] == finished['finished_ns']-started['started_ns'],
                'formal_launch_or_identity_changed/'+label)
        last = finished['finished_ns']
        arm = score_arm(root,started,install,negatives)
        arm['metrics']['outer_slot_ns'] = finished['wall_ns']
        require(arm['metrics']['complete_MCP_ns'] < finished['wall_ns'],'inverted_window_meter/'+label)
        arms[label] = arm
    compared = [pair(arms[n],arms[p]) for n,p in PAIRS]
    cold = median(r['relative']['cold_RPC_ns'] for r in compared[:3])
    whole = median(r['relative']['complete_MCP_ns'] for r in compared[:3])
    limit = frozen['min_paired_median_cold_MCP_improvement']
    native = sum(sum(r['raster_attempts'] for r in arm['requests']) for arm in arms.values())
    for arm in arms.values():
        arm.pop('semantic')
    return {'passed':cold >= limit,'quality_passed':True,'three_pair_cold_median_reduction':cold,
            'three_pair_complete_MCP_median_reduction':whole,'target':limit,'journal':pin(journal),
            'exact':pin(exact_path),'pairs':compared,'arms':arms,
            'denominators':{'all_completed':len(arms),'main_pairs':3,'holdout_pairs':1,'transfer_pairs':1,
                            'all_calls':sum(len(arm['requests']) for arm in arms.values()),
                            'all_actual_rasters':native,'Blender':0,'models':0,'replacements':0}}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--exact',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args = p.parse_args()
    try:
        score = main(args.runtime.resolve(strict=True), args.exact, args.output)
    except (ValueError, KeyError, OSError, IndexError) as exc:
        score = {'passed':False,'quality_passed':False,'error_type':type(exc).__name__,'error':str(exc)}
    with args.output.open('x',encoding='utf-8',newline='\n') as handle:
        json.dump(score,handle,ensure_ascii=False,indent=2,allow_nan=False)
        handle.write('\n')
    print(json.dumps({k:v for k,v in score.items() if k not in ('arms','pairs')}),flush=True)
    raise SystemExit(0 if score['passed'] else 1)

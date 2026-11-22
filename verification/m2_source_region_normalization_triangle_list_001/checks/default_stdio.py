"""Check actual stdio calls using unchanged default triangle consumers."""

import json
from pathlib import Path
from runpy import run_path
import sys


V = Path(__file__).resolve().parents[2]
OLD = run_path(str(V/'m4_source_region_nonplanar_short_circuit_001/score.py'))
read, require, pin = (OLD[k] for k in ('read','require','pin'))


def default_cli(packet,role):
    proof=OLD['CLI'](packet,require_all=role=='region_task')
    if role=='region_task':
        return proof
    helpers,policy=run_path(str(V/'m4_cross_scale_live_qualification_001/checks/delivery.py'))['budget_helpers']()
    probe=V/'m5_global_observe_measure_qualification_001/checks'
    previous=sys.path[:]
    try:
        sys.path.insert(0,str(probe))
        omitted=run_path(str(probe/'live_wire.py'))['omitted_paths']
    finally:
        sys.path[:]=previous
    require((policy['MCP_bytes'],policy['history_approximate_tokens'])==(12000,3000),'default_CLI_policy_changed')
    result=packet['result']
    text=result['content'][0]['text']
    checks=[]
    for seconds in ('0.0000','10.0000','100.0000'):
        original=helpers['model_items'](result,seconds)
        request=helpers['truncate_items'](original,12000)
        history=helpers['truncate_items'](request,3000,token_mode=True)
        for name,items in (('MCP',request),('history',history)):
            _,body=(item['text'] for item in items if item['type']=='input_text')
            lost=omitted(text,body)
            needed=[path for path in lost if (
                tuple(path[:2])==('facts','observations') and path[-1] in ('image_path','image_ref','image_sha256')
                or len(path)>1 and path[0]=='task_result' and ('surface_proximity' in path or path[1] in ('pair_order','objects')))]
            if role=='target':
                require(not needed,'target_required_image_or_pair_field_clipped')
            checks.append({'phase':name,'head_bytes':len(original[0]['text'].encode()),'lost_leaf_fields':len(lost),
                           'lost_image_and_pair_fields':needed,
                           'required_image_and_pair_fields_retained':not needed})
    proof['full_text_required_fields']=checks
    return proof


def artifacts(root, produced):
    frames,paths = [],{}
    roster = produced.get('constructed_frames',produced['frames'])
    source_order = set()
    for frame in roster:
        identity = frame['frame_identity']
        require(identity not in source_order,'duplicate_current_constructed_default_frame')
        source_order.add(identity)
        record = {'view_name':frame['view_name'],'scope_id':frame.get('scope_id')}
        for kind,name,sha_name in (('png','image_path','image_sha256'),('arrays','arrays_path','arrays_sha256')):
            p = Path(frame[name]).resolve(strict=True)
            rec = pin(p)
            require(p.is_relative_to(root) and rec['sha256']==frame[sha_name],'unbound_actual_default_frame_files')
            record[kind] = rec
            paths[str(p)] = paths[p.as_posix()] = rec['sha256']
        frames.append(record)
    return frames,paths


def inspect(root,binding):
    stamped = read(root/'SUMMARY.json')
    require(stamped['passed'] and stamped['fixture']=='defaults' and stamped['default_controls'] and not stamped['controls']
            and stamped['arm']==root.name and all(binding[k]==v for k,v in stamped['product'].items()),
            'default_control_installed_identity_changed')
    closure,_ = OLD['PRIOR']['closed_capture'](root,stamped)
    paths,seen,requests = {},[],[]
    values = []
    wire_log = root/'mcp_io/MCP_IO.jsonl'
    workers = [r for line in wire_log.read_bytes().splitlines() if (r:=json.loads(line))['method']=='tools/call']
    require(len(stamped['requests'])==len(workers)==3,'wrong_three_default_cases')
    for idx,(summary,worker) in enumerate(zip(stamped['requests'],workers,strict=True),1):
        tx,rpc,body,pngs,wires = OLD['verify_wire'](root,summary,worker)
        path = root/'product_full'/f'call_{idx:03d}'/'SERVICE_RESULT.json'
        full = read(path)
        r = 'region_task' in full['facts']
        t = full['binding']['capture_scope']=='target_observation_meshes'
        role = ('region_task' if r else 'target' if t else 'ordinary')
        requests.append(role)
        png_data = [Path(f['image_path']).read_bytes() for f in full['frames']]
        require(not rpc['result']['isError'] and tx['params']['arguments']['query']['mode']=='active_observation'
                and full['result_kind']=='active_observation' and full['read_only'] is True
                and full['execution_authority'] is False and pngs==png_data
                and full['work']==summary['work'] and full['stages']==summary['stages']
                and full['work']['raster_attempts']==summary['raster_attempts']==worker['raster_actual'],
                'default_mode_actual_raster_image_or_stage_changed/'+role)
        current,by_path = artifacts(root,full)
        saved = stamped['constructed_frames_by_request'][idx-1]
        historical = stamped['historical_frames_by_request'][idx-1]
        require(len(current)==summary['raster_attempts']==len(saved)==len(historical),
                'default_mode_actual_constructed_count_changed')
        for live,reported,old in zip(current,saved,historical,strict=True):
            require(live['view_name']==reported['view_name']==old['view_name']
                    and all(live[k]==reported[k] and {a:live[k][a] for a in ('sha256','bytes')}==
                            {a:old[k][a] for a in ('sha256','bytes')} for k in ('png','arrays')),
                    'default_original_png_or_arrays_changed')
        seen.extend(current)
        paths.update(by_path)
        values.append((tx,body,full))
    require(requests==['region_task','ordinary','target'],'unexpected_default_mode_order')
    captures=[]
    for i,call in enumerate(closure['calls'],1):
        current=root/f'CAPTURE_{i:02d}.json'
        require(read(current)['capture_state']==call['capture_state'],'default_provider_capture_state_differs')
        captures.append(pin(current)['sha256'])
    require([call['resource_count'] for call in closure['calls']]==[20,0,3],
            'default_current_capture_or_target_scope_resource_count_changed')
    observations=[]
    for idx,((tx,body,full),row,role) in enumerate(zip(values,stamped['requests'],requests,strict=True),1):
        p = root/'mcp'/f"rpc_{row['wire']['index']:02d}"/'RX.bin'
        proof=default_cli(read(p),role)
        obs={'default_role':role,'is_error':False,'raster_attempts':row['raster_attempts'],
             'wire_ns':row['wire']['elapsed_ns'],'text_bytes':row['text_bytes'],'PNG_bytes':row['PNG_bytes'],
             'result_cache_hit':row['result_cache_hit'],'CLI':proof,'stages_ns':OLD['clocks'](full['stages']),
             'wire':{'RX':pin(p),'TX':pin(p.with_name('TX.bin'))}}
        observations.append(obs)
    return {'label':root.name,'fixture':'defaults','control':True,'product':stamped['product'],
            'capture_exact_SHA256':captures,'actual_capture_deltas':closure['calls'],'measurements':observations,
            'frames':seen,'clock_whole_ns':stamped['whole_window_ns'],'peak_memory':stamped['memory'],
            'held_EOF':pin(stamped['held_close']['path']),
            'same_result':[OLD['normal'](v,paths,binding['source_sha256']) for v in values]}

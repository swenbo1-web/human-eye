"""Observe GC and decode intervals on separate, held production stdio runs."""

import argparse
import base64
import gc
import json
from math import ceil
from pathlib import Path
from runpy import run_path
from statistics import median
import sys
import time


HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import replay
from inputs import BASE, RUN, SEAL, digest, pin, read, require, sealed_inputs, write


LABELS = ('HA1','HB1','HB2','HA2')
WARM = 10
PHASE = 'source_region_GC_and_decode_diagnostic'


def case():
    original = sealed_inputs('main')
    query = original['calls'][0]
    full,delta = original['deltas']
    captures = [(value, {'command':'capture','params':{}}, original['terminal'])
                for value in [full]+[delta]*WARM]
    return {**original,'name':'defaults','calls':[
        query,*({**query,'id':f'hot_same_selection_{i:02d}'} for i in range(1,WARM+1))
    ],'capture_plan':captures}


def worker(root,binding):
    require(root.parent==RUN/'diagnostics' and root.name in LABELS,'invalid_hot_worker_scope')
    source = case()
    starts, pauses, decodes = {},[],[]
    initial = {'enabled':gc.isenabled(),'thresholds':list(gc.get_threshold())}

    def collect(phase, info):
        now = time.perf_counter_ns()
        generation = info['generation']
        if phase == 'start':
            starts[generation] = now
        elif generation in starts:
            pauses.append({'generation':generation,'start_ns':starts.pop(generation),'end_ns':now,
                           'collected':info['collected'],'uncollectable':info['uncollectable']})

    def captured(index, start, ready, current):
        decodes.append({'capture_index':index,'start_ns':start,'end_ns':ready,
                        'capture_state':current['capture_state']})

    gc.callbacks.append(collect)
    try:
        return replay.worker(root,binding,'main',False,source=source,on_capture=captured)
    finally:
        gc.callbacks.remove(collect)
        current = {'enabled':gc.isenabled(),'thresholds':list(gc.get_threshold())}
        require(current==initial,'actual_worker_GC_settings_changed')
        write(root/'GC_PROBE.json',{'phase':PHASE,'config_before':initial,'config_after':current,
                                  'pauses':pauses,'decodes':decodes,'still_open':starts})


def overlap(a,b,x,y):
    return max(0,min(b,y)-max(a,x))


def process(block,binding_path,source,cli):
    block.mkdir(parents=True,exist_ok=False)
    registered = read(binding_path)
    statics = replay.retained()
    from runtime import ProductionStdioClient
    ProductionStdioClient.finish.__globals__['SOURCE_SHA'] = registered['source_sha256']
    arg = [sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),'--worker',str(block),
           '--binding',str(binding_path)]
    launched=time.perf_counter_ns()
    owned=ProductionStdioClient(arg,block,block/'mcp',launched+120_000_000_000,worker_evidence=block/'mcp_io')
    replies=[]
    try:
        who=owned.call(statics['INIT'])['result']['_meta']['human_eye']
        require(who['source_kind']=='installed_distribution' and who['source_sha256']==registered['source_sha256'],
                'wrong_registered_hot_install')
        owned.call(statics['NOTIFY'])
        require(owned.call(statics['LIST'])['result']['tools']==read(replay.CATALOGUE),'diagnostic_catalogue_drift')
        for req in source['calls']:
            reply=owned.call(req)
            require(reply.get('error') is None and reply['result']['isError'] is False,'actual_hot_probe_request_failed')
            replies.append(reply)
    finally:
        close=owned.finish()
        ended=time.perf_counter_ns()
    require(close['confirmed'] and close['process_handle_closed'] and close['stdout_eof_seen']
            and close['production_eof_and_exit_verified'] and not close['forced_kill'] and close['exit_code']==0,
            'hot_worker_did_not_close_and_exit')
    probe=read(block/'GC_PROBE.json')
    closed=read(block/'REPLAY_CLOSE.json')
    require(probe['config_before']==probe['config_after'] and probe['phase']==PHASE
            and closed['old_sources_unchanged'] and closed['actual_Blender_starts']==closed['actual_models']==0,
            'hot_probe_environment_or_source_changed')
    require([c['resource_count'] for c in closed['calls']]==[2]+[0]*WARM
            and all(c['capture_state']==closed['calls'][0]['capture_state'] for c in closed['calls']),
            'hot_probe_capture_or_resource_sequence_changed')
    native=[json.loads(line) for line in (block/'mcp_io/MCP_IO.jsonl').read_bytes().splitlines()]
    wire=[row for row in native if row['method']=='tools/call']
    results=[]
    for i,(reply,request,trace,receipt,cap,dec) in enumerate(zip(replies,source['calls'],wire,owned.records[3:],
                                            closed['calls'],probe['decodes'],strict=True)):
        result=read(block/'product_full'/f'call_{i+1:03d}'/'SERVICE_RESULT.json')
        frame,=result['frames']
        contents=reply['result']['content']
        require(len(contents)==2 and contents[0]['type']=='text' and contents[1]['type']=='image'
                and digest(base64.b64decode(contents[1]['data'],validate=True))==source['frames'][0]['png'],
                'hot_original_native_PNG_changed')
        require(digest(Path(frame['arrays_path']).read_bytes())==source['frames'][0]['arrays'],
                'hot_original_NPZ_changed')
        if i==0:
            expected=frame['frame_identity'],result['region_ref']
        require((frame['frame_identity'],result['region_ref'])==expected
                and result['work']['raster_attempts']==trace['raster_actual']==int(i==0)
                and result['work']['geometry_normalization_calls']==int(i==0)
                and result['work'].get('frame_reuses',0)==int(i>0)
                and bool(result['work']['prepare_cache_hit'])==(i>0),
                'hot_region_current_binding_cache_or_raster_changed')
        clock=result['stages']['service_total']
        require(trace['request_received_ns']<=dec['start_ns']<=dec['end_ns']<=trace['reply_completed_ns']
                and dec['end_ns']-dec['start_ns']==cap['decode_elapsed_ns']
                and dec['capture_state']==cap['capture_state'],'GC_decode_and_wire_intervals_not_bound')
        wire_receipt=statics['bound_wire'](block,request,receipt,trace)
        event_gc=[]
        for event in probe['pauses']:
            span=overlap(event['start_ns'],event['end_ns'],trace['request_received_ns'],trace['reply_completed_ns'])
            if span:
                event_gc.append({**event,'in_request_ns':span,
                                 'in_decode_ns':overlap(event['start_ns'],event['end_ns'],dec['start_ns'],dec['end_ns'])})
        results.append({'is_warm':i>0,'call':i+1,'RPC_ns':receipt['elapsed_ns'],
                        'service_ns':clock['elapsed_ns'],'worker_RPC_ns':trace['request_to_reply_ns'],
                        'decode_ns':cap['decode_elapsed_ns'],'GC_events':event_gc,
                        'wire':wire_receipt,'fixed_CLI':cli(reply,require_all=True)})
    require(len(results)==1+WARM,'unexpected_hot_sample_count')
    return {'slot':block.name,'binding':pin(binding_path),'source_sha256':registered['source_sha256'],
            'results':results,'count_cold':1,'count_warm':WARM,'complete_MCP_ns':ended-launched,
            'GC_config':probe['config_before'],'GC_raw':pin(block/'GC_PROBE.json'),
            'held_close':pin(block/'mcp/HELD_CLOSE.json'),'read_cache':pin(block/'REPLAY_CLOSE.json')}


def observe(output):
    quals=run_path(str(HERE.parent/'qualification.py'))
    config=quals['verified_freeze']()
    require(config['hot_diagnostic']['schedule']==list(LABELS) and config['hot_diagnostic']['warm_per_process']==WARM,
            'hot_plan_differs_from_frozen_slots')
    sequence = (RUN/'FORMAL_SEQUENCE.jsonl').read_bytes().splitlines()
    require(json.loads(sequence[-1])['event']=='complete',
            'hot_probe_requires_closed_formal_clocks')
    install=HERE.parent/'install/PRODUCT_RUN_BINDING.json'
    require(read(install)['preparation_git']==config['candidate_git'],'wrong_candidate_for_hot_probe')
    base=read(BASE)
    sys.path[:0]=[base['dependency_root'],read(SEAL/'SHARED_DEPENDENCY.json')['dependency_root'],
                  str(replay.PRIOR/'harness')]
    source=case()
    fixed=run_path(str(replay.CLI_PATH))['fixed_cli']
    home=RUN/'diagnostics'
    home.mkdir(exist_ok=False)
    seen={}
    for label in LABELS:
        started=time.perf_counter_ns()
        row=process(home/label,BASE if label.startswith('HA') else install,source,fixed)
        row['controller_ns']=time.perf_counter_ns()-started
        write(home/label/'METRIC.json',row)
        seen[label]=row
        print('Hot diagnostic',label,'closed',row['count_warm'],flush=True)

    def percentiles(rows):
        ns=sorted(rows)
        return {'p50_ns':median(ns),'p95_ns':ns[ceil(.95*len(ns))-1],
                'minimum_ns':ns[0],'maximum_ns':ns[-1]}

    pools={}
    for arm,labels in (('baseline',('HA1','HA2')),('candidate',('HB1','HB2'))):
        measured=[row for label in labels for row in seen[label]['results'] if row['is_warm']]
        requests=[ev for row in measured for ev in row['GC_events']]
        require(len(measured)==2*WARM,'one_hot_diagnostic_arm_lacks_its_full_denominator')
        pools[arm]={'warm_count':len(measured),'RPC':percentiles([r['RPC_ns'] for r in measured]),
                    'service':percentiles([r['service_ns'] for r in measured]),
                    'decode':percentiles([r['decode_ns'] for r in measured]),
                    'decode_less_observed_GC':percentiles([r['decode_ns']-sum(e['in_decode_ns'] for e in r['GC_events'])
                                                           for r in measured]),
                    'requests_with_Gen2':sum(any(e['generation']==2 for e in r['GC_events']) for r in measured),
                    'Gen2_pause_ns':[e['in_request_ns'] for e in requests if e['generation']==2],
                    'Gen2_inside_decode_ns':[e['in_decode_ns'] for e in requests if e['generation']==2 and e['in_decode_ns']]}
    write(output,{'passed':True,'phase':PHASE,'arms':seen,'statistics':pools,'extra_cold':4,'warm':40,
                  'schedule':list(LABELS),'quantiles':'p50 median, p95 nearest rank','new_Blender':0,'new_models':0})


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'isolated_no_bytecode_runtime_required')
    p=argparse.ArgumentParser(description=__doc__)
    m=p.add_mutually_exclusive_group(required=True)
    m.add_argument('--worker',type=Path)
    m.add_argument('--output',type=Path)
    p.add_argument('--binding',type=Path)
    a=p.parse_args()
    if a.worker:
        require(a.binding is not None,'hot_worker_binding_required')
        raise SystemExit(worker(a.worker.resolve(strict=True),a.binding.resolve(strict=True)))
    observe(a.output.resolve())

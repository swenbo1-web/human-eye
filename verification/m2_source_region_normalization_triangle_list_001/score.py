"""Score the fixed isolated stdio series, retaining raw timing and output anchors."""

import argparse
import json
from pathlib import Path
from runpy import run_path
from statistics import median


NS = Path(__file__).resolve().parent
V = NS.parent
Q = run_path(str(NS/'qualification.py'))
OLD = run_path(str(V/'m4_source_region_nonplanar_short_circuit_001/score.py'))
read, pin, require, write = (Q[k] for k in ('read','pin','require','write'))
PAIRS = (('N1','P1'),('N2','P2'),('N3','P3'),('HN','HP'),('RN','RP'),('DN','DP'),('CN','CP'),('FN','FP'))


def stage(producer, name):
    row = producer['stages']['region_preparation'][name]
    require(row['closed_ns']-row['started_ns']==row['elapsed_ns']>0,'invalid_nested_preparation_clock/'+name)
    return row['elapsed_ns']


def normalization(root, measurements):
    for number,measured in enumerate(measurements,1):
        if measured['is_error']:
            measured['normalization_ns'] = None
            continue
        prod = read(root/'product_full'/f'call_{number:03d}'/'SERVICE_RESULT.json')
        work = prod['work']
        if not work.get('geometry_normalization_calls'):
            require(measured['result_cache_hit'],'missing_fresh_normalization_outside_hot_request')
            measured['normalization_ns'] = None
            continue
        require(work['geometry_normalization_calls']==1 and work['prepare_calls']==1,
                'expected_one_original_fresh_normalization')
        measured['normalization_ns'] = stage(prod,'geometry_normalization')
        measured['normalization_work'] = {key:work[key] for key in (
            'geometry_normalization_calls','prepare_calls','region_array_preparation_calls')}


def aux_source(root, binding):
    summary = read(root/'SUMMARY.json')
    require(summary['passed'] and summary['fixture']=='dual' and not summary['controls']
            and summary['arm']==root.name and all(summary['product'][k]==binding[k] for k in summary['product'])
            and not summary['construct_frames'] and not summary['historical_frames'],
            'wrong_dual_noimage_frozen_entry')
    closed,_ = OLD['PRIOR']['closed_capture'](root,summary)
    worker_wire = [r for line in (root/'mcp_io/MCP_IO.jsonl').read_bytes().splitlines()
                   if (r:=json.loads(line))['method']=='tools/call']
    require(len(summary['requests'])==len(worker_wire)==len(closed['calls'])==2
            and [r['resource_count'] for r in closed['calls']]==[2,0]
            and closed['calls'][0]['capture_state']==closed['calls'][1]['capture_state'],
            'dual_capture_did_not_use_one_state_and_actual_delta')
    expected = ((311,0.37011719389236364),(331,0.4355468820753541))
    semantics,measurements,captures = [],[],[]
    for i,(row,worker,(count,distance)) in enumerate(zip(summary['requests'],worker_wire,expected,strict=True),1):
        control = root/f'CAPTURE_{i:02d}.json'
        captures.append(pin(control)['sha256'])
        req,rpc,body,pngs,wire = OLD['verify_wire'](root,row,worker)
        path = root/'product_full'/f'call_{i:03d}'/'SERVICE_RESULT.json'
        producer = read(path)
        near = producer['task_result']['facts']['surface_proximity']
        require(not rpc['result']['isError'] and not pngs and not req['params']['arguments']['include_image']
                and producer['work']==row['work'] and producer['stages']==row['stages']
                and not row['raster_attempts'] and worker['raster_actual']==0 and not row['result_cache_hit']
                and all(not producer[key] for key in ('frames',))
                and producer['binding']['capture_state']==read(control)['capture_state']
                and len(producer['region_ref']['source_triangle_indices'])==count
                and near['status']=='measured' and near['value']['distance_m']==distance
                and near['value']['nearest_witness']['direction_a_to_b']==[0.0,0.0,1.0]
                and producer['task_result']['reference']['name']=='Cube',
                'actual_dual_noimage_selection_measurement_or_raster_changed')
        OLD['verify_region'](producer,body,pngs,root,'main')
        stages = OLD['clocks'](row['stages'])
        require('source_region_rectangle_selection' not in stages,'noimage_entered_image_branch')
        measurements.append({'wire':wire,'wire_ns':row['wire']['elapsed_ns'],'raster_attempts':0,'is_error':False,
                             'result_cache_hit':False,'text_bytes':row['text_bytes'],'PNG_bytes':0,'stages_ns':stages,
                             'CLI':OLD['CLI'](rpc,require_all=True),'producer':pin(path),'facts':near})
        semantics.append(OLD['normal']((req,body,producer),{},binding['source_sha256']))
    return {'label':root.name,'fixture':'dual','control':False,'product':summary['product'],
            'capture_exact_SHA256':captures,'actual_capture_deltas':closed['calls'],'measurements':measurements,
            'frames':[],'clock_whole_ns':summary['whole_window_ns'],'peak_memory':summary['memory'],
            'held_EOF':pin(summary['held_close']['path']),'same_result':semantics}


def comparisons(a,b):
    require(a['fixture']==b['fixture'] and a['capture_exact_SHA256']==b['capture_exact_SHA256']
            and a['same_result']==b['same_result'],'actual_public_result_or_producer_changed/'+a['label']+'/'+b['label'])
    require([{k:f[k]['sha256'] for k in ('png','arrays')} for f in a['frames']]==
            [{k:f[k]['sha256'] for k in ('png','arrays')} for f in b['frames']],
            'verified_original_raster_bytes_not_equal')
    metrics = {'slots':[a['label'],b['label']],'fixture':a['fixture'],'equal':True}
    if a['fixture'] in ('main','holdout','rectangle') and not a['control']:
        m,n=(x['measurements'][0] for x in (a,b))
        metrics.update(geometry_normalization_reduction=1-n['normalization_ns']/m['normalization_ns'],
                       cold_service_reduction=1-n['stages_ns']['service_total']/m['stages_ns']['service_total'],
                       cold_rpc_reduction=1-n['wire_ns']/m['wire_ns'],
                       complete_MCP_reduction=1-b['clock_whole_ns']/a['clock_whole_ns'])
    elif a['fixture']=='defaults':
        for x,y in zip(a['measurements'],b['measurements'],strict=True):
            ox,oy=(p['CLI'].get('full_text_required_fields',[]) for p in (x,y))
            require([q['lost_image_and_pair_fields'] for q in ox]==
                    [q['lost_image_and_pair_fields'] for q in oy],'default_legacy_CLI_image_or_measure_loss_changed')
    return metrics


def score(root, default_inspection):
    frozen = Q['verified_freeze']()
    journal = root/'FORMAL_SEQUENCE.jsonl'
    logs = [json.loads(line) for line in journal.read_bytes().splitlines()]
    ordered = frozen['schedule']
    require(logs[0]['schedule']==ordered and logs[0]['freeze_sha256']==pin(NS/'FROZEN.json')['sha256']
            and [r['event'] for r in logs]==['frozen']+['start','exit']*len(ordered)+['complete'],
            'actual_frozen_sequence_did_not_complete')
    exact = read(OLD['PRIOR']['check_pin'](logs[0]['exact_receipt'],root))
    require(exact['passed'] and exact['binding_git']==frozen['candidate_git'],'uncertified_candidate_not_for_scoring')
    arms = {}
    previous = 0
    for (label,fixture,control),start,stop in zip(ordered,logs[1:-1:2],logs[2:-1:2],strict=True):
        binding = NS/'install/PRODUCT_RUN_BINDING.json' if label.startswith('P') or label.endswith('P') else Q['BASE_BINDING']
        folder = root/('controls' if control else 'arms')/label
        require(start['label']==stop['label']==label and start['fixture']==fixture
                and start['control']==control and start['binding']==pin(binding)
                and previous<=start['started_ns']<stop['finished_ns']
                and stop['wall_ns']==stop['finished_ns']-start['started_ns']
                and stop['exit_code']==0 and stop['summary']==pin(folder/'SUMMARY.json'),
                'actual_slot_clock_or_receipt_changed/'+label)
        previous = stop['finished_ns']
        if fixture=='dual':
            arm=aux_source(folder,read(binding))
        elif fixture=='defaults':
            arm=default_inspection(folder,read(binding))
        else:
            arm=OLD['inspect_arm'](folder,fixture,control,read(binding))
        if fixture!='defaults':
            normalization(folder,arm['measurements'])
        arm['controller_ns']=stop['wall_ns']
        require(stop['wall_ns']>arm['clock_whole_ns'],'controller_clock_does_not_include_held_stdio')
        arms[label]=arm
    paired = [comparisons(arms[a],arms[b]) for a,b in PAIRS]
    medians = {key:median(pair[key] for pair in paired[:3]) for key in (
        'geometry_normalization_reduction','cold_service_reduction','cold_rpc_reduction','complete_MCP_reduction')}
    limits = frozen['gate']
    passed = (medians['geometry_normalization_reduction']>=limits['geometry_normalization_paired_median_reduction']
              and medians['cold_service_reduction']>=limits['cold_service_paired_median_reduction'])
    for arm in arms.values():
        arm.pop('same_result')
    calls = [call for arm in arms.values() for call in arm['measurements']]
    return {'passed':passed,'quality_passed':True,'sequence':pin(journal),'paired_median':medians,'pairs':paired,'arms':arms,
            'denominators':{'slots':len(arms),'calls':len(calls),'rasters':sum(c['raster_attempts'] for c in calls),
                            'rejections':sum(c['is_error'] for c in calls),'Blender':0,'models':0,'replacements':0}}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    try:
        from runpy import run_path as load_default
        inspector=load_default(str(NS/'checks/default_stdio.py'))['inspect']
        result=score(args.runtime.resolve(strict=True),inspector)
    except (OSError,ValueError,TypeError,KeyError,IndexError) as exc:
        result={'passed':False,'quality_passed':False,'error_type':type(exc).__name__,'error':str(exc)}
    write(args.output,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('arms','pairs')},ensure_ascii=False),flush=True)
    raise SystemExit(0 if result['passed'] else 1)

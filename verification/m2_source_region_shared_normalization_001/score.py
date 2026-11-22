"""Score the unchanged stdio evidence and the distinct-source-region thresholds."""

import argparse
import json
from pathlib import Path
from runpy import run_path
from statistics import median


NS = Path(__file__).resolve().parent
V = NS.parent
Q = run_path(str(NS/'qualification.py'))
PREVIOUS = run_path(str(V/'m2_source_region_normalization_triangle_list_001/score.py'))
OLD = PREVIOUS['OLD']
DEFAULT = run_path(str(V/'m2_source_region_normalization_triangle_list_001/checks/default_stdio.py'))['inspect']
read, pin, require, write = (Q[k] for k in ('read','pin','require','write'))
PAIRS = (('N1','P1'),('N2','P2'),('N3','P3'),('IN','IP'),('PN','PP'),('HN','HP'),('RN','RP'),('CN','CP'),('FN','FP'),('EN','EP'))
DISTANCES = [(311,0.37011719389236364),(331,0.4355468820753541)]


def interval(row):
    require(row['closed_ns']-row['started_ns']==row['elapsed_ns']>0,'invalid_region_prepare_stage')
    return row['elapsed_ns']


def fresh_diagnostics(root, arm, is_candidate):
    if arm['fixture']=='defaults':
        return
    expected_share = {
        'dual':{2},'paired_image':{2},'bad_edge':{3},'main':set() if arm['control'] else {3},
    }.get(arm['fixture'],set()) if is_candidate else set()
    observed=set()
    for step,call in enumerate(arm['measurements'],1):
        if call['is_error']:
            require(step not in expected_share,'planned_sharing_request_rejected')
            continue
        producer=read(root/'product_full'/f'call_{step:03d}'/'SERVICE_RESULT.json')
        work=producer['work']
        hit=work['prepare_cache_hit']
        share=work.get('geometry_normalization_shared_hit',False)
        actual_norms=work['geometry_normalization_calls']
        require(type(hit) is bool and type(share) is bool and
                work['prepare_calls']==work['region_array_preparation_calls']==work['camera_preparation_calls']==int(not hit)
                and actual_norms==int(not (hit or share)) and not (hit and share),
                'unbound_normalization_share_or_preparation_count/'+root.name)
        if share:
            observed.add(step)
        details=producer['stages'].get('region_preparation')
        if hit:
            require(details is None,'cached_region_repeated_fresh_preparation')
        else:
            require(details is not None and (not is_candidate or 'scene_validation' in details),
                    'fresh_region_did_not_independently_validate_scene')
            call['geometry_normalization_stage_ns']=interval(details['geometry_normalization'])
            if 'scene_validation' in details:
                call['complete_scene_validation_ns']=interval(details['scene_validation'])
        call.update(shared_normalization_hit=share,geometry_normalization_calls=actual_norms,
                    prepare_cache_hit=hit,fresh_region_preparations=work['prepare_calls'])
    require(observed==expected_share,'unexpected_same_state_registry_share_positions/'+root.name)


def check_pair_value(producer, expected):
    count,distance=expected
    fact=producer['task_result']['facts']['surface_proximity']
    value=fact['value']
    require(len(producer['region_ref']['source_triangle_indices'])==count
            and producer['task_result']['reference']['name']=='Cube'
            and fact['status']=='measured' and value['distance_m']==distance
            and value['nearest_witness']['direction_a_to_b']==[0.0,0.0,1.0],
            'current_bounds_or_whole_Cube_surface_point_pair_changed')


def special(root,fixture,binding):
    summary=read(root/'SUMMARY.json')
    require(summary['passed'] and summary['fixture']==fixture and not summary['controls']
            and summary['arm']==root.name and all(binding[k]==v for k,v in summary['product'].items()),
            'actual_special_source_region_binding_changed')
    state,release=OLD['PRIOR']['closed_capture'](root,summary)
    wire=[row for line in (root/'mcp_io/MCP_IO.jsonl').read_bytes().splitlines()
          if (row:=json.loads(line))['method']=='tools/call']
    actual_images=fixture=='paired_image'
    require(len(wire)==len(summary['requests'])==len(state['calls'])==(2 if actual_images else 3)
            and all(x['capture_state']==state['calls'][0]['capture_state'] for x in state['calls']),
            'special_compatibility_slot_not_same_capture')
    values,frames,measurements,captures,cameras=[],[],[],[],[]
    paths={}
    initial=None
    for i,(q,worker,current) in enumerate(zip(summary['requests'],wire,state['calls'],strict=True),1):
        tx,rpc,body,pngs,wire_paths=OLD['verify_wire'](root,q,worker)
        capture=root/f'CAPTURE_{i:02d}.json'
        captured=read(capture)
        require(captured['capture_state']==current['capture_state'],'wrong_compatibility_capture_ref')
        captures.append(pin(capture)['sha256'])
        recorded=root/'product_full'/f'call_{i:03d}'/'SERVICE_RESULT.json'
        expected_error=not actual_images and i==2
        require(rpc['result']['isError'] is expected_error,'invalid_edge_request_did_not_reject_and_recover')
        require(bool(tx['params']['arguments']['include_image'])==actual_images,'unexpected_compatibility_image_mode')
        measurement={'wire':wire_paths,'wire_ns':q['wire']['elapsed_ns'],
                     'raster_attempts':q['raster_attempts'],'text_bytes':q['text_bytes'],'PNG_bytes':q['PNG_bytes'],
                     'result_cache_hit':q['result_cache_hit'],'stages_ns':OLD['clocks'](q['stages']),
                     'is_error':expected_error,'producer':None if expected_error else pin(recorded),'CLI':None}
        require(q['raster_attempts']==worker['raster_actual']==int(actual_images),
                'unexpected_compatibility_raster_count')
        if expected_error:
            require(body['error']=='invalid topology indices' and not pngs and not recorded.is_file(),
                    'nonhashed_invalid_edge_failed_other_than_expected_scene_validation')
            values.append((tx,body))
        else:
            producer=read(recorded)
            require(q['stages']==producer['stages'] and q['work']==producer['work'],
                    'producer_and_worker_counters_diverged')
            if initial is None:
                initial=producer['binding']
            else:
                for k in ('capture_state','ordered_geometry_sha256','geometry_identity','objects','display_identity','source'):
                    require(producer['binding'][k]==initial[k],'fresh_second_region_not_bound_to_same_geometry/'+k)
            check_pair_value(producer,DISTANCES[int(i>1)])
            image=OLD['verify_region'](producer,body,pngs,root,'main' if i==1 else fixture)
            if actual_images:
                require(image is not None and image['closed_public_path_usable'],'new_distinct_region_image_ref_not_usable')
                shot={'view_name':image['view'],'png':image['png'],'arrays':image['arrays']}
                for field in ('png','arrays'):
                    art=Path(shot[field]['path'])
                    paths[str(art)]=paths[art.as_posix()]=shot[field]['sha256']
                frames.append(shot)
                cameras.append(producer['binding']['camera_identity'])
                measurement['image']=image
            else:
                require(image is None,'noimage_wrong_product_visualization')
            values.append((tx,body,producer))
            measurement['CLI']=OLD['CLI'](rpc,require_all=True)
        measurements.append(measurement)
    if actual_images:
        require(len(set(cameras))==2 and len(set(x['png']['sha256'] for x in frames))==2,
                'distinct_source_regions_used_one_camera_or_copied_image')
        for raw,saved in zip(frames,summary['construct_frames'],strict=True):
            require(all(raw[k]==saved[k] for k in raw),'actual_dual_image_producer_artifacts_changed')
    return {'label':root.name,'fixture':fixture,'control':False,'product':summary['product'],
            'capture_exact_SHA256':captures,'actual_capture_deltas':state['calls'],'measurements':measurements,
            'frames':frames,'clock_whole_ns':summary['whole_window_ns'],'peak_memory':summary['memory'],
            'held_EOF':pin(summary['held_close']['path']),
            'same_result':[OLD['normal'](val,paths,binding['source_sha256']) for val in values]}


def inspect(folder,fixture,control,binding):
    if fixture=='defaults':
        return DEFAULT(folder,binding)
    if fixture=='dual':
        result=PREVIOUS['aux_source'](folder,binding)
    elif fixture in ('paired_image','bad_edge'):
        result=special(folder,fixture,binding)
    else:
        result=OLD['inspect_arm'](folder,fixture,control,binding)
    fresh_diagnostics(folder,result,binding['preparation_git']!=Q['BASE'])
    return result


def compare(old,new):
    require(old['capture_exact_SHA256']==new['capture_exact_SHA256']
            and old['same_result']==new['same_result'],'product_semantics_or_captured_source_drift/'+old['label'])
    require([[r[k]['sha256'] for k in ('png','arrays')] for r in old['frames']]==
            [[r[k]['sha256'] for k in ('png','arrays')] for r in new['frames']],
            'actual_original_mcp_image_arrays_drift')
    if old['fixture']=='defaults':
        for a,b in zip(old['measurements'],new['measurements'],strict=True):
            p,q=(x['CLI'].get('full_text_required_fields',[]) for x in (a,b))
            require([i['lost_image_and_pair_fields'] for i in p]==[i['lost_image_and_pair_fields'] for i in q],
                    'existing_default_Full_CLI_truncation_changed')
    paired={'labels':[old['label'],new['label']],'fixture':old['fixture'],'quality_equal':True}
    if old['fixture']=='dual':
        steps=[x['measurements'] for x in (old,new)]
        require([[q['geometry_normalization_calls'] for q in r] for r in steps]==[[1,1],[1,0]],
                'timed_dual_normalizations_not_two_to_one')
        second_before,second_after=(r[1]['stages_ns'] for r in steps)
        first_before,first_after=(r[0]['stages_ns'] for r in steps)
        paired.update(second_prepare=1-second_after['region_prepare_lookup']/second_before['region_prepare_lookup'],
                      second_service=1-second_after['service_total']/second_before['service_total'],
                      service_sum=1-(first_after['service_total']+second_after['service_total'])/
                                    (first_before['service_total']+second_before['service_total']),
                      complete_MCP=1-new['clock_whole_ns']/old['clock_whole_ns'])
    return paired


def score(root):
    frozen=Q['verified_freeze']()
    register=root/'FORMAL_SEQUENCE.jsonl'
    events=[json.loads(line) for line in register.read_bytes().splitlines()]
    schedule=frozen['schedule']
    require(events[0]['schedule']==schedule and events[0]['freeze_sha256']==pin(NS/'FROZEN.json')['sha256']
            and [event['event'] for event in events]==['frozen']+['start','exit']*len(schedule)+['complete'],
            'unconfirmed_formal_slots_or_clocks')
    control=read(OLD['PRIOR']['check_pin'](events[0]['exact_receipt'],root))
    require(control['passed'] and control['binding_git']==frozen['candidate_git'],'installed_independent_shared_proof_missing')
    arms={}
    previous=0
    for (label,fixture,control),start,stop in zip(schedule,events[1:-1:2],events[2:-1:2],strict=True):
        folder=root/('arms' if label in Q['TIMED_LABELS'] else 'controls')/label
        binding=Q['BASE_BINDING'] if label in Q['BASE_LABELS'] else NS/'install/PRODUCT_RUN_BINDING.json'
        require(start['label']==stop['label']==label and start['fixture']==fixture
                and start['control']==control and start['binding']==pin(binding)
                and previous<=start['started_ns']<stop['finished_ns']
                and stop['wall_ns']==stop['finished_ns']-start['started_ns']
                and stop['exit_code']==0 and stop['summary']==pin(folder/'SUMMARY.json'),
                'incorrect_held_product_or_controller_time/'+label)
        previous=stop['finished_ns']
        arm=inspect(folder,fixture,control,read(binding))
        require(arm['clock_whole_ns']<stop['wall_ns'],'held_time_outside_controller_window')
        arm['controller_ns']=stop['wall_ns']
        arms[label]=arm
    pairs=[compare(arms[a],arms[b]) for a,b in PAIRS]
    primary={name:median(item[name] for item in pairs[:3])
             for name in ('second_prepare','second_service','service_sum','complete_MCP')}
    limits=frozen['gate']
    passed=(primary['second_prepare']>=limits['second_prepare_paired_median_reduction']
            and primary['second_service']>=limits['second_service_paired_median_reduction']
            and primary['service_sum']>=limits['sum_service_paired_median_reduction'])
    for arm in arms.values():
        arm.pop('same_result')
    requests=[q for arm in arms.values() for q in arm['measurements']]
    return {'passed':passed,'quality_passed':True,'paired_median':primary,'pairs':pairs,'arms':arms,
            'formal_sequence':pin(register),
            'denominators':{'slots':len(arms),'requests':len(requests),'rasters':sum(r['raster_attempts'] for r in requests),
                            'rejections':sum(r['is_error'] for r in requests),'Blender':0,'models':0,'replacements':0}}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args()
    try:
        result=score(a.runtime.resolve(strict=True))
    except (OSError,ValueError,TypeError,KeyError,IndexError) as exc:
        result={'passed':False,'quality_passed':False,'error':str(exc),'error_type':type(exc).__name__}
    write(a.output,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('arms','pairs')},ensure_ascii=False),flush=True)
    raise SystemExit(0 if result['passed'] else 1)

"""Verify actual cold/hot stdio, old compatibility, and the seven geometry fixtures."""

import argparse
import json
from pathlib import Path
from runpy import run_path


NS = Path(__file__).resolve().parents[1]
D = run_path(str(NS/'checks/evidence.py'))
F,G,OLD = (D[k] for k in ('F','G','OLD'))
require,read,pin = (D[k] for k in ('require','read','pin'))
public = OLD['E']['public']
PHASES = ('cold','hot')
SEARCH = ('validated_faces','triangle_pairs','leaf_pair_visits','node_pair_visits','narrow_phase_pairs',
          'tree_builds','intersection_tests','point_face_tests','edge_edge_tests')


def reconcile(saved):
    source = Path(saved['path'])
    actual = pin(source)
    require((actual['sha256'],actual['bytes'])==(saved['sha256'],saved['bytes']),'actual_stored_replay_bytes_changed')
    return source


def events(file):
    return [json.loads(line) for line in file.read_bytes().splitlines() if line]


def read_case(arm,label,*,opted_in):
    case = arm/'cases'/label
    live = read(case/'CASE.json')
    identity = read(reconcile(live['binding']))
    frozen = F['fixture'](label)
    require(live['passed'] and live['label']==label and live['production_evidence_option'] is opted_in
            and set(live['observations'])==set(PHASES)
            and live['actual_Blender_starts']==live['actual_models']==live['actual_rasters']==0,
            'expected_actual_case_lifecycle_not_complete')
    init = read(case/'INITIALIZE.json')['result']['_meta']['human_eye']
    held = read(reconcile(live['held_EOF']))
    eof,close = held['worker_EOF'],held['process_close']
    require(init['source_sha256']==identity['source_sha256']==eof['source_sha256']
            and init['source_kind']=='installed_distribution'
            and held['stdout_eof_observed'] and eof['input_eof_observed'] and eof['closed']
            and close['confirmed'] and close['process_handle_closed'] and close['exit_code']==0
            and eof['old_inputs_unchanged'] and eof['host_requests']==eof['observe_calls']==2
            and eof['network_attempts']==eof['old_write_attempts']==eof['PNG_open_attempts']
              ==eof['raster_attempt_events']==eof['producer_result_substitutions']==eof['geometry_algorithm_substitutions']==0,
            'actual_installed_source_held_eof_or_scope_counts_changed')
    host = events(case/'worker/HOST_CALLS.jsonl')
    solver = [e for e in events(case/'worker/PRODUCT_EVENTS.jsonl') if 'task_work' in e]
    require(len(host)==len(solver)==2,'ordinary_capture_or_surface_operation_count_changed')
    outcomes = {}
    for i,phase in enumerate(PHASES):
        row = live['observations'][phase]
        raw = {name:reconcile(row[name]) for name in ('request','response','public','TX','RX','receipt')}
        tx,rx = (raw[key].read_bytes() for key in ('TX','RX'))
        request,reply = json.loads(tx),json.loads(rx)
        receipt = read(raw['receipt'])
        require(request==frozen['request']==read(raw['request'])
                and reply==read(raw['response']) and request['id']==reply['id']==receipt['id']
                and receipt['RX_sha256']==OLD['H']['digest'](rx)
                and receipt['TX_bytes']==len(tx) and receipt['RX_bytes']==len(rx)
                and receipt['error'] is None and row['image_blocks']==0,
                'actual_original_arguments_or_received_stdio_wire_error')
        producer = Path(row['producer_path'])
        _,text,packet = public(reply)
        capture_path = Path(row['capture_path'])
        capture = read(capture_path)
        require(packet==read(producer) and text.encode()==raw['public'].read_bytes()
                and row['public_UTF8_bytes']==len(text.encode())
                and capture_path==reconcile(host[i]['capture']) and capture==frozen['capture']
                and host[i]['command']=='capture_task' and host[i]['params']=={'selectors':request['params']['arguments']['query']['objects']}
                and solver[i]['scene_revision']==capture['revision'],'real_service_producer_or_ordered_derived_capture_changed')
        work = solver[i]['task_work']
        spanned = read(producer.with_name('RECEIPT.json'))
        require(work['surface_pair_count']==(1 if phase=='cold' else 0) and work['result_cache_hit'] is (phase=='hot')
                and spanned['original_returned_object'] and spanned['started_ns']<=host[i]['started_ns']
                    <=host[i]['closed_ns']<=spanned['returned_ns'],
                    'expected_one_host_per_request_and_cold_only_original_solver')
        outcomes[phase] = {'reply':reply,'capture':capture,'work':work,'RX':pin(raw['RX']),
                           'producer':pin(producer),'capture_source':pin(capture_path),'stdio_ns':receipt['elapsed_ns'],
                           'service_ns':spanned['elapsed_ns'],'host_ns':host[i]['closed_ns']-host[i]['started_ns']}
    return identity,outcomes


def verify_matrix(baseline,candidate,*,standard_baseline=None,standard_candidate=None):
    arms = {'baseline_evidence':Path(baseline),'candidate_evidence':Path(candidate)}
    require((standard_baseline is None)==(standard_candidate is None),'both_standard_comparison_arms_are_required_together')
    if standard_baseline is not None:
        arms.update(baseline_standard=Path(standard_baseline),candidate_standard=Path(standard_candidate))
    labels = F['CASES']
    for root in arms.values():
        matrix = read(root/'INDEX.json')
        require(matrix['passed'] and tuple(matrix['planned'])==tuple(labels) and not matrix['unrun'],'actual_registered_7_cases_arm_required')
    totals = {}
    for label in labels:
        all_runs = {key:read_case(root,label,opted_in=key.endswith('_evidence')) for key,root in arms.items()}
        inst_old,base = all_runs['baseline_evidence']
        inst_new,candidate_arm = all_runs['candidate_evidence']
        require(inst_old['source_sha256']==D['BASE_SHA']!=inst_new['source_sha256'],'baseline_and_candidate_install_identity_changed')
        per_case = {}
        for phase in PHASES:
            old,new = base[phase],candidate_arm[phase]
            details = D['verify_delivery'](label,old['reply'],new['reply'],capture=new['capture'],identity=inst_new)
            if phase=='cold':
                values = [row['work']['surface_work'] for row in (old,new)]
                require(all(values[0][name]==values[1][name] for name in SEARCH),
                        'rounded_scope_changed_original_distance_search_work')
                expected = labels[label][0]!='success'
                require(values[1].get('exact_witness_triangle_checks',0)==(2 if expected else 0),
                        'bounded_two_current_winning_face_checks_or_old_strict_path_changed')
                if label=='tree_n02_n03':
                    require(values[1]['tree_builds']>0 and values[1]['node_pair_visits']==99,'true_BVH_holdout_not_exercised')
            standard = None
            options = all_runs
            if 'candidate_standard' in options:
                before,after = (options[arm][1][phase] for arm in ('baseline_standard','candidate_standard'))
                standard = D['verify_delivery'](label,before['reply'],after['reply'],capture=after['capture'],
                                                identity=options['candidate_standard'][0],evidence=False)
                require(options['baseline_standard'][0]['source_sha256']==inst_old['source_sha256']
                        and options['candidate_standard'][0]['source_sha256']==inst_new['source_sha256'],
                        'actual_standard_endpoints_did_not_use_same_frozen_installations')
            per_case[phase] = {'candidate_evidence':details,'candidate_standard':standard,
                'actual':{name:{k:v for k,v in result[1][phase].items() if k not in ('reply','capture')}
                          for name,result in all_runs.items()}}
        totals[label] = per_case
    inverse = {}
    for forward,reverse in (('linear_m01_m03','linear_m03_m01'),('linear_m16_m20','linear_m20_m16')):
        bodies = [public(read(arms['candidate_evidence']/'cases'/label/'cold/RESPONSE.json'))[2]
                  for label in (forward,reverse)]
        left,right = (body['facts']['surface_proximity']['value'] for body in bodies)
        direction = [body['nearest_witness']['direction_a_to_b'] for body in (left,right)]
        require(left['distance_m']==right['distance_m']
                and all(a==-b for a,b in zip(*direction,strict=True)),'reverse_real_point_witness_direction_not_opposite')
        inverse[reverse] = {'distance_m':left['distance_m'],'A_to_B_forward_and_reverse':direction}
    return {'passed':True,'arms':{key:pin(root/'INDEX.json') for key,root in arms.items()},
            'case_count':len(totals),'cases':totals,'exact_CLI_candidate_evidence_stage_count':len(totals)*12,
            'compatible_inverted_pairs':inverse,'actual_new_Blender':0,'actual_new_models':0,'actual_new_rasters':0}


if __name__=='__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    for flag in ('baseline','candidate','output'):
        cli.add_argument('--'+flag,type=Path,required=True)
    cli.add_argument('--standard-baseline',type=Path)
    cli.add_argument('--standard-candidate',type=Path)
    args = cli.parse_args()
    result = verify_matrix(args.baseline,args.candidate,standard_baseline=args.standard_baseline,
                           standard_candidate=args.standard_candidate)
    with args.output.open('x',encoding='utf8',newline='\n') as output:
        output.write(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2)+'\n')

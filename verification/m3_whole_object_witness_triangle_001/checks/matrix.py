"""Grade the sealed actual cold/hot replay arms from transport and source receipts."""

import argparse
import json
from pathlib import Path
from runpy import run_path


NS = Path(__file__).resolve().parents[1]
D = run_path(str(NS/'checks/delivery.py'))
require,read,pin = (D[key] for key in ('require','read','pin'))
PHASES = ('cold','hot')
SEARCH = ('validated_faces','referenced_vertices','triangle_pairs','leaf_pair_visits',
          'node_pair_visits','narrow_phase_pairs','tree_builds')


def reconcile(saved):
    proof = pin(Path(saved['path']))
    require((proof['sha256'],proof['bytes'])==(saved['sha256'],saved['bytes']),
            'actual_replay_artifact_no_longer_matches_recorded_bytes')
    return Path(saved['path'])


def lines(path):
    return [json.loads(raw) for raw in path.read_bytes().splitlines() if raw]


def read_case(arm, label, *, evidence):
    folder = arm/'cases'/label
    execution = read(folder/'CASE.json')
    require(execution['label']==label and execution['passed'] and execution['production_evidence_option'] is evidence
            and set(execution['observations'])==set(PHASES) and execution['actual_Blender_starts']==execution['actual_models']
            ==execution['actual_rasters']==0,'missing_actual_completed_registered_arm_cell')
    retained = D['historical'](label)
    registered = read(reconcile(execution['binding']))
    handshake = read(folder/'INITIALIZE.json')['result']['_meta']['human_eye']
    require(handshake['source_sha256']==registered['source_sha256']
            and handshake['source_kind']=='installed_distribution','actual_replay_not_same_installed_candidate')
    held = read(reconcile(execution['held_EOF']))
    close,eof = held['process_close'],held['worker_EOF']
    require(held['stdout_eof_observed'] and close['confirmed'] and close['exit_code']==0 and close['process_handle_closed']
            and eof['input_eof_observed'] and eof['closed'] and eof['old_inputs_unchanged']
            and eof['source_sha256']==registered['source_sha256'] and eof['host_requests']==eof['observe_calls']==2
            and eof['network_attempts']==eof['old_write_attempts']==eof['PNG_open_attempts']==eof['raster_attempt_events']
            ==eof['geometry_algorithm_substitutions']==eof['producer_result_substitutions']==0,
            'actual_replay_host_lifecycle_or_zero_work_guard_failed')
    host = lines(folder/'worker/HOST_CALLS.jsonl')
    events = [entry for entry in lines(folder/'worker/PRODUCT_EVENTS.jsonl') if 'task_work' in entry]
    require(len(host)==len(events)==len(PHASES),'actual_registered_host_or_solver_call_count_changed')
    outcomes = {}
    for i,phase in enumerate(PHASES):
        observation = execution['observations'][phase]
        original = {k:reconcile(observation[k]) for k in ('request','response','public','TX','RX','receipt')}
        tx,rx = (original[name].read_bytes() for name in ('TX','RX'))
        request,reply = (json.loads(blob) for blob in (tx,rx))
        receipt = read(original['receipt'])
        require(request==retained['request']==read(original['request'])
                and reply==read(original['response']) and request['id']==reply['id']==receipt['id']
                and receipt['RX_sha256']==D['H']['digest'](rx) and receipt['TX_bytes']==len(tx)
                and receipt['RX_bytes']==len(rx) and receipt['error'] is None,
                'actual_original_ordered_request_or_returned_stdio_receipt_changed')
        _,text,public = D['E']['public'](reply)
        producer_path,capture_path = (Path(observation[k]) for k in ('producer_path','capture_path'))
        require(public==read(producer_path) and len(text.encode())==observation['public_UTF8_bytes']
                and text.encode()==original['public'].read_bytes()
                and observation['image_blocks']==0,'actual_returned_producer_or_public_no_image_bytes_changed')
        captured = host[i]
        work = events[i]['task_work']
        require(captured['index']==i+1 and captured['command']=='capture_task'
                and captured['params']=={'selectors':request['params']['arguments']['query']['objects']}
                and capture_path==reconcile(captured['capture']) and events[i]['scene_revision']==public['binding']['scene_revision']
                and work['surface_pair_count']==(1 if phase=='cold' else 0)
                and work['result_cache_hit'] is (phase=='hot'),'actual_work_must_be_one_ordinary_host_capture_per_phase')
        worker = read(producer_path.with_name('RECEIPT.json'))
        require(worker['original_returned_object'] and worker['started_ns']<=captured['started_ns']
                <=captured['closed_ns']<=worker['returned_ns'],'actual_capture_or_producer_not_in_its_request_clock')
        outcomes[phase] = {'reply':reply,'capture':read(capture_path),'source':pin(capture_path),'RX':pin(original['RX']),
            'rt_ns':receipt['elapsed_ns'],'service_ns':worker['elapsed_ns'],'host_ns':captured['closed_ns']-captured['started_ns'],
            'work':work}
    return registered,outcomes


def verify_matrix(baseline,standard,evidence):
    roots = [Path(arm).resolve(strict=True) for arm in (baseline,standard,evidence)]
    slots = {}
    labels = D['H']['LABELS']
    for arm in roots:
        index = read(arm/'INDEX.json')
        require(index['passed'] and tuple(index['planned'])==labels and not index['unrun'],
                'registered_completed_three_case_replay_arm_required')
    for label in labels:
        bindings,outcomes = zip(*(read_case(arm,label,evidence=i==2) for i,arm in enumerate(roots)),strict=True)
        require(bindings[0]['source_sha256']==D['BASE_SHA']
                and bindings[1]['source_sha256']==bindings[2]['source_sha256']!=D['BASE_SHA'],
                'actual_baseline_standard_and_opt_in_install_identities_differ')
        pair = {}
        for phase in PHASES:
            old,ordinary,new = [arm[phase] for arm in outcomes]
            std = D['verify_delivery'](label,old['reply'],ordinary['reply'],capture=ordinary['capture'],
                                      identity=bindings[1],require_source=False)
            isolated = D['verify_delivery'](label,old['reply'],new['reply'],capture=new['capture'],
                                           identity=bindings[2],require_source=True)
            require(old['capture']==ordinary['capture']==new['capture'],
                    'actual_three_arms_did_not_use_the_same_owned_historical_capture')
            if phase=='cold':
                searches = [tuple(result['work']['surface_work'][name] for name in SEARCH) for result in (old,ordinary,new)]
                require(searches[0]==searches[1]==searches[2],'original_pair_search_work_counts_changed')
            pair[phase] = {'candidate_standard':std,'candidate_evidence':isolated,
                'actual':{name:{key:row[key] for key in ('source','RX','work','rt_ns','service_ns','host_ns')}
                    for name,row in zip(('baseline_standard','candidate_standard','candidate_evidence'),(old,ordinary,new),strict=True)}}
        slots[label] = pair
    return {'passed':True,'registered_actual_arms':dict(zip(('baseline_standard','candidate_standard','candidate_evidence'),
                 [pin(arm/'INDEX.json') for arm in roots],strict=True)),'cases':slots,'images':0,
            'original_comparable_quality_cells':18,'candidate_exact_CLI_stage_count':36,
            'actual_Blender_starts':0,'actual_models':0}


if __name__=='__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    for flag in ('baseline','standard','evidence','output'):
        cli.add_argument('--'+flag,type=Path,required=True)
    args = cli.parse_args()
    verified = verify_matrix(args.baseline,args.standard,args.evidence)
    with args.output.open('x',encoding='utf8',newline='\n') as out:
        out.write(json.dumps(verified,ensure_ascii=False,allow_nan=False,indent=2)+'\n')

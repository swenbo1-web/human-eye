"""Summarize saved entry evidence only; no product, host, solver or model calls."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import statistics

HERE=Path(__file__).resolve().parent
sha=lambda raw:hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


def without_local(facts):
    result=copy.deepcopy(facts)
    for row in result:row['closed'].pop('local_evidence',None)
    return result


def series(values):
    return {'samples':values,'median':statistics.median(values),'minimum':min(values),'maximum':max(values)}


def summarize(folder):
    raw=(folder/'RESULTS.json').read_bytes();run=json.loads(raw)
    assert run['passed'] is True and len(run['cases'])==4
    cases={(row['role'],row['profile']):row for row in run['cases']}
    assert set(cases)=={(role,profile) for role in ('baseline','candidate') for profile in ('C','S')}
    result={'source_result_sha256':sha(raw),'profiles':{},'core_facts_unchanged':True,
        'per_request_call_counts_unchanged':True,'model_consumers':0,'new_sessions':0,
        'scope':'saved evidence only; product stdio and owner intervals overlap and are not added; one first request/five repeats is not an OS-cold or model benefit experiment'}
    for profile in ('C','S'):
        baseline,candidate=(cases[(role,profile)] for role in ('baseline','candidate'))
        assert len(baseline['requests'])==len(candidate['requests'])==6
        paired=[]
        for old,new in zip(baseline['requests'],candidate['requests'],strict=True):
            facts_equal=encoded(without_local(old['facts']))==encoded(without_local(new['facts']))
            work_equal=encoded(old['task_work'])==encoded(new['task_work'])
            rpc_equal=old['worker_received_request_count']==new['worker_received_request_count']
            assert old['request_params_sha256']==new['request_params_sha256']
            result['core_facts_unchanged'] &= facts_equal
            result['per_request_call_counts_unchanged'] &= work_equal and rpc_equal
            paired.append({'request_index':old['request_index'],'core_facts_equal':facts_equal,
                'task_work_equal':work_equal,'worker_received_count_equal':rpc_equal,
                'baseline_worker_received':old['worker_received_request_count'],
                'candidate_worker_received':new['worker_received_request_count']})
        detail={'pair_checks':paired,'versions':{}}
        for role,case in (('baseline',baseline),('candidate',candidate)):
            rows=case['requests'];first,repeated=rows[0],rows[1:]
            local=rows[0]['facts'][0]['closed'].get('local_evidence')
            detail['versions'][role]={'source_sha256':case['source_sha256'],
                'first_product_stdio_elapsed_ns':first['product_stdio_receipt']['elapsed_ns'],
                'first_owner_elapsed_ns':first['owner_attempt']['elapsed_ns'],
                'repeated_product_stdio_elapsed_ns':series([row['product_stdio_receipt']['elapsed_ns'] for row in repeated]),
                'repeated_owner_elapsed_ns':series([row['owner_attempt']['elapsed_ns'] for row in repeated]),
                'product_stdio_RX_bytes':[row['product_stdio_RX_bytes'] for row in rows],
                'product_stdio_TX_bytes':[row['product_stdio_TX_bytes'] for row in rows],
                'worker_received_requests':[row['worker_received_request_count'] for row in rows],
                'result_cache_hit_recorded':[row['task_work'].get('result_cache_hit') for row in rows],
                'task_work_original':[row['task_work'] for row in rows],
                'N13_local_evidence_present':[('local_evidence' in row['facts'][0]['closed']) for row in rows],
                'local_evidence_object_compact_UTF8_bytes':len(encoded(local).encode('utf8')) if local is not None else 0,
                'local_evidence_cold_repeated_equal':all(encoded(row['facts'][0]['closed'].get('local_evidence'))==encoded(local) for row in rows),
                'all_close_confirmed':case['finish']['confirmed'],
                'actor_actual_exit':case['actor_runtime_exit'],
                'thin_actual_exit':case['thin_probe_lifecycle']['runtime_exit'],
                'geometry_and_source_unchanged':case['finish']['close']['geometry_unchanged'] and case['finish']['close']['asset_unchanged'],
                'recorded_image_construction_events':case['recorded_image_construction_events']}
        detail['RX_byte_deltas']=[new['product_stdio_RX_bytes']-old['product_stdio_RX_bytes']
            for old,new in zip(baseline['requests'],candidate['requests'],strict=True)]
        result['profiles'][profile]=detail
    result['protected_inputs_unchanged']=run['protected_inputs_unchanged']
    result['reused_runners_unchanged']=run['reused_runners_unchanged']
    result['owned_scene_attempts']=run['owned_scene_attempts'];result['metadata_only_attempts']=run['metadata_only_attempts']
    result['passed']=result['core_facts_unchanged'] and result['per_request_call_counts_unchanged']
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True,help='Existing entry run directory')
    parser.add_argument('--output',required=True,help='New summary JSON path')
    args=parser.parse_args();result=summarize(Path(args.run))
    with Path(args.output).open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({'passed':result['passed'],'core_facts_unchanged':result['core_facts_unchanged'],
        'per_request_call_counts_unchanged':result['per_request_call_counts_unchanged'],'output':args.output}))
    raise SystemExit(0 if result['passed'] else 1)

"""Serial correctness-only execution; no performance clocks or timing samples."""
from pathlib import Path
import argparse
import json
import subprocess
import sys
import traceback

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import PYTHON,RAW,dump,need,pin,read,verify


def semantics(facts):
    return {name:{k:v for k,v in value.items() if k not in ('certificate','local_evidence','support_evidence')}
            for name,value in facts.items()}


def compare(rows):
    by={arm:{r['case_id']:r for r in value['cases']} for arm,value in rows.items()}
    comparisons=[]
    for name in by['A']:
        direct={arm:by[arm][name]['direct'] for arm in ('A','B','C')}
        surface={a:{k:v for k,v in direct[a]['value'].items() if k!='work'} for a in ('A','B','C')}
        need(surface['A']==surface['B']==surface['C'],'direct_complete_geometry_value')
        need(direct['A']['native_pair']==direct['B']['native_pair']==direct['C']['native_pair'],'direct_canonical_pair')
        ctree=direct['C']['tree_evidence'];eligible=any(t['eligible_independent'] for t in ctree)
        if not eligible:need(direct['B']['work']==direct['C']['work'],'inactive_original_R3_work_exact')
        routes=[]
        for i in range(len(by['A'][name]['routes'])):
            values={arm:by[arm][name]['routes'][i] for arm in ('A','B','C')}
            labels=[c['label'] for c in values['A']['calls']]
            for arm in ('B','C'):need(labels==[c['label'] for c in values[arm]['calls']],'same_shared_call_sequence')
            for j,label in enumerate(labels):
                calls={arm:values[arm]['calls'][j] for arm in ('A','B','C')}
                need(semantics(calls['A']['facts'])==semantics(calls['B']['facts'])==semantics(calls['C']['facts']),
                     'compound_fact_semantics_'+name+'_'+label)
                need(calls['B']['facts']==calls['C']['facts'],'C_full_shared_fact_matches_original_R3')
            routes.append({'requested_facts':values['A']['requested_facts'],
                'first_fact_statuses':{arm:{k:{f:v.get(f) for f in ('status','value','reason') if f in v} for k,v in values[arm]['calls'][0]['facts'].items()} for arm in ('A','B','C')},
                'repeat_hits':{arm:{k:v for k,v in values[arm]['calls'][1]['diagnostics'].items() if k.endswith('_cache_hit') or k.endswith('_pair_count')} for arm in ('A','B','C')},
                'all_original_state_differences_preserved':True,'new_C_unknown_or_answer_regression':False})
        comparisons.append({'case_id':name,'surface_and_canonical_equal':True,'candidate_integer_guard_eligible':eligible,
            'candidate_actual_FIFO':direct['C']['enqueue_observation'],'inactive_B_C_work_equal':not eligible,
            'direct_work':{arm:direct[arm]['work'] for arm in ('A','B','C')},'shared_routes':routes})
    return comparisons


def main(plan_path,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False);plan=read(plan_path)
    result={'schema':'m6-043-untimed-shared-holdout-result-v1','status':'failed','plan':pin(plan_path),
        'arms':{},'process_attempts':[],'formal_timing_samples':0,'Blender':0,'models':0}
    try:
        for ref in plan['sources'].values():verify(ref)
        for arm in ('A','B','C'):
            command=[str(PYTHON),'-I','-B',str(HERE/'worker.py'),'--plan',str(Path(plan_path).resolve()),'--arm',arm,'--output',str(output/arm)]
            child=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=180)
            (output/(arm+'.stdout')).write_bytes(child.stdout);(output/(arm+'.stderr')).write_bytes(child.stderr)
            attempt={'arm':arm,'command':command,'returncode':child.returncode,'stdout':pin(output/(arm+'.stdout')),'stderr':pin(output/(arm+'.stderr'))}
            result['process_attempts'].append(attempt)
            if (output/arm/'RESULT.json').exists():result['arms'][arm]=read(output/arm/'RESULT.json')
            print(json.dumps({'arm':arm,'returncode':child.returncode}),flush=True)
        need(all(result['arms'].get(a,{}).get('status')=='pass' for a in ('A','B','C')),'one_or_more_control_arm_failed')
        result.update(status='pass',comparisons=compare(result['arms']))
    except BaseException:result['error']=traceback.format_exc()
    dump(output/'RESULT.json',result);print(json.dumps({'status':result['status'],'result':pin(output/'RESULT.json')}),flush=True)
    return 0 if result['status']=='pass' else 1


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',default=str(RAW/'PLAN.json'));p.add_argument('--output',required=True);a=p.parse_args()
    raise SystemExit(main(a.plan,a.output))

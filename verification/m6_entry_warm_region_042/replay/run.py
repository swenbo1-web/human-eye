"""Serial fixed-input replay controller; execute only in the released timing window."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from replay_common import PYTHON, RAW, dump, need, pin, read, verify


def summarize(cells):
    by = {(c['group'],c['arm']): c for c in cells}
    groups = sorted({c['group'] for c in cells})
    results = {}
    for phase in ('plain','substages'):
        for label in ('first','repeat'):
            paired = []
            for group in groups:
                left = next(r for r in by[group,'032']['rows'] if r['phase']==phase and r['read']==label)
                right = next(r for r in by[group,'r3']['rows'] if r['phase']==phase and r['read']==label)
                need(left['public'] == right['public'], 'cross_install_complete_public_congruence')
                terms = sorted(set(left['timing_ns']) & set(right['timing_ns']))
                paired.append({'group':group,'032_ns':left['timing_ns'],'r3_ns':right['timing_ns'],
                    'delta_ns':{k:right['timing_ns'][k]-left['timing_ns'][k] for k in terms},
                    'relative':right['timing_ns']['replay_pipeline_ns']/left['timing_ns']['replay_pipeline_ns']-1})
            results[phase+'_'+label] = {'pairs':paired,
                'median_delta_ns':{k:statistics.median(p['delta_ns'][k] for p in paired) for k in paired[0]['delta_ns']},
                'median_relative_pipeline':statistics.median(p['relative'] for p in paired),
                'median_032_ns':{k:statistics.median(p['032_ns'][k] for p in paired) for k in paired[0]['032_ns']},
                'median_r3_ns':{k:statistics.median(p['r3_ns'][k] for p in paired) for k in paired[0]['r3_ns']}}
    observer = {}
    for arm in ('032','r3'):
        values = []
        for group in groups:
            c = by[group,arm]
            plain = next(r for r in c['rows'] if r['phase']=='plain' and r['read']=='repeat')
            seen = next(r for r in c['rows'] if r['phase']=='substages' and r['read']=='repeat')
            values.append({'group':group,'pipeline_delta_ns':seen['timing_ns']['replay_pipeline_ns']-plain['timing_ns']['replay_pipeline_ns'],
                'measurement_delta_ns':seen['timing_ns']['task_measurement']-plain['timing_ns']['task_measurement']})
        observer[arm] = {'pairs':values,'median_pipeline_delta_ns':statistics.median(v['pipeline_delta_ns'] for v in values),
            'median_measurement_delta_ns':statistics.median(v['measurement_delta_ns'] for v in values),
            'scope':'descriptive order-balanced same-process observer contrast, not a bound on all scheduling noise'}
    return {'paired':results,'observer_contrast':observer}


def run(plan_path, output, preflight=False):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    plan=read(plan_path)
    result={'schema':'m6-042-stage-replay-result-v1','status':'failed','plan':pin(plan_path),
            'preflight':preflight,'cells':[],'attempts':[],'started_ns':time.perf_counter_ns(),
            'scope':plan['scope'],'not_measured':plan['not_measured']}
    try:
        for ref in plan['sources'].values():verify(ref)
        for group, order in enumerate(plan['orders'][:1] if preflight else plan['orders'],1):
            for arm in order:
                folder=output/(f'{group:02d}_'+arm);folder.mkdir()
                cmd=[str(PYTHON),'-I','-B',str(HERE/'worker.py'),'--plan',str(Path(plan_path).resolve()),
                     '--arm',arm,'--group',str(group),'--output',str(folder)]
                t0=time.perf_counter_ns()
                child=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90,check=False)
                t1=time.perf_counter_ns()
                (folder/'STDOUT.bin').write_bytes(child.stdout)
                (folder/'STDERR.bin').write_bytes(child.stderr)
                execution={'command':cmd,'started_ns':t0,'closed_ns':t1,'wall_ns':t1-t0,'returncode':child.returncode}
                dump(folder/'EXECUTION.json',execution)
                result['attempts'].append({'arm':arm,'group':group,'execution':pin(folder/'EXECUTION.json')})
                need((folder/'RESULT.json').is_file(),'worker_missing_result')
                cell=read(folder/'RESULT.json');result['cells'].append(cell)
                need(child.returncode==0 and cell['status']=='pass','worker_failure:'+str(folder))
                print(json.dumps({'group':group,'arm':arm,'status':'pass','wall_ns':t1-t0}),flush=True)
        result.update(status='pass',summary=summarize(result['cells']),
                      actual_solver_calls=sum(len(c['rows']) for c in result['cells']),actual_native_calls=0)
    except BaseException:
        result['error']=traceback.format_exc()
    result['closed_ns']=time.perf_counter_ns();result['controller_wall_ns']=result['closed_ns']-result['started_ns']
    dump(output/'RESULT.json',result)
    print(json.dumps({'status':result['status'],'result':pin(output/'RESULT.json')}),flush=True)
    return 0 if result['status']=='pass' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--plan',default=str(RAW/'PLAN.json'))
    parser.add_argument('--output',required=True)
    parser.add_argument('--preflight',action='store_true')
    args=parser.parse_args()
    raise SystemExit(run(args.plan,args.output,args.preflight))

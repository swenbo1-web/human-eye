"""Read-only recomputation of fixed-input replay receipts; optionally save new report."""
from __future__ import annotations
import argparse
from fractions import Fraction
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from replay_common import RAW, dump, need, pin, read, verify


def analyze(result_path):
    result=read(result_path);plan=read(result['plan']['path'])
    need(result['status']=='pass' and len(result['cells'])==14,'seven_complete_replay_pairs')
    verify(result['plan'])
    for ref in plan['sources'].values():verify(ref)
    for key in ('capture','capture_receipt','source','truth','asset','historical_public_receipt'):
        verify(plan[key])
    by={(c['group'],c['arm']):c for c in result['cells']}
    need(len(by)==14,'unique_arm_group_cells')
    exact={}
    for phase in ('plain','substages'):
        for label in ('first','repeat'):
            pairs=[]
            for group in range(1,8):
                rows={arm:next(r for r in by[group,arm]['rows'] if r['phase']==phase and r['read']==label) for arm in ('032','r3')}
                need(rows['032']['public']==rows['r3']['public'],'complete_public_congruence')
                a,b=(rows[arm]['timing_ns']['replay_pipeline_ns'] for arm in ('032','r3'))
                pairs.append({'group':group,'032_ns':a,'r3_ns':b,'delta_ns':b-a,
                              'relative_exact':str(Fraction(b-a,a))})
            exact[phase+'_'+label]={'pairs':pairs,'median_delta_ns':statistics.median(p['delta_ns'] for p in pairs),
                'median_relative_exact':str(statistics.median(Fraction(p['relative_exact']) for p in pairs))}
    work={}
    for arm in ('032','r3'):
        rows=[r for c in result['cells'] if c['arm']==arm for r in c['rows']]
        first=rows[0]['work']['task_query']
        need(all(r['work']['task_query']==first for r in rows),'per_arm_deterministic_actual_work')
        work[arm]=first
    gui=RAW.parent/'live/main/H3'
    before,after=(read(gui/(k+'.json')) for k in ('BEFORE','AFTER'))
    old=read('D:/HumanEye/runs/M6-041-KERNEL-HOOK/s1/warm_diagnostic/Yanyite/BEFORE.json')
    geomkeys=('local_sha256','world_sha256','triangles_sha256','matrix','vertices','triangles')
    for name in (plan['query']['region']['object']['name'],'Cube'):
        need(all(before['geometry'][name][k]==after['geometry'][name][k]==old['geometry'][name][k] for k in geomkeys),
             'h3_unchanged_historical_geometry_digest')
    preflight=read(RAW/'preflight_01/RESULT.json')
    execution=[read(a['execution']['path']) for a in result['attempts']]
    return {'schema':'m6-042-replay-audit-v1','status':'pass','result':pin(result_path),'plan':result['plan'],
        'input_qualification':plan['qualification'],'complete_public_congruence_all56':True,
        'current_H3_geometry_matches_041_before_and_after':True,'exact_paired_pipeline':exact,
        'stages':result['summary']['paired'],'observer_contrast':result['summary']['observer_contrast'],
        'deterministic_work':work,
        'cost':{'formal_replay_solver_calls':result['actual_solver_calls'],'formal_replay_native_calls':0,
                'formal_replay_controller_wall_ns':result['controller_wall_ns'],
                'formal_replay_child_process_wall_sum_ns':sum(e['wall_ns'] for e in execution),
                'separate_preflight_solver_calls':preflight['actual_solver_calls'],
                'separate_preflight_controller_wall_ns':preflight['controller_wall_ns'],
                'capture_native_calls':read(plan['capture_receipt']['path'])['native_calls'],
                'capture_wall_ns_diagnostic':read(plan['capture_receipt']['path'])['capture_wall_ns_diagnostic_only'],
                'paid_model_calls':0,'separate_process_CPU_time':'not_measured'},
        'first_failure':{'kind':'input_qualification_test_representation_error','solver_calls':0,
            'preserved_stdout':pin(RAW/'FREEZE_01.stdout'),'preserved_stderr':pin(RAW/'FREEZE_01.stderr'),
            'execution':pin(RAW/'FREEZE_EXECUTION_01.json'),
            'source_manifest':pin(RAW/'freeze_attempt_01_source/MANIFEST.json'),
            'recovery':'compare frame/subframe/scale; retain native view-layer instance separately; bind current layer name to H3 QA; never backfill RNA ID'},
        'qualification_limits':[
            'Same frozen input and fresh product processes; repeated calls are not independent GUI hosts.',
            'Replay host_read is frozen JSON decode; native acquisition, queue, TCP and real stdio write are absent.',
            'Captured historical host_capture stages/work are provenance only and are not current execution cost.',
            'Top-level imports are outside request clocks; original lazy initialization inside a first request remains included.',
            'Observed solver/membership intervals are nested children of task_measurement, not additive outer costs.',
            'Observer contrast is descriptive and includes ordinary scheduling noise; no absolute overhead bound is inferred.',
            'Live dual degradation gate was false; fixed-input solver difference grants no optimization eligibility.'],
        'analysis_source':pin(__file__)}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--result',default=str(RAW/'paired_01/RESULT.json'))
    parser.add_argument('--output',default=str(RAW/'AUDIT.json'))
    args=parser.parse_args()
    report=analyze(args.result);dump(args.output,report)
    print(pin(args.output))

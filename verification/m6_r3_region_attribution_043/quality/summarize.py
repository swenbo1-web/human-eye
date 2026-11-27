"""Combine preserved 043 correctness phases without executing a tested kernel."""
from pathlib import Path
import hashlib
import json
import struct

HERE=Path(__file__).resolve().parent
RAW=Path('D:/HumanEye/runs/M6-043-R3-REGION-ATTRIBUTION/quality')

def pin(path):
    p=Path(path).resolve(strict=True);b=p.read_bytes()
    return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())

def read(path):return json.loads(Path(path).read_bytes())

def bound(ref):
    assert pin(ref['path'])==ref
    return read(ref['path'])

def binary(value):
    if type(value) is float:return ('float64',struct.pack('<d',value).hex())
    if isinstance(value,dict):return {k:binary(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [binary(v) for v in value]
    return value

def main():
    main_path=RAW/'attempt_003/RESULTS.json';extra_path=RAW/'extra_003/RESULTS.json'
    phase=read(main_path);extra=read(extra_path);assert extra['status']=='pass'
    assert phase['status']=='fail' and phase['completed_rows']==23
    assert len(phase['errors'])==1 and 'extra_controls' in phase['errors'][0]['traceback']
    rows=[bound(ref) for ref in phase['rows']];assert all(row['status']=='pass' for row in rows)
    controls=bound(extra['controls']);assert controls['status']=='pass'
    eligible=[];inactive=[]
    for row in rows:
        contained=row.get('case',{}).get('root_strict_containment',row.get('root_strict_containment'))
        if 'binding' in row:contained=bound(row['binding'])['root_strict_containment']
        name=row.get('case',{}).get('id',row.get('case',{}).get('kind','other_family'))
        if contained is True:eligible.append(name)
        elif contained is False:
            assert binary(row['arms']['B']['work'])==binary(row['arms']['C']['work'])
            inactive.append(name)
    assert len(eligible)==8 and len(inactive)==15
    assert binary(controls['shift']['B'])==binary(controls['shift']['C'])
    assert binary(controls['limits']['B']['fresh_forged_diagnostics']['result'])==binary(
        controls['limits']['C']['fresh_forged_diagnostics']['result'])
    for arm in ('A','B','C'):
        assert controls['deadlines'][arm]['code']=='live_request_expired'
        assert controls['deadlines'][arm]['deadline_renewed'] is False
    costs=[]
    for p in sorted(RAW.glob('*/PREPARED.json'))+sorted(RAW.glob('*/RESULTS.json')):
        d=read(p)
        costs.append({'receipt':pin(p),'status':d['status'],'recorded_wall_ns':d.get('cost_wall_ns',0),
            'recorded_cpu_ns':d.get('cost_cpu_ns',0)})
    report={'schema':'m6-043-independent-correctness-quality-v1','status':'pass',
        'summary_source':pin(__file__),'current_reproduction_source':pin(HERE/'correctness.py'),
        'passed_case_receipts':phase['rows'],'remaining_controls':pin(extra_path),
        'preserved_partial_phase':pin(main_path),'phase_interpretation':'23 case rows passed; only extra validator failed; corrected extra phase passed separately',
        'case_counts':{'independent_fraction_synthetic':14,'independent_fraction_archived_family':1,
            'historical_analytical_budget':8,'root_containment_eligible_synthetic':8,'inactive_exact_B_C_work_equality':15},
        'all_sources_verified':{'A':143,'B':143,'C':143},
        'untouched_code_proof':'all original module functions/classes except _nearest_tree source-identical between B and C',
        'no_new_candidate_unknown':True,
        'explicit_original_status_difference':{'case':'historical_pair129_credit_reset',
            'A':{'known':False,'reason':'surface_pair_budget','narrow_phase_pairs':16384},
            'B_and_C':{'known':True,'narrow_phase_pairs':8,'work_units':129104}},
        'real_other_family':{'name':'original unrotated assembly','pair':['Obj_014','Obj_003'],
            'triangles':[128,28],'canonical':[16,24],'candidate_eligible':False,
            'work_units':{a:rows[14]['arms'][a]['work']['work_units'] for a in ('A','B','C')},
            'limitation':'different-family guard activation remains untested; fixed inactive holdout was not replaced'},
        'budget_scope':{'work_cap':1179648,'narrow_cap':16384,'combined_faces_cap':4096,
            'actual_hard_cap_rejections':True,'query_local_credit_end_invariants':True,
            'forged_previous_diagnostics_cannot_fund_query':True,'cooperative_abort_not_swallowed':True,
            'original_service_deadline_expired_all_arms':True,'internal_priority_shift':2,
            'internal_shift_B_C_result_and_work_equal':True,
            'limitation':'historical031 prepaid39..43 no longer straddles current installation work cap; unprepaid zero489 A=1174466, B=C=608801. No extra end-to-end boundary sweeps run.'},
        'retained_infrastructure_failures':[
            {'receipt':pin(RAW/'attempt_001/RESULTS.json'),'reason':'validator omitted original exact_witness_triangles native membership fallback'},
            {'receipt':pin(RAW/'attempt_002/RESULTS.json'),'reason':'validator omitted existing R3 earned_node_prune ledger term'},
            {'receipt':pin(main_path),'reason':'validator incorrectly required existing pair129 original A to succeed'},
            {'receipt':pin(RAW/'extra_001/RESULTS.json'),'reason':'installed top-level modules absent from temporary alias import path'},
            {'receipt':pin(RAW/'extra_002/RESULTS.json'),'reason':'light QA Python lacked Pillow; final extra used original production dependency Python'}],
        'cost_receipts':costs,'recorded_phase_wall_ns_total':sum(x['recorded_wall_ns'] for x in costs),
        'recorded_phase_cpu_ns_total':sum(x['recorded_cpu_ns'] for x in costs),
        'cost_scope':'all preserved preparation/retry/check phases; not performance comparisons; startup and some binding/file I/O outside individual phase counters',
        'Blender':0,'MCP':0,'models':0,'timing_benchmark_calls':0,
        'optional_further_QA':'held by parent request before formal timing'}
    path=RAW/'RESULTS.json'
    with path.open('x',encoding='utf8',newline='\n') as out:json.dump(report,out,indent=2);out.write('\n')
    print(json.dumps({'result':pin(path),'status':'pass','recorded_wall_s':report['recorded_phase_wall_ns_total']/1e9,
        'recorded_cpu_s':report['recorded_phase_cpu_ns_total']/1e9}))

if __name__=='__main__':main()

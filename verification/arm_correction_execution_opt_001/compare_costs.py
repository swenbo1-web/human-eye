"""Summarize the single recorded pair; never execute or resample a product."""
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent


def read(path):return json.loads(path.read_text(encoding='utf8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def ms(value):return value/1e6


def summarize(label):
    run=HERE/(label+'_01');value=read(run/'RESULT.json')
    costs=value['costs'];source_costs=value['source_costs'];cases=value['cases']
    rows=[]
    for index,case in enumerate(cases,1):
        raw=read(run/f'case_{index:02}.json')
        event=next(json.loads(line) for line in (run/'OBSERVER_EVENTS.jsonl').read_text().splitlines()
                   if json.loads(line)['index']==index)
        rows.append({'case_id':case['case_id'],'status':case['result']['status'],
            'entry_ms':ms(case['entry_ns']),
            'host_ms':{k:ms(v) for k,v in case['result']['timings_ns'].items()},
            'entry_phase_ms':{k:ms(v) for k,v in case['result']['entry_timings_ns'].items()},
            'qa_before_ms':ms(raw['qa_before_read_ns']),
            'qa_after_ms':ms(raw['qa_after_read_ns']),
            'qa_archive_ms':ms(event['evidence_write_ns']),
            'prepare_ms':sum(ms(c['elapsed_ns']) for c in raw['qa_source_costs'] if c['phase']=='prepare_patch'),
            'source_static_parse_ms':sum(ms(c['elapsed_ns']) for c in raw['qa_source_costs'] if c['phase']=='_parse_patch')})
    phase_ms={name:sum(ms(c['elapsed_ns']) for c in costs if c['phase']==name) for name in value['cost_counts']}
    source_ms={name:sum(ms(c['elapsed_ns']) for c in source_costs if c['phase']==name)
               for name in value['source_cost_counts']}
    return {'result_sha256':sha(run/'RESULT.json'),'source_sha256':value['source_before']['source_sha256'],
        'passed':value['passed'],'product_work':value['product_work'],'source_work':value['source_work_totals'],
        'state_phase_counts':value['cost_counts'],'state_phase_total_ms':phase_ms,
        'source_phase_counts':value['source_cost_counts'],'source_phase_total_ms':source_ms,
        'startup_ms':ms(value['startup_ns']),'close_ms':ms(value['close_ns']),
        'total_controller_ms':ms(value['total_controller_ns']),
        'entry_total_ms':sum(row['entry_ms'] for row in rows),
        'hot_positive_entry_median_ms':median(row['entry_ms'] for row in rows[1:4]),
        'cases':rows,'process_exit':value['process_exit']}


def main():
    before=summarize('baseline');after=summarize('candidate');equal=[]
    assert before['passed'] and after['passed']
    assert before['product_work']==after['product_work']
    assert {k:v for k,v in before['source_work'].items() if k!='preparations'} == {
        k:v for k,v in after['source_work'].items() if k!='preparations'}
    for index in range(1,9):
        a=read(HERE/'baseline_01'/f'case_{index:02}.json')
        b=read(HERE/'candidate_01'/f'case_{index:02}.json')
        row={'case_id':a['case_id'],
            'full_native_before_equal':a['native_before']==b['native_before'],
            'full_native_after_equal':a['native_after']==b['native_after'],
            'consumed_patch_equal':a['product_audit']['input_patch']==b['product_audit']['input_patch'],
            'resolved_task_equal':a['product_audit']['resolved_task']==b['product_audit']['resolved_task'],
            'status_and_reason_equal':(a['receipt']['status'],a['receipt']['reason'])==(
                b['receipt']['status'],b['receipt']['reason'])}
        assert all(v for k,v in row.items() if k!='case_id'),row
        equal.append(row)
    prepare=before['source_phase_total_ms']['prepare_patch']
    nested_parse=before['source_phase_total_ms']['_parse_patch']
    result={'schema':'arm-correction-single-pair-costs-v1','passed':True,
        'ordered_runs':['baseline_01','candidate_01'],'resamples':0,
        'baseline':before,'candidate':after,'exact_geometry_comparison':equal,
        'baseline_prepare_inclusive_ms':prepare,
        'baseline_parse_nested_inside_prepare_ms':nested_parse,
        'baseline_prepare_excluding_parse_ms':prepare-nested_parse,
        'candidate_retained_source_parse_ms':after['source_phase_total_ms']['_parse_patch'],
        'limitations':['one ordered pair, no distribution or causal end-to-end performance claim',
            'source and state phases are nested inside entry; do not sum them',
            'RPC and entry include independent QA reads, archive IO and text logging',
            'baseline prepare includes the parser retained by candidate; only its exclusive work was removed',
            'different runtime paths and fixed order can influence filesystem/cache scheduling costs'],
        'new_product_calls':0,'new_Blender_runs':0,'model_calls':0,'script_sha256':sha(Path(__file__))}
    (HERE/'COST_COMPARISON.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'passed':True,'prepare_excluding_parse_ms':prepare-nested_parse,
        'hot_positive_entry_median_ms':[before['hot_positive_entry_median_ms'],after['hot_positive_entry_median_ms']]}))


if __name__=='__main__':main()

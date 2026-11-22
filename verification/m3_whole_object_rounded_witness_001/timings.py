"""Collect raw inclusive request spans for each frozen cold and hot replay."""
import json
from pathlib import Path
from statistics import median

RUN=Path('D:/he_m3_whole_object_rounded_witness_001')
ARMS=('baseline_standard','baseline_evidence','candidate_standard','candidate_evidence')
STAGES=('host.capture','observation.task_facts','surface_proximity.rounded_source_membership',
        'surface_proximity.exact_source_membership','task_query.exact_source_encode',
        'mcp.content_encode','mcp.wire_encode','mcp.stdio_write')


def read(path):
    return json.loads(path.read_bytes())


def clocks():
    rows={}
    for arm in ARMS:
        index=read(RUN/arm/'INDEX.json')
        if not index['passed'] or len(index['planned'])!=7 or index['unrun']:
            raise ValueError('frozen actual arm incomplete',arm)
        rows[arm]={}
        for label in index['planned']:
            root=RUN/arm/'cases'/label
            case=read(root/'CASE.json')
            events=[json.loads(line) for line in (root/'worker/PRODUCT_EVENTS.jsonl').read_bytes().splitlines()]
            traces=[row['trace'] for row in events if row.get('event')=='request_trace'
                    and row['trace']['operation']=='mcp.observe']
            if len(traces)!=2:
                raise ValueError('expected original cold/hot request traces',arm,label,len(traces))
            phases={}
            for phase,trace in zip(('cold','hot'),traces,strict=True):
                receipt=read(Path(case['observations'][phase]['receipt']['path']))
                if trace['annotations']['mcp_request_id']!=receipt['id']:
                    raise ValueError('trace and held request differ',arm,label,phase)
                spans={stage:[row['duration_ns'] for row in trace['spans'] if row['name']==stage] for stage in STAGES}
                if any(len(span)>1 for span in spans.values()):
                    raise ValueError('trace phase produced ambiguous stage',arm,label)
                if phase=='hot' and any(spans[stage] for stage in STAGES[2:5]):
                    raise ValueError('hot replay repeated witness work',arm,label)
                phases[phase]={'stdio_RTT_ns':receipt['elapsed_ns'],'request_trace_ns':trace['duration_ns'],
                               'inclusive_stage_ns':{stage:span[0] for stage,span in spans.items() if span}}
            rows[arm][label]=phases
    evidence=rows['candidate_evidence']
    added=STAGES[2:5]
    exact=[label for label,pair in evidence.items() if pair['cold']['inclusive_stage_ns'].get(added[1]) is not None]
    if len(exact)!=5 or any(any(stage not in evidence[label]['cold']['inclusive_stage_ns'] for stage in added) for label in exact):
        raise ValueError('actual exact replay added stage or known denominator missing')
    medians={arm:{phase:median(pair[phase]['stdio_RTT_ns'] for pair in labels.values())
                  for phase in ('cold','hot')} for arm,labels in rows.items()}
    added_medians={stage:median(evidence[label]['cold']['inclusive_stage_ns'][stage] for label in exact)
                   for stage in added}
    result={'passed':True,'registered_processes':28,'actual_calls':56,'raw':rows,'stdio_RTT_median_ns':medians,
            'exact_cases':exact,'exact_case_cold_median_added_stages_ns':added_medians,
            'semantics':'inclusive wall-clock stages, with archival host replay and evidence recording; do not sum nested spans'}
    with (RUN/'CLOCKS.json').open('x',encoding='utf8',newline='\n') as stream:
        stream.write(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'median_ns':medians,'added_stage_ns':added_medians}))


if __name__=='__main__':
    clocks()

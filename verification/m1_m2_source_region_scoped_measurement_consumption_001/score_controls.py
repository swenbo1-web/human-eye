"""Exercise the formal scorer with true replay calls and labeled derived transcripts."""

from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SCORER = HERE/'score.py'
S = run_path(str(SCORER))
ROOT = S['ROOT']/'preflight'
TRUTH = ROOT/'TRUTH.json'
REPLAY = {'A1':ROOT/'replay_verified', 'B1':ROOT/'replay_ready_verified'}
PROBE = ROOT/'closed_score_v2'
load, write, pin, need = (S[key] for key in ('load','write','pin','need'))


def compact(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)


def write_lines(path, values):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        for value in values:
            stream.write(compact(value)+'\n')


def calls_from_actual_owner(slot):
    rows=[]
    for directory in sorted((slot/'owner').glob('tool_*')):
        call, response=(load(directory/name) for name in ('REQUEST.json','RESPONSE.json'))
        result=response['result']
        rows.append({'id':str(call['id']), 'type':'mcp_tool_call','server':'arm_engine',
                     'tool':call['params']['name'],'arguments':call['params']['arguments'],
                     'result':{'content':result['content'],'structured_content':None} if not result['isError'] else None,
                     'error':result['content'] if result['isError'] else None,
                     'status':'failed' if result['isError'] else 'completed'})
    need(len(rows)==5 and sum(x['tool']=='human_eye_scene_observe' for x in rows)==3
         and sum(bool(x['error']) for x in rows)==1,'true_replay_owner_denominator_changed')
    return rows


def create_claims(slot,truth,case):
    lines=['离线派生评分用转录，本次无模型。']
    claims={}
    for region,spec in truth['regions'].items():
        region_label={'high':'高区','low':'低区'}[region]
        value=spec['triangle_count']
        line=f'{region_label}选中面数 {value}'
        lines.append(line)
        claims[f'{region}.count']={'quote':line,'value':value}
        literal=str(spec['distance_m'])
        line=f'{region_label}距离 {literal} m'
        lines.append(line)
        claims[f'{region}.distance']={'quote':line,'literal':literal,'unit':'m'}
        line=f'{region_label}方向 (0, 0, 1)'
        lines.append(line)
        claims[f'{region}.direction']={'quote':line,'value':[0,0,1]}
        a,b=deepcopy(spec['source_point_world_m']),deepcopy(spec['reference_point_world_m'])
        if case=='off_surface' and region=='high':
            b[0] += .01
        line=f'{region_label}源点 {compact(a)}，参照点 {compact(b)}'
        lines.append(line)
        claims[f'{region}.points']={'quote':line,'a':a,'b':b}
        source_id=spec['source_witness_triangle_ids'][0]
        if case=='cross_region_source' and region=='high':
            source_id=truth['regions']['low']['source_witness_triangle_ids'][0]
        line=f'{region_label}目标源三角 {source_id}'
        lines.append(line)
        claims[f'{region}.source_triangle']={'quote':line,'value':source_id}
        source_id=1 if case=='wrong_reference_source' and region=='low' else spec['cube_witness_triangle_ids'][0]
        line=f'{region_label}参照源三角 {source_id}'
        lines.append(line)
        claims[f'{region}.reference_triangle']={'quote':line,'value':source_id}
        met=spec['threshold_met']
        line=f"{region_label}{'达到' if met else '未达到'} 0.300 m"
        lines.append(line)
        claims[f'{region}.threshold']={'quote':line,'value':met}
    line='高区更近'
    lines.append(line)
    if case!='missing_nearer':
        claims['nearer']={'quote':line,'value':'high'}
    if case=='wrong_quote':
        claims['low.direction']['quote']='低区方向 (0, 1, 0)'
    return '\n'.join(lines)+'\n', claims


def create_transcript(slot,truth,item_rows,root,case):
    root.mkdir(parents=True,exist_ok=False)
    text, claims=create_claims(slot,truth,case)
    final=root/'PUBLIC_FINAL.txt'
    final.write_bytes(text.encode())
    raw,timed=(root/key for key in ('stdout.raw.bin','events.jsonl'))
    rows=deepcopy(item_rows)
    if case=='absent_actual_exposure':
        row=next(item for item in rows if item['tool']=='human_eye_scene_observe')
        row['result']['content'][0]['text'] += '\n'
    items=[{'type':'item.completed','item':item} for item in rows]
    events=items+[{'type':'item.completed','item':{'id':'offline-final','type':'agent_message','text':text}},
                  {'type':'turn.completed','usage':{}}]
    write_lines(timed,[{'perf_ns':index,'event':item} for index,item in enumerate(events,1)])
    if case=='stdout_final_changed':
        events[-2]=deepcopy(events[-2])
        events[-2]['item']['text']+='额外文字\n'
    write_lines(raw,events)
    # Deliberately unparsable non-public evidence is outside the whitelist.
    # The true original appears only in the closed raw stream on a live slot.
    with raw.open('ab') as stream:
        stream.write(b'{"type":"item.completed","item":{"id":"filter-probe","type":"reasoning","ignored":bad}}\n')
    with timed.open('ab') as stream:
        stream.write(b'{"perf_ns":20,"event":{"type":"item.completed","item":{"id":"filter-probe","type":"reasoning","ignored":bad}}}\n')
    closed_slot=pin(slot/'SLOT_RESULT.json')
    if case=='wrong_closed_binding':
        closed_slot['sha256']='0'*64
    write(root/'TRANSCRIPT_BINDING.json',{'scope':'derived_no_model_scoring_transcript','slot':slot.name,
          'closed_slot':closed_slot,'answer':pin(final),'raw':pin(raw),'timed':pin(timed)})
    claim_file=root/'CLAIMS.json'
    write(claim_file,{'slot':slot.name,'answer_sha256':pin(final)['sha256'],'claims':claims})
    return claim_file


def run_case(slot,truth,row,case):
    context=PROBE/slot.name/case
    claims=create_transcript(slot,truth,row,context,case)
    verdict=context/'VERDICT.json'
    call=subprocess.run([sys.executable,'-IB','-X','utf8',str(SCORER),'--slot',str(slot),'--truth',str(TRUTH),
                         '--claims',str(claims),'--output',str(verdict),'--offline','--offline-transcript',str(context)],
                        timeout=50,capture_output=True)
    (context/'STDOUT.bin').write_bytes(call.stdout)
    (context/'STDERR.bin').write_bytes(call.stderr)
    need(verdict.is_file(), 'actual_same_scorer_did_not_publish/'+slot.name+'/'+case)
    result=load(verdict)
    literal_negative={'off_surface':'high.points','cross_region_source':'high.source_triangle',
                      'wrong_reference_source':'low.reference_triangle','missing_nearer':'nearer',
                      'wrong_quote':'low.direction'}
    passes=case in ('healthy','absent_actual_exposure')
    need(call.returncode==(0 if passes else 1) and result['quality_complete'] is passes,
         'same_scorer_control_has_wrong_quality_verdict/'+slot.name+'/'+case+':'+str(result.get('error')))
    if case in literal_negative:
        key=literal_negative[case]
        need(result['passed_items']==14 and result['claims'][key]['status']=='failure',
             'scoring_control_not_rejected_for_expected_item/'+case)
    if case=='stdout_final_changed':
        need(result['error']=='raw_and_timed_public_events_differ','alternate_public_final_not_rejected')
    if case=='wrong_closed_binding':
        need(result['error']=='derived_offline_transcript_not_bound_to_closed_fixture','cross_slot_transcript_not_rejected')
    if case=='absent_actual_exposure':
        high=result['adoption']['per_region']['high']
        need(high['first_matching_attempt']==2 and high['first_successful_public_measurement_attempt'] is None
             and high['first_packet_range_and_witness_match_literal_final'] is False,
             'altered_CLI_text_counted_as_actual_evidence')
    if case=='healthy':
        per=result['adoption']['per_region']
        need(result['passed_items']==15 and all(
            per[key]['first_successful_public_measurement_attempt']==attempt
            and per[key]['first_successful_public_measurement_mode']==(
                'source_region' if slot.name=='A1' else 'source_region_measurement')
            and per[key]['first_packet_range_and_witness_match_literal_final']
            for key,attempt in (('high',2),('low',4))),
            'healthy_packet_failed_same_scorer_adoption_check')
        need(len(result['adoption']['calls'])==5 and len(result['unmatched_public_tool_ids'])==0,
             'closed_replay_literal_proof_not_bound_to_all_tool_calls')
    return {'case':case,'slot':slot.name,'returncode':call.returncode,'verdict':pin(verdict),
            'passed_items':result['passed_items'],'quality_complete':passes}


def main():
    need(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_scorer')
    truth=load(TRUTH)
    cases=[]
    for label,cases_for_arm in (
            ('A1',('healthy','off_surface','wrong_reference_source','stdout_final_changed','wrong_quote')),
            ('B1',('healthy','cross_region_source','missing_nearer','wrong_closed_binding','absent_actual_exposure'))):
        slot=REPLAY[label]/label/'slots'/label
        rows=calls_from_actual_owner(slot)
        for case in cases_for_arm:
            cases.append(run_case(slot,truth,rows,case))
    paths={Path(__file__).resolve(),SCORER,TRUTH,Path(truth['terminal_path']),
           *[path for path in PROBE.rglob('*') if path.is_file()]}
    for label in ('A1','B1'):
        slot=REPLAY[label]/label/'slots'/label
        paths.update((slot/'SLOT_RESULT.json',slot/'SLOT_PUBLICATION.json',slot.parents[1]/'REPLAY_CLOSE.json',
                      slot/'owner/CLOSE.json',slot/'mcp/HELD_CLOSE.json'))
    write(ROOT/'SCORE_CONTROLS.json',{'passed':True,'cases':cases,'source_pins':list(map(pin,sorted(paths))),
                                     'scope':'formal scorer CLI, actual closed transport, clearly derived no-model finals',
                                     'new_Blender':0,'new_models':0,'new_rasters':0})
    print(len(cases),'same-scorer cases passed',flush=True)


if __name__=='__main__':
    main()

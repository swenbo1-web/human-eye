"""R1: necessary public timestamps, numeric counters and immutable byte checks."""
from collections import Counter
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]
OLD = OUT.parent/'run_01'
FIELDS = ('input_tokens','cached_input_tokens','output_tokens','reasoning_output_tokens','total_tokens')
IMPLEMENTATION = '01a1b4e2-2a3b-7f61-9607-1b6d9e6e80ee'
R1 = '01a1b51d-4e9e-7071-b517-2bf934d647a5'
PIN = 'fb5a4485c935512c1521b160c55e6034a30ae8177e2662b6a132fec5d85a4509'


def read(path): return json.loads(path.read_text('utf-8-sig'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def dt(value): return datetime.fromisoformat(value.replace('Z','+00:00'))
def sec(a,b): return round((dt(b)-dt(a)).total_seconds(),6)
def save(name,value): (OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf8')


def scan(path, target_turns, spawn_names=()):
    current, previous, previous_anchor = None, None, None
    records={turn:dict(turn_id=turn,token_events=0,duplicate_events=0,verified_sum=Counter(),
        first_counter_anchor=None,last_counter_anchor=None,task_start=None,public_final=None,task_complete=None,
        reported_duration_ms=None) for turn in target_turns}
    spawns={}
    with Path(path).open(encoding='utf8') as stream:
        for number,line in enumerate(stream,1):
            try: item=json.loads(line)
            except ValueError: break
            kind,payload,stamp=item.get('type'),item.get('payload',{}),item.get('timestamp')
            if kind=='turn_context': current=payload.get('turn_id',current)
            if kind=='event_msg' and payload.get('type')=='task_started':
                current=payload.get('turn_id',current)
                if current in records: records[current]['task_start']=dict(utc=stamp,line=number)
            if kind=='response_item' and payload.get('type')=='function_call' and current==IMPLEMENTATION:
                if str(payload.get('name','')).endswith('spawn_agent'):
                    arguments=payload.get('arguments')
                    if isinstance(arguments,str): arguments=json.loads(arguments)
                    name=arguments.get('task_name') if isinstance(arguments,dict) else None
                    if name in spawn_names:
                        assert name not in spawns
                        # Deliberately do not export/read message or protected body fields.
                        spawns[name]=dict(utc=stamp,line=number,call_id=payload.get('call_id'),task_name=name,
                            fork_turns=arguments.get('fork_turns'),model_override=arguments.get('model'),
                            effort_override=arguments.get('reasoning_effort'))
            if kind=='response_item' and current in records and payload.get('type')=='message':
                if payload.get('role')=='assistant' and payload.get('phase') in ('final','final_answer'):
                    assert records[current]['public_final'] is None
                    records[current]['public_final']=dict(utc=stamp,line=number)
            if kind!='event_msg': continue
            event=payload.get('type')
            if event=='task_complete':
                turn=payload.get('turn_id',current)
                if turn in records:
                    records[turn].update(task_complete=dict(utc=stamp,line=number),reported_duration_ms=payload.get('duration_ms'))
            if event!='token_count': continue
            info=payload.get('info') or {}
            raw,last=info.get('total_token_usage'),info.get('last_token_usage')
            if not isinstance(raw,dict) or not all(type(raw.get(k)) is int for k in FIELDS): continue
            cumulative={k:raw[k] for k in FIELDS}
            anchor=dict(utc=stamp,line=number,cumulative=cumulative)
            if current in records:
                assert isinstance(last,dict) and all(type(last.get(k)) is int for k in FIELDS)
                increment={k:cumulative[k]-(previous[k] if previous else 0) for k in FIELDS}
                assert all(value>=0 for value in increment.values())
                duplicate=all(value==0 for value in increment.values())
                assert duplicate or increment=={k:last[k] for k in FIELDS}, (str(path),number,'counter interval')
                assert cumulative['total_tokens']==cumulative['input_tokens']+cumulative['output_tokens']
                assert cumulative['cached_input_tokens']<=cumulative['input_tokens']
                assert cumulative['reasoning_output_tokens']<=cumulative['output_tokens']
                record=records[current]
                if record['first_counter_anchor'] is None:
                    record['first_counter_anchor']=dict(previous=previous_anchor,current=anchor,last_usage={k:last[k] for k in FIELDS})
                record['last_counter_anchor']=anchor
                record['token_events']+=1
                record['duplicate_events']+=int(duplicate)
                record['verified_sum'].update(increment)
            previous,previous_anchor=cumulative,anchor
    for record in records.values():
        record['verified_sum']=dict(record['verified_sum'])
        record['interval_complete']=record['task_complete'] is not None
        record['counter_validation']='Every monotone consecutive delta equals reported last usage, or is an exact duplicate; subsets not added.'
        record['source_rollout']=str(path)
    return records,spawns


bindings=read(OLD/'dispatch/BINDINGS.json')['bindings']
old_usage=read(OLD/'audit/MODEL_USAGE.json')
root_old=next(row['usage'] for row in old_usage['preparation_and_audit_usage'] if row['agent_path']=='/root')
root_records,spawns=scan(root_old['source_rollout'],[IMPLEMENTATION,R1],['consume_%02d'%i for i in range(1,9)])
assert len(spawns)==8 and root_records[IMPLEMENTATION]['reported_duration_ms']==2886540
assert root_records[IMPLEMENTATION]['interval_complete']
timing,consumers=[],[]
for binding,old_model in zip(bindings,old_usage['consumers']):
    assert binding['answer_id']==old_model['binding']['answer_id']
    prior=old_model['model_usage'];turn=prior['turns'][0]['turn_id']
    records,_=scan(prior['source_rollout'],[turn]);record=records[turn]
    assert record['interval_complete'] and record['verified_sum']==prior['verified_token_deltas']
    spawn=spawns[binding['agent_path'].split('/')[-1]]
    assert spawn['fork_turns']=='none' and spawn['model_override'] is spawn['effort_override'] is None
    registration=binding['dispatch_utc'];start=record['task_start']['utc'];final=record['public_final']['utc']
    complete=record['task_complete']['utc'];close=binding['notification_received_utc']
    timing.append(dict(answer_id=binding['answer_id'],chain_id=binding['chain_id'],registration_utc=registration,
        actual_spawn_utc=spawn['utc'],task_start_utc=start,public_final_utc=final,task_complete_utc=complete,
        parent_close_record_utc=close,registration_deadline_utc=binding['answer_deadline_utc'],
        registration_to_actual_spawn_s=sec(registration,spawn['utc']),actual_spawn_to_task_start_s=sec(spawn['utc'],start),
        registration_to_public_final_s=sec(registration,final),actual_spawn_to_public_final_s=sec(spawn['utc'],final),
        host_reported_duration_ms=record['reported_duration_ms'],parent_close_after_task_complete_s=sec(complete,close),
        registration_150s_pass=sec(registration,final)<=150,actual_spawn_150s_diagnostic_pass=sec(spawn['utc'],final)<150,
        anchors=dict(parent_spawn=spawn,child_task_start=record['task_start'],child_final=record['public_final'],
            child_complete=record['task_complete'],child_rollout=prior['source_rollout'])))
    consumers.append(dict(answer_id=binding['answer_id'],usage=record))
assert sum(row['registration_150s_pass'] for row in timing)==6
assert all(row['actual_spawn_150s_diagnostic_pass'] for row in timing)
save('TIMING.json',dict(extracted_utc=datetime.now(timezone.utc).isoformat(),rows=timing,
    interpretation='Registration is parent pre-registration, not actual spawn/provider queue; frozen6/8 gate and actual-spawn8/8 diagnostic stay separate.',
    parent_rollout=root_old['source_rollout'],fields_exported='timestamps, IDs, numeric counters only; no protected prompt or hidden reasoning bodies'))
with (OUT/'TIMING.csv').open('w',encoding='utf8',newline='') as stream:
    names=[key for key in timing[0] if key!='anchors'];writer=csv.DictWriter(stream,fieldnames=names)
    writer.writeheader();writer.writerows({key:row[key] for key in names} for row in timing)
preparation=[]
for entry in old_usage['preparation_and_audit_usage']:
    if entry['agent_path']=='/root': continue
    prior=entry['usage'];assert len(prior['turns'])==1
    record=scan(prior['source_rollout'],[prior['turns'][0]['turn_id']])[0][prior['turns'][0]['turn_id']]
    assert record['interval_complete'] and record['verified_sum']==prior['verified_token_deltas']
    preparation.append(dict(agent_path=entry['agent_path'],usage=record))
total=Counter()
for entry in consumers+preparation: total.update(entry['usage']['verified_sum'])
total.update(root_records[IMPLEMENTATION]['verified_sum'])
save('FINAL_USAGE.json',dict(extracted_utc=datetime.now(timezone.utc).isoformat(),consumers=consumers,
    preparation_and_audit_agents=preparation,original_implementation_final=root_records[IMPLEMENTATION],
    original_implementation_host_duration_ms=2886540,closed_implementation_batch_observed_token_totals=dict(total),
    previous_partial_total_tokens=37470752,previous_partial_implementation_tokens=root_old['verified_token_deltas'],
    completed_implementation_additional_tokens=root_records[IMPLEMENTATION]['verified_sum']['total_tokens']-root_old['verified_token_deltas']['total_tokens'],
    current_R1_partial=root_records[R1],coordinator_review=dict(tokens=None,complete=False,scope='separate unmeasured cost, not included in this closed implementation batch'),
    all_project_cost_complete=False,provider_request_count=None,fees=None,
    scope='Consumers + three preparatory agents + now-ended original implementer only. CurrentR1 and coordinator review are separate, not a full-project final total.',
    subset_accounting='cached_input_tokens and reasoning_output_tokens are subsets, never added again.'))

index=read(OLD/'EVIDENCE_INDEX.json')
assert sha(OLD/'EVIDENCE_INDEX.json')=='3ee06f33f4a892b28d009d065dd3ee83cc0e0d88cbffacf7e6a15e2f5b0a6b3e'
assert len(index['files'])==619
for row in index['files']:
    path=OLD/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],row['path']
identity=read(OLD/'SOURCE_CHECK.json')['identity'];assert len(identity['source_files'])==131
installed=Path(read(OLD/'SOURCE_CHECK.json')['purelib'])
for base in (REPO,installed):
    names={row['path'] for row in identity['source_files'] if '/' not in row['path']}
    for package in ('human_eye_plugin','human_eye_module1_operators'):
        names.update(package+'/'+path.name for path in (base/package).glob('*.py'))
    assert names=={row['path'] for row in identity['source_files']}
    rows=[dict(path=row['path'],sha256=sha(base/row['path'])) for row in identity['source_files']]
    assert rows==identity['source_files']
    payload=dict(base_version=identity['base_version'],implementation_revision=identity['implementation_revision'],files=rows)
    assert hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()==PIN
save('UNCHANGED.json',dict(checked_utc=datetime.now(timezone.utc).isoformat(),old_index_sha256=sha(OLD/'EVIDENCE_INDEX.json'),
    old_index_members_verified=619,product_source_count=131,product_source_sha256=PIN,
    checkout_and_installed_bytes_match=True,original_late_markers_preserved=True,new_consumers=0,new_agents=0,
    product_runs=0,Blender_runs=0,paid_API_calls=0,write_scope='only review_r1'))
print(json.dumps(dict(timing_rows=8,registration_gate='6/8',actual_spawn_diagnostic='8/8',
    implementation_final_tokens=root_records[IMPLEMENTATION]['verified_sum'],closed_implementation_batch_tokens=dict(total),
    old_evidence_unchanged=619,product_unchanged=131)))
if (OUT/'ERRATUM.md').is_file():
    save('EVIDENCE_INDEX.json',dict(sealed_utc=datetime.now(timezone.utc).isoformat(),
        scope='only new offline R1 files; no old evidence mutation or raw rollout bodies',
        files=[dict(path=path.name,bytes=path.stat().st_size,sha256=sha(path))
               for path in sorted(OUT.iterdir()) if path.is_file() and path.name!='EVIDENCE_INDEX.json']))

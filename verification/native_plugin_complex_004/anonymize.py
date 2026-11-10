"""Create unedited task-labelled blind answers only after all 18 final slots.

No consumer, product, Blender, scoring or truth/rubric import occurs here.
Method wording in original answers is deliberately retained.  Output is
exclusive: an existing blind directory or private map is never overwritten.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import tempfile
import uuid

HERE=Path(__file__).resolve().parent
TASK='NATIVE-PLUGIN-COMPLEX-004'


def decode(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate_json_key:'+key)
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique,
        parse_constant=lambda value:(_ for _ in ()).throw(ValueError('nonfinite_json:'+value)))


def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(path):return decode(Path(path).read_bytes())
def json_bytes(value):return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf8')


def fixed_inputs(root):
    plan_path=root/'PLAN.json';plan_blob=plan_path.read_bytes();plan=decode(plan_blob)
    run_path=root/'RUN_RESULT.json';run_blob=run_path.read_bytes();run=decode(run_blob)
    if plan.get('cycle_id')!=TASK or run.get('cycle_id')!=TASK or plan.get('denominator')!=18 or run.get('denominator')!=18:
        raise ValueError('fixed_task_and_18_slot_denominator_required')
    if type(run.get('ended_ns')) is not int or run['ended_ns']<=0:raise ValueError('terminal_RUN_RESULT_required')
    sequence=plan.get('sequence');records=run.get('cells')
    if not isinstance(sequence,list) or not isinstance(records,list) or len(sequence)!=18 or len(records)!=18:
        raise ValueError('all_18_plan_and_run_slots_required')
    if len({slot.get('cell') for slot in sequence})!=18 or len({slot.get('cell') for slot in records})!=18:
        raise ValueError('duplicate_cell_in_fixed_denominator')
    expected={(task,round_,group):1 for task in ('assembly','discovery') for round_ in (1,2,3) for group in ('N','O','C')}
    if Counter((s.get('task'),s.get('round'),s.get('group')) for s in sequence)!=Counter(expected):
        raise ValueError('fixed_two_tasks_three_rounds_three_groups_required')
    for slot,record in zip(sequence,records):
        if any(record.get(key)!=slot.get(key) for key in ('cell','task','round','group')):
            raise ValueError('RUN_RESULT_slot_identity_or_order_mismatch')
        if record.get('status') not in ('completed','failed','not_run'):raise ValueError('terminal_slot_status_required')
    freeze=load(root/'FREEZE.json');pin=freeze.get('files_sha256',{}).get(str(plan_path.resolve()))
    if pin!=sha(plan_blob):raise ValueError('PLAN_not_bound_to_execution_FREEZE')
    return plan,run,sha(plan_blob),sha(run_blob)


def task_inputs(plan,plan_sha):
    rules=Path(plan['session_rules']).read_bytes()
    if sha(rules)!=plan['session_rules_sha256']:raise ValueError('session_rules_changed')
    tasks=[]
    for task_id,spec in plan['tasks'].items():
        prompt=Path(spec['prompt']).read_bytes()
        if sha(prompt)!=spec['prompt_sha256']:raise ValueError('task_prompt_changed:'+task_id)
        raw=rules+b'\n'+prompt
        if sha(raw)!=spec['model_input_sha256'] or len(raw)!=spec['model_input_bytes']:
            raise ValueError('actual_model_input_binding_mismatch:'+task_id)
        text=raw.decode('utf8')
        if text.encode('utf8')!=raw:raise ValueError('model_input_not_roundtrip_UTF8:'+task_id)
        tasks.append({'task_id':task_id,'text':text,'model_input_sha256':sha(raw)})
    if {t['task_id'] for t in tasks}!={'assembly','discovery'}:raise ValueError('exact_two_task_inputs_required')
    return {'plan_sha256':plan_sha,'tasks':tasks}


def original_answer(root,slot,record):
    cell=slot['cell']
    if not isinstance(cell,str) or len(cell)!=2 or not cell.isascii() or not cell.isdecimal():raise ValueError('fixed_cell_directory_name_required')
    folder=root/'cells'/cell;consumer_path=folder/'CONSUMER.json';public_path=folder/'PUBLIC_FINAL.txt'
    consumer_blob=consumer_path.read_bytes() if consumer_path.is_file() else None
    consumer=decode(consumer_blob) if consumer_blob is not None else None
    public_blob=public_path.read_bytes() if public_path.is_file() else None
    if consumer is None:
        if record['status']=='completed' or public_blob is not None:raise ValueError('public_or_completed_answer_missing_CONSUMER:'+cell)
        text=None;delivered=False;final_blob=None;binding='no_consumer_or_public_final'
    else:
        if any(consumer.get(key)!=slot[key] for key in ('cell','task','round','group')):
            raise ValueError('CONSUMER_slot_binding_mismatch:'+cell)
        if type(consumer.get('valid_completion')) is not bool:raise ValueError('boolean_valid_completion_required:'+cell)
        text=consumer.get('final');delivered=consumer['valid_completion']
        if text is not None and not isinstance(text,str):raise ValueError('final_text_or_null_required:'+cell)
        final_blob=None if text is None else text.encode('utf8')
        if final_blob!=public_blob:raise ValueError('PUBLIC_FINAL_CONSUMER_exact_UTF8_bytes_mismatch:'+cell)
        if delivered and text is None:raise ValueError('valid_completion_without_public_final:'+cell)
        if 'model_completed' in record and (type(record['model_completed']) is not bool or record['model_completed']!=delivered):
            raise ValueError('RUN_RESULT_CONSUMER_completion_mismatch:'+cell)
        if record['status']=='not_run':raise ValueError('not_run_slot_has_consumer_record:'+cell)
        binding='exact_public_and_consumer_UTF8' if text is not None else 'consumer_without_final'
    return text,delivered,{'consumer_sha256':None if consumer_blob is None else sha(consumer_blob),
        'final_sha256':None if final_blob is None else sha(final_blob),
        'public_final_sha256':None if public_blob is None else sha(public_blob),
        'original_final_bytes':None if final_blob is None else len(final_blob),
        'valid_completion':delivered,'run_status':record['status'],'publication_binding':binding}


def prepare(root):
    """Validate everything before allocating a public/private output artifact."""
    plan,run,plan_sha,run_sha=fixed_inputs(root);tasks=task_inputs(plan,plan_sha)
    answers=[];mapping={}
    for slot,record in zip(plan['sequence'],run['cells']):
        text,delivered,binding=original_answer(root,slot,record)
        answer_id=uuid.uuid4().hex
        while answer_id in mapping:answer_id=uuid.uuid4().hex
        answers.append({'task_id':slot['task'],'answer_id':answer_id,'text':text,'delivered':delivered})
        mapping[answer_id]={'task_id':slot['task'],'task':slot['task'],'round':slot['round'],
            'group':slot['group'],'cell':slot['cell'],**binding}
    original_order=[row['answer_id'] for row in answers]
    rng=random.SystemRandom()
    rng.shuffle(answers)
    while [row['answer_id'] for row in answers]==original_order:rng.shuffle(answers)
    private={'schema':'complex-004-private-blind-map-v1','plan_sha256':plan_sha,'run_result_sha256':run_sha,
        'postprocess_script_sha256':sha(Path(__file__).read_bytes()),'denominator':18,'answers':mapping,
        'delivered_semantics':'CONSUMER.valid_completion; failed-but-published original text is retained with delivered=false',
        'scope':'postprocess only; original method wording retained; no truth/rubric or cost scoring performed'}
    return {'answers':answers},tasks,private


def anonymize(root):
    root=Path(root).resolve();blind=root/'blind';private_dir=root/'private';mapping_path=private_dir/'BLIND_MAP.json'
    if blind.exists() or mapping_path.exists():raise FileExistsError('blind_output_or_private_map_already_exists; never overwrite')
    answers,tasks,mapping=prepare(root)
    # Exclusive allocation and publication: failures leave their partial output
    # for inspection rather than overwriting it on a later invocation.
    blind.mkdir(exist_ok=False);private_dir.mkdir(exist_ok=True)
    with mapping_path.open('xb') as stream:stream.write(json_bytes(mapping))
    with (blind/'ANSWERS.json').open('xb') as stream:stream.write(json_bytes(answers))
    with (blind/'TASKS.json').open('xb') as stream:stream.write(json_bytes(tasks))
    return {'answers':18,'delivered':sum(row['delivered'] for row in answers['answers']),
        'missing_final':sum(row['text'] is None for row in answers['answers']),
        'blind_answers':str(blind/'ANSWERS.json'),'private_map':str(mapping_path),
        'consumer_calls':0,'product_calls':0,'Blender_calls':0,'scoring_calls':0}


def self_test():
    """Only fake records in a TemporaryDirectory, never the actual blind tree."""
    with tempfile.TemporaryDirectory(prefix='complex004-anonymize-fake-') as temporary:
        root=Path(temporary);rules=root/'rules.txt';rules.write_bytes('只读\r\n'.encode('utf8'))
        tasks={}
        for task in ('assembly','discovery'):
            prompt=root/(task+'.txt');prompt.write_bytes(('task '+task+'\n').encode())
            raw=rules.read_bytes()+b'\n'+prompt.read_bytes()
            tasks[task]={'prompt':str(prompt),'prompt_sha256':sha(prompt.read_bytes()),'model_input_sha256':sha(raw),'model_input_bytes':len(raw)}
        slots=[]
        for task in tasks:
            for round_ in (1,2,3):
                for group in ('N','O','C'):slots.append({'cell':str(len(slots)+1).zfill(2),'task':task,'round':round_,'group':group})
        plan={'cycle_id':TASK,'denominator':18,'sequence':slots,'tasks':tasks,'session_rules':str(rules),'session_rules_sha256':sha(rules.read_bytes())}
        (root/'PLAN.json').write_bytes(json_bytes(plan));(root/'FREEZE.json').write_bytes(json_bytes({'files_sha256':{str((root/'PLAN.json').resolve()):sha((root/'PLAN.json').read_bytes())}}))
        records=[]
        for i,slot in enumerate(slots):
            status='completed' if i<12 else 'failed' if i<15 else 'not_run';records.append(dict(slot,status=status))
            if status=='not_run':continue
            folder=root/'cells'/slot['cell'];folder.mkdir(parents=True)
            final='原始\r\nNative/plugin "method" '+slot['cell']+'\n' if i<13 else None
            consumer=dict(slot,final=final,valid_completion=status=='completed')
            (folder/'CONSUMER.json').write_bytes(json_bytes(consumer))
            if final is not None:(folder/'PUBLIC_FINAL.txt').write_bytes(final.encode('utf8'))
        run={'cycle_id':TASK,'denominator':18,'ended_ns':1,'cells':records};run_path=root/'RUN_RESULT.json';run_path.write_bytes(json_bytes(run))
        prepared,tasks_public,mapping=prepare(root)
        assert len(prepared['answers'])==18 and len(mapping['answers'])==18
        assert all(set(row)=={'task_id','answer_id','text','delivered'} for row in prepared['answers'])
        assert sum(row['text'] is None for row in prepared['answers'])==5
        assert sum(row['delivered'] for row in prepared['answers'])==12
        assert [mapping['answers'][r['answer_id']]['cell'] for r in prepared['answers']]!=[s['cell'] for s in slots]
        for row in prepared['answers']:
            private=mapping['answers'][row['answer_id']]
            if row['text'] is not None:assert sha(row['text'].encode('utf8'))==private['final_sha256']==private['public_final_sha256']
        assert tasks_public['tasks'][0]['text'].encode('utf8')==rules.read_bytes()+b'\n'+Path(tasks['assembly']['prompt']).read_bytes()
        def denied(call):
            try:call()
            except (ValueError,FileExistsError):return
            raise AssertionError('invalid_input_or_overwrite_was_not_denied')
        original=run_path.read_bytes();run['cells']=records[:-1];run_path.write_bytes(json_bytes(run));denied(lambda:prepare(root));run_path.write_bytes(original)
        run['cells']=records[:-1]+[records[0]];run_path.write_bytes(json_bytes(run));denied(lambda:prepare(root));run_path.write_bytes(original)
        public=root/'cells/01/PUBLIC_FINAL.txt';raw=public.read_bytes();public.write_bytes(raw+b'changed');denied(lambda:prepare(root));public.write_bytes(raw)
        result=anonymize(root);denied(lambda:anonymize(root))
        assert result['answers']==18 and set(load(root/'blind/ANSWERS.json'))=={'answers'}
        return {'passed':True,'fake_only':True,'checks':['18_slots_and_missing_preserved','no_label_cost_trace_keys',
            'exact_UTF8_and_CRLF_preserved','task_actual_input_bound','randomized_answer_order',
            'partial_and_duplicate_runs_rejected','altered_public_final_rejected','exclusive_no_overwrite'],
            'actual_blind_created':False,'consumer_calls':0,'product_calls':0,'Blender_calls':0,'scoring_calls':0}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=HERE);parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args();print(json.dumps(self_test() if args.self_test else anonymize(args.root),ensure_ascii=False))


if __name__=='__main__':main()

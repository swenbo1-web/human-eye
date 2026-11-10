"""Independent focused synthetic check; no runtime, consumer or product imports."""
import ast
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
from unittest.mock import patch

B=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_local_relation_consumption_001')
OUT=Path(__file__).resolve().parent
PACK=B/'quality_handoff/pack_quality.py'
OLD=B/'revisions/LRC_PREP_001/original_169b0be0/quality_handoff/pack_quality.py'
PRIOR=Path('D:/hefe/verification/fixes/20261111_m4_local_consumption_prep_review/quality/zero_launch_complete/e')
enc=lambda x:(json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
sha=lambda x:hashlib.sha256(x).hexdigest()
checks=[];cases=[];external=[]
def check(label,value):checks.append({'label':label,'passed':bool(value)})
def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s)
    s.loader.exec_module(m);return m

assert sha(PACK.read_bytes())=='3b960695d5308ac64c5512191d7c0dc4e854a72b5fa07b97ccb5dfe0c0b3c365'
new=module('root_fixed_packager',PACK);old=module('root_old_packager',OLD)
def functions(path):
    tree=ast.parse(path.read_text(encoding='utf-8'))
    return {n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
oldf,newf=functions(OLD),functions(PACK)
check('all_existing_payload_helpers_identical',all(oldf[k]==newf[k] for k in oldf if k!='main'))
check('only_one_new_function',set(newf)-set(oldf)=={'validate_zero_launch_failure'})
inputs={name:(PRIOR/name).read_bytes() for name in ('PLAN.json','FREEZE.json','private/ANON_MAP.json','input/INITIAL.png','input/PROMPT.txt','GO.json','STARTED.json','RUN_RESULT.json')}

def controls(variant):
    d={k:json.loads(v) for k,v in inputs.items() if k.endswith('.json')}
    run=d['RUN_RESULT.json'];row=run['records'][0]
    # The earlier compact reproducer omitted accounting fields. Populate the
    # exact field shape emitted by the existing driver, without any process.
    run.update(batch_started_ns=100,batch_ended_ns=500,batch_wall_ns=400,
      started_cells=1,maximum_consumers=9,all_planned_dispatched=False,no_replacements=True)
    d['STARTED.json']['started_ns']=200
    row.update(cell_started_ns=300,cell_ended_ns=400,full_cell_wall_ns=100,within_570s=True)
    if variant!='none':
        c={k:row[k] for k in ('cell','task','round','group')}
        c.update(external_group='N',status='failed',consumer_pid=None,valid_completion=False,
          thread_id=None,final=None,errors=[{'type':'OSError','message':'SYNTHETIC Popen failure; no launch'}])
        if variant=='missing':c.pop('consumer_pid')
        if variant=='positive':c['consumer_pid']=99999
        row['consumer']=c;row['errors']=[]
    return d

def invoke(label,variant='none',mutation=None,expected=None,pack=new):
    folder=OUT/'cases'/label;folder.mkdir(parents=True,exist_ok=False)
    d=controls(variant)
    if mutation:mutation(d)
    for key,value in d.items():
        p=folder/key;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(enc(value))
    for key in ('input/INITIAL.png','input/PROMPT.txt'):
        p=folder/key;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(inputs[key])
    row=d['RUN_RESULT.json']['records'][0];consumer=row.get('consumer')
    if consumer is not None:
        p=folder/'cells'/row['cell']/'CONSUMER.json';p.parent.mkdir(parents=True);p.write_bytes(enc(consumer))
    pack.EVAL=folder;pack.HERE=folder/'q';pack.HERE.mkdir()
    priorargv=sys.argv;exc=None;output=io.StringIO()
    try:
        sys.argv=['synthetic-only','h']
        with contextlib.redirect_stdout(output):pack.main()
    except BaseException as e:exc={'type':type(e).__name__,'message':str(e),'filename':Path(e.filename).name if isinstance(e,FileNotFoundError) else None}
    finally:sys.argv=priorargv
    public=folder/'q/h/public';index=public/'INDEX.json'
    case={'label':label,'variant':variant,'exception':exc,'INDEX_created':index.exists()}
    if expected is not None:
        check(label+'.exact_refusal',exc is not None and exc['type']==expected[0] and (exc['filename'] if expected[0]=='FileNotFoundError' else exc['message'])==expected[1])
        check(label+'.no_public_index',not index.exists())
    else:
        check(label+'.packaged',exc is None and index.exists())
        if index.exists():
            items=json.loads(index.read_bytes())['answers'];states=[r['execution_record_state'] for r in items]
            first='failed_before_consumer' if variant=='none' else 'failed'
            check(label+'.failed_plus_eight_not_run',len(items)==9 and states.count(first)==1 and states.count('not_run')==8)
            check(label+'.no_answer_fabrication',all(r['answer_file'] is None for r in items) and not list(public.rglob('answer.txt')))
            control=folder/'q/h/private/control'
            check(label+'.run_exact',control.joinpath('RUN_RESULT.json').read_bytes()==enc(d['RUN_RESULT.json']))
            if variant!='positive':
                check(label+'.GO_STARTED_exact',all(control.joinpath(k).read_bytes()==enc(d[k]) for k in ('GO.json','STARTED.json')))
            if consumer is not None:
                check(label+'.PID_null_or_missing_preserved',json.loads((folder/'cells'/row['cell']/'CONSUMER.json').read_bytes())==consumer)
    cases.append(case)
    return public

def forbidden(*a,**k):external.append('process_or_socket');raise AssertionError('external operation forbidden')
with patch.object(subprocess,'Popen',forbidden),patch.object(socket,'socket',forbidden):
    for variant in ('none','null','missing'):invoke('accept_'+variant,variant)
    invoke('missing_GO',mutation=lambda d:d.pop('GO.json'),expected=('FileNotFoundError','GO.json'))
    invoke('wrong_GO_hash',mutation=lambda d:d['GO.json'].update(plan_sha256='0'*64),expected=('AssertionError','zero-launch GO binding mismatch'))
    invoke('missing_STARTED',mutation=lambda d:d.pop('STARTED.json'),expected=('FileNotFoundError','STARTED.json'))
    invoke('wrong_STARTED_hash',mutation=lambda d:d['STARTED.json'].update(plan_sha256='0'*64),expected=('AssertionError','zero-launch STARTED binding mismatch'))
    invoke('missing_terminal',mutation=lambda d:d['RUN_RESULT.json'].pop('batch_ended_ns'),expected=('AssertionError','terminal batch record required'))
    invoke('bad_time_order',mutation=lambda d:d['STARTED.json'].update(started_ns=450),expected=('AssertionError','zero-launch timing mismatch'))
    invoke('no_failure_evidence',mutation=lambda d:d['RUN_RESULT.json']['records'][0].update(errors=[]),expected=('AssertionError','zero-launch failed prefix required'))
    invoke('bad_terminal_counts',mutation=lambda d:d['RUN_RESULT.json'].update(started_cells=2),expected=('AssertionError','zero-launch terminal counts mismatch'))
    invoke('null_PID_success_claim','null',lambda d:d['RUN_RESULT.json']['records'][0]['consumer'].update(status='completed',valid_completion=True),expected=('AssertionError','zero-launch failed prefix required'))
    invoke('missing_PID_thread_present','missing',lambda d:d['RUN_RESULT.json']['records'][0]['consumer'].update(thread_id='unknown-state'),expected=('AssertionError','zero-launch failed prefix required'))
    def remove_gate(d):d.pop('GO.json');d.pop('STARTED.json')
    before=invoke('positive_old','positive',remove_gate,pack=old)
    after=invoke('positive_new','positive',remove_gate,pack=new)
    content=lambda p:{f.relative_to(p).as_posix():f.read_bytes() for f in p.rglob('*') if f.is_file()}
    check('positive_PID_public_output_byte_identical',content(before)==content(after))
check('no_external_attempts',not external)
result={'status':'PASS' if all(c['passed'] for c in checks) else 'FAIL','checks':checks,'cases':cases,'check_count':len(checks),'case_count':len(cases),'author_QA_not_repeated':True,'product_Blender_model_calls':0,'consumer_modules_imported':False,'packager_sha256':sha(PACK.read_bytes()),'old_packager_sha256':sha(OLD.read_bytes()),'PLAN_sha256':sha((B/'PLAN.json').read_bytes()),'scope':'Independent synthetic packaging and helper AST checks only; not proof of real process absence or future consumer quality.'}
p=OUT/'RESULTS.json'
with p.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps({'status':result['status'],'checks':len(checks),'cases':len(cases),'failures':[c['label'] for c in checks if not c['passed']],'sha256':sha(p.read_bytes())}))

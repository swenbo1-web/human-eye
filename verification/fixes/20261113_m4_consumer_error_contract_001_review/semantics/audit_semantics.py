"""One isolated pure-data group on a byte-identical result matcher.

No archive, author matrix, tool code, CLI, server, model or renderer is run.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import pickle
import time

HERE=Path(__file__).resolve().parent
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_consumer_error_contract_001')
SOURCE=AUTHOR/'result_contract.py'
checks=[]
inputs={}

def raw(path):
    data=path.read_bytes();inputs[str(path)]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest());return data
def doc(path):return json.loads(raw(path))
def check(name, passed, detail=None):checks.append(dict(name=name,passed=bool(passed),detail=detail))

source=raw(SOURCE)
snapshot=HERE/'result_contract_snapshot.py'
with snapshot.open('xb') as stream:stream.write(source)
check('snapshot_identical',snapshot.read_bytes()==source)
module_spec=importlib.util.spec_from_file_location('_independent_contract_pure_group',snapshot)
matcher=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(matcher)

# Independently inspect actual response content and its CLI line, without
# invoking the candidate against the full fifteen-transaction corpus.
fixtures=doc(AUTHOR/'FIXTURE_MANIFEST.json')
actual_errors=[]
for record in fixtures['records']:
    if not record['owner_isError']:continue
    owner=doc(AUTHOR/'fixtures'/record['response'])
    event=doc(AUTHOR/'fixtures'/record['CLI_completed'])
    raw_stdout=raw(Path(record['CLI_stdout_source']))
    line=raw_stdout.splitlines(keepends=True)[record['CLI_raw_line_number']-1]
    original=json.loads(line)
    item=original['item']
    check(record['fixture_id']+'/raw_line_digest',hashlib.sha256(line).hexdigest()==record['CLI_raw_line_sha256'])
    check(record['fixture_id']+'/fixture_line',event==original)
    check(record['fixture_id']+'/business_error_status',owner['result']['isError'] is True and item['status']=='failed' and item['error'] is None)
    check(record['fixture_id']+'/preserved_content',json.dumps(owner['result']['content'],sort_keys=True,ensure_ascii=False)==json.dumps(item['result']['content'],sort_keys=True,ensure_ascii=False))
    check(record['fixture_id']+'/projected_shape',set(item['result'])=={'content','structured_content'} and item['result']['structured_content'] is None)
    actual_errors.append(dict(fixture_id=record['fixture_id'],owner_isError=True,CLI_status=item['status'],
        content_text_bytes=sum(len(c.get('text','').encode('utf8')) for c in item['result']['content'] if c.get('type')=='text')))

registered=doc(AUTHOR/'CASES.json')
observed=doc(AUTHOR/'offline/a01/RESULTS.json')
check('47_exact_case_id_set',{c['case_id'] for c in registered['cases']}=={c['case_id'] for c in observed['cases']} and len(registered['cases'])==47)
check('author_case_states_preserved',observed['case_counts']==dict(passed=47,failed=0,not_run=0))
check('expected_real_classifications',registered['expected_real_classifications']==dict(success=13,tool_error=2))

def pair(is_error=False, projected=True, content=None):
    if content is None:content=[{'type':'text','text':'same body','annotations':{'meta_value':True}}]
    owner={'jsonrpc':'2.0','id':17,'result':{'content':copy.deepcopy(content),'isError':is_error}}
    result={'content':copy.deepcopy(content),'structured_content':None} if projected else copy.deepcopy(owner['result'])
    cli={'id':'item_7','type':'mcp_tool_call','tool':'execute_python','arguments':{'code':'not executed'},
         'status':'failed' if is_error else 'completed','error':None,'result':result}
    return owner,cli

cases=[]
def add(name, owner,cli,matched,reason,classification=None):
    cases.append(dict(name=name,owner=owner,cli=cli,expected=dict(matched=matched,reason=reason,
        classification=classification or ('success' if matched else 'protocol_mismatch'))))
for err in (False,True):
    for projected in (False,True):
        o,c=pair(err,projected)
        add(('error'if err else 'success')+('_projected'if projected else '_original'),o,c,True,'content_and_envelope_match','tool_error'if err else 'success')
        o,c=pair(err,projected);c['status']='completed' if err else 'failed'
        add(('error'if err else 'success')+('_projected'if projected else '_original')+'_opposite_status',o,c,False,'cli_status_mismatch')
for boolean,integer in ((True,1),(False,0)):
    o,c=pair(content=[{'type':'text','text':'same','annotations':{'meta_value':boolean}}])
    c['result']['content'][0]['annotations']['meta_value']=integer
    add('nested_body_'+str(boolean)+'_versus_'+str(integer),o,c,False,'content_mismatch')
o,c=pair(content=[{'type':'text','text':'same','annotations':{'values':[1,True,0,False]}}])
c['result']['content'][0]['annotations']['values']=[1,1,0,0]
add('nested_array_bool_int_preserved',o,c,False,'content_mismatch')
o,c=pair();c['result']['content'][0]={'annotations':{'meta_value':True},'text':'same body','type':'text'}
add('object_member_order_not_business_change',o,c,True,'content_and_envelope_match')
o,c=pair(content=[{'type':'text','text':'first'},{'type':'text','text':'second'}]);c['result']['content'].reverse()
add('array_order_is_business_change',o,c,False,'content_mismatch')
o,c=pair(content=[{'type':'image','mimeType':'image/png','data':'YWJj'}]);c['result']['content'][0]['data']='YWJk'
add('image_payload_change',o,c,False,'content_mismatch')
o,c=pair(content=[{'type':'image','mimeType':'image/png','data':'YWJj'}]);c['result']['content'][0]['mimeType']='image/jpeg'
add('image_mime_change',o,c,False,'content_mismatch')
o,c=pair(content=[{'type':'text','text':'same','annotations':{'meta_value':float('nan')}}])
add('nonfinite_JSON_rejected',o,c,False,'content_invalid_json')
o,c=pair(content=[{'type':'text','text':'same','annotations':{1:'integer key'}}])
add('JSON_key_coercion_rejected',o,c,False,'content_invalid_json')
o,c=pair(content=[{'type':'text','text':'same','annotations':{'values':(1,2)}}])
add('Python_tuple_not_JSON_array',o,c,False,'content_invalid_json')
o,c=pair();c['error']=False
add('false_is_not_null_CLI_error',o,c,False,'cli_error_non_null')
o,c=pair();del c['error']
add('missing_CLI_error_not_implicit_null',o,c,False,'cli_error_missing')
o,c=pair();o['result']['isError']=0
add('owner_integer_not_boolean_flag',o,c,False,'owner_is_error_not_boolean')
o,c=pair(projected=False);c['result']['isError']=0
add('CLI_integer_not_boolean_flag',o,c,False,'cli_is_error_not_boolean')

# Case definitions and expectations are persisted before the one execution.
prereg=dict(scope='one targeted pure-data group; synthetic annotations test JSON equality, not full MCP-content schema validation',
    source_sha256=hashlib.sha256(source).hexdigest(),case_count=len(cases),
    cases=[dict(name=c['name'],expected=c['expected'])for c in cases])
with (HERE/'PURE_CASES.json').open('x',encoding='utf8')as stream:json.dump(prereg,stream,ensure_ascii=False,indent=2);stream.write('\n')
started=time.perf_counter_ns();results=[]
for case in cases:
    o,c=case['owner'],case['cli'];before=pickle.dumps((o,c),protocol=4)
    try:
        actual=matcher.bind_tool_result(o,c);error=None
    except BaseException as exc:
        actual=None;error=dict(type=type(exc).__name__,message=str(exc))
    immutable=pickle.dumps((o,c),protocol=4)==before
    passed=actual==case['expected'] and immutable
    check(case['name']+'/semantic_result',actual==case['expected'],dict(expected=case['expected'],actual=actual,error=error))
    check(case['name']+'/input_unchanged',immutable)
    results.append(dict(name=case['name'],expected=case['expected'],actual=actual,error=error,inputs_unchanged=immutable,passed=passed))
closed=time.perf_counter_ns()
check('source_still_identical',SOURCE.read_bytes()==source and snapshot.read_bytes()==source)
out=dict(author_commit='cb5c33a158a9dea06c8151248cc42d2b87c5697b',check_count=len(checks),checks=checks,failed=[c for c in checks if not c['passed']],
    pure_group_count=1,pure_candidate_calls=len(cases),pure_cases=results,pure_elapsed_ns=closed-started,actual_error_records=actual_errors,
    inputs=inputs,source_copy_sha256=hashlib.sha256(source).hexdigest(),
    executed='One offline audit Python script; only candidate pure result matcher copied byte-identically. No full author matrix, archive, caller or actual tool code execution.',
    unrun=['full47author_matrix','candidate_archive_or_driver','fresh_CLI','actor_server','model','renderer','Blender','provider'],
    limitations=['caller identity/attempt/global connection review belongs to separate root audit','pure annotations cover JSON type fidelity; no claim that arbitrary annotation shape is valid MCP semantic content','old formal states and provider usage unknown not changed'])
(HERE/'RESULTS.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:out[k]for k in ('check_count','failed','pure_candidate_calls','pure_elapsed_ns','actual_error_records')}))

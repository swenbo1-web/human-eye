"""Only synthetic nine-slot postprocessing; never a model/backend experiment.

All fictitious cells, PIDs and finals live below synthetic/run_02. The real
frozen map is checked structurally, but separate synthetic anonymous IDs are
used here. The shared image is an unchanged byte copy, never rendered.
"""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import traceback
from unittest.mock import patch
import zipfile

HERE=Path(__file__).resolve().parent
BATCH=HERE.parent
OLD=BATCH.parent/'m4_observation_baseline_001'
OUT=HERE/'run_02'
PACKAGER_SHA='90f07a6b78457bb7ca9a5b93fbb7d78bf3439b547cfb21ff4fbae0b0c76ab0d4'
CYCLE='M4-LOCAL-RELATION-CONSUMPTION-001'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
encode=lambda value:(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf8')
checks=[]
external_attempts={'subprocess':0,'socket':0}


def put(path,raw):
    assert path.resolve().is_relative_to(OUT.resolve())
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(raw)


def check(name,value):
    checks.append({'check':name,'passed':bool(value)})


def fixture(slot,index):
    internal={'N':'N','P0':'P','P1':'P'}[slot['group']]
    path='C:\\SYNTHETIC source folder\\profile geometry.txt'
    payload={'synthetic':True,'condition':{'one':True,'two':False},'profile':'synthetic cross section',
      'group':'geometric group, not an experiment arm','usage':{'profile':'semantic usage','condition':False},
      'pid':'semantic part id','cost':'geometry-path cost','_meta':{'group':'semantic metadata'},
      'unknown_future_field':{'traceback':'semantic nested field'},'original_path':path}
    text=' \r\n'+json.dumps(payload,ensure_ascii=False,indent=3)+'  \n\t'
    stdout='  SYNTHETIC native stdout\r\n'+path+'\n  '
    result={'content':[{'type':'text','text':text},{'type':'text','text':stdout}],
      'isError':False,'structured':payload,'native':{'result':{'result':text,'stdout':stdout}}}
    error={'code':-32000,'message':'  SYNTHETIC error\n'+path+'  ',
      'data':{'condition':payload['condition'],'profile':payload['profile'],'usage':payload['usage'],'raw':text}}
    code='# SYNTHETIC inert text, never executed\r\nprint('+repr(path)+')\n  '
    request={'jsonrpc':'2.0','id':7,'_meta':{'trace_id':'synthetic-rpc'},'method':'tools/call',
      'params':{'name':'SYNTHETIC_tool','_meta':{'usage':0},'arguments':{'code':code,'query':payload,'_meta':payload}}}
    final='  SYNTHETIC fixture final '+str(index)+'; not a real task answer\r\n'+path+'  \n'
    consumer={**slot,'synthetic':True,'group':internal,'external_group':slot['group'],
      'status':'failed' if index==1 else 'completed','final':None if index==1 else final}
    sources={'CONSUMER.json':encode(consumer),'PUBLIC_FINAL.txt':final.encode('utf8'),
      'final.txt':b'SYNTHETIC CLI corroboration; never replace final\r\n',
      'owner/CLOSE.json':encode({'synthetic':True,'geometry_unchanged':False,'asset_unchanged':None,
        'native_close':{'source_file_unchanged':False,'protected_files_unchanged':None},
        'worker_closed':{'pid':99999,'closed_ns':1,'original_deadline_ns':2,
          'initial_geometry_fingerprint':'synthetic-before','final_geometry_fingerprint':'synthetic-after',
          'nested':payload},'errors':[error]})}
    item={'type':'mcp_tool_call','tool':'SYNTHETIC_tool','server':'SYNTHETIC_server',
      'arguments':request['params']['arguments'],'result':result,'error':error,'status':'failed','command':code}
    events=[{'synthetic':True,'perf_ns':i,'event':{'type':phase,'item':item}}
      for i,phase in enumerate(('item.started','item.completed','item.completed'))]
    if index in (1,2):
        sources.pop('PUBLIC_FINAL.txt')
        events.append({'synthetic':True,'event':{'type':'item.completed',
          'item':{'type':'agent_message','text':'SYNTHETIC unconfirmed message; not a final\r\n  '}}})
    if index==4:
        sources['PUBLIC_FINAL.txt']=b'SYNTHETIC inconsistent original final retained verbatim\r\n'
    sources['events.jsonl']=b''.join(json.dumps(entry,ensure_ascii=False,separators=(',',':')).encode('utf8')+b'\n' for entry in events)
    for number in (1,2,3):
        prefix='owner/tool_'+str(number).zfill(2)+'/'
        sources[prefix+'REQUEST.json']=encode(request)
        sources[prefix+'ATTEMPT.json']=encode({'synthetic':True,'is_error':number!=1,
          'exception':None if number==1 else {'type':'SYNTHETIC','message':error['message'],
            'traceback':'administrative only','data':payload}})
        if number==1:sources[prefix+'RESPONSE.json']=encode({'jsonrpc':'2.0','id':7,'result':result})
        if number==2:sources[prefix+'ERROR_RESPONSE.json']=encode({'jsonrpc':'2.0','id':7,'error':error})
    # A recorded entry with no consumer or sources must remain distinct from a tail.
    if index==3:sources={}
    return sources,{'result':result,'error':error,'request':request,'payload':payload,'final':final}


def verify_answer(module,folder,slot,index,sources,expected,answer,audit):
    anon=answer['anonymous_id'];directory=folder/'quality_handoff/handoff_01/public'/anon
    if not sources:
        check(anon+':entered_without_consumer',(answer['execution_record_state'],answer['answer_state'])==('failed_before_consumer','missing'))
        return
    tools=json.loads((directory/'tool_evidence.json').read_bytes())
    calls=tools['owner_attempts'];events=tools['public_tool_events']
    check(anon+':three_unmerged_attempts',len(calls)==3 and [row['order'] for row in calls]==[1,2,3])
    check(anon+':duplicate_requests_preserved',calls[0]['request']==calls[1]['request']==calls[2]['request'])
    check(anon+':request_code_arguments_exact',calls[0]['request']['params']['arguments']==expected['request']['params']['arguments'])
    check(anon+':error_and_missing_response_preserved',[row['is_error'] for row in calls]==[False,True,True] and [row['response_missing'] for row in calls]==[False,False,True])
    check(anon+':owner_result_exact',calls[0]['responses'][0]['value']=={'result':expected['result']})
    check(anon+':owner_error_exact',calls[1]['responses'][0]['value']=={'error':expected['error']})
    check(anon+':public_result_error_string_exact',len(events)==3 and all(
      row['event']['result']==expected['result'] and row['event']['error']==expected['error'] for row in events))
    check(anon+':owner_exception_only_top_traceback_removed',all(
      calls[i]['owner_exception']=={'type':'SYNTHETIC','message':expected['error']['message'],'data':expected['payload']} for i in (1,2)))
    consistency=json.loads((directory/'source_consistency.json').read_bytes())
    worker=consistency['CLOSE']['worker_closed']
    check(anon+':worker_only_known_top_fields_removed',worker=={'initial_geometry_fingerprint':'synthetic-before',
      'final_geometry_fingerprint':'synthetic-after','nested':expected['payload']})
    check(anon+':close_error_payload_exact',consistency['CLOSE']['errors']==[expected['error']])
    check(anon+':false_null_not_promoted',consistency['CLOSE']['geometry_unchanged'] is False and consistency['CLOSE']['asset_unchanged'] is None)
    if 'PUBLIC_FINAL.txt' in sources:
        check(anon+':original_final_bytes',(directory/'answer.txt').read_bytes()==sources['PUBLIC_FINAL.txt'])
        wanted='inconsistent_final_binding' if index==4 else 'present'
        check(anon+':final_binding_state',answer['answer_state']==wanted)
    else:
        check(anon+':missing_final_not_repaired',answer['answer_state']=='missing' and answer['answer_file'] is None and not (directory/'answer.txt').exists())
        check(anon+':message_remains_unconfirmed',len(answer['unconfirmed_public_messages'])==1)
    check(anon+':CLI_exact_unconfirmed',(directory/'cli_output_unconfirmed.txt').read_bytes()==sources['final.txt'])
    check(anon+':source_hashes_exact',audit['source_files_sha256']=={name:sha(raw) for name,raw in sources.items()})
    with zipfile.ZipFile(folder/'quality_handoff/handoff_01/private/raw'/(anon+'.zip')) as archive:
        check(anon+':all_original_members_exact',{name:archive.read(name) for name in archive.namelist()}==sources)


def package_case(module,sequence,name,prefix):
    folder=OUT/name/'synthetic_eval';(folder/'quality_handoff').mkdir(parents=True)
    put(folder/'SYNTHETIC_SCOPE.json',encode({'synthetic':True,'all_PIDs_fictitious':True,
      'real_consumers':0,'product_calls':0,'Blender_sessions':0,'GO_created':False,
      'note':'Not real formal cells, answers, execution receipts or a quality score.'}))
    mapping={'synthetic':True,'generated_before_consumer':True,'rows':[
      dict(slot,anonymous_id='answer_'+sha(('synthetic-anonymous|'+slot['cell']).encode())[:16]) for slot in sequence]}
    mapping_raw=encode(mapping)
    image=(OLD/'input/INITIAL.png').read_bytes();prompt=b'SYNTHETIC packaging fixture only; no task answer or consumer.\n'
    plan={'synthetic':True,'cycle_id':CYCLE,'batch':CYCLE,'sequence':sequence,'logical_denominator':9,
      'per_arm':3,'arms':{'N':'synthetic','P0':'synthetic','P1':'synthetic'},'image_count':1,'new_images':0,
      'private_anonymous_map_sha256':sha(mapping_raw),'tasks':{'T1':{}},
      'inputs':{'image':'input/INITIAL.png','image_sha256':sha(image),'image_bytes':len(image),
        'prompt':'input/PROMPT.txt','prompt_sha256':sha(prompt)}}
    plan_raw=encode(plan);fixtures=[];records=[]
    for index,slot in enumerate(sequence[:prefix]):
        sources,expected=fixture(slot,index);fixtures.append((sources,expected))
        records.append({**slot,'synthetic':True,'consumer':{'consumer_pid':99000+index,'synthetic_fictitious_PID':True}})
        for relative,raw in sources.items():put(folder/'cells'/slot['cell']/relative,raw)
    run={'synthetic':True,'records':records,'batch_ended_ns':1,'stop':None if prefix==9 else 'synthetic_deliberate_stop'}
    for relative,raw in {'PLAN.json':plan_raw,'FREEZE.json':encode({'plan_sha256':sha(plan_raw)}),
      'private/ANON_MAP.json':mapping_raw,'RUN_RESULT.json':encode(run),'input/INITIAL.png':image,'input/PROMPT.txt':prompt}.items():put(folder/relative,raw)
    module.HERE=folder/'quality_handoff';module.EVAL=folder
    previous=sys.argv;stream=io.StringIO()
    try:
        sys.argv=['synthetic_packager','handoff_01']
        with contextlib.redirect_stdout(stream):module.main()
    finally:sys.argv=previous
    put(OUT/name/'PACKAGER_STDOUT.txt',stream.getvalue().encode('utf8'))
    public=folder/'quality_handoff/handoff_01/public'
    index=json.loads((public/'INDEX.json').read_bytes())
    receipt=json.loads((folder/'quality_handoff/handoff_01/private/PROVENANCE.json').read_bytes())
    by_id={row['anonymous_id']:row for row in index['answers']}
    audit={row['mapping']['anonymous_id']:row for row in receipt['answers']}
    check(name+':fixed_nine_all_present',index['fixed_slots']==9 and len(by_id)==len(index['answers'])==9)
    check(name+':opaque_sorted',[row['anonymous_id'] for row in index['answers']]==sorted(by_id))
    check(name+':private_map_exact',receipt['fixed_anonymous_map']==mapping)
    check(name+':no_scoring',index['scoring_performed'] is False and receipt['scoring_calls']==0)
    check(name+':source_script_sha',receipt['script_sha256']==PACKAGER_SHA)
    check(name+':public_hash_manifest',receipt['public_files_sha256']=={path.relative_to(public).as_posix():sha(path.read_bytes()) for path in public.rglob('*') if path.is_file()})
    for i,row in enumerate(mapping['rows']):
        answer=by_id[row['anonymous_id']]
        if i<prefix:verify_answer(module,folder,sequence[i],i,*fixtures[i],answer,audit[row['anonymous_id']])
        else:check(name+':tail_not_run:'+str(i),(answer['execution_record_state'],answer['answer_state'])==('not_run','not_run'))


def cross_binding(module,sequence):
    for slot in sequence[:3]:
        sources,_=fixture(slot,0);base_consumer=json.loads(sources['CONSUMER.json'])
        group=slot['group'];target=OUT/'cross_binding'/group
        good,_=module.handoff_one(slot,{'anonymous_id':'synthetic_good'},slot,sources,target/'good')
        check(group+':correct_internal_external_binding',good['answer_state']=='present')
        mutations=[('internal_group',{'group':'P' if base_consumer['group']=='N' else 'N'}),
          ('external_group',{'external_group':next(value for value in ('N','P0','P1') if value!=group)}),
          ('missing_external_group',{'external_group':None})]
        for label,delta in mutations:
            modified=copy.deepcopy(sources);bad=dict(base_consumer,**delta);modified['CONSUMER.json']=encode(bad)
            rejected=False;wrong_error=None
            try:module.handoff_one(slot,{'anonymous_id':'synthetic_bad'},slot,modified,target/label)
            except AssertionError as exc:rejected=str(exc)=='consumer external/internal group binding mismatch'
            except Exception as exc:wrong_error=type(exc).__name__
            check(group+':reject_'+label,rejected and wrong_error is None and not (target/label).exists())
        for key in ('cell','task','round'):
            modified=copy.deepcopy(sources);bad=dict(base_consumer);bad[key]='synthetic-wrong-binding'
            modified['CONSUMER.json']=encode(bad);rejected=False
            try:module.handoff_one(slot,{'anonymous_id':'synthetic_bad'},slot,modified,target/('wrong_'+key))
            except AssertionError as exc:rejected=str(exc)=='consumer slot binding mismatch'
            check(group+':reject_wrong_'+key,rejected)


def main():
    OUT.mkdir(exist_ok=False)
    unexpected=None
    try:
        path=BATCH/'quality_handoff/pack_quality.py';raw=path.read_bytes()
        assert sha(raw)==PACKAGER_SHA
        spec=importlib.util.spec_from_file_location('synthetic_nine_slot_packager',path)
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
        sequence=json.loads((BATCH/'SEQUENCE.json').read_bytes())['sequence']
        def forbidden(kind):
            def stop(*args,**kwargs):external_attempts[kind]+=1;raise AssertionError('forbidden external '+kind)
            return stop
        with patch('subprocess.Popen',side_effect=forbidden('subprocess')),patch('socket.socket',side_effect=forbidden('socket')):
            package_case(module,sequence,'all_nine',9)
            package_case(module,sequence,'stopped_prefix_five',5)
            cross_binding(module,sequence)
    except BaseException as exc:
        unexpected={'type':type(exc).__name__,'traceback':traceback.format_exc()}
    report={'synthetic':True,'passed':unexpected is None and all(row['passed'] for row in checks),
      'checks':checks,'check_count':len(checks),'failures':sum(not row['passed'] for row in checks),
      'unexpected_error':unexpected,'packager_sha256':PACKAGER_SHA,'test_script_sha256':sha(Path(__file__).read_bytes()),
      'scenarios':['synthetic full nine','synthetic stopped prefix five + four not_run','three external/internal groups with cross-binding refusals'],
      'model_consumers':0,'product_calls':0,'Blender_sessions':0,'GO_created':False,
      'external_attempts':external_attempts,'new_images':0,'image_scope':'unchanged historical PNG byte copies only',
      'no_formal_cells_or_answers':'All fictitious source cells/finals and positive PID placeholders live under synthetic/run_02 only; no actual consumers or quality scores.'}
    put(OUT/'RESULTS.json',encode(report))
    print(json.dumps({'passed':report['passed'],'checks':len(checks),'failures':report['failures'],
      'unexpected_error':None if unexpected is None else unexpected['type'],'external_attempts':external_attempts,
      'model_consumers':0,'product_calls':0,'Blender_sessions':0}))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())

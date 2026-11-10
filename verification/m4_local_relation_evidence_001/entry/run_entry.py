"""Four bounded installed entry sessions, no model, new asset, image or activation.

Reuse the accepted M1 C/S actor and original NativeSession/thin probe. Every
profile uses one owned Blender copy and six unchanged-parameter requests.
Metadata-only product processes have no host and are counted separately.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import time
import traceback
import types

HERE=Path(__file__).resolve().parent
BATCH=HERE.parent
ROOT=BATCH.parents[1]
M1=ROOT/'verification/m1_task_entry_001_eval'
BASE=ROOT/'verification/m4_observation_baseline_001'
BASE_SHA='7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1'
CANDIDATE_SHA='53db41976085ce5f361d026196f4da5faf80d639af33dfced35ba58e328ef732'
COMMIT='e077fce38b5951efff8166b3b688d05ffa2ebf04'
ASSET_SHA='91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
SOURCE_SNAPSHOT_SHA='ba46e235d6493c193bec7d79b741f2781badda7921aea2537491b609ec6eea4d'
BLENDER='D:/Tools/blender5.2/blender.exe'
ROLES={'baseline':BASE/'installation/READY.json','candidate':BATCH/'installation/READY.json'}
READ_NAMES={'C':{'human_eye_scene_observe','human_eye_connection_status'},
            'S':{'human_eye_spatial_relations','human_eye_surface_nearest'}}
sha=lambda raw:hashlib.sha256(raw).hexdigest()
read=lambda path:json.loads(Path(path).read_bytes())


def save(path,value):
    path=Path(path)
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);stream.write('\n')


def load(name,path):
    raw=Path(path).read_bytes();module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(raw,str(path),'exec',dont_inherit=True),module.__dict__)
    return module


def identity_check(identity,ready):
    assert identity['source_sha256']==ready['source_sha256']
    assert identity['source_kind']=='installed_distribution'
    assert identity['distribution_version']==ready['version']


def metadata(actor,ready,profile,folder,deadline):
    config={'schema_version':'1.0','enabled':True,'observe_on_prompt':False,'project_root':ready['install_root'],
        'state_file':str(folder/'metadata_state.json'),'audit_file':str(folder/'metadata_audit.jsonl'),
        'quad_size':128,'expected_identity':{'source_sha256':ready['source_sha256']},
        'blender':{'host':'127.0.0.1','port':1,'timeout_s':30.}}
    save(folder/'metadata_config.json',config);peer=None;result={}
    try:
        peer=actor.Peer.__new__(actor.Peer)
        peer.__init__(dict(ready,group=profile,product_config=folder/'metadata_config.json'),folder/'metadata')
        remaining=lambda:max(.001,min(30.,(deadline-time.perf_counter_ns())/1e9))
        assert time.perf_counter_ns()<deadline
        answer=peer.call({'jsonrpc':'2.0','id':'metadata-init','method':'initialize','params':{
            'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'local-relation-entry','version':'001'}}},timeout_s=remaining())
        identity=answer['result']['_meta']['human_eye'];identity_check(identity,ready)
        peer.call({'jsonrpc':'2.0','method':'notifications/initialized'},timeout_s=remaining())
        listing=peer.call({'jsonrpc':'2.0','id':'metadata-list','method':'tools/list'},timeout_s=remaining())
        tools=listing['result']['tools'];selected=[row for row in tools if row['name'] in READ_NAMES[profile]]
        assert len(selected)==2 and {row['name'] for row in selected}==READ_NAMES[profile]
        if profile=='S':assert len(tools)==2
        ping=peer.call({'jsonrpc':'2.0','id':'metadata-ping','method':'ping'},timeout_s=remaining())
        assert ping['result']=={}
        save(folder/'ACTUAL_METADATA_INITIALIZE.json',answer);save(folder/'ACTUAL_METADATA_TOOLS.json',listing)
        save(folder/'PUBLIC_TOOLS.json',selected);save(folder/'ACTUAL_METADATA_PING.json',ping)
        result={'installed_identity':identity,'tools':[row['name'] for row in tools],
            'public_tools_sha256':sha((folder/'PUBLIC_TOOLS.json').read_bytes()),
            'Blender_sessions':0,'geometry_requests':0,'host':'unused private loopback port1'}
        return selected,result
    finally:
        if peer is not None:
            result['close']=peer.close()
            save(folder/'METADATA_CLOSE.json',result)


def messages(profile):
    if profile=='C':
        params={'name':'human_eye_scene_observe','arguments':{'session_id':'local-relation-entry',
            'include_image':False,'query':{'mode':'task','target':{'name':'N16'},
                'candidates':[{'name':name} for name in ('N13','N08','N28')],
                'requested_facts':['closed_solid_relation','surface_proximity']}}}
    else:
        params={'name':'human_eye_spatial_relations','arguments':{'target':{'name':'N16'},
            'candidates':[{'name':name} for name in ('N13','N08','N28')]}}
    rows=[{'jsonrpc':'2.0','id':'client-init','method':'initialize','params':{
        'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'local-relation-fixed-six','version':'001'}}},
        {'jsonrpc':'2.0','method':'notifications/initialized'},
        {'jsonrpc':'2.0','id':'client-list','method':'tools/list'}]
    rows += [{'jsonrpc':'2.0','id':'relation-'+str(index),'method':'tools/call','params':copy.deepcopy(params)}
        for index in range(1,7)]
    assert len({json.dumps(row['params'],sort_keys=True) for row in rows[3:]})==1
    return rows


def rows_from_body(body,profile,expected_source):
    assert body['status']=='observed' and body['execution_authority'] is False
    binding=body['binding'] if profile=='C' else body['context']
    assert binding['runtime_source_sha256']==expected_source
    assert binding.get('unit',body.get('unit'))=='m'
    assert binding.get('coordinate_frame',body.get('coordinate_frame'))=='world'
    if profile=='C':
        assert [row['name'] for row in body['binding']['objects']]==['N16','N13','N08','N28']
        output=[dict(name=name,closed=pair['facts']['closed_solid_relation'],
            surface=pair['facts']['surface_proximity'],gap=pair['separation_gap'])
            for name,pair in zip(('N13','N08','N28'),body['pairs'],strict=True)]
    else:
        assert body['target']['name']=='N16' and [row['name'] for row in body['candidates']]==['N13','N08','N28']
        contracts=body['measurement_contracts']
        output=[dict(name=row['name'],
            closed={**contracts.get('closed_solid_relation',{}),**row['closed_solid_relation']},
            surface={**contracts.get('surface_proximity',{}),**row['surface_proximity']},
            gap={**contracts.get('separation_gap',{}),**row['separation_gap']})
            for row in body['candidates']]
    assert [row['closed']['value'] for row in output]==['penetrating','separated','separated']
    assert all(row['closed']['status']=='measured' for row in output)
    return output


def read_events(path):
    return [json.loads(line) for line in path.read_bytes().splitlines() if line]


def reserve_owned_scene(ready,profile,folder):
    """One fixed batch-wide cap, including earlier failed script invocations."""
    path=HERE/'OWNED_SCENE_STARTS.jsonl'
    previous=read_events(path) if path.exists() else []
    assert len(previous)<4,'maximum_four_owned_scene_starts_across_all_runs'
    row={'ordinal':len(previous)+1,'source_sha256':ready['source_sha256'],
        'profile':profile,'folder':str(folder),'reserved_ns':time.perf_counter_ns(),
        'scope':'conservative slot reservation before Popen; failed Popen is not silently refunded'}
    with path.open('a',encoding='utf8',newline='\n') as stream:
        stream.write(json.dumps(row,sort_keys=True)+'\n')
    return row


def collect_tools(folder,profile,source,probe):
    replies={row['id']:row for row in probe['responses']}
    rpc=read(folder/'owner/plugin/RPC.json')['requests']
    events=read_events(folder/'owner/native/WORKER_EVENTS.jsonl')
    audit=read_events(folder/'owner/audit.jsonl')
    observed=[row for row in audit if row.get('event')=='observe']
    assert len(observed)==6
    output=[]
    for index in range(1,7):
        tool=folder/'owner'/('tool_'+str(index).zfill(2))
        attempt=read(tool/'ATTEMPT.json');request=read(tool/'REQUEST.json')
        answer=replies['relation-'+str(index)]
        assert answer['result']['isError'] is False and attempt['is_error'] is False
        blocks=answer['result']['content'];assert len(blocks)==1 and blocks[0]['type']=='text'
        body=json.loads(blocks[0]['text']);facts=rows_from_body(body,profile,source)
        expected_local=source==CANDIDATE_SHA
        assert ('local_evidence' in facts[0]['closed']) is expected_local
        assert all('local_evidence' not in row['closed'] for row in facts[1:])
        matches=[(offset,row) for offset,row in enumerate(rpc,1) if row.get('request_id')==request['id']]
        assert len(matches)==1;offset,receipt=matches[0]
        wire=folder/'owner/plugin'/str(offset).zfill(3)
        rx=(wire/'RX.bin').read_bytes();tx=(wire/'TX.bin').read_bytes()
        assert len(rx)==receipt['received_bytes'] and len(tx)==receipt['sent_bytes']
        first=attempt['started_ns'];last=first+attempt['elapsed_ns']
        physical=[row for row in events if type(row.get('sequence')) is int
            and type(row.get('started_ns')) is int and first<=row['started_ns']<=last]
        work=observed[index-1]['task_work']
        row={'request_index':index,'cache_phase_label':'first_application_request' if index==1 else 'repeated_request',
            'request_params_sha256':sha(json.dumps(request['params'],sort_keys=True,separators=(',',':')).encode()),
            'product_stdio_receipt':receipt,'product_stdio_TX_bytes':len(tx),'product_stdio_RX_bytes':len(rx),
            'owner_attempt':attempt,'worker_received_request_count':len(physical),
            'worker_received_request_sequences':[event['sequence'] for event in physical],
            'worker_event_scope':'received worker request events whose start falls in owner tool interval; excludes initial/final safety reads and close, unreceived/transport attempts not inferred',
            'task_work':work,'facts':facts,'original_body':body,
            'cache_scope':'repeated request is not assumed a hit; existing result/pair cache flags in task_work are authoritative',
            'timing_scope':'product Peer elapsed includes its existing directory/TX/RX/JSON/audit work; owner interval includes Peer and overlaps it; never add the two as independent costs'}
        save(tool/'ENTRY_MEASUREMENT.json',row);output.append(row)
    return output


def run_case(actor,driver,client,ready,profile,folder):
    began=time.perf_counter_ns();deadline=began+570*10**9
    folder.mkdir(parents=True,exist_ok=False)
    result={'profile':profile,'source_sha256':ready['source_sha256'],'started_ns':began,
        'worker_deadline_ns':deadline,'errors':[],'finish':None,'requests':[]}
    process=runtime_handle=None
    try:
        schemas,result['metadata']=metadata(actor,ready,profile,folder,deadline)
        assert time.perf_counter_ns()<deadline
        config={'group':profile,'task':'local-relation-entry','output':str(folder/'owner'),
            'endpoint':str(folder/'ENDPOINT.json'),'asset':str(BASE/'input/scene.blend'),
            'asset_sha256':ASSET_SHA,'blender':BLENDER,'worker_deadline_ns':deadline,
            'dependency_python':ready['dependency_python'],'read_schemas':schemas,
            'entry':ready['entry'],'install_root':ready['install_root'],'source_sha256':ready['source_sha256']}
        save(folder/'ACTOR_CONFIG.json',config)
        command=[ready['dependency_python'],'-I','-B',str(M1/'actor.py'),'--config',str(folder/'ACTOR_CONFIG.json')]
        startup=min(deadline,time.perf_counter_ns()+40*10**9)
        result['owned_scene_start_reserved']=reserve_owned_scene(ready,profile,folder)
        with (folder/'actor_stdout.bin').open('wb') as out,(folder/'actor_stderr.bin').open('wb') as err:
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=out,stderr=err,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        result['actor_launcher_pid']=process.pid
        save(folder/'ACTOR_LAUNCH.json',{'pid':process.pid,'argv':command,'started_ns':began})
        while not (folder/'ENDPOINT.json').exists():
            assert process.poll() is None,'owned_actor_start_failed'
            if time.perf_counter_ns()>=startup:raise TimeoutError('original_actor_start_window')
            time.sleep(.02)
        identity=read(folder/'owner/IDENTITY.json');identity_check(identity['runtime_identity'],ready)
        assert identity['actor_pid']==process.pid or identity['actor_parent_pid']==process.pid
        proof,runtime_handle=client._windows_runtime_proof(process,identity['actor_pid'],deadline)
        save(folder/'ACTOR_RUNTIME_PROVENANCE.json',proof);assert proof['confirmed'] is True
        driver.snapshot_binding(read(folder/'owner/INITIAL.json'),read(BASE/'preflight/SOURCE_SNAPSHOT.json'))
        if time.perf_counter_ns()>=deadline:raise TimeoutError('original_entry_deadline')
        requested=messages(profile);save(folder/'REQUESTS.json',requested)
        probe=client.probe(ready['dependency_python'],folder/'ENDPOINT.json',folder/'thin_probe',requested)
        assert probe['confirmed'],'thin_client_lifecycle_unconfirmed'
        listed=next(row for row in probe['responses'] if row['id']=='client-list')['result']['tools']
        assert listed==[actor.base.NATIVE]+schemas
        result['thin_probe_lifecycle']=dict(confirmed=probe['confirmed'],
            launcher_pid=probe['launcher_pid'],runtime_pid=probe['runtime_pid'],
            launcher_exit_code=probe['launcher_exit_code'],runtime_exit=probe['runtime_exit'])
        result['requests']=collect_tools(folder,profile,ready['source_sha256'],probe)
    except BaseException as exc:
        result['errors'].append({'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()})
    finally:
        if process is not None:
            try:
                result['finish']=driver.finish(folder,process)
                assert result['finish']['confirmed'],'owned_actor_worker_product_close_unconfirmed'
                driver.snapshot_binding(read(folder/'owner/INITIAL.json'),read(folder/'owner/FINAL.json'))
                close=result['finish']['close']
                assert close['geometry_unchanged'] and close['asset_unchanged']
                assert close['native_close']['source_file_unchanged'] and close['native_close']['protected_files_unchanged']
                events=read_events(folder/'owner/native/WORKER_EVENTS.jsonl')
                construction=[row for row in events if row.get('event') in ('render_started','render_completed','render_cancelled')
                    or row.get('changed_or_new_PNG_files') or row.get('render_events_after',0)>row.get('render_events_before',0)]
                result['recorded_image_construction_events']=construction
                assert not construction,'unexpected_image_construction_in_original_helper_scope'
            except BaseException as exc:
                result['errors'].append({'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()})
        result['actor_runtime_exit']=client._runtime_exit(runtime_handle)
        if process is not None and result['actor_runtime_exit']['confirmed'] is not True:
            result['errors'].append({'type':'RuntimeExitUnknown','message':'actual_actor_exit_unconfirmed'})
        result['ended_ns']=time.perf_counter_ns();result['within_570s']=result['ended_ns']<deadline
        result['passed']=bool(not result['errors'] and result['within_570s']
            and result['finish'] and result['finish']['confirmed'] and len(result['requests'])==6)
        save(folder/'RESULTS.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,help='New immediate child, preserves every earlier attempt')
    args=parser.parse_args();assert Path(args.output).name==args.output and args.output not in ('.','..')
    output=HERE/args.output;output.mkdir(exist_ok=False)
    reuse=read(HERE/'RUNNER_REUSE.json')
    for row in reuse['files']:
        assert sha((ROOT/row['path']).read_bytes())==row['sha256'],'reused_runner_drift'
    before={str(path):sha(path.read_bytes()) for path in (BASE/'input/scene.blend',BASE/'input/INITIAL.png',BASE/'preflight/SOURCE_SNAPSHOT.json')}
    assert before[str(BASE/'input/scene.blend')]==ASSET_SHA
    assert before[str(BASE/'preflight/SOURCE_SNAPSHOT.json')]==SOURCE_SNAPSHOT_SHA
    versions={role:read(path) for role,path in ROLES.items()}
    assert versions['baseline']['source_sha256']==BASE_SHA and versions['candidate']['source_sha256']==CANDIDATE_SHA
    assert versions['candidate']['commit']==COMMIT
    assert all(row['source_count']==137 and row['no_default_activation'] for row in versions.values())
    assert versions['baseline']['dependency_python']==versions['candidate']['dependency_python']
    save(output/'FIXED_INPUTS.json',{'versions':versions,'asset_sha256':ASSET_SHA,'protected_before':before,
        'requests_per_scene':6,'maximum_owned_Blender_scenes':4,'metadata_only_product_processes_separately_counted':True,
        'script_sha256':sha(Path(__file__).read_bytes()),'model_consumers':0,'new_images':0})
    actor=load('_local_entry_original_actor',M1/'actor.py')
    driver=load('_local_entry_original_finish',M1/'driver.py')
    client=load('_local_entry_original_thin_probe',M1/'preflight_client.py')
    results=[]
    for profile in ('C','S'):
        for role in ('baseline','candidate'):
            if len(results)>=4:raise RuntimeError('maximum_four_owned_scenes')
            case=run_case(actor,driver,client,versions[role],profile,output/(role+'_'+profile))
            case['role']=role;results.append(case)
            save(output/('RESULTS_AFTER_'+str(len(results))+'.json'),{'cases':results,'model_consumers':0})
            if not case['passed']:break
        if not results[-1]['passed']:break
    after={path:sha(Path(path).read_bytes()) for path in before}
    reuse_unchanged=all(sha((ROOT/row['path']).read_bytes())==row['sha256'] for row in reuse['files'])
    value={'passed':len(results)==4 and all(row['passed'] for row in results) and before==after and reuse_unchanged,
        'cases':results,'protected_before':before,'protected_after':after,'protected_inputs_unchanged':before==after,
        'reused_runners_unchanged':reuse_unchanged,
        'owned_scene_attempts':sum(row.get('owned_scene_start_reserved') is not None for row in results),
        'metadata_only_attempts':len(results),'model_consumers':0,'new_images':0,
        'scope':'installed actual C/S engineering entry, application-cache request order only; not OS-cold, model latency, token or cognitive evidence benefit'}
    save(output/'RESULTS.json',value)
    print(json.dumps({'passed':value['passed'],'cases':len(results),'output':str(output),'model_consumers':0}))
    return 0 if value['passed'] else 1


if __name__=='__main__':raise SystemExit(main())

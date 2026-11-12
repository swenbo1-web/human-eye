"""One owned actual qualification sequence, with product rejections preserved."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import time
import traceback
import types

HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
READY = BATCH/'installation/READY.json'
QUALIFICATION = ROOT/'verification/spatial_task_qualification_001'
OWNED = ROOT/'verification/m2_tight_directory_001/measurement/owned_native.py'
METER = OWNED.with_name('wire_meter.py')
PEER = ROOT/'verification/m1_task_entry_001_eval/actor.py'
RUNTIME = ROOT/'verification/m1_task_entry_001_eval/preflight_client.py'
BINDER = QUALIFICATION/'oracle/verify_actual.py'
BOOTSTRAP = ROOT/'verification/m2_tight_directory_001/measurement/analyze_saved.py'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,value):
    with Path(path).open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,allow_nan=False,indent=2)
        stream.write('\n')


def load(name,path):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(Path(path).read_bytes(),str(path),'exec',dont_inherit=True),module.__dict__)
    return module


def events(path):
    return [json.loads(line) for line in path.read_bytes().splitlines() if line] if path.exists() else []


def encoded(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf8')


def tool_request(label,query,rules):
    return {'jsonrpc':'2.0','id':label,'method':'tools/call','params':{
        'name':rules['tool'],'arguments':{'session_id':rules['session_id'],
        'include_image':False,'query':query}}}


def task_query(selector,names,rules,requested_facts=None):
    return {'mode':'task','target':{'id':names[selector['target']]},
        'candidates':[{'id':names[name]} for name in selector['candidates']],
        'requested_facts':list(rules['requested_facts'] if requested_facts is None else requested_facts)}


def witness_values(value,path=()):
    found = []
    if isinstance(value,dict):
        for key,item in value.items():
            if key in ('nearest_witness','local_evidence','best_known_evidence'):
                found.append({'path':list(path+(key,)),'value':item,'value_JSON_UTF8_bytes':len(encoded(item))})
            else:
                found.extend(witness_values(item,path+(key,)))
    elif isinstance(value,list):
        for index,item in enumerate(value):
            found.extend(witness_values(item,path+(index,)))
    return found


def call_business(peer,request,output):
    row = {'request':request,'started_ns':time.perf_counter_ns()}
    save(output/(request['id']+'_REQUEST.json'),request)
    try:
        row['started_ns'] = time.perf_counter_ns()
        response = peer.call(request)
        row['ended_ns'] = time.perf_counter_ns()
        row['response'] = response
        row['stdio'] = dict(peer.records[-1])
        row['tool_ns'] = row['ended_ns']-row['started_ns']
        row['classification'] = ('rpc_error' if 'error' in response else
            'tool_error' if response.get('result',{}).get('isError') else 'tool_response')
        content = response.get('result',{}).get('content',[])
        row['visible_text_UTF8_bytes'] = sum(len(block.get('text','').encode('utf8')) for block in content)
        assert all(block.get('type')=='text' for block in content),'unexpected_image_block'
        text = content[0].get('text','') if content else ''
        try: row['body'] = json.loads(text)
        except json.JSONDecodeError: row['body'] = None
        row['witness_fields'] = witness_values(row['body'])
        row['witness_bytes_scope'] = 'unescaped compact JSON value bytes; full actual escaped MCP response retained in stdio RX.bin'
    except BaseException as exc:
        row['ended_ns'] = time.perf_counter_ns()
        row['tool_ns'] = row['ended_ns']-row['started_ns']
        row['classification'] = 'transport_or_harness_exception'
        row['error'] = {'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
    save(output/(request['id']+'_RESULT.json'),row)
    return row


def verify_directory(body,snapshot):
    assert body['result_kind']=='scene_directory' and body['status']=='complete'
    assert body['unit']=='m' and body['coordinate_frame']=='world'
    actual = body['objects']
    assert len(actual)==len(snapshot['objects'])==14
    by_name = {row['name']:row for row in actual}
    assert len(by_name)==14 and len({row['object_id'] for row in actual})==14
    for source in snapshot['objects']:
        row = by_name[source['name']]
        assert row['object_id']==source['object_id']
        low = [min(point[axis] for point in source['vertices_world']) for axis in range(3)]
        high = [max(point[axis] for point in source['vertices_world']) for axis in range(3)]
        assert row['bbox_min']==low and row['bbox_max']==high
        assert row['center']==[(a+b)/2 for a,b in zip(low,high)]
    assert body['binding']['frame']==snapshot['frame']
    assert body['binding']['subframe']==snapshot['subframe']
    assert body['binding']['scale_length']==snapshot['scale_length']
    return {name:row['object_id'] for name,row in by_name.items()}


def prepare(output, expected_commit, expected_source):
    ready = json.loads(READY.read_bytes())
    manifest = json.loads((QUALIFICATION/'assets/DERIVED_MANIFEST.json').read_bytes())
    assert re.fullmatch(r'[0-9a-f]{40}', expected_commit)
    assert re.fullmatch(r'[0-9a-f]{64}', expected_source)
    assert ready['source_sha256']==expected_source
    assert ready['commit']==expected_commit and ready['source_count']==137
    assert ready['version']=='9.7.2+m3.sufficient.r1'
    assert sha(manifest['asset'])==manifest['asset_sha256']
    assert manifest['counts']=={'mesh_objects':14,'vertices':848,'triangles':1640}
    paths = [Path(__file__),HERE/'qa_snapshot.py',HERE/'QUERY_RULES.json',BINDER,
        QUALIFICATION/'assets/DERIVED_MANIFEST.json',QUALIFICATION/'assets/BUILD_SNAPSHOT.json',
        QUALIFICATION/'assets/ORIGINAL_EVALUATED.json',QUALIFICATION/'assets/build_asset.py',
        BATCH/'ROOT_PLAN.md',BATCH/'WORK_ORDER.json',QUALIFICATION/'INSTALLATION_BINDING.json',
        QUALIFICATION/'entry/run_entry.py',
        ROOT/'verification/scale_diag_001/fixtures/G508.json',ROOT/'verification/scale_diag_001/oracle.py',
        ROOT/'verification/scale_diag_001/ORACLE.json',READY,OWNED,METER,PEER,RUNTIME,BOOTSTRAP,
        HERE/'verify_saved.py',HERE/'witness_oracle.py',
        QUALIFICATION/'oracle/formal_replay_01/ORACLE.json',
        ROOT/'verification/native_plugin_complex_003/actor.py']
    source_files = {str(path.resolve()):sha(path) for path in paths}
    binding = {'schema':'m3-sufficient-separation-entry-binding-v1','ready':ready,'asset_manifest':manifest,
        'source_files':source_files,'business_observe_attempts':4,'QA_evaluated_snapshots':1,
        'owned_Blender_limit':1,'owned_product_Peer_limit':1,'new_models':0,'new_images':0,
        'status_semantics':'execution completion and business facts are separate; assembly unknown/error still followed by control'}
    output.mkdir(parents=True,exist_ok=False)
    save(output/'INPUT_BINDINGS.json',binding)
    return binding


def run(binding,output):
    for path,expected in binding['source_files'].items():
        assert sha(path)==expected,(path,'source_changed_before_execution')
    assert not (HERE/'FORMAL_STARTED.json').exists(),'formal_sequence_already_reserved'
    started = time.perf_counter_ns()
    save(HERE/'FORMAL_STARTED.json',{'started_ns':started,'output':str(output),
        'input_bindings_sha256':sha(output/'INPUT_BINDINGS.json'),'formal_sessions_limit':1})
    native = peer = None
    runtime_handle = None
    helper = load('_stq_owned',OWNED)
    actor = load('_stq_peer',PEER)
    runtime = load('_stq_runtime_proof',RUNTIME)
    binder = load('_stq_independent_binding',BINDER)
    bootstrap = load('_stq_source_bytes',BOOTSTRAP).bootstrap
    rules = json.loads((HERE/'QUERY_RULES.json').read_bytes())
    ready,asset = binding['ready'],binding['asset_manifest']
    result = {'started_ns':started,'business':[],'errors':[],'timing_stages_ns':{},
              'qualification_status':'execution_incomplete','planned_business_attempts':4}
    try:
        mark = time.perf_counter_ns()
        native = helper.NativeSession.start(blender='D:/Tools/blender5.2/blender.exe',asset=asset['asset'],
            workspace=output/'native',deadline_ns=started+570*10**9,condition='P',
            expected_asset_sha256=asset['asset_sha256'],max_calls=128)
        result['timing_stages_ns']['native_start'] = time.perf_counter_ns()-mark
        config = {'schema_version':'1.0','enabled':True,'observe_on_prompt':False,
            'project_root':ready['install_root'],'state_file':str(output/'state.json'),
            'audit_file':str(output/'audit.jsonl'),'request_budget_s':30.,
            'expected_identity':{'source_sha256':ready['source_sha256']},
            'blender':{'host':native.host,'port':native.port,'timeout_s':30.}}
        save(output/'config.json',config)
        mark = time.perf_counter_ns()
        peer = actor.Peer(dict(ready,group='C',product_config=output/'config.json'),output/'product')
        initialized = peer.call({'jsonrpc':'2.0','id':'init','method':'initialize','params':{
            'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'spatial-task-qualification','version':'001'}}})
        save(output/'INITIALIZE.json',initialized)
        identity = initialized['result']['_meta']['human_eye']
        assert identity['source_sha256']==ready['source_sha256'] and identity['source_kind']=='installed_distribution'
        peer.call({'jsonrpc':'2.0','method':'notifications/initialized'})
        save(output/'TOOLS.json',peer.call({'jsonrpc':'2.0','id':'list','method':'tools/list'}))
        assert peer.call({'jsonrpc':'2.0','id':'ping','method':'ping'})['result']=={}
        assert events(native.workspace/'WORKER_EVENTS.jsonl')==[]
        result['metadata_zero_host_RPC_confirmed'] = True
        result['timing_stages_ns']['product_start_and_metadata'] = time.perf_counter_ns()-mark
        pids = {row['pid'] for row in events(output/'audit.jsonl') if row.get('event')=='request_trace'}
        assert len(pids)==1
        proof,runtime_handle = runtime._windows_runtime_proof(peer.process,pids.pop(),started+570*10**9)
        proof['before_stdin'] = False
        proof['scope'] = 'after zero-host-RPC metadata and before QA snapshot/business'
        result['product_runtime_proof'] = proof
        save(output/'PRODUCT_RUNTIME_PROOF.json',proof)
        assert proof['confirmed'] is True
        mark = time.perf_counter_ns()
        snapshot_code = (HERE/'qa_snapshot.py').read_text(encoding='utf8')
        snapshot_receipt = native.run(snapshot_code,timeout_s=30)
        result['QA_snapshot'] = {'started_ns':mark,'ended_ns':time.perf_counter_ns(),'receipt':snapshot_receipt,
                                'execute_code_UTF8_bytes':len(snapshot_code.encode('utf8'))}
        result['timing_stages_ns']['QA_evaluated_snapshot'] = time.perf_counter_ns()-mark
        save(output/'QA_SNAPSHOT_RECEIPT.json',snapshot_receipt)
        assert snapshot_receipt['response']['status']=='success',snapshot_receipt
        snapshot = json.loads(snapshot_receipt['response']['result']['result'])
        save(output/'ACTUAL_SNAPSHOT.json',snapshot)
        mark = time.perf_counter_ns()
        source_binding = binder.bind_actual(snapshot)
        result['timing_stages_ns']['independent_exact_source_binding'] = time.perf_counter_ns()-mark
        result['actual_source_binding'] = source_binding
        save(output/'ACTUAL_SOURCE_BINDING.json',source_binding)
        assert source_binding['passed'] is True,source_binding
        directory = call_business(peer,tool_request('directory',rules['directory_query'],rules),output)
        result['business'].append(directory)
        assert directory['classification']=='tool_response' and isinstance(directory['body'],dict),'directory_unavailable'
        names = verify_directory(directory['body'],snapshot)
        save(output/'DIRECTORY_NAME_ID_BINDING.json',names)
        for label,selector,facts in (('spatial_assembly_task',rules['assembly'],rules['requested_facts']),
                ('legacy_assembly_task',rules['assembly'],rules['legacy_requested_facts']),
                ('spatial_control_task',rules['control'],rules['requested_facts'])):
            # Preserve product unknowns and public errors, then continue control.
            result['business'].append(call_business(peer,tool_request(label,task_query(selector,names,rules,facts),rules),output))
        result['qualification_status'] = 'recorded_for_independent_business_verification'
    except BaseException as exc:
        result['errors'].append({'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()})
    finally:
        mark = time.perf_counter_ns()
        if peer is not None:
            try: result['product_close'] = peer.close()
            except BaseException as exc: result['errors'].append({'stage':'product_close','error':repr(exc)})
            try:
                result['product_runtime_exit'] = runtime._runtime_exit(runtime_handle)
                assert result['product_runtime_exit']['confirmed'] is True and result['product_runtime_exit']['exit_code']==0
                assert result['product_runtime_exit']['exited'] is True and result['product_runtime_exit']['handle_closed'] is True
            except BaseException as exc: result['errors'].append({'stage':'product_runtime_exit','error':repr(exc)})
        if native is not None:
            try:
                result['native_close'] = native.close()
                result['closed'] = native.status()['closed']
                assert result['native_close']['error'] is None and result['native_close']['response']['status']=='closed'
                assert result['native_close']['process_reaped'] and result['native_close']['exit_code']==0
                assert not result['closed']['poisoned']
                assert result['closed']['initial_geometry_fingerprint']==result['closed']['final_geometry_fingerprint']
                result['worker_events'] = events(native.workspace/'WORKER_EVENTS.jsonl')
                result['wire'] = json.loads((native.workspace/'WIRE/INDEX.json').read_bytes())
                for event in result['worker_events']:
                    assert event.get('event') not in ('render_started','render_completed','render_cancelled')
                    assert not event.get('changed_or_new_PNG_files')
                    if 'render_events_after' in event:
                        assert event['render_events_after']==event['render_events_before']
                windows = result['business'] + ([result['QA_snapshot']] if 'QA_snapshot' in result else [])
                for row in windows:
                    observed = [event for event in result['worker_events'] if type(event.get('started_ns')) is int
                        and row['started_ns']<=event['started_ns']<=row['ended_ns']]
                    row['host_RPC'] = len(observed)
                    row['work_events'] = observed
                    row['wire'] = [record for record in result['wire'] if record['sequence'] in {event['sequence'] for event in observed}]
                    row['bridge_request_bytes'] = sum(part['request_bytes'] for part in row['wire'])
                    row['bridge_response_bytes'] = sum(part['response_attempted_bytes'] for part in row['wire'])
                    row['bridge_sum_bytes'] = row['bridge_request_bytes']+row['bridge_response_bytes']
                    row['compressed_source_establishment'] = [bootstrap(native.workspace/'WIRE'/str(part['sequence']).zfill(3)/'REQUEST.bin')
                        for part in row['wire']]
                result['all_actual_host_RPC_including_QA_and_close'] = len(result['wire'])
                for part in result['wire']:
                    try:
                        part['request_type'] = json.loads((native.workspace/'WIRE'/str(part['sequence']).zfill(3)/'REQUEST.bin').read_bytes()).get('type')
                    except (ValueError,TypeError):
                        part['request_type'] = 'unknown'
                metadata = [row for row in peer.records if row['method']!='tools/call'] if peer is not None else []
                result['scope_counts'] = {'metadata_stdio_messages':len(metadata),
                    'metadata_response_messages':sum(row['request_id'] is not None for row in metadata),
                    'metadata_host_RPC':0 if result.get('metadata_zero_host_RPC_confirmed') else None,
                    'QA_snapshot_host_RPC':result.get('QA_snapshot',{}).get('host_RPC'),
                    'business_observe_attempts':len(result['business']),
                    'business_received_responses':sum('response' in row for row in result['business']),
                    'business_host_RPC':sum(row['host_RPC'] for row in result['business']),
                    'close_host_RPC':sum(part['request_type']=='close' for part in result['wire'])}
            except BaseException as exc: result['errors'].append({'stage':'native_close_or_meter','error':repr(exc)})
        result['timing_stages_ns']['close_and_meter_publication'] = time.perf_counter_ns()-mark
        result['audit'] = events(output/'audit.jsonl')
        for row in result['business']:
            row['traces'] = [event for event in result['audit'] if event.get('event')=='request_trace'
                and event['trace']['annotations'].get('mcp_request_id')==row['request']['id']]
        result['source_files_unchanged'] = all(sha(path)==expected for path,expected in binding['source_files'].items())
        result['ended_ns'] = time.perf_counter_ns()
        result['session_wall_ns'] = result['ended_ns']-started
        result['harness_execution_complete'] = (len(result['business'])==4
            and all('response' in row and row['classification']!='transport_or_harness_exception' for row in result['business'])
            and not result['errors'] and result['source_files_unchanged'])
        result['business_passed'] = None
        result['business_passed_scope'] = 'independent oracle verification required; harness completion cannot turn unknown into business success'
        save(output/'RESULTS.json',result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--commit',required=True)
    parser.add_argument('--source-sha256',required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    binding = prepare(output,args.commit,args.source_sha256)
    if not args.run:
        print(json.dumps({'prepared_only':True,'binding':str(output/'INPUT_BINDINGS.json')}))
        return 0
    result = run(binding,output)
    print(json.dumps({'harness_execution_complete':result['harness_execution_complete'],
                      'qualification_status':result['qualification_status'],'business_passed':None}))
    return 0 if result['harness_execution_complete'] else 1


if __name__=='__main__':
    raise SystemExit(main())

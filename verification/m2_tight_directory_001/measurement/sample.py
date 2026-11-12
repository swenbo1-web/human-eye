"""One fixed owned directory or continuous two-step sample, without profiling."""
import hashlib
import json
from pathlib import Path
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
exec(compile((HERE/'probe.py').read_bytes(), str(HERE/'probe.py'), 'exec'),
     common := {'__name__': '_m2_baseline_reuse', '__file__': str(HERE/'probe.py')})
save, load, rows, request = [common[key] for key in ('save','load','rows','request')]


def native_code(first):
    setup = ''
    if first:
        for path in (HERE/'reused/scene_residency.py', HERE/'native_directory.py'):
            setup += 'exec(compile(' + repr(path.read_text(encoding='utf8')) + ',' + repr(path.name) + ",'exec'),globals())\n"
    return setup + "print(json.dumps(_m2_native_directory(),ensure_ascii=False,separators=(',',':'),allow_nan=False))"


def verify_directory(body, lane, asset):
    actual = common['directory_facts'](body, 'overview' if lane=='old' else 'directory')
    expected = {row['name']: row for row in asset['oracle']}
    assert len(actual) == len(expected) and {row['name'] for row in actual} == set(expected)
    for item in actual:
        for key in ('bbox_min','bbox_max','center'):
            assert item[key] == expected[item['name']][key], (item['name'], key, item[key], expected[item['name']][key])
        identity = json.dumps(['',item['name']], sort_keys=True, separators=(',',':'),
                              ensure_ascii=False, allow_nan=False).encode('utf8')
        assert item['object_id'] == 'blender:' + hashlib.sha256(identity).hexdigest()
    return actual


def run(asset, ready, output, lane, *, two_step=False, warm_count=10):
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter_ns()
    result = {'asset': asset['name'], 'lane': lane, 'two_step': two_step, 'rows': [],
              'errors': [], 'started_ns': started, 'timing_stages_ns': {}}
    native = peer = None
    runtime_handle = None
    helper = load('_m2_sample_owned', HERE/'owned_native.py')
    actor = load('_m2_sample_peer', common['ACTOR'])
    client = load('_m2_runtime_proof', ROOT/'verification/m1_task_entry_001_eval/preflight_client.py')
    try:
        mark = time.perf_counter_ns()
        native = helper.NativeSession.start(blender='D:/Tools/blender5.2/blender.exe', asset=asset['asset'],
            workspace=output/'native', deadline_ns=started+570*10**9, condition='P',
            expected_asset_sha256=asset['asset_sha256'], max_calls=128)
        result['timing_stages_ns']['native_start'] = time.perf_counter_ns()-mark
        if lane != 'native' or two_step:
            mark = time.perf_counter_ns()
            config = {'schema_version':'1.0','enabled':True,'observe_on_prompt':False,
                'project_root':ready['install_root'],'state_file':str(output/'state.json'),
                'audit_file':str(output/'audit.jsonl'),'request_budget_s':30.,
                'expected_identity':{'source_sha256':ready['source_sha256']},
                'blender':{'host':native.host,'port':native.port,'timeout_s':30.}}
            save(output/'config.json',config)
            peer = actor.Peer(dict(ready,group='C',product_config=output/'config.json'),output/'product')
            initialized = peer.call({'jsonrpc':'2.0','id':'init','method':'initialize','params':{
                'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'m2-directory','version':'001'}}})
            identity = initialized['result']['_meta']['human_eye']
            assert identity['source_sha256']==ready['source_sha256'] and identity['source_kind']=='installed_distribution'
            save(output/'ACTUAL_INITIALIZE.json',initialized)
            peer.call({'jsonrpc':'2.0','method':'notifications/initialized'})
            save(output/'ACTUAL_TOOLS.json',peer.call({'jsonrpc':'2.0','id':'list','method':'tools/list'}))
            assert peer.call({'jsonrpc':'2.0','id':'ping','method':'ping'})['result']=={}
            result['timing_stages_ns']['product_start_and_metadata'] = time.perf_counter_ns()-mark
            assert rows(native.workspace/'WORKER_EVENTS.jsonl')==[]
            pids = {row['pid'] for row in rows(output/'audit.jsonl') if row.get('event')=='request_trace'}
            assert len(pids)==1
            proof,runtime_handle = client._windows_runtime_proof(peer.process,pids.pop(),started+570*10**9)
            # These metadata messages precede proof, with zero host RPCs.
            proof['before_stdin'] = False
            proof['scope'] = 'after metadata and before business; metadata made zero host RPCs'
            result['product_runtime_proof'] = proof
            save(output/'PRODUCT_RUNTIME_PROOF.json',proof)
            assert proof['confirmed'] is True
        result['timing_stages_ns']['setup_before_first_request'] = time.perf_counter_ns()-started
        count = 2 if two_step else warm_count+1
        combined_started = time.perf_counter_ns()
        for index in range(count):
            selected = two_step and index==1
            row = {'index':index,'phase':'selected' if selected else 'cold' if index==0 else 'warm'}
            result['rows'].append(row)
            if lane=='native' and not selected:
                code = native_code(index==0)
                (output/('REQUEST_'+str(index)+'.py')).write_text(code,encoding='utf8',newline='\n')
                began = time.perf_counter_ns()
                answer = native.run(code,timeout_s=30)
                ended = time.perf_counter_ns()
                row.update(request_kind='original_native_execute_code',code_UTF8_bytes=len(code.encode('utf8')),
                           response=answer,started_ns=began,ended_ns=ended,tool_ns=ended-began,
                           tool_scope='original NativeSession.run request through complete receipt and existing source checks')
                assert answer['response']['status']=='success',answer
                body = None if two_step else json.loads(answer['response']['result']['result'])
                row['visible_text_UTF8_bytes'] = len(answer['response']['result']['result'].encode('utf8'))
            else:
                mode = 'task' if selected else 'overview' if lane=='old' else 'directory'
                message = request(mode,'read_'+str(index))
                began = time.perf_counter_ns()
                answer = peer.call(message)
                ended = time.perf_counter_ns()
                row.update(request_kind='actual_product_MCP_stdio',request=message,response=answer,
                           started_ns=began,ended_ns=ended,tool_ns=ended-began,stdio=dict(peer.records[-1]),
                           tool_scope='Peer complete MCP request through complete receipt; broader than service trace')
                assert answer['result']['isError'] is False,answer
                assert all(block['type']=='text' for block in answer['result']['content'])
                body = None if two_step else json.loads(answer['result']['content'][0]['text'])
                row['visible_text_UTF8_bytes'] = sum(len(block['text'].encode('utf8')) for block in answer['result']['content'])
            if two_step:
                continue
            row['body'] = body
            verify_started = time.perf_counter_ns()
            if not selected:
                row['directory_facts'] = verify_directory(body,lane,asset)
            row['verification_ns'] = time.perf_counter_ns()-verify_started
            row['request_with_checks_ns'] = time.perf_counter_ns()-began
            save(output/('READ_'+str(index)+'.json'),row)
        result['continuous_request_window_ns'] = result['rows'][-1]['ended_ns']-result['rows'][0]['started_ns']
        result['continuous_scope'] = 'first request start through last complete receipt; two-step fact verification/publication deferred'
        if two_step:
            for row in result['rows']:
                answer = row['response']
                text = (answer['response']['result']['result'] if row['request_kind']=='original_native_execute_code'
                        else answer['result']['content'][0]['text'])
                row['body'] = json.loads(text)
                mark = time.perf_counter_ns()
                if row['index']==0:
                    row['directory_facts'] = verify_directory(row['body'],lane,asset)
                row['verification_ns'] = time.perf_counter_ns()-mark
                save(output/('READ_'+str(row['index'])+'.json'),row)
        result['continuous_business_with_checks_and_recording_ns'] = time.perf_counter_ns()-combined_started
    except BaseException as exc:
        result['errors'].append({'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()})
    finally:
        mark = time.perf_counter_ns()
        if peer is not None:
            try: result['product_close'] = peer.close()
            except BaseException as exc: result['errors'].append({'stage':'product_close','error':repr(exc)})
            try:
                result['product_runtime_exit'] = client._runtime_exit(runtime_handle)
                assert result['product_runtime_exit']['confirmed'] is True
                assert result['product_runtime_exit']['exit_code']==0
            except BaseException as exc: result['errors'].append({'stage':'runtime_exit','error':repr(exc)})
        if native is not None:
            try:
                result['native_close'] = native.close()
                result['closed'] = native.status()['closed']
                assert result['native_close']['error'] is None and result['native_close']['response']['status']=='closed'
                assert result['native_close']['exit_code']==0 and result['native_close']['process_reaped']
                assert not result['closed']['poisoned']
                assert result['closed']['final_geometry_fingerprint']==result['closed']['initial_geometry_fingerprint']
                result['worker_events'] = rows(native.workspace/'WORKER_EVENTS.jsonl')
                result['wire'] = json.loads((native.workspace/'WIRE/INDEX.json').read_bytes())
                for event in result['worker_events']:
                    assert event.get('event') not in ('render_started','render_completed','render_cancelled')
                    assert not event.get('changed_or_new_PNG_files')
                    if 'render_events_after' in event:
                        assert event['render_events_before']==event['render_events_after']
                for row in result['rows']:
                    if 'ended_ns' not in row:
                        continue
                    events = [event for event in result['worker_events'] if type(event.get('started_ns')) is int
                              and row['started_ns']<=event['started_ns']<=row['ended_ns']]
                    row['host_RPC'] = len(events)
                    row['work_events'] = events
                    row['wire'] = [record for record in result['wire'] if record['sequence'] in {event['sequence'] for event in events}]
                    assert row['host_RPC']>=1
                    assert all(record['response_sendall_completed'] for record in row['wire'])
            except BaseException as exc: result['errors'].append({'stage':'native_close_or_meter','error':repr(exc)})
        result['timing_stages_ns']['close_and_meter_publish'] = time.perf_counter_ns()-mark
        result['audit'] = rows(output/'audit.jsonl')
        for row in result['rows']:
            request_id = row.get('request',{}).get('id')
            row['service_traces'] = [event for event in result['audit'] if event.get('event')=='request_trace'
                and event['trace']['annotations'].get('mcp_request_id')==request_id] if request_id else []
        result['ended_ns'] = time.perf_counter_ns()
        result['session_wall_ns'] = result['ended_ns']-started
        result['passed'] = not result['errors']
        result['memory_scope'] = 'existing product request_trace process-lifetime peak; native OS/Python peak unmeasured'
        save(output/'RESULTS.json',result)
    return result

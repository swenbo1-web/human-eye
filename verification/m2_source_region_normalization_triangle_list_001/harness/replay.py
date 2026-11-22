"""Run the installed production stdio server against pinned complete captures."""

import argparse
import base64
from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path
import sys
import time


HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from inputs import (BASE_GIT, CATALOGUE, FIXTURES, GLOBAL_INPUTS, PRIOR, PRIOR_INPUTS, RUN,
                    SEAL, V, digest, pin, read, require, sealed_inputs, verify_geometry, write)


ENTRY = V/'m4_region_task_global_first_frame_001/harness/replay.py'
CLI_PATH = V/'m1_region_task_first_packet_consumption_holdout_001/checks/evidence.py'
FORMAL_ROLES = {**dict.fromkeys(('N1','P1','P2','N2','N3','P3'),'main'),
                'HN':'holdout','HP':'holdout','RN':'rectangle','RP':'rectangle','DN':'dual','DP':'dual'}
BASELINE_LABELS = ('N1','N2','N3','HN','RN','DN','CN','FN')


def source_paths():
    return (Path(__file__),HERE/'inputs.py',HERE/'defaults.py',PRIOR_INPUTS,GLOBAL_INPUTS,ENTRY,CLI_PATH,
            PRIOR/'harness/mcp_entry.py',
            PRIOR/'harness/runtime.py',PRIOR/'harness/common.py',PRIOR/'harness/budget.py',
            PRIOR/'harness/admission.py',CATALOGUE,SEAL/'SHARED_DEPENDENCY.json',
            V/'m1_region_task_first_packet_consumption_holdout_recovery_001/harness/runtime.py',
            V/'m4_live_source_region_task_003/harness/mcp_entry.py',
            V/'m4_live_source_region_task_003/harness/reused/verified_bootstrap.py',
            V/'m4_source_region_display_001/harness/reused/stdio_checks.py',
            V/'m4_cross_scale_live_qualification_001/checks/delivery.py')


def retained():
    roots = sys.path[:]
    try:
        return run_path(str(ENTRY))
    finally:
        sys.path[:] = roots


def replay_plan(fixture, controls):
    first,*later = fixture['calls']
    if fixture['name']=='defaults':
        return fixture['calls'],fixture['capture_plan']
    full,repeat = fixture['deltas']
    if controls:
        lower = later[0]
        stale = deepcopy(lower)
        stale['id'] = 'stale_current_source_region_ref'
        query = stale['params']['arguments']['query']
        del query['region']
        query['region_ref'] = fixture['producer']['region_ref']
        changed = deepcopy(repeat)
        changed['capture']['capture_state']['revision'] += 1
        changed['capture']['revision'] += ':normalization-replay-new-generation-control'
        recovery = {**lower,'id':'fresh_explicit_after_stale_reference'}
        return [lower,stale,recovery],[full,changed,changed]
    if fixture['name'] in ('rectangle','dual'):
        return [first,later[0]],[full,repeat]
    requests,deltas = [first,{**first,'id':'warm_original_selection'}],[full,repeat]
    if fixture['name']=='main':
        requests.append(later[0])
        deltas.append(repeat)
    return requests,deltas


def capture_plan(source,controls):
    _,deltas = replay_plan(source,controls)
    if source['name']=='defaults':
        return deltas
    return [(delta,{'command':'capture','params':{}},source['terminal']) for delta in deltas]


def worker(root,binding_path,fixture_name,controls):
    original = retained()
    sys.path.insert(0,str(PRIOR/'harness'))
    import mcp_entry

    source = sealed_inputs(fixture_name)
    binding = read(binding_path)
    mcp_entry.SOURCE_SHA = binding['source_sha256']
    config = root/'PRODUCT_CONFIG.json'
    write(config,{'schema_version':'1.0','enabled':True,'observe_on_prompt':False,
                  'project_root':binding['install_root'],'state_file':str(root/'product_state.json'),
                  'audit_file':str(root/'product_audit.jsonl'),'request_budget_s':30,
                  'expected_identity':{'source_sha256':binding['source_sha256']}})
    pending = capture_plan(source,controls)
    calls,restore = [],[]

    def setup(verified):
        require(verified==binding,'replay_worker_not_using_registered_install')
        from human_eye_plugin import live_service
        from human_eye_plugin.blender_mcp_host import BlenderMCPHost

        def no_live(event,args):
            if event in ('socket.connect','subprocess.Popen','os.system','os.spawn','os.exec'):
                raise AssertionError('archived_replay_cannot_launch_Blender_or_connect')
        sys.addaudithook(no_live)

        class ArchivedHost(BlenderMCPHost):
            def _request(self,command,params):
                index = len(calls)
                require(index<len(pending),'unexpected_replay_capture_request')
                delta, historical, _ = pending[index]
                if command=='capture_active_observation':
                    require(type(params.get('deadline_ns')) is int and params['deadline_ns']>time.perf_counter_ns(),
                            'actual_target_deadline_not_bound_to_current_rpc')
                require(command==historical['command']
                        and {k:v for k,v in params.items() if k!='deadline_ns'}==
                            {k:v for k,v in historical['params'].items() if k!='deadline_ns'},
                        'current_capture_command_or_selectors_changed/'+str(index))
                self._ensure_live()
                start = time.perf_counter_ns()
                current = self._scene_decoder.apply(deepcopy(delta))
                ready = time.perf_counter_ns()
                self._record_observation_document(current)
                capture = root/f'CAPTURE_{index+1:02d}.json'
                # Keep large proof-file formatting and writes outside request
                # clocks. The decoder and host document recording above are real.
                calls.append({'command':command,'params':params,'resource_count':len(delta['resources']),
                              'decode_elapsed_ns':ready-start,'capture_state':current['capture_state'],
                              'capture_file':str(capture),'payload':current})
                return current

        host = ArchivedHost(binding['install_root'])
        service = live_service.LiveSpatialService
        restore.append(lambda: setattr(live_service,'LiveSpatialService',service))

        class ReplayService(service):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,host=host,**kwargs)

        live_service.LiveSpatialService = ReplayService

    argv = argparse.Namespace(binding=binding_path,config=config,ledger=root/'budget',evidence=root/'mcp_io',
                              archive=root/'product_full',phase='qualification',label='QP',
                              region_task_evidence=True,_offline_capture_setup=setup)
    started = time.perf_counter_ns()
    try:
        return mcp_entry.worker(argv)
    finally:
        closed = time.perf_counter_ns()
        memory = original['peak_memory']()
        for undo in restore:
            undo()
        for call in calls:
            write(call['capture_file'],call.pop('payload'))
        write(root/'REPLAY_CLOSE.json',{'calls':calls,'source_pins':source['source_pins'],
            'old_sources_unchanged':all(pin(row['path'])==row for row in source['source_pins']),
            'worker_started_ns':started,'worker_closed_ns':closed,'worker_window_ns':closed-started,
            'memory':memory,'actual_Blender_starts':0,'actual_models':0})


def frame_receipts(slot,producer):
    output = []
    for frame in producer.get('constructed_frames',producer['frames']):
        png,npz = [Path(frame[key]).resolve(strict=True) for key in ('image_path','arrays_path')]
        require(png.is_relative_to(slot) and npz.is_relative_to(slot),'frame_paths_outside_new_owned_root')
        p,a = pin(png),pin(npz)
        require(p['sha256']==frame['image_sha256'] and a['sha256']==frame['arrays_sha256'],
                'current_frame_artifact_hash_changed')
        output.append({'view_name':frame['view_name'],'png':p,'arrays':a})
    return output


def run(root,binding_path,fixture_name,controls,preflight):
    binding = read(binding_path)
    base = binding['preparation_git']==BASE_GIT
    require(len(binding['source_manifest'])==143,'installed_source_manifest_count_changed')
    if preflight:
        require(base and root.is_relative_to(RUN/'preflight'),'preflight_only_under_new_root_with_baseline')
    elif fixture_name=='defaults':
        require(root.parent==RUN/'controls' and root.name in ('FN','FP') and (root.name=='FN')==base,
                'unexpected_default_control_arm')
    elif controls:
        require(root.parent==RUN/'controls' and root.name in ('CN','CP') and (root.name=='CN')==base,
                'unexpected_generation_control_arm')
    else:
        require(root.parent==RUN/'arms' and FORMAL_ROLES.get(root.name)==fixture_name
                and (root.name in BASELINE_LABELS)==base,'unexpected_formal_arm')
    require(not controls or fixture_name=='main','generation_controls_require_full_main_capture')
    root.mkdir(parents=True,exist_ok=False)
    fixed = sealed_inputs(fixture_name)
    original = retained()
    sys.path[:0] = [binding['dependency_root'],read(SEAL/'SHARED_DEPENDENCY.json')['dependency_root'],
                    str(PRIOR/'harness')]
    from runtime import ProductionStdioClient
    ProductionStdioClient.finish.__globals__['SOURCE_SHA'] = binding['source_sha256']
    requests,_ = replay_plan(fixed,controls)
    args = [sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),'--worker',str(root),
            '--fixture',fixture_name,'--binding',str(binding_path)]
    if controls:
        args.append('--controls')
    replies = []
    started = time.perf_counter_ns()
    client = ProductionStdioClient(args,root,root/'mcp',started+120_000_000_000,worker_evidence=root/'mcp_io')
    try:
        identity = client.call(original['INIT'])['result']['_meta']['human_eye']
        client.call(original['NOTIFY'])
        tools = client.call(original['LIST'])['result']['tools']
        require(identity['source_sha256']==binding['source_sha256'] and identity['source_kind']=='installed_distribution'
                and tools==read(CATALOGUE),'actual_production_install_or_tools_catalogue_changed')
        for index,request in enumerate(requests):
            reply = client.call(request)
            require(reply.get('error') is None and reply['result']['isError'] is (controls and index==1)
                    and reply['result']['content'][0]['type']=='text','unexpected_current_response_status/'+str(request['id']))
            replies.append(reply)
        last_response = time.perf_counter_ns()
    finally:
        close = client.finish()
        closed = time.perf_counter_ns()
    return verify_replay(root,binding,fixed,controls,preflight,close,replies,client.records[3:],
                         started,last_response,closed)


def verify_replay(root,binding,fixed,controls,preflight,close,replies,receipts,started,last_response,closed,
                  replayed_receipts=False):
    fixture_name = fixed['name']
    original = retained()
    requests,_ = replay_plan(fixed,controls)
    captures = capture_plan(fixed,controls)
    require(close['confirmed'] is True and close['exit_code']==0 and close['production_eof_and_exit_verified']
            and close['process_handle_closed'],'actual_held_process_close_unconfirmed')
    for item in ('worker_eof','worker_exit'):
        proof = close[item]
        require(pin(proof['path'])['sha256']==proof['sha256'],'held_exit_proof_changed/'+item)
    worker_close = read(root/'REPLAY_CLOSE.json')
    require(worker_close['old_sources_unchanged'] and len(worker_close['calls'])==len(captures)
            and [row['resource_count'] for row in worker_close['calls']]==[len(row[0]['resources']) for row in captures],
            'current_replay_capture_count_or_source_protection_failed')
    for index,call in enumerate(worker_close['calls'],1):
        decoded = read(root/f'CAPTURE_{index:02d}.json')
        delta,_,terminal = captures[index-1]
        verify_geometry(decoded,terminal)
        require(decoded['capture_state']==call['capture_state']==delta['capture']['capture_state']
                and decoded.get('display_snapshot')==delta['capture'].get('display_snapshot')
                and decoded.get('observation_target')==delta['capture'].get('observation_target'),
                'current_replay_capture_state_or_display_changed')
    defaults = fixture_name=='defaults'
    frames_per_request = [[] for _ in requests]
    history_per_request = fixed['frames_by_call'] if defaults else ([fixed.get('frames',[]), *[[] for _ in requests[1:]]]
                                                                  if not controls else [[] for _ in requests])
    for n,historical in enumerate(history_per_request):
        if not historical:
            continue
        frames = frame_receipts(root,read(root/'product_full'/f'call_{n+1:03d}'/'SERVICE_RESULT.json'))
        require(all(a['view_name']==b['view_name']
                    and all({k:a[field][k] for k in ('bytes','sha256')}==b[field] for field in ('png','arrays'))
                    for a,b in zip(frames,historical,strict=True)), 'current_view_roster_or_original_PNG_NPZ_changed')
        frames_per_request[n] = frames
    frames = [f for row in frames_per_request for f in row]
    history = [f for row in history_per_request for f in row]
    fixed_cli = run_path(str(CLI_PATH))['fixed_cli']
    worker_wire = [row for line in (root/'mcp_io/MCP_IO.jsonl').read_bytes().splitlines()
                   if (row:=json.loads(line))['method']=='tools/call']
    checks = []
    for index,(request,reply,receipt,w) in enumerate(zip(requests,replies,receipts,worker_wire,strict=True),1):
        content = reply['result']['content']
        body = json.loads(content[0]['text'])
        error = controls and index==2
        p = root/'product_full'/f'call_{index:03d}'/'SERVICE_RESULT.json'
        producer = None if error else read(p)
        pngs = [base64.b64decode(row['data'],validate=True) for row in content if row['type']=='image']
        raster = 0 if error else producer['work']['raster_attempts']
        require(raster==len(frames_per_request[index-1])==w['raster_actual'],
                'cold_or_warm_raster_budget_changed')
        if error:
            require(not p.exists() and not pngs and body['error']=='source_region_ref_capture_generation_changed',
                    'stale_source_reference_wrong_error_or_altered_state')
            require(body['execution_status']=='not_executed' and body['executed'] is False
                    and body['connector_state_write_attempted'] is False and body['host_mutation_started'] is False,
                    'stale_reference_has_execution_or_write_evidence')
        else:
            require(pngs==[Path(f['image_path']).read_bytes() for f in producer['frames']],
                    'published_image_bytes_not_own_producer')
            if pngs and not defaults:
                local_path = Path(body['images'][0]['local_image_path']).resolve(strict=True)
                require(local_path.is_relative_to(root) and local_path==Path(producer['frames'][0]['image_path']).resolve()
                        and local_path.read_bytes()==pngs[0],'closed_slot_png_path_not_bound_to_own_original')
        work = {} if error else producer['work']
        cli = ({'passed':True,'expected_mcp_error':body['error'],'stages':[],
                'original_text_bytes':len(content[0]['text'].encode())}
               if error else fixed_cli(reply,require_all=not defaults))
        checks.append({'index':index,'text_bytes':sum(len(row['text'].encode()) for row in content if row['type']=='text'),
                       'raster_attempts':raster,'wire':original['bound_wire'](root,request,receipt,w),
                       'CLI':cli,'PNG_bytes':sum(map(len,pngs)),
                       'result_cache_hit':work.get('task_query',{}).get('result_cache_hit',False),
                       'stages':{} if error else producer['stages'],'work':work,'is_error':error,
                       'producer':None if error else pin(p),
                       'capture_resource_count':worker_close['calls'][index-1]['resource_count']})
    if controls:
        require([row['is_error'] for row in checks]==[False,True,False]
                and all(row['PNG_bytes']==row['raster_attempts']==0 and not row['result_cache_hit'] for row in checks),
                'stale_reference_or_no_image_recovery_accounting_changed')
    elif fixture_name=='dual':
        for row,reference in zip(checks,fixed['producers'],strict=True):
            p = read(row['producer']['path'])
            require(not row['result_cache_hit'] and row['PNG_bytes']==row['raster_attempts']==0
                    and row['stages']['region_preparation']['geometry_normalization']['elapsed_ns']>0
                    and p['region_ref']==reference['region_ref']
                    and p['task_result']['facts']==reference['task_result']['facts'],
                    'dual_requests_did_not_both_normalize_or_original_measurement_changed')
    elif not defaults:
        require(checks[1]['result_cache_hit'] is True and checks[1]['work']['frame_reuses']==1,
                'original_same_capture_warm_cache_not_hit')
    write(root/'SUMMARY.json',{'passed':True,'arm':root.name,'fixture':fixture_name,'preflight':preflight,
              'controls':controls,'default_controls':defaults,
              'derived_offline_review':replayed_receipts,
              'product':{k:binding[k] for k in ('preparation_git','source_sha256','wheel_sha256')},
              'source_dimensions':fixed['source_dimensions'],
              'source_pins':[pin(p) for p in source_paths()]+fixed['source_pins'],
              'original_native_transport':fixed['transport'],'actual_Blender_starts':0,'actual_models':0,
              'requests':checks,'construct_frames':frames,'historical_frames':history,
              'constructed_frames_by_request':frames_per_request,'historical_frames_by_request':history_per_request,
              'held_close':pin(root/'mcp/HELD_CLOSE.json'),'closure':close,
              'resource_count':[row['resource_count'] for row in worker_close['calls']],
              'whole_window_ns':closed-started,'through_last_response_ns':last_response-started,
              'worker_window_ns':worker_close['worker_window_ns'],'memory':worker_close['memory']})
    print('Passed',root.name,fixture_name,'calls',len(checks),'rasters',sum(row['raster_attempts'] for row in checks),flush=True)


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_interpreter_required')
    cli = argparse.ArgumentParser(description=__doc__)
    choice = cli.add_mutually_exclusive_group(required=True)
    choice.add_argument('--output',type=Path)
    choice.add_argument('--worker',type=Path)
    cli.add_argument('--fixture',choices=tuple(FIXTURES),required=True)
    cli.add_argument('--binding',type=Path,required=True)
    cli.add_argument('--preflight',action='store_true')
    cli.add_argument('--controls',action='store_true')
    a = cli.parse_args()
    binding = a.binding.resolve(strict=True)
    if a.worker:
        raise SystemExit(worker(a.worker.resolve(strict=True),binding,a.fixture,a.controls))
    run(a.output.resolve(),binding,a.fixture,a.controls,a.preflight)

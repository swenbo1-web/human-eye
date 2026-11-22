"""Replay original product requests over a held local production MCP process."""

import argparse
import base64
import ctypes
from ctypes import wintypes
from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path
import sys
import time


HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
from inputs import (BASE_GIT, CATALOGUE, FIXTURES, PRIOR, RUN, SEAL, V, digest, pin, read, require,
                    sealed_inputs, write)


INIT = {'jsonrpc':'2.0','id':'init','method':'initialize',
        'params':{'protocolVersion':'2025-03-26','capabilities':{},
                  'clientInfo':{'name':'local-object-bounds-replay','version':'1'}}}
NOTIFY = {'jsonrpc':'2.0','method':'notifications/initialized'}
LIST = {'jsonrpc':'2.0','id':'list','method':'tools/list'}
LABELS = ('N1','P1','P2','N2','N3','P3','HN','HP')
CLI_PATH = V/'m1_region_task_first_packet_consumption_holdout_001/checks/evidence.py'


def source_paths():
    return (Path(__file__), HERE/'inputs.py', CLI_PATH, PRIOR/'harness/mcp_entry.py', PRIOR/'harness/runtime.py',
            PRIOR/'harness/common.py', PRIOR/'harness/budget.py', PRIOR/'harness/admission.py', CATALOGUE,
            SEAL/'SHARED_DEPENDENCY.json',
            V/'m1_region_task_first_packet_consumption_holdout_recovery_001/harness/runtime.py',
            V/'m4_live_source_region_task_003/harness/mcp_entry.py',
            V/'m4_live_source_region_task_003/harness/reused/verified_bootstrap.py',
            V/'m4_source_region_display_001/harness/reused/stdio_checks.py',
            V/'m4_cross_scale_live_qualification_001/checks/delivery.py')


def peak_memory():
    """Read operating-system process counters after the real producer returned."""
    class Counters(ctypes.Structure):
        _fields_ = [('cb',wintypes.DWORD),('page_fault_count',wintypes.DWORD),
                    *[(name,ctypes.c_size_t) for name in ('peak_rss','rss','peak_paged','paged',
                       'peak_nonpaged','nonpaged','pagefile','peak_pagefile','private')]]
    process = ctypes.WinDLL('kernel32',use_last_error=True).GetCurrentProcess
    process.restype = wintypes.HANDLE
    read_memory = ctypes.WinDLL('psapi',use_last_error=True).GetProcessMemoryInfo
    read_memory.argtypes = (wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD)
    read_memory.restype = wintypes.BOOL
    row = Counters()
    row.cb = ctypes.sizeof(row)
    require(read_memory(process(),ctypes.byref(row),row.cb),'actual_worker_memory_counters_unavailable')
    return {'source':'Windows GetProcessMemoryInfo','peak_working_set_bytes':row.peak_rss,
            'working_set_bytes':row.rss,'private_commit_bytes':row.private,
            'peak_pagefile_bytes':row.peak_pagefile}


def replay_calls(fixture, controls):
    first,later = fixture['calls']
    if not controls:
        # The two original requests are sent byte-equivalently as JSON, with
        # a distinct consumer ID only for the extra warm read in between.
        return [first,{**first,'id':'same_capture_warm'},later]
    # The main fixture proves no-image region, same generation hit, new
    # generation invalidation and ordinary active observation on both installs.
    active = {**first['params']['arguments'],'include_image':False}
    ordinary = {**active,'query':{'mode':'active_observation'}}
    return [{**first,'id':name,'params':{**first['params'],'arguments':args}}
            for name,args in (('no_image',active),('no_image_same_capture',active),
                              ('no_image_new_generation',active),('ordinary_no_image',ordinary))]


def replay_deltas(fixture, controls):
    full,repeat = fixture['deltas']
    if not controls:
        return [full,repeat,repeat]
    changed = deepcopy(full)
    changed['capture']['capture_state']['revision'] += 1
    changed['capture']['revision'] += ':offline-control-new-generation'
    repeat_changed = {**changed,'resources':[]}
    return [full,repeat,changed,repeat_changed]


def verify_geometry(current, terminal):
    rows = {entry['name']:entry for entry in terminal['objects']}
    require(len(current['meshes'])==len(rows) and {mesh['name'] for mesh in current['meshes']}==rows.keys(),
            'actual_replayed_complete_evaluated_roster_changed')
    for mesh in current['meshes']:
        expected = rows[mesh['name']]
        require(mesh['object_id']==expected['object_id']
                and current['host_identity']['object_instances'][expected['object_id']]==expected['instance_id']
                and mesh['vertices']==expected['evaluated']['vertices_world_m']
                and mesh['faces']==expected['evaluated']['triangles'],
                'original_replayed_current_source_mismatch/'+mesh['name'])


def worker(root, binding_path, fixture_name, controls):
    sys.path.insert(0,str(PRIOR/'harness'))
    import mcp_entry

    fixture = sealed_inputs(fixture_name)
    binding = read(binding_path)
    mcp_entry.SOURCE_SHA = binding['source_sha256']
    config = root/'PRODUCT_CONFIG.json'
    write(config,{'schema_version':'1.0','enabled':True,'observe_on_prompt':False,
                  'project_root':binding['install_root'],'state_file':str(root/'product_state.json'),
                  'audit_file':str(root/'product_audit.jsonl'),'request_budget_s':30,
                  'expected_identity':{'source_sha256':binding['source_sha256']}})
    pending = replay_deltas(fixture,controls)
    calls,restore = [],[]

    def setup(verified):
        require(verified==binding,'actual_installed_replay_binding_changed')
        from human_eye_plugin import live_service
        from human_eye_plugin.blender_mcp_host import BlenderMCPHost

        def guard(event,args):
            if event in ('socket.connect','subprocess.Popen','os.system','os.spawn','os.exec'):
                raise AssertionError('archived_worker_cannot_connect_or_launch_Blender')
        sys.addaudithook(guard)

        class ArchivedHost(BlenderMCPHost):
            def _request(self, command, params):
                index = len(calls)
                require(command=='capture' and not params and index<len(pending),'unexpected_original_host_request')
                self._ensure_live()
                at = time.perf_counter_ns()
                delta = pending[index]
                current = self._scene_decoder.apply(deepcopy(delta))
                decoded = time.perf_counter_ns()
                self._record_observation_document(current)
                call = {'command':command,'params':params,'resource_count':len(delta['resources']),
                        'decode_elapsed_ns':decoded-at,'capture_state':current['capture_state']}
                calls.append(call)
                write(root/f'CAPTURE_{index+1:02d}.json',current)
                return current

        host = ArchivedHost(binding['install_root'])
        original = live_service.LiveSpatialService
        restore.append(lambda: setattr(live_service,'LiveSpatialService',original))

        class ReplayService(original):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,host=host,**kwargs)

        live_service.LiveSpatialService = ReplayService

    args = argparse.Namespace(binding=binding_path,config=config,ledger=root/'budget',evidence=root/'mcp_io',
                             archive=root/'product_full',phase='qualification',label='QP',
                             region_task_evidence=True,_offline_capture_setup=setup)
    started = time.perf_counter_ns()
    try:
        return mcp_entry.worker(args)
    finally:
        after = time.perf_counter_ns()
        for undo in restore:
            undo()
        write(root/'REPLAY_CLOSE.json',{'calls':calls,'source_pins':fixture['source_pins'],
              'old_sources_unchanged':all(pin(row['path'])==row for row in fixture['source_pins']),
              'worker_started_ns':started,'worker_closed_ns':after,'worker_window_ns':after-started,
              'memory':peak_memory(),'actual_Blender_starts':0,'actual_models':0})


def raw_frames(root,producer):
    frames = []
    for frame in producer['constructed_frames']:
        png, npz = [Path(frame[name]).resolve(strict=True) for name in ('image_path','arrays_path')]
        require(png.is_relative_to(root) and npz.is_relative_to(root),'actual_current_raster_paths_outside_replay')
        p,a = pin(png),pin(npz)
        require(p['sha256']==frame['image_sha256'] and a['sha256']==frame['arrays_sha256'],'actual_frame_original_bytes_changed')
        frames.append({'scope_id':frame['scope_id'],'view_name':frame['view_name'],'png':p,'arrays':a})
    return frames


def run(root,binding_path,fixture_name,controls,preflight):
    binding = read(binding_path)
    require(len(binding['source_manifest'])==143,'fixed_existing_install_source_set_changed')
    if preflight:
        require(binding['preparation_git']==BASE_GIT and root.is_relative_to(RUN/'preflight'),
                'baseline_only_unmeasured_preflight_root_required')
    elif controls:
        require(root.is_relative_to(RUN/'controls'),'isolated_unmeasured_control_root_required')
    else:
        require(root.parent==RUN/'arms' and root.name in LABELS and
                (root.name.startswith('H')==(fixture_name=='holdout')),
                'fixed_formal_replay_arm_roster_changed')
    root.mkdir(parents=True,exist_ok=False)
    fixture = sealed_inputs(fixture_name)
    sys.path[:0] = [binding['dependency_root'],read(SEAL/'SHARED_DEPENDENCY.json')['dependency_root'],
                    str(PRIOR/'harness')]
    from runtime import ProductionStdioClient
    # The original held-close verifier must bind the real candidate source,
    # rather than the older namespace's baseline SHA.
    ProductionStdioClient.finish.__globals__['SOURCE_SHA'] = binding['source_sha256']
    requests = replay_calls(fixture,controls)
    args = [sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),'--worker',str(root),'--fixture',fixture_name,
            '--binding',str(binding_path)]
    if controls:
        args.append('--controls')
    replies = []
    before = time.perf_counter_ns()
    client = ProductionStdioClient(args,root,root/'mcp',before+120_000_000_000,worker_evidence=root/'mcp_io')
    try:
        identity = client.call(INIT)['result']['_meta']['human_eye']
        client.call(NOTIFY)
        tools = client.call(LIST)['result']['tools']
        require(identity['source_sha256']==binding['source_sha256'] and identity['source_kind']=='installed_distribution'
                and tools==read(CATALOGUE),'actual_installed_product_identity_or_directory_changed')
        for request in requests:
            resp = client.call(request)
            require(resp.get('error') is None and resp['result']['isError'] is False and
                    resp['result']['content'][0]['type']=='text','actual_replay_reply_failed/'+str(request['id']))
            replies.append(resp)
    finally:
        close = client.finish()
        after = time.perf_counter_ns()
    require(close['confirmed'] is True and close['exit_code']==0 and close['production_eof_and_exit_verified']
            and close['process_handle_closed'],'actual_held_process_close_or_exit_unconfirmed')
    worker_close = read(root/'REPLAY_CLOSE.json')
    require(len(worker_close['calls'])==len(requests) and worker_close['old_sources_unchanged']
            and [row['resource_count'] for row in worker_close['calls']]==[len(row['resources']) for row in replay_deltas(fixture,controls)],
            'actual_worker_replay_capture_count_or_unchanged_originals_failed')
    for index in range(1,len(requests)+1):
        verify_geometry(read(root/f'CAPTURE_{index:02d}.json'),fixture['terminal'])
    producers = [read(root/'product_full'/f'call_{i:03d}'/'SERVICE_RESULT.json') for i in range(1,len(requests)+1)]
    frames = [] if controls else raw_frames(root,producers[0])
    if not controls:
        require(len(frames)==3 and all({k:f[k] for k in ('scope_id','view_name')}==
                      {k:g[k] for k in ('scope_id','view_name')} and
                      all({key:f[k][key] for key in ('bytes','sha256')}==g[k] for k in ('png','arrays'))
                      for f,g in zip(frames,fixture['frames'],strict=True)),'actual_replayed_original_PNG_NPZ_changed')
    fixed_cli = run_path(str(CLI_PATH))['fixed_cli']
    checks = []
    for index,(reply,producer,receipt) in enumerate(zip(replies,producers,client.records[3:],strict=True)):
        content = reply['result']['content']
        bytes_text = sum(len(row['text'].encode()) for row in content if row['type']=='text')
        raster = producer['work']['raster_attempts']
        expected_raster = 3 if not controls and index==0 else 0
        require(raster==expected_raster,'actual_cold_or_warm_raster_count_changed')
        checks.append({'index':index+1,'text_bytes':bytes_text,'raster_attempts':raster,
                       'wire':receipt,'CLI':fixed_cli(reply,require_all=not controls and
                                                     (fixture_name=='main' or index<2)),
                       'PNG_bytes':sum(len(base64.b64decode(row['data'],validate=True))
                                       for row in content if row['type']=='image'),
                       'result_cache_hit':producer['work'].get('result_cache_hit',False),
                       'stages':producer['stages'],'work':producer['work']})
    require(checks[1]['result_cache_hit'] is True,'original_same_capture_warm_cache_not_hit')
    if controls:
        require(not checks[0]['result_cache_hit'] and not checks[2]['result_cache_hit']
                and all(row['raster_attempts']==row['PNG_bytes']==0 for row in checks),
                'no_image_warm_or_changed_generation_contract_changed')
    else:
        require([row['capture_state'] for row in worker_close['calls']]
                ==[worker_close['calls'][0]['capture_state']]*3,'original_closed_same_capture_generation_changed')
    write(root/'SUMMARY.json',{'passed':True,'arm':root.name,'fixture':fixture_name,'preflight':preflight,
              'controls':controls,'product':{key:binding[key] for key in ('preparation_git','source_sha256','wheel_sha256')},
              'source_dimensions':fixture['source_dimensions'],'source_pins':[pin(path) for path in source_paths()]+fixture['source_pins'],
              'original_native_transport':fixture['transport'],'actual_Blender_starts':0,'actual_models':0,
              'requests':checks,'construct_frames':frames,'held_close':pin(root/'mcp/HELD_CLOSE.json'),
              'whole_window_ns':after-before,'worker_window_ns':worker_close['worker_window_ns'],'memory':worker_close['memory']})
    print('Passed',root.name,fixture_name,'calls',len(checks),'rasters',sum(row['raster_attempts'] for row in checks),flush=True)


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'pinned_isolated_interpreter_required')
    cli = argparse.ArgumentParser(description=__doc__)
    choice = cli.add_mutually_exclusive_group(required=True)
    choice.add_argument('--output',type=Path)
    choice.add_argument('--worker',type=Path)
    cli.add_argument('--fixture',choices=tuple(FIXTURES),required=True)
    cli.add_argument('--binding',type=Path,required=True)
    cli.add_argument('--preflight',action='store_true')
    cli.add_argument('--controls',action='store_true')
    a = cli.parse_args()
    binding_path = a.binding.resolve(strict=True)
    if a.worker:
        raise SystemExit(worker(a.worker.resolve(strict=True),binding_path,a.fixture,a.controls))
    run(a.output.resolve(),binding_path,a.fixture,a.controls,a.preflight)

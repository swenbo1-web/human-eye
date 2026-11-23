"""Exercise the same held MCP and Owner against the custody-bound replay host."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parent))
import host

TRUTH = host.RUN/'preflight/TRUTH.json'
BASE = host.RUN/'preflight/replay_verified'
TOOL = 'human_eye_scene_observe'


def wait_ready(root, peer):
    until = time.perf_counter() + 50
    while True:
        try:
            ready = host.read(root/'REPLAY_READY.json')
        except (FileNotFoundError, json.JSONDecodeError):
            if peer.poll() is not None or time.perf_counter() >= until:
                raise RuntimeError('registered_fixture_TCP_peer_unavailable')
            time.sleep(.05)
        else:
            break
    host.require(ready['pid'] == peer.pid and ready['host'] == '127.0.0.1'
                 and ready['offline_fixture'] is True and ready['actual_Blender'] == ready['actual_models'] == 0,
                 'actual_registered_fixture_TCP_peer_required')
    return ready


def run(label):
    host.require(label in host.SLOTS and not (host.RUN/'slots').exists(),'offline_before_real_slots_only')
    root = (BASE if label == "A1" else host.RUN/"preflight/replay_ready_verified")/label
    slot = root/'slots'/label
    slot.mkdir(parents=True,exist_ok=False)
    with (root/'REPLAY_STDOUT.bin').open('xb') as stdout, (root/'REPLAY_STDERR.bin').open('xb') as stderr:
        peer = subprocess.Popen([sys.executable,'-IB','-X','utf8',str(host.HERE/'replay_host.py'),label,str(root)],
                                cwd=host.V.parent, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr)
    worker = owner = client = None
    result = {'slot':label,'label':label,'group':'P','phase':'formal','offline_fixture':True,
              'actual_model_admitted':False,'model_consumers':0,'paid_API_calls':0,'status':'failed'}
    start = time.perf_counter_ns()
    result['started_ns'] = start
    try:
        ready = wait_ready(root,peer)
        common,runtime,bridge,_,binding = host.runtime_graph(root,label)
        deadline=start+120_000_000_000
        worker=runtime.Runtime(slot,label,deadline,deadline+30_000_000_000)
        worker.budget=host.Gate(worker.budget,label)
        try:
            worker.start()
        except host.PreflightBoundary:
            host.require(worker.budget.reached and not worker.native_start_entered and worker.native is None
                         and worker.claim is None,'offline_crossed_owned_Blender_boundary')
        else:
            raise RuntimeError('offline_original_runtime_did_not_use_blender_budget')
        worker.native=SimpleNamespace(host=ready['host'],port=ready['port'])
        try:
            worker._start_public_mcp(host.PRODUCT_BINDING,binding)
        finally:
            worker.native=None
        worker.prepare_device(host.ASSET_SHA256)
        common.save(slot/'INSTALLED_TOOLS.json',worker.product_tools)
        owner=bridge.Owner(worker,{'label':label,'group':'P','phase':'formal',
                                  'worker_deadline_ns':deadline,'output':str(slot/'owner')},budget=worker.budget)
        endpoint=owner.start(slot/'ENDPOINT.json')
        client=runtime.transport.StdioClient(
            [sys.executable,'-IB','-X','utf8',str(host.HERE/'thin_stdio.py'),
             '--endpoint',str(endpoint),'--audit',str(slot/'attachments')],
            slot,slot/'ingress_wire',deadline)

        def rpc(method, ident=None, params=None):
            req={'jsonrpc':'2.0','method':method}
            if ident is not None:
                req['id']=ident
            if params is not None:
                req['params']=params
            return client.call(req)

        rpc('initialize','init',{'protocolVersion':'2025-03-26','capabilities':{},
                                 'clientInfo':{'name':'scoped-consumption-closed-replay','version':'001'}})
        rpc('notifications/initialized')
        tools=rpc('tools/list','list')['result']['tools']
        host.require(tools==owner.tools and [item for item in tools if item['name']!=TOOL]==bridge.TOOLS
                     and len(tools)==len(bridge.TOOLS)+1,'same_owner_and_actual_production_tools_required')

        def invoke(ident, name, args):
            return rpc('tools/call',ident,{'name':name,'arguments':args})['result']

        truth=host.read(TRUTH)
        measure_mode='source_region' if label=='A1' else 'source_region_measurement'
        queries=[{'mode':measure_mode,'region':{'object':{'name':truth['target']},
                  'world_box_m':truth['regions'][key]['box_m']},'reference':{'name':truth['reference']},
                  'requested_facts':['surface_proximity']} for key in ('high','low')]
        ordinary=invoke('ordinary-before', 'execute_python',{'code':'import numpy as np\nimport shapely\ns=np.arange(9)\nprint(int(s.sum()))'})
        host.require(ordinary['isError'] is False and json_result(ordinary)['stdout'].strip()=='36',
                     'common_ordinary_compute_failed')
        high=invoke('high',TOOL,{'query':queries[0],'include_image':False,'response_detail':'brief'})
        invalid={'query':{**queries[0],'mode':'source_region_measurement'},'include_image':label=='B1'}
        rejected=invoke('intentionally-invalid',TOOL,invalid)
        low=invoke('low',TOOL,{'query':queries[1],'include_image':False,'response_detail':'brief'})
        ordinary_after=invoke('ordinary-after','execute_python',{'code':'print(int(s[2]+s[-1]))'})
        host.require(rejected['isError'] is True and all(not row['isError'] and len(row['content'])==1
                     and row['content'][0]['type']=='text' for row in (high,low,ordinary_after))
                     and json_result(ordinary_after)['stdout'].strip()=='10'
                     and len(worker.public_requests)==3
                     and ['producer_archive' in row for row in worker.public_requests]==[True,False,True],
                     'actual_public_rejection_recovery_or_measurement_producer_failed')
        result.update(status='completed',actual_Blender_starts=0,actual_models=0,
                      actual_rasters=0,production_calls=3,valid_geometry_calls=2,
                      same_formal_owned_runtime=True,actual_product_tools=tools,ready=pin(root/'REPLAY_READY.json'))
    except BaseException as exc:
        result['error']={'type':type(exc).__name__,'message':str(exc)}
        raise
    finally:
        try:
            if client is not None:
                result['attachment_stdio_close']=client.finish()
        finally:
            try:
                if owner is not None:
                    result['owner_close']=owner.close()
            finally:
                try:
                    if worker is not None:
                        result['runtime_close']=worker.close('preflight')
                        result['budget']=worker.budget.snapshot()
                finally:
                    peer.stdin.close()
                    try:
                        result['actual_fixture_peer_exit_code']=peer.wait(timeout=18)
                    except subprocess.TimeoutExpired:
                        peer.kill()
                        peer.wait(timeout=10)
                        result['actual_fixture_peer_timeout']=True
        result['closed_ns']=time.perf_counter_ns()
        if (root/'REPLAY_CLOSE.json').is_file():
            result['fixture_peer_close']=pin(root/'REPLAY_CLOSE.json')
            closed=host.read(root/'REPLAY_CLOSE.json')
            actual_close=closed['passed'] and closed['actual_stdin_EOF'] and closed['connections_completed']==2
        else:
            actual_close=False
        runtime_close=result.get('runtime_close') or {}
        mcp_close=runtime_close.get('public_MCP_close') or {}
        mcp_exit=runtime_close.get('public_MCP_exit') or {}
        result['closure_verification']={'passed':bool(actual_close and result.get('actual_fixture_peer_exit_code')==0
            and (result.get('attachment_stdio_close') or {}).get('confirmed')
            and (result.get('owner_close') or {}).get('confirmed')
            and mcp_close.get('production_eof_and_exit_verified') and mcp_exit.get('confirmed')
            and not runtime_close.get('errors')),'status':'owned_replay_listener_and_held_stdio_closed',
            'offline_fixture':True}
        for key in ('Blender_start_attempts','consumer_admissions','all_raster_upper'):
            host.require(not (result.get('budget') or {}).get('counts',{}).get(key),
                         'preflight_unexpected_live_budget/'+key)
        if not result['closure_verification']['passed']:
            result['status']='failed'
        write(slot/'SLOT_RESULT.json',result)
        write(slot/'SLOT_PUBLICATION.json',{
            'slot':label,'label':label,'status':result['status'],'owned_budget_passed':True,
            'result_sha256':host.sha(slot/'SLOT_RESULT.json'),'offline_fixture':True})
    host.require(result['status']=='completed','actual_offline_dispatch_failure')


def pin(path):
    path=Path(path).resolve(strict=True)
    return {'path':str(path),'bytes':path.stat().st_size,'sha256':host.sha(path)}


def write(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
        stream.write('\n')


def json_result(result):
    return json.loads(result['content'][0]['text'])


if __name__ == '__main__':
    host.require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_runtime_required')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('label',choices=tuple(host.SLOTS))
    run(parser.parse_args().label)

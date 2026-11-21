"""Exercise the actual owner and consumer stdio with each fixed installed product."""

from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path
import sys
import time


NS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(NS/'harness'),str(Path(__file__).resolve().parent)]
from common import ASSET_SHA256, NARROW_TOOL, SEAL, product_for, read, save


OBSERVE = 'human_eye_scene_observe'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def region():
    return {'region':{'object':{'name':'N26'},'source_triangle_indices':[4,5]},'reference':{'name':'N07'}}


def old_region(*,image,detail='brief'):
    return {'include_image':image,'response_detail':detail,
            'query':{'mode':'source_region','requested_facts':['surface_proximity'],**region()}}


def request(identifier,method,**params):
    return {'jsonrpc':'2.0','id':identifier,'method':method,'params':params}


def call(tool,identifier,arguments):
    return request(identifier,'tools/call',name=tool,arguments=arguments)


def worker(root,label):
    spec = product_for(label)
    b = read(spec['binding'])
    sys.path[:0] = [b['install_root'],b['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.runtime_identity import runtime_identity

    require(runtime_identity()['source_sha256']==spec['source_sha256'],'wrong_actual_bridge_worker_identity')
    capture,_ = run_path(str(NS/'qualification/capture.py'))['pinned_capture']()
    config = root/'PRODUCT_CONFIG.json'
    save(config,{'schema_version':'1.0','enabled':True,'observe_on_prompt':False,
                 'project_root':b['install_root'],'state_file':str(root/'product_state.json'),
                 'audit_file':str(root/'product_audit.jsonl'),'request_budget_s':60,
                 'expected_identity':{'source_sha256':b['source_sha256']}})

    class SavedHost:
        def capture_scene(self):
            return deepcopy(capture)

    class Service(LiveSpatialService):
        def __init__(self):
            super().__init__(config,host=SavedHost())
            self.producers = []

        def observe(self,*args,**kwargs):
            response = super().observe(*args,**kwargs)
            self.producers.append(response)
            return response

        def close(self):
            save(root/'EOF.json',{'closed':True,'rasters':sum(p.get('work',{}).get('raster_attempts',0) for p in self.producers),
                                  'observations':len(self.producers)})

    mcp._configure_utf8_stdio()
    mcp.run_stdio_mcp_server(Service())


def suite(root,label):
    from bridge import Owner,tool_names
    from runtime import transport
    from frame_device import FrameDevice

    folder = root/label
    folder.mkdir()
    deadline = time.perf_counter_ns()+90_000_000_000
    engine = transport.StdioClient([sys.executable,'-IB',str(Path(__file__).resolve()),'--worker',str(folder),label],
                                   folder,folder/'engine_wire',deadline)
    catalogue = engine.call(request('catalogue','tools/list'))['result']['tools']
    require(catalogue==read(product_for(label)['catalogue']),'bridge_worker_catalogue_not_frozen')

    class ReplayRuntime:
        def __init__(self):
            self.label,self.folder,self.product_tools = label,folder,catalogue
            self.public_requests = []
            self.device = FrameDevice(runroot=folder,asset_sha256=ASSET_SHA256,group='P',label=label,
                                      native_call=self.no_host,terminal_call=self.no_host,phase='qualification')
            self.buffers,self.cameras = self.device.buffers,self.device.cameras

        def no_host(self,*_a,**_kw):
            raise AssertionError('bridge_preflight_does_not_start_live_Blender')

        def public_request(self,arguments,*,name=OBSERVE):
            tx = call(name,'observe-'+str(len(self.public_requests)+1),arguments)
            response = engine.call(tx)
            self.public_requests.append({'request':tx,'response':response,'receipt':engine.records[-1]})
            return response

    runtime = ReplayRuntime()
    owner = Owner(runtime,{'label':label,'group':'P','phase':'qualification',
                 'worker_deadline_ns':deadline,'output':str(folder/'owner')})
    client = None
    try:
        endpoint = owner.start(folder/'ENDPOINT.json')
        client = transport.StdioClient([sys.executable,'-IB','-X','utf8',str(NS/'consumer/thin_stdio.py'),
            '--endpoint',str(endpoint),'--audit',str(folder/'attachments')],folder,folder/'outer_wire',deadline)
        received = client.call(request('hello','initialize',protocolVersion='2025-03-26',capabilities={},
                                       clientInfo={'name':'task-entry-preflight','version':'1'}))
        require('result' in received,'actual_bridge_initialize_failed')
        client.call({'jsonrpc':'2.0','method':'notifications/initialized'})
        visible = client.call(request('tools','tools/list'))['result']['tools']
        require(owner.tools==visible and {row['name'] for row in visible}==tool_names(label),
                'the_model_facing_directory_did_not_match_the_actual_arm')
        ordinary = client.call(call('execute_python','ordinary',{'code':'x_for_bridge = 6 * 7\nprint(x_for_bridge)'}))
        require(not ordinary['result']['isError'] and '42' in ordinary['result']['content'][0]['text'],
                'the_common_ordinary_bridge_failed')
        name = OBSERVE if label=='QA' else NARROW_TOOL
        bad = {**old_region(image=False),'response_detail':'invalid'} if label=='QA' else {
            **region(),'include_image':False,'response_detail':'full'}
        refused = client.call(call(name,'invalid',bad))
        require(refused['result']['isError'] and runtime.public_requests[-1]['request']['params']=={
            'name':name,'arguments':bad},'invalid_request_not_forwarded_unchanged_and_rejected')
        payload = old_region(image=False) if label=='QA' else {**region(),'include_image':False}
        reply = client.call(call(name,'positive',payload))
        require(not reply['result']['isError'] and runtime.public_requests[-1]['request']['params']=={
            'name':name,'arguments':payload} and runtime.public_requests[-1]['response']['result']==reply['result'],
            'the_trial_bridge_changed_the_tool_arguments_or_response')
        body = json.loads(reply['result']['content'][0]['text'])
        measured = body['task_result']['facts']['surface_proximity']
        require(body['region_ref']['source_triangle_indices']==[4,5] and not body['images']
                and measured['status']=='measured' and abs(measured['value']['distance_m']-.02)<1e-8,
                'same_actual_query_did_not_deliver_the_no_image_measurement')
        save(folder/'OUTER_REPLY.json',reply)
    finally:
        outer = client.finish() if client else None
        closed_owner = owner.close()
        inner = engine.finish()
        require(outer and outer['confirmed'] and outer['exit_code']==0 and closed_owner['confirmed']
                and not closed_owner['errors'] and not closed_owner['transport_errors']
                and inner['confirmed'] and inner['exit_code']==0,'actual_preflight_transports_did_not_close')
    eof = read(folder/'EOF.json')
    require(eof=={'closed':True,'rasters':0,'observations':1},'unexpected_preflight_observation_or_raster')
    return {'catalogue':visible,'actual_named_stock_dispatch':name,'all_arguments_exact':True,
            'explicit_invalid_then_success':True,'closed':True,'rasters':0}


def run(root):
    b = read(product_for('QA')['binding'])
    sys.path[:0] = [b['dependency_root'],read(SEAL/'SHARED_DEPENDENCY.json')['dependency_root']]
    root.mkdir(parents=True,exist_ok=False)
    root = root.resolve(strict=True)
    results = {label:suite(root,label) for label in ('QA','QB')}
    a,b = (results[label]['catalogue'] for label in ('QA','QB'))
    require(b[:-1]==a and len(b)==len(a)+1 and b[-1]['name']==NARROW_TOOL,'unexpected_user_facing_catalogue_delta')
    save(root/'BRIDGE_PREFLIGHT.json',{'passed':True,'actual_Blender':0,'model':0,'raster':0,'arms':results,
         'scope':'real owner TCP, consumer stdio and each installed public server on retained source arrays'})
    print(json.dumps({'passed':True,'A_tools':len(a),'B_tools':len(b)}))


if __name__=='__main__':
    if len(sys.argv)==4 and sys.argv[1]=='--worker':
        worker(Path(sys.argv[2]),sys.argv[3])
    else:
        run(Path(sys.argv[1]))

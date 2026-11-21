"""Rehearse the real outer bridge and installed MCP on the sealed Q1 capture."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import time


NS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(NS/'harness'), str(Path(__file__).resolve().parent)]
from common import ASSET_SHA256, DUAL, PRODUCT_BINDING, CATALOGUE, SEAL, SOURCE_SHA, load_retained, read, save
from diagnostic import TOOL, args, require


def request(identifier, method, **params):
    return {'jsonrpc':'2.0','id':identifier,'method':method, 'params':params}


def tool_req(identifier, payload):
    return request(identifier,'tools/call',name=TOOL,arguments=payload)


def pinned_capture():
    prior = load_retained('_first_packet_captured_saved_source',DUAL/'qualification/product_replay.py')
    return prior.captured_source()


def product_worker(root):
    binding = read(PRODUCT_BINDING)
    sys.path[:0] = [binding['install_root'],binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.runtime_identity import runtime_identity

    require(runtime_identity()['source_sha256']==SOURCE_SHA,'preflight_used_wrong_installed_product')
    capture, _, _ = pinned_capture()
    cfg = root/'PRODUCT_CONFIG.json'
    save(cfg,{'schema_version':'1.0','enabled':True,'observe_on_prompt':False,
        'project_root':binding['install_root'],'state_file':str(root/'product_state.json'),
        'audit_file':str(root/'product_audit.jsonl'),'request_budget_s':60,
        'expected_identity':{'source_sha256':SOURCE_SHA}})

    class SavedHost:
        def capture_scene(self):
            return deepcopy(capture)

    class RecordingService(LiveSpatialService):
        def __init__(self):
            super().__init__(cfg,host=SavedHost())
            self.calls = 0

        def observe(self,*positional,**kwargs):
            observed = super().observe(*positional,**kwargs)
            self.calls += 1
            save(root/f'PRODUCER_{self.calls:02d}.json',observed)
            return observed

        def close(self):
            save(root/'PRODUCT_EOF.json',{'closed':True,'calls':self.calls})

    mcp._configure_utf8_stdio()
    mcp.run_stdio_mcp_server(RecordingService())


def run(root):
    sys.path[:0] = [read(PRODUCT_BINDING)['dependency_root'],read(SEAL/'SHARED_DEPENDENCY.json')['dependency_root']]
    from bridge import Owner
    from frame_device import FrameDevice
    from runtime import transport
    from treatment import Treatment

    root.mkdir(parents=True,exist_ok=False)
    root = root.resolve(strict=True)
    capture,sources,commands = pinned_capture()
    ids = {row['name']:row['object_id'] for row in capture['meshes']}
    save(root/'CAPTURE_BINDING.json',{'capture_state':capture['capture_state'],'revision':capture['revision'],'ids':ids})
    deadline = time.perf_counter_ns()+90_000_000_000
    product_root = root/'product'
    product_root.mkdir()
    product = transport.StdioClient([sys.executable,'-IB',str(Path(__file__).resolve()),'--worker',str(product_root)],
                                    root,root/'product_wire',deadline)
    catalogue = product.call(request('catalogue','tools/list'))['result']['tools']
    require(catalogue==read(CATALOGUE),'preflight_catalogue_does_not_match_frozen_install')
    replies, arms = {}, {}
    current_ref = []

    class ReplayRuntime:
        def __init__(self,folder,label,detail):
            self.folder, self.product_tools = folder,catalogue
            self.public_requests, self.rows = [],[]
            self.treatment = Treatment(detail,ids['Obj_09'],ids['Obj_04'])
            self.device = FrameDevice(runroot=folder,asset_sha256=ASSET_SHA256,group='P',label=label,
                native_call=self.forbid_host,terminal_call=self.forbid_host,phase='qualification')
            self.buffers,self.cameras = self.device.buffers,self.device.cameras

        def forbid_host(self,*_args,**_kwargs):
            raise AssertionError('replay_never_launches_live_Blender')

        def public_request(self, arguments):
            payload, decision = self.treatment.arguments(arguments,current_ref)
            tx = tool_req('observe-'+str(len(product.records)),payload)
            response = product.call(tx)
            result = self.treatment.accept(decision,response)
            self.public_requests.append({'request':tx,'response':response,'receipt':product.records[-1]})
            self.rows.append({'original_arguments':arguments,'product_arguments':payload,
                              'decision':decision,'outcome':result})
            return response

    try:
        for label, arm, detail in (('QA','A','full'),('QB','B','brief')):
            folder = root/arm
            folder.mkdir()
            runtime = ReplayRuntime(folder,label,detail)
            owner = Owner(runtime,{'label':label,'group':'P','phase':'qualification',
                'worker_deadline_ns':deadline,'output':str(folder/'owner')})
            client = None
            try:
                endpoint = owner.start(folder/'ENDPOINT.json')
                client = transport.StdioClient([sys.executable,'-IB','-X','utf8',str(NS/'consumer/thin_stdio.py'),
                    '--endpoint',str(endpoint),'--audit',str(folder/'attachments')],folder,folder/'outer_wire',deadline)
                init = client.call(request('initialize','initialize',protocolVersion='2025-03-26',capabilities={},
                                           clientInfo={'name':'first-packet-preflight','version':'1'}))
                require('result' in init,'actual_outer_initialize_failed')
                client.call({'jsonrpc':'2.0','method':'notifications/initialized'})
                listed = client.call(request('list','tools/list'))['result']['tools']
                require(listed==owner.tools and listed[-1]==next(t for t in catalogue if t['name']==TOOL),
                        'outer_catalogue_diverged_from_actual_product')
                ordinary = client.call(request('ordinary','tools/call',name='execute_python',
                    arguments={'code':'x_before_treatment = 6 * 7\nprint(x_before_treatment)'}))
                require(not ordinary['result']['isError'] and '42' in ordinary['result']['content'][0]['text'],
                        'ordinary_bridge_failed_before_treatment')
                if arm=='A':
                    not_eligible = args(detail='brief',include_image=False)
                    excluded = client.call(tool_req('excluded',not_eligible))
                    require(excluded['result']['isError'] is False and runtime.rows[-1]['product_arguments']==not_eligible,
                            'image_disabled_semantic_nonmatch_was_changed')
                    current_ref.append(json.loads(excluded['result']['content'][0]['text'])['region_ref'])
                invalid = args(detail='invalid')
                refused = client.call(tool_req('invalid',invalid))
                require(refused['result']['isError'] is True and runtime.rows[-1]['product_arguments']==invalid
                        and 'response_detail' in refused['result']['content'][0]['text'],
                        'invalid_response_detail_was_not_transparently_rejected')
                eligible = args(detail='brief' if arm=='A' else 'full')
                if arm=='B':
                    eligible['query'].pop('region')
                    eligible['query']['region_ref'] = current_ref[0]
                    eligible['query']['reference'] = {'id':ids['Obj_04']}
                positive = client.call(tool_req('eligible',eligible))
                require(positive['result']['isError'] is False and runtime.rows[-1]['original_arguments']==eligible
                        and runtime.rows[-1]['product_arguments']==dict(eligible,response_detail=detail),
                        'actual_first_captured_arguments_or_requested_shape_changed')
                replies[arm] = positive
                repeated = args(detail='brief')
                followup = client.call(tool_req('post_treatment',repeated))
                require(followup['result']['isError'] is False and runtime.rows[-1]['product_arguments']==repeated
                        and sum(row['decision']['applied'] for row in runtime.rows)==1,
                        'later_matching_legal_call_was_rewritten')
                save(folder/'FIRST_RX.json',positive)
                save(folder/'TREATMENT.json',runtime.rows)
            finally:
                closed = None if client is None else client.finish()
                owner_close = owner.close()
                require(closed and closed['confirmed'] and closed['exit_code']==0
                        and owner_close['confirmed'] and not owner_close['errors'] and not owner_close['transport_errors'],
                        'preflight_outer_stdio_did_not_close')
            arms[arm] = {'arm':arm,'actual_tools':listed,'consumer_stdio_closed':True,'owner_closed':True}
        require(arms['A']['actual_tools']==arms['B']['actual_tools'],'arm_tool_catalogues_disagree')
    finally:
        product_closed = product.finish()
        require(product_closed['confirmed'] and product_closed['exit_code']==0,'installed_MCP_replay_did_not_close')
    cli = load_retained('_first_packet_fixed_cli_preflight',NS/'checks/cli.py')
    trial = cli.audit(replies['A'],replies['B'],raw_output=root/'fixed_cli',expected_image_root=product_root)
    producers = [read(path) for path in product_root.glob('PRODUCER_*.json')]
    require(trial['passed'] and read(product_root/'PRODUCT_EOF.json')['closed'] is True
            and len(producers)==5 and sum(record['work']['raster_attempts'] for record in producers)==1,
            'same_producer_first_packet_current_evidence_missing')
    summary = {'passed':True,'product_closed':True,'offline_software_rasters':1,'Blender_starts':0,'model_starts':0,
               'current_fixture_binding_pins':sources,'archived_host_commands':commands,'arms':arms,'paired_fixed_CLI':trial,
               'scope':'actual outer TCP and consumer stdio, installed MCP over the saved Q1 host capture'}
    save(root/'PREFLIGHT.json',summary)
    print(json.dumps({'passed':True,'software_rasters':1,'brief_fixed_CLI':trial['brief_exact_stages']}))


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--worker':
        product_worker(Path(sys.argv[2]))
    else:
        run(Path(sys.argv[1]))

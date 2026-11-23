"""Run production stdio catalog, argument guards, and matched legacy capture controls."""

import argparse
import base64
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import sys
from time import perf_counter_ns


HERE = Path(__file__).resolve().parent
V = HERE.parent
WORKSPACE = V.parent
RUN = Path('D:/he_m1_m2_source_region_scoped_measurement_001').resolve()
PRIOR = V/'m2_source_region_selective_residency_001'
BASE_BINDING = PRIOR/'install/PRODUCT_RUN_BINDING.json'
CANDIDATE_BINDING = HERE/'install/PRODUCT_RUN_BINDING.json'
HARNESS = V/'m4_cross_scale_discovery_001/harness/reused/stdio_checks.py'
ORIGINAL_CONTROLS = V/'m2_source_region_cold_selective_transport_001/controls.py'
TOOL = 'human_eye_scene_observe'
MODE = 'source_region_measurement'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_bytes())


def pin(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    return {'path':str(path),'bytes':len(raw),'sha256':sha256(raw).hexdigest()}


def write(path, value):
    with path.open('x',encoding='utf8',newline='\n') as text:
        json.dump(value,text,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)
        text.write('\n')


def frame(result):
    require(result.get('isError') is False and result['content'][0]['type'] == 'text',
            'legacy_or_scoped_positive_must_publish_text/'+str(result.get('content',[{}])[0])[:600])
    return json.loads(result['content'][0]['text'])


def error(result, expected):
    require(result.get('isError') is True and len(result['content']) == 1 and result['content'][0]['type'] == 'text',
            'control_did_not_return_standard_tool_error/'+expected)
    body = json.loads(result['content'][0]['text'])
    require(expected in str(body['error']), 'wrong_public_rejection/'+expected+'/'+str(body))
    return body['error']


def worker(args):
    (root,dependency,config,fixture,calls) = (
        Path(args[0]).resolve(strict=True),Path(args[1]).resolve(strict=True),Path(args[2]).resolve(strict=True),
        Path(args[3]).resolve(strict=True),Path(args[4]).resolve())
    from contextvars import ContextVar
    sys.path[:0] = [str(root),str(dependency)]
    from human_eye_plugin import production_server
    require(Path(production_server.__file__).resolve().is_relative_to(root),'control_launcher_not_installed')
    incoming = read(fixture)
    current_id = ContextVar('production_control_id',default=None)
    start_service = production_server.construct_live_service

    def append(row):
        with calls.open('a',encoding='utf8',newline='\n') as stream:
            stream.write(json.dumps(row,allow_nan=False)+'\n')

    def deny(event, labels):
        if event in ('socket.connect','socket.bind','subprocess.Popen','os.system','os.spawn','os.exec','os.startfile'):
            append({'event':'blocked_external_operation','operation':event,'id':current_id.get()})
            raise PermissionError('public_controls_no_socket_or_child_process')

    def service(path):
        product = start_service(path)

        def whole(*unused,**ignored):
            append({'event':'replay_capture_scene','id':current_id.get()})
            return deepcopy(incoming['scene'])

        def scoped(target,reference,box,deadline,budget):
            name = current_id.get()
            append({'event':'replay_capture_source_region_pair','id':name})
            core = deepcopy(incoming['scoped'])
            if name == 'wrong_source':
                core['binding']['host_source_sha256'] = '1'*64
            if name == 'wrong_scope':
                core['binding']['capture_scope'] = 'complete_scene_meshes'
            if name == 'wrong_instance':
                core['binding']['target']['name'] = 'invalid-current-object'
            if name == 'bad_digest':
                core['payload_sha256'] = '2'*64
            return core

        product.host.capture_scene = whole
        # A legacy pair query can also use the original complete scene contract.
        product.host.capture_task_scene = None
        if incoming['scoped'] is not None:
            product.host.capture_source_region_pair = scoped
            product.host._readonly_host_source_sha256 = incoming['scoped']['binding']['host_source_sha256']
        return product

    production_server.construct_live_service = service
    from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
    dispatch = LiveSpatialMCPServer.handle_jsonrpc_message

    def observe_id(self, rpc):
        token = current_id.set(rpc.get('id') if isinstance(rpc,dict) else None)
        try:
            return dispatch(self,rpc)
        finally:
            current_id.reset(token)

    LiveSpatialMCPServer.handle_jsonrpc_message = observe_id
    sys.addaudithook(deny)
    return production_server.main(['--config',str(config),*args[5:]])


def call(client, ident, method, params=None):
    req={'jsonrpc':'2.0','id':ident,'method':method}
    if params is not None:
        req['params']=params
    reply=client.call(req)
    require('error' not in reply,'MCP_envelope_error/'+ident+'/'+str(reply.get('error')))
    return reply['result']


def invoke(client, ident, arguments):
    return call(client,ident,'tools/call',{'name':TOOL,'arguments':arguments})


def installed_cases(label,binding,fixture,legacy,scoped,transport,flags,rejections,run_compat=False):
    out=RUN/'preflight/public_controls'/label
    out.mkdir(parents=True,exist_ok=False)
    config=out/'CONFIG.json'
    write(config, {'schema_version':'1.0','enabled':True,'project_root':binding['install_root'],
        'state_file':str(out/'product_state.json'),'audit_file':str(out/'product_audit.jsonl'),
        'observe_on_prompt':False,'request_budget_s':30,'expected_identity':{'source_sha256':binding['source_sha256']},
        'blender':{'host':'127.0.0.1','port':1,'timeout_s':1}})
    events=out/'DISPATCH.jsonl'
    events.touch(exist_ok=False)
    command=[sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),'--worker',
             binding['install_root'],binding['dependency_root'],str(config),str(fixture),str(events),*flags]
    client=transport(command,WORKSPACE,out/'stdio',perf_counter_ns()+150_000_000_000)
    report,rejections_run,compat = {},{},{}
    try:
        hello=call(client,'initialize','initialize',{'protocolVersion':'2025-03-26','capabilities':{},
            'clientInfo':{'name':'scoped-measurement-public-controls','version':'1'}})
        require(hello['_meta']['human_eye']['source_sha256']==binding['source_sha256'],
                'actual_public_worker_source_identity')
        client.call({'jsonrpc':'2.0','method':'notifications/initialized'})
        catalogue=call(client,'tools','tools/list')['tools']
        for name,args,expected in rejections:
            rejections_run[name]=error(invoke(client,name,args),expected)
        if run_compat:
            br=frame(invoke(client,'legacy_brief',{'query':legacy,'include_image':False,'response_detail':'brief'}))
            full=frame(invoke(client,'legacy_full',{'query':legacy,'include_image':False,'response_detail':'full'}))
            ref=br['region_ref']
            by_ref={key:value for key,value in legacy.items() if key != 'region'} | {'region_ref':ref}
            bad_ref=deepcopy(by_ref)
            bad_ref['region_ref']['ordered_geometry_sha256']='0'*64
            error(invoke(client,'old_stale_reference',{'query':bad_ref,'include_image':True}),
                  'source_region_')
            image_result=invoke(client,'legacy_reference_image',{'query':by_ref,'include_image':True,
                                                                'response_detail':'brief'})
            image=frame(image_result)
            actual=[base64.b64decode(block['data'],validate=True) for block in image_result['content']
                    if block['type']=='image' and block.get('mimeType')=='image/png']
            require(len(actual)==1 and actual[0].startswith(b'\x89PNG\r\n\x1a\n')
                    and image['region_ref']==full['region_ref']==ref
                    and br['task_result']['facts']==full['task_result']['facts']==image['task_result']['facts']
                    and full['task_result']['binding']['capture_scope']=='complete_scene_meshes'
                    and full.get('source_mapping',{}) and br['images']==[]
                    and image['images'][0]['image_sha256']==sha256(actual[0]).hexdigest(),
                    'legacy_brief_full_or_current_reference_png_changed')
            png=out/'legacy_reference.png'
            png.write_bytes(actual[0])
            whole={'mode':'task','objects':[legacy['region']['object'],legacy['reference']],
                   'requested_facts':['surface_proximity']}
            ordinary=frame(invoke(client,'ordinary_task',{'query':whole,'include_image':False}))
            task=ordinary.get('task_result',ordinary)
            require(task.get('result_kind')=='task_query' and task['facts']['surface_proximity']['status']=='measured',
                    'ordinary_whole_surface_task_changed')
            compat={'region_ref':ref,'facts':br['task_result']['facts'],'source_mapping':full['task_result']['source_mapping'],
                    'ordinary_facts':task['facts'],'png':pin(png),'png_bytes':len(actual[0])}
        if 'wrong_source' in rejections_run:
            cases = [frame(invoke(client,'scoped_'+detail,dict(scoped,**(
                {} if detail=='omitted' else {'response_detail':detail}))))
                for detail in ('omitted','brief','full')]
            require(cases[0]==cases[1]==cases[2] and cases[0]['schema']=='human-eye-source-region-scoped-measurement-v1'
                    and cases[0]['read_only'] is True and 'region_ref' not in cases[0],
                    'public_scoped_detail_levels_or_recovery_disagree')
            report['same_scoped_detail_levels']=True
            report['private_public_result']=cases[0]
    finally:
        closed=client.finish()
    require(closed['confirmed'] is True and closed['exit_code']==0 and closed['reader_stopped'] is True,
            'control_mcp_worker_did_not_close/'+label)
    observed=[json.loads(line) for line in events.read_bytes().splitlines()]
    by_case={row['id']:row['event'] for row in observed}
    require(len(by_case)==len(observed)
            and not any(row['event']=='blocked_external_operation' for row in observed)
            and not set(rejections_run).intersection(by_case).difference(
                {'wrong_source','wrong_scope','wrong_instance','bad_digest'}),
            'input_rejection_reached_geometry_or_socket')
    if run_compat:
        require({name:by_case[name] for name in ('legacy_brief','legacy_full','legacy_reference_image',
                'old_stale_reference','ordinary_task')}=={name:'replay_capture_scene' for name in (
                    'legacy_brief','legacy_full','legacy_reference_image','old_stale_reference','ordinary_task')},
                'legacy_compatibility_did_not_use_the_current_capture_boundary')
    require(not report or all(by_case.get('scoped_'+detail)=='replay_capture_source_region_pair'
                for detail in ('omitted','brief','full')),'scoped_details_did_not_use_selective_route')
    report.update(catalogue=catalogue, rejections=rejections_run, dispatch=observed, compatibility=compat,
                  closure=closed, source_pins=[pin(path) for path in sorted(out.rglob('*')) if path.is_file()])
    return report


def args_rejections(scoped):
    out=[]
    def variant(name, where, key, value, reason, *, remove=False):
        case=deepcopy(scoped)
        current=case
        for field in where:
            current=current[field]
        if remove:
            current.pop(key)
        else:
            current[key]=value
        out.append((name,case,reason))
    variant('with_image',(),'include_image',True,'source_region_measurement')
    variant('missing_image',(),'include_image',None,'source_region_measurement',remove=True)
    variant('null_image',(),'include_image',None,'source_region_measurement')
    variant('wrong_fact',('query',),'requested_facts',['aabb'],'source_region')
    variant('extra_fact',('query',),'requested_facts',['surface_proximity','aabb'],'source_region')
    variant('missing_fact',('query',),'requested_facts',None,'source_region',remove=True)
    variant('old_ref',('query',),'region_ref',{},'source_region_measurement')
    variant('old_indices',('query','region'),'source_triangle_indices',[0],'source_region')
    variant('same_selector',('query',),'reference',scoped['query']['region']['object'],'distinct objects')
    variant('both_selector_kinds',('query','region','object'),'id','x','selector')
    variant('invalid_lower',('query','region','world_box_m'),'min',[True,0,0],'world_box')
    variant('inverse_limits',('query','region','world_box_m'),'min',[10,10,10],'world_box')
    variant('opaque_task_context',(),'task_context',{'label':'fixture'},'source_region_measurement')
    variant('bad_detail',(),'response_detail','compact','response_detail must be full or brief')
    out.extend((name,scoped,reason) for name,reason in (
        ('wrong_source','selective_source_region_capture_binding'),
        ('wrong_scope','selective_source_region_capture_binding'),
        ('wrong_instance','selective_source_region_object_binding'),
        ('bad_digest','selective_source_region_payload_digest_mismatch')))
    return out


def run():
    controls=run_path(str(ORIGINAL_CONTROLS))
    old=run_path(str(PRIOR/'verify.py'))
    baseline, root, old_pins=controls['check_installed'](BASE_BINDING)
    candidate, _, new_pins=controls['check_installed'](CANDIDATE_BINDING)
    delta, full, terminal, queries, truth, source_pins=controls['fixture']('assembly',root)
    require(len(full['meshes'])==28 and len(queries)==2,'frozen_assembly_capture_missing')
    original=Path('D:/he_m2_source_region_selective_residency_001/slots/AB')
    prev=old['wire_records'](original)[0]
    core,_,_=old['materialization'](prev,None,'B')
    expected=queries[0]
    require(core['binding']['target_selector']==expected['region']['object']
            and core['binding']['reference_selector']==expected['reference']
            and core['binding']['world_box_m']==expected['region']['world_box_m'],
            'historic_private_capture_differs_from_actual_control_query')
    raw_index=read(original.parents[1]/'sealed/RAW_INDEX.json')
    from zipfile import ZipFile
    with ZipFile(raw_index['archive']['path']) as archive:
        for direction in ('tx','rx'):
            wire=prev[direction]
            part=Path(wire['path']).relative_to(original.parents[1]).as_posix()
            require(archive.read(part)==Path(wire['path']).read_bytes()
                    and raw_index['members'][part]=={key:wire[key] for key in ('bytes','sha256')},
                    'old_selective_private_raw_control_differed_from_frozen_member')
    dest=RUN/'preflight/public_controls'
    dest.mkdir(parents=True,exist_ok=False)
    fixture=dest/'BOUND_SOURCE.json'
    write(fixture,{'scene':full,'scoped':core})
    scoped={'query':dict(expected,mode=MODE),'include_image':False}
    transport=run_path(str(HARNESS))['StdioClient']
    disabled=[('disabled',scoped,'source_region_measurement_disabled')]
    old_disabled=[('disabled',scoped,'query contains unsupported observation fields')]
    a=installed_cases('baseline',baseline,fixture,expected,scoped,transport,[],old_disabled,run_compat=True)
    closed=installed_cases('candidate_disabled',candidate,fixture,expected,scoped,transport,[],disabled)
    b=installed_cases('candidate_enabled',candidate,fixture,expected,scoped,transport,
                       ['--source-region-measurement'],args_rejections(scoped),run_compat=True)
    a_e=installed_cases('baseline_region_evidence',baseline,fixture,expected,scoped,transport,
                        ['--region-task-evidence'],old_disabled)
    b_e=installed_cases('candidate_region_evidence',candidate,fixture,expected,scoped,transport,
                        ['--region-task-evidence'],disabled)
    both=installed_cases('candidate_both',candidate,fixture,expected,scoped,transport,
                         ['--region-task-evidence','--source-region-measurement'],[])
    standard=read(HERE/'STANDARD_TOOLS.json')
    require(a['catalogue']==closed['catalogue']==standard and a_e['catalogue']==b_e['catalogue'],
            'standard_or_existing_evidence_catalogue_changes_when_new_option_disabled')
    supported=b['catalogue']
    by_name=lambda tools:{item['name']:item for item in tools}
    original,enabled=by_name(standard),by_name(supported)
    require(original.keys()==enabled.keys()
            and all(original[name]==enabled[name] for name in original if name!=TOOL)
            and MODE not in original[TOOL]['inputSchema']['properties']['query']['properties']['mode']['enum']
            and enabled[TOOL]['inputSchema']['properties']['query']['properties']['mode']['enum']
                == original[TOOL]['inputSchema']['properties']['query']['properties']['mode']['enum']+[MODE]
            and by_name(both['catalogue'])[TOOL]['inputSchema']==enabled[TOOL]['inputSchema']
            and 'same compact' in enabled[TOOL]['description'],
            'opt_in_schema_changed_any_other_tool_or_failed_to_declare_mode')
    for key in ('region_ref','facts','source_mapping','ordinary_facts','png_bytes'):
        require(a['compatibility'][key]==b['compatibility'][key],'old_A_B_compatibility_changed/'+key)
    require(a['compatibility']['png']['sha256']==b['compatibility']['png']['sha256'],
            'legacy_actual_reference_png_bytes_differed')
    result_path=RUN/'preflight/PUBLIC_CONTROLS.json'
    source_pins.extend([prev['tx'],prev['rx'],pin(fixture),pin(HARNESS),pin(Path(__file__))])
    pins=source_pins+old_pins+new_pins
    cases={'baseline':a,'candidate_disabled':closed,'candidate_enabled':b,'baseline_region_evidence':a_e,
           'candidate_region_evidence':b_e,'candidate_both':both}
    for report in cases.values():
        pins.extend(report.pop('source_pins'))
    write(result_path,{'passed':True,'cases':cases,'source_pins':list({row['path']:row for row in pins}.values()),
        'scope':'installed production stdio; exact sealed capture injected only at worker host boundary',
        'actual_sockets':0,'actual_models':0,'actual_Blender':0,'software_png_publications':2})
    print(result_path)


if __name__=='__main__':
    if '--worker' in sys.argv:
        raise SystemExit(worker(sys.argv[2:]))
    run()

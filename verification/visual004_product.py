"""Trial-only adapter to the unchanged actual LiveSpatialMCPServer.

N never imports this module. It only attaches P to a neutral owned Blender
execute_code transport, forwards the original task deadline and accounts PNGs.
No object selection, solver, view choice or product threshold is added.
"""
from __future__ import annotations
import argparse,base64,copy,hashlib,json,os,sys,time,uuid
from pathlib import Path
from verification.visual004_native import NativeSession,ImageLedger,encoded,load,save,check,sha,need

ROOT=Path(__file__).resolve().parents[1]
PIN='6a5375fb5d5577e8de05c043db7523263cf96ad8386ee524a04beb25feb9f382'
ALLOWED_VISUAL={('auto','SCENE'),('auto','XY'),('auto','XZ'),('projection','SCENE')}
_OWNED_CONTEXTS={}

def validate_observe_arguments(arguments):
    need(type(arguments) is dict,'observe_arguments')
    allowed={'task_instruction','focal_id','reference_id','include_image','query','response_detail'}
    need(set(arguments)<=allowed,'readonly_observe_arguments')
    query=arguments.get('query',{})
    need(type(query) is dict,'observe_query')
    need(set(query)<={'mode','object_ids','label_object_ids','max_exact_pairs','native_visual','visual_diagnostic'},'query_scope')
    need(query.get('mode','overview') in ('overview','exact_pairs','nearest','top1'),'query_scope')
    visual=query.get('native_visual',dict(mode='auto',view='SCENE'))
    need(type(visual) is dict and set(visual)<= {'mode','view'}
        and (visual.get('mode','auto'),visual.get('view','SCENE')) in ALLOWED_VISUAL,'fixed_visual_modes')
    return copy.deepcopy(arguments)

def config_for(session):
    from human_eye_plugin.runtime_identity import runtime_identity,check_source_drift
    identity=runtime_identity();need(identity['source_sha256']==PIN and len(identity['source_files'])==129
        and check_source_drift()['compatible'],'product_runtime_pin')
    need(session.config['condition']=='P','P_only_product')
    config=dict(schema_version='1.0',enabled=True,observe_on_prompt=False,project_root=str(ROOT),
        state_file=str(session.workspace/'product_state.json'),audit_file=str(session.workspace/'product_audit.jsonl'),
        expected_identity=dict(source_sha256=PIN,implementation_revision=identity['implementation_revision'],mode='live'),
        request_budget_s=20.,native_visual_timeout_s=10.,
        blender=dict(host=session.host,port=session.port,timeout_s=20.))
    path=session.workspace/'PRODUCT_CONFIG.json'
    if path.exists():need(load(path)==config,'product_config_changed')
    else:save(path,config)
    return path

def _private_native_evidence(session,after_sequence=0):
    """Actual existing host responses, not manufactured renderer attestations."""
    rows=[]
    for folder in sorted(session.workspace.glob('call_*'),key=lambda path:int(path.name.split('_')[-1])):
        if int(folder.name.split('_')[-1])<=after_sequence:continue
        source=folder/'stdout.txt'
        if not source.is_file():continue
        text=source.read_text(encoding='utf8')
        if not text.startswith('HUMAN_EYE_BLENDER_MCP:'):continue
        try:value=json.loads(text.split(':',1)[1]);result=value.get('result')
        except (ValueError,TypeError):continue
        if type(result) is dict:
            # All raw host responses remain in stdout.txt. Record structural
            # keys and actual PNG hashes recursively without copying base64
            # into a public text response.
            hashes=[]
            def walk(item,path=''):
                if type(item) is dict:
                    for key,child in item.items():
                        if key in ('png_sha256','image_sha256') and type(child) is str:hashes.append(dict(path=path+'/'+key,sha256=child))
                        elif key not in ('image_base64','data'):walk(child,path+'/'+key)
                elif type(item) is list:
                    for index,child in enumerate(item):walk(child,path+'/'+str(index))
            walk(result)
            rows.append(dict(call=folder.name,raw_response_sha256=sha(source),result_keys=sorted(result),raw_png_hashes=hashes))
    return rows

def close_product(session):
    context=_OWNED_CONTEXTS.pop(str(session.workspace),None)
    if context is not None:context['host'].close()

def _context(session):
    from human_eye_plugin.blender_mcp_host import BlenderMCPHost
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
    need(not (session.workspace/'POISONED.json').exists(),'session_poisoned')
    path=config_for(session);key=str(session.workspace)
    if key in _OWNED_CONTEXTS:
        item=_OWNED_CONTEXTS[key]
        need(item['pid']==session.config['pid'] and item['deadline_ns']==session.config['deadline_ns']
            and item['host'].is_alive,'product_context_not_replaced')
        return item
    host=BlenderMCPHost(ROOT,host=session.host,port=session.port,timeout_s=20.)
    try:
        service=LiveSpatialService(path,host=host,production_mode=True)
        item=dict(host=host,service=service,server=LiveSpatialMCPServer(service,
            default_session_id='visual004-'+session.workspace.name),pid=session.config['pid'],deadline_ns=session.config['deadline_ns'])
    except BaseException:
        host.close();raise
    _OWNED_CONTEXTS[key]=item;return item

def observe(session,arguments,*,request_id=None,operator_support_check=False):
    """Construct the actual MCP text/image blocks; never attest consumption."""
    start=time.perf_counter_ns();check(session.config['deadline_ns'])
    need(session.config['condition']=='P','P_only_product');arguments=validate_observe_arguments(arguments)
    request_id=uuid.uuid4().hex if request_id is None else request_id
    folder=session.workspace/'product_calls'/request_id;folder.mkdir(parents=True,exist_ok=False)
    context=_context(session);host=context['host'];service=context['service'];server=context['server']
    start_sequence=max((int(path.name.split('_')[-1]) for path in session.workspace.glob('call_*')),default=0)
    result=None;error=None;rows=[];images=[]
    try:
        request=dict(jsonrpc='2.0',id=request_id,method='tools/call',
            params=dict(name='human_eye_scene_observe',arguments=arguments))
        save(folder/'REQUEST.json',request)
        # Reuse the existing cooperative request scope and shorten it to the
        # task's original absolute deadline; do not mutate persistent config,
        # reset worker lifetime, or increase the native default10s lease.
        with service._request_budget() as budget:
            remaining=(session.config['deadline_ns']-time.perf_counter_ns())/1e9
            need(budget is not None and remaining>0,'task_deadline_forwarding')
            budget['deadline']=min(budget['deadline'],time.monotonic()+remaining)
            result=server.handle_jsonrpc_message(request)
        content=result.get('result',{}).get('content',[])
        images=[(index,block) for index,block in enumerate(content) if block.get('type')=='image']
        # Even expired returned blocks were constructed and cost something.
        # Preserve that raw response before deciding whether it may be used.
        save(folder/'MCP_RESPONSE.json',result);check(session.config['deadline_ns'])
        if not host.is_alive:
            session.abort('product_host_transport_unknown_no_reconnect')
            need(False,'product_host_poisoned')
        text=[block['text'] for block in content if block.get('type')=='text']
        ledger=ImageLedger(session.workspace)
        for index,block in images:
            need(block.get('mimeType')=='image/png','product_png_mime')
            raw=base64.b64decode(block['data'],validate=True)
            image=ledger.register_external_image(raw,label='P MCP block '+str(index),origin='unchanged_actual_live_MCP')
            rows.append(dict(**image,mcp_content_index=index,public_mcp_png_sha256=hashlib.sha256(raw).hexdigest()))
        check(session.config['deadline_ns'])
        metadata=None
        if text:
            try:metadata=json.loads(text[0])
            except ValueError:pass
        response=dict(schema='visual004-P-observation-v1',request_id=request_id,
            mcp_text=text,mcp_is_error=bool(result.get('error') or result.get('result',{}).get('isError')),
            rpc_error=result.get('error'),images=rows,
            visual_delivery=None if type(metadata) is not dict else metadata.get('visual_delivery'),
            actual_product_metadata=metadata,original_task_deadline_ns=session.config['deadline_ns'],
            operator_selected_pair_for_support_only=operator_support_check,
            actual_model_image_delivery_confirmed=False,
            scope='actual MCP output prepared, per-image actual host block proof still required')
        save(folder/'RESPONSE_WITH_IMAGE_REFS.json',response);check(session.config['deadline_ns']);return response
    except BaseException as exc:
        error=dict(type=type(exc).__name__,reason=str(exc))
        if not host.is_alive:session.abort('product_host_transport_unknown_no_reconnect')
        raise
    finally:
        save(folder/'COST.json',dict(started_ns=start,finished_ns=time.perf_counter_ns(),elapsed_ns=time.perf_counter_ns()-start,
            coordinator_process_id=os.getpid(),persistent_service_instance_id=id(service),persistent_host_instance_id=id(host),
            original_task_deadline_ns=session.config['deadline_ns'],error=error,
            mcp_content_image_blocks=len(images) if result is not None else None,
            public_images_registered=len(rows),all_render_attempt_images_constructed=None,
            native_private_evidence=_private_native_evidence(session,start_sequence),
            native_private_evidence_scope='only new underlying host calls in this observation; raw PNG fields may be incomplete',
            raw_public_delivered_hashes_may_differ=True,
            pixel_opportunity_is_not_measured_pixel_readability=True,
            model_consumption=None,source_asset_unchanged=sha(session.config['asset'])==session.config['asset_sha256']))

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--workspace',required=True,type=Path)
    parser.add_argument('--arguments',required=True,type=Path);args=parser.parse_args()
    # Standalone invocation is an explicit qualification/debug path. Formal
    # tasks use the persistent owner broker so service/host memo is retained.
    session=NativeSession.open(args.workspace)
    try:result=observe(session,load(args.arguments))
    finally:close_product(session)
    sys.stdout.buffer.write(encoded(result));sys.stdout.buffer.flush()

if __name__=='__main__':main()

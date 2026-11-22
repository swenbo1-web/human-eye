"""Run one zero-model consumer/profile comparison around the existing product server."""

import argparse
import base64
from contextlib import ExitStack, contextmanager
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import sys
import time


NS = Path(__file__).resolve().parent
sys.path[:0] = [str(NS/'harness'),str(NS)]
from common import (ASSET_SHA256, CATALOGUE, DISPLAY, EXTERNAL, FORMAL, ORIGINAL_RUN, PREVIOUS, PRIOR, PRODUCT,
                    PRODUCT_BINDING, SEAL, load_retained, read, save, sha)
from bridge import DETAIL_ERROR, Owner, PRODUCT_TOOL, REGION_TASK_RULE, TOOL_LIMIT


PYTHON = Path(sys.executable).resolve()
THIN = NS/'consumer/thin_stdio.py'
SHARED = read(SEAL/'SHARED_DEPENDENCY.json')
BINDING = read(PRODUCT_BINDING)
O = read(CATALOGUE)


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def rpc(identifier, method, **params):
    return {'jsonrpc':'2.0','id':identifier,'method':method,'params':params}


def hello(client, name):
    response = client.call(rpc('initialize','initialize',protocolVersion='2025-03-26',capabilities={},
                               clientInfo={'name':name,'version':'1'}))
    require(response.get('result',{}).get('capabilities',{}).get('tools') is not None, 'actual_stdio_initialize_failed/' + name)
    client.call({'jsonrpc':'2.0','method':'notifications/initialized'})
    catalogue = client.call(rpc('tools','tools/list'))
    return response,catalogue


def text(result):
    return [block['text'] for block in result['content'] if block['type']=='text']


def pngs(result):
    return [base64.b64decode(block['data'],validate=True) for block in result['content'] if block['type']=='image']


def metrics(result):
    return {'text_bytes':sum(len(block.encode()) for block in text(result)),
            'PNG':[{'bytes':len(png),'sha256':sha256(png).hexdigest()} for png in pngs(result)],
            'error':result['isError']}


def timing(record):
    return {key:record.get(key) for key in ('index','TX_bytes','RX_bytes','RX_sha256','started_ns','elapsed_ns',
                                           'stdin_flushed_ns','received_complete_ns','consumer_json_decoded_ns')}


@contextmanager
def stock(root, slot, transport, deadline):
    root.mkdir()
    worker = root/'worker'
    client = transport.StdioClient([str(PYTHON),'-IB',str(NS/'product_replay.py'),'--worker',str(worker),slot],
                                   root,root/'wire',deadline)
    try:
        identity,catalogue = hello(client,'isolated-installed-observe')
        source = identity['result']['_meta']['human_eye']
        require(source['source_sha256']==PRODUCT['source_sha256'] and source['source_kind']=='installed_distribution'
                and catalogue['result']['tools']==O,'actual_installed_identity_or_stock_directory_changed')
        save(root/'IDENTITY.json', identity)
        save(root/'TOOLS.json', catalogue)
        yield client
    finally:
        closed=client.finish()
        save(root/'STOCK_CLOSE.json',closed)
        require(closed['confirmed'] and closed['exit_code']==0,'actual_installed_stdio_did_not_close')


class ReplayRuntime:
    """Forward requests to stock stdio. Only the ordinary image device uses saved bytes."""

    def __init__(self, root, arm, client, slot, deadline):
        frame = load_retained('_region_task_profile_frame_'+arm, FORMAL/'frame_device.py')
        self.folder,self.client,self.product_tools = root,client,O
        self.public_requests = []
        self.device = frame.FrameDevice(runroot=root,asset_sha256=ASSET_SHA256,group='P',label=arm,
                                       native_call=self.forbid,terminal_call=self.forbid,phase='qualification')
        self.buffers,self.cameras = self.device.buffers,self.device.cameras
        self.image_specification = self.device.image_specification
        preserved = ORIGINAL_RUN/'slots'/slot/'product_full/call_001/SERVICE_RESULT.json'
        producer = read(preserved)
        cache = root/'same_scope_native'
        cache.mkdir()
        originals = []
        for index,row in enumerate(producer['frames']):
            original = Path(row['image_path']).resolve(strict=True)
            raw = original.read_bytes()
            require(sha256(raw).hexdigest()==row['image_sha256'], 'actual_archived_frame_changed')
            path=cache/f'{index:02}-{original.name}'
            path.write_bytes(raw)
            ref=row['image_ref']
            require(ref not in self.device.by_ref,'actual_original_frame_reference_repeated')
            item={'ref':ref,'scope_id':row['scope_id'],'view_name':row['view_name'],'frame_identity':row['frame_identity'],
                  'PNG':str(path),'PNG_sha256':row['image_sha256'],'size_px':row['pose']['size_px'],'origin':'product'}
            self.device.by_ref[ref]=item
            originals.append({**item,'source_path':str(original),'bytes':len(raw)})
        require(len(originals)==3 and sum(row['view_name']=='SCENE' for row in originals)==2
                and len({row['scope_id'] for row in originals})==3,'same_view_name_different_scopes_control_missing')
        self.originals=originals
        self.deadline=deadline
        save(root/'BOUND_ORIGINALS.json',originals)

    def forbid(self, *args, **kwargs):
        raise AssertionError('offline_profile_must_not_enter_Blender_or_construct')

    def public_request(self, arguments):
        index=len(self.public_requests)+1
        request=rpc('observe-'+str(index),'tools/call',name=PRODUCT_TOOL,arguments=arguments)
        started=time.perf_counter_ns()
        response=self.client.call(request)
        row={'index':index,'started_ns':started,'response_ns':time.perf_counter_ns(), 'request':request,
             'response':response,'receipt':self.client.records[-1]}
        self.public_requests.append(row)
        return response


@contextmanager
def endpoint(root, arm, client, slot, deadline):
    root.mkdir()
    runtime=ReplayRuntime(root,arm,client,slot,deadline)
    owner=Owner(runtime,{'label':arm,'group':'P','phase':'qualification','worker_deadline_ns':deadline,
                         'output':str(root/'owner')})
    try:
        where=owner.start(root/'ENDPOINT.json')
        yield owner,runtime,where
    finally:
        closed=owner.close()
        save(root/'OWNER_CLOSE.json',closed)
        require(closed['confirmed'] and not closed['errors'] and not closed['transport_errors'],
                'actual_owner_transport_did_not_close/'+arm)


def cases(requests, prefix, runtime):
    def product(key, args=None, *, rejected=False):
        return (key,PRODUCT_TOOL,args if args is not None else requests[key],rejected)

    names=('source_region_full','source_region_no_image','source_region_unknown','discover_no_image','active_other')
    if prefix=='QA':
        return [product('discover_full'),product('discover_brief'), *(product(name) for name in names)]
    return [product('explicit_full_rejected',requests['discover_full'],rejected=True),
            product('discover_brief'),
            ('same_name_scopes_read','read_images',{'refs':[row['ref'] for row in runtime.originals]},False),
            product('discover_omitted'),*(product(name) for name in names),
            product('explicit_null_rejected',{**requests['discover_brief'],'response_detail':None},rejected=True),
            ('common_tool_retained','execute_python',{'code':'print(7 * 6)'},False),
            product('permitted_repeat',requests['discover_omitted']),
            product('outer_budget_rejected',requests['discover_brief'],rejected=True)]


def verify_read_images(result,runtime):
    content=result['content']
    require([row['type'] for row in content]==['text','image']*len(runtime.originals), 'common_image_caption_block_order_changed')
    for index,row in enumerate(runtime.originals):
        title, bound=content[2*index]['text'].split('\n',1)
        item=json.loads(bound)
        png=base64.b64decode(content[2*index+1]['data'],validate=True)
        require(title.startswith(row['ref']+' ') and Path(item['local_image_path'])==Path(row['PNG'])
                and item['image_sha256']==row['PNG_sha256'] and sha256(png).hexdigest()==row['PNG_sha256']
                and png==Path(row['source_path']).read_bytes(),'common_original_image_scope_or_path_changed')


def run_outer(transport, root, arm, owner, runtime, where, requests, deadline):
    folder=root/'direct'
    folder.mkdir()
    client=transport.StdioClient([str(PYTHON),'-IB','-X','utf8',str(THIN),'--endpoint',str(where),
                                  '--audit',str(folder/'attachments')],folder,folder/'wire',deadline)
    outputs={}
    try:
        _, tools=hello(client,'local-profile-probe-'+arm)
        save(folder/'TOOLS.json',tools)
        require(tools['result']['tools']==owner.tools,'ordinary-consumer_tools_list_changed')
        for ordinal,(key,name,args,expected_error) in enumerate(cases(requests,arm,runtime),1):
            before=len(runtime.public_requests)
            call=rpc(key,'tools/call',name=name,arguments=args)
            response=client.call(call)
            body=response['result']
            require(response['id']==call['id'] and body['isError'] is expected_error,'real_outer_unexpected_result/'+arm+'/'+key)
            cache=folder/f'{ordinal:02}_{key}'
            cache.mkdir()
            save(cache/'REQUEST.json',call)
            save(cache/'RESPONSE.json',response)
            owner_record=root/'owner'/f'tool_{ordinal:02d}'
            receipt=None if key=='outer_budget_rejected' else read(owner_record/'RECEIPT.json')
            forwarded=name==PRODUCT_TOOL and not expected_error
            require(len(runtime.public_requests)==before+int(forwarded),'stock_product_dispatch_wrong/'+key)
            entry={'request':call,'response':body,'outer':timing(client.records[-1]),'owner':receipt,
                   'metrics':metrics(body),'product_dispatched':forwarded}
            if forwarded:
                row=runtime.public_requests[-1]
                require(row['request']['params']==call['params'] and row['response']['result']==body,
                        'bridge_changed_explicit_arguments_or_public_response/'+key)
                entry['stock']=timing(row['receipt'])
            if key.endswith('_rejected'):
                require(not (owner_record/'PRODUCT_ARGUMENTS.json').exists(),
                        'rejected_request_reached_stock_product/'+key)
                msg,=text(body)
                error='business_tool_attempt_budget_exhausted' if key=='outer_budget_rejected' else DETAIL_ERROR
                require(msg=='ValueError: '+error, 'legacy_argument_rejection_envelope_changed/'+key)
                if key=='outer_budget_rejected':
                    require(ordinal==TOOL_LIMIT+1 and not owner_record.exists(),'outer_attempt_limit_changed')
            if key=='same_name_scopes_read':
                verify_read_images(body,runtime)
            if key=='common_tool_retained':
                require(json.loads(text(body)[0])['stdout'].strip()=='42','ordinary_session_changed')
            outputs[key]=entry
        save(folder/'CALLS.json',outputs)
        return tools['result']['tools'],outputs
    finally:
        closed=client.finish()
        save(folder/'OUTER_CLOSE.json',closed)
        require(closed['confirmed'] and closed['exit_code']==0,'actual_outer_stdio_did_not_close/'+arm)


def owner_budget(root, owner, runtime, where, request):
    """Probe the independent Owner attempt ceiling after thin refuses its own last attempt."""
    import bridge
    exchange=run_path(str(PRIOR/'thin_stdio.py'))['exchange']
    attempt=TOOL_LIMIT+1
    record=root/'owner'/f'tool_{attempt:02d}'
    require(owner.rows[-1]['attempt']==TOOL_LIMIT and not record.exists(),'thin_budget_control_not_first')
    call=rpc('owner_budget_rejected','tools/call',name=PRODUCT_TOOL,arguments=request)
    count=len(runtime.public_requests)
    started=time.perf_counter_ns()
    response=exchange(read(Path(where)),call,attempt,bridge)
    receipt=read(record/'RECEIPT.json')
    require(response['result']['isError'] and text(response['result'])==['ValueError: business_tool_attempt_budget_exhausted']
            and receipt['attempt']==attempt and receipt['RPC_id']==call['id'] and receipt['is_error'] is True
            and not (record/'PRODUCT_ARGUMENTS.json').exists() and len(runtime.public_requests)==count,
            'independent_owner_attempt_budget_did_not_reject')
    proof={'passed':True,'layer':'Owner direct retained loopback transport','attempt':attempt,
           'zero_product_dispatch':True,'elapsed_ns':time.perf_counter_ns()-started,
           'request':call,'response':response,'owner':receipt}
    save(root/'OWNER_BUDGET.json',proof)
    return proof


def check_catalogues(a,b):
    from copy import deepcopy
    expected=deepcopy(a)
    tool,=[row for row in expected if row['name']==PRODUCT_TOOL]
    require(tool==next(row for row in O if row['name']==PRODUCT_TOOL),'stock_tool_definition_changed')
    tool['inputSchema']['allOf'].append(REGION_TASK_RULE)
    require(b==expected,'model_facing_directory_diff_outside_one_profile_rule')


def compatible(stock, candidate, name):
    if stock==candidate:
        return 'identical'
    require(name=='source_region_full','unrelated_response_changed/'+name)
    from copy import deepcopy
    original, changed = deepcopy(stock), deepcopy(candidate)
    for result in (original,changed):
        body=json.loads(result['content'][0]['text'])
        trace=body['request_trace']
        for key in ('request_id','trace_id'):
            require(type(trace.pop(key)) is str,'expected_fresh_runtime_trace_identifier_missing')
        result['content'][0]['text']=json.dumps(body,ensure_ascii=False,separators=(',',':'))
    require(original==changed,'same_source_response_changed_outside_two_fresh_trace_identifiers')
    return 'identical_except_fresh_request_trace.request_id_and_trace_id'


def run_trial(root):
    from cli_probe import probe
    from freeze import verify
    from product_replay import requests

    frozen=verify()
    root.mkdir(parents=True,exist_ok=False)
    transport=load_retained('_region_task_profile_actual_stdio',DISPLAY/'harness/reused/stdio_checks.py')
    deadline=time.perf_counter_ns()+180_000_000_000
    programme=requests('P3')
    cli, arms={},{}
    with ExitStack() as stack:
        for arm in ('QA','QB'):
            client=stack.enter_context(stock(root/('stock_'+arm),'P3',transport,deadline))
            owner,runtime,where=stack.enter_context(endpoint(root/arm,arm,client,'P3',deadline))
            arms[arm]=(owner,runtime,where)
        for arm,(owner,runtime,where) in arms.items():
            cli[arm]=probe(root/arm/'cli',where,arm,owner.tools)
        delivered={arm:run_outer(transport,root/arm,arm,owner,runtime,where,programme,deadline)
                   for arm,(owner,runtime,where) in arms.items()}
        budget=owner_budget(root/'QB',*arms['QB'],programme['discover_brief'])
        (a,stock_calls),(b,trial_calls)=delivered['QA'],delivered['QB']
        check_catalogues(a,b)
        unchanged={name:compatible(stock_calls[name]['response'],trial_calls[name]['response'],name) for name in
                   ('source_region_full','source_region_no_image','source_region_unknown','discover_no_image','active_other','discover_brief')}
        require(trial_calls['discover_brief']['response']==trial_calls['discover_omitted']['response']
                ==trial_calls['permitted_repeat']['response'],'exact_same_source_compatible_replies_changed')
    actual={'P3':{'discover_full':stock_calls['discover_full']['response'],
                  **{name:trial_calls[name]['response'] for name in ('discover_brief','discover_omitted')}},'P2':{}}
    p2=requests('P2')
    with stock(root/'stock_P2','P2',transport,deadline) as stock_p2:
        for name in ('discover_full','discover_brief','discover_omitted'):
            req=rpc(name,'tools/call',name=PRODUCT_TOOL,arguments=p2[name])
            res=stock_p2.call(req)
            require(res.get('id')==name and res['result']['isError'] is False,'stock_P2_archived_request_failed/'+name)
            actual['P2'][name]=res['result']
    checker=run_path(str(PREVIOUS/'evidence_check.py'))
    compatibility=checker['check_catalogue'](a,b)
    golden=checker['check_products'](actual)
    save(root/'GOLDEN_COMPARED.json',golden)
    proof={'passed':True,'freeze_sha256':frozen,'model_starts':0,'Blender_starts':0,'new_rasters':0,'extra_API_calls':0,
           'profiled_result':metrics(trial_calls['discover_brief']['response']),
           'original_result':metrics(stock_calls['discover_full']['response']),
           'directory_delta_UTF8_bytes':len(json.dumps(b,ensure_ascii=False,separators=(',',':')).encode())-
                                      len(json.dumps(a,ensure_ascii=False,separators=(',',':')).encode()),
           'no_argument_rewrites':True,'names':[x['name'] for x in a],'compatibility':unchanged,
           'catalogue_boundary_controls':compatibility,'two_proven_original_products':True,
           'outer_business':{arm:len(value[1]) for arm,value in delivered.items()},
           'product_calls':{arm:len(values[1].public_requests) for arm,values in arms.items()},
           'profile_mcp_rejections_zero_product_dispatch':['explicit_full_rejected','explicit_null_rejected'],
           'budget_rejection_zero_product_dispatch':['outer_budget_rejected','owner_budget_rejected'],
           'owner_budget':budget,'cli_registry':cli,
           'profile_setup':{arm:{'retained_startup_ns':values[0].base_startup_ns,
                 'profile_projection_ns':values[0].profile_projection_ns,'profile_publish_ns':values[0].profile_publish_ns}
                 for arm,values in arms.items()}}
    save(root/'TRIAL.json',proof)
    return proof


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'pinned_isolated_interpreter_required')
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--output',type=Path,default=EXTERNAL/'integrated')
    args=cli.parse_args()
    require(args.output.resolve()==(EXTERNAL/'integrated').resolve(),'only_registered_integrated_output_required')
    sys.path[:0]=[BINDING['dependency_root'],SHARED['dependency_root']]
    try:
        proof=run_trial(args.output.resolve())
        print(json.dumps({key:proof[key] for key in ('passed','freeze_sha256','directory_delta_UTF8_bytes',
                   'outer_business','product_calls','profiled_result','original_result')},ensure_ascii=True),flush=True)
    except Exception as error:
        if args.output.is_dir() and not (args.output/'TRIAL.json').exists():
            save(args.output/'TRIAL.json',{'passed':False,'error_type':type(error).__name__,'error':str(error),
                                           'model_starts':0,'Blender_starts':0,'new_rasters':0,'extra_API_calls':0})
        raise

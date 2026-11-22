"""Check two current whole-object measurements over the original public path."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import sys
import time

NS=Path(__file__).resolve().parents[1]
V=NS.parent
TOOL='human_eye_scene_observe'


def require(ok,reason):
    if not ok:
        raise ValueError(reason)


def arguments(label):
    require(label in ('QA','QB'),'register an original qualification arm')
    first,second=json.loads((NS/'inputs/QUALIFICATION_PAIRS.json').read_bytes())
    invalid=deepcopy(first)
    invalid['include_image']=True
    return (invalid,first,second)


def body(result):
    require(len(result.get('content',[]))==1 and result['content'][0]['type']=='text',
            'qualification expected one text block')
    return json.loads(result['content'][0]['text'])


def run_calls(call,label):
    invalid,*pairs=arguments(label)
    rejected=call(TOOL,invalid)
    require(rejected['isError'] is True
            and body(rejected)['error'].startswith('task queries require include_image=false and selectors only in query.objects'),
            'expected original whole task image refusal missing')
    evidence={}
    for args in pairs:
        reference=args['query']['objects'][1]['name']
        result=call(TOOL,args)
        packet=body(result)
        require(result['isError'] is False and packet['status']=='observed'
                and packet['schema_version']=='task-query-v3','actual whole object recovery was not measured')
        fact=packet['facts']['surface_proximity']
        require(fact['status']=='measured' and fact['witness_status']=='measured'
                and ('exact_source_triangles' in fact['value']['nearest_witness']) is (label=='QB')
                and 'source_triangles' not in fact['value']['nearest_witness'],
                'actual A/B whole witness response shape changed/'+reference)
        evidence[reference]=len(result['content'][0]['text'].encode('utf8'))
    return {'passed':False,'phase':'await_actual_close','no_images':True,'selected_body_bytes':evidence}


def run_diagnostic(folder, endpoint, deadline, group, owner, result, *, plan=run_calls):
    from common import save

    label=result['label']
    require(group=='P' and label in ('QA','QB'),'registered_qualification_slot_required')
    root=Path(folder)/'client'
    transport=run_path(str(V/'m4_source_region_display_001/harness/reused/stdio_checks.py'))
    client=transport['StdioClient'](
        [sys.executable,'-IB','-X','utf8',str(NS/'consumer/thin_stdio.py'),'--endpoint',str(endpoint),
         '--audit',str(root/'attachments')],folder,root/'transport',deadline)

    def call(name,arguments):
        i=len(result['diagnostic_calls'])+1
        directory=root/f'call_{i:02}'
        directory.mkdir()
        request={'jsonrpc':'2.0','id':f'qualification-{i}','method':'tools/call','params':{'name':name,'arguments':arguments}}
        save(directory/'REQUEST.json',request)
        row={'index':i,'name':name,'started_ns':time.perf_counter_ns(),
             'request_sha256':sha256((directory/'REQUEST.json').read_bytes()).hexdigest()}
        result['diagnostic_calls'].append(row)
        response=client.call(request)
        row['returned_ns']=time.perf_counter_ns()
        save(directory/'RESPONSE.json',response)
        save(directory/'RECEIPT.json',client.records[-1])
        row['response_sha256']=sha256((directory/'RESPONSE.json').read_bytes()).hexdigest()
        require(response.get('id')==request['id'] and isinstance(response.get('result'),dict)
                and 'error' not in response,'actual_qualification_RPC_failed/'+name)
        return response['result']

    try:
        init=client.call({'jsonrpc':'2.0','id':'initialize','method':'initialize','params':{
            'protocolVersion':'2025-03-26','capabilities':{},
            'clientInfo':{'name':'rounded-witness-consumption-qualification','version':'1'}}})
        save(root/'INITIALIZE.json',init)
        client.call({'jsonrpc':'2.0','method':'notifications/initialized'})
        tools=client.call({'jsonrpc':'2.0','id':'list','method':'tools/list'})
        save(root/'TOOLS.json',tools)
        require(tools['result']['tools']==owner.tools,'actual_qualification_catalogue_changed')
        pending=plan(call,label)
    finally:
        result['diagnostic_close']=closed=client.finish()
        require(closed['confirmed'] and closed['exit_code']==0 and closed['process_handle_closed'],
                'actual_qualification_consumer_close_unconfirmed')
    save(Path(folder)/'QUALIFICATION_PENDING.json',pending)
    result['qualification_pending']=pending

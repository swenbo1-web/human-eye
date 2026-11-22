"""Exercise the exact transparent consumer path for the two fixed measurements."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import sys
import time

NS = Path(__file__).resolve().parents[1]
V = NS.parent
TOOL = 'human_eye_scene_observe'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def arguments(label):
    selected = json.loads((NS/'inputs/QUALIFICATION_SELECTED.json').read_bytes())
    whole = json.loads((NS/'inputs/QUALIFICATION_WHOLE.json').read_bytes())
    invalid = deepcopy(selected)
    invalid['query']['requested_facts'].append('aabb')
    require(label in ('QA','QB'), 'invalid diagnostic arm')
    return (invalid, selected, whole)


def body(result):
    require(len(result.get('content', [])) == 1 and result['content'][0]['type'] == 'text',
            'no-image qualification expected one text block')
    return json.loads(result['content'][0]['text'])


def run_calls(call, label):
    invalid, selected, whole = arguments(label)
    rejected = call(TOOL, invalid)
    require(rejected['isError'] is True and 'requested_facts' in body(rejected)['error'],
            'invalid extra fact did not get expected original refusal')
    result = call(TOOL, selected)
    expected = 'human-eye-source-region-observation-v1' if label=='QA' else 'source-region-brief-v2'
    selected_body = body(result)
    require(result['isError'] is False and selected_body['schema'] == expected
            and selected_body['status']=='complete'
            and selected_body['observation_status']=='image_not_requested',
            'selected source result did not reach expected endpoint form')
    control = call(TOOL, whole)
    whole_body = body(control)
    require(control['isError'] is False and whole_body['status']=='observed'
            and whole_body['schema_version']=='task-query-v3'
            and whole_body['facts']['surface_proximity']['status']=='measured',
            'whole object control or recovery failed')
    return {'passed':False,'phase':'await_actual_close','no_images':True,
            'selected_body_bytes':len(result['content'][0]['text'].encode('utf8')),
            'appearances':[expected,body(control).get('schema_version')]}


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
            'clientInfo':{'name':'no-image-measurement-consumption-qualification','version':'1'}}})
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

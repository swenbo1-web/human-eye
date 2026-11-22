"""Use one public discovery and the baseline's ordinary path read in the live qualifiers."""

from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import sys
import time


NS = Path(__file__).resolve().parents[1]
V = NS.parent
TOOL = 'human_eye_scene_observe'
SCHEMA = 'active-observation-region-task-brief-v2'
CONDITIONS = {'area_min_m2':1/128,'area_max_m2':1/32,'normal_z_min':0.75}
DISCOVER = {'query':{'mode':'active_observation','region_task':CONDITIONS},'include_image':True,'response_detail':'full'}


def require(ok,reason):
    if not ok:
        raise ValueError(reason)


def rows(table):
    return [dict(zip(table['columns'],row,strict=True)) for row in table['rows']]


def complete_local_frames(result):
    require(result['isError'] is False and result['content'][0]['type']=='text','successful_region_discovery_required')
    body=json.loads(result['content'][0]['text'])
    require(body['schema']==SCHEMA,'actual_qualification_did_not_get_compact_region_packet')
    scope,frame=rows(body['scopes']),rows(body['frames'])
    found={}
    for witness in rows(body['witnesses']):
        index=witness['frame_index']
        require(type(index) is int and 0<=index<len(frame),'public_local_witness_index_outside_constructed_table')
        row=frame[index]
        block=row['native_content_block_index']
        if block is not None and scope[row['scope_index']]['scope_id']!='global':
            require(type(block) is int and 1<=block<len(result['content'])
                    and result['content'][block]['type']=='image','public_local_witness_missing_delivered_PNG')
            found[index] = row['image_ref']
    require(len(found)==len(set(found.values()))==2,'expected_two_distinct_delivered_local_qualification_frames')
    return body,found


def run_calls(call,label,*,discover=DISCOVER):
    discovered=call(TOOL,discover)
    body,frames=complete_local_frames(discovered)
    if label=='QA':
        require('witness_image_paths' not in body,'baseline_gained_candidate_path_table')
        fetched=call('read_images',{'refs':list(frames.values())})
        require(fetched['isError'] is False,'baseline_actual_public_read_images_failed')
    elif label=='QB':
        paths=body['witness_image_paths']
        require(paths['columns']==['frame_index','local_image_path'] and
                {row[0] for row in paths['rows']}==frames.keys() and len(paths['rows'])==2,
                'candidate_did_not_deliver_first_packet_paths')
    else:
        raise ValueError('only_two_registered_qualification_arms')
    return {'passed':False,'phase':'await_actual_close','witness_frame_refs':list(frames.values())}


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
            'clientInfo':{'name':'witness-path-consumption-qualification','version':'1'}}})
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

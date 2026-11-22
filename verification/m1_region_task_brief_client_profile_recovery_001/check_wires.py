"""Attest the retained consumer, Owner, and installed MCP wires after closure."""

import argparse
import base64
import hashlib
import json
from pathlib import Path


TOOL = 'human_eye_scene_observe'
BUDGET_ERROR = 'ValueError: business_tool_attempt_budget_exhausted'
PROFILE_ERROR = ('ValueError: response_detail must be brief or omitted for active_observation '
                 'with region_task in this client profile')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_bytes())


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def consume_wire(folder):
    """Read the held local process's original stdout, TX/RX and timing receipts."""
    close = read(folder/'CLOSE.json')
    spawn = read(folder/'SPAWN.json')
    require(close['confirmed'] and close['exit_code']==0 and close['pid']==spawn['pid']
            and close['process_handle_closed'] and close['reader_stopped'] and not close['forced_kill']
            and all(close['pipes_closed'].values()) and not close['errors'], 'stdio_not_reclaimed/'+str(folder))
    rows, stdout = [], bytearray()
    for index, slot in enumerate(sorted(folder.glob('rpc_*')),1):
        tx, receipt = (slot/'TX.bin').read_bytes(), read(slot/'RECEIPT.json')
        request = json.loads(tx)
        require(receipt['index']==index and receipt['id']==request.get('id')
                and receipt['method']==request['method'] and receipt['TX_bytes']==len(tx)
                and receipt['error'] is None and receipt['started_ns'] <= receipt['stdin_flushed_ns'] <= receipt['closed_ns']
                and receipt['elapsed_ns']==receipt['closed_ns']-receipt['started_ns'], 'stdio_TX_receipt_changed/'+str(slot))
        rx = (slot/'RX.bin').read_bytes() if 'id' in request else None
        reply = json.loads(rx) if rx is not None else None
        if rx is not None:
            stdout.extend(rx)
            require(reply.get('id')==request['id'] and receipt['RX_bytes']==len(rx) and receipt['RX_sha256']==digest(rx)
                    and read(slot/'RESPONSE.json')==reply
                    and receipt['started_ns']<=receipt['received_complete_ns']<=receipt['consumer_json_decoded_ns']<=receipt['closed_ns'],
                    'stdio_RX_receipt_changed/'+str(slot))
        rows.append({'request':request,'reply':reply,'tx':tx,'rx':rx,'receipt':receipt})
    require(bytes(stdout)==(folder/'stdout.raw.bin').read_bytes(), 'stdio_stdout_not_exact_RX_sequence/'+str(folder))
    return rows,close


def owner_wires(arm):
    rows=[]
    packets=read(arm/'owner'/'BRIDGE_RESULT.json')
    for index, wire in enumerate(sorted((arm/'owner').glob('rpc_*')),1):
        tx,rx=((wire/f'TCP_{kind}.bin').read_bytes() for kind in ('TX','RX'))
        request,reply=json.loads(tx),json.loads(rx)
        recorded=packets['protocol'][index-1]
        require(request['operation']=='attached_mcp' and request['args']['kind']=='native'
                and reply['request_id']==request['request_id'] and reply['ok'] is True
                and recorded['sequence']==index and recorded['send_confirmed']
                and recorded['request_bytes']==len(tx) and recorded['response_bytes']==len(rx)
                and recorded['RPC_id']==request['args']['message'].get('id') and recorded['attempt']==request['args']['attempt'],
                'owner_TCP_binding_changed/'+str(wire))
        rows.append({'request':request['args']['message'],'reply':reply['result'],'attempt':request['args']['attempt'],
                     'TX_bytes':len(tx),'RX_bytes':len(rx),'TX_sha256':digest(tx),'RX_sha256':digest(rx),
                     'elapsed_ns':recorded['closed_ns']-recorded['started_ns']})
    closure=read(arm/'OWNER_CLOSE.json')
    require(closure==read(arm/'owner'/'CLOSE.json') and closure['confirmed'] and not closure['errors']
            and not closure['transport_errors'] and len(rows)==len(packets['protocol']), 'owner_closure_or_protocol_count_changed')
    return rows,packets['calls'],closure


def find_once(items, predicate, reason):
    found=[record for record in items if predicate(record)]
    require(len(found)==1,reason)
    return found[0]


def cli_wires(arm, owner):
    root=arm/'cli'/'actual_cli_registry'
    proof,close=read(root/'CLI_PROOF.json'),read(root/'PROCESS_CLOSE.json')
    raw=(root/'003/RX.bin').read_bytes()
    proof_hash=proof['registry_response']
    require(proof['passed'] and proof['business_calls']==proof['threads_started']==proof['provider_model_launches']==0
            and proof_hash['sha256']==digest(raw) and proof_hash['bytes']==len(raw)
            and close['exit_code']==0 and close['readers_joined'] and close['thin_watcher_joined'] and not close['killed_after_timeout'],
            'registry_process_or_RPC_not_attested')
    child=close['observed_thin_process']
    require(child['confirmed'] and child['handle_closed'] and child['owned_process_handle_acquired'],
            'registry_child_not_reclaimed')
    tools=list(read(arm/'owner'/'TOOLS_SCHEMA.json'))
    registration,=json.loads(raw)['result']['data']
    require(registration['tools']=={row['name']:row for row in tools}, 'registry_directory_changed')
    wire,=(root/'mcp_audit').glob('bridge_*')
    require(read(wire/'STARTED.json')['pid']==child['pid'], 'registry_child_wrong_identity')
    eof_published=(wire/'EXIT.json').is_file()
    require(eof_published==proof['mcp_tools_list']['EOF_receipt_present'],'registry_thin_EOF_receipt_changed')
    for name in ('001','003'):
        request,reply=read(wire/name/'TX.bin'),read(wire/name/'RX.bin')
        find_once(owner,lambda row: row['attempt'] is None and row['request']==request and row['reply']==reply,
                  'CLI_registry_did_not_use_live_Owner/'+name)
    return {'registered_tools':len(tools),'app_server_exit_code':close['exit_code'],'thin_exit_code':child['exit_code'],
            'thin_normal_EOF_receipt':eof_published,'registry_RX_bytes':len(raw),
            'registry_RTT_ns':proof['app_server_RPC']['mcpServerStatus/list']['elapsed_ns']}


def plain_error(reply, expected):
    return reply['result']=={'content':[{'type':'text','text':expected}],'isError':True}


def stock_calls(root):
    records, close=consume_wire(root/'wire')
    require(close==read(root/'STOCK_CLOSE.json'),'stock_exit_copy_changed')
    eof=read(root/'worker'/'EOF.json')
    require(eof['closed'] and eof['host_attempts']==eof['new_rasters']==0
            and eof['source_sha256']=='65bd1ec8009f8024e85ef1cd30c1229957cceb1c1766c8e5b62f2ef2489ce48c',
            'stock_worker_side_effect_or_identity_change')
    calls=[row for row in records if row['request']['method']=='tools/call']
    require(eof['observe_dispatches']==len(calls) and all(row['reply'].get('result',{}).get('isError') is False for row in calls),
            'stock_producer_dispatch_count_or_eligibility_changed')
    produced=[json.loads(line) for line in (root/'worker'/'PRODUCER_CALLS.jsonl').read_bytes().splitlines()]
    require([row['index'] for row in produced]==list(range(1,len(calls)+1)), 'stock_producer_wire_count_changed')
    return calls,close,eof


def image_readback(arm, request, reply):
    originals=read(arm/'BOUND_ORIGINALS.json')
    sc=[row for row in originals if row['view_name']=='SCENE']
    require(len(sc)==2 and all(len({row[key] for row in sc})==2 for key in ('scope_id','ref','frame_identity')),
            'SCENE_references_or_scopes_aliased')
    blocks=reply['result']['content']
    require(request['params']['arguments']['refs']==[row['ref'] for row in originals]
            and [block['type'] for block in blocks]==['text','image']*len(originals), 'public_image_readback_shape_or_order_changed')
    for number,row in enumerate(originals):
        caption, description=blocks[2*number]['text'].split('\n',1)
        image=blocks[2*number+1]
        png=base64.b64decode(image['data'],validate=True)
        local=Path(row['PNG']).resolve(strict=True)
        require(image['mimeType']=='image/png' and caption.startswith(row['ref']+' ')
                and Path(json.loads(description)['local_image_path']).resolve(strict=True)==local
                and local.is_relative_to(arm.resolve()) and png==local.read_bytes()==Path(row['source_path']).read_bytes()
                and digest(png)==json.loads(description)['image_sha256']==row['PNG_sha256'] and len(png)==row['bytes'],
                'public_original_PNG_binding_changed')
    return {row['ref']:{key:row[key] for key in ('scope_id','view_name','frame_identity','PNG_sha256','bytes')}
            for row in originals}


def attest_arm(root, label):
    arm=root/label
    owner, attempts, owner_close=owner_wires(arm)
    registry=cli_wires(arm,owner)
    direct, direct_close=consume_wire(arm/'direct'/'wire')
    require(direct_close==read(arm/'direct'/'OUTER_CLOSE.json'),'business_exit_copy_changed')
    downstream, stock_close, eof=stock_calls(root/('stock_'+label))
    expected=read(arm/'direct'/'CALLS.json')
    audit,=(arm/'direct'/'attachments').glob('bridge_*')
    thin_exit=read(audit/'EXIT.json')
    require(thin_exit['normal_exit'] and thin_exit['requests']==len(direct)
            and thin_exit['attempts']==len(expected) and thin_exit['pid']==direct_close['pid'], 'business_thin_EOF_unconfirmed')
    totals={'TX':0,'RX':0}
    forwarded, facts, images=0,{},{}
    for ordinal, row in enumerate(direct,1):
        caller=audit/f'{ordinal:03d}'
        rx=row['rx']
        request,reply=row['request'],row['reply']
        receipt=read(caller/'RECEIPT.json')
        require((caller/'TX.bin').read_bytes()==row['tx'] and receipt['method']==request['method']
                and receipt['RPC_id']==request.get('id') and receipt['request_bytes']==len(row['tx']), 'direct_thin_TX_receipt_changed')
        totals['TX']+=len(row['tx'])
        if rx is not None:
            require((caller/'RX.bin').read_bytes()==rx and receipt['response_bytes']==len(rx)
                    and receipt['flush_completed_ns'] is not None,'direct_thin_RX_receipt_changed')
            totals['RX']+=len(rx)
        if request['method']!='tools/call':
            continue
        name, params=request['id'],request['params']
        retained=expected[name]
        require(retained['request']==request and retained['response']==reply['result'], 'trial_receipt_not_bound_to_raw_business/'+name)
        matching=[item for item in owner if item['request']==request]
        if name=='outer_budget_rejected':
            require(not matching and receipt['origin']=='budget_refusal' and not receipt['owner_TCP_attempted']
                    and receipt['attempt']==13 and plain_error(reply,BUDGET_ERROR),'thin_budget_control_hit_wrong_layer')
            facts[name]={'attempt':13,'layer':'thin','product_dispatch':False,'outer_RX_bytes':len(rx),
                         'outer_elapsed_ns':row['receipt']['elapsed_ns']}
            continue
        hit,=matching
        num=receipt['attempt']
        tool_folder=arm/'owner'/f'tool_{num:02d}'
        owner_receipt=read(tool_folder/'RECEIPT.json')
        require(hit['reply']==reply and hit['attempt']==num and receipt['owner_TCP_attempted'] and receipt['origin']=='owner'
                and owner_receipt==attempts[num-1]==retained['owner']
                and read(tool_folder/'REQUEST.json')==request and read(tool_folder/'RESPONSE.json')==reply,
                'direct_owner_business_wires_changed/'+name)
        entry={'attempt':num,'layer':'owner','product_dispatch':retained['product_dispatched'],
               'profile_check_ns':owner_receipt.get('client_profile',{}).get('check_ns'),
               'outer_TX_bytes':len(row['tx']),'outer_RX_bytes':len(rx),'outer_elapsed_ns':row['receipt']['elapsed_ns'],
               'owner_TCP_TX_bytes':hit['TX_bytes'],'owner_TCP_RX_bytes':hit['RX_bytes'],'owner_TCP_elapsed_ns':hit['elapsed_ns']}
        if retained['product_dispatched']:
            outgoing=downstream[forwarded]
            forwarded+=1
            require(outgoing['request']['params']==params and outgoing['reply']['result']==reply['result']
                    and read(tool_folder/'PRODUCT_ARGUMENTS.json')==params['arguments']
                    and read(tool_folder/'PRODUCT_REQUEST.json')==outgoing['request']
                    and read(tool_folder/'PRODUCT_RESPONSE.json')==outgoing['reply'], 'unchanged_stock_request_or_response_not_bound/'+name)
            entry.update(stock_TX_bytes=len(outgoing['tx']),stock_RX_bytes=len(outgoing['rx']),
                         stock_elapsed_ns=outgoing['receipt']['elapsed_ns'])
        else:
            require(not list(tool_folder.glob('PRODUCT_*')),'stock_artifacts_present_for_local_call/'+name)
        if name in ('explicit_full_rejected','explicit_null_rejected'):
            explicit=params['arguments']['response_detail']
            require(explicit==('full' if name=='explicit_full_rejected' else None) and plain_error(reply,PROFILE_ERROR)
                    and not entry['product_dispatch'] and owner_receipt['client_profile']['accepted'] is False,
                    'explicit_disallowed_request_changed_or_dispatched/'+name)
        elif name=='same_name_scopes_read':
            images=image_readback(arm,request,reply)
        facts[name]=entry
    if label=='QB':
        require(facts['explicit_full_rejected']['attempt']+1==facts['discover_brief']['attempt']
                and facts['explicit_null_rejected']['attempt']+1==facts['common_tool_retained']['attempt']
                and facts['discover_brief']['product_dispatch'] and facts['discover_omitted']['product_dispatch']
                and facts['permitted_repeat']['product_dispatch'], 'next_business_request_did_not_recover')
        budget=find_once(owner,lambda item:item['request'].get('id')=='owner_budget_rejected','direct_Owner_budget_wire_missing')
        number=budget['attempt']
        target=arm/'owner'/f'tool_{number:02d}'
        require(number==13 and budget['request']['params']['name']==TOOL and plain_error(budget['reply'],BUDGET_ERROR)
                and read(target/'REQUEST.json')==budget['request'] and read(target/'RESPONSE.json')==budget['reply']
                and read(target/'RECEIPT.json')['is_error'] and not list(target.glob('PRODUCT_*')),
                'direct_Owner_budget_control_did_not_refuse_before_dispatch')
        facts['owner_budget_rejected']={key:budget[key] for key in ('attempt','TX_bytes','RX_bytes','elapsed_ns')}
    require(len(downstream)==forwarded and totals['TX']==thin_exit['complete_tx_bytes']
            and totals['RX']==thin_exit['complete_rx_bytes'], 'profile_stock_dispatch_count_or_wire_totals_changed')
    return {'cases':facts,'stock_observations':forwarded,'business_attempts':len(expected),'direct_stdio_bytes':totals,
            'image_readback':images,'CLI_registry':registry,'stock_exit_code':stock_close['exit_code'],
            'business_thin_exit_code':direct_close['exit_code'],'Owner_closed':owner_close['confirmed'],
            'real_stock_encoder_events_ns':eof['encoder_events']}


def certify(root):
    """Require full evidence for both arms, or raise without granting admission."""
    root=Path(root).resolve(strict=True)
    arm_results={label:attest_arm(root,label) for label in ('QA','QB')}
    aux,close,_=stock_calls(root/'stock_P2')
    require([row['request']['params']['arguments'].get('response_detail','omitted') for row in aux]
            == ['full','brief','omitted'],'stock_P2_three_unchanged_shapes_missing')
    return {'passed':True,'arms':arm_results,'P2_stock_observations':len(aux),'P2_stock_exit_code':close['exit_code'],
            'provider_behavior':'unobserved','model_starts':0,'Blender_starts':0,'new_rasters':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--output', type=Path)
    args=parser.parse_args()
    result=json.dumps(certify(args.root),ensure_ascii=False,allow_nan=False,indent=2)+'\n'
    if args.output is None:
        print(result,end='')
    else:
        with args.output.open('x',encoding='utf8',newline='\n') as stream:
            stream.write(result)

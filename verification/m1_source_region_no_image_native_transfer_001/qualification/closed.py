"""Validate the original closed qualification slots before model admission."""
import json
from pathlib import Path
from runpy import run_path

NS = Path(__file__).resolve().parents[1]
V = NS.parent
RETAINED = V/'perf050_dense_micro_surface_holdout_recovery_001/qualification/verify.py'


def recorded_calls(slot,result):
    import diagnostic as D
    from common import read,sha

    check=run_path(str(RETAINED))
    p = result['label']=='QP'
    specs=[('render_local',D.PROBE),('execute_blender_code',{'code':D.read_code()})]
    raw = D.ordinary(read(slot/'client/call_02/RESPONSE.json')['result'])
    specs += [('execute_python',{'code':D.setup_code(raw)}),('execute_python',{'code':D.solve_code()})]
    if p:
        for case in D.cases():
            specs.extend((D.TOOL,case[key]) for key in ('qa_selected','qa_whole'))
    log=result['diagnostic_calls']
    bridge,=(slot/'client/attachments').glob('bridge_*')
    closed=read(bridge/'EXIT.json')
    D.require(closed['normal_exit'] and closed['attempts']==len(specs)==len(log),
              'actual qualification roster/transparent consumer close changed')
    calls=[]
    for i,(event,(name,args)) in enumerate(zip(log,specs,strict=True),1):
        folder=slot/'client'/f'call_{i:02d}'
        req,reply,receipt=(read(folder/file) for file in ('REQUEST.json','RESPONSE.json','RECEIPT.json'))
        D.require(req['params']=={'name':name,'arguments':args} and req['id']==reply['id']
                  and event['index']==i and event['name']==name
                  and sha(folder/'REQUEST.json')==event['request_sha256']
                  and sha(folder/'RESPONSE.json')==event['response_sha256'],
                  'actual arm changed args or reply identity')
        D.body(reply['result'],error=i==1)
        tx,rx=check['rpc_pair'](slot/'client/transport',receipt,req,reply)
        transport=bridge/f'{receipt["index"]:03d}'
        held=slot/'owner'/f'tool_{i:02d}'
        D.require((transport/'TX.bin').read_bytes()==tx and (transport/'RX.bin').read_bytes()==rx
                  and read(held/'REQUEST.json')==req and read(held/'RESPONSE.json')==reply
                  and read(held/'RECEIPT.json')['attempt']==i,
                  'owner/transparent stdio did not preserve actual original wire')
        calls.append({'request':req,'response':reply['result'],'owner':held,
                      'TX_sha256':check['digest'](tx),'RX_sha256':check['digest'](rx),
                      'public_RTT_ns':receipt['elapsed_ns']})
    return raw,calls


def verify(slot,result):
    import diagnostic as D
    from common import ASSET,binding_for,read,sha

    slot=Path(slot).resolve(strict=True)
    label=slot.name
    p=label=='QP'
    require=D.require
    close=read(slot/'RUNTIME_CLOSE.json')
    pending=read(slot/'QUALIFICATION_PENDING.json')
    require(pending==result['qualification_pending'] and pending['phase']=='await_actual_close'
            and pending['passed'] is False and pending['no_images'] is True
            and result['status']=='completed' and result['model_consumers']==result['paid_API_calls']==0
            and result['diagnostic_close']['confirmed'] and result['diagnostic_close']['exit_code']==0
            and result['budget']['counts']['qualification_raster_actual']==0,'qualification must be closed and no-image')
    if p:
        require(close['public_MCP_close']['confirmed'] and close['public_MCP_close']['production_eof_and_exit_verified']
                and close['public_MCP_exit']['confirmed'] and close['public_MCP_exit']['exit_code']==0,
                'candidate production actual EOF or process close missing')
    else:
        require(not (slot/'mcp').exists() and not (slot/'MCP_IDENTITY.json').exists()
                and not close.get('public_MCP_close') and not close.get('public_MCP_exit'),
                'native control was exposed to a product process')
    old=run_path(str(RETAINED))
    envelope=run_path(str(V/'m4_cross_scale_live_task_formal_001/scoring/formal.py'))
    native=old['closed_wire'](slot)
    start,ready,closed=envelope['generic_process'](slot,ASSET,slot/'native/input.blend',
                                                    result['asset_sha256'],result['owned_deadline_ns'])
    first,last=(envelope['read_capture'](slot,slot/path,result[k],start['pid'],result['asset_sha256'])
        for path,k in (('initial_capture/TERMINAL_SOURCE.json','initial_source'),('TERMINAL_SOURCE.json','terminal_source')))
    fields=('source','objects','source_face_offsets','display_object_mask','display_scope','layer_collections','scene_cameras')
    require(all(first[k]==last[k] for k in fields)
            and start['created_after_ns']<=first['started_ns']<=result['ready_ns']<=result['cleanup_started_ns']
            <=last['started_ns']<=closed['closed_ns']<=result['owned_deadline_ns'],
            'owned read-only scene or deadlines changed')
    raw,calls=recorded_calls(slot,result)
    raw_stdout=json.loads(calls[1]['response']['content'][0]['text'])['stdout']
    native_rows=[(seq,row) for seq,row in native.items()
        if row['request'].get('type')=='execute_code' and
        (row['response'].get('result') or {}).get('result')==raw_stdout]
    require(len(native_rows)==1,'ordinary evaluated read was not backed by one actual Blender wire reply')
    decoded=D.ordinary(calls[3]['response'])
    require(raw['meshes']==decoded['meshes'] and raw['frame']==decoded['frame']
            and raw['scale_length']==decoded['scale_length']==1,'persistent compute did not use current ordered mesh arrays')
    checker=run_path(str(NS/'checks/evidence.py'))
    cases={str(i):{'native':checker['verify_native_case'](i,last,decoded)} for i in (1,2,3)}
    require(all(proof is not None for proof in cases.values()),'native qualification scope missing')
    if p:
        installed=read(binding_for(label))
        oracle=run_path(str(V/'m4_cross_scale_discovery_001/oracle/check_saved.py'))
        captures,cmds=oracle['decode_captures'](slot,installed,oracle['Audit']())
        accepted=[row for row in cmds if row['command']['command'] in ('capture','capture_scene','capture_task')]
        require(len(captures)==len(accepted),'actual capture ordering not one-to-one')
        for i in (1,2,3):
            left_index=2*i-1
            scoped=[]
            for index in (left_index,left_index+1):
                row=calls[3+index]
                produced,rasters=old['product_result'](slot,row,index)
                require(rasters==0,'unexpected product raster for explicit no-image request')
                receipt=read(slot/'product_calls'/f'call_{index:03d}'/'RECEIPT.json')
                matches=[(item,capture) for item,capture in zip(accepted,captures,strict=True)
                    if receipt['started_ns']<=native[item['wire_sequence']]['worker_event']['started_ns']
                        and native[item['wire_sequence']]['worker_event']['started_ns']
                            +native[item['wire_sequence']]['worker_event']['elapsed_ns']<=receipt['received_complete_ns']]
                require(len(matches)==1,'product producer not bound to one actual native capture')
                item,capture=matches[0]
                scoped.append((row,produced,capture,item['wire_sequence']))
            (s,sub,s_cap,s_wire),(w,whole,w_cap,w_wire)=scoped
            proof=checker['verify_product_case'](i,slot,s['response'],sub,w['response'],whole,
                binding=installed,source=last,selected_capture=s_cap,whole_capture=w_cap)
            cases[str(i)].update(product=proof,selected_native_wire=s_wire,whole_native_wire=w_wire)
    return {'passed':True,'label':label,'actual_call_count':len(calls),'no_images':True,'raster_count':0,
            'cases':cases,'ordinary_read_native_wire':native_rows[0][0],
            'ordinary_dependency_checks':pending['ordinary_dependency_checks'],
            'wire':[ {k:v for k,v in row.items() if k not in ('response','owner','request')} for row in calls],
            'source':{'sha256_start':sha(slot/'initial_capture/TERMINAL_SOURCE.json'),
                      'sha256_final':sha(slot/'TERMINAL_SOURCE.json'),'fingerprint':ready['initial_fingerprint']}}

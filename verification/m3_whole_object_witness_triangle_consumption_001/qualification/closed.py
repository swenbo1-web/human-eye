"""Bind the public no-image measurement packets to owned captures and real close."""
from pathlib import Path
from runpy import run_path

NS=Path(__file__).resolve().parents[1]
V=NS.parent
PREVIOUS=V/'m1_source_region_no_image_measurement_consumption_001/qualification/closed.py'


def recorded_calls(slot,result,**paths):
    return run_path(str(PREVIOUS))['recorded_calls'](slot,result,**paths)


def verify(slot,result):
    import diagnostic
    from common import ASSET,binding_for,read,sha

    require=diagnostic.require
    slot=Path(slot).resolve(strict=True)
    label=slot.name
    pending=read(slot/'QUALIFICATION_PENDING.json')
    close=read(slot/'RUNTIME_CLOSE.json')
    require(pending==result['qualification_pending'] and pending['phase']=='await_actual_close'
            and pending['no_images'] is True and pending['passed'] is False
            and result['status']=='completed' and result['model_consumers']==result['paid_API_calls']==0
            and result['budget']['counts']['qualification_raster_actual']==0
            and result['diagnostic_close']['confirmed'] and result['diagnostic_close']['exit_code']==0
            and close['public_MCP_close']['confirmed'] and close['public_MCP_close']['production_eof_and_exit_verified']
            and close['public_MCP_exit']['confirmed'] and close['public_MCP_exit']['exit_code']==0,
            'original owned qualification or real stdio close missing')
    retained=run_path(str(V/'perf050_dense_micro_surface_holdout_recovery_001/qualification/verify.py'))
    envelope=run_path(str(V/'m4_cross_scale_live_task_formal_001/scoring/formal.py'))
    oracle=run_path(str(V/'m4_cross_scale_discovery_001/oracle/check_saved.py'))
    wire=retained['closed_wire'](slot)
    start,ready,closed=envelope['generic_process'](slot,ASSET,slot/'native/input.blend',
                                                    result['asset_sha256'],result['owned_deadline_ns'])
    first,last=(envelope['read_capture'](slot,slot/p,result[k],start['pid'],result['asset_sha256'])
        for p,k in (('initial_capture/TERMINAL_SOURCE.json','initial_source'),('TERMINAL_SOURCE.json','terminal_source')))
    fields=('source','objects','source_face_offsets','display_object_mask','display_scope','layer_collections','scene_cameras')
    require(all(first[k]==last[k] for k in fields)
            and start['created_after_ns']<=first['started_ns']<=result['ready_ns']<=result['cleanup_started_ns']
            <=last['started_ns']<=closed['closed_ns']<=result['owned_deadline_ns'],
            'scene or original owned window changed')
    calls=recorded_calls(slot,result)
    installed=read(binding_for(label))
    captures,commands=oracle['decode_captures'](slot,installed,oracle['Audit']())
    selected=[row for row in commands if row['command']['command']=='capture_task']
    require(len(selected)==len(captures)==2,
            'each success must originate in its distinct actual selected capture')
    bindings={}
    for reference,packet in zip(('M19','M14'),calls[1:],strict=True):
        outcomes=[]
        for item,capture in zip(selected,captures,strict=True):
            event=wire[item['wire_sequence']]['worker_event']
            if packet['product_started_ns']<=event['started_ns'] and event['started_ns']+event['elapsed_ns']<=packet['product_received_ns']:
                outcomes.append((item,capture))
        require(len(outcomes)==1,'actual selected host operation detached from '+reference)
        current,capture=outcomes[0]
        require(current['command']['params']=={'selectors':[{'name':'M16'},{'name':reference}]},
                'captured original pair order changed')
        bindings[reference]=(packet,capture,current['wire_sequence'])
    proof=run_path(str(NS/'checks/evidence.py'))['verify_qualification'](
        slot,{r:row[0]['public_response'] for r,row in bindings.items()},
        {r:row[0]['producer'] for r,row in bindings.items()},
        {r:row[1] for r,row in bindings.items()},binding=installed,require_source=label=='QB',source=last)
    require(proof['passed'] is True,'independent original whole-pair proof failed')
    receipt=[{k:v for k,v in packet.items() if k not in ('public_response','producer')} for packet in calls]
    return {'passed':True,'label':label,'actual_call_count':len(calls),'no_images':True,'raster_count':0,
            'qualification':proof,'wires':receipt,'native_wires':{r:entry[2] for r,entry in bindings.items()},
            'source':{'sha256_start':sha(slot/'initial_capture/TERMINAL_SOURCE.json'),
                      'sha256_final':sha(slot/'TERMINAL_SOURCE.json'),'fingerprint':ready['initial_fingerprint'],
                      'closed_ns':closed['closed_ns']}}

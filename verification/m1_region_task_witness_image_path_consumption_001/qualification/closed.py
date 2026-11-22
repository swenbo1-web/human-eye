"""Bind the live qualifying calls and pictures to the already closed slot."""

import json
from pathlib import Path
from runpy import run_path


NS=Path(__file__).resolve().parents[1]
V=NS.parent


def verify(slot,result):
    import diagnostic
    from common import ASSET, binding_for, read, sha

    require=diagnostic.require
    slot=Path(slot).resolve(strict=True)
    label=slot.name
    base=run_path(str(V/'perf050_dense_micro_surface_holdout_recovery_001/qualification/verify.py'))
    oracle=run_path(str(V/'m4_cross_scale_discovery_001/oracle/check_saved.py'))
    original=run_path(str(V/'m4_cross_scale_live_task_formal_001/scoring/formal.py'))
    checker=run_path(str(NS/'checks/evidence.py'))
    acquired=read(slot/'QUALIFICATION_PENDING.json')
    close=read(slot/'RUNTIME_CLOSE.json')
    require(acquired==result['qualification_pending'] and acquired['passed'] is False
            and acquired['phase']=='await_actual_close' and result['status']=='completed'
            and result['model_consumers']==result['paid_API_calls']==0
            and result['diagnostic_close']['confirmed'] and result['diagnostic_close']['exit_code']==0
            and close['public_MCP_close']['confirmed'] and close['public_MCP_close']['exit_code']==0
            and close['public_MCP_close']['production_eof_and_exit_verified'] is True
            and close['public_MCP_exit']['confirmed'] and close['public_MCP_exit']['exit_code']==0,
            'actual_unconfirmed_closed_qualification/'+label)
    native=base['closed_wire'](slot)
    asset=slot/'native/input.blend'
    start,ready,closed=original['generic_process'](slot,ASSET,asset,result['asset_sha256'],result['owned_deadline_ns'])
    first,last=(original['read_capture'](slot,slot/path,result[key],start['pid'],result['asset_sha256'])
                for path,key in (('initial_capture/TERMINAL_SOURCE.json','initial_source'),('TERMINAL_SOURCE.json','terminal_source')))
    require(all(first[key]==last[key] for key in ('source','objects','source_face_offsets','display_object_mask',
                                                 'display_scope','layer_collections','scene_cameras'))
            and start['created_after_ns']<=first['started_ns']<=result['ready_ns']<=result['cleanup_started_ns']
            <=last['started_ns']<=closed['closed_ns']<=result['owned_deadline_ns'],
            'unchanged_qualification_scene_or_original_clock_unproven')
    log=result['diagnostic_calls']
    refs=acquired['witness_frame_refs']
    commands=[(diagnostic.TOOL,diagnostic.DISCOVER)]
    if label=='QA':
        commands.append(('read_images',{'refs':refs}))
    require(len(refs)==len(set(refs))==2 and [row['name'] for row in log]==[name for name,_ in commands],
            'qualification_sequence_must_keep_B_first_packet_read_images_independent')
    bridge,=list((slot/'client/attachments').glob('bridge_*'))
    bridge_close=read(bridge/'EXIT.json')
    require(bridge_close['normal_exit'] and bridge_close['attempts']==len(commands),'actual_public_thin_stdio_did_not_close')
    calls=[]
    for i,(row,(name,arguments)) in enumerate(zip(log,commands,strict=True),1):
        at=slot/'client'/f'call_{i:02}'
        request,reply,receipt=(read(at/file) for file in ('REQUEST.json','RESPONSE.json','RECEIPT.json'))
        require(request=={'jsonrpc':'2.0','id':f'qualification-{i}','method':'tools/call',
                          'params':{'name':name,'arguments':arguments}}
                and sha(at/'REQUEST.json')==row['request_sha256'] and sha(at/'RESPONSE.json')==row['response_sha256']
                and reply['id']==request['id'] and reply['result']['isError'] is False,
                'actual_public_request_or_success_changed/'+name)
        tx,rx=base['rpc_pair'](slot/'client/transport',receipt,request,reply)
        packet=bridge/f'{receipt["index"]:03}'
        owner=slot/'owner'/f'tool_{i:02}'
        held=read(owner/'RECEIPT.json')
        require((packet/'TX.bin').read_bytes()==tx and (packet/'RX.bin').read_bytes()==rx
                and read(owner/'REQUEST.json')==request and read(owner/'RESPONSE.json')==reply
                and held['attempt']==i and held['RPC_id']==request['id'],
                'actual_qualifier_wire_attempt_not_preserved/'+name)
        calls.append({'request':request,'response':reply['result'],'owner':owner,'TX_sha256':checker['digest'](tx),
                      'RX_sha256':checker['digest'](rx),'RX_bytes':len(rx),'roundtrip_ns':receipt['elapsed_ns']})
    producer,rasters=base['product_result'](slot,calls[0],1)
    installed=read(binding_for(label))
    audit=oracle['Audit']()
    captures,host_calls=oracle['decode_captures'](slot,installed,audit)
    capture_item,capture=base['current_capture_for'](host_calls,captures,native,producer)
    oracle['source_binding_checks'](capture,producer['binding'],installed,audit)
    truth=read(NS/'fixture/TRUTH.json')
    require(capture['capture_state']==producer['binding']['capture_state'],
            'actual_qualification_source_capture_detached')
    proof=checker['verify_discovery'](slot,calls[0]['response'],producer,last,binding=installed,
                                       require_paths=label=='QB',pinned_truth=truth)
    if label=='QA':
        require('witness_image_paths' not in json.loads(calls[0]['response']['content'][0]['text']),
                'baseline_first_packet_unexpectedly_provided_a_path_table')
        images=checker['verify_read_images'](slot,calls[1]['response'],producer,refs)
    else:
        images=proof['original_images']
    require(len(images)==2 and {row['ref'] for row in images}==set(refs)
            and len(producer['frames'])<=len(producer['constructed_frames'])==rasters<=12,
            'actual_selected_subset_witness_or_raster_counter_changed')
    cli=run_path(str(V/'m4_dense_region_brief_001/checks/brief_schema.py'))['cli_stages']
    fixed=cli(calls[0]['response'])
    require(fixed['passed'] and all(row['MCP_exact'] and row['history_exact'] for row in fixed['stages']),
            'actual_discovery_packet_did_not_preserve_required_fixed_CLI_evidence')
    readback_cli=cli(calls[1]['response']) if label=='QA' else None
    return {'passed':True,'current_geometry':proof,'original_images':images,'fixed_CLI':fixed,'read_images_CLI':readback_cli,
            'actual_call_count':len(calls),'constructed':len(producer['constructed_frames']),
            'delivered':len(producer['frames']),'gold_capture_wire_index':capture_item['wire_sequence'],
            'original_wire':[{'tool':call['request']['params']['name'],**{key:call[key] for key in
                             ('TX_sha256','RX_sha256','RX_bytes','roundtrip_ns')}} for call in calls],
            'process_close':{'Blender':close['Blender_close'],'MCP':close['public_MCP_close']},
            'source':{'initial_fingerprint':ready['initial_fingerprint'],'closed_ns':closed['closed_ns'],
                      'initial_sha256':sha(slot/'initial_capture/TERMINAL_SOURCE.json'),
                      'terminal_sha256':sha(slot/'TERMINAL_SOURCE.json')}}

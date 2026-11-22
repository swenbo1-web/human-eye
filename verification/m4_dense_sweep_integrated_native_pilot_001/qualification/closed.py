"""Qualify each no-model arm only after the original worker WIRE is flushed."""

import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
DIAG = run_path(str(HERE/'diagnostic.py'))
VISUAL = run_path(str(HERE/'visual.py'))
PRIOR = run_path(str(V/'perf050_dense_micro_surface_holdout_recovery_001/qualification/verify.py'))
E = VISUAL['E']
require,read,digest = (VISUAL[key] for key in ('require','read','digest'))


def public_records(slot, result, expected):
    log = result['diagnostic_calls']
    require(len(log)==len(expected),'qualification_business_denominator_changed')
    attachment, = (slot/'client/attachments').glob('bridge_*')
    thin = read(attachment/'EXIT.json')
    require(thin['normal_exit'] and thin['attempts']==len(log),'qualified_thin_close_or_attempt_count_changed')
    calls = []
    for i,(event,expected_name) in enumerate(zip(log,expected,strict=True),1):
        folder = slot/'client'/f'call_{i:02d}'
        req,res,receipt = (read(folder/name) for name in ('REQUEST.json','RESPONSE.json','RECEIPT.json'))
        require(event['name']==req['params']['name']==expected_name and event['index']==i
                and req['id']==res['id']==f'qualification-{i}'
                and event['request_sha256']==digest((folder/'REQUEST.json').read_bytes())
                and event['response_sha256']==digest((folder/'RESPONSE.json').read_bytes())
                and res['result']['isError'] is (i==1),'qualification_input_result_or_expected_rejection_changed')
        tx,rx = PRIOR['rpc_pair'](slot/'client/transport',receipt,req,res)
        record = attachment/f'{receipt["index"]:03d}'
        require(tx==(record/'TX.bin').read_bytes() and rx==(record/'RX.bin').read_bytes(),
                'qualification_public_transport_or_retained_thin_wire_changed')
        owner = slot/'owner'/f'tool_{i:02d}'
        a,b,c = (read(owner/name) for name in ('REQUEST.json','RESPONSE.json','RECEIPT.json'))
        require(a==req and b==res and c['attempt']==i and c['RPC_id']==req['id'],
                'qualification_closed_owner_call_binding_changed')
        calls.append({'request':req,'response':res['result'],'owner':owner,
                      'TX_sha256':digest(tx),'RX_sha256':digest(rx)})
    require(calls[0]['request']['params']['arguments']==DIAG['INVALID'],'fixed_rejected_argument_changed')
    return calls


def _ordinary(slot, calls, source, wire, refs):
    d = DIAG['ordinary_document']
    origin,answer = (d(calls[i]['response']) for i in (1,2))
    require(calls[1]['request']['params']['arguments']=={'code':DIAG['native_read']()}
            and calls[2]['request']['params']['arguments']=={'code':DIAG['native_code']()}
            and origin['source_ref']==answer['source_ref']
            and calls[5]['request']['params']['arguments']=={'refs':refs},
            'ordinary_original_persistent_call_or_readback_changed')
    prior_native = VISUAL['module'](VISUAL['DENSE_NATIVE'])
    rows = prior_native['live_rows'](source)
    closed_stamp = source['source']
    match_keys = ('asset_sha256','asset_copy','frame','subframe','scale_length','pid','scene','view_layer_id')
    require(all(origin['source'][key]==closed_stamp[key] for key in match_keys)
            and origin['sha256']==digest(json.dumps(rows,separators=(',',':')).encode())
            and origin['counts']==[20,3502,6160] and answer['dependencies']=={'numpy':6,'shapely':1.0},
            'ordinary_live_source_shape_dependency_or_identity_changed')
    device = read(slot/'DEVICE_EVIDENCE.json')
    identified, = [row for row in device['sources'] if row['source_ref']==origin['source_ref']]
    receipt = identified['worker']
    data = VISUAL['pin'](identified['path'],slot)
    require(data['sha256']==identified['sha256']==receipt['sha256'] and data['bytes']==receipt['bytes']
            and not identified['terminal'],'ordinary_source_artifact_not_own_current_capture')
    matching = {}
    prefix = 'M4_LIVE_SOURCE_CAPTURE:'
    for i,row in wire.items():
        payload = row['response'].get('result')
        content = payload.get('result','') if isinstance(payload,dict) else ''
        if isinstance(content,str) and content.startswith(prefix) and json.loads(content[len(prefix):])==receipt:
            matching[i] = row
    require(len(matching)==1,'ordinary_source_artifact_missing_closed_native_wire')
    truth = VISUAL['truth']()
    regions = {row['object_name']:row for row in answer['regions']}
    require(len(regions)==len(answer['regions'])==3 and regions.keys()==truth['regions'].keys(),
            'ordinary_maximal_current_candidate_roster_changed')
    for name,row in regions.items():
        geometry = truth['regions'][name]
        require(all(row[key]==geometry[key] for key in ('source_triangle_indices','center_world_m'))
                and row['views'].keys()==geometry['directions'].keys(),
                'ordinary_source_faces_centers_or_checked_view_roster_changed/'+name)
        for view,check in row['views'].items():
            blocker = check['blocker']
            require(check['status']==geometry['directions'][view]['status']
                    and (blocker is None if check['status']!='positive_area_occlusion' else
                         blocker in geometry['directions'][view]['positive_area_occluders']
                         and E['_RECOVERY']['independently_positive'](
                             source,geometry,blocker['object_name'],blocker['source_triangle_index'],view)),
                    'ordinary_actual_view_or_bound_blocker_changed/'+name+'/'+view)
    measurement = E['_RECOVERY']['measured'](answer['measurement'],source,truth)
    require(answer['measurement']['squared_lower_bound']=='1/16'
            and answer['measurement']['bound_reference_faces']==514,
            'ordinary_global_reference_point_pair_not_proven')
    frames = {row['ref']:row for row in device['frames']}
    require(len(frames)==len(device['frames'])==len(refs)==2 and frames.keys()==set(refs),
            'ordinary_two_original_rasters_not_owned_in_slot')
    pixels = {}
    for ordinal,(target,view) in enumerate(DIAG['TARGETS'],3):
        ref = refs[ordinal-3]
        rendered = DIAG['document'](calls[ordinal]['response'])['frame']
        row = frames[ref]
        require(calls[ordinal]['request']['params']['arguments']==DIAG['render_options'](view,regions[target]['center_world_m'])
                and rendered['ref']==ref and rendered['frame_identity']==row['frame_identity']
                and row['source_ref']==origin['source_ref'] and row['origin']=='common_native'
                and row['view_name']==view,'ordinary_public_render_frame_not_own_current_view')
        proof = VISUAL['verify_native_frame'](slot,row,target,source,reply=calls[ordinal]['response'])
        require(proof['complete'],'ordinary_original_frame_fails_geometry_or_pixels/'+target)
        VISUAL['verify_native_frame'](slot,row,target,source,reply=calls[5]['response'])
        pixels[target] = proof
    return {'discovered':regions,'measurement':measurement,'witnesses':pixels,
            'source_wire_sequence':next(iter(matching)),'source_receipt':data,'rasters':2,
            'CLI':{str(i+1):E['fixed_cli'](entry['response'],require_all=True)
                   for i,entry in enumerate(calls) if i}}


def _product(slot, calls, source, wire, refs):
    require(calls[1]['request']['params']['arguments']==DIAG['DISCOVER']
            and calls[2]['request']['params']['arguments']=={'refs':refs}
            and calls[3]['request']['params']['arguments']==DIAG['MEASURE']
            and refs==DIAG['required_product_refs'](calls[1]['response']),
            'qualified_product_original_scope_or_arguments_changed')
    discovered,rasters = PRIOR['product_result'](slot,calls[1],1)
    measured,m_rasters = PRIOR['product_result'](slot,calls[3],2)
    installed = read(VISUAL['INSTALL'])
    oracle = VISUAL['module'](VISUAL['ORACLE'])
    captures,commands = oracle['decode_captures'](slot,installed,oracle['Audit']())
    d_row,d_capture = PRIOR['current_capture_for'](commands,captures,wire,discovered)
    m_row,m_capture = PRIOR['current_capture_for'](commands,captures,wire,measured)
    require(d_row['wire_sequence']<m_row['wire_sequence']
            and all(d_capture[key]==m_capture[key] for key in ('capture_state','display_snapshot','meshes'))
            and m_rasters==0 and 2<=rasters<=12,
            'source_region_measurement_not_bound_to_same_capture_or_added_raster')
    proof = VISUAL['verify_product'](slot,calls[1]['response'],discovered,source,
                                     readback=calls[2]['response'],capture=d_capture,installed=installed)
    measurement = VISUAL['verify_measurement'](calls[3]['response'],measured,source,
                                               parent_binding=discovered['binding'])
    require(set(refs)=={item['image_ref'] for item in proof['witness_paths']} and len(proof['witness_paths'])==2,
            'product_first_packet_must_supply_both_independently_readable_paths')
    return {'discovery':proof,'measurement':measurement,'witnesses':proof['witnesses'],'rasters':rasters,
            'source_wire_sequences':[d_row['wire_sequence'],m_row['wire_sequence']],
            'CLI':{str(i+1):E['fixed_cli'](entry['response'],require_all=True)
                   for i,entry in enumerate(calls) if i}}


def verify(slot, result):
    slot = Path(slot).resolve(strict=True)
    pending = read(slot/'QUALIFICATION_PENDING.json')
    require(slot.name in ('QN','QP') and pending==result['qualification_pending']
            and pending['passed'] is False and pending['phase']=='public_calls_completed_pending_owned_close'
            and result['status']=='completed' and result['model_consumers']==result['paid_API_calls']==0
            and result['diagnostic_close']['confirmed'] and result['diagnostic_close']['exit_code']==0,
            'qualified_synthetic_or_nonclosed_diagnostic_disallowed')
    source,closure = E['verify_closed'](slot,result,VISUAL['truth']())
    worker = PRIOR['closed_wire'](slot)
    runtime = read(slot/'RUNTIME_CLOSE.json')
    refs = pending['refs']
    if slot.name=='QP':
        close = runtime['public_MCP_close']
        require(close['confirmed'] and close['production_eof_and_exit_verified'] and close['exit_code']==0
                and runtime['public_MCP_exit']['confirmed'] and runtime['public_MCP_exit']['exit_code']==0,
                'installed_product_actual_eof_or_exit_missing')
        calls = public_records(slot,result,('render_local',DIAG['TOOL'],'read_images',DIAG['TOOL']))
        proof = _product(slot,calls,source,worker,refs)
    else:
        require(runtime.get('public_MCP_close') is None,'ordinary_arm_unexpected_product_process')
        calls = public_records(slot,result,('render_local','execute_python','execute_python',
                                         'render_local','render_local','read_images'))
        proof = _ordinary(slot,calls,source,worker,refs)
    budget = result['budget']['counts']
    require(proof['rasters']==budget['all_raster_actual'] and budget['pending_raster_reservations']==0,
            'actual_owned_raster_accounting_changed')
    return {'passed':True,'slot':slot.name,'source':closure,'rasters':proof['rasters'],'proof':proof,
            'outer_wire_receipts':[{key:row[key] for key in ('TX_sha256','RX_sha256')} for row in calls],
            'closed_native_wire_sha256':digest((slot/'native/WIRE/INDEX.json').read_bytes())}

"""Admit actual qualification evidence after Blender, product stdio and consumer close."""

import json
from pathlib import Path
from runpy import run_path


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent


def verify(slot, result):
    import diagnostic
    from common import PRODUCT_BINDING, read, sha

    check = run_path(str(NS/'checks/evidence.py'))
    prior = run_path(str(V/'perf050_dense_micro_surface_holdout_recovery_001/qualification/verify.py'))
    require = check['require']
    slot = Path(slot).resolve(strict=True)
    pending = read(slot/'QUALIFICATION_PENDING.json')
    require(pending == result['qualification_pending'] and pending['passed'] is False
            and pending['phase'] == 'public_calls_completed_pending_owned_close'
            and result['status'] == 'completed' and result['model_consumers'] == result['paid_API_calls'] == 0,
            'actual_qualification_business_not_completed')
    truth = check['normalize_truth'](NS/'fixture/TRUTH.json')
    source, closed = check['verify_closed'](slot, result, truth)
    worker_wire = prior['closed_wire'](slot)
    runtime = read(slot/'RUNTIME_CLOSE.json')
    mcp_close = runtime['public_MCP_close']
    require(result['diagnostic_close']['confirmed'] and result['diagnostic_close']['exit_code'] == 0
            and mcp_close['confirmed'] is True and mcp_close['exit_code'] == 0
            and mcp_close['production_eof_and_exit_verified'] is True
            and runtime['public_MCP_exit']['confirmed'] and runtime['public_MCP_exit']['exit_code'] == 0,
            'actual_qualification_stdio_eof_or_exit_unproven')
    log = result['diagnostic_calls']
    require(tuple(row['name'] for row in log) == diagnostic.ORDER, 'qualification_tool_order_changed')
    refs = [row['ref'] for row in pending['frames']]
    inputs = (diagnostic.INVALID, {**diagnostic.DISCOVER, 'response_detail':'full'}, {'refs':refs},
              {**diagnostic.DISCOVER, 'response_detail':'brief'}, diagnostic.MEASURE)
    bridge, = list((slot/'client/attachments').glob('bridge_*'))
    bridge_close = read(bridge/'EXIT.json')
    require(bridge_close['normal_exit'] is True and bridge_close['attempts'] == len(inputs),
            'actual_consumer_thin_attachment_process_did_not_close')
    calls = []
    for i, (row, arguments) in enumerate(zip(log, inputs, strict=True), 1):
        path = slot/'client'/f'call_{i:02}'
        request, response, receipt = (read(path/name) for name in ('REQUEST.json','RESPONSE.json','RECEIPT.json'))
        require(request == {'jsonrpc':'2.0','id':f'qualification-{i}','method':'tools/call',
                            'params':{'name':row['name'],'arguments':arguments}}
                and response['id'] == request['id'] and row['index'] == i
                and sha(path/'REQUEST.json') == row['request_sha256'] and sha(path/'RESPONSE.json') == row['response_sha256']
                and response['result']['isError'] is (i == 1), 'actual_qualification_invalid_or_recovery_changed')
        tx, rx = prior['rpc_pair'](slot/'client/transport', receipt, request, response)
        record = bridge/f'{receipt["index"]:03}'
        require((record/'TX.bin').read_bytes() == tx and (record/'RX.bin').read_bytes() == rx,
                'actual_thin_qualification_wire_changed')
        owner = slot/'owner'/f'tool_{i:02}'
        owner_receipt = read(owner/'RECEIPT.json')
        require(read(owner/'REQUEST.json') == request and read(owner/'RESPONSE.json') == response
                and owner_receipt['attempt'] == i and owner_receipt['RPC_id'] == request['id'],
                'actual_qualification_owner_attempt_binding_changed')
        calls.append({'request':request,'response':response['result'],'owner':owner,
                      'TX_sha256':check['digest'](tx),'RX_sha256':check['digest'](rx)})
    discover, brief, measure = (prior['product_result'](slot, calls[i], j) for i,j in ((1,1),(3,2),(4,3)))
    a, rasters = discover
    b, warm_rasters = brief
    c, measure_rasters = measure
    proof = check['verify_discovery'](slot, calls[1]['response'], a, source, truth,
                                      expected='brief' if slot.name == 'QB' else 'full')
    proof_brief = check['verify_discovery'](slot, calls[3]['response'], b, source, truth, expected='brief')
    require(proof['delivered_frames'] == proof_brief['delivered_frames'] and proof['binding'] == proof_brief['binding']
            and proof['P_blockers'] == proof_brief['P_blockers'] and warm_rasters == measure_rasters == 0
            and rasters == result['budget']['counts']['all_raster_actual']
            and 3 <= len(proof['delivered_frames']) <= rasters <= 12,
            'same_generation_qualification_repeated_or_lost_real_frames')
    readback = check['verify_readback'](slot, calls[2]['response'], proof['delivered_frames'])
    measurement = check['verify_measurement'](calls[4]['response'], c, a['binding'], source, truth)
    actual_cli = {
        name: check['fixed_cli'](calls[i]['response'], require_all=i != 1 or slot.name == 'QB')
        for name,i in (('initial_discovery',1),('original_readback',2),('legal_brief',3),('measurement',4))
    }
    oracle = run_path(str(V/'m4_cross_scale_discovery_001/oracle/check_saved.py'))
    install = read(PRODUCT_BINDING)
    audit = oracle['Audit']()
    captures, commands = oracle['decode_captures'](slot,install,audit)
    first, current = prior['current_capture_for'](commands,captures,worker_wire,a)
    selected, source_capture = prior['current_capture_for'](commands,captures,worker_wire,c)
    require(first['wire_sequence'] < selected['wire_sequence']
            and all(current[key] == source_capture[key] for key in ('capture_state','display_snapshot','meshes')),
            'same_generation_world_meshes_or_visibility_not_reused_in_measurement')
    return {'passed':True,'source':closed,'rasters':rasters,'full_or_evidence':proof,'legal_brief':proof_brief,
            'measurement':measurement,'readback':readback,'CLI':actual_cli,
            'mcp_close':mcp_close,'outer_calls':[{key:row[key] for key in ('TX_sha256','RX_sha256')} for row in calls],
            'capture_sequences':[first['wire_sequence'],selected['wire_sequence']]}

"""Check owned closing, exact public forwarding and original measurement captures."""
import json
from pathlib import Path
from runpy import run_path

NS = Path(__file__).resolve().parents[1]
V = NS.parent


def recorded_calls(slot, result, *, product_root=None, mcp_root=None):
    import diagnostic
    from common import read, sha
    verify = run_path(str(V/'perf050_dense_micro_surface_holdout_recovery_001/qualification/verify.py'))
    require = diagnostic.require
    label = result['label']
    product_root = slot if product_root is None else product_root
    mcp_root = slot/'mcp' if mcp_root is None else mcp_root
    log = result['diagnostic_calls']
    expected = diagnostic.arguments(label)
    require(len(log)==len(expected)==3, 'original diagnostic call roster missing')
    bridge, = (slot/'client/attachments').glob('bridge_*')
    closed = read(bridge/'EXIT.json')
    require(closed['normal_exit'] and closed['attempts']==3, 'transparent consumer exit missing')
    archives = []
    for index,(event,args) in enumerate(zip(log,expected,strict=True),1):
        path = slot/'client'/f'call_{index:02d}'
        request, reply, receipt = (read(path/name) for name in ('REQUEST.json','RESPONSE.json','RECEIPT.json'))
        require(request['params']=={'name':diagnostic.TOOL,'arguments':args} and reply['id']==request['id']
                and event['index']==index and event['name']==diagnostic.TOOL
                and sha(path/'REQUEST.json')==event['request_sha256']
                and sha(path/'RESPONSE.json')==event['response_sha256']
                and reply['result']['isError'] is (index==1), 'public no-image call or expected rejection changed')
        diagnostic.body(reply['result'])
        outer = verify['rpc_pair'](slot/'client/transport', receipt, request, reply)
        front = bridge/f'{receipt["index"]:03d}'
        require(outer==tuple((front/name).read_bytes() for name in ('TX.bin','RX.bin')),
                'transparent consumer actual bytes differ')
        owner = slot/'owner'/f'tool_{index:02d}'
        require(read(owner/'REQUEST.json')==request and read(owner/'RESPONSE.json')==reply
                and read(owner/'RECEIPT.json')['attempt']==index,
                'owner did not preserve actual attempt/request/reply')
        product = product_root/'product_calls'/f'call_{index:03d}'
        forwarded, received, wire = (read(product/name) for name in ('REQUEST.json','RESPONSE.json','RECEIPT.json'))
        inner = verify['rpc_pair'](mcp_root, wire, forwarded, received)
        require(forwarded['params']==request['params'] and received['result']==reply['result']
                and read(owner/'PRODUCT_REQUEST.json')==forwarded
                and read(owner/'PRODUCT_RESPONSE.json')==received,
                'installed args or result changed through the bridge')
        worker, = [row for row in verify['jsonl'](product_root/'mcp_io/MCP_IO.jsonl') if row['sequence']==wire['index']]
        require(worker['TX_bytes']==len(inner[0]) and worker['RX_text_UTF8_LF_sha256']==verify['digest'](inner[1].replace(b'\r\n',b'\n'))
                and worker['TX_sha256']==verify['digest'](inner[0]) and worker.get('raster_actual',0)==0,
                'original product wire or raster accounting changed')
        before, after = ((product/name).read_bytes() for name in ('ARCHIVE_BEFORE.bin','ARCHIVE_AFTER.bin'))
        held = read(owner/'PRODUCT_RECEIPT.json')
        entry = {'name':diagnostic.TOOL,'public_response':reply,'public_TX_sha256':verify['digest'](outer[0]),
                 'public_RX_sha256':verify['digest'](outer[1]),'product_TX_sha256':verify['digest'](inner[0]),
                 'product_RX_sha256':verify['digest'](inner[1]),'product_wire_index':wire['index'],
                 'public_RTT_ns':receipt['elapsed_ns'],'product_RTT_ns':wire['elapsed_ns'],
                 'product_started_ns':wire['started_ns'],'product_received_ns':wire['received_complete_ns']}
        if index==1:
            require(before==after and not held.get('producer_archive'), 'rejected request called measurement producer')
        else:
            require(after.startswith(before), 'original producer archive prefix changed')
            original, = [json.loads(line) for line in after[len(before):].splitlines()]
            require(original==held.get('producer_archive') and original['index']==index-1
                    and original['new_observations_for_archive']==0
                    and wire['started_ns']<=original['started_ns']<=original['producer_returned_ns']<=original['saved_ns']<=wire['received_complete_ns'],
                    'actual produced value detached from measured call')
            origin = Path(original['path']).resolve(strict=True)
            require(origin.is_relative_to(slot) and sha(origin)==original['sha256'],
                    'actual bound original producer bytes unavailable')
            entry.update(producer=read(origin),producer_sha256=original['sha256'],producer_path=str(origin))
        archives.append(entry)
    return archives


def verify(slot, result):
    import diagnostic
    from common import ASSET, binding_for, read, sha
    require = diagnostic.require
    slot = Path(slot).resolve(strict=True)
    label = slot.name
    pending = read(slot/'QUALIFICATION_PENDING.json')
    timing = read(slot/'RUNTIME_CLOSE.json')
    require(pending==result['qualification_pending'] and pending['phase']=='await_actual_close'
            and pending['no_images'] is True and pending['passed'] is False
            and result['status']=='completed' and result['model_consumers']==result['paid_API_calls']==0
            and result['diagnostic_close']['confirmed'] and result['diagnostic_close']['exit_code']==0
            and timing['public_MCP_close']['confirmed'] and timing['public_MCP_close']['production_eof_and_exit_verified']
            and timing['public_MCP_exit']['confirmed'] and timing['public_MCP_exit']['exit_code']==0,
            'owned eligibility requires real safe close and zero models')
    saved = run_path(str(V/'perf050_dense_micro_surface_holdout_recovery_001/qualification/verify.py'))
    envelope = run_path(str(V/'m4_cross_scale_live_task_formal_001/scoring/formal.py'))
    oracle = run_path(str(V/'m4_cross_scale_discovery_001/oracle/check_saved.py'))
    native = saved['closed_wire'](slot)
    copy = slot/'native/input.blend'
    start, ready, closed = envelope['generic_process'](slot,ASSET,copy,result['asset_sha256'],result['owned_deadline_ns'])
    first,last = (envelope['read_capture'](slot,slot/path,result[key],start['pid'],result['asset_sha256'])
        for path,key in (('initial_capture/TERMINAL_SOURCE.json','initial_source'),('TERMINAL_SOURCE.json','terminal_source')))
    fields = ('source','objects','source_face_offsets','display_object_mask','display_scope','layer_collections','scene_cameras')
    require(all(first[key]==last[key] for key in fields)
            and start['created_after_ns']<=first['started_ns']<=result['ready_ns']<=result['cleanup_started_ns']
            <=last['started_ns']<=closed['closed_ns']<=result['owned_deadline_ns'],
            'scene state or original closing clocks changed')
    rejected,selected,whole = recorded_calls(slot,result)
    installed = read(binding_for(label))
    captures, commands = oracle['decode_captures'](slot,installed,oracle['Audit']())
    commands = [row for row in commands if row['command']['command'] in ('capture','capture_scene','capture_task')]
    require(len(commands)==len(captures),'capture arrays were detached from host command sequence')

    def in_request(packet, modes):
        matches = []
        for item,capture in zip(commands,captures,strict=True):
            wire = native[item['wire_sequence']]['worker_event']
            if (item['command']['command'] in modes and packet['product_started_ns']<=wire['started_ns']
                    and wire['started_ns']+wire['elapsed_ns']<=packet['product_received_ns']):
                matches.append((item,capture))
        require(len(matches)==1,'no uniquely originated host capture for measured surface range')
        return matches[0]

    selected_item,selected_capture = in_request(selected,('capture','capture_scene'))
    whole_item,whole_capture = in_request(whole,('capture_task','capture','capture_scene'))
    checks = run_path(str(NS/'checks/evidence.py'))
    proof = checks['verify_qualification'](slot, selected['public_response'], selected['producer'],
        whole['public_response'], whole['producer'], binding=installed, require_compact=label=='QB',
        source=last, selected_capture=selected_capture, whole_capture=whole_capture)
    require(proof['passed'] is True,'current source / distance / threshold proof did not qualify')
    reduced = [{key:value for key,value in packet.items() if key not in ('public_response','producer')}
               for packet in (rejected,selected,whole)]
    return {'passed':True,'label':label,'actual_call_count':3,'no_images':True,'raster_count':0,
            'qualification':proof,'wires':reduced,'native_wires':{
                'selected':selected_item['wire_sequence'],'whole':whole_item['wire_sequence']},
            'source':{'sha256_start':sha(slot/'initial_capture/TERMINAL_SOURCE.json'),
                      'sha256_final':sha(slot/'TERMINAL_SOURCE.json'),'fingerprint':ready['initial_fingerprint'],
                      'closed_ns':closed['closed_ns']}}

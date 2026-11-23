"""Score original answers against both current Yanyite surfaces and public tool evidence."""

import argparse
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from hashlib import file_digest, sha256
import json
from math import dist, isfinite
from pathlib import Path
import re
import sys


ROOT = Path('D:/he_m1_m2_source_region_scoped_measurement_consumption_001')
TARGET = '0135bbc4-c6c7-4003-a402-6f2e0283497d'
REFERENCE = 'Cube'
ASSET = '614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d'
TERMINAL = 'dd47f22335c8f0fcd3e6e0aa764d5d174be89b49d9e488867813135bb64fd3e6'
PRODUCT_SOURCE = '4a51c48524b66895819b69a30d2bd8eb020ce840028f0612f8d6e887c0423f09'
INDEX_DOMAIN = 'zero_based_object_local_current_evaluated_capture_triangle_rows'
SCOPED_SCHEMA = 'human-eye-source-region-scoped-measurement-v1'
PRIVATE_SCHEMA = 'human-eye-selective-source-region-measurement-v1'
SCOPE = 'complete_selected_source_triangle_union_to_reference_triangle_surface'
REGIONS = ('high', 'low')
ITEMS = ('count', 'distance', 'direction', 'points', 'source_triangle', 'reference_triangle', 'threshold')
REQUIRED = (*(f'{name}.{key}' for name in REGIONS for key in ITEMS), 'nearer')
NUMBER = r'[+\-−]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?'
VECTOR_TEXT = re.compile(r'[\[(（]\s*(' + NUMBER + r')\s*[,，]\s*(' + NUMBER + r')\s*[,，]\s*(' + NUMBER + r')\s*[\])）]')
REGION_TEXT = {
    'high': re.compile(r'高(?:位|区|盒)|\b(?:high|upper)\b', re.I),
    'low': re.compile(r'低(?:位|区|盒)|\b(?:low|lower)\b', re.I),
}
BELOW = re.compile(r'未达|不达|低于|小于|不满足|不足|below|less than|does not (?:meet|reach)|(?:<|＜)(?!=)', re.I)
AT_LEAST = re.compile(r'达到|高于|超过|大于|不少于|满足|至少|meets|reaches|greater than|at least|above|≥|>=|(?:>|＞)(?!=)', re.I)
TIMED = rb'^\s*\{\s*"perf_ns"\s*:\s*[0-9]+\s*,\s*"event"\s*:\s*'
BARE = rb'^\s*'
ITEM_HEADER = (rb'\{\s*"type"\s*:\s*"item\.completed"\s*,\s*"item"\s*:\s*\{\s*'
               rb'"id"\s*:\s*"(?:[^"\\\x00-\x1f]|\\.)*"\s*,\s*"type"\s*:\s*"(mcp_tool_call|agent_message)"\s*[,}]')
TURN_HEADER = rb'\{\s*"type"\s*:\s*"(turn\.(?:completed|failed))"\s*[,}]'


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def load(value):
    def unique(pairs):
        result = dict(pairs)
        need(len(result) == len(pairs), 'duplicate_JSON_key')
        return result
    def nonfinite(value):
        raise ValueError('nonfinite_JSON_number:' + value)
    if isinstance(value, Path):
        value = value.read_bytes()
    return json.loads(value, object_pairs_hook=unique, parse_constant=nonfinite)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        stream.write('\n')


def pin(path):
    path = Path(path).resolve(strict=True)
    with path.open('rb') as stream:
        return {'path': str(path), 'bytes': path.stat().st_size,
                'sha256': file_digest(stream, 'sha256').hexdigest()}


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                             separators=(',', ':')).encode()).hexdigest()


def same_pin(one, other):
    return all(one.get(key) == other.get(key) for key in ('bytes','sha256'))


def public_events(path, *, timed):
    """Whitelist current CLI public item headers before deserializing the line."""
    item_pattern = re.compile((TIMED if timed else BARE) + ITEM_HEADER)
    turn_pattern = re.compile((TIMED if timed else BARE) + TURN_HEADER)
    with Path(path).open('rb') as stream:
        for line in stream:
            header = line[:4096]
            item, turn = item_pattern.match(header), turn_pattern.match(header)
            if turn and turn.group(1) == b'turn.failed':
                yield {'type':'turn.failed'}
            elif item or turn:
                value = load(line)
                event = value['event'] if timed else value
                if item:
                    need(event['type']=='item.completed' and event['item']['type']==item.group(1).decode(),
                         'public_event_header_body_mismatch')
                    yield event
                else:
                    need(event['type']=='turn.completed', 'public_turn_header_body_mismatch')
                    usage = event.get('usage') or {}
                    yield {'type':event['type'],'usage':{
                        k:usage[k] for k in ('input_tokens','output_tokens','cached_input_tokens')
                        if type(usage.get(k)) is int and usage[k]>=0
                    }}


def verify_public_final(slot, result, offline_transcript=None):
    directory = offline_transcript if offline_transcript is not None else slot/'consumer'
    final, raw, timed = (directory/name for name in ('PUBLIC_FINAL.txt','stdout.raw.bin','events.jsonl'))
    receipt, stdout = pin(final), pin(raw)
    if offline_transcript is None:
        answer_binding = result['answer']
    else:
        bundle = load(directory/'TRANSCRIPT_BINDING.json')
        need(bundle['scope']=='derived_no_model_scoring_transcript'
             and bundle['slot']==slot.name and bundle['closed_slot']==pin(slot/'SLOT_RESULT.json')
             and bundle['raw']==stdout and bundle['timed']==pin(timed),
             'derived_offline_transcript_not_bound_to_closed_fixture')
        answer_binding = bundle['answer']
    events = list(public_events(timed,timed=True))
    need(events==list(public_events(raw,timed=False)), 'raw_and_timed_public_events_differ')
    answers = [row['item'] for row in events if row['type']=='item.completed' and row['item']['type']=='agent_message']
    calls = [row['item'] for row in events if row['type']=='item.completed' and row['item']['type']=='mcp_tool_call']
    completions = [row for row in events if row['type']=='turn.completed']
    text = final.read_text(encoding='utf8')
    need(same_pin(answer_binding,receipt) and answers and len(completions)==1
         and not any(row['type']=='turn.failed' for row in events)
         and isinstance(answers[-1]['text'],str)
         and text.rstrip('\n')==answers[-1]['text'].replace('\r\n','\n').rstrip('\n')
         and len({row['id'] for row in (*answers,*calls)})==len(answers)+len(calls),
         'public_final_not_the_completed_original_CLI_answer')
    return receipt,text,calls,stdout,completions[0]['usage']


def close_source(slot, truth, offline):
    slot = slot.resolve(strict=True)
    result_path = slot/'SLOT_RESULT.json'
    result, publication = (load(slot/name) for name in ('SLOT_RESULT.json','SLOT_PUBLICATION.json'))
    need(slot.name in ('A1','B1') and slot.name==publication['label']==result['label']
         and publication['result_sha256']==pin(result_path)['sha256']
         and result['status']==publication['status']=='completed'
         and result.get('offline_fixture',False) is offline, 'unbound_closed_slot_receipt')
    need(result['closure_verification']['passed'] is True, 'closed_readonly_source_not_verified')
    mc = load(slot/'mcp/HELD_CLOSE.json')
    owner = load(slot/'owner/CLOSE.json')
    need(mc['production_eof_and_exit_verified'] is True and mc['confirmed'] is True
         and mc['exit_code']==0 and not mc['forced_kill'] and owner['confirmed'] is True,
         'actual_public_process_close_missing')

    known_path = Path(truth['terminal_path'])
    known = pin(known_path)
    need(truth['terminal_sha256']==known['sha256']==TERMINAL and truth['asset_sha256']==ASSET
         and truth['target']==TARGET and truth['reference']==REFERENCE, 'historical_Yanyite_terminal_changed')
    old = load(known_path)
    if offline:
        transport_close = slot.parents[1]/'REPLAY_CLOSE.json'
        closed = load(transport_close)
        need(result['actual_Blender_starts']==result['actual_models']==result['actual_rasters']==0
             and result['actual_fixture_peer_exit_code']==0
             and result['same_formal_owned_runtime'] is True
             and result['closure_verification']['offline_fixture'] is True
             and result['fixture_peer_close']==pin(transport_close)
             and closed['passed'] is True and closed['listener_closed'] is True
             and closed['terminal_source']==known and closed['connections_completed']==2
             and all(pin(row['path'])==row for row in closed['wire_pins']),
             'actual_readonly_fixture_TCP_close_or_source_unproven')
        current = old
    else:
        device = load(slot/'DEVICE_EVIDENCE.json')
        need(device['label']==slot.name and result['independent_before_after']['passed'] is True
             and result['asset_sha256']==device['asset_sha256']==ASSET
             and result['terminal_source']==device['terminal_source']
             and device['terminal_source']['status']=='complete'
             and result['consumer']['valid_completion'] is True,'formal_closed_source_or_consumer_unverified')
        current_path, opening_path=(slot/key for key in ('TERMINAL_SOURCE.json','initial_capture/TERMINAL_SOURCE.json'))
        current, opening = map(load,(current_path,opening_path))
        current_receipt = device['terminal_source']
        need(same_pin(pin(current_path),current_receipt)
             and Path(current_receipt['path']).resolve()==current_path
             and current['source'].get('pid')==current_receipt['worker']['pid']
             and current['source']==opening['source'] and current['objects']==opening['objects']
             and current['display_object_mask']==opening['display_object_mask']==old['display_object_mask']==[True,False],
             'current_terminal_source_identity_or_initial_geometry_changed')
        phase_fields = ('asset_sha256','frame','subframe','scale_length','unit_settings','source_index_domain')
        need(all(current['source'][key]==old['source'][key] for key in phase_fields),
             'current_asset_frame_unit_or_source_index_domain_changed')
        copied = Path(current['source']['asset_copy']).resolve(strict=True)
        need(copied.is_relative_to(slot) and pin(copied)['sha256']==ASSET, 'actual_slot_asset_copy_changed')
        runtime_close = load(slot/'RUNTIME_CLOSE.json')
        actual_exit = runtime_close['Blender_exit']
        need(actual_exit['confirmed'] is True and actual_exit['exit_code']==0
             and actual_exit['handle_closed'] is True
             and runtime_close['Blender_close']['pid']==current['source']['pid'],
             'same_Blender_process_normal_exit_unproven')
        object_fields = ('name','object_id','matrix_world','evaluated','visible_get','native')
        need(len(current['objects'])==len(old['objects'])==2 and
             all(all(a[key]==b[key] for key in object_fields) for a,b in zip(current['objects'],old['objects'],strict=True)),
             'current_mesh_or_evaluated_source_order_changed')
    meshes = {row['name']:row for row in current['objects']}
    target, reference = meshes[TARGET], meshes[REFERENCE]
    geometry = target['evaluated']
    for name in REGIONS:
        spec = truth['regions'][name]
        bounds = spec['box_m']
        inside = [all(lo<=x<=hi for lo,x,hi in zip(bounds['min'],point,bounds['max'],strict=True))
                  for point in geometry['vertices_world_m']]
        selected = [i for i,triangle in enumerate(geometry['triangles']) if all(inside[v] for v in triangle)]
        need(selected==spec['triangle_ids'] and len(selected)==spec['triangle_count'],
             'current_closed_box_source_rows_changed/'+name)
        ref = reference['evaluated']
        for point,row_ids,mesh in ((spec['source_point_world_m'],spec['source_witness_triangle_ids'],geometry),
                                   (spec['reference_point_world_m'],spec['cube_witness_triangle_ids'],ref)):
            need(row_ids and all(on_triangle(point,[mesh['vertices_world_m'][i] for i in mesh['triangles'][row]])
                                 for row in row_ids), 'current_exact_source_membership_changed/'+name)
    return result,current,target,reference


def subtract(a,b):
    return tuple(x-y for x,y in zip(a,b,strict=True))


def cross(a,b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def dot(a,b):
    return sum(x*y for x,y in zip(a,b,strict=True))


def on_triangle(point, triangle):
    p,a,b,c = (tuple(Fraction(v) for v in row) for row in (point,*triangle))
    n = cross(subtract(b,a),subtract(c,a))
    return any(n) and dot(n,subtract(p,a))==0 and all(
        dot(n,cross(subtract(y,x),subtract(p,x)))>=0 for x,y in ((a,b),(b,c),(c,a)))


def identity(row, obj):
    return all(row.get(k)==obj[k] for k in ('name','object_id','instance_id'))


def number(value):
    return type(value) in (int,float) and isfinite(value)


def vector(value):
    return isinstance(value,(list,tuple)) and len(value)==3 and all(number(x) for x in value)


def close(a,b,tol=1e-8):
    return vector(a) and vector(b) and dist(a,b)<=tol


def producer_for(slot, folder, request, response):
    item = load(folder/'PRODUCT_RECEIPT.json')
    rec = item['receipt']
    rpc = slot/'mcp'/f"rpc_{rec['index']:02d}"
    rx,tx = rpc/'RX.bin',rpc/'TX.bin'
    product_args = load(folder/'PRODUCT_ARGUMENTS.json')
    original_request = load(folder/'PRODUCT_REQUEST.json')
    forwarded = load(folder/'PRODUCT_RESPONSE.json')
    actual = load(rx)
    need(pin(rx)['sha256']==rec['RX_sha256'] and pin(tx)['bytes']==rec['TX_bytes']
         and pin(rx)['bytes']==rec['RX_bytes'] and load(tx)==original_request
         and actual['id']==original_request['id']==rec['id']==item['id']
         and original_request['params']['name']==request['params']['name']=='human_eye_scene_observe'
         and product_args==original_request['params']['arguments']==request['params'].get('arguments',{})
         and actual==forwarded and actual['result']==response['result'],
         'product_public_rsp_does_not_bind_actual_installed_stdio')
    archived = item.get('producer_archive')
    if not archived:
        return None
    path = Path(archived['path']).resolve(strict=True)
    need(path.is_relative_to(slot/'product_full') and pin(path)['sha256']==archived['sha256'],
         'scoped_producer_does_not_bind_current_slot')
    return load(path)


def actual_calls(slot, cli):
    fifo={}
    for folder in sorted((slot/'owner').glob('rpc_*')):
        tx,rx = folder/'TCP_TX.bin',folder/'TCP_RX.bin'
        if not(tx.exists() and rx.exists()):
            continue
        query,returned = load(tx),load(rx)
        need(query['request_id']==returned['request_id'], 'owner_transaction_mismatched')
        request = query.get('args',{}).get('message',{})
        if request.get('method')=='tools/call' and returned.get('ok') is True:
            response = returned['result']
            need(request['id']==response['id'] and request['id'] not in fifo,'owner_tool_ID_mismatched')
            fifo[request['id']] = (request,response,tx,rx)
    calls=[]
    for folder in sorted((slot/'owner').glob('tool_*')):
        request,response,rec=(load(folder/name) for name in ('REQUEST.json','RESPONSE.json','RECEIPT.json'))
        raw_request,raw_response,tx,rx=fifo.pop(request['id'])
        args = request['params'].get('arguments',{})
        tool = request['params']['name']
        need(request['id']==response['id']==rec['RPC_id'] and tool==rec['name']==raw_request['params']['name']
             and raw_request['params'].get('arguments',{})==args and raw_response==response
             and rec['attempt']==len(calls)+1,
             'same_slot_owner_arguments_response_or_order_mismatch')
        result = response['result']
        # Only an exact completed CLI delivery supports adoption; missing or reduced
        # public content remains counted as unknown rather than inferred from Owner.
        matches = [i for i,row in enumerate(cli) if row.get('tool')==tool and row.get('arguments',{})==args]
        exposure = None
        if matches:
            row = cli.pop(matches[0])
            if not row.get('error') and (row.get('result') or {}).get('content')==result.get('content'):
                exposure = row['id']
        body = [block['text'] for block in result.get('content',[]) if block['type']=='text']
        producer = producer_for(slot,folder,request,response) if tool=='human_eye_scene_observe' and (
            folder/'PRODUCT_RECEIPT.json').exists() else None
        calls.append({'attempt':rec['attempt'],'tool':tool,'args':args,'error':result.get('isError'),
                      'text':body,'producer':producer,'owner_tx_bytes':tx.stat().st_size,
                      'owner_rx_bytes':rx.stat().st_size,'CLI_public_item':exposure,
                      'image_blocks':sum(block['type']=='image' for block in result.get('content',[]))})
    need(not fifo,'closed_owner_call_missing_from_receipts')
    return calls


def measurement_region(query, truth, target, reference):
    if type(query) is not dict:
        return None
    mode = query.get('mode')
    region = query.get('region') or {}
    if type(region) is not dict:
        return None
    matches = lambda selector,obj: selector in ({'name':obj['name']},{'id':obj['object_id']})
    if (mode not in ('source_region','source_region_measurement') or
            query.get('requested_facts')!=['surface_proximity']
            or not matches(query.get('reference'),reference)):
        return None
    if region:
        if not matches(region.get('object'),target):
            return None
        rows = region.get('source_triangle_indices')
        selected = sorted(rows) if type(rows) is list and all(type(row) is int for row in rows) else None
        return next((name for name,spec in truth['regions'].items() if (
            region.get('world_box_m')==spec['box_m'] or selected==spec['triangle_ids'])),None)
    ref = query.get('region_ref') or {}
    if type(ref) is dict and ref.get('host_id')==target['object_id'] and ref.get('instance_id')==target['instance_id']:
        return next((name for name,spec in truth['regions'].items()
                     if ref.get('source_triangle_indices')==spec['triangle_ids']),None)
    return None


def read_measurement(call,spec,target,reference):
    need(call['error'] is False and len(call['text'])==1 and call['image_blocks']==0,
         'scoped_tool_no_complete_text_measurement')
    raw = call['producer']
    public = load(call['text'][0])
    need(raw and raw['read_only'] is True and raw['execution_authority'] is False
         and raw['status']=='complete' and raw['frames']==[]
         and raw['binding']['runtime_source_sha256']==PRODUCT_SOURCE,
         'actual_producer_missing_or_wrong_mode')
    scoped = call['args']['query']['mode']=='source_region_measurement'
    result = raw if scoped else raw['task_result']
    mapping = result['source_mapping']
    rows = mapping['region']['submesh_to_source_triangle_indices']
    fact = result['facts']['surface_proximity']
    witness = fact['value']['nearest_witness']
    distance = fact['value']['distance_m']
    a,b,direction = witness['a'],witness['b'],witness['direction_a_to_b']
    sources = mapping['nearest_witness']
    a_ids,b_ids = (sources[k]['source_triangle_indices'] for k in ('a','b'))
    need(rows==spec['triangle_ids'] and result['measurement_scope']==SCOPE
         and identity(result['reference'],reference) and fact['status']=='measured'
         and fact['witness_status']=='measured' and fact['direction_status']=='measured'
         and abs(distance-spec['distance_m'])<=1e-9 and close(a,spec['source_point_world_m'])
         and close(b,spec['reference_point_world_m']) and close(direction,spec['direction_world'])
         and set(a_ids)==set(spec['source_witness_triangle_ids'])
         and set(b_ids)==set(spec['cube_witness_triangle_ids'])
         and all(sources[k]['exact_membership'] is True and sources[k]['index_domain']==INDEX_DOMAIN
                 for k in ('a','b')), 'wrong_scope_distance_witness_or_current_source_membership')
    bound = raw['binding']
    if scoped:
        need(raw['schema']==PRIVATE_SCHEMA and bound['capture_scope']=='selected_source_region_and_reference'
             and identity(bound['target'],target) and identity(bound['reference'],reference)
             and bound['world_box_m']==spec['box_m']
             and public['schema']==SCOPED_SCHEMA and public['status']=='complete'
             and public['read_only'] is True and public['measurement_scope']==SCOPE
             and public['world_box_m']==spec['box_m'] and public['unit']=='m' and public['coordinate_frame']=='world'
             and identity(public['region_object'],target) and identity(public['reference_object'],reference)
             and public['selected_triangle_count']==len(rows) and public['distance_m']==distance
             and public['direction_status']=='measured' and public['direction_a_to_b']==direction
             and public['point_a_m']==a and public['point_b_m']==b
             and public['source_triangle_a'] in a_ids and public['source_triangle_b'] in b_ids
             and public['source_triangle_index_domain']==INDEX_DOMAIN
             and all(public.get(key)==raw['witness_provenance'].get(key) for key in
                     ('source_triangle_a','source_triangle_b','exact_points_m'))
             and not {'source_mapping','region_ref','frames','payload_sha256'}&public.keys(),
             'actual_scoped_public_evidence_wrong_or_incomplete')
        a_ids,b_ids = [public['source_triangle_a']],[public['source_triangle_b']]
    else:
        ref = raw['region_ref']
        public_task = public['task_result']
        expected_geometry = digest([{'host_id':obj['object_id'],'instance_id':obj['instance_id'],
                                     'vertices':obj['evaluated']['vertices_world_m'],
                                     'faces':obj['evaluated']['triangles']} for obj in (target,reference)])
        need(bound['capture_scope']=='complete_scene_meshes' and bound['ordered_geometry_sha256']==expected_geometry
             and ref['ordered_geometry_sha256']==expected_geometry
             and ref['host_id']==target['object_id'] and ref['instance_id']==target['instance_id']
             and ref['source_triangle_indices']==rows
             and public['region_ref']==ref and public_task['facts']==result['facts']
             and identity(public_task['reference'],reference)
             and all(public_task['source_mapping']['nearest_witness'][k]['source_triangle_indices']
                     == sources[k]['source_triangle_indices'] for k in ('a','b')),
             'actual_legacy_public_evidence_wrong_or_incomplete')
    return {'count':len(rows),'distance':distance,'direction':direction,'a':a,'b':b,
            'source_triangles':a_ids,'reference_triangles':b_ids,'body_utf8_bytes':len(call['text'][0].encode())}


def literal_number(text, value):
    need(number(value),'non_numeric_transcription')
    return any(Decimal(token.replace('−','-'))==Decimal(str(value)) for token in re.findall(NUMBER,text))


def check_claim(name,row,text,truth):
    region,_,key = name.partition('.')
    need(type(row) is dict and isinstance(quote:=row.get('quote'),str) and quote.strip() and quote in text,
         'unbound_literal_quote')
    if name=='nearer':
        value = row['value']
        need(value==truth['nearer'] and REGION_TEXT[value].search(quote)
             and re.search(r'更近|较近|更靠近|较靠近|最近|closer|nearest',quote,re.I),'wrong_or_unquoted_nearer_region')
        return value
    spec = truth['regions'][region]
    if key in ('count','source_triangle','reference_triangle'):
        value = row['value']
        expected = {'count':[spec['triangle_count']],'source_triangle':spec['source_witness_triangle_ids'],
                    'reference_triangle':spec['cube_witness_triangle_ids']}[key]
        need(type(value) is int and value in expected and literal_number(quote,value),
             'wrong_or_unquoted_count_or_source_triangle')
        return value
    if key=='distance':
        literal,unit = row['literal'],row['unit']
        need(type(literal) is str and re.fullmatch(NUMBER,literal) and unit in ('m','mm')
             and re.search(r'(?<![\d.])'+re.escape(literal)+r'(?![\d.])',quote),
             'distance_not_an_original_metric_literal')
        raw = Decimal(literal.replace('−','-'))
        divisor = 1000 if unit=='mm' else 1
        value = float(raw)/divisor
        allowance = max(1e-9,min(0.0005,float(Decimal((0,(5,),raw.as_tuple().exponent-1)))/divisor))
        need(abs(value-spec['distance_m'])<=allowance and
             (value>=truth['threshold_m'])==(spec['distance_m']>=truth['threshold_m']),
             'distance_does_not_round_to_true_current_measurement')
        return value
    if key=='threshold':
        value = row['value']
        short = quote.strip(' *`_')
        expressed = (bool(AT_LEAST.search(quote)) and not BELOW.search(quote)) or short in ('是','Yes','yes','True','true')
        denied = bool(BELOW.search(quote)) or short in ('否','No','no','False','false')
        need(type(value) is bool and value is (spec['distance_m']>=truth['threshold_m'])
             and (expressed if value else denied),
             'incorrect_or_unquoted_0_300_m_classification')
        return value
    vectors = [tuple(float(x.replace('−','-')) for x in match.groups()) for match in VECTOR_TEXT.finditer(quote)]
    if key=='direction':
        value = row['value']
        verbal = re.search(r'\+\s*[zZ]|[zZ]\s*(?:轴)?\s*正方向|正\s*[zZ]|positive\s+[zZ]',quote,re.I)
        need(close(value,spec['direction_world']) and (tuple(value) in vectors or verbal),
             'wrong_or_unquoted_world_unit_direction')
        return value
    a,b = row['a'],row['b']
    tol=5.1e-5
    need(close(a,spec['source_point_world_m'],tol) and close(b,spec['reference_point_world_m'],tol)
         and tuple(a) in vectors and tuple(b) in vectors
         and dist(a,b)>0 and close([x/dist(a,b) for x in subtract(b,a)],spec['direction_world'],1e-3),
         'nearest_points_not_literal_or_not_on_current_surface_witness')
    return [a,b]


def grade_claims(slot, claims_path, answer, text, truth):
    data = load(claims_path)
    need(data.get('slot')==slot.name and data.get('answer_sha256')==answer['sha256']
         and type(rows:=data.get('claims')) is dict and rows.keys()<=set(REQUIRED), 'transcription_not_bound_to_final')
    verdict={}
    for key in REQUIRED:
        try:
            value = check_claim(key,rows[key],text,truth)
            verdict[key]={'status':'pass','quote':rows[key]['quote'],'value':value}
        except (KeyError,TypeError,ValueError,OverflowError,InvalidOperation) as error:
            verdict[key]={'status':'failure','reason':str(error)}
    return verdict


def exposure(calls, truth, target, reference, criteria):
    grouped={name:[] for name in REGIONS}
    ordinary=[]
    ledger=[]
    for call in calls:
        args=call['args']
        query=args.get('query')
        mode=query.get('mode') if type(query) is dict else None
        region=measurement_region(query,truth,target,reference) if call['tool']=='human_eye_scene_observe' else None
        fields={key:call[key] for key in ('attempt','tool','error','CLI_public_item','owner_tx_bytes','owner_rx_bytes','image_blocks')}
        fields.update(mode=mode,region=region,include_image=args.get('include_image'),
                      response_detail=args.get('response_detail'),body_utf8_bytes=sum(len(x.encode()) for x in call['text']))
        ledger.append(fields)
        if region is None:
            if call['tool']!='human_eye_scene_observe':
                ordinary.append(call['attempt'])
            continue
        grouped[region].append(fields)
        if call['error'] is False and not fields['include_image']:
            try:
                fields['measurement']=read_measurement(call,truth['regions'][region],target,reference)
            except (KeyError,TypeError,ValueError,OverflowError,AttributeError) as error:
                fields['measurement_rejected']=str(error)
    result={}
    for region,rows in grouped.items():
        packet=next((row for row in rows if row.get('measurement') and row['CLI_public_item']),None)
        direct=False
        if packet:
            measurement=packet['measurement']
            direct=(all(criteria[f'{region}.{key}']['status']=='pass' for key in ITEMS)
                    and criteria[f'{region}.source_triangle']['value'] in measurement['source_triangles']
                    and criteria[f'{region}.reference_triangle']['value'] in measurement['reference_triangles'])
        result[region]={
            'first_matching_attempt': rows[0]['attempt'] if rows else None,
            'first_matching_mode':rows[0]['mode'] if rows else None,
            'first_successful_public_measurement_attempt':packet['attempt'] if packet else None,
            'first_successful_public_measurement_mode':packet['mode'] if packet else None,
            'first_packet_range_and_witness_match_literal_final':direct,
            'any_scoped_measurement_delivered':any(row['mode']=='source_region_measurement'
                and row.get('measurement') and row['CLI_public_item'] for row in rows),
            'later_matching_attempts':[row['attempt'] for row in rows[1:]],
            'ordinary_after_first_public_measurement':[
                attempt for attempt in ordinary if packet and attempt>packet['attempt']],
            'public_evidence_origin_in_model_not_observable':True,
        }
    return {'per_region':result,'calls':ledger,'ordinary_attempts':ordinary,
            'first_matching_attempt':next((row for row in ledger if row['region']),None)}


def score_slot(slot, truth_path, claims_path, *, offline=False, offline_transcript=None):
    slot=Path(slot).resolve(strict=True)
    truth=load(Path(truth_path))
    result,_,target,reference=close_source(slot,truth,offline)
    need((offline_transcript is not None) is offline,'tested_transcript_allowed_only_for_explicit_offline_fixture')
    answer,text,cli,stdout,usage=verify_public_final(slot,result,offline_transcript)
    claims=grade_claims(slot,Path(claims_path),answer,text,truth)
    actual=actual_calls(slot,cli)
    adopted=exposure(actual,truth,target,reference,claims)
    passed=sum(row['status']=='pass' for row in claims.values())
    return {'slot':slot.name,'offline_fixture':offline,'quality_complete':passed==len(REQUIRED),
            'passed_items':passed,'total_items':len(REQUIRED),'answer':answer,'CLI_stdout':stdout,
            'unmatched_public_tool_ids':[row['id'] for row in cli],'usage':usage,
            'claims':claims,'adoption':adopted}


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    for key in ('slot','truth','claims','output'):
        cli.add_argument('--'+key,type=Path,required=True)
    cli.add_argument('--offline',action='store_true')
    cli.add_argument('--offline-transcript',type=Path)
    args=cli.parse_args()
    need(args.output.resolve().is_relative_to(ROOT.resolve()),'scorer_output_must_stay_in_owned_root')
    try:
        value=score_slot(args.slot,args.truth,args.claims,offline=args.offline,offline_transcript=args.offline_transcript)
    except (OSError,KeyError,ValueError,TypeError,IndexError,AttributeError,OverflowError) as error:
        value={'slot':args.slot.name,'offline_fixture':args.offline,'quality_complete':False,
               'passed_items':0,'total_items':len(REQUIRED),'error':str(error)}
    write(args.output,value)
    print({k:value[k] for k in ('slot','quality_complete','passed_items','total_items','error') if k in value},flush=True)
    return 0 if value['quality_complete'] else 1


if __name__=='__main__':
    raise SystemExit(main())

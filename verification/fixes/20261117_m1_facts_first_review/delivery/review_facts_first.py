"""Saved-only v2 compatibility, public delivery and protocol review."""
import ast
import base64
import copy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import tomllib
import zipfile

OUT = Path(__file__).resolve().parent
NS = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe/verification/m1_source_region_facts_first_001')
RUNTIME = Path('D:/he_m1_source_region_facts_first_001')
PRODUCT = RUNTIME/'B/product'
sys.path[:0] = [str(PRODUCT), 'D:/he_anchor_001/venv/Lib/site-packages']
from PIL import Image
from human_eye_plugin.query_policy import validate_source_region_query

CHECKS, PINS = [], {}
PURE_PROJECTION_CALLS = 0


def require(condition, name):
    if not condition:
        raise AssertionError(name)
    CHECKS.append(name)


def raw(path):
    path = Path(path)
    data = path.read_bytes()
    PINS[str(path)] = hashlib.sha256(data).hexdigest()
    return data


def read(path):
    return json.loads(raw(path))


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()


def selected_functions(path, names, namespace):
    tree = ast.parse(raw(path).decode('utf8'))
    definitions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    require({n.name for n in definitions} == set(names), 'pure extracted source definitions '+Path(path).name)
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


def expect_error(callback, expected, label):
    try:
        callback()
    except ValueError as error:
        require(expected in str(error), label+'/exact rejection')
    else:
        raise AssertionError(label+'/missing rejection')


def export_records():
    result = {}
    for candidate in ('OLD', 'A', 'B'):
        table = {}
        for tx_path in sorted((RUNTIME/'projection_benchmark'/candidate/'stdio').glob('rpc_*/TX.bin')):
            tx = read(tx_path)
            if tx['method'] != 'export':
                continue
            rx = read(tx_path.with_name('RX.bin'))
            require(rx['id'] == tx['id'] and 'error' not in rx, candidate+'/'+tx_path.parent.name+'/original export request response')
            value = rx['result']
            require(value['input_unchanged'] is True and value['PNG_NPZ_encodes'] == 0 and value['raster'] == 0, candidate+'/'+tx_path.parent.name+'/original saved export no source or image construction')
            require(value['text'] == value['tool_result']['content'][0]['text'] and len(value['text'].encode()) == value['text_UTF8_bytes'] and hashlib.sha256(value['text'].encode()).hexdigest() == value['text_sha256'], candidate+'/'+tx_path.parent.name+'/original formatter exported text exact SHA')
            table[(tx['params']['case'], tx['params'].get('detail'))] = value
        result[candidate] = table
    require([len(result[c]) for c in ('OLD', 'A', 'B')] == [3, 6, 6], '15 existing export RPCs examined zero new formatter calls')
    return result


def pure_compatibility(projector, value, expected, case):
    global PURE_PROJECTION_CALLS
    before = encoded(value)
    projected = projector['project_source_region_brief'](value)
    PURE_PROJECTION_CALLS += 1
    # The transport substitutes delivery receipt metadata. The pure projection
    # keeps the input receipt exactly, so compare every other public field.
    a, b = copy.deepcopy(projected), copy.deepcopy(expected)
    a.pop('image_delivery', None)
    b.pop('image_delivery', None)
    require(a == b, case+'/actual pure B projection equals saved actual brief except transport receipt')
    projected['region_ref']['source_triangle_indices'].append(999999)
    projected['task_result']['facts']['surface_proximity']['value']['nearest_witness']['a'][0] = 123
    projected['task_result']['source_mapping']['nearest_witness']['a']['source_triangle_indices'].clear()
    projected['image_scope']['objects'][0]['object_name'] = 'review mutation'
    projected['images'][0]['image_ref'] = 'review mutation'
    projected['visibility']['unknown'].clear()
    require(encoded(value) == before, case+'/six nested output mutation probes leave original producer bytes unchanged')


def boundary_controls(projector, original):
    global PURE_PROJECTION_CALLS
    counts = []
    for count in (1, 4096):
        value = copy.deepcopy(original)
        indices = list(range(count))
        value['region_ref']['source_triangle_indices'] = indices
        unsigned = {k: v for k, v in value['region_ref'].items() if k != 'region_id'}
        value['region_ref']['region_id'] = 'source-region:'+hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()
        value['task_result']['region_ref'] = copy.deepcopy(value['region_ref'])
        value['facts']['region']['source_triangle_indices'] = indices
        value['facts']['visibility'].update(visible_source_triangle_indices=[], unseen_source_triangle_indices=indices, selected_source_triangle_count=count, selected_surface_pixels=0, reason='image_not_requested')
        value['frames'] = []
        brief = projector['project_source_region_brief'](value)
        PURE_PROJECTION_CALLS += 1
        query = dict(mode='source_region', region_ref=brief['region_ref'], reference={'id': value['task_result']['reference']['object_id']}, requested_facts=['surface_proximity'])
        require(validate_source_region_query(query)['region_ref'] == value['region_ref'] and brief['region']['source_triangle_count'] == count and brief['visibility']['unseen_source_triangle_count'] == count, 'query and pure projection complete ref count'+str(count))
        counts.append(dict(selected_rows=count, projected_text_bytes=len(encoded(brief)), fits_same_tag11964_byte_text_budget=len(encoded(brief)) <= 11964, scope='format and query shape only, host geometry execution unrun'))
    for kind in ('task_ref', 'source_rows', 'frame_binding'):
        value = copy.deepcopy(original)
        if kind == 'task_ref':
            value['task_result']['region_ref']['source_triangle_indices'] = [0]
        elif kind == 'source_rows':
            value['facts']['region']['source_triangle_indices'] = [0]
        else:
            value['frames'][0]['host_binding_sha256'] = '0'*64
        expected = 'source_region_frame_binding_mismatch' if kind == 'frame_binding' else 'source_region_result_scope_mismatch'
        expect_error(lambda: projector['project_source_region_brief'](value), expected, 'pure guard '+kind)
        PURE_PROJECTION_CALLS += 1
    for indices in ([], list(range(4097)), [0, 0], [True]):
        query = dict(mode='source_region', region_ref=copy.deepcopy(original['region_ref']), reference={'id': original['task_result']['reference']['object_id']}, requested_facts=['surface_proximity'])
        query['region_ref']['source_triangle_indices'] = indices
        expect_error(lambda: validate_source_region_query(query), '1..4096 unique nonnegative integer', 'query rejects illegal source rows '+str(len(indices)))
    unknown = copy.deepcopy(original)
    unknown['task_result']['facts']['surface_proximity'] = {'status':'unknown','reason':'exact_surface_witness_unavailable'}
    unknown['task_result']['source_mapping']['nearest_witness'] = {s:{'status':'unknown','reason':'exact_surface_witness_unavailable'} for s in ('a','b')}
    projected = projector['project_source_region_brief'](unknown)
    PURE_PROJECTION_CALLS += 1
    require(projected['task_result']['facts'] == unknown['task_result']['facts'] and projected['task_result']['source_mapping']['nearest_witness'] == unknown['task_result']['source_mapping']['nearest_witness'], 'pure unknown fact and both unknown source witnesses preserved without measured substitution')
    return counts


def audit_brief(case, baseline, records, projector):
    original = read(NS/'historical'/case/'SERVICE_RESULT.json')
    message = read(NS/'inputs'/case/'TOOL_RESULT.json')
    text = message['content'][0]['text']
    brief = json.loads(text)
    require(records['A'][(case, None)]['tool_result'] == records['B'][(case, None)]['tool_result'] == message, case+'/existing A B default full MCP content byte-value identical')
    require(records['OLD'][(case, 'full')]['tool_result'] == records['A'][(case, 'full')]['tool_result'] == records['B'][(case, 'full')]['tool_result'], case+'/existing OLD A B full complete MCP content identical')
    full = json.loads(records['B'][(case, 'full')]['text'])
    full.pop('image_delivery', None)
    producer = copy.deepcopy(original)
    producer.pop('image_delivery', None)
    require(full == producer, case+'/full complete producer fields except transport delivery receipt preserved')
    require(brief['schema'] == 'source-region-brief-v2' and len(text.encode()) == baseline['brief_UTF8_bytes'] <= 10000, case+'/actual registered10k default limit')
    require(brief['region_ref'] == original['region_ref'] and text.count('"schema":"human-eye-source-region-ref-v1"') == 1 and brief['details'] == 'response_detail=full', case+'/exact one original complete v1 reference existing full entry')
    task = brief['task_result']
    require(task['facts'] == original['task_result']['facts'] and task['source_mapping'] == {'nearest_witness': original['task_result']['source_mapping']['nearest_witness']}, case+'/all facts and exact original source witness')
    require(task['unit'] == original['binding']['unit'] == 'm' and task['coordinate_frame'] == original['binding']['coordinate_frame'] == 'world' and task['reference'] == original['task_result']['reference'] and task['measurement_scope'] == original['task_result']['measurement_scope'], case+'/explicit original unit coordinate frame reference measurement scope')
    require(brief['image_scope'] == original['binding']['image_scope'] and all(v == original['binding'][k] for k, v in brief['binding'].items()), case+'/all actual display and retained source identities')
    vis = original['facts']['visibility']
    expected_vis = {k: v for k, v in vis.items() if k not in ('visible_source_triangle_indices', 'unseen_source_triangle_indices', 'image_scope')}
    expected_vis.update(visible_source_triangle_count=len(vis['visible_source_triangle_indices']), unseen_source_triangle_count=len(vis['unseen_source_triangle_indices']))
    require(brief['visibility'] == expected_vis and brief['status'] == original['status'] and brief['observation_status'] == original['observation_status'], case+'/all status unknown visibility fields and exact member counts')
    positions = {}
    required = dict(facts=task['facts'], nearest_source_witness=task['source_mapping'], images_complete_value=brief['images'])
    for key, value in required.items():
        needle = encoded(value)
        pos = text.encode().index(needle)
        require(pos+len(needle) <= 4096, case+'/complete core value before4096 '+key)
        positions[key] = dict(start=pos, end=pos+len(needle))
    for key in ('distance_m', 'nearest_witness', 'unit', 'coordinate_frame', 'reference', 'measurement_scope', 'selected_surface_pixels', 'images'):
        positions[key] = text.encode().index(('"'+key+'"').encode())
        require(positions[key] < 4096, case+'/core key before4096 '+key)
    for header in (33, 34):
        require(len(text.encode()) <= 12000-header and (len(text.encode())+3)//4 <= 3000-(header+3)//4, case+'/same-tag original fallback MCP and history complete at header'+str(header))
    png = base64.b64decode(message['content'][1]['data'], validate=True)
    require(png == raw(NS/'historical'/case/'ORIGINAL_IMAGE.png') == raw(NS/'inputs'/case/'ORIGINAL_IMAGE.png') and hashlib.sha256(png).hexdigest() == baseline['PNG_sha256'] == original['frames'][0]['image_sha256'] and Image.open(BytesIO(png)).size == (512, 512), case+'/all default PNG bytes and original frame SHA exact512')
    pure_compatibility(projector, original, brief, case)
    return dict(case=case, text_bytes=len(text.encode()), PNG_bytes=len(png), positions=positions, selected_pixels=brief['visibility']['selected_surface_pixels'], visible_source_faces=brief['visibility']['visible_source_triangle_count'], unseen_source_faces=brief['visibility']['unseen_source_triangle_count'])


def audit_actual_consumer(case, baseline):
    slot = RUNTIME/'slots'/case
    tools, messages, skipped = [], [], 0
    for line in raw(slot/'consumer/stdout.raw.bin').splitlines():
        event = json.loads(line)
        item = event.get('item', {})
        if item.get('type') in ('reasoning', 'analysis') or item.get('channel') == 'analysis':
            skipped += 1
            continue
        if event.get('type') == 'item.completed' and item.get('type') == 'mcp_tool_call':
            tools.append(item)
        if event.get('type') == 'item.completed' and item.get('type') == 'agent_message':
            messages.append(item['text'])
    require(len(tools) == 1 and tools[0]['server'] == 'arm_engine' and tools[0]['tool'] == 'read_observation' and tools[0]['status'] == 'completed', case+'/one actual completed public business tool')
    item = tools[0]
    request = read(slot/'owner/tool_01/REQUEST.json')
    response = read(slot/'owner/tool_01/RESPONSE.json')
    require(set(request['params']) == {'_meta', 'name', 'arguments'} and request['params']['arguments'] == {} and isinstance(request['params']['_meta'], dict), case+'/actual standard metadata admitted')
    require(response['result'] == read(baseline['input_file']) and item['result']['content'] == response['result']['content'] and item['error'] is None, case+'/actual original successful reader and CLI content exact')
    require(len(item['result']['content']) == 2 and item['result']['content'][1]['type'] == 'image', case+'/one actual native image delivered')
    binding = read(slot/'consumer/BUSINESS_SOURCE_BINDING.json')
    require(binding['binding_errors'] == [] and len(binding['result_contracts']) == 1 and binding['result_contracts'][0]['matched'] is True, case+'/actual business archive successful original request response binding')
    wire = binding['protocol_RPC_ledger']
    business = [r for r in wire if r['request'].get('method') == 'tools/call']
    require(len(business) == 1 and business[0]['request'] == request and business[0]['response'] == response, case+'/actual reader RPC wire original matches owner')
    require(messages[-1].encode() == raw(slot/'consumer/PUBLIC_FINAL.txt') == raw(NS/'answers'/(case+'.txt')), case+'/original public final exact')
    config_args = read(slot/'consumer/CONSUMER_STARTED.json')['argv']
    config = tomllib.loads('\n'.join(config_args[i+1] for i, x in enumerate(config_args) if x == '-c'))
    require('tool_output_token_limit' not in config and set(config['mcp_servers']['arm_engine']['tools']['read_observation']) == {'approval_mode'}, case+'/same actual no global or per-tool output override')
    result = read(slot/'SLOT_RESULT.json')
    require(result['status'] == 'completed' and result['business_attempts'] == result['business_admitted'] == result['completed_tool_calls'] == result['native_image_deliveries'] == 1 and result['empty_discovery_calls'] == 0, case+'/actual source counters no accidental discovery false positive')
    return dict(case=case, tools=1, PNG_deliveries=1, discoveries=0, skipped_private_events=skipped, archive_binding_errors=[])


def audit_protocol():
    functions = selected_functions(NS/'harness/bridge_contract.py', ('classify_tool_item', 'tool_accounting', 'empty_discovery_rpc'), dict(json=json, DISCOVERY={'list_mcp_resources': ('resources/list', {'resources': []}), 'list_mcp_resource_templates': ('resources/templates/list', {'resourceTemplates': []})}))
    records = []
    for tool, key in (('list_mcp_resources', 'resources'), ('list_mcp_resource_templates', 'resourceTemplates')):
        item = dict(id='review-'+tool, type='mcp_tool_call', server='codex', tool=tool, arguments={}, status='completed', error=None, result={'content': [{'type':'text','text':json.dumps({key:[]})}], 'structured_content':None})
        require(functions['classify_tool_item'](item) == 'empty_resource_discovery' and functions['classify_tool_item'](item, completed=False) == 'pending_resource_discovery', 'pure discovery exact empty accepted '+tool)
        modified = copy.deepcopy(item)
        modified['result']['content'][0]['text'] = json.dumps({key:[{'unexpected':'data'}]})
        require(functions['classify_tool_item'](modified) == 'unexpected', 'pure nonempty discovery rejected '+tool)
        modified = copy.deepcopy(item)
        modified['server'] = 'other'
        require(functions['classify_tool_item'](modified) == 'unexpected', 'pure other server discovery rejected '+tool)
        request = {'jsonrpc':'2.0','id':7,'method':'resources/list','params':{'_meta':{}}}
        response = {'jsonrpc':'2.0','id':7,'result':{key:[]}}
        require(functions['empty_discovery_rpc'](request,response,{key:[]}), 'pure exact discovery RPC identity accepted '+tool)
        response['id'] = 8
        require(not functions['empty_discovery_rpc'](request,response,{key:[]}), 'pure mismatched discovery RPC identity rejected '+tool)
        records.append(item)
    events = [dict(type='item.started',item=records[0]), dict(type='item.completed',item=records[0]), dict(type='item.completed',item=records[1])]
    accounting = functions['tool_accounting'](events)
    require(accounting['completed_CLI_tool_calls'] == accounting['completed_empty_discoveries'] == 2 and accounting['completed_business_calls'] == accounting['completed_unexpected_tools'] == 0 and accounting['incomplete_control_item_ids'] == [], 'pure all-tool and business accounting separated')
    incomplete = functions['tool_accounting'](events[:1])
    require(incomplete['incomplete_control_item_ids'] == [records[0]['id']], 'pure unfinished discovery remains explicit')
    old_namespace = NS.parent/'m4_source_region_consumption_001'
    old_archive = read(old_namespace/'RUNTIME_ARCHIVE.json')
    actual_historical_discoveries = 0
    for case in ('S1','S2','S3'):
        row = next(r for r in old_archive['files'] if r['relative'] == 'slots/'+case+'/consumer/stdout.raw.bin')
        for line in raw(old_namespace/row['copy']).splitlines():
            event = json.loads(line)
            item = event.get('item', {})
            if item.get('type') in ('reasoning','analysis') or item.get('channel') == 'analysis':
                continue
            if event.get('type') == 'item.completed' and item.get('type') == 'mcp_tool_call' and item.get('server') == 'codex':
                require(functions['classify_tool_item'](item) == 'empty_resource_discovery', 'historical actual empty resource event accepted '+case+'/'+item['tool'])
                actual_historical_discoveries += 1
    require(actual_historical_discoveries == 6, 'all six original failing-harness discovery events independently reclassified')
    report = read(NS/'checks/BRIDGE_PREFLIGHT.json')
    require(len(report['checks']) == 13 and all(r['passed'] is True for r in report['checks']), 'all13 original author protocol preflight records pass')
    for row in report['adapter_proof']['execution_sources']:
        require(hashlib.sha256(raw(row['path'])).hexdigest() == row['sha256'], 'protocol actual preflight execution source pinned '+Path(row['path']).name)
    return dict(original_preflight_checks=13, independently_executed_pure_classifier_controls=12, actual_historical_discoveries_reclassified=6, new_server_replays=0)


def main():
    raw(__file__)
    source = PRODUCT/'human_eye_plugin/live_spatial_mcp.py'
    projector = selected_functions(source, ('_validate_source_region_projection','_project_source_region_brief','project_source_region_brief'), dict(copy=copy,__package__='human_eye_plugin'))
    for name in ('query_policy.py','source_region.py','active_observation_images.py'):
        require(raw(PRODUCT/'human_eye_plugin'/name) == raw(Path('D:/he_m4_source_region_display_001/R0/product/human_eye_plugin')/name), 'geometry/display/query implementation unchanged '+name)
    archive = read(NS/'RUNTIME_ARCHIVE.json')
    require(archive['file_count'] == len(archive['files']) == 913 and archive['projected_members'] == [], '913 original archive members zero projections')
    for row in archive['files']:
        require(hashlib.sha256(raw(NS/row['copy'])).hexdigest() == row['sha256'] == row['original_sha256'] and row['byte_exact'] is True, 'archive exact bytes '+row['relative'])
    records = export_records()
    inputs = read(NS/'INPUTS.json')
    cases = [audit_brief(row['case_id'],row,records,projector) for row in inputs['cases']]
    controls = boundary_controls(projector, read(NS/'historical/S1/SERVICE_RESULT.json'))
    actual = [audit_actual_consumer(row['case_id'], row) for row in inputs['cases']]
    protocol = audit_protocol()
    reference = Path('D:/hefe/verification/fixes/20261117_source_region_consumption_review/delivery/reference')
    for name in ('MANIFEST.json','codex-rs__models-manager__src__model_info.rs','codex-rs__core__src__tools__context.rs','codex-rs__utils__output-truncation__src__lib.rs','codex-rs__utils__string__src__truncate.rs'):
        raw(reference/name)
    require(all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p,h in PINS.items()), 'all saved originals unchanged at audit completion')
    result = dict(status='passed',author_commit='544cf4f123c35fbca24b8f425acc30fd3308b178', product_commit='08a5f3b29283270c97b6d9d6e217bbee6ca7bfc1', checks=len(CHECKS),
        cases=cases, reference_boundary_controls=controls, actual_consumers=actual, protocol=protocol,
        new_pure_projection_calls=PURE_PROJECTION_CALLS,new_full_formatter_calls=0, saved_export_RPCs=15,
        new_MCP=0,new_models=0,new_live=0,new_rasters=0,new_PNG_NPZ_encodes=0,new_paid=0,
        provider_payload_captured=False,binary_to_source_tag_attestation=False,
        AL_scope='own historical task740 assignment expired; current explicit root751 delegation; parent records untouched',
        input_pins=PINS,assertions=CHECKS)
    (OUT/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(status=result['status'],checks=len(CHECKS),pure_projection_calls=PURE_PROJECTION_CALLS,cases=cases,protocol=protocol)))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        (OUT/'CURRENT_FAILURE.json').write_text(json.dumps(dict(error=repr(error),passed_checks=len(CHECKS),last_checks=CHECKS[-5:]),indent=2),encoding='utf8')
        raise

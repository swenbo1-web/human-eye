"""Saved public-event audit and same-tag local truncation reconstruction."""
import base64
import ast
import copy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import tomllib
import zipfile
sys.path.insert(0, 'D:/he_anchor_001/venv/Lib/site-packages')
from PIL import Image

OUT = Path(__file__).resolve().parent
NS = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe/verification/m4_source_region_consumption_001')
RUNTIME = Path('D:/he_m4_source_region_consume_001')
CHECKS, PINS = [], {}


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


def digest(data):
    return hashlib.sha256(data).hexdigest()


def middle(text, budget):
    """Port of pinned truncate_with_byte_estimate/split_string, byte mode."""
    b = text.encode('utf8')
    if len(b) <= budget:
        return text, dict(prefix_end=len(b), suffix_start=len(b), truncated=False)
    left, right = budget//2, budget-budget//2
    prefix = b[:left].decode('utf8', errors='ignore')
    suffix = b[len(b)-right:].decode('utf8', errors='ignore')
    removed = len(text)-len(prefix)-len(suffix)
    return prefix+'…'+str(removed)+' chars truncated…'+suffix, dict(prefix_end=len(prefix.encode()), suffix_start=len(b)-len(suffix.encode()), truncated=True)


NEEDLES = {
    'distance': '0.37011719389236364', 'distance_key': '"distance_m"',
    'nearest_witness': '"nearest_witness"', 'witness_z': '0.6298828061076364',
    'world_metres_semantics': 'current_evaluated_triangle_surfaces_world_metres',
    'explicit_unit_m': '"unit":"m"', 'coordinate_frame_key': '"coordinate_frame"',
    'surface_fact_key': '"surface_proximity"', 'surface_method': 'exact_binary64_triangle_surface_hulls_v3',
    'selected_zero_pixels': '"selected_surface_pixels":0',
    'full_surface_unknown': 'complete_surface_visibility',
    'cube_visible_zero_reason': 'selected_region_displayed_without_pixels',
    'target_hidden_zero_reason': 'selected_region_not_displayed',
    'measurement_scope': 'complete_selected_source_triangle_union_to_reference_triangle_surface',
}


def reconstruction(case, text):
    variants = []
    # The wall-time scalar is not logged. Actual slots are <100sec, so its
    # formatted integer part has one or two digits. Both header lengths are run.
    for sample in ('0.0000', '10.0000'):
        header = 'Wall time: '+sample+' seconds\nOutput:'
        header_bytes = len(header.encode())
        first, region = middle(text, 12000-header_bytes)
        # History receives Tokens(3000). Its estimator is ceil(bytes/4).
        second_budget = (3000-(header_bytes+3)//4)*4
        second, _ = middle(first, second_budget)
        # Token-mode second-pass marker differs from byte mode. If a second
        # pass is needed only the marker changes, retained source edges remain.
        if len(first.encode()) > second_budget:
            left, right = second_budget//2, second_budget-second_budget//2
            a = first.encode()[:left].decode('utf8', errors='ignore')
            b = first.encode()[-right:].decode('utf8', errors='ignore')
            omitted_tokens = (len(first.encode())-second_budget+3)//4
            second = a+'…'+str(omitted_tokens)+' tokens truncated…'+b
        source_prefix = len(second.split('…', 1)[0].encode())
        source_suffix = len(second.rsplit('…', 1)[-1].encode())
        entry = dict(header_utf8_bytes=header_bytes, assumed_header=header,
            first_pass_original_byte_ranges=[[0, region['prefix_end']], [region['suffix_start'], len(text.encode())]],
            history_original_byte_ranges=[[0, source_prefix], [len(text.encode())-source_suffix, len(text.encode())]],
            output_text_bytes=len(second.encode()), source_text_bytes=len(text.encode()),
            retained_fields={k: v in second for k, v in NEEDLES.items()},
            image_content_preserved=True, actual_model_payload_capture=False)
        entry['field_occurrences_original_bytes'] = {}
        for key, needle in NEEDLES.items():
            positions = []
            start = 0
            while True:
                pos = text.encode().find(needle.encode(), start)
                if pos < 0:
                    break
                positions.append(dict(offset=pos, survives_history=pos+len(needle.encode()) <= source_prefix or pos >= len(text.encode())-source_suffix))
                start = pos+1
            entry['field_occurrences_original_bytes'][key] = positions
        filename = case+'_SAME_TAG_RECONSTRUCTION_HEADER_'+str(header_bytes)+'.txt'
        (OUT/filename).write_text(header+'\n'+second, encoding='utf8')
        entry['reconstruction_file'] = filename
        require(not entry['retained_fields']['distance'] and not entry['retained_fields']['nearest_witness'] and not entry['retained_fields']['world_metres_semantics'], case+'/same-tag default branch removes metric witness metre semantics at header '+str(header_bytes))
        variants.append(entry)
    return variants


def audit_probes():
    root = OUT.parent/'next'
    reviews = []
    for suffix in ('_R0', ''):
        source_path = root/('brief_projection_probe'+suffix+'.py')
        source = raw(source_path).decode('utf8')
        document = ast.parse(source)
        definitions = [n for n in document.body if isinstance(n, ast.FunctionDef) and n.name in ('project', 'encoded')]
        require(len(definitions) == 2, 'parent probe contains only two selected pure definitions '+suffix)
        namespace = dict(copy=copy, json=json)
        exec(compile(ast.Module(body=definitions, type_ignores=[]), str(source_path), 'exec'), namespace)
        expected = read(root/('BRIEF_PROJECTION_PROBE'+suffix+'.json'))
        records = []
        for record in expected['cases']:
            original = read(record['source_path'])
            value = json.loads(original['content'][0]['text'])
            projected = namespace['project'](value)
            text = namespace['encoded'](projected)
            require(len(text) == record['probe_text_bytes'] and len(text) <= 11000, 'probe actual bytes and11k cap '+suffix+'/'+record['case'])
            require(projected['region_ref'] == value['region_ref'] and projected['task_result']['facts'] == value['task_result']['facts'] and projected['task_result']['source_mapping']['nearest_witness'] == value['task_result']['source_mapping']['nearest_witness'] and projected['image_scope'] == value['binding']['image_scope'] and projected['images'] == value['images'], 'probe all required original facts ref display images preserved '+suffix+'/'+record['case'])
            for header_len in (33, 34):
                require(len(text) <= 12000-header_len and (len(text)+3)//4 <= 3000-(header_len+3)//4, 'probe full text unchanged both MCP and history budgets '+suffix+'/'+record['case']+'/'+str(header_len))
            records.append(dict(case=record['case'], actual_text_bytes=len(text), header_bytes=[33,34], MCP_text_floor_bytes=11966, history_text_budget_bytes=11964, full_text_preserved=True, PNG_preserved_by_both_passes=True))
        reviews.append(dict(probe_suffix=suffix, records=records, parent_script_sha256=digest(source.encode()), product_modified=False, model_consumption_run=False))
    return reviews


def audit_freezes():
    f0, f1 = read(NS/'FROZEN.json'), read(NS/'FROZEN_PROTOCOL_R1.json')
    revision = read(NS/'protocol_revisions/REVISION_01.json')
    pointer = read(NS/'ACTIVE_FREEZE.json')
    require(pointer['name'] == 'FROZEN_PROTOCOL_R1.json' and pointer['sha256'] == digest(raw(NS/'FROZEN_PROTOCOL_R1.json')), 'active revised freeze exact digest')
    require(f1['original_freeze_sha256'] == digest(raw(NS/'FROZEN.json')) and f1['protocol_revision_sha256'] == digest(raw(NS/'protocol_revisions/REVISION_01.json')), 'revision references exact original freeze and protocol record')
    changes = []
    old_inputs = {r['path']: r for r in f0['direct_inputs']}
    for row in f1['direct_inputs']:
        data = raw(row['path'])
        require(digest(data) == row['sha256'] and len(data) == row['bytes'], 'revised direct input current exact '+Path(row['path']).name)
        if row != old_inputs[row['path']]:
            changes.append(Path(row['path']).name)
            original = raw(NS/'protocol_revisions'/('R0_'+Path(row['path']).name+'.txt'))
            require(digest(original) == old_inputs[row['path']]['sha256'] and len(original) == old_inputs[row['path']]['bytes'], 'original R0 source retained exact '+Path(row['path']).name)
    require(sorted(changes) == ['read_observation.py', 'run_slot.py'] and len(f0['direct_inputs']) == len(f1['direct_inputs']) == 178, 'only two recorded protocol sources changed across178 direct inputs')
    slots = [read(RUNTIME/'slots'/c/'SLOT_RESULT.json') for c in ('S1', 'S2', 'S3')]
    require(f0['frozen_ns'] < slots[0]['started_ns'] < slots[0]['closed_ns'] < revision['started_ns'] < revision['closed_ns'] < f1['frozen_ns'] < slots[1]['started_ns'] < slots[1]['closed_ns'] < slots[2]['started_ns'], 'original freeze S1 closure protocol qualification revised freeze S2 S3 strict order')
    require(revision['S1_replacement_consumers'] == 0 and revision['S1_slot_result_sha256'] == digest(raw(RUNTIME/'slots/S1/SLOT_RESULT.json')), 'original failed S1 preserved no replacement')
    for c in ('S2', 'S3'):
        slot = read(RUNTIME/'slots'/c/'SLOT_RESULT.json')
        require(slot['freeze_sha256'] == digest(raw(NS/'FROZEN_PROTOCOL_R1.json')), c+'/actual runner revised source freeze')
    return dict(changed_sources=changes, original_frozen_ns=f0['frozen_ns'], revised_frozen_ns=f1['frozen_ns'], S1_replacement=0)


def audit_case(case, mapping):
    slot = RUNTIME/'slots'/case
    stdout = raw(NS/mapping['slots/'+case+'/consumer/stdout.raw.bin']['copy'])
    zip_data = raw(NS/mapping['slots/'+case+'/consumer.raw.zip']['copy'])
    with zipfile.ZipFile(BytesIO(zip_data)) as z:
        require(z.read('stdout.raw.bin') == stdout, case+'/projected legacy ZIP same public stdout bytes')
    tools, messages, usages, public_errors = [], [], [], []
    skipped_private = 0
    for line in stdout.splitlines():
        event = json.loads(line)
        item = event.get('item', {})
        if item.get('type') in ('reasoning', 'analysis') or item.get('channel') == 'analysis':
            skipped_private += 1
            continue
        if event.get('type') == 'item.completed' and item.get('type') == 'mcp_tool_call':
            tools.append(item)
        if event.get('type') == 'item.completed' and item.get('type') == 'agent_message':
            messages.append(item.get('text', ''))
        if event.get('type') == 'item.completed' and item.get('type') == 'error':
            public_errors.append(item.get('message', ''))
        if event.get('type') == 'turn.completed':
            usages.append(event['usage'])
    require(any('Model metadata for `gpt-6.1-sol` not found. Defaulting to fallback metadata' in e for e in public_errors), case+'/actual public fallback metadata warning')
    owner = [i for i in tools if i['server'] == 'arm_engine' and i['tool'] == 'read_observation']
    discovery = [i for i in tools if i['server'] == 'codex' and i['tool'] in ('list_mcp_resources', 'list_mcp_resource_templates')]
    require(len(discovery) == 2 and len(owner) == (2 if case == 'S1' else 1) and len(tools) <= 4, case+'/actual complete business discovery and all-tool budget')
    for item in discovery:
        require(item['status'] == 'completed' and item['error'] is None and item['result']['structured_content'] is None and len(item['result']['content']) == 1, case+'/completed resource discovery exact envelope '+item['tool'])
        value = json.loads(item['result']['content'][0]['text'])
        require(value == ({'resources': []} if item['tool'] == 'list_mcp_resources' else {'resourceTemplates': []}), case+'/resource discovery truly empty '+item['tool'])
    original_input = read(NS/'inputs'/case/'TOOL_RESULT.json')
    raw_text = original_input['content'][0]['text']
    brief = json.loads(raw_text)
    require(brief['task_result']['facts']['surface_proximity']['value']['distance_m'] == .37011719389236364 and 'nearest_witness' in brief['task_result']['facts']['surface_proximity']['value'], case+'/original text real metric and witness')
    delivered = []
    for index, item in enumerate(owner, 1):
        request = read(slot/'owner'/('tool_'+str(index).zfill(2))/'REQUEST.json')
        response = read(slot/'owner'/('tool_'+str(index).zfill(2))/'RESPONSE.json')
        require(set(request['params']) == {'name', 'arguments', '_meta'} and request['params']['name'] == 'read_observation' and request['params']['arguments'] == {} and type(request['params']['_meta']) is dict, case+'/standard actual metadata preserved request '+str(index))
        require(item['result']['content'] == response['result']['content'] and item['error'] is None, case+'/owner result equals full CLI public completion content '+str(index))
        if case == 'S1':
            require(response['result']['isError'] is True and item['status'] == 'failed' and response['result']['content'] == [{'type': 'text', 'text': 'empty_parameter_read_observation_required'}], case+'/R0 actual metadata rejection zero image '+str(index))
        else:
            require(response['result'] == original_input and item['status'] == 'completed', case+'/original unchanged tool input delivered to actual CLI event')
            content = item['result']['content']
            require(len(content) == 2 and len(content[0]['text'].encode()) == (117623 if case == 'S2' else 117620), case+'/actual complete117KB CLI text')
            png = base64.b64decode(content[1]['data'], validate=True)
            require(content[1]['type'] == 'image' and content[1]['mimeType'] == 'image/png' and Image.open(BytesIO(png)).size == (512, 512), case+'/actual original512PNG CLI event')
            require(not any(marker in content[0]['text'] for marker in ('chars truncated', 'tokens truncated', 'Warning: truncated output')), case+'/raw public completion has no truncation marker')
            delivered.append(dict(text_bytes=len(content[0]['text'].encode()), PNG_bytes=len(png), PNG_sha256=digest(png)))
    ledger = read(slot/'owner/TOOLS.json')
    require(ledger['attempts'] == len(owner) and ledger['admitted'] == (0 if case == 'S1' else 1), case+'/actual server attempts and admissions')
    binding = read(slot/'consumer/BUSINESS_SOURCE_BINDING.json')
    require(binding['binding_errors'] == [dict(reason='owner_and_CLI_attempt_count', owner=len(owner), CLI=len(tools))], case+'/original archive exact false owner count mismatch')
    started = read(slot/'consumer/CONSUMER_STARTED.json')
    argv = started['argv']
    config = tomllib.loads('\n'.join(argv[i+1] for i, x in enumerate(argv) if x == '-c'))
    require('tool_output_token_limit' not in config and set(config['mcp_servers']['arm_engine']['tools']['read_observation']) == {'approval_mode'}, case+'/actual argv no global or tool output limit override')
    require('--ignore-user-config' in argv and '--ignore-rules' in argv and '--ephemeral' in argv and 'resume' not in argv, case+'/fresh isolated configuration')
    original_answer = raw(slot/'consumer/PUBLIC_FINAL.txt')
    require(messages and messages[-1].encode() == original_answer == raw(NS/'answers'/(case+'.txt')), case+'/last public final exact frozen answer')
    server_resource_responses = []
    prefix = 'slots/'+case+'/consumer/attachments/'
    for relative, row in mapping.items():
        if relative.startswith(prefix) and relative.endswith('/TX.bin'):
            tx = read(NS/row['copy'])
            if tx.get('method') in ('resources/list', 'resources/templates/list'):
                rx = read(NS/mapping[relative[:-6]+'RX.bin']['copy'])
                expected = {'code': -32601, 'message': 'Method not found'}
                require(rx.get('error') == expected if case == 'S1' else rx.get('result') in ({'resources': []}, {'resourceTemplates': []}), case+'/actual server resource enumeration original result')
                server_resource_responses.append(dict(method=tx['method'], response=rx))
    require(len(server_resource_responses) == 2, case+'/two actual server resource calls')
    return dict(case=case, owner_attempts=len(owner), owner_admitted=ledger['admitted'], discovery=len(discovery), all_completed_tools=len(tools), delivered=delivered,
        public_fallback_warning=True, raw_metric_byte_offsets={k: raw_text.encode().find(v.encode()) for k, v in NEEDLES.items()},
        same_tag_reconstruction=reconstruction(case, raw_text) if case != 'S1' else [],
        actual_provider_input='not_captured', skipped_private_projected_events=skipped_private,
        original_harness_binding_errors=binding['binding_errors'], server_resource_responses=server_resource_responses,
        usage=usages, source_freeze_recorded=read(slot/'SLOT_RESULT.json').get('freeze_sha256', 'R0_no_freeze_field'))


def main():
    raw(__file__)
    archive = read(NS/'RUNTIME_ARCHIVE.json')
    mapping = {r['relative']: r for r in archive['files']}
    require(len(mapping) == 253 and len(archive['projected_members']) == 6, '253 shared records six declared projected members')
    for row in archive['files']:
        data = raw(NS/row['copy'])
        require(digest(data) == row['sha256'] and len(data) == row['shared_bytes'], 'shared original or safe projection SHA '+row['relative'])
    reference = read(OUT/'reference/MANIFEST.json')
    for r in reference:
        require(digest(raw(r['file'])) == r['sha256'], 'pinned official source '+r['path'])
    freeze = audit_freezes()
    cases = [audit_case(c, mapping) for c in ('S1', 'S2', 'S3')]
    probes = audit_probes()
    safe_metadata = []
    for filename in ('models_cache.json', 'models_cache.codex_work_desktop.json'):
        p = Path('C:/Users/Administrator/.codex')/filename
        metadata = read(p)
        model = next(m for m in metadata['models'] if m['slug'] == 'gpt-6.1-sol')
        safe_metadata.append(dict(file=str(p), fetched_at=metadata['fetched_at'], client_version=metadata['client_version'], model_slug=model['slug'], truncation_policy=model['truncation_policy'], same_as_executed_CLI_version=False))
    require(all(digest(Path(p).read_bytes()) == h for p, h in PINS.items()), 'all evidence unchanged at audit completion')
    result = dict(status='evidence_verified_harness_and_client_delivery_defects_identified', checks=len(CHECKS), author_commit='28cc6fc728c9fb62d46120f3be14b46d673f675a',
        cases=cases, freeze=freeze, public_source_commit='5adb68a49933ae446bf11935662c83dba55a0804', source_manifest=reference,
        parent_probe_pipeline_checks=probes,
        local_model_cache_safe_projection=safe_metadata, binary_to_tag_reproducible_build_proof=False,
        actual_provider_payload='not_captured', new_model=0, new_live=0, new_MCP=0, new_raster=0, new_image_encoding=0, new_paid=0,
        hidden_reasoning_body_read=False, historical_AL_assignment='own handle task740 expired, current explicit root749 delegation followed, parent records untouched',
        assertions=CHECKS, input_pins=PINS)
    (OUT/'RESULT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(dict(status=result['status'], checks=len(CHECKS), cases=[{k:c[k] for k in ('case','owner_attempts','discovery','all_completed_tools','delivered')} for c in cases])))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        (OUT/'CURRENT_FAILURE.json').write_text(json.dumps(dict(error=repr(error), passed_checks=len(CHECKS), last_checks=CHECKS[-5:]), indent=2), encoding='utf8')
        raise

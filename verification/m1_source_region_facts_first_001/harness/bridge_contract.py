"""Classify actual CLI discovery and bind business results to original RPCs."""

import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DISCOVERY = {
    'list_mcp_resources': ('resources/list', {'resources': []}),
    'list_mcp_resource_templates': ('resources/templates/list', {'resourceTemplates': []}),
}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


result_contract = load('_facts_first_result_contract', HERE / 'reused/result_contract.py')
packer = load('_facts_first_original_packer', ROOT / 'verification/m4_surface_scan_compact_consumption_001/runtime/pack_quality.py')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf8', newline='\n')


def classify_tool_item(item, *, completed=True):
    """Only the fixed server read and observed, exactly empty discovery qualify."""
    if type(item) is not dict or item.get('type') != 'mcp_tool_call':
        return 'unexpected'
    if item.get('server') == 'arm_engine' and item.get('tool') == 'read_observation':
        return 'business'
    if (item.get('server') != 'codex' or item.get('tool') not in DISCOVERY
            or item.get('arguments') not in ({}, {'server': 'arm_engine'})):
        return 'unexpected'
    if not completed:
        return 'pending_resource_discovery'
    result = item.get('result')
    if (item.get('status') != 'completed' or item.get('error') is not None
            or type(result) is not dict or set(result) != {'content', 'structured_content'}
            or result['structured_content'] is not None):
        return 'unexpected'
    content = result['content']
    if (type(content) is not list or len(content) != 1 or type(content[0]) is not dict
            or set(content[0]) != {'type', 'text'} or content[0]['type'] != 'text'):
        return 'unexpected'
    try:
        value = json.loads(content[0]['text'])
    except (TypeError, ValueError):
        return 'unexpected'
    return 'empty_resource_discovery' if value == DISCOVERY[item['tool']][1] else 'unexpected'


def tool_accounting(events):
    completed = [row for row in events if row['type'] == 'item.completed']
    classifications = [classify_tool_item(row['item']) for row in completed]
    started_controls = {row['item'].get('id') for row in events
                        if row['type'] == 'item.started'
                        and classify_tool_item(row['item'], completed=False) == 'pending_resource_discovery'}
    finished_ids = {row['item'].get('id') for row in completed}
    return {'completed_CLI_tool_calls': len(completed), 'completed_CLI_tool_limit': 4,
            'completed_business_calls': classifications.count('business'),
            'completed_empty_discoveries': classifications.count('empty_resource_discovery'),
            'completed_unexpected_tools': classifications.count('unexpected'),
            'incomplete_control_item_ids': sorted(started_controls - finished_ids, key=str)}


def protocol_rpc_records(folder):
    rows = []
    for tx in sorted((Path(folder) / 'attachments').glob('bridge_*/*/TX.bin')):
        request = json.loads(tx.read_bytes())
        rx = tx.with_name('RX.bin')
        response = json.loads(rx.read_bytes()) if rx.exists() else None
        rows.append({'request': request, 'response': response,
                     'TX_path': str(tx), 'TX_sha256': sha(tx),
                     'RX_path': str(rx) if rx.exists() else None,
                     'RX_sha256': sha(rx) if rx.exists() else None})
    return rows


def caller_identity(request, item):
    metadata_value = request.get('params', {}).get('_meta', {})
    metadata = metadata_value if type(metadata_value) is dict else {}
    observed = {key: metadata[key] for key in ('callId', 'itemId', 'threadId') if key in metadata}
    comparisons = []
    for meta_key, public_keys in (('callId', ('callId', 'call_id')),
                                  ('itemId', ('itemId', 'item_id')),
                                  ('threadId', ('threadId', 'thread_id'))):
        for key in public_keys:
            if key in item and meta_key in observed:
                comparisons.append({'metadata_key': meta_key, 'CLI_key': key,
                                    'matched': observed[meta_key] == item[key]})
    return {'RPC_id': request.get('id'), 'CLI_event_item_id': item.get('id'),
            'request_metadata_type': type(metadata_value).__name__,
            'request_metadata_caller_ids': observed, 'exposed_CLI_caller_id_comparisons': comparisons,
            'caller_id_binding': 'compared_exposed_fields' if comparisons else 'caller_ids_unexposed_in_CLI_event',
            'binding_basis': 'server/tool/arguments, original RPC id and exact request/response wire, ordered completed business events'}


def empty_discovery_rpc(request, response, expected):
    params = request.get('params', {})
    return bool(type(response) is dict and set(response) == {'jsonrpc', 'id', 'result'}
                and response['jsonrpc'] == '2.0' and type(request.get('id')) in (str, int)
                and type(request['id']) is type(response.get('id')) and request['id'] == response['id']
                and response['result'] == expected and type(params) is dict
                and not set(params) - {'_meta', 'cursor'} and params.get('cursor') is None
                and ('_meta' not in params or type(params['_meta']) is dict))


def archive_turn(folder, cell, first_attempt, tool_calls):
    """Keep every completed tool while binding owner originals only to reads."""
    folder = Path(folder)
    audit = Path(cell['audit_dir'])
    tools = read(audit / 'TOOLS.json') if (audit / 'TOOLS.json').exists() else {'tools': []}
    selected, binding_errors, result_contracts, source_records = [], [], [], []
    valid_first = type(first_attempt) is int and first_attempt >= 1
    for index, row in enumerate(tools.get('tools', [])):
        if type(row) is not dict or type(row.get('attempt')) is not int or row['attempt'] < 1:
            binding_errors.append({'reason': 'owner_attempt_identity', 'row_index': index})
        elif row['attempt'] >= (first_attempt if valid_first else 1):
            selected.append(row)
    attempts = [row['attempt'] for row in selected]
    if not valid_first or attempts != list(range(first_attempt, first_attempt + len(selected))):
        binding_errors.append({'reason': 'owner_attempt_order', 'first_attempt': first_attempt, 'attempts': attempts})
    business = [row for row in tool_calls if classify_tool_item(row['item']) == 'business']
    controls = [row for row in tool_calls if classify_tool_item(row['item']) == 'empty_resource_discovery']
    unexpected = [row for row in tool_calls if classify_tool_item(row['item']) == 'unexpected']
    if len(tool_calls) > 4:
        binding_errors.append({'reason': 'completed_CLI_tool_budget', 'completed': len(tool_calls), 'limit': 4})
    if unexpected:
        binding_errors.append({'reason': 'unexpected_completed_tools', 'item_ids': [row['item'].get('id') for row in unexpected]})
    if len(selected) != len(business):
        binding_errors.append({'reason': 'owner_and_business_CLI_attempt_count', 'owner': len(selected), 'CLI': len(business)})
    wire = protocol_rpc_records(folder)
    business_wire = [row for row in wire if row['request'].get('method') == 'tools/call']
    if len(business_wire) != len(selected):
        binding_errors.append({'reason': 'owner_and_wire_attempt_count', 'owner': len(selected), 'wire': len(business_wire)})
    for index, (owner, public) in enumerate(zip(selected, business)):
        original = audit / ('tool_' + str(owner['attempt']).zfill(2))
        try:
            request = read(original / 'REQUEST.json')
            response = read(original / 'RESPONSE.json')
            item = public['item']
            if (item.get('server') != 'arm_engine' or request['params']['name'] != item['tool']
                    or packer.encoded(request['params']['arguments']) != packer.encoded(item['arguments'])):
                binding_errors.append({'attempt': owner['attempt'], 'reason': 'CLI_request_differs_from_owner'})
            if type(request.get('id')) not in (str, int) or type(request['id']) is not type(response.get('id')) or request['id'] != response['id']:
                binding_errors.append({'attempt': owner['attempt'], 'reason': 'request_response_id_mismatch'})
            if index >= len(business_wire) or business_wire[index]['request'] != request or business_wire[index]['response'] != response:
                binding_errors.append({'attempt': owner['attempt'], 'reason': 'owner_RPC_differs_from_wire'})
            identity = caller_identity(request, item)
            if any(not row['matched'] for row in identity['exposed_CLI_caller_id_comparisons']):
                binding_errors.append({'attempt': owner['attempt'], 'reason': 'caller_metadata_mismatch'})
            binding = result_contract.bind_tool_result(response, item)
            result_contracts.append({'attempt': owner['attempt'], 'server': item.get('server'),
                                     'tool': item.get('tool'), 'caller_identity': identity, **binding})
            if not binding['matched']:
                binding_errors.append({'attempt': owner['attempt'], 'reason': 'CLI_result_differs_from_owner', 'result_contract': binding})
        except (OSError, ValueError, KeyError, TypeError) as error:
            binding_errors.append({'attempt': owner['attempt'], 'reason': 'owner_original_unreadable', 'error': repr(error)})
    discovery_bindings = []
    for tool, (method, expected) in DISCOVERY.items():
        public_rows = [row for row in controls if row['item']['tool'] == tool]
        rpc_rows = [row for row in wire if row['request'].get('method') == method]
        if len(public_rows) != len(rpc_rows):
            binding_errors.append({'reason': 'discovery_CLI_and_RPC_count', 'tool': tool, 'CLI': len(public_rows), 'RPC': len(rpc_rows)})
        for public, rpc in zip(public_rows, rpc_rows):
            request, response = rpc['request'], rpc['response']
            matched = empty_discovery_rpc(request, response, expected)
            discovery_bindings.append({'CLI_item_id': public['item'].get('id'), 'server': 'codex',
                                       'tool': tool, 'RPC_method': method, 'RPC_id': request.get('id'),
                                       'empty_result': expected, 'matched': matched,
                                       'TX_sha256': rpc['TX_sha256'], 'RX_sha256': rpc['RX_sha256']})
            if not matched:
                binding_errors.append({'reason': 'discovery_original_RPC_mismatch', 'tool': tool})
    for row in selected:
        original = audit / ('tool_' + str(row['attempt']).zfill(2))
        for source in sorted(original.rglob('*')):
            if source.is_file():
                target = folder / 'owner_turn' / original.name / source.relative_to(original)
                target.parent.mkdir(parents=True, exist_ok=True)
                raw = source.read_bytes()
                target.write_bytes(raw)
                source_records.append({'original': str(source), 'copy': target.relative_to(folder).as_posix(),
                                       'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    accounting = {'completed_CLI_tool_calls': len(tool_calls), 'completed_CLI_tool_limit': 4,
                  'completed_business_calls': len(business), 'completed_empty_discoveries': len(controls),
                  'completed_unexpected_tools': len(unexpected), 'owner_attempts': attempts}
    protocol_counts = {}
    for rpc in wire:
        method = rpc['request'].get('method')
        protocol_counts[method] = protocol_counts.get(method, 0) + 1
    save(folder / 'BUSINESS_SOURCE_BINDING.json', {'first_owner_attempt': first_attempt,
        'recorded_owner_attempts': attempts, 'sources': source_records, 'binding_errors': binding_errors,
        'result_contracts': result_contracts, 'discovery_bindings': discovery_bindings,
        'tool_accounting': accounting, 'protocol_RPC_ledger': wire, 'protocol_RPC_method_counts': protocol_counts,
        'scope': 'Original business RPCs and results bound to completed read events. Actual empty discovery RPCs retained and independently matched.'})
    archive = folder.parent / (folder.name + '.raw.zip')
    sources = packer.capture_cell(folder, archive)
    value = {'archive': str(archive), 'archive_sha256': sha(archive), 'archive_bytes': archive.stat().st_size,
             'source_files_sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in sources.items()},
             'original_file_count': len(sources), 'owner_attempts': attempts, 'tool_accounting': accounting,
             'business_binding_errors': binding_errors, 'result_contracts': result_contracts,
             'discovery_bindings': discovery_bindings,
             'scope': 'Raw events, outputs, attachments, all completed CLI tools and original owner business RPCs.'}
    save(folder / 'ARCHIVE.json', value)
    return value

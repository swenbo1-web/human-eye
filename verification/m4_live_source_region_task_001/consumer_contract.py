"""Match CLI output to the original client and owner RPCs for the slot."""

import hashlib
import json
from pathlib import Path


from bridge import DISCOVERY, PRODUCT_TOOL, TOOL_LIMIT, TOOL_NAMES, load, save


HERE = Path(__file__).resolve().parent
M1 = load('_m4_live_accepted_m1_contract', HERE.parent / 'm1_source_region_facts_first_001/harness/bridge_contract.py')
KNOWN_TOOLS = TOOL_NAMES['P']


def read(path):
    return json.loads(Path(path).read_bytes())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def classify_tool_item(item, *, completed=True):
    if type(item) is dict and item.get('type') == 'mcp_tool_call' and item.get('server') == 'arm_engine':
        return 'business' if item.get('tool') in KNOWN_TOOLS else 'unexpected'
    return M1.classify_tool_item(item, completed=completed)


def tool_accounting(events):
    completed = [row for row in events if row['type'] == 'item.completed']
    started = [row for row in events if row['type'] == 'item.started']
    classifications = [classify_tool_item(row['item']) for row in completed]
    completed_ids = {row['item'].get('id') for row in completed}
    open_controls = [row['item'].get('id') for row in started
                     if row['item'].get('id') not in completed_ids
                     and classify_tool_item(row['item'], completed=False) == 'pending_resource_discovery']
    return {'completed_CLI_tool_calls': len(completed), 'business_tool_attempt_limit': TOOL_LIMIT,
            'completed_business_calls': classifications.count('business'),
            'completed_empty_discoveries': classifications.count('empty_resource_discovery'),
            'completed_unexpected_tools': classifications.count('unexpected'),
            'incomplete_control_item_ids': open_controls,
            'started_business_items': sum(classify_tool_item(row['item'], completed=False) == 'business' for row in started)}


def copy_original(source, destination, folder):
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw = source.read_bytes()
    destination.write_bytes(raw)
    return {'original': str(source), 'copy': destination.relative_to(folder).as_posix(),
            'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def archive_turn(folder, cell, first_attempt, tool_calls):
    folder = Path(folder)
    audit = Path(cell['audit_dir'])
    errors, attempts, contracts, protocol, source_records = [], [], [], [], []
    protocol_counts = {}
    if first_attempt != 1:
        errors.append({'reason': 'fresh_owner_attempt_sequence_required', 'first_attempt': first_attempt})
    for tx in sorted((folder / 'attachments').glob('bridge_*/*/TX.bin')):
        rx = tx.with_name('RX.bin')
        receipt = tx.with_name('RECEIPT.json')
        request = read(tx)
        response = read(rx) if rx.exists() else None
        wire = {'request': request, 'response': response, 'TX_sha256': digest(tx),
                'RX_sha256': digest(rx) if rx.exists() else None,
                'TX_path': str(tx), 'RX_path': str(rx) if rx.exists() else None,
                'receipt': read(receipt) if receipt.exists() else {}}
        method = request.get('method')
        protocol_counts[method] = protocol_counts.get(method, 0) + 1
        if method == 'tools/call':
            attempts.append(wire)
        else:
            protocol.append(wire)
    clients = [row for row in tool_calls if classify_tool_item(row['item']) == 'business']
    owner_rows = read(audit / 'TOOLS.json')['tools']
    actual_owner = {row['attempt']: row for row in owner_rows}
    if len(actual_owner) != len(owner_rows) or set(actual_owner) - set(range(1, len(attempts) + 1)):
        errors.append({'reason': 'orphan_or_duplicate_owner_attempt', 'owner_attempts': list(actual_owner)})
    if len(attempts) > TOOL_LIMIT or len(clients) > TOOL_LIMIT:
        errors.append({'reason': 'tool_attempt_budget_exceeded', 'wire': len(attempts), 'CLI': len(clients)})
    if len(attempts) != len(clients):
        errors.append({'reason': 'CLI_and_wire_attempt_count', 'wire': len(attempts), 'CLI': len(clients)})
    actual_latest = None
    actual_first_evidence = None
    for attempt, wire in enumerate(attempts, 1):
        request, response, receipt = wire['request'], wire['response'], wire['receipt']
        method_params = request.get('params') or {}
        result_row = {'attempt': attempt, 'tool': method_params.get('name'), 'receipt': receipt,
                      'TX_sha256': wire['TX_sha256'], 'RX_sha256': wire['RX_sha256']}
        contracts.append(result_row)
        if receipt.get('attempt') != attempt or receipt.get('flush_completed_ns') is None:
            errors.append({'attempt': attempt, 'reason': 'incomplete_or_misnumbered_stdio_attempt'})
        if (type(response) is not dict or type(request.get('id')) not in (str, int)
                or type(request['id']) is not type(response.get('id')) or request['id'] != response['id']):
            errors.append({'attempt': attempt, 'reason': 'RPC_response_binding'})
        original = audit / f'tool_{attempt:02d}'
        for source in sorted(original.rglob('*')):
            if source.is_file():
                target = folder / 'owner_turn' / original.name / source.relative_to(original)
                source_records.append(copy_original(source, target, folder))
        if attempt in actual_owner and read(original / 'REQUEST.json') != request:
            errors.append({'attempt': attempt, 'reason': 'owner_request_differs_from_wire'})
        if receipt.get('origin') == 'owner':
            if attempt not in actual_owner or read(original / 'RESPONSE.json') != response:
                errors.append({'attempt': attempt, 'reason': 'owner_response_differs_from_wire'})
        elif receipt.get('origin') not in ('transport_failure', 'budget_refusal'):
            errors.append({'attempt': attempt, 'reason': 'unexplained_response_origin'})
        if attempt > len(clients):
            continue
        event = clients[attempt - 1]
        item = event['item']
        result_row['CLI_received_ns'] = event['perf_ns']
        result_row['caller_identity'] = identity = M1.caller_identity(request, item)
        if ((item.get('tool'), item.get('arguments', {})) != (method_params.get('name'), method_params.get('arguments', {}))
                or any(not row['matched'] for row in identity['exposed_CLI_caller_id_comparisons'])):
            errors.append({'attempt': attempt, 'reason': 'CLI_request_differs_from_wire'})
        binding = M1.result_contract.bind_tool_result(response, item)
        result_row.update(binding)
        if not binding['matched']:
            errors.append({'attempt': attempt, 'reason': 'CLI_result_differs_from_wire', 'binding': binding})
            continue
        blocks = response['result']['content']
        result_row['CLI_text_UTF8_bytes'] = sum(len(block['text'].encode('utf8')) for block in blocks if block['type'] == 'text')
        result_row['CLI_images'] = sum(block['type'] == 'image' for block in blocks)
        actual_latest = event['perf_ns']
        # Tool errors and empty stdout do not deliver evidence. The score still checks relevance of the facts.
        has_text = result_row['CLI_text_UTF8_bytes'] > 0
        if item.get('tool') in ('execute_python', 'execute_blender_code') and has_text:
            value = json.loads(blocks[0]['text']) if not response['result']['isError'] else {}
            has_text = bool(value.get('stdout', '').strip())
        if not response['result']['isError'] and (has_text or result_row['CLI_images']) and actual_first_evidence is None:
            actual_first_evidence = event['perf_ns']
    discovery = []
    for name, (method, expected) in M1.DISCOVERY.items():
        expected_cli = [row for row in tool_calls if classify_tool_item(row['item']) == 'empty_resource_discovery'
                        and row['item']['tool'] == name]
        expected_wire = [row for row in protocol if row['request'].get('method') == method]
        if len(expected_cli) != len(expected_wire):
            errors.append({'reason': 'resource_discovery_count_mismatch', 'method': method})
        for event, wire in zip(expected_cli, expected_wire):
            matched = M1.empty_discovery_rpc(wire['request'], wire['response'], expected)
            discovery.append({'method': method, 'item_id': event['item'].get('id'), 'matched': matched,
                              'TX_sha256': wire['TX_sha256'], 'RX_sha256': wire['RX_sha256']})
            if not matched:
                errors.append({'reason': 'resource_discovery_wire_mismatch', 'method': method})
    if cell['group'] == 'P':
        product_attempts = [row['attempt'] for row in owner_rows
                            if (audit / f'tool_{row["attempt"]:02d}' / 'PRODUCT_ARGUMENTS.json').is_file()]
        if not product_attempts:
            errors.append({'reason': 'missing_initial_P_standard_product_query'})
        else:
            initial = audit / f'tool_{product_attempts[0]:02d}'
            args = read(initial / 'PRODUCT_ARGUMENTS.json')
            if args.get('query', {}).get('mode') != 'source_region' or actual_owner[product_attempts[0]]['name'] != PRODUCT_TOOL:
                errors.append({'reason': 'initial_P_query_is_not_standard_source_region'})
    ledger = {'first_owner_attempt': first_attempt, 'recorded_owner_attempts': list(actual_owner),
              'stdio_attempts': len(attempts), 'tool_attempt_limit': TOOL_LIMIT, 'protocol_RPC_method_counts': protocol_counts,
              'result_contracts': contracts, 'binding_errors': errors, 'sources': source_records,
              'discovery_bindings': discovery, 'first_CLI_nonempty_successful_evidence_ns': actual_first_evidence,
              'last_CLI_tool_result_ns': actual_latest, 'protocol_controls': protocol}
    save(folder / 'BUSINESS_SOURCE_BINDING.json', ledger)
    archive = folder.parent / (folder.name + '.raw.zip')
    packed = M1.packer.capture_cell(folder, archive)
    value = {**ledger, 'archive': str(archive), 'archive_sha256': digest(archive), 'archive_bytes': archive.stat().st_size,
             'source_files_sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in packed.items()},
             'business_binding_errors': errors, 'owner_attempts': list(actual_owner)}
    save(folder / 'ARCHIVE.json', value)
    return value

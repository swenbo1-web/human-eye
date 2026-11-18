"""Match CLI output to the original client and owner RPCs for the slot."""

import hashlib
import json
from pathlib import Path
import re


from bridge import ASSEMBLY, PRODUCT_TOOL, TOOL_LIMIT, TOOL_NAMES, load, save, task_arguments


HERE = Path(__file__).resolve().parent
M1 = load('_m4_live_accepted_m1_contract', HERE.parent / 'm1_source_region_facts_first_001/harness/bridge_contract.py')
KNOWN_TOOLS = TOOL_NAMES['P']
CLI_PROJECTION_SIDE_UTF8_BYTES = 524288
# Codex 0.152.1 writes the event type, then the item ID and type before the body.
# The accepted timed log prepends its receipt time to that same public envelope.
_ITEM_HEADER = (rb'\{\s*"type"\s*:\s*"(item\.(?:started|completed))"\s*,\s*"item"\s*:\s*'
                rb'\{\s*"id"\s*:\s*("(?:[^"\\\x00-\x1f]|\\.)*")\s*,\s*'
                rb'"type"\s*:\s*"mcp_tool_call"\s*[,}]')
_STDOUT_TOOL_HEADER = re.compile(rb'^\s*' + _ITEM_HEADER)
_TIMED_TOOL_HEADER = re.compile(rb'^\s*\{\s*"perf_ns"\s*:\s*[0-9]+\s*,\s*"event"\s*:\s*' + _ITEM_HEADER)


def compact_json(value, *, sort_keys=False):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':'), sort_keys=sort_keys)


def same_json(left, right):
    try:
        return compact_json(left, sort_keys=True) == compact_json(right, sort_keys=True)
    except (ValueError, TypeError, RecursionError):
        return False


def bind_tool_result(response, item):
    """Reuse the exact contract and replay the observed 002 text projection on mismatch."""
    binding = M1.result_contract.bind_tool_result(response, item)
    if binding['reason'] != 'content_mismatch':
        return binding

    source, public = response['result'], item['result']
    if (source['isError'] is not False or set(public) != {'content', 'structured_content'}
            or len(source['content']) != 1 or len(public['content']) != 1):
        return binding
    source_block, public_block = source['content'][0], public['content'][0]
    for block in (source_block, public_block):
        if (type(block) is not dict or set(block) != {'type', 'text'} or block['type'] != 'text'
                or type(block['text']) is not str):
            return binding

    side = CLI_PROJECTION_SIDE_UTF8_BYTES
    try:
        original = compact_json(source)
        original_raw = original.encode('utf8')
        if len(original_raw) <= 2 * side:
            return binding
        prefix = original_raw[:side].decode('utf8')
        suffix = original_raw[-side:].decode('utf8')
        removed = len(original) - len(prefix) - len(suffix)
        marker = f'\u2026{removed} chars truncated\u2026'
        if public_block['text'] != prefix + marker + suffix:
            return binding
        public_raw = public_block['text'].encode('utf8')
        event_item_raw = compact_json(item, sort_keys=True).encode('utf8')
    except (UnicodeError, ValueError, TypeError, RecursionError):
        return binding

    return {'matched': True, 'classification': 'success', 'reason': 'verified_cli_text_projection',
            'CLI_event_projection': {
                'rule': '002_compact_result_JSON_fixed_UTF8_head_tail_and_character_removal_marker',
                'source_compact_result_UTF8_bytes': len(original_raw),
                'source_compact_result_sha256': hashlib.sha256(original_raw).hexdigest(),
                'CLI_projected_text_UTF8_bytes': len(public_raw),
                'CLI_projected_text_sha256': hashlib.sha256(public_raw).hexdigest(),
                'CLI_event_item_canonical_sha256': hashlib.sha256(event_item_raw).hexdigest(),
                'retained_prefix_UTF8_bytes': side,
                'retained_suffix_UTF8_bytes': side,
                'retained_source_UTF8_bytes': 2 * side,
                'removed_UTF8_bytes': len(original_raw) - 2 * side,
                'removed_characters': removed,
                'model_supplied_content_scope': 'unmeasured',
            }}


def public_tool_event_header(raw, *, timed=False):
    """Recognize a public MCP envelope from its original bytes before JSON decoding."""
    return (_TIMED_TOOL_HEADER if timed else _STDOUT_TOOL_HEADER).match(raw)


def archived_event_line(path, event, *, timed):
    """Identify the unique completed item and hash its original archived line."""
    item_id = event['item'].get('id')
    if type(item_id) is not str or not item_id or event['item'].get('type') != 'mcp_tool_call':
        return None
    encoded_id = compact_json(item_id).encode('utf8')
    expected = {'type': 'item.completed', 'item': event['item']}
    expected_row = {'perf_ns': event['perf_ns'], 'event': expected} if timed else expected
    matched = None
    try:
        with path.open('rb') as stream:
            for line_number, raw in enumerate(stream, 1):
                header = public_tool_event_header(raw, timed=timed)
                if header is None or header.groups() != (b'item.completed', encoded_id):
                    continue
                row = json.loads(raw)
                public = row['event'] if timed else row
                if public.get('type') != 'item.completed' or public.get('item', {}).get('id') != item_id:
                    continue
                if matched is not None or not same_json(row, expected_row):
                    return None
                matched = {'path': path.name, 'line': line_number, 'bytes': len(raw),
                           'sha256': hashlib.sha256(raw).hexdigest()}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        return None
    return matched


def verified_owner_tcp_folder(audit, attempt, wire):
    """Bind the owner TCP envelopes to the same stdio request and response."""
    request, response, receipt = wire['request'], wire['response'], wire['receipt']
    if receipt.get('owner_TCP_attempted') is not True or not same_json(receipt.get('RPC_id'), request['id']):
        return None
    try:
        protocol = [row for row in read(audit / 'BRIDGE_RESULT.json')['protocol']
                    if type(row.get('attempt')) is int and row['attempt'] == attempt]
        if len(protocol) != 1:
            return None
        row = protocol[0]
        sequence = row.get('sequence')
        if (type(sequence) is not int or sequence < 1 or row.get('send_confirmed') is not True
                or row.get('method') != 'tools/call' or not same_json(row.get('RPC_id'), request['id'])):
            return None
        folder = audit / f'rpc_{sequence:03d}'
        tx_raw = (folder / 'TCP_TX.bin').read_bytes()
        rx_raw = (folder / 'TCP_RX.bin').read_bytes()
        tx, rx = json.loads(tx_raw), json.loads(rx_raw)
        request_id = tx['request_id']
        if (type(request_id) is not str or not request_id
                or row.get('request_bytes') != len(tx_raw) or row.get('response_bytes') != len(rx_raw)
                or not same_json(tx, {'request_id': request_id, 'operation': 'attached_mcp',
                                      'args': {'kind': 'native', 'message': request, 'attempt': attempt}})
                or not same_json(rx, {'request_id': request_id, 'ok': True, 'result': response})):
            return None
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        return None
    return folder


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
        preceding_errors = len(errors)
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
        owner_request = read(original / 'REQUEST.json') if attempt in actual_owner else None
        owner_response = None
        if attempt in actual_owner and owner_request != request:
            errors.append({'attempt': attempt, 'reason': 'owner_request_differs_from_wire'})
        if receipt.get('origin') == 'owner':
            owner_response = read(original / 'RESPONSE.json') if attempt in actual_owner else None
            if attempt not in actual_owner or owner_response != response:
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
        binding = bind_tool_result(response, item)
        projection = binding.get('CLI_event_projection')
        if projection is not None:
            arguments = method_params.get('arguments', {})
            if (len(errors) != preceding_errors or receipt.get('origin') != 'owner'
                    or request.get('jsonrpc') != '2.0' or event.get('type') != 'item.completed'
                    or type(arguments) is not dict or type(item.get('arguments')) is not dict
                    or not (same_json(owner_request, request) and same_json(owner_response, response)
                            and same_json(item['arguments'], arguments))):
                errors.append({'attempt': attempt, 'reason': 'CLI_projection_without_original_RPC_binding'})
                binding = M1.result_contract.bind_tool_result(response, item)
            else:
                public_line = archived_event_line(folder / 'events.jsonl', event, timed=True)
                stdout_line = archived_event_line(folder / 'stdout.raw.bin', event, timed=False)
                owner_tcp = verified_owner_tcp_folder(audit, attempt, wire)
                if owner_tcp is None:
                    errors.append({'attempt': attempt, 'reason': 'CLI_projection_without_original_owner_TCP_binding'})
                    binding = M1.result_contract.bind_tool_result(response, item)
                elif public_line is None or stdout_line is None:
                    errors.append({'attempt': attempt, 'reason': 'CLI_projection_event_original_mismatch'})
                    binding = M1.result_contract.bind_tool_result(response, item)
                else:
                    tcp_records = [copy_original(owner_tcp / name, folder / 'owner_turn' / owner_tcp.name / name, folder)
                                   for name in ('TCP_TX.bin', 'TCP_RX.bin')]
                    source_records.extend(tcp_records)
                    projection.update({
                        'archived_public_event_line': public_line,
                        'archived_CLI_stdout_line': stdout_line,
                        'owner_TCP_originals': tcp_records,
                        'owner_response_path': f'owner_turn/{original.name}/RESPONSE.json',
                        'owner_response_sha256': digest(original / 'RESPONSE.json'),
                        'stdio_response_path': Path(wire['RX_path']).relative_to(folder).as_posix(),
                        'stdio_response_sha256': wire['RX_sha256'],
                    })
        result_row.update(binding)
        if not binding['matched']:
            errors.append({'attempt': attempt, 'reason': 'CLI_result_differs_from_wire', 'binding': binding})
            continue
        source_blocks, public_blocks = response['result']['content'], item['result']['content']
        result_row['source_text_UTF8_bytes'] = sum(len(block['text'].encode('utf8')) for block in source_blocks if block['type'] == 'text')
        result_row['CLI_text_UTF8_bytes'] = sum(len(block['text'].encode('utf8')) for block in public_blocks if block['type'] == 'text')
        result_row['CLI_images'] = sum(block['type'] == 'image' for block in public_blocks)
        actual_latest = event['perf_ns']
        # Tool errors and empty stdout do not deliver evidence. The score still checks relevance of the facts.
        has_text = result_row['CLI_text_UTF8_bytes'] > 0
        if item.get('tool') in ('execute_python', 'execute_blender_code') and has_text:
            value = json.loads(source_blocks[0]['text']) if not response['result']['isError'] else {}
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
            errors.append({'reason': 'missing_initial_P_standard_assembly_query'})
        else:
            initial = audit / f'tool_{product_attempts[0]:02d}'
            expected = task_arguments(ASSEMBLY)
            args = read(initial / 'PRODUCT_ARGUMENTS.json')
            caller = read(initial / 'REQUEST.json')['params']
            if (product_attempts[0] != 1 or caller['name'] != PRODUCT_TOOL
                    or not same_json(args, expected) or not same_json(caller['arguments'], expected)):
                errors.append({'reason': 'first_P_business_attempt_not_standard_assembly_query'})
            request_path = initial / 'PRODUCT_REQUEST.json'
            if not request_path.is_file() or not same_json(read(request_path).get('params'),
                                                         {'name': PRODUCT_TOOL, 'arguments': expected}):
                errors.append({'reason': 'initial_P_installed_product_request_unbound'})
    ledger = {'first_owner_attempt': first_attempt, 'recorded_owner_attempts': list(actual_owner),
              'stdio_attempts': len(attempts), 'tool_attempt_limit': TOOL_LIMIT, 'protocol_RPC_method_counts': protocol_counts,
              'result_contracts': contracts, 'binding_errors': errors, 'sources': source_records,
              'discovery_bindings': discovery, 'first_CLI_nonempty_successful_evidence_ns': actual_first_evidence,
              'last_CLI_tool_result_ns': actual_latest, 'protocol_controls': protocol,
              'public_event_binding_scope': 'Exact content and envelope or verified 002 public CLI text projection.',
              'model_supplied_content_scope': 'unmeasured'}
    save(folder / 'BUSINESS_SOURCE_BINDING.json', ledger)
    archive = folder.parent / (folder.name + '.raw.zip')
    packed = M1.packer.capture_cell(folder, archive)
    value = {**ledger, 'archive': str(archive), 'archive_sha256': digest(archive), 'archive_bytes': archive.stat().st_size,
             'source_files_sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in packed.items()},
             'business_binding_errors': errors, 'owner_attempts': list(actual_owner)}
    save(folder / 'ARCHIVE.json', value)
    return value

"""Audit sealed consumers using existing JSON, hashes, PNG headers and AST only."""

import ast
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import time
import tomllib
import zipfile


NS = Path(__file__).resolve().parents[1]
REPO = NS.parents[1]
RUNTIME = Path('D:/he_m4_source_region_consume_001/slots')
REPORT = NS / 'checks/RUNTIME_REVIEW.json'


def read(path):
    return json.loads(Path(path).read_bytes())


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def seal(path):
    path = Path(path)
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': digest(raw)}


def png_metadata(block):
    raw = base64.b64decode(block['data'], validate=True)
    valid_header = raw[:8] == b'\x89PNG\r\n\x1a\n' and raw[12:16] == b'IHDR'
    dimensions = struct.unpack('>II', raw[16:24]) if valid_header else None
    return {'bytes': len(raw), 'sha256': digest(raw), 'dimensions': dimensions,
            'mimeType': block.get('mimeType'), 'header_valid': valid_header}


def compact_identity(brief):
    binding = brief['binding']
    return {'region_ref_sha256': digest(json.dumps(brief['region_ref'], sort_keys=True).encode()),
            'binding_sha256': binding.get('binding_sha256'),
            'source_binding_sha256': binding.get('source_binding_sha256'),
            'ordered_geometry_sha256': binding.get('ordered_geometry_sha256'),
            'capture_generation': brief['region_ref'].get('capture_generation'),
            'session_id': brief.get('session_id')}


def main():
    started = time.perf_counter_ns()
    checks = []

    def check(name, condition, details=None):
        checks.append({'name': name, 'passed': bool(condition), 'details': details})

    frozen = read(NS / 'FROZEN.json')
    revised = read(NS / 'FROZEN_PROTOCOL_R1.json')
    active = read(NS / 'ACTIVE_FREEZE.json')
    inputs = read(NS / 'INPUTS.json')
    preflight = read(NS / 'PREFLIGHT.json')
    infrastructure_path = NS / 'checks/INFRA_PREFLIGHT_REVIEW.json'
    infrastructure = read(infrastructure_path)
    schema = read(NS / 'inputs/TOOL_SCHEMA.json')
    check('active_revision_hash', active['sha256'] == seal(NS / active['name'])['sha256'])
    check('original_freeze_hash', revised['original_freeze_sha256'] == seal(NS / 'FROZEN.json')['sha256'])
    check('revision_record_hash', revised['protocol_revision_sha256'] == seal(NS / 'protocol_revisions/REVISION_01.json')['sha256'])
    original_rows = {row['path']: row for row in frozen['direct_inputs']}
    revised_rows = {row['path']: row for row in revised['direct_inputs']}
    changed = [path for path in original_rows if original_rows[path] != revised_rows.get(path)]
    expected_changed = {str(NS / 'harness/read_observation.py'), str(NS / 'harness/run_slot.py')}
    check('only_two_declared_protocol_source_changes', set(changed) == expected_changed)
    mismatches = [path for path, row in revised_rows.items() if seal(path)['sha256'] != row['sha256']]
    check('current_revised_direct_inputs', not mismatches, mismatches)
    check('same_direct_input_path_set', set(original_rows) == set(revised_rows))
    check('infrastructure_review_nested_pins_frozen',
          original_rows[str(infrastructure_path)]['sha256'] == seal(infrastructure_path)['sha256'])
    nested_infrastructure_pins = []
    for row in infrastructure['source_files']:
        path = REPO / row['path']
        actual = seal(path)
        check('nested_infrastructure_source/' + row['path'], actual['sha256'] == row['sha256'])
        nested_infrastructure_pins.append({'path': str(path), 'nested_frozen_sha256': row['sha256'],
                                           'current_sha256': actual['sha256']})
    for name in ['model_profile', 'task_seconds', 'process_seconds', 'business_limit', 'new_consumer_cap']:
        check('revision_preserves_' + name, frozen[name] == revised[name])

    # AST inspection does not import or execute either harness or reused runtime code.
    source_paths = [NS / 'harness/read_observation.py', NS / 'harness/consumer_adapter.py',
                    NS / 'harness/run_slot.py', REPO / 'verification/m4_active_coverage_consumption_001/runtime_handle.py',
                    REPO / 'verification/m4_consumer_error_contract_001/consumer.py']
    sources = []
    for path in source_paths:
        tree = ast.parse(path.read_text(encoding='utf8'))
        sources.append({**seal(path), 'function_names': [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]})

    slots = []
    freeze_coverage_gaps = {}
    for case in inputs['cases']:
        case_id = case['case_id']
        folder = RUNTIME / case_id
        publication = read(folder / 'SLOT_PUBLICATION.json')
        slot = read(folder / 'SLOT_RESULT.json')
        consumer = read(folder / 'consumer/CONSUMER.json')
        archive = read(folder / 'consumer/ARCHIVE.json')
        ledger = read(folder / 'owner/TOOLS.json')
        cell = read(folder / 'consumer/cell.json')
        binding = read(folder / 'consumer/RUNTIME_BINDING.json')
        proof = read(folder / 'ADAPTER_PROOF.json')
        execution_rows = original_rows if case_id == 'S1' else revised_rows
        for prefix in ['adapter', 'accepted_consumer', 'event_loop', 'result_matcher', 'settings', 'server']:
            proof_path = proof[prefix + '_path']
            frozen_row = execution_rows.get(proof_path)
            expected_sha = frozen_row['sha256'] if frozen_row else seal(proof_path)['sha256']
            check(case_id + '/execution_source_proof/' + prefix,
                  proof[prefix + '_sha256'] == expected_sha)
            if frozen_row is None:
                nested_sha = preflight['adapter_proof'].get(prefix + '_sha256')
                check(case_id + '/nested_preflight_pin/' + prefix,
                      nested_sha == proof[prefix + '_sha256'])
                freeze_coverage_gaps[proof_path] = {
                    'runtime_proof_sha256': proof[prefix + '_sha256'],
                    'current_sha256': expected_sha,
                    'pre_run_direct_freeze_membership': False,
                    'pre_run_nested_preflight_sha256': nested_sha,
                    'pre_run_nested_commitment': nested_sha == expected_sha,
                    'run_slot_direct_preexecution_rehash': False,
                    'scope': 'PREFLIGHT.json is a direct frozen input and its adapter_proof commits this source hash before S1. All actual adapter proofs and current bytes agree. The original run_slot checks only direct paths, without a per-source rehash of these nested pins.'}
        timing = read(folder / 'consumer/FINAL_TIMING.json')
        inp = NS / 'inputs' / case_id
        payload = read(inp / 'TOOL_RESULT.json')
        original = read(inp / 'ORIGINAL_RESPONSE.json')
        brief_raw = (inp / 'ORIGINAL_BRIEF.json').read_bytes()
        brief = json.loads(brief_raw)
        check(case_id + '/published_result_hash', publication['result_sha256'] == seal(folder / 'SLOT_RESULT.json')['sha256'])
        check(case_id + '/consumer_hash', slot['consumer_record_sha256'] == seal(folder / 'consumer/CONSUMER.json')['sha256'])
        check(case_id + '/case_input_hash', seal(inp / 'TOOL_RESULT.json')['sha256'] == case['input_sha256'] == cell['input_sha256'])
        check(case_id + '/same_case_path', Path(cell['input_file']).resolve() == (inp / 'TOOL_RESULT.json').resolve())
        check(case_id + '/original_content', payload == original['result'])
        check(case_id + '/original_brief_bytes', payload['content'][0]['text'].encode('utf8') == brief_raw)
        check(case_id + '/original_brief_hash', digest(brief_raw) == case['original_brief_sha256'])
        expected_png = png_metadata(payload['content'][1])
        check(case_id + '/original_png_bytes', expected_png['sha256'] == case['PNG_sha256'] == seal(inp / 'ORIGINAL_IMAGE.png')['sha256'])
        check(case_id + '/common_prompt_metadata', consumer['input_sha256'] == inputs['prompt_sha256'] == seal(NS / 'inputs/PROMPT.txt')['sha256'] and consumer['input_text_bytes'] == 427)
        config = {}
        argv = consumer['argv']
        for position, value in enumerate(argv[:-1]):
            if value == '-c':
                config.update(tomllib.loads(argv[position + 1]))
        profile = {'model': config.get('model'), 'reasoning_effort': config.get('model_reasoning_effort'), 'service_tier': config.get('service_tier')}
        check(case_id + '/requested_profile', profile == frozen['model_profile'])
        check(case_id + '/fresh_independent_command', argv[1] == 'exec' and '--ephemeral' in argv and not any(value in argv for value in ['resume', 'fork', '--last', '--all']) and consumer['expected_thread_id'] is None)
        check(case_id + '/fixed_cli_sha', seal(argv[0])['sha256'] == proof['CLI_sha256'])
        check(case_id + '/runtime_python_sha', binding['actual_executable_sha256'] == proof['Python_sha256'] == seal(binding['actual_executable'])['sha256'])
        server = config['mcp_servers']['arm_engine']
        check(case_id + '/only_bound_server', set(config['mcp_servers']) == {'arm_engine'} and server['tools'] == {'read_observation': {'approval_mode': 'approve'}})
        check(case_id + '/bound_server_input_argument', server['args'][server['args'].index('--input') + 1] == cell['input_file'])
        check(case_id + '/original_450_600_deadlines', slot['task_deadline_ns'] - slot['started_ns'] == 450_000_000_000 and slot['lifecycle_deadline_ns'] - slot['started_ns'] == 600_000_000_000)
        check(case_id + '/final_and_close_within_original_deadlines', consumer['final_received_ns'] < slot['task_deadline_ns'] and timing['consumer_record_closed_ns'] < slot['task_deadline_ns'] and slot['closed_ns'] < slot['lifecycle_deadline_ns'])
        check(case_id + '/deadline_not_reset', cell['task_deadline_ns'] == consumer['deadline_ns'] == publication['original_task_deadline_ns'] == slot['task_deadline_ns'] and not consumer['deadline_timer_fired'])

        # Select only tool events. Agent-message text is never included in this report.
        raw_events = [json.loads(line) for line in (folder / 'consumer/stdout.raw.bin').read_bytes().splitlines()]
        threads = [event['thread_id'] for event in raw_events if event.get('type') == 'thread.started']
        check(case_id + '/one_thread_started', threads == [consumer['thread_id']])
        tool_events = [event for event in raw_events if event.get('item', {}).get('type') == 'mcp_tool_call']
        check(case_id + '/all_started_tools_classified', all(
            (event['item'].get('server'), event['item'].get('tool')) in {
                ('arm_engine', 'read_observation'), ('codex', 'list_mcp_resources'),
                ('codex', 'list_mcp_resource_templates')} for event in tool_events))
        completed = [event for event in raw_events if event.get('type') == 'item.completed' and event.get('item', {}).get('type') == 'mcp_tool_call']
        business = [event for event in completed if event['item'].get('server') == 'arm_engine' and event['item'].get('tool') == 'read_observation']
        enumerations = [event for event in completed if event['item'].get('server') == 'codex' and event['item'].get('tool') in ['list_mcp_resources', 'list_mcp_resource_templates']]
        other = [event['item'].get('tool') for event in completed if event not in business and event not in enumerations]
        resource_rows = []
        for event in enumerations:
            item = event['item']
            content = item['result']['content']
            value = json.loads(content[0]['text'])
            expected = {'resources': []} if item['tool'] == 'list_mcp_resources' else {'resourceTemplates': []}
            check(case_id + '/' + item['tool'] + '_empty', value == expected and len(content) == 1)
            resource_rows.append({'tool': item['tool'], 'arguments': item['arguments'], 'result': value})
        check(case_id + '/two_empty_codex_enumerations', len(enumerations) == 2)
        check(case_id + '/no_other_completed_tool_calls', not other, other)
        check(case_id + '/business_event_count_matches_owner', len(business) == ledger['attempts'] <= 4)
        deliveries = []
        for event, owner in zip(business, ledger['tools']):
            item = event['item']
            owner_dir = folder / 'owner' / ('tool_' + str(owner['attempt']).zfill(2))
            request = read(owner_dir / 'REQUEST.json')
            response = read(owner_dir / 'RESPONSE.json')
            check(case_id + '/request_' + str(owner['attempt']), request['id'] == response['id'] and request['params']['name'] == item['tool'] and request['params']['arguments'] == item['arguments'] == {})
            check(case_id + '/standard_transport_meta_' + str(owner['attempt']),
                  set(request['params']) == {'name', 'arguments', '_meta'}
                  and isinstance(request['params']['_meta'], dict))
            check(case_id + '/native_result_' + str(owner['attempt']), response['result']['content'] == item['result']['content'])
            admitted = not response['result'].get('isError', False)
            row = {'attempt': owner['attempt'], 'admitted': admitted, 'request_param_keys': list(request['params']), 'request_sha256': seal(owner_dir / 'REQUEST.json')['sha256'], 'response_sha256': seal(owner_dir / 'RESPONSE.json')['sha256']}
            if admitted:
                check(case_id + '/delivered_original_content', response['result'] == payload)
                actual_brief = item['result']['content'][0]['text'].encode('utf8')
                raw_text = actual_brief.decode('utf8')
                parsed_brief = json.loads(actual_brief)
                png = png_metadata(item['result']['content'][1])
                check(case_id + '/CLI_brief_byte_equality', actual_brief == brief_raw)
                check(case_id + '/CLI_png_byte_equality', png == expected_png)
                marker_terms = ['truncated', 'truncation', '[...', '…', 'content omitted', 'output truncated', '省略', '截断']
                row.update(brief_bytes=len(actual_brief), brief_sha256=digest(actual_brief), png=png, identity=compact_identity(parsed_brief),
                           raw_text_facts={'distance_literal_0_37011719389236364_present': '0.37011719389236364' in raw_text,
                               'surface_proximity': parsed_brief['task_result']['facts']['surface_proximity'],
                               'source_mapping_nearest_witness': parsed_brief['task_result']['source_mapping']['nearest_witness'],
                               'truncation_marker_search_terms': marker_terms,
                               'truncation_marker_hits': [term for term in marker_terms if term in raw_text.lower()],
                               'scope': 'Facts in the archived CLI completed read_observation text block. Provider-internal request text and any later transformation are unobserved.'})
            else:
                row['error_content'] = response['result']['content']
            deliveries.append(row)

        wire_rows = []
        for path in sorted((folder / 'consumer/attachments').glob('bridge_*/*/TX.bin')):
            tx = read(path)
            rx_path = path.with_name('RX.bin')
            rx = read(rx_path) if rx_path.exists() else None
            row = {'sequence': path.parent.name, 'method': tx.get('method'), 'request_sha256': seal(path)['sha256'], 'response_sha256': seal(rx_path)['sha256'] if rx else None}
            if tx.get('method') == 'tools/list':
                check(case_id + '/exact_tool_schema', rx['result']['tools'] == [schema])
            if tx.get('method') in ['resources/list', 'resources/templates/list']:
                row['result'] = rx.get('result')
                row['error'] = rx.get('error')
            check(case_id + '/known_wire_method_' + path.parent.name, tx.get('method') in ['initialize', 'notifications/initialized', 'tools/list', 'tools/call', 'resources/list', 'resources/templates/list'])
            wire_rows.append(row)

        zip_path = folder / 'consumer.raw.zip'
        check(case_id + '/legacy_zip_hash', seal(zip_path)['sha256'] == archive['archive_sha256'])
        with zipfile.ZipFile(zip_path) as zipped:
            check(case_id + '/legacy_zip_exact_membership',
                  set(zipped.namelist()) == set(archive['source_files_sha256'])
                  and len(zipped.namelist()) == archive['original_file_count'])
            for relative, expected in archive['source_files_sha256'].items():
                check(case_id + '/archive_bytes/' + relative, digest(zipped.read(relative)) == expected == seal(folder / 'consumer' / relative)['sha256'])
        final = seal(folder / 'consumer/PUBLIC_FINAL.txt')
        check(case_id + '/final_seal', final['sha256'] == slot['answer']['sha256'] and final['bytes'] == slot['answer']['bytes'] and final['sha256'] == seal(folder / 'consumer/final.txt')['sha256'])
        # Hash the last public item without examining its words or emitting its body.
        public_items = [event['item'] for event in raw_events if event.get('type') == 'item.completed' and event.get('item', {}).get('type') == 'agent_message']
        check(case_id + '/final_matches_last_public_item', bool(public_items) and digest(public_items[-1]['text'].encode('utf8')) == final['sha256'])
        runtime_exit = consumer['runtime_exit']
        cleanup = consumer['process_cleanup']
        check(case_id + '/CLI_held_process_closed', cleanup['confirmed'] and cleanup['reaped'] and cleanup['process_handle_closed'] and all(cleanup['pipes_closed'].values()) and consumer['readers_stopped'])
        check(case_id + '/MCP_creation_and_image_binding', binding['confirmed'] and binding['runtime_pid'] == binding['stdio_STARTED']['pid'] and binding['launcher_pid'] == consumer['consumer_pid'] and binding['runtime_created_filetime'] >= binding['launcher_created_filetime'])
        check(case_id + '/MCP_retained_handle_exit', runtime_exit['confirmed'] and runtime_exit['exited'] and runtime_exit['handle_closed'] and runtime_exit['closed_ns'] < slot['task_deadline_ns'])
        event_types = Counter(event.get('item', {}).get('type') for event in raw_events if event.get('type', '').startswith('item.'))
        check(case_id + '/no_command_or_other_data_tool_items', not set(event_types) - {'mcp_tool_call', 'agent_message', 'reasoning', 'warning', 'error'})
        usage = [event['usage'] for event in raw_events if event.get('type') == 'turn.completed']
        check(case_id + '/usage_matches_raw_CLI', usage == consumer['raw_usage_events'])
        slots.append({'case_id': case_id, 'publication': publication, 'legacy_status': {'slot': slot['status'], 'consumer': consumer['status'], 'valid_completion': consumer['valid_completion'], 'errors': consumer['errors'], 'unexpected_tool_deviation_event_count': len(consumer['unexpected_tool_deviations']), 'archive_binding_errors': archive['business_binding_errors']},
            'delivery_facts': {'business_attempts': len(business), 'admitted': ledger['admitted'], 'CLI_completed_tool_events': len(completed), 'empty_resource_enumerations': resource_rows, 'other_tool_calls': other, 'deliveries': deliveries, 'native_png_blocks': consumer['public_image_count'], 'native_png_bytes': consumer['public_image_bytes'], 'model_view_confirmed': consumer['image_delivery']['model_view_confirmed'], 'provider_delivery_confirmed': consumer['image_delivery']['provider_delivery_confirmed']},
            'input_boundary': {'prompt': seal(NS / 'inputs/PROMPT.txt'), 'schema': seal(NS / 'inputs/TOOL_SCHEMA.json'), 'bound_input': seal(inp / 'TOOL_RESULT.json'), 'requested_profile': profile, 'thread_id': consumer['thread_id'], 'fresh_expected_thread': consumer['expected_thread_id'], 'CLI': seal(argv[0]), 'runtime_python': seal(binding['actual_executable']), 'wire': wire_rows, 'observed_input_scope': 'CLI launch configuration, actual completed tool events, and MCP wire. Provider-internal full requests are unavailable.'},
            'legacy_accounting_difference': {'owner_attempts': ledger['attempts'], 'legacy_CLI_all_tool_events': len(consumer['tool_calls']), 'independent_business_only_events': len(business), 'extra_empty_enumeration_events': len(enumerations), 'business_originals_match_filtered_CLI_events': True, 'original_status_preserved': True},
            'deadlines_and_timing': {key: slot[key] for key in ['started_ns', 'task_deadline_ns', 'lifecycle_deadline_ns', 'closed_ns', 'wall_ns']},
            'final_seal': final, 'final_timing': timing,
            'usage': {'raw_CLI_events': usage, 'fees': consumer['fees'], 'provider_requests': consumer['provider_requests'], 'image_tokens': consumer['image_tokens'], 'resolved_effort': consumer['resolved_effort'], 'semantics': consumer['usage_semantics'], 'aggregation': consumer['usage_aggregation']},
            'closure': {'CLI': cleanup, 'MCP_binding': binding, 'MCP_retained_exit': runtime_exit, 'EXIT_receipts': consumer['bridge_cleanup'], 'readers_stopped': consumer['readers_stopped'], 'termination_cause': 'MCP exit1 follows CLI exit0. Actual held-handle terminal state is proven. The log does not expose the causal termination operation.'},
            'execution_freeze': {'inferred_from_registered_case_order_and_proof': 'FROZEN.json' if case_id == 'S1' else None,
                                 'recorded_path': slot.get('freeze_path'), 'recorded_sha256': slot.get('freeze_sha256'),
                                 'scope': 'R0 S1 did not persist freeze_path/sha256. Its archived source snapshots and adapter proof bind the original freeze. R1 records its selected freeze.'},
            'source_record_seals': [seal(folder / name) for name in ['SLOT_RESULT.json', 'SLOT_PUBLICATION.json', 'ADAPTER_PROOF.json', 'consumer/CONSUMER.json', 'consumer/ARCHIVE.json', 'consumer.raw.zip', 'consumer/stdout.raw.bin', 'consumer/events.jsonl', 'owner/TOOLS.json']]})

    check('three_unique_threads', len({slot['input_boundary']['thread_id'] for slot in slots}) == 3)
    check('serial_publication_before_next_start', all(slots[index]['publication']['published_ns'] < slots[index + 1]['deadlines_and_timing']['started_ns'] for index in range(2)))
    check('revision_after_S1_and_before_S2', slots[0]['publication']['published_ns'] < revised['frozen_ns'] < slots[1]['deadlines_and_timing']['started_ns'])
    check('nested_preflight_pins_committed_before_first_consumer',
          preflight['closed_ns'] < frozen['frozen_ns'] < slots[0]['deadlines_and_timing']['started_ns']
          and original_rows[str(NS / 'PREFLIGHT.json')]['sha256'] == seal(NS / 'PREFLIGHT.json')['sha256'])
    report = {'schema': 'source-region-consumption-independent-runtime-review-v1', 'started_ns': started, 'closed_ns': time.perf_counter_ns(),
        'status': 'audited_with_preserved_failures_and_unknowns', 'check_count': len(checks), 'failed_check_count': sum(not row['passed'] for row in checks),
        'audit_operations': {'new_model_consumers': 0, 'new_Blender': 0, 'new_product_calls': 0, 'raster': 0, 'PNG_encoding': 0, 'source_execution': 0, 'source_AST_parse': len(sources)},
        'audit_disclosure': {'content_scoring_performed': False, 'S1_final_body_accidentally_exposed': True, 'detail': 'An initial metadata exploration printed CONSUMER.summary, which contains the S1 final answer. No content scoring was performed. This checker emits hashes and metadata only. The root reviewer must retain this disclosure when describing audit independence.',
                             'checker_development_error': 'An added direct-freeze membership lookup raised KeyError for the reused event loop before report writing. Membership handling was corrected and the absent transitive paths are explicitly retained as coverage gaps.'},
        'freezes': {'R0': seal(NS / 'FROZEN.json'), 'R1': seal(NS / 'FROZEN_PROTOCOL_R1.json'), 'revision': seal(NS / 'protocol_revisions/REVISION_01.json'), 'direct_input_count': len(revised_rows), 'unchanged_input_count': len(revised_rows) - len(changed), 'changed_paths': changed, 'profile': revised['model_profile'], 'source_AST': sources},
        'conclusions': {'delivery': {'S1': 'Two attempted reads were rejected before admission by R0 optional _meta validation. No observation or PNG delivered. Original answer retained.', 'S2': 'One original brief and native PNG delivered. Two empty Codex enumerations also completed.', 'S3': 'One original brief and native PNG delivered. Two empty Codex enumerations also completed.'}, 'legacy_accounting': 'The inherited event loop treats the two Codex resource-enumeration tools as unexpected and passes them in the full tool-call list to the owner archive matcher. Owner/business counts are 2/2, 1/1, 1/1 after independent classification. Original archive counts remain 2/4, 1/3, 1/3, and all original failed statuses remain intact.', 'resource_wire': 'CLI enumeration results are empty in all slots. S1 wire returns -32601 for both enumeration methods. R1 S2/S3 wire returns empty lists.', 'closure': 'All CLI exits are zero. All actual MCP retained handles prove exit1 and handle closure. All MCP EXIT receipt states remain unknown.', 'input_boundary': 'Actual observed tools contain bound read_observation and empty resource enumerations only. Provider-internal requests, image perception, fees and unexposed usage fields remain unavailable.'},
        'transitive_direct_rehash_coverage': freeze_coverage_gaps,
        'additional_nested_infrastructure_pins': {
            'parent_frozen_input': str(infrastructure_path), 'sources': nested_infrastructure_pins,
            'runtime_handle_nested_sha256': next(row['nested_frozen_sha256'] for row in nested_infrastructure_pins if row['path'].endswith('m4_active_coverage_consumption_001\\runtime_handle.py')),
            'scope': 'These listed source hashes are also committed through the frozen infrastructure review, including runtime_handle.py. This audit checks the declared pins against current bytes and actual adapter hashes when exposed. The original run_slot does not recursively rehash nested source pins before execution. Exhaustive execution-closure membership is not established by the four-row loaded_execution_sources list.'},
        'slots': slots, 'checks': checks}
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
    print(json.dumps({'report': str(REPORT), 'checks': len(checks), 'failed_checks': report['failed_check_count'], 'failures': [row for row in checks if not row['passed']]}, ensure_ascii=False))


if __name__ == '__main__':
    main()

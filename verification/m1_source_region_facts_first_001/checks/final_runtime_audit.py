"""Independently audit sealed runtime bytes without exposing answer bodies."""

import ast
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time
import tomllib
import zipfile


NS = Path(__file__).resolve().parents[1]
RUNTIME = Path('D:/he_m1_source_region_facts_first_001')
REPORT = NS / 'checks/FINAL_RUNTIME_REVIEW.json'
USAGE_KEYS = ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens',
              'output_tokens', 'reasoning_output_tokens')
DISCOVERY = {
    'list_mcp_resources': ('resources/list', {'resources': []}),
    'list_mcp_resource_templates': ('resources/templates/list', {'resourceTemplates': []}),
}


def read(path):
    return json.loads(Path(path).read_bytes())


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def stream_digest(stream):
    result = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        result.update(chunk)
    return result.hexdigest()


def seal(path):
    path = Path(path)
    with path.open('rb') as stream:
        result = stream_digest(stream)
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': result}


def png_metadata(block):
    raw = base64.b64decode(block['data'], validate=True)
    header = len(raw) >= 24 and raw[:8] == b'\x89PNG\r\n\x1a\n' and raw[12:16] == b'IHDR'
    return {'bytes': len(raw), 'sha256': digest(raw), 'mimeType': block.get('mimeType'),
            'dimensions': list(struct.unpack('>II', raw[16:24])) if header else None,
            'header_valid': header}


def classify(item):
    if item.get('type') != 'mcp_tool_call':
        return 'unexpected'
    if (item.get('server'), item.get('tool')) == ('arm_engine', 'read_observation'):
        return 'business'
    if item.get('server') != 'codex' or item.get('tool') not in DISCOVERY:
        return 'unexpected'
    result = item.get('result')
    if (item.get('arguments') not in ({}, {'server': 'arm_engine'})
            or item.get('status') != 'completed' or item.get('error') is not None
            or type(result) is not dict or set(result) != {'content', 'structured_content'}
            or result['structured_content'] is not None):
        return 'unexpected'
    content = result['content']
    if (type(content) is not list or len(content) != 1 or type(content[0]) is not dict
            or set(content[0]) != {'type', 'text'} or content[0]['type'] != 'text'):
        return 'unexpected'
    try:
        parsed = json.loads(content[0]['text'])
    except (TypeError, ValueError):
        return 'unexpected'
    return 'empty_discovery' if parsed == DISCOVERY[item['tool']][1] else 'unexpected'


def selected_events(path):
    """Discard reasoning bodies and retain only the authorized event metadata."""
    result = {'threads': [], 'usage': [], 'tools': [], 'started_tools': [],
              'public_item_types': Counter(), 'message_hashes': [], 'error_events': 0,
              'reasoning_or_analysis_event_count': 0, 'message_UTF8_bytes': 0, 'lines': 0}
    with Path(path).open('rb') as stream:
        for raw in stream:
            result['lines'] += 1
            event = json.loads(raw)
            kind = event.get('type')
            item = event.get('item', {})
            item_type = item.get('type')
            if item_type in ('reasoning', 'analysis'):
                result['reasoning_or_analysis_event_count'] += 1
                continue
            if kind == 'thread.started':
                result['threads'].append(event.get('thread_id'))
            if kind == 'turn.completed':
                result['usage'].append(event.get('usage'))
            if kind in ('error', 'turn.failed'):
                result['error_events'] += 1
            if kind in ('item.started', 'item.completed'):
                result['public_item_types'][item_type] += 1
                if item_type == 'mcp_tool_call':
                    result['tools' if kind == 'item.completed' else 'started_tools'].append(item)
                if kind == 'item.completed' and item_type == 'agent_message':
                    message = item.get('text', '').encode('utf8')
                    result['message_hashes'].append(digest(message))
                    result['message_UTF8_bytes'] += len(message)
    return result


def phase_rows():
    specifications = [
        ('preparation', 'PREPARATION_CLOSED.json', 'started_ns', 'closed_ns'),
        ('build_A', 'build_A/BUILD_INSTALL.json', 'started_ns', 'closed_ns'),
        ('build_B', 'build_B/BUILD_INSTALL.json', 'started_ns', 'closed_ns'),
        ('regressions_source', 'tests/REGRESSIONS_source.json', 'started_ns', 'closed_ns'),
        ('regressions_installed', 'tests/REGRESSIONS_installed.json', 'started_ns', 'closed_ns'),
        ('protocol_preflight', 'checks/BRIDGE_PREFLIGHT.json', 'started_ns', 'closed_ns'),
        ('client_budget_replay', 'checks/CLIENT_BUDGET_REVIEW.json', 'started_ns', 'completed_ns'),
        ('paired_benchmark', 'BENCHMARK_RESULT.json', 'started_ns', 'closed_before_worker_cleanup_ns'),
        ('paired_benchmark_publication', 'BENCHMARK_PUBLICATION.json', 'started_ns', 'closed_ns'),
    ]
    rows = []
    for name, relative, start_key, end_key in specifications:
        path = NS / relative
        value = read(path)
        start, end = value[start_key], value[end_key]
        rows.append({'phase': name, 'source': seal(path), 'started_ns': start, 'closed_ns': end,
                     'wall_seconds': (end - start) / 1e9})
    return rows


def main():
    began = time.perf_counter_ns()
    if not (NS / 'ANSWERS_SEALED.json').is_file():
        raise RuntimeError('three_original_answers_must_be_sealed_before_audit')
    checks = []

    def check(name, condition, details=None):
        checks.append({'name': name, 'passed': bool(condition), 'details': details})

    frozen_path = NS / 'FROZEN.json'
    frozen = read(frozen_path)
    inputs = read(NS / 'INPUTS.json')
    sealed = read(NS / 'ANSWERS_SEALED.json')
    direct = {str(Path(row['path']).resolve()): row for row in frozen['direct_inputs']}
    execution = {str(Path(row['path']).resolve()): row for row in frozen['execution_sources']}
    for group, rows in [('direct_input', direct), ('execution_source', execution)]:
        for path, row in rows.items():
            actual = seal(path)
            check(group + '/' + path, actual['sha256'] == row['sha256']
                  and ('bytes' not in row or actual['bytes'] == row['bytes']))
    check('fourteen_execution_sources', len(execution) == frozen['execution_source_count'] == 14)
    check('three_hundred_sixty_three_direct_pins', len(direct) == 363)
    check('execution_sources_are_directly_frozen', set(execution) <= set(direct))
    check('registered_three_original_consumers', frozen['case_order'] == ['S1', 'S2', 'S3']
          and frozen['consumer_cap'] == 3 and frozen['replacement_consumers'] == 0)
    check('registered_limits', frozen['completed_CLI_tool_cap'] == 4
          and frozen['task_seconds'] == 450 and frozen['process_seconds'] == 600)
    event_loop_tree = ast.parse((NS / 'harness/consumer_loop.py').read_text(encoding='utf8'))
    launch_calls = [node for node in ast.walk(event_loop_tree)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == 'subprocess'
                    and node.func.attr == 'Popen']
    check('event_loop_has_one_process_launch_site', len(launch_calls) == 1)
    check('exact_three_slot_directories', sorted(p.name for p in (RUNTIME / 'slots').iterdir()) == ['S1', 'S2', 'S3'])
    check('sealed_exact_three_original_answers', [row['case_id'] for row in sealed['answers']] == ['S1', 'S2', 'S3']
          and sealed['real_consumers'] == 3 and sealed['replacement_consumers'] == 0
          and sealed['scoring_started_before_all_answers_sealed'] is False)
    slots = []
    totals = {key: 0 for key in USAGE_KEYS}
    schema = read(NS / 'inputs/TOOL_SCHEMA.json')
    sealed_by_case = {row['case_id']: row for row in sealed['answers']}
    for case in inputs['cases']:
        case_id = case['case_id']
        folder = RUNTIME / 'slots' / case_id
        consumer_dir = folder / 'consumer'
        started = read(folder / 'SLOT_STARTED.json')
        slot = read(folder / 'SLOT_RESULT.json')
        publication = read(folder / 'SLOT_PUBLICATION.json')
        consumer = read(consumer_dir / 'CONSUMER.json')
        timing = read(consumer_dir / 'FINAL_TIMING.json')
        cell = read(consumer_dir / 'cell.json')
        ledger = read(folder / 'owner/TOOLS.json')
        bridge = read(folder / 'owner/BRIDGE_RESULT.json')
        proof = read(folder / 'ADAPTER_PROOF.json')
        archive = read(consumer_dir / 'ARCHIVE.json')
        binding = read(consumer_dir / 'RUNTIME_BINDING.json')
        source_binding = read(consumer_dir / 'BUSINESS_SOURCE_BINDING.json')
        events = selected_events(consumer_dir / 'stdout.raw.bin')
        payload = read(case['input_file'])
        brief_raw = (NS / 'inputs' / case_id / 'ORIGINAL_BRIEF.json').read_bytes()
        png_raw = (NS / 'inputs' / case_id / 'ORIGINAL_IMAGE.png').read_bytes()
        expected_png = png_metadata(payload['content'][1])
        prefix = case_id + '/'
        check(prefix + 'publication_result_hash', publication['result_sha256'] == seal(folder / 'SLOT_RESULT.json')['sha256'])
        check(prefix + 'consumer_hash', slot['consumer_record_sha256'] == seal(consumer_dir / 'CONSUMER.json')['sha256'])
        check(prefix + 'original_frozen_input', Path(case['input_file']).resolve() == Path(cell['input_file']).resolve()
              and seal(case['input_file'])['sha256'] == case['input_sha256'] == cell['input_sha256'] == bridge['input_sha256'])
        check(prefix + 'original_brief_bytes', payload['content'][0]['text'].encode('utf8') == brief_raw
              and len(brief_raw) == case['brief_UTF8_bytes'])
        check(prefix + 'original_PNG_bytes', expected_png['header_valid'] and expected_png['mimeType'] == 'image/png'
              and expected_png['sha256'] == digest(png_raw) == case['PNG_sha256'])
        historical_png = NS / 'historical' / case_id / 'ORIGINAL_IMAGE.png'
        check(prefix + 'historical_original_PNG', seal(historical_png)['sha256'] == expected_png['sha256'])
        check(prefix + 'common_prompt', consumer['input_sha256'] == inputs['prompt_sha256']
              == seal(NS / 'inputs/PROMPT.txt')['sha256']
              and consumer['input_text_bytes'] == (NS / 'inputs/PROMPT.txt').stat().st_size)
        check(prefix + 'freeze_identity', Path(slot['freeze_path']).resolve() == frozen_path.resolve()
              and slot['freeze_sha256'] == seal(frozen_path)['sha256']
              and frozen['frozen_ns'] < started['started_ns'])
        proof_sources = {str(Path(row['path']).resolve()): row for row in proof['execution_sources']}
        check(prefix + 'execution_source_set', proof_sources == execution)
        for field in ('adapter', 'accepted_consumer', 'event_loop', 'original_event_loop',
                      'archive_contract', 'result_matcher', 'settings', 'server'):
            path = str(Path(proof[field + '_path']).resolve())
            check(prefix + 'execution_proof/' + field, path in execution
                  and proof[field + '_sha256'] == execution[path]['sha256'])
        argv = consumer['argv']
        config = {}
        for index, value in enumerate(argv[:-1]):
            if value == '-c':
                config.update(tomllib.loads(argv[index + 1]))
        profile = {'model': config.get('model'), 'reasoning_effort': config.get('model_reasoning_effort'),
                   'service_tier': config.get('service_tier')}
        check(prefix + 'requested_model_profile', profile == frozen['model_profile'])
        check(prefix + 'fresh_ephemeral', argv[1] == 'exec' and '--ephemeral' in argv
              and all(token not in argv for token in ('resume', 'fork', '--last', '--all'))
              and consumer['expected_thread_id'] is None and consumer['execution_kind'] == 'provider'
              and consumer['turn_index'] == 1)
        check(prefix + 'single_authorized_model_launch', consumer['frozen_cli_argv'] == argv
              and proof['model_calls_during_adapter_construction'] == 0
              and proof['fresh_ephemeral_argv_adapter'] and proof['resume_entry_available'] is False)
        check(prefix + 'one_thread_started', events['threads'] == [consumer['thread_id']] and bool(consumer['thread_id']))
        check(prefix + 'fixed_CLI_and_Python', seal(argv[0])['sha256'] == proof['CLI_sha256']
              and seal(binding['actual_executable'])['sha256'] == proof['Python_sha256'] == binding['actual_executable_sha256'])
        server = config['mcp_servers']['arm_engine']
        check(prefix + 'single_bound_server', set(config['mcp_servers']) == {'arm_engine'}
              and server['tools'] == {'read_observation': {'approval_mode': 'approve'}}
              and server['args'][server['args'].index('--input') + 1] == cell['input_file']
              and server['args'][server['args'].index('--input-sha256') + 1] == case['input_sha256'])
        check(prefix + 'original_deadlines', slot['task_deadline_ns'] - slot['started_ns'] == 450_000_000_000
              and slot['lifecycle_deadline_ns'] - slot['started_ns'] == 600_000_000_000
              and started['task_deadline_ns'] == slot['task_deadline_ns']
              and started['lifecycle_deadline_ns'] == slot['lifecycle_deadline_ns'])
        check(prefix + 'deadlines_never_reset', cell['task_deadline_ns'] == consumer['deadline_ns']
              == publication['original_task_deadline_ns'] == timing['original_turn_deadline_ns'] == slot['task_deadline_ns']
              and publication['original_lifecycle_deadline_ns'] == slot['lifecycle_deadline_ns']
              and read(folder / 'ENDPOINT.json')['chain_deadline_ns'] == slot['lifecycle_deadline_ns'])
        check(prefix + 'task_and_lifecycle_close', slot['started_ns'] <= consumer['started_ns']
              <= consumer['final_received_ns'] <= consumer['turn_completed_ns']
              <= timing['consumer_record_closed_ns'] < slot['task_deadline_ns']
              and slot['closed_ns'] < publication['published_ns'] < slot['lifecycle_deadline_ns']
              and not consumer['deadline_timer_fired'] and timing['accepted_success'])
        check(prefix + 'slot_publication_within_450_seconds', publication['published_ns'] < slot['task_deadline_ns'])
        completed = events['tools']
        business = [item for item in completed if classify(item) == 'business']
        discovery = [item for item in completed if classify(item) == 'empty_discovery']
        unexpected = [item for item in completed if classify(item) == 'unexpected']
        check(prefix + 'all_completed_calls_within_four', len(completed) == len(consumer['tool_calls'])
              == slot['completed_tool_calls'] <= 4 and ledger['attempts'] <= 4 and ledger['admitted'] <= 4)
        check(prefix + 'business_count_matches_owner', len(business) == ledger['attempts'] == slot['business_attempts']
              and ledger['admitted'] == slot['business_admitted'])
        check(prefix + 'tool_accounting', consumer['tool_accounting']['completed_CLI_tool_calls'] == len(completed)
              and consumer['tool_accounting']['completed_business_calls'] == len(business)
              and consumer['tool_accounting']['completed_empty_discoveries'] == len(discovery)
              and not consumer['tool_accounting']['incomplete_control_item_ids']
              and not unexpected and not consumer['unexpected_tool_deviations'])
        check(prefix + 'all_started_tools_completed', {item['id'] for item in events['started_tools']} == {item['id'] for item in completed})
        check(prefix + 'no_other_data_tools', not set(events['public_item_types']) - {'mcp_tool_call', 'agent_message', 'warning', 'error'})
        wire = []
        wire_bytes = {'TX': 0, 'RX': 0}
        for tx_path in sorted((consumer_dir / 'attachments').glob('bridge_*/*/TX.bin')):
            request = read(tx_path)
            rx_path = tx_path.with_name('RX.bin')
            response = read(rx_path) if rx_path.exists() else None
            wire_bytes['TX'] += tx_path.stat().st_size
            wire_bytes['RX'] += rx_path.stat().st_size if rx_path.exists() else 0
            wire.append((request, response))
            if request.get('method') == 'tools/list':
                check(prefix + 'exact_tool_schema', response['result']['tools'] == [schema])
            check(prefix + 'wire_method/' + tx_path.parent.name, request.get('method') in {
                'initialize', 'notifications/initialized', 'tools/list', 'tools/call',
                'resources/list', 'resources/templates/list', 'ping'})
        business_wire = [pair for pair in wire if pair[0].get('method') == 'tools/call']
        check(prefix + 'wire_business_count', len(business_wire) == len(business))
        check(prefix + 'wire_byte_accounting', wire_bytes['TX'] == consumer['MCP_stdio_TX_bytes']
              and wire_bytes['RX'] == consumer['MCP_stdio_RX_bytes'])
        deliveries = []
        for item, owner, wire_pair in zip(business, ledger['tools'], business_wire):
            owner_dir = folder / 'owner' / ('tool_' + str(owner['attempt']).zfill(2))
            request = read(owner_dir / 'REQUEST.json')
            response = read(owner_dir / 'RESPONSE.json')
            check(prefix + 'business_RPC/' + str(owner['attempt']), (request, response) == wire_pair
                  and type(request['id']) is type(response['id']) and request['id'] == response['id']
                  and request['params']['name'] == item['tool'] == 'read_observation'
                  and request['params']['arguments'] == item['arguments'] == {})
            check(prefix + 'delivered_original_content/' + str(owner['attempt']), response['result'] == payload
                  and response['result']['content'] == item['result']['content']
                  and item['status'] == 'completed' and item['error'] is None)
            actual_brief = item['result']['content'][0]['text'].encode('utf8')
            actual_png = png_metadata(item['result']['content'][1])
            check(prefix + 'CLI_native_bytes/' + str(owner['attempt']), actual_brief == brief_raw and actual_png == expected_png)
            deliveries.append({'attempt': owner['attempt'], 'brief_UTF8_bytes': len(actual_brief),
                               'brief_sha256': digest(actual_brief), 'PNG': actual_png,
                               'CLI_item_id': item['id'], 'RPC_id': request['id']})
        for tool, (method, expected) in DISCOVERY.items():
            cli_rows = [item for item in discovery if item['tool'] == tool]
            rpc_rows = [pair for pair in wire if pair[0].get('method') == method]
            check(prefix + 'empty_discovery_RPC/' + tool, len(cli_rows) == len(rpc_rows) and all(
                type(req['id']) is type(res.get('id')) and req['id'] == res['id'] and res.get('result') == expected
                for req, res in rpc_rows))
        check(prefix + 'exact_archive_binding', not source_binding['binding_errors']
              and not archive['business_binding_errors']
              and all(row['matched'] for row in source_binding['result_contracts'])
              and all(row['matched'] for row in source_binding['discovery_bindings']))
        zip_path = folder / 'consumer.raw.zip'
        check(prefix + 'archive_hash', seal(zip_path)['sha256'] == archive['archive_sha256'])
        with zipfile.ZipFile(zip_path) as zipped:
            check(prefix + 'archive_membership', set(zipped.namelist()) == set(archive['source_files_sha256'])
                  and len(zipped.namelist()) == archive['original_file_count'])
            for relative, expected in archive['source_files_sha256'].items():
                with zipped.open(relative) as stream:
                    actual_digest = stream_digest(stream)
                check(prefix + 'archive_bytes/' + relative, actual_digest == expected == seal(consumer_dir / relative)['sha256'])
        final_identity = seal(consumer_dir / 'PUBLIC_FINAL.txt')
        answer = sealed_by_case[case_id]
        check(prefix + 'original_answer_seal', final_identity['sha256'] == slot['answer']['sha256'] == answer['sha256']
              == seal(answer['copy_path'])['sha256']
              and final_identity['bytes'] == slot['answer']['bytes']
              and Path(answer['original_path']).resolve() == (consumer_dir / 'PUBLIC_FINAL.txt').resolve()
              and events['message_hashes'][-1] == final_identity['sha256'])
        check(prefix + 'public_text_and_stdout_bytes', events['message_UTF8_bytes'] == consumer['public_text_bytes']
              and final_identity['bytes'] == consumer['output_text_bytes']
              and seal(consumer_dir / 'stdout.raw.bin')['bytes'] == consumer['stdout_raw_bytes'] == consumer['stdout_bytes']
              and seal(consumer_dir / 'stdout.raw.bin')['sha256'] == consumer['stdout_raw_sha256'])
        cleanup = consumer['process_cleanup']
        runtime_exit = consumer['runtime_exit']
        startup_receipts = sorted((consumer_dir / 'attachments').glob('bridge_*/STARTED.json'))
        exit_receipts = sorted((consumer_dir / 'attachments').glob('bridge_*/EXIT.json'))
        check(prefix + 'one_original_MCP_start', len(startup_receipts) == 1
              and read(startup_receipts[0]) == binding['stdio_STARTED'])
        check(prefix + 'missing_normal_EXIT_remains_unknown', len(exit_receipts) == 0
              and consumer['bridge_cleanup']['missing_exit_count'] == 1
              and consumer['bridge_cleanup']['confirmed'] is None
              and consumer['bridge_cleanup']['receipt_status'] == 'unknown')
        check(prefix + 'CLI_cleanup', consumer['process_reaped'] and cleanup['confirmed'] and cleanup['reaped']
              and cleanup['process_handle_closed'] and all(cleanup['pipes_closed'].values())
              and consumer['readers_stopped'] and consumer['exit_code'] == 0)
        check(prefix + 'actual_MCP_identity', binding['confirmed']
              and binding['runtime_pid'] == binding['stdio_STARTED']['pid']
              and binding['launcher_pid'] == consumer['consumer_pid']
              and binding['runtime_created_filetime'] >= binding['launcher_created_filetime'])
        check(prefix + 'retained_MCP_exit', runtime_exit['confirmed'] and runtime_exit['exited']
              and runtime_exit['handle_closed'] and runtime_exit['closed_ns'] < slot['task_deadline_ns'])
        check(prefix + 'safe_complete', consumer['valid_completion'] and consumer['safe_to_continue']
              and slot['valid_completion'] and slot['status'] == consumer['status'] == publication['status'] == 'completed'
              and not slot['errors'] and not consumer['errors'] and not events['error_events'])
        usage = events['usage']
        check(prefix + 'original_usage', len(usage) == 1 and usage == consumer['raw_usage_events'] == slot['original_usage']
              and all(type(value) is int and value >= 0 for row in usage for value in row.values()))
        for row in usage:
            for key in totals:
                totals[key] += row.get(key, 0)
        check(prefix + 'no_new_graphics_work', all(bridge[key] == 0 for key in ('new_Blender', 'new_product_calls', 'raster', 'image_encoding')))
        check(prefix + 'image_accounting', len(deliveries) == consumer['public_image_count'] == slot['native_image_deliveries']
              and sum(row['PNG']['bytes'] for row in deliveries) == consumer['public_image_bytes']
              and consumer['unknown_image_payloads'] == 0 and consumer['input_image_count'] == 0)
        check(prefix + 'individual_image_telemetry', len(consumer['image_deliveries']) == len(deliveries)
              and all(observed['payload_valid'] and observed['PNG_sha256'] == actual['PNG']['sha256']
                      and observed['PNG_bytes'] == actual['PNG']['bytes']
                      and [observed['width'], observed['height']] == actual['PNG']['dimensions']
                      for observed, actual in zip(consumer['image_deliveries'], deliveries)))
        slots.append({'case_id': case_id, 'status': slot['status'], 'valid_completion': consumer['valid_completion'],
                      'business_attempts': ledger['attempts'], 'business_admitted': ledger['admitted'],
                      'completed_CLI_tool_calls': len(completed), 'empty_discovery_calls': len(discovery),
                      'thread_id': consumer['thread_id'], 'deliveries': deliveries,
                      'native_image_deliveries': consumer['public_image_count'], 'native_image_bytes': consumer['public_image_bytes'],
                      'delivered_brief_UTF8_bytes': sum(row['brief_UTF8_bytes'] for row in deliveries),
                      'MCP_wire_bytes': wire_bytes, 'CLI_stdout_raw_bytes': consumer['stdout_raw_bytes'],
                      'CLI_stderr_raw_bytes': (consumer_dir / 'stderr.raw.bin').stat().st_size,
                      'public_text_UTF8_bytes': consumer['public_text_bytes'],
                      'final_text_UTF8_bytes': consumer['output_text_bytes'],
                      'full_slot_seconds': slot['wall_ns'] / 1e9,
                      'slot_through_publication_seconds': (publication['published_ns'] - slot['started_ns']) / 1e9,
                      'consumer_seconds': timing['full_turn_wall_ns'] / 1e9,
                      'prompt_to_final_seconds': consumer['prompt_to_final_ns'] / 1e9,
                      'started_ns': slot['started_ns'], 'published_ns': publication['published_ns'],
                      'timing': {'task_deadline_ns': slot['task_deadline_ns'],
                                 'lifecycle_deadline_ns': slot['lifecycle_deadline_ns'],
                                 'consumer_record_closed_ns': timing['consumer_record_closed_ns'],
                                 'cleanup_and_archive_closed_ns': consumer['cleanup_end_ns'],
                                 'slot_result_closed_ns': slot['closed_ns'],
                                 'slot_published_ns': publication['published_ns']},
                      'answer': final_identity, 'original_usage': usage,
                      'usage_unknowns': {key: consumer.get(key) for key in ('fees', 'provider_requests', 'image_tokens', 'resolved_effort', 'usage_semantics')},
                      'provider_retry_observation_count': len(consumer['provider_retry_observations']),
                      'process_cleanup': cleanup, 'MCP_retained_exit': runtime_exit,
                      'normal_EXIT_receipts': consumer['bridge_cleanup'],
                      'source_execution_proof_sha256': seal(folder / 'ADAPTER_PROOF.json')['sha256'],
                      'reasoning_or_analysis_event_count': events['reasoning_or_analysis_event_count']})
    check('three_unique_threads', len({row['thread_id'] for row in slots}) == 3)
    check('serial_publications', all(slots[index]['published_ns'] < slots[index + 1]['started_ns'] for index in range(2)))
    check('freeze_before_all_consumers', frozen['frozen_ns'] < slots[0]['started_ns'])
    check('all_answers_sealed_after_consumers', slots[-1]['published_ns'] < sealed['started_ns'] <= sealed['sealed_ns'])
    process_command = (
        "$p=Get-CimInstance Win32_Process | Where-Object { "
        "$_.Name -in @('codex.exe','python.exe','pythonw.exe') -and "
        "$_.CommandLine -and $_.CommandLine.Contains('D:\\he_m1_source_region_facts_first_001\\slots') }; "
        "@($p | Select-Object ProcessId,ParentProcessId,Name) | ConvertTo-Json -Compress"
    )
    current = subprocess.run(['powershell', '-NoProfile', '-Command', process_command],
                             capture_output=True, check=True, text=True)
    live = json.loads(current.stdout) if current.stdout.strip() else []
    check('no_matching_consumer_or_MCP_processes_remain', live == [], live)
    phases = phase_rows()
    check('phase_clocks_valid', all(row['closed_ns'] >= row['started_ns'] for row in phases))
    preparation = read(NS / 'PREPARATION_CLOSED.json')
    check('preparation_closed_before_consumption', preparation['closed_ns'] < slots[0]['started_ns']
          and preparation['freeze_sha256'] == seal(frozen_path)['sha256'])
    benchmark = read(NS / 'BENCHMARK_RESULT.json')
    timed_calls = [row for row in benchmark['calls'] if row['operation'] == 'timed']
    preflight = read(NS / 'checks/BRIDGE_PREFLIGHT.json')
    client_budget = read(NS / 'checks/CLIENT_BUDGET_REVIEW.json')
    regression_source = read(NS / 'tests/REGRESSIONS_source.json')
    regression_installed = read(NS / 'tests/REGRESSIONS_installed.json')
    check('preparation_reports_zero_extra_models', benchmark['models'] == 0
          and preflight['zero_work']['CLI_inference'] == preflight['zero_work']['real_model_consumers'] == 0
          and client_budget['operations']['model_calls'] == 0
          and read(NS / 'CLI_PREFLIGHT.json')['model_calls'] == 0)
    check('preparation_reports_zero_graphics_work', benchmark['new_PNG_NPZ_encodes'] == benchmark['raster'] == 0
          and all(value == 0 for value in preflight['zero_work'].values())
          and all(value == 0 for result in (regression_source, regression_installed)
                  for value in result['guarded_operations'].values()))
    cost_operations = {
        'paired_benchmark': {
            'RPC_records': len(benchmark['calls']),
            'formatter_iterations': sum(row['iterations'] for row in benchmark['calls']),
            'timed_RPC_records': len(timed_calls),
            'timed_formatter_iterations': sum(row['iterations'] for row in timed_calls),
            'timed_formatter_interval_seconds': sum(row['elapsed_ns'] for row in timed_calls) / 1e9,
            'all_formatter_interval_seconds': sum(row['elapsed_ns'] for row in benchmark['calls']) / 1e9,
            'instrumentation_scope': benchmark['instrumentation_scope'],
            'timing_scope': benchmark['timing_scope'],
            'model_consumers': benchmark['models'], 'raster': benchmark['raster'],
            'PNG_NPZ_encodes': benchmark['new_PNG_NPZ_encodes']},
        'protocol_preflight': {'local_protocol_processes': len(preflight['protocol_processes']),
                               'zero_work': preflight['zero_work'],
                               'expired_deadline_control_expected_exit_code': 1},
        'client_budget_replay': {'check_count': client_budget['check_count'],
                                 'operations': client_budget['operations']},
        'regressions': {'source_tests': regression_source['tests'],
                        'installed_tests': regression_installed['tests'],
                        'source_guarded_operations': regression_source['guarded_operations'],
                        'installed_guarded_operations': regression_installed['guarded_operations']}}
    missing_exit_cases = [row['case_id'] for row in slots if row['normal_EXIT_receipts']['missing_exit_count']]
    closed = time.perf_counter_ns()
    value = {'schema': 'facts-first-independent-runtime-review-v1', 'started_ns': began, 'closed_ns': closed,
             'status': 'passed' if all(row['passed'] for row in checks) else 'failed',
             'check_count': len(checks), 'failed_check_count': sum(not row['passed'] for row in checks),
             'checks': checks, 'slots': slots,
             'totals': {'original_consumers': len(slots), 'replacement_consumers': 0,
                        'business_attempts': sum(row['business_attempts'] for row in slots),
                        'completed_CLI_tool_calls': sum(row['completed_CLI_tool_calls'] for row in slots),
                        'empty_discovery_calls': sum(row['empty_discovery_calls'] for row in slots),
                        'native_image_deliveries': sum(row['native_image_deliveries'] for row in slots),
                        'native_image_bytes': sum(row['native_image_bytes'] for row in slots),
                        'delivered_brief_UTF8_bytes': sum(row['delivered_brief_UTF8_bytes'] for row in slots),
                        'original_turn_completed_usage_sums': totals,
                        'full_slot_seconds_sum': sum(row['full_slot_seconds'] for row in slots),
                        'full_consumer_seconds_sum': sum(row['consumer_seconds'] for row in slots)},
             'cost_phases': phases,
             'cost_operations': cost_operations,
             'cost_scope': {'nested_preparation_phases_are_additive': False,
                            'preparation_scope': preparation['scope'],
                            'usage_scope': 'Three original independent CLI turn.completed rows. Reasoning output stays a separate reported field.',
                            'fees': None, 'provider_request_count': None, 'image_token_breakdown': None,
                            'provider_internal_input': 'unobserved',
                            'manual_planning_before_preparation_start': 'unmeasured',
                            'audit_wall_seconds': (closed - began) / 1e9},
             'unknowns': {'normal_EXIT_receipt_missing_cases': missing_exit_cases,
                          'normal_EXIT_receipts': 'unknown' if missing_exit_cases else 'observed',
                          'MCP_exit1_cause': 'unobserved',
                          'provider_internal_request_count': 'unobserved',
                          'provider_internal_input_and_visual_consumption': 'unobserved',
                          'fees': 'unobserved', 'image_token_breakdown': 'unobserved',
                          'resolved_effort': 'unobserved',
                          'manual_authoring_wall_time': 'unmeasured'},
             'limitations': ['Three sealed historical-observation consumers only.',
                             'Reviewer scope covers runtime metadata, cost accounting and identity checks.',
                             'Extra-model checks cover registered launch structure, retained CLI events and preparation records. Provider-internal attempts remain unexposed.',
                             'Current process enumeration supplements original retained-handle evidence. Unlogged historical processes remain unobserved.',
                             'Preparation child phases overlap the recorded total preparation window.'],
             'audit_operations': {'new_model_consumers': 0, 'new_Blender': 0, 'new_product_calls': 0,
                                  'solve': 0, 'raster': 0, 'PNG_NPZ_encoding': 0,
                                  'harness_or_product_imports': 0, 'binary_hashing': True},
             'audit_boundary': {'content_scoring_performed': False, 'answer_bodies_output': False,
                                'consumer_summary_output': False, 'reasoning_or_analysis_bodies_output': False,
                                'answer_files_stream_hashed_only': True,
                                'raw_events_scope': 'JSON parsed to select tool, thread and usage events. Agent messages retained only as UTF-8 hashes. Reasoning and analysis bodies discarded without inspection.'}}
    with REPORT.open('w', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': value['status'], 'check_count': len(checks),
                      'failed_check_count': value['failed_check_count'], 'report': str(REPORT),
                      'failed_checks': [row['name'] for row in checks if not row['passed']]}))


if __name__ == '__main__':
    main()

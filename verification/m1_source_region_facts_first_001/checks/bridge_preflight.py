"""Replay original RPC frames and public tool events with zero model calls."""

import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


NS = Path(__file__).resolve().parent.parent
ROOT = NS.parents[1]
OLD = ROOT / 'verification/m4_source_region_consumption_001'
RUNTIME = Path('D:/he_m1_source_region_facts_first_001')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(Path(path).read_bytes())


def seal(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n', encoding='utf8', newline='\n')


def main(inputs_path, output_root):
    began = time.perf_counter_ns()
    folder = Path(output_root) / ('bridge_preflight_' + str(began))
    folder.mkdir(parents=True, exist_ok=False)
    checks, process_records, replay_sources = [], [], []
    adapter = load('_facts_first_preflight_adapter', NS / 'harness/consumer_adapter.py')
    consume_turn, proof = adapter.consumer_adapter()
    contract = consume_turn.__globals__['bridge_contract']
    transport = load('_facts_first_preflight_transport', NS / 'harness/reused/stdio_checks.py')
    reader = load('_facts_first_preflight_reader', NS / 'harness/read_observation.py')
    cases = read(inputs_path)
    assert cases['consumer_group'] == 'F'
    schema = NS / 'inputs/TOOL_SCHEMA.json'
    assert reader.TOOL == read(schema)
    assert schema.read_bytes() == (OLD / 'inputs/TOOL_SCHEMA.json').read_bytes()
    assert (NS / 'inputs/PROMPT.txt').read_bytes() == (OLD / 'inputs/PROMPT.txt').read_bytes()
    assert adapter.sha(adapter.BASE) == adapter.BASE_SHA256 and adapter.sha(adapter.CLI) == adapter.CLI_SHA256
    checks.append({'name': 'fixed_schema_prompt_CLI_Python_and_group', 'passed': True})
    manifest_path = OLD / 'RUNTIME_ARCHIVE.json'
    manifest = read(manifest_path)
    replay_sources.append(seal(manifest_path))

    def original_case(case_id):
        prefix = 'slots/' + case_id + '/consumer/'
        requests, events = [], None
        for row in manifest['files']:
            if not row['relative'].startswith(prefix):
                continue
            path = OLD / row['copy']
            if '/attachments/' in row['relative'] and row['relative'].endswith('/TX.bin'):
                assert row['byte_exact'] and seal(path)['sha256'] == row['original_sha256']
                raw = path.read_bytes()
                requests.append((row['relative'], raw, json.loads(raw)))
                replay_sources.append(seal(path))
            elif row['relative'] == prefix + 'events.jsonl':
                events = [json.loads(line) for line in path.read_bytes().splitlines() if line]
                replay_sources.append(seal(path))
        assert requests and events
        return sorted(requests), events

    s1_requests, s1_events = original_case('S1')
    s2_requests, s2_events = original_case('S2')
    _, s3_events = original_case('S3')

    def run_window(name, case, messages, *, expired=False):
        target = folder / name
        target.mkdir()
        deadline = time.perf_counter_ns() + 30_000_000_000
        server_deadline = time.perf_counter_ns() - 1 if expired else deadline
        client = transport.StdioClient([str(adapter.BASE), '-I', '-B', '-X', 'utf8', str(adapter.SERVER),
            '--input', case['input_file'], '--input-sha256', case['input_sha256'],
            '--owner', str(target / 'owner'), '--audit', str(target / 'attachments'),
            '--deadline-ns', str(server_deadline)], target, target / 'stdio', deadline)
        responses, error = [], None
        try:
            for source, raw, request in messages:
                responses.append({'source': source, 'request': request,
                                  'response': client.call(request, raw_request=raw)})
        except BaseException as exc:
            error = {'type': type(exc).__name__, 'message': str(exc)}
        finally:
            closed = client.finish()
        receipts = []
        for start in sorted((target / 'attachments').glob('bridge_*/STARTED.json')):
            started = read(start)
            exit_path = start.with_name('EXIT.json')
            ended = read(exit_path) if exit_path.exists() else None
            matched = None if ended is None else bool(
                started['pid'] == ended['pid'] and started['instance_nonce'] == ended['instance_nonce']
                and started['started_ns'] == ended['started_ns'] and ended['ended_ns'] >= started['started_ns'])
            receipts.append({'STARTED': started, 'EXIT': ended, 'identity_matched': matched,
                             'receipt_status': 'unknown' if ended is None else 'observed'})
        row = {'window': name, 'path': str(target), 'original_transport_deadline_ns': deadline,
               'original_server_deadline_ns': server_deadline, 'responses': responses,
               'error': error, 'closure': closed, 'exit_receipts': receipts}
        save(target / 'REPLAY.json', row)
        process_records.append({'window': name, 'path': str(target), 'closure': closed,
                                'server_deadline_ns': server_deadline, 'error': error,
                                'exit_receipts': receipts, 'response_count': len(responses)})
        if expired:
            assert error and closed['exit_code'] == 1 and closed['process_handle_closed']
            assert closed['reader_stopped'] and all(closed['pipes_closed'].values())
            assert len(receipts) == 1 and receipts[0]['identity_matched']
            assert receipts[0]['EXIT']['normal_exit'] is False
            assert read(target / 'owner/BRIDGE_RESULT.json')['attempts'] == 0
        else:
            assert error is None and closed['confirmed']
            assert len(receipts) == 1 and receipts[0]['identity_matched']
            assert receipts[0]['EXIT']['normal_exit'] is True
            assert closed['closed_ns'] < server_deadline
        return target, responses

    new_case = cases['cases'][0]
    assert new_case['case_id'] == 'S1' and adapter.sha(new_case['input_file']) == new_case['input_sha256']
    target, responses = run_window('S1_actual_meta_new_projection', new_case, s1_requests)
    new_payload = read(new_case['input_file'])
    for row in responses:
        request, response = row['request'], row['response']
        if request.get('method') == 'tools/call':
            assert response['result'] == new_payload
        elif request.get('method') in ('resources/list', 'resources/templates/list'):
            expected = {'resources': []} if request['method'] == 'resources/list' else {'resourceTemplates': []}
            assert contract.empty_discovery_rpc(request, response, expected)
    ledger = read(target / 'owner/TOOLS.json')
    assert ledger['attempts'] == ledger['admitted'] == 2
    assert all(type(row['transport_meta']) is dict for row in ledger['tools'])
    checks.append({'name': 'S1_actual_RPC_bytes_standard_meta_new_projection', 'passed': True,
                   'read_attempts': 2, 'empty_discovery_kinds': 2, 'tool_result': seal(new_case['input_file'])})

    old_case = next(row for row in read(OLD / 'INPUTS.json')['cases'] if row['case_id'] == 'S2')
    replay_sources.append(seal(old_case['input_file']))
    target, responses = run_window('R1_actual_success_archive', old_case, s2_requests)
    actual_completed = [row for row in s2_events if row['event'].get('type') == 'item.completed'
                        and row['event'].get('item', {}).get('type') == 'mcp_tool_call']
    public_calls = [{'perf_ns': row['perf_ns'], **row['event']} for row in actual_completed]
    archive = contract.archive_turn(target, {'audit_dir': str(target / 'owner')}, 1, public_calls)
    assert not archive['business_binding_errors'], archive['business_binding_errors']
    assert archive['tool_accounting']['completed_CLI_tool_calls'] == 3
    assert archive['tool_accounting']['completed_business_calls'] == 1
    assert archive['tool_accounting']['completed_empty_discoveries'] == 2
    assert all(row['matched'] for row in archive['discovery_bindings'])
    checks.append({'name': 'R1_actual_requests_results_CLI_events_original_RPC_archive', 'passed': True,
                   'archive': seal(target / 'ARCHIVE.json'), 'business_calls': 1, 'all_completed_CLI_calls': 3,
                   'empty_discovery_calls': 2, 'caller_ids': archive['result_contracts'][0]['caller_identity']})

    historical_discovery_counts = {name: 0 for name in contract.DISCOVERY}
    for case_id, rows in (('S1', s1_events), ('S2', s2_events), ('S3', s3_events)):
        tool_events = [{'perf_ns': row['perf_ns'], **row['event']} for row in rows
                       if row['event'].get('type') in ('item.started', 'item.completed')
                       and row['event'].get('item', {}).get('type') == 'mcp_tool_call']
        assert all(contract.classify_tool_item(row['item'], completed=row['type'] == 'item.completed') != 'unexpected'
                   for row in tool_events)
        accounting = contract.tool_accounting(tool_events)
        assert accounting['completed_CLI_tool_calls'] <= 4 and accounting['completed_empty_discoveries'] == 2
        assert not accounting['incomplete_control_item_ids']
        for event in tool_events:
            if event['type'] == 'item.completed' and contract.classify_tool_item(event['item']) == 'empty_resource_discovery':
                historical_discovery_counts[event['item']['tool']] += 1
        checks.append({'name': case_id + '_actual_event_classification', 'passed': True, 'accounting': accounting})
    assert historical_discovery_counts == {'list_mcp_resources': 3, 'list_mcp_resource_templates': 3}
    checks.append({'name': 'all_six_historical_empty_discoveries_counted', 'passed': True,
                   'counts_by_tool': historical_discovery_counts})
    actual_control = copy.deepcopy(next(row['item'] for row in public_calls if row['item']['server'] == 'codex'))
    nonempty = copy.deepcopy(actual_control)
    key = next(iter(json.loads(nonempty['result']['content'][0]['text'])))
    nonempty['result']['content'][0]['text'] = json.dumps({key: [{'uri': 'controlled-nonempty'}]})
    other = dict(actual_control, server='other')
    wrong_tool = dict(actual_control, tool='other_tool')
    assert all(contract.classify_tool_item(item) == 'unexpected' for item in (nonempty, other, wrong_tool))
    checks.append({'name': 'controlled_nonempty_and_other_tool_events_rejected', 'passed': True,
                   'scope': 'Pure data mutations of one actual completed discovery event.'})

    original = next(row for row in s1_requests if row[2].get('method') == 'tools/call')
    mutations = []
    for index, params in enumerate(({'name': 'read_observation', 'arguments': {'unexpected': True}},
                                    {'name': 'other_tool', 'arguments': {}},
                                    {'name': 'read_observation', 'arguments': {}, '_meta': []}), 100):
        request = copy.deepcopy(original[2])
        request['id'] = index
        request['params'] = params
        mutations.append(('controlled_actual_request_mutation', reader.encoded(request), request))
    target, responses = run_window('rejection_then_legal_actual_read', new_case, mutations + [original])
    assert all(row['response']['result']['isError'] for row in responses[:-1])
    assert responses[-1]['response']['result'] == new_payload
    ledger = read(target / 'owner/TOOLS.json')
    assert ledger['attempts'] == 4 and ledger['admitted'] == 1
    checks.append({'name': 'rejection_then_legal_actual_read', 'passed': True, 'attempts': 4, 'admitted': 1,
                   'scope': 'Three explicit protocol-control mutations followed by one unchanged actual S1 request.'})

    target, responses = run_window('four_read_admissions_and_fifth_rejection', new_case, [original] * 5)
    assert all(row['response']['result'] == new_payload for row in responses[:4])
    assert responses[4]['response']['result']['content'][0]['text'] == 'business_tool_budget_exhausted'
    ledger = read(target / 'owner/TOOLS.json')
    assert ledger['attempts'] == 5 and ledger['admitted'] == 4
    checks.append({'name': 'server_four_attempt_budget_guard', 'passed': True, 'attempts': 5, 'admitted': 4,
                   'scope': 'Pure Python protocol budget test. Formal CLI completed-call cap remains four.'})

    run_window('original_expired_deadline_rejected', new_case, [original], expired=True)
    checks.append({'name': 'original_expired_deadline_before_any_business_attempt', 'passed': True})
    missing = folder / 'missing_EXIT_control/attachments/bridge_control'
    missing.mkdir(parents=True)
    source_started = process_records[0]['exit_receipts'][0]['STARTED']
    save(missing / 'STARTED.json', source_started)
    missing_state = consume_turn.__globals__['wait_bridge_closed']({'endpoint': str(folder / 'unused.json'),
        'attachments_dir': str(missing.parent)})
    assert missing_state['confirmed'] is None and missing_state['receipt_status'] == 'unknown'
    checks.append({'name': 'missing_EXIT_remains_unknown', 'passed': True, 'receipt': missing_state,
                   'scope': 'Pure receipt-absence control copied from one actual observed STARTED.'})

    # Inspection of the actual isolated launch entry produces argv only.
    argv_folder = folder / 'argv_only'
    argv_folder.mkdir()
    cell_path = argv_folder / 'cell.json'
    task_deadline = time.perf_counter_ns() + 450_000_000_000
    save(cell_path, {'group': 'F', 'input_file': new_case['input_file'], 'input_sha256': new_case['input_sha256'],
                     'audit_dir': str(argv_folder / 'owner'), 'task_deadline_ns': task_deadline})
    argv = consume_turn.__globals__['initial_argv'](adapter.BASE, cell_path, argv_folder, argv_folder / 'final.txt', 'F')
    assert adapter.fresh_argv(argv) == argv
    assert '--deadline-ns' in ' '.join(argv) and str(task_deadline) in ' '.join(argv)
    loop_tree = ast.parse((NS / 'harness/consumer_loop.py').read_bytes())
    cap_checks = [node for node in ast.walk(loop_tree) if isinstance(node, ast.Raise)
                  and isinstance(node.exc, ast.Call) and node.exc.args
                  and isinstance(node.exc.args[0], ast.Constant)
                  and node.exc.args[0].value == 'original_four_completed_tool_call_limit']
    assert len(cap_checks) == 1
    checks.append({'name': 'fresh_argv_original_task_deadline_and_four_completed_tool_guard', 'passed': True,
                   'argv_only_no_CLI_process': True, 'task_seconds': 450, 'lifecycle_seconds': 600})
    sources = {row['path']: row for row in proof['execution_sources'] + replay_sources}
    for path in (Path(__file__), NS / 'harness/reused/stdio_checks.py', Path(inputs_path), schema,
                 NS / 'inputs/PROMPT.txt'):
        sources[str(path.resolve())] = seal(path)
    value = {'schema': 'm1-source-region-facts-first-001-bridge-preflight-v1', 'status': 'passed',
             'started_ns': began, 'closed_ns': time.perf_counter_ns(), 'runtime_path': str(folder),
             'checks': checks, 'adapter_proof': proof, 'protocol_processes': process_records,
             'loaded_execution_sources': sorted(sources.values(), key=lambda row: row['path']),
             'zero_work': {'real_model_consumers': 0, 'CLI_processes': 0, 'CLI_inference': 0, 'Blender': 0,
                           'product_solver_calls': 0, 'PNG_or_NPZ_encoding': 0, 'raster': 0, 'paid_API': 0},
             'base64_scope': 'JSON transport carries existing base64 verbatim. No PNG construction or encoding.',
             'actual_replay_scope': 'Original S1 and S2 RPC frames replayed byte-for-byte. Actual historical public tool events feed classification and original archive matching. Protocol-control mutations and missing-receipt controls are explicitly identified.'}
    save(NS / 'checks/BRIDGE_PREFLIGHT.json', value)
    print(json.dumps({'status': value['status'], 'checks': len(checks), 'processes': len(process_records),
                      'model_calls': 0, 'runtime_path': str(folder)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, default=NS / 'INPUTS.json')
    parser.add_argument('--runtime', type=Path, default=RUNTIME / 'checks')
    options = parser.parse_args()
    main(options.inputs, options.runtime)

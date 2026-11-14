"""One finite installed-stdio replay, with independent semantic decoding.

Root freezes and explicitly releases this script. Existing source-bound PNGs
are read and encoded again. No Blender, core observation or model is run.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback


def check_deadline(deadline):
    if time.perf_counter_ns() >= deadline:
        raise TimeoutError('original_replay_deadline_exceeded')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', required=True, type=Path)
    parser.add_argument('--binding', required=True, type=Path)
    parser.add_argument('--inputs', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--deadline-ns', type=int)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if not args.run:
        parser.error('Root must explicitly release the frozen replay with --run')
    started = time.perf_counter_ns()
    deadline = args.deadline_ns if args.deadline_ns is not None else started + 600_000_000_000
    payload, output = args.payload.resolve(), args.output.resolve()
    inputs_path = (payload / 'inputs/INPUTS.json') if args.inputs is None else args.inputs.resolve()
    output.mkdir(parents=True, exist_ok=False)
    # The entry is also a pure fixture loader until serve is explicitly called.
    import importlib.util

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    replay = load('_brief_fixture_loader', payload / 'replay_entry.py')
    helpers = load('_brief_local_stdio', payload / 'stdio_checks.py')
    contract = load('_brief_independent_contract', payload / 'semantic_contract.py')
    save = replay.save
    result = {'schema': 'm4-active-observation-brief-stdio-replay-v1', 'passed': False,
              'transport_replay': True, 'started_ns': started, 'deadline_ns': deadline,
              'records': [], 'new_Blender_processes': 0, 'actual_new_capture_calls': 0,
              'actual_new_prepare_calls': 0, 'actual_new_raster_attempts': 0,
              'actual_new_local_image_constructions': 0, 'model_calls': 0,
              'expected_tool_calls': 15, 'expected_protocol_requests': 17,
              'semantic_decoder_source_sha256': hashlib.sha256((payload / 'semantic_contract.py').read_bytes()).hexdigest(),
              'inputs_sha256': hashlib.sha256(inputs_path.read_bytes()).hexdigest()}
    client = None
    try:
        cases = replay.load_cases(inputs_path)
        historical_text_bytes = sum(case['historical_text_UTF8_bytes'] for case in cases)
        assert historical_text_bytes == 101824
        check_deadline(deadline)
        command = [sys.executable, '-I', '-B', '-X', 'utf8', str(payload / 'replay_entry.py'),
                   '--inputs', str(inputs_path), '--binding', str(args.binding.resolve()),
                   '--bootstrap', str(payload / 'verified_bootstrap.py'),
                   '--evidence', str(output / 'server'), '--deadline-ns', str(deadline)]
        client = helpers.StdioClient(command, output.parent, output / 'stdio', deadline)
        check_deadline(deadline)
        initialize = client.call({'jsonrpc': '2.0', 'id': 'initialize', 'method': 'initialize',
            'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                       'clientInfo': {'name': 'historical-PNG-local-reader', 'version': '1'}}})
        assert 'result' in initialize
        check_deadline(deadline)
        listed = client.call({'jsonrpc': '2.0', 'id': 'tools-list', 'method': 'tools/list'})
        assert any(tool['name'] == 'human_eye_scene_observe' for tool in listed['result']['tools'])
        for case in cases:
            outputs = {}
            for detail in replay.DETAIL_ORDER:
                check_deadline(deadline)
                name = case['case'] + '__' + detail
                row = {'case': case['case'], 'response_detail': detail, 'request_id': name,
                       'started_ns': time.perf_counter_ns(), 'transport_replay': True,
                       'historical_response_sha256': case['raw_response_sha256']}
                arguments = {'session_id': case['historical_value']['session_id'],
                             'include_image': True, 'query': {'mode': 'active_observation'}}
                if detail != 'default':
                    arguments['response_detail'] = detail
                response = client.call({'jsonrpc': '2.0', 'id': name, 'method': 'tools/call',
                                        'params': {'name': 'human_eye_scene_observe', 'arguments': arguments}})
                row['response_received_ns'] = time.perf_counter_ns()
                # A tool-level failure is retained while the fixed sequence
                # continues. An unusable transport raises and leaves a prefix.
                row['tool_is_error'] = response.get('result', {}).get('isError')
                consumed = helpers.inspect_images(response, output / 'consumer' / name)
                row['consumer_images_read_ns'] = consumed['closed_ns']
                row['elapsed_to_consumer_images_ns'] = consumed['closed_ns'] - row['started_ns']
                original_blocks = case['original_response']['result']['content'][1:]
                actual_blocks = response.get('result', {}).get('content', [])[1:]
                row['native_images_byte_identical'] = actual_blocks == original_blocks
                row['native_image_blocks'] = consumed['image_blocks_read']
                row['PNG_bytes'] = consumed['PNG_bytes']
                row['base64_characters'] = consumed['base64_characters']
                row['public_text_UTF8_bytes'] = len(response['result']['content'][0]['text'].encode('utf8'))
                row['native_image_validation'] = {'passed': False}
                row['consumer_text_matches_actual_wire'] = False
                try:
                    public = contract.extract_public_value(response)
                    row['native_image_validation'] = contract.validate_native_images(response)
                    row['consumer_text_matches_actual_wire'] = replay.encoded(consumed['text']) == replay.encoded(public)
                    if detail == 'full':
                        relocations = {change['mapped']: change['original'] for change in case['path_changes']}
                        expected = contract.canonicalize_full_diagnostics(case['historical_value'])
                        actual = contract.canonicalize_full_diagnostics(public, path_relocations=relocations)
                        semantic = {'passed': replay.encoded(expected) == replay.encoded(actual), 'expected': expected, 'actual': actual,
                                    'scope': 'complete historical diagnostic value, declared image paths reversed'}
                    else:
                        semantic = contract.compare_semantics(case['historical_value'], public)
                except Exception as exc:
                    semantic = {'passed': False, 'error': {'type': type(exc).__name__, 'message': str(exc)}}
                save(output / 'semantics' / (name + '.json'), semantic)
                row['semantic_passed'] = semantic['passed']
                row['closed_ns'] = time.perf_counter_ns()
                row['elapsed_ns'] = row['closed_ns'] - row['started_ns']
                outputs[detail] = response
                result['records'].append(row)
                save(output / 'progress' / (name + '.json'), row)
            equality = replay.encoded(outputs['default']['result']) == replay.encoded(outputs['brief']['result'])
            for row in result['records'][-3:]:
                row['default_equals_explicit_brief'] = equality
        quality = all(row['tool_is_error'] is False and row['semantic_passed'] is True
                      and row['native_image_validation']['passed'] is True
                      and row['native_images_byte_identical'] and row['consumer_text_matches_actual_wire']
                      and row['default_equals_explicit_brief'] for row in result['records'])
        default_rows = [row for row in result['records'] if row['response_detail'] == 'default']
        default_total = sum(row['public_text_UTF8_bytes'] for row in default_rows)
        per_case = [{'case': row['case'], 'actual_text_UTF8_bytes': row['public_text_UTF8_bytes'],
                     'limit': 2048 if row['case'] == 'nonplanar_source' else 8192,
                     'passed': row['public_text_UTF8_bytes'] <= (2048 if row['case'] == 'nonplanar_source' else 8192)}
                    for row in default_rows]
        result['quality_passed'] = quality
        result['fixed_data_byte_gate'] = {
            'semantic_quality_passed_before_byte_verdict': quality,
            'historical_text_UTF8_bytes': historical_text_bytes, 'default_text_UTF8_bytes': default_total,
            'default_to_historical_ratio': default_total / historical_text_bytes,
            'per_case': per_case,
            'passed': quality and all(row['passed'] for row in per_case)
                      and default_total * 100 <= historical_text_bytes * 35,
        }
        result['native_image_blocks'] = sum(row['native_image_blocks'] for row in result['records'])
        result['native_PNG_bytes'] = sum(row['PNG_bytes'] for row in result['records'])
        result['native_base64_characters'] = sum(row['base64_characters'] for row in result['records'])
        result['passed'] = (len(result['records']) == 15 and result['native_image_blocks'] == 24
                            and result['quality_passed'] and result['fixed_data_byte_gate']['passed'])
    except BaseException as exc:
        result['error'] = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
    finally:
        cleanup_errors = []
        if client is not None:
            try:
                result['stdio_cleanup'] = client.finish()
                if not result['stdio_cleanup']['confirmed']:
                    result['passed'] = False
            except BaseException as exc:
                cleanup_errors.append({'stage': 'stdio_finish', 'type': type(exc).__name__, 'message': str(exc)})
                result['passed'] = False
            try:
                result['actual_protocol_requests'] = len(client.records)
                result['RPC_TX_bytes'] = sum(row['TX_bytes'] for row in client.records)
                result['RPC_RX_bytes'] = sum(row.get('RX_bytes', 0) for row in client.records)
            except BaseException as exc:
                cleanup_errors.append({'stage': 'protocol_receipts', 'type': type(exc).__name__, 'message': str(exc)})
                result['passed'] = False
        try:
            server = json.loads((output / 'server/FINISH.json').read_bytes())
            result['server_finish'] = server
            stub = json.loads((output / 'server/STUB_CLOSE.json').read_bytes())
            result['stub_close'] = stub
            if (server['failure'] is not None or server['source_error'] is not None
                    or not stub['fixed_call_count_completed'] or server['service_calls'] != 15):
                result['passed'] = False
        except BaseException as exc:
            cleanup_errors.append({'stage': 'server_terminal_receipts', 'type': type(exc).__name__, 'message': str(exc)})
            result['passed'] = False
        result['cleanup_errors'] = cleanup_errors
        result['closed_before_publication_ns'] = time.perf_counter_ns()
        result['elapsed_before_publication_ns'] = result['closed_before_publication_ns'] - started
        result['final_RESULTS_write_close_included'] = False
        result['timing_scope'] = 'Entry input checks through child exit and readback. Final RESULTS publication and parent process lifetime are recorded by root.'
        save(output / 'RESULTS.json', result)
    print(json.dumps({'passed': result['passed'], 'tool_records': len(result['records']),
                      'error': result.get('error')}), flush=True)
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

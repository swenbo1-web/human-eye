"""One split/join installed Host-to-MCP acceptance sequence.

Root freezes and launches this script in the isolated installation. The five
tool calls are fixed. Pixel and delivery checks use the saved actual captures,
service values and frames, with zero extra product preparation or rendering.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback


BINARY = Path('D:/Tools/blender5.2/blender.exe')
BINARY_SHA256 = '284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb'
CASES = ('split_cold', 'split_hot', 'joined_cold', 'joined_hot', 'cached_full')


def read(path):
    return json.loads(Path(path).read_bytes())


def lines(path):
    return [json.loads(line) for line in Path(path).read_bytes().splitlines() if line.strip()]


def encoded(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False,
                       separators=(',', ':')) + '\n').encode('ascii')


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def check(deadline):
    if time.perf_counter_ns() >= deadline:
        raise TimeoutError('original_acceptance_deadline_exceeded')


def wait_ready(process, path, deadline):
    while True:
        check(deadline)
        if process.poll() is not None:
            raise RuntimeError('owned_QA_exited_before_READY')
        try:
            value = read(path)
            check(deadline)
            return value
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(.1)


def private_request(ready, kind, output, deadline):
    check(deadline)
    started = time.perf_counter_ns()
    tx = encoded({'type': kind, 'params': {}})
    output.mkdir()
    (output / 'TX.bin').write_bytes(tx)
    limit = max(.001, min(20, (deadline - started) / 1e9))
    with socket.create_connection((ready['host'], ready['port']), timeout=limit) as connection:
        connection.sendall(tx)
        raw = bytearray()
        while True:
            check(deadline)
            connection.settimeout(max(.001, min(20, (deadline - time.perf_counter_ns()) / 1e9)))
            chunk = connection.recv(65536)
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > 32 * 1024 * 1024:
                raise ValueError('private_QA_response_budget')
    (output / 'RX.bin').write_bytes(raw)
    response = json.loads(raw)
    save(output / 'RECEIPT.json', {'type': kind, 'started_ns': started,
        'closed_ns': time.perf_counter_ns(), 'TX_bytes': len(tx), 'RX_bytes': len(raw),
        'status': response.get('status')})
    if response.get('status') not in ('success', 'closed'):
        raise ValueError('private_QA_control_failed:' + str(response))
    return response


def checked_sidecar(metadata):
    raw = Path(metadata['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != metadata['sha256'] or len(raw) != metadata['bytes']:
        raise ValueError('actual_sidecar_bytes_changed')
    return json.loads(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--external-root', type=Path, required=True)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter_ns()
    deadline = started + 600_000_000_000
    external, payload, output = (path.resolve() for path in (args.external_root, args.payload, args.output))
    assert output.is_relative_to(external) and payload.is_relative_to(external)
    output.mkdir(parents=True, exist_ok=False)
    result = {'schema': 'm4-patch-ownership-installed-acceptance-v1', 'passed': False,
              'started_ns': started, 'original_deadline_ns': deadline, 'requests': [],
              'new_model_calls': 0, 'extra_product_prepare_calls': 0, 'extra_product_raster_calls': 0}
    qa = None
    client = None
    ready = None
    logs = []
    try:
        binding = read(args.binding)
        bootstrap = load('_patch_acceptance_bootstrap', payload / 'verified_bootstrap.py')
        guard = bootstrap.bootstrap(binding)
        helpers = load('_patch_acceptance_stdio', payload / 'stdio_checks.py')
        delivery = load('_patch_delivery_oracle', payload / 'delivery_oracle.py')
        pixels = load('_patch_pixel_oracle', payload / 'pixel_oracle.py')
        fixtures = {name: read(payload / 'inputs' / (name.upper() + '.json')) for name in ('split', 'joined')}
        expected = read(payload / 'inputs/EXPECTED_PATCHES.json')
        budget_start_count = len(list((external / 'run/render_budget').glob('attempt_*/INTENT.json')))
        result['prior_charged_raster_attempts'] = budget_start_count
        assert hashlib.sha256(BINARY.read_bytes()).hexdigest() == BINARY_SHA256
        qa_config = {'workspace': str(output / 'qa'), 'deadline_ns': deadline, 'max_calls': 64}
        for name in ('split', 'joined'):
            path = payload / 'inputs' / (name.upper() + '.json')
            qa_config[name + '_fixture'] = str(path)
            qa_config[name + '_fixture_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        save(output / 'QA_CONFIG.json', qa_config)
        command = [str(BINARY), '--factory-startup', '--disable-autoexec', '--background',
                   '--python-exit-code', '1', '--python', str(payload / 'qa_worker.py'),
                   '--', '--config', str(output / 'QA_CONFIG.json')]
        check(deadline)
        for name in ('QA_STDOUT.bin', 'QA_STDERR.bin'):
            logs.append((output / name).open('wb'))
        launched = time.perf_counter_ns()
        qa = subprocess.Popen(command, stdout=logs[0], stderr=logs[1],
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        ready = wait_ready(qa, output / 'qa/READY.json', min(deadline, started + 60_000_000_000))
        assert ready['pid'] == qa.pid and ready['deadline_ns'] == deadline and ready['stage'] == 'split'
        assert ready['worker_sha256'] == hashlib.sha256((payload / 'qa_worker.py').read_bytes()).hexdigest()
        assert all(ready[name + '_fixture_sha256'] == qa_config[name + '_fixture_sha256'] for name in ('split', 'joined'))
        save(output / 'QA_LAUNCH.json', {'command': command, 'pid': qa.pid,
             'started_ns': launched, 'ready_ns': time.perf_counter_ns(), 'READY': ready})
        identity = {key: binding[key] for key in ('base_version', 'implementation_revision', 'build_id',
                                                 'source_sha256', 'protocol_version')}
        identity.update(source_kind='installed_distribution', mode='live')
        config = {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
                  'project_root': binding['install_root'], 'state_file': str(output / 'state.json'),
                  'audit_file': str(output / 'audit.jsonl'), 'expected_identity': identity,
                  'request_budget_s': 90, 'blender': {'host': ready['host'], 'port': ready['port'], 'timeout_s': 30}}
        save(output / 'LIVE_CONFIG.json', config)
        stdio_command = [sys.executable, '-I', '-B', '-X', 'utf8', str(payload / 'stdio_entry.py'),
                         '--config', str(output / 'LIVE_CONFIG.json'), '--binding', str(args.binding.resolve()),
                         '--bootstrap', str(payload / 'verified_bootstrap.py'), '--evidence', str(output / 'server'),
                         '--budget', str(external / 'run/render_budget')]
        check(deadline)
        client = helpers.StdioClient(stdio_command, external / 'run', output / 'stdio', deadline)
        check(deadline)
        initialized = client.call({'jsonrpc': '2.0', 'id': 'initialize', 'method': 'initialize',
            'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                       'clientInfo': {'name': 'patch-PNG-local-reader', 'version': '1'}}})
        assert 'result' in initialized
        check(deadline)
        listed = client.call({'jsonrpc': '2.0', 'id': 'tools-list', 'method': 'tools/list'})
        assert any(tool['name'] == 'human_eye_scene_observe' for tool in listed['result']['tools'])
        cold = {}
        raw_by_case = {}
        for number, case in enumerate(CASES, 1):
            check(deadline)
            if case == 'joined_cold':
                private_request(ready, 'qa_join', output / 'QA_JOIN', deadline)
            representation = 'split' if case.startswith('split') else 'joined'
            arguments = {'session_id': 'm4-patch-ownership-001', 'include_image': True,
                         'query': {'mode': 'active_observation'}}
            if case == 'cached_full':
                arguments['response_detail'] = 'full'
            mark = time.perf_counter_ns()
            response = client.call({'jsonrpc': '2.0', 'id': case, 'method': 'tools/call',
                                    'params': {'name': 'human_eye_scene_observe', 'arguments': arguments}})
            consumed = helpers.inspect_images(response, output / ('consumer_' + case))
            result_meta = lines(output / 'server/RESULTS.jsonl')
            assert len(result_meta) == number
            raw = checked_sidecar(result_meta[-1])
            raw_by_case[case] = raw
            capture_meta = lines(output / 'server/CAPTURES.jsonl')
            assert len(capture_meta) == number and len(result_meta[-1]['capture_associations']) == 1
            association = result_meta[-1]['capture_associations'][0]
            assert association['index'] == number and association['sha256'] == capture_meta[-1]['sha256']
            capture = checked_sidecar(capture_meta[-1])
            geometry_check = delivery.verify_capture(capture, fixtures[representation])
            assert geometry_check['world_triangle_sequence_sha256'] == expected['draw_order_world_triangles_sha256']
            assert raw['work']['capture_calls'] == 1 and raw['binding']['scene_revision'] == capture['revision']
            decoded = delivery.verify_response(response, raw, 'full' if case == 'cached_full' else 'brief')
            assert decoded['passed'] is True and decoded['ROI_count'] == 138
            assert decoded['object_count'] == (29 if representation == 'split' else 1)
            support = raw['facts']['scope']['patch_support']['objects']
            assert sum(row['source_triangle_count'] for row in support) == 3337
            assert sum(row['supported_triangle_count'] for row in support) == 3336
            assert sum(row['unsupported_triangle_count'] for row in support) == 1
            if case.endswith('_cold'):
                assert raw['work']['prepare_calls'] == raw['work']['geometry_parse_calls'] == 1
                assert raw['work']['raster_attempts'] == len(raw['frames']) <= 6
                indexes = lines(output / 'server/INDEXES.jsonl')
                matching = [row for row in indexes if row['actual_capture_sha256'] == capture_meta[-1]['sha256']]
                assert len(matching) == 1
                index = checked_sidecar(matching[0])
                normalized = delivery.normalize_index(capture, index, expected, representation)
                cold[representation] = {'capture': capture, 'index': index, 'raw': raw, 'normalized': normalized}
            else:
                baseline = raw_by_case[representation + '_cold']
                assert raw['work']['result_cache_hit'] is True
                assert all(raw['work'][key] == 0 for key in ('geometry_parse_calls', 'prepare_calls', 'raster_attempts'))
                assert raw['work']['frame_reuses'] == len(baseline['frames'])
                assert raw['binding'] == baseline['binding'] and raw['facts'] == baseline['facts']
                assert [(row['image_ref'], row['image_sha256']) for row in raw['frames']] == [
                    (row['image_ref'], row['image_sha256']) for row in baseline['frames']]
            row = {'case': case, 'representation': representation, 'started_ns': mark,
                   'consumer_read_closed_ns': consumed['closed_ns'],
                   'elapsed_to_consumer_ns': consumed['closed_ns'] - mark,
                   'actual_service_result': result_meta[-1], 'actual_capture': capture_meta[-1],
                   'delivery': decoded, 'geometry': geometry_check, 'work': raw['work']}
            result['requests'].append(row)
            save(output / 'progress' / (case + '.json'), row)
        assert delivery.encoded(cold['split']['normalized']) == delivery.encoded(cold['joined']['normalized'])
        assert cold['split']['raw']['binding']['binding_sha256'] != cold['joined']['raw']['binding']['binding_sha256']
        result['split_join_geometry_and_classifications_equal'] = True
        result['pixel_checks'] = []
        for representation in ('split', 'joined'):
            current = cold[representation]
            observations = {row['view_name']: row for row in current['raw']['facts']['observations']}
            for frame in current['raw']['frames']:
                check(deadline)
                receipt = pixels.verify_frame(current['capture'], current['index'], frame,
                    observations[frame['view_name']]['pixel_rows'], expected, representation)
                assert receipt['passed'] is True
                result['pixel_checks'].append({'representation': representation, 'view': frame['view_name'],
                                               'receipt': receipt})
                save(output / 'pixels' / (representation + '_' + frame['view_name'] + '.json'), receipt)
        # Existing arrays supply the cross-representation pixel comparison.
        import numpy as np
        split_frames = cold['split']['raw']['frames']
        joined_frames = cold['joined']['raw']['frames']
        assert [frame['view_name'] for frame in split_frames] == [frame['view_name'] for frame in joined_frames]
        result['representation_pixel_comparisons'] = []
        for first, second in zip(split_frames, joined_frames):
            assert first['patch_roi_ids'] == second['patch_roi_ids']
            with np.load(first['arrays_path'], allow_pickle=False) as a, np.load(second['arrays_path'], allow_pickle=False) as b:
                equal = {key: np.array_equal(a[key], b[key]) for key in ('color', 'depth', 'patch_owners')}
            assert all(equal.values()) and Path(first['image_path']).read_bytes() == Path(second['image_path']).read_bytes()
            result['representation_pixel_comparisons'].append({'view': first['view_name'], **equal, 'PNG_bytes_equal': True,
                                                              'object_owner_comparison': 'representation-dependent'})
        intents = lines(external / 'run/render_budget/INTENTS.jsonl')
        count = len(list((external / 'run/render_budget').glob('attempt_*/INTENT.json')))
        completed = sum(len(cold[name]['raw']['frames']) for name in cold)
        assert count == len(intents) and count - budget_start_count == completed <= 12 and count <= 14
        assert [row['attempt'] for row in intents] == list(range(1, count + 1))
        assert len(client.records) == 7 and len(lines(output / 'server/INDEXES.jsonl')) == 2
        result.update(new_raster_attempts=count - budget_start_count, global_charged_raster_attempts=count,
                      completed_new_frames=completed,
                      total_native_image_blocks=sum(len(row['delivery']['native_images']) for row in result['requests']),
                      global_raster_hard_cap=14, expected_active_calls=5, actual_protocol_requests=7)
        guard.verify_loaded()
        result['passed'] = True
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
        if qa is not None:
            close_started = time.perf_counter_ns()
            qa_exit = None
            forced = False
            try:
                if ready is not None and qa.poll() is None:
                    private_request(ready, 'close', output / 'QA_CLOSE', deadline)
            except BaseException as exc:
                cleanup_errors.append({'stage': 'QA_close_request', 'type': type(exc).__name__, 'message': str(exc)})
            try:
                qa_exit = qa.wait(timeout=10)
            except BaseException as exc:
                cleanup_errors.append({'stage': 'QA_initial_wait', 'type': type(exc).__name__, 'message': str(exc)})
            if qa_exit is None:
                forced = True
                try:
                    qa.kill()
                except BaseException as exc:
                    cleanup_errors.append({'stage': 'QA_held_kill', 'type': type(exc).__name__, 'message': str(exc)})
                try:
                    qa_exit = qa.wait(timeout=10)
                except BaseException as exc:
                    cleanup_errors.append({'stage': 'QA_post_kill_wait', 'type': type(exc).__name__, 'message': str(exc)})
            handle = getattr(qa, '_handle', None)
            try:
                if handle is not None and qa_exit is not None:
                    handle.Close()
            except BaseException as exc:
                cleanup_errors.append({'stage': 'QA_handle_close', 'type': type(exc).__name__, 'message': str(exc)})
            result['QA_cleanup'] = {'pid': qa.pid, 'exit_code': qa_exit, 'forced_kill': forced,
                'held_handle_closed': handle is None or bool(handle.closed),
                'started_ns': close_started, 'closed_ns': time.perf_counter_ns()}
            result['QA_cleanup']['confirmed'] = qa_exit == 0 and not forced and result['QA_cleanup']['held_handle_closed']
            if not result['QA_cleanup']['confirmed']:
                result['passed'] = False
        for stream in logs:
            try:
                stream.close()
            except BaseException as exc:
                cleanup_errors.append({'stage': 'QA_log_close', 'type': type(exc).__name__, 'message': str(exc)})
        try:
            finish = read(output / 'server/FINISH.json')
            result['server_finish'] = finish
            if (finish['source_check_error'] is not None or finish['failure'] is not None
                    or finish['capture_calls'] != 5 or finish['prepare_calls'] != 2 or finish['observe_calls'] != 5):
                result['passed'] = False
        except BaseException as exc:
            cleanup_errors.append({'stage': 'server_terminal_receipt', 'type': type(exc).__name__, 'message': str(exc)})
        result['cleanup_errors'] = cleanup_errors
        if cleanup_errors:
            result['passed'] = False
        result['closed_before_publication_ns'] = time.perf_counter_ns()
        result['final_RESULTS_publication_included_in_internal_clock'] = False
        save(output / 'RESULTS.json', result)
    print(json.dumps({'passed': result['passed'], 'requests': len(result['requests']), 'error': result.get('error')}), flush=True)
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

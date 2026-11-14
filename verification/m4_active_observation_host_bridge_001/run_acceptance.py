"""One owned Blender and stdio acceptance sequence, with all original receipts."""

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


def read(path):
    return json.loads(Path(path).read_bytes())


def encoded(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False,
                       separators=(',', ':')) + '\n').encode('ascii')


def save(path, value):
    with Path(path).open('xb') as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def wait_ready(process, path, deadline):
    while True:
        if time.perf_counter_ns() >= deadline:
            raise TimeoutError('owned_QA_READY_deadline')
        if process.poll() is not None:
            raise RuntimeError('owned_QA_exited_before_READY')
        try:
            candidate = read(path)
            if time.perf_counter_ns() >= deadline:
                raise TimeoutError('owned_QA_READY_deadline')
            return candidate
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        time.sleep(.1)


def private_request(ready, kind, output):
    started = time.perf_counter_ns()
    tx = encoded({'type': kind, 'params': {}})
    with socket.create_connection((ready['host'], ready['port']), timeout=20) as connection:
        connection.settimeout(20)
        connection.sendall(tx)
        raw = bytearray()
        while True:
            chunk = connection.recv(65536)
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > 32 * 1024 * 1024:
                raise ValueError('private_QA_response_budget')
        response = json.loads(raw)
    output.mkdir()
    (output / 'TX.bin').write_bytes(tx)
    (output / 'RX.bin').write_bytes(raw)
    save(output / 'RECEIPT.json', {'type': kind, 'started_ns': started,
        'closed_ns': time.perf_counter_ns(), 'TX_bytes': len(tx), 'RX_bytes': len(raw),
        'status': response.get('status')})
    if response.get('status') not in ('success', 'closed'):
        raise ValueError('private_QA_control_failed:' + str(response))
    return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--external-root', type=Path, required=True)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    external, payload, output = (p.resolve() for p in
                                 (options.external_root, options.payload, options.output))
    assert output.is_relative_to(external) and payload.is_relative_to(external)
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter_ns()
    deadline = started + 600_000_000_000
    binding = read(options.binding)
    bootstrap = load('_host_acceptance_bootstrap', payload / 'verified_bootstrap.py')
    guard = bootstrap.bootstrap(binding)
    from human_eye_plugin import active_observation as core
    helpers = load('_host_acceptance_stdio', payload / 'stdio_checks.py')
    protocol = read(payload / 'HARNESS_PROTOCOL.json')
    binary = Path(protocol['QA']['binary'])
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == protocol['QA']['binary_sha256']
    fixture = read(payload / 'FIXTURE.json')
    qa_config = {'fixture': str(payload / 'QA_GEOMETRY.json'),
                 'fixture_sha256': fixture['fixture_sha256'],
                 'workspace': str(output / 'qa'), 'deadline_ns': deadline, 'max_calls': 64}
    save(output / 'QA_CONFIG.json', qa_config)
    command = [str(binary), '--factory-startup', '--disable-autoexec', '--background',
               '--python-exit-code', '1', '--python', str(payload / 'qa_worker.py'),
               '--', '--config', str(output / 'QA_CONFIG.json')]
    qa = None
    client = None
    ready = None
    logs = []
    result = {'passed': False, 'started_ns': started, 'original_deadline_ns': deadline,
              'new_model_calls': 0, 'new_paired_benchmarks': 0, 'comparisons': [], 'requests': []}
    try:
        for name in ('QA_STDOUT.bin', 'QA_STDERR.bin'):
            logs.append((output / name).open('wb'))
        launch_started = time.perf_counter_ns()
        qa = subprocess.Popen(command, stdout=logs[0], stderr=logs[1],
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        ready = wait_ready(qa, output / 'qa/READY.json', min(deadline, started + 60_000_000_000))
        assert ready['pid'] == qa.pid and ready['deadline_ns'] == deadline
        assert ready['worker_sha256'] == hashlib.sha256((payload / 'qa_worker.py').read_bytes()).hexdigest()
        assert ready['fixture_sha256'] == fixture['fixture_sha256']
        save(output / 'QA_LAUNCH.json', {'command': command, 'pid': qa.pid,
             'started_ns': launch_started, 'ready_ns': time.perf_counter_ns(), 'READY': ready})
        expected = {key: binding[key] for key in ('base_version', 'implementation_revision',
                    'build_id', 'source_sha256', 'protocol_version')}
        expected.update(source_kind='installed_distribution', mode='live')
        config = {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
                  'project_root': binding['install_root'], 'state_file': str(output / 'state.json'),
                  'audit_file': str(output / 'audit.jsonl'), 'expected_identity': expected,
                  'request_budget_s': 90, 'blender': {'host': ready['host'], 'port': ready['port'],
                                                   'timeout_s': 30}}
        save(output / 'LIVE_CONFIG.json', config)
        stdio_command = [sys.executable, '-I', '-B', '-X', 'utf8', str(payload / 'stdio_entry.py'),
                         '--config', str(output / 'LIVE_CONFIG.json'), '--binding', str(options.binding),
                         '--bootstrap', str(payload / 'verified_bootstrap.py'),
                         '--evidence', str(output / 'server'),
                         '--budget', str(external / 'run/render_budget')]
        client = helpers.StdioClient(stdio_command, external / 'run', output / 'stdio', deadline)
        initialized = client.call({'jsonrpc': '2.0', 'id': 'initialize', 'method': 'initialize',
                                   'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                                              'clientInfo': {'name': 'local-PNG-reader', 'version': '1'}}})
        assert 'result' in initialized
        listed = client.call({'jsonrpc': '2.0', 'id': 'tools-list', 'method': 'tools/list'})
        assert any(tool['name'] == 'human_eye_scene_observe' for tool in listed['result']['tools'])
        ordinary = None
        for case in ('ordinary', 'same_source_repeat', 'renamed_source', 'nonplanar_source'):
            if case == 'renamed_source':
                private_request(ready, 'qa_rename', output / 'QA_RENAME')
            if case == 'nonplanar_source':
                private_request(ready, 'qa_nonplanar', output / 'QA_NONPLANAR')
            request_started = time.perf_counter_ns()
            response = client.call({'jsonrpc': '2.0', 'id': case, 'method': 'tools/call',
                'params': {'name': 'human_eye_scene_observe', 'arguments': {
                    'session_id': 'm4-host-bridge-001', 'include_image': True,
                    'query': {'mode': 'active_observation'}}}})
            assert response['result'].get('isError') is False, response
            consumed = helpers.inspect_images(response, output / ('consumer_' + case))
            value = consumed['text']
            result['requests'].append({'case': case, 'started_ns': request_started,
                'consumer_images_read_ns': consumed['closed_ns'],
                'elapsed_to_consumer_images_ns': consumed['closed_ns'] - request_started,
                'work': value['work'], 'binding': value['binding'],
                'consumer_image_blocks': consumed['image_blocks_read']})
            save(output / 'PROGRESS.json', result)
            assert value['result_kind'] == 'active_observation'
            assert value['work']['capture_calls'] == 1
            assert value['image_delivery']['consumer_read_status'] == 'unconfirmed'
            expected_images = 0 if case == 'nonplanar_source' else 2
            assert consumed['image_blocks_read'] == len(value['frames']) == expected_images
            assert [image['PNG_sha256'] for image in consumed['images']] == [frame['image_sha256'] for frame in value['frames']]
            if case == 'same_source_repeat':
                assert value['work']['prepare_calls'] == value['work']['geometry_parse_calls'] == value['work']['raster_attempts'] == 0
                assert value['work']['frame_reuses'] == 2
                assert value['binding']['binding_sha256'] == ordinary['binding']['binding_sha256']
                assert [f['image_ref'] for f in value['frames']] == [f['image_ref'] for f in ordinary['frames']]
            else:
                assert value['work']['geometry_parse_calls'] == value['work']['prepare_calls'] == 1
                assert value['work']['raster_attempts'] == expected_images
                indexes = [json.loads(line) for line in (output / 'server/INDEXES.jsonl').read_bytes().splitlines()]
                index = read(indexes[-1]['path'])
                captures = [json.loads(line) for line in (output / 'server/CAPTURES.jsonl').read_bytes().splitlines()]
                capture = read(captures[-1]['path'])
                compared = helpers.compare_same_capture(core, capture, index['cameras'], value, index)
                assert all(flag for key, flag in compared.items() if key.endswith(('equal', 'match')))
                assert compared['bridge_projection_bound_to_same_capture']
                for region in value['facts']['regions']:
                    actual = capture['meshes'][region['object_index']]
                    assert region['host_id'] == actual['object_id'] and region['object_name'] == actual['name']
                    assert region['instance_id'] == capture['host_identity']['object_instances'][actual['object_id']]
                save(output / ('DIRECT_' + case + '.json'), compared)
                result['comparisons'].append({'case': case, 'new_rasters': 0,
                                             'extra_test_geometry_parses': 1, 'extra_test_indexes': 1})
            scope = value['facts']['scope']
            if case == 'nonplanar_source':
                assert value['status'] == 'unknown' and value['observation_status'] == 'no_supported_regions'
                assert scope['capture_object_count'] == 1 and scope['supported_roi_object_count'] == 0
                assert len(scope['objects_without_supported_roi']) == 1
            else:
                assert value['facts']['coverage']['observed_views'] == ['SCENE', 'BACK']
                assert scope['capture_object_count'] == 28 and scope['supported_roi_object_count'] == 6
                assert len(scope['objects_without_supported_roi']) == 22
                assert len(value['facts']['coverage']['covered_roi_ids']) == 5
                assert len(value['facts']['coverage']['candidate_pool_uncovered_roi_ids']) == 1
            if case == 'ordinary':
                ordinary = value
            if case == 'renamed_source':
                assert value['binding']['binding_sha256'] != ordinary['binding']['binding_sha256']
                assert not ({f['image_ref'] for f in value['frames']} & {f['image_ref'] for f in ordinary['frames']})
                assert any(row['object_name'] == fixture['rename_control']['to'] for row in value['facts']['regions'])
            print(json.dumps({'case': case, 'consumer_images': expected_images,
                              'new_rasters': value['work']['raster_attempts']}), flush=True)
        bad = client.call({'jsonrpc': '2.0', 'id': 'bad_active_query', 'method': 'tools/call',
            'params': {'name': 'human_eye_scene_observe', 'arguments': {
                'session_id': 'm4-host-bridge-001', 'query': {'mode': 'active_observation', 'unsupported': True}}}})
        assert bad['result']['isError'] is True
        assert client.call({'jsonrpc': '2.0', 'id': 'ping_after_bad_request', 'method': 'ping'})['result'] == {}
        old = client.call({'jsonrpc': '2.0', 'id': 'old_readonly_regression', 'method': 'tools/call',
            'params': {'name': 'human_eye_scene_observe', 'arguments': {'session_id': 'm4-host-bridge-001',
                       'include_image': False, 'query': {'mode': 'directory'}}}})
        assert old['result'].get('isError') is False and all(block['type'] == 'text' for block in old['result']['content'])
        assert len(list((external / 'run/render_budget').glob('attempt_*/INTENT.json'))) == 4
        guard.verify_loaded()
        result['passed'] = True
    except BaseException as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
    finally:
        cleanup_errors = []
        if client is not None:
            try:
                result['stdio_cleanup'] = client.finish()
                if not result['stdio_cleanup']['confirmed']:
                    result['passed'] = False
            except BaseException as error:
                cleanup_errors.append({'stage': 'stdio_finish', 'type': type(error).__name__,
                                       'message': str(error)})
                result['passed'] = False
        if qa is not None:
            close_start = time.perf_counter_ns()
            qa_exit = None
            forced = False
            try:
                if ready is not None and qa.poll() is None:
                    private_request(ready, 'close', output / 'QA_CLOSE')
            except BaseException as error:
                cleanup_errors.append({'stage': 'QA_close_request', 'type': type(error).__name__,
                                       'message': str(error)})
                result['passed'] = False
            try:
                qa_exit = qa.wait(timeout=10)
            except BaseException as error:
                cleanup_errors.append({'stage': 'QA_initial_wait', 'type': type(error).__name__,
                                       'message': str(error)})
            if qa_exit is None:
                forced = True
                result['passed'] = False
                try:
                    qa.kill()
                except BaseException as error:
                    cleanup_errors.append({'stage': 'QA_held_kill', 'type': type(error).__name__,
                                           'message': str(error)})
                try:
                    qa_exit = qa.wait(timeout=10)
                except BaseException as error:
                    cleanup_errors.append({'stage': 'QA_post_kill_wait', 'type': type(error).__name__,
                                           'message': str(error)})
            handle = getattr(qa, '_handle', None)
            try:
                if handle is not None and qa_exit is not None:
                    handle.Close()
            except BaseException as error:
                cleanup_errors.append({'stage': 'QA_handle_close', 'type': type(error).__name__,
                                       'message': str(error)})
            result['QA_cleanup'] = {'pid': qa.pid, 'exit_code': qa_exit, 'forced_kill': forced,
                'held_handle_closed': handle is None or bool(handle.closed),
                'started_ns': close_start, 'closed_ns': time.perf_counter_ns()}
            result['QA_cleanup']['confirmed'] = (qa_exit == 0 and not forced
                and result['QA_cleanup']['held_handle_closed'])
            if not result['QA_cleanup']['confirmed']:
                result['passed'] = False
        for stream in logs:
            try:
                stream.close()
            except BaseException as error:
                cleanup_errors.append({'stage': 'QA_log_close', 'type': type(error).__name__,
                                       'message': str(error)})
        result['cleanup_errors'] = cleanup_errors
        if cleanup_errors:
            result['passed'] = False
        result['closed_before_publication_ns'] = time.perf_counter_ns()
        save(output / 'RESULTS.json', result)
    print(json.dumps({'passed': result['passed'], 'error': result.get('error')}), flush=True)
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

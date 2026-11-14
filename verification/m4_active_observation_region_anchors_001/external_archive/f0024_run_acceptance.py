"""One joined installed Host-to-MCP region-anchor acceptance sequence.

Root freezes and launches this script in the isolated installation. The three
tool calls are fixed. Pixel and delivery checks use the saved actual captures,
service values and frames, with zero extra product preparation or rendering.
"""

import argparse
from fractions import Fraction
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
CASES = ('joined_cold', 'joined_hot', 'cached_full')
WORLD_FIELDS = ('center_world_m', 'half_edge_u_world_m', 'half_edge_v_world_m', 'front_direction_world')
BASE_PIXEL_FIELDS = ('roi_id', 'object_index', 'view', 'front_facing', 'visible_surface_pixels',
                     'contrasting_boundary_pixels', 'readable', 'minimum_surface_pixels',
                     'minimum_boundary_pixels', 'minimum_rgb_boundary_contrast')
BRIEF_TEXT_LIMIT = 48162


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


def exact_vector(value):
    assert type(value) is list and len(value) == 3
    assert all(type(item) in (int, float, str) for item in value)
    return tuple(Fraction(item) for item in value)


def verify_historical_facts(raw, historical):
    facts, previous = raw['facts'], historical['facts']
    assert facts['coverage'] == previous['coverage']
    assert len(facts['coverage']['covered_roi_ids']) == 115
    assert len(facts['coverage']['unresolved_roi_ids']) == 23
    assert [row['roi_id'] for row in facts['regions']] == [row['roi_id'] for row in previous['regions']]
    for current, old in zip(facts['regions'], previous['regions']):
        assert all(current[key] == old[key] for key in ('roi_id', 'object_index', 'object_name', 'status', 'reason'))
    assert [row['view_name'] for row in facts['observations']] == [row['view_name'] for row in previous['observations']]
    rows = 0
    for current, old in zip(facts['observations'], previous['observations']):
        assert current['readable_roi_ids'] == old['readable_roi_ids']
        assert len(current['pixel_rows']) == len(old['pixel_rows']) == 138
        for pixel, prior in zip(current['pixel_rows'], old['pixel_rows']):
            assert all(pixel[key] == prior[key] for key in BASE_PIXEL_FIELDS)
            rows += 1
    current_support = facts['scope']['patch_support']['objects']
    old_support = previous['scope']['patch_support']['objects']
    assert len(current_support) == len(old_support) == 1
    fields = ('object_index', 'source_triangle_count', 'supported_triangle_count', 'supported_triangle_indices',
              'unsupported_triangle_count', 'unsupported_components', 'support_status')
    assert all(current_support[0][key] == old_support[0][key] for key in fields)
    return {'passed': True, 'covered_regions': 115, 'unknown_regions': 23,
            'unchanged_original_pixel_rows': rows, 'supported_triangles': 3336, 'unknown_triangles': 1}


def verify_location_questions(public, questions, capture, delivery):
    """Locate frozen questions through received brief tables and source ranges."""
    value = delivery.decode_brief(public)
    answers = []
    assert len(questions['questions']) == 4
    for question in questions['questions']:
        given, expected = question['given'], question['expected']
        if 'triangle_vertices_world_m' in given:
            vertices = [exact_vector(point) for point in given['triangle_vertices_world_m']]
            assert exact_vector(given['triangle_center_world_m']) == tuple(
                sum(point[axis] for point in vertices) / 3 for axis in range(3))
            matches = []
            for object_index, mesh in enumerate(capture['meshes']):
                points = [exact_vector(point) for point in mesh['vertices']]
                matches.extend((object_index, face_index) for face_index, face in enumerate(mesh['faces'])
                               if {points[index] for index in face} == set(vertices))
            assert matches == [(expected['object_index'], expected['source_triangle_indices'][0])]
            object_index, face_index = matches[0]
            components = [row for row in value['scope']['patch_support']['unsupported_components']
                          if row['object_index'] == object_index and face_index in row['triangle_indices']]
            assert len(components) == 1 and components[0]['status'] == expected['status'] == 'unknown'
            assert expected['supported'] is False
            answers.append({'id': question['id'], 'passed': True, 'object_index': object_index,
                'source_triangle_indices': [face_index], 'status': 'unknown',
                'location_binding': 'actual captured triangle and received brief unknown-component range'})
            continue
        matches = [(index, region) for index, region in enumerate(value['regions'])
                   if all(exact_vector(region[key]) == exact_vector(given[key])
                          for key in ('center_world_m', 'front_direction_world'))]
        assert len(matches) == 1
        region_index, region = matches[0]
        assert region['roi_id'] == expected['world']['roi_id']
        assert all(exact_vector(region[key]) == exact_vector(expected['world'][key]) for key in WORLD_FIELDS)
        wanted_pixels = [expected['pixel']] if 'pixel' in expected else expected['pixels']
        actual_pixels = []
        for wanted in wanted_pixels:
            image_indices = [index for index, image in enumerate(value['images']) if image['view_name'] == wanted['view']]
            assert len(image_indices) == 1
            pixels = [pixel for pixel in value['pixels']
                      if pixel['region_index'] == region_index and pixel['image_index'] == image_indices[0]]
            assert len(pixels) == 1
            actual = dict(pixels[0], roi_id=region['roi_id'], object_index=region['object_index'], view=wanted['view'])
            assert all(type(actual[key]) is type(item) and actual[key] == item for key, item in wanted.items())
            actual_pixels.append({key: actual[key] for key in wanted})
        if 'status' in expected:
            assert region['status'] == expected['status']
        answers.append({'id': question['id'], 'passed': True, 'roi_id': region['roi_id'],
            'world': {key: region[key] for key in WORLD_FIELDS}, 'status': region['status'],
            'pixels': actual_pixels})
    return {'passed': True, 'questions_checked': len(answers), 'answers': answers,
            'extra_local_brief_decode_calls': 1, 'new_product_calls': 0, 'new_model_calls': 0}


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
    result = {'schema': 'm4-region-anchors-installed-acceptance-v1', 'passed': False,
              'started_ns': started, 'original_deadline_ns': deadline, 'requests': [],
              'new_model_calls': 0, 'extra_product_prepare_calls': 0, 'extra_product_raster_calls': 0,
              'brief_text_limit': BRIEF_TEXT_LIMIT, 'brief_text_budget_passed': True}
    qa = None
    client = None
    ready = None
    logs = []
    budget_start_count = len(list((external / 'run/render_budget').glob('attempt_*')))
    result['prior_charged_raster_attempts'] = budget_start_count
    try:
        binding = read(args.binding)
        bootstrap = load('_anchor_acceptance_bootstrap', payload / 'verified_bootstrap.py')
        guard = bootstrap.bootstrap(binding)
        helpers = load('_anchor_acceptance_stdio', payload / 'stdio_checks.py')
        delivery = load('_anchor_delivery_oracle', payload / 'delivery_oracle.py')
        pixels = load('_anchor_pixel_oracle', payload / 'pixel_oracle.py')
        fixture = read(payload / 'inputs/JOINED.json')
        expected = read(payload / 'inputs/EXPECTED_PATCHES.json')
        reference = read(payload / 'REFERENCE.json')
        questions = read(payload / 'QUESTIONS.json')
        assert reference['reference_path_base'] == 'task_namespace'
        historical = read(payload / reference['historical']['service_result_path'])
        historical_index = read(payload / reference['historical']['index_path'])
        result['reference_sha256'] = hashlib.sha256((payload / 'REFERENCE.json').read_bytes()).hexdigest()
        result['questions_sha256'] = hashlib.sha256((payload / 'QUESTIONS.json').read_bytes()).hexdigest()
        assert hashlib.sha256(BINARY.read_bytes()).hexdigest() == BINARY_SHA256
        fixture_path = payload / 'inputs/JOINED.json'
        qa_config = {'workspace': str(output / 'qa'), 'deadline_ns': deadline, 'max_calls': 32,
                     'joined_fixture': str(fixture_path),
                     'joined_fixture_sha256': hashlib.sha256(fixture_path.read_bytes()).hexdigest()}
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
        assert ready['pid'] == qa.pid and ready['deadline_ns'] == deadline and ready['stage'] == 'joined'
        assert ready['worker_sha256'] == hashlib.sha256((payload / 'qa_worker.py').read_bytes()).hexdigest()
        assert ready['joined_fixture_sha256'] == qa_config['joined_fixture_sha256']
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
                       'clientInfo': {'name': 'region-anchor-local-reader', 'version': '1'}}})
        assert 'result' in initialized
        runtime = initialized['result']['_meta']['human_eye']
        assert runtime['source_kind'] == 'installed_distribution'
        assert runtime['source_sha256'] == binding['source_sha256'] and runtime['identity_check']['compatible'] is True
        check(deadline)
        listed = client.call({'jsonrpc': '2.0', 'id': 'tools-list', 'method': 'tools/list'})
        assert any(tool['name'] == 'human_eye_scene_observe' for tool in listed['result']['tools'])
        cold = None
        cold_index = None
        result['pixel_checks'] = []
        for number, case in enumerate(CASES, 1):
            check(deadline)
            arguments = {'session_id': 'm4-region-anchors-001', 'include_image': True,
                         'query': {'mode': 'active_observation'}}
            if case == 'cached_full':
                arguments['response_detail'] = 'full'
            mark = time.perf_counter_ns()
            response = client.call({'jsonrpc': '2.0', 'id': case, 'method': 'tools/call',
                                    'params': {'name': 'human_eye_scene_observe', 'arguments': arguments}})
            consumed = helpers.inspect_images(response, output / ('consumer_' + case))
            validation_started = time.perf_counter_ns()
            result_meta = lines(output / 'server/RESULTS.jsonl')
            assert len(result_meta) == number
            raw = checked_sidecar(result_meta[-1])
            capture_meta = lines(output / 'server/CAPTURES.jsonl')
            assert len(capture_meta) == number and len(result_meta[-1]['capture_associations']) == 1
            association = result_meta[-1]['capture_associations'][0]
            assert association['index'] == number and association['sha256'] == capture_meta[-1]['sha256']
            capture = checked_sidecar(capture_meta[-1])
            geometry_check = delivery.verify_capture(capture, fixture)
            assert geometry_check['world_triangle_sequence_sha256'] == expected['draw_order_world_triangles_sha256']
            assert raw['work']['capture_calls'] == 1 and raw['binding']['scene_revision'] == capture['revision']
            decoded = delivery.verify_response(response, raw, 'full' if case == 'cached_full' else 'brief')
            assert decoded['passed'] is True and decoded['ROI_count'] == 138 and decoded['object_count'] == 1
            if case != 'cached_full':
                assert decoded['schema'] == 'active-observation-brief-v3'
            support = raw['facts']['scope']['patch_support']['objects']
            assert len(support) == 1 and support[0]['source_triangle_count'] == 3337
            assert support[0]['supported_triangle_count'] == 3336 and support[0]['unsupported_triangle_count'] == 1
            assert support[0]['support_status'] == 'partially_supported'
            assert all(row['status'] == 'unknown' for row in support[0]['unsupported_components'])
            if case == 'joined_cold':
                assert raw['work']['prepare_calls'] == raw['work']['geometry_parse_calls'] == 1
                assert raw['work']['raster_attempts'] == len(raw['frames']) == 3
                indexes = lines(output / 'server/INDEXES.jsonl')
                assert len(indexes) == 1 and indexes[0]['actual_capture_sha256'] == capture_meta[-1]['sha256']
                cold_index = checked_sidecar(indexes[0])
                delivery.normalize_index(capture, cold_index, expected, 'joined')
                assert all(cold_index[key] == historical_index[key] for key in
                           ('regions', 'cameras', 'view_order', 'view_masks', 'classifications'))
                assert [frame['view_name'] for frame in raw['frames']] == ['SCENE', 'BACK', 'LEFT']
                cold = raw
            else:
                assert raw['work']['result_cache_hit'] is True
                assert all(raw['work'][key] == 0 for key in ('geometry_parse_calls', 'prepare_calls', 'raster_attempts'))
                assert raw['work']['frame_reuses'] == 3
                assert raw['binding'] == cold['binding'] and raw['facts'] == cold['facts']
                assert raw['frames'] == cold['frames']
            world_started = time.perf_counter_ns()
            world_check = delivery.verify_world_regions(raw, reference)
            world_closed = time.perf_counter_ns()
            world_check.update(started_ns=world_started, closed_ns=world_closed, elapsed_ns=world_closed-world_started,
                               actual_source_index_verified=True)
            historical_check = verify_historical_facts(raw, historical)
            if case == 'joined_cold':
                observations = {row['view_name']: row for row in raw['facts']['observations']}
                for frame in raw['frames']:
                    check(deadline)
                    receipt = pixels.verify_frame(capture, cold_index, frame,
                        observations[frame['view_name']]['pixel_rows'], expected, 'joined', reference=reference)
                    assert receipt['passed'] is True and receipt['locations_checked'] == 138
                    result['pixel_checks'].append({'representation': 'joined', 'view': frame['view_name'], 'receipt': receipt})
                    save(output / 'pixels' / ('joined_' + frame['view_name'] + '.json'), receipt)
                result['location_questions'] = verify_location_questions(consumed['text'], questions, capture, delivery)
            text_budget_passed = case == 'cached_full' or decoded['text_UTF8_bytes'] <= BRIEF_TEXT_LIMIT
            result['brief_text_budget_passed'] &= text_budget_passed
            row = {'case': case, 'representation': 'joined', 'started_ns': mark,
                   'consumer_read_closed_ns': consumed['closed_ns'],
                   'elapsed_to_consumer_ns': consumed['closed_ns'] - mark,
                   'validation_started_ns': validation_started, 'validation_closed_ns': time.perf_counter_ns(),
                   'actual_service_result': result_meta[-1], 'actual_capture': capture_meta[-1],
                   'delivery': decoded, 'geometry': geometry_check, 'world_locations': world_check,
                   'historical_facts': historical_check, 'work': raw['work'],
                   'text_budget_passed': text_budget_passed, 'brief_text_limit': BRIEF_TEXT_LIMIT}
            result['requests'].append(row)
            save(output / 'progress' / (case + '.json'), row)
        intents = lines(external / 'run/render_budget/INTENTS.jsonl')
        count = len(list((external / 'run/render_budget').glob('attempt_*')))
        assert count == len(intents) and count - budget_start_count == len(cold['frames']) == 3 and count <= 4
        assert [row['attempt'] for row in intents] == list(range(1, count + 1))
        assert len(client.records) == 5 and len(lines(output / 'server/INDEXES.jsonl')) == 1
        native_blocks = sum(len(row['delivery']['native_images']) for row in result['requests'])
        assert native_blocks == 9
        result.update(new_raster_attempts=count - budget_start_count, global_charged_raster_attempts=count,
                      completed_new_frames=3, total_native_image_blocks=native_blocks, global_raster_hard_cap=4,
                      expected_active_calls=3, actual_protocol_requests=5, semantic_checks_passed=True)
        guard.verify_loaded()
        result['passed'] = result['brief_text_budget_passed']
        if not result['brief_text_budget_passed']:
            result['admission_failure'] = 'brief_text_budget_exceeded_after_complete_semantic_validation'
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
                    or finish['capture_calls'] != 3 or finish['prepare_calls'] != 1 or finish['observe_calls'] != 3):
                result['passed'] = False
        except BaseException as exc:
            cleanup_errors.append({'stage': 'server_terminal_receipt', 'type': type(exc).__name__, 'message': str(exc)})
        result['cleanup_errors'] = cleanup_errors
        if cleanup_errors:
            result['passed'] = False
        charged_slots = sorted((external / 'run/render_budget').glob('attempt_*'))
        result['global_charged_raster_attempts'] = len(charged_slots)
        result['new_raster_attempts'] = len(charged_slots) - budget_start_count
        result['global_raster_hard_cap'] = 4
        result['charged_attempt_directories'] = [str(path) for path in charged_slots]
        result['closed_before_publication_ns'] = time.perf_counter_ns()
        result['final_RESULTS_publication_included_in_internal_clock'] = False
        save(output / 'RESULTS.json', result)
    print(json.dumps({'passed': result['passed'], 'requests': len(result['requests']), 'error': result.get('error')}), flush=True)
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

"""One owned formal-backend smoke with three actual compact relation calls."""

import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import time
import traceback
import types


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
ACTOR = ROOT / 'verification/m4_local_relation_consumption_001/runtime/actor.py'
NATIVE = ROOT / 'verification/native_plugin_complex_003/reused/accepted_native.py'
CLIENT = ROOT / 'verification/m1_task_entry_001_eval/preflight_client.py'
SOURCE = '4ebc3910652ee461d9fa7476c8df0ecf6312580d6a02e1066c0eac88bef5c76c'
PREFIX = 'HUMAN_EYE_BLENDER_MCP:'
SELECTED = ('N16', 'N28')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def load(name, path):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(Path(path).read_bytes(), str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def events(path):
    return [json.loads(line) for line in path.read_bytes().splitlines() if line] if path.exists() else []


def parameters(mode):
    value = {'target': {'name': 'N16'}, 'candidates': [{'name': name} for name in ('N13', 'N08', 'N28')]}
    if mode != 'OFF':
        value['geometry'] = {'objects': [{'name': name} for name in SELECTED],
                             'include_triangles': mode == 'full'}
    return {'name': 'human_eye_spatial_relations', 'arguments': value}


def capture_proof(native, sequence, body, resources, original_state):
    folder = native.workspace / ('call_' + str(sequence))
    script = (folder / 'SCRIPT.py').read_text(encoding='utf8')
    request_node = next(node for node in ast.parse(script).body if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == '_request' for target in node.targets))
    request = json.loads(ast.literal_eval(request_node.value.args[0]))
    assert request['command'] == 'capture_task'
    assert request['params']['selectors'] == [{'name': name} for name in ('N16', 'N13', 'N08', 'N28')]
    stdout = (folder / 'stdout.txt').read_text(encoding='utf8')
    envelopes = [json.loads(line[len(PREFIX):]) for line in stdout.splitlines() if line.startswith(PREFIX)]
    assert len(envelopes) == 1 and envelopes[0]['id'] == request['id']
    packet = envelopes[0]['result']
    assert packet['schema'] == 'human-eye-scene-delta-v1'
    scene = packet['capture']
    assert scene['unit'] == 'm' and scene['coordinate_frame'] == 'world'
    assert scene['revision'] == body['context']['scene_revision']
    state = scene['capture_state']
    if original_state is not None:
        assert state == original_state and packet['resources'] == []
    for resource in packet['resources']:
        resources[resource['id']] = resource
    assert set(packet['live_resources']) == set(resources)
    public = [body['target'], *body['candidates']]
    host = scene['host_identity']
    assert host['document_epoch'] == body['context']['host_identity']['document_epoch']
    assert set(host['object_instances']) == {item['object_id'] for item in public}
    for item in public:
        assert item['instance_id'] == host['object_instances'][item['object_id']]
    geometry = []
    for name in SELECTED:
        mesh = next(item for item in scene['meshes'] if item['name'] == name)
        reference = mesh['_scene_resource']
        resource = resources[reference['id']]
        assert resource['revision'] == reference['revision']
        matrix, scale = reference['matrix'], reference['scale']
        world = [[(sum(matrix[r][c] * point[c] for c in range(3)) + matrix[r][3]) * scale
                  for r in range(3)] for point in resource['vertices_local']]
        triangles = resource['faces']
        assert all(len(face) == 3 and all(type(index) is int and 0 <= index < len(world)
                                        for index in face) for face in triangles)
        geometry.append({'object_id': mesh['object_id'], 'name': name,
                         'vertices_world': world, 'triangles': triangles})
    return {'capture_state': state, 'scene_revision': scene['revision'],
            'expected_objects_from_actual_capture': geometry,
            'capture_envelope': envelopes[0], 'script_memory_sha256': sha(script.encode('utf8')),
            'script_file_sha256': sha((folder / 'SCRIPT.py').read_bytes()),
            'stdout_file_sha256': sha((folder / 'stdout.txt').read_bytes())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    assert Path(args.output).name == args.output and args.output not in ('.', '..')
    bindings = read(HERE / 'INPUT_BINDINGS.json')
    for relative, digest in bindings['source_files_sha256'].items():
        assert sha((ROOT / relative).read_bytes()) == digest
    ready = read(BATCH / 'installation/READY.json')
    assert ready['source_sha256'] == SOURCE and ready['source_count'] == 137
    output = HERE / args.output
    output.mkdir(exist_ok=False)
    save(output / 'FIXED_INPUTS.json', bindings)
    actor = load('_selected_geometry_formal_peer', ACTOR)
    helper = load('_selected_geometry_original_native', NATIVE)
    client = load('_selected_geometry_runtime_proof', CLIENT)
    assert 'setprofile' not in NATIVE.read_text(encoding='utf8')
    began = time.perf_counter_ns()
    deadline = began + 570 * 10**9
    result = {'rows': [], 'errors': [], 'started_ns': began,
              'product_close': None, 'native_close': None, 'product_runtime_exit': {'confirmed': False}}
    peer = native = runtime_handle = None
    try:
        save(HERE / 'OWNED_START.json', {'reserved_ns': time.perf_counter_ns(), 'maximum_starts': 1,
                                       'output': str(output), 'scope': 'one attempt, failure retained'})
        native = helper.NativeSession.start(blender='D:/Tools/blender5.2/blender.exe',
            asset=ROOT / bindings['asset'], workspace=output / 'native', deadline_ns=deadline,
            condition='P', expected_asset_sha256=bindings['asset_sha256'], max_calls=128)
        config = {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
                  'project_root': ready['install_root'], 'state_file': str(output / 'state.json'),
                  'audit_file': str(output / 'audit.jsonl'), 'request_budget_s': 30.,
                  'expected_identity': {'source_sha256': SOURCE},
                  'blender': {'host': native.host, 'port': native.port, 'timeout_s': 30.}}
        save(output / 'product_config.json', config)
        peer = actor.Peer(dict(ready, group='P', product_config=output / 'product_config.json'), output / 'product')
        initialized = peer.call({'jsonrpc': '2.0', 'id': 'init', 'method': 'initialize', 'params': {
            'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'selected-geometry-smoke', 'version': '001'}}})
        identity = initialized['result']['_meta']['human_eye']
        assert identity['source_sha256'] == SOURCE and identity['source_kind'] == 'installed_distribution'
        assert identity['distribution_version'] == ready['version']
        save(output / 'ACTUAL_INITIALIZE.json', initialized)
        peer.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        listing = peer.call({'jsonrpc': '2.0', 'id': 'list', 'method': 'tools/list'})
        assert {tool['name'] for tool in listing['result']['tools']} == {'human_eye_spatial_relations', 'human_eye_surface_nearest'}
        save(output / 'ACTUAL_TOOLS.json', listing)
        save(output / 'PUBLIC_TOOLS.json', listing['result']['tools'])
        assert peer.call({'jsonrpc': '2.0', 'id': 'ping', 'method': 'ping'})['result'] == {}
        assert len(peer.records) == 4 and events(native.workspace / 'WORKER_EVENTS.jsonl') == []
        pids = {item['trace']['pid'] for item in events(output / 'audit.jsonl') if item.get('event') == 'request_trace'}
        assert len(pids) == 1
        proof, runtime_handle = client._windows_runtime_proof(peer.process, pids.pop(), deadline)
        save(output / 'PRODUCT_RUNTIME_PROOF.json', proof)
        assert proof['confirmed'] is True
        reference = original_state = None
        resources = {}
        for sequence, mode in enumerate(('OFF', 'vertices', 'full'), 1):
            request = {'jsonrpc': '2.0', 'id': mode, 'method': 'tools/call', 'params': parameters(mode)}
            row = {'mode': mode, 'sequence': sequence, 'request': request, 'started_ns': time.perf_counter_ns()}
            result['rows'].append(row)
            response = peer.call(request)
            row['ended_ns'] = time.perf_counter_ns()
            row['stdio'] = copy.deepcopy(peer.records[-1])
            row['response'] = response
            assert response['result']['isError'] is False
            body = json.loads(response['result']['content'][0]['text'])
            row['body'] = body
            assert body['status'] == 'observed' and body['execution_authority'] is False
            assert body['context']['runtime_source_sha256'] == SOURCE
            current = {key: value for key, value in body.items() if key not in ('trace_id', 'geometry')}
            if reference is None:
                reference = current
            else:
                assert current == reference
            assert ('geometry' in body) == (mode != 'OFF')
            worker = events(native.workspace / 'WORKER_EVENTS.jsonl')
            assert len(worker) == sequence
            event = worker[-1]
            assert event['sequence'] == sequence and event['status'] == 'completed'
            assert row['started_ns'] <= event['started_ns'] <= row['ended_ns']
            assert event['terminal_geometry_and_file_checks_passed'] and 'qa_work' not in event
            capture = capture_proof(native, sequence, body, resources, original_state)
            row['capture_proof'] = capture
            original_state = capture['capture_state']
            assert capture['script_memory_sha256'] == event['script_sha256']
            if mode != 'OFF':
                expected = copy.deepcopy(capture['expected_objects_from_actual_capture'])
                if mode == 'vertices':
                    for item in expected:
                        item.pop('triangles')
                assert body['geometry']['objects'] == expected
            save(output / (mode + '.json'), row)
    except BaseException as exc:
        result['errors'].append({'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()})
    finally:
        if peer is not None:
            try:
                result['product_close'] = peer.close()
            except BaseException as exc:
                result['errors'].append({'stage': 'product_close', 'error': repr(exc)})
        try:
            result['product_runtime_exit'] = client._runtime_exit(runtime_handle)
            if runtime_handle is not None:
                exited = result['product_runtime_exit']
                assert exited['confirmed'] and exited['exited'] and exited['exit_code'] == 0 and exited['handle_closed']
        except BaseException as exc:
            result['product_runtime_exit'] = {'confirmed': False, 'error': repr(exc)}
            result['errors'].append({'stage': 'product_runtime_exit', 'error': repr(exc)})
        if native is not None:
            try:
                result['native_close'] = native.close()
                result['worker_closed'] = native.status()['closed']
                close = result['native_close']
                closed = result['worker_closed']
                assert close['response']['status'] == 'closed' and close['error'] is None
                assert close['exit_code'] == 0 and close['process_reaped']
                assert close['source_file_unchanged'] and close['protected_files_unchanged']
                assert not closed['poisoned'] and closed['final_geometry_fingerprint'] == closed['initial_geometry_fingerprint']
                assert closed['pid'] == native.ready['pid'] == native.process.pid
                worker = events(native.workspace / 'WORKER_EVENTS.jsonl')
                result['worker_events'] = worker
                assert len(worker) == 4 and [event['sequence'] for event in worker] == [1, 2, 3, 4]
                assert all('qa_work' not in event for event in worker)
                for event in worker:
                    assert not event.get('changed_or_new_PNG_files')
                    assert event.get('event') not in ('render_started', 'render_completed', 'render_cancelled')
                    if 'render_events_after' in event:
                        assert event['render_events_after'] == event['render_events_before']
            except BaseException as exc:
                result['errors'].append({'stage': 'native_close', 'error': repr(exc)})
        try:
            observations = [event['task_work'] for event in events(output / 'audit.jsonl')
                            if event.get('event') == 'observe']
            result['task_work'] = observations
            if not result['errors']:
                assert len(observations) == 3
                assert [work['result_cache_hit'] for work in observations] == [False, True, True]
                for work in observations[1:]:
                    assert all(work[key] == 0 for key in
                               ('exact_pair_count', 'surface_pair_count', 'closed_solid_pair_count'))
        except BaseException as exc:
            result['errors'].append({'stage': 'cached_relation_facts', 'error': repr(exc)})
        result['ended_ns'] = time.perf_counter_ns()
        result['source_checks'] = {relative: sha((ROOT / relative).read_bytes()) == digest
                                   for relative, digest in bindings['source_files_sha256'].items()}
        result['passed'] = bool(not result['errors'] and len(result['rows']) == 3
            and result['product_close'] and result['product_close']['confirmed']
            and result['product_runtime_exit']['confirmed'] is True and result['native_close']
            and result['ended_ns'] < deadline and all(result['source_checks'].values()))
        result['scope'] = 'one formal-backend engineering smoke; original worker, no QA profiler or native supplement'
        result['model_consumers'] = 0
        save(output / 'RESULTS.json', result)
    print(json.dumps({'passed': result['passed'], 'output': str(output), 'owned_starts': 1}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

"""Owned actual-MCP directory samples and an independent selected-task pair."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import traceback
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD_READY = ROOT / 'verification/m4_selected_geometry_consumption_001/installation/READY.json'
ACTOR = ROOT / 'verification/m1_task_entry_001_eval/actor.py'
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def load(name, path):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(Path(path).read_bytes(), str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def rows(path):
    return [json.loads(line) for line in path.read_bytes().splitlines() if line] if path.exists() else []


def request(mode, label):
    query = ({'mode': 'overview', 'native_visual': {'mode': 'projection'}} if mode == 'overview'
             else {'mode': 'directory'} if mode == 'directory'
             else {'mode': 'task', 'objects': [{'name': 'M4_Focal'}, {'name': 'M4_Near'}],
                   'requested_facts': ['aabb', 'axis_gap', 'surface_proximity']})
    return {'jsonrpc': '2.0', 'id': label, 'method': 'tools/call', 'params': {
        'name': 'human_eye_scene_observe', 'arguments': {
            'session_id': 'm2-tight-directory', 'include_image': False, 'query': query}}}


def directory_facts(body, mode):
    if mode == 'overview':
        facts = json.loads(body['routing']['context_text'])
        objects = facts['objects']
        return [{'object_id': item['object_id'], 'name': item['name'],
                 'bbox_min': item['bbox_min'], 'bbox_max': item['bbox_max'],
                 'center': [(a+b)*.5 for a,b in zip(item['bbox_min'], item['bbox_max'])]}
                for item in objects]
    return body['objects']


def run(asset, ready, output, mode, warm_count, two_step):
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter_ns()
    result = {'asset': asset['name'], 'mode': mode, 'rows': [], 'errors': [], 'started_ns': started}
    native = peer = None
    helper = load('_m2_owned_native', HERE / 'owned_native.py')
    actor = load('_m2_actual_peer', ACTOR)
    try:
        native = helper.NativeSession.start(blender='D:/Tools/blender5.2/blender.exe', asset=asset['asset'],
            workspace=output / 'native', deadline_ns=started + 570*10**9, condition='P',
            expected_asset_sha256=asset['asset_sha256'], max_calls=128)
        config = {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
            'project_root': ready['install_root'], 'state_file': str(output/'state.json'),
            'audit_file': str(output/'audit.jsonl'), 'request_budget_s': 30.,
            'expected_identity': {'source_sha256': ready['source_sha256']},
            'blender': {'host': native.host, 'port': native.port, 'timeout_s': 30.}}
        save(output/'config.json', config)
        peer = actor.Peer(dict(ready, group='C', product_config=output/'config.json'), output/'product')
        initialized = peer.call({'jsonrpc':'2.0','id':'init','method':'initialize','params':{
            'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'m2-owned-measurement','version':'001'}}})
        assert initialized['result']['_meta']['human_eye']['source_sha256'] == ready['source_sha256']
        save(output/'ACTUAL_INITIALIZE.json', initialized)
        peer.call({'jsonrpc':'2.0','method':'notifications/initialized'})
        tools = peer.call({'jsonrpc':'2.0','id':'list','method':'tools/list'})
        save(output/'ACTUAL_TOOLS.json', tools)
        assert peer.call({'jsonrpc':'2.0','id':'ping','method':'ping'})['result'] == {}
        assert rows(native.workspace/'WORKER_EVENTS.jsonl') == []
        modes = [mode, 'task'] if two_step else [mode] * (warm_count+1)
        expected = {row['name']: row for row in asset['oracle']}
        for index, selected_mode in enumerate(modes):
            message = request(selected_mode, 'read_'+str(index))
            began = time.perf_counter_ns()
            answer = peer.call(message)
            ended = time.perf_counter_ns()
            row = {'index': index, 'mode': selected_mode, 'request': message, 'started_ns': began,
                   'ended_ns': ended, 'tool_ns': ended-began, 'stdio': dict(peer.records[-1]), 'response': answer}
            result['rows'].append(row)
            assert answer['result']['isError'] is False, answer
            body = json.loads(answer['result']['content'][0]['text'])
            row['body'] = body
            row['visible_text_UTF8_bytes'] = sum(len(block.get('text','').encode('utf8')) for block in answer['result']['content'])
            if selected_mode != 'task':
                actual = directory_facts(body, selected_mode)
                row['directory_facts'] = actual
                assert {item['name'] for item in actual} == set(expected)
                for item in actual:
                    for key in ('bbox_min','bbox_max','center'):
                        assert item[key] == expected[item['name']][key], (item['name'],key)
            save(output/('READ_'+str(index)+'.json'), row)
    except BaseException as exc:
        result['errors'].append({'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()})
    finally:
        if peer is not None:
            try: result['product_close'] = peer.close()
            except BaseException as exc: result['errors'].append({'stage':'product_close','error':repr(exc)})
        if native is not None:
            try:
                result['native_close'] = native.close()
                result['closed'] = native.status()['closed']
                assert result['native_close']['response']['status'] == 'closed'
                assert result['native_close']['exit_code'] == 0 and result['native_close']['process_reaped']
                assert not result['closed']['poisoned']
                assert result['closed']['final_geometry_fingerprint'] == result['closed']['initial_geometry_fingerprint']
                result['worker_events'] = rows(native.workspace/'WORKER_EVENTS.jsonl')
                result['wire'] = json.loads((native.workspace/'WIRE/INDEX.json').read_bytes())
                for row in result['rows']:
                    received = [event for event in result['worker_events'] if type(event.get('started_ns')) is int
                                and row['started_ns'] <= event['started_ns'] <= row['ended_ns']]
                    row['host_RPC'] = len(received)
                    row['work_events'] = received
                    row['wire'] = [value for value in result['wire'] if value['sequence'] in {event['sequence'] for event in received}]
                    assert row['host_RPC'] >= 1
            except BaseException as exc: result['errors'].append({'stage':'native_close_or_meter','error':repr(exc)})
        result['audit'] = rows(output/'audit.jsonl')
        result['ended_ns'] = time.perf_counter_ns()
        result['passed'] = not result['errors']
        result['memory_scope'] = 'product request_trace process_lifetime peak only; worker OS/allocator peaks unmeasured'
        save(output/'RESULTS.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, choices=('simple_boxes','peripheral','rotated_asymmetric'))
    parser.add_argument('--ready', type=Path, default=OLD_READY)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--mode', choices=('overview','directory'), default='overview')
    parser.add_argument('--warm-count', type=int, default=10)
    parser.add_argument('--two-step', action='store_true')
    args = parser.parse_args()
    asset = next(row for row in json.loads((HERE/'assets_01/INPUTS.json').read_bytes())['inputs'] if row['name']==args.input)
    result = run(asset, json.loads(args.ready.read_bytes()), args.output.resolve(), args.mode, args.warm_count, args.two_step)
    print(json.dumps({'passed':result['passed'],'input':args.input,'output':str(args.output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

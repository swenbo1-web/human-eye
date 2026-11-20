"""Replay unaffected public result formats against original archived MCP traffic."""

import base64
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
BASE = PROJECT.parent / 'm4_dense_raster_cross_001/install/PRODUCT_RUN_BINDING.json'
CANDIDATE = PROJECT / 'install/PRODUCT_RUN_BINDING.json'
OLD_ASSEMBLY = Path('D:/he_m5_global_observe_measure_qualification_001/slots/A')
SOURCE_REGION = Path('D:/he_m4_live_source_region_task_003/slots/P1')
SINGLE_TARGET = Path('D:/he_m5_harness_recovery_001/sessions/B')
CASES = (
    ('region_task_without_joint', OLD_ASSEMBLY, 1, 4, 'active_observation'),
    ('standalone_surface_proximity', OLD_ASSEMBLY, 2, 5, 'task'),
    ('source_region', SOURCE_REGION, 1, 4, 'source_region'),
    ('single_target_joint', SINGLE_TARGET, 4, 8, 'active_observation'),
)


def read(path):
    return json.loads(path.read_bytes())


def json_lines(path):
    return (json.loads(line) for line in path.read_bytes().splitlines())


def pin(path):
    data = path.read_bytes()
    return {'path': str(path.resolve()), 'bytes': len(data), 'sha256': sha256(data).hexdigest()}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def original(case):
    label, slot, index, wire, mode = case
    tx, rx, receipt = (slot / 'mcp' / f'rpc_{wire:02}' / name
                       for name in ('TX.bin', 'RX.bin', 'RECEIPT.json'))
    producer_path = slot / 'product_full' / f'call_{index:03}' / 'SERVICE_RESULT.json'
    archive, requests = slot / 'product_full/INDEX.jsonl', slot / 'PUBLIC_REQUESTS.jsonl'
    request, reply, saved, producer = (read(path) for path in (tx, rx, receipt, producer_path))
    args = request['params']['arguments']
    require(request['method'] == 'tools/call' and request['params']['name'] == 'human_eye_scene_observe'
            and args['query']['mode'] == mode and request['id'] == saved['id'] == reply['id']
            and saved['error'] is None and reply['result']['isError'] is False and saved['index'] == wire
            and saved['RX_sha256'] == pin(rx)['sha256'] and saved['RX_bytes'] == rx.stat().st_size
            and saved['TX_bytes'] == tx.stat().st_size, f'original_MCP_wire_changed/{label}')
    event, = (row for row in json_lines(requests) if row['request']['id'] == request['id'])
    producer_record, = (row for row in json_lines(archive) if row['index'] == index)
    require(event['request'] == request and event['receipt'] == saved and event['response'] == reply
            and event['producer_archive'] == producer_record
            and Path(producer_record['path']).resolve() == producer_path.resolve()
            and producer_record['sha256'] == pin(producer_path)['sha256']
            and producer_record['new_observations_for_archive'] == 0, f'original_producer_binding_changed/{label}')

    query = args['query']
    if label == 'region_task_without_joint':
        require('region_task' in query and 'task_query' not in query and 'task_result' not in producer,
                'archive_does_not_cover_observe_without_joint')
    elif label == 'standalone_surface_proximity':
        require(producer['result_kind'] == 'task_query' and query['requested_facts'] == ['surface_proximity'],
                'archive_does_not_cover_standalone_measurement')
    elif label == 'source_region':
        require(producer['result_kind'] == 'source_region' and 'task_result' in producer,
                'archive_does_not_cover_source_region')
    else:
        require(len(query['objects']) == 1 and 'region_task' not in query and 'task_query' in query
                and producer['binding']['capture_scope'] == 'target_observation_meshes'
                and producer['task_result']['schema_version'] == 'task-query-v3',
                'archive_does_not_cover_single_target_joint')
    return args, reply['result'], producer, (tx, rx, receipt, producer_path, archive, requests)


def worker(binding_path):
    binding = read(binding_path)
    sys.path[:0] = [binding['install_root'], binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp

    module = Path(mcp.__file__).resolve()
    require(module.is_relative_to(Path(binding['install_root']).resolve()), 'formatter_outside_bound_install')
    outputs = {}
    for case in CASES:
        args, reply, producer, _ = original(case)
        options = {}
        if binding_path == CANDIDATE:
            options['observation_task_query'] = args['query'].get('task_query')
        outputs[case[0]] = mcp._tool_result(producer, is_error=reply['isError'],
                                          response_detail=args.get('response_detail'), **options)
    print(json.dumps({'module': pin(module), 'outputs': outputs}, ensure_ascii=True, allow_nan=False))


def main():
    base, candidate = [json.loads(subprocess.check_output(
        [sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--worker', str(binding)], timeout=45))
        for binding in (BASE, CANDIDATE)]
    pins = [pin(path) for path in (Path(__file__), BASE, CANDIDATE)] + [base['module'], candidate['module']]
    results = {}
    for case in CASES:
        label = case[0]
        _, public, _, paths = original(case)
        old, new = (trial['outputs'][label] for trial in (base, candidate))
        old_body, original_body = [reply['content'][0] for reply in (old, public)]
        require(new == old and old['isError'] is public['isError'] and old_body['type'] == original_body['type'] == 'text'
                and json.loads(old_body['text']) == json.loads(original_body['text'])
                and old['content'][1:] == public['content'][1:], f'compatibility_changed/{label}')
        results[label] = {'passed': True, 'installed_outputs_exact': True,
                          'original_JSON_facts_and_nontext_blocks_exact': True,
                          'original_text_bytes': len(original_body['text'].encode()),
                          'original_PNG_SHA256': [sha256(base64.b64decode(block['data'], validate=True)).hexdigest()
                                                   for block in public['content'][1:] if block['type'] == 'image']}
        pins.extend(pin(path) for path in paths)
    checks = {'passed': True, 'cases': results, 'live_Blender_slots': 0, 'model_runs': 0,
              'source_pins': list({row['path']: row for row in pins}.values())}
    with (HERE / 'COMPATIBILITY_OFFLINE.json').open('xb') as output:
        output.write(json.dumps(checks, indent=2, ensure_ascii=False, allow_nan=False).encode() + b'\n')
    print(f'Compatibility offline: {len(results)}/{len(CASES)} exact installed replays; zero live slots')


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'isolated_offline_interpreter_required')
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        worker(Path(sys.argv[2]))
    else:
        main()

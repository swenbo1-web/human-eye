"""Replay the actual assembly joint RFQ, and exercise projection compatibility controls."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
BASE = NS.parent / 'm4_dense_raster_cross_001/install/PRODUCT_RUN_BINDING.json'
CANDIDATE = NS / 'install/PRODUCT_RUN_BINDING.json'
ORIGINAL = Path('D:/he_m5_global_observe_measure_qualification_001/slots/B')
SAVED = ORIGINAL / 'product_full/call_001/SERVICE_RESULT.json'
REQUEST = ORIGINAL / 'product_calls/call_001/REQUEST.json'
PUBLIC = ORIGINAL / 'product_calls/call_001/RESPONSE.json'
OUTER = ORIGINAL / 'batch/rpc_03/RECEIPT.json'
sys.path.insert(0, str(HERE))
from offline_decode import VERSION, decode_task, require


def read(path):
    return json.loads(path.read_bytes())


def raw(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def pin(path):
    return {'path': str(path.resolve()), 'bytes': path.stat().st_size, 'sha256': sha256(path.read_bytes()).hexdigest()}


def measured_reversal(body, query, fingerprint):
    original = deepcopy(body)
    reversed_query = {**query, 'objects': query['objects'][::-1]}
    task = original['task_result']
    binding = task['binding']
    binding['objects'].reverse()
    value = task['facts']['surface_proximity']['value']
    witness = value['nearest_witness']
    witness['a'], witness['b'] = witness['b'], witness['a']
    witness['direction_a_to_b'] = [-x if x else x for x in witness['direction_a_to_b']]
    value['topology'].reverse()
    source = binding['observation_source']
    key = fingerprint(['observation_task', original['binding']['source_binding_sha256'],
                       reversed_query, source['objects']])
    source['capture_state']['selection_key'] = key
    binding['scene_revision'] = 'observation-task:' + key
    return original, reversed_query


def worker(binding_path):
    install = read(binding_path)
    sys.path[:0] = [install['install_root'], install['dependency_root']]
    from human_eye_plugin.active_observation import fingerprint
    from human_eye_plugin import live_spatial_mcp as mcp

    producer, message = read(SAVED), read(REQUEST)
    query = message['params']['arguments']['query']['task_query']
    is_candidate = binding_path == CANDIDATE
    only_candidate = {'observation_task_query': query} if is_candidate else {}
    formatter = mcp._tool_result
    projection = formatter(producer, is_error=False, response_detail='brief', **only_candidate)
    result = {'actual': projection, 'identities': {}, 'controls': {}}
    for label, detail, error in (('explicit_full', 'full', False), ('is_error', 'brief', True)):
        result['controls'][label] = sha256(raw(formatter(producer, is_error=error,
            response_detail=detail, **only_candidate)).encode()).hexdigest()
    mutations = {
        'unknown': (('status',), 'unknown'),
        'partial': (('status',), 'partial'),
        'measured_fact_unknown': (('facts', 'surface_proximity', 'status'), 'unknown'),
        'epoch_drift': (('binding', 'observation_source', 'capture_state', 'epoch'), 8),
        'bool_epoch': (('binding', 'observation_source', 'capture_state', 'epoch'), True),
        'float_count': (('binding', 'candidate_count'), 28.0),
        'wrong_runtime': (('binding', 'runtime_source_sha256'), 'a' * 64),
        'wrong_selection': (('binding', 'scene_revision'), 'observation-task:' + 'b' * 64),
        'alias_changed': (('binding', 'observation_source', 'objects', 0, 'geometry_id'), 'geometry:' + 'c' * 64),
        'ordered_geometry_changed': (('binding', 'observation_source', 'objects', 1, 'ordered_geometry_sha256'), 'd' * 64),
        'object_instance_changed': (('binding', 'observation_source', 'objects', 0, 'instance_id'), 'other'),
        'unmapped_object': (('binding', 'observation_source', 'objects', 0, 'observation_object_index'), None),
        'incomplete_source_range': (('binding', 'observation_source', 'objects', 0, 'source_triangle_index_ranges'), [[1, 11]]),
        'missing_bound_count': (('binding', 'candidate_count'), None),
        'wrong_parent': (('binding', 'observation_source', 'parent_binding_sha256'), 'b' * 64),
    }
    for label, (path, change) in mutations.items():
        value = deepcopy(producer)
        obj = value['task_result']
        for key in path[:-1]:
            obj = obj[key]
        obj[path[-1]] = change
        try:
            tested = formatter(value, is_error=False, response_detail='brief', **only_candidate)
            result['controls'][label] = sha256(raw(tested).encode()).hexdigest()
        except ValueError as error:
            result['controls'][label] = {'rejected': str(error)}
    if is_candidate:
        rev, reversed_query = measured_reversal(producer, query, fingerprint)
        reversed_wire = formatter(rev, is_error=False, response_detail='brief', observation_task_query=reversed_query)
        reversed_body = json.loads(reversed_wire['content'][0]['text'])
        require(decode_task(reversed_body) == rev['task_result'], 'reversed_measurement_did_not_restore_original')
        compact = reversed_body['task_result']['binding']
        order = compact['object_indices']
        require(order == [21, 13] and [row[0] for row in compact['sources']['rows']] == [13, 21],
                'measurement_order_not_independent_of_capture_row_order')
        same_name = deepcopy(producer)
        parent = same_name['binding']
        task = same_name['task_result']
        for row in (parent['objects'][13], parent['objects'][21]):
            row['object_name'] = 'Shared Name'
        for row in task['binding']['objects']:
            row['name'] = 'Shared Name'
        same_query = {**query, 'objects': [{'id': row['object_id']} for row in task['binding']['objects']]}
        sources = task['binding']['observation_source']['objects']
        key = fingerprint(['observation_task', parent['source_binding_sha256'], same_query, sources])
        task['binding']['observation_source']['capture_state']['selection_key'] = key
        task['binding']['scene_revision'] = 'observation-task:' + key
        verified = mcp._project_region_task_measurement(task, parent, same_name['facts']['scope']['patch_support'],
                                                      same_name['facts']['region_task']['rows'], same_query)
        require(verified['binding']['object_indices'] == [13, 21], 'same_name_objects_not_joined_by_identity')
        result['identities'] = {'reversed_order': order,
             'capture_source_order': [row[0] for row in compact['sources']['rows']],
             'same_named_objects_resolved_by_id_and_instance': True}
    print(raw(result))


def main():
    actual = read(PUBLIC)['result']
    original_outer = read(OUTER)['response']['result']
    old, new = [json.loads(subprocess.check_output([sys.executable, '-I', '-B', str(Path(__file__).resolve()),
             '--worker', str(path)], timeout=45)) for path in (BASE, CANDIDATE)]
    require(json.loads(old['actual']['content'][0]['text']) == json.loads(actual['content'][0]['text'])
            and old['actual']['content'][1:] == actual['content'][1:]
            and old['controls'] == new['controls'], 'original_replay_or_legacy_control_changed')
    result = new['actual']
    prior, compact = [json.loads(value['content'][0]['text']) for value in (actual, result)]
    require(compact['task_result']['schema_version'] == VERSION and decode_task(compact) == prior['task_result']
            and {k: v for k, v in prior.items() if k != 'task_result'} ==
                {k: v for k, v in compact.items() if k != 'task_result'}
            and result['content'][1:] == actual['content'][1:], 'entire_legacy_measurement_did_not_restore')
    outer = deepcopy(original_outer)
    text = outer['content'][0]['text']
    wrapped = json.loads(text)
    require(wrapped['stdout'] == 'M5_GLOBAL_JOINT:' + raw(prior) + '\n'
            and raw(wrapped) == text and original_outer['content'][1:] == actual['content'][1:],
            'original_outer_format_not_bound')
    wrapped['stdout'] = 'M5_GLOBAL_JOINT:' + raw(compact) + '\n'
    outer['content'][0]['text'] = raw(wrapped)
    from live_wire_adapter import replay
    receipt = {'passed': True, 'dense': False, 'controls': old['controls'], 'identity_controls': new['identities'],
        'raw_task_reconstituted_exactly': True, 'old_public_bytes': len(actual['content'][0]['text'].encode()),
        'new_public_bytes': len(result['content'][0]['text'].encode()), 'old_outer_bytes': len(text.encode()),
        'new_outer_bytes': len(outer['content'][0]['text'].encode()),
        'public_replay': replay(result), 'outer_replay': replay(outer),
        'source_pins': [pin(path) for path in (*map(Path, (BASE, CANDIDATE, SAVED, REQUEST, PUBLIC, OUTER)),
            Path(__file__), HERE / 'offline_decode.py', HERE / 'live_wire_adapter.py')]}
    require(receipt['new_outer_bytes'] <= 10800 and receipt['public_replay']['passed'] and
            receipt['outer_replay']['passed'], 'assembly_fixed_cli_or_outer_size_gate_failed')
    with (HERE / 'ASSEMBLY_OFFLINE.json').open('xb') as output:
        output.write(json.dumps(receipt, indent=2, ensure_ascii=False, allow_nan=False).encode() + b'\n')
    print('Assembly offline', receipt['old_public_bytes'], receipt['new_public_bytes'],
          receipt['old_outer_bytes'], receipt['new_outer_bytes'])


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'isolated_offline_interpreter_required')
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        worker(Path(sys.argv[2]))
    else:
        main()

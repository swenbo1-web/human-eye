"""Fixed seven-session installed stdio and owned-Blender engineering check."""

import argparse
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
BASE = ROOT / 'verification/m4_observation_baseline_001'
BASELINE_READY = ROOT / 'verification/m4_local_relation_evidence_001/installation/READY.json'
ACTOR = ROOT / 'verification/m1_task_entry_001_eval/actor.py'
BASE_SHA = '53db41976085ce5f361d026196f4da5faf80d639af33dfced35ba58e328ef732'
CANDIDATE_SHA = '9f287f28a9be9ad0a06c0689b1fda3b15e9181efae0e280c0f2bcfed2d3ef504'
ASSET_SHA = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
BLENDER = 'D:/Tools/blender5.2/blender.exe'
MODES = ('OFF', 'vertices', 'full')
GEOMETRY_NAMES = ('N16', 'N28')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf8')


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def load(name, path):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(Path(path).read_bytes(), str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def events(path):
    return [json.loads(line) for line in path.read_bytes().splitlines() if line] if path.exists() else []


def arguments(mode):
    value = {'target': {'name': 'N16'},
             'candidates': [{'name': name} for name in ('N13', 'N08', 'N28')]}
    if mode != 'OFF':
        value['geometry'] = {'objects': [{'name': name} for name in GEOMETRY_NAMES],
                             'include_triangles': mode == 'full'}
    return value


def core(body):
    return {key: value for key, value in body.items() if key not in ('geometry', 'trace_id')}


def native_script(body, retain_oracle):
    ids = {row['name']: row['object_id'] for row in [body['target'], *body['candidates']]}
    selection = [(name, ids[name]) for name in GEOMETRY_NAMES]
    return '''import json
_qa_native_supplement_work = dict(to_mesh=0, triangulations=0, world_preparations=0, vertices_mapped=0)
_qa_rows = []
_qa_oracle = []
_qa_graph = bpy.context.evaluated_depsgraph_get()
_qa_scale = float(bpy.context.scene.unit_settings.scale_length)
for _qa_name, _qa_id in ''' + repr(selection) + ''':
    _qa_object = bpy.data.objects[_qa_name]
    _qa_eval = _qa_object.evaluated_get(_qa_graph)
    _qa_mesh = _qa_eval.to_mesh()
    _qa_native_supplement_work['to_mesh'] += 1
    try:
        _qa_mesh.calc_loop_triangles()
        _qa_native_supplement_work['triangulations'] += 1
        _qa_local = [[float(x) for x in v.co] for v in _qa_mesh.vertices]
        _qa_matrix = [[float(x) for x in row] for row in _qa_eval.matrix_world]
        _qa_world = [[(sum(_qa_matrix[r][c] * p[c] for c in range(3)) + _qa_matrix[r][3]) * _qa_scale
                      for r in range(3)] for p in _qa_local]
        _qa_native_supplement_work['world_preparations'] += 1
        _qa_native_supplement_work['vertices_mapped'] += len(_qa_world)
        _qa_triangles = [[int(x) for x in tri.vertices] for tri in _qa_mesh.loop_triangles]
        _qa_rows.append(dict(object_id=_qa_id, name=_qa_name, vertices_world=_qa_world, triangles=_qa_triangles))
        if ''' + repr(retain_oracle) + ''':
            _qa_oracle.append(dict(name=_qa_name, vertices_local=_qa_local, matrix_world=_qa_matrix,
                                   unit_scale_m=_qa_scale, triangles=_qa_triangles,
                                   instance_id=str(getattr(_qa_object, 'session_uid', _qa_object.as_pointer())),
                                   data_users=[o.name for o in bpy.data.objects if o.type == 'MESH' and o.data is _qa_object.data]))
    finally:
        _qa_eval.to_mesh_clear()
if ''' + repr(retain_oracle) + ''':
    _qa_native_supplement_work['independent_host_oracle'] = _qa_oracle
print(json.dumps(dict(objects=_qa_rows, contract=dict(
    vertices_world='current_evaluated_vertices_world_metres_in_captured_order',
    triangles='zero_based_triplets_index_vertices_world_in_captured_order')), separators=(',', ':'), allow_nan=False))
'''


def supplement(native, body, folder, label, retain_oracle):
    script = native_script(body, retain_oracle)
    (folder / (label + '.py')).write_text(script, encoding='utf8', newline='\n')
    began = time.perf_counter_ns()
    receipt = native.run(script, timeout_s=30)
    ended = time.perf_counter_ns()
    save(folder / (label + '.RECEIPT.json'), receipt)
    raw = receipt['response']
    assert raw['status'] == 'success'
    geometry = json.loads(raw['result']['result'])
    save(folder / (label + '.GEOMETRY.json'), geometry)
    return {'kind': 'native_supplement', 'label': label, 'started_ns': began, 'ended_ns': ended,
            'entry_elapsed_ns': ended - began, 'receipt': receipt,
            'geometry': geometry, 'body_utf8_bytes': len(raw['result']['result'].encode('utf8')),
            'native_envelope_utf8_bytes': len(encoded(raw)), 'oracle_retained': retain_oracle}


def relation(peer, mode, folder, label, expected_source):
    request = {'jsonrpc': '2.0', 'id': label, 'method': 'tools/call',
               'params': {'name': 'human_eye_spatial_relations', 'arguments': arguments(mode)}}
    began = time.perf_counter_ns()
    response = peer.call(request)
    ended = time.perf_counter_ns()
    assert response['result']['isError'] is False
    body = json.loads(response['result']['content'][0]['text'])
    assert body['status'] == 'observed' and body['execution_authority'] is False
    assert body['context']['runtime_source_sha256'] == expected_source
    assert body['context']['unit'] == 'm' and body['context']['coordinate_frame'] == 'world'
    assert ('geometry' in body) == (mode != 'OFF')
    if mode != 'OFF':
        assert [row['name'] for row in body['geometry']['objects']] == list(GEOMETRY_NAMES)
        assert all(('triangles' in row) == (mode == 'full') for row in body['geometry']['objects'])
    save(folder / (label + '.REQUEST.json'), request)
    save(folder / (label + '.RESPONSE.json'), response)
    return {'kind': 'relation', 'label': label, 'mode': mode, 'started_ns': began, 'ended_ns': ended,
            'entry_elapsed_ns': ended - began, 'stdio': copy.deepcopy(peer.records[-1]), 'body': body,
            'text_utf8_bytes': len(response['result']['content'][0]['text'].encode('utf8')),
            'per_field_compact_JSON_bytes': {key: len(encoded(value)) for key, value in body.items()}}


def reserve(case, folder):
    ledger = HERE / 'OWNED_STARTS.jsonl'
    previous = events(ledger)
    assert len(previous) < 10, 'ten_owned_start_cap_including_failed_setups'
    row = {'ordinal': len(previous) + 1, 'case': case, 'folder': str(folder),
           'reserved_ns': time.perf_counter_ns()}
    with ledger.open('a', encoding='utf8', newline='\n') as stream:
        stream.write(json.dumps(row, sort_keys=True) + '\n')
    return row


def enrich(rows, folder):
    worker = events(folder / 'native/WORKER_EVENTS.jsonl')
    audit = events(folder / 'audit.jsonl')
    observations = [row['task_work'] for row in audit if row.get('event') == 'observe']
    traces = {row['trace']['annotations'].get('mcp_request_id'): row['trace']
              for row in audit if row.get('event') == 'request_trace'}
    relation_rows = [row for row in rows if row['kind'] == 'relation']
    assert len(observations) == len(relation_rows)
    for row, work in zip(relation_rows, observations, strict=True):
        row['task_work'] = work
        trace = traces[row['label']]
        row['request_trace'] = trace
        row['successful_normalize_hash_spans'] = sum(span['name'] == 'scene.hash'
            and span['outcome'] == 'completed' for span in trace['spans'])
    for row in rows:
        received = [event for event in worker if type(event.get('started_ns')) is int
                    and row['started_ns'] <= event['started_ns'] <= row['ended_ns']]
        row['worker_received_RPC_count'] = len(received)
        row['worker_received_events'] = received
    return worker


def run_case(case, ready, folder, peer_class, native_class):
    folder.mkdir(parents=True, exist_ok=False)
    began = time.perf_counter_ns()
    result = {'case': case, 'started_ns': began, 'rows': [], 'errors': [],
              'product_close': None, 'native_close': None}
    peer = native = None
    try:
        result['start_reservation'] = reserve(case, folder)
        native = native_class.start(blender=BLENDER, asset=BASE / 'input/scene.blend',
            workspace=folder / 'native', deadline_ns=began + 570 * 10**9, condition='P',
            expected_asset_sha256=ASSET_SHA, max_calls=128,
            qa_vertex_patch=HERE / 'MUTATION_PATCH.json' if case['mutation'] else None,
            qa_initial_rigid=case['transformed'])
        config = {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
                  'project_root': ready['install_root'], 'state_file': str(folder / 'state.json'),
                  'audit_file': str(folder / 'audit.jsonl'), 'request_budget_s': 30.,
                  'expected_identity': {'source_sha256': ready['source_sha256']},
                  'blender': {'host': native.host, 'port': native.port, 'timeout_s': 30.}}
        save(folder / 'product_config.json', config)
        peer = peer_class(dict(ready, group='S', product_config=folder / 'product_config.json'), folder / 'product')
        initialized = peer.call({'jsonrpc': '2.0', 'id': 'init', 'method': 'initialize', 'params': {
            'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'selected-evidence-QA', 'version': '001'}}})
        identity = initialized['result']['_meta']['human_eye']
        assert identity['source_sha256'] == ready['source_sha256']
        assert identity['source_kind'] == 'installed_distribution' and identity['distribution_version'] == ready['version']
        save(folder / 'ACTUAL_INITIALIZE.json', initialized)
        peer.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        listing = peer.call({'jsonrpc': '2.0', 'id': 'list', 'method': 'tools/list'})
        save(folder / 'ACTUAL_TOOLS.json', listing)
        tools = listing['result']['tools']
        assert {tool['name'] for tool in tools} == {'human_eye_spatial_relations', 'human_eye_surface_nearest'}
        result['tool_schema_compact_JSON_bytes'] = {tool['name']: len(encoded(tool)) for tool in tools}
        peer.call({'jsonrpc': '2.0', 'id': 'ping', 'method': 'ping'})
        cold = relation(peer, case['cold_mode'], folder, 'cold', ready['source_sha256'])
        result['rows'].append(cold)
        cold_oracle = supplement(native, cold['body'], folder, 'cold_oracle', True)
        result['rows'].append(cold_oracle)
        reference = core(cold['body'])
        for cycle in range(1 if case['transformed'] else 5):
            order = ('OFF',) if case['role'] == 'baseline' else MODES[cycle % 3:] + MODES[:cycle % 3]
            for mode in order:
                label = 'warm_' + str(cycle + 1) + '_' + mode
                row = relation(peer, mode, folder, label, ready['source_sha256'])
                assert core(row['body']) == reference
                result['rows'].append(row)
                if mode == 'OFF' and not case['transformed']:
                    if case['role'] == 'baseline':
                        row = relation(peer, 'OFF', folder, label + '_comparison', ready['source_sha256'])
                        assert core(row['body']) == reference
                        result['rows'].append(row)
                    readback = supplement(native, row['body'], folder, label + '_supplement', False)
                    assert readback['geometry'] == cold_oracle['geometry']
                    result['rows'].append(readback)
                if mode != 'OFF':
                    expected = copy.deepcopy(cold_oracle['geometry'])
                    if mode == 'vertices':
                        for item in expected['objects']:
                            item.pop('triangles')
                        expected['contract'].pop('triangles')
                    assert row['body']['geometry'] == expected
        if case['cold_mode'] == 'full':
            assert cold['body']['geometry'] == cold_oracle['geometry']
        if case['mutation']:
            mutation_began = time.perf_counter_ns()
            receipt = native.qa_advance(timeout_s=30)
            result['rows'].append({'kind': 'registered_QA_change', 'label': 'qa_advance',
                                   'started_ns': mutation_began, 'ended_ns': time.perf_counter_ns(), 'receipt': receipt})
            changed_off = relation(peer, 'OFF', folder, 'changed_OFF', ready['source_sha256'])
            changed_full = relation(peer, 'full', folder, 'changed_full', ready['source_sha256'])
            result['rows'].extend([changed_off, changed_full])
            assert changed_off['body']['context']['scene_revision'] != cold['body']['context']['scene_revision']
            assert core(changed_off['body']) == core(changed_full['body'])
            changed_oracle = supplement(native, changed_full['body'], folder, 'changed_oracle', True)
            result['rows'].append(changed_oracle)
            assert changed_full['body']['geometry'] == changed_oracle['geometry']
            assert changed_oracle['geometry'] != cold_oracle['geometry']
    except BaseException as exc:
        result['errors'].append({'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()})
    finally:
        if peer is not None:
            try:
                result['product_close'] = peer.close()
            except BaseException as exc:
                result['errors'].append({'stage': 'product_close', 'error': repr(exc)})
        if native is not None:
            try:
                result['native_close'] = native.close()
                result['worker_closed'] = native.status()['closed']
                closed = result['worker_closed']
                assert not closed['poisoned']
                expected = closed.get('accepted_geometry_fingerprint', closed['initial_geometry_fingerprint'])
                assert closed['final_geometry_fingerprint'] == expected
                assert bool(closed.get('qa_patch_applied')) == case['mutation']
                assert result['native_close']['process_reaped'] and result['native_close']['exit_code'] == 0
                assert result['native_close']['source_file_unchanged'] and result['native_close']['protected_files_unchanged']
            except BaseException as exc:
                result['errors'].append({'stage': 'native_close', 'error': repr(exc)})
        try:
            worker = enrich(result['rows'], folder)
            result['all_worker_events'] = worker
            assert not any(event.get('changed_or_new_PNG_files') or event.get('render_events_after', 0) > event.get('render_events_before', 0)
                           or event.get('event') in ('render_started', 'render_completed', 'render_cancelled') for event in worker)
        except BaseException as exc:
            result['errors'].append({'stage': 'record_enrichment', 'error': repr(exc)})
        result['ended_ns'] = time.perf_counter_ns()
        result['session_wall_ns'] = result['ended_ns'] - began
        result['within_570s'] = result['session_wall_ns'] < 570 * 10**9
        result['passed'] = bool(not result['errors'] and result['within_570s'] and result['product_close']
                                and result['product_close']['confirmed'] and result['native_close'])
        save(folder / 'RESULTS.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    assert Path(args.output).name == args.output and args.output not in ('.', '..')
    bindings = read(HERE / 'INPUT_BINDINGS.json')
    for name, digest in bindings['source_files_sha256'].items():
        assert sha((ROOT / name).read_bytes()) == digest, 'frozen_entry_source_changed'
    versions = {'baseline': read(BASELINE_READY), 'candidate': read(BATCH / 'installation/READY.json')}
    assert versions['baseline']['source_sha256'] == BASE_SHA and versions['candidate']['source_sha256'] == CANDIDATE_SHA
    assert all(ready['source_count'] == 137 and ready['no_default_activation'] for ready in versions.values())
    assert versions['baseline']['dependency_python'] == versions['candidate']['dependency_python']
    assert sha((BASE / 'input/scene.blend').read_bytes()) == ASSET_SHA
    output = HERE / args.output
    output.mkdir(exist_ok=False)
    save(output / 'FIXED_INPUTS.json', bindings)
    actor = load('_selected_evidence_peer', ACTOR)
    helper = load('_selected_evidence_owned_native', HERE / 'qa_native.py')
    cases = []
    for case in bindings['sessions']:
        row = run_case(case, versions[case['role']], output / case['id'], actor.Peer, helper.NativeSession)
        cases.append(row)
        save(output / ('RESULTS_AFTER_' + str(len(cases)) + '.json'), {'cases': cases})
        if not row['passed']:
            break
    protected = {name: sha((ROOT / name).read_bytes()) == digest
                 for name, digest in bindings['source_files_sha256'].items()}
    save(output / 'RESULTS.json', {'cases': cases, 'passed': len(cases) == 7 and all(row['passed'] for row in cases)
                                  and all(protected.values()), 'frozen_source_checks': protected,
                                  'model_consumers': 0, 'new_images': 0,
                                  'scope': 'first-application cold and same-generation engineering entry with identical QA instrumentation'})
    print(json.dumps({'output': str(output), 'successful_sessions': sum(row['passed'] for row in cases),
                      'attempted_sessions': len(cases)}))
    return 0 if len(cases) == 7 and all(row['passed'] for row in cases) and all(protected.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())

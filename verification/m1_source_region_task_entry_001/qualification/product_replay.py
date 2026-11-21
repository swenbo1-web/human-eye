"""Exercise both installed MCP tool catalogues and the new entry on sealed host input."""

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from math import isclose
from pathlib import Path
from runpy import run_path
import sys
from time import perf_counter_ns

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from capture import pinned_capture, require


NS = HERE.parent
V = NS.parent
OLD = 'human_eye_scene_observe'
NEW = 'human_eye_source_region_measure'
BINDINGS = {
    'A': V/'m4_source_region_blocker_frame_list_001/install/PRODUCT_RUN_BINDING.json',
    'B': NS/'install/PRODUCT_RUN_BINDING.json',
}
IDENTITIES = {
    'A': ('8cf3fabc1a735b7ff5849b3c63c49cf932df4b6b', '65bd1ec8009f8024e85ef1cd30c1229957cceb1c1766c8e5b62f2ef2489ce48c',
          '97053290d96270fefeff95d681efaf5222a64ef136a084267be5d7c707d6813d'),
    'B': ('e6e29f1857dfdfaea8b6c41c373fe42a5a6bde24', '66b8855a1e551f0a7e8f60c579b9f9116ec148a07988143077e9d57a08f3f7be',
          '997c664fbb80aaaed4f9cf0479a682bc8f8b06bb741650c0cfd00144a42a589a'),
}
SCOPE = 'complete_selected_source_triangle_union_to_reference_triangle_surface'
DISTANCE = 21474841 / 1073741824
DEFAULT_CONTEXT = {'session_id': 'sealed-source-region', 'task_context': {
    'task_id': 'qualification-source-region-task', 'task_run_id': 'sealed-assembly'}}


def read(path):
    return json.loads(Path(path).read_bytes())


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()


def save(path, value):
    with path.open('xb') as out:
        out.write(encoded(value) + b'\n')


def ident(path):
    raw = path.read_bytes()
    return {'path': path.resolve().as_posix(), 'bytes': len(raw), 'sha256': sha256(raw).hexdigest()}


def binding_for(arm):
    value = read(BINDINGS[arm])
    require(tuple(value[key] for key in ('preparation_git', 'source_sha256', 'wheel_sha256')) == IDENTITIES[arm]
            and ident(Path(value['wheel_path']))['sha256'] == value['wheel_sha256']
            and len(value['source_manifest']) == len({item['path'] for item in value['source_manifest']}) == 143,
            'incorrect_frozen_arm_installation/' + arm)
    install = Path(value['install_root']).resolve(strict=True)
    require(all(ident(install / row['path'])['sha256'] == row['sha256'] for row in value['source_manifest']),
            'loaded_install_manifest_bytes_changed/' + arm)
    return value


def worker(arm, mode, root):
    binding = binding_for(arm)
    sys.path[:0] = [binding['install_root'], binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.runtime_identity import runtime_identity

    require(runtime_identity()['source_sha256'] == binding['source_sha256']
            and Path(mcp.__file__).resolve().is_relative_to(Path(binding['install_root']).resolve()),
            'worker_imported_wrong_in_process_runtime')
    if mode == 'unknown':
        replay = run_path(str(V/'perf050_dual_region_occlusion_transfer_001/qualification/product_replay.py'))
        capture, sources, commands = replay['captured_source']()
        provenance = {'archive': 'Q1 regression only', 'sources': sources, 'commands': commands}
    else:
        capture, provenance = pinned_capture()
    root.mkdir()
    save(root/'SOURCE_RECEIPT.json', provenance)
    cfg = root/'PRODUCT_CONFIG.json'
    save(cfg, {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
               'project_root': binding['install_root'], 'state_file': str(root/'product_state.json'),
               'audit_file': str(root/'product_audit.jsonl'), 'request_budget_s': 40,
               'expected_identity': {'source_sha256': binding['source_sha256']}})

    class ArchiveHost:
        reads = 0

        def capture_scene(self):
            self.reads += 1
            return deepcopy(capture)

    class RecordedService(LiveSpatialService):
        calls = 0

        def observe(self, *args, **kwargs):
            result = super().observe(*args, **kwargs)
            self.calls += 1
            save(root/f'PRODUCER_{self.calls:02d}.json', result)
            return result

        def close(self):
            save(root/'EOF.json', {'closed': True, 'captures': self.host.reads, 'observations': self.calls})

    service = RecordedService(cfg, host=ArchiveHost())
    mcp._configure_utf8_stdio()
    mcp.run_stdio_mcp_server(service, spatial_task_only=(mode == 'special'))


def rpc(identifier, method, **params):
    return {'jsonrpc': '2.0', 'id': identifier, 'method': method, 'params': params}


def shape(target='N26', faces=(4, 5), **context):
    return {'region': {'object': {'name': target}, 'source_triangle_indices': list(faces)},
            'reference': {'name': 'N07'}, **DEFAULT_CONTEXT, **context}


def old_arguments(flat, detail='brief'):
    return {**{key: flat[key] for key in ('include_image', 'session_id', 'task_context') if key in flat},
            'query': {'mode': 'source_region', 'requested_facts': ['surface_proximity'],
                      **{key: flat[key] for key in ('region', 'region_ref', 'reference') if key in flat}},
            'response_detail': detail}


def stale_reference(ref):
    value = deepcopy(ref)
    value.pop('region_id')
    value['capture_generation']['revision'] += 1
    digest = sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {**value, 'region_id': 'source-region:' + digest}


def probe(arm, mode, output, transport, deadline):
    output.mkdir()
    state = output/'product'
    command = [sys.executable, '-IB', '-X', 'utf8', str(Path(__file__).resolve()),
               '--worker', arm, mode, str(state)]
    wire = output/'stdio'
    client = transport(command, output, wire, deadline)
    replies = {}

    def call(label, tool, arguments):
        response = client.call(rpc(label, 'tools/call', name=tool, arguments=arguments))
        path = wire/f'rpc_{client.records[-1]["index"]:02d}'/'RX.bin'
        require(response == read(path), 'actual_parsed_result_does_not_match_raw_wire')
        replies[label] = path
        return json.loads(response['result']['content'][0]['text'])

    def reject(label, tool, arguments, expected):
        body = call(label, tool, arguments)
        result = read(replies[label])['result']
        require(result['isError'] is True and expected in body['error'] and len(result['content']) == 1,
                'wrong_rejection/' + label + '/' + str(body.get('error')))

    try:
        startup = client.call(rpc('initialize', 'initialize', protocolVersion='2025-03-26',
                                  capabilities={}, clientInfo={'name': 'source-region-entry-preflight', 'version': '1'}))
        require('result' in startup, 'installed_stdio_initialize_failed')
        client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        tools = client.call(rpc('catalogue', 'tools/list'))['result']['tools']
        if mode == 'special':
            reject('new-not-exposed', NEW, shape(), 'Tool not exposed by this server mode')
        elif mode == 'unknown':
            flat = shape('Obj_06', (0, 1))
            flat['reference'] = {'name': 'Obj_03'}
            call('old-unknown', OLD, old_arguments(flat))
            if arm == 'B':
                call('new-unknown', NEW, flat)
        else:
            plain = shape()
            if arm == 'A':
                reject('new-not-available', NEW, plain, 'Unknown tool')
            else:
                reject('response-detail-rejected', NEW, dict(plain, response_detail='full'), 'Unexpected tool arguments')
                reject('selector-missing', NEW, {'reference': plain['reference']}, 'exactly one of region or region_ref')
                reject('nonboolean-image', NEW, dict(plain, include_image='false'), 'include_image must be boolean')
                call('new-positive', NEW, plain)
            measured = call('old-positive', OLD, old_arguments(plain))
            call('old-full', OLD, old_arguments(plain, 'full'))
            call('old-no-image', OLD, old_arguments(shape(include_image=False)))
            reject('old-budget', OLD, old_arguments(shape('N11', (10, 11))), 'Attention raster pixel work budget exceeded')
            if arm == 'B':
                ref = measured['region_ref']
                flat_ref = {key: value for key, value in plain.items() if key != 'region'}
                reject('selector-conflict', NEW, dict(plain, region_ref=ref), 'exactly one of region or region_ref')
                reject('stale-ref', NEW, dict(flat_ref, region_ref=stale_reference(ref)),
                       'source_region_ref_capture_generation_changed')
                call('new-ref-recovery', NEW, dict(flat_ref, region_ref=ref))
                call('new-no-image', NEW, shape(include_image=False))
                reject('new-budget', NEW, shape('N11', (10, 11)), 'Attention raster pixel work budget exceeded')
    finally:
        closure = client.finish()
        require(closure['confirmed'] and closure['exit_code'] == 0 and read(state/'EOF.json')['closed'],
                'installed_product_stdio_not_closed')
    return {'catalogue': tools, 'replies': replies, 'state': state, 'closure': closure}


def archived_probe(folder):
    reply = {}
    for path in sorted((folder/'stdio').glob('rpc_*/RX.bin')):
        payload = read(path)
        reply[payload['id']] = path
    closure = read(folder/'stdio/CLOSE.json')
    state = folder/'product'
    require(closure['confirmed'] and closure['exit_code'] == 0 and read(state/'EOF.json')['closed'],
            'retained_installed_stdio_not_closed')
    tools = read(reply.pop('catalogue'))['result']['tools']
    del reply['initialize']
    return {'catalogue': tools, 'replies': reply, 'state': state, 'closure': closure}


def score(body):
    task = body['task_result']
    metric = task['facts']['surface_proximity']
    value = metric['value']
    nearest = value['nearest_witness']
    a, b = nearest['a'], nearest['b']
    require(body['region_ref']['source_triangle_indices'] == [4, 5]
            and task['measurement_scope'] == SCOPE and task['reference']['name'] == 'N07'
            and metric['status'] == 'measured' and isclose(value['distance_m'], DISTANCE, abs_tol=1e-12, rel_tol=0)
            and nearest['direction_a_to_b'] == [0, 1, 0]
            and isclose(b[1]-a[1], DISTANCE, abs_tol=1e-12, rel_tol=0) and a[0] == b[0] and a[2] == b[2],
            'selected_region_distance_scope_or_actual_world_direction_changed')
    return {'distance_m': value['distance_m'], 'nearest': nearest,
            'membership': task['source_mapping']['nearest_witness']}


def image_proof(body, png, state, digest):
    data, = png
    brief = body['schema'] == 'source-region-brief-v3'
    frame, = body['images' if brief else 'frames']
    visibility = body['visibility'] if brief else body['facts']['visibility']
    witness = visibility['complete_witness']
    reference = Path(frame['local_image_path' if brief else 'image_path'])
    root = state/'product_state.json.source_region'
    require(reference.is_absolute() and reference.is_relative_to(root)
            and len(reference.relative_to(root).parts) == 2 and reference.resolve(strict=True) == reference
            and reference.read_bytes() == data and digest(data) == frame['image_sha256']
            and witness['geometry_status'] == 'complete' and witness['selected_surface_pixels'] >= 16
            and witness['contrasting_boundary_pixels'] >= 4
            and all(witness[key] == frame[key] for key in ('image_ref', 'frame_identity', 'view_name'))
            and frame['host_binding_sha256'] == body['binding']['binding_sha256'],
            'original_complete_witness_or_openable_same_slot_path_missing')
    if brief:
        require(frame['image_block_index'] == 1 and frame['local_image_path'] == reference.as_posix(),
                'wrong_brief_original_image_block_or_path')
    return {'original': ident(reference), 'witness': witness}


def projection_equal(a, b):
    for key in ('schema', 'region_ref', 'task_result', 'region', 'visibility', 'image_scope',
                'status', 'observation_status', 'read_only', 'execution_authority', 'session_id'):
        require(a[key] == b[key], 'dedicated_packet_changed_old_witness/' + key)
    for key in ('source_binding_sha256', 'binding_sha256', 'source_status', 'disk_status'):
        require(a['binding'].get(key) == b['binding'].get(key), 'source_binding_changed/' + key)
    require([{key: item for key, item in row.items() if key != 'local_image_path'} for row in a['images']]
            == [{key: item for key, item in row.items() if key != 'local_image_path'} for row in b['images']],
            'equivalent_route_changed_native_frame_metadata')


def review(output, arms, unknown):
    previous = run_path(str(V/'m1_source_region_diagnostic_artifact_prototype_001/checks/cli.py'))
    standard_a, special_a = arms['A']
    standard_b, special_b = arms['B']
    a_catalogue, b_catalogue = standard_a['catalogue'], standard_b['catalogue']
    new_schema, = [row for row in b_catalogue if row['name'] == NEW]
    require(a_catalogue == [row for row in b_catalogue if row['name'] != NEW]
            and special_a['catalogue'] == special_b['catalogue']
            and not any(row['name'] == NEW for row in special_b['catalogue']), 'catalogue_scope_or_legacy_schema_drift')
    schema = new_schema['inputSchema']
    require(set(schema['properties']) == {'region', 'region_ref', 'reference', 'include_image', 'session_id', 'task_context'}
            and schema['properties']['include_image']['default'] is True and schema['required'] == ['reference']
            and schema['additionalProperties'] is False
            and schema['oneOf'] == [{'required': ['region']}, {'required': ['region_ref']}],
            'narrow_catalogue_schema_contract_changed')

    positives, negatives, cli_cases = {}, {}, {}
    positive_cases = {'A': ('old-positive', 'old-full'),
                      'B': ('new-positive', 'old-positive', 'old-full', 'new-ref-recovery')}
    for arm, standard in (('A', standard_a), ('B', standard_b)):
        positives[arm], negatives[arm] = {}, {}
        for name in positive_cases[arm]:
            raw = standard['replies'][name]
            response, text, body, png, wire = previous['packet'](raw)
            require(body['binding']['runtime_source_sha256'] == IDENTITIES[arm][1] and body['read_only'] is True
                    and body['schema'] == ('human-eye-source-region-observation-v1' if name == 'old-full'
                                           else 'source-region-brief-v3'), 'incorrect_success_reply_identity_or_detail/' + name)
            image = image_proof(body, png, standard['state'], previous['digest'])
            positives[arm][name] = {'body': body, 'native': response['content'][1:], 'metric': score(body),
                                    'image': image, 'raw_RX': ident(raw), 'text_bytes': len(text.encode())}
            if name in ('old-positive', 'old-full', 'new-positive', 'new-ref-recovery'):
                stage_root = output/'fixed_cli'/arm/name
                stage_root.mkdir(parents=True)
                rows = previous['stages']('first' if name != 'old-full' else 'original_full',
                                          response, text, [dict(bytes=len(png[0]), sha256=previous['digest'](png[0]))],
                                          stage_root)
                require(all(row['native_PNG_exact'] and (name == 'old-full' or row['all_items_exact']) for row in rows),
                        'fixed_CLI_lost_native_evidence_or_brief/' + arm + '/' + name)
                cli_cases[arm + '/' + name] = rows
        for name in ('old-no-image', *(('new-no-image',) if arm == 'B' else ())):
            response, _, body, png, _ = previous['packet'](standard['replies'][name])
            require(not png and not body['images'] and body['observation_status'] == 'image_not_requested'
                    and body['visibility']['complete_witness'] is None, 'no_image_route_rendered_or_state_drift')
            score(body)
            negatives[arm][name] = {'body': body, 'native': response['content'][1:]}
        for index, name in enumerate(('old-unknown', *(('new-unknown',) if arm == 'B' else ())), 1):
            response, _, body, _, _ = previous['packet'](unknown[arm]['replies'][name])
            producer = read(unknown[arm]['state']/f'PRODUCER_{index:02d}.json')
            require(body['visibility']['complete_witness'] is None
                    and body['observation_status'] == 'evidence_insufficient'
                    and body['visibility']['status'] == 'unknown'
                    and body['visibility']['reason'] == 'selected_region_displayed_without_pixels'
                    and body['visibility']['selected_surface_pixels'] == 0
                    and producer['region_ref'] == body['region_ref']
                    and producer['binding']['binding_sha256'] == body['binding']['binding_sha256']
                    and len(producer['view_attempts']) == 6
                    and all(row['status'] == 'positive_area_occlusion' for row in producer['view_attempts'])
                    and body['task_result']['facts']['surface_proximity']['status'] == 'measured',
                    'unknown_visibility_or_preserved_measurement_contract_drift')
            negatives[arm][name] = {'body': body, 'native': response['content'][1:]}
    reference = positives['B']['new-positive']
    for a, name in (('A', 'old-positive'), ('B', 'old-positive'), ('B', 'new-ref-recovery')):
        peer = positives[a][name]
        projection_equal(reference['body'], peer['body'])
        require(reference['native'] == peer['native'] and reference['metric'] == peer['metric'],
                'dedicated_entry_changed_legacy_measurement_or_original_PNG')
    for name in ('no-image', 'unknown'):
        old = negatives['B']['old-' + name]
        new = negatives['B']['new-' + name]
        projection_equal(old['body'], new['body'])
        require(old['native'] == new['native'], 'dedicated_negative_changed_original_native_blocks')
    for arm in ('A', 'B'):
        full = positives[arm]['old-full']
        brief = positives[arm]['old-positive']
        require(full['metric'] == brief['metric'] and full['native'] == brief['native']
                and full['body']['region_ref'] == brief['body']['region_ref']
                and full['body']['binding']['binding_sha256'] == brief['body']['binding']['binding_sha256'],
                'legacy_full_scope_or_pixels_changed')
    projection_equal(negatives['A']['old-unknown']['body'], negatives['B']['new-unknown']['body'])
    require(negatives['A']['old-unknown']['native'] == negatives['B']['new-unknown']['native'],
            'candidate_unknown_PNG_different_from_historical_arm')
    budget = {}
    for arm, results in (('A', standard_a), ('B', standard_b)):
        for name in ('old', 'new') if arm == 'B' else ('old',):
            label = (name+'-unknown') if (name+'-unknown') in results['replies'] else (name+'-budget')
            raw = results['replies'][label]
            error = read(raw)['result']
            require(error['isError'] is True and len(error['content']) == 1
                    and 'Attention raster pixel work budget exceeded' in
                    json.loads(error['content'][0]['text'])['error'], 'unchanged_budget_guard_not_observed')
            budget[arm+'/'+name] = ident(raw)
    trace = {}
    for arm, standard in (('A', standard_a), ('B', standard_b)):
        state = standard['state']
        records = [json.loads(line) for line in (state/'product_audit.jsonl').read_bytes().splitlines()]
        by_id = {item['trace']['annotations'].get('mcp_request_id'): item['trace']
                 for item in records if item['event'] == 'request_trace'}
        for name in positive_cases[arm] + (('old-no-image',) if arm == 'A' else
                                          ('old-no-image', 'new-no-image')):
            item = by_id[name]
            props = item['annotations']
            require(item['operation'] == 'mcp.observe' and props['include_image'] == (not name.endswith('no-image'))
                    and props['image_request_source'] == 'mcp_transport'
                    and item['correlation']['session_id'] == DEFAULT_CONTEXT['session_id'],
                    'legacy_telemetry_or_image_request_intent_changed/' + arm + '/' + name)
            trace[arm+'/'+name] = {'mcp_observe': True, 'include_image': props['include_image'],
                                  'session_id': item['correlation']['session_id'],
                                  'trace_id': item['trace_id']}
    return {'passed': True, 'tools': {'A': len(a_catalogue), 'B': len(b_catalogue),
                 'tool_array_bytes_A': len(encoded(a_catalogue)), 'tool_array_bytes_B': len(encoded(b_catalogue)),
                 'dedicated_schema_bytes': len(encoded(new_schema)), 'specialized_count': len(special_a['catalogue'])},
            'positive': {arm: {name: {k: v for k, v in entry.items() if k not in ('body', 'native')}
                               for name, entry in entries.items()} for arm, entries in positives.items()},
            'telemetry': trace, 'fixed_CLI': cli_cases, 'assembly_budget_rejection': budget,
            'small_fixture_unknown': {arm: {name: ident(path) for name, path in slots['replies'].items()}
                                      for arm, slots in unknown.items()},
            'errors': {arm: {name: ident(path) for name, path in standard['replies'].items()
                             if read(path)['result']['isError']}
                       for arm, standard in (('A', standard_a), ('B', standard_b))},
            'isolated_stdio_closes': 6, 'Blender_starts': 0, 'model_starts': 0,
            'scope': 'Installed MCP stdio and frozen capture. No provider context or live host operation.'}


def run(output, retained=None, retained_unknown=None):
    output.mkdir(parents=True)
    output = output.resolve(strict=True)
    transport = run_path(str(V/'m4_global_local_qualification_001/harness/reused/stdio_checks.py'))['StdioClient']
    deadline = perf_counter_ns() + 150_000_000_000
    arms = {arm: tuple(archived_probe(retained/f'{arm}_{mode}') if retained is not None else
                       probe(arm, mode, output/f'{arm}_{mode}', transport, deadline)
                       for mode in ('live', 'special')) for arm in ('A', 'B')}
    unknown = {arm: archived_probe(retained_unknown/f'{arm}_unknown') if retained_unknown is not None else
               probe(arm, 'unknown', output/f'{arm}_unknown', transport, deadline) for arm in ('A', 'B')}
    report = review(output, arms, unknown)
    save(output/'PRODUCT_REPLAY.json', report)
    print(json.dumps({'passed': True, 'tools': report['tools'], 'CLI_cases': len(report['fixed_CLI'])}))


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'use_frozen_interpreter_with_I_B')
    if len(sys.argv) == 5 and sys.argv[1] == '--worker':
        worker(sys.argv[2], sys.argv[3], Path(sys.argv[4]))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('output', type=Path)
        parser.add_argument('--retained', type=Path)
        parser.add_argument('--retained-unknown', type=Path)
        args = parser.parse_args()
        run(args.output, args.retained, args.retained_unknown)

"""Derive legal paired facts from original dense source and replay the public tail gate."""

import argparse
from copy import deepcopy
from hashlib import sha256
from io import StringIO
import base64
import json
from pathlib import Path
import runpy
import subprocess
import sys
from time import perf_counter_ns
from zipfile import ZipFile


BASELINE = 'c8f87c540f802fe7b85caae95a8ac86b0f43518f'
WIDE = '475ae93a03780c1781c62c8372ee6cfe41792cad'
ASSET = '2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164'
EXPECTED_QUERY = {'mode': 'task', 'objects': [{'name': 'M4_Far_00'}, {'name': 'M4_Focal'}],
                  'requested_facts': ['surface_proximity']}
EXPANDED = ['aabb', 'center_delta', 'axis_gap', 'surface_clearance', 'solid_relation',
            'nearest_witness', 'pair_relation', 'surface_proximity', 'closed_solid_relation', 'spatial_relation']
OPTIONS = {
    'original_distance': ['surface_proximity'],
    'expanded_ten_facts': EXPANDED,
    'distance_with_AABB': ['surface_proximity', 'aabb'],
    'axis_gap_without_distance': ['axis_gap'],
}
RUNTIME_FIELDS = ('runtime_source_sha256', 'source_status', 'disk_status', 'source_check_scope')
EXPECTED_MISSING = (
    ('frames', 0, 'host_binding_sha256'),
    ('frames', 0, 'source_revision'),
)
FRAME_SCOPE_FIELDS = ('host_binding_sha256', 'source_revision', 'scene_identity', 'candidate_identity',
                      'patch_mapping_identity', 'patch_mapping_version', 'patch_roi_ids', 'mesh_order_identity')
IMAGE_FIELDS = ('image_path', 'image_ref', 'image_sha256')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(raw):
    return sha256(raw).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': digest(raw)}


def exact_json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def save(directory, name, raw):
    path = directory / name
    with path.open('xb') as output:
        output.write(raw)
    return pin(path)


class Original:
    """Independently bind the exact P1 original ZIP and each consumed member."""

    def __init__(self, repo):
        path = repo / 'verification/perf050_dense_pair_transfer_001/RUNTIME_INDEX.json'
        index = read(path)
        self.pins = [pin(path)]
        self.file = Path(index['archive']['path'])
        self.pins.append(pin(self.file))
        require(self.pins[1]['sha256'] == index['archive']['sha256'], 'original_dense_archive_changed')
        self.archive = ZipFile(self.file)
        self.entries = {row['path']: row for row in index['files']}
        require(len(self.archive.namelist()) == len(self.entries) == index['count']
                and set(self.archive.namelist()) == set(self.entries), 'original_archive_roster_changed')
        self.slot = self.file.parent / 'slots/P1'

    def fetch(self, relative):
        file = self.slot / relative
        key = file.relative_to(self.file.parent).as_posix()
        raw = self.archive.read(key)
        row = self.entries[key]
        require(len(raw) == row['bytes'] and digest(raw) == row['sha256'] and raw == file.read_bytes(),
                'original_dense_member_changed/' + key)
        self.pins.append(pin(file))
        return raw

    def json(self, relative):
        return json.loads(self.fetch(relative))

    def load(self):
        result = self.json('SLOT_RESULT.json')
        publication = self.json('SLOT_PUBLICATION.json')
        require(result['asset_sha256'] == ASSET and result['closure_verification']['passed']
                and result['independent_before_after']['passed'] and result['status'] == publication['status'] == 'completed'
                and publication['result_sha256'] == digest(self.fetch('SLOT_RESULT.json')),
                'original_P1_close_or_asset_changed')
        producer = self.json('product_full/call_001/SERVICE_RESULT.json')
        receipt = self.json('owner/tool_01/PRODUCT_RECEIPT.json')
        require(receipt['producer_archive']['sha256'] == digest(self.fetch('product_full/call_001/SERVICE_RESULT.json')),
                'original_P1_producer_ordinal_unbound')
        inner = 'mcp/rpc_%02d' % receipt['receipt']['index']
        req_raw, rx_raw = (self.fetch(inner + '/%s.bin' % tag) for tag in ('TX', 'RX'))
        request, reply = map(json.loads, (req_raw, rx_raw))
        require(request == self.json('product_calls/call_001/REQUEST.json')
                and reply == self.json('product_calls/call_001/RESPONSE.json')
                and receipt['receipt']['RX_sha256'] == digest(rx_raw)
                and request['params']['arguments']['response_detail'] == 'full'
                and request['params']['arguments']['query']['task_query'] == EXPECTED_QUERY,
                'original_P1_joint_request_unbound')
        actual_png = media(reply['result'])
        for index, frame in enumerate(producer['frames']):
            raw = self.fetch(Path(frame['image_path']).relative_to(self.slot))
            require(digest(raw) == frame['image_sha256'] == actual_png[index],
                    'actual_original_png_not_the_current_producer_frame')
        for sequence in ('002', '003'):
            self.fetch(f'native/WIRE/{sequence}/REQUEST.bin')
            self.fetch(f'native/WIRE/{sequence}/RESPONSE.bin')
        terminal = self.json('TERMINAL_SOURCE.json')
        require(digest(self.fetch('TERMINAL_SOURCE.json')) == result['terminal_source']['sha256']
                and len(terminal['objects']) == 14, 'original_dense_geometry_binding_changed')
        return request, producer, reply, terminal


def by_capture(repo, original, terminal, binding):
    entry = repo / 'verification/m4_cross_scale_discovery_001/oracle/check_saved.py'
    loader = runpy.run_path(str(entry))
    captures, commands = loader['decode_captures'](original.slot, binding, loader['Audit']())
    for row in commands:
        sequence = row['wire_sequence']
        original.fetch(f'native/WIRE/{sequence:03}/REQUEST.bin')
        original.fetch(f'native/WIRE/{sequence:03}/RESPONSE.bin')
    target_command, = [row for row in commands if row['wire_sequence'] == 2]
    select_command, = [row for row in commands if row['wire_sequence'] == 3]
    require(target_command['command']['command'] == 'capture_active_observation'
            and select_command['command']['command'] == 'capture_task'
            and select_command['command']['params']['selectors'] == EXPECTED_QUERY['objects'],
            'original_target_and_selected_host_commands_changed')
    target, = [row for row in captures if row['capture_scope'] == 'target_observation_meshes']
    selected, = [row for row in captures if row['capture_scope'] == 'selected_objects']
    stable_state = ('instance_id', 'epoch', 'revision')
    require(target['host_identity']['document_epoch'] == selected['host_identity']['document_epoch']
            and all(target['capture_state'][key] == selected['capture_state'][key] for key in stable_state),
            'original_two_scene_captures_not_current_together')
    complete = {row['object_id']: row for row in terminal['objects']}
    shared = {row['object_id']: row for row in target['meshes']}
    selected_sizes = {}
    for row in selected['meshes']:
        oid = row['object_id']
        current = complete[oid]
        require(row['name'] == current['name'] == shared[oid]['name']
                and row['vertices'] == current['evaluated']['vertices_world_m'] == shared[oid]['vertices']
                and row['faces'] == current['evaluated']['triangles'] == shared[oid]['faces']
                and selected['host_identity']['object_instances'][oid] == current['instance_id']
                == target['host_identity']['object_instances'][oid], 'ordered_geometry_differs_across_actual_captures')
        selected_sizes[row['name']] = {'vertices': len(row['vertices']), 'triangles': len(row['faces'])}
    require(selected_sizes == {'M4_Far_00': {'vertices': 293, 'triangles': 514},
                               'M4_Focal': {'vertices': 3, 'triangles': 1}},
            'expected_actual_whole_object_geometry_counts_changed')
    return target, selected_sizes, [target_command, select_command]


def task_replay(service, captured, query, old, geometry_ids):
    from human_eye_plugin.auto_router import _validated_scene
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.scene_cache import SpatialSceneCache
    from human_eye_plugin.task_query import task_result, validate_task_query

    query = validate_task_query(query)
    parent = old['binding']
    began = perf_counter_ns()
    task_view, task_sources, source_diagnostics = LiveSpatialService._prepare_observation_task_view(service, captured, query)
    task_view = LiveSpatialService._observation_task_view(service, task_view, task_sources, source_diagnostics,
                                                          query, parent, geometry_ids)
    view_ready = perf_counter_ns()
    scene, meshes, fingerprint = _validated_scene(task_view, _observation_task_capture=True, _annotate_scene=False)
    mesh_ready = perf_counter_ns()
    actual, timings = {}, {}
    task = task_result(scene, meshes, fingerprint, query, SpatialSceneCache(max_bytes=2 * 1024 * 1024),
                       service._check_request_budget, diagnostics=actual)
    compute_done = perf_counter_ns()
    task['binding']['observation_source'] = {'schema': 'active-observation-task-source-v1',
                    'measurement_scope': 'whole_objects', 'capture_scope': 'observation_task_objects',
                    'parent_binding_sha256': parent['binding_sha256'],
                    'parent_source_binding_sha256': parent['source_binding_sha256'],
                    'parent_capture_scope': parent['capture_scope'],
                    'capture_state': deepcopy(task_view['capture_state']), 'objects': task_sources}
    LiveSpatialService._bind_read_result(service, task, {'status': 'loaded_generation',
                                  'source_check_scope': old['task_result']['binding']['source_check_scope']})
    require(query['requested_facts'] and set(task['facts']) == set(query['requested_facts'])
            and [row['name'] for row in task['binding']['objects']] == ['M4_Far_00', 'M4_Focal']
            and task['binding']['capture_scope'] == 'observation_task_objects' and len(meshes) == 2
            and source_diagnostics['supplemental_capture_calls'] == 0
            and source_diagnostics['geometry_alias_reuses'] == 2, 'actual_task_producer_not_exact_pair_and_facts')
    if 'surface_proximity' in task['facts']:
        value = task['facts']['surface_proximity']
        require(value['status'] == 'measured' and value['value']['distance_m'] == 1
                and value['value']['nearest_witness'] ==
                    {'a': [1, 0, 0], 'b': [0, 0, 0], 'direction_a_to_b': [-1, 0, 0]},
                'actual_expanded_task_whole_distance_changed')
    timings.update(source_prepare_and_bind_ns=view_ready - began,
                   normalization_ns=mesh_ready - view_ready, task_calculation_ns=compute_done - mesh_ready,
                   source_attach_ns=perf_counter_ns() - compute_done)
    return task, source_diagnostics, actual, timings


def transport(mcp, service, request):
    input_stream = StringIO(json.dumps(request, ensure_ascii=False) + '\n')
    output_stream = StringIO(newline='\r\n')
    mcp.run_stdio_mcp_server(service, input_stream=input_stream, output_stream=output_stream)
    raw = output_stream.getvalue().encode()
    result = json.loads(raw)
    require(result['id'] == request['id'] and service.closed and service.observations == 1
            and result['result']['isError'] is False, 'actual_installed_public_stdio_delivery_failed')
    require(service.phases == [('before_task_publication', False), ('before_stdio_write', True)],
            'actual_installed_publication_budget_stages_changed')
    return raw


def media(result):
    return [digest(base64.b64decode(item['data'], validate=True))
            for item in result['content'] if item['type'] == 'image']


def normalized(result):
    result = deepcopy(result)
    result['binding']['runtime_source_sha256'] = '[current-runtime-identity]'
    result['task_result']['binding']['runtime_source_sha256'] = '[current-runtime-identity]'
    return result


def read_body(reply):
    raw = reply['result']['content'][0]['text']
    return raw, json.loads(raw)


def serialized(packet, target):
    patched = deepcopy(packet)
    patched['result']['content'][0]['text'] = exact_json(target)
    return (json.dumps(patched, ensure_ascii=False, allow_nan=False) + '\r\n').encode()


def worker(repo, install, out):
    spec = read(install)
    sys.path[:0] = [spec['install_root'], spec['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp
    from human_eye_plugin.active_observation_host import scene_from_capture, geometry, _meshes_from_objects
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.runtime_identity import runtime_identity

    identity = runtime_identity()
    require(identity['source_kind'] == 'installed_distribution' and identity['source_sha256'] == spec['source_sha256']
            and len(spec['source_manifest']) == 143, 'expected_isolated_installed_product')
    original = Original(repo)
    request, producer, original_reply, terminal = original.load()
    archived_binding = read(repo / 'verification/m1_pair_distance_entry_001/install/PRODUCT_RUN_BINDING.json')
    captured, selected_sizes, commands = by_capture(repo, original, terminal, archived_binding)
    objects, _, geometry_sha = geometry(scene_from_capture(captured))
    require(geometry_sha == producer['binding']['geometry_identity'], 'changed_actual_geometry_alias_source')
    geometry_ids = tuple(mesh.object_id for mesh in _meshes_from_objects(objects))

    class ArchivedService:
        request_budget_s = None
        _request_budget = LiveSpatialService._request_budget
        request_error_fields = staticmethod(LiveSpatialService.request_error_fields)

        def __init__(self, payload=None, query=None):
            self._identity = identity
            self.state_path = original.slot / 'product_state.json'
            self.payload, self.query = payload, query
            self.phases, self.observations, self.closed = [], 0, False

        def observe(self, _session, **kwargs):
            require(self.payload is not None and kwargs.get('query') == self.query and kwargs.get('include_image') is True,
                    'public_dispatch_did_not_use_actual_derived_request')
            self.observations += 1
            return deepcopy(self.payload)

        def _check_request_budget(self, phase, *, publication=False):
            self.phases.append((phase, publication))

        def close(self):
            self.closed = True

    reports = {}
    out.mkdir(exist_ok=False)
    archived_task = normalized(producer)['task_result']
    for case, facts in OPTIONS.items():
        authored = deepcopy(request)
        query = authored['params']['arguments']['query']
        query['task_query']['requested_facts'] = facts[:]
        task, source_diag, calculation, timings = task_replay(ArchivedService(), captured, query['task_query'], producer,
                                                               geometry_ids)
        payload = deepcopy(producer)
        payload['binding']['runtime_source_sha256'] = identity['source_sha256']
        payload['task_result'] = task
        if case == 'original_distance':
            require(normalized(payload)['task_result'] == archived_task, 'original_distance_does_not_rederive_exactly')
        require(all(payload[key] == producer[key] for key in producer if key not in ('binding', 'task_result')),
                'derived_fixture_changed_original_observation_or_telemetry')
        service = ArchivedService(payload, query)
        start = perf_counter_ns()
        wire = transport(mcp, service, authored)
        elapsed = perf_counter_ns() - start
        packet = json.loads(wire)
        body, document = read_body(packet)
        require(document['task_result'] == task and media(packet['result']) == media(original_reply['result']),
                'actual_public_measurement_or_original_PNG_changed')
        folder = out / case
        folder.mkdir()
        artifacts = {
            'request': save(folder, 'REQUEST.json', exact_json(authored).encode() + b'\n'),
            'producer': save(folder, 'DERIVED_PRODUCER.json', exact_json(payload).encode() + b'\n'),
            'raw_reply': save(folder, 'PUBLIC_RX.bin', wire),
        }
        reports[case] = {'requested_facts': facts, 'artifacts': artifacts, 'body_bytes': len(body.encode()),
                         'affected_measurement_status': task['status'],
                         'fact_statuses': {key: [row['status'] for row in value] if isinstance(value, list) else value['status']
                                           for key, value in task['facts'].items()},
                         'source_diagnostics': source_diag, 'calculation': calculation,
                         'elapsed_ns': {**timings, 'public_serialization_and_stdio_ns': elapsed},
                         'actual_original_pngs': media(packet['result']), 'actual_real_stdio_calls': 1,
                         'actual_model_Blender_image_construction': 0}
    original.archive.close()
    value = {'install_sha256': digest(install.read_bytes()), 'product_commit': spec['preparation_git'],
             'runtime_source_sha256': identity['source_sha256'], 'counts': selected_sizes,
             'archived_real_commands': commands, 'reports': reports, 'original_source_pins': original.pins}
    sys.stdout.buffer.write(exact_json(value).encode())


def cli_profile(repo, packet):
    budget = runpy.run_path(str(repo/'verification/m4_cross_scale_live_qualification_001/checks/delivery.py'))['budget_helpers']
    helpers, policy = budget()
    require((policy['MCP_bytes'], policy['history_approximate_tokens']) == (12000, 3000), 'fixed_CLI_policy_changed')
    module = repo/'verification/m5_global_observe_measure_qualification_001/checks'
    sys.path.insert(0, str(module))
    missing = runpy.run_path(str(module/'live_wire.py'))['omitted_paths']
    text, doc = read_body(packet)
    original_images = media(packet['result'])
    profiles = {}
    for seconds in ('0.0000', '10.0000', '100.0000'):
        model_items = helpers['model_items'](packet['result'], seconds)
        tier = helpers['truncate_items'](model_items, 12000)
        history = helpers['truncate_items'](tier, 3000, token_mode=True)
        rows = {}
        for label, items in [('MCP', tier), ('history', history)]:
            retained = [item['text'] for item in items if item['type'] == 'input_text'][1]
            png = [digest(base64.b64decode(item['image_url'].split(',', 1)[1], validate=True))
                   for item in items if item['type'] == 'input_image']
            lost = set(tuple(path) for path in missing(text, retained))
            lost_scope = [path for path in lost if path[:2] == ('frames', 0) and path[-1] in FRAME_SCOPE_FIELDS]
            lost_obs = [path for path in lost if path[:2] == ('facts', 'observations') and path[-1] in IMAGE_FIELDS]
            require(png == original_images and not lost_obs, 'native_png_or_observation_path_identity_lost')
            rows[label] = {'body_UTF8_bytes': len(retained.encode()), 'critical_lost': sorted(lost_scope, key=repr),
                           'observation_identity_lost': lost_obs, 'native_PNG_sha256': png,
                           'lost_measurement_count': sum(path[0] == 'task_result' for path in lost),
                           'all_lost_leaf_count': len(lost), 'input_body_sha256': digest(retained.encode())}
        profiles[len(model_items[0]['text'].encode())] = rows
    require(list(profiles) == [33, 34, 35], 'fixed_header_count_changed')
    return profiles


def launch(repo, binding, folder):
    argv = [sys.executable, '-IB', str(Path(__file__).resolve()), '--repo', str(repo),
            '--worker', str(binding), '--wire-dir', str(folder)]
    result = subprocess.run(argv, capture_output=True, timeout=60)
    if result.returncode:
        raise ValueError(result.stderr.decode(errors='replace'))
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--wide', type=Path)
    parser.add_argument('--narrow', type=Path)
    parser.add_argument('--wire-dir', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', type=Path)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'use_pinned_interpreter_minus_I_minus_B')
    if args.worker:
        worker(args.repo, args.worker, args.wire_dir)
        return
    require(args.baseline and args.wide and args.output, 'explicit_fixed_install_inputs_required')
    args.wire_dir.mkdir(exist_ok=False)
    installs = {'baseline': args.baseline.resolve(), 'old_wide_tail': args.wide.resolve()}
    if args.narrow:
        installs['narrowed'] = args.narrow.resolve()
    reports = {key: launch(args.repo, install, args.wire_dir / key) for key, install in installs.items()}
    require(reports['baseline']['product_commit'] == BASELINE and reports['old_wide_tail']['product_commit'] == WIDE,
            'wrong_prior_two_products')
    cases = {}
    for case in OPTIONS:
        packets = {arm: read(result['reports'][case]['artifacts']['raw_reply']['path']) for arm, result in reports.items()}
        bodies = {arm: normalized(read_body(packet)[1]) for arm, packet in packets.items()}
        original = bodies['baseline']
        old_tail = bodies['old_wide_tail']
        require(all(value == original for value in bodies.values())
                and all(packet['result']['content'][1:] == packets['baseline']['result']['content'][1:]
                        for packet in packets.values()) and list(old_tail)[-1] == 'task_result',
                'nonlayout_public_fields_or_original_png_changed')
        images = media(packets['baseline']['result'])
        layouts = {arm: list(value) for arm, value in bodies.items()}
        bytes_without_identity = {arm: serialized(packets[arm], value) for arm, value in bodies.items()}
        prof = {arm: cli_profile(args.repo, packet) for arm, packet in packets.items()}
        if 'narrowed' in bodies:
            intended = 'old_wide_tail' if case == 'original_distance' else 'baseline'
            require(bytes_without_identity['narrowed'] == bytes_without_identity[intended],
                    'narrowed_scope_did_not_keep_expected_exact_normalized_wire/' + case)
        if case == 'expanded_ten_facts':
            for stage in ('MCP', 'history'):
                a = prof['baseline'][35][stage]
                bad = prof['old_wide_tail'][35][stage]
                require(not a['critical_lost'] and set(EXPECTED_MISSING) <= set(bad['critical_lost'])
                        and a['lost_measurement_count'] > 0 and bad['lost_measurement_count'] == 0,
                        'old_wide_tail_exact_35B_frame_source_counterexample_not_reproduced/' + stage)
                if 'narrowed' in prof:
                    require(not prof['narrowed'][35][stage]['critical_lost'],
                            'narrowed_did_not_preserve_original_frame_source/')
        cases[case] = {'raw_semantics_and_original_PNG_equal': True,
                       'returned_original_PNGs': images, 'body_field_orders': layouts,
                       'identity_normalized_reply_sha256': {
                           arm: digest(value) for arm, value in bytes_without_identity.items()},
                       'fixed_cli_stages': prof}
    report = {'schema': 'm1-joint-full-task-tail-scope-actual-expanded-controls-v1', 'passed': True,
              'original_historical_slots': 1, 'new_derived_control_cases_per_install': len(OPTIONS),
              'actual_installed_products': list(reports), 'products': reports, 'comparative_controls': cases,
              'geometry_derivation': 'Actual original embedded host packet 002 source plus independently paired 003, '
              'production prepared and normalized task scope, actual installed solver and stdio, original observation graph retained.',
              'new_owned_Blender': 0, 'new_model': 0, 'new_raster': 0, 'constructed_or_run_bonus_candidate': 0}
    with args.output.open('x', encoding='utf-8', newline='\n') as out:
        json.dump(report, out, indent=2, ensure_ascii=False, allow_nan=False)
        out.write('\n')
    print(pin(args.output))


if __name__ == '__main__':
    main()

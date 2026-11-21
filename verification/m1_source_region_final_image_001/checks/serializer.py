"""Exercise the installed MCP serializer on original closed-run evidence."""

import argparse
import base64
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import time
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
P2 = V / 'perf050_source_region_active_view_p2'
ACTIVE = V / 'm4_source_region_active_view_001'
BASE = ACTIVE / 'install/PRODUCT_RUN_BINDING.json'
RUN = Path('D:/he_perf050_source_region_active_view_p2')
SLOT = RUN / 'slots/P2'
ENGINE = Path('D:/he_m4_source_region_active_view_001')
BASELINE_SOURCE = '2ad989728b7229934d164cf4c763eeb89b28e86d6fbfe7b90bace82055b2683c'
ORIGINAL_DIGEST = 'a0b1aa30a722c519252224c8645084c92b08a514762e07e61e24f1b8e8225dbe'
P2_ZIP_DIGEST = 'befd9d28399e6a2a06b89626d221684433050fda01422d1552a7b05eafde4aa5'
ENGINE_ZIP_DIGEST = '7a2637ddfd2b751d40ed3b08515e0326c2f5147cfc84cc74e1d73975bedfec03'
FIELD = 'local_image_path'
CLI = ACTIVE / 'checks/evidence.py'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def file_pin(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {'path': str(path), 'sha256': sha256(data).hexdigest(), 'bytes': len(data)}


def original_paths(attempt, producer):
    return (SLOT / 'product_calls' / f'call_{attempt:03d}' / 'REQUEST.json',
            SLOT / 'product_calls' / f'call_{attempt:03d}' / 'RESPONSE.json',
            SLOT / 'product_full' / f'call_{producer:03d}' / 'SERVICE_RESULT.json')


def fixtures():
    full, no_image, brief = (original_paths(attempt, item) for attempt, item in ((4, 3), (5, 4), (6, 5)))
    global_right = original_paths(3, 2)
    unknown = (full[0], ENGINE / 'slots/A/product_calls/call_001/RESPONSE.json',
               ENGINE / 'slots/A/product_full/call_001/SERVICE_RESULT.json')
    cross_slot = ENGINE / 'slots/B/product_full/call_001/SERVICE_RESULT.json'
    return {'full': full, 'no_image': no_image, 'brief': brief, 'global': global_right, 'unknown': unknown,
            'cross_slot': cross_slot}


def bind_archive(run, index, expected_archive, count, paths):
    reference = read(index)
    arc = Path(reference['archive']['path'])
    anchor = file_pin(arc)
    require(anchor['sha256'] == expected_archive == reference['archive']['sha256']
            and anchor['bytes'] == reference['archive']['bytes'], 'original_archive_identity_changed')
    records = {row['path']: row for row in reference['files']}
    require(len(records) == reference['count'] == count, 'original_archive_membership_changed')
    pins = [file_pin(index), anchor]
    with ZipFile(arc) as archive:
        require(set(archive.namelist()) == records.keys(), 'original_zip_member_set_changed')
        for path in sorted(set(paths)):
            name = path.relative_to(run).as_posix()
            pin = file_pin(path)
            require({**pin, 'path': name} == records[name] and archive.read(name) == path.read_bytes(),
                    'retained_wire_or_source_file_changed/' + name)
            pins.append(pin)
    return pins


class SavedProducer:
    """Return one immutable historical observation without starting the observer."""

    def __init__(self, producer, arguments, state_path):
        self.producer = producer
        self.arguments = arguments
        self.state_path = state_path
        self.observations = 0

    def observe(self, session, **arguments):
        self.observations += 1
        require(self.observations == 1 and session == self.producer['session_id']
                and arguments.get('query') == self.arguments['query']
                and arguments.get('include_image') is self.arguments['include_image'],
                'real_request_no_longer_binds_archived_observation')
        return deepcopy(self.producer)

    def _check_request_budget(self, phase):
        require(phase == 'before_task_publication', 'unexpected_replay_deadline_phase')


def call(server_type, request, producer, state_path):
    service = SavedProducer(producer, request['params']['arguments'], state_path)
    server = server_type(service, default_session_id=producer['session_id'])
    returned = server.handle_jsonrpc_message(deepcopy(request))
    require(returned['id'] == request['id'] and returned['jsonrpc'] == '2.0' and service.observations == 1,
            'true_public_dispatch_not_exercised')
    return returned['result']


def changed_request(request, detail):
    altered = deepcopy(request)
    altered['params']['arguments']['response_detail'] = detail
    return altered


def body(result):
    return json.loads(result['content'][0]['text'])


def path_fields(result):
    def visit(value):
        if isinstance(value, dict):
            return [child for key, item in value.items() for child in
                    ([item] if key == FIELD else visit(item))]
        if isinstance(value, list):
            return [child for item in value for child in visit(item)]
        return []
    return visit(body(result))


def payload(result):
    return {'body': body(result),
            'images': [item for item in result['content'] if item['type'] == 'image'],
            'is_error': result['isError']}


def lossless_display_rows(value):
    """The original archive sorts dictionary keys before replay."""
    scope = value['body'].get('image_scope') or {}
    objects = scope.get('objects')
    if isinstance(objects, dict):
        columns = objects['columns']
        scope['objects'] = [dict(zip(columns, row, strict=True)) for row in objects['rows']]
    return value


def worker(binding_path):
    binding = read(binding_path)
    sys.path[:0] = [binding['install_root'], binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp
    from human_eye_plugin.runtime_identity import runtime_identity

    runtime = runtime_identity()
    require(runtime['source_sha256'] == binding['source_sha256']
            and runtime['source_kind'] == 'installed_distribution' and len(binding['source_manifest']) == 143,
            'replay_import_must_be_the_verified_installed_product')
    state = SLOT / 'product_state.json'
    source = fixtures()
    originals, requests, replies = {}, {}, {}
    for key in ('full', 'no_image', 'brief', 'global', 'unknown'):
        request_path, response, producer = source[key]
        requests[key], originals[key] = read(request_path), read(producer)
        if key == 'unknown':
            requests[key] = changed_request(requests[key], 'brief')
        root = ENGINE / 'slots/A/product_state.json' if key == 'unknown' else state
        replies[key] = call(mcp.LiveSpatialMCPServer, requests[key], originals[key], root)
        if binding['source_sha256'] == BASELINE_SOURCE:
            recorded = read(response)['result']
            require(lossless_display_rows(payload(replies[key])) == lossless_display_rows(payload(recorded))
                    and len(replies[key]['content'][0]['text'].encode('utf-8'))
                        == len(recorded['content'][0]['text'].encode('utf-8')), 'actual_baseline_wire_changed/' + key)
    replies['cold_brief'] = call(mcp.LiveSpatialMCPServer, changed_request(requests['full'], 'brief'),
                                 originals['full'], state)

    selected = originals['brief']['frames'][0]
    global_right, = (row for row in originals['global']['frames'] if row['view_name'] == 'RIGHT')
    foreign = read(source['cross_slot'])['frames'][0]
    require(selected['image_sha256'] == foreign['image_sha256'] == ORIGINAL_DIGEST
            and selected['frame_identity'] != foreign['frame_identity']
            and selected['view_name'] == global_right['view_name'] and selected['image_sha256'] != global_right['image_sha256'],
            'same_name_and_identical_bytes_controls_not_distinct')

    controls = {}
    for label in ('cross_slot_same_png', 'same_name_global_right', 'ambiguous_construction_archive',
                  'missing_construction_archive', 'unbound_frame_ref', 'unbound_frame_identity',
                  'wrong_content_digest', 'missing_png', 'foreign_capture_binding', 'inconsistent_selected_ref'):
        sample = deepcopy(originals['brief'])
        chosen = sample['frames'][0]
        witness = sample['facts']['visibility']['complete_witness']
        if label in ('cross_slot_same_png', 'same_name_global_right'):
            replacement = foreign if label == 'cross_slot_same_png' else global_right
            if label == 'cross_slot_same_png':
                # Same byte checksum and an internally consistent archive row do not authorize another run's path.
                selected_record, = (record for record in sample['constructed_frames']
                                    if record['frame_identity'] == chosen['frame_identity'])
                selected_record['image_path'] = replacement['image_path']
            chosen['image_path'] = replacement['image_path']
            chosen['image_sha256'] = replacement['image_sha256']
        elif label == 'ambiguous_construction_archive':
            sample['constructed_frames'].append(deepcopy(chosen))
        elif label == 'missing_construction_archive':
            sample.pop('constructed_frames')
        elif label in ('unbound_frame_ref', 'unbound_frame_identity'):
            key = 'image_ref' if label == 'unbound_frame_ref' else 'frame_identity'
            wrong = 'source-region-image:' + '0' * 64 if key == 'image_ref' else '0' * 64
            chosen[key] = witness[key] = sample['facts']['visibility'][key] = wrong
        elif label == 'wrong_content_digest':
            chosen['image_sha256'] = '0' * 64
        elif label == 'missing_png':
            chosen['image_path'] = str(Path(chosen['image_path']).with_name('nonexistent-replay-original.png'))
            require(not Path(chosen['image_path']).exists(), 'missing_PNG_control_not_missing')
        elif label == 'foreign_capture_binding':
            chosen['host_binding_sha256'] = foreign['host_binding_sha256']
        elif label == 'inconsistent_selected_ref':
            sample['region_ref']['source_triangle_indices'] = [21]
        delivered = call(mcp.LiveSpatialMCPServer, requests['brief'], sample, state)
        controls[label] = {'paths': path_fields(delivered), 'is_error': delivered['isError'],
                           'native_images': len(payload(delivered)['images'])}
    unavailable = call(mcp.LiveSpatialMCPServer, requests['brief'], originals['brief'], None)
    controls['missing_trusted_state'] = {'paths': path_fields(unavailable), 'is_error': unavailable['isError'],
                                         'native_images': len(payload(unavailable)['images'])}
    projected = {'content': [{'type': 'text', 'text': json.dumps(mcp.project_source_region_brief(originals['brief']))}],
                 'isError': False}
    controls['projection_without_image_block'] = {'paths': path_fields(projected), 'is_error': False,
                                                  'native_images': 0}
    print(json.dumps({'replies': replies, 'controls': controls, 'source_sha256': runtime['source_sha256']},
                     ensure_ascii=False, allow_nan=False))


def run_worker(binding):
    return json.loads(subprocess.check_output(
        [sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--worker', str(binding)], timeout=60))


def strip_path(result):
    value = payload(result)
    value['body']['images'][0].pop(FIELD, None)
    return value


def run(candidate, output):
    source = fixtures()
    p2_pins = [path for key in ('full', 'no_image', 'brief', 'global') for path in source[key]]
    archived_selected = read(source['brief'][2])['frames'][0]
    global_right, = (row for row in read(source['global'][2])['frames'] if row['view_name'] == 'RIGHT')
    p2_pins.extend(Path(frame['image_path']) for frame in (archived_selected, global_right))
    p2_pins.extend((SLOT / 'SLOT_RESULT.json', SLOT / 'SLOT_PUBLICATION.json', SLOT / 'RUNTIME_CLOSE.json',
                    SLOT / 'consumer/PUBLIC_FINAL.txt'))
    eng_pins = [source['unknown'][1], source['unknown'][2], source['cross_slot']]
    eng_pins += [Path(read(path)['frames'][0]['image_path']) for path in (source['unknown'][2], source['cross_slot'])]
    pins = bind_archive(RUN, P2 / 'RUNTIME_INDEX.json', P2_ZIP_DIGEST, 338, p2_pins)
    pins += bind_archive(ENGINE, ACTIVE / 'RUNTIME_INDEX.json', ENGINE_ZIP_DIGEST, 293, eng_pins)
    require(read(SLOT / 'SLOT_RESULT.json')['closure_verification']['passed'] is True,
            'historical_source_run_must_be_closed')
    baseline = run_worker(BASE)
    require(not any(path_fields(value) for value in baseline['replies'].values()), 'baseline_already_has_local_image_path')
    require(Path(archived_selected['image_path']).read_bytes() == base64.b64decode(
        baseline['replies']['brief']['content'][1]['data'], validate=True), 'archived_original_file_not_same_as_bound_PNG')
    report = {'schema': 'm1-source-region-final-image-serializer-replay-v1', 'passed': True,
              'candidate_tested': candidate is not None, 'runtime_source_sha256': baseline['source_sha256'],
              'baseline_real_reply_equivalence': ['full', 'no_image', 'brief', 'global', 'unknown'],
              'replay_archive_orders_display_columns_differently_but_decodes_identically': True,
              'source_pins': pins + [file_pin(path) for path in (BASE, Path(__file__), CLI)],
              'observed_Blender_starts': 0, 'observed_model_runs': 0, 'observed_new_rasters': 0}
    if candidate is not None:
        from runpy import run_path

        check_cli = run_path(str(CLI))['replay_cli']
        actual = run_worker(candidate)
        expected_path = Path(archived_selected['image_path']).resolve().as_posix()
        rows = {}
        for key in ('cold_brief', 'brief'):
            result = actual['replies'][key]
            old = baseline['replies'][key]
            resolved = path_fields(result)
            require(resolved == [expected_path] and body(result)['images'][0][FIELD] == expected_path
                    and strip_path(result) == payload(old), 'candidate_changed_original_image_or_evidence/' + key)
            raw = base64.b64decode(result['content'][1]['data'], validate=True)
            started = time.perf_counter_ns()
            with Path(resolved[0]).open('rb') as original:
                opened = original.read()
            reopened_ns = time.perf_counter_ns() - started
            require(opened == raw and sha256(opened).hexdigest() == ORIGINAL_DIGEST,
                    'current_file_open_does_not_match_native_PNG')
            replay = check_cli(result)
            require(replay['passed'] is True, 'existing_fixed_CLI_does_not_preserve_local_image_reference')
            old_bytes = len(old['content'][0]['text'].encode('utf-8'))
            rows[key] = {'path': expected_path, 'original_PNG_sha256': ORIGINAL_DIGEST,
                         'opened_bytes': len(opened), 'file_open_read_ns': reopened_ns,
                         'baseline_body_bytes': old_bytes, 'candidate_body_bytes': replay['body_bytes'],
                         'added_body_bytes': replay['body_bytes'] - old_bytes, 'fixed_CLI': replay}
        for key in ('full', 'no_image', 'global', 'unknown'):
            require(payload(actual['replies'][key]) == payload(baseline['replies'][key]),
                    'existing_reply_contract_changed/' + key)
        for key, actual_control in actual['controls'].items():
            old = baseline['controls'][key]
            require(not actual_control['paths'] and
                    all(actual_control[item] == old[item] for item in ('is_error', 'native_images')),
                    'invalid_local_reference_or_original_behavior_changed/' + key)
        for key in ('wrong_content_digest', 'missing_png', 'foreign_capture_binding', 'inconsistent_selected_ref'):
            require(actual['controls'][key]['is_error'] and actual['controls'][key]['native_images'] == 0,
                    'expected_preexisting_serializer_rejection_missing/' + key)
        report.update(candidate_runtime_source_sha256=actual['source_sha256'], cold_and_hot=rows,
                      original_behavior_controls=actual['controls'], same_named_global_and_ineligible_responses_preserved=True)
        report['source_pins'].append(file_pin(candidate))
    with output.open('x', encoding='utf-8') as sink:
        json.dump(report, sink, indent=2, ensure_ascii=False, allow_nan=False)
        sink.write('\n')
    print('Serializer replay', file_pin(output)['sha256'], 'candidate', candidate is not None, flush=True)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'use_pinned_interpreter_with_I_B')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--output', type=Path, default=HERE / 'SERIALIZER.json')
    args = parser.parse_args()
    if args.worker is not None:
        worker(args.worker)
    else:
        run(args.candidate, args.output)

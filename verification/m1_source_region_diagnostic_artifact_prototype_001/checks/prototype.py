"""Publish two frozen full replies as local files behind existing brief projections."""

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns
from zipfile import ZipFile

CHECKS = Path(__file__).resolve().parent
sys.path.insert(0, str(CHECKS))
from fixture import DIAGNOSTIC_POINTER, load_fixtures, resolve_diagnostic


NS = CHECKS.parent
V = NS.parent
REPO = V.parent
BINDING = V / 'm4_source_region_blocker_frame_list_001/install/PRODUCT_RUN_BINDING.json'
COMMIT = '8cf3fabc1a735b7ff5849b3c63c49cf932df4b6b'
SOURCE_SHA = '65bd1ec8009f8024e85ef1cd30c1229957cceb1c1766c8e5b62f2ef2489ce48c'
WHEEL_SHA = '97053290d96270fefeff95d681efaf5222a64ef136a084267be5d7c707d6813d'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')


def save(folder, name, value):
    (folder / name).write_bytes(json_bytes(value) + b'\n')


def verified_product():
    binding = json.loads(BINDING.read_bytes())
    require((binding['preparation_git'], binding['source_sha256'], binding['wheel_sha256']) ==
            (COMMIT, SOURCE_SHA, WHEEL_SHA), 'frozen_product_binding_changed')
    wheel, install = Path(binding['wheel_path']), Path(binding['install_root'])
    require(digest(wheel.read_bytes()) == WHEEL_SHA and len(binding['source_manifest']) == 143,
            'frozen_wheel_changed')
    with ZipFile(wheel) as archive:
        for item in binding['source_manifest']:
            name = item['path']
            recorded = subprocess.check_output(['git', 'show', COMMIT + ':' + name], cwd=REPO)
            require(digest(recorded) == item['sha256'] and recorded == archive.read(name)
                    and recorded == (install / name).read_bytes(), 'source_wheel_install_mismatch/' + name)
    sys.path[:0] = [str(install), binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp
    from human_eye_plugin.runtime_identity import runtime_identity

    require(runtime_identity()['source_sha256'] == SOURCE_SHA
            and Path(mcp.__file__).is_relative_to(install), 'wrong_loaded_product')
    return mcp


def artifact_descriptor(directory, raw):
    checksum = digest(raw)
    return {'local_path': (directory / (checksum + '.json')).as_posix(), 'sha256': checksum, 'bytes': len(raw)}


def publish(root, raw):
    started = perf_counter_ns()
    root.mkdir(exist_ok=False)
    directory = root.resolve(strict=True)
    descriptor = artifact_descriptor(directory, raw)
    target = Path(descriptor['local_path'])
    staging = directory / 'pending.json'
    prepared = perf_counter_ns()
    try:
        with staging.open('xb') as stream:
            require(stream.write(raw) == len(raw), 'diagnostic_artifact_short_write')
        written = perf_counter_ns()
        os.replace(staging, target)
    finally:
        if staging.exists():
            staging.unlink()
    finished = perf_counter_ns()
    return directory, descriptor, {'prepare_path_and_digest': prepared - started,
                                   'open_write_close': written - prepared,
                                   'atomic_publish': finished - written, 'total': finished - started}


def public_source(fixture):
    packet = json.loads(fixture.rx_raw)
    require(packet.get('id') == fixture.request['id']
            and packet.get('result', {}).get('isError') is False, 'expected_successful_source_reply')
    raw = packet['result']['content'][0]['text'].encode('utf-8')
    require(raw == fixture.body_raw, 'archived_response_text_changed')
    full = json.loads(raw)
    require(full['result_kind'] == 'source_region' and full['binding'] == fixture.producer['binding']
            and full['region_ref'] == fixture.producer['region_ref'], 'archived_source_binding_changed')
    return packet, full


def measure_projection(mcp, fixture, detail, image_root):
    start = perf_counter_ns()
    result = mcp._tool_result(fixture.producer, is_error=False, response_detail=detail,
                              source_region_image_root=image_root)
    return result, perf_counter_ns() - start


def encode(mcp, request, result):
    start = perf_counter_ns()
    text = mcp.wire.encode_response({'jsonrpc': '2.0', 'id': request['id'], 'result': result}, request)
    # Match the CRLF delivered by the fixed Windows text stdio endpoint.
    wire = (text.removesuffix('\n') + '\r\n').encode()
    finish_encode = perf_counter_ns()
    decoded = json.loads(wire)
    body = json.loads(decoded['result']['content'][0]['text'])
    finish_decode = perf_counter_ns()
    require(decoded.get('result') == result, 'wire_roundtrip_changed')
    return wire, body, {'encode': finish_encode - start, 'client_decode': finish_decode - finish_encode}


def scenario(mcp, fixture, name, root):
    root.mkdir()
    old_packet, full = public_source(fixture)
    image_frame = fixture.image_frame
    image_root = None if image_frame is None else Path(image_frame['image_path']).parent.parent
    legacy_result, full_projection = measure_projection(mcp, fixture, 'full', image_root)
    legacy_text = legacy_result['content'][0]['text'].encode()
    legacy_wire, legacy_body, legacy_clock = encode(mcp, fixture.request, legacy_result)
    require(len(legacy_text) == len(fixture.body_raw) and len(legacy_wire) == len(fixture.rx_raw)
            and legacy_body == full
            and legacy_result['content'][1:] == old_packet['result']['content'][1:],
            'existing_full_replay_changed_archived_facts')

    brief_result, brief_projection = measure_projection(mcp, fixture, 'brief', image_root)
    start_parse = perf_counter_ns()
    current_brief = json.loads(brief_result['content'][0]['text'])
    parse_clock = perf_counter_ns() - start_parse
    require(brief_result['content'][1:] == legacy_result['content'][1:]
            and current_brief['region_ref'] == full['region_ref']
            and current_brief['binding']['binding_sha256'] == full['binding']['binding_sha256']
            and current_brief['task_result']['facts'] == full['task_result']['facts']
            and current_brief['task_result']['source_mapping']['nearest_witness']
            == full['task_result']['source_mapping']['nearest_witness'], 'brief_lost_region_or_measurement')
    if image_frame is None:
        require(not current_brief['images'] and current_brief['observation_status'] == 'image_not_requested'
                and current_brief['visibility']['complete_witness'] is None, 'no_image_status_changed')
    else:
        row, = current_brief['images']
        path = Path(row['local_image_path'])
        require(path.is_absolute() and path.resolve(strict=True).as_posix() == row['local_image_path']
                and row['local_image_path'] == Path(image_frame['image_path']).as_posix()
                and row['image_sha256'] == digest(fixture.image_raw)
                and row['image_ref'] == image_frame['image_ref'] == full['facts']['visibility']['complete_witness']['image_ref']
                and row['frame_identity'] == image_frame['frame_identity']
                and current_brief['visibility']['complete_witness'] == full['facts']['visibility']['complete_witness'],
                'known_png_witness_does_not_match_archived_source')

    directory, link, publication = publish(root / 'artifacts', fixture.body_raw)
    start_link = perf_counter_ns()
    first_text = json_bytes({**current_brief, 'diagnostic_artifact': link})
    link_clock = perf_counter_ns() - start_link
    require(len(first_text) <= 10800, 'first_packet_exceeds_10800')
    first = {**brief_result, 'content': [{'type': 'text', 'text': first_text.decode()},
                                        *brief_result['content'][1:]]}
    first_wire, consumer_body, first_clock = encode(mcp, fixture.request, first)
    consumer_ref = consumer_body['diagnostic_artifact']
    read_started = perf_counter_ns()
    retrieved = resolve_diagnostic(directory, consumer_ref, fixture, pointer=DIAGNOSTIC_POINTER)
    retrieve_clock = perf_counter_ns() - read_started
    require(retrieved['body_raw'] == fixture.body_raw
            and retrieved['diagnostic'] == full['source_mapping']['triangles_source_vertices'],
            'consumer_read_was_not_original_full_text_and_diagnostic')

    files = {'ORIGINAL_TX.bin': fixture.tx_raw, 'ORIGINAL_RX.bin': fixture.rx_raw,
             'ORIGINAL_PRODUCER.json': fixture.producer_raw, 'FIRST_RX.bin': first_wire,
             'READBACK.json': retrieved['body_raw'], 'REPLAYED_FULL_RX.bin': legacy_wire}
    if fixture.image_raw is not None:
        files['ORIGINAL.png'] = fixture.image_raw
    for destination, payload in files.items():
        (root/destination).write_bytes(payload)
    save(root, 'READBACK_RECEIPT.json', {key: value for key, value in retrieved.items() if key != 'body_raw'})

    old_wire_bytes, first_wire_bytes = len(fixture.rx_raw), len(first_wire)
    old_text_bytes, first_text_bytes = len(fixture.body_raw), len(first_text)
    first_elapsed = brief_projection + parse_clock + publication['total'] + link_clock + sum(first_clock.values())
    record = {
        'case': name, 'diagnostic_pointer': DIAGNOSTIC_POINTER, 'original_full_text_sha256': digest(fixture.body_raw),
        'original_request_bytes': len(fixture.tx_raw),
        'same_png_bytes': len(fixture.image_raw or b''), 'file': link,
        'proof': {'readback_exact_full_bytes': True, 'first_keeps_public_measurement_and_image': True,
                  'current_full_replay_JSON_values_identical': True,
                  'current_full_replay_raw_text_identical': legacy_text == fixture.body_raw},
        'legacy_full_once': {'response_wire_bytes': old_wire_bytes, 'public_text_bytes': old_text_bytes,
                             'diagnostic_file_publish_bytes': 0, 'diagnostic_retrieved_bytes': 0,
                             'local_replay_projection_ns': full_projection, **legacy_clock,
                             'total_local_replay_ns': full_projection + sum(legacy_clock.values())},
        'first_only': {'response_wire_bytes': first_wire_bytes, 'public_text_bytes': first_text_bytes,
                       'diagnostic_file_publish_bytes': old_text_bytes, 'diagnostic_retrieved_bytes': 0,
                       'current_brief_projection_ns': brief_projection, 'file_publish_ns': publication,
                       'parse_existing_brief_text_ns': parse_clock,
                       'insert_descriptor_and_reencode_text_ns': link_clock, **first_clock,
                       'total_local_replay_ns': first_elapsed},
        'first_and_full_read': {'response_wire_bytes': first_wire_bytes, 'diagnostic_retrieved_bytes': old_text_bytes,
                                'consumer_wire_plus_file_bytes': first_wire_bytes + old_text_bytes,
                                'increase_over_legacy_wire_bytes': first_wire_bytes + old_text_bytes - old_wire_bytes,
                                'read_wall_ns': retrieve_clock, 'reader_stages_ns': retrieved['timing_ns'],
                                'total_local_replay_ns': first_elapsed + retrieve_clock},
    }
    save(root, 'COST.json', record)
    return record


def controls(fixtures, results, output):
    output.mkdir()
    fixture = fixtures['no_image']
    peer = fixtures['image']
    descriptor = results['no_image']['file']
    root = Path(descriptor['local_path']).parent
    hits = []

    wrong_archive, wrong_archive_descriptor, _ = publish(output/'wrong_archive', peer.body_raw)
    damaged = b'[' + fixture.body_raw[1:]
    same_length = output/'wrong_digest'
    same_length.mkdir()
    original_name = dict(descriptor, local_path=(same_length / Path(descriptor['local_path']).name).as_posix())
    Path(original_name['local_path']).write_bytes(damaged)

    stale_expected = deepcopy(fixture.producer)
    stale_expected['region_ref']['capture_generation']['revision'] += 1
    stale = replace(fixture, producer=stale_expected)
    wrong_frame = replace(peer, image_frame=dict(peer.image_frame, frame_identity='0'*64))
    peer_link = results['image']['file']
    alias = Path(descriptor['local_path'])
    lost = dict(descriptor)
    lost.pop('local_path')
    absent_file = output/'missing_file'
    absent_file.mkdir()
    absent = dict(descriptor, local_path=(absent_file / alias.name).as_posix())
    for case, scope, link, expected, pointer, reason in (
        ('wrong_other_snapshot', wrong_archive, wrong_archive_descriptor, fixture, DIAGNOSTIC_POINTER,
         'diagnostic_artifact_size_binding_mismatch'),
        ('same_length_wrong_file_contents', same_length, original_name, fixture, DIAGNOSTIC_POINTER,
         'diagnostic_artifact_actual_bytes_or_digest_mismatch'),
        ('descriptor_wrong_digest', root, dict(descriptor, sha256='0'*64), fixture, DIAGNOSTIC_POINTER,
         'diagnostic_artifact_digest_binding_mismatch'),
        ('stale_capture_against_newer_expected_revision', root, descriptor, stale, DIAGNOSTIC_POINTER,
         'diagnostic_artifact_scene_or_region_binding_mismatch'),
        ('wrong_image_frame_identity', Path(peer_link['local_path']).parent, peer_link, wrong_frame, DIAGNOSTIC_POINTER,
         'diagnostic_artifact_frame_binding_mismatch'),
        ('missing_path_member', root, lost, fixture, DIAGNOSTIC_POINTER, 'invalid_diagnostic_artifact_descriptor'),
        ('missing_file', absent_file, absent, fixture, DIAGNOSTIC_POINTER, FileNotFoundError),
        ('wrong_absolute_root', wrong_archive, descriptor, fixture, DIAGNOSTIC_POINTER,
         'diagnostic_artifact_noncanonical_or_wrong_root'),
        ('attached_path_alias', root, dict(descriptor, local_path=alias.with_name(alias.name.upper()).as_posix()),
         fixture, DIAGNOSTIC_POINTER, 'diagnostic_artifact_noncanonical_or_wrong_root'),
        ('invalid_pointer', root, descriptor, fixture, '/source_mapping/absent_diagnostic', KeyError),
    ):
        try:
            resolve_diagnostic(scope, link, expected, pointer=pointer)
        except (ValueError, OSError, KeyError) as error:
            expected_failure = isinstance(error, reason) if isinstance(reason, type) else str(error) == reason
            require(expected_failure, 'control_raised_wrong_error/' + case)
            hits.append({'case': case, 'error': str(error), 'error_type': type(error).__name__})
        else:
            raise ValueError('control_wrongly_accepted/' + case)
    false_rx = json.loads(fixture.rx_raw)
    false_rx['result']['isError'] = True
    try:
        public_source(replace(fixture, rx_raw=json_bytes(false_rx)))
    except ValueError as error:
        hits.append({'case': 'error_reply_has_no_artifact', 'error': str(error), 'error_type': type(error).__name__})
    else:
        raise ValueError('error_reply_wrongly_accepted')
    require(len(hits) == 11, 'control_denominator_changed')
    save(output, 'CONTROLS.json', {'passed': len(hits), 'planned': 11, 'cases': hits})
    return hits


def run(output):
    mcp = verified_product()
    fixtures = load_fixtures()
    require(set(fixtures) == {'no_image', 'image'}, 'frozen_fixture_roster_changed')
    output.mkdir(parents=True, exist_ok=False)
    target = output.resolve(strict=True)
    raw = {label: scenario(mcp, fixtures[label], label, target/label) for label in ('no_image', 'image')}
    hits = controls(fixtures, raw, target/'controls')
    result = {'provenance': {label: fixture.receipts for label, fixture in fixtures.items()},
              'install': {'git': COMMIT, 'runtime_source_sha256': SOURCE_SHA, 'wheel_sha256': WHEEL_SHA, 'sources': 143},
              'cases': raw, 'controls_passed': len(hits), 'controls_planned': 11,
              'new_blender': 0, 'new_model': 0, 'new_raster': 0, 'new_product_build': 0}
    save(target, 'PROTOTYPE.json', result)
    print(json.dumps({'cases': {tag: row['first_only']['public_text_bytes'] for tag, row in raw.items()},
                      'controls_passed': len(hits)}))


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'use_pinned_interpreter_I_B')
    run(Path(sys.argv[1]))

"""Audit the two historical full results and resolve a snapshot independently."""

import argparse
import base64
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
import json
from pathlib import Path
from time import perf_counter_ns
from zipfile import ZipFile


V = Path(__file__).resolve().parents[2]
DIAGNOSTIC_POINTER = '/source_mapping/triangles_source_vertices'
FIXED = {
    'no_image': {
        'namespace': 'perf050_source_scope_rank_transfer_recovery_001',
        'commit': '007de68c',
        'archive_sha256': 'fef71aa0e06b589e386783f800ee67f507cc10b8a78bcd69de29d3b02f93810c',
        'text_sha256': '048791d3b052c74d1f30e915f465c3e38155ea0f3d4ad3b0eaf81b62ad6fc559',
        'text_bytes': 39717,
        'image_bytes': 0,
        'target': 'Obj_07',
        'reference': 'Obj_05',
        'source_faces': [0, 1, 2, 3],
    },
    'image': {
        'namespace': 'perf050_dual_region_occlusion_transfer_001',
        'commit': 'ac593f97',
        'archive_sha256': 'a750e623fee4737c14eeef3552deb59ddfc2bc5cc70ebd4009606a58d2ebcf36',
        'text_sha256': 'db06caf63baeb77534d1d94c13ea9c65f6f781b7aa47d2541ea456c78f5e77ff',
        'text_bytes': 62318,
        'image_sha256': '33e798129d7352ddc9eaa01ee3998e22ab221a79e8e71f1b7d3940cbf8b43341',
        'image_bytes': 3156,
        'target': 'Obj_02',
        'reference': 'Obj_03',
        'source_faces': [0, 1],
    },
}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(raw):
    return sha256(raw).hexdigest()


def serialized(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def pin(path):
    raw = path.read_bytes()
    return {'path': path.resolve().as_posix(), 'bytes': len(raw), 'sha256': digest(raw)}


@dataclass(frozen=True)
class Fixture:
    label: str
    commit: str
    request: dict
    producer: dict
    producer_raw: bytes
    tx_raw: bytes
    rx_raw: bytes
    body_raw: bytes
    body_sha256: str
    body: dict
    image_raw: bytes | None
    image_frame: dict | None
    receipts: dict
    original_profile: dict


def choose(doc, pointer):
    """Read an RFC 6901 reference's value without rewriting the evidence."""
    require(type(pointer) is str and (pointer == '' or pointer.startswith('/')), 'invalid_diagnostic_pointer')
    if pointer == '':
        return doc
    for raw in pointer[1:].split('/'):
        require('~' not in raw.replace('~0', '').replace('~1', ''), 'invalid_diagnostic_pointer_escape')
        token = raw.replace('~1', '/').replace('~0', '~')
        if isinstance(doc, list):
            require(token.isascii() and token.isdecimal() and (len(token) == 1 or token[0] != '0'),
                    'invalid_diagnostic_pointer_index')
            doc = doc[int(token)]
        else:
            doc = doc[token]
    return doc


def profile(body_raw, body, image):
    require(body_raw == serialized(body), 'full_compact_UTF8_does_not_match_original_wire')
    task = body['task_result']
    matching = body['binding'] == task['binding'] and serialized(body['binding']) == serialized(task['binding'])
    require(matching and body['region_ref'] == task['region_ref'], 'duplicate_binding_or_region_ref_differs')
    exact = {
        'parent_binding': len(serialized(body['binding'])),
        'duplicated_task_binding': len(serialized(task['binding'])),
        'source_index_mapping': len(serialized(body['source_mapping'])),
        'task_source_index_mapping': len(serialized(task['source_mapping'])),
        'direct_region_reference': len(serialized(body['region_ref'])),
        'nested_region_reference': len(serialized(task['region_ref'])),
        'observed_frames': len(serialized(body['frames'])),
        'constructed_frames': len(serialized(body['constructed_frames'])) if 'constructed_frames' in body else 0,
        'observation_stages': len(serialized(body['stages'])),
        'generation_stages': len(serialized(body['generation_stages'])),
        'work': len(serialized(body['work'])),
        'generation_work': len(serialized(body['generation_work'])),
        'genuine_measurement_facts': len(serialized(task['facts'])),
        'selected_diagnostic_value': len(serialized(choose(body, DIAGNOSTIC_POINTER))),
    }
    return {'field_size_definition': 'exact compact UTF-8 bytes of the JSON field value, excluding its key and delimiters',
            'original_text_B': len(body_raw), 'original_PNG_B': len(image) if image is not None else 0,
            'identical_binding_values': matching, 'values_B': exact}


def load_fixture(label):
    fixed = FIXED[label]
    directory = V / fixed['namespace']
    index_path = directory / 'RUNTIME_INDEX.json'
    index = json.loads(index_path.read_bytes())
    archive_path = Path(index['archive']['path'])
    archive_pin = pin(archive_path)
    require((archive_pin['sha256'], archive_pin['bytes']) == (index['archive']['sha256'], index['archive']['bytes'])
            and archive_pin['sha256'] == fixed['archive_sha256'], 'original_runtime_archive_changed/' + label)
    members = {row['path']: row for row in index['files']}
    receipts = {'archive': archive_pin, 'index': pin(index_path), 'members': {}}
    prefix = 'slots/P1/'
    call = 'product_calls/call_001/'
    original = 'product_full/call_001/'
    with ZipFile(archive_path) as archive:
        require(len(members) == index['count'] and set(members) == set(archive.namelist()),
                'original_runtime_roster_changed/' + label)

        def take(suffix):
            named = prefix + suffix
            raw = archive.read(named)
            recorded = members[named]
            p = archive_path.parent / named
            require(len(raw) == recorded['bytes'] and digest(raw) == recorded['sha256'] and raw == p.read_bytes(),
                    'checked_member_changed/' + named)
            receipts['members'][suffix] = {'bytes': len(raw), 'sha256': recorded['sha256'],
                                           'path': p.resolve().as_posix(), 'member': named}
            return raw

        request = json.loads(take(call + 'REQUEST.json'))
        args = request['params']['arguments']
        expected = {'mode': 'source_region', 'reference': {'name': fixed['reference']},
                    'region': {'object': {'name': fixed['target']}, 'source_triangle_indices': fixed['source_faces']},
                    'requested_facts': ['surface_proximity']}
        require(request['method'] == 'tools/call' and request['params']['name'] == 'human_eye_scene_observe'
                and args == {'include_image': bool(fixed['image_bytes']), 'query': expected, 'response_detail': 'full'},
                'frozen_actual_request_changed/' + label)
        entries = [json.loads(line) for line in take('PUBLIC_REQUESTS.jsonl').splitlines() if line.strip()]
        public, = [line for line in entries if line['index'] == 1 and line['request'] == request]
        receipt = public['receipt']
        thread = f"mcp/rpc_{receipt['index']:02}/"
        tx, rx = take(thread + 'TX.bin'), take(thread + 'RX.bin')
        reply = json.loads(rx)
        require(json.loads(tx) == request and reply['id'] == request['id'] and receipt['id'] == request['id']
                and receipt['TX_bytes'] == len(tx) and receipt['RX_bytes'] == len(rx)
                and receipt['RX_sha256'] == digest(rx) and receipt['error'] is None
                and json.loads(take(call + 'RESPONSE.json')) == reply
                and json.loads(take('owner/tool_01/PRODUCT_RESPONSE.json')) == reply
                and json.loads(take('owner/tool_01/RESPONSE.json'))['result'] == reply['result'],
                'actual_transmitted_packet_or_forwarded_content_changed/' + label)
        info = public['producer_archive']
        producer_raw = take(original + 'SERVICE_RESULT.json')
        require(info['sha256'] == digest(producer_raw) and info['new_observations_for_archive'] == 0
                and Path(info['path']).read_bytes() == producer_raw
                and 'same returned producer object' in info['scope'],
                'same_request_producer_identity_changed/' + label)
        producer = json.loads(producer_raw)
        take(original + 'READ_CONTEXT.json')
        result = reply['result']
        first, *image_blocks = result['content']
        require(first['type'] == 'text' and not result['isError'], 'actual_full_body_not_successful/' + label)
        original_raw = first['text'].encode('utf-8')
        body = json.loads(original_raw)
        require((len(original_raw), digest(original_raw)) == (fixed['text_bytes'], fixed['text_sha256'])
                and {key: val for key, val in producer.items() if key != 'image_delivery'}
                == {key: val for key, val in body.items() if key != 'image_delivery'}
                and body['result_kind'] == 'source_region' and body['read_only'] is True
                and body['execution_authority'] is False
                and body['region_ref']['source_triangle_indices'] == fixed['source_faces']
                and body['facts']['region']['object_name'] == fixed['target']
                and body['task_result']['reference']['name'] == fixed['reference'],
                'original_full_facts_binding_or_body_bytes_changed/' + label)
        closure = json.loads(take('SLOT_RESULT.json'))
        require(closure['status'] == 'completed' and closure['closure_verification']['passed'],
                'historical_slot_was_not_completed_and_closed/' + label)
        visibility = body['facts']['visibility']
        image_raw = frame = None
        expected_images = int(bool(fixed['image_bytes']))
        require(len(image_blocks) == len(body['frames']) == expected_images
                and body['image_delivery']['mcp_content_constructed_image_count'] == expected_images
                and body['image_delivery']['local_verified_image_count'] == expected_images
                and producer['image_delivery']['local_verified'] == expected_images,
                'historical_png_ledger_or_block_count_changed/' + label)
        if expected_images:
            media, = image_blocks
            frame, = body['frames']
            image_raw = base64.b64decode(media['data'], validate=True)
            source_png = Path(frame['image_path'])
            p = source_png.relative_to(archive_path.parent / prefix).as_posix()
            witness = visibility['complete_witness']
            identity = (body['region_ref']['region_id'], frame['frame_identity'], frame['image_sha256'])
            expected_ref = 'source-region-image:' + digest(json.dumps(
                identity, sort_keys=True, separators=(',', ':'), default=str).encode())
            require(media['type'] == 'image' and media['mimeType'] == 'image/png'
                    and image_raw.startswith(b'\x89PNG\r\n\x1a\n')
                    and len(image_raw) == frame['PNG_bytes'] == fixed['image_bytes']
                    and digest(image_raw) == frame['image_sha256'] == fixed['image_sha256']
                    and image_raw == take(p) == (directory / 'evidence/P1-SCENE.png').read_bytes()
                    and frame['host_binding_sha256'] == body['binding']['binding_sha256']
                    and frame['source_revision'] == body['binding']['scene_revision']
                    and frame['display_identity'] == body['binding']['display_identity']
                    and frame['scene_identity'] == body['binding']['geometry_identity']
                    and body['constructed_frames'] == [frame]
                    and witness['image_ref'] == frame['image_ref'] == expected_ref
                    and witness['frame_identity'] == frame['frame_identity']
                    and witness['view_name'] == frame['view_name'] == 'SCENE'
                    and witness['geometry_status'] == 'complete'
                    and witness['selected_surface_pixels'] == 50557
                    and witness['contrasting_boundary_pixels'] == 926
                    and body['work']['raster_attempts'] == body['work']['raster_completed'] == 1,
                    'actual_complete_witness_or_PNG_changed/' + label)
            arrays = Path(frame['arrays_path']).relative_to(archive_path.parent / prefix).as_posix()
            require(digest(take(arrays)) == frame['arrays_sha256'], 'archived_frame_arrays_changed/' + label)
        else:
            require(body.get('constructed_frames', []) == [] and visibility['complete_witness'] is None
                    and visibility['reason'] == 'image_not_requested'
                    and body['work']['raster_attempts'] == body['work']['raster_completed'] == 0,
                    'archived_no_image_control_changed')
    receipts['transport'] = receipt
    receipts['producer_formatting_difference'] = 'image_delivery ledger only'
    return Fixture(label, fixed['commit'], request, producer, producer_raw, tx, rx, original_raw,
                   fixed['text_sha256'], body, image_raw, frame, receipts, profile(original_raw, body, image_raw))


def load_fixtures():
    return {label: load_fixture(label) for label in FIXED}


def resolve_diagnostic(root, descriptor, fixture, pointer=DIAGNOSTIC_POINTER):
    """Resolve an exact historical snapshot with independently pinned expectations."""
    started = perf_counter_ns()
    require(type(descriptor) is dict and set(descriptor) == {'local_path', 'sha256', 'bytes'},
            'invalid_diagnostic_artifact_descriptor')
    expected_sha = fixture.body_sha256
    expected_length = len(fixture.body_raw)
    require(type(descriptor['bytes']) is int and descriptor['bytes'] == expected_length,
            'diagnostic_artifact_size_binding_mismatch')
    require(type(descriptor['sha256']) is str and descriptor['sha256'] == expected_sha,
            'diagnostic_artifact_digest_binding_mismatch')
    root = Path(root).resolve(strict=True)
    expected_path = root / (expected_sha + '.json')
    require(type(descriptor['local_path']) is str and descriptor['local_path'] == expected_path.as_posix(),
            'diagnostic_artifact_noncanonical_or_wrong_root')
    require(expected_path.resolve(strict=True).as_posix() == descriptor['local_path'] and expected_path.is_file(),
            'diagnostic_artifact_path_alias_or_not_a_file')
    path_check = perf_counter_ns() - started
    started = perf_counter_ns()
    with expected_path.open('rb') as stream:
        raw = stream.read(expected_length + 1)
    read_ns = perf_counter_ns() - started
    started = perf_counter_ns()
    require(len(raw) == expected_length and compare_digest(digest(raw), descriptor['sha256']),
            'diagnostic_artifact_actual_bytes_or_digest_mismatch')
    body = json.loads(raw)
    pinned = fixture.producer
    require(body['binding'] == body['task_result']['binding'] == pinned['binding']
            and body['region_ref'] == body['task_result']['region_ref'] == pinned['region_ref'],
            'diagnostic_artifact_scene_or_region_binding_mismatch')
    frame = fixture.image_frame
    if frame is not None:
        actual, = body['frames']
        fields = ('frame_identity', 'image_sha256', 'image_ref', 'image_path', 'host_binding_sha256', 'source_revision')
        require(all(actual[key] == frame[key] for key in fields)
                and body['facts']['visibility']['complete_witness']['image_ref'] == frame['image_ref'],
                'diagnostic_artifact_frame_binding_mismatch')
    else:
        require(body['frames'] == [] and body['facts']['visibility']['complete_witness'] is None,
                'diagnostic_artifact_expected_zero_image')
    verify_ns = path_check + perf_counter_ns() - started
    started = perf_counter_ns()
    selected = choose(body, pointer)
    select_ns = perf_counter_ns() - started
    return {
        'body_raw': raw, 'diagnostic': selected, 'pointer': pointer,
        'timing_ns': {'read': read_ns, 'verify': verify_ns, 'select': select_ns},
        'history': {'region_ref': body['region_ref'], 'body_sha256': expected_sha,
                    'binding_sha256': body['binding']['binding_sha256'], 'source_commit': fixture.commit,
                    'frame_identity': frame['frame_identity'] if frame else None,
                    'source_kind': 'historical_observation_snapshot'},
    }


def report(fixtures):
    return {
        label: {
            'source_commit': fixture.commit, 'request': fixture.request,
            **fixture.original_profile, 'body_sha256': fixture.body_sha256,
            'binding_sha256': fixture.body['binding']['binding_sha256'], 'region_ref': fixture.body['region_ref'],
            'diagnostic_pointer': DIAGNOSTIC_POINTER,
            'selected_diagnostic': choose(fixture.body, DIAGNOSTIC_POINTER),
            'historical_measurement_facts': fixture.body['task_result']['facts'],
            'historical_visibility_status': fixture.body['facts']['visibility']['status'],
            'historical_complete_witness': fixture.body['facts']['visibility']['complete_witness'],
            'original_receipts': fixture.receipts,
        }
        for label, fixture in fixtures.items()
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    summary = report(load_fixtures())
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')

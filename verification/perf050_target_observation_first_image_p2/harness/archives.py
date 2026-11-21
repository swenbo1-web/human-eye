"""Independently bind the historical complete-frame MCP and CLI receipts."""

import base64
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile


ARCHIVE_ROOT = Path('D:/he_perf050_readonly_product_transfer_001')
ARCHIVE_HASH = 'a9137fd155103d65d914cce847f7675cc8e0dbe09af2b00f30e7dcafd70b02fe'
TRANSFER = 'perf050_readonly_product_transfer_001'
GOOD_PRODUCT = 'm1_target_observation_first_image_path_windows_001'
GOOD_SOURCE = 'eaccba2ec88abc035c62841a765f99ecae5f50e34dd8e7867b09dc17cb6d9dc9'
GOOD_REPLAY = '1b633b584220d6440813934903b487b8dbbdf35cf1bf00909c0d4845e6746acf'
SOURCE_SHA = 'f44dce705fe0eeea2a11df63baed856131a7b26be267a66404e385d095e0639a'
ORIGINAL_IMAGES = (
    (2580, '1ada614acfce81b7c8ca867c16fb0bca85e83292b009c2137324584e52ffddff'),
    (2526, '4a69c9a0c955be1527564d9df02db9fbfcdbad95bfd836deb7fd6afd04c75157'),
)


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(data):
    return sha256(data).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': digest(data)}


def images(reply):
    return [base64.b64decode(row['data'], validate=True) for row in reply['content'] if row['type'] == 'image']


def rows(data):
    return [json.loads(line) for line in data.splitlines() if line.strip()]


class Archive:
    def __init__(self, root, index, expected_archive, count):
        self.root = root.resolve()
        index = Path(index)
        self.pointer = read(index)
        self.files = {row['path']: row for row in self.pointer['files']}
        arc = self.root / 'ORIGINAL_RUNTIME.zip'
        identity = pin(arc)
        require(len(self.files) == count == self.pointer['count']
                and identity['sha256'] == expected_archive == self.pointer['archive']['sha256'],
                'historical_capsule_identity_changed')
        self.archive = ZipFile(arc)
        require(set(self.archive.namelist()) == self.files.keys(), 'historical_capsule_member_set_changed')
        self.pins = {str(index.resolve()): pin(index), str(arc): identity}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.archive.close()

    def member(self, path):
        path = Path(path)
        path = path if path.is_absolute() else self.root / path
        require(path.resolve(strict=True) == path and path.is_relative_to(self.root),
                'historical_capsule_file_outside_root')
        relative = path.relative_to(self.root).as_posix()
        data = path.read_bytes()
        identity = {'path': str(path), 'bytes': len(data), 'sha256': digest(data)}
        require(self.files[relative] == {**identity, 'path': relative} and data == self.archive.read(relative),
                'historical_capsule_original_bytes_changed/' + relative)
        self.pins[str(path)] = identity
        return data

    def json(self, path):
        return json.loads(self.member(path))


def outer_packet(archive, slot, attempt, contracts, events):
    contract, = [row for row in contracts if row['attempt'] == attempt]
    refs = [path for path in archive.files if path.startswith(slot + '/consumer/attachments/')
            and path.endswith('/RX.bin') and archive.files[path]['sha256'] == contract['RX_sha256']]
    path, = [Path(value) for value in refs]
    recorded_tx, recorded_rx = (archive.member(path.with_name(name)) for name in ('TX.bin', 'RX.bin'))
    receipt = archive.json(path.with_name('RECEIPT.json'))
    message, response = json.loads(recorded_tx), json.loads(recorded_rx)
    tool = archive.json(f'{slot}/owner/tool_{attempt:02}/RESPONSE.json')
    caller = contract['caller_identity']
    source, = [event['item'] for event in events if event.get('type') == 'item.completed'
               and event.get('item', {}).get('id') == caller['CLI_event_item_id']]
    require(receipt == contract['receipt'] and receipt['attempt'] == attempt
            and contract['reason'] == 'content_and_envelope_match'
            and digest(recorded_tx) == contract['TX_sha256']
            and digest(recorded_rx) == contract['RX_sha256']
            and message == archive.json(f'{slot}/owner/tool_{attempt:02}/REQUEST.json')
            and response == tool and message['params']['arguments'] == source['arguments']
            and message['params']['name'] == source['tool']
            and response['result']['content'] == source['result']['content']
            and len(images(response['result'])) == contract['CLI_images'], 'archived_attempt_to_CLI_changed')
    return message, response, {
        'attempt': attempt, 'id': message['id'], 'tx_sha256': digest(recorded_tx),
        'rx_sha256': digest(recorded_rx), 'image_count': contract['CLI_images'],
        'CLI_event_id': caller['CLI_event_item_id'], 'CLI_received_ns': contract['CLI_received_ns'],
    }


def target_original(repo):
    index = repo / 'verification' / TRANSFER / 'RUNTIME_INDEX.json'
    slot = 'slots/P1'
    with Archive(ARCHIVE_ROOT, index, ARCHIVE_HASH, 376) as arc:
        close = arc.json(f'{slot}/SLOT_RESULT.json')
        pub = arc.json(f'{slot}/SLOT_PUBLICATION.json')
        runtime_close = arc.json(f'{slot}/RUNTIME_CLOSE.json')
        owner_close = arc.json(f'{slot}/owner/CLOSE.json')
        require(close['status'] == pub['status'] == 'completed' and close['closure_verification']['passed']
                and close['independent_before_after']['passed'] and owner_close['confirmed']
                and not owner_close['errors'] and not owner_close['transport_errors']
                and pub['result_sha256'] == digest(arc.member(f'{slot}/SLOT_RESULT.json')),
                'original_P1_slot_closure_missing')
        contracts = arc.json(f'{slot}/consumer/BUSINESS_SOURCE_BINDING.json')['result_contracts']
        events = rows(arc.member(f'{slot}/consumer/stdout.raw.bin'))
        outer = [outer_packet(arc, slot, attempt, contracts, events) for attempt in (2, 3)]
        request = arc.json(f'{slot}/mcp/rpc_05/TX.bin')
        response = arc.json(f'{slot}/mcp/rpc_05/RX.bin')
        body = json.loads(response['result']['content'][0]['text'])
        producer_raw = arc.member(f'{slot}/product_full/call_002/SERVICE_RESULT.json')
        producer = json.loads(producer_raw)
        expected = {'include_image': True, 'response_detail': 'brief', 'query': {
            'mode': 'active_observation', 'objects': [{'name': 'M09'}],
            'task_query': {'mode': 'task', 'objects': [{'name': 'M09'}, {'name': 'M03'}],
                           'requested_facts': ['surface_proximity']}}}
        require(request['params']['arguments'] == expected
                and request['params'] == {key: outer[0][0]['params'][key] for key in ('name', 'arguments')}
                and response['result'] == outer[0][1]['result']
                and body['schema'] == 'active-observation-brief-v5'
                and producer['binding']['capture_scope'] == 'target_observation_meshes'
                and digest(producer_raw) == SOURCE_SHA
                and producer['work']['raster_attempts'] == 2
                and 'local_image_path' not in body['images']['columns'],
                'original_P1_target_request_or_missing_path_evidence_changed')
        frames = {}
        native = images(response['result'])
        require(tuple((len(raw), digest(raw)) for raw in native) == ORIGINAL_IMAGES,
                'original_target_images_changed')
        for frame, raw in zip(producer['frames'], native, strict=True):
            filename = frame['image_path']
            require(frame['image_sha256'] == digest(raw) and arc.member(filename) == raw,
                    'archived_frame_and_PNG_not_bound')
            frames[filename] = raw
            frames[frame['arrays_path']] = arc.member(frame['arrays_path'])
        old_read = outer[1][1]['result']
        path = json.loads(old_read['content'][0]['text'].splitlines()[1])
        require(path['local_image_path'] == Path(producer['frames'][1]['image_path']).as_posix()
                and path['image_sha256'] == ORIGINAL_IMAGES[1][1]
                and images(old_read) == [native[1]], 'original_P1_third_call_does_not_deliver_same_LEFT')
        scene = arc.json(f'{slot}/TERMINAL_SOURCE.json')
        initial = arc.json(f'{slot}/initial_capture/TERMINAL_SOURCE.json')
        require(scene['objects'] == initial['objects'] and scene['display_object_mask'] == [True] * 21,
                'source_current_geometry_changed')
        return {'request': request, 'response': response, 'producer': producer, 'frames': frames,
                'scene': scene, 'old_read': path, 'outer': [row[2] for row in outer],
                'close': runtime_close, 'pins': list(arc.pins.values())}


def current_reference(repo):
    root = repo / 'verification' / GOOD_PRODUCT / 'checks'
    replay_path = root / 'REPLAY.json'
    byte_path = root / 'BYTE_CONTROLS.json'
    wire_path = root / 'CANDIDATE_DISPATCH_RX.bin'
    replay, byte = read(replay_path), read(byte_path)
    raw = wire_path.read_bytes()
    require(digest(raw) == GOOD_REPLAY and replay['passed'] and byte['passed']
            and replay['candidate_source_sha256'] == byte['candidate_source_sha256'] == GOOD_SOURCE,
            'Windows_accepted_frozen_first_reply_changed')
    packet = json.loads(raw)
    body = json.loads(packet['result']['content'][0]['text'])
    index = body['images']['columns'].index('local_image_path')
    require(body['images']['rows'][0][index] is None
            and body['images']['rows'][1][index].endswith('002-20a985e3ab3309b646fe0a5a.png')
            and tuple((len(x), digest(x)) for x in images(packet['result'])) == ORIGINAL_IMAGES,
            'Windows_candidate_reference_does_not_bind_actual_original_PNG')
    return packet, [pin(path) for path in (replay_path, byte_path, wire_path)]


def ordinary_original(repo):
    index = repo / 'verification' / TRANSFER / 'RUNTIME_INDEX.json'
    slot = 'slots/N1'
    with Archive(ARCHIVE_ROOT, index, ARCHIVE_HASH, 376) as arc:
        contracts = arc.json(f'{slot}/consumer/BUSINESS_SOURCE_BINDING.json')['result_contracts']
        events = rows(arc.member(f'{slot}/consumer/stdout.raw.bin'))
        request, reply, evidence = outer_packet(arc, slot, 7, contracts, events)
        parsed = json.loads(reply['result']['content'][0]['text'])
        metadata = parsed['frame']
        photo, = images(reply['result'])
        row, = [row for row in arc.json(f'{slot}/DEVICE_EVIDENCE.json')['frames'] if row['ref'] == metadata['ref']]
        caption = json.loads(reply['result']['content'][-2]['text'].split('\n', 1)[1])
        require(arc.member(row['PNG']) == photo
                and request['params']['name'] == 'render_local'
                and Path(caption['local_image_path']) == Path(row['PNG'])
                and digest(photo) == row['PNG_sha256'] == caption['image_sha256'],
                'native_final_frame_not_exact_archival_actual_PNG')
        npz = arc.member(row['NPZ'])
        require(digest(npz) == row['NPZ_sha256'], 'native_final_frame_arrays_not_archival')
        return {'row': row, 'png': photo, 'npz': npz, 'evidence': evidence, 'pins': list(arc.pins.values())}


def region_original(repo):
    key = 'm5_joint_brief_source_projection_recovery_001'
    index = repo / 'verification' / key / 'RUNTIME_INDEX.json'
    with Archive(Path('D:/he_' + key), index,
                 '8d6c39fb458dbf9d426366261f75bab63f4589ea18e3002d1cd3113cb81f20b1', 133) as arc:
        slot = 'slots/B'
        req = arc.json(f'{slot}/product_calls/call_001/REQUEST.json')
        reply = arc.json(f'{slot}/product_calls/call_001/RESPONSE.json')['result']
        value = arc.json(f'{slot}/product_full/call_001/SERVICE_RESULT.json')
        body = json.loads(reply['content'][0]['text'])
        require(req['params']['arguments']['query']['region_task'] and
                value['binding']['capture_scope'] == 'complete_scene_meshes'
                and body['schema'] == 'active-observation-region-task-brief-v2', 'whole_scene_fixture_changed')
        for frame, raw in zip(value['frames'], images(reply), strict=True):
            require(frame['image_sha256'] == digest(raw) and arc.member(frame['image_path']) == raw,
                    'whole_scene_witness_archive_PNG_unbound')
        return {'request': req, 'reply': reply, 'producer': value, 'pins': list(arc.pins.values()),
                'state': arc.root / slot / 'product_state.json'}
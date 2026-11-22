"""Authenticated original task #2 and its original ordered capture transport."""

from functools import lru_cache
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
ORIGINAL = V / 'm1_source_region_no_image_native_transfer_001'
ORIGINAL_ROOT = Path('D:/he_m1_source_region_no_image_native_transfer_001')
EXTERNAL = Path('D:/he_m3_whole_object_witness_triangle_001')
INDEX_SHA256 = 'd0b56ef683a1f5de79ef2ceeecdf28076514e5eba3f31055eec5920e3a6b71ba'
LABELS = ('P1', 'P2', 'P3')


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def compact(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf8')


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    with Path(path).open('xb') as stream:
        stream.write(compact(value) + b'\n')


def append(path, value):
    with Path(path).open('ab') as stream:
        stream.write(compact(value) + b'\n')


def pin(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


@lru_cache
def fixture(label):
    require(label in LABELS, 'three_original_formal_sources_required')
    index_path = ORIGINAL / 'RAW_INDEX.json'
    require(pin(index_path)['sha256'] == INDEX_SHA256, 'original_4268_index_changed')
    index = read(index_path)
    package_path = ORIGINAL / index['archive']['name']
    package_pin = pin(package_path)
    require((package_pin['sha256'], package_pin['bytes']) ==
            (index['archive']['sha256'], index['archive']['bytes']), 'original_4268_archive_changed')
    pins = [pin(index_path), package_pin]

    def member(relative):
        path = ORIGINAL_ROOT / 'slots' / label / relative
        actual = pin(path)
        key = 'runtime/slots/' + label + '/' + relative
        require(index['members'][key] == {'bytes': actual['bytes'], 'sha256': actual['sha256']},
                'original_member_changed/' + key)
        raw = path.read_bytes()
        with ZipFile(package_path) as package:
            require(package.read(key) == raw, 'original_zip_disk_mismatch/' + key)
        pins.append(actual)
        return json.loads(raw)

    request = member('product_calls/call_002/REQUEST.json')
    response = member('product_calls/call_002/RESPONSE.json')
    producer = member('product_full/call_002/SERVICE_RESULT.json')
    # Model tool #4 was its third product invocation, not product call_004.
    supplement = member('product_full/call_003/SERVICE_RESULT.json')
    request4 = member('product_calls/call_003/REQUEST.json')
    terminal = member('initial_capture/TERMINAL_SOURCE.json')
    deltas = []
    for number in ('002', '003'):
        packet = member('native/WIRE/' + number + '/RESPONSE.bin')
        text = packet['result']['result']
        require(text.startswith('HUMAN_EYE_BLENDER_MCP:'), 'actual_original_capture_protocol_required')
        delta = json.loads(text.split(':', 1)[1])['result']
        require(delta['schema'] == 'human-eye-scene-delta-v1', 'actual_scene_delta_required')
        deltas.append(delta)
    args = request['params']['arguments']
    require(request['params']['name'] == 'human_eye_scene_observe'
            and args['include_image'] is False and args['response_detail'] == 'full'
            and args['query']['mode'] == 'task' and len(args['query']['objects']) == 2
            and args['query']['requested_facts'] == ['surface_proximity'], 'original_ordered_task_2_required')
    require(len(deltas[0]['resources']) == 21 and not deltas[1]['resources']
            and deltas[1]['capture']['capture_scope'] == 'selected_objects'
            and len(deltas[1]['capture']['meshes']) == 2,
            'original_full_resource_prime_then_exact_selected_capture_required')
    return {'label': label, 'request': request, 'response': response, 'producer': producer,
            'supplement': supplement, 'supplement_request': request4, 'terminal': terminal,
            'prime_delta': deltas[0], 'task_delta': deltas[1], 'pins': pins}

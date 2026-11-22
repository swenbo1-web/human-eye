"""Seven frozen directions and authentic prior successful wire materials."""

from functools import lru_cache
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
EXTERNAL = Path('D:/he_m3_whole_object_rounded_witness_001')
DIRECT_PYTHON = Path('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
PRIOR_NS = V / 'm3_whole_object_witness_triangle_consumption_001'
PRIOR_ROOT = Path('D:/he_m3_whole_object_witness_triangle_consumption_001')
PRIOR_INDEX = '21d99413b5968604f97301dfce5616f653b078d03358c337368f8b56a6dccdd9'
CASES = {
    'linear_m01_m03': ('f5469', ('M01', 'M03')),
    'linear_m03_m01': ('f5469', ('M03', 'M01')),
    'linear_m16_m20': ('f5469', ('M16', 'M20')),
    'linear_m20_m16': ('f5469', ('M20', 'M16')),
    'tree_n02_n03': ('91129', ('N02', 'N03')),
    'success_m16_m19': ('actual_B1', ('M16', 'M19')),
    'success_m16_m14': ('actual_B1', ('M16', 'M14')),
}
LABELS = tuple(CASES)


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
def prior_member(relative):
    index_path = PRIOR_NS / 'RAW_INDEX.json'
    require(pin(index_path)['sha256'] == PRIOR_INDEX, 'prior_success_index_changed')
    index = read(index_path)
    package = PRIOR_NS / index['archive']['name']
    pp = pin(package)
    require((pp['sha256'], pp['bytes']) == (index['archive']['sha256'], index['archive']['bytes']),
            'prior_success_archive_changed')
    path = PRIOR_ROOT / 'slots/B1' / relative
    actual = pin(path)
    key = 'runtime/slots/B1/' + relative
    require(index['members'][key] == {'bytes': actual['bytes'], 'sha256': actual['sha256']},
            'prior_success_member_changed/' + relative)
    raw = path.read_bytes()
    with ZipFile(package) as archive:
        require(archive.read(key) == raw, 'prior_success_zip_disk_mismatch/' + relative)
    return json.loads(raw), [pin(index_path), pp, actual]


def delta(number):
    reply, pins = prior_member('native/WIRE/' + number + '/RESPONSE.bin')
    text = reply['result']['result']
    require(text.startswith('HUMAN_EYE_BLENDER_MCP:'), 'actual_prior_capture_protocol_required')
    packet = json.loads(text.split(':', 1)[1])['result']
    require(packet['schema'] == 'human-eye-scene-delta-v1', 'actual_prior_scene_delta_required')
    return packet, pins


def fixture(label):
    require(label in CASES, 'frozen_rounded_witness_case_required')
    family, names = CASES[label]
    if family == 'actual_B1':
        ordinal = '001' if names[1] == 'M19' else '002'
        request, rp = prior_member('product_calls/call_' + ordinal + '/REQUEST.json')
        response, wp = prior_member('product_calls/call_' + ordinal + '/RESPONSE.json')
        producer, pp = prior_member('product_full/call_' + ordinal + '/SERVICE_RESULT.json')
        first, dp = delta('002')
        if ordinal == '002':
            task, tp = delta('003')
            primes = [first]
        else:
            task, tp, primes = first, [], []
        require(request['params']['arguments']['query']['objects'] == [{'name': name} for name in names],
                'prior_success_original_order_changed')
        return {'label': label, 'family': family, 'names': names, 'request': request,
            'response': response, 'producer': producer, 'prime_packets': primes,
            'task_delta': task, 'pins': [*rp, *wp, *pp, *dp, *tp],
            'capture_kind': 'original_successful_ordered_selected_capture'}
    request = {'jsonrpc': '2.0', 'id': label, 'method': 'tools/call', 'params': {
        'name': 'human_eye_scene_observe', 'arguments': {'include_image': False, 'response_detail': 'full',
            'query': {'mode': 'task', 'objects': [{'name': name} for name in names],
                      'requested_facts': ['surface_proximity']}}}}
    return {'label': label, 'family': family, 'names': names, 'request': request,
        'pins': [], 'prime_packets': [], 'capture_kind': 'derived_selected_scope_from_pinned_real_geometry'}

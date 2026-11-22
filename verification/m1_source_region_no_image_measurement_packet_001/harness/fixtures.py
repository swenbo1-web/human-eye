"""Immutable archived requests, producers and original surface-source mappings."""

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from runpy import run_path
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
HOLDOUT = 'm1_region_task_first_packet_consumption_holdout_recovery_001'
INDEPENDENT = 'perf050_source_scope_rank_transfer_recovery_001'
POSITIVE_NAMES = ('holdout_A1', 'holdout_B1', 'independent_P1')


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def compact(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf8')


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


@lru_cache
def archive_scope(batch):
    namespace = V / batch
    external = Path('D:/he_' + batch)
    source = namespace / ('RAW_INDEX.json' if (namespace / 'RAW_INDEX.json').exists() else 'RUNTIME_INDEX.json')
    index = read(source)
    if 'members' in index:
        archive = namespace / index['archive']['name']
        members, prefix = index['members'], 'runtime/'
    else:
        archive = Path(index['archive']['path'])
        members, prefix = {row['path']: row for row in index['files']}, ''
    actual = pin(archive)
    require(actual['bytes'] == index['archive']['bytes'] and actual['sha256'] == index['archive']['sha256'],
            'original_archive_identity_changed/' + batch)
    return external, archive, members, prefix, [pin(source), actual]


@lru_cache
def archived(batch, relative):
    external, archive, members, prefix, pins = archive_scope(batch)
    path = external / relative
    raw = path.read_bytes()
    expected = members[prefix + relative]
    actual = pin(path)
    require(actual['bytes'] == expected['bytes'] and actual['sha256'] == expected['sha256'],
            'original_disk_member_changed/' + relative)
    with ZipFile(archive) as package:
        require(package.read(prefix + relative) == raw, 'original_zip_member_changed/' + relative)
    return json.loads(raw), actual


def original_order(value, public):
    if type(value) is dict and type(public) is dict:
        order = [key for key in public if key in value] + [key for key in value if key not in public]
        return {key: original_order(value[key], public.get(key)) for key in order}
    if type(value) is list and type(public) is list and len(value) == len(public):
        return [original_order(a, b) for a, b in zip(value, public, strict=True)]
    return value


@lru_cache
def fixture(batch, slot, ordinal):
    base = 'slots/' + slot
    suffix = 'call_' + str(ordinal).zfill(3)
    producer, pp = archived(batch, base + '/product_full/' + suffix + '/SERVICE_RESULT.json')
    request, rp = archived(batch, base + '/product_calls/' + suffix + '/REQUEST.json')
    response, wp = archived(batch, base + '/product_calls/' + suffix + '/RESPONSE.json')
    require(request['params']['name'] == 'human_eye_scene_observe' and response['result']['isError'] is False,
            'successful_original_observe_required')
    public = json.loads(response['result']['content'][0]['text'])
    ordered = original_order(producer, public) if request['params']['arguments'].get('response_detail') == 'full' else producer
    require(ordered == producer, 'restoring_key_order_changed_original_value')
    return {'case': batch + '/' + slot + '/' + suffix, 'batch': batch, 'slot': slot,
            'producer': ordered, 'request': request['params']['arguments'], 'response': response,
            'producer_source': pp, 'request_source': rp, 'response_source': wp,
            'pins': [*archive_scope(batch)[4], pp, rp, wp]}


@lru_cache
def positive(name):
    require(name in POSITIVE_NAMES, 'registered_positive_case_required')
    if name == 'independent_P1':
        first = fixture(INDEPENDENT, 'P1', 1)
        second = deepcopy(first)
        second['request']['response_detail'] = 'brief'
        derivation = 'Only response_detail=brief derived from original full #1; original #3 has another reference.'
    else:
        slot = name.rsplit('_', 1)[1]
        first, second = fixture(HOLDOUT, slot, 2), fixture(HOLDOUT, slot, 3)
        require({key: value for key, value in first['request'].items() if key != 'response_detail'} ==
                {key: value for key, value in second['request'].items() if key != 'response_detail'},
                'original_full_brief_queries_differ')
        derivation = 'Both requests and producers are the original full #2 and brief #3.'
    terminal, tp = archived(first['batch'], 'slots/' + first['slot'] + '/TERMINAL_SOURCE.json')
    counts = {row['object_id']: row['evaluated']['triangles'] for row in terminal['objects']}
    capture = {'meshes': [{'faces': counts[row['host_id']]} for row in first['producer']['binding']['objects']]}
    config, cp = archived(first['batch'], 'slots/' + first['slot'] + '/PRODUCT_CONFIG.json')
    return {'name': name, 'full': first, 'brief': second, 'capture': capture, 'config': config,
            'derivation': derivation, 'pins': [*first['pins'], *second['pins'], tp, cp]}


@lru_cache
def compatibility():
    legacy = run_path(str(V / 'm1_region_task_brief_client_profile_001/product_replay.py'))
    old = legacy['fixtures']('P3')
    cases = {}
    for name, key in (('source_image_unknown', 'source_unknown'), ('active_prediction', 'no_image_prediction'),
                      ('active_target', 'other_observation')):
        rec = deepcopy(old[key])
        batch, slot, _ = rec['case'].split('/')
        rec.update(batch=batch, slot=slot)
        config, cp = archived(batch, 'slots/' + slot + '/PRODUCT_CONFIG.json')
        cases[name] = {'name': name, 'records': [rec], 'config': config,
                       'pins': [*rec['pins'], cp], 'mutations': []}
    image = fixture(INDEPENDENT, 'P1', 2)
    config, cp = archived(INDEPENDENT, 'slots/P1/PRODUCT_CONFIG.json')
    cases['source_image_sampled'] = {'name': 'source_image_sampled', 'records': [image],
                                    'config': config, 'pins': [*image['pins'], cp], 'mutations': []}
    target = fixture('perf050_readonly_product_transfer_001', 'P1', 2)
    config, cp = archived(target['batch'], 'slots/P1/PRODUCT_CONFIG.json')
    cases['active_target_path'] = {'name': 'active_target_path', 'records': [target],
                                   'config': config, 'pins': [*target['pins'], cp], 'mutations': []}
    base = positive('holdout_A1')
    for name in ('partial', 'unknown', 'missing_distance', 'unmeasured_fact'):
        rec = deepcopy(base['full'])
        if name in ('partial', 'unknown'):
            rec['producer']['status'] = name
            mutation = 'producer.status=' + name
        elif name == 'missing_distance':
            del rec['producer']['task_result']['facts']['surface_proximity']['value']['distance_m']
            mutation = 'remove task_result.facts.surface_proximity.value.distance_m'
        else:
            rec['producer']['task_result']['facts']['surface_proximity']['status'] = 'unknown'
            mutation = 'task_result.facts.surface_proximity.status=unknown'
        cases[name] = {'name': name, 'records': [rec], 'config': base['config'],
                       'capture': base['capture'], 'pins': base['pins'], 'mutations': [mutation]}
    return cases


def dataset(name):
    if name in POSITIVE_NAMES:
        data = positive(name)
        return {**data, 'records': [data['full'], data['brief']], 'mutations': []}
    return compatibility()[name]

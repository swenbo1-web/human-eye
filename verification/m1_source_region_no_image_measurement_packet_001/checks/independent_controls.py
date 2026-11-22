"""Compare the two installed MCP dispatchers over sealed producers in memory."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys


NS = Path(__file__).resolve().parents[1]
BASE = NS.parent / 'm1_region_task_witness_image_path_001/install/PRODUCT_RUN_BINDING.json'
CANDIDATE = NS / 'install/PRODUCT_RUN_BINDING.json'
OUTPUT = Path('D:/he_m1_source_region_no_image_measurement_packet_001/independent_controls.json')
EXPECTED = {'baseline': '1535d08ac5124b5fe117101806ae3c85d47247fe',
            'candidate': '34372f04143535b6990a45956aa74d210e726b29'}
TOOL = 'human_eye_scene_observe'
OLD_GUIDE = 'response_detail=full'
NEW_GUIDE = 'response_detail=full on the standard endpoint'
COMPACT = 'source-region-brief-v2'
FULL = 'human-eye-source-region-observation-v1'


def wire(value, *, canonical=False):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=canonical,
                      separators=(',', ':')).encode('utf8')


def digest(raw):
    return sha256(raw).hexdigest()


def require(ok, case):
    if not ok:
        raise ValueError('independent_control/' + case)


def altered(template, mutation):
    producer, arguments = deepcopy(template['producer']), deepcopy(template['request'])
    mutation(producer, arguments)
    return producer, arguments


def surface(producer):
    return producer['task_result']['facts']['surface_proximity']


def zero_distance(producer, arguments):
    fact = surface(producer)
    fact.update(direction_status='not_applicable', direction_reason='undefined_zero_distance')
    proof = fact['value']['nearest_witness']
    fact['value']['distance_m'] = 0.0
    proof.update(b=deepcopy(proof['a']), direction_a_to_b=None)


def region_ref(producer, arguments):
    query = arguments['query']
    query.pop('region')
    query['region_ref'] = deepcopy(producer['region_ref'])


def measure_shape(producer, arguments):
    producer['task_result']['measurement_scope'] = 'whole_objects'


def inspect(arm):
    binding_path = BASE if arm == 'baseline' else CANDIDATE
    install = json.loads(binding_path.read_bytes())
    require(install['preparation_git'] == EXPECTED[arm] and len(install['source_manifest']) == 143,
            'fixed_install_identity/' + arm)
    sys.path[:0] = [install['install_root'], install['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp

    module = Path(mcp.__file__).resolve(strict=True)
    rel = module.relative_to(Path(install['install_root']).resolve()).as_posix()
    module_sha = digest(module.read_bytes())
    require(module_sha == {p['path']: p['sha256'] for p in install['source_manifest']}[rel],
            'actual_loaded_dispatcher_identity/' + arm)
    fixture = run_path(str(NS / 'harness/fixtures.py'))
    control = {}

    def capture(key, producer, arguments, *, flag=True, service_error=None):
        raw_producer, raw_args = wire(producer), wire(arguments)
        calls = []

        class ArchiveService:
            def observe(self, session, **kwargs):
                calls.append((session, kwargs))
                if service_error:
                    raise ValueError(service_error)
                return producer

            def _check_request_budget(self, stage):
                pass

        server = mcp.LiveSpatialMCPServer(ArchiveService(), 'independent-audit', region_task_evidence=flag)
        request = {'jsonrpc': '2.0', 'id': 'memory', 'method': 'tools/call',
                   'params': {'name': TOOL, 'arguments': arguments}}
        result = server.handle_jsonrpc_message(request)['result']
        require(wire(producer) == raw_producer and wire(arguments) == raw_args, 'in_place_mutation/' + key)
        text = result['content'][0]['text']
        body = json.loads(text)
        semantic = deepcopy(body)
        semantic.pop('details', None)
        control[key] = {
            'body_bytes': len(text.encode('utf8')), 'content_sha256': digest(wire(result)),
            'canonical_body_sha256': digest(wire(body, canonical=True)),
            'body_without_details_sha256': digest(wire(semantic, canonical=True)),
            'schema': body.get('schema'), 'details': body.get('details'), 'error': body.get('error'),
            'is_error': result['isError'], 'image_blocks': len(result['content']) - 1,
            'service_count': len(calls), 'service_args_sha256': digest(wire(calls)),
        }
        if calls:
            expected = {name: arguments[name] for name in ('query', 'include_image') if name in arguments}
            require('response_detail' not in calls[0][1]
                    and all(calls[0][1][name] == supplied for name, supplied in expected.items()),
                    'changed_service_arguments/' + key)

    for name in fixture['POSITIVE_NAMES']:
        data = fixture['positive'](name)
        first, brief = data['full'], data['brief']
        capture(name + '/standard_full', first['producer'], first['request'], flag=False)
        capture(name + '/standard_brief', brief['producer'], brief['request'], flag=False)
        capture(name + '/evidence_full', first['producer'], first['request'])
        capture(name + '/evidence_brief', brief['producer'], brief['request'])
        capture(name + '/evidence_omitted', *altered(first, lambda p, a: a.pop('response_detail')))
        capture(name + '/evidence_ref', *altered(first, region_ref))

    first = fixture['positive']('holdout_A1')['full']
    negatives = {
        'missing_source_mapping': lambda p, a: p['task_result'].pop('source_mapping'),
        'missing_nearest_source_map': lambda p, a: p['task_result']['source_mapping'].pop('nearest_witness'),
        'missing_nearest_points': lambda p, a: surface(p)['value'].pop('nearest_witness'),
        'point_wrong_shape': lambda p, a: surface(p)['value']['nearest_witness'].update(a=[1.5, 0.5]),
        'mapping_not_measured': lambda p, a: p['task_result']['source_mapping']['nearest_witness']['b'].update(status='unknown'),
        'mapping_without_faces': lambda p, a: p['task_result']['source_mapping']['nearest_witness']['b'].update(source_triangle_indices=[]),
        'missing_distance': lambda p, a: surface(p)['value'].pop('distance_m'),
        'boolean_distance': lambda p, a: surface(p)['value'].update(distance_m=False),
        'direction_unknown': lambda p, a: surface(p).update(direction_status='unknown'),
        'positive_direction_wrong_shape': lambda p, a: surface(p)['value']['nearest_witness'].update(direction_a_to_b=[0, 0]),
        'constructed_but_not_delivered': lambda p, a: p.update(constructed_frames=[{}]),
        'partial': lambda p, a: p.update(status='partial'),
        'unknown': lambda p, a: p.update(status='unknown'),
        'wrong_measurement_scope': measure_shape,
        'omitted_image_flag': lambda p, a: a.pop('include_image'),
        'has_ambient_ordinary_mode': lambda p, a: a.update(query={'mode': 'task',
            'objects': [{'name': 'Component_417'}, {'name': 'M4_Far_00'}], 'requested_facts': ['surface_proximity']}),
    }
    for case, mutation in negatives.items():
        capture('fallback/' + case, *altered(first, mutation))

    capture('accepted_zero', *altered(first, zero_distance))
    zero_producer, zero_arguments = altered(first, zero_distance)
    surface(zero_producer)['direction_status'] = 'measured'
    capture('fallback/zero_with_direction_status', zero_producer, zero_arguments)
    capture('extra_fact', *altered(first, lambda p, a: a['query']['requested_facts'].append('aabb')))
    stale_producer, stale_arguments = altered(first, region_ref)
    stale_arguments['query']['region_ref']['document_epoch'] = '0' * 64
    capture('stale_service_result', stale_producer, stale_arguments,
            service_error='source_region_ref_document_epoch_changed')
    capture('valid_after_stale', *altered(first, region_ref))
    legacy = fixture['fixture'](fixture['INDEPENDENT'], 'P1', 2)
    capture('image_real_full', *altered(legacy, lambda p, a: a.update(response_detail='full')))
    observed = fixture['fixture'](fixture['HOLDOUT'], 'B1', 1)
    capture('region_task_real_full', observed['producer'], observed['request'])
    ordinary = fixture['fixture'](fixture['INDEPENDENT'], 'P1', 4)
    capture('whole_pair_real', ordinary['producer'], ordinary['request'])
    capture('result_kind_collision', ordinary['producer'], first['request'])
    tool_request = {'jsonrpc': '2.0', 'id': 'list', 'method': 'tools/list'}
    catalogues = {key: mcp.LiveSpatialMCPServer(object(), 'independent-audit', region_task_evidence=flag)
                  .handle_jsonrpc_message(tool_request)['result']['tools']
                  for key, flag in (('standard', False), ('evidence', True))}
    return {'module': str(module), 'module_sha256': module_sha, 'install_commit': install['preparation_git'],
            'source_sha256': install['source_sha256'], 'wheel_sha256': install['wheel_sha256'],
            'cases': control, 'catalogues': catalogues}


def run():
    state = {}
    for arm in EXPECTED:
        process = subprocess.run([sys.executable, '-I', '-B', '-X', 'utf8', str(Path(__file__).resolve()), arm],
                                 text=True, encoding='utf8', capture_output=True, check=True)
        state[arm] = json.loads(process.stdout)
    baseline, candidate = (state[arm]['cases'] for arm in EXPECTED)
    require(baseline.keys() == candidate.keys(), 'arm_case_sets')
    positive_prefixes = ('holdout_A1/', 'holdout_B1/', 'independent_P1/')
    changed = []
    for name, current in candidate.items():
        prior = baseline[name]
        require(all(current[key] == prior[key] for key in ('service_count', 'service_args_sha256')),
                'service_dispatch_changed/' + name)
        if (name.startswith(positive_prefixes) and '/evidence_' in name
                or name in ('accepted_zero', 'valid_after_stale')):
            require(current['schema'] == COMPACT and current['details'] == NEW_GUIDE and current['body_bytes'] <= 10_800
                    and current['service_count'] == 1 and not current['is_error'] and current['image_blocks'] == 0,
                    'measured_projection_missing/' + name)
            changed.append(name)
        else:
            require(current == prior, 'unrelated_original_response_changed/' + name)
    for prefix in positive_prefixes:
        pack = candidate[prefix + 'evidence_full']
        require(candidate[prefix + 'standard_full']['schema'] == FULL
                and candidate[prefix + 'standard_brief']['details'] == OLD_GUIDE
                and all(candidate[prefix + form]['canonical_body_sha256'] == pack['canonical_body_sha256']
                        for form in ('evidence_brief', 'evidence_omitted', 'evidence_ref'))
                and pack['body_without_details_sha256'] == baseline[prefix + 'standard_brief']['body_without_details_sha256'],
                'positive_fact_or_default_differed/' + prefix)
    require(all(candidate[key]['schema'] == FULL and not candidate[key]['is_error']
                for key in candidate if key.startswith('fallback/')), 'failing_closed_to_existing_full')
    require(candidate['extra_fact']['is_error'] and candidate['extra_fact']['service_count'] == 0
            and candidate['stale_service_result']['error'] == 'source_region_ref_document_epoch_changed',
            'original_diagnostic_failure_not_preserved')
    std, old = state['baseline']['catalogues']['standard'], state['baseline']['catalogues']['evidence']
    actual = state['candidate']['catalogues']['evidence']
    require(state['candidate']['catalogues']['standard'] == std, 'normal_endpoint_catalogue_changed')
    directory_delta = []
    for x, y in zip(old, actual, strict=True):
        if x != y:
            require(x['name'] == y['name'] == TOOL
                    and {key: value for key, value in x.items() if key != 'description'} ==
                    {key: value for key, value in y.items() if key != 'description'}
                    and 'Use the standard endpoint with full for the face mapping and diagnostic fields.' in y['description'],
                    'wrong_evidence_directory_change')
            directory_delta.append(len(y['description'].encode()) - len(x['description'].encode()))
    require(len(directory_delta) == 1, 'expected_exactly_one_opt_in_description_change')
    for arm in state.values():
        arm.pop('catalogues')
    return {'passed': True, 'comparison_cases': len(candidate), 'dispatcher_requests': 2 * len(candidate),
            'projected_cases': changed, 'fallback_cases': sum(key.startswith('fallback/') for key in candidate),
            'directory_description_delta_bytes': directory_delta[0],
            'scope': 'In-memory installed MCP handlers and sealed or derived service objects; stale error injected; no host, stdio or models.',
            'arms': state}


if __name__ == '__main__':
    if sys.argv[1:] in (['baseline'], ['candidate']):
        print(json.dumps(inspect(sys.argv[1]), ensure_ascii=False))
    else:
        require(sys.argv[1:] in ([], ['--check']), 'usage')
        result = run()
        packet = wire(result) + b'\n'
        if sys.argv[1:] == ['--check']:
            require(OUTPUT.read_bytes() == packet, 'receipt_not_reproducible')
        else:
            with OUTPUT.open('xb') as stream:
                stream.write(packet)
        print(json.dumps({'cases': result['comparison_cases'], 'dispatcher_requests': result['dispatcher_requests'],
                          'fallbacks': result['fallback_cases'], 'sha256': digest(packet), 'bytes': len(packet)}))

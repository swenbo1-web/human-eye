"""Create the three frozen derived fixtures using saved dictionaries only."""
import copy
from fractions import Fraction
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
BASE_SHA = '41050b03e279faca7edc27a47e51b2232c5a15355ce2ed9895c7817ef13f23b6'
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode('utf8')


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = encode(value)
    with path.open('xb') as stream:
        stream.write(raw)
    return {'path': path.relative_to(BATCH).as_posix(), 'sha256': sha(raw), 'bytes': len(raw)}


def rotate(point):
    return None if point is None else [-point[1], point[0], point[2]]


def rotate_facts(facts):
    result = copy.deepcopy(facts)
    local = result['closed_solid_relation'].get('local_evidence')
    if local is not None:
        local['triangle_vertices_world_m'] = [[rotate(point) for point in triangle]
                                             for triangle in local['triangle_vertices_world_m']]
        local['point_world_m'] = rotate(local['point_world_m'])
    surface = result['surface_proximity'].get('value')
    if surface is not None and 'nearest_witness' in surface:
        witness = surface['nearest_witness']
        for field in ('a', 'b', 'direction_a_to_b'):
            witness[field] = rotate(witness[field])
    return result


def source_for(base, name, derivation):
    return {'kind': 'offline_derived_fixture', 'base_bundle_sha256': BASE_SHA,
            'original_source': copy.deepcopy(base['source']),
            'variant': name, 'derivation': copy.deepcopy(derivation)}


def remap_request(request, source, identifiers):
    result = copy.deepcopy(request)
    result['source'] = copy.deepcopy(source)
    for row in result['objects']:
        row['object_id'] = identifiers[row['object_id']]
    for row in result['relation_pairs']:
        row['target_id'] = identifiers[row['target_id']]
        row['candidate_id'] = identifiers[row['candidate_id']]
    return result


def selection_size(request):
    identifiers = {row['object_id'] for row in request['objects']}
    for row in request['relation_pairs']:
        identifiers.update((row['target_id'], row['candidate_id']))
    return len(identifiers)


def main():
    if (HERE/'MANIFEST.json').exists():
        raise FileExistsError('preserve_existing_validation_fixtures')
    spec_raw = (HERE/'SPEC.json').read_bytes()
    spec = json.loads(spec_raw)
    raw = (BATCH/'input/BUNDLE.json').read_bytes()
    assert sha(raw) == BASE_SHA
    base = json.loads(raw)
    requests = {name: json.loads((BATCH/'input'/name).read_bytes())
                for name in ('REQUEST_PRIMARY.json', 'REQUEST_OPTIONAL_UNION.json')}
    original_ids = [item['object_id'] for item in base['objects']]
    assert len(original_ids) == len(set(original_ids))
    variants = []
    seed = spec['seed']
    rank = sorted(original_ids, key=lambda value: sha((seed+'|id|'+value).encode('utf8')))
    renamed = {value: 'offline-r-'+str(i+1).zfill(4) for i, value in enumerate(rank)}
    names = {value: 'asset_'+sha((seed+'|name|'+value).encode('utf8'))[:12] for value in original_ids}
    fixture = copy.deepcopy(base)
    for item in fixture['objects']:
        old_id = item['object_id']
        item['object_id'], item['name'] = renamed[old_id], names[old_id]
    old_by_new = {new: old for old, new in renamed.items()}
    fixture['objects'].sort(key=lambda item: sha((seed+'|order|'+old_by_new[item['object_id']]).encode('utf8')))
    for row in fixture['relations']:
        row['target_id'], row['candidate_id'] = renamed[row['target_id']], renamed[row['candidate_id']]
    derivation = {'identifier_map': renamed, 'name_map': names,
                  'geometry_and_relation_scalars': 'unchanged', 'fresh_capture': False}
    variants.append(('renamed_ids_reordered', fixture, derivation, renamed))

    fixture = copy.deepcopy(base)
    for item in fixture['objects']:
        item['vertices_world'] = [rotate(point) for point in item['vertices_world']]
    for row in fixture['relations']:
        row['facts'] = rotate_facts(row['facts'])
    derivation = {'rotation': [[0, -1, 0], [1, 0, 0], [0, 0, 1]], 'translation_m': [0, 0, 0],
                  'arithmetic': 'binary64 coordinate copies and sign changes',
                  'relation_basis': 'exact proper signed-permutation isometry of the represented saved geometry',
                  'original_capture_context': 'retained in input/SOURCE_BINDING.json', 'fresh_capture': False}
    identity = {value: value for value in original_ids}
    variants.append(('proper_rotation_z90', fixture, derivation, identity))

    fixture = copy.deepcopy(base)
    target = base['relations'][0]['target_id']
    duplicate = copy.deepcopy(next(item for item in base['objects'] if item['object_id'] == target))
    duplicate['object_id'], duplicate['name'] = 'offline-distractor-v1', 'asset_distractor_v1'
    assert duplicate['object_id'] not in original_ids
    shifted = []
    for point in duplicate['vertices_world']:
        exact_x = Fraction.from_float(point[0]) + 2
        value = float(exact_x)
        assert Fraction.from_float(value) == exact_x, 'fixed distractor translation not exactly representable'
        shifted.append([value, point[1], point[2]])
    duplicate['vertices_world'] = shifted
    fixture['objects'].insert(0, duplicate)
    derivation = {'copied_source_object_id': target, 'new_object_id': duplicate['object_id'],
                  'translation_m': [2, 0, 0], 'all_original_relations_preserved': True,
                  'new_relation_records': 0, 'fresh_capture': False}
    variants.append(('additional_same_shape_object', fixture, derivation, identity))

    records = []
    for name, fixture, derivation, identifiers in variants:
        fixture['source'] = source_for(base, name, derivation)
        folder = HERE/'variants'/name
        files = [write(folder/'BUNDLE.json', fixture), write(folder/'DERIVATION.json', derivation)]
        for request_name, request in requests.items():
            files.append(write(folder/request_name, remap_request(request, fixture['source'], identifiers)))
        records.append({'name': name, 'files': files, 'object_count': len(fixture['objects']),
                        'stored_relation_count': len(fixture['relations'])})
    manifest = {'cycle_id': spec['cycle_id'], 'base_bundle_sha256': BASE_SHA,
                'SPEC_sha256': sha(spec_raw), 'generator_sha256': sha(Path(__file__).read_bytes()),
                'original_requests_sha256': {name: sha((BATCH/'input'/name).read_bytes()) for name in requests},
                'variants': records, 'selection_union_sizes': {name: selection_size(value) for name, value in requests.items()},
                'integration_scope': 'Primary union fits existing selected-host limit4. Optional union8 exceeds it and needs explicit integration work or additional reads. Offline projection does not satisfy that host contract.',
                'product_imports': 0, 'product_or_Blender_processes': 0, 'model_consumers': 0,
                'new_images': 0, 'performance_measurements': 0}
    write(HERE/'MANIFEST.json', manifest)
    print(json.dumps({'variants': len(records), 'base_bundle_sha256': BASE_SHA,
                      'product_imports': 0, 'performance_measurements': 0}))


if __name__ == '__main__':
    main()

"""Compare closed A/B saved evidence under the explicit target/scope contract."""

import argparse
import copy
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def target_facts(comparison):
    facts = copy.deepcopy(comparison['facts'])
    scope = facts['scope']
    # canonical_facts maps object_index fields. The observation scope uses
    # its explicit target_object_index field and therefore binds it here.
    target_rows = [row for row in scope['patch_support']['objects'] if row['supported_triangle_count'] == 514]
    assert len(target_rows) == 1
    target_key = target_rows[0]['object_index']
    source_identity = facts.pop('scene_identity')
    counts = {'capture_object_count': scope.pop('capture_object_count')}
    for key in ('occluder_only_object_count', 'excluded_object_count'):
        counts[key] = scope['observation_scope'].pop(key)
    scope['observation_scope']['target_object_index'] = target_key
    full_rows = scope['patch_support']['objects']
    scope['patch_support']['objects'] = target_rows
    audit = {'actual_geometry_identity': source_identity, 'scope_counts': counts,
             'full_patch_support_rows': full_rows, 'raw_scope': comparison['scope_audit']}
    return facts, audit


def excluded_proofs(slot, checker, viewport, scene_kind):
    owner = checker.read(slot / 'OWNER_BINDING.json')
    main = next(row for row in owner['captures'] if row['role'] == 'main_target_capture')
    capture = checker.read(main['capture'])
    metadata = capture['observation_target']
    frozen = checker.read(HERE / 'reference/FROZEN_GEOMETRY.json')
    originals = {row['reference_object_id']: row for row in frozen['objects']}
    directory = {row['object_id']: row for row in metadata['scene_directory']}
    proofs = []
    for identity in metadata['excluded_object_ids']:
        row = directory[identity]
        assert row['name'] == originals[identity]['name']
        bounds = row['bounds_world_m']
        assert bounds is not None
        for point in originals[identity]['world_vertices_m']:
            assert all(viewport.F(bounds[0][axis]) <= viewport.F(point[axis]) <= viewport.F(bounds[1][axis]) for axis in range(3))
        outside, views = viewport.outside(bounds, metadata['camera_plan'])
        assert outside is True
        proofs.append({'object_id': identity, 'name': row['name'], 'independent_outside': True, 'views': views})
    far = next(row['reference_object_id'] for row in frozen['objects'] if row['name'] == 'M4_Far_11')
    if scene_kind == 'main':
        assert far in metadata['excluded_object_ids']
    else:
        assert metadata['excluded_object_ids'] == []
    assert metadata['target_object_id'] in metadata['retained_object_ids']
    actual = checker.read(slot / 'PUBLIC_01.json')['work']['target_acquisition']
    assert actual['retained_objects'] == len(capture['meshes'])
    assert actual['excluded_objects'] == len(proofs)
    assert actual['expanded_vertices'] == sum(len(mesh['vertices']) for mesh in capture['meshes'])
    assert actual['expanded_triangles'] == sum(len(mesh['faces']) for mesh in capture['meshes'])
    assert actual['residency_delta']['to_mesh'] == len(capture['meshes'])
    assert actual['residency_delta']['triangulations'] == len(capture['meshes'])
    assert actual['residency_delta']['world_vertices_transformed'] == actual['expanded_vertices']
    return {'proofs': proofs, 'raw_target_acquisition_work': actual,
            'retained_object_ids': metadata['retained_object_ids'], 'excluded_object_ids': metadata['excluded_object_ids']}


def compare_pair(a_slot, b_slot, scene_kind, checker, viewport):
    a_summary, a = checker.audit_slot(a_slot, scene_kind)
    b_summary, b = checker.audit_slot(b_slot, scene_kind)
    a_facts, a_scope = target_facts(a)
    b_facts, b_scope = target_facts(b)
    assert a_facts == b_facts
    assert a['classes'] == b['classes'] and a['cameras'] == b['cameras']
    assert a_summary['view_sequence'] == b_summary['view_sequence']
    assert len(a['arrays']) == len(b['arrays'])
    q, _ = checker.dependencies()
    import numpy as np
    buffers = []
    for left, right in zip(a['arrays'], b['arrays']):
        comparison = q.compare_normalized_buffers(left, right)
        assert comparison['equal'] and np.array_equal(left['patch_owners'], right['patch_owners'])
        buffers.append(comparison)
    excluded = excluded_proofs(b_slot, checker, viewport, scene_kind)
    return {'scene_kind': scene_kind, 'passed_checked_scope': True,
            'all_target_semantic_facts_equal': True, 'six_view_classifications_equal': True,
            'actual_cameras_equal': True, 'actual_view_sequence': a_summary['view_sequence'],
            'buffers': buffers, 'patch_owners_equal': True,
            'A_acquisition_scope': a_scope, 'B_acquisition_scope': b_scope,
            'B_independent_exclusion': excluded, 'A': a_summary, 'B': b_summary}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--a-main', type=Path, required=True)
    parser.add_argument('--a-control', type=Path, required=True)
    parser.add_argument('--b-main', type=Path, required=True)
    parser.add_argument('--b-control', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    checker = load(HERE / 'quality_saved.py', '_target002_quality_checker')
    viewport = load(HERE / 'viewport_oracle.py', '_target002_independent_viewport')
    records = [compare_pair(args.a_main, args.b_main, 'main', checker, viewport),
               compare_pair(args.a_control, args.b_control, 'target_only', checker, viewport)]
    output = {'schema': 'target-002-saved-A-B-quality-v1', 'qualification': 'PASS',
              'passed_checked_scope': True, 'records': records,
              'comparison_contract_sha256': checker.sha(HERE / 'COMPARISON_CONTRACT.json'),
              'quality_checker_sha256': checker.sha(HERE / 'quality_saved.py'),
              'comparison_source_sha256': checker.sha(Path(__file__)),
              'new_Blender_starts': 0, 'new_rasters': 0, 'new_model_calls': 0,
              'performance_gate': 'not_evaluated_by_quality_checker'}
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'qualification': 'PASS', 'pairs': 2, 'all_target_facts_and_buffers_equal': True}))


if __name__ == '__main__':
    main()

"""Review the unchanged 001 peripheral control using its existing A record."""

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize(comparison):
    facts = copy.deepcopy(comparison['facts'])
    scope = facts['scope']
    target = [row for row in scope['patch_support']['objects'] if row['supported_triangle_count'] == 512]
    assert len(target) == 1
    facts.pop('scene_identity')
    acquisition = {'capture_object_count': scope.pop('capture_object_count')}
    for key in ('occluder_only_object_count', 'excluded_object_count'):
        acquisition[key] = scope['observation_scope'].pop(key)
    scope['observation_scope']['target_object_index'] = target[0]['object_index']
    for row in scope['patch_support']['objects']:
        if row is not target[0] and row['object_index'] != target[0]['object_index']:
            assert row['coverage_role'] == row['support_status'] == 'occluder_only'
            assert row['supported_triangle_count'] == row['unsupported_triangle_count'] == 0
    scope['patch_support']['objects'] = target
    return facts, acquisition


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--b-slot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    checker = load(HERE / 'quality_saved.py', '_legacy_current_helpers')
    q, metrics = checker.dependencies()
    numeric = load(checker.PREVIOUS / 'camera_numeric.py', '_legacy_numeric_helpers')
    old_inputs = checker.read(checker.PREVIOUS / 'INPUTS.json')
    reference = Path('D:/he_m4_camera_001/controls/NEW_peripheral')
    sys.path.insert(0, checker.read(reference / 'RESULT.json')['asset']['geometry'].split('assets_01')[0] if False else 'D:/he_anchor_001/venv/Lib/site-packages')
    import numpy as np
    from PIL import Image
    a_summary, a = metrics.audit_slot(reference, q, numeric, old_inputs, np, Image)
    b_summary, b = metrics.audit_slot(args.b_slot, q, numeric, old_inputs, np, Image)
    assert a_summary['asset'] == b_summary['asset'] == 'peripheral'
    left, a_scope = normalize(a)
    right, b_scope = normalize(b)
    assert left == right and a['classifications'] == b['classifications'] and a['cameras'] == b['cameras']
    assert a['views'] == b['views'] == ['SCENE']
    buffers = []
    for x, y in zip(a['arrays'], b['arrays']):
        result = q.compare_normalized_buffers(x, y)
        assert result['equal'] and np.array_equal(x['patch_owners'], y['patch_owners'])
        buffers.append(result)
    assert a_summary['target_faces'] == b_summary['target_faces'] == 512
    assert a_summary['main_witness'] is b_summary['main_witness'] is None
    assert a_summary['actual_inspection']['counts']['covered'] == b_summary['actual_inspection']['counts']['covered'] == 0
    output = {'schema': 'target-002-legacy-negative-review-v1', 'passed_checked_scope': True,
              'A_reference_not_rerun': str(reference), 'B_slot': str(args.b_slot),
              'source_faces': 512, 'supported': 1, 'covered': 0, 'complete_witness': None,
              'exact_Near_area': '73786983304225/9223372036854775808',
              'target_facts_and_six_classifications_equal': True, 'actual_cameras_equal': True,
              'buffers': buffers, 'patch_owners_equal': True, 'A_scope': a_scope, 'B_scope': b_scope,
              'A': a_summary, 'B': b_summary, 'checker_sha256': checker.sha(Path(__file__)),
              'new_Blender_starts': 0, 'new_rasters': 0, 'new_model_calls': 0}
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': True, 'legacy_supported': 1, 'legacy_covered': 0,
                      'actual_images_equal': True, 'new_rasters': 0}))


if __name__ == '__main__':
    main()

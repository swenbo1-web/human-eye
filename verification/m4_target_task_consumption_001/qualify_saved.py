"""Source-only qualification of the two closed no-model owned sessions."""

import argparse
import hashlib
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-root', type=Path, default=Path('D:/he_m4_target_consume_001/qualification'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    saved = load(HERE / 'saved_evidence.py', '_task_consume_qualification_saved')
    truth = saved.read(HERE / 'admin/TRUTH.json')
    records, evidence = [], {}
    for slot, group in (('N_qual', 'N'), ('P_qual', 'P')):
        root = args.runtime_root / slot
        result = saved.read(root / 'SLOT_RESULT.json')
        assert result['schema'] == 'target-task-consumption-slot-v1'
        assert result['slot_id'] == slot and result['group'] == group and result['phase'] == 'qualification'
        assert result['status'] == 'completed' and result['errors'] == []
        assert result['consumer_record'] is None and result['consumer_envelope_path'] is None
        cleanup = result['cleanup']
        assert cleanup['actor_exit_code'] == 0
        assert cleanup['native']['confirmed'] is True and cleanup['native']['exit_code'] == 0
        if group == 'P':
            assert cleanup['mcp']['confirmed'] is True and cleanup['mcp']['exit_code'] == 0
        actor = cleanup['actor_close']
        assert actor['errors'] == [] and actor['bridge']['confirmed'] is True and actor['bridge']['errors'] == []
        assert actor['runtime']['errors'] == []
        native = actor['runtime']['Blender_close']
        assert native['process_reaped'] is True and native['exit_code'] == 0
        assert native['source_file_unchanged'] and native['protected_files_unchanged']
        state = actor['runtime']['Blender_status']['closed']
        assert state['initial_geometry_fingerprint'] == state['final_geometry_fingerprint']
        current = saved.evaluate_slot(root, truth)
        assert current['summary']['frames'] and all(frame['view_name'] == 'SCENE' for frame in current['summary']['frames'])
        if group == 'P':
            assert current['initial_product_entry'] and len(current['actual_product_responses']) == 1
            assert len(current['summary']['product_reviews']) == 1
            counts = current['summary']['product_reviews'][0]['counts']
            assert counts['supported'] == 2 and counts['covered'] == 1 and counts['unobserved'] == 1
        else:
            assert current['actual_product_responses'] == []
            assert any(len(row['object_names']) == 14 for row in current['summary']['source_reviews'])
        observed_images = []
        for path in current['actual_tool_results']:
            observed_images.extend(block for block in saved.read(path)['result']['content'] if block.get('type') == 'image')
        assert observed_images
        frame = current['summary']['frames'][0]
        actual_images = [hashlib.sha256(__import__('base64').b64decode(image['data'], validate=True)).hexdigest()
                         for image in observed_images]
        assert all(digest == frame['PNG_sha256'] for digest in actual_images)
        evidence[group] = current
        records.append({'slot_id': slot, 'group': group, 'passed_checked_scope': True, 'actual_model_consumers': 0,
                        'SLOT_RESULT_sha256': saved.sha(root / 'SLOT_RESULT.json'),
                        'actual_image_blocks': len(observed_images), 'actual_image_delivery_sha256': actual_images,
                        'source_and_frame_review': current['summary']})
    binding = saved.read(HERE / 'PRODUCT_RUN_BINDING.json')
    sys.path.insert(0, binding['dependency_root'])
    import numpy as np
    n_frame = next(iter(evidence['N']['normalized_arrays'].values()))
    p_frame = next(iter(evidence['P']['normalized_arrays'].values()))
    buffers = {key: bool(np.array_equal(n_frame[key], p_frame[key]))
               for key in ('color', 'depth', 'asset_owner', 'local_source_face')}
    assert all(buffers.values())
    output = {'schema': 'target-task-consumption-saved-qualification-v1', 'passed_checked_scope': True,
              'qualification': 'PASS', 'records': records, 'same_device_current_SCENE_buffers': buffers,
              'scope': 'Two original current owned no-model qualification requests. Actual P default brief and same-producer background full agree. Native raw source and actual image delivery are bound independently.',
              'unconstructed_view_pixels': 'not_run', 'no_model_qualification': True,
              'checker_sha256': saved.sha(Path(__file__)), 'saved_adapter_sha256': saved.sha(HERE / 'saved_evidence.py'),
              'new_Blender_starts': 0, 'new_rasters': 0, 'new_product_observations': 0, 'new_model_calls': 0}
    destination = args.output.resolve()
    if not destination.is_relative_to(HERE):
        raise ValueError('new_namespace_output_required')
    with destination.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'qualification': 'PASS', 'owned_saved_sessions': 2, 'new_rasters': 0, 'new_models': 0}))


if __name__ == '__main__':
    main()

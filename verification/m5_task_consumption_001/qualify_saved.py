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
    parser.add_argument('--runtime-root', type=Path, default=Path('D:/he_m5_task_consume_001/qualification'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    saved = load(HERE / 'saved_evidence.py', '_task_consume_qualification_saved')
    truth = saved.read(HERE / 'admin/TRUTH.json')
    records, evidence = [], {}
    for slot, group in (('A_qual', 'A'), ('B_qual', 'B')):
        root = args.runtime_root / slot
        result = saved.read(root / 'SLOT_RESULT.json')
        assert result['schema'] == 'target-task-consumption-slot-v1'
        assert result['slot_id'] == slot and result['group'] == group and result['phase'] == 'qualification'
        assert result['status'] == 'completed' and result['errors'] == []
        assert result['consumer_record'] is None and result['consumer_envelope_path'] is None
        cleanup = result['cleanup']
        assert cleanup['actor_exit_code'] == 0
        assert cleanup['native']['confirmed'] is True and cleanup['native']['exit_code'] == 0
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
        assert current['initial_product_entry'] and len(current['actual_product_responses']) == 1
        assert len(current['summary']['product_reviews']) == 1
        counts = current['summary']['product_reviews'][0]['counts']
        assert counts['supported'] == 2 and counts['covered'] == 1 and counts['unobserved'] == 1
        calls = current['actual_public_calls']
        assert len(calls) == (2 if group == 'A' else 1)
        assert calls[0]['public']['schema'] == 'active-observation-brief-v5'
        if group == 'A':
            assert [row['mode'] for row in calls] == ['active_observation', 'task']
            assert current['actual_batch_outer_attempts'] == [1]
            assert not current['actual_joint_public_call_indices'] and calls[1]['measurement'] is not None
        else:
            assert current['actual_joint_public_call_indices'] == [1] and not current['actual_batch_outer_attempts']
            assert calls[0]['measurement'] is not None
            assert calls[0]['measurement']['source']['passed_checked_scope']
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
    binding = saved.read(HERE / 'A_RUN_BINDING.json')
    sys.path.insert(0, binding['dependency_root'])
    import numpy as np
    a_frame = next(iter(evidence['A']['normalized_arrays'].values()))
    b_frame = next(iter(evidence['B']['normalized_arrays'].values()))
    buffers = {key: bool(np.array_equal(a_frame[key], b_frame[key]))
               for key in ('color', 'depth', 'asset_owner', 'local_source_face')}
    assert all(buffers.values())
    output = {'schema': 'm5-task-consumption-saved-qualification-v1', 'passed_checked_scope': True,
              'qualification': 'PASS', 'records': records, 'same_device_current_SCENE_buffers': buffers,
              'scope': 'Two original current owned no-model qualifications. A batch contains two real public APIs and B joint contains one. Actual default briefs, current whole-object measurements, source association and same-producer frames are independently bound.',
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

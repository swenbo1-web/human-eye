"""Five paired full-localization measurements on one existing joined SCENE.

Each implementation computes complete counts, bounds and owned anchors for
138 ROIs. The independent reference scans each target mask, while the installed
helper uses shared histograms and grouped coordinate reductions.
The controller alone releases this script after source/input freezing.
"""

import argparse
import hashlib
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import statistics
import sys
import time


PAIR_ORDER = (('reference', 'optimized'), ('optimized', 'reference'),
              ('reference', 'optimized'), ('optimized', 'reference'), ('reference', 'optimized'))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read_json(path):
    return json.loads(path.read_bytes())


def main():
    started = time.perf_counter_ns()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frame', type=Path, help='Optional exact historical SCENE descriptor, checked against REFERENCE.')
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--capture', required=True, type=Path)
    parser.add_argument('--expected', required=True, type=Path)
    parser.add_argument('--binding', required=True, type=Path)
    parser.add_argument('--bootstrap', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='New result JSON, exclusive creation.')
    args = parser.parse_args()
    helper = load_module('_patch_benchmark_verified_bootstrap', args.bootstrap.resolve())
    binding = read_json(args.binding)
    guard = helper.bootstrap(binding)
    from human_eye_plugin import active_observation_images as installed_images
    import numpy as np

    oracle_path = Path(__file__).resolve().with_name('pixel_oracle.py')
    oracle = load_module('_patch_benchmark_independent_oracle', oracle_path)
    guard.verify_loaded()
    frozen_reference = read_json(args.reference)
    reference_frames = [row for row in frozen_reference['pixel_frames'] if row['view_name'] == 'SCENE']
    oracle.require(len(reference_frames) == 1, 'one_frozen_joined_SCENE')
    frame = reference_frames[0]['frame']
    if args.frame is not None:
        oracle.require(read_json(args.frame) == frame, 'benchmark_frame_must_equal_reference')
    capture, expected = (read_json(path) for path in (args.capture, args.expected))
    oracle.require(frame['view_name'] == 'SCENE', 'existing_first_joined_SCENE_required')
    mapping = oracle.independent_mapping(capture, expected, 'joined')
    oracle.require(len(mapping['roi_ids']) == 138, 'frozen_138_patch_benchmark')
    arrays_path = oracle.historical_path(frame['arrays_path'])
    raw = arrays_path.read_bytes()
    oracle.require(hashlib.sha256(raw).hexdigest() == frame['arrays_sha256'], 'benchmark_NPZ_hash')
    with np.load(BytesIO(raw), allow_pickle=False) as saved:
        oracle.require(set(saved.files) == set(oracle.ARRAY_KEYS), 'benchmark_NPZ_keys')
        color, patches = saved['color'].copy(), saved['patch_owners'].copy()
        for name, wanted in mapping['arrays'].items():
            values = saved[name]
            oracle.require(values.dtype == wanted.dtype and np.array_equal(values, wanted), 'benchmark_' + name)
    oracle.require(color.dtype == np.uint8 and color.shape == (512, 512, 3), 'benchmark_RGB')
    oracle.require(patches.dtype == np.int32 and patches.shape == (512, 512), 'benchmark_patch_owners')
    color.setflags(write=False)
    patches.setflags(write=False)
    functions = {'reference': oracle.reference_full, 'optimized': installed_images._aggregate_patch_pixels}
    setup_closed = time.perf_counter_ns()
    calls, pairs = [], []
    for pair_index, order in enumerate(PAIR_ORDER, 1):
        outputs, times = {}, {}
        for variant in order:
            call_started = time.perf_counter_ns()
            if variant == 'optimized':
                result = functions[variant](color, patches, len(mapping['roi_ids']), include_locations=True)
            else:
                result = functions[variant](color, patches, len(mapping['roi_ids']))
            call_closed = time.perf_counter_ns()
            outputs[variant] = result
            times[variant] = call_closed - call_started
            calls.append({'pair': pair_index, 'variant': variant, 'started_ns': call_started,
                          'closed_ns': call_closed, 'elapsed_ns': call_closed - call_started})
        compare_started = time.perf_counter_ns()
        for variant in ('reference', 'optimized'):
            oracle.require(set(outputs[variant]) == set(oracle.FULL_KEYS), 'full_localization_output_keys')
            for name in oracle.COUNT_KEYS:
                values = outputs[variant][name]
                oracle.require(values.dtype == np.int64 and values.shape == (138,), variant + '_count_dtype_shape')
            for name in oracle.LOCATION_KEYS:
                oracle.require(type(outputs[variant][name]) is list and len(outputs[variant][name]) == 138,
                               variant + '_location_list_shape')
        for name in oracle.COUNT_KEYS:
            oracle.require(np.array_equal(outputs['reference'][name], outputs['optimized'][name]), 'pair_count_equality')
        for name in oracle.LOCATION_KEYS:
            oracle.require(oracle.strict_equal(outputs['reference'][name], outputs['optimized'][name]), 'pair_location_equality')
        compare_closed = time.perf_counter_ns()
        pairs.append({'pair': pair_index, 'order': list(order), 'counts_equal': True, 'locations_equal': True,
                      'reference_ns': times['reference'], 'optimized_ns': times['optimized'],
                      'optimized_over_reference': times['optimized'] / times['reference'],
                      'comparison_started_ns': compare_started, 'comparison_closed_ns': compare_closed,
                      'comparison_elapsed_ns': compare_closed - compare_started,
                      'output_counts': {name: outputs['reference'][name].tolist() for name in oracle.COUNT_KEYS},
                      'output_locations': {name: outputs['reference'][name] for name in oracle.LOCATION_KEYS}})
    guard.verify_loaded()
    summary = {}
    for variant in ('reference', 'optimized'):
        values = [row['elapsed_ns'] for row in calls if row['variant'] == variant]
        summary[variant] = {'calls': len(values), 'sum_ns': sum(values), 'median_ns': statistics.median(values),
                            'minimum_ns': min(values), 'maximum_ns': max(values), 'raw_ns': values}
    computed = time.perf_counter_ns()
    source_path = Path(installed_images.__file__).resolve()
    result = {'schema': 'region-anchors-existing-buffer-five-pair-v1', 'passed': True,
              'process_id': __import__('os').getpid(), 'python_executable': sys.executable,
              'frame_descriptor': None if args.frame is None else str(args.frame.resolve()),
              'reference_descriptor': str(args.reference.resolve()), 'arrays_path': str(arrays_path),
              'arrays_sha256': frame['arrays_sha256'], 'view_name': 'SCENE', 'representation': 'joined',
              'patch_mapping_identity': mapping['identity'], 'region_count': 138,
              'binding_path': str(args.binding.resolve()), 'binding_sha256': hashlib.sha256(args.binding.read_bytes()).hexdigest(),
              'bootstrap_path': str(args.bootstrap.resolve()),
              'bootstrap_sha256': hashlib.sha256(args.bootstrap.read_bytes()).hexdigest(),
              'installed_helper_source_path': str(source_path),
              'installed_helper_source_sha256': hashlib.sha256(source_path.read_bytes()).hexdigest(),
              'independent_reference_path': str(oracle_path),
              'independent_reference_sha256': hashlib.sha256(oracle_path.read_bytes()).hexdigest(),
              'inputs': {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in (args.reference, args.capture, args.expected)},
              'pair_order': [list(order) for order in PAIR_ORDER], 'calls': calls, 'pairs': pairs, 'summary': summary,
              'pair_ratio_median': statistics.median(row['optimized_over_reference'] for row in pairs),
              'ratio_of_medians': summary['optimized']['median_ns'] / summary['reference']['median_ns'],
              'ratio_of_sums': summary['optimized']['sum_ns'] / summary['reference']['sum_ns'],
              'tail_definition': 'maximum of five calls in each arm',
              'timing': {'started_ns': started, 'setup_closed_ns': setup_closed, 'computed_ns': computed,
                         'setup_ns': setup_closed - started, 'through_computation_ns': computed - started},
              'reference_full_calls': 5, 'optimized_full_calls': 5, 'warmup_calls': 0,
              'new_raster_calls': 0, 'new_geometry_discovery_calls': 0, 'new_model_calls': 0,
              'scope': 'One existing 512x512 joined SCENE buffer and 138 ROI IDs. Both kernels return counts, visible bounds and owned anchors. Reference scans each ROI, candidate shares group reductions. No counts-only arm.',
              'limitations': ['Five pairs are a fixed local kernel sample.',
                              'Source-guard setup, array loading, comparisons and publication are outside individual kernel clocks.',
                              'No observation, model, token, fee, CPU-RSS or former six-ROI performance claim.']}
    publication_started = time.perf_counter_ns()
    result['timing']['publication_started_ns'] = publication_started
    result['timing']['through_prepublication_ns'] = publication_started - started
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=True, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': True, 'pairs': 5, 'reference_calls': 5, 'optimized_calls': 5,
                      'new_raster_calls': 0, 'output': str(args.output.resolve()),
                      'output_closed_ns': time.perf_counter_ns()}))


if __name__ == '__main__':
    main()

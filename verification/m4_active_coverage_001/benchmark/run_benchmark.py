"""One frozen 20-pair planning benchmark, reusing the six actual image buffers."""

import argparse
from contextlib import ExitStack
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import sys
import time
import traceback
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ORDER = ('SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, default=str, sort_keys=True, allow_nan=False) + '\n').encode('utf8')


def save(path, value):
    Path(path).write_bytes(encoded(value))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def runtime_paths():
    paths = [Path(__file__), HERE / 'BENCHMARK_PLAN.json', BATCH / 'coverage.py',
             BATCH / 'inputs/SCENE_GEOMETRY_RATIONAL.json', BATCH / 'inputs/CAMERAS.json',
             BATCH / 'inputs/PRECISION.json', BATCH / 'render/adapter.py',
             BATCH / 'render/assess_readability.py', BATCH / 'render/DEPENDENCIES.json',
             BATCH / 'render/RASTER_RESULTS.json']
    dependencies = json.loads((BATCH / 'render/DEPENDENCIES.json').read_bytes())
    paths.extend(Path(name) for name in dependencies['installed_sources_sha256'])
    for name in ORDER:
        paths.extend(BATCH / 'render' / (name + suffix) for suffix in ('.json', '.png', '.npz'))
    return sorted({path.resolve() for path in paths})


def source_hashes():
    return {str(path): sha(path.read_bytes()) for path in runtime_paths()}


def verify(frozen):
    actual = source_hashes()
    if actual != frozen['inputs_sha256']:
        raise ValueError('frozen_runtime_source_or_input_changed')
    plan = json.loads((HERE / 'BENCHMARK_PLAN.json').read_bytes())
    expected = [{'pair': i, 'order': ['reference', 'optimized'] if i % 2 else ['optimized', 'reference']}
                for i in range(1, 21)]
    if plan['sequence'] != expected or plan['formal_run_count'] != 40:
        raise ValueError('fixed_twenty_pair_order_required')
    return plan


def setup():
    started = time.perf_counter_ns()
    coverage = load('_formal_active_coverage', BATCH / 'coverage.py')
    images = load('_formal_active_readability', BATCH / 'render/assess_readability.py')
    adapter = images.adapter
    scene_raw = (BATCH / 'inputs/SCENE_GEOMETRY_RATIONAL.json').read_bytes()
    camera_raw = (BATCH / 'inputs/CAMERAS.json').read_bytes()
    cameras = json.loads(camera_raw)
    if tuple(pose['name'] for pose in cameras['views']) != ORDER:
        raise ValueError('registered_six_view_order')
    if cameras['source_geometry_file_sha256'] != sha(scene_raw):
        raise ValueError('raster_geometry_source_binding')
    buffers, frames = {}, {}
    for pose in cameras['views']:
        name = pose['name']
        metadata = json.loads((BATCH / 'render' / (name + '.json')).read_bytes())
        if metadata['pose'] != pose:
            raise ValueError('frozen_raster_camera_binding')
        array_path = BATCH / 'render' / metadata['owner_depth_RGB_arrays']
        image_path = BATCH / 'render' / metadata['PNG']
        if sha(array_path.read_bytes()) != metadata['arrays_sha256'] or sha(image_path.read_bytes()) != metadata['PNG_sha256']:
            raise ValueError('frozen_image_or_buffer_binding')
        with adapter.np.load(array_path, allow_pickle=False) as stored:
            buffers[name] = {key: stored[key] for key in ('color', 'depth', 'owners')}
        for value in buffers[name].values():
            value.setflags(write=False)
        frames[name] = {'view_name': name, 'image_path': str(image_path.resolve()),
                        'image_sha256': metadata['PNG_sha256'], 'array_sha256': metadata['arrays_sha256']}
    closed = time.perf_counter_ns()
    return {'coverage': coverage, 'images': images, 'adapter': adapter, 'scene_raw': scene_raw,
            'camera_raw': camera_raw, 'camera_sha256': sha(camera_raw), 'buffers': buffers, 'frames': frames,
            'setup': {'started_ns': started, 'closed_ns': closed, 'elapsed_ns': closed - started,
                      'scope': 'Shared module import, complete input byte read, existing frozen PNG/array verification and buffer loading. No ROI discovery or candidate evaluation.',
                      'common_raster_array_payload_bytes': sum(value.nbytes for group in buffers.values() for value in group.values())}}


def prohibit_rendering(runtime):
    attempts = {'calls': 0}

    def forbidden(*args, **kwargs):
        attempts['calls'] += 1
        raise AssertionError('planning_must_reuse_frozen_images_without_rendering')

    stack = ExitStack()
    stack.enter_context(patch.object(runtime['adapter'], 'render_one', forbidden))
    for module in (runtime['adapter'], sys.modules['human_eye_plugin.attention_rendering'],
                   sys.modules['human_eye_plugin.attention_raster']):
        stack.enter_context(patch.object(module, 'rasterize_attention', forbidden))
    return stack, attempts


def planning_run(runtime, variant):
    # Called after t0: every run rebuilds its geometry, ROI/index and state.
    scene, cameras = json.loads(runtime['scene_raw']), json.loads(runtime['camera_raw'])
    coverage, adapter = runtime['coverage'], runtime['adapter']
    index = coverage.build_index(scene, cameras, variant)
    meshes = adapter.load_meshes(scene)
    pixels, frames = [], []
    for pose in cameras['views']:
        rows = adapter.readability_for_rois(meshes, pose, runtime['buffers'][pose['name']], index.regions)
        pixels.extend(rows)
        frames.append({**runtime['frames'][pose['name']],
                       'readable_roi_ids': [row['roi_id'] for row in rows if row['readable']]})
    assessment = {'scene_identity': index.scene_identity, 'candidate_identity': index.candidate_identity,
                  'source_cameras_sha256': runtime['camera_sha256'], 'frames': frames}
    state = coverage.CoverageState(index)
    steps = []
    while True:
        view = state.next_view()
        if view is None:
            break
        if view in state.observed_views:
            raise ValueError('planner_repeated_observed_view')
        receipt = runtime['images'].receipt_for_view(index, view, assessment)
        steps.append(state.observe(receipt))
    semantic = {'scene_identity': index.scene_identity, 'candidate_identity': index.candidate_identity,
                'regions': [{'roi_id': roi.roi_id, 'vertices': roi.vertices, 'normal': roi.normal}
                            for roi in index.regions],
                'view_order': index.view_order, 'view_masks': index.view_masks,
                'classifications': index.classifications, 'pixel_evidence': pixels,
                'steps': steps, 'state': state.summary()}
    metrics = {**index.stats, 'bitset_state_updates': state.updates,
               'pixel_region_tests': len(pixels), 'planning_render_calls': 0,
               'fresh_mesh_array_payload_bytes': sum(getattr(mesh, name).nbytes for mesh in meshes
                    for name in ('vertices', 'faces', 'edges', 'local_axes')),
               'exact_fraction_index_memory_bytes': None,
               'array_payload_scope': 'Actual NumPy mesh-array nbytes. Python/Fraction/index object overhead and RSS unmeasured.'}
    payload = encoded({'semantic': semantic, 'metrics': metrics})
    semantic_sha = sha(encoded(semantic))
    return payload, semantic_sha, metrics


def middle(values):
    ordered = sorted(values)
    return Fraction(ordered[9] + ordered[10], 2)


def fraction_record(value):
    return {'numerator': value.numerator, 'denominator': value.denominator, 'value': float(value)}


def summarize(rows, resolution_ns):
    succeeded = all(row['state'] == 'completed' for row in rows)
    result = {'planned_pairs': 20, 'planned_runs': 40, 'completed_runs': sum(row['state'] == 'completed' for row in rows),
              'failed_runs': sum(row['state'] == 'failed' for row in rows),
              'not_run': sum(row['state'] == 'not_run' for row in rows), 'all_runs_completed': succeeded}
    if not succeeded:
        return {**result, 'engineering_gate': False, 'time_conclusion': 'unproven_incomplete_fixed_batch'}
    reference = [row for row in rows if row['variant'] == 'reference']
    optimized = [row for row in rows if row['variant'] == 'optimized']
    pairs = []
    for pair in range(1, 21):
        ref = next(row for row in reference if row['pair'] == pair)
        opt = next(row for row in optimized if row['pair'] == pair)
        pairs.append({'pair': pair, 'reference_ns': ref['elapsed_ns'], 'optimized_ns': opt['elapsed_ns'],
                      'optimized_minus_reference_ns': opt['elapsed_ns'] - ref['elapsed_ns'],
                      'optimized_over_reference': fraction_record(Fraction(opt['elapsed_ns'], ref['elapsed_ns'])),
                      'same_semantic_result': ref['semantic_sha256'] == opt['semantic_sha256']})
    ref_median = middle([row['elapsed_ns'] for row in reference])
    opt_median = middle([row['elapsed_ns'] for row in optimized])
    ref_clips = sum(row['metrics']['exact_clips'] for row in reference)
    opt_clips = sum(row['metrics']['exact_clips'] for row in optimized)
    reduction = Fraction(ref_clips - opt_clips, ref_clips)
    equal = len({row['semantic_sha256'] for row in rows}) == 1
    unresolved = abs(ref_median - opt_median) <= 2 * resolution_ns
    observed_nonworse = opt_median <= ref_median
    return {**result, 'pairs': pairs, 'all_semantic_results_equal': equal,
            'reference_median_ns': fraction_record(ref_median), 'optimized_median_ns': fraction_record(opt_median),
            'ratio_of_medians': fraction_record(opt_median / ref_median),
            'median_pair_ratio': fraction_record(statistics.median(Fraction(row['optimized_ns'], row['reference_ns']) for row in pairs)),
            'reference_range_ns': [min(row['elapsed_ns'] for row in reference), max(row['elapsed_ns'] for row in reference)],
            'optimized_range_ns': [min(row['elapsed_ns'] for row in optimized), max(row['elapsed_ns'] for row in optimized)],
            'reference_exact_clip_sum': ref_clips, 'optimized_exact_clip_sum': opt_clips,
            'exact_clip_reduction': fraction_record(reduction), 'clip_gate_at_least_30_percent': reduction >= Fraction(3, 10),
            'observed_median_not_worse': observed_nonworse, 'clock_resolution_ns_rounded_up': resolution_ns,
            'time_conclusion': 'unresolved_at_recorded_clock_resolution' if unresolved else 'observed_median_not_worse' if observed_nonworse else 'observed_median_regression',
            'timing_scope': 'Descriptive same-process fixed paired observations. Clock criterion establishes quantization resolution only. No broader statistical conclusion.',
            'engineering_gate': None if unresolved else equal and observed_nonworse and reduction >= Fraction(3, 10)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze-runtime', action='store_true')
    mode.add_argument('--check-glue', action='store_true')
    mode.add_argument('--run-formal', action='store_true')
    args = parser.parse_args()
    freeze_path = HERE / 'FROZEN_RUNTIME.json'
    if args.freeze_runtime:
        with freeze_path.open('x', encoding='utf8') as stream:
            json.dump({'cycle': 'M4-ACTIVE-COVERAGE-001', 'inputs_sha256': source_hashes()}, stream, indent=2)
        print('runtime_hashes_frozen_without_algorithm_execution')
        return
    if args.check_glue:
        before = source_hashes()
        runtime = setup()
        guard, attempts = prohibit_rendering(runtime)
        with guard:
            ref = planning_run(runtime, 'reference')
            opt = planning_run(runtime, 'optimized')
        if ref[1] != opt[1] or attempts['calls'] or source_hashes() != before:
            raise AssertionError('development_glue_not_equivalent_or_sources_changed')
        folder = HERE / 'development'
        folder.mkdir(exist_ok=True)
        number = len(list(folder.glob('check_*.json'))) + 1
        save(folder / ('check_' + str(number).zfill(2) + '.json'), {
            'passed': True, 'performance_samples': 0, 'new_raster_calls': 0, 'semantic_sha256': ref[1],
            'reference_output_bytes': len(ref[0]), 'optimized_output_bytes': len(opt[0]), 'inputs_sha256': before})
        print('untimed_glue_equivalence_passed_no_formal_samples')
        return
    frozen = json.loads(freeze_path.read_bytes())
    plan = verify(frozen)
    with (HERE / 'BENCHMARK_STARTED.json').open('x', encoding='utf8') as stream:
        json.dump({'started_ns': time.perf_counter_ns(), 'freeze_sha256': sha(freeze_path.read_bytes()),
                   'pairs': 20, 'runs': 40}, stream)
    batch_started = time.perf_counter_ns()
    runtime = setup()
    rows = [{'pair': pair['pair'], 'variant': variant, 'state': 'not_run'}
            for pair in plan['sequence'] for variant in pair['order']]
    guard, attempts = prohibit_rendering(runtime)
    stop = None
    with guard:
        for row in rows:
            try:
                verify(frozen)
            except BaseException as error:
                stop = {'type': type(error).__name__, 'message': str(error), 'stage': 'integrity'}
                break
            started = time.perf_counter_ns()
            try:
                payload, semantic_sha, metrics = planning_run(runtime, row['variant'])
                output_bytes, output_sha = len(payload), sha(payload)
                closed = time.perf_counter_ns()
                row.update(state='completed', started_ns=started, closed_ns=closed, elapsed_ns=closed-started,
                           output_bytes=output_bytes, output_sha256=output_sha, semantic_sha256=semantic_sha, metrics=metrics)
                sample_path = HERE / ('OUTPUT_' + row['variant'].upper() + '.json')
                if not sample_path.exists():
                    with sample_path.open('xb') as sample:
                        sample.write(payload)
            except BaseException as error:
                closed = time.perf_counter_ns()
                row.update(state='failed', started_ns=started, closed_ns=closed, elapsed_ns=closed-started,
                           error={'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
            save(HERE / 'RUNS.json', {'rows': rows, 'stop': stop})
    try:
        verify(frozen)
    except BaseException as error:
        stop = {'type': type(error).__name__, 'message': str(error), 'stage': 'final_integrity'}
    clock = time.get_clock_info('perf_counter')
    resolution = math.ceil(clock.resolution * 10**9)
    summary = summarize(rows, resolution)
    if stop or attempts['calls']:
        summary['engineering_gate'] = False
    closed = time.perf_counter_ns()
    save(HERE / 'RESULTS.json', {'cycle': 'M4-ACTIVE-COVERAGE-001', 'rows': rows, 'summary': summary,
        'shared_setup': runtime['setup'], 'freeze_sha256': sha(freeze_path.read_bytes()),
        'inputs_sha256': frozen['inputs_sha256'], 'stop': stop,
        'actual_planning_render_attempts': attempts['calls'], 'new_planning_raster_calls': 0,
        'preexisting_six_image_generation_cost': json.loads((BATCH / 'render/RASTER_RESULTS.json').read_bytes()),
        'batch_started_ns': batch_started, 'batch_closed_before_result_publication_ns': closed,
        'whole_benchmark_through_analysis_ns': closed - batch_started,
        'clock': {'implementation': clock.implementation, 'resolution_seconds': clock.resolution, 'monotonic': clock.monotonic},
        'new_model_provider_Blender_API_runs': 0,
        'scope': 'One fixed 20-pair batch. Full per-run planning includes JSON decode, ROI/index, 36 actual pixel tests, delivered state and result encoding. Shared setup, integrity/progress I/O and fixed raster preparation are separate.'})
    print(json.dumps(summary))


if __name__ == '__main__':
    main()

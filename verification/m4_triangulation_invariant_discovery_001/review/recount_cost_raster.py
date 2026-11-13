"""Audit saved clocks and image buffers without calling geometry or rendering."""

from collections import defaultdict
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import statistics
import sys


sys.path.insert(0, 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Lib/site-packages')
import numpy as np
from PIL import Image


BASE = Path(__file__).resolve().parents[1]
INPUTS = {}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def raw(path):
    path = Path(path)
    data = path.read_bytes()
    INPUTS[str(path)] = digest(data)
    return data


def read(path):
    return json.loads(raw(path))


def span(row):
    result = row['closed_ns'] - row['started_ns']
    assert result == row['elapsed_ns'] and result >= 0
    return result


def json_stream(data):
    text = data.decode('utf8')
    decoder = json.JSONDecoder()
    values = []
    position = 0
    while position < len(text):
        if text[position].isspace():
            position += 1
            continue
        value, position = decoder.raw_decode(text, position)
        values.append(value)
    return values


def load_arrays(npz_path, png_path):
    npz_raw, png_raw = raw(npz_path), raw(png_path)
    with np.load(npz_path, allow_pickle=False) as stored:
        arrays = {key: stored[key] for key in stored.files}
    assert set(arrays) == {'color', 'depth', 'owners'}
    with Image.open(png_path) as image:
        assert np.array_equal(np.asarray(image), arrays['color'])
    owners, depth = arrays['owners'], arrays['depth']
    assert owners.shape == depth.shape == arrays['color'].shape[:2]
    assert np.all(np.isposinf(depth[owners < 0]))
    assert np.all(np.isfinite(depth[owners >= 0]) & (depth[owners >= 0] > 0))
    return arrays, npz_raw, png_raw


def independent_pixel_counts(arrays, rows):
    rgb = arrays['color'].astype(np.int64)
    owners = arrays['owners']
    boundary = np.zeros(owners.shape, dtype=bool)
    for axis in (0, 1):
        first = (slice(None, -1), slice(None)) if axis == 0 else (slice(None), slice(None, -1))
        second = (slice(1, None), slice(None)) if axis == 0 else (slice(None), slice(1, None))
        differences = rgb[first] - rgb[second]
        qualifies = (owners[first] != owners[second]) & ((differences * differences).sum(axis=2) >= 576)
        boundary[first] |= qualifies
        boundary[second] |= qualifies
    for row in rows:
        target = owners == row['object_index']
        assert int(target.sum()) == row['visible_surface_pixels']
        assert int((target & boundary).sum()) == row['contrasting_boundary_pixels']
        assert row['readable'] == bool(row['front_facing'] and target.sum() >= 16 and (target & boundary).sum() >= 4)


def compare_arrays(first, second, first_png, second_png):
    finite_first, finite_second = np.isfinite(first['depth']), np.isfinite(second['depth'])
    common = finite_first & finite_second
    a, b = first['depth'][common], second['depth'][common]
    delta = np.abs(a - b)
    bits_a, bits_b = a.view(np.uint64), b.view(np.uint64)
    ulps = np.maximum(bits_a, bits_b) - np.minimum(bits_a, bits_b)
    return {'RGB_equal': bool(np.array_equal(first['color'], second['color'])),
            'owners_equal': bool(np.array_equal(first['owners'], second['owners'])),
            'PNG_bytes_equal': first_png == second_png,
            'depth_hash_equal': digest(first['depth'].tobytes()) == digest(second['depth'].tobytes()),
            'finite_mask_equal': bool(np.array_equal(finite_first, finite_second)),
            'different_finite_pixel_count': int(np.count_nonzero(delta)),
            'finite_mask_disagreement_count': int(np.count_nonzero(finite_first != finite_second)),
            'common_finite_pixel_count': int(common.sum()),
            'maximum_absolute_depth_difference': float(delta.max(initial=0)),
            'maximum_positive_finite_ULP_distance': int(ulps.max(initial=0))}


def main():
    frozen = read(BASE / 'FROZEN.json')
    for path, wanted in frozen['files_sha256'].items():
        assert digest(raw(path)) == wanted
    preparation = read(BASE / 'PREPARATION.json')
    phases = []
    for name in ('proof', 'legacy', 'correctness', 'observations', 'benchmark'):
        row = read(BASE / 'execution' / (name + '_RESULT.json'))
        assert row['passed'] is True
        total = row['closed_before_result_publication_ns'] - row['started_ns']
        assert total == row['elapsed_before_result_publication_ns']
        phases.append({'phase': name, 'started_ns': row['started_ns'],
                       'closed_before_result_publication_ns': row['closed_before_result_publication_ns'],
                       'elapsed_before_publication_ns': total,
                       'intent_and_source_binding_ns': row['binding_closed_ns'] - row['started_ns'],
                       'engineering_module_import_ns': row['module_loaded_ns'] - row['binding_closed_ns'],
                       'phase_payload_and_prepublication_ns': row['closed_before_result_publication_ns'] - row['module_loaded_ns']})
    benchmark = read(BASE / 'runs/benchmark/RESULTS.json')
    stage_totals = {variant: defaultdict(int) for variant in ('reference', 'candidate')}
    for row in benchmark['rows']:
        assert row['passed'] is True
        assert sum(span(value) for value in row['stages'].values()) == row['elapsed_ns']
        for key, value in row['stages'].items():
            stage_totals[row['variant']][key] += span(value)
    pairs = []
    for number in range(1, 6):
        reference = next(row for row in benchmark['rows'] if row['pair'] == number and row['variant'] == 'reference')
        candidate = next(row for row in benchmark['rows'] if row['pair'] == number and row['variant'] == 'candidate')
        ratio = Fraction(candidate['elapsed_ns'], reference['elapsed_ns'])
        pairs.append({'pair': number, 'reference_ns': reference['elapsed_ns'], 'candidate_ns': candidate['elapsed_ns'],
                      'C_over_R': float(ratio), 'exact_ratio_numerator': ratio.numerator,
                      'exact_ratio_denominator': ratio.denominator, 'candidate_slower': ratio > 1})
    reference_total = sum(row['reference_ns'] for row in pairs)
    candidate_total = sum(row['candidate_ns'] for row in pairs)
    assert reference_total == benchmark['reference_total_ns'] and candidate_total == benchmark['candidate_total_ns']
    median_ratio = statistics.median(row['C_over_R'] for row in pairs)
    assert median_ratio == benchmark['pair_ratio_median']
    chains, frame_totals, setup_unique, loaded = [], defaultdict(int), {}, {}
    all_attempts = []
    observations = read(BASE / 'execution/observations_RESULT.json')
    for chain in observations['chains']:
        directory = Path(chain['output'])
        result, timing = read(directory / 'RESULTS.json'), read(directory / 'FINAL_TIMING.json')
        assert result['passed'] is True and len(result['frames']) == result['actual_chain_render_attempts'] == 2
        full = span(timing)
        setup = result['shared_setup']
        setup_ns = setup['closed_ns'] - setup['started_ns']
        setup_unique[(setup['started_ns'], setup['closed_ns'])] = setup_ns
        contained = timing['started_ns'] <= setup['started_ns'] <= setup['closed_ns'] <= timing['closed_ns']
        recorded = defaultdict(int)
        trace = json_stream(raw(directory / 'TRACE.jsonl'))
        intents = [value for value in trace if value['event'] == 'render_attempt']
        completions = [value for value in trace if value['event'] == 'frame_complete']
        assert len(intents) == len(completions) == 2
        for view, frame in result['frames'].items():
            assert frame['status'] == 'completed'
            attempt = frame['attempt']['attempt']
            budget = read(BASE / 'render_budget' / (str(attempt).zfill(2) + '.json'))
            assert budget == frame['attempt'] and budget['view'] == view and Path(budget['output']) == directory
            assert sum(value['attempt'] == attempt for value in intents) == 1
            assert sum(value['attempt'] == attempt for value in completions) == 1
            all_attempts.append(attempt)
            arrays, npz, png = load_arrays(frame['NPZ'], frame['PNG'])
            assert digest(npz) == frame['NPZ_sha256'] and digest(png) == frame['PNG_sha256']
            assert len(npz) == frame['NPZ_bytes'] and len(png) == frame['PNG_bytes']
            for key, array in arrays.items():
                metadata = frame['arrays'][key]
                assert digest(array.tobytes(order='C')) == metadata['sha256']
                assert list(array.shape) == metadata['shape'] and str(array.dtype) == metadata['dtype']
                assert array.nbytes == metadata['nbytes']
                frame_totals['array_payload_bytes'] += array.nbytes
            independent_pixel_counts(arrays, frame['pixel_rows'])
            loaded[(chain['scene'], chain['variant'], view)] = (arrays, png)
            frame_totals['PNG_bytes'] += len(png)
            frame_totals['NPZ_bytes'] += len(npz)
            for key, value in frame['stages'].items():
                recorded[key] += span(value)
                frame_totals[key + '_ns'] += span(value)
        contained_setup = setup_ns if contained else 0
        remainder = full - sum(recorded.values()) - contained_setup
        assert remainder >= 0
        chains.append({'scene': chain['scene'], 'variant': chain['variant'],
                       'started_ns': timing['started_ns'], 'closed_ns': timing['closed_ns'],
                       'full_chain_ns': full, 'shared_setup_started_ns': setup['started_ns'],
                       'shared_setup_closed_ns': setup['closed_ns'], 'shared_setup_ns': setup_ns,
                       'setup_contained_in_this_chain': contained,
                       'derived_after_contained_shared_setup_ns': full - contained_setup,
                       'recorded_frame_stage_ns': dict(recorded), 'unseparated_remainder_ns': remainder,
                       'remainder_scope': 'Input/index/meshes, hash/state/trace/JSON and intervening work lack separately persisted chain clocks.',
                       'selected_views': list(result['final_state']['observed_views']), 'passed': True})
    assert sorted(all_attempts) == list(range(1, 9))
    assert len(list((BASE / 'render_budget').glob('*.json'))) == 8
    comparisons = []
    for scene in ('grid4_permuted_alternating', 'grid16_permuted_alternating'):
        for view in ('SCENE', 'BACK'):
            a, apng = loaded[(scene, 'reference', view)]
            b, bpng = loaded[(scene, 'candidate', view)]
            comparison = compare_arrays(a, b, apng, bpng)
            assert all(comparison[key] for key in ('RGB_equal', 'owners_equal', 'PNG_bytes_equal', 'depth_hash_equal'))
            comparisons.append({'kind': 'same_scene_R_C', 'scene': scene, 'view': view, **comparison})
    for view in ('SCENE', 'BACK'):
        a, apng = loaded[('grid4_permuted_alternating', 'reference', view)]
        b, bpng = loaded[('grid16_permuted_alternating', 'reference', view)]
        comparisons.append({'kind': 'grid4_vs_grid16', 'view': view, **compare_arrays(a, b, apng, bpng)})
        old = BASE.parent / 'm4_active_coverage_003/runs/main_p01_A/frames' / ('01_SCENE' if view == 'SCENE' else '06_BACK')
        if (old / (view + '.npz')).exists() and (old / (view + '.png')).exists():
            original, _, original_png = load_arrays(old / (view + '.npz'), old / (view + '.png'))
            for name, arrays, png in (('grid4', a, apng), ('grid16', b, bpng)):
                comparisons.append({'kind': 'old003_original_vs_' + name, 'view': view,
                                    'old_source': str(old), **compare_arrays(original, arrays, original_png, png)})
    for phase in ('legacy', 'correctness', 'benchmark'):
        result = read(BASE / 'runs' / phase / 'RESULTS.json')
        setup = result['shared_setup']
        setup_unique[(setup['started_ns'], setup['closed_ns'])] = setup['closed_ns'] - setup['started_ns']
    partial_sum = sum(value['elapsed_before_publication_ns'] for value in phases)
    execution_span = max(value['closed_before_result_publication_ns'] for value in phases) - min(value['started_ns'] for value in phases)
    preparation_ns = preparation['closed_before_publication_ns'] - preparation['marked_preparation_started_ns']
    raw(Path(__file__).resolve())
    report = {
        'schema': 'triangulation-invariant-discovery-001-cost-raster-audit-v1', 'passed': True,
        'source_freeze_sha256': digest(raw(BASE / 'FROZEN.json')), 'frozen_sources_verified': len(frozen['files_sha256']),
        'render_counts': {'intents': 8, 'completed_frames': 8, 'PNG': 8, 'NPZ': 8, 'trace_attempts': 8,
                          'trace_completions': 8, 'failed_intents': 0, 'hard_cap': 16},
        'payload_totals': dict(frame_totals), 'RSS_bytes': None,
        'frame_stage_scope': 'Disjoint recorded frame intervals. Array payload is generated ndarray bytes, independent of RSS or peak resident memory.',
        'chains': chains, 'image_comparisons': comparisons,
        'benchmark': {'pairs': pairs, 'reference_total_ns': reference_total, 'candidate_total_ns': candidate_total,
                      'paired_ratio_median': median_ratio, 'cumulative_C_over_R': candidate_total / reference_total,
                      'candidate_slower_pairs': [row['pair'] for row in pairs if row['candidate_slower']],
                      'stage_totals_ns': {key: dict(value) for key, value in stage_totals.items()},
                      'scope': 'Only the frozen five pairs. Substage totals partition each trial; nested discovery stats are not added again.'},
        'execution_cost': {'phase_intervals': phases, 'phase_prepublication_elapsed_sum_ns': partial_sum,
                           'observed_phase_span_ns': execution_span,
                           'interphase_unallocated_wall_ns': execution_span - partial_sum,
                           'full_external_command_wall_ns': None,
                           'scope': 'execute.main after argument parsing through pre-result-publication. Interpreter startup, external command handling and final phase-result write/close are not fully bounded.'},
        'shared_setups': [{'started_ns': key[0], 'closed_ns': key[1], 'elapsed_ns': value}
                          for key, value in setup_unique.items()],
        'shared_setups_unique_total_ns': sum(setup_unique.values()),
        'setup_overlap_scope': 'Setup intervals are already nested in their phase/first-chain wall times. Repeated setup metadata in later chains is deduplicated and never added to full times.',
        'marked_preparation': {'started_ns': preparation['marked_preparation_started_ns'],
                               'closed_before_publication_ns': preparation['closed_before_publication_ns'],
                               'elapsed_ns': preparation_ns,
                               'scope': 'Marked authoring/input-proof/freeze preparation wall window. It includes waiting and unsegmented work, with no CPU-time claim.'},
        'limitations': ['First grid4 reference chain contains module setup, the other three do not. Four raw chain times are descriptive.',
                        'TRACE.jsonl stores concatenated pretty-printed JSON objects. The first line-by-line audit parser rejected that framing, then the read-only decoder used exact JSON object boundaries. Frozen trace bytes remain unchanged.',
                        'Initial per-chain input/discovery/index clocks were not persisted separately; the chain remainder stays unseparated.',
                        'Finite depth differences are measured directly. Unchanged RGB/owners preserve the observed winning-surface/pixel evidence.',
                        'Old003 data are read-only historical comparisons and incur no new raster count.'],
        'review_execution': {'new_raster_geometry_discovery_model_or_benchmark_calls': 0,
                             'scope': 'Read stored clocks, PNG/NPZ and metadata, perform pixel recount and array comparisons only.'},
        'inputs_sha256': INPUTS,
    }
    path = BASE / 'review/COST_AND_RASTER_AUDIT.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'passed': True, 'renders': 8, 'PNG_bytes': frame_totals['PNG_bytes'],
                      'NPZ_bytes': frame_totals['NPZ_bytes'], 'arrays_bytes': frame_totals['array_payload_bytes'],
                      'paired_ratio_median': median_ratio, 'cumulative_ratio': candidate_total / reference_total,
                      'new_calls': 0}))


if __name__ == '__main__':
    main()

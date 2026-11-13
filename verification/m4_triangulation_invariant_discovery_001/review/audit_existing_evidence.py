"""Read this batch's saved evidence without importing its algorithm or renderer."""

from fractions import Fraction
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Lib/site-packages')
import numpy as np
from PIL import Image


HERE = Path(__file__).resolve().parents[1]
INPUTS = {}
CHECKS = []


def read_bytes(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(raw).hexdigest()
    return raw


def load(path):
    return json.loads(read_bytes(path))


def trace_objects(path):
    text = read_bytes(path).decode('utf8').lstrip()
    decoder = json.JSONDecoder()
    rows = []
    while text:
        row, end = decoder.raw_decode(text)
        rows.append(row)
        text = text[end:].lstrip()
    return rows


def check(name, condition):
    passed = bool(condition)
    CHECKS.append({'check': name, 'passed': passed})
    if not passed:
        raise AssertionError(name)


def recount(color, depth, owners, object_ids):
    """Unique target-owned endpoints of qualifying 4-neighbor owner transitions."""
    check('array_shapes', color.shape == (512, 512, 3) and depth.shape == owners.shape == (512, 512))
    check('array_dtypes', color.dtype == np.uint8 and depth.dtype == np.float64 and owners.dtype == np.int32)
    foreground = owners >= 0
    background = owners == -1
    check('owner_domain', np.all(foreground | background) and np.all(owners[foreground] < 28))
    check('depth_background_positive_inf', np.all(np.isposinf(depth[background])))
    check('depth_foreground_finite_positive', np.all(np.isfinite(depth[foreground]) & (depth[foreground] > 0)))
    rgb = color.astype(np.int32)
    horizontal_difference = rgb[:, 1:] - rgb[:, :-1]
    vertical_difference = rgb[1:, :] - rgb[:-1, :]
    horizontal_edges = ((owners[:, 1:] != owners[:, :-1]) &
                        (np.sum(horizontal_difference ** 2, axis=2) >= 576))
    vertical_edges = ((owners[1:, :] != owners[:-1, :]) &
                      (np.sum(vertical_difference ** 2, axis=2) >= 576))
    rows = {}
    for object_id in object_ids:
        owned = owners == object_id
        boundary = np.zeros_like(owned)
        boundary[:, :-1] |= owned[:, :-1] & horizontal_edges
        boundary[:, 1:] |= owned[:, 1:] & horizontal_edges
        boundary[:-1, :] |= owned[:-1, :] & vertical_edges
        boundary[1:, :] |= owned[1:, :] & vertical_edges
        rows[object_id] = {'visible_surface_pixels': int(np.count_nonzero(owned)),
                           'contrasting_boundary_pixels': int(np.count_nonzero(boundary))}
    return rows, int(np.count_nonzero(foreground)), int(np.count_nonzero(background))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    target = parser.parse_args().output.resolve()
    if not target.is_relative_to(HERE / 'review'):
        raise ValueError('review_output_required')
    if target.exists():
        raise FileExistsError(target)
    frozen = load(HERE / 'FROZEN.json')
    frozen_sha = INPUTS[str((HERE / 'FROZEN.json').resolve())]
    check('frozen_source_count_275', len(frozen['files_sha256']) == 275)
    for path, expected in frozen['files_sha256'].items():
        check('frozen_source:' + path, hashlib.sha256(read_bytes(path)).hexdigest() == expected)
    phases = ['proof', 'legacy', 'correctness', 'observations', 'benchmark']
    phase_rows = []
    previous_closed = frozen['closed_before_publication_ns']
    for phase in phases:
        intent = load(HERE / 'execution' / (phase + '_INTENT.json'))
        result = load(HERE / 'execution' / (phase + '_RESULT.json'))
        check(phase + ':explicit_success', result['passed'] is True and 'error' not in result)
        check(phase + ':same_source', result['source_freeze_sha256'] == frozen_sha)
        check(phase + ':identity', intent['phase'] == result['phase'] == phase and
              intent['pid'] == result['pid'] and intent['started_ns'] == result['started_ns'])
        check(phase + ':source_path', Path(intent['source']).resolve() == HERE / 'execute.py')
        check(phase + ':ordered', previous_closed < result['started_ns'] < result['binding_closed_ns'] <
              result['module_loaded_ns'] < result['closed_before_result_publication_ns'])
        previous_closed = result['closed_before_result_publication_ns']
        phase_rows.append({'phase': phase, 'pid': result['pid'], 'source_freeze_sha256': frozen_sha,
                           'started_ns': result['started_ns'], 'closed_before_result_publication_ns': previous_closed})
    check('exact_five_phase_intents', sorted(p.name for p in (HERE / 'execution').glob('*_INTENT.json')) ==
          sorted(phase + '_INTENT.json' for phase in phases))
    proof = load(HERE / 'proof/EXPECTED.json')
    legacy = load(HERE / 'runs/legacy/RESULTS.json')
    expected_legacy = {key: (6 if key == 'original' else 0) for key in proof['scenes']}
    check('legacy_five_exact_rows', len(legacy['rows']) == 5 and
          {row['scene']: row['discovered_count'] for row in legacy['rows']} == expected_legacy)
    for row in legacy['rows']:
        check('legacy_source:' + row['scene'], row['source_sha256'] == proof['scenes'][row['scene']]['sha256'])
    correctness = load(HERE / 'runs/correctness/RESULTS.json')
    wanted_quality = [(scene, variant) for scene in ['original', 'grid4_uniform', 'grid4_permuted_alternating',
                      'grid16_uniform', 'grid16_permuted_alternating', 'rotated_grid4', 'hole_grid4']
                      for variant in ['reference', 'candidate']]
    check('correctness_exact14_success', correctness['passed'] is True and len(correctness['rows']) == 14 and
          all(row['passed'] is True for row in correctness['rows']) and
          [(row.get('scene', row.get('control')), row['variant']) for row in correctness['rows']] == wanted_quality)
    check('correctness_proof_and_no_raster', correctness['proof_sha256'] == INPUTS[str((HERE / 'proof/EXPECTED.json').resolve())]
          and correctness['new_renders'] == 0)
    for row in correctness['rows']:
        key = row.get('scene', row.get('control'))
        specification = proof['scenes'][key] if 'scene' in row else proof['controls'][key]
        actual_regions = row['index']['regions'] if 'scene' in row else row['regions']
        check('saved_regions_match_independent_proof:' + key,
              sorted(actual_regions, key=lambda region: region['roi_id']) ==
              sorted(specification['expected_regions'], key=lambda region: region['roi_id']))
        if 'scene' in row:
            check('correctness_trial_source:' + key, row['trial']['scene_sha256'] == specification['sha256'])
            check('saved_masks_match_independent_proof:' + key, row['index']['view_masks'] == proof['view_masks'])
            for view, regions_by_id in proof['geometry_by_view'].items():
                for identity, expected in regions_by_id.items():
                    actual = row['index']['classifications'][view][identity]
                    check('saved_classification_matches_independent_proof', actual['status'] == expected['status'] and
                          actual['complete'] is expected['complete'])
    benchmark = load(HERE / 'runs/benchmark/RESULTS.json')
    protocol = load(HERE / 'BENCHMARK_PROTOCOL.json')
    expected_trials = [(pair, variant) for pair, order in enumerate(protocol['pairs'], 1) for variant in order]
    check('exact10_benchmark_trials_no_replacements', len(benchmark['rows']) == 10 and
          [(row['pair'], row['variant']) for row in benchmark['rows']] == expected_trials and
          all(row['passed'] is True for row in benchmark['rows']) and benchmark['new_renders'] == 0)
    for row in benchmark['rows']:
        check('benchmark_source', row['scene_sha256'] == proof['scenes']['grid16_permuted_alternating']['sha256'])
    gate = load(HERE / 'PRE_BENCHMARK_GATE.json')
    check('actual_gate_precedes_benchmark', gate['source_freeze_sha256'] == frozen_sha and
          phase_rows[3]['closed_before_result_publication_ns'] < gate['qualified_before_benchmark_ns'] < phase_rows[4]['started_ns'])
    outer = load(HERE / 'execution/observations_RESULT.json')
    cameras = {row['name']: row for row in load(HERE / 'inputs/CAMERAS.json')['views']}
    expected_chains = [(scene, variant) for scene in ['grid4_permuted_alternating', 'grid16_permuted_alternating']
                       for variant in ['reference', 'candidate']]
    check('registered_four_chain_order', [(row['scene'], row['variant']) for row in outer['chains']] == expected_chains)
    budget = HERE / 'render_budget'
    intent_files = sorted(budget.glob('*.json'))
    check('exact_eight_global_intents', [path.name for path in intent_files] == [str(i).zfill(2) + '.json' for i in range(1, 9)])
    intents = {row['attempt']: row for row in [load(path) for path in intent_files]}
    frame_rows, chain_rows, observed_attempts, chains = [], [], [], {}
    for specification in outer['chains']:
        scene_key, variant = specification['scene'], specification['variant']
        folder = HERE / 'runs' / ('observe_' + scene_key + '_' + variant)
        check('chain_fixed_output', Path(specification['output']).resolve() == folder)
        result = load(folder / 'RESULTS.json')
        chains[(scene_key, variant)] = result
        check('chain_explicit_success', result['passed'] is True and result['errors'] == [] and
              result['scene'] == scene_key and result['variant'] == variant)
        check('chain_one_fixed_budget', Path(result['global_budget_directory']).resolve() == budget)
        check('chain_attempts_two', result['actual_chain_render_attempts'] == specification['render_attempts'] == len(result['frames']) == 2)
        check('chain_views_and_feedback', [step['view'] for step in result['steps']] == ['SCENE', 'BACK'] and
              [len(step['update']['new_roi_ids']) for step in result['steps']] == [2, 3] and
              result['final_pixel_shortfall_roi_ids'] == [])
        trace = trace_objects(folder / 'TRACE.jsonl')
        check('chain_exact_trace', [row['event'] for row in trace] == ['render_attempt', 'frame_complete'] * 2)
        source_scene = load(HERE / 'inputs' / ('scene_' + scene_key + '.json'))
        regions = result['index']['regions']
        covered = set()
        for position, step in enumerate(result['steps'], 1):
            view = step['view']
            frame = result['frames'][view]
            attempt = frame['attempt']['attempt']
            observed_attempts.append(attempt)
            check('intent_frame_binding', frame['attempt'] == intents[attempt] and
                  Path(intents[attempt]['output']).resolve() == folder and intents[attempt]['view'] == view and
                  intents[attempt]['variant'] == variant)
            check('trace_frame_binding', {key: value for key, value in trace[2 * (position - 1)].items() if key != 'event'} == intents[attempt]
                  and trace[2 * position - 1]['attempt'] == attempt and trace[2 * position - 1]['PNG_sha256'] == frame['PNG_sha256'])
            frame_folder = folder / ('frame_' + str(position).zfill(2) + '_' + view)
            check('frame_original_exact', load(frame_folder / 'FRAME.json') == frame and frame['status'] == 'completed')
            for suffix in ['PNG', 'NPZ']:
                path = Path(frame[suffix]).resolve()
                check('frame_fixed_path', path == frame_folder / (view + '.' + suffix.lower()))
                raw = read_bytes(path)
                check('file_hash_and_bytes:' + suffix, len(raw) == frame[suffix + '_bytes'] and
                      hashlib.sha256(raw).hexdigest() == frame[suffix + '_sha256'])
            with np.load(frame['NPZ'], allow_pickle=False) as archive:
                check('array_keys', set(archive.files) == {'color', 'depth', 'owners'})
                arrays = {key: archive[key] for key in archive.files}
            for key, value in arrays.items():
                metadata = {'dtype': str(value.dtype), 'shape': list(value.shape), 'nbytes': int(value.nbytes),
                            'sha256': hashlib.sha256(value.tobytes(order='C')).hexdigest()}
                check('raw_array_metadata:' + key, metadata == frame['arrays'][key])
            with Image.open(frame['PNG']) as image:
                check('PNG_RGB_payload', image.mode == 'RGB' and image.size == (512, 512) and
                      np.array_equal(np.asarray(image), arrays['color']))
            counts, foreground, background = recount(arrays['color'], arrays['depth'], arrays['owners'],
                                                     [row['object_index'] for row in regions])
            check('depth_counts', frame['depth_checks']['foreground_pixels'] == foreground and
                  frame['depth_checks']['background_pixels'] == background and foreground + background == 512 * 512)
            pixel_rows = {row['roi_id']: row for row in frame['pixel_rows']}
            check('six_pixel_rows_unique', len(pixel_rows) == len(frame['pixel_rows']) == 6)
            readable = []
            for region in regions:
                identity, object_id = region['roi_id'], region['object_index']
                row = pixel_rows[identity]
                front = sum(Fraction(a) * Fraction(b) for a, b in zip(region['normal'], cameras[view]['direction_rational'])) > 0
                calculated = counts[object_id]
                check('independent_pixel_counts', calculated == frame['independent_counts'][identity] and
                      all(row[key] == value for key, value in calculated.items()))
                expected_readable = front and calculated['visible_surface_pixels'] >= 16 and calculated['contrasting_boundary_pixels'] >= 4
                check('front_and_readability', row['front_facing'] is front and row['readable'] is expected_readable and
                      row['minimum_surface_pixels'] == 16 and row['minimum_boundary_pixels'] == 4 and row['minimum_rgb_boundary_contrast'] == 24)
                source = source_scene['objects'][object_id]
                check('pixel_source_triangles', row['object_index'] == object_id and row['triangle_indices'] == region['triangle_indices'] ==
                      list(range(len(source['triangles']))) and row['source_vertices'] == len(source['vertices']) and row['source_triangles'] == len(source['triangles']))
                if expected_readable:
                    readable.append(identity)
            receipt = step['receipt']
            complete = {row['roi_id'] for row in regions if result['index']['classifications'][view][row['roi_id']]['complete']}
            gained = complete.intersection(readable) - covered
            covered.update(gained)
            unresolved = {row['roi_id'] for row in regions} - covered
            check('actual_receipt_binding', receipt['actual_image_delivered'] is True and receipt['image_path'] == frame['PNG'] and
                  receipt['image_sha256'] == frame['PNG_sha256'] and receipt['readable_roi_ids'] == sorted(readable) and
                  receipt['scene_identity'] == result['index']['scene_identity'] and receipt['candidate_identity'] == result['index']['candidate_identity'])
            check('incremental_coverage', step['geometrically_complete_roi_ids'] == sorted(complete) and
                  step['pixel_shortfall_roi_ids'] == sorted(complete - set(readable)) and
                  step['update']['new_roi_ids'] == sorted(gained) and step['update']['covered_roi_ids'] == sorted(covered) and
                  step['update']['unresolved_roi_ids'] == sorted(unresolved))
            frame_rows.append({'scene': scene_key, 'variant': variant, 'view': view, 'attempt': attempt,
                               'independent_counts': {row['roi_id']: counts[row['object_index']] for row in regions},
                               'foreground_pixels': foreground, 'background_pixels': background,
                               'PNG_sha256': frame['PNG_sha256'], 'raw_arrays': frame['arrays']})
        final_state = result['final_state']
        check('final_coverage', final_state['covered_roi_ids'] == sorted(covered) and final_state['unresolved_roi_ids'] == sorted(unresolved) and
              len(covered) == 5 and final_state['candidate_pool_uncovered_roi_ids'] == sorted(unresolved) == ['roi_16a6e8906884476acdedfc96'])
        chain_rows.append({'scene': scene_key, 'variant': variant, 'views': [step['view'] for step in result['steps']],
                           'increments': [len(step['update']['new_roi_ids']) for step in result['steps']],
                           'covered': len(covered), 'finite_pool_unresolved': sorted(unresolved), 'final_pixel_shortfall': []})
    check('all_eight_intents_consumed_once', sorted(observed_attempts) == list(range(1, 9)))
    for scene_key in ['grid4_permuted_alternating', 'grid16_permuted_alternating']:
        reference, candidate = chains[(scene_key, 'reference')], chains[(scene_key, 'candidate')]
        check('same_scene_semantic_index', {k: v for k, v in reference['index'].items() if k != 'stats'} ==
              {k: v for k, v in candidate['index'].items() if k != 'stats'})
        check('same_scene_feedback_state', reference['steps'] == candidate['steps'] or
              [{k: v for k, v in step.items() if k != 'receipt'} for step in reference['steps']] ==
              [{k: v for k, v in step.items() if k != 'receipt'} for step in candidate['steps']])
        check('same_scene_final_state', reference['final_state'] == candidate['final_state'])
        for view in ['SCENE', 'BACK']:
            first, second = reference['frames'][view], candidate['frames'][view]
            check('same_scene_pixels_and_raw_arrays', all(first[key] == second[key] for key in
                  ['PNG_sha256', 'arrays', 'pixel_rows', 'independent_counts', 'depth_checks']))
    tessellation_comparison = []
    for view in ['SCENE', 'BACK']:
        first = chains[('grid4_permuted_alternating', 'reference')]['frames'][view]
        second = chains[('grid16_permuted_alternating', 'reference')]['frames'][view]
        tessellation_comparison.append({'view': view, 'same_PNG': first['PNG_sha256'] == second['PNG_sha256'],
                                        'same_RGB': first['arrays']['color']['sha256'] == second['arrays']['color']['sha256'],
                                        'same_depth': first['arrays']['depth']['sha256'] == second['arrays']['depth']['sha256'],
                                        'same_owners': first['arrays']['owners']['sha256'] == second['arrays']['owners']['sha256']})
    limitations = [
        {'id': 'phase_prerequisites', 'locations': ['execute.py:57', 'execute.py:76'],
         'scope': 'Earlier proof/legacy/correctness outer source-bound gates are not all enforced against arbitrary direct phase calls. Actual five phases are ordered and bind the same frozen source.'},
        {'id': 'legacy_default_pass', 'locations': ['execute.py:83', 'engineering.py:173'],
         'scope': 'Legacy result has no explicit passed/count gate and the outer get defaults to true. Actual five saved rows are independently checked as 6/0/0/0/0.'},
        {'id': 'alternate_budget_directory', 'locations': ['engineering.py:282', 'execute.py:63'],
         'scope': 'Direct engineering caller may choose another budget directory under this namespace. Actual four registered chains and all eight intents use the sole fixed render_budget directory.'},
    ]
    report = {'schema': 'triangulation-invariant-discovery-001-independent-evidence-audit-v1',
              'passed': True, 'actual_evidence_affected_by_three_static_limitations': False,
              'scope': 'Post-run read-only JSON/SHA/PNG/NPZ audit. No discovery, renderer, model, timing trial or product call was executed by this checker.',
              'reviewer_role': 'Fixture/proof author and independent driver/evidence reviewer. Candidate and engineering implementation authored by other agents. Administrator independent review remains separate.',
              'source_freeze_sha256': frozen_sha, 'source_files_verified': 275,
              'phase_order': phase_rows, 'legacy_counts': expected_legacy, 'correctness_rows': 14,
              'benchmark_rows': 10, 'benchmark_scope': 'Existing fixed row identity/order/source only. No new timing and no statistical generalization.',
              'render_attempts': 8, 'global_render_cap': 16, 'render_budget_directory': str(budget),
              'new_models_Blender_provider_calls': 0, 'new_rasters_by_audit': 0,
              'chains': chain_rows, 'frames': frame_rows, 'grid4_vs_grid16_actual_images': tessellation_comparison,
              'static_harness_generalization_limitations': limitations, 'checks': CHECKS,
              'audit_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'inputs_sha256': INPUTS,
              'unmeasured': ['RSS', 'general concurrent or adversarial controller safety', 'new model-consumption benefit', 'non-rectangular topology', 'continuous geometry correctness beyond frozen independent proof and stated discovery domain']}
    with target.open('x', encoding='utf8', newline='\n') as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'passed': True, 'checks': len(CHECKS), 'sources': 275, 'frames': len(frame_rows),
                      'report': str(target), 'report_sha256': hashlib.sha256(target.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()

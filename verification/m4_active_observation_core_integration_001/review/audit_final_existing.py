"""Independently read this batch's saved source, archive and pixel evidence."""

import argparse
from fractions import Fraction
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, 'D:/he_core_001/venv/Lib/site-packages')
import numpy as np
from PIL import Image


HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
INPUT_SHA = {}
CHECKS = []


def blob(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    INPUT_SHA[str(path)] = hashlib.sha256(data).hexdigest()
    return data


def load(path):
    return json.loads(blob(path))


def check(name, condition):
    CHECKS.append({'check': name, 'passed': bool(condition)})
    if not condition:
        raise AssertionError(name)


def pixels(color, depth, owners, object_ids):
    check('array_shapes_and_dtypes', color.shape == (512, 512, 3) and color.dtype == np.uint8 and
          depth.shape == owners.shape == (512, 512) and depth.dtype == np.float64 and owners.dtype == np.int32)
    background, foreground = owners == -1, owners >= 0
    check('owner_domain', np.all(background | foreground) and np.all(owners < 28))
    check('actual_depth_masks', np.all(np.isposinf(depth[background])) and
          np.all(np.isfinite(depth[foreground]) & (depth[foreground] > 0)))
    rgb = color.astype(np.int32)
    horizontal_delta = rgb[:, 1:] - rgb[:, :-1]
    vertical_delta = rgb[1:, :] - rgb[:-1, :]
    horizontal = (owners[:, 1:] != owners[:, :-1]) & (np.sum(horizontal_delta ** 2, axis=2) >= 576)
    vertical = (owners[1:, :] != owners[:-1, :]) & (np.sum(vertical_delta ** 2, axis=2) >= 576)
    counts = {}
    for identity in object_ids:
        owned = owners == identity
        boundary = np.zeros_like(owned)
        boundary[:, :-1] |= owned[:, :-1] & horizontal
        boundary[:, 1:] |= owned[:, 1:] & horizontal
        boundary[:-1, :] |= owned[:-1, :] & vertical
        boundary[1:, :] |= owned[1:, :] & vertical
        counts[identity] = {'visible_surface_pixels': int(np.count_nonzero(owned)),
                            'contrasting_boundary_pixels': int(np.count_nonzero(boundary))}
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    output = parser.parse_args().output.resolve()
    if not output.is_relative_to(HERE / 'review') or output.exists():
        raise ValueError('new_review_output_required')
    frozen = load(HERE / 'FROZEN.json')
    original_freeze_sha = INPUT_SHA[str(HERE / 'FROZEN.json')]
    freeze2 = load(HERE / 'FROZEN_R2.json')
    freeze2_sha = INPUT_SHA[str(HERE / 'FROZEN_R2.json')]
    check('original_freeze_identity', original_freeze_sha == '507661a5372f4b679e2e85e7b76a2941ed0c51fba5894ce00ab9226823e551c1' and
          freeze2['original_freeze_sha256'] == original_freeze_sha)
    check('r2_freeze_identity', freeze2_sha == '032fdbfeea0dab167fcf03230306eed98b47c196832d536edbf884fa1fc1d7eb')
    correction = load(HERE / 'review/document_correction/CORRECTION.json')
    document_exception = str(Path(correction['path']).resolve())
    check('document_exception_is_named_contract_only', Path(document_exception) == HERE / 'NEXT_HOST_CONTRACT.md' and
          correction['product_runtime_source_changes'] == 0 and correction['qualification_or_performance_repeated'] is False)
    for path, wanted in freeze2['files_sha256'].items():
        current = hashlib.sha256(blob(path)).hexdigest()
        if str(Path(path).resolve()) == document_exception:
            check('document_exception_original_and_current_bound', wanted == correction['original_frozen_sha256'] and
                  hashlib.sha256(blob(correction['original_preserved_at'])).hexdigest() == wanted and current == correction['final_sha256'])
        else:
            check('frozen_file', current == wanted)
    archive = load(HERE / 'EXTERNAL_ARCHIVE.json')
    archived_paths = {}
    for row in archive['files']:
        source, archived = Path(row['source']).resolve(), (ROOT / row['archive']).resolve()
        check('archive_path_unique', str(source) not in archived_paths and archived.is_relative_to(HERE / 'external'))
        data = blob(archived)
        check('archive_exact_bytes', len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256'] and data == blob(source))
        archived_paths[str(source)] = archived

    def saved(path):
        return archived_paths[str(Path(path).resolve())]

    binding = load(HERE / 'external/payload_r2/RUN_BINDING.json')
    binding_sha = INPUT_SHA[str(HERE / 'external/payload_r2/RUN_BINDING.json')]
    wheel = next((HERE / 'build').glob('*.whl'))
    wheel_data = blob(wheel)
    check('same_wheel', hashlib.sha256(wheel_data).hexdigest() == binding['wheel_sha256'])
    manifest = binding['source_manifest']
    check('140_runtime_sources', len(manifest) == len({row['path'] for row in manifest}) == 140)
    with zipfile.ZipFile(BytesIO(wheel_data)) as zipped:
        for row in manifest:
            relative, wanted = row['path'], row['sha256']
            data = blob(ROOT / relative)
            check('source_wheel_install_failed_snapshot_equal', hashlib.sha256(data).hexdigest() == wanted and
                  zipped.read(relative) == data == blob(Path(binding['install_root']) / relative) ==
                  blob(Path('D:/he_core_001/failed_install_site') / relative))
    for relative, original in [('m4_triangulation_invariant_discovery_001/discovery.py',
                               ROOT / 'verification/m4_triangulation_invariant_discovery_001/discovery.py'),
                              ('m4_active_coverage_001/coverage.py', ROOT / 'verification/m4_active_coverage_001/coverage.py')]:
        check('two_baseline_copies_original_equal', blob(original) == blob(HERE / 'baseline' / relative) ==
              blob(Path('D:/he_core_001/payload_r2/baseline') / relative))
    first = load(HERE / 'external/run/source_check/RESULTS.json')
    check('first_setup_failure_preserved', first['passed'] is False and first['error']['message'] ==
          'verified_source_preloaded_module:numpy.version' and 'setup_closed_ns' not in first)
    gate = load(HERE / 'external/run/QUALITY_GATE_R2.json')
    pixel_gate = load(HERE / 'runs/PRE_BENCHMARK_QUALITY_GATE.json')
    check('quality_gate_freeze_chain', gate['passed'] is True and gate['binding_sha256'] == binding_sha and
          gate['root_pixel_quality_gate_sha256'] == INPUT_SHA[str(HERE / 'runs/PRE_BENCHMARK_QUALITY_GATE.json')] and
          pixel_gate['source_freeze_r2_sha256'] == freeze2_sha)
    for path, wanted in gate['evidence_sha256'].items():
        check('quality_gate_prior_phase_originals', hashlib.sha256(blob(saved(path))).hexdigest() == wanted)
    phases = []
    previous = freeze2['closed_before_publication_ns']
    for name in ['source_check', 'qualify', 'observe', 'benchmark']:
        record = load(HERE / 'external/run' / (name + '_r2') / 'RESULTS.json')
        process = load(HERE / 'runs' / (name + '_r2_PROCESS.json'))
        check('r2_phase_binding_and_source', record['passed'] is True and record['access']['denied'] == [] and
              record['binding_sha256'] == process['binding_sha256'] == binding_sha and
              process['exit_code'] == 0 and
              record['worker_source_sha256'] == hashlib.sha256(blob(HERE / 'isolated_worker_r2.py')).hexdigest())
        if name == 'benchmark':
            check('benchmark_freeze_via_quality_gate', process['quality_gate_sha256'] == INPUT_SHA[str(HERE / 'external/run/QUALITY_GATE_R2.json')])
        else:
            check('phase_direct_r2_freeze', process['freeze_r2_sha256'] == freeze2_sha)
        check('r2_phase_order_and_outer_clock', previous < process['started_ns'] <= record['started_ns'] <
              record['closed_before_publication_ns'] <= process['closed_after_process_exit_ns'])
        previous = process['closed_after_process_exit_ns']
        phases.append({'phase': name, 'pid': record['pid'], 'passed': True, 'binding_sha256': binding_sha,
                       'r2_freeze_binding_route': 'quality gate SHA and prior source-bound evidence' if name == 'benchmark' else 'direct PROCESS freeze_r2_sha256'})
    expected = load(HERE / 'admin/OLD_SELECTED.json')
    qualification = load(HERE / 'external/run/qualify_r2/QUALIFICATION.json')
    check('qualification_denominators', len(qualification['representations']) == 10 and len(qualification['controls']) == 4 and
          len(qualification['offline_replays']) == 4 and qualification['historical_frame_count'] == 8 and qualification['new_renders'] == 0)
    check('qualification_unique_cases', {(row['scene'], row['diagnostics_enabled']) for row in qualification['representations']} ==
          {(key, mode) for key in expected['scenes'] for mode in [False, True]})
    for row in qualification['representations']:
        wanted = {key: value for key, value in expected['scenes'][row['scene']].items() if key != 'stats'}
        check('stored_geometry_and_36_classifications', row['index'] == wanted)
    for row in qualification['controls']:
        check('stored_controls', row['regions'] == expected['controls'][row['control']])
    for row in qualification['offline_replays']:
        wanted = expected['replays'][row['id']]
        check('eight_old_frames_stay_replay', row['historical_frames_read'] == len(row['steps']) == 2 and row['new_renders'] == 0 and
              row['summary'] == wanted['final_state'] and len(wanted['steps']) == 2)
        for step, prior in zip(row['steps'], wanted['steps']):
            view = step['receipt']['view_name']
            check('old_replay_facts_and_provenance', step['pixel_rows'] == wanted['pixel_rows_by_view'][view] and
                  step['update'] == prior['update'] and step['receipt']['image_ref'].startswith('old-replay-'))
    control = qualification['repeat_and_invalidation_case']
    check('recorded_repeat_and_invalidation', all(control[key] is True for key in
          ['repeat_state_and_facts_equal', 'duplicate_update_reused', 'scene_change_invalidated', 'camera_change_invalidated']))
    observations = load(HERE / 'external/run/observe_r2/OBSERVATIONS.json')
    check('two_chains_six_new_attempts', [row['camera'] for row in observations['chains']] == ['normal', 'back64'] and
          observations['new_render_attempts'] == 6)
    intents = [load(path) for path in sorted((HERE / 'external/run/render_budget').glob('*.json'))]
    check('six_budget_slots_with_eight_cap', len(intents) == 6 and [row['attempt'] for row in intents] == list(range(1, 7)))
    check('budget_directory_fixed', sorted(path.name for path in Path('D:/he_core_001/run/render_budget').glob('*.json')) ==
          [str(i).zfill(2) + '.json' for i in range(1, 7)])
    trace = [json.loads(line) for line in blob(HERE / 'external/run/observe_r2/TRACE.jsonl').splitlines()]
    check('twelve_physical_trace_lines', len(trace) == 12 and [row['event'] for row in trace] == ['render_attempt', 'frame_complete'] * 6)
    scene = load(HERE / 'inputs/scene_grid16_permuted_alternating.json')
    ordinary = expected['scenes']['grid16_permuted_alternating']
    regions = ordinary['regions']
    pixel_rows, chain_rows, seen = [], [], []
    for chain in observations['chains']:
        name = chain['camera']
        camera_file = 'CAMERAS.json' if name == 'normal' else 'CAMERAS_BACK64.json'
        cameras = {row['name']: row for row in load(HERE / 'inputs' / camera_file)['views']}
        views = ['SCENE', 'BACK'] if name == 'normal' else ['SCENE', 'BACK64', 'LEFT', 'TOP']
        increments = [2, 3] if name == 'normal' else [2, 0, 2, 1]
        check('expected_sequence_and_gains', [row['receipt']['view_name'] for row in chain['steps']] == views and
              [len(row['update']['new_roi_ids']) for row in chain['steps']] == increments and
              len(chain['frames']) == len(views))
        check('short_facts_and_source', 'triangle_indices' not in json.dumps(chain['facts']) and
              chain['facts']['scene_identity'] == ordinary['scene_identity'])
        covered = set()
        history = set()
        for pending, step in zip(chain['frames'], chain['steps']):
            frame, attempt = pending['frame'], pending['attempt']
            number, view = attempt['attempt'], frame['view_name']
            seen.append(number)
            check('intent_and_trace_binding', attempt == intents[number - 1] and pending['status'] == 'completed' and
                  attempt['chain'] == name and attempt['view'] == view and
                  {key: value for key, value in trace[2 * number - 2].items() if key != 'event'} == attempt and
                  trace[2 * number - 1]['image_sha256'] == frame['image_sha256'])
            check('complete_actual_mesh_counts', frame['all_object_count'] == len(scene['objects']) == 28 and
                  frame['all_triangle_count'] == sum(len(obj['triangles']) for obj in scene['objects']) == 3336)
            png, npz = blob(saved(frame['image_path'])), blob(saved(frame['arrays_path']))
            check('frame_file_hash_bytes', hashlib.sha256(png).hexdigest() == frame['image_sha256'] and len(png) == frame['PNG_bytes'] and
                  hashlib.sha256(npz).hexdigest() == frame['arrays_sha256'] and len(npz) == frame['compressed_array_file_bytes'])
            with np.load(BytesIO(npz), allow_pickle=False) as data:
                check('three_npz_arrays', set(data.files) == {'color', 'depth', 'owners'})
                arrays = {key: data[key] for key in data.files}
            for key, value in arrays.items():
                check('raw_array_metadata', frame['arrays'][key] == {'dtype': str(value.dtype), 'shape': list(value.shape),
                      'nbytes': int(value.nbytes), 'sha256': hashlib.sha256(value.tobytes(order='C')).hexdigest()})
            with Image.open(BytesIO(png)) as image:
                check('PNG_matches_raw_RGB', image.format == 'PNG' and image.mode == 'RGB' and image.size == (512, 512) and
                      np.array_equal(np.asarray(image), arrays['color']))
            counts = pixels(arrays['color'], arrays['depth'], arrays['owners'], [row['object_index'] for row in regions])
            stored = {row['roi_id']: row for row in step['pixel_rows']}
            check('six_unique_pixel_rows', len(stored) == len(step['pixel_rows']) == 6)
            readable = []
            for region in regions:
                identity, object_id = region['roi_id'], region['object_index']
                row = stored[identity]
                front = sum(Fraction(x) * Fraction(y) for x, y in zip(region['normal'], cameras[view]['direction_rational'])) > 0
                calculated = counts[object_id]
                is_readable = front and calculated['visible_surface_pixels'] >= 16 and calculated['contrasting_boundary_pixels'] >= 4
                check('independent_actual_pixel_row', all(row[key] == value for key, value in calculated.items()) and
                      row['front_facing'] is front and row['readable'] is is_readable and
                      row['triangle_indices'] == region['triangle_indices'] == list(range(512)) and
                      row['source_triangles'] == 512 and row['source_vertices'] == 289)
                if is_readable:
                    readable.append(identity)
                pixel_rows.append({'chain': name, 'view': view, 'attempt': number, 'roi_id': identity,
                                   'front_facing': front, **calculated, 'readable': is_readable})
            receipt = step['receipt']
            check('bound_actual_image_feedback', receipt['readable_roi_ids'] == sorted(readable) and
                  receipt['image_path'] == frame['image_path'] and receipt['image_sha256'] == frame['image_sha256'] and
                  receipt['image_ref'] == frame['image_ref'] and receipt['scene_identity'] == frame['scene_identity'] == ordinary['scene_identity'] and
                  receipt['candidate_identity'] == frame['candidate_identity'] == chain['facts']['candidate_identity'] and frame['pose'] == cameras[view])
            mapped_view = 'BACK' if view == 'BACK64' else view
            complete = {row['roi_id'] for row in regions if ordinary['classifications'][mapped_view][row['roi_id']]['complete']}
            gained = complete.intersection(readable) - covered
            covered.update(gained)
            history.update(complete - set(readable))
            check('independent_coverage_increment', step['update']['new_roi_ids'] == sorted(gained) and
                  step['update']['covered_roi_ids'] == sorted(covered))
        unresolved = sorted(set(row['roi_id'] for row in regions) - covered)
        check('finite_unknown_and_recovered_shortfall', chain['summary']['covered_roi_ids'] == sorted(covered) and len(covered) == 5 and
              chain['summary']['unresolved_roi_ids'] == chain['summary']['candidate_pool_uncovered_roi_ids'] == unresolved == ['roi_16a6e8906884476acdedfc96'] and
              history.isdisjoint(unresolved))
        chain_rows.append({'camera': name, 'views': views, 'increments': increments, 'covered': 5,
                           'finite_pool_unknown': unresolved, 'historical_pixel_shortfall': sorted(history), 'final_pixel_shortfall': []})
    check('all_six_intents_used_once', sorted(seen) == list(range(1, 7)) and len(pixel_rows) == 36)
    normal_cameras = load(HERE / 'inputs/CAMERAS.json')['views']
    control_cameras = load(HERE / 'inputs/CAMERAS_BACK64.json')['views']
    for original, changed in zip(normal_cameras, control_cameras):
        if original['name'] == 'BACK':
            check('back64_unchanged_orientation_and_depth', changed['name'] == 'BACK64' and original['direction_rational'] == changed['direction_rational'] and
                  original['view_matrix'] == changed['view_matrix'] and original['projection_matrix'][2:] == changed['projection_matrix'][2:] and
                  original['projection_matrix'][0][0] == changed['projection_matrix'][0][0] * 64 and
                  original['projection_matrix'][1][1] == changed['projection_matrix'][1][1] * 64)
        else:
            check('other_control_cameras_unchanged', original == changed)
    benchmark = load(HERE / 'external/run/benchmark_r2/BENCHMARK.json')
    check('sole_ten_trial_sequence', [(row['pair'], row['arm']) for row in benchmark['rows']] ==
          [(number, arm) for number, order in enumerate([['old', 'new'], ['new', 'old'], ['old', 'new'], ['new', 'old'], ['old', 'new']], 1) for arm in order] and benchmark['new_renders'] == 0)
    report = {'schema': 'm4-active-observation-core-integration-001-final-independent-evidence-audit-v1',
              'passed': True, 'checks': CHECKS, 'frozen_r2_entries_accounted_for': len(freeze2['files_sha256']),
              'unchanged_current_frozen_files': len(freeze2['files_sha256']) - 1,
              'postrun_documentation_exception': correction,
              'original_freeze_sha256': original_freeze_sha, 'r2_freeze_sha256': freeze2_sha,
              'installed_source_wheel_failedsnapshot_files': 140, 'old_baseline_sources': 2,
              'archived_files_verified': len(archive['files']), 'phases': phases,
              'retained_setup_failures': 1, 'retained_setup_failure_reason': first['error']['message'],
              'historical_replay_frames': 8, 'historical_new_render_charge': 0,
              'new_frames': 6, 'global_render_cap': 8, 'trace_physical_lines': 12,
              'pixel_rows': pixel_rows, 'chains': chain_rows,
              'benchmark_existing_trial_rows': 10, 'new_trials_by_reviewer': 0,
              'review_scope': 'Independent saved-file SHA, wheel-member, JSON/PNG/NPZ and vectorized pixel recount. No product, candidate, renderer, test or benchmark function imported or called.',
              'reviewer_role': 'Cross-author reviewer. Fixed predecessor geometry proof authored by this reviewer, migration core/image/worker authored by other agents.',
              'limits': ['The first installed source_check failed and is retained. R2 changes deployment layout and two dependency-location assertions, with identical product source.',
                         'This audit establishes fixed rectangular-domain migration and local image feedback. No new model consumption or host/MCP default activation was measured.',
                         'Five existing timing pairs are only checked for count/order/source scope here. No performance significance or complete end-to-end deployment-cost aggregate is inferred.',
                         'Worker closed_before_publication excludes its final result write. Parent process records cover process exit. Archive/publication and setup are separate recorded windows.',
                         'RSS and general concurrent/adversarial runtime safety remain unmeasured.'],
              'inputs_sha256': INPUT_SHA, 'audit_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    with output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': True, 'checks': len(CHECKS), 'frames': 6, 'pixel_rows': len(pixel_rows),
                      'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'output': str(output)}))


if __name__ == '__main__':
    main()

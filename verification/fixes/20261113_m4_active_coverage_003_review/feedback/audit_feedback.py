"""Independent stored-pixel/state audit. No author imports, render or model calls."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification')
BATCH = ROOT / 'm4_active_coverage_003'
OLD = ROOT / 'm4_active_coverage_001'
checks, inputs, reports = [], {}, {}

def raw(path):
    path = Path(path)
    data = path.read_bytes()
    inputs[str(path)] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return data

def doc(path):
    return json.loads(raw(path))

def check(name, passed):
    checks.append({'name': name, 'passed': bool(passed)})

def equal(name, actual, expected):
    check(name, actual == expected)

def decode(png, npz):
    raw(png); raw(npz)
    with Image.open(png) as im:
        rgb = np.array(im.convert('RGB'))
    with np.load(npz, allow_pickle=False) as archive:
        color, owners, depth = (archive[k] for k in ('color', 'owners', 'depth'))
    return rgb, color, owners, depth

old_index = doc(OLD / 'results/optimized.json')
old_geom = {v['view_name']: set(v['geometric_complete_roi_ids']) for v in old_index['per_view']}
old_poses = {p['name']: p for p in doc(OLD / 'inputs/CAMERAS.json')['views']}

for run in ('control_A', 'control_B', 'main_p01_A', 'main_p01_B'):
    result = doc(BATCH / 'runs' / run / 'RESULT.json')
    index = result['index']; roi_ids = index['roi_ids']; universe = set(roi_ids)
    regions = index['regions']; order = index['view_order']
    geometric = {view: {roi for i, roi in enumerate(roi_ids) if mask & (1 << i)}
                 for view, mask in index['view_masks'].items()}
    equal(run + '/geometry_matches_accepted_001', geometric, old_geom)
    equal(run + '/six_unique_rois', len(universe), 6)
    equal(run + '/status', result['status'], 'completed')
    equal(run + '/frame_step_count', len(result['frames']), len(result['steps']))
    covered, observed, history, frame_reports = set(), [], set(), []
    for frame, step in zip(result['frames'], result['steps']):
        view = frame['view_name']; prefix = run + '/' + view
        equal(prefix + '/single_view_match', step['view_name'], view)
        check(prefix + '/no_repeated_view', view not in observed)
        if result['arm'] == 'B':
            remaining = [name for name in order if name not in observed]
            expected = 'SCENE' if not observed else max(remaining, key=lambda name: len(geometric[name] - covered))
            equal(prefix + '/next_choice_independently_reconstructed', view, expected)
            check(prefix + '/selected_positive_geometric_gain', bool(geometric[view] - covered))
        rgb, color, owners, depth = decode(frame['PNG'], frame['owner_depth_RGB_arrays'])
        check(prefix + '/png_matches_RGB_array', np.array_equal(rgb, color))
        check(prefix + '/shapes', rgb.shape == color.shape == (512, 512, 3) and owners.shape == depth.shape == (512, 512))
        check(prefix + '/dtypes', color.dtype == np.uint8 and owners.dtype == np.int32 and depth.dtype == np.float64)
        check(prefix + '/owner_range', np.all((owners >= -1) & (owners < 28)))
        check(prefix + '/depth_foreground_consistent', np.array_equal(owners >= 0, np.isfinite(depth) & (depth > 0)))
        boundary = np.zeros(owners.shape, dtype=bool)
        for axis in (0, 1):
            changed = np.diff(owners, axis=axis) != 0
            delta = np.diff(color.astype(np.int32), axis=axis)
            qualified = changed & (np.sum(delta * delta, axis=2) >= 24 ** 2)
            if axis == 0:
                boundary[:-1, :] |= qualified; boundary[1:, :] |= qualified
            else:
                boundary[:, :-1] |= qualified; boundary[:, 1:] |= qualified
        readable, rows = set(), []
        for region in regions:
            roi = region['roi_id']; mask = owners == region['object_index']
            surface = int(np.count_nonzero(mask)); edge = int(np.count_nonzero(mask & boundary))
            vertices = np.asarray([[float(Fraction(value)) for value in vertex] for vertex in region['vertices']])
            front = bool(np.dot(np.cross(vertices[1] - vertices[0], vertices[3] - vertices[0]), frame['pose']['target_to_eye_unit']) > 0)
            accepted = front and surface >= 16 and edge >= 4
            saved = next(row for row in frame['pixel_rows'] if row['roi_id'] == roi)
            equal(prefix + '/' + region['object_name'] + '/independent_pixel_result',
                  (surface, edge, front, accepted),
                  (saved['visible_surface_pixels'], saved['contrasting_boundary_pixels'], saved['front_facing'], saved['readable']))
            equal(prefix + '/' + region['object_name'] + '/fixed_thresholds',
                  (saved['minimum_surface_pixels'], saved['minimum_boundary_pixels'], saved['minimum_rgb_boundary_contrast']), (16, 4, 24))
            if accepted:
                readable.add(roi)
            rows.append({'object_name': region['object_name'], 'roi_id': roi, 'surface_pixels': surface,
                         'contrasting_boundary_pixels': edge, 'front_facing': front, 'readable': accepted})
        gain = (geometric[view] & readable) - covered
        shortfall = geometric[view] - readable
        history |= shortfall
        covered |= gain; observed.append(view)
        for name, value in (('geometry_complete_roi_ids', geometric[view]), ('readable_roi_ids', readable),
                            ('pixel_shortfall_roi_ids', shortfall), ('new_roi_ids', gain),
                            ('covered_roi_ids', covered), ('unresolved_roi_ids', universe - covered)):
            equal(prefix + '/step_' + name, set(step[name]), value)
        for name, value in (('new_roi_ids', gain), ('covered_roi_ids', covered), ('unresolved_roi_ids', universe - covered)):
            equal(prefix + '/state_' + name, set(frame['state_update'][name]), value)
        equal(prefix + '/receipt_readable', set(frame['receipt']['readable_roi_ids']), readable)
        equal(prefix + '/receipt_scene', frame['receipt']['scene_identity'], index['scene_identity'])
        equal(prefix + '/receipt_camera_set', frame['receipt']['candidate_identity'], index['candidate_identity'])
        old_rgb, old_color, old_owners, old_depth = decode(OLD / 'render' / (view + '.png'), OLD / 'render' / (view + '.npz'))
        if run.startswith('control') and view == 'BACK':
            equal(prefix + '/BACK_span_multiplier', frame['pose']['span'] / old_poses[view]['span'], 64.0)
            check(prefix + '/BACK_differs_from_original_png', not np.array_equal(rgb, old_rgb))
            check(prefix + '/BACK_zero_all_target_pixels', all(row['surface_pixels'] == row['contrasting_boundary_pixels'] == 0 for row in rows))
        else:
            equal(prefix + '/unchanged_camera', frame['pose'], old_poses[view])
            check(prefix + '/unchanged_original_RGBA_owner_depth', all(np.array_equal(a, b) for a, b in
                  ((rgb, old_rgb), (color, old_color), (owners, old_owners), (depth, old_depth))))
        frame_reports.append({'view': view, 'foreground_pixels': int(np.count_nonzero(owners >= 0)),
                              'unique_RGB': np.unique(rgb.reshape(-1, 3), axis=0).tolist(),
                              'new_roi_ids': sorted(gain), 'new_count': len(gain),
                              'covered_count': len(covered), 'pixel_shortfall_roi_ids': sorted(shortfall), 'rows': rows})
    pool_uncovered = universe - set().union(*geometric.values())
    state = result['final_state']
    equal(run + '/final_observed', state['observed_views'], observed)
    equal(run + '/final_covered', set(state['covered_roi_ids']), covered)
    equal(run + '/final_unresolved', set(state['unresolved_roi_ids']), universe - covered)
    equal(run + '/finite_pool_uncovered', set(state['candidate_pool_uncovered_roi_ids']), pool_uncovered)
    equal(run + '/updates_once_per_frame', state['state_updates'], len(observed))
    equal(run + '/historical_shortfall', set(result['pixel_shortfall_history_roi_ids']), history)
    equal(run + '/final_shortfall', set(result['final_pixel_shortfall_roi_ids']), history & (universe - covered))
    equal(run + '/covered_count', len(covered), 5)
    equal(run + '/uncovered_count', len(universe - covered), 1)
    equal(run + '/remaining_finite_pool_only', universe - covered, pool_uncovered)
    repeat = result['repeat_query']
    equal(run + '/repeat_no_render', repeat['new_render_attempts'], 0)
    equal(run + '/repeat_attempt_counter', repeat['render_attempts_before'], repeat['render_attempts_after'])
    equal(run + '/repeat_identical_state', repeat['state_before'], repeat['state_after'])
    equal(run + '/repeat_matches_final', repeat['state_after'], state)
    equal(run + '/repeat_next_view', repeat['next_view'], None)
    remaining = set(order) - set(observed)
    check(run + '/no_positive_remaining_geometry_gain', all(not geometric[name] - covered for name in remaining))
    reports[run] = {'frame_count': len(observed), 'pixel_rows_recomputed': 6 * len(observed),
                    'sequence': observed, 'new_counts': [frame['new_count'] for frame in frame_reports],
                    'covered_roi_ids': sorted(covered), 'unresolved_roi_ids': sorted(universe - covered),
                    'pixel_shortfall_history_roi_ids': sorted(history),
                    'final_pixel_shortfall_roi_ids': sorted(history & (universe - covered)), 'frames': frame_reports}

equal('control_A_B_same_final_coverage', reports['control_A']['covered_roi_ids'], reports['control_B']['covered_roi_ids'])
equal('main_A_B_same_final_coverage', reports['main_p01_A']['covered_roi_ids'], reports['main_p01_B']['covered_roi_ids'])
equal('control_B_sequence', reports['control_B']['sequence'], ['SCENE', 'BACK', 'LEFT', 'TOP'])
equal('control_B_new_counts', reports['control_B']['new_counts'], [2, 0, 2, 1])
equal('control_B_historical_shortfall_count', len(reports['control_B']['pixel_shortfall_history_roi_ids']), 3)
equal('control_B_final_shortfall_empty', reports['control_B']['final_pixel_shortfall_roi_ids'], [])
equal('main_B_sequence', reports['main_p01_B']['sequence'], ['SCENE', 'BACK'])
equal('main_B_new_counts', reports['main_p01_B']['new_counts'], [2, 3])

out = {'source_commit': 'f2b9dc01621d5b7adb330c096b6460eb3be9c552',
       'scope': 'Independent stored PNG/NPZ decode, pixel arithmetic and finite-state reconstruction for both controls and first main pair. Prior accepted geometric masks reused, no geometry engine execution.',
       'new_render_model_Blender_API_calls': 0, 'author_validator_or_scorer_imports': 0,
       'checks_count': len(checks), 'checks': checks, 'failed': [row for row in checks if not row['passed']],
       'sample_frames': sum(report['frame_count'] for report in reports.values()),
       'sample_pixel_rows': sum(report['pixel_rows_recomputed'] for report in reports.values()),
       'runs': reports, 'inputs': inputs,
       'unrun': ['remaining ten main-process pixel recounts (root checks all frame hashes)',
                 'new raster runs', 'new independent geometric classification (accepted001 reused)',
                 'model-facing image transport', 'model semantic recognition', 'model performance comparison']}
HERE.mkdir(parents=True, exist_ok=True)
(HERE / 'RESULTS.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
print(json.dumps({key: out[key] for key in ('checks_count', 'failed', 'sample_frames', 'sample_pixel_rows')}, ensure_ascii=False))

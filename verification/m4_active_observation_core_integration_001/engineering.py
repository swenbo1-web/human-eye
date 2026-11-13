"""Finite source/installed qualification against immutable migration evidence."""

import argparse
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SEMANTIC_KEYS = ('scene_identity', 'candidate_identity', 'regions', 'view_order', 'view_masks', 'classifications')


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf8')


def compare_qualification(result, output):
    expected = read(HERE / 'admin/OLD_SELECTED.json')
    representation_keys = [(row['scene'], row['diagnostics_enabled']) for row in result['representations']]
    assert len(representation_keys) == len(set(representation_keys)) == 10
    assert set(representation_keys) == {(name, diagnostics) for name in expected['scenes'] for diagnostics in (False, True)}
    control_keys = [(row['control'], row['diagnostics_enabled']) for row in result['controls']]
    assert len(control_keys) == len(set(control_keys)) == 4
    assert set(control_keys) == {(name, diagnostics) for name in expected['controls'] for diagnostics in (False, True)}
    replay_ids = [row['id'] for row in result['offline_replays']]
    assert len(replay_ids) == len(set(replay_ids)) == 4 and set(replay_ids) == set(expected['replays'])
    checks = []
    for row in result['representations']:
        wanted = expected['scenes'][row['scene']]
        target = {key: wanted[key] for key in SEMANTIC_KEYS}
        checks.append({'case': row['scene'], 'diagnostics': row['diagnostics_enabled'],
                       'index_equal_to_fixed_old_selected': row['index'] == target,
                       'diagnostics_mode_correct': (row['diagnostics'] is not None) is row['diagnostics_enabled']})
    for row in result['controls']:
        checks.append({'case': row['control'], 'diagnostics': row['diagnostics_enabled'],
                       'regions_equal_to_fixed_old_selected': row['regions'] == expected['controls'][row['control']]})
    for row in result['offline_replays']:
        wanted = expected['replays'][row['id']]
        state_equal = row['summary'] == wanted['final_state']
        pixels_equal = True
        updates_equal = True
        for actual, original in zip(row['steps'], wanted['steps']):
            view = actual['receipt']['view_name']
            assert view == original['view']
            before = {value['roi_id']: value for value in wanted['pixel_rows_by_view'][view]}
            actual_ids = [value['roi_id'] for value in actual['pixel_rows']]
            assert len(actual_ids) == len(set(actual_ids)) == len(before) and set(actual_ids) == set(before)
            for pixel in actual['pixel_rows']:
                for key in ('object_index', 'front_facing', 'visible_surface_pixels', 'contrasting_boundary_pixels', 'readable'):
                    pixels_equal = pixels_equal and pixel[key] == before[pixel['roi_id']][key]
            updates_equal = updates_equal and actual['update'] == original['update']
        assert len(row['steps']) == len(wanted['steps'])
        assert 'triangle_indices' not in json.dumps(row['facts'])
        checks.append({'case': row['id'], 'old_frame_replay_summary_equal': state_equal,
                       'actual_pixels_equal_to_fixed_frame_evidence': pixels_equal, 'incremental_updates_equal': updates_equal,
                       'historical_frames_read': row['historical_frames_read'], 'new_renders': row['new_renders']})
    control = result['repeat_and_invalidation_case']
    checks.append({'case': 'repeat_and_source_invalidation',
                   **{key: control[key] for key in ('repeat_state_and_facts_equal', 'duplicate_update_reused',
                                                   'scene_change_invalidated', 'camera_change_invalidated')}})
    boolean_values = [value for row in checks for key, value in row.items()
                      if type(value) is bool and key != 'diagnostics']
    passed = (all(boolean_values) and len(result['representations']) == 10 and len(result['controls']) == 4
              and len(result['offline_replays']) == 4 and result['historical_frame_count'] == 8 and result['new_renders'] == 0)
    value = {'passed': passed, 'checks': checks, 'fixed_old_selected_scope': True,
             'historical_frames': 8, 'new_renders': 0, 'new_models': 0}
    save(output, value)
    return value


def qualify_loaded(core, image_api, output):
    """Root supplies normally loaded source modules after its source binding."""
    output = Path(output).resolve()
    if not output.is_relative_to(HERE):
        raise ValueError('new_evidence_namespace_required')
    output.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('_core_integration_qualification_helpers', HERE / 'isolated_worker.py')
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    result = helpers.qualification(core, image_api, HERE, read(HERE / 'INPUTS.json'), output)
    return compare_qualification(result, output / 'COMPARISON.json')


def inspect_installed(result_path, output):
    result = read(result_path)
    if result['phase'] != 'qualify' or result['passed'] is not True:
        raise ValueError('completed_installed_qualification_required')
    return compare_qualification(result['qualification'], output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installed-result', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    result = inspect_installed(options.installed_result, options.output)
    print(json.dumps({'passed': result['passed'], 'new_renders': 0}))
    if not result['passed']:
        raise SystemExit(1)

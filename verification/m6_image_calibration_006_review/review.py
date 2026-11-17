"""Recompute twelve saved candidates, RGB objectives and stage equivalence."""
import json
from pathlib import Path
import runpy
import time

import numpy as np


HERE = Path(__file__).resolve().parent
BASE = HERE.parent / '_m6ca6/batch'
PREVIOUS = HERE.parent / '_m6im5/batch'
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification')
PNG = runpy.run_path(str(HERE.parent / 'm6_image_correspondence_005_plan/probe.py'))['read_png']
STATISTICS = runpy.run_path(str(HERE.parent / 'm6_matched_refine_003_review/review.py'))['statistics']


def read(path):
    return json.loads(path.read_bytes())


def local(value):
    path = Path(value)
    if path.is_absolute():
        for source, snapshot in ((AUTHOR / 'm6_image_calibration_006', BASE),
                                 (AUTHOR / 'm6_image_correspondence_005', PREVIOUS)):
            if path.is_relative_to(source):
                return snapshot / path.relative_to(source)
        raise ValueError('unexpected_external_source_' + str(path))
    return BASE / path


def main():
    started = time.perf_counter()
    binding = read(BASE / 'SOURCE_BINDING.json')
    with np.load(local(binding['initial']['packet']['path'])) as packet:
        initial = {name: packet[name] for name in packet.files}
    references = {entry['role'].removeprefix('normal_'): PNG(local(entry['path'])).astype(np.int16)
                  for entry in binding['images']['normal']}
    image_cache = {}
    models = {}
    selected = []
    scores = []
    with np.load(PREVIOUS / 'private/scoring/target.npz') as packet:
        target = {name: packet[name] for name in packet.files}
    support, editable, region = target['support_ids'], target['I_ids'], target['F_source_ids']
    normal_editable = np.setdiff1d(editable, support)
    outside = np.setdiff1d(initial['source_ids'], editable)
    groups = dict(support_47=support, observation_410=region,
                  normal_363=np.setdiff1d(region, support), normal_editable_227=normal_editable)
    before_error = initial['vertices_world'] - target['clean_vertices_world']
    for stage in ('v1', 'v2'):
        report = read(BASE / ('CALIBRATION_SCORES_' + stage + '.json'))
        for proposal in ('v1_native', 'v2_facts'):
            state = read(BASE / 'private/calibrations' / (stage + '_' + proposal) / 'STATE.json')
            result = read(local(state['result']['path']))
            assert state['status'] == result['status'] == 'image_selection_frozen'
            assert result['independent_geometry_scoring'] == 'pending_separate_private_scorer'
            assert result['image_selection_frozen_epoch'] < report['private_scoring_started_epoch']
            candidates = []
            for tag, entry in state['candidates'].items():
                candidate = entry['result']
                alpha = candidate['alpha']
                claim = next(row for row in report['candidates'] if row['proposal_id'] == proposal and row['alpha'] == alpha)
                images = {}
                integer_loss = 0
                for image_entry in candidate['images']:
                    path = local(image_entry['path'])
                    if path not in image_cache:
                        image_cache[path] = PNG(path)
                    pixels = image_cache[path]
                    view = image_entry['role'].removeprefix('current_')
                    reference = references[view]
                    assert pixels.shape == reference.shape == (640, 640, 3)
                    images[view] = pixels
                    integer_loss += int(np.abs(pixels.astype(np.int16) - reference).sum())
                assert integer_loss == claim['image']['absolute_error_sum'] == candidate['image']['absolute_error_sum']
                assert claim['image']['sample_count'] == 3686400
                with np.load(local(claim['artifacts']['readback']['path'])) as packet:
                    actual = {name: packet[name] for name in packet.files}
                with np.load(local(candidate['payload']['path'])) as payload:
                    ids = payload['source_ids']
                    delta = payload['displacements_world']
                with np.load(BASE / 'private/input/proposals' / (proposal + '.npz')) as original:
                    np.testing.assert_array_equal(ids, original['source_ids'])
                    np.testing.assert_array_equal(delta, alpha * original['displacements_world'])
                expected_local = initial['vertices_local'].copy()
                inverse = np.linalg.inv(initial['matrix_world'])
                wanted_world = initial['vertices_world'][ids] + delta
                expected_local[ids] = (wanted_world @ inverse[:3, :3].T + inverse[:3, 3]).astype(np.float32)
                np.testing.assert_array_equal(actual['vertices_local'], expected_local)
                np.testing.assert_array_equal(actual['vertices_local'][outside], initial['vertices_local'][outside])
                for name in ('matrix_world', 'source_ids', 'poly_offsets', 'poly_vertices', 'faces', 'triangle_polygon_ids'):
                    np.testing.assert_array_equal(actual[name], initial[name])
                final_error = actual['vertices_world'] - target['clean_vertices_world']
                for group, ids_in_group in groups.items():
                    for position, vectors in (('before', before_error), ('after', final_error)):
                        values = STATISTICS(vectors, ids_in_group)
                        for name, value in values.items():
                            assert abs(value - claim['metrics'][group][position][name]) < 1e-12
                reduction = 1 - STATISTICS(final_error, support)['RMSE_m'] / STATISTICS(before_error, support)['RMSE_m']
                displacement = actual['vertices_world'] - initial['vertices_world']
                normal_rms = STATISTICS(displacement, normal_editable)['RMSE_m']
                passed = (reduction >= .3 and STATISTICS(final_error, region)['RMSE_m'] < STATISTICS(before_error, region)['RMSE_m']
                          and normal_rms <= .0001)
                assert passed == claim['restoration_quality_pass']
                if stage == 'v1':
                    models[(proposal, alpha)] = (actual, images)
                else:
                    previous, previous_images = models[(proposal, alpha)]
                    for name in actual:
                        np.testing.assert_array_equal(actual[name], previous[name])
                    for view, pixels in images.items():
                        np.testing.assert_array_equal(pixels, previous_images[view])
                candidates.append((integer_loss, alpha))
                scores.append(dict(stage=stage, proposal=proposal, alpha=alpha, integer_RGB_loss=integer_loss,
                    support_RMSE_m=STATISTICS(final_error, support)['RMSE_m'], support_reduction_fraction=reduction,
                    normal_editable_misedit_RMS_m=normal_rms, restoration_pass=bool(passed)))
            chosen = min(candidates)[1]
            assert chosen == result['selected_alpha']
            selected.append(dict(stage=stage, proposal=proposal, alpha=chosen))
    assert len(scores) == 12
    result = dict(status='passed_saved_candidates_RGB_selection_and_equivalence', candidates=scores,
        selections=selected, candidate_count=12, exact_stage_mesh_pairs=6, exact_stage_RGB_pairs=18,
        unique_candidate_PNG_decodes=len(image_cache), new_Pro=0, new_Blender=0, new_training=0,
        independent_full_contact_rescan=False, wall_s=time.perf_counter() - started)
    (HERE / 'RESULTS.json').write_bytes((json.dumps(result, indent=2) + '\n').encode())
    print(json.dumps({key: value for key, value in result.items() if key != 'candidates'}))


if __name__ == '__main__':
    main()

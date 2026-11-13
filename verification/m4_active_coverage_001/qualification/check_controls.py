"""Targeted geometric/state qualification without oracle or new rendering."""

import copy
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import traceback


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def semantics(index):
    return {'scene_identity': index.scene_identity, 'candidate_identity': index.candidate_identity,
            'regions': [{'roi_id': roi.roi_id, 'vertices': roi.vertices, 'normal': roi.normal} for roi in index.regions],
            'view_order': index.view_order, 'view_masks': index.view_masks, 'classifications': index.classifications}


def main():
    paths = [BATCH / 'coverage.py', HERE / 'controls.py', Path(__file__),
             BATCH / 'inputs/SCENE_GEOMETRY_RATIONAL.json', BATCH / 'inputs/CAMERAS.json',
             BATCH / 'render/assess_readability.py', BATCH / 'render/adapter.py', BATCH / 'render/READABILITY.json']
    before = {str(path.resolve()): digest(path) for path in paths}
    coverage = load('_active_controls_candidate', BATCH / 'coverage.py')
    controls = load('_active_controls_inputs', HERE / 'controls.py')
    images = load('_active_controls_readability', BATCH / 'render/assess_readability.py')
    scene = json.loads((BATCH / 'inputs/SCENE_GEOMETRY_RATIONAL.json').read_bytes())
    cameras = json.loads((BATCH / 'inputs/CAMERAS.json').read_bytes())
    checks = []

    def check(name, condition):
        checks.append({'name': name, 'passed': bool(condition)})
        assert condition, name

    def refused(name, state, receipt, reason):
        previous = copy.deepcopy(state.summary())
        try:
            state.observe(receipt)
        except ValueError as error:
            check(name + '_reason', str(error) == reason)
        else:
            check(name + '_refused', False)
        check(name + '_unchanged', state.summary() == previous)

    reference = coverage.build_index(scene, cameras, 'reference')
    optimized = coverage.build_index(scene, cameras, 'optimized')
    check('reference_optimized_semantics', semantics(reference) == semantics(optimized))
    check('discovery_count_after_execution', len(reference.regions) == 6)
    check('candidate_matrix_size', sum(len(rows) for rows in reference.classifications.values()) == 36)
    for name, transformed in (('rename_object_order', controls.renamed_and_reordered(scene)),
                              ('mesh_vertex_triangle_enumeration', controls.permuted_mesh_enumeration(scene))):
        for variant in ('reference', 'optimized'):
            index = coverage.build_index(transformed, cameras, variant)
            check(name + '_' + variant, semantics(index) == semantics(reference))
    small_scene, small_camera = controls.off_center_scene(), controls.off_center_camera()
    off_center = {}
    for variant in ('reference', 'optimized'):
        index = coverage.build_index(small_scene, small_camera, variant)
        check('off_center_discovered_' + variant, len(index.regions) == 1)
        status = index.classifications['SCENE'][index.region_ids[0]]
        check('off_center_occlusion_' + variant, status['status'] == 'positive_area_occlusion' and not status['complete'])
        off_center[variant] = status
    rectangle = small_scene['objects'][0]['vertices']
    probes = [(Fraction(0), Fraction(0))] + [(Fraction(point[0]), Fraction(point[1])) for point in rectangle]
    check('center_and_four_corners_avoid_box', all(not (Fraction(3, 4) <= x <= Fraction(7, 8)
        and Fraction(3, 4) <= y <= Fraction(7, 8)) for x, y in probes))
    check('off_center_shadow_has_positive_area', (Fraction(7, 8) - Fraction(3, 4)) ** 2 == Fraction(1, 64))
    malformed = {'objects': [copy.deepcopy(small_scene['objects'][0])]}
    malformed['objects'][0]['triangles'] = [[0, 1, 2], [0, 1, 3]]
    check('shared_boundary_overlap_is_not_rectangle', len(coverage.discover_regions(malformed)) == 0)

    assessment = json.loads((BATCH / 'render/READABILITY.json').read_bytes())
    state = coverage.CoverageState(optimized)
    check('unobserved_has_no_delivered_coverage', state.covered_mask == 0 and state.next_view() == 'SCENE')
    receipt = images.receipt_for_view(optimized, 'SCENE', assessment)
    first = state.observe(receipt)
    check('actual_SCENE_committed', state.updates == 1 and first['reused'] is False)
    first_mask = state.covered_mask
    reused = state.observe(copy.deepcopy(receipt))
    check('same_version_reuse_idempotent', reused['reused'] is True and state.updates == 1 and state.covered_mask == first_mask)
    for key in ('scene_identity', 'candidate_identity'):
        bad = {**receipt, key: 'wrong-source'}
        refused('reused_' + key, state, bad, 'actual_bound_image_receipt_required')
    refused('truthy_delivery_string', state, {**receipt, 'actual_image_delivered': 'false'}, 'actual_bound_image_receipt_required')
    refused('wrong_image_hash', state, {**receipt, 'image_sha256': '0' * 64}, 'actual_PNG_bytes_required')
    bad_path = HERE / 'CONTROL_PLAN.md'
    refused('non_PNG_bytes', state, {**receipt, 'image_path': str(bad_path.resolve()), 'image_sha256': digest(bad_path)}, 'actual_PNG_bytes_required')
    fresh = coverage.CoverageState(optimized)
    refused('non_SCENE_first', fresh, images.receipt_for_view(optimized, 'BACK', assessment), 'common_SCENE_observation_required')
    check('same_scene_rebind_retains_state', not state.rebind(reference) and state.updates == 1 and state.covered_mask == first_mask)
    changed = copy.deepcopy(scene)
    for point in changed['objects'][-1]['vertices']:
        point[0] = str(Fraction(point[0]) + Fraction(1, 1000000))
    changed_index = coverage.build_index(changed, cameras, 'optimized')
    check('changed_scene_rebind_resets', state.rebind(changed_index) and state.updates == 0
          and state.covered_mask == 0 and not state.observed_views and state.next_view() == 'SCENE')
    refused('old_receipt_after_rebind', state, receipt, 'actual_bound_image_receipt_required')
    unchanged = all(digest(Path(path)) == expected for path, expected in before.items())
    check('candidate_and_inputs_unchanged_during_checks', unchanged)
    result = {'passed': all(row['passed'] for row in checks), 'checks': checks,
              'baseline': {'discovered_regions': len(reference.regions), 'matrix_cells': 36,
                           'reference_stats': reference.stats, 'optimized_stats': optimized.stats},
              'off_center': {'center_and_corners_visible': True, 'shadow_area_exact': '1/64', 'classifications': off_center},
              'new_model_provider_Blender_API_runs': 0, 'new_raster_calls': 0,
              'geometric_permutation_controls_reuse_pixel_arrays': False,
              'independent_oracle_used': False, 'inputs_sha256': before,
              'scope': 'Candidate equivalence, geometric counterexamples and bound-image state checks. Independent 36-cell truth comparison belongs to the separate oracle qualification.'}
    output = HERE / 'CONTROLS.json'
    output.write_text(json.dumps(result, default=str, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({'passed': result['passed'], 'checks': len(checks), 'new_raster_calls': 0}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        directory = HERE / 'development'
        directory.mkdir(exist_ok=True)
        number = len(list(directory.glob('failure_*.json'))) + 1
        (directory / ('failure_' + str(number).zfill(2) + '.json')).write_text(json.dumps({
            'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}, indent=2) + '\n', encoding='utf8')
        raise

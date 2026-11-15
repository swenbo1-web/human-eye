"""Freeze the six approved numeric inputs and reproduce the unmodified source."""

import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PLAN_SHA = '29cfad8ee1de593bb5e55f6ffe6060ab56d9779503b6ce53af7f51a3c4fe4afa'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bounds(vertices):
    return [[min(point[k] for point in vertices) for k in range(3)],
            [max(point[k] for point in vertices) for k in range(3)]]


def matrix(translation):
    return [[float(row == column) for column in range(3)] + [translation[row]] for row in range(3)] + [[0., 0., 0., 1.]]


def mapped_vertices(local, transform):
    return [[(sum(transform[row][column] * point[column] for column in range(3)) + transform[row][3]) * 1.0
             for row in range(3)] for point in local]


def write_new(name, value):
    with (HERE / name).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    spec = importlib.util.spec_from_file_location('_frozen_camera_input_oracle', HERE / 'camera_numeric.py')
    oracle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oracle)
    baseline = json.loads((HERE / 'BASELINE.json').read_bytes())
    assert baseline['baseline_git'] == oracle.BASELINE_GIT
    assert sha(HERE / 'M4_TARGET_CAMERA_RELIABILITY_001_PLAN.md') == PLAN_SHA
    raw = oracle.git_blob('human_eye_plugin/blender_host.py')
    core_raw = oracle.git_blob('human_eye_plugin/active_observation.py')
    assert raw == (ROOT / 'human_eye_plugin/blender_host.py').read_bytes()
    assert core_raw == (ROOT / 'human_eye_plugin/active_observation.py').read_bytes()
    assert raw == Path('D:/he_m4_target_001/A/product/human_eye_plugin/blender_host.py').read_bytes()
    reference = HERE / 'reference'
    reference_pins = []
    for original, expected_sha in baseline['original_reference_pins'].items():
        copied = reference / Path(original).name
        assert sha(Path(original)) == sha(copied) == expected_sha
        reference_pins.append({'original': original, 'copied': str(copied), 'sha256': expected_sha})
    reachable = json.loads((reference / 'camera_reachable.json').read_bytes())
    assert hashlib.sha256(raw).hexdigest() == reachable['source_sha256']
    assert hashlib.sha256(core_raw).hexdigest() == reachable['core_sha256']
    local = reachable['local_vertices']
    transform = reachable['matrix_world']
    f32 = lambda value: struct.unpack('<f', struct.pack('<f', value))[0]
    assert all(f32(value) == value for point in local for value in point)
    assert all(f32(value) == value for row in transform for value in row)
    world = mapped_vertices(local, transform)
    assert world == reachable['world_vertices']
    offset = [transform[row][3] for row in range(3)]
    origin = [[value - translation for value, translation in zip(point, offset)] for point in world]
    negative_faces = [[0, 2, 1], [0, 3, 2]]
    cases = [
        {'id': 'reachable_binary32', 'local_vertices': local, 'matrix_world': transform,
         'world_vertices': world, 'world_bounds': [bounds(world)], 'faces': negative_faces,
         'check_exact_coverage': True, 'source': 'verbatim fixed reachable reference',
         'candidate_unknown_allowed': 'explicit numeric_insufficient only'},
        {'id': 'origin_quantized_control', 'local_vertices': origin, 'matrix_world': matrix([0., 0., 0.]),
         'world_vertices': origin, 'world_bounds': [bounds(origin)], 'faces': negative_faces,
         'check_exact_coverage': True, 'source': 'same captured world minus the exact common translation',
         'candidate_unknown_allowed': False},
    ]
    fitted = [[-1., -1., 0.], [1., -1., 0.], [1., 1., 0.], [-1., 1., 0.]]
    cases.append({'id': 'prior_target_fit', 'world_vertices': fitted,
                  'world_bounds': [[[-4., -5., -6.], [7., 8., 9.]], [[100., 100., 100.], [101., 101., 101.]]],
                  'check_exact_coverage': False, 'source': 'prior targeted_numeric_checks fitted_camera input',
                  'candidate_unknown_allowed': False})
    u, v = [1., 2., 0.], [-2., 1., 2.]
    rotated = [[first * u[k] + second * v[k] for k in range(3)]
               for first, second in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    cases.append({'id': 'prior_rotated_target', 'world_vertices': rotated, 'world_bounds': [bounds(rotated)],
                  'check_exact_coverage': False, 'source': 'prior targeted_numeric_checks rotated_target_actual_vertex_fit input',
                  'candidate_unknown_allowed': False})
    for name, half_y, half_z, translation in (
            ('ordinary_translation', .75, .5, [17., -23., 41.]),
            ('slender_translation', 1., 1/64, [8., -4., 16.])):
        vertices = [[0., y * half_y, z * half_z] for y, z in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        pose = matrix(translation)
        points = mapped_vertices(vertices, pose)
        cases.append({'id': name, 'local_vertices': vertices, 'matrix_world': pose,
                      'world_vertices': points, 'world_bounds': [bounds(points)], 'faces': negative_faces,
                      'check_exact_coverage': True, 'source': 'approved minimal ordinary-scale binary-exact control',
                      'candidate_unknown_allowed': False})
    ordinary = next(case for case in cases if case['id'] == 'ordinary_translation')
    grid_local = [[0., -.75 + 1.5 * row / 16, -.5 + column / 16] for row in range(17) for column in range(17)]
    grid_world = mapped_vertices(grid_local, ordinary['matrix_world'])
    prior_root = Path('C:/Users/Administrator/.codex/worktrees/m4-target-001/hefe/verification/m4_target_acquisition_001')
    prior_pins = [{'path': str(prior_root / name), 'sha256': sha(prior_root / name)}
                  for name in ('NUMERIC_A_01.json', 'targeted_numeric_checks.py', 'ACTUAL_A_PERIPHERAL_REVIEW.json')]
    inputs = {
        'schema': 'target-camera-reliability-fixed-inputs-v1', 'baseline_git': oracle.BASELINE_GIT,
        'plan_sha256': PLAN_SHA, 'baseline_host_sha256': hashlib.sha256(raw).hexdigest(),
        'baseline_core_sha256': hashlib.sha256(core_raw).hexdigest(),
        'camera_cases': cases, 'camera_case_count': 6,
        'reference_pins': reference_pins, 'prior_reference_pins': prior_pins,
        'origin_rule': 'Subtract the common translation from captured binary64 world points. Preserve the quantized dimensions and all vertex/face ordering.',
        'numeric_acceptance': {
            'final_matrix_exact_projection': 'Every target point in all six published views must be inside inclusive NDC [-1,1] on all axes.',
            'execution_error': 'Two binary64 affine stages, gamma6=sum-operation relative error bound and six least-subnormal absolute units per stage, propagated through the second stage.',
            'sum_order_controls': 'All six scalar orders independently in both stages and separately rounded or single-rounded fused controls.',
            'only_extreme_may_reject': 'reachable_binary32 with explicit numeric_insufficient. This is an honest unknown, not restored complete capability.',
            'ordinary_and_origin': 'Returned reliable fit required, plus unchanged exact coverage for four source-bound rectangular cases.',
            'renderer_and_coverage_tolerance_changes': False,
            'span_inflation': 'No unbounded span expansion. Existing 5 percent policy and actual readable-witness thresholds remain fixed.'},
        'micro_cases': [
            {'id': 'ordinary_4_vertices', 'world_vertices': ordinary['world_vertices'], 'world_bounds': ordinary['world_bounds']},
            {'id': 'ordinary_289_vertices', 'world_vertices': grid_world, 'world_bounds': [bounds(grid_world)]}],
        'microbenchmark': {'warmups_per_arm_per_case': 16, 'calls_per_block': 512,
                           'pair_orders': [['old', 'new'] if index % 2 == 0 else ['new', 'old'] for index in range(7)],
                           'timed_calls_total': 14336, 'warmup_calls_total': 64,
                           'clock': 'perf_counter_ns per call and continuous block. Helper result construction is included. Raw clocks preserved.',
                           'extra_micro_inputs_are_task_samples': False,
                           'scope': 'Ordinary helper work and latency only, no MCP or task benefit gate.'},
        'negative_regression': {'asset': 'D:/he_m4_target_001/assets_01/peripheral.blend',
                                'asset_sha256': 'b0b819b0981adecb287a174fcb30d620cf81d986844d9430a2e9b3ebb583794c',
                                'target': 'M4_Far_00', 'exact_Near_shadow_area': '73786983304225/9223372036854775808',
                                'expected_covered': 0, 'expected_witness': None,
                                'actual_execution_owner': 'root only'},
        'old_384_probe': 'reference retained, no new fuzz. Replay is not part of this minimal six-case suite.',
        'Blender_starts_by_this_freeze': 0, 'raster_calls_by_this_freeze': 0,
    }
    namespace = oracle.camera_namespace(raw, 'fixed03eb:blender_host.py')
    core = oracle.coverage_core(core_raw)
    records = [oracle.evaluate(namespace, core, case, 'old') for case in cases]
    assert all(row['passed'] for row in records), [(row['id'], row['passed']) for row in records]
    old_repro = {'schema': 'target-camera-reliability-old-reproduction-v1',
                 'source_sha256': inputs['baseline_host_sha256'], 'core_sha256': inputs['baseline_core_sha256'],
                 'records': records, 'case_count': len(records), 'passed_as_expected_baseline': True,
                 'new_Blender_starts': 0, 'new_rasters': 0, 'new_model_calls': 0}
    write_new('INPUTS.json', inputs)
    write_new('OLD_REPRO.json', old_repro)
    source_pins = [{'path': str(HERE / name), 'sha256': sha(HERE / name)}
                   for name in ('freeze_inputs.py', 'camera_numeric.py', 'micro_camera.py')]
    freeze = {'schema': 'target-camera-reliability-input-freeze-v1',
              'inputs_sha256': sha(HERE / 'INPUTS.json'), 'old_repro_sha256': sha(HERE / 'OLD_REPRO.json'),
              'baseline_host_sha256': inputs['baseline_host_sha256'], 'baseline_core_sha256': inputs['baseline_core_sha256'],
              'numeric_source_pins': source_pins, 'production_still_identical_to_baseline': True,
              'frozen_before_production_edit_ns': time.perf_counter_ns(),
              'camera_case_count': 6, 'micro_timed_calls': 14336, 'micro_warmup_calls': 64,
              'new_Blender_starts': 0, 'new_rasters': 0}
    write_new('INPUT_FREEZE.json', freeze)
    print(json.dumps({'status': 'INPUTS_AND_OLD_REPRO_READY', 'inputs_sha256': freeze['inputs_sha256'],
                      'old_repro_sha256': freeze['old_repro_sha256'], 'input_freeze_sha256': sha(HERE / 'INPUT_FREEZE.json'),
                      'camera_cases': len(cases), 'old_expected_baseline_passed': True}))


if __name__ == '__main__':
    main()

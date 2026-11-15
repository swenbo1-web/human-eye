"""Replay only the original 384 fixed-seed camera inputs, without new search."""

import argparse
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import random


HERE = Path(__file__).resolve().parent


def inspect(oracle, points, cameras):
    exact_xy_inside = True
    execution_xyz_inside = True
    for pose in cameras['views']:
        for point in points:
            camera, error = oracle.affine_error(pose['view_matrix'], tuple(map(Fraction, point)), (Fraction(0),) * 3)
            ndc, error = oracle.affine_error(pose['projection_matrix'], camera, error)
            exact_xy_inside &= all(-1 <= ndc[axis] <= 1 for axis in (0, 1))
            execution_xyz_inside &= all(-1 <= value - bound and value + bound <= 1 for value, bound in zip(ndc, error))
    return bool(exact_xy_inside), bool(execution_xyz_inside)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--new-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('_legacy_camera_replay_oracle', HERE / 'camera_numeric.py')
    oracle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oracle)
    baseline = json.loads((HERE / 'BASELINE.json').read_bytes())
    for original, expected in baseline['original_reference_pins'].items():
        copied = HERE / 'reference' / Path(original).name
        assert oracle.sha(copied.read_bytes()) == expected
    reference = json.loads((HERE / 'reference/camera_probe.json').read_bytes())
    old_raw = oracle.git_blob('human_eye_plugin/blender_host.py')
    new_raw = args.new_source.read_bytes()
    functions = {arm: oracle.camera_namespace(raw, arm)['_observation_target_cameras']
                 for arm, raw in (('old', old_raw), ('new', new_raw))}
    rng = random.Random(101511)
    cases = []
    for magnitude in (0., 1e6, 1e8, 1e10, 1e11, 1e12):
        for span in (1., .01, .001, .0001):
            for repeat in range(16):
                offset = [magnitude * rng.uniform(-1, 1) for _ in range(3)]
                points = [[offset[0] + dx * span, offset[1] + dy * span, offset[2]]
                          for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                bounds = [[min(point[k] for point in points) for k in range(3)],
                          [max(point[k] for point in points) for k in range(3)]]
                cases.append({'magnitude': magnitude, 'span': span, 'repeat': repeat,
                              'offset': offset, 'points': points, 'bounds': bounds})
    assert len(cases) == reference['counter']['cases'] == 384
    records = []
    counts = {arm: {'accepted': 0, 'numeric_insufficient': 0, 'unexpected_error': 0,
                    'accepted_exact_xy_clipped': 0, 'accepted_execution_xyz_unreliable': 0}
              for arm in ('old', 'new')}
    first_old_clipped = None
    for index, case in enumerate(cases):
        outcomes = {}
        for arm, function in functions.items():
            try:
                cameras = function(case['points'], [case['bounds']])
            except ValueError as error:
                kind = 'numeric_insufficient' if 'numeric_insufficient' in str(error) else 'unexpected_error'
                counts[arm][kind] += 1
                outcomes[arm] = {'outcome': kind, 'error': str(error)}
                continue
            counts[arm]['accepted'] += 1
            exact, execution = inspect(oracle, case['points'], cameras)
            counts[arm]['accepted_exact_xy_clipped'] += int(not exact)
            counts[arm]['accepted_execution_xyz_unreliable'] += int(not execution)
            outcomes[arm] = {'outcome': 'accepted', 'exact_xy_inside': exact, 'execution_gamma6_xyz_inside': execution}
            if arm == 'old' and not exact and first_old_clipped is None:
                first_old_clipped = case
        records.append({'index': index, **case, 'outcomes': outcomes})
    assert counts['old']['accepted'] == reference['counter']['accepted'] == 384
    assert counts['old']['accepted_exact_xy_clipped'] == reference['counter']['accepted_clipped'] == 14
    assert first_old_clipped['points'] == reference['first_clipped']['points']
    assert first_old_clipped['offset'] == reference['first_clipped']['offset']
    passed = (counts['new']['unexpected_error'] == 0 and counts['new']['accepted_exact_xy_clipped'] == 0
              and counts['new']['accepted_execution_xyz_unreliable'] == 0)
    output = {'schema': 'target-camera-original-384-replay-v1', 'passed_checked_scope': passed,
              'source_sha256': {'old': oracle.sha(old_raw), 'new': oracle.sha(new_raw)},
              'legacy_generator_sha256': oracle.sha((HERE / 'reference/probe_camera.py').read_bytes()),
              'legacy_result_sha256': oracle.sha((HERE / 'reference/camera_probe.json').read_bytes()),
              'input_list_sha256': oracle.sha(json.dumps(cases, sort_keys=True, separators=(',', ':')).encode()),
              'replay_source_sha256': oracle.sha(Path(__file__).read_bytes()), 'case_count': 384,
              'counts': counts, 'records': records,
              'scope': 'The original 6 magnitudes by 4 spans by 16 repeats, exact seed 101511 and original operation order. No input selection or new fuzz.',
              'not_executed': ['original later 64-box loop', 'original negative-X search loop', 'new random seeds or ranges'],
              'limitations': ['Synthetic pure numeric world coordinates are not 384 real Blender assets or task samples.',
                              'Numeric insufficiency remains distinct from recovered fitted capability.'],
              'Blender_starts': 0, 'raster_calls': 0, 'model_calls': 0}
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': passed, 'cases': 384, 'counts': counts}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())

"""Check the complete frozen input before enabling product implementation."""

from fractions import Fraction
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rational(value):
    return Fraction(int(value['numerator']), int(value['denominator']))


def main():
    manifest = read(HERE / 'qualification/SOURCE_OUTPUT_MANIFEST.json')
    for row in manifest['files']:
        path = HERE / row['path']
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], row['path']
    for row in manifest['external_sources']:
        assert sha(ROOT / row['path']) == row['sha256']
    baseline = read(HERE / 'BASELINE_SOURCE.json')
    for row in baseline['source_manifest']:
        assert sha(ROOT / row['path']) == row['sha256'], row['path']
    qualification = read(HERE / 'qualification/QUALIFICATION_READY.json')
    assert qualification['qualification_status'] == 'passed'
    assert qualification['all_owned_Blender_processes_reaped']
    controls = read(HERE / 'qualification/CONTROL_CERTIFICATES.json')
    assert controls['passed'] and all(controls['checks'].values())
    states = {}
    for state in ('BASE', 'EDIT'):
        snapshot = read(HERE / 'qualification' / (state + '_SNAPSHOT.json'))
        truth = read(HERE / 'qualification' / (state + '_TRUTH.json'))
        objects = {row['name']: row for row in snapshot['objects']}
        threshold = Fraction(.002)
        assert len(truth['pairs']) == 276 and truth['passed']
        assert all(truth['qualification_checks'].values())
        pairs = set()
        matches = 0
        for row in truth['pairs']:
            pair = (row['object_a'], row['object_b'])
            assert pair not in pairs and pair[0] < pair[1]
            pairs.add(pair)
            witness = row['witness']
            points = []
            for suffix, name in (('a', pair[0]), ('b', pair[1])):
                obj = objects[name]
                triangle = obj['triangles'][witness['triangle_' + suffix]]
                bary = [rational(v) for v in witness['barycentric_' + suffix]]
                assert sum(bary) == 1 and min(bary) >= 0
                point = [sum((bary[i] * Fraction(obj['vertices_world'][triangle[i]][k])
                              for i in range(3)), Fraction(0)) for k in range(3)]
                assert point == [rational(v) for v in witness['point_' + suffix]]
                points.append(point)
            square = sum(((a - b) ** 2 for a, b in zip(*points, strict=True)), Fraction(0))
            assert square == rational(row['exact_squared_distance_m2'])
            assert row['matches_threshold'] == (square <= threshold ** 2)
            assert row['triangle_pairs_solved'] + row['triangle_pairs_bound_pruned'] == row['triangle_pairs_total']
            pruned = row['minimum_pruned_lower_squared_m2']
            assert pruned is None or rational(pruned) >= square
            if row['matches_threshold']:
                assert row['api_AABB_Linf_retained']
                matches += 1
        assert truth['candidate_count'] >= 69 and matches == truth['match_count']
        states[state.lower()] = {'all_pairs': len(pairs), 'matches': matches,
                                 'candidates': truth['candidate_count'],
                                 'truth_sha256': sha(HERE / 'qualification' / (state + '_TRUTH.json'))}
    output = {'status': 'qualified_input_frozen', 'states': states,
              'legal_witnesses_checked': 552, 'analytic_controls_passed': 16,
              'original_product_sources_verified': 137, 'product_pretests': 0,
              'allowed_next_step': 'Initial surface-scan implementation under the existing work order.',
              'qualification_manifest_sha256': sha(HERE / 'qualification/SOURCE_OUTPUT_MANIFEST.json')}
    with (HERE / 'INPUT_FREEZE.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(output))


if __name__ == '__main__':
    main()

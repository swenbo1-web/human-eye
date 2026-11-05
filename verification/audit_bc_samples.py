"""Reviewer-side reduction of BC raw samples; does not trust author gate flags."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(report):
    workers = report['workers']
    assert len(workers) == 3 and len({w['pid'] for w in workers}) == 3
    assert report['protocol']['processes'] == 3
    assert report['protocol']['warmups_per_case'] == 5
    assert report['protocol']['paired_samples_per_case'] == 31
    for worker in workers:
        assert worker['source_sha256'] == report['source_sha256']
        assert all(value == '1' for value in worker['thread_env'].values())
    result = {}
    for name in workers[0]['cases']:
        runs = [w['cases'][name] for w in workers]
        medians, pooled_a, pooled_b, differences = [], [], [], []
        max_delta = 0.
        for worker_id, run in enumerate(runs):
            assert 'error' not in run
            assert len(run['warmups']) == 5 and len(run['samples']) == 31
            assert len(run['stages']) == 6
            assert run['changed_vertex_counts'] == run['vertex_counts']
            assert run['state_sha256'] == runs[0]['state_sha256']
            assert run['state_sha256'][0] != run['state_sha256'][1]
            a, b = [], []
            for i, sample in enumerate(run['samples']):
                assert sample['phase'] == (i + 6) % 2
                assert sorted(sample['order']) == ['bvh', 'full_pairs']
                if i:
                    assert sample['order'] == run['samples'][i - 1]['order'][::-1]
                av = sample['methods']['bvh']['total_ns']
                bv = sample['methods']['full_pairs']['total_ns']
                assert av > 0 and bv > 0
                a.append(av); b.append(bv)
            for item in [run['cold'], *run['samples'], *run['stages']]:
                quality = item['quality']
                tolerance = quality['tolerance_m']
                ra, rb = [item['methods'][method]['result'] for method in ('bvh', 'full_pairs')]
                delta = abs(ra['distance_m'] - rb['distance_m'])
                assert delta <= tolerance
                max_delta = max(max_delta, delta)
                for method in ('bvh', 'full_pairs'):
                    value = item['methods'][method]['result']
                    assert np.isfinite(value['distance_m']) and value['distance_m'] >= 0
                    for side, nfaces in zip(('a', 'b'), run['face_counts']):
                        assert 0 <= value['triangle_' + side] < nfaces
                        assert np.isfinite(value['point_' + side]).all()
                    separation = np.linalg.norm(np.subtract(value['point_a'], value['point_b']))
                    assert abs(separation - value['distance_m']) <= tolerance
                    checks = quality['witness_checks'][method]
                    for key, error in checks.items():
                        if key.endswith('_m'):
                            assert error <= tolerance
                    if quality['expected_m'] is not None:
                        expected = quality['expected_m']
                        assert abs(expected - value['distance_m']) <= tolerance
                        assert (expected == 0) == (value['distance_m'] == 0)
            medians.append({'bvh_ms': float(np.median(a)) / 1e6,
                            'full_pairs_ms': float(np.median(b)) / 1e6,
                            'speedup': float(np.median(b) / np.median(a))})
            pooled_a.extend(a); pooled_b.extend(b)
            differences.extend(np.subtract(a, b).tolist())
        ratio = float(np.percentile(pooled_a, 95) / np.percentile(pooled_b, 95))
        dense = name == 'dense_512'
        if not dense and runs[0]['face_counts'][0] == 512:
            assert all(m['speedup'] >= 2 for m in medians)
        if not dense and runs[0]['face_counts'][0] == 128:
            assert ratio <= 1.20
        result[name] = {
            'sample_count': len(pooled_a), 'process_medians': medians,
            'pooled_p95_ms': {'bvh': float(np.percentile(pooled_a,95)) / 1e6,
                              'full_pairs': float(np.percentile(pooled_b,95)) / 1e6},
            'pooled_p95_ratio': ratio,
            'paired_difference_p95_ms': float(np.percentile(differences,95)) / 1e6,
            'max_absolute_distance_delta_m': max_delta,
        }
        if dense:
            result[name]['phase_medians_ms'] = {
                str(phase): {method: float(np.median([
                    s['methods'][method]['total_ns'] for run in runs
                    for s in run['samples'] if s['phase'] == phase])) / 1e6
                    for method in ('bvh','full_pairs')}
                for phase in (0,1)}
    return result


if __name__ == '__main__':
    path = ROOT / sys.argv[1]
    report = json.loads(path.read_text(encoding='utf-8'))
    result = audit(report)
    for relative, expected in report['source_sha256'].items():
        assert digest(ROOT / relative) == expected
    print(json.dumps(result, indent=2))

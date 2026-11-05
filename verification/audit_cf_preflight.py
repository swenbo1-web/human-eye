"""Bind stage-one CF evidence and freeze inputs; does not accept learning gains."""
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE = 'artifacts/cf/'


def read(name):
    return json.loads((ROOT / name).read_bytes())


def identity(name):
    data = (ROOT / name).read_bytes()
    return {'path': name, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def main():
    manifest = read(BASE + 'preflight_001/source-identity.json')
    source_checks = {}
    amendments = {'docs/CF_WORK_ORDER.md', 'docs/CF_ACCEPTANCE_PROTOCOL.md',
                  'human_eye_fast/raycast_saccade_gpu.py'}
    for name, expected in manifest['source'].items():
        source_checks[name] = identity(name)['sha256'] == expected['sha256']
        assert source_checks[name] or name in amendments, name
    assert identity('verification/baselines/vg_before_cf.py')['sha256'] == manifest['source']['human_eye_fast/raycast_saccade_gpu.py']['sha256']
    assert identity(BASE + 'root_review_001/source/docs/CF_ACCEPTANCE_PROTOCOL.md')['sha256'] == manifest['source']['docs/CF_ACCEPTANCE_PROTOCOL.md']['sha256']
    for name, expected in manifest['artifacts'].items():
        actual = identity(BASE + 'preflight_001/' + name)
        assert actual['sha256'] == expected['sha256'] and actual['bytes'] == expected['bytes'], name
    fixtures = read(BASE + 'root_review_001/fixture_review_probe.json')
    assert fixtures['manifest_checks']['main_count'] == 2160
    assert all(fixtures['outcome_checks'].values())
    for split in ('train', 'validation', 'evaluation', 'control', 'diagnostic'):
        assert all(fixtures['manifest_checks'][split].values())
    assert [k for k, v in fixtures['hash_checks'].items() if not v] == ['source/human_eye_fast/raycast_saccade_gpu.py']
    math = read(BASE + 'root_review_001/baseline_review_probe.json')
    assert math['triangle_pairs'] == 173 and not math['triangle_failures']
    assert all(math['native_and_observable_checks'].values()) and math['source_unchanged']
    native = read(BASE + 'root_native_001/review.json')
    assert native['passed'] and native['native_exit'] == native['score_exit'] == 0
    assert native['sources_before'] == native['sources_after']
    for name, digest in native['sources_before'].items():
        assert identity(BASE + 'root_native_001/source/' + name)['sha256'] == digest
    for name, expected in native['artifacts'].items():
        actual = identity(BASE + 'root_native_001/' + name)
        assert actual['sha256'] == expected['sha256'] and actual['bytes'] == expected['bytes']
    public = read(BASE + 'root_native_001/pixels.json')
    assert all(s['public_pixels']['passed'] and all(g['pass'] and g['mismatches'] == 0
               for g in s['audit_image_grid'].values()) for s in public.values())
    replay_names = ('A-before.json', 'A-after.json', 'A-schema.json', 'V-0.png', 'V-1.png',
                    'V-0-bottom.npy', 'V-1-bottom.npy', 'native.json', 'pixels.json')
    assert all((ROOT / BASE / 'root_native_001' / n).read_bytes() ==
               (ROOT / BASE / 'preflight_001' / n).read_bytes() for n in replay_names)
    hook = read(BASE + 'vg_integration_001/result.json')
    assert hook['passed'] and len(hook['quality']) == 24 and len(hook['controls']) == 2
    assert len(hook['samples']) == 31 and len(hook['warmups']) == 5
    assert hook['source_before'] == hook['source_after']
    for name, digest in hook['source_before'].items():
        assert identity(name)['sha256'] == digest
    for case in hook['quality']:
        folder = ROOT / BASE / 'vg_integration_001' / f"case-{case['scene']:02}"
        data = (folder / 'A.png').read_bytes()
        assert data == (folder / 'R.png').read_bytes() == (folder / 'identity.png').read_bytes()
        assert hashlib.sha256(data).hexdigest() == case['old_new_identity_sha256']
        assert case['rank_called_once_before_first_ray'] and case['same_metadata_except_camera_name']
        assert case['actual_reverse_rays'] == case['reverse_selection']['ray_count']
    stats = {m: {'median_ns': float(np.median([s['elapsed_ns'][m] for s in hook['samples']])),
                 'p95_ns': float(np.quantile([s['elapsed_ns'][m] for s in hook['samples']], .95, method='linear'))}
             for m in ('A', 'R')}
    assert stats == hook['statistics']
    assert all(stats['R'][metric] / stats['A'][metric] <= 1.05 for metric in ('median_ns', 'p95_ns'))
    protocol = (ROOT / 'docs/CF_ACCEPTANCE_PROTOCOL.md').read_text(encoding='utf-8')
    assert '全部 diagnostic' in protocol and 'V、A 两个子区间' in protocol
    dependencies = {name: identity(name) for name in manifest['source'] if name.startswith('human_eye_fast/')}
    frozen = {name: identity(name) for name in ('docs/CF_ACCEPTANCE_PROTOCOL.md',
        'verification/cf_fixtures.py', 'verification/cf_baselines.py',
        'verification/test_cerebellar_flash.py', 'verification/test_cf_vg_integration.py')}
    report = {
        'decision': 'ACCEPT_PREFLIGHT_ONLY', 'date': '2026-11-05',
        'frozen': frozen, 'dependencies': dependencies,
        'original_delivered_source_matches_current': source_checks,
        'explicit_prefreeze_amendments': ['All diagnostic geometry/features/results sealed until model selection freezes',
                                         'V subinterval p95 <= 1.10 as well as A subinterval and combined episode',
                                         'VG trusted direction-order callback; default behavior retained'],
        'manifest_counts': fixtures['counts'],
        'math_probe_pairs': 173, 'math_probe_max_abs_error': math['max_absolute_distance_error'],
        'native_observable_checks': math['native_and_observable_checks'],
        'root_source_bound_replay_passed': True,
        'root_replay_identical_artifacts_to_original': list(replay_names),
        'root_positive_PNG_and_2500_grid_pixels_passed': True,
        'hook_statistics': stats,
        'hook_median_ratio': stats['R']['median_ns'] / stats['A']['median_ns'],
        'hook_p95_ratio': stats['R']['p95_ns'] / stats['A']['p95_ns'],
        'evidence': [identity(BASE + p) for p in ('preflight_001/source-identity.json',
            'root_review_001/fixture_review_probe.json', 'root_review_001/baseline_review_probe.json',
            'root_native_001/review.json', 'vg_integration_001/result.json')],
        'next': 'Same CF implementation chat: implement model/memory, train and select within frozen budget, then held-out evaluation and complete native costs. No restart of accepted BC/VG/AO optimization.',
        'not_completed': ['CF runtime and training', 'held-out or diagnostic outcomes', 'A before/after PNG chain',
                          'formal F/R/L benefit and full/per-head tail gates', 'prequential and capacity/lifetime', 'S head'],
    }
    target = ROOT / 'docs/radical_acceptance_cf_preflight.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'decision': report['decision'], 'protocol_sha256': frozen['docs/CF_ACCEPTANCE_PROTOCOL.md']['sha256'],
                      'hook_median_ratio': report['hook_median_ratio'], 'hook_p95_ratio': report['hook_p95_ratio']}))


if __name__ == '__main__':
    main()

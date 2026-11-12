"""Cross-check two anonymous graders and seal quality before cost unblinding."""
from collections import Counter
from decimal import Decimal
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT = Path('D:/hefe')
HERE = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH = AUTHOR / 'verification/m4_surface_scan_compact_consumption_001'
PUBLIC = BATCH / 'quality/public'
DELIVERY = 'f5cfcf5e4768b1b6c31127b5d4a6c1227b8d7907'


def load(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def main():
    primary = load(HERE / 'numeric/RESULTS.json')
    second = load(HERE / 'answers/RESULTS.json')
    second_numbers = load(HERE / 'answers/NUMERIC_RESULTS.json')
    package = load(HERE / 'package/RESULTS.json')
    index = load(PUBLIC / 'INDEX.json')
    assert package['all_passed'] and not package['failed']
    assert subprocess.check_output(['git', '-C', str(AUTHOR), 'rev-parse', 'HEAD']).decode().strip() == DELIVERY
    assert subprocess.check_output(['git', '-C', str(AUTHOR), 'status', '--porcelain']).strip() == b''
    mappings = [{r['anonymous_id']: r for r in data} for data in
                (primary['answers'], second['answers'], second_numbers['answers'],
                 package['facts']['anonymous_rows'], index['answers'])]
    assert all(set(m) == set(mappings[0]) and len(m) == 9 for m in mappings)
    rows = []
    checked_distance_rows = 0
    for anonymous in sorted(mappings[0]):
        a, b, bn, p, ix = [m[anonymous] for m in mappings]
        per_answer = load(HERE / 'numeric' / (anonymous + '.json'))
        am = {tuple(sorted(r['pair'])): Decimal(r['value_text_mm']) for r in per_answer['per_pair']}
        bm = {tuple(sorted(r['pair'])): Decimal(r['distance_mm']) for r in bn['parsed_rows']}
        assert len(am) == len(bm) == len(per_answer['per_pair']) == len(bn['parsed_rows']) == 71
        assert am == bm, anonymous + ': independent parsed facts differ'
        checked_distance_rows += len(am)
        assert a['content_classification'] == b['content_classification']
        assert a['primary_classification'] == b['final_classification']
        assert a['cell_execution_state'] == b['execution_state'] == p['state'] == ix['cell_execution_state']
        assert a['consumer_valid_completion'] == b['consumer_valid_completion'] == ix['consumer_valid_completion']
        assert not b['manual_semantic_review_pending']
        assert b['pair_distance_presentation_pass']
        assert a['parsed_rows'] == a['unique_pairs'] == a['true_positive_pairs'] == b['final_pair_count'] == 71
        assert all(not a[k] for k in ('false_positive_pairs', 'missing_pairs', 'duplicate_pairs', 'wrong_distance_rows', 'presentation_incomplete_rows', 'additional_definite_errors'))
        answer = PUBLIC / anonymous / 'answer.txt'
        answer_sha = sha(answer)
        assert answer_sha == ix['answer_original_sha256'] == p['final_sha256']
        assert answer.read_bytes() == (PUBLIC / anonymous / 'cli_output_unconfirmed.txt').read_bytes()
        rows.append({
            'anonymous_id': anonymous, 'final_sha256': answer_sha,
            'execution_state': ix['cell_execution_state'],
            'consumer_valid_completion': ix['consumer_valid_completion'],
            'execution_errors': ix['consumer_execution_errors'],
            'primary_classification': a['primary_classification'],
            'final_content_classification': a['content_classification'],
            'matching_facts_correct': 71, 'matching_facts_required': 71,
            'missing': 0, 'extra': 0, 'duplicate': 0, 'wrong_distance': 0,
            'completeness': b['completeness_claim'],
        })
    assert checked_distance_rows == 639
    counted = dict(Counter(r['primary_classification'] for r in rows))
    content_counted = dict(Counter(r['final_content_classification'] for r in rows))
    assert counted == primary['primary_counts'] == second['execution_retaining_counts']
    assert content_counted == primary['content_counts'] == second['final_content_counts']
    fixed = {'r2_zip_sha256': '5d2ca81f18285da1fff1a05b9c0c03deb97966f57db86fa022c8ecc0b091f54f',
             'public_canonical_sha256': '03c566a5438fad7454b1d9f91157c3627a5fbd3740856972b61a353338fec101',
             'truth_sha256': 'a0f14b1a48601590445ce5e2d13bb34f56647caa2acedf3eeac97b32e8a656c7',
             'snapshot_sha256': 'f8a578f78004a21e611c76d47506c5290f6015e7343e67b3b094a9e54da9884b'}
    assert package['facts']['zip_sha256'] == primary['frozen_zip_sha256'] == fixed['r2_zip_sha256']
    assert package['facts']['final_public_canonical_sha256'] == fixed['public_canonical_sha256']
    assert sha(PUBLIC / 'scoring/TRUTH.json') == primary['truth_sha256'] == fixed['truth_sha256']
    assert sha(PUBLIC / 'scoring/ACTUAL_SNAPSHOT.json') == primary['snapshot_sha256'] == fixed['snapshot_sha256']
    review_inputs = [HERE / relative for relative in (
        'numeric/RESULTS.json', 'numeric/REPORT.md', 'answers/RESULTS.json',
        'answers/REPORT.md', 'package/RESULTS.json', 'package/REPORT.md', 'ROOT_MANUAL_REVIEW.md')]
    seal = {'schema': 'root-anonymous-quality-seal-v1', 'date': '2026-11-13',
        'cycle_id': 'M4-SURFACE-SCAN-COMPACT-CONSUMPTION-001',
        'delivery_commit': DELIVERY, 'preparation_commit': '3a1ba86c5fce2fe125671cc68a84b14031d318cb',
        **fixed, 'quality_before_cost': True, 'private_mapping_opened': False,
        'cost_usage_analysis_performed': False, 'finite_anonymity': 'Original business content may reveal route or incidental timings; not used for grading.',
        'primary_counts': {key: counted.get(key, 0) for key in ('complete_correct', 'incomplete', 'incorrect', 'execution_failure', 'not_run')},
        'content_counts': content_counted, 'finals_present': 9,
        'matching_facts_correct': checked_distance_rows, 'matching_facts_required': 639,
        'answers': rows, 'review_input_sha256': {p.relative_to(ROOT).as_posix(): sha(p) for p in review_inputs},
        'source_scope': 'Public evidence and immutable batch hashes bound; private final/thread/loaded source mapping remains for post-seal cost stage.',
        'new_Blender_model_API_runs': 0,
    }
    save(HERE / 'QUALITY_SEAL.json', seal)
    files = sorted(p for p in HERE.rglob('*') if p.is_file() and p.name != 'REVIEW_MANIFEST.json' and '__pycache__' not in p.parts)
    files += [ROOT / 'docs/M4_SURFACE_SCAN_COMPACT_CONSUMPTION_001_QUALITY_REVIEW.md',
              ROOT / 'docs/M4_SURFACE_SCAN_COMPACT_CONSUMPTION_001_COST_PLAN.md']
    records = [{'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in files]
    save(HERE / 'REVIEW_MANIFEST.json', {'files': records, 'content_files': len(records), 'bytes': sum(r['bytes'] for r in records), 'self_excluded': True})
    print(json.dumps({'quality_seal_sha256': sha(HERE / 'QUALITY_SEAL.json'), 'primary': counted, 'content': content_counted, 'facts': checked_distance_rows, 'content_files': len(records)}))


def verify_staged():
    manifest_path = HERE / 'REVIEW_MANIFEST.json'
    expected = {r['path']: r for r in load(manifest_path)['files']}
    expected[manifest_path.relative_to(ROOT).as_posix()] = {'bytes': manifest_path.stat().st_size, 'sha256': sha(manifest_path)}
    actual = subprocess.check_output(['git', '-C', str(ROOT), 'diff', '--cached', '--name-only', '-z']).decode().rstrip('\0').split('\0')
    assert set(actual) == set(expected)
    for path, record in expected.items():
        data = subprocess.check_output(['git', '-C', str(ROOT), 'show', ':' + path])
        assert data == (ROOT / path).read_bytes()
        assert len(data) == record['bytes'] and hashlib.sha256(data).hexdigest() == record['sha256']
    print(json.dumps({'staged_exact_files': len(expected), 'passed': True}))


if __name__ == '__main__':
    if sys.argv[1:] == ['--verify-staged']:
        verify_staged()
    else:
        main()

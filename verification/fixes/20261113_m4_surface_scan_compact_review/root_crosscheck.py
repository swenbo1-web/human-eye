"""Cross-check root review outputs and freeze the review's file inventory."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT = Path('D:/hefe')
HERE = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
PRODUCT = '452b44d2dcf231d6675bef54e568db0431a29261'
DELIVERY = '6ab4e53409e539c71a377f48708f2f8725db6dde'
SOURCE = '4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6'
checks = []


def read(path):
    return json.loads(path.read_bytes())


def check(name, condition):
    checks.append({'name': name, 'passed': bool(condition)})


def git(*args):
    return subprocess.check_output(['git', '-C', str(AUTHOR), *args])


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def main():
    semantic = read(HERE / 'semantics/RESULT.json')
    binding = read(HERE / 'binding/RESULTS.json')
    engineering = read(HERE / 'engineering/RESULTS.json')
    ready = read(AUTHOR / 'verification/m4_surface_scan_compact_facts_001/ENGINEERING_READY.json')
    check('implementation_fixed_head', git('rev-parse', 'HEAD').decode().strip() == DELIVERY)
    check('implementation_tracked_clean', git('status', '--porcelain').strip() == b'')
    changed = git('diff', '--name-only', 'c1cb2da32034e056a270384e691a2cde8dddbc0d', PRODUCT, '--', 'human_eye_plugin').decode().splitlines()
    check('one_product_file', changed == ['human_eye_plugin/live_spatial_mcp.py'])
    check('source_identity', ready['source_sha256'] == SOURCE == binding['facts']['source_sha256'])
    check('semantic_passed', semantic['passed'] == semantic['checks'] and not semantic['failed'])
    check('binding_passed', binding['all_passed'] and not binding['failed'])
    # The engineering result's own independent pass and numeric summary are
    # inspected here after its structure is frozen, rather than importing its verifier.
    check('engineering_passed', engineering['passed'] and not engineering['failed_checks'])
    check('five_author_rows', len(ready['business_rows']) == 5)
    check('actual_text_sizes', [r['business_text_utf8_bytes'] for r in ready['business_rows']] == [7911, 7911, 34754, 7912, 35209])
    check('actual_match_counts', [r['matches'] for r in ready['business_rows']] == [71, 71, 71, 72, 72])
    check('actual_new_kernels', [r['kernel_calls'] for r in ready['business_rows']] == [112, 0, 0, 10, 0])
    check('one_capture_per_request', [r['host_captures'] for r in ready['business_rows']] == [1] * 5)
    check('six_old_response_probes', len([p for p in semantic['probes'] if p['name'].startswith(('P1.', 'P2.', 'P3.'))]) == 6)
    check('old_full_baseline_bytes', all(p['full_bytes'] == 34754 and p['compact_bytes'] == 7911 and p['rows'] == 71 for p in semantic['probes'] if p['name'].startswith(('P1.', 'P2.', 'P3.'))))
    check('five_independent_rows', len(engineering['five_rows']) == 5 == len(binding['facts']['business_rows']))
    for actual, provenance, author in zip(engineering['five_rows'], binding['facts']['business_rows'], ready['business_rows'], strict=True):
        label = actual['state']
        check(label + '_identity', label == provenance['id'] == author['state'])
        check(label + '_bytes', actual['actual_text_utf8_bytes'] == provenance['body_bytes'] == author['business_text_utf8_bytes'])
        check(label + '_kernel', actual['kernel_calls'] == provenance['kernel_calls'] == author['kernel_calls'])
        check(label + '_facts', actual['matches'] == author['matches'])
        check(label + '_request_time', actual['client_request_ns'] == author['request_wall_ns'])
        check(label + '_capture', actual['host_rpc'] == author['host_captures'] == 1)
    check('independent_full_time', engineering['cost_scope']['full_session_ns'] == binding['facts']['full_engineering_wall_ns'] == 4862992900)
    check('independent_host_request_bytes', engineering['cost_scope']['business_host_request_bytes'] == binding['facts']['business_host_bytes']['request'] == 104520)
    check('independent_host_response_bytes', engineering['cost_scope']['business_host_response_attempted_bytes'] == binding['facts']['business_host_bytes']['response'] == 538172)
    result = {
        'product_commit': PRODUCT, 'delivery_commit': DELIVERY, 'source_sha256': SOURCE,
        'checks': checks, 'all_passed': all(c['passed'] for c in checks),
        'new_Blender_runs': 0, 'new_model_consumers': 0, 'new_paid_API_calls': 0,
        'existing_business_observations': 5,
        'scope': 'Cross-check independent results, source scope and fixed numeric gates; individual scripts contain primary-evidence verification.',
    }
    save(HERE / 'ROOT_CROSSCHECK.json', result)
    if not result['all_passed']:
        raise SystemExit('root crosscheck failed')
    paths = sorted(p for p in HERE.rglob('*') if p.is_file() and p.name != 'REVIEW_MANIFEST.json' and '__pycache__' not in p.parts)
    paths += [ROOT / 'docs/M4_SURFACE_SCAN_COMPACT_FACTS_001_REVIEW.md', ROOT / 'docs/M4_SURFACE_SCAN_COMPACT_CONSUMPTION_001_PLAN.md']
    files = [{'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]
    save(HERE / 'REVIEW_MANIFEST.json', {'files': files, 'content_files': len(files), 'bytes': sum(f['bytes'] for f in files), 'self_excluded': True})
    print(json.dumps({'checks': len(checks), 'passed': True, 'content_files': len(files)}))


def verify_staged():
    manifest_path = HERE / 'REVIEW_MANIFEST.json'
    manifest = read(manifest_path)
    expected = {item['path']: item for item in manifest['files']}
    expected[manifest_path.relative_to(ROOT).as_posix()] = {
        'sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        'bytes': manifest_path.stat().st_size,
    }
    actual = subprocess.check_output(['git', '-C', str(ROOT), 'diff', '--cached', '--name-only', '-z']).decode().rstrip('\0').split('\0')
    assert set(actual) == set(expected), 'staged scope differs from exact review inventory'
    for path, item in expected.items():
        content = subprocess.check_output(['git', '-C', str(ROOT), 'show', ':' + path])
        assert content == (ROOT / path).read_bytes(), path + ': staged != disk'
        assert len(content) == item['bytes'], path + ': size'
        assert hashlib.sha256(content).hexdigest() == item['sha256'], path + ': sha256'
    print(json.dumps({'staged_exact_files': len(expected), 'bytes_verified': True}))


if __name__ == '__main__':
    if sys.argv[1:] == ['--verify-staged']:
        verify_staged()
    else:
        main()

"""Verify saved finite acceptance and index this explicit spatial-fact delivery."""

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMMIT = 'e836e03f4b3821f869c72ac3e50df5204f28b50f'
SOURCE = '2c453e56f3abf83a49f9c8ef37a3a77728dd8f05168db4fd5217d3bad465c390'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def verify_sources(manifest, installed):
    requested = ''.join(COMMIT + ':' + row['path'] + '\n' for row in manifest).encode()
    raw = subprocess.check_output(['git', 'cat-file', '--batch'], input=requested, cwd=ROOT)
    cursor = 0
    for row in manifest:
        end = raw.index(b'\n', cursor)
        _, kind, length = raw[cursor:end].split()
        assert kind == b'blob'
        cursor = end + 1
        value = raw[cursor:cursor + int(length)]
        cursor += int(length) + 1
        assert sha(value) == row['sha256'], row['path']
        assert value == (ROOT / row['path']).read_bytes(), row['path']
        assert value == (installed / row['path']).read_bytes(), row['path']
    assert cursor == len(raw)


def verify():
    freeze = read(HERE / 'CANDIDATE_FREEZE.json')
    assert freeze['source_count'] == 137 and freeze['source_sha256'] == SOURCE
    ready = read(HERE / 'installation/READY.json')
    assert ready['commit'] == COMMIT and ready['source_sha256'] == SOURCE
    assert ready['source_count'] == 137 and ready['installed_identity_passed']
    assert ready['protected_inputs_unchanged'] and ready['no_default_activation']
    verify_sources(freeze['manifest'], Path(ready['install_root']))
    design = read(HERE / 'DESIGN_FREEZE.json')
    for name, expected in design['files'].items():
        assert sha((HERE / name).read_bytes()) == expected, name
    methods = 0
    for folder, count in (('initial_regressions_01', 213), ('initial_directed_01', 8), ('initial_wiring_01', 9)):
        result = read(HERE / 'testing' / folder / 'RESULTS.json')
        assert result['passed'] and result['methods'] == len(result['executed']) == count
        assert result['guard_verified'] and result['sources_unchanged'] and result['tests_unchanged']
        assert result['source_sha256'] == SOURCE and not result['failures'] and not result['errors']
        methods += count
    work = read(HERE / 'testing/initial_work_01/RESULTS.json')
    assert work['actual_calls'] == work['fixed_expected_calls'] == 6 and work['source_files_unchanged']
    timing = read(HERE / 'testing/sixty_01/RESULTS.json')
    assert timing['candidate_commit'] == COMMIT and timing['candidate_source_sha256'] == SOURCE
    assert timing['actual_calls'] == timing['fixed_calls'] == 60 and timing['retries'] == 0
    assert timing['source_files_unchanged'] and timing['preparation_files_unchanged']
    samples = timing['samples']
    assert len(samples) == 60 and len({row['sequence'] for row in samples}) == 60
    for row in samples:
        stem = str(row['sequence']).zfill(2) + '_' + row['arm']
        assert read(HERE / 'testing/sixty_01' / (stem + '.json')) == row
        assert sha((HERE / 'testing/sixty_01' / (stem + '.PAYLOAD.bin')).read_bytes()) == row['payload_sha256']
        assert row['error'] is None and row['within_original_30s']
    checks = read(HERE / 'testing/saved_verification_01/RESULTS.json')
    assert checks['passed'] and not checks['failed_checks'] and all(checks['frozen_gates'].values())
    assert checks['candidate_commit'] == COMMIT and checks['candidate_source_sha256'] == SOURCE
    medians = {case: {arm: statistics.median(row['complete_business_ns'] for row in samples
                 if row['case'] == case and row['arm'] == arm) for arm in ('reference', 'candidate')}
                 for case in {row['case'] for row in samples}}
    assert medians == checks['complete_business_medians_ns']
    old_sum = sum(value['reference'] for name, value in medians.items() if name.startswith('G508/'))
    new_sum = sum(value['candidate'] for name, value in medians.items() if name.startswith('G508/'))
    assert new_sum * 5 <= old_sum * 4
    entry = read(HERE / 'entry/run_01/RESULTS.json')
    public = read(HERE / 'entry/run_01/SAVED_VERIFICATION.json')
    counters = read(HERE / 'entry/run_01/COUNTER_VERIFICATION.json')
    assert entry['harness_execution_complete'] and entry['source_files_unchanged'] and not entry['errors']
    assert public['passed'] and public['new_contract_assembly_passed'] and public['legacy_failure_preserved']
    assert public['control_passed'] and public['cleanup_passed'] and public['source_sha256'] == SOURCE
    assert counters['passed'] and counters['new_spatial_work_and_zero_closed_verified']
    assert counters['new_request_preceded_legacy'] and counters['cross_semantic_memo_prewarming_absent']
    record = {
        'passed': True, 'product_commit': COMMIT, 'source_count': 137, 'source_sha256': SOURCE,
        'Git_disk_install_bytes_equal': True, 'regression_and_directed_methods': methods,
        'fixed_non_timing_work_calls': 6, 'fixed_primary_calls': 60,
        'all_primary_common_facts_and_cost_gates_passed': True,
        'g508_complete_business_medians_sum_ns': {'reference': old_sum, 'candidate': new_sum},
        'g508_sum_reduction_percent': (old_sum - new_sum) / old_sum * 100,
        'actual_new_MCP_contract_passed': True, 'actual_old_closed_failure_preserved': True,
        'actual_MCP_business_calls': 4, 'actual_MCP_host_RPC_including_QA_and_close': 6,
        'source_scope': 'strict separation of all referenced triangle convex hulls, with original closed fallback',
        'additional_guarantees_differ': 'reference certifies embedded closed shells; support path certifies strict hull separation',
        'product_calls_in_this_check': 0, 'model_consumers': 0,
        'review_scope': 'saved-only author delivery consistency check; administrator deep review is separate',
    }
    save(HERE / 'SAVED_VERIFICATION.json', record)
    print(json.dumps(record))


def index():
    files = []
    excluded = ('INDEX.json', 'COMPLETE.json')
    for path in sorted(HERE.rglob('*')):
        relative = path.relative_to(HERE)
        if not path.is_file() or relative.as_posix() in excluded:
            continue
        if path.suffix.lower() in ('.pyc', '.pyo') or any(part in ('tmp', '__pycache__') for part in relative.parts):
            continue
        raw = path.read_bytes()
        files.append({'path': relative.as_posix(), 'bytes': len(raw), 'sha256': sha(raw)})
    save(HERE / 'INDEX.json', {'files': files, 'count': len(files), 'bytes': sum(row['bytes'] for row in files),
                             'self_reference_exclusions': list(excluded),
                             'transient_exclusions': ['tmp/', '__pycache__/', '*.pyc', '*.pyo']})
    record = {
        'cycle_id': 'M3-SUFFICIENT-SEPARATION-001', 'execution_status': 'complete',
        'acceptance_status': 'passed_frozen_finite_spatial_fact_contract',
        'product_commit': COMMIT, 'source_count': 137, 'source_sha256': SOURCE,
        'index_sha256': sha((HERE / 'INDEX.json').read_bytes()),
        'report_sha256': sha((HERE / 'REPORT.md').read_bytes()),
        'saved_verification_sha256': sha((HERE / 'SAVED_VERIFICATION.json').read_bytes()),
        'indexed_files': len(files), 'substantive_simplifications_used': 0,
        'primary_calls': 60, 'non_timing_work_calls': 6, 'formal_MCP_sequences': 1,
        'business_calls': 4, 'owned_Blender_sessions': 1, 'default_activation': False,
        'model_consumers': 0, 'old_closed_qualification_still_failed': True,
        'next_step': 'administrator independent deep review',
    }
    save(HERE / 'COMPLETE.json', record)
    print(json.dumps(record))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', action='store_true')
    args = parser.parse_args()
    if args.index:
        index()
    else:
        verify()

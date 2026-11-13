"""Seal one FIX2 C episode, keeping execution and postclose qualification apart."""

import ast
import hashlib
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]


def read(path):
    return json.loads(path.read_bytes())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf8', newline='\n')


def main():
    prep = read(BATCH / 'PREPARATION.json')
    reserve = read(BATCH / 'ENGINEERING_STARTED.json')
    commit = reserve['preparation_commit']
    assert commit == '1511af696b564a0b261b70d5f0562325daa1f2a7'
    for item in prep['files']:
        raw = (BATCH / item['path']).read_bytes()
        assert len(raw) == item['bytes'] and sha(raw) == item['sha256'], item['path']
    for path, expected in prep['external_sha256'].items():
        assert sha(Path(path).read_bytes()) == expected, path
    relative = (BATCH / 'PREPARATION.json').relative_to(ROOT).as_posix()
    assert subprocess.check_output(['git', 'show', commit + ':' + relative], cwd=ROOT) == (BATCH / 'PREPARATION.json').read_bytes()
    result = read(BATCH / 'episodes/C/RESULTS.json')
    timing = read(BATCH / 'episodes/C/FINAL_TIMING.json')
    batch = read(BATCH / 'ENGINEERING_RESULT.json')
    assert batch['planned_episodes'] == batch['started_episodes'] == 1 and batch['N_episodes'] == 0
    assert batch['model_calls'] == batch['API_calls'] == 0
    assert batch['passed'] is timing['accepted_success'] is True
    assert result['execution_counts'] == {'planned': 3, 'attempted': 3, 'successful_returns': 3, 'succeeded': 3, 'failed': 0, 'not_run': 0}
    assert result['qualification_counts'] == {'planned': 3, 'passed': 3, 'failed': 0, 'unverified': 0}
    assert result['sequence_qualification_state'] == 'passed' and result['sequence_verification']['passed'] is True
    assert not result['errors'] and not result['qualification_errors'] and not timing['publication_errors']
    assert result['cleanup']['confirmed'] is True and result['asset_unchanged'] is True
    assert timing['within_590s'] is True and timing['full_episode_wall_ns'] == timing['business_receipts_closed_ns'] - timing['started_ns']
    rows = []
    for row, matches, kernels in zip(result['business'], (71, 71, 72), (112, 0, 10)):
        facts = row['verification']
        assert facts['matches'] == matches and facts['new_kernel_calls'] == kernels and facts['actual_host_capture_count'] == 1
        assert row['execution_state'] == 'succeeded' and row['qualification_state'] == 'passed'
        assert row['thin']['confirmed'] is True and row['thin']['bridge_cleanup']['confirmed'] is True
        assert row['started_ns'] < row['ended_ns'] <= result['qualification_started_ns'] <= row['qualification_started_ns'] <= row['qualification_ended_ns']
        assert facts['source_report']['rich_source_metadata_verified'] is False
        rows.append({'turn': row['turn'], 'matches': matches, 'new_kernel_calls': kernels,
                     'host_captures': 1, 'business_started_ns': row['started_ns'], 'business_ended_ns': row['ended_ns'],
                     'thin_wall_ns': row['thin']['wall_ns'], 'qualification_started_ns': row['qualification_started_ns'],
                     'qualification_ended_ns': row['qualification_ended_ns'],
                     'measurement_cache_before': facts['measurement_cache_before'], 'measurement_cache_after': facts['measurement_cache_after'],
                     'acquisition_work': facts['acquisition_work'], 'binding': facts['binding']})
    assert len(rows) == 3
    assert rows[0]['binding'] == rows[1]['binding'] and rows[1]['binding'] != rows[2]['binding']
    for name in ('lifecycle/REPORT.md', 'facts/REPORT.md'):
        assert (HERE / name).is_file(), name
    lifecycle = read(HERE / 'lifecycle/RESULTS.json')
    replay = read(HERE / 'facts/RESULTS.json')
    assert lifecycle['status'] == 'pass_as_recorded_success_audit' and lifecycle['checks'] == 1304
    assert replay['status'] == 'pass_as_actual_facts_replay' and replay['checks'] == 1719
    ready = {'callback': 'M4-SURFACE-SCAN-CONTINUITY-001_FIX2_READY', 'status': 'engineering_qualification_passed',
             'preparation_commit': commit, 'admin_commit': prep['admin_commit'],
             'preparation_sha256': sha((BATCH / 'PREPARATION.json').read_bytes()),
             'preserved_preparation_files': len(prep['files']) + 1, 'preserved_external_files': len(prep['external_sha256']),
             'product_commit': prep['product_commit'], 'product_source_sha256': prep['product_source_sha256'],
             'new_live_C_episodes': 1, 'new_live_N_episodes': 0, 'new_model_provider_API_calls': 0,
             'execution_counts': result['execution_counts'], 'qualification_counts': result['qualification_counts'],
             'sequence_qualification': result['sequence_verification'], 'turns': rows,
             'full_episode_wall_ns': timing['full_episode_wall_ns'], 'stages_ns': result['stages_ns'],
             'timing_scope': timing['scope'], 'owned_cleanup_confirmed': True,
             'qualification_follows_confirmed_finish': True,
             'unchanged_fixed_components': 'FIX1 actor, consumer, worker, stdio, product, snapshot binder, fact/sequence functions and WIRE reader',
             'offline_checks': {'phase_methods': 8, 'independent_contract_checks': 199, 'root_reconciliation_checks': 76},
             'actual_original_rechecks': {'lifecycle': 1304, 'lifecycle_input_files': 648,
                                         'facts': 1719, 'facts_input_files': 38,
                                         'counts_are_not_business_samples': True},
             'limits': ['One fixed scene and engineering episode.', 'No actual model resume, memory or usage semantics measured.',
                        'No fair N/C same-task model benefit comparison in this batch.', 'N prior engineering evidence reused only.',
                        'Missing rich source metadata remains unrecorded.', 'Model cash cost and total development/audit/coordination cost unmeasured.',
                        'Buffered report write/close, fsync-level durability unmeasured.', 'AL unbound at host_epoch 5.'],
             'prior_failures': 'CONTINUITY-001 and FIX1 original failures and not-run slots retained unchanged.',
             'next_action': 'Report to the authorized administrator, then await the fair continuous N/C model-consumption contract.'}
    save(BATCH / 'DELIVERY_READY.json', ready)
    files = []
    for path in sorted(BATCH.rglob('*'), key=lambda item: item.relative_to(BATCH).as_posix()):
        if not path.is_file() or path.name == 'DELIVERY_MANIFEST.json':
            continue
        assert '__pycache__' not in path.parts and path.suffix != '.pyc'
        raw = path.read_bytes()
        if path.suffix == '.json':
            json.loads(raw)
        if path.suffix == '.py':
            ast.parse(raw.decode('utf-8-sig'), filename=str(path))
        files.append({'path': path.relative_to(BATCH).as_posix(), 'bytes': len(raw), 'sha256': sha(raw)})
    save(BATCH / 'DELIVERY_MANIFEST.json', {'scope': 'All FIX2 files except this manifest itself', 'preparation_commit': commit,
                                         'file_count': len(files), 'total_bytes': sum(item['bytes'] for item in files), 'files': files})
    print(json.dumps({'files': len(files) + 1, 'manifest_sha256': sha((BATCH / 'DELIVERY_MANIFEST.json').read_bytes()),
                      'qualification_passed': True, 'actual_business': 3}))


if __name__ == '__main__':
    main()

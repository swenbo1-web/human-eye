"""Seal the fixed preparation, one failed C episode and its phase diagnosis."""

import ast
import hashlib
import importlib.util
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


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    prep = read(BATCH / 'PREPARATION.json')
    reserved = read(BATCH / 'ENGINEERING_STARTED.json')
    commit = reserved['preparation_commit']
    assert commit == 'e06597f92d1193b40e9a62b78919a3125e4e346d'
    for record in prep['files']:
        raw = (BATCH / record['path']).read_bytes()
        assert len(raw) == record['bytes'] and sha(raw) == record['sha256'], record['path']
    for path, expected in prep['external_sha256'].items():
        assert sha(Path(path).read_bytes()) == expected, path
    path = (BATCH / 'PREPARATION.json').relative_to(ROOT).as_posix()
    assert subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT) == (BATCH / 'PREPARATION.json').read_bytes()
    result = read(BATCH / 'episodes/C/RESULTS.json')
    timing = read(BATCH / 'episodes/C/FINAL_TIMING.json')
    batch = read(BATCH / 'ENGINEERING_RESULT.json')
    assert batch['started_episodes'] == batch['planned_episodes'] == 1 and batch['N_episodes'] == 0
    assert batch['passed'] is False and batch['model_calls'] == batch['API_calls'] == 0
    assert result['execution_counts'] == {'planned': 3, 'attempted': 1, 'completed': 0, 'failed': 1, 'not_run': 2}
    assert result['cleanup']['confirmed'] is True and result['asset_unchanged'] is True
    assert result['business'][0]['thin']['confirmed'] is True
    assert timing['accepted_success'] is False and timing['within_590s'] is True
    assert timing['full_episode_wall_ns'] == timing['business_receipts_closed_ns'] - timing['started_ns']
    assert result['errors'][0]['type'] == 'FileNotFoundError' and 'WIRE' in result['errors'][0]['message']
    folder = BATCH / 'episodes/C'
    runner = load('_fix1_delivery_runner', BATCH / 'engineering/run_candidate.py')
    qualification = load('_fix1_delivery_qualification', BATCH / 'qualification/verify_continuity.py')
    facts = runner.verify_business(read(folder / 'TURN_BASE.json'), folder, read(folder / 'owner/INITIAL.json'), qualification)
    assert facts['matches'] == 71 and facts['new_kernel_calls'] == 112 and facts['actual_host_capture_count'] == 1
    assert facts['source_report']['rich_source_metadata_verified'] is False
    for name in ('capture_phase/REPORT.md', 'lifecycle/REPORT.md'):
        assert (HERE / name).is_file(), name
    lifecycle = read(HERE / 'lifecycle/RESULTS.json')
    phase = read(HERE / 'capture_phase/REVIEW.json')
    assert lifecycle['status'] == 'pass_as_recorded_failure_audit'
    assert lifecycle['checks'] == 4008 and lifecycle['original_engineering_qualification_passed'] is False
    assert phase['passed_offline'] is True and phase['candidate_installed_or_applied'] is False
    assert phase['candidate_denied_paths'] == []
    assert read(HERE / 'capture_phase/PHASE_TEST_02.json')['passed'] is True
    ready = {
        'callback': 'M4-SURFACE-SCAN-CONTINUITY-001_FIX1_READY',
        'status': 'delivery_ready_engineering_qualification_failed',
        'initial_preparation_commit': '8000b52f', 'fixed_preparation_commit': commit,
        'admin_commit': prep['admin_commit'], 'preparation_sha256': sha((BATCH / 'PREPARATION.json').read_bytes()),
        'fixed_preparation_files_unchanged': len(prep['files']) + 1,
        'fixed_external_files_unchanged': len(prep['external_sha256']),
        'product_commit': prep['product_commit'], 'product_source_sha256': prep['product_source_sha256'],
        'actor_sha256': prep['actor_sha256'], 'new_live_C_episodes': 1, 'new_live_N_episodes': 0,
        'planned_business': 3, 'actual_business': 1, 'successful_tool_and_thin_exit': 1,
        'frozen_counts': result['execution_counts'], 'engineering_qualification_pass': False,
        'new_model_provider_API_calls': 0, 'owned_cleanup_confirmed': True,
        'failure': 'Online qualification depended on WIRE/INDEX.json, which is published only at worker close.',
        'postclose_actual_C1_fact_check': facts,
        'C1_fact_scope': 'Postclose correctness and phase-reader candidate evidence do not upgrade the original failed episode.',
        'actual_C_repeat_edit': 'not_run', 'registered_EDIT': False,
        'complete_episode_wall_ns': timing['full_episode_wall_ns'], 'stages_ns': result['stages_ns'],
        'consumer_integration': 'Actual consume loop, shared cwd, explicit UUID resume, per-turn originals and three-turn envelope connected using local synthetic CLI/broker.',
        'offline_checks': {'source_methods': 16, 'consumer_loop_methods': 9, 'full_e2e_methods': 10,
                           'archive_targeted_methods': 2, 'one_archive_method_overlaps_e2e': True,
                           'root_readonly_checks': read(BATCH / 'ROOT_PREPARATION_CHECK.json')['checks']},
        'postrun_checks': {'lifecycle_checks': 4008, 'lifecycle_input_files': 1997,
                           'phase_methods': 7, 'root_phase_replay_passed': True,
                           'postclose_and_future_artifact_reads_in_candidate': 0},
        'preserved_preparation_failures': ['runtime/offline/attempt_01', 'consumer/offline/attempt_01',
                                          'consumer/offline/attempt_02', 'preparation_repair/attempt_01'],
        'phase_candidate_applied': False,
        'remaining': ['Apply a stage-correct capture reader or stage the wire audit at close, then freeze the next authorized C qualification.',
                      'C full three-turn engineering acceptance.', 'Actual model resume, memory and usage semantics.',
                      'Fair continuous model consumption and full task quality/time/cost benefit.'],
        'limits': ['Missing rich source fields remain unrecorded.', 'Synthetic usage is not measured provider usage.',
                   'Consumer coordinator timing starts after an owner is prepared, backend startup belongs to the outer full episode.',
                   'Preparation, audit and coordination total cost and model cash cost are unmeasured.',
                   'AL remains unbound at host_epoch 5.'],
        'next_action': 'Report to the authorized administrator and end this batch without another live attempt.',
    }
    save(BATCH / 'DELIVERY_READY.json', ready)
    records = []
    for file in sorted(BATCH.rglob('*'), key=lambda item: item.relative_to(BATCH).as_posix()):
        if not file.is_file() or file.name == 'DELIVERY_MANIFEST.json':
            continue
        assert '__pycache__' not in file.parts and file.suffix != '.pyc'
        raw = file.read_bytes()
        if file.suffix == '.json':
            json.loads(raw)
        if file.suffix == '.py':
            ast.parse(raw.decode('utf-8-sig'), filename=str(file))
        records.append({'path': file.relative_to(BATCH).as_posix(), 'bytes': len(raw), 'sha256': sha(raw)})
    save(BATCH / 'DELIVERY_MANIFEST.json', {'scope': 'All FIX1 material except this manifest itself',
         'preparation_commit': commit, 'file_count': len(records), 'total_bytes': sum(row['bytes'] for row in records), 'files': records})
    print(json.dumps({'files': len(records) + 1, 'manifest_sha256': sha((BATCH / 'DELIVERY_MANIFEST.json').read_bytes()),
                      'qualification_pass': False, 'C_actual_business': 1, 'not_run': 2}))


if __name__ == '__main__':
    main()

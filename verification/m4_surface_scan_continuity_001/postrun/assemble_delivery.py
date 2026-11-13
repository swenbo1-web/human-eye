"""Seal the completed engineering attempt and its offline diagnosis without replay."""

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


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf8', newline='\n')


def main():
    preparation = read(BATCH / 'PREPARATION.json')
    reserved = read(BATCH / 'ENGINEERING_STARTED.json')
    assert reserved['preparation_commit'] == '1c96846cbbf948b80860a5366f5442407e1cbabd'
    for record in preparation['files']:
        raw = (BATCH / record['path']).read_bytes()
        assert len(raw) == record['bytes'] and digest(raw) == record['sha256'], record['path']
    for path, expected in preparation['external_sha256'].items():
        assert digest(Path(path).read_bytes()) == expected, path
    prep_files = [record['path'] for record in preparation['files']] + ['PREPARATION.json']
    for relative in prep_files:
        git_path = (BATCH / relative).relative_to(ROOT).as_posix()
        assert subprocess.check_output(['git', 'show', reserved['preparation_commit'] + ':' + git_path], cwd=ROOT) == (BATCH / relative).read_bytes()
    run = read(BATCH / 'ENGINEERING_RESULT.json')
    assert len(run['episodes']) == run['started_episodes'] == run['planned_episodes'] == 2
    assert run['model_calls'] == run['API_calls'] == 0 and run['passed'] is False
    rows = []
    for group in ('N', 'C'):
        result = read(BATCH / 'episodes' / group / 'RESULTS.json')
        timing = read(BATCH / 'episodes' / group / 'FINAL_TIMING.json')
        assert timing['full_episode_wall_ns'] == timing['business_receipts_closed_ns'] - timing['started_ns']
        assert timing['within_590s'] is True
        assert result['cleanup']['confirmed'] is True and result['asset_unchanged'] is True
        assert result['model_calls'] == result['API_calls'] == 0
        for row in result['business']:
            assert row['thin']['confirmed'] is True and row['thin']['exit_code'] == 0
            assert row['thin']['bridge_cleanup']['confirmed'] is True
            assert len(row['status_after']['completed_turns']) == ('BASE', 'REPEAT', 'EDIT').index(row['turn']) + 1
        rows.append({'group': group, 'full_episode_wall_ns': timing['full_episode_wall_ns'],
                     'accepted_success': timing['accepted_success'], 'execution_counts': result['execution_counts'],
                     'stages_ns': result['stages_ns'], 'owned_cleanup_confirmed': True,
                     'thin_turns': [{'turn': row['turn'], 'wall_ns': row['thin']['wall_ns'],
                                     'pid': row['thin']['pid'], 'confirmed': row['thin']['confirmed'],
                                     'waiting_and_barrier_before_turn_ns': row['waiting_and_barrier_before_turn_ns']}
                                    for row in result['business']],
                     'errors': result['errors']})
    assert rows[0]['accepted_success'] is True and rows[1]['accepted_success'] is False
    assert rows[0]['execution_counts'] == {'planned': 3, 'attempted': 3, 'completed': 3, 'failed': 0, 'not_run': 0}
    assert rows[1]['execution_counts'] == {'planned': 3, 'attempted': 1, 'completed': 0, 'failed': 1, 'not_run': 2}
    lifecycle = read(HERE / 'lifecycle/RESULTS.json')
    review = read(HERE / 'qualification_review/REVIEW.json')
    assert lifecycle['status'] == 'pass_as_original_lifecycle_audit'
    assert lifecycle['original_engineering_qualification_passed'] is False
    assert review['status'] == 'offline_review_pass' and review['original_episode_pass'] is False
    assert review['candidate_installed_or_applied'] is False and review['new_live_calls_or_retries'] == 0
    assert review['C1_candidate_fact_report']['facts']['matches'] == 71
    assert review['C1_candidate_fact_report']['new_kernel_calls'] == 112
    assert len(review['negative_cases']) == 5
    for record in lifecycle['inputs'] + review['sources']:
        raw = (ROOT / record['path']).read_bytes()
        assert len(raw) == record['bytes'] and digest(raw) == record['sha256'], record['path']
    ready = {
        'callback': 'M4-SURFACE-SCAN-CONTINUITY-001_PREPARATION_READY',
        'delivery_scope': 'Attempt records and offline diagnosis ready for administrator review; engineering qualification did not pass.',
        'preparation_commit': reserved['preparation_commit'], 'admin_commit': preparation['admin_commit'],
        'preparation_sha256': digest((BATCH / 'PREPARATION.json').read_bytes()),
        'fixed_preparation_files_unchanged': len(prep_files),
        'fixed_external_inputs_unchanged': len(preparation['external_sha256']),
        'product_commit': preparation['product_commit'], 'product_source_sha256': preparation['product_source_sha256'],
        'scene_sha256': preparation['scene_sha256'], 'planned_episodes': 2, 'started_episodes': 2,
        'planned_business_calls': 6, 'actual_business_tool_calls': 4,
        'successful_tool_responses_and_thin_exits': 4,
        'frozen_qualification_counts': {'completed': 3, 'failed': 1, 'not_run': 2},
        'engineering_qualification_pass': False, 'new_model_or_inference_API_calls': 0,
        'episode_costs': rows,
        'cost_scope': 'Engineering fixture cost only. N reads markers and poses while C scans, so these are not a same-task model-benefit comparison.',
        'source_of_failure': 'The new runner passed the owner geometry snapshot to a verifier expecting the prior rich qualification snapshot; the offline fixtures omitted this actual interface case.',
        'raw_failure_unchanged': 'episodes/C/RESULTS.json and TURN_BASE.json retain the original rejection; C REPEAT and EDIT were not run.',
        'runtime_continuity_proven': {'N': 'three thin lifecycles, same owner/backend/namespace/object identities, registered EDIT visible',
                                      'C': 'first scan, actual thin boundary and cleanup only; repeat/edit continuity unmeasured'},
        'remaining_integration': 'Connect the persisted/resume CLI argv and parser to the existing consume loop, parameterizing output folder/shared workspace/thread/deadline and binding real archives to the three-turn envelope.',
        'unknowns': ['Actual model resume and memory continuity', 'Per-turn versus cumulative usage after resume',
                     'Discarded-stream usage coverage and provider-resolved input/version/effort',
                     'Same-task model benefit and fees', 'Complete preparation, audit and coordination cost',
                     'Full rich source fields absent from the owner snapshot'],
        'offline_checks': {'runtime': 16, 'CLI': 30, 'qualification': 10, 'runner': 3, 'are_business_samples': False},
        'postrun_checks': {'lifecycle': lifecycle['checks'], 'lifecycle_input_files': len(lifecycle['inputs']),
                           'C1_facts_rechecked_offline': 71, 'snapshot_negative_cases': 5,
                           'original_qualification_pass': False, 'raw_status_preserved': True},
        'preparation_failures_retained': 'PREPARATION_CHECK_HISTORY.json',
        'next_action': 'Send the authorized administrator callback and end this batch. A new live attempt requires a separately frozen authorization.',
    }
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
        files.append({'path': path.relative_to(BATCH).as_posix(), 'bytes': len(raw), 'sha256': digest(raw)})
    manifest = {'scope': 'All continuity material except this manifest itself',
                'preparation_commit': reserved['preparation_commit'], 'file_count': len(files),
                'total_bytes': sum(row['bytes'] for row in files), 'files': files}
    save(BATCH / 'DELIVERY_MANIFEST.json', manifest)
    print(json.dumps({'content_files': len(files), 'manifest_sha256': digest((BATCH / 'DELIVERY_MANIFEST.json').read_bytes()),
                      'qualification_pass': False, 'actual_business': 4, 'not_run': 2}))


if __name__ == '__main__':
    main()

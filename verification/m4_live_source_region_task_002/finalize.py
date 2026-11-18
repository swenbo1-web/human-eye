"""Check the frozen pair, retained failures and final manifest before Git publication."""

import json
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from common import ASSET, ASSET_SHA256, BASELINE, EXTERNAL, ROOT, read, save, sha


def main():
    started = time.perf_counter_ns()
    prefix = NS.relative_to(ROOT).as_posix() + '/'
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASELINE], cwd=ROOT).decode().splitlines()
    if any(not name.startswith(prefix) for name in changed) or sha(ASSET) != ASSET_SHA256:
        raise ValueError('fixed_product_or_asset_changed')
    freeze_path = NS / 'FROZEN.json'
    frozen = read(freeze_path)
    for row in frozen['direct_inputs']:
        path = Path(row['path'])
        if sha(path) != row['sha256'] or path.stat().st_size != row['bytes']:
            raise ValueError('frozen_identity_changed/' + str(path))
    archive = read(NS / 'RUNTIME_INDEX.json')
    if sha(archive['archive']['path']) != archive['archive']['sha256']:
        raise ValueError('runtime_archive_identity_changed')
    for row in archive['files']:
        if sha(EXTERNAL / row['path']) != row['sha256']:
            raise ValueError('runtime_original_changed/' + row['path'])
    evidence = read(NS / 'scoring/EVIDENCE_VERDICT.json')
    quality = read(NS / 'scoring/QUALITY.json')
    audit = read(NS / 'checks/RUNTIME_REVIEW.json')
    if audit['audit_errors'] or not all(audit['checks'].values()):
        raise ValueError('runtime_review_incomplete')
    if not evidence['same_device_pair_eligible'] or not audit['frame_comparison']['paired_same_device_consumer_SCENE_frames']:
        raise ValueError('exact_paired_SCENE_not_verified')
    results = []
    for slot in ('N1', 'P1'):
        folder = EXTERNAL / 'slots' / slot
        result = read(folder / 'SLOT_RESULT.json')
        pub = read(folder / 'SLOT_PUBLICATION.json')
        if (result['freeze_sha256'] != sha(freeze_path) or pub['published_ns'] >= result['owned_deadline_ns']
                or pub['result_sha256'] != sha(folder / 'SLOT_RESULT.json')
                or result['consumer_returned_ns'] >= result['task_deadline_ns']):
            raise ValueError('formal_slot_deadline_or_binding_mismatch/' + slot)
        consumer = result['consumer']
        owner = read(folder / 'owner/TOOLS.json')
        results.append({'slot': slot, 'published_runtime_status': result['status'],
            'content_quality': quality['slots'][slot]['counts'],
            'result_sha256': pub['result_sha256'], 'answer': result['answer'],
            'startup_to_answer_seconds': (consumer['final_received_ns'] - result['started_ns']) / 1e9,
            'complete_owned_seconds': (pub['published_ns'] - result['started_ns']) / 1e9,
            'tool_attempts': owner['attempts'], 'usage': consumer['raw_usage_events'],
            'text_UTF8_bytes': sum(row['content_metrics']['text_UTF8_bytes'] for row in owner['tools']),
            'PNG_bytes': consumer['public_image_bytes']})
    budget = read(EXTERNAL / 'slots/P1/SLOT_RESULT.json')['budget']['counts']
    if (budget['Blender_start_attempts'], budget['consumer_admissions'], budget['all_raster_actual']) != (2, 2, 2):
        raise ValueError('unexpected_registered_work_counts')
    first_p = read(EXTERNAL / 'slots/P1/owner/tool_01/PRODUCT_DETAIL.json')
    if (first_p['request_response_detail_present'] or first_p['forwarded_response_detail_present']
            or not first_p['default_brief_v2_returned']):
        raise ValueError('first_P_default_brief_not_verified')
    prepared = read(NS / 'PREPARED.json')
    save(NS / 'DECISION.json', {'task': 'M4-LIVE-SOURCE-REGION-TASK-002',
         'decision': 'same_SCENE_quality_and_P_default_brief_confirmed_native_archive_mismatch_retained',
         'pair_scope': {'same_device_frames_verified': True, 'both_original_answers_scored': True,
                        'both_original_runners_passed': False, 'performance_acceptance': 'unestablished'},
         'slots': results, 'P_first_default_brief': first_p,
         'complete_P_minus_N_seconds': results[1]['complete_owned_seconds'] - results[0]['complete_owned_seconds'],
         'raw_budget': budget, 'paid_API_calls': 0, 'product_or_default_deployment_changes': 0,
         'final_freeze_sha256': sha(freeze_path), 'quality_sha256': sha(NS / 'scoring/QUALITY.json'),
         'runtime_review_sha256': sha(NS / 'checks/RUNTIME_REVIEW.json'), 'originals_index_sha256': sha(NS / 'RUNTIME_INDEX.json'),
         'pre_admission_failure': read(NS / 'STARTUP_PREFLIGHT.json')['preserved_admission_failure'],
         'agent_learning_registration': prepared['agent_learning_registration'],
         'timing': {'preparation_to_final_freeze_s': (frozen['closed_ns'] - prepared['started_ns']) / 1e9,
                    'archive_s': (archive['closed_ns'] - archive['started_ns']) / 1e9,
                    'independent_runtime_audit_s': (audit['audit_finished_ns'] - audit['audit_started_ns']) / 1e9,
                    'closeout_started_ns': started, 'closeout_reviewed_ns': time.perf_counter_ns()},
         'next_observation': 'Validate a client-capped raw tool result using explicit truncation evidence, then compare an independently frozen N/P pair where native output stays compact.'})
    rows = sorted(path for path in NS.rglob('*') if path.is_file())
    if any(path.suffix == '.pyc' for path in rows):
        raise ValueError('generated_bytecode_not_a_deliverable')
    items = [{'path': path.relative_to(NS).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)} for path in rows]
    save(NS / 'CONTENT_MANIFEST.json', {'files': items, 'count': len(items), 'self_excluded': True})
    print(json.dumps({'verified_runtime_originals': archive['file_count'], 'committable_files': len(items) + 1,
                      'strict_statuses': [row['published_runtime_status'] for row in results]}))


if __name__ == '__main__':
    main()

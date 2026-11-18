"""Verify scope and publish the batch decision and Git content manifest."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from common import ASSET, ASSET_SHA256, BASELINE, EXTERNAL, ROOT, read, save, sha


def rows():
    return sorted(path for path in NS.rglob('*') if path.is_file())


def main():
    began = time.perf_counter_ns()
    prefix = NS.relative_to(ROOT).as_posix() + '/'
    changes = subprocess.check_output(['git', 'diff', '--name-only', BASELINE], cwd=ROOT).decode().splitlines()
    if any(not name.startswith(prefix) for name in changes):
        raise ValueError('fixed_product_changed')
    if any(path.suffix == '.pyc' for path in rows()) or sha(ASSET) != ASSET_SHA256:
        raise ValueError('unexpected_generated_file_or_asset_change')
    original = read(NS / 'FROZEN.json')
    revised = read(NS / 'FROZEN_R1.json')
    changed = []
    for item in revised['direct_inputs']:
        path = Path(item['path'])
        if sha(path) != item['sha256'] or path.stat().st_size != item['bytes']:
            raise ValueError('P1_frozen_input_changed/' + str(path))
    for item in original['direct_inputs']:
        path = Path(item['path'])
        if sha(path) != item['sha256']:
            relative = path.relative_to(ROOT).as_posix()
            blob = subprocess.check_output(['git', 'show', '978819d4eb3aa8c9631d532d033ee174204190ea:' + relative], cwd=ROOT)
            if hashlib.sha256(blob).hexdigest() != item['sha256']:
                raise ValueError('N1_original_frozen_input_unrecoverable/' + relative)
            changed.append(relative)
    archive = read(NS / 'RUNTIME_INDEX.json')
    assert sha(archive['archive']['path']) == archive['archive']['sha256']
    for row in archive['files']:
        if sha(EXTERNAL / row['path']) != row['sha256']:
            raise ValueError('original_runtime_changed/' + row['path'])
    cases = []
    for label in ('N1', 'P1'):
        folder = EXTERNAL / 'slots' / label
        result = read(folder / 'SLOT_RESULT.json')
        pub = read(folder / 'SLOT_PUBLICATION.json')
        if sha(folder / 'SLOT_RESULT.json') != pub['result_sha256'] or pub['published_ns'] >= result['owned_deadline_ns']:
            raise ValueError('original_slot_publication_binding_or_deadline')
        consumer = result.get('consumer', {})
        if consumer and (consumer['final_received_ns'] >= result['task_deadline_ns'] or
                        result['consumer_returned_ns'] >= result['task_deadline_ns']):
            raise ValueError('original_consumer_deadline')
        cases.append({'slot': label, 'status': result['status'], 'model_started': bool(consumer),
             'startup_to_answer_seconds': (consumer['final_received_ns'] - result['started_ns']) / 1e9 if consumer else None,
             'complete_seconds': (pub['published_ns'] - result['started_ns']) / 1e9,
             'usage': consumer.get('raw_usage_events'), 'result_sha256': pub['result_sha256']})
    phases = read(NS / 'PREPARED.json')
    quality = read(NS / 'scoring/QUALITY.json')
    evidence = read(NS / 'scoring/EVIDENCE_VERDICT.json')
    budget = read(EXTERNAL / 'slots/P1/SLOT_RESULT.json')['budget']['counts']
    assert (budget['Blender_start_attempts'], budget['consumer_admissions'], budget['all_raster_actual']) == (2, 1, 1)
    assert [(value['slot'], value['status']) for value in cases] == [('N1', 'failed'), ('P1', 'completed')]
    assert not evidence['same_device_pair_eligible'] and not evidence['slots']['P1']['errors']
    runtime_review = NS / 'checks/RUNTIME_REVIEW.json'
    save(NS / 'DECISION.json', {'task': 'M4-LIVE-SOURCE-REGION-TASK-001',
         'decision': 'live_P1_quality_passed_NP_comparison_ineligible', 'slots': cases,
         'model_consumers': 1, 'owned_Blender_starts': 2, 'replacement_consumers': 0,
         'product_or_default_deployment_changes': 0, 'paid_API_calls': 0,
         'P1_assessment': '10/10; initial explicit full then brief/geometry supplement', 'N1_assessment': '10 unrun; dependency path omitted',
         'quality': quality['total'], 'quality_sha256': sha(NS / 'scoring/QUALITY.json'),
         'runtime_review_sha256': sha(runtime_review), 'originals_index_sha256': sha(NS / 'RUNTIME_INDEX.json'),
         'fixed_plan': phases['plan_sha256'], 'agent_learning_registration': phases['agent_learning_registration'],
         'initial_freeze_pins': len(original['direct_inputs']), 'P1_freeze_pins': len(revised['direct_inputs']),
         'N1_revision_paths_rechecked_at_original_Git': changed,
         'timing': {'preparation_window_from_first_receipt_to_first_freeze_s': (original['closed_ns'] - phases['started_ns']) / 1e9,
                    'P1_dependency_recovery_recheck_seconds': (revised['closed_ns'] - revised['started_ns']) / 1e9,
                    'archive_seconds': (archive['closed_ns'] - archive['started_ns']) / 1e9,
                    'final_audit_started_ns': began, 'final_audit_written_ns': time.perf_counter_ns(),
                    'scope': 'Phase receipts overlap per-slot totals. Engineering time before the first preparation receipt and fees are unmeasured.'},
         'next_observation': 'Re-run a fresh authorized live pair after existing dependencies are verified offline. Register the first P request as brief and measure full windows only when both answers meet the quality gates.'})
    items = [{'path': path.relative_to(NS).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)} for path in rows()]
    save(NS / 'CONTENT_MANIFEST.json', {'files': items, 'count': len(items), 'self_excluded': True})
    print(json.dumps({'verified_runtime_originals': archive['file_count'], 'committable_files': len(items) + 1}))


if __name__ == '__main__':
    main()

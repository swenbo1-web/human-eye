"""Bind the unchanged experiment inputs, original outcomes and repository contents."""

import hashlib
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
        raise ValueError('fixed_product_or_original_asset_changed')
    freeze = NS / 'FROZEN.json'
    frozen = read(freeze)
    closeout_script_initial_commit = '1c7d8749c92134ef497ec6db752ecff8e528abd3'
    archived_closeout_inputs = []
    for row in frozen['direct_inputs']:
        path = Path(row['path'])
        if sha(path) != row['sha256'] or path.stat().st_size != row['bytes']:
            if path != Path(__file__).resolve():
                raise ValueError('frozen_input_changed/' + str(path))
            relative = path.relative_to(ROOT).as_posix()
            prior = subprocess.check_output(['git', 'show', closeout_script_initial_commit + ':' + relative], cwd=ROOT)
            if len(prior) != row['bytes'] or hashlib.sha256(prior).hexdigest() != row['sha256']:
                raise ValueError('frozen_closeout_script_missing_from_original_commit')
            archived_closeout_inputs.append({'path': relative, 'original_commit': closeout_script_initial_commit,
                 'original_sha256': row['sha256'], 'current_sha256': sha(path),
                 'scope': 'Postrun report finalizer only. Never imported by formal slots or preflights.'})
    archive = read(NS / 'RUNTIME_INDEX.json')
    if sha(archive['archive']['path']) != archive['archive']['sha256']:
        raise ValueError('local_archive_changed')
    for entry in archive['files']:
        if sha(EXTERNAL / entry['path']) != entry['sha256']:
            raise ValueError('local_original_changed/' + entry['path'])

    quality = read(NS / 'scoring/QUALITY.json')
    audit_path = NS / 'checks/RUNTIME_REVIEW.json'
    audit = read(audit_path)
    controls = read(NS / 'checks/PROJECTION_CONTROLS.json')
    outcomes = []
    for slot in ('P1', 'N1'):
        folder = EXTERNAL / 'slots' / slot
        result_file = folder / 'SLOT_RESULT.json'
        result = read(result_file)
        pub = read(folder / 'SLOT_PUBLICATION.json')
        if result['freeze_sha256'] != sha(freeze) or pub['result_sha256'] != sha(result_file):
            raise ValueError('slot_publication_identity_changed/' + slot)
        consumer = result.get('consumer') or {}
        answer_ns = consumer.get('final_received_ns')
        began = result['started_ns']
        owner = read(folder / 'owner/TOOLS.json') if (folder / 'owner/TOOLS.json').is_file() else {'tools': [], 'attempts': 0}
        outcomes.append({'slot': slot, 'runtime_status': result['status'],
            'quality': quality['slots'][slot]['counts'], 'result_sha256': pub['result_sha256'],
            'answer': result.get('answer'), 'within_owned_deadline': pub['published_ns'] < result['owned_deadline_ns'],
            'answer_within_task_deadline': None if answer_ns is None else answer_ns < result['task_deadline_ns'],
            'startup_to_answer_s': (answer_ns - began) / 1e9 if answer_ns is not None else None,
            'owned_through_publication_s': (pub['published_ns'] - began) / 1e9,
            'tool_attempts': owner['attempts'], 'original_usage': consumer.get('raw_usage_events'),
            'tool_text_UTF8_bytes': sum(row.get('content_metrics', {}).get('text_UTF8_bytes', 0) for row in owner['tools']),
            'CLI_PNG_bytes': consumer.get('public_image_bytes')})
    save(NS / 'DECISION.json', {'task': 'M4-LIVE-SOURCE-REGION-TASK-003', 'outcomes': outcomes,
         'one_pair_only': True, 'case_denominator': 2, 'replacement_consumers': 0,
         'same_device_first_frame_verified': audit['frame_comparison']['paired_same_device_consumer_SCENE_frames'],
         'runtime_conditions_for_compact_pair': audit['runtime_conditions_for_compact_pair'],
         'compact_native_performance_pair_established': False, 'same_prompt_sampling_closed': True,
         'offline_projection_checks_passed': sum(case['passed'] for case in controls['cases']),
         'repeated_evidence_sha256': sha(NS / 'checks/REPEATED_EVIDENCE.json'),
         'archived_frozen_closeout_inputs': archived_closeout_inputs,
         'runtime_review_sha256': sha(audit_path), 'quality_sha256': sha(NS / 'scoring/QUALITY.json'),
         'final_freeze_sha256': sha(freeze), 'local_original_index_sha256': sha(NS / 'RUNTIME_INDEX.json'),
         'deferred_AL_registration': read(NS / 'PREPARED.json')['agent_learning_registration'],
         'paid_API_calls': 0, 'product_or_default_deployment_changes': 0,
         'timing': {'final_check_started_ns': started, 'final_check_closed_ns': time.perf_counter_ns(),
                    'preparation_to_freeze_s': (frozen['closed_ns'] - read(NS / 'PREPARED.json')['started_ns']) / 1e9,
                    'archive_s': (archive['closed_ns'] - archive['started_ns']) / 1e9}})
    paths = sorted(path for path in NS.rglob('*') if path.is_file())
    if any(path.suffix == '.pyc' for path in paths):
        raise ValueError('generated_bytecode_in_namespace')
    files = [{'path': path.relative_to(NS).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)} for path in paths]
    save(NS / 'CONTENT_MANIFEST.json', {'files': files, 'count': len(files), 'self_excluded': True})
    print(json.dumps({'original_runtime_files': archive['file_count'], 'Git_manifest_files': len(files) + 1}))


if __name__ == '__main__':
    main()

"""Verify fixed inputs and publish the original assembly experiment identities."""

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
    path_prefix = NS.relative_to(ROOT).as_posix() + '/'
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASELINE], cwd=ROOT).decode().splitlines()
    if any(not name.startswith(path_prefix) for name in changed) or sha(ASSET) != ASSET_SHA256:
        raise ValueError('product_or_original_assembly_changed')
    frozen = NS / 'FROZEN.json'
    for row in read(frozen)['direct_inputs']:
        path = Path(row['path'])
        if sha(path) != row['sha256'] or path.stat().st_size != row['bytes']:
            raise ValueError('frozen_input_changed/' + str(path))
    archive = read(NS / 'RUNTIME_INDEX.json')
    if sha(archive['archive']['path']) != archive['archive']['sha256']:
        raise ValueError('local_archive_changed')
    for row in archive['files']:
        if sha(EXTERNAL / row['path']) != row['sha256']:
            raise ValueError('local_original_changed/' + row['path'])
    review = NS / 'checks/RUNTIME_REVIEW.json'
    quality = NS / 'scoring/QUALITY.json'
    scores = read(quality)
    runtime = read(review)
    fixture_pass = EXTERNAL / 'preflight/installed_task_02/PREFLIGHT.json'
    receipt_paths = [quality, review, NS / 'scoring/EVIDENCE_VERDICT.json',
        NS / 'checks/PHASE_COSTS.json', NS / 'checks/EVIDENCE_INCREMENT.json', fixture_pass]
    outcome = {'task': 'M4-LIVE-ASSEMBLY-RELATION-TASK-001', 'original_denominator': 2,
               'candidate_product_sha256': read(NS / 'PRODUCT_RUN_BINDING.json')['source_sha256'],
               'freeze_sha256': sha(frozen), 'answer_seal_sha256': sha(NS / 'ANSWERS_SEALED.json'),
               'runtime_review_sha256': sha(review), 'quality_sha256': sha(quality),
               'runtime_original_index_sha256': sha(NS / 'RUNTIME_INDEX.json'),
               'quality_summary': {key: {field: value[field] for field in ('passes', 'denominator', 'unresolved')}
                                   for key, value in scores['slots'].items()},
               'same_initial_geometry': scores['pair_eligible_for_same_initial_geometry_comparison'],
               'receipts_sha256': {str(path): sha(path) for path in receipt_paths},
               'slots': [{k: row.get(k) for k in ('slot', 'status', 'startup_to_answer_s', 'full_window_s')}
                         for row in runtime['slots']],
               'cash_fees': None, 'scope': 'One serial comparison on one closed-solid synthetic assembly.',
               'no_replacement_consumers': True, 'product_or_deployment_changes': 0,
               'agent_learning_registration': read(NS / 'PREPARED.json')['agent_learning_registration'],
               'final_check_started_ns': started, 'final_check_completed_ns': time.perf_counter_ns()}
    save(NS / 'DECISION.json', outcome)
    manifest = NS / 'CONTENT_MANIFEST.json'
    paths = sorted(path for path in NS.rglob('*') if path.is_file() and path != manifest)
    if any(path.suffix == '.pyc' for path in paths):
        raise ValueError('unexpected_generated_bytecode')
    files = [{'path': path.relative_to(NS).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)} for path in paths]
    save(manifest, {'files': files, 'count': len(files), 'self_excluded': True})
    print(json.dumps({'runtime_originals': archive['file_count'], 'Git_files': len(files) + 1}))


if __name__ == '__main__':
    main()

"""Register the fixed zero-consumer recovery scope and direct input pins."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = ROOT / 'verification/m5_task_consumption_001'
BASELINE = 'baf8799d9e1cb411d39da58c28171b00ac76f12f'
PLAN_SHA = '4e37508e0fa047c13b832bd2f9c6b03442d0493f062da1fbe00d3f83bb627ee2'


def pin(path):
    path = Path(path).resolve()
    blob = path.read_bytes()
    return {'path': str(path), 'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()}


def main():
    started = time.perf_counter_ns()
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() != BASELINE:
        raise ValueError('accepted_baseline')
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT):
        raise ValueError('clean_tracked_baseline')
    reference = HERE / 'reference'
    reference.mkdir(exist_ok=True)
    original_plan = Path('D:/hefe/docs/M5_HARNESS_RECOVERY_001_PLAN.md')
    if pin(original_plan)['sha256'] != PLAN_SHA:
        raise ValueError('administrator_plan_identity')
    references = []
    for source in (original_plan, Path('D:/hefe/docs/M5_TASK_CONSUMPTION_001_INDEPENDENT_REVIEW.md')):
        target = reference / source.name
        if target.exists():
            raise ValueError('reference_write_once')
        shutil.copyfile(source, target)
        references.append({'original': pin(source), 'copy': pin(target)})
    for group in ('A', 'B'):
        shutil.copyfile(PRIOR / (group + '_RUN_BINDING.json'), HERE / (group + '_RUN_BINDING.json'))
    candidate = PRIOR / 'recovery_candidate/owned_runtime.py'
    if pin(candidate)['sha256'] != '371049158c7370a0e29e30992e5b1fe2cd6d6ba726688e77017ca44c27f94318':
        raise ValueError('reviewed_candidate_identity')
    protected = [pin(PRIOR / name) for name in ('CONTENT_MANIFEST.json', 'FINAL_AUDIT.json', 'FROZEN.json')]
    protected.extend(pin(PRIOR / name) for name in ('CANDIDATE_INDEPENDENT_REVIEW.json', 'recovery_candidate/CANDIDATE.json'))
    asset = Path('D:/he_m4_target_002/assets_01/main.blend')
    if pin(asset)['sha256'] != '2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164':
        raise ValueError('unchanged_asset')
    result = {'schema': 'm5-harness-recovery-baseline-v1', 'task': 'M5-HARNESS-RECOVERY-001',
              'baseline_git': BASELINE, 'started_ns': started, 'worktree': str(ROOT),
              'runtime_root': 'D:/he_m5_harness_recovery_001', 'references': references,
              'candidate': pin(candidate), 'protected_direct_seals': protected, 'asset': pin(asset),
              'A_binding': pin(HERE / 'A_RUN_BINDING.json'), 'B_binding': pin(HERE / 'B_RUN_BINDING.json'),
              'limits': {'owned_starts': 2, 'raster_attempts': 12, 'consumer_models': 0,
                         'paid_API_calls': 0, 'owned_seconds': 600, 'product_request_seconds': 30},
              'sequence': ['A_recovery', 'B_recovery'],
              'internal_request_sequence': ['observation', 'invalid_target_candidates_surface_only',
                                            'objects_surface_only', 'objects_surface_and_closed_solid',
                                            'A_observation_or_B_joint'],
              'expected_archive_indices': [1, None, 2, 3, 4],
              'product_changes_allowed': False,
              'AL': {'context_bound': False, 'rebind_required': True, 'host_epoch': 5,
                     'project_id': '58f409affce4d8852be3dc41',
                     'registration': 'pending_current_chat_host_binding', 'writes': 0},
              'clock_scope': 'First root registration onward. Prior plan reading and delegation not timed.',
              'paused': ['Google', 'API', 'key'],
              'acceptance': 'Verify the recovery harness only. Product/model benefit remains outside this batch.'}
    with (HERE / 'BASELINE.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'registered': True, 'direct_old_seals': len(protected), 'model_consumers': 0}))


if __name__ == '__main__':
    main()

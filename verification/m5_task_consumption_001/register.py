"""Record the administrator's fixed M5 consumer scope before live work."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREVIOUS = ROOT / 'verification/m5_observe_measure_001'
BASELINE_GIT = '14c8c6b8206dcaecc373bc9aa895cda1d622eee3'
PLAN_SHA = '45c2e7062c9e3fe6fb009431b28624ef3f41c91c8cb31263e391a900ded272d6'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    started = time.perf_counter_ns()
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() != BASELINE_GIT:
        raise ValueError('accepted_clean_start_commit')
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT):
        raise ValueError('tracked_start_must_be_clean')
    prior = json.loads((PREVIOUS / 'BASELINE.json').read_bytes())
    protected = dict(prior['protected_old_pins'])
    for name in ('CONTENT_MANIFEST.json', 'FINAL_AUDIT.json', 'FORMAL_FROZEN.json'):
        path = PREVIOUS / name
        protected[str(path)] = sha(path)
    for name, digest in protected.items():
        if sha(name) != digest:
            raise ValueError('protected_input_changed/' + name)
    reference = HERE / 'reference'
    reference.mkdir(exist_ok=True)
    sources = [Path('D:/hefe/docs/M5_OBSERVE_MEASURE_001_INDEPENDENT_REVIEW.md'),
               Path('D:/hefe/docs/M5_TASK_CONSUMPTION_001_PLAN.md'),
               Path('D:/hefe/verification/fixes/20261115_m4_selective_002_plan/FROZEN_GEOMETRY.json')]
    if sha(sources[1]) != PLAN_SHA:
        raise ValueError('administrator_plan_identity')
    references = {}
    for source in sources:
        destination = reference / source.name
        if destination.exists():
            raise ValueError('reference_is_write_once/' + str(destination))
        shutil.copyfile(source, destination)
        references[str(source)] = sha(source)
    asset = Path(prior['asset']['path'])
    if sha(asset) != prior['asset']['sha256']:
        raise ValueError('unchanged_frozen_asset')
    bindings = {'A': PREVIOUS / 'A_RUN_BINDING.json',
                'B': PREVIOUS / 'build_final/RUN_BINDING.json'}
    for group, source in bindings.items():
        shutil.copyfile(source, HERE / (group + '_RUN_BINDING.json'))
    result = {
        'schema': 'm5-task-consumption-baseline-v1',
        'task': 'M5-TASK-CONSUMPTION-001', 'baseline_git': BASELINE_GIT,
        'branch': subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip(),
        'worktree': str(ROOT), 'runtime_root': 'D:/he_m5_task_consume_001',
        'started_ns': started,
        'clock_scope': 'First root registration through final saved-only seal. Prior plan reading and delegation interval unmeasured.',
        'production_changes_allowed': False,
        'asset': prior['asset'], 'references': references,
        'protected_old_pins': protected,
        'bindings_sha256': {group: sha(HERE / (group + '_RUN_BINDING.json')) for group in bindings},
        'formal_order': ['A1', 'B1', 'B2', 'A2', 'A3', 'B3'],
        'limits': {'owned_starts': 8, 'qualification_rasters': 12, 'formal_rasters': 36,
                   'total_rasters': 48, 'consumers': 6, 'task_seconds': 450,
                   'owned_seconds': 600, 'business_tools_per_slot': 12,
                   'rasters_per_slot': 6, 'product_request_seconds': 30,
                   'paid_APIs': 0},
        'AL': {'context_bound': False, 'host_epoch': 5, 'rebind_required': True,
               'project_id': '58f409affce4d8852be3dc41',
               'registration': 'pending_current_chat_host_binding', 'writes': 0},
        'paused': ['Google', 'API', 'key'],
    }
    with (HERE / 'BASELINE.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'registered': True, 'protected_pins': len(protected),
                      'baseline_sha256': sha(HERE / 'BASELINE.json')}))


if __name__ == '__main__':
    main()

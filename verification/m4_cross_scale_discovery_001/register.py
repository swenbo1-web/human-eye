"""Register the bounded cross-scale capability and its direct accepted inputs."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.with_name('m4_global_local_qualification_001')
BASELINE = '99f939513111637b76a1d486622b4841cad9ccda'
PLAN_SHA = 'f2e13678ff210dd59db9ca565084c55198eb0eec64ab4c0af754617b97d9df1f'


def pin(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False, indent=2)
        stream.write('\n')


def main():
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() != BASELINE:
        raise ValueError('accepted_baseline_changed')
    (HERE / 'reference').mkdir(exist_ok=True)
    references = []
    for path in (Path('D:/hefe/docs/M4_CROSS_SCALE_DISCOVERY_001_PLAN.md'),
                 Path('D:/hefe/docs/M4_GLOBAL_LOCAL_QUALIFICATION_001_INDEPENDENT_REVIEW.md')):
        if path.name.endswith('PLAN.md') and pin(path)['sha256'] != PLAN_SHA:
            raise ValueError('administrator_plan_changed')
        copy = HERE / 'reference' / path.name
        shutil.copyfile(path, copy)
        references.append(dict(original=pin(path), copy=pin(copy)))
    save(HERE / 'BASELINE.json', dict(schema='m4-cross-scale-baseline-v1', started_ns=time.perf_counter_ns(),
        task='M4-CROSS-SCALE-DISCOVERY-001', baseline_git=BASELINE, references=references,
        qualification_asset=pin('D:/he_m4_global_local_001/fixture/main.blend'),
        qualification_geometry=pin(PRIOR / 'fixture/GEOMETRY.json'),
        old_direct_seals=[pin(PRIOR / name) for name in ('CONTENT_MANIFEST.json', 'FINAL_AUDIT.json', 'FROZEN.json', 'DECISION.json')],
        runtime_root='D:/he_m4_cross_scale_001',
        limits=dict(owned_starts=8, actual_rasters=64, model_consumers=0, paid_API_calls=0, owned_seconds=600, request_seconds=30),
        slot_order=['qualification_R0', 'pair_1_R0', 'pair_1_R1', 'pair_2_R1', 'pair_2_R0', 'pair_3_R0', 'pair_3_R1', 'state'],
        performance_gate=dict(service_paired_median_reduction_at_least=.20, owned_faster_pairs_at_least=2, owned_median_improves=True),
        AL=dict(context_bound=False, host_epoch=5, registration='pending_current_chat_host_binding', writes=0),
        interruption=dict(source_edits_preceded_registration=['live_service.py','live_spatial_mcp.py','query_policy.py'],
                          earlier_live_operations=0, earlier_task_delegation_recorded_in_chat=True),
        paused=['Google','API','key'], timing_scope='Root registration onward, preceding interrupted design and delegation excluded.'))
    print(json.dumps(dict(registered=True, actual_starts=0)))


if __name__ == '__main__':
    main()

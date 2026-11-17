"""Register the bounded source-region task and its direct accepted evidence."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PRIOR=HERE.with_name('m4_cross_scale_discovery_001')
PLAN=Path('D:/hefe/docs/M4_M5_SOURCE_REGION_001_PLAN.md')


def pin(path):
    path=Path(path).resolve()
    raw=path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def main():
    baseline='3c26b43d197e6de252f65db69c061733e5a7216e'
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=baseline:
        raise ValueError('accepted_baseline')
    if pin(PLAN)['sha256']!='0f533309340f84531b62c6a738bdb7b543bd3f3b0a18ef82a11501d3906b8e91':
        raise ValueError('administrator_plan_changed')
    (HERE/'reference').mkdir(exist_ok=True)
    references=[]
    for source in (PLAN,Path('D:/hefe/docs/M4_CROSS_SCALE_DISCOVERY_001_INDEPENDENT_REVIEW.md'),
        Path('D:/hefe/verification/fixes/20261117_m4_cross_scale_review/geometry/NEXT_REGION_PREFLIGHT.json'),
        Path('D:/hefe/verification/fixes/20261117_m4_cross_scale_review/geometry/next_region_preflight.py')):
        target=HERE/'reference'/source.name
        shutil.copyfile(source,target)
        references.append(dict(original=pin(source),copy=pin(target)))
    result=dict(schema='source-region-baseline-v1',task='M4-M5-SOURCE-REGION-001',baseline_git=baseline,
        started_ns=time.perf_counter_ns(),references=references,runtime_root='D:/he_m4_m5_source_region_001',
        old_direct_seals=[pin(PRIOR/name) for name in ('CONTENT_MANIFEST.json','FINAL_AUDIT.json','SOURCE_FREEZE_R1.json','DECISION.json')],
        accepted_install=pin(PRIOR/'R1_RUN_BINDING.json'),
        limits=dict(qualification_owned_starts=8,qualification_actual_rasters=24,asset_preparation_processes=1,
                    model_consumers=0,paid_API_calls=0,request_seconds=30,owned_seconds=600),
        slot_order=['qualification_R0','pair1_R0','pair1_R1','pair2_R1','pair2_R0','pair3_R0','pair3_R1','state'],
        performance_gate=dict(quality_equal=True,repeated_work_declines=True,business_faster_pairs_at_least=2,paired_business_median_improves=True),
        AL=dict(context_bound=False,host_epoch=5,registration='pending_current_chat_host_binding',writes=0),
        paused=['Google','key'],clock_scope='Registration onward, initial plan reading excluded.')
    with (HERE/'BASELINE.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,sort_keys=True,ensure_ascii=False,indent=2)
        stream.write('\n')
    print(json.dumps(dict(registered=True,new_live=0)))


if __name__=='__main__':
    main()

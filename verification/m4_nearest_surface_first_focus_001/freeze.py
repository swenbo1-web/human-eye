"""Freeze the fixed two-slot Blender run after both independent preflights."""
import argparse
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import formal

BATCH=formal.BATCH
need,pin,read,confirm=formal.need,formal.pin,formal.read,formal.confirm


def freeze(root):
    phase=formal.phase1(root)
    prep=root/'preflight'
    need(root.name==BATCH and not (root/'FORMAL_START.json').exists() and not (root/'slots').exists(),
         'attempt_already_registered')
    plan_path=prep/'FORMAL_PLAN.json'
    plan=formal.frozen(root)
    cold_path=prep/'FORMAL_COLD.json'
    cold=read(cold_path)
    need(cold['passed'] is True and cold['actual_Blender']==0 and cold['plan']==pin(plan_path)
         and all(slot['exit']==0 and slot['passed'] is True for slot in cold['slots']),
         'formal_cold_path_not_qualified')
    ctl_path=prep/'CANDIDATE_CONTROLS.json'
    ctl=read(ctl_path)
    need(ctl['passed'] is True,'nearest_surface_controls_failed')
    previous=root.parent/'M4-REFERENCE-ONLY-INTENT-HOLDOUT-001/preflight/FROZEN_EXECUTION.json'
    fixture=read(previous)['fixture']
    selected={k:pin(confirm(fixture[k])) for k in ('blend','source','truth')}
    need(selected['blend']==plan['fixture'],'unexpected_formal_fixture')
    custody=read(prep/'INSTALL_CUSTODY.json')
    inputs=[pin(prep/'ADMIN_PLAN.md'),pin(prep/'INSTALL_CUSTODY.json'),pin(ctl_path),pin(previous)]
    inputs.extend(pin(x) for x in sorted(HERE.glob('*.py')))
    inputs.extend(pin(x) for x in (
        HERE.parent/'m4_reference_only_intent_holdout_001/audit.py',
        HERE.parent/'m4_task_region_focus_feedback_001/score.py',
        HERE.parent/'m4_directed_focus_assembly_holdout_001/score.py'))
    record={'batch':BATCH,'phase1':phase,'formal_plan':pin(plan_path),'formal_cold':pin(cold_path),
            'candidate_controls':pin(ctl_path),'fixture':selected,'order':['A','B'],
            'candidate_commit':custody['candidate_commit'],'candidate_runtime_sha256':custody['source_sha256'],
            'candidate_wheel_sha256':custody['wheel']['sha256'],'limits':plan['limits'],
            'criteria':{'pixels_minimum':16,'candidate_primary':2,'candidate_first_raster':2,
                        'candidate_delivery':2,'allowed_actual_M3_searches_per_candidate_call':1},
            'inputs':inputs}
    path=prep/'FROZEN_EXECUTION.json'
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(record,stream,indent=2,ensure_ascii=False)
        stream.write('\n')
    print(json.dumps(pin(path),ensure_ascii=False))


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('root',type=lambda value:Path(value).resolve(strict=True))
    freeze(cli.parse_args().root)


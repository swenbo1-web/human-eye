"""Freeze all immutable inputs and limits before any formal Blender or consumer."""
import argparse
import json
from pathlib import Path
import subprocess
from hashlib import sha256

HERE=Path(__file__).resolve().parent
BATCH='M4-REFERENCE-ONLY-INTENT-HOLDOUT-001'
ADMIN='28668b2018d7abc17bfcdc056797f5589c34f7afc8c571f6d2012b5a77cb0f6a'
CUSTODY='004211486086650514d2c586cbf617bea3bd5a017fd2ede8384c81a420768e11'
PRODUCT='b7fe4bb0dc2ce277ff5dd7a6198365253b716c09'
ASSET='7a4e854b119f713fb2a2088035980df7472569fc47cdd109efdaf9fed2452159'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path=Path(path).resolve(strict=True)
    raw=path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=sha256(raw).hexdigest())


def freeze(root):
    p=root/'preflight'
    asset=p/'fixture'
    admin=pin(p/'ADMIN_PLAN.md')
    require(root.name==BATCH and admin['sha256']==ADMIN, 'wrong_fixed_admin_plan')
    formal=(root/'FORMAL_START.json',root/'NATURAL_START.json',root/'slots/DIAGNOSTIC',
            root/'slots/NATURAL_K',root/'slots/NATURAL_T')
    require(not any(path.exists() for path in formal),'formal_already_started')
    custody=pin(root.parent/'M4-TASK-REGION-FOCUS-FEEDBACK-001/preflight/CANDIDATE_INSTALL_CUSTODY.json')
    require(custody['sha256']==CUSTODY,'existing_install_custody_changed')
    product=read(custody['path'])
    require(product['candidate_commit']==PRODUCT and product['runtime_sources']==146,'wrong_installed_product')
    blend, source, truth=(pin(asset/name) for name in ('main.blend','EVALUATED_SOURCE.json','TARGET_TRUTH.json'))
    adjudication=read(truth['path'])
    require(blend['sha256']==ASSET==adjudication['asset_sha256']
            and source['sha256']==adjudication['evaluated_source_sha256']
            and set(adjudication['cases'])=={'K','T'}
            and adjudication['cases']['K']['nearest_source_triangle_indices']==[0,1]
            and adjudication['cases']['T']['nearest_source_triangle_indices']==[2,3], 'closed_evaluated_truth_changed')
    prompts={key:pin(asset/f'PROMPT_{key}.txt') for key in ('K','T')}
    k,t=(Path(prompts[key]['path']).read_bytes() for key in ('K','T'))
    require(k.count(b'Fixture K')==t.count(b'Fixture T')==1 and k.replace(b'Fixture K',b'Fixture T')==t,
            'natural_prompts_differ_beyond_reference')
    records={}
    for kind in ('diagnostic','natural'):
        for phase in ('plan','cold'):
            records[f'{kind}_{phase}']=pin(p/f'{kind.upper()}_{phase.upper()}.json')
        checked=read(records[f'{kind}_cold']['path'])
        require(checked.get('passed') is True,'preflight_not_passed/'+kind)
    inputs=[admin,custody,pin(asset/'ASSET_PREPARATION.json')]
    inputs.extend(pin(path) for path in sorted(HERE.glob('*.py')))
    inputs.extend(pin(path) for path in sorted(HERE.glob('*.md')))
    inputs += [pin(HERE.parent/'m4_task_region_focus_feedback_001/score.py'),
               pin(HERE.parent/'m4_directed_focus_assembly_holdout_001/score.py')]
    record={'batch':BATCH,'fixture':{'blend':blend,'source':source,'truth':truth,'prompts':prompts},
            'product':{'commit':PRODUCT,'runtime_sha256':product['source_sha256'],
                       'wheel_sha256':product['wheel']['sha256'],'runtime_files':product['runtime_sources']},
            'limits':{'diagnostic_blender':1,'diagnostic_requests':2,'diagnostic_rasters_per_request':2,
                      'natural_blender':2,'natural_consumers':2,'natural_requests_per_case':8,
                      'natural_rasters_per_case':4,'replacement_slots':0},
            'order':['DIAGNOSTIC','NATURAL_K','NATURAL_T'], 'inputs':inputs, **records}
    with (p/'FROZEN_EXECUTION.json').open('x',encoding='utf8',newline='\n') as output:
        json.dump(record,output,ensure_ascii=False,indent=2)
        output.write('\n')
    print(json.dumps(pin(p/'FROZEN_EXECUTION.json'),ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=lambda value:Path(value).resolve(strict=True))
    freeze(parser.parse_args().root)


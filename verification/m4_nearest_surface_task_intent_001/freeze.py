"""Freeze paired intent prompts and their common installed runtime before formal start."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
BATCH='M4-NEAREST-SURFACE-TASK-INTENT-001'
ADMIN='d20126432117c340282ea9dc11b6964d7147c890cfa1d5f775b2bef8116d40eb'
PRODUCT='2f7f492d7d0fd1af2ff956228d31bd57b5e31ddc'
RUNTIME='5c3ee219ae51a095ef26ec6bc71e11cafe937413372cc65a245e601a5710de85'
WHEEL='b839cbd608a7c18f59ce83b83a5df4f98d95903039c9aea4bdb0271d574d0719'
CUSTODY='21d7fb4a0c97cb508135632418c7c6d4a43732c5c6c46ba763600b1e7ec23593'
ORDER=['A1','B1','B2','A2']
TOPIC={'A1':'K','B1':'K','B2':'T','A2':'T'}
SUFFIX='另请分别报告两片到参照实际表面的最短间隙（米）。'


def need(ok,message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path=Path(path).resolve(strict=True)
    raw=path.read_bytes()
    return {'path':str(path),'bytes':len(raw),'sha256':sha256(raw).hexdigest()}


def freeze(root):
    pre=root/'preflight'
    admin=pin(pre/'ADMIN_PLAN.md')
    need(root.name==BATCH and admin['sha256']==ADMIN and not (root/'slots').exists(),'wrong_or_started_intent_batch')
    custody=pin(root.parent/'M1-NEAREST-SURFACE-ENTRY-DISCOVERY-001/preflight/INSTALL_CUSTODY.json')
    product=read(custody['path'])
    need(custody['sha256']==CUSTODY and product['candidate_commit']==PRODUCT and product['source_sha256']==RUNTIME
         and product['wheel']['sha256']==WHEEL and product['runtime_sources']==146
         and pin(product['wheel']['path'])==product['wheel'],'changed_fixed_runtime')
    f=pre/'fixture'
    blend,source,truth,prep=(pin(f/x) for x in ('main.blend','EVALUATED_SOURCE.json','TARGET_TRUTH.json','ASSET_PREPARATION.json'))
    truths=read(truth['path'])
    cases=truths['cases']
    need(blend['sha256']==truths['asset_sha256']==read(source['path'])['asset_sha256']
         and source['sha256']==truths['evaluated_source_sha256'] and set(cases)=={'K','T'}
         and not set(cases['K']['nearest_source_triangle_indices'])&set(cases['T']['nearest_source_triangle_indices'])
         and any(not set(c['candidate_aabb_nominee_source_triangle_indices']) &
                 set(c['nearest_source_triangle_indices']) for c in cases.values()),'geometry_did_not_bind_true_counterexample')
    prompts={slot:pin(f/f'PROMPT_{slot[0]}_{topic}.txt') for slot,topic in TOPIC.items()}
    raw={slot:Path(v['path']).read_bytes() for slot,v in prompts.items()}
    r1,r2=(cases[t]['reference_name'].encode('utf8') for t in 'KT')
    for arm in 'AB':
        need(raw[arm+'1'].count(r1)==1 and raw[arm+'2'].count(r2)==1
             and raw[arm+'1'].replace(r1,r2)==raw[arm+'2'],'paired_references_changed_more_than_name')
    for i in '12':
        before,after=raw['A'+i],raw['B'+i]
        need(after.startswith(before) and after[len(before):].decode('utf8').strip()==SUFFIX,
             'B_prompt_not_literal_A_plus_single_requirement')
    plan,cold,controls,parity,scoring=(pin(pre/f'{name}.json') for name in
         ('NATURAL_PLAN','NATURAL_COLD','INTENT_PRODUCT_PREFLIGHT','INTENT_NATURAL_PARITY','SCORE_CONTROLS'))
    setup=read(plan['path'])
    transport=setup['retained_transport']
    need(pin(transport['path'])==transport and read(transport['path'])['passed'] is True
         and setup['order']==ORDER and setup['prompts']==prompts and setup['asset']==blend
         and all(read(x['path'])['passed'] is True for x in (cold,controls,parity,scoring)),
         'missing_qualified_input_or_route')
    measured=pin(HERE/'score.py')
    need(read(scoring['path'])['actual_scorer']=={k:measured[k] for k in ('bytes','sha256')}, 'scoring_controls_not_this_code')
    refs=[admin,custody,prep,controls,parity,scoring,transport,pin(f/'image_viability/IMAGE_VIABILITY.json')]
    refs.extend(pin(p) for p in sorted(HERE.glob('*.py')))
    refs.append(pin(HERE/'RUBRIC.md'))
    for tag in ('m1_nearest_surface_entry_discovery_001','m4_nearest_surface_natural_holdout_001',
                'm4_nearest_surface_first_focus_001','m4_task_region_focus_feedback_001',
                'm4_directed_focus_assembly_holdout_001'):
        refs.append(pin(HERE.parent/tag/'score.py'))
    refs.append(pin(HERE.parent/'m4_reference_only_intent_holdout_001/audit.py'))
    record={'batch':BATCH,'order':ORDER,'product':{'commit':PRODUCT,'source_sha256':RUNTIME,
        'wheel_sha256':WHEEL,'source_files':146},'fixture':{'blend':blend,'source':source,'truth':truth,'prompts':prompts},
        'paired_prompt_suffix':SUFFIX,'natural_plan':plan,'natural_cold':cold,'transport_preflight':transport,
        'product_preflight':controls,'catalogue_parity':parity,'score_controls':scoring,
        'limits':setup['limits'],'inputs':refs}
    file=pre/'FROZEN_EXECUTION.json'
    with file.open('x',encoding='utf8',newline='\n') as out:
        json.dump(record,out,ensure_ascii=False,indent=2)
        out.write('\n')
    print(json.dumps(pin(file),ensure_ascii=False))


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('root',type=lambda value:Path(value).resolve(strict=True))
    freeze(cli.parse_args().root)


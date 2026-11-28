"""Freeze the sole entry-description experiment before any natural slot allocation."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

HERE=Path(__file__).resolve().parent
BATCH='M1-NEAREST-SURFACE-ENTRY-DISCOVERY-001'
ADMIN='62cd96e0673243bfb3f7cfaf183b79caacae52803c738cd706bece89d30400b9'
A='4225256485a82a9ddbdeeca61e1bbd3275574a6e'
B='2f7f492d7d0fd1af2ff956228d31bd57b5e31ddc'
SOURCE='33e90a7092bd042557e11719c52d241776bd7a6e728d04989e1093c11a840d0b'
TRUTH='0bb06a48e8481d0d2502259a842b73df208ec0eee83adc40240352efb34dbf9b'
ASSET='30db8c0e99ed038739c392af71b0ef1bb3bfd6a056cea4f134a75fcee3ca5b9c'
ORDER=['A1','B1','B2','A2']


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
    need(root.name==BATCH and admin['sha256']==ADMIN and not (root/'slots').exists(),'wrong_or_started_batch')
    a_pin=pin(root.parent/'M4-NEAREST-SURFACE-FIRST-FOCUS-001/preflight/INSTALL_CUSTODY.json')
    b_pin=pin(pre/'INSTALL_CUSTODY.json')
    a,b=(read(x['path']) for x in (a_pin,b_pin))
    need((a['candidate_commit'],b['candidate_commit'])==(A,B)
         and a['runtime_sources']==b['runtime_sources']==146,'actual_candidate_changed')
    build=read(b['build']['path'])
    need(build['changed']==['human_eye_plugin/live_spatial_mcp.py']
         and build['parent_commit']==A and build['builds']==build['installs']==1
         and build['description']['increase_bytes']==445,'scope_or_install_outside_plan')
    artefact=pre/'fixture'
    blend,source,truth=(pin(artefact/x) for x in ('main.blend','EVALUATED_SOURCE.json','TARGET_TRUTH.json'))
    cases=read(truth['path'])['cases']
    need((blend['sha256'],source['sha256'],truth['sha256'])==(ASSET,SOURCE,TRUTH)
         and not set(cases['K']['nearest_source_triangle_indices']) & set(cases['T']['nearest_source_triangle_indices'])
         and any(not set(c['nearest_source_triangle_indices']) & set(c['candidate_aabb_nominee_source_triangle_indices'])
                 for c in cases.values()),'fixture_truth_drift')
    prompts={s:pin(artefact/f'PROMPT_{s}.txt') for s in 'KT'}
    one,two=(Path(prompts[t]['path']).read_bytes() for t in 'KT')
    rn,sn=(cases[t]['reference_name'].encode('utf8') for t in 'KT')
    need(one.count(rn)==two.count(sn)==1 and one.replace(rn,sn)==two,'prompts_are_not_paired')
    plan,cold,control,parity=(pin(pre/f'{kind}.json') for kind in
        ('NATURAL_PLAN','NATURAL_COLD','ENTRY_PRODUCT_PREFLIGHT','ENTRY_CATALOGUE_PARITY'))
    setup=read(plan['path'])
    transport=setup['retained_transport']
    need(pin(transport['path'])==transport and read(transport['path'])['passed'] is True
         and setup['order']==ORDER and setup['prompts']==prompts and setup['asset']==blend
         and all(read(x['path'])['passed'] is True for x in (cold,control,parity)),
         'actual_natural_product_or_transport_gate_failed')
    product_proof={'A':{'commit':A,'runtime_sha256':a['source_sha256'],'wheel_sha256':a['wheel']['sha256']},
                   'B':{'commit':B,'runtime_sha256':b['source_sha256'],'wheel_sha256':b['wheel']['sha256']},
                   'description_utf8_delta':445}
    inputs=[admin,a_pin,b_pin,pin(b['build']['path']),pin(artefact/'ASSET_PREPARATION.json'),
            pin(artefact/'image_viability/IMAGE_VIABILITY.json'),parity,control,transport]
    inputs.extend(pin(x) for x in sorted(HERE.glob('*.py')))
    inputs.append(pin(HERE/'RUBRIC.md'))
    for r in ('m4_nearest_surface_natural_holdout_001','m4_nearest_surface_first_focus_001',
              'm4_task_region_focus_feedback_001','m4_directed_focus_assembly_holdout_001'):
        inputs.append(pin(HERE.parent/r/'score.py'))
    inputs.append(pin(HERE.parent/'m4_reference_only_intent_holdout_001/audit.py'))
    record={'batch':BATCH,'order':ORDER,'fixture':{'blend':blend,'source':source,'truth':truth,'prompts':prompts},
            'natural_plan':plan,'natural_cold':cold,'transport_preflight':transport,'product_preflight':control,
            'catalogue_parity':parity,'product':product_proof,'inputs':inputs, 'limits':setup['limits']}
    path=pre/'FROZEN_EXECUTION.json'
    with path.open('x',encoding='utf8',newline='\n') as out:
        json.dump(record,out,ensure_ascii=False,indent=2)
        out.write('\n')
    print(json.dumps(pin(path),ensure_ascii=False))


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('root',type=lambda p:Path(p).resolve(strict=True))
    freeze(cli.parse_args().root)


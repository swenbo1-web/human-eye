"""Pin the natural holdout inputs once before the first owned model slot."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
BATCH='M4-NEAREST-SURFACE-NATURAL-HOLDOUT-001'
ADMIN_SHA='a70496e203f61782f2108bf4d5af4b0ad6eab824dd6a8758d99a2ccac1956a98'
PRODUCT='4225256485a82a9ddbdeeca61e1bbd3275574a6e'
CUSTODY='60014204a745d00ea804dc06df0fff51dddecdbd16b5b6bcc22af01656ab117d'
RUNTIME='60eabe4f875aabbd6c7b1c24c7498ed06b53d10b40a0e70a0ab920b4a64631e0'
WHEEL='5b1f10708bc61cf21453ca0c72fb54cc8b7af19fc3925747bcef96499fd8e4fb'
ASSET='4efb6655353f36500205a286034371d359020600ef75c76970752b091aadab0e'
SOURCE='221761a2377c1a67143f3e32b9fe18e733911714b19557096a4b6d809e130d17'
TRUTH='bffa16c886384cb6e290101382b22ff45c433eaf05e6ecbdf1ccb8bcce65f64e'


def need(ok,message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path=Path(path).resolve(strict=True)
    raw=path.read_bytes()
    return {'path':str(path),'bytes':len(raw),'sha256':sha256(raw).hexdigest()}


def run(root,transport_receipt):
    prep=root/'preflight'
    need(root.name==BATCH and not (root/'slots').exists(),'formal_slot_already_allocated')
    admin=pin(prep/'ADMIN_PLAN.md')
    need(admin['sha256']==ADMIN_SHA,'wrong_admin_plan')
    custody=pin(root.parent/'M4-NEAREST-SURFACE-FIRST-FOCUS-001/preflight/INSTALL_CUSTODY.json')
    product=read(custody['path'])
    need(custody['sha256']==CUSTODY and product['candidate_commit']==PRODUCT
         and product['source_sha256']==RUNTIME and product['wheel']['sha256']==WHEEL
         and product['runtime_sources']==146 and pin(product['wheel']['path'])==product['wheel'],
         'fixed_installed_candidate_changed')
    fixture=prep/'fixture'
    asset,source,truth=(pin(fixture/name) for name in ('main.blend','EVALUATED_SOURCE.json','TARGET_TRUTH.json'))
    truth_content=read(truth['path'])
    need((asset['sha256'],source['sha256'],truth['sha256'])==(ASSET,SOURCE,TRUTH)
         and truth_content['asset_sha256']==ASSET
         and truth_content['evaluated_source_sha256']==SOURCE,'changed_fixture_or_truth')
    cases=truth_content['cases']
    k,t=cases['K'],cases['T']
    need(not set(k['nearest_source_triangle_indices']) & set(t['nearest_source_triangle_indices'])
         and any(not set(case['candidate_aabb_nominee_source_triangle_indices'])
                 & set(case['nearest_source_triangle_indices']) for case in (k,t)),
         'fixture_did_not_preserve_counterexample')
    prompts={label:pin(fixture/f'PROMPT_{label}.txt') for label in ('K','T')}
    text_k,text_t=[Path(prompts[k]['path']).read_bytes() for k in ('K','T')]
    n_k,n_t=k['reference_name'].encode('utf8'),t['reference_name'].encode('utf8')
    need(text_k.count(n_k)==text_t.count(n_t)==1 and text_k.replace(n_k,n_t)==text_t,'prompt_split_drift')
    plan_path=prep/'NATURAL_PLAN.json'
    cold_path=prep/'NATURAL_COLD.json'
    receipt=pin(transport_receipt)
    need(Path(receipt['path']).is_relative_to(prep) and read(receipt['path'])['passed'] is True,
         'close_preflight_not_accepted')
    transport=read(receipt['path'])
    need(transport['Blender']==0 and transport['models']==0 and transport['actual_app_server_processes']==3
         and transport['formal_transport']==pin(HERE/'transport.py')
         and set(transport['cases'])=={'normal','missing_last','reset'}, 'wrong_paired_close_preflight')
    for row in transport['cases'].values():
        need(pin(row['path'])==row,'changed_own_close_receipt')
    needs={'natural_plan':pin(plan_path),'natural_cold':pin(cold_path),'transport_preflight':receipt}
    cold=read(cold_path)
    need(cold['passed'] is True,'consumer_cold_path_not_accepted')
    inputs=[admin,custody,pin(fixture/'ASSET_PREPARATION.json'),pin(fixture/'IMAGE_VIABILITY.json'),receipt]
    inputs.extend(pin(x) for x in sorted(HERE.glob('*.py')))
    inputs.extend(pin(x) for x in sorted((prep/'retained_old_closes').glob('*.json')))
    inputs.append(pin(HERE/'RUBRIC.md'))
    inputs.extend(pin(x) for x in (HERE.parent/'m4_nearest_surface_first_focus_001/score.py',
                                  HERE.parent/'m4_reference_only_intent_holdout_001/audit.py',
                                  HERE.parent/'m4_task_region_focus_feedback_001/score.py',
                                  HERE.parent/'m4_directed_focus_assembly_holdout_001/score.py'))
    frozen={'batch':BATCH,'fixture':{'blend':asset,'source':source,'truth':truth,'prompts':prompts},
            'order':['NATURAL_K','NATURAL_T'],
            'limits':{'formal_Blender':2,'consumers':2,'business_per_slot':8,'rasters_per_slot':4,
                      'request_seconds':450,'lifecycle_seconds':600,'substitutes':0},
            'product':{'commit':PRODUCT,'runtime_sha256':RUNTIME,'wheel_sha256':WHEEL,'runtime_sources':146},
            'pixel_minimum':16,'inputs':inputs,**needs}
    path=prep/'FROZEN_EXECUTION.json'
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(frozen,stream,ensure_ascii=False,indent=2)
        stream.write('\n')
    print(json.dumps(pin(path),ensure_ascii=False))


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('root',type=lambda value:Path(value).resolve(strict=True))
    cli.add_argument('transport_receipt',type=Path)
    args=cli.parse_args()
    run(args.root,args.transport_receipt)


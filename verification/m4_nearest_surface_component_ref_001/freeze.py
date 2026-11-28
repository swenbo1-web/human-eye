"""Bind the one candidate, paired literal prompts and actual acceptance to formal launch."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BATCH = 'M4-NEAREST-SURFACE-COMPONENT-REF-001'
ADMIN = '45ca48b93c667b45ba9cc695aad53c0930bdb030527968ff9641425dd6762fab'
ORDER = ['A1','B1','B2','A2']
BASE = '2f7f492d7d0fd1af2ff956228d31bd57b5e31ddc'
ASSET = '2cb78efc91bfded88d8409f50e3de8e309f68a7b6d66ab0d05ad37a93dff0341'


def pin(path):
    path=Path(path).resolve(strict=True)
    raw=path.read_bytes()
    return {'path':str(path),'bytes':len(raw),'sha256':sha256(raw).hexdigest()}


def read(path):
    return json.loads(Path(path).read_bytes())


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def freeze(root):
    prep=root/'preflight'
    admin=pin(prep/'ADMIN_PLAN.md')
    need(root.name==BATCH and admin['sha256']==ADMIN and not (root/'slots').exists(),
         'wrong_or_started_component_batch')
    plan_path,cold_path,proof_path,scorer_path = (prep/name for name in (
        'NATURAL_PLAN.json','NATURAL_COLD.json','COMPONENT_PRODUCT_PREFLIGHT.json','SCORE_CONTROLS.json'))
    plan,cold,proof,controls = map(read,(plan_path,cold_path,proof_path,scorer_path))
    scorer=pin(HERE/'score.py')
    registered_scorer=controls['actual_scorer']
    need(controls['passed'] is True
         and all(registered_scorer[key]==scorer[key] for key in ('bytes','sha256')),
         'unqualified_actual_formal_scorer')
    need(plan['order']==ORDER and cold['passed'] and cold['same_actual_catalogue']
         and cold['plan']==pin(plan_path) and proof['passed'] and proof['same_actual_catalogue']
         and proof['actual_cold']==pin(cold_path) and proof['script']==pin(HERE/'component_preflight.py')
         and proof['custody']==pin(prep/'INSTALL_CUSTODY.json'), 'unqualified_actual_component_launch')
    for arm in 'AB':
        need(cold['arms'][arm]['actual_tools']==plan['prior_actual_catalogue'], 'actual_public_directory_changed')
    asset = pin(prep/'fixture/main.blend')
    source = pin(prep/'fixture/EVALUATED_SOURCE.json')
    truth = pin(prep/'fixture/TARGET_TRUTH.json')
    k,t = (pin(prep/'fixture'/name) for name in ('PROMPT_A_K.txt','PROMPT_B_T.txt'))
    prompts = {'A1':k,'B1':k,'B2':t,'A2':t}
    need(plan['asset']==asset and plan['prompts']==prompts and asset['sha256']==ASSET
         and read(truth['path'])['asset_sha256']==ASSET
         and read(truth['path'])['evaluated_source_sha256']==source['sha256']
         and k['bytes']==396 and t['bytes']==468, 'wrong_synthetic_fixture_or_pair')
    product = {arm:{'commit':row['product'],'source_sha256':row['product_source_sha256'],
                    'source_files':row['product_source_files'],'wheel_sha256':row['wheel']['sha256']}
               for arm,row in plan['arms'].items()}
    need(product['A']['commit']==BASE and product['A']!=product['B'], 'candidate_with_wrong_baseline')
    transport=plan['retained_transport']
    need(pin(transport['path'])==transport and read(transport['path'])['passed'], 'no_actual_transport_admission')
    inputs = [admin,pin(plan_path),pin(cold_path),pin(proof_path),pin(scorer_path),transport,
              pin(prep/'FIXTURE_CUSTODY.json'),asset,source,truth,k,t,*plan['inputs']]
    inputs.extend(pin(p) for p in sorted(HERE.glob('*.py')))
    for arm,qual in proof['arms'].items():
        inputs.extend(qual[key] for key in ('raw_wire','closure','public_stdout','catalogue'))
        for tag,case in qual['cases'].items():
            inputs.extend([case['producer'],*case['wire'].values(),*case['reference_wire'].values(),
                           case['frame']['PNG'],case['frame']['NPZ']])
    inputs.extend([proof['frame_verifier'],proof['full_controls']['actual_process'],
                   proof['full_controls']['real_close'],
                   *(pin(prep/'full_controls'/name) for name in ('TX.bin','STDOUT.bin','PRODUCER.json')),
                   pin(prep/'unit_checks/UNIT_CHECKS.json'),
                   pin(prep/'COMPONENT_PRODUCT_PREFLIGHT_INITIAL_FAILURE.json')])
    for history in ('m4_nearest_surface_task_intent_001','m1_nearest_surface_entry_discovery_001',
                    'm4_nearest_surface_natural_holdout_001','m4_nearest_surface_first_focus_001',
                    'm4_task_region_focus_feedback_001','m4_directed_focus_assembly_holdout_001'):
        inputs.append(pin(HERE.parent/history/'score.py'))
    inputs.append(pin(HERE.parent/'m4_reference_only_intent_holdout_001/audit.py'))
    inputs.append(pin(HERE.parent/'m4_nearest_surface_first_focus_001/controls.py'))
    unique={record['path']:record for record in inputs}
    for record in unique.values():
        need(pin(record['path'])==record, 'frozen_preflight_changed/'+Path(record['path']).name)
    data={'batch':BATCH,'order':ORDER,'product':product,
          'fixture':{'blend':asset,'source':source,'truth':truth,'prompts':prompts},
          'natural_plan':pin(plan_path),'natural_cold':pin(cold_path),'transport_preflight':transport,
          'product_preflight':pin(proof_path),'score_controls':pin(scorer_path),'limits':plan['limits'],
          'inputs':list(unique.values())}
    path=prep/'FROZEN_EXECUTION.json'
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(data,stream,indent=2,ensure_ascii=False)
        stream.write('\n')
    print(json.dumps(pin(path)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=lambda path: Path(path).resolve(strict=True))
    freeze(parser.parse_args().root)


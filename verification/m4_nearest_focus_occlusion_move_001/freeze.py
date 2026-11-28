"""Register the fixed scene before A and bind the one isolated candidate before B."""
from hashlib import sha256
import argparse
import json
from pathlib import Path

BATCH = 'M4-NEAREST-FOCUS-OCCLUSION-MOVE-001'
ADMIN = '2bc87832d55e7508d36ed1a53fff485168f30677cf2542c7d56ea6297515072d'
BASELINE = 'ad35b150b1cdc3d90a9de894d49ebaf2148efc88'
BASELINE_INSTALL = 'ea7995594709e4922168e73672085e4a40ceedfd32847ef43f6763104aacbed2'
FIXTURE = {'blend':'main.blend','asset_binding':'ASSET_BINDING.json',
           'truth':'TRUTH.json','requests':'REQUESTS.json','source':'CURRENT_SOURCE.json'}
LIMITS = {'actual_rasters_per_request':2,'minimum_target_pixels':16,'formal_Blender':2,'model_calls':0}
HERE = Path(__file__).resolve().parent


def pin(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    return {'path':str(path),'bytes':len(raw),'sha256':sha256(raw).hexdigest()}


def read(path):
    return json.loads(Path(path).read_bytes())


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def write(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as out:
        json.dump(value, out, ensure_ascii=False, sort_keys=True, indent=2)
        out.write('\n')
    print(json.dumps(pin(path)))


def install(path):
    record = read(path)
    original = ('python','blender','wheel','build')
    for key in original:
        require(pin(record[key]['path'])==record[key], 'invalid_install_pin/'+key)
    site = Path(record['installation']['path']).resolve(strict=True)
    manifest = record['source_manifest']
    require(record['passed'] is True and record['runtime_sources']==len(manifest)==146,
            'source_manifest_did_not_register_real_install')
    for member in manifest:
        require(pin(site/member['path'])['sha256']==member['sha256'], 'runtime_source_changed/'+member['path'])
    return record


def baseline(root, script_inputs):
    require(not (root/'slots'/'A').exists() and not (root/'slots'/'B').exists(),
            'official_run_already_started')
    base_path = root.parent/'M4-NEAREST-SURFACE-COMPONENT-REF-001/preflight/INSTALL_CUSTODY.json'
    receipt = pin(base_path)
    product = install(base_path)
    require(receipt['sha256']==BASELINE_INSTALL and product['candidate_commit']==BASELINE,
            'unexpected_actual_baseline')
    fixture={key:pin(root/'preflight'/'fixture'/path) for key,path in FIXTURE.items()}
    binding=read(fixture['asset_binding']['path'])
    require(binding['reopened_source_exact'] is True and binding['save_count']==1 and binding['rasters']==0,
            'fixture_not_independently_reopened_once')
    for key, fixture_key in (('asset','blend'),('truth','truth'),('source','source'),('requests','requests')):
        info=binding[key]
        require(info['sha256']==fixture[fixture_key]['sha256'] and info['bytes']==fixture[fixture_key]['bytes']
                and Path(info['path']).resolve()==Path(fixture[fixture_key]['path']), 'unchecked_fixture_pin/'+key)
    require(read(fixture['truth']['path'])['asset_sha256']==fixture['blend']['sha256'],
            'truth_not_prespecified_for_exact_asset')
    selected=[pin(path) for path in (Path(__file__),root/'preflight/ADMIN_PLAN.md',*script_inputs)]
    require(len({item['path'] for item in selected})==len(selected), 'duplicate_phase_input')
    write(root/'preflight/FROZEN_BASELINE.json', {'batch':BATCH,'stage':'baseline',
          'limits':LIMITS,'fixture':fixture,'baseline_installation':receipt,'inputs':selected})


def candidate(root, baseline_audit, deadline_result, script_inputs):
    pre = root/'preflight'
    initial = pin(pre/'FROZEN_BASELINE.json')
    frozen = read(initial['path'])
    require(frozen['batch']==BATCH and frozen['stage']=='baseline'
            and frozen['limits']==LIMITS and (root/'slots'/'A').is_dir()
            and not (root/'slots'/'B').exists(), 'expected_only_A_closed')
    for item in [*frozen['fixture'].values(),*frozen['inputs'],frozen['baseline_installation']]:
        require(pin(item['path'])==item, 'baseline_changed/'+Path(item['path']).name)
    audit, deadline = (pin(value) for value in (baseline_audit, deadline_result))
    require(read(audit['path']).get('passed') is True and read(deadline['path']).get('passed') is True,
            'baseline_or_deadline_gate_failed')
    custody = pin(pre/'INSTALL_CUSTODY.json')
    product = install(custody['path'])
    require(product['candidate_commit']!=BASELINE and
            read(product['build']['path'])['parent_commit']==BASELINE and
            read(deadline['path'])['identity']==product['source_sha256'], 'candidate_not_exact_accepted_build')
    selected = [pin(path) for path in script_inputs]
    write(pre/'FROZEN_CANDIDATE.json', {'batch':BATCH,'stage':'candidate',
        'limits':LIMITS,'fixture':frozen['fixture'],'baseline_freeze':initial,
        'baseline_audit':audit,'baseline_installation':frozen['baseline_installation'],
        'candidate_installation':custody,'deadline_control':deadline,'inputs':selected})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=lambda path:Path(path).resolve(strict=True))
    p.add_argument('phase',choices=('baseline','candidate'))
    p.add_argument('inputs',nargs='*',type=Path)
    a=p.parse_args()
    require(a.root.name==BATCH and pin(a.root/'preflight/ADMIN_PLAN.md')['sha256']==ADMIN, 'incorrect_admin_plan')
    if a.phase=='baseline':
        baseline(a.root,a.inputs)
    else:
        candidate(a.root,a.inputs[0],a.inputs[1],a.inputs[2:])


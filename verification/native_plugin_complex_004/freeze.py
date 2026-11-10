"""Freeze reviewed preparation. This does not grant model execution GO."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def read(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    plan=read(HERE/'PLAN.json');preflight=read(HERE/'PREFLIGHT_REVIEW.json');tests=read(HERE/'WRAPPER_TESTS.json');source=read(HERE/'SOURCE_PREFLIGHT.json')
    assert plan['denominator']==18 and preflight['passed'] and preflight['model_calls']==0 and tests['passed']
    assert tests['actor_sha256']==sha(HERE/'actor.py')
    refs=read(HERE/'SCORING_CONTRACT.json')['references']
    files={str((ROOT/row['path']).resolve()):row['sha256'] for row in refs.values()}
    for p in HERE.glob('*.py'):files[str(p.resolve())]=sha(p)
    for name in ('PLAN.json','PLAN_DRAFT.md','SCORING_CONTRACT.json','SESSION_RULES.txt','PROMPT_DISCOVERY.txt','SOURCE_PREFLIGHT.json','CLI_PREFLIGHT.json','PREFLIGHT.json','PREFLIGHT_REVIEW.json','WRAPPER_TESTS.json','O_schemas.stdout.json','C_schemas.stdout.json','O_identity.stdout.json','C_identity.stdout.json'):
        files[str((HERE/name).resolve())]=sha(HERE/name)
    for name in ('actor.py','reused/accepted_native.py','reused/stdio_attach.py'):
        p=HERE.parent/'native_plugin_complex_003'/name;files[str(p.resolve())]=sha(p)
    for group in ('O','C'):
        entry=Path(source['versions'][group]['entry'])
        for p in (entry,entry.with_name('RUNTIME_BINDING.json'),entry.with_name('installed_release.py')):files[str(p.resolve())]=sha(p)
    assert all(sha(path)==want for path,want in files.items())
    result={'task':'NATIVE-PLUGIN-COMPLEX-004','phase':'PREFLIGHT_READY, root GO pending','parent_commit':'df016079b0265ee327f884c90dd4815c392016b6',
        'root_plan_commit':'10c0f6bd','model_execution_authorized':False,'logical_denominator':18,'files_sha256':files,
        'private_truth_visibility':'not sent, copied into consumer workspaces, or exposed by public broker; protocol audited, not an adversarial Python OS sandbox',
        'model_inputs':{task:{key:row[key] for key in ('prompt_sha256','model_input_sha256','model_input_bytes')} for task,row in plan['tasks'].items()},
        'source_versions':{group:source['versions'][group]['source_sha256'] for group in ('O','C')},'preflight_model_calls':0,
        'no_product_or_default_config_changes':True}
    target=HERE/'FREEZE.json';assert not target.exists()
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'freeze_sha256':sha(target),'files':len(files),'model_calls':0,'phase':result['phase']}))
if __name__=='__main__':main()

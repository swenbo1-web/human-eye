"""Seal only the projection correction; read/hash existing evidence, no replay."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

REV=Path(__file__).resolve().parent
BATCH=REV.parents[1]
ROOT=BATCH.parents[1]
OLD=REV/'original_9c85ab9a'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())


def main():
    assert not any((BATCH/name).exists() for name in ('GO.json','STARTED.json','RUN_RESULT.json','cells'))
    archive=read(REV/'ORIGINAL_ARCHIVE.json')
    for row in archive['files']:
        p=OLD/row['path']
        assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
    original_index=read(OLD/'ARTIFACT_INDEX.json')
    assert (BATCH/'ARTIFACT_INDEX.json').read_bytes()==(OLD/'ARTIFACT_INDEX.json').read_bytes()
    assert (BATCH/'FREEZE.json').read_bytes()==(OLD/'FREEZE.json').read_bytes()
    allowed={'quality_handoff/pack_quality.py','quality_handoff/SOURCE_REUSE.json','PLAN.json','REPORT.md'}
    for row in original_index['files']:
        path=ROOT/row['path'];relative=path.relative_to(BATCH).as_posix()
        if relative not in allowed:
            assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],relative
    plan=read(BATCH/'PLAN.json');old_plan=read(OLD/'PLAN.json')
    old_minus_quality={k:v for k,v in old_plan.items() if k not in (
        'phase','quality_handoff_script_sha256','quality_handoff_execution',
        'dispatch_input_sha256','quality_packet_policy')}
    new_minus_quality={k:v for k,v in plan.items() if k not in (
        'phase','quality_handoff_script_sha256','quality_handoff_execution',
        'dispatch_input_sha256','quality_packet_policy','preparation_revision')}
    assert old_minus_quality==new_minus_quality
    assert len(plan['dispatch_input_sha256'])==len(old_plan['dispatch_input_sha256'])==37
    for key,expected in plan['dispatch_input_sha256'].items():assert sha(BATCH/key)==expected,key
    for key,expected in old_plan['dispatch_input_sha256'].items():
        if key not in ('quality_handoff/pack_quality.py','quality_handoff/SOURCE_REUSE.json'):
            assert plan['dispatch_input_sha256'][key]==expected
    assert {k:v for k,v in plan['quality_packet_policy'].items() if k!='source_and_evidence'}=={
        k:v for k,v in old_plan['quality_packet_policy'].items() if k!='source_and_evidence'}
    baseline=read(REV/'tests/baseline_01/EVIDENCE.json')
    revised=read(REV/'tests/revised_01/EVIDENCE.json')
    assert baseline['packager_sha256']==sha(OLD/'quality_handoff/pack_quality.py')
    assert revised['packager_sha256']==sha(BATCH/'quality_handoff/pack_quality.py')
    assert baseline['test_script_sha256']==revised['test_script_sha256']==sha(REV/'tests/run_projection_contract.py')
    assert baseline['test_result']['tests_run']==revised['test_result']['tests_run']==4
    assert not baseline['test_result']['contract_passed'] and baseline['test_result']['only_expected_old_semantic_assertions']
    assert len(baseline['test_result']['failures'])==2 and not baseline['test_result']['errors']
    assert revised['test_result']['contract_passed'] and not revised['test_result']['failures'] and not revised['test_result']['errors']
    assert (REV/'tests/baseline_01/SYNTHETIC_FIXTURE.json').read_bytes()==(REV/'tests/revised_01/SYNTHETIC_FIXTURE.json').read_bytes()
    assert sha(BATCH/'quality_handoff/pack_quality.py')==plan['quality_handoff_script_sha256']
    # Product source identity is checked without importing or executing it.
    tree=ast.parse((ROOT/'human_eye_plugin/runtime_identity.py').read_bytes())
    values={n.targets[0].id:ast.literal_eval(n.value) for n in tree.body
        if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name)
        and n.targets[0].id in ('BASE_VERSION','IMPLEMENTATION_REVISION','_ROOT_MODULES')}
    names=set(values['_ROOT_MODULES'])|{p.relative_to(ROOT).as_posix()
        for d in ('human_eye_plugin','human_eye_module1_operators') for p in (ROOT/d).glob('*.py')}
    manifest=[{'path':name,'sha256':sha(ROOT/name)} for name in sorted(names)]
    value={'base_version':values['BASE_VERSION'],'implementation_revision':values['IMPLEMENTATION_REVISION'],'files':manifest}
    canonical=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    assert len(manifest)==137 and canonical==plan['candidate_source_sha256']=='7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1'
    changed=subprocess.run(['git','-C',str(ROOT),'diff','--name-only'],check=True,stdout=subprocess.PIPE).stdout.decode().splitlines()
    assert set(changed)=={(BATCH/p).relative_to(ROOT).as_posix() for p in allowed},changed
    paths={ROOT/row['path'] for row in original_index['files']}
    paths.update(p for p in REV.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    for path in paths:
        if path.suffix=='.py':compile(path.read_bytes(),str(path),'exec',dont_inherit=True)
    files=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(paths)]
    index={'cycle_id':plan['cycle_id'],'revision':'M4-PREP-001',
        'supersedes_commit':'9c85ab9a0518e1fe2369113f59ce308a2d97b8d3',
        'file_count':len(files),'bytes':sum(row['bytes'] for row in files),'files':files,
        'exclusion_policy':original_index['exclusion_policy'],
        'revision_scope':'original 303 selected material paths plus explicit revision originals/reference/synthetic tests/notes; no new backend or model artifacts'}
    (BATCH/'ARTIFACT_INDEX.json').write_text(json.dumps(index,indent=2,ensure_ascii=True)+'\n',encoding='utf8')
    freeze=read(OLD/'FREEZE.json')
    freeze.update(status='PREP_FIX_READY',revision='M4-PREP-001',
        supersedes={'commit':'9c85ab9a0518e1fe2369113f59ce308a2d97b8d3','originals':'revisions/M4_PREP_001/original_9c85ab9a',
            'PLAN_sha256':sha(OLD/'PLAN.json'),'FREEZE_sha256':sha(OLD/'FREEZE.json'),'INDEX_sha256':sha(OLD/'ARTIFACT_INDEX.json'),'packager_sha256':sha(OLD/'quality_handoff/pack_quality.py')},
        plan_sha256=sha(BATCH/'PLAN.json'),artifact_index_sha256=sha(BATCH/'ARTIFACT_INDEX.json'),
        indexed_files=len(files),indexed_bytes=index['bytes'],quality_handoff_script_sha256=sha(BATCH/'quality_handoff/pack_quality.py'),
        directed_test_script_sha256=sha(REV/'tests/run_projection_contract.py'),
        old_expected_semantic_failures=2,old_errors=0,revised_tests_passed=4,revised_errors=0,
        unchanged_original_index_files=299,revision_model_consumers=0,revision_product_or_Blender_runs=0,
        revision_installation_or_geometry_replays=0,formal_GO=False,
        reused_preparation_evidence_from_commit='9c85ab9a0518e1fe2369113f59ce308a2d97b8d3',
        report='verification/m4_observation_baseline_001/revisions/M4_PREP_001/REPORT.md')
    (BATCH/'FREEZE.json').write_text(json.dumps(freeze,indent=2,ensure_ascii=True)+'\n',encoding='utf8')
    print(json.dumps({k:freeze[k] for k in ('cycle_id','status','revision','plan_sha256','artifact_index_sha256',
        'quality_handoff_script_sha256','directed_test_script_sha256','indexed_files','indexed_bytes','formal_GO')},ensure_ascii=True))


if __name__=='__main__':main()

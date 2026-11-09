"""Check and index fixed artifacts after cleanup, without product execution."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BASE='a3a72b929f55c40f195ff5e1a9f64ceb303b6360'
CORE=('human_eye_plugin/arm_twist_source.py','human_eye_plugin/blender_host.py',
      'human_eye_plugin/goal_execution.py')


def read(path):return json.loads(path.read_text(encoding='utf8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    cpu=read(HERE/'cpu_final_02/RESULT.json');audit=read(HERE/'INDEPENDENT_PAIR_AUDIT.json')
    compare=read(HERE/'COST_COMPARISON.json');cleanup=read(HERE/'CLEANUP.json')
    assert cpu['passed'] and cpu['tests']==62
    assert cpu['failures']==cpu['errors']==cpu['skips']==0
    assert cpu['diagnostic_prediction_calls']==14 and cpu['geometry_model_calls']==0
    assert cpu['before_sha256']==cpu['after_sha256']
    for name,value in cpu['after_sha256'].items():assert sha(ROOT/name)==value,name
    assert audit['passed'] and audit['checks']==16218
    assert sha(HERE/'audit_pair.py')==audit['script_sha256']
    assert sha(ROOT/'verification/arm_correction_execution_001/audit_execution.py')==audit['helper_script_sha256']
    for name,value in audit['input_sha256'].items():
        assert sha(ROOT/name.replace('\\','/'))==value,name
    assert compare['passed'] and compare['resamples']==0
    assert sha(HERE/'compare_costs.py')==compare['script_sha256']
    baseline=read(HERE/'BASELINE_MATERIALIZATION.json')
    assert baseline['commit']==BASE and baseline['runtime_sources']==137
    for name,value in baseline['files'].items():
        raw=subprocess.check_output(['git','show',BASE+':'+name],cwd=ROOT)
        assert hashlib.sha256(raw).hexdigest()==value,name
    identities={}
    for label,preparations,validations in (('baseline',8,16),('candidate',0,8)):
        run=HERE/(label+'_01');value=read(run/'RESULT.json')
        freeze=read(run/'SOURCE_FREEZE.json')
        assert value['passed'] and value['source_before']==value['source_after']
        assert len(value['source_before']['source_files'])==137
        assert value['source_work_totals']['preparations']==preparations
        assert value['source_work_totals']['static_reads']==12
        assert value['source_cost_counts'].get('prepare_patch',0)==preparations
        assert value['source_cost_counts']['_parse_patch']==8
        assert value['cost_counts']['arm_ledger_validation']==validations
        assert value['product_work']=={'mutation_rpc':8,'setter_attempts':8,'setter_returns':8,
            'preview_calls':8,'source_captures':12}
        assert value['model_calls']==value['qa_candidate_assignments']==0
        assert value['process_exit']['closed'] and value['process_exit']['returncode']==0
        assert value['blend_sha256_before']==value['blend_sha256_after']==sha(Path(freeze['blend_path']))
        assert value['replay']['rpc_delta']==0 and value['replay']['result']['replayed']
        assert compare[label]['result_sha256']==sha(run/'RESULT.json')
        for name,digest in freeze['qa_scripts'].items():assert sha(Path(name))==digest,name
        for member in value['source_before']['source_files']:
            expected=baseline['files'][member['path']] if label=='baseline' else sha(ROOT/member['path'])
            assert member['sha256']==expected,member
        identities[label]=value['source_before']['source_sha256']
    assert cleanup['baseline_directory_removed'] and cleanup['owned_processes_absent']
    assert not Path(cleanup['baseline_target']).exists()
    assert sha(HERE/'cleanup_baseline.ps1')==cleanup['cleanup_script_sha256']
    changed=subprocess.check_output(['git','diff','--name-only',BASE,'--','human_eye_plugin'],cwd=ROOT,text=True).splitlines()
    assert sorted(changed)==sorted(CORE),changed
    assert not subprocess.check_output(['git','diff','--name-only',BASE,'--',
        'verification/arm_correction_execution_001'],cwd=ROOT,text=True).strip()
    files={}
    for path in sorted(HERE.rglob('*')):
        if not path.is_file() or path.name=='EVIDENCE_INDEX.json':continue
        assert '__pycache__' not in path.parts and path.suffix!='.pyc',path
        files[path.relative_to(ROOT).as_posix()]={'bytes':path.stat().st_size,'sha256':sha(path)}
    result={'schema':'arm-correction-execution-opt-evidence-index-v1','passed':True,'base_commit':BASE,
        'core_sha256':{name:sha(ROOT/name) for name in CORE},'runtime_source_sha256':identities,
        'cpu_methods':62,'independent_checks':16218,'native_runs_per_version':1,'native_tasks_per_version':8,
        'geometry_model_calls':0,'final_cpu_diagnostic_prediction_calls':14,
        'files':files,'exclusions':['EVIDENCE_INDEX.json (self reference)'],
        'new_product_calls':0,'new_Blender_runs':0,'new_model_calls':0}
    (HERE/'EVIDENCE_INDEX.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'passed':True,'files':len(files),'index_sha256':sha(HERE/'EVIDENCE_INDEX.json')}))


if __name__=='__main__':main()

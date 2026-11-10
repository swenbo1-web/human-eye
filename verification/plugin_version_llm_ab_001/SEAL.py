"""Index fixed experiment bytes and verify recorded installations, no execution."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BASE='d01d49bc0ec82583b24a8faf22e622e6f6ea8c5d'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf8'))


def main():
    plan=read(HERE/'PLAN.json');freeze=read(HERE/'RUNNER_FREEZE.json')
    for name,digest in read(HERE/'PLAN_FREEZE.json').items():assert sha(HERE/name)==digest,name
    for key,name in [('runner_sha256','run_consumers.py'),('bridge_sha256','bridge.py'),
        ('initializer_sha256','initializer.py'),('plan_sha256','PLAN.json'),
        ('grader_sha256_at_recovery_start','audit_results.py'),('amendment_sha256','AMENDMENT.json')]:
        assert sha(HERE/name)==freeze[key],name
    installs=read(HERE/'INSTALL_RESULT.json');assert installs['passed']
    install_members=0
    for version,value in installs['versions'].items():
        wheel=ROOT/value['wheel'].replace('\\','/');assert sha(wheel)==value['wheel_sha256']
        identity=value['proof']['runtime_identity'];assert identity['source_kind']=='installed_distribution'
        assert len(identity['source_files'])==137
        with zipfile.ZipFile(wheel) as archive:
            for member in identity['source_files']:
                name=member['path'];expected=member['sha256']
                assert hashlib.sha256(archive.read(name)).hexdigest()==expected,name
                assert sha(Path(value['installed_root'])/name)==expected,name
                git=subprocess.check_output(['git','show',value['commit']+':'+name],cwd=ROOT)
                assert hashlib.sha256(git).hexdigest()==expected,name
                install_members+=1
    run=read(HERE/'RUN_RESULT.json')
    assert run['denominator']==run['total_attempts']==13 and run['formal_denominator']==12
    assert run['consumers_started']==12 and run['stop_reason'] is None
    assert sha(HERE/'infra_attempt_01/RUN_RESULT.json')==run['infra_attempt_result_sha256']
    assert len(run['cells'])==12 and all(c['valid_completion'] and c['safe_to_continue'] for c in run['cells'])
    result=read(HERE/'INDEPENDENT_RESULTS.json');assert result['script_sha256']==sha(HERE/'audit_results.py')
    assert result['formal_comparison_denominator']==12 and result['all_attempt_denominator']==13
    assert sum(r['geometry_pass'] for r in result['cells'])==12
    assert sum(r['model_answer']['score'] for r in result['cells'])==59
    assert result['group_summaries']['all']['A']['model_score_sum']==29
    assert result['group_summaries']['all']['B']['model_score_sum']==30
    assert sum(r['model_answer']['pass'] for r in result['cells'])==4
    for name,digest in result['input_sha256'].items():assert sha(ROOT/name)==digest,name
    extras=read(HERE/'SUPPLEMENTAL_METRICS.json');assert extras['passed']
    assert extras['script_sha256']==sha(HERE/'supplement_metrics.py')
    for name,digest in extras['input_sha256'].items():assert sha(Path(name))==digest,name
    assert extras['actual_usage_totals']['all13']['input_tokens']==301963
    assert extras['actual_usage_totals']['all13']['output_tokens']==3270
    assert read(HERE/'CLEANUP.json')['all_absent']
    thread_ids=[]
    for item in plan['sequence']:
        folder=HERE/'formal_cells'/item['cell'];consumer=read(folder/'CONSUMER.json')
        bridge=read(folder/'bridge_native/BRIDGE_RESULT.json')
        assert bridge['closed'] and bridge['process_exit']['closed'] and bridge['process_exit']['returncode']==0
        assert bridge['source_before']==bridge['source_after'] and bridge['source_unchanged']
        assert bridge['bridge_sha256']==freeze['bridge_sha256']
        assert len(bridge['calls'])==1
        assert bridge['cost_counts']['arm_ledger_validation']==(2 if item['version']=='A' else 1)
        assert bridge['calls'][0]['result']['work']['source']['preparations']==(1 if item['version']=='A' else 0)
        assert bridge['blend_sha256_before']==bridge['blend_sha256_after']
        cfg=read(folder/'cell.json');assert sha(Path(cfg['blend_file']))==bridge['blend_sha256_after']
        thread_ids.append(consumer['thread_id'])
    old=read(HERE/'cells/01/CONSUMER.json');thread_ids.append(old['thread_id'])
    assert len(set(thread_ids))==13
    assert not (HERE/'cells/01/bridge_native/FINAL_NATIVE.json').exists()
    assert not subprocess.check_output(['git','diff',BASE,'--name-only','--','human_eye_plugin',
        'human_eye_module1_operators','pyproject.toml'],cwd=ROOT,text=True).strip()
    members={}
    for path in sorted(HERE.rglob('*')):
        if not path.is_file() or path.name=='EVIDENCE_INDEX.json':continue
        assert '__pycache__' not in path.parts and path.suffix!='.pyc',path
        members[path.relative_to(ROOT).as_posix()]={'bytes':path.stat().st_size,'sha256':sha(path)}
    index={'schema':'plugin-version-llm-ab-evidence-index-v1','passed':True,'base_commit':BASE,
        'formal_denominator':12,'all_attempt_denominator':13,'unique_new_consumer_threads':13,
        'installed_runtime_members_checked':install_members,'geometry_passes':12,
        'strict_model_score':{'A':29,'B':30,'max_per_version':36,'full_passes':4},
        'external_root_semantic_score':'72/72 semantic criteria; separate from author strict59/72',
        'source_versions':{k:v['commit'] for k,v in installs['versions'].items()},
        'new_model_calls':0,'new_product_calls':0,'new_Blender_runs':0,
        'files':members,'exclusions':['EVIDENCE_INDEX.json (self reference)',
            '.plugin_ab_runtime installed environments retained locally, wheels and identities indexed']}
    (HERE/'EVIDENCE_INDEX.json').write_text(json.dumps(index,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'passed':True,'indexed_files':len(members),'bytes':sum(v['bytes'] for v in members.values()),
        'index_sha256':sha(HERE/'EVIDENCE_INDEX.json')}))


if __name__=='__main__':main()

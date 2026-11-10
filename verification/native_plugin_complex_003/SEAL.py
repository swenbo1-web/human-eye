"""Seal recorded evidence; no product/model/Blender execution."""
import hashlib,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BASE='4d7801cf7072e9da0ba302710acd35ace1e1c645'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    for name,digest in read(HERE/'FREEZE.json').items():assert sha(HERE/name)==digest,name
    plan=read(HERE/'PLAN.json');run=read(HERE/'RUN_RESULT.json');metrics=read(HERE/'METRICS.json')
    assert len(plan['sequence'])==run['denominator']==len(run['cells'])==9
    assert run['stop_reason'] is None and metrics['completed']==metrics['geometry_verified']==9
    assert metrics['script_sha256']==sha(HERE/'analyze.py')
    for name,digest in metrics['inputs_sha256'].items():assert sha(HERE/name)==digest,name
    assert read(HERE/'CLEANUP.json')['all_absent']
    assert sha(HERE/'scene.blend')==plan['asset_sha256']
    assert sha(HERE/'private/TRUTH.json')==plan['truth_sha256']
    sessions=[]
    for row in plan['sequence']:
        folder=HERE/'cells'/row['cell'];c=read(folder/'CONSUMER.json')
        assert c['valid_completion'] and c['owner_finish']['confirmed']
        sessions.append(c['thread_id'])
        assert c['input_sha256']==plan['prompt_sha256']
        close=read(folder/'owner/CLOSE.json');assert close['confirmed'] and close['geometry_unchanged']
        assert close['native_close']['process_reaped'] and close['native_close']['exit_code']==0
        assert close['native_close']['response']['status']=='closed'
        assert close['worker_closed']['initial_geometry_fingerprint']==close['worker_closed']['final_geometry_fingerprint']
        identity=read(folder/'owner/IDENTITY.json')['runtime_identity']
        if row['group']=='N':assert identity is None
        else:
            expected=next(x for x in read(HERE/'INSTALL_REUSE.json')['rows'] if x['group']==row['group'])
            assert identity==expected['runtime_identity']
            for m in identity['source_files']:
                assert sha(Path(expected['installed_root'])/m['path'])==m['sha256'],m
    assert len(set(sessions))==9
    eq=read(HERE/'SPATIAL_CODE_EQUALITY.json')
    assert eq['different_host_methods']==['correct_arm_axial'] and eq['space_query_modules_identical']
    refs=read(HERE/'EXTERNAL_REVIEW_REFERENCES.json')
    quality=read(Path(refs['BLIND_QUALITY_REVIEW.json']['path']))
    assert sha(Path(refs['BLIND_QUALITY_REVIEW.json']['path']))==refs['BLIND_QUALITY_REVIEW.json']['sha256']
    assert quality['summary']['core_facts_correct_count']==quality['summary']['complete_requested_answer_count']==9
    assert not subprocess.check_output(['git','diff',BASE,'--name-only','--','human_eye_plugin','human_eye_module1_operators','pyproject.toml'],cwd=ROOT,text=True).strip()
    files={}
    for p in sorted(HERE.rglob('*')):
        if not p.is_file() or p.name=='EVIDENCE_INDEX.json':continue
        assert '__pycache__' not in p.parts and p.suffix!='.pyc',p
        files[p.relative_to(ROOT).as_posix()]={'bytes':p.stat().st_size,'sha256':sha(p)}
    value={'schema':'native-plugin-complex-003-evidence-index-v1','passed':True,'base_commit':BASE,
        'model_consumers':9,'helper_no_model_preflights':1,'new_model_calls':0,'new_Blender_runs':0,
        'independent_core_answers_correct':9,'independent_complete_answers':9,'lifecycle_geometry_verified':9,
        'product_changes':0,'files':files,'excluded':['EVIDENCE_INDEX.json (self reference)',
            'previous actual installed venvs remain local, prior wheel/manifest references preserved']}
    (HERE/'EVIDENCE_INDEX.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'passed':True,'files':len(files),'index_sha256':sha(HERE/'EVIDENCE_INDEX.json')}))
if __name__=='__main__':main()

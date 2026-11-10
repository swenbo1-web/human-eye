"""Seal this one completed preparation batch; never launches any consumer."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
SOURCE='7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1'
COMMIT='107641ec19919d56aa843c1949261590fc338148'
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
read=lambda path:json.loads(Path(path).read_bytes())


def save(path,value):
    assert not path.exists(),path
    path.write_text(json.dumps(value,indent=2,ensure_ascii=True)+'\n',encoding='utf8')


def include(path):
    parts=path.relative_to(HERE).parts
    if path.name in ('ARTIFACT_INDEX.json','FREEZE.json') and len(parts)==1:return False
    if '__pycache__' in parts or path.suffix.lower() in ('.pyc','.whl'):return False
    if parts[0]=='installation' and ('.human-eye' in parts or 'source_107641ec' in parts):return False
    if parts[0]=='installation' and path.name in ('01_GIT_TREE.stdout.bin','03_GIT_ARCHIVE.stdout.bin'):return False
    if parts[0]=='installation' and 'bundle' in parts and path.suffix.lower()=='.zip':return False
    if parts[0]=='preflight' and path.name=='input.blend' and 'native' in parts:return False
    return True


def main():
    plan=read(HERE/'PLAN.json')
    assert plan['cycle_id']=='M4-OBSERVATION-BASELINE-001'
    assert plan['fixed_product_commit']==COMMIT and plan['candidate_source_sha256']==SOURCE
    assert plan['current_preparation_consumer_budget']==0
    assert not any((HERE/name).exists() for name in ('GO.json','STARTED.json','RUN_RESULT.json','cells'))
    sequence=plan['sequence'];mapping=read(HERE/'private/ANON_MAP.json')['rows']
    assert len(sequence)==len(mapping)==6
    assert [row['group'] for row in sequence]==['N','P','P','N','N','P']
    assert len({row['anonymous_id'] for row in mapping})==6
    assert all(all(row[key]==slot[key] for key in ('cell','round','task','group'))
               for row,slot in zip(mapping,sequence,strict=True))
    assert sha(HERE/'private/ANON_MAP.json')==plan['private_anonymous_map_sha256']
    for relative,expected in plan['dispatch_input_sha256'].items():
        assert sha(HERE/relative)==expected,relative
    assert plan['tasks']['T1']['snapshot_sha256']==sha(HERE/'preflight/SOURCE_SNAPSHOT.json')
    assert plan['image_count']==1 and plan['new_images']==plan['tool_images']==0
    assert plan['max_session_seconds']==450 and plan['total_cell_seconds']==570
    assert plan['tool_attempts']==32 and plan['physical_RPC_limit']==128
    assert plan['tool_timeout_s']==30 and plan['tool_response_bytes']==1048576 and plan['code_bytes']==262144
    ready=read(HERE/'installation/READY.json')
    assert ready['source_sha256']==SOURCE and ready['commit']==COMMIT and ready['source_count']==137
    assert ready['installed_identity_passed'] and ready['no_default_activation']
    tree=ast.parse((ROOT/'human_eye_plugin/runtime_identity.py').read_bytes())
    values={node.targets[0].id:ast.literal_eval(node.value) for node in tree.body
        if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name)
        and node.targets[0].id in ('BASE_VERSION','IMPLEMENTATION_REVISION','_ROOT_MODULES')}
    names=set(values['_ROOT_MODULES'])|{path.relative_to(ROOT).as_posix()
        for package in ('human_eye_plugin','human_eye_module1_operators')
        for path in (ROOT/package).glob('*.py')}
    manifest=[{'path':name,'sha256':sha(ROOT/name)} for name in sorted(names)]
    material={'base_version':values['BASE_VERSION'],'implementation_revision':values['IMPLEMENTATION_REVISION'],'files':manifest}
    canonical=hashlib.sha256(json.dumps(material,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    assert len(manifest)==137 and canonical==SOURCE
    for row in manifest:assert sha(Path(ready['install_root'])/row['path'])==row['sha256']
    assert sha(ready['entry'])==ready['launcher_sha256']
    cli=read(HERE/'runtime/CLI_IMAGE_CAPABILITY.json')
    assert cli['initial_image_flag_supported'] and cli['auth_mode']=='chatgpt'
    assert sha(cli['cli_path'])==cli['cli_sha256']==plan['CLI_sha256']
    assert read(HERE/'runtime/NO_MODEL_TEST_RESULT.json')['exit_code']==0
    assert read(HERE/'runtime/PREPARED_INPUT.json')['model_consumers']==0
    delivery=read(HERE/'scoring/DELIVERY_CHECK.json')
    assert delivery['passed'] and delivery['all_seven_original_shared_and_copies_verified']
    assert delivery['all_nine_private_original_sources_and_copies_verified']
    replay=read(HERE/'scoring/REFERENCE_REPLAY.json')
    assert replay['passed'] and replay['target_conjunction_unique'] and replay['relations_match_original_exact_certificates']
    post=read(HERE/'preflight/postprocess_01/RESULTS.json')
    assert post['readonly_and_source_pipeline_passed'] and post['main_three_relations_match_independent_truth']
    assert post['nearest_applicable_to_original_source'] is False
    assert post['original_aggregate_passed'] is False and post['original_failure_retained'] is True
    assert post['actual_backend_or_geometry_replays']==post['model_calls']==post['new_images']==post['new_assets']==0
    integrity=read(HERE/'preflight/postprocess_01/FINAL_INTEGRITY.json')
    assert integrity['all_source_pins_unchanged'] and integrity['all_recorded_owned_pids_absent']
    assert integrity['model_calls']==integrity['additional_backend_runs_in_postprocessing']==0
    assert integrity['default_activation_requested'] is False
    for path,row in integrity['original_and_copied_inputs'].items():assert sha(path)==row['expected_sha256']
    decision=read(HERE/'DECISION_A.json')
    assert decision['decision']=='A' and decision['consumers_authorized_now']==0 and decision['formal_GO_still_required']
    assert sha(HERE/'PLAN_REFERENCE.md')==decision['original_plan_reference_sha256']
    assert sha(HERE/'PLAN_DECISION_A_ADDENDUM.md')==decision['saved_addendum_sha256']
    # Old runs are read and hashed, never imported, re-scored or rerun.
    previous=[]
    for relative in ('verification/m1_task_entry_001_eval/formal_run/EXECUTION_ARTIFACT_INDEX.json',
                     'verification/m1_nearest_evidence_001/ARTIFACT_INDEX.json'):
        index=read(ROOT/relative)
        rows=index['files']+index.get('duplicate_input_assets_retained_local_and_in_private_zip',[])
        for row in rows:
            path=ROOT/row['path']
            assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],row['path']
        previous.append({'index':relative,'sha256':sha(ROOT/relative),'unchanged_files':len(rows)})
    assert not subprocess.run(['git','-C',str(ROOT),'diff','--name-only'],check=True,stdout=subprocess.PIPE).stdout
    paths=sorted(path for path in HERE.rglob('*') if path.is_file() and include(path))
    for path in paths:
        if path.suffix=='.py':compile(path.read_bytes(),str(path),'exec',dont_inherit=True)
    files=[{'path':path.relative_to(ROOT).as_posix(),'bytes':path.stat().st_size,'sha256':sha(path)} for path in paths]
    index={'cycle_id':plan['cycle_id'],'file_count':len(files),'bytes':sum(row['bytes'] for row in files),'files':files,
        'exclusion_policy':'Local installed releases, duplicate source archives/wheels, whole-Git-tree dumps, bytecode and two native byte-copy input.blend files are retained locally and not duplicated in Git. Reproducible large build payloads have SHA/byte records in EXCLUDED_LOCAL_BUILD_PAYLOADS.json. Original inputs, private QA sources, failures, raw preflight and their bindings are included.'}
    save(HERE/'ARTIFACT_INDEX.json',index)
    freeze={'cycle_id':plan['cycle_id'],'status':'PREP_READY','formal_GO':False,'model_consumers':0,
        'fixed_product_commit':COMMIT,'source_sha256':SOURCE,'source_count':137,
        'plan_sha256':sha(HERE/'PLAN.json'),'private_anonymous_map_sha256':sha(HERE/'private/ANON_MAP.json'),
        'artifact_index_sha256':sha(HERE/'ARTIFACT_INDEX.json'),'indexed_files':len(files),'indexed_bytes':index['bytes'],
        'root_decision':'A; same original asset/source/real two-tool catalogue',
        'readonly_pipeline_and_main_relation_preflight':True,'nearest_source_supported':False,
        'nearest_refusal':'acquisition_triangle_data_required','original_preflight_aggregate_passed':False,
        'same_raw_postprocess_not_replacement_run':True,'quality_model_results_exist':False,
        'initial_image_provider_receipt':None,'model_image_view_confirmed':None,
        'formal_consumers_planned':6,'repetitions_each_arm':3,'independent_scene_count':1,
        'installed_release_activated_as_default':False,'new_images':0,'new_geometry_assets':0,
        'old_evidence_unchanged':previous,'Agent_Learning_registration':'pending own host-issued binding; no borrowed context',
        'report':'verification/m4_observation_baseline_001/REPORT.md'}
    save(HERE/'FREEZE.json',freeze)
    print(json.dumps(freeze,ensure_ascii=True))


if __name__=='__main__':main()

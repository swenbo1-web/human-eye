import hashlib, io, json, subprocess, sys, traceback
from collections import Counter
from pathlib import Path

WT=Path(r'C:\Users\Administrator\.codex\worktrees\m4-single-pass-acquisition\hefe')
REL='verification/m1_task_entry_001_optimize'
R=WT/REL
OUT=Path(r'D:\hefe\verification\fixes\20261110_m1_task_entry_opt_review')
COMMIT='7411ac7aa9338f17355ffe5cdf4df113ce862aed'
PARENT='b296bae6f6e9f5fddda19f0fd6dc9eadcabee1f3'
ATTEMPT=OUT/('SOURCE_REVIEW_ATTEMPT_%02d.json'%(len(list(OUT.glob('SOURCE_REVIEW_ATTEMPT_*.json')))+1))
def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def exception_record(typ,value,tb):
    save(ATTEMPT,{'status':'reviewer_checker_exception','traceback':''.join(traceback.format_exception(typ,value,tb)),'product_executed':False})
    sys.__excepthook__(typ,value,tb)
sys.excepthook=exception_record
sha=lambda b:hashlib.sha256(b).hexdigest()
H=lambda p:sha(Path(p).read_bytes())
J=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
L=lambda p:J(R/p)
G=lambda *a:subprocess.check_output(['git','-C',str(WT),*a])
errors=[];checks=Counter()
def check(ok,name,path=None):
    checks[name]+=1
    if not ok:errors.append({'check':name,'path':str(path) if path else None})
def blobs(commit,paths):
    p=subprocess.run(['git','-C',str(WT),'cat-file','--batch'],input=''.join(commit+':'+x+'\n' for x in paths).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
    stream=io.BytesIO(p.stdout);values={}
    for name in paths:
        header=stream.readline().split()
        if len(header)!=3 or header[1]!=b'blob':raise ValueError('missing Git blob '+name)
        values[name]=stream.read(int(header[2]));assert stream.read(1)==b'\n'
    return values

index,seal,source=L('ARTIFACT_INDEX.json'),L('CANDIDATE_SEAL.json'),L('SOURCE_REVIEW.json')
check(H(R/'ARTIFACT_INDEX.json')=='eaa81ac99dc265d1a2352cfc341ba67d1a7bbfaea125bec89746e8228150899f','index_pin')
check(H(R/'CANDIDATE_SEAL.json')=='19325e882a2f84e78dfe8be1875cfad8ac74b585d3afd0d72841eaf7ab19b5bc','seal_pin')
head=G('rev-parse','HEAD').decode().strip();status=G('status','--porcelain').decode()
check(head==COMMIT and not status,'fixed_clean_HEAD')
check(G('rev-parse',COMMIT+'^').decode().strip()==PARENT==seal['parent_commit'],'parent_commit')
artifact_paths=[r['path'] for r in index['files']]+[REL+'/ARTIFACT_INDEX.json',REL+'/CANDIDATE_SEAL.json']
git_artifacts=blobs(COMMIT,artifact_paths);total=0
for row in index['files']:
    data=(WT/row['path']).read_bytes();total+=len(data)
    check(len(data)==row['bytes'] and sha(data)==row['sha256'],'artifact_hash_and_bytes',row['path'])
for p,data in git_artifacts.items():check((WT/p).read_bytes()==data,'artifact_Git_blob',p)
tracked=set(G('ls-tree','-r','--name-only',COMMIT,'--',REL).decode().splitlines())
check(tracked==set(artifact_paths),'all_99_committed_members_indexed')
check(len(index['files'])==index['file_count']==seal['artifact_count']==97 and total==index['bytes']==544043,'artifact_count_and_total_bytes')
check(seal['artifact_index_sha256']==H(R/'ARTIFACT_INDEX.json') and seal['report_sha256']==H(R/'REPORT.md'),'seal_internal_pins')

paths=[r['path'] for r in source['candidate_files']]
before,after=blobs(PARENT,paths),blobs(COMMIT,paths)
check(len(paths)==len(set(paths))==137==seal['source_count'],'source_137_count')
for row in source['candidate_files']:check(sha(after[row['path']])==row['sha256'] and (WT/row['path']).read_bytes()==after[row['path']],'candidate_source_manifest_and_checkout',row['path'])
for row in source['baseline_files']:check(sha(before[row['path']])==row['sha256'],'baseline_source_manifest',row['path'])
changed=[p for p in paths if before[p]!=after[p]]
check(changed==seal['product_diff']==source['diff_paths']==['human_eye_plugin/live_spatial_mcp.py'],'only_live_spatial_mcp_changed')
check(sha(after[changed[0]])==seal['product_file_sha256'],'changed_file_pin')
identity=J(WT/'verification/m1_task_entry_001/blender_equivalence_01/EXECUTION_IDENTITY_INITIAL.json')['identity']
def canonical(data):
    return sha(json.dumps({'base_version':identity['base_version'],'implementation_revision':identity['implementation_revision'],'files':[{'path':p,'sha256':sha(data[p])} for p in paths]},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
old_sha,new_sha=canonical(before),canonical(after)
check(new_sha==seal['candidate_source_sha256']==source['candidate_source_sha256']=='0005ab437c8f330ed277bd49133348389fe7222bda3087f16450dce55ec9c05a','candidate_canonical')
check(old_sha==source['baseline_source_sha256']=='347ec4e52b24ff77239c5540caac52cdc6031e3542c0359798f821538ef4e3ea','baseline_canonical')
roots={'offline_01/engine':after,'compare_01/baseline/engine':before,'compare_01/candidate/engine':after,'compare_02/baseline/engine':before,'compare_02/candidate/engine':after}
for rel,data in roots.items():
    root=R/rel
    check({p.relative_to(root).as_posix() for p in root.rglob('*.py')}==set(paths),'physical_engine_membership',rel)
    for p,raw in data.items():check((root/p).read_bytes()==raw,'physical_engine_bytes',rel+'/'+p)
expected_excluded={rel+'/'+p for rel in roots for p in paths}
check(set(index['excluded_local_source_duplicate_files'])==expected_excluded and len(expected_excluded)==685,'exact_685_duplicate_source_exclusions')

# The first-candidate evidence stays byte-bound to its original commit.
old_rel='verification/m1_task_entry_001'
old_paths=G('ls-tree','-r','--name-only',PARENT,'--',old_rel).decode().splitlines()
old_blobs,current_old_blobs=blobs(PARENT,old_paths),blobs(COMMIT,old_paths)
check(len(old_paths)==227,'first_candidate_227_file_denominator')
for p in old_paths:check((WT/p).read_bytes()==old_blobs[p]==current_old_blobs[p],'first_candidate_Git_and_disk_unchanged',p)
check(H(WT/old_rel/'ARTIFACT_INDEX.json')=='f7ab0e8c524491df19163845c242d336269dd92b80f78fc88d39b7c618da39c8' and H(WT/old_rel/'CANDIDATE_SEAL.json')=='ab79463fe3648f30dd988524c27821ae344e8f6378f0d741b4d5103651706094','first_candidate_index_seal_unchanged')

binding=L('REGRESSION_RUNNER_BINDING.json');offline=L('offline_01/EXECUTION_IDENTITY.json');result=L('offline_01/RESULTS.json')
check(binding['files']==offline['manifest']==source['candidate_files'] and binding['source_files']==offline['source_count']==result['source_count']==137,'offline_manifest_binding')
check(binding['candidate_source_sha256']==offline['runtime_source_sha256']==result['runtime_source_sha256']==new_sha,'offline_runtime_source_identity')
check(offline['guard_verify_loaded'] and offline['product_files_unchanged'] and offline['sealed_original_files_unchanged'],'offline_guard_and_preservation_records')
check('human_eye_plugin.live_spatial_mcp' in offline['loaded_product_witnesses'] and all(p in paths for p in offline['loaded_product_witnesses'].values()),'offline_changed_module_witness')
check(offline['test']['sha256']==source['original_14_test_sha256']==H(WT/offline['test']['path'])=='bff257e4e1f762a830b8350a8f067fa265348e1ea54d8282e8ffa41096bcff65' and offline['test']['unchanged'],'original_14_test_bytes_unchanged')
original_runner=(WT/binding['original_runner_path']).read_bytes();new_runner=(WT/binding['runner_path']).read_bytes()
check(sha(original_runner)==binding['original_runner_sha256'] and sha(new_runner)==binding['runner_sha256']==offline['runner_sha256'],'offline_runner_pins')
check(original_runner.replace(sha(before[changed[0]]).encode(),sha(after[changed[0]]).encode(),1)==new_runner,'runner_change_only_product_hash_pin')
check(result['tests']==14 and result['successful'] and not result['failures'] and not result['errors'] and not result['skipped'] and not result['external_operation_attempts'],'recorded_offline_14_pass')

comparison=L('compare_02/RESULTS.json');comparison_rows=[]
check(comparison['baseline_source_sha256']==old_sha and comparison['candidate_source_sha256']==new_sha and comparison['source_count']==137,'compare02_source_pair_identity')
check(comparison['runner_sha256']==H(R/'compare_validation.py'),'compare02_runner_pin')
for phase,expected,data in [('baseline',old_sha,before),('candidate',new_sha,after)]:
    root=R/'compare_02'/phase;rows=J(root/'MANIFEST.json');record=J(root/'RESULTS.json');exit_record=J(root/'EXIT.json')
    check(rows==[{'path':p,'sha256':sha(data[p])} for p in paths],'compare02_phase_manifest',phase)
    check(record['runtime_source_sha256']==expected and record['source_kind']=='unregistered_runtime' and record['guard_verify_loaded'] and record['snapshot_unchanged'] and not record['external_operation_attempts'],'compare02_execution_identity_guard_record',phase)
    check(record['passed'] and len(record['validation'])==24 and len(record['integration'])==5 and record['direct_service']['passed'] and exit_record['returncode']==0,'compare02_phase_completion_record',phase)
    comparison_rows.append({'phase':phase,'runtime_source_sha256':expected,'source_kind':record['source_kind'],'guard_verified_record':record['guard_verify_loaded'],'exit_code_record':exit_record['returncode'],'loaded_module_name_list_recorded':False})
check(comparison['passed'] and len(comparison['comparisons'])==29 and all(x['equal'] for x in comparison['comparisons']),'recorded_compare02_29_pairs_equal')
initial_comparison=L('compare_01/RESULTS.json')
check(initial_comparison['passed'] is False,'first_comparison_failure_preserved')
old_runner_paths=[p for p in R.rglob('*.py') if H(p)==initial_comparison['runner_sha256']]
check(bool(old_runner_paths),'first_comparison_original_runner_retained')
report={'schema_version':1,'status':'passed' if not errors else 'requires_review','candidate_commit':COMMIT,'parent_commit':PARENT,'worktree_HEAD':head,'worktree_clean':not status,'scope':'Limited independent source/seal and archived execution-identity binding; no product imports or tests, Blender, model or process scan. No expansion into prior 004/005 evidence.','artifact_index':{'path':str(R/'ARTIFACT_INDEX.json'),'sha256':H(R/'ARTIFACT_INDEX.json'),'members':97,'member_bytes':total,'Git_blobs_including_index_seal':len(tracked)},'seal':{'path':str(R/'CANDIDATE_SEAL.json'),'sha256':H(R/'CANDIDATE_SEAL.json')},'source':{'count':137,'canonical':new_sha,'baseline_canonical':old_sha,'changed_paths':changed,'unchanged_sources':137-len(changed),'exact_physical_source_copies':685,'first_candidate_files_unchanged':len(old_paths)},'execution_records':{'offline_tests':14,'offline_reported_pass':result['successful'],'offline_loaded_module_witnesses':len(offline['loaded_product_witnesses']),'compare02':comparison_rows,'compare02_paired_rows':29,'first_comparison_failure_and_original_script_retained':True,'identity_scope':'Offline source manifest and module witnesses plus compare02 source identity, manifest, guard and snapshot assertions agree with Git-bound physical engines. Compare02 does not record a per-module name witness list. These are archived execution records, not independent replay.'},'checks_performed':dict(checks),'errors':errors,'not_independently_run':['14-test suite','24 validation/5 integration/1 direct-service checks per version','Product CLI or installed runtime','Performance or model-quality evaluation','Blender or PID scan'],'first_checker_attempt_file':str(ATTEMPT),'reviewer_inspection_note':'Pre-audit schema inspection assumed MANIFEST.json was an object and produced AttributeError; inspection was corrected to its actual list format. No acceptance result existed or was overwritten.','product_execution_count':0,'Blender_execution_count':0,'model_execution_count':0,'worktree_writes':0}
save(ATTEMPT,report)
save(OUT/'SOURCE_REVIEW.json',report)
print(json.dumps({'status':report['status'],'artifacts':97,'artifact_bytes':total,'Git_blobs':len(tracked),'sources':137,'unchanged':137-len(changed),'first_candidate_files_preserved':len(old_paths),'errors':errors,'attempt':str(ATTEMPT),'report':str(OUT/'SOURCE_REVIEW.json')},ensure_ascii=False))

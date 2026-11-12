"""Independent saved-source/installation/closure audit; never imports product code."""
import ast
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import zipfile
from collections import Counter
from datetime import datetime

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OUT=Path(__file__).resolve().parent
B=ROOT/'verification/m2_tight_directory_001'
COMMIT='c0134088796d47a982edfc838aa6704c8e052d57'
PRODUCT='fac9b4373575d653cc96f39f1dcb225300cd5977'
OLD='00b13060a3cbe709b38f6e98ce04a6e5c3dabfb4'
NEW_SHA='6acb3ac7f014a590a279994f44be07c581af53a2da4dafae8dba9cd58eaea0bb'
OLD_SHA='4ebc3910652ee461d9fa7476c8df0ecf6312580d6a02e1066c0eac88bef5c76c'
CHECKS=[]
sha=lambda b:hashlib.sha256(b).hexdigest()
def j(p):return json.loads(Path(p).read_text('utf8'))
def check(name,value,detail=None):CHECKS.append(dict(name=name,passed=bool(value),detail=detail))
def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args])
def archive_hashes(commit,paths):
    raw=git('archive','--format=tar',commit,'--',*paths)
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as a:
        return {m.name:sha(a.extractfile(m).read()) for m in a if m.isfile()}

check('head',git('rev-parse','HEAD').decode().strip()==COMMIT)
check('checkout_clean',not git('status','--porcelain').strip())
index=j(B/'INDEX.json');complete=j(B/'COMPLETE.json')
check('index_sha',sha((B/'INDEX.json').read_bytes())=='bf33b9249869724209adecf9188de7f0f1ee6a33d0f6505a74061dcaada74bcf')
check('index_count',len(index['files'])==index['file_count']==4700)
files={r['path']:r for r in index['files']}
check('unique_index_paths',len(files)==4700)
tracked=archive_hashes(COMMIT,['verification/m2_tight_directory_001'])
for name,r in files.items():
    raw=(ROOT/name).read_bytes()
    check('index_file:'+name,sha(raw)==r['sha256'] and len(raw)==r['bytes'])
    check('git_file:'+name,sha(raw)==tracked.get(name))
for name in ['COMPLETE.json','INDEX.json']:
    rel='verification/m2_tight_directory_001/'+name
    check('git_self:'+name,sha((B/name).read_bytes())==tracked.get(rel))
check('git_evidence_file_count',len(tracked)==4702,len(tracked))
check('index_bytes',sum(r['bytes'] for r in files.values())==index['bytes'])

ready=j(B/'installation/READY.json')
receipt=j(ready['receipt']);install=Path(ready['install_root'])
candidate=j(B/'CANDIDATE_SOURCE.json');baseline=j(B/'BASELINE_SOURCE.json')
expected_changes=set(candidate['changed_files'])
changes=set(git('diff','--name-only',OLD,PRODUCT,'--','human_eye_plugin','human_eye_module1_operators').decode().splitlines())
check('seven_product_changes',changes==expected_changes and len(changes)==7,sorted(changes))
check('no_post_freeze_source_change',not git('diff',PRODUCT,COMMIT,'--',*[r['path'] for r in candidate['manifest']]).strip())
wheel=next((B/'installation/run_01/bundle').glob('*.whl'))
check('wheel_whole_sha',sha(wheel.read_bytes())==ready['wheel_sha256']==receipt['wheel_sha256'])
with zipfile.ZipFile(wheel) as z:
    wh={name:sha(z.read(name)) for name in z.namelist() if not name.endswith('/')}
check('wheel_members',len(wh)==144,len(wh))
source_root=Path(receipt['source_root'])
manifests={}
for label,manifest,commit,identity in [('new',candidate['manifest'],PRODUCT,NEW_SHA),('old',baseline['manifest'],OLD,OLD_SHA)]:
    gh=archive_hashes(commit,[r['path'] for r in manifest]);manifests[label]=gh
    check('source_manifest_count:'+label,len(gh)==len(manifest)==137)
    for r in manifest:
        check('source_git:'+label+':'+r['path'],gh[r['path']]==r['sha256'])
        if label=='new':
            check('source_four_way:'+r['path'],gh[r['path']]==sha((ROOT/r['path']).read_bytes())==sha((source_root/r['path']).read_bytes())==sha((install/r['path']).read_bytes())==wh.get(r['path']))
    data=git('show',commit+':human_eye_plugin/runtime_identity.py')
    values={n.targets[0].id:ast.literal_eval(n.value) for n in ast.parse(data).body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('BASE_VERSION','IMPLEMENTATION_REVISION')}
    computed=sha(json.dumps(dict(base_version=values['BASE_VERSION'],implementation_revision=values['IMPLEMENTATION_REVISION'],files=manifest),sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
    check('canonical_identity:'+label,computed==identity,computed)
for field,name in [('launcher_sha256','target_runtime_entry.py'),('admin_sha256','installed_release.py'),('binding_sha256','RUNTIME_BINDING.json')]:
    check('installed_admin:'+field,sha((Path(ready['release'])/'admin'/name).read_bytes())==receipt[field])
check('no_activation_receipt',receipt['default_activation_changed'] is False and receipt['owned_reference_changed'] is False)
before=j(B/'installation/run_01/PROTECTED_BEFORE.json');after=j(B/'installation/run_01/PROTECTED_AFTER.json')
check('protected_recorded_after',set(after['unchanged'])==set(before) and all(after['unchanged'].values()))
for path,digest in before.items():check('protected_current:'+path,(sha(Path(path).read_bytes()) if Path(path).is_file() else None)==digest)

freeze=j(B/'MEASUREMENT_FREEZE.json');bindings=j(B/'measurement/prepared_02/INPUT_BINDINGS.json')
check('prepared_sha',sha((B/'measurement/prepared_02/INPUT_BINDINGS.json').read_bytes())==freeze['prepared_bindings_sha256'])
check('dispatched_bindings_identical',(B/'measurement/prepared_02/INPUT_BINDINGS.json').read_bytes()==(B/'measurement/run_01/INPUT_BINDINGS.json').read_bytes())
freeze_hashes=archive_hashes(complete['measurement_freeze_commit'],['verification/m2_tight_directory_001'])
for path,digest in bindings['source_files'].items():
    check('dispatch_source:'+path,sha(Path(path).read_bytes())==digest)
    rel=Path(path).relative_to(ROOT).as_posix()
    # Sources outside this batch are still pinned to freeze via git show.
    frozen=freeze_hashes.get(rel) if rel.startswith('verification/m2_tight_directory_001/') else sha(git('show',complete['measurement_freeze_commit']+':'+rel))
    check('prefrozen_dispatch_source:'+path,frozen==digest)
basefreeze=j(B/'measurement/BASELINE_FROZEN.json')
for path,digest in basefreeze['files'].items():check('baseline_pin:'+path,sha((B/'measurement'/path).read_bytes())==digest)
for asset in bindings['assets']:check('asset:'+asset['name'],sha(Path(asset['asset']).read_bytes())==asset['asset_sha256'])
stamp=git('show','-s','--format=%cI',complete['measurement_freeze_commit']).decode().strip()
matrix_process=j(B/'measurement/MATRIX_PROCESS.json')
check('freeze_commit_before_matrix_recorded_utc',datetime.fromisoformat(stamp)<datetime.fromisoformat(matrix_process['started_utc'].replace('Z','+00:00')),[stamp,matrix_process['started_utc']])
results=j(B/'measurement/run_01/RESULTS.json')
check('schedule_identity',results['schedule']==bindings['schedule'])
check('single_fixed_matrix',results['performance_retries']==0 and len(results['cases'])==36 and results['all_planned_dispatched'] and results['passed'])
check('schedule_counts',sum(not c['two_step'] for c in results['schedule'])==27 and sum(c['two_step'] for c in results['schedule'])==9)
check('model_count',bindings['models']==0 and bindings['profiler'] is False)
case_summaries=[];total_business=total_rpc=runtime_count=0
for sched in results['schedule']:
    folder=B/'measurement/run_01'/sched['case_id'];d=j(folder/'RESULTS.json')
    rows=d['rows'];n=len(rows);expected_n=2 if sched['two_step'] else 11
    check('row_count:'+sched['case_id'],n==expected_n)
    total_business+=sum(r['host_RPC'] for r in rows);total_rpc+=len(d['worker_events'])
    close=d['native_close'];closed=d['closed']
    check('blender_exit:'+sched['case_id'],close['exit_code']==0 and close['process_reaped'] and not close['error'] and close['pid']==closed['pid'])
    check('scene_unchanged:'+sched['case_id'],closed['initial_geometry_fingerprint']==closed['final_geometry_fingerprint'] and not closed['poisoned'] and close['source_file_unchanged'] and close['protected_files_unchanged'])
    if sched['lane']!='native' or sched['two_step']:
        identity=j(folder/'ACTUAL_INITIALIZE.json')['result']['_meta']['human_eye'];expected=OLD_SHA if sched['lane']=='old' else NEW_SHA
        check('actual_runtime_identity:'+sched['case_id'],identity['source_sha256']==expected and identity['source_file_count']==137 and identity['source_kind']=='installed_distribution' and identity['identity_check']['compatible'])
        cfg=j(folder/'config.json');check('actual_config:'+sched['case_id'],cfg['expected_identity']['source_sha256']==expected and cfg['observe_on_prompt'] is False)
        proof=j(folder/'PRODUCT_RUNTIME_PROOF.json');exit_=d['product_runtime_exit'];pclose=d['product_close']
        check('runtime_handle_exit:'+sched['case_id'],proof['confirmed'] and proof['runtime_pid']!=proof['launcher_pid'] and exit_['confirmed'] and exit_['exited'] and exit_['exit_code']==0 and exit_['handle_closed'] and pclose['confirmed'] and pclose['exit_code']==0)
        check('runtime_bound_before_business:'+sched['case_id'],proof['proved_ns']<rows[0]['started_ns'])
        runtime_count+=1
    case_summaries.append(dict(case_id=sched['case_id'],rows=n,blender_pid=closed['pid'],runtime_pid=d.get('product_runtime_proof',{}).get('runtime_pid')))
check('denominators',total_business==315 and total_rpc==351 and runtime_count==27,[total_business,total_rpc,runtime_count])

entry1=j(B/'correctness/entry_01/RESULTS.json');entry2=j(B/'correctness/entry_02/RESULTS.json')
check('old_failed_entry_retained',entry1['passed'] is False and entry1['Blender_close']['forced'] is True)
check('fixed_entry_pass_and_exit',entry2['passed'] and entry2['Blender_close']['forced'] is False and entry2['Blender_close']['exit_code']==0)
check('fixed_entry_records',len(entry2['records'])==21 and entry2['source_sha256']==NEW_SHA)
typed=j(B/'correctness/TYPED_SUMMARY.json');check('typed_identity_closure',typed['source_sha256']==NEW_SHA and typed['source_count']==137 and typed['passed'] and typed['close']['exit_code']==0 and typed['close']['reaped'])
failures=[r for r in CHECKS if not r['passed']]
result=dict(audit_scope='independent offline bytes/Git/archive/zip/JSON checks; no product import or live process execution',evidence_commit=COMMIT,product_commit=PRODUCT,source_sha256=NEW_SHA,indexed_files=4700,git_files=4702,source_files=137,wheel_members=len(wh),runtime_sessions=runtime_count,blender_sessions=len(case_summaries),business_rpc=total_business,total_rpc=total_rpc,checks=len(CHECKS),failures=failures,passed=not failures,cases=case_summaries,limitations=['Saved handle/exit records independently cross-checked, not a new live witness of past process exits.','UTC/Git order demonstrates recorded freeze precedes run; does not independently attest every pre-edit author action.','Native all-event real Blender freshness sequence, complete JSON Schema evaluator and same-world replacement live case remain unrun as disclosed.','No new models, Blender sessions, installation or default configuration changes by reviewer.'])
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
(OUT/'CHECKS.json').write_text(json.dumps(CHECKS,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps({k:v for k,v in result.items() if k!='cases'},ensure_ascii=False,indent=2))

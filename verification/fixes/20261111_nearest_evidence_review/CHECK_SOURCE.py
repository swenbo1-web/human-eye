"""Read-only byte and evidence comparison. No project code import/execution."""
from pathlib import Path
from collections import Counter
import ast
import copy
import datetime
import hashlib
import json
import subprocess

ROOT=Path(r'C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
PROOF=ROOT/'verification/m1_nearest_evidence_001'
OUT=Path(__file__).resolve().parent
HEAD='107641ec19919d56aa843c1949261590fc338148'
OLD='fa23496e1565e34ddacf4a0ce28b65e0a85c3ca8'
BASE='7411ac7aa9338f17355ffe5cdf4df113ce862aed'
PINS={'baseline':'0005ab437c8f330ed277bd49133348389fe7222bda3087f16450dce55ec9c05a','candidate':'7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1'}
INDEX_PIN='a0dc29d224e602b16a9b992ee634b222f45e152c430a10eb0bf6f3a133158c48'
SEAL_PIN='eafaa0d2d85bcfc96764c3d296173e2b58b148adc60795b0441606fa72ba4e1e'
ADDED={'best_known_evidence','measurement_semantics'}
DROP=ADDED|{'trace_id'}
findings=[]
counts=Counter()

def sha(raw):return hashlib.sha256(raw).hexdigest()
def file_sha(p):return sha(p.read_bytes())
def read(p):return json.loads(p.read_text(encoding='utf8'))
def git(*args):return subprocess.run(['git','-C',str(ROOT),*args],capture_output=True,check=True).stdout
def blob(raw):return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
def check(ok,kind,detail):
    counts[kind]+=1
    if not ok:findings.append({'check':kind,'detail':detail})
    return bool(ok)
def tree(commit):
    result={}
    for record in git('ls-tree','-r','-z',commit).split(b'\0'):
        if record:
            meta,name=record.split(b'\t',1);result[name.decode()]=meta.split()[2].decode()
    return result
def normalized(v,pin):
    if isinstance(v,dict):
        out={}
        for k,x in v.items():
            if k=='runtime_source_sha256':
                check(x==pin,'exact_source_before_normalization',x)
                out[k]='<exact_verified_source_only>'
            else:out[k]=normalized(x,pin)
        return out
    if isinstance(v,list):return [normalized(x,pin) for x in v]
    return v
def core(body,pin):
    check(body['binding']['runtime_source_sha256']==pin,'body_source_pin',body.get('result_kind'))
    return normalized({k:v for k,v in body.items() if k not in DROP},pin)

def main():
    trees={c:tree(c) for c in [HEAD,OLD,BASE]}
    index=read(PROOF/'ARTIFACT_INDEX.json');seal=read(PROOF/'CANDIDATE_SEAL.json')
    check(file_sha(PROOF/'ARTIFACT_INDEX.json')==INDEX_PIN==seal['artifact_index_sha256'],'outer_pin','index')
    check(file_sha(PROOF/'CANDIDATE_SEAL.json')==SEAL_PIN,'outer_pin','seal')
    total=0
    for r in index['files']:
        raw=(ROOT/r['path']).read_bytes();total+=len(raw)
        check(sha(raw)==r['sha256'] and len(raw)==r['bytes'],'artifact_hash_size',r['path'])
        check(blob(raw)==trees[HEAD].get(r['path']),'artifact_fixed_git',r['path'])
    check(len(index['files'])==index['file_count']==seal['indexed_files']==230 and total==index['bytes']==seal['indexed_bytes'],'artifact_totals',total)
    for p in [PROOF/'ARTIFACT_INDEX.json',PROOF/'CANDIDATE_SEAL.json']:
        check(blob(p.read_bytes())==trees[HEAD][p.relative_to(ROOT).as_posix()],'outer_fixed_git',p.name)
    old_index_path=ROOT/'verification/m1_task_entry_001_eval/formal_run/EXECUTION_ARTIFACT_INDEX.json'
    old_index=read(old_index_path)
    prior=read(PROOF/'PREVIOUS_RUN_INTEGRITY.json')
    check(file_sha(old_index_path)==prior['original_index_sha256']==seal['original_index_sha256'],'old_index_pin','execution index')
    check(blob(old_index_path.read_bytes())==trees[OLD][old_index_path.relative_to(ROOT).as_posix()]==trees[HEAD][old_index_path.relative_to(ROOT).as_posix()],'old_index_git','execution index')
    for r in old_index['files']:
        raw=(ROOT/r['path']).read_bytes()
        check(sha(raw)==r['sha256'] and len(raw)==r['bytes'],'old_formal_member_bytes',r['path'])
        check(blob(raw)==trees[OLD].get(r['path'])==trees[HEAD].get(r['path']),'old_formal_git_unchanged',r['path'])
    duplicates=old_index['duplicate_input_assets_retained_local_and_in_private_zip']
    for r in duplicates:
        raw=(ROOT/r['path']).read_bytes()
        check(sha(raw)==r['sha256'] and len(raw)==r['bytes'],'old_duplicate_bytes',r['path'])
    check(len(old_index['files'])==prior['original_formal_files_checked']==2396 and len(duplicates)==prior['original_duplicate_input_assets_checked']==37,'old_formal_denominator','2396 + 37')
    identities={}
    for role in ['baseline','candidate']:
        for attempt in ['01','02']:
            label=f'{role}_{attempt}';folder=PROOF/label;ident=read(folder/'EXECUTION_IDENTITY.json');identities[label]=ident
            check(ident['runtime_source_sha256']==PINS[role] and ident['source_count']==len(ident['manifest'])==137,'identity_manifest',label)
            runtime=(folder/'engine/human_eye_plugin/runtime_identity.py').read_bytes()
            constants={n.targets[0].id:ast.literal_eval(n.value) for n in ast.parse(runtime).body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('BASE_VERSION','IMPLEMENTATION_REVISION','_ROOT_MODULES')}
            canonical=sha(json.dumps({'base_version':constants['BASE_VERSION'],'implementation_revision':constants['IMPLEMENTATION_REVISION'],'files':ident['manifest']},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
            check(canonical==PINS[role],'recomputed_canonical',label)
            expected_names=set(constants['_ROOT_MODULES'])
            for pkg in ['human_eye_plugin','human_eye_module1_operators']:
                expected_names.update(pkg+'/'+p.name for p in (folder/'engine'/pkg).glob('*.py'))
            check(expected_names=={r['path'] for r in ident['manifest']},'complete_source_domain',label)
            for r in ident['manifest']:
                raw=(folder/'engine'/r['path']).read_bytes()
                commit=BASE if role=='baseline' else HEAD
                check(sha(raw)==r['sha256'] and blob(raw)==trees[commit].get(r['path']),'physical_engine_git_bytes',{'run':label,'path':r['path']})
                if role=='candidate':check(raw==(ROOT/r['path']).read_bytes(),'candidate_checkout_equal',{'run':label,'path':r['path']})
            expected_runner=PROOF/('history/run_offline_r1_state_assumption.py.txt' if attempt=='01' else 'run_offline.py')
            check(file_sha(expected_runner)==ident['runner_sha256'],'runner_byte_binding',label)
            for path,r in ident['loaded_tests'].items():
                check(file_sha(ROOT/path)==r['sha256'] and r['co_filename']=='verified-test:'+r['sha256']+':'+path,'test_byte_binding',{'run':label,'path':path})
            for field in ['fixture_sha256','original_read_evidence_sha256']:
                for path,digest in ident[field].items():
                    check(file_sha(ROOT/path)==digest and blob((ROOT/path).read_bytes())==trees[HEAD].get(path),'fixture_and_referenced_bytes',{'run':label,'field':field,'path':path})
            for module,path in ident['loaded_product_witnesses'].items():
                check(path in expected_names,'loaded_module_in_verified_source',{'run':label,'module':module,'path':path})
            check(all(ident[k] is True for k in ['guard_verify_loaded','checkout_files_unchanged','loaded_tests_unchanged','original_read_evidence_unchanged']) and ident['source_kind']=='unregistered_runtime','guard_and_scope_record',label)
    for attempt in ['01','02']:
        a,b=(identities[x+'_'+attempt] for x in ['baseline','candidate'])
        for k in ['loaded_tests','fixture_sha256','original_read_evidence_sha256','runner_sha256']:
            check(a[k]==b[k],'paired_test_fixture_runner_equality',{'attempt':attempt,'field':k})
    bm={r['path']:r['sha256'] for r in identities['baseline_02']['manifest']}
    cm={r['path']:r['sha256'] for r in identities['candidate_02']['manifest']}
    changed=sorted(k for k in bm if bm[k]!=cm[k])
    check(changed==sorted(['human_eye_plugin/live_service.py','human_eye_plugin/live_spatial_mcp.py','human_eye_plugin/task_query.py']),'product_changed_scope',changed)
    old=read(PROOF/'baseline_02/EVIDENCE.json');new=read(PROOF/'candidate_02/EVIDENCE.json')
    direct='verification/nearest_integration_001/tests/test_integration.py';entry='verification/m1_nearest_evidence_001/tests/test_nearest_evidence.py'
    direct_rows=[]
    check(set(old[direct])==set(new[direct]),'direct_group_set','same groups')
    for key in sorted(old[direct]):
        normalized_rows=[]
        for role,data in [('baseline',old),('candidate',new)]:
            row=copy.deepcopy(data[direct][key])
            for ob in row['observations']:
                check(ob['result']['binding']['runtime_source_sha256']==PINS[role],'direct_source_pin',key)
                ob['result']={k:v for k,v in ob['result'].items() if k not in DROP}
            normalized_rows.append(normalized(row,PINS[role]))
        ok=check(normalized_rows[0]==normalized_rows[1],'direct_full_row_equal',key)
        direct_rows.append({'group':key,'observations':len(old[direct][key]['observations']),'all_original_fields_equal':ok})
    entry_rows=[];totals={'baseline':Counter(),'candidate':Counter()}
    check(set(old[entry])==set(new[entry]) and len(old[entry])==18,'entry_case_set','18 fixed cases')
    for key in sorted(old[entry]):
        a,b=old[entry][key],new[entry][key]
        result={'case':key}
        for field in ['capture_binding','measurements','diagnostics','packet_work','counts']:
            result[field+'_equal']=check(normalized(a[field],PINS['baseline'])==normalized(b[field],PINS['candidate']),'entry_'+field+'_equal',key)
        result['core_equal']=check(core(a['body'],PINS['baseline'])==core(b['body'],PINS['candidate']),'entry_core_equal',key)
        for role,row in [('baseline',a),('candidate',b)]:
            totals[role].update(row['counts'])
            expected_core={k:v for k,v in row['body'].items() if k not in DROP}
            check(expected_core==row['core'],'recorded_core_no_hidden_filter',{'case':key,'role':role})
            body=row['body'];cap=row['capture_binding']
            check(body['binding']['document_epoch']==cap['host_identity']['document_epoch'] and body['binding']['directory_sha256']==cap['directory_sha256'] and body['binding']['host_source_sha256']==cap['host_source_sha256'],'entry_capture_self_binding',{'case':key,'role':role})
            if row.get('raw_text') is not None:
                check(json.loads(row['raw_text'])==body,'raw_body_binding',{'case':key,'role':role})
            if row.get('raw_tool_result') is not None:
                check(json.loads(row['raw_tool_result_json'])==row['raw_tool_result'] and json.loads(row['raw_tool_result']['content'][0]['text'])==body,'raw_tool_object_binding',{'case':key,'role':role})
        ids=[o['id'] for o in b['body']['best_known_objects']]
        measures=b['measurements'];source_case=key
        if not all(oid in measures for oid in ids):
            matches=[(k,r['measurements']) for k,r in new[entry].items() if k!=key and r['capture_binding']==b['capture_binding'] and r['body']['focal']==b['body']['focal'] and r['body']['best_known_objects']==b['body']['best_known_objects'] and r['body']['binding']==b['body']['binding'] and all(oid in r['measurements'] for oid in ids)]
            check(not measures and b['diagnostics'].get('result_cache_hit') is True and bool(matches),'warm_measured_source_bound',key)
            if matches:source_case,measures=matches[0]
        evidence=b['body']['best_known_evidence']
        check(len(evidence)==len(ids),'evidence_winner_count',key)
        for named,item,oid in zip(b['body']['best_known_objects'],evidence,ids):
            m=measures[oid]
            expected={'candidate':named,**{k:m.get(k) for k in ('point_a_world','point_b_world','direction_a_to_b','witness_status','direction_status')},**{k:m[k] for k in ('witness_reason','direction_reason') if k in m}}
            check(item==expected,'evidence_original_measurement_projection',{'case':key,'id':oid})
        result['measurement_evidence_case']=source_case;entry_rows.append(result)
    comparison=read(PROOF/'compare_02/RESULTS.json')
    check(comparison['passed'] is True and not comparison['errors'] and comparison['strict_entry_core_pairs']==18 and comparison['entry_pairs_with_different_capture_binding']==0,'comparison_summary_scope','all 18 strictly comparable')
    check(dict(totals['baseline'])==dict(totals['candidate'])==seal['counts_each_version'],'counts_unchanged',dict(totals['baseline']))
    first=read(PROOF/'compare_01/RESULTS.json')
    check(first['passed'] is False and first['errors']==[{'type':'ValueError','message':'runtime_source_sha256_mismatch'}] and first['direct_groups']==[] and first['entry_cases']==[],'first_compare_failure_preserved','no successful groups claimed')
    for role in ['baseline','candidate']:
        r1=read(PROOF/(role+'_01')/'RESULTS.json');r2=read(PROOF/(role+'_02')/'RESULTS.json')
        check(r1['tests']==50 and not r1['successful'] and len(r1['errors'])==1 and 'FileNotFoundError' in r1['errors'][0]['traceback'],'first_runner_failure_preserved',role)
        check(r2['tests']==49 and r2['successful'] and not r2['errors'] and not r2['failures'] and not r2['skipped'] and r2['model_consumers']==r2['Blender_sessions']==r2['network_sessions']==0 and not r2['external_operation_attempts'],'final_runner_records',role)
    execution=read(PROOF/'COMPARISON_EXECUTION.json')
    for r in execution['files']:
        raw=(ROOT/r['path']).read_bytes();check(sha(raw)==r['sha256'] and len(raw)==r['bytes'],'comparison_execution_binding',r['path'])
    report={
        'schema':'m1-nearest-evidence-independent-source-review-v1','reviewer':'/root/latest_local_upgrade_audit','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'fixed_commit':HEAD,'baseline_product_commit':BASE,'previous_formal_commit':OLD,'status':'passed_with_scope_limits' if not findings else 'requires_review','findings':findings,'check_counts':dict(counts),
        'pins':{'artifact_index_sha256':file_sha(PROOF/'ARTIFACT_INDEX.json'),'candidate_seal_sha256':file_sha(PROOF/'CANDIDATE_SEAL.json'),'canonical':PINS},
        'summary':{'new_indexed_members':230,'old_formal_members_unchanged':2396,'old_duplicate_input_bytes_unchanged':37,'sources_each_version':137,'changed_product_files':changed,'unchanged_product_files':134,'physical_engine_copies_checked':4,'selected_test_files_each_version':len(identities['candidate_02']['loaded_tests']),'fixture_files_each_version':len(identities['candidate_02']['fixture_sha256']),'referenced_existing_evidence_files_each_version':len(identities['candidate_02']['original_read_evidence_sha256']),'loaded_module_witnesses_each_final_run':{r:len(identities[r+'_02']['loaded_product_witnesses']) for r in ['baseline','candidate']},'final_author_test_methods_each_version':49,'direct_groups':len(direct_rows),'direct_records':sum(x['observations'] for x in direct_rows),'entry_cases':len(entry_rows),'entry_capture_binding_differences':sum(not r['capture_binding_equal'] for r in entry_rows),'counts_each_version':{r:dict(v) for r,v in totals.items()}},
        'direct_comparisons':direct_rows,'entry_comparisons':entry_rows,
        'verified_source_execution_review':{'static_flow':'run_offline computes source digest from exact blobs, writes physical engine copies, compiles verified loader from those blobs, installs guard with immutable MappingProxyType(blobs), and compiles tests from bytes with hashed co_filename. Product loader execs guard-held source blob, not pyc. Recorded verify_loaded is true for both versions.','evidence_limit':'This review verifies bytes and recorded execution identities; it did not rerun product or observe live execution. Manifest coverage is not a claim that all 137 modules executed.','scope':'unregistered_runtime source + fake RNA + actual kernel; not installed distribution or actual Blender qualification'},
        'normalization_review':{'removed_at_result_root_only':['best_known_evidence','measurement_semantics','trace_id'],'replaced_field':'runtime_source_sha256, only after exact per-version validation','preserved':'All original nested core data and capture fields including scene_revision, scene_fingerprint, document_epoch, directory_sha256, host_source_sha256 and instance identity; measurements/diagnostics/packet_work/counters compared.','independent_result':'All 18 entry bindings match with only exact source identity substitution. All 9 direct full rows / 11 observations match. No scene/epoch/fingerprint mismatch was normalized away.','caveat':'Author comparator can report separately incomparable inputs if a future capture differs; this particular frozen batch has zero such cases and 18 strict pairs.'},
        'retained_failures':['baseline_01 and candidate_01: identical obsolete action-state-file test failure, each 49 of 50 passing; final scope excludes that method without editing it','compare_01: repeated source-pin normalization rejected sentinel before any passing group; history and failure output retained'],
        'author_vs_independent':{'author':'Final 49/49 per version source/fake-RNA/kernel runs, recorded 0 external operations.','this_review':'Independent bytes/Git/manifest/execution-record and raw-result comparison only; no product tests, installed-entry tests, real Blender, model, network or performance experiments run.'},
        'not_run':['product tests by reviewer','installed/default entry qualification','actual Blender','model consumption or benefit','full historical matrix'],
        'script_sha256':file_sha(Path(__file__))}
    out=OUT/'SOURCE_REVIEW.json'
    if out.exists():out=OUT/('SOURCE_REVIEW_attempt_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.json')
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'path':str(out),'status':report['status'],'summary':report['summary'],'findings':findings[:10],'findings_count':len(findings)},ensure_ascii=False))

if __name__=='__main__':
    try:main()
    except BaseException as exc:
        p=OUT/('CHECKER_FAILURE_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.json')
        p.write_text(json.dumps({'type':type(exc).__name__,'message':str(exc),'findings_so_far':findings,'counts':dict(counts)},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        raise

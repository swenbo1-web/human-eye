"""Read-only hash/Git/saved-output review; never imports or runs tested code."""
from pathlib import Path
from collections import Counter
import hashlib,json,subprocess

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe')
N=ROOT/'verification/m4_complete_witness_score_fix_001'
OLD=ROOT/'verification/m4_complete_witness_consumption_001'
RUNTIME=Path('D:/he_complete_witness_001')
OUT=Path(__file__).resolve().parent
HEAD='b0e2fcfe90b7b535105e24dff9c34b36c27a26af'
BASE='8baad59ac6da01f14e1eb87c3e1f4f0687eb2b7d'
inputs={}; checks=[]

def data(p):
    p=Path(p); b=p.read_bytes()
    inputs[str(p.resolve())]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
    return b

def read(p): return json.loads(data(p))
def sha(p): data(p);return inputs[str(Path(p).resolve())]['sha256']
def check(group,name,ok): checks.append({'group':group,'name':name,'passed':bool(ok)})
def git(*args,stdin=None): return subprocess.check_output(['git',*args],cwd=ROOT,input=stdin)
def save(name,d):
    with (OUT/name).open('x',encoding='utf8',newline='\n') as f:json.dump(d,f,ensure_ascii=False,indent=2);f.write('\n')

manifest=read(N/'CONTENT_MANIFEST.json'); frozen=read(N/'FROZEN.json')
check('git','HEAD',git('rev-parse','HEAD').decode().strip()==HEAD)
check('git','clean',not git('status','--porcelain'))
paths={r['path'] for r in manifest['files']}|{'verification/m4_complete_witness_score_fix_001/CONTENT_MANIFEST.json'}
changed={p.decode() for p in git('diff','--name-only','-z',BASE,HEAD).split(b'\0') if p}
check('git','exact_changed_182',paths==changed and len(paths)==182)
check('git','new_namespace_only',all(p.startswith('verification/m4_complete_witness_score_fix_001/') for p in paths))
check('git','actual_new_namespace_set',paths=={p.relative_to(ROOT).as_posix() for p in N.rglob('*') if p.is_file()})
for row in manifest['files']:
    p=ROOT/row['path']; b=data(p)
    check('manifest',row['path'],len(b)==row['bytes'] and sha(p)==row['sha256'])
ordered=sorted(paths)
bloboutput=git('cat-file','--batch',stdin=('\n'.join(HEAD+':'+p for p in ordered)+'\n').encode())
position=0
for p in ordered:
    end=bloboutput.index(b'\n',position);header=bloboutput[position:end].split();size=int(header[2]);position=end+1
    b=bloboutput[position:position+size];position+=size+1
    check('git_blob',p,header[1]==b'blob' and b==data(ROOT/p))
check('git','batch_consumed_exactly',position==len(bloboutput))
check('freeze','count2524',len(frozen['files_sha256'])==2524)
for p,h in frozen['files_sha256'].items():check('freeze',p,sha(p)==h)
snap_before=read(N/'regression_01/ORIGINALS_BEFORE.json');snap_after=read(N/'regression_01/ORIGINALS_AFTER.json')
check('snapshots','before_equals_after',snap_before==snap_after and len(snap_before)==338)
current={str(p.resolve()) for root in (OLD,RUNTIME) for p in root.rglob('*') if p.is_file()}
check('snapshots','actual_set',set(snap_before)==current)
for p,h in snap_before.items():check('protected_file',p,sha(p)==h)
baseline=read(N/'BASELINE.json');audit=read(N/'FINAL_AUDIT.json')
for row in baseline['fixed_originals']:
    check('original_pin',row['path'],sha(row['path'])==row['sha256'] and len(data(row['path']))==row['bytes'])
for p,h in audit['registered_inputs_sha256'].items():check('audit_input',p,sha(p)==h)
for p,h in audit['actual_outputs_sha256'].items():check('audit_output',p,sha(p)==h)
provenance=read(N/'fixtures/PROVENANCE.json')
for row in provenance['files']:
    check('fixture',row['fixture_path'],data(row['fixture_path'])==data(row['source_path']) and sha(row['source_path'])==row['sha256'])
old_quality=read(OLD/'admin/QUALITY.json')
check('historical','quality_original_failure',sha(OLD/'admin/QUALITY.json')=='272f925f1f46b4140b7483fbeceb1ff0a2b58285d3b5c9cab6c417cbb6cb3a87' and old_quality['final_quality_passed'] is False and old_quality['direct_product_adoption'] is None)
check('historical','normalized_unchanged',sha(OLD/'admin/NORMALIZED.json')=='7bb03e3df6a52fa158b689b00c0ce32d5cabe7edf8fb2ad8df2fee26f5f1ef33')
check('historical','quality_seal_unchanged',sha(OLD/'admin/QUALITY_SEAL.json')=='93b0dde406a185bdb60c7921eb1f7d3f697e45e493763130d304828fdfdd30d9')
reg=read(N/'REGISTRY.json');result=read(N/'regression_01/RESULT.json');positive=read(N/'POSITIVE_RUN.json');quality=read(N/'SUPPLEMENTARY_QUALITY.json')
check('positive','real_main_no_overlay',positive['scorer_entry']=='main' and positive['read_overlay'] is False and positive['exit_code']==0 and positive['blocked_side_effects']==[])
check('positive','same_output',positive['output_sha256']==sha(N/'SUPPLEMENTARY_QUALITY.json'))
check('positive','33_contents_direct_false',len(quality['checks'])==33 and all(x['passed'] for x in quality['checks']) and quality['final_quality_passed'] is True and quality['direct_product_adoption'] is False and quality['correct_with_supplement_or_recomputation'] is True)
counts=Counter(x['kind'] for x in reg['cases'])
check('denominator','registered21',counts=={'positive':1,'terminal':18,'content':2})
check('denominator','run21',result['logical_case_denominator']==result['logical_cases_run']==result['passed_cases']==result['fullscore_calls']==21 and result['unrun_cases']==[])
check('denominator','reader21_separate',result['terminal_reader_calls']==21)
check('denominator','23_score_entries',result['total_harness_score_invocations']==22 and result['root_independent_positive_calls']==1 and audit['offline_score_entry_invocations']==23)
check('guard','no_blocked_events',result['blocked_side_effects']==[] and result['new_model_product_Blender_raster_network_calls']==0)
check('saved_set','one_regression_folder',len([p for p in N.glob('regression_*') if p.is_dir()])==1)
case_outcomes={r['id']:r for r in result['outcomes']}
for case in reg['cases']:
    folder=N/'regression_01'/case['id']
    actual=read(folder/'RESULT.json');score=read(folder/'FULL_SCORE.json');terminal=read(folder/'TERMINAL.json');overlay=read(folder/'READ_OVERLAY.json')
    check('case_result',case['id'],actual==case_outcomes[case['id']] and actual['passed'] is True)
    check('case_binding',case['id'],read(folder/'CONTROL.json')==case and terminal==score['terminal_binding'] and terminal['failed_fields']==case['expected_terminal_failed_fields'])
    if case['kind']=='positive':expected=True; errs=[]
    elif case['kind']=='terminal':expected=False;errs=case['expected_terminal_failed_fields']
    else:expected=False;errs=case['expected_content_errors']
    check('case_quality',case['id'],score['final_quality_passed'] is expected and set(score['errors'])==set(errs) and actual['scorer_exit_code']==(0 if expected else 1))
    check('case_overlay',case['id'],overlay['artificial_control'] is (case['kind']!='positive') and {r['target'] for r in overlay['read_intercepts']}=={'run','consumer','normalized'})
    check('case_stderr',case['id'],data(folder/'SCORER_STDERR.txt')==b'')
aux=read(N/'regression_01/AUX_exclusive_output/RESULT.json')
check('auxiliary','expected_existing_file_not_overwritten',aux['passed'] is True and aux['observed_error']['type']=='FileExistsError' and aux['before_sha256']==aux['after_sha256']==sha(N/'regression_01/AUX_exclusive_output/FULL_SCORE.json') and aux['score_invocations']==1)
check('auxiliary','reported_same_aux',all(result['output_protection_auxiliary'].get(k)==v for k,v in aux.items()))
for row in reg['source_pins']:check('registry_pin',row['path'],sha(row['path'])==row['sha256'])
data(N/'regression.py');data(N/'REPORT.md');data(N/'score_saved.py');data(N/'terminal_reader.py')
failures=[x for x in checks if not x['passed']]
groups={g:{'checks':sum(x['group']==g for x in checks),'failed':sum(x['group']==g and not x['passed'] for x in checks)} for g in sorted({x['group'] for x in checks})}
save('RESULT.json',{'method':'Independent original-byte, Git blob and saved output review. No scorer/producer execution or imports.', 'fixed_git':HEAD,'new_product_model_Blender_raster_network_calls':0,'identity_counts':{'new_paths':len(paths),'freeze':len(frozen['files_sha256']),'protected_before_after_current':len(snap_before),'fixtures':2},'offline_score_entries':23,'same_original_model_samples':1,'new_model_samples':0,'main_cases':dict(counts),'checks':len(checks),'passed':len(checks)-len(failures),'failures':failures,'groups':groups,'all_passed':not failures,'details':checks})
save('INPUTS.json',{'inputs':inputs})
print(json.dumps({'checks':len(checks),'failures':failures,'groups':groups}))

"""Independent standard-library audit; no product/scorer/Blender execution."""
import collections
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import zipfile

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
P=ROOT/'verification/scale_opt_001'
D=ROOT/'verification/scale_diag_001'
COMMIT='df016079b0265ee327f884c90dd4815c392016b6'
load=lambda p:json.loads(Path(p).read_bytes())
sha=lambda b:hashlib.sha256(b).hexdigest()
hashfile=lambda p:sha(Path(p).read_bytes())
canonical=lambda v:json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()

assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==COMMIT
seal=load(P/'SEAL.json');tree={}
for line in subprocess.check_output(['git','ls-tree','-r',COMMIT,'--','verification/scale_opt_001'],cwd=ROOT,text=True).splitlines():
    meta,name=line.split('\t');tree[name]=meta.split()[2]
assert len(tree)==seal['file_count']+1==1204
for name in list(seal['files'])+['SEAL.json']:
    data=(P/name).read_bytes()
    if name!='SEAL.json':assert sha(data)==seal['files'][name],name
    assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==tree['verification/scale_opt_001/'+name],name
freeze=load(P/'FREEZE.json');inst=load(P/'INSTALLS.json')
for mapping in (freeze['files_sha256'],freeze['same_fixtures_and_oracle']):
    for path,digest in mapping.items():assert hashfile(path)==digest,path
installed={};wheel_count=0
for group,version in inst['versions'].items():
    identity=version['identity'];files=identity['source_files'];assert len(files)==len({f['path'] for f in files})==137
    actual=[{'path':f['path'],'sha256':hashfile(Path(version['installed_root'])/f['path'])} for f in files]
    assert actual==files
    digest=sha(canonical({'base_version':identity['base_version'],'implementation_revision':identity['implementation_revision'],'files':actual}))
    assert digest==version['source_sha256']==identity['source_sha256']==freeze['versions'][group]
    assert version['proof']['numpy_version']=='2.3.5' and version['proof']['pillow_version']=='12.3.0'
    installed[group]={'canonical':digest,'source_count':137}
    if group=='C':
        assert hashfile(version['wheel'])==version['wheel_sha256']
        with zipfile.ZipFile(version['wheel']) as wheel:
            for f in files:
                data=wheel.read(f['path']);assert sha(data)==f['sha256']
                assert data==(Path(version['source_root'])/f['path']).read_bytes()==(ROOT/f['path']).read_bytes();wheel_count+=1
oldfiles={f['path']:f['sha256'] for f in inst['versions']['O']['identity']['source_files']}
newfiles={f['path']:f['sha256'] for f in inst['versions']['C']['identity']['source_files']}
assert [p for p in oldfiles if oldfiles[p]!=newfiles[p]]==['human_eye_plugin/surface_proximity.py']

fixtures={p.stem:load(p) for p in (D/'fixtures').glob('*.json') if p.stem!='BUILD_COMPLETE'}
oracles={s['id']:s for s in load(D/'ORACLE.json')['snapshots']}
plan=load(P/'measurements/PLAN.json');runs=load(P/'measurements/RUNS.json')
assert plan['chains']==freeze['order'] and len(runs)==18
static=[('G_low','G60_D12','G'),('G_mid','G508','G'),('G_high','G4092','G'),('D_low','G60_D12','D'),('D_mid','D48','D'),('D_high','D192','D')]
expected=[(c+'_'+g,s,m,g,3) for c,s,m in static for g in ('O','C')]+[('T_round_%d_%s'%(i,g),'D48','T',g,7) for i in range(3) for g in ('O','C')]
assert {p[0] for p in expected}=={r['cell']+'_'+r['group'] for r in runs}
counts=collections.Counter();raws={};facts={};work={};states=0;max_error=0;physical=0
times={name:{g:[] for g in ('O','C')} for name in ('original','wrapper','process')}
for name,sid,mode,group,n in expected:
    folder=P/'measurements'/name;chain=load(folder/'CHAIN.json');identity=load(folder/'IDENTITY.json')
    assert identity['source_files']==inst['versions'][group]['identity']['source_files'] and identity['source_sha256']==freeze['versions'][group]
    assert chain['error'] is None and chain['logical_unexecuted']==0 and chain['rows']==n
    assert chain['close']['process_reaped'] is True and chain['file_unchanged'] is True
    assert len(list(folder.glob('MEASUREMENT_*.json')))==n
    def state_check(stem,fixture):
        global states
        actual=load(folder/(stem+'.json'));receipt=load(folder/(stem+'_RECEIPT.json'))['response']['result']
        assert actual=={k:fixture[k] for k in ('unit_scale_m','objects')}
        assert receipt['executed'] is True and json.loads(receipt['result'])==actual;states+=1
    state_check('INITIAL',fixtures[sid])
    run=next(r for r in runs if r['cell']+'_'+r['group']==name)
    assert run['full_process_ns']>=chain['driver_whole_chain_ns']>=chain['whole_chain_ns']
    if mode=='T':
        for field,value in [('original',chain['whole_chain_ns']),('wrapper',chain['driver_whole_chain_ns']),('process',run['full_process_ns'])]:times[field][group].append(value/1e9)
    for index in range(n):
        row=load(folder/('MEASUREMENT_%d.json'%index));assert row['exception'] is None
        assert row['group']==group and row['repeat_or_step']==index and row['canonical']==freeze['versions'][group]
        fixture=fixtures['T'+str(index)] if mode=='T' else fixtures[sid];truth=oracles[fixture['id']]
        answer=json.loads(row['result']['result']['content'][0]['text']);key=(name.rsplit('_',1)[0],group,index);raws[key]=row
        if mode=='T':state_check('STATE_'+str(index),fixture)
        if answer['status']=='expired':
            assert name=='D_high_'+group;counts[(group,'expired')]+=1;continue
        binding=answer['context'] if mode=='G' else answer['binding']
        assert binding['runtime_source_sha256']==freeze['versions'][group] and answer['execution_authority'] is False
        if mode=='G':
            assert len(answer['candidates'])==1;c=answer['candidates'][0];surface=c['surface_proximity'];solid=c['closed_solid_relation']
            certificate=next(p for p in truth['pairs'] if p['candidate']=='peer')
            facts[key]={k:answer.get(k) for k in ('status','sets','coverage','measurement_contracts')}|{'candidate':{k:v for k,v in c.items() if k not in ('object_id','instance_id')}}
            if surface['status']!='measured' or solid['status']!='measured':
                assert surface['reason']=='surface_geometry_work_limit' and solid['reason']=='closed_solid_geometry_work_limit' and answer['status']=='unknown'
                counts[(group,'unknown')]+=1;value=None
            else:
                assert c['name']=='Peer_000' and solid['value']=='separated' and certificate['relation_qualified'];value=surface['value']['distance_m']
        else:
            certificate=truth['global_nearest_unsigned'];assert certificate['complete']
            nameids={o['name']:o['logical_id'] for o in fixture['objects']}
            assert sorted(nameids[o['name']] for o in answer['nearest_objects'])==certificate['nearest_ids']
            coverage=answer['coverage'];assert coverage['unresolved']==0 and answer['unresolved']==[]
            assert coverage['distance_valid']+coverage['strictly_excluded']==coverage['targets_excluding_focal']==len(fixture['objects'])-1
            value=answer['distance_m']
            facts[key]={k:answer.get(k) for k in ('result_kind','status','distance_m','best_known_distance_m','unit','coverage','measurement_notes','unresolved')}|{field:[{'name':o['name']} for o in answer[field]] for field in ('nearest_objects','best_known_objects')}
        if value is not None:
            error=max(abs(value-certificate['distance_lower_m']),abs(value-certificate['distance_upper_m']))
            assert math.isfinite(value) and error<=freeze['accuracy_m'];max_error=max(max_error,error);counts[(group,'correct')]+=1
        assert row['meter']['issues']==[]
        work[key]=[{k:v for k,v in item.items() if k!='object_ids'} for item in row['meter']['details'].get('kernels',[])]
    physical+=sum(bool(line) for line in (folder/'native/WORKER_EVENTS.jsonl').read_text().splitlines())
assert len(raws)==78 and states==60 and physical==192
comparisons=0
for cell,group,index in facts:
    if group!='O':continue
    assert facts[(cell,'O',index)]==facts[(cell,'C',index)],('facts',cell,index)
    assert work[(cell,'O',index)]==work[(cell,'C',index)],('kernel_records',cell,index)
    comparisons+=1
assert comparisons==36
cold={g:raws[('D_mid',g,0)]['entry_ns']/1e9 for g in ('O','C')}
medians={g:statistics.median(times['original'][g]) for g in ('O','C')}
reductions={'D48_cold':1-cold['C']/cold['O'],'T_chain_median':1-medians['C']/medians['O']}
assert min(reductions.values())>=.25
summary=load(P/'SUMMARY.json')
for key,value in reductions.items():assert math.isclose(value,summary['targets'][key]['reduction'],abs_tol=1e-14)
old=load(P/'REGRESSIONS_BASELINE.json');new=load(P/'REGRESSIONS_CANDIDATE.json')
assert old['tests_run']==new['tests_run']==193 and old['failures']==new['failures']==2
assert old['failure_ids']==new['failure_ids'] and not new['successful']
for name in ('REGRESSIONS_BASELINE.txt','REGRESSIONS_CANDIDATE.txt'):
    log=(P/name).read_text();assert 'Ran 193 tests' in log and 'FAILED (failures=2)' in log
contract=load(P/'CURRENT_CONTRACT_REGRESSIONS.json')
assert contract['tests_run']==contract['tests_passed']==24 and not contract['runner_completed'] and not contract['post_test_global_audit_passed']
for group in contract['groups']:assert hashfile(P/group['log'])==group['log_sha256']
result={'review':'Independent raw quality, cost and source binding','commit':COMMIT,'verdict':'supports four-line candidate acceptance and separately verified local upgrade','blockers':[],
    'installed':installed,'wheel_source_installed_runtime_files':wheel_count,'seal_members':len(seal['files']),'git_blobs_verified':len(tree),'seal_sha256':hashfile(P/'SEAL.json'),
    'shared_inputs_rechecked':len(freeze['same_fixtures_and_oracle']),'logical_rows':78,'chains':18,'states_and_receipts':states,'worker_request_events':physical,
    'outcomes':{g:{status:n for (gg,status),n in counts.items() if gg==g} for g in ('O','C')},'comparable_pairs_facts_and_full_kernel_records_equal':comparisons,
    'max_success_error_m':max_error,'D48_cold_s':cold,'T_chain_s':times,'T_original_medians_s':medians,'reductions':reductions,
    'D192_candidate_first_success_paid_entry_s':(raws[('D_high','C',0)]['entry_ns']+raws[('D_high','C',1)]['entry_ns'])/1e9,
    'legacy_failures_preserved':new['failure_ids'],'current_contract':{'tests_passed':24,'post_test_audit_passed':False,'error':contract['post_test_audit_error']['message']},
    'reviewer_runtime_tests':0,'producer_scorer_imports':0,'oracle_math':'own earlier 599-pair independent audit reused; frozen source hashes rechecked',
    'checker_sha256':hashfile(__file__),'checker_first_inline_attempt':'failed on missing warm kernels key; corrected to empty records, no product execution',
    'limits':['One D48 cold pair and three T repeats, not p95 or whole-domain/LLM gain','G508/G4092 remain unknown; D192 cold still expires, two warm successes follow paid partial computation','Two unchanged failures among 193; 24 contract tests pass but post-test source-guard audit fails','Does not attest final desktop/Hook upgrade','Child assignment still old504/current=false; parent507 observed, no borrowed handle or task writes']}
out=Path(__file__).with_name('ROOT_QUALITY_REVIEW.json');assert not out.exists(),'do not overwrite existing result'
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'out':str(out),'outcomes':result['outcomes'],'reductions':reductions,'comparable_pairs':comparisons,'seal_members':len(seal['files']),'passed':True}))

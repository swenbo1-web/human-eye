import hashlib,json,statistics,subprocess,zipfile
from pathlib import Path
WT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B=WT/'verification/m4_local_relation_consumption_001'
OUT=Path(__file__).parent
COMMIT='06d1b4b4cadd880884a0a3c0927a3095ea761f30'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_bytes())
assert sha(Path('D:/hefe/verification/fixes/20261111_m4_local_consumption_quality_review/QUALITY_SEAL.json'))=='efdee7dbf1bb4230c465afdaeb77f82b2266a8e7ef209c52c4323d3f83d5d2b0'
index=read(B/'FORMAL_EXECUTION_INDEX.json')
expected={r['path']:r['sha256'] for r in index['files']}
for name in ['FORMAL_EXECUTION_INDEX.json','FORMAL_QUALITY_READY.json']:
 expected[(B/name).relative_to(WT).as_posix()]=sha(B/name)
tracked=subprocess.check_output(['git','-C',str(WT),'ls-tree','-r','--name-only',COMMIT,'--',B.relative_to(WT).as_posix()],text=True).splitlines()
assert set(tracked)==set(expected)
raw=subprocess.run(['git','-C',str(WT),'cat-file','--batch'],input=''.join(COMMIT+':'+p+'\n' for p in expected).encode(),capture_output=True,check=True).stdout
pos=0
for path,digest in expected.items():
 end=raw.index(b'\n',pos);header=raw[pos:end].split();assert header[1]==b'blob'
 size=int(header[2]);pos=end+1;value=raw[pos:pos+size];pos+=size;assert raw[pos:pos+1]==b'\n';pos+=1
 assert hashlib.sha256(value).hexdigest()==digest and value==(WT/path).read_bytes(),path
assert pos==len(raw)
changes=subprocess.check_output(['git','-C',str(WT),'diff','--name-only','db4ec4c4e0fa3cbf44a8f57fb3f4826730432e81',COMMIT],text=True).splitlines()
assert all(p.startswith('verification/m4_local_relation_consumption_001/') for p in changes)
plan=read(B/'PLAN.json')
for path,digest in plan['dispatch_input_sha256'].items():assert sha(B/path)==digest,path
assert sha(B/'GO.json')=='adc9fbbddb82104ff151d5feb89f3fc8f44383dac173158b422b4c32eef1d9bc'
prov=read(B/'quality_handoff/handoff_01/private/PROVENANCE.json')
archived=0
for row in prov['answers']:
 cell=B/'cells'/row['mapping']['cell']
 for path,digest in row['source_files_sha256'].items():assert sha(cell/path)==digest;archived+=1
run=read(B/'RUN_RESULT.json');records=run['records'];assert len(records)==9 and run['started_cells']==9 and run['stop'] is None
rows=[]
for r in records:
 c=r['consumer'];f=r['finish'];close=f['close'];u=c['usage']
 assert c==read(B/'cells'/r['cell']/'CONSUMER.json')
 assert r['full_cell_wall_ns']==r['cell_ended_ns']-r['cell_started_ns']
 assert not r['errors'] and not c['errors'] and not close['errors']
 assert c['status']=='completed' and f['confirmed'] and close['confirmed']
 assert close['asset_unchanged'] and close['geometry_unchanged'] and close['native_close']['process_reaped']
 assert close['native_close']['original_deadline_ns']==r['worker_deadline_ns']==r['cell_started_ns']+570_000_000_000
 if close['plugin_close']:assert close['plugin_close']['process_reaped']
 rows.append({'cell':r['cell'],'group':r['group'],'round':r['round'],'full_s':r['full_cell_wall_ns']/1e9,'prompt_to_final_s':(c['final_received_ns']-c['prompt_submitted_ns'])/1e9,'tool_calls':close['tool_attempts'],'response_bytes':sum(t['response_bytes'] for t in close['tools']),'owner_tool_s':sum(t['elapsed_ns'] for t in close['tools'])/1e9,'input':u['input_tokens'],'output':u['output_tokens'],'cached_input':u['cached_input_tokens'],'reasoning_output':u['reasoning_output_tokens'],'input_output':u['input_tokens']+u['output_tokens']})
groups={}
for g in ['N','P0','P1']:
 rr=[r for r in rows if r['group']==g]
 groups[g]={'n':len(rr),'full_median_s':statistics.median(r['full_s'] for r in rr),'full_range_s':[min(r['full_s'] for r in rr),max(r['full_s'] for r in rr)],'full_total_s':sum(r['full_s'] for r in rr),**{k:sum(r[k] for r in rr) for k in ['input','output','input_output','cached_input','tool_calls','response_bytes','owner_tool_s']}}
comparison={}
for ref in ['P0','N']:
 a=groups['P1'];b=groups[ref]
 comparison[ref]={'median_change_pct':(a['full_median_s']/b['full_median_s']-1)*100,'token_change_pct':(a['input_output']/b['input_output']-1)*100,'net_benefit_frozen_rule':a['full_median_s']<b['full_median_s'] and a['input_output']<=b['input_output']}
result={'execution_commit':COMMIT,'fixed_git_files':len(expected),'indexed_files':len(index['files']),'unchanged_dispatch_controls':len(plan['dispatch_input_sha256']),'raw_source_files_hashed':archived,'product_changes':0,'quality_sealed_before_read':True,'batch_wall_s':run['batch_wall_ns']/1e9,'rows':rows,'groups':groups,'comparisons':comparison,'fees':None,'new_consumers':0,'notes':'Root recalculates primary timing and usage from originals. Actual source records and Git bytes verified; not a new installation, Blender capture, or host process reaping.'}
(OUT/'ROOT_COST_AND_INTEGRITY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(result,ensure_ascii=False,indent=2))

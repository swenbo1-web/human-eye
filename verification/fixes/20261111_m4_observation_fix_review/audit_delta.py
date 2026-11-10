from pathlib import Path
import hashlib, json, subprocess

WT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OUT=Path('D:/hefe/verification/fixes/20261111_m4_observation_fix_review')
PREFIX='verification/m4_observation_baseline_001/'
B=WT/PREFIX
OLD='9c85ab9a0518e1fe2369113f59ce308a2d97b8d3'
NEW='1c110f2b81b148fd85eb58de0cbe39cae4f3c6e5'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def git(*args,input=None):return subprocess.run(['git','-C',str(WT),*args],input=input,capture_output=True,check=True).stdout
def old(rel):return git('show',OLD+':'+PREFIX+rel)
def read(rel):return json.loads((B/rel).read_bytes())
assert git('rev-parse','HEAD').decode().strip()==NEW
assert not git('status','--short').strip()
pins={'PLAN.json':'376339732b468fd1eb2c6008f2b97141ffdd6c7902fc047adb3facce15cf4619',
 'FREEZE.json':'04d97d22e88b5dd1f8a0f604376f54e3a30f451dfda3cbe81aae96e131612f05',
 'ARTIFACT_INDEX.json':'3ee8d171bec069f31670ca66a3015ff0c72116e976f71938563e06675e21f995',
 'quality_handoff/pack_quality.py':'afa802bdb085ad9e174f04c4ba91ff05bdacdbc7b0bb892162a7b7e14d580cbc'}
for rel,digest in pins.items():assert sha((B/rel).read_bytes())==digest,rel
index=read('ARTIFACT_INDEX.json');paths=set();total=0
for row in index['files']:
 p=WT/row['path'];assert p.resolve().is_relative_to(B.resolve()) and row['path'] not in paths
 raw=p.read_bytes();assert sha(raw)==row['sha256'] and len(raw)==row['bytes'],row['path']
 paths.add(row['path']);total+=len(raw)
assert len(paths)==index['file_count']==380 and total==index['bytes']==5619387
paths=sorted(paths|{PREFIX+'FREEZE.json',PREFIX+'ARTIFACT_INDEX.json'})
tracked=git('ls-tree','-r','--name-only',NEW,'--',PREFIX).decode().splitlines()
assert set(tracked)==set(paths) and len(paths)==382
blob=git('cat-file','--batch',input=''.join(NEW+':'+p+'\n' for p in paths).encode());pos=0
for rel in paths:
 end=blob.index(b'\n',pos);header=blob[pos:end].split();assert header[1]==b'blob'
 size=int(header[2]);pos=end+1
 assert blob[pos:pos+size]==(WT/rel).read_bytes(),rel
 pos+=size;assert blob[pos:pos+1]==b'\n';pos+=1
assert pos==len(blob)
changed=git('diff','--name-only',OLD,NEW).decode().splitlines()
assert len(changed)==83 and all(p.startswith(PREFIX) for p in changed)
original_index=json.loads(old('ARTIFACT_INDEX.json'))
old_changed=[];unchanged=0
for row in original_index['files']:
 if sha((WT/row['path']).read_bytes())==row['sha256']:unchanged+=1
 else:old_changed.append(row['path'][len(PREFIX):])
assert set(old_changed)=={'PLAN.json','REPORT.md','quality_handoff/SOURCE_REUSE.json','quality_handoff/pack_quality.py'}
assert unchanged==299
archive=B/'revisions/M4_PREP_001/original_9c85ab9a'
archive_checks=[]
for rel in (*old_changed,'FREEZE.json','ARTIFACT_INDEX.json'):
 matches=[p for p in archive.rglob('*') if p.is_file() and p.read_bytes()==old(rel)]
 assert len(matches)==1,rel
 archive_checks.append({'original':rel,'preserved_at':str(matches[0].relative_to(B))})
a=json.loads(old('PLAN.json'));b=read('PLAN.json')
allowed={'$/dispatch_input_sha256/quality_handoff~1SOURCE_REUSE.json','$/dispatch_input_sha256/quality_handoff~1pack_quality.py',
 '$/phase','$/preparation_revision','$/quality_handoff_execution','$/quality_handoff_script_sha256','$/quality_packet_policy/source_and_evidence'}
changes=[]
def diff(a,b,p='$'):
 if a==b:return
 if isinstance(a,dict) and isinstance(b,dict):
  for k in sorted(set(a)|set(b)):
   at=p+'/'+k.replace('~','~0').replace('/','~1')
   if k not in a or k not in b:changes.append(at)
   else:diff(a[k],b[k],at)
 else:changes.append(p)
diff(a,b);assert set(changes)==allowed and len(changes)==7
for rel,digest in b['dispatch_input_sha256'].items():assert sha((B/rel).read_bytes())==digest,rel
assert len(b['dispatch_input_sha256'])==37
for x in ['GO.json','STARTED.json','RUN_RESULT.json','cells']:assert not (B/x).exists()
result={'status':'passed','review_kind':'root static byte/Git/delta audit; no product/Blender/model execution',
 'old_commit':OLD,'new_commit':NEW,'pins':pins,'indexed_files':380,'indexed_bytes':total,
 'git_blobs_equal':382,'changed_files':83,'unchanged_old_index_members':299,
 'changed_old_index_members':old_changed,'original_archives':archive_checks,
 'plan_changes':changes,'dispatch_pins_verified':37,'anonymous_map':'hash only; not parsed',
 'runtime_input_asset_scoring_budget_sequence_unchanged':True,'formal_markers_absent':True}
(OUT/'INTEGRITY_DELTA.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(result,ensure_ascii=False,indent=2))

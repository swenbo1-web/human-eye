"""Delta-only raw/Git audit; no products, CLI, Blender, models or QA imported."""
from pathlib import Path
import hashlib,json,subprocess,zipfile
WT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B=WT/'verification/m4_local_relation_consumption_001';R=B/'revisions/LRC_PREP_001'
OUT=Path(__file__).resolve().parent
OLD='169b0be061e91b126f46313478690564ccb2bd60';NEW='db4ec4c4e0fa3cbf44a8f57fb3f4826730432e81';PREFIX=B.relative_to(WT).as_posix()+'/'
SOURCES={}
def sha(v):return hashlib.sha256(v).hexdigest()
def raw(p):
 p=Path(p);v=p.read_bytes();SOURCES[str(p)]=sha(v);return v
def read(p):return json.loads(raw(p))
def check(c,s):
 if not c:raise AssertionError(s)
def git(*a):return subprocess.check_output(['git','-C',str(WT),*a])
def tree(commit):
 out={}
 for line in git('ls-tree','-r','-z',commit,'--',PREFIX).split(b'\0'):
  if line:
   a,p=line.split(b'\t',1);out[p.decode()]=a.split()[2].decode()
 return out
def diffs(a,b,path='$'):
 if type(a)!=type(b):return [path]
 if isinstance(a,dict):return sum(([path+'/'+k] if k not in a or k not in b else diffs(a[k],b[k],path+'/'+k) for k in sorted(set(a)|set(b))),[])
 if isinstance(a,list):return [path] if a!=b else []
 return [path] if a!=b else []
check(git('rev-parse','HEAD').decode().strip()==NEW,'fixed HEAD');status=git('status','--short').decode()
oldtree,newtree=tree(OLD),tree(NEW);check(len(oldtree)==692 and len(newtree)==724,'Git denominators692/724')
index=read(B/'ARTIFACT_INDEX.json');roots=set(index['root_self_reference_records']);check(roots=={'ARTIFACT_INDEX.json','FREEZE.json','PREP_READY.json','FIX_READY.json'},'only4root exclusions')
check(len(index['files'])==index['file_count']==720,'index720')
rows=list(index['files'])+[dict(path=PREFIX+p,sha256=sha(raw(B/p)),bytes=len(raw(B/p))) for p in roots]
check({r['path'] for r in rows}==set(newtree),'index720 plus4 equals Git724 exact')
oids=[newtree[r['path']] for r in rows];packed=subprocess.check_output(['git','-C',str(WT),'cat-file','--batch'],input=('\n'.join(oids)+'\n').encode());off=0
for row,oid in zip(rows,oids):
 e=packed.index(b'\n',off);h=packed[off:e].split();size=int(h[2]);value=packed[e+1:e+1+size];off=e+size+2
 check(h[0].decode()==oid and h[1]==b'blob' and value==raw(WT/row['path']) and size==row['bytes'] and sha(value)==row['sha256'],'exact Git/current/index '+row['path'])
check(off==len(packed),'whole batch consumed');check(sum(r['bytes'] for r in index['files'])==index['bytes']==27498323,'indexbytes')
check(set(oldtree)<=set(newtree),'all original692paths retained')
changed=[p[len(PREFIX):] for p in oldtree if oldtree[p]!=newtree[p]]
originals=read(R/'ORIGINALS.json')['originals'];check(len(originals)==11,'eleven original archives')
for row in originals:
 v=raw(R/'original_169b0be0'/row['path']);old=git('show',OLD+':'+PREFIX+row['path']);check(v==old and len(v)==row['bytes'] and sha(v)==row['sha256'],'old archived original '+row['path'])
check(set(changed)<={r['path'] for r in originals},'every modified original archived')
for p in changed:check(raw(R/'original_169b0be0'/p)==git('show',OLD+':'+PREFIX+p),'changed old file preserved')
old_index=json.loads(git('show',OLD+':'+PREFIX+'ARTIFACT_INDEX.json'));oldcovered={r['path'] for r in old_index['files']}|{PREFIX+p for p in ('ARTIFACT_INDEX.json','FREEZE.json','PREP_READY.json')}
nine=sorted(set(oldtree)-oldcovered);check(len(nine)==9,'nine original omissions')
for p in nine:check(p in {r['path'] for r in index['files']} and oldtree[p]==newtree[p],'nested old FREEZE now indexed unchanged')
plan=read(B/'PLAN.json');oldplan=json.loads(git('show',OLD+':'+PREFIX+'PLAN.json'));planpaths=diffs(oldplan,plan)
allowed_existing={'$/dispatch_input_sha256/seal_preparation.py','$/dispatch_input_sha256/quality_handoff/pack_quality.py','$/dispatch_input_sha256/quality_handoff/SOURCE_REUSE.json','$/quality_handoff_script_sha256'}
allowed_new={'$/phase','$/preparation_fix','$/synthetic_validation_result'}
unexpected=[p for p in planpaths if p not in allowed_existing and p not in allowed_new and not p.startswith('$/dispatch_input_sha256/revisions/LRC_PREP_001/')]
# Print any unforeseen metadata path for inspection rather than treating it as harmless.
check(not unexpected,'unexpected PLAN changes '+repr(unexpected))
check(plan['phase']=='LRC-PREP-001 FIX_READY; consumers0; separate current-cycle root review and formal GO required' and plan['preparation_fix']['formal_GO'] is False and plan['preparation_fix']['previous_preparation_commit']==OLD and plan['synthetic_validation_result']=='revisions/LRC_PREP_001/tests/RESULTS.json','fix metadata only; no new execution grant')
freeze=read(B/'FREEZE.json');ready=read(B/'PREP_READY.json');fix=read(B/'FIX_READY.json')
check(sha(raw(B/'PLAN.json'))==fix['plan_sha256']==ready['plan_sha256']==freeze['plan_sha256']=='036a091cfc69a5cb085d5d71e649f7d2673967fb3be5552a6669e2e724117efb','planseal')
check(sha(raw(B/'quality_handoff/pack_quality.py'))==fix['packager_sha256']==plan['quality_handoff_script_sha256']=='3b960695d5308ac64c5512191d7c0dc4e854a72b5fa07b97ccb5dfe0c0b3c365','packseal')
check(sha(raw(B/'FREEZE.json'))==fix['freeze_sha256']==ready['freeze_sha256'],'freezeseal')
check(sha(raw(B/'ARTIFACT_INDEX.json'))==fix['artifact_index_sha256']==ready['artifact_index_sha256']==freeze['artifact_index_sha256'],'indexseal')
for p,h in plan['dispatch_input_sha256'].items():check(sha(raw(B/p))==h,'newdispatch '+p)
protected_prefixes=('input/','private/','scoring/','installations/','schemas/','runtime/','preflight/','preparation_history/')
protected_files={'BENEFIT_CONTRACT.json','INPUT_REUSE.json','SEQUENCE.json','PREPARATION_STATE.json','PREPARATION_NOTES.md'}
protected=[p for p in oldtree if p[len(PREFIX):].startswith(protected_prefixes) or p[len(PREFIX):] in protected_files]
check(all(oldtree[p]==newtree[p] for p in protected),'inputs mapping sequence score benefit runtime install controls unchanged')
manifest=read(WT/'verification/m4_local_relation_evidence_001/CANDIDATE_SOURCE.json')['manifest'];check(len(manifest)==137,'137sources')
for row in manifest:check(sha(raw(WT/row['path']))==row['sha256'],'unchanged product checkout '+row['path'])
zip_results=[]
for n in ('01','02'):
 m=read(R/'tests'/('OUTPUT_MANIFEST_'+n+'.json'));zpath=R/'tests'/('OUTPUTS_'+n+'.zip')
 with zipfile.ZipFile(zpath) as z:
  names=[x for x in z.namelist() if not x.endswith('/')];check(set(names)==set(m['members']),'archive member set'+n)
  for p,r in m['members'].items():v=z.read(p);check(len(v)==r['bytes'] and sha(v)==r['sha256'],'archive rawmember '+n+p)
 zip_results.append(dict(attempt=n,members=len(m['members']),sha256=sha(raw(zpath))))
first=read(R/'tests/RESULTS_01.json');second=read(R/'tests/RESULTS_02.json');check(first['passed'] is False and first['unexpected_error']['type']=='FileNotFoundError','first wrapper failure retained')
check(first['packager_sha256']==second['packager_sha256']==fix['packager_sha256'],'same pack in failed and corrected wrappers')
rejection=read(B/'preparation_history/CLEANUP_AUTOREVIEW_REJECTION.json');check(oldtree[PREFIX+'preparation_history/CLEANUP_AUTOREVIEW_REJECTION.json']==newtree[PREFIX+'preparation_history/CLEANUP_AUTOREVIEW_REJECTION.json'],'cleanup refusal untouched')
pyc=sorted(p.relative_to(B).as_posix() for p in B.rglob('*.pyc'))
for p in ('GO.json','STARTED.json','RUN_RESULT.json','cells'):check(not (B/p).exists(),'noformal '+p)
check(git('status','--short').decode()==status,'review leaves implementation unchanged')
result={'scope':'Independent delta-only source/manifest review; no product/model/Blender/CLI/test execution; not overall GO','old_commit':OLD,'new_commit':NEW,'status_before':status,'index_files':720,'index_bytes':27498323,'root_seals':sorted(roots),'actual_git_files':724,'all_current_and_git_hashes_match':True,'old_paths_retained':692,'old_files_changed':changed,'eleven_original_archives_match_fixed_old_blobs':True,'nine_old_nested_FREEZE_now_indexed':nine,'plan_changed_paths':planpaths,'protected_original_files_unchanged':len(protected),'product_source_files_unchanged':137,'wheel_install_matrix_repeated':False,'zip_originals_verified':zip_results,'first_wrapper_failure_preserved':first['unexpected_error']['type'],'same_packager_across_wrapper_fix':True,'cleanup_refusal_unchanged':True,'local_pyc_retained':pyc,'cleanup_attempted':False,'formal_state_absent':True,'source_hashes':SOURCES}
(OUT/'SOURCE_REVIEW.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:result[k] for k in result if k!='source_hashes'},ensure_ascii=False))

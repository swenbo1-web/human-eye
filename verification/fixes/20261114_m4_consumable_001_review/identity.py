"""Independent source/install/archive checks; no product imports or execution."""
from pathlib import Path
import hashlib,json,subprocess,zipfile
R=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
H=R/'verification/m4_consumable_observation_001';O=Path(__file__).parent
HEAD='a7632563fa8631176816100ff4bef778bdbce318';BASE='8030a99b081e9e604fe87797c2daf74c2f6618f7'
PREP='a94fb17fdc0cd8b8ae6dc7b434e3c003e77ba30a';PRODUCT='99fa034ee6074a9b674c1bb05b3328b91e9d93fe'
inputs={};failures=[];checks=0
def raw(p):
 p=Path(p);b=p.read_bytes();inputs[str(p)]=hashlib.sha256(b).hexdigest();return b
def sha(p):return hashlib.sha256(raw(p)).hexdigest()
def js(p):return json.loads(raw(p))
def ck(n,v):
 global checks
 checks+=1
 if not v:failures.append(n)
def git(*a):return subprocess.check_output(['git','-C',str(R),*a])
def blobs(commit,paths):
 b=subprocess.check_output(['git','-C',str(R),'cat-file','--batch'],input=''.join(commit+':'+p+'\n' for p in paths).encode());at=0;out={}
 for p in paths:
  end=b.index(b'\n',at);h=b[at:end].split();assert len(h)==3 and h[1]==b'blob',(p,h)
  size=int(h[2]);out[p]=b[end+1:end+1+size];at=end+size+2
 assert at==len(b)
 return out
ck('HEAD',git('rev-parse','HEAD').decode().strip()==HEAD)
ck('branch',git('branch','--show-current').decode().strip()=='codex/architecture-arm-correction')
ck('clean',not git('status','--porcelain','--untracked-files=all'))
m=js(H/'CONTENT_MANIFEST.json');paths=[x['path'] for x in m['files']]+[(H/'CONTENT_MANIFEST.json').relative_to(R).as_posix()]
ck('manifest370',len(paths)==370)
ck('manifestSHA',sha(H/'CONTENT_MANIFEST.json')=='8e645a6d578221c1d3360716521c06c7b19a40b97713db0b16d48ea9366ca0fe')
changed=git('diff','--name-only',BASE,HEAD).decode().splitlines();ck('scope_exact',set(changed)==set(paths))
product_changes={'human_eye_plugin/active_observation.py','human_eye_plugin/live_spatial_mcp.py'}
ck('only_two_product_files',set(p for p in changed if not p.startswith('verification/m4_consumable_observation_001/'))==product_changes)
for p,b in blobs(HEAD,paths).items():ck('Git:'+p,raw(R/p)==b)
for x in m['files']:
 b=raw(R/x['path']);ck('manifest:'+x['path'],len(b)==x['bytes'] and hashlib.sha256(b).hexdigest()==x['sha256'])
f=js(H/'FROZEN.json');ck('frozen1746',len(f['files_sha256'])==1746)
ck('frozenSHA',sha(H/'FROZEN.json')=='7b239d6a6416d4250750d7b7443a6df09ca166ff59040d4ab74f5b883caf1cd1')
for p,h in f['files_sha256'].items():ck('frozen:'+p,sha(p)==h)
tracked=set(git('ls-tree','-r','--name-only',PREP).decode().splitlines())
repo_frozen=[Path(p).relative_to(R).as_posix() for p in f['files_sha256'] if Path(p).is_relative_to(R)]
untracked=[p for p in repo_frozen if p not in tracked]
ck('untracked_frozen_installed_releases',all(p.startswith('.human-eye/releases/') for p in untracked))
for p,b in blobs(PREP,[p for p in repo_frozen if p in tracked]).items():ck('prep:'+p,b==raw(R/p))
s=js(H/'inputs/SOURCES.json')
for name in ('capture','cameras','scene','product_binding'):
 row=s[name];ck('input:'+name,sha(row['path'])==row['sha256'])
b=js(s['product_binding']['path']);run=js(H/'build/RUN_BINDING.json');ck('binding_match',b==run)
ck('141_sources',len(b['source_manifest'])==141)
src=[x['path'] for x in b['source_manifest']];pb=blobs(PRODUCT,src);hb=blobs(HEAD,src)
wheel=H/'build/human_eye_spatial_plugin-9.7.2+m4.consumable.observation.r1-py3-none-any.whl'
ck('wheelSHA',sha(wheel)==b['wheel_sha256']=='fe3dbb4dcad6c352334a5f31e6fc3c402eee3798ae4f7f2d59edd8a9cdbdf912')
with zipfile.ZipFile(wheel) as z:
 for row in b['source_manifest']:
  p=row['path'];data=raw(R/p);ck('source:'+p,data==pb[p]==hb[p]==raw(Path(b['install_root'])/p)==z.read(p) and hashlib.sha256(data).hexdigest()==row['sha256'])
 meta=[n for n in z.namelist() if n.endswith('.dist-info/METADATA')];ck('wheel_metadata',len(meta)==1 and ('Version: '+b['distribution_version']).encode() in z.read(meta[0]))
digest=hashlib.sha256(json.dumps({'base_version':b['base_version'],'implementation_revision':b['implementation_revision'],'files':b['source_manifest']},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
ck('source_digest',digest==b['source_sha256']==f['product_source_sha256']=='6d4f7d363aaa48081eff7db467fff20665419172560f19b3a4ccb0fbb46c900f')
prompt=raw(H/'inputs/PROMPT.txt');ck('prompt_unchanged',prompt==raw(R/'verification/m4_explicit_observation_consumption_001/inputs/PROMPT.txt'))
ck('promptSHA',hashlib.sha256(prompt).hexdigest()==f['prompt_sha256']=='ecbcb28c961847f14ae9564425f1b8152f07b952d2d5f38ebfcd9fd143ff79d4')
a=js(H/'EXTERNAL_ARCHIVE.json');ck('archive289',len(a['files'])==289)
for x in a['files']:
 data=raw(H/x['archive_path']);ck('archive:'+x['archive_path'],data==raw(x['original_path']) and len(data)==x['bytes'] and hashlib.sha256(data).hexdigest()==x['sha256'])
ck('archive_bytes',sum(x['bytes'] for x in a['files'])==7496644)
ck('archive_originals_complete',{str(p.resolve()) for p in Path('D:/he_consume_001').rglob('*') if p.is_file()}=={str(Path(x['original_path']).resolve()) for x in a['files']})
q=js(H/'QUALITY_SEAL.json')
for x in q['inputs']:ck('quality:'+x['path'],sha(H/x['path'])==x['sha256'])
for file,want in [('REPORT.md','de048f3457256638dc503e23dae97414d530a76fa7fe8b7cde20cf0f01e2dfbd'),('QUALITY_SEAL.json','510a7817f754c883d86082c4dabf54a84cfea516d53502839640b6b2645d4977'),('COST.json','c421f1fd6e7958842765c6e91f5198d3352064a28bc5bd986f2045b0d1cdae8b')]:ck(file+'_SHA',sha(H/file)==want)
ck('root_plan',sha('D:/hefe/docs/M4_CONSUMABLE_OBSERVATION_001_PLAN.md')=='2286adad9cc2fbdc640808ba4c44bc102ab07222e9024ff20b9bb9a30c20cfaf')
result={'passed':not failures,'checks':checks,'failures':failures,'author_HEAD':HEAD,'product_candidate':PRODUCT,'preparation':PREP,'source_sha256':digest,'frozen_files':1746,'Git_manifest_paths':370,'external_original_files':289,'new_product_model_Blender_raster_benchmark_calls':0}
(O/'IDENTITY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(O/'IDENTITY_INPUTS.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))

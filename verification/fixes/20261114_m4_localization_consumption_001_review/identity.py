"""Independent immutable evidence/source audit; no product imports."""
from pathlib import Path
import hashlib,json,subprocess
R=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
H=R/'verification/m4_region_localization_consumption_001'
O=Path(__file__).parent
HEAD='21b2871df70c5fedde4a916c67983ee40c626f89'
BASE='7d42bb939c7881a98fe322c10c216398f6c7aecc'
PREP='20d80b0bd90333d1e3eadaa135aadd6fe62cd9ef'
FIRST='b426c4c813c038693dd40c1de38bd5d61ba91823'
checks=[]; inputs={}
def raw(p):
    p=Path(p); b=p.read_bytes(); inputs[str(p)]=hashlib.sha256(b).hexdigest(); return b
def sha(p):return hashlib.sha256(raw(p)).hexdigest()
def js(p):return json.loads(raw(p))
def ck(n,v):checks.append({'name':n,'passed':bool(v)})
def git(*a):return subprocess.check_output(['git','-C',str(R),*a])
def blobs(commit,paths):
    b=subprocess.check_output(['git','-C',str(R),'cat-file','--batch'],input=''.join(commit+':'+p+'\n' for p in paths).encode());at=0;out={}
    for p in paths:
        end=b.index(b'\n',at);parts=b[at:end].split();assert len(parts)==3 and parts[1]==b'blob',(p,parts)
        n=int(parts[2]);out[p]=b[end+1:end+1+n];at=end+n+2
    assert at==len(b)
    return out
ck('fixed_HEAD',git('rev-parse','HEAD').decode().strip()==HEAD)
ck('clean_author',not git('status','--porcelain','--untracked-files=all'))
ck('author_branch',git('branch','--show-current').decode().strip()=='codex/architecture-arm-correction')
m=js(H/'CONTENT_MANIFEST.json');ck('manifest1151',len(m['files'])==1151)
ck('manifest_digest',sha(H/'CONTENT_MANIFEST.json')=='2cf98ac0dfc873795a9a931568eaad4057e32b2f264bb52800000f2888c72262')
paths=[x['path'] for x in m['files']]+[(H/'CONTENT_MANIFEST.json').relative_to(R).as_posix()]
changed=git('diff','--name-only',BASE,HEAD).decode().splitlines()
ck('exact_scope1152',set(paths)==set(changed))
ck('only_new_namespace',all(p.startswith('verification/m4_region_localization_consumption_001/') for p in changed))
gb=blobs(HEAD,paths)
for p,b in gb.items():ck('Git_disk:'+p,raw(R/p)==b)
for row in m['files']:
    b=raw(R/row['path']);ck('manifest:'+row['path'],len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256'])
f=js(H/'FROZEN.json');pf=js(H/'PREP_FROZEN.json');note=js(H/'FREEZE_GENERATION_NOTE.json')
ck('formal1726',len(f['files_sha256'])==1726)
ck('formal_SHA',sha(H/'FROZEN.json')=='7d55ddadcb4683c9b262d4412ab2604670ebb340290c00e5f9b56e6fc87acd50')
for p,want in f['files_sha256'].items():ck('formal_pin:'+p,sha(p)==want)
utility=(H/'freeze_sources.py').relative_to(R).as_posix();old=blobs(FIRST,[utility])[utility]
prep_changes=[]
for p,want in pf['files_sha256'].items():
    got=sha(p)
    if got!=want:
        prep_changes.append(p);ck('old_freezer_binding',Path(p)==H/'freeze_sources.py' and hashlib.sha256(old).hexdigest()==want==note['preparation_utility_sha256'])
    else:ck('prep_pin:'+p,True)
ck('single_disclosed_prep_change',prep_changes==[str(H/'freeze_sources.py')])
ck('formal_freezer_note',sha(H/'freeze_sources.py')==note['formal_utility_sha256'])
b=js(H/'inputs/PRODUCT_BINDING.json');ck('binding141',len(b['source_manifest'])==141)
src=[x['path'] for x in b['source_manifest']];bas=blobs(BASE,src);pr=blobs(PREP,src);he=blobs(HEAD,src)
install=Path(b['install_root'])
for row in b['source_manifest']:
    p=row['path'];data=raw(R/p);ck('product:'+p,hashlib.sha256(data).hexdigest()==row['sha256'] and data==bas[p]==pr[p]==he[p]==raw(install/p))
digest=hashlib.sha256(json.dumps({'base_version':b['base_version'],'implementation_revision':b['implementation_revision'],'files':b['source_manifest']},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
ck('source_digest',digest==b['source_sha256']==f['product_source_sha256']=='96d7da8c50680a73f251496406c9f0bbbf6b38bd4dfe848c931e45f094343b76')
sources=js(H/'inputs/SOURCES.json')
for name in ('capture','cameras','scene'):
    row=sources[name];ck('input:'+name,sha(H/'inputs'/row['file'])==row['sha256'])
ck('prompt',sha(H/'inputs/PROMPT.txt')==f['prompt_sha256']==pf['prompt_sha256']=='3f848a42070580ad479e3de6507b9ffe09c59b9651c784c17608f0d752c1205a')
rules=js(H/'admin/FROZEN_SCORING.json')
ck('rules',sha(H/'admin/FROZEN_SCORING.json')==f['scoring_sha256']==pf['scoring_sha256'])
for p,want in rules['files_sha256'].items():ck('scoring_pin:'+p,sha(p)==want)
a=js(H/'EXTERNAL_ARCHIVE.json');ck('archive1026',len(a['files'])==1026)
for row in a['files']:
    data=raw(R/row['archive_path']);ck('external:'+row['archive_path'],len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'] and data==raw(row['original_path']))
ck('archive_bytes',sum(x['bytes'] for x in a['files'])==15379031)
ck('report_SHA',sha(H/'REPORT.md')=='476182f7bb2ceffc26ce87b3c1bd3637978ac7436f2bea252018808ca62241eb')
ck('quality_seal_SHA',sha(H/'QUALITY_SEAL.json')=='6b5000de0ff44d67dce5d6e006471787921c1dd90cef74476f254abd89444c55')
ck('plan_SHA',sha('D:/hefe/docs/M4_REGION_LOCALIZATION_CONSUMPTION_001_PLAN.md')=='02b22fc129e05fe963edeb97d0fc0e9e64dfcf68a682227771186e6bdfe95e4c')
result={'passed':all(x['passed'] for x in checks),'checks':len(checks),'failures':[x for x in checks if not x['passed']],'head':HEAD,'product':BASE,'formal_frozen':len(f['files_sha256']),'prep_frozen':len(pf['files_sha256']),'manifest':len(m['files']),'external_files':len(a['files']),'product_source':digest,'known_prep_changes':prep_changes,'root_new_product_model_Blender_raster_benchmark_calls':0,'details':checks}
(O/'IDENTITY.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
(O/'IDENTITY_INPUTS.json').write_text(json.dumps(inputs,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='details'},indent=2))

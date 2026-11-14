"""Independent stdlib byte/identity checks; no candidate modules imported."""
import ast, collections, hashlib, json, subprocess, zipfile
from pathlib import Path

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe')
OLD=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BASE=ROOT/'verification/m4_view_reuse_001'
OUT=Path(__file__).resolve().parent
FINAL='a9dd9490d1817630e090975362591ce232d881ae'
START='6e1e65c6eba0545ef7d3a4280e914b76c99a3f38'
PRODUCT='d12c7ab248452ff253452007d0635f2d662f0191'
PREP='7965c89c1ab3ed139d43f26e28f526e0b0686450'
failures=[]; counts=collections.Counter(); inputs={}; cache={}

def check(group, name, ok):
    counts[group]+=1
    if not ok: failures.append({'group':group,'name':name})
def raw(path):
    p=Path(path); key=str(p)
    if key not in cache:
        data=p.read_bytes(); cache[key]=data
        inputs[key]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    return cache[key]
def sha(path): return hashlib.sha256(raw(path)).hexdigest()
def load(path):return json.loads(raw(path).decode('utf-8-sig'))
def git(*args, root=ROOT):return subprocess.check_output(['git','-C',str(root),*args])
def blobs(ref, paths):
    commands=''.join(ref+':'+p+'\n' for p in paths).encode()
    data=subprocess.run(['git','-C',str(ROOT),'cat-file','--batch'],input=commands,capture_output=True,check=True).stdout
    pos=0; result={}
    for path in paths:
        end=data.index(b'\n',pos); header=data[pos:end].split(); size=int(header[2]); pos=end+1
        result[path]=data[pos:pos+size]; pos+=size+1
    if pos!=len(data):raise ValueError('unconsumed git batch bytes')
    return result

check('git','final_head',git('rev-parse','HEAD').decode().strip()==FINAL)
check('git','new_clean',not git('status','--porcelain').strip())
check('git','old_head',git('rev-parse','HEAD',root=OLD).decode().strip()==START)
check('git','old_clean',not git('status','--porcelain',root=OLD).strip())
for ref in (START,PRODUCT,PREP):
    check('git','ancestor_'+ref,subprocess.run(['git','-C',str(ROOT),'merge-base','--is-ancestor',ref,FINAL]).returncode==0)
manifest=load(BASE/'CONTENT_MANIFEST.json')
paths=git('diff','--name-only',START,FINAL).decode().splitlines()
expected={r['path'] for r in manifest['files']}|{'verification/m4_view_reuse_001/CONTENT_MANIFEST.json'}
check('git','exact_changed_paths',len(paths)==932 and set(paths)==expected)
runtime_changes={p for p in paths if p.startswith('human_eye_plugin/')}
check('git','three_runtime_files',runtime_changes=={'human_eye_plugin/active_observation_images.py','human_eye_plugin/active_observation_host.py','human_eye_plugin/live_spatial_mcp.py'})
final_blobs=blobs(FINAL,paths)
for p in paths:check('git_blob',p,raw(ROOT/p)==final_blobs[p])
for row in manifest['files']:
    p=ROOT/row['path'];check('manifest',str(p),sha(p)==row['sha256'] and len(raw(p))==row['bytes'])

frozen=load(BASE/'FROZEN.json')
for p,h in frozen['files_sha256'].items():check('frozen',p,sha(p)==h)
old_frozen=load(OLD/'verification/m4_routed_task_benefit_001/FROZEN.json')
for p,h in old_frozen['files_sha256'].items():check('old_frozen',p,sha(p)==h)

source=load(BASE/'SOURCE_FREEZE.json'); binding=load(BASE/'build/RUN_BINDING.json')
runtime_paths=[r['path'] for r in source['runtime_manifest']]
product_blobs=blobs(PRODUCT,runtime_paths)
tree=ast.parse(raw(ROOT/'human_eye_plugin/runtime_identity.py'))
const={}
for n in tree.body:
    if isinstance(n,ast.Assign):
        for t in n.targets:
            if isinstance(t,ast.Name) and t.id in ('BASE_VERSION','IMPLEMENTATION_REVISION','_ROOT_MODULES'):
                const[t.id]=ast.literal_eval(n.value)
actual_paths=set(const['_ROOT_MODULES'])
for package in ('human_eye_plugin','human_eye_module1_operators'):
    actual_paths.update(package+'/'+p.name for p in (ROOT/package).glob('*.py'))
check('product','enumeration',set(runtime_paths)==actual_paths and len(runtime_paths)==141)
for row in source['runtime_manifest']:
    p=row['path']; disk=raw(ROOT/p); installed=raw(Path(binding['install_root'])/p)
    check('product',p,disk==installed==product_blobs[p] and hashlib.sha256(disk).hexdigest()==row['sha256'])
payload={'base_version':const['BASE_VERSION'],'implementation_revision':const['IMPLEMENTATION_REVISION'],'files':source['runtime_manifest']}
digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
check('product','digest',digest==source['source_sha256']==binding['source_sha256']=='d8ad7003397d0c0611f54d128c0d0ad3433865b8d9f69b8b0519123752fe9f02')
check('product','source_binding_sha',sha(BASE/'SOURCE_FREEZE.json')==binding['source_freeze_sha256'])
wheel=next((BASE/'build').glob('*.whl'))
check('wheel','whole',sha(wheel)==binding['wheel_sha256']=='b9fd0be946230088aa05577b7bbc42a52cd8a820f1d5d6f4d86309b72174dd1a')
with zipfile.ZipFile(wheel) as archive:
    for p in runtime_paths:check('wheel',p,archive.read(p)==product_blobs[p])
archive=load(BASE/'RUNTIME_ARCHIVE.json')
total=0
for row in archive['files']:
    original=raw(row['original_path']); copy=raw(BASE/row['archive_path']); total+=len(original)
    check('archive',row['relative_path'],original==copy and len(original)==row['bytes'] and hashlib.sha256(original).hexdigest()==row['sha256'])
check('archive','counts',len(archive['files'])==840 and total==archive['bytes']==14984596)

focused=load(BASE/'product_checks_01/RESULT.json')
before=load(BASE/'no_ref_before_01/RESULT.json'); after1=load(BASE/'no_ref_after_01/RESULT.json'); after2=load(BASE/'no_ref_after_02/RESULT.json')
text=raw(ROOT/'human_eye_plugin/active_observation_images.py').decode()
block="""        image_ref = frame.get('image_ref')
        if not image_ref:
            reference_binding = (self._binding, self._patch_mapping_identity, name, frame['image_sha256'])
            if has_raw:
                reference_binding += (OWNER_SCHEMA, self._patch_mapping['owner_identity'], frame.get('frame_identity'))
            image_ref = 'active-image:' + fingerprint(reference_binding)
"""
# Source is byte-pinned; normalize neither line endings nor unrelated content.
newline='\r\n' if '\r\n' in text else '\n'
block=block.replace('\n',newline)
old_expression=("            'image_ref': frame.get('image_ref') or 'active-image:' + fingerprint(\n"
                "                (self._binding, self._patch_mapping_identity, name, frame['image_sha256']),\n"
                "            ),").replace('\n',newline)
prior=text.replace(block,'').replace("            'image_ref': image_ref,",old_expression)
check('fallback','exact_prior_images_reconstruction',text.count(block)==1 and hashlib.sha256(prior.encode()).hexdigest()==focused['source_pins'][0]['sha256'])
check('fallback','final_after_pins',after2['source_sha256']==sha(ROOT/'human_eye_plugin/active_observation_images.py'))
check('fallback','before_collision_retained',before['defect_reproduced'] and before['actual_dual_ref']==before['actual_legacy_ref'])
check('fallback','after_distinct_refs',after2['passed'] and after2['actual_dual_ref']!=after2['actual_legacy_ref'] and after2['actual_legacy_ref']==after2['expected_legacy_ref'])
check('fallback','first_error_retained',not after1['passed'] and len(after1['units']['errors'])==1)
check('fallback','final_units',after2['units']['tests_run']==31 and after2['units']['passed'])
for p,h in after2['protected_saved_bytes'].items():check('fallback_savedbytes',p,sha(p)==h)
result={'schema':'root-view-reuse-identity-v1','final_commit':FINAL,'product_commit':PRODUCT,'preexecution_commit':PREP,
        'groups':dict(counts),'checks':sum(counts.values()),'failures':failures,'all_passed':not failures,
        'changed_paths':len(paths),'manifest_rows':len(manifest['files']),'frozen':len(frozen['files_sha256']),
        'old_frozen':len(old_frozen['files_sha256']),'product_sources':len(runtime_paths),'product_digest':digest,
        'archive_files':len(archive['files']),'archive_bytes':total,'new_product_model_Blender_raster':0}
(OUT/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
(OUT/'INPUTS.json').write_text(json.dumps(inputs,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
if failures:raise SystemExit(1)

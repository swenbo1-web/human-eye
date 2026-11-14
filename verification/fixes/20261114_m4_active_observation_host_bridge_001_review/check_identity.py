"""Independent sealed-source check; no product, host or render execution."""
from pathlib import Path
import ast,base64,csv,hashlib,io,json,subprocess,zipfile

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
H=ROOT/'verification/m4_active_observation_host_bridge_001'
OUT=Path(__file__).resolve().parent
COMMIT='32a1c6eb47cfa84133d92199387339d407a33cb5'
checks=[];inputs={}
def raw(p):
    p=Path(p);b=p.read_bytes();inputs[str(p)]=hashlib.sha256(b).hexdigest();return b
def sha(p):return hashlib.sha256(raw(p)).hexdigest()
def js(p):return json.loads(raw(p))
def ck(k,v,detail=None):checks.append({'name':k,'passed':bool(v),'detail':detail})
def git(*a):return subprocess.check_output(['git','-C',str(ROOT),*a])
ck('fixed_author_HEAD',git('rev-parse','HEAD').decode().strip()==COMMIT)
ck('clean_author_worktree',not git('status','--porcelain','--untracked-files=all'))
manifest=js(H/'CONTENT_MANIFEST.json')
ck('final_manifest_sha',sha(H/'CONTENT_MANIFEST.json')=='10cc531c863bfa886f547f7991ea6c4c253ba36c28e3ff773b700c9589b538a2')
ck('manifest_count',len(manifest['files'])==256)
paths=[r['path'] for r in manifest['files']]+[(H/'CONTENT_MANIFEST.json').relative_to(ROOT).as_posix()]
ck('change_scope_matches_manifest',set(git('diff','--name-only',manifest['baseline_git'],COMMIT,'-z').decode().rstrip('\0').split('\0'))==set(paths))
blobs=subprocess.check_output(['git','-C',str(ROOT),'cat-file','--batch'],input=''.join(COMMIT+':'+p+'\n' for p in paths).encode());off=0
for p in paths:
    end=blobs.index(b'\n',off);header=blobs[off:end].split();size=int(header[2]);start=end+1
    ck('git_disk:'+p,header[1]==b'blob' and blobs[start:start+size]==raw(ROOT/p));off=start+size+1
ck('all_blobs_consumed',off==len(blobs))
for r in manifest['files']:ck('manifest:'+r['path'],sha(ROOT/r['path'])==r['sha256'] and (ROOT/r['path']).stat().st_size==r['bytes'])
frozen=[]
for name,n,expected in [('FROZEN.json',1219,'0051e5da53afe01d9e33d3d96d90397dbd65b2f2c731edc7b44ec610937df0be'),('FROZEN_R2.json',14,'df556713d3e7706073d5f29badbbf5ee3f37003da561ac16ef16db90832fe526')]:
    v=js(H/name);ck(name+':sha',sha(H/name)==expected);ck(name+':count',len(v['files_sha256'])==n)
    for path,digest in v['files_sha256'].items():ck(name+':'+path,sha(path)==digest)
    frozen.append({'file':name,'entries':n,'sha256':expected})
ck('recovery_freeze_original',js(H/'FROZEN_R2.json')['original_source_freeze_sha256']==sha(H/'FROZEN.json'))
archive=js(H/'EXTERNAL_ARCHIVE.json')
ck('archive_count',len(archive['files'])==archive['file_count']==199)
ck('archive_bytes',sum(r['bytes'] for r in archive['files'])==archive['bytes']==4206086)
for r in archive['files']:
    p=ROOT/r['archive_path'];ck('archive:'+r['original_path'],raw(p)==raw(r['original_path']) and sha(p)==r['sha256'] and p.stat().st_size==r['bytes'])

binding=js(H/'build/RUN_BINDING.json');build=js(H/'build/BUILD_INSTALL.json')
wheel=Path(build['wheel']['file']);source=binding['source_manifest'];install=Path(binding['install_root'])
ck('source_count',len(source)==141)
ck('source_freezes_same',source==js(H/'FROZEN.json')['runtime_manifest']==js(H/'FROZEN_R2.json')['product_manifest'])
ck('wheel_sha',sha(wheel)==binding['wheel_sha256']=='c41152a171827f01e2d443de9fb37eebd2755fd1a2a75cca6b7c6a2fe10255f9')
ck('wheel_size',wheel.stat().st_size==build['wheel']['bytes']==1151024)
with zipfile.ZipFile(wheel) as z:
    recordpath=next(p for p in z.namelist() if p.endswith('.dist-info/RECORD'))
    records=list(csv.reader(io.StringIO(z.read(recordpath).decode())))
    ck('wheel_records',len(records)==148 and {r[0] for r in records}==set(z.namelist()))
    installed_records={r[0]:r[1:] for r in csv.reader(io.StringIO(raw(install/recordpath).decode()))}
    for path,digest,size in records:
        b=z.read(path)
        if digest:
            expected='sha256='+base64.urlsafe_b64encode(hashlib.sha256(b).digest()).decode().rstrip('=')
            ck('wheel_RECORD:'+path,digest==expected and int(size)==len(b))
        else:ck('wheel_RECORD_self',path==recordpath and not size)
    for r in source:
        p=r['path'];b=raw(ROOT/p);expected='sha256='+base64.urlsafe_b64encode(hashlib.sha256(b).digest()).decode().rstrip('=')
        ck('runtime:'+p,hashlib.sha256(b).hexdigest()==r['sha256'] and b==z.read(p)==raw(install/p))
        ck('installed_RECORD:'+p,installed_records[p]==[expected,str(len(b))])
constants={}
for n in ast.parse(raw(ROOT/'human_eye_plugin/runtime_identity.py')).body:
    if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('BASE_VERSION','IMPLEMENTATION_REVISION','_ROOT_MODULES'):
        constants[n.targets[0].id]=ast.literal_eval(n.value)
enumerated=list(constants['_ROOT_MODULES'])
for pkg in ('human_eye_plugin','human_eye_module1_operators'):enumerated += [pkg+'/'+p.name for p in (ROOT/pkg).glob('*.py')]
ck('source_manifest_complete',sorted(enumerated)==[r['path'] for r in source])
payload={'base_version':constants['BASE_VERSION'],'implementation_revision':constants['IMPLEMENTATION_REVISION'],'files':source}
digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
ck('recomputed_runtime_digest',digest==binding['source_sha256']=='b12db7282381df800fbd0d44d2f921e332a6b85c2fb3ac77aba51b5cc462b278')
deps=js(H/'preparation/ENVIRONMENT.json');ck('dependency_count',len(deps['dependency_files'])==1046)
for r in deps['dependency_files']:
    p=Path(deps['dependency_root'])/r['relative'];ck('dep:'+r['relative'],sha(p)==r['sha256'] and p.stat().st_size==r['bytes'])

repair=js(H/'preparation/PROGRESS_PUBLICATION_REPAIR.json');original=raw(H/'run_acceptance.py').decode();new=original
for r in repair['changes']:new=new.replace(r['before'],r['after'])
ck('four_exact_harness_changes',len(repair['changes'])==4 and new==raw(H/'run_acceptance_r2.py').decode())
ck('original_controller_digest',sha(H/'run_acceptance.py')==repair['original_controller_sha256'])
ck('recovery_controller_digest',sha(H/'run_acceptance_r2.py')==repair['recovery_controller_sha256'])
addendum=js(H/'review/FINAL_AUDIT_HELPER_CLEANUP.json')
oldcommit=manifest['publication_addendum']['previous_manifest_git']
oldmanifest=git('show',oldcommit+':'+(H/'CONTENT_MANIFEST.json').relative_to(ROOT).as_posix())
ck('previous_seal_preserved_in_git',hashlib.sha256(oldmanifest).hexdigest()==addendum['previous_content_manifest_sha256']==manifest['publication_addendum']['previous_manifest_sha256'])
changed_late=git('diff','--name-only',oldcommit,COMMIT).decode().splitlines()
ck('late_change_only_manifest_and_helper_record',set(changed_late)=={(H/'CONTENT_MANIFEST.json').relative_to(ROOT).as_posix(),(H/'review/FINAL_AUDIT_HELPER_CLEANUP.json').relative_to(ROOT).as_posix()})
ck('cost_original_unchanged',sha(H/'review/FINAL_COST_AUDIT.json')==addendum['cost_audit_preserved_sha256'])
ck('final_audit_sha',sha(H/'FINAL_AUDIT.json')=='dabc56d7a924dbc059d292f860a107c8c32021329133d2d3cad81df141b8823d')
ck('report_sha',sha(H/'REPORT.md')=='64987d14655cc5e2d681a900c9aaceb8bad567b56e7d2e4ce30c4b15219a3769')
for r in archive['files']:
    if r['original_relative_path'].endswith('/LIVE_CONFIG.json'):
        v=js(ROOT/r['archive_path']);ck('isolated_config:'+r['original_relative_path'],v.get('observe_on_prompt') is False and str(v.get('project_root','')).replace('\\','/')=='D:/he_host_001/product')
ck('previous_acceptance_artifacts_unchanged',not git('diff','--name-only',manifest['baseline_git'],COMMIT,'--','verification/m4_active_observation_core_integration_001'))
result={'schema':'root-host-bridge-001-source-review','commit':COMMIT,'passed':all(r['passed'] for r in checks),'check_count':len(checks),'checks':checks,'failures':[r for r in checks if not r['passed']],'runtime_digest':digest,'freezes':frozen,'new_product_model_Blender_raster_calls':0,'method':'Independent bytes, Git, AST constants, ZIP/RECORD and explicit source receipts, no product import.'}
for name,value in [('IDENTITY.json',result),('IDENTITY_INPUTS.json',inputs)]:
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('checks','freezes')},ensure_ascii=False))

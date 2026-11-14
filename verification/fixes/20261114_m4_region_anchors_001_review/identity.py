"""Read-only independent byte/identity audit. Never imports product code."""
from pathlib import Path
import base64, csv, hashlib, io, json, subprocess, zipfile

R=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
H=R/'verification/m4_active_observation_region_anchors_001'
O=Path(__file__).parent
HEAD='7d42bb939c7881a98fe322c10c216398f6c7aecc'
BASE='efe7f77aabdab4f8de47fdb4f8714cb25f301503'
PREP='2a1ac1423c218ea31eafe3db16b4d5f174e9ba22'
checks=[]; inputs={}
def raw(p):
    p=Path(p); b=p.read_bytes(); inputs[str(p)]=hashlib.sha256(b).hexdigest(); return b
def sha(p): return hashlib.sha256(raw(p)).hexdigest()
def js(p): return json.loads(raw(p))
def ck(n,v): checks.append({'name':n,'passed':bool(v)})
def git(*args): return subprocess.check_output(['git','-C',str(R),*args])
def blobs(commit,paths):
    b=subprocess.check_output(['git','-C',str(R),'cat-file','--batch'],input=''.join(commit+':'+p+'\n' for p in paths).encode())
    out={}; at=0
    for p in paths:
        end=b.index(b'\n',at); h=b[at:end].split(); assert len(h)==3 and h[1]==b'blob',(p,h)
        size=int(h[2]); out[p]=b[end+1:end+1+size]; at=end+2+size
    assert at==len(b)
    return out
ck('HEAD',git('rev-parse','HEAD').decode().strip()==HEAD)
ck('branch',git('branch','--show-current').decode().strip()=='codex/architecture-arm-correction')
ck('clean',not git('status','--porcelain','--untracked-files=all'))
m=js(H/'CONTENT_MANIFEST.json'); ck('manifest197',len(m['files'])==197)
ck('manifest_sha',sha(H/'CONTENT_MANIFEST.json')=='6592c053005417ed811a5232731130751b242fd03d240f6a5e778601859d2c10')
paths=[x['path'] for x in m['files']]+[(H/'CONTENT_MANIFEST.json').relative_to(R).as_posix()]
ck('changed_paths198',set(git('diff','--name-only',BASE,HEAD).decode().splitlines())==set(paths))
gb=blobs(HEAD,paths)
for p,b in gb.items(): ck('Git_disk:'+p,raw(R/p)==b)
for row in m['files']: ck('manifest:'+row['path'],sha(R/row['path'])==row['sha256'] and len(raw(R/row['path']))==row['bytes'])
f=js(H/'FROZEN.json'); binding=js(H/'build/RUN_BINDING.json'); build=js(H/'build/BUILD_INSTALL.json')
ck('freeze_sha',sha(H/'FROZEN.json')=='adcc9c4103d43fcb56ce136bca069e44bdf07c1d5796570e8c9674e9776100cc')
ck('freeze1245',len(f['files_sha256'])==1245)
for p,s in f['files_sha256'].items(): ck('frozen:'+p,sha(p)==s)
manifest=binding['source_manifest']; ck('sources141',len(manifest)==141)
ck('source_binding',manifest==f['runtime_manifest'] and binding['source_freeze_sha256']==sha(H/'FROZEN.json'))
digest=hashlib.sha256(json.dumps({'base_version':binding['base_version'],'implementation_revision':binding['implementation_revision'],'files':manifest},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
ck('source_digest',digest==binding['source_sha256']=='96d7da8c50680a73f251496406c9f0bbbf6b38bd4dfe848c931e45f094343b76')
srcpaths=[x['path'] for x in manifest]; pb=blobs(PREP,srcpaths); hb=blobs(HEAD,srcpaths)
install=Path(binding['install_root']); wheel=Path(build['wheel']['file']); wheelbytes=raw(wheel)
ck('wheel_sha',hashlib.sha256(wheelbytes).hexdigest()==binding['wheel_sha256']=='d986d01fb874e6f4cd613934008d3ca9bdcc9a352fdc1097b2dd927b95ff8b4c')
with zipfile.ZipFile(io.BytesIO(wheelbytes)) as z:
    ck('wheel148',len(z.namelist())==148)
    recname=next(n for n in z.namelist() if n.endswith('.dist-info/RECORD'))
    for p,h,size in csv.reader(io.StringIO(z.read(recname).decode())):
        if h:
            b=z.read(p); ck('wheel_RECORD:'+p,h=='sha256='+base64.urlsafe_b64encode(hashlib.sha256(b).digest()).decode().rstrip('=') and len(b)==int(size))
    for row in manifest:
        p=row['path']; b=raw(R/p)
        ck('source:'+p,hashlib.sha256(b).hexdigest()==row['sha256'] and b==pb[p]==hb[p]==z.read(p)==raw(install/p))
    for p in z.namelist():
        if '.dist-info/' in p and not p.endswith('/RECORD'): ck('installed_wheel_metadata:'+p,z.read(p)==raw(install/p))
    relocated=[]
    for p,h,size in csv.reader(io.StringIO(raw(install/recname).decode())):
        if not h: continue
        resolved=install/p
        if p.startswith('../../bin/'):
            resolved=install/'bin'/Path(p).name; relocated.append(p)
        b=raw(resolved); ck('installed_RECORD:'+p,h=='sha256='+base64.urlsafe_b64encode(hashlib.sha256(b).digest()).decode().rstrip('=') and len(b)==int(size))
    ck('console_relocation4',len(relocated)==4)
a=js(H/'EXTERNAL_ARCHIVE.json'); ck('archive117',len(a['files'])==117)
for row in a['files']:
    b=raw(R/row['archive_path']); ck('archive:'+row['archive_path'],len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256'] and b==raw(row['original_path']))
ck('archive_bytes',sum(r['bytes'] for r in a['files'])==a['total_bytes']==7270039)
ck('report_sha',sha(H/'REPORT.md')=='728e42546374986aa1d30aa50f79b40f632c859ae59917c1b45699220710af95')
ck('root_plan',sha('D:/hefe/docs/M4_ACTIVE_OBSERVATION_REGION_ANCHORS_001_PLAN.md')=='209958cbefd346c7cbae5e38cd8c24b2c74e5c0e19ef05fde3532bd1cec59d8e')
changed=git('diff','--name-only',BASE,HEAD,'--','human_eye_plugin').decode().splitlines()
ck('only_four_product',set(changed)=={'human_eye_plugin/'+n+'.py' for n in ('active_observation','active_observation_host','active_observation_images','live_spatial_mcp')})
result={'passed':all(c['passed'] for c in checks),'checks':len(checks),'failures':[c for c in checks if not c['passed']],'head':HEAD,'preparation':PREP,'sources':len(manifest),'source_sha256':digest,'frozen':len(f['files_sha256']),'manifest':len(m['files']),'archive':len(a['files']),'console_relocation':relocated,'new_product_model_Blender_raster_benchmark_calls':0,'checks_detail':checks}
(O/'IDENTITY.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
(O/'IDENTITY_INPUTS.json').write_text(json.dumps(inputs,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='checks_detail'},indent=2))

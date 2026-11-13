"""Read only author disk/Git/source bindings; no author code is imported."""
import hashlib
import io
import json
from pathlib import Path
import subprocess

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
PREFIX='verification/m4_active_image_consumption_001/'
BASE=ROOT/PREFIX
OUT=Path(__file__).resolve().parent
COMMIT='a54ad3a9bf738e8f9b5a75c71c29b0a6b105a6ff'
PREP='1088b491a5051a2e2135670c79e67fb228a12575'
PARENT='f2b9dc01621d5b7adb330c096b6460eb3be9c552'
CHECKS=[]

def sha(b): return hashlib.sha256(b).hexdigest()
def read(p): return json.loads(Path(p).read_bytes())
def check(n,ok,detail=None): CHECKS.append(dict(name=n,passed=bool(ok),detail=detail))
def git(*args,data=None): return subprocess.run(['git',*args],cwd=ROOT,input=data,capture_output=True,check=True).stdout
def tree(commit,prefix):
    out={}
    for row in git('ls-tree','-r','-z',commit,'--',prefix).split(b'\0'):
        if row:
            meta,path=row.split(b'\t',1);out[path.decode()]=meta.split()[2].decode()
    return out
def blobs(entries):
    stream=io.BytesIO(git('cat-file','--batch',data=('\n'.join(entries.values())+'\n').encode()));out={}
    for name,oid in entries.items():
        header=stream.readline().decode().split();assert header[:2]==[oid,'blob']
        out[name]=stream.read(int(header[2]));assert stream.read(1)==b'\n'
    return out

manifest=read(BASE/'CONTENT_MANIFEST.json')
check('manifest_sha',sha((BASE/'CONTENT_MANIFEST.json').read_bytes())=='619e81c7221bd73ad2e13c366cd374f600a49fffc11b9e517051ffd03b4cc35c')
check('HEAD',git('rev-parse','HEAD').decode().strip()==COMMIT)
check('tracked_clean',not git('status','--porcelain','--untracked-files=no'))
entries=tree(COMMIT,PREFIX);expected={r['path'] for r in manifest['files']}|{PREFIX+'CONTENT_MANIFEST.json'}
actual={p.relative_to(ROOT).as_posix() for p in BASE.rglob('*') if p.is_file()}
check('262_git_files',set(entries)==expected and len(entries)==262)
check('262_disk_files',actual==expected,dict(extra=sorted(actual-expected),missing=sorted(expected-actual)))
for name,raw in blobs(entries).items():check('git:'+name,raw==(ROOT/name).read_bytes())
total=0
for r in manifest['files']:
    raw=(ROOT/r['path']).read_bytes();total+=len(raw)
    check('manifest:'+r['path'],len(raw)==r['bytes'] and sha(raw)==r['sha256'])
check('member_bytes',total==manifest['total_member_bytes']==1397715)
frozen=read(BASE/'FROZEN.json');check('24_runtime_sources',len(frozen['runtime_sources'])==24)
for path,digest in frozen['runtime_sources'].items():check('frozen:'+path,sha(Path(path).read_bytes())==digest)
prep=read(BASE/'PREPARATION.json');check('146_preparation_members',len(prep['source_files'])==146)
prepblobs=blobs(tree(PREP,PREFIX))
for r in prep['source_files']:
    raw=(ROOT/r['path']).read_bytes()
    check('preparation:'+r['path'],len(raw)==r['bytes'] and sha(raw)==r['sha256'] and prepblobs[r['path']]==raw)
for cycle,previous,count in [
    ('001','bfcc35e32aab0b724261a5140fc5d05df9ddad48',79),
    ('002','35e9321121e5ca8e9a8414dab859cd6361da4d9c',51),
    ('003',PARENT,321),
]:
    prefix='verification/m4_active_coverage_'+cycle+'/'
    old=tree(previous,prefix)
    check('historical_tree_'+cycle,old==tree(COMMIT,prefix) and len(old)==count)
    for name,raw in blobs(old).items():check('historical_disk:'+name,raw==(ROOT/name).read_bytes())
changed=git('diff','--name-only',PARENT,COMMIT).decode().splitlines()
check('only_new_batch_changes',set(changed)==expected,dict(count=len(changed)))
plan=read(BASE/'PLAN.json');rootplan=Path('D:/hefe/docs/M4_ACTIVE_IMAGE_CONSUMPTION_001_PLAN.md')
check('root_plan_sha',sha(rootplan.read_bytes())==plan['root_plan_sha256']=='8477d53bdc9807c718b370fe9f3cc811906b5069653555e64e32b8020e28a427')
admin_plans=list((BASE/'admin').glob('*PLAN*'))
check('copied_root_plan',any(p.read_bytes()==rootplan.read_bytes() for p in admin_plans),[str(p) for p in admin_plans])
result=dict(commit=COMMIT,preparation_commit=PREP,checks=len(CHECKS),passed=sum(c['passed'] for c in CHECKS),failed=[c for c in CHECKS if not c['passed']],
            delivery_files=len(entries),member_bytes=total,runtime_files=len(frozen['runtime_sources']),preparation_members=146,historical_files_unchanged=451,
            new_runtime_model_renderer_Blender_calls=0,scope='Existing file hashes and Git blobs only, no author scripts imported.')
(OUT/'CHECKS.json').write_text(json.dumps(CHECKS,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(OUT/'IDENTITY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(result,ensure_ascii=False))

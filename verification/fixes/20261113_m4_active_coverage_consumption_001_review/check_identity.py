"""Offline byte audit of fixed formal task delivery; no author modules imported."""
import hashlib
import io
import json
from pathlib import Path
import subprocess

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
PREFIX='verification/m4_active_coverage_consumption_001/'
BASE=ROOT/PREFIX
OUT=Path(__file__).resolve().parent
COMMIT='52d9a838fd52074f3df157aba97e29a5c0cde924'
PREP='28105d629416cbfe8e15e7414ea008a08e74a269'
PARENT='a54ad3a9bf738e8f9b5a75c71c29b0a6b105a6ff'
CHECKS=[]
def sha(b):return hashlib.sha256(b).hexdigest()
def doc(p):return json.loads(Path(p).read_bytes())
def check(n,ok,detail=None):CHECKS.append(dict(name=n,passed=bool(ok),detail=detail))
def git(*args,data=None):return subprocess.run(['git',*args],cwd=ROOT,input=data,capture_output=True,check=True).stdout
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

manifest=doc(BASE/'CONTENT_MANIFEST.json')
check('manifest_sha',sha((BASE/'CONTENT_MANIFEST.json').read_bytes())=='ec5187602167b8a23a93543dba242c54da11c6a71c28a770e519d92b411b5fea')
check('HEAD',git('rev-parse','HEAD').decode().strip()==COMMIT)
check('clean_tracked',not git('status','--porcelain','--untracked-files=no'))
entries=tree(COMMIT,PREFIX);expected={PREFIX+r['path'] for r in manifest['members']}|{PREFIX+'CONTENT_MANIFEST.json'}
actual={p.relative_to(ROOT).as_posix() for p in BASE.rglob('*') if p.is_file()}
check('git_722',set(entries)==expected and len(entries)==722)
check('disk_722',actual==expected,dict(extra=sorted(actual-expected),missing=sorted(expected-actual)))
for name,raw in blobs(entries).items():check('git:'+name,raw==(ROOT/name).read_bytes())
total=0
for row in manifest['members']:
    raw=(BASE/row['path']).read_bytes();total+=len(raw)
    check('manifest:'+row['path'],len(raw)==row['bytes'] and sha(raw)==row['sha256'])
frozen=doc(BASE/'FROZEN.json');check('176_runtime_sources',len(frozen['runtime_sources'])==176)
for path,digest in frozen['runtime_sources'].items():check('runtime:'+path,sha(Path(path).read_bytes())==digest)
check('frozen_digest',sha((BASE/'FROZEN.json').read_bytes())=='e9c7fe18cd047c3c2a3f0d94905efaa48d8e8d6b3f2c3fb88fa2535c2f645f83')
pm=doc(BASE/'PREPARATION_MANIFEST.json');pe=tree(PREP,PREFIX)
check('preparation_exact_225',set(pe)=={PREFIX+r['path'] for r in pm['members']}|{PREFIX+'PREPARATION_MANIFEST.json'} and len(pe)==225)
for name,raw in blobs(pe).items():check('prep_git:'+name,raw==(ROOT/name).read_bytes())
for row in pm['members']:
    raw=(BASE/row['path']).read_bytes();check('prep_manifest:'+row['path'],len(raw)==row['bytes'] and sha(raw)==row['sha256'])
history=[('m4_active_coverage_001',79),('m4_active_coverage_002',51),('m4_active_coverage_003',321),('m4_active_image_consumption_001',262)]
for cycle,count in history:
    prefix='verification/'+cycle+'/'
    old=tree(PARENT,prefix)
    check('history_tree:'+cycle,len(old)==count and old==tree(COMMIT,prefix))
    for name,raw in blobs(old).items():check('history_disk:'+name,raw==(ROOT/name).read_bytes())
check('only_new_batch_changes',set(git('diff','--name-only',PARENT,COMMIT).decode().splitlines())==expected)
rootplan=Path('D:/hefe/docs/M4_ACTIVE_COVERAGE_CONSUMPTION_001_PLAN.md')
check('root_plan_copy',rootplan.read_bytes()==(BASE/'admin/DISPATCH_PLAN.md').read_bytes())
check('root_plan_digest',sha(rootplan.read_bytes())==doc(BASE/'PLAN.json')['administrator_plan_sha256']=='8f1ae6ee3f7e8be7bfaee9bbc6978ad86884958c674264fea6860d0a6738e368')
out=dict(commit=COMMIT,preparation_commit=PREP,checks=len(CHECKS),passed=sum(c['passed'] for c in CHECKS),failed=[c for c in CHECKS if not c['passed']],delivery_files=len(entries),member_bytes=total,runtime_sources=176,preparation_Git_files=225,historical_files_unchanged=713,scope='Read/hash Git and disk only. No author module import or experimental calls.')
(OUT/'CHECKS.json').write_text(json.dumps(CHECKS,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(OUT/'IDENTITY.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(out,ensure_ascii=False))

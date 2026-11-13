"""Offline fixed-delivery byte audit; no candidate modules imported."""
import hashlib
import io
import json
from pathlib import Path
import subprocess

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
PREFIX='verification/m4_consumer_error_contract_001/'
BASE=ROOT/PREFIX
OUT=Path(__file__).resolve().parent
COMMIT='cb5c33a158a9dea06c8151248cc42d2b87c5697b'
PARENT='52d9a838fd52074f3df157aba97e29a5c0cde924'
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

m=doc(BASE/'CONTENT_MANIFEST.json')
check('manifest_digest',sha((BASE/'CONTENT_MANIFEST.json').read_bytes())=='8e7c00530c1f736899c38ac8af0bba56ff307097ee4df7cae5afb3ba6cbb4a59')
check('HEAD',git('rev-parse','HEAD').decode().strip()==COMMIT)
check('tracked_clean',not git('status','--porcelain','--untracked-files=no'))
entries=tree(COMMIT,PREFIX);expected={PREFIX+r['path']for r in m['members']}|{PREFIX+'CONTENT_MANIFEST.json'}
actual={p.relative_to(ROOT).as_posix()for p in BASE.rglob('*')if p.is_file()}
check('1323_Git_files',set(entries)==expected and len(entries)==1323)
check('1323_disk_files',actual==expected,dict(extra=sorted(actual-expected),missing=sorted(expected-actual)))
for name,raw in blobs(entries).items():check('Git:'+name,raw==(ROOT/name).read_bytes())
total=0
for r in m['members']:
    raw=(BASE/r['path']).read_bytes();total+=len(raw)
    check('manifest:'+r['path'],len(raw)==r['bytes']and sha(raw)==r['sha256'])
frozen=doc(BASE/'FROZEN.json')
check('freeze_digest',sha((BASE/'FROZEN.json').read_bytes())=='76a163b53771564a86ac95460e89f986468c58bd36f0527f236b44e3b1e06083')
check('996_frozen_files',len(frozen['files_sha256'])==996)
for path,digest in frozen['files_sha256'].items():check('frozen:'+path,sha(Path(path).read_bytes())==digest)
oldprefix='verification/m4_active_coverage_consumption_001/'
old=tree(PARENT,oldprefix)
check('old_722_tree_unchanged',len(old)==722 and old==tree(COMMIT,oldprefix))
for name,raw in blobs(old).items():check('old_disk:'+name,raw==(ROOT/name).read_bytes())
oldfrozen=doc(ROOT/oldprefix/'FROZEN.json')
check('old_runtime_176',len(oldfrozen['runtime_sources'])==176)
for path,digest in oldfrozen['runtime_sources'].items():check('old_runtime:'+path,sha(Path(path).read_bytes())==digest)
check('only_new_batch_changes',set(git('diff','--name-only',PARENT,COMMIT).decode().splitlines())==expected)
plan=Path('D:/hefe/docs/M4_CONSUMER_ERROR_CONTRACT_001_PLAN.md')
check('root_plan_copy',plan.read_bytes()==(BASE/'admin/DISPATCH_PLAN.md').read_bytes())
check('root_plan_SHA',sha(plan.read_bytes())=='8524e602b75e7d00765c6ea2058ceefbeddac4c92ccab16d6e938d6d1b1b29aa')
out=dict(commit=COMMIT,checks=len(CHECKS),passed=sum(c['passed']for c in CHECKS),failed=[c for c in CHECKS if not c['passed']],delivery_files=len(entries),member_bytes=total,frozen_files=996,old_delivery_files=722,old_runtime_files=176,scope='Disk/Git hashes only; candidate source, matrix, archive and experiment not executed.')
(OUT/'CHECKS.json').write_text(json.dumps(CHECKS,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(OUT/'IDENTITY.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(out,ensure_ascii=False))

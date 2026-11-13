"""Read-only delivery and source binding audit of the stopped 002 batch."""
import hashlib
import io
import json
from pathlib import Path
import subprocess

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
PREFIX='verification/m4_active_coverage_002/'
BASE=ROOT/PREFIX
OUT=Path(__file__).resolve().parent
COMMIT='35e9321121e5ca8e9a8414dab859cd6361da4d9c'
CHECKS=[]
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def check(name,ok,detail=None):CHECKS.append({'name':name,'passed':bool(ok),'detail':detail})
def git(*args,data=None):return subprocess.run(['git',*args],cwd=ROOT,input=data,capture_output=True,check=True).stdout

manifest=read(BASE/'CONTENT_MANIFEST.json')
check('manifest_sha',sha((BASE/'CONTENT_MANIFEST.json').read_bytes())=='aebb78cab5e58d687b0f2514c929511d2f41782439a43d5ddbe8d756b5d357be')
check('author_HEAD',git('rev-parse','HEAD').decode().strip()==COMMIT)
check('author_clean',not git('status','--porcelain','--untracked-files=no'))
entries={}
for line in git('ls-tree','-r','-z',COMMIT,'--',PREFIX).split(b'\0'):
    if line:
        meta,path=line.split(b'\t',1);entries[path.decode()]=meta.split()[2].decode()
listed={row['path']for row in manifest['files']}
expected=listed|{PREFIX+'CONTENT_MANIFEST.json'}
actual={p.relative_to(ROOT).as_posix()for p in BASE.rglob('*')if p.is_file()}
check('git_exact_51',set(entries)==expected and len(entries)==51)
check('disk_exact_51',actual==expected,{'extra':sorted(actual-expected),'missing':sorted(expected-actual)})
data=git('cat-file','--batch',data=('\n'.join(entries.values())+'\n').encode())
stream=io.BytesIO(data)
for name,oid in entries.items():
    header=stream.readline().decode().split()
    assert header[:2]==[oid,'blob']
    raw=stream.read(int(header[2]));assert stream.read(1)==b'\n'
    check('git_bytes:'+name,raw==(ROOT/name).read_bytes())
for row in manifest['files']:
    raw=(ROOT/row['path']).read_bytes()
    check('manifest:'+row['path'],len(raw)==row['bytes']and sha(raw)==row['sha256'])
frozen=read(BASE/'FROZEN.json')
check('151_runtime_files',len(frozen['runtime_sources'])==151)
for path,digest in frozen['runtime_sources'].items():check('frozen:'+path,sha(Path(path).read_bytes())==digest)
for path,digest in frozen['parent_post_run_reference_only'].items():check('old_reference:'+path,sha(Path(path).read_bytes())==digest)
results=read(BASE/'RESULTS.json')
check('formal_freeze_bound',sha((BASE/'FROZEN.json').read_bytes())==results['freeze_sha256'])
diagnosis=read(BASE/'PID_BINDING_DIAGNOSIS.json')
for row in diagnosis['files']:
    raw=Path(row['path']).read_bytes()
    check('diagnosis_file:'+row['path'],len(raw)==row['bytes']and sha(raw)==row['sha256'])
changed=git('diff','--name-only','bfcc35e32aab0b724261a5140fc5d05df9ddad48',COMMIT).decode().splitlines()
check('only_002_new_paths',set(changed)==expected,{'changed_count':len(changed)})
check('prior_root_plan', (BASE/'admin/ROOT_PLAN.md').read_bytes()==Path('D:/hefe/docs/M4_ACTIVE_COVERAGE_002_PLAN.md').read_bytes())
result={'commit':COMMIT,'checks':len(CHECKS),'passed':sum(c['passed']for c in CHECKS),'failed':[c for c in CHECKS if not c['passed']],
        'delivery_files':len(entries),'runtime_files':len(frozen['runtime_sources']),
        'scope':'Git, source, old references and diagnosis files read/hash only. No author validator, engine, renderer, formal benchmark or probe execution.'}
(OUT/'CHECKS.json').write_text(json.dumps(CHECKS,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(OUT/'IDENTITY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(result,ensure_ascii=False))

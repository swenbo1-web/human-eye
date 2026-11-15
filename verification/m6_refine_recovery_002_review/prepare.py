"""Bind the small recovery patch and its complete evidence to one commit."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

HERE=Path(__file__).resolve().parent
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
PREFIX='verification/m6_refine_recovery_002/'
COMMIT='d121d7fd86db16c3cf4f2338704359685571df9a'
BASE=HERE.parent/'_m6rr2/batch'


def git(*args):
    return subprocess.check_output(['git','-C',str(AUTHOR),*args])


def main():
    started=time.perf_counter()
    assert git('rev-parse','HEAD').decode().strip()==COMMIT
    assert not git('status','--short').strip()
    paths=git('ls-tree','-r','--name-only',COMMIT,'--',PREFIX).decode().splitlines()
    assert len(paths)==23
    for path in paths:
        data=git('show',COMMIT+':'+path)
        assert data==(AUTHOR/path).read_bytes()
        target=BASE/Path(path).relative_to(PREFIX)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
    manifest=json.loads((BASE/'MANIFEST.json').read_bytes())
    for row in manifest['files']:
        source=Path(row['path'])
        relative=source.relative_to(AUTHOR/PREFIX)
        data=source.read_bytes()
        assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
        target=BASE/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():shutil.copyfile(source,target)
        assert hashlib.sha256(target.read_bytes()).hexdigest()==row['sha256']
    api='verification/m6_refine_001/session_api.py'
    current=git('show',COMMIT+':'+api)
    assert current==(AUTHOR/api).read_bytes()==(BASE/'private/source/session_api_after.py').read_bytes()
    previous=git('show','154ff39a9a0fa0ed25c59aec282f0bbd315a8a15:'+api)
    assert previous==(BASE/'private/source/session_api_before.py').read_bytes()
    result=dict(status='passed',commit=COMMIT,public_new_files=23,modified_api=api,
                manifest_members=len(manifest['files']),bytes=sum(r['bytes'] for r in manifest['files']),
                old_api_sha256=hashlib.sha256(previous).hexdigest(),new_api_sha256=hashlib.sha256(current).hexdigest(),
                snapshot=str(BASE),wall_s=time.perf_counter()-started)
    (HERE/'SNAPSHOT.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
    print(json.dumps(result))


if __name__=='__main__':main()

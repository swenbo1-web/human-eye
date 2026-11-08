"""Commit exactly the reviewed index, preserving all failed offline attempts."""
import hashlib
import json
from pathlib import Path
import subprocess

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
git=lambda *a,data=None:subprocess.check_output(['git',*a],cwd=ROOT,input=data)
sha=lambda b:hashlib.sha256(b).hexdigest()
freeze=json.loads((OUT/'SOURCE_FREEZE.json').read_bytes())
assert git('rev-parse','HEAD').decode().strip()==freeze['candidate_commit']
assert not git('status','--porcelain','--untracked-files=all')
index_path=OUT/'EVIDENCE_INDEX.json';index=json.loads(index_path.read_bytes())
expected={r['path']:(ROOT/r['path']).read_bytes() for r in index['files']}
for row in index['files']:assert len(expected[row['path']])==row['bytes'] and sha(expected[row['path']])==row['sha256']
actual={p.relative_to(ROOT).as_posix() for p in OUT.rglob('*') if p.is_file() and p!=index_path and '__pycache__' not in p.parts and p.suffix!='.pyc'}
assert actual==set(expected)
expected[index_path.relative_to(ROOT).as_posix()]=index_path.read_bytes()
git('-c','core.autocrlf=false','add','-f','--pathspec-from-file=-','--pathspec-file-nul',data=b''.join(p.encode()+b'\0' for p in expected))
assert set(git('diff','--cached','--name-only','-z').decode().strip('\0').split('\0'))==set(expected)
def verify(revision):
    raw=git('cat-file','--batch',data=b''.join((revision+':'+p+'\n').encode() for p in expected));offset=0
    for p,disk in expected.items():
        end=raw.index(b'\n',offset);header=raw[offset:end].split();assert header[1]==b'blob'
        size=int(header[2]);begin=end+1;assert raw[begin:begin+size]==disk,p;offset=begin+size+1
    assert offset==len(raw)
verify('')
git('commit','--quiet','-m','Archive description-only schema, parser and byte evidence')
head=git('rev-parse','HEAD').decode().strip();verify(head)
assert git('show','-s','--format=%P',head).decode().strip()==freeze['candidate_commit']
assert not git('status','--porcelain','--untracked-files=all')
print(json.dumps(dict(HEAD=head,candidate_commit=freeze['candidate_commit'],source_sha256=freeze['source_sha256'],
    committed_files=len(expected),all_indexed_git_blobs_exact=True,clean_worktree=True,
    report_sha256=sha((OUT/'REPORT.md').read_bytes()),index_sha256=sha(index_path.read_bytes()))))

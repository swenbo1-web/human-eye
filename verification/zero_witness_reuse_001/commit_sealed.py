"""Commit only the indexed evidence after read-only review."""
import hashlib
import json
from pathlib import Path
import subprocess

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
git=lambda *args,data=None:subprocess.check_output(['git',*args],cwd=ROOT,input=data)

def verify_blobs(revision, expected):
    raw=git('cat-file','--batch',data=b''.join((revision+':'+p+'\n').encode() for p in expected))
    offset=0
    for p,disk in expected.items():
        end=raw.index(b'\n',offset);header=raw[offset:end].split();assert header[1]==b'blob',p
        size=int(header[2]);begin=end+1
        assert raw[begin:begin+size]==disk and raw[begin+size:begin+size+1]==b'\n',p
        offset=begin+size+1
    assert offset==len(raw)

frozen=json.loads((OUT/'SOURCE_FREEZE_CANDIDATE.json').read_bytes());candidate=frozen['candidate_commit']
assert git('rev-parse','HEAD').decode().strip()==candidate
assert not git('status','--porcelain','--untracked-files=all') and not git('diff','--cached','--name-only')
index_path=OUT/'EVIDENCE_INDEX.json';index=json.loads(index_path.read_bytes())
expected={}
for r in index['files']:
    p=ROOT/r['path'];assert p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],r['path']
    expected[r['path']]=p.read_bytes()
actual={p.relative_to(ROOT).as_posix() for p in OUT.rglob('*') if p.is_file() and p!=index_path and '__pycache__' not in p.parts and p.suffix!='.pyc'}
assert actual==set(expected) and len(expected)==index['file_count']
expected[index_path.relative_to(ROOT).as_posix()]=index_path.read_bytes()
assert all(p.startswith('verification/zero_witness_reuse_001/') for p in expected)
for r in frozen['product_manifest']:assert sha(ROOT/r['path'])==r['sha256']
git('-c','core.autocrlf=false','add','-f','--pathspec-from-file=-','--pathspec-file-nul',data=b''.join(p.encode()+b'\0' for p in expected))
assert set(git('diff','--cached','--name-only','-z').decode().strip('\0').split('\0'))==set(expected)
verify_blobs('',expected)
git('commit','--quiet','-m','Archive fresh paired zero-witness optimization gates and evidence')
head=git('rev-parse','HEAD').decode().strip();assert git('show','-s','--format=%P',head).decode().strip()==candidate
verify_blobs(head,expected)
for r in frozen['product_manifest']:assert git('cat-file','blob',head+':'+r['path'])==(ROOT/r['path']).read_bytes()
assert not git('status','--porcelain','--untracked-files=all')
print(json.dumps(dict(HEAD=head,candidate_commit=candidate,source_sha256=frozen['source_sha256'],
    indexed_members=index['file_count'],committed_evidence_files=len(expected),all_git_blobs_exact=True,clean_worktree=True,
    report_sha256=sha(OUT/'REPORT.md'),index_sha256=sha(index_path))))

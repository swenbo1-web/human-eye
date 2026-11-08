"""Verify and commit the sealed new evidence after independent review."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = '4ca1fdb2882ae31da2fd3ec49ac77e1710c69a3e'
CANDIDATE = 'b60dd327e3926a06b73d77b37be7b63c50a3939a'
sha = lambda data: hashlib.sha256(data).hexdigest()


def git(*args, data=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, input=data)


def blobs(revision, expected):
    request = b''.join((revision + ':' + name + '\n').encode('utf8') for name in expected)
    raw = git('cat-file', '--batch', data=request)
    offset = 0
    for name, disk in expected.items():
        end = raw.index(b'\n', offset); header = raw[offset:end].split()
        assert len(header) == 3 and header[1] == b'blob', name
        size = int(header[2]); begin = end + 1
        assert raw[begin:begin+size] == disk, name
        assert raw[begin+size:begin+size+1] == b'\n'
        offset = begin + size + 1
    assert offset == len(raw)


def main():
    assert git('rev-parse', 'HEAD').decode().strip() == CANDIDATE
    assert not git('status', '--porcelain', '--untracked-files=all')
    assert not git('diff', '--cached', '--name-only')
    index_path = OUT / 'EVIDENCE_INDEX.json'; index = json.loads(index_path.read_bytes())
    members = {row['path']: row for row in index['files']}
    assert len(members) == index['file_count']
    own_actual = {p.relative_to(ROOT).as_posix() for p in OUT.rglob('*')
                  if p.is_file() and p != index_path and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    own_index = {name for name in members if name.startswith('verification/closed_solid_read_001/')}
    assert own_actual == own_index
    expected = {}
    for name, row in members.items():
        raw = (ROOT / name).read_bytes()
        assert len(raw) == row['bytes'] and sha(raw) == row['sha256'], name
        expected[name] = raw
    expected[index_path.relative_to(ROOT).as_posix()] = index_path.read_bytes()
    tracked = set(git('ls-tree', '-r', '--name-only', CANDIDATE).decode('utf8').splitlines())
    new_paths = set(expected) - tracked
    for name in set(expected) & tracked:
        assert git('cat-file', 'blob', CANDIDATE + ':' + name) == expected[name], name
    git('-c', 'core.autocrlf=false', 'add', '-f', '--pathspec-from-file=-', '--pathspec-file-nul',
        data=b''.join(name.encode('utf8') + b'\0' for name in expected))
    assert set(git('diff', '--cached', '--name-only', '-z').decode('utf8').strip('\0').split('\0')) == new_paths
    blobs('', expected)
    git('commit', '--quiet', '-m', 'Archive closed-shell relation proof and original assembly three-state QA')
    head = git('rev-parse', 'HEAD').decode().strip()
    assert git('show', '-s', '--format=%P', 'HEAD').decode().strip() == CANDIDATE
    changed = set(git('diff', '--name-only', '-z', BASE, head).decode('utf8').strip('\0').split('\0'))
    assert changed == set(expected)
    blobs(head, expected)
    assert not git('status', '--porcelain', '--untracked-files=all')
    print(json.dumps(dict(HEAD=head, candidate_commit=CANDIDATE, baseline=BASE,
        indexed_members=len(members), new_evidence_commit_files=len(new_paths), total_changed_files=len(changed),
        all_indexed_committed_blobs_exact=True, clean_worktree=True,
        report_sha256=sha((OUT / 'REPORT.md').read_bytes()), index_sha256=sha(index_path.read_bytes()))))


if __name__ == '__main__':
    main()

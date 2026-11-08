"""Verify and commit only this batch's already-sealed evidence bytes."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / 'verification/complex_reentry_001'
BASE = 'a4465a388b73ce144035d9139afb48f61519163a'
PREFIX = 'verification/complex_reentry_001/'
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def git(*args, data=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, input=data)


def check_blobs(revision, expected):
    request = b''.join((revision + ':' + path + '\n').encode('utf8') for path in expected)
    raw = git('cat-file', '--batch', data=request)
    offset = 0
    for path, disk in expected.items():
        end = raw.index(b'\n', offset)
        header = raw[offset:end].split()
        assert len(header) == 3 and header[1] == b'blob', (path, header)
        size = int(header[2]); begin = end + 1
        assert raw[begin:begin + size] == disk, path
        assert raw[begin + size:begin + size + 1] == b'\n'
        offset = begin + size + 1
    assert offset == len(raw)


def main():
    assert git('rev-parse', 'HEAD').decode().strip() == BASE
    assert not git('status', '--porcelain', '--untracked-files=all')
    assert not git('diff', '--cached', '--name-only', '-z')
    index_path = RUN / 'EVIDENCE_INDEX.json'
    index = json.loads(index_path.read_bytes())
    members = {row['path']: row for row in index['files']}
    assert len(members) == index['file_count']
    actual = {p.relative_to(RUN).as_posix() for p in RUN.rglob('*')
              if p.is_file() and p != index_path and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    assert actual == set(members)
    expected = {}
    for rel in sorted(members):
        raw = (RUN / rel).read_bytes(); row = members[rel]
        assert len(raw) == row['bytes'] and sha(raw) == row['sha256'], rel
        expected[PREFIX + rel] = raw
    expected[PREFIX + index_path.name] = index_path.read_bytes()
    pathspec = b''.join(path.encode('utf8') + b'\0' for path in expected)
    git('-c', 'core.autocrlf=false', 'add', '-f', '--pathspec-from-file=-', '--pathspec-file-nul', data=pathspec)
    staged = set(git('diff', '--cached', '--name-only', '-z').decode('utf8').strip('\0').split('\0'))
    assert staged == set(expected)
    check_blobs('', expected)
    git('commit', '--quiet', '-m', 'Archive bounded original assembly public capability confirmation')
    head = git('rev-parse', 'HEAD').decode().strip()
    assert git('show', '-s', '--format=%P', 'HEAD').decode().strip() == BASE
    changed = set(git('diff', '--name-only', '-z', BASE, head).decode('utf8').strip('\0').split('\0'))
    assert changed == set(expected)
    check_blobs(head, expected)
    assert not git('status', '--porcelain', '--untracked-files=all')
    print(json.dumps(dict(HEAD=head, parent=BASE, committed_files=len(expected),
        sealed_members=index['file_count'], report_sha256=sha((RUN / 'REPORT.md').read_bytes()),
        index_sha256=sha(index_path.read_bytes()), all_staged_and_committed_blobs_exact=True,
        clean_worktree=True)))


if __name__ == '__main__':
    main()

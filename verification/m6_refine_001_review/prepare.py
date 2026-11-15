"""Freeze fixed refinement evidence in a short Windows path."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
PREFIX = 'verification/m6_refine_001/'
COMMIT = '154ff39a9a0fa0ed25c59aec282f0bbd315a8a15'
BASE = HERE.parent / '_m6rf1/batch'


def git(*args):
    return subprocess.check_output(['git', '-C', str(AUTHOR), *args])


def main():
    started = time.perf_counter()
    assert git('rev-parse', 'HEAD').decode().strip() == COMMIT
    assert not git('status', '--short').strip()
    paths = git('ls-tree', '-r', '--name-only', COMMIT, '--', PREFIX).decode().splitlines()
    assert len(paths) == 60
    for path in paths:
        data = git('show', COMMIT+':'+path)
        assert (AUTHOR/path).read_bytes() == data
        target = BASE/Path(path).relative_to(PREFIX)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    manifest = json.loads((BASE/'MANIFEST.json').read_bytes())
    rows = manifest['files']
    assert len(rows) == 1499
    assert len({r['path'] for r in rows}) == len(rows)
    for row in rows:
        relative = Path(row['path'])
        assert not relative.is_absolute() and '..' not in relative.parts
        source = AUTHOR/PREFIX/relative
        data = source.read_bytes()
        assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256'], row['path']
        target = BASE/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(source, target)
        assert hashlib.sha256(target.read_bytes()).hexdigest() == row['sha256']
    result = dict(status='passed', commit=COMMIT, public_files=len(paths), manifest_members=len(rows),
                  bytes=sum(r['bytes'] for r in rows), snapshot_directory=str(BASE),
                  manifest_sha256=hashlib.sha256((BASE/'MANIFEST.json').read_bytes()).hexdigest(),
                  wall_s=time.perf_counter()-started, author_modified=False)
    (HERE/'SNAPSHOT.json').write_bytes((json.dumps(result, indent=2)+'\n').encode())
    print(json.dumps(result))


if __name__ == '__main__':
    main()

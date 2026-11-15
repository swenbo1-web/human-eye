"""Freeze reference correspondence evidence at the delivered commit."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
PREFIX = 'verification/m6_reference_refine_001/'
COMMIT = '9a759efd7d4acdbc7917fad709d350bd86b33ae2'
BASE = HERE.parent / '_m6ref1/batch'


def git(*args):
    return subprocess.check_output(['git', '-C', str(AUTHOR), *args])


def main():
    started = time.perf_counter()
    assert git('rev-parse', 'HEAD').decode().strip() == COMMIT
    assert not git('status', '--short').strip()
    paths = git('ls-tree', '-r', '--name-only', COMMIT, '--', PREFIX).decode().splitlines()
    assert len(paths) == 35
    for path in paths:
        data = git('show', COMMIT + ':' + path)
        assert data == (AUTHOR / path).read_bytes()
        target = BASE / Path(path).relative_to(PREFIX)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    rows = json.loads((BASE / 'MANIFEST.json').read_bytes())['files']
    assert len(rows) == 247 and len({row['path'] for row in rows}) == 247
    for row in rows:
        relative = Path(row['path'])
        assert not relative.is_absolute() and '..' not in relative.parts
        source = AUTHOR / PREFIX / relative
        data = source.read_bytes()
        assert len(data) == row['bytes']
        assert hashlib.sha256(data).hexdigest() == row['sha256']
        target = BASE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(source, target)
        assert hashlib.sha256(target.read_bytes()).hexdigest() == row['sha256']
    result = dict(
        status='passed', commit=COMMIT, public_files=35, manifest_members=247,
        bytes=sum(row['bytes'] for row in rows), snapshot=str(BASE),
        wall_s=time.perf_counter() - started,
    )
    (HERE / 'SNAPSHOT.json').write_bytes((json.dumps(result, indent=2) + '\n').encode())
    print(json.dumps(result))


if __name__ == '__main__':
    main()

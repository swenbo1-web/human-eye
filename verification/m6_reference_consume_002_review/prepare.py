"""Bind the published consumer trial to a local read-only review snapshot."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time


HERE = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
PREFIX = 'verification/m6_reference_consume_002/'
COMMIT = '159181eede633063e8a5becbaa33210ebb4223a0'
BASE = HERE.parent / '_m6ref2/batch'


def git(*arguments):
    return subprocess.check_output(['git', '-C', str(AUTHOR), *arguments])


def main():
    started = time.perf_counter()
    assert git('rev-parse', 'HEAD').decode().strip() == COMMIT
    assert not git('status', '--short').strip()
    paths = git('ls-tree', '-r', '--name-only', COMMIT, '--', PREFIX).decode().splitlines()
    assert len(paths) == 68
    for path in paths:
        source = git('show', COMMIT + ':' + path)
        assert source == (AUTHOR / path).read_bytes()
        target = BASE / Path(path).relative_to(PREFIX)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source)
    members = json.loads((BASE / 'MANIFEST.json').read_bytes())['files']
    assert len(members) == len({row['path'] for row in members}) == 861
    for row in members:
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
        status='passed', commit=COMMIT, public_files=len(paths),
        manifest_members=len(members), bytes=sum(row['bytes'] for row in members),
        snapshot=str(BASE), wall_s=time.perf_counter() - started,
    )
    (HERE / 'SNAPSHOT.json').write_bytes((json.dumps(result, indent=2) + '\n').encode())
    print(json.dumps(result))


if __name__ == '__main__':
    main()

"""Freeze author evidence without modifying the implementation worktree."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
COMMIT = 'fb529836f3b665be4f22eee886690d583aa9dc31'
PREFIX = 'verification/m6_task_perception_001/'
HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE / 'snapshot'


def git(*args):
    return subprocess.check_output(['git', '-C', str(AUTHOR), *args])


def main():
    started = time.perf_counter()
    public = git('ls-tree', '-r', '--name-only', COMMIT, '--', PREFIX).decode().splitlines()
    assert len(public) == 64
    assert git('rev-parse', 'HEAD').decode().strip() == COMMIT
    assert not git('status', '--short').strip()
    for path in public:
        data = git('show', COMMIT + ':' + path)
        assert (AUTHOR / path).read_bytes() == data, path
        target = SNAPSHOT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    base = SNAPSHOT / PREFIX
    manifest = json.loads((base / 'MANIFEST.json').read_bytes())
    records = manifest['public_files'] + manifest['private_files']
    assert len(records) == 18687
    assert len({r['path'] for r in records}) == len(records)
    for row in records:
        relative = Path(row['path'])
        assert not relative.is_absolute() and '..' not in relative.parts
        source = AUTHOR / PREFIX / relative
        data = source.read_bytes()
        assert len(data) == row['bytes'], row['path']
        assert hashlib.sha256(data).hexdigest() == row['sha256'], row['path']
        destination = base / relative
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        assert hashlib.sha256(destination.read_bytes()).hexdigest() == row['sha256']
    prior = HERE.parent / 'm6_perception_data_001_review/snapshot/verification/m6_perception_data_001'
    shutil.copytree(prior, SNAPSHOT / 'verification/m6_perception_data_001', dirs_exist_ok=True)
    for ancestor in ('a463116f52cc954812cfb6f54513ecfea0eb46ef',
                     '3f79fe14bae4b438a57028122f5defe9b7ee35fd',
                     'de2fb746d262d0d0b5c7aa56d7ff2c623d8d950b'):
        assert subprocess.run(['git', '-C', str(AUTHOR), 'merge-base', '--is-ancestor',
                               ancestor, COMMIT]).returncode == 0
    result = dict(status='passed', commit=COMMIT, public_files=len(public),
                  manifest_members=len(records), manifest_sha256=hashlib.sha256((base / 'MANIFEST.json').read_bytes()).hexdigest(),
                  bytes=sum(r['bytes'] for r in records), prior_data='previous independently verified physical snapshot',
                  wall_s=time.perf_counter()-started, new_training=0)
    (HERE / 'SNAPSHOT.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()

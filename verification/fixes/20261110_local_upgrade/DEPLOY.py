"""Record existing migration-helper operations; no alternative migration logic."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time

ROOT = Path('D:/hefe')
OUT = Path(__file__).resolve().parent
PY = ROOT / '.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe'
OLD = ROOT / '.human-eye/releases/9.7.2+20261103.scene.trace.r1/admin/target_runtime_entry.py'
NEW = ROOT / '.human-eye/releases/9.7.2+20261110.scale.opt.r1/admin/target_runtime_entry.py'
OLD_BUILD = 'a045a800256f4767271308d239c735177f992ce3408d927d42bde5f1d4b60d8f'
NEW_BUILD = '3fc2651e108ad7ac252394871d78e1abaee1200c92a018125984b2fc240193bd'
OLD_SHA = 'dcdbb83011bdb80ba75dd2e442ff8e8ca334443424646dc999563b76a11a93ae'
NEW_SHA = 'e8f710dd283be03acf01a29f3b811a41ef767fd12b2fb6372fa8b628269617d2'
FILES = ['.codex/config.toml', '.codex/hooks.json',
         '.human-eye/live-connector.routing-spatial.json',
         '.human-eye/live-state.routing-spatial.json']


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def snapshot(name):
    folder = OUT / name
    folder.mkdir(exist_ok=False)
    rows = []
    for relative in FILES:
        path = ROOT / relative
        raw = path.read_bytes()
        target = folder / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        rows.append(dict(path=relative, sha256=sha(raw), size=len(raw)))
    state = json.loads((folder / FILES[-1]).read_bytes())
    save(folder / 'SNAPSHOT.json', dict(files=rows,
        inflight=state.get('inflight'), quarantine=state.get('runtime', {}).get('quarantine')))
    return rows


def run(name, entry, action, prior=None, extra=()):
    build = NEW_BUILD if entry == NEW else OLD_BUILD
    argv = [str(PY), '-I', '-B', str(entry), 'admin', action,
            '--agent', 'codex', '--project', str(ROOT), '--expected-build', 'sha256:' + build]
    if prior is not None:
        argv += ['--prior-launcher', str(prior), NEW_SHA if prior == NEW else OLD_SHA,
                 'sha256:' + (NEW_BUILD if prior == NEW else OLD_BUILD)]
    argv += list(extra)
    start = time.perf_counter_ns()
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=90)
    with (OUT / (name + '.stdout.json')).open('xb') as stream:
        stream.write(result.stdout)
    with (OUT / (name + '.stderr.txt')).open('xb') as stream:
        stream.write(result.stderr)
    value = json.loads(result.stdout) if result.stdout else {}
    save(OUT / (name + '.json'), dict(argv=argv, returncode=result.returncode,
        elapsed_ns=time.perf_counter_ns() - start, result=value))
    print(json.dumps(dict(operation=name, returncode=result.returncode,
        plan_sha256=value.get('plan_sha256'), applied=value.get('applied'),
        ready_to_apply=value.get('ready_to_apply'), changes=value.get('changes'),
        error=value.get('error')), ensure_ascii=False))
    if result.returncode:
        raise RuntimeError('Migration helper failed; inspect retained ' + name)
    return value


if __name__ == '__main__':
    mode = sys.argv[1]
    assert sha(OLD.read_bytes()) == OLD_SHA
    assert sha(NEW.read_bytes()) == NEW_SHA
    if mode == 'prepare':
        snapshot('BEFORE')
        run('OLD_DOCTOR_BEFORE', OLD, 'doctor')
        run('NEW_DOCTOR_BEFORE', NEW, 'doctor', OLD)
        run('PLAN_BEFORE', NEW, 'plan', OLD)
    elif mode == 'apply':
        run('APPLY', NEW, 'plan', OLD, ['--apply', '--plan-sha256', sys.argv[2]])
        snapshot('AFTER_APPLY')
    elif mode == 'check':
        run('NEW_DOCTOR_AFTER', NEW, 'doctor')
        run('ROLLBACK_PLAN', OLD, 'plan', NEW)
    else:
        raise ValueError(mode)

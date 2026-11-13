"""Independent fixed-delivery byte verification, no candidate imports."""
import hashlib
import io
import json
from pathlib import Path
import subprocess

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
PREFIX = 'verification/m4_triangulation_invariant_discovery_001/'
BASE = ROOT / PREFIX
OUT = Path(__file__).resolve().parent
COMMIT = 'b638c499c049604902415965f500f50a9947d34f'
PREP = '7b4bb0cd70e35b1e367a14aeae611513b545ae28'
PARENT = 'c556d29156e7d65fc02238dca63321ac062d2c1a'
CHECKS = []


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def check(name, ok, detail=None):
    CHECKS.append({'name': name, 'passed': bool(ok), 'detail': detail})


def git(*args, data=None):
    return subprocess.run(['git', *args], cwd=ROOT, input=data, capture_output=True, check=True).stdout


def tree(commit, prefix):
    out = {}
    for row in git('ls-tree', '-r', '-z', commit, '--', prefix).split(b'\0'):
        if row:
            meta, path = row.split(b'\t', 1)
            out[path.decode()] = meta.split()[2].decode()
    return out


def blobs(entries):
    stream = io.BytesIO(git('cat-file', '--batch', data=('\n'.join(entries.values()) + '\n').encode()))
    for name, oid in entries.items():
        header = stream.readline().decode().split()
        assert header[:2] == [oid, 'blob']
        raw = stream.read(int(header[2]))
        assert stream.read(1) == b'\n'
        yield name, raw


m = read(BASE / 'CONTENT_MANIFEST.json')
check('manifest_SHA', sha((BASE / 'CONTENT_MANIFEST.json').read_bytes()) ==
      'c551595916e8d857d620239bf55add78ef42cfa7ddffb67207ac19de9b346962')
check('HEAD', git('rev-parse', 'HEAD').decode().strip() == COMMIT)
check('branch', git('branch', '--show-current').decode().strip() == 'codex/architecture-arm-correction')
check('clean', not git('status', '--porcelain'))
entries = tree(COMMIT, PREFIX)
expected = {row['path'] for row in m['files']} | {PREFIX + 'CONTENT_MANIFEST.json'}
actual = {p.relative_to(ROOT).as_posix() for p in BASE.rglob('*') if p.is_file()}
check('104_Git_files', set(entries) == expected and len(entries) == 104)
check('104_disk_files', actual == expected, {'extra': sorted(actual - expected), 'missing': sorted(expected - actual)})
for name, raw in blobs(entries):
    check('Git:' + name, raw == (ROOT / name).read_bytes())
total = 0
for row in m['files']:
    raw = (ROOT / row['path']).read_bytes()
    total += len(raw)
    check('manifest:' + row['path'], len(raw) == row['bytes'] and sha(raw) == row['sha256'])
f = read(BASE / 'FROZEN.json')
check('freeze_SHA', sha((BASE / 'FROZEN.json').read_bytes()) ==
      '8570363ae37fd2f9d06d90154f7c88a327ac1aa6bb45daa758bbf4cef9d52593')
check('275_frozen', len(f['files_sha256']) == 275)
for path, wanted in f['files_sha256'].items():
    check('frozen:' + path, sha(Path(path).read_bytes()) == wanted)
prepared = tree(PREP, PREFIX)
check('25_prepared_files', len(prepared) == 25)
check('prepared_tree_unchanged', all(entries[k] == v for k, v in prepared.items()))
for name, raw in blobs(prepared):
    check('prepared:' + name, raw == (ROOT / name).read_bytes())
check('only_new_namespace_changed', set(git('diff', '--name-only', PARENT, COMMIT).decode().splitlines()) == expected)
old_prefix = 'verification/m4_active_coverage_consumption_002/'
old = tree(PARENT, old_prefix)
check('638_old_delivery_Git_unchanged', len(old) == 638 and old == tree(COMMIT, old_prefix))
check('old_disk_set_unchanged', {p.relative_to(ROOT).as_posix() for p in (ROOT / old_prefix).rglob('*') if p.is_file()} == set(old))
for name, raw in blobs(old):
    check('old_delivery:' + name, raw == (ROOT / name).read_bytes())
plan = Path('D:/hefe/docs/M4_TRIANGULATION_INVARIANT_DISCOVERY_001_PLAN.md')
check('root_plan_exact', plan.read_bytes() == (BASE / 'admin/DISPATCH_PLAN.md').read_bytes())
check('root_plan_SHA', sha(plan.read_bytes()) == '31e20718c282848475cf6445eeea02295dc234950be0a0f0da7716da5979675a')
result = {'commit': COMMIT, 'preparation_commit': PREP, 'checks': len(CHECKS),
          'passed': sum(c['passed'] for c in CHECKS), 'failed': [c for c in CHECKS if not c['passed']],
          'delivery_files': len(entries), 'member_bytes': total, 'frozen_files': len(f['files_sha256']),
          'preparation_files': len(prepared), 'old_delivery_files': len(old),
          'scope': 'Disk/Git/source bytes only; no candidate code or workload executed.'}
for name, value in [('CHECKS.json', CHECKS), ('IDENTITY.json', result)]:
    (OUT / name).write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
print(json.dumps(result, ensure_ascii=False))

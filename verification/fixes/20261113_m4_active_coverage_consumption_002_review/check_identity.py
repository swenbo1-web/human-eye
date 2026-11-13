"""Read-only Git/disk/source audit of the fixed coverage consumption delivery."""
import hashlib
import io
import json
from pathlib import Path
import subprocess

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
PREFIX = 'verification/m4_active_coverage_consumption_002/'
BASE = ROOT / PREFIX
OUT = Path(__file__).resolve().parent
COMMIT = 'c556d29156e7d65fc02238dca63321ac062d2c1a'
PREP = 'bad18a465300eba102120b1544dd698d655d61d6'
PARENT = 'cb5c33a158a9dea06c8151248cc42d2b87c5697b'
CHECKS = []


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def check(name, passed, detail=None):
    CHECKS.append({'name': name, 'passed': bool(passed), 'detail': detail})


def git(*args, data=None):
    return subprocess.run(['git', *args], cwd=ROOT, input=data, capture_output=True, check=True).stdout


def tree(commit, prefix):
    result = {}
    for row in git('ls-tree', '-r', '-z', commit, '--', prefix).split(b'\0'):
        if row:
            meta, path = row.split(b'\t', 1)
            result[path.decode()] = meta.split()[2].decode()
    return result


def blobs(entries):
    stream = io.BytesIO(git('cat-file', '--batch', data=('\n'.join(entries.values()) + '\n').encode()))
    for name, oid in entries.items():
        header = stream.readline().decode().split()
        assert header[:2] == [oid, 'blob']
        data = stream.read(int(header[2]))
        assert stream.read(1) == b'\n'
        yield name, data


m = read(BASE / 'CONTENT_MANIFEST.json')
check('manifest_digest', sha((BASE / 'CONTENT_MANIFEST.json').read_bytes()) ==
      '98620c2f88aaed838cc2d895d027d040744f9b297dedff608ce72ee72f6afa66')
check('HEAD', git('rev-parse', 'HEAD').decode().strip() == COMMIT)
check('clean', not git('status', '--porcelain'))
check('branch', git('branch', '--show-current').decode().strip() == 'codex/architecture-arm-correction')
entries = tree(COMMIT, PREFIX)
expected = {PREFIX + row['path'] for row in m['members']} | {PREFIX + 'CONTENT_MANIFEST.json'}
actual = {p.relative_to(ROOT).as_posix() for p in BASE.rglob('*') if p.is_file()}
check('638_Git_files', set(entries) == expected and len(entries) == 638)
check('638_disk_files', actual == expected, {'extra': sorted(actual - expected), 'missing': sorted(expected - actual)})
for name, raw in blobs(entries):
    check('Git:' + name, raw == (ROOT / name).read_bytes())
total = 0
for row in m['members']:
    raw = (BASE / row['path']).read_bytes()
    total += len(raw)
    check('manifest:' + row['path'], len(raw) == row['bytes'] and sha(raw) == row['sha256'])
f = read(BASE / 'FROZEN.json')
check('freeze_digest', sha((BASE / 'FROZEN.json').read_bytes()) ==
      '1f9527f844b58a3e9719a2c0130c1cd1ad19c05a815bb39b975fb256b2a6680e')
check('188_sources', len(f['files_sha256']) == 188)
for path, wanted in f['files_sha256'].items():
    check('source:' + path, sha(Path(path).read_bytes()) == wanted)
prepared = tree(PREP, PREFIX)
pm = read(BASE / 'PREPARATION_MANIFEST.json')
prep_expected = {PREFIX + row['path'] for row in pm['members']} | {PREFIX + 'PREPARATION_MANIFEST.json'}
check('145_preparation_Git_files', set(prepared) == prep_expected and len(prepared) == 145)
check('prepared_Git_OIDs_unchanged', all(entries[k] == v for k, v in prepared.items()))
for row in pm['members']:
    raw = (BASE / row['path']).read_bytes()
    check('preparation:' + row['path'], len(raw) == row['bytes'] and sha(raw) == row['sha256'])
old_counts = {}
for namespace, count in [('m4_active_coverage_consumption_001', 722), ('m4_consumer_error_contract_001', 1323)]:
    prefix = 'verification/' + namespace + '/'
    old = tree(PARENT, prefix)
    check(namespace + ':unchanged_tree', len(old) == count and old == tree(COMMIT, prefix))
    old_disk = {p.relative_to(ROOT).as_posix() for p in (ROOT / prefix).rglob('*') if p.is_file()}
    check(namespace + ':unchanged_file_set', set(old) == old_disk)
    for name, raw in blobs(old):
        check('historical:' + name, raw == (ROOT / name).read_bytes())
    old_counts[namespace] = count
oldf = read(ROOT / 'verification/m4_active_coverage_consumption_001/FROZEN.json')['runtime_sources']
check('old176_subset_of_new188', len(oldf) == 176 and all(f['files_sha256'].get(p) == h for p, h in oldf.items()))
check('only_new_batch_changes', set(git('diff', '--name-only', PARENT, COMMIT).decode().splitlines()) == expected)
plan = Path('D:/hefe/docs/M4_ACTIVE_COVERAGE_CONSUMPTION_002_PLAN.md')
check('root_plan_exact', plan.read_bytes() == (BASE / 'admin/DISPATCH_PLAN.md').read_bytes())
check('root_plan_sha', sha(plan.read_bytes()) == 'cf9fb0d9f7980f0a07c7c7e5f4779951b710abb9c1fa1a407ca0336a4abceae8')
result = {'commit': COMMIT, 'preparation_commit': PREP, 'checks': len(CHECKS),
          'passed': sum(c['passed'] for c in CHECKS), 'failed': [c for c in CHECKS if not c['passed']],
          'delivery_files': len(entries), 'member_bytes': total, 'frozen_files': len(f['files_sha256']),
          'preparation_files': len(prepared), 'old_files': old_counts,
          'scope': 'Git/disk/source bytes only; no candidate import or workload execution.'}
for name, value in [('CHECKS.json', CHECKS), ('IDENTITY.json', result)]:
    (OUT / name).write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
print(json.dumps(result, ensure_ascii=False))

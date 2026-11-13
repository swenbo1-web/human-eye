"""Independent offline byte audit. Does not import author validators or runtime."""
import hashlib
import io
import json
from pathlib import Path
import subprocess

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
PREFIX = 'verification/m4_active_coverage_003/'
BASE = ROOT / PREFIX
OUT = Path(__file__).resolve().parent
COMMIT = 'f2b9dc01621d5b7adb330c096b6460eb3be9c552'
PREP = 'ca33b639e9873457381aa3f62f2f4c32a6c4c0d6'
CHECKS = []

def sha(raw): return hashlib.sha256(raw).hexdigest()
def read(p): return json.loads(Path(p).read_bytes())
def check(name, ok, detail=None): CHECKS.append(dict(name=name, passed=bool(ok), detail=detail))
def git(*args, data=None):
    return subprocess.run(['git', *args], cwd=ROOT, input=data, capture_output=True, check=True).stdout

def tree(commit, prefix):
    entries = {}
    for line in git('ls-tree', '-r', '-z', commit, '--', prefix).split(b'\0'):
        if line:
            meta, path = line.split(b'\t', 1)
            entries[path.decode()] = meta.split()[2].decode()
    return entries

def blobs(entries):
    stream = io.BytesIO(git('cat-file', '--batch', data=('\n'.join(entries.values())+'\n').encode()))
    result = {}
    for name, oid in entries.items():
        header = stream.readline().decode().split()
        assert header[:2] == [oid, 'blob']
        result[name] = stream.read(int(header[2]))
        assert stream.read(1) == b'\n'
    return result

manifest = read(BASE / 'CONTENT_MANIFEST.json')
check('manifest_sha', sha((BASE/'CONTENT_MANIFEST.json').read_bytes()) == '525e8b5fc70cb286ae37a02dfbdc76e49a30d1011f41fe6e3927dbf6e1fb6443')
check('HEAD', git('rev-parse', 'HEAD').decode().strip() == COMMIT)
check('tracked_clean', not git('status', '--porcelain', '--untracked-files=no'))
entries = tree(COMMIT, PREFIX)
listed = {r['path'] for r in manifest['files']}
expected = listed | {PREFIX+'CONTENT_MANIFEST.json'}
actual = {p.relative_to(ROOT).as_posix() for p in BASE.rglob('*') if p.is_file()}
check('git_exact_321', set(entries) == expected and len(entries) == 321)
check('disk_exact_321', actual == expected, dict(extra=sorted(actual-expected), missing=sorted(expected-actual)))
for name, raw in blobs(entries).items(): check('git:'+name, raw == (ROOT/name).read_bytes())
total = 0
for r in manifest['files']:
    raw = (ROOT/r['path']).read_bytes(); total += len(raw)
    check('manifest:'+r['path'], len(raw) == r['bytes'] and sha(raw) == r['sha256'])
check('member_bytes', total == manifest['total_member_bytes'] == 7491110)
frozen = read(BASE/'FROZEN.json')
check('158_sources', len(frozen['runtime_sources']) == 158)
for path, digest in frozen['runtime_sources'].items(): check('source:'+path, sha(Path(path).read_bytes()) == digest)
for path, digest in frozen['parent_post_run_reference_only'].items(): check('old_reference:'+path, sha(Path(path).read_bytes()) == digest)
prep = read(BASE/'PREPARATION.json')
check('66_preparation_members', len(prep['source_files']) == 66)
prepblobs = blobs(tree(PREP, PREFIX))
for r in prep['source_files']:
    raw = (ROOT/r['path']).read_bytes()
    check('preparation:'+r['path'], len(raw) == r['bytes'] and sha(raw) == r['sha256'] and prepblobs[r['path']] == raw)
check('prep_freeze', prep['freeze_sha256'] == sha((BASE/'FROZEN.json').read_bytes()))
for cycle, previous, digest, count in [
    ('001','bfcc35e32aab0b724261a5140fc5d05df9ddad48','f107617a7eb444bfdadc315672f44de19108ed057a9235a19c4b829dfe90e824',79),
    ('002','35e9321121e5ca8e9a8414dab859cd6361da4d9c','aebb78cab5e58d687b0f2514c929511d2f41782439a43d5ddbe8d756b5d357be',51),
]:
    prefix = 'verification/m4_active_coverage_'+cycle+'/'
    old = tree(previous, prefix)
    check('history_tree_'+cycle, old == tree(COMMIT, prefix) and len(old) == count)
    for name, raw in blobs(old).items(): check('history_disk:'+name, raw == (ROOT/name).read_bytes())
    check('history_manifest_'+cycle, sha((ROOT/prefix/'CONTENT_MANIFEST.json').read_bytes()) == digest)
changed = git('diff', '--name-only', '35e9321121e5ca8e9a8414dab859cd6361da4d9c', COMMIT).decode().splitlines()
check('only_003_paths', set(changed) == expected, dict(count=len(changed)))
check('root_plan_bytes', (BASE/'admin/ROOT_PLAN.md').read_bytes() == Path('D:/hefe/docs/M4_ACTIVE_COVERAGE_003_PLAN.md').read_bytes())
result = dict(commit=COMMIT, preparation_commit=PREP, checks=len(CHECKS), passed=sum(c['passed'] for c in CHECKS),
              failed=[c for c in CHECKS if not c['passed']], delivery_files=len(entries), member_bytes=total,
              runtime_files=len(frozen['runtime_sources']), historical_files=130,
              scope='Read/hash existing files and Git blobs only; no author runtime/validator, probe, render, benchmark, model, Blender or API execution.')
(OUT/'CHECKS.json').write_text(json.dumps(CHECKS,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(OUT/'IDENTITY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(result,ensure_ascii=False))

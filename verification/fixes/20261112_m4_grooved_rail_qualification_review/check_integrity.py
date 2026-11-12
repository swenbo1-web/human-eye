"""Read-only input identity checks; writes only this independent review's result."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path('D:/hefe')
IMPL = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
PREFIX = 'verification/m4_grooved_rail_transfer_001'
PACK = IMPL / PREFIX
OUT = Path(__file__).resolve().parent
DELIVERY = '9f38e8522cfeea9a580a19baad0e0d823eb1a16f'
PRODUCT = 'e836e03f4b3821f869c72ac3e50df5204f28b50f'
PARENT = '6d72118299e9097045673d8354f9de729843ee90'
checks = []

def git(cwd, *args):
    return subprocess.check_output(['git', '-C', str(cwd), *args])

def sha(data):
    return hashlib.sha256(data).hexdigest()

def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()

def check(name, passed, detail=None):
    row = {'name': name, 'passed': bool(passed)}
    if detail is not None:
        row['detail'] = detail
    checks.append(row)

def tree(cwd, commit, prefix=None):
    args = ['ls-tree', '-r', '-z', commit]
    if prefix:
        args.extend(['--', prefix])
    rows = {}
    for raw in git(cwd, *args).split(b'\0'):
        if raw:
            meta, path = raw.split(b'\t', 1)
            rows[path.decode()] = meta.split()[2].decode()
    return rows

check('delivery_HEAD', git(IMPL, 'rev-parse', 'HEAD').decode().strip() == DELIVERY)
check('implementation_clean', not git(IMPL, 'status', '--porcelain').strip())
delta = git(IMPL, 'diff', '--name-only', 'a44a6138b9d354ecc98a4fbd76095f0536d6973f', DELIVERY).decode().splitlines()
check('only_57_qualification_files_changed', len(delta) == 57 and all(p.startswith(PREFIX + '/') for p in delta), {'count': len(delta)})
manifest_bytes = (PACK / 'QUALIFICATION_MANIFEST.json').read_bytes()
check('callback_manifest_SHA', sha(manifest_bytes) == '6ff0b854aa52385322e93693c3fa647647eae7705fe91c6a6ca87d209855a9c4')
check('callback_ready_SHA', sha((PACK / 'QUALIFICATION_READY.json').read_bytes()) == 'df2f277cb2951384161f10fc62a2148c80cb28a84c8d729f0af3ed2530643ff6')
manifest = json.loads(manifest_bytes)
listed = {r['path'] for r in manifest['files']} | {'QUALIFICATION_MANIFEST.json'}
actual = {p.relative_to(PACK).as_posix() for p in PACK.rglob('*') if p.is_file()}
check('complete_file_set', actual == listed and len(actual) == 57, {'actual': len(actual), 'manifested': len(listed)})
manifest_bad = []
for row in manifest['files']:
    data = (PACK / row['path']).read_bytes()
    if len(data) != row['bytes'] or sha(data) != row['sha256']:
        manifest_bad.append(row['path'])
check('all_manifest_lengths_and_SHA', not manifest_bad, {'checked': len(manifest['files']), 'mismatch': manifest_bad})
delivery_tree = tree(IMPL, DELIVERY)
disk_bad = [name for name in actual if delivery_tree.get(PREFIX + '/' + name) != blob((PACK / name).read_bytes())]
check('all_57_disk_files_match_delivery_Git', not disk_bad, {'mismatch': disk_bad})
freeze = json.loads((PACK / 'FREEZE.json').read_bytes())
spec_bad = []
for row in freeze['specifications']:
    copied = (PACK / row['copy']).read_bytes()
    original = git(ROOT, 'show', PARENT + ':' + row['parent_path'])
    if copied != original or sha(copied) != row['sha256']:
        spec_bad.append(row['copy'])
check('three_specs_match_preexisting_root_commit_bytes', not spec_bad, {'checked': len(freeze['specifications']), 'mismatch': spec_bad})
source = json.loads((PACK / 'SOURCE_BINDING.json').read_bytes())
install = Path(source['reused_installation']['install_root'])
product_tree = tree(IMPL, PRODUCT)
source_bad, install_bad, product_bad = [], [], []
for row in source['source_manifest']:
    name = row['path']
    data = (IMPL / name).read_bytes()
    if sha(data) != row['sha256']:
        source_bad.append(name)
    if sha((install / name).read_bytes()) != row['sha256']:
        install_bad.append(name)
    if product_tree.get(name) != blob(data) or delivery_tree.get(name) != blob(data):
        product_bad.append(name)
check('137_live_sources_match_frozen_manifest', len(source['source_manifest']) == 137 and not source_bad, {'mismatch': source_bad})
check('137_installed_sources_match_same_manifest', not install_bad, {'checked': len(source['source_manifest']), 'mismatch': install_bad})
check('137_sources_match_product_and_delivery_Git', not product_bad, {'mismatch': product_bad})
protected = json.loads((PACK / 'PROTECTED_BEFORE.json').read_bytes())
protected_bad = [name for name, digest in protected.items() if sha(Path(name).read_bytes()) != digest]
check('five_protected_files_unchanged', len(protected) == 5 and not protected_bad, {'count': len(protected), 'mismatch': protected_bad})
ready = json.loads((PACK / 'QUALIFICATION_READY.json').read_bytes())
bound = {'asset/grooved_rail.blend': 'asset_sha256', 'asset/ACTUAL_SNAPSHOT.json': 'actual_snapshot_sha256', 'oracle/TRUTH.json': 'truth_sha256', 'review/FINAL_BINDING.json': 'independent_final_binding_sha256', 'PREPARATION_LEDGER.json': 'preparation_ledger_sha256', 'review/RESULTS.json': 'independent_review_sha256'}
check('ready_named_artifacts_bound', all(sha((PACK / name).read_bytes()) == ready[key] for name, key in bound.items()), {'count': len(bound)})
result = {'delivery': DELIVERY, 'product': PRODUCT, 'root_plan_commit': PARENT, 'checks': checks, 'passed': sum(c['passed'] for c in checks), 'failed': sum(not c['passed'] for c in checks), 'product_runs': 0, 'Blender_runs': 0, 'model_calls': 0, 'API_calls': 0, 'scope': 'Independent file/Git byte identity only; geometry and worker execution reviewed separately.'}
(OUT / 'INTEGRITY.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'passed': result['passed'], 'failed': result['failed'], 'result': str(OUT / 'INTEGRITY.json')}, ensure_ascii=False))
raise SystemExit(bool(result['failed']))

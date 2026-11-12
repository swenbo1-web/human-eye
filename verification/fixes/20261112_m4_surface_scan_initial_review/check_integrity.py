"""Root independent byte/commit checks; does not import the implementation."""
from pathlib import Path
import ast
import base64
import csv
import hashlib
import io
import json
import subprocess
import zipfile

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OUT = Path(__file__).resolve().parent
PREFIX = 'verification/m4_surface_scan_001'
BASE = ROOT / PREFIX
DELIVERY = '726e88efba548e85eba1eb148b91486470c5d2c1'
PRODUCT = 'c6355a01a4c6ee204a0d676cd9309f02428fe3ba'
INPUT = '96fce78b98cb749885792112e039a406744d282b'
checks = []

def sha(data):
    return hashlib.sha256(data).hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def tree(commit, *paths):
    rows = git('ls-tree', '-r', '-z', commit, '--', *paths).split(b'\0')
    return {name.decode(): meta.split()[2].decode()
            for row in rows if row for meta, name in [row.split(b'\t', 1)]}

def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()

def check(name, value, detail=None):
    checks.append(dict(name=name, passed=bool(value), detail=detail))
    if not value:
        raise AssertionError(name)

def main():
    check('current_delivery_HEAD', git('rev-parse', 'HEAD').decode().strip() == DELIVERY)
    check('implementation_tracked_tree_clean', not git('status', '--porcelain').strip())
    manifest_path = BASE / 'DELIVERY_MANIFEST.json'
    check('callback_manifest_anchor', sha(manifest_path.read_bytes()) ==
          'd2258591204d8215414e0f9d1952484fbbb2894ffb799ab7ce4db9d1a98eea82')
    manifest = read(manifest_path)
    rows = manifest['files']
    names = {row['path'] for row in rows}
    check('751_unique_manifest_rows', len(names) == len(rows) == manifest['file_count'] == 751)
    entries = tree(DELIVERY, PREFIX)
    check('delivery_file_set_complete', set(entries) == names | {PREFIX + '/DELIVERY_MANIFEST.json'}, len(entries))
    mismatch = []
    for row in rows:
        data = (ROOT / row['path']).read_bytes()
        if len(data) != row['bytes'] or sha(data) != row['sha256'] or blob(data) != entries[row['path']]:
            mismatch.append(row['path'])
    check('751_disk_lengths_SHA_and_delivery_Git', not mismatch, mismatch)
    ready = read(BASE / 'INITIAL_READY.json')
    check('ready_report_anchors', all(sha((BASE / n).read_bytes()) == h
          for n, h in ready['review_files'].items()), len(ready['review_files']))
    qualification = read(BASE / 'qualification/SOURCE_OUTPUT_MANIFEST.json')
    old_entries = tree(INPUT, PREFIX)
    mismatch = []
    for row in qualification['files']:
        path = BASE / row['path']; data = path.read_bytes(); rel = path.relative_to(ROOT).as_posix()
        if len(data) != row['bytes'] or sha(data) != row['sha256'] or blob(data) != old_entries.get(rel):
            mismatch.append(rel)
    check('frozen_qualification_bytes_and_INPUT_Git', not mismatch,
          dict(count=len(qualification['files']), mismatch=mismatch))
    qready = read(BASE / 'qualification/QUALIFICATION_READY.json')
    promises = {'asset_sha256': qready['asset'], 'base_snapshot_sha256': 'qualification/BASE_SNAPSHOT.json',
        'edit_snapshot_sha256': 'qualification/EDIT_SNAPSHOT.json', 'base_truth_sha256': 'qualification/BASE_TRUTH.json',
        'edit_truth_sha256': 'qualification/EDIT_TRUTH.json', 'geometry_freeze_sha256': 'qualification/GEOMETRY_FREEZE.json',
        'control_certificates_sha256': 'qualification/CONTROL_CERTIFICATES.json',
        'pose_helper_sha256': qready['pose_helper'], 'pose_patch_sha256': qready['pose_patch']}
    check('nine_old_qualification_promises', all(sha((BASE / p).read_bytes()) == qready[k]
          for k, p in promises.items()), len(promises))
    check('qualification_freeze_manifest_anchor', sha((BASE / 'qualification/SOURCE_OUTPUT_MANIFEST.json').read_bytes()) ==
          read(BASE / 'INPUT_FREEZE.json')['qualification_manifest_sha256'])
    identity = read(BASE / 'CANDIDATE_SOURCE.json')['identity']
    sources = identity['source_files']
    source_paths = {row['path'] for row in sources}
    src_tree = tree(PRODUCT, 'human_eye_plugin', 'human_eye_module1_operators', *source_paths)
    installation = read(BASE / 'installation/run_01/READY.json')
    site = Path(installation['install_root'])
    wheels = list((BASE / 'installation/run_01/bundle').glob('*.whl'))
    check('single_expected_wheel', len(wheels) == 1)
    check('wheel_SHA', sha(wheels[0].read_bytes()) ==
          'c6a75bd682666e855f71f9b9386180fca30de0f801ed36d4fd547be7c4ffffcb')
    mismatch = []
    with zipfile.ZipFile(wheels[0]) as z:
        for row in sources:
            name = row['path']; data = (ROOT / name).read_bytes()
            if (sha(data) != row['sha256'] or blob(data) != src_tree.get(name)
                    or (site / name).read_bytes() != data or z.read(name) != data):
                mismatch.append(name)
        record = next(n for n in z.namelist() if n.endswith('.dist-info/RECORD'))
        count = 0
        for name, digest, size in csv.reader(io.StringIO(z.read(record).decode())):
            if not digest:
                check('wheel_unhashed_member_is_RECORD', name == record)
                continue
            raw = z.read(name); method, expected = digest.split('=', 1)
            check('wheel_member_' + name, method == 'sha256' and len(raw) == int(size) and
                  base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=') == expected)
            count += 1
    check('138_source_checkout_commit_wheel_install', len(sources) == 138 and not mismatch, mismatch)
    digest_input = {'base_version': identity['base_version'],
        'implementation_revision': identity['implementation_revision'], 'files': sources}
    actual = sha(json.dumps(digest_input, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
    check('source_aggregate', actual == identity['source_sha256'] == ready['source_sha256'] ==
          'b3654f6f943c3fb6feff0011397c0a8c20872e41f35973e6baf53e3a5e277314')
    package_paths = {p.relative_to(ROOT).as_posix() for package in ('human_eye_plugin', 'human_eye_module1_operators')
                     for p in (ROOT / package).glob('*.py')}
    check('package_source_enumeration_complete', package_paths <= source_paths)
    old = tree('e836e03f4b3821f869c72ac3e50df5204f28b50f', *source_paths)
    check('product_unchanged_after_product_commit', not git('diff', '--name-only', PRODUCT, DELIVERY, '--', *source_paths).strip())
    check('no_pyc_submitted', not any(n.endswith('.pyc') for n in entries))
    return dict(delivery=DELIVERY, product=PRODUCT, input_commit=INPUT,
                manifest_file_count=len(rows), wheel_hashed_members=count, checks=checks,
                source_files=len(sources), passed=all(c['passed'] for c in checks),
                new_Blender_consumer_API_runs=0)

if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        result = main()
    except Exception as exc:
        result = dict(passed=False, error=repr(exc), checks=checks)
        (OUT / 'INTEGRITY_FAILED.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        raise
    (OUT / 'INTEGRITY.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({'passed':result['passed'], 'checks':len(checks), 'files':len(rows) if 'rows' in globals() else 751}))

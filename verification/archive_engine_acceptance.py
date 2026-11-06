"""Archive the frozen V1 integration recheck and independent acceptance evidence."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / 'docs/engine_v1_evidence_index.json.gz'
AUTHOR = ROOT / 'artifacts/integration/managed_current_recheck_001'
REVIEW = ROOT / 'artifacts/integration/root_recheck_review_001'
LIMIT = 40 * 1024 * 1024
IDENTITY_SHA = '904733375f92791733f8bd35db334fafa06d2b8dcd496f244a52a42a72653a8a'
EXTRA = (
    'docs/ENGINE_V1_ACCEPTANCE.md',
    'docs/radical_acceptance_engine_v1.json',
    'docs/MANAGED_CURRENT_RECHECK_PROTOCOL.md',
    'docs/ENGINE_INTEGRATION_API.md',
    'docs/INTEGRATION_COST_PROTOCOL.md',
    'examples/blender_radical_session.py',
    'verification/archive_engine_acceptance.py',
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def current_record(path):
    data = path.read_bytes()
    return {'bytes': len(data), 'sha256': digest(data)}


def author_identity():
    path = AUTHOR / 'artifact-identity.json'
    assert digest(path.read_bytes()) == IDENTITY_SHA
    identity = json.loads(path.read_text())
    assert identity['file_count'] == len(identity['files']) == 16109
    for name, record in identity['files'].items():
        assert current_record(AUTHOR / name) == record, name
    actual = {p.relative_to(AUTHOR).as_posix() for p in AUTHOR.rglob('*') if p.is_file()}
    assert actual == set(identity['files']) | {'artifact-identity.json'}
    return len(identity['files'])


def selected_paths():
    files = [p for directory in (AUTHOR, REVIEW) for p in directory.rglob('*') if p.is_file()]
    files += [ROOT / name for name in EXTRA]
    files += list((ROOT / 'human_eye_fast').glob('*.py'))
    names = sorted({p.relative_to(ROOT).as_posix() for p in files})
    assert all((ROOT / name).is_file() for name in names)
    assert not any('RADICAL_V1_SPEC_REVIEW' in name for name in names)
    return names


def verify(index):
    assert set(index['files']) == set(selected_paths())
    seen = set()
    for volume in index['volumes']:
        path = ROOT / volume['path']
        assert current_record(path) == {k: volume[k] for k in ('bytes', 'sha256')}
        with zipfile.ZipFile(path) as archive:
            assert len(archive.namelist()) == len(set(archive.namelist()))
            assert archive.testzip() is None
            for name in archive.namelist():
                assert name not in seen
                seen.add(name)
                record = index['files'][name]
                assert record['volume'] == volume['path']
                data = archive.read(name)
                assert len(data) == record['bytes'] and digest(data) == record['sha256'], name
                assert current_record(ROOT / name) == {k: record[k] for k in ('bytes', 'sha256')}, name
    assert seen == set(index['files'])
    return {'files_verified': len(seen), 'author_files_verified': author_identity(),
            'volumes': len(index['volumes']), 'uncompressed_bytes': index['uncompressed_bytes'],
            'archive_bytes': sum(v['bytes'] for v in index['volumes']), 'verification': 'PASS'}


def build():
    assert not INDEX.exists(), 'Existing evidence must be verified, not overwritten'
    author_identity()
    records = {name: current_record(ROOT / name) for name in selected_paths()}
    groups, group, size = [], [], 0
    for name, record in records.items():
        if group and size + record['bytes'] > LIMIT:
            groups.append(group)
            group, size = [], 0
        group.append(name)
        size += record['bytes']
    if group:
        groups.append(group)
    volumes = []
    for number, names in enumerate(groups, 1):
        relative = f'docs/engine_v1_evidence_{number:02d}.zip'
        path = ROOT / relative
        assert not path.exists(), relative
        with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name in names:
                data = (ROOT / name).read_bytes()
                assert len(data) == records[name]['bytes'] and digest(data) == records[name]['sha256'], name
                info = zipfile.ZipInfo(name, (2026, 11, 6, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
                records[name]['volume'] = relative
        volumes.append({'path': relative, **current_record(path), 'files': len(names)})
    index = {'schema': 'human-eye-engine-v1-evidence-1', 'date': '2026-11-06',
             'scope': 'One bounded nine-process repair recheck and root independent acceptance; historical results remain in earlier archives',
             'author_identity_sha256': IDENTITY_SHA, 'file_count': len(records),
             'uncompressed_bytes': sum(r['bytes'] for r in records.values()),
             'volumes': volumes, 'files': records}
    result = verify(index)
    INDEX.write_bytes(gzip.compress(json.dumps(index, ensure_ascii=False, indent=2).encode(), mtime=0))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    result = verify(json.loads(gzip.decompress(INDEX.read_bytes()))) if args.verify_only else build()
    print(json.dumps(result))

"""Preserve the complete S necessity preflight/review and its public AO inputs."""

from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def main():
    preflight = ROOT / 'artifacts/cf/s_preflight_001'
    review = ROOT / 'artifacts/cf/s_root_review_001'
    receipt = json.loads((preflight / 'source-identity.json').read_bytes())
    consumer = json.loads((preflight / 'ao-case13-replay.json').read_bytes())
    paths = {p for folder in (preflight, review) for p in folder.rglob('*')
             if p.is_file() and '__pycache__' not in p.parts}
    paths.update(ROOT / entry['path'] for entry in receipt['source'].values())
    paths.update(ROOT / entry['path'] for entry in consumer['actual_reads'])
    paths.update((Path(__file__), ROOT / 'verification/audit_cf_salience_preflight.py'))
    files = {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in sorted(paths)}
    manifest = {name: {'bytes': len(data), 'sha256': sha256(data).hexdigest()}
                for name, data in files.items()}
    archive = ROOT / 'docs/cf_s_review_evidence.zip'
    with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as zipped:
        zipped.writestr('manifest.json', json.dumps(manifest, indent=2))
        for name, data in files.items():
            zipped.writestr(name, data)
    with ZipFile(archive) as zipped:
        assert zipped.testzip() is None
        assert set(zipped.namelist()) == set(files) | {'manifest.json'}
        for name, data in files.items():
            assert zipped.read(name) == data
    print(json.dumps({'files': len(files), 'bytes': archive.stat().st_size,
                      'sha256': sha256(archive.read_bytes()).hexdigest(), 'exact_roundtrip': True}))


if __name__ == '__main__':
    main()

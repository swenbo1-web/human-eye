"""Seal this batch's private originals without rewriting earlier evidence."""

import argparse
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preparation', action='store_true')
    parser.add_argument('--verify', action='store_true')
    options = parser.parse_args()
    filename = 'PREPARATION_MANIFEST.json' if options.preparation else 'CONTENT_MANIFEST.json'
    target = HERE / filename
    if options.verify:
        manifest = json.loads(target.read_bytes())
        for row in manifest['members']:
            raw = (HERE / row['path']).read_bytes()
            if len(raw) != row['bytes'] or digest(raw) != row['sha256']:
                raise ValueError('sealed_member_changed_' + row['path'])
        print(json.dumps({'verified': True, 'members': len(manifest['members']),
                          'manifest_sha256': digest(target.read_bytes())}))
        return
    if target.exists():
        raise FileExistsError('existing_seal_is_immutable')
    rows = []
    for path in sorted(HERE.rglob('*')):
        if not path.is_file() or path == target:
            continue
        raw = path.read_bytes()
        rows.append({'path': path.relative_to(HERE).as_posix(),
                     'bytes': len(raw), 'sha256': digest(raw)})
    value = {'schema': 'active-coverage-consumption-001-content-manifest-v1',
             'stage': 'preparation' if options.preparation else 'final',
             'scope': 'All files under this batch except this manifest itself at sealing time.',
             'members': rows}
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf8')
    with target.open('xb') as stream:
        stream.write(raw)
    print(json.dumps({'sealed': True, 'members': len(rows), 'manifest_sha256': digest(raw)}))


if __name__ == '__main__':
    main()

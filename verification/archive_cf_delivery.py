"""Archive CF numerical/source evidence and all evaluation media in bounded ZIP parts.

Bulk offline train/validation media remain local; every omitted member is indexed
by digest. All raw numerical records, labels, models and validation scores remain
in the archive. This is a transparent storage boundary, not outcome filtering.
"""

from hashlib import sha256
import gzip
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('formal_001', 'stage2_smoke_001', 'stage2_smoke_002', 'stage2_smoke_003',
         'root_formal_review_001', 'root_formal_native_001',
         'root_formal_controls_001', 'root_formal_controls_002')
LIMIT = 32 * 1024 * 1024


def meta(data):
    return {'sha256': sha256(data).hexdigest(), 'bytes': len(data)}


class Parts:
    def __init__(self, name):
        self.name = name
        self.paths = []
        self.archive = None
        self.size = 0

    def add(self, name, data):
        if self.archive is None or self.size + len(data) > LIMIT:
            self.close()
            path = ROOT / f'docs/cf_formal_{self.name}_{len(self.paths) + 1:02d}.zip'
            assert not path.exists(), path
            self.paths.append(path)
            self.archive = ZipFile(path, 'w', compression=ZIP_DEFLATED)
            self.size = 0
        self.archive.writestr(name, data)
        self.size += len(data)
        return {'archive': self.paths[-1].relative_to(ROOT).as_posix(), 'entry': name}

    def close(self):
        if self.archive is not None:
            self.archive.close()
            self.archive = None


def main():
    raw, visual = Parts('raw'), Parts('visual')
    files, assets, containers, blobs = {}, {}, {}, {}
    for folder in NAMES:
        for path in sorted((ROOT / 'artifacts/cf' / folder).rglob('*')):
            if not path.is_file() or '__pycache__' in path.parts:
                continue
            rel = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            if path.name != 'media.zip' and path.suffix != '.png':
                files[rel] = meta(data) | raw.add(rel, data)
                continue
            if path.name == 'media.zip':
                stored = not (folder == 'formal_001' and any(part in path.parts for part in
                              ('train', 'validation-labels', 'validation-arms')))
                containers[rel] = meta(data) | {'members_archived': stored}
                with ZipFile(path) as source:
                    members = [(rel + '::' + name, source.read(name)) for name in source.namelist()]
            else:
                stored, members = True, [(rel, data)]
            for name, content in members:
                value = meta(content)
                if stored:
                    digest = value['sha256']
                    if digest not in blobs:
                        blobs[digest] = visual.add('blobs/' + digest, content)
                    value |= blobs[digest]
                assets[name] = value | {'archived': stored}
    raw.close()
    visual.close()
    paths = raw.paths + visual.paths
    indexes = {p.relative_to(ROOT).as_posix(): meta(p.read_bytes()) for p in paths}
    for path in paths:
        with ZipFile(path) as archive:
            assert archive.testzip() is None
    handles = {name: ZipFile(ROOT / name) for name in indexes}
    try:
        for entry in (*files.values(), *assets.values()):
            if 'archive' in entry:
                restored = handles[entry['archive']].read(entry['entry'])
                assert meta(restored) == {key: entry[key] for key in ('sha256', 'bytes')}
    finally:
        for archive in handles.values():
            archive.close()
    index = {'scope': 'All fixed stage-two numerical records, source snapshots, models, failures and root reviews; '
                      'all formal evaluation/control/diagnostic/prequential and smoke/root PNG/AO members. '
                      'Bulk train/validation media are hash-indexed and retained locally, not included in Git.',
             'directories': NAMES, 'raw_files': files, 'media_containers': containers,
             'assets': assets, 'archives': indexes, 'exact_content_roundtrip': True}
    target = ROOT / 'docs/cf_formal_evidence_index.json.gz'
    target.write_bytes(gzip.compress(json.dumps(index, ensure_ascii=False, separators=(',', ':')).encode(), mtime=0))
    print(json.dumps({'raw_files': len(files), 'media_paths': len(assets),
                      'archived_media_paths': sum(item['archived'] for item in assets.values()),
                      'unique_archived_media': len(blobs), 'archives': indexes,
                      'index_bytes': target.stat().st_size, 'exact_roundtrip': True}, indent=2))


if __name__ == '__main__':
    main()

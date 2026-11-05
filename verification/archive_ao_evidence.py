"""Package all AO evidence, including failures, with exact-byte roundtrip checks."""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    raw, images, unique = {}, {}, {}
    for path in sorted((ROOT / 'artifacts/ao').rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts:
            continue
        data = path.read_bytes()
        name = path.relative_to(ROOT).as_posix()
        metadata = {'bytes': len(data), 'sha256': sha(data)}
        if path.suffix.lower() == '.png':
            item = 'png/' + metadata['sha256'] + '.png'
            images[name] = {**metadata, 'archive': item}
            unique[item] = data
        else:
            try:
                content, encoding = data.decode('utf-8'), 'utf-8'
            except UnicodeDecodeError:
                content, encoding = base64.b64encode(data).decode('ascii'), 'base64'
            raw[name] = {**metadata, 'encoding': encoding, 'content': content}
    payload = {'scope': 'All AO local raw evidence, including unsuccessful trials and source snapshots; no filtering by outcome',
               'files': raw, 'png_manifest': images}
    packed = gzip.compress(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8'), mtime=0)
    raw_path = ROOT / 'docs/ao_raw.json.gz'
    raw_path.write_bytes(packed)
    visual_path = ROOT / 'docs/ao_visual_evidence.zip'
    with zipfile.ZipFile(visual_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps(images, ensure_ascii=False, indent=2))
        for name, data in unique.items():
            archive.writestr(name, data)
    restored = json.loads(gzip.decompress(raw_path.read_bytes()))
    for name, entry in restored['files'].items():
        data = entry['content'].encode('utf-8') if entry['encoding'] == 'utf-8' else base64.b64decode(entry['content'])
        assert len(data) == entry['bytes'] and sha(data) == entry['sha256']
        assert data == (ROOT / name).read_bytes()
    with zipfile.ZipFile(visual_path) as archive:
        assert archive.testzip() is None
        for name, entry in images.items():
            data = archive.read(entry['archive'])
            assert sha(data) == entry['sha256'] and data == (ROOT / name).read_bytes()
    print(json.dumps({'raw_files': len(raw), 'png_references': len(images), 'unique_pngs': len(unique),
                      'raw_archive_bytes': len(packed), 'visual_archive_bytes': visual_path.stat().st_size,
                      'all_exact_roundtrips_passed': True}))


if __name__ == '__main__':
    main()

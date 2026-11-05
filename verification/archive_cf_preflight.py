"""Archive the fixed CF stage-one evidence set, preserving failed attempts."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ('preflight_001', 'root_review_001', 'root_native_001', 'vg_integration_001')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    raw, assets, unique = {}, {}, {}
    paths = [p for name in DIRECTORIES for p in (ROOT / 'artifacts/cf' / name).rglob('*') if p.is_file()]
    paths.append(ROOT / 'artifacts/cf/vg_integration_001.log')
    for path in sorted(paths):
        if '__pycache__' in path.parts:
            continue
        data = path.read_bytes()
        name = path.relative_to(ROOT).as_posix()
        meta = {'bytes': len(data), 'sha256': sha(data)}
        if path.suffix in ('.png', '.npy'):
            entry = 'assets/' + meta['sha256'] + path.suffix
            assets[name] = meta | {'archive': entry}
            unique[entry] = data
        else:
            try:
                content, encoding = data.decode('utf-8'), 'utf-8'
            except UnicodeDecodeError:
                content, encoding = base64.b64encode(data).decode('ascii'), 'base64'
            raw[name] = meta | {'encoding': encoding, 'content': content}
    result = {'scope': 'Fixed stage-one CF directories, all outcomes retained; excludes future stage-two experiments',
              'files': raw, 'assets_manifest': assets}
    packed = gzip.compress(json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode(), mtime=0)
    raw_path = ROOT / 'docs/cf_preflight_raw.json.gz'
    raw_path.write_bytes(packed)
    visual = ROOT / 'docs/cf_preflight_visual_evidence.zip'
    with zipfile.ZipFile(visual, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json', json.dumps(assets, ensure_ascii=False, indent=2))
        for name, data in unique.items():
            z.writestr(name, data)
    for name, value in json.loads(gzip.decompress(raw_path.read_bytes()))['files'].items():
        data = value['content'].encode() if value['encoding'] == 'utf-8' else base64.b64decode(value['content'])
        assert data == (ROOT / name).read_bytes() and sha(data) == value['sha256']
    with zipfile.ZipFile(visual) as z:
        assert z.testzip() is None
        for name, value in assets.items():
            data = z.read(value['archive'])
            assert data == (ROOT / name).read_bytes() and sha(data) == value['sha256']
    print(json.dumps({'raw_files': len(raw), 'asset_paths': len(assets), 'unique_assets': len(unique),
                      'raw_bytes': len(packed), 'visual_bytes': visual.stat().st_size, 'exact_roundtrip': True}))


if __name__ == '__main__':
    main()
